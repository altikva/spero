# -#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#
# __creation__ = 2026-06-05
# __author__ = "jndjama (Joy Ndjama)"
# __copyright__ = "Copyright 2026 ALTIKVA."
# __licence__ = "MIT & CC BY-NC-SA (https://www.altikva.com/licenses/LICENSE-1.0)"
# -#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#
# Description: Tests for the Textual spero top app (skipped when textual is absent).

"""Tests for the Textual `spero top` app; skipped when the tui extra is not installed."""

from __future__ import annotations

import pytest

from spero.core.models import Policy, ProbeSpec, TargetPolicy

pytest.importorskip("textual")


def _policy() -> Policy:
    return Policy(
        targets=[
            TargetPolicy(
                name="nginx",
                provider="local",
                probe=ProbeSpec(type="systemd", params={"unit": "nginx.service"}),
            )
        ]
    )


async def test_app_mounts_and_keys_work() -> None:
    from spero.tui import SperoTopApp

    app = SperoTopApp(_policy(), interval=999, store=False)
    async with app.run_test() as pilot:
        await pilot.pause()
        from textual.widgets import DataTable

        table = app.query_one("#targets", DataTable)
        assert table.row_count == 1  # one target row

        assert app.policy.frozen is False
        await pilot.press("f")
        assert app.policy.frozen is True

        assert app.paused is False
        await pilot.press("p")
        assert app.paused is True

        await pilot.press("q")
