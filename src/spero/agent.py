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
import logging

from spero.alerting.base import Alerter
from spero.api.supervisor import Supervisor
from spero.core.engine import ActionStatus
from spero.core.models import Policy, RemediationSpec, TargetPolicy

log = logging.getLogger(__name__)


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


def latest_policy_order(orders: list[dict]) -> str | None:
    """Return the policy YAML from the last ``policy`` order, or None.

    The owner queues orders in arrival order, so the last policy order wins: an
    agent that fell behind and pulls several at once converges on the newest one.
    """
    yaml_text: str | None = None
    for order in orders:
        if order.get("type") == "policy" and order.get("policy") is not None:
            yaml_text = str(order["policy"])
    return yaml_text


async def swap_supervisor(
    sup: Supervisor,
    policy_yaml: str,
    approver: RemoteApprover,
    *,
    alerter: Alerter | None = None,
) -> Supervisor:
    """Hot-swap the running supervisor to a pushed policy.

    Validates the YAML, stops the old supervisor, starts a new one on the same
    RemoteApprover and alert channel so approvals and alerts keep flowing, and
    returns it. If the policy is invalid the current supervisor is left running and
    returned unchanged, so a bad push from the owner can never take the agent down.
    """
    from spero.core.policy import load_policy_str

    try:
        policy = load_policy_str(policy_yaml)
    except Exception as exc:  # invalid push: keep supervising on the old policy
        log.warning("ignoring invalid pushed policy: %s", exc)
        return sup
    await sup.stop()
    new_sup = Supervisor(policy, approver=approver.approve, approver_name="owner", alerter=alerter)
    await new_sup.start()
    log.info("hot-swapped policy: now supervising %d target(s)", len(policy.targets))
    return new_sup


async def run_agent(
    policy: Policy, *, owner_url: str, agent_id: str, interval: float, token: str = ""
) -> None:
    """Supervise locally and report to the owner until interrupted.

    ``token`` is sent as ``Authorization: Bearer <token>`` so the agent can dial
    home to a token-guarded owner; empty means no auth header.
    """
    import contextlib
    import signal

    import httpx

    from spero.alerting import make_alerter
    from spero.config import settings

    approver = RemoteApprover()
    alerter = make_alerter(settings)  # Slack/webhook/email from config, else NullAlerter
    sup = Supervisor(policy, approver=approver.approve, approver_name="owner", alerter=alerter)
    await sup.start()

    headers = {"Authorization": f"Bearer {token}"} if token else None

    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, stop.set)
        except NotImplementedError:  # e.g. Windows
            signal.signal(sig, lambda *_: loop.call_soon_threadsafe(stop.set))

    try:
        async with httpx.AsyncClient(base_url=owner_url, timeout=10.0, headers=headers) as client:
            while not stop.is_set():
                payload = {"status": sup.status(), "events": sup.events()}
                try:
                    resp = await client.post(f"/agents/{agent_id}/report", json=payload)
                    if resp.status_code == 200:
                        orders = resp.json().get("orders", [])
                        approver.apply_orders(orders)  # approve orders into the gate
                        pushed = latest_policy_order(orders)  # policy orders restart the sup
                        if pushed is not None:
                            sup = await swap_supervisor(sup, pushed, approver, alerter=alerter)
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
