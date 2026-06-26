"""Tests for issue #34: Replace deprecated navigator.clipboard fallback.

AC coverage (static analysis of cases.js):
  AC1 – navigator.clipboard.writeText is wrapped in a try/catch that catches failures.
  AC2 – If writeText fails the catch falls back to document.execCommand('copy').
  AC3 – The document.execCommand fallback is itself wrapped in a try/catch.
  AC4 – If both methods fail, a user-visible error message is displayed.
  AC5 – If primary clipboard write succeeds, no error is shown and success state is set.
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


# ---------------------------------------------------------------------------
# AC1: navigator.clipboard.writeText wrapped in try/catch
# ---------------------------------------------------------------------------

def test_ac1_clipboard_writeText_wrapped_in_try():
    """AC1: navigator.clipboard.writeText is inside a try block."""
    src = _src()
    block = _handleCopy_block(src)
    assert "navigator.clipboard.writeText" in block, \
        "handleCopy must call navigator.clipboard.writeText"
    # try must appear before the clipboard call
    try_pos = block.find("try")
    clip_pos = block.find("navigator.clipboard.writeText")
    assert try_pos != -1 and try_pos < clip_pos, \
        "navigator.clipboard.writeText must be inside a try block"


def test_ac1_clipboard_try_has_catch():
    """AC1: The try block around clipboard.writeText has a catch clause."""
    src = _src()
    block = _handleCopy_block(src)
    assert re.search(r'\}\s*catch\s*\(', block), \
        "handleCopy must have a catch block to handle clipboard failures"


# ---------------------------------------------------------------------------
# AC2: catch handles failure gracefully — execCommand removed by issue #42
# ---------------------------------------------------------------------------

def test_ac2_no_execCommand_in_catch():
    """AC2 (updated by #42): document.execCommand is no longer in the catch path.

    Issue #42 removed the deprecated execCommand fallback entirely; the catch
    now shows a user-visible error message directly instead.
    """
    src = _src()
    block = _handleCopy_block(src)
    catch_match = re.search(r'\}\s*catch\s*\([^)]*\)\s*\{(.+)', block, re.DOTALL)
    assert catch_match, "No catch block found in handleCopy"
    catch_body = catch_match.group(1)
    assert "execCommand" not in catch_body, \
        "document.execCommand must NOT be in the catch block (removed per #42)"


# ---------------------------------------------------------------------------
# AC3: catch is a simple error handler — no nested try/catch
# ---------------------------------------------------------------------------

def test_ac3_no_nested_try_in_catch():
    """AC3 (updated by #42): The catch body is a flat error handler, no nested try.

    Issue #42 removed the inner try/catch that wrapped execCommand; the catch
    now directly calls setCopyError without any nested control flow.
    """
    src = _src()
    block = _handleCopy_block(src)
    catch_match = re.search(r'\}\s*catch\s*\([^)]*\)\s*\{(.+)', block, re.DOTALL)
    assert catch_match, "No outer catch block found in handleCopy"
    catch_body = catch_match.group(1)
    assert "try" not in catch_body, \
        "catch body must not contain a nested try block (execCommand complexity removed per #42)"


# ---------------------------------------------------------------------------
# AC4: Copy failure → user-visible error message shown
# ---------------------------------------------------------------------------

def test_ac4_error_state_variable_declared():
    """AC4: A copyError state variable is declared in CommanderSpecModal."""
    src = _src()
    # Expect something like: const [copyError, setCopyError] = React.useState('')
    assert re.search(
        r'const\s*\[\s*copyError\s*,\s*setCopyError\s*\]\s*=\s*React\.useState',
        src,
    ), "copyError state must be declared with React.useState"


def test_ac4_error_set_when_copy_fails():
    """AC4 (updated by #42): setCopyError is called in the catch when writeText fails."""
    src = _src()
    block = _handleCopy_block(src)
    catch_match = re.search(r'\}\s*catch\s*\([^)]*\)\s*\{(.+)', block, re.DOTALL)
    assert catch_match, "No catch block found in handleCopy"
    catch_body = catch_match.group(1)
    assert "setCopyError" in catch_body, \
        "setCopyError must be called in the catch to surface the error to the user"


def test_ac4_error_rendered_in_jsx():
    """AC4: copyError is rendered as a user-visible element in CommanderSpecModal JSX."""
    src = _src()
    # Look for copyError being conditionally rendered, e.g. {copyError && <p...>}
    assert re.search(r'copyError\s*&&', src) or re.search(r'\{copyError\}', src), \
        "copyError must be rendered in the JSX so the user sees the error message"


# ---------------------------------------------------------------------------
# AC5: Success path unchanged — setCopyState('copied') called on success
# ---------------------------------------------------------------------------

def test_ac5_success_sets_copied_state():
    """AC5: The copied state is set when clipboard write succeeds (literal or STATES.COPIED)."""
    src = _src()
    block = _handleCopy_block(src)
    sets_copied = (
        "setCopyState('copied')" in block
        or 'setCopyState("copied")' in block
        or "setCopyState(STATES.COPIED)" in block
    )
    assert sets_copied, \
        "setCopyState must transition to the copied state on successful copy"


def test_ac5_no_error_on_success_path():
    """AC5: setCopyError is not called on the success path (only on failure)."""
    src = _src()
    block = _handleCopy_block(src)
    # The success path is BEFORE any catch block
    try_pos = block.find("try")
    first_catch_pos = re.search(r'\}\s*catch', block).start()
    success_path = block[try_pos:first_catch_pos]
    # setCopyError must NOT appear in the success path
    assert "setCopyError" not in success_path, \
        "setCopyError must not be called on the success path"
