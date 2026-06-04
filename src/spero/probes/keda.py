# -#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#
# __creation__ = 2026-06-04
# __author__ = "jndjama (Joy Ndjama)"
# __copyright__ = "Copyright 2026 ALTIKVA."
# __licence__ = "MIT & CC BY-NC-SA (http://www.altikva.com/licenses/LICENSE-1.0)"
# -#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#

"""KEDA ScaledObject probe -- the supervision half of the a4c serverless seam experiment.

EXPERIMENTAL (see docs/experiments/0001-keda-seam.md). This exists to test one
question from the spero<->a4c council: can spero's four-seam shape express a KEDA
(serverless autoscaling) concern? Supervising a ScaledObject's health maps cleanly
onto the Probe seam -- it's a ``kubectl get`` + read, exactly like DeploymentProbe.
The provisioning half (creating the ScaledObject) is where the seam strains; that
finding lives in the experiment write-up, not in code.
"""

from __future__ import annotations

import json
from typing import ClassVar

from spero.probes.base import Probe, ProbeResult
from spero.providers.base import Provider


class KedaScaledObjectProbe(Probe):
    """Healthy iff the KEDA ScaledObject ``name`` is ``Ready`` and not ``Paused``.

    Scaled-to-zero is healthy, mirroring DeploymentProbe: an idle serverless workload
    with ``Active=False`` but ``Ready=True`` is doing exactly what it should. The detail
    string reports the Active state so the operator can see idle vs serving.

    A *paused* ScaledObject is unhealthy. Verified against live KEDA: pausing sets
    ``Paused=True`` but leaves ``Ready=True``, so a Ready-only check would miss it and
    the engine would never fire the unpause remediation. The autoscaler being frozen
    is precisely the fault this probe pairs with UnpauseScaledObject to heal.
    """

    type: ClassVar[str] = "keda-scaledobject"

    def __init__(self, name: str) -> None:
        self.name = name

    async def check(self, provider: Provider) -> ProbeResult:
        r = await provider.run(["get", "scaledobject", self.name, "-o", "json"], timeout=30)
        if not r.ok:
            return ProbeResult(False, f"kubectl get scaledobject failed: {r.stderr.strip()}")
        try:
            conditions = json.loads(r.stdout).get("status", {}).get("conditions", [])
        except json.JSONDecodeError as exc:
            return ProbeResult(False, f"could not parse kubectl json: {exc}")
        ready = _condition(conditions, "Ready")
        if ready != "True":
            return ProbeResult(False, f"{self.name}: ScaledObject not Ready (Ready={ready})")
        if _condition(conditions, "Paused") == "True":
            return ProbeResult(False, f"{self.name}: autoscaling paused")
        active = _condition(conditions, "Active")
        scale_state = "active" if active == "True" else "scaled-to-zero (idle)"
        return ProbeResult(True, f"{self.name}: Ready, {scale_state}")


def _condition(conditions: object, kind: str) -> str:
    """Return the ``status`` ("True"/"False"/"Unknown") of condition ``kind``, or "" if absent."""
    if not isinstance(conditions, list):
        return ""
    for c in conditions:
        if isinstance(c, dict) and c.get("type") == kind:
            status = c.get("status")
            return status if isinstance(status, str) else ""
    return ""
