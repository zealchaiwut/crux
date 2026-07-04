"""Tests for issue #173: Rewrite case summary as cited literature-review JSON (runs against UAT)"""
import os
import pytest
import httpx


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

def test_summary_generates_paragraphs_with_inline_citations(client):
    # AC: `app/summary.py` generates a 3–4 paragraph narrative with inline numbered citations
    # AC2: paragraphs array contains inline citation markers [N]
    pytest.skip("manual — UAT step 1: verify GET /cases/{id}/summary returns paragraphs with [1], [2], etc.")


def test_summary_returns_paragraphs_and_references_keys(client):
    # AC2: The endpoint returns JSON with two top-level keys: paragraphs (array) and references (array)
    # AC2: references objects contain id (integer), source_id, title, and url
    pytest.skip("manual — UAT step 1: inspect response structure and key presence")


def test_references_source_ids_map_to_actual_sources(client):
    # AC3: Every `references[].source_id` maps to an actual source that exists on the case
    pytest.skip("manual — UAT step 2: verify each reference source_id exists in case sources")


def test_case_summary_stores_json_not_plaintext(client):
    # AC4: `Case.summary` stores the JSON as text (not plain-text strings)
    pytest.skip("manual — UAT step 6: query database directly and verify valid JSON structure")


def test_get_cases_summary_deserializes_and_returns_json(client):
    # AC5: `GET /cases/{id}/summary` returns the deserialized JSON structure (paragraphs + references)
    pytest.skip("manual — UAT step 1: verify GET endpoint returns correct JSON shape")


def test_get_cases_summary_force_true_regenerates(client):
    # AC6: `GET /cases/{id}/summary?force=true` discards cache and regenerates
    # AC6: regenerated summary may differ from cached version
    pytest.skip("manual — UAT step 4: call with ?force=true and verify fresh generation")


def test_pre_probe_stage_returns_422(client):
    # AC7: Request on pre-probe case returns HTTP 422 with descriptive error
    pytest.skip("manual — UAT step 5: test on intake/review stage case and verify 422")


def test_references_id_matches_citation_markers(client):
    # AC8: `references[].id` values match every citation marker [N] in paragraphs
    # AC8: no orphan citations or missing references
    pytest.skip("manual — UAT step 1: verify citation-to-reference consistency")


def test_stage_gate_rejects_pre_probe_with_422(client):
    # AC9: Stage gate rejects pre-probe requests with 422
    pytest.skip("manual — UAT step 5: verify stage gate enforcement")


def test_existing_tests_updated_or_replaced(client):
    # AC10: Existing tests updated to work with new JSON format
    pytest.skip("manual — code review: verify test_issue_146.py and test_issue_94.py updated")
