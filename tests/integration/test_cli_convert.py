"""Integration tests for `fin convert` CLI command (T-C.2)."""

from __future__ import annotations

from pathlib import Path

import pytest
from typer.testing import CliRunner


@pytest.mark.integration
class TestCliConvertHelpAndErrors:
    """CLI command parsing and error handling."""

    def test_convert_help_shown(self, cli_runner: CliRunner) -> None:
        """`fin convert --help` shows usage."""
        from pyfintracker.cli import app

        result = cli_runner.invoke(app, ["convert", "--help"])
        assert result.exit_code == 0
        assert "Convert" in result.stdout

    def test_convert_invalid_currency_exit_1(self, cli_runner: CliRunner) -> None:
        """Unknown currency -> exit 1 via validate_currency."""
        from pyfintracker.cli import app

        result = cli_runner.invoke(app, ["convert", "100", "USD", "ABC"])
        assert result.exit_code == 1

    def test_convert_invalid_amount_exit_1(self, cli_runner: CliRunner) -> None:
        """Invalid amount -> exit 1."""
        from pyfintracker.cli import app

        result = cli_runner.invoke(app, ["convert", "abc", "USD", "COP"])
        assert result.exit_code == 1

    def test_convert_same_currency_no_db(self, cli_runner: CliRunner, tmp_path: Path) -> None:
        """Same-currency convert works without DB (fast path)."""
        from pyfintracker.cli import app

        db_path = tmp_path / "test.db"
        result = cli_runner.invoke(
            app,
            ["convert", "100.50", "COP", "COP"],
            env={"FIN_DB_PATH": str(db_path)},
        )
        # Same-currency fast path doesn't touch DB
        assert result.exit_code == 0, result.stdout
        assert "101 COP" in result.stdout  # ROUND_HALF_UP

    def test_convert_same_currency_usd_no_db(self, cli_runner: CliRunner, tmp_path: Path) -> None:
        """Same-currency USD convert works without DB."""
        from pyfintracker.cli import app

        db_path = tmp_path / "test.db"
        result = cli_runner.invoke(
            app,
            ["convert", "100.456", "USD", "USD"],
            env={"FIN_DB_PATH": str(db_path)},
        )
        assert result.exit_code == 0, result.stdout
        assert "100.46 USD" in result.stdout
