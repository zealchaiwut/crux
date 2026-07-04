"""Tests for issue #142: Verify WeighPanel error messages don't reference 'required context' (runs against UAT)"""
import os
import pytest


# --- Acceptance Criteria ---

def test_weighpanel_error_messages__no_context_required_in_errors():
    # AC: No error message displayed by WeighPanel on rerank POST failure contains
    # the phrase "context is required" or any equivalent wording implying context is mandatory.
    # Check app/static/js/cases.js for forbidden strings
    cases_file = os.path.join(os.path.dirname(__file__), "..", "app", "static", "js", "cases.js")
    with open(cases_file, "r") as f:
        content = f.read().lower()
    assert "context is required" not in content, "Found 'context is required' in cases.js"
    assert "context required" not in content, "Found 'context required' in cases.js"
    assert "required context" not in content, "Found 'required context' in cases.js"


def test_weighpanel_error_messages__empty_context_shows_actual_failure():
    # AC: When a rerank POST fails with an empty context field, the displayed error
    # message describes the actual failure reason (e.g., server error, network error)
    # rather than a context validation message.
    # This step will be verified via browser UAT step 1, not pytest.
    pytest.skip("manual — verified via browser UAT step 1")


def test_weighpanel_error_messages__omitted_context_no_reference():
    # AC: When a rerank POST fails with the context field entirely omitted,
    # the error message does not reference context at all.
    # This step will be verified via browser UAT step 3, not pytest.
    pytest.skip("manual — verified via browser UAT step 3")


def test_weighpanel_error_messages__whitespace_context_no_validation_error():
    # AC: When a rerank POST fails with a whitespace-only context value (which is
    # converted to null by the handler at cases.js:149), the error message accurately
    # reflects the server response rather than a client-side context validation error.
    # This step will be verified via browser UAT step 2, not pytest.
    pytest.skip("manual — verified via browser UAT step 2")


def test_weighpanel_error_messages__no_forbidden_strings_in_source():
    # AC: If any error message string referencing "context is required" is found in
    # app/static/js/cases.js, it is updated to a neutral, accurate alternative
    # before this ticket closes.
    # Verify the source code does not contain these strings
    cases_file = os.path.join(os.path.dirname(__file__), "..", "app", "static", "js", "cases.js")
    with open(cases_file, "r") as f:
        content = f.read().lower()
    assert "context is required" not in content, "Found 'context is required' in cases.js"
    assert "context required" not in content, "Found 'context required' in cases.js"
    assert "required context" not in content, "Found 'required context' in cases.js"
