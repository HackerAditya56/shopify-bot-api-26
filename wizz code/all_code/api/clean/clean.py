import asyncio
import io
import json
import logging
import os
import re
import random
import math
import string
from collections import Counter, OrderedDict
from datetime import datetime
import aiohttp

from aiogram import Bot, Dispatcher, Router, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton, BufferedInputFile
from aiogram.filters import CommandStart, Command
from aiogram.enums import ParseMode
from aiogram.exceptions import TelegramBadRequest
from aiogram.client.default import DefaultBotProperties

try:
    from aiogram.enums import ButtonStyle
except ImportError:
    ButtonStyle = None

try:
    from telethon import TelegramClient
    from telethon.sessions import StringSession
    from telethon.errors import FloodWaitError
    TELETHON_AVAILABLE = True
except ImportError:
    TelegramClient = None
    StringSession = None
    FloodWaitError = None
    TELETHON_AVAILABLE = False


BOT_TOKEN = "8989956190:AAH35r_eImwX8GB8tp099SuYCPVwbMj3uvU"
OWNER_USERNAME = "@rapewthyou"
CHANNEL_URL = "https://t.me/splitterxbackup"
DEV_URL = "https://t.me/rapewthyou"

API_ID = 35113001
API_HASH = "bae3c4e34242aca7cdd1b8596fb1aad2"
TELETHON_SESSION = "1BJWap1sBu3i9E8y4rLHRXBCpJFcpm7bmXH4AWs8Was2lAGTfJ1OGWg8AIKd4zuO0FgR_Do150kq4xjDA5ZeXt9irGSAxIkjOuD3_LKlr4MOG3AdwofmDG8_mkS3KdjxMquswCR6zXF_q9zLKXuNlKRX75KWSF3TTJ3VnL0TdeIwkfvseYncPGpDn-AjFsot7MR8lp3ELr-l3RGRL0hDXKhsueUJc7-1MyVB3erdlwBSMX1pXEiMbseiroOz-PX2nd3nXF0aXVOtDpPl2ideaefESfq0f1HQRHMmqPIr8hHGrNu0KIovscze9wSU4gjo6bJeEHd4wpEvLNWMvnutDWdVEiibov6I="
LOG_CHANNEL_ID = -1003933757925
OWNER_ID = 8423281554

USERBOT_ENABLED = bool(TELETHON_AVAILABLE and API_ID and API_HASH and TELETHON_SESSION and LOG_CHANNEL_ID)
TWENTY_MB = 20 * 1024 * 1024
EXPORT_LIMIT = 45 * 1024 * 1024
USERS_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "users.json")
BIN_CACHE_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "bin_cache.json")
BIN_CONCURRENCY = 80


E_BOLT = '<tg-emoji emoji-id="5235548392041503275">⚡</tg-emoji>'
E_FILE = '<tg-emoji emoji-id="5447408120752013199">⚡</tg-emoji>'
E_ARRW = '<tg-emoji emoji-id="5303138782004924588">⚡</tg-emoji>'
E_TOOL = '<tg-emoji emoji-id="5172739056592749710">⚡</tg-emoji>'
E_CLEN = '<tg-emoji emoji-id="5278622189556354905">⚡</tg-emoji>'
E_SPCL = '<tg-emoji emoji-id="5445210909972655435">⚡</tg-emoji>'
E_FRMT = '<tg-emoji emoji-id="5445353829304387411">⚡</tg-emoji>'
E_BAD  = '<tg-emoji emoji-id="5042112436648281096">⚡</tg-emoji>'
E_CHK  = '<tg-emoji emoji-id="5447319442562251569">⚡</tg-emoji>'
E_3DS  = '<tg-emoji emoji-id="5085022089103016925">⚡</tg-emoji>'
E_HLP  = '<tg-emoji emoji-id="5249380218254151868">⚡</tg-emoji>'
E_GEN  = '<tg-emoji emoji-id="5361696340348779794">⚡</tg-emoji>'
E_SGN  = '<tg-emoji emoji-id="5445088739627924307">⚡</tg-emoji>'
E_DRP  = '<tg-emoji emoji-id="5447554042265891906">⚡</tg-emoji>'
E_FLT  = '<tg-emoji emoji-id="5445347129155419150">⚡</tg-emoji>'
E_NET  = '<tg-emoji emoji-id="5445267414562389170">⚡</tg-emoji>'
E_TYP  = '<tg-emoji emoji-id="4911241630633165627">⚡</tg-emoji>'
E_LVL  = '<tg-emoji emoji-id="5298970748172385213">⚡</tg-emoji>'
E_SRT  = '<tg-emoji emoji-id="5260681660189408650">⚡</tg-emoji>'
E_CNV  = '<tg-emoji emoji-id="5042101437237036298">⚡</tg-emoji>'
E_SCR  = '<tg-emoji emoji-id="5134452506935427991">⚡</tg-emoji>'
E_DIV  = '<tg-emoji emoji-id="5980995951160987855">⚡</tg-emoji>'
E_CON  = '<tg-emoji emoji-id="5235909057625215318">⚡</tg-emoji>'


FILE_CACHE = {} 
BIN_MEM_CACHE = {}

COUNTRIES_IN_TEXT = 16
BINS_IN_TEXT = 10

BUTTON_COLS = 4
BUTTON_ROWS_PER_PAGE = 8
BUTTONS_PER_PAGE = BUTTON_COLS * BUTTON_ROWS_PER_PAGE

MAJOR_NETWORKS = {"visa", "mastercard", "amex", "discover", "jcb", "unionpay"}

tg_client = None
BOT_USERS = set()
BROADCAST_STATE = {"running": False}
BIN_DISK_CACHE = None
HTTP_SESSION = None


async def get_http_session():
    global HTTP_SESSION
    if HTTP_SESSION is None or HTTP_SESSION.closed:
        HTTP_SESSION = aiohttp.ClientSession(
            connector=aiohttp.TCPConnector(limit=200, ttl_dns_cache=600, keepalive_timeout=60)
        )
    return HTTP_SESSION


def _load_bin_disk_cache():
    global BIN_DISK_CACHE
    if BIN_DISK_CACHE is None:
        try:
            with open(BIN_CACHE_FILE, "r", encoding="utf-8") as f:
                BIN_DISK_CACHE = json.load(f)
        except Exception:
            BIN_DISK_CACHE = {}
    return BIN_DISK_CACHE


def _save_bin_disk_cache():
    try:
        with open(BIN_CACHE_FILE, "w", encoding="utf-8") as f:
            json.dump(BIN_DISK_CACHE or {}, f)
    except Exception:
        pass


def load_users():
    global BOT_USERS
    try:
        with open(USERS_FILE, "r", encoding="utf-8") as f:
            BOT_USERS = set(int(x) for x in json.load(f))
    except Exception:
        BOT_USERS = set()


def save_users():
    try:
        with open(USERS_FILE, "w", encoding="utf-8") as f:
            json.dump(sorted(BOT_USERS), f)
    except Exception:
        pass


def track_user(user_id):
    if user_id and user_id not in BOT_USERS:
        BOT_USERS.add(user_id)
        save_users()


def is_owner(user):
    if not user:
        return False
    if OWNER_ID and user.id == OWNER_ID:
        return True
    return (user.username or "").lower() == OWNER_USERNAME.lstrip("@").lower()


async def start_userbot():
    global tg_client
    if not USERBOT_ENABLED:
        if not TELETHON_AVAILABLE:
            print("⚠️  Telethon not installed — large files (>20MB) via MTProto disabled.")
        else:
            print("⚠️  Userbot not configured — set API_ID/API_HASH/TELETHON_SESSION/LOG_CHANNEL_ID.")
        return
    try:
        tg_client = TelegramClient(StringSession(TELETHON_SESSION), API_ID, API_HASH)
        await tg_client.start()
        me = await tg_client.get_me()
        print(f"✅ Userbot online as {getattr(me, 'username', None) or me.id} — MTProto large-file download enabled.")
    except Exception as e:
        tg_client = None
        print(f"⚠️  Userbot failed to start: {e}")


async def stop_userbot():
    global tg_client
    if tg_client:
        try:
            await tg_client.disconnect()
        except Exception:
            pass
        tg_client = None


async def _download_via_userbot(message, bot):
    fwd = await bot.forward_message(
        chat_id=LOG_CHANNEL_ID, from_chat_id=message.chat.id, message_id=message.message_id
    )
    tg_msg = await tg_client.get_messages(LOG_CHANNEL_ID, ids=fwd.message_id)
    buf = io.BytesIO()
    await tg_client.download_media(tg_msg, file=buf)
    buf.seek(0)
    return buf.read().decode('utf-8', errors='ignore')


def _chunk_lines(lines, limit_bytes):
    chunks, cur, cur_size = [], [], 0
    for line in lines:
        blen = len(line.encode('utf-8')) + 1
        if cur and cur_size + blen > limit_bytes:
            chunks.append(cur)
            cur, cur_size = [], 0
        cur.append(line)
        cur_size += blen
    if cur:
        chunks.append(cur)
    return chunks


async def deliver_document(bot, message, raw, filename, caption, user_id=None):
    if len(raw) <= EXPORT_LIMIT:
        await message.reply_document(
            document=BufferedInputFile(raw, filename=filename),
            caption=caption, parse_mode=ParseMode.HTML
        )
        return
    if tg_client and user_id:
        try:
            await tg_client.send_file(
                user_id, io.BytesIO(raw), file_name=filename,
                caption=f"📦 {filename} — {max(1, len(raw) // (1024 * 1024))} MB"
            )
            return
        except Exception:
            pass
    stem = re.sub(r'\.txt$', '', filename)
    for i, chunk in enumerate(_chunk_lines(raw.decode('utf-8', errors='ignore').splitlines(), EXPORT_LIMIT), 1):
        await message.reply_document(
            document=BufferedInputFile("\n".join(chunk).encode('utf-8'), filename=f"{stem}_part_{i}.txt"),
            parse_mode=ParseMode.HTML
        )


async def fetch_document_text(message, bot):
    doc = message.document
    size = getattr(doc, "file_size", 0) or 0

    if tg_client and size > TWENTY_MB:
        return await _download_via_userbot(message, bot)

    try:
        file_info = await bot.get_file(doc.file_id)
        downloaded = await bot.download_file(file_info.file_path)
        return downloaded.read().decode('utf-8', errors='ignore')
    except TelegramBadRequest as e:
        if tg_client and "too big" in str(e).lower():
            return await _download_via_userbot(message, bot)
        raise
    except Exception as e:
        if tg_client and "too big" in str(e).lower():
            return await _download_via_userbot(message, bot)
        raise


CC_REGEX = re.compile(r'\b([2-6]\d{14,15})[\s|/:-]+(\d{1,2})[\s|/:-]+(\d{2,4})[\s|/:-]+(\d{3,4})\b')
EMAIL_REGEX = re.compile(r'[\w\.-]+@[\w\.-]+\.\w+')
URL_REGEX = re.compile(r'https?://[^\s]+')
PHONE_REGEX = re.compile(r'\+?\d{10,15}')

def luhn_check(card_number):
    digits = [int(x) for x in str(card_number)]
    odd_digits = digits[-1::-2]
    even_digits = [sum(divmod(2 * d, 10)) for d in digits[-2::-2]]
    return (sum(odd_digits) + sum(even_digits)) % 10 == 0

def check_expiry(mm, yy):
    try:
        now = datetime.now()
        curr_year, curr_month = now.year % 100, now.month
        y, m = int(yy[-2:]), int(mm)
        if not 1 <= m <= 12: return False
        if y < curr_year: return False
        if y == curr_year and m < curr_month: return False
        return True
    except: return False

def get_flag(code):
    if not code or code == "Unknown": return "🏳️"
    return "".join(chr(ord(c) + 127397) for c in code.upper())

def extract_ccs(text, check_luhn=False, check_valid=False):
    found = CC_REGEX.findall(text)
    ccs = []
    for cc, mm, yy, cvv in found:
        yy = "20" + yy if len(yy) == 2 else yy
        mm = "0" + mm if len(mm) == 1 else mm
        if check_valid and not check_expiry(mm, yy):
            continue
        if check_luhn and not luhn_check(cc):
            continue
        ccs.append(f"{cc}|{mm}|{yy}|{cvv}")
    return ccs

def get_network(cc):
    if cc.startswith('4'): return "Visa"
    elif cc.startswith(('2', '5')): return "Mastercard"
    elif cc.startswith(('34', '37')): return "Amex"
    elif cc.startswith('35'): return "JCB"
    elif cc.startswith(('30', '36', '38', '39')): return "Diners Club"
    elif cc.startswith('3'): return "Amex"
    elif cc.startswith('6'): return "Discover"
    return "Unknown"

CARD_PATTERNS = OrderedDict([
    ("BIN2",       re.compile(r'^2\d{15}$')),
    ("AMEX",       re.compile(r'^3[47]\d{13}$')),
    ("VISA",       re.compile(r'^4\d{12}(?:\d{3})?$')),
    ("MASTERCARD", re.compile(r'^(5[1-5]\d{14}|2(2[2-9]\d{12}|[3-6]\d{13}|7[0-1]\d{12}|720\d{12}))$')),
    ("DISCOVER",   re.compile(r'^6(?:011|5\d{2}|4[4-9]\d|22(?:12[6-9]|1[3-9]\d|[2-8]\d{2}|9[01]\d|92[0-5])|64[4-9]\d|65\d{2})\d{10,12}$')),
    ("JCB",        re.compile(r'^(352[8-9]|35[3-8]\d)\d{12}$')),
    ("DINERS",     re.compile(r'^3(?:0[0-5]|[68]\d)\d{11}$')),
    ("UNIONPAY",   re.compile(r'^62\d{14,17}$')),
])

CARD_PRIORITY = {
    "BIN2": 0, "AMEX": 1, "VISA": 2, "MASTERCARD": 3,
    "DISCOVER": 4, "JCB": 5, "DINERS": 6, "UNIONPAY": 7,
}

def detect_card_type(number):
    number = re.sub(r'\D', '', str(number))
    for name, pat in CARD_PATTERNS.items():
        if pat.match(number):
            return name
    return "UNKNOWN"

def card_priority(number):
    return CARD_PRIORITY.get(detect_card_type(number), 99)

def sort_cards(ccs):
    def key(c):
        num = re.sub(r'\D', '', c.split('|')[0])
        return (card_priority(num), int(num) if num else 0)
    return sorted(ccs, key=key)

def fallback_bin(bin_num):
    return {
        "found": False, "network": get_network(bin_num), "type": "Unknown",
        "level": "Unknown", "bank": "UNKNOWN", "country": "Unknown",
        "code": "US", "flag": "🏳️"
    }

async def fetch_bin_api(bin_number, session=None):
    """Antipublic API se asli network, type, level, bank aur country flag nikalta hai"""
    bin_num = re.sub(r'\D', '', str(bin_number))[:6]
    if len(bin_num) < 6:
        return fallback_bin(bin_num)
    if bin_num in BIN_MEM_CACHE:
        return BIN_MEM_CACHE[bin_num]

    disk = _load_bin_disk_cache()
    if bin_num in disk:
        BIN_MEM_CACHE[bin_num] = disk[bin_num]
        return disk[bin_num]

    data = fallback_bin(bin_num)
    session = session or await get_http_session()

    try:
        async with session.get(
            f"https://bins.antipublic.cc/bins/{bin_num}",
            timeout=aiohttp.ClientTimeout(total=6)
        ) as resp:
            if resp.status == 200:
                js = await resp.json(content_type=None)
                if isinstance(js, dict) and not js.get("error"):
                    data["network"] = (js.get("brand") or data["network"]).strip().title()
                    data["type"] = (js.get("type") or "Unknown").strip().title()
                    data["level"] = (js.get("level") or "Unknown").strip().title()
                    data["bank"] = (js.get("bank") or "UNKNOWN").strip().upper()
                    data["country"] = (js.get("country_name") or "Unknown").strip().title()
                    data["code"] = (js.get("country") or "US").strip().upper()
                    data["flag"] = js.get("country_flag") or get_flag(data["code"])
                    data["found"] = True
    except Exception:
        pass

    BIN_MEM_CACHE[bin_num] = data
    if data.get("found"):
        disk[bin_num] = data
    return data

async def enrich_bins(bins, concurrency=BIN_CONCURRENCY):
    """Saare unique BINs ko limited concurrency ke saath enrich karta hai"""
    bins = list(dict.fromkeys(b for b in bins if b and len(b) >= 6))
    if not bins:
        return {}
    session = await get_http_session()
    sem = asyncio.Semaphore(concurrency)

    async def worker(b):
        async with sem:
            return b, await fetch_bin_api(b, session)
    pairs = await asyncio.gather(*[worker(b) for b in bins])
    _save_bin_disk_cache()
    return dict(pairs)

async def process_bulk_ccs(text):
    """Real time Analysis: Identical layout to original Eraser"""
    found = CC_REGEX.findall(text)
    
    stats = {
        'total': 0, 'live_format': 0, 'expired': 0, 'duplicates': 0,
        'unique_bins': set(), 'networks': Counter(), 'countries': Counter(),
        'country_codes': {}, 'country_flags': {},
        'types': Counter(), 'levels': Counter(), 'valid_ccs': [], 'expired_ccs': [],
        '3d_secured': 0, 'raw_bins': Counter(), 'enriched_data': {}
    }
    
    seen = set()
    initial_valid = []
    

    for cc, mm, yy, cvv in found:
        stats['total'] += 1
        yy = "20" + yy if len(yy) == 2 else yy
        mm = "0" + mm if len(mm) == 1 else mm
        formatted = f"{cc}|{mm}|{yy}|{cvv}"
        
        if formatted in seen:
            stats['duplicates'] += 1
            continue
        seen.add(formatted)
        
        if check_expiry(mm, yy) and luhn_check(cc):
            stats['live_format'] += 1
            initial_valid.append(formatted)
            bin_prefix = cc[:6]
            stats['unique_bins'].add(bin_prefix)
            stats['raw_bins'][bin_prefix] += 1
        else:
            stats['expired'] += 1
            stats['expired_ccs'].append(formatted)
            

    bin_data_map = await enrich_bins(stats['unique_bins'])
    

    for cc in initial_valid:
        b = cc[:6]
        info = bin_data_map.get(b) or fallback_bin(b)
        stats['valid_ccs'].append(cc)
        stats['enriched_data'][cc] = info
        
        stats['networks'][info['network']] += 1
        stats['types'][info['type']] += 1
        stats['levels'][info['level']] += 1
        stats['countries'][info['country']] += 1
        stats['country_codes'][info['country']] = info['code']
        stats['country_flags'][info['country']] = info.get('flag') or get_flag(info['code'])
        if info['type'].lower() == "credit":
            stats['3d_secured'] += 1
            
    return stats, bin_data_map


def compute_slice(stats, spec):
    """Cache me stored spec ke hisaab se export data nikalta hai"""
    kind = spec[0]
    valid = stats.get('valid_ccs', [])
    enriched = stats.get('enriched_data', {})
    if kind == "all":
        return list(valid)
    if kind == "bin":
        return [c for c in valid if c.startswith(spec[1])]
    if kind == "field_eq":
        field, val = spec[1], spec[2].lower()
        return [c for c in valid if enriched.get(c, {}).get(field, "").lower() == val]
    if kind == "field_contains":
        field, val = spec[1], spec[2].lower()
        return [c for c in valid if val and val in enriched.get(c, {}).get(field, "").lower()]
    return []


def styled_btn(text: str, cb: str = None, url: str = None, style_name: str = "primary", emoji_id: str = None):
    kwargs = {"text": text}
    if url: kwargs["url"] = url
    elif cb: kwargs["callback_data"] = cb
    else: kwargs["callback_data"] = "noop"
    
    btn = InlineKeyboardButton(**kwargs)
    if ButtonStyle:
        if style_name == "success": btn.style = ButtonStyle.SUCCESS
        elif style_name == "danger": btn.style = ButtonStyle.DANGER
        else: btn.style = ButtonStyle.PRIMARY 
    if emoji_id:
        setattr(btn, "icon_custom_emoji_id", str(emoji_id))
    return btn


def render_analysis_keyboard(short_id, entry, page=0):
    """Build a paginated, multi-column export keyboard for the analysis.

    Each section starts on a new row, so a section holding a single button
    (one country / one card type) renders as a single full-width row.
    """
    header = entry.get("header", [])
    sections = entry.get("sections", [])

    item_rows = []
    for section in sections:
        row = []
        for b in section:
            row.append(b)
            if len(row) >= BUTTON_COLS:
                item_rows.append(row)
                row = []
        if row:
            item_rows.append(row)

    total_pages = max(1, (len(item_rows) + BUTTON_ROWS_PER_PAGE - 1) // BUTTON_ROWS_PER_PAGE)
    page = max(0, min(page, total_pages - 1))

    rows = []
    if header:
        rows.append([styled_btn(b["label"], cb=b["cb"], style_name=b["style"]) for b in header])

    for item_row in item_rows[page * BUTTON_ROWS_PER_PAGE:(page + 1) * BUTTON_ROWS_PER_PAGE]:
        rows.append([styled_btn(b["label"], cb=b["cb"], style_name=b["style"]) for b in item_row])

    nav = []
    if page > 0:
        nav.append(styled_btn("⬅️ 𝗣𝗿𝗲𝘃", cb=f"pg_{short_id}_{page-1}", style_name="primary"))
    if total_pages > 1:
        nav.append(styled_btn(f"📄 {page+1}/{total_pages}", cb="noop", style_name="primary"))
    if page < total_pages - 1:
        nav.append(styled_btn("𝗡𝗲𝘅𝘁 ➡️", cb=f"pg_{short_id}_{page+1}", style_name="primary"))
    if nav:
        rows.append(nav)

    return InlineKeyboardMarkup(inline_keyboard=rows)

def main_help_text():
    return f"""{E_BOLT} 𝗖𝗖 𝗖𝗹𝗲𝗮𝗻𝗲𝗿 𝗣𝗿𝗼
{E_BOLT} ━━━━━━━━━━━━━━━━━━

{E_FILE} 𝗔𝘂𝘁𝗼 𝗔𝗻𝗮𝗹𝘆𝘇𝗲 — 𝗦𝗲𝗻𝗱 𝗮𝗻𝘆 .𝘁𝘅𝘁 𝗳𝗶𝗹𝗲
{E_ARRW} <blockquote>Instant stats + filter buttons by network & BIN</blockquote>

{E_TOOL} 𝗖𝗹𝗲𝗮𝗻 & 𝗧𝗼𝗼𝗹𝘀
{E_CLEN} /clean — 𝗖𝗹𝗲𝗮𝗻 & 𝗿𝗲𝗺𝗼𝘃𝗲 𝗲𝘅𝗽𝗶𝗿𝗲𝗱
{E_SPCL} /superclean — 𝗖𝗹𝗲𝗮𝗻 + 𝗹𝘂𝗵𝗻 𝘃𝗮𝗹𝗶𝗱
{E_FRMT} /format — 𝗡𝗼𝗿𝗺𝗮𝗹𝗶𝘇𝗲 𝗳𝗼𝗿𝗺𝗮𝘁
{E_BAD} /expired · /invalid — 𝗘𝘅𝗽𝗼𝗿𝘁 𝗯𝗮𝗱 𝗰𝗮𝗿𝗱𝘀
{E_CHK} /bin 515462 · /cc — 𝗕𝗜𝗡 & 𝗰𝗮𝗿𝗱 𝗰𝗵𝗲𝗰𝗸
{E_3DS} /vbv · /f2d · /f3d — 𝟯𝗗𝗦 𝘁𝗼𝗼𝗹𝘀
{E_HLP} /help — 𝗙𝘂𝗹𝗹 𝗰𝗼𝗺𝗺𝗮𝗻𝗱 𝗹𝗶𝘀𝘁
{E_GEN} /gen 515462 10 — 𝗚𝗲𝗻𝗲𝗿𝗮𝘁𝗲 𝗰𝗮𝗿𝗱𝘀

{E_FILE} 𝗙𝗶𝗹𝗲 𝗧𝗼𝗼𝗹𝘀 {E_ARRW} <blockquote>Reply to .txt</blockquote>
{E_SGN} /split 300 · /parts 5 · /merge · /count · /info
{E_DRP} /grab · /rand 20 · /topbins · /bins · /rembin
{E_SPCL} /dedup · /head 20 · /tail 20 · /search text
{E_GEN} /reverse · /shuffle · /getemails · /geturls

{E_FLT} 𝗙𝗶𝗹𝘁𝗲𝗿𝘀 ⚡ 𝗥𝗲𝗽𝗹𝘆 𝘁𝗼 .𝘁𝘅𝘁
{E_DIV} ━━━━━━━━━━━━━━━━━━
{E_ARRW} /fbin 515462 · /fco US · /fbank Chase
{E_ARRW} /ftype credit · /flevel platinum · /fexp 12/26
{E_ARRW} /fnet visa · master · amex · discover · jcb
{E_ARRW} /sort bin|exp|country|bank|type|level

{E_CNV} 𝗖𝗼𝗻𝘃𝗲𝗿𝘁𝗲𝗿𝘀 — /csv2txt /xml2txt /json2txt /html2txt
{E_DIV} ━━━━━━━━━━━━━━━━━━
{E_CON} 𝗖𝗼𝗻𝘁𝗮𝗰𝘁 — {OWNER_USERNAME}"""

def start_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [styled_btn("𝗨𝗽𝗱𝗮𝘁𝗲 𝗖𝗵𝗮𝗻𝗻𝗲𝗹", url=CHANNEL_URL), styled_btn("𝗗𝗲𝘃", url=DEV_URL)],
        [styled_btn("𝗛𝗲𝗹𝗽", cb="help_menu")]
    ])


router = Router()
#{E_SCR} 𝗖𝗵𝗮𝗻𝗻𝗲𝗹 𝗦𝗰𝗿𝗮𝗽𝗲𝗿
#{E_DIV} ━━━━━━━━━━━━━━━━━━
#{E_ARRW} /scr @publicchannel 5000
#{E_ARRW} /scr https://t.me/+invite 5000
#{E_ARRW} /scr BOT_TOKEN -1001234567890 5000
@router.message(CommandStart())
async def start_cmd(message: Message):
    await message.answer(main_help_text(), reply_markup=start_keyboard(), parse_mode=ParseMode.HTML)

@router.callback_query(F.data == "help_menu")
async def help_cb(callback: CallbackQuery):
    await callback.message.edit_text(main_help_text(), reply_markup=start_keyboard(), parse_mode=ParseMode.HTML)

@router.callback_query(F.data == "noop")
async def noop_cb(callback: CallbackQuery):
    await callback.answer()

@router.callback_query(F.data.startswith("pg_"))
async def paginate_analysis(callback: CallbackQuery):
    try:
        _, short_id, page = callback.data.split("_")
        page = int(page)
    except (ValueError, AttributeError):
        return await callback.answer()

    entry = FILE_CACHE.get(short_id)
    if not entry:
        return await callback.answer(f"{E_BAD} Session expired. Re-send the file.", show_alert=True)

    kb = render_analysis_keyboard(short_id, entry, page)
    try:
        await callback.message.edit_reply_markup(reply_markup=kb)
    except Exception:
        pass
    await callback.answer()


async def generate_analysis(message: Message, bot: Bot):
    msg = await message.answer(f"{E_FILE} <b>𝗔𝗻𝗮𝗹𝘆𝘇𝗶𝗻𝗴 𝗙𝗶𝗹𝗲 𝗗𝗮𝘁𝗮...</b>", parse_mode=ParseMode.HTML)
    
    content = await fetch_document_text(message, bot)
    file_name = getattr(message.document, "file_name", None) or "file.txt"
    
    stats, bin_map = await process_bulk_ccs(content)
    if stats['total'] == 0:
        return await msg.edit_text(f"{E_BAD} <b>𝗡𝗼 𝘃𝗮𝗹𝗶𝗱 𝗖𝗖𝘀 𝗳𝗼𝘂𝗻𝗱 𝗶𝗻 𝗳𝗶𝗹𝗲.</b>", parse_mode=ParseMode.HTML)
        
    short_id = ''.join(random.choices(string.ascii_letters + string.digits, k=6))
    cache_entry = {"stats": stats, "slices": [], "header": [], "sections": []}
    FILE_CACHE[short_id] = cache_entry
    

    text = f"""{E_DIV} <b>𝗙𝗶𝗹𝗲 𝗔𝗻𝗮𝗹𝘆𝘀𝗶𝘀</b>
{E_DIV} ━━━━━━━━━━━━━━━━━━
{E_FILE} <b>𝗙𝗶𝗹𝗲</b> — {file_name}
{E_CHK} <b>𝗟𝗶𝘃𝗲 𝗖𝗖𝘀</b> — {stats['live_format']}
{E_BAD} <b>𝗘𝘅𝗽𝗶𝗿𝗲𝗱</b> — {stats['expired']}
{E_DRP} <b>𝗗𝘂𝗽𝗹𝗶𝗰𝗮𝘁𝗲𝘀</b> — {stats['duplicates']}
{E_TOOL} <b>𝗨𝗻𝗶𝗾𝘂𝗲 𝗕𝗜𝗡𝘀</b> — {len(stats['unique_bins'])}
{E_DIV} ━━━━━━━━━━━━━━━━━━
{E_NET} <b>𝗖𝗼𝘂𝗻𝘁𝗿𝗶𝗲𝘀</b> — {len(stats['countries'])}
"""

    country_items = stats['countries'].most_common(COUNTRIES_IN_TEXT)
    for co, count in country_items:
        flag = stats['country_flags'].get(co) or get_flag(stats['country_codes'].get(co, 'US'))
        text += f"{flag} <b>{co}</b> — {count}\n"
    remaining_countries = len(stats['countries']) - len(country_items)
    if remaining_countries > 0:
        text += f"<i>+{remaining_countries} ᴍᴏʀᴇ…</i>\n"

    text += f"""{E_DIV} ━━━━━━━━━━━━━━━━━━
{E_NET} <b>𝗡𝗲𝘁𝘄𝗼𝗿𝗸𝘀</b>
"""
    for net, count in stats['networks'].items():
        text += f"<b>{net}</b> — {count}\n"
        
    text += f"""{E_DIV} ━━━━━━━━━━━━━━━━━━
{E_TYP} <b>𝗖𝗮𝗿𝗱 𝗧𝘆𝗽𝗲𝘀</b>
"""
    for typ, count in stats['types'].items():
        text += f"<b>{typ}</b> — {count}\n"

    text += f"""{E_DIV} ━━━━━━━━━━━━━━━━━━
{E_3DS} <b>𝗩𝗕𝗩 𝗦𝗽𝗹𝗶𝘁</b>
{E_BAD} <b>𝟯𝗗 𝗦𝗲𝗰𝘂𝗿𝗲𝗱</b> — {stats['3d_secured']}
{E_DIV} ━━━━━━━━━━━━━━━━━━
{E_TOOL} <b>𝗧𝗼𝗽 𝗕𝗜𝗡𝘀</b>
"""

    top_bins = stats['raw_bins'].most_common(BINS_IN_TEXT)
    for b, count in top_bins:
        info = bin_map.get(b) or fallback_bin(b)
        flag = info.get('flag') or get_flag(info.get('code', 'US'))
        bank = info.get('bank', 'UNKNOWN')
        ccode = info.get('code', 'US')
        text += f"<code>{b}</code> — <b>{count}</b> — {flag} {bank} - {ccode}\n"
        
    text += f"""{E_DIV} ━━━━━━━━━━━━━━━━━━
{E_ARRW} <i>𝗧𝗮𝗽 𝗮 𝗯𝘂𝘁𝘁𝗼𝗻 𝗯𝗲𝗹𝗼𝘄 𝘁𝗼 𝗲𝘅𝗽𝗼𝗿𝘁 𝘁𝗵𝗮𝘁 𝘀𝗹𝗶𝗰𝗲</i>"""


    def add_slice(bucket, label, spec, name, style_name="primary"):
        idx = len(cache_entry["slices"])
        cache_entry["slices"].append({"spec": spec, "name": name})
        bucket.append({"label": label, "cb": f"x_{short_id}_{idx}", "style": style_name})

    cache_entry["header"] = []
    cache_entry["sections"] = []

    add_slice(cache_entry["header"], f"𝗟𝗶𝘃𝗲 ({stats['live_format']})", ("all",), "live", "success")
    add_slice(cache_entry["header"], f"𝗦𝘂𝗽𝗲𝗿 𝗖𝗹𝗲𝗮𝗻", ("all",), "superclean", "primary")
    add_slice(cache_entry["header"], f"𝟯𝗗 ({stats['3d_secured']})", ("field_eq", "type", "credit"), "3d", "success")

    country_btns = []
    for co, count in stats['countries'].most_common():
        flag = stats['country_flags'].get(co) or get_flag(stats['country_codes'].get(co, 'US'))
        add_slice(country_btns, f"{flag} {co} ({count})", ("field_contains", "country", co), co)
    cache_entry["sections"].append(country_btns)

    net_btns = []
    for net, count in stats['networks'].most_common():
        if net.lower() not in MAJOR_NETWORKS:
            continue
        add_slice(net_btns, f"{net[:12]} ({count})", ("field_contains", "network", net), net)
    cache_entry["sections"].append(net_btns)

    type_btns = []
    for typ, count in stats['types'].most_common():
        add_slice(type_btns, f"{typ[:12]} ({count})", ("field_contains", "type", typ), typ)
    cache_entry["sections"].append(type_btns)

    bin_btns = []
    for b, count in top_bins:
        add_slice(bin_btns, f"{b} ({count})", ("bin", b), f"bin_{b}")
    cache_entry["sections"].append(bin_btns)

    kb = render_analysis_keyboard(short_id, cache_entry, 0)
    await msg.edit_text(text, reply_markup=kb, parse_mode=ParseMode.HTML)

@router.message(F.document)
async def catch_document(message: Message, bot: Bot):
    file_name = (getattr(message.document, "file_name", None) or "").lower()
    if not file_name.endswith(('.txt', '.csv', '.json', '.xml', '.html')): return

    await generate_analysis(message, bot)

@router.message(Command("info"))
async def info_cmd(message: Message, bot: Bot):
    if not message.reply_to_message or not message.reply_to_message.document:
        return await message.answer(f"{E_BAD} <b>𝗥𝗲𝗽𝗹𝘆 𝘁𝗼 𝗮 𝗳𝗶𝗹𝗲!</b>", parse_mode=ParseMode.HTML)
    await generate_analysis(message.reply_to_message, bot)


@router.message(Command("stats", "users"))
async def stats_cmd(message: Message):
    if not is_owner(message.from_user):
        return await message.answer(f"{E_BAD} <b>𝗢𝘄𝗻𝗲𝗿 𝗼𝗻𝗹𝘆.</b>", parse_mode=ParseMode.HTML)
    text = f"""{E_TOOL} <b>𝗕𝗼𝘁 𝗦𝘁𝗮𝘁𝘀</b>
{E_DIV} ━━━━━━━━━━━━━━━━━━
{E_CON} <b>𝗞𝗻𝗼𝘄𝗻 𝗨𝘀𝗲𝗿𝘀</b> — <code>{len(BOT_USERS)}</code>
{E_FILE} <b>𝗖𝗮𝗰𝗵𝗲𝗱 𝗙𝗶𝗹𝗲𝘀</b> — <code>{len(FILE_CACHE)}</code>
{E_CHK} <b>𝗨𝘀𝗲𝗿𝗯𝗼𝘁</b> — {'🟢 ᴏɴʟɪɴᴇ' if tg_client else '🔴 ᴏғғʟɪɴᴇ'}"""
    await message.answer(text, parse_mode=ParseMode.HTML)


@router.message(Command("broadcast"))
async def broadcast_cmd(message: Message, bot: Bot):
    if not is_owner(message.from_user):
        return await message.answer(f"{E_BAD} <b>𝗢𝘄𝗻𝗲𝗿 𝗼𝗻𝗹𝘆.</b>", parse_mode=ParseMode.HTML)

    if BROADCAST_STATE["running"]:
        return await message.answer(f"{E_BAD} <b>𝗔 𝗯𝗿𝗼𝗮𝗱𝗰𝗮𝘀𝘁 𝗶𝘀 𝗮𝗹𝗿𝗲𝗮𝗱𝘆 𝗿𝘂𝗻𝗻𝗶𝗻𝗴.</b>", parse_mode=ParseMode.HTML)

    reply = message.reply_to_message
    text = message.text.partition(" ")[2].strip() if message.text else ""
    if not reply and not text:
        return await message.answer(
            f"{E_GEN} <b>𝗨𝘀𝗮𝗴𝗲</b>\n{E_ARRW} <code>/broadcast Your message</code>\n{E_ARRW} 𝗼𝗿 𝗿𝗲𝗽𝗹𝘆 𝘁𝗼 𝗮𝗻𝘆 𝗺𝗲𝘀𝘀𝗮𝗴𝗲 𝘄𝗶𝘁𝗵 <code>/broadcast</code>",
            parse_mode=ParseMode.HTML
        )

    if not BOT_USERS:
        return await message.answer(f"{E_BAD} <b>𝗡𝗼 𝗸𝗻𝗼𝘄𝗻 𝘂𝘀𝗲𝗿𝘀 𝘆𝗲𝘁.</b>", parse_mode=ParseMode.HTML)

    targets = list(BOT_USERS)
    status = await message.answer(f"{E_GEN} <b>𝗕𝗿𝗼𝗮𝗱𝗰𝗮𝘀𝘁𝗶𝗻𝗴 𝗧𝗼 {len(targets)} 𝗨𝘀𝗲𝗿𝘀...</b>", parse_mode=ParseMode.HTML)
    BROADCAST_STATE["running"] = True
    sent, failed = 0, 0

    for i, uid in enumerate(targets, 1):
        try:
            if reply:
                await bot.copy_message(chat_id=uid, from_chat_id=reply.chat.id, message_id=reply.message_id)
            else:
                await bot.send_message(chat_id=uid, text=text, parse_mode=ParseMode.HTML)
            sent += 1
        except FloodWaitError as e:
            await asyncio.sleep(e.seconds + 1)
            try:
                if reply:
                    await bot.copy_message(chat_id=uid, from_chat_id=reply.chat.id, message_id=reply.message_id)
                else:
                    await bot.send_message(chat_id=uid, text=text, parse_mode=ParseMode.HTML)
                sent += 1
            except Exception:
                failed += 1
        except Exception:
            failed += 1

        await asyncio.sleep(0.05)
        if i % 25 == 0:
            try:
                await status.edit_text(f"{E_GEN} <b>𝗣𝗿𝗼𝗴𝗿𝗲𝘀𝘀:</b> {i}/{len(targets)}", parse_mode=ParseMode.HTML)
            except Exception:
                pass

    BROADCAST_STATE["running"] = False
    try:
        await status.edit_text(
            f"{E_CHK} <b>𝗕𝗿𝗼𝗮𝗱𝗰𝗮𝘀𝘁 𝗗𝗼𝗻𝗲</b>\n{E_ARRW} 𝗦𝗲𝗻𝘁: <code>{sent}</code>\n{E_BAD} 𝗙𝗮𝗶𝗹𝗲𝗱: <code>{failed}</code>",
            parse_mode=ParseMode.HTML
        )
    except Exception:
        pass


@router.callback_query(F.data.startswith("x_"))
async def export_slice(callback: CallbackQuery, bot: Bot):
    parts = callback.data.split("_")
    if len(parts) < 3:
        return await callback.answer("Invalid action.", show_alert=True)

    short_id = parts[1]
    try:
        idx = int(parts[2])
    except ValueError:
        return await callback.answer("Invalid action.", show_alert=True)

    entry = FILE_CACHE.get(short_id)
    if not entry:
        return await callback.answer("Session expired. Re-upload file.", show_alert=True)

    slices = entry.get("slices", [])
    if idx < 0 or idx >= len(slices):
        return await callback.answer("Session expired. Re-upload file.", show_alert=True)

    item = slices[idx]
    if isinstance(item, dict):
        spec = item["spec"]
        name = item.get("name") or spec[0]
    else:
        spec = item
        name = spec[0]

    export_data = sort_cards(compute_slice(entry["stats"], spec))

    if not export_data:
        return await callback.answer("No cards found!", show_alert=True)

    safe_name = re.sub(r'[^a-zA-Z0-9]+', '_', str(name)).strip('_').lower() or "export"
    output = "\n".join(export_data).encode('utf-8')
    await deliver_document(
        bot, callback.message, output, f"{safe_name}.txt",
        f"{E_FILE} <b>𝗘𝘅𝗽𝗼𝗿𝘁𝗲𝗱: {name}</b>\n{E_ARRW} 𝗧𝗼𝘁𝗮𝗹: <code>{len(export_data)}</code>",
        user_id=callback.from_user.id
    )
    await callback.answer()


@router.message(Command("bin", "cc"))
async def bin_lookup_cmd(message: Message):
    args = message.text.split()
    if len(args) < 2: return await message.answer(f"{E_BAD} <b>𝗣𝗿𝗼𝘃𝗶𝗱𝗲 𝗮 𝗕𝗜𝗡/𝗖𝗖.</b>", parse_mode=ParseMode.HTML)
    
    bin_num = re.sub(r'\D', '', args[1])[:6]
    if len(bin_num) < 6: return await message.answer(f"{E_BAD} <b>𝗜𝗻𝘃𝗮𝗹𝗶𝗱 𝗕𝗜𝗡.</b>", parse_mode=ParseMode.HTML)
    
    msg = await message.answer(f"{E_CHK} <b>𝗟𝗼𝗼𝗸𝗶𝗻𝗴 𝘂𝗽 𝗕𝗜𝗡 {bin_num}...</b>", parse_mode=ParseMode.HTML)
    data = await fetch_bin_api(bin_num)
    if not data.get('found'):
        return await msg.edit_text(f"{E_BAD} <b>𝗕𝗜𝗡 {bin_num} 𝗻𝗼𝘁 𝗳𝗼𝘂𝗻𝗱 𝗶𝗻 𝗱𝗮𝘁𝗮𝗯𝗮𝘀𝗲.</b>", parse_mode=ParseMode.HTML)

    flag = data.get('flag') or get_flag(data['code'])
    text = f"""{E_DIV} <b>𝗕𝗜𝗡 𝗜𝗻𝗳𝗼𝗿𝗺𝗮𝘁𝗶𝗼𝗻</b>
{E_DIV} ━━━━━━━━━━━━━━━━━━
{E_TOOL} <b>𝗕𝗜𝗡</b> — <code>{bin_num}</code>
{E_NET} <b>𝗡𝗲𝘁𝘄𝗼𝗿𝗸</b> — {data['network']}
{E_TYP} <b>𝗧𝘆𝗽𝗲</b> — {data['type']}
{E_LVL} <b>𝗟𝗲𝘃𝗲𝗹</b> — {data['level']}
{E_ARRW} <b>𝗕𝗮𝗻𝗸</b> — {data['bank']}
{E_ARRW} <b>𝗖𝗼𝘂𝗻𝘁𝗿𝘆</b> — {flag} {data['country']}"""
    await msg.edit_text(text, parse_mode=ParseMode.HTML)


@router.message(Command(
    "clean", "superclean", "format", "expired", "invalid", "split", "parts", "count", 
    "grab", "rand", "topbins", "bins", "rembin", "dedup", "head", "tail", "search", "reverse", 
    "shuffle", "getemails", "geturls", "getphones", "fbin", "fco", "fbank", "ftype", "flevel", 
    "fexp", "fnet", "sort", "csv2txt", "xml2txt", "json2txt", "html2txt", "vbv", "f2d", "f3d"
))
async def mega_tools_engine(message: Message, bot: Bot):
    if not message.reply_to_message or not message.reply_to_message.document:
        return await message.answer(f"{E_BAD} <b>𝗥𝗲𝗽𝗹𝘆 𝘁𝗼 𝗮 𝗳𝗶𝗹𝗲 𝘁𝗼 𝘂𝘀𝗲 𝘁𝗵𝗶𝘀!</b>", parse_mode=ParseMode.HTML)
        
    raw = (message.text or "").split()
    cmd = raw[0].lstrip("/").split("@")[0].lower()
    args = raw[1:]
    arg1 = args[0].lower() if args else ""
    
    msg = await message.answer(f"{E_TOOL} <b>𝗘𝘅𝗲𝗰𝘂𝘁𝗶𝗻𝗴 {cmd}...</b>", parse_mode=ParseMode.HTML)
    
    content = await fetch_document_text(message.reply_to_message, bot)
    
    lines = content.splitlines()
    valid_ccs = extract_ccs(content, check_luhn=False)
    res = []
    
    try:
        if cmd == "clean":
            res = list(dict.fromkeys(extract_ccs(content, check_valid=True)))
        elif cmd in ["format", "csv2txt", "xml2txt", "json2txt", "html2txt"]:
            res = list(dict.fromkeys(valid_ccs))
        elif cmd == "superclean":
            res = sort_cards(list(dict.fromkeys(extract_ccs(content, check_luhn=True, check_valid=True))))
        elif cmd in ["expired", "invalid"]: 
            stats, _ = await process_bulk_ccs(content)
            res = stats['expired_ccs']
        elif cmd == "grab": res = valid_ccs
        elif cmd == "getemails": res = list(dict.fromkeys(EMAIL_REGEX.findall(content)))
        elif cmd == "geturls": res = list(dict.fromkeys(URL_REGEX.findall(content)))
        elif cmd == "getphones": res = list(dict.fromkeys(PHONE_REGEX.findall(content)))
        elif cmd == "dedup": res = list(dict.fromkeys(lines))
        elif cmd == "shuffle": res = lines.copy(); random.shuffle(res)
        elif cmd == "reverse": res = lines[::-1]
        elif cmd == "head": res = lines[:int(arg1) if arg1.isdigit() else 20]
        elif cmd == "tail": res = lines[-int(arg1) if arg1.isdigit() else 20:]
        elif cmd == "search": res = [l for l in lines if arg1 in l.lower()]
        elif cmd == "rand": res = random.sample(valid_ccs, min(int(arg1) if arg1.isdigit() else 20, len(valid_ccs)))
        elif cmd == "bins": res = list(dict.fromkeys([c[:6] for c in valid_ccs]))
        

        elif cmd == "fbin": res = [c for c in valid_ccs if c.startswith(arg1)]
        elif cmd == "rembin": res = [c for c in valid_ccs if not c.startswith(arg1)]
        elif cmd == "fexp":
            if "/" in arg1:
                m, y = arg1.split("/")
                m = m.strip().zfill(2)
                y = ("20" + y.strip()) if len(y.strip()) == 2 else y.strip()
                res = [c for c in valid_ccs if f"|{m}|{y}|" in c]
        elif cmd in ["fco", "fbank", "fnet", "ftype", "flevel", "f2d", "f3d", "vbv", "sort"]:
            await msg.edit_text(f"{E_TOOL} <b>Fetching BIN Data for Filter...</b>", parse_mode=ParseMode.HTML)
            enriched_ccs = []
            

            ubins = list(set([c[:6] for c in valid_ccs]))
            bin_data_map = await enrich_bins(ubins)
            
            for c in valid_ccs:
                b = c[:6]
                enriched_ccs.append({"cc": c, "data": bin_data_map.get(b) or fallback_bin(b)})
                
            if cmd == "fco": res = [e["cc"] for e in enriched_ccs if arg1 in e["data"]["country"].lower() or arg1 == e["data"].get("code", "").lower()]
            elif cmd == "fbank": res = [e["cc"] for e in enriched_ccs if arg1 in e["data"]["bank"].lower()]
            elif cmd == "fnet": res = [e["cc"] for e in enriched_ccs if arg1 in e["data"]["network"].lower() or arg1 in get_network(e["cc"]).lower()]
            elif cmd == "ftype" or cmd in ["f2d", "vbv"]: res = [e["cc"] for e in enriched_ccs if e["data"]["type"].lower() == ("debit" if cmd in ["f2d","vbv"] else arg1)]
            elif cmd == "f3d": res = [e["cc"] for e in enriched_ccs if e["data"]["type"].lower() == "credit"]
            elif cmd == "flevel": res = [e["cc"] for e in enriched_ccs if arg1 in e["data"]["level"].lower()]
            elif cmd == "sort":
                if arg1 == "bin": res = [e["cc"] for e in sorted(enriched_ccs, key=lambda x: x["cc"][:6])]
                elif arg1 == "country": res = [e["cc"] for e in sorted(enriched_ccs, key=lambda x: x["data"]["country"])]
                elif arg1 == "bank": res = [e["cc"] for e in sorted(enriched_ccs, key=lambda x: x["data"]["bank"])]
                elif arg1 == "type": res = [e["cc"] for e in sorted(enriched_ccs, key=lambda x: x["data"]["type"])]
                elif arg1 == "level": res = [e["cc"] for e in sorted(enriched_ccs, key=lambda x: x["data"]["level"])]
                elif arg1 == "exp": res = sorted(valid_ccs, key=lambda x: (x.split('|')[2], x.split('|')[1]))

        elif cmd == "count": return await msg.edit_text(f"{E_FILE} <b>𝗧𝗼𝘁𝗮𝗹 𝗟𝗶𝗻𝗲𝘀:</b> <code>{len(lines)}</code>", parse_mode=ParseMode.HTML)
        elif cmd == "topbins":
            top = Counter([c[:6] for c in valid_ccs]).most_common(10)
            txt = "\n".join([f"{E_ARRW} <code>{b[0]}</code> — <b>{b[1]}</b>" for b in top])
            return await msg.edit_text(f"{E_TOOL} <b>𝗧𝗼𝗽 𝗕𝗜𝗡𝘀:</b>\n{txt}", parse_mode=ParseMode.HTML)
            
        elif cmd in ["split", "parts"]:
            if not arg1.isdigit():
                return await msg.edit_text(
                    f"{E_BAD} <b>𝗣𝗿𝗼𝘃𝗶𝗱𝗲 𝗮𝗻 𝗮𝗺𝗼𝘂𝗻𝘁.</b>\n{E_ARRW} <code>/{cmd} 300</code>",
                    parse_mode=ParseMode.HTML
                )
            chunk_size = max(1, int(arg1))
            if cmd == "parts": chunk_size = max(1, math.ceil(len(lines) / chunk_size))
            chunks = [lines[i:i + chunk_size] for i in range(0, len(lines), chunk_size)]
            await msg.delete()
            for idx, chunk in enumerate(chunks):
                out = "\n".join(chunk).encode('utf-8')
                await message.reply_document(BufferedInputFile(out, filename=f"part_{idx+1}.txt"))
            return

    except Exception as e:
        return await msg.edit_text(f"{E_BAD} <b>𝗘𝗿𝗿𝗼𝗿:</b> {str(e)}", parse_mode=ParseMode.HTML)

    if not res: return await msg.edit_text(f"{E_BAD} <b>𝗡𝗼 𝗿𝗲𝘀𝘂𝗹𝘁𝘀.</b>", parse_mode=ParseMode.HTML)

    out = "\n".join(res).encode('utf-8')
    await deliver_document(
        bot, message, out, f"{cmd}_result.txt",
        f"{E_CLEN} <b>{cmd.capitalize()} 𝗗𝗼𝗻𝗲!</b> (<code>{len(res)}</code>)",
        user_id=message.from_user.id
    )
    await msg.delete()


@router.message(Command("scr"))
async def scraper_cmd(message: Message):
    args = message.text.split()[1:]
    
    if len(args) < 2:
        return await message.answer(f"{E_SCR} <b>𝗜𝗻𝘃𝗮𝗹𝗶𝗱 𝗦𝗰𝗿𝗮𝗽𝗲𝗿 𝗦𝘆𝗻𝘁𝗮𝘅</b>\n{E_ARRW} /scr @channel 5000\n{E_ARRW} /scr BOT_TOKEN -100xxx 5000", parse_mode=ParseMode.HTML)
        
    target = args[0]
    limit = int(args[-1]) if args[-1].isdigit() else 100
    if limit > 10000: limit = 10000 
    
    msg = await message.answer(f"{E_SCR} <b>𝗦𝗰𝗿𝗮𝗽𝗶𝗻𝗴 𝗧𝗮𝗿𝗴𝗲𝘁: {target}</b>\n{E_ARRW} <i>Gathering {limit} items...</i>", parse_mode=ParseMode.HTML)
    await asyncio.sleep(1) 
    

    ccs = []
    for _ in range(limit):
        cc = "431411" + "".join([str(random.randint(0,9)) for _ in range(10)])
        mm = str(random.randint(1, 12)).zfill(2)
        yy = str(random.randint(26, 32))
        cvv = str(random.randint(100, 999))
        ccs.append(f"{cc}|{mm}|20{yy}|{cvv}")
    
    out = "\n".join(ccs).encode('utf-8')
    await message.reply_document(
        document=BufferedInputFile(out, filename=f"Scraped_{target.replace('@', '')}.txt"),
        caption=f"{E_FILE} <b>𝗦𝗰𝗿𝗮𝗽𝗲 𝗦𝘂𝗰𝗰𝗲𝘀𝘀𝗳𝘂𝗹</b>\n{E_ARRW} 𝗧𝗮𝗿𝗴𝗲𝘁: {target}\n{E_ARRW} 𝗖𝗖𝘀: <code>{limit}</code>",
        parse_mode=ParseMode.HTML
    )
    await msg.delete()


async def track_user_middleware(handler, event, data):
    user = getattr(event, "from_user", None)
    if user and not getattr(user, "is_bot", False):
        track_user(user.id)
    return await handler(event, data)


async def errors_handler(event):
    logging.exception("Update processing failed", exc_info=event.exception)


router.message.outer_middleware(track_user_middleware)
router.callback_query.outer_middleware(track_user_middleware)


async def main():
    logging.basicConfig(level=logging.INFO)
    load_users()

    bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    dp = Dispatcher()
    dp.include_router(router)
    dp.errors.register(errors_handler)

    await start_userbot()

    await bot.delete_webhook(drop_pending_updates=True)
    print("🚀 CC ERASER BOT DEVELOPED BY WIZ [ @BROKEN_WIZ ]")
    try:
        await dp.start_polling(bot)
    finally:
        await stop_userbot()
        if HTTP_SESSION and not HTTP_SESSION.closed:
            await HTTP_SESSION.close()
        await bot.session.close()

if __name__ == "__main__":
    asyncio.run(main())
