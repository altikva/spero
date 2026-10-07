# -#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#
# __creation__ = 2026-06-03
# __author__ = "jndjama (Joy Ndjama)"
# __copyright__ = "Copyright 2026 ALTIKVA."
# __licence__ = "MIT & CC BY-NC-SA (https://www.altikva.com/licenses/LICENSE-1.0)"
# -#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#
# Description: Load and validate Spero policy files (YAML).

"""Load and validate Spero policy files (YAML)."""

from __future__ import annotations

from pathlib import Path

import yaml
from pydantic import ValidationError

from spero.core.models import Policy


def load_policy(path: str | Path) -> Policy:
    """Parse a YAML policy file into a validated Policy."""
    data = yaml.safe_load(Path(path).read_text()) or {}
    return Policy.model_validate(data)


def load_policy_str(text: str) -> Policy:
    """Parse a YAML policy from a string (used in tests and the API)."""
    return Policy.model_validate(yaml.safe_load(text) or {})


class PolicyReloadError(Exception):
    """The policy file changed but cannot be loaded; the running policy stays in force."""


class PolicyReloader:
    """Reloads a policy file for a running supervisor, on request or when it changes.

    ``poll()`` returns a new Policy when there is one to apply and None otherwise.
    With ``on_change`` it also notices edits by comparing the file's signature
    (mtime, size, inode) and only reads once that signature has held for two polls
    in a row: a file written through a shell redirection is truncated first, and a
    truncated YAML list can still validate with fewer targets. An empty file is
    rejected for the same reason. ``poll(force=True)`` (SIGHUP) reads at once.
    """

    def __init__(self, path: str | Path, *, on_change: bool = False) -> None:
        self.path = Path(path)
        self.on_change = on_change
        self._loaded = self._signature()  # what the running policy was read from
        self._seen = self._loaded  # what the previous poll saw

    def _signature(self) -> tuple[int, int, int] | None:
        try:
            st = self.path.stat()
        except OSError:
            return None
        return st.st_mtime_ns, st.st_size, st.st_ino

    def poll(self, *, force: bool = False) -> Policy | None:
        sig = self._signature()
        if not force:
            settled = sig == self._seen
            self._seen = sig
            if not self.on_change or sig == self._loaded or not settled:
                return None
        # Mark these bytes as handled even if they fail, so a bad file is reported
        # once and not on every poll. The next edit changes the signature again.
        self._seen = self._loaded = sig
        try:
            text = self.path.read_text()
            if not text.strip():
                raise PolicyReloadError(f"{self.path} is empty")
            return load_policy_str(text)
        except (OSError, yaml.YAMLError, ValidationError) as exc:
            raise PolicyReloadError(f"{self.path}: {exc}") from exc
