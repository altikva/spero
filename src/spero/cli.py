"""The `spero` command line. Typer for structure, rich for output."""

from __future__ import annotations

import typer
from rich.console import Console
from rich.table import Table

from spero import __version__
from spero.config import settings
from spero.core.policy import load_policy

app = typer.Typer(add_completion=False, help="Spero - self-healing supervision agent.")
console = Console()


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
def serve(
    host: str = typer.Option(settings.host, help="Bind address."),
    port: int = typer.Option(settings.port, help="Bind port."),
) -> None:
    """Run the control-plane API."""
    import uvicorn

    uvicorn.run("spero.api.app:app", host=host, port=port)


def main() -> None:
    app()


if __name__ == "__main__":
    main()
