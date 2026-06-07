# -#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#
# __creation__ = 2026-06-07
# __author__ = "jndjama (Joy Ndjama)"
# __copyright__ = "Copyright 2026 ALTIKVA."
# __licence__ = "MIT & CC BY-NC-SA (https://www.altikva.com/licenses/LICENSE-1.0)"
# -#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#
# Description: Slack incoming-webhook alerter. Posts a {"text": ...} message, never raises.

"""Slack incoming-webhook alerter. Posts a {"text": ...} message, never raises.

Slack's incoming webhooks accept a simple {"text": "..."} body. Same best-effort
contract as WebhookAlerter: a bounded timeout, and network errors are swallowed
so a flaky Slack never stalls or crashes the supervision loop.
"""

from __future__ import annotations

import httpx

from spero.alerting.base import Alerter

# A bounded timeout so a hung endpoint can never stall a supervision cycle.
DEFAULT_TIMEOUT = 5.0


class SlackAlerter(Alerter):
    def __init__(self, url: str, *, timeout: float = DEFAULT_TIMEOUT) -> None:
        self.url = url
        self.timeout = timeout

    async def fire(self, target: str, detail: str) -> None:
        await self._post(f":rotating_light: *{target}* is unhealthy: {detail}")

    async def resolve(self, target: str, detail: str) -> None:
        await self._post(f":white_check_mark: *{target}* recovered: {detail}")

    async def _post(self, text: str) -> None:
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                await client.post(self.url, json={"text": text})
        except httpx.HTTPError:
            # Slack unreachable or slow. Drop the message; supervision continues.
            return None
