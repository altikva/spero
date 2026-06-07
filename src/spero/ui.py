# -#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#
# __creation__ = 2026-06-07
# __author__ = "jndjama (Joy Ndjama)"
# __copyright__ = "Copyright 2026 ALTIKVA."
# __licence__ = "MIT & CC BY-NC-SA (https://www.altikva.com/licenses/LICENSE-1.0)"
# -#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#
# Description: Shared presentation constants for the CLI banner and the dashboards
#              (banner art, status->color map, event->color map, grid columns).

"""Shared presentation constants for `spero`'s terminal UIs.

The rich.Live dashboard (cli/dashboard) and the Textual dashboard (tui) render the
same target grid and event feed, so the banner art, the action-status color map,
the event-kind color map, and the column headers live here once. Keeping them in a
single module is what stops the two dashboards from drifting apart.
"""

from __future__ import annotations

from spero.core.engine import ActionStatus

# figlet "Standard" spero banner. Used as the CLI landing/header art and at the top
# of the Textual dashboard.
BANNER = (
    " ___ _ __   ___ _ __ ___\n"
    "/ __| '_ \\ / _ \\ '__/ _ \\\n"
    "\\__ \\ |_) |  __/ | | (_) |\n"
    "|___/ .__/ \\___|_|  \\___/\n"
    "    |_|"
)

# Action status -> rich color, shared by both dashboards.
STATUS_STYLE = {
    ActionStatus.applied: "green",
    ActionStatus.failed: "red",
    ActionStatus.frozen: "yellow",
    ActionStatus.suggested: "cyan",
    ActionStatus.awaiting_approval: "magenta",
    ActionStatus.waiting: "dim",
}

# Target-grid column headers, in order.
COLUMNS = ("Target", "Provider", "Probe", "Health", "Fails", "Action", "Detail")


def event_style(kind: str) -> str:
    """rich color for an event kind (probe_fail/remediation/error/info)."""
    return {"probe_fail": "red", "remediation": "yellow", "error": "red", "info": "green"}.get(
        kind, "dim"
    )
