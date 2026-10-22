"""
Extract unique URLs from a PROBEX result log, verify each is still online against
the two Shopify APIs, and append verified working ones to mass_gates/sites.txt
(bare URL format, one per line).

Usage:
    py extract_and_verify_sites.py <input_log.txt> [--out sites.txt]
"""

import asyncio
import json
import os
import random
import re
import sys
import time
from pathlib import Path
from urllib.parse import urlparse

import aiohttp

SHOP = Path(__file__).resolve().parent
PROXIES_FILE = SHOP / "proxies.txt"
SITES_FILE_DEFAULT = SHOP / "mass_gates" / "sites.txt"

API_URLS = [
    ("http://38.247.64.215:5000/shopify", {"card": "cc", "url": "site"}),
]         

URL_REGEX = re.compile(r"https?://[A-Za-z0-9._\-]+(?:/[^\s|]*)?", re.IGNORECASE)
DEFAULT_CARD = "4111111111111111|12|2030|123|123"

# Key signature of a "real" working Shopify API response (after rename -> lowercase)
_WORKING_KEYS = (
    "response",
    "gateway",
    "price",
    "amount",
    "success",
    "status",
    "error",
)


def _normalize_url(url: str) -> str:
    u = url.strip().rstrip("/").lower()
    if not u.startswith(("http://", "https://")):
        u = "https://" + u
    return u


def extract_urls_from_log(text: str):
    seen, out = set(), []
    for line in text.splitlines():
        for m in URL_REGEX.finditer(line):
            u = _normalize_url(m.group(0))
            if u not in seen:
                seen.add(u)
                out.append(u)
    return out


def load_proxies_http():
    """proxies.txt uses `host:port:user:pass`; convert to http://user:pass@host:port."""
    if not PROXIES_FILE.exists():
        return []
    out = []
    for line in PROXIES_FILE.read_text(encoding="utf-8", errors="ignore").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        parts = line.split(":")
        if len(parts) == 4:
            host, port, user, pw = parts
            out.append(f"http://{user}:{pw}@{host}:{port}")
    return out


def load_existing_site_set(path: Path):
    if not path.exists():
        return set()
    return {
        line.strip()
        for line in path.read_text(encoding="utf-8", errors="ignore").splitlines()
        if line.strip() and not line.strip().startswith("#")
    }


def _build_params(card: str, site: str, proxy: str, renames: dict | None) -> dict:
    base = {"card": card, "url": site, "proxy": proxy}
    if not renames:
        return base
    return {renames.get(k, k): v for k, v in base.items()}


def _proxy_for_api_format(proxy: str) -> str:
    """Convert http://user:pass@host:port → host:port:user:pass (API expects raw form)."""
    if not proxy or not isinstance(proxy, str):
        return proxy
    p = proxy.strip()
    if not p.startswith(("http://", "https://")):
        return p
    rest = p.split("://", 1)[1]
    if "@" not in rest:
        return rest
    userinfo, hostport = rest.rsplit("@", 1)
    if ":" not in userinfo or ":" not in hostport:
        return rest
    try:
        user, password = userinfo.split(":", 1)
        host, port = hostport.rsplit(":", 1)
        if not port.isdigit():
            return rest
        return f"{host}:{port}:{user}:{password}"
    except Exception:
        return rest


def looks_like_working_response(data) -> bool:
    if not isinstance(data, dict):
        return False
    if any(k in data for k in _WORKING_KEYS):
        return True
    return False


async def verify_one(session: aiohttp.ClientSession, url: str, proxy: str, api_idx: int):
    api_url, renames = API_URLS[api_idx]
    card = DEFAULT_CARD.split("|")[0]
    params = _build_params(card, url, proxy, renames)
    try:
        async with session.get(api_url, params=params, timeout=aiohttp.ClientTimeout(total=20)) as resp:
            text = await resp.text()
            return resp.status, text[:400]
    except asyncio.TimeoutError:
        return None, "timeout"
    except Exception as e:
        return None, f"{type(e).__name__}: {e}"


async def main_async(in_log: Path, out_sites: Path):
    text = in_log.read_text(encoding="utf-8", errors="ignore")
    urls = extract_urls_from_log(text)
    print(f"[+] Extracted {len(urls)} unique URLs from log", flush=True)

    proxies = load_proxies_http()
    if not proxies:
        print("[!] No proxies loaded from proxies.txt; aborting", flush=True)
        return 2
    print(f"[+] Loaded {len(proxies)} proxies", flush=True)

    existing = load_existing_site_set(out_sites)
    print(f"[+] Existing entries in {out_sites.name}: {len(existing)}", flush=True)

    to_test = []
    for u in urls:
        bare = _normalize_url(u)
        if not bare or bare in existing:
            continue
        to_test.append(bare)
    print(f"[+] New URLs to verify: {len(to_test)}", flush=True)
    if not to_test:
        return 0

    sem = asyncio.Semaphore(20)
    proxy_cycle = [random.choice(proxies) for _ in range(200)]
    api_cycle = [i % len(API_URLS) for i in range(200)]
    rr_p = 0
    rr_a = 0

    verified = []
    failed_sample = []

    connector = aiohttp.TCPConnector(limit=50, ssl=False)
    async with aiohttp.ClientSession(connector=connector, headers={"User-Agent": "Mozilla/5.0"}) as sess:

        async def run_one(idx, bare):
            nonlocal rr_p, rr_a
            async with sem:
                proxy_url = proxy_cycle[rr_p % len(proxy_cycle)]
                api_idx = api_cycle[rr_a % len(api_cycle)]
                rr_p += 1
                rr_a += 1
                # API #2 (blacklisted) misparses http://user@host:port form —
                # convert to host:port:user:pass before sending.
                proxy_for_api = _proxy_for_api_format(proxy_url)
                status, body = await verify_one(sess, bare, proxy_for_api, api_idx)
                ok = False
                if status is not None:
                    try:
                        data = json.loads(body)
                        if isinstance(data, dict) and any(k in data for k in _WORKING_KEYS):
                            ok = True
                    except Exception:
                        ok = False
                return idx, bare, ok, status, body

        t0 = time.time()
        tasks = [asyncio.create_task(run_one(i, u)) for i, u in enumerate(to_test)]
        done_count = 0
        total = len(tasks)
        for fut in asyncio.as_completed(tasks):
            idx, bare, ok, status, body = await fut
            done_count += 1
            if ok:
                verified.append(bare)
            elif len(failed_sample) < 5:
                failed_sample.append((bare, status, body[:120]))
            if done_count % 50 == 0 or done_count == total:
                elapsed = time.time() - t0
                rate = done_count / max(1, elapsed)
                eta = (total - done_count) / max(0.1, rate)
                print(
                    f"  [{done_count}/{total}] verified={len(verified)} "
                    f"rate={rate:.1f}/s eta={eta/60:.1f}min",
                    flush=True,
                )
        print(f"[+] Verification done in {time.time()-t0:.1f}s — {len(verified)} working", flush=True)

    print("\n[+] Sample failures (first 5):")
    for u, s, b in failed_sample:
        print(f"   - {u}  status={s}  body={b!r}")

    if verified:
        with out_sites.open("a", encoding="utf-8") as f:
            for line in verified:
                f.write(line + "\n")
        print(f"[+] Appended {len(verified)} entries to {out_sites}")
    else:
        print("[!] No new verified entries")
    return 0


def main(argv):
    if len(argv) < 2:
        print("Usage: py extract_and_verify_sites.py <input_log.txt> [--out path]")
        return 1
    in_log = Path(argv[1]).resolve()
    out_sites = SITES_FILE_DEFAULT
    if "--out" in argv:
        i = argv.index("--out")
        if i + 1 < len(argv):
            out_sites = Path(argv[i + 1]).resolve()
    if not in_log.exists():
        print(f"[!] Input log not found: {in_log}")
        return 1
    return asyncio.run(main_async(in_log, out_sites))


if __name__ == "__main__":
    sys.exit(main(sys.argv))
