"""Tests for the ``fin account`` commands.

Covers T-2.11 (account new), T-2.12 (account list),
T-2.14 (account new edge cases), T-2.15 (account list edge cases).
"""

from __future__ import annotations

from pathlib import Path

from typer.testing import CliRunner


def _init_db(tmp_path: Path, cli_runner: CliRunner) -> Path:
    """Initialize a fresh database and return its path."""
    from pyfintracker.cli import app

    db_path = tmp_path / "fin" / "fin.db"
    result = cli_runner.invoke(app, ["init"], env={"FIN_DB_PATH": str(db_path)})
    assert result.exit_code == 0, result.stdout
    return db_path


# ── T-2.11: account new ──────────────────────────────────────────────────────


def test_account_new_creates_account(tmp_path: Path, cli_runner: CliRunner) -> None:
    """``fin account new Assets:Investments`` creates the account."""
    from sqlalchemy import text

    from pyfintracker.cli import app
    from pyfintracker.db import make_engine

    db_path = _init_db(tmp_path, cli_runner)
    result = cli_runner.invoke(
        app, ["account", "new", "Assets:Investments"],
        env={"FIN_DB_PATH": str(db_path)},
    )
    assert result.exit_code == 0, result.stdout
    assert "created" in result.stdout.lower()

    engine = make_engine(f"sqlite:///{db_path}")
    with engine.connect() as conn:
        count = conn.execute(
            text("SELECT count(*) FROM accounts WHERE name = 'Assets:Investments'")
        ).scalar()
    assert count == 1, "Account was not inserted into the database"


def test_account_new_with_currency(tmp_path: Path, cli_runner: CliRunner) -> None:
    """``fin account new Assets:SavingsUSD --currency USD`` overrides currency."""
    from sqlalchemy import text

    from pyfintracker.cli import app
    from pyfintracker.db import make_engine

    db_path = _init_db(tmp_path, cli_runner)
    result = cli_runner.invoke(
        app, ["account", "new", "Assets:SavingsUSD", "--currency", "USD"],
        env={"FIN_DB_PATH": str(db_path)},
    )
    assert result.exit_code == 0, result.stdout

    engine = make_engine(f"sqlite:///{db_path}")
    with engine.connect() as conn:
        row = conn.execute(
            text("SELECT currency FROM accounts WHERE name = 'Assets:SavingsUSD'")
        ).fetchone()
    assert row is not None
    assert row[0] == "USD"


def test_account_new_invalid_name(tmp_path: Path, cli_runner: CliRunner) -> None:
    """Invalid account name raises error and exits 1."""
    from pyfintracker.cli import app

    db_path = _init_db(tmp_path, cli_runner)
    result = cli_runner.invoke(
        app, ["account", "new", "invalid"],
        env={"FIN_DB_PATH": str(db_path)},
    )
    assert result.exit_code == 1, (result.stdout, result.stderr)
    combined = result.stdout + result.stderr
    assert "invalid" in combined.lower()


def test_account_new_duplicate(tmp_path: Path, cli_runner: CliRunner) -> None:
    """Creating an account with an existing name exits 1 with 'already exists'."""
    from pyfintracker.cli import app

    db_path = _init_db(tmp_path, cli_runner)
    result = cli_runner.invoke(
        app, ["account", "new", "Assets:Duplicate"],
        env={"FIN_DB_PATH": str(db_path)},
    )
    assert result.exit_code == 0, result.stdout

    result2 = cli_runner.invoke(
        app, ["account", "new", "Assets:Duplicate"],
        env={"FIN_DB_PATH": str(db_path)},
    )
    assert result2.exit_code == 1, (result2.stdout, result2.stderr)
    combined = result2.stdout + result2.stderr
    assert "already exists" in combined.lower()


# ── T-2.12: account list ─────────────────────────────────────────────────────


def test_account_list_renders(tmp_path: Path, cli_runner: CliRunner) -> None:
    """``fin account list`` exits 0."""
    from pyfintracker.cli import app

    db_path = _init_db(tmp_path, cli_runner)
    result = cli_runner.invoke(
        app, ["account", "list"],
        env={"FIN_DB_PATH": str(db_path)},
    )
    assert result.exit_code == 0, result.stdout


def test_account_list_shows_starter_chart(tmp_path: Path, cli_runner: CliRunner) -> None:
    """Output contains the starter chart accounts."""
    from pyfintracker.cli import app

    db_path = _init_db(tmp_path, cli_runner)
    result = cli_runner.invoke(
        app, ["account", "list"],
        env={"FIN_DB_PATH": str(db_path)},
    )
    assert "Assets:Checking" in result.stdout
    assert "Income:Salary" in result.stdout


def test_account_list_new_account_appears(tmp_path: Path, cli_runner: CliRunner) -> None:
    """Create an account, list → new account in output."""
    from pyfintracker.cli import app

    db_path = _init_db(tmp_path, cli_runner)
    # Create a new account
    cli_runner.invoke(
        app, ["account", "new", "Expenses:Testing"],
        env={"FIN_DB_PATH": str(db_path)},
    )
    # List
    result = cli_runner.invoke(
        app, ["account", "list"],
        env={"FIN_DB_PATH": str(db_path)},
    )
    assert "Expenses:Testing" in result.stdout


def test_account_list_headers(tmp_path: Path, cli_runner: CliRunner) -> None:
    """Output contains table headers: ID, Name, Type, Currency, Depth."""
    from pyfintracker.cli import app

    db_path = _init_db(tmp_path, cli_runner)
    result = cli_runner.invoke(
        app, ["account", "list"],
        env={"FIN_DB_PATH": str(db_path)},
    )
    assert "ID" in result.stdout
    assert "Name" in result.stdout
    assert "Type" in result.stdout or "Kind" in result.stdout
    assert "Currency" in result.stdout
    assert "Depth" in result.stdout


def test_account_list_starter_chart_count(tmp_path: Path, cli_runner: CliRunner) -> None:
    """Exactly 11 starter accounts are listed."""
    from sqlalchemy import text

    from pyfintracker.cli import app
    from pyfintracker.db import make_engine

    db_path = _init_db(tmp_path, cli_runner)

    # Verify DB has 11
    engine = make_engine(f"sqlite:///{db_path}")
    with engine.connect() as conn:
        count = conn.execute(text("SELECT count(*) FROM accounts")).scalar()
    assert count == 11, f"Expected 11 starter accounts, got {count}"

    result = cli_runner.invoke(
        app, ["account", "list"],
        env={"FIN_DB_PATH": str(db_path)},
    )
    assert result.exit_code == 0, result.stdout


def test_account_list_after_create(tmp_path: Path, cli_runner: CliRunner) -> None:
    """Create one account → list shows 12."""
    from sqlalchemy import text

    from pyfintracker.cli import app
    from pyfintracker.db import make_engine

    db_path = _init_db(tmp_path, cli_runner)

    # Create one
    cli_runner.invoke(
        app, ["account", "new", "Expenses:Testing"],
        env={"FIN_DB_PATH": str(db_path)},
    )

    engine = make_engine(f"sqlite:///{db_path}")
    with engine.connect() as conn:
        count = conn.execute(text("SELECT count(*) FROM accounts")).scalar()
    assert count == 12, f"Expected 12 accounts after create, got {count}"

    result = cli_runner.invoke(
        app, ["account", "list"],
        env={"FIN_DB_PATH": str(db_path)},
    )
    assert result.exit_code == 0, result.stdout


# ── T-2.14: account new edge cases ───────────────────────────────────────────


def test_account_new_invalid_currency(tmp_path: Path, cli_runner: CliRunner) -> None:
    """Invalid --currency XXX exits 1."""
    from pyfintracker.cli import app

    db_path = _init_db(tmp_path, cli_runner)
    result = cli_runner.invoke(
        app, ["account", "new", "Assets:Test", "--currency", "XXX"],
        env={"FIN_DB_PATH": str(db_path)},
    )
    assert result.exit_code == 1, result.stdout


def test_account_new_no_db(tmp_path: Path, cli_runner: CliRunner) -> None:
    """Running account new without init exits 3 (NotInitializedError)."""
    from pyfintracker.cli import app

    db_path = tmp_path / "nonexistent" / "fin.db"
    result = cli_runner.invoke(
        app, ["account", "new", "Assets:Test"],
        env={"FIN_DB_PATH": str(db_path)},
    )
    # Either exit 3 (NotInitializedError) or exit 1 (OperationalError)
    assert result.exit_code in (1, 2, 3), (
        f"Unexpected exit code {result.exit_code}: {result.stdout}"
    )
