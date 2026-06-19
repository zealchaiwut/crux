"""Tests for issue #1: Scaffold FastAPI backend and configure Render deploy."""
import os
import re
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

REPO_ROOT = Path(__file__).parent.parent


# AC1: app/ package with __init__.py and main.py
def test_app_package_exists():
    assert (REPO_ROOT / "app" / "__init__.py").exists()
    assert (REPO_ROOT / "app" / "main.py").exists()


def test_app_main_has_fastapi_instance():
    content = (REPO_ROOT / "app" / "main.py").read_text()
    assert "FastAPI" in content


# AC2: GET /healthz returns 200 with {"status": "ok"} (requires auth — issue #3)
def test_healthz_returns_200(authed_client):
    response = authed_client.get("/healthz")
    assert response.status_code == 200


def test_healthz_returns_json_with_status(authed_client):
    response = authed_client.get("/healthz")
    body = response.json()
    assert "status" in body
    assert body["status"] == "ok"


# AC3: Config from env vars with sensible defaults; no hard-coded values
def test_port_from_env_var(monkeypatch):
    monkeypatch.setenv("PORT", "9999")
    from importlib import reload
    import app.config as cfg
    reload(cfg)
    assert cfg.PORT == 9999
    monkeypatch.delenv("PORT", raising=False)
    reload(cfg)


def test_port_has_default():
    from app.config import PORT
    assert isinstance(PORT, int)
    assert PORT > 0


def test_env_name_from_env_var(monkeypatch):
    monkeypatch.setenv("ENV", "staging")
    from importlib import reload
    import app.config as cfg
    reload(cfg)
    assert cfg.ENV == "staging"
    monkeypatch.delenv("ENV", raising=False)
    reload(cfg)


# AC4: requirements.txt pins all deps to exact versions (==)
def test_requirements_txt_exists():
    assert (REPO_ROOT / "requirements.txt").exists()


def test_requirements_txt_pins_exact_versions():
    content = (REPO_ROOT / "requirements.txt").read_text()
    lines = [l.strip() for l in content.splitlines() if l.strip() and not l.startswith("#")]
    for line in lines:
        assert "==" in line, f"Unpinned dependency: {line}"


def test_requirements_txt_includes_fastapi():
    content = (REPO_ROOT / "requirements.txt").read_text()
    assert "fastapi==" in content.lower() or "fastapi ==" in content.lower()


def test_requirements_txt_includes_uvicorn():
    content = (REPO_ROOT / "requirements.txt").read_text()
    # allow extras notation: uvicorn==... or uvicorn[standard]==...
    assert re.search(r"uvicorn(\[.*?\])?==", content, re.IGNORECASE), "uvicorn must be pinned in requirements.txt"


# AC5: uvicorn invocation documented (Makefile or README)
def test_uvicorn_command_documented():
    makefile = REPO_ROOT / "Makefile"
    readme = REPO_ROOT / "README.md"
    has_uvicorn = False
    if makefile.exists():
        has_uvicorn = has_uvicorn or "uvicorn" in makefile.read_text()
    if readme.exists():
        has_uvicorn = has_uvicorn or "uvicorn" in readme.read_text()
    assert has_uvicorn, "uvicorn command must be documented in Makefile or README.md"


# AC6: render.yaml present, defines web service, start command is uvicorn app.main:app, targets develop
def test_render_yaml_exists():
    assert (REPO_ROOT / "render.yaml").exists()


def test_render_yaml_has_web_service():
    import yaml
    content = (REPO_ROOT / "render.yaml").read_text()
    config = yaml.safe_load(content)
    services = config.get("services", [])
    assert any(s.get("type") == "web" for s in services), "render.yaml must define a web service"


def test_render_yaml_start_command():
    import yaml
    content = (REPO_ROOT / "render.yaml").read_text()
    config = yaml.safe_load(content)
    services = config.get("services", [])
    web_service = next(s for s in services if s.get("type") == "web")
    start_cmd = web_service.get("startCommand", "")
    assert "uvicorn" in start_cmd
    assert "app.main:app" in start_cmd


def test_render_yaml_targets_develop_branch():
    import yaml
    content = (REPO_ROOT / "render.yaml").read_text()
    config = yaml.safe_load(content)
    services = config.get("services", [])
    web_service = next(s for s in services if s.get("type") == "web")
    assert web_service.get("branch") == "develop", "render.yaml web service must target the develop branch"
