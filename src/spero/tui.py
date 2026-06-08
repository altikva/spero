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

from collections.abc import AsyncIterator, Callable
from datetime import datetime
from typing import TYPE_CHECKING, ClassVar

from rich.text import Text
from textual.app import App, ComposeResult
from textual.binding import Binding, BindingType
from textual.screen import ModalScreen
from textual.widgets import DataTable, Footer, RichLog, Static, TextArea
from textual.worker import Worker

from spero import __version__
from spero.core.engine import ActionStatus, Engine
from spero.core.models import Policy, RemediationSpec, TargetPolicy
from spero.ui import BANNER as _BANNER
from spero.ui import COLUMNS as _COLUMNS
from spero.ui import STATUS_STYLE as _STATUS_STYLE
from spero.ui import event_style as _event_style

if TYPE_CHECKING:
    import httpx

_DASH_CSS = """
#banner { height: auto; color: $accent; padding: 0 1; }
#status { height: 1; padding: 0 1; }
#targets { height: 2fr; }
#events { height: 1fr; border: round $panel-darken-1; padding: 0 1; }
"""


class InspectScreen(ModalScreen[None]):
    """A scrollable, read-only view of a target's object YAML (q / esc to close)."""

    BINDINGS: ClassVar[list[BindingType]] = [
        Binding("escape", "close", "close"),
        Binding("q", "close", "close"),
    ]
    CSS = """
    InspectScreen { align: center middle; }
    InspectScreen TextArea { width: 90%; height: 90%; border: round $accent; }
    """

    def __init__(self, title: str, yaml_text: str) -> None:
        super().__init__()
        self._title = title
        self._yaml = yaml_text

    def compose(self) -> ComposeResult:
        area = TextArea(self._yaml, read_only=True, show_line_numbers=True)
        area.border_title = f" {self._title} "
        yield area

    def action_close(self) -> None:
        self.dismiss()


class FollowScreen(ModalScreen[None]):
    """A live, scrolling `kubectl logs -f` follow (q / esc to close).

    Takes a ``source`` callable returning an async iterator of log lines (local via
    core.inspect.stream_logs, remote via the /logs/{name}/stream SSE endpoint). The
    pump worker is cancelled on close so the underlying stream is torn down.
    """

    BINDINGS: ClassVar[list[BindingType]] = [
        Binding("escape", "close", "close"),
        Binding("q", "close", "close"),
    ]
    CSS = """
    FollowScreen { align: center middle; }
    FollowScreen RichLog { width: 90%; height: 90%; border: round $accent; }
    """

    def __init__(self, title: str, source: Callable[[], AsyncIterator[str]]) -> None:
        super().__init__()
        self._title = title
        self._source = source
        self._worker: Worker[None] | None = None

    def compose(self) -> ComposeResult:
        log = RichLog(highlight=False, markup=False, wrap=True)
        log.border_title = f" {self._title} "
        yield log

    def on_mount(self) -> None:
        self._worker = self.run_worker(self._pump(), exclusive=True, group="follow")

    async def _pump(self) -> None:
        log = self.query_one(RichLog)
        try:
            async for line in self._source():
                log.write(line)
        except Exception as exc:  # surface the failure in the pane, do not crash the app
            log.write(f"[error] {exc}")

    def action_close(self) -> None:
        if self._worker is not None:
            self._worker.cancel()
        self.dismiss()


class SperoTopApp(App[None]):
    """Live supervision dashboard with selection, mouse, and scrollback."""

    TITLE = "spero top"
    CSS = _DASH_CSS
    # Show "ctrl+p palette" in the footer instead of the cryptic "^p" (clearer on macOS).
    COMMAND_PALETTE_DISPLAY = "ctrl+p"
    BINDINGS: ClassVar[list[BindingType]] = [
        Binding("q", "quit", "quit"),
        Binding("p", "pause", "pause"),
        Binding("r", "refresh", "refresh"),
        Binding("a", "approve", "approve selected"),
        Binding("f", "freeze", "toggle freeze"),
        Binding("i", "inspect", "inspect yaml"),
        Binding("l", "logs", "logs"),
        Binding("L", "follow", "follow logs"),
        Binding("s", "shell", "connect"),
    ]

    def __init__(self, policy: Policy, *, interval: float, store: bool) -> None:
        super().__init__()
        self.policy = policy
        self.interval = interval
        self.engine = Engine(policy, approver=self._approve, approver_name="human")
        self.store_engine = _make_store_engine() if store else None
        self.paused = False
        self.approved: set[str] = set()
        self.latest: dict[str, object] = {}
        self._event_cursor = 0
        self._cols: list = []

    async def _approve(self, target: TargetPolicy, spec: RemediationSpec) -> bool:
        return target.name in self.approved

    def compose(self) -> ComposeResult:
        yield Static(_BANNER, id="banner")
        yield Static(id="status")
        yield DataTable(id="targets", cursor_type="row", zebra_stripes=True)
        yield RichLog(id="events", markup=True, highlight=False, wrap=True)
        yield Footer()

    def on_mount(self) -> None:
        table = self.query_one("#targets", DataTable)
        self._cols = table.add_columns(*_COLUMNS)
        for t in self.policy.targets:
            # Literal Text cells so the auto-highlighter does not underline path/url
            # tokens (e.g. k8s:/orders) as if they were links.
            table.add_row(
                Text(t.name),
                Text(t.provider),
                Text(t.probe.type),
                Text("..."),
                Text(""),
                Text(""),
                Text(""),
                key=t.name,
            )
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
            table.update_cell(o.target, self._cols[4], Text(str(o.failures) if o.failures else ""))
            table.update_cell(o.target, self._cols[5], action)
            table.update_cell(o.target, self._cols[6], Text(o.detail))

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
            f"[bold cyan]spero top[/] [dim]v{__version__}[/]"
            f"  {len(self.policy.targets)} target(s){flag}"
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

    def action_inspect(self) -> None:
        table = self.query_one("#targets", DataTable)
        if table.row_count:
            self._open_inspect(
                str(table.coordinate_to_cell_key(table.cursor_coordinate).row_key.value)
            )

    def on_data_table_row_selected(self, event: DataTable.RowSelected) -> None:
        self._open_inspect(str(event.row_key.value))

    def _selected(self) -> str | None:
        table = self.query_one("#targets", DataTable)
        if not table.row_count:
            return None
        return str(table.coordinate_to_cell_key(table.cursor_coordinate).row_key.value)

    def _target(self, name: str) -> TargetPolicy | None:
        return next((t for t in self.policy.targets if t.name == name), None)

    def _open_inspect(self, name: str) -> None:
        self.run_worker(self._inspect(name), exclusive=False, group="inspect")

    async def _inspect(self, name: str) -> None:
        from spero.core.inspect import object_yaml

        target = self._target(name)
        if target is None:
            return
        try:
            text = await object_yaml(target)
        except LookupError as exc:
            text = f"# {exc}"
        except Exception as exc:
            text = f"# error fetching {name}:\n# {exc}"
        self.push_screen(InspectScreen(name, text))

    def action_logs(self) -> None:
        name = self._selected()
        if name is not None:
            self.run_worker(self._logs(name), exclusive=False, group="logs")

    async def _logs(self, name: str) -> None:
        from spero.core.inspect import object_logs

        target = self._target(name)
        if target is None:
            return
        try:
            text = await object_logs(target)
        except LookupError as exc:
            text = f"# {exc}"
        except Exception as exc:
            text = f"# error fetching logs for {name}:\n# {exc}"
        self.push_screen(InspectScreen(f"logs: {name}", text))

    def action_shell(self) -> None:
        name = self._selected()
        if name is not None:
            self.run_worker(self._shell(name), exclusive=False, group="shell")

    async def _shell(self, name: str) -> None:
        """Local convenience: open a session into the target with your own tools.

        kubectl exec for a pod, ssh for a host, a local shell for a local target.
        """
        import subprocess

        from spero.core.shell import connect_argv

        target = self._target(name)
        if target is None:
            return
        try:
            argv = await connect_argv(target)
        except LookupError as exc:
            self.notify(str(exc), severity="warning")
            return
        except Exception as exc:
            self.notify(f"connect setup failed: {exc}", severity="error")
            return
        with self.suspend():
            try:
                # argv is your local kubectl/ssh/shell invocation (no shell string).
                subprocess.run(argv)
            except (OSError, subprocess.SubprocessError) as exc:
                # The terminal is restored under suspend(), so a plain print is correct here.
                print(f"connect failed: {exc}")
        self.notify(f"left session on {name}")

    def action_follow(self) -> None:
        name = self._selected()
        target = self._target(name) if name is not None else None
        if name is None or target is None:
            return
        from spero.core.inspect import stream_logs

        self.push_screen(FollowScreen(f"logs -f: {name}", lambda: stream_logs(target)))


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


class SperoRemoteApp(App[None]):
    """Observe a remote spero by polling its /status + /events (mouse, selection, scroll)."""

    TITLE = "spero top (remote)"
    CSS = _DASH_CSS
    COMMAND_PALETTE_DISPLAY = "ctrl+p"
    BINDINGS: ClassVar[list[BindingType]] = [
        Binding("q", "quit", "quit"),
        Binding("r", "refresh", "refresh"),
        Binding("p", "pause", "pause"),
        Binding("i", "inspect", "inspect yaml"),
        Binding("l", "logs", "logs"),
        Binding("L", "follow", "follow logs"),
    ]

    def __init__(self, url: str, *, interval: float, token: str = "") -> None:
        super().__init__()
        self.url = url
        self.interval = interval
        self.token = token
        self.paused = False
        self._client: httpx.AsyncClient | None = None
        self._cols: list = []
        self._rows: set[str] = set()
        self._server_version = ""  # the observed spero's version, from /health

    def compose(self) -> ComposeResult:
        yield Static(_BANNER, id="banner")
        yield Static(id="status")
        yield DataTable(id="targets", cursor_type="row", zebra_stripes=True)
        yield RichLog(id="events", markup=True, highlight=False, wrap=True)
        yield Footer()

    def on_mount(self) -> None:
        import httpx

        headers = {"Authorization": f"Bearer {self.token}"} if self.token else None
        self._client = httpx.AsyncClient(base_url=self.url, timeout=5.0, headers=headers)
        self._cols = self.query_one("#targets", DataTable).add_columns(*_COLUMNS)
        self._update_status(connected=True)
        self.set_interval(self.interval, self._tick)
        self._tick()

    def _tick(self) -> None:
        self.run_worker(self._poll(), exclusive=True, group="poll")

    async def _poll(self) -> None:
        if self.paused or self._client is None:
            return
        try:
            if not self._server_version:  # learn the remote's version once
                health = (await self._client.get("/health")).json()
                self._server_version = str(health.get("version", ""))
            status = (await self._client.get("/status")).raise_for_status().json()
            body = (await self._client.get("/events")).raise_for_status().json()
        except Exception as exc:
            self._update_status(connected=False, error=str(exc))
            return
        self._repaint(status)
        self._repaint_events(body.get("events", []))
        self._update_status(connected=True, frozen=bool(status.get("frozen")))

    def _repaint(self, status: dict) -> None:
        table = self.query_one("#targets", DataTable)
        for t in status.get("targets", []):
            name = str(t.get("target", ""))
            healthy = t.get("healthy")
            if healthy is None:
                health = Text("...", style="dim")
            else:
                health = (
                    Text("healthy", style="green") if healthy else Text("DOWN", style="bold red")
                )
            a = t.get("action")
            if a:
                try:
                    style = _STATUS_STYLE.get(ActionStatus(a["status"]), "white")
                except ValueError:
                    style = "white"
                action = Text(f"{a['remediation']}:{a['status']}", style=style)
            else:
                action = Text("")
            fails = str(t.get("failures") or "") if t.get("failures") else ""
            # Literal Text so the auto-highlighter does not underline path/url tokens.
            cells = [
                Text(name),
                Text(str(t.get("provider", ""))),
                Text(str(t.get("probe", ""))),
                health,
                Text(fails),
                action,
                Text(str(t.get("detail", ""))),
            ]
            if name in self._rows:
                for col, val in zip(self._cols, cells, strict=True):
                    table.update_cell(name, col, val)
            else:
                table.add_row(*cells, key=name)
                self._rows.add(name)

    def _repaint_events(self, events: list[dict]) -> None:
        log = self.query_one("#events", RichLog)
        log.clear()
        for e in events[-50:]:
            log.write(
                f"[dim]{e.get('target', '')}[/] "
                f"[{_event_style(e.get('kind', ''))}]{e.get('kind', '')}[/] {e.get('detail', '')}"
            )

    def _update_status(self, *, connected: bool, frozen: bool = False, error: str = "") -> None:
        tag = ""
        if self.paused:
            tag += "  [yellow]PAUSED[/]"
        if frozen:
            tag += "  [yellow]FROZEN[/]"
        if not connected:
            tag += f"  [red]unreachable: {error}[/]"
        ver = f" [dim]server v{self._server_version}[/]" if self._server_version else ""
        self.query_one("#status", Static).update(
            f"[bold cyan]spero top[/] [dim]remote {self.url}[/]{ver}{tag}"
            f"  [dim]{datetime.now():%H:%M:%S}[/]"
        )

    async def on_unmount(self) -> None:
        if self._client is not None:
            await self._client.aclose()

    def action_pause(self) -> None:
        self.paused = not self.paused
        self._update_status(connected=True)

    def action_refresh(self) -> None:
        self._tick()

    def action_inspect(self) -> None:
        table = self.query_one("#targets", DataTable)
        if table.row_count:
            self._open_inspect(
                str(table.coordinate_to_cell_key(table.cursor_coordinate).row_key.value)
            )

    def on_data_table_row_selected(self, event: DataTable.RowSelected) -> None:
        self._open_inspect(str(event.row_key.value))

    def _open_inspect(self, name: str) -> None:
        self.run_worker(self._fetch_inspect(name), exclusive=False, group="inspect")

    async def _fetch_inspect(self, name: str) -> None:
        if self._client is None:
            return
        try:
            resp = await self._client.get(f"/objects/{name}")
            text = (
                resp.json().get("yaml", "")
                if resp.status_code == 200
                else (f"# {name}: HTTP {resp.status_code}\n# {resp.text}")
            )
        except Exception as exc:
            text = f"# error fetching {name}:\n# {exc}"
        self.push_screen(InspectScreen(name, text))

    def action_logs(self) -> None:
        table = self.query_one("#targets", DataTable)
        if table.row_count:
            name = str(table.coordinate_to_cell_key(table.cursor_coordinate).row_key.value)
            self.run_worker(self._fetch_logs(name), exclusive=False, group="logs")

    async def _fetch_logs(self, name: str) -> None:
        if self._client is None:
            return
        try:
            resp = await self._client.get(f"/logs/{name}")
            text = (
                resp.json().get("logs", "")
                if resp.status_code == 200
                else (f"# {name}: HTTP {resp.status_code}\n# {resp.text}")
            )
        except Exception as exc:
            text = f"# error fetching logs for {name}:\n# {exc}"
        self.push_screen(InspectScreen(f"logs: {name}", text))

    def action_follow(self) -> None:
        table = self.query_one("#targets", DataTable)
        if table.row_count:
            name = str(table.coordinate_to_cell_key(table.cursor_coordinate).row_key.value)
            self.push_screen(
                FollowScreen(f"logs -f: {name}", lambda: self._remote_log_stream(name))
            )

    async def _remote_log_stream(self, name: str) -> AsyncIterator[str]:
        if self._client is None:
            return
        async with self._client.stream("GET", f"/logs/{name}/stream") as resp:
            if resp.status_code != 200:
                yield f"# {name}: HTTP {resp.status_code}"
                return
            async for raw in resp.aiter_lines():
                if raw.startswith("data: "):
                    yield raw[len("data: ") :]


def run_remote_app(url: str, *, interval: float, token: str = "") -> None:
    """Run the Textual remote dashboard against a spero control plane (blocking)."""
    SperoRemoteApp(url, interval=interval, token=token).run()
