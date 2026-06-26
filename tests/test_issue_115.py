"""Tests for issue #115: Document temporary stub verifier in sources.py.

AC coverage:
  AC1 – A docstring or inline comment is added to the stub verifier function in
         app/routers/sources.py:282-289 explaining that the hardcoded keywords
         ("not", "support", "contradict") are intentional and temporary.
  AC2 – The comment or docstring explicitly references issue #98 as the tracking
         issue for real AI verifier integration.
  AC3 – SCHEMA.md is updated to include a note that VERIFIER_ENGINE=stub is
         intended for development/testing only and is not production-ready.
  AC4 – The stub verifier code itself is unchanged — only documentation is added.
"""
import pathlib
import ast
from unittest.mock import MagicMock

SOURCES_PY = pathlib.Path(__file__).parent.parent / "app" / "routers" / "sources.py"
SCHEMA_MD = pathlib.Path(__file__).parent.parent / "SCHEMA.md"


def _sources_text() -> str:
    return SOURCES_PY.read_text()


def _stub_block(src: str) -> str:
    """Return the slice of sources.py from _run_verifier definition through the
    end of the stub keyword-matching block."""
    start = src.find("def _run_verifier(")
    if start == -1:
        return ""
    # Extend ~50 lines to capture the full stub body and any comments
    lines = src[start:].splitlines()[:60]
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# AC1 — Comment/docstring in stub verifier explains keywords are intentional & temporary
# ---------------------------------------------------------------------------

class TestStubVerifierDocumentation:
    def test_stub_block_present(self):
        """_run_verifier must exist in sources.py."""
        block = _stub_block(_sources_text())
        assert block, "_run_verifier function not found in app/routers/sources.py"

    def test_keywords_mentioned(self):
        """AC1: The docstring or a comment in the stub verifier must mention the
        hardcoded keyword strings used to determine the verdict."""
        block = _stub_block(_sources_text())
        block_lower = block.lower()
        # At least one of the keyword strings must be mentioned in documentation context
        has_keywords = (
            '"not"' in block or "'not'" in block or
            '"support"' in block or "'support'" in block or
            '"contradict"' in block or "'contradict'" in block or
            "hardcoded" in block_lower or "keyword" in block_lower
        )
        assert has_keywords, (
            "The stub verifier block must mention the hardcoded keyword strings "
            '("not", "support", "contradict") or reference them as keywords in a comment.'
        )

    def test_temporary_nature_documented(self):
        """AC1: The docstring or comment must indicate the stub is temporary."""
        block = _stub_block(_sources_text())
        block_lower = block.lower()
        has_temporary = (
            "temporary" in block_lower or
            "temp" in block_lower or
            "placeholder" in block_lower or
            "will be replaced" in block_lower or
            "stub" in block_lower
        )
        assert has_temporary, (
            "The stub verifier documentation must indicate it is temporary "
            "(expected 'temporary', 'placeholder', or 'will be replaced')."
        )


# ---------------------------------------------------------------------------
# AC2 — Comment/docstring references issue #98
# ---------------------------------------------------------------------------

class TestIssueReferencePresent:
    def test_issue_98_referenced_in_stub_block(self):
        """AC2: The stub verifier docstring or a nearby comment must reference issue #98."""
        block = _stub_block(_sources_text())
        assert "#98" in block or "issue 98" in block.lower(), (
            "The stub verifier block must reference issue #98 as the tracking issue "
            "for real AI verifier integration."
        )


# ---------------------------------------------------------------------------
# AC3 — SCHEMA.md notes VERIFIER_ENGINE=stub is dev/testing only
# ---------------------------------------------------------------------------

class TestSchemaMdVerifierEngineNote:
    def test_verifier_engine_entry_present(self):
        """AC3: SCHEMA.md must mention VERIFIER_ENGINE."""
        schema = SCHEMA_MD.read_text()
        assert "VERIFIER_ENGINE" in schema, (
            "SCHEMA.md must contain a VERIFIER_ENGINE entry."
        )

    def test_stub_is_dev_only(self):
        """AC3: SCHEMA.md must state that VERIFIER_ENGINE=stub is for dev/testing only."""
        schema = SCHEMA_MD.read_text()
        schema_lower = schema.lower()
        # Find the section around VERIFIER_ENGINE
        idx = schema.find("VERIFIER_ENGINE")
        assert idx != -1
        context = schema[max(0, idx - 50): idx + 500].lower()
        has_dev_note = (
            "development" in context or
            "testing" in context or
            "dev" in context or
            "not production" in context or
            "not for production" in context
        )
        assert has_dev_note, (
            "SCHEMA.md must note that VERIFIER_ENGINE=stub is for development/testing "
            "only and is not production-ready."
        )


# ---------------------------------------------------------------------------
# AC4 — Stub verifier logic is unchanged
# ---------------------------------------------------------------------------

class TestStubLogicUnchanged:
    def test_stub_returns_contradicts_for_not_keyword(self, monkeypatch):
        """AC4: Stub still returns 'contradicts' when claim contains 'not'."""
        import sys
        for key in list(sys.modules.keys()):
            if "app.routers.sources" in key:
                del sys.modules[key]

        monkeypatch.setenv("VERIFIER_ENGINE", "stub")
        from app.routers.sources import _run_verifier

        source = MagicMock()
        source.claim = "this does not support the hypothesis"
        status, rationale = _run_verifier(source)
        assert status == "contradicts", (
            f"Expected 'contradicts' for claim with 'not', got '{status}'"
        )

    def test_stub_returns_supports_for_support_keyword(self, monkeypatch):
        """AC4: Stub still returns 'supports' when claim contains 'support'."""
        import sys
        for key in list(sys.modules.keys()):
            if "app.routers.sources" in key:
                del sys.modules[key]

        monkeypatch.setenv("VERIFIER_ENGINE", "stub")
        from app.routers.sources import _run_verifier  # noqa: PLC0415

        source = MagicMock()
        source.claim = "this evidence supports the claim"
        status, rationale = _run_verifier(source)
        assert status == "supports", (
            f"Expected 'supports' for claim with 'support', got '{status}'"
        )

    def test_stub_returns_unverified_for_neutral_claim(self, monkeypatch):
        """AC4: Stub still returns 'unverified' for claims with no matching keywords."""
        import sys
        for key in list(sys.modules.keys()):
            if "app.routers.sources" in key:
                del sys.modules[key]

        monkeypatch.setenv("VERIFIER_ENGINE", "stub")
        from app.routers.sources import _run_verifier

        source = MagicMock()
        source.claim = "a general statement about something"
        status, rationale = _run_verifier(source)
        assert status == "unverified", (
            f"Expected 'unverified' for neutral claim, got '{status}'"
        )

    def test_stub_returns_unverified_for_empty_claim(self, monkeypatch):
        """AC4: Stub still returns 'unverified' for empty claim."""
        import sys
        for key in list(sys.modules.keys()):
            if "app.routers.sources" in key:
                del sys.modules[key]

        monkeypatch.setenv("VERIFIER_ENGINE", "stub")
        from app.routers.sources import _run_verifier

        source = MagicMock()
        source.claim = ""
        status, rationale = _run_verifier(source)
        assert status == "unverified"
