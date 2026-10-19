import asyncio
import re
import logging
import time
import psycopg2.extras
import random
import aiohttp
from html import escape

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# AIogram Imports
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
from aiogram import types, F, Router
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.exceptions import TelegramForbiddenError, TelegramBadRequest

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# LOCAL IMPORTS
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
from database import is_gate_enabled, get_user_credits, update_credits, get_db_connection, has_rz_access
from bin import get_bin_info
from sub import get_premium_status
import urllib.request, urllib.parse, urllib.error, json, os, itertools

# ── Razorpay API (VPS:9000) ─────────────────────────────────────────────
RZ_API = os.environ.get("RZ_API", "http://127.0.0.1:9000")
import rz_rotation
RZ_SITES_FILE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "rz_site.txt")
_site_ctr = itertools.count()




def _rz_api_check(cc, proxy, site, amount_paise):
    """Single-card check against the Razorpay API. Returns {status, response}."""
    q = urllib.parse.urlencode({"cc": cc, "site": site, "proxy": proxy, "amount": amount_paise, "region": "IN"})
    url = f"{RZ_API}/razorpay?{q}"
    try:
        resp = urllib.request.urlopen(url, timeout=180)
        data = json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        # server returned 4xx/5xx — surface the real error body
        try:
            data = json.loads(e.read().decode())
        except Exception:
            data = {}
        return {"status": str(data.get("status") or "error").lower(),
                "response": data.get("message") or f"HTTP {e.code}",
                "amount_paise": amount_paise, "amount_inr": amount_paise // 100}
    except urllib.error.URLError as e:
        return {"status": "error", "response": f"Connection error: {str(e.reason)[:60]}",
                "amount_paise": amount_paise, "amount_inr": amount_paise // 100}
    except Exception as e:
        return {"status": "error", "response": f"API: {str(e)[:80]}",
                "amount_paise": amount_paise, "amount_inr": amount_paise // 100}
    status = str(data.get("status") or "error").lower()
    if status == "dead":
        status = "declined"
    msg = data.get("message") or data.get("reason") or "N/A"
    actual_paise = int(data.get("amount_paise") or amount_paise)
    return {"status": status, "response": msg,
            "amount_paise": actual_paise, "amount_inr": actual_paise // 100}
from mass_gates._tg_helpers import safe_reply

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# GIF REACTIONS
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

REACTIONS = [
    "airkiss", "blush", "brofist", "celebrate", "cheers", "clap",
    "cool", "cuddle", "dance", "handhold", "happy", "hug",
    "kiss", "laugh", "lick", "love", "nervous", "nom",
    "nuzzle", "nyah", "pat", "peek", "shy", "sip",
    "sleep", "smile", "smug", "sorry", "thumbsup",
    "tickle", "tired", "wave", "wink", "yay", "yes"
]

async def get_anime_gif():
    """Fetches a random anime reaction GIF from otakugifs API."""
    reaction = random.choice(REACTIONS)
    api_url = f"https://api.otakugifs.xyz/gif?reaction={reaction}"
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(api_url, timeout=10) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    return data.get("url")
    except Exception as e:
        logging.error(f"Error fetching anime gif: {e}")
    return "https://media.giphy.com/media/v1.Y2lkPTc5MGI3NjExM3Z6eXF6eXF6eXF6eXF6eXF6eXF6eXF6SZlcD12MV9pbnRlcm5hbF9naWZfYnlfaWQmY3Q9Zw/LdOyjZ7h5xS3yCjQ8I/giphy.gif"

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# CONFIGURATION & EMOJI IDs
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

# Custom Emoji IDs
CUSTOM_CHARGED_EMOJI_ID = "5359719332542718652"
CUSTOM_APPROVED_EMOJI_ID = "6044254523009012231"
CUSTOM_DECLINED_EMOJI_ID = "5893081007153746175"

# In-memory dictionary for rate limiting
user_last_command_time = {}

# Router for this module
router = Router()

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# DATABASE INITIALIZATION (Ensure columns exist)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def ensure_stats_columns():
    """Ensures cc_checked and cc_charged columns exist in the users table."""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        try:
            cursor.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS cc_checked INTEGER DEFAULT 0")
        except Exception:
            pass 
        try:
            cursor.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS cc_charged INTEGER DEFAULT 0")
        except Exception:
            pass
        conn.commit()
        conn.close()
        print("[DB] RZ Stats columns checked/created.")
    except Exception as e:
        print(f"[DB] Error checking stats columns: {e}")

# Run this once when script loads
ensure_stats_columns()

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# HELPERS
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

async def update_user_stats(user_id, is_charged):
    """
    Synchronous helper to increment stats.
    Wrapped in asyncio.to_thread when called.
    """
    def _sync_update():
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Always increment total checked
        cursor.execute("UPDATE users SET cc_checked = cc_checked + 1 WHERE user_id = %s", (user_id,))
        
        # If it was a hit (charged/approved), increment charged count
        if is_charged:
            cursor.execute("UPDATE users SET cc_charged = cc_charged + 1 WHERE user_id = %s", (user_id,))
            
        conn.commit()
        conn.close()

    await asyncio.to_thread(_sync_update)

async def get_user_plan_name(user_id):
    """Fetches specific plan name from receipts if premium, else Trial."""
    is_premium, _ = await asyncio.to_thread(get_premium_status, user_id)
    
    if is_premium:
        try:
            def _sync_fetch():
                conn = get_db_connection()
                cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
                # Get the latest plan purchased
                cursor.execute("SELECT plan FROM receipts WHERE user_id = %s ORDER BY purchased_on DESC LIMIT 1", (user_id,))
                row = cursor.fetchone()
                conn.close()
                return row['plan'].upper() if row else "PREMIUM"
            return await asyncio.to_thread(_sync_fetch)
        except Exception as e:
            logging.error(f"Error fetching plan name: {e}")
        return "PREMIUM"
    else:
        return "FREE"

def luhn_check(card_number: str) -> bool:
    """
    Validates a credit card number using Luhn Algorithm.
    Returns True if valid, False otherwise.
    """
    card_number = str(card_number).strip()
    if not card_number.isdigit():
        return False
    
    total = 0
    reverse_digits = card_number[::-1]
    
    for i, char in enumerate(reverse_digits):
        digit = int(char)
        
        if i % 2 == 1:
            digit *= 2
            if digit > 9:
                digit -= 9
        total += digit
        
    return total % 10 == 0

def is_india_card(bin_info: dict) -> bool:
    """
    Checks if the card is from India based on BIN info.
    Checks both country name and country code.
    """
    country_name = bin_info.get("country", "").lower()
    country_code = bin_info.get("country_code", "").upper()
    
    # Check country name contains "india"
    if "india" in country_name:
        return True
    
    # Check country code is "IN" (India's ISO code)
    if country_code == "IN":
        return True
    
    return False

def build_user_link(user_obj) -> str:
    """Builds a clickable user mention link."""
    name = user_obj.first_name or "User"
    if user_obj.username:
        return f'<a href="https://t.me/{user_obj.username}">{name}</a>'
    return f'<a href="tg://user?id={user_obj.id}">{name}</a>'

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# COMMAND HANDLER
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

@router.message(F.text.startswith("/rz"))
async def rz_command(message: types.Message):
    # 1. GATE CHECK
    if not await asyncio.to_thread(is_gate_enabled, "rz"):
        await safe_reply(message, 
            "🚧 <b>𝗥𝗮𝘇𝗼𝗿𝗽𝗮𝘆 𝟭₹ 𝗚𝗮𝘁𝗲 𝗶𝘀 𝘂𝗻𝗱𝗲𝗿 𝗺𝗮𝗶𝗻𝘁𝗲𝗻𝗮𝗻𝗰𝗲.</b>\n"
            "𝗜𝘁 𝘄𝗶𝗹𝗹 𝗯𝗲 𝗯𝗮𝗰𝗸 𝘀𝗵𝗼𝗿𝘁𝗹𝘆 𝘄𝗶𝘁𝗵 𝗲𝘅𝗰𝗶𝘁𝗶𝗻𝗴 𝗶𝗺𝗽𝗿𝗼𝘃𝗲𝗺𝗲𝗻𝘁𝘀.⚙️",
            parse_mode="HTML"
        )
        return

    user = message.from_user
    user_id = user.id
    current_time = time.time()

    # 2. RAZORPAY ACCESS CHECK (dev-only grant; premium/owner do NOT auto-qualify)
    if not await asyncio.to_thread(has_rz_access, user_id):
        await safe_reply(message,
            "🔒 <b>𝗥𝗮𝘇𝗼𝗿𝗽𝗮𝘆 𝗔𝗰𝗰𝗲𝘀𝘀 𝗥𝗲𝗾𝘂𝗶𝗿𝗲𝗱</b>\n\n"
            "𝗬𝗼𝘂 𝗱𝗼𝗻'𝘁 𝗵𝗮𝘃𝗲 𝗮𝗰𝗰𝗲𝘀𝘀 𝘁𝗼 𝘁𝗵𝗲 𝗥𝗮𝘇𝗼𝗿𝗽𝗮𝘆 𝗴𝗮𝘁𝗲.\n"
            "𝗢𝗻𝗹𝘆 𝘁𝗵𝗲 𝗱𝗲𝘃 𝗰𝗮𝗻 𝗴𝗿𝗮𝗻𝘁 𝗶𝘁.",
            parse_mode="HTML"
        )
        return
    
    # 4. Extract Card Details
    parts = message.text.split(maxsplit=1)
    raw_text = ""
    
    if len(parts) > 1:
        raw_text = parts[1].strip()

    if message.reply_to_message:
        raw_text += " " + (message.reply_to_message.text or message.reply_to_message.caption or "")
        
    if not raw_text.strip():
        await safe_reply(message, 
            "❌ <b>Usage:</b> /rz <code>cc|mm|yy|cvv</code>\n"
            "Or reply to a message containing card details.",
            parse_mode="HTML"
        )
        return

    # Regex to find CC (Supports 15-16 digits for AMEX/Visa/MC)
    pattern = r'\b(\d{15,16})[|\s/?\\:]+(\d{2,4})[|\s/?\\:]+(\d{2,4})[|\s/?\\:]+(\d{3,4})\b'
    match = re.search(pattern, raw_text)

    if not match:
        await safe_reply(message, 
            "❌ <b>Invalid Card Format.</b>\n"
            "Please provide CC as <code>4242424242424242|05|27|123</code>",
            parse_mode="HTML"
        )
        return

    cc, mm, yy_raw, cvv = match.groups()

    # Normalize Year
    if len(yy_raw) == 4:
        yy = yy_raw[2:]
    else:
        yy = yy_raw

    formatted_cc = f"{cc}|{mm}|{yy}|{cvv}"

    # Amount: amount=X (rupees) or random ₹50–₹100
    amt_match = re.search(r'amount\s*=\s*(\d+)', raw_text, re.I)

    # Site: site=URL or random from rz_site.txt
    site_match = re.search(r'site\s*=\s*(https?://\S+)', raw_text, re.I)
    if site_match:
        site = site_match.group(1)
    else:
        site = rz_rotation.next_site() or ""

    # Amount: amount=X override, else site fixed price, else ₹23-100
    if amt_match:
        amount_paise = min(int(amt_match.group(1)), 100) * 100  # cap ₹100
    else:
        amount_paise = rz_rotation.get_site_price(site) or random.randint(23, 100) * 100

    # 5. LUHN CHECK
    if not luhn_check(cc):
        await safe_reply(message, 
            "❌ <b>Invalid Card</b>\n"
            "Your card number is incorrect.",
            parse_mode="HTML"
        )
        return

    # 6. Check Credits (APPLIED TO EVERYONE)
    current_credits = await asyncio.to_thread(get_user_credits, user_id)
    if current_credits is None or current_credits <= 0:
        await safe_reply(message, 
            "❌ <b>Insufficient Credits!</b>\n\n"
            "You have 0 credits left.",
            parse_mode="HTML"
        )
        return

    # 7. Fetch Plan Name
    plan_name = await get_user_plan_name(user_id)

    # 8. Send Processing Message (as reply)
    escaped_card = escape(formatted_cc)
    proc_msg = await safe_reply(message,
        f"<pre>𝗖𝗵𝗲𝗰𝗸𝗶𝗻𝗴 𝗦𝗶𝗻𝗴𝗹𝗲 𝗖𝗮𝗿𝗱...</pre>\n"
        f"<b>𝗖𝗮𝗿𝗱 ➠</b> <code>{escaped_card}</code>",
        parse_mode="HTML"
    )

    # 9. Execute Background Task
    asyncio.create_task(
        process_rz_check(
            message, proc_msg, user, user_id, formatted_cc, cc, plan_name, site, amount_paise
        )
    )

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# BACKGROUND PROCESSOR
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

async def process_rz_check(message, proc_msg, user, user_id, formatted_cc, cc, plan_name, site="", amount_paise=100):
    """
    Handles gate check, DB updates, and final message editing.
    Optimized for faster response times.
    """
    
    start_time = time.time()
    
    # Initialize variables
    api_result = {"status": "error", "response": "Unknown Error"}
    bin_info = {}
    status_raw = "error"
    res_message = "Unknown Error"
    is_charged = False
    
    # First, get BIN info to check if it's India
    async def run_bin_lookup():
        nonlocal bin_info
        try:
            bin_info = await get_bin_info(cc[:6])
        except Exception:
            bin_info = {}
    
    await run_bin_lookup()
    
    # Prepare BIN data
    bin_scheme = bin_info.get("scheme", "N/A")
    bin_bank = bin_info.get("bank", "N/A")
    
    # Prepare Country with Flag
    country_name = bin_info.get("country", "N/A")
    country_flag = bin_info.get("country_emoji", "")
    bin_country = f"{country_flag} {country_name}" if country_flag else country_name
    
    # ═══════════════════════════════════════════════════════
    # INDIA CARD CHECK - Skip gate, direct region block
    # ═══════════════════════════════════════════════════════
    if is_india_card(bin_info):
        status_raw = "declined"
        res_message = "[RISK_CONTROL] / REGION_BLOCKED"
        api_result = {"status": "declined", "response": res_message}
        logging.info(f"India card blocked: {cc[:6]} for user {user_id}")
    else:
        # ═══════════════════════════════════════════════════════
        # NON-INDIA CARD - Proceed with actual gate check
        # ═══════════════════════════════════════════════════════
        # Site-level failures ("Site Change", server error, etc.) cool the site
        # and the SAME card is re-checked on the next site — never shown raw.
        _site_error_kw = (
            "site change", "server error", "site issue", "something went wrong",
            "should not be sent", "extra field", "order failed", "merchant blocked",
            "merchant not activated", "payment page inactive", "site unavailable",
            "no stock", "out of stock", "amount too small", "min purchase",
            "gay site", "mandatory item", "invalid email", "currency is invalid",
        )
        cur_site = site
        api_result = {"status": "error", "response": "Unknown Error"}
        for _attempt in range(12):
            if not cur_site:
                cur_site = rz_rotation.next_site() or ""
            _proxy, _plock = rz_rotation.acquire_proxy()
            if not _proxy:
                api_result = {"status": "error", "response": "No proxies in rz_pxy.txt."}
                break
            try:
                api_result = await asyncio.to_thread(_rz_api_check, formatted_cc, _proxy, cur_site, amount_paise)
            finally:
                rz_rotation.release_proxy(_proxy, _plock)
                rz_rotation.record_proxy_use(_proxy)
            _resp_low = str(api_result.get("response", "")).lower()
            if cur_site:
                rz_rotation.record_site_result(cur_site, _resp_low)
            if "403" in _resp_low or "forbidden" in _resp_low or "waf" in _resp_low:
                rz_rotation.pause_proxy_403(_proxy)
            if any(k in _resp_low for k in _site_error_kw):
                cur_site = rz_rotation.next_site()
                if not cur_site:
                    await asyncio.sleep(60)
                    cur_site = rz_rotation.next_site() or ""
                continue
            break
        status_raw = api_result.get("status", "").lower()
        res_message = api_result.get("response", "N/A")
    actual_inr = int(api_result.get("amount_inr") or (amount_paise // 100))
    amount_warn = f"\n⚠️ <b>𝗔𝗺𝗼𝘂𝗻𝘁 𝘁𝗼𝗼 𝗵𝗶𝗴𝗵 (₹{actual_inr:.0f} > ₹100)</b>" if actual_inr > 100 else ""

    # Determine Final Status Display (premium emojis — same IDs as /msh)
    if status_raw == "charged":
        final_status = f'𝗖𝗛𝗔𝗥𝗚𝗘𝗗 <tg-emoji emoji-id="{CUSTOM_CHARGED_EMOJI_ID}">💎</tg-emoji>'
        is_charged = True
    elif status_raw == "approved":
        final_status = f'𝗔𝗣𝗣𝗥𝗢𝗩𝗘𝗗 <tg-emoji emoji-id="{CUSTOM_APPROVED_EMOJI_ID}">✅</tg-emoji>'
        is_charged = True
    elif status_raw == "declined":
        final_status = f'𝗗𝗘𝗖𝗟𝗜𝗡𝗘𝗗 <tg-emoji emoji-id="{CUSTOM_DECLINED_EMOJI_ID}">❌</tg-emoji>'
    else:
        final_status = "𝗘𝗥𝗥𝗢𝗥 ⚠️"

    # UPDATED CREDIT DEDUCTION LOGIC (Applies to everyone)
    credits_to_deduct = 0
    
    if status_raw == 'charged':
        credits_to_deduct = 2
    elif status_raw == 'approved':
        credits_to_deduct = 1
    elif status_raw == 'declined':
        credits_to_deduct = 1
    # Else (Error/Timeout) -> 0 credits

    # Fetch fresh balance and deduct
    if credits_to_deduct > 0:
        current_balance = await asyncio.to_thread(get_user_credits, user_id)
        new_balance = current_balance - credits_to_deduct
        if new_balance < 0: new_balance = 0
        await asyncio.to_thread(update_credits, user_id, new_balance)

    # UPDATE STATS (Checked + Charged)
    await update_user_stats(user_id, is_charged)

    # Build Final Caption
    user_link = build_user_link(user)
    dev_link = '<a href="https://t.me/Enchanted_linux_0x">Enchanted_linux_0x</a>'
    
    user_display = f"{user_link} <b>[{plan_name}]</b>"
    
    elapsed = time.time() - start_time
    
    final_caption = (
        f"𝗦𝘁𝗮𝘁𝘂𝘀 ➠ {final_status}\n"
        f"𝗖𝗮𝗿𝗱 ➠ <code>{formatted_cc}</code>\n"
        f"𝗚𝗮𝘁𝗲𝘄𝗮𝘆 ➠ 𝗥𝗮𝘇𝗼𝗿𝗽𝗮𝘆 ₹{actual_inr}{amount_warn}\n"
        f"𝗥𝗲𝘀𝗽𝗼𝗻𝘀𝗲 ➠ <b>{res_message}</b>\n"
        f"𝗕𝗿𝗮𝗻𝗱 ➠ <b>{bin_scheme}</b>\n"
        f"𝗜𝘀𝘀𝘂𝗲𝗿 ➠ <b>{bin_bank}</b>\n"
        f"𝗖𝗼𝘂𝗻𝘁𝗿𝘆 ➠ <b>{bin_country}</b>\n"
        f"𝗨𝘀𝗲𝗿 ➠ {user_display}\n"
        f"𝗗𝗲𝘃 ➠ {dev_link}"
    )

    # Send result by editing the processing message (matches /sh single-gate flow)
    try:
        await proc_msg.edit_text(final_caption, parse_mode="HTML", disable_web_page_preview=True)
    except Exception:
        await safe_reply(message, final_caption, parse_mode="HTML", disable_web_page_preview=True)
    
    # Log timing
    logging.info(f"RZ command completed in {elapsed:.2f}s for user {user_id}")
