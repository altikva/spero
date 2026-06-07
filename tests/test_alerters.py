# -#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#
# __creation__ = 2026-06-07
# __author__ = "jndjama (Joy Ndjama)"
# __copyright__ = "Copyright 2026 ALTIKVA."
# __licence__ = "MIT & CC BY-NC-SA (https://www.altikva.com/licenses/LICENSE-1.0)"
# -#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#
# Description: Tests for WebhookAlerter, SlackAlerter, and make_alerter selection.

"""Tests for the HTTP alerters and the make_alerter factory.

httpx.MockTransport stands in for the network, so nothing leaves the test. We
assert the payload + URL on fire/resolve, and that a network error is swallowed.
"""

from __future__ import annotations

import httpx

from spero.alerting import (
    NullAlerter,
    SlackAlerter,
    WebhookAlerter,
    make_alerter,
)
from spero.config import Settings

WEBHOOK_URL = "https://hooks.example.com/spero"
SLACK_URL = "https://hooks.slack.com/services/T000/B000/xxx"


def _capture(captured: list[httpx.Request], status: int = 200) -> httpx.MockTransport:
    def handler(request: httpx.Request) -> httpx.Response:
        captured.append(request)
        return httpx.Response(status)

    return httpx.MockTransport(handler)


def _patch_client(monkeypatch, transport: httpx.MockTransport) -> None:
    """Force every httpx.AsyncClient(...) the alerter builds to use transport."""
    real_init = httpx.AsyncClient.__init__

    def init(self: httpx.AsyncClient, *args: object, **kwargs: object) -> None:
        kwargs["transport"] = transport
        real_init(self, *args, **kwargs)

    monkeypatch.setattr(httpx.AsyncClient, "__init__", init)


async def test_webhook_fire_posts_expected_payload(monkeypatch) -> None:
    captured: list[httpx.Request] = []
    _patch_client(monkeypatch, _capture(captured))

    await WebhookAlerter(WEBHOOK_URL).fire("nginx", "down")

    assert len(captured) == 1
    req = captured[0]
    assert req.method == "POST"
    assert str(req.url) == WEBHOOK_URL
    import json

    assert json.loads(req.content) == {
        "event": "fire",
        "target": "nginx",
        "detail": "down",
    }


async def test_webhook_resolve_posts_expected_payload(monkeypatch) -> None:
    captured: list[httpx.Request] = []
    _patch_client(monkeypatch, _capture(captured))

    await WebhookAlerter(WEBHOOK_URL).resolve("nginx", "up")

    import json

    assert json.loads(captured[0].content) == {
        "event": "resolve",
        "target": "nginx",
        "detail": "up",
    }


async def test_slack_fire_and_resolve_post_text(monkeypatch) -> None:
    captured: list[httpx.Request] = []
    _patch_client(monkeypatch, _capture(captured))

    alerter = SlackAlerter(SLACK_URL)
    await alerter.fire("nginx", "down")
    await alerter.resolve("nginx", "up")

    import json

    assert len(captured) == 2
    assert str(captured[0].url) == SLACK_URL
    fire_body = json.loads(captured[0].content)
    resolve_body = json.loads(captured[1].content)
    assert set(fire_body) == {"text"}
    assert "nginx" in fire_body["text"]
    assert "down" in fire_body["text"]
    assert "nginx" in resolve_body["text"]
    assert "up" in resolve_body["text"]


async def test_webhook_swallows_network_error(monkeypatch) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("boom", request=request)

    _patch_client(monkeypatch, httpx.MockTransport(handler))

    # Must not raise; alerting failures never reach the caller.
    await WebhookAlerter(WEBHOOK_URL).fire("nginx", "down")


async def test_slack_swallows_network_error(monkeypatch) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectTimeout("slow", request=request)

    _patch_client(monkeypatch, httpx.MockTransport(handler))

    await SlackAlerter(SLACK_URL).resolve("nginx", "up")


def test_make_alerter_prefers_slack() -> None:
    settings = Settings(slack_webhook_url=SLACK_URL, alert_webhook_url=WEBHOOK_URL)
    alerter = make_alerter(settings)
    assert isinstance(alerter, SlackAlerter)
    assert alerter.url == SLACK_URL


def test_make_alerter_webhook_when_no_slack() -> None:
    settings = Settings(alert_webhook_url=WEBHOOK_URL)
    alerter = make_alerter(settings)
    assert isinstance(alerter, WebhookAlerter)
    assert alerter.url == WEBHOOK_URL


def test_make_alerter_null_when_unconfigured() -> None:
    assert isinstance(make_alerter(Settings()), NullAlerter)
