# -*- coding: utf-8 -*-
"""
BargainBot - app.py
Flask web application for AI-powered price comparison and prediction.
"""

import os
import sys

# Force UTF-8 output on Windows so Unicode characters in print() don't crash
if sys.stdout.encoding and sys.stdout.encoding.lower() != 'utf-8':
    sys.stdout.reconfigure(encoding='utf-8')
if sys.stderr.encoding and sys.stderr.encoding.lower() != 'utf-8':
    sys.stderr.reconfigure(encoding='utf-8')

import threading
from flask import Flask, request, jsonify, render_template

# Ensure our project root is on sys.path
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from database  import init_db, save_price, get_history, save_alert
from scraper   import scrape_prices
from model     import train_models, generate_suggestion, get_model_stats
from scheduler import start_scheduler

# ---------------------------------------------------------------------------
# Application factory
# ---------------------------------------------------------------------------
app = Flask(__name__, template_folder="templates", static_folder="static")


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@app.route("/")
def index():
    """Serves the main single-page application."""
    return render_template("index.html")


@app.route("/search", methods=["POST"])
def search():
    """
    POST /search
    Body: { "product": "<product name>" }

    Returns:
    {
      "product":    str,
      "prices":     {"amazon": int|null, "flipkart": int|null},
      "prediction": { ...generate_suggestion dict... },
      "history":    [ ...last 30 days price records... ]
    }
    """
    try:
        data         = request.get_json(force=True)
        product_name = str(data.get("product", "")).strip()

        if not product_name:
            return jsonify({"error": "Product name is required."}), 400

        # Scrape live prices
        prices = scrape_prices(product_name)

        # Save scraped prices to DB
        for platform, price in prices.items():
            if price is not None:
                try:
                    save_price(product_name, platform, price)
                except Exception as e:
                    print(f"[App] DB save error for {platform}: {e}")

        # Generate ML suggestion — pass live prices so the model uses the
        # cross-validated price, not a stale DB value.
        try:
            prediction = generate_suggestion(product_name, live_prices=prices)
        except Exception as e:
            print(f"[App] Prediction error: {e}")
            prediction = {
                "verdict":         "CONSIDER",
                "current_price":   min((v for v in prices.values() if v), default=0),
                "predicted_price": min((v for v in prices.values() if v), default=0),
                "days_to_wait":    7,
                "savings":         0,
                "why":             "Insufficient data for prediction.",
                "trust":           "uncertain",
                "forecast":        [],
                "message":         "Not enough price history to make a confident prediction.",
            }


        # Get price history
        try:
            history = get_history(product_name)
        except Exception as e:
            print(f"[App] History error: {e}")
            history = []

        return jsonify({
            "product":    product_name,
            "prices":     prices,
            "prediction": prediction,
            "history":    history,
        })

    except Exception as e:
        print(f"[App] /search error: {e}")
        return jsonify({"error": "An unexpected error occurred. Please try again."}), 500


@app.route("/set-alert", methods=["POST"])
def set_alert():
    """
    POST /set-alert
    Body: { "product": str, "email": str, "target_price": int }

    Returns: { "success": True, "message": str }
    """
    try:
        data         = request.get_json(force=True)
        product_name = str(data.get("product", "")).strip()
        email        = str(data.get("email", "")).strip()
        target_price = data.get("target_price")

        if not product_name:
            return jsonify({"error": "Product name is required."}), 400
        if not email or "@" not in email:
            return jsonify({"error": "A valid email address is required."}), 400
        if target_price is None or int(target_price) <= 0:
            return jsonify({"error": "Target price must be a positive number."}), 400

        save_alert(product_name, email, int(target_price))

        return jsonify({
            "success": True,
            "message": (
                f"Alert saved! We'll email {email} when "
                f"'{product_name}' drops below Rs.{int(target_price):,}."
            ),
        })

    except Exception as e:
        print(f"[App] /set-alert error: {e}")
        return jsonify({"error": "Failed to save alert. Please try again."}), 500


@app.route("/history", methods=["GET"])
def history():
    """
    GET /history?product=<product name>
    Returns last 30 days of price history for a product.
    """
    try:
        product_name = request.args.get("product", "").strip()
        if not product_name:
            return jsonify({"error": "Product name is required."}), 400

        records = get_history(product_name)
        return jsonify({"product": product_name, "history": records})

    except Exception as e:
        print(f"[App] /history error: {e}")
        return jsonify({"error": "Failed to retrieve history."}), 500


@app.route("/model-stats", methods=["GET"])
def model_stats():
    """
    GET /model-stats
    Returns the model accuracy comparison dict.
    """
    try:
        stats = get_model_stats()
        return jsonify(stats)
    except Exception as e:
        print(f"[App] /model-stats error: {e}")
        return jsonify({"error": "Failed to retrieve model stats."}), 500


# ---------------------------------------------------------------------------
# Startup
# ---------------------------------------------------------------------------
def startup():
    """Called once on app start: initialise DB, train models, start scheduler."""
    print("=" * 60)
    print("  BargainBot - Starting up...")
    print("=" * 60)

    print("[Startup] Initialising database...")
    init_db()

    print("[Startup] Training / loading ML models...")
    train_models()

    print("[Startup] Starting background scheduler...")
    start_scheduler()

    print("[Startup] Ready! Visit http://localhost:5000")
    print("=" * 60)


# Run startup in main thread before serving
startup()

if __name__ == "__main__":
    app.run(debug=False, host="0.0.0.0", port=5000, use_reloader=False)
