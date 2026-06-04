# -#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#
# __creation__ = 2026-06-03
# __author__ = "jndjama (Joy Ndjama)"
# __copyright__ = "Copyright 2026 ALTIKVA."
# __licence__ = "MIT & CC BY-NC-SA (http://www.altikva.com/licenses/LICENSE-1.0)"
# -#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#

"""Tests for the ported local command executor."""

from __future__ import annotations

import sys
from pathlib import Path

from spero.providers.command import TIMEOUT_RC, CommandResult, run_local


def _py(code: str) -> list[str]:
    return [sys.executable, "-c", code]


def test_success_captures_stdout() -> None:
    r = run_local(_py("print('hello')"))
    assert isinstance(r, CommandResult)
    assert r.ok
    assert r.returncode == 0
    assert "hello" in r.stdout


def test_nonzero_returncode() -> None:
    r = run_local(_py("import sys; sys.exit(3)"))
    assert not r.ok
    assert r.returncode == 3


def test_stderr_captured() -> None:
    r = run_local(_py("import sys; sys.stderr.write('boom')"))
    assert "boom" in r.stderr


def test_timeout_returns_conventional_code() -> None:
    r = run_local(_py("import time; time.sleep(5)"), timeout=0.2)
    assert r.returncode == TIMEOUT_RC
    assert "timed out" in r.stderr


def test_string_command_is_tokenized() -> None:
    r = run_local("echo spero")
    assert r.ok
    assert "spero" in r.stdout


def test_retries_until_success(tmp_path: Path) -> None:
    counter = tmp_path / "n"
    code = (
        f"import pathlib; p = pathlib.Path({str(counter)!r}); "
        "n = int(p.read_text()) if p.exists() else 0; "
        "p.write_text(str(n + 1)); "
        "import sys; sys.exit(0 if n >= 2 else 1)"
    )
    r = run_local(_py(code), retries=3)
    assert r.ok
    # failed on attempts 0 and 1, succeeded on attempt 2 -> stopped, no 4th try
    assert int(counter.read_text()) == 3
