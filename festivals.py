# -*- coding: utf-8 -*-
"""
BargainBot - festivals.py
Single source of truth for Indian shopping festival calendar.
All date comparisons handle year wrap-around (MM-DD applies to
current or next year depending on whether the date has passed).
"""

import datetime

# ---------------------------------------------------------------------------
# Festival Calendar
# ---------------------------------------------------------------------------
FESTIVAL_CALENDAR = {
    # Format: "MM-DD": {"name": str, "discount_pct": float,
    #                   "type": str, "days_before": int,
    #                   "days_after": int, "platforms": list}

    # --- Amazon Events ---
    "07-15": {"name": "Amazon Prime Day",         "discount_pct": 35.0,
              "type": "platform",  "days_before": 3,  "days_after": 5,
              "platforms": ["amazon"]},
    "01-12": {"name": "Amazon Great Republic Day", "discount_pct": 25.0,
              "type": "platform",  "days_before": 5,  "days_after": 3,
              "platforms": ["amazon"]},
    "08-08": {"name": "Amazon Freedom Sale",       "discount_pct": 20.0,
              "type": "platform",  "days_before": 3,  "days_after": 2,
              "platforms": ["amazon"]},
    "12-19": {"name": "Amazon Year End Sale",      "discount_pct": 28.0,
              "type": "platform",  "days_before": 5,  "days_after": 7,
              "platforms": ["amazon"]},

    # --- Flipkart Events ---
    "10-07": {"name": "Flipkart Big Billion Days", "discount_pct": 40.0,
              "type": "platform",  "days_before": 5,  "days_after": 5,
              "platforms": ["flipkart"]},
    "01-16": {"name": "Flipkart Republic Day Sale","discount_pct": 22.0,
              "type": "platform",  "days_before": 3,  "days_after": 3,
              "platforms": ["flipkart"]},
    "05-05": {"name": "Flipkart Big Shopping Days","discount_pct": 20.0,
              "type": "platform",  "days_before": 2,  "days_after": 2,
              "platforms": ["flipkart"]},

    # --- Indian National Festivals (both platforms) ---
    "10-20": {"name": "Diwali Sale",               "discount_pct": 30.0,
              "type": "festival",  "days_before": 10, "days_after": 5,
              "platforms": ["amazon", "flipkart"]},
    "09-28": {"name": "Navratri Sale",             "discount_pct": 18.0,
              "type": "festival",  "days_before": 5,  "days_after": 3,
              "platforms": ["amazon", "flipkart"]},
    "03-25": {"name": "Holi Sale",                 "discount_pct": 15.0,
              "type": "festival",  "days_before": 3,  "days_after": 2,
              "platforms": ["amazon", "flipkart"]},
    "08-15": {"name": "Independence Day Sale",     "discount_pct": 18.0,
              "type": "national",  "days_before": 3,  "days_after": 2,
              "platforms": ["amazon", "flipkart"]},
    "01-26": {"name": "Republic Day Sale",         "discount_pct": 20.0,
              "type": "national",  "days_before": 5,  "days_after": 3,
              "platforms": ["amazon", "flipkart"]},
    "11-11": {"name": "Singles Day Sale",          "discount_pct": 22.0,
              "type": "global",    "days_before": 2,  "days_after": 2,
              "platforms": ["amazon", "flipkart"]},
    "11-29": {"name": "Black Friday Sale",         "discount_pct": 25.0,
              "type": "global",    "days_before": 3,  "days_after": 4,
              "platforms": ["amazon", "flipkart"]},
    "12-25": {"name": "Christmas Sale",            "discount_pct": 20.0,
              "type": "global",    "days_before": 5,  "days_after": 3,
              "platforms": ["amazon", "flipkart"]},
    "09-05": {"name": "Onam Sale",                 "discount_pct": 16.0,
              "type": "festival",  "days_before": 3,  "days_after": 2,
              "platforms": ["amazon", "flipkart"]},
    "04-14": {"name": "Baisakhi / Tamil New Year", "discount_pct": 14.0,
              "type": "festival",  "days_before": 2,  "days_after": 2,
              "platforms": ["amazon", "flipkart"]},
    "10-02": {"name": "Gandhi Jayanti Sale",       "discount_pct": 12.0,
              "type": "national",  "days_before": 2,  "days_after": 1,
              "platforms": ["amazon", "flipkart"]},
    "06-20": {"name": "Mid-Year Clearance Sale",   "discount_pct": 18.0,
              "type": "platform",  "days_before": 3,  "days_after": 3,
              "platforms": ["amazon", "flipkart"]},
}


# ---------------------------------------------------------------------------
# Internal helper: resolve MM-DD to an actual date (current or next year)
# ---------------------------------------------------------------------------
def _resolve_date(mm_dd: str, from_date: datetime.date) -> datetime.date:
    """
    Given a 'MM-DD' key and a reference date, returns the nearest future
    occurrence of that calendar date.  If it has already passed this year,
    returns next year's occurrence.
    """
    month, day = int(mm_dd[:2]), int(mm_dd[3:])
    try:
        candidate = datetime.date(from_date.year, month, day)
    except ValueError:
        # e.g. Feb 29 on non-leap year → use Mar 1
        candidate = datetime.date(from_date.year, month, 28)
    if candidate < from_date:
        try:
            candidate = datetime.date(from_date.year + 1, month, day)
        except ValueError:
            candidate = datetime.date(from_date.year + 1, month, 28)
    return candidate


# ---------------------------------------------------------------------------
# Public helpers
# ---------------------------------------------------------------------------

def get_upcoming_events(from_date: datetime.date = None, days_ahead: int = 60) -> list:
    """
    Returns a list of upcoming sale events within the next `days_ahead` days.
    from_date defaults to today if None.

    Each entry: {
        "name":         str,
        "date":         datetime.date,        # exact date of the event
        "days_away":    int,                  # days from from_date to event
        "sale_starts":  datetime.date,        # date - days_before
        "sale_ends":    datetime.date,        # date + days_after
        "discount_pct": float,
        "type":         str,
        "platforms":    list
    }
    Sorted by days_away ascending.
    """
    if from_date is None:
        from_date = datetime.date.today()

    results = []
    for mm_dd, info in FESTIVAL_CALENDAR.items():
        event_date = _resolve_date(mm_dd, from_date)
        days_away  = (event_date - from_date).days

        if 0 <= days_away <= days_ahead:
            sale_starts = event_date - datetime.timedelta(days=info["days_before"])
            sale_ends   = event_date + datetime.timedelta(days=info["days_after"])
            results.append({
                "name":         info["name"],
                "date":         event_date,
                "days_away":    days_away,
                "sale_starts":  sale_starts,
                "sale_ends":    sale_ends,
                "discount_pct": info["discount_pct"],
                "type":         info["type"],
                "platforms":    info["platforms"],
            })

    results.sort(key=lambda x: x["days_away"])
    return results


def get_active_event(on_date: datetime.date = None) -> dict | None:
    """
    Returns the active event dict if today falls within any event's
    sale window (sale_starts to sale_ends), else returns None.
    If multiple events overlap, returns the one with the highest discount_pct.
    """
    if on_date is None:
        on_date = datetime.date.today()

    active = []
    for mm_dd, info in FESTIVAL_CALENDAR.items():
        # Check both current-year and previous-year occurrences so we catch
        # events whose main date has just passed but are still in their
        # post-sale window.
        for year_offset in (-1, 0):
            month, day = int(mm_dd[:2]), int(mm_dd[3:])
            try:
                event_date  = datetime.date(on_date.year + year_offset, month, day)
            except ValueError:
                event_date  = datetime.date(on_date.year + year_offset, month, 28)
            sale_starts = event_date - datetime.timedelta(days=info["days_before"])
            sale_ends   = event_date + datetime.timedelta(days=info["days_after"])
            if sale_starts <= on_date <= sale_ends:
                active.append({
                    "name":         info["name"],
                    "date":         event_date,
                    "sale_starts":  sale_starts,
                    "sale_ends":    sale_ends,
                    "discount_pct": info["discount_pct"],
                    "type":         info["type"],
                    "platforms":    info["platforms"],
                })
                break  # found this event's window, no need to check other year

    if not active:
        return None
    # Return the one with the highest discount
    return max(active, key=lambda x: x["discount_pct"])


def get_festival_feature(date) -> float:
    """
    Given a date (datetime.date or datetime-like), returns a float 0.0–1.0:
      - 1.0  if date falls exactly on an event day
      - 0.75 if within days_before of an event (pre-sale buildup)
      - 0.5  if within days_after of an event (post-sale recovery)
      - 0.0  if no nearby event
    Used as an ML training feature.
    """
    try:
        if hasattr(date, "date"):
            date = date.date()
        elif not isinstance(date, datetime.date):
            date = datetime.date.fromisoformat(str(date)[:10])
    except Exception:
        return 0.0

    best = 0.0
    for mm_dd, info in FESTIVAL_CALENDAR.items():
        for year_offset in (-1, 0, 1):
            month, day = int(mm_dd[:2]), int(mm_dd[3:])
            try:
                event_date = datetime.date(date.year + year_offset, month, day)
            except ValueError:
                event_date = datetime.date(date.year + year_offset, month, 28)

            if date == event_date:
                return 1.0  # exact match — no need to search further

            diff = (date - event_date).days
            if -info["days_before"] <= diff < 0:
                # date is within pre-sale window
                best = max(best, 0.75)
            elif 0 < diff <= info["days_after"]:
                # date is within post-sale window
                best = max(best, 0.50)

    return best


def days_until_next_event(from_date: datetime.date = None,
                          platform: str = None) -> dict | None:
    """
    Returns {"event": name, "days": int, "date": date,
             "discount_pct": float, "sale_starts": date}
    for the next upcoming event (within 180 days).
    If platform is specified, filter to events that include that platform.
    Returns None if no event found.
    """
    if from_date is None:
        from_date = datetime.date.today()

    best      = None
    best_days = 999999

    for mm_dd, info in FESTIVAL_CALENDAR.items():
        if platform and platform not in info["platforms"]:
            continue
        event_date = _resolve_date(mm_dd, from_date)
        days_away  = (event_date - from_date).days
        if 0 <= days_away <= 180 and days_away < best_days:
            best_days = days_away
            sale_starts = event_date - datetime.timedelta(days=info["days_before"])
            best = {
                "event":        info["name"],
                "days":         days_away,
                "date":         event_date,
                "discount_pct": info["discount_pct"],
                "sale_starts":  sale_starts,
            }

    return best


def get_event_price_multiplier(date) -> float:
    """
    Returns a float multiplier for the expected price on a given date.
      - If date is in an active sale window: 1.0 - (discount_pct / 100)
      - Otherwise: 1.0 (no adjustment)
    Example: Diwali sale 30% off → multiplier = 0.70
    Uses the highest-discount active event if multiple overlap.
    """
    try:
        if hasattr(date, "date"):
            date = date.date()
        elif not isinstance(date, datetime.date):
            date = datetime.date.fromisoformat(str(date)[:10])
    except Exception:
        return 1.0

    active = get_active_event(on_date=date)
    if active:
        return round(1.0 - active["discount_pct"] / 100.0, 4)
    return 1.0
