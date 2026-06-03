"""Alerting sinks. NullAlerter by default; EmailAlerter sends over SMTP."""

from spero.alerting.base import Alerter, NullAlerter
from spero.alerting.email import EmailAlerter

__all__ = ["Alerter", "EmailAlerter", "NullAlerter"]
