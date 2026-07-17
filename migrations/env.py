"""Alembic environment configuration.

Supports both CLI usage (``alembic upgrade head``) and programmatic
invocation from tests via ``config.attributes["connection"]``.
"""

from logging.config import fileConfig
from typing import Any

from alembic import context
from sqlalchemy import Connection, engine_from_config, pool

# Alembic Config object
config = context.config

# Logging
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Hand-written migration — no target_metadata needed
target_metadata: Any = None


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode (emit SQL, no DB connection)."""
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online(connection: Connection | None = None) -> None:
    """Run migrations in 'online' mode.

    If a *connection* is provided (e.g. from a test fixture) it is used
    directly.  Otherwise an engine is created from the config URL.
    """
    if connection is not None:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()
        return

    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as conn:
        context.configure(connection=conn, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    # Allow test fixtures to inject a connection
    run_migrations_online(connection=config.attributes.get("connection"))
