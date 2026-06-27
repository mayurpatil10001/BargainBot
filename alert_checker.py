# -*- coding: utf-8 -*-
"""
BargainBot - alert_checker.py
Checks all pending price alerts and fires emails when prices drop.
"""

from database import get_all_alerts, get_latest_price, mark_alert_sent
from emailer   import send_price_alert_email
from model     import generate_suggestion


def check_and_send_alerts():
    """
    Iterates all unsent alerts. For each:
      - Fetches the latest prices from DB
      - If best price <= target, sends alert email and marks it sent.
    Each alert is wrapped in its own try/except so one failure
    does not stop the others.
    """
    alerts = get_all_alerts()
    print(f"[AlertChecker] Checking {len(alerts)} active alert(s)...")

    for alert in alerts:
        try:
            alert_id     = alert["id"]
            product_name = alert["product_name"]
            email        = alert["email"]
            target_price = int(alert["target_price"])

            # Get latest prices per platform from DB
            latest_prices = get_latest_price(product_name)
            valid_prices  = {k: v for k, v in latest_prices.items() if v is not None}

            if not valid_prices:
                print(f"[AlertChecker] No price data for '{product_name}', skipping.")
                continue

            best_price    = min(valid_prices.values())
            best_platform = min(valid_prices, key=valid_prices.get)

            print(
                f"[AlertChecker] '{product_name}': best=Rs.{best_price:,} "
                f"on {best_platform}, target=Rs.{target_price:,}"
            )

            if best_price <= target_price:
                # Generate full suggestion for email content
                suggestion = generate_suggestion(product_name)

                sent = send_price_alert_email(
                    recipient_email   = email,
                    product_name      = product_name,
                    current_price     = best_price,
                    target_price      = target_price,
                    platform          = best_platform,
                    predicted_price   = suggestion.get("predicted_price", best_price),
                    days_to_wait      = suggestion.get("days_to_wait", 1),
                    savings           = max(0, target_price - best_price),
                    why_explanation   = suggestion.get("why", "Price has dropped to your target!"),
                )

                if sent:
                    mark_alert_sent(alert_id)
                    print(
                        f"[AlertChecker] Alert {alert_id} fired and marked sent "
                        f"('{product_name}' -> {email})."
                    )
                else:
                    print(f"[AlertChecker] Email failed for alert {alert_id}, will retry later.")

        except Exception as e:
            print(f"[AlertChecker] Error processing alert {alert.get('id', '?')}: {e}")
            continue
