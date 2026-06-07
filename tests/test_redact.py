# -#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#
# __creation__ = 2026-06-07
# __author__ = "jndjama (Joy Ndjama)"
# __copyright__ = "Copyright 2026 ALTIKVA."
# __licence__ = "MIT & CC BY-NC-SA (https://www.altikva.com/licenses/LICENSE-1.0)"
# -#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#
# Description: Tests for ai.redact: secret/PII scrubbing before LLM egress.

"""Tests for spero.ai.redact.redact."""

from __future__ import annotations

import pytest

from spero.ai.redact import redact


@pytest.mark.parametrize(
    "secret",
    [
        "Authorization: Bearer abc123.DEF-456_ghi",
        "password=hunter2supersecret",
        "api_key: sk-livesomethinglongenough1234",
        "AKIAIOSFODNN7EXAMPLE",
        "deadbeefdeadbeefdeadbeefdeadbeef0123",  # 36 hex chars
        "user@example.com",
        "eyJhbGciOi.JhbGciOiJIUzI1NiIsInR5.cCI6IkpXVCJ9abc",  # jwt-ish
    ],
)
def test_redact_scrubs_secrets(secret: str) -> None:
    out = redact(f"log line before {secret} and after")
    assert "[REDACTED]" in out or "[EMAIL]" in out
    # the raw secret token must not survive verbatim
    raw = secret.split(":")[-1].split("=")[-1].strip()
    assert raw not in out


def test_redact_leaves_ordinary_text_alone() -> None:
    text = "nginx.service inactive (exit code 3) after 2 failures"
    assert redact(text) == text
