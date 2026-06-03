"""Tests for the FastAPI control plane."""

from __future__ import annotations

from fastapi.testclient import TestClient

from spero import __version__
from spero.api.app import app

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
