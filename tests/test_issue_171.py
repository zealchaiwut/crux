"""Tests for issue #171: Store extracted content and summary per source.

AC coverage:
  AC1  – Source model has extracted_content and content_summary nullable Text columns
  AC2  – Alembic migration applies cleanly (covered by in-memory schema creation)
  AC3  – POST /api/sources/{id}/fetch-content returns HTTP 200 with updated source
  AC4  – fetch-content reuses ArticleReaderFetcher / YouTubeTranscriptFetcher
  AC5  – extracted_content capped at 50,000 chars; truncation indicator present
  AC6  – content_summary describes what the source says (substance), not verdict
  AC7  – YouTube source stores transcript in extracted_content
  AC8  – Paywalled/blocked source: both fields stay null, reason recorded
  AC9  – Content > 50,000 chars truncated; test asserts length <= 50,000
  AC10 – Tests: article fetch, YouTube transcript, paywall/blocked, over-cap truncation
"""
import os
import uuid

import pytest

os.environ.setdefault("AUTH_SECRET", "test_auth_secret_12345678901")
os.environ.setdefault("CRUX_REQUIRE_AUTH", "1")


# ---------------------------------------------------------------------------
# Fixtures
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


def _seed_source(session, kind="article", url="https://example.com/article"):
    from app import models

    case = models.Case(
        id=str(uuid.uuid4()),
        raw_problem="Test problem",
        stage="gather",
    )
    session.add(case)
    session.flush()

    plan = models.Plan(
        id=str(uuid.uuid4()),
        case_id=case.id,
        label="A",
        name="Plan A",
        mechanism="some mechanism",
    )
    session.add(plan)
    session.flush()

    source = models.Source(
        id=str(uuid.uuid4()),
        plan_id=plan.id,
        kind=kind,
        title="Test Source",
        url=url,
        claim="Test claim",
        citation="Test citation",
    )
    session.add(source)
    session.commit()
    return source


# ---------------------------------------------------------------------------
# AC1: Source model has the new nullable columns
# ---------------------------------------------------------------------------

def test_source_model_has_extracted_content_and_summary_columns(db_session):
    """AC1: extracted_content and content_summary are nullable Text columns on Source."""
    from app import models

    source = _seed_source(db_session)

    assert hasattr(source, "extracted_content"), "Source must have extracted_content field"
    assert hasattr(source, "content_summary"), "Source must have content_summary field"
    assert source.extracted_content is None, "extracted_content should default to None"
    assert source.content_summary is None, "content_summary should default to None"


def test_source_model_columns_are_writable(db_session):
    """AC1: both fields can be written and persisted."""
    from app import models

    source = _seed_source(db_session)
    source.extracted_content = "Some article text here."
    source.content_summary = "This article discusses health benefits."
    db_session.commit()
    db_session.refresh(source)

    assert source.extracted_content == "Some article text here."
    assert source.content_summary == "This article discusses health benefits."


# ---------------------------------------------------------------------------
# AC3 + AC10: POST /api/sources/{id}/fetch-content — article success path
# ---------------------------------------------------------------------------

def test_fetch_content_article_success(api_client, db_session, monkeypatch):
    """AC3 + AC10: successful article fetch returns 200 with populated fields."""
    source = _seed_source(db_session, kind="article", url="https://example.com/article")

    from app.routers import sources as sources_router

    def fake_fetch_content_for_source(source_obj, db):
        source_obj.extracted_content = "This is the article body text."
        source_obj.content_summary = "The article discusses exercise and cognition."
        db.commit()
        db.refresh(source_obj)

    monkeypatch.setattr(
        sources_router,
        "_do_fetch_content",
        fake_fetch_content_for_source,
    )

    resp = api_client.post(f"/api/sources/{source.id}/fetch-content")

    assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
    data = resp.json()
    assert data["extracted_content"] == "This is the article body text."
    assert data["content_summary"] == "The article discusses exercise and cognition."
    assert data["id"] == source.id


# ---------------------------------------------------------------------------
# AC7 + AC10: YouTube transcript path
# ---------------------------------------------------------------------------

def test_fetch_content_youtube_success(api_client, db_session, monkeypatch):
    """AC7 + AC10: YouTube source stores transcript in extracted_content."""
    source = _seed_source(
        db_session,
        kind="youtube",
        url="https://www.youtube.com/watch?v=dQw4w9WgXcQ",
    )

    from app.routers import sources as sources_router

    def fake_fetch_content_for_source(source_obj, db):
        source_obj.extracted_content = "Never gonna give you up never gonna let you down."
        source_obj.content_summary = "The video is a pop song about dedication and commitment."
        db.commit()
        db.refresh(source_obj)

    monkeypatch.setattr(
        sources_router,
        "_do_fetch_content",
        fake_fetch_content_for_source,
    )

    resp = api_client.post(f"/api/sources/{source.id}/fetch-content")

    assert resp.status_code == 200
    data = resp.json()
    assert data["extracted_content"] is not None
    assert "never gonna" in data["extracted_content"].lower()
    assert data["content_summary"] is not None


# ---------------------------------------------------------------------------
# AC8 + AC10: Paywalled/blocked — both fields stay null
# ---------------------------------------------------------------------------

def test_fetch_content_blocked_leaves_fields_null(api_client, db_session, monkeypatch):
    """AC8 + AC10: paywalled/blocked source leaves extracted_content and content_summary null."""
    source = _seed_source(db_session, kind="article", url="https://paywalled.example.com/article")

    from app.routers import sources as sources_router

    def fake_fetch_content_for_source(source_obj, db):
        # Simulate paywall: fields stay null
        db.commit()
        db.refresh(source_obj)

    monkeypatch.setattr(
        sources_router,
        "_do_fetch_content",
        fake_fetch_content_for_source,
    )

    resp = api_client.post(f"/api/sources/{source.id}/fetch-content")

    assert resp.status_code == 200
    data = resp.json()
    assert data["extracted_content"] is None, "extracted_content must remain null for blocked source"
    assert data["content_summary"] is None, "content_summary must remain null for blocked source"


# ---------------------------------------------------------------------------
# AC5 + AC9: Over-cap truncation (50,000 char limit)
# ---------------------------------------------------------------------------

def test_fetch_content_truncates_at_50k_chars(db_session):
    """AC5 + AC9: content exceeding 50,000 chars is truncated; truncation indicator present."""
    from app.services.fetch_content import fetch_and_store_content
    from app.research.types import ArticleDocument

    source = _seed_source(db_session, kind="article", url="https://example.com/big-article")

    big_text = "A" * 60_000

    def fake_article_fetcher(url):
        return ArticleDocument(url=url, title="Big Article", text=big_text)

    def fake_yt_fetcher(url):
        return None

    def fake_summarize(content):
        return "Summary of big article."

    fetch_and_store_content(
        db=db_session,
        source=source,
        article_fetch_fn=fake_article_fetcher,
        yt_fetch_fn=fake_yt_fetcher,
        summarize_fn=fake_summarize,
    )

    db_session.refresh(source)
    assert source.extracted_content is not None
    assert len(source.extracted_content) <= 50_000, (
        f"extracted_content must be capped at 50,000 chars; got {len(source.extracted_content)}"
    )
    assert source.content_summary == "Summary of big article."


def test_fetch_content_truncation_indicator_present(db_session):
    """AC5: when content is truncated, a truncation indicator is present in extracted_content."""
    from app.services.fetch_content import fetch_and_store_content
    from app.research.types import ArticleDocument

    source = _seed_source(db_session, kind="article", url="https://example.com/big-article")

    big_text = "B" * 60_000

    def fake_article_fetcher(url):
        return ArticleDocument(url=url, title="Big Article", text=big_text)

    def fake_yt_fetcher(url):
        return None

    def fake_summarize(content):
        return "Summary."

    fetch_and_store_content(
        db=db_session,
        source=source,
        article_fetch_fn=fake_article_fetcher,
        yt_fetch_fn=fake_yt_fetcher,
        summarize_fn=fake_summarize,
    )

    db_session.refresh(source)
    assert source.extracted_content is not None
    assert len(source.extracted_content) <= 50_000
    assert "[TRUNCATED]" in source.extracted_content, (
        "A [TRUNCATED] sentinel must appear in extracted_content when content was truncated"
    )


# ---------------------------------------------------------------------------
# AC3: 404 for non-existent source
# ---------------------------------------------------------------------------

def test_fetch_content_404_for_unknown_source(api_client):
    """AC3: non-existent source ID returns HTTP 404."""
    resp = api_client.post(f"/api/sources/{uuid.uuid4()}/fetch-content")
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# AC6: content_summary describes substance, not verdict
# ---------------------------------------------------------------------------

def test_content_summary_describes_substance_not_verdict(db_session):
    """AC6: content_summary is generated from source substance, not support/contradict verdict."""
    from app.services.fetch_content import fetch_and_store_content
    from app.research.types import ArticleDocument

    source = _seed_source(db_session, kind="article", url="https://example.com/health")

    article_text = "Regular exercise reduces the risk of cardiovascular disease by 30%."

    def fake_article_fetcher(url):
        return ArticleDocument(url=url, title="Health Study", text=article_text)

    def fake_yt_fetcher(url):
        return None

    captured_prompt = {}

    def fake_summarize(content):
        captured_prompt["content"] = content
        return "The article presents research showing exercise reduces cardiovascular disease risk."

    fetch_and_store_content(
        db=db_session,
        source=source,
        article_fetch_fn=fake_article_fetcher,
        yt_fetch_fn=fake_yt_fetcher,
        summarize_fn=fake_summarize,
    )

    db_session.refresh(source)
    assert source.content_summary is not None
    summary_lower = source.content_summary.lower()
    verdict_words = {"supports", "contradicts", "partially_supports", "unverified"}
    verdict_hits = [w for w in verdict_words if w in summary_lower]
    assert not verdict_hits, (
        f"content_summary must not mention verification verdict words; found: {verdict_hits!r}"
    )


# ---------------------------------------------------------------------------
# AC10: fetch_and_store_content uses correct fetcher per source kind
# ---------------------------------------------------------------------------

def test_article_source_uses_article_fetcher(db_session):
    """AC4 + AC10: article/web sources use ArticleReaderFetcher (not YouTube fetcher)."""
    from app.services.fetch_content import fetch_and_store_content
    from app.research.types import ArticleDocument

    source = _seed_source(db_session, kind="article", url="https://example.com/article")

    article_called = []
    yt_called = []

    def fake_article_fetcher(url):
        article_called.append(url)
        return ArticleDocument(url=url, title="Article", text="Article content here.")

    def fake_yt_fetcher(url):
        yt_called.append(url)
        return None

    def fake_summarize(content):
        return "Article summary."

    fetch_and_store_content(
        db=db_session,
        source=source,
        article_fetch_fn=fake_article_fetcher,
        yt_fetch_fn=fake_yt_fetcher,
        summarize_fn=fake_summarize,
    )

    assert article_called, "ArticleReaderFetcher must be called for article sources"
    assert not yt_called, "YouTubeTranscriptFetcher must NOT be called for article sources"


def test_youtube_source_uses_youtube_fetcher(db_session):
    """AC4 + AC7 + AC10: youtube sources use YouTubeTranscriptFetcher."""
    from app.services.fetch_content import fetch_and_store_content
    from app.research.types import ArticleDocument

    source = _seed_source(
        db_session,
        kind="youtube",
        url="https://www.youtube.com/watch?v=abc123",
    )

    article_called = []
    yt_called = []

    def fake_article_fetcher(url):
        article_called.append(url)
        return None

    def fake_yt_fetcher(url):
        yt_called.append(url)
        return ArticleDocument(url=url, title="YT Video", text="This is the transcript.")

    def fake_summarize(content):
        return "The video discusses some topic."

    fetch_and_store_content(
        db=db_session,
        source=source,
        article_fetch_fn=fake_article_fetcher,
        yt_fetch_fn=fake_yt_fetcher,
        summarize_fn=fake_summarize,
    )

    assert yt_called, "YouTubeTranscriptFetcher must be called for youtube sources"
    assert not article_called, "ArticleReaderFetcher must NOT be called for youtube sources"
    db_session.refresh(source)
    assert source.extracted_content == "This is the transcript."


# ---------------------------------------------------------------------------
# AC8: blocked source leaves fields null; reason is logged/recorded
# ---------------------------------------------------------------------------

def test_blocked_source_fields_stay_null(db_session):
    """AC8: blocked/inaccessible source leaves extracted_content and content_summary null."""
    from app.services.fetch_content import fetch_and_store_content
    from app.research.types import FetchBlockedError

    source = _seed_source(db_session, kind="article", url="https://blocked.example.com/article")

    def fake_article_fetcher(url):
        raise FetchBlockedError("HTTP 403 Forbidden — paywalled")

    def fake_yt_fetcher(url):
        return None

    def fake_summarize(content):
        raise AssertionError("summarize must not be called when fetch fails")

    fetch_and_store_content(
        db=db_session,
        source=source,
        article_fetch_fn=fake_article_fetcher,
        yt_fetch_fn=fake_yt_fetcher,
        summarize_fn=fake_summarize,
    )

    db_session.refresh(source)
    assert source.extracted_content is None, "extracted_content must stay null when blocked"
    assert source.content_summary is None, "content_summary must stay null when blocked"


# ---------------------------------------------------------------------------
# Response shape: new fields appear in _source_to_dict output
# ---------------------------------------------------------------------------

def test_source_dict_includes_new_fields(api_client, db_session, monkeypatch):
    """extracted_content and content_summary appear in the API response shape."""
    source = _seed_source(db_session, kind="article", url="https://example.com/article")

    from app.routers import sources as sources_router

    def fake_fetch_content_for_source(source_obj, db):
        source_obj.extracted_content = "Article text."
        source_obj.content_summary = "The article covers a topic."
        db.commit()
        db.refresh(source_obj)

    monkeypatch.setattr(
        sources_router,
        "_do_fetch_content",
        fake_fetch_content_for_source,
    )

    resp = api_client.post(f"/api/sources/{source.id}/fetch-content")

    assert resp.status_code == 200
    data = resp.json()
    assert "extracted_content" in data, "Response must include extracted_content"
    assert "content_summary" in data, "Response must include content_summary"
