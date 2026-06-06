# -#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#
# __creation__ = 2026-06-03
# __author__ = "jndjama (Joy Ndjama)"
# __copyright__ = "Copyright 2026 ALTIKVA."
# __licence__ = "MIT & CC BY-NC-SA (https://www.altikva.com/licenses/LICENSE-1.0)"
# -#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#
# Description: FastAPI application factory.

"""FastAPI application factory.

Phase 0 ships a health endpoint and a policy view so the control plane is real
and testable. Phase 1 adds the resource routers (nodes, events, targets, heal).
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import TYPE_CHECKING

import yaml
from fastapi import FastAPI, HTTPException
from pydantic import ValidationError

from spero import __version__
from spero.config import Settings
from spero.config import settings as default_settings
from spero.core.policy import load_policy

if TYPE_CHECKING:
    from spero.api.supervisor import Supervisor


def create_app(settings: Settings | None = None, supervisor: Supervisor | None = None) -> FastAPI:
    """Build the control-plane app.

    With a ``supervisor`` attached (what ``spero serve`` does), the app drives the
    supervision loop in the background and serves its live state at /status and
    /events. Without one, those endpoints return 503 (the plain `uvicorn
    spero.api.app:app` import target is a static policy view only).
    """
    settings = settings or default_settings

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        if supervisor is not None:
            await supervisor.start()
        try:
            yield
        finally:
            if supervisor is not None:
                await supervisor.stop()

    app = FastAPI(
        title="Spero",
        version=__version__,
        summary="Self-healing supervision agent for Linux hosts and Kubernetes.",
        lifespan=lifespan,
    )

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok", "version": __version__}

    @app.get("/status")
    def status() -> dict[str, object]:
        if supervisor is None:
            raise HTTPException(503, "not supervising; run `spero serve`")
        return supervisor.status()

    @app.get("/events")
    def events(limit: int = 50) -> dict[str, object]:
        if supervisor is None:
            raise HTTPException(503, "not supervising; run `spero serve`")
        return {"events": supervisor.events(limit)}

    @app.get("/targets")
    def targets() -> dict[str, object]:
        try:
            policy = load_policy(settings.policy_path)
        except FileNotFoundError as exc:
            raise HTTPException(503, f"policy file not found: {settings.policy_path}") from exc
        except (yaml.YAMLError, ValidationError) as exc:
            raise HTTPException(422, f"invalid policy: {exc}") from exc
        return {
            "frozen": policy.frozen,
            "targets": [
                {
                    "name": t.name,
                    "provider": t.provider,
                    "probe": t.probe.type,
                    "remediations": [r.type for r in t.remediations],
                }
                for t in policy.targets
            ],
        }

    return app


# Module-level instance for uvicorn's "spero.api.app:app" import target.
app = create_app()
