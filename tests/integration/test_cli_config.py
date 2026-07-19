"""Integration tests for config precedence and ``fin config-show``.

Covers T-1.19 — verifies the 4-tier precedence chain and CLI output.
"""

from __future__ import annotations

from pathlib import Path

from typer.testing import CliRunner


def test_config_show_defaults(tmp_path: Path, cli_runner: CliRunner) -> None:
    """``fin config-show`` works with defaults (no env or TOML)."""
    from pyfintracker.cli import app

    result = cli_runner.invoke(app, ["config-show"])
    assert result.exit_code == 0, result.stdout
    assert "db_path" in result.stdout
    assert "display_currency" in result.stdout
    assert "[default]" in result.stdout
    # Default currency is COP
    assert "COP" in result.stdout


def test_config_env_override(tmp_path: Path, cli_runner: CliRunner) -> None:
    """``FIN_DISPLAY_CURRENCY`` env var overrides the default."""
    from pyfintracker.cli import app

    result = cli_runner.invoke(
        app,
        ["config-show"],
        env={"FIN_DISPLAY_CURRENCY": "EUR"},
    )
    assert result.exit_code == 0, result.stdout
    assert "EUR" in result.stdout
    assert "[env]" in result.stdout


def test_config_toml_override(tmp_path: Path, cli_runner: CliRunner) -> None:
    """``~/.config/fin/config.toml`` is picked up by config-show."""
    from pyfintracker.cli import app

    # Write a temporary TOML file
    config_dir = Path("~/.config/fin").expanduser()
    config_dir.mkdir(parents=True, exist_ok=True)
    toml_path = config_dir / "config.toml"
    original = toml_path.read_text() if toml_path.exists() else None
    toml_path.write_text('display_currency = "GBP"\n')

    try:
        result = cli_runner.invoke(app, ["config-show"])
        assert result.exit_code == 0, result.stdout
        assert "GBP" in result.stdout
        assert "[toml]" in result.stdout
    finally:
        # Restore original
        if original is not None:
            toml_path.write_text(original)
        elif toml_path.exists():
            toml_path.unlink()


def test_config_env_overrides_toml(tmp_path: Path, cli_runner: CliRunner) -> None:
    """Env var overrides TOML value."""
    from pyfintracker.cli import app

    config_dir = Path("~/.config/fin").expanduser()
    config_dir.mkdir(parents=True, exist_ok=True)
    toml_path = config_dir / "config.toml"
    original = toml_path.read_text() if toml_path.exists() else None
    toml_path.write_text('display_currency = "GBP"\n')

    try:
        result = cli_runner.invoke(
            app,
            ["config-show"],
            env={"FIN_DISPLAY_CURRENCY": "JPY"},
        )
        assert result.exit_code == 0, result.stdout
        assert "JPY" in result.stdout, "Env should win over TOML"
        assert "[env]" in result.stdout
    finally:
        if original is not None:
            toml_path.write_text(original)
        elif toml_path.exists():
            toml_path.unlink()
