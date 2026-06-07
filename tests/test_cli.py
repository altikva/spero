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

from spero import __version__
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
    # Branded landing screen: version/tagline line and the Examples panel.
    assert __version__ in result.output
    assert "Examples" in result.output


def test_help_flag_exits_zero() -> None:
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    assert "self-healing supervision agent" in result.output


def test_version_subcommand_still_runs() -> None:
    result = runner.invoke(app, ["version"])
    assert result.exit_code == 0
    assert "spero" in result.output.lower()


def test_subcommand_prints_banner_header_on_stderr() -> None:
    # Every command gets the banner header (like cgh), but on stderr -- so stdout
    # stays clean and parseable (`spero version` prints just the version string).
    result = runner.invoke(app, ["version"])
    assert result.exit_code == 0
    assert result.stdout.strip() == f"spero {__version__}"
    assert "|___/" in result.stderr  # the ascii banner went to stderr


def test_top_dashboard_render() -> None:
    # The `spero top` live dashboard renders the target grid + event feed off pure
    # data (no loop, no live terminal), so it is testable directly.
    from rich.console import Console

    from spero.core.engine import ActionOutcome, ActionStatus, TargetOutcome
    from spero.core.models import Policy, ProbeSpec, TargetPolicy
    from spero.dashboard import _render_top
    from spero.store.models import Event

    policy = Policy(
        targets=[
            TargetPolicy(
                name="nginx",
                provider="local",
                probe=ProbeSpec(type="systemd", params={"unit": "nginx.service"}),
            )
        ]
    )
    outcomes = [
        TargetOutcome(
            "nginx", False, "inactive", 2, ActionOutcome("restart", ActionStatus.applied, "ok")
        )
    ]
    events = [Event(node="local", target="nginx", kind="probe_fail", detail="[2] inactive")]

    console = Console(width=120)
    with console.capture() as cap:
        console.print(_render_top(policy, outcomes, events))
    out = cap.get()
    assert "spero top" in out
    assert f"v{__version__}" in out  # version shown in the header
    assert "nginx" in out
    assert "restart:applied" in out
    assert "recent events" in out


def test_top_key_handler() -> None:
    # Pure single-key dispatch for `spero top`: pause, freeze, approve, quit.
    from spero.core.engine import ActionOutcome, ActionStatus, TargetOutcome
    from spero.core.models import Policy, ProbeSpec, TargetPolicy
    from spero.dashboard import _handle_key, _TopState

    policy = Policy(
        targets=[
            TargetPolicy(
                name="nginx",
                provider="local",
                probe=ProbeSpec(type="systemd", params={"unit": "nginx.service"}),
            )
        ]
    )
    state = _TopState()

    _handle_key("p", state, policy)
    assert state.paused is True
    _handle_key("p", state, policy)
    assert state.paused is False

    assert policy.frozen is False
    _handle_key("f", state, policy)
    assert policy.frozen is True

    # 'a' approves only targets currently awaiting approval
    state.outcomes = [
        TargetOutcome(
            "nginx", False, "down", 2, ActionOutcome("restart", ActionStatus.applied, "")
        ),
    ]
    _handle_key("a", state, policy)
    assert state.approved == set()  # applied != awaiting_approval

    state.outcomes = [
        TargetOutcome(
            "nginx", False, "down", 2, ActionOutcome("restart", ActionStatus.awaiting_approval, "")
        ),
    ]
    _handle_key("a", state, policy)
    assert "nginx" in state.approved

    _handle_key("q", state, policy)
    assert state.quit is True

    _handle_key("z", state, policy)  # unknown key is a no-op


def test_render_remote_from_json() -> None:
    # `spero top --remote` renders purely from the /status + /events JSON.
    from rich.console import Console

    from spero.dashboard import _render_remote

    status = {
        "frozen": True,
        "targets": [
            {
                "target": "orders",
                "provider": "k8s:/orders",
                "probe": "keda-scaledobject",
                "healthy": False,
                "failures": 3,
                "detail": "autoscaling paused",
                "action": {
                    "remediation": "keda-unpause",
                    "status": "awaiting_approval",
                    "detail": "",
                },
            }
        ],
    }
    events = [{"target": "orders", "kind": "probe_fail", "detail": "autoscaling paused"}]
    console = Console(width=120)
    with console.capture() as cap:
        console.print(_render_remote(status, events, server_version="9.9.9"))
    out = cap.get()
    assert "remote" in out
    assert "server v9.9.9" in out  # the observed spero's version
    assert "orders" in out
    assert "DOWN" in out
    assert "keda-unpause:awaiting_approval" in out
    assert "action freeze ON" in out
