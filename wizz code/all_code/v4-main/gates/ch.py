from live_emoji import plan_badge, dev_badge
import asyncio
import re
import logging
import time
import random
import aiohttp
import psycopg2.extras
from html import escape

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# AIogram Imports
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
from aiogram import types, F, Router
from aiogram.exceptions import TelegramForbiddenError, TelegramBadRequest

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# LOCAL IMPORTS
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
from database import is_gate_enabled, get_user_credits, update_credits, get_db_connection, update_user_stats
from bin import get_bin_info
from sub import get_premium_status
from gates.chase import run_check

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# CONFIGURATION
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

GATE_NAME = "Chase Auth"
GATE_KEY = "ch"
COOLDOWN_SECONDS = 10

user_last_command_time = {}
router = Router()

# Strong references to in-flight background checks (see step 9 below).
_background_tasks = set()

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# GIF REACTIONS (Same as chk.py)
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
# HELPERS
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

async def get_user_plan_name(user_id):
    """Fetches the specific plan name from receipts if premium, else FREE."""
    is_premium, _ = get_premium_status(user_id)

    if is_premium:
        try:
            def _sync_fetch():
                conn = get_db_connection()
                cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
                cursor.execute(
                    "SELECT plan FROM receipts WHERE user_id = %s ORDER BY purchased_on DESC LIMIT 1",
                    (user_id,)
                )
                row = cursor.fetchone()
                conn.close()
                return row['plan'].upper() if row else "PREMIUM"

            return await asyncio.to_thread(_sync_fetch)
        except Exception as e:
            logging.error(f"Error fetching plan name: {e}")
        return "PREMIUM"
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

def _display(value, default: str = "N/A") -> str:
    """
    Coerce an API/DB value into a safe display string.

    get_bin_info() maps JSON fields with data.get(...), so a null in the
    response yields None rather than a missing key -- and escape(None) raises.
    """
    if value is None:
        return default
    text = str(value).strip()
    return text or default

async def run_chase_check(formatted_cc: str) -> dict:
    """Runs the blocking Chase pipeline off the event loop."""
    return await asyncio.to_thread(run_check, formatted_cc)

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# COMMAND HANDLER
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

@router.message(F.text.startswith("/ch ") | (F.text == "/ch"))
async def ch_command(message: types.Message):
    # 1. GATE CHECK
    if not await asyncio.to_thread(is_gate_enabled, GATE_KEY):
        await message.reply(
            "🚧 <b>𝗦𝘁𝗿𝗶𝗽𝗲 𝗔𝘂𝘁𝗵 𝗚𝗮𝘁𝗲 𝗶𝘀 𝘂𝗻𝗱𝗲𝗿 𝗺𝗮𝗶𝗻𝘁𝗲𝗻𝗮𝗻𝗰𝗲.</b>\n"
            "𝗔𝗻𝗱 𝘄𝗶𝗹𝗹 𝗯𝗲 𝗳𝗶𝘅𝗲𝗱 𝘀𝗼𝗼𝗻.",
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
            if elapsed < COOLDOWN_SECONDS:
                remaining_time = round(COOLDOWN_SECONDS - elapsed, 1)
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
            "<tg-emoji emoji-id=\"4956612582816351459\">❌</tg-emoji> <b>Usage:</b> /ch <code>cc|mm|yy|cvv</code>\n"
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
        f"<b>Gᴀᴛᴇ ➵ {GATE_NAME}</b>\n",
        parse_mode="HTML"
    )

    # 9. Execute Background Task
    # Keep a strong reference and consume the result, otherwise a late failure
    # surfaces as "Task exception was never retrieved" with no visible result.
    task = asyncio.create_task(
        process_ch_check(
            message, proc_msg, user, user_id, formatted_cc, cc, plan_name
        )
    )
    _background_tasks.add(task)
    task.add_done_callback(_background_tasks.discard)
    task.add_done_callback(_log_task_failure)

def _log_task_failure(task):
    """Retrieves any exception from a finished background task so asyncio
    doesn't report it as never retrieved, and logs it with a traceback."""
    if task.cancelled():
        return
    exc = task.exception()
    if exc is not None:
        logging.error(f"[CH] Background task failed: {exc!r}", exc_info=exc)

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# BACKGROUND PROCESSOR
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

async def process_ch_check(message, proc_msg, user, user_id, formatted_cc, cc, plan_name):
    """Guaranteed-delivery wrapper: any unexpected error still notifies the
    user instead of leaving the processing message stuck."""
    try:
        await _run_ch_check(message, proc_msg, user, user_id, formatted_cc, cc, plan_name)
    except Exception as e:
        logging.error(f"[CH] Unhandled error in process_ch_check: {e!r}", exc_info=e)
        try:
            await message.reply(
                "<tg-emoji emoji-id=\"4956612582816351459\">❌</tg-emoji> <b>Unexpected Error</b>\n\n"
                "The check could not be completed. Please try again.",
                parse_mode="HTML"
            )
        except Exception:
            pass

async def _run_ch_check(message, proc_msg, user, user_id, formatted_cc, cc, plan_name):
    """Handles the Chase check, DB updates, and final message with GIF."""

    # A. CALL CHASE PIPELINE
    check_started = time.time()
    try:
        api_result = await run_chase_check(formatted_cc)
    except Exception as e:
        logging.error(f"CH run_check error: {e}")
        api_result = {"status": "ERROR", "response": str(e), "approved": False}
    logging.info(f"CH Result for {cc[:6]}: {api_result.get('status')} - {api_result.get('response')}")

    # B. Bin Lookup
    try:
        bin_info = await get_bin_info(cc[:6])
    except Exception:
        bin_info = {}

    if not isinstance(bin_info, dict):
        bin_info = {}

    bin_scheme = _display(bin_info.get("scheme"))
    bin_bank = _display(bin_info.get("bank"))
    country_name = _display(bin_info.get("country"))
    country_flag = _display(bin_info.get("country_emoji"), "")
    bin_country = f"{country_flag} {country_name}".strip() if country_flag else country_name
    bin_type = _display(bin_info.get("type"))

    # C. Determine Final Status
    status_raw = str(api_result.get("status", "ERROR")).upper()

    # Raw line shows the human-readable Chase detail; fall back to the generic
    # response when detail is empty (e.g. transport-level errors).
    api_response_msg = str(api_result.get("detail") or api_result.get("response") or "N/A")
    chase_code = api_result.get("code")

    is_approved = bool(api_result.get("approved")) or status_raw == "APPROVED"

    # Custom Emoji IDs
    CUSTOM_DECLINED_EMOJI_ID = "4956612582816351459"
    CUSTOM_APPROVED_EMOJI_ID = "4958610528588008305"

    if is_approved:
        final_status = f'<b>ᎪꮲꮲꭱƦꮎꮩꭼꭰ</b> <tg-emoji emoji-id="{CUSTOM_APPROVED_EMOJI_ID}">✅</tg-emoji>'
    elif status_raw == "DECLINED":
        final_status = f'<b>Ꭰᴇᴄʟɪɴᴇᴅ</b> <tg-emoji emoji-id="{CUSTOM_DECLINED_EMOJI_ID}">❌</tg-emoji>'
    else:
        final_status = "<b>Ꭼʀʀᴏʀ</b> / Ꭲɪᴍᴇᴏᴜᴛ ⚠️"

    # Append the Chase response code only when detail doesn't already carry it
    if chase_code and chase_code not in api_response_msg:
        api_response_msg = f"{api_response_msg} [{chase_code}]"

    # D. CREDIT DEDUCTION (only on approval, same rule as /chk)
    if is_approved:
        current_balance = await asyncio.to_thread(get_user_credits, user_id)
        new_balance = max(0, (current_balance or 0) - 1)
        await asyncio.to_thread(update_credits, user_id, new_balance)

    # E. UPDATE STATS (shared cc_checked / cc_charged counters)
    try:
        await asyncio.to_thread(update_user_stats, user_id, is_approved)
    except Exception as e:
        logging.error(f"Failed to update stats: {e}")

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
        f'<b><a href="https://t.me/broken_wiz">⬢</a> Gᴀᴛᴇ ➵ {GATE_NAME}</b>\n'
        f'<b><a href="https://t.me/broken_wiz">⬡</a> Rᴀᴡ ➵ {escape(api_response_msg)}</b>\n'
        f"━━━━━━━━━━━\n"
        f"<b>Tʏᴘᴇ ➵</b> <code>[ {escape(bin_type)} ]</code>\n"
        f"<b>Iɴꜰᴏ ➵</b> <code>{escape(bin_scheme)} - {escape(bin_bank)} - {escape(bin_country)}</code>\n"
        f"━━━━━━━━━━━\n"
        f"<tg-emoji emoji-id=\"5440621591387980068\">🔜</tg-emoji> <b>➵ {elapsed:.2f}s</b>\n"
        f"<tg-emoji emoji-id=\"6028240037366207289\">👤</tg-emoji> <b>➵ {user_display}</b>\n"
        f"<tg-emoji emoji-id=\"5429615084856969948\">🏴‍☠️</tg-emoji> <b>➵ {dev_link}</b>"
    )

    # G. FETCH ANIME GIF
    gif_url = await get_anime_gif()

    # H. Send as Animation (GIF) with Caption
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
        logging.warning(f"[CH] Could not send GIF, falling back to text: {e}")
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
