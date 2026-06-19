"""Tests for issue #4: App shell with design tokens and theme toggle."""
import re
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

REPO_ROOT = Path(__file__).parent.parent
STATIC = REPO_ROOT / "app" / "static"


@pytest.fixture
def client():
    from app.main import app
    from app.auth import create_session_cookie
    from app.config import AUTH_SECRET
    tc = TestClient(app)
    tc.cookies.set("session", create_session_cookie(AUTH_SECRET))
    return tc


# ---------------------------------------------------------------------------
# AC1: styles.css imported once at app root, partials in order:
#       fonts → colors → typography → spacing → base → primitives
# ---------------------------------------------------------------------------

def test_styles_css_exists():
    assert (STATIC / "styles.css").exists(), "app/static/styles.css must exist"


def test_styles_css_imports_partials_in_order():
    content = (STATIC / "styles.css").read_text()
    # Extract only @import lines (ignore comments)
    import_lines = [l.strip() for l in content.splitlines()
                    if l.strip().lower().startswith("@import")]
    urls = [l for l in import_lines]
    # Build a string of just the urls in order to check relative order
    joined = "\n".join(urls)
    font_pos = joined.lower().find("fonts")
    colors_pos = joined.lower().find("colors")
    typo_pos = joined.lower().find("typography")
    spacing_pos = joined.lower().find("spacing")
    base_pos = joined.lower().find("base")
    prim_pos = joined.lower().find("primitives")
    assert font_pos != -1, "styles.css must import fonts partial"
    assert colors_pos != -1, "styles.css must import colors partial"
    assert typo_pos != -1, "styles.css must import typography partial"
    assert spacing_pos != -1, "styles.css must import spacing partial"
    assert base_pos != -1, "styles.css must import base partial"
    assert prim_pos != -1, "styles.css must import primitives partial"
    assert font_pos < colors_pos, "fonts must come before colors"
    assert colors_pos < typo_pos, "colors must come before typography"
    assert typo_pos < spacing_pos, "typography must come before spacing"
    assert spacing_pos < base_pos, "spacing must come before base"
    assert base_pos < prim_pos, "base must come before primitives"


def test_token_partials_exist():
    assert (STATIC / "styles" / "tokens" / "fonts.css").exists()
    assert (STATIC / "styles" / "tokens" / "colors.css").exists()
    assert (STATIC / "styles" / "tokens" / "typography.css").exists()
    assert (STATIC / "styles" / "tokens" / "spacing.css").exists()
    assert (STATIC / "styles" / "base.css").exists()
    assert (STATIC / "styles" / "primitives.css").exists()


def test_styles_css_served_by_server(client):
    r = client.get("/static/styles.css")
    assert r.status_code == 200
    assert "text/css" in r.headers.get("content-type", "")


def test_index_html_links_styles_once(client):
    r = client.get("/")
    assert r.status_code == 200
    # Count how many times styles.css is referenced
    count = r.text.count("styles.css")
    assert count == 1, f"styles.css must appear exactly once in the HTML, found {count} times"


# ---------------------------------------------------------------------------
# AC2: Sidebar navigation rendered (JS component definition present)
# ---------------------------------------------------------------------------

def test_sidebar_component_defined():
    shell = STATIC / "js" / "shell.js"
    assert shell.exists(), "app/static/js/shell.js must exist"
    content = shell.read_text()
    assert "Sidebar" in content, "shell.js must define a Sidebar component"
    # Sidebar should have nav items for Cases, Probes, Verdicts
    assert "Cases" in content
    assert "Probes" in content
    assert "Verdicts" in content


# ---------------------------------------------------------------------------
# AC3: Right rail container present
# ---------------------------------------------------------------------------

def test_right_rail_component_defined():
    content = (STATIC / "js" / "shell.js").read_text()
    assert "RightRail" in content, "shell.js must define a RightRail component"


# ---------------------------------------------------------------------------
# AC4: crux• wordmark rendered in shell
# ---------------------------------------------------------------------------

def test_wordmark_component_defined():
    content = (STATIC / "js" / "shell.js").read_text()
    assert "Wordmark" in content, "shell.js must define a Wordmark component"


def test_wordmark_uses_crux_token():
    content = (STATIC / "js" / "shell.js").read_text()
    # Wordmark should use var(--crux) for the dot
    assert "var(--crux)" in content or "--crux" in content, \
        "Wordmark must reference --crux token for the violet dot"


# ---------------------------------------------------------------------------
# AC5: Light theme is the default (no data-theme on initial HTML)
# ---------------------------------------------------------------------------

def test_html_root_has_no_data_theme_by_default(client):
    r = client.get("/")
    html = r.text
    # The <html> tag must not have data-theme set in the static HTML
    html_tag_match = re.search(r"<html[^>]*>", html, re.IGNORECASE)
    assert html_tag_match, "HTML must have an <html> tag"
    assert "data-theme" not in html_tag_match.group(), \
        "data-theme must not be in the <html> tag on initial load"


# ---------------------------------------------------------------------------
# AC6: Dark theme activates via data-theme="dark" on <html>; toggle logic
# ---------------------------------------------------------------------------

def test_colors_css_has_dark_theme_rule():
    content = (STATIC / "styles" / "tokens" / "colors.css").read_text()
    assert '[data-theme="dark"]' in content or "[data-theme='dark']" in content, \
        "colors.css must define [data-theme=\"dark\"] overrides"


def test_theme_toggle_logic_present():
    # Check app JS or shell.js contains toggle / data-theme logic
    shell = (STATIC / "js" / "shell.js").read_text()
    # Could be in index.html too — check both
    index = (STATIC / "index.html").read_text()
    combined = shell + index
    assert "data-theme" in combined, "Toggle logic must reference data-theme attribute"
    assert "dark" in combined, "Toggle logic must handle dark theme"


# ---------------------------------------------------------------------------
# AC7: Both light and dark themes are fully styled (tokens exist for both)
# ---------------------------------------------------------------------------

def test_colors_css_has_light_and_dark():
    content = (STATIC / "styles" / "tokens" / "colors.css").read_text()
    assert ":root" in content, "colors.css must have :root block for light theme"
    assert '[data-theme="dark"]' in content or "[data-theme='dark']" in content, \
        "colors.css must have dark theme block"


def test_spacing_css_has_dark_elevation():
    content = (STATIC / "styles" / "tokens" / "spacing.css").read_text()
    assert '[data-theme="dark"]' in content or "[data-theme='dark']" in content, \
        "spacing.css must have dark theme shadow overrides"


# ---------------------------------------------------------------------------
# AC8: Tabler Icons wired; icon refs use names without ti- prefix
# ---------------------------------------------------------------------------

def test_tabler_icons_loaded_in_html():
    content = (STATIC / "index.html").read_text()
    assert "tabler" in content.lower(), "index.html must load Tabler Icons"


def test_icons_constructed_without_ti_prefix():
    content = (STATIC / "js" / "shell.js").read_text()
    # Pattern: className={`ti ti-${icon}`} — the icon variable doesn't contain 'ti-'
    # But nav items pass names like 'folder', 'flask', 'gavel'
    # Check that the icon class is constructed by prepending ti-
    assert "ti-" in content, "shell.js should construct ti- icon class names"
    # The icon data names should NOT start with 'ti-' (they should be bare names)
    bare_icon_names = re.findall(r'icon["\s]*:\s*["\']([^"\']+)["\']', content)
    for name in bare_icon_names:
        assert not name.startswith("ti-"), \
            f"Icon name '{name}' must not include 'ti-' prefix — pass bare name only"


# ---------------------------------------------------------------------------
# AC9: Every style rule uses CSS custom properties — no hard-coded values
# ---------------------------------------------------------------------------

def _css_rules_outside_variables(css_text):
    """Extract CSS property:value declarations that are NOT inside :root or dark theme blocks."""
    # Remove :root { ... } and [data-theme="dark"] { ... } blocks
    # (these legitimately contain raw values)
    without_vars = re.sub(r':root\s*\{[^}]*\}', '', css_text, flags=re.DOTALL)
    without_vars = re.sub(r'\[data-theme=["\']dark["\']\]\s*\{[^}]*\}', '',
                          without_vars, flags=re.DOTALL)
    return without_vars


def test_base_css_no_hardcoded_colors():
    content = (STATIC / "styles" / "base.css").read_text()
    rules = _css_rules_outside_variables(content)
    hex_colors = re.findall(r'(?<!-)#[0-9a-fA-F]{3,6}(?![a-fA-F0-9])', rules)
    assert not hex_colors, f"base.css has hard-coded hex colors outside tokens: {hex_colors}"


def test_primitives_css_no_hardcoded_colors():
    content = (STATIC / "styles" / "primitives.css").read_text()
    rules = _css_rules_outside_variables(content)
    hex_colors = re.findall(r'(?<!-)#[0-9a-fA-F]{3,6}(?![a-fA-F0-9])', rules)
    # Allow #fff in btn-crux color (it's a white text on violet — technically hardcoded)
    # Per design handoff primitives.css which has: .btn-crux { color: #fff }
    # This is the only allowed exception per the design reference
    non_white = [c for c in hex_colors if c.lower() not in ("#fff", "#ffffff")]
    assert not non_white, \
        f"primitives.css has hard-coded non-white hex colors outside tokens: {non_white}"


def test_shell_js_styles_use_css_variables():
    content = (STATIC / "js" / "shell.js").read_text()
    # Inline styles in JSX use var(--...) not raw hex
    # Check that color values in style props use var()
    # Find patterns like: color: '#...' or background: '#...' (without var)
    raw_colors_in_style = re.findall(
        r'(?:color|background|border(?:-color)?|fill|stroke)\s*:\s*["\']#[0-9a-fA-F]{3,6}["\']',
        content
    )
    assert not raw_colors_in_style, \
        f"shell.js has hard-coded colors in inline styles: {raw_colors_in_style}"


# ---------------------------------------------------------------------------
# AC10: Placeholder routes for all primary nav destinations — no 404
# ---------------------------------------------------------------------------

def test_cases_route_does_not_404(client):
    r = client.get("/cases")
    assert r.status_code != 404, f"GET /cases must not return 404, got {r.status_code}"


def test_probes_route_does_not_404(client):
    r = client.get("/probes")
    assert r.status_code != 404, f"GET /probes must not return 404, got {r.status_code}"


def test_verdicts_route_does_not_404(client):
    r = client.get("/verdicts")
    assert r.status_code != 404, f"GET /verdicts must not return 404, got {r.status_code}"
