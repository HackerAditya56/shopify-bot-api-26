# gate.py - Site Lookup/Gate Scanner Module
# Simple command without router - just /gate command

import re
import asyncio
import logging
import time
import aiohttp
from bs4 import BeautifulSoup
from urllib.parse import urlparse

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# AIogram Imports
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
from aiogram import types, F
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# LOCAL IMPORTS
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
from database import get_user_credits, update_credits, PooledConn
from sub import get_premium_status

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# CONFIGURATION
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

# Rate limiting dictionary
user_last_command_time = {}

# Shared aiohttp session
_session: aiohttp.ClientSession = None
_session_lock = asyncio.Lock()

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# CMS PATTERNS
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

CMS_PATTERNS = {
    'Shopify': r'cdn\.shopify\.com|shopify\.js|shopify\.com/cdn',
    'BigCommerce': r'cdn\.bigcommerce\.com|bigcommerce\.com',
    'Wix': r'static\.parastorage\.com|wix\.com',
    'Squarespace': r'static1\.squarespace\.com|squarespace-cdn\.com',
    'WooCommerce': r'wp-content/plugins/woocommerce/|woocommerce',
    'Magento': r'static/version\d+/frontend/|magento/|Magento',
    'PrestaShop': r'prestashop\.js|prestashop/',
    'OpenCart': r'catalog/view/theme|opencart/',
    'WordPress': r'wp-content|wp-includes/',
    'Joomla': r'media/jui|joomla\.js|media/system/js',
    'Drupal': r'sites/all/modules|drupal\.js/|drupal',
    'TYPO3': r'typo3temp|typo3/',
}

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# PAYMENT GATEWAYS LIST
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

PAYMENT_GATEWAYS = [
    "PayPal", "Stripe", "Braintree", "Square", "Cybersource",
    "Authorize.Net", "2Checkout", "Worldpay", "SagePay",
    "Checkout.com", "Bolt", "Eway", "PayFlow", "Payeezy",
    "Paddle", "Mollie", "Viva Wallet", "Recurly",
    "Shopify", "WooCommerce", "BigCommerce", "Magento",
    "OpenCart", "PrestaShop", "3DCart", "Ecwid",
    "Razorpay", "PayU", "CCAvenue", "Paytm", "UPI",
    "Apple Pay", "Google Pay", "Klarna", "Affirm", "Afterpay",
    "BitPay", "Coinbase Commerce", "Binance Pay",
]

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# SESSION MANAGEMENT
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

async def get_session():
    """Get or create shared aiohttp session."""
    global _session
    async with _session_lock:
        if _session is None or _session.closed:
            connector = aiohttp.TCPConnector(limit=50, limit_per_host=10, ttl_dns_cache=300)
            timeout = aiohttp.ClientTimeout(total=20, connect=10)
            _session = aiohttp.ClientSession(connector=connector, timeout=timeout)
            logging.info("[GATE] HTTP Session created")
    return _session

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# DATABASE HELPERS
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def ensure_gate_stats_columns():
    """Ensures lookup stats columns exist in users table."""
    try:
        with PooledConn() as conn:
            cursor = conn.cursor()
            try:
                cursor.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS site_lookups INTEGER DEFAULT 0")
            except Exception:
                pass
            conn.commit()
        logging.info("[GATE] Lookup stats columns checked.")
    except Exception as e:
        logging.error(f"[GATE] Error checking stats columns: {e}")

# Run on import
ensure_gate_stats_columns()

async def update_lookup_stats(user_id: int):
    """Increment site_lookups counter for user."""
    def _sync_update():
        try:
            with PooledConn() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    "UPDATE users SET site_lookups = site_lookups + 1 WHERE user_id = %s",
                    (user_id,)
                )
                conn.commit()
        except Exception as e:
            logging.error(f"[GATE] Error updating lookup stats: {e}")
    
    await asyncio.to_thread(_sync_update)

async def get_user_plan_name(user_id: int) -> str:
    """Fetches the specific plan name from receipts if premium, else Trial."""
    premium_result = await asyncio.to_thread(get_premium_status, user_id)
    is_premium = premium_result[0] if isinstance(premium_result, tuple) else False
    
    if is_premium:
        try:
            def _sync_fetch():
                with PooledConn() as conn:
                    cursor = conn.cursor()
                    cursor.execute(
                        "SELECT plan FROM receipts WHERE user_id = %s ORDER BY purchased_on DESC LIMIT 1",
                        (user_id,)
                    )
                    row = cursor.fetchone()
                    return row[0].upper() if row else "PREMIUM"
            
            return await asyncio.to_thread(_sync_fetch)
        except Exception as e:
            logging.error(f"[GATE] Error fetching plan name: {e}")
        return "PREMIUM"
    else:
        return "FREE"

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# SITE FETCHING
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

async def fetch_site(url: str):
    """Fetch website content with proper headers."""
    session = await get_session()
    
    if not url.startswith(("http://", "https://")):
        url = "https://" + url
    
    domain = urlparse(url).netloc
    
    headers = {
        "authority": domain,
        "scheme": "https",
        "accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
        "accept-language": "en-US,en;q=0.9",
        "cache-control": "max-age=0",
        "sec-ch-ua": '"Chromium";v="140", "Not=A?Brand";v="24", "Google Chrome";v="140"',
        "sec-ch-ua-mobile": "?1",
        "sec-ch-ua-platform": '"Android"',
        "sec-fetch-dest": "document",
        "sec-fetch-mode": "navigate",
        "sec-fetch-site": "none",
        "sec-fetch-user": "?1",
        "upgrade-insecure-requests": "1",
        "user-agent": "Mozilla/5.0 (Linux; Android 6.0; Nexus 5 Build/MRA58N) "
                      "AppleWebKit/537.36 (KHTML, like Gecko) "
                      "Chrome/140.0.0.0 Mobile Safari/537.36",
    }
    
    try:
        async with session.get(url, headers=headers, timeout=15) as resp:
            html = await resp.text()
            return resp.status, html, dict(resp.headers)
    except asyncio.TimeoutError:
        logging.warning(f"[GATE] Timeout fetching {url}")
        return None, None, None
    except Exception as e:
        logging.error(f"[GATE] Error fetching {url}: {e}")
        return None, None, None

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# DETECTION FUNCTIONS
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def detect_cms(html: str) -> str:
    for cms, pattern in CMS_PATTERNS.items():
        if re.search(pattern, html, re.IGNORECASE):
            return cms
    return "Unknown / Custom"

def detect_gateways(html: str) -> str:
    detected = []
    html_lower = html.lower()
    
    for gateway in PAYMENT_GATEWAYS:
        pattern = r'\b' + re.escape(gateway.lower()) + r'\b'
        if re.search(pattern, html_lower):
            detected.append(gateway)
    
    if 'stripe' in html_lower and 'pk_' in html_lower:
        if 'Stripe' not in detected:
            detected.append('Stripe (JS)')
    if 'braintree' in html_lower and 'client_token' in html_lower:
        if 'Braintree' not in detected:
            detected.append('Braintree (JS)')
    
    return ", ".join(detected[:5]) if detected else "None Detected"

def detect_security(html: str) -> str:
    patterns_3ds = [
        r'3d\s*secure', r'verified\s*by\s*visa', r'mastercard\s*securecode',
        r'american\s*express\s*safekey', r'3ds', r'3ds2', r'acsurl',
        r'pareq', r'three-domain-secure', r'secure_redirect', r'x-3ds',
    ]
    
    for pattern in patterns_3ds:
        if re.search(pattern, html, re.IGNORECASE):
            return "3D Secure Enabled ✅"
    return "2D (No 3D Secure) ❌"

def detect_captcha(html: str) -> str:
    html_lower = html.lower()
    
    if "hcaptcha" in html_lower:
        return "hCaptcha ✅"
    elif "recaptcha" in html_lower or "g-recaptcha" in html_lower:
        return "reCAPTCHA ✅"
    elif "captcha" in html_lower:
        return "Generic CAPTCHA ✅"
    elif "cloudflare" in html_lower and "challenge" in html_lower:
        return "Cloudflare Challenge ✅"
    return "No CAPTCHA ❌"

def detect_cloudflare(html: str, headers=None, status=None) -> str:
    if headers is None:
        headers = {}
    
    lower_keys = [k.lower() for k in headers.keys()]
    server = headers.get('Server', '').lower()
    
    if 'cf-ray' in lower_keys or 'cloudflare' in server or 'cf-cache-status' in lower_keys:
        soup = BeautifulSoup(html, 'html.parser')
        title = soup.title.string.strip().lower() if soup.title else ''
        
        challenge_indicators = [
            "just a moment", "attention required", "checking your browser",
            "enable javascript", "ddos protection",
        ]
        
        if any(indicator in title for indicator in challenge_indicators):
            return "Active (Challenge) 🛡️"
        return "Cloudflare detect 🔍"
    return "None ❌"

def detect_graphql(html: str) -> str:
    if re.search(r'/graphql|graphqlendpoint|apollo-client|query\s*\{|mutation\s*\{', html, re.IGNORECASE):
        return "GraphQL Detected ✅"
    return "No GraphQL ❌"

def detect_site_status(status: int) -> str:
    if status is None:
        return "⏳ Timeout"
    elif status == 200:
        return "✅ Online"
    elif 300 <= status < 400:
        return "🔄 Redirect"
    elif 400 <= status < 500:
        return f"⚠️ Client Error ({status})"
    elif 500 <= status < 600:
        return f"❌ Server Error ({status})"
    else:
        return f"ℹ️ Status: {status}"

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# SCAN FUNCTION
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

async def scan_site(url: str) -> dict:
    status, html, headers = await fetch_site(url)
    
    if not html:
        return {
            "status": status,
            "status_text": detect_site_status(status),
            "online": False,
            "cms": "N/A",
            "gateways": "N/A",
            "security": "N/A",
            "captcha": "N/A",
            "cloudflare": "N/A",
            "graphql": "N/A",
        }
    
    return {
        "status": status,
        "status_text": detect_site_status(status),
        "online": True,
        "cms": detect_cms(html),
        "gateways": detect_gateways(html),
        "security": detect_security(html),
        "captcha": detect_captcha(html),
        "cloudflare": detect_cloudflare(html, headers, status),
        "graphql": detect_graphql(html),
    }

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# COMMAND HANDLER
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

async def gate_command(message: types.Message):
    """
    /gate <url> - Website lookup/scanner command
    """
    
    user = message.from_user
    user_id = user.id
    current_time = time.time()
    
    # Rate limiting (5 seconds for all users)
    if user_id in user_last_command_time:
        elapsed = current_time - user_last_command_time[user_id]
        if elapsed < 5:
            remaining_time = round(5 - elapsed, 1)
            await message.reply(
                f"⚠️ <b>Slow Down!</b>\n"
                f"Please wait <code>{remaining_time}</code> seconds before continuing.",
                parse_mode="HTML"
            )
            return
    
    user_last_command_time[user_id] = current_time
    
    # Extract URL from command
    parts = message.text.split(maxsplit=1)
    if len(parts) < 2:
        await message.reply(
            "❌ <b>Usage:</b> /gate <code>https://example.com</code>\n\n"
            "<b>Example:</b> /gate https://shopify.com",
            parse_mode="HTML",
            disable_web_page_preview=True
        )
        return
    
    url = parts[1].strip()
    
    # Check if replying to a message with URL
    if not url and message.reply_to_message:
        reply_text = message.reply_to_message.text or message.reply_to_message.caption
        if reply_text:
            url_match = re.search(r'https?://[^\s]+', reply_text)
            if url_match:
                url = url_match.group(0)
    
    if not url:
        await message.reply(
            "❌ <b>No URL provided.</b>\n"
            "Usage: /gate <code>https://example.com</code>",
            parse_mode="HTML"
        )
        return
    
    # Check Credits
    current_credits = await asyncio.to_thread(get_user_credits, user_id)
    if current_credits is None or current_credits <= 0:
        await message.reply(
            "❌ <b>Insufficient Credits!</b>\n\n"
            "You have 0 credits left.\n"
            "Use /buy to purchase more credits.",
            parse_mode="HTML"
        )
        return
    
    # Fetch Plan Name
    plan_name = await get_user_plan_name(user_id)
    
    # Send Processing Message
    processing_text = "<pre>🔍 Scanning Site…⏳</pre>"
    proc_msg = await message.reply(processing_text, parse_mode="HTML")
    
    # Execute Background Scan
    asyncio.create_task(process_gate_scan(message, proc_msg, user, user_id, url, plan_name))

async def process_gate_scan(message, proc_msg, user, user_id, url, plan_name):
    """Process site scan, deduct credits, update stats, and send results."""
    
    # Perform Site Scan
    try:
        result = await scan_site(url)
        logging.info(f"[GATE] Scan completed for {url}: {result.get('status')}")
    except Exception as e:
        logging.error(f"[GATE] Scan error: {e}")
        result = {
            "online": False,
            "status_text": "❌ Error",
            "cms": "N/A",
            "gateways": "N/A",
            "security": "N/A",
            "captcha": "N/A",
            "cloudflare": "N/A",
            "graphql": "N/A",
        }
    
    # Credit Deduction (1 credit per scan)
    current_balance = await asyncio.to_thread(get_user_credits, user_id)
    new_balance = max(0, current_balance - 1)
    await asyncio.to_thread(update_credits, user_id, new_balance)
    
    # Update Stats
    await update_lookup_stats(user_id)
    
    # Build Final Caption
    user_link = f'<a href="tg://user?id={user.id}">{user.first_name}</a>'
    dev_link = '<a href="https://t.me/Enchanted_linux_0x">Enchanted_linux_0x</a>'
    user_display = f"{user_link} <b>[{plan_name}]</b>"
    
    #if result.get("online"):
        #status_display = f"✅ <b>{result.get('status_text', 'Online')}</b>"
    #else:
        #status_display = f"❌ <b>{result.get('status_text', 'Offline')}</b>"
    
    display_url = url if len(url) <= 50 else url[:47] + "..."
    
    final_caption = (
        f"<pre><b>𝐒𝐢𝐭𝐞 𝐋𝐨𝐨𝐤𝐮𝐩 𝐫𝐞𝐬𝐮𝐥𝐭𝐬</b></pre>\n"
        f"━━━━━━━━━━━━━━━━\n"
        f"<b>𝐒𝐢𝐭𝐞</b> ➠ <code>{display_url}</code>\n"
        f"━━━━━━━━━━━━━━━━\n"
        f"<b>𝐂𝐌𝐒</b> ➠ <b>{result.get('cms', 'N/A')}</b>\n"
        f"<b>𝐆𝐚𝐭𝐞𝐰𝐚𝐲𝐬</b> ➠ <b>{result.get('gateways', 'N/A')}</b>\n"
        f"━━━━━━━━━━━━━━━━\n"
        f"<b>𝐒𝐞𝐜𝐮𝐫𝐢𝐭𝐲</b> ➠ <b>{result.get('security', 'N/A')}</b>\n"
        f"<b>𝐂𝐚𝐩𝐭𝐜𝐡𝐚</b> ➠ <b>{result.get('captcha', 'N/A')}</b>\n"
        f"<b>𝐂𝐥𝐨𝐮𝐝𝐟𝐥𝐚𝐫𝐞</b> ➠ <b>{result.get('cloudflare', 'N/A')}</b>\n"
        f"<b>𝐆𝐫𝐚𝐩𝐡𝐐𝐋</b> ➠ <b>{result.get('graphql', 'N/A')}</b>\n"
        f"━━━━━━━━━━━━━━━━\n"
        f"<b>𝐔𝐬𝐞𝐫</b> ➠ <b>{user_display}</b>\n"
        f"<b>𝐃𝐞𝐯</b> ➠ <b>{dev_link}</b>"
    )
    
    # Edit the Processing Message with Result
    try:
        await proc_msg.edit_text(
            text=final_caption,
            parse_mode="HTML",
            disable_web_page_preview=True
        )
    except Exception as e:
        logging.error(f"[GATE] Error editing message: {e}")
        await message.reply(
            text=final_caption,
            parse_mode="HTML",
            disable_web_page_preview=True
        )

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# HELPER COMMAND: /gatehelp
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

async def gatehelp_command(message: types.Message):
    """Show help for Gate command."""
    help_text = (
        "🔍 <b>Site Lookup Command Help</b>\n"
        "━━━━━━━━━━━━━━━━\n"
        "<b>Command:</b> /gate\n"
        "<b>Usage:</b> /gate &lt;url&gt;\n\n"
        "<b>Example:</b>\n"
        "<code>/gate https://shopify.com</code>\n\n"
        "<b>What it does:</b>\n"
        "🔹 Detects CMS (Shopify, WordPress, etc.)\n"
        "🔹 Identifies Payment Gateways\n"
        "🔹 Checks for 3D Secure\n"
        "🔹 Detects CAPTCHA protection\n"
        "🔹 Identifies Cloudflare\n"
        "🔹 Checks for GraphQL endpoints\n\n"
        "<b>Cost:</b> 1 credit per scan\n"
        "<b>Cooldown:</b> 5 seconds"
    )
    await message.reply(help_text, parse_mode="HTML", disable_web_page_preview=True)