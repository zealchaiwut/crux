"""Tests for issue #113: Extract inline CSS styles to .chip-expanded class.

AC coverage:
  AC1 – A .chip-expanded CSS class is added to the project stylesheet containing
         font-size: var(--text-2xs) (and/or var(--text-sm)).
  AC2 – Inline font-size: var(--text-2xs) or var(--text-sm) style attributes in the
         expanded SourceChip section are replaced with the chip-expanded class applied
         via className; the four targeted elements no longer set fontSize inline.
  AC3 – No other inline styles at those four locations are removed or altered — only
         the font-size declarations are extracted.
  AC4 – Visual appearance is unchanged: the .chip-expanded class provides the same
         font-size value that was previously set inline.
  AC5 – No new inline style duplication for var(--text-2xs) font-size is introduced
         in the expanded SourceChip section.
"""
import pathlib
import re

import pytest

CASES_JS = pathlib.Path(__file__).parent.parent / "app" / "static" / "js" / "cases.js"
PRIMITIVES_CSS = pathlib.Path(__file__).parent.parent / "app" / "static" / "styles" / "primitives.css"


def _cases_src() -> str:
    return CASES_JS.read_text()


def _css_src() -> str:
    return PRIMITIVES_CSS.read_text()


def _expanded_chip_section(src: str) -> str:
    """Return the slice of cases.js covering the expanded SourceChip return block."""
    marker = "// Expanded state"
    start = src.find(marker)
    if start == -1:
        return ""
    # SourceChip closes with the `}` at the end of the function.
    # Find `function SourceForm` which immediately follows SourceChip.
    end = src.find("\nfunction SourceForm", start)
    if end == -1:
        end = len(src)
    return src[start:end]


# ---------------------------------------------------------------------------
# AC1 — .chip-expanded class exists in the CSS and defines the font-size
# ---------------------------------------------------------------------------

class TestChipExpandedClassInCSS:
    def test_chip_expanded_class_exists(self):
        """AC1: primitives.css must define a .chip-expanded rule."""
        css = _css_src()
        assert ".chip-expanded" in css, (
            ".chip-expanded class is missing from primitives.css"
        )

    def test_chip_expanded_sets_font_size_2xs(self):
        """AC1: .chip-expanded rule must set font-size to var(--text-2xs)."""
        css = _css_src()
        # Match `.chip-expanded { ... font-size: var(--text-2xs) ... }`
        match = re.search(
            r"\.chip-expanded\s*\{([^}]+)\}",
            css,
        )
        assert match, ".chip-expanded rule not found in primitives.css"
        rule_body = match.group(1)
        assert "font-size" in rule_body, (
            ".chip-expanded rule must include a font-size declaration"
        )
        assert "var(--text-2xs)" in rule_body, (
            ".chip-expanded font-size must use var(--text-2xs)"
        )


# ---------------------------------------------------------------------------
# AC2 — The four targeted elements use chip-expanded class, not inline fontSize
# ---------------------------------------------------------------------------

class TestFontSizeRemovedFromInlineStyles:
    def test_status_label_span_has_chip_expanded_class(self):
        """AC2: The statusLabel <span> in the expanded chip uses className chip-expanded."""
        src = _cases_src()
        section = _expanded_chip_section(src)
        assert section, "Expanded SourceChip section not found"
        # The statusLabel span renders {statusLabel} text and is near the collapse button
        assert "chip-expanded" in section, (
            "chip-expanded class not found in expanded SourceChip section"
        )

    def test_status_label_span_no_inline_font_size(self):
        """AC2: The statusLabel span must not set fontSize inline in the expanded chip."""
        src = _cases_src()
        section = _expanded_chip_section(src)
        assert section, "Expanded SourceChip section not found"

        # Find the statusLabel span — it renders {statusLabel} and has className mono chip-expanded
        # It must NOT have fontSize: "var(--text-2xs)" inline next to it
        pattern = re.compile(
            r'<span\b[^>]*className=["\'][^"\']*chip-expanded[^"\']*["\'][^>]*>'
            r'.*?\{statusLabel\}',
            re.DOTALL,
        )
        match = pattern.search(section)
        assert match, (
            "Could not find statusLabel <span> with chip-expanded class in expanded chip section"
        )
        span_block = match.group(0)
        assert 'fontSize' not in span_block, (
            "statusLabel span must not set fontSize inline — it should use .chip-expanded"
        )

    def test_overridden_span_has_chip_expanded_class(self):
        """AC2: The 'Overridden' span must carry the chip-expanded class."""
        src = _cases_src()
        section = _expanded_chip_section(src)
        # Find the span that contains 'Overridden' text
        pattern = re.compile(
            r'<span\b[^>]*className=["\'][^"\']*chip-expanded[^"\']*["\'][^>]*>'
            r'.*?Overridden',
            re.DOTALL,
        )
        assert pattern.search(section), (
            "'Overridden' span is missing chip-expanded class in expanded SourceChip"
        )

    def test_overridden_span_no_inline_font_size(self):
        """AC2: The 'Overridden' span must not set fontSize inline."""
        src = _cases_src()
        section = _expanded_chip_section(src)
        pattern = re.compile(
            r'<span\b(?:[^>]*)className=["\'][^"\']*chip-expanded[^"\']*["\'](?:[^>]*)>'
            r'(.*?)Overridden',
            re.DOTALL,
        )
        match = pattern.search(section)
        assert match, "Overridden span with chip-expanded not found"
        # Check the opening tag doesn't have fontSize
        tag_start = match.group(0).split(">")[0]
        assert "fontSize" not in tag_start, (
            "Overridden span must not set fontSize inline"
        )

    def test_external_link_has_chip_expanded_class(self):
        """AC2: The external-link <a> element in expanded chip uses chip-expanded class."""
        src = _cases_src()
        section = _expanded_chip_section(src)
        # The external link has ti-external-link icon
        pattern = re.compile(
            r'<a\b[^>]*className=["\'][^"\']*chip-expanded[^"\']*["\'][^>]*>'
            r'.*?ti-external-link',
            re.DOTALL,
        )
        assert pattern.search(section), (
            "External link <a> is missing chip-expanded class in expanded SourceChip"
        )

    def test_external_link_no_inline_font_size(self):
        """AC2: The external-link <a> must not set fontSize inline."""
        src = _cases_src()
        section = _expanded_chip_section(src)
        pattern = re.compile(
            r'(<a\b[^>]*className=["\'][^"\']*chip-expanded[^"\']*["\'][^>]*>)'
            r'.*?ti-external-link',
            re.DOTALL,
        )
        match = pattern.search(section)
        assert match, "External link with chip-expanded not found"
        opening_tag = match.group(1)
        assert "fontSize" not in opening_tag, (
            "External link <a> must not set fontSize inline — use .chip-expanded"
        )

    def test_status_label_element_has_chip_expanded(self):
        """AC2: The <label> or equivalent wrapping the Status override select uses chip-expanded."""
        src = _cases_src()
        section = _expanded_chip_section(src)
        # The status label contains "Status:" and the override select
        pattern = re.compile(
            r'<label\b[^>]*className=["\'][^"\']*chip-expanded[^"\']*["\'][^>]*>'
            r'.*?Status:',
            re.DOTALL,
        )
        assert pattern.search(section), (
            "Status <label> is missing chip-expanded class in expanded SourceChip"
        )

    def test_status_label_element_no_inline_font_size(self):
        """AC2: The Status <label> must not set fontSize inline."""
        src = _cases_src()
        section = _expanded_chip_section(src)
        pattern = re.compile(
            r'(<label\b[^>]*className=["\'][^"\']*chip-expanded[^"\']*["\'][^>]*>)'
            r'.*?Status:',
            re.DOTALL,
        )
        match = pattern.search(section)
        assert match, "Status label with chip-expanded not found"
        opening_tag = match.group(1)
        assert "fontSize" not in opening_tag, (
            "Status <label> must not set fontSize inline — use .chip-expanded"
        )


# ---------------------------------------------------------------------------
# AC3 — Other inline styles at the four locations are preserved
# ---------------------------------------------------------------------------

class TestOtherInlineStylesPreserved:
    def test_status_label_span_retains_other_styles(self):
        """AC3: statusLabel span must keep color and fontWeight in inline style."""
        src = _cases_src()
        section = _expanded_chip_section(src)
        # Find the statusLabel span block
        pattern = re.compile(
            r'<span\b(?:[^>]*)className=["\'][^"\']*chip-expanded[^"\']*["\']'
            r'(?:[^>]*)style=\{([^}]+)\}'
            r'[^>]*>\s*\{statusLabel\}',
            re.DOTALL,
        )
        match = pattern.search(section)
        assert match, (
            "statusLabel span with chip-expanded and inline style not found — "
            "ensure it keeps color/fontWeight inline"
        )
        style_content = match.group(1)
        assert "color" in style_content, (
            "statusLabel span must retain 'color' in its inline style (AC3)"
        )
        assert "fontWeight" in style_content, (
            "statusLabel span must retain 'fontWeight' in its inline style (AC3)"
        )

    def test_overridden_span_retains_other_styles(self):
        """AC3: Overridden span must keep display, alignItems, gap, color inline."""
        src = _cases_src()
        section = _expanded_chip_section(src)
        pattern = re.compile(
            r'<span\b(?:[^>]*)className=["\'][^"\']*chip-expanded[^"\']*["\']'
            r'.*?style=\{\{([^}]+)\}\}'
            r'.*?Overridden',
            re.DOTALL,
        )
        match = pattern.search(section)
        assert match, (
            "Overridden span with chip-expanded and style not found"
        )
        style_content = match.group(1)
        assert "color" in style_content, (
            "Overridden span must retain 'color' inline (AC3)"
        )

    def test_external_link_retains_other_styles(self):
        """AC3: External link <a> must keep marginLeft and color inline."""
        src = _cases_src()
        section = _expanded_chip_section(src)
        pattern = re.compile(
            r'<a\b(?:[^>]*)className=["\'][^"\']*chip-expanded[^"\']*["\']'
            r'.*?style=\{\{([^}]+)\}\}'
            r'.*?ti-external-link',
            re.DOTALL,
        )
        match = pattern.search(section)
        assert match, (
            "External link with chip-expanded and style not found"
        )
        style_content = match.group(1)
        assert "marginLeft" in style_content, (
            "External link must retain 'marginLeft' inline (AC3)"
        )
        assert "color" in style_content, (
            "External link must retain 'color' inline (AC3)"
        )

    def test_status_label_retains_other_styles(self):
        """AC3: Status <label> must keep display, alignItems, gap, color inline."""
        src = _cases_src()
        section = _expanded_chip_section(src)
        pattern = re.compile(
            r'<label\b(?:[^>]*)className=["\'][^"\']*chip-expanded[^"\']*["\']'
            r'.*?style=\{\{([^}]+)\}\}'
            r'.*?Status:',
            re.DOTALL,
        )
        match = pattern.search(section)
        assert match, (
            "Status label with chip-expanded and style not found"
        )
        style_content = match.group(1)
        assert "display" in style_content, (
            "Status label must retain 'display' inline (AC3)"
        )


# ---------------------------------------------------------------------------
# AC5 — No new inline font-size duplication for var(--text-2xs) in expanded chip
# ---------------------------------------------------------------------------

class TestNoNewInlineFontSizeDuplication:
    def test_expanded_chip_font_size_2xs_not_on_targeted_elements(self):
        """AC5: None of the four targeted elements set fontSize: var(--text-2xs) inline."""
        src = _cases_src()
        section = _expanded_chip_section(src)

        # Check statusLabel span
        pattern = re.compile(
            r'<span\b[^>]*className=["\'][^"\']*chip-expanded[^"\']*["\'][^>]*>'
            r'[^<]*\{statusLabel\}',
            re.DOTALL,
        )
        match = pattern.search(section)
        if match:
            assert 'fontSize.*text-2xs' not in match.group(0) and \
                   'var(--text-2xs)' not in match.group(0).split('chip-expanded')[0], \
                   "statusLabel span must not repeat fontSize: var(--text-2xs) inline"

    def test_no_chip_expanded_element_has_inline_font_size(self):
        """AC5: No element carrying chip-expanded class also sets fontSize inline."""
        src = _cases_src()
        section = _expanded_chip_section(src)

        # Find all occurrences of chip-expanded class usage in the section
        # and verify none of them also have fontSize: "var(--text-2xs)" in the same style prop
        pattern = re.compile(
            r'className=["\'][^"\']*chip-expanded[^"\']*["\']',
        )
        for match in pattern.finditer(section):
            # Look at the surrounding ~200 chars for an inline fontSize
            start = max(0, match.start() - 50)
            end = min(len(section), match.end() + 200)
            context = section[start:end]
            assert 'fontSize: "var(--text-2xs)"' not in context and \
                   "fontSize: 'var(--text-2xs)'" not in context, (
                f"Element with chip-expanded class also sets fontSize inline near: {context[:100]!r}"
            )
