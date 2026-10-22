"""
webshare_gen.py - headless webshare.io account generator (from websh.py).

One-shot: create an account (browser + invisible reCAPTCHA) and return the
ROTATING proxy endpoint (p.webshare.io:80:{user}-rotate:{pass}).

VPS / no display: headful under xvfb (most reliable for reCAPTCHA) or --headless.
CLI:  xvfb-run -a python3 webshare_gen.py --proxy "http://user:pass@host:port" --scheme socks5
Module: from webshare_gen import generate_one
"""
import os, random, re, string, sys, time
import requests
import undetected_chromedriver as uc
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC


def _find_browser():
    """Locate a Chrome/Chromium binary (incl. snap)."""
    import shutil
    for cand in ("/usr/bin/google-chrome", "/usr/bin/google-chrome-stable",
                 "/usr/bin/chromium-browser", "/usr/bin/chromium", "/snap/bin/chromium"):
        if os.path.exists(cand):
            return cand
    return (shutil.which("google-chrome") or shutil.which("google-chrome-stable")
            or shutil.which("chromium") or shutil.which("chromium-browser"))


def rand_str(k=8):
    return "".join(random.choices(string.ascii_lowercase, k=k))


def unique_email():
    existing = set()
    try:
        with open("accounts.txt") as f:
            for l in f:
                if ":" in l:
                    existing.add(l.split(":")[0].strip())
    except Exception:
        pass
    while True:
        e = f"{rand_str(6)}{random.randint(100, 9999)}@outlook.com"
        if e not in existing:
            return e


def make_auth_ext(ip, port, user, pwd, scheme):
    d = os.path.join(os.environ.get("TEMP", "/tmp"), f"ext_{rand_str()}")
    os.makedirs(d, exist_ok=True)
    with open(os.path.join(d, "manifest.json"), "w") as f:
        f.write('{"version":"1.0","manifest_version":2,"name":"P","permissions":["proxy","webRequest","webRequestBlocking","<all_urls>"],"background":{"scripts":["b.js"]}}')
    js = 'var c={"mode":"fixed_servers","rules":{"singleProxy":{"scheme":"%s","host":"%s","port":%s}}};chrome.proxy.settings.set({value:c,scope:"regular"});chrome.webRequest.onAuthRequired.addListener(function(d){return {authCredentials:{username:"%s",password:"%s"}}},{urls:["<all_urls>"]},["blocking"]);'
    with open(os.path.join(d, "b.js"), "w") as f:
        f.write(js % (scheme, ip, port, user, pwd))
    return d


def parse_proxy(proxy_str):
    s = (proxy_str or "").strip()
    for pref in ("socks5://", "socks4://", "http://", "https://"):
        if s.lower().startswith(pref):
            s = s[len(pref):]
            break
    if "@" in s:
        auth, hostport = s.rsplit("@", 1)
        u, _, p = auth.partition(":")
        h, _, pt = hostport.partition(":")
        return h, pt, u, p
    x = s.split(":")
    if len(x) == 4:
        return x[0], x[1], x[2], x[3]
    if len(x) == 2:
        return x[0], x[1], "", ""
    return None


def fetch_rotating_proxy(at):
    h2 = {"Authorization": f"Token {at}", "Accept": "application/json",
          "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
          "Origin": "https://dashboard.webshare.io", "Referer": "https://dashboard.webshare.io/"}
    r2 = requests.get("https://proxy.webshare.io/api/v2/proxy/list/", headers=h2,
                      params={"mode": "direct", "page": "1", "page_size": "10"}, timeout=20)
    if r2.status_code != 200:
        return None, []
    results = r2.json().get("results", [])
    if not results:
        return None, []
    user = results[0].get("username", "")
    pw = results[0].get("password", "")
    rotating = f"p.webshare.io:80:{user}-rotate:{pw}" if user and pw else None
    individuals = [f"{x['proxy_address']}:{x['port']}:{x['username']}:{x['password']}" for x in results]
    return rotating, individuals


def generate_one(proxy_str=None, scheme="socks5", headless=False):
    """Create one webshare account + return the rotating proxy line, or None."""
    email = unique_email()
    password = rand_str(8) + random.choice(string.digits) + random.choice(string.ascii_uppercase) + "x"

    from webdriver_manager.chrome import ChromeDriverManager
    cd_path = ChromeDriverManager().install()
    opts = uc.ChromeOptions()
    opts.add_argument("--window-size=1280,720")
    opts.add_argument("--disable-blink-features=AutomationControlled")
    opts.add_argument("--incognito")
    opts.add_argument("--no-sandbox")
    opts.add_argument("--disable-dev-shm-usage")
    if headless:
        opts.add_argument("--headless=new")

    ext = None
    if proxy_str:
        p = parse_proxy(proxy_str)
        if p:
            h, pt, u, pw = p
            ext = make_auth_ext(h, pt, u, pw, scheme)
            if ext:
                opts.add_argument(f"--load-extension={ext}")

    browser_path = _find_browser()
    driver = uc.Chrome(options=opts, driver_executable_path=cd_path, browser_executable_path=browser_path)
    w = WebDriverWait(driver, 20)
    rotating = None

    try:
        driver.get("https://dashboard.webshare.io/register?source=login_signup_link")
        time.sleep(1)

        em = w.until(EC.element_to_be_clickable((By.ID, "email-input")))
        em.click(); em.clear(); em.send_keys(email)
        if not driver.execute_script("return arguments[0].value;", em):
            driver.execute_script("arguments[0].value = arguments[1];", em, email)
        time.sleep(0.3)

        pw_el = w.until(EC.element_to_be_clickable((By.CSS_SELECTOR, "input[type='password']")))
        pw_el.click(); pw_el.clear(); pw_el.send_keys(password)
        if not driver.execute_script("return arguments[0].value;", pw_el):
            driver.execute_script("arguments[0].value = arguments[1];", pw_el, password)
        time.sleep(0.3)

        try:
            cb = driver.find_element(By.CSS_SELECTOR, "input[type='checkbox']")
            if not cb.is_selected():
                cb.click()
        except Exception:
            pass

        time.sleep(0.3)
        driver.find_element(By.CSS_SELECTOR, "button[type='submit']").click()

        # click the reCAPTCHA checkbox (inside the recaptcha iframe) — webshare uses
        # a checkbox captcha, not invisible, so the token only appears after the click
        for _ in range(20):
            time.sleep(1)
            try:
                frames = driver.find_elements(By.CSS_SELECTOR, "iframe[src*='recaptcha']")
                for fr in frames:
                    driver.switch_to.frame(fr)
                    try:
                        anchor = driver.find_element(By.ID, "recaptcha-anchor")
                        if anchor:
                            anchor.click()
                            break
                    except Exception:
                        pass
                    finally:
                        driver.switch_to.default_content()
            except Exception:
                pass
        driver.switch_to.default_content()

        # wait for the reCAPTCHA token / form to auto-submit
        token = None
        for _ in range(90):
            time.sleep(1)
            try:
                t = driver.execute_script("return grecaptcha.getResponse();")
                if t:
                    token = t
                    break
            except Exception:
                pass
            try:
                cur = driver.current_url
                if "register" not in cur and "login" not in cur:
                    break
            except Exception:
                pass
        if not token:
            print("DEBUG: no recaptcha token after 90s (captcha challenge?)", flush=True)
            # dump page state
            try:
                body = driver.execute_script("return document.body.innerText.slice(0,300)")
                print(f"DEBUG: page body: {body!r}", flush=True)
            except Exception:
                pass

        # authoritative: token in localStorage OR cookie -> fetch proxies
        for _ in range(10):
            time.sleep(1)
            try:
                at = driver.execute_script("return localStorage.getItem('token') || '';")
                if not at:
                    at = driver.execute_script("return (document.cookie.match(/token=([^;]+)/)||[])[1] || '';")
                if at:
                    rotating, _ = fetch_rotating_proxy(at)
                    if rotating:
                        break
            except Exception:
                pass

        # fallback: API register with the solved captcha token (direct)
        if not rotating and token:
            cookies = {c["name"]: c["value"] for c in driver.get_cookies()}
            cs = "; ".join(f"{k}={v}" for k, v in cookies.items())
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:153.0) Gecko/20100101 Firefox/153.0",
                "Accept": "application/json, text/plain, */*",
                "Content-Type": "application/json",
                "Origin": "https://dashboard.webshare.io",
                "Referer": "https://dashboard.webshare.io/",
                "Cookie": cs,
            }
            data = {"email": email, "password": password, "tos_accepted": True, "recaptcha": token}
            resp = requests.post("https://proxy.webshare.io/api/v2/register/", headers=headers, json=data, timeout=30)
            if resp.status_code in (200, 201):
                at = resp.json().get("token", "")
                if at:
                    time.sleep(1)
                    rotating, _ = fetch_rotating_proxy(at)

        if rotating:
            with open("accounts.txt", "a") as f:
                f.write(f"{email}:{password}\n")
        return rotating
    finally:
        try:
            driver.close()
        except Exception:
            pass
        if ext and os.path.exists(ext):
            import shutil
            shutil.rmtree(ext, ignore_errors=True)


if __name__ == "__main__":
    import argparse, json, traceback
    ap = argparse.ArgumentParser()
    ap.add_argument("--proxy", default="")
    ap.add_argument("--scheme", default="socks5")
    ap.add_argument("--headless", action="store_true")
    args = ap.parse_args()
    try:
        rotating = generate_one(args.proxy or None, args.scheme, args.headless)
        print(json.dumps({"rotating": rotating or "", "proxy": args.proxy}))
    except Exception as e:
        # always emit a JSON line so the bot's parser doesn't hit empty output
        print(json.dumps({"rotating": "", "proxy": args.proxy, "error": str(e)[:200]}))
        traceback.print_exc()
