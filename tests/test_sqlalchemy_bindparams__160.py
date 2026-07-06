"""Tests for issue #160: Use SQLAlchemy bindparams instead of f-string in SQL query in test_issue_153.py

AC coverage:
  AC1 – Replace f-string SQL interpolation with SQLAlchemy bindparams in test_issue_153.py:171.
"""
import os
import sys
import re

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

os.environ.setdefault("AUTH_SECRET", "test_auth_secret_12345678901")


def test_bindparams_pattern_used_in_test_issue_153():
    """AC1: test_issue_153.py:171 uses bindparams instead of f-string SQL."""
    test_file_path = os.path.join(os.path.dirname(__file__), "test_issue_153.py")
    with open(test_file_path, "r") as f:
        content = f.read()

    # Verify that the pattern uses bindparams
    pattern = r'text\("SELECT support_status FROM source WHERE id=:id"\)\.bindparams\(id=src_id\)'
    assert re.search(pattern, content), (
        "test_issue_153.py should use bindparams pattern: "
        'text("SELECT support_status FROM source WHERE id=:id").bindparams(id=src_id)'
    )

    # Ensure the old f-string pattern is NOT present
    old_pattern = r"text\(f\"SELECT support_status FROM source WHERE id=.*\""
    assert not re.search(old_pattern, content), (
        "test_issue_153.py should NOT use f-string SQL interpolation pattern"
    )
