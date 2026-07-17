"""pytest fixtures for pyfintracker tests.

All fixtures are function-scoped — each test gets a fresh in-memory
database with migrations applied and a clean transaction.  The
``connection`` fixture runs Alembic upgrade on the fresh database.
"""

from collections.abc import Generator

import pytest
from alembic.command import upgrade
from alembic.config import Config
from sqlalchemy import Connection, Engine


@pytest.fixture(scope="function")
def engine() -> Generator[Engine, None, None]:
    """Function-scoped :memory: engine with pragmas applied.

    Each test gets a completely isolated in-memory SQLite database.
    """
    from pyfintracker.db import make_test_engine

    yield make_test_engine()


@pytest.fixture(scope="function")
def connection(engine: Engine) -> Generator[Connection, None, None]:
    """Dedicated connection with migrations applied.

    Runs Alembic ``upgrade("head")`` on the fresh in-memory database so
    every test starts with a fully migrated schema (4 tables + 11-account
    starter chart).
    """
    conn = engine.connect()
    alembic_cfg = Config("alembic.ini")
    alembic_cfg.attributes["connection"] = conn
    upgrade(alembic_cfg, "head")
    yield conn
    conn.close()


@pytest.fixture(scope="function")
def session(connection: Connection) -> Generator[Connection, None, None]:
    """PEP 249 session wrapping the connection with transaction rollback.

    The transaction is rolled back after the test completes, providing a
    safety net.  Since the database is in-memory, the entire DB is
    discarded after each test regardless.
    """
    trans = connection.begin()
    yield connection
    trans.rollback()


@pytest.fixture(scope="function")
def cli_runner() -> Generator:
    """Typer CliRunner for testing CLI commands."""
    from typer.testing import CliRunner

    yield CliRunner()
