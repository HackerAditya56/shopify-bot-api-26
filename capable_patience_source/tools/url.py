# url.py — Advanced Site Analyzer (Site Lookup / Gate Scanner)
# Enhanced with reference patterns from the JINX GATE BOT analyzer.

import re
import asyncio
import logging
import time
import socket
import aiohttp
from bs4 import BeautifulSoup
from urllib.parse import urlparse, urljoin

from aiogram import types, F
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

from database import get_user_credits, update_credits, PooledConn
from sub import get_premium_status
from mass_gates._tg_helpers import safe_reply

user_last_command_time = {}

_session: aiohttp.ClientSession = None
_session_lock = asyncio.Lock()

# ── SSRF-safe URL validation ─────────────────────────────────────────
def is_safe_url(url: str):
    try:
        parsed = urlparse(url)
        if parsed.scheme not in ('http', 'https'):
            return False, "Only HTTP/HTTPS URLs are allowed"
        hostname = parsed.hostname
        if not hostname:
            return False, "Invalid URL"
        port = parsed.port or (443 if parsed.scheme == 'https' else 80)
        if port not in (80, 443, 8080, 8443):
            return False, f"Port {port} is not allowed"
        infos = socket.getaddrinfo(hostname, port, socket.AF_UNSPEC, socket.SOCK_STREAM)
        for _fam, _t, _p, _cn, sockaddr in infos:
            ip = sockaddr[0]
            if any([
                ip.startswith('10.'), ip.startswith('192.168.'),
                ip.startswith('127.'), ip.startswith('169.254.'),
                ip.startswith('172.16.') or ip.startswith('172.17.') or
                ip.startswith('172.18.') or ip.startswith('172.19.') or
                ip.startswith('172.20.') or ip.startswith('172.21.') or
                ip.startswith('172.22.') or ip.startswith('172.23.') or
                ip.startswith('172.24.') or ip.startswith('172.25.') or
                ip.startswith('172.26.') or ip.startswith('172.27.') or
                ip.startswith('172.28.') or ip.startswith('172.29.') or
                ip.startswith('172.30.') or ip.startswith('172.31.'),
                ip.startswith('0.'), ip.startswith('fc'), ip.startswith('fe80'),
                '::1' in ip or '::' == ip
            ]):
                return False, f"Blocked private/internal IP: {ip}"
        return True, "OK"
    except socket.gaierror:
        return False, "Cannot resolve hostname"
    except Exception as e:
        return False, f"URL validation error: {str(e)}"

# ── Session ──────────────────────────────────────────────────────────
async def get_session():
    global _session
    async with _session_lock:
        if _session is None or _session.closed:
            connector = aiohttp.TCPConnector(limit=50, limit_per_host=10, ttl_dns_cache=300)
            timeout = aiohttp.ClientTimeout(total=20, connect=10)
            _session = aiohttp.ClientSession(connector=connector, timeout=timeout)
            logging.info("[URL] HTTP Session created")
    return _session

# ── DB helpers ───────────────────────────────────────────────────────
def ensure_url_stats_columns():
    try:
        with PooledConn() as conn:
            c = conn.cursor()
            c.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS site_lookups INTEGER DEFAULT 0")
            conn.commit()
        logging.info("[URL] stats columns checked")
    except Exception as e:
        logging.error(f"[URL] stats err: {e}")

ensure_url_stats_columns()

async def update_lookup_stats(user_id: int):
    def _f():
        with PooledConn() as conn:
            c = conn.cursor()
            c.execute("UPDATE users SET site_lookups = site_lookups + 1 WHERE user_id = %s", (user_id,))
            conn.commit()
    await asyncio.to_thread(_f)

async def get_user_plan_name(user_id: int) -> str:
    premium_result = await asyncio.to_thread(get_premium_status, user_id)
    is_premium = premium_result[0] if isinstance(premium_result, tuple) else False
    if is_premium:
        def _f():
            with PooledConn() as conn:
                c = conn.cursor()
                c.execute("SELECT plan FROM receipts WHERE user_id = %s ORDER BY purchased_on DESC LIMIT 1", (user_id,))
                row = c.fetchone()
                return row[0].upper() if row else "PREMIUM"
        try:
            return await asyncio.to_thread(_f)
        except Exception:
            return "PREMIUM"
    return "FREE"

# ── Fetch ────────────────────────────────────────────────────────────
async def fetch_site(url: str):
    if not url.startswith(("http://", "https://")):
        url = "https://" + url
    safe, reason = is_safe_url(url)
    if not safe:
        return None, None, None, reason
    session = await get_session()
    domain = urlparse(url).netloc
    headers = {
        "accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
        "accept-language": "en-US,en;q=0.9",
        "cache-control": "max-age=0",
        "sec-fetch-dest": "document",
        "sec-fetch-mode": "navigate",
        "sec-fetch-site": "none",
        "sec-fetch-user": "?1",
        "upgrade-insecure-requests": "1",
        "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36",
    }
    try:
        async with session.get(url, headers=headers, timeout=15, allow_redirects=True) as resp:
            html = await resp.text()
            return resp.status, html, dict(resp.headers), str(resp.url)
    except asyncio.TimeoutError:
        return None, None, None, "Timeout"
    except Exception as e:
        return None, None, None, str(e)[:120]

# ── Detection: captcha (advanced) ────────────────────────────────────
def detect_captcha(html):
    types = []
    h = html.lower()
    if any(re.search(p, html, re.I) for p in [r'google\.com/recaptcha', r'grecaptcha', r'g-recaptcha', r'recaptcha/api\.js', r'data-sitekey=', r'6L[a-zA-Z0-9_-]{38}']):
        if 'recaptcha/enterprise' in h or 'grecaptcha.enterprise' in h:
            types.append('reCAPTCHA Enterprise')
        elif 'grecaptcha.execute' in h or 'recaptcha v3' in h:
            types.append('reCAPTCHA v3')
        elif 'g-recaptcha' in h or 'recaptcha/api.js' in h:
            types.append('reCAPTCHA v2')
        else:
            types.append('reCAPTCHA')
    if any(re.search(p, html, re.I) for p in [r'hcaptcha\.com', r'h-captcha', r'data-hcaptcha', r'hcaptcha/api\.js', r'hcaptcha\.render']):
        types.append('hCaptcha')
    if any(re.search(p, html, re.I) for p in [r'challenges\.cloudflare\.com/turnstile', r'cf-turnstile', r'turnstile/v0', r'_cf_chl_opt']):
        types.append('Cloudflare Turnstile')
    if any(re.search(p, html, re.I) for p in [r'cf_chl_jschl', r'cf-challenge', r'__cf_chl_jschl_tk__', r'challenge-platform']):
        if 'Cloudflare Turnstile' not in types:
            types.append('Cloudflare Challenge')
    if re.search(r'friendlycaptcha|frc-captcha|friendly-challenge', html, re.I):
        types.append('FriendlyCaptcha')
    if re.search(r'funcaptcha|arkoselabs|arkose|enforcement\.arkoselabs|api\.funcaptcha', html, re.I):
        types.append('FunCaptcha/Arkose')
    if re.search(r'geetest\.com|gt-captcha|geetest_', html, re.I):
        types.append('GeeTest')
    if re.search(r'awswaf|aws-waf-token|AwsWafToken', html, re.I):
        types.append('AWS WAF Captcha')
    if re.search(r'perimeterx|px-captcha|human-security|/_px/', html, re.I):
        types.append('PerimeterX/HUMAN')
    if re.search(r'datadome\.co|dd-captcha|DataDome', html, re.I):
        types.append('DataDome')
    if re.search(r'mtcaptcha|mt-captcha', html, re.I):
        types.append('MTCaptcha')
    if re.search(r'simplecaptcha|simple-captcha', html, re.I):
        types.append('SimpleCaptcha')
    if re.search(r'botdetect|captcha\.ashx', html, re.I):
        types.append('BotDetect')
    if re.search(r'kasada|kpsdk', html, re.I):
        types.append('Kasada')
    if re.search(r'keycaptcha', html, re.I):
        types.append('KeyCAPTCHA')
    if re.search(r'solvemedia|adcopy', html, re.I):
        types.append('SolveMedia')
    if re.search(r'capy\.jp|puzzle-captcha', html, re.I):
        types.append('Capy Puzzle')
    return types if types else ['None']

# ── Detection: security (advanced) ───────────────────────────────────
def detect_security(html, headers):
    systems = []
    h = html.lower()
    hs = str(headers).lower()
    if any(['cloudflare' in hs, 'cf-ray' in headers, 'cf-cache-status' in headers, '__cf_bm' in h, 'cf_clearance' in hs, 'cdn-cgi/' in h]):
        systems.append('Cloudflare' if 'cf-bot-management' not in hs and '__cfbm' not in hs else 'Cloudflare Bot Management')
    if any([re.search(r'perimeterx|_px\d+|px-captcha|pxvid|pxhd', html, re.I), 'perimeterx.net' in h, '/_px/' in h]):
        systems.append('PerimeterX/HUMAN')
    if any(['akamai' in hs, '_abck' in h, 'bm_sz' in h, 'ak_bmsc' in h, re.search(r'akamai\.net|akamaicdn', html, re.I)]):
        systems.append('Akamai Bot Manager' if '_abck' in hs or 'bm_sz' in hs else 'Akamai')
    if any(['incapsula' in hs, 'incap_ses' in h, 'visid_incap' in h, re.search(r'imperva|incapsula', html, re.I)]):
        systems.append('Imperva/Incapsula')
    if re.search(r'aws-waf|x-amzn-waf|awswaf', hs, re.I):
        systems.append('AWS WAF')
    if re.search(r'sucuri|x-sucuri', html, re.I) or 'sucuri' in hs:
        systems.append('Sucuri')
    if re.search(r'wordfence|wfwaf|wordfence-waf', html, re.I):
        systems.append('Wordfence')
    if re.search(r'datadome\.co|datadome', html, re.I) or 'datadome' in hs:
        systems.append('DataDome')
    if re.search(r'shape-security|shapesecurity', html, re.I):
        systems.append('Shape Security')
    if re.search(r'kasada|kpsdk', html, re.I):
        systems.append('Kasada')
    if re.search(r'distil_|distilnetworks', html, re.I):
        systems.append('Distil Networks')
    if re.search(r'signal-?sciences|sigsci', html, re.I):
        systems.append('Signal Sciences')
    if re.search(r'reblaze|rbzid|reblaze\.com', html, re.I):
        systems.append('Reblaze')
    if 'fastly' in hs or 'fastly' in h:
        systems.append('Fastly')
    if re.search(r'radware', html, re.I):
        systems.append('Radware')
    if 'f5' in hs or 'bigip' in h:
        systems.append('F5 BIG-IP')
    if re.search(r'barracuda', html, re.I):
        systems.append('Barracuda')
    if re.search(r'fortinet|fortiweb', html, re.I):
        systems.append('FortiWeb')
    if 'cloudfront' in hs or 'cloudfront.net' in h:
        systems.append('AWS CloudFront')
    return systems if systems else ['None']

# ── Detection: gateways (advanced) ───────────────────────────────────
def detect_gateways(html):
    g = []
    h = html.lower()
    if any(re.search(p, html, re.I) for p in [r'js\.stripe\.com/v3', r'stripe\.com/v3', r'pk_live_[\w]+', r'pk_test_[\w]+', r'stripe-card-element', r'stripeToken', r'stripe\.createToken', r'stripe\.confirmCardPayment', r'wc_stripe_params', r'woocommerce-gateway-stripe']):
        g.append('Stripe')
    if any(re.search(p, html, re.I) for p in [r'paypal\.com|paypalobjects', r'paypal-button', r'paypal/sdk', r'paypal\.Buttons']):
        g.append('PayPal')
    if re.search(r'squareup\.com|square\.com|sq-payment|squarecdn', html, re.I):
        g.append('Square')
    if re.search(r'authorize\.net|authorizenet', html, re.I):
        g.append('Authorize.Net')
    if re.search(r'braintree|braintreegateway\.com|braintreepayments', html, re.I):
        g.append('Braintree')
    if re.search(r'adyen\.com|adyen-checkout|adyen-encrypt', html, re.I):
        g.append('Adyen')
    if re.search(r'razorpay\.com|razorpay-checkout|checkout\.razorpay', html, re.I):
        g.append('Razorpay')
    if re.search(r'mollie\.com|mollie-checkout', html, re.I):
        g.append('Mollie')
    if re.search(r'2checkout|2co\.com|verifone', html, re.I):
        g.append('2Checkout')
    if re.search(r'apple-pay|applepay|ApplePaySession', html, re.I):
        g.append('Apple Pay')
    if re.search(r'google-pay|googlepay|pay\.google', html, re.I):
        g.append('Google Pay')
    if re.search(r'klarna\.com|klarna-checkout', html, re.I):
        g.append('Klarna')
    if re.search(r'afterpay\.com|clearpay', html, re.I):
        g.append('Afterpay')
    if re.search(r'shop-pay|shoppay|shop\.app', html, re.I):
        g.append('Shop Pay')
    if re.search(r'worldpay|fisglobal', html, re.I):
        g.append('Worldpay')
    if re.search(r'checkout\.com|checkout-sdk', html, re.I):
        g.append('Checkout.com')
    if re.search(r'payu\.com', html, re.I):
        g.append('PayU')
    if re.search(r'paddle\.com|paddlejs', html, re.I):
        g.append('Paddle')
    if re.search(r'gumroad', html, re.I):
        g.append('Gumroad')
    if re.search(r'payfast\.co\.za|payfast', html, re.I):
        g.append('PayFast')
    if re.search(r'paystack', html, re.I):
        g.append('Paystack')
    if re.search(r'flutterwave', html, re.I):
        g.append('Flutterwave')
    return g if g else ['None']

# ── Detection: card save / auth ──────────────────────────────────────
def detect_card_save_auth(html, soup):
    detected = set()
    if re.search(r'stripe\.com|stripe\.js|pk_live|pk_test|stripe-card-element', html, re.I):
        if re.search(r'setupIntent|SetupIntent|stripe\.confirmCardSetup|setup_intent', html, re.I):
            detected.add('Stripe SetupIntent (Card Auth)')
        if re.search(r'createPaymentMethod|attachPaymentMethod|payment_method|pm_\w+', html, re.I):
            detected.add('Stripe Payment Method Save')
        if re.search(r'saved.*payment.*method.*stripe|customer\.invoice_settings', html, re.I):
            detected.add('Stripe Customer Vault')
    if re.search(r'braintree|braintreegateway|braintreepayments', html, re.I):
        if re.search(r'vault|vaultManager|storeInVault', html, re.I):
            detected.add('Braintree Vault')
        if re.search(r'paymentMethodNonce|paymentMethodToken', html, re.I):
            detected.add('Braintree Payment Token')
    if re.search(r'authorize\.net|authorizenet', html, re.I):
        if re.search(r'customerProfileId|paymentProfileId|createCustomerProfile', html, re.I):
            detected.add('Authorize.Net CIM (Card Vault)')
    if re.search(r'adyen\.com|adyen-checkout', html, re.I):
        if re.search(r'storePaymentMethod|recurringDetailReference', html, re.I):
            detected.add('Adyen Card Tokenization')
    if any(re.search(p, html, re.I) for p in [r'zero.*dollar.*authorization', r'\$0\.00.*auth', r'card.*verification.*value', r'pre.*auth.*card']):
        detected.add('Zero-Dollar Authorization')
    if re.search(r'recurring.*billing.*setup|subscription.*payment.*method|auto.*billing', html, re.I):
        if re.search(r'stripe|braintree|authorize|adyen|square|paypal', html, re.I):
            detected.add('Recurring Billing Setup')
    for form in soup.find_all('form'):
        f = str(form).lower()
        if re.search(r'save.*this.*card|store.*payment.*method|remember.*card.*details', f, re.I) and re.search(r'card[_-]?number|cvv|cvc', f, re.I):
            detected.add('Form-Based Card Save')
            break
    return sorted(detected) if detected else ['Not Detected']

# ── Detection: technology stack ──────────────────────────────────────
def detect_technology(html, headers):
    t = []
    h = html.lower()
    hs = str(headers).lower()
    if re.search(r'wp-content|wp-includes|/wp-json/|wordpress|wp-emoji', html, re.I):
        t.append('WordPress')
    if re.search(r'woocommerce|wc-|add-to-cart|cart-fragments', html, re.I):
        t.append('WooCommerce')
    if any(['shopify.com' in h, 'cdn.shopify' in h, 'myshopify' in h, 'x-shopify' in hs]):
        t.append('Shopify')
    if re.search(r'magento|mage/cookies|catalogsearch', html, re.I):
        t.append('Magento')
    if re.search(r'react|_react|react-dom|__REACT', html, re.I):
        t.append('React')
    if re.search(r'vue\.js|vuejs|__vue__|data-v-', html, re.I):
        t.append('Vue.js')
    if re.search(r'angular|ng-app|@angular/', html, re.I):
        t.append('Angular')
    if re.search(r'next\.js|__next|_next/static|__NEXT_DATA__', html, re.I):
        t.append('Next.js')
    if re.search(r'nuxt\.js|__nuxt|_nuxt/|__NUXT__', html, re.I):
        t.append('Nuxt.js')
    if re.search(r'django|csrfmiddlewaretoken', html, re.I) or 'django' in hs:
        t.append('Django')
    if re.search(r'laravel|laravel_session|XSRF-TOKEN', html, re.I):
        t.append('Laravel')
    if re.search(r'drupal|/sites/default|/sites/all', html, re.I):
        t.append('Drupal')
    if re.search(r'joomla|/components/com_|/modules/mod_', html, re.I):
        t.append('Joomla')
    if re.search(r'wix\.com|wixstatic|_wix', html, re.I):
        t.append('Wix')
    if re.search(r'squarespace|squarespace-cdn', html, re.I):
        t.append('Squarespace')
    if re.search(r'webflow|webflow\.io', html, re.I):
        t.append('Webflow')
    if re.search(r'prestashop|ps_', html, re.I):
        t.append('PrestaShop')
    if re.search(r'opencart|route=product|catalog/view', html, re.I):
        t.append('OpenCart')
    if re.search(r'bigcommerce|cdn\d+\.bigcommerce', html, re.I):
        t.append('BigCommerce')
    if re.search(r'gatsby|___gatsby', html, re.I):
        t.append('Gatsby')
    if re.search(r'svelte|__svelte|sveltekit', html, re.I):
        t.append('Svelte')
    if 'x-powered-by' in headers and 'express' in hs:
        t.append('Express.js')
    if re.search(r'__viewstate|__eventvalidation|asp\.net', html, re.I) or 'aspnet' in hs:
        t.append('ASP.NET')
    if 'x-powered-by' in headers and 'phusion passenger' in hs:
        t.append('Ruby on Rails')
    if re.search(r'jquery|jQuery\.', html, re.I):
        t.append('jQuery')
    if re.search(r'bootstrap|bootstrap\.min|col-md-', html, re.I):
        t.append('Bootstrap')
    if re.search(r'tailwind|tailwindcss', html, re.I):
        t.append('Tailwind CSS')
    if re.search(r'vercel|\.vercel-analytics|x-vercel', html, re.I) or 'vercel' in hs:
        t.append('Vercel')
    if 'netlify' in hs or 'netlify' in h:
        t.append('Netlify')
    return t if t else ['Undetected']

# ── Detection: CDN / analytics / chat ────────────────────────────────
def detect_cdn(html, headers):
    c = []
    h = html.lower()
    hs = str(headers).lower()
    if 'cloudflare' in hs or 'cf-ray' in headers or '__cfduid' in h:
        c.append('Cloudflare')
    if 'akamai' in hs or re.search(r'akamai\.net|akamaicdn', html, re.I):
        c.append('Akamai')
    if 'cloudfront' in hs or 'cloudfront.net' in h:
        c.append('CloudFront')
    if 'fastly' in hs or 'fastly.net' in h:
        c.append('Fastly')
    if 'cf-pages' in hs or 'workers.dev' in h:
        c.append('Cloudflare Pages')
    if re.search(r'keycdn|kxcdn\.com', html, re.I):
        c.append('KeyCDN')
    if re.search(r'bunnycdn|b-cdn\.net', html, re.I):
        c.append('BunnyCDN')
    if 'vercel' in hs or '.vercel.app' in h:
        c.append('Vercel')
    if 'netlify' in hs or 'netlify.app' in h:
        c.append('Netlify')
    return c if c else ['None']

def detect_analytics(html):
    a = []
    h = html.lower()
    if re.search(r'google-analytics\.com|analytics\.js|gtag\.js|gtag\(|UA-\d+-\d+|G-[A-Z0-9]+', html, re.I):
        a.append('Google Analytics 4' if ('gtag' in h or 'G-' in html) else 'Google Analytics')
    if re.search(r'googletagmanager\.com|GTM-[A-Z0-9]+', html, re.I):
        a.append('Google Tag Manager')
    if re.search(r'facebook\.com/tr|fbq\(|connect\.facebook\.net', html, re.I):
        a.append('Facebook Pixel')
    if re.search(r'hotjar\.com|_hjSettings', html, re.I):
        a.append('Hotjar')
    if re.search(r'mixpanel\.com', html, re.I):
        a.append('Mixpanel')
    if re.search(r'segment\.com', html, re.I):
        a.append('Segment')
    if re.search(r'amplitude\.com', html, re.I):
        a.append('Amplitude')
    if re.search(r'matomo|piwik', html, re.I):
        a.append('Matomo')
    if re.search(r'plausible\.io', html, re.I):
        a.append('Plausible')
    if re.search(r'clarity\.ms|clarity\.js', html, re.I):
        a.append('Microsoft Clarity')
    return a if a else ['None']

def detect_chat_widgets(html):
    w = []
    if re.search(r'intercom\.io|intercomSettings', html, re.I):
        w.append('Intercom')
    if re.search(r'zendesk\.com|zdassets', html, re.I):
        w.append('Zendesk')
    if re.search(r'drift\.com|driftt', html, re.I):
        w.append('Drift')
    if re.search(r'livechatinc\.com|livechat', html, re.I):
        w.append('LiveChat')
    if re.search(r'tawk\.to', html, re.I):
        w.append('Tawk.to')
    if re.search(r'crisp\.chat|crisp\.im', html, re.I):
        w.append('Crisp')
    if re.search(r'hubspot.*chat|hs-chat', html, re.I):
        w.append('HubSpot Chat')
    return w if w else ['None']

# ── Detection: 3DS ───────────────────────────────────────────────────
def detect_3ds(html):
    if re.search(r'3d\s*secure|verified\s*by\s*visa|mastercard\s*securecode|acsurl|three-domain-secure', html, re.I):
        return '3D Secure ✅'
    return '2D (No 3DS) ❌'

# ── DNS info (A records) ─────────────────────────────────────────────
def get_dns_info(url):
    try:
        hostname = urlparse(url).hostname
        if not hostname:
            return 'N/A'
        infos = socket.getaddrinfo(hostname, 443, socket.AF_INET, socket.SOCK_STREAM)
        ips = sorted(set(sock[4][0] for sock in infos))
        return ', '.join(ips[:4]) or 'N/A'
    except Exception:
        return 'N/A'

# ── Core scan ────────────────────────────────────────────────────────
async def scan_site(url):
    status, html, headers, final_url = await fetch_site(url)
    if status is None:
        return {
            "online": False,
            "status_text": "❌ Error" if not html else "⏳ Timeout",
            "error": headers or "Fetch failed",
            "url": url,
        }
    soup = BeautifulSoup(html, 'html.parser')
    all_scripts = ' '.join(str(s.get('src', '')) for s in soup.find_all('script'))
    all_meta = ' '.join(str(m.get('content', '')) + ' ' + str(m.get('name', '')) for m in soup.find_all('meta'))
    all_forms = ' '.join(str(f) for f in soup.find_all('form'))
    all_content = ' '.join([html, all_scripts, all_meta, all_forms, str(headers)])

    return {
        "online": True,
        "status_text": "✅ Online" if status == 200 else f"⚠️ HTTP {status}",
        "url": final_url or url,
        "captcha": ', '.join(detect_captcha(all_content)),
        "security": ', '.join(detect_security(all_content, headers)),
        "gateways": ', '.join(detect_gateways(all_content)),
        "card_save": ', '.join(detect_card_save_auth(all_content, soup)),
        "technology": ', '.join(detect_technology(all_content, headers)),
        "cdn": ', '.join(detect_cdn(all_content, headers)),
        "analytics": ', '.join(detect_analytics(all_content)),
        "chat": ', '.join(detect_chat_widgets(all_content)),
        "threeds": detect_3ds(all_content),
        "ip": get_dns_info(final_url or url),
    }

def fmt_result(r, url_label):
    if not r.get("online"):
        return f"❌ <b>Scan failed</b> — <code>{r.get('error', 'unknown')}</code>"
    lines = [
        f"<b>🌐 {url_label}</b>",
        "━━━━━━━━━━━━━━━━",
        f"<b>𝐒𝐭𝐚𝐭𝐮𝐬</b> ➠ {r['status_text']}",
        f"<b>𝐈𝐏</b> ➠ <code>{r['ip']}</code>",
        f"<b>𝐂𝐌𝐒/𝐓𝐞𝐜𝐡</b> ➠ {r['technology']}",
        f"<b>𝐂𝐃𝐍</b> ➠ {r['cdn']}",
        "━━━━━━━━━━━━━━━━",
        f"<b>𝐆𝐚𝐭𝐞𝐰𝐚𝐲𝐬</b> ➠ {r['gateways']}",
        f"<b>𝟑𝐃𝐒</b> ➠ {r['threeds']}",
        f"<b>𝐂𝐚𝐫𝐝 𝐒𝐚𝐯𝐞/𝐀𝐮𝐭𝐡</b> ➠ {r['card_save']}",
        "━━━━━━━━━━━━━━━━",
        f"<b>𝐂𝐚𝐩𝐭𝐜𝐡𝐚</b> ➠ {r['captcha']}",
        f"<b>𝐒𝐞𝐜𝐮𝐫𝐢𝐭𝐲</b> ➠ {r['security']}",
        f"<b>𝐀𝐧𝐚𝐥𝐲𝐭𝐢𝐜𝐬</b> ➠ {r['analytics']}",
        f"<b>𝐂𝐡𝐚𝐭</b> ➠ {r['chat']}",
    ]
    return "\n".join(lines)

# ── Commands ─────────────────────────────────────────────────────────
async def gate_command(message: types.Message):
    user = message.from_user
    user_id = user.id
    now = time.time()
    if user_id in user_last_command_time and now - user_last_command_time[user_id] < 5:
        await safe_reply(message, f"⚠️ <b>Slow down!</b> wait <code>{round(5 - (now - user_last_command_time[user_id]), 1)}</code>s", parse_mode="HTML")
        return
    user_last_command_time[user_id] = now

    parts = message.text.split(maxsplit=1)
    url = parts[1].strip() if len(parts) > 1 else ""
    if not url and message.reply_to_message:
        rt = message.reply_to_message.text or message.reply_to_message.caption
        m = re.search(r'https?://[^\s]+', rt or "")
        url = m.group(0) if m else ""
    if not url:
        await safe_reply(message, "❌ <b>Usage:</b> /gate <code>https://site.com</code>", parse_mode="HTML", disable_web_page_preview=True)
        return

    credits = await asyncio.to_thread(get_user_credits, user_id)
    if credits is None or credits <= 0:
        await safe_reply(message, "❌ <b>Insufficient Credits!</b>", parse_mode="HTML")
        return

    proc = await safe_reply(message, "🔍 <b>Scanning site…</b>", parse_mode="HTML")
    asyncio.create_task(_finish_gate(message, proc, user, user_id, url))

async def _finish_gate(message, proc, user, user_id, url):
    result = await scan_site(url)
    balance = max(0, await asyncio.to_thread(get_user_credits, user_id) - 1)
    await asyncio.to_thread(update_credits, user_id, balance)
    await update_lookup_stats(user_id)
    dev = '<a href="https://t.me/Enchanted_linux_0x">Enchanted_linux_0x</a>'
    caption = fmt_result(result, url) + f"\n━━━━━━━━━━━━━━━━\n<b>𝐃𝐞𝐯</b> ➠ {dev}"
    try:
        await proc.edit_text(caption, parse_mode="HTML", disable_web_page_preview=True)
    except Exception as e:
        await safe_reply(message, caption, parse_mode="HTML", disable_web_page_preview=True)

async def gmass_command(message: types.Message):
    user = message.from_user
    user_id = user.id
    parts = message.text.split(maxsplit=1)
    urls = []
    if len(parts) > 1:
        urls = [u.strip() for u in re.split(r'[,\n]', parts[1]) if u.strip()]
    if not urls and message.reply_to_message:
        rt = message.reply_to_message.text or message.reply_to_message.caption
        urls = [u for u in re.findall(r'https?://[^\s]+', rt or "")] if rt else []
    if not urls:
        await safe_reply(message, "❌ <b>Usage:</b> /gmass <code>site1.com, site2.com, site3.com</code>", parse_mode="HTML")
        return
    urls = urls[:10]
    credits = await asyncio.to_thread(get_user_credits, user_id)
    if credits is None or credits < len(urls):
        await safe_reply(message, f"❌ <b>Insufficient Credits!</b> need {len(urls)}", parse_mode="HTML")
        return
    proc = await safe_reply(message, f"🔍 <b>Scanning {len(urls)} sites…</b>", parse_mode="HTML")
    asyncio.create_task(_finish_gmass(message, proc, user, user_id, urls))

async def _finish_gmass(message, proc, user, user_id, urls):
    results = []
    for u in urls:
        results.append((u, await scan_site(u)))
    await asyncio.to_thread(update_credits, user_id, max(0, await asyncio.to_thread(get_user_credits, user_id) - len(urls)))
    await update_lookup_stats(user_id)
    out = []
    for u, r in results:
        out.append(fmt_result(r, u))
        out.append("")
    dev = '<a href="https://t.me/Enchanted_linux_0x">Enchanted_linux_0x</a>'
    text = "\n".join(out).strip() + f"\n━━━━━━━━━━━━━━━━\n<b>𝐃𝐞𝐯</b> ➠ {dev}"
    try:
        await proc.edit_text(text[:4000], parse_mode="HTML", disable_web_page_preview=True)
    except Exception:
        await safe_reply(message, text[:4000], parse_mode="HTML", disable_web_page_preview=True)

async def gatehelp_command(message: types.Message):
    help_text = (
        "🔍 <b>Site Analyzer Help</b>\n"
        "━━━━━━━━━━━━━━━━\n"
        "<b>Commands:</b>\n"
        "<code>/gate &lt;url&gt;</code> — full site scan\n"
        "<code>/gmass url1, url2, ...</code> — mass scan (max 10)\n\n"
        "<b>Detects:</b>\n"
        "• CMS / tech stack (Shopify, WordPress, React, Next.js…)\n"
        "• Payment gateways (Stripe, PayPal, Braintree, Adyen…)\n"
        "• 3D Secure\n"
        "• Card save / auth (SetupIntent, vaults, zero-dollar…)\n"
        "• CAPTCHA (reCAPTCHA v2/v3, hCaptcha, Turnstile, Arkose…)\n"
        "• WAF/Bot protection (Cloudflare, Akamai, PerimeterX…)\n"
        "• CDN, analytics, chat widgets\n"
        "• DNS / IP\n\n"
        "<b>Cost:</b> 1 credit per site\n"
        "<b>Cooldown:</b> 5 seconds"
    )
    await safe_reply(message, help_text, parse_mode="HTML", disable_web_page_preview=True)
