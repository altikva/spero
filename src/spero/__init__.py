# -#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#
# __creation__ = 2026-06-03
# __author__ = "jndjama (Joy Ndjama)"
# __copyright__ = "Copyright 2026 ALTIKVA."
# __licence__ = "Apache-2.0 (https://www.apache.org/licenses/LICENSE-2.0)"
# -#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#
# Description: Spero — a self-healing supervision agent for Linux hosts and Kubernetes.

"""Spero — a self-healing supervision agent for Linux hosts and Kubernetes.

Spero watches the things you run (processes, services, disks, workloads),
notices when they break, and heals them under policy-governed autonomy.
Shipped under Altikva.
"""

from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("spero")  # single source of truth: the installed package version
except PackageNotFoundError:  # running from a source tree that was never installed
    __version__ = "0.0.0+unknown"
__author__ = "Joy Ndjama"

__all__ = ["__author__", "__version__"]
