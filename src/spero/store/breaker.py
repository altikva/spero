# -#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#
# __creation__ = 2026-11-28
# __author__ = "jndjama (Joy Ndjama)"
# __copyright__ = "Copyright 2026 ALTIKVA."
# __licence__ = "Apache-2.0 (https://www.apache.org/licenses/LICENSE-2.0)"
# -#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#
# Description: SQL-backed breaker state, so a tripped breaker survives a restart.

"""SQL-backed breaker state, so a tripped breaker survives a restart.

One row per target in ``breaker_state``. ``spero reset`` and the daemon share it,
and the engine reads it before every remediation, so a reset from another process
takes effect at the target's next check.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime

from sqlalchemy import Engine, delete

from spero.core.breaker import BreakerState
from spero.store.db import session_scope
from spero.store.models import BreakerRow


class SQLBreakerStore:
    def __init__(self, engine: Engine) -> None:
        self.engine = engine

    def load(self, target: str) -> BreakerState:
        with session_scope(self.engine) as session:
            row = session.get(BreakerRow, target)
            if row is None:
                return BreakerState()
            tripped_at = row.tripped_at
            if tripped_at is not None and tripped_at.tzinfo is None:
                tripped_at = tripped_at.replace(tzinfo=UTC)  # SQLite drops the zone
            return BreakerState(
                restarts=[float(t) for t in json.loads(row.restarts or "[]")],
                tripped_at=tripped_at.timestamp() if tripped_at else None,
                detail=row.detail,
            )

    def save(self, target: str, state: BreakerState) -> None:
        tripped_at = (
            datetime.fromtimestamp(state.tripped_at, UTC) if state.tripped_at is not None else None
        )
        with session_scope(self.engine) as session:
            session.merge(
                BreakerRow(
                    target=target,
                    restarts=json.dumps(state.restarts),
                    tripped_at=tripped_at,
                    detail=state.detail,
                )
            )

    def reset(self, target: str) -> bool:
        with session_scope(self.engine) as session:
            row = session.get(BreakerRow, target)
            was_tripped = row is not None and row.tripped_at is not None
            session.execute(delete(BreakerRow).where(BreakerRow.target == target))
            return was_tripped
