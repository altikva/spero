# -#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#
# __creation__ = 2026-06-06
# __author__ = "jndjama (Joy Ndjama)"
# __copyright__ = "Copyright 2026 ALTIKVA."
# __licence__ = "MIT & CC BY-NC-SA (https://www.altikva.com/licenses/LICENSE-1.0)"
# -#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#
# Description: Tests for the dial-home agent's RemoteApprover.

"""Tests for the dial-home agent (RemoteApprover gating)."""

from __future__ import annotations

from spero.agent import RemoteApprover
from spero.core.models import ProbeSpec, RemediationSpec, TargetPolicy


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
