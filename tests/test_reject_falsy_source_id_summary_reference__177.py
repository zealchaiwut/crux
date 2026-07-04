"""Tests for issue #177: Reject falsy source_id in summary reference validation"""
import pytest
from app.summary import _validate_source_ids, SummaryError


class TestRejectFalsySourceIdInCitedReferences:
    """Test suite for rejecting falsy source_id on cited references."""

    def test_source_id_null_with_citation_raises_error(self):
        # AC1: _validate_source_ids raises SummaryError when source_id is null and cited via [N]
        references = [
            {
                "id": 1,
                "source_id": None,  # falsy: null
                "title": "Some source",
                "url": "http://example.com",
            }
        ]
        valid_source_ids = set()
        paragraphs = ["This is a citation [1] in the text."]

        with pytest.raises(SummaryError) as exc_info:
            _validate_source_ids(references, valid_source_ids, paragraphs)

        assert "null" in str(exc_info.value).lower() or "falsy" in str(exc_info.value).lower()

    def test_source_id_empty_string_with_citation_raises_error(self):
        # AC2: _validate_source_ids raises SummaryError when source_id is "" and cited via [N]
        references = [
            {
                "id": 1,
                "source_id": "",  # falsy: empty string
                "title": "Some source",
                "url": "http://example.com",
            }
        ]
        valid_source_ids = set()
        paragraphs = ["This is a citation [1] in the text."]

        with pytest.raises(SummaryError) as exc_info:
            _validate_source_ids(references, valid_source_ids, paragraphs)

        assert "empty" in str(exc_info.value).lower() or "falsy" in str(exc_info.value).lower()

    def test_error_message_identifies_offending_reference(self):
        # AC3: The raised SummaryError message identifies the offending reference
        references = [
            {
                "id": 1,
                "source_id": None,
                "title": "Bad Reference",
                "url": "http://example.com",
            }
        ]
        valid_source_ids = set()
        paragraphs = ["This is a citation [1] in the text."]

        with pytest.raises(SummaryError) as exc_info:
            _validate_source_ids(references, valid_source_ids, paragraphs)

        error_msg = str(exc_info.value)
        # Should mention either the id [1] or index or the title to identify it
        assert "1" in error_msg or "Bad Reference" in error_msg or "offending" in error_msg.lower()

    def test_uncited_falsy_source_id_does_not_raise_error(self):
        # AC6: Uncited references with falsy source_id (no [N] marker) do not raise error
        # Since _validate_source_ids now checks citation markers via paragraphs,
        # a reference with falsy source_id that has no [N] marker in the text
        # should not raise an error (only cited falsy refs are rejected).

        references = [
            {
                "id": 1,
                "source_id": None,  # falsy, but not cited
                "title": "Uncited source",
                "url": "http://example.com",
            }
        ]
        valid_source_ids = set()
        paragraphs = ["This summary has no citation markers."]

        # Should not raise because reference 1 is not cited (no [1] marker)
        _validate_source_ids(references, valid_source_ids, paragraphs)

    def test_non_falsy_invalid_source_id_still_raises_error(self):
        # AC4: References with non-falsy source_id not in valid_source_ids raise error (no regression)
        references = [
            {
                "id": 1,
                "source_id": "invalid-src-99",
                "title": "Some source",
                "url": "http://example.com",
            }
        ]
        valid_source_ids = {"valid-src-1", "valid-src-2"}
        paragraphs = ["This is a citation [1] in the text."]

        with pytest.raises(SummaryError) as exc_info:
            _validate_source_ids(references, valid_source_ids, paragraphs)

        assert "invalid-src-99" in str(exc_info.value)

    def test_valid_non_falsy_source_id_passes(self):
        # AC5: References with valid non-falsy source_id in valid_source_ids pass validation
        references = [
            {
                "id": 1,
                "source_id": "valid-src-1",
                "title": "Valid source",
                "url": "http://example.com",
            },
            {
                "id": 2,
                "source_id": "valid-src-2",
                "title": "Another valid source",
                "url": "http://example.com/2",
            }
        ]
        valid_source_ids = {"valid-src-1", "valid-src-2"}
        paragraphs = ["This citation [1] and another [2] are both valid."]

        # Should not raise
        _validate_source_ids(references, valid_source_ids, paragraphs)

    def test_multiple_references_one_falsy_raises_error(self):
        # Edge case: multiple references, one has falsy source_id
        references = [
            {
                "id": 1,
                "source_id": "valid-src-1",
                "title": "Valid source",
                "url": "http://example.com",
            },
            {
                "id": 2,
                "source_id": None,  # falsy
                "title": "Invalid source",
                "url": "http://example.com/2",
            }
        ]
        valid_source_ids = {"valid-src-1"}
        paragraphs = ["Citation [1] is valid, but [2] is not."]

        with pytest.raises(SummaryError) as exc_info:
            _validate_source_ids(references, valid_source_ids, paragraphs)

        error_msg = str(exc_info.value)
        assert "falsy" in error_msg.lower() or "null" in error_msg.lower() or "empty" in error_msg.lower()

    def test_empty_references_list_passes(self):
        # Edge case: empty references list (no sources cited)
        references = []
        valid_source_ids = set()
        paragraphs = ["No citations here."]

        # Should not raise
        _validate_source_ids(references, valid_source_ids, paragraphs)

    def test_zero_source_id_is_valid_non_falsy(self):
        # Edge case: 0 is falsy in Python but may be a valid numeric source_id
        # Assuming source_id is string-based, this test ensures we handle numeric falsy values correctly
        # Based on the code, source_id appears to be string, so 0 wouldn't naturally appear,
        # but we should be aware of the distinction.
        references = [
            {
                "id": 1,
                "source_id": "0",  # string "0" is non-falsy
                "title": "Source with id 0",
                "url": "http://example.com",
            }
        ]
        valid_source_ids = {"0"}
        paragraphs = ["Citation [1] with numeric string source_id."]

        # Should not raise
        _validate_source_ids(references, valid_source_ids, paragraphs)
