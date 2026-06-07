# -#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#
# __creation__ = 2026-06-07
# __author__ = "jndjama (Joy Ndjama)"
# __copyright__ = "Copyright 2026 ALTIKVA."
# __licence__ = "MIT & CC BY-NC-SA (https://www.altikva.com/licenses/LICENSE-1.0)"
# -#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#
# Description: Tests for the patch-requests rightsizing remediation.

"""Tests for the `patch-requests` remediation (rightsizing) and its gating."""

from __future__ import annotations

import pytest

from spero.core.models import Autonomy, ProbeSpec, RemediationSpec, TargetPolicy
from spero.providers.command import CommandResult
from spero.remediations import build_remediation
from spero.remediations.kubernetes import PatchRequests


class _RecordingProvider:
    def __init__(self) -> None:
        self.commands: list[list[str]] = []

    async def run(self, command: list[str], *, timeout: float | None = None) -> CommandResult:
        self.commands.append(command)
        return CommandResult(0, "deployment.apps/web resource requirements updated", "")


async def test_patch_requests_sets_both_resources() -> None:
    provider = _RecordingProvider()
    rem = PatchRequests(deployment="web", cpu="200m", memory="256Mi", container="app")
    result = await rem.apply(provider)  # type: ignore[arg-type]
    assert result.success
    assert provider.commands == [
        ["set", "resources", "deployment/web", "--requests=cpu=200m,memory=256Mi", "-c", "app"]
    ]


async def test_patch_requests_cpu_only() -> None:
    provider = _RecordingProvider()
    await PatchRequests(deployment="web", cpu="500m").apply(provider)  # type: ignore[arg-type]
    assert provider.commands == [["set", "resources", "deployment/web", "--requests=cpu=500m"]]


def test_patch_requests_requires_a_resource() -> None:
    with pytest.raises(ValueError, match="at least one of cpu/memory"):
        PatchRequests(deployment="web")


def test_patch_requests_is_destructive_so_auto_is_rejected() -> None:
    assert PatchRequests.destructive is True
    # _validate_buildable runs at construction and rejects destructive + auto.
    with pytest.raises(ValueError, match="destructive"):
        TargetPolicy(
            name="web",
            provider="k8s",
            probe=ProbeSpec(type="resource-usage", params={"selector": "app=web"}),
            remediations=[
                RemediationSpec(
                    type="patch-requests",
                    params={"deployment": "web", "cpu": "200m"},
                    autonomy=Autonomy.auto,
                )
            ],
        )


def test_patch_requests_builds_from_spec_when_gated() -> None:
    rem = build_remediation(
        RemediationSpec(
            type="patch-requests",
            params={"deployment": "web", "memory": "512Mi"},
            autonomy=Autonomy.gated,
        )
    )
    assert isinstance(rem, PatchRequests)
