# -#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#
# __creation__ = 2026-06-03
# __author__ = "jndjama (Joy Ndjama)"
# __copyright__ = "Copyright 2026 ALTIKVA."
# __licence__ = "MIT & CC BY-NC-SA (https://www.altikva.com/licenses/LICENSE-1.0)"
# -#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#
# Description: Tests for the AI layer: predictive (pure), and the LLM-backed pieces via a fake.

"""Tests for the AI layer: predictive (pure), and the LLM-backed pieces via a fake."""

from __future__ import annotations

from spero.ai import (
    AIApprover,
    NullLLM,
    detect_flapping,
    diagnose_failure,
    forecast_threshold_crossing,
    nl_query,
    parse_pct,
)
from spero.ai.llm import LLMClient
from spero.core.models import RemediationSpec, TargetPolicy


class FakeLLM(LLMClient):
    def __init__(self, reply: str) -> None:
        self.reply = reply
        self.prompts: list[str] = []

    async def complete(self, prompt: str, *, system: str | None = None) -> str:
        self.prompts.append(prompt)
        return self.reply


# --- predictive (pure, no model) -------------------------------------------------


def test_forecast_rising_series_reaches_threshold() -> None:
    # 10%/unit rising from 50; should hit 90 in ~4 time units after the last sample.
    samples = [(0.0, 50.0), (1.0, 60.0), (2.0, 70.0)]
    eta = forecast_threshold_crossing(samples, 90.0)
    assert eta is not None
    assert abs(eta - 2.0) < 1e-6


def test_forecast_flat_series_returns_none() -> None:
    assert forecast_threshold_crossing([(0.0, 50.0), (1.0, 50.0)], 90.0) is None


def test_forecast_needs_two_samples() -> None:
    assert forecast_threshold_crossing([(0.0, 50.0)], 90.0) is None


def test_detect_flapping() -> None:
    assert detect_flapping([True, False, True, False], max_transitions=3)
    assert not detect_flapping([True, True, False], max_transitions=3)


def test_parse_pct() -> None:
    assert parse_pct("/data at 73% (threshold 90%)") == 73
    assert parse_pct("no number here") is None


# --- LLM-backed (via FakeLLM / NullLLM) ------------------------------------------


async def test_diagnose_uses_model_when_present() -> None:
    llm = FakeLLM("disk filled from log spam")
    out = await diagnose_failure("web", "down", ["evt1", "evt2"], llm)
    assert out == "disk filled from log spam"
    assert "web" in llm.prompts[0]


async def test_diagnose_falls_back_without_model() -> None:
    out = await diagnose_failure("web", "down", ["evt1"], NullLLM())
    assert "web" in out
    assert "No model configured" in out


async def test_nl_query_with_and_without_model() -> None:
    docs = ["2026-01-01 probe_fail web: nginx is inactive", "2026-01-01 info db: ok"]
    assert await nl_query("why did web fail?", docs, FakeLLM("nginx crashed")) == "nginx crashed"
    fallback = await nl_query("why did web fail?", docs, NullLLM())
    assert "No model configured" in fallback


async def test_ai_approver_exact_match_only() -> None:
    target = TargetPolicy(name="web", probe={"type": "systemd", "params": {"unit": "x.service"}})
    spec = RemediationSpec(type="restart", params={"unit": "x.service"})
    assert await AIApprover(FakeLLM("yes")).approve(target, spec) is True
    assert await AIApprover(FakeLLM("YES")).approve(target, spec) is True
    assert await AIApprover(FakeLLM("no")).approve(target, spec) is False
    # a loose prefix match must NOT approve a hedged or negative answer
    assert await AIApprover(FakeLLM("yes, but only with a human")).approve(target, spec) is False
    assert await AIApprover(FakeLLM("y'know, the answer is no")).approve(target, spec) is False
    # reasoning followed by a verdict on the last line
    assert await AIApprover(FakeLLM("It looks risky.\nno")).approve(target, spec) is False
    # fails closed with no model configured
    assert await AIApprover(NullLLM()).approve(target, spec) is False


async def test_ai_approver_fails_closed_on_llm_error() -> None:
    class BoomLLM(LLMClient):
        async def complete(self, prompt: str, *, system: str | None = None) -> str:
            raise RuntimeError("api down")

    target = TargetPolicy(name="web", probe={"type": "systemd", "params": {"unit": "x.service"}})
    spec = RemediationSpec(type="restart", params={"unit": "x.service"})
    assert await AIApprover(BoomLLM()).approve(target, spec) is False


def test_forecast_already_over_threshold_returns_zero() -> None:
    assert forecast_threshold_crossing([(0.0, 95.0), (1.0, 96.0)], 90.0) == 0.0
