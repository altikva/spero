"""Declarative policy model: targets -> probe -> remediations.

This is the modern successor to the old cluster_config.json. A `Policy` is the
whole supervised surface; `frozen` is the global action freeze that blocks every
remediation (ported from the bot's action_freeze flag).
"""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, Field, field_validator, model_validator


class Autonomy(StrEnum):
    """How much a remediation may act on its own.

    suggest -> propose only, a human always approves
    gated   -> low-risk acts automatically, high-risk needs approval (default policy)
    auto    -> acts without approval where policy allows
    """

    suggest = "suggest"
    gated = "gated"
    auto = "auto"


class ProbeSpec(BaseModel):
    type: str
    params: dict[str, object] = Field(default_factory=dict)
    interval: int = 30  # seconds between checks


class RemediationSpec(BaseModel):
    type: str
    params: dict[str, object] = Field(default_factory=dict)
    autonomy: Autonomy = Autonomy.suggest
    # how many times to try before escalating (ported from NB_FAILS_BEFORE_AUTO_RESTART)
    max_attempts: int = 2


class TargetPolicy(BaseModel):
    name: str
    provider: str = "local"  # "local" or "ssh:[user@]host[:port]"
    probe: ProbeSpec
    remediations: list[RemediationSpec] = Field(default_factory=list)

    @field_validator("provider")
    @classmethod
    def _validate_provider(cls, value: str) -> str:
        # Deferred import keeps the core layer from hard-importing providers.
        from spero.providers.host import parse_provider_spec

        parse_provider_spec(value)  # raises ValueError on an unknown/garbage spec
        return value

    @model_validator(mode="after")
    def _validate_buildable(self) -> TargetPolicy:
        """Fail at load if a probe/remediation type or its params are wrong, and
        require the remediation list to be a coherent escalation ladder
        (non-decreasing ``max_attempts``, so 'most-escalated eligible' is well-defined).
        """
        from spero.probes import build_probe
        from spero.remediations import build_remediation

        build_probe(self.probe)  # raises on unknown type / bad params
        last = 0
        for spec in self.remediations:
            build_remediation(spec)
            if spec.max_attempts < last:
                raise ValueError(
                    f"remediation {spec.type!r} has max_attempts={spec.max_attempts} below a "
                    f"prior one ({last}); list them gentlest-first with non-decreasing thresholds"
                )
            last = spec.max_attempts
        return self


class Policy(BaseModel):
    version: int = 1
    frozen: bool = False  # global action freeze
    targets: list[TargetPolicy] = Field(default_factory=list)

    @model_validator(mode="after")
    def _unique_target_names(self) -> Policy:
        names = [t.name for t in self.targets]
        dupes = {n for n in names if names.count(n) > 1}
        if dupes:
            raise ValueError(f"duplicate target names: {sorted(dupes)}")
        return self
