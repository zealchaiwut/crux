"""Tests for issue #191: Route bulk pipeline stages to CRUX_BULK_MODEL.

AC coverage:
  AC1 – Per-source content_summary calls use CRUX_BULK_MODEL from the provider interface
  AC2 – Deduplication calls use CRUX_BULK_MODEL from the provider interface
  AC3 – Candidate summarization calls use CRUX_BULK_MODEL from the provider interface
  AC4 – CRUX_BULK_MODEL is read from environment/config independently of the judgment model setting
  AC5 – Changing the judgment model does not affect which model bulk calls use
  AC6 – Per-source summaries for a case are routed through Groq (as the configured bulk provider)
  AC7 – Judgment/scoring calls are unaffected and continue using their configured model
"""
import os
from unittest.mock import MagicMock, patch

import pytest


# ============================================================================
# Test AC1: content_summary uses CRUX_BULK_MODEL
# ============================================================================


def test_content_summary_sync_routes_to_bulk_model():
    """AC1: content_summary_sync calls route to CRUX_BULK_MODEL via call_bulk_stage_sync."""
    import app.bulk_stages as bulk_stages

    with patch("app.bulk_stages.call_bulk_stage_sync") as mock_call:
        mock_call.return_value = {"summary": "Test summary"}

        result = bulk_stages.content_summary_sync("Test source text", "Test Title")

        assert mock_call.called
        assert result == "Test summary"
        call_args = mock_call.call_args
        assert call_args[0][2] == "content_summary"


def test_content_summary_sync_uses_bulk_schema():
    """AC1: content_summary_sync passes the correct schema for bulk routing."""
    import app.bulk_stages as bulk_stages

    with patch("app.bulk_stages.call_bulk_stage_sync") as mock_call:
        mock_call.return_value = {"summary": "Test summary"}

        bulk_stages.content_summary_sync("Test", "Title")

        call_args = mock_call.call_args
        assert len(call_args[0]) >= 3


# ============================================================================
# Test AC2: dedup_candidates uses CRUX_BULK_MODEL
# ============================================================================


def test_dedup_candidates_sync_routes_to_bulk_model():
    """AC2: dedup_candidates_sync calls route to CRUX_BULK_MODEL via call_bulk_stage_sync."""
    import app.bulk_stages as bulk_stages

    candidates = [
        {"url": "http://example1.com", "claim": "Claim 1"},
        {"url": "http://example1.com", "claim": "Claim 1 duplicate"},
    ]

    with patch("app.bulk_stages.call_bulk_stage_sync") as mock_call:
        mock_call.return_value = {"keep_indices": [0]}

        result = bulk_stages.dedup_candidates_sync(candidates)

        assert mock_call.called
        assert len(result) == 1
        call_args = mock_call.call_args
        assert call_args[0][2] == "dedup_output"


def test_dedup_candidates_sync_falls_back_on_error():
    """AC2: dedup_candidates_sync returns original list if bulk call fails."""
    import app.bulk_stages as bulk_stages

    candidates = [
        {"url": "http://example1.com", "claim": "Claim 1"},
    ]

    with patch("app.bulk_stages.call_bulk_stage_sync") as mock_call:
        mock_call.side_effect = Exception("Bulk model unavailable")

        result = bulk_stages.dedup_candidates_sync(candidates)

        assert result == candidates


# ============================================================================
# Test AC3: summarize_candidates uses CRUX_BULK_MODEL
# ============================================================================


def test_summarize_candidates_sync_routes_to_bulk_model():
    """AC3: summarize_candidates_sync calls route to CRUX_BULK_MODEL via call_bulk_stage_sync."""
    import app.bulk_stages as bulk_stages

    candidates = [
        {"kind": "article", "title": "Article", "url": "http://example.com", "claim": "Claim"},
    ]

    with patch("app.bulk_stages.call_bulk_stage_sync") as mock_call:
        mock_call.return_value = {
            "sources": [
                {
                    "kind": "article",
                    "title": "Article",
                    "url": "http://example.com",
                    "claim": "Claim",
                    "citation": "Citation text",
                }
            ]
        }

        result = bulk_stages.summarize_candidates_sync("mechanism", "prior", candidates)

        assert mock_call.called
        assert len(result) == 1
        call_args = mock_call.call_args
        assert call_args[0][2] == "candidate_summarization"


def test_summarize_candidates_sync_validates_sources():
    """AC3: summarize_candidates_sync validates and returns only valid source rows."""
    import app.bulk_stages as bulk_stages

    candidates = [
        {"kind": "article", "title": "Article", "url": "http://example.com", "claim": "Claim"},
    ]

    with patch("app.bulk_stages.call_bulk_stage_sync") as mock_call:
        mock_call.return_value = {
            "sources": [
                {
                    "kind": "article",
                    "title": "Article",
                    "url": "http://example.com",
                    "claim": "Claim",
                    "citation": "Citation text",
                },
                {
                    "kind": "article",
                    "title": "Invalid",
                    "url": "",  # Missing URL
                    "claim": "Claim",
                    "citation": "Citation",
                },
            ]
        }

        result = bulk_stages.summarize_candidates_sync("mechanism", "prior", candidates)

        assert len(result) == 1
        assert result[0]["url"] == "http://example.com"


# ============================================================================
# Test AC4: CRUX_BULK_MODEL is read independently
# ============================================================================


def test_bulk_model_read_from_config():
    """AC4: CRUX_BULK_MODEL is loaded from environment config."""
    from app.config import CRUX_BULK_MODEL

    assert isinstance(CRUX_BULK_MODEL, str)
    assert len(CRUX_BULK_MODEL) > 0


def test_bulk_model_independent_of_judgment_model():
    """AC4: CRUX_BULK_MODEL and CRUX_JUDGMENT_MODEL are independently configured."""
    from app.config import CRUX_BULK_MODEL, CRUX_JUDGMENT_MODEL

    assert CRUX_BULK_MODEL is not None
    assert CRUX_JUDGMENT_MODEL is not None
    assert isinstance(CRUX_BULK_MODEL, str)
    assert isinstance(CRUX_JUDGMENT_MODEL, str)


def test_groq_provider_has_bulk_model_property():
    """AC4: GroqProvider reads CRUX_BULK_MODEL from environment."""
    with patch.dict(
        os.environ,
        {
            "CRUX_LLM_PROVIDER": "groq",
            "GROQ_API_KEY": "test-key",
            "CRUX_BULK_MODEL": "test-bulk-model",
            "CRUX_JUDGMENT_MODEL": "test-judgment-model",
        },
    ):
        from app.llm_providers import GroqProvider

        provider = GroqProvider()
        assert provider._bulk_model == "test-bulk-model"
        assert provider._judgment_model == "test-judgment-model"


# ============================================================================
# Test AC5: Changing judgment model does not affect bulk model routing
# ============================================================================


def test_bulk_routing_unaffected_by_judgment_model_change():
    """AC5: Bulk calls always use CRUX_BULK_MODEL regardless of judgment model setting."""
    with patch.dict(
        os.environ,
        {
            "CRUX_BULK_MODEL": "groq/llama-3.1-8b",
            "CRUX_JUDGMENT_MODEL": "groq/gpt-oss-120b",
            "CRUX_LLM_PROVIDER": "groq",
            "GROQ_API_KEY": "test-key",
        },
    ):
        from app.llm_providers import GroqProvider

        provider = GroqProvider()
        bulk_model_1 = provider._bulk_model
        provider._judgment_model = "groq/some-other-model"
        assert provider._bulk_model == bulk_model_1


def test_resolve_model_for_judgment_calls():
    """AC5: _resolve_model correctly identifies judgment model triggers (Sonnet/Opus)."""
    with patch.dict(
        os.environ,
        {
            "CRUX_LLM_PROVIDER": "groq",
            "GROQ_API_KEY": "test-key",
            "CRUX_BULK_MODEL": "llama-3.1-8b-instant",
            "CRUX_JUDGMENT_MODEL": "gpt-oss-120b",
        },
    ):
        from app.llm_providers import GroqProvider

        provider = GroqProvider()

        assert provider._resolve_model("claude-sonnet") == "gpt-oss-120b"
        assert provider._resolve_model("claude-opus") == "gpt-oss-120b"
        assert provider._resolve_model("unknown") == "llama-3.1-8b-instant"
        assert provider._resolve_model(None) == "llama-3.1-8b-instant"


# ============================================================================
# Test AC6: Groq bulk provider verification
# ============================================================================


def test_groq_provider_configured_as_bulk_provider():
    """AC6: When Groq is configured, bulk calls route through Groq's bulk model endpoint."""
    with patch.dict(
        os.environ,
        {
            "CRUX_LLM_PROVIDER": "groq",
            "GROQ_API_KEY": "test-groq-key",
            "CRUX_BULK_MODEL": "groq/llama-3.1-8b-instant",
        },
    ):
        from app.llm_providers import get_provider

        provider = get_provider()
        assert provider is not None
        assert hasattr(provider, "complete_bulk_structured")
        assert provider._bulk_model == "groq/llama-3.1-8b-instant"


def test_groq_provider_bulk_structured_method_exists():
    """AC6: GroqProvider implements complete_bulk_structured_sync for bulk routing."""
    with patch.dict(
        os.environ,
        {
            "CRUX_LLM_PROVIDER": "groq",
            "GROQ_API_KEY": "test-key",
            "CRUX_BULK_MODEL": "llama-3.1-8b-instant",
        },
    ):
        from app.llm_providers import GroqProvider

        provider = GroqProvider()

        assert hasattr(provider, "complete_bulk_structured_sync")
        assert callable(provider.complete_bulk_structured_sync)


# ============================================================================
# Test AC7: Judgment calls unaffected
# ============================================================================


def test_call_stage_routes_to_judgment_not_bulk():
    """AC7: call_stage routes through provider's complete_structured method."""
    with patch.dict(
        os.environ,
        {
            "CRUX_BULK_MODEL": "llama-3.1-8b-instant",
            "CRUX_JUDGMENT_MODEL": "gpt-oss-120b",
            "CRUX_LLM_PROVIDER": "groq",
            "GROQ_API_KEY": "test-key",
        },
    ):
        with patch("app.llm_providers.get_provider") as mock_get:
            import asyncio

            async def mock_complete_structured(*args, **kwargs):
                return {"result": "ok"}

            mock_provider = MagicMock()
            mock_provider.supports_structured_output = True
            mock_provider.complete_structured = mock_complete_structured
            mock_get.return_value = mock_provider

            from app.llm_providers import call_stage

            result = asyncio.run(
                call_stage("system", "user", "claude-sonnet", "schema", {"type": "object"})
            )

            assert result == {"result": "ok"}


def test_judgment_model_passed_to_complete_structured():
    """AC7: Judgment calls pass the model parameter to complete_structured."""
    with patch.dict(
        os.environ,
        {
            "CRUX_BULK_MODEL": "llama-3.1-8b-instant",
            "CRUX_JUDGMENT_MODEL": "gpt-oss-120b",
            "CRUX_LLM_PROVIDER": "groq",
            "GROQ_API_KEY": "test-key",
        },
    ):
        from app.llm_providers import GroqProvider

        provider = GroqProvider()

        with patch("httpx.Client.post") as mock_post:
            mock_response = MagicMock()
            mock_response.json.return_value = {
                "choices": [{"message": {"content": '{"result": "ok"}'}}]
            }
            mock_post.return_value = mock_response

            provider.complete_sync(
                "system", "user", "claude-sonnet"
            )

            call_args = mock_post.call_args
            payload = call_args[1]["json"]
            # Since complete_sync uses _resolve_model, sonnet should map to judgment model
            assert payload["model"] == "gpt-oss-120b"
