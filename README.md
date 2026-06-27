# BargainBot 🤖💰

> **AI-powered price comparison, prediction, festival intelligence, and Groq LLM shopping advisor for Indian e-commerce.**
> Compares live prices from Amazon India and Flipkart, predicts the next 3 months of price movement using ML, layers on Indian festival sale intelligence, and generates Groq LLM analysis telling you *exactly* when to buy and why.

---

## Table of Contents

1. [What the Project Does](#what-the-project-does)
2. [Market Analysis](#market-analysis)
3. [Novelty & Approach](#novelty--approach)
4. [Tech Stack](#tech-stack)
5. [Architecture Overview](#architecture-overview)
6. [Project Structure](#project-structure)
7. [File-by-File Breakdown](#file-by-file-breakdown)
8. [How the ML Model Works](#how-the-ml-model-works)
9. [Groq AI Integration](#groq-ai-integration-v7)
10. [Analytics Engine](#analytics-engine-v8)
11. [How the Scraper Works](#how-the-scraper-works)
12. [Festival Calendar System](#festival-calendar-system)
13. [Database Schema](#database-schema)
14. [API Routes & Response Shape](#api-routes--response-shape)
15. [Frontend Architecture](#frontend-architecture)
16. [Email Alert System](#email-alert-system)
17. [Background Scheduler](#background-scheduler)
18. [Setup & Running Locally](#setup--running-locally)
19. [Known Limitations](#known-limitations)
20. [Current State of the Project](#current-state-of-the-project)
21. [Version Change Log](#version-change-log)

---

## What the Project Does

BargainBot is a single-page Flask web application. A user types any product name (e.g. "Samsung Galaxy S24", "boAt headphones", "iPhone 15") and BargainBot:

1. **Scrapes live prices** from Amazon India and Flipkart in real-time (no Selenium)
2. **Cross-validates** both prices — discards outliers if the ratio exceeds 3x
3. **Predicts** 90 days (3 months) of future prices using ML with 14 festival-aware features
4. **Shows a verdict**: `BUY NOW`, `WAIT`, or `CONSIDER`
5. **Shows specific date advice** — "Wait until 12 July for Amazon Prime Day — save ₹31,465 extra at ₹58,435"
6. **Renders a full price chart** — 24-month history + 90-day ML forecast with sale-day star markers
7. **Shows an Upcoming Sales strip** — next 5 Indian/global sales as scrollable pills
8. **Renders a complete analytics dashboard** from real scraped data + ML forecast:
   - Price statistics (ATH, ATL, historical average)
   - Deal Score ring gauge (0–100)
   - Buy Intelligence (best month, price drops, max savings — powered by forecast)
   - Monthly Price Trend bar chart (actual months in purple + ML forecast months in blue)
9. **Runs Groq LLM analysis** — category detection, AI confidence score, smart summary, best time to buy, risk note
10. **Lets users set a target price alert** — email sent when price drops below target
11. **Runs a background job** every 6 hours to refresh prices and fire pending alerts

---

## Market Analysis

### The Indian E-Commerce Opportunity

India is the world's fastest-growing e-commerce market.

| Metric | Value |
|---|---|
| **Indian e-commerce market size (2024)** | ~$70 billion USD |
| **Projected market size (2030)** | ~$325 billion USD |
| **Active online shoppers in India (2024)** | ~300 million |
| **Amazon India + Flipkart market share** | ~60–65% of all Indian e-commerce |
| **Annual festival sale GMV (Prime Day + Big Billion Days)** | ~$8–12 billion combined |
| **Shoppers who regret paying too much** | 74% (KPMG India, 2023) |

### The Problem BargainBot Solves

Indian e-commerce pricing is uniquely complex:

- **Flash sales happen at any time** — prices change within hours, not days
- **Festival season (Oct–Nov) drops prices 20–40%** but most shoppers don't know the exact dates
- **Amazon and Flipkart compete aggressively** — the same product can vary 15–30% between platforms on the same day
- **No existing tool gives Indian shoppers a data-backed buy/wait decision** — CamelCamelCamel, PriceSpy are US/EU focused and don't model Indian festivals

### Competitive Landscape

| Tool | India? | ML Forecast? | Festival-Aware? | AI Advice? |
|---|---|---|---|---|
| **CamelCamelCamel** | No | No | No | No |
| **PriceSpy** | No | No | No | No |
| **PriceHunt** | Yes | No | No | No |
| **Smartprix** | Yes | No | No | No |
| **Flipkart Wishlist Alerts** | Yes | No | No | No |
| **BargainBot** | **Yes** | **Yes (90 days)** | **Yes (19 events)** | **Yes (Llama 3.3)** |

### Target Users

| Segment | Pain Point |
|---|---|
| Budget-conscious smartphone buyers (~80M/year) | Don't know if they should wait for Amazon Prime Day |
| Festival shoppers (Diwali season, ~180M/year) | Can't predict which products will drop and by how much |
| Electronics buyers (laptops, TVs, ~25M/year) | High-value purchases where timing saves thousands of rupees |
| Deal hunters (~40M regular users on deal forums) | Need real data, not guesswork |

### Revenue Potential (Future)

| Model | Description |
|---|---|
| **Affiliate commissions** | Amazon Associates / Flipkart Affiliate — earn 3–8% on purchases driven through BargainBot links |
| **Premium alerts** | Paid tier for real-time alerts (<1 hour) vs free 6-hour checks |
| **B2B API** | Sell price prediction API to fintech apps, BNPL lenders, comparison sites |
| **Brand partnerships** | Manufacturers pay for placement in "best time to buy" recommendations |

---

## Novelty & Approach

### 1. Festival-First ML Architecture

Most price prediction tools treat time as the only variable. BargainBot encodes 7 Indian festival features directly into the ML feature vector:

```
festival_score        → 0.0–1.0 float (how close to a sale event)
event_multiplier      → expected price multiplier (0.60 on Prime Day = 40% off)
is_prime_day_window   → binary: Jul 12–20
is_big_billion_window → binary: Oct 4–12
is_diwali_window      → binary: Oct 10–30
is_republic_day_window→ binary: Jan 20–31
is_year_end_window    → binary: Dec 15–31
```

No other free/open-source Indian price tool trains ML models with these features.

### 2. Forecast-Powered Analytics (Real Data Philosophy)

The analytics engine has a strict hierarchy:
1. **Real scraped data** (from `prices` DB table) — always preferred
2. **ML forecast data** (90-day Linear Regression output) — used when scraped history is sparse
3. **Provenance always shown** — users see exactly where the numbers come from

Analytics are always meaningful on the first search — not blank or placeholder.

### 3. Three-Layer Intelligence Pipeline

Every search produces three independent layers:

```
Layer 1: ML prediction (Linear Regression / Prophet)
         → predicted_price, verdict, 90-day festival-adjusted forecast

Layer 2: Festival calendar engine
         → sale events overlaid on forecast, date_advice generated,
           active_event_banner, upcoming_events strip

Layer 3: Groq LLM (Llama 3.3 70B)
         → synthesises all of the above into human language:
           smart_summary, analysis_paragraph, category_advice,
           confidence_score, best_time_to_buy, risk_note
```

No other price tool combines quantitative ML + festival knowledge graph + generative LLM in a single pipeline.

### 4. Data Provenance Transparency

- Green badge: "Based on N real price records"
- Amber badge: "Limited data — N records (search again to build history)"
- Grey badge: "No price history yet — analytics improve with each search"

### 5. Self-Healing Design

- **Groq unavailable?** All ML features still work, no error shown
- **Flipkart blocked?** Analysis proceeds with Amazon price alone
- **No price history?** Analytics uses ML forecast as the data source
- **Festival dates shift?** Year-wrap-around logic resolves all dates correctly

---

## Tech Stack

| Layer | Technology | Notes |
|---|---|---|
| **Backend** | Python 3.11+, Flask | Dev server on `0.0.0.0:5000` |
| **ML Primary** | scikit-learn LinearRegression | 14 features, 164k row training set, MAE ~₹803 |
| **ML Secondary** | Facebook Prophet | Festival regressors, MAE ~₹67k on multi-product data |
| **AI Analysis** | Groq REST API — llama-3.3-70b-versatile | Free tier, no SDK needed |
| **Scraping** | requests + BeautifulSoup4 | 3-strategy Flipkart, no Selenium |
| **Database** | SQLite (prices.db) via sqlite3 | Frozen 3-table schema |
| **Scheduler** | schedule library + threading | Daemon thread, 6-hour cycles |
| **Email** | smtplib + MIME — Gmail SMTP port 587 | STARTTLS, App Password auth |
| **Frontend** | Vanilla HTML + CSS + JavaScript | Zero frameworks, no build step |
| **Charts** | Chart.js (CDN) | Price trend + seasonal bar chart |
| **Fonts** | Google Fonts — Inter | Preconnect optimised |

---

## Architecture Overview

```
┌─────────────────────────────────────────────────────┐
│                    USER BROWSER                     │
│  index.html + script.js + style.css                 │
│  Search bar → POST /search                          │
│  Chart.js renders price trend + monthly bar chart   │
│  Groq AI card, festival pills, analytics dashboard  │
└────────────────────┬────────────────────────────────┘
                     │ HTTP
┌────────────────────▼────────────────────────────────┐
│              FLASK APP (app.py)                     │
│  / | /search | /set-alert | /history | /model-stats │
└──────┬──────────────┬──────────────┬────────────────┘
       │              │              │
┌──────▼──────┐ ┌─────▼──────┐ ┌────▼───────────┐
│ scraper.py  │ │ model.py   │ │ database.py    │
│ Amazon      │ │ LinearReg  │ │ prices table   │
│ Flipkart    │ │ Prophet    │ │ alerts table   │
│ 3-strategy  │ │ festivals  │ │ products table │
│ cross-valid │ │ analytics  │ └────────────────┘
└─────────────┘ │ groq_client│
                └─────┬──────┘
                      │ REST
               ┌──────▼──────┐
               │  GROQ API   │
               │ Llama 3.3   │
               │ 70B Versatile│
               └─────────────┘

Background (scheduler.py + alert_checker.py):
  Every 6h → scrape tracked products → check alerts → emailer.py → Gmail
```

---

## Project Structure

```
D:\BargainBot\
│
├── app.py              # Flask app — routes & startup
├── scraper.py          # Live price scraping (Amazon + Flipkart, 3-strategy)
├── model.py            # ML training, prediction, 90-day forecast, analytics, festival engine
├── festivals.py        # Indian festival/sale calendar — 19 events, single source of truth
├── database.py         # SQLite helpers — all DB reads/writes including get_full_history()
├── groq_client.py      # Groq REST API wrapper — Llama 3.3 70B analysis
├── scheduler.py        # Background 6-hour price refresh daemon thread
├── alert_checker.py    # Alert processor — compares prices, fires emails
├── emailer.py          # Gmail SMTP email sender
├── email_config.py     # SMTP credentials (user must fill in)
│
├── Dataset/            # Training data CSVs (164,912 rows total, auto-loaded)
│
├── model_cache.pkl     # Cached trained models (version v2-festival)
├── prices.db           # SQLite database (auto-created on first run)
│
├── static/
│   ├── style.css       # All styling (~1,100+ lines)
│   └── script.js       # All frontend JS (~1,080 lines)
│
├── templates/
│   └── index.html      # Single-page app HTML (314 lines)
│
└── README.md           # This file
```

---

## File-by-File Breakdown

### `app.py` — Flask Application
- Entry point. `startup()` calls: `init_db()` → `train_models()` → `start_scheduler()`
- Serves on `0.0.0.0:5000`. Forces UTF-8 on Windows stdout/stderr.
- **5 routes**: `/`, `/search`, `/set-alert`, `/history`, `/model-stats`

---

### `festivals.py` — Indian Festival Calendar (v6)

**`FESTIVAL_CALENDAR`** — 19 events keyed by `"MM-DD"`:

| Category | Events |
|---|---|
| **Amazon** | Prime Day (Jul 15, 35%), Great Republic Day (Jan 12, 25%), Freedom Sale (Aug 8, 20%), Year End Sale (Dec 19, 28%) |
| **Flipkart** | Big Billion Days (Oct 7, 40%), Republic Day Sale (Jan 16, 22%), Big Shopping Days (May 5, 20%) |
| **National** | Diwali (Oct 20, 30%), Navratri (Sep 28, 18%), Holi (Mar 25, 15%), Independence Day (Aug 15, 18%), Republic Day (Jan 26, 20%), Onam (Sep 5, 16%), Baisakhi (Apr 14, 14%), Gandhi Jayanti (Oct 2, 12%) |
| **Global** | Singles Day (Nov 11, 22%), Black Friday (Nov 29, 25%), Christmas (Dec 25, 20%), Mid-Year Clearance (Jun 20, 18%) |

**Helper functions**: `get_upcoming_events()`, `get_active_event()`, `get_festival_feature()`, `get_event_price_multiplier()`, `days_until_next_event()`

**Year wrap-around**: All date comparisons resolve current year first, then next year if date has passed.

---

### `scraper.py` — Price Scraper

**Amazon**: GET `amazon.in/s?k=...` → CSS selectors in priority order.

**Flipkart** — 3 strategies:
1. Internal JSON API (`/api/4/page/fetch?q=...&ajax=true`) — parses `finalPrice`/`sellingPrice`
2. Full browser-like HTML — primes session with homepage cookies + full Chrome fingerprint
3. Minimal GET fallback

**Cross-validation**: If `max/min > 3.0`, discard outlier. Price floor: ₹500.

---

### `model.py` — ML Engine (v6, v7, v8)

**14 ML features**:

| Feature | Description |
|---|---|
| `day_of_week` | 0–6 |
| `month` | 1–12 |
| `days_since_start` | Age of data point |
| `rolling_avg_7d` | 7-day rolling average |
| `price_volatility` | Std dev of last 7 days |
| `discount_pct` | % off from original |
| `is_festival_month` | 1 if Jul/Oct/Nov |
| `festival_score` | 0.0–1.0 float (v6) |
| `event_multiplier` | Expected price multiplier (v6) |
| `is_prime_day_window` | Binary (v6) |
| `is_big_billion_window` | Binary (v6) |
| `is_diwali_window` | Binary (v6) |
| `is_republic_day_window` | Binary (v6) |
| `is_year_end_window` | Binary (v6) |

**Models**: Linear Regression (winner, MAE ~₹803) vs Prophet (MAE ~₹67k on multi-product data).

**Cache**: Tagged `v2-festival` — stale cache auto-deleted and retrains.

**`generate_suggestion()` pipeline**:
1. Scrape live prices
2. `_build_real_history()` — real scraped DB data
3. `_predict_linear()` — 90-day festival-adjusted forecast
4. Compute `date_advice` (BUY_NOW / WAIT_FOR_EVENT / WAIT_FOR_DIP / CONSIDER)
5. Get `upcoming_events` + `active_event`
6. `_compute_analytics(hist_prices, forecast=forecast)` — enriched with forecast (v8)
7. `get_groq_analysis()` — Llama 3.3 AI synthesis (v7)

---

### `groq_client.py` — Groq AI Integration (v7)

**Model**: `llama-3.3-70b-versatile` (updated from decommissioned `llama3-70b-8192`)

**Prompt includes**: product name, current price, ML predicted price, all-time high/low, deal score, festival context, upcoming sales, price history summary, 3-month forecast summary.

**Returns 9 fields**: `category`, `category_advice`, `analysis_paragraph`, `smart_summary`, `confidence`, `confidence_reason`, `best_time_to_buy`, `risk_note`, `groq_verdict_text`

**Fallback**: Returns `None` on any error. All ML features continue working. No error shown to user.

---

### `database.py` — SQLite Helpers

| Function | Purpose |
|---|---|
| `init_db()` | Creates 3 tables if they don't exist |
| `save_price(product, platform, price)` | Inserts a scraped price record |
| `get_history(product)` | Last 30 days of price records |
| `get_full_history(product_name)` | **All** scraped records for a product (v8) |
| `save_alert(product, email, target_price)` | Stores a new price alert |
| `get_all_alerts()` | Returns all unsent alerts |
| `mark_alert_sent(alert_id)` | Flips `is_sent = 1` |
| `get_latest_price(product)` | Most recent price per platform |
| `get_all_tracked_products()` | All unique products with price data |

---

## How the ML Model Works

```
Dataset CSVs → _load_csv() → _engineer_features() → train/test split (80/20)
                                    |
                      14 features (7 original + 7 festival)
                                    ↓
                Linear Regression         Prophet + add_regressor()
                (scikit-learn)            (festival_score, event_multiplier)
                                    ↓
                      MAE comparison → winner selected
                                    ↓
                model_cache.pkl (version: "v2-festival")
                                    ↓
User searches → scrape_prices() → generate_suggestion(live_prices)
                                    ↓
                        get_full_history() from DB
                                    ↓
                _predict_linear() → raw 90-day forecast
                                    ↓
                For each forecast date: get_event_price_multiplier()
                → adjust price if in sale window
                → mark is_sale_day + event_name
                                    ↓
                _compute_analytics(hist, forecast=forecast)  [v8]
                                    ↓
                get_groq_analysis() → Llama 3.3 synthesis    [v7]
                                    ↓
                Full JSON → frontend renders 3-layer intelligence
```

---

## Groq AI Integration (v7)

### Setup

1. Get your Groq API key free: https://console.groq.com
2. Open `D:\BargainBot\groq_client.py`
3. Set `GROQ_API_KEY = "gsk_your_key_here"`
4. Restart the app — AI analysis appears automatically

### What it shows in the UI

| Component | Location |
|---|---|
| Smart Summary | Purple banner at top of Prediction card |
| Confidence Meter | Animated progress bar + % in Prediction card |
| Category Badge | "Smartphone", "Laptop" etc. in Groq card |
| Category Advice | India-specific timing advice |
| Analysis Paragraph | Main body of Groq card |
| Best Time to Buy | Green box with specific date/event |
| Risk Note | Amber box with risk of waiting |

### Fallback

If Groq API is unavailable, times out (>15s), or key is not set: `groq_analysis = null`, all ML features continue, no error shown.

---

## Analytics Engine (v8)

`_compute_analytics()` accepts both real scraped history AND the 90-day ML forecast. Analytics are always populated on the first search.

### Data Hierarchy

```
Priority 1: Real scraped DB data → get_full_history()
Priority 2: ML 90-day forecast   → _predict_linear()
```

### Metrics Computed

| Metric | Source | Description |
|---|---|---|
| All-Time High | Real DB | Max ever-scraped price |
| All-Time Low | Real DB | Min ever-scraped price |
| Historical Avg | Real DB | Mean of all scraped prices |
| vs Average % | Real DB | (current − avg) / avg × 100 |
| Deal Score | Real + Forecast | 0–100 based on combined price range |
| Price Trend | Real (fallback: Forecast) | up / down / stable |
| Best Month to Buy | **Forecast** (primary) | Cheapest predicted month from 90-day ML |
| Price Drops | Real + Forecast | Actual drops (>5%) + ML-predicted dips (>3%) |
| Max Possible Savings | **Forecast** (primary) | current_price − min(forecast) |
| Monthly Chart | Real + Forecast | Purple bars = actual months; Blue bars = forecast months |

### Provenance Badge (always shown)

- Green: "Based on N real price records" (>=5 scrapes)
- Amber: "Limited data — N records (search again to build history)" (1–4 scrapes)
- Grey: "No price history yet — analytics improve with each search" (first search)

---

## Database Schema

```sql
CREATE TABLE products (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    name       TEXT UNIQUE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE prices (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    product_name TEXT,
    platform     TEXT,       -- 'amazon' or 'flipkart'
    price        INTEGER,    -- price in Indian Rupees
    timestamp    TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE alerts (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    product_name TEXT,
    email        TEXT,
    target_price INTEGER,
    created_at   TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    is_sent      INTEGER DEFAULT 0
);
```

> Schema is frozen. No columns added without a migration.

---

## API Routes & Response Shape

| Method | Route | Input | Response |
|---|---|---|---|
| GET | `/` | — | Renders index.html |
| POST | `/search` | `{ "product": "..." }` | Full prediction + analytics + Groq |
| POST | `/set-alert` | `{ "product", "email", "target_price" }` | `{ success, message }` |
| GET | `/history?product=...` | query param | `{ product, history[] }` |
| GET | `/model-stats` | — | `{ linear_mae, prophet_mae, winner }` |

### `/search` Response Shape (v8)

```json
{
  "product": "Samsung Galaxy S24",
  "prices": { "amazon": 52198, "flipkart": null },
  "prediction": {
    "verdict": "CONSIDER",
    "current_price": 52198,
    "predicted_price": 49999,
    "days_to_wait": 5,
    "savings": 2199,
    "why": "ML forecast predicts a dip in 5 days",
    "trust": "limited",
    "forecast": [
      {"date": "2026-06-28", "price": 51800, "is_sale_day": false, "event_name": null},
      {"date": "2026-07-15", "price": 33929, "is_sale_day": true, "event_name": "Amazon Prime Day"}
    ],
    "analytics": {
      "all_time_high": 52198,
      "all_time_low": 49999,
      "avg_price": 49999,
      "vs_avg_pct": 4.4,
      "deal_score": 66,
      "price_drops": 3,
      "avg_drop_pct": 3.2,
      "fc_dips": 3,
      "trend": "stable",
      "best_month": "August (predicted)",
      "max_savings": 18269,
      "max_savings_pct": 35.0,
      "savings_note": "vs 3-month forecast low",
      "forecast_low": 33929,
      "monthly_data": [
        {"month": "2026-06", "price": 49999, "type": "actual"},
        {"month": "2026-07", "price": 42800, "type": "forecast"},
        {"month": "2026-08", "price": 39100, "type": "forecast"},
        {"month": "2026-09", "price": 41500, "type": "forecast"}
      ],
      "data_source": "limited",
      "data_points": 3
    },
    "date_advice": {
      "action": "WAIT_FOR_EVENT",
      "reason": "Amazon Prime Day is in 18 days — expect ~35% off",
      "buy_after": "12 July 2026",
      "buy_before": "17 July 2026",
      "event_name": "Amazon Prime Day",
      "event_discount": 35.0,
      "projected_price": 33929,
      "extra_saving": 18269,
      "urgency": "MEDIUM"
    },
    "upcoming_events": [
      {
        "name": "Amazon Prime Day",
        "date": "15 July 2026",
        "days_away": 18,
        "discount_pct": 35.0,
        "sale_starts": "12 July 2026",
        "platforms": ["amazon"]
      }
    ],
    "active_event": null,
    "groq_analysis": {
      "category": "Smartphone",
      "category_advice": "Smartphones in India see biggest discounts during Prime Day and Big Billion Days. Wait until July for 20-35% savings.",
      "analysis_paragraph": "The Samsung Galaxy S24 is currently priced at Rs.52,198...",
      "smart_summary": "Wait 18 days for Prime Day — save Rs.18,269 at Rs.33,929.",
      "confidence": 78,
      "confidence_reason": "Prime Day historically delivers 35% on Samsung flagships.",
      "best_time_to_buy": "Buy between 12-17 July 2026 during Amazon Prime Day",
      "risk_note": "Risk: Prime Day stock sells out fast — set the price alert now.",
      "groq_verdict_text": "..."
    }
  },
  "history": [...]
}
```

---

## Frontend Architecture

- **Zero frameworks** — pure HTML, CSS, JavaScript
- **No build step** — files served directly by Flask static handler
- **State**: results hidden/shown by toggling `.visible` CSS class
- **Dynamic injection**: Upcoming Events strip, Date Advice box, Groq card, analytics data badge — all created via `createElement` after each search
- **Charts**: Chart.js from CDN
- **Currency**: `.toLocaleString("en-IN")` for Rs.1,23,456 format

**Key JS functions**:

| Function | Purpose |
|---|---|
| `searchProduct()` | Main search — calls /search, orchestrates all renders |
| `populateLivePrices()` | Renders live price cards |
| `populatePrediction()` | Verdict, event banner, date-advice, Groq summary + confidence |
| `renderGroqAnalysisCard()` | Full AI card — category, advice, best time, risk note |
| `renderUpcomingEvents()` | Scrollable upcoming sales pill strip |
| `drawChart()` | Chart.js price trend with sale-day star markers |
| `populateAnalytics()` | All analytics cards + real data badge |
| `drawSeasonalChart()` | Bar chart — purple actual + blue forecast + amber festival |
| `setAlert()` | Calls /set-alert, shows success/error |
| `loadModelStats()` | Renders MAE comparison boxes |

---

## Email Alert System

1. User submits email + target price via Price Alert form
2. Frontend calls `POST /set-alert`
3. Alert saved to `alerts` table with `is_sent = 0`
4. Every 6 hours, scheduler fires `check_and_send_alerts()`
5. Compare `best_current_price <= target_price`
6. If triggered: Gmail SMTP sends HTML email, alert marked `is_sent = 1`

**Email includes**: product, current price, target, platform, predicted price (90-day), estimated savings.

---

## Background Scheduler

```
scheduler.py — daemon thread, every 6 hours
  ↓
get_all_tracked_products()
  ↓ for each product:
scrape_prices() → save_price()
  ↓
check_and_send_alerts()
  ↓ if price <= target:
send_price_alert_email() → Gmail SMTP → User inbox
mark_alert_sent()
```

---

## Setup & Running Locally

### Prerequisites

```bash
pip install flask requests beautifulsoup4 scikit-learn pandas numpy prophet schedule
```

No extra install needed for Groq — uses standard `requests` library.

### Steps

```bash
# 1. Download the project to D:\BargainBot\

# 2. (Optional) Configure email alerts
#    Edit email_config.py with your Gmail + 16-digit App Password

# 3. (Optional) Set Groq API key for AI analysis
#    Edit groq_client.py — set GROQ_API_KEY = "gsk_your_key_here"
#    Free key at: https://console.groq.com

# 4. Run
cd D:\BargainBot
python app.py

# 5. Open browser: http://localhost:5000
```

**First run**: `prices.db` auto-created. `model_cache.pkl` generated in ~30–60s for 164k rows. Subsequent startups are instant.

---

## Known Limitations

| Issue | Status |
|---|---|
| **Flipkart bot protection** | Cloudflare WAF. Shows "Unavailable" when blocked. Not a code bug. |
| **Amazon rate limiting** | Occasional CAPTCHA → price shows as null. |
| **Email requires config** | `email_config.py` must be filled manually. Alerts still save to DB. |
| **Prophet accuracy** | MAE ~₹67,525 on multi-product data. Linear Regression always wins. |
| **Price history depth** | Analytics gets richer with every repeated search. Forecast fills gaps on first search. |
| **Festival dates** | Some dates (Diwali, Navratri, Onam) shift yearly. Fixed MM-DD approximations used. |
| **No user accounts** | Alerts by email only — no login system. |
| **Dev server only** | Production deployment needs Gunicorn + Nginx. |

---

## Current State of the Project

**Version**: v8 (Real Data Analytics + Forecast-Powered Buy Intelligence)
**Status**: Fully functional and running
**Server**: Flask dev server on `http://localhost:5000`
**Model cache**: `model_cache.pkl` (v2-festival, 14-feature Linear Regression + Prophet)
**AI model**: Groq `llama-3.3-70b-versatile`

### What works end-to-end

- Amazon price scraping (reliable)
- Flipkart scraping (3-strategy, works when not rate-limited)
- 3x cross-validation between platforms
- 14-feature festival-aware ML model
- **90-day ML forecast** with festival-adjusted sale-day prices
- **Date Advice box** — specific buy/wait date, projected sale price, extra saving
- **Active Event Banner** — gradient when any sale is currently live
- **Upcoming Events strip** — next 5 sales in 90 days as scrollable pills
- **Chart sale-day markers** — star markers on forecast dates in sale window
- **Groq AI analysis** — Llama 3.3 70B, smart summary, confidence, best-time, risk note
- **Real data analytics** — all metrics from actual scraped prices
- **Forecast-powered Buy Intelligence** — best month, max savings, price dips from ML forecast
- **Monthly Price Trend** — actual months (purple) + forecast months (blue) in same chart
- **Analytics provenance badge** — data source and record count always shown
- Price alert form saves to DB
- Background scheduler every 6 hours
- Email alerts fire when price drops (requires email_config.py)
- Auto cache invalidation on feature upgrade
- Responsive on mobile and tablet
- Graceful degradation at every layer

### What needs manual action

- **Email**: Fill `email_config.py` with Gmail App Password
- **Flipkart**: May return "Unavailable" due to bot protection (not a code bug)

### UI Layout (v8)

```
[Hero + Search Bar]
       ↓ (after search)
[Live Prices Card]  [Prediction + Groq Smart Summary + Date Advice]
       ↓
[Groq AI Analysis Card — Category · Confidence · Best Time · Risk Note]
       ↓
[Upcoming Events Strip — horizontal scrollable pills]
       ↓
[Price Trend Chart — 90-day forecast + sale-day star markers]
       ↓
[Analytics Header + Real Data Provenance Badge]
[Price Statistics | Deal Score Ring | Buy Intelligence]
       ↓
[Monthly Price Trend — purple actual + blue ML forecast + amber festival]
       ↓
[Price Alert Form]
       ↓
[Model Performance — Linear MAE vs Prophet MAE]
       ↓
[Footer]
```

---

## Version Change Log

| Version | Key Changes |
|---|---|
| **v1** | Basic Flask app, manual price input, simple prediction |
| **v2** | Live scraping (Amazon + Flipkart), SQLite DB, ML training on CSV data |
| **v3** | Frontend redesign — premium white UI, Chart.js price trend chart |
| **v4** | Analytics dashboard — deal score ring, price statistics, buy intelligence |
| **v5** | Clean white redesign — removed purple backgrounds, polished UI |
| **v6** | Festival Intelligence — `festivals.py`, 7 ML festival features, date-advice box, active event banner, upcoming events strip, sale-day chart markers |
| **v7** | Groq AI Integration — `groq_client.py`, Llama 3 (then 3.3) 70B, smart summary, confidence meter, category detection, 90-day forecast (extended from 14 days) |
| **v8** | Real Data Analytics — `get_full_history()`, `_build_real_history()`, `_compute_analytics()` enriched with forecast, analytics provenance badge, Monthly Trend shows actual+forecast months, Buy Intelligence powered by ML forecast, Groq model fixed (llama3-70b-8192 decommissioned → llama-3.3-70b-versatile) |

---

*Built for smart Indian shoppers. © 2025 BargainBot.*
