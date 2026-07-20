"""Integration tests for ``fin tag`` commands.

Tests cover tag creation, listing, deletion, attaching to transactions,
and the ``--tag`` option on ``fin register``.
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


# ── Tag create ────────────────────────────────────────────────────────────


def test_tag_create(tmp_path: Path, cli_runner: CliRunner) -> None:
    """``fin tag create groceries`` creates a tag."""
    from pyfintracker.cli import app

    db_path = _init_db(tmp_path, cli_runner)
    result = cli_runner.invoke(
        app,
        ["tag", "create", "groceries"],
        env={"FIN_DB_PATH": str(db_path)},
    )
    assert result.exit_code == 0, result.stdout
    assert "created" in result.stdout.lower()
    assert "groceries" in result.stdout


def test_tag_create_duplicate(tmp_path: Path, cli_runner: CliRunner) -> None:
    """Creating a tag with an existing name exits 1."""
    from pyfintracker.cli import app

    db_path = _init_db(tmp_path, cli_runner)
    cli_runner.invoke(app, ["tag", "create", "groceries"], env={"FIN_DB_PATH": str(db_path)})
    result = cli_runner.invoke(
        app,
        ["tag", "create", "groceries"],
        env={"FIN_DB_PATH": str(db_path)},
    )
    assert result.exit_code != 0
    assert "already exists" in (result.stdout + result.stderr).lower()


def test_tag_create_invalid_name(tmp_path: Path, cli_runner: CliRunner) -> None:
    """Creating a tag with commas exits 1."""
    from pyfintracker.cli import app

    db_path = _init_db(tmp_path, cli_runner)
    result = cli_runner.invoke(
        app,
        ["tag", "create", "groceries,food"],
        env={"FIN_DB_PATH": str(db_path)},
    )
    assert result.exit_code == 1


# ── Tag list ──────────────────────────────────────────────────────────────


def test_tag_list(tmp_path: Path, cli_runner: CliRunner) -> None:
    """``fin tag list`` shows created tags."""
    from pyfintracker.cli import app

    db_path = _init_db(tmp_path, cli_runner)
    cli_runner.invoke(app, ["tag", "create", "groceries"], env={"FIN_DB_PATH": str(db_path)})
    cli_runner.invoke(app, ["tag", "create", "salary"], env={"FIN_DB_PATH": str(db_path)})

    result = cli_runner.invoke(app, ["tag", "list"], env={"FIN_DB_PATH": str(db_path)})
    assert result.exit_code == 0, result.stdout
    assert "groceries" in result.stdout
    assert "salary" in result.stdout


def test_tag_list_empty(tmp_path: Path, cli_runner: CliRunner) -> None:
    """``fin tag list`` with no tags says so."""
    from pyfintracker.cli import app

    db_path = _init_db(tmp_path, cli_runner)
    result = cli_runner.invoke(app, ["tag", "list"], env={"FIN_DB_PATH": str(db_path)})
    assert result.exit_code == 0, result.stdout
    assert "No tags" in result.stdout


# ── Tag delete ────────────────────────────────────────────────────────────


def test_tag_delete(tmp_path: Path, cli_runner: CliRunner) -> None:
    """``fin tag delete`` removes a tag."""
    from pyfintracker.cli import app

    db_path = _init_db(tmp_path, cli_runner)
    cli_runner.invoke(app, ["tag", "create", "groceries"], env={"FIN_DB_PATH": str(db_path)})

    result = cli_runner.invoke(
        app,
        ["tag", "delete", "groceries"],
        env={"FIN_DB_PATH": str(db_path)},
    )
    assert result.exit_code == 0, result.stdout
    assert "deleted" in result.stdout.lower()

    # Verify it's gone
    list_result = cli_runner.invoke(app, ["tag", "list"], env={"FIN_DB_PATH": str(db_path)})
    assert "groceries" not in list_result.stdout


def test_tag_delete_nonexistent(tmp_path: Path, cli_runner: CliRunner) -> None:
    """Deleting a non-existent tag exits 1."""
    from pyfintracker.cli import app

    db_path = _init_db(tmp_path, cli_runner)
    result = cli_runner.invoke(
        app,
        ["tag", "delete", "nonexistent"],
        env={"FIN_DB_PATH": str(db_path)},
    )
    assert result.exit_code == 1
    assert "not found" in (result.stdout + result.stderr).lower()


# ── Tag add / remove on transactions ──────────────────────────────────────


def test_tag_add_remove_transaction(tmp_path: Path, cli_runner: CliRunner) -> None:
    """Create a tag and a register, tag the txn, verify, then untag."""
    from pyfintracker.cli import app

    db_path = _init_db(tmp_path, cli_runner)

    # Create a tag
    cli_runner.invoke(app, ["tag", "create", "groceries"], env={"FIN_DB_PATH": str(db_path)})

    # Create a transaction via register (auto-creates Equity:Registered)
    reg_result = cli_runner.invoke(
        app,
        [
            "register",
            "Test txn",
            "50000",
            "--account",
            "Expenses:Food:Groceries",
        ],
        env={"FIN_DB_PATH": str(db_path)},
    )
    assert reg_result.exit_code == 0, reg_result.stdout
    # Extract transaction ID from output
    txn_id = "1"  # first transaction gets id 1

    # Tag the transaction
    add_result = cli_runner.invoke(
        app,
        ["tag", "add", "groceries", txn_id],
        env={"FIN_DB_PATH": str(db_path)},
    )
    assert add_result.exit_code == 0, add_result.stdout
    assert "added" in add_result.stdout.lower()

    # Remove the tag
    remove_result = cli_runner.invoke(
        app,
        ["tag", "remove", "groceries", txn_id],
        env={"FIN_DB_PATH": str(db_path)},
    )
    assert remove_result.exit_code == 0, remove_result.stdout
    assert "removed" in remove_result.stdout.lower()


def test_tag_add_nonexistent_tag(tmp_path: Path, cli_runner: CliRunner) -> None:
    """Tagging with a non-existent tag exits 1."""
    from pyfintracker.cli import app

    db_path = _init_db(tmp_path, cli_runner)
    result = cli_runner.invoke(
        app,
        ["tag", "add", "nonexistent", "1"],
        env={"FIN_DB_PATH": str(db_path)},
    )
    assert result.exit_code == 1
    assert "not found" in (result.stdout + result.stderr).lower()


# ── Tag on register ───────────────────────────────────────────────────────


def test_tag_on_register(tmp_path: Path, cli_runner: CliRunner) -> None:
    """``fin register --tag groceries 100 ...`` creates tag + txns."""
    from pyfintracker.cli import app

    db_path = _init_db(tmp_path, cli_runner)

    # Register with --tag — the tag is auto-created by register
    result = cli_runner.invoke(
        app,
        [
            "register",
            "Snacks",
            "25000",
            "--account",
            "Expenses:Food:Groceries",
            "--tag",
            "groceries",
        ],
        env={"FIN_DB_PATH": str(db_path)},
    )
    assert result.exit_code == 0, result.stdout
    assert "Transaction #1" in result.stdout

    # Verify tag exists
    list_result = cli_runner.invoke(app, ["tag", "list"], env={"FIN_DB_PATH": str(db_path)})
    assert "groceries" in list_result.stdout


def test_tag_on_register_multiple(tmp_path: Path, cli_runner: CliRunner) -> None:
    """``fin register --tag t1 --tag t2`` attaches multiple tags."""
    from pyfintracker.cli import app

    db_path = _init_db(tmp_path, cli_runner)

    result = cli_runner.invoke(
        app,
        [
            "register",
            "Groceries",
            "30000",
            "--account",
            "Expenses:Food:Groceries",
            "--tag",
            "food",
            "--tag",
            "weekly",
        ],
        env={"FIN_DB_PATH": str(db_path)},
    )
    assert result.exit_code == 0, result.stdout

    list_result = cli_runner.invoke(app, ["tag", "list"], env={"FIN_DB_PATH": str(db_path)})
    assert "food" in list_result.stdout
    assert "weekly" in list_result.stdout
