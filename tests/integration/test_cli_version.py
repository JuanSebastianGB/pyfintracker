"""Tests for the ``fin version`` command."""

from __future__ import annotations

from importlib.metadata import version as pkg_version

from typer.testing import CliRunner

# NOTE: ``fin version`` does NOT depend on a database at all.
# All tests use bare CliRunner without ``FIN_DB_PATH``.


def test_version_command_exits_zero():
    """``fin version`` exits with code 0."""
    from pyfintracker.cli import app

    runner = CliRunner()
    result = runner.invoke(app, ["version"])
    assert result.exit_code == 0


def test_version_output_contains_version_string():
    """Output contains the installed version from importlib.metadata."""
    from pyfintracker.cli import app

    expected = pkg_version("pyfintracker")
    runner = CliRunner()
    result = runner.invoke(app, ["version"])
    assert expected in result.stdout


def test_version_output_format():
    """Output matches 'pyfintracker v0.1.0' format."""
    from pyfintracker.cli import app

    expected = pkg_version("pyfintracker")
    runner = CliRunner()
    result = runner.invoke(app, ["version"])
    assert f"pyfintracker v{expected}" in result.stdout
