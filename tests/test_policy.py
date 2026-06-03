"""Tests for policy loading and the autonomy model."""

from __future__ import annotations

from pathlib import Path

from spero.core.models import Autonomy
from spero.core.policy import load_policy, load_policy_str

ROOT = Path(__file__).resolve().parent.parent


def test_example_policy_loads() -> None:
    p = load_policy(ROOT / "policies" / "example.yaml")
    assert p.version == 1
    assert p.frozen is False
    assert {t.name for t in p.targets} == {"nginx", "data-disk"}


def test_remediation_autonomy_and_attempts() -> None:
    p = load_policy(ROOT / "policies" / "example.yaml")
    nginx = next(t for t in p.targets if t.name == "nginx")
    rem = nginx.remediations[0]
    assert rem.autonomy is Autonomy.gated
    assert rem.max_attempts == 2


def test_defaults_apply_for_minimal_policy() -> None:
    p = load_policy_str(
        """
        targets:
          - name: redis
            probe:
              type: process
              params: {name: redis-server}
            remediations:
              - type: restart
        """
    )
    target = p.targets[0]
    assert target.provider == "local"
    assert target.probe.interval == 30
    # remediation autonomy defaults to the safest level
    assert target.remediations[0].autonomy is Autonomy.suggest
    assert target.remediations[0].max_attempts == 2
