# -#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#
# __creation__ = 2026-06-07
# __author__ = "jndjama (Joy Ndjama)"
# __copyright__ = "Copyright 2026 ALTIKVA."
# __licence__ = "MIT & CC BY-NC-SA (https://www.altikva.com/licenses/LICENSE-1.0)"
# -#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#
# Description: Best-effort scrubbing of secrets from text before it leaves the
#              process for the LLM (ask / diagnose). Opt-in via SPERO_REDACT_EVENTS.

"""Best-effort secret redaction for text sent to the LLM.

Event details can carry command output that includes secrets, and `spero ask` /
`spero diagnose` send that text to the model. When SPERO_REDACT_EVENTS is on, the
CLI runs event text through :func:`redact` first. This is a coarse safety net, not
a guarantee: it errs toward over-redaction (a redacted secret is cheap, a leaked
one is not), and it does not replace keeping real secrets out of logs.
"""

from __future__ import annotations

import re

_PLACEHOLDER = "[REDACTED]"

# Ordered most-specific first. Each pattern maps a match to its replacement.
_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    # JWTs (header.payload.signature)
    (re.compile(r"eyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+"), _PLACEHOLDER),
    # Authorization: Bearer <token>
    (re.compile(r"(?i)(bearer)\s+[A-Za-z0-9._\-+/=]+"), r"\1 " + _PLACEHOLDER),
    # key=value / key: value for secret-ish keys
    (
        re.compile(
            r"(?i)\b(password|passwd|pwd|secret|token|api[_-]?key|access[_-]?key|"
            r"private[_-]?key|client[_-]?secret)\b\s*[=:]\s*\S+"
        ),
        r"\1=" + _PLACEHOLDER,
    ),
    # AWS access key id
    (re.compile(r"\bAKIA[0-9A-Z]{16}\b"), _PLACEHOLDER),
    # Email addresses
    (re.compile(r"\b[\w.+-]+@[\w-]+\.[\w.-]+\b"), "[EMAIL]"),
    # Long hex blobs (hashes, hex-encoded keys)
    (re.compile(r"\b[A-Fa-f0-9]{32,}\b"), _PLACEHOLDER),
    # Long base64-ish blobs (likely keys/tokens)
    (re.compile(r"\b[A-Za-z0-9+/]{40,}={0,2}\b"), _PLACEHOLDER),
]


def redact(text: str) -> str:
    """Return ``text`` with likely secrets and PII replaced by placeholders."""
    for pattern, replacement in _PATTERNS:
        text = pattern.sub(replacement, text)
    return text
