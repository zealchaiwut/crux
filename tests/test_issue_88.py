"""Tests for issue #88: Clarify type hint for batch endpoint sources parameter.

AC coverage:
  AC1 – sources parameter is typed as List[Dict[str, Any]] instead of List[Any]
  AC2 – Dict and Any are both imported from typing correctly
  AC3 – No runtime behavior changes (endpoint accepts same valid payloads)
  AC4 – Type annotation is more specific than Any (List[Dict[str, Any]])
"""
from __future__ import annotations

import inspect
import os
import typing
import uuid

import pytest

os.environ.setdefault("AUTH_SECRET", "test_auth_secret_12345678901")


# ---------------------------------------------------------------------------
# AC1: Type annotation on BatchCreateSourceRequest.sources is List[Dict[str, Any]]
# ---------------------------------------------------------------------------

def test_sources_field_type_is_list_of_dict():
    """AC1: sources is typed as List[Dict[str, Any]], not List[Any]."""
    from app.routers.sources import BatchCreateSourceRequest

    hints = typing.get_type_hints(BatchCreateSourceRequest)
    sources_hint = hints["sources"]

    # Must be a generic alias (List[...])
    origin = getattr(sources_hint, "__origin__", None)
    assert origin is list, f"sources origin must be list, got {origin}"

    args = getattr(sources_hint, "__args__", ())
    assert len(args) == 1, f"List must have one type argument, got {args}"

    inner = args[0]
    inner_origin = getattr(inner, "__origin__", None)
    assert inner_origin is dict, (
        f"sources inner type must be dict (i.e. Dict[str, Any]), got {inner}"
    )


def test_sources_field_not_list_of_any():
    """AC1: sources must NOT be typed as List[Any] (the old permissive type)."""
    from app.routers.sources import BatchCreateSourceRequest

    hints = typing.get_type_hints(BatchCreateSourceRequest)
    sources_hint = hints["sources"]

    args = getattr(sources_hint, "__args__", ())
    if args:
        inner = args[0]
        # If inner is just Any, that's the old bad type
        assert inner is not typing.Any, (
            "sources must not be typed as List[Any]; expected List[Dict[str, Any]]"
        )


# ---------------------------------------------------------------------------
# AC2: Dict and Any are both importable from app.routers.sources
# ---------------------------------------------------------------------------

def test_dict_imported_in_sources_module():
    """AC2: Dict is imported in app.routers.sources (from typing or builtins)."""
    import app.routers.sources as sources_mod

    # The module must have access to Dict — either as a name or via typing
    module_source = inspect.getsource(sources_mod)
    assert "Dict" in module_source or "dict[str," in module_source, (
        "Dict must appear in sources.py (from typing import Dict, or dict[str, Any] usage)"
    )


def test_any_imported_in_sources_module():
    """AC2: Any is imported in app.routers.sources."""
    import app.routers.sources as sources_mod

    module_source = inspect.getsource(sources_mod)
    assert "Any" in module_source, "Any must be imported in sources.py"


# ---------------------------------------------------------------------------
# AC3: No runtime behavior changes — endpoint still accepts valid dict payloads
# ---------------------------------------------------------------------------

def _make_engine():
    from sqlalchemy import create_engine
    from sqlalchemy.pool import StaticPool
    from app.models import Base

    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    return engine


@pytest.fixture()
def db_session():
    engine = _make_engine()
    from sqlalchemy.orm import sessionmaker

    Session = sessionmaker(bind=engine)
    session = Session()
    yield session
    session.close()
    engine.dispose()


@pytest.fixture()
def api_client(db_session):
    from app.main import app
    from app.db import get_db
    from app.auth import create_session_cookie
    from app.config import AUTH_SECRET
    from fastapi.testclient import TestClient

    def _override():
        yield db_session

    app.dependency_overrides[get_db] = _override
    tc = TestClient(app)
    tc.cookies.set("session", create_session_cookie(AUTH_SECRET))
    yield tc
    app.dependency_overrides.pop(get_db, None)


def _seed_plan(session, label="A"):
    from app import models

    case = models.Case(
        id=str(uuid.uuid4()),
        raw_problem="Test problem",
        sharpened="Sharpened test",
        stage="gather",
    )
    session.add(case)
    session.flush()
    plan = models.Plan(
        id=str(uuid.uuid4()),
        case_id=case.id,
        label=label,
        name=f"Plan {label}",
        mechanism="Some mechanism.",
        prior="0.5",
        current_rank=1,
    )
    session.add(plan)
    session.commit()
    return plan


def _valid_source(overrides=None):
    base = {
        "kind": "article",
        "title": "Test Article",
        "url": "https://example.com/article",
        "claim": "Supports hypothesis",
        "citation": "Smith 2024",
    }
    if overrides:
        base.update(overrides)
    return base


def test_batch_endpoint_accepts_list_of_dicts(api_client, db_session):
    """AC3: Endpoint still accepts a list of dictionaries as before."""
    plan = _seed_plan(db_session)
    sources = [
        _valid_source({"title": "First"}),
        _valid_source({"title": "Second", "kind": "book"}),
    ]
    r = api_client.post("/api/sources/batch", json={"plan_id": plan.id, "sources": sources})
    assert r.status_code == 201, r.text
    data = r.json()
    assert len(data) == 2


def test_batch_endpoint_response_unchanged(api_client, db_session):
    """AC3: Response shape is unchanged after the type hint update."""
    plan = _seed_plan(db_session)
    r = api_client.post("/api/sources/batch", json={
        "plan_id": plan.id,
        "sources": [_valid_source()],
    })
    assert r.status_code == 201, r.text
    row = r.json()[0]
    for field in ("id", "plan_id", "kind", "title", "url", "claim", "citation"):
        assert field in row, f"Response row must include '{field}'"


# ---------------------------------------------------------------------------
# AC4: Type annotation is more constrained — Dict[str, Any] not just Any
# ---------------------------------------------------------------------------

def test_sources_inner_type_has_str_key():
    """AC4: The dict key type is str (not Any or object)."""
    from app.routers.sources import BatchCreateSourceRequest

    hints = typing.get_type_hints(BatchCreateSourceRequest)
    sources_hint = hints["sources"]

    inner = sources_hint.__args__[0]
    dict_args = getattr(inner, "__args__", ())
    assert len(dict_args) == 2, f"Dict must have 2 type args (key, value), got {dict_args}"
    key_type = dict_args[0]
    assert key_type is str, f"Dict key type must be str, got {key_type}"


def test_sources_inner_type_has_any_value():
    """AC4: The dict value type is Any (flexible values, typed keys)."""
    from app.routers.sources import BatchCreateSourceRequest

    hints = typing.get_type_hints(BatchCreateSourceRequest)
    sources_hint = hints["sources"]

    inner = sources_hint.__args__[0]
    dict_args = getattr(inner, "__args__", ())
    assert len(dict_args) == 2, f"Dict must have 2 type args, got {dict_args}"
    value_type = dict_args[1]
    assert value_type is typing.Any, f"Dict value type must be Any, got {value_type}"
