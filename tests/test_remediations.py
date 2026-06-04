# -#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#
# __creation__ = 2026-06-03
# __author__ = "jndjama (Joy Ndjama)"
# __copyright__ = "Copyright 2026 ALTIKVA."
# __licence__ = "MIT & CC BY-NC-SA (http://www.altikva.com/licenses/LICENSE-1.0)"
# -#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#

"""Tests for host remediations: the commands they issue and how they read results."""

from __future__ import annotations

from _fakes import ScriptedProvider, fixed
from spero.remediations import build_remediation
from spero.remediations.host import KillProcess, RespawnProcess, RestartService, RotateLogs


async def test_restart_service() -> None:
    provider = ScriptedProvider(fixed(0))
    res = await RestartService("nginx.service").apply(provider)
    assert res.success
    assert provider.commands == [["systemctl", "restart", "nginx.service"]]


async def test_restart_service_sudo() -> None:
    provider = ScriptedProvider(fixed(0))
    await RestartService("nginx.service", sudo=True).apply(provider)
    assert provider.commands[0][0] == "sudo"


async def test_respawn_with_user_uses_runuser_argv() -> None:
    provider = ScriptedProvider(fixed(0))
    await RespawnProcess(start="/opt/app/start.sh --daemon", user="app").apply(provider)
    # runuser + argv, never `su -c <string>` (no shell interpretation of policy params)
    assert provider.commands == [["runuser", "-u", "app", "--", "/opt/app/start.sh", "--daemon"]]


async def test_respawn_without_user_tokenizes() -> None:
    provider = ScriptedProvider(fixed(0))
    await RespawnProcess(start="/opt/app/run --daemon").apply(provider)
    assert provider.commands == [["/opt/app/run", "--daemon"]]


async def test_kill_treats_no_match_as_success() -> None:
    # pkill exits 1 when nothing matched -> "already gone" is fine.
    res = await KillProcess(name="zombie").apply(ScriptedProvider(fixed(1)))
    assert res.success


async def test_rotate_logs_command() -> None:
    provider = ScriptedProvider(fixed(0))
    await RotateLogs(path="/data/logs", keep_days=7).apply(provider)
    assert provider.commands == [["find", "/data/logs", "-type", "f", "-mtime", "+7", "-delete"]]


async def test_build_remediation_from_spec() -> None:
    from spero.core.models import RemediationSpec

    rem = build_remediation(RemediationSpec(type="restart", params={"unit": "x.service"}))
    assert isinstance(rem, RestartService)


def test_build_remediation_unknown() -> None:
    import pytest

    from spero.core.models import RemediationSpec

    with pytest.raises(ValueError, match="unknown remediation"):
        build_remediation(RemediationSpec(type="nope"))
