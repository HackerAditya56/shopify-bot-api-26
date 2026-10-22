#!/usr/bin/env python3
"""bms_test_proxy.py — real headful-Chrome proxy test for BookMyShow.

BMS/Cloudflare returns 403 to every plain HTTP request (even a clean IP), so a
curl check can never tell a good proxy from a bad one. The only real verdict is:
launch headful Chrome through the proxy, load the explore home page, and see if
Cloudflare hands back a cf_clearance cookie (the same check /bms performs).

Run (headful needs a display — xvfb-run -a on a VPS):
    xvfb-run -a python3 bms_test_proxy.py --proxy "http://user:pass@host:port"

Prints one verdict line:
    OK       -> proxy passes Cloudflare (add it)
    BLOCKED  -> challenge not solved / 403 (skip)
    DEAD     -> unreachable / timeout (skip)
"""
import argparse
import sys
import time
import urllib.parse

from playwright.sync_api import sync_playwright

BMS_PAGE = "https://in.bookmyshow.com/explore/home/patna"
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"


def parse_proxy(proxy_url: str) -> dict:
    if not proxy_url:
        return {}
    u = urllib.parse.urlparse(proxy_url if "://" in proxy_url else "http://" + proxy_url)
    d = {"server": f"{u.scheme}://{u.hostname}:{u.port or 80}"}
    if u.username:
        d["username"] = urllib.parse.unquote(u.username)
        d["password"] = urllib.parse.unquote(u.password or "")
    return d


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--proxy", required=True)
    ap.add_argument("--timeout", type=int, default=45)
    args = ap.parse_args()

    try:
        with sync_playwright() as pw:
            proxy = parse_proxy(args.proxy)
            browser = pw.chromium.launch(
                headless=False,
                proxy=proxy,
                args=[
                    "--no-sandbox",
                    "--disable-blink-features=AutomationControlled",
                    "--disable-gpu",
                    "--disable-dev-shm-usage",
                    "--disable-software-rasterizer",
                    "--no-zygote",
                ],
            )
            ctx = browser.new_context(user_agent=UA, viewport={"width": 1366, "height": 768}, locale="en-IN")
            page = ctx.new_page()
            try:
                page.goto(BMS_PAGE, timeout=60000, wait_until="domcontentloaded")
                deadline = time.time() + args.timeout
                while time.time() < deadline:
                    page.wait_for_timeout(2000)
                    try:
                        cookies = ctx.cookies()
                    except Exception:
                        cookies = []
                    if any(c.get("name") == "cf_clearance" for c in cookies):
                        print("OK", flush=True)
                        return
                print("BLOCKED", flush=True)
            finally:
                try:
                    browser.close()
                except Exception:
                    pass
    except Exception as e:
        print(f"DEAD {str(e)[:80]}", flush=True)


if __name__ == "__main__":
    main()
