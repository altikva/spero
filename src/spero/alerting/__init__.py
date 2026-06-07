# -#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#
# __creation__ = 2026-06-03
# __author__ = "jndjama (Joy Ndjama)"
# __copyright__ = "Copyright 2026 ALTIKVA."
# __licence__ = "MIT & CC BY-NC-SA (https://www.altikva.com/licenses/LICENSE-1.0)"
# -#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#
# Description: Alerting sinks plus make_alerter, the settings-driven channel selector.

"""Alerting sinks plus make_alerter, the settings-driven channel selector.

NullAlerter by default; EmailAlerter ports the bot's mail.py; WebhookAlerter and
SlackAlerter POST to an HTTP endpoint. make_alerter picks one from Settings.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from spero.alerting.base import Alerter, NullAlerter
from spero.alerting.email import EmailAlerter
from spero.alerting.slack import SlackAlerter
from spero.alerting.webhook import WebhookAlerter

if TYPE_CHECKING:
    from spero.config import Settings

__all__ = [
    "Alerter",
    "EmailAlerter",
    "NullAlerter",
    "SlackAlerter",
    "WebhookAlerter",
    "make_alerter",
]


def make_alerter(settings: Settings) -> Alerter:
    """Pick the configured alert channel.

    Slack takes priority over a generic webhook when both URLs are set; with
    neither set, alerting is a no-op (NullAlerter).
    """
    if settings.slack_webhook_url:
        return SlackAlerter(settings.slack_webhook_url)
    if settings.alert_webhook_url:
        return WebhookAlerter(settings.alert_webhook_url)
    return NullAlerter()
