"""
rz_rotation.py — shared site + proxy rotation for /rz and /mrz.

Keeps Razorpay checks 403-free by staying under the measured thresholds:
  - site soft block: SERVER_ERROR at ~10-11 checks/site  -> rotate before 5, cool 5min on sight
  - IP hard block: 403 on dirty IPs                       -> rotate proxy every 5 checks, pause 1-3min
One in-flight request per proxy (bursts on a single exit are what trip the WAF).

Proxy source: rz_pxy.txt (user-maintained, one proxy per line).
Site source:   rz_site.txt (user-maintained, one URL per line).
"""
import os
import time
import random
import itertools
import threading

_BOT_DIR = os.path.dirname(os.path.abspath(__file__))
RZ_PROXY_FILE = os.path.join(_BOT_DIR, "rz_pxy.txt")
RZ_SITES_FILE = os.path.join(_BOT_DIR, "rz_site.txt")

MAX_CHECKS_PER_SITE = 2          # 2 checkouts per site, then pause (human-like: 2 CCs then wait)
SITE_PAUSE_SECONDS = 30          # 30s cooldown before the site re-enters the pool
SITE_ERROR_COOLDOWN_SECONDS = 120  # SERVER_ERROR / site-change -> 2 min site cooldown
SITE_NOSTOCK_COOLDOWN_SECONDS = 86400  # "no stock left" -> 24h site cooldown

# rotating residential proxies (fresh IP per request) never get IP-paused
_ROTATING_HINTS = ("proxyempire", "iproyal", "brightdata", "brd.superproxy", "marsproxies")
MAX_PROXY_USES = 5               # rotate proxy before its IP reputation threshold
PROXY_PAUSE_MIN = 120            # 2-5 min normal pause after 5 uses
PROXY_PAUSE_MAX = 300
PROXY_403_PAUSE_MIN = 900     # 15-45 min pause when the proxy hits a WAF 403
PROXY_403_PAUSE_MAX = 2700


def _site_key(site):
    k = (site or "").strip().lower().rstrip("/")
    for p in ("http://", "https://"):
        if k.startswith(p):
            k = k[len(p):]
    return k


# ── Sites ─────────────────────────────────────────────────────────────────
_sites = []
_site_ctr = itertools.count()
_site_uses = {}
_site_paused_until = {}
_site_error_until = {}
_site_guard = threading.Lock()


_SITE_PRICES = {}


def load_sites():
    global _SITE_PRICES
    try:
        with open(RZ_SITES_FILE, encoding="utf-8") as f:
            sites = []
            for l in f:
                l = l.strip()
                if not l.startswith("http"):
                    continue
                if "|" in l:
                    url, price = l.split("|", 1)
                    url = url.strip()
                    try:
                        _SITE_PRICES[_site_key(url)] = int(price) * 100
                    except Exception:
                        pass
                    sites.append(url)
                else:
                    sites.append(l)
            return sites
    except Exception:
        return []


def get_site_price(site):
    """Fixed price (paise) for a site marked `url|price` in rz_site.txt, else None."""
    return _SITE_PRICES.get(_site_key(site))


def refresh_sites(exclude_keys=()):
    """(Re)load sites, dropping any keys in `exclude_keys` (e.g. API site cooldowns)."""
    global _sites
    excl = {_site_key(x) for x in exclude_keys}
    _sites = [s for s in load_sites() if _site_key(s) not in excl]
    return _sites


def next_site():
    global _sites
    if not _sites:
        _sites = load_sites()
    if not _sites:
        return None
    n = len(_sites)
    for _ in range(n):
        s = _sites[next(_site_ctr) % n]
        key = _site_key(s)
        with _site_guard:
            if time.time() < _site_error_until.get(key, 0):
                continue
            if time.time() >= _site_paused_until.get(key, 0):
                return s
    return None


_server_error_count = 0
_server_error_lock = threading.Lock()


def _is_rotating(proxy):
    h = (proxy or "").lower()
    return any(k in h for k in _ROTATING_HINTS)


def record_site_result(site, message):
    """`message` = API response message (lowercased). SERVER_ERROR cools the site."""
    global _server_error_count
    key = _site_key(site)
    m = (message or "").lower()
    with _site_guard:
        if "no stock" in m or "out of stock" in m:
            # merchant ran out of stock -> park the site for 24h
            _site_error_until[key] = time.time() + SITE_NOSTOCK_COOLDOWN_SECONDS
            _site_uses.pop(key, None)
            _site_paused_until.pop(key, None)
            return
        if ("server error" in m or "site issue" in m or "something went wrong" in m
                or "site change" in m or "should not be sent" in m or "extra field" in m
                or "order failed" in m or "merchant blocked" in m or "site unavailable" in m):
            _site_error_until[key] = time.time() + SITE_ERROR_COOLDOWN_SECONDS
            _site_uses.pop(key, None)
            _site_paused_until.pop(key, None)
            with _server_error_lock:
                _server_error_count += 1
            return
        uses = _site_uses.get(key, 0) + 1
        _site_uses[key] = uses
        if uses >= MAX_CHECKS_PER_SITE:
            _site_paused_until[key] = time.time() + SITE_PAUSE_SECONDS
            _site_uses[key] = 0


def status() -> dict:
    """Snapshot of the rotation engine for the /rzg monitor."""
    global _proxies, _sites, _server_error_count
    if not _proxies:
        _proxies = load_proxies()
    if not _sites:
        _sites = load_sites()
    now = time.time()
    with _proxy_guard:
        proxies_total = len(_proxies)
        proxies_paused = sum(1 for p in _proxies if now < _proxy_paused_until.get(p, 0))
    with _site_guard:
        sites_total = len(_sites)
        sites_error = sum(1 for s in _sites if now < _site_error_until.get(_site_key(s), 0))
        sites_paused = sum(1 for s in _sites if now < _site_paused_until.get(_site_key(s), 0))
    with _server_error_lock:
        se_count = _server_error_count
    return {
        "proxies_total": proxies_total,
        "proxies_paused": proxies_paused,
        "proxies_usable": proxies_total - proxies_paused,
        "sites_total": sites_total,
        "sites_error_cooldown": sites_error,
        "sites_paused": sites_paused,
        "sites_usable": sites_total - sites_error - sites_paused,
        "server_error_count": se_count,
    }


# ── Proxies ───────────────────────────────────────────────────────────────
_proxies = []
_proxy_ctr = itertools.count()
_proxy_uses = {}
_proxy_paused_until = {}
_proxy_guard = threading.Lock()
_proxy_locks = {}
_proxy_locks_guard = threading.Lock()


def load_proxies():
    try:
        with open(RZ_PROXY_FILE, encoding="utf-8") as f:
            return [l.strip() for l in f if l.strip() and not l.strip().startswith("#")]
    except Exception:
        return []


def refresh_proxies():
    global _proxies
    _proxies = load_proxies()
    return _proxies


def _proxy_usable(proxy):
    with _proxy_guard:
        return time.time() >= _proxy_paused_until.get(proxy, 0)


def _proxy_lock(proxy):
    with _proxy_locks_guard:
        if proxy not in _proxy_locks:
            _proxy_locks[proxy] = threading.Lock()
        return _proxy_locks[proxy]


def acquire_proxy():
    """Return (proxy, lock) where proxy is free (not in-flight, not paused)."""
    global _proxies
    if not _proxies:
        _proxies = load_proxies()
    if not _proxies:
        return None, None
    n = len(_proxies)
    for _ in range(n):
        cand = _proxies[next(_proxy_ctr) % n]
        if not _proxy_usable(cand):
            continue
        if _is_rotating(cand):
            # rotating proxy -> fresh IP per request, allow concurrent (no lock)
            return cand, None
        lock = _proxy_lock(cand)
        if lock.acquire(blocking=False):
            return cand, lock
    for _ in range(n):
        cand = _proxies[next(_proxy_ctr) % n]
        if _proxy_usable(cand):
            if _is_rotating(cand):
                return cand, None
            lock = _proxy_lock(cand)
            lock.acquire()
            return cand, lock
    return None, None


def release_proxy(proxy, lock):
    try:
        lock.release()
    except Exception:
        pass


def pause_proxy_403(proxy):
    """WAF 403 -> pause this proxy 15-45 min (hard cooldown).
    Rotating proxies (fresh IP each request) are never paused."""
    if _is_rotating(proxy):
        return
    with _proxy_guard:
        _proxy_paused_until[proxy] = time.time() + random.randint(PROXY_403_PAUSE_MIN, PROXY_403_PAUSE_MAX)
        _proxy_uses[proxy] = 0


def record_proxy_use(proxy):
    if _is_rotating(proxy):
        return
    with _proxy_guard:
        uses = _proxy_uses.get(proxy, 0) + 1
        if uses >= MAX_PROXY_USES:
            _proxy_paused_until[proxy] = time.time() + random.randint(PROXY_PAUSE_MIN, PROXY_PAUSE_MAX)
            _proxy_uses[proxy] = 0
        else:
            _proxy_uses[proxy] = uses
