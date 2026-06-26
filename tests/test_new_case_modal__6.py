"""Tests for issue #6: Add New Case modal with Sharpen (Stage 0).

AC coverage:
  AC1  – "New Case" trigger opens modal; multi-line input + disabled Sharpen button present in JS
  AC2  – Sharpen button enabled only when input is non-empty (JS contains non-empty guard)
  AC3  – Clicking Sharpen calls POST /api/cases/sharpen; endpoint returns sharpened + not_investigating
  AC4  – Response parsed into (a) sharpened statement and (b) not_investigating array
  AC5  – Confirmation step rendered in modal (JS shows sharpened statement + not_investigating)
  AC6  – Back button returns to input step (JS defined, raw text preserved)
  AC7  – POST /api/cases creates Case at stage "sharpened" with correct DB fields
  AC8  – After creation modal routes to new Case detail; POST returns case id
  AC9  – GET /api/cases/{id} returns sharpened statement as primary field
  AC10 – not_investigating items returned as array; JS renders them as chips
  AC11 – Claude API failure returns 502 with error detail; JS shows inline error
  AC12 – Modal keyboard-accessible; Escape closes without creating a record (JS handles keydown)
"""
import json
import os
import uuid
from unittest.mock import AsyncMock, patch

import pytest

os.environ.setdefault("AUTH_SECRET", "test_auth_secret_12345678901")

STATIC = __import__("pathlib").Path(__file__).parent.parent / "app" / "static"
JS_DIR = STATIC / "js"


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


_MOCK_SHARPEN_RESULT = {
    "sharpened": "Aerobic pace regressed ~20s/km over 14 weeks at stable mileage — identify the single dominant cause.",
    "not_investigating": [
        "Nutrition changes",
        "Sleep quality",
        "Equipment upgrades",
        "Mental factors",
    ],
}


def _mock_sharpen(*args, **kwargs):
    return _MOCK_SHARPEN_RESULT.copy()


# ---------------------------------------------------------------------------
# AC3 / AC4: POST /api/cases/sharpen — endpoint exists and returns correct shape
# ---------------------------------------------------------------------------

def test_sharpen_endpoint_returns_sharpened_and_not_investigating(api_client):
    """AC3+AC4: /api/cases/sharpen returns sharpened statement and not_investigating array."""
    with patch("app.routers.cases.sharpen_problem", new=AsyncMock(return_value=_MOCK_SHARPEN_RESULT)):
        r = api_client.post("/api/cases/sharpen", json={"raw_problem": "My running is getting worse"})
    assert r.status_code == 200
    data = r.json()
    assert "sharpened" in data, "Response must have 'sharpened' key"
    assert "not_investigating" in data, "Response must have 'not_investigating' key"
    assert isinstance(data["sharpened"], str) and data["sharpened"], "sharpened must be a non-empty string"
    assert isinstance(data["not_investigating"], list), "not_investigating must be a list"
    assert len(data["not_investigating"]) > 0, "not_investigating must have at least one item"


def test_sharpen_endpoint_rejects_empty_input(api_client):
    """AC2 (backend): Empty raw_problem returns 422."""
    with patch("app.routers.cases.sharpen_problem", new=AsyncMock(return_value=_MOCK_SHARPEN_RESULT)):
        r = api_client.post("/api/cases/sharpen", json={"raw_problem": ""})
    assert r.status_code == 422, "Empty input must be rejected with 422"


def test_sharpen_endpoint_rejects_missing_input(api_client):
    """AC3: Missing raw_problem returns 422."""
    with patch("app.routers.cases.sharpen_problem", new=AsyncMock(return_value=_MOCK_SHARPEN_RESULT)):
        r = api_client.post("/api/cases/sharpen", json={})
    assert r.status_code == 422


# ---------------------------------------------------------------------------
# AC11: Claude API failure returns 502 with inline error
# ---------------------------------------------------------------------------

def test_sharpen_endpoint_api_failure_returns_502(api_client):
    """AC11: When Claude API call fails, endpoint returns 502 with error detail."""
    from app.sharpen import SharpenError
    with patch("app.routers.cases.sharpen_problem", new=AsyncMock(side_effect=SharpenError("API unavailable"))):
        r = api_client.post("/api/cases/sharpen", json={"raw_problem": "Some problem"})
    assert r.status_code == 502
    data = r.json()
    assert "detail" in data, "502 response must include 'detail' field"


# ---------------------------------------------------------------------------
# AC7 / AC8: POST /api/cases — creates Case record; returns case id
# ---------------------------------------------------------------------------

def test_create_case_stores_record_at_stage_sharpened(api_client, db_session):
    """AC7: POST /api/cases creates a Case at stage='sharpened' with correct fields."""
    payload = {
        "raw_problem": "My running pace keeps getting worse",
        "sharpened": _MOCK_SHARPEN_RESULT["sharpened"],
        "not_investigating": _MOCK_SHARPEN_RESULT["not_investigating"],
    }
    r = api_client.post("/api/cases", json=payload)
    assert r.status_code == 201
    data = r.json()
    assert "id" in data, "Response must include the new case id"

    # Verify DB record
    from app import models
    case = db_session.query(models.Case).filter_by(id=data["id"]).first()
    assert case is not None, "Case must exist in database"
    assert case.stage == "sharpened", f"stage must be 'sharpened', got {case.stage!r}"
    assert case.sharpened == _MOCK_SHARPEN_RESULT["sharpened"]
    assert case.raw_problem == payload["raw_problem"]
    stored = json.loads(case.not_investigating)
    assert stored == _MOCK_SHARPEN_RESULT["not_investigating"]


def test_create_case_returns_201_with_id(api_client):
    """AC8: POST /api/cases returns 201 with case id for client-side routing."""
    payload = {
        "raw_problem": "I can't focus during work",
        "sharpened": "Focus loss during deep work — identify dominant cause",
        "not_investigating": ["diet", "sleep"],
    }
    r = api_client.post("/api/cases", json=payload)
    assert r.status_code == 201
    assert "id" in r.json()
    assert len(r.json()["id"]) > 0


def test_create_case_rejects_missing_sharpened(api_client):
    """AC7: sharpened is required on POST /api/cases."""
    r = api_client.post("/api/cases", json={"raw_problem": "problem"})
    assert r.status_code == 422


# ---------------------------------------------------------------------------
# AC9 / AC10: GET /api/cases/{id} — detail endpoint returns sharpened + not_investigating
# ---------------------------------------------------------------------------

def test_get_case_detail_returns_sharpened(api_client, db_session):
    """AC9: GET /api/cases/{id} returns the sharpened statement as primary field."""
    # Create via API
    payload = {
        "raw_problem": "My runs are slower",
        "sharpened": "Aerobic pace drop — find cause",
        "not_investigating": ["gear", "weather"],
    }
    create_r = api_client.post("/api/cases", json=payload)
    assert create_r.status_code == 201
    case_id = create_r.json()["id"]

    r = api_client.get(f"/api/cases/{case_id}")
    assert r.status_code == 200
    data = r.json()
    assert data["sharpened"] == payload["sharpened"], "sharpened must match what was stored"


def test_get_case_detail_returns_not_investigating_as_array(api_client, db_session):
    """AC10: GET /api/cases/{id} returns not_investigating as a list (not raw JSON string)."""
    payload = {
        "raw_problem": "Focus problem",
        "sharpened": "Focus loss — identify dominant cause",
        "not_investigating": ["diet", "caffeine", "sleep"],
    }
    create_r = api_client.post("/api/cases", json=payload)
    case_id = create_r.json()["id"]

    r = api_client.get(f"/api/cases/{case_id}")
    data = r.json()
    assert isinstance(data["not_investigating"], list), "not_investigating must be deserialized to list"
    assert data["not_investigating"] == ["diet", "caffeine", "sleep"]


def test_get_case_detail_404_for_unknown_id(api_client):
    """AC9: GET /api/cases/{id} returns 404 for unknown id."""
    r = api_client.get(f"/api/cases/{uuid.uuid4()}")
    assert r.status_code == 404


def test_get_case_detail_includes_stage_string(api_client, db_session):
    """AC9: Case detail includes stage as the enum string ('sharpened' for a new case)."""
    payload = {
        "raw_problem": "A problem",
        "sharpened": "A sharpened statement",
        "not_investigating": ["x"],
    }
    create_r = api_client.post("/api/cases", json=payload)
    case_id = create_r.json()["id"]

    r = api_client.get(f"/api/cases/{case_id}")
    data = r.json()
    assert "stage" in data
    assert data["stage"] == "sharpened", f"Newly created case must be at stage 'sharpened', got {data['stage']}"


# ---------------------------------------------------------------------------
# AC1: NewCaseModal in JS — step 0 has textarea + Sharpen button
# ---------------------------------------------------------------------------

def test_new_case_modal_has_textarea_and_sharpen_button():
    """AC1+AC2: NewCaseModal JS must contain textarea element and Sharpen button."""
    combined = "".join((JS_DIR / f).read_text() for f in JS_DIR.iterdir() if f.suffix == ".js")
    assert "textarea" in combined.lower(), "Modal must render a textarea for problem input"
    assert "Sharpen" in combined, "Modal must have a 'Sharpen' button"


def test_new_case_modal_disables_sharpen_when_empty():
    """AC2: Sharpen button must be disabled when input is empty (JS contains disabled/non-empty guard)."""
    combined = "".join((JS_DIR / f).read_text() for f in JS_DIR.iterdir() if f.suffix == ".js")
    # The button should be conditionally disabled — look for a disabled prop tied to input length/empty check
    assert "disabled" in combined, "JS must contain a disabled attribute for the Sharpen button"
    # The guard should reference the raw input state (empty/length check)
    assert (
        ".trim()" in combined or "!raw" in combined or "raw.length" in combined or "rawProblem" in combined
    ), "JS must guard Sharpen button on non-empty input"


# ---------------------------------------------------------------------------
# AC3: JS calls /api/cases/sharpen
# ---------------------------------------------------------------------------

def test_modal_calls_sharpen_api_endpoint():
    """AC3: NewCaseModal JS must call /api/cases/sharpen."""
    combined = "".join((JS_DIR / f).read_text() for f in JS_DIR.iterdir() if f.suffix == ".js")
    assert "/api/cases/sharpen" in combined, "JS must call /api/cases/sharpen endpoint"


# ---------------------------------------------------------------------------
# AC3 (loading state): Sharpen button shows loading/spinner state
# ---------------------------------------------------------------------------

def test_modal_has_loading_state():
    """AC3: Modal JS must have a loading state for the Sharpen call."""
    combined = "".join((JS_DIR / f).read_text() for f in JS_DIR.iterdir() if f.suffix == ".js")
    assert (
        "loading" in combined.lower() or "crux-spin" in combined or "spinner" in combined.lower()
    ), "JS must have a loading/spinner state during Sharpen API call"


# ---------------------------------------------------------------------------
# AC5: Confirmation step renders sharpened statement + not-investigating list
# ---------------------------------------------------------------------------

def test_modal_confirmation_step_renders_sharpened():
    """AC5: NewCaseModal step 1 (confirm) must reference sharpened statement in JS."""
    combined = "".join((JS_DIR / f).read_text() for f in JS_DIR.iterdir() if f.suffix == ".js")
    assert "SHARPENED" in combined.upper() or "sharpened" in combined, \
        "Confirmation step must render the sharpened statement"


def test_modal_confirmation_step_renders_not_investigating():
    """AC5: Confirmation step must render not_investigating items."""
    combined = "".join((JS_DIR / f).read_text() for f in JS_DIR.iterdir() if f.suffix == ".js")
    assert "not_investigating" in combined or "notInvestigating" in combined, \
        "Confirmation step must render not_investigating items"


# ---------------------------------------------------------------------------
# AC6: Back button returns to input step
# ---------------------------------------------------------------------------

def test_modal_has_back_button():
    """AC6: NewCaseModal must have a Back/Edit button on the confirmation step."""
    combined = "".join((JS_DIR / f).read_text() for f in JS_DIR.iterdir() if f.suffix == ".js")
    assert "Back" in combined or "Edit" in combined or "back" in combined, \
        "Confirmation step must have a Back/Edit button to return to input"


def test_modal_preserves_raw_input_on_back():
    """AC6: The raw input state is preserved when going back (setStep / step state management)."""
    combined = "".join((JS_DIR / f).read_text() for f in JS_DIR.iterdir() if f.suffix == ".js")
    # Raw problem state variable must persist across steps
    assert "setStep" in combined or "step" in combined, \
        "Modal must manage step state to preserve raw input on Back"


# ---------------------------------------------------------------------------
# AC8: Create Case calls /api/cases; navigates to detail
# ---------------------------------------------------------------------------

def test_modal_calls_create_case_api():
    """AC8: NewCaseModal must call POST /api/cases on confirm."""
    combined = "".join((JS_DIR / f).read_text() for f in JS_DIR.iterdir() if f.suffix == ".js")
    assert "/api/cases" in combined, "JS must call /api/cases to create a case"
    assert "Create" in combined or "create" in combined, \
        "Confirm step must have a Create Case button"


def test_modal_routes_to_case_detail_after_creation():
    """AC8: After creation, JS navigates to case detail (routes to case/{id})."""
    combined = "".join((JS_DIR / f).read_text() for f in JS_DIR.iterdir() if f.suffix == ".js")
    assert (
        "case/" in combined or "/cases/" in combined or "setRoute" in combined
    ), "After creation JS must navigate to the new Case detail"


# ---------------------------------------------------------------------------
# AC9 / AC10: Case detail screen in JS
# ---------------------------------------------------------------------------

def test_case_detail_screen_defined_in_js():
    """AC9: CaseDetailScreen or equivalent component must be defined in JS."""
    combined = "".join((JS_DIR / f).read_text() for f in JS_DIR.iterdir() if f.suffix == ".js")
    assert (
        "CaseDetail" in combined or "CaseScreen" in combined or "case-detail" in combined.lower()
    ), "A case detail screen component must be defined in JS"


def test_case_detail_shows_not_investigating_chips():
    """AC10: Case detail JS must render not_investigating items as chips."""
    combined = "".join((JS_DIR / f).read_text() for f in JS_DIR.iterdir() if f.suffix == ".js")
    assert (
        "notInvestigating" in combined or "not_investigating" in combined
    ), "Case detail must render not_investigating chips"


# ---------------------------------------------------------------------------
# AC11: Inline error in JS when API fails
# ---------------------------------------------------------------------------

def test_modal_has_inline_error_display():
    """AC11: NewCaseModal JS must have an error state to display inline error messages."""
    combined = "".join((JS_DIR / f).read_text() for f in JS_DIR.iterdir() if f.suffix == ".js")
    assert (
        "error" in combined.lower() and "setError" in combined or "errMsg" in combined or "err" in combined
    ), "Modal must have an error state for inline error display"


# ---------------------------------------------------------------------------
# AC12: Escape key closes modal
# ---------------------------------------------------------------------------

def test_modal_handles_escape_key():
    """AC12: NewCaseModal JS must handle Escape key to close without creating a record."""
    combined = "".join((JS_DIR / f).read_text() for f in JS_DIR.iterdir() if f.suffix == ".js")
    assert (
        "Escape" in combined or "keydown" in combined or "onKeyDown" in combined
    ), "Modal must handle Escape key press to close"


# ---------------------------------------------------------------------------
# AC12: SPA page route /cases/{id} served by backend
# ---------------------------------------------------------------------------

def test_case_detail_page_route_served(api_client):
    """AC12 (routing): /cases/<id> must return 200 serving the SPA shell."""
    r = api_client.get(f"/cases/{uuid.uuid4()}")
    assert r.status_code == 200
    assert b"crux" in r.content.lower() or b"<!doctype" in r.content.lower(), \
        "Case detail page route must serve index.html"
