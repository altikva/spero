# -#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#
# __creation__ = 2026-06-03
# __author__ = "jndjama (Joy Ndjama)"
# __copyright__ = "Copyright 2026 ALTIKVA."
# __licence__ = "MIT & CC BY-NC-SA (http://www.altikva.com/licenses/LICENSE-1.0)"
# -#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#
# Description: Tests for host probes, driven by a scripted provider.

"""Tests for host probes, driven by a scripted provider."""

from __future__ import annotations

from _fakes import ScriptedProvider, fixed
from spero.probes import build_probe
from spero.probes.host import DiskProbe, PortProbe, ProcessProbe, SystemdProbe

SS_OUTPUT = (
    "LISTEN 0      4096   0.0.0.0:8080   0.0.0.0:*\n"
    "LISTEN 0      128       [::]:22         [::]:*\n"
)
DF_OUTPUT = (
    "Filesystem 1024-blocks  Used Available Capacity Mounted on\n"
    "/dev/sda1      1000000 500000    500000      50% /data\n"
)


async def test_process_probe_healthy() -> None:
    probe = ProcessProbe(name="redis-server")
    r = await probe.check(ScriptedProvider(fixed(0, "111\n222\n")))
    assert r.healthy
    assert "2 process" in r.detail


async def test_process_probe_unhealthy() -> None:
    r = await ProcessProbe(name="redis").check(ScriptedProvider(fixed(1)))
    assert not r.healthy


async def test_process_probe_with_user_builds_command() -> None:
    provider = ScriptedProvider(fixed(0, "1\n"))
    await ProcessProbe(name="java", user="hdfs").check(provider)
    assert provider.commands == [["pgrep", "-u", "hdfs", "-f", "java"]]


async def test_systemd_probe() -> None:
    assert (await SystemdProbe("nginx.service").check(ScriptedProvider(fixed(0, "active")))).healthy
    assert not (
        await SystemdProbe("nginx.service").check(ScriptedProvider(fixed(3, "inactive")))
    ).healthy


async def test_port_probe() -> None:
    assert (await PortProbe(port=8080).check(ScriptedProvider(fixed(0, SS_OUTPUT)))).healthy
    assert not (await PortProbe(port=9999).check(ScriptedProvider(fixed(0, SS_OUTPUT)))).healthy


async def test_disk_probe_under_and_over_threshold() -> None:
    assert (await DiskProbe("/data", 90).check(ScriptedProvider(fixed(0, DF_OUTPUT)))).healthy
    assert not (await DiskProbe("/data", 40).check(ScriptedProvider(fixed(0, DF_OUTPUT)))).healthy


async def test_build_probe_from_spec() -> None:
    from spero.core.models import ProbeSpec

    probe = build_probe(ProbeSpec(type="disk", params={"path": "/data", "threshold_pct": 80}))
    assert isinstance(probe, DiskProbe)
    assert probe.threshold_pct == 80


def test_build_probe_unknown() -> None:
    import pytest

    from spero.core.models import ProbeSpec

    with pytest.raises(ValueError, match="unknown probe"):
        build_probe(ProbeSpec(type="nope"))
