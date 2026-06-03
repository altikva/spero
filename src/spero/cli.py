"""The `spero` command line. Typer for structure, rich for output, questionary
for the human-in-the-loop approvals on gated remediations."""

from __future__ import annotations

import asyncio

import questionary
import typer
from rich.console import Console
from rich.table import Table

from spero import __version__
from spero.config import settings
from spero.core.engine import ActionStatus, Engine, TargetOutcome
from spero.core.models import Autonomy, RemediationSpec, TargetPolicy
from spero.core.policy import load_policy
from spero.probes import build_probe
from spero.providers.host import make_provider
from spero.remediations import build_remediation

app = typer.Typer(add_completion=False, help="Spero - self-healing supervision agent.")
console = Console()

_STATUS_STYLE = {
    ActionStatus.applied: "green",
    ActionStatus.failed: "red",
    ActionStatus.frozen: "yellow",
    ActionStatus.suggested: "cyan",
    ActionStatus.awaiting_approval: "magenta",
    ActionStatus.waiting: "dim",
}


@app.command()
def version() -> None:
    """Show the Spero version."""
    console.print(f"[bold]spero[/] {__version__}")


@app.command()
def status(
    policy: str = typer.Option(settings.policy_path, help="Path to the policy file."),
) -> None:
    """Show the supervised targets declared in a policy."""
    p = load_policy(policy)
    if p.frozen:
        console.print("[yellow]action freeze is ON - no remediations will run[/]")
    table = Table(title="Spero targets")
    table.add_column("Target", style="bold")
    table.add_column("Provider")
    table.add_column("Probe")
    table.add_column("Autonomy")
    for t in p.targets:
        autonomy = ", ".join(sorted({r.autonomy.value for r in t.remediations})) or "-"
        table.add_row(t.name, t.provider, t.probe.type, autonomy)
    console.print(table)


@app.command()
def run(
    policy: str = typer.Option(settings.policy_path, help="Path to the policy file."),
) -> None:
    """Run one supervision cycle over the policy (unattended; gated actions wait)."""
    p = load_policy(policy)
    engine = Engine(p)
    outcomes = asyncio.run(engine.run_cycle())
    _render_outcomes(outcomes)


@app.command()
def heal(
    target: str = typer.Argument(..., help="Target name to heal."),
    policy: str = typer.Option(settings.policy_path, help="Path to the policy file."),
    yes: bool = typer.Option(False, "--yes", "-y", help="Approve all actions without prompting."),
) -> None:
    """Probe one target and, if unhealthy, walk its remediations with approval prompts."""
    p = load_policy(policy)
    tp = next((t for t in p.targets if t.name == target), None)
    if tp is None:
        console.print(f"[red]no such target:[/] {target}")
        raise typer.Exit(1)
    if p.frozen:
        console.print("[yellow]action freeze is ON - refusing to heal[/]")
        raise typer.Exit(1)
    asyncio.run(_heal_target(tp, assume_yes=yes))


async def _heal_target(tp: TargetPolicy, *, assume_yes: bool) -> None:
    provider = make_provider(tp.provider)
    result = await build_probe(tp.probe).check(provider)
    if result.healthy:
        console.print(f"[green]{tp.name} is healthy[/]: {result.detail}")
        return
    console.print(f"[red]{tp.name} is unhealthy[/]: {result.detail}")
    for spec in tp.remediations:
        if not await _approve(tp, spec, assume_yes=assume_yes):
            console.print(f"  [dim]skipped {spec.type}[/]")
            continue
        res = await build_remediation(spec).apply(provider)
        style = "green" if res.success else "red"
        console.print(f"  [{style}]{spec.type}: {res.detail}[/]")
        if res.success:
            return
    console.print("[yellow]no remediation succeeded[/]")


async def _approve(tp: TargetPolicy, spec: RemediationSpec, *, assume_yes: bool) -> bool:
    if spec.autonomy is Autonomy.suggest:
        # suggest still asks here: an explicit `heal` is a human deciding to act.
        pass
    if assume_yes:
        return True
    answer = await questionary.confirm(
        f"Apply {spec.type} to {tp.name} (autonomy={spec.autonomy.value})?", default=False
    ).ask_async()
    return bool(answer)


@app.command()
def serve(
    host: str = typer.Option(settings.host, help="Bind address."),
    port: int = typer.Option(settings.port, help="Bind port."),
) -> None:
    """Run the control-plane API."""
    import uvicorn

    uvicorn.run("spero.api.app:app", host=host, port=port)


def _render_outcomes(outcomes: list[TargetOutcome]) -> None:
    table = Table(title="Spero cycle")
    table.add_column("Target", style="bold")
    table.add_column("Health")
    table.add_column("Fails", justify="right")
    table.add_column("Action")
    table.add_column("Detail")
    for o in sorted(outcomes, key=lambda x: x.target):
        health = "[green]ok[/]" if o.healthy else "[red]down[/]"
        if o.action is None:
            action = "-"
        else:
            style = _STATUS_STYLE.get(o.action.status, "white")
            action = f"[{style}]{o.action.remediation}:{o.action.status.value}[/]"
        table.add_row(o.target, health, str(o.failures), action, o.detail)
    console.print(table)


def main() -> None:
    app()


if __name__ == "__main__":
    main()
