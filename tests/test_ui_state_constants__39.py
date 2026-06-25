"""Tests for issue #39: [follow-up] Extract UI state constants — no bare literals remain.

AC coverage (static analysis of app/static/js/cases.js):
  AC1 – STATES constant object is defined with at minimum IDLE, COPIED, and LOADING keys.
  AC2 – All string literal references to 'idle', 'copied', 'loading' used for UI state
         tracking are replaced with STATES.IDLE, STATES.COPIED, STATES.LOADING.
  AC3 – No raw string literals for these UI states remain anywhere in cases.js outside
         the STATES definition block itself.
"""
import re
import pathlib

CASES_JS = pathlib.Path(__file__).parent.parent / "app" / "static" / "js" / "cases.js"


def _src():
    return CASES_JS.read_text()


def _src_without_states_def():
    """Return cases.js with the STATES constant definition removed."""
    src = _src()
    return re.sub(r"const STATES\s*=\s*\{[^}]+\};?\n?", "", src, flags=re.DOTALL)


def _strip_line_comments(src):
    """Remove // … line comments so comment mentions don't count as literals."""
    return re.sub(r"//[^\n]*", "", src)


# ---------------------------------------------------------------------------
# AC1: STATES constant defined with required keys
# ---------------------------------------------------------------------------

def test_ac1_states_constant_defined():
    """AC1: const STATES = { … } exists in cases.js."""
    assert re.search(r"\bconst\s+STATES\s*=\s*\{", _src()), \
        "STATES constant must be declared in cases.js"


def test_ac1_states_has_idle_key():
    """AC1: STATES has an IDLE key."""
    assert re.search(r"STATES\s*=\s*\{[^}]*\bIDLE\s*:", _src(), re.DOTALL), \
        "STATES must contain an IDLE key"


def test_ac1_states_has_copied_key():
    """AC1: STATES has a COPIED key."""
    assert re.search(r"STATES\s*=\s*\{[^}]*\bCOPIED\s*:", _src(), re.DOTALL), \
        "STATES must contain a COPIED key"


def test_ac1_states_has_loading_key():
    """AC1: STATES has a LOADING key."""
    assert re.search(r"STATES\s*=\s*\{[^}]*\bLOADING\s*:", _src(), re.DOTALL), \
        "STATES must contain a LOADING key"


# ---------------------------------------------------------------------------
# AC2 / AC3: No bare 'idle', 'copied', 'loading' string literals remain
# ---------------------------------------------------------------------------

def test_ac3_no_bare_idle_literals():
    """AC3: No bare \"idle\" or 'idle' remain anywhere outside the STATES definition."""
    src = _strip_line_comments(_src_without_states_def())
    matches = re.findall(r"""["']idle["']""", src)
    assert not matches, \
        f"Found {len(matches)} bare 'idle' literal(s) outside STATES definition — " \
        f"replace with STATES.IDLE"


def test_ac3_no_bare_loading_literals():
    """AC3: No bare \"loading\" or 'loading' remain anywhere outside the STATES definition."""
    src = _strip_line_comments(_src_without_states_def())
    matches = re.findall(r"""["']loading["']""", src)
    assert not matches, \
        f"Found {len(matches)} bare 'loading' literal(s) outside STATES definition — " \
        f"replace with STATES.LOADING"


def test_ac3_no_bare_copied_literals():
    """AC3: No bare \"copied\" or 'copied' remain anywhere outside the STATES definition."""
    src = _strip_line_comments(_src_without_states_def())
    matches = re.findall(r"""["']copied["']""", src)
    assert not matches, \
        f"Found {len(matches)} bare 'copied' literal(s) outside STATES definition — " \
        f"replace with STATES.COPIED"
