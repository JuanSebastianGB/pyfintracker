"""Engine, session factory, and test helpers.

Provides ``make_engine`` for production (with WAL + foreign_keys + synchronous=NORMAL
PRAGMAs) and ``make_test_engine`` for tests (in-memory + StaticPool + same PRAGMAs).
"""

from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from decimal import Decimal
from typing import Any

from sqlalchemy import Connection, Engine, create_engine, event, text
from sqlalchemy.pool import StaticPool
from sqlalchemy.types import Text, TypeDecorator


def make_engine(url: str, *, echo: bool = False) -> Engine:
    """Create a SQLAlchemy Engine with required PRAGMAs.

    Applies *journal_mode=WAL*, *foreign_keys=ON*, and *synchronous=NORMAL*
    on every connection via an after-connect event listener.
    """
    engine = create_engine(url, echo=echo)
    _register_pragmas(engine)
    return engine


def make_test_engine() -> Engine:
    """Create an in-memory Engine with ``StaticPool`` for test isolation.

    The same PRAGMAs as ``make_engine`` are applied. Connections share a
    single in-memory database so test state is visible across sessions.
    """
    engine = create_engine(
        "sqlite:///:memory:",
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )
    _register_pragmas(engine)
    return engine


def apply_pragmas(conn: Connection) -> None:
    """Apply required PRAGMAs to an existing connection.

    Idempotent — safe to call multiple times.
    """
    conn.execute(text("PRAGMA journal_mode=WAL"))
    conn.execute(text("PRAGMA foreign_keys=ON"))
    conn.execute(text("PRAGMA synchronous=NORMAL"))


@contextmanager
def get_session(engine: Engine) -> Iterator[Connection]:
    """Yield a connection inside an explicit transaction.

    Usage::

        with get_session(engine) as conn:
            conn.execute(...)
    """
    with engine.begin() as conn:
        yield conn


# ── Internal helpers ───────────────────────────────────────────────────────


def _register_pragmas(engine: Engine) -> None:
    """Wire up the PRAGMA event listener on *connect*."""

    @event.listens_for(engine, "connect")
    def _on_connect(
        dbapi_connection: sqlite3.Connection, _connection_record: object
    ) -> None:
        """Apply PRAGMAs every time a new raw connection is opened."""
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.execute("PRAGMA synchronous=NORMAL")
        cursor.close()


# ── Decimal type decorator ────────────────────────────────────────────────────


class DecimalAsText(TypeDecorator):  # type: ignore[type-arg]
    """Store Decimal as TEXT in SQLite to preserve precision.

    SQLite NUMERIC/REAL would convert to float and lose precision.
    This TypeDecorator ensures byte-exact Decimal roundtrip.
    """

    impl = Text
    cache_ok = True  # Safe to cache because TEXT is always the same

    def process_bind_param(
        self, value: Decimal | None, dialect: Any
    ) -> str | None:
        if value is not None:
            return str(value)
        return None

    def process_result_value(
        self, value: str | None, dialect: Any
    ) -> Decimal | None:
        if value is not None:
            return Decimal(value)
        return None

    def python_type(self) -> type[Decimal]:  # type: ignore[override]
        return Decimal


__all__ = [
    "DecimalAsText",
    "apply_pragmas",
    "get_session",
    "make_engine",
    "make_test_engine",
]
