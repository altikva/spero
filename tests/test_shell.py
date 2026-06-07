# -#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#
# __creation__ = 2026-06-07
# __author__ = "jndjama (Joy Ndjama)"
# __copyright__ = "Copyright 2026 ALTIKVA."
# __licence__ = "MIT & CC BY-NC-SA (https://www.altikva.com/licenses/LICENSE-1.0)"
# -#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#
# Description: Tests for the local `kubectl exec` argv builder (core.shell.exec_argv).

"""Tests for core.shell.exec_argv (the local exec convenience for `spero top`)."""

from __future__ import annotations

import pytest

from spero.core.models import ProbeSpec, TargetPolicy
from spero.core.shell import _resolve_pod, exec_argv
from spero.providers.command import CommandResult


class _FakeProvider:
    """Minimal provider double for exercising _resolve_pod without a cluster."""

    def __init__(self, stdout: str) -> None:
        self._stdout = stdout

    async def run(self, command: object, *, timeout: float | None = None) -> CommandResult:
        return CommandResult(0, self._stdout, "")


async def test_resolve_pod_direct_resource_skips_lookup() -> None:
    # A <kind>/<name> ref is exec'able as-is; no kubectl call needed.
    assert await _resolve_pod(_FakeProvider(""), ["deployment/orders"]) == "deployment/orders"


async def test_resolve_pod_selector_picks_first_running_pod() -> None:
    pod = await _resolve_pod(_FakeProvider("orders-7d9-abc"), ["-l", "app=orders"])
    assert pod == "pod/orders-7d9-abc"


async def test_resolve_pod_selector_no_match_raises() -> None:
    with pytest.raises(LookupError):
        await _resolve_pod(_FakeProvider("   "), ["-l", "app=none"])


async def test_exec_argv_for_deployment_target() -> None:
    # A deployment ref is exec'able directly, so no pod resolution (no kubectl call).
    target = TargetPolicy(
        name="orders",
        provider="k8s:/orders",
        probe=ProbeSpec(type="deployment", params={"name": "orders"}),
    )
    argv = await exec_argv(target)
    assert argv == ["kubectl", "-n", "orders", "exec", "-it", "deployment/orders", "--", "/bin/sh"]


async def test_exec_argv_honours_shell_argument() -> None:
    target = TargetPolicy(
        name="orders",
        provider="k8s",
        probe=ProbeSpec(type="deployment", params={"name": "orders"}),
    )
    argv = await exec_argv(target, shell="/bin/bash")
    assert argv == ["kubectl", "exec", "-it", "deployment/orders", "--", "/bin/bash"]


async def test_exec_argv_rejects_non_kubernetes_target() -> None:
    target = TargetPolicy(
        name="nginx",
        provider="local",
        probe=ProbeSpec(type="systemd", params={"unit": "nginx.service"}),
    )
    with pytest.raises(LookupError):
        await exec_argv(target)


async def test_exec_argv_rejects_target_without_pods() -> None:
    # A k8s target whose probe exposes no pods (a KEDA ScaledObject CRD) is not exec'able.
    target = TargetPolicy(
        name="dispatcher",
        provider="k8s",
        probe=ProbeSpec(type="keda-scaledobject", params={"name": "dispatcher"}),
    )
    with pytest.raises(LookupError):
        await exec_argv(target)
