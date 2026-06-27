# -*- coding: utf-8 -*-
"""
BargainBot - groq_client.py
Calls the Groq REST API directly (no SDK) to generate AI-powered
shopping analysis and recommendations.

Setup:
  1. Get your free API key from https://console.groq.com
  2. Replace the placeholder below with your actual key
  3. Restart the app
"""

import requests
import json
import os

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
GROQ_API_KEY = "Drop your api key "
GROQ_API_URL = "https://api.groq.com/openai/v1/chat/completions"
GROQ_MODEL   = "llama-3.3-70b-versatile"

# ---------------------------------------------------------------------------
# Startup validation
# ---------------------------------------------------------------------------
if GROQ_API_KEY == "paste_the_actual_api_key_here":
    print("⚠️  WARNING: Groq API key not set in groq_client.py")
    print("    AI analysis features will be disabled.")
    print("    All other BargainBot features work normally.")


def is_groq_configured() -> bool:
    """Returns True if a real Groq API key has been set."""
    return (
        GROQ_API_KEY != "paste_the_actual_api_key_here"
        and len(GROQ_API_KEY) > 20
    )


# ---------------------------------------------------------------------------
# Helper: build prompt context strings
# ---------------------------------------------------------------------------
def build_price_history_summary(history: list, current_price: int) -> str:
    """
    Converts DB price history to a short human-readable string for
    inclusion in the Groq prompt.

    Returns "No scraped price history yet..." if history is empty.
    """
    if not history:
        return "No scraped price history yet — first search for this product."

    prices = [h["price"] for h in history if h.get("price")]
    if not prices:
        return "No price history available."

    oldest  = prices[0]
    highest = max(prices)

    if prices[-1] < prices[0]:
        trend = "declining"
    elif prices[-1] > prices[0]:
        trend = "rising"
    else:
        trend = "stable"

    return (
        f"Price over last {len(prices)} records: "
        f"started at ₹{oldest:,}, peaked at ₹{highest:,}, "
        f"dropped to current ₹{current_price:,}. Trend: {trend}."
    )


def build_forecast_summary(forecast: list) -> str:
    """
    Converts the 3-month forecast list to a short string for the prompt.
    Highlights sale-day dips by name.

    Returns "No forecast data available." if forecast is empty.
    """
    if not forecast:
        return "No forecast data available."

    price_tuples = [
        (f["price"], f["date"], f.get("event_name"))
        for f in forecast
        if f.get("price") is not None
    ]
    if not price_tuples:
        return "No forecast available."

    lowest  = min(price_tuples, key=lambda x: x[0])
    highest = max(price_tuples, key=lambda x: x[0])

    low_str = f"₹{lowest[0]:,} on {lowest[1]}"
    if lowest[2]:
        low_str += f" ({lowest[2]})"

    return (
        f"3-month forecast: lowest point {low_str}, "
        f"highest point ₹{highest[0]:,} on {highest[1]}."
    )


# ---------------------------------------------------------------------------
# Main API call
# ---------------------------------------------------------------------------
def get_groq_analysis(
    product_name: str,
    current_price: int,
    predicted_price: int,
    days_to_wait: int,
    savings: int,
    verdict: str,
    trust: str,
    festival_context: str,
    upcoming_events: list,
    active_event: dict,
    price_history_summary: str,
    analytics: dict,
    forecast_summary: str,
) -> dict | None:
    """
    Calls Groq LLM and returns a dict with AI analysis fields.

    Returns
    -------
    dict with keys:
        category, category_advice, analysis_paragraph,
        smart_summary, confidence, confidence_reason,
        best_time_to_buy, risk_note, groq_verdict_text

    Returns None on any error — never crashes the search flow.
    """
    if not is_groq_configured():
        return None

    # ---- Build context strings ----
    active_str = (
        f"ACTIVE SALE RIGHT NOW: {active_event['name']} "
        f"({active_event['discount_pct']}% off, ends {active_event['sale_ends']})"
        if active_event else "No active sale right now"
    )

    upcoming_str = "\n".join([
        f"- {e['name']}: {e['days_away']} days away "
        f"({e['discount_pct']}% off expected, starts {e['sale_starts']})"
        for e in (upcoming_events or [])[:5]
    ]) or "No major sales in next 90 days"

    # ---- Safe analytics extraction ----
    ath     = analytics.get("all_time_high", "unknown")
    atl     = analytics.get("all_time_low", "unknown")
    avg_pr  = analytics.get("avg_price", analytics.get("avg_24m", "unknown"))
    deal_sc = analytics.get("deal_score", "unknown")
    best_mo = analytics.get("best_month", "unknown")
    drops   = analytics.get("price_drops", analytics.get("drop_count", "unknown"))
    avg_drp = analytics.get("avg_drop_pct", analytics.get("avg_drop", "unknown"))

    def fmt(v):
        try:
            return f"{int(v):,}"
        except Exception:
            return str(v)

    # ---- System prompt ----
    system_prompt = (
        "You are BargainBot's AI shopping advisor for Indian e-commerce. "
        "You analyze price data and give smart, specific, honest advice to Indian shoppers.\n\n"
        "You speak directly to the shopper in plain English (not formal). "
        "You know Indian shopping patterns, festival sales, and e-commerce pricing strategies deeply. "
        "You always give a specific recommendation — never vague answers. "
        "You understand that Indian shoppers are price-sensitive and value getting the best deal at the right time.\n\n"
        "Always respond with valid JSON only. No markdown. No explanation outside the JSON. "
        "No backticks. Just the raw JSON object."
    )

    # ---- User prompt ----
    user_prompt = f"""Analyze this product and give shopping advice.

PRODUCT: {product_name}
CURRENT PRICE: ₹{current_price:,}
ML PREDICTED PRICE (14 days): ₹{predicted_price:,}
PREDICTED SAVINGS: ₹{savings:,}
DAYS TO PREDICTED LOW: {days_to_wait}
ML VERDICT: {verdict}
PRICE TRUST LABEL: {trust}

PRICE ANALYTICS:
- All-time high: ₹{fmt(ath)}
- All-time low: ₹{fmt(atl)}
- 24-month average: ₹{fmt(avg_pr)}
- Deal score (0-100): {deal_sc}
- Best month to buy historically: {best_mo}
- Number of price drops in 24 months: {drops}
- Average drop size: {avg_drp}%

FESTIVAL & SALE CONTEXT:
{active_str}

UPCOMING SALES:
{upcoming_str}

PRICE HISTORY SUMMARY: {price_history_summary}

FORECAST SUMMARY: {forecast_summary}

Respond with this exact JSON structure:
{{
    "category": "detect the product category from the name — one of: Smartphone, Laptop, Tablet, TV, Audio, Appliance, Camera, Wearable, Gaming, Fashion, Grocery, Other",
    "category_advice": "1-2 sentences of advice specific to THIS product category in India. E.g. for smartphones: mention typical launch cycle and when to buy. For TVs: mention festival season is the best time. Be specific and practical.",
    "analysis_paragraph": "3-4 sentences analyzing this specific product's price situation. Mention the current price vs average, whether it's a good deal right now, what the ML model predicts, and any festival context. Use ₹ for prices. Sound like a smart friend giving advice, not a corporate bot.",
    "smart_summary": "ONE punchy sentence (max 15 words) that is the headline advice. E.g. 'Great time to buy — price is 15% below average and dropping.' or 'Wait 18 days for Prime Day — save ₹31,465 extra.' Be specific with numbers.",
    "confidence": "integer 0-100 — how confident you are in the recommendation. Base this on: trust label (stable=high, flash_sale=low), deal score (>75=high), days to wait (0=high, >14=lower), active sale (high), upcoming sale soon (medium-high)",
    "confidence_reason": "1 sentence explaining why you gave this confidence score",
    "best_time_to_buy": "specific date range or event advice. E.g. 'Buy between 12-17 July during Amazon Prime Day for the best price' or 'Buy in the next 3 days before price recovers' or 'Wait until October for Big Billion Days if you can hold off 3 months'",
    "risk_note": "1 sentence about the main risk in waiting or buying now. E.g. 'Risk: Flash sales end without notice — if you need it urgently, buy now.' or 'Risk: Waiting 3 months means missing 3 months of use.' Be honest.",
    "groq_verdict_text": "2-3 sentences expanding on the ML verdict ({verdict}). Explain in human terms what this means for the shopper right now, referencing the specific price numbers and festival context."
}}"""

    payload = {
        "model":       GROQ_MODEL,
        "messages":    [
            {"role": "system", "content": system_prompt},
            {"role": "user",   "content": user_prompt},
        ],
        "temperature": 0.3,
        "max_tokens":  1024,
        "stream":      False,
    }

    headers = {
        "Authorization": f"Bearer {GROQ_API_KEY}",
        "Content-Type":  "application/json",
    }

    try:
        response = requests.post(
            GROQ_API_URL,
            headers=headers,
            json=payload,
            timeout=15,
        )
        response.raise_for_status()
        data    = response.json()
        content = data["choices"][0]["message"]["content"]

        # Strip any accidental markdown backticks
        content = content.strip()
        if content.startswith("```"):
            parts = content.split("```")
            content = parts[1] if len(parts) > 1 else content
            if content.lower().startswith("json"):
                content = content[4:]
        content = content.strip()

        result = json.loads(content)

        # Validate required keys — fill missing ones with safe fallback
        required_keys = [
            "category", "category_advice", "analysis_paragraph",
            "smart_summary", "confidence", "confidence_reason",
            "best_time_to_buy", "risk_note", "groq_verdict_text",
        ]
        for key in required_keys:
            if key not in result:
                result[key] = "Analysis unavailable"

        # Ensure confidence is an integer
        try:
            result["confidence"] = int(result["confidence"])
        except Exception:
            result["confidence"] = 70

        print(f"[Groq] ✅ Analysis ready — category: {result.get('category')}, "
              f"confidence: {result.get('confidence')}%")
        return result

    except requests.exceptions.Timeout:
        print("[Groq] API timeout (15s) — continuing without AI analysis")
        return None
    except requests.exceptions.HTTPError as e:
        print(f"[Groq] HTTP error {e.response.status_code}: {e}")
        return None
    except json.JSONDecodeError as e:
        print(f"[Groq] JSON parse error: {e}")
        return None
    except Exception as e:
        print(f"[Groq] Unexpected error: {e}")
        return None
