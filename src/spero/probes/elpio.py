# -#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#
# __creation__ = 2026-06-05
# __author__ = "jndjama (Joy Ndjama)"
# __copyright__ = "Copyright 2026 ALTIKVA."
# __licence__ = "MIT & CC BY-NC-SA (https://www.altikva.com/licenses/LICENSE-1.0)"
# -#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#
# Description: Elpio CRD probes -- supervise elpio's serverless objects (Service,
#              Function, Task) by reading their Knative/KEDA-style Ready condition.

"""Elpio CRD probes: are elpio's serverless objects (Service, Function, Task) Ready?

EXPERIMENTAL (see docs/experiments/0001-keda-seam.md). This is the day-2 half of
council option (c): spero supervises elpio's own custom resources, while elpio's
operator owns provisioning them. The three RFC 0001 objects (renamed from A4C*)
all reconcile down to Knative / KEDA primitives and carry status conditions, so
supervising any of them is the same shape as `DeploymentProbe`: a `kubectl get`
plus a read of the `Ready` condition.

- `ElpioService` (A4CService): a Cloud Run-like service -> Knative `Service`.
- `ElpioFunction` (A4CFunction): source -> Tekton build -> produces an `ElpioService`.
- `ElpioTask` (A4CTask): a durable queue worker, KEDA-backed (carries `Active`).

Provisioning the resources stays elpio's job, not spero's.
"""

from __future__ import annotations

import json
from typing import ClassVar

from spero.probes.base import Probe, ProbeResult
from spero.providers.base import Provider


class ElpioServiceProbe(Probe):
    """Healthy iff the ElpioService ``name`` reports ``Ready=True``.

    Scaled-to-zero is healthy: a Knative-backed service idles at zero replicas but
    stays Ready, exactly like DeploymentProbe treats a deliberate 0-replica target.
    When not Ready, the detail surfaces the first failing sub-condition (e.g.
    ``ConfigurationsReady`` / ``RoutesReady``) and its reason, so the operator sees
    why without a second kubectl call.
    """

    type: ClassVar[str] = "elpio-service"

    def __init__(self, name: str) -> None:
        self.name = name

    async def check(self, provider: Provider) -> ProbeResult:
        r = await provider.run(["get", "elpioservice", self.name, "-o", "json"], timeout=30)
        if not r.ok:
            return ProbeResult(False, f"kubectl get elpioservice failed: {r.stderr.strip()}")
        try:
            status = json.loads(r.stdout).get("status", {})
        except json.JSONDecodeError as exc:
            return ProbeResult(False, f"could not parse kubectl json: {exc}")

        conditions = status.get("conditions", [])
        ready = _find(conditions, "Ready")
        if ready.get("status") != "True":
            return ProbeResult(False, f"{self.name}: not Ready{_why(conditions)}")

        revision = status.get("latestReadyRevisionName")
        rev = f", revision {revision}" if revision else ""
        return ProbeResult(True, f"{self.name}: Ready{rev}")


class ElpioFunctionProbe(Probe):
    """Healthy iff the ElpioFunction ``name`` reports ``Ready=True``.

    An ElpioFunction (RFC 0001's renamed A4CFunction) builds source into a container
    via Tekton, then produces an ElpioService. Not Ready usually means a failed build
    or a not-yet-Ready produced service; the detail names the failing sub-condition
    (e.g. ``BuildReady``) and its reason so the operator sees which half broke.
    """

    type: ClassVar[str] = "elpio-function"

    def __init__(self, name: str) -> None:
        self.name = name

    async def check(self, provider: Provider) -> ProbeResult:
        r = await provider.run(["get", "elpiofunction", self.name, "-o", "json"], timeout=30)
        if not r.ok:
            return ProbeResult(False, f"kubectl get elpiofunction failed: {r.stderr.strip()}")
        try:
            status = json.loads(r.stdout).get("status", {})
        except json.JSONDecodeError as exc:
            return ProbeResult(False, f"could not parse kubectl json: {exc}")

        conditions = status.get("conditions", [])
        if _find(conditions, "Ready").get("status") != "True":
            return ProbeResult(False, f"{self.name}: not Ready{_why(conditions)}")
        service = status.get("serviceName")
        svc = f", serves {service}" if service else ""
        return ProbeResult(True, f"{self.name}: Ready{svc}")


class ElpioTaskProbe(Probe):
    """Healthy iff the ElpioTask ``name`` reports ``Ready=True``.

    An ElpioTask (RFC 0001's renamed A4CTask) is a durable queue worker, KEDA-backed,
    so it carries an ``Active`` condition: Active=True means it is draining the queue,
    Active=False means idle (scaled to zero); both are healthy when Ready. The detail
    reports the processing state and the queue backlog when the status exposes it.
    """

    type: ClassVar[str] = "elpio-task"

    def __init__(self, name: str) -> None:
        self.name = name

    async def check(self, provider: Provider) -> ProbeResult:
        r = await provider.run(["get", "elpiotask", self.name, "-o", "json"], timeout=30)
        if not r.ok:
            return ProbeResult(False, f"kubectl get elpiotask failed: {r.stderr.strip()}")
        try:
            status = json.loads(r.stdout).get("status", {})
        except json.JSONDecodeError as exc:
            return ProbeResult(False, f"could not parse kubectl json: {exc}")

        conditions = status.get("conditions", [])
        if _find(conditions, "Ready").get("status") != "True":
            return ProbeResult(False, f"{self.name}: not Ready{_why(conditions)}")
        active = _find(conditions, "Active").get("status") == "True"
        state = "processing" if active else "idle (scaled to zero)"
        backlog = status.get("queueLength")
        depth = f", {backlog} queued" if backlog is not None else ""
        return ProbeResult(True, f"{self.name}: Ready, {state}{depth}")


def _find(conditions: object, kind: str) -> dict[str, object]:
    """Return condition ``kind`` as a dict (``{}`` if absent or malformed)."""
    if isinstance(conditions, list):
        for c in conditions:
            if isinstance(c, dict) and c.get("type") == kind:
                return c
    return {}


def _why(conditions: object) -> str:
    """Summarize the first non-True condition as ' (Type: reason)', or '' if none."""
    if not isinstance(conditions, list):
        return ""
    for c in conditions:
        if isinstance(c, dict) and c.get("type") != "Ready" and c.get("status") != "True":
            reason = c.get("reason") or c.get("message") or "?"
            return f" ({c.get('type')}: {reason})"
    return ""
