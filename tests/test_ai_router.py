# ============================================================================
# Source: tests/test_ai_router.py
# Version: 1.0.0 — 2026-04-16
# Why: Tests for the AI routing layer — mocked OpenAI and Flux clients
# Env / Identity: pytest + unittest.mock — async test with pytest-asyncio
# ============================================================================

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from dataclasses import dataclass

from app.ai.openai_client import calculate_text_cost, TextResult
from app.ai.flux_client import FLUX_PRICING, ImageResult


# ---------------------------------------------------------------------------
# Cost Calculation Tests — pure math, no mocks needed
# ---------------------------------------------------------------------------

class TestCostCalculation:
    """Unit tests for the cost calculation utility functions."""

    def test_gpt4o_mini_cost(self):
        """
        gpt-4o-mini is the cheapest model — verify cost is correctly low.
        100 prompt tokens + 100 completion tokens @ gpt-4o-mini pricing.
        """
        cost = calculate_text_cost(
            model="gpt-4o-mini",
            prompt_tokens=100,
            completion_tokens=100,
        )
        # Input: (100/1000) * 0.00015 = 0.000015
        # Output: (100/1000) * 0.0006  = 0.000060
        # Total = 0.000075
        assert cost == pytest.approx(0.000075, rel=1e-5)

    def test_gpt4o_cost(self):
        """gpt-4o is more expensive — verify correct calculation."""
        cost = calculate_text_cost(
            model="gpt-4o",
            prompt_tokens=1000,
            completion_tokens=500,
        )
        # Input:  (1000/1000) * 0.005  = 0.005
        # Output: (500/1000)  * 0.015  = 0.0075
        # Total = 0.0125
        assert cost == pytest.approx(0.0125, rel=1e-5)

    def test_zero_tokens_cost(self):
        """Zero tokens should produce zero cost."""
        cost = calculate_text_cost("gpt-4o-mini", 0, 0)
        assert cost == 0.0

    def test_unknown_model_uses_default_pricing(self):
        """An unknown model should fall back to gpt-4o-mini pricing."""
        cost_unknown = calculate_text_cost("gpt-99-ultra", 1000, 1000)
        cost_default = calculate_text_cost("gpt-4o-mini", 1000, 1000)
        assert cost_unknown == pytest.approx(cost_default, rel=1e-5)

    def test_flux_schnell_price(self):
        """Flux-schnell should be the cheapest image model at $0.003."""
        price = FLUX_PRICING["black-forest-labs/flux-schnell"]
        assert price == 0.003

    def test_flux_pro_price(self):
        """Flux-pro should be the most expensive image model at $0.055."""
        price = FLUX_PRICING["black-forest-labs/flux-pro"]
        assert price == pytest.approx(0.055, rel=1e-5)


# ---------------------------------------------------------------------------
# AI Router Tests — mock the clients to avoid real API calls
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
class TestAIRouter:
    """Integration tests for the AI router — uses mocked AI providers."""

    async def test_text_routing(self):
        """
        route_query with intent='text' should call generate_text
        and return an AIResponse with text fields populated.
        """
        mock_text_result = TextResult(
            content="The capital of France is Paris.",
            model="gpt-4o-mini",
            prompt_tokens=10,
            completion_tokens=8,
            total_tokens=18,
            cost_usd=0.0000135,
        )

        with patch(
            "app.ai.router.generate_text",
            new=AsyncMock(return_value=mock_text_result),
        ):
            from app.ai.router import route_query

            response = await route_query(
                query="What is the capital of France?",
                user_id=12345,
                intent="text",
            )

        # Verify the response structure
        assert response.intent == "text"
        assert response.model == "gpt-4o-mini"
        assert response.content == "The capital of France is Paris."
        assert response.total_tokens == 18
        assert response.cost_usd == pytest.approx(0.0000135, rel=1e-5)
        # Image fields should not be set
        assert response.image_url is None

    async def test_image_routing(self):
        """
        route_query with intent='image' should call generate_image
        and return an AIResponse with image fields populated.
        """
        mock_image_result = ImageResult(
            image_url="https://example.replicate.delivery/generated.webp",
            model="black-forest-labs/flux-schnell",
            cost_usd=0.003,
            width=1024,
            height=1024,
        )

        with patch(
            "app.ai.router.generate_image",
            new=AsyncMock(return_value=mock_image_result),
        ):
            from app.ai.router import route_query

            response = await route_query(
                query="draw a sunset over the mountains",
                user_id=12345,
                intent="image",
            )

        # Verify the response structure
        assert response.intent == "image"
        assert response.model == "black-forest-labs/flux-schnell"
        assert response.image_url == "https://example.replicate.delivery/generated.webp"
        assert response.cost_usd == pytest.approx(0.003, rel=1e-5)
        # Text fields should not be set
        assert response.content is None
        assert response.total_tokens == 0

    async def test_invalid_intent_raises(self):
        """
        An unknown intent string should raise a ValueError.
        Ensures the router has a safe fallback for unexpected values.
        """
        from app.ai.router import route_query

        with pytest.raises(ValueError, match="Unknown intent"):
            await route_query(
                query="some query",
                user_id=999,
                intent="audio",  # type: ignore — intentionally wrong
            )

    async def test_text_client_error_propagates(self):
        """
        If generate_text raises an exception, route_query should propagate it.
        The inline handler is responsible for catching and formatting errors.
        """
        with patch(
            "app.ai.router.generate_text",
            new=AsyncMock(side_effect=Exception("OpenAI API error")),
        ):
            from app.ai.router import route_query

            with pytest.raises(Exception, match="OpenAI API error"):
                await route_query("tell me a joke", user_id=1, intent="text")


# ---------------------------------------------------------------------------
# TextResult and ImageResult dataclass tests
# ---------------------------------------------------------------------------

class TestResultDataclasses:
    """Verify that result dataclasses have the correct default values."""

    def test_text_result_defaults(self):
        """TextResult should have sensible zero defaults."""
        result = TextResult(content="Hello", model="gpt-4o-mini")
        assert result.prompt_tokens == 0
        assert result.completion_tokens == 0
        assert result.total_tokens == 0
        assert result.cost_usd == 0.0

    def test_image_result_defaults(self):
        """ImageResult should default to 1024x1024."""
        result = ImageResult(
            image_url="https://example.com/img.webp",
            model="flux-schnell",
        )
        assert result.width == 1024
        assert result.height == 1024
        assert result.cost_usd == 0.0
