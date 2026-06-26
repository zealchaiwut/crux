"""Tests for issue #112: Document override state persistence behavior for navigation.

AC coverage:
  AC1 – A code comment is added near the currentStatus/currentOverridden state declarations
         (or the useEffect that syncs them) explaining that override state is intentional
         local state and will reset on parent PlanCard unmount/remount.
  AC2 – The comment explicitly states what triggers a reset (parent unmount, e.g. after
         case detail refetch).
  AC3 – The comment describes the expected user-facing consequence: overrides do not survive
         a full PlanCard remount, but are restored from the DB after a refetch.
  AC5 – At least one test verifies the reset-on-remount behavior is intentional — the DB
         stores the override so a refetch after remount correctly restores it.
"""
import os
import pathlib
import uuid

import pytest

os.environ.setdefault("AUTH_SECRET", "test_auth_secret_12345678901")
os.environ.setdefault("CRUX_REQUIRE_AUTH", "1")

CASES_JS = pathlib.Path(__file__).parent.parent / "app" / "static" / "js" / "cases.js"


def _src() -> str:
    return CASES_JS.read_text()


# ---------------------------------------------------------------------------
# Helpers — locate the SourceChip state block in cases.js
# ---------------------------------------------------------------------------

def _sourcechip_state_block(src: str) -> str:
    """Return the slice of cases.js from the SourceChip function definition through
    the first useEffect (which syncs state from props), so AC checks can scan it."""
    start = src.find("function SourceChip(")
    if start == -1:
        return ""
    # Extend past the useEffect that syncs currentStatus/currentOverridden
    effect_marker = "}, [initialStatus, initialRationale, initialOverridden]);"
    end = src.find(effect_marker, start)
    if end == -1:
        return src[start:]
    return src[start : end + len(effect_marker)]


# ---------------------------------------------------------------------------
# AC1 — Comment near state declarations explains intentional local state / remount reset
# ---------------------------------------------------------------------------

class TestCommentPresentNearStateDeclarations:
    def test_comment_exists_near_sourcechip_state(self):
        """A comment must be present in the SourceChip block covering currentStatus /
        currentOverridden and must mention that state resets on remount."""
        block = _sourcechip_state_block(_src())
        assert block, "SourceChip function not found in cases.js"

        block_lower = block.lower()
        # The comment must mention intentional/local state
        has_intentional = "intentional" in block_lower or "local state" in block_lower
        assert has_intentional, (
            "No comment found near SourceChip state explaining that override state is "
            "intentional local state (expected 'intentional' or 'local state' in the block)."
        )

    def test_comment_mentions_remount_reset(self):
        """The comment must make clear that state resets on remount."""
        block = _sourcechip_state_block(_src())
        block_lower = block.lower()
        has_reset = "reset" in block_lower or "clears" in block_lower or "cleared" in block_lower
        assert has_reset, (
            "Comment near SourceChip state must mention that override state resets "
            "(expected 'reset', 'clears', or 'cleared')."
        )


# ---------------------------------------------------------------------------
# AC2 — Comment states what triggers a reset (parent unmount / remount / refetch)
# ---------------------------------------------------------------------------

class TestCommentDescribesTrigger:
    def test_comment_mentions_unmount_or_remount(self):
        """The comment must identify the trigger: parent unmount or remount."""
        block = _sourcechip_state_block(_src())
        block_lower = block.lower()
        has_trigger = "unmount" in block_lower or "remount" in block_lower
        assert has_trigger, (
            "Comment near SourceChip state must name the reset trigger "
            "(expected 'unmount' or 'remount' in the block)."
        )

    def test_comment_mentions_refetch_as_example(self):
        """The comment should give refetch as a concrete example trigger."""
        block = _sourcechip_state_block(_src())
        block_lower = block.lower()
        has_refetch = "refetch" in block_lower or "re-fetch" in block_lower or "fetch" in block_lower
        assert has_refetch, (
            "Comment should mention refetch as an example trigger for the state reset."
        )


# ---------------------------------------------------------------------------
# AC3 — Comment describes user-facing consequence and DB restoration
# ---------------------------------------------------------------------------

class TestCommentDescribesConsequence:
    def test_comment_mentions_db_restoration(self):
        """The comment should note that the DB preserves the override and it is
        restored from props after any refetch — so users do not lose overrides permanently."""
        block = _sourcechip_state_block(_src())
        block_lower = block.lower()
        # Must mention DB or persistence so the reader understands state is durable
        has_persistence = (
            "db" in block_lower
            or "database" in block_lower
            or "persist" in block_lower
            or "patch" in block_lower
        )
        assert has_persistence, (
            "Comment should mention DB/persistence so developers understand overrides "
            "are not lost permanently — they are restored from DB-sourced props after refetch."
        )


# ---------------------------------------------------------------------------
# AC5 — Backend test: override survives a case-detail refetch (simulated remount)
#
# This is the intentional design: overrides are stored in the DB so after any
# PlanCard remount triggered by a refetch, the component receives fresh DB-sourced
# props and the useEffect re-syncs local state to the stored override.
# ---------------------------------------------------------------------------

def _make_engine():
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
    engine = _make_engine()
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


def _seed(session):
    """Return (case_id, plan_id, source_id)."""
    from app import models

    case_id = str(uuid.uuid4())
    plan_id = str(uuid.uuid4())
    sid = str(uuid.uuid4())

    session.add(models.Case(
        id=case_id,
        raw_problem="Test problem",
        sharpened="Sharpened",
        stage="gather",
    ))
    session.add(models.Plan(
        id=plan_id,
        case_id=case_id,
        label="A",
        name="Plan A",
        mechanism="mech",
        prior="0.50",
    ))
    session.add(models.Source(
        id=sid,
        plan_id=plan_id,
        kind="article",
        title="Source 1",
        url="https://example.com/s1",
        claim="Claim 1",
        citation="Cit 1",
    ))
    session.commit()
    return case_id, plan_id, sid


class TestOverrideSurvivesRemountViaDbRefetch:
    """AC5: verifies the intentional design — override state resets on PlanCard remount,
    but because the override is persisted to the DB, a case-detail refetch (which is what
    triggers the remount in practice) restores the correct override state in the component.

    We simulate the remount by fetching the case detail endpoint twice: once before and
    once after applying an override.  The second fetch represents the fresh DB-sourced
    props that SourceChip would receive on remount — confirming the override is correctly
    restored automatically.
    """

    def test_override_present_in_case_detail_after_patch(self, api_client, db_session):
        """After PATCH status-override, case detail refetch returns the override — so
        SourceChip's useEffect will re-sync to the correct overridden state on remount."""
        case_id, _, sid = _seed(db_session)

        # Simulate PlanCard mount (initial state — no override)
        initial = api_client.get(f"/api/cases/{case_id}")
        assert initial.status_code == 200
        sources_before = initial.json()["plans"][0]["sources"]
        src_before = next(s for s in sources_before if s["id"] == sid)
        assert src_before["manually_overridden"] is False

        # User applies an override (stored in DB)
        patch = api_client.patch(
            f"/api/sources/{sid}/status-override",
            json={"support_status": "contradicts", "rationale": "Human override."},
        )
        assert patch.status_code == 200

        # Simulate PlanCard remount triggered by case-detail refetch
        after = api_client.get(f"/api/cases/{case_id}")
        assert after.status_code == 200
        sources_after = after.json()["plans"][0]["sources"]
        src_after = next(s for s in sources_after if s["id"] == sid)

        # The fresh DB-sourced props carry the override — useEffect will restore state
        assert src_after["manually_overridden"] is True, (
            "After a case-detail refetch (simulated remount), the source must carry "
            "manually_overridden=True so SourceChip's useEffect restores the override state."
        )
        assert src_after["support_status"] == "contradicts"

    def test_override_absent_before_patch_confirming_reset_is_observable(
        self, api_client, db_session
    ):
        """If no override was applied before PlanCard unmounts, the remounted component
        correctly shows no override — confirming local state is reset to DB truth on remount."""
        case_id, _, sid = _seed(db_session)

        resp = api_client.get(f"/api/cases/{case_id}")
        assert resp.status_code == 200
        src = resp.json()["plans"][0]["sources"][0]
        # No override in DB → remount would show no override (state reset is correct)
        assert src["manually_overridden"] is False
        assert src["support_status"] == "unverified"
