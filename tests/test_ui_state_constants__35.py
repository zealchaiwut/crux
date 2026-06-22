"""Tests for issue #35: Extract UI state constants to avoid string literals.

AC coverage (static analysis of app/static/js/cases.js):
  AC1 – STATES constant object is defined with IDLE, COPIED, LOADING, ERROR keys.
  AC2 – All assignments to copyState use STATES.* references (no bare string literals).
  AC3 – All assignments to regenState use STATES.* references (no bare string literals).
  AC4 – All comparisons against copyState/regenState use STATES.* references.
  AC5 – No bare string literals 'idle', 'copied', 'loading', 'error' remain in
         state-tracking logic around copyState and regenState.
"""
import re
import pathlib

CASES_JS = pathlib.Path(__file__).parent.parent / "app" / "static" / "js" / "cases.js"


def _src():
    return CASES_JS.read_text()


def _commander_spec_modal_block(src):
    """Extract the CommanderSpecModal function body from cases.js."""
    match = re.search(
        r'function CommanderSpecModal\s*\([^)]*\)\s*\{(.+?)(?=\nfunction [A-Z])',
        src,
        re.DOTALL,
    )
    assert match, "CommanderSpecModal function not found in cases.js"
    return match.group(0)


# ---------------------------------------------------------------------------
# AC1: STATES constant object is defined with all required keys
# ---------------------------------------------------------------------------

def test_ac1_states_constant_defined():
    """AC1: STATES constant is declared in cases.js."""
    src = _src()
    assert re.search(r'\bconst\s+STATES\s*=\s*\{', src), \
        "STATES constant must be declared in cases.js"


def test_ac1_states_idle_value():
    """AC1: STATES.IDLE has value 'idle'."""
    src = _src()
    assert re.search(r"STATES\s*=\s*\{[^}]*IDLE\s*:\s*'idle'", src, re.DOTALL), \
        "STATES must have IDLE: 'idle'"


def test_ac1_states_copied_value():
    """AC1: STATES.COPIED has value 'copied'."""
    src = _src()
    assert re.search(r"STATES\s*=\s*\{[^}]*COPIED\s*:\s*'copied'", src, re.DOTALL), \
        "STATES must have COPIED: 'copied'"


def test_ac1_states_loading_value():
    """AC1: STATES.LOADING has value 'loading'."""
    src = _src()
    assert re.search(r"STATES\s*=\s*\{[^}]*LOADING\s*:\s*'loading'", src, re.DOTALL), \
        "STATES must have LOADING: 'loading'"


def test_ac1_states_error_value():
    """AC1: STATES.ERROR has value 'error'."""
    src = _src()
    assert re.search(r"STATES\s*=\s*\{[^}]*ERROR\s*:\s*'error'", src, re.DOTALL), \
        "STATES must have ERROR: 'error'"


# ---------------------------------------------------------------------------
# AC2: All assignments to copyState use STATES.* references
# ---------------------------------------------------------------------------

def test_ac2_copystate_initial_uses_states():
    """AC2: copyState useState initialiser uses STATES.IDLE not 'idle'."""
    src = _src()
    block = _commander_spec_modal_block(src)
    # Must NOT have useState('idle') for copyState
    assert not re.search(r"copyState.*useState\s*\(\s*'idle'\s*\)", block), \
        "copyState useState must use STATES.IDLE not 'idle'"
    assert re.search(r"useState\s*\(\s*STATES\.IDLE\s*\)", block), \
        "copyState useState must initialise with STATES.IDLE"


def test_ac2_setcopystate_no_bare_literals():
    """AC2: No setCopyState calls use bare string literals."""
    src = _src()
    block = _commander_spec_modal_block(src)
    # Find all setCopyState(...) calls and check none use bare string literals
    bare = re.findall(r"setCopyState\s*\(\s*'(idle|copied|loading|error)'\s*\)", block)
    assert not bare, \
        f"setCopyState must use STATES.* references, found bare literals: {bare}"


def test_ac2_setcopystate_copied_uses_states():
    """AC2: setCopyState for 'copied' state uses STATES.COPIED."""
    src = _src()
    block = _commander_spec_modal_block(src)
    assert re.search(r"setCopyState\s*\(\s*STATES\.COPIED\s*\)", block), \
        "setCopyState must use STATES.COPIED not 'copied'"


def test_ac2_setcopystate_idle_uses_states():
    """AC2: setCopyState for reset uses STATES.IDLE."""
    src = _src()
    block = _commander_spec_modal_block(src)
    assert re.search(r"setCopyState\s*\(\s*STATES\.IDLE\s*\)", block), \
        "setCopyState reset must use STATES.IDLE not 'idle'"


# ---------------------------------------------------------------------------
# AC3: All assignments to regenState use STATES.* references
# ---------------------------------------------------------------------------

def test_ac3_regenstate_initial_uses_states():
    """AC3: regenState useState initialiser uses STATES.IDLE not 'idle'."""
    src = _src()
    block = _commander_spec_modal_block(src)
    assert not re.search(r"regenState.*useState\s*\(\s*'idle'\s*\)", block), \
        "regenState useState must use STATES.IDLE not 'idle'"


def test_ac3_setregenstate_no_bare_literals():
    """AC3: No setRegenState calls use bare string literals."""
    src = _src()
    block = _commander_spec_modal_block(src)
    bare = re.findall(r"setRegenState\s*\(\s*'(idle|copied|loading|error)'\s*\)", block)
    assert not bare, \
        f"setRegenState must use STATES.* references, found bare literals: {bare}"


def test_ac3_setregenstate_loading_uses_states():
    """AC3: setRegenState for loading uses STATES.LOADING."""
    src = _src()
    block = _commander_spec_modal_block(src)
    assert re.search(r"setRegenState\s*\(\s*STATES\.LOADING\s*\)", block), \
        "setRegenState must use STATES.LOADING not 'loading'"


# ---------------------------------------------------------------------------
# AC4: All comparisons use STATES.* references
# ---------------------------------------------------------------------------

def test_ac4_regenstate_comparison_uses_states():
    """AC4: Comparisons against regenState use STATES.* not bare strings."""
    src = _src()
    block = _commander_spec_modal_block(src)
    bare_comparisons = re.findall(
        r"regenState\s*===?\s*'(idle|copied|loading|error)'",
        block,
    )
    assert not bare_comparisons, \
        f"regenState comparisons must use STATES.*, found bare: {bare_comparisons}"


def test_ac4_copystate_comparison_uses_states():
    """AC4: Comparisons against copyState use STATES.* not bare strings."""
    src = _src()
    block = _commander_spec_modal_block(src)
    bare_comparisons = re.findall(
        r"copyState\s*===?\s*'(idle|copied|loading|error)'",
        block,
    )
    assert not bare_comparisons, \
        f"copyState comparisons must use STATES.*, found bare: {bare_comparisons}"


# ---------------------------------------------------------------------------
# AC5: No bare state string literals remain in the state-tracking logic
# ---------------------------------------------------------------------------

def test_ac5_no_bare_state_literals_in_modal():
    """AC5: No bare 'idle'/'copied'/'loading'/'error' literals near copyState/regenState."""
    src = _src()
    block = _commander_spec_modal_block(src)
    # We're specifically looking for literals assigned to or compared with copyState/regenState.
    # These are: setCopyState('...'), setRegenState('...'), copyState === '...', regenState === '...'
    pattern = re.compile(
        r"(?:(?:setCopyState|setRegenState)\s*\(\s*'(?:idle|copied|loading|error)'\s*\))"
        r"|(?:(?:copyState|regenState)\s*===?\s*'(?:idle|copied|loading|error)')"
    )
    matches = pattern.findall(block)
    assert not matches, \
        f"Found bare state string literals in CommanderSpecModal: {matches}"
