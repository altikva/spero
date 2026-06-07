# -#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#
# __creation__ = 2026-06-03
# __author__ = "jndjama (Joy Ndjama)"
# __copyright__ = "Copyright 2026 ALTIKVA."
# __licence__ = "MIT & CC BY-NC-SA (https://www.altikva.com/licenses/LICENSE-1.0)"
# -#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#
# Description: Kubernetes probes: pod readiness and deployment availability.

"""Kubernetes probes: pod readiness and deployment availability.

Each issues a `kubectl get ... -o json` through the provider and reads the result;
the KubernetesProvider supplies the kubectl/context/namespace prefix.
"""

from __future__ import annotations

import base64
import binascii
import json
from datetime import UTC, datetime
from typing import ClassVar

from spero.probes.base import Probe, ProbeResult
from spero.providers.base import Provider


class PodReadyProbe(Probe):
    """Healthy iff at least ``min_ready`` pods matching ``selector`` are Ready."""

    type: ClassVar[str] = "pod"

    def __init__(self, selector: str, min_ready: int = 1) -> None:
        if int(min_ready) < 1:
            raise ValueError("min_ready must be >= 1")
        self.selector = selector
        self.min_ready = int(min_ready)

    def object_ref(self) -> list[str]:
        return ["pods", "-l", self.selector]

    def pod_ref(self) -> list[str]:
        return ["-l", self.selector]

    async def check(self, provider: Provider) -> ProbeResult:
        r = await provider.run(["get", "pods", "-l", self.selector, "-o", "json"], timeout=30)
        if not r.ok:
            return ProbeResult(False, f"kubectl get pods failed: {r.stderr.strip()}")
        try:
            items = json.loads(r.stdout).get("items", [])
        except json.JSONDecodeError as exc:
            return ProbeResult(False, f"could not parse kubectl json: {exc}")
        ready = sum(1 for pod in items if _pod_ready(pod))
        healthy = ready >= self.min_ready
        return ProbeResult(healthy, f"{ready}/{self.min_ready} ready for {self.selector!r}")


class DeploymentProbe(Probe):
    """Healthy iff the deployment's available replicas meet its desired count."""

    type: ClassVar[str] = "deployment"

    def __init__(self, name: str) -> None:
        self.name = name

    def object_ref(self) -> list[str]:
        return ["deployment", self.name]

    def pod_ref(self) -> list[str]:
        return [f"deployment/{self.name}"]

    async def check(self, provider: Provider) -> ProbeResult:
        r = await provider.run(["get", "deployment", self.name, "-o", "json"], timeout=30)
        if not r.ok:
            return ProbeResult(False, f"kubectl get deployment failed: {r.stderr.strip()}")
        try:
            data = json.loads(r.stdout)
        except json.JSONDecodeError as exc:
            return ProbeResult(False, f"could not parse kubectl json: {exc}")
        desired = int(data.get("spec", {}).get("replicas", 0) or 0)
        available = int(data.get("status", {}).get("availableReplicas", 0) or 0)
        if desired == 0:  # intentionally scaled to zero: nothing wanted, nothing missing
            return ProbeResult(True, f"{self.name}: scaled to 0 (no replicas desired)")
        return ProbeResult(available >= desired, f"{self.name}: {available}/{desired} available")


class PvcProbe(Probe):
    """Healthy iff the PersistentVolumeClaim ``name`` is ``Bound``.

    This checks bind health only: a claim is healthy once it has bound to a
    PersistentVolume and the storage is provisioned. True PVC *usage* (how full
    the mounted filesystem is) needs kubelet volume stats, which kubectl does not
    expose, so disk-fill thresholds on a PVC are future work, handled by a
    metrics-backed probe rather than this one. The detail names the phase and,
    when the status exposes it, the bound capacity.
    """

    type: ClassVar[str] = "pvc"

    def __init__(self, name: str) -> None:
        self.name = name

    def object_ref(self) -> list[str]:
        return ["pvc", self.name]

    async def check(self, provider: Provider) -> ProbeResult:
        r = await provider.run(["get", "pvc", self.name, "-o", "json"], timeout=30)
        if not r.ok:
            return ProbeResult(False, f"kubectl get pvc failed: {r.stderr.strip()}")
        try:
            status = json.loads(r.stdout).get("status", {})
        except json.JSONDecodeError as exc:
            return ProbeResult(False, f"could not parse kubectl json: {exc}")

        phase = status.get("phase", "Unknown") or "Unknown"
        capacity = ""
        cap = status.get("capacity")
        if isinstance(cap, dict) and cap.get("storage"):
            capacity = f", capacity {cap['storage']}"
        return ProbeResult(phase == "Bound", f"{self.name}: {phase}{capacity}")


class CertExpiryProbe(Probe):
    """Unhealthy if the X.509 cert in a TLS ``Secret`` expires within ``days``.

    Reads ``data[key]`` (default ``tls.crt``) from the named Secret, base64-decodes
    it, and parses the leaf certificate's ``notAfter`` with the ``cryptography``
    library. Reports unhealthy when the certificate expires within ``days`` (or has
    already expired). The detail names the days remaining. ``cryptography`` is
    imported lazily so the dependency stays optional: without it the probe returns
    a clear pointer to the ``certs`` extra rather than crashing.
    """

    type: ClassVar[str] = "cert-expiry"

    def __init__(self, secret: str, days: int = 14, key: str = "tls.crt") -> None:
        if int(days) < 0:
            raise ValueError("days must be >= 0")
        self.secret = secret
        self.days = int(days)
        self.key = key

    def object_ref(self) -> list[str]:
        return ["secret", self.secret]

    async def check(self, provider: Provider) -> ProbeResult:
        try:
            from cryptography import x509
        except ImportError:
            return ProbeResult(
                False, "cert-expiry needs the 'certs' extra: pip install spero[certs]"
            )

        r = await provider.run(["get", "secret", self.secret, "-o", "json"], timeout=30)
        if not r.ok:
            return ProbeResult(False, f"kubectl get secret failed: {r.stderr.strip()}")
        try:
            data = json.loads(r.stdout).get("data", {})
        except json.JSONDecodeError as exc:
            return ProbeResult(False, f"could not parse kubectl json: {exc}")
        if not isinstance(data, dict) or self.key not in data:
            return ProbeResult(False, f"{self.secret}: no data[{self.key!r}] in secret")

        try:
            pem = base64.b64decode(data[self.key], validate=True)
        except (binascii.Error, ValueError) as exc:
            return ProbeResult(False, f"{self.secret}: could not base64-decode {self.key!r}: {exc}")
        try:
            cert = x509.load_pem_x509_certificate(pem)
        except ValueError as exc:
            return ProbeResult(False, f"{self.secret}: could not parse certificate: {exc}")

        not_after = cert.not_valid_after_utc
        remaining = (not_after - datetime.now(UTC)).days
        if remaining < 0:
            return ProbeResult(False, f"{self.secret}: certificate expired {-remaining}d ago")
        healthy = remaining >= self.days
        return ProbeResult(
            healthy, f"{self.secret}: {remaining}d until expiry (need >= {self.days})"
        )


class RestartCountProbe(Probe):
    """Unhealthy if any pod matching ``selector`` is crash-looping.

    Flags a container that is in ``CrashLoopBackOff``, was ``OOMKilled``, or has
    restarted at least ``max_restarts`` times. These are the common "the pod is up
    but unhealthy" signals that a plain readiness check can miss between restarts.
    The detail names the worst container and why.
    """

    type: ClassVar[str] = "restart-count"

    def __init__(self, selector: str, max_restarts: int = 5) -> None:
        if int(max_restarts) < 1:
            raise ValueError("max_restarts must be >= 1")
        self.selector = selector
        self.max_restarts = int(max_restarts)

    def object_ref(self) -> list[str]:
        return ["pods", "-l", self.selector]

    def pod_ref(self) -> list[str]:
        return ["-l", self.selector]

    async def check(self, provider: Provider) -> ProbeResult:
        r = await provider.run(["get", "pods", "-l", self.selector, "-o", "json"], timeout=30)
        if not r.ok:
            return ProbeResult(False, f"kubectl get pods failed: {r.stderr.strip()}")
        try:
            items = json.loads(r.stdout).get("items", [])
        except json.JSONDecodeError as exc:
            return ProbeResult(False, f"could not parse kubectl json: {exc}")
        if not items:
            return ProbeResult(True, f"no pods match {self.selector!r}")

        worst_restarts = -1
        reason = ""
        for pod in items:
            pod_name = pod.get("metadata", {}).get("name", "?")
            for cs in pod.get("status", {}).get("containerStatuses", []):
                if not isinstance(cs, dict):
                    continue
                restarts = int(cs.get("restartCount", 0) or 0)
                why = _crash_reason(cs)
                if why:  # CrashLoopBackOff / OOMKilled trumps a raw count
                    return ProbeResult(False, f"{pod_name}/{cs.get('name', '?')}: {why}")
                if restarts > worst_restarts:
                    worst_restarts = restarts
                    reason = f"{pod_name}/{cs.get('name', '?')} restarted {restarts}x"

        if worst_restarts >= self.max_restarts:
            return ProbeResult(False, f"{reason} (>= {self.max_restarts})")
        return ProbeResult(True, f"{len(items)} pod(s), worst {max(worst_restarts, 0)} restarts")


def _crash_reason(cs: dict[str, object]) -> str:
    """A crash signal for a container status: CrashLoopBackOff or OOMKilled, else ''."""
    state = cs.get("state")
    if isinstance(state, dict):
        waiting = state.get("waiting")
        if isinstance(waiting, dict) and waiting.get("reason") == "CrashLoopBackOff":
            return "CrashLoopBackOff"
    last = cs.get("lastState")
    if isinstance(last, dict):
        term = last.get("terminated")
        if isinstance(term, dict) and term.get("reason") == "OOMKilled":
            return "OOMKilled"
    return ""


def _pod_ready(pod: dict[str, object]) -> bool:
    status = pod.get("status", {})
    if not isinstance(status, dict) or status.get("phase") != "Running":
        return False
    conditions = status.get("conditions", [])
    if not isinstance(conditions, list):
        return False
    return any(
        isinstance(c, dict) and c.get("type") == "Ready" and c.get("status") == "True"
        for c in conditions
    )
