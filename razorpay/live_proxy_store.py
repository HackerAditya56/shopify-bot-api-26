"""
live_proxy_store.py — Persistent live proxy manager.

Tests all proxies from Downloads/Telegram Desktop against Razorpay edge,
saves live ones to current directory (live_proxies.json), and reuses
them across restarts with periodic refresh.

Usage:
    from live_proxy_store import get_live_proxies, refresh_proxies
    proxies = get_live_proxies()  # returns cached list
    refresh_proxies()             # re-test all proxies
"""

import os, json, time, random, threading
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from curl_cffi import requests as cr

STORE_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'live_proxies.json')
RAZORPAY_EDGE = 'https://api.razorpay.com/'

PROXY_SOURCES = [
    '/home/zirconium/Downloads/Telegram Desktop/ALIVE_20260722_144922.txt',
    '/home/zirconium/Downloads/Telegram Desktop/CXCHK_LIVE_PROXIES_1785302884571.txt',
    '/home/zirconium/Downloads/Telegram Desktop/live_proxies.txt',
]

REFRESH_INTERVAL = 3600  # re-test all proxies every hour
MAX_CONCURRENT_TESTS = 50

_store_lock = threading.Lock()
_cache: list[str] = []
_last_refresh: float = 0.0


def _normalize_proxy(line: str) -> str | None:
    """Normalize any proxy format to host:port:user:pass."""
    line = line.strip()
    if not line or line.startswith('#'):
        return None
    if line.startswith('http://'):
        try:
            rest = line.replace('http://', '')
            auth, hp = rest.split('@', 1)
            u, pw = auth.split(':', 1)
            h, p = hp.split(':', 1)
            line = f"{h}:{p}:{u}:{pw}"
        except Exception:
            return None
    parts = line.split(':')
    if len(parts) != 4:
        return None
    return line


def _proxy_to_url(pxy: str) -> str:
    parts = pxy.split(':')
    return f"http://{parts[2]}:{parts[3]}@{parts[0]}:{parts[1]}"


def _test_one(pxy: str) -> tuple[str, str]:
    """Test one proxy. Returns (proxy, status)."""
    purl = _proxy_to_url(pxy)
    try:
        s = cr.Session(impersonate='chrome131', default_headers=True)
        s.proxies = {'http': purl, 'https': purl}
        r = s.get(RAZORPAY_EDGE, timeout=10)
        if r.status_code < 400:
            return (pxy, 'live')
        elif r.status_code == 403:
            return (pxy, 'waf_403')
        elif r.status_code == 406:
            return (pxy, 'waf_406')
        return (pxy, f'http_{r.status_code}')
    except Exception as e:
        es = str(e).lower()
        if 'timeout' in es or 'timed' in es:
            return (pxy, 'timeout')
        if 'refused' in es:
            return (pxy, 'dead')
        return (pxy, 'error')


def _load_all_raw() -> list[str]:
    """Load all proxies from all source files, deduplicate."""
    seen = set()
    proxies = []
    for fp in PROXY_SOURCES:
        if not os.path.exists(fp):
            continue
        with open(fp) as f:
            for line in f:
                pxy = _normalize_proxy(line)
                if pxy and pxy.split(':')[0] not in seen:
                    seen.add(pxy.split(':')[0])
                    proxies.append(pxy)
    return proxies


def refresh_proxies(verbose: bool = True) -> dict:
    """Test all proxies and update the live store. Returns stats dict."""
    global _cache, _last_refresh

    raw = _load_all_raw()
    if verbose:
        print(f"[proxy_store] Testing {len(raw)} proxies against Razorpay edge...")

    t0 = time.time()
    results: dict[str, str] = {}
    done = 0

    with ThreadPoolExecutor(max_workers=MAX_CONCURRENT_TESTS) as ex:
        futures = {ex.submit(_test_one, p): p for p in raw}
        for future in as_completed(futures):
            pxy, status = future.result()
            results[pxy] = status
            done += 1
            if verbose and done % 200 == 0:
                live = sum(1 for v in results.values() if v == 'live')
                print(f"  [{done}/{len(raw)}] live={live} ({live/done*100:.0f}%)", flush=True)

    live = [p for p, s in results.items() if s == 'live']
    elapsed = time.time() - t0

    # Save to disk
    store_data = {
        'updated': time.time(),
        'total_tested': len(results),
        'live_count': len(live),
        'proxies': live,
        'stats': {s: c for s, c in defaultdict(int, **{s: list(results.values()).count(s) for s in set(results.values())}).items()},
    }
    with open(STORE_FILE, 'w') as f:
        json.dump(store_data, f, indent=2)

    with _store_lock:
        _cache = live
        _last_refresh = time.time()

    if verbose:
        print(f"[proxy_store] {len(live)}/{len(raw)} live ({elapsed:.0f}s). Saved to {STORE_FILE}")

    return store_data


def get_live_proxies(min_count: int = 5) -> list[str]:
    """Get list of live proxies. Auto-refreshes if cache is stale or empty."""
    global _cache, _last_refresh

    with _store_lock:
        # First call: try loading from disk
        if not _cache and os.path.exists(STORE_FILE):
            try:
                with open(STORE_FILE) as f:
                    data = json.load(f)
                _cache = data.get('proxies', [])
                _last_refresh = data.get('updated', 0)
            except Exception:
                pass

        # Stale or empty: refresh
        now = time.time()
        if not _cache or (now - _last_refresh) > REFRESH_INTERVAL:
            # Release lock during slow I/O
            pass

    if not _cache or (time.time() - _last_refresh) > REFRESH_INTERVAL:
        refresh_proxies(verbose=True)

    with _store_lock:
        if len(_cache) < min_count:
            print(f"[proxy_store] WARNING: only {len(_cache)} live proxies (need {min_count})")
        return list(_cache)


def get_stats() -> dict:
    """Get proxy store stats for health endpoint."""
    with _store_lock:
        return {
            'live_count': len(_cache),
            'last_refresh': _last_refresh,
            'store_file': STORE_FILE,
            'sources': len(PROXY_SOURCES),
        }
