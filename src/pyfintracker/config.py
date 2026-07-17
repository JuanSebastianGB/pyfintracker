"""pydantic-settings configuration loader.

Provides ``Settings`` (BaseSettings) with 4-tier precedence:
    defaults < TOML file < ``FIN_*`` env vars < CLI overrides

TOML support uses ``TomlConfigSettingsSource`` via ``settings_customise_sources``.
"""

from __future__ import annotations

import os
import tomllib
from pathlib import Path

from pydantic import Field
from pydantic_settings import (
    BaseSettings,
    SettingsConfigDict,
    TomlConfigSettingsSource,
)
from pydantic_settings.sources import PydanticBaseSettingsSource


class Settings(BaseSettings):
    """Application configuration loaded from TOML, env, and defaults.

    Precedence (lowest → highest):
        1. Hard-coded defaults (below)
        2. TOML file at ``~/.config/fin/config.toml``
        3. ``FIN_*`` environment variables
        4. CLI overrides (via ``setattr`` after construction in :func:`load_settings`)
    """

    model_config = SettingsConfigDict(
        env_prefix="FIN_",
        extra="ignore",
    )

    db_path: Path = Field(
        default=Path("~/.local/share/fin/fin.db").expanduser(),
        description="Path to the SQLite database file.",
    )
    default_currency: str = Field(
        default="COP",
        description="Default ISO 4217 currency code.",
    )
    account_name_max_length: int = Field(
        default=64,
        description="Maximum length for account names.",
    )
    description_max_length: int = Field(
        default=256,
        description="Maximum length for transaction descriptions.",
    )
    snapshot_width: int = Field(
        default=120,
        description="Column width for Rich snapshot tables.",
    )
    journal_mode: str = Field(
        default="WAL",
        description="SQLite journal mode (WAL or DELETE).",
    )

    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls: type[BaseSettings],
        init_settings: PydanticBaseSettingsSource,
        env_settings: PydanticBaseSettingsSource,
        dotenv_settings: PydanticBaseSettingsSource,
        file_secret_settings: PydanticBaseSettingsSource,
    ) -> tuple[PydanticBaseSettingsSource, ...]:
        """Custom source order: init, env, TOML (no dotenv, no secrets).

        Sources earlier in the tuple have higher priority, so ``env``
        overrides TOML, and explicit init args (used by CLI overrides)
        override everything.
        """
        toml_path = Path("~/.config/fin/config.toml").expanduser()
        return (
            init_settings,
            env_settings,
            TomlConfigSettingsSource(settings_cls, toml_file=str(toml_path)),
        )


_TOML_PATH = Path("~/.config/fin/config.toml").expanduser()


def source_of(field: str, cli_overrides: dict[str, object] | None = None) -> str:
    """Return the source layer of a Settings field value.

    Best-effort heuristic — pydantic-settings does not expose a direct
    source-tracking API.  Checks layers in reverse precedence order:

        ``cli`` > ``env`` > ``toml`` > ``default``

    Args:
        field: Settings field name (e.g. ``"default_currency"``).
        cli_overrides: Optional CLI override dict (same shape as
                       :func:`load_settings`).

    Returns:
        One of ``"cli"``, ``"env"``, ``"toml"``, or ``"default"``.
    """
    if cli_overrides and field in cli_overrides:
        return "cli"

    env_val = os.getenv(f"FIN_{field.upper()}")
    if env_val is not None:
        return "env"

    if _TOML_PATH.exists():
        with open(_TOML_PATH, "rb") as f:
            data = tomllib.load(f)
        if field in data:
            return "toml"

    return "default"


def load_settings(cli_overrides: dict[str, object] | None = None) -> Settings:
    """Load settings with precedence: defaults < TOML < env < CLI.

    Args:
        cli_overrides: Optional dict from CLI flags
                       (e.g., ``{"db_path": Path("/tmp/db.sqlite")}``).

    Returns:
        Settings instance with merged values.
    """
    settings = Settings()

    if cli_overrides:
        for k, v in cli_overrides.items():
            if hasattr(settings, k):
                setattr(settings, k, v)

    return settings


__all__ = [
    "Settings",
    "load_settings",
    "source_of",
]
