"""Tests for issue #98: source-verifier service for claim support detection.

AC coverage:
  AC1  – app/services/source_verifier.py exists and is importable
  AC2  – Service accepts a source object with at least url and claim fields
  AC3  – Reuses ArticleReaderFetcher for article URLs, YouTubeTranscriptFetcher for YouTube
  AC4  – Calls classify_fn with fetched content and claim
  AC5  – Returns {support_status, support_rationale} where support_status is a valid enum value
  AC6  – Returns support_status="unverified" with rationale when fetch blocked/empty/paywall
  AC7  – Rationale cites the failure reason explicitly — no hallucination
  AC8  – Unit tests cover: supports, partially_supports, contradicts, paywall/blocked, empty-content
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


# ---------------------------------------------------------------------------
# Mock helpers
# ---------------------------------------------------------------------------

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


class _Source:
    def __init__(self, url, claim):
        self.url = url
        self.claim = claim


def _ok_classify(content, claim):
    return {"support_status": "supports", "support_rationale": "Content confirms the claim."}


# ---------------------------------------------------------------------------
# AC1 — module importable
# ---------------------------------------------------------------------------

class TestImportable:
    def test_module_importable(self):
        """AC1: app/services/source_verifier.py exists and is importable."""
        from app.services import source_verifier  # noqa: F401
        from app.services.source_verifier import verify_source  # noqa: F401
        assert callable(verify_source)


# ---------------------------------------------------------------------------
# AC2 — accepts source with url and claim
# ---------------------------------------------------------------------------

class TestAcceptsSourceObject:
    def test_accepts_object_with_url_and_claim(self):
        """AC2: verify_source accepts an object with .url and .claim."""
        from app.services.source_verifier import verify_source

        source = _Source(url="https://example.com/article", claim="The sky is blue.")
        doc = ArticleDocument(url="https://example.com/article", title="T", text="The sky is blue as shown by spectral analysis.")
        result = verify_source(source, article_fetcher=_MockArticleFetcher(result=doc), classify_fn=_ok_classify)
        assert isinstance(result, dict)
        assert "support_status" in result
        assert "support_rationale" in result

    def test_accepts_dict_with_url_and_claim(self):
        """AC2: verify_source also accepts a dict with 'url' and 'claim' keys."""
        from app.services.source_verifier import verify_source

        source = {"url": "https://example.com/article", "claim": "The sky is blue."}
        doc = ArticleDocument(url="https://example.com/article", title="T", text="Blue sky confirmed by atmospheric measurements.")
        result = verify_source(source, article_fetcher=_MockArticleFetcher(result=doc), classify_fn=_ok_classify)
        assert "support_status" in result
        assert "support_rationale" in result


# ---------------------------------------------------------------------------
# AC3 — fetcher routing by URL type
# ---------------------------------------------------------------------------

class TestFetcherRouting:
    def test_web_url_uses_article_fetcher(self):
        """AC3: non-YouTube URL routes to ArticleReaderFetcher."""
        from app.services.source_verifier import verify_source

        fetcher = _MockArticleFetcher(result=ArticleDocument(url="https://example.com", title="T", text="Sufficient content about the claim."))
        source = _Source(url="https://example.com/article", claim="The treatment works.")
        verify_source(source, article_fetcher=fetcher, classify_fn=_ok_classify)
        assert fetcher.called_with == "https://example.com/article"

    def test_youtube_com_url_uses_yt_fetcher(self):
        """AC3: youtube.com URL routes to YouTubeTranscriptFetcher."""
        from app.services.source_verifier import verify_source

        yt_fetcher = _MockYTFetcher(result=ArticleDocument(
            url="https://www.youtube.com/watch?v=abc123",
            title="Video",
            text="Transcript with relevant content about the claim.",
        ))
        source = _Source(url="https://www.youtube.com/watch?v=abc123", claim="Treatment reduces inflammation.")
        verify_source(source, yt_fetcher=yt_fetcher, classify_fn=_ok_classify)
        assert yt_fetcher.called_with == "https://www.youtube.com/watch?v=abc123"

    def test_youtu_be_url_uses_yt_fetcher(self):
        """AC3: youtu.be short URL routes to YouTubeTranscriptFetcher."""
        from app.services.source_verifier import verify_source

        yt_fetcher = _MockYTFetcher(result=ArticleDocument(url="https://youtu.be/abc", title="V", text="Some transcript content."))
        source = _Source(url="https://youtu.be/abc", claim="Some claim.")
        verify_source(source, yt_fetcher=yt_fetcher, classify_fn=_ok_classify)
        assert yt_fetcher.called_with == "https://youtu.be/abc"


# ---------------------------------------------------------------------------
# AC4 — classify_fn receives content and claim
# ---------------------------------------------------------------------------

class TestClassifyFnCalled:
    def test_classify_fn_receives_fetched_content_and_claim(self):
        """AC4: classify_fn is called with the fetched article text and the claim."""
        from app.services.source_verifier import verify_source

        received = {}

        def spy_classify(content, claim):
            received["content"] = content
            received["claim"] = claim
            return {"support_status": "supports", "support_rationale": "Confirmed."}

        text = "The article clearly supports the claim with empirical evidence."
        doc = ArticleDocument(url="https://example.com", title="T", text=text)
        source = _Source(url="https://example.com/article", claim="Specific claim here.")
        verify_source(source, article_fetcher=_MockArticleFetcher(result=doc), classify_fn=spy_classify)

        assert received["content"] == text
        assert received["claim"] == "Specific claim here."


# ---------------------------------------------------------------------------
# AC5 — returns valid status enum values
# ---------------------------------------------------------------------------

class TestValidReturnShape:
    @pytest.mark.parametrize("status", ["supports", "partially_supports", "contradicts", "unverified"])
    def test_all_four_statuses_returned_correctly(self, status):
        """AC5 + AC8: all four status values are handled and returned."""
        from app.services.source_verifier import verify_source

        doc = ArticleDocument(url="https://example.com", title="T", text="Sufficient article content for classification.")
        source = _Source(url="https://example.com/article", claim="A claim.")
        result = verify_source(
            source,
            article_fetcher=_MockArticleFetcher(result=doc),
            classify_fn=lambda c, cl: {"support_status": status, "support_rationale": f"Rationale for {status}."},
        )
        assert result["support_status"] == status
        assert result["support_rationale"] == f"Rationale for {status}."


# ---------------------------------------------------------------------------
# AC6 + AC7 — paywall / blocked → unverified, rationale cites failure
# ---------------------------------------------------------------------------

class TestPaywallBlocked:
    def test_fetch_blocked_returns_unverified(self):
        """AC6: FetchBlockedError → support_status='unverified'."""
        from app.services.source_verifier import verify_source

        source = _Source(url="https://paywalled-journal.com/article", claim="Some claim.")
        result = verify_source(
            source,
            article_fetcher=_MockArticleFetcher(raises=FetchBlockedError("HTTP 403 fetching https://paywalled-journal.com/article")),
            classify_fn=_ok_classify,
        )
        assert result["support_status"] == "unverified"

    def test_fetch_blocked_rationale_cites_error(self):
        """AC7: rationale cites the specific fetch failure — no inference."""
        from app.services.source_verifier import verify_source

        source = _Source(url="https://paywalled-journal.com/article", claim="Some claim.")
        result = verify_source(
            source,
            article_fetcher=_MockArticleFetcher(raises=FetchBlockedError("HTTP 403 fetching https://paywalled-journal.com/article")),
            classify_fn=_ok_classify,
        )
        rationale = result["support_rationale"].lower()
        assert "403" in rationale or "blocked" in rationale or "fetch" in rationale

    def test_fetch_timeout_returns_unverified(self):
        """AC6: FetchTimeoutError → support_status='unverified'."""
        from app.services.source_verifier import verify_source

        source = _Source(url="https://slow-site.com/article", claim="Some claim.")
        result = verify_source(
            source,
            article_fetcher=_MockArticleFetcher(raises=FetchTimeoutError("Timeout fetching https://slow-site.com")),
            classify_fn=_ok_classify,
        )
        assert result["support_status"] == "unverified"
        assert result["support_rationale"]

    def test_fetch_timeout_rationale_cites_timeout(self):
        """AC7: timeout rationale mentions the failure, not inferred content."""
        from app.services.source_verifier import verify_source

        source = _Source(url="https://slow-site.com/article", claim="Some claim.")
        result = verify_source(
            source,
            article_fetcher=_MockArticleFetcher(raises=FetchTimeoutError("Timeout fetching https://slow-site.com")),
            classify_fn=_ok_classify,
        )
        rationale = result["support_rationale"].lower()
        assert "timeout" in rationale or "fetch" in rationale or "slow" in rationale


# ---------------------------------------------------------------------------
# AC6 + AC7 — empty content → unverified
# ---------------------------------------------------------------------------

class TestEmptyContent:
    def test_empty_content_error_returns_unverified(self):
        """AC6: FetchEmptyContentError → support_status='unverified'."""
        from app.services.source_verifier import verify_source

        source = _Source(url="https://example.com/abstract", claim="Specific finding.")
        result = verify_source(
            source,
            article_fetcher=_MockArticleFetcher(raises=FetchEmptyContentError("Insufficient content at URL (45 chars)")),
            classify_fn=_ok_classify,
        )
        assert result["support_status"] == "unverified"
        assert result["support_rationale"]

    def test_empty_content_rationale_cites_failure(self):
        """AC7: empty-content rationale explicitly cites the fetch failure."""
        from app.services.source_verifier import verify_source

        source = _Source(url="https://example.com/abstract", claim="Specific finding.")
        result = verify_source(
            source,
            article_fetcher=_MockArticleFetcher(raises=FetchEmptyContentError("Insufficient content at URL (45 chars)")),
            classify_fn=_ok_classify,
        )
        rationale = result["support_rationale"].lower()
        assert "insufficient" in rationale or "content" in rationale or "empty" in rationale or "fetch" in rationale


# ---------------------------------------------------------------------------
# AC3 + AC8 — YouTube transcript scenarios
# ---------------------------------------------------------------------------

class TestYouTubeVerification:
    def test_youtube_transcript_classify_fn_called(self):
        """AC3 + AC8: YouTube URL fetches transcript and calls classify_fn."""
        from app.services.source_verifier import verify_source

        received = {}

        def spy_classify(content, claim):
            received["content"] = content
            received["claim"] = claim
            return {"support_status": "supports", "support_rationale": "Transcript confirms."}

        doc = ArticleDocument(
            url="https://www.youtube.com/watch?v=abc123",
            title="Study review",
            text="The speaker confirms significant reduction in inflammation markers.",
        )
        source = _Source(url="https://www.youtube.com/watch?v=abc123", claim="Treatment reduces inflammation.")
        result = verify_source(source, yt_fetcher=_MockYTFetcher(result=doc), classify_fn=spy_classify)
        assert result["support_status"] == "supports"
        assert received["content"] == doc.text

    def test_youtube_transcript_unavailable_returns_unverified(self):
        """AC6 + AC8: YouTube transcript None → support_status='unverified'."""
        from app.services.source_verifier import verify_source

        source = _Source(url="https://www.youtube.com/watch?v=private123", claim="Some claim.")
        result = verify_source(
            source,
            yt_fetcher=_MockYTFetcher(result=None),
            classify_fn=_ok_classify,
        )
        assert result["support_status"] == "unverified"

    def test_youtube_unavailable_rationale_explains(self):
        """AC7: unverified YouTube rationale describes why — not a guessed conclusion."""
        from app.services.source_verifier import verify_source

        source = _Source(url="https://youtu.be/private123", claim="Some claim.")
        result = verify_source(
            source,
            yt_fetcher=_MockYTFetcher(result=None),
            classify_fn=_ok_classify,
        )
        assert result["support_status"] == "unverified"
        rationale = result["support_rationale"].lower()
        assert any(kw in rationale for kw in ["transcript", "unavailable", "disabled", "private", "deleted", "youtube"])

    def test_youtube_contradicts(self):
        """AC8: YouTube URL can produce contradicts status."""
        from app.services.source_verifier import verify_source

        doc = ArticleDocument(url="https://www.youtube.com/watch?v=xyz", title="V", text="Study found no significant reduction in inflammation.")
        source = _Source(url="https://www.youtube.com/watch?v=xyz", claim="Treatment reduces inflammation.")
        result = verify_source(
            source,
            yt_fetcher=_MockYTFetcher(result=doc),
            classify_fn=lambda c, cl: {"support_status": "contradicts", "support_rationale": "Transcript refutes the claim."},
        )
        assert result["support_status"] == "contradicts"

    def test_youtube_partially_supports(self):
        """AC8: YouTube URL can produce partially_supports status."""
        from app.services.source_verifier import verify_source

        doc = ArticleDocument(url="https://www.youtube.com/watch?v=yyy", title="V", text="Some evidence of reduction but not conclusive.")
        source = _Source(url="https://www.youtube.com/watch?v=yyy", claim="Treatment reduces inflammation.")
        result = verify_source(
            source,
            yt_fetcher=_MockYTFetcher(result=doc),
            classify_fn=lambda c, cl: {"support_status": "partially_supports", "support_rationale": "Partial evidence found."},
        )
        assert result["support_status"] == "partially_supports"
