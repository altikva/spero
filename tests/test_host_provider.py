"""Tests for host providers (local execution + SSH argv construction)."""

from __future__ import annotations

import sys

import pytest

from spero.providers.host import LocalProvider, SSHProvider, make_provider


def test_local_provider_runs() -> None:
    r = LocalProvider().run([sys.executable, "-c", "print('ok')"])
    assert r.ok
    assert "ok" in r.stdout


def test_ssh_argv_includes_destination_and_command() -> None:
    p = SSHProvider("web-01", user="ops")
    argv = p.build_argv("systemctl is-active nginx")
    assert argv[0] == "ssh"
    assert "ops@web-01" in argv
    assert argv[-1] == "systemctl is-active nginx"
    assert "BatchMode=yes" in argv


def test_ssh_argv_without_user() -> None:
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
