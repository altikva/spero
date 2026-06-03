"""Providers: WHERE things run. A provider executes commands against a target.

The host provider (local + SSH) ports the bot's remote/connexion command layer.
The Kubernetes provider arrives in Phase 2 behind the same interface.
"""

from spero.providers.base import Provider
from spero.providers.command import CommandResult, run_local, run_local_async
from spero.providers.host import LocalProvider, SSHProvider, make_provider

__all__ = [
    "CommandResult",
    "LocalProvider",
    "Provider",
    "SSHProvider",
    "make_provider",
    "run_local",
    "run_local_async",
]
