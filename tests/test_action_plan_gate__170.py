"""Tests for issue #170: Gate action plan on first probe verdict (UAT)."""
import os

import pytest
import httpx


BASE_URL = os.environ.get("UAT_BASE_URL") or (
    "http://localhost:" + os.environ.get("UAT_PORT", "8001")
)
if not BASE_URL.startswith("http"):
    msg = (
        "UAT_BASE_URL / UAT_PORT not set. "
        "Run the tester skill's Step 0 to resolve UAT before pytest."
    )
    raise RuntimeError(msg)


@pytest.fixture
def client():
    """HTTP client configured for UAT server."""
    with httpx.Client(base_url=BASE_URL, timeout=10.0) as c:
        yield c


# --- Acceptance Criteria Tests ---

def test_action_plan_locked_with_no_verdicts(client):
    """AC1: Action plan remains locked when zero verdicts logged.

    GET /api/cases/{id} returns action_plan_state='locked' when no verdicts.
    GET /api/cases/{id}/action-plan returns 403 (Forbidden).
    """
    pytest.skip("manual — UAT lacks test case creation; see API test suite")


def test_action_plan_unlocks_on_first_verdict(client):
    """AC2: Action plan unlocks provisionally on first verdict.

    GET /api/cases/{id} returns action_plan_state='provisional' after first.
    GET /api/cases/{id}/action-plan returns 200 (not 403).
    """
    pytest.skip("manual — UAT lacks test case creation; see API test suite")


def test_action_plan_provisional_label_displays(client):
    """AC3: Provisional label 'provisional · pending long-horizon' renders.

    cases.js includes label text when action_plan_state='provisional'.
    """
    pytest.skip("manual — frontend code review; check app/static/js/cases.js")


def test_action_plan_transitions_to_final_on_long_horizon_verdict(client):
    """AC4: Transitions to final on long-horizon verdict.

    GET /api/cases/{id} returns action_plan_state='final' after.
    GET /api/cases/{id}/action-plan returns 200 with state='final'.
    """
    pytest.skip("manual — UAT lacks test case creation; see API test suite")


def test_case_summary_accessible_across_all_states(client):
    """AC5: Case Summary accessible at all states.

    POST /api/cases/{id}/summary succeeds regardless of action_plan_state.
    """
    pytest.skip("manual — UAT lacks test case creation; see API test suite")


def test_server_side_action_plan_gate_enforced(client):
    """AC6: Server gate enforces provisional/final; client bypass prevented.

    GET /api/cases/{id}/action-plan returns 403 when state='locked'.
    Returns 200 with state when locked=false.
    """
    pytest.skip("manual — UAT lacks test case creation; see API test suite")


def test_no_regression_to_case_summary_or_probes(client):
    """AC8: No regression to Case Summary or probe-gated UI.

    GET /api/cases/{id} still returns probes[], verdict_log, and fields.
    """
    pytest.skip("manual — UAT lacks test case creation; see API test suite")


# --- Browser Interaction Tests (if UAT supports page navigation) ---

def test_action_plan_renders_in_provisional_state_on_page(client):
    """AC4: Provisional badge on case detail page in provisional state."""
    pytest.skip("manual — requires browser navigation; see UAT steps")


def test_action_plan_final_badge_disappears_after_long_horizon(client):
    """AC4: Provisional badge disappears; final styling applies."""
    pytest.skip("manual — requires browser navigation; see UAT steps")
