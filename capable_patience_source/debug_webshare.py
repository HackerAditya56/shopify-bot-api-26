#!/usr/bin/env python3
"""
debug_webshare.py — verbose step-by-step debug for the webshare generator.

Run on the VPS to see exactly where it breaks:
    xvfb-run -a python3 debug_webshare.py --proxy "user:pass@host:port" --scheme socks5
Prints every step + the full traceback on any error.
"""
import argparse
import os
import sys
import time
import traceback


def step(msg):
    print(f"[STEP] {msg}", flush=True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--proxy", default="")
    ap.add_argument("--scheme", default="socks5")
    args = ap.parse_args()

    # 1. deps
    step("checking python deps...")
    try:
        import undetected_chromedriver as uc
        print(f"  undetected_chromedriver {uc.__version__ if hasattr(uc,'__version__') else 'ok'}")
    except Exception as e:
        print(f"  FAIL undetected_chromedriver: {e}")
        sys.exit(1)
    try:
        import selenium
        print(f"  selenium {selenium.__version__}")
    except Exception as e:
        print(f"  FAIL selenium: {e}")
        sys.exit(1)
    try:
        from webdriver_manager.chrome import ChromeDriverManager
    except Exception as e:
        print(f"  FAIL webdriver_manager: {e}")
        sys.exit(1)

    # 2. browser binary
    step("finding a Chrome/Chromium binary...")
    import shutil
    candidates = ["/usr/bin/google-chrome", "/usr/bin/google-chrome-stable",
                  "/usr/bin/chromium-browser", "/usr/bin/chromium", "/snap/bin/chromium"]
    browser = None
    for c in candidates:
        if os.path.exists(c):
            browser = c
            break
    if not browser:
        browser = (shutil.which("google-chrome") or shutil.which("google-chrome-stable")
                   or shutil.which("chromium") or shutil.which("chromium-browser"))
    if not browser:
        print("  FAIL: no Chrome/Chromium binary found. apt-get install -y google-chrome-stable")
        sys.exit(1)
    print(f"  browser: {browser}")

    # 3. chromedriver
    step("installing chromedriver (webdriver-manager)...")
    try:
        cd_path = ChromeDriverManager().install()
        print(f"  chromedriver: {cd_path}")
    except Exception as e:
        print(f"  FAIL chromedriver: {e}")
        traceback.print_exc()
        sys.exit(1)

    # 4. proxy
    step("parsing proxy...")
    raw = args.proxy or ""
    for pref in ("socks5://", "socks4://", "http://", "https://"):
        if raw.lower().startswith(pref):
            raw = raw[len(pref):]
            break
    if "@" in raw:
        auth, hostport = raw.rsplit("@", 1)
        u, _, pw = auth.partition(":")
        h, _, pt = hostport.partition(":")
    else:
        parts = raw.split(":")
        if len(parts) == 4:
            h, pt, u, pw = parts
        elif len(parts) == 2:
            h, pt, u, pw = parts[0], parts[1], "", ""
        else:
            print(f"  FAIL: bad proxy format: {args.proxy!r}")
            sys.exit(1)
    print(f"  host={h} port={pt} user={u} pass={'*'*len(pw) if pw else ''} scheme={args.scheme}")

    # 5. launch
    step("launching Chrome (undetected)...")
    opts = uc.ChromeOptions()
    opts.add_argument("--window-size=1280,720")
    opts.add_argument("--disable-blink-features=AutomationControlled")
    opts.add_argument("--incognito")
    opts.add_argument("--no-sandbox")
    opts.add_argument("--disable-dev-shm-usage")
    if os.environ.get("HEADLESS") == "1":
        opts.add_argument("--headless=new")
    # proxy extension
    ext = None
    if args.proxy:
        d = os.path.join("/tmp", f"dbgext_{int(time.time())}")
        os.makedirs(d, exist_ok=True)
        with open(os.path.join(d, "manifest.json"), "w") as f:
            f.write('{"version":"1.0","manifest_version":2,"name":"P","permissions":["proxy","webRequest","webRequestBlocking","<all_urls>"],"background":{"scripts":["b.js"]}}')
        js = 'var c={"mode":"fixed_servers","rules":{"singleProxy":{"scheme":"%s","host":"%s","port":%s}}};chrome.proxy.settings.set({value:c,scope:"regular"});chrome.webRequest.onAuthRequired.addListener(function(d){return {authCredentials:{username:"%s",password:"%s"}}},{urls:["<all_urls>"]},["blocking"]);'
        with open(os.path.join(d, "b.js"), "w") as f:
            f.write(js % (args.scheme, h, pt, u, pw))
        opts.add_argument(f"--load-extension={d}")
        ext = d
        print(f"  proxy extension loaded: {d}")
    try:
        driver = uc.Chrome(options=opts, driver_executable_path=cd_path, browser_executable_path=browser)
        print("  Chrome launched OK")
    except Exception as e:
        print(f"  FAIL Chrome launch: {e}")
        traceback.print_exc()
        sys.exit(1)

    try:
        # 6. load register page
        step("loading register page...")
        driver.get("https://dashboard.webshare.io/register?source=login_signup_link")
        time.sleep(3)
        print(f"  url: {driver.current_url[:80]}")
        title = driver.title or ""
        print(f"  title: {title[:60]}")

        # 7. fill form
        step("filling email + password...")
        from selenium.webdriver.common.by import By
        from selenium.webdriver.support.ui import WebDriverWait
        from selenium.webdriver.support import expected_conditions as EC
        w = WebDriverWait(driver, 20)
        email = f"dbg{int(time.time())}@outlook.com"
        em = w.until(EC.element_to_be_clickable((By.ID, "email-input")))
        em.click(); em.clear(); em.send_keys(email)
        print(f"  email: {email}")
        pw_el = w.until(EC.element_to_be_clickable((By.CSS_SELECTOR, "input[type='password']")))
        pw_el.click(); pw_el.clear(); pw_el.send_keys("Dbg12345!x")
        time.sleep(1)
        print("  filled")

        # 8. submit
        step("clicking submit...")
        try:
            cb = driver.find_element(By.CSS_SELECTOR, "input[type='checkbox']")
            if not cb.is_selected():
                cb.click()
        except Exception:
            pass
        driver.find_element(By.CSS_SELECTOR, "button[type='submit']").click()
        print("  submit clicked")

        # 9. click the reCAPTCHA checkbox (inside the recaptcha iframe)
        step("clicking reCAPTCHA checkbox...")
        clicked = False
        for i in range(20):
            time.sleep(1)
            try:
                frames = driver.find_elements(By.CSS_SELECTOR, "iframe[src*='recaptcha']")
                for fr in frames:
                    driver.switch_to.frame(fr)
                    try:
                        anchor = driver.find_element(By.ID, "recaptcha-anchor")
                        if anchor:
                            anchor.click()
                            clicked = True
                            print("  checkbox clicked")
                            break
                    except Exception:
                        pass
                    finally:
                        driver.switch_to.default_content()
            except Exception:
                pass
            if clicked:
                break
        if not clicked:
            print("  could not find/click the reCAPTCHA checkbox")

        # 10. wait for the token
        step("waiting for reCAPTCHA token...")
        token = None
        for i in range(60):
            time.sleep(1)
            try:
                t = driver.execute_script("return grecaptcha.getResponse();")
                if t:
                    token = t
                    print(f"  captcha token obtained ({len(t)} chars) after {i+1}s")
                    break
            except Exception:
                pass
        if not token:
            print("  NO captcha token after 60s — captcha challenge shown?")
            try:
                body = driver.execute_script("return document.body.innerText.slice(0,400)")
                print(f"  page body: {body!r}")
            except Exception:
                pass
        print(f"  url now: {driver.current_url[:80]}")
    finally:
        try:
            driver.close()
        except Exception:
            pass
        if ext and os.path.exists(ext):
            import shutil as _sh
            _sh.rmtree(ext, ignore_errors=True)
    print("[DONE]", flush=True)


if __name__ == "__main__":
    main()
