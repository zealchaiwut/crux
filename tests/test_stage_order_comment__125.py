"""Tests for issue #125: [follow-up] Add clarifying comment to _STAGE_ORDER definition (runs against UAT)"""
import os
import pytest
import httpx
import re


# Resolved from UAT .env at runtime; see tester skill Step 0.
# Default kept only as a last-resort fallback if BASE_URL not exported.
BASE_URL = os.environ.get("UAT_BASE_URL") or "http://localhost:" + os.environ.get("UAT_PORT", "")
if not BASE_URL.startswith("http"):
    raise RuntimeError(
        "UAT_BASE_URL / UAT_PORT not set. Run the tester skill's Step 0 to resolve UAT before pytest."
    )


@pytest.fixture
def client():
    with httpx.Client(base_url=BASE_URL, timeout=10.0) as c:
        yield c


# --- Acceptance Criteria ---

def test_stage_order__comment_present():
    """AC: An inline comment is added adjacent to the _STAGE_ORDER definition in app/routers/cases.py (around line 20)"""
    # Read the source file
    source_path = os.path.join(
        os.path.dirname(__file__),
        "..",
        "app",
        "routers",
        "cases.py"
    )
    with open(source_path, "r") as f:
        content = f.read()

    # Verify _STAGE_ORDER definition exists
    assert "_STAGE_ORDER = {" in content, "_STAGE_ORDER definition not found"

    # Extract the section around _STAGE_ORDER
    stage_order_start = content.find("_STAGE_ORDER = {")
    assert stage_order_start != -1, "_STAGE_ORDER definition not found"

    # Look backwards from _STAGE_ORDER for comments
    # We'll search a larger window (300 chars before and 300 after)
    section_start = max(0, stage_order_start - 300)
    section_end = min(len(content), stage_order_start + 300)
    section = content[section_start:section_end]

    # Check for a comment explaining the legacy fallback purpose
    # The comment should mention legacy/fallback and that it's not used for API response serialization
    has_legacy_mention = "legacy" in section.lower() and "fallback" in section.lower()
    has_ui_mapping = "ui" in section.lower() and "mapping" in section.lower()
    has_api_mention = "api" in section.lower() and ("response" in section.lower() or "serialization" in section.lower())

    assert has_legacy_mention and (has_ui_mapping or has_api_mention), (
        "No clarifying comment found near _STAGE_ORDER. "
        "Expected a comment explaining legacy fallback/UI mapping purpose and that it's not used for API response serialization."
    )


def test_stage_order__values_unchanged():
    """AC: The existing _STAGE_ORDER numeric mapping values remain unchanged after the edit"""
    # Read the source file
    source_path = os.path.join(
        os.path.dirname(__file__),
        "..",
        "app",
        "routers",
        "cases.py"
    )
    with open(source_path, "r") as f:
        content = f.read()

    # Extract _STAGE_ORDER definition
    match = re.search(
        r'_STAGE_ORDER\s*=\s*\{([^}]+)\}',
        content,
        re.DOTALL
    )
    assert match, "_STAGE_ORDER definition not found"

    dict_content = match.group(1)

    # Expected values
    expected_stages = {
        "sharpened": "0",
        "bake_off": "1",
        "gather": "2",
        "weigh": "3",
        "probe": "4",
        "verdict": "5",
    }

    # Verify each stage and its value
    for stage, value in expected_stages.items():
        pattern = rf'"{stage}"\s*:\s*{value}'
        assert re.search(pattern, dict_content), (
            f"Expected mapping '{stage}': {value} not found in _STAGE_ORDER"
        )


def test_stage_order__no_behavioral_change(client):
    """AC: The comment does not alter the behavior or value of _STAGE_ORDER — code change is comment-only"""
    # Create a test case to verify stage field is returned as string enum
    r = client.get("/api/cases")
    assert r.status_code == 200, f"GET /api/cases failed: {r.status_code}"

    data = r.json()
    # If there are cases in the response, verify stage is a string
    if "data" in data and isinstance(data["data"], list) and len(data["data"]) > 0:
        for case in data["data"]:
            if "stage" in case:
                # Stage should be a string enum value, not a numeric value from _STAGE_ORDER
                assert isinstance(case["stage"], str), (
                    f"Stage field should be a string enum, got {type(case['stage'])}"
                )
                # Verify it's one of the valid stage strings
                valid_stages = {"sharpened", "bake_off", "gather", "weigh", "probe", "verdict"}
                assert case["stage"] in valid_stages, (
                    f"Stage '{case['stage']}' is not a recognized stage value"
                )
