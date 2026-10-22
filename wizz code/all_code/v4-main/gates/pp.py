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
from database import is_gate_enabled, get_user_credits, update_credits, get_db_connection
from bin import get_bin_info
from sub import get_premium_status

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# PAYPAL CHECKER IMPORT
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
try:
    from gates.paypal_cvv import run_paypal_check
except ImportError:
    from paypal_cvv import run_paypal_check

_PP_CVV_OK = callable(run_paypal_check)

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
# CONFIGURATION & PROXIES
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

PP_AMOUNT   = "1"
PP_CURRENCY = "USD"

PROXIES = [
    "103.183.121.128:58122:3dfw7c6x:oSeqx0CNeV0k",
    "103.183.121.211:11657:azqdr5vn:71WCPuMwyc72",
    "103.183.121.59:34219:y7g4dd8d:Buw96jtGFKA5",
    "103.156.91.173:58798:zqrn9y5d:zQRN9y5d",
    "103.161.113.230:18491:dz46cabj:ksuRcKlNqJMU",
    "82.117.94.14:63126:RrkJjUqfT:jYEH6Emdg",
    "193.254.17.97:64708:1DnugnypC:4yPtzMd3f",
    "194.33.9.114:64170:nWtrJqsb:RYYEE72Y",
    "194.33.9.136:49520:nWtrJqsb:RYYEE72Y",
    "135.148.117.75:59813:oldg6k2r:oLdG6k2R",
]

MAX_PROXY_ATTEMPTS = 4

# Custom Emoji IDs
CUSTOM_CHARGED_EMOJI_ID   = "4956719506027185156"
CUSTOM_APPROVED_EMOJI_ID  = "4958610528588008305"
CUSTOM_DECLINED_EMOJI_ID  = "4956612582816351459"

user_last_command_time = {}

router = Router()

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# DECLINE CODE — LIVE-CARD SIGNALS
# Codes in this set mean the bank actually responded and the
# card is real. We surface them as APPROVED (live) even though
# PayPal reports DECLINED, because the card itself is valid.
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
LIVE_CARD_CODES = {
    "INSUFFICIENT_FUNDS",
    "INSUFFICIENT_FUND",
    "NOT_ENOUGH_BALANCE",
}

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# DECLINE CODE EXTRACTION (UI SAFETY NET)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
_DECLINE_CODE_RE = re.compile(r'\b([A-Z][A-Z0-9_]{3,})\b')

_DECLINE_STOPWORDS = {
    "PAYPAL", "ORDER", "HAS", "BEEN", "DECLINED", "TRANSACTION",
    "STATUS", "FOR", "VISA", "MASTERCARD", "DISCOVER", "AMERICAN",
    "EXPRESS", "CARD", "HOLDER", "THE", "ADDRESS", "AND", "POSTAL",
    "CODE", "ARE", "BOTH", "INCORRECT", "CVV2", "CSC", "MATCHES",
    "NOTHING", "SERVICE", "IS", "UNAVAILABLE", "INFORMATION",
    "AVAILABLE", "MAESTRO", "CHECKED", "OR", "ACQUIRER", "HAD",
    "NO", "RESPONSE", "WAS", "PROCESSED", "ANOTHER", "DO", "RETRY",
    "SAME", "TRY", "USING",
}

def shorten_decline(text: str) -> str:
    """Reduce PayPal's verbose description to just the SCREAMING_SNAKE code."""
    if not text:
        return text
    for token in _DECLINE_CODE_RE.findall(text):
        if token not in _DECLINE_STOPWORDS and "_" in token:
            return token
    for token in _DECLINE_CODE_RE.findall(text):
        if token not in _DECLINE_STOPWORDS:
            return token
    return text

def is_valid_decline_code(text: str) -> bool:
    """True if the string looks like a clean SCREAMING_SNAKE code."""
    if not text:
        return False
    return bool(re.fullmatch(r'[A-Z][A-Z0-9_]{3,}', text))

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# DATABASE INITIALIZATION
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def ensure_stats_columns():
    """Ensures cc_checked and cc_charged columns exist in users table."""
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
        print("[DB] PP Stats columns checked/created.")
    except Exception as e:
        print(f"[DB] Error checking stats columns: {e}")

ensure_stats_columns()

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# HELPERS
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

async def update_user_stats(user_id, is_charged):
    """Increments cc_checked and optionally cc_charged in database."""
    def _sync_update():
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("UPDATE users SET cc_checked = cc_checked + 1 WHERE user_id = %s", (user_id,))
        if is_charged:
            cursor.execute("UPDATE users SET cc_charged = cc_charged + 1 WHERE user_id = %s", (user_id,))
        conn.commit()
        conn.close()

    await asyncio.to_thread(_sync_update)

async def get_user_plan_name(user_id):
    """Fetches specific plan name from receipts if premium, else FREE."""
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

def escape_html(text: str) -> str:
    """Escape HTML special characters to avoid Telegram parse errors."""
    if not text:
        return text
    return (text.replace('&', '&amp;')
                .replace('<', '&lt;')
                .replace('>', '&gt;')
                .replace('"', '&quot;'))

def build_user_link(user_obj) -> str:
    """Builds a clickable user mention link."""
    name = escape(user_obj.first_name or "User")
    if user_obj.username:
        return f'<a href="https://t.me/{escape(user_obj.username)}">{name}</a>'
    return f'<a href="tg://user?id={user_obj.id}">{name}</a>'

def _proxy_level_failure(result) -> bool:
    """True when the check failed for a proxying/network reason."""
    if str(result.get("status", "")).upper() != "ERROR":
        return False
    text = (
        f'{result.get("response") or ""} '
        f'{result.get("decline_description") or ""} '
        f'{result.get("raw") or ""}'
    ).lower()
    return any(k in text for k in (
        "token", "nonce", "proxy", "dead", "timeout",
        "connection", "retries", "failed to load", "order failed",
        "transaction failed",
    ))

def _random_billing() -> dict:
    """Random billing details for each PayPal check."""
    first_names = ["John","James","Michael","David","Robert","William","Mary","Linda","Sarah","Jessica"]
    last_names  = ["Smith","Johnson","Williams","Brown","Jones","Garcia","Miller","Davis","Rodriguez","Martinez"]
    streets     = ["476 West White Mountain Blvd","123 Main St","Oak Ave","Maple Rd","Pine Ln","Lake Shore Dr","Washington Blvd"]
    cities      = ["Pinetop","New York","Los Angeles","Chicago","Houston","Phoenix","San Diego","Philadelphia"]
    states      = ["AZ","CA","NY","TX","FL","IL","PA","GA"]
    zips        = ["85929","10001","90210","60601","77001","85001","92101","19101"]
    return {
        "firstName": random.choice(first_names),
        "lastName":  random.choice(last_names),
        "email":     f"wiz{random.randint(1000, 99999)}@gmail.com",
        "phone":     f"+1{random.randint(200, 999)}{random.randint(200, 999)}{random.randint(1000, 9999)}",
        "address1":  random.choice(streets),
        "address2":  "",
        "city":      random.choice(cities),
        "state":     random.choice(states),
        "zip":       random.choice(zips),
        "country":   "US",
        "amount":    PP_AMOUNT,
        "currency":  PP_CURRENCY,
    }

def _resolve_ui_response(result: dict) -> str:
    """
    Resolve what goes on the UI `Raw ➵` line.
    Priority: clean code > extracted code > raw response.
    """
    dd = result.get("decline_description")
    rs = result.get("response")

    if dd and is_valid_decline_code(dd):
        return dd

    if dd:
        extracted = shorten_decline(dd)
        if extracted and extracted != dd and is_valid_decline_code(extracted):
            return extracted

    if rs:
        extracted = shorten_decline(rs)
        if is_valid_decline_code(extracted):
            return extracted
        return rs

    return "N/A"

def _is_live_card(result: dict) -> bool:
    """
    True when the decline reason indicates the card is real
    (bank responded). Currently: insufficient funds family.
    """
    for key in ("decline_description", "decline_code", "response"):
        val = result.get(key)
        if val and str(val).upper() in LIVE_CARD_CODES:
            return True
    return False

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# COMMAND HANDLER
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

@router.message(F.text.startswith("/pp"))
async def pp_command(message: types.Message):
    # 1. GATE CHECK
    if not await asyncio.to_thread(is_gate_enabled, "pp"):
        await message.reply(
            "🚧 <b>𝗣𝗮𝘆𝗣𝗮𝗹 𝟭$ 𝗚𝗮𝘁𝗲 𝗶𝘀 𝘂𝗻𝗱𝗲𝗿 𝗺𝗮𝗶𝗻𝘁𝗲𝗻𝗮𝗻𝗰𝗲.</b>\n"
            "𝗔𝗻𝗱 𝘄𝗶𝗹𝗹 𝗯𝗲 𝗳𝗶𝘅𝗲𝗱 𝘀𝗼𝗼𝗻.",
            parse_mode="HTML"
        )
        return

    user = message.from_user
    user_id = user.id
    current_time = time.time()

    # 2. PLUGIN AVAILABILITY CHECK
    if not _PP_CVV_OK:
        await message.reply(
            "🚧 <b>𝗣𝗮𝘆𝗣𝗮𝗹 𝗰𝗵𝗲𝗰𝗸𝗲𝗿 𝗶𝘀 𝘂𝗻𝗮𝘃𝗮𝗶𝗹𝗮𝗯𝗹𝗲.</b>\n"
            "𝗧𝗵𝗲 𝗽𝗮𝘆𝗽𝗮𝗹_𝗰𝘃𝘃 𝗺𝗼𝗱𝘂𝗹𝗲 𝗰𝗼𝘂𝗹𝗱𝗻'𝘁 𝗯𝗲 𝗹𝗼𝗮𝗱𝗲𝗱.",
            parse_mode="HTML"
        )
        return

    # 3. GET PREMIUM STATUS
    is_premium, _ = await asyncio.to_thread(get_premium_status, user_id)

    # 4. RATE LIMITING CHECK
    if not is_premium:
        if user_id in user_last_command_time:
            elapsed = current_time - user_last_command_time[user_id]
            if elapsed < 10:
                remaining_time = round(10 - elapsed, 1)
                await message.reply(
                    f"<tg-emoji emoji-id=\"6255910249362885846\">⚠️</tg-emoji> <b>Aᴄᴛɪᴠᴇ Cᴏᴏʟᴅᴏᴡɴ !</b>\n\n"
                    f"<b>Pʟᴇᴀsᴇ Wᴀɪᴛ <code>{remaining_time}</code> Sᴇᴄᴏɴᴅs Bᴇғᴏʀᴇ Cᴏɴᴛɪɴᴜɪɴɢ.</b>\n\n"
                    f"<tg-emoji emoji-id=\"6136275172283391020\">⭐</tg-emoji> <b>Pᴜʀᴄʜᴀsᴇ Pʀᴇᴍɪᴜᴍ Pʟᴀɴ Fᴏʀ Usᴇ Cᴏᴍᴍᴀɴᴅs Wɪᴛʜᴏᴜᴛ Cᴏᴏʟᴅᴏᴡɴ.</b>",
                    parse_mode="HTML"
                )
                return

        user_last_command_time[user_id] = current_time

    # 5. Extract Card Details
    parts = message.text.split(maxsplit=1)
    raw_text = ""

    if len(parts) > 1:
        raw_text = parts[1].strip()

    if message.reply_to_message:
        raw_text += " " + (message.reply_to_message.text or message.reply_to_message.caption or "")

    if not raw_text.strip():
        await message.reply(
            "<tg-emoji emoji-id=\"4956612582816351459\">❌</tg-emoji> <b>Usage:</b> /pp <code>cc|mm|yy|cvv</code>\n"
            "Or reply to a message containing card details.",
            parse_mode="HTML"
        )
        return

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

    yy = yy_raw[2:] if len(yy_raw) == 4 else yy_raw

    formatted_cc = f"{cc}|{mm}|{yy}|{cvv}"

    # 6. LUHN CHECK
    if not luhn_check(cc):
        await message.reply(
            "<tg-emoji emoji-id=\"4956612582816351459\">❌</tg-emoji> <b>Invalid Card</b>\n"
            "Your card number is incorrect.",
            parse_mode="HTML"
        )
        return

    # 7. Check Credits
    current_credits = await asyncio.to_thread(get_user_credits, user_id)
    if current_credits is None or current_credits <= 0:
        await message.reply(
            "<tg-emoji emoji-id=\"4956612582816351459\">❌</tg-emoji> <b>Iɴsᴜғғɪᴄɪᴇɴᴛ Cʀᴇᴅɪᴛs</b>\n\n"
            "Yᴏᴜ Nᴇᴇᴅ Aᴛ Lᴇᴀsᴛ <b>1 Cʀᴇᴅɪᴛ</b> Tᴏ Usᴇ Tʜɪs Gᴀᴛᴇ.\n"
            "Usᴇ /plan Tᴏ Gᴇᴛ Mᴏʀᴇ.",
            parse_mode="HTML"
        )
        return

    # 8. Fetch Plan Name
    plan_name = await get_user_plan_name(user_id)

    # 9. Send Processing Message
    escaped_card = escape(formatted_cc)
    proc_msg = await message.reply(
        f"<b>Pʀᴏᴄᴇssɪɴɢ...</b><tg-emoji emoji-id=\"6154603635981423575\">⏳</tg-emoji>\n"
        f"<pre><code>{escaped_card}</code></pre>\n"
        f"<b>Gᴀᴛᴇ ➵ PᴀʏPᴀʟ 1$</b>\n",
        parse_mode="HTML"
    )

    # 10. Execute Background Task
    asyncio.create_task(
        process_pp_check(
            message, proc_msg, user, user_id, formatted_cc, cc, plan_name
        )
    )

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# BACKGROUND PROCESSOR
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

async def process_pp_check(message, proc_msg, user, user_id, formatted_cc, cc, plan_name):
    """
    Runs the PayPal check, updates DB, posts result.
    Live-card codes (INSUFFICIENT_FUNDS etc.) render as APPROVED
    even though PayPal reports DECLINED.
    """
    parts = formatted_cc.split('|')
    cc_num, mm, yy, cvv = parts[0], parts[1], parts[2], parts[3]

    check_started = time.time()

    # A. REAL PAYPAL CHECK (proxy rotation)
    result = {
        "status": "ERROR",
        "response": "Checker unavailable",
        "decline_description": None,
        "time_take": 0.0,
    }

    if _PP_CVV_OK:
        used_proxies = set()
        for attempt in range(MAX_PROXY_ATTEMPTS):
            proxy_pool = [p for p in PROXIES if p not in used_proxies]
            if not proxy_pool:
                break

            proxy_str = random.choice(proxy_pool)
            used_proxies.add(proxy_str)
            billing = _random_billing()

            try:
                result = await asyncio.to_thread(
                    run_paypal_check,
                    cc_num, mm, yy, cvv,
                    None, proxy_str=proxy_str, **billing
                )
            except Exception as e:
                logging.error(f"PayPal check error: {e}")
                result = {
                    "status": "ERROR",
                    "response": str(e)[:120],
                    "decline_description": None,
                    "time_take": 0.0,
                }

            if not _proxy_level_failure(result):
                break

            logging.warning(
                f"[PP] attempt {attempt + 1} failed (proxy-level), rotating..."
            )

    # B. Bin Lookup
    try:
        bin_info = await get_bin_info(cc[:6])
    except Exception:
        bin_info = {}

    bin_scheme = bin_info.get("scheme", "N/A")
    bin_bank   = bin_info.get("bank", "N/A")

    country_name = bin_info.get("country", "N/A")
    country_flag = bin_info.get("country_emoji", "")
    bin_country  = f"{country_flag} {country_name}" if country_flag else country_name
    type         = bin_info.get("type") or "N/A"

    # C. Determine Final Status (with live-card override)
    status_raw = str(result.get("status", "ERROR")).upper()

    is_charged = False
    is_live    = False

    if status_raw == "CHARGED":
        final_status = f'<b>ᏟꮋꭺꭱƦᏽꭼꭰ</b> <tg-emoji emoji-id="{CUSTOM_APPROVED_EMOJI_ID}">✅</tg-emoji>'
        is_charged = True

    elif status_raw == "DECLINED" and _is_live_card(result):
        final_status = f'<b>ᎪꮲꮲꭱƦꮎꮩꭼꭰ</b> <tg-emoji emoji-id="{CUSTOM_APPROVED_EMOJI_ID}">✅</tg-emoji>'
        is_live = True

    elif status_raw == "DECLINED":
        final_status = f'<b>Ꭰᴇᴄʟɪɴᴇᴅ</b> <tg-emoji emoji-id="{CUSTOM_DECLINED_EMOJI_ID}">❌</tg-emoji>'

    else:
        final_status = "<b>Ꭼʀʀᴏʀ</b> / Ꭲɪᴍᴇᴏᴜᴛ ⚠️"

    # D. Resolve UI response — code only
    ui_response = _resolve_ui_response(result)
    formatted_response = escape_html(ui_response)

    # E. CREDIT DEDUCTION
    if is_charged:
        credits_to_deduct = 2
    elif is_live:
        credits_to_deduct = 1
    else:
        credits_to_deduct = 1

    if credits_to_deduct > 0:
        try:
            current_balance = await asyncio.to_thread(get_user_credits, user_id)
            new_balance = current_balance - credits_to_deduct
            if new_balance < 0:
                new_balance = 0
            await asyncio.to_thread(update_credits, user_id, new_balance)
        except Exception as e:
            logging.error(f"Credit deduction error: {e}")

    # F. UPDATE STATS
    try:
        await update_user_stats(user_id, is_charged)
    except Exception as e:
        logging.error(f"Stats update error: {e}")

    # G. Build Final Caption
    user_link = build_user_link(user)
    dev_link  = dev_badge()

    user_display = f"{user_link} {plan_badge(plan_name)}"

    elapsed = time.time() - check_started

    final_caption = (
        f'<b><a href="https://t.me/broken_wiz">[⌭]</a> Sᴛᴀᴛᴜs ➵ {final_status}</b>\n'
        f'<tg-emoji emoji-id="5920055227133725805">💳</tg-emoji>\n'
        f"⤷ <code>{escape_html(formatted_cc)}</code>\n"
        f"━━━━━━━━━━━\n"
        f'<b><a href="https://t.me/broken_wiz">⬢</a> Gᴀᴛᴇ ➵ PᴀʏPᴀʟ 1$</b>\n'
        f'<b><a href="https://t.me/broken_wiz">⬡</a> Rᴀᴡ ➵ {formatted_response}</b>\n'
        f"━━━━━━━━━━━\n"
        f"<b>Tʏᴘᴇ ➵</b> <code>[ {escape_html(type)} ]</code>\n"
        f"<b>Iɴꜰᴏ ➵</b> <code>{escape_html(bin_scheme)} - {escape_html(bin_bank)} - {escape_html(bin_country)}</code>\n"
        f"━━━━━━━━━━━\n"
        f"<tg-emoji emoji-id=\"5440621591387980068\">🔜</tg-emoji> <b>➵ {elapsed:.2f}s</b>\n"
        f"<tg-emoji emoji-id=\"6028240037366207289\">👤</tg-emoji> <b>➵ {user_display}</b>\n"
        f"<tg-emoji emoji-id=\"5429615084856969948\">🏴‍☠️</tg-emoji> <b>➵ {dev_link}</b>"
    )

    # H. FETCH ANIME GIF
    gif_url = await get_anime_gif()

    # I. Send as Animation (GIF) with Caption
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
        logging.warning(f"[PP] Could not send GIF, falling back to text: {e}")
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