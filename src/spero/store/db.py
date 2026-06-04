# -#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#
# __creation__ = 2026-06-03
# __author__ = "jndjama (Joy Ndjama)"
# __copyright__ = "Copyright 2026 ALTIKVA."
# __licence__ = "MIT & CC BY-NC-SA (https://www.altikva.com/licenses/LICENSE-1.0)"
# -#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#
# Description: Engine and session helpers. Replaces the bot's MyDatabase context manager.

"""Engine and session helpers. Replaces the bot's MyDatabase context manager."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager

from sqlalchemy import Engine, create_engine, select
from sqlalchemy.orm import Session, sessionmaker

from spero.store.models import Base, Event


def make_engine(url: str = "sqlite:///spero.db", *, echo: bool = False) -> Engine:
    return create_engine(url, echo=echo, future=True)


def init_db(engine: Engine) -> None:
    Base.metadata.create_all(engine)


def recent_events(engine: Engine, *, target: str | None = None, limit: int = 200) -> list[Event]:
    """Most recent events (optionally for one target), newest first."""
    stmt = select(Event).order_by(Event.created_at.desc()).limit(limit)
    if target is not None:
        stmt = stmt.where(Event.target == target)
    with session_scope(engine) as session:
        return list(session.scalars(stmt).all())


@contextmanager
def session_scope(engine: Engine) -> Iterator[Session]:
    """Transactional session: commit on success, roll back on error, always close."""
    factory = sessionmaker(engine, expire_on_commit=False)
    session = factory()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
