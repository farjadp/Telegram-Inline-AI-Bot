# ============================================================================
# Source: app/services/usage_tracker.py
# Version: 1.0.0 — 2026-04-16
# Why: Persists request logs and usage stats — called after every AI response
# Env / Identity: Python module — wraps database/crud for structured logging
# ============================================================================

import logging
from typing import Optional

logger = logging.getLogger(__name__)


async def track_usage(
    telegram_id: int,
    query: str,
    request_type: str,
    model: str,
    status: str = "success",
    processing_time_ms: int = 0,
    ai_response=None,       # AIResponse dataclass from ai/router.py
    error_message: Optional[str] = None,
) -> None:
    """
    Persist a completed (or failed) request to the database.
    Extracts token counts, image credits, and cost from the AIResponse object.

    This function is "best effort" — it catches all exceptions so a DB write
    failure never crashes the bot or degrades the user experience.

    Args:
        telegram_id:       The Telegram user ID who made the request
        query:             The raw inline query text
        request_type:      'text' or 'image'
        model:             AI model name used
        status:            'success', 'error', or 'rate_limited'
        processing_time_ms: How long the request took end-to-end
        ai_response:        AIResponse object (None for failed/rate-limited requests)
        error_message:      Error details (None for successful requests)
    """
    try:
        from app.database.crud import get_user_by_telegram_id, create_request

        # -----------------------------------------------------------------
        # Look up our internal user ID from the Telegram ID
        # This may be None if the user hasn't been upserted yet (edge case)
        # -----------------------------------------------------------------
        user = await get_user_by_telegram_id(telegram_id)
        user_id = user.id if user else None

        # -----------------------------------------------------------------
        # Extract fields from the AIResponse (if available)
        # -----------------------------------------------------------------
        prompt_tokens = 0
        completion_tokens = 0
        total_tokens = 0
        image_credits = 0.0
        image_url = None
        response_preview = None
        cost_usd = 0.0

        if ai_response is not None:
            cost_usd = float(ai_response.cost_usd or 0.0)

            if request_type == "text":
                # Extract token counts from the text response
                prompt_tokens = getattr(ai_response, "prompt_tokens", 0) or 0
                completion_tokens = getattr(ai_response, "completion_tokens", 0) or 0
                total_tokens = getattr(ai_response, "total_tokens", 0) or 0

                # Preview: first 500 characters of the response content
                content = getattr(ai_response, "content", "") or ""
                response_preview = content[:500] if content else None

            elif request_type == "image":
                # Extract image cost and URL
                image_credits = float(ai_response.cost_usd or 0.0)
                image_url = getattr(ai_response, "image_url", None)
                # Preview for images is the URL itself
                response_preview = image_url

        # -----------------------------------------------------------------
        # Write the request record to the database
        # -----------------------------------------------------------------
        await create_request(
            user_id=user_id,
            query=query,
            request_type=request_type,
            model=model,
            status=status,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=total_tokens,
            image_credits=image_credits,
            image_url=image_url,
            response_preview=response_preview,
            cost_usd=cost_usd,
            error_message=error_message,
            processing_time_ms=processing_time_ms,
        )

        logger.debug(
            "Usage tracked | user=%s | type=%s | model=%s | cost=$%.6f | status=%s",
            telegram_id,
            request_type,
            model,
            cost_usd,
            status,
        )

    except Exception as exc:
        # Never let a logging/tracking error crash the bot
        logger.error(
            "track_usage failed for user %s (query=%r): %s",
            telegram_id,
            query[:40],
            exc,
            exc_info=True,
        )
