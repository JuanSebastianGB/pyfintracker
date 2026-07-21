"""Integration tests for ``fin recurring`` CLI commands.

Tests cover create, list, due, generate, and delete operations
through the full CLI surface using ``CliRunner``.
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


def test_create_rule(tmp_path: Path, cli_runner: CliRunner) -> None:
    """Create a monthly recurring rule → list shows it."""
    from pyfintracker.cli import app

    db_path = _init_db(tmp_path, cli_runner)
    _create_account(tmp_path, cli_runner, db_path, "Expenses:TestRent")

    result = cli_runner.invoke(
        app,
        [
            "recurring",
            "create",
            "Monthly Rent",
            "monthly",
            "1200000",
            "Expenses:TestRent",
            "--description",
            "Office rent",
            "--start-date",
            "2026-07-01",
            "--currency",
            "COP",
        ],
        env={"FIN_DB_PATH": str(db_path)},
    )
    assert result.exit_code == 0, result.stdout
    assert "created" in result.stdout.lower()
    assert "Monthly Rent" in result.stdout

    # Verify it appears in list
    list_result = cli_runner.invoke(app, ["recurring", "list"], env={"FIN_DB_PATH": str(db_path)})
    assert list_result.exit_code == 0, list_result.stdout
    assert "Monthly Rent" in list_result.stdout


def test_create_rule_invalid_frequency(tmp_path: Path, cli_runner: CliRunner) -> None:
    """Creating a rule with invalid frequency exits 1."""
    from pyfintracker.cli import app

    db_path = _init_db(tmp_path, cli_runner)
    result = cli_runner.invoke(
        app,
        [
            "recurring",
            "create",
            "Bad",
            "fortnightly",
            "1000",
            "Expenses:TestRent",
        ],
        env={"FIN_DB_PATH": str(db_path)},
    )
    assert result.exit_code == 1


# ── Due ────────────────────────────────────────────────────────────────────


def test_due_rules(tmp_path: Path, cli_runner: CliRunner) -> None:
    """Rule with start_date=yesterday appears in due list."""
    from pyfintracker.cli import app

    db_path = _init_db(tmp_path, cli_runner)
    _create_account(tmp_path, cli_runner, db_path, "Expenses:TestRent")

    cli_runner.invoke(
        app,
        [
            "recurring",
            "create",
            "Rent",
            "monthly",
            "1200000",
            "Expenses:TestRent",
            "--start-date",
            "2026-06-01",
        ],
        env={"FIN_DB_PATH": str(db_path)},
    )

    result = cli_runner.invoke(
        app,
        ["recurring", "due", "--date", "2026-07-20"],
        env={"FIN_DB_PATH": str(db_path)},
    )
    assert result.exit_code == 0, result.stdout
    assert "Rent" in result.stdout


def test_no_due_rules(tmp_path: Path, cli_runner: CliRunner) -> None:
    """Rule with future start_date → empty due list."""
    from pyfintracker.cli import app

    db_path = _init_db(tmp_path, cli_runner)
    _create_account(tmp_path, cli_runner, db_path, "Expenses:TestRent")

    cli_runner.invoke(
        app,
        [
            "recurring",
            "create",
            "Rent",
            "monthly",
            "1200000",
            "Expenses:TestRent",
            "--start-date",
            "2026-08-01",
        ],
        env={"FIN_DB_PATH": str(db_path)},
    )

    result = cli_runner.invoke(
        app,
        ["recurring", "due", "--date", "2026-07-20"],
        env={"FIN_DB_PATH": str(db_path)},
    )
    assert result.exit_code == 0, result.stdout
    assert "No rules due" in result.stdout


# ── List empty ─────────────────────────────────────────────────────────────


def test_list_empty(tmp_path: Path, cli_runner: CliRunner) -> None:
    """``fin recurring list`` with no rules says so."""
    from pyfintracker.cli import app

    db_path = _init_db(tmp_path, cli_runner)
    result = cli_runner.invoke(app, ["recurring", "list"], env={"FIN_DB_PATH": str(db_path)})
    assert result.exit_code == 0, result.stdout
    assert "No recurring rules" in result.stdout


# ── Generate ───────────────────────────────────────────────────────────────


def test_generate_transactions(tmp_path: Path, cli_runner: CliRunner) -> None:
    """Create a due rule → generate → 1 transaction created, next_date advances."""
    from pyfintracker.cli import app

    db_path = _init_db(tmp_path, cli_runner)
    _create_account(tmp_path, cli_runner, db_path, "Expenses:TestGenerate")

    cli_runner.invoke(
        app,
        [
            "recurring",
            "create",
            "Rent",
            "monthly",
            "1200000",
            "Expenses:TestGenerate",
            "--start-date",
            "2026-07-01",
        ],
        env={"FIN_DB_PATH": str(db_path)},
    )

    # Generate on a due date
    gen_result = cli_runner.invoke(
        app,
        ["recurring", "generate", "--date", "2026-07-31"],
        env={"FIN_DB_PATH": str(db_path)},
    )
    assert gen_result.exit_code == 0, gen_result.stdout
    assert "Generated" in gen_result.stdout
    assert "1" in gen_result.stdout

    # After generation, next_date should have advanced to August
    list_result = cli_runner.invoke(app, ["recurring", "list"], env={"FIN_DB_PATH": str(db_path)})
    assert "2026-08-01" in list_result.stdout


def test_generate_no_due_rules(tmp_path: Path, cli_runner: CliRunner) -> None:
    """No due rules → generate says no."""
    from pyfintracker.cli import app

    db_path = _init_db(tmp_path, cli_runner)
    result = cli_runner.invoke(
        app,
        ["recurring", "generate", "--date", "2026-07-31"],
        env={"FIN_DB_PATH": str(db_path)},
    )
    assert result.exit_code == 0, result.stdout
    assert "No due rules" in result.stdout


# ── Delete ─────────────────────────────────────────────────────────────────


def test_delete_rule(tmp_path: Path, cli_runner: CliRunner) -> None:
    """Create then delete a rule → gone from list."""
    from pyfintracker.cli import app

    db_path = _init_db(tmp_path, cli_runner)
    _create_account(tmp_path, cli_runner, db_path, "Expenses:TestDelete")

    cli_runner.invoke(
        app,
        [
            "recurring",
            "create",
            "Rent",
            "monthly",
            "1200000",
            "Expenses:TestDelete",
            "--start-date",
            "2026-07-01",
        ],
        env={"FIN_DB_PATH": str(db_path)},
    )

    del_result = cli_runner.invoke(
        app,
        ["recurring", "delete", "1"],
        env={"FIN_DB_PATH": str(db_path)},
    )
    assert del_result.exit_code == 0, del_result.stdout
    assert "deleted" in del_result.stdout.lower()

    # Verify gone from list
    list_result = cli_runner.invoke(app, ["recurring", "list"], env={"FIN_DB_PATH": str(db_path)})
    assert "Rent" not in list_result.stdout


def test_delete_nonexistent_rule(tmp_path: Path, cli_runner: CliRunner) -> None:
    """Deleting a non-existent rule exits 1."""
    from pyfintracker.cli import app

    db_path = _init_db(tmp_path, cli_runner)
    result = cli_runner.invoke(
        app,
        ["recurring", "delete", "999"],
        env={"FIN_DB_PATH": str(db_path)},
    )
    assert result.exit_code == 1
    assert "not found" in (result.stdout + result.stderr).lower()
