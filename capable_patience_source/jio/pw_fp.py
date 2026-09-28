"""Playwright (stealth) fingerprint + cookie capture for PayGlocal.
Loads the payflow-ui, lets FingerprintJS + ThreatMetrix mint a REAL visitorId,
then dumps cookies + the risk_fp payload for curl_cffi to reuse.
Usage: python pw_fp.py <xgl_token> <proxy>
Output JSON: {"cookies": {...}, "visitorId": "...", "requestId": "..."}
"""
import json, sys, time

def parse_proxy(proxy):
    p = proxy.strip()
    if "://" in p: p = p.split("://", 1)[1]
    if "@" in p:
        auth, hp = p.split("@", 1); u, pw = auth.split(":", 1); h, port = hp.split(":", 1)
        return {"server": f"http://{h}:{port}", "username": u, "password": pw}
    parts = p.split(":")
    if len(parts) == 4:
        h, port, u, pw = parts  # host:port:user:pass
        return {"server": f"http://{h}:{port}", "username": u, "password": pw}
    return {"server": f"http://{parts[0]}:{parts[1]}"}

STEALTH_JS = """
Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
window.chrome = window.chrome || { runtime: {} };
Object.defineProperty(navigator, 'languages', {get: () => ['en-US', 'en']});
Object.defineProperty(navigator, 'plugins', {get: () => [1,2,3,4,5]});
"""

def main():
    xgl, proxy = sys.argv[1], sys.argv[2]
    proxy_cfg = parse_proxy(proxy)
    from playwright.sync_api import sync_playwright
    risk_fp_req = {}
    risk_fp_resp = {}
    dc_resp = {}
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, proxy=proxy_cfg,
            args=["--disable-blink-features=AutomationControlled"])
        ctx = browser.new_context(viewport={"width":1920,"height":1080},
            user_agent="Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36")
        ctx.add_init_script(STEALTH_JS)
        page = ctx.new_page()
        def on_req(req):
            if "risk/fp" in req.url:
                try: risk_fp_req["body"] = req.post_data
                except Exception: pass
        def on_resp(resp):
            if "risk/fp" in resp.url:
                try: risk_fp_resp["body"] = resp.text()
                except Exception: pass
            elif "redirect/dc" in resp.url:
                try: dc_resp["body"] = resp.text()
                except Exception: pass
        page.on("request", on_req)
        page.on("response", on_resp)
        page.goto(f"https://api.payglocal.com/gl/payflow-ui/?x-gl-token={xgl}",
                  timeout=45000, wait_until="domcontentloaded")
        # human-like mouse movement while the page settles
        page.mouse.move(400, 300)
        for i in range(12):
            page.mouse.move(400 + (i*37) % 500, 300 + (i*53) % 300, steps=8)
            page.wait_for_timeout(120)
        # wait for risk_fp to fire
        for _ in range(25):
            if risk_fp_req.get("body"):
                break
            page.wait_for_timeout(1000)
        cookies = ctx.cookies()
        browser.close()
    out = {"cookies": {c["name"]: c["value"] for c in cookies}}
    if risk_fp_req.get("body"):
        try:
            body = json.loads(risk_fp_req["body"])
            out["visitorId"] = body.get("visitorId", "")
            out["requestId"] = body.get("requestId", "")
            out["visitorFound"] = body.get("visitorFound", "true")
            out["confidenceScore"] = body.get("confidenceScore", "1")
        except Exception:
            pass
    if dc_resp.get("body"):
        try: out["dc_resp"] = json.loads(dc_resp["body"])
        except Exception: out["dc_resp"] = dc_resp["body"][:500]
    if risk_fp_resp.get("body"):
        try:
            out["risk_fp_resp"] = json.loads(risk_fp_resp["body"])
        except Exception:
            out["risk_fp_resp"] = risk_fp_resp["body"][:500]
    print(json.dumps(out))

if __name__ == "__main__":
    main()
