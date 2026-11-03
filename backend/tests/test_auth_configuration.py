"""The real application must reject implicit or unsupported authentication."""
import os
import re
import subprocess
import sys
import time

import httpx
import pytest
from fastapi.testclient import TestClient

from app.core.config import AuthConfigurationError, get_auth_mode
from app.db.session import get_db
from app.main import app


INVALID_MODES = [None, "", " ", "unknown", "disabled", "supabase", "DEMO", " demo "]


@pytest.mark.parametrize("mode", INVALID_MODES)
def test_invalid_auth_mode_fails_before_startup_or_routing(monkeypatch, mode):
    if mode is None:
        monkeypatch.delenv("AUTH_MODE", raising=False)
    else:
        monkeypatch.setenv("AUTH_MODE", mode)

    with pytest.raises(AuthConfigurationError, match="AUTH_MODE"):
        get_auth_mode()
    with pytest.raises(AuthConfigurationError, match="AUTH_MODE"):
        with TestClient(app):
            pytest.fail("Unsupported authentication must prevent startup")

    def unexpected_db():
        pytest.fail("Invalid authentication configuration must not reach the database")

    app.dependency_overrides[get_db] = unexpected_db
    try:
        # Also protect ASGI hosts that omit lifespan and configurations changed at runtime.
        client = TestClient(app)
        for method, path in [
            ("POST", "/api/v1/demo/login"),
            ("GET", "/api/v1/auth/me"),
            ("GET", "/api/v1/dashboards"),
            ("POST", "/api/v1/auth/logout"),
            ("GET", "/health"),
            ("GET", "/docs"),
        ]:
            response = client.request(method, path, json={"email": "demo.admin@queryops.local"})
            assert response.status_code == 503
            assert response.json()["error"]["code"] == "AUTH_CONFIGURATION_ERROR"
            assert "set-cookie" not in response.headers
            assert "demo.admin" not in response.text
    finally:
        app.dependency_overrides.pop(get_db, None)


@pytest.mark.parametrize("mode", INVALID_MODES)
def test_uvicorn_rejects_invalid_auth_mode_before_serving(mode):
    environment = os.environ.copy()
    environment.pop("AUTH_MODE", None)
    if mode is not None:
        environment["AUTH_MODE"] = mode
    result = subprocess.run(
        [sys.executable, "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", "0"],
        env=environment, capture_output=True, text=True, timeout=20,
    )
    assert result.returncode != 0
    assert "AUTH_MODE must be explicitly set to demo" in result.stderr
    assert "Application startup failed" in result.stderr
    assert "Uvicorn running" not in result.stderr


def test_uvicorn_serves_with_explicit_demo_mode(tmp_path):
    assert get_auth_mode() == "demo"
    log_path = tmp_path / "uvicorn.log"
    with log_path.open("w") as log:
        process = subprocess.Popen(
            [sys.executable, "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", "0"],
            stdout=log, stderr=log,
        )
        try:
            deadline = time.monotonic() + 20
            while time.monotonic() < deadline:
                output = log_path.read_text()
                match = re.search(r"Uvicorn running on (http://127\.0\.0\.1:\d+)", output)
                if match:
                    response = httpx.get(f"{match[1]}/health", timeout=5, trust_env=False)
                    assert response.status_code == 200
                    assert response.json()["status"] == "ok"
                    break
                assert process.poll() is None, output
                time.sleep(0.05)
            else:
                pytest.fail(f"Uvicorn did not become ready: {log_path.read_text()}")
        finally:
            process.terminate()
            process.wait(timeout=10)
