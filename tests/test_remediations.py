# -#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#
# __creation__ = 2026-06-03
# __author__ = "jndjama (Joy Ndjama)"
# __copyright__ = "Copyright 2026 ALTIKVA."
# __licence__ = "Apache-2.0 (https://www.apache.org/licenses/LICENSE-2.0)"
# -#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#
# Description: Tests for host remediations: the commands they issue and how they read results.

"""Tests for host remediations: the commands they issue and how they read results."""

from __future__ import annotations

import pytest

from _fakes import ScriptedProvider, fixed
from spero.core.models import RemediationSpec
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


async def test_respawn_passes_no_env_by_default() -> None:
    provider = ScriptedProvider(fixed(0))
    await RespawnProcess(start="/opt/app/run").apply(provider)
    assert provider.envs == [(None, False)]


async def test_respawn_merges_env() -> None:
    provider = ScriptedProvider(fixed(0))
    res = await RespawnProcess(start="/opt/app/run", env={"PORT": "8080"}).apply(provider)
    assert provider.envs == [({"PORT": "8080"}, False)]
    assert res.detail == "started '/opt/app/run' (env merged: PORT)"


async def test_respawn_replaces_env_and_keeps_values_out_of_the_result() -> None:
    provider = ScriptedProvider(fixed(0))
    rem = RespawnProcess(
        start="/opt/app/run", env={"PATH": "/usr/bin", "TOKEN": "s3cr3t"}, env_replace=True
    )
    res = await rem.apply(provider)
    assert provider.envs == [({"PATH": "/usr/bin", "TOKEN": "s3cr3t"}, True)]
    assert "s3cr3t" not in res.detail
    assert "/usr/bin" not in res.detail
    assert "PATH, TOKEN" in res.detail


async def test_respawn_env_with_user_still_uses_runuser_argv() -> None:
    provider = ScriptedProvider(fixed(0))
    await RespawnProcess(start="/opt/app/run", user="app", env={"A": "1"}).apply(provider)
    assert provider.commands == [["runuser", "-u", "app", "--", "/opt/app/run"]]
    assert provider.envs == [({"A": "1"}, False)]


@pytest.mark.parametrize(
    "params",
    [
        {"start": "x", "env": {"PORT": 8080}},
        {"start": "x", "env": ["A=1"]},
        {"start": "x", "env": {"A": "1"}, "env_replace": "yes"},
        {"start": "x", "env_replace": True},
    ],
)
def test_respawn_rejects_bad_env_params(params: dict[str, object]) -> None:
    with pytest.raises(ValueError, match="bad params for remediation 'respawn'"):
        build_remediation(RemediationSpec(type="respawn", params=params))


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
