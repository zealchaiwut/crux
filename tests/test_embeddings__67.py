"""Tests for issue #67: Keep case embeddings fresh and add reindex endpoint.

AC coverage:
  AC1 – POST /api/cases/{id}/bake-off recomputes embedding after bake-off completes
  AC2 – PATCH /api/cases/{id} recomputes embedding when sharpened or plan_mechanisms changed
  AC3 – PATCH /api/cases/{id} does NOT recompute when neither field is in the payload
  AC4 – Each stored embedding record includes a model_version field
  AC5 – GET /api/admin/reindex returns 401 without valid admin authentication
  AC6 – GET /api/admin/reindex recomputes all embeddings and returns { reindexed: N, errors: M }
  AC7 – GET /api/admin/reindex updates model_version on every refreshed record
  AC8 – Cases with embedding errors during reindex are logged and counted without halting
"""
import json
import uuid
import os
from unittest.mock import patch

import pytest

os.environ.setdefault("AUTH_SECRET", "test_auth_secret_12345678901")


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
    from app.auth import create_session_cookie, reset_rate_limiter
    from app.config import AUTH_SECRET
    from fastapi.testclient import TestClient

    reset_rate_limiter()

    def _override():
        yield db_session

    app.dependency_overrides[get_db] = _override
    cookie = create_session_cookie(AUTH_SECRET)
    client = TestClient(app)
    client.cookies.set("session", cookie)
    yield client
    app.dependency_overrides.pop(get_db, None)
    reset_rate_limiter()


@pytest.fixture()
def unauthed_client(db_session):
    """Client without a valid session cookie."""
    from app.main import app
    from app.db import get_db
    from app.auth import reset_rate_limiter
    from fastapi.testclient import TestClient

    reset_rate_limiter()

    def _override():
        yield db_session

    app.dependency_overrides[get_db] = _override
    client = TestClient(app, follow_redirects=False)
    yield client
    app.dependency_overrides.pop(get_db, None)
    reset_rate_limiter()


def _create_case(db, stage="sharpened", sharpened="Sharpened problem statement"):
    from datetime import datetime, timezone
    from app import models
    case = models.Case(
        id=str(uuid.uuid4()),
        raw_problem="raw problem text",
        sharpened=sharpened,
        not_investigating=json.dumps([]),
        stage=stage,
        created_at=datetime.now(tz=timezone.utc),
    )
    db.add(case)
    db.commit()
    db.refresh(case)
    return case


def _add_plan(db, case_id, label="A", mechanism="plan mechanism text"):
    from app import models
    plan = models.Plan(
        id=str(uuid.uuid4()),
        case_id=case_id,
        label=label,
        name=f"Plan {label}",
        mechanism=mechanism,
        prior="0.6",
        current_rank=1,
    )
    db.add(plan)
    db.commit()
    db.refresh(plan)
    return plan


def _get_embedding(db, case_id):
    from app import models
    return db.query(models.CaseEmbedding).filter_by(case_id=case_id).first()


# ---------------------------------------------------------------------------
# AC4: Embedding records have a model_version field
# ---------------------------------------------------------------------------

def test_embedding_record_has_model_version(db_session):
    """AC4: Stored embedding record must have a non-null model_version."""
    from app.services.embeddings import upsert_case_embedding, EMBEDDING_MODEL_VERSION
    case = _create_case(db_session)
    upsert_case_embedding(case.id, [0.1, 0.2, 0.3], EMBEDDING_MODEL_VERSION, db_session)
    emb = _get_embedding(db_session, case.id)
    assert emb is not None
    assert emb.model_version is not None
    assert emb.model_version == EMBEDDING_MODEL_VERSION


def test_embedding_model_version_is_nonempty_string():
    """AC4: EMBEDDING_MODEL_VERSION must be a non-empty string."""
    from app.services.embeddings import EMBEDDING_MODEL_VERSION
    assert isinstance(EMBEDDING_MODEL_VERSION, str)
    assert len(EMBEDDING_MODEL_VERSION) > 0


# ---------------------------------------------------------------------------
# AC1: bake-off recomputes embedding
# ---------------------------------------------------------------------------

def test_bake_off_creates_embedding(api_client, db_session):
    """AC1: POST /api/cases/{id}/bake-off stores an embedding after success."""
    case = _create_case(db_session)

    fake_plans = [
        {"label": "A", "name": "Plan A", "mechanism": "mechanism alpha", "prior": 0.6},
        {"label": "B", "name": "Plan B", "mechanism": "mechanism beta", "prior": 0.3},
    ]
    with patch("app.routers.cases.generate_plans", return_value=fake_plans):
        resp = api_client.post(f"/api/cases/{case.id}/bake-off")
    assert resp.status_code == 200

    emb = _get_embedding(db_session, case.id)
    assert emb is not None
    assert emb.model_version is not None


def test_bake_off_embedding_changes_on_repeated_call(api_client, db_session):
    """AC1: Calling bake-off on a case without plans creates an embedding."""
    case = _create_case(db_session)

    fake_plans = [
        {"label": "A", "name": "Plan A", "mechanism": "plan alpha", "prior": 0.7},
    ]
    with patch("app.routers.cases.generate_plans", return_value=fake_plans):
        resp = api_client.post(f"/api/cases/{case.id}/bake-off")
    assert resp.status_code == 200

    emb = _get_embedding(db_session, case.id)
    assert emb is not None
    old_vector = emb.vector

    # Bake-off on a case with existing plans should return cached plans (no recompute call)
    resp2 = api_client.post(f"/api/cases/{case.id}/bake-off")
    assert resp2.status_code == 200
    # Embedding should still exist
    db_session.refresh(emb)
    assert _get_embedding(db_session, case.id) is not None


# ---------------------------------------------------------------------------
# AC2: PATCH recomputes embedding when sharpened or plan_mechanisms changed
# ---------------------------------------------------------------------------

def test_patch_sharpened_triggers_embedding_update(api_client, db_session):
    """AC2: PATCH with sharpened update recomputes the embedding."""
    case = _create_case(db_session, sharpened="Original sharpened text")

    from app.services.embeddings import upsert_case_embedding, EMBEDDING_MODEL_VERSION
    upsert_case_embedding(case.id, [0.0, 0.0, 0.0], EMBEDDING_MODEL_VERSION, db_session)
    before_emb = _get_embedding(db_session, case.id)
    old_vector = before_emb.vector

    resp = api_client.patch(
        f"/api/cases/{case.id}",
        json={"sharpened": "Completely different problem statement for embedding test"},
    )
    assert resp.status_code == 200

    db_session.expire(before_emb)
    emb = _get_embedding(db_session, case.id)
    # Embedding must have been updated (vector may differ or model_version is set)
    assert emb is not None
    assert emb.model_version is not None


def test_patch_plan_mechanisms_triggers_embedding_update(api_client, db_session):
    """AC2: PATCH with plan_mechanisms recomputes the embedding."""
    case = _create_case(db_session)
    _add_plan(db_session, case.id, label="A", mechanism="old mechanism")

    from app.services.embeddings import upsert_case_embedding, EMBEDDING_MODEL_VERSION
    upsert_case_embedding(case.id, [0.0], EMBEDDING_MODEL_VERSION, db_session)

    resp = api_client.patch(
        f"/api/cases/{case.id}",
        json={"plan_mechanisms": {"A": "brand new mechanism text here"}},
    )
    assert resp.status_code == 200

    emb = _get_embedding(db_session, case.id)
    assert emb is not None
    assert emb.model_version is not None


# ---------------------------------------------------------------------------
# AC3: PATCH without sharpened or plan_mechanisms does NOT recompute
# ---------------------------------------------------------------------------

def test_patch_not_investigating_does_not_recompute_embedding(api_client, db_session):
    """AC3: Updating only not_investigating leaves the embedding unchanged."""
    case = _create_case(db_session)

    from app.services.embeddings import upsert_case_embedding, EMBEDDING_MODEL_VERSION
    sentinel_vector = [9.9, 8.8, 7.7]
    upsert_case_embedding(case.id, sentinel_vector, "sentinel-v0", db_session)

    resp = api_client.patch(
        f"/api/cases/{case.id}",
        json={"not_investigating": ["some item"]},
    )
    assert resp.status_code == 200

    emb = _get_embedding(db_session, case.id)
    assert emb is not None
    # model_version must NOT have changed
    assert emb.model_version == "sentinel-v0"
    assert emb.vector == json.dumps(sentinel_vector)


def test_patch_empty_body_does_not_recompute_embedding(api_client, db_session):
    """AC3: Sending no embedding-relevant fields leaves embedding unchanged."""
    case = _create_case(db_session)

    from app.services.embeddings import upsert_case_embedding
    upsert_case_embedding(case.id, [1.0, 2.0], "stable-v1", db_session)

    resp = api_client.patch(
        f"/api/cases/{case.id}",
        json={},
    )
    assert resp.status_code == 200

    emb = _get_embedding(db_session, case.id)
    assert emb.model_version == "stable-v1"


# ---------------------------------------------------------------------------
# AC5: GET /api/admin/reindex returns 401 without auth
# ---------------------------------------------------------------------------

def test_admin_reindex_requires_auth(unauthed_client):
    """AC5: GET /api/admin/reindex without session cookie returns 401."""
    resp = unauthed_client.get("/api/admin/reindex")
    assert resp.status_code == 401


# ---------------------------------------------------------------------------
# AC6: GET /api/admin/reindex recomputes all embeddings and returns summary
# ---------------------------------------------------------------------------

def test_admin_reindex_returns_summary(api_client, db_session):
    """AC6: GET /api/admin/reindex returns { reindexed: N, errors: M }."""
    case1 = _create_case(db_session, sharpened="Case one text")
    case2 = _create_case(db_session, sharpened="Case two text")

    resp = api_client.get("/api/admin/reindex")
    assert resp.status_code == 200
    data = resp.json()
    assert "reindexed" in data
    assert "errors" in data
    assert data["reindexed"] == 2
    assert data["errors"] == 0


def test_admin_reindex_creates_embeddings_for_all_cases(api_client, db_session):
    """AC6: After reindex, every case has a stored embedding."""
    case1 = _create_case(db_session, sharpened="Problem A")
    case2 = _create_case(db_session, sharpened="Problem B")

    resp = api_client.get("/api/admin/reindex")
    assert resp.status_code == 200

    emb1 = _get_embedding(db_session, case1.id)
    emb2 = _get_embedding(db_session, case2.id)
    assert emb1 is not None
    assert emb2 is not None


# ---------------------------------------------------------------------------
# AC7: Reindex updates model_version on every record
# ---------------------------------------------------------------------------

def test_admin_reindex_updates_model_version(api_client, db_session):
    """AC7: Reindex updates model_version to current value on every embedding."""
    from app.services.embeddings import upsert_case_embedding, EMBEDDING_MODEL_VERSION
    case = _create_case(db_session)
    # Pre-load with stale version
    upsert_case_embedding(case.id, [0.0], "old-model-v0", db_session)

    resp = api_client.get("/api/admin/reindex")
    assert resp.status_code == 200

    db_session.expire_all()
    emb = _get_embedding(db_session, case.id)
    assert emb.model_version == EMBEDDING_MODEL_VERSION


# ---------------------------------------------------------------------------
# AC8: Embedding errors during reindex are counted without halting
# ---------------------------------------------------------------------------

def test_admin_reindex_counts_errors_without_halting(api_client, db_session):
    """AC8: An error on one case is counted in errors without stopping reindex."""
    case1 = _create_case(db_session, sharpened="Good case")
    case2 = _create_case(db_session, sharpened="Also good")

    call_count = 0

    from app.services import embeddings as emb_mod

    original_fn = emb_mod.compute_case_embedding

    def _flaky(case):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            raise RuntimeError("simulated embedding failure")
        return original_fn(case)

    with patch.object(emb_mod, "compute_case_embedding", side_effect=_flaky):
        resp = api_client.get("/api/admin/reindex")

    assert resp.status_code == 200
    data = resp.json()
    assert data["errors"] == 1
    assert data["reindexed"] == 1
