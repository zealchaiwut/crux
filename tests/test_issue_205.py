"""Tests for issue #205: Add a claim-verification endpoint for the hub.

AC coverage:
  AC1 – endpoint accepts claim + optional structured context and returns sources
         with citations, URLs, and support_status
  AC2 – context is typed JSON (not a free-text blob); numeric values and nested
         keys are preserved exactly as submitted
  AC3 – verification result is persisted; the same claim returns cached=True
         on the second call without re-running research
  AC4 – integration test submits a claim with sample hub-shaped context and
         asserts that cited sources come back in the response
"""
import json
import os
import uuid
from unittest.mock import AsyncMock, patch

import pytest

os.environ.setdefault("AUTH_SECRET", "test_auth_secret_12345678901")

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_SAMPLE_SOURCES = [
    {
        "title": "VO2 Max Study 2023",
        "url": "https://example.com/vo2max",
        "citation": "Smith et al. (2023)",
        "support_status": "supports",
    },
    {
        "title": "Step Count Meta-Analysis",
        "url": "https://example.com/steps",
        "citation": "Jones et al. (2022)",
        "support_status": "partial",
    },
]

_HUB_CONTEXT = {
    "subject": "athlete-performance",
    "domain": "sports-science",
    "training_figures": {"weekly_km": 80, "resting_hr": 48},
    "performance_figures": {"vo2_max_baseline": 58.3},
}


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


# ---------------------------------------------------------------------------
# AC1: endpoint exists and returns sources with required fields
# ---------------------------------------------------------------------------

def test_verify_claim_endpoint_exists(api_client):
    """AC1: POST /api/hub/verify-claim must exist and return 200."""
    with patch(
        "app.routers.hub.gather_sources_for_claim",
        new_callable=AsyncMock,
        return_value=_SAMPLE_SOURCES,
    ):
        r = api_client.post(
            "/api/hub/verify-claim",
            json={"claim": "Running 10k steps/day improves VO2 max."},
        )
    assert r.status_code == 200, r.text


def test_verify_claim_returns_sources(api_client):
    """AC1: Response must include a 'sources' list with title, url, citation, support_status."""
    with patch(
        "app.routers.hub.gather_sources_for_claim",
        new_callable=AsyncMock,
        return_value=_SAMPLE_SOURCES,
    ):
        r = api_client.post(
            "/api/hub/verify-claim",
            json={"claim": "Running 10k steps/day improves VO2 max."},
        )
    assert r.status_code == 200, r.text
    data = r.json()
    assert "sources" in data
    assert len(data["sources"]) == 2
    src = data["sources"][0]
    assert "title" in src
    assert "url" in src
    assert "citation" in src
    assert "support_status" in src


def test_verify_claim_returns_verification_id(api_client):
    """AC1/AC3: Response must include a verification_id for later retrieval."""
    with patch(
        "app.routers.hub.gather_sources_for_claim",
        new_callable=AsyncMock,
        return_value=_SAMPLE_SOURCES,
    ):
        r = api_client.post(
            "/api/hub/verify-claim",
            json={"claim": "Running 10k steps/day improves VO2 max."},
        )
    assert r.status_code == 200, r.text
    data = r.json()
    assert "verification_id" in data
    assert data["verification_id"]  # non-empty string


def test_verify_claim_missing_claim_returns_422(api_client):
    """AC1: Missing 'claim' field returns 422."""
    r = api_client.post("/api/hub/verify-claim", json={})
    assert r.status_code == 422


def test_verify_claim_empty_claim_returns_422(api_client):
    """AC1: Empty 'claim' string returns 422."""
    r = api_client.post("/api/hub/verify-claim", json={"claim": ""})
    assert r.status_code == 422


# ---------------------------------------------------------------------------
# AC2: context is typed JSON — numeric values and nested keys preserved
# ---------------------------------------------------------------------------

def test_verify_claim_accepts_typed_context(api_client):
    """AC2: Optional 'context' field accepts arbitrary typed JSON (numbers, nested dicts)."""
    with patch(
        "app.routers.hub.gather_sources_for_claim",
        new_callable=AsyncMock,
        return_value=_SAMPLE_SOURCES,
    ):
        r = api_client.post(
            "/api/hub/verify-claim",
            json={
                "claim": "Daily step count improves cardiovascular fitness.",
                "context": _HUB_CONTEXT,
            },
        )
    assert r.status_code == 200, r.text


def test_verify_claim_context_passed_to_gather(api_client):
    """AC2: The context dict is forwarded verbatim to the gather function."""
    mock_gather = AsyncMock(return_value=_SAMPLE_SOURCES)
    with patch("app.routers.hub.gather_sources_for_claim", mock_gather):
        api_client.post(
            "/api/hub/verify-claim",
            json={
                "claim": "Strength training raises resting metabolic rate.",
                "context": _HUB_CONTEXT,
            },
        )
    mock_gather.assert_called_once()
    _, kwargs = mock_gather.call_args
    assert kwargs.get("context") == _HUB_CONTEXT or mock_gather.call_args[0][1] == _HUB_CONTEXT


def test_verify_claim_works_without_context(api_client):
    """AC2: context is optional — omitting it must not cause errors."""
    with patch(
        "app.routers.hub.gather_sources_for_claim",
        new_callable=AsyncMock,
        return_value=_SAMPLE_SOURCES,
    ):
        r = api_client.post(
            "/api/hub/verify-claim",
            json={"claim": "Sleep deprivation impairs reaction time."},
        )
    assert r.status_code == 200, r.text


# ---------------------------------------------------------------------------
# AC3: verification result persisted and retrievable; same claim → cached
# ---------------------------------------------------------------------------

def test_verify_claim_first_call_not_cached(api_client):
    """AC3: First verification call returns cached=False."""
    with patch(
        "app.routers.hub.gather_sources_for_claim",
        new_callable=AsyncMock,
        return_value=_SAMPLE_SOURCES,
    ):
        r = api_client.post(
            "/api/hub/verify-claim",
            json={"claim": "Protein intake boosts muscle synthesis."},
        )
    assert r.status_code == 200, r.text
    assert r.json()["cached"] is False


def test_verify_claim_second_call_is_cached(api_client):
    """AC3: Second call with the same claim returns cached=True without re-running research."""
    mock_gather = AsyncMock(return_value=_SAMPLE_SOURCES)
    with patch("app.routers.hub.gather_sources_for_claim", mock_gather):
        api_client.post(
            "/api/hub/verify-claim",
            json={"claim": "Protein intake boosts muscle synthesis cached test."},
        )
        r2 = api_client.post(
            "/api/hub/verify-claim",
            json={"claim": "Protein intake boosts muscle synthesis cached test."},
        )
    assert r2.status_code == 200, r2.text
    assert r2.json()["cached"] is True
    # gather should only have been called once
    assert mock_gather.call_count == 1


def test_verify_claim_cached_sources_match_original(api_client):
    """AC3: Cached result returns the same sources as the original verification."""
    with patch(
        "app.routers.hub.gather_sources_for_claim",
        new_callable=AsyncMock,
        return_value=_SAMPLE_SOURCES,
    ):
        r1 = api_client.post(
            "/api/hub/verify-claim",
            json={"claim": "Cold exposure increases brown fat activation."},
        )
        r2 = api_client.post(
            "/api/hub/verify-claim",
            json={"claim": "Cold exposure increases brown fat activation."},
        )
    assert r1.json()["sources"] == r2.json()["sources"]


def test_verify_claim_retrievable_by_id(api_client):
    """AC3: A verification result can be retrieved by ID via GET."""
    with patch(
        "app.routers.hub.gather_sources_for_claim",
        new_callable=AsyncMock,
        return_value=_SAMPLE_SOURCES,
    ):
        r_post = api_client.post(
            "/api/hub/verify-claim",
            json={"claim": "Intermittent fasting reduces insulin resistance."},
        )
    vid = r_post.json()["verification_id"]
    r_get = api_client.get(f"/api/hub/verify-claim/{vid}")
    assert r_get.status_code == 200, r_get.text
    data = r_get.json()
    assert data["verification_id"] == vid
    assert "sources" in data


def test_verify_claim_get_unknown_id_returns_404(api_client):
    """AC3: GET with unknown verification_id returns 404."""
    r = api_client.get(
        "/api/hub/verify-claim/00000000-0000-0000-0000-000000000000"
    )
    assert r.status_code == 404


# ---------------------------------------------------------------------------
# AC4: integration test — hub-shaped context, cited sources come back
# ---------------------------------------------------------------------------

def test_hub_shaped_context_returns_cited_sources(api_client):
    """AC4: Submitting a claim with hub-shaped context returns sources with non-empty citations."""
    with patch(
        "app.routers.hub.gather_sources_for_claim",
        new_callable=AsyncMock,
        return_value=_SAMPLE_SOURCES,
    ):
        r = api_client.post(
            "/api/hub/verify-claim",
            json={
                "claim": (
                    "Athletes running 80 km/week with a resting HR of 48 bpm "
                    "and VO2 max of 58 mL/kg/min can improve performance by "
                    "adding 10k daily steps."
                ),
                "context": _HUB_CONTEXT,
            },
        )
    assert r.status_code == 200, r.text
    data = r.json()
    assert "sources" in data
    assert len(data["sources"]) > 0
    for src in data["sources"]:
        assert src.get("citation"), f"Missing citation on source: {src}"
        assert src.get("url"), f"Missing URL on source: {src}"
        assert src.get("support_status"), f"Missing support_status on source: {src}"


def test_hub_context_numeric_values_are_preserved_in_persistence(api_client, db_session):
    """AC4/AC2: Numeric context values are stored and returned intact (not stringified)."""
    from app import models

    with patch(
        "app.routers.hub.gather_sources_for_claim",
        new_callable=AsyncMock,
        return_value=_SAMPLE_SOURCES,
    ):
        r = api_client.post(
            "/api/hub/verify-claim",
            json={
                "claim": "Numeric context preservation test.",
                "context": {"steps_per_day": 10000, "weeks": 12, "improvement": 0.15},
            },
        )
    assert r.status_code == 200, r.text
    vid = r.json()["verification_id"]
    db_session.expire_all()
    row = db_session.query(models.ClaimVerification).filter_by(id=vid).first()
    assert row is not None
    ctx = row.context_json
    assert ctx["steps_per_day"] == 10000
    assert ctx["improvement"] == 0.15
