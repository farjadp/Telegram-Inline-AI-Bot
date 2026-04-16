# ============================================================================
# Source: alembic/env.py
# Version: 1.0.0 — 2026-04-16
# Why: Alembic runtime environment — connects ORM metadata to the migration engine
# Env / Identity: Alembic migration runner — async SQLAlchemy
# ============================================================================

import asyncio
from logging.config import fileConfig

from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import async_engine_from_config

from alembic import context

# Import our ORM models so Alembic can detect schema changes (autogenerate)
from app.database.models import Base  # noqa: F401 — needed for metadata
from app.config import settings

# ---------------------------------------------------------------------------
# Alembic Config object provides access to values in alembic.ini
# ---------------------------------------------------------------------------
config = context.config

# Override the SQLAlchemy URL from our application settings (reads .env)
# This ensures migration URL and app URL are always in sync
config.set_main_option("sqlalchemy.url", settings.DATABASE_URL)

# Interpret the config file for Python logging
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# ORM metadata object for autogenerate support
# Alembic will compare this against the live DB to detect schema drift
target_metadata = Base.metadata


def run_migrations_offline() -> None:
    """
    Run migrations in 'offline' mode.
    Does not require a live DB connection — generates SQL script to stdout.
    Used for: generating migration SQL to review before applying.
    """
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection: Connection) -> None:
    """
    Execute migrations against a live database connection.
    Called by both online sync and async migration runners.
    """
    context.configure(connection=connection, target_metadata=target_metadata)

    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    """
    Run migrations using the async engine.
    Required because our SQLAlchemy setup uses asyncpg/aiosqlite drivers.
    """
    # Build an async engine from the alembic config values
    connectable = async_engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,  # No connection pooling during migrations
    )

    async with connectable.connect() as connection:
        # Run synchronous migration code within the async connection
        await connection.run_sync(do_run_migrations)

    await connectable.dispose()


def run_migrations_online() -> None:
    """
    Run migrations in 'online' mode (default).
    Wraps the async runner in an event loop.
    """
    asyncio.run(run_async_migrations())


# ---------------------------------------------------------------------------
# Entry point — Alembic calls this automatically
# ---------------------------------------------------------------------------
if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
