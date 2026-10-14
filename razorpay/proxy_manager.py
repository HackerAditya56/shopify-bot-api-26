"""
proxy_manager.py — Proxy pool database + bulk health checker.

Features:
  - Proxy pool DB (proxy_db.json): stores working proxies, auto-selected for checkouts
  - Threaded bulk testing: fast parallel validation against api.razorpay.com
  - Smart add: test first → live → pool | dead → discard
"""

from __future__ import annotations

import asyncio
import fcntl
import json
import os
import random
import time
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Optional

import curl_cffi.requests as curl_requests

# ── Configuration ──────────────────────────────────────────────────────────

# Data directory for proxy DB files.  Set PROXY_DATA_DIR env var to a Railway
# volume mount (e.g., /data) so proxy pool survives redeploys.
# Defaults to the app directory (ephemeral on Railway — wiped on redeploy).
_DATA_DIR = os.environ.get("PROXY_DATA_DIR", os.path.dirname(os.path.abspath(__file__)))
_APP_DIR = os.path.dirname(os.path.abspath(__file__))
os.makedirs(_DATA_DIR, exist_ok=True)

POOL_FILE = os.path.join(_DATA_DIR, "proxy_db.json")
DEAD_PROXY_FILE = os.path.join(_DATA_DIR, "proxy_dead.json")
CHECK_URL = "https://api.razorpay.com/"
CHECK_TIMEOUT = 10  # seconds — long enough for proxy CONNECT + TLS handshake

# ── Migration: copy old app-dir files to volume on first run ─────────────────

def _migrate_file(filename: str):
    """Copy a data file from old app-dir path to new data-dir if missing."""
    if _DATA_DIR == _APP_DIR:
        return  # same directory, no migration needed
    old_path = os.path.join(_APP_DIR, filename)
    new_path = os.path.join(_DATA_DIR, filename)
    if os.path.exists(new_path):
        return  # already migrated
    if os.path.exists(old_path):
        import shutil
        try:
            shutil.copy2(old_path, new_path)
        except Exception:
            pass

_migrate_file("proxy_db.json")
_migrate_file("api_keys.json")
_migrate_file("session_cache.json")

# ── Proxy pool database ────────────────────────────────────────────────────

_pool_lock = threading.Lock()
_pool: dict[str, dict] = {}
_pool_mtime: float = 0.0      # fast-path: skip JSON parse if file unchanged


def _load_pool():
    global _pool, _pool_mtime

    # FAST PATH: skip file read + JSON parse if another worker hasn't modified
    # the file.  mtime check is ~0.001ms vs ~5-50ms for full parse + lock.
    try:
        if os.path.exists(POOL_FILE):
            current_mtime = os.path.getmtime(POOL_FILE)
            if current_mtime <= _pool_mtime and _pool:
                return
    except Exception:
        pass

    lockfile = POOL_FILE + ".lock"
    try:
        with open(lockfile, "a") as lf:
            fcntl.flock(lf, fcntl.LOCK_SH)
            try:
                if os.path.exists(POOL_FILE):
                    current_mtime = os.path.getmtime(POOL_FILE)
                    with open(POOL_FILE) as f:
                        data = json.load(f)
                    with _pool_lock:
                        _pool = data.get("proxies", {})
                        _pool_mtime = current_mtime
                else:
                    with _pool_lock:
                        _pool = {}
                        _pool_mtime = 0.0
            finally:
                fcntl.flock(lf, fcntl.LOCK_UN)
    except Exception:
        with _pool_lock:
            _pool = {}


def _save_pool():
    tmp = POOL_FILE + ".tmp"
    lockfile = POOL_FILE + ".lock"
    try:
        with open(lockfile, "a") as lf:
            fcntl.flock(lf, fcntl.LOCK_EX)
            try:
                with _pool_lock:
                    data = {"proxies": dict(_pool)}
                with open(tmp, "w") as f:
                    json.dump(data, f, indent=2)
                os.replace(tmp, POOL_FILE)
            finally:
                fcntl.flock(lf, fcntl.LOCK_UN)
    except Exception:
        pass


def add_to_pool(host: str, port: str, user: str, password: str):
    """Add a working proxy to the live pool.

    Keys by host:port — each port on an InstantProxies gateway is a
    different exit IP, so they must be tracked independently.

    Reloads from file first to ensure cross-worker safety — another worker
    may have added proxies since this worker last loaded the pool."""
    _load_pool()  # cross-worker: sync from file before modifying
    key = f"{host.lower()}:{port}"
    with _pool_lock:
        _pool[key] = {
            "host": host.lower(),
            "port": port,
            "user": user,
            "pass": password,
            "full_url": f"{host.lower()}:{port}:{user}:{password}",
            "added_at": _pool.get(key, {}).get("added_at", time.time()),
            "last_used": _pool.get(key, {}).get("last_used", 0),
            "times_used": _pool.get(key, {}).get("times_used", 0),
        }
    _save_pool()


# ── Failure threshold — prevent rapid pool drain on transient errors ──────

FAILURE_COUNTS_FILE = os.path.join(_DATA_DIR, "proxy_failures.json")
FAILURE_THRESHOLD = 2  # consecutive failures before removing proxy from pool
# Reduced from 3 — a proxy flagged twice in a row is almost certainly
# permanently blocked by Razorpay WAF; keeping it only wastes retries.
_failure_lock = threading.Lock()
_failures_cache: dict[str, int] = {}
_failures_mtime: float = 0.0


def _load_failure_counts() -> dict[str, int]:
    """Read failure counts from shared file with fcntl for cross-worker safety.

    Uses mtime fast-path: skips JSON parse if file hasn't been modified since
    last read.  Failure counts change rarely (only on proxy failure), so this
    eliminates thousands of unnecessary file reads/sec under load.
    """
    global _failures_cache, _failures_mtime

    # FAST PATH: skip file read if it hasn't changed
    try:
        if os.path.exists(FAILURE_COUNTS_FILE):
            current_mtime = os.path.getmtime(FAILURE_COUNTS_FILE)
            if current_mtime <= _failures_mtime:
                return _failures_cache
    except Exception:
        pass

    lockfile = FAILURE_COUNTS_FILE + ".lock"
    try:
        with open(lockfile, "a") as lf:
            fcntl.flock(lf, fcntl.LOCK_SH)
            try:
                if os.path.exists(FAILURE_COUNTS_FILE):
                    current_mtime = os.path.getmtime(FAILURE_COUNTS_FILE)
                    with open(FAILURE_COUNTS_FILE) as f:
                        _failures_cache = json.load(f)
                    _failures_mtime = current_mtime
                    return _failures_cache
            finally:
                fcntl.flock(lf, fcntl.LOCK_UN)
    except Exception:
        pass
    return {}


def _save_failure_counts(counts: dict[str, int]):
    """Write failure counts to shared file atomically with fcntl exclusive lock."""
    tmp = FAILURE_COUNTS_FILE + ".tmp"
    lockfile = FAILURE_COUNTS_FILE + ".lock"
    try:
        with open(lockfile, "a") as lf:
            fcntl.flock(lf, fcntl.LOCK_EX)
            try:
                with open(tmp, "w") as f:
                    json.dump(counts, f)
                os.replace(tmp, FAILURE_COUNTS_FILE)
            finally:
                fcntl.flock(lf, fcntl.LOCK_UN)
    except Exception:
        pass


def _record_proxy_failure(proxy_host: str) -> bool:
    """Increment failure count.  Returns True if threshold exceeded (remove).

    File-backed for cross-worker visibility — in Gunicorn's 16-worker pre-fork
    mode, each process has its own memory space.  Without a shared file, Worker
    1 and 2 each see count=1 and none reach FAILURE_THRESHOLD=2."""
    key = proxy_host.lower()
    with _failure_lock:
        counts = _load_failure_counts()
        counts[key] = counts.get(key, 0) + 1
        exceeded = counts[key] >= FAILURE_THRESHOLD
        _save_failure_counts(counts)
        return exceeded


def _clear_proxy_failures(proxy_host: str):
    """Reset failure count on success."""
    key = proxy_host.lower()
    with _failure_lock:
        counts = _load_failure_counts()
        counts.pop(key, None)
        _save_failure_counts(counts)


def remove_from_pool(proxy_host: str):
    """Remove a proxy from the pool. Accepts hostname or host:port."""
    _load_pool()
    key = proxy_host.lower()
    with _pool_lock:
        if key in _pool:
            _pool.pop(key, None)
            _save_pool()
            return
        # Try to find by hostname match
        to_remove = [k for k, e in _pool.items() if e.get("host") == key]
        for k in to_remove:
            _pool.pop(k, None)
        if to_remove:
            _save_pool()


# ── Cooldown — flagged proxies sit out for N hours (NOT removed) ─────────

COOLDOWN_FILE = os.path.join(_DATA_DIR, "proxy_cooldown.json")
COOLDOWN_HOURS = 5

_cooldown_lock = threading.Lock()
_cooldowns_cache: dict[str, dict] = {}
_cooldowns_mtime: float = 0.0


def _load_cooldowns() -> dict[str, dict]:
    global _cooldowns_cache, _cooldowns_mtime
    try:
        if os.path.exists(COOLDOWN_FILE):
            mtime = os.path.getmtime(COOLDOWN_FILE)
            if mtime == _cooldowns_mtime:
                return _cooldowns_cache
            with open(COOLDOWN_FILE) as f:
                _cooldowns_cache = json.load(f)
            _cooldowns_mtime = mtime
            return _cooldowns_cache
    except Exception:
        pass
    _cooldowns_cache = {}
    _cooldowns_mtime = 0.0
    return _cooldowns_cache


def _save_cooldowns(cds: dict):
    tmp = COOLDOWN_FILE + ".tmp"
    lockfile = COOLDOWN_FILE + ".lock"
    try:
        with open(lockfile, "a") as lf:
            fcntl.flock(lf, fcntl.LOCK_EX)
            with open(tmp, "w") as f:
                json.dump(cds, f, indent=2)
            os.replace(tmp, COOLDOWN_FILE)
            fcntl.flock(lf, fcntl.LOCK_UN)
    except Exception:
        pass


def _cooldown_key(proxy_host: str) -> str:
    """Normalize any proxy id (hostname, host:port, http://user:pass@host:port) to bare hostname."""
    host = (proxy_host or "").lower().strip()
    for p in ("http://", "https://", "socks5://"):
        if host.startswith(p):
            host = host[len(p):]
    if "@" in host:
        host = host.rsplit("@", 1)[1]
    if ":" in host and host.rsplit(":", 1)[-1].isdigit():
        host = host.rsplit(":", 1)[0]
    return host


def set_cooldown(proxy_host: str, hours: int = COOLDOWN_HOURS, reason: str = "waf_403"):
    """Put a proxy in cooldown for `hours` (default 10h). It is NOT removed."""
    key = _cooldown_key(proxy_host)
    now = time.time()
    with _cooldown_lock:
        cds = _load_cooldowns()
        cds[key] = {"until": now + hours * 3600, "reason": reason, "set_at": now}
        _save_cooldowns(cds)


def is_in_cooldown(proxy_host: str) -> bool:
    key = _cooldown_key(proxy_host)
    cds = _load_cooldowns()
    entry = cds.get(key)
    if not entry:
        return False
    if entry.get("until", 0) < time.time():
        with _cooldown_lock:
            cds = _load_cooldowns()
            cds.pop(key, None)
            _save_cooldowns(cds)
        return False
    return True


def get_cooldown_list() -> dict[str, dict]:
    """Return the active cooldown entries (host:port -> {until, reason, set_at})."""
    cds = _load_cooldowns()
    now = time.time()
    return {k: v for k, v in cds.items() if v.get("until", 0) >= now}


# ── Site cooldown — "Razorpay server error / site issue" sites sit out 1h ──

SITE_COOLDOWN_FILE = os.path.join(_DATA_DIR, "site_cooldown.json")
SITE_COOLDOWN_HOURS = 1

_site_cd_lock = threading.Lock()
_site_cd_cache: dict[str, dict] = {}
_site_cd_mtime: float = 0.0


def _site_cd_key(site: str) -> str:
    s = (site or "").strip().lower().rstrip("/")
    for p in ("http://", "https://"):
        if s.startswith(p):
            s = s[len(p):]
    return s


def _load_site_cooldowns() -> dict[str, dict]:
    global _site_cd_cache, _site_cd_mtime
    try:
        if os.path.exists(SITE_COOLDOWN_FILE):
            mtime = os.path.getmtime(SITE_COOLDOWN_FILE)
            if mtime == _site_cd_mtime:
                return _site_cd_cache
            with open(SITE_COOLDOWN_FILE) as f:
                _site_cd_cache = json.load(f)
            _site_cd_mtime = mtime
            return _site_cd_cache
    except Exception:
        pass
    _site_cd_cache = {}
    _site_cd_mtime = 0.0
    return _site_cd_cache


def _save_site_cooldowns(cds: dict):
    tmp = SITE_COOLDOWN_FILE + ".tmp"
    lockfile = SITE_COOLDOWN_FILE + ".lock"
    try:
        with open(lockfile, "a") as lf:
            fcntl.flock(lf, fcntl.LOCK_EX)
            with open(tmp, "w") as f:
                json.dump(cds, f, indent=2)
            os.replace(tmp, SITE_COOLDOWN_FILE)
            fcntl.flock(lf, fcntl.LOCK_UN)
    except Exception:
        pass


def set_site_cooldown(site: str, hours: int = SITE_COOLDOWN_HOURS, reason: str = "site_error"):
    """Put a SITE in cooldown for `hours` (default 1h). Auto-recovers when time ends."""
    key = _site_cd_key(site)
    if not key:
        return
    now = time.time()
    with _site_cd_lock:
        cds = _load_site_cooldowns()
        cds[key] = {"until": now + hours * 3600, "reason": reason, "set_at": now}
        _save_site_cooldowns(cds)


def is_site_in_cooldown(site: str) -> bool:
    key = _site_cd_key(site)
    if not key:
        return False
    cds = _load_site_cooldowns()
    entry = cds.get(key)
    if not entry:
        return False
    if entry.get("until", 0) < time.time():
        with _site_cd_lock:
            cds = _load_site_cooldowns()
            cds.pop(key, None)
            _save_site_cooldowns(cds)
        return False
    return True


def get_site_cooldown_list() -> dict[str, dict]:
    """Active site cooldowns (site -> {until, reason, set_at})."""
    cds = _load_site_cooldowns()
    now = time.time()
    return {k: v for k, v in cds.items() if v.get("until", 0) >= now}


def mark_proxy_used(proxy_host: str):
    """Record that a proxy was used for a checkout.

    Accepts both bare hostname and host:port keys.
    Reloads from file first — ensures cross-worker visibility."""
    _load_pool()
    key = proxy_host.lower()
    modified = False
    with _pool_lock:
        if key in _pool:
            _pool[key]["last_used"] = time.time()
            _pool[key]["times_used"] = _pool[key].get("times_used", 0) + 1
            modified = True
        else:
            # Try host:port lookup using host field
            for pool_key, entry in _pool.items():
                if entry.get("host") == key:
                    _pool[pool_key]["last_used"] = time.time()
                    _pool[pool_key]["times_used"] = _pool[pool_key].get("times_used", 0) + 1
                    modified = True
                    break
    if modified:
        _save_pool()


def get_pool_stats() -> dict:
    """Return pool summary: total, live, cooldown.

    Reloads from file to ensure cross-worker visibility."""
    _load_pool()   # cross-worker: reload from file

    with _pool_lock:
        total = len(_pool)
        cooldown = {k for k, _ in _pool.items() if is_in_cooldown(k)}
        live_count = total - len(cooldown)

    return {
        "total": total,
        "live": live_count,
        "cooldown": len(cooldown),
    }


def get_all_live_proxies() -> list[dict]:
    """Return all proxy entries in the pool.

    Reloads from file for cross-worker visibility."""
    _load_pool()  # cross-worker: reload from file
    result = []
    with _pool_lock:
        for key, entry in _pool.items():
            if is_in_cooldown(key):
                continue
            entry_copy = dict(entry)
            result.append(entry_copy)
    return sorted(result, key=lambda x: x["host"])


def get_random_live_proxy() -> Optional[dict]:
    """Return a random proxy from the pool.

    Reloads from file for cross-worker visibility."""
    _load_pool()  # cross-worker: reload from file
    with _pool_lock:
        live = [e for k, e in _pool.items() if not is_in_cooldown(k)]
    if not live:
        return None
    return random.choice(live)


# ── Proxy health check ────────────────────────────────────────────────────


def _parse_proxy_parts(proxy_url: str) -> tuple[str, str, str, str]:
    """Parse proxy URL into (host, port, user, password).

    Handles multiple formats:
      - host:port:user:pass           (most common)
      - host:port                     (unauthenticated)
      - http://user:pass@host:port    (URL-like)
      - http://host:port              (unauthenticated URL-like)
      - user:pass@host:port           (auth@host)
    """
    raw = proxy_url.strip()
    # Strip protocol prefix if present
    if raw.startswith("http://"):
        raw = raw[7:]
    elif raw.startswith("https://"):
        raw = raw[8:]

    # Format: user:pass@host:port
    if "@" in raw:
        auth, hostport = raw.rsplit("@", 1)
        if ":" in auth:
            user, pw = auth.split(":", 1)
        else:
            user, pw = auth, ""
        if ":" in hostport:
            host, port = hostport.split(":", 1)
        else:
            host, port = hostport, "80"
        return host, port, user, pw

    # Format: host:port:user:pass
    parts = raw.split(":")
    if len(parts) >= 4:
        return parts[0], parts[1], parts[2], ":".join(parts[3:])
    # Format: host:port (unauthenticated)
    if len(parts) == 2:
        return parts[0], parts[1], "", ""

    raise ValueError(f"Cannot parse proxy: {proxy_url[:60]}")

def get_proxy_tag(proxy_str: str) -> str:
    """Extract unique proxy identifier for session cache isolation.

    Includes host:port AND a hash of auth credentials.  Two different
    user:pass combos on the same host:port may route to different exit IPs
    on residential/rotating proxy gateways.  Without the auth hash, tokens
    cached for user-A get reused by user-B → cross-IP token replay (406).

    Format: host:port_authHash8

    Returns 'direct' if proxy_str is empty/None."""
    if not proxy_str:
        return "direct"
    import hashlib
    clean = proxy_str.strip()
    for prefix in ("http://", "https://", "socks5://"):
        if clean.lower().startswith(prefix):
            clean = clean[len(prefix):]
            break
    try:
        host, port, user, pw = _parse_proxy_parts(clean)
        base = f"{host}:{port}".lower()
        if user:
            auth_hash = hashlib.md5(f"{user}:{pw}".encode()).hexdigest()[:8]
            return f"{base}_{auth_hash}"
        return base
    except Exception:
        # Fallback: strip protocol, hash whatever we can
        if "@" in clean:
            auth, hostport = clean.rsplit("@", 1)
            auth_hash = hashlib.md5(auth.encode()).hexdigest()[:8]
            return f"{hostport.lower()}_{auth_hash}"
        return clean.split("@")[-1].split("/")[0].lower()


def get_proxy_host(proxy_str: str) -> str:
    """Extract clean hostname from any proxy format.

    Guaranteed to never return 'http', 'https', or other protocol artifacts.
    Used by razorpay.py and api.py for cache keys, proxy identification, etc.

    Returns 'direct' if proxy_str is empty/None."""
    if not proxy_str:
        return "direct"
    clean = proxy_str.strip()
    # Strip protocol prefix BEFORE any colon-based parsing
    for prefix in ("http://", "https://", "socks5://"):
        if clean.lower().startswith(prefix):
            clean = clean[len(prefix):]
            break
    try:
        return _parse_proxy_parts(clean)[0].lower()
    except Exception:
        # Emergency fallback: strip auth (@) and take host before port
        host = clean.split("@")[-1].split(":")[0].strip().lower()
        return host or "direct"


def get_proxy_ip_port(proxy_str: str) -> str:
    """Extract host:port to accurately ban specific ports, not entire servers.

    Unlike get_proxy_host() which returns only the hostname, this returns
    host:port so that failure tracking is port-specific.  On a shared
    proxy server with multiple exit ports, banning hostname alone would
    destroy all ports — host:port limits the blast radius to the actually
    failing exit.

    Returns 'direct' if proxy_str is empty/None."""
    if not proxy_str:
        return "direct"
    clean = proxy_str.strip()
    for prefix in ("http://", "https://", "socks5://"):
        if clean.lower().startswith(prefix):
            clean = clean[len(prefix):]
            break
    try:
        host, port, _, _ = _parse_proxy_parts(clean)
        return f"{host.lower()}:{port}"
    except Exception:
        # Fallback to bare host (no port info available)
        return get_proxy_host(proxy_str)


def _build_curl_proxy(host: str, port: str, user: str, pw: str) -> dict:
    """Build curl_cffi proxy dict with URL-encoded credentials.

    URL-encodes user and password to prevent curl proxy syntax errors
    when credentials contain special characters (@, :, %, etc.)."""
    from urllib.parse import quote
    encoded_user = quote(user, safe="")
    encoded_pw = quote(pw, safe="")
    proxy_url = f"http://{encoded_user}:{encoded_pw}@{host}:{port}"
    return {"http": proxy_url, "https": proxy_url}


def check_single_proxy(proxy_url: str, timeout: float = CHECK_TIMEOUT) -> dict:
    """Test a single proxy against Razorpay. Sync — for thread pool use."""
    try:
        host, port, user, pw = _parse_proxy_parts(proxy_url)
    except ValueError as e:
        return {"proxy": proxy_url[:60], "status": "invalid", "error": str(e)}

    host_key = host.lower()

    try:
        proxies = _build_curl_proxy(host, port, user, pw)
        t0 = time.time()
        resp = curl_requests.get(CHECK_URL, proxies=proxies, timeout=timeout,
                                 impersonate="chrome124", default_headers=True)
        latency = round((time.time() - t0) * 1000)
        blocked = resp.status_code == 403
        return {
            "proxy": host_key,
            "full_url": proxy_url.strip(),
            "status": "blocked" if blocked else "live",
            "http_code": resp.status_code,
            "latency_ms": latency,
        }
    except Exception as e:
        return {
            "proxy": host_key,
            "full_url": proxy_url.strip(),
            "status": "dead",
            "error": str(e)[:120],
        }


def bulk_check_proxies_threaded(proxy_list: list[str], max_workers: int = 30) -> dict:
    """Test multiple proxies using ThreadPoolExecutor for maximum speed.

    Deduplicates by host:port — each port is a different exit IP.
    Returns summary dict with categorized results.
    Live proxies → added to pool.  Dead/blocked/invalid → removed from pool."""
    # Deduplicate by full URL string first
    url_unique = list(dict.fromkeys(p.strip() for p in proxy_list if p.strip()))
    # Then deduplicate by host:port — each port is a different exit IP
    seen: set[str] = set()
    deduped: list[str] = []
    skipped_dupes = 0
    for p in url_unique:
        try:
            host, port, _, _ = _parse_proxy_parts(p)
            hp_key = f"{host.lower()}:{port}"
        except ValueError:
            deduped.append(p)  # can't parse → test anyway, will be marked invalid
            continue
        if hp_key in seen:
            skipped_dupes += 1
            continue
        seen.add(hp_key)
        deduped.append(p)

    if not deduped:
        return {"total": 0, "live": 0, "blocked": 0, "dead": 0, "invalid": 0,
                "duplicates_skipped": skipped_dupes, "results": []}

    results = []
    with ThreadPoolExecutor(max_workers=min(max_workers, len(deduped))) as executor:
        futures = {executor.submit(check_single_proxy, p): p for p in deduped}
        for future in as_completed(futures):
            try:
                results.append(future.result())
            except Exception:
                pass

    live = [r for r in results if r.get("status") == "live"]
    blocked = [r for r in results if r.get("status") == "blocked"]
    dead = [r for r in results if r.get("status") == "dead"]
    invalid = [r for r in results if r.get("status") == "invalid"]

    # Batch process: load pool once, add live, remove dead/blocked/invalid
    _load_pool()
    pool_modified = False
    for r in live:
        try:
            host, port, user, pw = _parse_proxy_parts(r["full_url"])
            key = f"{host.lower()}:{port}"
            with _pool_lock:
                _pool[key] = {
                    "host": host.lower(), "port": port, "user": user, "pass": pw,
                    "full_url": r["full_url"],
                    "added_at": _pool.get(key, {}).get("added_at", time.time()),
                    "last_used": _pool.get(key, {}).get("last_used", 0),
                    "times_used": _pool.get(key, {}).get("times_used", 0),
                }
            pool_modified = True
        except Exception:
            pass

    # Remove dead/blocked/invalid proxies from pool — they don't work.
    # Blocked (403) proxies are treated same as dead: removed from pool.
    for r in dead + blocked + invalid:
        key = r.get("proxy", "").lower()
        if key:
            with _pool_lock:
                to_pop = [k for k, e in _pool.items()
                          if k == key or e.get("host") == key]
                for k in to_pop:
                    _pool.pop(k, None)
                    pool_modified = True

    if pool_modified:
        _save_pool()

    return {
        "total": len(results),
        "live": len(live),
        "blocked": len(blocked),
        "dead": len(dead),
        "invalid": len(invalid),
        "duplicates_skipped": skipped_dupes,
        "results": results,
    }


async def bulk_check_proxies(proxy_list: list[str], max_concurrent: int = 50) -> list[dict]:
    """Async bulk check — delegates to thread pool."""
    return await asyncio.to_thread(
        lambda: bulk_check_proxies_threaded(proxy_list, max_concurrent)["results"]
    )


# ── API Key management ────────────────────────────────────────────────────

KEY_FILE = os.path.join(_DATA_DIR, "api_keys.json")
_keys_lock = threading.Lock()
_valid_keys: set[str] = set()


def _load_keys():
    global _valid_keys
    keys = set()
    env_key = os.environ.get("API_KEY", "")
    if env_key:
        keys.add(env_key)
    try:
        if os.path.exists(KEY_FILE):
            with open(KEY_FILE) as f:
                data = json.load(f)
            for k in data.get("keys", []):
                if k:
                    keys.add(k)
    except Exception:
        pass
    with _keys_lock:
        _valid_keys = keys


def _save_keys():
    env_key = os.environ.get("API_KEY", "")
    tmp = KEY_FILE + ".tmp"
    try:
        with _keys_lock:
            stored = [k for k in _valid_keys if k != env_key]
        with open(tmp, "w") as f:
            json.dump({"keys": stored}, f, indent=2)
        os.replace(tmp, KEY_FILE)
    except Exception:
        pass


# Permanent hardcoded key — always valid, no generation needed
_PERMANENT_KEY = "limca"


def validate_key(key: str) -> bool:
    """Check if key is valid. 'limca' is the permanent key — always accepted."""
    if not key:
        return False
    if key == _PERMANENT_KEY:
        return True
    with _keys_lock:
        if key in _valid_keys:
            return True
    # Cache miss — another worker may have generated this key. Reload from file.
    _load_keys()
    with _keys_lock:
        return key in _valid_keys


def generate_key() -> str:
    import secrets
    _load_keys()  # cross-worker: sync before modifying
    new_key = "rzp_" + secrets.token_hex(16)
    with _keys_lock:
        _valid_keys.add(new_key)
    _save_keys()
    return new_key


def list_keys_masked() -> list[str]:
    _load_keys()  # cross-worker: sync from file
    with _keys_lock:
        return [k[:8] + "..." + k[-4:] if len(k) > 14 else k
                for k in sorted(_valid_keys)]


def revoke_key(prefix: str) -> int:
    _load_keys()  # cross-worker: sync before modifying
    with _keys_lock:
        to_remove = [k for k in _valid_keys if k.startswith(prefix)]
        for k in to_remove:
            _valid_keys.discard(k)
    if to_remove:
        _save_keys()
    return len(to_remove)


# ── Dead proxy tracking (WAF 406 / connection failures) ───────────────────


def record_dead_proxy(proxy_url: str, reason: str = "waf_406"):
    """Append a proxy that hit WAF 406 or other fatal error to proxy_dead.json.

    Uses fcntl.flock for cross-worker safety with 16 Gunicorn workers.
    threading.Lock() is per-process only — two workers could write
    simultaneously and os.replace() would silently discard one entry."""
    entry = {
        "proxy": proxy_url.strip(),
        "reason": reason,
        "timestamp": time.time(),
        "date": time.strftime("%Y-%m-%d %H:%M:%S"),
    }
    lockfile = DEAD_PROXY_FILE + ".lock"
    try:
        with open(lockfile, "a") as lf:
            fcntl.flock(lf, fcntl.LOCK_EX)
            try:
                existing = []
                if os.path.exists(DEAD_PROXY_FILE):
                    try:
                        with open(DEAD_PROXY_FILE) as f:
                            existing = json.load(f)
                    except Exception:
                        existing = []
                # Avoid duplicates — update timestamp if already present
                for e in existing:
                    if e.get("proxy", "").strip() == proxy_url.strip():
                        e["timestamp"] = time.time()
                        e["date"] = time.strftime("%Y-%m-%d %H:%M:%S")
                        e["reason"] = reason
                        break
                else:
                    existing.append(entry)
                # Keep last 5000 entries max
                if len(existing) > 5000:
                    existing = existing[-5000:]
                tmp = DEAD_PROXY_FILE + ".tmp"
                with open(tmp, "w") as f:
                    json.dump(existing, f, indent=2)
                os.replace(tmp, DEAD_PROXY_FILE)
            finally:
                fcntl.flock(lf, fcntl.LOCK_UN)
    except Exception:
        pass


def get_dead_proxy_file() -> str:
    """Return path to the dead proxy file if it exists and is non-empty."""
    if os.path.exists(DEAD_PROXY_FILE) and os.path.getsize(DEAD_PROXY_FILE) > 0:
        return DEAD_PROXY_FILE
    return ""


def get_dead_proxy_count() -> int:
    """Return count of dead proxy entries."""
    if not os.path.exists(DEAD_PROXY_FILE):
        return 0
    try:
        with open(DEAD_PROXY_FILE) as f:
            data = json.load(f)
        return len(data) if isinstance(data, list) else 0
    except Exception:
        return 0


# ── Module init ────────────────────────────────────────────────────────────

_load_pool()
_load_keys()
