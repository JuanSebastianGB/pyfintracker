"""Tests for the ``fin migrate`` command.

Covers T-1.13 (up / down / status).
"""

from __future__ import annotations

from pathlib import Path

from sqlalchemy import text
from typer.testing import CliRunner


def test_migrate_status_on_init(tmp_path: Path, cli_runner: CliRunner) -> None:
    """After ``fin init``, ``migrate status`` shows the head revision."""
    from pyfintracker.cli import app

    db_path = tmp_path / "fin" / "fin.db"
    cli_runner.invoke(app, ["init"], env={"FIN_DB_PATH": str(db_path)})

    result = cli_runner.invoke(app, ["migrate", "status"], env={"FIN_DB_PATH": str(db_path)})
    assert result.exit_code == 0, f"stdout: {result.stdout} stderr: {result.stderr}"


def test_migrate_down_up(tmp_path: Path, cli_runner: CliRunner) -> None:
    """``migrate down base`` then ``migrate up head`` works."""
    from pyfintracker.cli import app
    from pyfintracker.db import make_engine

    db_path = tmp_path / "fin" / "fin.db"
    cli_runner.invoke(app, ["init"], env={"FIN_DB_PATH": str(db_path)})

    # Downgrade to base
    result = cli_runner.invoke(app, ["migrate", "down", "base"], env={"FIN_DB_PATH": str(db_path)})
    assert result.exit_code == 0, result.stderr

    # Verify tables are gone
    engine = make_engine(f"sqlite:///{db_path}")
    with engine.connect() as conn:
        tables = conn.execute(
            text(
                "SELECT name FROM sqlite_master WHERE type='table'"
                " AND name NOT LIKE 'alembic_%' AND name != 'sqlite_sequence'"
            )
        ).fetchall()
    assert len(tables) == 0, f"Expected 0 tables after downgrade, got {len(tables)}"

    # Upgrade back to head
    result = cli_runner.invoke(app, ["migrate", "up", "head"], env={"FIN_DB_PATH": str(db_path)})
    assert result.exit_code == 0, result.stderr

    # Verify tables are back
    with engine.connect() as conn:
        tables = conn.execute(
            text(
                "SELECT name FROM sqlite_master WHERE type='table'"
                " AND name NOT LIKE 'alembic_%'"
                " AND name != 'sqlite_sequence'"
                " AND name NOT LIKE '%\\_fts\\_%' ESCAPE '\\'"
            )
        ).fetchall()
    assert len(tables) == 10, f"Expected 10 tables after re-upgrade, got {len(tables)}"


def test_migrate_invalid_action(tmp_path: Path, cli_runner: CliRunner) -> None:
    """An invalid action produces exit code 1 and an error message."""
    from pyfintracker.cli import app

    db_path = tmp_path / "fin" / "fin.db"
    cli_runner.invoke(app, ["init"], env={"FIN_DB_PATH": str(db_path)})

    result = cli_runner.invoke(app, ["migrate", "invalid"], env={"FIN_DB_PATH": str(db_path)})
    assert result.exit_code == 1, result.stdout
    assert "Unknown" in result.stderr
