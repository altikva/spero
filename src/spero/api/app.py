"""FastAPI application factory.

Phase 0 ships a health endpoint and a policy view so the control plane is real
and testable. Phase 1 adds the resource routers (nodes, events, targets, heal).
"""

from __future__ import annotations

from fastapi import FastAPI

from spero import __version__
from spero.config import settings
from spero.core.policy import load_policy


def create_app() -> FastAPI:
    app = FastAPI(
        title="Spero",
        version=__version__,
        summary="Self-healing supervision agent for Linux hosts and Kubernetes.",
    )

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok", "version": __version__}

    @app.get("/targets")
    def targets() -> dict[str, object]:
        policy = load_policy(settings.policy_path)
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


app = create_app()
