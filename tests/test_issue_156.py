"""Tests for issue #156: Colour SourceChip by support_status with verify actions.

AC coverage:
  AC1  – SourceChip reads support_status (supports/partial/contradicts/unverified) and applies
         green/amber/red/grey colours; no new colour tokens introduced.
  AC2  – Expanding a SourceChip reveals rationale text.
  AC3  – Each SourceChip includes a Verify button.
  AC4  – Each PlanCard includes a Verify all control.
  AC5  – After verification runs the chip reflects resolved support_status (API).
  AC6  – Accept and Dismiss/Override controls present in expanded chip JS.
  AC7  – Missing/null support_status defaults to unverified (grey) without JS error.
  AC8  – No new CSS colour tokens or chip variants beyond DESIGN.md §6/§7 palette.
  AC9  – Existing SourceChip link/tooltip/layout behaviour unaffected when support_status absent.
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


def _seed_plan_with_source(session, claim="supports hypothesis", kind="article"):
    """Seed Case→Plan→Source; return (plan, source)."""
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
        label="A",
        name="Plan A",
        mechanism="Test mechanism.",
        prior="0.5",
        current_rank=1,
    )
    session.add(plan)
    session.flush()
    source = models.Source(
        id=str(uuid.uuid4()),
        plan_id=plan.id,
        kind=kind,
        title="Test Source",
        url=None,
        claim=claim,
        citation="Author 2024",
    )
    session.add(source)
    session.commit()
    return plan, source


# ---------------------------------------------------------------------------
# AC1: _CHIP_COLORS map in JS uses the four canonical status values
# ---------------------------------------------------------------------------

def _chip_block(js, window=500):
    """Return the JS block starting at _CHIP_COLORS definition."""
    idx = js.find("_CHIP_COLORS")
    assert idx != -1, "_CHIP_COLORS must be defined in JS"
    return js[idx: idx + window]


def _source_chip_block(js, window=16000):
    """Return the JS block starting at the SourceChip function definition."""
    idx = js.find("function SourceChip")
    assert idx != -1, "function SourceChip must be defined in JS"
    return js[idx: idx + window]


def test_chip_colors_has_partial_key():
    """AC1: JS colour map must include 'partial' key (maps to amber)."""
    js = _read_combined_js()
    block = _chip_block(js)
    assert "partial" in block, "'partial' status must be referenced in JS colour map"
    idx = block.find("partial")
    surrounding = block[max(0, idx - 10): idx + 150]
    assert "amber" in surrounding, "'partial' status must map to amber colour"


def test_chip_colors_has_supports_green():
    """AC1: 'supports' status must map to green colour tokens."""
    js = _read_combined_js()
    block = _chip_block(js)
    assert "supports" in block, "'supports' key must be in _CHIP_COLORS"
    assert "green" in block, "'supports' must reference green colour token"


def test_chip_colors_has_contradicts_red():
    """AC1: 'contradicts' status must map to red colour tokens."""
    js = _read_combined_js()
    block = _chip_block(js)
    assert "contradicts" in block, "'contradicts' key must be in _CHIP_COLORS"
    assert "red" in block, "'contradicts' must reference red colour token"


def test_chip_colors_does_not_use_neutral_or_inconclusive():
    """AC1: legacy 'neutral'/'inconclusive' keys must not appear in the colour map."""
    js = _read_combined_js()
    block = _chip_block(js)
    assert "neutral" not in block, \
        "Legacy 'neutral' key must be replaced by 'partial' in _CHIP_COLORS"
    assert "inconclusive" not in block, \
        "Legacy 'inconclusive' key must be replaced by 'partial' in _CHIP_COLORS"


def test_status_label_has_partial():
    """AC1: _STATUS_LABEL must map 'partial' to a human-readable string."""
    js = _read_combined_js()
    idx = js.find("_STATUS_LABEL")
    assert idx != -1, "_STATUS_LABEL must be defined in JS"
    block = js[idx: idx + 300]
    assert "partial" in block, "'partial' must appear in _STATUS_LABEL"


def test_status_label_has_unverified():
    """AC1/AC7: _STATUS_LABEL must map 'unverified' to a human-readable string."""
    js = _read_combined_js()
    idx = js.find("_STATUS_LABEL")
    block = js[idx: idx + 300]
    assert "unverified" in block.lower() or "Unverified" in block, \
        "'unverified' must appear in _STATUS_LABEL"


# ---------------------------------------------------------------------------
# AC1: No new CSS colour tokens
# ---------------------------------------------------------------------------

def test_no_new_colour_tokens_in_css():
    """AC8: Only existing palette tokens used; no new --support-* or similar tokens added."""
    css = _read_combined_css()
    # No new colour custom properties that weren't in the original palette
    assert "--support-" not in css, "No new --support-* colour tokens should be introduced"
    assert "--status-" not in css, "No new --status-* colour tokens should be introduced"
    assert "--chip-" not in css, "No new --chip-* colour tokens should be introduced"


# ---------------------------------------------------------------------------
# AC2: Expanding a SourceChip shows rationale
# ---------------------------------------------------------------------------

def test_source_chip_shows_rationale_when_expanded():
    """AC2: Expanded SourceChip must display rationale text."""
    js = _read_combined_js()
    block = _source_chip_block(js)
    assert "rationale" in block, "SourceChip must render rationale text when expanded"


# ---------------------------------------------------------------------------
# AC3: Each SourceChip has a Verify button
# ---------------------------------------------------------------------------

def test_source_chip_has_verify_button():
    """AC3: SourceChip must contain a Verify button."""
    js = _read_combined_js()
    block = _source_chip_block(js)
    assert "Verify" in block, "SourceChip must include a Verify button"
    assert "handleVerify" in block or "run-verify" in block, \
        "SourceChip Verify button must trigger verification"


# ---------------------------------------------------------------------------
# AC4: PlanCard has Verify all control
# ---------------------------------------------------------------------------

def test_plan_card_has_verify_all_button():
    """AC4: PlanCard must include a 'Verify all' control."""
    js = _read_combined_js()
    assert "Verify all" in js or "verify-all" in js or "verifyAll" in js, \
        "PlanCard must include a 'Verify all' control"


# ---------------------------------------------------------------------------
# AC5: run-verify endpoint updates support_status (API)
# ---------------------------------------------------------------------------

def test_run_verify_source_updates_status(api_client, db_session):
    """AC5: POST /api/sources/{id}/run-verify updates support_status and returns it."""
    plan, source = _seed_plan_with_source(db_session, claim="supports hypothesis")
    r = api_client.post(f"/api/sources/{source.id}/run-verify")
    assert r.status_code == 200, r.text
    data = r.json()
    assert "support_status" in data, "Response must include support_status"
    assert data["support_status"] in ("supports", "partial", "contradicts", "unverified"), \
        "support_status must be one of the four canonical values"


def test_run_verify_all_updates_all_sources(api_client, db_session):
    """AC5: POST /api/plans/{id}/run-verify-all updates all sources and returns results."""
    from app import models
    plan, source1 = _seed_plan_with_source(db_session, claim="supports hypothesis")
    source2 = models.Source(
        id=str(uuid.uuid4()),
        plan_id=plan.id,
        kind="book",
        title="Book Source",
        url=None,
        claim="evidence confirms this",
        citation="Smith 2024",
    )
    db_session.add(source2)
    db_session.commit()

    r = api_client.post(f"/api/plans/{plan.id}/run-verify-all")
    assert r.status_code == 200, r.text
    data = r.json()
    assert "results" in data, "Response must include 'results'"
    assert len(data["results"]) == 2, "Both sources must be returned in results"
    for result in data["results"]:
        assert "support_status" in result
        assert result["support_status"] in ("supports", "partial", "contradicts", "unverified")


# ---------------------------------------------------------------------------
# AC6: Accept and Dismiss/Override controls in JS
# ---------------------------------------------------------------------------

def test_source_chip_has_accept_control():
    """AC6: SourceChip must include an Accept control for confirming auto-assigned verdicts."""
    js = _read_combined_js()
    block = _source_chip_block(js)
    assert "Accept" in block, "SourceChip must include an Accept control"
    assert "handleAccept" in block or "accept-status" in block, \
        "Accept control must call the accept-status handler"


def test_source_chip_has_override_control():
    """AC6: SourceChip must include a Dismiss/Override control for rejecting verdicts."""
    js = _read_combined_js()
    block = _source_chip_block(js)
    assert "Override" in block or "status-override" in block or "handleOverride" in block, \
        "SourceChip must include a Dismiss/Override control"


def test_override_select_uses_canonical_values():
    """AC6: Override select must offer the four canonical support_status values."""
    js = _read_combined_js()
    block = _source_chip_block(js)
    assert '"partial"' in block or "'partial'" in block, \
        "Override select must include 'partial' option"
    assert '"supports"' in block or "'supports'" in block, \
        "Override select must include 'supports' option"
    assert '"contradicts"' in block or "'contradicts'" in block, \
        "Override select must include 'contradicts' option"


def test_override_select_does_not_use_legacy_neutral():
    """AC6: Override select must not offer legacy 'neutral' option."""
    js = _read_combined_js()
    block = _source_chip_block(js)
    select_idx = block.find("<select")
    if select_idx == -1:
        select_idx = block.find("select")
    select_block = block[select_idx: select_idx + 600]
    assert "neutral" not in select_block, \
        "Override select must not contain legacy 'neutral' option — use 'partial' instead"


# ---------------------------------------------------------------------------
# AC7: Missing support_status defaults to grey (unverified) in JS without error
# ---------------------------------------------------------------------------

def test_chip_unverified_fallback_defined():
    """AC7: A fallback colour object for unverified/null status must be defined."""
    js = _read_combined_js()
    assert "_CHIP_UNVERIFIED" in js or "unverified" in js, \
        "A fallback grey colour for unverified status must be defined in JS"


def test_chip_colors_fallback_uses_grey_tokens():
    """AC7: The unverified fallback must use border/surface-2/text-muted tokens (grey)."""
    js = _read_combined_js()
    idx = js.find("_CHIP_UNVERIFIED")
    if idx == -1:
        # Accept if unverified is handled inline via _CHIP_COLORS fallback
        idx = js.find("unverified")
    assert idx != -1
    block = js[idx: idx + 200]
    # Should reference border/surface/muted for grey appearance
    has_grey = (
        "border" in block or "surface" in block or "muted" in block or
        "var(--border)" in block or "var(--surface" in block
    )
    assert has_grey, "Unverified/grey fallback must use neutral border/surface tokens"


# ---------------------------------------------------------------------------
# AC5: status-override API endpoint
# ---------------------------------------------------------------------------

def test_status_override_endpoint_sets_manually_overridden(api_client, db_session):
    """AC6: PATCH /api/sources/{id}/status-override sets manually_overridden=True."""
    plan, source = _seed_plan_with_source(db_session)
    r = api_client.patch(
        f"/api/sources/{source.id}/status-override",
        json={"support_status": "partial", "rationale": "Manually set to partial."},
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["support_status"] == "partial"
    assert data["manually_overridden"] is True


def test_status_override_accepts_all_four_values(api_client, db_session):
    """AC6: status-override accepts all four canonical values."""
    for status in ("supports", "partial", "contradicts", "unverified"):
        plan, source = _seed_plan_with_source(db_session)
        r = api_client.patch(
            f"/api/sources/{source.id}/status-override",
            json={"support_status": status, "rationale": f"Override to {status}."},
        )
        assert r.status_code == 200, f"status-override must accept '{status}': {r.text}"
        assert r.json()["support_status"] == status


def test_accept_status_clears_manually_overridden(api_client, db_session):
    """AC6: POST /api/sources/{id}/accept-status clears the manually_overridden flag."""
    plan, source = _seed_plan_with_source(db_session)
    # First override manually
    api_client.patch(
        f"/api/sources/{source.id}/status-override",
        json={"support_status": "partial", "rationale": "Manual."},
    )
    # Then accept (clear override)
    r = api_client.post(f"/api/sources/{source.id}/accept-status")
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["manually_overridden"] is False, \
        "accept-status must clear the manually_overridden flag"


# ---------------------------------------------------------------------------
# AC9: Existing SourceChip behaviour unaffected when support_status absent
# ---------------------------------------------------------------------------

def test_source_chip_link_and_layout_intact():
    """AC9: Existing target=_blank link and layout classes remain in SourceChip."""
    js = _read_combined_js()
    block = _source_chip_block(js)
    assert "_blank" in block, "SourceChip must still include target='_blank' for URL links"
    assert "className" in block, "SourceChip must still use className for layout"


def test_source_chip_default_status_when_absent(api_client, db_session):
    """AC7/AC9: Source created without support_status defaults to 'unverified' in API response."""
    plan, source = _seed_plan_with_source(db_session)
    # Fresh source has no explicit support_status set — should default to 'unverified'
    from app import models
    db_session.refresh(source)
    assert source.support_status == "unverified", \
        "New source must default to 'unverified' support_status"
