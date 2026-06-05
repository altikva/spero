# -#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#
# __creation__ = 2026-06-05
# __author__ = "jndjama (Joy Ndjama)"
# __copyright__ = "Copyright 2026 ALTIKVA."
# __licence__ = "MIT & CC BY-NC-SA (https://www.altikva.com/licenses/LICENSE-1.0)"
# -#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#
# Description: Textual UI for `spero top` -- a DataTable of targets with row-cursor
#              selection, mouse, and a scrollable event log; approve gated actions inline.

"""The rich-interactive `spero top` dashboard (Textual).

Optional: lives behind the ``tui`` extra. ``spero top`` imports this when textual is
installed and falls back to the rich.Live dashboard in cli.py otherwise, so the
command always works. This version adds what rich.Live cannot: row-cursor selection,
mouse, and scrollback over both the target grid and the event log. The selected
target is the one ``a`` approves.
"""

from __future__ import annotations

from datetime import datetime
from typing import ClassVar

from rich.text import Text
from textual.app import App, ComposeResult
from textual.binding import Binding, BindingType
from textual.widgets import DataTable, Footer, RichLog, Static

from spero.core.engine import ActionStatus, Engine
from spero.core.models import Policy, RemediationSpec, TargetPolicy

_STATUS_STYLE = {
    ActionStatus.applied: "green",
    ActionStatus.failed: "red",
    ActionStatus.frozen: "yellow",
    ActionStatus.suggested: "cyan",
    ActionStatus.awaiting_approval: "magenta",
    ActionStatus.waiting: "dim",
}
_COLUMNS = ("Target", "Provider", "Probe", "Health", "Fails", "Action", "Detail")


class SperoTopApp(App[None]):
    """Live supervision dashboard with selection, mouse, and scrollback."""

    TITLE = "spero top"
    CSS = """
    #status { height: 1; padding: 0 1; }
    #targets { height: 2fr; }
    #events { height: 1fr; border: round $panel-darken-1; padding: 0 1; }
    """
    BINDINGS: ClassVar[list[BindingType]] = [
        Binding("q", "quit", "quit"),
        Binding("p", "pause", "pause"),
        Binding("r", "refresh", "refresh"),
        Binding("a", "approve", "approve selected"),
        Binding("f", "freeze", "toggle freeze"),
    ]

    def __init__(self, policy: Policy, *, interval: float, store: bool) -> None:
        super().__init__()
        self.policy = policy
        self.interval = interval
        self.engine = Engine(policy, approver=self._approve)
        self.store_engine = _make_store_engine() if store else None
        self.paused = False
        self.approved: set[str] = set()
        self.latest: dict[str, object] = {}
        self._event_cursor = 0
        self._cols: list = []

    async def _approve(self, target: TargetPolicy, spec: RemediationSpec) -> bool:
        return target.name in self.approved

    def compose(self) -> ComposeResult:
        yield Static(id="status")
        yield DataTable(id="targets", cursor_type="row", zebra_stripes=True)
        yield RichLog(id="events", markup=True, highlight=False, wrap=True)
        yield Footer()

    def on_mount(self) -> None:
        table = self.query_one("#targets", DataTable)
        self._cols = table.add_columns(*_COLUMNS)
        for t in self.policy.targets:
            table.add_row(t.name, t.provider, t.probe.type, "...", "", "", "", key=t.name)
        self._update_status()
        self.set_interval(self.interval, self._tick)
        self._tick()  # first cycle immediately

    def _tick(self) -> None:
        self.run_worker(self._cycle(), exclusive=True, group="cycle")

    async def _cycle(self) -> None:
        if self.paused:
            return
        outcomes = await self.engine.run_cycle()
        self.latest = {o.target: o for o in outcomes}
        self.approved -= {
            o.target
            for o in outcomes
            if o.action is not None and o.action.status is ActionStatus.applied
        }
        if self.store_engine is not None:
            await self.engine.persist(self.store_engine)

        table = self.query_one("#targets", DataTable)
        for o in outcomes:
            health = Text("healthy", style="green") if o.healthy else Text("DOWN", style="bold red")
            if o.action is not None:
                style = _STATUS_STYLE.get(o.action.status, "white")
                action = Text(f"{o.action.remediation}:{o.action.status.value}", style=style)
            else:
                action = Text("")
            table.update_cell(o.target, self._cols[3], health)
            table.update_cell(o.target, self._cols[4], str(o.failures) if o.failures else "")
            table.update_cell(o.target, self._cols[5], action)
            table.update_cell(o.target, self._cols[6], o.detail)

        self._drain_events()
        self._update_status()

    def _drain_events(self) -> None:
        log = self.query_one("#events", RichLog)
        events = self.engine.events
        if self._event_cursor > len(events):  # store flush reset the buffer
            self._event_cursor = 0
        for e in events[self._event_cursor :]:
            log.write(f"[dim]{e.target}[/] [{_event_style(e.kind)}]{e.kind}[/] {e.detail}")
        self._event_cursor = len(events)

    def _update_status(self) -> None:
        flags = []
        if self.policy.frozen:
            flags.append("[yellow]FROZEN[/]")
        if self.paused:
            flags.append("[yellow]PAUSED[/]")
        flag = ("  " + "  ".join(flags)) if flags else ""
        self.query_one("#status", Static).update(
            f"[bold cyan]spero top[/]  {len(self.policy.targets)} target(s){flag}"
            f"  [dim]{datetime.now():%H:%M:%S}[/]"
        )

    # --- key actions ---

    def action_pause(self) -> None:
        self.paused = not self.paused
        self._update_status()

    def action_freeze(self) -> None:
        self.policy.frozen = not self.policy.frozen
        self._update_status()

    def action_refresh(self) -> None:
        self._tick()

    def action_approve(self) -> None:
        table = self.query_one("#targets", DataTable)
        if table.row_count == 0:
            return
        name = str(table.coordinate_to_cell_key(table.cursor_coordinate).row_key.value)
        outcome = self.latest.get(name)
        action = getattr(outcome, "action", None)
        if action is not None and action.status is ActionStatus.awaiting_approval:
            self.approved.add(name)
            self.notify(f"approved {name}; remediation runs next cycle")
        else:
            self.notify(f"{name}: nothing awaiting approval", severity="warning")


def _event_style(kind: str) -> str:
    return {"probe_fail": "red", "remediation": "yellow", "error": "red", "info": "green"}.get(
        kind, "dim"
    )


def _make_store_engine() -> object:
    from spero.config import settings
    from spero.store import init_db, make_engine

    engine = make_engine(settings.database_url)
    init_db(engine)
    return engine


def run_top_app(policy_obj: object, *, interval: float, store: bool) -> None:
    """Run the Textual dashboard (blocking; Textual owns its own event loop)."""
    assert isinstance(policy_obj, Policy)
    SperoTopApp(policy_obj, interval=interval, store=store).run()
