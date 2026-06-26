"""Tests for issue #28: Related-case matching service over Verdicts.

AC coverage:
  AC1  – Endpoint accepts Case ID and returns ranked list of related
         Cases with Verdicts.
  AC2  – Similarity computed over sharpened statement and plan
         mechanism fields.
  AC3  – Each match includes case_id, sharpened snippet,
         verdict_outcome, deciding_metric, similarity_score.
  AC4  – Results ranked by descending similarity_score.
  AC5  – Case with no sharpened statement returns empty list (no
         crash).
  AC6  – Empty corpus (no Cases with Verdicts) returns empty list
         with 200 response.
  AC7  – Query latency < 3s for corpus of up to 1,000 Case+Verdict
         rows.
  AC8  – Integration tests: ranking order, outcome field mapping,
         empty-corpus edge case.
  AC9  – Similarity threshold tunable via config without code change.
"""
import json
import os
import time
import uuid

import pytest

os.environ.setdefault("AUTH_SECRET", "test_auth_secret_12345678901")

# Fixed vectors used for embedding-based similarity tests (issue #68).
# _TEST_VECTOR is used for the query case and "similar" candidates.
# _DISSIMILAR_VECTOR is the opposite direction; cosine similarity with _TEST_VECTOR ≈ -1.0.
_TEST_VECTOR = [0.1] * 256
_DISSIMILAR_VECTOR = [-0.1] * 256


# ---------------------------------------------------------------------------
# Shared fixtures
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


# ---------------------------------------------------------------------------
# Seed helpers
# ---------------------------------------------------------------------------

def _seed_case_with_verdict(
    session,
    sharpened: str,
    mechanisms: list[str],
    outcome: str = "confirmed",
    target_metric: str = "blood pressure",
    embedding_vector: list | None = None,
) -> tuple:
    """Seed a Case with plans, a probe, a Verdict, and a pre-computed embedding."""
    import datetime
    from app import models

    c = models.Case(
        id=str(uuid.uuid4()),
        raw_problem="Raw " + sharpened,
        sharpened=sharpened,
        not_investigating=json.dumps([]),
        stage="verdict",
    )
    session.add(c)
    session.flush()

    for i, mech in enumerate(mechanisms):
        label = ["A", "B", "C"][i % 3]
        plan = models.Plan(
            id=str(uuid.uuid4()),
            case_id=c.id,
            label=label,
            name=f"Plan {label}",
            mechanism=mech,
            prior="0.33",
            current_rank=i + 1,
        )
        session.add(plan)
    session.flush()

    probe = models.Probe(
        id=str(uuid.uuid4()),
        case_id=c.id,
        type="measurement",
        target_metric=target_metric,
        status=outcome,
    )
    session.add(probe)
    session.flush()

    verdict = models.Verdict(
        id=str(uuid.uuid4()),
        probe_id=probe.id,
        outcome=outcome,
        notes="Test verdict notes.",
        decided_at=datetime.datetime.now(tz=datetime.timezone.utc),
    )
    session.add(verdict)

    # Pre-compute embedding so find_related_cases (issue #68) can use this case.
    vector = embedding_vector if embedding_vector is not None else _TEST_VECTOR
    emb = models.CaseEmbedding(
        case_id=c.id,
        embedding=json.dumps(vector),
        model_version="claude-haiku-4-5-20251001",
        created_at=datetime.datetime.now(tz=datetime.timezone.utc),
    )
    session.add(emb)

    session.commit()
    return c, probe, verdict


def _seed_case_no_verdict(
    session, sharpened: str, mechanisms: list[str],
    embedding_vector: list | None = None,
):
    """Seed a Case with plans, an embedding row, but no probe or verdict (query target)."""
    import datetime
    from app import models

    c = models.Case(
        id=str(uuid.uuid4()),
        raw_problem="Raw " + sharpened,
        sharpened=sharpened,
        not_investigating=json.dumps([]),
        stage="probe",
    )
    session.add(c)
    session.flush()

    for i, mech in enumerate(mechanisms):
        label = ["A", "B", "C"][i % 3]
        plan = models.Plan(
            id=str(uuid.uuid4()),
            case_id=c.id,
            label=label,
            name=f"Plan {label}",
            mechanism=mech,
            prior="0.33",
            current_rank=i + 1,
        )
        session.add(plan)

    # Pre-compute embedding so find_related_cases (issue #68) can query from this case.
    vector = embedding_vector if embedding_vector is not None else _TEST_VECTOR
    emb = models.CaseEmbedding(
        case_id=c.id,
        embedding=json.dumps(vector),
        model_version="claude-haiku-4-5-20251001",
        created_at=datetime.datetime.now(tz=datetime.timezone.utc),
    )
    session.add(emb)

    session.commit()
    return c


# ---------------------------------------------------------------------------
# AC6: Empty corpus returns 200 with empty list
# ---------------------------------------------------------------------------

def test_empty_corpus_returns_empty_list(api_client, db_session):
    """AC6: When no prior Cases with Verdicts exist, returns [] with 200."""
    query_case = _seed_case_no_verdict(
        db_session,
        sharpened="Why is my energy declining despite adequate sleep?",
        mechanisms=["Iron deficiency reduces oxygen delivery to cells."],
    )
    r = api_client.get(f"/api/cases/{query_case.id}/related")
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["matches"] == [], \
        f"Expected empty list, got {data['matches']}"


def test_empty_corpus_response_shape(api_client, db_session):
    """AC6: Response shape must have 'matches' key even when empty."""
    query_case = _seed_case_no_verdict(
        db_session,
        sharpened="Some problem statement.",
        mechanisms=["Some mechanism."],
    )
    r = api_client.get(f"/api/cases/{query_case.id}/related")
    assert r.status_code == 200
    data = r.json()
    assert "matches" in data, "Response must contain 'matches' key"


# ---------------------------------------------------------------------------
# AC1: Endpoint returns list of related prior Cases with Verdicts
# ---------------------------------------------------------------------------

def test_endpoint_returns_related_cases(api_client, db_session):
    """AC1: Endpoint returns related Cases with at least one Verdict."""
    _seed_case_with_verdict(
        db_session,
        sharpened=(
            "Energy levels have declined due to iron deficiency "
            "and low ferritin."
        ),
        mechanisms=["Low ferritin impairs oxygen transport to muscles."],
        outcome="confirmed",
        target_metric="serum ferritin",
    )
    query_case = _seed_case_no_verdict(
        db_session,
        sharpened="Fatigue and low energy possibly from iron deficiency.",
        mechanisms=[
            "Iron deficiency reduces hemoglobin and oxygen delivery."
        ],
    )
    r = api_client.get(f"/api/cases/{query_case.id}/related")
    assert r.status_code == 200, r.text
    data = r.json()
    assert len(data["matches"]) >= 1, \
        "Should return at least one related case"


def test_endpoint_excludes_cases_without_verdicts(api_client, db_session):
    """AC1: Cases without a logged Verdict must not appear in results."""
    _seed_case_with_verdict(
        db_session,
        sharpened="Energy levels declined due to iron deficiency.",
        mechanisms=["Low ferritin impairs oxygen transport."],
        outcome="confirmed",
    )
    # This case has no verdict
    no_verdict = _seed_case_no_verdict(
        db_session,
        sharpened="Energy levels declined due to iron deficiency.",
        mechanisms=["Low ferritin impairs oxygen transport."],
    )
    query_case = _seed_case_no_verdict(
        db_session,
        sharpened="Fatigue and low energy from iron deficiency.",
        mechanisms=["Iron deficiency reduces oxygen delivery."],
    )
    r = api_client.get(f"/api/cases/{query_case.id}/related")
    assert r.status_code == 200
    data = r.json()
    returned_ids = {m["case_id"] for m in data["matches"]}
    assert no_verdict.id not in returned_ids, \
        "Case without a verdict must not appear in related results"


# ---------------------------------------------------------------------------
# AC3: Response payload shape per match
# ---------------------------------------------------------------------------

def test_match_contains_required_fields(api_client, db_session):
    """AC3: Each match must include case_id, sharpened_snippet,
    verdict_outcome, deciding_metric, and similarity_score."""
    _seed_case_with_verdict(
        db_session,
        sharpened=(
            "Energy declined from iron deficiency and low ferritin levels."
        ),
        mechanisms=["Low ferritin impairs oxygen transport to muscles."],
        outcome="confirmed",
        target_metric="serum ferritin",
    )
    query_case = _seed_case_no_verdict(
        db_session,
        sharpened="Fatigue from iron deficiency and low hemoglobin.",
        mechanisms=["Iron deficiency reduces oxygen delivery to cells."],
    )
    r = api_client.get(f"/api/cases/{query_case.id}/related")
    assert r.status_code == 200
    data = r.json()
    assert len(data["matches"]) >= 1, "Expected at least one match"
    match = data["matches"][0]
    assert "case_id" in match, "match must have case_id"
    assert "sharpened_snippet" in match, \
        "match must have sharpened_snippet"
    assert "verdict_outcome" in match, "match must have verdict_outcome"
    assert "deciding_metric" in match, "match must have deciding_metric"
    assert "similarity_score" in match, \
        "match must have similarity_score"


def test_match_verdict_outcome_is_valid(api_client, db_session):
    """AC3: verdict_outcome must be one of confirmed/killed/inconclusive."""
    _seed_case_with_verdict(
        db_session,
        sharpened="Energy declined from iron deficiency.",
        mechanisms=["Low ferritin impairs oxygen transport."],
        outcome="killed",
        target_metric="ferritin level",
    )
    query_case = _seed_case_no_verdict(
        db_session,
        sharpened="Fatigue from iron deficiency.",
        mechanisms=["Iron deficiency reduces oxygen."],
    )
    r = api_client.get(f"/api/cases/{query_case.id}/related")
    data = r.json()
    if data["matches"]:
        outcome = data["matches"][0]["verdict_outcome"]
        assert outcome in ("confirmed", "killed", "inconclusive"), \
            f"verdict_outcome must be valid enum value, got {outcome!r}"


def test_match_deciding_metric_maps_to_probe_target_metric(
    api_client, db_session
):
    """AC3: deciding_metric must equal the probe's target_metric."""
    _seed_case_with_verdict(
        db_session,
        sharpened=(
            "Energy declined from iron deficiency and low ferritin."
        ),
        mechanisms=["Low ferritin impairs oxygen transport to muscles."],
        outcome="confirmed",
        target_metric="serum ferritin ng/mL",
    )
    query_case = _seed_case_no_verdict(
        db_session,
        sharpened="Fatigue from iron deficiency and low hemoglobin.",
        mechanisms=["Iron deficiency reduces oxygen delivery."],
    )
    r = api_client.get(f"/api/cases/{query_case.id}/related")
    data = r.json()
    assert len(data["matches"]) >= 1
    assert data["matches"][0]["deciding_metric"] == "serum ferritin ng/mL"


def test_match_sharpened_snippet_is_substring(api_client, db_session):
    """AC3: sharpened_snippet must be a non-empty substring of the
    matched Case's sharpened field."""
    original_sharpened = (
        "Energy declined from iron deficiency and low ferritin levels."
    )
    _seed_case_with_verdict(
        db_session,
        sharpened=original_sharpened,
        mechanisms=["Low ferritin impairs oxygen transport."],
        outcome="confirmed",
    )
    query_case = _seed_case_no_verdict(
        db_session,
        sharpened="Fatigue from iron deficiency and low hemoglobin.",
        mechanisms=["Iron deficiency reduces oxygen delivery."],
    )
    r = api_client.get(f"/api/cases/{query_case.id}/related")
    data = r.json()
    assert len(data["matches"]) >= 1
    snippet = data["matches"][0]["sharpened_snippet"]
    assert snippet, "sharpened_snippet must be non-empty"
    starts_with = original_sharpened.startswith(snippet[:20])
    assert snippet in original_sharpened or starts_with, \
        "sharpened_snippet must derive from matched case's sharpened"


def test_match_similarity_score_is_numeric(api_client, db_session):
    """AC4: similarity_score must be a numeric value between 0 and 1."""
    _seed_case_with_verdict(
        db_session,
        sharpened="Energy declined from iron deficiency and low ferritin.",
        mechanisms=["Low ferritin impairs oxygen transport."],
        outcome="confirmed",
    )
    query_case = _seed_case_no_verdict(
        db_session,
        sharpened="Fatigue from iron deficiency and low hemoglobin.",
        mechanisms=["Iron deficiency reduces oxygen delivery."],
    )
    r = api_client.get(f"/api/cases/{query_case.id}/related")
    data = r.json()
    if data["matches"]:
        score = data["matches"][0]["similarity_score"]
        assert isinstance(score, (int, float)), \
            "similarity_score must be numeric"
        assert 0.0 <= score <= 1.0, \
            f"similarity_score must be in [0,1], got {score}"


# ---------------------------------------------------------------------------
# AC4: Results ranked by descending similarity score
# ---------------------------------------------------------------------------

def test_results_ranked_by_descending_similarity(api_client, db_session):
    """AC4: Matches must appear in descending order of similarity_score."""
    # Case clearly similar to query (high similarity)
    _seed_case_with_verdict(
        db_session,
        sharpened=(
            "Low energy fatigue iron deficiency hemoglobin oxygen "
            "transport."
        ),
        mechanisms=[
            "Iron deficiency reduces hemoglobin oxygen transport fatigue."
        ],
        outcome="confirmed",
    )
    # Case less similar (different domain)
    _seed_case_with_verdict(
        db_session,
        sharpened=(
            "Quarterly revenue declined due to reduced customer "
            "acquisition costs."
        ),
        mechanisms=[
            "Marketing spend cut reduces new customer pipeline inflow."
        ],
        outcome="killed",
    )
    query_case = _seed_case_no_verdict(
        db_session,
        sharpened="Low energy fatigue hemoglobin iron oxygen.",
        mechanisms=["Iron hemoglobin oxygen fatigue."],
    )
    r = api_client.get(f"/api/cases/{query_case.id}/related")
    assert r.status_code == 200
    data = r.json()
    scores = [m["similarity_score"] for m in data["matches"]]
    assert scores == sorted(scores, reverse=True), \
        f"Matches must be sorted descending by similarity_score: {scores}"


def test_topically_similar_case_ranked_above_unrelated(
    api_client, db_session
):
    """AC4/AC8: Topically similar case appears above unrelated case."""
    similar_case, _, _ = _seed_case_with_verdict(
        db_session,
        sharpened=(
            "Low energy fatigue iron deficiency hemoglobin oxygen."
        ),
        mechanisms=[
            "Iron deficiency reduces hemoglobin and oxygen transport "
            "to muscles."
        ],
        outcome="confirmed",
        # Same vector as query → cosine similarity = 1.0
        embedding_vector=_TEST_VECTOR,
    )
    _seed_case_with_verdict(
        db_session,
        sharpened=(
            "Revenue declined due to reduced customer acquisition "
            "costs budget."
        ),
        mechanisms=[
            "Marketing spend cut reduces new pipeline inflow acquisition."
        ],
        outcome="killed",
        # Opposite vector → cosine similarity = -1.0 (below threshold)
        embedding_vector=_DISSIMILAR_VECTOR,
    )
    query_case = _seed_case_no_verdict(
        db_session,
        sharpened="Fatigue low energy iron deficiency hemoglobin.",
        mechanisms=["Iron deficiency reduces oxygen hemoglobin transport."],
    )
    r = api_client.get(f"/api/cases/{query_case.id}/related")
    assert r.status_code == 200
    data = r.json()
    assert len(data["matches"]) >= 1, "Should return at least one match"
    top_match_id = data["matches"][0]["case_id"]
    assert top_match_id == similar_case.id, \
        f"Similar case should be top match, but got {top_match_id}"


# ---------------------------------------------------------------------------
# AC2: Similarity uses sharpened + mechanism fields, not raw_problem
# ---------------------------------------------------------------------------

def test_similarity_uses_sharpened_not_raw_problem(api_client, db_session):
    """AC2: Matching is based on sharpened and plan mechanism, not
    raw_problem."""
    # Seed a case where raw_problem matches query but sharpened does not
    from app import models
    import datetime

    # Seed case: raw_problem very similar to query, sharpened different
    c = models.Case(
        id=str(uuid.uuid4()),
        raw_problem="Low energy fatigue iron deficiency hemoglobin oxygen.",
        sharpened=(
            "Revenue declined due to marketing budget cuts and "
            "reduced pipeline."
        ),
        not_investigating=json.dumps([]),
        stage="verdict",
    )
    db_session.add(c)
    db_session.flush()

    plan = models.Plan(
        id=str(uuid.uuid4()),
        case_id=c.id,
        label="A",
        name="Plan A",
        mechanism="Marketing spend cut reduces new pipeline inflow.",
        prior="0.5",
        current_rank=1,
    )
    db_session.add(plan)
    db_session.flush()

    probe = models.Probe(
        id=str(uuid.uuid4()),
        case_id=c.id,
        type="measurement",
        target_metric="pipeline revenue",
        status="killed",
    )
    db_session.add(probe)
    db_session.flush()

    verdict = models.Verdict(
        id=str(uuid.uuid4()),
        probe_id=probe.id,
        outcome="killed",
        notes="Refuted.",
        decided_at=datetime.datetime.now(tz=datetime.timezone.utc),
    )
    db_session.add(verdict)
    db_session.commit()

    # Query case: sharpened is about iron/fatigue (should NOT match)
    query_case = _seed_case_no_verdict(
        db_session,
        sharpened="Low energy fatigue iron deficiency hemoglobin oxygen.",
        mechanisms=["Iron deficiency reduces hemoglobin oxygen transport."],
    )
    r = api_client.get(f"/api/cases/{query_case.id}/related")
    assert r.status_code == 200
    data = r.json()
    # Seeded case should NOT be top result (its sharpened is marketing)
    if data["matches"]:
        top_id = data["matches"][0]["case_id"]
        assert top_id != c.id, \
            "Case matching only on raw_problem must not be top match"


# ---------------------------------------------------------------------------
# AC5: Case with no sharpened statement returns empty list (no crash)
# ---------------------------------------------------------------------------

def test_no_sharpened_statement_returns_empty_list(api_client, db_session):
    """AC5: Case with null sharpened returns empty list, not an error."""
    from app import models

    c = models.Case(
        id=str(uuid.uuid4()),
        raw_problem="Some raw problem.",
        sharpened=None,
        not_investigating=json.dumps([]),
        stage="sharpened",
    )
    db_session.add(c)
    db_session.commit()

    r = api_client.get(f"/api/cases/{c.id}/related")
    assert r.status_code == 200, \
        f"Expected 200, got {r.status_code}: {r.text}"
    data = r.json()
    assert data["matches"] == [], \
        f"Expected empty list for no-sharpened case: {data['matches']}"


def test_empty_sharpened_statement_returns_empty_list(
    api_client, db_session
):
    """AC5: Case with empty sharpened returns empty list."""
    from app import models

    c = models.Case(
        id=str(uuid.uuid4()),
        raw_problem="Some raw problem.",
        sharpened="",
        not_investigating=json.dumps([]),
        stage="sharpened",
    )
    db_session.add(c)
    db_session.commit()

    r = api_client.get(f"/api/cases/{c.id}/related")
    assert r.status_code == 200, \
        f"Expected 200, got {r.status_code}: {r.text}"
    data = r.json()
    assert data["matches"] == [], \
        f"Expected empty list for empty-sharpened: {data['matches']}"


def test_unknown_case_id_returns_404(api_client):
    """AC1: Unknown Case ID returns 404."""
    r = api_client.get(
        "/api/cases/00000000-0000-0000-0000-000000000000/related"
    )
    assert r.status_code == 404, r.text


# ---------------------------------------------------------------------------
# AC8: Outcome field mapping across all three enum values
# ---------------------------------------------------------------------------

def test_outcome_confirmed_mapped_correctly(api_client, db_session):
    """AC8: confirmed outcome is preserved in match payload."""
    _seed_case_with_verdict(
        db_session,
        sharpened=(
            "Energy fatigue iron deficiency hemoglobin oxygen transport."
        ),
        mechanisms=[
            "Iron deficiency reduces hemoglobin transport oxygen fatigue."
        ],
        outcome="confirmed",
    )
    query_case = _seed_case_no_verdict(
        db_session,
        sharpened="Fatigue energy iron hemoglobin oxygen.",
        mechanisms=["Iron hemoglobin oxygen fatigue."],
    )
    r = api_client.get(f"/api/cases/{query_case.id}/related")
    data = r.json()
    confirmed = [
        m for m in data["matches"] if m["verdict_outcome"] == "confirmed"
    ]
    assert confirmed, "At least one confirmed match must appear"


def test_outcome_killed_mapped_correctly(api_client, db_session):
    """AC8: killed outcome is preserved in match payload."""
    _seed_case_with_verdict(
        db_session,
        sharpened=(
            "Energy fatigue iron deficiency hemoglobin oxygen transport."
        ),
        mechanisms=[
            "Iron deficiency reduces hemoglobin oxygen fatigue transport."
        ],
        outcome="killed",
    )
    query_case = _seed_case_no_verdict(
        db_session,
        sharpened="Fatigue energy iron hemoglobin oxygen.",
        mechanisms=["Iron hemoglobin oxygen fatigue."],
    )
    r = api_client.get(f"/api/cases/{query_case.id}/related")
    data = r.json()
    killed = [
        m for m in data["matches"] if m["verdict_outcome"] == "killed"
    ]
    assert killed, "At least one killed match must appear"


def test_outcome_inconclusive_mapped_correctly(api_client, db_session):
    """AC8: inconclusive outcome is preserved in match payload."""
    _seed_case_with_verdict(
        db_session,
        sharpened=(
            "Energy fatigue iron deficiency hemoglobin oxygen transport."
        ),
        mechanisms=[
            "Iron deficiency reduces hemoglobin oxygen fatigue transport."
        ],
        outcome="inconclusive",
    )
    query_case = _seed_case_no_verdict(
        db_session,
        sharpened="Fatigue energy iron hemoglobin oxygen.",
        mechanisms=["Iron hemoglobin oxygen fatigue."],
    )
    r = api_client.get(f"/api/cases/{query_case.id}/related")
    data = r.json()
    inconclusive = [
        m for m in data["matches"]
        if m["verdict_outcome"] == "inconclusive"
    ]
    assert inconclusive, "At least one inconclusive match must appear"


# ---------------------------------------------------------------------------
# AC9: Similarity threshold tunable via config
# ---------------------------------------------------------------------------

def test_high_threshold_filters_out_low_similarity_matches(
    api_client, db_session, monkeypatch
):
    """AC9: Setting a very high threshold (0.99) returns fewer matches."""
    import app.services.related_cases as svc
    _seed_case_with_verdict(
        db_session,
        sharpened="Energy fatigue iron deficiency hemoglobin oxygen.",
        mechanisms=["Iron deficiency reduces hemoglobin oxygen transport."],
        outcome="confirmed",
    )
    query_case = _seed_case_no_verdict(
        db_session,
        sharpened="Fatigue from possible iron deficiency.",
        mechanisms=["Iron reduces oxygen."],
    )
    # With default threshold, we expect matches
    r_default = api_client.get(f"/api/cases/{query_case.id}/related")
    default_count = len(r_default.json()["matches"])

    # With very high threshold, should return fewer (possibly zero)
    monkeypatch.setattr(svc, "SIMILARITY_THRESHOLD", 0.99)
    r_high = api_client.get(f"/api/cases/{query_case.id}/related")
    high_count = len(r_high.json()["matches"])

    assert high_count <= default_count, (
        f"High threshold should return <= matches vs default, "
        f"got {high_count} vs {default_count}"
    )


def test_zero_threshold_returns_all_cases_with_verdicts(
    api_client, db_session, monkeypatch
):
    """AC9: Setting threshold to 0.0 returns all Cases with Verdicts."""
    import app.services.related_cases as svc
    monkeypatch.setattr(svc, "SIMILARITY_THRESHOLD", 0.0)

    for i in range(3):
        _seed_case_with_verdict(
            db_session,
            sharpened=(
                f"Unrelated domain case number {i} with unique "
                "distinct words."
            ),
            mechanisms=[
                f"Completely different mechanism number {i} unique words."
            ],
            outcome="confirmed",
        )
    query_case = _seed_case_no_verdict(
        db_session,
        sharpened="Some query case about a completely separate topic.",
        mechanisms=["Different mechanism altogether."],
    )
    r = api_client.get(f"/api/cases/{query_case.id}/related")
    assert r.status_code == 200
    data = r.json()
    # With threshold=0.0, all 3 seeded cases should be returned
    assert len(data["matches"]) == 3, (
        "With threshold=0.0, all 3 verdict cases should be returned, "
        f"got {len(data['matches'])}"
    )


# ---------------------------------------------------------------------------
# AC7: Performance — < 3s for 1,000 Case+Verdict rows
# ---------------------------------------------------------------------------

def test_query_latency_under_3_seconds_for_1000_rows(db_session):
    """AC7: Related-case query must complete within 3s for 1,000 rows."""
    import datetime
    from app import models
    from app.services.related_cases import find_related_cases

    # Seed 1,000 cases with verdicts
    words = [
        "energy", "fatigue", "iron", "hemoglobin", "oxygen", "sleep",
        "cortisol", "stress", "metabolism", "thyroid", "vitamin",
        "deficiency", "inflammation",
    ]
    import random
    random.seed(42)

    for i in range(1000):
        c = models.Case(
            id=str(uuid.uuid4()),
            raw_problem=f"Problem {i}",
            sharpened=" ".join(random.choices(words, k=8)) + f" case {i}.",
            not_investigating=json.dumps([]),
            stage="verdict",
        )
        db_session.add(c)
        db_session.flush()

        probe = models.Probe(
            id=str(uuid.uuid4()),
            case_id=c.id,
            type="measurement",
            target_metric="metric " + str(i % 10),
            status="confirmed",
        )
        db_session.add(probe)
        db_session.flush()

        verdict = models.Verdict(
            id=str(uuid.uuid4()),
            probe_id=probe.id,
            outcome="confirmed",
            notes="Test.",
            decided_at=datetime.datetime.now(tz=datetime.timezone.utc),
        )
        db_session.add(verdict)

    db_session.commit()

    query_case = models.Case(
        id=str(uuid.uuid4()),
        raw_problem="Query case",
        sharpened="energy fatigue iron hemoglobin oxygen sleep cortisol.",
        not_investigating=json.dumps([]),
        stage="probe",
    )
    db_session.add(query_case)
    db_session.commit()

    start = time.time()
    find_related_cases(query_case.id, db_session)
    elapsed = time.time() - start

    assert elapsed < 3.0, f"Query took {elapsed:.2f}s, must be under 3s"
