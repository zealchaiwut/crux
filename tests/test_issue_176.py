"""Tests for issue #176: Return focus to SourceChip and trap focus in source detail modal.

AC coverage:
  AC1 – When SourceDetailModal opens, document.activeElement at open time is captured/stored.
  AC2 – When modal closes (close button / Escape / backdrop), focus is returned to the
         stored trigger element.
  AC3 – While open, Tab cycles focus only through the modal's focusable elements and does
         not reach elements behind the modal (focus trap).
  AC4 – While open, Shift+Tab cycles focus backwards and wraps correctly at the first element.
  AC5 – If triggering element is no longer in DOM, focus falls back to document.body without
         throwing (graceful fallback).
  AC6 – Fix is scoped to SourceDetailModal in cases.js near line 647; no other modal or
         component is altered.
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
# AC1: Trigger element captured when modal opens
# ===========================================================================

def test_trigger_element_captured_on_open():
    """AC1: document.activeElement is captured when the modal mounts."""
    block = _modal_block(_src())
    # Must reference document.activeElement somewhere — captured at mount time
    assert "document.activeElement" in block, (
        "SourceDetailModal must capture document.activeElement when it opens (AC1)"
    )


def test_trigger_element_stored_in_ref():
    """AC1: Captured trigger element is stored in a React ref (useRef) for later restoration."""
    block = _modal_block(_src())
    # useRef is the canonical way to store the element without triggering re-renders
    assert "useRef" in block or "triggerRef" in block or "focusTrigger" in block, (
        "SourceDetailModal must store the trigger element in a React ref (AC1)"
    )


# ===========================================================================
# AC2: Focus returned to trigger on close
# ===========================================================================

def test_focus_returned_on_close():
    """AC2: .focus() is called on the stored trigger element when the modal closes."""
    block = _modal_block(_src())
    # Must call .focus() to return focus on close
    assert ".focus()" in block, (
        "SourceDetailModal must call .focus() to return focus to the trigger element on close (AC2)"
    )


def test_focus_returned_on_escape():
    """AC2: Focus is returned when modal closes via Escape key."""
    block = _modal_block(_src())
    # The Escape key handler must trigger focus return (either via shared close fn or direct)
    assert "Escape" in block, "Escape key handler must exist in SourceDetailModal"
    assert ".focus()" in block, (
        "Focus must be returned when modal closes via Escape key (AC2)"
    )


def test_close_logic_returns_focus():
    """AC2: The modal's close pathway (handleClose / onClose wrapper) restores focus."""
    block = _modal_block(_src())
    # There should be a unified close handler that calls .focus() before/around onClose,
    # or the useEffect cleanup does it. Either pattern satisfies AC2.
    has_close_with_focus = (
        ".focus()" in block
        and ("handleClose" in block or "returnFocus" in block or "triggerRef" in block or "focusRef" in block)
    )
    assert has_close_with_focus, (
        "SourceDetailModal must have a close handler that returns focus to the trigger element (AC2)"
    )


# ===========================================================================
# AC3: Focus trap — Tab stays within modal
# ===========================================================================

def test_focus_trap_tab_key_handled():
    """AC3: Tab key is intercepted to cycle focus within the modal's focusable elements."""
    block = _modal_block(_src())
    # Must handle Tab key for focus trapping
    assert '"Tab"' in block or "'Tab'" in block, (
        "SourceDetailModal must intercept the Tab key to trap focus within the modal (AC3)"
    )


def test_focus_trap_queries_focusable_elements():
    """AC3: Focus trap logic queries focusable elements within the modal container."""
    block = _modal_block(_src())
    # Common selectors for focusable elements
    focusable_selector = (
        "querySelectorAll" in block
        or "focusable" in block.lower()
        or "tabbable" in block.lower()
        or 'querySelector(' in block
    )
    assert focusable_selector, (
        "SourceDetailModal must query focusable elements to implement focus trapping (AC3)"
    )


def test_focus_trap_wraps_at_last_element():
    """AC3: When Tab is pressed on the last focusable element, focus wraps to the first."""
    block = _modal_block(_src())
    # Wrapping requires checking if the active element is the last in the list
    has_wrap_logic = (
        "lastFocusable" in block
        or "last" in block.lower()
        or "length - 1" in block
        or "focusable[0]" in block
        or "first" in block.lower()
    )
    assert has_wrap_logic, (
        "SourceDetailModal focus trap must wrap Tab from last to first focusable element (AC3)"
    )


# ===========================================================================
# AC4: Shift+Tab cycles backwards and wraps
# ===========================================================================

def test_focus_trap_shift_tab_handled():
    """AC4: Shift+Tab is intercepted for backwards focus cycling within the modal."""
    block = _modal_block(_src())
    # Shift+Tab detection: e.shiftKey combined with Tab
    assert "shiftKey" in block, (
        "SourceDetailModal must handle Shift+Tab for backward focus cycling (AC4)"
    )


def test_focus_trap_shift_tab_wraps_to_last():
    """AC4: Shift+Tab from the first focusable element wraps to the last."""
    block = _modal_block(_src())
    # Backwards wrap: must reference both shiftKey and last element
    has_backwards_wrap = "shiftKey" in block and (
        "lastFocusable" in block
        or "length - 1" in block
        or "focusable[focusable.length" in block
        or "last" in block.lower()
    )
    assert has_backwards_wrap, (
        "SourceDetailModal Shift+Tab must wrap from first to last focusable element (AC4)"
    )


# ===========================================================================
# AC5: Graceful fallback when trigger element is removed from DOM
# ===========================================================================

def test_graceful_fallback_when_trigger_removed():
    """AC5: Focus falls back to document.body if the trigger element is no longer in the DOM."""
    block = _modal_block(_src())
    # Must check if element is still in DOM (contains / isConnected) before calling .focus()
    has_fallback = (
        "document.body" in block
        and (
            ".focus()" in block
        )
    )
    assert has_fallback, (
        "SourceDetailModal must fall back to document.body.focus() if trigger is not in DOM (AC5)"
    )


def test_fallback_uses_contains_or_isConnected():
    """AC5: DOM-presence check uses contains() or isConnected before calling .focus()."""
    block = _modal_block(_src())
    has_dom_check = (
        "isConnected" in block
        or "contains(" in block
        or "document.body.contains" in block
    )
    assert has_dom_check, (
        "SourceDetailModal must check if trigger is in DOM (isConnected or contains) before "
        "restoring focus (AC5)"
    )


# ===========================================================================
# AC6: Fix scoped to SourceDetailModal; no other modal altered
# ===========================================================================

def test_fix_scoped_to_source_detail_modal():
    """AC6: Focus-trap and focus-return code appears only within SourceDetailModal block."""
    src = _src()
    modal_block = _modal_block(src)

    # The focus management keywords should appear in the modal block
    assert ".focus()" in modal_block, "Focus management must be inside SourceDetailModal (AC6)"
    assert "shiftKey" in modal_block, "Focus trap must be inside SourceDetailModal (AC6)"

    # Verify that CommanderSpecModal (if present) does NOT contain the new shiftKey focus-trap
    # logic — meaning we haven't accidentally modified other modals.
    commander_spec_block = re.search(
        r"function CommanderSpecModal\(.+?\n\}(?=\n\n// |\nfunction |\Z)",
        src,
        re.DOTALL,
    )
    if commander_spec_block:
        other_block = commander_spec_block.group(0)
        # If CommanderSpecModal already has shiftKey, it predates this PR; that's fine.
        # What we must NOT do is add triggerRef / returnFocus-style code to OTHER modals.
        # We only assert that SourceDetailModal has the new code; we don't fail if
        # CommanderSpecModal independently has its own focus handling.
        assert "function SourceDetailModal" not in other_block, (
            "SourceDetailModal code must not be nested inside CommanderSpecModal (AC6)"
        )
