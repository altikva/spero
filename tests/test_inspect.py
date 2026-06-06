# -#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#
# __creation__ = 2026-06-06
# __author__ = "jndjama (Joy Ndjama)"
# __copyright__ = "Copyright 2026 ALTIKVA."
# __licence__ = "MIT & CC BY-NC-SA (https://www.altikva.com/licenses/LICENSE-1.0)"
# -#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#
# Description: Tests for probe object_ref() and the YAML-inspect helper.

"""Tests for Probe.object_ref() and core.inspect.object_yaml."""

from __future__ import annotations

import pytest

from spero.core.models import ProbeSpec, TargetPolicy
from spero.probes import build_probe


@pytest.mark.parametrize(
    ("ptype", "params", "expected"),
    [
        ("deployment", {"name": "x"}, ["deployment", "x"]),
        ("pod", {"selector": "app=x"}, ["pods", "-l", "app=x"]),
        ("keda-scaledobject", {"name": "x"}, ["scaledobject", "x"]),
        ("elpio-service", {"name": "x"}, ["elpioservice.elpio.io", "x"]),
        ("elpio-function", {"name": "x"}, ["elpiofunction.elpio.io", "x"]),
        ("elpio-task", {"name": "x"}, ["elpiotask.elpio.io", "x"]),
        ("knative-service", {"name": "x"}, ["ksvc", "x"]),
        ("resource-usage", {"selector": "app=x"}, ["pods", "-l", "app=x"]),
    ],
)
def test_object_ref(ptype: str, params: dict, expected: list[str]) -> None:
    assert build_probe(ProbeSpec(type=ptype, params=params)).object_ref() == expected


def test_host_probe_has_no_object_ref() -> None:
    probe = build_probe(ProbeSpec(type="systemd", params={"unit": "nginx.service"}))
    assert probe.object_ref() is None


async def test_object_yaml_lookuperror_for_host_target() -> None:
    from spero.core.inspect import object_yaml

    target = TargetPolicy(
        name="nginx",
        provider="local",
        probe=ProbeSpec(type="systemd", params={"unit": "nginx.service"}),
    )
    with pytest.raises(LookupError):
        await object_yaml(target)
