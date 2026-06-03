"""FastAPI application factory.

Phase 0 ships a health endpoint and a policy view so the control plane is real
and testable. Phase 1 adds the resource routers (nodes, events, targets, heal).
"""

from __future__ import annotations

import yaml
from fastapi import FastAPI, HTTPException
from pydantic import ValidationError

from spero import __version__
from spero.config import Settings
from spero.config import settings as default_settings
from spero.core.policy import load_policy


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or default_settings
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
