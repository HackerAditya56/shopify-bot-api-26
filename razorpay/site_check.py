#!/usr/bin/env python3
"""
site_check.py — Razorpay site validator (single proxy + single international CC).

Theory: a site is GOOD if an international card gets a REAL response
(declined / 3DS / approved / charged). SERVER_ERROR = the site is soft-blocked
at ~10 checks -> recheck after a 2-minute cooldown. "international not supported"
or any other config error -> the site is not usable, skip it.

Every site's full request/response is dumped to a log dir so you can eyeball it.

Usage:
    python3 site_check.py --proxy "user:pass@host:port" --cc "4060|08|2029|248" \
        --sites sites.txt --out ./site_check_logs

    python3 site_check.py --proxy "..." --cc "..." --site https://pages.razorpay.com/foo
"""
import os
import re
import sys
import json
import time
import argparse

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from razorpay import RazorpaySession, parse_cc, parse_proxy

# reasons that mean "this site is fine, card just did a normal thing"
GOOD_REASONS = {
    "declined", "rzp_risk_decline", "card_expiry_invalid", "card_number_invalid",
    "card_network_not_enabled", "insufficient_funds", "online_payments_not_enabled",
    "card_type_not_allowed", "authentication_failed", "3ds", "three_ds",
}
# reasons that mean "site rejects international cards / misconfigured" -> skip
SKIP_REASONS = {
    "international_not_supported", "currency_mismatch", "invalid_fee",
    "amount_mismatch", "mandatory_item", "gay_site", "merchant_blocked",
    "merchant_not_activated", "payment_page_inactive", "site_unavailable",
    "site_change", "auth_required", "extra_field_sent", "invalid_email",
}

SERVER_ERROR_REASONS = {"rzp_server_error", "server_error"}


def _site_key(site):
    k = (site or "").strip().lower().rstrip("/")
    for p in ("http://", "https://"):
        if k.startswith(p):
            k = k[len(p):]
    return re.sub(r"[^a-z0-9._-]", "_", k)


def classify(result):
    status = str(result.get("status") or "").lower()
    reason = str(result.get("reason") or "").lower()
    msg = str(result.get("message") or "").lower()

    # hard SKIPs first (site unusable) — must beat the "dead = declined" fallback
    actual_paise = int(result.get("amount_paise") or 0)
    if actual_paise > 10000:
        return "SKIP", f"amount too high (₹{actual_paise // 100})"
    if "international" in msg and ("not support" in msg or "not allowed" in msg):
        return "SKIP", "international not supported"
    if reason in SKIP_REASONS:
        return "SKIP", reason

    # site soft-block (rate limit) -> recheck after cooldown
    if reason in SERVER_ERROR_REASONS or "server error" in msg:
        return "RECHECK", "server_error (site soft-block)"

    # real card responses -> site is fine
    if status in ("charged", "approved") or reason in ("charged", "approved"):
        return "GOOD", f"charged/approved ({reason})"
    if "3ds" in msg or "3d secure" in msg or "3-d secure" in msg or "3ds" in reason:
        return "GOOD", "3DS"
    if reason in ("declined", "rzp_risk_decline") or status == "dead":
        return "GOOD", "declined (" + (reason or "dead") + ")"
    if status == "error":
        return "SKIP", f"error: {reason or msg[:60]}"
    return "SKIP", f"unclassified: {status}/{reason}"


def run_checkout(site, cc, proxy, log):
    card = parse_cc(cc)
    year = card["expiry_year"]
    if len(year) == 2:
        year = "20" + year
    sess = RazorpaySession(
        payment_page_url=RazorpaySession._normalize_url(site), card=card,
        proxy=parse_proxy(proxy), traffic_env="canary", amount_paise=100,
        per_request_timeout=20.0,
    )
    sess._response_log = log
    try:
        result = sess.run()
    except Exception as e:
        result = {"status": "error", "message": str(e)[:300], "reason": "exception"}
    return result


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--proxy", required=True, help="single proxy (user:pass@host:port)")
    ap.add_argument("--cc", required=True, help="international card number|MM|YYYY|CVV")
    ap.add_argument("--sites", help="file with one site URL per line")
    ap.add_argument("--site", help="single site URL")
    ap.add_argument("--out", default="./site_check_logs", help="log dir")
    ap.add_argument("--delay", type=float, default=3.0, help="seconds between sites")
    ap.add_argument("--recheck-delay", type=float, default=120.0, help="SERVER_ERROR recheck cooldown (default 120s)")
    a = ap.parse_args()

    if a.sites:
        with open(a.sites, encoding="utf-8") as f:
            sites = [l.strip() for l in f if l.strip().startswith("http")]
    elif a.site:
        sites = [a.site]
    else:
        print("need --sites or --site"); sys.exit(1)

    os.makedirs(a.out, exist_ok=True)
    good, skipped, recheck = [], [], []

    def process(site_list, tag):
        for site in site_list:
            log = []
            t0 = time.time()
            result = run_checkout(site, a.cc, a.proxy, log)
            verdict, why = classify(result)
            entry = {
                "site": site,
                "verdict": verdict,
                "why": why,
                "result": result,
                "request_count": len(log),
                "duration_s": round(time.time() - t0, 2),
                "responses": log,
            }
            with open(os.path.join(a.out, f"{_site_key(site)}.json"), "w") as f:
                json.dump(entry, f, indent=2)
            print(f"[{tag}] {verdict:8s} {why:35s} {site}", flush=True)
            if verdict == "GOOD":
                good.append(site)
            elif verdict == "RECHECK":
                recheck.append(site)
            else:
                skipped.append(site)
            time.sleep(a.delay)

    print(f"== PASS 1: {len(sites)} sites ==", flush=True)
    process(sites, "pass1")

    # recheck SERVER_ERROR sites after cooldown
    if recheck:
        print(f"== SERVER_ERROR sites: {len(recheck)} -> recheck after {a.recheck_delay:.0f}s ==", flush=True)
        time.sleep(a.recheck_delay)
        retry = list(recheck)
        recheck.clear()
        process(retry, "recheck")

    with open(os.path.join(a.out, "good_sites.txt"), "w") as f:
        f.write("\n".join(good) + ("\n" if good else ""))
    summary = {
        "total": len(sites),
        "good": len(good),
        "skipped": len(skipped),
        "still_server_error": len(recheck),
        "good_sites": good,
        "skipped_sites": skipped,
        "server_error_sites": recheck,
    }
    with open(os.path.join(a.out, "summary.json"), "w") as f:
        json.dump(summary, f, indent=2)
    print(f"== DONE == good={len(good)} skipped={len(skipped)} server_error={len(recheck)}", flush=True)
    print(f"logs + good_sites.txt + summary.json -> {a.out}", flush=True)


if __name__ == "__main__":
    main()
