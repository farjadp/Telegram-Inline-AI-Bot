# ============================================================================
# Source: app/bot/intent.py
# Version: 1.0.0 — 2026-04-16
# Why: Detects user intent from inline query text — routes to image or text AI
# Env / Identity: Python module — no external dependencies
# ============================================================================

import re
from typing import Literal

# ---------------------------------------------------------------------------
# Keyword lists for image intent detection
# Covers both English and Persian / Farsi trigger words
# ---------------------------------------------------------------------------
IMAGE_KEYWORDS_EN = [
    # Actions
    "draw", "sketch", "paint", "render", "generate", "create", "make",
    "design", "build", "produce", "show", "visualize", "illustrate",
    # Nouns indicating a visual output is expected
    "image", "picture", "photo", "photograph", "illustration",
    "artwork", "art", "painting", "portrait", "landscape",
    "wallpaper", "thumbnail", "poster", "logo", "icon",
    # Common prefix phrases
    "make me", "show me", "give me", "create a", "generate a",
    "draw a", "draw me", "paint a",
]

IMAGE_KEYWORDS_FA = [
    # Persian / Farsi verbs for creation
    "بساز",       # make / create
    "بکش",        # draw
    "طراحی",      # design / draw
    "رسم",        # drawing / sketch
    "ایجاد",      # create
    "تولید",      # produce / generate
    "بسازید",     # create (formal)
    "بکشید",      # draw (formal)
    # Persian nouns for visual content
    "تصویر",      # image / picture
    "عکس",        # photo
    "نقاشی",      # painting
    "طرح",        # design / sketch
    "پس‌زمینه",   # wallpaper / background
    "لوگو",       # logo
    "آیکون",      # icon
    "پوستر",      # poster
    "تصویرسازی",  # illustration
]

# Combined flat list used by detect_intent()
ALL_IMAGE_KEYWORDS = IMAGE_KEYWORDS_EN + IMAGE_KEYWORDS_FA


def detect_intent(query: str) -> Literal["image", "text"]:
    """
    Determine whether a query is requesting image generation or a text response.

    Strategy:
      1. Normalize the query (lowercase, strip whitespace)
      2. Check if any image keyword appears as a substring
      3. Use a simple word-boundary regex for single-word English keywords
         to avoid false positives (e.g. "create" vs "recreation")

    Args:
        query: Raw inline query string from Telegram

    Returns:
        "image" if the query appears to request image generation,
        "text"  for all other queries (chat / factual / etc.)

    Examples:
        >>> detect_intent("draw a sunset")   → "image"
        >>> detect_intent("تصویر گربه")      → "image"
        >>> detect_intent("what is python?") → "text"
    """
    if not query or not query.strip():
        return "text"

    query_lower = query.lower().strip()

    # --- Check Persian / multi-char keywords as plain substrings ---
    # Persian keywords don't need word-boundary checks since they are
    # distinct character sequences in Farsi text.
    for keyword in IMAGE_KEYWORDS_FA:
        if keyword in query_lower:
            return "image"

    # --- Check English keywords with word-boundary awareness ---
    # Use regex word boundaries to avoid matching "recreation" as "create"
    for keyword in IMAGE_KEYWORDS_EN:
        # Escape keyword for regex safety, wrap in word boundaries
        pattern = r"\b" + re.escape(keyword) + r"\b"
        if re.search(pattern, query_lower):
            return "image"

    # Nothing matched → treat as a text / chat query
    return "text"


def get_image_keywords() -> list[str]:
    """Return the full list of image trigger keywords (for admin display)."""
    return ALL_IMAGE_KEYWORDS.copy()
