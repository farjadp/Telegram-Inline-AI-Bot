# ============================================================================
# Source: app/database/models.py
# Version: 1.0.0 — 2026-04-16
# Why: SQLAlchemy ORM models — defines all database tables as Python classes
# Env / Identity: SQLAlchemy 2.x — async-compatible declarative models
# ============================================================================

from datetime import datetime, timezone
from decimal import Decimal
from typing import Optional

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    func,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


# ---------------------------------------------------------------------------
# Declarative Base — all models inherit from this
# ---------------------------------------------------------------------------
class Base(DeclarativeBase):
    """Base class for all ORM models. Provides the metadata registry."""
    pass


# ---------------------------------------------------------------------------
# User Model
# Records every Telegram user who has used the bot
# ---------------------------------------------------------------------------
class User(Base):
    """
    Represents a Telegram user.
    Created on first interaction, updated on each subsequent request.
    """

    __tablename__ = "users"

    # Primary key — internal app ID (not the Telegram ID)
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    # Telegram user ID — globally unique, used for rate limiting + lookups
    telegram_id: Mapped[int] = mapped_column(BigInteger, unique=True, nullable=False, index=True)

    # Telegram profile fields (can be null if user has privacy settings)
    username: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    first_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    last_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)

    # Admin controls
    is_blocked: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    # Per-user rate limit override — None means use global default from settings
    rate_limit: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    last_active_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    # Relationship — access all requests for this user
    requests: Mapped[list["Request"]] = relationship("Request", back_populates="user")

    def display_name(self) -> str:
        """Return the best available display name for this user."""
        if self.username:
            return f"@{self.username}"
        if self.first_name:
            full = self.first_name
            if self.last_name:
                full += f" {self.last_name}"
            return full
        return str(self.telegram_id)

    def __repr__(self) -> str:
        return f"<User id={self.id} telegram_id={self.telegram_id} username={self.username!r}>"


# ---------------------------------------------------------------------------
# Request Model
# Records every inline query processed by the bot
# ---------------------------------------------------------------------------
class Request(Base):
    """
    A single inline query request — includes AI provider details, tokens, and cost.
    Both text and image requests are stored here with type-specific nullable fields.
    """

    __tablename__ = "requests"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    # Foreign key to users table (nullable — user record may not exist if DB was unavailable)
    user_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("users.id"), nullable=True, index=True
    )

    # The raw query text from Telegram
    query: Mapped[str] = mapped_column(Text, nullable=False)

    # Request classification: 'text' or 'image'
    request_type: Mapped[str] = mapped_column(String(20), nullable=False, index=True)

    # AI model used (e.g. "gpt-4o-mini", "black-forest-labs/flux-schnell")
    model: Mapped[str] = mapped_column(String(100), nullable=False)

    # --- Text-only fields ---
    prompt_tokens: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    completion_tokens: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    total_tokens: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    # --- Image-only fields ---
    image_credits: Mapped[Optional[Decimal]] = mapped_column(Numeric(10, 6), nullable=True)
    image_url: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # --- Common fields ---
    # First 500 chars of text response, or image URL for quick preview in admin
    response_preview: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    cost_usd: Mapped[Optional[Decimal]] = mapped_column(Numeric(10, 6), nullable=True)

    # Status: 'success', 'error', or 'rate_limited'
    status: Mapped[str] = mapped_column(String(20), default="success", nullable=False)
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # How long the AI provider took (milliseconds)
    processing_time_ms: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    # When this request was made
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False, index=True
    )

    # Relationship back to user
    user: Mapped[Optional["User"]] = relationship("User", back_populates="requests")

    def __repr__(self) -> str:
        return (
            f"<Request id={self.id} type={self.request_type!r} "
            f"model={self.model!r} status={self.status!r}>"
        )


# ---------------------------------------------------------------------------
# Setting Model
# Admin-configurable key-value settings stored in DB
# Overrides environment variables at runtime
# ---------------------------------------------------------------------------
class Setting(Base):
    """
    Key-value store for admin-configurable settings.
    Values stored here take precedence over .env values (via DynamicSettings cache).
    """

    __tablename__ = "settings"

    # Key is the primary key — enforces uniqueness
    key: Mapped[str] = mapped_column(String(100), primary_key=True)
    value: Mapped[str] = mapped_column(Text, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    def __repr__(self) -> str:
        display_value = self.value[:20] + "…" if len(self.value) > 20 else self.value
        return f"<Setting key={self.key!r} value={display_value!r}>"


# ---------------------------------------------------------------------------
# AdminSession Model
# Tracks active admin panel login sessions (cookie-based auth)
# ---------------------------------------------------------------------------
class AdminSession(Base):
    """
    Represents an active admin panel session.
    Created on login, deleted on logout or expiry.
    Session token is stored in a signed cookie via itsdangerous.
    """

    __tablename__ = "admin_sessions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    # Cryptographically random token stored in the browser cookie
    session_token: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    # Session expires after SESSION_EXPIRE_HOURS (config setting)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    def is_expired(self) -> bool:
        """Return True if this session has passed its expiry time."""
        return datetime.now(timezone.utc) > self.expires_at.replace(tzinfo=timezone.utc)

    def __repr__(self) -> str:
        return f"<AdminSession id={self.id} expires_at={self.expires_at}>"
