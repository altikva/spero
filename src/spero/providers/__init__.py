"""Providers: WHERE things run. A provider executes commands against a target.

The host provider (local + SSH) ports the bot's remote/connexion command layer.
The Kubernetes provider arrives in Phase 2 behind the same interface.
"""

from spero.providers.base import Provider
from spero.providers.command import CommandResult, run_local
from spero.providers.host import LocalProvider, SSHProvider

__all__ = ["CommandResult", "LocalProvider", "Provider", "SSHProvider", "run_local"]
