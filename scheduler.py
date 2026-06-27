# -*- coding: utf-8 -*-
"""
BargainBot - scheduler.py
Runs a background thread that scrapes prices every 6 hours
and checks alerts. Uses the 'schedule' library.
"""

import time
import threading
import schedule

from database      import get_all_tracked_products, save_price
from scraper       import scrape_prices
from alert_checker import check_and_send_alerts


def scrape_and_check():
    """
    Scrapes fresh prices for all tracked products,
    saves them to the DB, then fires any pending alerts.
    """
    print("[Scheduler] Running scheduled scrape + alert check...")

    products = get_all_tracked_products()
    print(f"[Scheduler] Tracking {len(products)} product(s).")

    for product in products:
        try:
            prices = scrape_prices(product)
            for platform, price in prices.items():
                if price is not None:
                    save_price(product, platform, price)
                    print(f"[Scheduler] Saved Rs.{price:,} for '{product}' on {platform}.")
        except Exception as e:
            print(f"[Scheduler] Error scraping '{product}': {e}")

    check_and_send_alerts()
    print("[Scheduler] Cycle complete.")


# Register the job to run every 6 hours
schedule.every(6).hours.do(scrape_and_check)


def start_scheduler():
    """
    Starts the scheduler in a background daemon thread.
    The thread will not block Flask from starting or running.
    """
    def run():
        print("[Scheduler] Background thread started. Runs every 6 hours.")
        while True:
            schedule.run_pending()
            time.sleep(60)

    t = threading.Thread(target=run, daemon=True)
    t.start()
    print("[Scheduler] Daemon thread launched.")
