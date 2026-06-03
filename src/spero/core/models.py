"""Declarative policy model: targets -> probe -> remediations.

A `Policy` is the
whole supervised surface; `frozen` is the global action freeze that blocks every
remediation.
"""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, Field


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
    # how many times to try before escalating
    max_attempts: int = 2


class TargetPolicy(BaseModel):
    name: str
    provider: str = "local"  # "local" or "ssh:<host>"
    probe: ProbeSpec
    remediations: list[RemediationSpec] = Field(default_factory=list)


class Policy(BaseModel):
    version: int = 1
    frozen: bool = False  # global action freeze
    targets: list[TargetPolicy] = Field(default_factory=list)
