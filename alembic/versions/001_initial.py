# ============================================================================
# Source: alembic/versions/001_initial.py
# Version: 1.0.0 — 2026-04-16
# Why: Initial database migration — creates all production tables
# Env / Identity: Alembic migration script — SQLAlchemy DDL
# ============================================================================

"""Initial schema — users, requests, settings, admin_sessions

Revision ID: 001
Revises: (none — this is the first migration)
Create Date: 2026-04-16
"""

from alembic import op
import sqlalchemy as sa

# ---------------------------------------------------------------------------
# Alembic metadata
# ---------------------------------------------------------------------------
revision = "001"
down_revision = None       # No parent migration — first in chain
branch_labels = None
depends_on = None


def upgrade() -> None:
    """
    Create all tables from scratch.
    Safe to run on an empty database.
    """

    # ------------------------------------------------------------------
    # users — tracks every Telegram user who has interacted with the bot
    # ------------------------------------------------------------------
    op.create_table(
        "users",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("telegram_id", sa.BigInteger(), nullable=False),
        sa.Column("username", sa.String(255), nullable=True),
        sa.Column("first_name", sa.String(255), nullable=True),
        sa.Column("last_name", sa.String(255), nullable=True),
        sa.Column("is_blocked", sa.Boolean(), server_default="false", nullable=False),
        # custom rate limit — NULL means use the global default from settings
        sa.Column("rate_limit", sa.Integer(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("last_active_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("telegram_id"),
    )
    op.create_index("ix_users_telegram_id", "users", ["telegram_id"], unique=True)

    # ------------------------------------------------------------------
    # requests — every inline query processed by the bot
    # ------------------------------------------------------------------
    op.create_table(
        "requests",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("query", sa.Text(), nullable=False),
        # 'text' or 'image'
        sa.Column("request_type", sa.String(20), nullable=False),
        # Model name e.g. gpt-4o-mini, flux-schnell
        sa.Column("model", sa.String(100), nullable=False),
        # --- Text request fields ---
        sa.Column("prompt_tokens", sa.Integer(), nullable=True),
        sa.Column("completion_tokens", sa.Integer(), nullable=True),
        sa.Column("total_tokens", sa.Integer(), nullable=True),
        # --- Image request fields ---
        sa.Column("image_credits", sa.Numeric(10, 6), nullable=True),
        sa.Column("image_url", sa.Text(), nullable=True),
        # --- Common fields ---
        # First 500 chars or image URL for quick preview
        sa.Column("response_preview", sa.Text(), nullable=True),
        sa.Column("cost_usd", sa.Numeric(10, 6), nullable=True),
        # 'success', 'error', 'rate_limited'
        sa.Column("status", sa.String(20), server_default="success", nullable=False),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("processing_time_ms", sa.Integer(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_requests_user_id", "requests", ["user_id"])
    op.create_index("ix_requests_created_at", "requests", ["created_at"])
    op.create_index("ix_requests_request_type", "requests", ["request_type"])

    # ------------------------------------------------------------------
    # settings — key-value store for admin-configurable bot settings
    # All settings saved here override environment variables at runtime
    # ------------------------------------------------------------------
    op.create_table(
        "settings",
        sa.Column("key", sa.String(100), nullable=False),
        sa.Column("value", sa.Text(), nullable=False),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            onupdate=sa.func.now(),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("key"),
    )

    # ------------------------------------------------------------------
    # admin_sessions — tracks active admin panel login sessions
    # ------------------------------------------------------------------
    op.create_table(
        "admin_sessions",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("session_token", sa.String(255), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("session_token"),
    )
    op.create_index(
        "ix_admin_sessions_token", "admin_sessions", ["session_token"], unique=True
    )


def downgrade() -> None:
    """
    Drop all tables created by this migration.
    Reverses the upgrade() function in reverse dependency order.
    """
    op.drop_table("admin_sessions")
    op.drop_table("settings")
    op.drop_table("requests")
    op.drop_table("users")
