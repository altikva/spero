# -#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#
# __creation__ = 2026-06-06
# __author__ = "jndjama (Joy Ndjama)"
# __copyright__ = "Copyright 2026 ALTIKVA."
# __licence__ = "MIT & CC BY-NC-SA (https://www.altikva.com/licenses/LICENSE-1.0)"
# -#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#
# Description: Tests for the owner/fleet service (report, approve, orders, fleet).

"""Tests for the dial-home owner service."""

from __future__ import annotations

from fastapi.testclient import TestClient

from spero.owner import create_owner_app


def test_report_approve_orders_roundtrip() -> None:
    c = TestClient(create_owner_app())
    # First report: nothing queued.
    r = c.post("/agents/a1/report", json={"status": {"frozen": False, "targets": []}, "events": []})
    assert r.status_code == 200
    assert r.json() == {"orders": []}
    # Owner approves a target -> queued as an order.
    assert c.post("/agents/a1/approve", json={"target": "orders"}).status_code == 200
    # Next report delivers the approve order, then clears it.
    assert c.post("/agents/a1/report", json={"status": {}, "events": []}).json()["orders"] == [
        {"type": "approve", "target": "orders"}
    ]
    assert c.post("/agents/a1/report", json={"status": {}, "events": []}).json()["orders"] == []


def test_fleet_and_unknown_agent() -> None:
    c = TestClient(create_owner_app())
    c.post("/agents/a1/report", json={"status": {"targets": [{"target": "x"}]}, "events": []})
    fleet = c.get("/agents").json()["agents"]
    assert any(a["id"] == "a1" and a["reports"] == 1 for a in fleet)
    assert c.get("/agents/a1").status_code == 200
    assert c.get("/agents/nope").status_code == 404
