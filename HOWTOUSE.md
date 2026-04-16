# How To Use

This guide walks you through configuring, running, and managing the AI bot infrastructure.

---

## 1. Environment Configuration

You must create a `.env` file from the supplied `.env.example`.

\`\`\`bash
cp .env.example .env
\`\`\`

Fill in your secrets:
- `TELEGRAM_BOT_TOKEN="1231321321a3sd21a3sd1a3sd1a3sd1a32sd1a32d1a3s2s1d3as1d3"`
- `OPENAI_API_KEY="sk-..."` 
- `FAL_API_KEY="..."` or `REPLICATE_API_TOKEN="..."`
- Update `ADMIN_USERNAME` and `ADMIN_PASSWORD` for the web dashboard.

---

## 2. Running Locally (Development)

The system automatically detects if no PostgreSQL is provided and will fallback to a lightweight `sqlite+aiosqlite:///./data.db` local deployment to let you develop quickly.

1. **Install Python virtual environment:**
   \`\`\`bash
   python3.11 -m venv venv
   source venv/bin/activate
   pip install -r requirements.txt
   \`\`\`

2. **Run Migrations (Initializes the Database schema):**
   \`\`\`bash
   alembic upgrade head
   \`\`\`

3. **Start the API Server:**
   \`\`\`bash
   uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
   \`\`\`

You can access the backend now at `http://localhost:8000/admin`. Since no webhooks are setup, the code automatically falls back to **polling mode** to read bot messages.

---

## 3. Running via Docker (Production)

To scale, the project is structured with a multi-container Docker implementation relying on PostgreSQL for persistent database tracking and Redis for precise background rate-limiting.

1. Configure your `.env` completely including `DATABASE_URL=postgresql+asyncpg://user:pass@postgres:5432/bot`.
2. Ensure you have Docker and Docker Compose installed.

\`\`\`bash
docker-compose up -d --build
\`\`\`

The bot will automatically apply database migrations inside the container before starting.

**Note on Webhooks (Production):**
If you wish to switch to webhook mode (a huge performance leap vs polling):
1. In the Web Admin Panel, go to `Settings`.
2. Change the Bot mode to `Webhook`.
3. Fill your domain (e.g. `https://my-webhook.com`). The bot will automatically alert Telegram.

---

## 4. Bot Interaction

Open Telegram and jump into any chat (even saved messages).
Call your bot inline using its name:
\`\`\`text
@FarjadInlineBot Write a funny tweet about AI programmers
\`\`\`

Wait a second and it will give you the text you can attach to your chat.
To test Flux Images, trigger intent with an image keyword:
\`\`\`text
@FarjadInlineBot draw a futuristic cyberpunk city
\`\`\`
**(Or use Persian prompts)**
\`\`\`text
@FarjadInlineBot تصویر یک گربه روی کره ماه
\`\`\`

---

## 5. Web Navigation
Visit `http://localhost:8000/admin` (or your domain/admin). Log in.
From the settings, you can edit system prompts, modify Flux sizes, and check API capabilities natively.
