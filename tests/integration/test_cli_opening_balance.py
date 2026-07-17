"""Tests for ``fin account new --initial`` opening balance (T-4.7).

Verifies that the synthetic opening balance transaction (debit new account,
credit Equity:OpeningBalances) is created atomically with sum=0.
"""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path

from sqlalchemy import text
from typer.testing import CliRunner


def _init_and_create(
    tmp_path: Path,
    cli_runner: CliRunner,
    account_name: str = "Assets:OpeningTest",
    currency: str = "COP",
    initial: str = "1000000",
) -> Path:
    """Initialize DB and create account with opening balance."""
    from pyfintracker.cli import app

    db_path = tmp_path / "fin" / "fin.db"
    result = cli_runner.invoke(app, ["init"], env={"FIN_DB_PATH": str(db_path)})
    assert result.exit_code == 0, result.stdout

    result = cli_runner.invoke(
        app,
        [
            "account", "new", account_name,
            "--currency", currency,
            "--initial", initial,
        ],
        env={"FIN_DB_PATH": str(db_path)},
    )
    assert result.exit_code == 0, result.stdout
    return db_path


def test_opening_balance_creates_transaction(
    tmp_path: Path, cli_runner: CliRunner,
) -> None:
    """``--initial`` creates an opening balance transaction with 2 postings."""
    from pyfintracker.db import make_engine

    db_path = _init_and_create(tmp_path, cli_runner)

    engine = make_engine(f"sqlite:///{db_path}")
    with engine.connect() as conn:
        # Verify account exists
        row = conn.execute(
            text("SELECT id, name, currency FROM accounts WHERE name = 'Assets:OpeningTest'"),
        ).fetchone()
        assert row is not None
        assert row.currency == "COP"

        # Find opening balance transaction
        txn_row = conn.execute(
            text("""
                SELECT t.id FROM transactions t
                JOIN postings p ON p.transaction_id = t.id
                WHERE p.account_id = :account_id
                AND t.description LIKE '%Opening%'
            """),
            {"account_id": row.id},
        ).fetchone()
        assert txn_row is not None, "Opening balance transaction not found"

        # Verify two postings sum to zero
        postings = conn.execute(
            text("SELECT amount FROM postings WHERE transaction_id = :txn_id"),
            {"txn_id": txn_row.id},
        ).fetchall()
        assert len(postings) == 2
        total = sum(Decimal(p.amount) for p in postings)
        assert total == Decimal("0")


def test_opening_balance_creates_equity_account(
    tmp_path: Path, cli_runner: CliRunner,
) -> None:
    """Equity:OpeningBalances is auto-created if it doesn't exist."""
    from pyfintracker.db import make_engine

    db_path = _init_and_create(tmp_path, cli_runner)

    engine = make_engine(f"sqlite:///{db_path}")
    with engine.connect() as conn:
        equity = conn.execute(
            text("SELECT id, name FROM accounts WHERE name = 'Equity:OpeningBalances'"),
        ).fetchone()
        assert equity is not None


def test_opening_balance_second_initial_fails(
    tmp_path: Path, cli_runner: CliRunner,
) -> None:
    """Second ``--initial`` on the same account is rejected."""
    from pyfintracker.cli import app

    db_path = _init_and_create(tmp_path, cli_runner, account_name="Assets:DoubleInit")

    # Second attempt with same account
    result = cli_runner.invoke(
        app,
        ["account", "new", "Assets:DoubleInit", "--initial", "500000"],
        env={"FIN_DB_PATH": str(db_path)},
    )
    assert result.exit_code != 0
    combined = (result.stdout + result.stderr).lower()
    assert (
        "already" in combined
        or "exists" in combined
        or "has postings" in combined
    )
