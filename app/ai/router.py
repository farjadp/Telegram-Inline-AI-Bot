# ============================================================================
# Source: app/ai/router.py
# Version: 1.0.0 — 2026-04-16
# Why: AI request router — dispatches text/image to the correct AI client
# Env / Identity: Python module — orchestrates openai_client + flux_client
# ============================================================================

import logging
from dataclasses import dataclass, field
from typing import Literal, Optional

from app.ai.openai_client import generate_text, TextResult
from app.ai.flux_client import generate_image, ImageResult

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Unified AI Response — returned to the caller regardless of provider
# This keeps the inline handler decoupled from the specific AI client errors
# ---------------------------------------------------------------------------
@dataclass
class AIResponse:
    """
    Unified response object returned by route_query().
    Fields are populated based on intent type:
      - Text queries: content, prompt_tokens, completion_tokens, total_tokens
      - Image queries: image_url, image_credits
      - Both: model, cost_usd, intent
    """

    intent: Literal["text", "image"]     # What kind of request this was
    model: str                            # Which AI model was used

    # --- Text fields ---
    content: Optional[str] = None         # GPT response text
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0

    # --- Image fields ---
    image_url: Optional[str] = None       # Generated image URL
    image_credits: float = 0.0            # Credits consumed (for image providers)
    image_width: int = 1024
    image_height: int = 1024

    # --- Common ---
    cost_usd: float = 0.0                 # Estimated USD cost for this request


def _from_text_result(result: TextResult) -> AIResponse:
    """Convert a TextResult into a unified AIResponse."""
    return AIResponse(
        intent="text",
        model=result.model,
        content=result.content,
        prompt_tokens=result.prompt_tokens,
        completion_tokens=result.completion_tokens,
        total_tokens=result.total_tokens,
        cost_usd=result.cost_usd,
    )


def _from_image_result(result: ImageResult) -> AIResponse:
    """Convert an ImageResult into a unified AIResponse."""
    return AIResponse(
        intent="image",
        model=result.model,
        image_url=result.image_url,
        image_credits=result.cost_usd,
        image_width=result.width,
        image_height=result.height,
        cost_usd=result.cost_usd,
    )


# ---------------------------------------------------------------------------
# Main routing function
# ---------------------------------------------------------------------------
async def route_query(
    query: str,
    user_id: int | None,
    intent: Literal["text", "image"],
) -> AIResponse:
    """
    Route an inline query to the appropriate AI provider.

    Decision:
      - intent == "text"  → OpenAI GPT via openai_client.generate_text()
      - intent == "image" → Flux via flux_client.generate_image()

    Args:
        query:   The raw user query string
        user_id: Telegram user ID (passed to AI providers for tracking)
        intent:  Pre-detected intent from bot.intent.detect_intent()

    Returns:
        Unified AIResponse object

    Raises:
        Exception: Any AI provider error propagates up to the inline handler,
                   which handles it gracefully with a user-facing error message.
    """
    logger.info("Routing query | intent=%s | user=%s | query=%r", intent, user_id, query[:60])

    if intent == "text":
        # --- Route to OpenAI GPT ---
        logger.debug("Dispatching to OpenAI GPT")
        result = await generate_text(prompt=query, user_id=user_id)
        response = _from_text_result(result)
        logger.info(
            "Text response | model=%s | tokens=%d | cost=$%.6f",
            response.model,
            response.total_tokens,
            response.cost_usd,
        )
        return response

    elif intent == "image":
        # --- Route to Flux image generation ---
        logger.debug("Dispatching to Flux image generation")
        
        # -----------------------------------------------------
        # Pre-translate prompt to English to prevent hallucinations
        # -----------------------------------------------------
        try:
            from app.ai.openai_client import _get_client
            client = await _get_client()
            translation_resp = await client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {"role": "system", "content": "You are a prompt translator. Translate the given Persian (or any non-English) input to a highly descriptive English image generation prompt. ONLY output the English text without explanations."},
                    {"role": "user", "content": query}
                ],
                max_tokens=100,
                temperature=0.3
            )
            english_prompt = translation_resp.choices[0].message.content.strip()
            logger.info("Auto-translated: %r -> %r", query, english_prompt)
        except Exception as e:
            logger.warning("Translation failed: %s", e)
            english_prompt = query

        result = await generate_image(prompt=english_prompt, user_id=user_id)
        response = _from_image_result(result)
        logger.info(
            "Image response | model=%s | url=%s | cost=$%.4f",
            response.model,
            (response.image_url or "")[:60],
            response.cost_usd,
        )
        return response

    else:
        # Safety fallback — should never reach here if detect_intent() works correctly
        raise ValueError(f"Unknown intent: {intent!r}")
