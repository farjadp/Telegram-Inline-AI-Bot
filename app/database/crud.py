# ============================================================================
# Source: app/database/crud.py
# Version: 1.0.0 — 2026-04-16
# Why: All database operations — create, read, update, delete for all models
# Env / Identity: Python module — SQLAlchemy 2.x async ORM
# ============================================================================

import logging
from datetime import datetime, timezone, timedelta
from decimal import Decimal
from typing import Optional

from sqlalchemy import func, select, update, desc, and_, cast, Date
from sqlalchemy.dialects.sqlite import insert as sqlite_insert

from app.database.models import User, Request, Setting, AdminSession
from app.database.session import get_session

logger = logging.getLogger(__name__)


# ===========================================================================
# User Operations
# ===========================================================================

async def upsert_user(
    telegram_id: int,
    username: Optional[str] = None,
    first_name: Optional[str] = None,
    last_name: Optional[str] = None,
) -> User:
    """
    Create a new user or update their profile info if they already exist.
    Also updates last_active_at timestamp on every call.

    Args:
        telegram_id: Telegram user ID (globally unique)
        username:    Telegram username (without @), may be None
        first_name:  User's first name
        last_name:   User's last name

    Returns:
        The User ORM object (created or existing)
    """
    async with get_session() as session:
        # Try to find existing user
        result = await session.execute(
            select(User).where(User.telegram_id == telegram_id)
        )
        user = result.scalar_one_or_none()

        now = datetime.now(timezone.utc)

        if user is None:
            # First time this user has used the bot — create their record
            user = User(
                telegram_id=telegram_id,
                username=username,
                first_name=first_name,
                last_name=last_name,
                last_active_at=now,
            )
            session.add(user)
            logger.info("New user created: telegram_id=%s username=%s", telegram_id, username)
        else:
            # Update mutable fields in case user changed their Telegram profile
            user.username = username
            user.first_name = first_name
            user.last_name = last_name
            user.last_active_at = now

        await session.flush()  # Write to DB within the transaction
        await session.refresh(user)  # Reload to get server-generated values
        return user


async def get_user_by_telegram_id(telegram_id: int) -> Optional[User]:
    """Fetch a user by their Telegram ID. Returns None if not found."""
    async with get_session() as session:
        result = await session.execute(
            select(User).where(User.telegram_id == telegram_id)
        )
        return result.scalar_one_or_none()


async def get_all_users(
    limit: int = 100,
    offset: int = 0,
    search: Optional[str] = None,
) -> tuple[list[User], int]:
    """
    Paginated list of all users with optional username/name search.

    Returns:
        (list of User objects, total count matched)
    """
    async with get_session() as session:
        base_query = select(User)

        if search:
            # Search across username, first_name, and last_name fields
            search_filter = (
                User.username.ilike(f"%{search}%")
                | User.first_name.ilike(f"%{search}%")
                | User.last_name.ilike(f"%{search}%")
            )
            base_query = base_query.where(search_filter)

        # Count total matches for pagination
        count_result = await session.execute(
            select(func.count()).select_from(base_query.subquery())
        )
        total = count_result.scalar_one()

        # Fetch paginated results ordered by most recently active
        users_result = await session.execute(
            base_query.order_by(desc(User.last_active_at)).limit(limit).offset(offset)
        )
        users = users_result.scalars().all()
        return list(users), total


async def set_user_blocked(telegram_id: int, blocked: bool) -> bool:
    """
    Block or unblock a user. Returns True if user was found and updated.
    """
    async with get_session() as session:
        result = await session.execute(
            update(User)
            .where(User.telegram_id == telegram_id)
            .values(is_blocked=blocked)
        )
        updated = result.rowcount > 0
        if updated:
            logger.info("User %s blocked=%s", telegram_id, blocked)
        return updated


async def set_user_rate_limit(telegram_id: int, rate_limit: Optional[int]) -> bool:
    """
    Set a custom per-user rate limit (overrides global setting).
    Pass None to reset to global default.
    """
    async with get_session() as session:
        result = await session.execute(
            update(User)
            .where(User.telegram_id == telegram_id)
            .values(rate_limit=rate_limit)
        )
        return result.rowcount > 0


# ===========================================================================
# Request Operations
# ===========================================================================

async def create_request(
    user_id: Optional[int],
    query: str,
    request_type: str,
    model: str,
    status: str = "success",
    # Text fields
    prompt_tokens: int = 0,
    completion_tokens: int = 0,
    total_tokens: int = 0,
    # Image fields
    image_credits: float = 0.0,
    image_url: Optional[str] = None,
    # Common
    response_preview: Optional[str] = None,
    cost_usd: float = 0.0,
    error_message: Optional[str] = None,
    processing_time_ms: int = 0,
) -> Request:
    """
    Persist a new request record to the database.
    Called after every inline query completes (success or error).
    """
    async with get_session() as session:
        req = Request(
            user_id=user_id,
            query=query,
            request_type=request_type,
            model=model,
            status=status,
            prompt_tokens=prompt_tokens or None,
            completion_tokens=completion_tokens or None,
            total_tokens=total_tokens or None,
            image_credits=Decimal(str(image_credits)) if image_credits else None,
            image_url=image_url,
            response_preview=response_preview,
            cost_usd=Decimal(str(cost_usd)) if cost_usd else None,
            error_message=error_message,
            processing_time_ms=processing_time_ms,
        )
        session.add(req)
        await session.flush()
        await session.refresh(req)
        logger.debug("Request logged: id=%s type=%s model=%s", req.id, request_type, model)
        return req


async def get_requests(
    limit: int = 50,
    offset: int = 0,
    request_type: Optional[str] = None,
    status: Optional[str] = None,
    user_id: Optional[int] = None,
    search: Optional[str] = None,
    date_from: Optional[datetime] = None,
    date_to: Optional[datetime] = None,
) -> tuple[list[Request], int]:
    """
    Paginated and filtered request log for the admin history page.

    Returns:
        (list of Request objects, total count matching filters)
    """
    async with get_session() as session:
        base_query = select(Request)

        # Apply all optional filters
        filters = []
        if request_type:
            filters.append(Request.request_type == request_type)
        if status:
            filters.append(Request.status == status)
        if user_id:
            filters.append(Request.user_id == user_id)
        if search:
            filters.append(Request.query.ilike(f"%{search}%"))
        if date_from:
            filters.append(Request.created_at >= date_from)
        if date_to:
            filters.append(Request.created_at <= date_to)

        if filters:
            base_query = base_query.where(and_(*filters))

        # Count total matching records
        count_result = await session.execute(
            select(func.count()).select_from(base_query.subquery())
        )
        total = count_result.scalar_one()

        # Fetch paginated results, newest first
        reqs_result = await session.execute(
            base_query.order_by(desc(Request.created_at)).limit(limit).offset(offset)
        )
        requests = reqs_result.scalars().all()
        return list(requests), total


async def get_analytics(days: int = 30) -> dict:
    """
    Compute aggregated analytics for the admin dashboard.

    Returns a dict with:
      - total_requests: total in the period
      - text_requests / image_requests: by type
      - total_tokens: sum of all GPT tokens
      - total_cost_usd: sum of all costs
      - active_users: distinct users in period
      - daily_stats: list of {date, text_count, image_count, tokens, cost}
      - top_users: list of {telegram_id, username, count}
      - model_usage: dict of model → count
    """
    since = datetime.now(timezone.utc) - timedelta(days=days)

    async with get_session() as session:
        # --- Aggregate totals ---
        totals = await session.execute(
            select(
                func.count(Request.id).label("total"),
                func.sum(Request.total_tokens).label("total_tokens"),
                func.sum(Request.cost_usd).label("total_cost"),
                func.count(func.distinct(Request.user_id)).label("active_users"),
            ).where(Request.created_at >= since)
        )
        row = totals.one()

        # --- Type breakdown ---
        text_count = await session.execute(
            select(func.count(Request.id)).where(
                Request.created_at >= since, Request.request_type == "text"
            )
        )
        image_count = await session.execute(
            select(func.count(Request.id)).where(
                Request.created_at >= since, Request.request_type == "image"
            )
        )

        # --- Daily aggregated stats (for chart) ---
        daily = await session.execute(
            select(
                cast(Request.created_at, Date).label("day"),
                func.sum(
                    func.case((Request.request_type == "text", 1), else_=0)
                ).label("text_count"),
                func.sum(
                    func.case((Request.request_type == "image", 1), else_=0)
                ).label("image_count"),
                func.sum(Request.total_tokens).label("tokens"),
                func.sum(Request.cost_usd).label("cost"),
            )
            .where(Request.created_at >= since)
            .group_by(cast(Request.created_at, Date))
            .order_by(cast(Request.created_at, Date))
        )
        daily_rows = daily.all()

        # --- Top users (most active) ---
        top_users_result = await session.execute(
            select(
                User.telegram_id,
                User.username,
                User.first_name,
                func.count(Request.id).label("request_count"),
            )
            .join(Request, Request.user_id == User.id)
            .where(Request.created_at >= since)
            .group_by(User.telegram_id, User.username, User.first_name)
            .order_by(desc("request_count"))
            .limit(10)
        )
        top_users = top_users_result.all()

        return {
            "total_requests": row.total or 0,
            "text_requests": text_count.scalar() or 0,
            "image_requests": image_count.scalar() or 0,
            "total_tokens": int(row.total_tokens or 0),
            "total_cost_usd": float(row.total_cost or 0),
            "active_users": row.active_users or 0,
            "daily_stats": [
                {
                    "date": str(r.day),
                    "text_count": int(r.text_count or 0),
                    "image_count": int(r.image_count or 0),
                    "tokens": int(r.tokens or 0),
                    "cost": float(r.cost or 0),
                }
                for r in daily_rows
            ],
            "top_users": [
                {
                    "telegram_id": u.telegram_id,
                    "username": u.username or u.first_name or str(u.telegram_id),
                    "count": u.request_count,
                }
                for u in top_users
            ],
        }


# ===========================================================================
# Settings Operations
# ===========================================================================

async def get_setting(key: str) -> Optional[str]:
    """Retrieve a single setting value by key. Returns None if not found."""
    async with get_session() as session:
        result = await session.execute(
            select(Setting.value).where(Setting.key == key)
        )
        return result.scalar_one_or_none()


async def set_setting(key: str, value: str) -> None:
    """
    Upsert a setting — creates it if it doesn't exist, updates if it does.
    Uses insert-or-replace for atomicity.
    """
    async with get_session() as session:
        # Check if it exists first
        existing = await session.execute(
            select(Setting).where(Setting.key == key)
        )
        setting = existing.scalar_one_or_none()

        if setting is None:
            setting = Setting(key=key, value=value)
            session.add(setting)
        else:
            setting.value = value
            setting.updated_at = datetime.now(timezone.utc)


async def get_all_settings() -> dict[str, str]:
    """Return all settings as a plain dict. Used by admin settings page."""
    async with get_session() as session:
        result = await session.execute(select(Setting))
        settings = result.scalars().all()
        return {s.key: s.value for s in settings}


# ===========================================================================
# Admin Session Operations
# ===========================================================================

async def create_admin_session(session_token: str, expire_hours: int = 24) -> AdminSession:
    """
    Create a new admin session record in the database.

    Args:
        session_token: Cryptographically random token (from auth.py)
        expire_hours:  Hours until session expires

    Returns:
        Created AdminSession object
    """
    async with get_session() as session:
        now = datetime.now(timezone.utc)
        admin_session = AdminSession(
            session_token=session_token,
            created_at=now,
            expires_at=now + timedelta(hours=expire_hours),
        )
        session.add(admin_session)
        await session.flush()
        await session.refresh(admin_session)
        return admin_session


async def get_admin_session(session_token: str) -> Optional[AdminSession]:
    """
    Look up an admin session by token.
    Returns None if not found or already expired.
    """
    async with get_session() as session:
        result = await session.execute(
            select(AdminSession).where(AdminSession.session_token == session_token)
        )
        admin_session = result.scalar_one_or_none()

        if admin_session is None:
            return None

        # Check expiry
        if admin_session.is_expired():
            # Clean up expired session from DB
            await session.delete(admin_session)
            return None

        return admin_session


async def delete_admin_session(session_token: str) -> None:
    """Delete an admin session (logout)."""
    async with get_session() as session:
        result = await session.execute(
            select(AdminSession).where(AdminSession.session_token == session_token)
        )
        admin_session = result.scalar_one_or_none()
        if admin_session:
            await session.delete(admin_session)
