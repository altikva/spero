# -#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#
# __creation__ = 2026-06-05
# __author__ = "jndjama (Joy Ndjama)"
# __copyright__ = "Copyright 2026 ALTIKVA."
# __licence__ = "MIT & CC BY-NC-SA (https://www.altikva.com/licenses/LICENSE-1.0)"
# -#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#
# Description: Knative Service probe -- supervise a serving.knative.dev Service by
#              reading its Ready condition (ConfigurationsReady / RoutesReady).

"""Knative Service probe: is a serving.knative.dev ``Service`` Ready?

EXPERIMENTAL. A Knative ``Service`` (the ``ksvc`` short name) is the top-level
serving primitive: it owns a Configuration and a Route, which surface as the
``ConfigurationsReady`` and ``RoutesReady`` sub-conditions and roll up into a
single ``Ready`` condition. Supervising one is the same shape as DeploymentProbe:
a ``kubectl get`` plus a read of the ``Ready`` condition.

Scaled-to-zero is healthy: a Knative service idles at zero replicas but stays
Ready. When not Ready, the detail surfaces the first failing sub-condition
(e.g. ``ConfigurationsReady`` / ``RoutesReady``) and its reason, so the operator
sees why without a second kubectl call. Provisioning the Service stays with
whoever owns its desired state, not spero.
"""

from __future__ import annotations

import json
from typing import ClassVar

from spero.probes.base import Probe, ProbeResult
from spero.providers.base import Provider


class KnativeServiceProbe(Probe):
    """Healthy iff the Knative ``Service`` ``name`` reports ``Ready=True``.

    Scaled-to-zero is healthy: a Knative-backed service idles at zero replicas but
    stays Ready, exactly like DeploymentProbe treats a deliberate 0-replica target.
    When not Ready, the detail surfaces the first failing sub-condition (e.g.
    ``ConfigurationsReady`` / ``RoutesReady``) and its reason, so the operator sees
    why without a second kubectl call. On healthy, the detail names the
    ``latestReadyRevisionName`` when the status exposes it.
    """

    type: ClassVar[str] = "knative-service"

    def __init__(self, name: str) -> None:
        self.name = name

    def object_ref(self) -> list[str]:
        return ["ksvc", self.name]

    def pod_ref(self) -> list[str]:
        # Knative labels each serving pod with its service name; the revision pods
        # are what carry the user container's logs.
        return ["-l", f"serving.knative.dev/service={self.name}"]

    async def check(self, provider: Provider) -> ProbeResult:
        r = await provider.run(["get", "ksvc", self.name, "-o", "json"], timeout=30)
        if not r.ok:
            return ProbeResult(False, f"kubectl get ksvc failed: {r.stderr.strip()}")
        try:
            status = json.loads(r.stdout).get("status", {})
        except json.JSONDecodeError as exc:
            return ProbeResult(False, f"could not parse kubectl json: {exc}")

        conditions = status.get("conditions", [])
        ready = _ksvc_find(conditions, "Ready")
        if ready.get("status") != "True":
            return ProbeResult(False, f"{self.name}: not Ready{_ksvc_why(conditions)}")

        revision = status.get("latestReadyRevisionName")
        rev = f", revision {revision}" if revision else ""
        return ProbeResult(True, f"{self.name}: Ready{rev}")


def _ksvc_find(conditions: object, kind: str) -> dict[str, object]:
    """Return condition ``kind`` as a dict (``{}`` if absent or malformed)."""
    if isinstance(conditions, list):
        for c in conditions:
            if isinstance(c, dict) and c.get("type") == kind:
                return c
    return {}


def _ksvc_why(conditions: object) -> str:
    """Summarize the first non-True condition as ' (Type: reason)', or '' if none."""
    if not isinstance(conditions, list):
        return ""
    for c in conditions:
        if isinstance(c, dict) and c.get("type") != "Ready" and c.get("status") != "True":
            reason = c.get("reason") or c.get("message") or "?"
            return f" ({c.get('type')}: {reason})"
    return ""
