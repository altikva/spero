# -#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#
# __creation__ = 2026-06-06
# __author__ = "jndjama (Joy Ndjama)"
# __copyright__ = "Copyright 2026 ALTIKVA."
# __licence__ = "MIT & CC BY-NC-SA (https://www.altikva.com/licenses/LICENSE-1.0)"
# -#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#
# Description: Tests for the Supervisor (live status/events serialization + watch lifecycle).

"""Tests for the Supervisor that backs `spero serve`."""

from __future__ import annotations

from spero.api.supervisor import Supervisor
from spero.core.engine import ActionOutcome, ActionStatus, TargetOutcome
from spero.core.models import Policy, ProbeSpec, TargetPolicy
from spero.store.models import Event


def _policy() -> Policy:
    return Policy(
        targets=[
            TargetPolicy(
                name="nginx",
                provider="local",
                probe=ProbeSpec(type="systemd", params={"unit": "nginx.service"}),
            )
        ]
    )


def test_status_pending_before_first_probe() -> None:
    sup = Supervisor(_policy())
    s = sup.status()
    assert s["frozen"] is False
    t = s["targets"][0]
    assert t == {
        "target": "nginx",
        "provider": "local",
        "probe": "systemd",
        "healthy": None,
        "failures": 0,
        "detail": "",
        "action": None,
    }


def test_status_serializes_outcome_and_action() -> None:
    sup = Supervisor(_policy())
    sup.latest["nginx"] = TargetOutcome(
        "nginx",
        False,
        "inactive",
        2,
        ActionOutcome("restart", ActionStatus.awaiting_approval, "needs ok"),
    )
    t = sup.status()["targets"][0]
    assert t["healthy"] is False
    assert t["failures"] == 2
    assert t["detail"] == "inactive"
    assert t["action"] == {
        "remediation": "restart",
        "status": "awaiting_approval",
        "detail": "needs ok",
    }


def test_events_in_memory() -> None:
    sup = Supervisor(Policy(targets=[]))
    assert sup.events() == []
    sup.engine._events.append(Event(node="local", target="nginx", kind="probe_fail", detail="boom"))
    assert sup.events() == [
        {"node": "local", "target": "nginx", "kind": "probe_fail", "detail": "boom"}
    ]


async def test_start_stop_with_no_targets() -> None:
    # Exercises the watch lifecycle without probing anything.
    sup = Supervisor(Policy(targets=[]))
    await sup.start()
    await sup.stop()
    assert sup.status() == {"frozen": False, "targets": []}
