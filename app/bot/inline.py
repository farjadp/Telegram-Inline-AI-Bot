# ============================================================================
# Source: app/bot/inline.py
# Version: 1.0.0 — 2026-04-16
# Why: Core inline query handler — routes queries to AI and returns results
# Env / Identity: python-telegram-bot v20+ async handler
# ============================================================================

import logging
import time
import uuid

from telegram import (
    InlineQueryResultArticle,
    InlineQueryResultPhoto,
    InputTextMessageContent,
    Update,
)
from telegram.ext import ContextTypes
from telegram.error import TelegramError

from app.bot.intent import detect_intent
from app.config import settings, DynamicSettings
from app.services.rate_limiter import rate_limiter

logger = logging.getLogger(__name__)


async def handle_inline_query(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Main inline query handler — called by Telegram every time a user types
    @botname <query> in any chat.

    Full processing flow:
      1. Validate query is non-empty
      2. Check maintenance mode
      3. Check user allow-list (if configured)
      4. Check rate limit for this user
      5. Record user in DB (or update last_active_at)
      6. Detect intent: text vs image
      7. Route to correct AI provider
      8. Return inline results to Telegram
      9. Log the request and token/cost usage

    Args:
        update:  The incoming Telegram update object
        context: Bot context (unused directly but required by the handler signature)
    """
    query = update.inline_query.query
    tg_user = update.inline_query.from_user
    start_time = time.time()

    # ------------------------------------------------------------------
    # 1. Ignore empty queries (user just typed @botname with no text yet)
    # ------------------------------------------------------------------
    if not query or not query.strip():
        return

    logger.info("Inline query from user %s: %r", tg_user.id, query[:80])

    # ------------------------------------------------------------------
    # 2. Maintenance mode — return a friendly message and stop processing
    # ------------------------------------------------------------------
    maintenance = await DynamicSettings.get("maintenance_mode", "false")
    if maintenance == "true" or settings.MAINTENANCE_MODE:
        await _answer_maintenance(update)
        return

    # ------------------------------------------------------------------
    # 3. Allowed users check — if whitelist is configured, reject others
    # ------------------------------------------------------------------
    allowed_users = settings.allowed_users_list
    if allowed_users and tg_user.id not in allowed_users:
        await _answer_not_allowed(update)
        return

    # ------------------------------------------------------------------
    # 4. Rate limit check — prevent abuse per user
    # ------------------------------------------------------------------
    if await rate_limiter.is_rate_limited(tg_user.id):
        logger.warning("Rate limited user %s", tg_user.id)
        await _answer_rate_limited(update)

        # Still log the rate-limited request to the DB
        await _log_request(
            user=tg_user,
            query=query,
            request_type="text",   # We don't know intent yet at this point
            model="—",
            status="rate_limited",
            processing_time_ms=int((time.time() - start_time) * 1000),
        )
        return

    # ------------------------------------------------------------------
    # 5. Upsert user record in database (creates if first time, updates last_active)
    # ------------------------------------------------------------------
    try:
        from app.database.crud import upsert_user
        db_user = await upsert_user(
            telegram_id=tg_user.id,
            username=tg_user.username,
            first_name=tg_user.first_name,
            last_name=tg_user.last_name,
        )

        # Check if this user is manually blocked via admin panel
        if db_user and db_user.is_blocked:
            await _answer_blocked(update)
            return
    except Exception as exc:
        logger.error("DB upsert_user error for %s: %s", tg_user.id, exc)
        db_user = None  # Continue even if DB is temporarily unavailable

    # ------------------------------------------------------------------
    # 6. Detect intent: image generation or text chat
    # ------------------------------------------------------------------
    intent = detect_intent(query)
    logger.debug("Intent detected for query %r: %s", query[:40], intent)

    # Record this request for rate limiting (sliding window)
    await rate_limiter.record_request(tg_user.id)

    # ------------------------------------------------------------------
    # 7. Route to correct AI provider and build inline results
    # ------------------------------------------------------------------
    status = "success"
    error_message = None
    results = []

    try:
        from app.ai.router import route_query

        # Call the AI router — returns TextResult or ImageResult
        ai_response = await route_query(query=query, user_id=tg_user.id, intent=intent)

        # Build Telegram inline results from AI response
        results = _build_results(intent, query, ai_response)

        # Log usage and cost to database
        await _log_request(
            user=tg_user,
            query=query,
            request_type=intent,
            model=ai_response.model,
            status="success",
            processing_time_ms=int((time.time() - start_time) * 1000),
            ai_response=ai_response,
        )

    except Exception as exc:
        logger.exception("AI route_query failed for user %s: %s", tg_user.id, exc)
        status = "error"
        error_message = str(exc)

        # Return a graceful error message inline
        results = [
            InlineQueryResultArticle(
                id=str(uuid.uuid4()),
                title="❌ Error",
                description="Something went wrong. Please try again.",
                input_message_content=InputTextMessageContent(
                    "❌ Sorry, an error occurred. Please try again later."
                ),
            )
        ]

        # Log the failed request
        await _log_request(
            user=tg_user,
            query=query,
            request_type=intent,
            model="—",
            status="error",
            error_message=error_message,
            processing_time_ms=int((time.time() - start_time) * 1000),
        )

    # ------------------------------------------------------------------
    # 8. Send results back to Telegram
    # ------------------------------------------------------------------
    try:
        await update.inline_query.answer(
            results=results,
            cache_time=300,  # Cache results for 5 minutes to reduce API calls
        )
    except TelegramError as exc:
        logger.error("Failed to answer inline query for user %s: %s", tg_user.id, exc)


# ---------------------------------------------------------------------------
# Helper: Build InlineQueryResult objects from AI response
# ---------------------------------------------------------------------------
def _build_results(intent: str, query: str, ai_response) -> list:
    """
    Convert an AIResponse into the appropriate Telegram InlineQueryResult objects.

    For text: returns up to 1 InlineQueryResultArticle with the GPT reply.
    For image: returns 1 InlineQueryResultPhoto with the generated image.
    """
    results = []

    if intent == "text":
        content = ai_response.content or "No response generated."
        # Article title: first 50 chars of response
        title = content[:50] + ("…" if len(content) > 50 else "")

        results.append(
            InlineQueryResultArticle(
                id=str(uuid.uuid4()),
                title=title,
                description=content[:100],
                input_message_content=InputTextMessageContent(
                    content,
                    parse_mode=None,  # Plain text — GPT output may contain Markdown
                ),
            )
        )

    elif intent == "image":
        image_url = ai_response.image_url
        if image_url:
            results.append(
                InlineQueryResultPhoto(
                    id=str(uuid.uuid4()),
                    photo_url=image_url,
                    thumbnail_url=image_url,
                    caption=f"🎨 {query[:200]}",
                    title=f"Generated: {query[:50]}",
                )
            )
        else:
            # Fallback if image URL is missing
            results.append(
                InlineQueryResultArticle(
                    id=str(uuid.uuid4()),
                    title="🎨 Image generation failed",
                    description="Could not generate image. Please try again.",
                    input_message_content=InputTextMessageContent(
                        "Image generation failed. Please try again."
                    ),
                )
            )

    return results


# ---------------------------------------------------------------------------
# Helper: Log request to database (non-blocking best-effort)
# ---------------------------------------------------------------------------
async def _log_request(
    user,
    query: str,
    request_type: str,
    model: str,
    status: str,
    processing_time_ms: int = 0,
    ai_response=None,
    error_message: str = None,
) -> None:
    """
    Persist request details to the database.
    Errors here are caught and logged — we never want DB writes to crash the bot.
    """
    try:
        from app.services.usage_tracker import track_usage
        await track_usage(
            telegram_id=user.id,
            query=query,
            request_type=request_type,
            model=model,
            status=status,
            processing_time_ms=processing_time_ms,
            ai_response=ai_response,
            error_message=error_message,
        )
    except Exception as exc:
        logger.error("_log_request DB write error: %s", exc)


# ---------------------------------------------------------------------------
# Helper: Canned inline responses for blocked/limited/maintenance states
# ---------------------------------------------------------------------------
async def _answer_rate_limited(update: Update) -> None:
    """Inform user they've hit the rate limit."""
    await update.inline_query.answer(
        results=[
            InlineQueryResultArticle(
                id="rate_limited",
                title="⏳ Rate Limited",
                description="You've sent too many requests. Please wait.",
                input_message_content=InputTextMessageContent(
                    "⏳ Rate limited. Please wait a moment before your next request."
                ),
            )
        ],
        cache_time=10,
    )


async def _answer_blocked(update: Update) -> None:
    """Inform a blocked user they cannot use the bot."""
    await update.inline_query.answer(
        results=[
            InlineQueryResultArticle(
                id="blocked",
                title="🚫 Access Denied",
                description="Your account has been blocked from using this bot.",
                input_message_content=InputTextMessageContent(
                    "🚫 Your access has been restricted. Contact the bot administrator."
                ),
            )
        ],
        cache_time=60,
    )


async def _answer_not_allowed(update: Update) -> None:
    """Inform a non-whitelisted user they lack access."""
    await update.inline_query.answer(
        results=[
            InlineQueryResultArticle(
                id="not_allowed",
                title="🔒 Private Bot",
                description="This bot is not available to the public.",
                input_message_content=InputTextMessageContent(
                    "🔒 This is a private bot. Access is restricted."
                ),
            )
        ],
        cache_time=60,
    )


async def _answer_maintenance(update: Update) -> None:
    """Inform users the bot is in maintenance mode."""
    await update.inline_query.answer(
        results=[
            InlineQueryResultArticle(
                id="maintenance",
                title="🔧 Under Maintenance",
                description="The bot is temporarily unavailable. Check back soon!",
                input_message_content=InputTextMessageContent(
                    "🔧 The bot is currently under maintenance. Please try again later."
                ),
            )
        ],
        cache_time=30,
    )
