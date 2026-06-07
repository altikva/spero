# -#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#
# __creation__ = 2026-06-07
# __author__ = "jndjama (Joy Ndjama)"
# __copyright__ = "Copyright 2026 ALTIKVA."
# __licence__ = "MIT & CC BY-NC-SA (https://www.altikva.com/licenses/LICENSE-1.0)"
# -#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#
# Description: Build a local `kubectl exec -it` argv into a target's pod (local
#              convenience for `spero top`; uses your kubeconfig, not spero's RBAC).

"""A local, interactive `kubectl exec` convenience for `spero top`.

Shelling into a pod is a Kubernetes primitive (the ``pods/exec`` subresource), not a
spero capability: this builds the argv for *your* local ``kubectl exec -it`` and the
TUI shells out to it, so it runs with your kubeconfig and credentials, not the
in-cluster agent's least-privilege RBAC. It is therefore offered only in local
``spero top`` (never over ``--remote`` or dial-home, which would need a TTY tunnel).

It is k8s-only: the target's provider must be a KubernetesProvider, and its probe
must expose pods via ``pod_ref()``. A label selector is resolved to one running pod;
a ``<kind>/<name>`` workload (e.g. ``deployment/x``) is passed to exec as-is.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from spero.core.models import TargetPolicy

if TYPE_CHECKING:
    from spero.providers.kubernetes import KubernetesProvider


async def exec_argv(target: TargetPolicy, *, shell: str = "/bin/sh") -> list[str]:
    """Build a ``kubectl exec -it <pod> -- <shell>`` argv for ``target``'s pod.

    Raises LookupError when the target is not an exec'able kubernetes pod (wrong
    provider, no ``pod_ref``, or no running pod matches the selector).
    """
    from spero.probes import build_probe
    from spero.providers.host import make_provider
    from spero.providers.kubernetes import KubernetesProvider

    provider = make_provider(target.provider)
    if not isinstance(provider, KubernetesProvider):
        raise LookupError(f"{target.name}: exec is only available for kubernetes targets")
    ref = build_probe(target.probe).pod_ref()
    if ref is None:
        raise LookupError(f"{target.name}: probe {target.probe.type!r} has no pod to exec into")
    pod = await _resolve_pod(provider, ref)
    return [*provider.prefix(), "exec", "-it", pod, "--", shell]


async def _resolve_pod(provider: KubernetesProvider, ref: list[str]) -> str:
    """A ``<kind>/<name>`` ref is exec'able directly; a ``-l`` selector resolves to
    the first running matching pod."""
    if ref and ref[0] != "-l":
        return ref[0]
    r = await provider.run(
        [
            "get",
            "pods",
            *ref,
            "--field-selector=status.phase=Running",
            "-o",
            "jsonpath={.items[0].metadata.name}",
        ],
        timeout=15,
    )
    name = r.stdout.strip()
    if not name:
        raise LookupError(f"no running pod matches {' '.join(ref)}")
    return f"pod/{name}"
