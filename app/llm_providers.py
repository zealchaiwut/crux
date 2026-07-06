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
"""
from __future__ import annotations

import os

import httpx

_GROQ_BASE_URL = "https://api.groq.com/openai/v1"
_GROQ_TIMEOUT = httpx.Timeout(60.0, connect=10.0, read=30.0, write=5.0, pool=5.0)


class GroqProvider:
    """OpenAI-compatible provider backed by the Groq API."""

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

    async def _post(self, model: str, messages: list) -> str:
        async with httpx.AsyncClient(timeout=_GROQ_TIMEOUT) as client:
            resp = await client.post(
                f"{_GROQ_BASE_URL}/chat/completions",
                json={"model": model, "messages": messages},
                headers=self._headers(),
            )
        resp.raise_for_status()
        return resp.json()["choices"][0]["message"]["content"]

    def _post_sync(self, model: str, messages: list) -> str:
        with httpx.Client(timeout=_GROQ_TIMEOUT) as client:
            resp = client.post(
                f"{_GROQ_BASE_URL}/chat/completions",
                json={"model": model, "messages": messages},
                headers=self._headers(),
            )
        resp.raise_for_status()
        return resp.json()["choices"][0]["message"]["content"]

    async def complete(self, system: str, user: str, model: str | None = None) -> str:
        from app.claude_cli import _strip_fences
        groq_model = self._resolve_model(model)
        text = await self._post(groq_model, self._build_messages(system, user))
        return _strip_fences(text)

    def complete_sync(self, system: str, user: str, model: str | None = None) -> str:
        from app.claude_cli import _strip_fences
        groq_model = self._resolve_model(model)
        text = self._post_sync(groq_model, self._build_messages(system, user))
        return _strip_fences(text)


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
