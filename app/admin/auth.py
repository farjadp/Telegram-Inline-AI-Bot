# ============================================================================
# Source: app/admin/auth.py
# Version: 1.0.0 — 2026-04-16
# Why: Admin panel authentication — login, session management, auth dependency
# Env / Identity: Python module — passlib bcrypt + itsdangerous signed cookies
# ============================================================================

import logging
import secrets
from datetime import datetime, timezone, timedelta
from typing import Optional

from fastapi import Cookie, HTTPException, Request, status
from passlib.context import CryptContext

from app.config import settings

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Password hashing — bcrypt with automatic work factor
# ---------------------------------------------------------------------------
pwd_context = CryptContext(
    schemes=["bcrypt"],
    deprecated="auto",  # Automatically migrate old-format hashes
)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """
    Verify a plain text password against a bcrypt hash.
    Returns True if they match, False otherwise.
    """
    return pwd_context.verify(plain_password, hashed_password)


def hash_password(password: str) -> str:
    """
    Hash a plain text password using bcrypt.
    Use this when changing admin passwords via the settings page.
    """
    return pwd_context.hash(password)


# ---------------------------------------------------------------------------
# Credential verification
# Compares against env-configured username/password
# In a real multi-admin setup, you'd check against a DB table instead
# ---------------------------------------------------------------------------
def verify_admin_credentials(username: str, password: str) -> bool:
    """
    Verify admin login credentials.

    Strategy:
    1. Username must match ADMIN_USERNAME (case-sensitive)
    2. Password is compared directly to ADMIN_PASSWORD (plaintext in .env)
       OR against a bcrypt hash if ADMIN_PASSWORD starts with '$2b$' (bcrypt)

    This allows dev mode (plain text .env) and prod mode (hashed) seamlessly.

    Args:
        username: Submitted username from login form
        password: Submitted password from login form

    Returns:
        True if credentials are valid
    """
    # Username check (constant-time to prevent timing attacks)
    if not secrets.compare_digest(username, settings.ADMIN_USERNAME):
        logger.warning("Admin login: wrong username attempt (got %r)", username)
        return False

    stored = settings.ADMIN_PASSWORD

    # If stored password looks like a bcrypt hash, verify with passlib
    if stored.startswith("$2b$") or stored.startswith("$2a$"):
        valid = verify_password(password, stored)
    else:
        # Plain text comparison (for dev convenience — use bcrypt in production!)
        valid = secrets.compare_digest(password, stored)

    if not valid:
        logger.warning("Admin login: wrong password attempt for username %r", username)

    return valid


# ---------------------------------------------------------------------------
# Session Token Management
# ---------------------------------------------------------------------------
def generate_session_token() -> str:
    """
    Generate a cryptographically secure random session token.
    Uses 32 bytes of entropy → 64 hex chars — effectively unguessable.
    """
    return secrets.token_hex(32)


async def create_session(token: str) -> None:
    """
    Persist a new admin session token to the database.

    Args:
        token: The session token to store (should be pre-generated)
    """
    from app.database.crud import create_admin_session

    await create_admin_session(
        session_token=token,
        expire_hours=settings.SESSION_EXPIRE_HOURS,
    )
    logger.info("Admin session created (expires in %dh)", settings.SESSION_EXPIRE_HOURS)


async def validate_session(token: str) -> bool:
    """
    Check if a session token is valid and not expired.

    Args:
        token: Session token from the browser cookie

    Returns:
        True if the session is valid and not expired
    """
    from app.database.crud import get_admin_session

    session = await get_admin_session(token)
    return session is not None


async def destroy_session(token: str) -> None:
    """
    Invalidate a session (logout).
    Deletes the session record from the database.
    """
    from app.database.crud import delete_admin_session

    await delete_admin_session(token)
    logger.info("Admin session destroyed")


# ---------------------------------------------------------------------------
# FastAPI Dependency — require_auth
# Use with Depends() on any protected route
# ---------------------------------------------------------------------------

# Cookie name used to store the session token
SESSION_COOKIE_NAME = "admin_session"


async def require_auth(request: Request) -> str:
    """
    FastAPI dependency that verifies the admin session cookie.

    Usage in route:
        @router.get("/dashboard")
        async def dashboard(session_token: str = Depends(require_auth)):
            ...

    Raises:
        HTTPException 303: Redirect to login page if not authenticated
    """
    token = request.cookies.get(SESSION_COOKIE_NAME)

    if not token:
        # No cookie — redirect to login
        raise HTTPException(
            status_code=status.HTTP_303_SEE_OTHER,
            headers={"Location": "/admin/login"},
            detail="Authentication required",
        )

    is_valid = await validate_session(token)
    if not is_valid:
        # Cookie present but session expired or invalid
        raise HTTPException(
            status_code=status.HTTP_303_SEE_OTHER,
            headers={"Location": "/admin/login?expired=1"},
            detail="Session expired",
        )

    return token


def set_session_cookie(response, token: str) -> None:
    """
    Set the session cookie on a response.
    Cookie is HttpOnly (not accessible from JavaScript) and SameSite=Lax.

    Args:
        response: FastAPI Response object
        token:    Session token to store in the cookie
    """
    response.set_cookie(
        key=SESSION_COOKIE_NAME,
        value=token,
        httponly=True,          # Not accessible to JavaScript
        secure=settings.is_production,  # HTTPS only in production
        samesite="lax",         # CSRF protection
        max_age=settings.SESSION_EXPIRE_HOURS * 3600,  # Seconds
        path="/admin",          # Cookie only sent to /admin routes
    )


def clear_session_cookie(response) -> None:
    """
    Clear the session cookie on a response (logout).
    Sets the cookie with an immediate expiry.
    """
    response.delete_cookie(
        key=SESSION_COOKIE_NAME,
        path="/admin",
    )
