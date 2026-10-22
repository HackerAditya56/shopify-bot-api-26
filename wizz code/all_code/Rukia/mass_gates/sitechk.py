import asyncio
import random
import aiohttp
import json
import os
import time
import re
import logging
import io

# Absolute path to sites.txt — always correct regardless of launch directory
SITES_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "sites.txt")

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# AIogram Imports
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
from aiogram import types, F, Router, Bot
from aiogram.filters import Command
from aiogram.types import FSInputFile

from shopify_api import call_shopify_api, APIStatusError

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# CONFIGURATION
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

# ADD YOUR TELEGRAM ID HERE
ADMIN_IDS = {8423281554} 

# Test card to verify site functionality
TEST_CARD = "4000223372377978|05|29|651"

# ━━━ TEST CARDS POOL (60 random cards, rotation per check) ━━━━━━━━━━━
# All exp dates are FUTURE (today = Jul 2026). No expired cards.
TEST_CARDS = [
    # Visa
    "4242424242424242|11|27|123",
    "4111111111111111|11|27|123",
    "4012888888881881|11|27|123",
    "4222222222222222|11|27|123",
    "4000111111111115|11|27|123",
    "4242424242424242|03|28|321",
    "4111111111111111|03|28|321",
    "4012888888881881|03|28|321",
    "4222222222222222|03|28|321",
    "4000111111111115|03|28|321",
    "4242424242424242|08|28|456",
    "4111111111111111|08|28|456",
    "4012888888881881|08|28|456",
    "4222222222222222|08|28|456",
    "4000111111111115|08|28|456",
    "4242424242424242|06|29|789",
    "4111111111111111|06|29|789",
    "4012888888881881|06|29|789",
    "4222222222222222|06|29|789",
    "4000111111111115|06|29|789",
    "4242424242424242|09|29|321",
    "4111111111111111|09|29|321",
    "4012888888881881|09|29|321",
    "4222222222222222|09|29|321",
    "4000111111111115|09|29|321",
    # Mastercard
    "5555555555554444|11|27|123",
    "5105105105105100|11|27|123",
    "5454545454545454|11|27|123",
    "5111111111111111|11|27|123",
    "5200828282828210|11|27|123",
    "5555555555554444|03|28|321",
    "5105105105105100|03|28|321",
    "5454545454545454|03|28|321",
    "5111111111111111|03|28|321",
    "5200828282828210|03|28|321",
    "5555555555554444|08|28|456",
    "5105105105105100|08|28|456",
    "5454545454545454|08|28|456",
    "5111111111111111|08|28|456",
    "5200828282828210|08|28|456",
    "5555555555554444|06|29|789",
    "5105105105105100|06|29|789",
    "5454545454545454|06|29|789",
    "5111111111111111|06|29|789",
    "5200828282828210|06|29|789",
    # Amex (4-digit CVV)
    "378282246310005|11|27|1234",
    "371449635398431|11|27|1234",
    "378734493671000|11|27|1234",
    "378282246310005|03|28|4321",
    "371449635398431|03|28|4321",
    "378734493671000|03|28|4321",
    "378282246310005|08|28|8765",
    "371449635398431|08|28|8765",
    # Discover
    "6011111111111117|03|28|123",
    "6011000990139424|03|28|123",
    "6011111111111117|06|29|321",
    "6011000990139424|06|29|321",
    "6011111111111117|09|29|456",
    "6011000990139424|09|29|456",
    # JCB
    "3530111333300000|06|29|123",
    "3566002020360505|06|29|123",
    "3530111333300000|09|29|321",
]  # 60 cards total — all FUTURE exp dates

# API Configuration (admin-specified URL — used ONLY for site checks)
SITE_CHECK_API_URL = "http://5.83.136.102:8073/shopify"
API_TIMEOUT = 30
PRICE_FETCH_TIMEOUT = 8  # short timeout — price pre-fetch should be a "quick probe", not block site-check

# Proxy pool — REMOVED in this rev per admin request.
# Site checking used to fall back to a hardcoded 16-proxy admin-only list
# whenever the operator forgot to run /proxy. That list has been DELETED
# — /addsite and /sitechk now consume proxies EXCLUSIVELY from two
# sources, in priority order:
#   1. The admin's saved proxies in the MongoDB `proxies` collection
#      (same place /proxy stores them) — loaded per-run by
#      `_load_admin_proxies_for_run()`.
#   2. The shared global `proxies.txt` (loaded by
#      `database.load_global_proxies()`) — only as a fallback when the
#      admin's DB has zero entries.
# No hardcoded list ships in code anymore.
_PROXY_POOL: list = []

# Bad proxies that failed - removed from rotation
BAD_PROXIES = set()

# ━━━ DEAD ERRORS LIST ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# REMOVED in this rev (per admin request): the previous 30+ generic
# dead/error keywords (step failures, missing tokens, JSON/timeout/etc.)
# are no longer in effect. Sites.txt no longer auto-guesses "broken" from
# raw error text. Instead, /addsite now only marks a site as DEAD if the
# API returns one of the CAUSE-SPECIFIC card-retry patterns listed in
# DEAD_KEYWORDS below. All other responses = site is WORKING.
DEAD_ERRORS = []


# ━━━ DEAD KEYWORDS (the ONLY patterns that mark site as DEAD now) ━━━━
# Per admin request: /addsite uses ONLY these card-retry-specific
# patterns as the dead-site indicator. Match in any of these (case-
# insensitive substring) ⇒ site is REMOVED. Anything else ⇒ site is
# WORKING and added to sites.txt.
#
# These mirror the same patterns that drive rotation/retry in /msh and
# /sh — sites that consistently return them under the test card are
# merchants that won't accept the bot's flow at all, so it's safer to
# never feed them back into mass card checks.
DEAD_KEYWORDS = [
    # Shopify billing/payment-validator errors — merchant config that
    # rejects the cart we hand it (price hint, payment flexibility, …).
    "PAYMENTS_POSITIVE_AMOUNT_EXPECTED",
    "PAYMENTS_PAYMENT_FLEXIBILITY_TERMS_ID_MISMATCH",
    # CartCreate price mismatch — only fires for stale merchant sale
    # configs or negative cart totals.
    "MERCHANDISE_EXPECTED_PRICE_MISMATCH",
    # Proxy-blocked — the merchant is rejecting the bot's proxy IP at
    # the storefront. Adding such a site is useless: every /msh card
    # routed through this merchant will hit the same block.
    "Proxied IP Blocked",
    "proxied ip blocked",
    # Comma-space form to cover the exact HTML-wrapped response:
    "<b>Proxied IP Blocked - Try Different Proxy</b>",
]


# ━━━ RETRYABLE KEYWORDS — DISABLED in this rev ━━━━━━━━━━━━━━━━━━━━━
# Per admin request: /addsite no longer retries on price/currency
# transient mismatches. The site is either marked DEAD (matches a
# DEAD_KEYWORD) or KEEP on first valid response. Set to empty list so
# the existing "is_retryable" branch in check_site_status is a no-op.
RETRYABLE_KEYWORDS = []  # PLACEHOLDER_RESOLVED


# ━━━ PRICE PRE-FETCH (avoid MERCHANDISE_EXPECTED_PRICE_MISMATCH retry) ━━━
# To avoid the price-mismatch retry loop entirely, we pre-fetch the site's
# product price from the API before doing the real check, then pass that
# price as a 5th segment of the cc parameter (card|mm|yy|cvv|$X.XX).
# When price matches, MERCHANDISE_EXPECTED_PRICE_MISMATCH never fires.
# Falls back silently to retry logic if the price endpoint isn't supported.

# ━━━ SMART ERROR RESPONSE DETECTION — REMOVED in this rev ━━━━━━━━━━━━━
# REMOVED per admin request: the generic-error-prefix detector
# `_looks_like_error_response` plus its helpers SHOPIFY_ERROR_PREFIXES
# and GENERIC_ERROR_MARKERS are no longer loaded here. They were a
# catch-all "this response text smells like an error" heuristic that
# false-positive-flipped too many sites. /addsite now relies EXCLUSIVELY
# on DEAD_KEYWORDS for the dead-site decision; anything else is KEEP.
# (the `response_msg.lower()` substring match inside check_site_status
# was the remaining path, and that consumes DEAD_KEYWORDS directly with
# no other interpretation in between.)


def _parse_price(price_val) -> float | None:
    """Parse various price formats to float. Returns None if invalid."""
    if price_val is None:
        return None
    if isinstance(price_val, (int, float)):
        return float(price_val)
    if not isinstance(price_val, str):
        return None
    s = re.sub(r'[^\d.]', '', str(price_val))
    if not s:
        return None
    try:
        return float(s)
    except ValueError:
        return None


async def _fetch_site_price(site_url: str, proxy: str) -> float | None:
    """
    Best-effort price pre-fetch from the site-check API.
    Tries several endpoint patterns to maximize compatibility.
    Returns float price or None if not available.

    Designed to be FAST — single 8s timeout cap per variant, max 2 variants.
    If price endpoint doesn't exist or proxy/network stalls, we bail out
    quickly so the main check proceeds without delay.
    """
    try:
        from shopify_api import _get_shared_session, _proxy_for_api
    except Exception:
        return None

    session = await _get_shared_session()
    proxy_param = _proxy_for_api(proxy) if proxy else ""
    base = SITE_CHECK_API_URL.rstrip("/")
    proxy_for_aiohttp = proxy if (proxy and proxy.strip()) else None
    quick_timeout = aiohttp.ClientTimeout(total=PRICE_FETCH_TIMEOUT)

    # Just two patterns — both common, returns on first 200 + valid price.
    variants = [
        ("{base}/price",                  {"site": site_url, "proxy": proxy_param}),
        ("{base}?info=price",             {"site": site_url, "proxy": proxy_param, "info": "price"}),
    ]
    for url_template, params in variants:
        url = url_template.format(base=base)
        try:
            async with session.get(
                url,
                params=params,
                proxy=proxy_for_aiohttp,
                timeout=quick_timeout,
            ) as resp:
                if resp.status != 200:
                    continue
                text = await resp.text()
                if not text or not text.strip():
                    continue
                try:
                    data = json.loads(text)
                except json.JSONDecodeError:
                    continue
                if not isinstance(data, dict):
                    continue
                for key, value in data.items():
                    if key.lower() in ("price", "amount", "expectedprice",
                                        "expected_price", "total", "totalamount"):
                        parsed = _parse_price(value)
                        if parsed is not None and 0 < parsed <= 1000:
                            return parsed
                # 200 OK but no price field — endpoint exists but doesn't
                # return a price for this site. Don't try more variants.
                if data:
                    return None
        except Exception:
            continue
    return None


# List of valid gateway responses (Site is Alive)
SUCCESS_RESPONSES = [
    'CARD_DECLINED', 'INVALID_CVC', 'INCORRECT_CVV', 'INSUFFICIENT_FUNDS', 
    'GENERIC_DECLINE', 'DO NOT HONOR', 'UNKNOWN_ERROR', 'EXPIRED_CARD',
    'PICK_UP_CARD', 'FRAUD_SUSPECTED', '3DS_REQUIRED', 'AMOUNT_TOO_SMALL',
    'INVALID_PURCHASE_TYPE', 'INVALID_PAYMENT_METHOD', 'ORDER_PAID', 'INCORRECT_NUMBER',
]

# Router for this module
router = Router()

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# HELPER FUNCTIONS
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def is_admin(user_id):
    """Check if user is admin"""
    return user_id in ADMIN_IDS

def read_sites():
    """Read sites from sites.txt file - returns list without duplicates"""
    if not os.path.exists(SITES_FILE):
        return []
    with open(SITES_FILE, "r", encoding="utf-8") as f:
        # Automatically remove duplicates when reading
        sites = list(set([line.strip() for line in f if line.strip()]))
    return sites

def write_sites(sites_list):
    """Write sites to sites.txt file - ENSURES NO DUPLICATES"""
    # Convert to set to remove duplicates, then back to list
    unique_sites = list(set(sites_list))
    
    with open(SITES_FILE, "w", encoding="utf-8") as f:
        for site in unique_sites:
            f.write(f"{site}\n")
    
    return len(unique_sites)

def normalize_url(url: str) -> str:
    """
    Normalize URL to prevent duplicates with slight variations
    
    Examples:
    - https://example.com/ -> https://example.com
    - https://EXAMPLE.COM -> https://example.com
    - https://example.com/// -> https://example.com
    """
    url = url.strip().lower()
    
    # Remove trailing slash
    url = url.rstrip('/')
    
    # Remove www. prefix for consistency
    if url.startswith('www.'):
        url = url[4:]
    
    return url

def get_random_proxy():
    """Get a random proxy from the run-loaded pool (DB-saved admin
    proxies + global proxies.txt fallback). Driven by `_PROXY_POOL` —
    populated at the start of every run_site_checker() call via
    `_load_admin_proxies_for_run()`.
    """
    global BAD_PROXIES
    available = [p for p in _PROXY_POOL if p not in BAD_PROXIES]
    if not available:
        # Reset bad proxies if all are bad
        BAD_PROXIES.clear()
        available = list(_PROXY_POOL)
    if not available:
        return None
    return random.choice(available)

def mark_proxy_bad(proxy):
    """Mark a proxy as bad"""
    global BAD_PROXIES
    BAD_PROXIES.add(proxy)


async def _load_admin_proxies_for_run(user_id: int) -> int:
    """
    Populate `_PROXY_POOL` with the admin's DB-saved proxies for this
    /addsite or /sitechk run. Falls back to `database.load_global_proxies()`
    (the shared `proxies.txt` pool) if the admin has zero saved entries.

    Returns the number of proxies loaded.
    """
    global _PROXY_POOL, BAD_PROXIES
    _PROXY_POOL = []
    BAD_PROXIES = set()  # fresh per-run blacklist

    # Pass 1: admin's per-user DB collection ("proxies").
    try:
        def _query_db():
            from database import get_collection
            col = get_collection("proxies")
            return [doc["proxy"] for doc in col.find(
                {"user_id": user_id}, {"proxy": 1, "_id": 0}
            )]

        db_proxies = await asyncio.to_thread(_query_db)
    except Exception as e:
        logging.error(f"[SITECHK] DB proxy load failed for user {user_id}: {e}")
        db_proxies = []

    if db_proxies:
        _PROXY_POOL = list(dict.fromkeys(db_proxies))  # dedupe, keep order
        return len(_PROXY_POOL)

    # Pass 2: global proxies.txt fallback (shared pool — every user can
    # benefit if admin's DB is empty).
    try:
        from database import load_global_proxies
        _PROXY_POOL = load_global_proxies()
    except Exception as e:
        logging.error(f"[SITECHK] Global proxy load failed: {e}")
        _PROXY_POOL = []

    return len(_PROXY_POOL)


async def call_site_check_api(site_url: str, cc_formatted: str, proxy: str) -> dict:
    """
    Call the site-check API URL with smart price-hint retry.

    Flow:
      1. First call WITHOUT price hint — capture actual site price from
         response (Shopify API returns `Price` field even on price-mismatch
         errors).
      2. If response was MERCHANDISE_EXPECTED_PRICE_MISMATCH (or similar)
         AND the response carries a valid site price:
         Second call WITH that price passed as `&price=$X.XX` URL param.
         The API uses our price instead of running the merchant-side
         expected-price comparison, eliminating the mismatch on shot #2.

    Persistent mismatch after the price-hint retry falls through to the
    RETRYABLE_KEYWORDS handler in check_site_status (which keeps the site
    alive — never marks it dead for a price mismatch).
    """
    from shopify_api import _proxy_for_api

    proxy_param = _proxy_for_api(proxy) if proxy else ""
    proxy_for_aiohttp = proxy if (proxy and proxy.strip()) else None

    # ── CALL 1: standard request without price hint ──
    result1 = await _do_site_api_call(
        site_url=site_url,
        cc=cc_formatted,
        proxy_param=proxy_param,
        proxy_for_aiohttp=proxy_for_aiohttp,
        price_hint=None,
    )

    response_msg = result1.get("response", "Unknown")
    response_upper = response_msg.upper()

    # ── SMART RETRY: mismatch + valid price in response → pass price ──
    is_price_mismatch = (
        "MERCHANDISE_EXPECTED_PRICE_MISMATCH" in response_upper
        or "EXPECTED_PRICE_MISMATCH" in response_upper
        or "SALE_PRICE_MISMATCH" in response_upper
        or "PRICE_OUT_OF_RANGE" in response_upper
        or "EXPECTED_LINE_ITEM_PRICE" in response_upper
    )

    if is_price_mismatch:
        first_price = _parse_price(result1.get("price"))
        if first_price is not None and first_price > 0:
            # Second call WITH price hint — bypass merchant price check
            result2 = await _do_site_api_call(
                site_url=site_url,
                cc=cc_formatted,
                proxy_param=proxy_param,
                proxy_for_aiohttp=proxy_for_aiohttp,
                price_hint=f"{first_price:.2f}",
            )
            return result2

    return result1


async def _do_site_api_call(
    site_url: str,
    cc: str,
    proxy_param: str,
    proxy_for_aiohttp: str | None,
    price_hint: str | None,
) -> dict:
    """Single HTTP call to SITE_CHECK_API_URL. Internal helper."""
    try:
        from shopify_api import _get_shared_session

        params: dict = {
            "site": site_url,
            "cc": cc,
            "proxy": proxy_param,
        }
        if price_hint:
            # Pass `price=` URL param so the API uses our value and skips
            # the merchant-side expected-price check that causes
            # MERCHANDISE_EXPECTED_PRICE_MISMATCH.
            params["price"] = price_hint

        session = await _get_shared_session()
        async with session.get(
            SITE_CHECK_API_URL,
            params=params,
            proxy=proxy_for_aiohttp,
            timeout=aiohttp.ClientTimeout(total=API_TIMEOUT),
        ) as resp:
            text = await resp.text()
            if resp.status in (408, 429, 500, 502, 503, 504):
                raise APIStatusError(resp.status, text)
            if not text or not text.strip():
                raise APIStatusError(resp.status, "<empty body>")
            try:
                data = json.loads(text)
            except json.JSONDecodeError as e:
                raise json.JSONDecodeError(e.msg, e.doc, e.pos) from e

        response_msg = data.get("Response", "Unknown")
        price_str = data.get("Price", "-1.0")
        proxy_raw = data.get("Proxy", "Dead")
        gateway = data.get("Gateway", "")
        status = data.get("Status", "false")

        if "live" in str(proxy_raw).lower():
            proxy_status = "Live"
        else:
            proxy_status = "Dead"

        return {
            "success": True,
            "response": response_msg,
            "price": price_str,
            "proxy_status": proxy_status,
            "gateway": gateway,
            "status": status,
            "error": None,
        }

    except asyncio.TimeoutError:
        return {
            "success": False,
            "response": "Timeout Error",
            "price": "-1.0",
            "proxy_status": "Dead",
            "gateway": "",
            "error": "TIMEOUT"
        }
    except aiohttp.ClientResponseError as e:
        return {
            "success": False,
            "response": f"HTTP Error {e.status}",
            "price": "-1.0",
            "proxy_status": "Dead",
            "gateway": "",
            "error": f"HTTP_{e.status}"
        }
    except APIStatusError as e:
        return {
            "success": False,
            "response": f"HTTP Error {e.status}",
            "price": "-1.0",
            "proxy_status": "Dead",
            "gateway": "",
            "error": f"HTTP_{e.status}"
        }
    except json.JSONDecodeError:
        return {
            "success": False,
            "response": "Invalid JSON Response",
            "price": "-1.0",
            "proxy_status": "Dead",
            "gateway": "",
            "error": "JSON_PARSE_ERROR"
        }
    except aiohttp.ClientConnectorError as e:
        error_str = str(e).lower()
        if "proxy" in error_str or "tunnel" in error_str:
            return {
                "success": False,
                "response": f"Proxy Error: {str(e)[:60]}",
                "price": "-1.0",
                "proxy_status": "Dead",
                "gateway": "",
                "error": "PROXY_ERROR"
            }
        return {
            "success": False,
            "response": f"Connection Error: {str(e)[:60]}",
            "price": "-1.0",
            "proxy_status": "Dead",
            "gateway": "",
            "error": "CONNECTION_ERROR"
        }
    except aiohttp.ClientError as e:
        return {
            "success": False,
            "response": f"Client Error: {str(e)[:60]}",
            "price": "-1.0",
            "proxy_status": "Dead",
            "gateway": "",
            "error": "CLIENT_ERROR"
        }
    except Exception as e:
        return {
            "success": False,
            "response": f"Error: {str(e)[:60]}",
            "price": "-1.0",
            "proxy_status": "Dead",
            "gateway": "",
            "error": "UNKNOWN_ERROR"
        }

async def check_site_status(site_url: str) -> tuple:
    """
    Checks a single site using the API with a test card.
    
    Returns: (site_url, status, data_dict, final_response_string)
    - status: "KEEP", "REMOVE", "ERROR"
    """
    MAX_RETRIES = 3
    
    for attempt in range(MAX_RETRIES):
        proxy = get_random_proxy()
        test_cc = random.choice(TEST_CARDS)
        
        result = await call_site_check_api(
            site_url=site_url,
            cc_formatted=test_cc,
            proxy=proxy
        )
        
        response_msg = result.get("response", "Unknown")
        price_str = result.get("price", "-1.0")
        proxy_status = result.get("proxy_status", "Dead")
        error_type = result.get("error")
        
        if proxy_status and proxy_status.lower() != "live":
            mark_proxy_bad(proxy)
            
            if error_type in ["PROXY_ERROR", "TIMEOUT", "CONNECTION_ERROR"]:
                if attempt < MAX_RETRIES - 1:
                    await asyncio.sleep(0.5)
                    continue
        
        # ━━━ DEAD-SITE CHECK (REWRITTEN per admin request) ━━━━━━━━━━━━━━━━━━━
        # Per admin request: /addsite no longer applies the 30+ generic
        # error/step-failure keywords (DEAD_ERRORS), the prefix-based
        # SHOPIFY_ERROR_PREFIXES detector (_looks_like_error_response),
        # HTTP/JSON technical-error auto-dead, and the price/currency
        # RETRYABLE_KEYWORDS retry-on-test-card loop. ALL of those were
        # heuristics guessing "is this site broken" from raw error text;
        # they triggered many false-positives.
        #
        # New rule (single source of truth):
        #   1. If response matches one of DEAD_KEYWORDS -> REMOVE
        #   2. Else if response matches SUCCESS_RESPONSES -> KEEP (price-capped)
        #   3. Else if response is "Unknown" / empty / other obvious
        #      placeholder -> REMOVE (API couldn't parse a real gateway
        #      decision; admin report: purecosmetics.com etc. were being
        #      added despite the API giving back literally "Unknown").
        #   4. ELSE -> KEEP (any other real response = working site).
        # Admin's DB-saved proxies (or global proxies.txt fallback) is
        # used regardless of result (already loaded in get_random_proxy()
        # -- no change needed there).
        response_lower = response_msg.lower()

        # (1) Is the response one of the explicit card-retry failure modes?
        is_dead = False
        for kw in DEAD_KEYWORDS:
            if kw.lower() in response_lower:
                is_dead = True
                break

        if is_dead:
            return site_url, "REMOVE", {"Price": -1.0}, response_msg

        # (2) Recognised valid gateway response -- validate price range, KEEP.
        if any(x in response_msg.upper() for x in SUCCESS_RESPONSES):
            actual_price = -1.0
            if price_str and price_str != "-1.0":
                clean_price = re.sub(r'[^\d.]', '', str(price_str))
                if clean_price:
                    try:
                        actual_price = float(clean_price)
                    except ValueError:
                        actual_price = -1.0

            # PRICE CONSTRAINT: must be between $0 and $20 to be usable for /msh.
            if 0.00 <= actual_price <= 20.00:
                msg_display = f"${actual_price:.2f} | {response_msg}"
                return site_url, "KEEP", {"Price": actual_price}, msg_display
            else:
                return site_url, "REMOVE", {"Price": actual_price}, f"Price ${actual_price:.2f} (Rejected) | {response_msg}"

        # (3) Filter "Unknown" / empty placeholders BEFORE falling through
        # to the admin-permissive KEEP rule. The API returns "Unknown" or
        # empty when it can't parse a real gateway decision (merchant
        # config is broken, or the storefront doesn't expose the JSON
        # fields the bot expects). User-reported purecosmetics.com,
        # upliftprovisionsco.com, timewarpboulder.com all came back as
        # "Unknown Response: Unknown" and were being marked KEEP under
        # the previous "any other = working" rule, polluting sites.txt.
        resp_clean = (response_msg.strip().lower()
                      if response_msg is not None else "")
        if (
            not resp_clean
            or resp_clean in ("unknown", "unknown response", "unknown error",
                              "none", "null", "n/a", "na", "error")
        ):
            return site_url, "REMOVE", {"Price": -1.0}, response_msg or "(empty response)"

        # (4) Anything else -- KEEP per admin directive ("other REAL
        # response = working"). Trusts the API's domain-specific
        # response over keyword regex for variants we haven't enumerated.
        return site_url, "KEEP", {"Price": -1.0}, f"Unknown Response: {response_msg}"

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# BACKGROUND WORKER FUNCTIONS
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

async def run_site_checker(bot: Bot, chat_id: int, sites_to_check, command_name="Audit", status_message_id=None, user_id: int | None = None):
    """Run site checking process in background with DUPLICATE PREVENTION"""
    global BAD_PROXIES
    # Reset bad proxies for fresh start
    BAD_PROXIES.clear()

    # Load this admin's DB-saved proxies (or fallback to global pool if
    # the admin has none). Done BEFORE spawning any worker tasks so the
    # very first site check already has the correct pool. The hardcoded
    # admin proxy list that shipped in this file for years has been
    # removed — operators add their proxies via /proxy and the MongoDB
    # `proxies` collection, just like end users do.
    if user_id is not None:
        loaded = await _load_admin_proxies_for_run(user_id)
        print(f"[SITECHK] Loaded {loaded} proxies from DB for user {user_id} "
              f"(command={command_name})")
    else:
        loaded = 0
        print(f"[SITECHK] run_site_checker called WITHOUT user_id — using empty pool "
              f"(command={command_name}). Pass user_id from the command handler.")

    total_sites = len(sites_to_check)
    valid_sites = []
    working_sites_content = []
    checked_count = 0
    live_count = 0
    dead_count = 0
    duplicate_count = 0
    
    last_edit_time = 0
    MIN_EDIT_INTERVAL = 2.0
    CHECKS_PER_UPDATE = 10
    # Concurrency cap for /sitechk and /addsite — bumped from 20 → 40 per
    # admin request so large site-batches (1000+ URLs) finish noticeably
    # faster. 40 in-flight HTTP calls to the site-check API is well within
    # the bot's backend tolerance (the GLOBAL_API_SEMAPHORE in msh.py
    # only governs /msh-heavy traffic, not these admin runs).
    sem = asyncio.Semaphore(40)
    
    # Get existing sites for duplicate checking (for /addsite command)
    existing_sites = set()
    if command_name == "Adding":
        existing_sites = set(await asyncio.to_thread(read_sites))
        print(f"[SITECHK] Found {len(existing_sites)} existing sites for duplicate check")

    async def worker(site):
        async with sem:
            return await check_site_status(site)
    
    tasks = [worker(site) for site in sites_to_check]
    
    for future in asyncio.as_completed(tasks):
        try:
            site, status, data, resp_msg = await future
        except Exception as e:
            checked_count += 1
            dead_count += 1
            print(f"[LOG] {site} | Error: {e}")
            continue
            
        checked_count += 1
        print(f"[LOG] {site} | {resp_msg}")

        if status == "KEEP":
            # NORMALIZE URL FOR DUPLICATE CHECK
            normalized_site = normalize_url(site)
            
            # Check if already exists (for Adding mode)
            if command_name == "Adding":
                normalized_existing = {normalize_url(s) for s in existing_sites}
                if normalized_site in normalized_existing:
                    duplicate_count += 1
                    print(f"[DUPLICATE SKIPPED] {site} already exists!")
                    continue
                
                # Also check if already added in this batch
                normalized_valid = {normalize_url(s) for s in valid_sites}
                if normalized_site in normalized_valid:
                    duplicate_count += 1
                    print(f"[DUPLICATE SKIPPED] {site} duplicate in batch!")
                    continue
            
            live_count += 1
            valid_sites.append(site)
            price = data.get("Price", "0.00") if isinstance(data, dict) else "0.00"
            if isinstance(price, float):
                price = f"${price:.2f}"
            working_sites_content.append(f"{site} | Price: {price} | Response: {resp_msg}")
        else:
            dead_count += 1

        current_time = time.time()
        if (current_time - MIN_EDIT_INTERVAL > last_edit_time) or (checked_count % CHECKS_PER_UPDATE == 0):
            try:
                if status_message_id:
                    dup_text = ""
                    if duplicate_count > 0:
                        dup_text = f"\n🔄 <b>Duplicates Skipped:</b> <code>{duplicate_count}</code>"
                    
                    await bot.edit_message_text(
                        chat_id=chat_id,
                        message_id=status_message_id,
                        text=f"🔄 <b>{command_name}ing {total_sites} Sites...</b>\n"
                        f"<b>━━━━━━━━━━━━━━━━━━━━━━</b>\n"
                        f"<tg-emoji emoji-id='5310296284874159738'>✅</tg-emoji> <b>Kept ($0-20):</b> <code>{live_count}</code>\n"
                        f"<tg-emoji emoji-id='5397890704062038337'>❌</tg-emoji> <b>Rejected:</b> <code>{dead_count}</code>\n"
                        f"🔄 <b>Checked:</b> <code>{checked_count}/{total_sites}</code>\n"
                        f"🌐 <b>Proxies Available:</b> <code>{len(_PROXY_POOL) - len(BAD_PROXIES)}/{len(_PROXY_POOL)}</code>"
                        f"{dup_text}",
                        parse_mode="HTML"
                    )
                    last_edit_time = current_time
            except Exception:
                pass 

    # FINAL DEDUPLICATION before saving
    final_unique_sites = []
    seen_normalized = set()
    
    for site in valid_sites:
        normalized = normalize_url(site)
        if normalized not in seen_normalized:
            seen_normalized.add(normalized)
            final_unique_sites.append(site)
    
    removed_dupes = len(valid_sites) - len(final_unique_sites)
    if removed_dupes > 0:
        print(f"[SITECHK] Removed {removed_dupes} internal duplicates before saving")
    
    # Save results based on command type
    if command_name == "Audit":
        saved_count = await asyncio.to_thread(write_sites, final_unique_sites)
    elif command_name == "Adding":
        # Merge with existing, ensuring no duplicates
        existing = await asyncio.to_thread(read_sites)
        existing_normalized = {normalize_url(s) for s in existing}
        
        combined = list(existing)
        for new_site in final_unique_sites:
            norm_new = normalize_url(new_site)
            if norm_new not in existing_normalized:
                combined.append(new_site)
                existing_normalized.add(norm_new)
        
        saved_count = await asyncio.to_thread(write_sites, combined)

    # Generate report file
    filename = f"report_{command_name.lower()}_{int(time.time())}.txt"
    
    file_content = "━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
    file_content += f"TOTAL CHECKED: {total_sites}\n"
    file_content += f"WORKING SITES (Price $0-20): {len(final_unique_sites)}\n"
    file_content += f"REJECTED (Dead/High Price): {dead_count}\n"
    if duplicate_count > 0 or removed_dupes > 0:
        file_content += f"DUPLICATES SKIPPED: {duplicate_count + removed_dupes}\n"
    file_content += f"PROXIES USED: {len(_PROXY_POOL)} | BAD: {len(BAD_PROXIES)}\n"
    file_content += "━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
    
    if working_sites_content:
        file_content += "\n".join(working_sites_content)
    else:
        file_content += "No valid sites found within price range!"

    try:
        def _write_report():
            with open(filename, "w", encoding="utf-8") as f:
                f.write(file_content)
        
        await asyncio.to_thread(_write_report)
        
        if status_message_id:
            try:
                dup_final = ""
                if (duplicate_count + removed_dupes) > 0:
                    dup_final = f"\n<tg-emoji emoji-id='5397890704062038337'>🚫</tg-emoji> <b>Duplicates Blocked:</b> <code>{duplicate_count + removed_dupes}</code>"
                
                await bot.edit_message_text(
                    chat_id=chat_id,
                    message_id=status_message_id,
                    text=f"<tg-emoji emoji-id='5310296284874159738'>✅</tg-emoji> <b>{command_name} Complete!</b>\n\n"
                    f"<b>Total Checked:</b> {total_sites}\n"
                    f"<b>Valid ($0-20):</b> {len(final_unique_sites)} <tg-emoji emoji-id='5310296284874159738'>✅</tg-emoji>\n"
                    f"<b>Rejected:</b> {dead_count} <tg-emoji emoji-id='5397890704062038337'>❌</tg-emoji>\n"
                    f"<b>━━━━━━━━━━━━━━━━━━━━━━</b>\n"
                    f"🌐 <b>Proxies Used:</b> {len(_PROXY_POOL)} | <b>Bad:</b> {len(BAD_PROXIES)}"
                    f"{dup_final}",
                    parse_mode="HTML"
                )
            except Exception:
                pass

        await bot.send_document(
            chat_id=chat_id,
            document=FSInputFile(filename),
            caption=f"📜 <b>{command_name} Report (Deduplicated)</b>",
            parse_mode="HTML"
        )
        
        try:
            os.remove(filename)
        except:
            pass
            
    except Exception as e:
        await bot.send_message(chat_id=chat_id, text=f"<tg-emoji emoji-id='5397890704062038337'>❌</tg-emoji> <b>Error:</b> {e}")

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# COMMAND 1: /sitechk (Audit & Clean Sites)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

@router.message(Command("sitechk"))
async def sitechk_command(message: types.Message):
    """Audit existing sites - removes dead ones and deduplicates"""
    user_id = message.from_user.id
    if not is_admin(user_id):
        await message.answer("⛔ <b>You are not authorized.</b>", parse_mode="HTML")
        return

    bot = message.bot
    chat_id = message.chat.id

    sites = await asyncio.to_thread(read_sites)
    if not sites:
        await message.answer("📭 <b>No sites found in sites.txt</b>", parse_mode="HTML")
        return

    status_msg = await message.answer(
        f"🔄 <b>Starting Audit on {len(sites)} Sites...</b>\n"
        f"<b>━━━━━━━━━━━━━━━━━━━━━━</b>\n"
        f"🔄 <b>Checked:</b> <code>0/{len(sites)}</code>\n"
        f"<tg-emoji emoji-id='5310296284874159738'>✅</tg-emoji> <b>Kept ($0-20):</b> <code>0</code>\n"
        f"<tg-emoji emoji-id='5397890704062038337'>❌</tg-emoji> <b>Rejected:</b> <code>0</code>\n"
        f"🌐 <b>Proxies:</b> <code>{len(_PROXY_POOL)}</code>",
        parse_mode="HTML"
    )

    asyncio.create_task(
        run_site_checker(
            bot,
            chat_id,
            sites,
            command_name="Audit",
            status_message_id=status_msg.message_id,
            user_id=user_id,
        )
    )

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# COMMAND 2: /addsite (Add & Verify New Sites)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

@router.message(Command("addsite"))
async def addsite_command(message: types.Message):
    """Add new sites from uploaded file - automatically skips duplicates"""
    user_id = message.from_user.id
    if not is_admin(user_id):
        await message.answer("⛔ <b>You are not authorized.</b>", parse_mode="HTML")
        return

    bot = message.bot
    chat_id = message.chat.id

    doc = message.document
    if not doc:
        if message.reply_to_message:
            doc = message.reply_to_message.document
    
    if not doc:
        await message.answer(
            "<tg-emoji emoji-id='5350572310627632617'>⚠️</tg-emoji> <b>Please reply to a file or upload a file containing sites with /addsite.</b>",
            parse_mode="HTML"
        )
        return

    # Download file content
    try:
        file_info = await bot.get_file(doc.file_id)
        
        destination = io.BytesIO()
        await bot.download_file(file_info.file_path, destination)
        
        destination.seek(0)
        byte_content = destination.read()
        text = byte_content.decode('utf-8', errors='ignore')
        
        # Extract URLs
        url_pattern = r'(https?://\S+)'
        new_sites = []
        lines = text.split('\n')
        
        for line in lines:
            match = re.search(url_pattern, line)
            if match:
                url = match.group(1)
                url = url.rstrip('.,;:!?)\'"')
                new_sites.append(url)
        
        # Remove duplicates from uploaded file itself
        new_sites = list(set(new_sites))
        
        if not new_sites:
            await message.answer("<tg-emoji emoji-id='5397890704062038337'>❌</tg-emoji> <b>No valid sites found in file.</b>", parse_mode="HTML")
            return
            
    except Exception as e:
        logging.error(f"Error downloading file: {e}", exc_info=True)
        await message.answer(f"<tg-emoji emoji-id='5397890704062038337'>❌</tg-emoji> <b>Error reading file:</b> {e}", parse_mode="HTML")
        return

    # Send initial status
    status_msg = await message.answer(
        f"🔄 <b>Starting Addition of {len(new_sites)} Sites...</b>\n"
        f"<b>━━━━━━━━━━━━━━━━━━━━━━</b>\n"
        f"🔄 <b>Checked:</b> <code>0/{len(new_sites)}</code>\n"
        f"<tg-emoji emoji-id='5310296284874159738'>✅</tg-emoji> <b>Added ($0-20):</b> <code>0</code>\n"
        f"<tg-emoji emoji-id='5397890704062038337'>❌</tg-emoji> <b>Rejected:</b> <code>0</code>\n"
        f"<tg-emoji emoji-id='5397890704062038337'>🚫</tg-emoji> <b>Duplicates:</b> <code>0</code>\n"
        f"🌐 <b>Proxies:</b> <code>{len(_PROXY_POOL)}</code>",
        parse_mode="HTML"
    )

    asyncio.create_task(
        run_site_checker(
            bot,
            chat_id,
            new_sites,
            command_name="Adding",
            status_message_id=status_msg.message_id,
            user_id=user_id,
        )
    )

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# COMMAND 3: /siteall (List All Sites)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

@router.message(Command("siteall"))
async def siteall_command(message: types.Message):
    """Download full list of all sites (automatically deduplicated)"""
    user_id = message.from_user.id
    if not is_admin(user_id):
        await message.answer("⛔ <b>You are not authorized.</b>", parse_mode="HTML")
        return

    sites = await asyncio.to_thread(read_sites)
    if not sites:
        await message.answer("📭 <b>sites.txt is empty.</b>", parse_mode="HTML")
        return

    filename = f"full_sites_list_{int(time.time())}.txt"
    
    try:
        def _write_file():
            with open(filename, "w", encoding="utf-8") as f:
                f.write(f"Total Sites: {len(sites)} (Deduplicated)\n\n")
                f.write("\n".join(sites))
        
        await asyncio.to_thread(_write_file)
        
        await message.answer_document(
            document=FSInputFile(filename),
            caption=f"📜 <b>Total Sites:</b> <code>{len(sites)}</code> <tg-emoji emoji-id='5310296284874159738'>✨</tg-emoji> (No Duplicates)",
            parse_mode="HTML"
        )
        os.remove(filename)
    except Exception as e:
        await message.answer(f"<tg-emoji emoji-id='5397890704062038337'>❌</tg-emoji> <b>Error:</b> {e}", parse_mode="HTML")

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# COMMAND 4: /removeall (Remove All Sites)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

@router.message(Command("removeall"))
async def removeall_command(message: types.Message):
    """Clear all sites from sites.txt"""
    user_id = message.from_user.id
    if not is_admin(user_id):
        await message.answer("⛔ <b>You are not authorized.</b>", parse_mode="HTML")
        return

    sites = await asyncio.to_thread(read_sites)
    if not sites:
        await message.answer("📭 <b>sites.txt is already empty.</b>", parse_mode="HTML")
        return

    try:
        def _clear_file():
            with open("sites.txt", "w", encoding="utf-8") as f:
                pass
        
        await asyncio.to_thread(_clear_file)
        
        await message.answer(
            f"<tg-emoji emoji-id='5310296284874159738'>✅</tg-emoji> <b>All sites have been successfully removed.</b>\n\n"
            f"<b>Removed:</b> <code>{len(sites)}</code> sites",
            parse_mode="HTML"
        )
    except Exception as e:
        await message.answer(f"<tg-emoji emoji-id='5397890704062038337'>❌</tg-emoji> <b>Error:</b> {e}", parse_mode="HTML")

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# COMMAND 5: /dedupe (Force Deduplicate)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

@router.message(Command("dedupe"))
async def dedupe_command(message: types.Message):
    """Force deduplicate sites.txt"""
    user_id = message.from_user.id
    if not is_admin(user_id):
        await message.answer("⛔ <b>You are not authorized.</b>", parse_mode="HTML")
        return
    
    sites = await asyncio.to_thread(read_sites)
    
    if not sites:
        await message.answer("📭 <b>sites.txt is empty.</b>", parse_mode="HTML")
        return
    
    original_count = len(sites)
    
    # Force write (which auto-deduplicates)
    final_count = await asyncio.to_thread(write_sites, sites)
    
    removed = original_count - final_count
    
    if removed > 0:
        await message.answer(
            f"<tg-emoji emoji-id='5310296284874159738'>✨</tg-emoji> <b>Deduplication Complete!</b>\n\n"
            f"<b>Original:</b> <code>{original_count}</code>\n"
            f"<b>Removed:</b> <code>{removed}</code> duplicates\n"
            f"<b>Final:</b> <code>{final_count}</code> unique sites",
            parse_mode="HTML"
        )
    else:
        await message.answer(
            f"<tg-emoji emoji-id='5310296284874159738'>✅</tg-emoji> <b>No duplicates found!</b>\n\n"
            f"<b>Total Sites:</b> <code>{final_count}</code> (All Unique)",
            parse_mode="HTML"
        )

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# COMMAND 6: /proxyinfo (Check Proxy Status)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

@router.message(Command("proxyinfo"))
async def proxyinfo_command(message: types.Message):
    """Show proxy statistics"""
    user_id = message.from_user.id
    if not is_admin(user_id):
        await message.answer("⛔ <b>You are not authorized.</b>", parse_mode="HTML")
        return

    available = len(_PROXY_POOL) - len(BAD_PROXIES)
    
    text = (
        f"🌐 <b>Proxy Information</b>\n"
        f"<b>━━━━━━━━━━━━━━━━━━━━━━</b>\n"
        f"<tg-emoji emoji-id='5388849303982716989'>📊</tg-emoji> <b>Total Proxies:</b> <code>{len(_PROXY_POOL)}</code>\n"
        f"<tg-emoji emoji-id='5310296284874159738'>✅</tg-emoji> <b>Available:</b> <code>{available}</code>\n"
        f"<tg-emoji emoji-id='5397890704062038337'>❌</tg-emoji> <b>Bad/Dead:</b> <code>{len(BAD_PROXIES)}</code>\n"
        f"<b>━━━━━━━━━━━━━━━━━━━━━━</b>\n\n"
    )
    
    for i, proxy in enumerate(_PROXY_POOL, 1):
        status = "<tg-emoji emoji-id='5397890704062038337'>❌</tg-emoji> Dead" if proxy in BAD_PROXIES else "<tg-emoji emoji-id='5310296284874159738'>✅</tg-emoji> Live"
        if "@" in proxy:
            parts = proxy.split("@")
            host_part = parts[1] if len(parts) > 1 else proxy
            text += f"<code>{i}.</code> {host_part} - {status}\n"
        else:
            text += f"<code>{i}.</code> {proxy[:30]}... - {status}\n"
    
    await message.answer(text, parse_mode="HTML")

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# COMMAND 7: /resetproxy (Reset Bad Proxies)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

@router.message(Command("resetproxy"))
async def resetproxy_command(message: types.Message):
    """Reset all bad proxies back to available"""
    user_id = message.from_user.id
    if not is_admin(user_id):
        await message.answer("⛔ <b>You are not authorized.</b>", parse_mode="HTML")
        return

    global BAD_PROXIES
    cleared_count = len(BAD_PROXIES)
    BAD_PROXIES.clear()
    
    await message.answer(
        f"<tg-emoji emoji-id='5310296284874159738'>✅</tg-emoji> <b>Proxy List Reset!</b>\n\n"
        f"<b>Cleared:</b> <code>{cleared_count}</code> bad proxies\n"
        f"<b>Available Now:</b> <code>{len(_PROXY_POOL)}</code>",
        parse_mode="HTML"
    )
