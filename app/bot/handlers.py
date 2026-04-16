# ============================================================================
# Source: app/bot/handlers.py
# Version: 1.0.0 — 2026-04-16
# Why: Builds the Telegram Application and registers all update handlers
# Env / Identity: python-telegram-bot v20+ ApplicationBuilder
# ============================================================================

import logging

from telegram import Update, BotCommand
from telegram.ext import (
    Application,
    ApplicationBuilder,
    InlineQueryHandler,
    CommandHandler,
    ContextTypes,
)

from app.config import settings

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# /start command handler
# Sent when user opens a direct chat with the bot
# ---------------------------------------------------------------------------
async def handle_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Respond to the /start command.
    Provides a brief intro and instructs the user on how to use inline mode.
    """
    welcome_message = (
        "👋 *Welcome to AI Inline Bot!*\n\n"
        "Use me anywhere in Telegram by typing:\n"
        "`@{username} your question or request`\n\n"
        "📝 *Text queries:* Ask anything — I'll respond with GPT\n"
        "🎨 *Image generation:* Use words like _draw_, _create_, _تصویر_ to generate images\n\n"
        "Try it now in any chat! 👆"
    ).format(username=context.bot.username or "botname")

    await update.message.reply_text(welcome_message, parse_mode="Markdown")


# ---------------------------------------------------------------------------
# /help command handler
# ---------------------------------------------------------------------------
async def handle_help(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Provide usage instructions and examples."""
    help_message = (
        "🤖 *How to use this bot:*\n\n"
        "1️⃣ In any chat, type `@{username}` followed by your request\n"
        "2️⃣ Select the result that appears above the keyboard\n\n"
        "*Examples:*\n"
        "• `@{username} explain quantum computing`\n"
        "• `@{username} draw a mountain landscape at sunset`\n"
        "• `@{username} عکس یه گربه نارنجی`\n"
        "• `@{username} write a haiku about rain`\n\n"
        "*Keywords that trigger image generation:*\n"
        "draw, create, generate, image, picture, photo, تصویر, عکس, نقاشی, بساز…"
    ).format(username=context.bot.username or "botname")

    await update.message.reply_text(help_message, parse_mode="Markdown")


# ---------------------------------------------------------------------------
# Global error handler
# Catches all unhandled exceptions in any handler
# ---------------------------------------------------------------------------
async def handle_error(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Log all unhandled errors from the Telegram dispatcher.
    Does not send a message to the user — errors in inline queries
    are already handled gracefully inside handle_inline_query().
    """
    logger.error(
        "Unhandled exception in update %s: %s",
        update,
        context.error,
        exc_info=context.error,
    )


# ---------------------------------------------------------------------------
# Application factory — builds and configures the Telegram bot
# ---------------------------------------------------------------------------
async def setup_bot() -> Application:
    """
    Build the Telegram Application instance and register all handlers.

    Returns:
        Configured Application ready for initialize() / start() calls.
    """
    if not settings.TELEGRAM_BOT_TOKEN:
        raise ValueError(
            "TELEGRAM_BOT_TOKEN is not set. "
            "Please copy .env.example to .env and add your bot token."
        )

    # Build the Application using builder pattern
    application = (
        ApplicationBuilder()
        .token(settings.TELEGRAM_BOT_TOKEN)
        .build()
    )

    # --- Register command handlers ---
    application.add_handler(CommandHandler("start", handle_start))
    application.add_handler(CommandHandler("help", handle_help))

    # --- Register the main inline query handler ---
    from app.bot.inline import handle_inline_query  # Local import to avoid circular

    application.add_handler(InlineQueryHandler(handle_inline_query))

    # --- Register global error handler ---
    application.add_error_handler(handle_error)

    logger.info("✅ Bot handlers registered: /start, /help, inline_query")

    # Set bot commands visible in the Telegram menu
    try:
        await application.bot.set_my_commands(
            commands=[
                BotCommand("start", "Welcome message and quick start guide"),
                BotCommand("help", "Usage instructions and examples"),
            ]
        )
        logger.info("✅ Bot commands menu updated")
    except Exception as exc:
        # Non-fatal — commands menu is cosmetic
        logger.warning("Could not set bot commands: %s", exc)

    return application
