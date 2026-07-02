"""Tavily search + extract client.

Tavily is a search API built for LLM pipelines. Unlike our dead DuckDuckGo
scraper (403-blocked) and LLM-guessed URLs (often wrong/paywalled), Tavily
returns REAL, existing URLs together with the page's extracted text content —
so we get both URL existence and fetchable content in one call, sidestepping
the bot-blocking that breaks direct fetches.

Config: set TAVILY_API_KEY in the environment (.env). When absent, available()
returns False and callers fall back to the LLM-guess + direct-fetch path.
"""
from __future__ import annotations

import logging
import os

import httpx

logger = logging.getLogger(__name__)

_SEARCH_URL = "https://api.tavily.com/search"
_EXTRACT_URL = "https://api.tavily.com/extract"
_TIMEOUT = 30.0


def api_key() -> str:
    return os.environ.get("TAVILY_API_KEY", "")


def available() -> bool:
    return bool(api_key())


async def search(
    query: str,
    *,
    max_results: int = 10,
    include_raw: bool = True,
    include_domains: list[str] | None = None,
) -> list[dict]:
    """Search Tavily and return result dicts.

    Each result has: ``title``, ``url``, ``content`` (relevant snippet), and
    ``raw_content`` (full extracted page text, when include_raw and available),
    plus a relevance ``score``. ``include_domains`` restricts results to those
    hosts (e.g. ["youtube.com"]). Returns [] on any API failure.
    """
    payload = {
        "api_key": api_key(),
        "query": query,
        "max_results": max_results,
        "include_raw_content": include_raw,
        "search_depth": "advanced",
    }
    if include_domains:
        payload["include_domains"] = include_domains
    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            resp = await client.post(_SEARCH_URL, json=payload)
        resp.raise_for_status()
        return resp.json().get("results", []) or []
    except (httpx.HTTPError, ValueError, KeyError) as exc:
        logger.warning("tavily: search failed for %r: %s", query[:80], exc)
        return []


def _first_raw_content(data: dict) -> str:
    results = data.get("results", []) or []
    if results:
        return results[0].get("raw_content") or ""
    return ""


async def extract(url: str) -> str:
    """Return the extracted page text for a single URL via Tavily, or "".

    Used to fetch content for verification when a direct fetch would be
    bot-blocked. Returns "" on any failure so callers degrade gracefully.
    """
    payload = {"api_key": api_key(), "urls": [url]}
    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            resp = await client.post(_EXTRACT_URL, json=payload)
        resp.raise_for_status()
        return _first_raw_content(resp.json())
    except (httpx.HTTPError, ValueError, KeyError) as exc:
        logger.warning("tavily: extract failed for %s: %s", url, exc)
        return ""


def extract_sync(url: str) -> str:
    """Blocking variant of :func:`extract` for sync call sites (the verifier)."""
    payload = {"api_key": api_key(), "urls": [url]}
    try:
        with httpx.Client(timeout=_TIMEOUT) as client:
            resp = client.post(_EXTRACT_URL, json=payload)
        resp.raise_for_status()
        return _first_raw_content(resp.json())
    except (httpx.HTTPError, ValueError, KeyError) as exc:
        logger.warning("tavily: extract failed for %s: %s", url, exc)
        return ""
