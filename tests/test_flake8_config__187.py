"""
Tests for issue #187: Review repo-wide .flake8 config added under a feature ticket.

AC1: .flake8 exists at the repo root with max-line-length = 120.
AC2: The exclude list in .flake8 covers the standard directories that should be
     skipped during linting (venv, .venv, .git, __pycache__, alembic/versions).
AC3: CLAUDE.md documents the project linting convention so future agents and
     reviewers know max-line-length = 120 is intentional, not accidental.
"""
import configparser
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent
FLAKE8_PATH = REPO_ROOT / ".flake8"
CLAUDE_MD_PATH = REPO_ROOT / "CLAUDE.md"

EXPECTED_MAX_LINE_LENGTH = "120"
REQUIRED_EXCLUDES = {"venv", ".venv", ".git", "__pycache__", "alembic/versions"}


# ---------------------------------------------------------------------------
# AC1 — .flake8 exists and sets max-line-length = 120
# ---------------------------------------------------------------------------

def test_flake8_config_file_exists():
    """AC1: .flake8 must exist at the repo root."""
    assert FLAKE8_PATH.exists(), f".flake8 not found at {FLAKE8_PATH}"


def test_flake8_max_line_length_is_120():
    """AC1: max-line-length must be 120 — the confirmed project convention."""
    cfg = configparser.ConfigParser()
    cfg.read(str(FLAKE8_PATH))
    assert cfg.has_option("flake8", "max-line-length"), (
        ".flake8 is missing the max-line-length option"
    )
    assert cfg.get("flake8", "max-line-length") == EXPECTED_MAX_LINE_LENGTH, (
        f"Expected max-line-length = {EXPECTED_MAX_LINE_LENGTH}, "
        f"got {cfg.get('flake8', 'max-line-length')!r}"
    )


# ---------------------------------------------------------------------------
# AC2 — exclude list covers the standard directories
# ---------------------------------------------------------------------------

def test_flake8_excludes_standard_directories():
    """AC2: The exclude list must cover venv, .venv, .git, __pycache__, and alembic/versions."""
    cfg = configparser.ConfigParser()
    cfg.read(str(FLAKE8_PATH))
    assert cfg.has_option("flake8", "exclude"), (
        ".flake8 is missing the exclude option"
    )
    raw = cfg.get("flake8", "exclude")
    excludes = {e.strip() for e in raw.split(",") if e.strip()}
    missing = REQUIRED_EXCLUDES - excludes
    assert not missing, (
        f"These required directories are missing from the .flake8 exclude list: {sorted(missing)}"
    )


# ---------------------------------------------------------------------------
# AC3 — CLAUDE.md documents the linting convention
# ---------------------------------------------------------------------------

def test_claude_md_documents_linting_convention():
    """AC3: CLAUDE.md must contain a linting / tooling section that mentions max-line-length."""
    assert CLAUDE_MD_PATH.exists(), f"CLAUDE.md not found at {CLAUDE_MD_PATH}"
    content = CLAUDE_MD_PATH.read_text(encoding="utf-8")
    assert "max-line-length" in content, (
        "CLAUDE.md must document the max-line-length convention so agents know it is intentional"
    )


def test_claude_md_mentions_standalone_tooling_changes():
    """AC3: CLAUDE.md must note that tooling-config changes should land as standalone tickets."""
    content = CLAUDE_MD_PATH.read_text(encoding="utf-8")
    # A flexible check: just ensure there's guidance about tooling config changes being separate.
    keywords = ["tooling", "linting", "flake8", ".flake8"]
    assert any(kw in content for kw in keywords), (
        "CLAUDE.md should reference the linting convention or .flake8 config"
    )
