"""Tests for issue #190: Route judgment stages to provider with structured outputs.

AC coverage:
  AC1 — sharpen, bake-off, weigh, probe, summary stages call via provider interface
  AC2 — when provider.supports_structured_output, complete_structured() is used (no fence scraping)
  AC3 — fallback fenced-JSON path is used when provider lacks schema support
  AC4 — output type contracts are preserved (no shape regressions)
  AC5 — stages work against a mocked Groq client returning schema-validated responses
  AC6 — no stage directly imports/instantiates a Groq/provider SDK client
  AC7 — capability detection tested with truthy and falsy case per stage
"""
import asyncio
import importlib
import inspect
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

import os
os.environ.setdefault("AUTH_SECRET", "test_auth_secret_12345678901")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_structured_provider(return_value):
    """Mock provider that supports structured output and returns return_value from complete_structured."""
    p = MagicMock()
    p.supports_structured_output = True
    p.complete_structured = AsyncMock(return_value=return_value)
    p.complete = AsyncMock()
    return p


def _make_text_provider(return_text):
    """Mock provider that does NOT support structured output and returns text from complete()."""
    p = MagicMock()
    p.supports_structured_output = False
    p.complete = AsyncMock(return_value=return_text)
    p.complete_structured = AsyncMock()
    return p


# ---------------------------------------------------------------------------
# AC7: GroqProvider capability flag
# ---------------------------------------------------------------------------

def test_groq_provider_has_structured_output_flag_true():
    """AC7: GroqProvider.supports_structured_output must be True."""
    from app.llm_providers import GroqProvider
    assert getattr(GroqProvider, "supports_structured_output", False) is True


def test_claude_cli_provider_does_not_support_structured_output():
    """AC7: ClaudeCLIProvider.supports_structured_output must be False or absent."""
    from app.claude_cli import ClaudeCLIProvider
    assert not getattr(ClaudeCLIProvider, "supports_structured_output", False)


def test_anthropic_api_provider_does_not_support_structured_output():
    """AC7: AnthropicAPIProvider.supports_structured_output must be False or absent."""
    from app.claude_cli import AnthropicAPIProvider
    assert not getattr(AnthropicAPIProvider, "supports_structured_output", False)


# ---------------------------------------------------------------------------
# AC2: GroqProvider.complete_structured sends response_format json_schema
# ---------------------------------------------------------------------------

def test_groq_complete_structured_sends_response_format(monkeypatch):
    """AC2: complete_structured() POSTs with response_format.type == json_schema."""
    monkeypatch.setenv("GROQ_API_KEY", "gsk-test")
    from app.llm_providers import GroqProvider
    provider = GroqProvider()

    schema = {"type": "object", "properties": {"sharpened": {"type": "string"}}, "required": ["sharpened"], "additionalProperties": False}
    response_body = {"choices": [{"message": {"content": '{"sharpened": "test"}'}}]}

    mock_resp = MagicMock()
    mock_resp.json.return_value = response_body
    mock_resp.raise_for_status.return_value = None

    with patch("httpx.AsyncClient") as MockCls:
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.post = AsyncMock(return_value=mock_resp)
        MockCls.return_value = mock_client

        result = asyncio.run(
            provider.complete_structured("sys", "user", None, "test_schema", schema)
        )

    payload = mock_client.post.call_args[1]["json"]
    assert "response_format" in payload, "request must include response_format"
    rf = payload["response_format"]
    assert rf["type"] == "json_schema", f"response_format.type must be json_schema, got {rf['type']}"
    assert "json_schema" in rf, "response_format must include json_schema key"
    assert rf["json_schema"]["name"] == "test_schema"
    assert result == {"sharpened": "test"}


def test_groq_complete_structured_returns_parsed_dict(monkeypatch):
    """AC2: complete_structured() returns a parsed Python object, not a string."""
    monkeypatch.setenv("GROQ_API_KEY", "gsk-test")
    from app.llm_providers import GroqProvider
    provider = GroqProvider()

    schema = {"type": "object"}
    response_body = {"choices": [{"message": {"content": '{"foo": "bar"}'}}]}
    mock_resp = MagicMock()
    mock_resp.json.return_value = response_body
    mock_resp.raise_for_status.return_value = None

    with patch("httpx.AsyncClient") as MockCls:
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.post = AsyncMock(return_value=mock_resp)
        MockCls.return_value = mock_client

        result = asyncio.run(
            provider.complete_structured("sys", "user", None, "schema", schema)
        )

    assert isinstance(result, dict), f"complete_structured must return dict, got {type(result)}"
    assert result == {"foo": "bar"}


# ---------------------------------------------------------------------------
# AC3: call_stage fallback — fenced-JSON extraction
# ---------------------------------------------------------------------------

def test_call_stage_uses_structured_output_when_supported():
    """AC2/AC3: call_stage uses complete_structured when provider supports it."""
    from app.llm_providers import call_stage
    provider = _make_structured_provider({"k": "v"})

    with patch("app.llm_providers.get_provider", return_value=provider):
        result = asyncio.run(call_stage("sys", "user", None, "name", {"type": "object"}))

    provider.complete_structured.assert_called_once()
    provider.complete.assert_not_called()
    assert result == {"k": "v"}


def test_call_stage_uses_text_fallback_when_no_structured_support():
    """AC3: call_stage falls back to text parsing when provider lacks structured output."""
    from app.llm_providers import call_stage
    provider = _make_text_provider('{"k": "v"}')

    with patch("app.llm_providers.get_provider", return_value=provider):
        result = asyncio.run(call_stage("sys", "user", None, "name", {"type": "object"}))

    provider.complete.assert_called_once()
    provider.complete_structured.assert_not_called()
    assert result == {"k": "v"}


def test_call_stage_fallback_strips_fences():
    """AC3: fallback path strips markdown fences before JSON parsing."""
    from app.llm_providers import call_stage
    fenced_text = '```json\n{"key": "value"}\n```'
    provider = _make_text_provider(fenced_text)

    with patch("app.llm_providers.get_provider", return_value=provider):
        result = asyncio.run(call_stage("sys", "user", None, "name", {"type": "object"}))

    assert result == {"key": "value"}


def test_call_stage_fallback_raises_on_malformed_json():
    """AC3/UAT step 3: fallback raises on malformed JSON instead of silently returning empty."""
    from app.llm_providers import call_stage
    provider = _make_text_provider("not valid json !@#$")

    with patch("app.llm_providers.get_provider", return_value=provider):
        with pytest.raises(Exception):  # json.JSONDecodeError or similar
            asyncio.run(call_stage("sys", "user", None, "name", {"type": "object"}))


# ---------------------------------------------------------------------------
# AC1 + AC6: No direct Groq/provider SDK imports in stage modules
# ---------------------------------------------------------------------------

def test_sharpen_no_direct_sdk_import():
    """AC6: sharpen.py must not import a Groq or provider SDK client directly."""
    import app.sharpen
    src = inspect.getsource(app.sharpen)
    assert "import groq" not in src.lower()
    assert "from groq" not in src.lower()
    assert "GroqProvider()" not in src and "GroqProvider (" not in src


def test_bake_off_no_direct_sdk_import():
    """AC6: bake_off.py must not import a Groq or provider SDK client directly."""
    import app.bake_off
    src = inspect.getsource(app.bake_off)
    assert "import groq" not in src.lower()
    assert "from groq" not in src.lower()
    assert "GroqProvider()" not in src and "GroqProvider (" not in src


def test_weigh_no_direct_sdk_import():
    """AC6: weigh.py must not import a Groq or provider SDK client directly."""
    import app.weigh
    src = inspect.getsource(app.weigh)
    assert "import groq" not in src.lower()
    assert "from groq" not in src.lower()
    assert "GroqProvider()" not in src and "GroqProvider (" not in src


def test_probe_no_direct_sdk_import():
    """AC6: probe.py must not import a Groq or provider SDK client directly."""
    import app.probe
    src = inspect.getsource(app.probe)
    assert "import groq" not in src.lower()
    assert "from groq" not in src.lower()
    assert "GroqProvider()" not in src and "GroqProvider (" not in src


def test_summary_no_direct_sdk_import():
    """AC6: summary.py must not import a Groq or provider SDK client directly."""
    import app.summary
    src = inspect.getsource(app.summary)
    assert "import groq" not in src.lower()
    assert "from groq" not in src.lower()
    assert "GroqProvider()" not in src and "GroqProvider (" not in src


# ---------------------------------------------------------------------------
# AC2 + AC4 + AC5 + AC7: sharpen stage — structured output path
# ---------------------------------------------------------------------------

_SHARPEN_STRUCTURED = {
    "sharpened": "Running performance has dropped 15% over 6 weeks.",
    "not_investigating": ["Shoe wear", "Weather conditions"],
}

_SHARPEN_JSON_TEXT = json.dumps(_SHARPEN_STRUCTURED)


def test_sharpen_structured_output_path_returns_correct_shape():
    """AC2/AC4/AC5: sharpen uses complete_structured and returns {sharpened, not_investigating}."""
    provider = _make_structured_provider(_SHARPEN_STRUCTURED)

    with patch("app.llm_providers.get_provider", return_value=provider):
        from app.sharpen import sharpen_problem
        result = asyncio.run(sharpen_problem("My running is slower"))

    provider.complete_structured.assert_called_once()
    assert isinstance(result["sharpened"], str)
    assert isinstance(result["not_investigating"], list)
    assert result["sharpened"] == _SHARPEN_STRUCTURED["sharpened"]


def test_sharpen_fallback_path_returns_correct_shape():
    """AC3/AC7: sharpen uses text fallback when provider lacks structured output."""
    provider = _make_text_provider(_SHARPEN_JSON_TEXT)

    with patch("app.llm_providers.get_provider", return_value=provider):
        from app.sharpen import sharpen_problem
        result = asyncio.run(sharpen_problem("My running is slower"))

    provider.complete.assert_called_once()
    provider.complete_structured.assert_not_called()
    assert isinstance(result["sharpened"], str)
    assert isinstance(result["not_investigating"], list)


def test_sharpen_malformed_structured_raises_sharpen_error():
    """UAT step 3: sharpen raises SharpenError (not silent null) on malformed response."""
    from app.sharpen import SharpenError
    provider = _make_structured_provider({"wrong_key": "value"})  # missing 'sharpened'

    with patch("app.llm_providers.get_provider", return_value=provider):
        with pytest.raises(SharpenError):
            from app.sharpen import sharpen_problem
            asyncio.run(sharpen_problem("raw"))


def test_sharpen_malformed_fallback_raises_sharpen_error():
    """UAT step 3: sharpen raises SharpenError on malformed fallback text."""
    from app.sharpen import SharpenError
    provider = _make_text_provider("not json at all!!!")

    with patch("app.llm_providers.get_provider", return_value=provider):
        with pytest.raises(SharpenError):
            from app.sharpen import sharpen_problem
            asyncio.run(sharpen_problem("raw"))


# ---------------------------------------------------------------------------
# AC2 + AC4 + AC5 + AC7: bake_off stage
# ---------------------------------------------------------------------------

_PLANS_LIST = [
    {"label": "A", "name": "Overtraining", "mechanism": "Volume depresses HRV.", "prior": 0.55},
    {"label": "B", "name": "Iron deficiency", "mechanism": "Low ferritin.", "prior": 0.30},
    {"label": "C", "name": "Sleep debt", "mechanism": "Poor sleep.", "prior": 0.15},
]

# Structured output wraps list in an object
_BAKE_OFF_STRUCTURED = {"plans": _PLANS_LIST}
_BAKE_OFF_JSON_TEXT = json.dumps(_PLANS_LIST)  # fallback returns bare array


def test_bake_off_structured_output_returns_list_of_plans():
    """AC2/AC4/AC5: generate_plans uses complete_structured and returns list of 3 plan dicts."""
    provider = _make_structured_provider(_BAKE_OFF_STRUCTURED)

    with patch("app.llm_providers.get_provider", return_value=provider):
        from app.bake_off import generate_plans
        result = asyncio.run(generate_plans("Sharpened problem statement"))

    provider.complete_structured.assert_called_once()
    assert isinstance(result, list)
    assert len(result) == 3
    for plan in result:
        assert "label" in plan and "name" in plan and "mechanism" in plan and "prior" in plan


def test_bake_off_fallback_returns_list_of_plans():
    """AC3/AC7: generate_plans uses text fallback when provider lacks structured output."""
    provider = _make_text_provider(_BAKE_OFF_JSON_TEXT)

    with patch("app.llm_providers.get_provider", return_value=provider):
        from app.bake_off import generate_plans
        result = asyncio.run(generate_plans("Sharpened problem statement"))

    provider.complete.assert_called_once()
    provider.complete_structured.assert_not_called()
    assert isinstance(result, list)
    assert len(result) == 3


def test_bake_off_malformed_structured_raises_error():
    """UAT step 3: generate_plans raises BakeOffError on bad structured response."""
    from app.bake_off import BakeOffError
    provider = _make_structured_provider({"plans": []})  # empty plans list

    with patch("app.llm_providers.get_provider", return_value=provider):
        with pytest.raises(BakeOffError):
            from app.bake_off import generate_plans
            asyncio.run(generate_plans("problem"))


def test_bake_off_malformed_fallback_raises_error():
    """UAT step 3: generate_plans raises BakeOffError on malformed fallback text."""
    from app.bake_off import BakeOffError
    provider = _make_text_provider("not json at all")

    with patch("app.llm_providers.get_provider", return_value=provider):
        with pytest.raises(BakeOffError):
            from app.bake_off import generate_plans
            asyncio.run(generate_plans("problem"))


# ---------------------------------------------------------------------------
# AC2 + AC4 + AC5 + AC7: weigh stage
# ---------------------------------------------------------------------------

_RANKINGS_LIST = [
    {"label": "B", "rank": 1, "standing": "ruled-in", "rationale": "Evidence supports B."},
    {"label": "A", "rank": 2, "standing": None, "rationale": "Neutral evidence."},
    {"label": "C", "rank": 3, "standing": "ruled-out", "rationale": "Contradicted by data."},
]
_WEIGH_STRUCTURED = {"rankings": _RANKINGS_LIST}
_WEIGH_JSON_TEXT = json.dumps(_RANKINGS_LIST)


def test_weigh_structured_output_returns_list_of_rankings():
    """AC2/AC4/AC5: rerank_plans uses complete_structured and returns ranking list."""
    from app.weigh import rerank_plans
    plans = [
        {"label": "A", "name": "Plan A", "mechanism": "Mechanism A"},
        {"label": "B", "name": "Plan B", "mechanism": "Mechanism B"},
        {"label": "C", "name": "Plan C", "mechanism": "Mechanism C"},
    ]
    provider = _make_structured_provider(_WEIGH_STRUCTURED)

    with patch("app.llm_providers.get_provider", return_value=provider):
        result = asyncio.run(rerank_plans("Sharpened problem", plans, "Some context"))

    provider.complete_structured.assert_called_once()
    assert isinstance(result, list)
    assert len(result) == 3
    for item in result:
        assert "label" in item and "rank" in item and "standing" in item and "rationale" in item


def test_weigh_fallback_returns_list_of_rankings():
    """AC3/AC7: rerank_plans uses text fallback when provider lacks structured output."""
    from app.weigh import rerank_plans
    plans = [
        {"label": "A", "name": "Plan A", "mechanism": "Mechanism A"},
        {"label": "B", "name": "Plan B", "mechanism": "Mechanism B"},
        {"label": "C", "name": "Plan C", "mechanism": "Mechanism C"},
    ]
    provider = _make_text_provider(_WEIGH_JSON_TEXT)

    with patch("app.llm_providers.get_provider", return_value=provider):
        result = asyncio.run(rerank_plans("Sharpened problem", plans, "Some context"))

    provider.complete.assert_called_once()
    provider.complete_structured.assert_not_called()
    assert isinstance(result, list)
    assert len(result) == 3


def test_weigh_malformed_structured_raises_error():
    """UAT step 3: rerank_plans raises WeighError on bad structured response."""
    from app.weigh import WeighError, rerank_plans
    plans = [{"label": "A", "name": "A", "mechanism": "m"}]
    provider = _make_structured_provider({"rankings": []})  # no rankings

    with patch("app.llm_providers.get_provider", return_value=provider):
        with pytest.raises(WeighError):
            asyncio.run(rerank_plans("problem", plans, "context"))


def test_weigh_malformed_fallback_raises_error():
    """UAT step 3: rerank_plans raises WeighError on malformed fallback text."""
    from app.weigh import WeighError, rerank_plans
    plans = [{"label": "A", "name": "A", "mechanism": "m"}]
    provider = _make_text_provider("not json")

    with patch("app.llm_providers.get_provider", return_value=provider):
        with pytest.raises(WeighError):
            asyncio.run(rerank_plans("problem", plans, "context"))


# ---------------------------------------------------------------------------
# AC2 + AC4 + AC5 + AC7: probe stage
# ---------------------------------------------------------------------------

_PROBE_DATA = {
    "type": "measurement",
    "target_metric": "Resting HRV",
    "cost": "free",
    "time": "7 days",
    "note": "Measure HRV each morning.",
    "steps": ["Wake up", "Measure HRV", "Record value"],
    "duration": "7 days",
    "decision_rule": "If HRV < 40 → overtraining; else ruled out",
}
_PROBE_JSON_TEXT = json.dumps(_PROBE_DATA)

_PLANS_FOR_PROBE = [
    {"label": "A", "name": "Overtraining", "mechanism": "Volume depresses HRV.", "current_rank": 1},
]


def test_probe_structured_output_returns_probe_dict():
    """AC2/AC4/AC5: design_probe uses complete_structured and returns probe dict."""
    from app.probe import design_probe
    provider = _make_structured_provider(_PROBE_DATA)

    with patch("app.llm_providers.get_provider", return_value=provider):
        result = asyncio.run(design_probe("Sharpened problem", _PLANS_FOR_PROBE))

    provider.complete_structured.assert_called_once()
    assert isinstance(result, dict)
    assert result["type"] in ("measurement", "lab-test", "behaviour-experiment", "prototype")
    assert "target_metric" in result and "cost" in result and "time" in result and "note" in result


def test_probe_fallback_returns_probe_dict():
    """AC3/AC7: design_probe uses text fallback when provider lacks structured output."""
    from app.probe import design_probe
    provider = _make_text_provider(_PROBE_JSON_TEXT)

    with patch("app.llm_providers.get_provider", return_value=provider):
        result = asyncio.run(design_probe("Sharpened problem", _PLANS_FOR_PROBE))

    provider.complete.assert_called_once()
    provider.complete_structured.assert_not_called()
    assert isinstance(result, dict)
    assert "type" in result


def test_probe_malformed_structured_raises_error():
    """UAT step 3: design_probe raises ProbeError on bad structured response."""
    from app.probe import ProbeError, design_probe
    provider = _make_structured_provider({"wrong_key": "value"})  # missing required fields

    with patch("app.llm_providers.get_provider", return_value=provider):
        with pytest.raises(ProbeError):
            asyncio.run(design_probe("problem", _PLANS_FOR_PROBE))


def test_probe_malformed_fallback_raises_error():
    """UAT step 3: design_probe raises ProbeError on malformed fallback text."""
    from app.probe import ProbeError, design_probe
    provider = _make_text_provider("not json")

    with patch("app.llm_providers.get_provider", return_value=provider):
        with pytest.raises(ProbeError):
            asyncio.run(design_probe("problem", _PLANS_FOR_PROBE))


# ---------------------------------------------------------------------------
# AC2 + AC4 + AC5 + AC7: summary stage (generate_summary)
# ---------------------------------------------------------------------------

_SUMMARY_DATA = {
    "problem_statement": "Running performance dropped.",
    "option_ranking": "A: overtraining (rank 1). B: iron (rank 2). C: sleep (rank 3).",
    "recommended_plan": "Pursue Plan A: reduce training volume.",
    "probe_plan": "Measure resting HRV daily for 7 days.",
}
_SUMMARY_JSON_TEXT = json.dumps(_SUMMARY_DATA)

_CASE_DATA = {
    "sharpened": "Running perf dropped 15% over 6 weeks.",
    "plans": [
        {"label": "A", "name": "Overtraining", "mechanism": "Volume.", "current_rank": 1, "sources": []},
    ],
    "probe": {"type": "measurement", "target_metric": "HRV", "note": "Measure daily"},
}


def test_summary_generate_summary_structured_output_returns_json():
    """AC2/AC4/AC5: generate_summary uses complete_structured and returns JSON string."""
    from app.summary import generate_summary
    provider = _make_structured_provider(_SUMMARY_DATA)

    with patch("app.llm_providers.get_provider", return_value=provider):
        result = asyncio.run(generate_summary(_CASE_DATA))

    provider.complete_structured.assert_called_once()
    parsed = json.loads(result)
    assert "problem_statement" in parsed
    assert "option_ranking" in parsed
    assert "recommended_plan" in parsed
    assert "probe_plan" in parsed


def test_summary_generate_summary_fallback_returns_json():
    """AC3/AC7: generate_summary uses text fallback when provider lacks structured output."""
    from app.summary import generate_summary
    provider = _make_text_provider(_SUMMARY_JSON_TEXT)

    with patch("app.llm_providers.get_provider", return_value=provider):
        result = asyncio.run(generate_summary(_CASE_DATA))

    provider.complete.assert_called_once()
    provider.complete_structured.assert_not_called()
    parsed = json.loads(result)
    assert "problem_statement" in parsed


def test_summary_generate_summary_malformed_structured_raises_error():
    """UAT step 3: generate_summary raises SummaryError on bad structured response."""
    from app.summary import SummaryError, generate_summary
    provider = _make_structured_provider({"incomplete": "data"})  # missing required fields

    with patch("app.llm_providers.get_provider", return_value=provider):
        with pytest.raises(SummaryError):
            asyncio.run(generate_summary(_CASE_DATA))


def test_summary_generate_summary_malformed_fallback_raises_error():
    """UAT step 3: generate_summary raises SummaryError on malformed fallback text."""
    from app.summary import SummaryError, generate_summary
    provider = _make_text_provider("not valid json")

    with patch("app.llm_providers.get_provider", return_value=provider):
        with pytest.raises(SummaryError):
            asyncio.run(generate_summary(_CASE_DATA))


# ---------------------------------------------------------------------------
# AC5: UAT step 4 — existing per-stage tests must still pass (verified by running them)
# No direct test here; the existing test files cover this.
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# AC5: UAT step 5 — verify request payload includes response_format + schema
# ---------------------------------------------------------------------------

def test_groq_complete_structured_includes_schema_in_payload(monkeypatch):
    """AC5/UAT step 5: complete_structured request payload contains response_format json_schema."""
    monkeypatch.setenv("GROQ_API_KEY", "gsk-test")
    from app.llm_providers import GroqProvider
    provider = GroqProvider()

    schema = {
        "type": "object",
        "properties": {"sharpened": {"type": "string"}},
        "required": ["sharpened"],
        "additionalProperties": False,
    }
    resp_body = {"choices": [{"message": {"content": '{"sharpened": "ok"}'}}]}
    mock_resp = MagicMock()
    mock_resp.json.return_value = resp_body
    mock_resp.raise_for_status.return_value = None

    captured_payload = {}

    async def fake_post(url, json=None, headers=None):
        captured_payload.update(json or {})
        return mock_resp

    with patch("httpx.AsyncClient") as MockCls:
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.post = AsyncMock(side_effect=fake_post)
        MockCls.return_value = mock_client

        asyncio.run(provider.complete_structured("sys", "user", None, "sharpen_output", schema))

    assert "response_format" in captured_payload
    assert captured_payload["response_format"]["type"] == "json_schema"
    nested = captured_payload["response_format"]["json_schema"]
    assert nested["name"] == "sharpen_output"
    assert nested["schema"] == schema
