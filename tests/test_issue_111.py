"""Tests for issue #111: Add error logging to silent catch blocks in cases.js.

AC coverage:
  AC1 – The catch block in handleOverride no longer silently swallows the exception;
         it calls console.warn with a message containing "Source override failed" and
         the caught error object.
  AC2 – The catch block in handleAccept no longer silently swallows the exception;
         it calls console.warn with a message containing "Accept status failed" and
         the caught error object.
  AC3 – No other logic in either catch block is altered (no new side effects, no
         re-throws, no UI changes) — the catch blocks contain only the console.warn call.
  AC4 – Both warn messages include the caught error as the second argument so the full
         stack trace is visible in browser DevTools.
"""
import pathlib
import re

import pytest

CASES_JS = pathlib.Path(__file__).parent.parent / "app" / "static" / "js" / "cases.js"


def _src() -> str:
    return CASES_JS.read_text()


def _extract_catch_block(src: str, func_name: str) -> str:
    """Extract the body of the catch block inside the named async function."""
    pattern = rf"async function {re.escape(func_name)}\b.+?catch\s*\(\w+\)\s*\{{([^}}]*)\}}"
    match = re.search(pattern, src, re.DOTALL)
    assert match, f"Could not find catch block in {func_name}"
    return match.group(1).strip()


# ---------------------------------------------------------------------------
# AC1 — handleOverride catch block logs "Source override failed"
# ---------------------------------------------------------------------------

def test_override_catch_warns_source_override_failed():
    """AC1: handleOverride's catch block calls console.warn with 'Source override failed'."""
    src = _src()
    body = _extract_catch_block(src, "handleOverride")
    assert "console.warn" in body, (
        "handleOverride catch block must call console.warn"
    )
    assert "Source override failed" in body, (
        "handleOverride warn message must contain 'Source override failed'"
    )


# ---------------------------------------------------------------------------
# AC2 — handleAccept catch block logs "Accept status failed"
# ---------------------------------------------------------------------------

def test_accept_catch_warns_accept_status_failed():
    """AC2: handleAccept's catch block calls console.warn with 'Accept status failed'."""
    src = _src()
    body = _extract_catch_block(src, "handleAccept")
    assert "console.warn" in body, (
        "handleAccept catch block must call console.warn"
    )
    assert "Accept status failed" in body, (
        "handleAccept warn message must contain 'Accept status failed'"
    )


# ---------------------------------------------------------------------------
# AC3 — No other logic added to either catch block
# ---------------------------------------------------------------------------

def test_override_catch_block_only_contains_warn():
    """AC3: handleOverride catch block contains only the console.warn call."""
    src = _src()
    body = _extract_catch_block(src, "handleOverride")
    # Strip the console.warn line and whitespace; nothing else should remain
    remaining = re.sub(r"console\.warn\([^)]+\)\s*;?", "", body).strip()
    assert remaining == "", (
        f"handleOverride catch block contains unexpected extra code: {remaining!r}"
    )


def test_accept_catch_block_only_contains_warn():
    """AC3: handleAccept catch block contains only the console.warn call."""
    src = _src()
    body = _extract_catch_block(src, "handleAccept")
    remaining = re.sub(r"console\.warn\([^)]+\)\s*;?", "", body).strip()
    assert remaining == "", (
        f"handleAccept catch block contains unexpected extra code: {remaining!r}"
    )


# ---------------------------------------------------------------------------
# AC4 — Caught error is passed as second argument to console.warn
# ---------------------------------------------------------------------------

def test_override_warn_includes_error_as_second_arg():
    """AC4: handleOverride console.warn passes the error object as second argument."""
    src = _src()
    body = _extract_catch_block(src, "handleOverride")
    # Matches: console.warn("...", e) where the second arg is an identifier (the caught var)
    assert re.search(r'console\.warn\(\s*["\'][^"\']+["\'],\s*\w+\s*\)', body), (
        "handleOverride console.warn must pass the caught error as a second argument"
    )


def test_accept_warn_includes_error_as_second_arg():
    """AC4: handleAccept console.warn passes the error object as second argument."""
    src = _src()
    body = _extract_catch_block(src, "handleAccept")
    assert re.search(r'console\.warn\(\s*["\'][^"\']+["\'],\s*\w+\s*\)', body), (
        "handleAccept console.warn must pass the caught error as a second argument"
    )


# ---------------------------------------------------------------------------
# Sanity — silent catch (_) {} patterns are gone for these two functions
# ---------------------------------------------------------------------------

def test_no_silent_catch_in_handle_override():
    """Regression: handleOverride must not use the silent catch (_) {} pattern."""
    src = _src()
    # Extract just the handleOverride function body
    func_match = re.search(
        r"async function handleOverride\b(.+?)(?=\n  async function|\n  (?:function|const|let|var)\s|\Z)",
        src,
        re.DOTALL,
    )
    assert func_match, "handleOverride function not found"
    func_body = func_match.group(1)
    assert not re.search(r"catch\s*\(_\)\s*\{\s*\}", func_body), (
        "handleOverride still uses silent catch (_) {} — error logging not added"
    )


def test_no_silent_catch_in_handle_accept():
    """Regression: handleAccept must not use the silent catch (_) {} pattern."""
    src = _src()
    func_match = re.search(
        r"async function handleAccept\b(.+?)(?=\n  async function|\n  (?:function|const|let|var)\s|\Z)",
        src,
        re.DOTALL,
    )
    assert func_match, "handleAccept function not found"
    func_body = func_match.group(1)
    assert not re.search(r"catch\s*\(_\)\s*\{\s*\}", func_body), (
        "handleAccept still uses silent catch (_) {} — error logging not added"
    )
