# -#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#
# __creation__ = 2026-06-03
# __author__ = "jndjama (Joy Ndjama)"
# __copyright__ = "Copyright 2026 ALTIKVA."
# __licence__ = "MIT & CC BY-NC-SA (http://www.altikva.com/licenses/LICENSE-1.0)"
# -#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#

"""Kubernetes provider: run kubectl against a cluster/namespace.

Keeping k8s on the same ``Provider.run`` seam (rather than a parallel client API)
means the engine, probes, and remediations are provider-agnostic: a k8s target is
just "a place where commands are kubectl subcommands." The provider bakes in the
``--context`` and ``-n <namespace>`` flags; probes/remediations supply the rest.

Provider policy strings: ``k8s`` | ``k8s:<context>`` | ``k8s:<context>/<namespace>``
| ``k8s:/<namespace>``.
"""

from __future__ import annotations

import shlex
from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from spero.providers.base import Provider
from spero.providers.command import CommandResult, run_local_async


class KubernetesProvider(Provider):
    name = "k8s"

    def __init__(
        self,
        *,
        context: str | None = None,
        namespace: str | None = None,
        kubectl_bin: str = "kubectl",
    ) -> None:
        self.context = context
        self.namespace = namespace
        self.kubectl_bin = kubectl_bin

    def prefix(self) -> list[str]:
        argv = [self.kubectl_bin]
        if self.context:
            argv += ["--context", self.context]
        if self.namespace:
            argv += ["-n", self.namespace]
        return argv

    async def run(
        self,
        command: str | Sequence[str],
        *,
        timeout: float | None = None,
        retries: int = 0,
        cwd: str | None = None,
        env: Mapping[str, str] | None = None,
    ) -> CommandResult:
        if cwd is not None or env is not None:
            raise NotImplementedError("KubernetesProvider does not support cwd/env")
        sub = shlex.split(command) if isinstance(command, str) else list(command)
        return await run_local_async([*self.prefix(), *sub], timeout=timeout, retries=retries)


@dataclass(frozen=True, slots=True)
class KubeTarget:
    context: str | None = None
    namespace: str | None = None


def parse_kube_dest(rest: str) -> KubeTarget:
    """Parse ``[context][/namespace]`` (the part after ``k8s:``). Raises on garbage."""
    context, _, namespace = rest.partition("/")
    if "/" in namespace:
        raise ValueError(f"too many '/' in k8s spec: {rest!r} (expected [context][/namespace])")
    return KubeTarget(context=context or None, namespace=namespace or None)
