from live_emoji import plan_badge, dev_badge
import asyncio
import re
import logging
import requests
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
from database import is_gate_enabled, get_user_credits, update_credits, get_db_connection, create_user
from bin import get_bin_info
from sub import get_premium_status

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

# Router for this module
router = Router()

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# CONFIGURATION
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

# Updated VBV API Endpoint
VBV_API_URL = "https://api.voidapi.xyz/v2/vbv"
VBV_API_KEY = "VDX-SHA2X-NZ0RS-O7HAM"

user_last_command_time = {}

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# DATABASE INITIALIZATION
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
        print("[DB] VBV Stats columns checked/created.")
    except Exception as e:
        print(f"[DB] Error checking stats columns: {e}")

ensure_stats_columns()

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# VBV API CALLER (UPDATED WITH CORRECT MAPPING)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def call_vbv_api(cc, mm, yy, cvv):
    """
    Calls the VBV API and returns a dict with 'status' and 'response'.
    The card param is sent as cc|mm|yy|cvv.
    
    New API Response format:
    {
        "data": {
            "bin": "514377",
            "scheme": "Mastercard",
            "type": "DEBIT",
            "level": "ENHANCED",
            "bank": "THE BANCORP BANK NATIONAL ASSOCIATION",
            "country": "US",
            "emoji": "🇺🇸",
            "status": "challenge_required"
        },
        "success": true
    }
    
    APPROVED responses: authenticate_successful, authenticate_attempt_successful
    DECLINED responses: authenticate_frictionless_failed, challenge_required, authenticate_rejected
    """
    card_param = f"{cc}|{mm}|{yy}|{cvv}"
    try:
        # Updated API call with new endpoint format
        resp = requests.get(
            VBV_API_URL,
            params={"key": VBV_API_KEY, "card": card_param},
            timeout=30
        )
        data = resp.json()
        
        # Extract response from new format
        response_data = data.get("data", {})
        status = response_data.get("status", "").lower()
        
        # Map status to approved/declined based on new rules
        # APPROVED: authenticate_successful, authenticate_attempt_successful
        # DECLINED: authenticate_frictionless_failed, challenge_required, authenticate_rejected
        if status in ["authenticate_successful", "authenticate_attempt_successful"]:
            status_result = "approved"
        elif status in ["authenticate_frictionless_failed", "challenge_required", "authenticate_rejected"]:
            status_result = "declined"
        else:
            # Default to declined for unknown statuses
            status_result = "declined"
        
        # Return the exact status as received from API
        response_text = status  # Keep as is, exactly what API returned
        
        return {"status": status_result, "response": response_text}

    except Exception as e:
        logging.error(f"[VBV API] Request failed: {e}")
        return {"status": "error", "response": str(e)}

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# HELPERS
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def _update_user_stats_sync(user_id, is_charged):
    """Synchronous helper to increment stats."""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("UPDATE users SET cc_checked = cc_checked + 1 WHERE user_id = %s", (user_id,))
    if is_charged:
        cursor.execute("UPDATE users SET cc_charged = cc_charged + 1 WHERE user_id = %s", (user_id,))
    conn.commit()
    conn.close()

async def get_user_plan_name(user_id):
    """Fetches the specific plan name from receipts if premium, else Trial."""
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
    """Validates a credit card number using Luhn Algorithm."""
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

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# COMMAND HANDLER
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

@router.message(F.text.startswith("/vbv"))
async def vbv_command(message: types.Message):
    # 1. GATE CHECK
    if not await asyncio.to_thread(is_gate_enabled, "vbv"):
        await message.reply(
            "🚧 <b>𝗕𝗿𝗮𝗶𝗻𝘁𝗿𝗲𝗲 𝗩𝗕𝗩 𝗚𝗮𝘁𝗲 𝗶𝘀 𝘂𝗻𝗱𝗲𝗿 𝗺𝗮𝗶𝗻𝘁𝗲𝗻𝗮𝗻𝗰𝗲.</b>\n"
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
        if user_id in user_last_command_time:
            elapsed = current_time - user_last_command_time[user_id]
            if elapsed < 10:
                remaining_time = round(10 - elapsed, 1)
                await message.reply(
                    f"<tg-emoji emoji-id=\"6255910249362885846\">⚠️</tg-emoji> <b>Aᴄᴛɪᴠᴇ Cᴏᴏʟᴅᴏᴡɴ !</b>\n\n"
                    f"<b>Pʟᴇᴀsᴇ Wᴀɪᴛ <code>{remaining}</code> Sᴇᴄᴏɴᴅs Bᴇғᴏʀᴇ Cᴏɴᴛɪɴᴜɪɴɢ.</b>\n\n"
                    f"<tg-emoji emoji-id=\"6136275172283391020\">⭐</tg-emoji> <b>Pᴜʀᴄʜᴀsᴇ Pʀᴇᴍɪᴜᴍ Pʟᴀɴ Fᴏʀ Usᴇ Cᴏᴍᴍᴀɴᴅs Wɪᴛʜᴏᴜᴛ Cᴏᴏʟᴅᴏᴡɴ.</b>",
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
            "<tg-emoji emoji-id=\"4956612582816351459\">❌</tg-emoji> <b>Usage:</b> /vbv <code>cc|mm|yy|cvv</code>\n"
            "Or reply to a message containing card details.",
            parse_mode="HTML"
        )
        return

    # Regex to find CC
    pattern = r'\b(\d{15,16})[|\s/?\\:]+(\d{2,4})[|\s/?\\:]+(\d{2,4})[|\s/?\\:]+(\d{3,4})\b'
    match = re.search(pattern, raw_text)
    if not match:
        await message.reply(
            "<tg-emoji emoji-id=\"4956612582816351459\">❌</tg-emoji> <b>Invalid Card Format.</b>\n"
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
            "<tg-emoji emoji-id=\"4956612582816351459\">❌</tg-emoji> <b>Invalid Card</b>\n"
            "Your card number is incorrect.",
            parse_mode="HTML"
        )
        return

    # 6. Check Credits
    current_credits = await asyncio.to_thread(get_user_credits, user_id)
    if current_credits is None or current_credits < 1:
        await message.reply(
            "<tg-emoji emoji-id=\"4956612582816351459\">❌</tg-emoji> <b>Iɴsᴜғғɪᴄɪᴇɴᴛ Cʀᴇᴅɪᴛs</b>\n\n"
            "Yᴏᴜ Nᴇᴇᴅ Aᴛ Lᴇᴀsᴛ <b>1 Cʀᴇᴅɪᴛ</b> Tᴏ Usᴇ Tʜɪs Gᴀᴛᴇ.\n"
            "Usᴇ /plan Tᴏ Gᴇᴛ Mᴏʀᴇ.",
            parse_mode="HTML"
        )
        return

    # 7. Fetch Plan Name
    plan_name = await get_user_plan_name(user_id)

    # 8. Send Processing Message
    escaped_card = escape(formatted_cc)
    proc_msg = await message.reply(
        f"<b>Pʀᴏᴄᴇssɪɴɢ...</b><tg-emoji emoji-id=\"6154603635981423575\">⏳</tg-emoji>\n"
        f"<pre><code>{escaped_card}</code></pre>\n"
        f"<b>Gᴀᴛᴇ ➺ VBV Lᴏᴏᴋᴜᴘ</b>\n",
        parse_mode="HTML"
    )

    # 9. Execute Background Task
    asyncio.create_task(
        process_vbv_check(
            message, proc_msg, user, user_id, formatted_cc, cc, mm, yy, cvv, plan_name
        )
    )

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# BACKGROUND PROCESSOR
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

async def process_vbv_check(message, proc_msg, user, user_id, formatted_cc, cc, mm, yy, cvv, plan_name):
    """Handles calling the VBV API, DB updates, and final message editing."""

    # A. ENSURE USER EXISTS IN DB
    check_started = time.time()
    try:
        await asyncio.to_thread(create_user, user_id, user.username)
    except Exception as e:
        logging.error(f"Error ensuring user exists: {e}")

    # B. CALL VBV API
    api_result = await asyncio.to_thread(call_vbv_api, cc, mm, yy, cvv)

    # C. Bin Lookup (keeping original bin lookup)
    try:
        bin_info = await get_bin_info(cc[:6])
    except Exception:
        bin_info = {}

    bin_scheme = bin_info.get("scheme", "N/A")
    bin_bank = bin_info.get("bank", "N/A")
    country_name = bin_info.get("country", "N/A")
    country_flag = bin_info.get("country_emoji", "")
    bin_country = f"{country_flag} {country_name}" if country_flag else country_name
    type = bin_info.get("type") or "N/A"

    # D. Determine Final Status
    status_raw = api_result.get("status", "").lower()
    res_message = api_result.get("response", "N/A")  # Now contains exact API status

    is_charged = False

    CUSTOM_APPROVED_EMOJI_ID = "4958610528588008305"
    CUSTOM_DECLINED_EMOJI_ID = "4956612582816351459"

    if status_raw == "approved":
        final_status = f'<b>ᎪꮲꮲꭱƦꮎꮩꭼꭰ</b> <tg-emoji emoji-id="{CUSTOM_APPROVED_EMOJI_ID}">✅</tg-emoji>'
        is_charged = True
    elif status_raw == "declined":
        final_status = f'<b>Ꭰᴇᴄʟɪɴᴇᴅ</b> <tg-emoji emoji-id="{CUSTOM_DECLINED_EMOJI_ID}">❌</tg-emoji>'
    else:
        final_status = "<b>Ꭼʀʀᴏʀ</b> ⚠️"

    # E. UPDATE STATS
    try:
        await asyncio.to_thread(_update_user_stats_sync, user_id, is_charged)
    except Exception as e:
        logging.error(f"Failed to update stats: {e}")

    # F. CREDIT DEDUCTION
    try:
        current_credits = await asyncio.to_thread(get_user_credits, user_id)
        if current_credits is not None and current_credits > 0:
            new_balance = current_credits - 1
            await asyncio.to_thread(update_credits, user_id, new_balance)
            print(f"[CREDIT LOG VBV] User {user_id} deducted 1 credit. Old: {current_credits} -> New: {new_balance}")
        else:
            print(f"[CREDIT LOG VBV] User {user_id} has 0 credits. Skipping deduction (should have been blocked earlier).")
    except Exception as e:
        logging.error(f"Failed to deduct credits for user {user_id}: {e}")
        print(f"[ERROR] Credit deduction failed: {e}")

    # G. Build Final Caption
    user_link = build_user_link(user)
    dev_link = dev_badge()
    user_display = f"{user_link} {plan_badge(plan_name)}"

    elapsed = time.time() - check_started
    final_caption = (
        f'<b><a href="https://t.me/broken_wiz">[⌭]</a> Sᴛᴀᴛᴜs ➵ {final_status}</b>\n'
        f"<tg-emoji emoji-id=\"5920055227133725805\">💳</tg-emoji>\n"
        f"⤷ <code>{formatted_cc}</code>\n"
        f"━━━━━━━━━━━\n"
        f'<b><a href="https://t.me/broken_wiz">⬢</a> Gᴀᴛᴇ ➵ VBV Lᴏᴏᴋᴜᴘ</b>\n'
        f'<b><a href="https://t.me/broken_wiz">⬡</a> Rᴀᴡ ➵ {res_message}</b>\n'
        f"━━━━━━━━━━━\n"
        f"<b>Tʏᴘᴇ ➵</b> <code>[ {type} ]</code>\n"
        f"<b>Iɴꜰᴏ ➵</b> <code>{bin_scheme} - {bin_bank} - {bin_country}</code>\n"
        f"━━━━━━━━━━━\n"
        f"<tg-emoji emoji-id=\"5440621591387980068\">🔜</tg-emoji> <b>➵ {elapsed:.2f}s</b>\n"
        f"<tg-emoji emoji-id=\"6028240037366207289\">👤</tg-emoji> <b>➵ {user_display}</b>\n"
        f"<tg-emoji emoji-id=\"5429615084856969948\">🏴‍☠️</tg-emoji> <b>➵ {dev_link}</b>"
    )

    # H. FETCH ANIME GIF
    gif_url = await get_anime_gif()

    # I. Send as Animation (GIF) with Caption
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
        logging.warning(f"[VBV] Could not send GIF, falling back to text: {e}")
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
