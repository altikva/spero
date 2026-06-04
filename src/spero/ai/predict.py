# -#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#
# __creation__ = 2026-06-03
# __author__ = "jndjama (Joy Ndjama)"
# __copyright__ = "Copyright 2026 ALTIKVA."
# __licence__ = "MIT & CC BY-NC-SA (http://www.altikva.com/licenses/LICENSE-1.0)"
# -#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#

"""Predictive analytics. Pure functions, no model or external service.

The cheap, high-signal half of the AI roadmap: forecast when a metric (disk usage)
will cross a threshold, and detect flapping from a health history.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from itertools import pairwise

_PCT = re.compile(r"(\d+)%")


def forecast_threshold_crossing(
    samples: Sequence[tuple[float, float]], threshold: float
) -> float | None:
    """Least-squares forecast of when a rising series reaches ``threshold``.

    ``samples`` are ``(t, value)`` points (t in any consistent unit). Returns the
    time-from-last-sample until the crossing, ``0.0`` if already past, or ``None``
    if there's too little data or the trend isn't rising toward the threshold.
    """
    if len(samples) < 2:
        return None
    if samples[-1][1] >= threshold:  # already at or over the ceiling
        return 0.0
    n = len(samples)
    sx = sum(t for t, _ in samples)
    sy = sum(v for _, v in samples)
    sxx = sum(t * t for t, _ in samples)
    sxy = sum(t * v for t, v in samples)
    denom = n * sxx - sx * sx
    if denom == 0:
        return None
    slope = (n * sxy - sx * sy) / denom
    intercept = (sy - slope * sx) / n
    if slope <= 0:  # flat or falling: not trending toward the ceiling
        return None
    t_cross = (threshold - intercept) / slope
    t_last = samples[-1][0]
    return max(0.0, t_cross - t_last)


def detect_flapping(history: Sequence[bool], max_transitions: int = 3) -> bool:
    """True if the health history flips state at least ``max_transitions`` times."""
    transitions = sum(1 for a, b in pairwise(history) if a != b)
    return transitions >= max_transitions


def parse_pct(text: str) -> int | None:
    """Pull the first percentage out of a probe detail like '/data at 73% (...)'."""
    m = _PCT.search(text)
    return int(m.group(1)) if m else None
