"""Tests for issue #20: claim extractor and citation-aware synthesiser."""
from __future__ import annotations

import json
import logging
import pytest
from unittest.mock import MagicMock


# ---------------------------------------------------------------------------
# Fixture document text
# ---------------------------------------------------------------------------

ARTICLE_TEXT = (
    "Regular exercise reduces the risk of cardiovascular disease. "
    "A 30-minute walk each day can lower blood pressure significantly. "
    "Exercise releases endorphins, which improve mood and reduce anxiety. "
    "Studies show that people who exercise regularly live longer than sedentary individuals."
)

YOUTUBE_TEXT = (
    "Machine learning is a subset of artificial intelligence. "
    "Neural networks are inspired by the structure of the human brain. "
    "Supervised learning requires labeled training data. "
    "Deep learning models can recognize images with human-level accuracy."
)

BOOK_TEXT = (
    "The scientific method was formalized during the 17th century. "
    "Galileo Galilei pioneered the use of experiments to test hypotheses. "
    "Isaac Newton's laws of motion transformed our understanding of physics. "
    "The discovery of DNA structure in 1953 revolutionized biology."
)


def _make_article_doc():
    from app.research.types import SourceDocument
    return SourceDocument(
        kind="article",
        title="The Benefits of Exercise",
        url="https://example.com/exercise",
        text=ARTICLE_TEXT,
    )


def _make_youtube_doc():
    from app.research.types import SourceDocument
    return SourceDocument(
        kind="youtube",
        title="Intro to ML",
        url="https://www.youtube.com/watch?v=dQw4w9WgXcQ",
        text=YOUTUBE_TEXT,
    )


def _make_book_doc():
    from app.research.types import SourceDocument
    return SourceDocument(
        kind="book",
        title="History of Science",
        url="https://example.com/book",
        text=BOOK_TEXT,
    )


def _make_plan():
    from app.research.types import Plan
    return Plan(mechanism="exercise and health", prior="general knowledge")


def _make_mock_anthropic_client(response_rows: list[dict]) -> MagicMock:
    """Build a mock anthropic.Anthropic client that returns given rows as JSON."""
    content_block = MagicMock()
    content_block.text = json.dumps(response_rows)
    message = MagicMock()
    message.content = [content_block]
    client = MagicMock()
    client.messages.create.return_value = message
    return client


def _make_candidates() -> list[dict]:
    return [
        {
            "kind": "article",
            "title": "The Benefits of Exercise",
            "url": "https://example.com/exercise",
            "claim": "Regular exercise reduces the risk of cardiovascular disease.",
        },
        {
            "kind": "youtube",
            "title": "Intro to ML",
            "url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
            "claim": "Machine learning is a subset of artificial intelligence.",
        },
    ]


# ===========================================================================
# Extractor tests — AC1, AC2, AC6
# ===========================================================================

def test_extractor_article_returns_non_empty_claims():
    """AC1: extractor returns a non-empty list of claim strings for an article."""
    from app.research.extractor import ClaimExtractor
    claims = ClaimExtractor().extract(_make_article_doc())
    assert isinstance(claims, list)
    assert len(claims) > 0


def test_extractor_article_claims_are_non_empty_strings():
    """AC1: every claim string is non-empty."""
    from app.research.extractor import ClaimExtractor
    for claim in ClaimExtractor().extract(_make_article_doc()):
        assert isinstance(claim, str)
        assert claim.strip()


def test_extractor_youtube_returns_non_empty_claims():
    """AC2: extractor works for youtube kind."""
    from app.research.extractor import ClaimExtractor
    claims = ClaimExtractor().extract(_make_youtube_doc())
    assert len(claims) > 0


def test_extractor_book_returns_non_empty_claims():
    """AC2: extractor works for book kind."""
    from app.research.extractor import ClaimExtractor
    claims = ClaimExtractor().extract(_make_book_doc())
    assert len(claims) > 0


def test_extractor_claims_drawn_from_source_text():
    """AC1: claim strings are drawn from the source text, not invented."""
    from app.research.extractor import ClaimExtractor
    claims = ClaimExtractor().extract(_make_article_doc())
    for claim in claims:
        # each claim must appear verbatim in the source text
        assert claim in ARTICLE_TEXT, f"Claim not found in source text: {claim!r}"


def test_extractor_youtube_claims_drawn_from_source_text():
    """AC2: youtube claims come from source text."""
    from app.research.extractor import ClaimExtractor
    claims = ClaimExtractor().extract(_make_youtube_doc())
    for claim in claims:
        assert claim in YOUTUBE_TEXT, f"Claim not in source text: {claim!r}"


def test_extractor_requires_no_live_api_call(monkeypatch):
    """AC6: ClaimExtractor works without any network or API access."""
    import socket
    original_connect = socket.socket.connect

    def _blocked_connect(self, *args, **kwargs):
        raise RuntimeError("Network access not allowed in extractor tests")

    monkeypatch.setattr(socket.socket, "connect", _blocked_connect)
    from app.research.extractor import ClaimExtractor
    claims = ClaimExtractor().extract(_make_article_doc())
    assert len(claims) > 0


# ===========================================================================
# Source type tests — AC5
# ===========================================================================

def test_source_dataclass_has_required_fields():
    """AC5: Source dataclass has kind, title, url, claim, citation fields."""
    from app.research.types import Source
    s = Source(
        kind="article",
        title="Test Title",
        url="https://example.com",
        claim="A factual claim.",
        citation="The verbatim supporting text.",
    )
    assert s.kind == "article"
    assert s.title == "Test Title"
    assert s.url == "https://example.com"
    assert s.claim == "A factual claim."
    assert s.citation == "The verbatim supporting text."


def test_source_document_dataclass_has_required_fields():
    """SourceDocument dataclass has kind, title, url, text fields."""
    from app.research.types import SourceDocument
    doc = SourceDocument(kind="youtube", title="My Video", url="https://youtube.com/watch?v=abc", text="Some text.")
    assert doc.kind == "youtube"
    assert doc.title == "My Video"
    assert doc.text == "Some text."


# ===========================================================================
# Synthesiser tests — AC2, AC3, AC4, AC5, AC6, AC8
# ===========================================================================

def test_synthesiser_returns_source_rows():
    """AC2: synthesiser calls Claude API and returns Source objects."""
    from app.research.synthesiser import CitationSynthesiser
    response_rows = [
        {
            "kind": "article",
            "title": "The Benefits of Exercise",
            "url": "https://example.com/exercise",
            "claim": "Exercise reduces cardiovascular disease risk.",
            "citation": "Regular exercise reduces the risk of cardiovascular disease.",
        }
    ]
    synth = CitationSynthesiser(client=_make_mock_anthropic_client(response_rows))
    sources = synth.synthesise(_make_plan(), _make_candidates())
    assert len(sources) >= 1
    s = sources[0]
    assert s.kind == "article"
    assert s.title
    assert s.url
    assert s.claim
    assert s.citation


def test_synthesiser_drops_empty_citation(caplog):
    """AC4: rows with empty citation are dropped and a warning is logged."""
    from app.research.synthesiser import CitationSynthesiser
    response_rows = [
        {
            "kind": "article",
            "title": "The Benefits of Exercise",
            "url": "https://example.com/exercise",
            "claim": "Exercise is good.",
            "citation": "",  # empty — must be dropped
        },
        {
            "kind": "youtube",
            "title": "Intro to ML",
            "url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
            "claim": "ML is a subset of AI.",
            "citation": "Machine learning is a subset of artificial intelligence.",
        },
    ]
    synth = CitationSynthesiser(client=_make_mock_anthropic_client(response_rows))
    with caplog.at_level(logging.WARNING, logger="app.research.synthesiser"):
        sources = synth.synthesise(_make_plan(), _make_candidates())
    assert len(sources) == 1
    assert sources[0].citation
    assert any("citation" in r.message.lower() for r in caplog.records)


def test_synthesiser_drops_missing_citation_key(caplog):
    """AC4: rows with no citation key are dropped and a warning is logged."""
    from app.research.synthesiser import CitationSynthesiser
    response_rows = [
        {
            "kind": "article",
            "title": "The Benefits of Exercise",
            "url": "https://example.com/exercise",
            "claim": "Exercise is good.",
            # "citation" key is absent
        }
    ]
    synth = CitationSynthesiser(client=_make_mock_anthropic_client(response_rows))
    with caplog.at_level(logging.WARNING, logger="app.research.synthesiser"):
        sources = synth.synthesise(_make_plan(), _make_candidates())
    assert len(sources) == 0
    assert any("citation" in r.message.lower() for r in caplog.records)


def test_synthesiser_drops_invalid_kind(caplog):
    """AC5: rows with kind not in {book,article,youtube} are dropped."""
    from app.research.synthesiser import CitationSynthesiser
    response_rows = [
        {
            "kind": "podcast",  # invalid
            "title": "Test",
            "url": "https://example.com",
            "claim": "A claim.",
            "citation": "A citation.",
        }
    ]
    synth = CitationSynthesiser(client=_make_mock_anthropic_client(response_rows))
    with caplog.at_level(logging.WARNING, logger="app.research.synthesiser"):
        sources = synth.synthesise(_make_plan(), _make_candidates())
    assert len(sources) == 0


def test_synthesiser_drops_empty_title(caplog):
    """AC5: rows with empty title are dropped."""
    from app.research.synthesiser import CitationSynthesiser
    response_rows = [
        {
            "kind": "article",
            "title": "",  # empty
            "url": "https://example.com/exercise",
            "claim": "Exercise is good.",
            "citation": "Some citation.",
        }
    ]
    synth = CitationSynthesiser(client=_make_mock_anthropic_client(response_rows))
    with caplog.at_level(logging.WARNING, logger="app.research.synthesiser"):
        sources = synth.synthesise(_make_plan(), _make_candidates())
    assert len(sources) == 0


def test_synthesiser_drops_invalid_url(caplog):
    """AC5: rows with non-URL url field are dropped."""
    from app.research.synthesiser import CitationSynthesiser
    response_rows = [
        {
            "kind": "article",
            "title": "Test",
            "url": "not-a-valid-url",
            "claim": "Exercise is good.",
            "citation": "Some citation.",
        }
    ]
    synth = CitationSynthesiser(client=_make_mock_anthropic_client(response_rows))
    with caplog.at_level(logging.WARNING, logger="app.research.synthesiser"):
        sources = synth.synthesise(_make_plan(), _make_candidates())
    assert len(sources) == 0


def test_synthesiser_drops_empty_claim(caplog):
    """AC5: rows with empty claim are dropped."""
    from app.research.synthesiser import CitationSynthesiser
    response_rows = [
        {
            "kind": "article",
            "title": "Test",
            "url": "https://example.com",
            "claim": "",  # empty
            "citation": "Some citation.",
        }
    ]
    synth = CitationSynthesiser(client=_make_mock_anthropic_client(response_rows))
    with caplog.at_level(logging.WARNING, logger="app.research.synthesiser"):
        sources = synth.synthesise(_make_plan(), _make_candidates())
    assert len(sources) == 0


def test_synthesiser_valid_output_kinds():
    """AC5: synthesiser only emits rows with kind in {book, article, youtube}."""
    from app.research.synthesiser import CitationSynthesiser
    response_rows = [
        {
            "kind": "article",
            "title": "Exercise",
            "url": "https://example.com/exercise",
            "claim": "Exercise reduces cardiovascular disease risk.",
            "citation": "Regular exercise reduces the risk of cardiovascular disease.",
        },
        {
            "kind": "youtube",
            "title": "ML",
            "url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
            "claim": "ML is a subset of AI.",
            "citation": "Machine learning is a subset of artificial intelligence.",
        },
    ]
    synth = CitationSynthesiser(client=_make_mock_anthropic_client(response_rows))
    sources = synth.synthesise(_make_plan(), _make_candidates())
    for s in sources:
        assert s.kind in ("book", "article", "youtube")


def test_synthesiser_prompt_instructs_cite_from_source():
    """AC8: SYNTHESISER_PROMPT tells Claude to cite only from the provided source text."""
    from app.research.synthesiser import SYNTHESISER_PROMPT
    prompt_lower = SYNTHESISER_PROMPT.lower()
    assert "cite only from" in prompt_lower or ("only" in prompt_lower and "source" in prompt_lower)
    assert "omit" in prompt_lower


def test_synthesiser_prompt_is_committed():
    """AC8: prompt constant is present in the synthesiser module."""
    from app.research import synthesiser
    assert hasattr(synthesiser, "SYNTHESISER_PROMPT")
    assert isinstance(synthesiser.SYNTHESISER_PROMPT, str)
    assert len(synthesiser.SYNTHESISER_PROMPT) > 50


def test_synthesiser_claude_api_is_called():
    """AC2: synthesiser invokes the Claude API (messages.create) exactly once."""
    from app.research.synthesiser import CitationSynthesiser
    response_rows = [
        {
            "kind": "article",
            "title": "Exercise",
            "url": "https://example.com/exercise",
            "claim": "Exercise reduces cardiovascular disease risk.",
            "citation": "Regular exercise reduces the risk of cardiovascular disease.",
        }
    ]
    client = _make_mock_anthropic_client(response_rows)
    synth = CitationSynthesiser(client=client)
    synth.synthesise(_make_plan(), _make_candidates())
    assert client.messages.create.call_count == 1


# ===========================================================================
# Integration test — AC7
# ===========================================================================

def test_full_pipeline_mixed_kinds():
    """AC7: ≥1 valid Source row per document; no citation-less rows in output."""
    from app.research.extractor import ClaimExtractor
    from app.research.types import SourceDocument, Plan

    docs = [
        SourceDocument(kind="article", title="Exercise", url="https://example.com/ex", text=ARTICLE_TEXT),
        SourceDocument(kind="youtube", title="ML Intro", url="https://www.youtube.com/watch?v=dQw4w9WgXcQ", text=YOUTUBE_TEXT),
    ]

    plan = Plan(mechanism="health and technology", prior="none")
    extractor = ClaimExtractor()

    candidates: list[dict] = []
    for doc in docs:
        claims = extractor.extract(doc)
        assert len(claims) > 0, f"No claims extracted for {doc.kind}"
        for claim in claims:
            candidates.append({"kind": doc.kind, "title": doc.title, "url": doc.url, "claim": claim})

    # Build mock response: one valid Source row per document kind
    mock_rows = []
    seen_kinds: set[str] = set()
    for cand in candidates:
        if cand["kind"] not in seen_kinds:
            mock_rows.append({
                "kind": cand["kind"],
                "title": cand["title"],
                "url": cand["url"],
                "claim": f"Summary: {cand['claim'][:60]}",
                "citation": cand["claim"],
            })
            seen_kinds.add(cand["kind"])

    from app.research.synthesiser import CitationSynthesiser
    synth = CitationSynthesiser(client=_make_mock_anthropic_client(mock_rows))
    sources = synth.synthesise(plan, candidates)

    # No citation-less rows
    for s in sources:
        assert s.citation, f"Source row has empty citation: {s}"

    # At least one Source row per fixture document
    kinds_in_output = {s.kind for s in sources}
    assert "article" in kinds_in_output, "No article source in output"
    assert "youtube" in kinds_in_output, "No youtube source in output"
