# -*- coding: utf-8 -*-
"""
BargainBot - scraper.py
Scrapes live prices from Amazon India and Flipkart.
Uses requests + BeautifulSoup only. Never uses Selenium.
"""

import time
import random
import re
import requests
from bs4 import BeautifulSoup
from itertools import cycle

# ---------------------------------------------------------------------------
# Rotating User-Agent pool
# ---------------------------------------------------------------------------
_USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
]
_agent_cycle = cycle(_USER_AGENTS)

# ---------------------------------------------------------------------------
# Short-lived price cache: { product_name_lower: (price, timestamp) }
# Used as last-resort fallback when Amazon blocks a request.
# ---------------------------------------------------------------------------
_amazon_cache: dict = {}
_CACHE_TTL_SECONDS = 7200  # 2 hours


def _get_headers() -> dict:
    """Returns headers with the next rotating User-Agent."""
    return {
        "User-Agent": next(_agent_cycle),
        "Accept-Language": "en-IN,en;q=0.9",
        "Accept-Encoding": "gzip, deflate, br",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Referer": "https://www.google.com/",
        "DNT": "1",
    }


def _random_delay():
    """Sleeps between 3 and 7 seconds to avoid rate limiting."""
    delay = random.uniform(3.0, 7.0)
    time.sleep(delay)


def _clean_price(raw: str) -> int | None:
    """Strips non-numeric characters and returns an integer price, or None."""
    try:
        cleaned = re.sub(r"[^\d]", "", raw.replace(",", ""))
        if cleaned:
            val = int(cleaned)
            # Sanity check: Indian product prices should be between Rs.10 and Rs.10,00,000
            if 500 <= val <= 1_000_000:
                return val
    except Exception:
        pass
    return None


# ---------------------------------------------------------------------------
# Amazon India scraper
# ---------------------------------------------------------------------------
def _scrape_amazon(product_name: str) -> int | None:
    """
    Searches Amazon India for the product and returns the first listed price.
    Strategy order:
      1. CSS selectors on the search results page
      2. Raw HTML regex (a-price-whole pattern — confirmed working)
      3. Retry with alternate URL if page shows no results
      4. Cached price from previous successful scrape (up to 2 hours old)
    """
    query    = product_name.replace(" ", "+")
    cache_key = product_name.strip().lower()

    # URLs to try: standard search first, then no-ref variant
    urls = [
        f"https://www.amazon.in/s?k={query}&ref=nb_sb_noss",
        f"https://www.amazon.in/s?k={query}",
    ]

    # Extended selector list — Amazon changes class names periodically
    selectors = [
        "span.a-price-whole",
        "span.a-offscreen",
        "div[data-component-type='s-search-result'] span.a-price span.a-offscreen",
        "span[data-a-size='xl'] span.a-offscreen",
        "span[data-a-size='b'] span.a-offscreen",
        "span[data-a-size='m'] span.a-offscreen",
        "span[class*='price'] span.a-offscreen",
        ".s-price-instructions-style span.a-offscreen",
    ]

    def _attempt(url_to_use: str, attempt_num: int) -> int | None:
        try:
            _random_delay()
            headers = _get_headers()
            if attempt_num > 1:
                headers["Cache-Control"] = "no-cache"
                headers["Pragma"]        = "no-cache"
            response = requests.get(url_to_use, headers=headers, timeout=15)
            response.raise_for_status()

            body = response.text

            # Detect CAPTCHA / bot-check page
            if "captcha" in body.lower() or "Enter the characters" in body:
                print(f"[Amazon] Attempt {attempt_num}: CAPTCHA detected")
                return None

            # Detect empty-results / rate-limit page
            no_results_signals = [
                "did not match any products",
                "sorryWeCouldntFind",
                "no results for",
                "Try checking your spelling",
            ]
            if any(sig.lower() in body.lower() for sig in no_results_signals):
                print(f"[Amazon] Attempt {attempt_num}: no-results page (rate limited?)")
                return None

            soup = BeautifulSoup(body, "html.parser")

            # --- CSS selector sweep ---
            for selector in selectors:
                for el in soup.select(selector):
                    price = _clean_price(el.get_text())
                    if price is not None:
                        print(f"[Amazon] Attempt {attempt_num}: CSS price Rs.{price} for '{product_name}'")
                        return price

            # --- Raw HTML regex — confirmed working in diagnostic ---
            # Pattern 1: Amazon's a-price-whole span content (Indian lakh format)
            for raw in re.findall(r'a-price-whole[^>]*>([0-9,]+)', body):
                p = _clean_price(raw)
                if p:
                    print(f"[Amazon] Attempt {attempt_num}: price-whole regex Rs.{p} for '{product_name}'")
                    return p

            # Pattern 2: JSON embedded price fields
            for raw in re.findall(r'(?:"price(?:Amount)?"\s*:\s*"?|data-price=")([\d,]{3,10})', body):
                p = _clean_price(raw)
                if p:
                    print(f"[Amazon] Attempt {attempt_num}: JSON regex Rs.{p} for '{product_name}'")
                    return p

            print(f"[Amazon] Attempt {attempt_num}: no price found for '{product_name}'")
            return None

        except Exception as e:
            print(f"[Amazon] Attempt {attempt_num} error for '{product_name}': {e}")
            return None

    # --- Attempt 1: standard URL ---
    price = _attempt(urls[0], 1)
    if price is not None:
        _amazon_cache[cache_key] = (price, time.time())
        return price

    # --- Attempt 2: alternate URL after short pause ---
    print(f"[Amazon] Retrying with alternate URL for '{product_name}'...")
    time.sleep(random.uniform(2.0, 4.0))
    price = _attempt(urls[1], 2)
    if price is not None:
        _amazon_cache[cache_key] = (price, time.time())
        return price

    # --- Attempt 3: final fallback — use cached price if recent ---
    cached = _amazon_cache.get(cache_key)
    if cached:
        cached_price, cached_at = cached
        age = time.time() - cached_at
        if age < _CACHE_TTL_SECONDS:
            age_min = int(age / 60)
            print(f"[Amazon] Using cached price Rs.{cached_price} for '{product_name}' (from {age_min}m ago)")
            return cached_price

    print(f"[Amazon] All strategies exhausted for '{product_name}'")
    return None


# ---------------------------------------------------------------------------
# Flipkart scraper
# ---------------------------------------------------------------------------
def _scrape_flipkart(product_name: str) -> int | None:
    """
    Searches Flipkart for the product using multiple strategies:
      1. __INITIAL_STATE__ embedded JSON in page (confirmed working — prices in
         finalPrice.value and sellingPrice.value structures)
      2. Cookie-primed full-browser HTML request with raw-body regex scan
      3. JSON-LD structured data in script tags
      4. CSS class selector sweep
      5. Minimal fallback GET
    Returns None only if all strategies fail.
    """
    import json as _json

    query_p = product_name.replace(" ", "+")
    query_e = product_name.replace(" ", "%20")

    session = requests.Session()

    chrome_ua = (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    )

    base_headers = {
        "User-Agent":         chrome_ua,
        "Accept-Language":    "en-IN,en-GB;q=0.9,en;q=0.8",
        "Accept-Encoding":    "gzip, deflate, br",
        "Connection":         "keep-alive",
        "sec-ch-ua":          '"Chromium";v="124", "Google Chrome";v="124", "Not-A.Brand";v="99"',
        "sec-ch-ua-mobile":   "?0",
        "sec-ch-ua-platform": '"Windows"',
        "DNT":                "1",
    }

    def _fetch_search_page(sess, headers_override=None):
        """Prime cookies, then fetch the search page. Returns response or None."""
        try:
            sess.get(
                "https://www.flipkart.com",
                headers={**base_headers, "Accept": "text/html,*/*;q=0.9"},
                timeout=8,
            )
            time.sleep(random.uniform(1.5, 3.0))
            search_url = f"https://www.flipkart.com/search?q={query_p}&otracker=search"
            hdrs = {
                **base_headers,
                "Accept":                    "text/html,application/xhtml+xml,*/*;q=0.8",
                "Referer":                   "https://www.flipkart.com/",
                "Upgrade-Insecure-Requests": "1",
                "sec-fetch-dest":            "document",
                "sec-fetch-mode":            "navigate",
                "sec-fetch-site":            "same-origin",
                "sec-fetch-user":            "?1",
            }
            if headers_override:
                hdrs.update(headers_override)
            return sess.get(search_url, headers=hdrs, timeout=18)
        except Exception as ex:
            print(f"[Flipkart] fetch_search_page failed: {ex}")
            return None

    # ── Strategy 1: __INITIAL_STATE__ embedded JSON ───────────────────────────
    # Flipkart injects the full page state as a JS variable in every search
    # response.  Prices live inside nested objects:
    #   {"finalPrice": {"value": 49999, ...}, "mrp": {"value": 79999, ...}}
    # We scan for finalPrice.value first (actual selling price), then mrp.value.
    try:
        _random_delay()
        resp = _fetch_search_page(session)
        if resp and resp.status_code == 200:
            body = resp.text

            # Extract finalPrice values (actual selling price)
            final_prices = re.findall(
                r'"finalPrice"\s*:\s*\{[^}]{0,120}"value"\s*:\s*(\d{4,7})',
                body,
            )
            for raw in final_prices:
                p = _clean_price(raw)
                if p:
                    print(f"[Flipkart] __INITIAL_STATE__ finalPrice Rs.{p} for '{product_name}'")
                    return p

            # Fall back to sellingPrice values
            sell_prices = re.findall(
                r'"sellingPrice"\s*:\s*\{[^}]{0,120}"value"\s*:\s*(\d{4,7})',
                body,
            )
            for raw in sell_prices:
                p = _clean_price(raw)
                if p:
                    print(f"[Flipkart] __INITIAL_STATE__ sellingPrice Rs.{p} for '{product_name}'")
                    return p

            # Last resort: any mrp.value in a reasonable range
            mrp_prices = re.findall(
                r'"mrp"\s*:\s*\{[^}]{0,120}"value"\s*:\s*(\d{4,7})',
                body,
            )
            # Apply a 15% discount to MRP as an estimate of the selling price
            for raw in mrp_prices:
                try:
                    mrp_val = int(raw)
                    if 500 <= mrp_val <= 1_000_000:
                        est = int(mrp_val * 0.85)
                        print(f"[Flipkart] Estimated from MRP Rs.{mrp_val} → Rs.{est} for '{product_name}'")
                        return est
                except Exception:
                    pass
    except Exception as e:
        print(f"[Flipkart] __INITIAL_STATE__ strategy failed: {e}")

    # ── Strategy 2: JSON-LD + CSS selectors (same page, already fetched) ──────
    try:
        _random_delay()
        resp2 = _fetch_search_page(requests.Session())
        if resp2 and resp2.status_code == 200:
            soup = BeautifulSoup(resp2.text, "html.parser")

            # JSON-LD structured data
            for script_tag in soup.find_all("script", type="application/ld+json"):
                try:
                    ld    = _json.loads(script_tag.string or "")
                    items = ld if isinstance(ld, list) else [ld]
                    for item in items:
                        for entry in item.get("itemListElement", [item]):
                            obj = entry.get("item", entry)
                            for ok in ("offers", "Offers"):
                                offer = obj.get(ok, {})
                                if isinstance(offer, list):
                                    offer = offer[0] if offer else {}
                                for pk in ("price", "lowPrice", "highPrice"):
                                    rp = offer.get(pk)
                                    if rp:
                                        p = _clean_price(str(rp))
                                        if p:
                                            print(f"[Flipkart] JSON-LD Rs.{p} for '{product_name}'")
                                            return p
                except Exception:
                    pass

            # CSS class selectors (class names change, so try many)
            for selector in [
                "div.Nx9bqj", "div._30jeq3",
                "div.hl05eU div.Nx9bqj", "div.CEmiEU div.Nx9bqj",
                "div[class*='Nx9bqj']", "div[class*='_30jeq3']",
                "div._25b18c", "div._16Jk6d",
            ]:
                for el in soup.select(selector):
                    p = _clean_price(el.get_text())
                    if p:
                        print(f"[Flipkart] CSS Rs.{p} for '{product_name}'")
                        return p
    except Exception as e:
        print(f"[Flipkart] JSON-LD/CSS strategy failed: {e}")

    # ── Strategy 3: Minimal header GET ────────────────────────────────────────
    try:
        _random_delay()
        sr = requests.get(
            f"https://www.flipkart.com/search?q={query_p}",
            headers={"User-Agent": chrome_ua, "Accept-Language": "en-IN,en;q=0.9", "Accept": "text/html,*/*;q=0.8"},
            timeout=15,
        )
        body3 = sr.text
        # Try __INITIAL_STATE__ pattern on minimal response too
        for pattern in [
            r'"finalPrice"\s*:\s*\{[^}]{0,120}"value"\s*:\s*(\d{4,7})',
            r'"sellingPrice"\s*:\s*\{[^}]{0,120}"value"\s*:\s*(\d{4,7})',
        ]:
            found = re.findall(pattern, body3)
            for raw in found:
                p = _clean_price(raw)
                if p:
                    print(f"[Flipkart] Minimal INIT Rs.{p} for '{product_name}'")
                    return p

        ssoup = BeautifulSoup(body3, "html.parser")
        for selector in ["div.Nx9bqj", "div._30jeq3", "div[class*='price']"]:
            for el in ssoup.select(selector):
                p = _clean_price(el.get_text())
                if p:
                    print(f"[Flipkart] Minimal CSS Rs.{p} for '{product_name}'")
                    return p
    except Exception as e:
        print(f"[Flipkart] Minimal strategy failed: {e}")

    print(f"[Flipkart] All strategies exhausted for '{product_name}'")
    return None


# ---------------------------------------------------------------------------
# Public interface
# ---------------------------------------------------------------------------
def scrape_prices(product_name: str) -> dict:
    """
    Scrapes Amazon India and Flipkart for the given product.

    Cross-validates both prices: if one is more than 3x cheaper/dearer than
    the other it is almost certainly wrong (e.g. regex matched an accessory
    price) and is discarded.

    Returns:
        {
            "amazon":   int or None,
            "flipkart": int or None
        }
    Never raises — all errors are caught internally.
    """
    print(f"[Scraper] Searching for: '{product_name}'")

    amazon_price   = _scrape_amazon(product_name)
    flipkart_price = _scrape_flipkart(product_name)

    # ---- Cross-validation ----
    # If both prices exist, make sure they are within 3× of each other.
    # A larger ratio almost always means one scraper matched the wrong element.
    if amazon_price and flipkart_price:
        lo, hi = sorted([amazon_price, flipkart_price])
        ratio  = hi / lo
        if ratio > 3.0:
            print(
                f"[Scraper] Cross-validation FAIL — Amazon: Rs.{amazon_price}, "
                f"Flipkart: Rs.{flipkart_price} (ratio {ratio:.1f}×). "
                f"Discarding the lower price as likely wrong."
            )
            # The lower price is almost always the wrong one
            if flipkart_price < amazon_price:
                flipkart_price = None
            else:
                amazon_price   = None

    return {
        "amazon":   amazon_price,
        "flipkart": flipkart_price,
    }
