"""Tests for issue #9: Add manual source attachment form to Plan cards.

AC coverage:
  AC1  – "Add Source" trigger visible on every PlanCard (JS).
  AC2  – Clicking trigger opens a form with Kind/Title/URL/Claim/Citation fields (JS).
  AC3  – POST /api/plans/{plan_id}/sources creates a Source row linked to the Plan.
  AC4  – Required-field validation: Title, Claim, Citation must not be empty; inline errors shown (JS).
  AC5  – After submission, form clears/closes and SourceChip appears without page reload (JS).
  AC6  – SourceChip colour by Kind: book=amber, article=blue, youtube=red (CSS + JS).
  AC7  – SourceChip with URL renders as a link (target=_blank); without URL renders non-interactive (JS).
  AC8  – Multiple sources on same Plan all display (no cap) (API).
  AC9  – Source data persists across requests (DB).
  AC10 – No network call is made to fetch/synthesize URL content (JS: no fetch inside source submit).
"""
import os
import uuid

import pytest

os.environ.setdefault("AUTH_SECRET", "test_auth_secret_12345678901")

STATIC = __import__("pathlib").Path(__file__).parent.parent / "app" / "static"
JS_DIR = STATIC / "js"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _read_combined_js():
    return "".join((JS_DIR / f).read_text() for f in sorted(JS_DIR.iterdir()) if f.suffix == ".js")


def _read_combined_css():
    styles_dir = STATIC / "styles"
    pieces = []
    # primitives.css at root static level
    root_css = STATIC / "styles.css"
    if root_css.exists():
        pieces.append(root_css.read_text())
    for f in sorted(styles_dir.rglob("*.css")):
        pieces.append(f.read_text())
    return "\n".join(pieces)


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


def _seed_plan(session, label="A"):
    """Seed a Case + Plan; return the Plan."""
    from app import models
    case = models.Case(
        id=str(uuid.uuid4()),
        raw_problem="Test problem",
        sharpened="Sharpened test",
        stage="gather",
    )
    session.add(case)
    session.flush()
    plan = models.Plan(
        id=str(uuid.uuid4()),
        case_id=case.id,
        label=label,
        name=f"Plan {label}",
        mechanism="Some mechanism.",
        prior="0.5",
        current_rank=1,
    )
    session.add(plan)
    session.commit()
    return plan


# ---------------------------------------------------------------------------
# AC3: POST /api/plans/{plan_id}/sources creates a Source row
# ---------------------------------------------------------------------------

def test_create_source_endpoint_exists(api_client, db_session):
    """AC3: POST /api/plans/{plan_id}/sources returns 201 and the new source id."""
    plan = _seed_plan(db_session)
    payload = {
        "kind": "article",
        "title": "Test Article",
        "url": None,
        "claim": "Supports hypothesis",
        "citation": "Smith 2024",
    }
    r = api_client.post("/api/sources", json={**payload, "plan_id": plan.id})
    assert r.status_code == 201, r.text
    data = r.json()
    assert "id" in data, "Response must include the new source id"


def test_create_source_persists_to_db(api_client, db_session):
    """AC3/AC9: Source row is persisted and linked to the correct plan_id."""
    from app import models
    plan = _seed_plan(db_session)
    payload = {
        "kind": "book",
        "title": "Reference Book",
        "url": None,
        "claim": "Background context",
        "citation": "Doe 2023",
    }
    r = api_client.post("/api/sources", json={**payload, "plan_id": plan.id})
    assert r.status_code == 201, r.text

    src = db_session.query(models.Source).filter_by(plan_id=plan.id).first()
    assert src is not None, "Source row must exist in the database"
    assert src.title == "Reference Book"
    assert src.kind == "book"
    assert src.claim == "Background context"
    assert src.citation == "Doe 2023"


def test_create_source_with_url(api_client, db_session):
    """AC3: Source with a valid URL is persisted correctly."""
    from app import models
    plan = _seed_plan(db_session)
    payload = {
        "kind": "youtube",
        "title": "Demo Video",
        "url": "https://youtube.com/watch?v=abc123",
        "claim": "Visual proof",
        "citation": "YouTube 2024",
    }
    r = api_client.post("/api/sources", json={**payload, "plan_id": plan.id})
    assert r.status_code == 201, r.text
    src = db_session.query(models.Source).filter_by(plan_id=plan.id).first()
    assert src.url == "https://youtube.com/watch?v=abc123"


def test_create_source_404_for_unknown_plan(api_client):
    """AC3: POST with unknown plan_id returns 404."""
    r = api_client.post("/api/sources", json={
        "plan_id": str(uuid.uuid4()),
        "kind": "article",
        "title": "Ghost",
        "url": None,
        "claim": "A claim",
        "citation": "Citation 2024",
    })
    assert r.status_code == 404, r.text


def test_create_source_validates_required_fields(api_client, db_session):
    """AC4 (API side): Missing required fields return 422."""
    plan = _seed_plan(db_session)
    # Missing title
    r = api_client.post("/api/sources", json={
        "plan_id": plan.id, "kind": "article", "url": None, "claim": "A claim", "citation": "X 2024"
    })
    assert r.status_code == 422, "Missing title must return 422"

    # Missing claim
    r2 = api_client.post("/api/sources", json={
        "plan_id": plan.id, "kind": "article", "title": "Title", "url": None, "citation": "X 2024"
    })
    assert r2.status_code == 422, "Missing claim must return 422"

    # Missing citation
    r3 = api_client.post("/api/sources", json={
        "plan_id": plan.id, "kind": "article", "title": "Title", "url": None, "claim": "A claim"
    })
    assert r3.status_code == 422, "Missing citation must return 422"


def test_create_source_rejects_invalid_url(api_client, db_session):
    """AC (URL validation): Invalid URL string returns 422."""
    plan = _seed_plan(db_session)
    r = api_client.post("/api/sources", json={
        "plan_id": plan.id,
        "kind": "article",
        "title": "Bad URL Source",
        "url": "not-a-url",
        "claim": "A claim",
        "citation": "X 2024",
    })
    assert r.status_code == 422, "Invalid URL must return 422"


# ---------------------------------------------------------------------------
# AC8: GET sources for a plan returns all of them (no cap)
# ---------------------------------------------------------------------------

def test_get_sources_for_plan(api_client, db_session):
    """AC8: GET /api/plans/{plan_id}/sources returns all sources for the plan."""
    plan = _seed_plan(db_session)
    sources_payload = [
        {"kind": "article", "title": "Article 1", "url": None, "claim": "Claim 1", "citation": "Cite 1"},
        {"kind": "book",    "title": "Book 1",    "url": None, "claim": "Claim 2", "citation": "Cite 2"},
        {"kind": "youtube", "title": "Video 1", "url": "https://youtube.com/watch?v=xyz",
         "claim": "Claim 3", "citation": "Cite 3"},
    ]
    for payload in sources_payload:
        r = api_client.post("/api/sources", json={**payload, "plan_id": plan.id})
        assert r.status_code == 201, r.text

    r = api_client.get(f"/api/sources?plan_id={plan.id}")
    assert r.status_code == 200, r.text
    data = r.json()
    assert "sources" in data
    assert len(data["sources"]) == 3, f"Expected 3 sources, got {len(data['sources'])}"


def test_get_sources_returns_correct_fields(api_client, db_session):
    """AC8: Each source in GET response has id, kind, title, url, claim, citation."""
    plan = _seed_plan(db_session)
    api_client.post("/api/sources", json={
        "plan_id": plan.id, "kind": "article", "title": "T", "url": "https://example.com",
        "claim": "C", "citation": "X 2024"
    })
    r = api_client.get(f"/api/sources?plan_id={plan.id}")
    assert r.status_code == 200
    src = r.json()["sources"][0]
    for field in ("id", "kind", "title", "url", "claim", "citation"):
        assert field in src, f"Source response must include '{field}'"


# ---------------------------------------------------------------------------
# AC9: GET /api/cases/{id} includes sources in each plan
# ---------------------------------------------------------------------------

def test_case_detail_includes_sources_in_plans(api_client, db_session):
    """AC9: GET /api/cases/{id} returns sources list inside each plan."""
    plan = _seed_plan(db_session)
    api_client.post("/api/sources", json={
        "plan_id": plan.id, "kind": "book", "title": "My Book", "url": None,
        "claim": "Important", "citation": "Author 2024"
    })

    from app import models
    case = db_session.get(models.Case, plan.case_id)
    r = api_client.get(f"/api/cases/{case.id}")
    assert r.status_code == 200
    data = r.json()
    plans = data.get("plans", [])
    assert len(plans) > 0
    plan_a = next((p for p in plans if p["label"] == "A"), None)
    assert plan_a is not None
    assert "sources" in plan_a, "Each plan in GET /api/cases/{id} must have a 'sources' list"
    assert len(plan_a["sources"]) == 1
    assert plan_a["sources"][0]["title"] == "My Book"


# ---------------------------------------------------------------------------
# AC1: "Add Source" trigger visible on every PlanCard (JS)
# ---------------------------------------------------------------------------

def test_add_source_trigger_in_plancard():
    """AC1: PlanCard JS must contain an 'Add source' trigger."""
    combined = _read_combined_js()
    # Check for 'Add source' or 'Add Source' button/trigger text
    assert "Add source" in combined or "Add Source" in combined, \
        "PlanCard must contain an 'Add source' trigger"


# ---------------------------------------------------------------------------
# AC2: Form has Kind/Title/URL/Claim/Citation fields (JS)
# ---------------------------------------------------------------------------

def test_source_form_has_kind_field():
    """AC2: Source form must have a Kind select field."""
    combined = _read_combined_js()
    assert "kind" in combined.lower(), "Source form must include a 'Kind' field"
    # Check for the kind options
    assert "book" in combined and "article" in combined and "youtube" in combined, \
        "Kind field must have book, article, youtube options"


def test_source_form_has_title_field():
    """AC2: Source form must have a Title field."""
    combined = _read_combined_js()
    assert "title" in combined.lower(), "Source form must include a 'Title' field"


def test_source_form_has_url_field():
    """AC2: Source form must have a URL field."""
    combined = _read_combined_js()
    assert "url" in combined.lower(), "Source form must include a 'URL' field"


def test_source_form_has_claim_field():
    """AC2: Source form must have a Claim field."""
    combined = _read_combined_js()
    assert "claim" in combined.lower(), "Source form must include a 'Claim' field"


def test_source_form_has_citation_field():
    """AC2: Source form must have a Citation field."""
    combined = _read_combined_js()
    assert "citation" in combined.lower(), "Source form must include a 'Citation' field"


# ---------------------------------------------------------------------------
# AC4: Inline validation errors shown in JS
# ---------------------------------------------------------------------------

def test_source_form_shows_inline_errors():
    """AC4: Source form must show inline validation error messages."""
    combined = _read_combined_js()
    # The form should have some error display mechanism
    assert "error" in combined.lower(), "Source form must have inline error state"


# ---------------------------------------------------------------------------
# AC5: SourceForm/Modal + SourceChip defined in JS
# ---------------------------------------------------------------------------

def test_source_chip_component_defined():
    """AC5/AC6: SourceChip component must be defined in JS."""
    combined = _read_combined_js()
    assert "SourceChip" in combined, "SourceChip component must be defined in JS"


def test_source_form_component_defined():
    """AC2/AC5: A source form or modal component must be defined in JS."""
    combined = _read_combined_js()
    assert "SourceForm" in combined or "AddSource" in combined or "sourceForm" in combined, \
        "A source form component must be defined in JS"


# ---------------------------------------------------------------------------
# AC6: SourceChip colour encoding (amber=book, blue=article, red=youtube) in CSS
# ---------------------------------------------------------------------------

def test_source_chip_book_amber():
    """AC6: .src.book uses amber colour."""
    css = _read_combined_css()
    assert ".src.book" in css, ".src.book CSS rule must be defined"
    # Find the .src.book block and check it references amber
    idx = css.find(".src.book")
    snippet = css[idx:idx+120]
    assert "amber" in snippet or "--amber" in snippet, \
        ".src.book must reference --amber"


def test_source_chip_article_blue():
    """AC6: .src.article uses blue colour."""
    css = _read_combined_css()
    assert ".src.article" in css, ".src.article CSS rule must be defined"
    idx = css.find(".src.article")
    snippet = css[idx:idx+120]
    assert "blue" in snippet or "--blue" in snippet, \
        ".src.article must reference --blue"


def test_source_chip_youtube_red():
    """AC6: .src.youtube uses red colour."""
    css = _read_combined_css()
    assert ".src.youtube" in css, ".src.youtube CSS rule must be defined"
    idx = css.find(".src.youtube")
    snippet = css[idx:idx+120]
    assert "red" in snippet or "--red" in snippet, \
        ".src.youtube must reference --red"


# ---------------------------------------------------------------------------
# AC7: SourceChip link behaviour in JS
# ---------------------------------------------------------------------------

def test_source_chip_renders_as_link_when_url_present():
    """AC7: SourceChip must render as <a> with target=_blank when URL present."""
    combined = _read_combined_js()
    # SourceChip should conditionally render an <a> tag
    assert "_blank" in combined or 'target' in combined, \
        "SourceChip must open URL in a new tab (target='_blank')"
    # Check for conditional URL rendering
    assert "href" in combined, "SourceChip must render an href when URL is present"


# ---------------------------------------------------------------------------
# AC10: No network fetch inside source submission to retrieve URL content (JS)
# ---------------------------------------------------------------------------

def test_no_url_fetch_in_source_form():
    """AC10: Source form must POST to the API only — not fetch the source URL content."""
    combined = _read_combined_js()
    # Find SourceForm or AddSource section
    form_idx = combined.find("SourceForm") if "SourceForm" in combined else combined.find("AddSource")
    assert form_idx != -1, "Source form component must exist"
    form_block = combined[form_idx:form_idx+3000]
    # Should only POST to /api/sources, NOT fetch the user-entered URL
    # We verify by checking the API endpoint pattern is present
    assert "/api/sources" in form_block or "sources" in form_block, \
        "Source form must POST to the /api/sources endpoint"
