"""Tests for issue #42: [follow-up] Replace deprecated clipboard fallback.

Sprint-4 review of #27 noted that the fallback in handleCopy() still uses the
deprecated document.execCommand('copy').  Issues #34 and #38 added try/catch
wrappers; #42 completes the clean-up by removing execCommand entirely in favour
of a graceful error message.

AC coverage (static analysis of cases.js):
  AC1 – document.execCommand('copy') fallback is removed (not kept in any form).
  AC2 – The primary copy path uses navigator.clipboard.writeText().
  AC3 – If navigator.clipboard.writeText() rejects, the catch handles it
         gracefully — no uncaught / re-thrown exception.
  AC4 – If copy fails, a user-visible error message is set via setCopyError.
  AC5 – No document.execCommand calls remain in cases.js for clipboard ops.
"""
import re
import pathlib

CASES_JS = pathlib.Path(__file__).parent.parent / "app" / "static" / "js" / "cases.js"


def _src():
    return CASES_JS.read_text()


def _handleCopy_block(src):
    """Extract the handleCopy function body from cases.js."""
    match = re.search(
        r"async function handleCopy\(\)\s*\{(.+?)(?=\n  (?:async function|function|const |return |}\s*$))",
        src,
        re.DOTALL,
    )
    assert match, "handleCopy function not found in cases.js"
    return match.group(0)


def _outer_catch_body(block):
    """Return the body of the first catch clause in handleCopy."""
    m = re.search(r"\}\s*catch\s*\([^)]*\)\s*\{(.+)", block, re.DOTALL)
    assert m, "No catch block found in handleCopy"
    return m.group(1)


# ---------------------------------------------------------------------------
# AC1 + AC5: document.execCommand removed from clipboard operations
# ---------------------------------------------------------------------------


def test_ac1_no_execCommand_in_handleCopy():
    """AC1: handleCopy no longer calls document.execCommand."""
    src = _src()
    block = _handleCopy_block(src)
    assert "execCommand" not in block, (
        "handleCopy must not call document.execCommand (deprecated fallback removed per AC1)"
    )


def test_ac5_no_execCommand_anywhere_in_cases_js():
    """AC5: No document.execCommand calls remain in cases.js for clipboard operations."""
    src = _src()
    assert "execCommand" not in src, (
        "document.execCommand must not appear anywhere in cases.js (AC5)"
    )


# ---------------------------------------------------------------------------
# AC2: primary copy path uses navigator.clipboard.writeText()
# ---------------------------------------------------------------------------


def test_ac2_primary_path_uses_writeText():
    """AC2: navigator.clipboard.writeText is still the primary copy path."""
    src = _src()
    block = _handleCopy_block(src)
    assert "navigator.clipboard.writeText" in block, (
        "handleCopy must call navigator.clipboard.writeText as the primary path (AC2)"
    )


def test_ac2_writeText_inside_try_block():
    """AC2: navigator.clipboard.writeText is wrapped in a try block."""
    src = _src()
    block = _handleCopy_block(src)
    try_pos = block.find("try")
    clip_pos = block.find("navigator.clipboard.writeText")
    assert try_pos != -1, "handleCopy must have a try block"
    assert try_pos < clip_pos, (
        "navigator.clipboard.writeText must be inside the try block (AC2)"
    )


def test_ac2_success_sets_copied_state():
    """AC2: setCopyState transitions to COPIED when writeText succeeds."""
    src = _src()
    block = _handleCopy_block(src)
    try_pos = block.find("try")
    first_catch_pos = re.search(r"\}\s*catch", block).start()
    success_path = block[try_pos:first_catch_pos]
    sets_copied = (
        "setCopyState('copied')" in success_path
        or 'setCopyState("copied")' in success_path
        or "setCopyState(STATES.COPIED)" in success_path
    )
    assert sets_copied, (
        "setCopyState(STATES.COPIED) must be called on the success path (AC2)"
    )


# ---------------------------------------------------------------------------
# AC3: rejection of writeText is caught gracefully — no uncaught exception
# ---------------------------------------------------------------------------


def test_ac3_try_has_catch():
    """AC3: The try block around writeText has a catch clause."""
    src = _src()
    block = _handleCopy_block(src)
    assert re.search(r"\}\s*catch\s*\(", block), (
        "handleCopy must have a catch block to handle writeText rejection (AC3)"
    )


def test_ac3_catch_does_not_rethrow():
    """AC3: The catch block does not re-throw — the error is handled gracefully."""
    src = _src()
    block = _handleCopy_block(src)
    catch_body = _outer_catch_body(block)
    assert not re.search(r"\bthrow\b", catch_body), (
        "catch block must not re-throw the error; failure must be handled silently (AC3)"
    )


def test_ac3_no_nested_try_in_catch():
    """AC3: The catch body has no nested try/catch (execCommand complexity is gone)."""
    src = _src()
    block = _handleCopy_block(src)
    catch_body = _outer_catch_body(block)
    assert "try" not in catch_body, (
        "catch body must not contain a nested try block — execCommand complexity removed (AC3)"
    )


# ---------------------------------------------------------------------------
# AC4: if copy fails, user sees an error message
# ---------------------------------------------------------------------------


def test_ac4_setCopyError_called_in_catch():
    """AC4: setCopyError is called in the catch to surface the failure."""
    src = _src()
    block = _handleCopy_block(src)
    catch_body = _outer_catch_body(block)
    assert "setCopyError" in catch_body, (
        "setCopyError must be called in the catch block so the user sees the error (AC4)"
    )


def test_ac4_error_message_mentions_copy_failed():
    """AC4: The error message text indicates copy failure."""
    src = _src()
    assert re.search(r"[Cc]opy\s+failed", src), (
        "Error message must contain 'Copy failed' (or similar) (AC4)"
    )


def test_ac4_error_rendered_in_jsx():
    """AC4: copyError is conditionally rendered so the user sees it."""
    src = _src()
    assert re.search(r"copyError\s*&&", src) or re.search(r"\{copyError\}", src), (
        "copyError must be rendered in JSX so the user can see the error message (AC4)"
    )


def test_ac4_no_error_on_success_path():
    """AC4: setCopyError is not called on the success path."""
    src = _src()
    block = _handleCopy_block(src)
    try_pos = block.find("try")
    first_catch_pos = re.search(r"\}\s*catch", block).start()
    success_path = block[try_pos:first_catch_pos]
    assert "setCopyError" not in success_path, (
        "setCopyError must not be called on the success path (AC4)"
    )
