# ============================================================================
# Source: app/main.py
# Version: 1.0.0 — 2026-04-16
# Why: FastAPI application factory — registers all routes and manages lifecycle
# Env / Identity: ASGI entry point — FastAPI + uvicorn
# ============================================================================

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from telegram import Update

from app.config import settings
from app.database.session import init_db

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Configure logging before anything else
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=getattr(logging, settings.LOG_LEVEL.upper(), logging.INFO),
    format="%(asctime)s | %(levelname)-8s | %(name)s — %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)


# ---------------------------------------------------------------------------
# Application Lifespan — startup and shutdown hooks
# ---------------------------------------------------------------------------
@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Manage application startup and shutdown.
    - Startup: Initialize DB, configure and start the Telegram bot
    - Shutdown: Stop the bot gracefully
    """
    logger.info("🚀 Starting Telegram AI Bot server...")

    # Initialize database tables (creates SQLite file if not using Alembic migrations)
    await init_db()
    logger.info("✅ Database initialized")

    # Start the Telegram bot
    from app.bot.handlers import setup_bot

    bot_app = await setup_bot()
    app.state.bot_app = bot_app  # Store reference for webhook route

    if settings.BOT_MODE == "polling":
        # Polling mode — no public URL required (ideal for local dev)
        logger.info("📡 Starting bot in POLLING mode...")
        await bot_app.initialize()
        await bot_app.start()
        await bot_app.updater.start_polling(
            allowed_updates=["inline_query", "message", "callback_query"]
        )
        logger.info("✅ Bot polling started")
    else:
        # Webhook mode — requires a public HTTPS URL
        logger.info("🪝 Starting bot in WEBHOOK mode: %s", settings.TELEGRAM_WEBHOOK_URL)
        await bot_app.initialize()
        await bot_app.start()
        await bot_app.bot.set_webhook(
            url=f"{settings.TELEGRAM_WEBHOOK_URL}/webhook",
            allowed_updates=["inline_query", "message", "callback_query"],
        )
        logger.info("✅ Webhook registered")

    logger.info("🌐 Admin panel available at /admin")

    yield  # Application runs here — everything above is startup, below is shutdown

    # ---------------------------------------------------------------------------
    # Shutdown — gracefully stop the Telegram bot updater
    # ---------------------------------------------------------------------------
    logger.info("🛑 Shutting down bot...")
    if settings.BOT_MODE == "polling":
        await bot_app.updater.stop()
    await bot_app.stop()
    await bot_app.shutdown()
    logger.info("👋 Bot shutdown complete")


# ---------------------------------------------------------------------------
# FastAPI Application Instance
# ---------------------------------------------------------------------------
app = FastAPI(
    title="Telegram Inline AI Bot",
    description="Telegram inline bot routing text to OpenAI GPT and images to Flux",
    version="1.0.0",
    docs_url="/docs" if settings.DEBUG else None,   # Disable Swagger in production
    redoc_url="/redoc" if settings.DEBUG else None,
    lifespan=lifespan,
)

# Mount static files (CSS, JS for admin panel)
app.mount("/static", StaticFiles(directory="app/static"), name="static")

# ---------------------------------------------------------------------------
# Telegram Webhook Route
# Only active when BOT_MODE=webhook — receives updates from Telegram servers
# ---------------------------------------------------------------------------
@app.post("/webhook")
async def telegram_webhook(request: Request):
    """
    Receive Telegram update payloads via webhook.
    Telegram POST's update JSON here after set_webhook() is called.
    """
    if settings.BOT_MODE != "webhook":
        return JSONResponse({"error": "Webhook not enabled"}, status_code=400)

    # Parse raw JSON body into a Telegram Update object
    data = await request.json()
    update = Update.de_json(data, request.app.state.bot_app.bot)

    # Queue the update for processing by the bot application
    await request.app.state.bot_app.process_update(update)

    return JSONResponse({"ok": True})


# ---------------------------------------------------------------------------
# Health Check Endpoint
# Used by load balancers and monitoring tools to verify the app is alive
# ---------------------------------------------------------------------------
@app.get("/health")
async def health_check():
    """Simple liveness probe — returns OK if the app is running."""
    return {
        "status": "ok",
        "version": "1.0.0",
        "bot_mode": settings.BOT_MODE,
        "env": settings.APP_ENV,
    }


# ---------------------------------------------------------------------------
# Admin Panel Router — mounted under /admin prefix
# ---------------------------------------------------------------------------
from app.admin.routes import admin_router  # noqa: E402 — must be after app creation

app.include_router(admin_router, prefix="/admin")

# ---------------------------------------------------------------------------
# Root redirect → admin panel for convenience
# ---------------------------------------------------------------------------
from fastapi.responses import RedirectResponse  # noqa: E402


@app.get("/")
async def root():
    """Redirect root URL to the admin panel dashboard."""
    return RedirectResponse(url="/admin/dashboard")
