# -#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#
# __creation__ = 2026-06-03
# __author__ = "jndjama (Joy Ndjama)"
# __copyright__ = "Copyright 2026 ALTIKVA."
# __licence__ = "MIT & CC BY-NC-SA (http://www.altikva.com/licenses/LICENSE-1.0)"
# -#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#

"""Tests for host providers (async local execution + SSH wiring)."""

from __future__ import annotations

import sys

import pytest

from spero.providers.host import LocalProvider, SSHProvider, make_provider


async def test_local_provider_runs() -> None:
    r = await LocalProvider().run([sys.executable, "-c", "print('ok')"])
    assert r.ok
    assert "ok" in r.stdout


def test_ssh_destination() -> None:
    assert SSHProvider("web-01", user="ops").destination == "ops@web-01"
    assert SSHProvider("web-01").destination == "web-01"


def test_make_provider_local() -> None:
    assert isinstance(make_provider("local"), LocalProvider)


def test_make_provider_ssh() -> None:
    p = make_provider("ssh:ops@web-01")
    assert isinstance(p, SSHProvider)
    assert p.host == "web-01"
    assert p.user == "ops"


def test_make_provider_unknown() -> None:
    with pytest.raises(ValueError, match="unknown provider"):
        make_provider("magic:foo")


async def test_ssh_provider_rejects_cwd_env() -> None:
    p = SSHProvider("web-01")
    with pytest.raises(NotImplementedError):
        await p.run("uptime", cwd="/tmp")
