"""Load and validate Spero policy files (YAML)."""

from __future__ import annotations

from pathlib import Path

import yaml

from spero.core.models import Policy


def load_policy(path: str | Path) -> Policy:
    """Parse a YAML policy file into a validated Policy."""
    data = yaml.safe_load(Path(path).read_text()) or {}
    return Policy.model_validate(data)


def load_policy_str(text: str) -> Policy:
    """Parse a YAML policy from a string (used in tests and the API)."""
    return Policy.model_validate(yaml.safe_load(text) or {})
