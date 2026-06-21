"""Tests for issue #15: Narrow exception handler in verify_session_cookie.

Follow-up on issue #3 code review (see #14). The except clause must be narrowed
from the broad `(BadSignature, Exception)` to only `BadSignature` so that
unexpected exceptions surface instead of being silently swallowed.
"""
import pytest
from unittest.mock import patch

from itsdangerous import BadSignature

from app.auth import create_session_cookie, verify_session_cookie

SECRET = "a" * 32


# AC1 — Valid cookie still verifies as True after the narrowing

def test_valid_cookie_still_returns_true():
    token = create_session_cookie(SECRET)
    assert verify_session_cookie(token, SECRET) is True


# AC2 — BadSignature (tampered / forged tokens) is still caught and returns False

def test_tampered_token_returns_false():
    assert verify_session_cookie("tampered.invalid.cookie", SECRET) is False


def test_empty_token_returns_false():
    assert verify_session_cookie("", SECRET) is False


def test_forged_unsigned_token_returns_false():
    assert verify_session_cookie('{"auth": true}', SECRET) is False


def test_bad_signature_explicitly_caught():
    """BadSignature raised by the serializer must be caught and return False."""
    with patch("app.auth.URLSafeSerializer") as mock_cls:
        mock_cls.return_value.loads.side_effect = BadSignature("bad sig")
        assert verify_session_cookie("anytoken", SECRET) is False


# AC3 — Non-BadSignature exceptions are NOT silently swallowed

def test_type_error_propagates():
    """TypeError must not be masked by an overly broad except clause."""
    with patch("app.auth.URLSafeSerializer") as mock_cls:
        mock_cls.return_value.loads.side_effect = TypeError("unexpected")
        with pytest.raises(TypeError):
            verify_session_cookie("anytoken", SECRET)


def test_attribute_error_propagates():
    """AttributeError must not be masked by an overly broad except clause."""
    with patch("app.auth.URLSafeSerializer") as mock_cls:
        mock_cls.return_value.loads.side_effect = AttributeError("missing attr")
        with pytest.raises(AttributeError):
            verify_session_cookie("anytoken", SECRET)


def test_runtime_error_propagates():
    """RuntimeError must not be masked — broad Exception catch is forbidden."""
    with patch("app.auth.URLSafeSerializer") as mock_cls:
        mock_cls.return_value.loads.side_effect = RuntimeError("oops")
        with pytest.raises(RuntimeError):
            verify_session_cookie("anytoken", SECRET)
