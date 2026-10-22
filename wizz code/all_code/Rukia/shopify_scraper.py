"""
Local Shopify product scraper.

Ported from C:\\Users\\ASUS\\Desktop\\api\\api.py fetch_products() so the bot
can fetch the cheapest available variant DIRECTLY from the merchant site
instead of relying on the remote API to do it. Used by:

  * mass_gates/msh.py    → _prefetch_shopify_site_price() (price hint fallback)
  * gates/sh.py          → _local_price_hint()          (price hint for /sh)

Strategy (matches Desktop\\api\\api.py):
  1. Try product endpoints in order:
       /products.json?limit=50
       /products.json
       /collections/all.json
       /collections/all/products.json
       /search.json?q=*&type=product&limit=50
  2. If none yield a parseable product list, fall back to the
     Storefront GraphQL endpoint `/api/2024-01/graphql.json` with
     `sortKey: PRICE` and pick the cheapest available variant.

Returns the cheapest available variant under LOW_PRICE_THRESHOLD, or any
available variant if nothing is cheap enough. Returns False + reason on
anti-bot / rate-limit / network failure.

Proxy: pass in either raw `host:port:user:pass` (auto-converted to
`http://user:pass@host:port`) or the already-formatted
`http://user:pass@host:port` URL. `None` for direct connection.
"""

import asyncio
import json
import logging
import random
import time
from typing import Optional
from urllib.parse import urlparse

import aiohttp

LOG = logging.getLogger("shopify_scraper")

# ━━━ CONFIG ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

LOW_PRICE_THRESHOLD = 5.00  # Prefer variants <= this; otherwise fall back to any.

PRODUCT_ENDPOINTS = [
    "/products.json?limit=50",
    "/products.json",
    "/collections/all.json",
    "/collections/all/products.json",
    "/search.json?q=*&type=product&limit=50",
]

# Rotated per call so we don't look like a script.
PRODUCT_HEADERS = [
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/146.0.0.0 Safari/537.36 Edg/146.0.0.0',
    'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/146.0.0.0 Safari/537.36',
    'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/146.0.0.0 Safari/537.36',
    'Mozilla/5.0 (iPhone; CPU iPhone OS 17_5 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.5 Mobile/15E148 Safari/604.1',
]

# GraphQL query posted to /api/2024-01/graphql.json — sortKey:PRICE so the
# server returns the cheapest variants first (cheap = less likely to trigger
# merchant-side sale/expected-price mismatch on the checkout API later).
SHOPIFY_GRAPHQL_QUERY = (
    '{"query":"{ products(first: 50, sortKey: PRICE, reverse: false) {'
    ' edges { node { id handle title onlineStoreUrl '
    ' variants(first: 50) { edges { node { id availableForSale price { amount currencyCode } } } } } } } }"}'
)


# ━━━ PROXY PARSING ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def _parse_proxy(proxy_str: Optional[str]) -> Optional[str]:
    """Convert host:port[:user:pass] → http://user:pass@host:port.

    If proxy_str already starts with http(s)://, pass it through.
    """
    if not proxy_str or not proxy_str.strip():
        return None
    p = proxy_str.strip()
    if p.startswith(("http://", "https://", "socks4://", "socks5://")):
        return p
    parts = p.split(":")
    if len(parts) == 2:
        host, port = parts
        return f"http://{host}:{port}"
    if len(parts) == 4:
        host, port, user, password = parts
        return f"http://{user}:{password}@{host}:{port}"
    return None


# ━━━ CORE: PICK CHEAPEST VARIANT ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

# Banknote floor — we never pick a variant cheaper than this for the
# `price=` cart-hint. Free/zero-price variants exist on most Shopify stores
# (samples, demos, marketing placeholders) and they break the merchant-side
# cartCreate with a $0.00 total, which then surfaces to the user as the
# embarrassing "Gateway ➛ Shopify 0.00 USD" line that we just fixed.
MIN_PRICE = 0.50


def _pick_variant(products: list, site_domain: str) -> Optional[dict]:
    """From a list of Shopify product dicts, pick the cheapest AVAILABLE
    variant under LOW_PRICE_THRESHOLD, or any available variant if nothing
    is cheap enough. Returns the same dict shape api.py's fetch_products
    returns: {site, price, variant_id, link}.

    Builds the link from `handle` because products.json doesn't include
    a `url` field on the product — we have to construct
    `{site}/products/{handle}` ourselves.

    Variants with price <= MIN_PRICE are skipped — they're usually $0
    marketing/samples on Shopify stores and break cartCreate when used
    as the cart-hint price (merchant returns $0.00 total). If a site has
    ONLY zero-priced variants, this function returns None and the caller
    falls through to whatever fallback it has (remote API price endpoint,
    etc).
    """
    low_price = float("inf")
    low_product: Optional[dict] = None
    any_price = float("inf")
    any_product: Optional[dict] = None

    for product in products:
        variants = product.get("variants") or []
        handle = product.get("handle") or ""

        # Build canonical product URL from handle (products.json doesn't ship `url`).
        if handle:
            if site_domain.startswith(("http://", "https://")):
                link = f"{site_domain.rstrip('/')}/products/{handle}"
            else:
                link = f"https://{site_domain}/products/{handle}"
        else:
            online = product.get("onlineStoreUrl") or product.get("url") or ""
            link = online if online else ""

        for variant in variants:
            if not variant.get("available", True):
                continue
            try:
                raw_price = variant.get("price", "0")
                if isinstance(raw_price, str):
                    price = float(raw_price.replace(",", ""))
                else:
                    price = float(raw_price)
            except (ValueError, TypeError, AttributeError):
                continue

            # Skip free/underpriced variants — they break cartCreate and
            # leak as "Gateway … 0.00 USD" in the bot output.
            if price < MIN_PRICE:
                continue

            if price < any_price:
                any_price = price
                any_product = {
                    "price": f"{price:.2f}",
                    "variant_id": str(variant.get("id", "")),
                    "link": link,
                }

            if price <= LOW_PRICE_THRESHOLD and price < low_price:
                low_price = price
                low_product = {
                    "price": f"{price:.2f}",
                    "variant_id": str(variant.get("id", "")),
                    "link": link,
                }

    if low_product is not None:
        return low_product
    return any_product


# ━━━ MAIN ENTRY POINT ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

async def fetch_shopify_products(
    domain: str,
    proxy_str: Optional[str] = None,
    max_total_budget: float = 10.0,
) -> tuple:
    """Scrape the cheapest available variant from a Shopify site.

    Mirrors api.py::fetch_products:
      * normalises domain → https://…
      * tries PRODUCT_ENDPOINTS in order
      * on first 200-with-products, picks cheapest variant via _pick_variant
      * if all endpoints are blocked/empty, falls back to GraphQL
        `sortKey: PRICE` against /api/2024-01/graphql.json

    Args:
        domain: site URL ("site.myshopify.com" or full https://…)
        proxy_str: host:port[:user:pass] OR http://user:pass@host:port
        max_total_budget: hard time budget for the whole scrape (sec)

    Returns:
        On success: dict {site, price, variant_id, link}
        On failure: (False, "<b>error message</b>")
    """
    try:
        if not domain.startswith("http"):
            domain = "https://" + domain

        proxy_url = _parse_proxy(proxy_str)
        start = time.monotonic()
        ip_blocked = False
        last_error = None

        def _budget_left() -> float:
            return max(2.0, max_total_budget - (time.monotonic() - start))

        ua = random.choice(PRODUCT_HEADERS)
        browser_headers = {
            "User-Agent": ua,
            "Accept": "application/json, text/plain, */*",
            "Accept-Language": "en-US,en;q=0.9",
            "Accept-Encoding": "gzip, deflate, br",
            "sec-ch-ua": '"Chromium";v="146", "Not:A-Brand";v="24", "Microsoft Edge";v="146"',
            "sec-ch-ua-mobile": "?0",
            "sec-ch-ua-platform": '"Windows"',
            "sec-fetch-dest": "document",
            "sec-fetch-mode": "navigate",
            "sec-fetch-site": "none",
            "sec-fetch-user": "?1",
        }

        connector = aiohttp.TCPConnector(ssl=False, force_close=False)
        timeout = aiohttp.ClientTimeout(
            total=min(10.0, _budget_left()),
            connect=min(5.0, _budget_left()),
            sock_connect=min(5.0, _budget_left()),
            sock_read=min(10.0, _budget_left()),
        )

        async with aiohttp.ClientSession(
            connector=connector, timeout=timeout, headers=browser_headers
        ) as session:

            async def _try_endpoint(url: str):
                """Returns:
                    list[product] on success
                    '429' if rate-limited
                    '404' if not found
                    'block' on 403/503
                    'other' on other non-200
                    None on network/JSON error
                """
                nonlocal last_error
                try:
                    async with session.get(
                        url,
                        proxy=proxy_url,
                        timeout=aiohttp.ClientTimeout(total=min(5.0, _budget_left())),
                    ) as resp:
                        if resp.status == 200:
                            text = await resp.text()
                            if "/search.json" in url:
                                # Search endpoint returns {results: [...]} instead of
                                # {products: [...]} — handle both shapes.
                                try:
                                    d = json.loads(text)
                                except Exception:
                                    return None
                                results = d.get("results", d.get("products", []))
                                return results if results else None
                            try:
                                if text.lstrip().startswith("<"):
                                    return None
                                d = json.loads(text)
                            except Exception:
                                return None
                            return d.get("products", [])
                        if resp.status == 429:
                            last_error = "<b>429 Rate Limited</b>"
                            return "429"
                        if resp.status == 404:
                            last_error = "<b>404 Not Found</b>"
                            return "404"
                        if resp.status in (403, 503):
                            last_error = f"<b>{resp.status} Blocked</b>"
                            return "block"
                        last_error = f"<b>Error {resp.status}</b>"
                        return "other"
                except (asyncio.TimeoutError, aiohttp.ClientError) as e:
                    LOG.debug(f"[scraper] {url} → {type(e).__name__}: {e}")
                    return None
                except Exception as e:
                    LOG.debug(f"[scraper] {url} → {type(e).__name__}: {e}")
                    return None

            if not ip_blocked:
                for endpoint in PRODUCT_ENDPOINTS:
                    if time.monotonic() - start >= max_total_budget - 4.0:
                        break
                    url = f"{domain}{endpoint}"
                    products = await _try_endpoint(url)
                    if isinstance(products, list) and products:
                        pick = _pick_variant(products, domain)
                        if pick:
                            pick["site"] = domain
                            return pick
                    elif products == "429":
                        ip_blocked = True
                        break
                    elif products == "block":
                        ip_blocked = True
                        break
                    elif products == "404":
                        continue
                    elif products == "other":
                        continue

            if time.monotonic() - start >= max_total_budget - 4.0:
                return False, last_error or "<b>Proxied IP Blocked - Try Different Proxy</b>"

            # ━━━ GRAPHQL FALLBACK (sortKey: PRICE) ━━━━━━━━━━━━━━━━━━━━
            try:
                async with session.post(
                    f"{domain}/api/2024-01/graphql.json",
                    proxy=proxy_url,
                    timeout=aiohttp.ClientTimeout(total=min(5.0, _budget_left())),
                    data=SHOPIFY_GRAPHQL_QUERY,
                    headers={
                        "Content-Type": "application/json",
                        "Accept": "application/json",
                        "Origin": domain,
                        "Referer": domain,
                    },
                ) as resp:
                    if resp.status == 200:
                        try:
                            data = await resp.json()
                        except Exception:
                            data = None
                        if data:
                            edges = (
                                data.get("data", {})
                                .get("products", {})
                                .get("edges", [])
                            )
                            if edges:
                                products = []
                                for edge in edges:
                                    node = edge.get("node") or {}
                                    handle = node.get("handle", "")
                                    online_url = node.get("onlineStoreUrl") or (
                                        f"{domain}/products/{handle}" if handle else ""
                                    )
                                    variants_edges = (
                                        node.get("variants", {}).get("edges", [])
                                    )
                                    variants = []
                                    for ve in variants_edges:
                                        v_node = ve.get("node") or {}
                                        amount = v_node.get("price", {}).get("amount", "0")
                                        variants.append({
                                            "id": (v_node.get("id", "").split("/")[-1] or ""),
                                            "available": v_node.get("availableForSale", True),
                                            "price": amount,
                                        })
                                    products.append({
                                        "handle": handle,
                                        "onlineStoreUrl": online_url,
                                        "variants": variants,
                                    })
                                pick = _pick_variant(products, domain)
                                if pick:
                                    pick["site"] = domain
                                    return pick
                    elif resp.status == 429:
                        last_error = "<b>Proxied IP Blocked - Try Different Proxy</b>"
            except Exception as e:
                LOG.debug(f"[scraper] GraphQL fallback failed: {type(e).__name__}: {e}")

            return False, last_error or "<b>Proxied IP Blocked - Try Different Proxy</b>"

    except Exception as e:
        return False, f"error: {str(e)[:80]}"


# ━━━ CONVENIENCE: PRICE-ONLY WRAPPER ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

async def fetch_site_price_local(site: str, proxy: Optional[str] = None) -> Optional[float]:
    """Scrape the site locally and return just the price as a float.

    Used by _prefetch_shopify_site_price() in msh.py and as a local fallback
    for /sh in gates/sh.py — saves us a remote API round-trip when the
    merchant's anti-bot hasn't blocked our IP.

    Returns None on any failure (caller should fall back to the external API).
    """
    try:
        result = await fetch_shopify_products(site, proxy_str=proxy, max_total_budget=6.0)
        if isinstance(result, dict):
            price_str = result.get("price")
            try:
                return float(price_str) if price_str is not None else None
            except (ValueError, TypeError):
                return None
        return None
    except Exception as e:
        LOG.debug(f"[scraper] fetch_site_price_local failed: {type(e).__name__}: {e}")
        return None


if __name__ == "__main__":
    import sys

    async def _demo():
        site = sys.argv[1] if len(sys.argv) > 1 else "scrap-addicts.myshopify.com"
        proxy = sys.argv[2] if len(sys.argv) > 2 else None
        result = await fetch_shopify_products(site, proxy_str=proxy)
        print(json.dumps(result, indent=2, default=str))

    asyncio.run(_demo())
