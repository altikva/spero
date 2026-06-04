# -#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#
# __creation__ = 2026-06-03
# __author__ = "jndjama (Joy Ndjama)"
# __copyright__ = "Copyright 2026 ALTIKVA."
# __licence__ = "MIT & CC BY-NC-SA (http://www.altikva.com/licenses/LICENSE-1.0)"
# -#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#

"""Providers: WHERE things run. A provider executes commands against a target.

The host provider (local + SSH) ports the bot's remote/connexion command layer.
The Kubernetes provider arrives in Phase 2 behind the same interface.
"""

from spero.providers.base import Provider
from spero.providers.command import CommandResult, run_local, run_local_async
from spero.providers.host import LocalProvider, SSHProvider, make_provider, parse_provider_spec
from spero.providers.kubernetes import KubernetesProvider

__all__ = [
    "CommandResult",
    "KubernetesProvider",
    "LocalProvider",
    "Provider",
    "SSHProvider",
    "make_provider",
    "parse_provider_spec",
    "run_local",
    "run_local_async",
]
