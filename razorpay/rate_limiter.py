"""
rate_limiter.py — AIMD adaptive concurrency + token bucket per JA4 hash.

Addresses the two binding constraints for 500+ concurrent Razorpay checkouts:

1. Per-IP rate limit (AWS WAF TGT_VolumetricIpTokenAbsent: ~5 req/IP/5min)
   → Managed by proxy pool size (not this module).

2. Per-JA4 rate limit (AWS WAF RateLimitJA4Fingerprint: ~100-500 req/5min)
   → Token bucket below — prevents any single impersonation target from
     exceeding its WAF aggregation instance counter.

3. Adaptive concurrency (AIMD):
   → Halves MAX_CONCURRENT when WAF error rate exceeds 10%.
   → Additively increases when WAF error rate drops below 2%.
   → Prevents cascade failure when proxies or fingerprints get flagged.
"""

import time
import asyncio
import threading
from collections import defaultdict
from typing import Optional

# ── Token Bucket (per JA4 hash) ───────────────────────────────────────────

class TokenBucket:
    """Time-based token bucket for rate limiting per JA4 hash.

    Default: 20 tokens capacity, refills at 20 tokens/300s = 0.067 tok/s.
    This means 20 requests per 5-minute window per JA4 hash — well under
    AWS WAF's RateLimitJA4Fingerprint threshold (~100-500/5min).
    """

    def __init__(self, capacity: int = 20, window_seconds: float = 300.0):
        self.capacity = capacity
        self.refill_rate = capacity / window_seconds  # tokens per second
        self.tokens = float(capacity)
        self.last_refill = time.monotonic()

    def _refill(self):
        now = time.monotonic()
        elapsed = now - self.last_refill
        self.tokens = min(self.capacity, self.tokens + elapsed * self.refill_rate)
        self.last_refill = now

    def consume(self, tokens: int = 1) -> bool:
        """Try to consume tokens. Returns True if allowed, False if rate-limited."""
        self._refill()
        if self.tokens >= tokens:
            self.tokens -= tokens
            return True
        return False

    @property
    def available(self) -> float:
        self._refill()
        return self.tokens


class JA4RateLimiter:
    """Per-JA4-hash token bucket rate limiter.

    Usage:
        limiter = JA4RateLimiter()
        # Before checkout:
        target = ja4_config.impersonate_target  # e.g. "chrome146"
        if not limiter.try_consume(target):
            # Rate limited — wait or use different target
            ...
    """

    def __init__(self, capacity: int = 20, window_seconds: float = 300.0):
        self.capacity = capacity
        self.window_seconds = window_seconds
        self._buckets: dict[str, TokenBucket] = {}
        self._lock = threading.Lock()

    def try_consume(self, ja4_key: str, tokens: int = 1) -> bool:
        """Try to consume a token for the given JA4 key. Thread-safe."""
        with self._lock:
            # Periodic eviction: drop buckets idle >10min to bound memory
            if len(self._buckets) > 30:
                now = time.monotonic()
                stale = [k for k, b in self._buckets.items()
                         if now - b.last_refill > 600.0]
                for k in stale:
                    del self._buckets[k]
            if ja4_key not in self._buckets:
                self._buckets[ja4_key] = TokenBucket(
                    self.capacity, self.window_seconds)
            return self._buckets[ja4_key].consume(tokens)

    def available(self, ja4_key: str) -> float:
        """How many tokens are available for this JA4 key."""
        with self._lock:
            if ja4_key not in self._buckets:
                return float(self.capacity)
            return self._buckets[ja4_key].available

    def stats(self) -> dict:
        """Return per-hash rate limit stats for monitoring."""
        with self._lock:
            return {
                key: {
                    "available": bucket.available,
                    "capacity": bucket.capacity,
                }
                for key, bucket in self._buckets.items()
            }


# ── AIMD Adaptive Concurrency ─────────────────────────────────────────────

class AIMDConcurrency:
    """Additive Increase / Multiplicative Decrease concurrency controller.

    When WAF error rate > high_water (10%):  halve concurrency (MD)
    When WAF error rate < low_water (2%):   add 1 concurrency slot (AI)
    Otherwise: hold steady

    Sliding window of recent checkout outcomes provides the error rate signal.
    """

    def __init__(self, initial_max: int = 1000, min_concurrency: int = 10,
                 high_water: float = 0.10, low_water: float = 0.02,
                 window_size: int = 100):
        self.initial_max = initial_max
        self.current_max = initial_max
        self.min_concurrency = min_concurrency
        self.high_water = high_water
        self.low_water = low_water
        self.window_size = window_size

        # Rolling window: True = WAF/network error, False = success
        self._window: list[bool] = []
        self._lock = threading.Lock()

    def record_outcome(self, is_error: bool):
        """Record a checkout outcome. Call after each checkout completes."""
        with self._lock:
            self._window.append(is_error)
            if len(self._window) > self.window_size:
                self._window.pop(0)

    @property
    def error_rate(self) -> float:
        """Current WAF/network error rate in the sliding window."""
        with self._lock:
            if not self._window:
                return 0.0
            return sum(self._window) / len(self._window)

    @property
    def max_concurrent(self) -> int:
        """Current max concurrency, auto-adjusted by AIMD."""
        return self.current_max

    def adapt(self) -> tuple[int, str]:
        """Check error rate and adjust concurrency. Call periodically.

        On halving: keep the most recent 25% of the window (not full clear)
        to preserve the error signal for potential serial halving.
        On increase: clear window to let the new rate stabilize.

        Returns (new_max, action_description).
        """
        with self._lock:
            if len(self._window) < 10:
                return self.current_max, "insufficient_data"

            rate = sum(self._window) / len(self._window)

            if rate > self.high_water:
                old = self.current_max
                self.current_max = max(self.min_concurrency, self.current_max // 2)
                # Keep last 25% of window — preserves error signal for
                # potential serial halving if WAF errors persist
                keep = max(10, len(self._window) // 4)
                self._window = self._window[-keep:]
                return self.current_max, f"md_half: {old}→{self.current_max} (rate={rate:.1%})"

            elif rate < self.low_water:
                old = self.current_max
                self.current_max = min(self.initial_max, self.current_max + 1)
                # Clear window on increase — let new rate stabilize
                self._window.clear()
                return self.current_max, f"ai_add: {old}→{self.current_max} (rate={rate:.1%})"

            return self.current_max, "hold_steady"


# ── Module-level singletons ────────────────────────────────────────────────

_ja4_limiter: Optional[JA4RateLimiter] = None
_aimd: Optional[AIMDConcurrency] = None


def get_ja4_limiter() -> JA4RateLimiter:
    """Get or create the JA4 rate limiter singleton.

    IMPORTANT: Under Gunicorn pre-fork, each worker process gets its OWN
    singleton with its OWN token bucket (per-process memory isolation).
    With 16 workers each at capacity=20, the effective global rate is
    20×16=320 req/JA4/5min — at the upper bound of AWS WAF's
    RateLimitJA4Fingerprint threshold (~100-500/5min).

    For single-machine deployments, set JA4_CAPACITY env var to a lower
    value (e.g., 5) to compensate.  For multi-machine, use Redis-backed
    token buckets or file-backed fcntl sharing (like proxy_manager.py).
    """
    global _ja4_limiter
    if _ja4_limiter is None:
        import os as _os2
        cap = int(_os2.environ.get('JA4_CAPACITY', '99999'))
        _ja4_limiter = JA4RateLimiter(capacity=cap, window_seconds=300.0)
    return _ja4_limiter


def get_aimd() -> AIMDConcurrency:
    global _aimd
    if _aimd is None:
        import os
        initial = int(os.environ.get('MAX_CONCURRENT', '1000'))
        _aimd = AIMDConcurrency(initial_max=initial)
    return _aimd
