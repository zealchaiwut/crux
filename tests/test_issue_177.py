"""Tests for issue #177: Reject falsy source_id in summary reference validation.

AC coverage:
  AC1 – _validate_source_ids raises SummaryError for null source_id on a cited reference
  AC2 – _validate_source_ids raises SummaryError for empty-string source_id on a cited reference
  AC3 – The raised SummaryError message identifies the offending reference
  AC4 – Non-falsy source_id absent from valid_source_ids still raises SummaryError (no regression)
  AC5 – Non-falsy source_id present in valid_source_ids passes validation
  AC6 – Falsy source_id on an uncited reference does not raise an error
"""
import pytest
from app.summary import SummaryError, _validate_source_ids


VALID_ID = "source-abc-123"


def _make_refs(*source_ids):
    """Build a reference list where ref id N maps to source_ids[N-1]."""
    return [{"id": i + 1, "source_id": sid} for i, sid in enumerate(source_ids)]


def _paragraphs_citing(*ref_ids):
    """Return a single-paragraph list that cites the given reference IDs."""
    markers = " ".join(f"[{n}]" for n in ref_ids)
    return [f"This paragraph cites {markers}."]


# ---------------------------------------------------------------------------
# AC1: null source_id on cited reference raises SummaryError
# ---------------------------------------------------------------------------

def test_null_source_id_cited_raises():
    """AC1: SummaryError when source_id is None and reference is cited."""
    refs = _make_refs(None)
    paragraphs = _paragraphs_citing(1)
    with pytest.raises(SummaryError):
        _validate_source_ids(refs, {VALID_ID}, paragraphs)


# ---------------------------------------------------------------------------
# AC2: empty-string source_id on cited reference raises SummaryError
# ---------------------------------------------------------------------------

def test_empty_source_id_cited_raises():
    """AC2: SummaryError when source_id is '' and reference is cited."""
    refs = _make_refs("")
    paragraphs = _paragraphs_citing(1)
    with pytest.raises(SummaryError):
        _validate_source_ids(refs, {VALID_ID}, paragraphs)


# ---------------------------------------------------------------------------
# AC3: error message identifies the offending reference
# ---------------------------------------------------------------------------

def test_error_message_identifies_reference_null():
    """AC3: SummaryError message for null source_id must identify the reference."""
    refs = _make_refs(None)
    paragraphs = _paragraphs_citing(1)
    with pytest.raises(SummaryError, match=r"\[?1\]?"):
        _validate_source_ids(refs, {VALID_ID}, paragraphs)


def test_error_message_identifies_reference_empty():
    """AC3: SummaryError message for empty source_id must identify the reference."""
    refs = _make_refs("")
    paragraphs = _paragraphs_citing(1)
    with pytest.raises(SummaryError, match=r"\[?1\]?"):
        _validate_source_ids(refs, {VALID_ID}, paragraphs)


# ---------------------------------------------------------------------------
# AC4: non-falsy source_id absent from valid_source_ids still raises (regression)
# ---------------------------------------------------------------------------

def test_unknown_source_id_still_raises():
    """AC4: Non-falsy source_id not in valid_source_ids must still raise SummaryError."""
    refs = _make_refs("ghost-id-999")
    paragraphs = _paragraphs_citing(1)
    with pytest.raises(SummaryError):
        _validate_source_ids(refs, {VALID_ID}, paragraphs)


# ---------------------------------------------------------------------------
# AC5: valid source_id present in valid_source_ids passes
# ---------------------------------------------------------------------------

def test_valid_source_id_passes():
    """AC5: Valid non-falsy source_id in valid_source_ids must pass without error."""
    refs = _make_refs(VALID_ID)
    paragraphs = _paragraphs_citing(1)
    _validate_source_ids(refs, {VALID_ID}, paragraphs)  # must not raise


def test_multiple_valid_source_ids_pass():
    """AC5: Multiple valid source_ids all present in valid_source_ids pass."""
    id_a, id_b = "src-a", "src-b"
    refs = _make_refs(id_a, id_b)
    paragraphs = _paragraphs_citing(1, 2)
    _validate_source_ids(refs, {id_a, id_b}, paragraphs)  # must not raise


# ---------------------------------------------------------------------------
# AC6: falsy source_id on uncited reference does not raise
# ---------------------------------------------------------------------------

def test_null_source_id_uncited_passes():
    """AC6: Falsy (null) source_id on an uncited reference must not raise."""
    # ref id=1 has null source_id; paragraph cites nothing
    refs = _make_refs(None)
    paragraphs = ["This paragraph has no citation markers."]
    # Note: in practice _validate_citations runs first and would catch orphan refs,
    # but _validate_source_ids must itself be safe with uncited falsy refs.
    _validate_source_ids(refs, {VALID_ID}, paragraphs)  # must not raise


def test_empty_source_id_uncited_passes():
    """AC6: Falsy ('') source_id on an uncited reference must not raise."""
    refs = _make_refs("")
    paragraphs = ["No markers here."]
    _validate_source_ids(refs, {VALID_ID}, paragraphs)  # must not raise


def test_mixed_refs_only_cited_falsy_raises():
    """AC6: Only the cited falsy-source_id reference causes an error; uncited one is fine."""
    # ref 1: valid source_id, cited
    # ref 2: null source_id, cited → should raise
    # If we have ref 3: null source_id, uncited → should be fine (but covered by AC6 above)
    id_a = "src-valid"
    refs = [
        {"id": 1, "source_id": id_a},
        {"id": 2, "source_id": None},
    ]
    paragraphs = ["Evidence [1] and [2] show the trend."]
    with pytest.raises(SummaryError):
        _validate_source_ids(refs, {id_a}, paragraphs)
