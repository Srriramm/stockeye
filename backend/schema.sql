-- ═══════════════════════════════════════════════════════════════
-- StockEye — Supabase PostgreSQL Schema (multi-user)
-- Run this once via:  python setup_db.py
-- OR paste into Supabase → SQL Editor and click Run
-- ═══════════════════════════════════════════════════════════════

-- ─── Portfolio ──────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS holdings (
    id          SERIAL PRIMARY KEY,
    user_id     UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    ticker      TEXT NOT NULL,
    name        TEXT NOT NULL,
    quantity    REAL NOT NULL,
    buy_price   REAL NOT NULL,
    purchase_date TEXT NOT NULL,
    sector      TEXT DEFAULT '',
    exchange    TEXT DEFAULT 'NSE',
    created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS monitored_stocks (
    id              SERIAL PRIMARY KEY,
    user_id         UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    ticker          TEXT NOT NULL,
    name            TEXT DEFAULT '',
    is_active       BOOLEAN DEFAULT TRUE,
    price_baseline  REAL DEFAULT 0,
    volume_avg_30d  REAL DEFAULT 0,
    created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(user_id, ticker)
);

CREATE TABLE IF NOT EXISTS alerts (
    id          SERIAL PRIMARY KEY,
    user_id     UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    ticker      TEXT NOT NULL,
    alert_type  TEXT NOT NULL,
    message     TEXT NOT NULL,
    severity    TEXT NOT NULL DEFAULT 'info',
    is_read     BOOLEAN DEFAULT FALSE,
    data        TEXT DEFAULT '{}',
    created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS price_alerts (
    id           SERIAL PRIMARY KEY,
    user_id      UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    ticker       TEXT NOT NULL,
    target_price REAL NOT NULL,
    direction    TEXT NOT NULL DEFAULT 'above',
    is_active    BOOLEAN DEFAULT TRUE,
    triggered    BOOLEAN DEFAULT FALSE,
    created_at   TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS portfolio_snapshots (
    id               SERIAL PRIMARY KEY,
    user_id          UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    total_value      REAL NOT NULL,
    total_investment REAL NOT NULL,
    pnl              REAL NOT NULL,
    pnl_percent      REAL NOT NULL,
    snapshot_date    TEXT NOT NULL,
    created_at       TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(user_id, snapshot_date)
);

-- ─── Watchlists ──────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS watchlists (
    id          SERIAL PRIMARY KEY,
    user_id     UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    name        TEXT NOT NULL,
    description TEXT,
    color       TEXT DEFAULT '#3b82f6',
    position    INTEGER DEFAULT 0,
    created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS watchlist_items (
    id           SERIAL PRIMARY KEY,
    user_id      UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    watchlist_id INTEGER NOT NULL REFERENCES watchlists(id) ON DELETE CASCADE,
    ticker       TEXT NOT NULL,
    name         TEXT,
    sector       TEXT,
    position     INTEGER DEFAULT 0,
    added_at     TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(watchlist_id, ticker)
);

-- ─── Advanced Alerts ─────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS advanced_alerts (
    id              SERIAL PRIMARY KEY,
    user_id         UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    ticker          TEXT NOT NULL,
    alert_type      TEXT NOT NULL,
    condition       TEXT NOT NULL,
    threshold_value REAL,
    current_value   REAL,
    is_active       INTEGER DEFAULT 1,
    triggered       INTEGER DEFAULT 0,
    triggered_at    TIMESTAMP,
    created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    notes           TEXT
);

-- ─── Paper Trading ───────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS orders (
    id                SERIAL PRIMARY KEY,
    user_id           UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    ticker            TEXT NOT NULL,
    name              TEXT,
    side              TEXT NOT NULL,
    order_type        TEXT NOT NULL,
    quantity          REAL NOT NULL,
    price             REAL,
    stop_price        REAL,
    limit_price       REAL,
    status            TEXT DEFAULT 'PENDING',
    executed_price    REAL,
    executed_quantity REAL,
    executed_at       TIMESTAMP,
    brokerage         REAL DEFAULT 0,
    taxes             REAL DEFAULT 0,
    total_cost        REAL,
    created_at        TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at        TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    notes             TEXT
);

CREATE TABLE IF NOT EXISTS trades (
    id           SERIAL PRIMARY KEY,
    user_id      UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    order_id     INTEGER REFERENCES orders(id),
    ticker       TEXT NOT NULL,
    side         TEXT NOT NULL,
    quantity     REAL NOT NULL,
    price        REAL NOT NULL,
    brokerage    REAL DEFAULT 0,
    taxes        REAL DEFAULT 0,
    total_amount REAL NOT NULL,
    executed_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS trading_portfolio (
    id               SERIAL PRIMARY KEY,
    user_id          UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    ticker           TEXT NOT NULL,
    name             TEXT,
    quantity         REAL NOT NULL,
    avg_buy_price    REAL NOT NULL,
    total_investment REAL NOT NULL,
    sector           TEXT,
    updated_at       TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(user_id, ticker)
);

CREATE TABLE IF NOT EXISTS trading_balance (
    id         SERIAL PRIMARY KEY,
    user_id    UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE UNIQUE,
    balance    REAL DEFAULT 100000.0,
    invested   REAL DEFAULT 0,
    pnl        REAL DEFAULT 0,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS trading_daily_snapshots (
    id              SERIAL PRIMARY KEY,
    user_id         UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    date            TEXT NOT NULL,
    portfolio_value REAL,
    cash_balance    REAL,
    invested        REAL,
    pnl             REAL,
    pnl_pct         REAL,
    created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(user_id, date)
);
ALTER TABLE trading_daily_snapshots ENABLE ROW LEVEL SECURITY;
CREATE INDEX IF NOT EXISTS idx_trading_snapshots_user
    ON trading_daily_snapshots(user_id, date DESC);

-- ─── Conversations ───────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS conversations (
    id         SERIAL PRIMARY KEY,
    user_id    UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    title      TEXT DEFAULT 'New Chat',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS conversation_messages (
    id              SERIAL PRIMARY KEY,
    user_id         UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    conversation_id INTEGER NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
    role            TEXT NOT NULL,  -- 'user' | 'assistant'
    content         TEXT NOT NULL,
    created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- ═══════════════════════════════════════════════════════════════
-- Row Level Security (RLS) — users see only their own data
-- ═══════════════════════════════════════════════════════════════

ALTER TABLE holdings            ENABLE ROW LEVEL SECURITY;
ALTER TABLE monitored_stocks    ENABLE ROW LEVEL SECURITY;
ALTER TABLE alerts              ENABLE ROW LEVEL SECURITY;
ALTER TABLE price_alerts        ENABLE ROW LEVEL SECURITY;
ALTER TABLE portfolio_snapshots ENABLE ROW LEVEL SECURITY;
ALTER TABLE watchlists          ENABLE ROW LEVEL SECURITY;
ALTER TABLE watchlist_items     ENABLE ROW LEVEL SECURITY;
ALTER TABLE advanced_alerts     ENABLE ROW LEVEL SECURITY;
ALTER TABLE orders              ENABLE ROW LEVEL SECURITY;
ALTER TABLE trades              ENABLE ROW LEVEL SECURITY;
ALTER TABLE trading_portfolio          ENABLE ROW LEVEL SECURITY;
ALTER TABLE trading_balance            ENABLE ROW LEVEL SECURITY;
ALTER TABLE trading_daily_snapshots    ENABLE ROW LEVEL SECURITY;
ALTER TABLE conversations       ENABLE ROW LEVEL SECURITY;
ALTER TABLE conversation_messages ENABLE ROW LEVEL SECURITY;

-- Policies: authenticated users can only CRUD their own rows
DO $$ DECLARE
    t TEXT;
BEGIN
    FOREACH t IN ARRAY ARRAY[
        'holdings','monitored_stocks','alerts','price_alerts',
        'portfolio_snapshots','watchlists','watchlist_items',
        'advanced_alerts','orders','trades','trading_portfolio',
        'trading_balance','trading_daily_snapshots','conversations','conversation_messages'
    ] LOOP
        EXECUTE format('DROP POLICY IF EXISTS own_rows ON %I', t);
        EXECUTE format('
            CREATE POLICY own_rows ON %I
            FOR ALL
            USING (user_id = auth.uid())
            WITH CHECK (user_id = auth.uid());
        ', t);
    END LOOP;
END $$;

-- Indexes for fast user-scoped queries
CREATE INDEX IF NOT EXISTS idx_holdings_user         ON holdings(user_id);
CREATE INDEX IF NOT EXISTS idx_watchlists_user       ON watchlists(user_id);
CREATE INDEX IF NOT EXISTS idx_orders_user           ON orders(user_id);
CREATE INDEX IF NOT EXISTS idx_conversations_user    ON conversations(user_id);
CREATE INDEX IF NOT EXISTS idx_messages_conversation ON conversation_messages(conversation_id);

-- Additional indexes for monitoring, alert cooldowns, and trading performance
CREATE INDEX IF NOT EXISTS idx_alerts_user_created  ON alerts(user_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_alerts_ticker_type   ON alerts(ticker, alert_type, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_monitored_active     ON monitored_stocks(is_active, user_id);
CREATE INDEX IF NOT EXISTS idx_orders_status        ON orders(user_id, status, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_messages_conv        ON conversation_messages(conversation_id, created_at ASC);
CREATE INDEX IF NOT EXISTS idx_price_alerts_active  ON price_alerts(is_active, triggered);

-- ─── Audit Log ────────────────────────────────────────────────
-- Records every significant mutation for compliance and debugging.
-- user_id SET NULL on user deletion to preserve audit history.
CREATE TABLE IF NOT EXISTS audit_log (
    id          SERIAL PRIMARY KEY,
    user_id     UUID REFERENCES auth.users(id) ON DELETE SET NULL,
    event_type  TEXT NOT NULL,
    entity_type TEXT,
    entity_id   INTEGER,
    ip_address  TEXT,
    user_agent  TEXT,
    request_id  TEXT,
    details     JSONB DEFAULT '{}',
    created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_audit_user    ON audit_log(user_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_audit_event   ON audit_log(event_type, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_audit_created ON audit_log(created_at DESC);

-- ─── User Management (Beta Access Control) ────────────────────
-- Stores every user who has signed in, with their role and access status.
-- Backend reads/writes this via service connection (not RLS-filtered).
CREATE TABLE IF NOT EXISTS app_users (
    id           SERIAL PRIMARY KEY,
    user_id      UUID UNIQUE NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    email        TEXT NOT NULL,
    full_name    TEXT,
    avatar_url   TEXT,
    role         TEXT NOT NULL DEFAULT 'user',      -- 'user' | 'admin'
    status       TEXT NOT NULL DEFAULT 'rejected',  -- 'approved' | 'rejected' | 'suspended'
    notes        TEXT,
    approved_by  UUID REFERENCES auth.users(id) ON DELETE SET NULL,
    approved_at  TIMESTAMP,
    last_seen_at TIMESTAMP,
    created_at   TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_app_users_user_id ON app_users(user_id);
CREATE INDEX IF NOT EXISTS idx_app_users_email   ON app_users(email);
CREATE INDEX IF NOT EXISTS idx_app_users_status  ON app_users(status);

-- Pre-approved email whitelist for invite-only beta.
-- Adding an email here auto-approves any existing user with that email.
CREATE TABLE IF NOT EXISTS invited_emails (
    id         SERIAL PRIMARY KEY,
    email      TEXT UNIQUE NOT NULL,
    added_by   UUID REFERENCES auth.users(id) ON DELETE SET NULL,
    notes      TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- ─── Proactive Agent Recommendations ─────────────────────────────────────────
-- Stores autonomous BUY/SELL/HOLD/WATCH recommendations generated by the
-- Claude tool_use agentic loop (proactive_agent.py).
-- Populated by Celery Beat at 9:00 AM and 4:00 PM IST, or on-demand.
CREATE TABLE IF NOT EXISTS agent_recommendations (
    id           SERIAL PRIMARY KEY,
    user_id      UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    ticker       TEXT NOT NULL,
    action       TEXT NOT NULL,              -- 'BUY' | 'SELL' | 'HOLD' | 'WATCH'
    confidence   REAL NOT NULL DEFAULT 0,    -- 0.0 – 1.0
    reasoning    TEXT NOT NULL DEFAULT '',   -- 2-3 sentence explanation
    entry_price  REAL,                       -- suggested entry (BUY) or exit (SELL)
    target_price REAL,                       -- 12-month price target
    stop_loss    REAL,                       -- stop-loss level
    risk_reward  REAL,                       -- (target-entry)/(entry-stop_loss)
    timeframe    TEXT DEFAULT 'short',       -- 'short' | 'medium' | 'long'
    key_factors  TEXT DEFAULT '[]',          -- JSON array of factor strings
    model_used   TEXT,                       -- 'claude-haiku-...' | 'claude-sonnet-...'
    data_sources TEXT DEFAULT '[]',          -- JSON array of tool names called
    session      TEXT,                       -- 'morning' | 'evening' | 'manual'
    is_read      BOOLEAN DEFAULT FALSE,
    is_dismissed BOOLEAN DEFAULT FALSE,
    created_at   TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
ALTER TABLE agent_recommendations ENABLE ROW LEVEL SECURITY;
CREATE POLICY own_agent_recs ON agent_recommendations
    FOR ALL
    USING (user_id = auth.uid())
    WITH CHECK (user_id = auth.uid());
CREATE INDEX IF NOT EXISTS idx_agent_recs_user
    ON agent_recommendations(user_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_agent_recs_unread
    ON agent_recommendations(user_id, is_read, is_dismissed);
