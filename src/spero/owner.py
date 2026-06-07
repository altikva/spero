# -#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#
# __creation__ = 2026-06-06
# __author__ = "jndjama (Joy Ndjama)"
# __copyright__ = "Copyright 2026 ALTIKVA."
# __licence__ = "MIT & CC BY-NC-SA (https://www.altikva.com/licenses/LICENSE-1.0)"
# -#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#
# Description: Owner / fleet service: agents dial home, report status, and pull orders.

"""The owner (fleet) service that in-cluster agents dial home to.

An agent (``spero agent``) cannot be reached inbound, so it dials OUT to this
service: it POSTs its status + recent events on a timer, and the response carries
any pending orders (e.g. an approval for a gated remediation). A human approves a
target's gated action here; the next agent report picks it up. State is in-memory:
one process, restart-clears, which is the right scope for a single-owner fleet view.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from fastapi import Depends, FastAPI, HTTPException
from pydantic import BaseModel, Field

from spero.api.auth import make_auth_dependency


class Report(BaseModel):
    status: dict = Field(default_factory=dict)
    events: list[dict] = Field(default_factory=list)


class Approve(BaseModel):
    target: str


@dataclass
class AgentState:
    status: dict = field(default_factory=dict)
    events: list[dict] = field(default_factory=list)
    orders: list[dict] = field(default_factory=list)  # delivered on the next report
    reports: int = 0


class AgentRegistry:
    """In-memory fleet state: latest report per agent + a per-agent order queue."""

    def __init__(self) -> None:
        self.agents: dict[str, AgentState] = {}

    def report(self, agent_id: str, status: dict, events: list[dict]) -> list[dict]:
        st = self.agents.setdefault(agent_id, AgentState())
        st.status = status
        st.events = events
        st.reports += 1
        orders, st.orders = st.orders, []  # hand over and clear the queue
        return orders

    def queue_approve(self, agent_id: str, target: str) -> None:
        self.agents.setdefault(agent_id, AgentState()).orders.append(
            {"type": "approve", "target": target}
        )

    def fleet(self) -> list[dict]:
        return [
            {
                "id": aid,
                "reports": st.reports,
                "frozen": st.status.get("frozen", False),
                "targets": st.status.get("targets", []),
            }
            for aid, st in self.agents.items()
        ]


def create_owner_app(registry: AgentRegistry | None = None, *, token: str | None = None) -> FastAPI:
    registry = registry or AgentRegistry()
    if token is None:  # default to the configured owner token (empty = auth disabled)
        from spero.config import settings

        token = settings.owner_token
    app = FastAPI(title="spero owner", summary="Fleet owner: agents dial home here.")
    app.state.registry = registry
    # /health stays open for kubelet probes; everything else is token-guarded.
    auth = Depends(make_auth_dependency(token))

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    # The handlers are `async def` on purpose: they run on the event loop rather
    # than Starlette's threadpool, so concurrent agent reports serialize and the
    # in-memory AgentRegistry needs no lock.
    @app.post("/agents/{agent_id}/report", dependencies=[auth])
    async def report(agent_id: str, body: Report) -> dict[str, object]:
        return {"orders": registry.report(agent_id, body.status, body.events)}

    @app.post("/agents/{agent_id}/approve", dependencies=[auth])
    async def approve(agent_id: str, body: Approve) -> dict[str, str]:
        registry.queue_approve(agent_id, body.target)
        return {"queued": body.target}

    @app.get("/agents", dependencies=[auth])
    async def agents() -> dict[str, object]:
        return {"agents": registry.fleet()}

    @app.get("/agents/{agent_id}", dependencies=[auth])
    async def agent(agent_id: str) -> dict[str, object]:
        st = registry.agents.get(agent_id)
        if st is None:
            raise HTTPException(404, f"unknown agent: {agent_id}")
        return {"status": st.status, "events": st.events}

    return app
