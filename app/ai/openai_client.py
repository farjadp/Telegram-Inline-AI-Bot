# ============================================================================
# Source: app/ai/openai_client.py
# Version: 1.0.0 — 2026-04-16
# Why: Async OpenAI GPT client — wraps chat completions with cost calculation
# Env / Identity: Python module — openai v1.x async API
# ============================================================================

import logging
from dataclasses import dataclass, field

from openai import AsyncOpenAI, OpenAIError

from app.config import settings, DynamicSettings

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Token pricing table — per 1,000 tokens (input / output)
# Update these values when OpenAI changes their pricing
# ---------------------------------------------------------------------------
OPENAI_PRICING: dict[str, dict[str, float]] = {
    "gpt-4o": {
        "input": 0.005,    # $0.005 per 1K input tokens
        "output": 0.015,   # $0.015 per 1K output tokens
    },
    "gpt-4o-mini": {
        "input": 0.00015,
        "output": 0.0006,
    },
    "gpt-3.5-turbo": {
        "input": 0.0005,
        "output": 0.0015,
    },
    "gpt-4-turbo": {
        "input": 0.010,
        "output": 0.030,
    },
}

# Default pricing if model is not in the table
DEFAULT_PRICING = OPENAI_PRICING["gpt-4o-mini"]


# ---------------------------------------------------------------------------
# Result dataclass — structured response from generate_text()
# ---------------------------------------------------------------------------
@dataclass
class TextResult:
    """Structured result from an OpenAI chat completion request."""

    content: str                   # The actual GPT response text
    model: str                     # Model that was used (may differ from requested)
    prompt_tokens: int = 0         # Tokens used in the prompt (input)
    completion_tokens: int = 0     # Tokens used in the completion (output)
    total_tokens: int = 0          # prompt_tokens + completion_tokens
    cost_usd: float = 0.0          # Estimated cost in USD


# ---------------------------------------------------------------------------
# Lazy-initialized async client
# We reuse a single AsyncOpenAI instance for connection pooling
# ---------------------------------------------------------------------------
_client: AsyncOpenAI | None = None


def _get_client() -> AsyncOpenAI:
    """
    Return the shared AsyncOpenAI client, creating it on first call.
    The API key is read fresh each time to pick up any admin panel updates.
    """
    global _client
    if _client is None:
        _client = AsyncOpenAI(api_key=settings.OPENAI_API_KEY)
    return _client


def calculate_text_cost(model: str, prompt_tokens: int, completion_tokens: int) -> float:
    """
    Estimate the USD cost of an OpenAI API call.

    Args:
        model:             Model name string (e.g. "gpt-4o-mini")
        prompt_tokens:     Number of input tokens
        completion_tokens: Number of output tokens

    Returns:
        Estimated cost in USD (may be $0.00 for very small requests)
    """
    # Look up the base model name (strip version suffixes like "-2024-05-13")
    pricing = next(
        (OPENAI_PRICING[key] for key in OPENAI_PRICING if key in model),
        DEFAULT_PRICING,
    )

    input_cost = (prompt_tokens / 1000) * pricing["input"]
    output_cost = (completion_tokens / 1000) * pricing["output"]
    return round(input_cost + output_cost, 8)


async def generate_text(
    prompt: str,
    user_id: int | None = None,
) -> TextResult:
    """
    Send a prompt to OpenAI GPT and return a structured TextResult.

    Settings (model, max_tokens, temperature, system_prompt) are loaded
    dynamically from the DB so admin panel changes take effect immediately.

    Args:
        prompt:  The user's inline query text
        user_id: Telegram user ID (passed to OpenAI for abuse detection)

    Returns:
        TextResult with content, token counts, and estimated cost

    Raises:
        OpenAIError: if the API call fails (caller handles this)
    """
    # Load dynamic settings — admin panel values override .env defaults
    model = await DynamicSettings.get("openai_model") or settings.OPENAI_MODEL
    max_tokens = int(await DynamicSettings.get("openai_max_tokens") or settings.OPENAI_MAX_TOKENS)
    temperature = float(await DynamicSettings.get("openai_temperature") or settings.OPENAI_TEMPERATURE)
    system_prompt = (
        await DynamicSettings.get("openai_system_prompt") or settings.OPENAI_SYSTEM_PROMPT
    )

    # Re-create client if API key was changed via admin panel
    api_key = await DynamicSettings.get("openai_api_key") or settings.OPENAI_API_KEY
    client = AsyncOpenAI(api_key=api_key)

    logger.debug(
        "OpenAI request | model=%s | max_tokens=%d | temp=%.1f | prompt=%r",
        model,
        max_tokens,
        temperature,
        prompt[:60],
    )

    try:
        response = await client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": prompt},
            ],
            max_tokens=max_tokens,
            temperature=temperature,
            user=str(user_id) if user_id else None,  # OpenAI abuse detection
        )
    except OpenAIError as exc:
        logger.error("OpenAI API error: %s", exc)
        raise

    # Extract response data
    choice = response.choices[0]
    content = choice.message.content or ""
    usage = response.usage

    prompt_tokens = usage.prompt_tokens if usage else 0
    completion_tokens = usage.completion_tokens if usage else 0
    total_tokens = usage.total_tokens if usage else 0

    cost = calculate_text_cost(model, prompt_tokens, completion_tokens)

    logger.info(
        "OpenAI response | model=%s | tokens=%d | cost=$%.6f",
        model,
        total_tokens,
        cost,
    )

    return TextResult(
        content=content,
        model=model,
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        total_tokens=total_tokens,
        cost_usd=cost,
    )


async def test_api_key(api_key: str) -> tuple[bool, str]:
    """
    Validate an OpenAI API key by making a lightweight models list call.
    Used by the admin panel "Test" button.

    Returns:
        (True, "OK") on success
        (False, error_message) on failure
    """
    try:
        client = AsyncOpenAI(api_key=api_key)
        models = await client.models.list()
        # Check that GPT models are accessible
        model_ids = [m.id for m in models.data]
        gpt_models = [m for m in model_ids if "gpt" in m]
        return True, f"✅ Valid key — {len(gpt_models)} GPT models available"
    except OpenAIError as exc:
        return False, f"❌ {exc}"
    except Exception as exc:
        return False, f"❌ Unexpected error: {exc}"
