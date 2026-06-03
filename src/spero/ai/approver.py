"""Agentic remediation: an LLM-backed approver for gated actions.

Drops straight into the engine's ``approver`` slot, so 'agentic auto-remediation'
is just the existing human-gated machinery with an AI standing in for the human.
Fails closed: with no model (or an unclear answer) it denies, matching the
human-gated default.
"""

from __future__ import annotations

import asyncio

from spero.ai.llm import LLMClient
from spero.core.models import RemediationSpec, TargetPolicy

_SYSTEM = (
    "You gate self-healing actions for the Spero supervision agent. Answer with a single "
    "word on the last line: 'yes' to approve running the action now, or 'no' to withhold "
    "it. Withhold if the action looks risky, destructive, or unjustified by the situation."
)
# Exact affirmative tokens only -- a security gate must not be fooled by
# "yes, but..." or "y'know, no", so we match the last line exactly, not a prefix.
_AFFIRMATIVE = frozenset({"yes", "approve", "approved"})


class AIApprover:
    def __init__(self, llm: LLMClient, *, context: str = "", timeout: float = 30.0) -> None:
        self.llm = llm
        self.context = context
        self.timeout = timeout

    async def approve(self, target: TargetPolicy, spec: RemediationSpec) -> bool:
        prompt = (
            f"Target '{target.name}' (provider {target.provider}) is unhealthy and the "
            f"policy proposes remediation '{spec.type}' with params {spec.params}.\n"
            f"{self.context}\n"
            "Approve running this remediation now? Answer yes or no."
        )
        try:
            raw = await asyncio.wait_for(
                self.llm.complete(prompt, system=_SYSTEM), timeout=self.timeout
            )
        except Exception:
            return False
        raw = raw.strip()
        if not raw:
            return False
        verdict = raw.splitlines()[-1].strip().lower().rstrip(".!,")
        return verdict in _AFFIRMATIVE
