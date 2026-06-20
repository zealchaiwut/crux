"""Tests for issue #19: YouTube transcript fetcher."""
from __future__ import annotations

import pytest
from unittest.mock import MagicMock, patch


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_snippets(text: str = "Hello world content here.") -> list:
    """Build snippet objects matching the youtube-transcript-api v1 interface."""
    snippet = MagicMock()
    snippet.text = text
    return [snippet]


def _make_http_client(title: str = "Test Video Title") -> MagicMock:
    resp = MagicMock()
    resp.status_code = 200
    resp.json.return_value = {"title": title}
    client = MagicMock()
    client.get.return_value = resp
    return client


def _patch_api(snippets=None, side_effect=None):
    """Context manager that patches YouTubeTranscriptApi and configures its instance."""
    patcher = patch("app.research.fetchers.YouTubeTranscriptApi")
    mock_cls = patcher.start()
    if side_effect is not None:
        mock_cls.return_value.fetch.side_effect = side_effect
    else:
        mock_cls.return_value.fetch.return_value = snippets or _make_snippets()
    return patcher, mock_cls


# ---------------------------------------------------------------------------
# AC1: Accept both full YouTube URLs and bare video IDs
# ---------------------------------------------------------------------------

def test_youtube_fetcher_accepts_full_watch_url():
    """AC1: Accepts https://www.youtube.com/watch?v=VIDEO_ID format."""
    from app.research.fetchers import YouTubeTranscriptFetcher

    patcher, _ = _patch_api()
    try:
        fetcher = YouTubeTranscriptFetcher(budget=5, http_client=_make_http_client())
        result = fetcher.fetch("https://www.youtube.com/watch?v=dQw4w9WgXcQ")
    finally:
        patcher.stop()

    assert result is not None
    assert result.url == "https://www.youtube.com/watch?v=dQw4w9WgXcQ"


def test_youtube_fetcher_accepts_youtu_be_url():
    """AC1: Accepts https://youtu.be/VIDEO_ID short URL format."""
    from app.research.fetchers import YouTubeTranscriptFetcher

    patcher, _ = _patch_api()
    try:
        fetcher = YouTubeTranscriptFetcher(budget=5, http_client=_make_http_client())
        result = fetcher.fetch("https://youtu.be/dQw4w9WgXcQ")
    finally:
        patcher.stop()

    assert result is not None
    assert result.url == "https://www.youtube.com/watch?v=dQw4w9WgXcQ"


def test_youtube_fetcher_accepts_bare_video_id():
    """AC1: Accepts bare 11-character video ID."""
    from app.research.fetchers import YouTubeTranscriptFetcher

    patcher, _ = _patch_api()
    try:
        fetcher = YouTubeTranscriptFetcher(budget=5, http_client=_make_http_client())
        result = fetcher.fetch("dQw4w9WgXcQ")
    finally:
        patcher.stop()

    assert result is not None
    assert result.url == "https://www.youtube.com/watch?v=dQw4w9WgXcQ"


# ---------------------------------------------------------------------------
# AC2: Returns normalized document with non-empty url, title, text
# ---------------------------------------------------------------------------

def test_youtube_fetcher_returns_article_document():
    """AC2: Returns ArticleDocument with all three fields populated."""
    from app.research.fetchers import YouTubeTranscriptFetcher
    from app.research.types import ArticleDocument

    s1, s2 = MagicMock(), MagicMock()
    s1.text = "This is the first segment."
    s2.text = "This is the second segment."

    patcher, _ = _patch_api(snippets=[s1, s2])
    try:
        fetcher = YouTubeTranscriptFetcher(budget=5, http_client=_make_http_client("My Video"))
        result = fetcher.fetch("https://www.youtube.com/watch?v=dQw4w9WgXcQ")
    finally:
        patcher.stop()

    assert isinstance(result, ArticleDocument)
    assert result.url != ""
    assert result.title != ""
    assert result.text != ""


def test_youtube_fetcher_title_from_oembed():
    """AC2: Title is fetched via YouTube oEmbed and returned in document."""
    from app.research.fetchers import YouTubeTranscriptFetcher

    patcher, _ = _patch_api()
    try:
        fetcher = YouTubeTranscriptFetcher(
            budget=5, http_client=_make_http_client("Actual Video Title")
        )
        result = fetcher.fetch("dQw4w9WgXcQ")
    finally:
        patcher.stop()

    assert result is not None
    assert result.title == "Actual Video Title"


def test_youtube_fetcher_text_joins_transcript_segments():
    """AC2: text field concatenates all transcript segments."""
    from app.research.fetchers import YouTubeTranscriptFetcher

    s1, s2, s3 = MagicMock(), MagicMock(), MagicMock()
    s1.text, s2.text, s3.text = "Hello", "world", "content"

    patcher, _ = _patch_api(snippets=[s1, s2, s3])
    try:
        fetcher = YouTubeTranscriptFetcher(budget=5, http_client=_make_http_client())
        result = fetcher.fetch("dQw4w9WgXcQ")
    finally:
        patcher.stop()

    assert result is not None
    assert "Hello" in result.text
    assert "world" in result.text
    assert "content" in result.text


# ---------------------------------------------------------------------------
# AC3: url is canonical form regardless of input
# ---------------------------------------------------------------------------

def test_youtube_fetcher_canonical_url_from_watch_url():
    """AC3: Canonical URL produced from full watch URL."""
    from app.research.fetchers import YouTubeTranscriptFetcher

    patcher, _ = _patch_api()
    try:
        fetcher = YouTubeTranscriptFetcher(budget=5, http_client=_make_http_client())
        result = fetcher.fetch("https://www.youtube.com/watch?v=abcdefghijk")
    finally:
        patcher.stop()

    assert result is not None
    assert result.url == "https://www.youtube.com/watch?v=abcdefghijk"


def test_youtube_fetcher_canonical_url_from_bare_id():
    """AC3: Canonical URL produced from bare video ID."""
    from app.research.fetchers import YouTubeTranscriptFetcher

    patcher, _ = _patch_api()
    try:
        fetcher = YouTubeTranscriptFetcher(budget=5, http_client=_make_http_client())
        result = fetcher.fetch("abcdefghijk")
    finally:
        patcher.stop()

    assert result is not None
    assert result.url == "https://www.youtube.com/watch?v=abcdefghijk"


def test_youtube_fetcher_canonical_url_from_youtu_be():
    """AC3: Canonical URL produced from youtu.be short URL."""
    from app.research.fetchers import YouTubeTranscriptFetcher

    patcher, _ = _patch_api()
    try:
        fetcher = YouTubeTranscriptFetcher(budget=5, http_client=_make_http_client())
        result = fetcher.fetch("https://youtu.be/abcdefghijk")
    finally:
        patcher.stop()

    assert result is not None
    assert result.url == "https://www.youtube.com/watch?v=abcdefghijk"


# ---------------------------------------------------------------------------
# AC4: Returns None when transcript unavailable (captions off, age-gated, etc.)
# ---------------------------------------------------------------------------

def test_youtube_fetcher_returns_none_when_captions_disabled():
    """AC4: Returns None when captions are disabled (skip reason: captions off)."""
    from app.research.fetchers import YouTubeTranscriptFetcher
    from youtube_transcript_api import TranscriptsDisabled

    patcher, _ = _patch_api(side_effect=TranscriptsDisabled("dQw4w9WgXcQ"))
    try:
        fetcher = YouTubeTranscriptFetcher(budget=5)
        result = fetcher.fetch("https://www.youtube.com/watch?v=dQw4w9WgXcQ")
    finally:
        patcher.stop()

    assert result is None


def test_youtube_fetcher_returns_none_when_age_gated():
    """AC4: Returns None for age-gated content (skip reason: age-gated)."""
    from app.research.fetchers import YouTubeTranscriptFetcher
    from youtube_transcript_api import AgeRestricted

    patcher, _ = _patch_api(side_effect=AgeRestricted("dQw4w9WgXcQ"))
    try:
        fetcher = YouTubeTranscriptFetcher(budget=5)
        result = fetcher.fetch("https://www.youtube.com/watch?v=dQw4w9WgXcQ")
    finally:
        patcher.stop()

    assert result is None


def test_youtube_fetcher_returns_none_when_video_private():
    """AC4: Returns None when video is private or deleted."""
    from app.research.fetchers import YouTubeTranscriptFetcher
    from youtube_transcript_api import VideoUnavailable

    patcher, _ = _patch_api(side_effect=VideoUnavailable("dQw4w9WgXcQ"))
    try:
        fetcher = YouTubeTranscriptFetcher(budget=5)
        result = fetcher.fetch("https://www.youtube.com/watch?v=dQw4w9WgXcQ")
    finally:
        patcher.stop()

    assert result is None


def test_youtube_fetcher_does_not_raise_on_any_transcript_error():
    """AC4: No unhandled exception for any transcript retrieval failure."""
    from app.research.fetchers import YouTubeTranscriptFetcher

    patcher, _ = _patch_api(side_effect=RuntimeError("unexpected internal error"))
    try:
        fetcher = YouTubeTranscriptFetcher(budget=5)
        result = fetcher.fetch("https://www.youtube.com/watch?v=dQw4w9WgXcQ")
    finally:
        patcher.stop()

    assert result is None


# ---------------------------------------------------------------------------
# AC5: Budget enforcement
# ---------------------------------------------------------------------------

def test_youtube_fetcher_returns_none_when_budget_zero():
    """AC5: Returns None immediately when budget is 0 (exhausted before retrieval)."""
    from app.research.fetchers import YouTubeTranscriptFetcher

    with patch("app.research.fetchers.YouTubeTranscriptApi") as mock_cls:
        fetcher = YouTubeTranscriptFetcher(budget=0)
        result = fetcher.fetch("https://www.youtube.com/watch?v=dQw4w9WgXcQ")
        mock_cls.return_value.fetch.assert_not_called()

    assert result is None


def test_youtube_fetcher_decrements_budget_on_success():
    """AC5: Budget is consumed on a successful fetch."""
    from app.research.fetchers import YouTubeTranscriptFetcher

    patcher, _ = _patch_api()
    try:
        fetcher = YouTubeTranscriptFetcher(budget=3, http_client=_make_http_client())
        fetcher.fetch("dQw4w9WgXcQ")
    finally:
        patcher.stop()

    assert fetcher.budget == 2


def test_youtube_fetcher_exhausted_budget_blocks_api_call():
    """AC5: After budget reaches 0, subsequent fetches skip the API entirely."""
    from app.research.fetchers import YouTubeTranscriptFetcher

    with patch("app.research.fetchers.YouTubeTranscriptApi") as mock_cls:
        mock_cls.return_value.fetch.return_value = _make_snippets()

        http_client = _make_http_client()
        fetcher = YouTubeTranscriptFetcher(budget=1, http_client=http_client)
        fetcher.fetch("dQw4w9WgXcQ")  # consumes budget
        result = fetcher.fetch("dQw4w9WgXcQ")  # budget now 0

        assert mock_cls.return_value.fetch.call_count == 1

    assert result is None


# ---------------------------------------------------------------------------
# AC6: Registered/discoverable through the research-loop interface
# ---------------------------------------------------------------------------

def test_youtube_fetcher_importable_from_research_module():
    """AC6: YouTubeTranscriptFetcher is exported from app.research."""
    from app.research import YouTubeTranscriptFetcher
    assert YouTubeTranscriptFetcher is not None


def test_youtube_fetcher_satisfies_research_fetcher_protocol():
    """AC6: Conforms to ResearchFetcher protocol (has budget attribute)."""
    from app.research.fetchers import YouTubeTranscriptFetcher
    from app.research.types import ResearchFetcher

    fetcher = YouTubeTranscriptFetcher(budget=5)
    assert isinstance(fetcher, ResearchFetcher)


def test_youtube_fetcher_in_research_all():
    """AC6: YouTubeTranscriptFetcher is listed in app.research.__all__."""
    import app.research as research
    assert "YouTubeTranscriptFetcher" in research.__all__


# ---------------------------------------------------------------------------
# AC7: Invalid/malformed input handling
# ---------------------------------------------------------------------------

def test_youtube_fetcher_returns_none_for_malformed_url():
    """AC7: Returns None for a URL with a non-11-char video ID (INVALID000 = 10 chars)."""
    from app.research.fetchers import YouTubeTranscriptFetcher

    with patch("app.research.fetchers.YouTubeTranscriptApi") as mock_cls:
        fetcher = YouTubeTranscriptFetcher(budget=5)
        result = fetcher.fetch("https://www.youtube.com/watch?v=INVALID000")
        mock_cls.return_value.fetch.assert_not_called()

    assert result is None


def test_youtube_fetcher_returns_none_for_empty_string():
    """AC7: Returns None for empty string input."""
    from app.research.fetchers import YouTubeTranscriptFetcher

    with patch("app.research.fetchers.YouTubeTranscriptApi") as mock_cls:
        fetcher = YouTubeTranscriptFetcher(budget=5)
        result = fetcher.fetch("")
        mock_cls.return_value.fetch.assert_not_called()

    assert result is None


def test_youtube_fetcher_returns_none_for_non_youtube_url():
    """AC7: Returns None for a non-YouTube URL."""
    from app.research.fetchers import YouTubeTranscriptFetcher

    with patch("app.research.fetchers.YouTubeTranscriptApi") as mock_cls:
        fetcher = YouTubeTranscriptFetcher(budget=5)
        result = fetcher.fetch("https://www.example.com/video/12345")
        mock_cls.return_value.fetch.assert_not_called()

    assert result is None


def test_youtube_fetcher_returns_none_for_garbage_input():
    """AC7: Returns None for completely invalid string."""
    from app.research.fetchers import YouTubeTranscriptFetcher

    fetcher = YouTubeTranscriptFetcher(budget=5)
    result = fetcher.fetch("not-a-url-at-all!!!")

    assert result is None
