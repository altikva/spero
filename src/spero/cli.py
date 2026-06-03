"""The `spero` command line. Typer for structure, rich for output, questionary
for the human-in-the-loop approvals on gated remediations."""

from __future__ import annotations

import asyncio
import os

import questionary
import typer
from rich.console import Console
from rich.table import Table
from sqlalchemy import Engine as SAEngine

from spero import __version__
from spero.ai import (
    AIApprover,
    NullLLM,
    diagnose_failure,
    forecast_threshold_crossing,
    nl_query,
    parse_pct,
)
from spero.ai.llm import LLMClient
from spero.config import settings
from spero.core.engine import ActionStatus, Engine, TargetOutcome, deny_all
from spero.core.models import Autonomy, RemediationSpec, TargetPolicy
from spero.core.policy import load_policy
from spero.probes import build_probe
from spero.providers.host import make_provider
from spero.remediations import build_remediation
from spero.store import Event, init_db, make_engine, recent_events

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
    ai_approve: bool = typer.Option(
        False, "--ai-approve", help="Let the AI approve gated remediations (agentic mode)."
    ),
    store: bool = typer.Option(True, help="Persist events to the store."),
) -> None:
    """Run one supervision cycle over the policy.

    Unattended, gated actions wait for a human by default; pass --ai-approve to let
    the configured model decide them.
    """
    p = load_policy(policy)
    approver = AIApprover(_llm()).approve if ai_approve else deny_all
    engine = Engine(p, approver=approver)
    outcomes = asyncio.run(engine.run_cycle())
    _render_outcomes(outcomes)
    if store:
        engine.persist(_store_engine())


@app.command()
def watch(
    policy: str = typer.Option(settings.policy_path, help="Path to the policy file."),
    ai_approve: bool = typer.Option(
        False, "--ai-approve", help="Let the AI approve gated remediations (agentic mode)."
    ),
    store: bool = typer.Option(True, help="Persist events to the store."),
) -> None:
    """Supervise continuously: each target on its own probe interval, until Ctrl-C."""
    p = load_policy(policy)
    asyncio.run(_run_watch(p, ai_approve=ai_approve, store=store))


async def _run_watch(policy_obj: object, *, ai_approve: bool, store: bool) -> None:
    import signal

    from spero.core.models import Policy
    from spero.core.watch import watch as watch_loop

    assert isinstance(policy_obj, Policy)
    approver = AIApprover(_llm()).approve if ai_approve else deny_all
    engine = Engine(policy_obj, approver=approver)
    store_engine = _store_engine() if store else None

    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, stop.set)
        except NotImplementedError:  # e.g. Windows
            pass

    mode = "agentic" if ai_approve else "human-gated"
    console.print(
        f"[green]spero watching[/] {len(policy_obj.targets)} target(s) ({mode}) - Ctrl-C to stop"
    )
    await watch_loop(engine, policy_obj, store_engine=store_engine, on_outcome=_log_outcome)
    console.print("[dim]stopped[/]")


def _log_outcome(outcome: TargetOutcome) -> None:
    # Quiet on the happy path; a daemon should only speak when something matters.
    action = outcome.action
    noteworthy = {ActionStatus.applied, ActionStatus.failed, ActionStatus.awaiting_approval}
    if outcome.healthy and not (action and action.status in noteworthy):
        return
    when = _now()
    if not outcome.healthy:
        suffix = ""
        if action:
            style = _STATUS_STYLE.get(action.status, "white")
            suffix = f" [{style}]{action.remediation}:{action.status.value}[/]"
        console.print(f"[dim]{when}[/] [red]{outcome.target} down[/]: {outcome.detail}{suffix}")
    elif action:
        console.print(
            f"[dim]{when}[/] [green]{outcome.target} ok[/] ({action.remediation} cleared)"
        )


def _now() -> str:
    from datetime import datetime

    return datetime.now().strftime("%H:%M:%S")


@app.command()
def ask(
    question: str = typer.Argument(..., help="A question about what Spero has seen."),
) -> None:
    """Ask a natural-language question over the recorded event history."""
    docs = [_format_event(e) for e in _events()]
    console.print(asyncio.run(nl_query(question, docs, _llm())))


@app.command()
def diagnose(target: str = typer.Argument(..., help="Target to diagnose.")) -> None:
    """LLM-assisted root-cause sketch for a target, from its recent events."""
    events = _events(target=target)
    if not events:
        console.print(f"[dim]no recorded events for {target}[/]")
        return
    detail = next((e.detail for e in events if e.kind == "probe_fail"), events[0].detail)
    recent = [_format_event(e) for e in reversed(events[:20])]  # oldest-last
    console.print(asyncio.run(diagnose_failure(target, detail, recent, _llm())))


@app.command()
def forecast(
    target: str = typer.Argument(..., help="A disk target to forecast."),
    threshold: int = typer.Option(90, help="Usage percent to forecast crossing."),
) -> None:
    """Forecast when a disk target will cross a usage threshold (linear trend)."""
    samples: list[tuple[float, float]] = []
    for e in _events(target=target):
        pct = parse_pct(e.detail)
        if pct is not None and e.created_at is not None:
            samples.append((e.created_at.timestamp(), float(pct)))
    samples.sort()
    eta = forecast_threshold_crossing(samples, threshold)
    if eta is None:
        console.print(f"[dim]{target}: not trending toward {threshold}% (or too few samples)[/]")
    else:
        console.print(f"{target}: ~{eta / 3600:.1f}h until {threshold}% ({len(samples)} samples)")


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


def _llm() -> LLMClient:
    """Use Claude when a key and the optional dep are present, else the no-op model."""
    if os.environ.get("ANTHROPIC_API_KEY"):
        try:
            from spero.ai import AnthropicLLM

            return AnthropicLLM()
        except ImportError:
            console.print("[dim]anthropic not installed; falling back to NullLLM[/]")
    return NullLLM()


def _store_engine() -> SAEngine:
    engine = make_engine(settings.database_url)
    init_db(engine)
    return engine


def _events(*, target: str | None = None, limit: int = 200) -> list[Event]:
    return recent_events(_store_engine(), target=target, limit=limit)


def _format_event(e: Event) -> str:
    when = e.created_at.strftime("%Y-%m-%d %H:%M") if e.created_at else "?"
    return f"{when} {e.kind} {e.target}: {e.detail}"


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
