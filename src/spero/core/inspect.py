# -#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#
# __creation__ = 2026-06-06
# __author__ = "jndjama (Joy Ndjama)"
# __copyright__ = "Copyright 2026 ALTIKVA."
# __licence__ = "MIT & CC BY-NC-SA (https://www.altikva.com/licenses/LICENSE-1.0)"
# -#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#
# Description: Fetch the YAML and recent logs of the object a target supervises (k9s-style).

"""Inspect a target's underlying object as YAML, and tail its pod logs.

A target's probe declares what it watches via ``Probe.object_ref()`` (the object to
show as YAML) and ``Probe.pod_ref()`` (the pods to read logs from). Both run
``kubectl`` through the target's provider so `spero top` can show the live object or
its logs on demand. Host / data-infra targets have no single k8s object and raise
LookupError; CRD targets without addressable pods raise it for logs.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator

from spero.core.models import TargetPolicy


async def object_yaml(target: TargetPolicy) -> str:
    """Return the target's object as YAML. Raises LookupError (no object) / RuntimeError."""
    from spero.probes import build_probe
    from spero.providers.host import make_provider

    ref = build_probe(target.probe).object_ref()
    if ref is None:
        raise LookupError(f"{target.name}: probe {target.probe.type!r} has no inspectable object")
    provider = make_provider(target.provider)
    r = await provider.run(["get", *ref, "-o", "yaml"], timeout=30)
    if not r.ok:
        raise RuntimeError(r.stderr.strip() or "kubectl get failed")
    return r.stdout


async def object_logs(target: TargetPolicy, *, tail: int = 200) -> str:
    """Return the last ``tail`` log lines of the target's pod(s).

    Snapshot, not a follow: a single ``kubectl logs --tail`` over the probe's
    ``pod_ref()``, prefixed per pod/container so multi-pod selectors stay readable.
    Raises LookupError when the target has no pods (host / CRD probes) and
    RuntimeError when kubectl fails (e.g. no pod currently matches the selector).
    """
    from spero.probes import build_probe
    from spero.providers.host import make_provider

    ref = build_probe(target.probe).pod_ref()
    if ref is None:
        raise LookupError(f"{target.name}: probe {target.probe.type!r} has no streamable logs")
    provider = make_provider(target.provider)
    r = await provider.run(
        ["logs", *ref, "--tail", str(tail), "--all-containers=true", "--prefix=true"],
        timeout=30,
    )
    if not r.ok:
        raise RuntimeError(r.stderr.strip() or "kubectl logs failed")
    return r.stdout or "# (no log output)"


def _stream_argv(target: TargetPolicy, *, tail: int = 200) -> list[str]:
    """Build the ``kubectl logs -f`` argv for a target's pods (k8s-only).

    Raises LookupError when the target is not a kubernetes workload with pods, so
    the caller can map it to an HTTP status before any streaming starts.
    """
    from spero.probes import build_probe
    from spero.providers.host import make_provider
    from spero.providers.kubernetes import KubernetesProvider

    provider = make_provider(target.provider)
    if not isinstance(provider, KubernetesProvider):
        raise LookupError(f"{target.name}: log streaming is only available for kubernetes targets")
    ref = build_probe(target.probe).pod_ref()
    if ref is None:
        raise LookupError(f"{target.name}: probe {target.probe.type!r} has no streamable logs")
    return [
        *provider.prefix(),
        "logs",
        *ref,
        "-f",
        "--tail",
        str(tail),
        "--all-containers=true",
        "--prefix=true",
    ]


async def stream_logs(target: TargetPolicy, *, tail: int = 200) -> AsyncIterator[str]:
    """Yield log lines from ``kubectl logs -f`` for a target's pods until cancelled.

    A live follow (unlike the one-shot ``object_logs`` snapshot). The kubectl child
    is killed and reaped when the consumer stops iterating or is cancelled.
    """
    argv = _stream_argv(target, tail=tail)
    proc = await asyncio.create_subprocess_exec(
        *argv, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT
    )
    assert proc.stdout is not None
    try:
        while True:
            line = await proc.stdout.readline()
            if not line:  # process ended (pod gone, kubectl exited)
                break
            yield line.decode(errors="replace").rstrip("\n")
    finally:
        if proc.returncode is None:
            proc.kill()
            await proc.wait()
