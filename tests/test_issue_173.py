"""Tests for issue #173: Rewrite case summary as cited literature-review JSON.

AC coverage:
  AC1  – generate_summary produces 3–4 paragraph narrative with inline [N] citations
  AC2  – Returns JSON with paragraphs (array of strings) and references (array of objects
          each with id, source_id, title, url)
  AC3  – All references[].source_id map to actual sources; phantom source_ids raise SummaryError
  AC4  – Case.summary stores the new JSON as text
  AC5  – GET /api/cases/{id}/summary deserialises and returns the JSON structure
  AC6  – GET /api/cases/{id}/summary?force=true discards cache and regenerates
  AC7  – Returns HTTP 422 when case has not yet reached probe stage
  AC8  – references[].id values match every [N] citation marker present in paragraphs;
          mismatched citations raise SummaryError
  AC9  – Stage gate rejects requests before probe with 422
  AC10 – Existing tests updated: summary endpoint uses GET and returns new format
"""
import json
import os
import re
import uuid
from unittest.mock import AsyncMock, patch

import pytest

os.environ.setdefault("AUTH_SECRET", "test_auth_secret_12345678901")
os.environ.setdefault("CRUX_REQUIRE_AUTH", "1")


# ---------------------------------------------------------------------------
# Helpers / fixtures
# ---------------------------------------------------------------------------

def _make_db():
    from sqlalchemy import create_engine
    from sqlalchemy.pool import StaticPool
    from app.models import Base

    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    return engine


@pytest.fixture()
def db_session():
    engine = _make_db()
    from sqlalchemy.orm import sessionmaker

    Session = sessionmaker(bind=engine)
    session = Session()
    yield session
    session.close()
    engine.dispose()


@pytest.fixture()
def api_client(db_session):
    from app.main import app
    from app.db import get_db
    from app.auth import create_session_cookie
    from app.config import AUTH_SECRET
    from fastapi.testclient import TestClient

    def _override():
        yield db_session

    app.dependency_overrides[get_db] = _override
    tc = TestClient(app)
    tc.cookies.set("session", create_session_cookie(AUTH_SECRET))
    yield tc
    app.dependency_overrides.pop(get_db, None)


def _seed_case(session, stage: str = "probe", with_sources: bool = True):
    from app import models

    src_id_a = str(uuid.uuid4())
    src_id_b = str(uuid.uuid4())

    c = models.Case(
        id=str(uuid.uuid4()),
        raw_problem="Why did our retention drop?",
        sharpened="User retention dropped 20% after the pricing change.",
        stage=stage,
    )
    session.add(c)
    session.flush()

    plan_a = models.Plan(
        id=str(uuid.uuid4()),
        case_id=c.id,
        label="A",
        name="Price sensitivity",
        mechanism="Users left because the new price exceeded their perceived value.",
        current_rank=1,
    )
    session.add(plan_a)
    session.flush()

    plan_b = models.Plan(
        id=str(uuid.uuid4()),
        case_id=c.id,
        label="B",
        name="Feature gap",
        mechanism="Users left because a competitor offers a missing feature.",
        current_rank=2,
    )
    session.add(plan_b)
    session.flush()

    if with_sources:
        src_a = models.Source(
            id=src_id_a,
            plan_id=plan_a.id,
            kind="article",
            title="Price Elasticity Study Q1",
            url="https://example.com/price-study",
            claim="60% of churned users cited price as the primary reason.",
        )
        src_b = models.Source(
            id=src_id_b,
            plan_id=plan_b.id,
            kind="article",
            title="Competitor Analysis Report",
            url="https://example.com/competitor",
            claim="Rival launched a key feature in Q4.",
        )
        session.add_all([src_a, src_b])
        session.flush()

    session.commit()
    return c, src_id_a, src_id_b


def _make_mock_summary(src_id_a: str, src_id_b: str) -> str:
    return json.dumps({
        "paragraphs": [
            f"The retention drop coincides with the pricing change [1]. This hypothesis is strongly supported by survey data.",
            f"A secondary factor is the competitive landscape [2]. A rival launched a key feature in Q4.",
            f"Taken together, the evidence points primarily to price sensitivity [1] as the root cause.",
        ],
        "references": [
            {"id": 1, "source_id": src_id_a, "title": "Price Elasticity Study Q1", "url": "https://example.com/price-study"},
            {"id": 2, "source_id": src_id_b, "title": "Competitor Analysis Report", "url": "https://example.com/competitor"},
        ],
    })


# ---------------------------------------------------------------------------
# AC1 + AC2 (unit): generate_summary returns paragraphs and references structure
# ---------------------------------------------------------------------------

def test_generate_summary_returns_paragraphs_and_references():
    """AC1/AC2: generate_summary must return JSON with paragraphs (3-4) and references."""
    src_id = str(uuid.uuid4())
    mock_response = json.dumps({
        "paragraphs": [
            "Retention dropped after pricing changes [1]. The evidence is clear.",
            "Survey data confirms [1] price was the dominant factor.",
            "This synthesis leads to a clear recommendation.",
        ],
        "references": [
            {"id": 1, "source_id": src_id, "title": "Price Study", "url": "https://example.com"},
        ],
    })

    case_data = {
        "sharpened": "Why did retention drop?",
        "plans": [
            {
                "label": "A",
                "name": "Price sensitivity",
                "mechanism": "Price exceeded perceived value.",
                "current_rank": 1,
                "sources": [
                    {"id": src_id, "title": "Price Study", "url": "https://example.com", "claim": "Price was key."},
                ],
            }
        ],
    }

    from unittest.mock import AsyncMock, patch
    import asyncio

    async def run():
        with patch("app.summary.complete", new_callable=AsyncMock, return_value=mock_response):
            from app.summary import generate_summary
            return await generate_summary(case_data)

    result_json = asyncio.get_event_loop().run_until_complete(run())
    data = json.loads(result_json)

    assert "paragraphs" in data, "Result must have 'paragraphs' key"
    assert "references" in data, "Result must have 'references' key"
    assert isinstance(data["paragraphs"], list), "paragraphs must be a list"
    assert 3 <= len(data["paragraphs"]) <= 4, f"paragraphs must have 3-4 items; got {len(data['paragraphs'])}"
    assert isinstance(data["references"], list), "references must be a list"


def test_generate_summary_references_have_required_fields():
    """AC2: Each reference object must have id, source_id, title, url."""
    src_id = str(uuid.uuid4())
    mock_response = json.dumps({
        "paragraphs": [
            "The evidence shows price sensitivity [1].",
            "Further analysis confirms [1] the trend.",
            "This is a decisive finding.",
        ],
        "references": [
            {"id": 1, "source_id": src_id, "title": "Study", "url": "https://example.com"},
        ],
    })

    case_data = {
        "sharpened": "Why did retention drop?",
        "plans": [{"label": "A", "name": "P", "mechanism": "m", "current_rank": 1,
                   "sources": [{"id": src_id, "title": "Study", "url": "https://example.com", "claim": "c"}]}],
    }

    import asyncio
    async def run():
        with patch("app.summary.complete", new_callable=AsyncMock, return_value=mock_response):
            from app.summary import generate_summary
            return await generate_summary(case_data)

    result_json = asyncio.get_event_loop().run_until_complete(run())
    data = json.loads(result_json)

    for ref in data["references"]:
        for field in ("id", "source_id", "title", "url"):
            assert field in ref, f"Reference must have '{field}'; got keys: {list(ref)}"
        assert isinstance(ref["id"], int), f"reference id must be an int; got {type(ref['id'])}"


# ---------------------------------------------------------------------------
# AC3: Phantom citation validation (source_id not on case)
# ---------------------------------------------------------------------------

def test_generate_summary_rejects_phantom_source_id():
    """AC3: generate_summary must raise SummaryError when a reference source_id is not a real source."""
    real_src_id = str(uuid.uuid4())
    phantom_src_id = str(uuid.uuid4())

    mock_response = json.dumps({
        "paragraphs": [
            "Analysis shows [1] the trend.",
            "Further detail confirms [1].",
            "Conclusion follows.",
        ],
        "references": [
            {"id": 1, "source_id": phantom_src_id, "title": "Ghost Source", "url": "https://ghost.com"},
        ],
    })

    case_data = {
        "sharpened": "Problem",
        "plans": [{"label": "A", "name": "P", "mechanism": "m", "current_rank": 1,
                   "sources": [{"id": real_src_id, "title": "Real Source", "url": "https://real.com", "claim": "c"}]}],
    }

    import asyncio
    from app.summary import SummaryError

    async def run():
        with patch("app.summary.complete", new_callable=AsyncMock, return_value=mock_response):
            from app.summary import generate_summary
            return await generate_summary(case_data)

    with pytest.raises(SummaryError, match="source_id"):
        asyncio.get_event_loop().run_until_complete(run())


# ---------------------------------------------------------------------------
# AC8: Citation markers in paragraphs match reference ids
# ---------------------------------------------------------------------------

def test_generate_summary_rejects_unmatched_citation_markers():
    """AC8: generate_summary must raise SummaryError when [N] marker has no matching reference id."""
    src_id = str(uuid.uuid4())

    # Paragraph cites [2] but references only has id 1
    mock_response = json.dumps({
        "paragraphs": [
            "Evidence shows [1] the main cause.",
            "Additional data points to [2] another factor.",  # [2] has no reference
            "Conclusion based on the above.",
        ],
        "references": [
            {"id": 1, "source_id": src_id, "title": "Study", "url": "https://example.com"},
        ],
    })

    case_data = {
        "sharpened": "Problem",
        "plans": [{"label": "A", "name": "P", "mechanism": "m", "current_rank": 1,
                   "sources": [{"id": src_id, "title": "Study", "url": "https://example.com", "claim": "c"}]}],
    }

    import asyncio
    from app.summary import SummaryError

    async def run():
        with patch("app.summary.complete", new_callable=AsyncMock, return_value=mock_response):
            from app.summary import generate_summary
            return await generate_summary(case_data)

    with pytest.raises(SummaryError):
        asyncio.get_event_loop().run_until_complete(run())


def test_generate_summary_citation_markers_match_references():
    """AC8: All [N] markers in paragraphs must have matching reference ids."""
    src_id_a = str(uuid.uuid4())
    src_id_b = str(uuid.uuid4())

    mock_response = json.dumps({
        "paragraphs": [
            "First finding [1] shows X.",
            "Second finding [2] reveals Y.",
            "Both [1] and [2] together point to the same root cause.",
        ],
        "references": [
            {"id": 1, "source_id": src_id_a, "title": "Source A", "url": "https://a.com"},
            {"id": 2, "source_id": src_id_b, "title": "Source B", "url": "https://b.com"},
        ],
    })

    case_data = {
        "sharpened": "Problem",
        "plans": [
            {"label": "A", "name": "P", "mechanism": "m", "current_rank": 1,
             "sources": [
                 {"id": src_id_a, "title": "Source A", "url": "https://a.com", "claim": "c"},
                 {"id": src_id_b, "title": "Source B", "url": "https://b.com", "claim": "c"},
             ]},
        ],
    }

    import asyncio
    async def run():
        with patch("app.summary.complete", new_callable=AsyncMock, return_value=mock_response):
            from app.summary import generate_summary
            return await generate_summary(case_data)

    result_json = asyncio.get_event_loop().run_until_complete(run())
    data = json.loads(result_json)

    # Collect all [N] markers from paragraphs
    markers_in_paragraphs = set()
    for para in data["paragraphs"]:
        for m in re.findall(r'\[(\d+)\]', para):
            markers_in_paragraphs.add(int(m))

    ref_ids = {r["id"] for r in data["references"]}
    assert markers_in_paragraphs == ref_ids, (
        f"Citation markers in paragraphs {sorted(markers_in_paragraphs)} "
        f"must match reference ids {sorted(ref_ids)}"
    )


# ---------------------------------------------------------------------------
# AC5 + AC7: GET endpoint, stage gate (422)
# ---------------------------------------------------------------------------

def test_get_summary_endpoint_returns_200(api_client, db_session):
    """AC5: GET /api/cases/{id}/summary must return 200 for a probe-stage case."""
    c, src_id_a, src_id_b = _seed_case(db_session, stage="probe")
    mock_summary = _make_mock_summary(src_id_a, src_id_b)

    with patch("app.routers.cases.generate_summary", new_callable=AsyncMock, return_value=mock_summary):
        r = api_client.get(f"/api/cases/{c.id}/summary")

    assert r.status_code == 200, f"Expected 200; got {r.status_code}: {r.text}"
    data = r.json()
    assert "paragraphs" in data, f"Response must contain 'paragraphs'; got: {list(data)}"
    assert "references" in data, f"Response must contain 'references'; got: {list(data)}"


def test_get_summary_response_structure(api_client, db_session):
    """AC5: GET response must have paragraphs (list) and references (list of objects)."""
    c, src_id_a, src_id_b = _seed_case(db_session, stage="probe")
    mock_summary = _make_mock_summary(src_id_a, src_id_b)

    with patch("app.routers.cases.generate_summary", new_callable=AsyncMock, return_value=mock_summary):
        r = api_client.get(f"/api/cases/{c.id}/summary")

    assert r.status_code == 200
    data = r.json()
    assert isinstance(data["paragraphs"], list), "paragraphs must be a list"
    assert len(data["paragraphs"]) >= 1, "paragraphs must be non-empty"
    for ref in data["references"]:
        for field in ("id", "source_id", "title", "url"):
            assert field in ref, f"Reference missing '{field}'; got: {list(ref)}"


@pytest.mark.parametrize("stage", ["sharpened", "bake_off", "gather", "weigh"])
def test_stage_gate_returns_422_for_pre_probe(api_client, db_session, stage):
    """AC7/AC9: GET /api/cases/{id}/summary must return 422 for stages before probe."""
    c, _, _ = _seed_case(db_session, stage=stage)
    r = api_client.get(f"/api/cases/{c.id}/summary")
    assert r.status_code == 422, (
        f"Expected 422 for stage={stage!r}; got {r.status_code}: {r.text}"
    )
    body = r.json()
    assert "detail" in body, "422 response must include a 'detail' message"
    detail = body["detail"].lower()
    assert "probe" in detail or "stage" in detail, (
        f"Error message must mention the stage requirement; got: {body['detail']!r}"
    )


def test_stage_gate_allows_probe_stage(api_client, db_session):
    """AC9: GET /api/cases/{id}/summary must succeed for cases at the probe stage."""
    c, src_id_a, src_id_b = _seed_case(db_session, stage="probe")
    mock_summary = _make_mock_summary(src_id_a, src_id_b)

    with patch("app.routers.cases.generate_summary", new_callable=AsyncMock, return_value=mock_summary):
        r = api_client.get(f"/api/cases/{c.id}/summary")

    assert r.status_code == 200, f"probe stage must return 200; got {r.status_code}: {r.text}"


def test_stage_gate_allows_verdict_stage(api_client, db_session):
    """AC9: GET /api/cases/{id}/summary must succeed for cases at the verdict stage."""
    c, src_id_a, src_id_b = _seed_case(db_session, stage="verdict")
    mock_summary = _make_mock_summary(src_id_a, src_id_b)

    with patch("app.routers.cases.generate_summary", new_callable=AsyncMock, return_value=mock_summary):
        r = api_client.get(f"/api/cases/{c.id}/summary")

    assert r.status_code == 200, f"verdict stage must return 200; got {r.status_code}: {r.text}"


# ---------------------------------------------------------------------------
# AC6: force=true discards cache and regenerates
# ---------------------------------------------------------------------------

def test_cache_hit_does_not_call_claude(api_client, db_session):
    """AC6: Second GET without force=true must return cached value without calling Claude."""
    c, src_id_a, src_id_b = _seed_case(db_session, stage="probe")
    mock_summary = _make_mock_summary(src_id_a, src_id_b)
    call_count = 0

    async def _mock_gen(case_data):
        nonlocal call_count
        call_count += 1
        return mock_summary

    with patch("app.routers.cases.generate_summary", side_effect=_mock_gen):
        r1 = api_client.get(f"/api/cases/{c.id}/summary")
        r2 = api_client.get(f"/api/cases/{c.id}/summary")

    assert r1.status_code == 200
    assert r2.status_code == 200
    assert call_count == 1, f"Claude must be called only once; called {call_count} times"
    d1, d2 = r1.json(), r2.json()
    assert d1["paragraphs"] == d2["paragraphs"], "Cached paragraphs must match first response"
    assert d1["references"] == d2["references"], "Cached references must match first response"


def test_force_true_regenerates_summary(api_client, db_session):
    """AC6: GET ?force=true must discard cache and call Claude again."""
    c, src_id_a, src_id_b = _seed_case(db_session, stage="probe")
    mock_summary = _make_mock_summary(src_id_a, src_id_b)
    call_count = 0

    async def _mock_gen(case_data):
        nonlocal call_count
        call_count += 1
        return mock_summary

    with patch("app.routers.cases.generate_summary", side_effect=_mock_gen):
        r1 = api_client.get(f"/api/cases/{c.id}/summary")
        r2 = api_client.get(f"/api/cases/{c.id}/summary?force=true")

    assert r1.status_code == 200
    assert r2.status_code == 200
    assert call_count == 2, f"Claude must be called twice when force=true; called {call_count} times"


# ---------------------------------------------------------------------------
# AC4: Case.summary stores the new JSON format as text
# ---------------------------------------------------------------------------

def test_summary_stored_as_json_with_new_format(api_client, db_session):
    """AC4: After GET /summary, Case.summary must contain JSON with paragraphs and references."""
    c, src_id_a, src_id_b = _seed_case(db_session, stage="probe")
    mock_summary = _make_mock_summary(src_id_a, src_id_b)

    async def _mock_gen(case_data):
        return mock_summary

    with patch("app.routers.cases.generate_summary", side_effect=_mock_gen):
        r = api_client.get(f"/api/cases/{c.id}/summary")

    assert r.status_code == 200

    db_session.expire_all()
    from app import models
    updated = db_session.get(models.Case, c.id)
    assert updated.summary is not None, "case.summary must be non-null after generation"

    stored = json.loads(updated.summary)
    assert "paragraphs" in stored, f"Stored summary must have 'paragraphs'; got: {list(stored)}"
    assert "references" in stored, f"Stored summary must have 'references'; got: {list(stored)}"


def test_summary_stored_as_valid_json_not_plain_text(api_client, db_session):
    """AC4: case.summary column must contain valid JSON, not plain text."""
    c, src_id_a, src_id_b = _seed_case(db_session, stage="probe")
    mock_summary = _make_mock_summary(src_id_a, src_id_b)

    async def _mock_gen(case_data):
        return mock_summary

    with patch("app.routers.cases.generate_summary", side_effect=_mock_gen):
        api_client.get(f"/api/cases/{c.id}/summary")

    db_session.expire_all()
    from app import models
    updated = db_session.get(models.Case, c.id)

    try:
        parsed = json.loads(updated.summary)
    except (json.JSONDecodeError, TypeError) as e:
        pytest.fail(f"case.summary must be valid JSON; got error: {e}")

    assert isinstance(parsed, dict), f"Parsed summary must be a dict; got {type(parsed)}"


# ---------------------------------------------------------------------------
# AC5: GET endpoint exists (not POST)
# ---------------------------------------------------------------------------

def test_get_endpoint_exists_not_post(api_client, db_session):
    """AC5: The summary endpoint must be a GET (not POST) endpoint."""
    c, _, _ = _seed_case(db_session, stage="probe")
    # POST should return 405 Method Not Allowed
    r = api_client.post(f"/api/cases/{c.id}/summary")
    assert r.status_code == 405, (
        f"POST to summary endpoint must return 405 (Method Not Allowed) since it is now a GET; "
        f"got {r.status_code}: {r.text}"
    )


def test_get_returns_404_for_nonexistent_case(api_client):
    """AC5: Must return 404 when the case ID does not exist."""
    r = api_client.get(f"/api/cases/{uuid.uuid4()}/summary")
    assert r.status_code == 404, f"Expected 404 for non-existent case; got {r.status_code}: {r.text}"


# ---------------------------------------------------------------------------
# generate_summary: no sources case
# ---------------------------------------------------------------------------

def test_generate_summary_no_sources():
    """generate_summary handles a case with no sources (empty references list)."""
    mock_response = json.dumps({
        "paragraphs": [
            "No evidence sources are available yet.",
            "The investigation is in its early stages.",
            "Further sources are needed to draw conclusions.",
        ],
        "references": [],
    })

    case_data = {
        "sharpened": "Problem with no sources",
        "plans": [{"label": "A", "name": "P", "mechanism": "m", "current_rank": 1, "sources": []}],
    }

    import asyncio
    async def run():
        with patch("app.summary.complete", new_callable=AsyncMock, return_value=mock_response):
            from app.summary import generate_summary
            return await generate_summary(case_data)

    result_json = asyncio.get_event_loop().run_until_complete(run())
    data = json.loads(result_json)
    assert "paragraphs" in data
    assert "references" in data
    assert data["references"] == []
