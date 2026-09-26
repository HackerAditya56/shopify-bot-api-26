#!/usr/bin/env python3
"""
proxy_checker.py — Shopify checker proxy liveness test.

Reads proxy.txt (user:pass@host:port), checks every proxy concurrently,
rewrites proxy.txt with ONLY live proxies, and writes proxy_dead.txt with
dead proxies annotated by failure reason (e.g. "402 (payment required)").

Usage:
    python3 proxy_checker.py [--workers 150] [--timeout 30] [--retries 3] [--url https://api.ipify.org]
"""

import os
import re
import sys
import time
import argparse
import threading
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed

try:
    from curl_cffi import requests as curl_requests
except ImportError:
    print("[!] curl_cffi not installed. Install with: pip install curl_cffi")
    sys.exit(1)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PROXY_FILE = os.path.join(BASE_DIR, "proxy.txt")
DEAD_FILE = os.path.join(BASE_DIR, "proxy_dead.txt")

WORKERS = 150        # concurrent checks
TIMEOUT = 30         # seconds per attempt
MAX_ATTEMPTS = 3     # total attempts per proxy (1 initial + 2 retries)
TEST_URL = "https://api.ipify.org?format=json"

HTTP_REASONS = {
    400: "bad request",
    401: "unauthorized",
    402: "payment required",
    403: "forbidden",
    407: "proxy auth required",
    408: "request timeout",
    429: "too many requests",
    500: "internal server error",
    502: "bad gateway",
    503: "service unavailable",
    504: "gateway timeout",
}


def normalize_proxy(proxy: str) -> str:
    """user:pass@host:port -> http://user:pass@host:port (idempotent)."""
    proxy = proxy.strip()
    if proxy.startswith(("http://", "https://", "socks4://", "socks5://")):
        return proxy
    return "http://" + proxy


def classify_reason(exc_type: str, err_text: str, status_code=None) -> str:
    """Map a failure to a short human-readable reason."""
    if status_code:
        name = HTTP_REASONS.get(status_code)
        return f"{status_code} ({name})" if name else f"HTTP {status_code}"

    t = (err_text or "").lower()

    # CONNECT tunnel rejected with an HTTP code (proxy-side): "response 402"
    m = re.search(r"response\s+(\d{3})", t)
    if m:
        code = int(m.group(1))
        name = HTTP_REASONS.get(code)
        return f"{code} ({name})" if name else f"tunnel rejected {code}"

    if any(x in t for x in ("resolving timed out", "could not resolve",
                            "couldn't resolve", "name resolution")) or exc_type == "DNSError":
        return "dns (resolution failed)"
    if "connection refused" in t or "econnrefused" in t:
        return "connection refused"
    if "connection reset" in t or "econnreset" in t:
        return "connection reset"
    if "could not connect" in t:
        return "connection failed"
    if any(x in t for x in ("connection timed out", "operation timed out",
                            "timed out", "timeout", "etimedout")):
        return "timeout"
    if "authentication" in t or "auth" in t or "407" in t:
        return "407 (proxy auth required)"
    if "tunnel failed" in t or "connect aborted" in t or "proxy connect" in t:
        return "tunnel failed"
    if "ssl" in t or "certificate" in t or exc_type == "SSLError":
        return "ssl error"
    if "unreachable" in t:
        return "unreachable"
    if "bad gateway" in t or "502" in t:
        return "502 (bad gateway)"

    mc = re.search(r"curl: \((\d+)\)", t)
    if mc:
        return f"curl error {mc.group(1)}"
    return (err_text or exc_type or "unknown")[:80]


def _is_hard_fail(reason: str) -> bool:
    """Auth/forbidden/payment failures won't change on retry — stop early."""
    return bool(reason) and reason[:3] in ("401", "402", "403", "407")


def check_proxy(proxy):
    """Check one proxy. Returns (original, is_live, reason)."""
    original, proxy_url = proxy
    last_reason = None

    for _ in range(MAX_ATTEMPTS):
        try:
            r = curl_requests.get(
                TEST_URL,
                proxies={"http": proxy_url, "https": proxy_url},
                timeout=TIMEOUT,
            )
            if r.status_code == 200:
                return original, True, None
            last_reason = classify_reason("", "", status_code=r.status_code)
            if _is_hard_fail(last_reason):
                break
        except Exception as e:  # noqa: BLE001 — curl_cffi raises several types
            last_reason = classify_reason(type(e).__name__, str(e))
            if _is_hard_fail(last_reason):
                break

    return original, False, last_reason or "unknown"


def load_proxies():
    """Read proxy.txt, normalize, dedupe (preserving order)."""
    if not os.path.isfile(PROXY_FILE):
        print(f"[!] {PROXY_FILE} not found.")
        sys.exit(1)
    proxies, seen = [], set()
    with open(PROXY_FILE, encoding="utf-8", errors="replace") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            norm = normalize_proxy(line)
            if norm in seen:
                continue
            seen.add(norm)
            proxies.append((line, norm))
    return proxies


def main():
    global TIMEOUT, MAX_ATTEMPTS, TEST_URL

    ap = argparse.ArgumentParser(description="Check proxy.txt liveness.")
    ap.add_argument("--workers", type=int, default=WORKERS)
    ap.add_argument("--timeout", type=int, default=TIMEOUT)
    ap.add_argument("--retries", type=int, default=MAX_ATTEMPTS)
    ap.add_argument("--url", default=TEST_URL)
    args = ap.parse_args()

    TIMEOUT = args.timeout
    MAX_ATTEMPTS = args.retries
    TEST_URL = args.url

    proxies = load_proxies()
    total = len(proxies)
    print(f"[*] Checking {total} proxies | {args.workers} workers | "
          f"{TIMEOUT}s timeout | {MAX_ATTEMPTS} attempts")
    print(f"[*] Target: {TEST_URL}\n")

    live, dead = [], []
    reason_counts = Counter()
    t0 = time.monotonic()
    done = 0
    lock = threading.Lock()

    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        futures = [pool.submit(check_proxy, p) for p in proxies]
        for fut in as_completed(futures):
            original, is_live, reason = fut.result()
            with lock:
                done += 1
                if is_live:
                    live.append(original)
                else:
                    dead.append((original, reason))
                    reason_counts[reason] += 1
                if done % 100 == 0 or done == total:
                    el = time.monotonic() - t0
                    print(f"  [{done}/{total}] live={len(live)} dead={len(dead)} ({el:.0f}s)")

    # live -> proxy.txt (preserve original format/order)
    with open(PROXY_FILE, "w", encoding="utf-8") as f:
        if live:
            f.write("\n".join(live) + "\n")

    # dead -> proxy_dead.txt (with reason)
    with open(DEAD_FILE, "w", encoding="utf-8") as f:
        for original, reason in dead:
            f.write(f"{original} | {reason}\n")

    print(f"\n[✓] Done in {time.monotonic() - t0:.0f}s")
    print(f"[✓] LIVE : {len(live)}  -> {PROXY_FILE}")
    print(f"[✓] DEAD : {len(dead)}  -> {DEAD_FILE}")
    if reason_counts:
        print("\n[Dead reason breakdown]")
        for reason, count in reason_counts.most_common():
            print(f"  {count:6d}  {reason}")


if __name__ == "__main__":
    main()
