from live_emoji import plan_badge, dev_badge
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
from gates.braintree import run_check as run_braintree_check

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# CONFIGURATION
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

GATE_NAME = "Bʀᴀɪɴᴛʀᴇᴇ Aᴜᴛʜ"
GATE_KEY = "b3"
COOLDOWN_SECONDS = 10

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
    name = escape(user_obj.first_name or "User")
    if user_obj.username:
        return f'<a href="https://t.me/{escape(user_obj.username)}">{name}</a>'
    return f'<a href="tg://user?id={user_obj.id}">{name}</a>'

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# COMMAND HANDLER
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

@router.message(F.text.startswith("/b3"))
async def b3_command(message: types.Message):
    if not is_gate_enabled(GATE_KEY):
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
                    f"<tg-emoji emoji-id=\"6255910249362885846\">⚠️</tg-emoji> <b>Aᴄᴛɪᴠᴇ Cᴏᴏʟᴅᴏᴡɴ !</b>\n\n"
                    f"<b>Pʟᴇᴀsᴇ Wᴀɪᴛ <code>{remaining_time}</code> Sᴇᴄᴏɴᴅs Bᴇғᴏʀᴇ Cᴏɴᴛɪɴᴜɪɴɢ.</b>\n\n"
                    f"<tg-emoji emoji-id=\"6136275172283391020\">⭐</tg-emoji> <b>Pᴜʀᴄʜᴀsᴇ Pʀᴇᴍɪᴜᴍ Pʟᴀɴ Fᴏʀ Usᴇ Cᴏᴍᴍᴀɴᴅs Wɪᴛʜᴏᴜᴛ Cᴏᴏʟᴅᴏᴡɴ.</b>",
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
            "<tg-emoji emoji-id=\"4956612582816351459\">❌</tg-emoji> <b>Usage:</b> /b3 <code>cc|mm|yy|cvv</code>\n"
            "Or reply to a message containing card details.",
            parse_mode="HTML"
        )
        return

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

    if len(yy_raw) == 4:
        yy = yy_raw[2:]
    else:
        yy = yy_raw

    formatted_cc = f"{cc}|{mm}|{yy}|{cvv}"

    if not luhn_check(cc):
        await message.reply(
            "<tg-emoji emoji-id=\"4956612582816351459\">❌</tg-emoji> <b>Invalid Card</b>\n"
            "Your card number is incorrect.",
            parse_mode="HTML"
        )
        return

    current_credits = await asyncio.to_thread(get_user_credits, user_id)
    
    if current_credits is None or current_credits < 1:
        await message.reply(
            "<tg-emoji emoji-id=\"4956612582816351459\">❌</tg-emoji> <b>Iɴsᴜғғɪᴄɪᴇɴᴛ Cʀᴇᴅɪᴛs</b>\n\n"
            "Yᴏᴜ Nᴇᴇᴅ Aᴛ Lᴇᴀsᴛ <b>1 Cʀᴇᴅɪᴛ</b> Tᴏ Usᴇ Tʜɪs Gᴀᴛᴇ.\n"
            "Usᴇ /plan Tᴏ Gᴇᴛ Mᴏʀᴇ.",
            parse_mode="HTML"
        )
        return

    plan_name = await get_user_plan_name(user_id)

    escaped_card = escape(formatted_cc)
    proc_msg = await message.reply(
        f"<b>Pʀᴏᴄᴇssɪɴɢ...</b><tg-emoji emoji-id=\"6154603635981423575\">⏳</tg-emoji>\n"
        f"<pre><code>{escaped_card}</code></pre>\n"
        f"<b>Gᴀᴛᴇ ➵ Bʀᴀɪɴᴛʀᴇᴇ Aᴜᴛʜ</b>\n",
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
    check_started = time.time()
    try:
        await asyncio.to_thread(create_user, user_id, user.username)
    except Exception as e:
        logging.error(f"Error ensuring user exists: {e}")

    api_result = {"status": "ERROR", "response": "Unknown Error", "raw_status": "ERROR", "card": formatted_cc}

    # Blocking curl_cffi pipeline with proxy retries -> keep off the event loop.
    try:
        api_result = await asyncio.to_thread(run_braintree_check, formatted_cc)
    except Exception as e:
        logging.error(f"Braintree checker error: {e}")
        api_result["response"] = f"Connection Error: {str(e)}"
        api_result["status"] = "error"
        api_result["raw_status"] = "ERROR"

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

    CUSTOM_LIVE_EMOJI_ID = "4958610528588008305"
    CUSTOM_DEAD_EMOJI_ID = "4956612582816351459"
    
    # Rᴀᴡ field shows the human-readable gateway message returned by the
    # local braintree checker (CheckResult.message).
    api_raw_status = api_result.get("raw_status", "") or str(api_result.get("status", "")).upper()
    api_response_msg = str(api_result.get("response") or api_result.get("message") or "N/A")
    
    is_charged = False
    
    # Determine status based on raw_status field
    if api_raw_status == "APPROVED":
        final_status = f'<b>ᎪꮲꮲꭱƦꮎꮩꭼꭰ</b> <tg-emoji emoji-id=\"{CUSTOM_LIVE_EMOJI_ID}\">✅</tg-emoji>'
        is_charged = True
    elif api_raw_status == "DECLINED":
        final_status = f'<b>Ꭰᴇᴄʟɪɴᴇᴅ</b> <tg-emoji emoji-id=\"{CUSTOM_DEAD_EMOJI_ID}\">❌</tg-emoji>'
    elif api_raw_status == "LIVE":
        final_status = f'<b>ᎪꮲꮲꭱƦꮎꮩꭼꭰ</b> <tg-emoji emoji-id=\"{CUSTOM_LIVE_EMOJI_ID}\">✅</tg-emoji>'
        is_charged = True
    elif api_raw_status == "DEAD":
        final_status = f'<b>Ꭰᴇᴄʟɪɴᴇᴅ</b> <tg-emoji emoji-id=\"{CUSTOM_DEAD_EMOJI_ID}\">❌</tg-emoji>'
    elif api_raw_status == "ERROR":
        final_status = f'<b>Ꭼʀʀᴏʀ</b> ⚠️'
    else:
        # Fallback to status field for compatibility
        api_status = api_result.get("status", "").lower()
        if api_status == "approved":
            final_status = f'<b>ᎪꮲꮲꭱƦꮎꮩꭼꭰ</b> <tg-emoji emoji-id=\"{CUSTOM_LIVE_EMOJI_ID}\">✅</tg-emoji>'
            is_charged = True
        elif api_status == "declined":
            final_status = f'<b>Ꭰᴇᴄʟɪɴᴇᴅ</b> <tg-emoji emoji-id=\"{CUSTOM_DEAD_EMOJI_ID}\">❌</tg-emoji>'
        elif api_status == "live":
            final_status = f'<b>ᎪꮲꮲꭱƦꮎꮩꭼꭰ</b> <tg-emoji emoji-id=\"{CUSTOM_LIVE_EMOJI_ID}\">✅</tg-emoji>'
            is_charged = True
        elif api_status == "dead":
            final_status = f'<b>Ꭰᴇᴄʟɪɴᴇᴅ</b> <tg-emoji emoji-id=\"{CUSTOM_DEAD_EMOJI_ID}\">❌</tg-emoji>'
        elif api_status == "error":
            final_status = f'<b>Ꭼʀʀᴏʀ</b> ⚠️'
        else:
            final_status = "<b>Ꭲɪᴍᴇᴏᴜᴛ</b> ⚠️"

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

    user_link = build_user_link(user)
    dev_link = dev_badge()
    user_display = f"{user_link} {plan_badge(plan_name)}"
    
    elapsed = time.time() - check_started
    final_caption = (
        f'<b><a href="https://t.me/broken_wiz">[⌭]</a> Sᴛᴀᴛᴜs ➵ {final_status}</b>\n'
        f"<tg-emoji emoji-id=\"5920055227133725805\">💳</tg-emoji>\n"
        f"⤷ <code>{formatted_cc}</code>\n"
        f"━━━━━━━━━━━\n"
        f'<b><a href="https://t.me/broken_wiz">⬢</a> Gᴀᴛᴇ ➵ {GATE_NAME}</b>\n'
        f'<b><a href="https://t.me/broken_wiz">⬡</a> Rᴀᴡ ➵ {api_response_msg}</b>\n'
        f"━━━━━━━━━━━\n"
        f"<b>Tʏᴘᴇ ➵</b> <code>[ {type} ]</code>\n"
        f"<b>Iɴꜰᴏ ➵</b> <code>{bin_scheme} - {bin_bank} - {bin_country}</code>\n"
        f"━━━━━━━━━━━\n"
        f"<tg-emoji emoji-id=\"5440621591387980068\">🔜</tg-emoji> <b>➵ {elapsed:.2f}s</b>\n"
        f"<tg-emoji emoji-id=\"6028240037366207289\">👤</tg-emoji> <b>➵ {user_display}</b>\n"
        f"<tg-emoji emoji-id=\"5429615084856969948\">🏴‍☠️</tg-emoji> <b>➵ {dev_link}</b>"
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
