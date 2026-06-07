# -#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#
# __creation__ = 2026-06-06
# __author__ = "jndjama (Joy Ndjama)"
# __copyright__ = "Copyright 2026 ALTIKVA."
# __licence__ = "MIT & CC BY-NC-SA (https://www.altikva.com/licenses/LICENSE-1.0)"
# -#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#
# Description: Tests for the dial-home agent's RemoteApprover.

"""Tests for the dial-home agent (RemoteApprover gating)."""

from __future__ import annotations

from spero.agent import RemoteApprover, latest_policy_order, swap_supervisor
from spero.api.supervisor import Supervisor
from spero.core.models import ProbeSpec, RemediationSpec, TargetPolicy
from spero.core.policy import load_policy_str

_POLICY_A = """
version: 1
targets:
  - name: nginx
    provider: local
    probe:
      type: systemd
      params:
        unit: nginx.service
    remediations:
      - type: restart
        params:
          unit: nginx.service
        autonomy: gated
        max_attempts: 2
"""

_POLICY_B = """
version: 1
targets:
  - name: web
    provider: local
    probe:
      type: systemd
      params:
        unit: web.service
    remediations:
      - type: restart
        params:
          unit: web.service
        autonomy: gated
        max_attempts: 2
  - name: cache
    provider: local
    probe:
      type: systemd
      params:
        unit: cache.service
    remediations:
      - type: restart
        params:
          unit: cache.service
        autonomy: gated
        max_attempts: 2
"""


async def test_remote_approver_gates_on_owner_orders() -> None:
    ap = RemoteApprover()
    target = TargetPolicy(
        name="orders", provider="local", probe=ProbeSpec(type="systemd", params={"unit": "x"})
    )
    spec = RemediationSpec(type="restart", params={})
    assert await ap.approve(target, spec) is False  # nothing approved yet
    ap.apply_orders([{"type": "approve", "target": "orders"}, {"type": "noise"}])
    assert await ap.approve(target, spec) is True  # owner approved this target
    other = TargetPolicy(
        name="web", provider="local", probe=ProbeSpec(type="systemd", params={"unit": "x"})
    )
    assert await ap.approve(other, spec) is False  # a different target stays gated


def test_latest_policy_order_picks_last() -> None:
    assert latest_policy_order([]) is None
    assert latest_policy_order([{"type": "approve", "target": "x"}]) is None
    orders = [
        {"type": "policy", "policy": "first"},
        {"type": "approve", "target": "x"},
        {"type": "policy", "policy": "second"},
    ]
    assert latest_policy_order(orders) == "second"  # newest push wins


async def test_swap_supervisor_hot_swaps_policy() -> None:
    ap = RemoteApprover()
    ap.approved.add("nginx")  # an in-flight approval before the swap
    sup = Supervisor(load_policy_str(_POLICY_A), approver=ap.approve, approver_name="owner")
    await sup.start()
    try:
        new_sup = await swap_supervisor(sup, _POLICY_B, ap)
        assert new_sup is not sup  # a fresh supervisor on the new policy
        assert [t.name for t in new_sup.policy.targets] == ["web", "cache"]
        # The same RemoteApprover backs the new engine, so approvals still flow.
        assert ap.approved == {"nginx"}
        target = new_sup.policy.targets[0]
        ap.approved.add(target.name)
        spec = RemediationSpec(type="restart", params={})
        assert await ap.approve(target, spec) is True
    finally:
        await new_sup.stop()


async def test_swap_supervisor_keeps_running_on_invalid_policy() -> None:
    ap = RemoteApprover()
    sup = Supervisor(load_policy_str(_POLICY_A), approver=ap.approve, approver_name="owner")
    await sup.start()
    try:
        same = await swap_supervisor(sup, "targets: [unclosed", ap)
        assert same is sup  # invalid push: the old supervisor is left running
        assert [t.name for t in same.policy.targets] == ["nginx"]
    finally:
        await sup.stop()
