"""pydantic-settings configuration loader.

Provides ``Settings`` (BaseSettings) with 4-tier precedence:
    defaults < TOML file < ``FIN_*`` env vars < CLI overrides

TOML support uses ``TomlConfigSettingsSource`` via ``settings_customise_sources``.
"""

from __future__ import annotations

import os
import tomllib
import warnings
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
    display_currency: str = Field(
        default="COP",
        description="ISO 4217 currency code for display formatting.",
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

    @property
    def default_currency(self) -> str:
        """Deprecated: use display_currency."""
        warnings.warn(
            "default_currency is deprecated, use display_currency",
            DeprecationWarning,
            stacklevel=2,
        )
        return self.display_currency

    @default_currency.setter
    def default_currency(self, value: str) -> None:
        """Deprecated: use display_currency."""
        warnings.warn(
            "default_currency is deprecated, use display_currency",
            DeprecationWarning,
            stacklevel=2,
        )
        self.display_currency = value

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

# Map from deprecated field names to current field names.
_DEPRECATED_FIELDS: dict[str, str] = {
    "default_currency": "display_currency",
}


def _resolve_field(field: str) -> str:
    """Resolve a field name, following deprecated aliases."""
    return _DEPRECATED_FIELDS.get(field, field)


def source_of(field: str, cli_overrides: dict[str, object] | None = None) -> str:
    """Return the source layer of a Settings field value.

    Best-effort heuristic — pydantic-settings does not expose a direct
    source-tracking API.  Checks layers in reverse precedence order:

        ``cli`` > ``env`` > ``toml`` > ``default``

    Accepts both current and deprecated field names (e.g. ``"default_currency"``
    is resolved to ``"display_currency"``).

    Args:
        field: Settings field name (e.g. ``"display_currency"``).
        cli_overrides: Optional CLI override dict (same shape as
                       :func:`load_settings`).

    Returns:
        One of ``"cli"``, ``"env"``, ``"toml"``, or ``"default"``.
    """
    current = _resolve_field(field)

    if cli_overrides and current in cli_overrides:
        return "cli"

    env_val = os.getenv(f"FIN_{current.upper()}")
    if env_val is not None:
        return "env"

    if _TOML_PATH.exists():
        with open(_TOML_PATH, "rb") as f:
            data = tomllib.load(f)
        if current in data:
            return "toml"
        # Also check deprecated names in TOML
        if field != current and field in data:
            return "toml"

    return "default"


def _remap_cli_overrides(cli_overrides: dict[str, object]) -> dict[str, object]:
    """Remap deprecated field names to current field names."""
    remapped = {}
    for k, v in cli_overrides.items():
        if k in _DEPRECATED_FIELDS:
            remapped[_DEPRECATED_FIELDS[k]] = v
        else:
            remapped[k] = v
    return remapped


def load_settings(cli_overrides: dict[str, object] | None = None) -> Settings:
    """Load settings with precedence: defaults < TOML < env < CLI.

    Args:
        cli_overrides: Optional dict from CLI flags
                       (e.g., ``{"db_path": Path("/tmp/db.sqlite")}``).
                       Deprecated field names (``default_currency``) are
                       silently remapped to ``display_currency``.

    Returns:
        Settings instance with merged values.
    """
    settings = Settings()

    if cli_overrides:
        remapped = _remap_cli_overrides(cli_overrides)
        for k, v in remapped.items():
            if hasattr(settings, k):
                setattr(settings, k, v)

    return settings


__all__ = [
    "Settings",
    "load_settings",
    "source_of",
]
