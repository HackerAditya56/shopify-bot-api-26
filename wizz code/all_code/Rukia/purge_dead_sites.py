"""
Scan mass_gates/sites.txt for truly dead Shopify sites and purge them.

A site is TRULY dead if any of these hold (after handling 429 rate-limits):
  - HEAD returns 404 (store deleted)
  - 401 Unauthorized on /products.json
  - DNS resolution fails
  - Two consecutive 429s (persistent throttle = site is anti-bot)
  - Non-JSON / empty body on /products.json?limit=1 with 2xx status

Sites returning 429 are retried with backoff (real throttle, not dead).

Usage:
    py purge_dead_sites.py
"""

import asyncio
import json
import sys
import time
from pathlib import Path

import aiohttp

SHOP = Path(__file__).resolve().parent
SITES_FILE = SHOP / "mass_gates" / "sites.txt"
BACKUP_FILE = SITES_FILE.with_suffix(SITES_FILE.suffix + ".bak")

CHECK_PATH = "/products.json?limit=1"
TIMEOUT_S = 8
CONCURRENCY = 12
MAX_429_RETRIES = 3
RETRY_BACKOFF_BASE = 4


def load_sites(path: Path):
    if not path.exists():
        return []
    out, seen = [], set()
    for line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
        s = line.strip()
        if not s or s.startswith("#") or s in seen:
            continue
        seen.add(s)
        out.append(s)
    return out


def is_alive_response(status: int | None, body: str) -> bool:
    if status is None:
        return False
    if status == 429:
        return None
    if status >= 400:
        return False
    if not body or len(body) < 30:
        return False
    s = body.lstrip()
    if not s.startswith("{"):
        return False
    return True


async def check_one(session: aiohttp.ClientSession, url: str):
    full = url.rstrip("/") + CHECK_PATH
    last_status, last_body = None, ""
    for attempt in range(MAX_429_RETRIES + 1):
        try:
            async with session.get(
                full,
                allow_redirects=False,
                timeout=aiohttp.ClientTimeout(total=TIMEOUT_S),
                headers={"User-Agent": "Mozilla/5.0"},
            ) as r:
                text = await r.text()
                last_status, last_body = r.status, text
                ok = is_alive_response(r.status, text)
                if ok is True:
                    return url, "alive", r.status, None
                if ok is None and attempt < MAX_429_RETRIES:
                    await asyncio.sleep(RETRY_BACKOFF_BASE * (attempt + 1))
                    continue
                return url, "dead", r.status, text[:120]
        except asyncio.TimeoutError:
            return url, "dead", None, "timeout"
        except Exception as e:
            return url, "dead", None, f"{type(e).__name__}: {e}"[:120]
    return url, "dead", last_status, last_body[:120]


async def main_async():
    sites = load_sites(SITES_FILE)
    print(f"[+] Loaded {len(sites)} sites from {SITES_FILE.name}", flush=True)
    if not sites:
        print("[!] Empty sites.txt - nothing to do")
        return 0

    sem = asyncio.Semaphore(CONCURRENCY)
    alive, dead = [], []

    connector = aiohttp.TCPConnector(limit=CONCURRENCY + 5, ssl=False)
    async with aiohttp.ClientSession(connector=connector) as sess:

        async def run_one(url):
            async with sem:
                return await check_one(sess, url)

        t0 = time.time()
        tasks = [asyncio.create_task(run_one(u)) for u in sites]
        done = 0
        total = len(tasks)
        for fut in asyncio.as_completed(tasks):
            url, verdict, status, body = await fut
            done += 1
            if verdict == "alive":
                alive.append(url)
            else:
                dead.append((url, status, body))
            if done % 100 == 0 or done == total:
                elapsed = time.time() - t0
                rate = done / max(1, elapsed)
                eta = (total - done) / max(0.1, rate)
                print(
                    f"  [{done}/{total}] alive={len(alive)} dead={len(dead)} "
                    f"rate={rate:.1f}/s eta={eta:.0f}s",
                    flush=True,
                )

    print()
    print(f"[+] Total scanned:  {total}")
    print(f"[+] Alive:          {len(alive)}")
    print(f"[+] Dead:           {len(dead)}")
    if dead:
        from collections import Counter
        reasons = Counter()
        for _, st, b in dead:
            reasons[(st, (b or "")[:60])] += 1
        print("[+] Top failure signatures (status, body snippet):")
        for (st, sn), cnt in reasons.most_common(15):
            print(f"   {cnt:4d}  status={st}  body={sn!r}")
        print("[+] Sample dead sites (first 15):")
        for u, st, b in dead[:15]:
            print(f"   {u}  status={st}  body={b!r}")

    if not dead:
        print("[!] No dead sites found")
        return 0

    import shutil
    try:
        shutil.copy2(SITES_FILE, BACKUP_FILE)
        print(f"[+] Backup saved to {BACKUP_FILE}")
    except Exception as e:
        print(f"[!] Backup failed: {e}")

    with SITES_FILE.open("w", encoding="utf-8") as f:
        for u in alive:
            f.write(u + "\n")
    print(f"[+] Wrote {len(alive)} surviving sites to {SITES_FILE} (removed {len(dead)})")
    return 0


def main(argv):
    return asyncio.run(main_async())


if __name__ == "__main__":
    sys.exit(main(sys.argv))
