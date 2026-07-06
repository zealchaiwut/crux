"""Tests for issue #199: Route design_probes (three-horizon) through llm_providers.call_stage.

AC coverage:
  AC1 — design_probes calls app.llm_providers.call_stage, not app.claude_cli.complete
  AC2 — JSON schema wraps the three-probe array under a "probes" key
  AC3 — horizon/type/field validation is unchanged and still enforced after unwrapping
  AC4 — structured-output path and plain-text fallback path both covered
  AC5 — design_probe (legacy singular) is untouched
"""
import asyncio
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

import os
os.environ.setdefault("AUTH_SECRET", "test_auth_secret_12345678901")


def _make_structured_provider(return_value):
    p = MagicMock()
    p.supports_structured_output = True
    p.complete_structured = AsyncMock(return_value=return_value)
    p.complete = AsyncMock()
    return p


def _make_text_provider(return_text):
    p = MagicMock()
    p.supports_structured_output = False
    p.complete = AsyncMock(return_value=return_text)
    p.complete_structured = AsyncMock()
    return p


_PLANS_FOR_PROBES = [
    {"label": "A", "name": "Overtraining", "mechanism": "Volume depresses HRV.", "current_rank": 1},
]

_THREE_PROBES = [
    {
        "horizon": "short", "type": "measurement", "target_metric": "Resting HRV",
        "cost": "free", "time": "5 days", "note": "Measure HRV each morning.",
        "steps": ["Wake up", "Measure HRV", "Record value"],
        "duration": "5 days", "decision_rule": "If HRV < 40 → early signal of overtraining",
    },
    {
        "horizon": "mid", "type": "behaviour-experiment", "target_metric": "Session RPE trend",
        "cost": "free", "time": "2 weeks", "note": "Deload for two weeks and track RPE.",
        "steps": ["Reduce volume 50%", "Log RPE per session", "Compare to baseline"],
        "duration": "2 weeks", "decision_rule": "If RPE drops ≥ 2 points → confirmed",
    },
    {
        "horizon": "long", "type": "lab-test", "target_metric": "Cortisol panel",
        "cost": "~£40", "time": "4 weeks", "note": "See a doctor for a blood panel.",
        "steps": ["Book appointment", "Take test", "Review results with doctor"],
        "duration": "4 weeks", "decision_rule": "If cortisol elevated → confirmed; else discard",
    },
]
_THREE_PROBES_WRAPPED = {"probes": _THREE_PROBES}
_THREE_PROBES_JSON_TEXT = json.dumps(_THREE_PROBES_WRAPPED)


class TestCallStageRouting:
    """AC1: design_probes routes through call_stage, not complete() directly."""

    def test_design_probes_does_not_import_complete(self):
        import inspect
        from app import probe
        source = inspect.getsource(probe)
        assert "app.claude_cli import" not in source, (
            "app/probe.py must no longer import from app.claude_cli — "
            "both design_probe and design_probes now route through call_stage"
        )

    def test_structured_output_calls_complete_structured(self):
        from app.probe import design_probes
        provider = _make_structured_provider(_THREE_PROBES_WRAPPED)

        with patch("app.llm_providers.get_provider", return_value=provider):
            asyncio.run(design_probes("Sharpened problem", _PLANS_FOR_PROBES))

        provider.complete_structured.assert_called_once()

    def test_fallback_calls_complete_not_structured(self):
        from app.probe import design_probes
        provider = _make_text_provider(_THREE_PROBES_JSON_TEXT)

        with patch("app.llm_providers.get_provider", return_value=provider):
            asyncio.run(design_probes("Sharpened problem", _PLANS_FOR_PROBES))

        provider.complete.assert_called_once()
        provider.complete_structured.assert_not_called()


class TestSchemaShape:
    """AC2: schema wraps the three-probe array under a 'probes' key."""

    def test_schema_root_is_object_with_probes_key(self):
        from app.probe import _JSON_SCHEMA_THREE
        assert _JSON_SCHEMA_THREE["type"] == "object"
        assert "probes" in _JSON_SCHEMA_THREE["properties"]
        probes_schema = _JSON_SCHEMA_THREE["properties"]["probes"]
        assert probes_schema["type"] == "array"
        assert probes_schema["minItems"] == 3
        assert probes_schema["maxItems"] == 3
        assert _JSON_SCHEMA_THREE["required"] == ["probes"]
        assert _JSON_SCHEMA_THREE["additionalProperties"] is False


class TestValidationUnchanged:
    """AC3: horizon/type/field validation still enforced after unwrapping."""

    def test_structured_output_returns_three_validated_probes(self):
        from app.probe import design_probes
        provider = _make_structured_provider(_THREE_PROBES_WRAPPED)

        with patch("app.llm_providers.get_provider", return_value=provider):
            result = asyncio.run(design_probes("Sharpened problem", _PLANS_FOR_PROBES))

        assert isinstance(result, list)
        assert len(result) == 3
        assert {p["horizon"] for p in result} == {"short", "mid", "long"}
        for p in result:
            assert p["type"] in (
                "measurement", "lab-test", "behaviour-experiment", "prototype"
            )

    def test_fallback_returns_three_validated_probes(self):
        from app.probe import design_probes
        provider = _make_text_provider(_THREE_PROBES_JSON_TEXT)

        with patch("app.llm_providers.get_provider", return_value=provider):
            result = asyncio.run(design_probes("Sharpened problem", _PLANS_FOR_PROBES))

        assert isinstance(result, list)
        assert len(result) == 3
        assert {p["horizon"] for p in result} == {"short", "mid", "long"}

    def test_missing_probes_key_raises_error(self):
        from app.probe import ProbeError, design_probes
        provider = _make_structured_provider({"wrong_key": "value"})

        with patch("app.llm_providers.get_provider", return_value=provider):
            with pytest.raises(ProbeError):
                asyncio.run(design_probes("problem", _PLANS_FOR_PROBES))

    def test_wrong_probe_count_raises_error(self):
        from app.probe import ProbeError, design_probes
        provider = _make_structured_provider({"probes": _THREE_PROBES[:2]})

        with patch("app.llm_providers.get_provider", return_value=provider):
            with pytest.raises(ProbeError):
                asyncio.run(design_probes("problem", _PLANS_FOR_PROBES))

    def test_duplicate_horizons_raises_error(self):
        from app.probe import ProbeError, design_probes
        bad = [dict(_THREE_PROBES[0]), dict(_THREE_PROBES[0]), dict(_THREE_PROBES[2])]
        provider = _make_structured_provider({"probes": bad})

        with patch("app.llm_providers.get_provider", return_value=provider):
            with pytest.raises(ProbeError):
                asyncio.run(design_probes("problem", _PLANS_FOR_PROBES))

    def test_invalid_probe_type_raises_error(self):
        from app.probe import ProbeError, design_probes
        bad = [dict(p) for p in _THREE_PROBES]
        bad[0]["type"] = "not-a-real-type"
        provider = _make_structured_provider({"probes": bad})

        with patch("app.llm_providers.get_provider", return_value=provider):
            with pytest.raises(ProbeError):
                asyncio.run(design_probes("problem", _PLANS_FOR_PROBES))

    def test_malformed_fallback_text_raises_error(self):
        from app.probe import ProbeError, design_probes
        provider = _make_text_provider("not json")

        with patch("app.llm_providers.get_provider", return_value=provider):
            with pytest.raises(ProbeError):
                asyncio.run(design_probes("problem", _PLANS_FOR_PROBES))


class TestLegacyDesignProbeUntouched:
    """AC5: design_probe (legacy singular) still works, unaffected by this change."""

    def test_design_probe_still_returns_single_dict(self):
        from app.probe import design_probe
        single = {
            "type": "measurement", "target_metric": "Resting HRV", "cost": "free",
            "time": "7 days", "note": "Measure HRV each morning.",
            "steps": ["Wake up", "Measure HRV"], "duration": "7 days",
            "decision_rule": "If HRV < 40 → overtraining",
        }
        provider = _make_structured_provider(single)

        with patch("app.llm_providers.get_provider", return_value=provider):
            result = asyncio.run(design_probe("Sharpened problem", _PLANS_FOR_PROBES))

        assert isinstance(result, dict)
        assert result["type"] == "measurement"
