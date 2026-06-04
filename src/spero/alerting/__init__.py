# -#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#
# __creation__ = 2026-06-03
# __author__ = "jndjama (Joy Ndjama)"
# __copyright__ = "Copyright 2026 ALTIKVA."
# __licence__ = "MIT & CC BY-NC-SA (https://www.altikva.com/licenses/LICENSE-1.0)"
# -#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#
# Description: Alerting sinks. NullAlerter by default; EmailAlerter ports the bot's mail.py.

"""Alerting sinks. NullAlerter by default; EmailAlerter ports the bot's mail.py."""

from spero.alerting.base import Alerter, NullAlerter
from spero.alerting.email import EmailAlerter

__all__ = ["Alerter", "EmailAlerter", "NullAlerter"]
