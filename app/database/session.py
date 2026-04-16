# ============================================================================
# Source: app/database/session.py
# Version: 1.0.0 — 2026-04-16
# Why: Async database engine + session factory — supports SQLite and PostgreSQL
# Env / Identity: Python module — SQLAlchemy 2.x async + aiosqlite/asyncpg
# ============================================================================

import logging
from contextlib import asynccontextmanager
from typing import AsyncGenerator

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.config import settings

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Engine Configuration
# Selects appropriate engine settings based on the database driver
# ---------------------------------------------------------------------------
def _create_engine() -> AsyncEngine:
    """
    Create the async SQLAlchemy engine.

    SQLite (development):
      - check_same_thread=False is required for aiosqlite
      - Lower pool settings (SQLite doesn't support concurrent writes well)

    PostgreSQL (production):
      - Uses asyncpg driver (fastest async Postgres driver)
      - Connection pool tuned for concurrent requests
    """
    db_url = settings.DATABASE_URL

    is_sqlite = "sqlite" in db_url

    if is_sqlite:
        # SQLite-specific configuration
        engine = create_async_engine(
            db_url,
            echo=settings.DEBUG,          # Log all SQL queries in debug mode
            connect_args={"check_same_thread": False},  # Required for SQLite + asyncio
            pool_size=1,                   # SQLite supports 1 writer at a time
            max_overflow=0,
        )
    else:
        # PostgreSQL configuration with connection pool
        engine = create_async_engine(
            db_url,
            echo=settings.DEBUG,
            pool_size=10,                  # Keep 10 connections warm
            max_overflow=20,               # Allow up to 30 total connections under load
            pool_pre_ping=True,            # Verify connections are live before using them
            pool_recycle=3600,             # Recycle connections after 1 hour
        )

    logger.info(
        "Database engine created | driver=%s | debug=%s",
        "sqlite" if is_sqlite else "postgresql",
        settings.DEBUG,
    )

    return engine


# Create the engine singleton at module load time
engine: AsyncEngine = _create_engine()

# ---------------------------------------------------------------------------
# Session Factory
# Creates AsyncSession instances bound to our engine
# ---------------------------------------------------------------------------
AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,   # Objects remain accessible after commit (avoids lazy-load errors)
    autoflush=True,
    autocommit=False,
)


# ---------------------------------------------------------------------------
# Session Context Manager
# The recommended pattern for using async SQLAlchemy sessions
# ---------------------------------------------------------------------------
@asynccontextmanager
async def get_session() -> AsyncGenerator[AsyncSession, None]:
    """
    Async context manager that provides a database session.
    Automatically commits on success, rolls back on exception.

    Usage:
        async with get_session() as session:
            result = await session.execute(select(User))

    Handles:
        - Commit on successful block exit
        - Rollback on exception
        - Session closure in finally block (always)
    """
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


# ---------------------------------------------------------------------------
# FastAPI Dependency
# Use this with Depends() in route handlers for automatic session management
# ---------------------------------------------------------------------------
async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """
    FastAPI dependency that yields a database session.
    Use in route handlers with: session: AsyncSession = Depends(get_db)

    Note: Unlike get_session(), this does NOT auto-commit.
    The route handler is responsible for calling session.commit().
    """
    async with AsyncSessionLocal() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


# ---------------------------------------------------------------------------
# Database Initialization
# Called once at application startup
# ---------------------------------------------------------------------------
async def init_db() -> None:
    """
    Create all database tables if they don't already exist.

    For production use, prefer Alembic migrations (alembic upgrade head).
    This is a convenience fallback for development/Docker fresh starts.
    """
    from app.database.models import Base  # Imported here to avoid circular imports at module level

    async with engine.begin() as conn:
        # create_all is idempotent — safe to call even if tables exist
        await conn.run_sync(Base.metadata.create_all)

    logger.info("✅ Database tables created (or already exist)")


async def close_db() -> None:
    """
    Dispose the engine connection pool.
    Called during application shutdown to cleanly close all DB connections.
    """
    await engine.dispose()
    logger.info("✅ Database engine disposed")
