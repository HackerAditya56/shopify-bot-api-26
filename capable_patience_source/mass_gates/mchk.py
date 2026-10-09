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
from io import BytesIO, RawIOBase

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
from database import is_gate_enabled, get_user_credits, update_credits, update_user_stats, get_db_connection, deduct_credits_atomic, is_owner_user
from bin import get_bin_info
from sub import get_premium_status
from mass_gates._tg_helpers import send_hit, send_message_safe

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# STRIPE AUTH IMPORT (Handles its own proxy internally)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
from mass_gates.stripeauth import process_stripe_auth

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# CONFIGURATION & URLS
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

HIT_LOG_GROUP_ID = -1004453592223
EXTRA_CHARGED_GROUP_ID = -1004453592223
BUTTON_LOCK_SECONDS = 30

CUSTOM_CHARGED_EMOJI_ID = "5359719332542718652"
CUSTOM_APPROVED_EMOJI_ID = "6044254523009012231"
CUSTOM_DECLINED_EMOJI_ID = "5893081007153746175"

#BTN_CHARGED_EMOJI_ID = "5465465194056525619"
#BTN_DEAD_EMOJI_ID = "5042112436648281096"
#BTN_LIVE_EMOJI_ID = "5039793437776282663"
#BTN_STOP_EMOJI_ID = "6179444193518162239"
#BTN_ALL_EMOJI_ID = "4956324463525233747"

MCHK_SESSIONS = {}
MCHK_SESSION_LOCKS = {}

MCHK_PENDING = {}

class MchkSelCallback(CallbackData, prefix="mchksel"):
    sel_id: str
    action: str


def _selection_text(charged: bool, approved: bool, total: int) -> str:
    charged_s = "✅ 𝗢𝗡" if charged else "❌ 𝗢𝗙𝗙"
    approved_s = "✅ 𝗢𝗡" if approved else "❌ 𝗢𝗙𝗙"
    return (
        f"<b><tg-emoji emoji-id=\"5361734213370396027\">⚙️</tg-emoji> 𝐒𝐄𝐋𝐄𝐂𝐓𝐈𝐎𝐍</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━━\n"
        f"<b>𝐓𝐨𝐭𝐚𝐥 𝐂𝐚𝐫𝐝𝐬 ➠</b> <code>{total}</code>\n"
        f"━━━━━━━━━━━━━━━━━━━━━\n"
        f"<tg-emoji emoji-id=\"{CUSTOM_CHARGED_EMOJI_ID}\">💎</tg-emoji> <b>𝐂𝐡𝐚𝐫𝐠𝐞𝐝 ➠</b> <b>{charged_s}</b>\n"
        f"<tg-emoji emoji-id=\"{CUSTOM_APPROVED_EMOJI_ID}\">✅</tg-emoji> <b>𝐀𝐩𝐩𝐫𝐨𝐯𝐞𝐝 ➠</b> <b>{approved_s}</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━━\n"
        f"<i>Tap the buttons to toggle what is sent to your DM, then press 𝐒𝐭𝐚𝐫𝐭.</i>"
    )


def _selection_keyboard(sel_id: str, charged: bool, approved: bool) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="𝐂𝐡𝐚𝐫𝐠𝐞𝐝", callback_data=MchkSelCallback(sel_id=sel_id, action="charged").pack()),
            InlineKeyboardButton(text="𝐀𝐩𝐩𝐫𝐨𝐯𝐞𝐝", callback_data=MchkSelCallback(sel_id=sel_id, action="approved").pack()),
        ],
        [
            InlineKeyboardButton(text="𝐒𝐭𝐚𝐫𝐭", callback_data=MchkSelCallback(sel_id=sel_id, action="start").pack()),
        ],
    ])


# ── Session GC: prune stale sessions every 10 min to prevent memory leaks ─────
import threading as _mchk_threading
import time as _mchk_time

_MCHK_SESSION_MAX_AGE = 3600

def _cleanup_mchk_sessions():
    cutoff = _mchk_time.time() - _MCHK_SESSION_MAX_AGE
    dead = [sid for sid, s in list(MCHK_SESSIONS.items())
            if s.get('status') in ('𝗦𝘂𝗺𝗺𝗮𝗿𝘆', '𝗦𝘁𝗼𝗽𝗽𝗲𝗱') and s.get('start_time', 0) < cutoff]
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

OWNER_ID = 8462705169

router = Router()

async def _safe_answer(callback: types.CallbackQuery, text: str = "", **kw):
    """Answer a callback query without ever raising (expired queries raise 400)."""
    try:
        await callback.answer(text, **kw)
    except Exception:
        pass




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
    seen = set()
    for pattern in patterns:
        matches = re.findall(pattern, text)
        for match in matches:
            if len(match) == 4:
                card_number, month, year, cvv = match
                month = month.zfill(2)
                if len(year) == 4:
                    year = year[2:]
                card_string = f"{card_number}|{month}|{year}|{cvv}"
                if card_string not in seen:
                    seen.add(card_string)
                    cards.append(card_string)
    return cards


# ── Chunked file download (2MB chunks → low memory, fast) ──────────────────
_CHUNK_SIZE = 2 * 1024 * 1024


class _CardChunkSink(RawIOBase):
    """Streams a Telegram file download and extracts cards per ~2MB chunk."""

    def __init__(self, chunk_size=_CHUNK_SIZE):
        self._buf = b""
        self._chunk = chunk_size
        self.carry = ""
        self.cards = []
        self._seen = set()

    def writable(self):
        return True

    def seekable(self):
        return False

    def write(self, b):
        self._buf += bytes(b)
        while len(self._buf) >= self._chunk:
            self._process(self._buf[:self._chunk])
            self._buf = self._buf[self._chunk:]
        return len(b)

    def flush(self):
        pass

    def seek(self, offset, whence=0):
        return offset

    def _process(self, raw):
        text = self.carry + raw.decode("utf-8", errors="ignore")
        for c in extract_cards_from_text(text):
            if c not in self._seen:
                self._seen.add(c)
                self.cards.append(c)
        self.carry = text[-96:]

    def finalize(self):
        if self._buf:
            self._process(self._buf)
            self._buf = b""
        for c in extract_cards_from_text(self.carry):
            if c not in self._seen:
                self._seen.add(c)
                self.cards.append(c)
        self.carry = ""
        return self.cards


async def download_and_extract_chunked(bot, document) -> List[str]:
    """Download a document and extract cards in ~2MB chunks (low memory)."""
    file_info = await bot.get_file(document.file_id)
    sink = _CardChunkSink()
    # download_file() takes a file_PATH (download() takes a file_id).
    # Higher timeout: Telegram CDN can be slow for 10-20MB files.
    await bot.download_file(file_info.file_path, destination=sink, seek=False, timeout=120)
    return sink.finalize()

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
    return session.get('status') == "𝗦𝘁𝗼𝗽𝗽𝗲𝗱"

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
    return f"{user_obj.first_name} [{plan_name}]"

def build_user_link(user_obj) -> str:
    name = user_obj.first_name or "User"
    if user_obj.username:
        return f'<a href="https://t.me/{user_obj.username}">{name}</a>'
    return f'<a href="tg://user?id={user_obj.id}">{name}</a>'

async def get_anime_gif():
    reaction = random.choice(REACTIONS)
    api_url = f"https://api.otakugifs.xyz/gif?reaction={reaction}"
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(api_url, timeout=3) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    return data.get("url")
    except Exception as e:
        logging.error(f"Error fetching anime gif: {e}")
    return "https://media.giphy.com/media/v1.Y2lkPTc5MGI3NjExM3Z6eXF6eXF6eXF6eXF6eXF6eXF6eXF6SZlcD12MV9pbnRlcm5hbF9naWZfYnlfaWQmY3Q9Zw/LdOyjZ7h5xS3yCjQ8I/giphy.gif"

async def get_user_plan_name(user_id):
    if user_id == OWNER_ID:
        return "OWNER"
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
        return "TRIAL"

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
# HIT NOTIFICATION FUNCTIONS
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

async def send_hit_log_to_group(bot: Bot, response_msg, user_obj, plan_name, hit_type):
    user_link = build_user_link(user_obj)

    if hit_type == "CHARGED":
        header = f"𝗛𝗜𝗧 ➠ ᏟꮋꭺꭱƦᏽꭼꭰ <tg-emoji emoji-id=\"{CUSTOM_CHARGED_EMOJI_ID}\">💎</tg-emoji>"
    else:
        header = f"𝗛𝗜𝗧 ➠ ᎪꮲꮲꭱƦꮎꮩꭼꭰ <tg-emoji emoji-id=\"{CUSTOM_APPROVED_EMOJI_ID}\">✅</tg-emoji>"

    caption = (
        f"{header}\n"
        f"𝗚𝗮𝘁𝗲𝘄𝗮𝘆 ➠ 𝗦𝘁𝗿𝗶𝗽𝗲 𝗔𝘂𝘁𝗵\n"
        f"𝗥𝗲𝘀𝗽𝗼𝗻𝘀𝗲 ➠ <b>{response_msg}</b>\n"
        f"𝗨𝘀𝗲𝗿 ➠ <b>{user_link} [{plan_name}]</b>\n"
    )
    await send_message_safe(bot, HIT_LOG_GROUP_ID, caption, parse_mode="HTML",
                             disable_web_page_preview=True)

async def send_user_hit_notification(bot: Bot, session, cc_formatted, cc_num, response_msg, user_obj, plan_name, hit_type):
    """
    Always sends the hit notification to the user's DM (private chat).
    CHARGED cards are additionally broadcast to EXTRA_CHARGED_GROUP_ID.
    """
    try:
        try:
            bin_data = await get_bin_info(cc_num[:6])
        except:
            bin_data = {}

        bin_scheme = bin_data.get("scheme", "N/A")
        bin_bank = bin_data.get("bank", "N/A")
        country_name = bin_data.get("country", "N/A")
        country_flag = bin_data.get("country_emoji", "")
        bin_country = f"{country_name} {country_flag}" if country_flag else country_name

        gif_url = await get_anime_gif()
        user_link = build_user_link(user_obj)
        dev_link = '<a href="https://t.me/Enchanted_linux_0x">Enchanted_linux_0x</a>'
        user_display = f"{user_link} <b>[{plan_name}]</b>"

        if hit_type == "CHARGED":
            status_text = f"ᏟꮋꭺꭱƦᏽꭼꭰ <tg-emoji emoji-id=\"{CUSTOM_CHARGED_EMOJI_ID}\">💎</tg-emoji>"
        else:
            status_text = f"ᎪꮲꮲꭱƦꮎꮩꭼꭰ <tg-emoji emoji-id=\"{CUSTOM_APPROVED_EMOJI_ID}\">✅</tg-emoji>"

        caption = (
            f"𝐒𝐭𝐚𝐭𝐮𝐬 ➠ {status_text}\n"
            f"𝐂𝐚𝐫𝐝 ➠ <code>{cc_formatted}</code>\n"
            f"𝐆𝐚𝐭𝐞𝐰𝐚𝐲 ➠ 𝐒𝐭𝐫𝐢𝐩𝐞 𝐀𝐮𝐭𝐡\n"
            f"𝐑𝐞𝐬𝐩𝐨𝐧𝐬𝐞 ➠ <b>{response_msg}</b>\n"
            f"𝐁𝐫𝐚𝐧𝐝 ➠ <b>{bin_scheme}</b>\n"
            f"𝐁𝐚𝐧𝐤 ➠ <b>{bin_bank}</b>\n"
            f"𝐂𝐨𝐮𝐧𝐭𝐫𝐲 ➠ <b>{bin_country}</b>\n"
            f"𝐔𝐬𝐞𝐫 ➠ {user_display}\n"
            f"𝐃𝐞𝐯 ➠ {dev_link}"
        )

        await send_hit(bot, user_obj.id, caption, gif_url)

        if hit_type == "CHARGED":
            await send_hit(bot, EXTRA_CHARGED_GROUP_ID, caption, gif_url)

    except Exception as e:
        logging.error(f"Error sending user HIT message: {e}")

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# RESULT FILE GENERATION
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def generate_result_file(session: dict, result_type: str, user_obj, plan_name: str) -> Tuple[BytesIO, str, int]:
    cards_list = []

    if result_type == "charged":
        cards_list = session.get('charged_cards', [])
        type_label = "𝗖𝗵𝗮𝗿𝗴𝗲𝗱"
        type_emoji = "💎"
    elif result_type == "live":
        cards_list = session.get('approved_cards', [])
        type_label = "𝗟𝗶𝘃𝗲"
        type_emoji = "✅"
    elif result_type == "dead":
        cards_list = session.get('dead_cards', [])
        type_label = "𝗗𝗲𝗮𝗱"
        type_emoji = "❌"
    else:
        cards_list = (
            session.get('charged_cards', []) +
            session.get('approved_cards', []) +
            session.get('dead_cards', []) +
            session.get('error_cards', [])
        )
        type_label = "𝗔𝗹𝗹"
        type_emoji = "📁"

    total_count = len(cards_list)
    user_display = get_user_display(user_obj, plan_name)

    lines = []
    lines.append("┏━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┓")
    lines.append("┃        𝑪𝑯𝑶𝑹 𝑷𝑨𝑳𝑻𝑨𝑵         ┃")
    lines.append("┗━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┛")
    lines.append("")
    lines.append(f"𝗥𝗲𝘀𝘂𝗹𝘁 𝗧𝘆𝗽𝗲 ➠ {type_label} {type_emoji}")
    lines.append(f"𝗧𝗼𝘁𝗮𝗹 𝗖𝗮𝗿𝗱𝘀 ➠ {total_count}")
    lines.append(f"𝗚𝗮𝘁𝗲𝘄𝗮𝘆 ➠ 𝗦𝘁𝗿𝗶𝗽𝗲 𝗔𝘂𝘁𝗵")
    lines.append(f"𝗣𝗼𝘄𝗲𝗿𝗲𝗱 𝗕𝘆 ➠ 𝑪𝑯𝑶𝑹 𝑷𝑨𝑳𝑻𝑨𝑵")
    lines.append("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    lines.append("")

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
                status = "𝗖𝗵𝗮𝗿𝗴𝗲𝗱 💎"
            elif "insufficient" in response.lower() or "APPROVED" in response.upper():
                status = "𝗔𝗣𝗣𝗥𝗢𝗩𝗘𝗗 ✅"
            elif "ERROR" in response.upper() or "TIMEOUT" in response.upper() or "error" in response.lower():
                status = "𝗘𝗥𝗥𝗢𝗥 ⚠️"
            else:
                status = "𝗗𝗘𝗖𝗟𝗜𝗡𝗘𝗗 ❌"

            lines.append(f"𝐒𝐭𝐚𝐭𝐮𝐬 ➠ {status}")
            lines.append(f"𝐂𝐚𝐫𝐝 ➠ {cc}")
            lines.append(f"𝐆𝐚𝐭𝐞𝐰𝐚𝐲 ➠ 𝐒𝐭𝐫𝐢𝐩𝐞 𝐀𝐮𝐭𝐡")
            lines.append(f"𝐑𝐞𝐬𝐩𝐨𝐧𝐬𝐞 ➠ {response}")
            lines.append(f"𝐁𝐫𝐚𝐧𝐝 ➠ {scheme}")
            lines.append(f"𝐁𝐚𝐧𝐤 ➠ {bank}")
            lines.append(f"𝐂𝐨𝐮𝐧𝐭𝐫𝐲 ➠ {country_display}")
            lines.append(f"𝐔𝐬𝐞𝐫 ➠ {user_display}")
            lines.append(f"𝐃𝐞𝐯 ➠ Enchanted_linux_0x")
            lines.append("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
            lines.append("")

    content = "\n".join(lines)
    file_buffer = BytesIO(content.encode('utf-8'))
    file_buffer.seek(0)

    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    type_map = {"charged": "CHARGED", "live": "LIVE", "dead": "DEAD", "all": "ALL"}
    filename = f"CHORPALTAN_STRIPEAUTH_{type_map.get(result_type, 'ALL')}_{timestamp}.txt"

    return file_buffer, filename, total_count

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# BUTTONS & PROGRESS MESSAGE
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def get_result_buttons(session_id: str, is_running: bool = True) -> dict:
    session = MCHK_SESSIONS.get(session_id, {})
    approved_count = session.get('approved', 0)
    dead_count = session.get('dead', 0)
    charged_count = session.get('charged', 0)
    error_count = session.get('errors', 0)
    all_count = charged_count + approved_count + dead_count + error_count

    buttons = []
    buttons.append([
        {
            "text": f"Lɪᴠᴇ ({approved_count})",
            "callback_data": MchkResultCallback(session_id=session_id, result_type="live").pack(),
            "style": "success",
            #"icon_custom_emoji_id": BTN_LIVE_EMOJI_ID
        },
        {
            "text": f"Dᴇᴀᴅ ({dead_count})",
            "callback_data": MchkResultCallback(session_id=session_id, result_type="dead").pack(),
            "style": "danger",
            #"icon_custom_emoji_id": BTN_DEAD_EMOJI_ID
        }
    ])
    buttons.append([
        {
            "text": f"Cʜᴀʀɢᴇᴅ ({charged_count})",
            "callback_data": MchkResultCallback(session_id=session_id, result_type="charged").pack(),
            "style": "primary",
            #"icon_custom_emoji_id": BTN_CHARGED_EMOJI_ID
        },
        {
            "text": f"Aʟʟ ({all_count})",
            "callback_data": MchkResultCallback(session_id=session_id, result_type="all").pack(),
            "style": "primary",
            #"icon_custom_emoji_id": BTN_ALL_EMOJI_ID
        }
    ])

    if is_running:
        buttons.append([
            {
                "text": "Sᴛᴏᴘ Cʜᴇᴄᴋɪɴɢ",
                "callback_data": MchkStopCallback(session_id=session_id).pack(),
                "style": "danger",
                #"icon_custom_emoji_id": BTN_STOP_EMOJI_ID
            }
        ])

    return {"inline_keyboard": buttons}

async def update_progress_message(bot: Bot, session_id):
    session = MCHK_SESSIONS.get(session_id)
    if not session:
        return

    current_time = time.time()
    last_update = session.get('last_update_time', 0)
    is_finished = session['status'] == "𝗦𝘂𝗺𝗺𝗮𝗿𝘆"
    is_stopped = session['status'] == "𝗦𝘁𝗼𝗽𝗽𝗲𝗱"

    if not is_finished and not is_stopped and (current_time - last_update) < 1.0:
        return

    elapsed = current_time - session['start_time']
    minutes = int(elapsed // 60)
    seconds = int(elapsed % 60)
    elapsed_str = f"{minutes}m {seconds}s" if minutes > 0 else f"{seconds}s"

    status_icon = "<tg-emoji emoji-id=\"5258077393884562645\">⬜️</tg-emoji>" if session['status'] == "𝗖𝗵𝗲𝗰𝗸𝗶𝗻𝗴..." else ("<tg-emoji emoji-id=\"5247149163132493357\">⛔️</tg-emoji>" if session['status'] == "𝗦𝘁𝗼𝗽𝗽𝗲𝗱" else "<tg-emoji emoji-id=\"6253754970349243649\">✨</tg-emoji>")
    status_text = session['status']
    if status_text == "𝗖𝗵𝗲𝗰𝗸𝗶𝗻𝗴...":
        status_text = f"<b>{status_text}</b>"
    elif status_text in ("𝗦𝘁𝗼𝗽𝗽𝗲𝗱", "𝗦𝘂𝗺𝗺𝗮𝗿𝘆"):
        status_text = f"<b>{status_text}</b>"

    text = (
        f"<a href='https://t.me/Enchanted_linux_0x'>✧</a> <b>𝐒𝐭𝐚𝐭𝐮𝐬 ➠</b> {status_text} {status_icon}\n"
        f"<a href='https://t.me/Enchanted_linux_0x'>✧</a> <b>𝐒𝐞𝐬𝐬𝐢𝐨𝐧 𝐈𝐃 ➠</b> <code>{session_id}</code>\n"        
        f"<a href='https://t.me/Enchanted_linux_0x'>✧</a> <b>𝐓𝐨𝐭𝐚𝐥 ➠</b> <code>{session['checked']}/{session['total']}</code>\n"
        f"     <tg-emoji emoji-id=\"{CUSTOM_CHARGED_EMOJI_ID}\">💎</tg-emoji> <b>𝐂𝐡𝐚𝐫𝐠𝐞𝐝 ➠</b> <b>{session['charged']} </b>\n"
        f"     <tg-emoji emoji-id=\"{CUSTOM_APPROVED_EMOJI_ID}\">✅</tg-emoji> <b>𝐀𝐩𝐩𝐫𝐨𝐯𝐞𝐝 ➠</b> <b>{session['approved']} </b>\n"
        f"     <tg-emoji emoji-id=\"{CUSTOM_DECLINED_EMOJI_ID}\">❌</tg-emoji> <b>𝐃𝐞𝐜𝐥𝐢𝐧𝐞𝐝 ➠</b> <b>{session['dead']} </b>\n"
        f"<a href='https://t.me/Enchanted_linux_0x'>π</a> <b>𝐆𝐚𝐭𝐞𝐰𝐚𝐲 ➠</b> 𝐒𝐭𝐫𝐢𝐩𝐞 𝐀𝐮𝐭𝐡\n"
        f"     <tg-emoji emoji-id=\"6255910249362885846\">⚠️</tg-emoji> <b>𝐄𝐫𝐫𝐨𝐫 ➠</b> <b>{session['errors']} </b>\n"
        f"     <tg-emoji emoji-id=\"5258419835922030550\">🕔</tg-emoji> <b>𝐄𝐥𝐚𝐩𝐬𝐞𝐝 ➠</b> <b>{elapsed_str}</b>\n"
        f"<b><tg-emoji emoji-id=\"5429495925284296642\">🚬</tg-emoji> 𝐃𝐞𝐯 ➠</b> <a href='https://t.me/Enchanted_linux_0x'>Enchanted_linux_0x</a>"
        
    )

    if session.get('last_text') == text:
        return

    if session_id not in MCHK_SESSION_LOCKS:
        MCHK_SESSION_LOCKS[session_id] = asyncio.Lock()

    async with MCHK_SESSION_LOCKS[session_id]:
        if session.get('last_text') == text:
            return

        is_running = session['status'] == "𝗖𝗵𝗲𝗰𝗸𝗶𝗻𝗴..."
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
            await _safe_answer(callback, "⚠️ Session expired", show_alert=True)
            return
        if callback.from_user.id != session.get('user_id'):
            await _safe_answer(callback, "❌ No permission", show_alert=True)
            return

        if is_buttons_locked(session_id):
            remaining = get_remaining_lock(session_id)
            await _safe_answer(callback, f"⏳ Please wait {remaining} seconds before using buttons", show_alert=True)
            return

        count = 0
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
            await _safe_answer(callback, f"❌ No {type_names.get(result_type, '')} cards found", show_alert=True)
            return

        await _safe_answer(callback, "📦 Generating report...", show_alert=False)

        user_obj = session.get('user_obj')
        plan_name = session.get('plan_name', 'TRIAL')
        user_msg_id = session.get('user_msg_id')

        file_buffer, filename, total_count = generate_result_file(session, result_type, user_obj, plan_name)
        file_content = file_buffer.read()
        file_buffer.seek(0)

        type_emojis = {
            "charged": f'<tg-emoji emoji-id="{CUSTOM_CHARGED_EMOJI_ID}">💎</tg-emoji>',
            "live": f'<tg-emoji emoji-id="{CUSTOM_APPROVED_EMOJI_ID}">✅</tg-emoji>',
            "dead": f'<tg-emoji emoji-id="{CUSTOM_DECLINED_EMOJI_ID}">❌</tg-emoji>',
            "all": "📁"
        }
        type_labels = {"charged": "𝗖𝗵𝗮𝗿𝗴𝗲𝗱", "live": "𝗟𝗶𝘃𝗲", "dead": "𝗗𝗲𝗮𝗱", "all": "𝗔𝗹𝗹"}

        caption = (
            f"𝗥𝗲𝘀𝘂𝗹𝘁 𝗧𝘆𝗽𝗲 ➠ {type_labels.get(result_type, '𝗔𝗹𝗹')} {type_emojis.get(result_type, '📁')}\n"
            f"𝗧𝗼𝘁𝗮𝗹 𝗖𝗮𝗿𝗱𝘀 ➠ <b>{total_count}</b>\n"
            f"𝗚𝗮𝘁𝗲𝘄𝗮𝘆 ➠ 𝗦𝘁𝗿𝗶𝗽𝗲 𝗔𝘂𝘁𝗵"
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
            await _safe_answer(callback, "⚠️ Session expired", show_alert=True)
            return
        if callback.from_user.id != session.get('user_id'):
            await _safe_answer(callback, "❌ No permission", show_alert=True)
            return

        if session['status'] != "𝗖𝗵𝗲𝗰𝗸𝗶𝗻𝗴...":
            await _safe_answer(callback, "ℹ️ Not running", show_alert=True)
            return

        session['status'] = "𝗦𝘁𝗼𝗽𝗽𝗲𝗱"
        print(f"🛑 [MCHK] Stop signal sent")

        # Graceful stop: workers check is_session_stopped() and bail on their own.
        await _safe_answer(callback, "🛑 Stopping... in-flight cards will finish", show_alert=False)

        session['last_text'] = ""
        await update_progress_message(callback.bot, session_id)

    except Exception as e:
        logging.error(f"Error handling MCHK stop callback: {e}", exc_info=True)
        try:
            await _safe_answer(callback, "❌ Error stopping", show_alert=True)
        except:
            pass

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# CARD PROCESSING
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

async def process_single_card(session_id, cc_formatted, cc_num, user_id, bot, user_obj, plan_name):
    """
    Process a single card using stripeauth.py which handles its own proxy rotation.
    """
    session = MCHK_SESSIONS.get(session_id)
    if not session or is_session_stopped(session_id):
        return

    result_status = "ERROR"
    response_msg = "Unknown Error"

    try:
        # Call with use_proxy=True (default) - stripeauth handles proxies internally
        api_result = await process_stripe_auth(cc_formatted, use_proxy=True)
        result_status = api_result.get("status", "error").upper()
        response_msg = api_result.get("response", "Unknown Error")
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

    card_result_data = {
        'card': cc_formatted,
        'response': response_msg,
        'bin_info': bin_data,
        'gateway': 'Stripe Auth',
        'timestamp': datetime.now().isoformat()
    }

    if is_session_stopped(session_id):
        return

    # Handle different result statuses
    if result_status in ["HTTP_ERROR", "TIMEOUT", "ERROR"]:
        session['errors'] += 1
        session['error_cards'].append(card_result_data)
        # No credit deduction for errors

    elif result_status == "APPROVED":
        # APPROVED means charged/approved in stripeauth
        session['charged'] += 1
        session['charged_cards'].append(card_result_data)

        await asyncio.gather(
            asyncio.to_thread(update_user_stats, user_id, True),
            asyncio.to_thread(log_hit_to_mchk, user_id, user_obj.username, user_obj.first_name),
            asyncio.to_thread(deduct_credits_atomic, user_id, 2),
        )

        if is_session_stopped(session_id):
            return

        if session.get('send_charged', True):
            await send_user_hit_notification(bot, session, cc_formatted, cc_num, response_msg, user_obj, plan_name, "CHARGED")

    elif result_status == "DECLINED":
        session['dead'] += 1
        session['dead_cards'].append(card_result_data)

        await asyncio.gather(
            asyncio.to_thread(update_user_stats, user_id, False),
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
            "💎<b>𝗣𝗹𝗲𝗮𝘀𝗲 𝘂𝗽𝗴𝗿𝗮𝗱𝗲 𝘆𝗼𝘂𝗿 𝗽𝗹𝗮𝗻 𝘁𝗼 𝘂𝘀𝗲 𝘁𝗵𝗶𝘀 𝗳𝗲𝗮𝘁𝘂𝗿𝗲.</b>\n\n👉 𝗨𝘀𝗲 /plan 𝘁𝗼 𝘂𝗽𝗴𝗿𝗮𝗱𝗲.",
            parse_mode="HTML"
        )
        return

    # ── CHECK FOR ACTIVE SESSION ──
    is_checking = False
    for session_id, session_data in list(MCHK_SESSIONS.items()):
        if session_data.get('user_id') == user_id and session_data.get('status') == "𝗖𝗵𝗲𝗰𝗸𝗶𝗻𝗴...":
            is_checking = True
            break

    if is_checking:
        await message.reply(
            "⚠️ <b>𝗔𝗰𝘁𝗶𝘃𝗲 𝗦𝗲𝘀𝘀𝗶𝗼𝗻</b>\n\nUse the <b>🛑 Stop</b> button to stop it.",
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

    file_cards = []
    if document:
        try:
            file_cards = await download_and_extract_chunked(bot, document)
        except Exception as e:
            await message.reply(f"❌ Error reading file: {e}")
            return

    if not raw_text.strip() and not file_cards:
        await message.reply("❌ <b>No cards found.</b>", parse_mode="HTML")
        return

    extracted_cards = extract_cards_from_text(raw_text)
    if file_cards:
        _seen = set(extracted_cards)
        extracted_cards.extend(c for c in file_cards if c not in _seen)
    if not extracted_cards:
        await message.reply("❌ No valid card formats found.")
        return

    valid_cards = []
    is_owner = is_owner_user(user_id)
    for card_string in extracted_cards:
        parts = card_string.split('|')
        if len(parts) != 4:
            continue
        cc, mm, yy, cvv = parts
        if luhn_check(cc):
            valid_cards.append((card_string, cc))

    total_cards = len(valid_cards)
    if total_cards == 0:
        await message.reply("❌ No valid Luhn checked cards found.")
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

    plan_name = await get_user_plan_name(user_id)

    # ── Selection UI: ask which hits to DM before starting ──
    sel_id = "".join(random.choices(string.ascii_uppercase + string.digits, k=8))
    MCHK_PENDING[sel_id] = {
        "user_id": user_id,
        "cards": valid_cards,
        "user_obj": user,
        "plan_name": plan_name,
        "charged": True,
        "approved": False,
        "chat_id": message.chat.id,
    }
    sel_msg = await message.reply(
        _selection_text(True, False, total_cards),
        parse_mode="HTML",
        reply_markup=_selection_keyboard(sel_id, True, False),
    )
    MCHK_PENDING[sel_id]["msg_id"] = sel_msg.message_id


async def _start_mchk(callback: types.CallbackQuery, pending: dict):
    bot = callback.bot
    message = callback.message
    user = pending["user_obj"]
    user_id = pending["user_id"]
    valid_cards = pending["cards"]
    plan_name = pending.get("plan_name")
    send_charged = pending.get("charged", True)
    send_approved = pending.get("approved", False)

    try:
        await message.edit_text("🚀 Starting mass check...", parse_mode="HTML")
    except Exception:
        pass
    await callback.answer("🚀 Starting...")

    session_id = "".join(random.choices(string.ascii_uppercase + string.digits, k=8))
    initial_text = (
        f"<a href='https://t.me/Enchanted_linux_0x'>✧</a> <b>𝐒𝐭𝐚𝐭𝐮𝐬 ➠</b> 𝗖𝗵𝗲𝗰𝗸𝗶𝗻𝗴... <tg-emoji emoji-id=\"6253754970349243649\">✨</tg-emoji>\n"
        f"<a href='https://t.me/Enchanted_linux_0x'>✧</a> <b>𝐒𝐞𝐬𝐬𝐢𝐨𝐧 𝐈𝐃 ➠</b> <code>{session_id}</code>\n"                
        f"<a href='https://t.me/Enchanted_linux_0x'>✧</a> <b>𝐓𝐨𝐭𝐚𝐥 ➠</b> <code>0/{total_cards}</code>\n"
        f"      <b>𝐂𝐡𝐚𝐫𝐠𝐞𝐝 ➠</b> <b>0 <tg-emoji emoji-id=\"{CUSTOM_CHARGED_EMOJI_ID}\">💎</tg-emoji></b>\n"
        f"      <b>𝐀𝐩𝐩𝐫𝐨𝐯𝐞𝐝 ➠</b> <b>0 <tg-emoji emoji-id=\"{CUSTOM_APPROVED_EMOJI_ID}\">✅</tg-emoji></b>\n"        
        f"      <b>𝐃𝐞𝐜𝐥𝐢𝐧𝐞𝐝 ➠</b> <b>0 <tg-emoji emoji-id=\"{CUSTOM_DECLINED_EMOJI_ID}\">❌</tg-emoji></b>\n"
        f"<a href='https://t.me/Enchanted_linux_0x'>π</a> <b>𝐆𝐚𝐭𝐞𝐰𝐚𝐲 ➠</b> 𝐒𝐭𝐫𝐢𝐩𝐞 𝐀𝐮𝐭𝐡\n"
        f"      <b>𝐄𝐫𝐫𝐨𝐫 ➠</b> <b>0 ⚠️</b>\n"
        f"      <b>𝐄𝐥𝐚𝐩𝐬𝐞𝐝 ➠</b> <b>0s</b>\n"
        f"<b>𝐃𝐞𝐯 ➠</b> <a href='https://t.me/Enchanted_linux_0x'>Enchanted_linux_0x</a>"
        
    )

    initial_buttons = get_result_buttons(session_id, is_running=True)
    progress_msg = await message.reply(initial_text, parse_mode="HTML", reply_markup=initial_buttons, disable_web_page_preview=True)

    MCHK_SESSIONS[session_id] = {
        "status": "𝗖𝗵𝗲𝗰𝗸𝗶𝗻𝗴...",
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
        "is_group": message.chat.type in ("group", "supergroup", "channel"),
        "send_charged": send_charged,
        "send_approved": send_approved,
    }

    print(f"🚀 [MCHK] Started - {total_cards} cards - User: {user_id}")
    logging.info(f"🚀 [MCHK] Started - {total_cards} cards - User: {user_id}")

    asyncio.create_task(run_mass_checker(bot, session_id, valid_cards, user, plan_name))


@router.callback_query(MchkSelCallback.filter())
async def handle_selection_callback(callback: types.CallbackQuery, callback_data: MchkSelCallback):
    sel_id = callback_data.sel_id
    action = callback_data.action
    pending = MCHK_PENDING.get(sel_id)
    if not pending:
        await callback.answer("⚠️ Selection expired — run /mchk again.", show_alert=True)
        return
    if callback.from_user.id != pending.get("user_id"):
        await callback.answer("❌ No permission", show_alert=True)
        return
    if action == "charged":
        pending["charged"] = not pending["charged"]
    elif action == "approved":
        pending["approved"] = not pending["approved"]
    elif action == "start":
        if MCHK_PENDING.pop(sel_id, None) is None:
            await callback.answer("Already starting...")
            return
        asyncio.create_task(_start_mchk(callback, pending))
        return
    charged = pending.get("charged", True)
    approved = pending.get("approved", False)
    try:
        await callback.message.edit_text(
            _selection_text(charged, approved, len(pending.get("cards", []))),
            parse_mode="HTML",
            reply_markup=_selection_keyboard(sel_id, charged, approved),
        )
    except Exception as e:
        logging.error(f"[mchk] selection edit error: {e}")
    await callback.answer("✅ Updated")

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

    # Concurrency level - matches mst.py
    sem = asyncio.Semaphore(30)

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

    if tasks:
        results = await asyncio.gather(*tasks, return_exceptions=True)
        cancelled = sum(1 for r in results if isinstance(r, asyncio.CancelledError))
        if cancelled > 0:
            print(f"🛑 [MCHK] {cancelled} tasks cancelled")

    session = MCHK_SESSIONS.get(session_id)
    if session and session['status'] != "𝗦𝘁𝗼𝗽𝗽𝗲𝗱":
        session['status'] = "𝗦𝘂𝗺𝗺𝗮𝗿𝘆"
        session['last_text'] = ""
        await update_progress_message(bot, session_id)
        print(f"✅ [MCHK] Completed - A:{session['approved']} C:{session['charged']} D:{session['dead']} E:{session['errors']}")
    elif session and session['status'] == "𝗦𝘁𝗼𝗽𝗽𝗲𝗱":
        print(f"🛑 [MCHK] Stopped - A:{session['approved']} C:{session['charged']} D:{session['dead']} Checked:{session['checked']}")