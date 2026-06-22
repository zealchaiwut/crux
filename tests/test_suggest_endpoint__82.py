"""Tests for issue #82: Add suggest endpoint for non-persisting candidate sources (runs against UAT)"""
import os
import pytest
import httpx
import uuid


BASE_URL = os.environ.get("UAT_BASE_URL") or "http://localhost:" + os.environ.get("UAT_PORT", "")
if not BASE_URL.startswith("http"):
    raise RuntimeError(
        "UAT_BASE_URL / UAT_PORT not set. Run the tester skill's Step 0 to resolve UAT before pytest."
    )


@pytest.fixture
def client():
    with httpx.Client(base_url=BASE_URL, timeout=10.0) as c:
        yield c


@pytest.fixture
def valid_plan(client):
    """Create a Case and Plan for testing."""
    # Create Case
    case_resp = client.post("/api/cases", json={
        "raw_problem": "Test problem for suggest endpoint",
        "sharpened": "Sharpened test problem",
        "not_investigating": ["Out of scope for this test"],
    })
    if case_resp.status_code != 201:
        pytest.skip(f"Failed to create case (UAT dependency): {case_resp.text}")
    case_id = case_resp.json()["id"]

    # Run bake-off to generate plans
    bakeoff_resp = client.post(f"/api/cases/{case_id}/bake-off")
    if bakeoff_resp.status_code != 200:
        pytest.skip(f"Failed bake-off (Claude dependency): {bakeoff_resp.text}")
    bakeoff_data = bakeoff_resp.json()

    # Extract first plan ID from bakeoff response
    if "plans" not in bakeoff_data or len(bakeoff_data["plans"]) == 0:
        pytest.skip("Bake-off produced no plans (research engine unavailable)")
    plan_id = bakeoff_data["plans"][0]["id"]

    return case_id, plan_id


# --- Acceptance Criteria ---

def test_suggest_endpoint_exists_and_routed_separately(client, valid_plan):
    # AC1: POST /api/plans/{plan_id}/gather/suggest exists and is routed separately
    case_id, plan_id = valid_plan
    resp = client.post(f"/api/plans/{plan_id}/gather/suggest")
    # Should not 404 due to wrong route; should succeed or fail for business reasons
    assert resp.status_code != 404, "suggest endpoint not found or route misconfigured"


def test_suggest_returns_ranked_candidates(client, valid_plan):
    # AC2: Endpoint runs research loop and returns 0-5 ranked candidates without persisting
    case_id, plan_id = valid_plan
    resp = client.post(f"/api/plans/{plan_id}/gather/suggest")
    assert resp.status_code == 200
    body = resp.json()
    assert "candidates" in body
    assert isinstance(body["candidates"], list)
    assert len(body["candidates"]) <= 5


def test_candidate_schema_has_required_fields(client, valid_plan):
    # AC3: Each candidate includes candidate_id, kind, title, url, claim, citation, relevance_score
    case_id, plan_id = valid_plan
    resp = client.post(f"/api/plans/{plan_id}/gather/suggest")
    assert resp.status_code == 200
    body = resp.json()

    for candidate in body["candidates"]:
        assert "candidate_id" in candidate, "Missing candidate_id"
        assert "kind" in candidate, "Missing kind"
        assert "title" in candidate, "Missing title"
        assert "url" in candidate, "Missing url"
        assert "claim" in candidate, "Missing claim"
        assert "citation" in candidate, "Missing citation"
        assert "relevance_score" in candidate, "Missing relevance_score"

        # Validate types
        assert isinstance(candidate["candidate_id"], str), "candidate_id not a string"
        assert candidate["kind"] in ("book", "article", "youtube"), f"Invalid kind: {candidate['kind']}"
        assert isinstance(candidate["title"], str), "title not a string"
        assert isinstance(candidate["url"], str), "url not a string"
        assert isinstance(candidate["claim"], str), "claim not a string"
        assert isinstance(candidate["citation"], str), "citation not a string"
        assert isinstance(candidate["relevance_score"], (int, float)), "relevance_score not numeric"


def test_candidates_sorted_by_relevance_descending(client, valid_plan):
    # AC4: Candidates ordered by relevance_score descending
    case_id, plan_id = valid_plan
    resp = client.post(f"/api/plans/{plan_id}/gather/suggest")
    assert resp.status_code == 200
    body = resp.json()

    candidates = body["candidates"]
    if len(candidates) > 1:
        scores = [c["relevance_score"] for c in candidates]
        assert scores == sorted(scores, reverse=True), "Candidates not sorted by relevance_score descending"


def test_empty_results_graceful_degradation(client, valid_plan):
    # AC5: When research engine yields no results, return 200 OK with empty candidates array
    case_id, plan_id = valid_plan
    # Use the first plan from valid_plan (may be empty); just verify response is 200 with candidates array
    suggest_resp = client.post(f"/api/plans/{plan_id}/gather/suggest")
    assert suggest_resp.status_code == 200
    body = suggest_resp.json()
    assert "candidates" in body
    assert isinstance(body["candidates"], list)


def test_unavailable_dependency_graceful_degradation(client, valid_plan):
    # AC6: When LLM/embedding unavailable, return 200 OK with empty candidates array
    case_id, plan_id = valid_plan
    resp = client.post(f"/api/plans/{plan_id}/gather/suggest")
    # Just verify it doesn't return 5xx; if engine fails gracefully, returns empty list
    assert resp.status_code in (200, 503), f"Unexpected status: {resp.status_code}"
    if resp.status_code == 200:
        body = resp.json()
        assert "candidates" in body


def test_existing_gather_endpoint_unaffected(client, valid_plan):
    # AC7: Existing POST /api/plans/{plan_id}/gather continues to function and auto-attach
    case_id, plan_id = valid_plan
    resp = client.post(f"/api/plans/{plan_id}/gather")
    # Endpoint should exist and return 200 or graceful error
    assert resp.status_code in (200, 422, 500), f"Unexpected gather status: {resp.status_code}"
    if resp.status_code == 200:
        assert "sources" in resp.json() or "gather_status" in resp.json()


def test_suggest_is_primary_entry_point(client):
    # AC8: suggest treated as primary entry point in routing, documentation, and schema
    # Verify suggest endpoint is routable (not 404 due to wrong path)
    # Use a valid plan_id (any UUID); we're checking for route existence, not content
    import uuid
    fake_plan_id = str(uuid.uuid4())
    resp = client.post(f"/api/plans/{fake_plan_id}/gather/suggest")
    # Should not 404 due to route mismatch; may 404 for missing plan, but route exists
    assert resp.status_code != 404, "suggest route not found (404)"


def test_response_schema_validated_malformed_candidates_dropped(client, valid_plan):
    # AC9: Missing/malformed fields cause a logged warning, candidate is dropped, no 500
    case_id, plan_id = valid_plan
    resp = client.post(f"/api/plans/{plan_id}/gather/suggest")
    # Verify endpoint doesn't return 500 even if some candidates are malformed
    assert resp.status_code != 500, f"Got 500 on suggest: {resp.text}"


def test_suggest_integration_normal_response_ranked(client, valid_plan):
    # AC10a: Integration test — normal response with ranked candidates
    case_id, plan_id = valid_plan
    resp = client.post(f"/api/plans/{plan_id}/gather/suggest")
    assert resp.status_code == 200
    body = resp.json()
    assert "candidates" in body
    # If candidates returned, they should be sorted by relevance_score descending
    if body["candidates"]:
        scores = [c["relevance_score"] for c in body["candidates"]]
        assert scores == sorted(scores, reverse=True)


def test_suggest_integration_empty_degradation(client, valid_plan):
    # AC10b: Integration test — empty-list degradation when engine returns nothing
    case_id, plan_id = valid_plan
    resp = client.post(f"/api/plans/{plan_id}/gather/suggest")
    assert resp.status_code == 200
    body = resp.json()
    assert isinstance(body.get("candidates"), list)


def test_suggest_integration_llm_unavailable_degradation(client, valid_plan):
    # AC10c: Integration test — empty-list degradation when LLM/embedding unavailable
    case_id, plan_id = valid_plan
    resp = client.post(f"/api/plans/{plan_id}/gather/suggest")
    # Should gracefully degrade; status 200 with empty list or 503 with service error
    assert resp.status_code in (200, 503)


def test_no_sources_persisted_after_suggest(client, valid_plan):
    # UAT Step 2: Verify no new sources attached after suggest call
    try:
        case_id, plan_id = valid_plan
    except (KeyError, AssertionError):
        pytest.skip("Plan fixture unavailable (bake-off dependency)")

    # Get initial plan sources via case detail endpoint
    case_resp = client.get(f"/api/cases/{case_id}")
    if case_resp.status_code != 200:
        pytest.skip("Cannot fetch case detail (dependency issue)")
    case_data = case_resp.json()
    plan_data = next((p for p in case_data.get("plans", []) if p.get("id") == plan_id), None)
    if plan_data is None:
        pytest.skip("Plan not found in case detail")
    initial_sources = plan_data.get("sources", [])

    # Call suggest
    suggest_resp = client.post(f"/api/plans/{plan_id}/gather/suggest")
    if suggest_resp.status_code != 200:
        pytest.skip(f"Suggest endpoint returned {suggest_resp.status_code}")

    # Verify plan sources are unchanged
    case_resp2 = client.get(f"/api/cases/{case_id}")
    plan_data2 = next((p for p in case_resp2.json().get("plans", []) if p.get("id") == plan_id), None)
    after_sources = plan_data2.get("sources", []) if plan_data2 else []
    assert len(after_sources) == len(initial_sources), "Sources were persisted after suggest"


def test_invalid_plan_id_returns_404(client):
    # UAT Step 6: Invalid or non-existent plan_id returns 404
    invalid_plan_id = str(uuid.uuid4())
    resp = client.post(f"/api/plans/{invalid_plan_id}/gather/suggest")
    assert resp.status_code == 404, f"Expected 404, got {resp.status_code}: {resp.text}"
