"""Tests for issue #38: [follow-up] Replace deprecated navigator.clipboard fallback.

AC coverage (static analysis of cases.js):
  AC1 – document.execCommand('copy') fallback is wrapped in a try/catch block.
  AC2 – When the fallback succeeds, existing copy success behavior (visual feedback) is preserved.
  AC3 – When the fallback throws or returns false, a user-visible error message is displayed.
  AC4 – The primary navigator.clipboard.writeText() path is unchanged.
  AC5 – No new dependencies; the fix is pure vanilla JS.
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
# AC1: document.execCommand fallback is wrapped in try/catch
# ---------------------------------------------------------------------------

def test_ac1_execCommand_is_wrapped_in_try():
    """AC1: document.execCommand('copy') appears inside a try block in the fallback path."""
    src = _src()
    block = _handleCopy_block(src)
    catch_body = _outer_catch_body(block)
    inner_try_pos = catch_body.find("try")
    exec_pos = catch_body.find("execCommand")
    assert inner_try_pos != -1, "No inner try block found in the fallback catch body"
    assert exec_pos != -1, "document.execCommand not found in the fallback catch body"
    assert inner_try_pos < exec_pos, \
        "document.execCommand('copy') must be inside the inner try block"


def test_ac1_execCommand_try_has_catch():
    """AC1: The inner try around execCommand has a catch clause."""
    src = _src()
    block = _handleCopy_block(src)
    catch_body = _outer_catch_body(block)
    assert re.search(r'execCommand.+?\}\s*catch\s*\(', catch_body, re.DOTALL), \
        "document.execCommand fallback must have its own catch block"


# ---------------------------------------------------------------------------
# AC2: When fallback succeeds, existing copy success behavior is preserved
# ---------------------------------------------------------------------------

def test_ac2_success_sets_copied_state_in_fallback():
    """AC2: setCopyState transitions to copied when execCommand succeeds."""
    src = _src()
    block = _handleCopy_block(src)
    catch_body = _outer_catch_body(block)
    # The inner try body (before the inner catch) must set the copied state
    inner_try_match = re.search(r'\btry\s*\{(.+?)\}\s*catch\s*\(', catch_body, re.DOTALL)
    assert inner_try_match, "Inner try block not found in fallback"
    inner_try_body = inner_try_match.group(1)
    sets_copied = (
        "setCopyState('copied')" in inner_try_body
        or 'setCopyState("copied")' in inner_try_body
        or "setCopyState(STATES.COPIED)" in inner_try_body
    )
    assert sets_copied, \
        "setCopyState(STATES.COPIED) must be called in the inner try (fallback success path)"


def test_ac2_success_resets_after_timeout_in_fallback():
    """AC2: setTimeout(...IDLE) is called on the fallback success path."""
    src = _src()
    block = _handleCopy_block(src)
    catch_body = _outer_catch_body(block)
    inner_try_match = re.search(r'\btry\s*\{(.+?)\}\s*catch\s*\(', catch_body, re.DOTALL)
    assert inner_try_match, "Inner try block not found in fallback"
    inner_try_body = inner_try_match.group(1)
    assert "setTimeout" in inner_try_body, \
        "setTimeout must be called on the fallback success path to reset state"


# ---------------------------------------------------------------------------
# AC3: When fallback throws or returns false, user-visible error is shown
# ---------------------------------------------------------------------------

def test_ac3_false_return_throws_or_is_handled():
    """AC3: A false return from execCommand is treated as a failure (throws or branched)."""
    src = _src()
    block = _handleCopy_block(src)
    catch_body = _outer_catch_body(block)
    inner_try_match = re.search(r'\btry\s*\{(.+?)\}\s*catch\s*\(', catch_body, re.DOTALL)
    assert inner_try_match, "Inner try block not found in fallback"
    inner_try_body = inner_try_match.group(1)
    # Either an if/throw when ok is false, or the return value is checked
    handles_false = (
        "if (!ok)" in inner_try_body
        or re.search(r'if\s*\(\s*!\s*ok\s*\)', inner_try_body)
        or re.search(r'ok\s*===\s*false', inner_try_body)
    )
    assert handles_false, \
        "execCommand returning false must be treated as a failure (e.g. `if (!ok) throw ...`)"


def test_ac3_error_message_shown_when_inner_catch_fires():
    """AC3: setCopyError is called in the inner catch to display an error message."""
    src = _src()
    block = _handleCopy_block(src)
    catch_body = _outer_catch_body(block)
    inner_catch_match = re.search(
        r'execCommand.*?\}\s*catch\s*\([^)]*\)\s*\{([^}]+)\}',
        catch_body,
        re.DOTALL,
    )
    assert inner_catch_match, "Inner catch block (after execCommand) not found"
    inner_catch_body = inner_catch_match.group(1)
    assert "setCopyError" in inner_catch_body, \
        "setCopyError must be called in the inner catch to surface the failure to the user"


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


def test_ac4_primary_path_is_first_attempt():
    """AC4: navigator.clipboard.writeText is attempted before the execCommand fallback."""
    src = _src()
    block = _handleCopy_block(src)
    clip_pos = block.find("navigator.clipboard.writeText")
    exec_pos = block.find("execCommand")
    assert clip_pos < exec_pos, \
        "navigator.clipboard.writeText must appear before execCommand (primary-then-fallback order)"


def test_ac4_primary_success_does_not_call_execCommand():
    """AC4: The success path (inside the try) does not call execCommand."""
    src = _src()
    block = _handleCopy_block(src)
    try_pos = block.find("try")
    first_catch = re.search(r'\}\s*catch', block).start()
    try_body = block[try_pos:first_catch]
    assert "execCommand" not in try_body, \
        "execCommand must not appear in the primary try block — it belongs only in the fallback"


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
