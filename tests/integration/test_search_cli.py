"""Integration tests for ``fin search`` command — FTS5 full-text search.

Covers basic match, no-match, limit, empty query, and FTS rebuild.
"""

from __future__ import annotations

from pathlib import Path

from typer.testing import CliRunner


def _init_db(tmp_path: Path, cli_runner: CliRunner) -> Path:
    """Initialise a fresh database and return its path."""
    from pyfintracker.cli import app

    db_path = tmp_path / "fin" / "fin.db"
    result = cli_runner.invoke(app, ["init"], env={"FIN_DB_PATH": str(db_path)})
    assert result.exit_code == 0, result.stdout
    return db_path


def _create_transaction(
    db_path: Path,
    cli_runner: CliRunner,
    description: str,
    amount: str = "10000",
) -> None:
    """Helper: create a single transaction via ``fin register``."""
    from pyfintracker.cli import app

    result = cli_runner.invoke(
        app,
        [
            "register",
            description,
            amount,
            "--account",
            "Expenses:Food:Groceries",
        ],
        env={"FIN_DB_PATH": str(db_path)},
    )
    assert result.exit_code == 0, result.stdout


# ── Tests ──────────────────────────────────────────────────────────────────


def test_search_basic(tmp_path: Path, cli_runner: CliRunner) -> None:
    """Search for "café" finds a transaction with "café latte"."""
    db_path = _init_db(tmp_path, cli_runner)
    _create_transaction(db_path, cli_runner, "café latte")

    from pyfintracker.cli import app

    result = cli_runner.invoke(
        app,
        ["search", "café"],
        env={"FIN_DB_PATH": str(db_path)},
    )
    assert result.exit_code == 0, result.stdout
    assert "café latte" in result.stdout
    assert "Expenses:Food:Groceries" in result.stdout


def test_search_no_match(tmp_path: Path, cli_runner: CliRunner) -> None:
    """Search for a non-existent string returns empty."""
    db_path = _init_db(tmp_path, cli_runner)
    _create_transaction(db_path, cli_runner, "coffee")

    from pyfintracker.cli import app

    result = cli_runner.invoke(
        app,
        ["search", "zzzznotfound"],
        env={"FIN_DB_PATH": str(db_path)},
    )
    assert result.exit_code == 0, result.stdout
    assert "No matching transactions" in result.stdout


def test_search_limit(tmp_path: Path, cli_runner: CliRunner) -> None:
    """Search returns at most ``--limit`` results."""
    db_path = _init_db(tmp_path, cli_runner)
    for i in range(5):
        _create_transaction(db_path, cli_runner, f"coffee run {i}")

    from pyfintracker.cli import app

    result = cli_runner.invoke(
        app,
        ["search", "coffee", "--limit", "2"],
        env={"FIN_DB_PATH": str(db_path)},
    )
    assert result.exit_code == 0, result.stdout
    # Should show exactly 2 transactions
    lines = [ln for ln in result.stdout.split("\n") if "coffee run" in ln]
    assert len(lines) == 2, f"Expected 2 result lines, got {len(lines)}"


def test_search_empty_query(tmp_path: Path, cli_runner: CliRunner) -> None:
    """Empty query should produce an error (FTS5 rejects empty MATCH)."""
    db_path = _init_db(tmp_path, cli_runner)

    from pyfintracker.cli import app

    result = cli_runner.invoke(
        app,
        ["search", ""],
        env={"FIN_DB_PATH": str(db_path)},
    )
    # Empty string search may cause an error — ensure graceful handling
    assert result.exit_code != 0 or "No matching" in result.stdout


def test_fts_rebuild(tmp_path: Path, cli_runner: CliRunner) -> None:
    """Direct FTS rebuild — create transactions, rebuild, search."""
    db_path = _init_db(tmp_path, cli_runner)
    _create_transaction(db_path, cli_runner, "rebuild test transaction")

    # Rebuild FTS index directly
    from sqlalchemy import create_engine, text

    engine = create_engine(f"sqlite:///{db_path}")
    with engine.begin() as conn:
        conn.execute(text("INSERT INTO transactions_fts(transactions_fts) VALUES('rebuild')"))

    from pyfintracker.cli import app

    result = cli_runner.invoke(
        app,
        ["search", "rebuild"],
        env={"FIN_DB_PATH": str(db_path)},
    )
    assert result.exit_code == 0, result.stdout
    # Rich table may truncate long descriptions, match partial
    assert "rebuild test" in result.stdout
