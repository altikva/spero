# -#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#
# __creation__ = 2026-06-05
# __author__ = "jndjama (Joy Ndjama)"
# __copyright__ = "Copyright 2026 ALTIKVA."
# __licence__ = "MIT & CC BY-NC-SA (https://www.altikva.com/licenses/LICENSE-1.0)"
# -#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#
# Description: ElpioService probe -- supervise an elpio serverless service (the
#              renamed A4CService CRD) by reading its Knative-style Ready condition.

"""ElpioService probe: is an elpio serverless service Ready?

EXPERIMENTAL (see docs/experiments/0001-keda-seam.md). This is the day-2 half of
council option (c): spero supervises elpio's own `ElpioService` custom resource,
while elpio's operator owns provisioning it. `ElpioService` (RFC 0001's renamed
A4CService) reconciles to a Knative `Service` or a KEDA-scaled `Deployment`, so it
carries Knative-style status conditions. Supervising it is the same shape as
`DeploymentProbe`/`KedaScaledObjectProbe`: a `kubectl get` plus a read of the
`Ready` condition. Provisioning the resource stays elpio's job, not spero's.
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
