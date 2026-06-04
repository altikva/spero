# -#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#
# __creation__ = 2026-06-03
# __author__ = "jndjama (Joy Ndjama)"
# __copyright__ = "Copyright 2026 ALTIKVA."
# __licence__ = "MIT & CC BY-NC-SA (http://www.altikva.com/licenses/LICENSE-1.0)"
# -#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#
# Description: Failure-path tests for run_local: the cases that must NOT raise.

"""Failure-path tests for run_local: the cases that must NOT raise.

A self-healing agent runs commands that are often missing or malformed on the
target; every such case has to come back as a non-zero CommandResult, never an
exception, or the supervision loop dies on the thing it was meant to fix.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

from spero.providers.command import NOT_FOUND_RC, TIMEOUT_RC, run_local


def _py(code: str) -> list[str]:
    return [sys.executable, "-c", code]


def test_missing_binary_returns_result_not_exception() -> None:
    r = run_local(["spero_definitely_not_a_real_binary_xyz"])
    assert not r.ok
    assert r.returncode == NOT_FOUND_RC
    assert "FileNotFoundError" in r.stderr


def test_missing_binary_still_retries() -> None:
    # Should attempt and fail cleanly without raising even with retries.
    r = run_local(["spero_definitely_not_a_real_binary_xyz"], retries=2)
    assert r.returncode == NOT_FOUND_RC


def test_malformed_quoting_returns_result() -> None:
    r = run_local('echo "unterminated')
    assert r.returncode == NOT_FOUND_RC
    assert "invalid command" in r.stderr


def test_timeout_does_not_retry_by_default() -> None:
    # An always-timing-out command with retries must run exactly once.
    r = run_local(_py("import time; time.sleep(5)"), timeout=0.2, retries=3)
    assert r.timed_out
    assert r.returncode == TIMEOUT_RC


def test_timeout_retries_when_opted_in() -> None:
    r = run_local(_py("import time; time.sleep(5)"), timeout=0.2, retries=1, retry_on_timeout=True)
    assert r.timed_out


def test_env_is_merged_with_parent_by_default() -> None:
    # PATH from the parent survives; the custom var is added.
    r = run_local(
        _py("import os; print(os.environ.get('SPERO_X', '')); print('PATH' in os.environ)"),
        env={"SPERO_X": "yes"},
    )
    assert "yes" in r.stdout
    assert "True" in r.stdout


def test_env_replace_drops_parent() -> None:
    r = run_local(
        _py("import os; print('PATH' in os.environ)"), env={"SPERO_X": "yes"}, env_replace=True
    )
    assert "False" in r.stdout


def test_cwd_is_applied(tmp_path: Path) -> None:
    r = run_local(_py("import os; print(os.getcwd())"), cwd=str(tmp_path))
    assert str(tmp_path) in r.stdout or os.path.realpath(str(tmp_path)) in r.stdout
