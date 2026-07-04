"""Tests for issue #162: handleAccept sets accepted=true before API call succeeds.

AC coverage:
  AC1 – setAccepted(true) is called only after resp.ok is confirmed and _applyUpdate returns.
  AC2 – When id is falsy, handleAccept returns early without setting accepted=true.
  AC3 – When API returns !resp.ok, accepted is set to false (not left as true).
  AC4 – When a network error is thrown, catch block sets accepted=false.
  AC5 – No failure path leaves accepted=true (visual "Accepted" state not shown on error).
"""

import pathlib
import re

JS_DIR = pathlib.Path(__file__).parent.parent / "app" / "static" / "js"


def _read_combined_js():
    return "".join((JS_DIR / f).read_text() for f in sorted(JS_DIR.iterdir()) if f.suffix == ".js")


def _handle_accept_block(js: str, window: int = 600) -> str:
    """Return the JS source of the handleAccept function body."""
    idx = js.find("async function handleAccept(")
    assert idx != -1, "handleAccept function must exist in JS"
    return js[idx: idx + window]


# ---------------------------------------------------------------------------
# AC1: setAccepted(true) must appear AFTER resp.ok check, not before the fetch
# ---------------------------------------------------------------------------

def test_setAccepted_true_not_before_fetch():
    """AC1: setAccepted(true) must not appear before the fetch() call in handleAccept."""
    js = _read_combined_js()
    block = _handle_accept_block(js)
    fetch_idx = block.find("fetch(")
    assert fetch_idx != -1, "handleAccept must call fetch()"
    # Find the first setAccepted(true) occurrence
    accepted_true_idx = block.find("setAccepted(true)")
    assert accepted_true_idx != -1, "setAccepted(true) must appear in handleAccept"
    assert accepted_true_idx > fetch_idx, (
        "setAccepted(true) must appear AFTER fetch(), not before it — "
        f"found setAccepted(true) at offset {accepted_true_idx}, fetch at {fetch_idx}"
    )


def test_setAccepted_true_after_resp_ok_check():
    """AC1: setAccepted(true) must appear after the resp.ok guard in handleAccept."""
    js = _read_combined_js()
    block = _handle_accept_block(js)
    resp_ok_idx = block.find("resp.ok")
    assert resp_ok_idx != -1, "handleAccept must check resp.ok"
    accepted_true_idx = block.find("setAccepted(true)")
    assert accepted_true_idx != -1, "setAccepted(true) must appear in handleAccept"
    assert accepted_true_idx > resp_ok_idx, (
        "setAccepted(true) must come after the resp.ok check, not before it"
    )


def test_setAccepted_true_after_applyUpdate():
    """AC1: setAccepted(true) must appear after _applyUpdate(data) call in handleAccept."""
    js = _read_combined_js()
    block = _handle_accept_block(js)
    apply_idx = block.find("_applyUpdate(data)")
    assert apply_idx != -1, "handleAccept must call _applyUpdate(data)"
    accepted_true_idx = block.find("setAccepted(true)")
    assert accepted_true_idx != -1, "setAccepted(true) must appear in handleAccept"
    assert accepted_true_idx > apply_idx, (
        "setAccepted(true) must come after _applyUpdate(data) succeeds"
    )


# ---------------------------------------------------------------------------
# AC2: falsy id path — must not set accepted=true
# ---------------------------------------------------------------------------

def test_early_return_on_falsy_id_before_setAccepted_true():
    """AC2: The !id early-return guard must appear before setAccepted(true)."""
    js = _read_combined_js()
    block = _handle_accept_block(js)
    id_guard_idx = block.find("if (!id)")
    assert id_guard_idx != -1, "handleAccept must have an if (!id) guard"
    accepted_true_idx = block.find("setAccepted(true)")
    assert accepted_true_idx != -1, "setAccepted(true) must exist in handleAccept"
    assert id_guard_idx < accepted_true_idx, (
        "The if (!id) guard must come before setAccepted(true) so falsy-id path "
        "never sets accepted=true"
    )


# ---------------------------------------------------------------------------
# AC3: !resp.ok path — must set accepted=false (not just return)
# ---------------------------------------------------------------------------

def test_not_resp_ok_sets_accepted_false():
    """AC3: When !resp.ok, handleAccept must call setAccepted(false)."""
    js = _read_combined_js()
    block = _handle_accept_block(js)
    # Find the !resp.ok branch
    not_ok_idx = block.find("!resp.ok")
    assert not_ok_idx != -1, "handleAccept must check !resp.ok"
    # Look for setAccepted(false) anywhere after !resp.ok and before the next top-level statement
    after_not_ok = block[not_ok_idx:]
    assert "setAccepted(false)" in after_not_ok, (
        "handleAccept must call setAccepted(false) in the !resp.ok branch"
    )


def test_not_resp_ok_does_not_only_return():
    """AC3: The !resp.ok branch must not be a bare return — it must reset accepted state."""
    js = _read_combined_js()
    block = _handle_accept_block(js)
    not_ok_idx = block.find("!resp.ok")
    assert not_ok_idx != -1
    # Extract the branch — find the code between !resp.ok and the next newline/semicolon group
    branch_slice = block[not_ok_idx: not_ok_idx + 120]
    # The branch must NOT be just "if (!resp.ok) return;"
    is_bare_return = bool(re.search(r"!\s*resp\.ok\s*\)\s*return\s*;", branch_slice))
    assert not is_bare_return, (
        "!resp.ok branch must not be a bare 'return;' — it must call setAccepted(false)"
    )


# ---------------------------------------------------------------------------
# AC4: catch block — must set accepted=false on network error
# ---------------------------------------------------------------------------

def test_catch_block_sets_accepted_false():
    """AC4: The catch block in handleAccept must call setAccepted(false)."""
    js = _read_combined_js()
    block = _handle_accept_block(js)
    catch_idx = block.find("} catch")
    assert catch_idx != -1, "handleAccept must have a catch block"
    catch_slice = block[catch_idx:]
    assert "setAccepted(false)" in catch_slice, (
        "handleAccept catch block must call setAccepted(false) to reset UI on network error"
    )


def test_catch_block_does_not_only_log():
    """AC4: catch block must not only console.warn — it must also reset accepted state."""
    js = _read_combined_js()
    block = _handle_accept_block(js)
    catch_idx = block.find("} catch")
    assert catch_idx != -1
    catch_slice = block[catch_idx: catch_idx + 200]
    # Must have setAccepted(false), not just console.warn
    has_reset = "setAccepted(false)" in catch_slice
    has_warn = "console.warn" in catch_slice
    assert has_reset, (
        "catch block must call setAccepted(false), not just console.warn"
    )


# ---------------------------------------------------------------------------
# AC5: setAccepted(true) appears exactly once in handleAccept (success path only)
# ---------------------------------------------------------------------------

def test_setAccepted_true_appears_exactly_once_in_handleAccept():
    """AC5: setAccepted(true) must appear exactly once in handleAccept (success path only)."""
    js = _read_combined_js()
    block = _handle_accept_block(js)
    count = block.count("setAccepted(true)")
    assert count == 1, (
        f"setAccepted(true) must appear exactly once in handleAccept (on success path), "
        f"found {count} occurrences"
    )


def test_setAccepted_false_appears_in_handleAccept():
    """AC3+AC4: setAccepted(false) must appear at least twice (for !resp.ok and catch)."""
    js = _read_combined_js()
    block = _handle_accept_block(js)
    count = block.count("setAccepted(false)")
    assert count >= 2, (
        f"setAccepted(false) must appear in both the !resp.ok branch and the catch block, "
        f"found {count} occurrence(s)"
    )
