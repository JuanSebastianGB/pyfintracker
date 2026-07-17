"""Tests for config.Settings — pydantic-settings loader + precedence chain."""

from __future__ import annotations

from pathlib import Path

from pydantic_settings import BaseSettings

from pyfintracker import config


class TestSettingsDefaults:
    """Verify the Settings class exists and has expected shape."""

    def test_settings_class_exists(self) -> None:
        assert hasattr(config, "Settings")
        assert issubclass(config.Settings, BaseSettings)

    def test_settings_defaults(self) -> None:
        """Settings can be instantiated with no arguments (uses defaults)."""
        s = config.Settings()
        assert s.default_currency == "COP"
        assert s.account_name_max_length == 64
        assert s.description_max_length == 256
        assert s.snapshot_width == 120

    def test_db_path_default(self) -> None:
        """db_path defaults to ~/.local/share/fin/fin.db using pathlib expansion."""
        s = config.Settings()
        expected = Path("~/.local/share/fin/fin.db").expanduser()
        assert s.db_path == expected

    def test_default_currency_default(self) -> None:
        """default_currency defaults to COP."""
        s = config.Settings()
        assert s.default_currency == "COP"

    def test_account_name_max_length_default(self) -> None:
        """account_name_max_length defaults to 64."""
        s = config.Settings()
        assert s.account_name_max_length == 64

    def test_description_max_length_default(self) -> None:
        """description_max_length defaults to 256."""
        s = config.Settings()
        assert s.description_max_length == 256

    def test_snapshot_width_default(self) -> None:
        """snapshot_width defaults to 120."""
        s = config.Settings()
        assert s.snapshot_width == 120

    def test_journal_mode_default(self) -> None:
        """journal_mode defaults to WAL."""
        s = config.Settings()
        assert s.journal_mode == "WAL"


class TestLoadSettings:
    """Precedence chain: defaults < TOML < env < CLI."""

    def test_default_currency_default(self) -> None:
        """Default 'COP' if no override."""
        s = config.load_settings()
        assert s.default_currency == "COP"

    def test_env_overrides_default(self, monkeypatch) -> None:
        """Env var FIN_DEFAULT_CURRENCY=GBP overrides default."""
        monkeypatch.setenv("FIN_DEFAULT_CURRENCY", "GBP")
        s = config.load_settings()
        assert s.default_currency == "GBP"

    def test_env_overrides_toml(self, monkeypatch) -> None:
        """Env var overrides TOML (if TOML file exists with a value)."""
        monkeypatch.setenv("FIN_DEFAULT_CURRENCY", "GBP")
        s = config.load_settings()
        assert s.default_currency == "GBP"

    def test_cli_overrides_env(self, monkeypatch) -> None:
        """CLI override via dict overrides env."""
        monkeypatch.setenv("FIN_DEFAULT_CURRENCY", "GBP")
        s = config.load_settings(cli_overrides={"default_currency": "EUR"})
        assert s.default_currency == "EUR"

    def test_cli_no_override_uses_env(self, monkeypatch) -> None:
        """Without cli override, env var applies."""
        monkeypatch.setenv("FIN_DEFAULT_CURRENCY", "GBP")
        s = config.load_settings()
        assert s.default_currency == "GBP"

    def test_load_settings_returns_settings_instance(self) -> None:
        """load_settings returns a Settings instance."""
        s = config.load_settings()
        from pyfintracker.config import Settings

        assert isinstance(s, Settings)

    def test_cli_overrides_db_path(self) -> None:
        """CLI override can change db_path."""
        custom_path = "/tmp/test_fin.db"
        s = config.load_settings(cli_overrides={"db_path": Path(custom_path)})
        assert str(s.db_path) == custom_path


class TestTomlLayer:
    """TOML file overrides defaults (integration-level test).

    Writes/removes the actual TOML config file during this test class.
    """

    toml_path = Path.home() / ".config" / "fin" / "config.toml"

    @classmethod
    def setup_class(cls) -> None:
        cls.toml_path.parent.mkdir(parents=True, exist_ok=True)
        # Save existing content if any
        cls._saved = cls.toml_path.read_text() if cls.toml_path.exists() else None

    @classmethod
    def teardown_class(cls) -> None:
        if cls._saved is not None:
            cls.toml_path.write_text(cls._saved)
        elif cls.toml_path.exists():
            cls.toml_path.unlink()

    def test_toml_overrides_default(self) -> None:
        """TOML file value overrides default when env is not set."""
        self.toml_path.write_text('default_currency = "USD"')
        s = config.load_settings()
        assert s.default_currency == "USD"

    def test_toml_overrides_default_and_env_wins(self, monkeypatch) -> None:
        """Env still wins over TOML."""
        self.toml_path.write_text('default_currency = "USD"')
        monkeypatch.setenv("FIN_DEFAULT_CURRENCY", "GBP")
        s = config.load_settings()
        assert s.default_currency == "GBP"

    def test_toml_not_exists_falls_back_to_default(self) -> None:
        """When TOML file does not exist, defaults apply."""
        if self.toml_path.exists():
            self.toml_path.unlink()
        s = config.load_settings()
        assert s.default_currency == "COP"


class TestSourceOf:
    """source_of(field) returns the origin layer of a setting."""

    def test_source_default(self) -> None:
        """Returns 'default' when no override."""
        result = config.source_of("default_currency")
        assert result == "default"

    def test_source_env(self, monkeypatch) -> None:
        """Returns 'env' when set via FIN_* env var."""
        monkeypatch.setenv("FIN_DEFAULT_CURRENCY", "GBP")
        result = config.source_of("default_currency")
        assert result == "env"

    def test_source_cli(self) -> None:
        """Returns 'cli' when set via cli_overrides."""
        result = config.source_of(
            "default_currency",
            cli_overrides={"default_currency": "EUR"},
        )
        assert result == "cli"

    def test_source_cli_wins_over_env(self, monkeypatch) -> None:
        """CLI reported even when env also set."""
        monkeypatch.setenv("FIN_DEFAULT_CURRENCY", "GBP")
        result = config.source_of(
            "default_currency",
            cli_overrides={"default_currency": "EUR"},
        )
        assert result == "cli"

    def test_source_toml(self) -> None:
        """Returns 'toml' when set via TOML file (and no env/cli)."""
        self.__class__.toml_path = Path.home() / ".config" / "fin" / "config.toml"
        self.__class__.toml_path.parent.mkdir(parents=True, exist_ok=True)
        # Save existing
        saved = self.__class__.toml_path.read_text() if self.__class__.toml_path.exists() else None
        try:
            self.__class__.toml_path.write_text('default_currency = "USD"')
            result = config.source_of("default_currency")
            assert result == "toml"
        finally:
            if saved is not None:
                self.__class__.toml_path.write_text(saved)
            elif self.__class__.toml_path.exists():
                self.__class__.toml_path.unlink()
