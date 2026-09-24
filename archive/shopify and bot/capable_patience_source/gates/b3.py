import asyncio
import re
import logging
import random
import aiohttp
import time
import psycopg2.extras
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
# CONFIGURATION & URLS
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

B3_API_URL = "http://b3byxenin.up.railway.app/gate=b3/key=broken/card={cc}"
user_last_command_time = {}
router = Router()

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
# DATABASE INITIALIZATION
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def ensure_stats_columns():
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
        print("[DB] B3 Stats columns checked/created.")
    except Exception as e:
        print(f"[DB] Error checking stats columns: {e}")

ensure_stats_columns()

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# HELPERS
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

async def update_user_stats(user_id, is_charged):
    def _sync_update():
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("UPDATE users SET cc_checked = cc_checked + 1 WHERE user_id = %s", (user_id,))
        if is_charged:
            cursor.execute("UPDATE users SET cc_charged = cc_charged + 1 WHERE user_id = %s", (user_id,))
        conn.commit()
        conn.close()

    await asyncio.to_thread(_sync_update)

async def get_user_plan_name(user_id):
    is_premium, _ = get_premium_status(user_id)
    
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
    name = user_obj.first_name or "User"
    if user_obj.username:
        return f'<a href="https://t.me/{user_obj.username}">{name}</a>'
    return f'<a href="tg://user?id={user_obj.id}">{name}</a>'

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# COMMAND HANDLER
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

@router.message(F.text.startswith("/b3"))
async def b3_command(message: types.Message):
    if not is_gate_enabled("b3"):
        await message.reply(
            "🚧 <b>𝗕𝗿𝗮𝗶𝗻𝘁𝗿𝗲𝗲 𝗔𝘂𝘁𝗵 𝗶𝘀 𝘂𝗻𝗱𝗲𝗿 𝗺𝗮𝗶𝗻𝘁𝗲𝗻𝗮𝗻𝗰𝗲.</b>\n"
            "𝗜𝘁 𝘄𝗶𝗹𝗹 𝗯𝗲 𝗯𝗮𝗰𝗸 𝘀𝗵𝗼𝗿𝘁𝗹𝘆 𝘄𝗶𝘁𝗵 𝗲𝘅𝗰𝗶𝘁𝗶𝗻𝗴 𝗶𝗺𝗽𝗿𝗼𝘃𝗲𝗺𝗲𝗻𝘁𝘀.⚙️",
            parse_mode="HTML"
        )
        return

    user = message.from_user
    user_id = user.id
    current_time = time.time()

    is_premium, _ = await asyncio.to_thread(get_premium_status, user_id)

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
    
    parts = message.text.split(maxsplit=1)
    raw_text = ""
    
    if len(parts) > 1:
        raw_text = parts[1].strip()
    elif message.reply_to_message:
        raw_text = message.reply_to_message.text or message.reply_to_message.caption
        
    if not raw_text:
        await message.reply(
            "❌ <b>Usage:</b> /b3 <code>cc|mm|yy|cvv</code>\n"
            "Or reply to a message containing card details.",
            parse_mode="HTML"
        )
        return

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

    if len(yy_raw) == 4:
        yy = yy_raw[2:]
    else:
        yy = yy_raw

    formatted_cc = f"{cc}|{mm}|{yy}|{cvv}"

    if not luhn_check(cc):
        await message.reply(
            "❌ <b>Invalid Card</b>\n"
            "Your card number is incorrect.",
            parse_mode="HTML"
        )
        return

    current_credits = await asyncio.to_thread(get_user_credits, user_id)
    
    if current_credits is None or current_credits < 1:
        await message.reply(
            "❌ <b>Insufficient Credits!</b>\n\n"
            "You need at least 1 credit to perform a check.",
            parse_mode="HTML"
        )
        return

    plan_name = await get_user_plan_name(user_id)

    escaped_card = escape(formatted_cc)
    proc_msg = await message.reply(
        f"<pre><code>𝙋𝙧𝙤𝙘𝙚𝙨𝙨𝙞𝙣𝙜⏳...</code></pre>\n"
        f"<pre><code>{escaped_card}</code></pre>\n"
        f"<b>𝙂𝙖𝙩𝙚𝙬𝙖𝙮 ➠ 𝘽𝙧𝙖𝙞𝙣𝙩𝙧𝙚𝙚 𝘼𝙪𝙩𝙝</b>\n",
        parse_mode="HTML"
    )

    asyncio.create_task(
        process_b3_check(
            message, proc_msg, user, user_id, formatted_cc, cc, plan_name
        )
    )

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# BACKGROUND PROCESSOR
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

async def process_b3_check(message, proc_msg, user, user_id, formatted_cc, cc, plan_name):
    try:
        await asyncio.to_thread(create_user, user_id, user.username)
    except Exception as e:
        logging.error(f"Error ensuring user exists: {e}")

    api_result = {"status": "ERROR", "response": "Unknown Error", "elapsed": 0, "dev": "@Enchanted_linux_0x"}
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(B3_API_URL.format(cc=formatted_cc), timeout=90) as resp:
                if resp.status == 200:
                    api_result = await resp.json()
                else:
                    api_result["response"] = f"API Error: {resp.status}"
                    api_result["status"] = "error"
    except asyncio.TimeoutError:
        logging.error(f"Braintree API Timeout")
        api_result["response"] = "API Timed Out (Server took too long to respond)"
        api_result["status"] = "error"
    except Exception as e:
        logging.error(f"Braintree API Error: {e}")
        api_result["response"] = f"Connection Error: {str(e)}"
        api_result["status"] = "error"

    try:
        bin_info = await get_bin_info(cc[:6])
    except Exception:
        bin_info = {}

    bin_scheme = bin_info.get("scheme", "N/A")
    bin_bank = bin_info.get("bank", "N/A")
    
    country_name = bin_info.get("country", "N/A")
    country_flag = bin_info.get("country_emoji", "")
    bin_country = f"{country_name} {country_flag}" if country_flag else country_name

    CUSTOM_LIVE_EMOJI_ID = "4958610528588008305"
    CUSTOM_DEAD_EMOJI_ID = "4956612582816351459"
    
    api_status = api_result.get("status", "").lower()
    api_response_msg = api_result.get("response", "N/A")
    api_elapsed = api_result.get("elapsed", 0)
    api_dev = api_result.get("dev", "@Enchanted_linux_0x")
    
    is_charged = False
    
    if api_status == "live":
        final_status = f'𝗔𝗽𝗽𝗿𝗼𝘃𝗲𝗱 <tg-emoji emoji-id=\"{CUSTOM_LIVE_EMOJI_ID}\">✅</tg-emoji>'
        is_charged = True
    elif api_status == "dead":
        final_status = f'𝗗𝗲𝗰𝗹𝗶𝗻𝗲𝗱 <tg-emoji emoji-id=\"{CUSTOM_DEAD_EMOJI_ID}\">❌</tg-emoji>'
    elif api_status == "error":
        final_status = f'𝗘𝗥𝗥𝗢𝗥 ⚠️'
    else:
        final_status = "𝗨𝗡𝗞𝗡𝗢𝗪𝗡 ⚠️"

    try:
        await update_user_stats(user_id, is_charged)
    except Exception as e:
        logging.error(f"Failed to update stats: {e}")

    try:
        current_credits = await asyncio.to_thread(get_user_credits, user_id)
        
        if current_credits is not None and current_credits > 0:
            new_balance = current_credits - 1
            await asyncio.to_thread(update_credits, user_id, new_balance)
            print(f"[CREDIT LOG B3] User {user_id} deducted 1 credit. Old: {current_credits} -> New: {new_balance}")
        else:
            print(f"[CREDIT LOG B3] User {user_id} has 0 credits. Skipping deduction (should have been blocked earlier).")
            
    except Exception as e:
        logging.error(f"Failed to deduct credits for user {user_id}: {e}")
        print(f"[ERROR] Credit deduction failed: {e}")

    masked_card = api_result.get("card", {}).get("masked", formatted_cc)
    
    user_link = build_user_link(user)
    dev_link = '<a href="https://t.me/Enchanted_linux_0x">Enchanted_linux_0x</a>'
    user_display = f"{user_link} <b>[{plan_name}]</b>"
    
    final_caption = (
        f"𝗦𝘁𝗮𝘁𝘂𝘀 ➠ {final_status}\n"
        f"𝗖𝗮𝗿𝗱 ➠ <code>{formatted_cc}</code>\n"
        f"𝗚𝗮𝘁𝗲𝘄𝗮𝘆 ➠ 𝗕𝗿𝗮𝗶𝗻𝘁𝗿𝗲𝗲 𝗔𝘂𝘁𝗵\n"
        f"𝗥𝗲𝘀𝗽𝗼𝗻𝘀𝗲 ➠ <b>{api_response_msg}</b>\n"
        f"𝗕𝗿𝗮𝗻𝗱 ➠ <b>{bin_scheme}</b>\n"
        f"𝗜𝘀𝘀𝘂𝗲𝗿 ➠ <b>{bin_bank}</b>\n"
        f"𝗖𝗼𝘂𝗻𝘁𝗿𝘆 ➠ <b>{bin_country}</b>\n"
        f"𝗨𝘀𝗲𝗿 ➠ {user_display}\n"
        f"𝗗𝗲𝘃 ➠ {dev_link}"
    )

    gif_url = await get_anime_gif()

    try:
        try:
            await proc_msg.delete()
        except Exception:
            pass
        
        await message.reply_animation(
            animation=gif_url,
            caption=final_caption,
            parse_mode="HTML",
            disable_web_page_preview=True
        )
    except (TelegramForbiddenError, TelegramBadRequest) as e:
        logging.warning(f"[B3] Could not send GIF, falling back to text: {e}")
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