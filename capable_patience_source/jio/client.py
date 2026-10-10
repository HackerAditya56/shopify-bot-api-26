"""Jio Recharge -> PayGlocal automation client.

Full reverse-engineered flow (see flow.md). Uses curl_cffi for browser
impersonation + a rotating proxy pool + one persistent Session per flow
(connection pooling, per the spec).

Endpoints + crypto verified live on 2026-08-29.
"""
from __future__ import annotations

import base64
import json
import random
import re
import time
from dataclasses import dataclass, field
from urllib.parse import urlparse, parse_qs

from curl_cffi import requests as creq

from crypto import decrypt_public_key, encrypt_card_payload

CHROME = "chrome131"
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36")

JIO_PLAN_ID_19 = "1019863"  # verified live via recharge/search

# Real-browser profiles (impersonation + matching UA / sec-ch-ua). Picked randomly
# per session so every recharge looks like a different browser — the fixed
# chrome150+Linux-UA combo was being flagged GL-400-005 "high risk".
PROFILES = [
    {"imp": "chrome131", "ua": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
     "ch": '"Google Chrome";v="131", "Not_A Brand";v="8", "Chromium";v="131"', "plat": '"Windows"', "mob": "?0"},
    {"imp": "chrome124", "ua": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
     "ch": '"Google Chrome";v="124", "Not_A Brand";v="8", "Chromium";v="124"', "plat": '"macOS"', "mob": "?0"},
    {"imp": "chrome123", "ua": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
     "ch": '"Google Chrome";v="123", "Not_A Brand";v="8", "Chromium";v="123"', "plat": '"Linux"', "mob": "?0"},
    {"imp": "chrome120", "ua": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
     "ch": '"Google Chrome";v="120", "Not_A Brand";v="8", "Chromium";v="120"', "plat": '"Windows"', "mob": "?0"},
    {"imp": "edge101", "ua": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/101.0.0.0 Safari/537.36 Edg/101.0.0.0",
     "ch": '"Microsoft Edge";v="101", "Not_A Brand";v="8", "Chromium";v="101"', "plat": '"Windows"', "mob": "?0"},
]


class SessionFactory:
    """curl_cffi Session with a random real-browser profile + proxy."""

    def make(self, proxy: str | None = None) -> creq.Session:
        pf = random.choice(PROFILES)
        s = creq.Session(impersonate=pf["imp"], timeout=(12, 15))
        if proxy:
            s.proxies = {"http": proxy, "https": proxy}
        s.headers.update({
            "User-Agent": pf["ua"],
            "sec-ch-ua": pf["ch"],
            "sec-ch-ua-mobile": pf["mob"],
            "sec-ch-ua-platform": pf["plat"],
        })
        s._pf = pf
        return s


class JioClient:
    """STAGE 1+2: Jio selfcare -> JioPG payment-options -> gateway redirect."""

    BASE = "https://www.jio.com"
    PG = "https://pay.jio.com"

    def __init__(self, number: str, plan_id: str = JIO_PLAN_ID_19, proxy: str | None = None):
        self.number = number
        self.plan_id = plan_id
        self.session = SessionFactory().make(proxy)
        self.session.headers.update({"User-Agent": UA, "Accept-Language": "en-US,en;q=0.9"})

    def _api_headers(self) -> dict:
        return {
            "Accept": "*/*",
            "Referer": "https://www.jio.com/selfcare/plans/mobility/prepaid-plans-list/",
        }

    def bootstrap(self) -> None:
        """Load plans page -> set cookies."""
        r = self.session.get(
            f"{self.BASE}/selfcare/plans/mobility/prepaid-plans-list/",
            headers={"Accept": "text/html,application/xhtml+xml"},
        )
        r.raise_for_status()

    def mdm_reference(self) -> dict:
        r = self.session.get(
            f"{self.BASE}/api/jio-mdmdata-service/mdmdata/getMDMReferenceValue",
            headers=self._api_headers(),
        )
        return r.json()

    def auth_state(self) -> dict:
        r = self.session.get(
            f"{self.BASE}/api/jio-authenticate-service/authenticate/authJsonData",
            headers=self._api_headers(),
        )
        return r.json()

    def find_plan(self, amount: str = "19") -> dict | None:
        body = {"data": "", "validity": "", "price": "", "ott": "", "other": amount,
                "productType": "MOBILITY", "billingType": "1"}
        r = self.session.post(
            f"{self.BASE}/api/jio-mdmdata-service/mdmdata/recharge/search",
            headers={**self._api_headers(), "Content-Type": "application/json",
                     "Origin": self.BASE},
            json=body,
        )
        plans = []
        def walk(x):
            if isinstance(x, dict):
                if "amount" in x and "id" in x:
                    plans.append(x)
                for v in x.values():
                    walk(v)
            elif isinstance(x, list):
                for v in x:
                    walk(v)
        walk(r.json())
        for p in plans:
            if str(p.get("amount")) == amount:
                return p
        return None

    def initiate_recharge(self) -> str:
        """Returns the jio-common-servlet redirect URL."""
        r = self.session.get(
            f"{self.BASE}/api/jio-recharge-service/recharge/mobility/number/"
            f"{self.number}/plan/{self.plan_id}",
            headers=self._api_headers(),
        )
        if r.status_code != 200:
            raise RuntimeError(f"initiate_recharge HTTP {r.status_code}: {r.text[:200]}")
        try:
            pu = (r.json() or {}).get("paymentUrl", "")
        except Exception:
            pu = ""
        if not pu:
            raise RuntimeError("initiate_recharge: no paymentUrl (jio error/waf): " + r.text[:200])
        return pu

    def redirect_form(self, payment_url: str) -> dict:
        """GET the redirect servlet -> parse auto-submit form (param1 = JioPG token)."""
        if not payment_url or not payment_url.startswith("http"):
            return {"action": None, "fields": {}, "error": "bad paymentUrl", "body": str(payment_url)[:100]}
        r = self.session.get(payment_url, headers={"Accept": "text/html,application/xhtml+xml"})
        m = re.search(r"<form[^>]*action=['\"]([^'\"]+)['\"]", r.text)
        if not m:
            return {"action": None, "fields": {}, "error": "no redirect form", "body": r.text[:300]}
        action = m.group(1)
        fields = dict(re.findall(r"name=['\"]([^'\"]+)['\"][^>]*value=['\"]([^'\"]*)['\"]", r.text))
        return {"action": action, "fields": fields}

    def jiopg_payment_options(self, action: str, fields: dict) -> tuple[str, str]:
        """POST pay.jio.com/jiopg/v1/payment-options -> 302 -> JpgWebApp/home?paramx1&paramx2."""
        r = self.session.post(
            action,
            headers={"Content-Type": "application/x-www-form-urlencoded",
                     "Origin": self.BASE, "Referer": self.BASE + "/",
                     "Accept": "text/html,application/xhtml+xml"},
            data=fields,
            allow_redirects=False,
        )
        loc = r.headers.get("Location", "")
        q = parse_qs(urlparse(loc).query)
        return q.get("paramx1", [""])[0], q.get("paramx2", [""])[0]

    def payment_dashboard(self, paramx1: str, paramx2: str) -> dict:
        r = self.session.get(
            f"{self.PG}/jiopg/v1/payment-dashboard?paramx1={paramx1}&paramx2={paramx2}",
            headers={"Accept": "application/json, text/plain, */*",
                     "Referer": f"{self.PG}/JpgWebApp/home?paramx1={paramx1}&paramx2={paramx2}"},
        )
        d = r.json()
        d["params1_decoded"] = json.loads(base64.b64decode(d.get("params1", "")))
        return d


    def authorize_card(self, card_prefix: str, sku_code: str = "1019863",
                       payment_mode: str = "CCDC") -> dict:
        """POST /jiopg/v1/authorize-card-operation -> {token, invokeUrl, browserDetailsRequired}.

        Verified: skuCode = plan id (NOT the plan key), paymentMode = "CCDC",
        cardPrefix = first 6 digits of card number. cashbackAmount/copco must be None.
        """
        r = self.session.post(
            f"{self.PG}/jiopg/v1/authorize-card-operation",
            headers={"Accept": "application/json", "content-type": "application/json",
                     "Content-Type": "application/json",
                     "Referer": f"{self.PG}/JpgWebApp/home"},
            json={"paymentMode": payment_mode, "cardPrefix": card_prefix,
                  "isEMISelected": False, "viewOffer": False, "skuCode": sku_code,
                  "cashbackAmount": None, "copco": None, "isStoreCreditSelected": False},
        )
        return r.json()

    def on_ccdc_confirmation(self, token: str, invoke_url: str, card: dict,
                             browser_details: dict | None = None) -> dict:
        """POST the on-ccdc-confirmation invoke URL with x-token header + card details.

        card = {cardNumber, cardExpiry(MM/YY), cardName, cardType}; cvv separate.
        """
        bd = browser_details or {
            "browserHeader": "application/json", "browserJavaEnabled": False,
            "browserJavascriptEnabled": True, "browserLanguage": "en-US",
            "browserColorDepth": 24, "browserScreenHeight": 1080,
            "browserScreenWidth": 1920, "browserTz": -330,
            "browserUserAgent": UA,
        }
        body = {
            "cvvNumber": card["cvv"], "cashBackApplied": "Y",
            "isTrxnStatusCheckEnable": "N", "seqId": "", "ccRoutePg": "",
            "paymentMode": "CCDC", "offerAppliedByCust": False,
            "viewOffer": False, "offerCode": None,
            "cardNumber": card["cardNumber"],
            "expiryMonth": card["expiryMonth"], "expiryYear": card["expiryYear"],
            "cardHolderName": card.get("cardHolderName", ""),
            "cardType": card.get("cardType", ""),
            "cardTypeText": card.get("cardTypeText", card["cardNumber"][:6]),
            "customerCardTypeValue": card.get("customerCardTypeValue", card.get("cardType", "")),
            "userCardSaveConsent": False, "browserDetails": bd,
        }
        r = self.session.post(
            invoke_url,
            headers={"Accept": "application/json", "content-type": "application/json",
                     "x-token": token, "Origin": self.PG},
            json=body,
        )
        return r.json()


class PayGlocalClient:
    """STAGE 3: PayGlocal card payment (DC -> risk/fp -> key -> paynow -> ipay)."""

    def __init__(self, xgl_token: str, proxy: str | None = None):
        self.token = xgl_token
        self.session = SessionFactory().make(proxy)
        pf = getattr(self.session, "_pf", None)
        self.ua = pf["ua"] if pf else UA
        self.session.headers.update({"Accept-Language": "en-US,en;q=0.9",
                                     "Referer": f"https://api.payglocal.com/gl/payflow-ui/?x-gl-token={xgl_token}"})

    def _url(self, path: str) -> str:
        return f"https://api.payglocal.com{path}?x-gl-token={self.token}"

    def dc(self) -> dict:
        r = self.session.get(self._url("/gl/v2/payments/redirect/dc"),
                             headers={"Accept": "application/json, text/plain, */*",
                                      "x-gl-current-host": "api.payglocal.com",
                                      "x-gl-gid": "gl_payflow-ui",
                                      "x-gl-pb-tag-id": "",
                                      "x-gl-previous-host": "https://pay.easebuzz.in/",
                                      "x-gl-referrer-mismatch": "false",
                                      "x-gl-trusted-referrer": "https://pay.easebuzz.in"})
        return r.json()

    def risk_fp(self, request_id: str, visitor_id: str) -> dict:
        r = self.session.post(
            self._url("/gl/v1/payments/risk/fp"),
            headers={"Content-Type": "application/json", "Accept": "application/json"},
            json={"requestId": request_id, "visitorId": visitor_id,
                  "visitorFound": True, "confidenceScore": 1},
        )
        return r.json()

    def get_public_key(self, key_blob: str, visitor_id: str) -> str:
        return decrypt_public_key(key_blob, visitor_id)

    def paynow(self, kid: str, payload: dict, public_key_pem: str) -> dict:
        jwe = encrypt_card_payload(payload, public_key_pem)
        r = self.session.post(
            self._url("/gl/v2/payments/pd/paynow"),
            headers={"Content-Type": "application/json", "Accept": "application/json",
                     "Origin": "https://api.payglocal.com"},
            json={"isEnc": "true", "kid": kid, "payload": jwe},
        )
        return r.json()

    def ipay(self, kid: str, payload: dict, public_key_pem: str) -> dict:
        jwe = encrypt_card_payload(payload, public_key_pem)
        r = self.session.post(
            self._url("/gl/v2/payments/dc/ipay"),
            headers={"Content-Type": "application/json", "Accept": "application/json",
                     "Origin": "https://api.payglocal.com"},
            json={"isEnc": "true", "kid": kid, "payload": jwe},
        )
        return r.json()


    # ── Plain (isEnc=false) flow — matches the @Real_Stocky reference ─────────
    def paynow_plain(self, browser_details: dict) -> dict:
        """Payment init with NO card data (billing + browser only)."""
        r = self.session.post(
            self._url("/gl/v2/payments/pd/paynow"),
            headers={"Content-Type": "application/json", "Accept": "application/json",
                     "Origin": "https://api.payglocal.com"},
            json={"isEnc": "false", "payload": {
                "customerCurrency": "INR", "saveCurrencyPreference": False,
                "browserDetails": browser_details,
                "billingData": {"addressCountry": "FR"}, "shippingData": {},
                "agreedOnTnCs": True}},
        )
        return r.json()

    def ipay_plain(self, kid: str, card: dict, browser_details: dict) -> dict:
        """Terminal charge with the card in PLAIN json (no JWE)."""
        r = self.session.post(
            self._url("/gl/v2/payments/dc/ipay"),
            headers={"Content-Type": "application/json", "Accept": "application/json",
                     "Origin": "https://api.payglocal.com"},
            json={"isEnc": "false", "kid": kid, "payload": {
                "cardNumber": card["number"],
                "expiryMonth": card["expiryMonth"],
                "expiryYear": card["expiryYear"],
                "cvv": card["cvv"],
                "cardHolderName": "matt henry",
                "saveCard": False,
                "browserDetails": browser_details}},
        )
        return r.json()


def build_card_payload(card: dict, customer_currency: str = "INR",
                       browser_details: dict | None = None,
                       cardinal_request: dict | None = None) -> dict:
    """The JSON that gets JWE-encrypted for paynow/ipay (from payflow UI JS)."""
    em = str(card.get("expiryMonth") or card.get("expiry_month") or "")
    ey = str(card.get("expiryYear") or card.get("expiry_year") or "")
    p = {
        "cardData": {
            "number": card["number"],
            "expiryMonth": em,
            "expiryYear": ey,
            "securityCode": card["cvv"],
        },
        "agreedOnSaveCard": "false",
        "sessionCardId": None,
        "saveCurrencyPreference": None,
        "customerCurrency": customer_currency,
        "browserDetails": browser_details or {
            "userAgent": UA, "screenWidth": 1920, "screenHeight": 1080,
            "colorDepth": 24, "timezone": "Asia/Kolkata", "language": "en-US",
            "platform": "Linux x86_64", "hardwareConcurrency": 8,
            "deviceMemoryGb": 8, "javaEnabled": False, "cookiesEnabled": True,
            "screenAvailWidth": 1920, "screenAvailHeight": 1080,
        },
    }
    if customer_currency == "INR":
        p["fallbackToInrCurrency"] = True
    if cardinal_request:
        p["cardinalRequest"] = cardinal_request
    return p
