"""The FastAPI control plane. Replaces the bot's Flask agent.py + api/ resources."""

from spero.api.app import app, create_app

__all__ = ["app", "create_app"]
