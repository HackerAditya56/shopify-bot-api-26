# url.py — Advanced Site Lookup / Gate Scanner Module
# Production-grade upgrade: aiogram architecture preserved,
# enhanced with caching, concurrency control, and expanded detection.

from __future__ import annotations

from live_emoji import plan_badge, dev_badge

import asyncio
import logging
import re
import time
from collections import defaultdict
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Set, Tuple
from urllib.parse import urlparse
from html import escape

import aiohttp
from aiogram import types
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from bs4 import BeautifulSoup

from database import PooledConn, get_user_credits, update_credits
from sub import get_premium_status

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# CONFIGURATION
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

RATE_LIMIT_SECONDS: int = 5
CACHE_TTL_SECONDS: int = 300          # 5-minute domain cache
MAX_CONCURRENT_REQUESTS: int = 20     # global semaphore cap
REQUEST_TIMEOUT_TOTAL: int = 20
REQUEST_TIMEOUT_CONNECT: int = 10
CREDITS_PER_SCAN: int = 1

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# RUNTIME STATE
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

_session: Optional[aiohttp.ClientSession] = None
_session_lock = asyncio.Lock()
_semaphore = asyncio.Semaphore(MAX_CONCURRENT_REQUESTS)

# Per-user rate-limit timestamps
user_last_command_time: Dict[int, float] = {}

# Domain-keyed result cache  {domain: {"data": dict, "ts": float}}
_domain_cache: Dict[str, dict] = {}

# Domains currently being fetched (prevents duplicate in-flight requests)
_in_flight: Set[str] = set()
_in_flight_lock = asyncio.Lock()

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# CMS DETECTION PATTERNS
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

CMS_PATTERNS: Dict[str, str] = {
    "Shopify Plus":               r"shopify-plus|cdn\.shopifycdn\.net/",
    "Shopify":                    r"cdn\.shopify\.com|shopify\.js|shopify\.com/cdn",
    "BigCommerce":                r"cdn\.bigcommerce\.com|bigcommerce\.com",
    "Wix":                        r"static\.parastorage\.com|wix\.com",
    "Squarespace":                r"static1\.squarespace\.com|squarespace-cdn\.com",
    "WooCommerce":                r"wp-content/plugins/woocommerce/|woocommerce",
    "Magento":                    r"static/version\d+/frontend/|magento/|Magento_",
    "PrestaShop":                 r"prestashop\.js|/themes/\w+/assets/|prestashop/",
    "OpenCart":                   r"catalog/view/theme|opencart/",
    "WordPress":                  r"wp-content|wp-includes/",
    "Joomla":                     r"media/jui|joomla\.js|media/system/js",
    "Drupal":                     r"sites/all/modules|drupal\.js|drupal\.settings",
    "TYPO3":                      r"typo3temp|typo3/",
    "Concrete5":                  r"concrete/js|concrete5/",
    "Umbraco":                    r"umbraco/|umbraco\.config/",
    "Sitecore":                   r"sitecore/content|sitecore\.js/",
    "Kentico":                    r"cms/getresource\.ashx|kentico\.js/",
    "Episerver":                  r"episerver/|episerver\.js/",
    "Salesforce Commerce Cloud":  r"demandware\.edgesuite\.net/",
    "Custom CMS":                 r'<meta[^>]+name=["\']generator["\'][^>]+content=["\']([^"\']+)["\']',
}

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# PAYMENT GATEWAY DATABASE
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

PAYMENT_GATEWAYS: List[str] = [
    # Global Leaders
    "PayPal", "Stripe", "Braintree", "Square", "Cybersource",
    "Authorize.Net", "2Checkout", "Adyen", "Worldpay", "SagePay",
    "Checkout.com", "Bolt", "Eway", "PayFlow", "Payeezy",
    # Subscription / SaaS
    "Paddle", "Recurly", "Chargebee", "Chargify",
    # European
    "Mollie", "Viva Wallet", "Klarna", "Skrill", "Neteller",
    "Paysafe", "Payeer", "Barclaycard", "Bizum",
    # BNPL
    "Affirm", "Afterpay", "Splitit", "Perpay", "Quadpay",
    "Laybuy", "Openpay", "ChargeAfter", "Sezzle",
    # eCommerce Platforms (payment features)
    "Shopify", "WooCommerce", "BigCommerce", "Magento",
    "OpenCart", "PrestaShop", "3DCart", "Ecwid", "Shift4Shop",
    "Shopware", "VirtueMart", "CS-Cart", "X-Cart", "LemonStand",
    # US Regional
    "Moneris", "Paytrace", "CardKnox", "BluePay",
    "CardConnect", "Clover", "FluidPay", "ChasePay", "AuroPay",
    "SagePayments", "USAePay", "EBizCharge", "CPay",
    "BlackBaud", "LawPay", "Converge", "PaySimple",
    "OceanPayments", "eProcessing", "HiPay", "PayJunction",
    "HostedPayments", "SecurePay", "Creo",
    # Digital Wallets
    "Apple Pay", "Google Pay", "Samsung Pay", "Cash App",
    "Alipay", "WeChat Pay", "Revolut", "Zelle",
    # South / Southeast Asia
    "Razorpay", "Cashfree", "Instamojo", "CCAvenue", "PayU",
    "PayUBiz", "PayUMoney", "Paytm", "PhonePe", "BharatPe",
    "BillDesk", "RazorpayX", "EasyPaisa", "GrabPay",
    "PayMaya", "MoMo", "TrueMoney", "GoPay", "JKOPay",
    "Midtrans", "MOLPay", "iPay88",
    # East Asia
    "KakaoPay", "Toss Payments", "NaverPay", "LinePay", "PayPay",
    # Latin America
    "Mercado Pago", "PagSeguro", "Culqi", "Pagar.me", "Kushki",
    # Middle East & Africa
    "PayFort", "MyFatoorah",
    # South Asia
    "UPI", "BharatQR", "FreeCharge", "MobiKwik", "Citrus Pay", "RuPay",
    # Global/Regional
    "Payoneer", "WebMoney", "Rapyd", "PayKun", "Pine Labs",
    "Cashalo", "Hoolah",
    # Crypto
    "BitPay", "Coinbase Commerce", "CoinGate", "CoinPayments",
    "Crypto.com Pay", "BTCPay Server", "NOWPayments", "OpenNode",
    "Utrust", "MoonPay", "Binance Pay", "CoinsPaid", "BitGo", "Flexa",
    # Enterprise
    "ACI Worldwide", "JP Morgan Payment Services",
    "Wells Fargo Payment Solutions", "Deutsche Bank Payments",
    "American Express Payment Gateway", "Discover Network",
    "UnionPay", "JCB Payment Gateway",
    # Misc
    "Rocketgate", "lemon-squeezy", "Auth.net", "Authnet",
]

# JS-specific smart detection patterns (regex → label)
JS_SMART_PATTERNS: List[Tuple[str, str]] = [
    (r"pk_live_[A-Za-z0-9]+|pk_test_[A-Za-z0-9]+",           "Stripe (Live Key)"),
    (r"braintree(?:\.client|\.paypal|client_token)",           "Braintree (JS SDK)"),
    (r"razorpay(?:\.js|checkout|_key|[_-]key)",               "Razorpay (JS SDK)"),
    (r"checkout\.shopify\.com|shopify-pay|shopify_pay",        "Shopify Payments"),
    (r"paypal\.com/sdk/js|paypal\.Buttons",                    "PayPal (SDK)"),
    (r"square\.com/js/form|squareup\.com/js",                  "Square (JS SDK)"),
    (r"cashfree(?:\.js|payments\.js|pg)",                       "Cashfree (JS)"),
    (r"phonepe\.com/apis|phonepe-sdk",                         "PhonePe (SDK)"),
    (r"midtrans(?:\.min\.js|snap\.js)",                        "Midtrans (JS)"),
    (r"payu(?:\.js|biz\.js|biz/api)",                         "PayU (JS)"),
]

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 3D SECURE / SECURITY PATTERNS
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

PATTERNS_3DS: List[str] = [
    r"3d\s*secure",
    r"verified\s*by\s*visa",
    r"mastercard\s*securecode",
    r"american\s*express\s*safekey",
    r"3ds2?(?!\w)",
    r"\bacsurl\b",
    r"\bpareq\b",
    r"three-domain-secure",
    r"secure_redirect",
    r"x-3ds",
    r"Cardinal(?:Commerce|Cruise)",
]

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# DATABASE HELPERS
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def ensure_gate_stats_columns() -> None:
    """Ensure site_lookups column exists in users table."""
    try:
        with PooledConn() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "ALTER TABLE users ADD COLUMN IF NOT EXISTS site_lookups INTEGER DEFAULT 0"
            )
            conn.commit()
        logging.info("[GATE] DB columns verified.")
    except Exception as exc:
        logging.error(f"[GATE] DB column check failed: {exc}")


ensure_gate_stats_columns()


async def update_lookup_stats(user_id: int) -> None:
    def _sync() -> None:
        try:
            with PooledConn() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    "UPDATE users SET site_lookups = site_lookups + 1 WHERE user_id = %s",
                    (user_id,),
                )
                conn.commit()
        except Exception as exc:
            logging.error(f"[GATE] Stats update error: {exc}")

    await asyncio.to_thread(_sync)


async def get_user_plan_name(user_id: int) -> str:
    """Return the user's plan label (FREE / specific plan name)."""
    premium_result = await asyncio.to_thread(get_premium_status, user_id)
    is_premium = premium_result[0] if isinstance(premium_result, tuple) else bool(premium_result)

    if not is_premium:
        return "FREE"

    def _sync_fetch() -> str:
        try:
            with PooledConn() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    "SELECT plan FROM receipts WHERE user_id = %s ORDER BY purchased_on DESC LIMIT 1",
                    (user_id,),
                )
                row = cursor.fetchone()
                return row[0].upper() if row else "PREMIUM"
        except Exception as exc:
            logging.error(f"[GATE] Plan fetch error: {exc}")
            return "PREMIUM"

    return await asyncio.to_thread(_sync_fetch)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# SESSION MANAGEMENT
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

async def get_session() -> aiohttp.ClientSession:
    """Return the shared aiohttp session, creating it if needed."""
    global _session
    async with _session_lock:
        if _session is None or _session.closed:
            connector = aiohttp.TCPConnector(
                limit=100,
                limit_per_host=10,
                ttl_dns_cache=300,
                enable_cleanup_closed=True,
            )
            timeout = aiohttp.ClientTimeout(
                total=REQUEST_TIMEOUT_TOTAL,
                connect=REQUEST_TIMEOUT_CONNECT,
            )
            _session = aiohttp.ClientSession(
                connector=connector,
                timeout=timeout,
                headers={"Connection": "keep-alive"},
            )
            logging.info("[GATE] HTTP session created.")
    return _session


async def close_session() -> None:
    global _session
    async with _session_lock:
        if _session and not _session.closed:
            await _session.close()
            logging.info("[GATE] HTTP session closed.")


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# SITE FETCHING WITH CACHING + CONCURRENCY CONTROL
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

_CHROME_HEADERS = {
    "accept": (
        "text/html,application/xhtml+xml,application/xml;"
        "q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8"
    ),
    "accept-language": "en-US,en;q=0.9",
    "accept-encoding": "gzip, deflate, br",
    "cache-control": "max-age=0",
    "sec-ch-ua": '"Chromium";v="140", "Not=A?Brand";v="24", "Google Chrome";v="140"',
    "sec-ch-ua-mobile": "?0",
    "sec-ch-ua-platform": '"Windows"',
    "sec-fetch-dest": "document",
    "sec-fetch-mode": "navigate",
    "sec-fetch-site": "none",
    "sec-fetch-user": "?1",
    "upgrade-insecure-requests": "1",
    "user-agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/140.0.0.0 Safari/537.36"
    ),
}


def _cache_get(domain: str) -> Optional[Tuple[Optional[int], Optional[str], Optional[dict]]]:
    entry = _domain_cache.get(domain)
    if entry and (time.monotonic() - entry["ts"]) < CACHE_TTL_SECONDS:
        return entry["status"], entry["html"], entry["headers"]
    return None


def _cache_set(domain: str, status: Optional[int], html: Optional[str], headers: Optional[dict]) -> None:
    _domain_cache[domain] = {"status": status, "html": html, "headers": headers, "ts": time.monotonic()}


async def fetch_site(url: str) -> Tuple[Optional[int], Optional[str], Optional[dict]]:
    """
    Fetch website HTML with:
      - shared session reuse
      - domain-level caching (5 min TTL)
      - in-flight deduplication
      - global concurrency semaphore
      - realistic Chrome desktop headers
      - graceful error classification
    """
    if not url.startswith(("http://", "https://")):
        url = "https://" + url

    domain = urlparse(url).netloc

    # Cache hit
    cached = _cache_get(domain)
    if cached:
        logging.debug(f"[GATE] Cache hit: {domain}")
        return cached

    # Wait if another coroutine is already fetching this domain
    wait_cycles = 0
    async with _in_flight_lock:
        if domain in _in_flight:
            # Release lock and poll until done
            pass
        else:
            _in_flight.add(domain)

    if domain not in _in_flight:
        # Another coroutine was fetching; wait for it
        for _ in range(40):
            await asyncio.sleep(0.25)
            cached = _cache_get(domain)
            if cached:
                return cached
            if domain not in _in_flight:
                break
        cached = _cache_get(domain)
        if cached:
            return cached

    # We hold the fetch token — go fetch
    session = await get_session()
    request_headers = {**_CHROME_HEADERS, "authority": domain}

    try:
        async with _semaphore:
            async with session.get(
                url,
                headers=request_headers,
                timeout=aiohttp.ClientTimeout(total=15, connect=8),
                allow_redirects=True,
                max_redirects=5,
                ssl=False,
            ) as resp:
                html = await resp.text(errors="replace")
                result = (resp.status, html, dict(resp.headers))
                _cache_set(domain, *result)
                return result

    except asyncio.TimeoutError:
        logging.warning(f"[GATE] Timeout: {url}")
        _cache_set(domain, None, None, None)
        return None, None, None
    except aiohttp.ClientSSLError:
        logging.warning(f"[GATE] SSL error: {url}")
        _cache_set(domain, None, None, None)
        return None, None, None
    except aiohttp.ClientConnectorError:
        logging.warning(f"[GATE] Connection refused / DNS failed: {url}")
        _cache_set(domain, None, None, None)
        return None, None, None
    except Exception as exc:
        logging.error(f"[GATE] Fetch error ({url}): {exc}")
        _cache_set(domain, None, None, None)
        return None, None, None
    finally:
        async with _in_flight_lock:
            _in_flight.discard(domain)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# DETECTION FUNCTIONS
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def detect_cms(html: str) -> str:
    """Detect CMS using ordered pattern matching with meta-generator fallback."""
    for cms, pattern in CMS_PATTERNS.items():
        match = re.search(pattern, html, re.IGNORECASE)
        if match:
            if cms == "Custom CMS":
                generator = match.group(1)
                return generator.strip() if generator else "Custom CMS"
            return cms
    return "Unknown / Custom"


def detect_gateways(html: str) -> str:
    """
    Detect payment gateways using:
      1. Word-boundary keyword matching against the large gateway list
      2. Smart JS pattern detection (API keys, SDK scripts, embedded widgets)
    Returns up to 8 unique detected gateways.
    """
    detected: List[str] = []
    html_lower = html.lower()

    # 1 — Keyword scan
    for gateway in PAYMENT_GATEWAYS:
        pattern = r"\b" + re.escape(gateway) + r"\b"
        if re.search(pattern, html, re.IGNORECASE):
            if gateway not in detected:
                detected.append(gateway)

    # 2 — Smart JS scan
    for js_pattern, label in JS_SMART_PATTERNS:
        if re.search(js_pattern, html, re.IGNORECASE):
            if label not in detected:
                detected.append(label)

    if not detected:
        return "None Detected"

    unique = list(dict.fromkeys(detected))  # preserve order, deduplicate
    return ", ".join(unique[:8])


def detect_security(html: str) -> str:
    """Detect 3D Secure / payment security indicators."""
    for pattern in PATTERNS_3DS:
        if re.search(pattern, html, re.IGNORECASE):
            return "3D Secure Enabled ✅"
    return "2D — No 3DS Detected ❌"


def detect_captcha(html: str) -> str:
    """Detect CAPTCHA / bot-challenge systems."""
    html_lower = html.lower()

    if "hcaptcha.com/1/api.js" in html_lower or "data-sitekey" in html_lower and "hcaptcha" in html_lower:
        return "hCaptcha ✅"
    if "turnstile.cloudflare.com" in html_lower or "cf-turnstile" in html_lower:
        return "Cloudflare Turnstile ✅"
    if re.search(r"recaptcha/api\.js|g-recaptcha|grecaptcha", html, re.IGNORECASE):
        return "reCAPTCHA ✅"
    if "hcaptcha" in html_lower:
        return "hCaptcha ✅"
    if re.search(r"\bcaptcha\b", html, re.IGNORECASE):
        return "Generic CAPTCHA ✅"
    return "No CAPTCHA ❌"


def detect_cloudflare(html: str, headers: Optional[dict] = None, status: Optional[int] = None) -> str:
    """
    Detect Cloudflare presence and differentiate between:
      - Active challenge (JS challenge, Turnstile, browser verification)
      - Passive CDN presence
      - No Cloudflare
    """
    if headers is None:
        headers = {}

    header_keys_lower = {k.lower() for k in headers}
    server_header = headers.get("Server", "").lower()

    cf_present = (
        "cf-ray" in header_keys_lower
        or "cf-cache-status" in header_keys_lower
        or "cloudflare" in server_header
    )

    if not cf_present:
        return "None ❌"

    # Determine if an active challenge is being served
    soup = BeautifulSoup(html, "html.parser")
    page_title = ""
    if soup.title and soup.title.string:
        page_title = soup.title.string.strip().lower()

    challenge_titles = [
        "just a moment",
        "attention required",
        "checking your browser",
        "enable javascript and cookies",
        "please wait while we verify",
        "ddos protection by cloudflare",
    ]
    challenge_body_patterns = [
        r"cf-browser-verification",
        r"cf_chl_",
        r"checking your browser",
        r"enable javascript and cookies",
        r"cloudflare ray id",
        r"turnstile\.cloudflare\.com",
    ]

    is_challenge = any(t in page_title for t in challenge_titles) or any(
        re.search(p, html, re.IGNORECASE) for p in challenge_body_patterns
    )

    if is_challenge:
        return "Active Challenge 🛡️"
    if status in (403, 503) and "cloudflare" in html.lower():
        return "Blocked by Cloudflare 🚫"
    return "CDN Present (No Challenge) 🔍"


def detect_graphql(html: str) -> str:
    """Detect GraphQL API usage via endpoints, clients, and inline queries."""
    patterns = [
        r"/graphql",
        r"graphqlendpoint",
        r"apollo(?:-client|-server|\.client|\.server)",
        r"__typename",
        r'query\s+\w+\s*\{',
        r'mutation\s+\w+\s*\{',
        r"hasura\.io",
        r"graphql-ws",
    ]
    for p in patterns:
        if re.search(p, html, re.IGNORECASE):
            return "GraphQL Detected ✅"
    return "No GraphQL ❌"


def detect_site_status(status: Optional[int]) -> str:
    """Classify HTTP status into a human-readable site status."""
    if status is None:
        return "⏳ Unreachable / Timeout"
    if status == 200:
        return "✅ Online"
    if 201 <= status < 300:
        return f"✅ Online ({status})"
    if 300 <= status < 400:
        return f"🔄 Redirect ({status})"
    if status == 401:
        return "🔒 Auth Required (401)"
    if status == 403:
        return "🚫 Forbidden (403)"
    if status == 404:
        return "❓ Not Found (404)"
    if status == 429:
        return "⛔ Rate Limited (429)"
    if 400 <= status < 500:
        return f"⚠️ Client Error ({status})"
    if status == 500:
        return "❌ Internal Server Error (500)"
    if status == 503:
        return "❌ Service Unavailable (503)"
    if 500 <= status < 600:
        return f"❌ Server Error ({status})"
    return f"ℹ️ HTTP {status}"


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# MAIN SCAN FUNCTION
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

async def scan_site(url: str) -> dict:
    """
    Fetch and fully analyse a website URL.
    Returns a result dict with all detection fields.
    """
    status, html, headers = await fetch_site(url)

    if not html:
        return {
            "status": status,
            "status_text": detect_site_status(status),
            "online": False,
            "cms": "N/A",
            "gateways": "N/A",
            "security": "N/A",
            "captcha": "N/A",
            "cloudflare": "N/A",
            "graphql": "N/A",
        }

    return {
        "status": status,
        "status_text": detect_site_status(status),
        "online": True,
        "cms":        detect_cms(html),
        "gateways":   detect_gateways(html),
        "security":   detect_security(html),
        "captcha":    detect_captcha(html),
        "cloudflare": detect_cloudflare(html, headers, status),
        "graphql":    detect_graphql(html),
    }


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# COMMAND HANDLERS (aiogram — preserved architecture)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

async def gate_command(message: types.Message) -> None:
    """
    /gate <url>
    Scan a website for CMS, payment gateways, security measures, and more.
    Costs 1 credit per scan with a 5-second per-user cooldown.
    """
    user = message.from_user
    user_id = user.id
    now = time.time()

    # — Rate limiting —
    last = user_last_command_time.get(user_id, 0)
    elapsed = now - last
    if elapsed < RATE_LIMIT_SECONDS:
        remaining = round(RATE_LIMIT_SECONDS - elapsed, 1)
        await message.reply(
            f"⚠️ <b>Slow down!</b>\n"
            f"Please wait <code>{remaining}s</code> before the next scan.",
            parse_mode="HTML",
        )
        return

    user_last_command_time[user_id] = now

    # — Parse URL from command or replied message —
    parts = message.text.split(maxsplit=1)
    url = parts[1].strip() if len(parts) > 1 else ""

    if not url and message.reply_to_message:
        reply_text = message.reply_to_message.text or message.reply_to_message.caption or ""
        match = re.search(r"https?://\S+", reply_text)
        if match:
            url = match.group(0)

    if not url:
        await message.reply(
            "❌ <b>No URL provided.</b>\n\n"
            "<b>Usage:</b> /gate <code>https://example.com</code>\n"
            "<b>Example:</b> /gate https://shopify.com",
            parse_mode="HTML",
            disable_web_page_preview=True,
        )
        return

    # — Credit check —
    current_credits = await asyncio.to_thread(get_user_credits, user_id)
    if current_credits is None or current_credits <= 0:
        await message.reply(
            "❌ <b>Insufficient Credits!</b>\n\n"
            "You have <b>0 credits</b> remaining.\n"
            "Use /plan to top up.",
            parse_mode="HTML",
        )
        return

    # — Fetch plan name and send processing placeholder —
    plan_name = await get_user_plan_name(user_id)

    proc_msg = await message.reply(
        "<pre>🔍 𝗦𝗰𝗮𝗻𝗻𝗶𝗻𝗴 𝘂𝗿𝗹…</pre>",
        parse_mode="HTML",
    )

    # — Run scan in background task so the handler returns immediately —
    asyncio.create_task(
        _process_scan(message, proc_msg, user, user_id, url, plan_name)
    )


async def _process_scan(
    message: types.Message,
    proc_msg: types.Message,
    user: types.User,
    user_id: int,
    url: str,
    plan_name: str,
) -> None:
    """Background task: run the scan, deduct credits, update stats, post result."""
    try:
        result = await scan_site(url)
        logging.info(f"[GATE] Scan done: {url} → {result.get('status')}")
    except Exception as exc:
        logging.error(f"[GATE] Scan exception ({url}): {exc}")
        result = {
            "online": False,
            "status_text": "❌ Scan Error",
            "cms": "N/A",
            "gateways": "N/A",
            "security": "N/A",
            "captcha": "N/A",
            "cloudflare": "N/A",
            "graphql": "N/A",
        }

    # — Deduct 1 credit —
    current_balance = await asyncio.to_thread(get_user_credits, user_id)
    if current_balance is not None:
        new_balance = max(0, current_balance - CREDITS_PER_SCAN)
        await asyncio.to_thread(update_credits, user_id, new_balance)

    # — Increment scan counter —
    await update_lookup_stats(user_id)

    # — Build result caption —
    display_url = url if len(url) <= 55 else url[:52] + "…"
    user_link = f'<a href="tg://user?id={user_id}">{escape(user.first_name)}</a>'
    dev_link = dev_badge()

    caption = (
        "<pre><b>𝐒𝐢𝐭𝐞 𝐋𝐨𝐨𝐤𝐮𝐩 𝐑𝐞𝐬𝐮𝐥𝐭𝐬</b></pre>\n"
        "━━━━━━━━━━━━━━━━\n"
        f"<b>𝐒𝐢𝐭𝐞</b> ➺ <code>{display_url}</code>\n"
        f"<b>𝐒𝐭𝐚𝐭𝐮𝐬</b> ➺ <b>{result.get('status_text', 'N/A')}</b>\n"
        "━━━━━━━━━━━━━━━━\n"
        f"<b>𝐂𝐌𝐒</b> ➺ <b>{result.get('cms', 'N/A')}</b>\n"
        f"<b>𝐆𝐚𝐭𝐞𝐰𝐚𝐲𝐬</b> ➺ <b>{result.get('gateways', 'N/A')}</b>\n"
        "━━━━━━━━━━━━━━━━\n"
        f"<b>𝐒𝐞𝐜𝐮𝐫𝐢𝐭𝐲</b> ➺ <b>{result.get('security', 'N/A')}</b>\n"
        f"<b>𝐂𝐚𝐩𝐭𝐜𝐡𝐚</b> ➺ <b>{result.get('captcha', 'N/A')}</b>\n"
        f"<b>𝐂𝐥𝐨𝐮𝐝𝐟𝐥𝐚𝐫𝐞</b> ➺ <b>{result.get('cloudflare', 'N/A')}</b>\n"
        f"<b>𝐆𝐫𝐚𝐩𝐡𝐐𝐋</b> ➺ <b>{result.get('graphql', 'N/A')}</b>\n"
        "━━━━━━━━━━━━━━━━\n"
        f"<b>𝐔𝐬𝐞𝐫</b> ➺ {user_link} <b>[{plan_name}]</b>\n"
        f"<b>𝐃𝐞𝐯</b> ➺ {dev_link}"
    )

    try:
        await proc_msg.edit_text(
            text=caption,
            parse_mode="HTML",
            disable_web_page_preview=True,
        )
    except Exception as exc:
        logging.error(f"[GATE] edit_text failed: {exc}")
        try:
            await message.reply(
                text=caption,
                parse_mode="HTML",
                disable_web_page_preview=True,
            )
        except Exception as exc2:
            logging.error(f"[GATE] reply fallback failed: {exc2}")


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# HELP COMMAND
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

async def gatehelp_command(message: types.Message) -> None:
    """Display usage and feature overview for the /gate command."""
    help_text = (
        "🔍 <b>Site Lookup — Help</b>\n"
        "━━━━━━━━━━━━━━━━\n"
        "<b>Command:</b> /gate\n"
        "<b>Usage:</b> /gate &lt;url&gt;\n\n"
        "<b>Examples:</b>\n"
        "<code>/gate https://shopify.com</code>\n"
        "<code>/gate example.com</code>\n\n"
        "<b>What it detects:</b>\n"
        "🔹 CMS platform (20+ supported)\n"
        "🔹 Payment gateways (150+ supported)\n"
        "🔹 Smart JS gateway detection (API keys / SDKs)\n"
        "🔹 3D Secure / security posture\n"
        "🔹 CAPTCHA system (reCAPTCHA, hCaptcha, Turnstile)\n"
        "🔹 Cloudflare (CDN vs active challenge)\n"
        "🔹 GraphQL API endpoints\n"
        "🔹 Site status (online / redirect / error)\n\n"
        "<b>Cost:</b> 1 credit per scan\n"
        "<b>Cooldown:</b> 5 seconds\n"
        "<b>Cache:</b> Results cached 5 min per domain"
    )
    await message.reply(help_text, parse_mode="HTML", disable_web_page_preview=True)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# CACHE MAINTENANCE UTILITY
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

async def cleanup_cache() -> None:
    """
    Periodic task to purge expired cache entries.
    Call from your bot startup:
        asyncio.create_task(gate_cache_cleanup_loop())
    """
    while True:
        await asyncio.sleep(120)
        now = time.monotonic()
        expired = [
            domain
            for domain, entry in list(_domain_cache.items())
            if now - entry["ts"] >= CACHE_TTL_SECONDS
        ]
        for domain in expired:
            _domain_cache.pop(domain, None)
        if expired:
            logging.debug(f"[GATE] Cache purged {len(expired)} expired entries.")


async def gate_cache_cleanup_loop() -> None:
    """Convenience wrapper — create_task this on bot start."""
    await cleanup_cache()
