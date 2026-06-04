# -#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#
# __creation__ = 2026-06-03
# __author__ = "jndjama (Joy Ndjama)"
# __copyright__ = "Copyright 2026 ALTIKVA."
# __licence__ = "MIT & CC BY-NC-SA (http://www.altikva.com/licenses/LICENSE-1.0)"
# -#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#
# Description: Bad policies must fail at load, not mid-remediation.

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


def test_unknown_probe_type_rejected_at_load() -> None:
    with pytest.raises(ValidationError):
        load_policy_str("targets:\n  - {name: x, probe: {type: nope}}")


def test_bad_remediation_params_rejected_at_load() -> None:
    # `restart` requires a `unit`; a typo'd/missing param must fail at load, not mid-heal.
    with pytest.raises(ValidationError):
        load_policy_str(
            """
            targets:
              - name: web
                probe: {type: systemd, params: {unit: nginx.service}}
                remediations:
                  - {type: restart, params: {untit: nginx.service}}
            """
        )


def test_duplicate_target_names_rejected() -> None:
    with pytest.raises(ValidationError, match="duplicate target names"):
        load_policy_str(
            """
            targets:
              - {name: web, probe: {type: systemd, params: {unit: a.service}}}
              - {name: web, probe: {type: systemd, params: {unit: b.service}}}
            """
        )


def test_destructive_remediation_cannot_be_auto() -> None:
    # rotate deletes files -> autonomy 'auto' must be rejected at load
    with pytest.raises(ValidationError, match="destructive"):
        load_policy_str(
            """
            targets:
              - name: disk
                probe: {type: disk, params: {path: /data}}
                remediations:
                  - {type: rotate, params: {path: /data/logs}, autonomy: auto}
            """
        )


def test_destructive_remediation_gated_is_allowed() -> None:
    p = load_policy_str(
        """
        targets:
          - name: disk
            probe: {type: disk, params: {path: /data}}
            remediations:
              - {type: rotate, params: {path: /data/logs}, autonomy: gated}
        """
    )
    assert p.targets[0].remediations[0].type == "rotate"


def test_decreasing_max_attempts_rejected() -> None:
    with pytest.raises(ValidationError, match="non-decreasing"):
        load_policy_str(
            """
            targets:
              - name: web
                probe: {type: systemd, params: {unit: nginx.service}}
                remediations:
                  - {type: restart, params: {unit: nginx.service}, max_attempts: 5}
                  - {type: kill, params: {name: nginx}, max_attempts: 2}
            """
        )
