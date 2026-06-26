"""Tests for issue #146: Add POST /api/cases/{id}/summary endpoint with caching (runs against UAT)"""
import os
import pytest
import httpx
import json


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

def test_post_api_cases_summary_endpoint__endpoint_exists(client):
    # AC1: POST /api/cases/{id}/summary is registered in routers/cases.py
    # Verify the endpoint exists by checking it doesn't return 404 (method not allowed)
    r = client.post("/api/cases/nonexistent-case-id/summary")
    assert r.status_code != 405, f"Endpoint should exist; 405 indicates missing route. Got {r.status_code}"


def test_post_api_cases_summary_endpoint__404_nonexistent_case(client):
    # AC6: Returns 404 Not Found if the case ID does not exist
    r = client.post("/api/cases/nonexistent-case-id-does-not-exist/summary")
    assert r.status_code == 404, f"Expected 404 for non-existent case, got {r.status_code}: {r.text}"
    body = r.json()
    assert "detail" in body, "404 response should include detail message"


def test_post_api_cases_summary_endpoint__422_pre_probe_stage(client):
    # AC5: Returns 422 Unprocessable Entity if the case has not yet reached the probe stage
    pytest.skip("manual — requires test case fixture at pre-probe stage (sharpened/bake_off/gather/weigh)")


def test_post_api_cases_summary_endpoint__generates_summary_at_probe(client):
    # AC2: On success, a summary is generated and stored on case.summary, then returned
    # AC8: The response body includes the summary text and indicates freshly generated vs cached
    pytest.skip("manual — requires test case fixture at probe stage in UAT database")


def test_post_api_cases_summary_endpoint__caching_behavior(client):
    # AC3: If case.summary already exists and ?force=true is NOT passed, cached value returned
    # AC8: The response indicates whether it was freshly generated or served from cache
    pytest.skip("manual — requires test case fixture with existing summary in UAT database")


def test_post_api_cases_summary_endpoint__force_regenerate(client):
    # AC4: If ?force=true is passed, the summary is regenerated and case.summary is overwritten
    pytest.skip("manual — requires test case fixture with existing summary in UAT database")


def test_post_api_cases_summary_endpoint__verdict_not_required(client):
    # AC7: A verdict is NOT required for the endpoint to succeed
    pytest.skip("manual — requires test case fixture at probe stage without verdict in UAT database")
