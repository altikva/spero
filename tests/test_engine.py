# -#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#
# __creation__ = 2026-06-03
# __author__ = "jndjama (Joy Ndjama)"
# __copyright__ = "Copyright 2026 ALTIKVA."
# __licence__ = "MIT & CC BY-NC-SA (http://www.altikva.com/licenses/LICENSE-1.0)"
# -#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#

"""Tests for the supervision engine: counting, escalation, autonomy gating, freeze."""

from __future__ import annotations

from _fakes import ScriptedProvider, systemd_handler
from spero.alerting.base import Alerter
from spero.core.engine import ActionStatus, Engine
from spero.core.models import RemediationSpec, TargetPolicy
from spero.core.policy import load_policy_str


def _policy(autonomy: str = "auto", max_attempts: int = 1, frozen: bool = False) -> str:
    return f"""
    frozen: {str(frozen).lower()}
    targets:
      - name: web
        provider: local
        probe: {{type: systemd, params: {{unit: nginx.service}}}}
        remediations:
          - type: restart
            params: {{unit: nginx.service}}
            autonomy: {autonomy}
            max_attempts: {max_attempts}
    """


def _engine(policy_yaml: str, provider: ScriptedProvider, **kw: object) -> Engine:
    return Engine(load_policy_str(policy_yaml), provider_factory=lambda _spec: provider, **kw)


async def test_healthy_target_no_action() -> None:
    provider = ScriptedProvider(systemd_handler(active=True))
    engine = _engine(_policy(), provider)
    (outcome,) = await engine.run_cycle()
    assert outcome.healthy
    assert outcome.failures == 0
    assert outcome.action is None


async def test_waiting_below_threshold() -> None:
    provider = ScriptedProvider(systemd_handler(active=False))
    engine = _engine(_policy(max_attempts=2), provider)
    (outcome,) = await engine.run_cycle()
    assert not outcome.healthy
    assert outcome.failures == 1
    assert outcome.action is not None
    assert outcome.action.status is ActionStatus.waiting
    # no restart was attempted
    assert all("restart" not in c for c in provider.commands)


async def test_auto_remediation_applies() -> None:
    provider = ScriptedProvider(systemd_handler(active=False, restart_ok=True))
    engine = _engine(_policy(autonomy="auto", max_attempts=1), provider)
    (outcome,) = await engine.run_cycle()
    assert outcome.action is not None
    assert outcome.action.status is ActionStatus.applied
    assert ["systemctl", "restart", "nginx.service"] in provider.commands


async def test_gated_waits_for_approval_by_default() -> None:
    provider = ScriptedProvider(systemd_handler(active=False))
    engine = _engine(_policy(autonomy="gated", max_attempts=1), provider)
    (outcome,) = await engine.run_cycle()
    assert outcome.action is not None
    assert outcome.action.status is ActionStatus.awaiting_approval
    assert all("restart" not in c for c in provider.commands)


async def test_gated_runs_when_approved() -> None:
    provider = ScriptedProvider(systemd_handler(active=False))

    async def approve(_t: TargetPolicy, _s: RemediationSpec) -> bool:
        return True

    engine = _engine(_policy(autonomy="gated", max_attempts=1), provider, approver=approve)
    (outcome,) = await engine.run_cycle()
    assert outcome.action is not None
    assert outcome.action.status is ActionStatus.applied


async def test_suggest_never_acts() -> None:
    provider = ScriptedProvider(systemd_handler(active=False))
    engine = _engine(_policy(autonomy="suggest", max_attempts=1), provider)
    (outcome,) = await engine.run_cycle()
    assert outcome.action is not None
    assert outcome.action.status is ActionStatus.suggested
    assert all("restart" not in c for c in provider.commands)


async def test_freeze_blocks_action() -> None:
    provider = ScriptedProvider(systemd_handler(active=False))
    engine = _engine(_policy(autonomy="auto", max_attempts=1, frozen=True), provider)
    (outcome,) = await engine.run_cycle()
    assert outcome.action is not None
    assert outcome.action.status is ActionStatus.frozen
    assert all("restart" not in c for c in provider.commands)


async def test_failure_count_accumulates_across_cycles() -> None:
    provider = ScriptedProvider(systemd_handler(active=False))
    engine = _engine(_policy(autonomy="auto", max_attempts=3), provider)
    await engine.run_cycle()
    await engine.run_cycle()
    (outcome,) = await engine.run_cycle()
    assert outcome.failures == 3
    # threshold reached on the third cycle
    assert outcome.action is not None
    assert outcome.action.status is ActionStatus.applied


async def test_counter_resets_after_apply_no_runaway() -> None:
    # With max_attempts=2 and a persistently-down target, the engine applies on the
    # threshold cycle, then must WAIT again next cycle (counter reset), not re-fire.
    provider = ScriptedProvider(systemd_handler(active=False, restart_ok=True))
    engine = _engine(_policy(autonomy="auto", max_attempts=2), provider)
    o1 = (await engine.run_cycle())[0]
    o2 = (await engine.run_cycle())[0]
    o3 = (await engine.run_cycle())[0]
    assert o1.action and o1.action.status is ActionStatus.waiting
    assert o2.action and o2.action.status is ActionStatus.applied
    assert o3.action and o3.action.status is ActionStatus.waiting  # reset, not re-fired


async def test_escalation_picks_last_eligible_in_order() -> None:
    policy = """
    targets:
      - name: web
        provider: local
        probe: {type: systemd, params: {unit: nginx.service}}
        remediations:
          - {type: restart, params: {unit: nginx.service}, autonomy: suggest, max_attempts: 1}
          - {type: kill, params: {name: nginx}, autonomy: suggest, max_attempts: 1}
    """
    provider = ScriptedProvider(systemd_handler(active=False))
    engine = _engine(policy, provider)
    (outcome,) = await engine.run_cycle()
    # both eligible at n=1; the more-escalated (last) one is selected
    assert outcome.action is not None
    assert outcome.action.remediation == "kill"


async def test_one_raising_target_does_not_break_others() -> None:
    from _fakes import ScriptedProvider as SP

    def boom(_cmd: object) -> None:
        raise RuntimeError("provider exploded")

    good = ScriptedProvider(systemd_handler(active=True))
    bad = SP(boom)  # its .run raises

    def factory(spec: str):  # type: ignore[no-untyped-def]
        return bad if spec.startswith("ssh") else good

    policy = """
    targets:
      - {name: ok, provider: local, probe: {type: systemd, params: {unit: a.service}}}
      - {name: broken, provider: ssh:web-01, probe: {type: systemd, params: {unit: b.service}}}
    """
    engine = Engine(load_policy_str(policy), provider_factory=factory)
    outcomes = {o.target: o for o in await engine.run_cycle()}
    assert outcomes["ok"].healthy
    assert not outcomes["broken"].healthy
    assert outcomes["broken"].detail.startswith("error")


class SpyAlerter(Alerter):
    def __init__(self) -> None:
        self.fired: list[str] = []
        self.resolved: list[str] = []

    async def fire(self, target: str, detail: str) -> None:
        self.fired.append(target)

    async def resolve(self, target: str, detail: str) -> None:
        self.resolved.append(target)


async def test_alert_fires_then_resolves() -> None:
    alerter = SpyAlerter()
    # unhealthy on cycle 1, healthy on cycle 2
    states = iter([False, True])
    provider = ScriptedProvider(lambda cmd: systemd_handler(active=next(states))(cmd))
    engine = _engine(_policy(autonomy="suggest"), provider, alerter=alerter)
    await engine.run_cycle()
    await engine.run_cycle()
    assert alerter.fired == ["web"]
    assert alerter.resolved == ["web"]
