"""Tests for issue #126: Add semicolon to .chip-expanded CSS rule.

AC coverage:
  AC1 – The .chip-expanded CSS rule in primitives.css has a trailing semicolon
         after font-size: var(--text-2xs), making it font-size: var(--text-2xs);
  AC2 – No other lines in the .chip-expanded rule block are modified.
  AC3 – The stylesheet parses without errors after the change (syntactically valid).
"""
import pathlib
import re

PRIMITIVES_CSS = pathlib.Path(__file__).parent.parent / "app" / "static" / "styles" / "primitives.css"


def _css_src() -> str:
    return PRIMITIVES_CSS.read_text()


def _chip_expanded_rule(css: str) -> str:
    """Return the full .chip-expanded rule block from the stylesheet."""
    match = re.search(r"\.chip-expanded\s*\{([^}]*)\}", css)
    assert match, ".chip-expanded rule not found in primitives.css"
    return match.group(0)


# ---------------------------------------------------------------------------
# AC1 — font-size: var(--text-2xs) has a trailing semicolon
# ---------------------------------------------------------------------------

class TestChipExpandedSemicolon:
    def test_font_size_has_trailing_semicolon(self):
        """AC1: font-size: var(--text-2xs) must end with a semicolon."""
        css = _css_src()
        rule = _chip_expanded_rule(css)
        # The declaration must end with ; before the closing brace or next declaration
        assert re.search(r"font-size\s*:\s*var\(--text-2xs\)\s*;", rule), (
            "font-size: var(--text-2xs) is missing the trailing semicolon in .chip-expanded rule"
        )

    def test_chip_expanded_rule_exists(self):
        """AC1: .chip-expanded rule must exist in primitives.css."""
        css = _css_src()
        assert ".chip-expanded" in css, ".chip-expanded class missing from primitives.css"

    def test_font_size_value_unchanged(self):
        """AC1: font-size value must remain var(--text-2xs) exactly."""
        css = _css_src()
        rule = _chip_expanded_rule(css)
        assert "var(--text-2xs)" in rule, (
            ".chip-expanded must use var(--text-2xs) as the font-size value"
        )


# ---------------------------------------------------------------------------
# AC2 — No other lines in the .chip-expanded rule block are modified
# ---------------------------------------------------------------------------

class TestNoOtherModifications:
    def test_only_font_size_declaration_present(self):
        """AC2: .chip-expanded rule block contains only the font-size declaration."""
        css = _css_src()
        match = re.search(r"\.chip-expanded\s*\{([^}]*)\}", css)
        assert match, ".chip-expanded rule not found"
        rule_body = match.group(1).strip()
        # Strip the semicolon and whitespace to get the raw declarations
        declarations = [d.strip() for d in rule_body.split(";") if d.strip()]
        assert len(declarations) == 1, (
            f".chip-expanded rule should contain exactly one declaration, found: {declarations}"
        )
        assert declarations[0].startswith("font-size"), (
            f"The single declaration in .chip-expanded must be font-size, got: {declarations[0]!r}"
        )


# ---------------------------------------------------------------------------
# AC3 — Stylesheet is syntactically valid (basic parse check)
# ---------------------------------------------------------------------------

class TestStylesheetValidity:
    def test_braces_are_balanced(self):
        """AC3: primitives.css must have balanced curly braces."""
        css = _css_src()
        assert css.count("{") == css.count("}"), (
            "primitives.css has unbalanced curly braces — stylesheet is invalid"
        )

    def test_chip_expanded_rule_closes_properly(self):
        """AC3: .chip-expanded rule has exactly one opening and one closing brace."""
        css = _css_src()
        match = re.search(r"\.chip-expanded\s*\{[^}]*\}", css)
        assert match, ".chip-expanded rule block does not close properly"

    def test_file_is_nonempty(self):
        """AC3: primitives.css is non-empty and readable."""
        css = _css_src()
        assert len(css) > 0, "primitives.css is empty"
