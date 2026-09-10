"""Tests for issue #183: Avoid stale-closure eslint-disable on SourceDetailModal keydown effect.

Context: The SourceDetailModal keydown effect uses an empty dependency array with
eslint-disable-next-line react-hooks/exhaustive-deps. The Escape handler closes over
the first-render handleClose (stale closure). Fix: hold the latest handleClose in a
ref so the bind-once listener always calls the up-to-date function.
"""
import pathlib
import re

CASES_JS = pathlib.Path(__file__).parent.parent / "app" / "static" / "js" / "cases.js"


def _src():
    return CASES_JS.read_text()


def _modal_block(src):
    """Extract the SourceDetailModal function body from cases.js."""
    m = re.search(
        r"function SourceDetailModal\(.+?\n\}(?=\n\n// )",
        src,
        re.DOTALL,
    )
    assert m, "SourceDetailModal function not found in cases.js"
    return m.group(0)


# ===========================================================================
# AC1: eslint-disable-next-line for react-hooks/exhaustive-deps is removed
# from the keydown useEffect.
# ===========================================================================

def test_eslint_disable_removed_from_keydown_effect():
    """AC1: The eslint-disable-next-line react-hooks/exhaustive-deps comment must be gone."""
    block = _modal_block(_src())
    assert "eslint-disable-next-line react-hooks/exhaustive-deps" not in block, (
        "SourceDetailModal must not use eslint-disable to suppress the stale-closure warning "
        "(issue #183 AC1)"
    )


# ===========================================================================
# AC2: Latest handleClose is held in a ref so the bind-once listener
# can read it without creating a stale closure.
# ===========================================================================

def test_handle_close_ref_exists():
    """AC2: A ref is used to hold the latest handleClose for the keydown listener."""
    block = _modal_block(_src())
    has_close_ref = (
        "handleCloseRef" in block
        or "closeRef" in block
        or ("useRef" in block and ".current" in block and "handleClose" in block)
    )
    assert has_close_ref, (
        "SourceDetailModal must store the latest handleClose in a React ref so the "
        "bind-once keydown listener avoids stale closure (issue #183 AC2)"
    )


def test_keydown_effect_reads_ref_current():
    """AC2: The onKey function inside the useEffect reads via .current, not the stale closure."""
    block = _modal_block(_src())
    # The onKey handler must dereference a ref (.current) to get handleClose
    has_ref_read = re.search(
        r"\w+Ref\.current\s*\(",
        block,
    )
    assert has_ref_read, (
        "The onKey handler in SourceDetailModal's useEffect must call handleClose via "
        "ref.current() to avoid stale closure (issue #183 AC2)"
    )


def test_keydown_effect_still_empty_deps():
    """AC2: The bind-once pattern is preserved — keydown useEffect still uses [] deps."""
    block = _modal_block(_src())
    # The effect that registers the keydown listener must still end with }, [])
    has_empty_deps = re.search(
        r"window\.addEventListener\(['\"]keydown['\"].*?\}\s*,\s*\[\]\s*\)",
        block,
        re.DOTALL,
    )
    assert has_empty_deps, (
        "The keydown listener useEffect must still use an empty dependency array [] "
        "— the ref pattern makes that safe (issue #183 AC2)"
    )
