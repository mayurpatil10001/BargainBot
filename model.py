# -*- coding: utf-8 -*-
"""
BargainBot - model.py
ML price prediction using Linear Regression + Facebook Prophet.
Reads ALL CSVs from D:\\BargainBot\\Dataset automatically.
Saves/loads trained models to model_cache.pkl.
"""

import os
import re
import glob
import pickle
import warnings
import numpy as np
import pandas as pd
from datetime import datetime, timedelta
from sklearn.linear_model import LinearRegression
from sklearn.model_selection import train_test_split
from sklearn.metrics import mean_absolute_error

warnings.filterwarnings("ignore")

# Festival helpers (import here so any file that imports model.py doesn't
# need to import festivals.py separately)
try:
    from festivals import (
        get_festival_feature,
        get_event_price_multiplier,
        get_upcoming_events,
        get_active_event,
        days_until_next_event,
    )
    _FESTIVALS_AVAILABLE = True
except Exception as _fest_import_err:
    print(f"[Model] festivals.py not available: {_fest_import_err}")
    _FESTIVALS_AVAILABLE = False
    # Define no-op fallbacks so the rest of the file never crashes
    def get_festival_feature(d):      return 0.0
    def get_event_price_multiplier(d): return 1.0
    def get_upcoming_events(**kw):     return []
    def get_active_event(**kw):        return None
    def days_until_next_event(**kw):   return None

# Version tag — increment when new features are added to _engineer_features
_CACHE_VERSION = "v2-festival"

# ---------------------------------------------------------------------------
# Forecast horizon
# ---------------------------------------------------------------------------
FORECAST_DAYS = 90   # 3-month forecast shown on the price trend chart

# ---------------------------------------------------------------------------
# Groq AI integration (optional — degrades gracefully if not configured)
# ---------------------------------------------------------------------------
try:
    from groq_client import (
        get_groq_analysis,
        build_price_history_summary,
        build_forecast_summary,
        is_groq_configured,
    )
    _GROQ_AVAILABLE = True
except Exception as _groq_import_err:
    print(f"[Model] groq_client not available: {_groq_import_err}")
    _GROQ_AVAILABLE = False
    def get_groq_analysis(*a, **kw): return None
    def build_price_history_summary(*a, **kw): return ""
    def build_forecast_summary(*a, **kw): return ""
    def is_groq_configured(): return False


# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
BASE_DIR    = os.path.dirname(os.path.abspath(__file__))
DATASET_DIR = os.path.join(BASE_DIR, "Dataset")
CACHE_PATH  = os.path.join(BASE_DIR, "model_cache.pkl")

# ---------------------------------------------------------------------------
# Global model state
# ---------------------------------------------------------------------------
_lr_model          = None
_prophet_model     = None
_model_comparison  = {
    "linear_mae":  None,
    "prophet_mae": None,
    "winner":      "Linear Regression",
}
_global_df         = None   # aggregated training dataframe


# ---------------------------------------------------------------------------
# Column mapping helpers
# ---------------------------------------------------------------------------
def _find_column(columns: list, keywords: list) -> str | None:
    """
    Case-insensitively searches column names for any keyword.
    Returns the first matching column name, or None.
    """
    for col in columns:
        col_lower = col.lower()
        for kw in keywords:
            if kw in col_lower:
                return col
    return None


def _load_csv(filepath: str) -> pd.DataFrame | None:
    """
    Loads a single CSV and maps columns to standardised names:
      product_name, actual_price, discounted_price, date
    Returns None if the file cannot produce usable price data.
    """
    try:
        df = pd.read_csv(filepath, low_memory=False, on_bad_lines="skip")
        if df.empty or len(df) < 10:
            return None

        cols = df.columns.tolist()

        # --- Map product name ---
        name_col = _find_column(cols, ["name", "title", "product"])
        if name_col is None:
            name_col = cols[0]  # fallback to first column

        # --- Map actual price ---
        actual_col = _find_column(cols, ["actual", "mrp", "original"])

        # --- Map discounted price ---
        disc_col = _find_column(
            cols,
            ["discount", "selling", "sale_price", "discounted", "price"]
        )
        # Avoid picking the same column for both
        if disc_col and disc_col == actual_col:
            remaining = [c for c in cols if "price" in c.lower() and c != actual_col]
            disc_col = remaining[0] if remaining else None

        if disc_col is None:
            disc_col = actual_col  # fall back to actual price

        if disc_col is None:
            return None   # no usable price column at all

        # --- Map date column ---
        date_col = _find_column(cols, ["date", "time", "crawl", "timestamp"])

        # Build result dataframe
        result = pd.DataFrame()

        result["product_name"] = df[name_col].astype(str).str.strip()

        # Clean price columns - strip currency symbols and commas
        def clean_price_series(series):
            def parse_price(val):
                s = str(val).strip()
                # Remove currency symbols, spaces
                s = s.replace(',', '').replace('Rs.', '').replace('INR', '').strip()
                # Remove leading/trailing dots and collapse multiple dots
                # Handle cases like '.250.00' -> try parsing from right
                parts = [p for p in s.split('.') if p.isdigit() or (p == '' )]
                # Try direct float parse first
                try:
                    # Remove non-numeric except last decimal point
                    import re as _re
                    cleaned = _re.sub(r'[^\d.]', '', s)
                    # If multiple dots, keep only digits before the last dot + last segment
                    dot_count = cleaned.count('.')
                    if dot_count > 1:
                        # Take integer part only (before first dot after removing prefix dots)
                        cleaned = cleaned.replace('.', '', dot_count - 1)
                    if cleaned and cleaned != '.':
                        return float(cleaned)
                except Exception:
                    pass
                return float('nan')

            return series.apply(parse_price)

        result["discounted_price"] = clean_price_series(df[disc_col])

        if actual_col and actual_col != disc_col:
            result["actual_price"] = clean_price_series(df[actual_col])
        else:
            result["actual_price"] = result["discounted_price"]

        # Parse or synthesise dates - always produce tz-naive timestamps
        if date_col:
            try:
                # utc=True forces all timestamps into UTC (making them tz-aware),
                # then dt.tz_localize(None) strips the tz info to make them tz-naive.
                # This safely handles mixed tz-aware and tz-naive values in the column.
                parsed = pd.to_datetime(df[date_col], errors="coerce", utc=True)
                parsed = parsed.dt.tz_localize(None)
                result["date"] = parsed

            except Exception:
                result["date"] = pd.NaT
        else:
            result["date"] = pd.NaT

        # If no valid dates parsed, synthesise 90-day daily dates
        if result["date"].isna().all():
            today    = datetime.today()
            n_rows   = len(result)
            # Repeat the 90-day date sequence across all rows
            base_dates = [
                today - timedelta(days=89 - (i % 90))
                for i in range(n_rows)
            ]
            result["date"] = pd.to_datetime(base_dates)

        # Drop rows where price or date is NaN
        result = result.dropna(subset=["discounted_price", "date"])

        # Sanity-check: prices should be > 0 and reasonable
        result = result[
            (result["discounted_price"] > 0) &
            (result["discounted_price"] < 1_000_000) &
            (result["actual_price"]    > 0)
        ]

        if len(result) < 10:
            return None

        return result

    except Exception as e:
        print(f"[Model] Error loading {os.path.basename(filepath)}: {e}")
        return None


# ---------------------------------------------------------------------------
# Feature engineering
# ---------------------------------------------------------------------------
def _engineer_features(df: pd.DataFrame) -> pd.DataFrame:
    """Adds derived columns needed by the Linear Regression model."""
    df = df.copy()

    # Ensure all dates are tz-naive so sorting doesn't fail
    if hasattr(df["date"].dtype, 'tz') and df["date"].dtype.tz is not None:
        df["date"] = df["date"].dt.tz_localize(None)
    # Also handle object-dtype dates that may be mixed tz
    try:
        df["date"] = pd.to_datetime(df["date"], errors="coerce", utc=False)
        if hasattr(df["date"].dt, 'tz') and df["date"].dt.tz is not None:
            df["date"] = df["date"].dt.tz_localize(None)
    except Exception:
        pass

    df = df.sort_values("date").reset_index(drop=True)

    df["day_of_week"]      = df["date"].dt.dayofweek
    df["month"]            = df["date"].dt.month
    df["days_since_start"] = (df["date"] - df["date"].min()).dt.days
    df["rolling_avg_7d"]   = df["discounted_price"].rolling(7, min_periods=1).mean()
    df["price_volatility"] = df["discounted_price"].rolling(7, min_periods=1).std().fillna(0)
    df["discount_pct"]     = (
        (df["actual_price"] - df["discounted_price"]) /
        df["actual_price"].replace(0, np.nan) * 100
    ).fillna(0)
    df["is_festival_month"] = df["month"].apply(lambda m: 1 if m in [7, 10, 11] else 0)

    # --- Festival features (new in v2) ---
    df["festival_score"]      = df["date"].apply(get_festival_feature)
    df["event_multiplier"]    = df["date"].apply(get_event_price_multiplier)
    df["is_prime_day_window"] = df["date"].apply(
        lambda d: 1 if (d.month == 7 and 12 <= d.day <= 20) else 0)
    df["is_big_billion_window"] = df["date"].apply(
        lambda d: 1 if (d.month == 10 and 4 <= d.day <= 12) else 0)
    df["is_diwali_window"] = df["date"].apply(
        lambda d: 1 if (d.month == 10 and 10 <= d.day <= 30) else 0)
    df["is_republic_day_window"] = df["date"].apply(
        lambda d: 1 if (d.month == 1 and 20 <= d.day <= 31) else 0)
    df["is_year_end_window"] = df["date"].apply(
        lambda d: 1 if (d.month == 12 and d.day >= 15) else 0)

    return df


# ---------------------------------------------------------------------------
# Model training
# ---------------------------------------------------------------------------
FEATURE_COLS = [
    "day_of_week", "month", "days_since_start",
    "rolling_avg_7d", "price_volatility", "discount_pct",
    "is_festival_month",
    # v2 festival features
    "festival_score", "event_multiplier",
    "is_prime_day_window", "is_big_billion_window",
    "is_diwali_window", "is_republic_day_window",
    "is_year_end_window",
]


def _train_linear_regression(df: pd.DataFrame):
    """Trains a Linear Regression model and returns (model, mae)."""
    df = _engineer_features(df)
    df = df.dropna(subset=FEATURE_COLS + ["discounted_price"])

    X = df[FEATURE_COLS].values
    y = df["discounted_price"].values

    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.20, random_state=42, shuffle=False
    )

    model = LinearRegression()
    model.fit(X_train, y_train)

    preds = model.predict(X_test)
    mae   = float(mean_absolute_error(y_test, preds))

    print(f"[Model] Linear Regression MAE: Rs.{mae:.2f}")
    return model, mae


def _train_prophet(df: pd.DataFrame):
    """Trains a Prophet model and returns (model, mae). Returns (None, inf) on failure."""
    try:
        from prophet import Prophet  # lazy import so app starts even if not installed

        # Engineer features first (adds festival_score, event_multiplier, etc.)
        df = _engineer_features(df)

        prophet_df = (
            df[["date", "discounted_price", "festival_score", "event_multiplier"]]
            .rename(columns={"date": "ds", "discounted_price": "y"})
            .dropna(subset=["ds", "y"])
            .sort_values("ds")
        )


        if len(prophet_df) < 30:
            print("[Model] Not enough rows for Prophet training.")
            return None, float("inf")

        split_idx = int(len(prophet_df) * 0.80)
        train_df  = prophet_df.iloc[:split_idx]
        test_df   = prophet_df.iloc[split_idx:]

        m = Prophet(
            weekly_seasonality=True,
            yearly_seasonality=True,
            daily_seasonality=False,
            interval_width=0.80,
        )
        m.add_regressor("festival_score")
        m.add_regressor("event_multiplier")
        m.fit(train_df[["ds", "y", "festival_score", "event_multiplier"]])

        future = m.make_future_dataframe(periods=len(test_df), freq="D")
        # Add regressor columns to future frame
        future["festival_score"]   = future["ds"].apply(
            lambda d: get_festival_feature(d.date()))
        future["event_multiplier"] = future["ds"].apply(
            lambda d: get_event_price_multiplier(d.date()))
        forecast = m.predict(future)

        test_preds = forecast.iloc[-len(test_df):]["yhat"].values
        mae = float(mean_absolute_error(test_df["y"].values, test_preds))

        print(f"[Model] Prophet MAE: Rs.{mae:.2f}")
        return m, mae

    except Exception as e:
        print(f"[Model] Prophet training failed: {e}")
        return None, float("inf")


# ---------------------------------------------------------------------------
# Public: train_models()
# ---------------------------------------------------------------------------
def train_models():
    """
    Entry point called by app.py on startup.
    1. Checks model_cache.pkl - loads if present.
    2. Otherwise loads all CSVs, engineers features, trains both models,
       compares MAEs, saves winner + both models to cache.
    """
    global _lr_model, _prophet_model, _model_comparison, _global_df

    # Load from cache if it exists — but only if version matches
    if os.path.exists(CACHE_PATH):
        try:
            with open(CACHE_PATH, "rb") as f:
                cache = pickle.load(f)
            cached_version = cache.get("version", "v1")
            if cached_version != _CACHE_VERSION:
                print(f"[Model] Cache version mismatch ({cached_version} vs {_CACHE_VERSION}). "
                      f"Invalidating cache and retraining with festival features...")
                os.remove(CACHE_PATH)
            else:
                _lr_model         = cache.get("lr_model")
                _prophet_model    = cache.get("prophet_model")
                _model_comparison = cache.get("model_comparison", _model_comparison)
                _global_df        = cache.get("global_df")
                print(f"[Model] Loaded from cache (version {cached_version}). "
                      f"Winner: {_model_comparison['winner']}")
                return
        except Exception as e:
            print(f"[Model] Cache load failed ({e}), retraining...")

    # Load and merge all CSVs
    csv_files = glob.glob(os.path.join(DATASET_DIR, "*.csv"))
    print(f"[Model] Found {len(csv_files)} CSV files in {DATASET_DIR}")

    frames = []
    for filepath in csv_files:
        fname = os.path.basename(filepath)
        print(f"[Model] Loading: {fname}")
        df_part = _load_csv(filepath)
        if df_part is not None:
            frames.append(df_part)
            print(f"[Model]   -> {len(df_part):,} usable rows")
        else:
            print(f"[Model]   -> Skipped (no usable data)")

    if not frames:
        print("[Model] No usable data found. Models will use fallback estimates.")
        return

    _global_df = pd.concat(frames, ignore_index=True)

    # Normalize all dates to tz-naive (some CSVs may parse with timezone info)
    try:
        dates = pd.to_datetime(_global_df["date"], errors="coerce")
        # If dtype has tz, strip it
        if hasattr(dates.dtype, 'tz') and dates.dtype.tz is not None:
            dates = dates.dt.tz_localize(None)
        elif dates.dtype == object:
            # Mixed types - convert each element
            def _strip_tz(d):
                try:
                    ts = pd.Timestamp(d)
                    return ts.tz_localize(None) if ts.tzinfo is not None else ts
                except Exception:
                    return pd.NaT
            dates = dates.apply(_strip_tz)
        _global_df["date"] = dates
    except Exception as e:
        print(f"[Model] Date tz normalization warning: {e}")

    print(f"[Model] Total training rows: {len(_global_df):,}")

    # Train Linear Regression
    lr_model, lr_mae = _train_linear_regression(_global_df)


    # Train Prophet
    prophet_model, prophet_mae = _train_prophet(_global_df)

    # Compare and pick winner
    if prophet_mae < lr_mae and prophet_model is not None:
        winner = "Prophet"
    else:
        winner = "Linear Regression"

    _lr_model      = lr_model
    _prophet_model = prophet_model
    _model_comparison = {
        "linear_mae":  round(lr_mae, 2),
        "prophet_mae": round(prophet_mae, 2) if prophet_mae != float("inf") else None,
        "winner":      winner,
    }

    print(f"[Model] Winner: {winner}")

    # Save to cache with version tag
    try:
        with open(CACHE_PATH, "wb") as f:
            pickle.dump(
                {
                    "version":          _CACHE_VERSION,
                    "lr_model":         _lr_model,
                    "prophet_model":    _prophet_model,
                    "model_comparison": _model_comparison,
                    "global_df":        _global_df,
                },
                f,
            )
        print(f"[Model] Cache saved to {CACHE_PATH} (version {_CACHE_VERSION})")
    except Exception as e:
        print(f"[Model] Cache save failed: {e}")


# ---------------------------------------------------------------------------
# Historical price curve generator (for chart display)
# ---------------------------------------------------------------------------
def _build_real_history(product_name: str, current_price: float) -> tuple:
    """
    Builds historical price list and analytics from REAL scraped DB data.

    Returns
    -------
    (hist_prices, data_source, data_points)
        hist_prices  : list of {date, price} dicts — real scraped data
        data_source  : "real" | "limited" | "none"
        data_points  : int — number of real records found
    """
    from database import get_full_history

    raw_rows = get_full_history(product_name)

    if not raw_rows:
        # No real data at all — return current price as single point
        today_str = datetime.today().strftime("%Y-%m-%d")
        return (
            [{"date": today_str, "price": int(current_price)}],
            "none",
            0,
        )

    # Convert DB rows to {date, price} — take the lowest platform price per timestamp
    # Group by date (YYYY-MM-DD) and keep the minimum price seen that day
    from collections import defaultdict
    daily: dict = defaultdict(list)
    for row in raw_rows:
        ts    = str(row.get("timestamp", ""))[:10]   # YYYY-MM-DD
        price = row.get("price")
        if ts and price:
            daily[ts].append(int(price))

    hist_prices = [
        {"date": d, "price": min(prices)}
        for d, prices in sorted(daily.items())
    ]

    # Always ensure current price is the last data point today
    today_str = datetime.today().strftime("%Y-%m-%d")
    if hist_prices and hist_prices[-1]["date"] != today_str:
        hist_prices.append({"date": today_str, "price": int(current_price)})
    elif not hist_prices:
        hist_prices = [{"date": today_str, "price": int(current_price)}]

    n = len(raw_rows)
    data_source = "real" if n >= 5 else "limited"
    return hist_prices, data_source, n



# ---------------------------------------------------------------------------
# Analytics engine
# ---------------------------------------------------------------------------
def _compute_analytics(
    historical_prices: list,
    current_price: float,
    data_source: str = "none",
    data_points: int = 0,
    forecast: list = None,
) -> dict:
    """
    Derives analytics from real scraped prices + ML forecast.

    - historical_prices : real DB scrape records {date, price}
    - forecast          : 90-day ML forecast {date, price, is_sale_day, event_name}
    - data_source       : 'real' | 'limited' | 'none'
    - data_points       : raw DB records used

    Buy Intelligence and Monthly Trend are enriched with forecast data so
    the analytics are always useful even on first search.
    """
    import calendar
    from collections import defaultdict

    forecast = forecast or []

    # ---- Price stats from real scraped data ----
    if historical_prices:
        prices        = [p["price"] for p in historical_prices]
        all_time_high = max(prices)
        all_time_low  = min(prices)
        avg_price     = int(sum(prices) / len(prices))
        vs_avg_pct    = round((current_price - avg_price) / avg_price * 100, 1)
    else:
        prices        = [int(current_price)]
        all_time_high = int(current_price)
        all_time_low  = int(current_price)
        avg_price     = int(current_price)
        vs_avg_pct    = 0.0

    # Deal score: based on real range if available, else use forecast range
    fc_prices  = [f["price"] for f in forecast if f.get("price")]
    all_prices = prices + fc_prices  # combined for range calc
    combined_high = max(all_prices) if all_prices else int(current_price)
    combined_low  = min(all_prices) if all_prices else int(current_price)
    price_range   = combined_high - combined_low

    if price_range > 0:
        deal_score = int(100 * (1 - (current_price - combined_low) / price_range))
    else:
        deal_score = 75 if current_price <= avg_price else max(20, int(75 - (current_price - avg_price) / avg_price * 200))
    deal_score = max(0, min(100, deal_score))

    # ---- Price drops from real scraped history ----
    drops          = 0
    total_drop_pct = 0.0
    for i in range(1, len(prices)):
        chg = (prices[i] - prices[i - 1]) / prices[i - 1]
        if chg < -0.05:
            drops          += 1
            total_drop_pct += abs(chg)

    # Also count predicted dips from forecast (> 3% drop day-on-day)
    fc_dips      = 0
    fc_dip_total = 0.0
    for i in range(1, len(fc_prices)):
        chg = (fc_prices[i] - fc_prices[i - 1]) / fc_prices[i - 1]
        if chg < -0.03:
            fc_dips      += 1
            fc_dip_total += abs(chg)

    avg_drop_pct = round(total_drop_pct / drops * 100, 1) if drops > 0 else 0.0

    # ---- Price trend (from real data) ----
    if len(prices) >= 6:
        recent   = sum(prices[-3:]) / 3
        previous = sum(prices[-6:-3]) / 3
        delta    = (recent - previous) / previous * 100
        trend    = "down" if delta < -3 else ("up" if delta > 3 else "stable")
    elif len(prices) >= 2:
        delta = (prices[-1] - prices[0]) / prices[0] * 100
        trend = "down" if delta < -3 else ("up" if delta > 3 else "stable")
    elif fc_prices:
        # Use forecast trend direction when no real history
        delta = (fc_prices[-1] - fc_prices[0]) / fc_prices[0] * 100
        trend = "down" if delta < -2 else ("up" if delta > 2 else "stable")
    else:
        trend = "stable"

    # ---- Monthly series: real scraped months ----
    hist_monthly_map: dict = defaultdict(list)
    for row in (historical_prices or []):
        key = row["date"][:7]
        hist_monthly_map[key].append(row["price"])
    hist_monthly_data = [
        {"month": k, "price": int(sum(v) / len(v)), "type": "actual"}
        for k, v in sorted(hist_monthly_map.items())
    ]

    # ---- Monthly series: forecast months (ML predictions) ----
    fc_monthly_map: dict = defaultdict(list)
    for row in forecast:
        key = row["date"][:7]
        fc_monthly_map[key].append(row["price"])
    fc_monthly_data = [
        {"month": k, "price": int(sum(v) / len(v)), "type": "forecast"}
        for k, v in sorted(fc_monthly_map.items())
    ]

    # Merge: if a month has both real and forecast, prefer real
    hist_months = {d["month"] for d in hist_monthly_data}
    fc_monthly_data_filtered = [d for d in fc_monthly_data if d["month"] not in hist_months]

    # Combined chart data: actual months first, then future forecast months
    monthly_data = sorted(
        hist_monthly_data + fc_monthly_data_filtered,
        key=lambda x: x["month"]
    )

    # ---- Best month to buy ----
    # Use forecast monthly data (future months) to find the cheapest predicted month
    if fc_monthly_data:
        best_fc = min(fc_monthly_data, key=lambda x: x["price"])
        # Parse month name from YYYY-MM
        yr, mo = best_fc["month"].split("-")
        best_month = f"{calendar.month_name[int(mo)]} (predicted)"
    elif hist_monthly_data:
        # Fall back to real historical data
        best_hist = min(hist_monthly_data, key=lambda x: x["price"])
        yr, mo    = best_hist["month"].split("-")
        best_month = calendar.month_name[int(mo)]
    else:
        best_month = "—"

    # ---- Max possible savings ----
    # Use the LOWEST forecast price vs current — always actionable
    if fc_prices:
        forecast_low    = min(fc_prices)
        max_savings     = max(0, int(current_price - forecast_low))
        max_savings_pct = round(max_savings / current_price * 100, 1) if current_price > 0 else 0
        savings_note    = "vs 3-month forecast low"
    elif all_time_low < current_price:
        max_savings     = max(0, int(current_price - all_time_low))
        max_savings_pct = round(max_savings / current_price * 100, 1) if current_price > 0 else 0
        savings_note    = "vs all-time low"
    else:
        max_savings     = 0
        max_savings_pct = 0.0
        savings_note    = ""

    # Total price drops = real drops + predicted dips
    total_drops     = drops + fc_dips
    all_drop_total  = total_drop_pct + fc_dip_total
    all_avg_drop    = round(all_drop_total / total_drops * 100, 1) if total_drops > 0 else 0.0

    return {
        "all_time_high":        all_time_high,
        "all_time_low":         all_time_low,
        "avg_price":            avg_price,
        "vs_avg_pct":           vs_avg_pct,
        "deal_score":           deal_score,
        "price_drops":          total_drops,
        "avg_drop_pct":         all_avg_drop,
        "trend":                trend,
        "monthly_data":         monthly_data,       # combined actual + forecast months
        "best_month":           best_month,
        "max_savings":          max_savings,
        "max_savings_pct":      max_savings_pct,
        "savings_note":         savings_note,
        "fc_dips":              fc_dips,            # predicted dips from ML
        "forecast_low":         min(fc_prices) if fc_prices else None,
        # Provenance flags
        "data_source":          data_source,
        "data_points":          data_points,
    }



# ---------------------------------------------------------------------------
# Prediction helpers
# ---------------------------------------------------------------------------
def _predict_linear(future_dates: list, base_price: float, base_date: datetime) -> list:
    """Generates price predictions for a list of future dates using Linear Regression.
    Returns a list of dicts: {date, price, is_sale_day, event_name}.
    """
    if _lr_model is None:
        results = []
        for d in future_dates:
            d_date      = d.date() if hasattr(d, 'date') else d
            multiplier  = get_event_price_multiplier(d_date)
            active      = get_active_event(on_date=d_date)
            is_sale_day = multiplier < 1.0
            adj_price   = max(1, int(round(base_price * multiplier)))
            results.append(adj_price)
        return results

    rows = []
    for d in future_dates:
        d_date     = d.date() if hasattr(d, 'date') else d
        days_since = (d - base_date).days
        rows.append({
            "day_of_week":           d.weekday(),
            "month":                 d.month,
            "days_since_start":      max(0, days_since),
            "rolling_avg_7d":        base_price,
            "price_volatility":      base_price * 0.02,
            "discount_pct":          10.0,
            "is_festival_month":     1 if d.month in [7, 10, 11] else 0,
            "festival_score":        get_festival_feature(d_date),
            "event_multiplier":      get_event_price_multiplier(d_date),
            "is_prime_day_window":   1 if (d.month == 7 and 12 <= d.day <= 20) else 0,
            "is_big_billion_window": 1 if (d.month == 10 and 4 <= d.day <= 12) else 0,
            "is_diwali_window":      1 if (d.month == 10 and 10 <= d.day <= 30) else 0,
            "is_republic_day_window":1 if (d.month == 1 and 20 <= d.day <= 31) else 0,
            "is_year_end_window":    1 if (d.month == 12 and d.day >= 15) else 0,
        })

    X     = pd.DataFrame(rows)[FEATURE_COLS].values
    preds = _lr_model.predict(X)
    return [max(1, int(round(p))) for p in preds]


def _predict_prophet_14(product_name: str, base_price: float) -> list:
    """Generates FORECAST_DAYS-day price forecast using Prophet.
    Returns enriched dicts: {date, price, is_sale_day, event_name}.
    """
    if _prophet_model is None:
        return []
    try:
        future = _prophet_model.make_future_dataframe(periods=FORECAST_DAYS, freq="D")
        future["festival_score"]   = future["ds"].apply(
            lambda d: get_festival_feature(d.date()))
        future["event_multiplier"] = future["ds"].apply(
            lambda d: get_event_price_multiplier(d.date()))
        forecast = _prophet_model.predict(future)
        tail = forecast.tail(FORECAST_DAYS)
        results = []
        for _, row in tail.iterrows():
            d_date      = row["ds"].date()
            raw_price   = max(1, int(round(row["yhat"])))
            multiplier  = get_event_price_multiplier(d_date)
            active      = get_active_event(on_date=d_date)
            is_sale_day = multiplier < 1.0
            adj_price   = max(1, int(round(raw_price * multiplier))) if is_sale_day else raw_price
            results.append({
                "date":        row["ds"].strftime("%Y-%m-%d"),
                "price":       adj_price,
                "is_sale_day": is_sale_day,
                "event_name":  active["name"] if active else None,
            })
        return results
    except Exception as e:
        print(f"[Model] Prophet forecast error: {e}")
        return []


# ---------------------------------------------------------------------------
# Public: generate_suggestion()
# ---------------------------------------------------------------------------
def generate_suggestion(product_name: str, live_prices: dict | None = None) -> dict:
    """
    Generates a full buy/wait suggestion for a product.

    Parameters
    ----------
    product_name : str
        The product to predict for.
    live_prices : dict | None
        Optional {"amazon": int|None, "flipkart": int|None} from the scraper.
        When supplied, this overrides the DB-based current_price so the
        cross-validated live price is always used.

    Returns a dict with keys:
      verdict, current_price, predicted_price, days_to_wait,
      savings, why, trust, forecast, message, historical_prices, analytics
    """
    from database import get_latest_price, get_history

    # ---- Get current price ----
    # Prefer the caller-supplied live_prices (already cross-validated by
    # scraper.py) over whatever is stored in the DB.
    if live_prices:
        valid_live = {k: v for k, v in live_prices.items() if v}
        current_price = min(valid_live.values()) if valid_live else None

    if not live_prices or not current_price:
        latest_prices = get_latest_price(product_name)
        valid_prices  = {k: v for k, v in latest_prices.items() if v}
        current_price = min(valid_prices.values()) if valid_prices else 15000

    # ---- Get price history ----
    history = get_history(product_name)

    # ---- Trust label ----
    trust = "uncertain"
    if history:
        prices_series = [r["price"] for r in history]
        timestamps    = [r["timestamp"] for r in history]

        if len(set(prices_series)) == 1:
            trust = "stable"
        else:
            try:
                latest_ts = pd.to_datetime(timestamps[-1])
                prev_ts   = pd.to_datetime(timestamps[-2]) if len(timestamps) > 1 else latest_ts
                delta     = (latest_ts - prev_ts).days
                if delta <= 3:
                    trust = "flash_sale"
                else:
                    trust = "uncertain"
            except Exception:
                trust = "uncertain"

    if len(set(r["price"] for r in history)) == 1 and len(history) >= 14:
        trust = "stable"

    # ---- Forecast (FORECAST_DAYS months) — festival-adjusted ----
    today = datetime.today()
    future_dates = [today + timedelta(days=i + 1) for i in range(FORECAST_DAYS)]

    if _model_comparison["winner"] == "Prophet" and _prophet_model is not None:
        forecast = _predict_prophet_14(product_name, current_price)
    else:
        preds = _predict_linear(future_dates, current_price, today)
        forecast = []
        for i, p in enumerate(preds):
            fd        = (today + timedelta(days=i + 1))
            d_date    = fd.date()
            multiplier = get_event_price_multiplier(d_date)
            active_ev  = get_active_event(on_date=d_date)
            is_sale    = multiplier < 1.0
            adj_price  = max(1, int(round(p * multiplier))) if is_sale else p
            forecast.append({
                "date":        fd.strftime("%Y-%m-%d"),
                "price":       adj_price,
                "is_sale_day": is_sale,
                "event_name":  active_ev["name"] if active_ev else None,
            })

    # Ensure forecast has exactly FORECAST_DAYS entries
    while len(forecast) < FORECAST_DAYS:
        next_date = (today + timedelta(days=len(forecast) + 1)).strftime("%Y-%m-%d")
        forecast.append({"date": next_date, "price": current_price,
                         "is_sale_day": False, "event_name": None})

    forecast = forecast[:FORECAST_DAYS]

    # ---- Predicted price = minimum forecast price ----
    predicted_price = min(f["price"] for f in forecast) if forecast else current_price
    savings         = max(0, current_price - predicted_price)

    # ---- Days to wait = index of minimum predicted price ----
    if forecast:
        min_idx    = min(range(len(forecast)), key=lambda i: forecast[i]["price"])
        days_to_wait = min_idx + 1
    else:
        days_to_wait = 7

    # ---- Verdict (decision rules in exact order) ----
    if savings < 500:
        verdict = "BUY_NOW"
    elif days_to_wait > 60:          # dip is > 2 months away — buy now
        verdict = "BUY_NOW"
    elif savings >= 2000 and trust != "flash_sale":
        verdict = "WAIT"
    else:
        verdict = "CONSIDER"

    # ---- Why explanation (festival-first) ----
    why = "Based on past 30-day trend, a price drop is predicted"

    # Part 7: Check festivals FIRST before any other why logic
    try:
        _active_why = get_active_event()
        _next_why   = days_until_next_event(from_date=today.date())
        if _active_why:
            why = (f"{_active_why['name']} is currently live — "
                   f"prices are ~{_active_why['discount_pct']:.0f}% lower than usual")
        elif _next_why and _next_why["days"] <= 14:
            why = (f"{_next_why['event']} is in {_next_why['days']} days "
                   f"— prices expected to drop by ~{_next_why['discount_pct']:.0f}%")
    except Exception:
        pass

    if why == "Based on past 30-day trend, a price drop is predicted":
        if history and len(history) >= 7:
            try:
                hist_df = pd.DataFrame(history)
                hist_df["timestamp"]  = pd.to_datetime(hist_df["timestamp"])
                hist_df["day_of_week"] = hist_df["timestamp"].dt.dayofweek
                weekends = hist_df[hist_df["day_of_week"].isin([5, 6])]
                if len(weekends) > 0:
                    weekend_drops = (weekends["price"].diff() < 0).sum()
                    if len(weekends) > 1 and (weekend_drops / (len(weekends) - 1)) > 0.70:
                        why = "This seller usually drops prices on weekends"
            except Exception:
                pass

    if why == "Based on past 30-day trend, a price drop is predicted":
        if today.month in [7, 10, 11]:
            why = "Prices typically fall during festival sale season"

    if why == "Based on past 30-day trend, a price drop is predicted" and history:
        try:
            if len(history) >= 90:
                why = "Price drops before a newer model launches"
        except Exception:
            pass

    # ---- Build message ----
    if verdict == "BUY_NOW":
        message = f"Buy now! The price is already at a great level - waiting won't save you much."
    elif verdict == "WAIT":
        message = (
            f"Hold off for ~{days_to_wait} days. "
            f"Our model predicts a Rs.{savings:,} drop is coming."
        )
    else:
        message = (
            f"Consider buying if you need it soon. "
            f"A small drop of Rs.{savings:,} may happen in ~{days_to_wait} days."
        )

    hist_prices, data_source, data_points = _build_real_history(product_name, current_price)
    analytics = _compute_analytics(
        hist_prices, current_price,
        data_source=data_source,
        data_points=data_points,
        forecast=forecast,
    )


    # ---- Part 4: Date advice + upcoming events ----
    date_advice    = {}
    upcoming_events_out = []
    active_event_out    = None
    try:
        import datetime as _dt_mod
        _today_date  = today.date()
        _active_ev   = get_active_event()
        _upcoming    = get_upcoming_events(from_date=_today_date, days_ahead=90)
        _next_ev     = days_until_next_event(from_date=_today_date)

        # Find lowest forecast point
        _fc_list = [f for f in forecast if f.get("price")]
        if _fc_list:
            _lowest_fc    = min(_fc_list, key=lambda x: x["price"])
            _lowest_date  = _dt_mod.date.fromisoformat(_lowest_fc["date"])
            _lowest_price = _lowest_fc["price"]
        else:
            _lowest_date  = _today_date
            _lowest_price = current_price

        if _active_ev:
            _sale_ends = _active_ev["sale_ends"]
            date_advice = {
                "action":          "BUY_NOW",
                "reason":          f"{_active_ev['name']} is live right now",
                "buy_before":      _sale_ends.strftime("%d %B %Y"),
                "buy_before_date": _sale_ends.isoformat(),
                "days_left":       (_sale_ends - _today_date).days,
                "event_name":      _active_ev["name"],
                "event_discount":  _active_ev["discount_pct"],
                "urgency":         "HIGH",
            }
        elif verdict == "BUY_NOW":
            if _next_ev and _next_ev["days"] <= 30:
                _proj_sale_price  = current_price * (1 - _next_ev["discount_pct"] / 100)
                _extra_saving     = current_price - _proj_sale_price
                if _extra_saving > 1500:
                    date_advice = {
                        "action":          "WAIT_FOR_EVENT",
                        "reason":          (f"{_next_ev['event']} is in {_next_ev['days']} days "
                                            f"\u2014 expect ~{_next_ev['discount_pct']:.0f}% off"),
                        "buy_after":       _next_ev["sale_starts"].strftime("%d %B %Y"),
                        "buy_after_date":  _next_ev["sale_starts"].isoformat(),
                        "buy_before":      (_next_ev["date"] + _dt_mod.timedelta(days=2)).strftime("%d %B %Y"),
                        "event_name":      _next_ev["event"],
                        "event_discount":  _next_ev["discount_pct"],
                        "projected_price": round(_proj_sale_price),
                        "extra_saving":    round(_extra_saving),
                        "urgency":         "MEDIUM",
                    }
                else:
                    date_advice = {
                        "action":          "BUY_NOW",
                        "reason":          "Current price is already good",
                        "buy_before":      (_today_date + _dt_mod.timedelta(days=3)).strftime("%d %B %Y"),
                        "buy_before_date": (_today_date + _dt_mod.timedelta(days=3)).isoformat(),
                        "urgency":         "LOW",
                    }
            else:
                date_advice = {
                    "action":          "BUY_NOW",
                    "reason":          "No major sale in the next 30 days",
                    "buy_before":      (_today_date + _dt_mod.timedelta(days=7)).strftime("%d %B %Y"),
                    "buy_before_date": (_today_date + _dt_mod.timedelta(days=7)).isoformat(),
                    "urgency":         "LOW",
                }
        elif verdict == "WAIT":
            if _next_ev and _next_ev["days"] <= 45:
                _proj_sale_price = current_price * (1 - _next_ev["discount_pct"] / 100)
                date_advice = {
                    "action":            "WAIT_FOR_EVENT",
                    "reason":            (f"Wait for {_next_ev['event']} "
                                          f"({_next_ev['days']} days away) "
                                          f"\u2014 expect ~{_next_ev['discount_pct']:.0f}% off"),
                    "buy_after":         _next_ev["sale_starts"].strftime("%d %B %Y"),
                    "buy_after_date":    _next_ev["sale_starts"].isoformat(),
                    "buy_before":        _next_ev["date"].strftime("%d %B %Y"),
                    "buy_before_date":   _next_ev["date"].isoformat(),
                    "event_name":        _next_ev["event"],
                    "event_discount":    _next_ev["discount_pct"],
                    "projected_price":   round(_proj_sale_price),
                    "extra_saving":      round(current_price - _proj_sale_price),
                    "days_to_sale_start": max(0, _next_ev["days"] - (_next_ev["date"] - _next_ev["sale_starts"]).days),
                    "urgency":           "MEDIUM",
                }
            else:
                date_advice = {
                    "action":        "WAIT_FOR_DIP",
                    "reason":        f"ML model predicts lowest price around {_lowest_date.strftime('%d %B')}",
                    "buy_after":     _lowest_date.strftime("%d %B %Y"),
                    "buy_after_date":_lowest_date.isoformat(),
                    "predicted_low": _lowest_price,
                    "urgency":       "LOW",
                }
        else:  # CONSIDER
            if _next_ev and _next_ev["days"] <= 21:
                _proj_sale_price = current_price * (1 - _next_ev["discount_pct"] / 100)
                date_advice = {
                    "action":          "WAIT_FOR_EVENT",
                    "reason":          f"{_next_ev['event']} starts in {_next_ev['days']} days",
                    "buy_after":       _next_ev["sale_starts"].strftime("%d %B %Y"),
                    "buy_after_date":  _next_ev["sale_starts"].isoformat(),
                    "event_name":      _next_ev["event"],
                    "event_discount":  _next_ev["discount_pct"],
                    "projected_price": round(_proj_sale_price),
                    "urgency":         "MEDIUM",
                }
            else:
                date_advice = {
                    "action":  "CONSIDER",
                    "reason":  "Small saving predicted \u2014 set an alert",
                    "urgency": "LOW",
                }

        # Build serialisable upcoming events (next 5)
        upcoming_events_out = [
            {
                "name":         e["name"],
                "date":         e["date"].strftime("%d %B %Y"),
                "days_away":    e["days_away"],
                "discount_pct": e["discount_pct"],
                "sale_starts":  e["sale_starts"].strftime("%d %B %Y"),
                "platforms":    e["platforms"],
            }
            for e in _upcoming[:5]
        ]

        if _active_ev:
            active_event_out = {
                "name":         _active_ev["name"],
                "discount_pct": _active_ev["discount_pct"],
                "sale_ends":    _active_ev["sale_ends"].strftime("%d %B %Y"),
            }

    except Exception as _fest_err:
        print(f"[Model] Festival date_advice error (non-fatal): {_fest_err}")

    # === GROQ AI ANALYSIS (Part 2 — v7 upgrade) ===
    groq_analysis = None
    try:
        if _GROQ_AVAILABLE and is_groq_configured():
            from database import get_history as _get_history_for_groq
            history_for_groq      = _get_history_for_groq(product_name)
            price_history_summary = build_price_history_summary(
                history_for_groq, int(current_price)
            )
            forecast_summary_str  = build_forecast_summary(forecast)

            groq_analysis = get_groq_analysis(
                product_name          = product_name,
                current_price         = int(current_price),
                predicted_price       = int(predicted_price),
                days_to_wait          = int(days_to_wait),
                savings               = int(savings),
                verdict               = verdict,
                trust                 = trust,
                festival_context      = why,
                upcoming_events       = upcoming_events_out,
                active_event          = active_event_out,
                price_history_summary = price_history_summary,
                analytics             = analytics,
                forecast_summary      = forecast_summary_str,
            )

            # Upgrade why + message with Groq's richer text (fallback to ML text)
            if groq_analysis:
                why     = groq_analysis.get("groq_verdict_text", why)
                message = groq_analysis.get("analysis_paragraph", message)
    except Exception as _groq_err:
        print(f"[Groq] Integration error (non-fatal): {_groq_err}")
        groq_analysis = None
    # === END GROQ ===

    return {
        "verdict":           verdict,
        "current_price":     int(current_price),
        "predicted_price":   int(predicted_price),
        "days_to_wait":      int(days_to_wait),
        "savings":           int(savings),
        "why":               why,
        "trust":             trust,
        "forecast":          forecast,
        "message":           message,
        "historical_prices": hist_prices,
        "analytics":         analytics,
        # Festival keys (v6)
        "date_advice":       date_advice,
        "upcoming_events":   upcoming_events_out,
        "active_event":      active_event_out,
        # Groq AI analysis (v7 — None if API not configured or failed)
        "groq_analysis":     groq_analysis,
    }




def get_model_stats() -> dict:
    """Returns the model comparison dict for the /model-stats endpoint."""
    return {
        "linear_mae":  _model_comparison.get("linear_mae"),
        "prophet_mae": _model_comparison.get("prophet_mae"),
        "winner":      _model_comparison.get("winner", "Linear Regression"),
    }
