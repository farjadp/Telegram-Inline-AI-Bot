# Feature List

This document highlights the comprehensive suite of features integrated into the Telegram Inline AI Bot.

## 🤖 Bot & Telegram Integration
- **Inline Queries**: Respond directly in any chat (requires typing `@FarjadInlineBot`).
- **Multilingual Intent Router**: Accurately recognizes natural language intent (English & Persian) to route the prompt to the correct AI engine.
- **Support for Both Polling & Webhook**: Designed to handle localhost (polling) and Production (HTTPS webhooks).

## 🧠 AI Capabilities
- **OpenAI Text Generation**: Streams responses from GPT models (e.g. `gpt-4o-mini`). Includes token tracking and cost calculation.
- **Flux Image Generation**: Harnesses state-of-the-art models for images. Supports switching dynamically between `Replicate` and `fal.ai` via Admin Dashboard.
- **Rich Media**: Outputs high-quality WebP/JPEG images natively supported by Telegram's inline photo viewer.

## 🛡 Security & Concurrency
- **Sliding-Window Rate Limiting**: Built on Redis for extreme scalability with in-memory fallbacks.
- **Anti-Spam & Blocking**: Administrators can indefinitely block misbehaving users directly from the UI.
- **Custom Rate Limits**: Adjust max requests per minute on a per-user basis independently of global settings.

## 📊 Administration Panel (Dashboard)
- **Glassmorphism Design**: State-of-the-art Dark UI with deep space aesthetics. Fully responsive on Mobile.
- **Dynamic Settings (No Restart)**: Adjust API keys (OpenAI, fal, Telegram) instantly via HTTP cache overriding DB.
- **AJAX API Testing**: Button to click and test validity of API tokens securely from the frontend.
- **Session Auth**: BCrypt encrypted passwords matching and JWT-inspired token HTTP-only cookies.
- **Advanced Request History**: Table showing tokens used, cost generated, time logic, with an inline modal for viewing the exact prompt and generated image.
- **Export to CSV**: Download complete data analytics as a `.csv` file.
- **Real-Time Analytics**: Chart.js charts displaying token usage over the last X days, Cost estimations, and Request Mix (Text vs Image).

## 🏗 Architecture
- **FastAPI**: Non-blocking asynchronous python engine.
- **SQLAlchemy (Async)**: Modern ORM connecting to PostgreSQL.
- **Alembic**: Zero-downtime database migrations.
- **Jinja2**: Server side rendering avoiding bulky JS frameworks.
- **Docker Ready**: Built-in script for quick spinning everything up using Docker Compose.
