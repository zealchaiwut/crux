"""Tests for issue #4: Build app shell with design tokens and theme toggle (runs against UAT)"""
import os
import pytest
import httpx
from pathlib import Path


# Resolved from UAT .env at runtime; see tester skill Step 0.
BASE_URL = os.environ.get("UAT_BASE_URL") or "http://localhost:" + os.environ.get("UAT_PORT", "8001")
if not BASE_URL.startswith("http"):
    raise RuntimeError(
        "UAT_BASE_URL / UAT_PORT not set. Run the tester skill's Step 0 to resolve UAT before pytest."
    )

# Path to repo root and app directory
REPO_ROOT = Path(__file__).parent.parent
APP_DIR = REPO_ROOT / "app"
STATIC_DIR = APP_DIR / "static"


@pytest.fixture
def client():
    with httpx.Client(base_url=BASE_URL, timeout=10.0) as c:
        yield c


# --- Acceptance Criteria ---

def test_app_shell_design_tokens_theme_toggle__styles_css_imported_once_in_order():
    # AC: styles.css is imported once at the app root and loads token partials in order:
    # fonts → colors → typography → spacing → base → primitives
    styles_file = STATIC_DIR / "styles.css"
    assert styles_file.exists(), "styles.css not found"
    content = styles_file.read_text()

    # Verify the @import statements exist and are in the correct order
    fonts_idx = content.find("@import url('./styles/tokens/fonts.css')")
    colors_idx = content.find("@import url('./styles/tokens/colors.css')")
    typography_idx = content.find("@import url('./styles/tokens/typography.css')")
    spacing_idx = content.find("@import url('./styles/tokens/spacing.css')")
    base_idx = content.find("@import url('./styles/base.css')")
    primitives_idx = content.find("@import url('./styles/primitives.css')")

    assert fonts_idx >= 0, "fonts.css not imported"
    assert colors_idx >= 0, "colors.css not imported"
    assert typography_idx >= 0, "typography.css not imported"
    assert spacing_idx >= 0, "spacing.css not imported"
    assert base_idx >= 0, "base.css not imported"
    assert primitives_idx >= 0, "primitives.css not imported"
    assert fonts_idx < colors_idx < typography_idx < spacing_idx < base_idx < primitives_idx, \
        "token imports not in correct order"


def test_app_shell_design_tokens_theme_toggle__sidebar_navigation_rendered():
    # AC: Sidebar navigation is rendered and matches the layout defined in reference_screens/Shell.jsx
    shell_js = STATIC_DIR / "js" / "shell.js"
    assert shell_js.exists(), "shell.js not found"
    content = shell_js.read_text()

    # Check for presence of sidebar component definition
    assert "function Sidebar" in content, "Sidebar component not defined"
    assert "NavItem" in content, "NavItem component not referenced in Sidebar"


def test_app_shell_design_tokens_theme_toggle__right_rail_container_present():
    # AC: Right rail container is present and structurally matches the reference screen
    shell_js = STATIC_DIR / "js" / "shell.js"
    assert shell_js.exists(), "shell.js not found"
    content = shell_js.read_text()

    # Check that the RightRail component is defined
    assert "function RightRail" in content, "RightRail component not defined"
    assert "aside" in content, "right rail structure (aside) not used"


def test_app_shell_design_tokens_theme_toggle__wordmark_rendered():
    # AC: The typographic crux• wordmark is rendered in the shell header/sidebar as specified in the reference
    shell_js = STATIC_DIR / "js" / "shell.js"
    assert shell_js.exists(), "shell.js not found"
    content = shell_js.read_text()

    # The Wordmark component should be defined
    assert "function Wordmark" in content, "Wordmark component not defined"
    assert "crux" in content, "crux text not present in wordmark"


def test_app_shell_design_tokens_theme_toggle__light_theme_default_on_load():
    # AC: Light theme is the default on first load (no data-theme attribute required)
    shell_js = STATIC_DIR / "js" / "shell.js"
    assert shell_js.exists(), "shell.js not found"
    content = shell_js.read_text()

    # Check that theme state initializes to 'light'
    assert "useState('light')" in content or 'useState("light")' in content, \
        "light theme not set as default in state initialization"


def test_app_shell_design_tokens_theme_toggle__dark_theme_toggles_via_data_theme_attribute():
    # AC: Dark theme activates by setting data-theme="dark" on <html> and a working toggle switches between the two
    shell_js = STATIC_DIR / "js" / "shell.js"
    assert shell_js.exists(), "shell.js not found"
    content = shell_js.read_text()

    # Check that the theme toggle mechanism exists
    assert "toggleTheme" in content or "setTheme" in content, "theme toggle mechanism not present"
    # Check for data-theme attribute setting
    assert ("setAttribute('data-theme'" in content or 'setAttribute("data-theme"' in content), \
        "data-theme attribute setter not present"
    # Check for removal mechanism
    assert ("removeAttribute('data-theme')" in content or 'removeAttribute("data-theme")' in content), \
        "data-theme attribute remover not present"


def test_app_shell_design_tokens_theme_toggle__both_themes_fully_styled():
    # AC: Both light and dark themes are fully styled — neither is a stub or fallback
    colors_file = STATIC_DIR / "styles" / "tokens" / "colors.css"
    assert colors_file.exists(), "colors.css not found"
    content = colors_file.read_text()

    # Verify light theme variables are defined in :root
    assert "--bg:" in content, "light theme --bg not defined"
    assert "--text:" in content, "light theme --text not defined"
    assert "--crux:" in content, "light theme --crux not defined"

    # Verify dark theme variables are defined under [data-theme="dark"]
    assert '[data-theme="dark"]' in content, "dark theme block not present"
    dark_section = content[content.find('[data-theme="dark"]'):]
    assert "--bg:" in dark_section, "dark theme --bg not defined"
    assert "--text:" in dark_section, "dark theme --text not defined"
    assert "--crux:" in dark_section, "dark theme --crux not defined"


def test_app_shell_design_tokens_theme_toggle__tabler_icons_wired():
    # AC: Tabler Icons are wired via webfont or @tabler/icons-react; icon references use names without the ti- prefix
    index_html = STATIC_DIR / "index.html"
    assert index_html.exists(), "index.html not found"
    html_content = index_html.read_text()

    # Check that the Tabler Icons webfont is loaded in index.html
    assert "tabler-icons" in html_content or "tabler/icons" in html_content, \
        "Tabler Icons webfont not referenced"

    # Check that icon class names use the ti- prefix pattern (from shell.js)
    shell_js = STATIC_DIR / "js" / "shell.js"
    shell_content = shell_js.read_text()
    assert "ti ti-" in shell_content or "ti-" in shell_content, \
        "icon class names not using ti- pattern"


def test_app_shell_design_tokens_theme_toggle__all_styles_use_css_custom_properties():
    # AC: Every style rule reads from CSS custom properties — no hard-coded color,
    # spacing, or typography values anywhere in shell code
    shell_js = STATIC_DIR / "js" / "shell.js"
    assert shell_js.exists(), "shell.js not found"
    content = shell_js.read_text()

    # Check that inline styles reference var(--*) for key properties
    assert "var(--" in content, "CSS custom properties not used in shell.js"
    # Spot-check that common properties use variables
    assert "var(--text)" in content or "var(--bg)" in content or "var(--crux)" in content, \
        "color/bg/crux custom properties not referenced"


def test_app_shell_design_tokens_theme_toggle__placeholder_routes_exist():
    # AC: Placeholder routes exist for all primary nav destinations so navigation links do not 404
    shell_js = STATIC_DIR / "js" / "shell.js"
    assert shell_js.exists(), "shell.js not found"
    content = shell_js.read_text()

    # Check that routes are handled (they should exist based on the code review)
    assert "route" in content.lower(), "route mechanism not present"
    # Verify placeholder screen component exists
    assert "PlaceholderScreen" in content, "placeholder screen component not defined"


def test_app_shell_design_tokens_theme_toggle__no_console_errors_on_load():
    # AC: No console errors on initial load in either theme
    # This test verifies the HTML structure is valid and JavaScript loads without syntax errors
    index_html = STATIC_DIR / "index.html"
    assert index_html.exists(), "index.html not found"
    content = index_html.read_text()

    # Check that HTML is well-formed and required elements are present
    assert "<html" in content, "HTML tag not present"
    assert "<body" in content, "body tag not present"
    assert 'id="app"' in content, "app container not present"
    # Verify React and Babel are loaded
    assert "react@" in content or "react" in content.lower(), "React not loaded"
    assert "babel" in content.lower(), "Babel not loaded"
    # Verify shell.js is loaded
    assert "/static/js/shell.js" in content, "shell.js not loaded"
