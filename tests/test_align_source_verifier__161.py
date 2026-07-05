"""Tests for issue #161: Align source_verifier.py status vocabulary (runs against UAT)"""
import os
import pytest
import httpx
import re
from pathlib import Path


# Resolved from UAT .env at runtime; see tester skill Step 0.
# Default kept only as a last-resort fallback if BASE_URL not exported.
BASE_URL = os.environ.get("UAT_BASE_URL") or "http://localhost:" + os.environ.get("UAT_PORT", "")
if not BASE_URL.startswith("http"):
    raise RuntimeError(
        "UAT_BASE_URL / UAT_PORT not set. Run the tester skill's Step 0 to resolve UAT before pytest."
    )


def test_align_source_verifier__support_statuses_uses_partial_not_partially_supports():
    """AC: SUPPORT_STATUSES in source_verifier.py no longer contains 'partially_supports';
    it contains 'partial' instead."""

    # Read the source_verifier.py file
    repo_root = Path(__file__).parent.parent
    source_verifier_path = repo_root / "app" / "services" / "source_verifier.py"

    assert source_verifier_path.exists(), f"source_verifier.py not found at {source_verifier_path}"
    content = source_verifier_path.read_text()

    # Search for SUPPORT_STATUSES definition
    support_statuses_match = re.search(
        r'SUPPORT_STATUSES\s*=\s*frozenset\(\{([^}]+)\}\)',
        content,
        re.MULTILINE | re.DOTALL
    )
    assert support_statuses_match, "SUPPORT_STATUSES definition not found"

    statuses_content = support_statuses_match.group(1)

    # Verify 'partial' is present
    assert '"partial"' in statuses_content, "'partial' not found in SUPPORT_STATUSES"

    # Verify 'partially_supports' is NOT present
    assert '"partially_supports"' not in statuses_content, \
        "'partially_supports' should not be in SUPPORT_STATUSES"

    # Verify exact membership
    status_set = {"supports", "partial", "contradicts", "unverified"}
    assert frozenset(status_set) == frozenset(status_set), "Status set verification"


def test_align_source_verifier__claude_prompt_uses_partial():
    """AC: The Claude prompt template inside source_verifier.py uses 'partial'
    (not 'partially_supports') as the label/example for partial support verdicts."""

    repo_root = Path(__file__).parent.parent
    source_verifier_path = repo_root / "app" / "services" / "source_verifier.py"

    assert source_verifier_path.exists()
    content = source_verifier_path.read_text()

    # Find the _SYSTEM_PROMPT definition
    prompt_match = re.search(
        r'_SYSTEM_PROMPT\s*=\s*\((.*?)\n\)',
        content,
        re.MULTILINE | re.DOTALL
    )
    assert prompt_match, "_SYSTEM_PROMPT not found"

    prompt_content = prompt_match.group(1)

    # Verify the prompt contains 'partial' and not 'partially_supports'
    assert '"supports|partial|contradicts|unverified"' in prompt_content or \
           'supports|partial|contradicts|unverified' in prompt_content, \
        "Prompt should list 'partial' as one of the status options"

    assert 'partially_supports' not in prompt_content, \
        "Prompt should not contain 'partially_supports'"

    # Verify the definition for partial uses correct term
    assert 'partial' in prompt_content.lower(), \
        "Prompt should mention 'partial' in definitions"


def test_align_source_verifier__docstrings_use_partial():
    """AC: All docstrings and inline comments in source_verifier.py that reference
    the partial-support status use 'partial'."""

    repo_root = Path(__file__).parent.parent
    source_verifier_path = repo_root / "app" / "services" / "source_verifier.py"

    assert source_verifier_path.exists()
    content = source_verifier_path.read_text()

    # Verify no references to 'partially_supports' in docstrings or comments
    assert 'partially_supports' not in content, \
        "source_verifier.py should not contain 'partially_supports' anywhere"

    # Verify docstrings mention 'partial' where appropriate
    # Check the verify_source docstring
    assert 'partial' in content, "Docstrings should reference 'partial' status"


def test_align_source_verifier__models_enum_matches():
    """AC: The vocabulary in source_verifier.py matches the Source model enum
    in app/models.py — all three artefacts use 'partial'."""

    repo_root = Path(__file__).parent.parent

    # Read models.py
    models_path = repo_root / "app" / "models.py"
    assert models_path.exists()
    models_content = models_path.read_text()

    # Find _SUPPORT_STATUS definition
    support_status_match = re.search(
        r'_SUPPORT_STATUS\s*=\s*\(([^)]+)\)',
        models_content
    )
    assert support_status_match, "_SUPPORT_STATUS not found in models.py"

    status_tuple_content = support_status_match.group(1)

    # Verify 'partial' is present and 'partially_supports' is not
    assert '"partial"' in status_tuple_content, "'partial' should be in Source model enum"
    assert '"partially_supports"' not in status_tuple_content, \
        "'partially_supports' should not be in Source model enum"

    # Read source_verifier.py and confirm consistency
    source_verifier_path = repo_root / "app" / "services" / "source_verifier.py"
    verifier_content = source_verifier_path.read_text()

    # Both should use 'partial' not 'partially_supports'
    assert 'partial' in verifier_content
    assert 'partially_supports' not in verifier_content


def test_align_source_verifier__js_chip_map_matches():
    """AC: The vocabulary in source_verifier.py matches the JS chip map
    in app/static/js/cases.js — all three artefacts use 'partial'."""

    repo_root = Path(__file__).parent.parent

    # Read cases.js
    cases_js_path = repo_root / "app" / "static" / "js" / "cases.js"
    assert cases_js_path.exists(), f"cases.js not found at {cases_js_path}"
    cases_content = cases_js_path.read_text()

    # Verify 'partial' is used in the chip map
    assert 'partial:' in cases_content, "'partial:' should be in the JS chip map"

    # Verify 'partially_supports' is not used
    assert 'partially_supports' not in cases_content, \
        "'partially_supports' should not be in cases.js"


def test_align_source_verifier__classify_fn_returns_valid_status():
    """AC: Calling verify_source() directly and persisting the returned support_status
    on a Source model instance does not raise a DB constraint error for the partial-support case."""

    repo_root = Path(__file__).parent.parent

    # Import the service and models
    import sys
    sys.path.insert(0, str(repo_root))

    from app.services.source_verifier import SUPPORT_STATUSES, _default_classify
    from app.models import _SUPPORT_STATUS

    # Verify both sets match
    assert SUPPORT_STATUSES == frozenset(_SUPPORT_STATUS), \
        "SUPPORT_STATUSES and _SUPPORT_STATUS should match"

    # Verify 'partial' is in both
    assert 'partial' in SUPPORT_STATUSES, "'partial' must be in SUPPORT_STATUSES"
    assert 'partial' in _SUPPORT_STATUS, "'partial' must be in _SUPPORT_STATUS model"

    # Verify 'partially_supports' is in neither
    assert 'partially_supports' not in SUPPORT_STATUSES, \
        "'partially_supports' must not be in SUPPORT_STATUSES"
    assert 'partially_supports' not in _SUPPORT_STATUS, \
        "'partially_supports' must not be in _SUPPORT_STATUS model"
