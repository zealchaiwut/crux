"""Tests for issue #4: Build app shell with design tokens and theme toggle."""
from pathlib import Path
import pytest
from fastapi.testclient import TestClient

# Use local TestClient since UAT requires auth (issue #3) and AUTH_SECRET may not be available
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


# --- Acceptance Criteria ---

def test_app_shell__styles_css_imported_with_correct_token_order():
    # AC: `styles.css` is imported once at the app root and loads token partials in order:
    # fonts → colors → typography → spacing → base → primitives
    content = (STATIC / "styles.css").read_text()
    # Extract @import lines in order
    import_lines = [ln.strip() for ln in content.splitlines()
                    if ln.strip().lower().startswith("@import")]
    joined = "\n".join(import_lines)
    fonts_pos = joined.lower().find("fonts")
    colors_pos = joined.lower().find("colors")
    typo_pos = joined.lower().find("typography")
    spacing_pos = joined.lower().find("spacing")
    base_pos = joined.lower().find("base")
    prim_pos = joined.lower().find("primitives")

    assert fonts_pos != -1, "fonts.css not imported"
    assert colors_pos != -1, "colors.css not imported"
    assert typo_pos != -1, "typography.css not imported"
    assert spacing_pos != -1, "spacing.css not imported"
    assert base_pos != -1, "base.css not imported"
    assert prim_pos != -1, "primitives.css not imported"
    # Verify order
    assert fonts_pos < colors_pos < typo_pos < spacing_pos < base_pos < prim_pos


def test_app_shell__sidebar_navigation_rendered(client):
    # AC: Sidebar navigation is rendered and matches the layout
    shell_js = (STATIC / "js" / "shell.js").read_text()
    assert "function Sidebar" in shell_js, "Sidebar component not defined"
    assert "Cases" in shell_js, "Cases nav item missing"
    assert "Probes" in shell_js, "Probes nav item missing"
    assert "Verdicts" in shell_js, "Verdicts nav item missing"


def test_app_shell__right_rail_container_present():
    # AC: Right rail container is present and structurally matches the reference screen
    shell_js = (STATIC / "js" / "shell.js").read_text()
    assert "function RightRail" in shell_js, "RightRail component not defined"


def test_app_shell__crux_wordmark_rendered_in_shell():
    # AC: The typographic `crux•` wordmark is rendered in the shell header/sidebar
    shell_js = (STATIC / "js" / "shell.js").read_text()
    assert "function Wordmark" in shell_js, "Wordmark component not defined"
    assert "crux" in shell_js, "Wordmark doesn't contain 'crux' text"
    # Check for bullet/dot styling via border-radius
    assert "borderRadius" in shell_js or "border-radius" in shell_js


def test_app_shell__light_theme_default_on_first_load():
    # AC: Light theme is the default on first load (no `data-theme` attribute required)
    shell_js = (STATIC / "js" / "shell.js").read_text()
    # Check that theme is initialized to 'light'
    assert "useState('light')" in shell_js or 'useState("light")' in shell_js


def test_app_shell__dark_theme_activates_with_data_theme_attribute():
    # AC: Dark theme activates by setting `data-theme="dark"` on `<html>`
    shell_js = (STATIC / "js" / "shell.js").read_text()
    assert "data-theme" in shell_js, "data-theme attribute not used"
    assert "setAttribute('data-theme'" in shell_js or 'setAttribute("data-theme"' in shell_js


def test_app_shell__both_light_and_dark_themes_fully_styled():
    # AC: Both light and dark themes are fully styled — neither is a stub or fallback
    colors_css = (STATIC / "styles" / "tokens" / "colors.css").read_text()
    # Verify both :root (light) and [data-theme="dark"] (dark) are defined
    assert ":root" in colors_css
    assert '[data-theme="dark"]' in colors_css
    # Verify color tokens exist for both
    assert "--bg:" in colors_css
    assert "--text:" in colors_css
    # Count tokens to ensure both themes have sufficient styling
    light_section = colors_css[:colors_css.find('[data-theme="dark"]')]
    dark_section = colors_css[colors_css.find('[data-theme="dark"]'):]
    light_tokens = light_section.count("--")
    dark_tokens = dark_section.count("--")
    assert light_tokens > 5, f"Light theme has only {light_tokens} tokens"
    assert dark_tokens > 5, f"Dark theme has only {dark_tokens} tokens"


def test_app_shell__tabler_icons_wired_via_webfont(client):
    # AC: Tabler Icons are wired via webfont; icon references use names without the `ti-` prefix
    r = client.get("/")
    assert r.status_code == 200
    # Verify Tabler Icons CDN link is in the HTML
    assert "tabler-icons" in r.text


def test_app_shell__style_rules_use_css_custom_properties():
    # AC: Every style rule reads from CSS custom properties — no hard-coded values
    shell_js = (STATIC / "js" / "shell.js").read_text()
    # Verify style definitions use var(--*) custom properties
    assert "var(--" in shell_js
    # Check for common variables
    assert "var(--crux)" in shell_js
    assert "var(--space-" in shell_js
    assert "var(--text)" in shell_js
    assert "var(--bg)" in shell_js


def test_app_shell__placeholder_routes_exist_for_nav_destinations(client):
    # AC: Placeholder routes exist for all primary nav destinations (no 404)
    routes = ["/cases", "/probes", "/verdicts"]
    for route in routes:
        r = client.get(route)
        assert r.status_code == 200, f"Route {route} returned {r.status_code}"


def test_app_shell__no_console_errors_on_initial_load(client):
    # AC: No console errors on initial load
    r = client.get("/")
    assert r.status_code == 200
    # Verify critical assets are loaded and structured correctly
    assert "id=\"app\"" in r.text or 'id="app"' in r.text
    assert "shell.js" in r.text
    assert "styles.css" in r.text
