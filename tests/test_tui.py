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


async def test_logs_opens_a_screen() -> None:
    from spero.tui import InspectScreen, SperoTopApp

    app = SperoTopApp(_policy(), interval=999, store=False)
    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.press("l")  # the host target has no pods; the screen shows the reason
        await app.workers.wait_for_complete()
        await pilot.pause()
        assert isinstance(app.screen, InspectScreen)
        await pilot.press("q")


async def test_follow_opens_a_screen() -> None:
    from spero.tui import FollowScreen, SperoTopApp

    app = SperoTopApp(_policy(), interval=999, store=False)
    async with app.run_test() as pilot:
        await pilot.pause()
        app.action_follow()  # host target is not streamable; the pane shows the error
        await pilot.pause()
        assert isinstance(app.screen, FollowScreen)


async def test_remote_app_renders_from_fake_api() -> None:
    # SperoRemoteApp polls /status + /events; stub its httpx client so no network.
    import httpx

    from spero.tui import SperoRemoteApp

    status = {
        "frozen": False,
        "targets": [
            {
                "target": "orders",
                "provider": "k8s:/orders",
                "probe": "deployment",
                "healthy": True,
                "failures": 0,
                "detail": "1/1 available",
                "action": None,
            }
        ],
    }

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/status":
            return httpx.Response(200, json=status)
        if request.url.path.startswith("/logs/"):
            return httpx.Response(200, json={"logs": "line one\nline two"})
        return httpx.Response(200, json={"events": []})

    app = SperoRemoteApp("http://test", interval=999)
    async with app.run_test() as pilot:
        # Replace the real client with one backed by the in-memory handler.
        app._client = httpx.AsyncClient(
            base_url="http://test", transport=httpx.MockTransport(handler)
        )
        await app._poll()
        await pilot.pause()
        table = app.query_one("#targets")
        assert table.row_count == 1
        await pilot.press("p")
        assert app.paused is True
        app.paused = False

        from spero.tui import InspectScreen

        await pilot.press("l")  # fetch /logs/orders from the mock and show it
        await app.workers.wait_for_complete()
        await pilot.pause()
        assert isinstance(app.screen, InspectScreen)
        await pilot.press("q")
