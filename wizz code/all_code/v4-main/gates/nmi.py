from live_emoji import plan_badge, dev_badge
import asyncio
import re
import logging
import psycopg2.extras
import time
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
from database import is_gate_enabled, get_user_credits, update_credits, get_db_connection
from bin import get_bin_info
from sub import get_premium_status
from gates.nmidonor import process_nmi_card

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
# CONFIGURATION
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
user_last_command_time = {}

# Router for this module
router = Router()

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
        print("[DB] NMI Stats columns checked/created.")
    except Exception as e:
        print(f"[DB] Error checking stats columns: {e}")

# Run check on import
ensure_stats_columns()

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# HELPERS
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

async def update_user_stats(user_id, is_charged):
    """
    Increments cc_checked and optionally cc_charged in the database.
    Wrapped in asyncio.to_thread for non-blocking execution.
    """
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
    """Fetches the specific plan name from receipts if premium, else Trial."""
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
    """Builds a clickable user mention link."""
    name = escape(user_obj.first_name or "User")
    if user_obj.username:
        return f'<a href="https://t.me/{escape(user_obj.username)}">{name}</a>'
    return f'<a href="tg://user?id={user_obj.id}">{name}</a>'

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# COMMAND HANDLER
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

@router.message(F.text.startswith("/nmi"))
async def nmi_command(message: types.Message):
    # 1. GATE CHECK
    if not await asyncio.to_thread(is_gate_enabled, "nmi"):
        await message.reply(
            "🚧 <b>𝗡𝗠𝗜 𝟭$ 𝗚𝗮𝘁𝗲 𝗶𝘀 𝘂𝗻𝗱𝗲𝗿 𝗺𝗮𝗶𝗻𝘁𝗲𝗻𝗮𝗻𝗰𝗲.</b>\n"
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
                    f"<b>Pʟᴇᴀsᴇ Wᴀɪᴛ <code>{remaining_time}</code> Sᴇᴄᴏɴᴅs Bᴇғᴏʀᴇ Cᴏɴᴛɪɴᴜɪɴɢ.</b>\n\n"
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
    elif message.reply_to_message:
        raw_text = message.reply_to_message.text or message.reply_to_message.caption
        
    if not raw_text:
        await message.reply(
            "<tg-emoji emoji-id=\"4956612582816351459\">❌</tg-emoji> <b>Usage:</b> /nmi <code>cc|mm|yy|cvv</code>\n"
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
    if current_credits is None or current_credits <= 0:
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
        f"<b>Gᴀᴛᴇ ➺ NMI 1 USD</b>\n",
        parse_mode="HTML"
    )

    # 9. Execute Background Task
    asyncio.create_task(
        process_nmi_check(
            message, proc_msg, user, user_id, formatted_cc, cc, plan_name
        )
    )

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# BACKGROUND PROCESSOR
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

async def process_nmi_check(message, proc_msg, user, user_id, formatted_cc, cc, plan_name):
    """
    Handles the NMI processing via external function, 
    DB updates, and final message editing.
    """
    
    # A. Call the synchronous NMI processor in a separate thread
    check_started = time.time()
    try:
        result = await asyncio.to_thread(process_nmi_card, formatted_cc)
    except Exception as e:
        logging.error(f"NMI processing error: {e}")
        result = {
            'status': 'ERROR',
            'message': 'Internal Processing Error',
            'card': formatted_cc
        }
    
    if not result:
        result = {
            'status': 'ERROR',
            'message': 'Internal Processing Error',
            'card': formatted_cc
        }

    # B. Bin Lookup
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

    # C. Determine Final Status
    status_raw = result.get("status", "").lower()
    res_code = result.get("message", "Unknown Error")
    
    # Remove the "Status | " prefix (e.g., "Declined | ") from the response message
    # so it doesn't show up in the Response field of the final message.
    if " | " in res_code:
        res_code = res_code.split(" | ", 1)[1]
    
    is_charged = False
    
    # Custom Emoji IDs
    CUSTOM_CHARGED_EMOJI_ID = "4956719506027185156"
    CUSTOM_DECLINED_EMOJI_ID = "4956612582816351459"

    if status_raw == "charged":
        # Using Custom Telegram Emoji for CHARGED
        final_status = f'<b>ᏟꮋꭺꭱƦᏽꭼꭰ</b> <tg-emoji emoji-id="{CUSTOM_CHARGED_EMOJI_ID}">❌</tg-emoji>'
        is_charged = True
    elif status_raw == "declined":
        # Using Custom Telegram Emoji for DECLINED
        final_status = f'<b>Ꭰᴇᴄʟɪɴᴇᴅ</b> <tg-emoji emoji-id="{CUSTOM_DECLINED_EMOJI_ID}">❌</tg-emoji>'
    else:
        final_status = "<b>Ꭼʀʀᴏʀ</b> ⚠️"

    # D. SPECIFIC CREDIT DEDUCTION LOGIC
    credits_to_deduct = 0
    
    if status_raw == 'charged':
        credits_to_deduct = 2
    elif status_raw == 'declined':
        credits_to_deduct = 1
    # Else (Error/Timeout) -> 0 credits

    # Fetch fresh balance and deduct
    if credits_to_deduct > 0:
        current_balance = await asyncio.to_thread(get_user_credits, user_id)
        new_balance = current_balance - credits_to_deduct
        if new_balance < 0: new_balance = 0 
        await asyncio.to_thread(update_credits, user_id, new_balance)

    # E. UPDATE STATS
    await update_user_stats(user_id, is_charged)

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
        f'<b><a href="https://t.me/broken_wiz">⬢</a> Gᴀᴛᴇ ➵ NMI 1 USD</b>\n'
        f'<b><a href="https://t.me/broken_wiz">⬡</a> Rᴀᴡ ➵ {res_code}</b>\n'
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
        logging.warning(f"[NMI] Could not send GIF, falling back to text: {e}")
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
