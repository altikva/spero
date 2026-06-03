"""Agentic remediation: an LLM-backed approver for gated actions.

Drops straight into the engine's ``approver`` slot, so 'agentic auto-remediation'
is just the existing human-gated machinery with an AI standing in for the human.
Fails closed: with no model (or an unclear answer) it denies, matching the
human-gated default.
"""

from __future__ import annotations

from spero.ai.llm import LLMClient
from spero.core.models import RemediationSpec, TargetPolicy

_SYSTEM = (
    "You gate self-healing actions for the Spero supervision agent. Reply with exactly "
    "'yes' to approve running the action now, or 'no' to withhold it. Withhold if the "
    "action looks risky, destructive, or unjustified by the situation."
)


class AIApprover:
    def __init__(self, llm: LLMClient, *, context: str = "") -> None:
        self.llm = llm
        self.context = context

    async def approve(self, target: TargetPolicy, spec: RemediationSpec) -> bool:
        prompt = (
            f"Target '{target.name}' (provider {target.provider}) is unhealthy and the "
            f"policy proposes remediation '{spec.type}' with params {spec.params}.\n"
            f"{self.context}\n"
            "Approve running this remediation now? Answer yes or no."
        )
        answer = (await self.llm.complete(prompt, system=_SYSTEM)).strip().lower()
        return answer.startswith("y")
