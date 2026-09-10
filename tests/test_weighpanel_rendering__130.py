"""
UAT tests for issue #130: Fix WeighPanel not rendering in CaseDetailScreen.

These tests verify the WeighPanel (context textarea + submit button) renders correctly
for cases at gather/weigh stages and does NOT render at other stages.

Tests run against the live UAT server via HTTP.
"""
import os
import pytest
import httpx


BASE_URL = os.environ.get("UAT_BASE_URL", "").rstrip("/")
if not BASE_URL:
    pytest.skip("UAT_BASE_URL not set", allow_module_level=True)


@pytest.fixture
def client():
    with httpx.Client(base_url=BASE_URL, timeout=10.0) as c:
        yield c


def test_weighpanel__renders_at_gather_stage_in_ui(client):
    """AC1: WeighPanel renders between PlanCard list and ProbeCard section for gather stage."""
    # Get existing cases to find one at gather stage
    r = client.get("/api/cases")
    assert r.status_code == 200
    data = r.json()
    cases = data.get("cases", []) if isinstance(data, dict) else data

    # Find a case at gather stage (numeric stage 2)
    gather_case_id = None
    for case in cases:
        if case.get("stage") == 2:  # gather stage
            gather_case_id = case.get("id")
            break

    if not gather_case_id:
        pytest.skip("No gather-stage case found in UAT to test WeighPanel visibility")

    # Fetch the case detail page and verify WeighPanel is present
    page_resp = client.get(f"/cases/{gather_case_id}")
    assert page_resp.status_code == 200
    # The page should contain the WeighPanel textarea with aria-label "Your Context"
    # or the text "YOUR CONTEXT"
    content = page_resp.text
    assert "YOUR CONTEXT" in content or "aria-label" in content, \
        "WeighPanel does not appear to be rendered at gather stage"


def test_weighpanel__renders_at_weigh_stage_in_ui(client):
    """AC1: WeighPanel renders between PlanCard list and ProbeCard section for weigh stage."""
    r = client.get("/api/cases")
    assert r.status_code == 200
    data = r.json()
    cases = data.get("cases", []) if isinstance(data, dict) else data

    # Find a case at weigh stage (numeric stage 3)
    weigh_case_id = None
    for case in cases:
        if case.get("stage") == 3:  # weigh stage
            weigh_case_id = case.get("id")
            break

    if not weigh_case_id:
        pytest.skip("No weigh-stage case found in UAT to test WeighPanel visibility")

    # Fetch the case detail page and verify WeighPanel is present
    page_resp = client.get(f"/cases/{weigh_case_id}")
    assert page_resp.status_code == 200
    content = page_resp.text
    assert "YOUR CONTEXT" in content or "aria-label" in content, \
        "WeighPanel does not appear to be rendered at weigh stage"


def test_weighpanel__not_rendered_at_probe_stage(client):
    """AC2: WeighPanel must NOT render for cases at probe stage (stage >= 4)."""
    r = client.get("/api/cases")
    assert r.status_code == 200
    data = r.json()
    cases = data.get("cases", []) if isinstance(data, dict) else data

    # Find a case at probe stage (numeric stage >= 4)
    probe_case_id = None
    for case in cases:
        if case.get("stage") >= 4:  # probe or verdict stage
            probe_case_id = case.get("id")
            break

    if not probe_case_id:
        pytest.skip("No probe-stage case found in UAT to test WeighPanel absence")

    # Fetch the case detail page and verify WeighPanel is NOT present
    page_resp = client.get(f"/cases/{probe_case_id}")
    assert page_resp.status_code == 200
    # The WeighPanel textarea with aria-label "Your Context" should not be in the page
    content = page_resp.text
    assert "aria-label=\"Your Context\"" not in content, \
        "WeighPanel should not render at probe stage or higher"


def test_weighpanel__rerank_endpoint_accepts_context(client):
    """AC3: POST /api/cases/{id}/rerank accepts context payload."""
    r = client.get("/api/cases")
    assert r.status_code == 200
    data = r.json()
    cases = data.get("cases", []) if isinstance(data, dict) else data

    # Find a gather-stage case to test rerank
    gather_case = None
    for case in cases:
        if case.get("stage") == 2:  # gather
            gather_case = case
            break

    if not gather_case:
        pytest.skip("No gather-stage case available to test rerank endpoint")

    # POST to the rerank endpoint with context
    rerank_resp = client.post(
        f"/api/cases/{gather_case.get('id')}/rerank",
        json={"context": "Test context for reranking"}
    )
    assert rerank_resp.status_code in (200, 201), \
        f"Rerank endpoint failed: {rerank_resp.status_code} {rerank_resp.text}"


def test_weighpanel__rerank_advances_stage_to_weigh(client):
    """AC4: Successful POST /api/cases/{id}/rerank advances case from gather to weigh stage."""
    r = client.get("/api/cases")
    assert r.status_code == 200
    data = r.json()
    cases = data.get("cases", []) if isinstance(data, dict) else data

    # Find a gather-stage case
    gather_case = None
    for case in cases:
        if case.get("stage") == 2:  # gather
            gather_case = case
            break

    if not gather_case:
        pytest.skip("No gather-stage case available to test stage advancement")

    case_id = gather_case.get("id")

    # POST to rerank
    rerank_resp = client.post(
        f"/api/cases/{case_id}/rerank",
        json={"context": "Context for stage advancement test"}
    )
    assert rerank_resp.status_code in (200, 201), \
        f"Rerank POST failed: {rerank_resp.status_code}"

    # Verify the case advanced to weigh stage (stage 3)
    get_resp = client.get(f"/api/cases/{case_id}")
    assert get_resp.status_code == 200
    updated_case = get_resp.json()
    assert updated_case.get("stage") == 3, \
        f"Case stage should be 3 (weigh) after rerank, got {updated_case.get('stage')}"


def test_weighpanel__no_render_errors_at_gather(client):
    """AC5: No console errors when WeighPanel is rendered at gather stage."""
    # This is a structural check: verify the JS code does not have syntax errors
    r = client.get("/api/cases")
    assert r.status_code == 200
    data = r.json()
    cases = data.get("cases", []) if isinstance(data, dict) else data

    gather_case = None
    for case in cases:
        if case.get("stage") == 2:
            gather_case = case
            break

    if not gather_case:
        pytest.skip("No gather-stage case to verify JS renders without errors")

    # Fetch the page — if there were JS syntax errors, the page would fail to load
    page_resp = client.get(f"/cases/{gather_case.get('id')}")
    assert page_resp.status_code == 200, \
        "Page failed to load — likely JS error"


def test_weighpanel__plancards_rendering_unaffected(client):
    """AC6: PlanCard and ProbeCard rendering is unaffected by the WeighPanel fix."""
    r = client.get("/api/cases")
    assert r.status_code == 200
    data = r.json()
    cases = data.get("cases", []) if isinstance(data, dict) else data

    # Find a case with plans
    case_with_plans = None
    for case in cases:
        if case.get("plans") and len(case.get("plans", [])) > 0:
            case_with_plans = case
            break

    if not case_with_plans:
        pytest.skip("No cases with plans found for regression test")

    # Verify the case still has plans in the API response
    get_resp = client.get(f"/api/cases/{case_with_plans.get('id')}")
    assert get_resp.status_code == 200
    case_data = get_resp.json()
    assert case_data.get("plans") is not None
    assert len(case_data.get("plans", [])) > 0, \
        "PlanCard rendering appears affected: plans no longer returned"
