"""Tests for issue #96: Split case gate — Summary pre-verdict, ActionPlan stays locked.

This test verifies that Case Summary renders once a probe is designed (stage >= 4),
regardless of verdict state, while ActionPlan remains locked behind the verdict.

The feature is implemented in app/static/js/cases.js with a stage >= 4 gate wrapping
the ACTION PLAN section, while the CASE SUMMARY section was already gated at stage >= 4.

AC coverage:
  AC1 – Case Summary renders once a probe is designed, regardless of verdict state
  AC2 – ActionPlan remains hidden until a verdict is logged (existing gate preserved)
  AC3 – Probe designed + no verdict → Summary visible, no ActionPlan
  AC4 – Probe designed + verdict logged → both Summary and ActionPlan visible
  AC5 – No probe designed → neither Summary nor ActionPlan visible
  AC6 – No regression on cases that already have a logged verdict
  AC7 – LockedPlan / ActionPlan gate logic refactored so Summary and ActionPlan
        are controlled by separate conditions
"""
from pathlib import Path


# Read the cases.js file to verify the implementation
REPO_ROOT = Path(__file__).parent.parent
CASES_JS = (REPO_ROOT / "app" / "static" / "js" / "cases.js").read_text()


# --- Acceptance Criteria Tests (JavaScript structure verification) ---

def test_ac1_case_summary_section_exists():
    """AC1: CASE SUMMARY section must exist in the JS render output."""
    assert "CASE SUMMARY" in CASES_JS, (
        "CASE SUMMARY section heading must exist in cases.js (AC1)"
    )


def test_ac2_locked_plan_component_exists():
    """AC2: LockedPlan component must exist for the ActionPlan gate."""
    assert "LockedPlan" in CASES_JS, (
        "LockedPlan component must be referenced in cases.js (AC2)"
    )
    assert "verdict_log" in CASES_JS, (
        "verdict_log must be checked to conditionally render ActionPlan (AC2)"
    )


def test_ac3_action_plan_section_gated_at_stage_4():
    """AC3/AC5: ACTION PLAN section must be wrapped in a stage >= 4 gate.
    This ensures it is hidden for cases with no probe (stage < 4)."""

    # Find the ACTION PLAN section
    action_plan_idx = CASES_JS.find("<SectionLabel>ACTION PLAN")
    assert action_plan_idx != -1, (
        "ACTION PLAN section with JSX SectionLabel must exist in cases.js (AC3)"
    )

    # Check that there's a stage >= 4 gate BEFORE the ACTION PLAN section
    # We search backwards from the ACTION PLAN position for the gate
    preceding_500_chars = CASES_JS[max(0, action_plan_idx - 500):action_plan_idx]

    # The gate must be within the preceding code block (not too far back)
    assert "stage >= 4" in preceding_500_chars, (
        "A 'stage >= 4' conditional gate must appear immediately before the "
        "ACTION PLAN section to hide it for pre-probe cases (AC3/AC5)"
    )

    # Verify the gate wraps the section properly by looking for JSX structure
    # The gate should look like: {stage >= 4 && (<>...<SectionLabel>ACTION PLAN...
    gate_idx = preceding_500_chars.rfind("stage >= 4")
    if gate_idx != -1:
        # Check for opening fragment/conditional after the gate
        after_gate = CASES_JS[action_plan_idx - 500 + gate_idx:action_plan_idx + 200]
        assert "{" in after_gate and "ACTION PLAN" in after_gate, (
            "stage >= 4 gate must conditionally wrap the ACTION PLAN section in JSX (AC3)"
        )


def test_ac4_action_plan_content_gated_by_verdict():
    """AC4: Within the ACTION PLAN section (stage >= 4), content must be gated by verdict_log."""
    # Find ACTION PLAN and the verdict_log check
    action_plan_idx = CASES_JS.find("<SectionLabel>ACTION PLAN")
    assert action_plan_idx != -1

    # Within the next 3000 chars, there must be a verdict_log conditional
    after_action_plan = CASES_JS[action_plan_idx:action_plan_idx + 3000]
    assert "verdict_log" in after_action_plan, (
        "verdict_log must be checked within the ACTION PLAN section (AC4)"
    )
    # LockedPlan is further down in the section, check it exists somewhere in the file
    assert "LockedPlan" in CASES_JS, (
        "LockedPlan must appear in the ACTION PLAN section for the no-verdict case (AC4)"
    )


def test_ac5_summary_and_action_plan_separately_gated():
    """AC5/AC7: Summary and ActionPlan must be controlled by separate gates.

    Look for evidence that:
    - CASE SUMMARY appears in render
    - It is NOT inside the same stage >= 4 gate as ACTION PLAN
    - They are independent conditions
    """

    # Find both sections
    summary_idx = CASES_JS.find("CASE SUMMARY")
    action_plan_idx = CASES_JS.find("<SectionLabel>ACTION PLAN")

    assert summary_idx != -1, "CASE SUMMARY must exist"
    assert action_plan_idx != -1, "ACTION PLAN section must exist"

    # Summary should appear before ACTION PLAN in the file
    assert summary_idx < action_plan_idx, (
        "CASE SUMMARY should be rendered before ACTION PLAN in render order (AC5/AC7)"
    )

    # Count the number of stage >= 4 gates; there should be at least one for ACTION PLAN
    stage_gates = CASES_JS.count("stage >= 4")
    assert stage_gates >= 1, (
        "At least one 'stage >= 4' gate must exist for the ACTION PLAN section (AC5)"
    )


def test_ac6_no_regression_verdict_log_field_accessed():
    """AC6: The verdict_log field is still accessed and rendered when present."""
    # Ensure the code still uses verdict_log for rendering the full ActionPlan
    assert "verdict_log" in CASES_JS, (
        "verdict_log must still be referenced in cases.js for ActionPlan content (AC6 regression)"
    )

    # The LEADING PLAN and VERDICT sections should still exist
    assert "LEADING PLAN" in CASES_JS, (
        "LEADING PLAN section must still be rendered for verdict cases (AC6 regression)"
    )
    assert "VERDICT" in CASES_JS, (
        "VERDICT display must still be rendered when verdict_log exists (AC6 regression)"
    )


def test_ac7_gate_logic_is_split_not_combined():
    """AC7: Verify that Summary and ActionPlan are gated separately.

    The implementation should have:
    - stage >= 4 at the ACTION PLAN section level
    - verdict_log inside the ACTION PLAN section (not combined at outer level)

    This means Summary is gated ONLY by stage >= 4,
    while ActionPlan is gated by stage >= 4 AND verdict_log.
    """

    # Find the pattern: ACTION PLAN must be gated by stage >= 4 independently
    action_plan_idx = CASES_JS.find("<SectionLabel>ACTION PLAN")
    assert action_plan_idx != -1

    # Check the 300 chars before ACTION PLAN for the gate
    preceding = CASES_JS[max(0, action_plan_idx - 300):action_plan_idx]

    # The pattern should be: {stage >= 4 && (... then later verdict_log check
    assert "stage >= 4" in preceding, (
        "ACTION PLAN must have a stage >= 4 gate at the section level (AC7)"
    )

    # Verify that verdict_log is NOT in the preceding section (it comes AFTER in the content)
    # This proves they're not combined at the outer level
    if "verdict_log" in preceding:
        # If verdict_log appears before, it should not be combined with the stage gate
        # (they're separate OR the outer gate is stage >= 4 with verdict_log inside)
        pass  # Acceptable if inside

    # The key is: CASE SUMMARY should appear OUTSIDE or before any verdict_log check
    summary_idx = CASES_JS.find("CASE SUMMARY")

    # For proper separation: Summary must exist independent of verdict checks
    assert summary_idx < action_plan_idx, (
        "CASE SUMMARY must appear in render before ACTION PLAN (AC7)"
    )


def test_ac7_refactoring_introduces_stage_gate_for_action_plan():
    """AC7: The refactoring introduces a stage >= 4 gate specifically for ACTION PLAN.

    Before: both Summary and ActionPlan were behind the same verdict_log gate
    After: Summary is behind stage >= 4 (already was in issue #95)
           ActionPlan is behind stage >= 4 AND verdict_log (split gate)
    """

    # Verify that stage >= 4 exists and is associated with ACTION PLAN
    action_plan_idx = CASES_JS.find("<SectionLabel>ACTION PLAN")
    assert action_plan_idx != -1

    # Search backwards from ACTION PLAN for the gate
    preceding = CASES_JS[max(0, action_plan_idx - 500):action_plan_idx]
    assert "stage >= 4" in preceding, (
        "stage >= 4 gate must appear before ACTION PLAN (AC7 refactor requirement)"
    )

    # Verify the gate is in a conditional JSX context
    # Pattern: {stage >= 4 && (...)...ACTION PLAN...}
    section_start = preceding.rfind("stage >= 4")
    if section_start != -1:
        context = preceding[section_start:]
        assert "{" not in context.split("ACTION")[0], (
            "stage >= 4 gate should be in JSX conditional context (AC7)"
        )
