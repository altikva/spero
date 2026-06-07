# -#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#
# __creation__ = 2026-06-07
# __author__ = "jndjama (Joy Ndjama)"
# __copyright__ = "Copyright 2026 ALTIKVA."
# __licence__ = "MIT & CC BY-NC-SA (https://www.altikva.com/licenses/LICENSE-1.0)"
# -#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#
# Description: Tests for the bearer-token auth on the serve and owner HTTP surfaces.

"""Tests for control-plane / owner bearer-token auth (api/auth.py)."""

from __future__ import annotations

from fastapi.testclient import TestClient

from spero.api.app import create_app
from spero.config import Settings
from spero.owner import create_owner_app

_TOKEN = "s3cr3t-token"
_AUTH = {"Authorization": f"Bearer {_TOKEN}"}


def test_serve_open_when_no_token() -> None:
    # Empty token = auth disabled; a guarded route is reachable with no header.
    api = TestClient(create_app(Settings(api_token="")))
    assert api.get("/targets").status_code != 401


def test_serve_requires_token_when_set() -> None:
    api = TestClient(create_app(Settings(api_token=_TOKEN)))
    assert api.get("/status").status_code == 401  # no header
    assert api.get("/status", headers={"Authorization": "Bearer wrong"}).status_code == 401
    # Correct token passes auth; 503 (no supervisor) proves we reached the handler.
    assert api.get("/status", headers=_AUTH).status_code == 503


def test_serve_health_always_open() -> None:
    api = TestClient(create_app(Settings(api_token=_TOKEN)))
    assert api.get("/health").status_code == 200  # kubelet probe must work


def test_owner_requires_token_when_set() -> None:
    c = TestClient(create_owner_app(token=_TOKEN))
    assert c.get("/health").status_code == 200  # open
    assert c.get("/agents").status_code == 401  # guarded, no header
    assert c.get("/agents", headers=_AUTH).status_code == 200
    body = {"status": {}, "events": []}
    assert c.post("/agents/a1/report", json=body).status_code == 401
    assert c.post("/agents/a1/report", json=body, headers=_AUTH).status_code == 200


def test_owner_open_when_no_token() -> None:
    c = TestClient(create_owner_app(token=""))
    assert c.get("/agents").status_code == 200
