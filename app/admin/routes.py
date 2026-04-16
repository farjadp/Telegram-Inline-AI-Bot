# ============================================================================
# Source: app/admin/routes.py
# Version: 1.0.0 — 2026-04-16
# Why: All admin panel HTTP routes — dashboard, settings, history, analytics, users
# Env / Identity: FastAPI APIRouter — Jinja2 templates + JSON API endpoints
# ============================================================================

import csv
import io
import logging
from datetime import datetime, timezone, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, Form, Request, Response
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse, StreamingResponse
from fastapi.templating import Jinja2Templates

from app.admin.auth import (
    SESSION_COOKIE_NAME,
    clear_session_cookie,
    create_session,
    destroy_session,
    generate_session_token,
    require_auth,
    set_session_cookie,
    verify_admin_credentials,
)
from app.config import settings, DynamicSettings

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Router and template engine setup
# ---------------------------------------------------------------------------
admin_router = APIRouter()

# Jinja2 templates directory — relative to the project root
templates = Jinja2Templates(directory="app/admin/templates")


# ===========================================================================
# Authentication Routes
# ===========================================================================

@admin_router.get("/login", response_class=HTMLResponse)
async def login_page(request: Request, expired: Optional[str] = None, error: Optional[str] = None):
    """
    Render the admin login page.
    Shows an 'expired' message if the user's session ran out.
    """
    return templates.TemplateResponse(
        "login.html",
        {
            "request": request,
            "expired": expired == "1",
            "error": error,
        },
    )


@admin_router.post("/login", response_class=HTMLResponse)
async def login_submit(
    request: Request,
    username: str = Form(...),
    password: str = Form(...),
):
    """
    Handle admin login form submission.
    On success: create session, set cookie, redirect to dashboard.
    On failure: re-render login page with error message.
    """
    if not verify_admin_credentials(username, password):
        return templates.TemplateResponse(
            "login.html",
            {
                "request": request,
                "error": "Invalid username or password",
                "expired": False,
            },
            status_code=401,
        )

    # Valid credentials — create session
    token = generate_session_token()
    await create_session(token)

    # Redirect to dashboard with session cookie
    response = RedirectResponse(url="/admin/dashboard", status_code=303)
    set_session_cookie(response, token)
    logger.info("Admin logged in successfully")
    return response


@admin_router.post("/logout")
async def logout(request: Request, session_token: str = Depends(require_auth)):
    """
    Destroy the admin session and redirect to login page.
    """
    await destroy_session(session_token)
    response = RedirectResponse(url="/admin/login", status_code=303)
    clear_session_cookie(response)
    return response


# ===========================================================================
# Dashboard Route
# ===========================================================================

@admin_router.get("/", response_class=HTMLResponse)
async def admin_root(session_token: str = Depends(require_auth)):
    """Redirect /admin/ to /admin/dashboard for convenience."""
    return RedirectResponse(url="/admin/dashboard", status_code=303)


@admin_router.get("/dashboard", response_class=HTMLResponse)
async def dashboard(
    request: Request,
    session_token: str = Depends(require_auth),
):
    """
    Main admin dashboard — shows today's stats, charts placeholder, and recent activity.
    Charts are populated via the /api/stats JSON endpoint by admin.js.
    """
    from app.database.crud import get_analytics, get_requests

    # Load summary stats for the last 30 days
    analytics = await get_analytics(days=30)

    # Today's stats (last 24 hours)
    today_analytics = await get_analytics(days=1)

    # Last 10 requests for the activity feed
    recent_requests, _ = await get_requests(limit=10)

    return templates.TemplateResponse(
        "dashboard.html",
        {
            "request": request,
            "analytics": analytics,
            "today": today_analytics,
            "recent_requests": recent_requests,
            "active_page": "dashboard",
        },
    )


# ===========================================================================
# Settings Routes
# ===========================================================================

@admin_router.get("/settings", response_class=HTMLResponse)
async def settings_page(
    request: Request,
    session_token: str = Depends(require_auth),
    saved: Optional[str] = None,
):
    """
    Admin settings page — API keys, model config, Telegram bot settings.
    Current values are loaded from dynamic settings (DB overrides .env).
    """
    from app.database.crud import get_all_settings

    # Load all current settings from DB
    db_settings = await get_all_settings()

    # Build the display config — DB values take precedence, then .env defaults
    def get_val(key: str, default: str = "") -> str:
        return db_settings.get(key, default)

    config = {
        # OpenAI
        "openai_api_key": get_val("openai_api_key", ""),  # Masked in template
        "openai_model": get_val("openai_model", settings.OPENAI_MODEL),
        "openai_max_tokens": get_val("openai_max_tokens", str(settings.OPENAI_MAX_TOKENS)),
        "openai_temperature": get_val("openai_temperature", str(settings.OPENAI_TEMPERATURE)),
        "openai_system_prompt": get_val("openai_system_prompt", settings.OPENAI_SYSTEM_PROMPT),
        # Image generation
        "image_provider": get_val("image_provider", settings.IMAGE_PROVIDER),
        "replicate_api_token": get_val("replicate_api_token", ""),  # Masked
        "fal_api_key": get_val("fal_api_key", ""),  # Masked
        "flux_model": get_val("flux_model", settings.FLUX_MODEL),
        "flux_image_size": get_val("flux_image_size", settings.FLUX_IMAGE_SIZE),
        "flux_style_prefix": get_val("flux_style_prefix", settings.FLUX_STYLE_PREFIX),
        # Telegram
        "telegram_bot_token": get_val("telegram_bot_token", ""),  # Masked
        "telegram_webhook_url": get_val("telegram_webhook_url", settings.TELEGRAM_WEBHOOK_URL),
        "bot_mode": get_val("bot_mode", settings.BOT_MODE),
        # Rate limiting
        "rate_limit_requests": get_val("rate_limit_requests", str(settings.RATE_LIMIT_REQUESTS)),
        "rate_limit_window": get_val("rate_limit_window", str(settings.RATE_LIMIT_WINDOW)),
        # App
        "maintenance_mode": get_val("maintenance_mode", "false"),
    }

    return templates.TemplateResponse(
        "settings.html",
        {
            "request": request,
            "config": config,
            "saved": saved == "1",
            "active_page": "settings",
        },
    )


@admin_router.post("/settings")
async def save_settings(
    request: Request,
    session_token: str = Depends(require_auth),
):
    """
    Save all settings from the settings form to the database.
    Only non-empty values are saved to avoid overwriting with blanks.
    Sensitive fields (API keys) are only updated if a new value is provided.
    """
    form_data = await request.form()

    # Fields to persist — sensitive ones only saved if non-empty
    sensitive_fields = {
        "openai_api_key", "replicate_api_token", "fal_api_key", "telegram_bot_token"
    }

    saved_count = 0
    for key, value in form_data.items():
        value_str = str(value).strip()

        if key in sensitive_fields:
            # Skip empty sensitive fields — don't overwrite existing keys with blank
            if not value_str or value_str == "••••••••••••••••":
                continue

        if value_str:
            await DynamicSettings.set(key, value_str)
            saved_count += 1

    logger.info("Admin saved %d settings", saved_count)

    # Redirect back to settings page with success flag
    return RedirectResponse(url="/admin/settings?saved=1", status_code=303)


@admin_router.post("/settings/test")
async def test_api_key(request: Request, session_token: str = Depends(require_auth)):
    """
    Test an API key by making a lightweight verification request.
    Returns JSON — called via AJAX from the settings page "Test" buttons.

    Request body: {"provider": "openai"|"replicate"|"fal", "api_key": "..."}
    """
    body = await request.json()
    provider = body.get("provider", "")
    api_key = body.get("api_key", "").strip()

    if not api_key:
        return JSONResponse({"success": False, "message": "❌ No API key provided"})

    if provider == "openai":
        from app.ai.openai_client import test_api_key as test_openai
        success, message = await test_openai(api_key)

    elif provider == "replicate":
        from app.ai.flux_client import test_replicate_key
        success, message = await test_replicate_key(api_key)

    elif provider == "fal":
        from app.ai.flux_client import test_fal_key
        success, message = await test_fal_key(api_key)

    elif provider == "telegram":
        # Test Telegram bot token by calling getMe
        import httpx
        try:
            async with httpx.AsyncClient() as client:
                resp = await client.get(
                    f"https://api.telegram.org/bot{api_key}/getMe",
                    timeout=10.0,
                )
            data = resp.json()
            if data.get("ok"):
                bot = data["result"]
                success = True
                message = f"✅ Valid token — bot: @{bot.get('username', 'unknown')}"
            else:
                success = False
                message = f"❌ {data.get('description', 'Invalid token')}"
        except Exception as exc:
            success = False
            message = f"❌ Connection error: {exc}"
    else:
        return JSONResponse({"success": False, "message": f"Unknown provider: {provider}"})

    return JSONResponse({"success": success, "message": message})


# ===========================================================================
# Request History Routes
# ===========================================================================

@admin_router.get("/history", response_class=HTMLResponse)
async def history_page(
    request: Request,
    session_token: str = Depends(require_auth),
    page: int = 1,
    request_type: Optional[str] = None,
    status: Optional[str] = None,
    search: Optional[str] = None,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
):
    """
    Paginated and searchable request history log.
    Supports filtering by type, status, date range, and text search.
    """
    from app.database.crud import get_requests

    limit = 50  # Rows per page
    offset = (page - 1) * limit

    # Parse date strings from query params
    dt_from = datetime.fromisoformat(date_from) if date_from else None
    dt_to = datetime.fromisoformat(date_to) if date_to else None

    requests_list, total = await get_requests(
        limit=limit,
        offset=offset,
        request_type=request_type or None,
        status=status or None,
        search=search or None,
        date_from=dt_from,
        date_to=dt_to,
    )

    total_pages = (total + limit - 1) // limit

    return templates.TemplateResponse(
        "history.html",
        {
            "request": request,
            "requests": requests_list,
            "total": total,
            "page": page,
            "total_pages": total_pages,
            "filters": {
                "request_type": request_type or "",
                "status": status or "",
                "search": search or "",
                "date_from": date_from or "",
                "date_to": date_to or "",
            },
            "active_page": "history",
        },
    )


# ===========================================================================
# Analytics Routes
# ===========================================================================

@admin_router.get("/analytics", response_class=HTMLResponse)
async def analytics_page(
    request: Request,
    session_token: str = Depends(require_auth),
    days: int = 30,
):
    """
    Analytics page with usage charts, breakdowns, and export functionality.
    Raw chart data is fetched via /api/stats by Chart.js in admin.js.
    """
    from app.database.crud import get_analytics

    analytics = await get_analytics(days=days)

    return templates.TemplateResponse(
        "analytics.html",
        {
            "request": request,
            "analytics": analytics,
            "days": days,
            "active_page": "analytics",
        },
    )


# ===========================================================================
# User Management Routes
# ===========================================================================

@admin_router.get("/users", response_class=HTMLResponse)
async def users_page(
    request: Request,
    session_token: str = Depends(require_auth),
    page: int = 1,
    search: Optional[str] = None,
):
    """
    User management page — list all users with block/unblock controls.
    """
    from app.database.crud import get_all_users

    limit = 50
    offset = (page - 1) * limit

    users, total = await get_all_users(
        limit=limit,
        offset=offset,
        search=search or None,
    )

    total_pages = (total + limit - 1) // limit

    return templates.TemplateResponse(
        "users.html",
        {
            "request": request,
            "users": users,
            "total": total,
            "page": page,
            "total_pages": total_pages,
            "search": search or "",
            "active_page": "users",
        },
    )


@admin_router.post("/users/{telegram_id}/block")
async def block_user(
    telegram_id: int,
    request: Request,
    session_token: str = Depends(require_auth),
):
    """
    Toggle a user's blocked status.
    Request body: {"blocked": true|false}
    """
    from app.database.crud import set_user_blocked

    body = await request.json()
    blocked = bool(body.get("blocked", True))
    updated = await set_user_blocked(telegram_id, blocked)

    if updated:
        logger.info("Admin %s user %s", "blocked" if blocked else "unblocked", telegram_id)
        return JSONResponse({"success": True, "blocked": blocked})
    else:
        return JSONResponse({"success": False, "message": "User not found"}, status_code=404)


@admin_router.post("/users/{telegram_id}/rate-limit")
async def set_rate_limit(
    telegram_id: int,
    request: Request,
    session_token: str = Depends(require_auth),
):
    """
    Set a custom rate limit for a specific user.
    Request body: {"rate_limit": 10} or {"rate_limit": null} to reset to default.
    """
    from app.database.crud import set_user_rate_limit

    body = await request.json()
    rate_limit = body.get("rate_limit")  # None = reset to global default

    if rate_limit is not None:
        rate_limit = int(rate_limit)

    updated = await set_user_rate_limit(telegram_id, rate_limit)

    if updated:
        return JSONResponse({"success": True, "rate_limit": rate_limit})
    else:
        return JSONResponse({"success": False, "message": "User not found"}, status_code=404)


# ===========================================================================
# API Endpoints (JSON) — consumed by Chart.js in admin.js
# ===========================================================================

@admin_router.get("/api/stats")
async def api_stats(
    session_token: str = Depends(require_auth),
    days: int = 30,
):
    """
    JSON endpoint returning aggregated analytics for Chart.js rendering.
    Called by admin.js on dashboard and analytics pages.
    """
    from app.database.crud import get_analytics

    analytics = await get_analytics(days=days)
    return JSONResponse(analytics)


@admin_router.get("/api/export")
async def export_csv(
    session_token: str = Depends(require_auth),
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    request_type: Optional[str] = None,
):
    """
    Export request history as CSV download.
    Respects the same date range and type filters as the history page.
    """
    from app.database.crud import get_requests

    # Parse date range
    dt_from = datetime.fromisoformat(date_from) if date_from else None
    dt_to = datetime.fromisoformat(date_to) if date_to else None

    # Fetch up to 10,000 rows for export
    requests_list, total = await get_requests(
        limit=10000,
        offset=0,
        request_type=request_type or None,
        date_from=dt_from,
        date_to=dt_to,
    )

    # Build CSV in memory
    output = io.StringIO()
    writer = csv.writer(output)

    # Header row
    writer.writerow([
        "ID", "Timestamp", "User ID", "Type", "Model",
        "Query", "Response Preview", "Tokens", "Cost USD",
        "Processing Time (ms)", "Status",
    ])

    # Data rows
    for req in requests_list:
        writer.writerow([
            req.id,
            req.created_at.isoformat() if req.created_at else "",
            req.user_id or "",
            req.request_type,
            req.model,
            req.query[:200],  # Truncate long queries
            (req.response_preview or "")[:200],
            req.total_tokens or req.image_credits or "",
            float(req.cost_usd) if req.cost_usd else "",
            req.processing_time_ms or "",
            req.status,
        ])

    csv_content = output.getvalue()
    output.close()

    # Return as downloadable file
    filename = f"bot_requests_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
    return StreamingResponse(
        iter([csv_content]),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )
