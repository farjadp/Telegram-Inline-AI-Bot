# ============================================================================
# Source: app/services/rate_limiter.py
# Version: 1.0.0 — 2026-04-16
# Why: Per-user sliding window rate limiter — in-memory with optional Redis backend
# Env / Identity: Python module — asyncio + optional Redis
# ============================================================================

import asyncio
import logging
import time
from collections import defaultdict, deque
from typing import Deque

from app.config import settings

logger = logging.getLogger(__name__)


class RateLimiter:
    """
    Sliding window rate limiter that tracks requests per user.

    Algorithm:
      - Maintains a deque of timestamps for each user
      - On each check, prunes timestamps older than the window
      - If the deque length >= limit, the user is rate limited

    Backend selection:
      - If Redis is available: uses Redis sorted sets (shared across workers)
      - Fallback: in-memory deques (works for single-process deployments)

    Configuration (from settings):
      - RATE_LIMIT_REQUESTS: max requests per window (default: 20)
      - RATE_LIMIT_WINDOW: window size in seconds (default: 60)
    """

    def __init__(self) -> None:
        # In-memory store: {user_id: deque of request timestamps}
        self._store: dict[int, Deque[float]] = defaultdict(deque)
        # Lock per user to prevent race conditions in async context
        self._locks: dict[int, asyncio.Lock] = defaultdict(asyncio.Lock)
        # Redis client (initialized lazily)
        self._redis = None
        self._redis_initialized = False

    async def _get_redis(self):
        """
        Lazily initialize the Redis client.
        Returns None if Redis is not available, enabling graceful fallback.
        """
        if self._redis_initialized:
            return self._redis

        self._redis_initialized = True
        try:
            import redis.asyncio as aioredis

            client = aioredis.from_url(
                settings.REDIS_URL,
                encoding="utf-8",
                decode_responses=True,
                socket_connect_timeout=2,  # Fail fast if Redis is down
            )
            # Ping to verify the connection works
            await client.ping()
            self._redis = client
            logger.info("✅ Rate limiter using Redis backend: %s", settings.REDIS_URL)
        except Exception as exc:
            logger.warning(
                "Redis unavailable (%s) — falling back to in-memory rate limiter", exc
            )
            self._redis = None

        return self._redis

    async def is_rate_limited(self, user_id: int) -> bool:
        """
        Check if a user has exceeded their rate limit.

        Checks per-user custom rate limit first (from DB), then global setting.

        Args:
            user_id: Telegram user ID

        Returns:
            True if the user should be rate limited, False if they can proceed
        """
        # Load limit — check if user has a custom limit configured in admin panel
        limit, window = await self._get_limit_for_user(user_id)

        redis = await self._get_redis()
        if redis:
            return await self._redis_is_limited(user_id, limit, window, redis)
        else:
            return await self._memory_is_limited(user_id, limit, window)

    async def record_request(self, user_id: int) -> None:
        """
        Record a request timestamp for the user.
        Must be called AFTER is_rate_limited() returns False.
        """
        _, window = await self._get_limit_for_user(user_id)
        now = time.time()

        redis = await self._get_redis()
        if redis:
            await self._redis_record(user_id, now, window, redis)
        else:
            await self._memory_record(user_id, now, window)

    async def _get_limit_for_user(self, user_id: int) -> tuple[int, int]:
        """
        Fetch the effective rate limit for a specific user.
        Per-user custom limit (from admin panel) takes precedence over global setting.

        Returns:
            (requests_per_window, window_size_seconds)
        """
        try:
            from app.database.crud import get_user_by_telegram_id

            user = await get_user_by_telegram_id(user_id)
            if user and user.rate_limit is not None:
                # Use per-user custom limit
                return user.rate_limit, settings.RATE_LIMIT_WINDOW
        except Exception as exc:
            logger.debug("Could not fetch user rate limit from DB: %s", exc)

        # Use global default
        return settings.RATE_LIMIT_REQUESTS, settings.RATE_LIMIT_WINDOW

    # -----------------------------------------------------------------------
    # In-memory implementation
    # -----------------------------------------------------------------------
    async def _memory_is_limited(self, user_id: int, limit: int, window: int) -> bool:
        """Sliding window check using in-memory deques."""
        async with self._locks[user_id]:
            now = time.time()
            timestamps = self._store[user_id]
            cutoff = now - window

            # Remove timestamps outside the current window
            while timestamps and timestamps[0] < cutoff:
                timestamps.popleft()

            # Check if limit is exceeded
            return len(timestamps) >= limit

    async def _memory_record(self, user_id: int, timestamp: float, window: int) -> None:
        """Record a timestamp in the in-memory deque."""
        async with self._locks[user_id]:
            self._store[user_id].append(timestamp)

    # -----------------------------------------------------------------------
    # Redis implementation (shared across multiple workers)
    # -----------------------------------------------------------------------
    async def _redis_is_limited(self, user_id: int, limit: int, window: int, redis) -> bool:
        """
        Sliding window check using Redis sorted sets.
        Key: rate_limit:{user_id}
        Score: request timestamp
        Members: unique timestamp strings
        """
        key = f"rate_limit:{user_id}"
        now = time.time()
        cutoff = now - window

        # Atomic pipeline: remove old entries + count remaining
        async with redis.pipeline() as pipe:
            pipe.zremrangebyscore(key, 0, cutoff)   # Remove expired entries
            pipe.zcard(key)                          # Count current entries
            results = await pipe.execute()

        current_count = results[1]
        return current_count >= limit

    async def _redis_record(self, user_id: int, timestamp: float, window: int, redis) -> None:
        """Record a request in Redis sorted set with TTL cleanup."""
        key = f"rate_limit:{user_id}"
        # Use timestamp as both score and member (member must be unique)
        member = f"{timestamp:.6f}"

        async with redis.pipeline() as pipe:
            pipe.zadd(key, {member: timestamp})
            # Set TTL so Redis auto-cleans old keys (window + buffer)
            pipe.expire(key, window + 10)
            await pipe.execute()

    def clear_user(self, user_id: int) -> None:
        """Clear rate limit history for a specific user (e.g. after unblocking)."""
        self._store.pop(user_id, None)
        self._locks.pop(user_id, None)


# ---------------------------------------------------------------------------
# Module-level singleton — import this directly in other modules
# ---------------------------------------------------------------------------
rate_limiter = RateLimiter()
