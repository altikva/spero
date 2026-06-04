# -#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#
# __creation__ = 2026-06-03
# __author__ = "jndjama (Joy Ndjama)"
# __copyright__ = "Copyright 2026 ALTIKVA."
# __licence__ = "MIT & CC BY-NC-SA (http://www.altikva.com/licenses/LICENSE-1.0)"
# -#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#
# Description: LLM-assisted diagnosis and incident summaries.

"""LLM-assisted diagnosis and incident summaries.

Both degrade gracefully: with NullLLM (no model) they return a deterministic
heuristic built from the inputs, so they're always useful and always testable.
"""

from __future__ import annotations

from collections.abc import Sequence

from spero.ai.llm import LLMClient

_SYSTEM = (
    "You are an SRE assistant. Given a failing target and recent events, give a short, "
    "concrete likely-cause analysis and the single most useful next step. Be terse."
)


async def diagnose_failure(target: str, detail: str, recent: Sequence[str], llm: LLMClient) -> str:
    """Root-cause sketch for a failing target from its recent events."""
    prompt = (
        f"Target '{target}' is unhealthy: {detail}\n\n"
        "Recent events (newest last):\n" + "\n".join(f"- {r}" for r in recent) + "\n\n"
        "What is the likely cause and the best next step?"
    )
    answer = await llm.complete(prompt, system=_SYSTEM)
    if answer:
        return answer
    # Heuristic fallback when no model is configured.
    return (
        f"{target} is unhealthy ({detail}). {len(recent)} recent event(s). "
        "No model configured — inspect the events above and the target's logs."
    )


async def incident_summary(events: Sequence[str], llm: LLMClient) -> str:
    """A human-readable summary of a batch of events."""
    if not events:
        return "No events to summarize."
    prompt = "Summarize these supervision events into a brief incident report:\n" + "\n".join(
        f"- {e}" for e in events
    )
    answer = await llm.complete(prompt, system=_SYSTEM)
    if answer:
        return answer
    return f"{len(events)} event(s); newest: {events[-1]}"
