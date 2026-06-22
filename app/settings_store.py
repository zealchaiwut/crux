"""Runtime-editable app settings, persisted to a gitignored local JSON file.

Holds the Claude provider choice and the API-path USD budget. Secrets stay in
``.env`` — this file never stores the API key, only the toggle and budget.

Schema (settings.local.json):
    {
      "provider": "cli" | "api",   # which Claude backend to use
      "api_usd_budget": 5.0,        # USD cap for the API path (0 = no API spend)
      "api_usd_spent": 0.0          # accumulated API spend in USD
    }

The CLI path (`claude -p`) is unmetered — it bills against the subscription, so
the budget only governs the API path. When API spend reaches the budget, callers
fall back to the CLI automatically (see app/claude_cli.py).
"""
from __future__ import annotations

import json
import os
import threading
from pathlib import Path

_PATH = Path(
    os.environ.get(
        "CRUX_SETTINGS_FILE", str(Path(__file__).resolve().parent.parent / "settings.local.json")
    )
)
_LOCK = threading.Lock()
_DEFAULTS = {"provider": "cli", "api_usd_budget": 5.0, "api_usd_spent": 0.0}


def _coerce(data: dict) -> dict:
    merged = {**_DEFAULTS, **(data if isinstance(data, dict) else {})}
    merged["provider"] = "api" if merged.get("provider") == "api" else "cli"
    try:
        merged["api_usd_budget"] = max(0.0, float(merged.get("api_usd_budget") or 0.0))
    except (TypeError, ValueError):
        merged["api_usd_budget"] = _DEFAULTS["api_usd_budget"]
    try:
        merged["api_usd_spent"] = max(0.0, float(merged.get("api_usd_spent") or 0.0))
    except (TypeError, ValueError):
        merged["api_usd_spent"] = 0.0
    return merged


def _load() -> dict:
    try:
        with open(_PATH, encoding="utf-8") as f:
            raw = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        raw = {}
    return _coerce(raw)


def _save(data: dict) -> None:
    tmp = _PATH.with_name(_PATH.name + ".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
    os.replace(tmp, _PATH)


def get_settings() -> dict:
    with _LOCK:
        return _load()


def update_settings(provider: str | None = None, api_usd_budget: float | None = None) -> dict:
    with _LOCK:
        data = _load()
        if provider is not None:
            data["provider"] = "api" if provider == "api" else "cli"
        if api_usd_budget is not None:
            data["api_usd_budget"] = max(0.0, float(api_usd_budget))
        _save(data)
        return data


def add_spend(usd: float) -> None:
    """Accumulate API spend (USD). No-op for non-positive amounts."""
    if not usd or usd <= 0:
        return
    with _LOCK:
        data = _load()
        data["api_usd_spent"] = round(data["api_usd_spent"] + float(usd), 6)
        _save(data)


def reset_spend() -> dict:
    with _LOCK:
        data = _load()
        data["api_usd_spent"] = 0.0
        _save(data)
        return data


def budget_remaining(data: dict | None = None) -> float:
    d = data if data is not None else get_settings()
    return max(0.0, d["api_usd_budget"] - d["api_usd_spent"])
