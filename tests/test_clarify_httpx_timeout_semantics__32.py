"""Tests for issue #32: Clarify httpx timeout semantics in commander spec generation.

AC1: app/commander_spec.py uses explicit httpx.Timeout object (already enforced by #31).
AC2: All four timeout components (connect, read, write, pool) are explicitly accounted for.
AC3: No existing behavior of spec generation is changed.
AC4: A brief inline comment explains the rationale for the chosen timeout values.
"""
import ast
import inspect
import re


def _get_source() -> str:
    import app.commander_spec as mod
    return inspect.getsource(mod)


def _get_timeout_call_node() -> ast.Call | None:
    """Return the httpx.Timeout(...) AST node inside httpx.AsyncClient(timeout=...)."""
    source = _get_source()
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
                for kw in node.keywords:
                    if kw.arg == "timeout" and isinstance(kw.value, ast.Call):
                        return kw.value
    return None


# ---------------------------------------------------------------------------
# AC1: httpx.Timeout is still used (guard against regression)
# ---------------------------------------------------------------------------

def test_ac1_uses_httpx_timeout_object():
    """AC1: timeout= argument is an httpx.Timeout(...) constructor call."""
    timeout_node = _get_timeout_call_node()
    assert timeout_node is not None, (
        "httpx.Timeout(...) not found as the timeout= argument of httpx.AsyncClient"
    )
    func = timeout_node.func
    assert (
        isinstance(func, ast.Attribute)
        and func.attr == "Timeout"
        and isinstance(func.value, ast.Name)
        and func.value.id == "httpx"
    ), "timeout= must be httpx.Timeout(...)"


# ---------------------------------------------------------------------------
# AC2: All four timeout components explicitly accounted for
# ---------------------------------------------------------------------------

def test_ac2_write_component_explicitly_set():
    """AC2: httpx.Timeout must include an explicit write= keyword argument."""
    timeout_node = _get_timeout_call_node()
    assert timeout_node is not None, "httpx.Timeout call not found"

    kwarg_names = [kw.arg for kw in timeout_node.keywords]
    assert "write" in kwarg_names, (
        f"httpx.Timeout must include write= kwarg to explicitly account for write timeout; "
        f"found kwargs: {kwarg_names}"
    )


def test_ac2_pool_component_explicitly_set():
    """AC2: httpx.Timeout must include an explicit pool= keyword argument."""
    timeout_node = _get_timeout_call_node()
    assert timeout_node is not None, "httpx.Timeout call not found"

    kwarg_names = [kw.arg for kw in timeout_node.keywords]
    assert "pool" in kwarg_names, (
        f"httpx.Timeout must include pool= kwarg to explicitly account for pool timeout; "
        f"found kwargs: {kwarg_names}"
    )


def test_ac2_connect_component_still_present():
    """AC2: connect= must still be present (not regressed)."""
    timeout_node = _get_timeout_call_node()
    assert timeout_node is not None
    kwarg_names = [kw.arg for kw in timeout_node.keywords]
    assert "connect" in kwarg_names, f"connect= must be present; found: {kwarg_names}"


def test_ac2_read_component_still_present():
    """AC2: read= must still be present (not regressed)."""
    timeout_node = _get_timeout_call_node()
    assert timeout_node is not None
    kwarg_names = [kw.arg for kw in timeout_node.keywords]
    assert "read" in kwarg_names, f"read= must be present; found: {kwarg_names}"


# ---------------------------------------------------------------------------
# AC3: No existing behavior changed
# ---------------------------------------------------------------------------

def test_ac3_generate_commander_spec_still_exists():
    """AC3: generate_commander_spec function is unchanged."""
    import app.commander_spec as mod
    assert hasattr(mod, "generate_commander_spec"), (
        "generate_commander_spec must still exist"
    )
    assert hasattr(mod, "CommanderSpecError"), "CommanderSpecError must still exist"
    assert hasattr(mod, "ANTHROPIC_API_KEY"), "ANTHROPIC_API_KEY must still exist"


def test_ac3_timeout_values_are_numeric():
    """AC3: All httpx.Timeout values are positive floats/ints (no behaviour change)."""
    import httpx

    import app.commander_spec as mod

    source = _get_source()
    timeout_node = _get_timeout_call_node()
    assert timeout_node is not None

    # Evaluate the actual timeout object that the module would construct
    # by checking that all keyword arg values are numeric constants > 0
    for kw in timeout_node.keywords:
        val = kw.value
        assert isinstance(val, ast.Constant) and isinstance(val.value, (int, float)), (
            f"httpx.Timeout kwarg '{kw.arg}' must be a numeric constant; got {ast.dump(val)}"
        )
        assert val.value > 0, f"Timeout component '{kw.arg}' must be positive"

    # Positional default (first arg) must also be numeric
    if timeout_node.args:
        default_val = timeout_node.args[0]
        assert isinstance(default_val, ast.Constant) and isinstance(default_val.value, (int, float)), (
            f"httpx.Timeout first positional arg must be numeric; got {ast.dump(default_val)}"
        )
        assert default_val.value > 0, "httpx.Timeout default must be positive"


# ---------------------------------------------------------------------------
# AC4: Inline comment explains rationale
# ---------------------------------------------------------------------------

def test_ac4_inline_comment_present_near_async_client():
    """AC4: A comment near the httpx.AsyncClient call documents timeout rationale."""
    source = _get_source()

    # Find the block around the AsyncClient instantiation
    lines = source.splitlines()
    client_line_idx = next(
        (i for i, line in enumerate(lines) if "AsyncClient" in line),
        None,
    )
    assert client_line_idx is not None, "AsyncClient line not found in source"

    # Check a window of ±5 lines for a comment
    window_start = max(0, client_line_idx - 5)
    window_end = min(len(lines), client_line_idx + 5)
    window = "\n".join(lines[window_start:window_end])

    assert "#" in window, (
        "No inline comment found near the httpx.AsyncClient call. "
        "AC4 requires a brief comment explaining the timeout rationale."
    )

    # The comment should reference at least one timeout concept
    comment_lines = [l for l in lines[window_start:window_end] if "#" in l]
    comment_text = " ".join(comment_lines).lower()
    has_timeout_context = any(
        kw in comment_text
        for kw in ("timeout", "connect", "read", "write", "pool", "512", "token", "second")
    )
    assert has_timeout_context, (
        f"Comment near AsyncClient must mention timeout semantics; found: {comment_lines}"
    )
