# -#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#
# __creation__ = 2026-06-07
# __author__ = "jndjama (Joy Ndjama)"
# __copyright__ = "Copyright 2026 ALTIKVA."
# __licence__ = "MIT & CC BY-NC-SA (https://www.altikva.com/licenses/LICENSE-1.0)"
# -#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#
# Description: Build a local argv to open an interactive session into a target
#              (kubectl exec / ssh / local shell) for `spero top`; uses YOUR tools
#              and credentials, not spero's RBAC or any brokered identity.

"""A local, interactive connect convenience for `spero top` (the `s` key).

Opening a session into a target is done with the operator's own tools: this builds
the argv for *your* local ``kubectl exec -it`` (pods), ``ssh -t`` (hosts), or a local
shell, and the TUI shells out to it. It runs with your kubeconfig / ssh config and
keys, not the in-cluster agent's least-privilege RBAC, so access stays bounded by
what you can already reach. It is therefore offered only in local ``spero top``,
never over ``--remote`` or dial-home (a brokered session is the Tier B bastion, a
separate design, not this convenience).

For a kubernetes target the probe must expose pods via ``pod_ref()``: a label
selector is resolved to one running pod; a ``<kind>/<name>`` workload (e.g.
``deployment/x``) is passed to exec as-is.
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


async def connect_argv(target: TargetPolicy, *, shell: str = "/bin/sh") -> list[str]:
    """Build the argv for an interactive session into ``target`` (the `spero top` `s`).

    Dispatches on the provider: ``kubectl exec -it`` for a kubernetes pod, ``ssh -t``
    for an ssh host, or a local shell for a ``local`` target. Like ``exec_argv`` it
    uses the operator's own tools and credentials (your kubeconfig, your ssh config
    and keys), never spero's RBAC or any brokered identity, so access stays bounded
    by what you can already reach. Raises LookupError when a kubernetes target has no
    running pod to enter.
    """
    import os

    from spero.providers.host import SSHTarget, parse_provider_spec

    kind, detail = parse_provider_spec(target.provider)
    if kind == "k8s":
        return await exec_argv(target, shell=shell)
    if kind == "ssh":
        assert isinstance(detail, SSHTarget)
        argv = ["ssh", "-t"]  # force a TTY for an interactive session
        if detail.port is not None:
            argv += ["-p", str(detail.port)]
        argv.append(f"{detail.user}@{detail.host}" if detail.user else detail.host)
        return argv
    return [os.environ.get("SHELL", "/bin/sh")]  # local: a shell on this host


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
