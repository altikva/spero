# -#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#
# __creation__ = 2026-06-03
# __author__ = "jndjama (Joy Ndjama)"
# __copyright__ = "Copyright 2026 ALTIKVA."
# __licence__ = "MIT & CC BY-NC-SA (http://www.altikva.com/licenses/LICENSE-1.0)"
# -#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#

"""Pluggable LLM client. Claude is the default backend; NullLLM needs no key.

The rest of the AI layer depends only on the ``LLMClient`` protocol, so it runs
(degraded but useful) with no model configured and is trivially testable.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

DEFAULT_MODEL = "claude-sonnet-4-6"


@runtime_checkable
class LLMClient(Protocol):
    async def complete(self, prompt: str, *, system: str | None = None) -> str:
        """Return the model's text answer, or '' if no model is available."""
        ...


class NullLLM:
    """No model configured. Returns '' so callers fall back to their heuristics."""

    async def complete(self, prompt: str, *, system: str | None = None) -> str:
        return ""


class AnthropicLLM:
    """Claude backend. Requires the ``ai`` extra (``pip install spero[ai]``) and a key."""

    def __init__(self, *, model: str = DEFAULT_MODEL, api_key: str | None = None) -> None:
        import anthropic  # imported lazily so the dependency stays optional

        # Bounded so a slow/hung API call can't stall a supervision tick.
        self._client = anthropic.AsyncAnthropic(api_key=api_key, timeout=30.0, max_retries=1)
        self.model = model

    async def complete(self, prompt: str, *, system: str | None = None) -> str:
        try:
            message = await self._client.messages.create(
                model=self.model,
                max_tokens=1024,
                system=system or "You are an SRE assistant for the Spero supervision agent.",
                messages=[{"role": "user", "content": prompt}],
            )
        except Exception:
            return ""
        return "".join(block.text for block in message.content if block.type == "text")
