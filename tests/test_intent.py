# ============================================================================
# Source: tests/test_intent.py
# Version: 1.0.0 — 2026-04-16
# Why: Tests for intent detection — English + Persian keywords → image/text routing
# Env / Identity: pytest — no external dependencies needed
# ============================================================================

import pytest
from app.bot.intent import detect_intent


# ---------------------------------------------------------------------------
# English keyword tests — each keyword should trigger "image" intent
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("query, expected_intent", [
    # Direct action words
    ("draw a cat",                   "image"),
    ("sketch a mountain",            "image"),
    ("paint a sunset landscape",     "image"),
    ("create an illustration",       "image"),
    ("generate a logo",              "image"),
    ("design a poster",              "image"),
    ("render a 3D car",              "image"),
    ("make me a wallpaper",          "image"),
    ("show me a dragon",             "image"),
    ("visualize the solar system",   "image"),
    # Noun-only triggers
    ("photo of a dog",               "image"),
    ("picture of Paris at night",    "image"),
    ("artwork of a warrior",         "image"),
    ("portrait of a scientist",      "image"),
    ("landscape of mountains",       "image"),
    # Mixed case
    ("Draw A Sunset Please",         "image"),
    ("GENERATE an image of the sea", "image"),
    # Phrase triggers
    ("give me an image of a robot",  "image"),
    ("create a picture of a fox",    "image"),
])
def test_english_image_keywords(query: str, expected_intent: str):
    """
    Every English image keyword should route the query to 'image' intent.
    Tests both lowercase and mixed-case inputs.
    """
    result = detect_intent(query)
    assert result == expected_intent, (
        f"Expected intent={expected_intent!r} for query={query!r}, got {result!r}"
    )


# ---------------------------------------------------------------------------
# Persian keyword tests — Farsi image request phrases
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("query, expected_intent", [
    ("یک گربه بساز",       "image"),   # make a cat
    ("تصویر کوه",          "image"),   # mountain image
    ("عکس یه اسب",         "image"),   # photo of a horse
    ("نقاشی from a galaxy", "image"),  # painting keyword mixed
    ("طراحی یه لوگو",      "image"),   # design a logo
    ("یه پوستر ایجاد کن",  "image"),   # create a poster
    ("بکش یه جنگل",        "image"),   # draw a forest
    ("تصویرسازی از دریا",  "image"),   # illustration of the sea
])
def test_persian_image_keywords(query: str, expected_intent: str):
    """
    Persian / Farsi image keywords should correctly detect 'image' intent.
    """
    result = detect_intent(query)
    assert result == expected_intent, (
        f"Expected intent={expected_intent!r} for query={query!r}, got {result!r}"
    )


# ---------------------------------------------------------------------------
# Text intent tests — queries that should NOT trigger image intent
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("query", [
    "what is the capital of France?",
    "explain quantum entanglement",
    "write a poem about the ocean",
    "translate hello to Spanish",
    "who invented the telephone",
    "what is PyTorch?",
    "tell me a joke",
    "how do I bake sourdough bread?",
    "مفهوم نسبیت را توضیح بده",      # Explain the concept of relativity (Persian)
    "پایتون چیست؟",                   # What is Python? (Persian)
    "یه شعر فارسی بنویس",             # Write a Farsi poem (no image keywords)
    "1 + 1 equals?",
    "recreation park near me",         # "create" substring but NOT as a whole word
])
def test_text_intent_queries(query: str):
    """
    Non-image queries should always return 'text' intent.
    Also verifies that 'recreation' doesn't match 'create' (word-boundary check).
    """
    result = detect_intent(query)
    assert result == "text", (
        f"Expected intent='text' for query={query!r}, got {result!r}"
    )


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------
def test_empty_query_returns_text():
    """Empty queries should default to 'text'."""
    assert detect_intent("") == "text"


def test_whitespace_only_returns_text():
    """Whitespace-only input should return 'text'."""
    assert detect_intent("   \n\t  ") == "text"


def test_very_long_query():
    """Very long queries should still be processed without error."""
    long_query = "draw " + "a " * 500 + "landscape"
    assert detect_intent(long_query) == "image"


def test_case_insensitive_english():
    """Intent detection should be case-insensitive for English."""
    assert detect_intent("DRAW A CAT") == "image"
    assert detect_intent("Draw A Cat") == "image"
    assert detect_intent("dRaW a CaT") == "image"


def test_special_characters_in_query():
    """Queries with special characters shouldn't break the detector."""
    result = detect_intent("draw a cat! @#$%^&*()")
    assert result == "image"
