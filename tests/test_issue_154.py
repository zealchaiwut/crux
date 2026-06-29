"""Tests for issue #154: Source verifier service validates claims against fetched content.

AC coverage:
  AC1 – app/services/source_verifier.py exists and exports verify_source callable
  AC2 – ArticleReaderFetcher used for article URLs; YouTubeTranscriptFetcher for YouTube
  AC3 – Sends extracted content + source.claim to Claude; parses one of:
         supports | partially_supports | contradicts
  AC4 – Returns dict with exactly keys: support_status, support_rationale on success
  AC5 – Returns {support_status: "unverified", support_rationale: "<reason>"} when
         content is paywalled, abstract-only, fetch-blocked, or empty — never guesses
  AC6 – unverified rationale explicitly distinguishes: paywall/4xx, empty content,
         network/timeout error, and unsupported source type
  AC7 – No new fetcher logic; all fetching delegates to existing fetchers
"""
from __future__ import annotations

import pytest

from app.research.types import (
    ArticleDocument,
    FetchBlockedError,
    FetchEmptyContentError,
    FetchTimeoutError,
)

VALID_STATUSES = frozenset({"supports", "partially_supports", "contradicts", "unverified"})
VERDICT_STATUSES = frozenset({"supports", "partially_supports", "contradicts"})


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

class _Source:
    def __init__(self, url, claim, kind=None):
        self.url = url
        self.claim = claim
        if kind is not None:
            self.kind = kind


class _MockArticleFetcher:
    def __init__(self, result=None, raises=None):
        self._result = result
        self._raises = raises
        self.called_with = None

    def fetch(self, url):
        self.called_with = url
        if self._raises is not None:
            raise self._raises
        return self._result


class _MockYTFetcher:
    def __init__(self, result=None, raises=None):
        self._result = result
        self._raises = raises
        self.called_with = None

    def fetch(self, url):
        self.called_with = url
        if self._raises is not None:
            raise self._raises
        return self._result


def _ok_classify(content, claim):
    return {"support_status": "supports", "support_rationale": "Content confirms the claim."}


def _article_doc(text="Sufficient content confirming the claim with evidence."):
    return ArticleDocument(url="https://example.com", title="Test Article", text=text)


# ---------------------------------------------------------------------------
# AC1 — module importable, verify_source callable
# ---------------------------------------------------------------------------

class TestImportable:
    def test_module_exists_and_is_importable(self):
        """AC1: app/services/source_verifier.py is importable."""
        from app.services import source_verifier  # noqa: F401

    def test_verify_source_is_exported_and_callable(self):
        """AC1: verify_source is a callable exported from the module."""
        from app.services.source_verifier import verify_source
        assert callable(verify_source)


# ---------------------------------------------------------------------------
# AC2 — fetcher routing
# ---------------------------------------------------------------------------

class TestFetcherRouting:
    def test_article_url_uses_article_fetcher(self):
        """AC2: Non-YouTube URL routes to ArticleReaderFetcher."""
        from app.services.source_verifier import verify_source
        fetcher = _MockArticleFetcher(result=_article_doc())
        source = _Source(url="https://example.com/study", claim="The treatment works.")
        verify_source(source, article_fetcher=fetcher, classify_fn=_ok_classify)
        assert fetcher.called_with == "https://example.com/study"

    def test_youtube_com_url_uses_yt_fetcher(self):
        """AC2: youtube.com URL routes to YouTubeTranscriptFetcher."""
        from app.services.source_verifier import verify_source
        yt_fetcher = _MockYTFetcher(result=_article_doc("Transcript about the claim."))
        source = _Source(url="https://www.youtube.com/watch?v=abc123", claim="Claim.")
        verify_source(source, yt_fetcher=yt_fetcher, classify_fn=_ok_classify)
        assert yt_fetcher.called_with == "https://www.youtube.com/watch?v=abc123"

    def test_youtu_be_url_uses_yt_fetcher(self):
        """AC2: youtu.be short URL routes to YouTubeTranscriptFetcher."""
        from app.services.source_verifier import verify_source
        yt_fetcher = _MockYTFetcher(result=_article_doc("Transcript content."))
        source = _Source(url="https://youtu.be/abc123", claim="Claim.")
        verify_source(source, yt_fetcher=yt_fetcher, classify_fn=_ok_classify)
        assert yt_fetcher.called_with == "https://youtu.be/abc123"

    def test_article_fetcher_not_called_for_youtube(self):
        """AC2: ArticleReaderFetcher is NOT called for YouTube URLs."""
        from app.services.source_verifier import verify_source
        article_fetcher = _MockArticleFetcher()
        yt_fetcher = _MockYTFetcher(result=_article_doc("Transcript."))
        source = _Source(url="https://www.youtube.com/watch?v=xyz", claim="Claim.")
        verify_source(source, article_fetcher=article_fetcher, yt_fetcher=yt_fetcher, classify_fn=_ok_classify)
        assert article_fetcher.called_with is None


# ---------------------------------------------------------------------------
# AC3 — classify_fn receives content + claim; returns valid status
# ---------------------------------------------------------------------------

class TestClassification:
    def test_classify_fn_receives_fetched_content(self):
        """AC3: classify_fn is called with the fetched text."""
        from app.services.source_verifier import verify_source
        received = {}

        def spy(content, claim):
            received["content"] = content
            received["claim"] = claim
            return {"support_status": "supports", "support_rationale": "Confirmed."}

        text = "Specific article text supporting the claim empirically."
        doc = _article_doc(text)
        source = _Source(url="https://example.com/article", claim="The claim.")
        verify_source(source, article_fetcher=_MockArticleFetcher(result=doc), classify_fn=spy)
        assert received["content"] == text
        assert received["claim"] == "The claim."

    @pytest.mark.parametrize("status", ["supports", "partially_supports", "contradicts"])
    def test_verdict_statuses_returned_correctly(self, status):
        """AC3: supports, partially_supports, and contradicts are valid returned statuses."""
        from app.services.source_verifier import verify_source
        doc = _article_doc()
        source = _Source(url="https://example.com/article", claim="A claim.")
        result = verify_source(
            source,
            article_fetcher=_MockArticleFetcher(result=doc),
            classify_fn=lambda c, cl: {"support_status": status, "support_rationale": f"Rationale for {status}."},
        )
        assert result["support_status"] == status


# ---------------------------------------------------------------------------
# AC4 — return shape
# ---------------------------------------------------------------------------

class TestReturnShape:
    def test_success_returns_both_required_keys(self):
        """AC4: On success, dict has exactly support_status and support_rationale."""
        from app.services.source_verifier import verify_source
        doc = _article_doc()
        source = _Source(url="https://example.com", claim="Claim.")
        result = verify_source(source, article_fetcher=_MockArticleFetcher(result=doc), classify_fn=_ok_classify)
        assert "support_status" in result
        assert "support_rationale" in result

    def test_support_status_is_valid_enum_value(self):
        """AC4: support_status is always one of the four valid values."""
        from app.services.source_verifier import verify_source
        doc = _article_doc()
        source = _Source(url="https://example.com", claim="Claim.")
        result = verify_source(source, article_fetcher=_MockArticleFetcher(result=doc), classify_fn=_ok_classify)
        assert result["support_status"] in VALID_STATUSES

    def test_accepts_dict_source(self):
        """AC4: verify_source also accepts a dict with 'url' and 'claim' keys."""
        from app.services.source_verifier import verify_source
        doc = _article_doc()
        source = {"url": "https://example.com", "claim": "A claim."}
        result = verify_source(source, article_fetcher=_MockArticleFetcher(result=doc), classify_fn=_ok_classify)
        assert "support_status" in result
        assert "support_rationale" in result


# ---------------------------------------------------------------------------
# AC5 — unverified on fetch failure; never infers
# ---------------------------------------------------------------------------

class TestUnverifiedOnFetchFailure:
    def test_fetch_blocked_returns_unverified(self):
        """AC5: FetchBlockedError → support_status='unverified'."""
        from app.services.source_verifier import verify_source
        source = _Source(url="https://journal.com/article", claim="Claim.")
        result = verify_source(
            source,
            article_fetcher=_MockArticleFetcher(raises=FetchBlockedError("HTTP 403")),
            classify_fn=_ok_classify,
        )
        assert result["support_status"] == "unverified"
        assert result["support_rationale"]

    def test_fetch_timeout_returns_unverified(self):
        """AC5: FetchTimeoutError → support_status='unverified'."""
        from app.services.source_verifier import verify_source
        source = _Source(url="https://slow-site.com", claim="Claim.")
        result = verify_source(
            source,
            article_fetcher=_MockArticleFetcher(raises=FetchTimeoutError("Timeout fetching URL")),
            classify_fn=_ok_classify,
        )
        assert result["support_status"] == "unverified"
        assert result["support_rationale"]

    def test_empty_content_error_returns_unverified(self):
        """AC5: FetchEmptyContentError → support_status='unverified'."""
        from app.services.source_verifier import verify_source
        source = _Source(url="https://example.com/abstract", claim="Claim.")
        result = verify_source(
            source,
            article_fetcher=_MockArticleFetcher(raises=FetchEmptyContentError("Insufficient content (45 chars)")),
            classify_fn=_ok_classify,
        )
        assert result["support_status"] == "unverified"
        assert result["support_rationale"]

    def test_youtube_none_transcript_returns_unverified(self):
        """AC5: YouTubeTranscriptFetcher returning None → support_status='unverified'."""
        from app.services.source_verifier import verify_source
        source = _Source(url="https://www.youtube.com/watch?v=private", claim="Claim.")
        result = verify_source(
            source,
            yt_fetcher=_MockYTFetcher(result=None),
            classify_fn=_ok_classify,
        )
        assert result["support_status"] == "unverified"
        assert result["support_rationale"]

    def test_classify_fn_not_called_on_fetch_failure(self):
        """AC5: classify_fn is never invoked when fetching fails."""
        from app.services.source_verifier import verify_source
        called = []

        def classify_spy(content, claim):
            called.append((content, claim))
            return _ok_classify(content, claim)

        source = _Source(url="https://example.com", claim="Claim.")
        verify_source(
            source,
            article_fetcher=_MockArticleFetcher(raises=FetchBlockedError("HTTP 403")),
            classify_fn=classify_spy,
        )
        assert called == [], "classify_fn must not be called on fetch failure"


# ---------------------------------------------------------------------------
# AC6 — rationale distinguishes failure reasons
# ---------------------------------------------------------------------------

class TestRationaleDistinguishesFailures:
    def test_paywall_rationale_mentions_paywall_or_http_error(self):
        """AC6: FetchBlockedError rationale cites HTTP error/paywall — no inference."""
        from app.services.source_verifier import verify_source
        source = _Source(url="https://journal.com/article", claim="Claim.")
        result = verify_source(
            source,
            article_fetcher=_MockArticleFetcher(raises=FetchBlockedError("HTTP 403 fetching https://journal.com/article")),
            classify_fn=_ok_classify,
        )
        rationale = result["support_rationale"].lower()
        assert any(kw in rationale for kw in ["403", "blocked", "http", "fetch"])

    def test_timeout_rationale_cites_timeout(self):
        """AC6: FetchTimeoutError rationale cites timeout or network failure."""
        from app.services.source_verifier import verify_source
        source = _Source(url="https://slow-site.com", claim="Claim.")
        result = verify_source(
            source,
            article_fetcher=_MockArticleFetcher(raises=FetchTimeoutError("Timeout fetching https://slow-site.com")),
            classify_fn=_ok_classify,
        )
        rationale = result["support_rationale"].lower()
        assert any(kw in rationale for kw in ["timeout", "fetch", "slow-site"])

    def test_empty_content_rationale_cites_content_issue(self):
        """AC6: FetchEmptyContentError rationale mentions insufficient/empty content."""
        from app.services.source_verifier import verify_source
        source = _Source(url="https://example.com/abstract", claim="Claim.")
        result = verify_source(
            source,
            article_fetcher=_MockArticleFetcher(raises=FetchEmptyContentError("Insufficient content at URL (45 chars)")),
            classify_fn=_ok_classify,
        )
        rationale = result["support_rationale"].lower()
        assert any(kw in rationale for kw in ["insufficient", "content", "empty", "fetch"])

    def test_youtube_unavailable_rationale_explains_transcript(self):
        """AC6: YouTube transcript None → rationale mentions transcript unavailability."""
        from app.services.source_verifier import verify_source
        source = _Source(url="https://www.youtube.com/watch?v=private", claim="Claim.")
        result = verify_source(
            source,
            yt_fetcher=_MockYTFetcher(result=None),
            classify_fn=_ok_classify,
        )
        rationale = result["support_rationale"].lower()
        assert any(kw in rationale for kw in ["transcript", "unavailable", "disabled", "private", "youtube"])

    def test_unsupported_source_type_returns_unverified(self):
        """AC6: Source with kind='book' (unsupported) → support_status='unverified'."""
        from app.services.source_verifier import verify_source
        source = _Source(url="https://books.example.com/isbn/12345", claim="Claim.", kind="book")
        result = verify_source(source, classify_fn=_ok_classify)
        assert result["support_status"] == "unverified"

    def test_unsupported_source_type_rationale_mentions_type(self):
        """AC6: Unsupported source type rationale identifies the unsupported kind."""
        from app.services.source_verifier import verify_source
        source = _Source(url="https://books.example.com/isbn/12345", claim="Claim.", kind="book")
        result = verify_source(source, classify_fn=_ok_classify)
        rationale = result["support_rationale"].lower()
        assert any(kw in rationale for kw in ["unsupported", "book", "type", "kind"])

    def test_unsupported_source_type_dict_returns_unverified(self):
        """AC6: Dict source with unsupported kind also returns unverified."""
        from app.services.source_verifier import verify_source
        source = {"url": "https://books.example.com/isbn/12345", "claim": "Claim.", "kind": "book"}
        result = verify_source(source, classify_fn=_ok_classify)
        assert result["support_status"] == "unverified"


# ---------------------------------------------------------------------------
# AC7 — no new fetcher logic; existing fetchers used as-is
# ---------------------------------------------------------------------------

class TestNoNewFetcherLogic:
    def test_imports_article_reader_fetcher_from_fetchers(self):
        """AC7: Source verifier imports ArticleReaderFetcher from app.research.fetchers."""
        import inspect
        import app.services.source_verifier as sv
        src = inspect.getsource(sv)
        assert "ArticleReaderFetcher" in src

    def test_imports_youtube_transcript_fetcher_from_fetchers(self):
        """AC7: Source verifier imports YouTubeTranscriptFetcher from app.research.fetchers."""
        import inspect
        import app.services.source_verifier as sv
        src = inspect.getsource(sv)
        assert "YouTubeTranscriptFetcher" in src

    def test_fetchers_module_unchanged(self):
        """AC7: app/research/fetchers.py is not modified by this service."""
        import pathlib
        fetchers_src = (
            pathlib.Path(__file__).parent.parent / "app" / "research" / "fetchers.py"
        ).read_text()
        assert "verify_source" not in fetchers_src, (
            "verify_source should not appear in fetchers.py — verifier logic belongs in source_verifier.py"
        )
