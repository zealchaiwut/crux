"""Tests for issue #43: [follow-up] Extract UI state constants.

AC coverage (static analysis of app/static/js/cases.js):
  AC1 – STATES constant object is defined with IDLE, COPIED, LOADING, and ERROR keys.
  AC2 – All string literal state comparisons and assignments use STATES.* references;
         no bare state strings remain outside the STATES constant definition.
  AC3 – The STATES constant is defined before its first use.
  AC4 – No remaining bare "error" state literals in state-setter or state-comparison
         expressions (the primary gap left after issues #35/#39).
"""
import re
import pathlib

CASES_JS = pathlib.Path(__file__).parent.parent / "app" / "static" / "js" / "cases.js"


def _src():
    return CASES_JS.read_text()


def _src_without_states_def():
    """Return cases.js with the STATES constant definition block stripped."""
    src = _src()
    return re.sub(r"const STATES\s*=\s*\{[^}]+\};?\n?", "", src, flags=re.DOTALL)


def _strip_comments(src):
    """Remove // … line comments so comment text does not count as literals."""
    return re.sub(r"//[^\n]*", "", src)


# ---------------------------------------------------------------------------
# AC1: STATES constant defined with all four required keys
# ---------------------------------------------------------------------------

def test_ac1_states_constant_exists():
    """AC1: const STATES = { … } is declared in cases.js."""
    assert re.search(r"\bconst\s+STATES\s*=\s*\{", _src()), \
        "STATES constant must be declared in cases.js"


def test_ac1_states_has_idle_key():
    """AC1: STATES has an IDLE key."""
    assert re.search(r"STATES\s*=\s*\{[^}]*\bIDLE\s*:", _src(), re.DOTALL), \
        "STATES must contain IDLE"


def test_ac1_states_has_copied_key():
    """AC1: STATES has a COPIED key."""
    assert re.search(r"STATES\s*=\s*\{[^}]*\bCOPIED\s*:", _src(), re.DOTALL), \
        "STATES must contain COPIED"


def test_ac1_states_has_loading_key():
    """AC1: STATES has a LOADING key."""
    assert re.search(r"STATES\s*=\s*\{[^}]*\bLOADING\s*:", _src(), re.DOTALL), \
        "STATES must contain LOADING"


def test_ac1_states_has_error_key():
    """AC1: STATES has an ERROR key."""
    assert re.search(r"STATES\s*=\s*\{[^}]*\bERROR\s*:", _src(), re.DOTALL), \
        "STATES must contain ERROR"


# ---------------------------------------------------------------------------
# AC2/AC4: No bare "error" state literals remain in setter/comparison positions
# ---------------------------------------------------------------------------

# Patterns that indicate a state setter receiving a bare "error" string.
_SETTER_ERROR_RE = re.compile(
    r'\bset[A-Z]\w*\s*\(\s*"error"\s*\)',
)

# Patterns that indicate a state comparison against a bare "error" string.
_CMP_ERROR_RE = re.compile(
    r'\b\w+\s*===?\s*"error"',
)

# Names whose "error" comparisons we intentionally exclude (component prop
# discriminators, not state-machine values).
_EXCLUDED_VARS = {"type"}


def test_ac4_no_bare_error_in_setters():
    """AC4: No state-setter calls use bare "error" string literal."""
    src = _strip_comments(_src_without_states_def())
    matches = _SETTER_ERROR_RE.findall(src)
    assert not matches, (
        f'Found {len(matches)} bare "error" literal(s) passed to state setter(s) — '
        f"replace with STATES.ERROR: {matches}"
    )


def test_ac4_no_bare_error_in_state_comparisons():
    """AC4: No state-tracking variable comparisons use bare "error" literal."""
    src = _strip_comments(_src_without_states_def())
    raw_matches = _CMP_ERROR_RE.findall(src)
    # Filter out excluded component-prop variables (e.g. `type === "error"`)
    filtered = [
        m for m in raw_matches
        if not any(re.match(rf'\b{v}\b', m.strip()) for v in _EXCLUDED_VARS)
    ]
    assert not filtered, (
        f'Found {len(filtered)} bare "error" comparison(s) with state variable(s) — '
        f"replace with STATES.ERROR: {filtered}"
    )


# ---------------------------------------------------------------------------
# AC3: STATES defined before its first use
# ---------------------------------------------------------------------------

def test_ac3_states_defined_before_first_use():
    """AC3: const STATES declaration appears before any STATES.* reference."""
    src = _src()
    def_match = re.search(r"\bconst\s+STATES\s*=\s*\{", src)
    assert def_match, "STATES constant must be declared"

    # Find first STATES.* usage (excluding the definition block itself)
    src_after_def_end = src[def_match.end():]
    # Skip to the closing brace of the STATES definition
    brace_end = src_after_def_end.index("}")
    src_after_def = src_after_def_end[brace_end + 1:]

    first_use = re.search(r"\bSTATES\.", src_after_def)
    # Also check nothing before the definition uses STATES.*
    src_before_def = src[: def_match.start()]
    early_use = re.search(r"\bSTATES\.", src_before_def)
    assert not early_use, (
        f"STATES.* referenced before its const declaration at offset "
        f"{early_use.start() if early_use else '?'}"
    )
    assert first_use, "STATES.* must be used somewhere after its definition"


# ---------------------------------------------------------------------------
# AC2: No bare "idle", "copied", "loading" remain (regression guard)
# ---------------------------------------------------------------------------

def test_ac2_no_bare_idle_literals():
    """AC2: No bare \"idle\" string literals remain outside the STATES definition."""
    src = _strip_comments(_src_without_states_def())
    matches = re.findall(r'"idle"', src)
    assert not matches, (
        f"Found {len(matches)} bare \"idle\" literal(s) — replace with STATES.IDLE"
    )


def test_ac2_no_bare_copied_literals():
    """AC2: No bare \"copied\" string literals remain outside the STATES definition."""
    src = _strip_comments(_src_without_states_def())
    matches = re.findall(r'"copied"', src)
    assert not matches, (
        f"Found {len(matches)} bare \"copied\" literal(s) — replace with STATES.COPIED"
    )


def test_ac2_no_bare_loading_literals():
    """AC2: No bare \"loading\" string literals remain outside the STATES definition."""
    src = _strip_comments(_src_without_states_def())
    matches = re.findall(r'"loading"', src)
    assert not matches, (
        f"Found {len(matches)} bare \"loading\" literal(s) — replace with STATES.LOADING"
    )
