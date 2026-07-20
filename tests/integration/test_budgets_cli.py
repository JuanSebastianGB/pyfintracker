"""Integration tests for ``fin budget`` CLI commands.

Tests cover create, list, report, and delete operations through
the full CLI surface using ``CliRunner``.
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


def _create_account(tmp_path: Path, cli_runner: CliRunner, db_path: Path, name: str) -> None:
    """Create an account via CLI."""
    from pyfintracker.cli import app

    result = cli_runner.invoke(
        app,
        ["account", "new", name],
        env={"FIN_DB_PATH": str(db_path)},
    )
    assert result.exit_code == 0, result.stdout


# ── Create ─────────────────────────────────────────────────────────────────


def test_create_budget(tmp_path: Path, cli_runner: CliRunner) -> None:
    """Create a monthly budget → list shows it."""
    from pyfintracker.cli import app

    db_path = _init_db(tmp_path, cli_runner)

    result = cli_runner.invoke(
        app,
        [
            "budget", "create",
            "Groceries",
            "500000",
            "--period", "monthly",
            "--start-date", "2026-07-01",
        ],
        env={"FIN_DB_PATH": str(db_path)},
    )
    assert result.exit_code == 0, result.stdout
    assert "created" in result.stdout.lower()
    assert "Groceries" in result.stdout

    # Verify it appears in list
    list_result = cli_runner.invoke(app, ["budget", "list"], env={"FIN_DB_PATH": str(db_path)})
    assert list_result.exit_code == 0, list_result.stdout
    assert "Groceries" in list_result.stdout


def test_create_budget_invalid_period(tmp_path: Path, cli_runner: CliRunner) -> None:
    """Creating a budget with invalid period exits 1."""
    from pyfintracker.cli import app

    db_path = _init_db(tmp_path, cli_runner)
    result = cli_runner.invoke(
        app,
        [
            "budget", "create",
            "Bad",
            "1000",
            "--period", "weekly",
        ],
        env={"FIN_DB_PATH": str(db_path)},
    )
    assert result.exit_code == 1


# ── Spending ──────────────────────────────────────────────────────────────


def test_budget_spending(tmp_path: Path, cli_runner: CliRunner) -> None:
    """Create a budget, register a transaction → spending reflects it."""
    from pyfintracker.cli import app

    db_path = _init_db(tmp_path, cli_runner)
    _create_account(tmp_path, cli_runner, db_path, "Expenses:Food:Delivery")

    # Create budget
    cli_runner.invoke(
        app,
        [
            "budget", "create",
            "Delivery",
            "500000",
            "--period", "monthly",
            "--start-date", "2026-07-01",
        ],
        env={"FIN_DB_PATH": str(db_path)},
    )

    # Register a transaction
    reg = cli_runner.invoke(
        app,
        [
            "register", "Supermarket", "50000",
            "--account", "Expenses:Food:Delivery",
            "--date", "2026-07-15",
        ],
        env={"FIN_DB_PATH": str(db_path)},
    )
    assert reg.exit_code == 0, reg.stdout

    # Budget list should show spending
    list_result = cli_runner.invoke(app, ["budget", "list"], env={"FIN_DB_PATH": str(db_path)})
    assert list_result.exit_code == 0, list_result.stdout
    # The progress bar should contain non-empty indicators
    assert "50000" in list_result.stdout
    assert "Progress" in list_result.stdout


def test_budget_report_shows_spending(tmp_path: Path, cli_runner: CliRunner) -> None:
    """Budget report for a month with spending shows percentage."""
    from pyfintracker.cli import app

    db_path = _init_db(tmp_path, cli_runner)
    _create_account(tmp_path, cli_runner, db_path, "Expenses:Food:Delivery")

    cli_runner.invoke(
        app,
        [
            "budget", "create",
            "Grocery Budget",
            "200000",
            "--period", "monthly",
            "--start-date", "2026-07-01",
        ],
        env={"FIN_DB_PATH": str(db_path)},
    )

    cli_runner.invoke(
        app,
        [
            "register", "Market", "50000",
            "--account", "Expenses:Food:Delivery",
            "--date", "2026-07-15",
        ],
        env={"FIN_DB_PATH": str(db_path)},
    )

    report = cli_runner.invoke(
        app,
        ["budget", "report", "--month", "2026-07"],
        env={"FIN_DB_PATH": str(db_path)},
    )
    assert report.exit_code == 0, report.stdout
    assert "Grocery Budget" in report.stdout
    assert "%" in report.stdout


# ── Tag scope ─────────────────────────────────────────────────────────────


def test_budget_with_tag_scope(tmp_path: Path, cli_runner: CliRunner) -> None:
    """Budget scoped to a tag counts only tagged transactions."""
    from pyfintracker.cli import app

    db_path = _init_db(tmp_path, cli_runner)
    _create_account(tmp_path, cli_runner, db_path, "Expenses:Food:Delivery")

    # Create a tag
    tag_result = cli_runner.invoke(
        app, ["tag", "create", "food"],
        env={"FIN_DB_PATH": str(db_path)},
    )
    assert tag_result.exit_code == 0, tag_result.stdout

    # Get tag id — we know it's 1
    tag_id = "1"

    # Create budget scoped to tag
    cli_runner.invoke(
        app,
        [
            "budget", "create",
            "Food Budget",
            "300000",
            "--period", "monthly",
            "--tag", tag_id,
            "--start-date", "2026-07-01",
        ],
        env={"FIN_DB_PATH": str(db_path)},
    )

    # Register a tagged transaction
    cli_runner.invoke(
        app,
        [
            "register", "Lunch", "25000",
            "--account", "Expenses:Food:Delivery",
            "--date", "2026-07-15",
            "--tag", "food",
        ],
        env={"FIN_DB_PATH": str(db_path)},
    )

    # Register an untagged transaction (should NOT count)
    cli_runner.invoke(
        app,
        [
            "register", "Snacks", "10000",
            "--account", "Expenses:Food:Delivery",
            "--date", "2026-07-16",
        ],
        env={"FIN_DB_PATH": str(db_path)},
    )

    # Report should show the tagged amount
    report = cli_runner.invoke(
        app,
        ["budget", "report", "--month", "2026-07"],
        env={"FIN_DB_PATH": str(db_path)},
    )
    assert report.exit_code == 0, report.stdout
    assert "Food Budget" in report.stdout


# ── Over limit ────────────────────────────────────────────────────────────


def test_budget_report_over_limit(tmp_path: Path, cli_runner: CliRunner) -> None:
    """Budget with limit below spending shows over-budget."""
    from pyfintracker.cli import app

    db_path = _init_db(tmp_path, cli_runner)
    _create_account(tmp_path, cli_runner, db_path, "Expenses:Food:Delivery")

    # Small budget
    cli_runner.invoke(
        app,
        [
            "budget", "create",
            "Tight Budget",
            "10000",
            "--period", "monthly",
            "--start-date", "2026-07-01",
        ],
        env={"FIN_DB_PATH": str(db_path)},
    )

    # Big expense
    cli_runner.invoke(
        app,
        [
            "register", "Big Shop", "50000",
            "--account", "Expenses:Food:Delivery",
            "--date", "2026-07-15",
        ],
        env={"FIN_DB_PATH": str(db_path)},
    )

    report = cli_runner.invoke(
        app,
        ["budget", "report", "--month", "2026-07"],
        env={"FIN_DB_PATH": str(db_path)},
    )
    assert report.exit_code == 0, report.stdout
    assert "Tight Budget" in report.stdout
    assert "0.0" in report.stdout  # remaining should be 0


# ── Delete ────────────────────────────────────────────────────────────────


def test_delete_budget(tmp_path: Path, cli_runner: CliRunner) -> None:
    """Create then delete a budget → gone from list."""
    from pyfintracker.cli import app

    db_path = _init_db(tmp_path, cli_runner)

    cli_runner.invoke(
        app,
        [
            "budget", "create",
            "Temp Budget",
            "100000",
            "--period", "monthly",
            "--start-date", "2026-07-01",
        ],
        env={"FIN_DB_PATH": str(db_path)},
    )

    del_result = cli_runner.invoke(
        app,
        ["budget", "delete", "1"],
        env={"FIN_DB_PATH": str(db_path)},
    )
    assert del_result.exit_code == 0, del_result.stdout
    assert "deleted" in del_result.stdout.lower()

    # Verify gone
    list_result = cli_runner.invoke(app, ["budget", "list"], env={"FIN_DB_PATH": str(db_path)})
    assert "Temp Budget" not in list_result.stdout


def test_delete_nonexistent_budget(tmp_path: Path, cli_runner: CliRunner) -> None:
    """Deleting a non-existent budget exits 1."""
    from pyfintracker.cli import app

    db_path = _init_db(tmp_path, cli_runner)
    result = cli_runner.invoke(
        app,
        ["budget", "delete", "999"],
        env={"FIN_DB_PATH": str(db_path)},
    )
    assert result.exit_code == 1
    assert "not found" in (result.stdout + result.stderr).lower()
