# -#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#
# __creation__ = 2026-06-05
# __author__ = "jndjama (Joy Ndjama)"
# __copyright__ = "Copyright 2026 ALTIKVA."
# __licence__ = "MIT & CC BY-NC-SA (https://www.altikva.com/licenses/LICENSE-1.0)"
# -#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#
# Description: Tests for ResourceUsageProbe -- threshold logic and the unit parsers.

"""Tests for the resource-usage probe and its CPU/memory unit parsers."""

from __future__ import annotations

import json

import pytest

from _fakes import ScriptedProvider
from spero.core.models import ProbeSpec
from spero.probes import build_probe
from spero.probes.resources import (
    ResourceUsageProbe,
    _cpu_to_millicores,
    _mem_to_bytes,
    _parse_top,
)
from spero.providers.command import CommandResult


def _pods_json(name: str, cpu: str | None, mem: str | None) -> str:
    requests: dict = {}
    if cpu is not None:
        requests["cpu"] = cpu
    if mem is not None:
        requests["memory"] = mem
    return json.dumps(
        {
            "items": [
                {
                    "metadata": {"name": name},
                    "spec": {"containers": [{"resources": {"requests": requests}}]},
                }
            ]
        }
    )


def _provider(
    top_out: str, pods_json: str, *, top_rc: int = 0, pods_rc: int = 0
) -> ScriptedProvider:
    def handler(cmd: object) -> CommandResult:
        argv = [cmd] if isinstance(cmd, str) else list(cmd)
        if "top" in argv:
            return CommandResult(top_rc, top_out, "" if top_rc == 0 else "metrics unavailable", "")
        return CommandResult(pods_rc, pods_json, "" if pods_rc == 0 else "not found", "")

    return ScriptedProvider(handler)


async def test_over_threshold_is_unhealthy() -> None:
    prov = _provider("orders-abc 800m 20Mi\n", _pods_json("orders-abc", "100m", "16Mi"))
    r = await ResourceUsageProbe("app=orders").check(prov)
    assert not r.healthy
    assert "cpu at 800%" in r.detail  # 800m / 100m


async def test_within_threshold_is_healthy() -> None:
    prov = _provider("orders-abc 50m 8Mi\n", _pods_json("orders-abc", "100m", "16Mi"))
    r = await ResourceUsageProbe("app=orders").check(prov)
    assert r.healthy
    assert "within request thresholds" in r.detail


async def test_missing_request_is_skipped() -> None:
    # No cpu request: cannot be "over" a request that does not exist; mem is fine.
    prov = _provider("orders-abc 999m 8Mi\n", _pods_json("orders-abc", None, "16Mi"))
    r = await ResourceUsageProbe("app=orders").check(prov)
    assert r.healthy


async def test_no_matching_pods_is_healthy() -> None:
    r = await ResourceUsageProbe("app=nope").check(_provider("", _pods_json("x", "1", "1Mi")))
    assert r.healthy
    assert "no pods match" in r.detail


async def test_top_failure_is_unhealthy() -> None:
    r = await ResourceUsageProbe("app=orders").check(_provider("", "", top_rc=1))
    assert not r.healthy
    assert "top failed" in r.detail


def test_cpu_parser() -> None:
    assert _cpu_to_millicores("250m") == 250
    assert _cpu_to_millicores("2") == 2000
    assert _cpu_to_millicores("1500m") == 1500


def test_mem_parser() -> None:
    assert _mem_to_bytes("64Mi") == 64 * 1024 * 1024
    assert _mem_to_bytes("1Gi") == 1024**3
    assert _mem_to_bytes("512000") == 512000


def test_top_parser_skips_short_lines() -> None:
    parsed = _parse_top("podA 100m 50Mi\ngarbage\npodB 200m 10Mi\n")
    assert set(parsed) == {"podA", "podB"}
    assert parsed["podA"] == (100.0, 50 * 1024 * 1024)


def test_registry_build() -> None:
    probe = build_probe(ProbeSpec(type="resource-usage", params={"selector": "app=orders"}))
    assert isinstance(probe, ResourceUsageProbe)


def test_bad_params_rejected() -> None:
    with pytest.raises(ValueError, match="bad params"):
        build_probe(ProbeSpec(type="resource-usage", params={}))  # selector required
