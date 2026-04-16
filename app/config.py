# ============================================================================
# Source: app/config.py
# Version: 1.0.0 — 2026-04-16
# Why: Centralized settings — loads from .env, with a DB-backed dynamic cache
# Env / Identity: Python module — pydantic-settings
# ============================================================================

import time
import logging
from functools import lru_cache
from typing import Optional

from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import field_validator

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Static Settings — loaded once at startup from environment variables / .env
# ---------------------------------------------------------------------------
class Settings(BaseSettings):
    """
    Application-wide settings sourced from environment variables.
    pydantic-settings automatically reads from .env file.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",  # Ignore undeclared env vars — avoid noisy errors
    )

    # --- Telegram -------------------------------------------------------
    TELEGRAM_BOT_TOKEN: str = ""
    TELEGRAM_WEBHOOK_URL: str = ""
    BOT_MODE: str = "polling"  # 'polling' for dev, 'webhook' for prod

    # --- OpenAI ---------------------------------------------------------
    OPENAI_API_KEY: str = ""
    OPENAI_MODEL: str = "gpt-4o-mini"
    OPENAI_MAX_TOKENS: int = 1000
    OPENAI_TEMPERATURE: float = 0.7
    OPENAI_SYSTEM_PROMPT: str = "You are a helpful assistant. Be concise and clear."

    # --- Image Generation -----------------------------------------------
    IMAGE_PROVIDER: str = "replicate"    # 'replicate' or 'fal'
    REPLICATE_API_TOKEN: str = ""
    FAL_API_KEY: str = ""
    FLUX_MODEL: str = "black-forest-labs/flux-schnell"
    FLUX_IMAGE_SIZE: str = "1024x1024"
    FLUX_STYLE_PREFIX: str = ""

    # --- Database -------------------------------------------------------
    DATABASE_URL: str = "sqlite+aiosqlite:///./bot.db"

    # --- Redis ----------------------------------------------------------
    REDIS_URL: str = "redis://localhost:6379/0"

    # --- Admin Panel Auth -----------------------------------------------
    ADMIN_USERNAME: str = "admin"
    ADMIN_PASSWORD: str = "change_me"
    SECRET_KEY: str = "change_this_secret_key_in_production"
    SESSION_EXPIRE_HOURS: int = 24

    # --- Rate Limiting --------------------------------------------------
    RATE_LIMIT_REQUESTS: int = 20   # Max requests per window
    RATE_LIMIT_WINDOW: int = 60     # Window size in seconds

    # --- App Behaviour --------------------------------------------------
    APP_ENV: str = "development"
    DEBUG: bool = True
    LOG_LEVEL: str = "INFO"
    MAINTENANCE_MODE: bool = False
    ALLOWED_USERS: str = ""         # Comma-separated Telegram user IDs, empty = all

    @field_validator("OPENAI_TEMPERATURE")
    @classmethod
    def validate_temperature(cls, v: float) -> float:
        """Clamp temperature to the valid OpenAI range [0.0, 2.0]."""
        return max(0.0, min(2.0, v))

    @property
    def allowed_users_list(self) -> list[int]:
        """Parse ALLOWED_USERS comma string into a list of integers."""
        if not self.ALLOWED_USERS.strip():
            return []  # Empty list = all users allowed
        return [int(uid.strip()) for uid in self.ALLOWED_USERS.split(",") if uid.strip()]

    @property
    def is_production(self) -> bool:
        """Convenience check: are we running in production mode?"""
        return self.APP_ENV.lower() == "production"


@lru_cache()
def get_settings() -> Settings:
    """
    Return the cached Settings singleton.
    Uses lru_cache so we parse .env only once per process.
    """
    return Settings()


# Module-level singleton — import this directly in other modules
settings = get_settings()


# ---------------------------------------------------------------------------
# Dynamic Settings — admin-configurable values stored in the database
# These override static settings and can be changed without restarting the app
# ---------------------------------------------------------------------------
class DynamicSettings:
    """
    Key-value settings store backed by the database.

    Flow:
      1. Admin changes a value in the admin panel → saved to `settings` table
      2. Next request reads the value from this cache (TTL: 60 seconds)
      3. After TTL expires, fresh value is loaded from the DB

    This avoids hitting the DB on every inline query while still picking up
    changes within one minute.
    """

    _cache: dict[str, tuple[str, float]] = {}
    _cache_ttl: int = 60  # Cache entries expire after 60 seconds

    @classmethod
    async def get(cls, key: str, default: Optional[str] = None) -> Optional[str]:
        """
        Retrieve a setting value.
        Checks in-memory cache first, then falls back to the database.
        """
        # Check if we have a fresh cache entry
        if key in cls._cache:
            value, timestamp = cls._cache[key]
            if time.time() - timestamp < cls._cache_ttl:
                return value  # Cache hit — use cached value

        # Cache miss or stale — fetch from database
        try:
            from app.database.crud import get_setting  # Deferred import to avoid circular

            value = await get_setting(key)
            result = value if value is not None else default

            # Store in cache with current timestamp
            if result is not None:
                cls._cache[key] = (str(result), time.time())

            return result
        except Exception as exc:
            logger.warning("DynamicSettings.get(%s) DB error: %s — using default", key, exc)
            return default

    @classmethod
    async def set(cls, key: str, value: str) -> None:
        """
        Persist a setting to the database and update the cache immediately.
        """
        from app.database.crud import set_setting  # Deferred import

        await set_setting(key, value)
        cls._cache[key] = (value, time.time())
        logger.debug("DynamicSettings.set(%s) = %s", key, value)

    @classmethod
    def invalidate(cls, key: str) -> None:
        """Remove a specific key from the cache, forcing a fresh DB read."""
        cls._cache.pop(key, None)

    @classmethod
    def clear_cache(cls) -> None:
        """Flush the entire settings cache."""
        cls._cache.clear()
        logger.debug("DynamicSettings cache cleared")
