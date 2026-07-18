"""Cross-cutting acceptance tests (proposal §13 — all scenarios).

Parametrized integration tests covering every acceptance criterion for
Wave 1 MVP.  Each scenario is a (args, expected_exit_code, expected_substr,
setup_fn) tuple where setup_fn prepares the DB state before invoking args.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest
from typer.testing import CliRunner

# ── Setup helpers ─────────────────────────────────────────────────────────────


def _no_setup(tmp_path: Path, cli_runner: CliRunner) -> None:
    """No setup needed."""


def _init(tmp_path: Path, cli_runner: CliRunner) -> None:
    """Run fin init to create a fresh database."""
    from pyfintracker.cli import app

    db_path = tmp_path / "fin" / "fin.db"
    result = cli_runner.invoke(app, ["init"], env={"FIN_DB_PATH": str(db_path)})
    assert result.exit_code == 0, result.stdout


def _init_and_seed(tmp_path: Path, cli_runner: CliRunner) -> None:
    """Init DB and create test accounts + transactions."""
    from pyfintracker.cli import app

    db_path = tmp_path / "fin" / "fin.db"
    _init(tmp_path, cli_runner)

    # Create custom accounts (not in starter chart)
    for acct in ["Assets:Wallet", "Expenses:Food:Delivery", "Income:Freelance"]:
        r = cli_runner.invoke(
            app, ["account", "new", acct, "--currency", "COP"],
            env={"FIN_DB_PATH": str(db_path)},
        )
        assert r.exit_code == 0, r.stdout

    # Add transactions
    r = cli_runner.invoke(
        app, [
            "add", "--from", "Income:Freelance", "--to", "Assets:Wallet",
            "--amount", "1000000", "--description", "Test income",
        ],
        env={"FIN_DB_PATH": str(db_path)},
    )
    assert r.exit_code == 0, r.stdout

    r2 = cli_runner.invoke(
        app, [
            "add", "--from", "Assets:Wallet", "--to", "Expenses:Food:Delivery",
            "--amount", "30000", "--description", "Test expense",
        ],
        env={"FIN_DB_PATH": str(db_path)},
    )
    assert r2.exit_code == 0, r2.stdout

    # Rewrite transaction dates to 2024-01 for predictable reports
    from sqlalchemy import text

    from pyfintracker.db import make_engine
    engine = make_engine(f"sqlite:///{db_path}")
    with engine.begin() as conn:
        conn.execute(text("UPDATE transactions SET date = '2024-01-15'"))


def _init_for_add_flag(tmp_path: Path, cli_runner: CliRunner) -> None:
    """Init DB and create the two accounts needed for the flag-mode add test."""
    from pyfintracker.cli import app

    db_path = tmp_path / "fin" / "fin.db"
    _init(tmp_path, cli_runner)

    # Create accounts that the flag mode add will use
    r = cli_runner.invoke(
        app, ["account", "new", "Assets:TestChecking", "--currency", "COP"],
        env={"FIN_DB_PATH": str(db_path)},
    )
    assert r.exit_code == 0, r.stdout
    r = cli_runner.invoke(
        app, ["account", "new", "Expenses:TestGroceries", "--currency", "COP"],
        env={"FIN_DB_PATH": str(db_path)},
    )
    assert r.exit_code == 0, r.stdout


# ── Scenario definitions ──────────────────────────────────────────────────────

Scenario = tuple[list[str], int, str, Callable[[Path, CliRunner], None]]

SCENARIOS: list[tuple[Any, ...]] = [
    pytest.param(
        ["init"], 0, "fin initialized", _no_setup,
        id="init-creates-db",
    ),
    pytest.param(
        ["init"], 0, "already initialized", _init,
        id="init-refuses-existing",
    ),
    pytest.param(
        ["init", "--force"], 0, "fin initialized", _init,
        id="init-force-rebuilds",
    ),
    pytest.param(
        ["account", "new", "Assets:TestCash"], 0, "created", _init,
        id="account-new-creates",
    ),
    pytest.param(
        ["account", "new", "INVALID"], 1, "Invalid", _init,
        id="account-new-invalid-name",
    ),
    pytest.param(
        ["account", "list"], 0, "Accounts", _init,
        id="account-list-shows",
    ),
    pytest.param(
        ["add", "--from", "Assets:TestChecking", "--to", "Expenses:TestGroceries",
         "--amount", "50000", "--description", "Integration test txn"],
        0, "Transaction", _init_for_add_flag,
        id="add-flag-mode-balanced",
    ),
    pytest.param(
        ["add"], 2, "REPL requires interactive terminal", _init,
        id="add-repl-non-tty",
    ),
    pytest.param(
        ["report", "month", "--month", "2024-01"], 0, "Monthly Report", _init_and_seed,
        id="report-month-shows",
    ),
    pytest.param(
        ["report", "balance"], 0, "Balance Report", _init_and_seed,
        id="balance-shows",
    ),
    pytest.param(
        ["version"], 0, "pyfintracker v", _no_setup,
        id="version-shows",
    ),
    pytest.param(
        ["migrate", "status"], 0, "0001", _init,
        id="migrate-status-shows",
    ),
]


# ── Test ──────────────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("args", "expected_exit", "expected_substr", "setup_fn"),
    SCENARIOS,
)
def test_acceptance_scenario(
    tmp_path: Path,
    cli_runner: CliRunner,
    args: list[str],
    expected_exit: int,
    expected_substr: str,
    setup_fn: Callable[[Path, CliRunner], None],
) -> None:
    """Run each acceptance scenario and verify exit code + output."""
    from pyfintracker.cli import app

    db_path = tmp_path / "fin" / "fin.db"

    # Run scenario-specific setup
    setup_fn(tmp_path, cli_runner)

    # Invoke the actual scenario
    result = cli_runner.invoke(
        app, args, env={"FIN_DB_PATH": str(db_path)},
    )
    assert result.exit_code == expected_exit, (
        f"Expected exit {expected_exit}, got {result.exit_code}. "
        f"stdout: {result.stdout!r}  stderr: {result.stderr!r}"
    )
    assert expected_substr in result.stdout + result.stderr, (
        f"Expected substring {expected_substr!r} not found. "
        f"stdout: {result.stdout!r}  stderr: {result.stderr!r}"
    )
