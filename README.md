# StockEye

An AI-powered stock market assistant for Indian markets (NSE/BSE). Real-time price monitoring, autonomous paper trading, proactive analysis, multi-model AI advisor, and full Telegram control — all in one platform.

---

## Features

### AI Advisor
- Dual-provider AI (OpenAI GPT-4 + Anthropic Claude) with automatic fallback
- Per-user conversation history stored in DB
- Context-aware: reads the shared intelligence bus before every response, so it knows what the monitor and proactive agent have already flagged

### Autonomous Paper Trading
- Claude-powered agentic trader (Haiku model for speed) that scans opportunities, analyses them, sizes positions, and executes trades — fully hands-free
- Strategies: ETF NAV arbitrage, pairs mean-reversion, Bollinger extremes
- **Exit rules**: partial exit at 4% gain, hard stop-loss at 5% loss, news-sentiment exit, ETF arb exit when spread closes, pairs exit when z-score reverts
- **Self-tuning**: computes win rate of last 10 trades; tightens R:R thresholds automatically when win rate drops below 40%
- **Budget-aware sizing**: when a budget is set, splits it evenly across up to 3 position slots (capital-first sizing, not risk-formula)
- **No-rebuy guard**: won't buy a ticker already held
- **Concurrency lock**: Redis-backed per-user session lock prevents duplicate sessions from Telegram + Celery firing at the same time (auto-expires after 15 min if the session crashes)
- Scheduled auto-sessions via Celery Beat: **9:15 AM IST** (market open) and **3:30 PM IST** (pre-close) for all funded users, using 60% of available balance as budget
- Live P&L per holding in portfolio state (fetches real-time prices before every decision)

### Proactive Analysis Agent
- Background agent that analyses watchlist stocks and generates BUY/SELL/HOLD recommendations
- Reads shared intelligence context before reasoning, so it factors in active monitor alerts and recent trades
- Writes its recommendations back to the shared bus for all other modules to see

### Market Monitor
- Real-time price and volume monitoring with configurable alerts
- Per-user cooldowns to prevent alert spam
- All alerts published to the shared intelligence bus (with `user_id`) so the AI advisor and trader are aware of price events

### Shared Intelligence Bus
- `shared_signals` DB table acts as a cross-module context layer
- Every module (Monitor, Proactive Agent, AI Advisor, Autonomous Trader) **writes** when it generates intelligence and **reads** before it reasons
- Per-user isolation — User A never sees User B's signals
- TTL on all signals (default 24 h) so stale data doesn't pollute sessions
- Injected as a formatted block into every AI prompt: AI modules literally debate from the same data

### Telegram Bot (Admin)
Single-user bot locked to a configured `TELEGRAM_CHAT_ID`. Full application control from your phone:

| Command | Description |
|---|---|
| `/portfolio` | Current holdings with live P&L |
| `/balance` | Cash balance and invested amount |
| `/run [budget]` | Start an autonomous trading session |
| `/buy TICKER QTY` | Place a manual paper buy |
| `/sell TICKER QTY` | Place a manual paper sell |
| `/history` | Last 10 trades |
| `/status` | Active session status |
| `/chat` | Free-form chat with AI Advisor |
| plain text | Automatically routes to AI Advisor |

- Session results (trades, capital deployed, reasoning) are sent back to Telegram automatically
- Scheduled auto-sessions also notify via Telegram when they complete
- If you trigger `/run` while a session is already active (e.g. scheduled session still running), the bot replies immediately: `⏳ A session is already running`

### Stock Screener
- Multi-factor screener across NSE/BSE stocks
- Technical filters: RSI, MACD, Bollinger Bands, volume surge, price momentum

### Portfolio & Watchlists
- Paper trading portfolio with full trade history, daily P&L snapshots, return charts
- Multiple watchlists with ownership verification

### Real-time Prices
- WebSocket-based live price feed via Flask-SocketIO
- Redis-cached prices (30 s TTL) to reduce API calls

### Forecasting
- Prophet + ML-based price forecasting
- Agentic forecaster with confidence intervals

---

## Tech Stack

| Layer | Tech |
|---|---|
| Backend | Flask 3.0, Flask-SocketIO (eventlet), Python 3.11 |
| AI | Anthropic Claude (Haiku / Sonnet), OpenAI GPT-4 |
| Auth | Supabase JWT + Google OAuth, Redis token cache |
| Database | Supabase PostgreSQL (RLS) → SQLiteCloud → SQLite (fallback) |
| Cache | Redis (prices 30 s, technicals 300 s, news 900 s, auth 240 s) |
| Rate limiting | Flask-Limiter backed by Redis |
| Task queue | Celery + Redis (worker + beat scheduler) |
| Notifications | Telegram Bot API (`python-telegram-bot 20.7`) |
| Frontend | React 18, Vite, Supabase auth, socket.io-client |
| Reverse proxy | nginx (SSL/TLS, CSP, HSTS) |
| Deploy | Docker Compose |

---

## Services (Docker Compose)

```
backend      — Flask API on port 5000 (internal)
frontend     — nginx on ports 80/443, reverse-proxies to backend
redis        — Redis 7, 256 MB LRU cache
worker       — Celery worker (concurrency=2, background tasks)
beat         — Celery Beat scheduler (9:15 AM + 3:30 PM IST auto-sessions)
telegram     — Telegram bot (python telegram_bot.py)
mcp-server   — MCP server for Claude Desktop integration (STDIO mode)
```

---

## Setup

### Prerequisites
- Docker + Docker Compose
- Supabase project (PostgreSQL + Auth)
- Anthropic API key
- OpenAI API key
- Telegram bot token (from @BotFather)

### 1. Configure environment

Copy and fill in `backend/.env`:

```env
FLASK_SECRET_KEY=<random 64-char hex>
OPENAI_API_KEY=sk-...
ANTHROPIC_API_KEY=sk-ant-...
NEWS_API_KEY=...
DATABASE_URL=postgresql://...   # Supabase connection string
SUPABASE_URL=https://....supabase.co
SUPABASE_ANON_KEY=eyJ...
SUPABASE_SERVICE_KEY=eyJ...
TELEGRAM_BOT_TOKEN=...          # from @BotFather
TELEGRAM_CHAT_ID=...            # your personal chat ID (from @userinfobot)
TELEGRAM_USER_ID=...            # your Supabase user UUID
ZERODHA_API_KEY=...             # optional, for live broker integration
ZERODHA_API_SECRET=...
```

### 2. Supabase schema

Run the following in the Supabase SQL Editor (in addition to the main `backend/schema.sql`):

```sql
CREATE TABLE IF NOT EXISTS shared_signals (
    id          BIGSERIAL PRIMARY KEY,
    user_id     TEXT NOT NULL,
    source      TEXT NOT NULL,
    signal_type TEXT NOT NULL,
    ticker      TEXT,
    direction   TEXT,
    message     TEXT NOT NULL,
    confidence  REAL,
    created_at  TIMESTAMPTZ DEFAULT NOW(),
    expires_at  TIMESTAMPTZ
);
CREATE INDEX IF NOT EXISTS idx_shared_signals_user_created
    ON shared_signals (user_id, created_at DESC);
```

### 3. Deploy

```bash
docker compose up -d
```

All services start automatically. The beat scheduler registers the 9:15 AM and 3:30 PM IST sessions on first run.

---

## Project Structure

```
stockeye/
├── backend/
│   ├── app.py                  # Flask app, all API routes
│   ├── agentic_trader.py       # Autonomous Claude trading agent
│   ├── proactive_agent.py      # Background proactive analysis
│   ├── market_monitor.py       # Real-time price/volume monitoring
│   ├── ai_advisor.py           # Dual-provider AI chat
│   ├── shared_context.py       # Cross-module intelligence bus
│   ├── telegram_bot.py         # Telegram control bot
│   ├── telegram_notify.py      # Telegram push notifications
│   ├── trading_manager.py      # Paper trading execution
│   ├── tasks.py                # Celery tasks + beat schedule
│   ├── auth_manager.py         # Supabase JWT auth
│   ├── cache.py                # Redis cache helpers
│   ├── conversation_manager.py # Per-user chat history
│   ├── stock_data.py           # Price + technical data fetching
│   ├── stock_screener.py       # Multi-factor screener
│   ├── news_monitor.py         # News + sentiment
│   └── schema.sql              # DB schema
├── frontend/
│   └── src/components/         # React components
├── docker-compose.yml
└── docker-compose.prod.yml
```

---

## Key Design Decisions

- **Shared intelligence bus** — all AI modules read from and write to the same `shared_signals` table. The AI advisor, proactive agent, and autonomous trader all reason from a unified picture of the world rather than isolated data silos.
- **Concurrency safety** — Redis `SET NX EX` locks prevent two sessions from running simultaneously for the same user (e.g. Telegram `/run` colliding with a scheduled session). Falls back to in-memory check if Redis is unavailable.
- **Capital-first position sizing** — when a budget is explicitly provided, the agent divides it evenly across slots and sizes positions by capital rather than the risk formula, ensuring the full budget is deployed.
- **Modular monolith** — clean module boundaries without microservice overhead. Single Docker Compose file, shared Redis, one DB connection pool.
