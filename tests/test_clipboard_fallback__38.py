"""Tests for issue #38: [follow-up] Replace deprecated navigator.clipboard fallback.

AC coverage (static analysis of cases.js):
  AC1 – (updated by #42) document.execCommand fallback is removed entirely.
  AC2 – (updated by #42) Fallback path now shows an error; execCommand path gone.
  AC3 – When copy fails, a user-visible error message is displayed.
  AC4 – The primary navigator.clipboard.writeText() path is unchanged.
  AC5 – No new dependencies; the fix is pure vanilla JS.

Note: issue #42 completed the clean-up that #38 began — execCommand has been
removed entirely. Tests for AC1 and AC2 that previously verified execCommand's
presence have been updated to verify its absence.
"""
import re
import pathlib

CASES_JS = pathlib.Path(__file__).parent.parent / "app" / "static" / "js" / "cases.js"


def _src():
    return CASES_JS.read_text()


def _handleCopy_block(src):
    """Extract the handleCopy function body from cases.js."""
    match = re.search(
        r'async function handleCopy\(\)\s*\{(.+?)(?=\n  (?:async function|function|const |return |}\s*$))',
        src,
        re.DOTALL,
    )
    assert match, "handleCopy function not found in cases.js"
    return match.group(0)


def _outer_catch_body(block):
    """Return the body of the outer catch block (the clipboard fallback path)."""
    catch_match = re.search(r'\}\s*catch\s*\([^)]*\)\s*\{(.+)', block, re.DOTALL)
    assert catch_match, "No outer catch block found in handleCopy"
    return catch_match.group(1)


# ---------------------------------------------------------------------------
# AC1: execCommand fallback is removed (updated by issue #42)
# ---------------------------------------------------------------------------

def test_ac1_no_execCommand_in_catch():
    """AC1 (updated by #42): document.execCommand is NOT in the catch path.

    Issue #42 removed the deprecated fallback entirely; the catch now shows
    a user-visible error message directly.
    """
    src = _src()
    block = _handleCopy_block(src)
    catch_body = _outer_catch_body(block)
    assert "execCommand" not in catch_body, \
        "document.execCommand must NOT appear in the catch body (removed per #42)"


def test_ac1_catch_is_flat_no_nested_try():
    """AC1 (updated by #42): The catch body has no nested try block.

    The inner try/catch that wrapped execCommand was removed; the catch is now
    a simple single-statement error handler.
    """
    src = _src()
    block = _handleCopy_block(src)
    catch_body = _outer_catch_body(block)
    assert "try" not in catch_body, \
        "catch body must not contain a nested try block (execCommand complexity gone per #42)"


# ---------------------------------------------------------------------------
# AC2: Failure path shows error (no execCommand success path exists any more)
# ---------------------------------------------------------------------------

def test_ac2_catch_shows_error_not_success():
    """AC2 (updated by #42): The catch body calls setCopyError, not setCopyState.

    There is no longer a fallback success path; the only catch behaviour is
    to surface a user-visible error message.
    """
    src = _src()
    block = _handleCopy_block(src)
    catch_body = _outer_catch_body(block)
    assert "setCopyError" in catch_body, \
        "catch body must call setCopyError to inform the user that copy failed"
    # Success state must NOT be set in the catch
    assert "setCopyState(STATES.COPIED)" not in catch_body, \
        "setCopyState(STATES.COPIED) must not appear in the catch body (no fallback success path)"


def test_ac2_no_setTimeout_in_catch():
    """AC2 (updated by #42): No setTimeout in the catch body (success-path reset removed)."""
    src = _src()
    block = _handleCopy_block(src)
    catch_body = _outer_catch_body(block)
    assert "setTimeout" not in catch_body, \
        "catch body must not call setTimeout (fallback success path was removed per #42)"


# ---------------------------------------------------------------------------
# AC3: Copy failure → user-visible error message shown
# ---------------------------------------------------------------------------

def test_ac3_false_return_not_needed():
    """AC3 (updated by #42): No execCommand return-value check needed; catch is flat."""
    src = _src()
    block = _handleCopy_block(src)
    catch_body = _outer_catch_body(block)
    # No `ok` variable or false-return guard since execCommand is gone
    assert "if (!ok)" not in catch_body, \
        "execCommand false-return guard must be absent (execCommand removed per #42)"


def test_ac3_error_message_shown_when_catch_fires():
    """AC3: setCopyError is called in the catch to display an error message."""
    src = _src()
    block = _handleCopy_block(src)
    catch_body = _outer_catch_body(block)
    assert "setCopyError" in catch_body, \
        "setCopyError must be called in the catch to surface the failure to the user"


def test_ac3_error_message_text():
    """AC3: The error message text indicates copy failure and instructs manual copy."""
    src = _src()
    assert re.search(
        r'[Cc]opy\s+failed',
        src,
    ), "Error message must include 'Copy failed' (or similar)"
    assert re.search(
        r'[Mm]anually|manually',
        src,
    ), "Error message must mention copying manually"


def test_ac3_error_rendered_to_user():
    """AC3: copyError is conditionally rendered so the user sees it."""
    src = _src()
    assert re.search(r'copyError\s*&&', src) or re.search(r'\{copyError\}', src), \
        "copyError must be rendered in JSX for the user to see it"


# ---------------------------------------------------------------------------
# AC4: Primary navigator.clipboard.writeText() path is unchanged
# ---------------------------------------------------------------------------

def test_ac4_primary_clipboard_path_present():
    """AC4: navigator.clipboard.writeText is still called as the primary path."""
    src = _src()
    block = _handleCopy_block(src)
    assert "navigator.clipboard.writeText" in block, \
        "Primary navigator.clipboard.writeText path must be present"


def test_ac4_primary_path_is_only_attempt():
    """AC4 (updated by #42): navigator.clipboard.writeText is the ONLY copy attempt.

    execCommand was removed by #42 so there is no fallback path to order
    against; this test verifies writeText is present and execCommand is absent.
    """
    src = _src()
    block = _handleCopy_block(src)
    assert "navigator.clipboard.writeText" in block, \
        "navigator.clipboard.writeText must be present as the sole copy method"
    assert "execCommand" not in block, \
        "execCommand must be absent — removed per #42, writeText is now the only copy path"


def test_ac4_primary_success_does_not_call_execCommand():
    """AC4: The success path (inside the try) does not call execCommand."""
    src = _src()
    block = _handleCopy_block(src)
    try_pos = block.find("try")
    first_catch = re.search(r'\}\s*catch', block).start()
    try_body = block[try_pos:first_catch]
    assert "execCommand" not in try_body, \
        "execCommand must not appear in the primary try block"


# ---------------------------------------------------------------------------
# AC5: No new external dependencies introduced
# ---------------------------------------------------------------------------

def test_ac5_no_import_statements_in_handleCopy():
    """AC5: handleCopy uses no import or require calls (pure vanilla JS)."""
    src = _src()
    block = _handleCopy_block(src)
    assert "import " not in block, "handleCopy must not use ES module imports"
    assert "require(" not in block, "handleCopy must not use require() calls"


def test_ac5_no_external_library_calls():
    """AC5: handleCopy does not call any third-party library APIs for clipboard."""
    src = _src()
    block = _handleCopy_block(src)
    forbidden = ["clipboard.js", "clipboardy", "copy-to-clipboard"]
    for lib in forbidden:
        assert lib not in block, f"handleCopy must not use external library: {lib}"
