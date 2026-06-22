"""Tests for issue #68: Replace TF-IDF with Claude embedding-based similarity.

AC1  — case_embedding table exists with correct columns.
AC2  — Anthropic embedding API called once on case create/update; result persisted.
AC3  — find_related_cases / find_related_by_text retain existing signatures and return types.
AC4  — Cosine similarity computed in-process; no external vector DB.
AC5  — Backfill script populates embeddings for pre-existing cases; idempotent.
AC6  — Graceful fallback (empty list, no 500) when case has no stored embedding.
AC7  — model_version column populated with the exact model identifier used.
AC8  — Unit tests: embedding insertion on create/update, cosine similarity, fallback.
AC9  — No re-embedding during related-case lookup; reads from case_embedding only.
"""
from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy import create_engine, inspect
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

# ---------------------------------------------------------------------------
# DB fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(scope="function")
def db_engine():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    from app.models import Base
    Base.metadata.create_all(engine)
    yield engine
    Base.metadata.drop_all(engine)


@pytest.fixture(scope="function")
def db_session(db_engine):
    Session = sessionmaker(bind=db_engine)
    session = Session()
    yield session
    session.close()


@pytest.fixture(scope="function")
def authed_client_with_db(db_session):
    from app.main import app
    from app.db import get_db
    from app.auth import create_session_cookie
    from app.config import AUTH_SECRET

    def _override_db():
        try:
            yield db_session
        finally:
            pass

    app.dependency_overrides[get_db] = _override_db
    from fastapi.testclient import TestClient
    client = TestClient(app)
    token = create_session_cookie(AUTH_SECRET)
    client.cookies.set("session", token)
    yield client
    app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# Seed helpers
# ---------------------------------------------------------------------------

def _make_case(db_session, sharpened: str = "Default sharpened test problem statement.", with_verdict: bool = False) -> str:
    """Insert a Case (and optionally a Probe+Verdict). Return case_id."""
    from app.models import Case, Plan, Probe, Verdict

    case_id = str(uuid.uuid4())
    case = Case(
        id=case_id,
        raw_problem=sharpened,
        sharpened=sharpened,
        stage="sharpened",
        created_at=datetime.now(tz=timezone.utc),
    )
    db_session.add(case)

    plan = Plan(
        id=str(uuid.uuid4()),
        case_id=case_id,
        label="A",
        name="Plan A",
        mechanism="test mechanism",
        prior="0.5",
        current_rank=1,
    )
    db_session.add(plan)

    if with_verdict:
        probe = Probe(
            id=str(uuid.uuid4()),
            case_id=case_id,
            type="measurement",
            target_metric="blood test",
            status="confirmed",
        )
        db_session.add(probe)
        db_session.flush()
        verdict = Verdict(
            id=str(uuid.uuid4()),
            probe_id=probe.id,
            outcome="confirmed",
            notes="confirmed by measurement",
            decided_at=datetime.now(tz=timezone.utc),
        )
        db_session.add(verdict)

    db_session.commit()
    return case_id


def _make_embedding_row(db_session, case_id: str, vector: list[float] | None = None,
                         model: str = "claude-haiku-4-5-20251001") -> None:
    from app.models import CaseEmbedding
    if vector is None:
        vector = [0.1] * 256
    emb = CaseEmbedding(
        case_id=case_id,
        embedding=json.dumps(vector),
        model_version=model,
        created_at=datetime.now(tz=timezone.utc),
    )
    db_session.add(emb)
    db_session.commit()


_STUB_VECTOR = [0.1 if i % 2 == 0 else -0.1 for i in range(256)]
_SIMILAR_VECTOR = [0.1 if i % 2 == 0 else -0.09 for i in range(256)]  # high cosine similarity
_DISSIMILAR_VECTOR = [-0.1 if i % 2 == 0 else 0.1 for i in range(256)]  # opposite direction → low similarity


# ---------------------------------------------------------------------------
# AC1 — case_embedding table exists with correct columns
# ---------------------------------------------------------------------------

def test_case_embedding_table_exists(db_engine):
    """AC1: case_embedding table is present after Base.metadata.create_all."""
    inspector = inspect(db_engine)
    tables = inspector.get_table_names()
    assert "case_embedding" in tables, f"case_embedding table missing; found: {tables}"


def test_case_embedding_has_required_columns(db_engine):
    """AC1: case_embedding has case_id, embedding, model_version, created_at columns."""
    inspector = inspect(db_engine)
    cols = {c["name"] for c in inspector.get_columns("case_embedding")}
    assert "case_id" in cols
    assert "embedding" in cols
    assert "model_version" in cols
    assert "created_at" in cols


# ---------------------------------------------------------------------------
# AC2 + AC7 — Embedding called on case create; model_version persisted
# ---------------------------------------------------------------------------

def test_upsert_embedding_inserts_row(db_session):
    """AC2: upsert_embedding writes a CaseEmbedding row to the database."""
    from app.services.embeddings import upsert_embedding
    from app.models import CaseEmbedding

    case_id = _make_case(db_session)

    with patch("app.services.embeddings.get_embedding", return_value=_STUB_VECTOR):
        upsert_embedding(case_id, "some sharpened text", db_session)

    row = db_session.query(CaseEmbedding).filter(CaseEmbedding.case_id == case_id).first()
    assert row is not None
    stored = json.loads(row.embedding)
    assert stored == _STUB_VECTOR


def test_upsert_embedding_stores_model_version(db_session):
    """AC7: model_version is persisted with the embedding."""
    from app.services.embeddings import upsert_embedding
    from app.models import CaseEmbedding
    import os

    case_id = _make_case(db_session)

    with patch("app.services.embeddings.get_embedding", return_value=_STUB_VECTOR), \
         patch.dict("os.environ", {"EMBEDDING_MODEL": "claude-test-model-9"}):
        # Reload module constant after env change
        import importlib
        import app.services.embeddings as emb_mod
        emb_mod.EMBEDDING_MODEL = "claude-test-model-9"
        upsert_embedding(case_id, "text", db_session)
        emb_mod.EMBEDDING_MODEL = os.environ.get("EMBEDDING_MODEL", "claude-haiku-4-5-20251001")

    row = db_session.query(CaseEmbedding).filter(CaseEmbedding.case_id == case_id).first()
    assert row is not None
    assert row.model_version == "claude-test-model-9"


def test_upsert_embedding_is_idempotent(db_session):
    """AC2+AC5: calling upsert_embedding twice results in exactly one row (upsert)."""
    from app.services.embeddings import upsert_embedding
    from app.models import CaseEmbedding

    case_id = _make_case(db_session)

    with patch("app.services.embeddings.get_embedding", return_value=_STUB_VECTOR):
        upsert_embedding(case_id, "first text", db_session)
        upsert_embedding(case_id, "updated text", db_session)

    count = db_session.query(CaseEmbedding).filter(CaseEmbedding.case_id == case_id).count()
    assert count == 1


def test_upsert_embedding_updates_existing_row(db_session):
    """AC2: second upsert overwrites the embedding (no duplicate rows)."""
    from app.services.embeddings import upsert_embedding
    from app.models import CaseEmbedding

    case_id = _make_case(db_session)
    _make_embedding_row(db_session, case_id, vector=[0.0] * 256)

    new_vector = [0.5] * 256
    with patch("app.services.embeddings.get_embedding", return_value=new_vector):
        upsert_embedding(case_id, "updated text", db_session)

    rows = db_session.query(CaseEmbedding).filter(CaseEmbedding.case_id == case_id).all()
    assert len(rows) == 1
    stored = json.loads(rows[0].embedding)
    assert stored == new_vector


# ---------------------------------------------------------------------------
# AC3 — find_related_cases and find_related_by_text retain signatures
# ---------------------------------------------------------------------------

def test_find_related_cases_returns_none_for_missing_case(db_session):
    """AC3: find_related_cases returns None (not raises) for a non-existent case_id."""
    from app.services.related_cases import find_related_cases

    result = find_related_cases("nonexistent-case-id", db_session)
    assert result is None


def test_find_related_cases_returns_list_for_valid_case(db_session):
    """AC3: find_related_cases returns a list for a valid case_id."""
    from app.services.related_cases import find_related_cases

    case_id = _make_case(db_session)

    with patch("app.services.related_cases.get_embedding", return_value=_STUB_VECTOR):
        result = find_related_cases(case_id, db_session)

    assert isinstance(result, list)


def test_find_related_by_text_returns_list(db_session):
    """AC3: find_related_by_text returns a list (never None)."""
    from app.services.related_cases import find_related_by_text

    with patch("app.services.related_cases.get_embedding", return_value=_STUB_VECTOR):
        result = find_related_by_text("some problem", [], db_session)

    assert isinstance(result, list)


def test_find_related_by_text_empty_string_returns_empty(db_session):
    """AC3: find_related_by_text returns [] when sharpened is empty."""
    from app.services.related_cases import find_related_by_text

    result = find_related_by_text("", [], db_session)
    assert result == []


def test_find_related_cases_result_shape(db_session):
    """AC3: each result dict has the expected keys."""
    from app.services.related_cases import find_related_cases

    query_id = _make_case(db_session)
    cand_id = _make_case(db_session, "login fails after password reset", with_verdict=True)

    _make_embedding_row(db_session, query_id, vector=_STUB_VECTOR)
    _make_embedding_row(db_session, cand_id, vector=_SIMILAR_VECTOR)

    result = find_related_cases(query_id, db_session, threshold=0.0)
    assert isinstance(result, list)
    if result:
        r = result[0]
        assert "case_id" in r
        assert "sharpened_snippet" in r
        assert "verdict_outcome" in r
        assert "deciding_metric" in r
        assert "similarity_score" in r


# ---------------------------------------------------------------------------
# AC4 — Cosine similarity computed in-process
# ---------------------------------------------------------------------------

def test_cosine_similarity_identical_vectors():
    """AC4: identical vectors have cosine similarity of 1.0."""
    from app.services.related_cases import _cosine_vec

    v = [0.1, 0.5, -0.3, 0.8]
    assert abs(_cosine_vec(v, v) - 1.0) < 1e-6


def test_cosine_similarity_opposite_vectors():
    """AC4: opposite vectors have cosine similarity of -1.0."""
    from app.services.related_cases import _cosine_vec

    v = [0.1, 0.5, -0.3]
    neg_v = [-0.1, -0.5, 0.3]
    assert abs(_cosine_vec(v, neg_v) - (-1.0)) < 1e-6


def test_cosine_similarity_orthogonal_vectors():
    """AC4: orthogonal vectors have cosine similarity near 0."""
    from app.services.related_cases import _cosine_vec

    v1 = [1.0, 0.0]
    v2 = [0.0, 1.0]
    assert abs(_cosine_vec(v1, v2)) < 1e-6


def test_cosine_similarity_zero_vector_returns_zero():
    """AC4: zero vector returns 0 without error."""
    from app.services.related_cases import _cosine_vec

    assert _cosine_vec([0.0, 0.0], [0.1, 0.2]) == 0.0
    assert _cosine_vec([0.1, 0.2], [0.0, 0.0]) == 0.0


def test_similar_cases_rank_higher_than_dissimilar(db_session):
    """AC4: cases with higher cosine similarity appear first in results."""
    from app.services.related_cases import find_related_cases

    query_id = _make_case(db_session)
    similar_id = _make_case(db_session, "auth failure after login", with_verdict=True)
    dissimilar_id = _make_case(db_session, "completely unrelated topic", with_verdict=True)

    _make_embedding_row(db_session, query_id, vector=_STUB_VECTOR)
    _make_embedding_row(db_session, similar_id, vector=_SIMILAR_VECTOR)
    _make_embedding_row(db_session, dissimilar_id, vector=_DISSIMILAR_VECTOR)

    result = find_related_cases(query_id, db_session, threshold=-1.0)
    assert len(result) >= 1
    ids_in_order = [r["case_id"] for r in result]
    assert ids_in_order.index(similar_id) < ids_in_order.index(dissimilar_id)


# ---------------------------------------------------------------------------
# AC6 — Graceful fallback when no embedding exists
# ---------------------------------------------------------------------------

def test_find_related_cases_no_embedding_returns_empty_list(db_session):
    """AC6: case with no embedding row returns [] not an exception."""
    from app.services.related_cases import find_related_cases

    case_id = _make_case(db_session)
    # Deliberately do NOT insert a case_embedding row

    result = find_related_cases(case_id, db_session)
    assert result == []


def test_find_related_by_text_graceful_when_candidate_has_no_embedding(db_session):
    """AC6: candidates missing an embedding row are skipped gracefully."""
    from app.services.related_cases import find_related_by_text

    cand_id = _make_case(db_session, "authentication problem", with_verdict=True)
    # Candidate has no embedding row; query should not raise

    with patch("app.services.related_cases.get_embedding", return_value=_STUB_VECTOR):
        result = find_related_by_text("login issue", [], db_session)

    assert isinstance(result, list)


# ---------------------------------------------------------------------------
# AC9 — No re-embedding during related-case lookup
# ---------------------------------------------------------------------------

def test_find_related_cases_does_not_call_get_embedding(db_session):
    """AC9: find_related_cases reads from case_embedding only; never calls get_embedding."""
    from app.services.related_cases import find_related_cases

    case_id = _make_case(db_session)
    _make_embedding_row(db_session, case_id, vector=_STUB_VECTOR)

    with patch("app.services.related_cases.get_embedding") as mock_embed:
        find_related_cases(case_id, db_session)
        mock_embed.assert_not_called()


def test_find_related_by_text_calls_get_embedding_exactly_once(db_session):
    """AC9 (corollary): find_related_by_text calls get_embedding once for the query text."""
    from app.services.related_cases import find_related_by_text

    with patch("app.services.related_cases.get_embedding", return_value=_STUB_VECTOR) as mock_embed:
        find_related_by_text("login authentication failure", ["failed auth"], db_session)
        assert mock_embed.call_count == 1


# ---------------------------------------------------------------------------
# AC2 (integration) — Embedding triggered when case created via API
# ---------------------------------------------------------------------------

def test_create_case_triggers_embedding(authed_client_with_db, db_session):
    """AC2: POST /api/cases calls upsert_embedding after case commit."""
    from app.models import CaseEmbedding

    with patch("app.services.embeddings.get_embedding", return_value=_STUB_VECTOR):
        resp = authed_client_with_db.post("/api/cases", json={
            "raw_problem": "Login authentication failure",
            "sharpened": "Users cannot log in after password reset — is the session token invalid?",
            "not_investigating": [],
        })

    assert resp.status_code == 201
    case_id = resp.json()["id"]

    row = db_session.query(CaseEmbedding).filter(CaseEmbedding.case_id == case_id).first()
    assert row is not None, "Expected CaseEmbedding row after case creation"
    stored = json.loads(row.embedding)
    assert stored == _STUB_VECTOR


def test_create_case_embedding_has_model_version(authed_client_with_db, db_session):
    """AC7: CaseEmbedding row has non-empty model_version after case creation."""
    from app.models import CaseEmbedding

    with patch("app.services.embeddings.get_embedding", return_value=_STUB_VECTOR):
        resp = authed_client_with_db.post("/api/cases", json={
            "raw_problem": "Test problem",
            "sharpened": "Test sharpened problem statement for embedding test.",
            "not_investigating": [],
        })

    assert resp.status_code == 201
    case_id = resp.json()["id"]

    row = db_session.query(CaseEmbedding).filter(CaseEmbedding.case_id == case_id).first()
    assert row is not None
    assert row.model_version  # non-empty string


# ---------------------------------------------------------------------------
# AC5 — Backfill script: idempotent, logs progress, skips already-embedded
# ---------------------------------------------------------------------------

def test_backfill_populates_missing_embeddings(db_session):
    """AC5: backfill_embeddings embeds cases that have no case_embedding row."""
    from scripts.backfill_embeddings import backfill
    from app.models import CaseEmbedding

    case_id = _make_case(db_session)
    # No embedding row yet

    with patch("scripts.backfill_embeddings.get_embedding", return_value=_STUB_VECTOR):
        result = backfill(db_session)

    assert result["processed"] >= 1
    row = db_session.query(CaseEmbedding).filter(CaseEmbedding.case_id == case_id).first()
    assert row is not None


def test_backfill_skips_already_embedded(db_session):
    """AC5: backfill skips cases that already have an embedding row."""
    from scripts.backfill_embeddings import backfill
    from app.models import CaseEmbedding

    case_id = _make_case(db_session)
    _make_embedding_row(db_session, case_id, vector=_STUB_VECTOR)

    with patch("scripts.backfill_embeddings.get_embedding", return_value=_STUB_VECTOR) as mock_embed:
        result = backfill(db_session)

    assert result["skipped"] >= 1
    mock_embed.assert_not_called()


def test_backfill_is_idempotent(db_session):
    """AC5: running backfill twice leaves exactly one embedding row per case."""
    from scripts.backfill_embeddings import backfill
    from app.models import CaseEmbedding

    case_id = _make_case(db_session)

    with patch("scripts.backfill_embeddings.get_embedding", return_value=_STUB_VECTOR):
        backfill(db_session)
        backfill(db_session)

    count = db_session.query(CaseEmbedding).filter(CaseEmbedding.case_id == case_id).count()
    assert count == 1


def test_backfill_returns_counts(db_session):
    """AC5: backfill returns a dict with 'processed' and 'skipped' counts."""
    from scripts.backfill_embeddings import backfill

    _make_case(db_session)  # no embedding → will be processed
    already_embedded_id = _make_case(db_session)
    _make_embedding_row(db_session, already_embedded_id)  # already has embedding → will be skipped

    with patch("scripts.backfill_embeddings.get_embedding", return_value=_STUB_VECTOR):
        result = backfill(db_session)

    assert "processed" in result
    assert "skipped" in result
    assert result["processed"] == 1
    assert result["skipped"] == 1
