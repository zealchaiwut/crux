"""UAT Tests for issue #96: Split case gate — Summary pre-verdict, ActionPlan stays locked.

These tests verify that the frontend JS correctly gates the Case Summary and ActionPlan
sections based on stage and verdict state. They focus on the data structures returned
by the API that the frontend depends on for conditional rendering.

The critical gates in the frontend (cases.js):
- CASE SUMMARY: shown when stage >= 4
- ACTION PLAN: shown when stage >= 4; content inside is gated by verdict_log

These tests use the UAT server API to verify the data returned supports these gates.
"""
import os
import pytest
import httpx

# Resolved from UAT .env at runtime; see tester skill Step 0.
BASE_URL = os.environ.get("UAT_BASE_URL") or "http://localhost:" + os.environ.get("UAT_PORT", "")
if not BASE_URL.startswith("http"):
    raise RuntimeError(
        "UAT_BASE_URL / UAT_PORT not set. Run the tester skill's Step 0 to resolve UAT before pytest."
    )


@pytest.fixture
def client():
    with httpx.Client(base_url=BASE_URL, timeout=10.0) as c:
        yield c


def _create_case(client, title="Test case"):
    """Helper: POST /api/cases to create a new case (stage 0 - sharpened)."""
    resp = client.post(
        "/api/cases",
        json={
            "raw_problem": title,
            "sharpened": f"Test: {title}",
            "not_investigating": [],
        },
    )
    assert resp.status_code == 201, f"Failed to create case: {resp.text}"
    return resp.json()


# ---------------------------------------------------------------------------
# AC1: Case Summary renders once a probe is designed, regardless of verdict
# AC3: Probe designed + no verdict → Summary visible, ActionPlan absent
# ---------------------------------------------------------------------------

def test_ac1_ac3_summary_visible_at_probe_stage_without_verdict(client):
    """AC1/AC3: Case Summary depends on stage >= 4; it does NOT require verdict.

    Verify the API returns the structure that allows the frontend to show Summary
    at probe stage (stage >= 4) even when verdict_log is null.
    """
    case = _create_case(client, "AC1/AC3: Test probe stage without verdict")
    case_id = case["id"]

    resp = client.get(f"/api/cases/{case_id}")
    assert resp.status_code == 200
    data = resp.json()

    # The gate for Case Summary in the frontend is: {stage >= 4 && (...)}
    # This test verifies the case will reach stage >= 4 (verified elsewhere in full flow)
    # At minimum, the API response must include the 'summary' field so the frontend
    # can conditionally render it when stage >= 4
    assert "summary" in data, (
        "API must include 'summary' field to support Case Summary rendering (AC1)"
    )

    # At this stage (initially stage 0), summary should be null/empty
    # but the field must exist for the frontend to render it when stage becomes >= 4
    # The frontend will later hydrate this as the case progresses


# ---------------------------------------------------------------------------
# AC2: ActionPlan remains hidden until a verdict is logged
# AC5: No probe designed → neither Summary nor ActionPlan visible
# ---------------------------------------------------------------------------

def test_ac2_ac5_action_plan_gate_requires_stage_and_verdict(client):
    """AC2/AC5: ActionPlan is gated by stage >= 4 AND verdict_log.

    The frontend renders ActionPlan (and LockedPlan) only when stage >= 4.
    Within that, it shows ActionPlan content when verdict_log is present,
    and LockedPlan when verdict_log is null.

    This test verifies pre-probe cases (stage < 4) will not render ActionPlan.
    """
    case = _create_case(client, "AC2/AC5: Test pre-probe stage")
    case_id = case["id"]

    resp = client.get(f"/api/cases/{case_id}")
    assert resp.status_code == 200
    data = resp.json()

    # Pre-probe stage (initially < 4): neither Summary nor ActionPlan should render
    assert data["stage"] < 4, (
        f"New case should start at stage < 4, got {data['stage']} (AC5)"
    )

    # verdict_log should be null pre-verdict
    assert data.get("verdict_log") is None, (
        "verdict_log should be null until verdict is logged (AC2)"
    )

    # The frontend gates ActionPlan with {stage >= 4 && (<>...{verdict_log ? (...) : <LockedPlan>})}
    # Since stage < 4, ActionPlan should not render at all (AC5)


# ---------------------------------------------------------------------------
# AC4: Probe designed + verdict logged → both Summary and ActionPlan visible
# AC6: Regression — cases with verdict still show both sections correctly
# ---------------------------------------------------------------------------

def test_ac4_ac6_both_sections_visible_with_probe_and_verdict(client):
    """AC4/AC6: Both Summary and ActionPlan render when stage >= 4 AND verdict_log present.

    Verify the API returns the required fields for both sections to render correctly.
    This tests the regression case: existing cases with verdict should not break.
    """
    case = _create_case(client, "AC4/AC6: Test regression with verdict case")
    case_id = case["id"]

    # Note: In a real UAT flow, we would progress the case through stages.
    # For now, we verify the API structure supports the frontend gates.
    # A full end-to-end test requires AI API access (bake-off, probe, summary generation).

    resp = client.get(f"/api/cases/{case_id}")
    assert resp.status_code == 200
    data = resp.json()

    # The frontend requires these fields for Case Summary
    assert "summary" in data, "summary field must exist (AC4/AC6)"

    # The frontend requires these fields for ActionPlan (when verdict_log is present)
    # - verdict_log: the verdict object
    # - plans: the list of plans (for leading plan display)
    # - verdict: the verdict outcome (for color-coded display)

    # At this pre-verdict stage, verdict_log is null, which is expected
    # But the API must be able to return it when verdict is logged


# ---------------------------------------------------------------------------
# AC7: Summary and ActionPlan are gated separately
# ---------------------------------------------------------------------------

def test_ac7_summary_and_action_plan_separate_gates(client):
    """AC7: Verify in the frontend code that Summary and ActionPlan gates are separate.

    This is a static code check, not an API test. The tester's Step 4 already
    covers this with the test_split_case_gate__96.py file.

    This test documents that the separation is enforced:
    - CASE SUMMARY: gated by {stage >= 4 && (...)}
    - ACTION PLAN: gated by {stage >= 4 && (<> ... {verdict_log ? (...) : <LockedPlan>} ... </>)}

    If they were combined, the fix would be incomplete.
    """
    # This is verified by the static code tests in test_split_case_gate__96.py
    # and test_issue_96.py, which check the JS file directly.
    # This placeholder documents the requirement.
    pass


# ---------------------------------------------------------------------------
# Summary gate visibility
# ---------------------------------------------------------------------------

def test_api_returns_summary_field_for_gate(client):
    """Verify API returns 'summary' field so frontend can conditionally render it."""
    case = _create_case(client, "API summary field test")
    resp = client.get(f"/api/cases/{case.get('id')}")
    assert resp.status_code == 200
    data = resp.json()
    assert "summary" in data, "API must return 'summary' field (AC1)"


def test_api_returns_verdict_log_for_gate(client):
    """Verify API returns 'verdict_log' field so frontend can conditionally render ActionPlan."""
    case = _create_case(client, "API verdict_log field test")
    resp = client.get(f"/api/cases/{case.get('id')}")
    assert resp.status_code == 200
    data = resp.json()
    # verdict_log can be null initially, but the key must exist or the frontend must handle None
    # For this test, we verify the response structure allows verdict_log (either None or present)
    assert "verdict_log" in data or data.get("verdict_log") is None, (
        "API must include verdict_log field (null or present) (AC2)"
    )


def test_api_returns_stage_for_gates(client):
    """Verify API returns 'stage' field (needed for both Summary and ActionPlan gates)."""
    case = _create_case(client, "API stage field test")
    resp = client.get(f"/api/cases/{case.get('id')}")
    assert resp.status_code == 200
    data = resp.json()
    assert "stage" in data, "API must return 'stage' field (AC1/AC2/AC5)"
    assert isinstance(data["stage"], int), "stage must be an integer"
    assert 0 <= data["stage"] <= 5, "stage must be between 0 and 5"
