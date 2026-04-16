# Telegram Inline AI Bot (@FarjadInlineBot)

A production-ready Telegram Inline Bot powered by FastAPI, Python 3.11, OpenAI GPT, and Flux (Replicate / fal.ai). This seamless bot allows users to trigger chat completions or generate AI images directly through inline queries across any chat.

It features a stunning, premium dark-themed Admin Panel where administrators can view analytics, monitor request history, manage API keys dynamically, and control user access (rate limiting, blocking) without restarting the server.

---

## 🎯 Quick Start

Please check [HOWTOUSE.md](HOWTOUSE.md) to learn how to configure, run, and interact with the bot in both development and production environments.

## 🌟 Highlights

- **Inline Query Support**: Use the bot anywhere simply by typing `@FarjadInlineBot <your query>`.
- **Smart Intent Detection**: Automatically detects english and persian keywords (e.g. "draw", "بکش", "تصویر") and routes them to Image Generation or Text Chat.
- **Dynamic Configuration**: Change API keys, modes, and rate limits in the Admin Panel without touching `.env`.
- **Built-in Analytics**: Interactive charts powered by Chart.js (Daily Usage, Cost, Top Users).
- **Graceful Error Handling**: Fallbacks for API limits, timeout handling, and user feedback inline.

---

## 📁 Project Structure

\`\`\`text
farjad-inline-bot/
├── docker-compose.yml     # Fast deployment setup with Postgres + Redis
├── requirements.txt       # Project dependencies
├── app/
│   ├── main.py            # FastAPI entry point
│   ├── bot/               # Telegram bot handlers & inline routing
│   ├── ai/                # OpenAI & Flux Integration
│   ├── admin/             # Dark-themed Dashboard & API Config
│   ├── database/          # SQLAlchemy async models & CRUD
│   └── services/          # Rate limiter & usage trackers
└── tests/                 # Unit & integration tests
\`\`\`

## 🛡 License & Credits
Developed for a high-quality user experience. Please refer to [CHANGELOG.md](CHANGELOG.md) for version history, and see [FEATURELIST.md](FEATURELIST.md) for a comprehensive look at what's inside.
