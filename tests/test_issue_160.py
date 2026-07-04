"""Tests for issue #160: Replace f-string in text() with bindparams in test_issue_153.py.

AC coverage:
  AC1 – test_all_four_enum_variants_persist uses bindparams instead of f-string.
  AC2 – No f-string interpolation remains in any text() call in test_issue_153.py.
  AC3 – Parametrized test passes for all four enum variants (verified by running the test).
  AC4 – Refactor is behaviour-neutral (results unchanged).
"""
import pathlib
import re


def test_no_fstring_in_text_calls():
    """AC1 & AC2: No f-string interpolation inside any text() call in test_issue_153.py."""
    test_file = pathlib.Path(__file__).parent / "test_issue_153.py"
    source = test_file.read_text()
    # Match text(f"..." or text(f'...'
    matches = re.findall(r'text\(f["\']', source)
    assert matches == [], (
        f"Found {len(matches)} f-string(s) inside text() call(s) in test_issue_153.py: {matches}"
    )


def test_bindparams_present_in_enum_variants_test():
    """AC1: test_all_four_enum_variants_persist uses .bindparams(id=src_id)."""
    test_file = pathlib.Path(__file__).parent / "test_issue_153.py"
    source = test_file.read_text()
    assert 'bindparams(id=src_id)' in source, (
        "Expected bindparams(id=src_id) in test_issue_153.py but it was not found."
    )
