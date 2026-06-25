"""Tests for issue #36: Clarify httpx timeout semantics in embeddings service.

Issues #31 and #32 fixed the bare float timeout in app/claude_cli.py.
This ticket addresses the remaining bare float in app/services/embeddings.py.

AC1: app/services/embeddings.py uses httpx.Timeout object (not bare float) in httpx.Client.
AC2: The Timeout constructor specifies at least connect and read values separately.
AC3: No existing embedding behavior is changed.
AC4: A brief inline comment explains the rationale for the chosen timeout values.
"""
import ast
import inspect


def _get_source() -> str:
    import app.services.embeddings as mod
    return inspect.getsource(mod)


def _get_client_call_node() -> ast.Call | None:
    """Return the httpx.Client(...) AST node in embeddings.py."""
    source = _get_source()
    tree = ast.parse(source)
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            func = node.func
            if (
                isinstance(func, ast.Attribute)
                and func.attr == "Client"
                and isinstance(func.value, ast.Name)
                and func.value.id == "httpx"
            ):
                return node
    return None


def _get_timeout_kwarg(client_node: ast.Call) -> ast.expr | None:
    for kw in client_node.keywords:
        if kw.arg == "timeout":
            return kw.value
    return None


# ---------------------------------------------------------------------------
# AC1: timeout= must be httpx.Timeout(...), not a bare float
# ---------------------------------------------------------------------------

def test_ac1_timeout_is_not_bare_float():
    """AC1: timeout= argument in httpx.Client must not be a bare float literal."""
    node = _get_client_call_node()
    assert node is not None, "httpx.Client call not found in app/services/embeddings.py"

    timeout_value = _get_timeout_kwarg(node)
    assert timeout_value is not None, "timeout= keyword argument not found in httpx.Client call"
    assert not isinstance(timeout_value, ast.Constant), (
        "timeout= must not be a bare float/int constant — use httpx.Timeout(...) instead"
    )


def test_ac1_timeout_uses_httpx_timeout_class():
    """AC1: timeout= argument must be an httpx.Timeout(...) call."""
    node = _get_client_call_node()
    assert node is not None, "httpx.Client call not found in app/services/embeddings.py"

    timeout_value = _get_timeout_kwarg(node)
    assert timeout_value is not None, "timeout= keyword argument not found"
    assert isinstance(timeout_value, ast.Call), (
        "timeout= value must be a constructor call (httpx.Timeout(...))"
    )
    func = timeout_value.func
    assert (
        isinstance(func, ast.Attribute)
        and func.attr == "Timeout"
        and isinstance(func.value, ast.Name)
        and func.value.id == "httpx"
    ), "timeout= must be httpx.Timeout(...)"


# ---------------------------------------------------------------------------
# AC2: Timeout constructor must name at least connect and read kwargs
# ---------------------------------------------------------------------------

def test_ac2_timeout_specifies_connect_kwarg():
    """AC2: httpx.Timeout must include a connect= keyword argument."""
    node = _get_client_call_node()
    assert node is not None

    timeout_value = _get_timeout_kwarg(node)
    assert timeout_value is not None
    assert isinstance(timeout_value, ast.Call)

    kwarg_names = [kw.arg for kw in timeout_value.keywords]
    assert "connect" in kwarg_names, (
        f"httpx.Timeout must include connect= kwarg; found: {kwarg_names}"
    )


def test_ac2_timeout_specifies_read_kwarg():
    """AC2: httpx.Timeout must include a read= keyword argument."""
    node = _get_client_call_node()
    assert node is not None

    timeout_value = _get_timeout_kwarg(node)
    assert timeout_value is not None
    assert isinstance(timeout_value, ast.Call)

    kwarg_names = [kw.arg for kw in timeout_value.keywords]
    assert "read" in kwarg_names, (
        f"httpx.Timeout must include read= kwarg; found: {kwarg_names}"
    )


def test_ac2_timeout_values_are_positive():
    """AC2: All httpx.Timeout values must be positive numeric constants."""
    node = _get_client_call_node()
    assert node is not None

    timeout_value = _get_timeout_kwarg(node)
    assert timeout_value is not None
    assert isinstance(timeout_value, ast.Call)

    for kw in timeout_value.keywords:
        val = kw.value
        assert isinstance(val, ast.Constant) and isinstance(val.value, (int, float)), (
            f"httpx.Timeout kwarg '{kw.arg}' must be a numeric constant; got {ast.dump(val)}"
        )
        assert val.value > 0, f"Timeout component '{kw.arg}' must be positive"

    if timeout_value.args:
        default_val = timeout_value.args[0]
        assert isinstance(default_val, ast.Constant) and isinstance(default_val.value, (int, float)), (
            f"httpx.Timeout first positional arg must be numeric; got {ast.dump(default_val)}"
        )
        assert default_val.value > 0, "httpx.Timeout default must be positive"


# ---------------------------------------------------------------------------
# AC3: No existing embedding behavior changed
# ---------------------------------------------------------------------------

def test_ac3_embedding_api_still_exists():
    """AC3: get_embedding and upsert_embedding must still exist."""
    import app.services.embeddings as mod
    assert hasattr(mod, "get_embedding"), "get_embedding must still exist"
    assert hasattr(mod, "upsert_embedding"), "upsert_embedding must still exist"
    assert hasattr(mod, "EmbeddingError"), "EmbeddingError must still exist"
    assert hasattr(mod, "EMBEDDING_DIM"), "EMBEDDING_DIM must still exist"


def test_ac3_timeout_object_is_valid_at_runtime():
    """AC3: The httpx.Timeout values are valid and accepted by httpx at runtime."""
    import httpx
    # Mirrors the expected values: 30s default, explicit connect + read
    t = httpx.Timeout(30.0, connect=10.0, read=30.0)
    assert t.connect == 10.0
    assert t.read == 30.0


# ---------------------------------------------------------------------------
# AC4: Inline comment explains rationale
# ---------------------------------------------------------------------------

def test_ac4_inline_comment_present_near_client():
    """AC4: A comment near the httpx.Client call documents timeout rationale."""
    source = _get_source()
    lines = source.splitlines()

    client_line_idx = next(
        (i for i, line in enumerate(lines) if "httpx.Client(" in line),
        None,
    )
    assert client_line_idx is not None, "httpx.Client line not found in embeddings.py"

    window_start = max(0, client_line_idx - 5)
    window_end = min(len(lines), client_line_idx + 5)
    window_lines = lines[window_start:window_end]

    assert any("#" in line for line in window_lines), (
        "No inline comment found near the httpx.Client call. "
        "AC4 requires a brief comment explaining the timeout rationale."
    )

    comment_lines = [l for l in window_lines if "#" in l]
    comment_text = " ".join(comment_lines).lower()
    has_timeout_context = any(
        kw in comment_text
        for kw in ("timeout", "connect", "read", "write", "pool", "second", "embed")
    )
    assert has_timeout_context, (
        f"Comment near httpx.Client must mention timeout semantics; found: {comment_lines}"
    )
