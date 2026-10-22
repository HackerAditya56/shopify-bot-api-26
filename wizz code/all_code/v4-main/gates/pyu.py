from live_emoji import plan_badge, dev_badge
import asyncio
import re
import logging
import time
import random
import psycopg2.extras
import urllib3
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
from database import is_gate_enabled, get_user_credits, update_credits, get_db_connection
from bin import get_bin_info
from sub import get_premium_status
from gates import payu  # Import local PayU gate script

# Disable InsecureRequestWarnings for PayU requests
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

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
# PROXY ROTATION POOL
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

PROXY_LIST = [
    #"http://wtvdwams:z3jfr2x3c38b@31.59.20.176:6754",
    #"http://wtvdwams:z3jfr2x3c38b@198.23.239.134:6540",
    #"http://wtvdwams:z3jfr2x3c38b@45.38.107.97:6014",
    #"http://wtvdwams:z3jfr2x3c38b@107.172.163.27:6543",
    #"http://wtvdwams:z3jfr2x3c38b@198.105.121.200:6462",
    #"http://wtvdwams:z3jfr2x3c38b@216.10.27.159:6837",
    #"http://wtvdwams:z3jfr2x3c38b@142.111.67.146:5611",
    "http://wtvdwams:z3jfr2x3c38b@191.96.254.138:6185",
    "http://wtvdwams:z3jfr2x3c38b@31.58.9.4:6077",
    #"http://wtvdwams:z3jfr2x3c38b@198.46.161.42:5092"
]

def set_random_proxy():
    """Picks a random proxy and injects it into the payu.py module variables."""
    proxy_url = random.choice(PROXY_LIST)
    parsed = proxy_url.replace("http://", "")
    creds_host = parsed.split('@')
    user_pass = creds_host[0].split(':')
    host_port = creds_host[1].split(':')
    
    # Override payu.py module globals before initialization
    payu.PROXY_HOST = host_port[0]
    payu.PROXY_PORT = int(host_port[1])
    payu.PROXY_USERNAME = user_pass[0]
    payu.PROXY_PASSWORD = user_pass[1]
    payu.PROXY_URL = proxy_url
    payu.PROXIES = {'http': proxy_url, 'https': proxy_url}

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# CONFIGURATION
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

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
        print("[DB] PYU Stats columns checked/created.")
    except Exception as e:
        print(f"[DB] Error checking stats columns: {e}")

# Run this once when script loads
ensure_stats_columns()

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# HELPERS
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def update_user_stats_sync(user_id, is_charged):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("UPDATE users SET cc_checked = cc_checked + 1 WHERE user_id = %s", (user_id,))
    if is_charged:
        cursor.execute("UPDATE users SET cc_charged = cc_charged + 1 WHERE user_id = %s", (user_id,))
    conn.commit()
    conn.close()

async def get_user_plan_name(user_id):
    """Fetches specific plan name from receipts if premium, else Trial."""
    is_premium, _ = await asyncio.to_thread(get_premium_status, user_id)
    
    if is_premium:
        try:
            def _sync_fetch():
                conn = get_db_connection()
                cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
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

def build_user_link(user_obj) -> str:
    """Builds a clickable user mention link."""
    name = escape(user_obj.first_name or "User")
    if user_obj.username:
        return f'<a href="https://t.me/{escape(user_obj.username)}">{name}</a>'
    return f'<a href="tg://user?id={user_obj.id}">{name}</a>'

def run_payu_gate_sync(formatted_cc):
    """
    Synchronous wrapper to run the heavy PayU Selenium/Requests process.
    Runs completely in a thread to avoid blocking the async loop.
    """
    set_random_proxy()  # Inject proxy before init
    
    processor = payu.PayUProcessor()
    try:
        result = processor.process(formatted_cc)
        return result
    except Exception as e:
        logging.error(f"PYU Sync Execution Error: {e}")
        return {"value": "We are unable to authorize your payment.(ERROR)", "status": "declined", "code": "ERROR"}
    finally:
        processor.cleanup()

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# COMMAND HANDLER
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

@router.message(F.text.startswith("/pyu"))
async def pyu_command(message: types.Message):
    # 1. GATE CHECK
    if not await asyncio.to_thread(is_gate_enabled, "pyu"):
        await message.reply(
            #"🚧 <b>𝗣𝗮𝘆𝗨 𝟭$ 𝗚𝗮𝘁𝗲 𝗶𝘀 𝘂𝗻𝗱𝗲𝗿 𝗺𝗮𝗶𝗻𝘁𝗲𝗻𝗮𝗻𝗰𝗲.</b>\n"
            #"𝗜𝘁 𝘄𝗶𝗹𝗹 𝗯𝗲 𝗯𝗮𝗰𝗸 𝘀𝗵𝗼𝗿𝘁𝗹𝘆 𝘄𝗶𝘁𝗵 𝗲𝘅𝗰𝗶𝘁𝗶𝗻𝗴 𝗶𝗺𝗽𝗿𝗼𝘃𝗲𝗺𝗲𝗻𝘁𝘀.⚙️",
            "🚧 <b>𝗚𝗮𝘁𝗲 𝗶𝘀 𝘂𝗻𝗱𝗲𝗿 𝗺𝗮𝗶𝗻𝘁𝗲𝗻𝗮𝗻𝗰𝗲.</b>\n\n"
            "<b>𝗜𝘁 𝘄𝗶𝗹𝗹 𝗯𝗲 𝗯𝗮𝗰𝗸 𝘄𝗶𝘁𝗵 𝗶𝗺𝗽𝗿𝗼𝘃𝗲𝗺𝗲𝗻𝘁𝘀.</b> <tg-emoji emoji-id=\"5372965329511139384\">😎</tg-emoji>",
            parse_mode="HTML"
        )
        return

    user = message.from_user
    user_id = user.id
    current_time = time.time()

    # 2. GET PREMIUM STATUS
    is_premium, _ = await asyncio.to_thread(get_premium_status, user_id)

    # 3. PREMIUM RESTRICTION CHECK
    if not is_premium:
        await message.reply(
            "❌ 𝗧𝗵𝗶𝘀 𝗴𝗮𝘁𝗲 𝗿𝗲𝗾𝘂𝗶𝗿𝗲𝘀 𝗮𝗻 𝗮𝗰𝘁𝗶𝘃𝗲 𝗽𝗹𝗮𝗻. 𝘂𝘀𝗲 /plan",
            parse_mode="HTML"
        )
        return

    # 4. RATE LIMITING CHECK (Skips automatically since user is premium, but kept for structure)
    if not is_premium:
        if user_id in user_last_command_time:
            elapsed = current_time - user_last_command_time[user_id]
            if elapsed < 10:
                remaining_time = round(10 - elapsed, 1)
                await message.reply(
                    f"<tg-emoji emoji-id=\"6255910249362885846\">⚠️</tg-emoji> <b>𝗔𝗰𝘁𝗶𝘃𝗲 𝗰𝗼𝗼𝗹𝗱𝗼𝘄𝗻 !</b>\n\n"
                    f"𝗣𝗹𝗲𝗮𝘀𝗲 𝘄𝗮𝗶𝘁 <code>{remaining_time}</code> 𝘀𝗲𝗰𝗼𝗻𝗱𝘀 𝗯𝗲𝗳𝗼𝗿𝗲 𝗰𝗼𝗻𝘁𝗶𝗻𝘂𝗶𝗻𝗴.\n\n"
                    f"<tg-emoji emoji-id=\"6136275172283391020\">⭐</tg-emoji> 𝗣𝘂𝗿𝗰𝗵𝗮𝘀𝗲 𝗽𝗿𝗲𝗺𝗶𝘂𝗺 𝗽𝗹𝗮𝗻 𝗳𝗼𝗿 𝘂𝘀𝗲 𝗰𝗼𝗺𝗺𝗮𝗻𝗱𝘀 𝘄𝗶𝘁𝗵𝗼𝘂𝘁 𝗰𝗼𝗼𝗹𝗱𝗼𝘄𝗻.",
                    parse_mode="HTML"
                )
                return
        user_last_command_time[user_id] = current_time
    
    # 5. Extract Card Details
    parts = message.text.split(maxsplit=1)
    raw_text = ""
    
    if len(parts) > 1:
        raw_text = parts[1].strip()
    elif message.reply_to_message:
        raw_text = message.reply_to_message.text or message.reply_to_message.caption
        
    if not raw_text:
        await message.reply(
            "❌ <b>Usage:</b> /pyu <code>cc|mm|yy|cvv</code>\n"
            "Or reply to a message containing card details.",
            parse_mode="HTML"
        )
        return

    # Regex to find CC
    pattern = r'\b(\d{15,16})[|\s/?\\:]+(\d{2,4})[|\s/?\\:]+(\d{2,4})[|\s/?\\:]+(\d{3,4})\b'
    match = re.search(pattern, raw_text)

    if not match:
        await message.reply(
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

    # 6. LUHN CHECK
    if not luhn_check(cc):
        await message.reply(
            "❌ <b>Invalid Card</b>\n"
            "Your card number is incorrect.",
            parse_mode="HTML"
        )
        return

    # 7. Check Credits
    current_credits = await asyncio.to_thread(get_user_credits, user_id)
    if current_credits is None or current_credits <= 0:
        await message.reply(
            "❌ <b>Insufficient Credits!</b>\n\n"
            "You have 0 credits left.",
            parse_mode="HTML"
        )
        return

    # 8. Fetch Plan Name
    plan_name = await get_user_plan_name(user_id)

    # 9. Send Processing Message
    escaped_card = escape(formatted_cc)
    proc_msg = await message.reply(
        f"<pre><code>𝙋𝙧𝙤𝙘𝙚𝙨𝙨𝙞𝙣𝙜⏳...</code></pre>\n"
        f"<pre><code>{escaped_card}</code></pre>\n"
        f"<b>𝙂𝙖𝙩𝙚𝙬𝙖𝙮 ➠ 𝙋𝙖𝙮𝙐 𝟭$</b>\n",
        parse_mode="HTML"
    )

    # 10. Execute Background Task
    asyncio.create_task(
        process_pyu_check(
            message, proc_msg, user, user_id, formatted_cc, cc, plan_name
        )
    )

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# BACKGROUND PROCESSOR
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

async def process_pyu_check(message, proc_msg, user, user_id, formatted_cc, cc, plan_name):
    # A. Call PayU Gate in a thread (Selenium takes ~25s)
    check_started = time.time()
    api_result = await asyncio.to_thread(run_payu_gate_sync, formatted_cc)

    # B. Bin Lookup
    try:
        bin_info = await get_bin_info(cc[:6])
    except Exception:
        bin_info = {}

    bin_scheme = bin_info.get("scheme", "N/A")
    bin_bank = bin_info.get("bank", "N/A")
    
    country_name = bin_info.get("country", "N/A")
    country_flag = bin_info.get("country_emoji", "")
    bin_country = f"{country_name} {country_flag}" if country_flag else country_name
    type = bin_info.get("type") or "N/A"

    # C. Determine Final Status & Format Response
    status_raw = api_result.get("status", "declined").lower()
    res_code = api_result.get("code", "ERROR")
    res_value = api_result.get("value", "Unknown Error")
    
    # REQUIRED FORMAT: response [code]
    res_message = f"{res_value} [{res_code}]"
    
    is_charged = False
    
    # Custom Emoji IDs
    CUSTOM_CHARGED_EMOJI_ID = "4956719506027185156"
    CUSTOM_APPROVED_EMOJI_ID = "4958610528588008305"
    CUSTOM_DECLINED_EMOJI_ID = "4956612582816351459"

    if status_raw == "charged":
        final_status = f'𝗖𝗛𝗔𝗥𝗚𝗘𝗗 <tg-emoji emoji-id="{CUSTOM_CHARGED_EMOJI_ID}">❌</tg-emoji>'
        is_charged = True
    elif status_raw == "approved":
        final_status = f'𝗔𝗣𝗣𝗥𝗢𝗩𝗘𝗗 <tg-emoji emoji-id="{CUSTOM_APPROVED_EMOJI_ID}">❌</tg-emoji>'
        is_charged = True 
    elif status_raw == "declined":
        final_status = f'𝗗𝗘𝗖𝗟𝗜𝗡𝗘𝗗 <tg-emoji emoji-id="{CUSTOM_DECLINED_EMOJI_ID}">❌</tg-emoji>'
    else:
        final_status = "𝗘𝗥𝗥𝗢𝗥 ⚠️"

    # D. CREDIT DEDUCTION LOGIC
    credits_to_deduct = 0
    
    if status_raw == 'charged':
        credits_to_deduct = 2
    elif status_raw == 'approved':
        credits_to_deduct = 1
    elif status_raw == 'declined':
        credits_to_deduct = 1

    if credits_to_deduct > 0:
        current_balance = await asyncio.to_thread(get_user_credits, user_id)
        new_balance = current_balance - credits_to_deduct
        if new_balance < 0: new_balance = 0
        await asyncio.to_thread(update_credits, user_id, new_balance)

    # E. UPDATE STATS
    await asyncio.to_thread(update_user_stats_sync, user_id, is_charged)

    # F. Build Final Caption
    user_link = build_user_link(user)
    dev_link = dev_badge()
    user_display = f"{user_link} {plan_badge(plan_name)}"
    
    elapsed = time.time() - check_started
    final_caption = (
        f'<b><a href="https://t.me/broken_wiz">[⌭]</a> Sᴛᴀᴛᴜs ➵ {final_status}</b>\n'
        f"<tg-emoji emoji-id=\"5920055227133725805\">💳</tg-emoji>\n"
        f"⤷ <code>{formatted_cc}</code>\n"
        f"━━━━━━━━━━━\n"
        f'<b><a href="https://t.me/broken_wiz">⬢</a> Gᴀᴛᴇ ➵ 𝗣𝗮𝘆𝗨 𝟭 𝗨𝗦𝗗</b>\n'
        f'<b><a href="https://t.me/broken_wiz">⬡</a> Rᴀᴡ ➵ {res_message}</b>\n'
        f"━━━━━━━━━━━\n"
        f"<b>Tʏᴘᴇ ➵</b> <code>[ {type} ]</code>\n"
        f"<b>Iɴꜰᴏ ➵</b> <code>{bin_scheme} - {bin_bank} - {bin_country}</code>\n"
        f"━━━━━━━━━━━\n"
        f"<tg-emoji emoji-id=\"5440621591387980068\">🔜</tg-emoji> <b>➵ {elapsed:.2f}s</b>\n"
        f"<tg-emoji emoji-id=\"6028240037366207289\">👤</tg-emoji> <b>➵ {user_display}</b>\n"
        f"<tg-emoji emoji-id=\"5429615084856969948\">🏴‍☠️</tg-emoji> <b>➵ {dev_link}</b>"
    )

    # G. FETCH ANIME GIF
    gif_url = await get_anime_gif()

    # H. Send as Animation (GIF) with Caption
    try:
        # Try to delete the processing message first
        try:
            await proc_msg.delete()
        except Exception:
            pass
        
        # Send as animation with GIF
        await message.reply_animation(
            animation=gif_url,
            caption=final_caption,
            parse_mode="HTML",
            disable_web_page_preview=True
        )
    except (TelegramForbiddenError, TelegramBadRequest) as e:
        # Fallback to editing the processing message if GIF sending fails
        logging.warning(f"[PYU] Could not send GIF, falling back to text: {e}")
        try:
            await proc_msg.edit_text(
                text=final_caption,
                parse_mode="HTML",
                disable_web_page_preview=True
            )
        except Exception as edit_err:
            logging.error(f"Error editing message: {edit_err}")
            await message.reply(
                text=final_caption,
                parse_mode="HTML",
                disable_web_page_preview=True
            )
    except Exception as e:
        # Ultimate fallback - just edit the processing message
        logging.error(f"Error sending result: {e}")
        try:
            await proc_msg.edit_text(
                text=final_caption,
                parse_mode="HTML",
                disable_web_page_preview=True
            )
        except Exception:
            await message.reply(
                text=final_caption,
                parse_mode="HTML",
                disable_web_page_preview=True
            )
