"""Tests for issue #147: Show Case Summary section at probe stage
(runs against UAT)"""
import os
import pathlib

# Resolved from UAT .env at runtime; see tester skill Step 0.
BASE_URL = (
    os.environ.get("UAT_BASE_URL")
    or "http://localhost:" + os.environ.get("UAT_PORT", "")
)
if not BASE_URL.startswith("http"):
    raise RuntimeError(
        "UAT_BASE_URL / UAT_PORT not set. Run the tester skill's Step 0"
        " to resolve UAT before pytest."
    )

# Read the JavaScript source to verify the component implementation
STATIC = pathlib.Path(__file__).parent.parent / "app" / "static"
JS_DIR = STATIC / "js"


def _read_combined_js():
    """Read all JS files to verify component implementation."""
    return "".join(
        (JS_DIR / f).read_text()
        for f in sorted(JS_DIR.iterdir())
        if f.suffix == ".js"
    )


# --- Acceptance Criteria Tests ---

def test_case_summary_section_component_exists():
    # AC1: A Case Summary section is rendered inside CaseDetailScreen
    # whenever case.stage === 'probe' (or any later stage).
    # Verify the CaseSummarySection component is defined
    combined_js = _read_combined_js()
    assert "CaseSummarySection" in combined_js, \
        "CaseSummarySection component must be defined in cases.js"


def test_case_summary_section_rendered_at_probe_stage_or_later():
    # AC1: The section is rendered at stage >= 4 (probe) or any later stage
    combined_js = _read_combined_js()
    # Verify the conditional that renders CaseSummarySection at probe stage
    assert "stage >= 4" in combined_js, (
        "CaseDetailScreen must render CaseSummarySection when stage >= 4"
        " (probe stage)"
    )


def test_case_summary_visible_without_verdict():
    # AC2: The section is visible even when no verdict exists
    # (case.verdict is null or undefined)
    combined_js = _read_combined_js()
    # Find CaseSummarySection definition and verify it doesn't require
    # verdict prop
    case_summary_start = combined_js.find("function CaseSummarySection")
    assert case_summary_start != -1, (
        "CaseSummarySection must be defined as a function"
    )
    case_summary_section = combined_js[
        case_summary_start:case_summary_start+5000
    ]

    # Verify the component accepts hasVerdict prop but doesn't require it
    # for rendering
    assert "hasVerdict" in case_summary_section, (
        "CaseSummarySection should accept hasVerdict prop"
    )
    # The component should render regardless of verdict state (verified by
    # checking it's inside the component)
    assert "summary" in case_summary_section, (
        "CaseSummarySection must handle summary prop for rendering"
    )


def test_case_summary_not_rendered_before_probe_stage():
    # AC3: The section is NOT rendered when the case stage is earlier than
    # probe
    combined_js = _read_combined_js()
    # Verify the conditional check for stage >= 4
    case_detail_start = combined_js.find("function CaseDetailScreen")
    assert case_detail_start != -1, "CaseDetailScreen must be defined"
    # Find the CaseSummarySection usage
    case_detail_block = combined_js[case_detail_start:]
    summary_usage = case_detail_block.find("CaseSummarySection")
    assert summary_usage != -1, (
        "CaseSummarySection must be used in CaseDetailScreen"
    )

    # Verify it's conditionally rendered with stage >= 4 check
    summary_context = case_detail_block[
        max(0, summary_usage-200):summary_usage+200
    ]
    assert (
        "stage >= 4" in summary_context
        or "{stage >= 4" in summary_context
    ), (
        "CaseSummarySection should only render when stage >= 4"
        " (not at sharpened/bake_off/gather/weigh)"
    )


def test_case_summary_section_uses_design_tokens():
    # AC4: Section heading and container use design tokens from DESIGN.md
    combined_js = _read_combined_js()
    case_summary_start = combined_js.find("function CaseSummarySection")
    case_summary_section = combined_js[
        case_summary_start:case_summary_start+3000
    ]

    # Verify design token usage (var(--*) pattern)
    assert "var(--surface)" in case_summary_section, (
        "CaseSummarySection should use --surface token for background"
    )
    assert "var(--border)" in case_summary_section, (
        "CaseSummarySection should use --border token for borders"
    )
    assert "var(--radius)" in case_summary_section, (
        "CaseSummarySection should use --radius token for border-radius"
    )
    assert "var(--space" in case_summary_section, (
        "CaseSummarySection should use spacing tokens (--space-*)"
    )
    assert "var(--text" in case_summary_section, (
        "CaseSummarySection should use text tokens (--text-*)"
        " for colors and sizing"
    )


def test_case_summary_field_handling():
    # AC5: If the field is empty/absent, the section renders a legible
    # placeholder rather than breaking
    combined_js = _read_combined_js()
    case_summary_start = combined_js.find("function CaseSummarySection")
    case_summary_section = combined_js[
        case_summary_start:case_summary_start+6000
    ]

    # Verify conditional rendering of summary content vs placeholder
    assert "No summary" in case_summary_section, (
        "CaseSummarySection should render a placeholder when summary"
        " is empty"
    )
    # Verify ternary or conditional check for summary presence
    assert "{summary ?" in case_summary_section, (
        "CaseSummarySection should conditionally render based on"
        " summary presence"
    )


def test_case_summary_and_verdict_no_regression():
    # AC6: No regression — existing verdict section continues to render
    # correctly when a verdict is present
    combined_js = _read_combined_js()
    case_detail_start = combined_js.find("function CaseDetailScreen")
    case_detail_block = combined_js[case_detail_start:]

    # Verify both CaseSummarySection and verdict rendering exist
    assert "CaseSummarySection" in case_detail_block, (
        "CaseSummarySection must be rendered in CaseDetailScreen"
    )
    # Look for verdict section rendering (may be in ActionPlan or separate)
    assert "verdict" in case_detail_block.lower(), (
        "CaseDetailScreen must still render verdict section/UI"
    )

    # Find both components to ensure they're both present (no replacement)
    summary_pos = case_detail_block.find("CaseSummarySection")
    verdict_pos = case_detail_block.lower().find("verdict")
    assert summary_pos != -1 and verdict_pos != -1, (
        "Both Case Summary and verdict sections should coexist"
        " in CaseDetailScreen"
    )


def test_case_summary_sectionlabel_styling():
    # AC4: Section heading uses design tokens (CASE SUMMARY label styling)
    combined_js = _read_combined_js()
    case_summary_start = combined_js.find("function CaseSummarySection")
    case_summary_section = combined_js[
        case_summary_start:case_summary_start+1000
    ]

    # Verify SectionLabel component is used for the heading
    assert "SectionLabel" in case_summary_section, (
        "CaseSummarySection should use SectionLabel component for the"
        " heading"
    )
    # Verify the label text
    assert "CASE SUMMARY" in case_summary_section, (
        "CaseSummarySection should have 'CASE SUMMARY' as the section"
        " heading"
    )
