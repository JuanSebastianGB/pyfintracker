"""Tests for ``fin report month`` command (T-6.6).

Covers default current month, specific month, invalid format, and
seeded-data rendering.
"""

from __future__ import annotations

from pathlib import Path

from typer.testing import CliRunner


def _init_and_seed(tmp_path: Path, cli_runner: CliRunner) -> Path:
    """Initialize database, create accounts, and add transactions for 2024-01."""
    from sqlalchemy import text

    from pyfintracker.cli import app
    from pyfintracker.db import make_engine

    db_path = tmp_path / "fin" / "fin.db"
    result = cli_runner.invoke(app, ["init"], env={"FIN_DB_PATH": str(db_path)})
    assert result.exit_code == 0, result.stdout

    # Create accounts for income and expense
    for acct in ["Income:Freelance", "Expenses:Groceries"]:
        result = cli_runner.invoke(
            app, ["account", "new", acct, "--currency", "COP"],
            env={"FIN_DB_PATH": str(db_path)},
        )
        assert result.exit_code == 0, result.stdout

    # Add transactions (they get today's date, so update to 2024-01 below)
    result = cli_runner.invoke(
        app, [
            "add", "--from", "Income:Freelance", "--to", "Assets:Checking",
            "--amount", "2000000", "--description", "Freelance payment Jan",
        ],
        env={"FIN_DB_PATH": str(db_path)},
    )
    assert result.exit_code == 0, result.stdout

    result = cli_runner.invoke(
        app, [
            "add", "--from", "Assets:Checking", "--to", "Expenses:Groceries",
            "--amount", "150000", "--description", "Weekly groceries",
        ],
        env={"FIN_DB_PATH": str(db_path)},
    )
    assert result.exit_code == 0, result.stdout

    # Rewrite transaction dates to 2024-01 so month filter finds them
    engine = make_engine(f"sqlite:///{db_path}")
    with engine.begin() as conn:
        conn.execute(
            text("UPDATE transactions SET date = '2024-01-15'")
        )

    return db_path


# ── T-6.6: report month ───────────────────────────────────────────────────────


def test_report_month_default(tmp_path: Path, cli_runner: CliRunner) -> None:
    """``fin report month`` (no args) exits 0 with current month header."""
    from pyfintracker.cli import app

    db_path = _init_and_seed(tmp_path, cli_runner)

    result = cli_runner.invoke(
        app, ["report", "month"],
        env={"FIN_DB_PATH": str(db_path)},
    )
    assert result.exit_code == 0, result.stdout
    assert "Monthly Report" in result.stdout


def test_report_month_specific(tmp_path: Path, cli_runner: CliRunner) -> None:
    """``fin report month --month 2024-01`` shows that month's report."""
    from pyfintracker.cli import app

    db_path = _init_and_seed(tmp_path, cli_runner)

    result = cli_runner.invoke(
        app, ["report", "month", "--month", "2024-01"],
        env={"FIN_DB_PATH": str(db_path)},
    )
    assert result.exit_code == 0, result.stdout
    assert "Monthly Report — 2024-01" in result.stdout
    assert "Income" in result.stdout
    assert "Expenses" in result.stdout


def test_report_month_shows_amounts(tmp_path: Path, cli_runner: CliRunner) -> None:
    """Report includes income and expense amounts."""
    from pyfintracker.cli import app

    db_path = _init_and_seed(tmp_path, cli_runner)

    result = cli_runner.invoke(
        app, ["report", "month", "--month", "2024-01"],
        env={"FIN_DB_PATH": str(db_path)},
    )
    assert result.exit_code == 0, result.stdout
    # Income of 2,000,000 should appear
    assert "2,000,000" in result.stdout or "2000000" in result.stdout
    # Expense of 150,000 should appear
    assert "150,000" in result.stdout or "150000" in result.stdout


def test_report_month_invalid_format(tmp_path: Path, cli_runner: CliRunner) -> None:
    """Invalid --month format exits 1 with error message."""
    from pyfintracker.cli import app

    db_path = _init_and_seed(tmp_path, cli_runner)

    result = cli_runner.invoke(
        app, ["report", "month", "--month", "2024/01"],
        env={"FIN_DB_PATH": str(db_path)},
    )
    assert result.exit_code == 1, result.stdout
    assert "2024/01" in result.stdout


def test_report_month_bad_format(tmp_path: Path, cli_runner: CliRunner) -> None:
    """``--month 2024-1`` (missing leading zero) exits 1."""
    from pyfintracker.cli import app

    db_path = _init_and_seed(tmp_path, cli_runner)

    result = cli_runner.invoke(
        app, ["report", "month", "--month", "2024-1"],
        env={"FIN_DB_PATH": str(db_path)},
    )
    assert result.exit_code == 1, result.stdout


def test_report_month_non_numeric(tmp_path: Path, cli_runner: CliRunner) -> None:
    """``--month abc-def`` exits 1."""
    from pyfintracker.cli import app

    db_path = _init_and_seed(tmp_path, cli_runner)

    result = cli_runner.invoke(
        app, ["report", "month", "--month", "abc-def"],
        env={"FIN_DB_PATH": str(db_path)},
    )
    assert result.exit_code == 1, result.stdout
