# -#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#
# __creation__ = 2026-06-07
# __author__ = "jndjama (Joy Ndjama)"
# __copyright__ = "Copyright 2026 ALTIKVA."
# __licence__ = "MIT & CC BY-NC-SA (https://www.altikva.com/licenses/LICENSE-1.0)"
# -#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#
# Description: Generic webhook alerter. POSTs a JSON event to a URL, never raises.

"""Generic webhook alerter. POSTs a JSON event to a URL, never raises.

Alerting is best-effort: if the endpoint is down or slow, the supervision loop
keeps running. So every network error is caught and swallowed, matching how the
rest of the alerting layer degrades.
"""

from __future__ import annotations

import httpx

from spero.alerting.base import Alerter

# A bounded timeout so a hung endpoint can never stall a supervision cycle.
DEFAULT_TIMEOUT = 5.0


class WebhookAlerter(Alerter):
    def __init__(self, url: str, *, timeout: float = DEFAULT_TIMEOUT) -> None:
        self.url = url
        self.timeout = timeout

    async def fire(self, target: str, detail: str) -> None:
        await self._post({"event": "fire", "target": target, "detail": detail})

    async def resolve(self, target: str, detail: str) -> None:
        await self._post({"event": "resolve", "target": target, "detail": detail})

    async def _post(self, payload: dict[str, str]) -> None:
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                await client.post(self.url, json=payload)
        except httpx.HTTPError:
            # Endpoint unreachable, timed out, or refused. Drop the alert and
            # let supervision continue; alerting is never allowed to crash it.
            return None
