# -#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#
# __creation__ = 2026-06-03
# __author__ = "jndjama (Joy Ndjama)"
# __copyright__ = "Copyright 2026 ALTIKVA."
# __licence__ = "MIT & CC BY-NC-SA (http://www.altikva.com/licenses/LICENSE-1.0)"
# -#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#
# Description: SMTP email alerter. Ports send_mail_from_server, modernized to EmailMessage.

"""SMTP email alerter. Ports send_mail_from_server, modernized to EmailMessage.

smtplib is blocking, so sends run in a worker thread to stay out of the event loop.
"""

from __future__ import annotations

import asyncio
import smtplib
from collections.abc import Sequence
from email.message import EmailMessage

from spero.alerting.base import Alerter


class EmailAlerter(Alerter):
    def __init__(
        self,
        *,
        host: str,
        sender: str,
        recipients: Sequence[str],
        port: int = 25,
        subject_prefix: str = "[spero]",
    ) -> None:
        self.host = host
        self.port = port
        self.sender = sender
        self.recipients = list(recipients)
        self.subject_prefix = subject_prefix

    async def fire(self, target: str, detail: str) -> None:
        await self._send(f"ALERT {target}", f"{target} is unhealthy: {detail}")

    async def resolve(self, target: str, detail: str) -> None:
        await self._send(f"RESOLVED {target}", f"{target} recovered: {detail}")

    async def _send(self, subject: str, body: str) -> None:
        msg = EmailMessage()
        msg["Subject"] = f"{self.subject_prefix} {subject}"
        msg["From"] = self.sender
        msg["To"] = ", ".join(self.recipients)
        msg.set_content(body)
        await asyncio.to_thread(self._send_sync, msg)

    def _send_sync(self, msg: EmailMessage) -> None:
        with smtplib.SMTP(self.host, self.port) as smtp:
            smtp.send_message(msg)
