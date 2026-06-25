"""Tests for issue #40: [follow-up] Clarify httpx timeout semantics.

Follow-up to sprint sprint-4 code review of issue #26, which flagged
app/commander_spec.py for using an unspecified httpx timeout.

The code has since been refactored: commander_spec.py now delegates all
HTTP calls to claude_cli.complete(), which uses httpx.Timeout with
explicit per-phase components. These tests verify the concern is resolved.

AC1: httpx.Timeout(60.0, read=30.0) (or a named constant) is used for
     the httpx client at the relevant call site(s) for commander_spec.
AC2: If a different timeout value is chosen, a code comment documents
     the rationale (connect vs. read distinction).
AC3: No httpx client instantiation or request call in app/commander_spec.py
     uses the default (unspecified) timeout.
AC4: Existing tests pass without modification after the change.
"""
import ast
import inspect


def _commander_spec_source() -> str:
    import app.commander_spec as mod
    return inspect.getsource(mod)


def _claude_cli_source() -> str:
    import app.claude_cli as mod
    return inspect.getsource(mod)


# ---------------------------------------------------------------------------
# AC3: No httpx call in commander_spec.py uses an implicit/default timeout
# ---------------------------------------------------------------------------

def test_ac3_no_direct_httpx_client_in_commander_spec():
    """AC3: commander_spec.py contains no httpx.AsyncClient or httpx.Client call.

    All HTTP is delegated to claude_cli.complete(), so there are no direct
    httpx instantiations in commander_spec that could carry an unspecified timeout.
    """
    source = _commander_spec_source()
    tree = ast.parse(source)

    httpx_client_calls = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            func = node.func
            if (
                isinstance(func, ast.Attribute)
                and func.attr in ("AsyncClient", "Client", "get", "post", "put", "delete", "request")
                and isinstance(func.value, ast.Name)
                and func.value.id == "httpx"
            ):
                httpx_client_calls.append(func.attr)

    assert len(httpx_client_calls) == 0, (
        f"commander_spec.py must not contain direct httpx calls; "
        f"found: {httpx_client_calls}. Delegate to claude_cli.complete() instead."
    )


def test_ac3_no_httpx_import_in_commander_spec():
    """AC3: commander_spec.py does not import httpx directly.

    Importing httpx directly would open a path for unspecified timeout calls.
    """
    source = _commander_spec_source()
    tree = ast.parse(source)

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names = [alias.name for alias in node.names]
            assert "httpx" not in names, (
                "commander_spec.py must not import httpx; "
                "all HTTP is handled by claude_cli.complete()"
            )
        elif isinstance(node, ast.ImportFrom) and node.module == "httpx":
            raise AssertionError(
                "commander_spec.py must not import from httpx; "
                "all HTTP is handled by claude_cli.complete()"
            )


# ---------------------------------------------------------------------------
# AC1: Effective httpx call site (via delegation) uses explicit httpx.Timeout
# ---------------------------------------------------------------------------

def test_ac1_effective_timeout_uses_httpx_timeout_object():
    """AC1: The HTTP client used by commander_spec (via claude_cli) uses httpx.Timeout.

    commander_spec delegates to claude_cli.complete(); that function must
    use an explicit httpx.Timeout object, not a bare float or the default.
    """
    source = _claude_cli_source()
    tree = ast.parse(source)

    found = False
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            func = node.func
            if (
                isinstance(func, ast.Attribute)
                and func.attr == "AsyncClient"
                and isinstance(func.value, ast.Name)
                and func.value.id == "httpx"
            ):
                timeout_kw = next((kw for kw in node.keywords if kw.arg == "timeout"), None)
                assert timeout_kw is not None, (
                    "Every httpx.AsyncClient call in claude_cli.py must have timeout= kwarg"
                )
                assert isinstance(timeout_kw.value, ast.Call), (
                    "timeout= must be httpx.Timeout(...), not a bare value"
                )
                call_func = timeout_kw.value.func
                assert (
                    isinstance(call_func, ast.Attribute)
                    and call_func.attr == "Timeout"
                    and isinstance(call_func.value, ast.Name)
                    and call_func.value.id == "httpx"
                ), "timeout= must use httpx.Timeout(...) constructor"
                found = True

    assert found, "httpx.AsyncClient call not found in claude_cli.py"


def test_ac1_effective_timeout_specifies_read_kwarg():
    """AC1: The effective timeout specifies read= explicitly (per the AC suggestion).

    The AC suggests httpx.Timeout(60.0, read=30.0) or equivalent. The
    implementation in claude_cli.py must include an explicit read= value.
    """
    source = _claude_cli_source()
    tree = ast.parse(source)

    found = False
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            func = node.func
            if (
                isinstance(func, ast.Attribute)
                and func.attr == "AsyncClient"
                and isinstance(func.value, ast.Name)
                and func.value.id == "httpx"
            ):
                timeout_kw = next((kw for kw in node.keywords if kw.arg == "timeout"), None)
                if timeout_kw and isinstance(timeout_kw.value, ast.Call):
                    kwarg_names = [kw.arg for kw in timeout_kw.value.keywords]
                    assert "read" in kwarg_names, (
                        f"httpx.Timeout in claude_cli.py must include read= kwarg; "
                        f"found kwargs: {kwarg_names}"
                    )
                    found = True

    assert found, (
        "httpx.AsyncClient with httpx.Timeout timeout= not found in claude_cli.py"
    )


def test_ac1_effective_timeout_has_positive_default():
    """AC1: The httpx.Timeout positional default is a positive number >= 30.0.

    The AC suggests 60.0 as the overall default. Verify the actual value is
    a numeric constant and meets a reasonable minimum.
    """
    source = _claude_cli_source()
    tree = ast.parse(source)

    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            func = node.func
            if (
                isinstance(func, ast.Attribute)
                and func.attr == "AsyncClient"
                and isinstance(func.value, ast.Name)
                and func.value.id == "httpx"
            ):
                timeout_kw = next((kw for kw in node.keywords if kw.arg == "timeout"), None)
                if timeout_kw and isinstance(timeout_kw.value, ast.Call):
                    timeout_node = timeout_kw.value
                    if timeout_node.args:
                        default_arg = timeout_node.args[0]
                        assert isinstance(default_arg, ast.Constant) and isinstance(
                            default_arg.value, (int, float)
                        ), "httpx.Timeout default must be a numeric constant"
                        assert default_arg.value >= 30.0, (
                            f"httpx.Timeout default should be >= 30.0; got {default_arg.value}"
                        )
                    return

    assert False, "httpx.AsyncClient with timeout= not found in claude_cli.py"


# ---------------------------------------------------------------------------
# AC2: A comment near the call site documents the timeout rationale
# ---------------------------------------------------------------------------

def test_ac2_timeout_rationale_documented_near_async_client():
    """AC2: A comment near the httpx.AsyncClient call explains timeout semantics.

    When timeout values differ from the bare httpx.Timeout(60.0, read=30.0)
    suggestion, the rationale (connect vs read vs write phases) must be
    documented inline.
    """
    source = _claude_cli_source()
    lines = source.splitlines()

    client_line_idx = next(
        (i for i, line in enumerate(lines) if "AsyncClient" in line),
        None,
    )
    assert client_line_idx is not None, "AsyncClient line not found in claude_cli.py"

    window_start = max(0, client_line_idx - 5)
    window_end = min(len(lines), client_line_idx + 6)
    window_lines = lines[window_start:window_end]

    assert any("#" in line for line in window_lines), (
        "No inline comment found near httpx.AsyncClient in claude_cli.py. "
        "AC2 requires a comment explaining the timeout rationale."
    )

    comment_lines = [ln for ln in window_lines if "#" in ln]
    comment_text = " ".join(comment_lines).lower()
    has_timeout_context = any(
        kw in comment_text
        for kw in ("timeout", "connect", "read", "write", "pool", "second", "phase")
    )
    assert has_timeout_context, (
        f"Comment near AsyncClient must reference timeout semantics; found: {comment_lines}"
    )


# ---------------------------------------------------------------------------
# AC4: Existing commander_spec API is unchanged; test suite still importable
# ---------------------------------------------------------------------------

def test_ac4_commander_spec_public_api_unchanged():
    """AC4: commander_spec still exports its full public API."""
    import app.commander_spec as mod

    assert hasattr(mod, "generate_commander_spec"), (
        "generate_commander_spec must still exist"
    )
    assert hasattr(mod, "CommanderSpecError"), (
        "CommanderSpecError must still exist"
    )
    assert callable(mod.generate_commander_spec), (
        "generate_commander_spec must be callable"
    )


def test_ac4_generate_commander_spec_is_async():
    """AC4: generate_commander_spec is still an async coroutine function."""
    import app.commander_spec as mod

    assert inspect.iscoroutinefunction(mod.generate_commander_spec), (
        "generate_commander_spec must remain an async function"
    )


def test_ac4_claude_cli_complete_is_async():
    """AC4: claude_cli.complete (the HTTP delegate) is still async."""
    import app.claude_cli as cli

    assert hasattr(cli, "complete"), "claude_cli.complete must still exist"
    assert inspect.iscoroutinefunction(cli.complete), (
        "claude_cli.complete must remain an async function"
    )
