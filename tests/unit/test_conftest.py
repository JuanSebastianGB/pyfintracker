"""Smoke tests for conftest.py fixtures."""

import pytest
from sqlalchemy import Connection, Engine, text
from typer.testing import CliRunner


class TestEngineFixture:
    """Verify the engine fixture works."""

    @pytest.mark.unit
    def test_engine_is_sqlalchemy_engine(self, engine: Engine) -> None:
        """engine fixture returns a SQLAlchemy Engine."""
        assert isinstance(engine, Engine)

    @pytest.mark.unit
    def test_select_1(self, engine: Engine) -> None:
        """Can execute a simple query through the engine."""
        with engine.connect() as conn:
            row = conn.execute(text("SELECT 1")).scalar()
            assert row == 1


class TestConnectionFixture:
    """Verify the connection fixture runs migrations."""

    @pytest.mark.unit
    def test_migration_tables_exist(self, connection: Connection) -> None:
        """After migration, accounts table exists."""
        row = connection.execute(
            text(
                "SELECT count(*) FROM sqlite_master "
                "WHERE type='table' AND name='accounts'"
            )
        ).scalar()
        assert row == 1

    @pytest.mark.unit
    def test_starter_chart_seeded(self, connection: Connection) -> None:
        """Starter chart accounts exist after migration."""
        row = connection.execute(
            text("SELECT count(*) FROM accounts")
        ).scalar()
        assert row == 11

    @pytest.mark.unit
    def test_foreign_keys_on(self, connection: Connection) -> None:
        """PRAGMA foreign_keys is ON."""
        row = connection.execute(text("PRAGMA foreign_keys")).scalar()
        assert row == 1


class TestSessionFixture:
    """Verify the session fixture works."""

    @pytest.mark.unit
    def test_session_is_connection(self, session: Connection) -> None:
        """session fixture yields a Connection."""
        assert isinstance(session, Connection)

    @pytest.mark.unit
    def test_can_query(self, session: Connection) -> None:
        """Can query through session."""
        row = session.execute(text("SELECT count(*) FROM accounts")).scalar()
        assert row == 11


class TestCliRunner:
    """Verify the cli_runner fixture works."""

    @pytest.mark.unit
    def test_cli_runner_is_typer(self, cli_runner: CliRunner) -> None:
        """cli_runner fixture returns a CliRunner."""
        assert isinstance(cli_runner, CliRunner)
