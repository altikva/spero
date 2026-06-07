# -#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#
# __creation__ = 2026-06-03
# __author__ = "jndjama (Joy Ndjama)"
# __copyright__ = "Copyright 2026 ALTIKVA."
# __licence__ = "MIT & CC BY-NC-SA (https://www.altikva.com/licenses/LICENSE-1.0)"
# -#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#
# Description: Tests for the FastAPI control plane.

"""Tests for the FastAPI control plane."""

from __future__ import annotations

from fastapi.testclient import TestClient

from spero import __version__
from spero.api.app import app, create_app
from spero.config import Settings

client = TestClient(app)


def test_health() -> None:
    r = client.get("/health")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert body["version"] == __version__


def test_targets_lists_policy() -> None:
    r = client.get("/targets")
    assert r.status_code == 200
    body = r.json()
    assert "targets" in body
    names = {t["name"] for t in body["targets"]}
    assert "nginx" in names


def test_targets_missing_policy_returns_503() -> None:
    bad_app = create_app(Settings(policy_path="does/not/exist.yaml"))
    r = TestClient(bad_app).get("/targets")
    assert r.status_code == 503
    assert "not found" in r.json()["detail"]


def test_status_and_events_503_without_supervisor() -> None:
    # The plain app (no supervisor) is a static policy view; live endpoints 503.
    assert client.get("/status").status_code == 503
    assert client.get("/events").status_code == 503


def test_status_and_events_with_supervisor() -> None:
    from spero.api.supervisor import Supervisor
    from spero.core.models import Policy, ProbeSpec, TargetPolicy

    pol = Policy(
        targets=[
            TargetPolicy(
                name="nginx",
                provider="local",
                probe=ProbeSpec(type="systemd", params={"unit": "nginx.service"}),
            )
        ]
    )
    # No `with`: lifespan (and the background watch loop) does not start, so this is
    # a deterministic read of the live endpoints with no probing.
    api = TestClient(create_app(supervisor=Supervisor(pol)))
    s = api.get("/status")
    assert s.status_code == 200
    body = s.json()
    assert body["frozen"] is False
    assert body["targets"][0]["target"] == "nginx"
    assert body["targets"][0]["healthy"] is None  # not probed yet
    e = api.get("/events")
    assert e.status_code == 200
    assert e.json() == {"events": []}


def test_objects_503_without_supervisor() -> None:
    assert client.get("/objects/whatever").status_code == 503


def test_objects_404_and_422_with_supervisor() -> None:
    from spero.api.supervisor import Supervisor
    from spero.core.models import Policy, ProbeSpec, TargetPolicy

    pol = Policy(
        targets=[
            TargetPolicy(
                name="nginx",
                provider="local",
                probe=ProbeSpec(type="systemd", params={"unit": "nginx.service"}),
            )
        ]
    )
    api = TestClient(create_app(supervisor=Supervisor(pol)))
    assert api.get("/objects/missing").status_code == 404  # unknown target
    assert api.get("/objects/nginx").status_code == 422  # host probe has no k8s object


def test_logs_503_without_supervisor() -> None:
    assert client.get("/logs/whatever").status_code == 503


def test_logs_404_and_422_with_supervisor() -> None:
    from spero.api.supervisor import Supervisor
    from spero.core.models import Policy, ProbeSpec, TargetPolicy

    pol = Policy(
        targets=[
            TargetPolicy(
                name="nginx",
                provider="local",
                probe=ProbeSpec(type="systemd", params={"unit": "nginx.service"}),
            )
        ]
    )
    api = TestClient(create_app(supervisor=Supervisor(pol)))
    assert api.get("/logs/missing").status_code == 404  # unknown target
    assert api.get("/logs/nginx").status_code == 422  # host probe has no pods


def test_logs_tail_is_clamped() -> None:
    # The endpoint must bound `tail` before passing it to kubectl logs.
    class _StubSupervisor:
        def __init__(self) -> None:
            self.seen_tail: int | None = None

        async def start(self) -> None: ...
        async def stop(self) -> None: ...

        async def object_logs(self, name: str, *, tail: int = 200) -> str:
            self.seen_tail = tail
            return "ok"

    stub = _StubSupervisor()
    api = TestClient(create_app(supervisor=stub))  # type: ignore[arg-type]
    assert api.get("/logs/anything", params={"tail": 10_000_000}).status_code == 200
    assert stub.seen_tail == 5000  # clamped to the max
    api.get("/logs/anything", params={"tail": -5})
    assert stub.seen_tail == 1  # non-positive floored to 1
