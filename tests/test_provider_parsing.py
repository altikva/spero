# -#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#
# __creation__ = 2026-06-03
# __author__ = "jndjama (Joy Ndjama)"
# __copyright__ = "Copyright 2026 ALTIKVA."
# __licence__ = "MIT & CC BY-NC-SA (http://www.altikva.com/licenses/LICENSE-1.0)"
# -#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#
# Description: Tests for provider-spec parsing and policy-load validation.

"""Tests for provider-spec parsing and policy-load validation."""

from __future__ import annotations

import pytest

from spero.providers.host import SSHProvider, make_provider, parse_ssh_dest


def test_plain_host() -> None:
    t = parse_ssh_dest("web-01")
    assert (t.host, t.user, t.port) == ("web-01", None, None)


def test_user_at_host() -> None:
    t = parse_ssh_dest("ops@web-01")
    assert (t.host, t.user, t.port) == ("web-01", "ops", None)


def test_host_with_port() -> None:
    t = parse_ssh_dest("web-01:2222")
    assert (t.host, t.user, t.port) == ("web-01", None, 2222)


def test_user_host_port() -> None:
    t = parse_ssh_dest("ops@web-01:2222")
    assert (t.host, t.user, t.port) == ("web-01", "ops", 2222)


def test_ipv6_bracketed_with_port() -> None:
    t = parse_ssh_dest("ops@[2001:db8::1]:22")
    assert (t.host, t.user, t.port) == ("2001:db8::1", "ops", 22)


@pytest.mark.parametrize("bad", ["web-01:notaport", "web-01:99999", "@web-01", "ssh://x", ""])
def test_bad_dest_raises(bad: str) -> None:
    with pytest.raises(ValueError):
        parse_ssh_dest(bad)


def test_make_provider_carries_port() -> None:
    p = make_provider("ssh:ops@web-01:2222")
    assert isinstance(p, SSHProvider)
    assert p.port == 2222
    assert p.user == "ops"
    assert p.host == "web-01"


def test_make_provider_rejects_garbage() -> None:
    with pytest.raises(ValueError, match="unknown provider"):
        make_provider("sssh:web-01")
