"""Middleware-level tests for maintenance mode.

We mount the middleware on a minimal FastAPI app so we can hit it via the
TestClient and assert exact response shape.
"""
import os
import sys

from fastapi import FastAPI
from fastapi.testclient import TestClient

THIS_DIR = os.path.dirname(os.path.abspath(__file__))
BACKEND_DIR = os.path.dirname(THIS_DIR)
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)

from app.middleware.maintenance import (  # noqa: E402
    MaintenanceMiddleware,
    enable_maintenance_mode,
    disable_maintenance_mode,
    get_maintenance_state,
)


def _make_app() -> TestClient:
    app = FastAPI()
    app.add_middleware(MaintenanceMiddleware)

    @app.get("/api/anything")
    async def get_anything():
        return {"ok": True}

    @app.post("/api/write")
    async def write():
        return {"ok": True}

    @app.post("/api/auth/login")
    async def login():
        return {"ok": True}

    @app.post("/api/backup/run")
    async def backup_run():
        return {"ok": True}

    return TestClient(app)


def test_normal_mode_allows_writes():
    disable_maintenance_mode()
    client = _make_app()
    assert client.post("/api/write").status_code == 200


def test_maintenance_blocks_non_exempt_writes():
    enable_maintenance_mode("Restoring")
    try:
        client = _make_app()
        r = client.post("/api/write")
        assert r.status_code == 503
        body = r.json()
        assert body["maintenance"] is True
        assert "Restoring" in body["detail"]
    finally:
        disable_maintenance_mode()


def test_maintenance_allows_gets():
    enable_maintenance_mode("Restoring")
    try:
        client = _make_app()
        r = client.get("/api/anything")
        assert r.status_code == 200
    finally:
        disable_maintenance_mode()


def test_maintenance_allows_exempt_paths():
    enable_maintenance_mode("Restoring")
    try:
        client = _make_app()
        assert client.post("/api/auth/login").status_code == 200
        assert client.post("/api/backup/run").status_code == 200
    finally:
        disable_maintenance_mode()


def test_state_reflects_toggles():
    disable_maintenance_mode()
    assert get_maintenance_state()["active"] is False
    enable_maintenance_mode("custom reason")
    try:
        state = get_maintenance_state()
        assert state["active"] is True
        assert state["reason"] == "custom reason"
        assert state["started_at"]
    finally:
        disable_maintenance_mode()
