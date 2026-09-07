"""
Tests for issue #203: Resolve committed merge conflict and support-status enum drift.

AC1: The merge conflict in README.md is resolved and the correct sprint count stated once.
AC2: SCHEMA.md's support-status values match the model exactly.
AC3: CI fails on any file containing merge-conflict markers.
AC4: A quick pass confirms no other tracked file carries conflict markers.
"""
import re
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent

# Matches the three merge-conflict marker line types
CONFLICT_PATTERN = re.compile(r'^(<{7}|={7}|>{7})[ \t]?', re.MULTILINE)


def _tracked_text_files():
    """Return paths of all git-tracked files that can be decoded as UTF-8."""
    result = subprocess.run(
        ['git', 'ls-files'],
        capture_output=True, text=True, cwd=str(REPO_ROOT), check=True,
    )
    paths = []
    for rel in result.stdout.splitlines():
        p = REPO_ROOT / rel
        if not p.is_file():
            continue
        try:
            p.read_text(encoding='utf-8')
            paths.append(p)
        except (UnicodeDecodeError, PermissionError):
            pass
    return paths


# ---------------------------------------------------------------------------
# AC1 — README.md merge conflict resolved, sprint count stated once
# ---------------------------------------------------------------------------

def test_readme_no_conflict_markers():
    """AC1: README.md must contain no merge-conflict markers."""
    content = (REPO_ROOT / 'README.md').read_text(encoding='utf-8')
    assert not CONFLICT_PATTERN.search(content), (
        "README.md still contains unresolved merge-conflict markers"
    )


def test_readme_sprint_count_stated_once():
    """AC1: The sprint count is stated exactly once (no duplicate / conflicting lines)."""
    content = (REPO_ROOT / 'README.md').read_text(encoding='utf-8')
    matches = re.findall(r'\w+ sprints? complete', content, re.IGNORECASE)
    assert len(matches) == 1, (
        f"README.md should state the sprint count exactly once; "
        f"found {len(matches)} occurrence(s): {matches}"
    )


# ---------------------------------------------------------------------------
# AC2 — SCHEMA.md support-status values match the model
# ---------------------------------------------------------------------------

def test_schema_support_status_matches_model():
    """AC2: SCHEMA.md's support_status_enum values exactly match models._SUPPORT_STATUS."""
    sys.path.insert(0, str(REPO_ROOT))
    from app.models import _SUPPORT_STATUS  # noqa: E402 (local import after path fix)

    schema_text = (REPO_ROOT / 'SCHEMA.md').read_text(encoding='utf-8')

    # Find the table row for support_status_enum
    match = re.search(r'`support_status_enum`\s*\|\s*([^|\n]+)', schema_text)
    assert match, "SCHEMA.md is missing a 'support_status_enum' row"

    cell = match.group(1)
    schema_values = set(re.findall(r'`([^`]+)`', cell))
    model_values = set(_SUPPORT_STATUS)

    assert schema_values == model_values, (
        f"support_status_enum mismatch:\n"
        f"  SCHEMA.md : {sorted(schema_values)}\n"
        f"  models.py : {sorted(model_values)}"
    )


# ---------------------------------------------------------------------------
# AC3 — Conflict-marker detection is wired up (proves the check works)
# ---------------------------------------------------------------------------

def test_conflict_marker_detection_catches_markers():
    """AC3: The detection regex identifies genuine conflict markers."""
    conflicted = (
        "normal line\n"
        "<<<<<<< HEAD\n"
        "version A\n"
        "=======\n"
        "version B\n"
        ">>>>>>> origin/develop\n"
        "after\n"
    )
    assert CONFLICT_PATTERN.search(conflicted), (
        "Detection regex failed to match known conflict markers"
    )


def test_conflict_marker_detection_ignores_clean_content():
    """AC3: The detection regex does not flag clean content."""
    clean = "# Heading\nSome text\n> blockquote\n== separator ==\n"
    assert not CONFLICT_PATTERN.search(clean), (
        "Detection regex produced a false positive on clean content"
    )


# ---------------------------------------------------------------------------
# AC3 + AC4 — No tracked file carries conflict markers
# ---------------------------------------------------------------------------

def test_no_tracked_file_has_conflict_markers():
    """AC3+AC4: Every tracked UTF-8 text file is free of merge-conflict markers."""
    offenders = []
    for path in _tracked_text_files():
        content = path.read_text(encoding='utf-8')
        if CONFLICT_PATTERN.search(content):
            offenders.append(str(path.relative_to(REPO_ROOT)))

    assert not offenders, (
        "Tracked files containing merge-conflict markers:\n"
        + "\n".join(f"  {f}" for f in offenders)
    )
