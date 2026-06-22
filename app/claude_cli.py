"""Run Claude prompts through either the local ``claude`` CLI (Claude Code) or
the Anthropic HTTP API, chosen at runtime by app settings.

Provider is read from app.settings_store on every call:
  * "cli" (default) — shell out to ``claude -p``; bills the Claude subscription,
    no ``ANTHROPIC_API_KEY`` needed, unmetered.
  * "api" — call the Anthropic HTTP API with ``ANTHROPIC_API_KEY``; each call's
    USD cost is tracked against the configured budget. When the budget is
    exhausted (or the key is missing, or the API call fails), callers fall back
    to the CLI automatically.

CLI mechanics: the user prompt is piped on stdin (avoids argv length limits) and
the system prompt is passed via ``--append-system-prompt``.

Requirements (CLI path):
  * the ``claude`` CLI on PATH (Claude Code), authenticated once via ``claude``

Env overrides:
  CLAUDE_CLI_BIN      binary name/path        (default: "claude")
  CLAUDE_CLI_MODEL    default model alias     (default: "haiku")
  CLAUDE_CLI_TIMEOUT  per-call timeout, secs  (default: "120")
  ANTHROPIC_API_KEY   required for the "api" provider
"""
from __future__ import annotations

import asyncio
import os
import re
import shutil
import subprocess
from types import SimpleNamespace

import httpx

from app import settings_store

_CLI = os.environ.get("CLAUDE_CLI_BIN", "claude")
_DEFAULT_MODEL = os.environ.get("CLAUDE_CLI_MODEL", "haiku")
_TIMEOUT = float(os.environ.get("CLAUDE_CLI_TIMEOUT", "120"))

# --- Anthropic HTTP API path -------------------------------------------------
_API_URL = "https://api.anthropic.com/v1/messages"
_API_VERSION = "2023-06-01"
_API_MAX_TOKENS = 4096

# USD per token (input, output), keyed by model alias. Pricing per MTok:
#   haiku-4.5  $1 / $5     sonnet-4.6  $3 / $15     opus  $5 / $25
_PRICING = {
    "haiku": (1.00e-6, 5.00e-6),
    "sonnet": (3.00e-6, 15.00e-6),
    "opus": (5.00e-6, 25.00e-6),
}


def api_key() -> str:
    return os.environ.get("ANTHROPIC_API_KEY", "")


def api_key_present() -> bool:
    return bool(api_key())


def _api_cost_usd(model: str | None, usage: dict) -> float:
    pin, pout = _PRICING.get(_alias(model), _PRICING["haiku"])
    return (usage.get("input_tokens", 0) or 0) * pin + (usage.get("output_tokens", 0) or 0) * pout


def _api_payload(system: str, user: str, model: str | None) -> dict:
    return {
        "model": model or "claude-haiku-4-5",
        "max_tokens": _API_MAX_TOKENS,
        "system": system,
        "messages": [{"role": "user", "content": user}],
    }


def _api_headers() -> dict:
    return {
        "x-api-key": api_key(),
        "anthropic-version": _API_VERSION,
        "content-type": "application/json",
    }


def _api_extract(data: dict, model: str | None) -> tuple[str, float]:
    text = _strip_fences(data["content"][0]["text"])
    return text, _api_cost_usd(model, data.get("usage", {}))


def _use_api(settings: dict) -> bool:
    """True when the API provider is selected, configured, and under budget."""
    return (
        settings["provider"] == "api"
        and api_key_present()
        and settings_store.budget_remaining(settings) > 0
    )


class ClaudeCLIError(Exception):
    """Raised when the claude CLI is missing, errors, times out, or returns nothing."""


def _alias(model: str | None) -> str:
    """Map a full model id (e.g. claude-haiku-4-5-20251001) to a CLI alias."""
    if not model:
        return _DEFAULT_MODEL
    lowered = model.lower()
    for name in ("haiku", "sonnet", "opus"):
        if name in lowered:
            return name
    return model


def _strip_fences(text: str) -> str:
    """Remove a single wrapping ```...``` markdown fence if present."""
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```[^\n]*\n?", "", text)
        text = re.sub(r"\n?```$", "", text.rstrip())
    return text.strip()


def _build_args(system: str, model: str | None) -> list[str]:
    args = [_CLI, "-p", "--output-format", "text", "--model", _alias(model)]
    if system:
        args += ["--append-system-prompt", system]
    return args


def _require_cli() -> None:
    if shutil.which(_CLI) is None:
        raise ClaudeCLIError(
            f"`{_CLI}` not found on PATH. Install Claude Code and run `claude` "
            "once to authenticate."
        )


async def _cli_complete(system: str, user: str, model: str | None = None) -> str:
    """Async: run a one-shot prompt through ``claude -p`` and return cleaned text."""
    _require_cli()
    try:
        proc = await asyncio.create_subprocess_exec(
            *_build_args(system, model),
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        out, err = await asyncio.wait_for(
            proc.communicate(user.encode()), timeout=_TIMEOUT
        )
    except asyncio.TimeoutError as exc:
        raise ClaudeCLIError(f"claude CLI timed out after {_TIMEOUT}s") from exc
    except OSError as exc:
        raise ClaudeCLIError(f"claude CLI failed to start: {exc}") from exc
    if proc.returncode != 0:
        raise ClaudeCLIError(
            f"claude CLI exited {proc.returncode}: {err.decode(errors='replace').strip()}"
        )
    text = _strip_fences(out.decode())
    if not text:
        raise ClaudeCLIError("claude CLI returned empty output")
    return text


def _cli_complete_sync(system: str, user: str, model: str | None = None) -> str:
    """Blocking variant for synchronous call sites."""
    _require_cli()
    try:
        proc = subprocess.run(
            _build_args(system, model),
            input=user.encode(),
            capture_output=True,
            timeout=_TIMEOUT,
        )
    except subprocess.TimeoutExpired as exc:
        raise ClaudeCLIError(f"claude CLI timed out after {_TIMEOUT}s") from exc
    except OSError as exc:
        raise ClaudeCLIError(f"claude CLI failed to start: {exc}") from exc
    if proc.returncode != 0:
        raise ClaudeCLIError(
            f"claude CLI exited {proc.returncode}: {proc.stderr.decode(errors='replace').strip()}"
        )
    text = _strip_fences(proc.stdout.decode())
    if not text:
        raise ClaudeCLIError("claude CLI returned empty output")
    return text


# Errors the API path may raise that should trigger CLI fallback.
_API_FALLBACK_ERRORS = (httpx.HTTPError, KeyError, IndexError, ValueError, OSError)


async def _api_complete(system: str, user: str, model: str | None) -> tuple[str, float]:
    # Structured per-phase timeouts: connect 10s (fast-fail on routing failures),
    # read 30s (room for a multi-token completion), write/pool 5s (small single-
    # connection JSON payload). Avoids one bare float silently governing all phases.
    async with httpx.AsyncClient(
        timeout=httpx.Timeout(60.0, connect=10.0, read=30.0, write=5.0, pool=5.0)
    ) as client:
        resp = await client.post(_API_URL, json=_api_payload(system, user, model), headers=_api_headers())
    resp.raise_for_status()
    return _api_extract(resp.json(), model)


def _api_complete_sync(system: str, user: str, model: str | None) -> tuple[str, float]:
    with httpx.Client(
        timeout=httpx.Timeout(60.0, connect=10.0, read=30.0, write=5.0, pool=5.0)
    ) as client:
        resp = client.post(_API_URL, json=_api_payload(system, user, model), headers=_api_headers())
    resp.raise_for_status()
    return _api_extract(resp.json(), model)


# ---------------------------------------------------------------------------
# Provider dispatch
# ---------------------------------------------------------------------------


async def complete(system: str, user: str, model: str | None = None) -> str:
    """Run a one-shot prompt via the configured provider; fall back to CLI.

    API path is used when selected, keyed, and under budget; on success its USD
    cost is recorded. Any API failure (or exhausted budget) falls through to the
    CLI so the pipeline keeps working.
    """
    settings = settings_store.get_settings()
    if _use_api(settings):
        try:
            text, cost = await _api_complete(system, user, model)
            if text:
                settings_store.add_spend(cost)
                return text
        except _API_FALLBACK_ERRORS:
            pass  # fall back to CLI
    return await _cli_complete(system, user, model)


def complete_sync(system: str, user: str, model: str | None = None) -> str:
    """Blocking variant of :func:`complete` with the same provider dispatch."""
    settings = settings_store.get_settings()
    if _use_api(settings):
        try:
            text, cost = _api_complete_sync(system, user, model)
            if text:
                settings_store.add_spend(cost)
                return text
        except _API_FALLBACK_ERRORS:
            pass  # fall back to CLI
    return _cli_complete_sync(system, user, model)


# ---------------------------------------------------------------------------
# anthropic.Anthropic-compatible shim
# ---------------------------------------------------------------------------
# Drop-in for call sites that expect `client.messages.create(...).content[0].text`.


class _Messages:
    def create(self, *, model=None, messages=None, system=None, **_ignored):
        user = "\n\n".join(
            m["content"] if isinstance(m["content"], str) else str(m["content"])
            for m in (messages or [])
            if m.get("role") == "user"
        )
        text = complete_sync(system or "", user, model)
        return SimpleNamespace(content=[SimpleNamespace(text=text)])


class ClaudeCLIClient:
    """Minimal stand-in for ``anthropic.Anthropic`` covering ``messages.create``."""

    def __init__(self, *_args, **_kwargs) -> None:
        self.messages = _Messages()
