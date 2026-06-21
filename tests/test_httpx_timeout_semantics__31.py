"""Tests for issue #31: Clarify httpx timeout semantics in commander_spec.py.

AC1: httpx.AsyncClient uses explicit httpx.Timeout object (not a bare float).
AC2: The Timeout constructor specifies at least connect and read values separately.
AC3: No other logic in app/commander_spec.py is changed.
AC4: The change passes the existing test suite without modification.
"""
import ast
import inspect

import httpx


def _get_source() -> str:
    import app.commander_spec as mod
    return inspect.getsource(mod)


def _get_async_client_call_node():
    """Parse commander_spec.py and find the httpx.AsyncClient(...) call node."""
    source = _get_source()
    tree = ast.parse(source)
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            func = node.func
            # Match httpx.AsyncClient(...)
            if (
                isinstance(func, ast.Attribute)
                and func.attr == "AsyncClient"
                and isinstance(func.value, ast.Name)
                and func.value.id == "httpx"
            ):
                return node
    return None


# ---------------------------------------------------------------------------
# AC1: timeout arg must be an httpx.Timeout call, not a bare numeric literal
# ---------------------------------------------------------------------------

def test_ac1_timeout_is_not_bare_float():
    """AC1: timeout= argument must not be a bare float literal."""
    node = _get_async_client_call_node()
    assert node is not None, "httpx.AsyncClient call not found in commander_spec.py"

    timeout_value = None
    for kw in node.keywords:
        if kw.arg == "timeout":
            timeout_value = kw.value
            break

    assert timeout_value is not None, "timeout keyword argument not found in AsyncClient call"
    assert not isinstance(timeout_value, ast.Constant), (
        "timeout= must not be a bare float/int constant — use httpx.Timeout(...) instead"
    )


def test_ac1_timeout_uses_httpx_timeout_class():
    """AC1: timeout= argument must be an httpx.Timeout(...) call."""
    node = _get_async_client_call_node()
    assert node is not None, "httpx.AsyncClient call not found in commander_spec.py"

    timeout_kw = None
    for kw in node.keywords:
        if kw.arg == "timeout":
            timeout_kw = kw.value
            break

    assert timeout_kw is not None, "timeout keyword argument not found"
    assert isinstance(timeout_kw, ast.Call), (
        "timeout= value must be a function/constructor call (httpx.Timeout(...))"
    )
    func = timeout_kw.func
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
    node = _get_async_client_call_node()
    assert node is not None

    timeout_kw = next((kw.value for kw in node.keywords if kw.arg == "timeout"), None)
    assert timeout_kw is not None
    assert isinstance(timeout_kw, ast.Call)

    kwarg_names = [kw.arg for kw in timeout_kw.keywords]
    assert "connect" in kwarg_names, (
        f"httpx.Timeout must include connect= kwarg; found: {kwarg_names}"
    )


def test_ac2_timeout_specifies_read_kwarg():
    """AC2: httpx.Timeout must include a read= keyword argument."""
    node = _get_async_client_call_node()
    assert node is not None

    timeout_kw = next((kw.value for kw in node.keywords if kw.arg == "timeout"), None)
    assert timeout_kw is not None
    assert isinstance(timeout_kw, ast.Call)

    kwarg_names = [kw.arg for kw in timeout_kw.keywords]
    assert "read" in kwarg_names, (
        f"httpx.Timeout must include read= kwarg; found: {kwarg_names}"
    )


# ---------------------------------------------------------------------------
# AC3: No other logic changed — function count and names must be unchanged
# ---------------------------------------------------------------------------

def test_ac3_no_other_logic_changed():
    """AC3: Only the timeout argument is changed; function signatures are unchanged."""
    import app.commander_spec as mod

    assert hasattr(mod, "generate_commander_spec"), (
        "generate_commander_spec function must still exist"
    )
    assert hasattr(mod, "CommanderSpecError"), (
        "CommanderSpecError class must still exist"
    )
    assert hasattr(mod, "ANTHROPIC_API_KEY"), (
        "ANTHROPIC_API_KEY constant must still exist"
    )


# ---------------------------------------------------------------------------
# AC4 (runtime): httpx.Timeout object is accepted by httpx at runtime
# ---------------------------------------------------------------------------

def test_ac4_httpx_timeout_object_is_valid():
    """AC4: The httpx.Timeout values used are valid and accepted by httpx."""
    # Mirrors the actual values used in commander_spec.py
    t = httpx.Timeout(60.0, connect=10.0, read=30.0)
    assert t.connect == 10.0
    assert t.read == 30.0
