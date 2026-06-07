# -#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#
# __creation__ = 2026-06-07
# __author__ = "jndjama (Joy Ndjama)"
# __copyright__ = "Copyright 2026 ALTIKVA."
# __licence__ = "MIT & CC BY-NC-SA (https://www.altikva.com/licenses/LICENSE-1.0)"
# -#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#
# Description: Tests for EmailAlerter STARTTLS + SMTP auth (with a stub smtplib).

"""Tests for the EmailAlerter, with a stub SMTP so nothing leaves the test."""

from __future__ import annotations

import smtplib
from typing import ClassVar

import pytest

from spero.alerting.email import EmailAlerter


class _StubSMTP:
    """Records the calls EmailAlerter makes; stands in for smtplib.SMTP."""

    calls: ClassVar[list[str]] = []
    login_args: ClassVar[tuple[str, str] | None] = None

    def __init__(self, host: str, port: int) -> None:
        _StubSMTP.calls = []
        _StubSMTP.login_args = None
        self.host = host
        self.port = port

    def __enter__(self) -> _StubSMTP:
        return self

    def __exit__(self, *exc: object) -> None:
        return None

    def starttls(self) -> None:
        _StubSMTP.calls.append("starttls")

    def login(self, user: str, password: str) -> None:
        _StubSMTP.calls.append("login")
        _StubSMTP.login_args = (user, password)

    def send_message(self, msg: object) -> None:
        _StubSMTP.calls.append("send")


@pytest.fixture(autouse=True)
def _stub_smtp(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(smtplib, "SMTP", _StubSMTP)


async def test_plain_smtp_no_tls_no_login() -> None:
    alerter = EmailAlerter(host="mail", sender="s@x", recipients=["r@x"])
    await alerter.fire("nginx", "down")
    assert _StubSMTP.calls == ["send"]


async def test_starttls_and_login() -> None:
    alerter = EmailAlerter(
        host="mail",
        sender="s@x",
        recipients=["r@x"],
        use_tls=True,
        username="u",
        password="p",
    )
    await alerter.resolve("nginx", "up")
    assert _StubSMTP.calls == ["starttls", "login", "send"]
    assert _StubSMTP.login_args == ("u", "p")
