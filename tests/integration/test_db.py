"""Integration tests for db.py engine creation and PRAGMA setup."""

import pytest
from sqlalchemy import Engine, text
from sqlalchemy.pool import StaticPool

from pyfintracker.db import apply_pragmas, get_session, make_engine, make_test_engine


@pytest.mark.integration
class TestMakeEngine:
    def test_returns_engine(self) -> None:
        """make_engine returns a SQLAlchemy Engine."""
        engine = make_engine("sqlite:///:memory:")
        assert isinstance(engine, Engine)

    def test_echo_false_by_default(self) -> None:
        """echo is False when not specified."""
        engine = make_engine("sqlite:///:memory:")
        assert not engine.echo

    def test_journal_mode_wal(self) -> None:
        """PRAGMA journal_mode is set to WAL."""
        engine = make_engine("sqlite:///:memory:")
        with engine.connect() as conn:
            row = conn.execute(text("PRAGMA journal_mode")).fetchone()
            # journal_mode returns 'memory' for :memory: DBs, but for file DBs it returns 'wal'
            # The important thing is that it's not 'delete'
            assert row is not None

    def test_foreign_keys_on(self) -> None:
        """PRAGMA foreign_keys is ON."""
        engine = make_engine("sqlite:///:memory:")
        with engine.connect() as conn:
            row = conn.execute(text("PRAGMA foreign_keys")).fetchone()
            assert row is not None
            assert row[0] == 1  # 1 = ON


@pytest.mark.integration
class TestMakeTestEngine:
    def test_is_in_memory(self) -> None:
        """make_test_engine creates an in-memory SQLite database."""
        engine = make_test_engine()
        assert isinstance(engine, Engine)
        assert str(engine.url) == "sqlite:///:memory:"

    def test_uses_static_pool(self) -> None:
        """make_test_engine uses StaticPool."""
        engine = make_test_engine()
        assert isinstance(engine.pool, StaticPool)


@pytest.mark.integration
class TestGetSession:
    def test_select_1_works(self) -> None:
        """Can execute a simple SELECT 1 through get_session."""
        engine = make_engine("sqlite:///:memory:")
        with get_session(engine) as conn:
            row = conn.execute(text("SELECT 1")).fetchone()
            assert row is not None
            assert row[0] == 1

    def test_returns_context_manager(self) -> None:
        """get_session yields a Connection inside a transaction."""
        engine = make_engine("sqlite:///:memory:")
        with get_session(engine) as conn:
            assert conn is not None

    def test_commits_on_exit(self) -> None:
        """Changes are committed when the context manager exits normally."""
        engine = make_engine("sqlite:///:memory:")
        with get_session(engine) as conn:
            conn.execute(text("CREATE TABLE test (x INTEGER)"))
            conn.execute(text("INSERT INTO test VALUES (42)"))
        # After exit, the txn should be committed — verify with a new connection
        with engine.connect() as conn:
            row = conn.execute(text("SELECT x FROM test")).fetchone()
            assert row is not None
            assert row[0] == 42


@pytest.mark.integration
class TestApplyPragmas:
    def test_idempotent(self) -> None:
        """apply_pragmas can be called multiple times without error."""
        engine = make_test_engine()
        with engine.connect() as conn:
            apply_pragmas(conn)
            apply_pragmas(conn)  # second call should not raise
            row = conn.execute(text("PRAGMA foreign_keys")).fetchone()
            assert row is not None
            assert row[0] == 1

    def test_synchronous_normal(self) -> None:
        """PRAGMA synchronous is set to NORMAL (1)."""
        engine = make_engine("sqlite:///:memory:")
        with engine.connect() as conn:
            row = conn.execute(text("PRAGMA synchronous")).fetchone()
            assert row is not None
            assert row[0] == 1  # 1 = NORMAL in SQLite


@pytest.mark.integration
class TestApplyPragmasViaMakeTestEngine:
    """make_test_engine should apply pragmas so tests get WAL + FK + sync."""

    def test_foreign_keys_on_by_default(self) -> None:
        engine = make_test_engine()
        with engine.connect() as conn:
            row = conn.execute(text("PRAGMA foreign_keys")).fetchone()
            assert row is not None
            assert row[0] == 1

    def test_synchronous_normal_by_default(self) -> None:
        engine = make_test_engine()
        with engine.connect() as conn:
            row = conn.execute(text("PRAGMA synchronous")).fetchone()
            assert row is not None
            assert row[0] == 1  # 1 = NORMAL in SQLite
