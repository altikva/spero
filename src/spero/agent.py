# -#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#
# __creation__ = 2026-06-06
# __author__ = "jndjama (Joy Ndjama)"
# __copyright__ = "Copyright 2026 ALTIKVA."
# __licence__ = "MIT & CC BY-NC-SA (https://www.altikva.com/licenses/LICENSE-1.0)"
# -#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#
# Description: Dial-home agent: supervise locally, report to a remote owner, obey its orders.

"""The dial-home agent.

Runs the supervision loop locally (a Supervisor) and dials OUT to a remote owner on
a timer: it POSTs status + events, and the response carries orders. A gated
remediation waits for the owner via RemoteApprover, which drops straight into the
engine's existing ``approver`` slot, the same seam a human or the AI approver fills.
The owner is the only one who can act on the cluster, but it never reaches inbound;
the agent pulls its decisions. Works standalone: if the owner is unreachable, the
agent keeps supervising, runs `auto` remediations, and queues `gated` ones.
"""

from __future__ import annotations

import asyncio

from spero.api.supervisor import Supervisor
from spero.core.engine import ActionStatus
from spero.core.models import Policy, RemediationSpec, TargetPolicy


class RemoteApprover:
    """Approves a gated remediation iff the owner has approved that target.

    The report loop fills ``approved`` from the orders the owner returns; the engine
    consults ``approve`` each cycle. Approvals are one-shot: the loop drops a target
    once its action has applied (see run_agent), so a single click is a single action.
    """

    def __init__(self) -> None:
        self.approved: set[str] = set()

    async def approve(self, target: TargetPolicy, spec: RemediationSpec) -> bool:
        return target.name in self.approved

    def apply_orders(self, orders: list[dict]) -> None:
        for order in orders:
            if order.get("type") == "approve" and order.get("target"):
                self.approved.add(str(order["target"]))


async def run_agent(policy: Policy, *, owner_url: str, agent_id: str, interval: float) -> None:
    """Supervise locally and report to the owner until interrupted."""
    import contextlib
    import signal

    import httpx

    approver = RemoteApprover()
    sup = Supervisor(policy, approver=approver.approve)
    await sup.start()

    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, stop.set)
        except NotImplementedError:  # e.g. Windows
            signal.signal(sig, lambda *_: loop.call_soon_threadsafe(stop.set))

    try:
        async with httpx.AsyncClient(base_url=owner_url, timeout=10.0) as client:
            while not stop.is_set():
                payload = {"status": sup.status(), "events": sup.events()}
                try:
                    resp = await client.post(f"/agents/{agent_id}/report", json=payload)
                    if resp.status_code == 200:
                        approver.apply_orders(resp.json().get("orders", []))
                except httpx.HTTPError:
                    pass  # owner unreachable: keep supervising, retry next tick
                # One-shot: forget approvals whose action has applied.
                approver.approved -= {
                    name
                    for name, o in sup.latest.items()
                    if o.action is not None and o.action.status is ActionStatus.applied
                }
                with contextlib.suppress(TimeoutError):
                    await asyncio.wait_for(stop.wait(), timeout=interval)
    finally:
        await sup.stop()
