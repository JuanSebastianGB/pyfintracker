"""Tests for ``fin report balance`` command (T-6.7).

Covers balance report rendering, account name filtering, and edge
cases.
"""

from __future__ import annotations

from pathlib import Path

from typer.testing import CliRunner


def _init_and_seed(tmp_path: Path, cli_runner: CliRunner) -> Path:
    """Initialize database, create accounts with opening balances."""
    from pyfintracker.cli import app

    db_path = tmp_path / "fin" / "fin.db"
    result = cli_runner.invoke(app, ["init"], env={"FIN_DB_PATH": str(db_path)})
    assert result.exit_code == 0, result.stdout

    # Create accounts with opening balances (avoiding starter-chart names)
    result = cli_runner.invoke(
        app,
        [
            "account",
            "new",
            "Assets:Wallet",
            "--currency",
            "COP",
            "--initial",
            "500000",
        ],
        env={"FIN_DB_PATH": str(db_path)},
    )
    assert result.exit_code == 0, result.stdout

    result = cli_runner.invoke(
        app,
        [
            "account",
            "new",
            "Assets:EmergencyFund",
            "--currency",
            "COP",
            "--initial",
            "2000000",
        ],
        env={"FIN_DB_PATH": str(db_path)},
    )
    assert result.exit_code == 0, result.stdout

    result = cli_runner.invoke(
        app,
        [
            "account",
            "new",
            "Liabilities:TravelCard",
            "--currency",
            "COP",
            "--initial",
            "-300000",  # liability = credit balance
        ],
        env={"FIN_DB_PATH": str(db_path)},
    )
    assert result.exit_code == 0, result.stdout

    return db_path


# ── T-6.7: report balance ────────────────────────────────────────────────────


def test_balance_default(tmp_path: Path, cli_runner: CliRunner) -> None:
    """``fin report balance`` exits 0 and shows Balance Report."""
    from pyfintracker.cli import app

    db_path = _init_and_seed(tmp_path, cli_runner)

    result = cli_runner.invoke(
        app,
        ["report", "balance"],
        env={"FIN_DB_PATH": str(db_path)},
    )
    assert result.exit_code == 0, result.stdout
    assert "Balance Report" in result.stdout


def test_balance_shows_accounts(tmp_path: Path, cli_runner: CliRunner) -> None:
    """Balance report lists created accounts with balances."""
    from pyfintracker.cli import app

    db_path = _init_and_seed(tmp_path, cli_runner)

    result = cli_runner.invoke(
        app,
        ["report", "balance"],
        env={"FIN_DB_PATH": str(db_path)},
    )
    assert result.exit_code == 0, result.stdout
    assert "Wallet" in result.stdout
    assert "EmergencyFund" in result.stdout
    assert "TravelCard" in result.stdout


def test_balance_shows_net_worth(tmp_path: Path, cli_runner: CliRunner) -> None:
    """Balance report includes net worth."""
    from pyfintracker.cli import app

    db_path = _init_and_seed(tmp_path, cli_runner)

    result = cli_runner.invoke(
        app,
        ["report", "balance"],
        env={"FIN_DB_PATH": str(db_path)},
    )
    assert result.exit_code == 0, result.stdout
    assert "Net worth" in result.stdout


def test_balance_filter(tmp_path: Path, cli_runner: CliRunner) -> None:
    """``fin report balance Wallet`` shows only Wallet account."""
    from pyfintracker.cli import app

    db_path = _init_and_seed(tmp_path, cli_runner)

    result = cli_runner.invoke(
        app,
        ["report", "balance", "Wallet"],
        env={"FIN_DB_PATH": str(db_path)},
    )
    assert result.exit_code == 0, result.stdout
    assert "Wallet" in result.stdout
    # EmergencyFund should NOT appear (filtered out)
    assert "EmergencyFund" not in result.stdout
    assert "Net worth" in result.stdout


def test_balance_filter_case_insensitive(tmp_path: Path, cli_runner: CliRunner) -> None:
    """``fin report balance emergencyfund`` (lowercase) matches EmergencyFund."""
    from pyfintracker.cli import app

    db_path = _init_and_seed(tmp_path, cli_runner)

    result = cli_runner.invoke(
        app,
        ["report", "balance", "emergencyfund"],
        env={"FIN_DB_PATH": str(db_path)},
    )
    assert result.exit_code == 0, result.stdout
    assert "EmergencyFund" in result.stdout


def test_balance_filter_no_match(tmp_path: Path, cli_runner: CliRunner) -> None:
    """Non-matching filter shows only net worth (no account lines)."""
    from pyfintracker.cli import app

    db_path = _init_and_seed(tmp_path, cli_runner)

    result = cli_runner.invoke(
        app,
        ["report", "balance", "Nonexistent"],
        env={"FIN_DB_PATH": str(db_path)},
    )
    assert result.exit_code == 0, result.stdout
    assert "Net worth" in result.stdout


def test_balance_includes_starter_checking(tmp_path: Path, cli_runner: CliRunner) -> None:
    """Assets:Checking (starter chart, no balance) does not appear (zero omitted)."""
    from pyfintracker.cli import app

    db_path = _init_and_seed(tmp_path, cli_runner)

    result = cli_runner.invoke(
        app,
        ["report", "balance"],
        env={"FIN_DB_PATH": str(db_path)},
    )
    # Assets:Checking has zero balance, so it should not appear
    assert "Checking" not in result.stdout
