# ============================================================================
# Source: app/ai/flux_client.py
# Version: 1.0.0 — 2026-04-16
# Why: Flux image generation — supports Replicate and fal.ai providers
# Env / Identity: Python module — replicate + fal-client async SDKs
# ============================================================================

import logging
import asyncio
from dataclasses import dataclass

from app.config import settings, DynamicSettings

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Per-image pricing — in USD
# Pricing as of April 2026 — update when provider prices change
# ---------------------------------------------------------------------------
FLUX_PRICING: dict[str, float] = {
    # Replicate models (billed per generation)
    "black-forest-labs/flux-pro": 0.055,
    "black-forest-labs/flux-dev": 0.025,
    "black-forest-labs/flux-schnell": 0.003,
    # fal.ai models
    "fal-ai/flux-pro": 0.055,
    "fal-ai/flux/dev": 0.025,
    "fal-ai/flux/schnell": 0.003,
}

DEFAULT_IMAGE_COST = 0.025  # Fallback if model not in table


# ---------------------------------------------------------------------------
# Result dataclass — structured response from generate_image()
# ---------------------------------------------------------------------------
@dataclass
class ImageResult:
    """Structured result from a Flux image generation request."""

    image_url: str          # Direct URL to the generated image
    model: str              # Model that was used
    cost_usd: float = 0.0   # Estimated cost in USD
    width: int = 1024
    height: int = 1024


# ---------------------------------------------------------------------------
# Replicate provider
# ---------------------------------------------------------------------------
async def _generate_via_replicate(
    prompt: str,
    model: str,
    width: int,
    height: int,
    api_token: str,
) -> str:
    """
    Run a Flux model on Replicate and return the generated image URL.

    Replicate's Python client is synchronous — we run it in a thread pool
    to keep the FastAPI event loop free during the blocking API call.

    Args:
        prompt:    Text prompt for image generation
        model:     Replicate model identifier (e.g. "black-forest-labs/flux-schnell")
        width:     Output image width in pixels
        height:    Output image height in pixels
        api_token: Replicate API token

    Returns:
        URL string of the generated image (may be a FileOutput object from SDK)

    Raises:
        Exception: if the Replicate API call fails
    """
    import replicate  # Imported here to avoid errors if package not installed

    # Configure the client with the provided API token
    client = replicate.Client(api_token=api_token)

    logger.debug("Replicate request | model=%s | size=%dx%d", model, width, height)

    # Run the blocking Replicate call in a thread pool executor
    loop = asyncio.get_event_loop()
    output = await loop.run_in_executor(
        None,  # Default thread pool
        lambda: client.run(
            model,
            input={
                "prompt": prompt,
                "width": width,
                "height": height,
                "num_inference_steps": 4 if "schnell" in model else 28,
                "output_format": "webp",
                "output_quality": 90,
            },
        ),
    )

    # Replicate returns either a list or a FileOutput — extract the URL
    if isinstance(output, list):
        image_url = str(output[0])
    else:
        image_url = str(output)

    logger.info("Replicate image generated: %s", image_url[:80])
    return image_url


# ---------------------------------------------------------------------------
# fal.ai provider
# ---------------------------------------------------------------------------
async def _generate_via_fal(
    prompt: str,
    model: str,
    width: int,
    height: int,
    api_key: str,
) -> str:
    """
    Run a Flux model on fal.ai and return the generated image URL.
    fal-client has native async support.

    Args:
        prompt:  Text prompt for image generation
        model:   fal.ai model identifier (e.g. "fal-ai/flux/schnell")
        width:   Output image width
        height:  Output image height
        api_key: fal.ai API key

    Returns:
        URL string of the first generated image

    Raises:
        Exception: if the fal.ai API call fails
    """
    import fal_client  # Imported here to avoid errors if package not installed
    import os

    logger.debug("fal.ai request | model=%s | size=%dx%d", model, width, height)

    # fal_client currently reads from environment securely per thread/process
    os.environ["FAL_KEY"] = api_key

    # Advanced models (v1.1, ultra) use different argument signatures
    args = {"prompt": prompt}
    if "v1.1" in model or "ultra" in model:
        args["aspect_ratio"] = "1:1"  # Defaulting to square, advanced handling can be added
    else:
        args["image_size"] = {"width": width, "height": height}
        args["num_inference_steps"] = 4 if "schnell" in model else 28
        args["num_images"] = 1

    # fal_client.run_async() no longer accepts 'key' parameter directly
    result = await fal_client.run_async(
        model,
        arguments=args,
    )

    # fal.ai result shape: {"images": [{"url": "https://..."}]}
    images = result.get("images", [])
    if not images:
        raise ValueError("fal.ai returned no images in response")

    image_url = images[0].get("url") or images[0].get("path")
    if not image_url:
        raise ValueError(f"fal.ai image URL missing from response: {result}")

    logger.info("fal.ai image generated: %s", image_url[:80])
    return image_url


# ---------------------------------------------------------------------------
# Public API — called by ai/router.py
# ---------------------------------------------------------------------------
async def generate_image(prompt: str, user_id: int | None = None) -> ImageResult:
    """
    Generate an image from a text prompt using the configured provider.

    Loads all settings dynamically so admin panel changes take effect
    without restarting the app.

    Args:
        prompt:  The user's image generation prompt
        user_id: Telegram user ID (for logging only)

    Returns:
        ImageResult with image_url, model name, and cost

    Raises:
        ValueError: if provider is not configured
        Exception:  if the provider API call fails
    """
    # Load dynamic settings (admin panel overrides)
    provider = await DynamicSettings.get("image_provider") or settings.IMAGE_PROVIDER
    model = await DynamicSettings.get("flux_model") or settings.FLUX_MODEL
    size_str = await DynamicSettings.get("flux_image_size") or settings.FLUX_IMAGE_SIZE
    style_prefix = await DynamicSettings.get("flux_style_prefix") or settings.FLUX_STYLE_PREFIX

    # Parse "1024x1024" → (1024, 1024)
    try:
        width, height = (int(x) for x in size_str.lower().split("x"))
    except ValueError:
        logger.warning("Invalid FLUX_IMAGE_SIZE '%s', using 1024x1024", size_str)
        width, height = 1024, 1024

    # Prepend optional style prefix to enrich the prompt
    full_prompt = f"{style_prefix}{prompt}" if style_prefix else prompt

    logger.info(
        "Image generation | provider=%s | model=%s | user=%s | prompt=%r",
        provider,
        model,
        user_id,
        full_prompt[:60],
    )

    # --- Dispatch to the correct provider ---
    if provider == "replicate":
        api_token = await DynamicSettings.get("replicate_api_token") or settings.REPLICATE_API_TOKEN
        if not api_token:
            raise ValueError("REPLICATE_API_TOKEN is not configured")
        image_url = await _generate_via_replicate(full_prompt, model, width, height, api_token)

    elif provider == "fal":
        api_key = await DynamicSettings.get("fal_api_key") or settings.FAL_API_KEY
        if not api_key:
            raise ValueError("FAL_API_KEY is not configured")
        image_url = await _generate_via_fal(full_prompt, model, width, height, api_key)

    else:
        raise ValueError(f"Unknown image provider: {provider!r}. Expected 'replicate' or 'fal'")

    # Calculate cost
    cost = FLUX_PRICING.get(model, DEFAULT_IMAGE_COST)

    return ImageResult(
        image_url=image_url,
        model=model,
        cost_usd=cost,
        width=width,
        height=height,
    )


async def test_replicate_key(api_token: str) -> tuple[bool, str]:
    """
    Validate a Replicate API token by fetching the account info endpoint.
    Used by the admin panel "Test" button.
    """
    try:
        import httpx

        async with httpx.AsyncClient() as client:
            resp = await client.get(
                "https://api.replicate.com/v1/account",
                headers={"Authorization": f"Token {api_token}"},
                timeout=10.0,
            )
        if resp.status_code == 200:
            data = resp.json()
            username = data.get("username", "unknown")
            return True, f"✅ Valid token — account: {username}"
        else:
            return False, f"❌ HTTP {resp.status_code}: {resp.text[:200]}"
    except Exception as exc:
        return False, f"❌ Connection error: {exc}"


async def test_fal_key(api_key: str) -> tuple[bool, str]:
    """
    Validate a fal.ai API key by calling a lightweight endpoint.
    Used by the admin panel "Test" button.
    """
    try:
        import httpx

        async with httpx.AsyncClient() as client:
            resp = await client.get(
                "https://fal.run/info",
                headers={"Authorization": f"Key {api_key}"},
                timeout=10.0,
            )
        if resp.status_code in (200, 404):
            # 404 is acceptable — key is valid, endpoint just doesn't exist
            return True, "✅ Valid fal.ai API key"
        elif resp.status_code == 401:
            return False, "❌ Invalid API key (401 Unauthorized)"
        else:
            return False, f"❌ HTTP {resp.status_code}"
    except Exception as exc:
        return False, f"❌ Connection error: {exc}"
