# -#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#
# __creation__ = 2026-06-03
# __author__ = "jndjama (Joy Ndjama)"
# __copyright__ = "Copyright 2026 ALTIKVA."
# __licence__ = "MIT & CC BY-NC-SA (http://www.altikva.com/licenses/LICENSE-1.0)"
# -#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#
# Description: Data-infrastructure probes (Phase 4).

"""Data-infrastructure probes (Phase 4).

These ride the same Provider seam as everything else -- they're just commands run
on the target (local, ssh, or k8s) -- so a Postgres or Trino check works the same
whether the service runs on a VM or in a pod, and heals with the restart /
rollout-restart remediations you already have.

Two generic building blocks (HttpProbe, CommandProbe) cover most systems; the
named adapters (postgres, trino, clickhouse, kafka) are thin presets over them.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import ClassVar

from spero.probes.base import Probe, ProbeResult
from spero.providers.base import Provider


class HttpProbe(Probe):
    """Healthy iff an HTTP GET returns ``expect_status``. Uses curl on the target."""

    type: ClassVar[str] = "http"

    def __init__(
        self, url: str, expect_status: int = 200, insecure: bool = False, max_time: int = 10
    ) -> None:
        if not url.startswith(("http://", "https://")):
            raise ValueError(f"http probe url must be http(s): {url!r}")
        self.url = url
        self.expect_status = int(expect_status)
        self.insecure = insecure
        self.max_time = int(max_time)

    async def check(self, provider: Provider) -> ProbeResult:
        cmd = [
            "curl",
            "-s",
            "-o",
            "/dev/null",
            "-w",
            "%{http_code}",
            "--max-time",
            str(self.max_time),
        ]
        if self.insecure:
            cmd.append("-k")
        # `--` so a URL can never be parsed as a curl flag (-O, -K file, ...).
        cmd += ["--", self.url]
        r = await provider.run(cmd, timeout=self.max_time + 5)
        code = r.stdout.strip()
        healthy = r.ok and code == str(self.expect_status)
        return ProbeResult(healthy, f"{self.url} -> {code or r.stderr.strip() or 'no response'}")


class CommandProbe(Probe):
    """Healthy iff ``command`` exits 0 (and, if set, stdout contains ``expect_contains``).

    The universal escape hatch: pg_isready, redis-cli ping, a SQL one-liner, a CLI
    health subcommand -- anything that returns 0 when the service is well.
    """

    type: ClassVar[str] = "command"

    def __init__(
        self, command: str | Sequence[str], expect_contains: str | None = None, timeout: int = 15
    ) -> None:
        self.command = command
        self.expect_contains = expect_contains
        self.timeout = int(timeout)

    async def check(self, provider: Provider) -> ProbeResult:
        r = await provider.run(self.command, timeout=self.timeout)
        healthy = r.ok and (self.expect_contains is None or self.expect_contains in r.stdout)
        detail = (r.stdout.strip() or r.stderr.strip() or f"rc={r.returncode}")[:200]
        return ProbeResult(healthy, detail)


class PostgresProbe(Probe):
    """Postgres accepting connections, via ``pg_isready``."""

    type: ClassVar[str] = "postgres"

    def __init__(
        self,
        host: str = "localhost",
        port: int = 5432,
        dbname: str | None = None,
        timeout: int = 10,
    ) -> None:
        self.host = host
        self.port = int(port)
        self.dbname = dbname
        self.timeout = int(timeout)

    async def check(self, provider: Provider) -> ProbeResult:
        cmd = ["pg_isready", "-h", self.host, "-p", str(self.port), "-t", str(self.timeout)]
        if self.dbname:
            cmd += ["-d", self.dbname]
        r = await provider.run(cmd, timeout=self.timeout + 5)
        return ProbeResult(r.ok, r.stdout.strip() or r.stderr.strip() or f"rc={r.returncode}")


class KafkaProbe(Probe):
    """Kafka broker reachable, via ``kafka-broker-api-versions``."""

    type: ClassVar[str] = "kafka"

    def __init__(
        self, bootstrap: str, cli: str = "kafka-broker-api-versions.sh", timeout: int = 20
    ) -> None:
        self.bootstrap = bootstrap
        self.cli = cli
        self.timeout = int(timeout)

    async def check(self, provider: Provider) -> ProbeResult:
        r = await provider.run(
            [self.cli, "--bootstrap-server", self.bootstrap], timeout=self.timeout + 5
        )
        return ProbeResult(r.ok, f"{self.bootstrap}: {'reachable' if r.ok else r.stderr.strip()}")


class TrinoProbe(HttpProbe):
    """Trino coordinator up, via its ``/v1/info`` endpoint."""

    type: ClassVar[str] = "trino"

    def __init__(self, url: str, insecure: bool = False) -> None:
        super().__init__(url=url.rstrip("/") + "/v1/info", insecure=insecure)


class ClickHouseProbe(HttpProbe):
    """ClickHouse up, via its ``/ping`` endpoint."""

    type: ClassVar[str] = "clickhouse"

    def __init__(self, url: str, insecure: bool = False) -> None:
        super().__init__(url=url.rstrip("/") + "/ping", insecure=insecure)
