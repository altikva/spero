# -#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#
# __creation__ = 2026-06-04
# __author__ = "jndjama (Joy Ndjama)"
# __copyright__ = "Copyright 2026 ALTIKVA."
# __licence__ = "MIT & CC BY-NC-SA (https://www.altikva.com/licenses/LICENSE-1.0)"
# -#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#
# Description: Tests for the spero CLI entrypoint: bare invocation shows help and exits 0.

"""Tests for the spero CLI entrypoint: bare invocation shows help and exits 0."""

from __future__ import annotations

from typer.testing import CliRunner

from spero.cli import app

runner = CliRunner()


def test_bare_invocation_shows_help_and_exits_zero() -> None:
    # The point of the no-args callback: greet with help, exit 0 (like cgh),
    # rather than the Typer default "Missing command" usage error (exit 2).
    result = runner.invoke(app, [])
    assert result.exit_code == 0
    # CliRunner renders the prog name as "root"; the installed entry point is `spero`.
    assert "Usage:" in result.output
    assert "Commands" in result.output


def test_help_flag_exits_zero() -> None:
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    assert "self-healing supervision agent" in result.output


def test_version_subcommand_still_runs() -> None:
    result = runner.invoke(app, ["version"])
    assert result.exit_code == 0
    assert "spero" in result.output.lower()
