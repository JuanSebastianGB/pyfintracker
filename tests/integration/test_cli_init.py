"""Tests for the ``fin init`` command.

Covers T-1.12 (implementation) and T-1.17 (integration coverage).
"""

from __future__ import annotations

from pathlib import Path

from sqlalchemy import text
from typer.testing import CliRunner


def test_init_creates_db(tmp_path: Path, cli_runner: CliRunner) -> None:
    """``fin init`` creates the SQLite database file."""
    from pyfintracker.cli import app

    db_path = tmp_path / "fin" / "fin.db"
    result = cli_runner.invoke(app, ["init"], env={"FIN_DB_PATH": str(db_path)})
    assert result.exit_code == 0, result.stdout
    assert db_path.exists()


def test_init_runs_migrations(tmp_path: Path, cli_runner: CliRunner) -> None:
    """After ``fin init``, 4 user tables exist."""
    from pyfintracker.cli import app
    from pyfintracker.db import make_engine

    db_path = tmp_path / "fin" / "fin.db"
    result = cli_runner.invoke(app, ["init"], env={"FIN_DB_PATH": str(db_path)})
    assert result.exit_code == 0, result.stdout

    engine = make_engine(f"sqlite:///{db_path}")
    with engine.connect() as conn:
        tables = conn.execute(
            text(
                "SELECT name FROM sqlite_master WHERE type='table'"
                " AND name NOT LIKE 'alembic_%'"
                " AND name != 'sqlite_sequence'"
                " AND name NOT LIKE '%\\_fts\\_%' ESCAPE '\\'"
            )
        ).fetchall()
    assert len(tables) == 10, f"Expected 10 tables, got {len(tables)}: {[r[0] for r in tables]}"


def test_init_seeds_chart(tmp_path: Path, cli_runner: CliRunner) -> None:
    """After ``fin init``, 11 starter accounts exist."""
    from pyfintracker.cli import app
    from pyfintracker.db import make_engine

    db_path = tmp_path / "fin" / "fin.db"
    cli_runner.invoke(app, ["init"], env={"FIN_DB_PATH": str(db_path)})

    engine = make_engine(f"sqlite:///{db_path}")
    with engine.connect() as conn:
        count = conn.execute(text("SELECT count(*) FROM accounts")).scalar()
    assert count == 11, f"Expected 11 accounts, got {count}"


def test_init_refuses_if_db_exists(tmp_path: Path, cli_runner: CliRunner) -> None:
    """Re-invoking ``init`` without --force prints message and exits 0."""
    from pyfintracker.cli import app

    db_path = tmp_path / "fin" / "fin.db"
    cli_runner.invoke(app, ["init"], env={"FIN_DB_PATH": str(db_path)})

    result = cli_runner.invoke(app, ["init"], env={"FIN_DB_PATH": str(db_path)})
    assert result.exit_code == 0, result.stdout
    assert "already initialized" in result.stdout.lower()


def test_init_force_recreates(tmp_path: Path, cli_runner: CliRunner) -> None:
    """``init --force`` removes old DB and creates a fresh one."""
    from pyfintracker.cli import app
    from pyfintracker.db import make_engine

    db_path = tmp_path / "fin" / "fin.db"
    cli_runner.invoke(app, ["init"], env={"FIN_DB_PATH": str(db_path)})

    # Add a custom record so we can tell it's a different DB
    engine = make_engine(f"sqlite:///{db_path}")
    with engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO accounts (name, currency, depth, kind) "
                "VALUES ('Expenses:Testing', 'COP', 1, 'Expenses')"
            )
        )

    # Force recreate
    result = cli_runner.invoke(app, ["init", "--force"], env={"FIN_DB_PATH": str(db_path)})
    assert result.exit_code == 0, result.stdout

    # Fresh DB should have exactly the 11 starter accounts
    engine2 = make_engine(f"sqlite:///{db_path}")
    with engine2.connect() as conn:
        count = conn.execute(text("SELECT count(*) FROM accounts")).scalar()
    assert count == 11, f"Expected 11 after force, got {count}"


def test_init_custom_path(tmp_path: Path, cli_runner: CliRunner) -> None:
    """``fin init`` with custom ``FIN_DB_PATH`` creates DB at that path."""
    from pyfintracker.cli import app

    custom_path = tmp_path / "custom_dir" / "data.sqlite"
    result = cli_runner.invoke(app, ["init"], env={"FIN_DB_PATH": str(custom_path)})
    assert result.exit_code == 0, result.stdout
    assert custom_path.exists()


def test_init_creates_parent_dir(tmp_path: Path, cli_runner: CliRunner) -> None:
    """``fin init`` creates parent directories automatically."""
    from pyfintracker.cli import app

    deep_path = tmp_path / "a" / "b" / "c" / "fin.db"
    result = cli_runner.invoke(app, ["init"], env={"FIN_DB_PATH": str(deep_path)})
    assert result.exit_code == 0, result.stdout
    assert deep_path.exists()


def test_init_without_force_is_noop(tmp_path: Path, cli_runner: CliRunner) -> None:
    """Re-invoking ``init`` without --force does NOT reset the DB."""
    from pyfintracker.cli import app
    from pyfintracker.db import make_engine

    db_path = tmp_path / "fin" / "fin.db"
    cli_runner.invoke(app, ["init"], env={"FIN_DB_PATH": str(db_path)})

    # Remove a starter account to alter the chart
    engine = make_engine(f"sqlite:///{db_path}")
    with engine.begin() as conn:
        conn.execute(text("DELETE FROM accounts WHERE name = 'Expenses:Rent'"))

    # Re-init (no force) — should be a no-op
    cli_runner.invoke(app, ["init"], env={"FIN_DB_PATH": str(db_path)})

    # Account should still be gone
    with engine.connect() as conn:
        row = conn.execute(text("SELECT count(*) FROM accounts WHERE kind = 'Expenses'")).scalar()
    assert row == 4, "Re-init without --force should not reset accounts"
