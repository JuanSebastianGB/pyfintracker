"""Tests for ``fin add`` command (T-4.8).

Verifies the two-posting transaction creation via flag-based CLI.
"""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path

from sqlalchemy import text
from typer.testing import CliRunner


def _init_and_seed(tmp_path: Path, cli_runner: CliRunner) -> Path:
    """Initialize database and create test accounts."""
    from pyfintracker.cli import app

    db_path = tmp_path / "fin" / "fin.db"
    result = cli_runner.invoke(app, ["init"], env={"FIN_DB_PATH": str(db_path)})
    assert result.exit_code == 0, result.stdout

    # Create a few custom accounts (not in starter chart)
    for acct in ["Assets:Wallet", "Expenses:Food:Delivery"]:
        result = cli_runner.invoke(
            app,
            ["account", "new", acct, "--currency", "COP"],
            env={"FIN_DB_PATH": str(db_path)},
        )
        assert result.exit_code == 0, result.stdout

    return db_path


def test_add_two_postings(tmp_path: Path, cli_runner: CliRunner) -> None:
    """``fin add --from A --to B --amount X`` creates balanced transaction."""
    from pyfintracker.cli import app
    from pyfintracker.db import make_engine

    db_path = _init_and_seed(tmp_path, cli_runner)

    result = cli_runner.invoke(
        app,
        [
            "add",
            "--from",
            "Assets:Wallet",
            "--to",
            "Expenses:Food:Delivery",
            "--amount",
            "50000",
            "--currency",
            "COP",
            "--description",
            "Lunch with team",
        ],
        env={"FIN_DB_PATH": str(db_path)},
    )
    assert result.exit_code == 0, result.stdout
    assert "Transaction" in result.stdout

    engine = make_engine(f"sqlite:///{db_path}")
    with engine.connect() as conn:
        # Must have at least 1 transaction (init doesn't create any)
        txn_count = conn.execute(
            text("SELECT COUNT(*) FROM transactions"),
        ).scalar()
        assert txn_count == 1, f"Expected 1 transaction, got {txn_count}"

        # Must have 2 postings
        posting_count = conn.execute(
            text("SELECT COUNT(*) FROM postings"),
        ).scalar()
        assert posting_count == 2, f"Expected 2 postings, got {posting_count}"

        # Sum of postings must be 0
        rows = conn.execute(text("SELECT amount FROM postings")).fetchall()
        total = sum(Decimal(r[0]) for r in rows)
        assert total == Decimal("0"), f"Postings sum to {total}, expected 0"


def test_add_default_currency(tmp_path: Path, cli_runner: CliRunner) -> None:
    """Omitting --currency defaults to COP."""
    from pyfintracker.cli import app
    from pyfintracker.db import make_engine

    db_path = _init_and_seed(tmp_path, cli_runner)

    result = cli_runner.invoke(
        app,
        [
            "add",
            "--from",
            "Assets:Wallet",
            "--to",
            "Expenses:Food:Delivery",
            "--amount",
            "25000",
            "--description",
            "Snacks",
        ],
        env={"FIN_DB_PATH": str(db_path)},
    )
    assert result.exit_code == 0, result.stdout

    engine = make_engine(f"sqlite:///{db_path}")
    with engine.connect() as conn:
        currencies = conn.execute(
            text("SELECT DISTINCT currency FROM postings"),
        ).fetchall()
        for row in currencies:
            assert row[0] == "COP"


def test_add_invalid_from_account(tmp_path: Path, cli_runner: CliRunner) -> None:
    """Non-existent --from account exits with error."""
    from pyfintracker.cli import app

    db_path = _init_and_seed(tmp_path, cli_runner)

    result = cli_runner.invoke(
        app,
        [
            "add",
            "--from",
            "Assets:Nope",
            "--to",
            "Expenses:Food:Delivery",
            "--amount",
            "100",
            "--description",
            "Should fail",
        ],
        env={"FIN_DB_PATH": str(db_path)},
    )
    assert result.exit_code != 0


def test_add_invalid_to_account(tmp_path: Path, cli_runner: CliRunner) -> None:
    """Non-existent --to account exits with error."""
    from pyfintracker.cli import app

    db_path = _init_and_seed(tmp_path, cli_runner)

    result = cli_runner.invoke(
        app,
        [
            "add",
            "--from",
            "Assets:Wallet",
            "--to",
            "Income:Mystery",
            "--amount",
            "100",
            "--description",
            "Should fail",
        ],
        env={"FIN_DB_PATH": str(db_path)},
    )
    assert result.exit_code != 0
