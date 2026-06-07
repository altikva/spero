# -#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#
# __creation__ = 2026-06-08
# __author__ = "jndjama (Joy Ndjama)"
# __copyright__ = "Copyright 2026 ALTIKVA."
# __licence__ = "MIT & CC BY-NC-SA (https://www.altikva.com/licenses/LICENSE-1.0)"
# -#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#
# Description: Render the README screenshots (assets/*.svg) from the real rich
#              renderers with representative data. Run: uv run python scripts/gen_screenshots.py

"""Regenerate the README dashboard screenshots as self-contained SVGs.

Uses rich's SVG exporter on spero's own renderers (dashboard._render_top /
_render_remote, the cycle table, the CLI landing) with representative sample data,
so the images stay faithful to the actual UI. Re-run after a UI change.
"""

from __future__ import annotations

from pathlib import Path

from rich.console import Console, Group
from rich.panel import Panel
from rich.table import Table

from spero import __version__
from spero.cli import _EXAMPLES
from spero.core.engine import ActionOutcome, ActionStatus, TargetOutcome
from spero.core.models import Policy, ProbeSpec, TargetPolicy
from spero.dashboard import _render_remote, _render_top
from spero.store.models import Event
from spero.ui import BANNER, STATUS_STYLE

ASSETS = Path(__file__).resolve().parent.parent / "assets"


def _save(renderable: object, name: str, *, title: str, width: int = 100) -> None:
    console = Console(record=True, width=width)
    console.print(renderable)
    (ASSETS / name).write_text(console.export_svg(title=title))
    print(f"wrote assets/{name}")


def _policy() -> Policy:
    return Policy(
        targets=[
            TargetPolicy(
                name="orders-api",
                provider="k8s:/orders",
                probe=ProbeSpec(type="deployment", params={"name": "orders"}),
            ),
            TargetPolicy(
                name="checkout",
                provider="k8s:/shop",
                probe=ProbeSpec(type="pod", params={"selector": "app=checkout"}),
            ),
            TargetPolicy(
                name="nginx",
                provider="local",
                probe=ProbeSpec(type="systemd", params={"unit": "nginx.service"}),
            ),
            TargetPolicy(
                name="disk-root",
                provider="ssh:web-01",
                probe=ProbeSpec(type="disk", params={"path": "/", "threshold_pct": 90}),
            ),
        ]
    )


def _outcomes() -> list[TargetOutcome]:
    return [
        TargetOutcome("orders-api", True, "3/3 available", 0),
        TargetOutcome(
            "checkout",
            False,
            "1/2 ready for 'app=checkout'",
            2,
            ActionOutcome("rollout-restart", ActionStatus.applied, "restarted"),
        ),
        TargetOutcome(
            "nginx",
            False,
            "inactive (dead)",
            1,
            ActionOutcome("restart", ActionStatus.awaiting_approval, ""),
        ),
        TargetOutcome("disk-root", True, "/ at 71%", 0),
    ]


def _events() -> list[Event]:
    return [
        Event(
            node="k8s:/shop",
            target="checkout",
            kind="probe_fail",
            detail="[2] 1/2 ready for 'app=checkout'",
        ),
        Event(
            node="k8s:/shop",
            target="checkout",
            kind="remediation",
            detail="rollout-restart: restarted [approved by ai]",
        ),
        Event(node="local", target="nginx", kind="probe_fail", detail="[1] inactive (dead)"),
        Event(
            node="local", target="nginx", kind="remediation", detail="awaiting approval: restart"
        ),
    ]


def _status_dict() -> dict:
    return {
        "frozen": False,
        "targets": [
            {
                "target": "orders-api",
                "provider": "k8s:/orders",
                "probe": "deployment",
                "healthy": True,
                "failures": 0,
                "detail": "3/3 available",
                "action": None,
            },
            {
                "target": "checkout",
                "provider": "k8s:/shop",
                "probe": "pod",
                "healthy": False,
                "failures": 2,
                "detail": "1/2 ready for 'app=checkout'",
                "action": {"remediation": "rollout-restart", "status": "applied", "detail": ""},
            },
            {
                "target": "payments",
                "provider": "k8s:/shop",
                "probe": "knative-service",
                "healthy": True,
                "failures": 0,
                "detail": "Ready, scaled-to-zero (idle)",
                "action": None,
            },
        ],
    }


def _remote_events() -> list[dict]:
    return [
        {"target": "checkout", "kind": "probe_fail", "detail": "[2] 1/2 ready"},
        {
            "target": "checkout",
            "kind": "remediation",
            "detail": "rollout-restart: restarted [approved by owner]",
        },
        {"target": "payments", "kind": "info", "detail": "recovered: Ready"},
    ]


def _cycle_table() -> Table:
    table = Table(title="Spero cycle")
    table.add_column("Target", style="bold")
    table.add_column("Health")
    table.add_column("Fails", justify="right")
    table.add_column("Action")
    table.add_column("Detail")
    for o in _outcomes():
        health = "[green]ok[/]" if o.healthy else "[red]down[/]"
        if o.action is None:
            action = "-"
        else:
            style = STATUS_STYLE.get(o.action.status, "white")
            action = f"[{style}]{o.action.remediation}:{o.action.status.value}[/]"
        table.add_row(o.target, health, str(o.failures), action, o.detail)
    return table


def _landing() -> Group:
    tagline = (
        f"  [bold]v{__version__}[/]  ---  Self-healing supervision agent for Linux and Kubernetes\n"
    )
    return Group(
        f"[bold cyan]{BANNER}[/]",
        tagline,
        Panel(_EXAMPLES, title="Examples", border_style="dim", expand=False),
    )


def main() -> None:
    _save(_render_top(_policy(), _outcomes(), _events()), "spero-top.svg", title="spero top")
    _save(
        _render_remote(_status_dict(), _remote_events(), server_version=__version__),
        "spero-top-remote.svg",
        title="spero top --remote",
    )
    _save(_cycle_table(), "spero-run.svg", title="spero run", width=88)
    _save(_landing(), "spero-cli.svg", title="spero", width=78)


if __name__ == "__main__":
    main()
