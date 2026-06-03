"""Tests for the FastAPI control plane."""

from __future__ import annotations

from fastapi.testclient import TestClient

from spero import __version__
from spero.api.app import app, create_app
from spero.config import Settings

client = TestClient(app)


def test_health() -> None:
    r = client.get("/health")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert body["version"] == __version__


def test_targets_lists_policy() -> None:
    r = client.get("/targets")
    assert r.status_code == 200
    body = r.json()
    assert "targets" in body
    names = {t["name"] for t in body["targets"]}
    assert "nginx" in names


def test_targets_missing_policy_returns_503() -> None:
    bad_app = create_app(Settings(policy_path="does/not/exist.yaml"))
    r = TestClient(bad_app).get("/targets")
    assert r.status_code == 503
    assert "not found" in r.json()["detail"]
