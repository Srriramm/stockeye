# StockEye — Complete Implementation Plan & Vision

> **Purpose:** This document is the single source of truth for StockEye's product vision, technical architecture, and build roadmap. Reference this in every conversation to maintain continuity. Last updated: 2026-03-28.

---

## The Core Thesis

Indian retail traders (180M+ Demat accounts, 90M+ active on NSE) have world-class execution platforms (Zerodha, Upstox, Groww) but **zero intelligent layer on top**. They trade blind — no institutional-grade analysis, no AI reasoning, no automated discipline.

StockEye fills this gap: an **AI-native paper trading platform** that builds a verifiable track record, then converts trust into a SaaS subscription business.

**Why paper trading first:**
- Zero SEBI regulatory risk (simulation = education tool, no license needed)
- Build 6-12 months of transparent, logged track record
- Proof of performance is the entire sales pitch
- Real trading added later once trust and compliance are established

**The India moat nobody else has:**
Every serious AI trading tool (OpenProphet, claude-trading-skills, Polymarket bots) is US/crypto focused. FII/DII flows, F&O OI, delivery %, promoter pledging, India VIX — nobody is feeding this into AI for retail traders. This is the competitive gap.

---

## Revenue Model

### Subscription Tiers

| Tier | Price | What's Included |
|---|---|---|
| **Free** | ₹0 | 5 AI recommendations/week, manual paper trading, basic watchlist, market indices |
| **Pro** | ₹399/month | Unlimited recommendations, daily autonomous sessions, full signal breakdown, Telegram alerts, performance analytics vs Nifty benchmark, Claude's reasoning chain visible |
| **Premium** | ₹999/month | Everything in Pro + multiple portfolios, event-aware trading, custom risk parameters, weekly AI portfolio review, priority Opus model |
| **Teams/Educator** | ₹2,999/month | 10 sub-accounts, instructor dashboard, for trading educators and YouTube traders |

### Revenue Milestones
- 100 Pro users = ₹39,900/month
- 1,000 Pro users = ₹3,99,000/month
- 10,000 Pro users = ₹39,90,000/month

### Path to Licensing
- Months 1-6: Operate as "AI-powered paper trading simulator and market education tool" (no SEBI license needed)
- Month 6+: Apply for Research Analyst (RA) license backed by 6-month verifiable track record
- Month 12+: Real broker integration (Zerodha Kite API) with full compliance

---

## Complete Technical Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                        DATA LAYER                               │
│   Price + Technical + Fundamental + Sentiment + India-Specific  │
└─────────────────────────┬───────────────────────────────────────┘
                          │
┌─────────────────────────▼───────────────────────────────────────┐
│                      SIGNAL LAYER                               │
│   Specialized scorers — each expert in one domain               │
│   Mix of rule-based (free, fast) + AI (where reasoning helps)   │
└─────────────────────────┬───────────────────────────────────────┘
                          │
┌─────────────────────────▼───────────────────────────────────────┐
│                    DECISION LAYER                               │
│   Claude Haiku → quick scan/filter (cheap)                      │
│   Claude Opus + Extended Thinking → final decision (powerful)   │
└─────────────────────────┬───────────────────────────────────────┘
                          │
┌─────────────────────────▼───────────────────────────────────────┐
│                      RISK LAYER                                 │
│   Hard rules — no AI involvement, no override possible          │
└─────────────────────────┬───────────────────────────────────────┘
                          │
┌─────────────────────────▼───────────────────────────────────────┐
│                   EXECUTION LAYER                               │
│   Paper trade + full reasoning log + outcome tracking           │
└─────────────────────────┬───────────────────────────────────────┘
                          │
┌─────────────────────────▼───────────────────────────────────────┐
│                   FEEDBACK LOOP                                 │
│   Post-trade analysis → adaptive signal weights                 │
└─────────────────────────────────────────────────────────────────┘
```

### Tech Stack (Current + Planned)

| Layer | Current | Target |
|---|---|---|
| Backend | Flask 3.0 + SocketIO | Same — don't over-engineer |
| Database | Supabase PostgreSQL | Same + time-series tables for signals |
| Cache | Redis | Same + signal score caching |
| AI Decision | claude-haiku | claude-haiku (scan) + claude-opus (decision) |
| AI Reasoning | Standard prompt | Extended thinking (budget_tokens: 10000+) |
| Task Queue | Celery (partially) | Full Celery Beat for scheduled signal fetching |
| Frontend | React 18 + Vite | Same + PWA manifest |
| Mobile | None | PWA first, React Native at 5K users |
| Payments | None | Razorpay subscription API |
| Messaging | Telegram | Telegram + WhatsApp Business API |

---

## Data Layer — Complete Signal Stack

### Currently Have
- Price (OHLCV)
- RSI, MACD, Bollinger Bands, SMA 20/50
- News sentiment
- Brain score + ML forecast

### India-Specific Signals to Add (Highest Priority First)

#### Tier 1 — Add Immediately (Week 1-2)
| Signal | Source | Why It Matters |
|---|---|---|
| **FII net flows (daily)** | NSE website / NSDL | Single biggest price mover in Indian markets. FII sold ₹2000cr+ = avoid new longs |
| **DII net flows (daily)** | NSE website | Counter-signal — DII buys when FII sells, shows domestic conviction |
| **Delivery volume %** | NSE Bhavcopy | High delivery (>50%) = conviction buying, not speculation |
| **F&O Put-Call Ratio** | NSE F&O data | PCR < 0.7 = bearish, PCR > 1.3 = bullish sentiment extreme |

#### Tier 2 — Add Month 2
| Signal | Source | Why It Matters |
|---|---|---|
| **F&O Open Interest buildup** | NSE F&O | OI increasing + price rising = strong trend confirmation |
| **India VIX** | NSE | VIX > 20 = high fear, avoid new positions. VIX > 25 = hard block on all buys |
| **Promoter pledging %** | BSE disclosures | High pledging = forced selling risk. Red flag for any position |
| **Bulk/block deal detection** | NSE bulk deals | Institutional buy/sell signal — often precedes large moves |
| **SGX Nifty futures** | SGX | Pre-market gap indicator — predicts opening direction |
| **Sector-wise FII flow** | SEBI | FII buying IT? All IT stocks get tailwind. Sector rotation intelligence |

#### Tier 3 — Add Month 3
| Signal | Source | Why It Matters |
|---|---|---|
| **Earnings calendar** | NSE corporate actions | Never enter 2 days before results — volatility crush risk |
| **Dividend/bonus/split calendar** | NSE | Corporate actions distort price signals |
| **RBI policy dates** | RBI website | Rate-sensitive sectors (banks, realty, NBFCs) — avoid entry week before |
| **F&O expiry cycle position** | Calendar | Week of expiry = rollover pressure, specific price behavior |
| **Global cues** | Yahoo Finance | Dow futures, crude oil, dollar index, Asia markets |
| **Short interest / F&O short covering** | NSE | Heavy short position + positive catalyst = explosive upside |

### Signal Accuracy Improvements

**Cross-validation requirement:**
Never trade on one signal alone. Require minimum 3 out of 5 signal categories to align:
```
1. Technical signals (RSI, MACD, Bollinger)
2. Volume/delivery signals
3. FII/DII flow signals
4. F&O sentiment signals (PCR, OI)
5. News/sentiment signals
```

**Signal staleness check:**
Each signal has a TTL. If data is older than TTL, mark as stale and reduce its weight:
```
Price data:         TTL 5 minutes
FII/DII flows:      TTL 24 hours (daily data)
Delivery %:         TTL 24 hours
News sentiment:     TTL 4 hours
Promoter pledging:  TTL 7 days
```

**Correlation filter:**
Never hold two stocks with >0.85 correlation simultaneously. If INFY and TCS are highly correlated and you hold INFY, don't buy TCS. Concentration risk.

**Time-of-day filter:**
Avoid entries in first 15 minutes (9:15-9:30 AM) and last 15 minutes (3:15-3:30 PM) of trading session. These windows have high volatility and institutional manipulation. Best entry window: 10:00 AM - 2:30 PM.

**Liquidity filter:**
Never trade stocks with average daily volume < ₹5 crore. Low liquidity = wide spreads, difficult to exit, manipulated price signals.

**Anti-pattern detection:**
Even if technical signals are bullish, block entry if:
- Stock has negative regulatory news (SEBI action, promoter fraud) in last 7 days
- Stock hit upper/lower circuit in last 3 days
- F&O ban period active (stock in ban = no new F&O positions = restricted activity)

---

## Signal Layer — Scoring Architecture

```python
# Each signal returns a score 0-100 and a confidence 0-1
signals = {
    "technical": {
        "score": technical_scorer(price_data),      # Rule-based
        "weight": 0.20,
        "confidence": 0.9  # Always available
    },
    "volume_delivery": {
        "score": delivery_scorer(delivery_data),    # Rule-based
        "weight": 0.15,
        "confidence": 0.9
    },
    "fii_dii": {
        "score": fii_scorer(fii_data),              # Rule-based
        "weight": 0.25,                              # Highest weight
        "confidence": 0.8  # Daily data, slightly stale
    },
    "fno_sentiment": {
        "score": fno_scorer(pcr, oi_data),          # Rule-based
        "weight": 0.20,
        "confidence": 0.85
    },
    "news_sentiment": {
        "score": haiku_scorer(news),                # AI (cheap)
        "weight": 0.20,
        "confidence": varies
    }
}

# Composite score
composite = sum(s["score"] * s["weight"] * s["confidence"] for s in signals.values())
# Normalize for missing signals
```

**Adaptive weights:** After every 50 trades, analyze which signals had highest predictive accuracy and increase their weights. Over time the system learns what works for Indian markets.

---

## Decision Layer — Claude Architecture

### Two-Tier AI Approach

**Tier 1 — Claude Haiku (Scan)**
- Runs on all watchlist stocks every session
- Quick go/no-go based on composite signal score
- Cheap — runs on many stocks
- Output: SCAN_PASS or SCAN_FAIL

**Tier 2 — Claude Opus + Extended Thinking (Decide)**
- Runs only on SCAN_PASS stocks
- Full reasoning with extended thinking (budget: 10,000-16,000 tokens)
- Expensive — runs on few stocks (typically 1-3 per session)
- Output: BUY/SELL/HOLD/WATCH with full reasoning chain

```python
# Opus extended thinking prompt structure
prompt = f"""
You are a disciplined Indian equity trader managing a paper portfolio.

=== MARKET CONTEXT ===
Date: {date} | Session: {session}
Market regime: {regime}  # BULL / BEAR / SIDEWAYS / VOLATILE
India VIX: {vix} | Trend: {vix_trend}
FII today: ₹{fii_flow}cr {fii_direction}
DII today: ₹{dii_flow}cr {dii_direction}

=== STOCK: {ticker} ===
Signal scores: {signal_breakdown}
Composite score: {composite_score}/100
Technical: {technical_summary}
News: {news_summary}
F&O: PCR {pcr}, OI {oi_change}
Delivery %: {delivery_pct}%

=== PORTFOLIO STATE ===
Total value: ₹{total_value}
Cash available: ₹{cash}
Portfolio heat: {heat}%
Current positions: {positions}
Open P&L: ₹{open_pnl} ({open_pnl_pct}%)

=== UPCOMING EVENTS ===
{events_next_7_days}

=== ABSOLUTE RULES (CANNOT BE OVERRIDDEN) ===
- Risk max 1.5% of portfolio per trade
- Max 20% of portfolio in any single stock
- No entry within 2 days of earnings
- No new longs if India VIX > 25
- No new longs if FII sold > ₹2000cr today
- No trades in first/last 15 minutes of session
- If 3+ consecutive losses this week: HOLD only

=== TASK ===
Reason through this opportunity. Consider:
1. Are signals genuinely aligned or conflicting?
2. What is the macro context telling you?
3. What could go wrong? What's the asymmetric risk?
4. Is this the RIGHT time, or just an okay time?

Make your decision. If BUY: provide exact quantity using ATR position sizing.
If not confident 70%+: output WATCH or HOLD.
"""
```

**Why extended thinking matters here:**
The reasoning chain is logged permanently. After 6 months you have 400+ documented AI decisions with outcomes. This is:
1. Your trust story — show users how the AI thinks
2. Your training data — fine-tune on what worked
3. Your marketing — post reasoning chain snippets on social media

---

## Risk Layer — Hard Rules

```python
class RiskGate:
    """Zero AI involvement. Pure rules. All must pass."""

    def check_all(self, decision, portfolio, market_data) -> tuple[bool, list[str]]:
        failures = []

        # Position sizing
        if decision.quantity * decision.entry_price > portfolio.value * 0.20:
            failures.append("Position exceeds 20% of portfolio")

        # Portfolio heat
        if portfolio.heat + (decision.position_value / portfolio.value) > 0.60:
            failures.append("Portfolio heat would exceed 60%")

        # Max positions
        if len(portfolio.open_positions) >= 5:
            failures.append("Max 5 open positions reached")

        # Daily loss
        if portfolio.today_pnl_pct < -0.05:
            failures.append("Daily loss limit -5% hit. No new trades today.")

        # Drawdown
        if portfolio.drawdown_from_peak > 0.15:
            failures.append("Strategy paused: drawdown > 15%")

        # Earnings blackout
        if market_data.days_to_earnings(decision.ticker) <= 2:
            failures.append("Earnings blackout: < 2 days to results")

        # VIX limit
        if market_data.india_vix > 25:
            failures.append("India VIX > 25: no new long positions")

        # FII selling
        if market_data.fii_net_today < -2000:  # crores
            failures.append("FII heavy selling day: no new longs")

        # Consecutive losses
        if portfolio.consecutive_losses >= 3:
            failures.append("3 consecutive losses: HOLD mode only")

        # Correlation
        for held in portfolio.open_positions:
            if market_data.correlation(decision.ticker, held.ticker) > 0.85:
                failures.append(f"High correlation with existing {held.ticker} position")

        # Liquidity
        if market_data.avg_daily_volume_cr(decision.ticker) < 5:
            failures.append("Insufficient liquidity: avg volume < ₹5cr")

        # Time of day
        if not (time(10, 0) <= current_time() <= time(14, 30)):
            failures.append("Outside optimal trading window (10AM-2:30PM)")

        return len(failures) == 0, failures

    def calculate_position_size(self, ticker, portfolio_value, entry_price, stop_loss) -> int:
        """ATR-based position sizing."""
        risk_amount = portfolio_value * 0.015  # 1.5% risk
        risk_per_share = abs(entry_price - stop_loss)
        if risk_per_share == 0:
            return 0
        raw_qty = risk_amount / risk_per_share
        # Cap at 20% portfolio
        max_by_capital = (portfolio_value * 0.20) / entry_price
        return int(min(raw_qty, max_by_capital))
```

---

## Execution Layer — What Gets Logged Per Trade

Every trade logs permanently and immutably:

```json
{
  "trade_id": "uuid",
  "timestamp": "ISO8601",
  "ticker": "TCS",
  "action": "BUY",
  "quantity": 3,
  "entry_price": 2394.90,
  "stop_loss": 2320.00,
  "target_price": 2600.00,
  "risk_amount": 225.00,
  "position_size_pct": 1.5,

  "signal_scores": {
    "technical": 72,
    "volume_delivery": 65,
    "fii_dii": 80,
    "fno_sentiment": 70,
    "news_sentiment": 85,
    "composite": 74.4
  },

  "market_context": {
    "india_vix": 14.2,
    "fii_flow_today": 1240,
    "nifty_trend": "BULLISH",
    "regime": "BULL"
  },

  "ai_model": "claude-opus-4-6",
  "ai_thinking_chain": "full extended thinking text...",
  "ai_confidence": 0.82,
  "risk_gate_passed": true,

  "outcome": {
    "exit_price": null,
    "exit_date": null,
    "pnl": null,
    "exit_reason": null,
    "signals_correct": null
  }
}
```

When trade closes, outcome is filled in. Over time this becomes a dataset for fine-tuning and strategy improvement.

---

## Feedback Loop — How the System Gets Smarter

**Post-trade analysis (runs after every trade closes):**

```
For each closed trade:
1. Which signals were correct?
   - FII signal said BUY, trade was profitable → FII signal +1 accuracy
   - News signal said BUY, trade was loss → News signal -1 accuracy
2. What was the market regime when it worked/failed?
3. What was the hold duration vs target?

Every 50 trades:
4. Recalculate signal accuracy scores
5. Adjust signal weights (more weight to accurate signals)
6. Identify patterns: "Strategy fails in high VIX regime" → add to rules
```

**Monthly strategy review (automated report):**
```
Win rate: 64%
Avg winner: +3.2%
Avg loser: -1.4%
Profit factor: 2.1 (sum of wins / sum of losses)
Best signal: FII/DII (82% accuracy)
Worst signal: News sentiment (54% accuracy)
Best market regime: BULL (74% win rate)
Worst regime: VOLATILE (41% win rate)
Recommendation: Reduce news sentiment weight, add VIX filter for volatile regime
```

---

## Backtesting Engine

**Critical for the sales pitch.** Run the strategy on 2 years of NSE data.

```
Data needed:
├── 2 years daily OHLCV for all watchlist stocks (NSE Bhavcopy, free)
├── 2 years FII/DII daily flows (NSE, free)
├── 2 years F&O PCR data (NSE, free)
├── 2 years India VIX (NSE, free)
└── Earnings dates (NSE corporate calendar, free)

Backtest approach:
├── Replay signal logic day by day (no lookahead bias)
├── Apply identical risk rules as live trading
├── Simulate realistic execution: entry at next-day open price
├── Account for: no trades on holidays, earnings blackouts
└── Output: equity curve, Sharpe ratio, max drawdown, win rate, CAGR

Target output metrics:
├── CAGR vs Nifty50 benchmark
├── Sharpe ratio (>1.5 is good, >2.0 is excellent)
├── Max drawdown (target: < 15%)
├── Win rate (target: > 60%)
└── Profit factor (target: > 1.8)
```

This output becomes the homepage hero section and the entire marketing argument.

---

## Performance Dashboard (Public Page)

Accessible without login. This is the marketing.

```
StockEye AI — Live Track Record

Strategy performance (last 180 days)
┌─────────────────────────────────────────┐
│  Returns      +23.4%   Nifty: +9.1%    │
│  Win Rate     66%      Trades: 147      │
│  Avg Hold     3.4 days                  │
│  Max Drawdown -11.2%                    │
│  Sharpe       1.94                      │
└─────────────────────────────────────────┘

[Equity curve chart vs Nifty]
[Trade history table — ticker, entry, exit, P&L]
[Monthly breakdown table]

⚠️ Paper trading simulation. Not investment advice.
```

Every trade is public. Every loss is shown. Transparency is the product.

---

## Product Features — Complete List

### Portfolio & Trading
- [x] Paper portfolio with balance, holdings, P&L
- [x] Autonomous AI trading sessions
- [x] Manual paper trading
- [x] Performance history (daily snapshots)
- [ ] ATR-based position sizing
- [ ] Multiple portfolios (test different strategies)
- [ ] Portfolio benchmark comparison (vs Nifty, vs Sensex)
- [ ] Trade journal with reasoning chain per trade

### AI Intelligence
- [x] Claude recommendations (BUY/SELL/HOLD/WATCH)
- [x] Technical analysis signals
- [x] News sentiment
- [ ] Extended thinking decisions (Opus model)
- [ ] FII/DII signal integration
- [ ] F&O PCR + OI signal
- [ ] Delivery volume % signal
- [ ] India VIX regime filter
- [ ] Macro regime detector (BULL/BEAR/SIDEWAYS/VOLATILE)
- [ ] Event calendar awareness (earnings, RBI, expiry)
- [ ] Adaptive signal weights (learns over time)

### Risk Management
- [ ] Hard risk gate (15+ rule checks)
- [ ] ATR-based position sizing
- [ ] Daily loss limit enforcement
- [ ] Drawdown-based pause
- [ ] Correlation filter between positions
- [ ] Liquidity filter
- [ ] Time-of-day filter
- [ ] Earnings blackout enforcement

### Screener (Free, Public, SEO)
- [x] Basic screener
- [ ] FII buying + technically strong
- [ ] High delivery % + oversold RSI
- [ ] F&O OI buildup + price consolidating
- [ ] Pre-earnings momentum setups
- [ ] Public, no-login required (traffic driver)

### Analytics & Reporting
- [x] Daily returns history
- [ ] Public performance dashboard
- [ ] Post-trade signal accuracy analysis
- [ ] Monthly strategy review report
- [ ] Weekly AI portfolio review (personalized)
- [ ] Signal accuracy breakdown over time

### Notifications & Distribution
- [x] Telegram daily briefings
- [ ] WhatsApp Business API integration
- [ ] Public Telegram channel (AI trade calls, outcomes)
- [ ] Browser push notifications (PWA)
- [ ] Email digest (weekly performance)

### Monetization
- [ ] Subscription tiers (Free/Pro/Premium/Teams)
- [ ] Razorpay subscription billing
- [ ] Usage tracking per tier
- [ ] Feature gating by subscription
- [ ] Affiliate/referral program (₹100 per paid referral)

### Mobile & Distribution
- [ ] PWA manifest (installable from browser)
- [ ] Mobile-optimized UI
- [ ] React Native app (at 5,000 users)

### Compliance & Trust
- [x] Audit log for all actions
- [ ] Immutable trade log (append-only)
- [ ] Public performance dashboard with all losses shown
- [ ] "Paper trading only" disclaimer throughout
- [ ] Terms of Service and Disclaimer pages

---

## Distribution & Growth Strategy

### Primary Channel — Telegram Public Channel

Create: "StockEye AI Calls" (public, free)
- Post every AI trade call: "StockEye flagged TCS BUY at ₹2,394. Here's Claude's reasoning: [excerpt]"
- Post every outcome: "TCS trade closed +4.2% in 3 days. Signal that nailed it: FII bought ₹1,800cr"
- Post losses too — transparency builds more trust than hiding them
- Weekly performance summary

Traders share good calls. 10,000 Telegram subscribers = 500-1,000 paying users.

### Secondary Channel — Twitter/X Finance Community

Post daily:
- Trade calls with Claude reasoning excerpt
- "What the AI is watching today" with signal scores
- Weekly performance vs Nifty chart

One viral post = thousands of signups. The reasoning chain excerpts are shareable content nobody else has.

### YouTube Creator Partnerships

Target: 10-15 Indian trading YouTubers (50K-500K subscribers)
Offer: Free Premium account + affiliate commission (₹100/paid referral)
They demo StockEye to their audience, you get qualified leads.

### Free Screener (SEO Play)

Public screener, no login, powered by India-specific signals.
Chartink has 2M+ monthly visitors just from free screeners.
Your screener has FII + delivery + F&O signals — nobody else offers this free.
This is the top-of-funnel traffic driver.

### Referral Program
- Existing user refers → friend subscribes → referrer gets ₹100 credit
- Simple, compound growth

---

## Build Order — Strict Month-by-Month

### Month 1 — Make It Trustworthy
**Goal: Accurate data, disciplined risk, better decisions**

1. Fix all P&L accuracy issues (invested = market value, daily P&L vs previous day) ← in progress
2. Build `RiskGate` class with all 15+ hard rules
3. ATR-based `calculate_position_size()` function
4. Replace current agentic trader to use RiskGate before every trade
5. FII/DII daily flows signal (fetch from NSE, store daily)
6. Delivery volume % signal (from NSE Bhavcopy)
7. F&O PCR signal (from NSE F&O data)
8. Two-tier AI: Haiku for scan, Opus+extended thinking for decision
9. Full trade logging (immutable, with signal scores + reasoning chain)

**Done when:** Autonomous session runs, hits risk gate, uses ATR sizing, logs full reasoning.

---

### Month 2 — Build the Proof
**Goal: Backtest, public track record, Telegram channel**

1. Backtesting engine (90-day minimum on watchlist stocks)
2. India VIX integration + regime detector (BULL/BEAR/SIDEWAYS/VOLATILE)
3. Promoter pledging % signal
4. Earnings calendar integration + blackout enforcement
5. Signal accuracy tracking (which signals predicted outcomes)
6. Adaptive signal weight adjustment (after every 50 trades)
7. Public performance dashboard (no login required)
8. Launch "StockEye AI Calls" Telegram public channel

**Done when:** Can show "here's 60 days of backtested trades, here's the live record, here's the reasoning behind each call."

---

### Month 3 — Monetize
**Goal: First paying users**

1. Razorpay subscription integration
2. Feature gating (Free/Pro/Premium tiers)
3. WhatsApp Business API for briefings
4. Free public screener (FII + delivery + F&O signals)
5. Weekly AI portfolio review (personalized, Pro feature)
6. Monthly strategy review report (auto-generated)
7. PWA manifest (mobile installable)
8. Terms of Service, Disclaimer, public compliance copy

**Done when:** First 100 paid subscribers.

---

### Month 4 — Deepen Intelligence
**Goal: Best signal stack for Indian markets**

1. Global cues integration (SGX Nifty, Dow futures, crude oil)
2. Bulk/block deal detection
3. F&O OI buildup signal
4. Short covering / F&O ban detection
5. Sector rotation intelligence (which sectors FII buying)
6. RBI/FOMC event calendar
7. F&O expiry cycle awareness
8. Correlation filter between open positions (implemented in risk gate)
9. Post-trade signal accuracy analysis dashboard

**Done when:** System refuses trades on expiry week when appropriate, detects FII sector rotation.

---

### Month 5 — Scale the Product
**Goal: Community, retention, growth**

1. Community paper trading leaderboard (anonymous rankings)
2. Multiple portfolios per user (test different strategies)
3. Teams/Educator tier
4. YouTube creator partnership program
5. Referral program (Razorpay credit integration)
6. Mobile optimization pass
7. Browser push notifications

**Done when:** 500+ paid users, week-over-week growth positive.

---

### Month 6 — Prepare for Real Trading
**Goal: Compliance and real execution foundation**

1. Apply for Research Analyst (SEBI RA) license (with 6-month track record)
2. Zerodha Kite API integration (paper mode first, then live)
3. Real vs paper portfolio comparison for same user
4. Slippage and liquidity modeling for real trades
5. Compliance documentation and risk disclosures

**Done when:** RA license applied, Kite sandbox integration working.

---

## Accuracy Improvement Checklist

These are all the things that make the AI's decisions genuinely better:

### Data Quality
- [ ] Price data staleness check (if price > 10 min old, don't trade)
- [ ] Corporate action adjustment (split/bonus affects all historical prices)
- [ ] Holiday calendar (NSE market holidays — don't attempt trades)
- [ ] Pre-market gap detection (SGX Nifty vs previous Nifty close)

### Signal Quality
- [ ] Minimum 3/5 signal categories must align before allowing trade
- [ ] Signal confidence weighted scoring (stale data = lower confidence)
- [ ] Anti-pattern blocklist (SEBI actions, circuit history, F&O ban)
- [ ] Liquidity filter (avg daily volume > ₹5cr)
- [ ] Time-of-day filter (10:00 AM - 2:30 PM only)

### Decision Quality
- [ ] Market regime filter (different strategy for BULL vs BEAR vs VOLATILE)
- [ ] Session awareness (morning vs afternoon — momentum behaves differently)
- [ ] Multi-timeframe confirmation (daily + hourly signals must agree)
- [ ] Stop-loss must be technically meaningful (below support, not arbitrary %)
- [ ] Target must have at least 2:1 risk-reward ratio

### Portfolio Quality
- [ ] Correlation check between all open positions
- [ ] Sector concentration check (max 40% in any sector)
- [ ] Consecutive loss detection (3 losses = HOLD mode)
- [ ] Rolling drawdown monitoring (daily peak-to-trough)
- [ ] Rebalancing trigger (position drifts > 5% from target → flag)

### Feedback Quality
- [ ] Every trade outcome linked back to signal scores at entry
- [ ] Signal accuracy tracking per signal type
- [ ] Regime-conditional accuracy (does the strategy work in bear markets?)
- [ ] Adaptive weight adjustment every 50 trades
- [ ] Monthly strategy degradation check (is win rate falling?)

---

## Competitive Positioning

| Product | Focus | AI? | India-specific? | Track record? | Price |
|---|---|---|---|---|---|
| **StockEye** | AI paper trading | Yes (deep) | Yes (FII, F&O, delivery) | Yes (public) | ₹399-999 |
| Streak (Zerodha) | Algo trading | No | Yes | No | ₹500-1500 |
| Smallcase | Thematic investing | Basic | Yes | Partial | ₹99-500 |
| Tickertape | Screener + research | Basic | Yes | No | ₹299-999 |
| Chartink | Screener | No | Yes | No | Free-₹499 |
| Sensibull | Options | Basic | Yes | No | ₹800-1500 |
| OpenProphet | AI trading | Yes | No (US) | Yes | Open source |

**StockEye's unique position:** Only product combining deep AI reasoning + India-specific institutional signals + transparent public track record + accessible price point.

---

## Key Metrics to Track

### Product Health
- Daily active users / Monthly active users (DAU/MAU ratio)
- Autonomous session completion rate
- Average session P&L
- 30-day retention rate (most important SaaS metric)

### AI Performance
- Win rate (target: >60%)
- Profit factor (target: >1.8)
- Sharpe ratio (target: >1.5)
- Max drawdown (target: <15%)
- Signal accuracy by type

### Business
- MRR (Monthly Recurring Revenue)
- Churn rate (target: <5%/month)
- CAC (Customer Acquisition Cost)
- LTV (Lifetime Value)
- Free-to-paid conversion rate (target: >8%)

---

## What NOT to Build (Avoid Scope Creep)

- Real-money trading before RA license and broker integration is ready
- Options trading strategy (complex, high risk — Phase 2 only)
- Crypto trading (different market, different regulations, distraction)
- Social/copy trading (regulatory complexity)
- Fundamental analysis deep-dive (quarterly financials) — not the core loop
- Mobile native app before 5,000 users (PWA is sufficient)
- Multi-language/vernacular (Phase 2, after product-market fit)

---

## Critical Files to Know

```
backend/
├── app.py                    # All Flask routes (1900+ lines)
├── agentic_trader.py         # Autonomous session logic ← major changes needed
├── trading_manager.py        # Paper trading execution, snapshots
├── ai_advisor.py             # Claude integration
├── brain_engine.py           # Brain score calculation
├── stock_data.py             # Price/technical data fetching
├── market_monitor.py         # Background monitoring
├── telegram_notify.py        # Telegram notifications
├── risk_gate.py              # TO CREATE: hard risk rules
├── signal_engine.py          # TO CREATE: unified signal scoring
├── backtest.py               # TO CREATE: backtesting engine
└── fii_dii_fetcher.py        # TO CREATE: India-specific data

frontend/src/components/
├── Advisor.jsx               # Main trading UI
└── [public performance page] # TO CREATE: no-auth performance dashboard
```

---

## Notes & Decisions

- **No microservices.** Modular monolith with Flask + Celery + Redis is the right architecture for this stage. Extract to services only when a specific bottleneck demands it.
- **Paper trading is the product, not a limitation.** The track record IS the value proposition.
- **Claude Opus for final decisions, Haiku for scanning.** Cost control is important — Opus only runs when Haiku passes the scan.
- **Extended thinking is non-negotiable for premium tier.** The reasoning chain is the differentiator.
- **All signal data from free NSE/BSE sources first.** Don't pay for data until you have paying users.
- **WhatsApp > Telegram for Indian retail reach.** Implement WhatsApp Business API in Month 3.
- **Transparency is the marketing strategy.** Show every trade, every loss, every decision. Trust compounds.
