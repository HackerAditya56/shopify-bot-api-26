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

MAX_CHECKS_PER_SITE = 5          # rotate site before the ~10 soft-block threshold
SITE_PAUSE_SECONDS = 60          # short velocity pause
SITE_ERROR_COOLDOWN_SECONDS = 300  # SERVER_ERROR -> 5 min site cooldown
MAX_PROXY_USES = 5               # rotate proxy before its IP reputation threshold
PROXY_PAUSE_MIN = 900            # 15-30 min random pause after 5 uses (403-safe)
PROXY_PAUSE_MAX = 1800


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


def load_sites():
    try:
        with open(RZ_SITES_FILE, encoding="utf-8") as f:
            return [l.strip() for l in f if l.strip().startswith("http")]
    except Exception:
        return []


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


def record_site_result(site, message):
    """`message` = API response message (lowercased). SERVER_ERROR cools the site."""
    global _server_error_count
    key = _site_key(site)
    m = (message or "").lower()
    with _site_guard:
        if "server error" in m or "site issue" in m:
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
        lock = _proxy_lock(cand)
        if lock.acquire(blocking=False):
            return cand, lock
    for _ in range(n):
        cand = _proxies[next(_proxy_ctr) % n]
        if _proxy_usable(cand):
            lock = _proxy_lock(cand)
            lock.acquire()
            return cand, lock
    return None, None


def release_proxy(proxy, lock):
    try:
        lock.release()
    except Exception:
        pass


def record_proxy_use(proxy):
    with _proxy_guard:
        uses = _proxy_uses.get(proxy, 0) + 1
        if uses >= MAX_PROXY_USES:
            _proxy_paused_until[proxy] = time.time() + random.randint(PROXY_PAUSE_MIN, PROXY_PAUSE_MAX)
            _proxy_uses[proxy] = 0
        else:
            _proxy_uses[proxy] = uses
