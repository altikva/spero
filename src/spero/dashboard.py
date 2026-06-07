# -#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#
# __creation__ = 2026-06-07
# __author__ = "jndjama (Joy Ndjama)"
# __copyright__ = "Copyright 2026 ALTIKVA."
# __licence__ = "MIT & CC BY-NC-SA (https://www.altikva.com/licenses/LICENSE-1.0)"
# -#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#
# Description: The rich.Live `spero top` dashboard (fallback when the tui extra is
#              absent): local and --remote renderers, the run loops, and the
#              cbreak single-key reader. The Textual UI (tui.py) is the richer path.

"""The rich.Live fallback for `spero top`.

`spero top` uses the Textual UI (tui.py) when the optional ``tui`` extra is
installed; this module is what it falls back to otherwise, so the command always
works. It renders the same target grid + event feed (local via an engine, remote
via a spero's /status + /events), and reads single keys in cbreak mode: q quit,
p pause, r refresh, plus f/a locally. Shared colors/columns come from spero.ui.
"""

from __future__ import annotations

import asyncio
import os
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from rich.console import Console, Group, RenderableType
from rich.panel import Panel
from rich.table import Table

from spero import __version__
from spero.core.engine import ActionStatus, Engine, TargetOutcome
from spero.core.models import Policy, RemediationSpec, TargetPolicy
from spero.store import Event, init_db, make_engine
from spero.ui import STATUS_STYLE, event_style

console = Console()

_TOP_KEYS = (
    "[bold]q[/] quit   [bold]p[/] pause   [bold]r[/] refresh   "
    "[bold]a[/] approve gated   [bold]f[/] toggle freeze"
)


def _now() -> str:
    return datetime.now().strftime("%H:%M:%S")


def _store_engine() -> object:
    from spero.config import settings

    engine = make_engine(settings.database_url)
    init_db(engine)
    return engine


def _render_top(
    policy_obj: object,
    outcomes: list[TargetOutcome],
    events: list[Event],
    paused: bool = False,
) -> Group:
    assert isinstance(policy_obj, Policy)
    frozen = " [yellow](action freeze ON)[/]" if policy_obj.frozen else ""
    pause_tag = " [yellow](paused)[/]" if paused else ""
    header = Panel(
        f"[bold cyan]spero top[/] [dim]v{__version__}[/]"
        f"  {len(policy_obj.targets)} target(s){frozen}{pause_tag}"
        f"  [dim]{_now()}[/]\n{_TOP_KEYS}",
        border_style="cyan",
    )

    table = Table(expand=True)
    table.add_column("Target", style="bold")
    table.add_column("Provider")
    table.add_column("Probe")
    table.add_column("Health")
    table.add_column("Fails", justify="right")
    table.add_column("Action")
    table.add_column("Detail", overflow="fold")
    by_name = {o.target: o for o in outcomes}
    for t in policy_obj.targets:
        o = by_name.get(t.name)
        if o is None:  # first paint, before the first cycle returns
            table.add_row(t.name, t.provider, t.probe.type, "[dim]...[/]", "", "", "")
            continue
        health = "[green]healthy[/]" if o.healthy else "[red]DOWN[/]"
        action = ""
        if o.action is not None:
            style = STATUS_STYLE.get(o.action.status, "white")
            action = f"[{style}]{o.action.remediation}:{o.action.status.value}[/]"
        fails = str(o.failures) if o.failures else ""
        table.add_row(t.name, t.provider, t.probe.type, health, fails, action, o.detail)

    feed = (
        "\n".join(
            f"[dim]{e.target}[/] [{event_style(e.kind)}]{e.kind}[/] {e.detail}"
            for e in events[-12:]
        )
        or "[dim]no events yet[/]"
    )
    return Group(header, table, Panel(feed, title="recent events", border_style="dim"))


def _render_remote(status: dict, events: list[dict], server_version: str = "") -> Group:
    """Render the dashboard from a remote spero's /status + /events JSON."""
    targets = status.get("targets") or []
    frozen = " [yellow](action freeze ON)[/]" if status.get("frozen") else ""
    ver = f" [dim]server v{server_version}[/]" if server_version else ""
    header = Panel(
        f"[bold cyan]spero top[/] [dim]remote[/]{ver}  {len(targets)} target(s){frozen}"
        f"  [dim]{_now()}[/]",
        border_style="cyan",
    )
    table = Table(expand=True)
    table.add_column("Target", style="bold")
    table.add_column("Provider")
    table.add_column("Probe")
    table.add_column("Health")
    table.add_column("Fails", justify="right")
    table.add_column("Action")
    table.add_column("Detail", overflow="fold")
    for t in targets:
        healthy = t.get("healthy")
        if healthy is None:
            health = "[dim]...[/]"
        else:
            health = "[green]healthy[/]" if healthy else "[red]DOWN[/]"
        action = ""
        a = t.get("action")
        if a:
            try:
                style = STATUS_STYLE.get(ActionStatus(a["status"]), "white")
            except ValueError:
                style = "white"
            action = f"[{style}]{a['remediation']}:{a['status']}[/]"
        fails = str(t.get("failures") or "") if t.get("failures") else ""
        table.add_row(
            str(t.get("target", "")),
            str(t.get("provider", "")),
            str(t.get("probe", "")),
            health,
            fails,
            action,
            str(t.get("detail", "")),
        )
    feed = (
        "\n".join(
            f"[dim]{e.get('target', '')}[/] "
            f"[{event_style(e.get('kind', ''))}]{e.get('kind', '')}[/] {e.get('detail', '')}"
            for e in events[-12:]
        )
        or "[dim]no events[/]"
    )
    return Group(header, table, Panel(feed, title="recent events", border_style="dim"))


@dataclass
class _TopState:
    """Mutable dashboard state driven by single-key commands."""

    paused: bool = False
    quit: bool = False
    approved: set[str] = field(default_factory=set)
    outcomes: list[TargetOutcome] = field(default_factory=list)


def _handle_key(key: str, state: _TopState, policy_obj: object) -> None:
    """Apply one keypress to the dashboard state (pure; no terminal/engine I/O)."""
    assert isinstance(policy_obj, Policy)
    key = key.lower()
    if key == "q":
        state.quit = True
    elif key == "p":
        state.paused = not state.paused
    elif key == "f":
        policy_obj.frozen = not policy_obj.frozen
    elif key == "a":
        # Approve every target currently awaiting approval; the approver consults this
        # set on the next cycle, so the gated remediation fires then.
        state.approved |= {
            o.target
            for o in state.outcomes
            if o.action is not None and o.action.status is ActionStatus.awaiting_approval
        }


async def _wait_first(events: list[asyncio.Event], timeout: float | None) -> None:
    """Return when any event fires or the timeout elapses, cancelling the rest."""
    tasks = [asyncio.ensure_future(e.wait()) for e in events]
    try:
        await asyncio.wait(tasks, timeout=timeout, return_when=asyncio.FIRST_COMPLETED)
    finally:
        for t in tasks:
            t.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)


async def run_top(policy_obj: object, *, interval: float, store: bool) -> None:
    """Supervise locally on a timer and render the rich.Live dashboard."""
    import signal

    from rich.live import Live

    assert isinstance(policy_obj, Policy)
    state = _TopState()
    store_engine = _store_engine() if store else None

    async def _approve(target: TargetPolicy, spec: RemediationSpec) -> bool:
        return target.name in state.approved

    engine = Engine(policy_obj, approver=_approve, approver_name="human")

    stop = asyncio.Event()
    wake = asyncio.Event()  # any keypress wakes the loop so the UI reacts promptly
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, stop.set)
        except NotImplementedError:  # e.g. Windows
            signal.signal(sig, lambda *_: loop.call_soon_threadsafe(stop.set))

    def _dispatch(ch: str) -> None:
        _handle_key(ch, state, policy_obj)
        wake.set()

    fd = _start_keyreader(loop, _dispatch)
    try:
        initial: RenderableType = _render_top(policy_obj, [], [])
        with Live(initial, console=console, screen=True, auto_refresh=False) as live:
            while not state.quit and not stop.is_set():
                if not state.paused:
                    state.outcomes = await engine.run_cycle()
                    # One-shot approvals: forget targets whose action just applied.
                    state.approved -= {
                        o.target
                        for o in state.outcomes
                        if o.action is not None and o.action.status is ActionStatus.applied
                    }
                    if store_engine is not None:
                        await engine.persist(store_engine)
                live.update(
                    _render_top(policy_obj, state.outcomes, engine.events, state.paused),
                    refresh=True,
                )
                wake.clear()
                await _wait_first([stop, wake], timeout=None if state.paused else interval)
    finally:
        _stop_keyreader(loop, fd)


async def run_top_remote(url: str, *, interval: float, token: str = "") -> None:
    """Poll a remote spero's control plane and render its live state.

    The rich.Live fallback for when the `tui` extra is absent. Keys: q quit, r
    refresh now, p pause. (With the `tui` extra, `top --remote` uses the Textual
    app instead, which adds mouse and scrollback.)
    """
    import signal

    import httpx
    from rich.live import Live

    headers = {"Authorization": f"Bearer {token}"} if token else None

    stop = asyncio.Event()
    wake = asyncio.Event()
    paused = {"on": False}  # boxed so the key handler can mutate it
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, stop.set)
        except NotImplementedError:  # e.g. Windows
            signal.signal(sig, lambda *_: loop.call_soon_threadsafe(stop.set))

    def _on_key(ch: str) -> None:
        c = ch.lower()
        if c == "q":
            stop.set()
        elif c == "p":
            paused["on"] = not paused["on"]
        wake.set()  # r (or any key) wakes the loop to repaint/refetch

    fd = _start_keyreader(loop, _on_key)
    try:
        async with httpx.AsyncClient(base_url=url, timeout=5.0, headers=headers) as client:
            server_version = ""
            with Live(
                Panel(f"connecting to {url} ..."), console=console, screen=True, auto_refresh=False
            ) as live:
                while not stop.is_set():
                    if not paused["on"]:
                        try:
                            if not server_version:  # learn the remote's version once
                                health = (await client.get("/health")).json()
                                server_version = str(health.get("version", ""))
                            status = (await client.get("/status")).raise_for_status().json()
                            body = (await client.get("/events")).raise_for_status().json()
                            renderable: RenderableType = _render_remote(
                                status, body.get("events", []), server_version
                            )
                        except Exception as exc:
                            renderable = Panel(
                                f"[red]cannot reach {url}[/]\n{exc}", border_style="red"
                            )
                        live.update(renderable, refresh=True)
                    wake.clear()
                    await _wait_first([stop, wake], timeout=interval)
    finally:
        _stop_keyreader(loop, fd)


_KEYREADER_STATE: dict[int, Any] = {}


def _start_keyreader(loop: asyncio.AbstractEventLoop, on_key: Callable[[str], None]) -> int | None:
    """Put stdin in cbreak mode and dispatch single keys to ``on_key``. Returns the fd.

    Returns None when stdin is not a TTY (piped / CI): the dashboard still auto-refreshes
    and Ctrl-C still quits, there is just nothing to read keys from.
    """
    import sys

    if not sys.stdin.isatty():
        return None
    import termios
    import tty

    fd = sys.stdin.fileno()
    _KEYREADER_STATE[fd] = termios.tcgetattr(fd)
    tty.setcbreak(fd)  # leaves ISIG on, so Ctrl-C still raises SIGINT

    def _readable() -> None:
        try:
            data = os.read(fd, 1)
        except OSError:
            return
        if data:
            on_key(data.decode(errors="ignore"))

    loop.add_reader(fd, _readable)
    return fd


def _stop_keyreader(loop: asyncio.AbstractEventLoop, fd: int | None) -> None:
    if fd is None:
        return
    import termios

    loop.remove_reader(fd)
    old = _KEYREADER_STATE.pop(fd, None)
    if old is not None:
        termios.tcsetattr(fd, termios.TCSADRAIN, old)
