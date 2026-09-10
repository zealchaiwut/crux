"""Tests for issue #160: Use SQLAlchemy bindparams instead of f-string in SQL query in test_issue_153.py

Acceptance Criteria:
  AC1 – test_all_four_enum_variants_persist uses bindparams API instead of f-string
  AC2 – No f-string interpolation remains in any text() call within test_issue_153.py
  AC3 – The parametrized test passes for all four enum variants after the change
  AC4 – The SQL query produces the same results as before — behaviour-neutral refactor
"""
import os
import sys
import subprocess
import re

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


class TestCodeRefactoring:
    """Inspect the refactored test file for correct SQL binding pattern."""

    def test_bindparams_api_used_at_line_171(self):
        """AC1: test_all_four_enum_variants_persist at line 171 uses bindparams API."""
        test_file = os.path.join(os.path.dirname(__file__), "test_issue_153.py")
        with open(test_file, "r") as f:
            lines = f.readlines()

        # Find the line with text(...).bindparams
        line_171 = lines[170]  # 0-indexed, so line 171 is index 170
        assert (
            'text("SELECT support_status FROM source WHERE id=:id").bindparams(id=src_id)'
            in line_171
        ), f"Line 171 does not contain the expected bindparams pattern. Got: {line_171!r}"

    def test_no_f_string_in_text_calls(self):
        """AC2: No f-string interpolation in any text() call in test_issue_153.py."""
        test_file = os.path.join(os.path.dirname(__file__), "test_issue_153.py")
        with open(test_file, "r") as f:
            content = f.read()

        # Pattern: text(f"...") — should not exist
        pattern = r'text\s*\(\s*f["\']'
        matches = re.findall(pattern, content)
        assert (
            len(matches) == 0
        ), f"Found f-string in text() calls: {matches}. All text() calls should use bindparams."

    def test_parametrized_test_structure_preserved(self):
        """AC3/AC4: The test_all_four_enum_variants_persist structure is unchanged."""
        test_file = os.path.join(os.path.dirname(__file__), "test_issue_153.py")
        with open(test_file, "r") as f:
            content = f.read()

        # Verify the parametrized decorator and function signature are intact
        assert (
            '@pytest.mark.parametrize("status", ["supports", "partial", "contradicts", "unverified"])'
            in content
        ), "Parametrized decorator not found or modified."
        assert (
            "def test_all_four_enum_variants_persist(plan, status):"
            in content
        ), "Test function signature changed unexpectedly."


class TestQueryBehavior:
    """Run the refactored parametrized test to verify behaviour-neutral refactoring."""

    def test_parametrized_test_all_four_variants_pass(self):
        """AC3/AC4: Run test_all_four_enum_variants_persist for all four enum variants."""
        # Run pytest on the specific test; captures exit code and output
        result = subprocess.run(
            [
                "python",
                "-m",
                "pytest",
                os.path.join(os.path.dirname(__file__), "test_issue_153.py::test_all_four_enum_variants_persist"),
                "-v",
            ],
            capture_output=True,
            text=True,
            cwd=os.path.dirname(os.path.dirname(__file__)),
        )

        # All four parametrized variants must pass
        assert result.returncode == 0, (
            f"Parametrized test did not pass. Exit code: {result.returncode}\n"
            f"STDOUT:\n{result.stdout}\n"
            f"STDERR:\n{result.stderr}"
        )

        # Verify all four variants were tested
        output = result.stdout + result.stderr
        assert "supports" in output, "Test for 'supports' variant not found in output"
        assert "partial" in output, "Test for 'partial' variant not found in output"
        assert "contradicts" in output, "Test for 'contradicts' variant not found in output"
        assert "unverified" in output, "Test for 'unverified' variant not found in output"
