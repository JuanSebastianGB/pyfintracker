"""Integration tests for REPL transaction entry via CLI (contract e).

Tests T-5.6, T-5.8, T-5.9, T-5.11, T-5.12.

Uses TTYCliRunner — a CliRunner subclass that patches ``sys.stdin.isatty``
inside the isolation context so REPL mode works with programmatic input.
"""

from __future__ import annotations

import contextlib
import sys
from collections.abc import Iterator
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy import text
from typer.testing import CliRunner


class TTYCliRunner(CliRunner):
    """CliRunner that makes sys.stdin report as a TTY."""

    @contextlib.contextmanager
    def isolation(
        self, *args: Any, **kwargs: Any,
    ) -> Iterator[tuple[object, object, object]]:
        with super().isolation(*args, **kwargs) as outputs:
            # CliRunner replaces sys.stdin with a non-TTY _NamedTextIOWrapper.
            # Patch its isatty back to True so REPL TTY guard passes.
            sys.stdin.isatty = lambda: True  # type: ignore[method-assign]
            yield outputs


def _init_and_seed(tmp_path: Path, cli_runner: CliRunner) -> Path:
    """Initialize database and create test accounts.

    Uses accounts NOT in the starter chart (Assets:Cash and Income:Salary
    already exist from ``fin init``).
    """
    from pyfintracker.cli import app

    db_path = tmp_path / "fin" / "fin.db"
    result = cli_runner.invoke(app, ["init"], env={"FIN_DB_PATH": str(db_path)})
    assert result.exit_code == 0, result.stdout

    for acct in ["Assets:Wallet", "Expenses:Food", "Expenses:Drinks", "Income:Freelance"]:
        result = cli_runner.invoke(
            app, ["account", "new", acct, "--currency", "COP"],
            env={"FIN_DB_PATH": str(db_path)},
        )
        assert result.exit_code == 0, result.stdout

    return db_path


@pytest.fixture
def repl_runner() -> TTYCliRunner:
    """Return a CliRunner that makes stdin appear as a TTY."""
    return TTYCliRunner()


@pytest.mark.integration
class TestAddRepl:
    """T-5.6: CLI add dispatches to REPL when no flags."""

    def _get_postings(self, db_path: Path) -> list[Decimal]:
        """Fetch posting amounts from the database."""
        from pyfintracker.db import make_engine

        engine = make_engine(f"sqlite:///{db_path}")
        with engine.connect() as conn:
            rows = conn.execute(text("SELECT amount FROM postings")).fetchall()
            return [Decimal(r[0]) for r in rows]

    def _get_txn_count(self, db_path: Path) -> int:
        """Fetch transaction count from the database."""
        from pyfintracker.db import make_engine

        engine = make_engine(f"sqlite:///{db_path}")
        with engine.connect() as conn:
            return conn.execute(text("SELECT COUNT(*) FROM transactions")).scalar()

    def test_add_no_flags_enters_repl(self, tmp_path: Path, repl_runner: TTYCliRunner) -> None:
        """``fin add`` without flags enters REPL mode and creates a transaction."""
        from pyfintracker.cli import app

        db_path = _init_and_seed(tmp_path, repl_runner)

        input_data = "\n".join([
            "2024-01-15",       # date
            "Grocery run",       # description
            "COP",               # currency
            "Expenses:Food",     # account (created by _init_and_seed)
            "50000",
            "Assets:Wallet",     # account (created by _init_and_seed)
            "-50000",
        ])

        result = repl_runner.invoke(
            app, ["add"],
            input=input_data,
            env={"FIN_DB_PATH": str(db_path)},
        )

        assert result.exit_code == 0, result.stdout
        assert self._get_txn_count(db_path) >= 1
        total = sum(self._get_postings(db_path))
        assert total == Decimal("0")

    def test_repl_creates_balanced_txn(self, tmp_path: Path, repl_runner: TTYCliRunner) -> None:
        """T-5.8: REPL creates a balanced two-posting transaction."""
        from pyfintracker.cli import app

        db_path = _init_and_seed(tmp_path, repl_runner)

        input_data = "\n".join([
            "2024-01-15",
            "Grocery run",
            "COP",
            "Expenses:Food",
            "50000",
            "Assets:Wallet",
            "-50000",
        ])

        result = repl_runner.invoke(
            app, ["add"],
            input=input_data,
            env={"FIN_DB_PATH": str(db_path)},
        )

        assert result.exit_code == 0, result.stdout
        assert self._get_txn_count(db_path) == 1
        total = sum(self._get_postings(db_path))
        assert total == Decimal("0")

    def test_repl_abort_discards(self, tmp_path: Path, repl_runner: TTYCliRunner) -> None:
        """T-5.12: Abort via :abort discards the transaction (nothing saved)."""
        from pyfintracker.cli import app

        db_path = _init_and_seed(tmp_path, repl_runner)

        input_data = "\n".join([
            "2024-01-15",
            "Test",
            "COP",
            ":abort",
        ])

        result = repl_runner.invoke(
            app, ["add"],
            input=input_data,
            env={"FIN_DB_PATH": str(db_path)},
        )

        assert result.exit_code == 130, result.stdout
        assert self._get_txn_count(db_path) == 0

    def test_repl_three_postings(self, tmp_path: Path, repl_runner: TTYCliRunner) -> None:
        """T-5.9: 3-posting split payment balances correctly."""
        from pyfintracker.cli import app

        db_path = _init_and_seed(tmp_path, repl_runner)

        input_data = "\n".join([
            "2024-06-01",
            "Split dinner",
            "COP",
            "Expenses:Food",
            "30000",
            "Expenses:Drinks",
            "20000",
            "Assets:Wallet",
            "-50000",
        ])

        result = repl_runner.invoke(
            app, ["add"],
            input=input_data,
            env={"FIN_DB_PATH": str(db_path)},
        )

        assert result.exit_code == 0, result.stdout
        postings = self._get_postings(db_path)
        total = sum(postings)
        assert total == Decimal("0"), f"Postings sum to {total}"
        assert len(postings) == 3

    def test_repl_retries_unknown_account(self, tmp_path: Path, repl_runner: TTYCliRunner) -> None:
        """T-5.11: Unknown account shows error and retries."""
        from pyfintracker.cli import app

        db_path = _init_and_seed(tmp_path, repl_runner)

        # REPL always prompts Account → Amount.
        # After unknown "Expenses:Nope" + its amount, resolve fails → retry.
        input_data = "\n".join([
            "2024-01-15",
            "Test retry",
            "COP",
            "Expenses:Nope",     # Account → unknown, resolve error
            "50000",             # Amount (collected before resolve)
            "Expenses:Food",     # Account → known (retry after error)
            "50000",             # Amount
            "Assets:Wallet",     # Account
            "-50000",            # Amount
        ])

        result = repl_runner.invoke(
            app, ["add"],
            input=input_data,
            env={"FIN_DB_PATH": str(db_path)},
        )

        assert result.exit_code == 0, result.stdout
        assert "not found" in result.stdout.lower()
        total = sum(self._get_postings(db_path))
        assert total == Decimal("0")

    def test_repl_partial_flags_error(self, tmp_path: Path, cli_runner: CliRunner) -> None:
        """Partial flags (some but not all) show error."""
        from pyfintracker.cli import app

        db_path = _init_and_seed(tmp_path, cli_runner)

        result = cli_runner.invoke(
            app, ["add", "--from", "Assets:Wallet"],
            env={"FIN_DB_PATH": str(db_path)},
        )
        assert result.exit_code != 0
        assert "all flags" in result.stdout.lower()
