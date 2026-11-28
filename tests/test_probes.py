# -#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#
# __creation__ = 2026-06-03
# __author__ = "jndjama (Joy Ndjama)"
# __copyright__ = "Copyright 2026 ALTIKVA."
# __licence__ = "Apache-2.0 (https://www.apache.org/licenses/LICENSE-2.0)"
# -#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#
# Description: Tests for host probes, driven by a scripted provider.

"""Tests for host probes, driven by a scripted provider."""

from __future__ import annotations

from collections.abc import Sequence

import pytest

from _fakes import ScriptedProvider, fixed
from spero.probes import build_probe
from spero.probes.host import (
    DiskProbe,
    PortProbe,
    ProcessProbe,
    SystemdProbe,
    _listening_on_netstat,
)
from spero.providers.command import NOT_FOUND_RC, CommandResult

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


NETSTAT_DARWIN = (
    "Active Internet connections (including servers)\n"
    "Proto Recv-Q Send-Q  Local Address          Foreign Address        (state)\n"
    "tcp4       0      0  127.0.0.1.8080         *.*                    LISTEN\n"
    "tcp46      0      0  *.5000                 *.*                    LISTEN\n"
    "tcp6       0      0  ::1.631                *.*                    LISTEN\n"
    "tcp4       0      0  192.168.1.10.52344     17.57.146.20.9090      ESTABLISHED\n"
    "udp4       0      0  *.7070                 *.*\n"
)
NETSTAT_LINUX = (
    "Active Internet connections (servers and established)\n"
    "Proto Recv-Q Send-Q Local Address           Foreign Address         State\n"
    "tcp        0      0 0.0.0.0:22              0.0.0.0:*               LISTEN\n"
    "tcp        0      0 127.0.0.1:6379          0.0.0.0:*               LISTEN\n"
    "tcp        0      0 10.0.0.5:22             10.0.0.9:51000          ESTABLISHED\n"
    "tcp6       0      0 :::80                   :::*                    LISTEN\n"
)


def _without_ss(netstat_output: str) -> ScriptedProvider:
    def handler(command: str | Sequence[str]) -> CommandResult:
        if command[0] == "ss":
            return CommandResult(NOT_FOUND_RC, "", "ss: not found", "ss -ltnH")
        return CommandResult(0, netstat_output, "", "netstat -an")

    return ScriptedProvider(handler)


@pytest.mark.parametrize(
    ("port", "host", "healthy"),
    [
        (8080, None, True),
        (8080, "127.0.0.1", True),
        (8080, "10.0.0.1", False),
        (5000, "10.0.0.1", True),  # bound to every address
        (631, "::1", True),
        (9090, None, False),  # remote port of an established connection
        (52344, None, False),  # local port, but not listening
        (7070, None, False),  # udp, not tcp
        (80, None, False),
    ],
)
def test_netstat_darwin_parsing(port: int, host: str | None, healthy: bool) -> None:
    assert _listening_on_netstat(NETSTAT_DARWIN, port, host) is healthy


@pytest.mark.parametrize(
    ("port", "host", "healthy"),
    [
        (22, None, True),
        (22, "10.0.0.5", True),
        (6379, "127.0.0.1", True),
        (6379, "10.0.0.5", False),
        (80, None, True),
        (51000, None, False),
        (8080, None, False),
    ],
)
def test_netstat_linux_parsing(port: int, host: str | None, healthy: bool) -> None:
    assert _listening_on_netstat(NETSTAT_LINUX, port, host) is healthy


async def test_port_probe_falls_back_to_netstat_and_remembers_it() -> None:
    provider = _without_ss(NETSTAT_DARWIN)
    probe = PortProbe(port=8080)
    assert (await probe.check(provider)).healthy
    assert (await probe.check(provider)).healthy
    assert provider.commands == [["ss", "-ltnH"], ["netstat", "-an"], ["netstat", "-an"]]


async def test_port_probe_nothing_listening_via_netstat() -> None:
    r = await PortProbe(port=9999).check(_without_ss(NETSTAT_DARWIN))
    assert not r.healthy
    assert r.detail == "nothing listening on port 9999"


async def test_port_probe_reports_missing_tools_distinctly() -> None:
    provider = ScriptedProvider(fixed(NOT_FOUND_RC, "", "not found"))
    r = await PortProbe(port=8080).check(provider)
    assert not r.healthy
    assert r.detail.startswith("cannot query listening sockets")
    assert "ss or netstat" in r.detail
    assert provider.commands == [["ss", "-ltnH"], ["netstat", "-an"]]


async def test_port_probe_tool_error_is_not_nothing_listening() -> None:
    r = await PortProbe(port=8080).check(ScriptedProvider(fixed(1, "", "permission denied")))
    assert not r.healthy
    assert "could not query listening sockets with ss" in r.detail


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
