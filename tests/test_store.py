# -#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#
# __creation__ = 2026-06-03
# __author__ = "jndjama (Joy Ndjama)"
# __copyright__ = "Copyright 2026 ALTIKVA."
# __licence__ = "MIT & CC BY-NC-SA (http://www.altikva.com/licenses/LICENSE-1.0)"
# -#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#

"""Tests for the SQLAlchemy store: schema, session commit/rollback."""

from __future__ import annotations

import pytest
from sqlalchemy import select

from spero.store import Event, init_db, make_engine, session_scope


def test_commit_persists() -> None:
    engine = make_engine("sqlite://")  # in-memory
    init_db(engine)
    with session_scope(engine) as s:
        s.add(Event(node="web-01", target="nginx", kind="probe_fail", detail="down"))
    with session_scope(engine) as s:
        rows = s.scalars(select(Event)).all()
        assert len(rows) == 1
        assert rows[0].kind == "probe_fail"


def test_rollback_on_error() -> None:
    engine = make_engine("sqlite://")
    init_db(engine)
    with pytest.raises(RuntimeError), session_scope(engine) as s:
        s.add(Event(node="web-01", target="nginx", kind="info", detail=""))
        raise RuntimeError("boom")
    # the failed transaction left nothing behind
    with session_scope(engine) as s:
        assert s.scalars(select(Event)).all() == []
