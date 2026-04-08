"""Alembic migration environment for OpenArena Perception SQLite database."""
from __future__ import annotations

from logging.config import fileConfig
from pathlib import Path

from sqlalchemy import create_engine, pool

from alembic import context

# Alembic Config object -- provides access to alembic.ini values
config = context.config

# Set up Python logging from the ini file
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Import schema metadata for autogenerate support
from openarena_perception.memory.schema import metadata as target_metadata

# Resolve database URL from BotSettings (env-overridable) with fallback
try:
    from openarena_perception.settings import get_settings

    _db_path = Path(get_settings().db_path).expanduser().resolve()
    _url = f"sqlite:///{_db_path}"
except Exception:
    # Fallback to alembic.ini URL if settings unavailable
    _url = config.get_main_option("sqlalchemy.url")


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode (SQL script generation)."""
    context.configure(
        url=_url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode against a live database."""
    connectable = create_engine(_url, poolclass=pool.NullPool)

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
