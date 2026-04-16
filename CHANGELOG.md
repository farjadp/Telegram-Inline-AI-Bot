# Changelog

All notable changes to this project will be documented in this file.

## [1.0.0] - initial release

### Added
- **Core Orchestration**: `docker-compose.yml` & `Dockerfile` integrated for multi-container spinups (App, Postgres, Redis).
- **FastAPI Core (`/app/main.py`)**: Built-in App factory pattern handling DB initialization and Telegram Bot start sequences. Async lifecycle events integrated for clean start/shutdown.
- **SQLAlchemy Async Persistence (`/app/database/`)**: Complete DB structure mapped for users, requests history, settings overriding, and admin sessions. Migrations handled strictly via `Alembic`.
- **Bot Layer (`/app/bot/`)**: `inline.py` acts as central router tracking rate limits mapping keyword queries towards `app.ai`. Added Intent detection algorithm evaluating keyword boundaries via Regex.
- **AI Integrations (`/app/ai/`)**: Async clients written for `OpenAI API (gpt models)` and `Flux API (Replicate / fal.ai)`. Mathematical costing built straight into the core processing.
- **Service Utilities (`/app/services/`)**: Full sliding window algorithm for exact rate-limiting built on Redis avoiding memory-leaks.
- **Server Side Rendered Admin Panel (`/app/admin/`)**: Complete Dark Mode UI / UX. Securely authenticates admins using `itsdangerous` sessions and `passlib/bcrypt` password checking. 
- **Analytics View**: Visual interfaces for all traffic usage utilizing DataFrames and Chart.js.
- **Testing**: Added Pytest configuration containing full mathematical integrity evaluations of costs algorithms and intents testing matching algorithms.

### Changed
- Refactored away from older Python Threading constraints to full concurrency via `asyncio`.
- Dynamically routing settings through the DB. This prevents mandatory application restarts.

### Security
- Admin Panel routes locked behind hard authentication dependencies.
- Passwords are strictly hashed avoiding plain-texts.
- Sensitive environment API variables are conditionally masked across frontend rendering.
