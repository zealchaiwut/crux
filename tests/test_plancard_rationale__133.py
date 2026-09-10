"""Tests for issue #133: Render per-plan rationale text in PlanCard"""
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


def _find_case_with_rationale(client):
    """Return (case_id, rationale_text) for the first plan with non-empty rationale."""
    r = client.get("/api/cases")
    assert r.status_code == 200
    cases = r.json().get("cases", [])
    for case in cases:
        detail = client.get(f"/api/cases/{case['id']}")
        if detail.status_code != 200:
            continue
        for plan in detail.json().get("plans", []):
            if plan.get("rationale"):
                return case["id"], plan["rationale"]
    return None, None


def test_plancard_rationale__api_includes_rationale_field(client):
    """AC1 prerequisite: GET /api/cases/{id} returns a rationale field on each plan."""
    r = client.get("/api/cases")
    assert r.status_code == 200
    cases = r.json().get("cases", [])
    if not cases:
        pytest.skip("No cases in UAT database")

    case_id = cases[0]["id"]
    r2 = client.get(f"/api/cases/{case_id}")
    assert r2.status_code == 200
    data = r2.json()
    for plan in data.get("plans", []):
        assert "rationale" in plan, (
            f"Plan object is missing 'rationale' field: {list(plan.keys())}"
        )


def test_plancard_rationale__rendered_when_present(client):
    """AC1: PlanCard renders plan rationale text when the field is non-empty."""
    case_id, rationale_text = _find_case_with_rationale(client)
    if case_id is None:
        pytest.skip("No plans with non-empty rationale found in UAT")

    page = client.get(f"/cases/{case_id}")
    assert page.status_code == 200
    # The rationale text (or a distinct substring of it) must appear in the rendered page
    snippet = rationale_text[:80]
    assert snippet in page.text, (
        f"Rationale text not found in rendered PlanCard. "
        f"Expected snippet: {snippet!r}"
    )


def test_plancard_rationale__hidden_when_absent(client):
    """AC2: No empty rationale container when the field is absent or empty."""
    r = client.get("/api/cases")
    assert r.status_code == 200
    cases = r.json().get("cases", [])

    # Find a case where at least one plan has no rationale
    target_case_id = None
    for case in cases:
        detail = client.get(f"/api/cases/{case['id']}")
        if detail.status_code != 200:
            continue
        for plan in detail.json().get("plans", []):
            if not plan.get("rationale"):
                target_case_id = case["id"]
                break
        if target_case_id:
            break

    if not target_case_id:
        pytest.skip("All plans in UAT have a rationale — cannot test absent case")

    page = client.get(f"/cases/{target_case_id}")
    assert page.status_code == 200
    # The sentinel data-testid or aria-label for an empty rationale block must not appear.
    # The implementation uses data-testid="plan-rationale" only when rationale is present.
    content = page.text
    # Count occurrences of the rationale testid — should correspond only to plans
    # that actually have rationale, not to all plans.
    detail = client.get(f"/api/cases/{target_case_id}")
    plans = detail.json().get("plans", [])
    plans_with_rationale = sum(1 for p in plans if p.get("rationale"))
    occurrences = content.count('data-testid="plan-rationale"')
    assert occurrences == plans_with_rationale, (
        f"Expected {plans_with_rationale} rationale block(s), found {occurrences} in page HTML"
    )


def test_plancard_rationale__page_loads_without_error(client):
    """AC5: Component renders without JS errors — page loads successfully."""
    r = client.get("/api/cases")
    assert r.status_code == 200
    cases = r.json().get("cases", [])
    if not cases:
        pytest.skip("No cases in UAT database")

    # Find a case that has at least one plan
    case_with_plans = None
    for case in cases:
        detail = client.get(f"/api/cases/{case['id']}")
        if detail.status_code == 200 and detail.json().get("plans"):
            case_with_plans = case["id"]
            break

    if not case_with_plans:
        pytest.skip("No cases with plans found")

    page = client.get(f"/cases/{case_with_plans}")
    assert page.status_code == 200, (
        f"Case detail page failed to load: {page.status_code}"
    )
    # Page must contain the JS bundle — absence indicates a load failure
    assert "cases.js" in page.text or "PlanCard" in page.text or "plan-key" in page.text, (
        "Page does not appear to contain the cases.js bundle"
    )


def test_plancard_rationale__sources_section_still_present(client):
    """AC4: Existing sources section is unaffected by the rationale block addition."""
    r = client.get("/api/cases")
    assert r.status_code == 200
    cases = r.json().get("cases", [])

    # Find a case with a plan that has sources
    target_id = None
    for case in cases:
        detail = client.get(f"/api/cases/{case['id']}")
        if detail.status_code != 200:
            continue
        for plan in detail.json().get("plans", []):
            if plan.get("sources"):
                target_id = case["id"]
                break
        if target_id:
            break

    if not target_id:
        pytest.skip("No cases with sourced plans found in UAT")

    page = client.get(f"/cases/{target_id}")
    assert page.status_code == 200
    # SOURCES label must still appear in the rendered card
    assert "SOURCES" in page.text, (
        "SOURCES section label missing from PlanCard — layout may be broken"
    )
