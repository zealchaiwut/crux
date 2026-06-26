"""Tests for issue #114: Move os import to module level in routers/sources.py."""
import ast
import pathlib


SOURCES_PY = pathlib.Path(__file__).parent.parent / "app" / "routers" / "sources.py"


def _parse_tree():
    return ast.parse(SOURCES_PY.read_text())


def test_no_import_os_inside_function():
    """AC: import os is removed from the body of _run_verifier()."""
    tree = _parse_tree()
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            for child in ast.walk(node):
                if isinstance(child, ast.Import):
                    for alias in child.names:
                        assert alias.name != "os", (
                            f"Found 'import os' inside function '{node.name}' "
                            f"at line {child.lineno}"
                        )


def test_import_os_at_module_level():
    """AC: import os appears at the module level in sources.py."""
    tree = _parse_tree()
    module_level_imports = [
        node for node in ast.iter_child_nodes(tree)
        if isinstance(node, ast.Import)
    ]
    os_imported = any(
        alias.name == "os"
        for node in module_level_imports
        for alias in node.names
    )
    assert os_imported, "Expected 'import os' at module level but did not find it"


def test_exactly_one_import_os():
    """AC: No other references to 'import os' remain inside any function body."""
    source_text = SOURCES_PY.read_text()
    count = source_text.count("import os")
    assert count == 1, (
        f"Expected exactly one 'import os' in sources.py, found {count}"
    )


def test_run_verifier_still_works(monkeypatch):
    """AC: All existing functionality that depends on os in _run_verifier() works."""
    import importlib
    import sys

    # Remove cached module if present
    for key in list(sys.modules.keys()):
        if "app.routers.sources" in key:
            del sys.modules[key]

    from app.routers.sources import _run_verifier
    from unittest.mock import MagicMock

    source = MagicMock()
    source.claim = "this is a normal claim"
    source.citation = "http://example.com"

    monkeypatch.setenv("VERIFIER_ENGINE", "stub")
    status, rationale = _run_verifier(source)
    assert status in ("supports", "partial", "contradicts", "unverified")
    assert isinstance(rationale, str) and len(rationale) > 0
