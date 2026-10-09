"""
session_cache.py — Session token cache for Razorpay checkouts.

When we obtain a valid session_token from checkout/public (step 3), we cache it
along with the associated cookies.  Subsequent checkouts to the same payment page
can reuse the token, saving one HTTP round-trip AND reducing the number of times
we hit the WAF's most heavily-inspected endpoint.

FILE-BACKED for Gunicorn cross-worker visibility.  Without this, each of 16
workers has its own in-memory cache → 16x the checkout/public calls → Razorpay
rate-limits with 406.  Now all workers share one cache file.

Cache entries expire after TTL seconds (default 5 min).  Razorpay session tokens
typically live 5-15 minutes before the server rotates them.
"""

from __future__ import annotations

import asyncio
import fcntl
import json
import os
import time
import threading
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class CachedSession:
    """A cached session token + cookies for a specific payment page."""
    session_token: str
    cookies: dict[str, str]         # cookie name → value
    payment_page_url: str
    created_at: float = field(default_factory=time.time)
    expires_at: float = 300.0       # overridden by SessionCache._ttl on put()
    hit_count: int = 0

    @property
    def is_expired(self) -> bool:
        return time.time() > (self.created_at + self.expires_at)

    @property
    def age_seconds(self) -> float:
        return time.time() - self.created_at

    @property
    def ttl_seconds(self) -> float:
        return max(0.0, self.created_at + self.expires_at - time.time())

    def to_dict(self) -> dict:
        return {
            "session_token": self.session_token,
            "cookies": self.cookies,
            "payment_page_url": self.payment_page_url,
            "created_at": self.created_at,
            "expires_at": self.expires_at,
            "hit_count": self.hit_count,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "CachedSession":
        return cls(
            session_token=d["session_token"],
            cookies=d.get("cookies", {}),
            payment_page_url=d.get("payment_page_url", ""),
            created_at=d.get("created_at", time.time()),
            expires_at=d.get("expires_at", 300.0),
            hit_count=d.get("hit_count", 0),
        )


class SessionCache:
    """File-backed cache for Razorpay session tokens — shared across workers.

    Usage:
        cache = SessionCache(ttl=60, max_size=200, max_hits=1)  # 1 card = 1 session

        # Store after successful checkout/public:
        cache.put(payment_page_url, session_token, cookies_dict)

        # Retrieve before checkout/public:
        entry = cache.get(payment_page_url)
        if entry:
            session_token = entry.session_token
            cookies = entry.cookies
    """

    def __init__(self, ttl: float = 300.0, max_size: int = 200, max_hits: int = 1):
        """
        Args:
            ttl: Cache entry lifetime in seconds (default 5 min).
            max_size: Maximum cache entries across all workers.
            max_hits: Max times a cached token can be used (default 1 — use once).
        """
        self._ttl = ttl
        self._max_size = max_size
        self._max_hits = max_hits
        self._lock = threading.Lock()
        # Use same data dir as proxy_manager for persistence
        _data_dir = os.environ.get("PROXY_DATA_DIR",
                                   os.path.dirname(os.path.abspath(__file__)))
        os.makedirs(_data_dir, exist_ok=True)
        self._file = os.path.join(_data_dir, "session_cache.json")
        # Cache stampede prevention: keys currently being fetched by another
        # coroutine.  Waiting coroutines poll until the token is cached.
        self._in_flight: dict[str, float] = {}  # key → started_at timestamp
        self._in_flight_lock = threading.Lock()
        # In-memory entries cache — avoids file I/O on every hit count bump.
        # Writes to file only on structural changes (new entry, eviction, removal).
        self._entries: dict[str, dict] = {}
        self._entries_loaded = False
        # In-memory hit counters survive _load() overwrites.  _load() reads
        # the on-disk state (which lacks hit counts since we don't persist
        # them to avoid disk thrash), but hit counts must persist across
        # reads for accurate stats reporting.
        self._hit_counts: dict[str, int] = {}
        self._last_mtime: float = 0.0  # fast-path: skip JSON parse if file unchanged

    def _key(self, payment_page_url: str) -> str:
        """Normalize URL to a cache key."""
        return payment_page_url.strip().rstrip('/').lower()

    def _load(self) -> dict[str, dict]:
        """Process-safe read from disk with shared lock (fcntl LOCK_SH).

        Locks the shared lock file, not the data file — the data file may
        be replaced by os.replace() during read, which changes the inode
        and invalidates the lock.  The persistent lock file has a stable
        inode across os.replace() calls on the data file.

        Uses mtime fast-path: skips JSON parse if file hasn't been modified
        since last read.  At 500+ concurrent checkouts, this eliminates
        tens of thousands of unnecessary disk reads + JSON parses per second."""
        if not os.path.exists(self._file):
            return {}

        # FAST PATH: skip file read + JSON parse if file hasn't changed.
        # mtime check is ~0.001ms vs ~5-50ms for full parse + flock.
        try:
            current_mtime = os.path.getmtime(self._file)
            if current_mtime <= self._last_mtime and self._entries_loaded:
                return self._entries
        except Exception:
            pass

        lockfile = self._file + ".lock"
        try:
            # Acquire shared lock — multiple readers can hold LOCK_SH simultaneously
            with open(lockfile, "a") as lf:
                fcntl.flock(lf, fcntl.LOCK_SH)
                try:
                    if os.path.exists(self._file):
                        current_mtime = os.path.getmtime(self._file)
                        with open(self._file, "r") as f:
                            raw = json.load(f)
                        self._last_mtime = current_mtime
                        return raw.get("entries", {})
                finally:
                    fcntl.flock(lf, fcntl.LOCK_UN)
        except Exception:
            pass
        return {}

    def _save(self, entries: dict[str, dict]):
        """Process-safe atomic write with exclusive lock on a shared lock file.

        CRITICAL: locks the persistent lock file (session_cache.json.lock),
        NOT the per-process .tmp file.  Locking a unique tmp file provides
        zero cross-process synchronization.  The lock file is shared across
        all Gunicorn workers so LOCK_EX serializes writes correctly."""
        tmp = self._file + ".tmp"
        lockfile = self._file + ".lock"
        try:
            # Acquire exclusive lock on the SHARED lock file before writing
            with open(lockfile, "a") as lf:
                fcntl.flock(lf, fcntl.LOCK_EX)
                try:
                    with open(tmp, "w") as f:
                        json.dump({"entries": entries, "updated": time.time()}, f)
                    os.replace(tmp, self._file)
                finally:
                    fcntl.flock(lf, fcntl.LOCK_UN)
        except Exception:
            pass

    def get(self, payment_page_url: str) -> Optional[CachedSession]:
        """Get a cached session if one exists and hasn't expired.

        ALWAYS reloads from disk for cross-worker visibility.  In Gunicorn
        multi-worker mode, Worker A may have cached a token to disk while
        Worker B's in-memory _entries is stale.  Without re-reading from
        disk, get_or_wait() polls stale memory for 1.5s and times out,
        firing a duplicate checkout/public → WAF 406/403."""
        key = self._key(payment_page_url)
        with self._lock:
            self._entries = self._load()
            self._entries_loaded = True
            raw = self._entries.get(key)
            if raw is None:
                return None
            entry = CachedSession.from_dict(raw)
            if entry.is_expired:
                del self._entries[key]
                self._save(self._entries)
                return None
            # Update hit count in-memory only — skip file write on every hit.
            # Uses _hit_counts dict that survives _load() overwrites.
            self._hit_counts[key] = self._hit_counts.get(key, 0) + 1
            # Evict after max_hits uses — 1 card = 1 session (never reuse)
            if self._hit_counts[key] > self._max_hits:
                del self._entries[key]
                self._save(self._entries)
                return None
            return entry

    async def get_or_wait(self, payment_page_url: str,
                    timeout: float = 3.0) -> tuple[Optional[CachedSession], bool]:
        """Get cached session, waiting if another coroutine is fetching.

        Cache stampede prevention: when N concurrent checkouts hit the same
        proxy+page, the first one gets a cache miss and fetches a fresh token.
        The other N-1 see an in-flight marker and poll until the token arrives,
        avoiding N redundant checkout/public calls (each of which is a WAF
        signal and wastes proxy bandwidth).

        Returns (entry, was_waiting) — was_waiting=True means the caller
        waited for another coroutine and should add jitter before proceeding
        to avoid herd synchronization on the remaining steps.

        Args:
            payment_page_url: Cache key (page URL + proxy tag)
            timeout: Max seconds to wait for in-flight fetch (default 3s)
        Returns:
            (CachedSession, was_waiting) tuple.  (None, False) if cache miss
            and this caller should fetch.  (entry, True) if waited.
        """
        key = self._key(payment_page_url)

        # Fast path: already cached
        entry = self.get(key)
        if entry is not None:
            return entry, False

        # Slow path: check if another coroutine is fetching
        with self._in_flight_lock:
            inflight_start = self._in_flight.get(key)
            # Treat markers older than 10s as abandoned (crash during step 3
            # before put() or put_done() was called).  Otherwise the marker
            # lingers forever and all subsequent requests poll for the full
            # timeout before falling back to fetching a fresh token.
            if inflight_start is None or (time.time() - inflight_start > 10.0):
                # No active fetch — mark in-flight and return None
                # (caller will fetch and put)
                self._in_flight[key] = time.time()
                return None, False

        # Someone is fetching — wait for them to finish
        deadline = time.time() + timeout
        while time.time() < deadline:
            await asyncio.sleep(0.05)  # 50ms poll interval — NON-BLOCKING async
            entry = self.get(key)
            if entry is not None:
                return entry, True  # was_waiting=True → caller should add jitter
            # Check if in-flight marker was cleared (fetch failed)
            with self._in_flight_lock:
                if key not in self._in_flight:
                    # Fetch completed but no cache entry → fetch failed.
                    # Mark ourselves as in-flight and go fetch.
                    self._in_flight[key] = time.time()
                    return None, False

        # Timeout — fetch ourselves
        with self._in_flight_lock:
            self._in_flight[key] = time.time()
        return None, False

    def put_done(self, payment_page_url: str):
        """Clear the in-flight marker after a fetch completes (success or fail).

        Call this after put() or after a failed fetch to unblock waiters."""
        key = self._key(payment_page_url)
        with self._in_flight_lock:
            self._in_flight.pop(key, None)

    def put(self, payment_page_url: str, session_token: str,
            cookies: dict[str, str]) -> CachedSession:
        """Store a session token in the cache.

        Writes to file (structural change) and clears in-flight marker.
        ALWAYS reloads from disk before modifying — in Gunicorn multi-worker
        mode, another worker may have written tokens since our last _load()."""
        key = self._key(payment_page_url)
        with self._lock:
            self._entries = self._load()   # ALWAYS sync from disk before modifying
            self._entries_loaded = True
            # Preserve hit count from persistent counter if updating existing entry
            old_hits = self._hit_counts.get(key, 0)
            entry = CachedSession(
                session_token=session_token,
                cookies=dict(cookies),
                payment_page_url=key,
                expires_at=self._ttl,
                hit_count=old_hits,
            )
            self._entries[key] = entry.to_dict()
            self._evict_if_needed(self._entries)
            self._save(self._entries)
            # Clear in-flight marker — unblocks any waiting coroutines
            with self._in_flight_lock:
                self._in_flight.pop(key, None)
            return entry

    def remove(self, payment_page_url: str):
        """Explicitly remove a cached session (e.g., on 403/406).

        Writes to file (structural change).
        ALWAYS reloads from disk before modifying — in Gunicorn multi-worker
        mode, another worker may have written tokens since our last _load()."""
        key = self._key(payment_page_url)
        with self._lock:
            self._entries = self._load()   # ALWAYS sync from disk before modifying
            self._entries_loaded = True
            if key in self._entries:
                del self._entries[key]
                self._save(self._entries)

    def _evict_if_needed(self, entries: dict[str, dict]):
        """Evict expired entries, then oldest if still over max_size."""
        now = time.time()
        # First pass: remove expired
        expired = [k for k, v in entries.items()
                   if now > (v.get("created_at", 0) + v.get("expires_at", self._ttl))]
        for k in expired:
            del entries[k]

        # Second pass: remove oldest if still too many
        if len(entries) > self._max_size:
            sorted_entries = sorted(
                entries.items(), key=lambda x: x[1].get("created_at", 0)
            )
            to_remove = len(entries) - self._max_size
            for k, _ in sorted_entries[:to_remove]:
                del entries[k]

    def refresh_from_file(self):
        """Re-read cache from file — call periodically for cross-worker sync.

        In Gunicorn multi-worker mode, each process has its own in-memory
        cache.  This method syncs from the shared file so workers see tokens
        cached by other workers.  Call before get() in multi-worker setups."""
        with self._lock:
            self._entries = self._load()
            self._entries_loaded = True

    @property
    def size(self) -> int:
        with self._lock:
            if not self._entries_loaded:
                self._entries = self._load()
                self._entries_loaded = True
            return len(self._entries)

    @property
    def stats(self) -> dict:
        with self._lock:
            if not self._entries_loaded:
                self._entries = self._load()
                self._entries_loaded = True
            now = time.time()
            entry_list = list(self._entries.values())
            active = sum(1 for e in entry_list
                        if now <= (e.get("created_at", 0) + e.get("expires_at", self._ttl)))
            return {
                "total_entries": len(entry_list),
                "active": active,
                "expired": len(entry_list) - active,
                "total_hits": sum(self._hit_counts.values()),
                "oldest_age_s": min((now - e.get("created_at", now) for e in entry_list), default=0),
                "newest_age_s": max((now - e.get("created_at", 0) for e in entry_list), default=0),
            }


# Module-level singleton
_cache: Optional[SessionCache] = None


def get_session_cache() -> SessionCache:
    global _cache
    if _cache is None:
        # TTL 120s — Razorpay rotates tokens every 1-2 min.  300s (5 min)
        # was causing cross-worker token replay when the per-proxy cache
        # isolation fixed in razorpay.py wasn't enough (same proxy re-used
        # within TTL window with a stale token).
        _cache = SessionCache(ttl=120.0, max_size=200)
    return _cache
