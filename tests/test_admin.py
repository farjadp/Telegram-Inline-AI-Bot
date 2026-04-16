# ============================================================================
# Source: tests/test_admin.py
# Version: 1.0.0 — 2026-04-16
# Why: Admin panel route tests — login, session auth, settings, API endpoints
# Env / Identity: pytest + FastAPI TestClient (httpx) — async tests
# ============================================================================

import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from fastapi.testclient import TestClient

# ---------------------------------------------------------------------------
# Fixtures — shared test setup
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def test_client():
    """
    Create a FastAPI TestClient for the admin panel.
    Mocks database calls so tests don't require a real database.
    """
    # Patch init_db and bot setup to prevent real I/O during tests
    with (
        patch("app.database.session.init_db", new=AsyncMock()),
        patch("app.bot.handlers.setup_bot", new=AsyncMock(return_value=MagicMock())),
        patch("app.config.settings.TELEGRAM_BOT_TOKEN", "fake_token_for_testing"),
    ):
        from app.main import app
        client = TestClient(app, raise_server_exceptions=False)
        yield client


@pytest.fixture
def authenticated_client(test_client):
    """
    A client fixture that is pre-authenticated as admin.
    Mocks session validation so we don't need a real DB session.
    """
    with patch("app.admin.auth.validate_session", new=AsyncMock(return_value=True)):
        yield test_client


# ---------------------------------------------------------------------------
# Login Page Tests
# ---------------------------------------------------------------------------

class TestLoginPage:
    """Tests for the admin login flow."""

    def test_login_page_renders(self, test_client):
        """GET /admin/login should return 200 with the login form."""
        response = test_client.get("/admin/login")
        assert response.status_code == 200
        assert "Admin Login" in response.text
        assert 'name="username"' in response.text
        assert 'name="password"' in response.text

    def test_login_page_expired_notice(self, test_client):
        """Login page with ?expired=1 should show the session expired notice."""
        response = test_client.get("/admin/login?expired=1")
        assert response.status_code == 200
        assert "expired" in response.text.lower()

    def test_login_wrong_credentials(self, test_client):
        """
        POST with wrong credentials should re-render login with an error,
        and NOT set a session cookie.
        """
        with patch(
            "app.admin.auth.verify_admin_credentials",
            return_value=False,
        ):
            response = test_client.post(
                "/admin/login",
                data={"username": "admin", "password": "wrongpassword"},
                follow_redirects=False,
            )

        assert response.status_code == 401
        assert "Invalid username or password" in response.text
        # No session cookie should be set on failed login
        assert "admin_session" not in response.cookies

    def test_login_correct_credentials_redirects(self, test_client):
        """
        POST with correct credentials should redirect to dashboard
        and set the admin_session cookie.
        """
        with (
            patch("app.admin.auth.verify_admin_credentials", return_value=True),
            patch("app.admin.auth.create_session", new=AsyncMock()),
        ):
            response = test_client.post(
                "/admin/login",
                data={"username": "admin", "password": "correct_password"},
                follow_redirects=False,
            )

        # Should redirect to dashboard
        assert response.status_code == 303
        assert response.headers["location"] == "/admin/dashboard"


# ---------------------------------------------------------------------------
# Authentication Middleware Tests
# ---------------------------------------------------------------------------

class TestAuthGuard:
    """Tests that protected routes require valid session."""

    def test_dashboard_redirects_unauthenticated(self, test_client):
        """
        GET /admin/dashboard without session cookie should redirect to login.
        """
        with patch("app.admin.auth.validate_session", new=AsyncMock(return_value=False)):
            response = test_client.get("/admin/dashboard", follow_redirects=False)
        # Should redirect (302 or 303) to login
        assert response.status_code in (302, 303)
        assert "/admin/login" in response.headers.get("location", "")

    def test_settings_redirects_unauthenticated(self, test_client):
        """Settings page should not be accessible without auth."""
        with patch("app.admin.auth.validate_session", new=AsyncMock(return_value=False)):
            response = test_client.get("/admin/settings", follow_redirects=False)
        assert response.status_code in (302, 303)


# ---------------------------------------------------------------------------
# API Stats Endpoint Tests
# ---------------------------------------------------------------------------

class TestApiStats:
    """Tests for the JSON stats endpoint consumed by Chart.js."""

    def test_stats_returns_json(self, authenticated_client):
        """GET /admin/api/stats should return valid JSON with expected keys."""
        mock_analytics = {
            "total_requests": 100,
            "text_requests": 80,
            "image_requests": 20,
            "total_tokens": 50000,
            "total_cost_usd": 0.0075,
            "active_users": 15,
            "daily_stats": [],
            "top_users": [],
        }

        with (
            patch("app.admin.auth.validate_session", new=AsyncMock(return_value=True)),
            patch("app.database.crud.get_analytics", new=AsyncMock(return_value=mock_analytics)),
        ):
            response = authenticated_client.get("/admin/api/stats")

        assert response.status_code == 200
        data = response.json()

        # Verify all expected keys are present
        assert "total_requests" in data
        assert "text_requests" in data
        assert "image_requests" in data
        assert "total_tokens" in data
        assert "total_cost_usd" in data
        assert "active_users" in data
        assert data["total_requests"] == 100
        assert data["text_requests"] == 80
        assert data["image_requests"] == 20


# ---------------------------------------------------------------------------
# Settings Tests
# ---------------------------------------------------------------------------

class TestSettings:
    """Tests for the settings page and save endpoint."""

    def test_settings_page_renders(self, authenticated_client):
        """GET /admin/settings should render the settings form."""
        with (
            patch("app.admin.auth.validate_session", new=AsyncMock(return_value=True)),
            patch(
                "app.database.crud.get_all_settings",
                new=AsyncMock(return_value={}),
            ),
        ):
            response = authenticated_client.get("/admin/settings")

        assert response.status_code == 200
        # Should contain the three main config sections
        assert "OpenAI Configuration" in response.text
        assert "Image Generation" in response.text
        assert "Telegram Bot" in response.text

    def test_api_key_test_endpoint_no_key(self, authenticated_client):
        """
        POST /admin/settings/test with no API key should return failure.
        """
        with patch("app.admin.auth.validate_session", new=AsyncMock(return_value=True)):
            response = authenticated_client.post(
                "/admin/settings/test",
                json={"provider": "openai", "api_key": ""},
            )

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is False
        assert "No API key provided" in data["message"]

    def test_api_key_test_unknown_provider(self, authenticated_client):
        """
        POST /admin/settings/test with an unknown provider should return failure message.
        """
        with patch("app.admin.auth.validate_session", new=AsyncMock(return_value=True)):
            response = authenticated_client.post(
                "/admin/settings/test",
                json={"provider": "unknown_provider", "api_key": "sk-test123"},
            )

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is False


# ---------------------------------------------------------------------------
# Health Check Test
# ---------------------------------------------------------------------------

def test_health_endpoint():
    """GET /health should return 200 with status=ok."""
    with (
        patch("app.database.session.init_db", new=AsyncMock()),
        patch("app.bot.handlers.setup_bot", new=AsyncMock(return_value=MagicMock())),
        patch("app.config.settings.TELEGRAM_BOT_TOKEN", "fake_token"),
    ):
        from app.main import app
        client = TestClient(app, raise_server_exceptions=False)
        response = client.get("/health")

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert "version" in data
