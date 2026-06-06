# -#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#
# __creation__ = 2026-06-05
# __author__ = "jndjama (Joy Ndjama)"
# __copyright__ = "Copyright 2026 ALTIKVA."
# __licence__ = "MIT & CC BY-NC-SA (https://www.altikva.com/licenses/LICENSE-1.0)"
# -#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#
# Description: Elpio CRD probes -- supervise elpio's serverless objects (Service,
#              Function, Task) by reading their elpio.io status.ready + Ready condition.

"""Elpio CRD probes: are elpio's serverless objects (Service, Function, Task) Ready?

EXPERIMENTAL. This is the day-2 half of council option (c): spero supervises elpio's
own custom resources (group ``elpio.io``), while elpio's operator owns provisioning
them. Each CR carries a canonical ``status.ready`` boolean plus a Kubernetes-style
``Ready`` condition (status ``"True"``/``"False"`` with a reason); supervising any of
them is the same shape as ``DeploymentProbe``: a ``kubectl get`` and a read of status.
Verified against elpio v0.1.0's CRDs and operator.

- ``ElpioService``: a Cloud Run-like service. status: ready, engine, url.
- ``ElpioFunction``: source -> build -> produces an ElpioService. status: ready,
  phase (Building/Ready/BuildFailed), serviceName.
- ``ElpioTask``: a durable queue worker (KEDA-backed dispatcher). status: ready.

Provisioning the resources stays elpio's job, not spero's.
"""

from __future__ import annotations

import json
from typing import ClassVar

from spero.probes.base import Probe, ProbeResult
from spero.providers.base import Provider


class ElpioServiceProbe(Probe):
    """Healthy iff the ElpioService ``name`` reports ready. Detail names the engine.

    Scale-to-zero is healthy: an idle elpio service stays ready, like DeploymentProbe
    treats a deliberate 0-replica target. When not ready, the detail carries the
    operator's reason so no second kubectl call is needed.
    """

    type: ClassVar[str] = "elpio-service"

    def __init__(self, name: str) -> None:
        self.name = name

    async def check(self, provider: Provider) -> ProbeResult:
        r = await provider.run(
            ["get", "elpioservice.elpio.io", self.name, "-o", "json"], timeout=30
        )
        if not r.ok:
            return ProbeResult(False, f"kubectl get elpioservice failed: {r.stderr.strip()}")
        try:
            status = json.loads(r.stdout).get("status", {})
        except json.JSONDecodeError as exc:
            return ProbeResult(False, f"could not parse kubectl json: {exc}")

        ready, reason = _ready(status)
        if not ready:
            return ProbeResult(False, f"{self.name}: not ready{_paren(reason)}")
        engine = status.get("engine")
        return ProbeResult(True, f"{self.name}: ready{_on(engine)}")


class ElpioFunctionProbe(Probe):
    """Healthy iff the ElpioFunction ``name`` reports ready (build succeeded).

    An ElpioFunction builds source into a container, then produces an ElpioService.
    Not ready means the build is in progress or failed; the operator's reason/phase
    (e.g. ``BuildFailed``) is surfaced. When ready, the produced service is named.
    """

    type: ClassVar[str] = "elpio-function"

    def __init__(self, name: str) -> None:
        self.name = name

    async def check(self, provider: Provider) -> ProbeResult:
        r = await provider.run(
            ["get", "elpiofunction.elpio.io", self.name, "-o", "json"], timeout=30
        )
        if not r.ok:
            return ProbeResult(False, f"kubectl get elpiofunction failed: {r.stderr.strip()}")
        try:
            status = json.loads(r.stdout).get("status", {})
        except json.JSONDecodeError as exc:
            return ProbeResult(False, f"could not parse kubectl json: {exc}")

        ready, reason = _ready(status)
        if not ready:
            return ProbeResult(False, f"{self.name}: not ready{_paren(reason)}")
        service = status.get("serviceName")
        return ProbeResult(True, f"{self.name}: ready{f', serves {service}' if service else ''}")


class ElpioTaskProbe(Probe):
    """Healthy iff the ElpioTask ``name`` reports ready.

    An ElpioTask is a durable queue worker (a dispatcher scaled by KEDA off queue
    depth). Idle (scaled to zero) is healthy when ready. The queue backlog is shown
    when the status exposes it.
    """

    type: ClassVar[str] = "elpio-task"

    def __init__(self, name: str) -> None:
        self.name = name

    async def check(self, provider: Provider) -> ProbeResult:
        r = await provider.run(["get", "elpiotask.elpio.io", self.name, "-o", "json"], timeout=30)
        if not r.ok:
            return ProbeResult(False, f"kubectl get elpiotask failed: {r.stderr.strip()}")
        try:
            status = json.loads(r.stdout).get("status", {})
        except json.JSONDecodeError as exc:
            return ProbeResult(False, f"could not parse kubectl json: {exc}")

        ready, reason = _ready(status)
        if not ready:
            return ProbeResult(False, f"{self.name}: not ready{_paren(reason)}")
        backlog = status.get("queueLength")
        depth = f", {backlog} queued" if backlog is not None else ""
        return ProbeResult(True, f"{self.name}: ready{depth}")


def _ready(status: dict) -> tuple[bool, str]:
    """Elpio readiness. ``status.ready`` (bool) is canonical; the ``Ready`` condition
    is the fallback. Returns (ready, reason) where reason explains a not-ready state."""
    cond = _find(status.get("conditions", []), "Ready")
    ready = status.get("ready") is True or cond.get("status") == "True"
    reason = str(cond.get("reason") or cond.get("message") or status.get("phase") or "")
    return ready, reason


def _find(conditions: object, kind: str) -> dict[str, object]:
    """Return condition ``kind`` as a dict (``{}`` if absent or malformed)."""
    if isinstance(conditions, list):
        for c in conditions:
            if isinstance(c, dict) and c.get("type") == kind:
                return c
    return {}


def _paren(reason: str) -> str:
    return f" ({reason})" if reason else ""


def _on(engine: object) -> str:
    return f" on {engine}" if engine else ""
