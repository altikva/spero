"""Bad policies must fail at load, not mid-remediation."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from spero.core.policy import load_policy_str


def test_unknown_provider_rejected_at_load() -> None:
    with pytest.raises(ValidationError):
        load_policy_str(
            """
            targets:
              - name: redis
                provider: sssh:web-01
                probe: {type: process, params: {name: redis}}
            """
        )


def test_valid_ssh_provider_accepted() -> None:
    p = load_policy_str(
        """
        targets:
          - name: redis
            provider: ssh:ops@web-01:2222
            probe: {type: process, params: {name: redis}}
        """
    )
    assert p.targets[0].provider == "ssh:ops@web-01:2222"
