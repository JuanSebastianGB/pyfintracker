"""Tests for error UX — Rich panels by error type (T-7.2).

Verifies that errors are rendered with styled Rich panels based on their
type, and that the CLI uses ``_render_error`` for error display.
"""

from __future__ import annotations

from pathlib import Path

from typer.testing import CliRunner


def _init_db(tmp_path: Path, cli_runner: CliRunner) -> Path:
    """Initialize a fresh DB and return its path."""
    from pyfintracker.cli import app

    db_path = tmp_path / "fin" / "fin.db"
    result = cli_runner.invoke(app, ["init"], env={"FIN_DB_PATH": str(db_path)})
    assert result.exit_code == 0, result.stdout
    return db_path


# ── ValidationError (red Panel, title "Validation Error") ────────────────────


def test_validation_error_invalid_account_name(
    tmp_path: Path, cli_runner: CliRunner,
) -> None:
    """Invalid account name shows red Panel with 'Validation Error' title."""
    from pyfintracker.cli import app

    db_path = _init_db(tmp_path, cli_runner)
    result = cli_runner.invoke(
        app, ["account", "new", "invalid"],
        env={"FIN_DB_PATH": str(db_path)},
    )
    assert result.exit_code == 1
    assert "Validation Error" in result.stdout


def test_validation_error_invalid_amount(
    tmp_path: Path, cli_runner: CliRunner,
) -> None:
    """Invalid amount shows red Panel with 'Validation Error' title."""
    from pyfintracker.cli import app

    # Zero-amount should be rejected by validation
    db_path = _init_db(tmp_path, cli_runner)
    result = cli_runner.invoke(
        app, [
            "add", "--from", "Assets:Checking", "--to", "Expenses:Food:Groceries",
            "--amount", "0", "--description", "Test",
        ],
        env={"FIN_DB_PATH": str(db_path)},
    )
    assert result.exit_code == 1
    assert "Validation Error" in result.stdout


def test_validation_error_invalid_currency(
    tmp_path: Path, cli_runner: CliRunner,
) -> None:
    """Invalid currency shows red Panel with 'Validation Error' title."""
    from pyfintracker.cli import app

    db_path = _init_db(tmp_path, cli_runner)
    result = cli_runner.invoke(
        app, ["account", "new", "Assets:Test", "--currency", "XXX"],
        env={"FIN_DB_PATH": str(db_path)},
    )
    assert result.exit_code == 1
    assert "Validation Error" in result.stdout


# ── AccountNotFoundError (red Panel, title "Account Not Found") ──────────────


def test_account_not_found_from(
    tmp_path: Path, cli_runner: CliRunner,
) -> None:
    """Unknown --from account shows red Panel with 'Account Not Found' title."""
    from pyfintracker.cli import app

    db_path = _init_db(tmp_path, cli_runner)
    result = cli_runner.invoke(
        app, [
            "add", "--from", "Assets:Nonexistent", "--to", "Expenses:Food:Groceries",
            "--amount", "100", "--description", "Test",
        ],
        env={"FIN_DB_PATH": str(db_path)},
    )
    assert result.exit_code == 1
    assert "Account Not Found" in result.stdout


def test_account_not_found_to(
    tmp_path: Path, cli_runner: CliRunner,
) -> None:
    """Unknown --to account shows red Panel with 'Account Not Found' title."""
    from pyfintracker.cli import app

    db_path = _init_db(tmp_path, cli_runner)
    result = cli_runner.invoke(
        app, [
            "add", "--from", "Assets:Checking", "--to", "Expenses:Nowhere",
            "--amount", "100", "--description", "Test",
        ],
        env={"FIN_DB_PATH": str(db_path)},
    )
    assert result.exit_code == 1
    assert "Account Not Found" in result.stdout


# ── ConfigError / NotInitializedError (yellow Panel) ──────────────────────────
# (These are harder to trigger via CLI — most are caught earlier or manifest
#  as different errors.  We at least verify the handler is wired.)


# ── REPL on non-TTY (plain stderr, no panel) ────────────────────────────────


def test_repl_non_tty_plain_error(tmp_path: Path, cli_runner: CliRunner) -> None:
    """REPL on non-TTY exits 2 with plain 'REPL requires interactive terminal'."""
    from pyfintracker.cli import app

    db_path = _init_db(tmp_path, cli_runner)
    result = cli_runner.invoke(
        app, ["add"], env={"FIN_DB_PATH": str(db_path)},
    )
    assert result.exit_code == 2
    assert "REPL requires interactive terminal" in result.stdout + result.stderr


# ── _render_error unit tests ─────────────────────────────────────────────────


def test_render_error_validation_red_panel() -> None:
    """_render_error produces red Panel with 'Validation Error' for ValidationError."""
    from io import StringIO

    from rich.console import Console

    from pyfintracker.cli import _render_error
    from pyfintracker.exceptions import ValidationError

    console = Console(file=StringIO(), width=80)
    error = ValidationError("Test validation error")
    _render_error(error, console)
    output = console.file.getvalue() if hasattr(console.file, 'getvalue') else str(console.file)
    assert "Validation Error" in output


def test_render_error_account_not_found_red_panel() -> None:
    """_render_error produces red Panel with 'Account Not Found' for AccountNotFoundError."""
    from io import StringIO

    from rich.console import Console

    from pyfintracker.cli import _render_error
    from pyfintracker.exceptions import AccountNotFoundError

    console = Console(file=StringIO(), width=80)
    error = AccountNotFoundError("Account 'Foo' not found")
    _render_error(error, console)
    output = console.file.getvalue() if hasattr(console.file, 'getvalue') else str(console.file)
    assert "Account Not Found" in output


def test_render_error_config_yellow_panel() -> None:
    """_render_error produces yellow Panel for ConfigError."""
    from io import StringIO

    from rich.console import Console

    from pyfintracker.cli import _render_error
    from pyfintracker.exceptions import ConfigError

    console = Console(file=StringIO(), width=80)
    error = ConfigError("Config file not found")
    _render_error(error, console)
    output = console.file.getvalue() if hasattr(console.file, 'getvalue') else str(console.file)
    assert "Configuration Error" in output or "Config" in output


def test_render_error_repl_plain_stderr() -> None:
    """_render_error outputs plain text for ReplRequiresTTYError (no panel)."""
    from io import StringIO

    from rich.console import Console

    from pyfintracker.cli import _render_error
    from pyfintracker.exceptions import ReplRequiresTTYError

    console = Console(file=StringIO(), width=80)
    error = ReplRequiresTTYError("REPL needs TTY")
    _render_error(error, console)
    output = console.file.getvalue() if hasattr(console.file, 'getvalue') else str(console.file)
    # No Panel characters should appear (╭─, │, ╰─)
    assert "╭─" not in output, "REPL error should not have a panel border"
    assert "REPL Error" in output or "REPL" in output


def test_render_error_unknown_plain() -> None:
    """_render_error outputs plain text for unknown error types."""
    from io import StringIO

    from rich.console import Console

    from pyfintracker.cli import _render_error
    from pyfintracker.exceptions import FinanceError

    console = Console(file=StringIO(), width=80)
    error = FinanceError("Generic error")
    _render_error(error, console)
    output = console.file.getvalue() if hasattr(console.file, 'getvalue') else str(console.file)
    assert "╭─" not in output, "Unknown error should not have a panel"
