"""Tests for Phase 4 data-infrastructure probes (driven by a scripted provider)."""

from __future__ import annotations

from _fakes import ScriptedProvider, fixed
from spero.core.models import ProbeSpec
from spero.probes import build_probe
from spero.probes.datainfra import (
    ClickHouseProbe,
    CommandProbe,
    HttpProbe,
    KafkaProbe,
    PostgresProbe,
    TrinoProbe,
)


async def test_http_probe_status_match() -> None:
    provider = ScriptedProvider(fixed(0, "200"))
    r = await HttpProbe("http://localhost:8080/health").check(provider)
    assert r.healthy
    assert provider.commands[0][0] == "curl"
    assert provider.commands[0][-1] == "http://localhost:8080/health"


async def test_http_probe_wrong_status() -> None:
    r = await HttpProbe("http://x/health", expect_status=200).check(
        ScriptedProvider(fixed(0, "503"))
    )
    assert not r.healthy


async def test_http_probe_insecure_flag() -> None:
    provider = ScriptedProvider(fixed(0, "200"))
    await HttpProbe("https://x", insecure=True).check(provider)
    assert "-k" in provider.commands[0]


async def test_command_probe_rc_and_contains() -> None:
    assert (await CommandProbe("pg_isready").check(ScriptedProvider(fixed(0, "accepting")))).healthy
    # rc 0 but missing expected substring -> unhealthy
    r = await CommandProbe("redis-cli ping", expect_contains="PONG").check(
        ScriptedProvider(fixed(0, "LOADING"))
    )
    assert not r.healthy


async def test_postgres_probe_command() -> None:
    provider = ScriptedProvider(fixed(0, "accepting connections"))
    r = await PostgresProbe(host="db1", port=5433, dbname="app").check(provider)
    assert r.healthy
    assert provider.commands[0][:5] == ["pg_isready", "-h", "db1", "-p", "5433"]
    assert "app" in provider.commands[0]


async def test_kafka_probe_command() -> None:
    provider = ScriptedProvider(fixed(0))
    await KafkaProbe(bootstrap="broker:9092").check(provider)
    assert provider.commands[0] == [
        "kafka-broker-api-versions.sh",
        "--bootstrap-server",
        "broker:9092",
    ]


async def test_trino_and_clickhouse_endpoints() -> None:
    trino = ScriptedProvider(fixed(0, "200"))
    await TrinoProbe("http://trino:8080").check(trino)
    assert trino.commands[0][-1] == "http://trino:8080/v1/info"

    ch = ScriptedProvider(fixed(0, "200"))
    await ClickHouseProbe("http://ch:8123/").check(ch)
    assert ch.commands[0][-1] == "http://ch:8123/ping"


async def test_build_datainfra_probes_from_spec() -> None:
    assert isinstance(build_probe(ProbeSpec(type="postgres", params={"host": "db"})), PostgresProbe)
    assert isinstance(
        build_probe(ProbeSpec(type="trino", params={"url": "http://t:8080"})), TrinoProbe
    )
