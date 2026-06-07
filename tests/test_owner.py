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


_VALID_POLICY = """
version: 1
targets:
  - name: nginx
    provider: local
    probe:
      type: systemd
      params:
        unit: nginx.service
    remediations:
      - type: restart
        params:
          unit: nginx.service
        autonomy: gated
        max_attempts: 2
"""


def test_policy_push_queues_and_delivers() -> None:
    c = TestClient(create_owner_app())
    r = c.post("/agents/a1/policy", json={"policy": _VALID_POLICY})
    assert r.status_code == 200
    assert r.json() == {"queued": "policy"}
    # The queued policy order rides the next report, then clears.
    orders = c.post("/agents/a1/report", json={"status": {}, "events": []}).json()["orders"]
    assert orders == [{"type": "policy", "policy": _VALID_POLICY}]
    assert c.post("/agents/a1/report", json={"status": {}, "events": []}).json()["orders"] == []


def test_policy_push_rejects_invalid() -> None:
    c = TestClient(create_owner_app())
    # Malformed: a remediation list whose escalation ladder is unbuildable.
    bad = "version: 1\ntargets:\n  - {name: x, provider: local}\n"
    r = c.post("/agents/a1/policy", json={"policy": bad})
    assert r.status_code == 422
    # Unparseable YAML is rejected too, and nothing gets queued.
    assert c.post("/agents/a1/policy", json={"policy": "targets: [unclosed"}).status_code == 422
    assert c.post("/agents/a1/report", json={"status": {}, "events": []}).json()["orders"] == []


def test_fleet_and_unknown_agent() -> None:
    c = TestClient(create_owner_app())
    c.post("/agents/a1/report", json={"status": {"targets": [{"target": "x"}]}, "events": []})
    fleet = c.get("/agents").json()["agents"]
    assert any(a["id"] == "a1" and a["reports"] == 1 for a in fleet)
    assert c.get("/agents/a1").status_code == 200
    assert c.get("/agents/nope").status_code == 404
