"""LLM provider abstraction for the crux pipeline (issue #189).

CRUX_LLM_PROVIDER selects the active backend:
  groq          — Groq OpenAI-compatible API (GROQ_API_KEY required)
  anthropic_api — Anthropic HTTP API (ANTHROPIC_API_KEY required)
  claude_cli    — Local ``claude -p`` CLI subprocess
  (unset)       — Falls through to settings_store runtime toggle (existing behaviour)

Model selection for Groq:
  CRUX_JUDGMENT_MODEL  model for judgment/scoring stages (default: openai/gpt-oss-120b)
  CRUX_BULK_MODEL      model for bulk/high-volume stages (default: llama-3.1-8b-instant)
  Haiku callers → bulk; Sonnet/Opus callers → judgment.

Structured output (issue #190):
  Providers that set supports_structured_output = True expose complete_structured(),
  which sends response_format.json_schema and returns a parsed Python object —
  no fenced-JSON scraping required. Providers without this flag fall back to the
  existing text → _strip_fences → json.loads path via call_stage().

Bulk routing (issue #191):
  call_bulk_stage() / call_bulk_stage_sync() route high-volume, low-stakes pipeline
  calls (content_summary, dedup, candidate_summarization) explicitly to CRUX_BULK_MODEL
  via complete_bulk_structured() — never the judgment model, regardless of caller model name.
"""
from __future__ import annotations

import json as _json
import logging
import os

import httpx

_GROQ_BASE_URL = "https://api.groq.com/openai/v1"
_GROQ_TIMEOUT = httpx.Timeout(60.0, connect=10.0, read=30.0, write=5.0, pool=5.0)
_log = logging.getLogger(__name__)


class GroqBudgetExhaustedError(Exception):
    """Raised when the combined USD budget (Anthropic + Groq spend) is exhausted."""


class GroqProvider:
    """OpenAI-compatible provider backed by the Groq API."""

    supports_structured_output: bool = True

    def __init__(self) -> None:
        self._api_key = os.environ.get("GROQ_API_KEY", "")
        self._judgment_model = os.environ.get("CRUX_JUDGMENT_MODEL", "openai/gpt-oss-120b")
        self._bulk_model = os.environ.get("CRUX_BULK_MODEL", "llama-3.1-8b-instant")

    def _resolve_model(self, model: str | None) -> str:
        if model:
            lowered = model.lower()
            if "sonnet" in lowered or "opus" in lowered:
                return self._judgment_model
        return self._bulk_model

    def _headers(self) -> dict:
        return {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }

    def _build_messages(self, system: str, user: str) -> list:
        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": user})
        return messages

    async def _post(self, model: str, messages: list) -> tuple[str, dict]:
        async with httpx.AsyncClient(timeout=_GROQ_TIMEOUT) as client:
            resp = await client.post(
                f"{_GROQ_BASE_URL}/chat/completions",
                json={"model": model, "messages": messages},
                headers=self._headers(),
            )
        resp.raise_for_status()
        data = resp.json()
        return data["choices"][0]["message"]["content"], data.get("usage", {})

    def _post_sync(self, model: str, messages: list) -> tuple[str, dict]:
        with httpx.Client(timeout=_GROQ_TIMEOUT) as client:
            resp = client.post(
                f"{_GROQ_BASE_URL}/chat/completions",
                json={"model": model, "messages": messages},
                headers=self._headers(),
            )
        resp.raise_for_status()
        data = resp.json()
        return data["choices"][0]["message"]["content"], data.get("usage", {})

    def _groq_cost_usd(self, model: str, usage: dict) -> float:
        from app import settings_store
        rates = settings_store.get_settings().get("groq_rates", {})
        model_rates = rates.get(model)
        if model_rates is None:
            _log.warning(
                "No Groq rate configured for model %s; cost counted as $0.00", model
            )
            return 0.0
        prompt_tokens = usage.get("prompt_tokens", 0) or 0
        completion_tokens = usage.get("completion_tokens", 0) or 0
        return (prompt_tokens / 1_000_000) * model_rates.get("input_per_1m", 0) + \
               (completion_tokens / 1_000_000) * model_rates.get("output_per_1m", 0)

    def _check_budget(self) -> None:
        from app import settings_store
        settings = settings_store.get_settings()
        if settings["api_usd_budget"] > 0 and settings_store.budget_remaining(settings) <= 0:
            spent = settings["api_usd_spent"] + settings.get("groq_usd_spent", 0.0)
            raise GroqBudgetExhaustedError(
                f"USD budget exhausted (limit=${settings['api_usd_budget']:.4f}, "
                f"combined_spent=${spent:.6f}); halting Groq call. "
                f"Groq spend: ${settings.get('groq_usd_spent', 0.0):.6f}, "
                f"Anthropic spend: ${settings['api_usd_spent']:.6f}"
            )

    def _record_spend(self, model: str, usage: dict) -> float:
        from app import settings_store
        cost = self._groq_cost_usd(model, usage)
        prompt_tokens = usage.get("prompt_tokens", 0) or 0
        completion_tokens = usage.get("completion_tokens", 0) or 0
        _log.info(
            "Groq stage: model=%s tokens_in=%d tokens_out=%d cost_usd=%.8f",
            model, prompt_tokens, completion_tokens, cost,
        )
        settings_store.add_groq_spend(cost)
        return cost

    async def complete(self, system: str, user: str, model: str | None = None) -> str:
        from app.claude_cli import _strip_fences
        self._check_budget()
        groq_model = self._resolve_model(model)
        content, usage = await self._post(groq_model, self._build_messages(system, user))
        self._record_spend(groq_model, usage)
        return _strip_fences(content)

    def complete_sync(self, system: str, user: str, model: str | None = None) -> str:
        from app.claude_cli import _strip_fences
        self._check_budget()
        groq_model = self._resolve_model(model)
        content, usage = self._post_sync(groq_model, self._build_messages(system, user))
        self._record_spend(groq_model, usage)
        return _strip_fences(content)

    async def complete_structured(
        self,
        system: str,
        user: str,
        model: str | None,
        schema_name: str,
        json_schema: dict,
    ) -> dict | list:
        """POST with response_format json_schema; return a parsed Python object."""
        self._check_budget()
        groq_model = self._resolve_model(model)
        payload = {
            "model": groq_model,
            "messages": self._build_messages(system, user),
            "response_format": {
                "type": "json_schema",
                "json_schema": {
                    "name": schema_name,
                    "schema": json_schema,
                    "strict": True,
                },
            },
        }
        async with httpx.AsyncClient(timeout=_GROQ_TIMEOUT) as client:
            resp = await client.post(
                f"{_GROQ_BASE_URL}/chat/completions",
                json=payload,
                headers=self._headers(),
            )
        resp.raise_for_status()
        data = resp.json()
        self._record_spend(groq_model, data.get("usage", {}))
        content = data["choices"][0]["message"]["content"]
        return _json.loads(content)

    async def complete_bulk_structured(
        self,
        system: str,
        user: str,
        schema_name: str,
        json_schema: dict,
    ) -> dict | list:
        """Structured output always using CRUX_BULK_MODEL — no model-name inference.

        Unlike complete_structured(), this method never inspects the caller's model
        name to decide routing; it always dispatches to self._bulk_model.
        """
        self._check_budget()
        payload = {
            "model": self._bulk_model,
            "messages": self._build_messages(system, user),
            "response_format": {
                "type": "json_schema",
                "json_schema": {
                    "name": schema_name,
                    "schema": json_schema,
                    "strict": True,
                },
            },
        }
        async with httpx.AsyncClient(timeout=_GROQ_TIMEOUT) as client:
            resp = await client.post(
                f"{_GROQ_BASE_URL}/chat/completions",
                json=payload,
                headers=self._headers(),
            )
        resp.raise_for_status()
        data = resp.json()
        self._record_spend(self._bulk_model, data.get("usage", {}))
        content = data["choices"][0]["message"]["content"]
        return _json.loads(content)

    def complete_bulk_structured_sync(
        self,
        system: str,
        user: str,
        schema_name: str,
        json_schema: dict,
    ) -> dict | list:
        """Synchronous version of complete_bulk_structured."""
        self._check_budget()
        payload = {
            "model": self._bulk_model,
            "messages": self._build_messages(system, user),
            "response_format": {
                "type": "json_schema",
                "json_schema": {
                    "name": schema_name,
                    "schema": json_schema,
                    "strict": True,
                },
            },
        }
        with httpx.Client(timeout=_GROQ_TIMEOUT) as client:
            resp = client.post(
                f"{_GROQ_BASE_URL}/chat/completions",
                json=payload,
                headers=self._headers(),
            )
        resp.raise_for_status()
        data = resp.json()
        self._record_spend(self._bulk_model, data.get("usage", {}))
        content = data["choices"][0]["message"]["content"]
        return _json.loads(content)


_VALID_PROVIDERS = {"", "groq", "anthropic_api", "claude_cli"}


def get_provider():
    """Factory: read CRUX_LLM_PROVIDER and return the matching provider or None.

    Returns None when CRUX_LLM_PROVIDER is unset, signalling callers to fall
    through to the existing settings_store runtime toggle.
    Raises ValueError for unrecognised provider names.
    """
    from app.claude_cli import AnthropicAPIProvider, ClaudeCLIProvider

    name = os.environ.get("CRUX_LLM_PROVIDER", "")
    if name == "groq":
        return GroqProvider()
    if name == "anthropic_api":
        return AnthropicAPIProvider()
    if name == "claude_cli":
        return ClaudeCLIProvider()
    if name:
        raise ValueError(
            f"Unknown CRUX_LLM_PROVIDER '{name}'. Accepted: groq, anthropic_api, claude_cli"
        )
    return None


async def call_stage(
    system: str,
    user: str,
    model: str | None,
    schema_name: str,
    json_schema: dict,
) -> dict | list:
    """Route a judgment-stage call to the active provider.

    When the provider supports response_format json_schema, calls complete_structured()
    and returns the parsed Python object directly — no fenced-JSON scraping.

    When the provider lacks structured-output support (or no provider is configured),
    falls back to plain text completion followed by _strip_fences() + json.loads().
    """
    from app.claude_cli import _strip_fences
    from app.claude_cli import complete as _cli_complete

    provider = get_provider()

    if provider is not None and getattr(provider, "supports_structured_output", False):
        return await provider.complete_structured(system, user, model, schema_name, json_schema)

    _log.warning(
        "Provider %s does not support response_format json_schema; using fenced-JSON fallback",
        type(provider).__name__ if provider is not None else "none (settings_store)",
    )
    if provider is not None:
        text = await provider.complete(system, user, model)
    else:
        text = await _cli_complete(system, user, model)

    return _json.loads(_strip_fences(text))


async def call_bulk_stage(
    system: str,
    user: str,
    schema_name: str,
    json_schema: dict,
) -> dict | list:
    """Route a bulk-stage call to CRUX_BULK_MODEL via the active provider.

    Unlike call_stage(), always dispatches to the configured bulk model (CRUX_BULK_MODEL)
    regardless of the caller's model name — never falls through to the judgment model.

    When the provider exposes complete_bulk_structured(), that is called for explicit
    bulk routing with structured output. Falls back to text completion + JSON parsing
    when the provider lacks structured-output support.
    """
    from app.claude_cli import _strip_fences
    from app.claude_cli import complete as _cli_complete

    provider = get_provider()

    if provider is not None and getattr(provider, "supports_structured_output", False):
        if hasattr(provider, "complete_bulk_structured"):
            return await provider.complete_bulk_structured(system, user, schema_name, json_schema)
        return await provider.complete_structured(system, user, None, schema_name, json_schema)

    _log.warning(
        "Bulk provider %s does not support response_format json_schema; using fenced-JSON fallback",
        type(provider).__name__ if provider is not None else "none (settings_store)",
    )
    if provider is not None:
        text = await provider.complete(system, user, None)
    else:
        text = await _cli_complete(system, user, None)

    return _json.loads(_strip_fences(text))


def call_bulk_stage_sync(
    system: str,
    user: str,
    schema_name: str,
    json_schema: dict,
) -> dict | list:
    """Synchronous version of call_bulk_stage for use in sync contexts (e.g. research orchestrator).

    Routes to CRUX_BULK_MODEL via complete_bulk_structured_sync() when available.
    Falls back to complete_sync() + JSON parsing otherwise.
    """
    from app.claude_cli import _strip_fences
    from app.claude_cli import complete_sync as _cli_complete_sync

    provider = get_provider()

    if provider is not None and getattr(provider, "supports_structured_output", False):
        if hasattr(provider, "complete_bulk_structured_sync"):
            return provider.complete_bulk_structured_sync(system, user, schema_name, json_schema)

    if provider is not None and hasattr(provider, "complete_sync"):
        text = provider.complete_sync(system, user, None)
        return _json.loads(_strip_fences(text))

    text = _cli_complete_sync(system, user, None)
    return _json.loads(_strip_fences(text))
