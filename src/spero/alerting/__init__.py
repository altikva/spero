"""Alerting sinks. NullAlerter by default; EmailAlerter ports the bot's mail.py."""

from spero.alerting.base import Alerter, NullAlerter
from spero.alerting.email import EmailAlerter

__all__ = ["Alerter", "EmailAlerter", "NullAlerter"]
