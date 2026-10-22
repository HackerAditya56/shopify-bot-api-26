"""
Filter sites.txt to keep ONLY sites whose cheapest product is under $1.

Uses shopify_scraper.fetch_site_price_local() to verify each site's actual
price (not whatever price was logged at /addsite time — some merchants
change prices and old logs become stale).

Usage:
  python filter_low_price_sites.py [--max-price 1.00] [--out sites_low.txt]

Default behaviour: writes sites whose scraped cheapest is strictly < $1
to mass_gates/sites_low.txt and prints stats. Original sites.txt is
NOT modified.
"""
import argparse
import asyncio
import os
import random
import sys

ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, ROOT)

from shopify_scraper import fetch_site_price_local

SITES_FILE = os.path.join(ROOT, "mass_gates", "sites.txt")
PROXIES_FILE = os.path.join(ROOT, "proxies.txt")


def _load_proxies(path):
    out = []
    if not os.path.exists(path):
        return out
    for line in open(path, "r", encoding="utf-8", errors="ignore"):
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        parts = line.split(":")
        if len(parts) == 4:
            host, port, user, pw = parts
            out.append(f"http://{user}:{pw}@{host}:{port}")
    return out


def _read_sites(path):
    out = []
    for line in open(path, "r", encoding="utf-8", errors="ignore"):
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if "|" in line:
            line = line.split("|")[0].strip()
        if line:
            out.append(line)
    return out


async def _scrape(site, proxy, sem):
    async with sem:
        try:
            return await fetch_site_price_local(site, proxy)
        except Exception:
            return None


async def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--max-price", type=float, default=1.00,
                    help="Keep sites whose cheapest is strictly < this (default 1.00)")
    ap.add_argument("--out", default=None,
                    help="Output path (default: mass_gates/sites_low.txt)")
    args = ap.parse_args()

    out_path = args.out or os.path.join(ROOT, "mass_gates", "sites_low.txt")

    sites = _read_sites(SITES_FILE)
    print(f"[+] Read {len(sites)} sites from {SITES_FILE}")

    proxies = _load_proxies(PROXIES_FILE)
    proxy_cycle = [random.choice(proxies) if proxies else "" for _ in range(len(sites))]
    sem = asyncio.Semaphore(8)
    tasks = [_scrape(s, p, sem) for s, p in zip(sites, proxy_cycle)]
    prices = await asyncio.gather(*tasks)

    kept = []
    rejected = []
    failed = []
    for site, price in zip(sites, prices):
        if price is None:
            failed.append(site)
            continue
        if price < args.max_price:
            kept.append((site, price))
        else:
            rejected.append((site, price))

    with open(out_path, "w", encoding="utf-8") as f:
        for site, _ in kept:
            f.write(site + "\n")

    print(f"\n[+] Kept (price < ${args.max_price:.2f}): {len(kept)}")
    print(f"[-] Rejected (>= ${args.max_price:.2f}): {len(rejected)}")
    print(f"[?] Failed (scraper error): {len(failed)}")
    print(f"[+] Wrote: {out_path}")
    print(f"\nTo use this filtered list, replace sites.txt with this file")
    print(f"or temporarily swap the path in msh.py (SITES_FILE).")


if __name__ == "__main__":
    asyncio.run(main())
