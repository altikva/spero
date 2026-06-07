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
from spero.core.shell import exec_argv


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
