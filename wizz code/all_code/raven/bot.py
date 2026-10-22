from telethon.errors import (
    UserNotParticipantError,
    ChannelPrivateError,
    FloodWaitError,
    UserIsBlockedError,
    PeerIdInvalidError,
    InputUserDeactivatedError,
    UserDeactivatedError,
    UserDeactivatedBanError,
    ChatWriteForbiddenError,
    QueryIdInvalidError,
    MessageNotModifiedError,
)
from telethon import TelegramClient, events, Button
from telethon.tl.types import (
    MessageEntityCustomEmoji, ChannelParticipantBanned, ChannelParticipantLeft,
    MessageMediaPhoto, MessageMediaDocument,
    DocumentAttributeVideo, DocumentAttributeAnimated,
)
from telethon.tl.functions.channels import GetParticipantRequest
from telethon.extensions import html as thtml
import asyncio
import itertools
import aiohttp
import aiofiles
import os
import random
import time
import json
import re
import string
import logging
import html
import uuid
import hmac
import hashlib
from datetime import datetime, timedelta, timezone
from urllib.parse import urlparse, quote, urlencode
from typing import Optional

from database import (
    init_db, close_db,
    save_maintenance_db, load_maintenance_db,
    save_sh_session, get_sh_session,
    get_top_hits, get_total_hits, get_user_stats,
    ensure_user, get_user_plan, set_user_plan, is_premium_user,
    is_banned_user, get_user_expiry,
    add_proxy_db, get_all_user_proxies, get_proxy_count,
    remove_proxy_by_index, remove_proxy_by_url, clear_all_proxies,
    add_global_site, get_global_sites, remove_global_site,
    count_global_sites, clear_global_sites, seed_global_sites_from_user,
    track_user_stats, get_total_cards_count, get_charged_count, get_approved_count, get_declined_count,
    get_active_premium_users, get_active_key_plan_users, get_all_user_ids,
    expire_due_plans, get_pending_expiry_notifications, clear_pending_expiry_notification,
    mark_user_joined, is_user_marked_joined, remove_joined_mark,
    save_feedback, get_top_feedbacks, get_total_feedbacks,
    get_user_credits, add_user_credits, deduct_credit, get_user_joined_date,
    create_keys, redeem_key, get_remaining_keys, expire_stale_unused_keys, revoke_all_unused_keys,
    MAX_KEYS_PER_GENERATE,
    user_exists, register_pending_referral, get_verified_referral_count, complete_referral_on_verify,
    REFERRAL_GOAL, REFERRAL_REWARD_DAYS,
    claim_crypto_payment,
    _norm_proxy_gate,
    get_user_doc, record_gate_result, get_gate_health_records,
)

# ====================== LOGGING ======================
log = logging.getLogger("NothingBot")
log.setLevel(logging.INFO)
_log_fmt = logging.Formatter('[%(asctime)s] [%(levelname)s] %(message)s', datefmt='%Y-%m-%d %H:%M:%S')
_ch = logging.StreamHandler()
_ch.setLevel(logging.INFO)
_ch.setFormatter(_log_fmt)
log.addHandler(_ch)
try:
    _fh = logging.FileHandler('nothing_bot.log', encoding='utf-8')
    _fh.setLevel(logging.INFO)
    _fh.setFormatter(_log_fmt)
    log.addHandler(_fh)
except Exception:
    pass


def log_user(uid, action, msg, level="info"):
    getattr(log, level, log.info)(f"[USER:{uid}] [{action}] {msg}")


def log_system(action, msg, level="info"):
    getattr(log, level, log.info)(f"[SYSTEM] [{action}] {msg}")


def bs(text):
    """Bold plain Latin (Telegram HTML <b>)."""
    if text is None:
        return text
    return f"<b>{html.escape(str(text))}</b>"


def bval(value):
    """Bold a value shown after ➳ (counts, stats, status text)."""
    if value is None:
        return value
    return bs(str(value))


ARROW = bs('➳')
PLAIN_ARROW = "➳"
UI_SEP = "\u2500" * 12


def _btn_label(text):
    """Strip <b> tags for inline/url button text (no HTML in buttons)."""
    s = str(text or "")
    if "<b>" in s or "</b>" in s:
        s = re.sub(r"</?b>", "", s)
        s = html.unescape(s)
    return s


# ====================== CONFIG ======================
def clean_channel_id(val):
    """Parse chat/channel IDs as provided — do not auto-prefix -100."""
    try:
        s = str(val).strip().replace(" ", "")
        return int(s)
    except Exception:
        return int(val)

API_ID = int(os.getenv("API_ID", "35113001"))
API_HASH = os.getenv("API_HASH", "bae3c4e34242aca7cdd1b8596fb1aad2")
BOT_TOKEN = os.getenv("BOT_TOKEN", "8827860401:AAGZuwzMNsgEpNVvO2OoFHNfC5c7YT8IrIo")
ADMIN_ID = json.loads(os.getenv("ADMIN_ID", "[8423281554]"))
# database.deduct_credit() re-reads ADMIN_ID from the environment, so mirror the
# resolved config here; setdefault keeps an externally exported value winning.
os.environ.setdefault("ADMIN_ID", json.dumps(ADMIN_ID))
LOGS_CHANNEL_ID = clean_channel_id(os.getenv("LOGS_CHANNEL_ID", "-1004472821773"))
LOGS_CHANNEL_LINK = os.getenv("LOGS_CHANNEL_LINK", "https://t.me/+Q2jYXxlErFcyZmU0")
HITS_CHANNEL_ID = clean_channel_id(os.getenv("HITS_CHANNEL_ID", "-1004472821773"))
HITS_CHANNEL_LINK = os.getenv("HITS_CHANNEL_LINK", "https://t.me/+Q2jYXxlErFcyZmU0")

HIT_CHANNEL_ID = LOGS_CHANNEL_ID

JOIN_GROUP_ID = clean_channel_id(os.getenv("JOIN_GROUP_ID", "-1004472821773"))
JOIN_GROUP_LINK = os.getenv("JOIN_GROUP_LINK", "https://t.me/+Q2jYXxlErFcyZmU0")
UPDATES_CHANNEL_LINK = os.getenv("UPDATES_CHANNEL_LINK", "https://t.me/+Q2jYXxlErFcyZmU0")
FORCE_JOIN_IMAGES = [
    "",
]
API_BASE_URL = os.getenv("API_BASE_URL", "")
VBV_API_URL = os.getenv("VBV_API_URL", "")
VBV_API_KEY = os.getenv("VBV_API_KEY", "")
KEY_USER_API_GO_URL = ""
KEY_USER_API_ROTATING_URL = ""
KEY_USER_API_ROTATING_URL_2 = ""
_key_user_api_cycle = itertools.cycle([
    KEY_USER_API_GO_URL,
    KEY_USER_API_ROTATING_URL,
    KEY_USER_API_ROTATING_URL_2,
])
BOT_API = f"https://api.telegram.org/bot{BOT_TOKEN}"
DEV_LINK = os.getenv("DEV_LINK", "https://t.me/rapewthyou")
DEV_NAME = "𝐈 𝐓 𝐀 𝐂 𝐇 𝐈 ×‌×"
BOT_LINK = os.getenv("BOT_LINK", "https://t.me/NOTHINGV4_BOT")
BOT_NAME = "〔ƝᎧᎢᚺᏆƝᏀ〕!"

_DEV_ROTATING_EMOJIS = [
    5433818199982378380,
    5303453594517790819,
    5413634774268934356,
    5330319637156479518,
    5465478779038095942,
    5465645879035713500,
    5211021358527448098,
    5400228115458849450,
]

def get_random_dev_emoji():
    return random.choice(_DEV_ROTATING_EMOJIS)


def get_dev_line_emojis():
    """Two PE slots: dev icon + trailing star (matches /start footer)."""
    return [get_random_dev_emoji(), 6233303538676541503]


def get_stats_emoji_ids():
    """Emoji IDs for /stats — one per PE placeholder in order."""
    return [
        5042290883949495533,
        5257969839313526622,
        random.choice(CHARGED_EMOJIS),
        4958610528588008305,
        4956612582816351459,
        *get_dev_line_emojis(),
    ]


START_WELCOME_EMOJI = 4915791289489818259
START_VERSION_EMOJI = 5116163917713769254
REFERRAL_EMOJI = 5436196151575459790
START_TRAIL_EMOJI = 6233303538676541503
KEY_CLAIMED_EMOJI = 5444960062407732826


def updates_channel_bracket_link() -> str:
    return f'<a href="{UPDATES_CHANNEL_LINK}">[❆]</a>'


def build_referral_link(uid):
    bot_user = BOT_LINK.rstrip("/").split("/")[-1]
    return f"https://t.me/{bot_user}?start=ref_{uid}"


def parse_start_payload(raw_text):
    try:
        parts = (raw_text or "").strip().split(maxsplit=1)
        if len(parts) > 1:
            return parts[1].strip()
    except Exception:
        pass
    return ""


def build_start_caption(uid, name, username, plan, credits_display, joined_str):
    access_label = "Custom" if (plan or "").title() == "Custom" else (plan or "Trial").upper()
    return f"""{updates_channel_bracket_link()} {bs('Welcome to ' + BOT_NAME + '.')} {PE}
{UI_SEP}
{bs('User')} {ARROW} {user_link_html(uid, name, username)}
{bs('User ID')} {ARROW} <code>{uid}</code>
{bs('Access')} {ARROW} {bs(access_label)}
{bs('Credits')} {ARROW} {bs(credits_display)}
{bs('Joined')} {ARROW} {bs(joined_str)}
{UI_SEP}
{PE} {bs('Dev')} {ARROW} <a href='{DEV_LINK}'>{bs(DEV_NAME)}</a> {PE}
{PE} {bs('Version')} {ARROW} {bs('4.0')} {PE}
{UI_SEP}
{bs('Choose an option below.')}"""


def get_start_emoji_ids():
    return [
        START_WELCOME_EMOJI,
        *get_dev_line_emojis(),
        START_VERSION_EMOJI,
        START_TRAIL_EMOJI,
    ]


def build_referral_caption(uid, ref_count):
    ref_link = build_referral_link(uid)
    progress = ref_count % REFERRAL_GOAL
    remaining = REFERRAL_GOAL - progress if progress else REFERRAL_GOAL
    return f"""{updates_channel_bracket_link()} {bs('Referral')} {PE}
{UI_SEP}
{bs('Your Link')} {ARROW}
<code>{html.escape(ref_link)}</code>

{bs('Referrals')} {ARROW} {bval(ref_count)}
{bs('Progress')} {ARROW} {bval(f'{progress} / {REFERRAL_GOAL}')} ({bval(remaining)} {bs('more for reward')})
{UI_SEP}
{bs('How to earn free premium:')}
1. Share your link above with friends
2. They open the bot via your link
3. They join the channels + group and click ✅ Verify
4. Every {REFERRAL_GOAL} verified joins = {REFERRAL_REWARD_DAYS} days FREE premium
{UI_SEP}
⚠️ {bs('Note')} {ARROW} {bs('Referral only works for new users')}
{UI_SEP}
{PE} {bs('Dev')} {ARROW} <a href='{DEV_LINK}'>{bs(DEV_NAME)}</a> {PE}"""


def get_referral_emoji_ids():
    return [REFERRAL_EMOJI, *get_dev_line_emojis()]


def build_referral_kb(uid):
    ref_link = build_referral_link(uid)
    share_url = (
        "https://t.me/share/url?"
        f"url={quote(ref_link)}&text={quote('Join ' + BOT_NAME + ' and earn free premium!')}"
    )
    return [
        [pbtn(bs("Share My Link"), url=share_url, color="blue")],
        [pbtn(f"« {bs('Back')}", "rx_back:main", color="red")],
    ]


def build_start_kb(uid):
    return [
        [pbtn(bs("Checker"), "rx_checker", color="blue"), pbtn(bs("Buy Now"), "show_plans", color="blue")],
        [pbtn(bs("Updates"), url=UPDATES_CHANNEL_LINK, color="blue"), pbtn(bs("Referral"), "rx_referral", color="blue")],
        [pbtn(bs("Support"), url=DEV_LINK, color="blue")],
    ]



# ====================== WORKERS ======================
SP_WORKERS = 50
SITE_WORKERS = 10
PROXY_WORKERS = 10
BIN_WORKERS = 50
VBV_WORKERS = 50

API_TIMEOUT = 60
BIN_TIMEOUT = 60
PROXY_TIMEOUT = 12

HIT_DELAY = 2.0
MAX_PROXIES = 500
PROXY_TEST_WORKERS = 10
PROXY_TEST_UI_INTERVAL = 2.0
MAX_SITES = 3000
LOG_CHANNEL_ID = LOGS_CHANNEL_ID

FREE_ALL_GATES_COOLDOWN = 10

FREE_PLAN = "Trial"

PLANS = {
    "plan1": {"name": bs("Core Access"), "tier": "Core", "duration_days": 7, "emoji": "🛠️", "price": "$10.00"},
    "plan2": {"name": bs("Elite Access"), "tier": "Elite", "duration_days": 15, "emoji": "👑", "price": "$15.00"},
    "plan3": {"name": bs("Root Access"), "tier": "Root", "duration_days": 30, "emoji": "⭐", "price": "$30.00"},
    "plan4": {"name": bs("X-Access"), "tier": "X", "duration_days": 90, "emoji": "💎", "price": "$60.00"},
}
PAID_TIERS = ["Core", "Elite", "Root", "X", "Custom"]
OWNER_CONTACT = f"<a href='{DEV_LINK}'>{bs(DEV_NAME)}</a>"

_SP_SEM = asyncio.Semaphore(SP_WORKERS)
_SITE_SEM = asyncio.Semaphore(SITE_WORKERS)
_PROXY_SEM = asyncio.Semaphore(PROXY_WORKERS)
_BIN_SEM = asyncio.Semaphore(BIN_WORKERS)
_VBV_SEM = asyncio.Semaphore(VBV_WORKERS)

PER_USER_MASS_WORKERS = {"msp": 10}
_USER_MASS_SEMS = {}


def get_mass_workers(plan, gate_cmd, uid=None):
    """MSP concurrency per user type. Key (Custom): MSP=30. Paid plans: MSP=30."""
    if uid and uid in ADMIN_ID:
        return 30
    p = (plan or FREE_PLAN).title()
    if p == "Custom":
        return 30
    if is_paid_plan(p):
        return 30
    return PER_USER_MASS_WORKERS.get(gate_cmd, 10)


def _get_user_mass_sem(user_id, gate_cmd, plan=None):
    limit = get_mass_workers(plan, gate_cmd, user_id)
    key = (user_id, gate_cmd, limit)
    sem = _USER_MASS_SEMS.get(key)
    if sem is None:
        sem = asyncio.Semaphore(limit)
        _USER_MASS_SEMS[key] = sem
    return sem


def _cleanup_user_mass_sem(user_id, gate_cmd, plan=None):
    limit = get_mass_workers(plan, gate_cmd, user_id)
    _USER_MASS_SEMS.pop((user_id, gate_cmd, limit), None)


CE = {
    "crown": 5039727497143387500, "bolt": 5042334757040423886,
    "brain": 5040030395416969985, "shield": 5042328396193864923,
    "star": 5042176294222037888, "gem": 5042050649248760772,
    "check": 5039793437776282663, "fire": 5039644681583985437,
    "party": 5039778134807806727, "search": 5039649904264217620,
    "chart": 5042290883949495533, "pin": 5039600026809009149,
    "joker": 5039998939076494446, "plus": 5039891861246838069,
    "cross": 5040042498634810056, "info": 5042306247047513767,
    "gift": 5041975203853239332, "eyes": 5039623284056917259,
    "trash": 5039614900280754969, "tick": 5039844895779455925,
    "stop": 5039671744172917707, "warn": 5039665997506675838,
    "link": 5042101437237036298, "globe": 5042186567783809934,
    "restart": 5413554170668032766, "online": 5413813953685923984,
    "declined": 5042112436648281096,
    "approved": 5039793437776282663,
    "charged": 4956719506027185156,
    "addtick": 4958610528588008305,
    "wave": 5319007286004299794,
}
PE = "⭐"

CHARGED_EMOJIS = [
    5285373878145667586, 5287547831677112267, 5287360712836928126,
    5285024405246725814, 5287777298894835685, 5285221724634239278,
    5285186510197381130, 5436143465211640305, 5787435351521889877,
    4956719506027185156, 6026031174340579961, 6025955600096038513,
    5321125250342083365, 5267419403019886452, 5231265132826343149,
    5285181291812120474, 5462902520215002477, 5994295021040309628,
    5380111356227770863
]

PLAN_EXPIRY_CHECK_INTERVAL = 120

ACTIVE_MTXT_PROCESSES = {}
ACTIVE_SH_SESSIONS = {}
ACTIVE_ADD_PROCESSES = {}
PENDING_ADD_SITES = {}
PENDING_SITE_CHECK = {}
PENDING_ADD_PROXIES = {}
PENDING_RM_PROXIES = {}
ACTIVE_CHK_PROXY = {}
ACTIVE_ADD_PROXY = {}
BROADCAST_SLEEP_TIME = 0.09
BROADCAST_PROGRESS_EVERY = 25
broadcast_task = None
MAINTENANCE_FILE = "maintenance.json"
_MAINTENANCE_CACHE = {"enabled": None, "last_check": 0}

_PENDING_FEEDBACK = {}

_GATE_MAINT = {}
_MAINT_GATE_NAMES = {
    # Single Gates
    "sp": "Shopify", "vbv": "VBV Lookup",
    
    # Mass Gates
    "msp": "Mass Shopify",    
    # Group Gates
    "mass": "All Mass",
}

_JOIN_CACHE = {}
_GLOBAL_COOLDOWN = {}
_VBV_LAST_USE = {}


def _get_ui_interval():
    active = len(ACTIVE_MTXT_PROCESSES)
    if active <= 5:
        return 2.5
    elif active <= 20:
        return 4.0
    elif active <= 50:
        return 6.0
    else:
        return 8.0


async def _record_gate_result(gate_key, success):
    try:
        await record_gate_result(gate_key, success)
    except Exception:
        pass


async def _get_gate_health(gate_key):
    try:
        records = await get_gate_health_records(gate_key)
        if not records:
            return "No Data"
        pct = int((sum(records) / len(records)) * 100)
        if pct >= 90:
            return f"{pct}%"
        elif pct >= 70:
            return f"{pct}% (Good)"
        else:
            return f"{pct}% (Degraded)"
    except Exception:
        return "No Data"


class _TgRateLimiter:
    def __init__(self, max_per_second=25):
        self._sem = asyncio.Semaphore(max_per_second)

    async def acquire(self):
        await self._sem.acquire()
        loop = asyncio.get_event_loop()
        loop.call_later(1.0, self._sem.release)

    async def __aenter__(self):
        await self.acquire()
        return self

    async def __aexit__(self, *args):
        pass


_TG_RATE = _TgRateLimiter(max_per_second=25)

# ====================== BACKGROUND TASK QUEUE ======================
_BG_QUEUE = asyncio.Queue(maxsize=0)
_BG_WORKERS_COUNT = 500


async def _bg_worker():
    while True:
        try:
            coro = await _BG_QUEUE.get()
            await coro
        except asyncio.CancelledError:
            break
        except Exception:
            pass
        finally:
            _BG_QUEUE.task_done()


def fire_and_forget(coro):
    try:
        _BG_QUEUE.put_nowait(coro)
    except asyncio.QueueFull:
        asyncio.create_task(coro)


async def _send_plan_expired_notice(user_id: int):
    await styled_send(
        user_id,
        f"{PE} {bs('Your Plan is Expired.')} {PE}\n\n"
        f"{PE} {bs('Contact')} {OWNER_CONTACT} {bs('for premium.')}",
        emoji_ids=[5454156248813432363, 5319007286004299794, 5454156248813432363],
    )


async def _plan_expiry_worker():
    while True:
        try:
            expired_count = await expire_due_plans()
            if expired_count:
                log_system("PLAN_EXPIRY", f"Downgraded {expired_count} expired plan(s)")
            try:
                stale_keys = await expire_stale_unused_keys()
                if stale_keys:
                    log_system("KEY_EXPIRY", f"Expired {stale_keys} unused key(s)")
            except Exception as ke:
                log_system("KEY_EXPIRY_ERR", str(ke), "error")
            pending = await get_pending_expiry_notifications()
            for u in pending:
                uid = u.get("user_id")
                if not uid:
                    continue
                try:
                    await _send_plan_expired_notice(uid)
                    log_user(uid, "PLAN_EXPIRED", "Expiry notification sent")
                except Exception as e:
                    log_system("PLAN_EXPIRY_NOTIFY_ERR", f"User={uid} Error={e}", "error")
                await clear_pending_expiry_notification(uid)
        except Exception as e:
            log_system("PLAN_EXPIRY_WORKER_ERR", str(e), "error")
        await asyncio.sleep(PLAN_EXPIRY_CHECK_INTERVAL)


# ====================== CLIENT ======================
client = TelegramClient('nothing_bot', API_ID, API_HASH)
client_instance = client

_SESSION_SP = None
_SESSION_SITE = None
_SESSION_BIN = None
_SESSION_PROXY = None


CONN_POOL_LIMIT = 2000


async def get_sp_session():
    global _SESSION_SP
    if _SESSION_SP is None or _SESSION_SP.closed:
        _SESSION_SP = aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=API_TIMEOUT, connect=10), connector=aiohttp.TCPConnector(limit=CONN_POOL_LIMIT, limit_per_host=100, ttl_dns_cache=300, use_dns_cache=True, enable_cleanup_closed=True, force_close=False))
    return _SESSION_SP


async def get_site_session():
    global _SESSION_SITE
    if _SESSION_SITE is None or _SESSION_SITE.closed:
        _SESSION_SITE = aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=API_TIMEOUT, connect=10), connector=aiohttp.TCPConnector(limit=CONN_POOL_LIMIT, limit_per_host=100, ttl_dns_cache=300, use_dns_cache=True, enable_cleanup_closed=True, force_close=False))
    return _SESSION_SITE


async def get_bin_session():
    global _SESSION_BIN
    if _SESSION_BIN is None or _SESSION_BIN.closed:
        _SESSION_BIN = aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=BIN_TIMEOUT, connect=5), connector=aiohttp.TCPConnector(limit=CONN_POOL_LIMIT, limit_per_host=100, ttl_dns_cache=300, use_dns_cache=True, enable_cleanup_closed=True, force_close=False))
    return _SESSION_BIN


async def get_proxy_session():
    global _SESSION_PROXY
    if _SESSION_PROXY is None or _SESSION_PROXY.closed:
        _SESSION_PROXY = aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=PROXY_TIMEOUT, connect=15), connector=aiohttp.TCPConnector(limit=CONN_POOL_LIMIT, limit_per_host=100, ttl_dns_cache=300, use_dns_cache=True, enable_cleanup_closed=True, force_close=False))
    return _SESSION_PROXY



def generate_session_id():
    return ''.join(random.choices(string.ascii_uppercase + string.digits, k=8))


# ====================== ANTI-FLOOD COOLDOWN ======================
def check_global_cooldown(user_id, cmd, cooldown_sec=2):
    key = f"{user_id}_{cmd}"
    now = time.time()
    last = _GLOBAL_COOLDOWN.get(key, 0)
    if now - last < cooldown_sec:
        return round(cooldown_sec - (now - last), 1)
    _GLOBAL_COOLDOWN[key] = now
    return 0


# ====================== FREE USER COOLDOWN ======================
_FREE_GATE_GLOBAL_LAST_USE = {}


def get_free_sp_cooldown_remaining(user_id):
    return get_free_gate_cooldown(user_id)


def set_free_sp_last_use(user_id):
    set_free_gate_last_use(user_id)


def get_free_gate_cooldown(user_id, gate=None):
    last = _FREE_GATE_GLOBAL_LAST_USE.get(user_id, 0)
    elapsed = time.time() - last
    return 0 if elapsed >= FREE_ALL_GATES_COOLDOWN else round(FREE_ALL_GATES_COOLDOWN - elapsed, 1)


def set_free_gate_last_use(user_id, gate=None):
    _FREE_GATE_GLOBAL_LAST_USE[user_id] = time.time()


# ====================== SMART ROTATION ENGINE ======================
class SmartRotator:
    def __init__(self):
        self._site_fails = {}
        self._proxy_fails = {}
        self._site_idx = 0
        self._proxy_idx = 0

    def pick_site(self, sites, exclude=None):
        if not sites:
            return None
        exclude = exclude or set()
        n = len(sites)
        # True round-robin across the full pool so consecutive /sp checks change site
        for _ in range(n):
            self._site_idx = (self._site_idx + 1) % n
            site = sites[self._site_idx]
            if site in exclude:
                continue
            if self._site_fails.get(site, 0) >= 5:
                continue
            return site
        # Fallback: ignore fail counts, still skip exclude
        for _ in range(n):
            self._site_idx = (self._site_idx + 1) % n
            site = sites[self._site_idx]
            if site not in exclude:
                return site
        return sites[self._site_idx % n]

    def pick_proxy(self, proxies, exclude=None):
        if not proxies:
            return None
        exclude = exclude or set()
        n = len(proxies)
        for _ in range(n):
            self._proxy_idx = (self._proxy_idx + 1) % n
            proxy = proxies[self._proxy_idx]
            url = proxy.get('proxy_url')
            if url in exclude:
                continue
            if self._proxy_fails.get(url, 0) >= 5:
                continue
            return proxy
        for _ in range(n):
            self._proxy_idx = (self._proxy_idx + 1) % n
            proxy = proxies[self._proxy_idx]
            if proxy.get('proxy_url') not in exclude:
                return proxy
        return proxies[self._proxy_idx % n]

    def report_site_ok(self, site):
        self._site_fails[site] = 0

    def report_site_fail(self, site):
        self._site_fails[site] = self._site_fails.get(site, 0) + 1

    def report_proxy_ok(self, pu):
        if pu:
            self._proxy_fails[pu] = 0

    def report_proxy_fail(self, pu):
        if pu:
            self._proxy_fails[pu] = self._proxy_fails.get(pu, 0) + 1


# Persistent rotators so consecutive single checks advance site/proxy
_SP_ROTATOR = SmartRotator()


# ====================== SITE ERROR DETECTION ======================
SITE_ERROR_KEYWORDS = [
    'r4 token empty', 'payment method is not shopify', 'r2 id empty', 'product id is empty',
    'py id empty', 'clinte token', 'receipt_empty', 'receipt id is empty', 'receipt empty',
    'site requires login', 'failed to get token', 'no valid products', 'not shopify',
    'failed to get checkout', 'failed to detect product', 'failed to create checkout',
    'failed to get proposal data', 'site not supported', 'site error! status: 429',
    'token not found', 'handle is empty', 'payment method identifier is empty',
    'failed to get session token', 'failed to tokenize card', 'no_session_token',
    'no session token', 'no checkout token found', 'checkout token not found',
    'no checkout token', 'checkout token is empty', 'tokenize_fail', 'tokenize fail',
    'tax ammount empty', 'tax amount empty', 'tax amount is empty', 'del ammount empty',
    'site not supported for now', 'payment base card not supported', 'no product found',
    'checkout is not available', 'cart is empty', 'cart add failed after retries',
    'checkout_expired', 'checkout_not_found', 'no shipping methods available',
    'site error', 'site dead', 'site errors', 'server error', 'internal server error',
    'internal_server_error', 'application error', 'unexpected error', 'something went wrong',
    'error in 1st req', 'error in 1 req', 'error processing card', 'we could not process',
    'unable to process', 'payment provider error', 'payment gateway error', 'session expired',
    'session invalid', 'failed after retries', 'max retries exceeded', 'all sites dead',
    'all sites unavailable', 'processinf error', 'handle error', 'nonetype',
    "nonetype' object has no attribute 'get", 'unknown error', 'unknown_error',
    'unknown_result', 'utm_source', 'shop is unavailable', 'store is unavailable',
    'store not found', 'page not found', 'this store is unavailable',
    'this shop is currently unavailable', 'password protected', 'enter store using password',
    'storefront is password protected', 'shop closed', 'store closed',
    'delivery_delivery_line_detail_changed', 'delivery_address2_required',
    'delivery_line_detail_changed', 'delivery_line', 'delivery_address', 'address_required',
    'submit_rejected', 'submit rejected:', 'change proxy or site', 'change site',
    'fake charge gate', 'fake gate', 'hcaptcha detected', 'hcaptcha_detected',
    'captcha at checkout', 'captcha_required', 'captcha required', 'cloudflare',
    'access denied', 'permission denied', 'connection error', 'connection failed',
    'timed out', 'timeout', 'could not resolve host', 'connect tunnel failed',
    'unreachable', 'network error', 'connection reset', 'empty reply from server',
    'tlsv1 alert', 'ssl routines', 'openssl ssl_connect', 'api_timeout',
    'http error', 'httperror504', '502', '503', '504', 'bad gateway',
    'service unavailable', 'gateway timeout', 'site error! status: 404',
    'site error! status: 401', 'amount_too_small', 'amount too small',
    'merchandise_not_enough_stock', 'product out of stock', 'malformed input',
    'url rejected', 'invalid_response', 'cart failed with status', 'invalid json response',
    'invalid json', 'inventoryreservationfailure', 'inventory_reservation_failure',
    'payments_positive_amount_expec', 'payments_payment_flexibility_t',
    'payments_credit_card_brand_not', 'buyer_identity_presentment_currency',
    "'products'", 'unable to get payment token',
    'empty submit response', 'empty submit', 'order_total_changed', 'order total changed',
    'invalid_payment_method', 'invalid payment method', 'validation_custom',
    'validation custom', 'artifact_dissatisfaction', 'tax_new_tax_must_be_accepted',
    'processing_error', 'delivery_company_required', 'decision_rule_block',
]

PROXY_ERROR_KEYWORDS = ['proxy dead', 'proxy error', 'proxy timeout', 'proxy connection failed', 'proxy refused', 'connection_error', 'connection error']


def is_site_error(text):
    if not text:
        return True
    lower = text.lower().strip()
    if lower == 'na':
        return True
    return any(kw.lower().strip() in lower for kw in SITE_ERROR_KEYWORDS)


def is_proxy_error(text):
    if not text:
        return False
    return any(kw in text.lower().strip() for kw in PROXY_ERROR_KEYWORDS)


def has_restricted_gateway(response_text: str = "", gateway_text: str = "") -> bool:
    """True if API Response/Gateway indicates a blocked processor.

    Authorize.Net often appears only in the Gateway field (not Response), so
    both must be checked or /add and /site will keep those stores.
    """
    blob = f"{response_text or ''} {gateway_text or ''}".lower()
    if not blob.strip():
        return False
    # authorize.net / AuthorizeNet / authorize net
    if "authorize.net" in blob or "authorizenet" in blob or "authorize net" in blob:
        return True
    # ONERWAY (Direct)
    if "onerway" in blob and "direct" in blob:
        return True
    return False


def is_truly_alive(response, price):
    if not response:
        return False
    lower = response.lower().strip()
    pv = _parse_price_value(price)
    bad = ['error:', 'error: ', "error: '", 'cart failed', 'invalid json', 'inventoryreservationfailure', 'payments_positive_amount', 'payments_payment_flexibility', 'payments_credit_card_brand']
    for b in bad:
        if b in lower:
            return False
    if pv == 0.0:
        normal = ['card_declined', 'card declined', 'generic_decline', 'generic decline', 'do_not_honor', 'do not honor', 'insufficient_funds', 'insufficient funds', 'stolen_card', 'lost_card', 'expired_card', 'expired card', 'otp_required', 'otp required', '3d', 'authentication', 'cvc', 'ccn', 'generic_error', 'generic error', 'restricted_card', 'fraudulent', 'not_permitted', 'transaction_not_allowed', 'card_not_supported']
        if not any(n in lower for n in normal):
            return False
    return True


_CURRENCY_SYMBOL_MAP = {
    '$': 'USD', '£': 'GBP', '€': 'EUR', '¥': 'JPY', '₹': 'INR',
    '₽': 'RUB', '₩': 'KRW', 'R$': 'BRL', 'C$': 'CAD', 'A$': 'AUD',
    'CHF': 'CHF', 'kr': 'SEK', 'zł': 'PLN', '₺': 'TRY', '฿': 'THB',
    'RM': 'MYR', 'S$': 'SGD', 'HK$': 'HKD', 'NZ$': 'NZD', 'Kč': 'CZK',
    '₴': 'UAH', '₱': 'PHP', 'Rp': 'IDR', '₫': 'VND', 'лв': 'BGN',
    'R': 'ZAR', 'Ft': 'HUF', '₡': 'CRC', '₦': 'NGN', 'د.إ': 'AED',
    'ر.س': 'SAR', 'MX$': 'MXN', 'CLP$': 'CLP', 'COP$': 'COP',
}


def _parse_price_value(price):
    """Extract numeric price from API/formatted price string (e.g. '$1.06', '1.06 USD')."""
    if not price or price == '-':
        return 0.0
    pc = str(price).replace('$', '').replace('£', '').replace('€', '').replace('¥', '').replace('₹', '').replace('₽', '').replace('₩', '').replace('R$', '').replace('C$', '').replace('A$', '').replace('CHF', '').replace('USD', '').replace('GBP', '').replace('EUR', '').replace('CAD', '').replace('AUD', '').replace('INR', '').strip()
    try:
        return float(pc)
    except Exception:
        return 0.0


def _format_price_with_currency(price_raw):
    """Convert API price like '$1.06' or '£2.50' to '1.06 USD' or '2.50 GBP'."""
    if not price_raw or price_raw == '-':
        return price_raw
    ps = str(price_raw).strip()
    # Try longest symbols first (e.g. 'HK$' before '$')
    for sym in sorted(_CURRENCY_SYMBOL_MAP, key=len, reverse=True):
        if ps.startswith(sym):
            numeric = ps[len(sym):].strip()
            return f"{numeric} {_CURRENCY_SYMBOL_MAP[sym]}"
        if ps.endswith(sym):
            numeric = ps[:-len(sym)].strip()
            return f"{numeric} {_CURRENCY_SYMBOL_MAP[sym]}"
    # No known symbol found — try to detect if it's just a number
    cleaned = ps.replace(',', '').replace(' ', '')
    try:
        float(cleaned)
        return f"{cleaned} USD"  # Default to USD if no symbol
    except ValueError:
        pass
    return ps


# ====================== ANIME GIF API ======================
_ANIME_REACTIONS = [
    "airkiss", "angrystare", "bite", "bleh", "blush", "brofist", "celebrate",
    "cheers", "clap", "confused", "cool", "cry", "cuddle", "dance", "drool",
    "evillaugh", "facepalm", "handhold", "happy", "headbang", "hug", "huh",
    "kiss", "laugh", "lick", "love", "mad", "nervous", "no", "nom", "nosebleed",
    "nuzzle", "nyah", "pat", "peek", "pinch", "poke", "pout", "punch", "roll",
    "run", "sad", "scared", "shout", "shrug", "shy", "sigh", "sing", "sip",
    "slap", "sleep", "slowclap", "smack", "smile", "smug", "sneeze", "sorry",
    "stare", "stop", "surprised", "sweat", "thumbsup", "tickle", "tired",
    "wave", "wink", "woah", "yawn", "yay", "yes"
]


async def fetch_anime_gif():
    """Fetch a random anime reaction GIF URL from otakugifs.xyz."""
    try:
        reaction = random.choice(_ANIME_REACTIONS)
        url = f"https://api.otakugifs.xyz/gif?reaction={reaction}"
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=5)) as s:
            async with s.get(url) as resp:
                if resp.status == 200:
                    data = await resp.json(content_type=None)
                    return data.get("url", None)
    except Exception:
        pass
    return None

def normalize_site_url(url):
    """Normalize site URLs (domain only)."""
    if not url:
        return None
    raw = str(url).strip()
    if not raw:
        return None
    if not raw.lower().startswith(("http://", "https://")):
        raw = "https://" + raw
    try:
        p = urlparse(raw)
        host = (p.netloc or "").lower()
        if host.startswith("www."):
            host = host[4:]
        if not host:
            return None
        return host
    except Exception:
        s = str(url).strip().lower()
        s = re.sub(r"^https?://", "", s).rstrip("/")
        if s.startswith("www."):
            s = s[4:]
        return s or None


def is_valid_url_or_domain(url):
    d = str(url or "").lower().strip()
    if not d:
        return False
    if d.startswith(("http://", "https://")):
        try:
            d = urlparse(d).netloc
        except Exception:
            return False
    else:
        # domain only
        d = d.split("/")[0]
    if d.startswith("www."):
        d = d[4:]
    return bool(re.match(
        r'^[a-zA-Z0-9]([a-zA-Z0-9\-]*[a-zA-Z0-9])?(\.[a-zA-Z0-9]([a-zA-Z0-9\-]*[a-zA-Z0-9])?)*\.[a-zA-Z]{2,}$',
        d,
    ))


async def get_shopify_sites():
    """Single Shopify site pool for all users (shared Shopify pool)."""
    try:
        return await get_global_sites()
    except Exception:
        return []


# ====================== MESSAGE SYSTEM ======================
import contextvars
from telethon import TelegramClient
from telethon.tl import functions
from telethon.tl.types import MessageEntitySpoiler

_noforwards_var = contextvars.ContextVar('noforwards', default=False)

_orig_send_message = TelegramClient.send_message
async def _custom_send_message(self, *args, noforwards=False, **kwargs):
    token = _noforwards_var.set(noforwards)
    try:
        return await _orig_send_message(self, *args, **kwargs)
    finally:
        _noforwards_var.reset(token)

_orig_send_file = TelegramClient.send_file
async def _custom_send_file(self, *args, noforwards=False, **kwargs):
    token = _noforwards_var.set(noforwards)
    try:
        return await _orig_send_file(self, *args, **kwargs)
    finally:
        _noforwards_var.reset(token)

TelegramClient.send_message = _custom_send_message
TelegramClient.send_file = _custom_send_file

_orig_call = TelegramClient.__call__
async def _custom_call(self, request, *args, **kwargs):
    if _noforwards_var.get():
        if isinstance(request, (functions.messages.SendMessageRequest, functions.messages.SendMediaRequest)):
            request.noforwards = True
    return await _orig_call(self, request, *args, **kwargs)

TelegramClient.__call__ = _custom_call


async def safe_callback_answer(event, message=None, alert=False):
    """Answer a callback query; ignore expired/invalid query IDs.

    Telegram expires callback query IDs after a few seconds. Heavy /add work
    (thousands of sites) can outlive that window and crash the handler.
    """
    try:
        if message is None:
            await event.answer()
        else:
            await event.answer(message, alert=alert)
    except (QueryIdInvalidError, Exception):
        pass


# Monkey patch Telethon HTML parser to support <spoiler>
_original_handle_starttag = thtml.HTMLToTelegramParser.handle_starttag

def _custom_handle_starttag(self, tag, attrs):
    if tag == 'spoiler' or tag == 'tg-spoiler':
        self._open_tags.appendleft(tag)
        self._open_tags_meta.appendleft(None)
        if tag not in self._building_entities:
            self._building_entities[tag] = MessageEntitySpoiler(
                offset=len(self.text),
                length=0
            )
        return
    return _original_handle_starttag(self, tag, attrs)

thtml.HTMLToTelegramParser.handle_starttag = _custom_handle_starttag
def build_entities(html_text, emoji_ids=None):
    text, entities = thtml.parse(html_text)
    if emoji_ids:
        idx, utf16_pos = 0, 0
        for ch in text:
            if ch == PE and idx < len(emoji_ids):
                entities.append(MessageEntityCustomEmoji(offset=utf16_pos, length=1, document_id=emoji_ids[idx]))
                idx += 1
            utf16_pos += 2 if ord(ch) > 0xFFFF else 1

    def entity_key(e):
        cls_name = e.__class__.__name__
        if cls_name == 'MessageEntitySpoiler':
            priority = 0
        elif cls_name in ('MessageEntityTextUrl', 'MessageEntityUrl'):
            priority = 1
        elif cls_name in ('MessageEntityBold', 'MessageEntityItalic', 'MessageEntityUnderline', 'MessageEntityStrike'):
            priority = 2
        elif cls_name in ('MessageEntityCode', 'MessageEntityPre'):
            priority = 3
        else:
            priority = 4
        return (e.offset, -e.length, priority)

    return text, sorted(entities, key=entity_key)


def _ui_rule(*_html_lines):
    return UI_SEP


def build_panel_ui(header, primary_lines, secondary_lines=None, footer_lines=None):
    """Build site/proxy panel text with fixed UI_SEP rules."""
    primary_lines = list(primary_lines)
    secondary_lines = list(secondary_lines or [])
    footer_lines = list(footer_lines or [])
    width_lines = [header, *primary_lines, *secondary_lines]
    rule = _ui_rule(*width_lines)
    parts = [header, rule, *primary_lines]
    if secondary_lines:
        parts.extend([rule, *secondary_lines])
    if footer_lines:
        parts.extend([rule, *footer_lines])
    return "\n".join(parts)


SITE_TEST_PROGRESS_EMOJIS = [
    5325834523068342417,
    5278622189556354905,
    6266967801580231067,
    5042112436648281096,
    5215327832040811010,
    5980995951160987855,
    4902715076873553054,
]


def build_site_test_progress_ui(alive_count, kept_count, dead_count, tested, total, title="Testing Sites"):
    title_line = f"{bs(title)} {PE}"
    body_lines = [
        f"{bs('Working')} {ARROW} {bval(alive_count)} {PE}",
        f"{bs('Added To DB')} {ARROW} {bval(f'{kept_count}/{total}')} {PE}",
        f"{bs('Dead')} {ARROW} {bval(dead_count)} {PE}",
        f"{bs('Tested')} {ARROW} {bval(f'{tested}/{total}')} {PE}",
        f"{bs('Total')} {ARROW} {bval(total)} {PE}",
    ]
    footer_line = f"{PE} {bs('Only sites with price in range will be added in the database.')}"
    text = build_panel_ui(title_line, body_lines, footer_lines=[footer_line])
    return text, list(SITE_TEST_PROGRESS_EMOJIS)


async def styled_reply(event, html_text, buttons=None, emoji_ids=None, file=None, noforwards=False):
    try:
        async with _TG_RATE:
            text, entities = build_entities(html_text, emoji_ids)
            return await asyncio.wait_for(event.reply(text, formatting_entities=entities, buttons=buttons, file=file, link_preview=False, noforwards=noforwards), timeout=15)
    except asyncio.TimeoutError:
        return None
    except Exception:
        try:
            async with _TG_RATE:
                return await asyncio.wait_for(event.reply(html_text[:4000], parse_mode='html', link_preview=False), timeout=10)
        except Exception:
            return None


def _telethon_entities_to_bot_api(entities):
    """Convert Telethon message entities to Bot API entity dicts."""
    out = []
    if not entities:
        return out
    for e in entities:
        cls = e.__class__.__name__
        base = {"offset": e.offset, "length": e.length}
        if cls == "MessageEntityBold":
            base["type"] = "bold"
        elif cls == "MessageEntityItalic":
            base["type"] = "italic"
        elif cls == "MessageEntityUnderline":
            base["type"] = "underline"
        elif cls == "MessageEntityStrike":
            base["type"] = "strikethrough"
        elif cls == "MessageEntityCode":
            base["type"] = "code"
        elif cls == "MessageEntityPre":
            base["type"] = "pre"
            if getattr(e, "language", None):
                base["language"] = e.language
        elif cls == "MessageEntityTextUrl":
            base["type"] = "text_link"
            base["url"] = e.url
        elif cls == "MessageEntityUrl":
            base["type"] = "url"
        elif cls == "MessageEntityMentionName":
            base["type"] = "text_mention"
            base["user"] = {"id": e.user_id}
        elif cls == "MessageEntityCustomEmoji":
            base["type"] = "custom_emoji"
            base["custom_emoji_id"] = str(e.document_id)
        elif cls == "MessageEntitySpoiler":
            base["type"] = "spoiler"
        else:
            continue
        out.append(base)
    return out


def _buttons_to_bot_api_markup(buttons):
    if not buttons:
        return None
    rows = []
    try:
        for row in buttons:
            api_row = []
            for btn in row:
                if getattr(btn, "url", None):
                    api_row.append({"text": btn.text, "url": btn.url})
                elif getattr(btn, "data", None) is not None:
                    data = btn.data
                    if isinstance(data, (bytes, bytearray)):
                        data = data.decode("utf-8", errors="ignore")
                    api_row.append({"text": btn.text, "callback_data": str(data)})
            if api_row:
                rows.append(api_row)
    except Exception:
        return None
    return {"inline_keyboard": rows} if rows else None


async def _resolve_send_peer(chat_id):
    """Best-effort Telethon peer resolution for channels/groups/users."""
    try:
        return await client_instance.get_input_entity(chat_id)
    except Exception:
        pass
    try:
        from telethon.tl.types import PeerChannel, PeerChat, PeerUser
        cid = int(chat_id)
        if cid < 0:
            s = str(cid)
            if s.startswith("-100"):
                bare = int(s[4:])
                for peer in (PeerChannel(bare), PeerChat(bare)):
                    try:
                        return await client_instance.get_input_entity(peer)
                    except Exception:
                        pass
            else:
                bare = abs(cid)
                for peer in (PeerChat(bare), PeerChannel(bare)):
                    try:
                        return await client_instance.get_input_entity(peer)
                    except Exception:
                        pass
        else:
            try:
                return await client_instance.get_input_entity(PeerUser(cid))
            except Exception:
                pass
    except Exception:
        pass
    # Refresh dialog cache once, then retry
    try:
        await asyncio.wait_for(client_instance.get_dialogs(limit=50), timeout=10)
        return await client_instance.get_input_entity(chat_id)
    except Exception:
        return None


async def _styled_send_http(chat_id, text, entities=None, buttons=None):
    """Bot HTTP API fallback — works with raw chat_id when Telethon entity cache misses."""
    payload = {
        "chat_id": int(chat_id),
        "text": text[:4096],
        "disable_web_page_preview": True,
    }
    api_entities = _telethon_entities_to_bot_api(entities)
    if api_entities:
        payload["entities"] = api_entities
    markup = _buttons_to_bot_api_markup(buttons)
    if markup:
        payload["reply_markup"] = markup
    url = f"{BOT_API}/sendMessage"
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(url, json=payload, timeout=aiohttp.ClientTimeout(total=15)) as resp:
                data = await resp.json(content_type=None)
                if data.get("ok"):
                    return data.get("result")
                log_system(
                    "STYLED_SEND_HTTP_ERR",
                    f"Chat={chat_id} Error={data.get('description') or data}",
                    "error",
                )
                return None
    except Exception as e:
        log_system("STYLED_SEND_HTTP_ERR", f"Chat={chat_id} Error={repr(e)}", "error")
        return None


async def styled_send(chat_id, html_text, buttons=None, emoji_ids=None, file=None, noforwards=False):
    text, entities = build_entities(html_text, emoji_ids)
    # File sends still go through Telethon (HTTP multipart is heavier); resolve peer first
    try:
        async with _TG_RATE:
            peer = chat_id
            try:
                return await asyncio.wait_for(
                    client_instance.send_message(
                        peer, text, formatting_entities=entities, buttons=buttons,
                        file=file, link_preview=False, noforwards=noforwards,
                    ),
                    timeout=15,
                )
            except ValueError as ve:
                if "entity" not in str(ve).lower() and "PeerChannel" not in str(ve):
                    raise
                resolved = await _resolve_send_peer(chat_id)
                if resolved is not None:
                    return await asyncio.wait_for(
                        client_instance.send_message(
                            resolved, text, formatting_entities=entities, buttons=buttons,
                            file=file, link_preview=False, noforwards=noforwards,
                        ),
                        timeout=15,
                    )
                raise
    except Exception as e:
        # HTTP fallback for text messages when Telethon cannot resolve the channel entity
        if file is None:
            result = await _styled_send_http(chat_id, text, entities=entities, buttons=buttons)
            if result is not None:
                return result
        log_system("STYLED_SEND_ERR", f"Chat={chat_id} Error={repr(e)}", "error")
        return None


async def styled_edit(msg, html_text, buttons=None, emoji_ids=None):
    for _attempt in range(2):
        try:
            async with _TG_RATE:
                text, entities = build_entities(html_text, emoji_ids)
                await asyncio.wait_for(msg.edit(text, formatting_entities=entities, buttons=buttons, link_preview=False), timeout=10)
            return
        except FloodWaitError as e:
            await asyncio.sleep(min(e.seconds + 1, 15))
        except MessageNotModifiedError:
            return
        except Exception as e:
            log_system("STYLED_EDIT_ERR", f"Error={repr(e)}", "error")
            return


def pbtn(text, data=None, url=None, color=None, icon=None):
    text = _btn_label(text)
    style = None
    if color == "blue":
        style = "primary"
    elif color == "green":
        style = "success"
    elif color == "red":
        style = "danger"
        
    if url:
        return Button.url(text, url, style=style)
    if data:
        return Button.inline(text, data.encode() if isinstance(data, str) else data, style=style, icon=icon)
    return Button.inline(text, b"none", style=style, icon=icon)

def get_hit_button(status=None, is_channel=False):
    if is_channel:
        color = "blue"
    elif not status:
        color = "blue"
    else:
        s = status.lower()
        if "charged" in s:
            color = "blue"
        elif "approved" in s:
            color = "green"
        elif "declined" in s:
            color = "red"
        else:
            color = "blue"
    return [[pbtn(bs(BOT_NAME), url=BOT_LINK, color=color)]]


# ====================== STATUS EMOJI HELPER ======================
def get_status_emoji_id(status):
    import random
    s = status.upper()
    if s == "CHARGED":
        return random.choice(CHARGED_EMOJIS)
    elif s == "APPROVED":
        return CE["approved"]
    else:
        return CE["declined"]


# ====================== EXTRACT GATEWAY FROM API ======================
def extract_gateway_from_api(rj):
    gw = rj.get('Gateway', '')
    if gw and str(gw).strip() not in ('', '-', 'null', 'None', 'unknown', 'Unknown', 'UNKNOWN'):
        return str(gw).strip()
    gw2 = rj.get('gateway', '')
    if gw2 and str(gw2).strip() not in ('', '-', 'null', 'None', 'unknown', 'Unknown', 'UNKNOWN'):
        return str(gw2).strip()
    gw3 = rj.get('Gate', '')
    if gw3 and str(gw3).strip() not in ('', '-', 'null', 'None', 'unknown', 'Unknown', 'UNKNOWN'):
        return str(gw3).strip()
    gw4 = rj.get('gate', '')
    if gw4 and str(gw4).strip() not in ('', '-', 'null', 'None', 'unknown', 'Unknown', 'UNKNOWN'):
        return str(gw4).strip()
    return 'Shopify Payments'


# ====================== UNIFIED UI FORMATTERS (SANS BOLD, NO HTML TAGS) ======================
def format_single_result(status, card, gateway, response, bin_info=None, user_name="User", user_link="#", user_tag="TRIAL", proxy_status=None):
    bi = bin_info or {"brand": "-", "type": "-", "level": "-", "bank": "-", "country": "-", "flag": "🏳️"}
    proxy_line = ""
    if proxy_status:
        proxy_line = f" / {bs('Proxy')} {ARROW} {bs(proxy_status)} {PE}"
    return f"""{bs('Status')} {ARROW} {bs(status.upper())} {PE}
{PE} {ARROW} <code>{card}</code>
{bs('Gate')} {ARROW} {bs(gateway)}
{bs('Response')} {ARROW} {bs(response)}
{bs('Brand')} {ARROW} {bs(bi.get('brand', '-'))}
{bs('Issuer')} {ARROW} {bs(bi.get('bank', '-'))}
{bs('Country')} {ARROW} {bi.get('flag', '🏳️')} {bs(bi.get('country', '-'))}
{bs('User')} {ARROW} <a href="{user_link}">{bs(user_name)}</a> ({bs(user_tag)})
{PE} {bs('Dev')} {ARROW} <a href='{DEV_LINK}'>{bs(DEV_NAME)}</a> {PE}{proxy_line}"""


def format_mass_hit_dm(status, card, gateway, response, bin_info=None, user_name="User", user_link="#", user_tag="TRIAL", proxy_status=None):
    bi = bin_info or {"brand": "-", "type": "-", "level": "-", "bank": "-", "country": "-", "flag": "🏳️"}
    proxy_line = ""
    if proxy_status:
        proxy_line = f" / {bs('Proxy')} {ARROW} {bs(proxy_status)} {PE}"
    return f"""{bs('Status')} {ARROW} {bs(status.upper())} {PE}
{PE} {ARROW} <code>{card}</code>
{bs('Gate')} {ARROW} {bs(gateway)}
{bs('Response')} {ARROW} {bs(response)}
{bs('Brand')} {ARROW} {bs(bi.get('brand', '-'))}
{bs('Issuer')} {ARROW} {bs(bi.get('bank', '-'))}
{bs('Country')} {ARROW} {bi.get('flag', '🏳️')} {bs(bi.get('country', '-'))}
{bs('User')} {ARROW} <a href="{user_link}">{bs(user_name)}</a> ({bs(user_tag)})
{PE} {bs('Dev')} {ARROW} <a href='{DEV_LINK}'>{bs(DEV_NAME)}</a> {PE}{proxy_line}"""


_CHANNEL_HIT_RESPONSE_EMOJIS = list(dict.fromkeys([
    5839116473951328489, 5116163917713769254, 5445027583588593750,
]))
_CHANNEL_HIT_USERNAME_STAR_EMOJIS = list(dict.fromkeys([
    5837208434730077905, 5836898273666798437, 5839049953497844833, 5415588516237157133,
    5379869575338812919, 5235611059909323996, 5346309121794659890,
]))


def format_channel_hit(status, gateway, response, user_name, user_link, user_tag, price=None, status_emoji_id=None):
    st_emoji = status_emoji_id or 5318770787925113164
    user_emoji_id = 5445174334031166029
    check_emoji = random.choice(_CHANNEL_HIT_RESPONSE_EMOJIS)
    star_emoji = random.choice(_CHANNEL_HIT_USERNAME_STAR_EMOJIS)
    emoji_list = [st_emoji, check_emoji, user_emoji_id, star_emoji]
    text = f"""{bs('HIT')} ➺ {bs(status.upper())} {PE}
{bs('Gate')} ➺ {bs(gateway)}
{PE} {bs(response)}
{PE} ➺ <a href="{user_link}">{bs(user_name)}</a> {PE}"""
    return text, emoji_list


def format_mass_progress(gate_name, status_label, checked, total, approved, charged, declined, errors, elapsed_str, session_id, user_link=None):
    ulink = user_link or bs("User")
    return f"""{bs('Gateway')} {ARROW} {bs(gate_name)} {bs('Mass')}
{bs('Status')} {ARROW} {bs(status_label)} {PE}
{bs('Checked')} {ARROW} {bval(f'{checked}/{total}')}
{bs('Approved')} {ARROW} {bval(approved)} {PE}
{bs('CHARGED')} {ARROW} {bval(charged)} {PE}
{bs('Dead')} {ARROW} {bval(declined)} {PE}
{bs('Errors')} {ARROW} {bval(errors)} {PE}
{PE} {bs('Time')} {ARROW} {bval(elapsed_str)}
{PE} {bs('User')} {ARROW} {ulink}
{PE} {bs('Dev')} {ARROW} <a href='{DEV_LINK}'>{bs(DEV_NAME)}</a> {PE}
{PE} {bs('Session ID')} {ARROW} <code>{session_id}</code>"""


def get_mass_progress_emojis(status_label):
    if status_label == "CHECKING":
        status_eid = 5220046725493828505
    elif status_label == "FINISHED":
        status_eid = 4915791289489818259
    else:
        status_eid = 5275969776668134187

    app_eid = 4916036072560919511
    ch_eid = CE["charged"]
    dead_eid = 4918014360267260850
    err_eid = 4915853119839011973
    time_eid = 5318770787925113164
    user_eid = 5445174334031166029
    dev_eid = get_random_dev_emoji()
    star_eid = 6233303538676541503
    sess_eid = 5301275719681190738

    return [
        status_eid,
        app_eid,
        ch_eid,
        dead_eid,
        err_eid,
        time_eid,
        user_eid,
        dev_eid,
        star_eid,
        sess_eid,
    ]


def make_mass_buttons(approved, charged, declined, checked, session_id=None, is_done=False, errors=0):
    dead_count = declined + errors
    all_count = approved + charged + declined + errors
    sid = session_id or "session"
    app_btn = pbtn(f"{bs('Approved')} ({approved})", data=f"mass_file:approved:{sid}", color="green", icon=4916036072560919511)
    dead_btn = pbtn(f"{bs('Dead')} ({dead_count})", data=f"mass_file:dead:{sid}", color="red", icon=4918014360267260850)
    all_btn = pbtn(f"{bs('All')} ({all_count})", data=f"mass_file:all:{sid}", color="blue", icon=5282843764451195532)

    return [
        [app_btn, dead_btn],
        [all_btn]
    ]


SH_MAX_CARDS = 15
SH_CARDS_PER_PAGE = 10
SH_COMPLETE_EMOJI = 4958610528588008305


def _sh_format_response_label(response):
    resp = str(response or "").strip()
    if not resp:
        return "UNKNOWN"
    rl = resp.lower().replace("_", " ")
    if any(k in rl for k in ("3ds", "otp", "authentication", "3d redirect", "3d required")):
        return "3DS REQUIRED"
    if "insufficient" in rl and "fund" in rl:
        return "INSUFFICIENT FUNDS"
    if "ccn" in rl:
        return "CCN LIVE"
    if "cvc" in rl:
        return "CVC MATCH"
    return resp.upper().replace("_", " ")[:60]


def _sh_status_label(status, response=""):
    resp = str(response or "").lower()
    if status == "Charged":
        return "CHARGED", CE["charged"]
    if status == "Approved":
        return _sh_format_response_label(response), CE["approved"]
    if status in ("Error", "SiteError"):
        return _sh_format_response_label(response) if response else "ERROR", CE["cross"]
    return "CARD DECLINED", CE["declined"]


def _sh_format_bin_info(bi):
    brand = str(bi.get("brand") or "-").strip().upper()
    bank = str(bi.get("bank") or "-").strip().upper()
    if bank.lower() in ("none", "null", ""):
        bank = "-"
    country = str(bi.get("country") or "-").strip().upper()
    flag = bi.get("flag", "🏳️")
    info_text = html.escape(f"{brand} - {bank} - {country}")
    return f"<code>{info_text}</code> {flag}"


def _sh_format_status_bin_line(label, bi):
    return f"{bs(label)} {PE} {ARROW} {_sh_format_bin_info(bi)}"


def _sh_total_pages(result_count):
    if result_count <= 0:
        return 1
    return (result_count + SH_CARDS_PER_PAGE - 1) // SH_CARDS_PER_PAGE


def format_sh_message(session, page_index):
    results = session["results"]
    total = session["total"]
    checked = len(results)
    elapsed = format_elapsed(time.time() - session["start"])
    uid = session["user_id"]
    user_link = user_link_html(uid, session.get("name") or "User", session.get("username"))
    emoji_ids = []

    if checked == 0 and not session.get("done"):
        text = "\n".join([
            f"{bs('Total Cards')} {ARROW} {bval(total)}",
            f"{bs('Elapsed')} {ARROW} {bval('0s')}",
            f"{bs('Starting Mass Check')}⏳...",
        ])
        return text, emoji_ids

    total_pages = _sh_total_pages(checked) if checked else 1
    page_index = max(0, min(page_index, total_pages - 1))
    page_results = results[page_index * SH_CARDS_PER_PAGE:(page_index + 1) * SH_CARDS_PER_PAGE]

    header_lines = [
        f"{bs('TOTAL CARDS')} {ARROW} {bval(f'{checked}/{total}')}",
        f"{bs('TIME')} {ARROW} {bval(elapsed)}",
        f"{bs('USER')} {ARROW} {user_link}",
    ]
    lines = list(header_lines)
    lines.append(UI_SEP)
    for item in page_results:
        label, eid = _sh_status_label(item["status"], item.get("response", ""))
        bi = item.get("bin_info") or {}
        card_line = f"<code>{html.escape(item['card'])}</code>"
        status_line = _sh_format_status_bin_line(label, bi)
        lines.extend([card_line, status_line, UI_SEP])
        emoji_ids.append(eid)

    if session.get("done") and page_index == total_pages - 1:
        lines.append(f"{bs('CHECK COMPLETE.')} {PE}")
        emoji_ids.append(SH_COMPLETE_EMOJI)

    return "\n".join(lines), emoji_ids


def build_sh_buttons(session_id, page_index, result_count, done=False):
    total_pages = _sh_total_pages(result_count) if result_count else 1
    page_index = max(0, min(page_index, total_pages - 1))
    if total_pages <= 1 and not done:
        return None
    nav = []
    if page_index > 0:
        nav.append(pbtn(f"« {bs('Back')}", f"sh_page:{session_id}:{page_index - 1}", color="blue"))
    if total_pages > 1:
        nav.append(pbtn(bs(f"{page_index + 1} / {total_pages}"), f"sh_nop:{session_id}"))
    if page_index < total_pages - 1:
        nav.append(pbtn(f"{bs('Next')} »", f"sh_page:{session_id}:{page_index + 1}", color="blue"))
    return [nav] if nav else None


async def _edit_sh_message(msg, session, page_index=None, force_latest=False):
    if page_index is None:
        page_index = session.get("view_page", 0)
    if not session.get("done") and force_latest:
        page_index = max(page_index, _sh_total_pages(len(session["results"])) - 1)
    session["view_page"] = page_index
    text, emoji_ids = format_sh_message(session, page_index)
    buttons = build_sh_buttons(
        session["session_id"],
        page_index,
        len(session["results"]),
        done=session.get("done", False),
    )
    await styled_edit(msg, text, buttons=buttons, emoji_ids=emoji_ids or None)
    try:
        await save_sh_session(session)
    except Exception:
        pass


def format_elapsed(seconds):
    h = int(seconds) // 3600
    m = (int(seconds) % 3600) // 60
    s = int(seconds) % 60
    if h > 0:
        return f"{h}h {m}m {s}s"
    if m > 0:
        return f"{m}m {s}s"
    return f"{s}s"


def slowdown_wait_text(seconds):
    return f"⚠️ {bs('Slow Down!')}\n{bs('Wait')} <code>{int(seconds)}s</code>"


# ====================== FORCE JOIN ======================
async def check_membership_via_http(chat_id: int, user_id: int):
    try:
        url = f"https://api.telegram.org/bot{BOT_TOKEN}/getChatMember"
        params = {"chat_id": chat_id, "user_id": user_id}
        async with aiohttp.ClientSession() as session:
            async with session.get(url, params=params, timeout=10) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    if data.get("ok"):
                        return data["result"].get("status")
        return None
    except Exception as e:
        log_system("FORCE_JOIN", f"HTTP membership check failed for {chat_id}: {e}", "warning")
        return None


async def safe_get_member(chat_id, user_id):
    """Returns True if joined, False if not, None if verification failed."""
    try:
        r = await asyncio.wait_for(
            client_instance(GetParticipantRequest(channel=chat_id, participant=user_id)),
            timeout=10,
        )
        if isinstance(r.participant, ChannelParticipantLeft):
            log_system("FORCE_JOIN", f"User {user_id} not active in {chat_id}: {type(r.participant).__name__}", "warning")
            return False
        if isinstance(r.participant, ChannelParticipantBanned):
            if r.participant.banned_rights and r.participant.banned_rights.view_messages:
                log_system("FORCE_JOIN", f"User {user_id} kicked from {chat_id}: {type(r.participant).__name__}", "warning")
                return False
            else:
                log_system("FORCE_JOIN", f"User {user_id} restricted/muted in {chat_id} but still member, allowing")
                return True
        log_system("FORCE_JOIN", f"User {user_id} in {chat_id}: {type(r.participant).__name__}")
        return True
    except UserNotParticipantError:
        log_system("FORCE_JOIN", f"User {user_id} NOT in {chat_id}", "warning")
        return False
    except Exception as e:
        # Fall back to Telegram Bot HTTP API to bypass all MTProto entity caching limitations
        log_system("FORCE_JOIN", f"MTProto check failed for {chat_id} (Error: {e}). Trying HTTP Bot API fallback...", "warning")
        try:
            status = await check_membership_via_http(chat_id, user_id)
            if status in ("creator", "administrator", "member", "restricted"):
                log_system("FORCE_JOIN", f"HTTP Success: User {user_id} in {chat_id} (Status: {status})")
                return True
            elif status in ("left", "kicked"):
                log_system("FORCE_JOIN", f"HTTP Success: User {user_id} NOT in {chat_id} (Status: {status})", "warning")
                return False
            else:
                log_system("FORCE_JOIN", f"HTTP Check returned unknown status {status} for {chat_id}", "warning")
        except Exception as ex:
            log_system("FORCE_JOIN", f"HTTP fallback failed for {chat_id}: {ex}", "warning")
        return None


async def is_user_joined(user_id):
    if user_id in ADMIN_ID:
        return True
    now = time.time()
    cached = _JOIN_CACHE.get(user_id)
    if cached and now - cached < 600:
        return True

    group_ok = await safe_get_member(JOIN_GROUP_ID, user_id)
    logs_ok = await safe_get_member(LOGS_CHANNEL_ID, user_id)
    hits_ok = await safe_get_member(HITS_CHANNEL_ID, user_id)

    if group_ok is False or logs_ok is False or hits_ok is False:
        await remove_joined_mark(user_id)
        _JOIN_CACHE.pop(user_id, None)
        return False
    
    if group_ok is True and logs_ok is True and hits_ok is True:
        await mark_user_joined(user_id)
        _JOIN_CACHE[user_id] = now
        return True

    # Telegram API could not verify — trust a prior successful "I have joined" check
    if await is_user_marked_joined(user_id):
        return True

    return False


async def force_join_check(event):
    if event.sender_id in ADMIN_ID:
        return True
    if getattr(event, "raw_text", None) and re.match(r'(?i)^[/.]start\b', event.raw_text.strip()):
        return True
    if await is_user_joined(event.sender_id):
        return True
    buttons = [
        [pbtn(bs("Join Logs Channel"), url=LOGS_CHANNEL_LINK, color="blue")],
        [pbtn(bs("Join Hits Channel"), url=HITS_CHANNEL_LINK, color="blue")],
        [pbtn(bs("Join Group"), url=JOIN_GROUP_LINK, color="blue")],
        [pbtn(bs("I have joined"), data="check_joined", color="green")]
    ]
    text = f"""{bs('Access Locked')} {PE}
{UI_SEP}
{PE} {bs('Join All Three to Unlock')}
{PE} {bs('Logs')} {ARROW} {bs(BOT_NAME + ' Logs')}
{PE} {bs('Hits')} {ARROW} {bs(BOT_NAME + ' Hits')}
{PE} {bs('Group')} {ARROW} {bs(BOT_NAME + ' Chat')}
{UI_SEP}
{PE} {bs('All Features Restricted')}"""
    try:
        await styled_reply(event, text, buttons=buttons, emoji_ids=[CE["fire"], CE["stop"], CE["link"], CE["link"], CE["link"], CE["warn"]], file=random.choice(FORCE_JOIN_IMAGES))
    except Exception:
        await styled_reply(event, text, buttons=buttons, emoji_ids=[CE["fire"], CE["stop"], CE["link"], CE["link"], CE["link"], CE["warn"]])
    return False


# ====================== MAINTENANCE ======================
MAINTENANCE_BLOCK_EMOJI = 5042112436648281096
MAINTENANCE_BLOCK_TEXT = f"{bs('Bot under maintenance. Will be up in some time.')} {PE}"


async def reply_maintenance_blocked(event):
    await styled_reply(event, MAINTENANCE_BLOCK_TEXT, emoji_ids=[MAINTENANCE_BLOCK_EMOJI])


async def save_maintenance_config():
    global _GATE_MAINT
    try:
        # Save to local file as backup
        data = {}
        if os.path.exists(MAINTENANCE_FILE):
            try:
                async with aiofiles.open(MAINTENANCE_FILE, "r") as f:
                    data = json.loads(await f.read())
            except Exception:
                pass
        data["gates"] = _GATE_MAINT
        async with aiofiles.open(MAINTENANCE_FILE, "w") as f:
            await f.write(json.dumps(data))
    except Exception:
        pass
    try:
        global_maint = await get_maintenance_mode()
        await save_maintenance_db(global_maint, _GATE_MAINT)
    except Exception:
        pass


async def load_maintenance_config():
    global _GATE_MAINT, _MAINTENANCE_CACHE
    # 1. Try loading from Database
    try:
        global_maint, gates, success = await load_maintenance_db()
        if success:
            stale_mpp = gates.pop("mpp", None) is not None
            _GATE_MAINT.update(gates)
            _GATE_MAINT.pop("mpp", None)
            _MAINTENANCE_CACHE = {"enabled": global_maint, "last_check": time.time()}
            if stale_mpp:
                await save_maintenance_db(global_maint, _GATE_MAINT)
            # Write back to local file as cache/backup
            try:
                async with aiofiles.open(MAINTENANCE_FILE, "w") as f:
                    await f.write(json.dumps({"maintenance": global_maint, "gates": _GATE_MAINT}))
            except:
                pass
            return
    except Exception:
        pass

    # 2. Fallback to local file if DB load failed/empty
    try:
        if not os.path.exists(MAINTENANCE_FILE):
            return
        async with aiofiles.open(MAINTENANCE_FILE, "r") as f:
            data = json.loads(await f.read())
            gates = data.get("gates", {})
            if isinstance(gates, dict):
                gates.pop("mpp", None)
                _GATE_MAINT.update(gates)
                _GATE_MAINT.pop("mpp", None)
            global_maint = data.get("maintenance", False)
            _MAINTENANCE_CACHE = {"enabled": global_maint, "last_check": time.time()}
    except Exception:
        pass


async def set_maintenance_mode(enabled):
    global _MAINTENANCE_CACHE
    try:
        data = {}
        if os.path.exists(MAINTENANCE_FILE):
            try:
                async with aiofiles.open(MAINTENANCE_FILE, "r") as f:
                    data = json.loads(await f.read())
            except Exception:
                pass
        data["maintenance"] = enabled
        async with aiofiles.open(MAINTENANCE_FILE, "w") as f:
            await f.write(json.dumps(data))
        _MAINTENANCE_CACHE = {"enabled": enabled, "last_check": time.time()}
    except Exception:
        pass
    try:
        await save_maintenance_db(enabled, _GATE_MAINT)
    except Exception:
        pass


async def get_maintenance_mode():
    global _MAINTENANCE_CACHE, _GATE_MAINT
    now = time.time()
    if _MAINTENANCE_CACHE["enabled"] is not None and now - _MAINTENANCE_CACHE["last_check"] < 30:
        return _MAINTENANCE_CACHE["enabled"]
    try:
        global_maint, gates, success = await load_maintenance_db()
        if success:
            _GATE_MAINT.update(gates)
            _GATE_MAINT.pop("mpp", None)
            _MAINTENANCE_CACHE = {"enabled": global_maint, "last_check": now}
            return global_maint
    except Exception:
        pass
    try:
        if not os.path.exists(MAINTENANCE_FILE):
            return False
        async with aiofiles.open(MAINTENANCE_FILE, "r") as f:
            data = json.loads(await f.read())
            gates = data.get("gates", {})
            if isinstance(gates, dict):
                _GATE_MAINT.update(gates)
                _GATE_MAINT.pop("mpp", None)
            val = data.get("maintenance", False)
            _MAINTENANCE_CACHE = {"enabled": val, "last_check": now}
            return val
    except Exception:
        return False


async def check_maintenance(event):
    if await get_maintenance_mode() and event.sender_id not in ADMIN_ID:
        await reply_maintenance_blocked(event)
        return True
    return False


async def check_gate_maintenance(event, gate_key):
    if event.sender_id in ADMIN_ID:
        return False
    if _GATE_MAINT.get(gate_key, False):
        gname = _MAINT_GATE_NAMES.get(gate_key, gate_key)
        await styled_reply(
            event,
            f"{PE} {bs(f'{gname} under maintenance. Will be up in some time.')}",
            emoji_ids=[MAINTENANCE_BLOCK_EMOJI],
        )
        return True
    return False


# ====================== ACCESS ======================
def _broadcast_user_chats():
    """Group only — used by /broad (no Logs/Hits channels)."""
    chats = []
    if JOIN_GROUP_ID is not None:
        chats.append(JOIN_GROUP_ID)
    return chats


def _maint_group_only_chats():
    """Group only — used by /maintenance announcements (no Logs/Hits channels)."""
    chats = []
    if JOIN_GROUP_ID is not None:
        chats.append(JOIN_GROUP_ID)
    return chats


async def _announce_maintenance_change(gate: str, state: bool):
    """Announce maintenance ON/OFF using fixed custom emoji IDs."""
    down_eid = 5258077595748030166
    up_eid = 4958610528588008305

    async def _announce_to_group(text, emoji_ids=None):
        for chat_id in _maint_group_only_chats():
            try:
                await styled_send(chat_id, text, emoji_ids=emoji_ids)
            except Exception as e:
                log_system("MAINT_ANNOUNCE_ERR", f"Chat={chat_id} Error={e}", "error")
            await asyncio.sleep(0.15)

    if gate == "global":
        if state:
            await _announce_to_group(MAINTENANCE_BLOCK_TEXT, emoji_ids=[MAINTENANCE_BLOCK_EMOJI])
        else:
            text = f"{bs('Bot up.')} {PE}"
            await _announce_to_group(text, emoji_ids=[up_eid])
        return
    if gate == "all":
        for gk, gname in _MAINT_GATE_NAMES.items():
            if state:
                text = f"{PE} {bs(gname)} {bs('under maintenance. Will be up in some time.')}"
                await _announce_to_group(text, emoji_ids=[down_eid])
            else:
                text = f"{bs(gname)} {bs('is up.')} {PE}"
                await _announce_to_group(text, emoji_ids=[up_eid])
        return
    gname = _MAINT_GATE_NAMES.get(gate, gate)
    if state:
        text = f"{PE} {bs(gname)} {bs('under maintenance. Will be up in some time.')}"
        await _announce_to_group(text, emoji_ids=[down_eid])
    else:
        text = f"{bs(gname)} {bs('is up.')} {PE}"
        await _announce_to_group(text, emoji_ids=[up_eid])



async def can_use(user_id, chat, event=None):
    try:
        sender = await client_instance.get_entity(user_id)
        username = getattr(sender, 'username', None)
        name = getattr(sender, 'first_name', None) or username or f"user_{user_id}"
        await ensure_user(user_id, name=name, username=username)
    except Exception:
        await ensure_user(user_id)
    if await is_banned_user(user_id):
        return False, "banned"
    plan = (await get_user_plan(user_id)).title()
    chat_id = getattr(chat, "id", None) if chat is not None else None
    if chat_id is None and event is not None:
        chat_id = event.chat_id
    scope = f"{plan}_private" if chat_id == user_id else f"{plan}_group"
    return True, scope


async def get_user_access(event):
    uid = event.sender_id
    try:
        sender = await event.get_sender()
        username = getattr(sender, 'username', None)
        name = getattr(sender, 'first_name', None) or getattr(sender, 'last_name', None) or username or f"user_{uid}"
        await ensure_user(uid, name=name, username=username)
    except Exception:
        await ensure_user(uid)
    if await is_banned_user(uid):
        return False, "banned", FREE_PLAN
    plan = (await get_user_plan(uid)).title()
    return True, f"{plan}_private" if event.chat.id == uid else f"{plan}_group", plan


def get_cc_limit(plan, uid=None):
    """Mass-check card limit. Single gates (/sp, etc.) are not capped by this."""
    if uid and uid in ADMIN_ID:
        return 10000
    p = plan.title() if plan else FREE_PLAN
    if p in (FREE_PLAN, "Bronze"):
        return 0
    if p == "Custom":
        return 2000  # key plan: mass only
    if p == "X":
        return 10000
    if p == "Root":
        return 6500
    if p == "Elite":
        return 4500
    if p == "Core":
        return 3000
    return 0


def is_paid_plan(plan):
    return plan.title() in PAID_TIERS if plan else False


def is_owner(uid) -> bool:
    return uid in ADMIN_ID


async def send_owner_only_message(event):
    return await styled_reply(
        event,
        f"{PE} {bs('Owner only command!')}",
        emoji_ids=[5042112436648281096],
    )


def shopify_proxy_gate_for_plan(plan=None) -> str:
    """Paid Shopify checks use shopify pool; Custom (key) users use shopify_key pool."""
    return "shopify_key" if is_key_user_plan(plan) else "shopify"


async def get_owner_proxies(gate: str = "shopify"):
    """Owner proxies for one gate pool (shopify | shopify_key)."""
    gate = _norm_proxy_gate(gate)
    for admin_id in ADMIN_ID:
        try:
            proxies = await get_all_user_proxies(admin_id, gate=gate)
        except Exception:
            proxies = []
        if proxies:
            return proxies
    return []


async def get_owner_check_resources(plan=None):
    """Shopify sites (shared) + owner proxies for the user's Shopify pool."""
    sites = []
    try:
        sites = await get_shopify_sites()
    except Exception:
        sites = []
    proxy_gate = shopify_proxy_gate_for_plan(plan)
    proxies = await get_owner_proxies(proxy_gate)
    return sites or [], proxies or []


def format_premium_time_left(expiry) -> str:
    if not expiry:
        return "0d 0h"
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    if expiry.tzinfo is not None:
        now = datetime.now(expiry.tzinfo)
    delta = expiry - now
    total_seconds = max(0, int(delta.total_seconds()))
    days = total_seconds // 86400
    hours = (total_seconds % 86400) // 3600
    return f"{days}d {hours}h"


async def send_group_only_message(event):
    return await styled_reply(event, f"""{bs('Group Only')} {PE}
{PE} {bs('Free users')} → {bs('group only')}
{PE} {bs('Upgrade for private access')}""", emoji_ids=[CE["stop"], CE["warn"], CE["gem"]])


async def send_premium_only_message(event):
    return await styled_reply(event, f"""{bs('Premium Only')} {PE}
{PE} {bs('This feature requires an active plan')}
{PE} {bs('Use /plan to see available plans')}""", buttons=[[pbtn(bs("Upgrade"), url="{DEV_LINK}")]], emoji_ids=[CE["stop"], CE["warn"], CE["info"]])


def banned_user_message():
    return f"""{bs('Banned')} {PE}
{PE} {bs('Not allowed')}
{PE} {bs('Appeal')} {ARROW} {bs('Contact Admin')}""", [CE["stop"], CE["warn"], CE["info"]]


# ====================== UTILITIES ======================
def extract_cc(text):
    if not text:
        return []
    cards = []
    for c, m, y, cv in re.findall(r'(\d{15,16})[\s|/\\:]+(\d{2})[\s|/\\:]+(\d{2,4})[\s|/\\:]+(\d{3,4})', text):
        if len(y) == 2:
            y = '20' + y
        cards.append(f"{c}|{m}|{y}|{cv}")
    if not cards:
        for c, m, y, cv in re.findall(r'(\d{15,16})[\s|/\\:]+(\d{2})[\s|/\\:]+(\d{4})(\d{3,4})', text):
            cards.append(f"{c}|{m}|{y}|{cv}")
    if not cards:
        for c, m, y, cv in re.findall(r'(\d{15,16})[\s|/\\:]+(\d{2})[\s|/\\:]+(\d{2})(\d{3,4})', text):
            cards.append(f"{c}|{m}|20{y}|{cv}")
    return list(dict.fromkeys(cards))


def luhn_valid(card_number: str) -> bool:
    digits = re.sub(r"\D", "", str(card_number or ""))
    if not digits.isdigit() or len(digits) < 13:
        return False
    total = 0
    for i, ch in enumerate(reversed(digits)):
        n = int(ch)
        if i % 2 == 1:
            n *= 2
            if n > 9:
                n -= 9
        total += n
    return total % 10 == 0


def is_card_expired(mm: str, yy: str) -> bool:
    try:
        month = int(mm)
        year = int(yy)
        if year < 100:
            year += 2000
        if month < 1 or month > 12:
            return True
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        if year < now.year:
            return True
        if year == now.year and month < now.month:
            return True
        return False
    except (ValueError, TypeError):
        return True


def validate_card(card: str):
    parts = str(card or "").split("|")
    if len(parts) < 4:
        return False, "format"
    cn, mm, yy = parts[0].strip(), parts[1].strip(), parts[2].strip()
    if not luhn_valid(cn):
        return False, "luhn"
    if is_card_expired(mm, yy):
        return False, "expired"
    return True, None


def filter_valid_cards(cards):
    valid, removed = [], 0
    for card in cards:
        ok, _ = validate_card(card)
        if ok:
            valid.append(card)
        else:
            removed += 1
    return valid, removed


def format_invalid_card_reply(reason: str) -> str:
    if reason == "expired":
        detail = "Card expired."
    else:
        detail = "Luhn check failed."
    return f"❌ {bs('Invalid Card Number')}\n{bs(detail)}"


def format_mass_card_filter_notice(removed: int, valid_count: int) -> str:
    if removed <= 0:
        return ""
    label = "card" if removed == 1 else "cards"
    return f"ℹ️ {bs('Removed:')} {bval(removed)} {bs(f'invalid/expired {label}.')}"


async def reply_invalid_card(event, reason: str):
    return await styled_reply(event, format_invalid_card_reply(reason), emoji_ids=[CE["cross"]])


async def reply_mass_card_filter_notice(event, removed: int, valid_count: int):
    notice = format_mass_card_filter_notice(removed, valid_count)
    if not notice:
        return
    return await styled_reply(event, notice, emoji_ids=[CE["info"]])


def extract_urls_from_text(text):
    """Pull every site URL/domain from free-form text.

    Supports multiple URLs on one line, newlines, commas/pipes, with or without
    https://, Shopify domains only. Previous logic only kept the first
    https URL per line, so pasted multi-URL messages lost sites.
    """
    if not text:
        return []
    seen, result = set(), []

    def _add(raw):
        raw = str(raw or "").strip()
        if not raw:
            return
        # Trim common trailing junk from pasted chat text / markdown
        raw = raw.rstrip(".,;:!?)>]}\"'" )
        raw = raw.lstrip("<([\"'")
        if not raw:
            return
        norm = normalize_site_url(raw)
        if norm and is_valid_url_or_domain(norm) and norm not in seen:
            seen.add(norm)
            result.append(norm)

    # 1) Every explicit http(s) URL anywhere in the blob (multi-per-line OK)
    for m in re.finditer(r"https?://[^\s<>\"'\)\]\}]+", str(text), flags=re.IGNORECASE):
        _add(m.group(0))

    # 2) Bare host or host/path tokens (no scheme) between separators
    for token in re.split(r"[\s,|;]+", str(text)):
        token = token.strip()
        if not token:
            continue
        low = token.lower()
        if low.startswith(("http://", "https://", "/add", ".add")):
            continue
        # Drop list markers / leading junk: "1. site.com", "- site.com"
        token = re.sub(r"^[\s\-\+\|,\d\.\)\(\[\]]+", "", token).split("{")[0].strip()
        if token and "." in token:
            _add(token)

    return result


def parse_proxy_format(proxy):
    proxy = proxy.strip()
    pt = 'http'
    pm = re.match(r'^(socks5|socks4|http|https)://(.+)$', proxy, re.IGNORECASE)
    if pm:
        pt, proxy = pm.group(1).lower(), pm.group(2)
    h = p = u = pw = ''
    m = re.match(r'^([^@:]+):([^@]+)@([^:@]+):(\d+)$', proxy)
    if m:
        u, pw, h, p = m.groups()
    elif re.match(r'^([^:]+):(\d+):([^:]+):(.+)$', proxy):
        m2 = re.match(r'^([^:]+):(\d+):([^:]+):(.+)$', proxy)
        ph, pp, pu, ppw = m2.groups()
        if 0 < int(pp) <= 65535:
            h, p, u, pw = ph, pp, pu, ppw
    elif re.match(r'^([^:@]+):(\d+)$', proxy):
        m3 = re.match(r'^([^:@]+):(\d+)$', proxy)
        h, p = m3.groups()
    else:
        return None
    if not h or not p:
        return None
    try:
        if not (0 < int(p) <= 65535):
            return None
    except Exception:
        return None
    pu = f'{pt}://{u}:{pw}@{h}:{p}' if u and pw else f'{pt}://{h}:{p}'
    return {'ip': h, 'port': p, 'username': u or None, 'password': pw or None, 'proxy_url': pu, 'type': pt}


async def test_proxy(proxy_url):
    try:
        s = await get_proxy_session()
        async with _PROXY_SEM:
            async with s.get('http://api.ipify.org?format=json', proxy=proxy_url) as r:
                if r.status == 200:
                    return True, (await r.json()).get('ip', '?')
                return False, None
    except Exception as e:
        return False, str(e)


async def get_bin_info(cn):
    try:
        s = await get_bin_session()
        async with _BIN_SEM:
            async with s.get(f'https://bins.antipublic.cc/bins/{cn[:6]}') as r:
                if r.status != 200:
                    return {"brand": "-", "type": "-", "level": "-", "bank": "-", "country": "-", "flag": "🏳️"}
                d = await r.json(content_type=None)
                return {"brand": d.get('brand', '-'), "type": d.get('type', '-'), "level": d.get('level', '-'), "bank": d.get('bank', '-'), "country": d.get('country_name', '-'), "flag": d.get('country_flag', '🏳️')}
    except Exception:
        return {"brand": "-", "type": "-", "level": "-", "bank": "-", "country": "-", "flag": "🏳️"}


BINLIST_URL = "https://bins.antipublic.cc/bins/{}"


async def lookup_bin(bin_number: str) -> dict:
    """Fetch BIN information from the antipublic.cc API for /bin command."""
    if not bin_number.isdigit() or len(bin_number) < 6:
        return {"error": "Invalid BIN. Must be at least 6 digits."}

    async with aiohttp.ClientSession() as session:
        try:
            async with session.get(BINLIST_URL.format(bin_number[:6])) as resp:
                if resp.status == 429:
                    return {"error": "Rate limit exceeded. Try again later."}
                if resp.status == 404:
                    return {"error": "BIN not found."}
                if resp.status != 200:
                    return {"error": f"API request failed (status {resp.status})"}

                data = await resp.json()

                return {
                    "bin": data.get("bin"),
                    "length": "N/A",
                    "luhn": "N/A",
                    "scheme": data.get("brand"),
                    "type": data.get("type"),
                    "brand": data.get("level"),
                    "bank": data.get("bank"),
                    "bank_phone": "N/A",
                    "bank_url": "N/A",
                    "country": data.get("country_name"),
                    "country_emoji": data.get("country_flag"),
                }
        except Exception as e:
            return {"error": f"Exception: {str(e)}"}


def _format_vbv_card(card: str) -> Optional[str]:
    parts = card.split('|')
    if len(parts) < 4:
        return None
    cn, mm, yy, cvv = parts[0], parts[1], parts[2], parts[3]
    if len(yy) == 4:
        yy = yy[2:]
    return f"{cn}|{mm}|20{yy}|{cvv}"


def _parse_vbv_status(api_response: dict) -> tuple:
    if not api_response.get("success", False):
        return "Error", "API request failed"
    data = api_response.get("data", {})
    status = data.get("status", "unknown")
    response_text = status.replace("_", " ").title()
    status_lower = status.lower()
    if "successful" in status_lower:
        return "Approved", response_text
    if "frictionless" in status_lower or "failed" in status_lower:
        return "Declined", response_text
    return "Declined", response_text or "VBV Required"


async def check_vbv_api(card: str) -> dict:
    formatted = _format_vbv_card(card)
    if not formatted:
        return {"card": card, "Gateway": "3DS Lookup", "Response": "Invalid card format", "Status": "Error"}

    max_retries = 3
    last_error = None
    for attempt in range(max_retries):
        try:
            timeout = aiohttp.ClientTimeout(total=45)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                url = f"{VBV_API_URL}?key={VBV_API_KEY}&card={formatted}"
                async with session.get(url) as response:
                    if response.status != 200:
                        error_text = await response.text()
                        log.warning(f"VBV API attempt {attempt+1}/{max_retries} status {response.status}: {error_text[:200]}")
                        last_error = f"HTTP_{response.status}"
                        if attempt < max_retries - 1:
                            await asyncio.sleep(2 ** attempt)
                            continue
                        return {"card": card, "Gateway": "3DS Lookup", "Response": last_error, "Status": "Error"}
                    api_response = await response.json(content_type=None)
                    log.info(f"VBV API response for {card[:6]}******: {json.dumps(api_response)[:500]}")
                    if not api_response.get("success", False) and attempt < max_retries - 1:
                        log.warning(f"VBV API attempt {attempt+1}/{max_retries} returned success=false, retrying...")
                        await asyncio.sleep(2 ** attempt)
                        continue
            status, response_text = _parse_vbv_status(api_response)
            return {"card": card, "Gateway": "3DS Lookup", "Response": response_text, "Status": status}
        except asyncio.TimeoutError:
            log.warning(f"VBV API attempt {attempt+1}/{max_retries} timed out")
            last_error = "Timeout"
            if attempt < max_retries - 1:
                await asyncio.sleep(2 ** attempt)
                continue
            return {"card": card, "Gateway": "3DS Lookup", "Response": "Timeout", "Status": "Error"}
        except json.JSONDecodeError:
            log.warning(f"VBV API attempt {attempt+1}/{max_retries} invalid JSON")
            last_error = "Invalid JSON"
            if attempt < max_retries - 1:
                await asyncio.sleep(2 ** attempt)
                continue
            return {"card": card, "Gateway": "3DS Lookup", "Response": "Invalid JSON", "Status": "Error"}
        except Exception as e:
            log.error(f"VBV check error attempt {attempt+1}/{max_retries}: {e}")
            last_error = str(e)[:80]
            if attempt < max_retries - 1:
                await asyncio.sleep(2 ** attempt)
                continue
            return {"card": card, "Gateway": "3DS Lookup", "Response": last_error, "Status": "Error"}
    return {"card": card, "Gateway": "3DS Lookup", "Response": last_error or "Unknown error", "Status": "Error"}


def user_profile_url(uid, username=None) -> str:
    """Profile link: @username when set, otherwise tg://user?id= for users without a handle."""
    if username and str(username).strip() and not str(username).startswith("user_") and not str(username).isdigit():
        u = str(username).strip().lstrip("@")
        return f"https://t.me/{u}"
    if uid:
        return f"tg://user?id={int(uid)}"
    return DEV_LINK


async def get_user_link(uid):
    """Live Telegram name/username + clickable profile HTML."""
    name, username, _, _ = await get_user_info(uid)
    return user_link_html(uid, name, username), name, username


def user_link_html(uid, name, username=None) -> str:
    """Clickable HTML mention that opens the user's Telegram profile."""
    display = bs(str(name or "User"))
    return f'<a href="{user_profile_url(uid, username)}">{display}</a>'


async def get_user_info(uid):
    try:
        sender = await client_instance.get_entity(uid)
        username = getattr(sender, 'username', None)
        name = getattr(sender, 'first_name', None) or username or "User"
    except Exception:
        username, name = None, "User"
    prem = await is_premium_user(uid)
    tag = "Premium" if prem else "TRIAL"
    prof = user_profile_url(uid, username)
    return name, username, tag, prof


# ====================== SHOPIFY API ======================
def is_key_user_plan(plan) -> bool:
    return (plan or "").title() == "Custom"


def get_shopify_api_base(plan=None) -> str:
    if is_key_user_plan(plan):
        return next(_key_user_api_cycle)
    return API_BASE_URL


def _shopify_api_label(url: str, plan=None) -> str:
    if not is_key_user_plan(plan):
        return "MAIN"
    if KEY_USER_API_GO_URL in url:
        return "KEY_GO"
    if KEY_USER_API_ROTATING_URL in url:
        return "KEY_ROT"
    if KEY_USER_API_ROTATING_URL_2 in url:
        return "KEY_ROT2"
    return "KEY"


def _extract_proxy_parts(proxy_data):
    """Return (host, port, username, password, scheme) or None."""
    if not proxy_data:
        return None
    scheme = (proxy_data.get("type") or "http").lower()
    if scheme not in ("http", "https", "socks4", "socks5"):
        scheme = "http"
    proxy_url = proxy_data.get("proxy_url")
    if proxy_url:
        s = str(proxy_url).strip()
        sm = re.match(r"^(https?|socks[45])://", s, re.I)
        if sm:
            scheme = sm.group(1).lower()
        bare = re.sub(r"^(?:https?|socks[45])://", "", s, flags=re.I)
        am = re.match(r"^([^@:]+):([^@]+)@([^:]+):(\d+)$", bare)
        if am:
            u, pw, h, p = am.groups()
            return h, p, u, pw, scheme
        nm = re.match(r"^([^:@]+):(\d+)$", bare)
        if nm:
            h, p = nm.groups()
            return h, p, None, None, scheme
    host, port = proxy_data.get("ip"), proxy_data.get("port")
    if not host or not port:
        return None
    return host, port, proxy_data.get("username"), proxy_data.get("password"), scheme


def format_shopify_proxy_param(proxy_data=None, key_api=False):
    """Shopify API proxy query param.
    Main API: no-auth -> http://host:port; auth -> user:pass@host:port (no scheme).
    Go key-user API: always scheme://host:port or scheme://user:pass@host:port.
    """
    parts = _extract_proxy_parts(proxy_data)
    if not parts:
        return None
    host, port, username, password, scheme = parts
    if key_api:
        if username and password:
            return f"{scheme}://{username}:{password}@{host}:{port}"
        return f"{scheme}://{host}:{port}"
    if username and password:
        return f"{username}:{password}@{host}:{port}"
    return f"http://{host}:{port}"


def build_api_url(site, cc, proxy_data=None, plan=None):
    if not site.startswith('http'):
        site = f'https://{site}'
    base = get_shopify_api_base(plan)
    url = f'{base}?site={quote(site, safe="")}&cc={quote(cc, safe="")}'
    proxy_param = format_shopify_proxy_param(proxy_data, key_api=is_key_user_plan(plan))
    if proxy_param:
        url += f'&proxy={quote(proxy_param, safe="")}'
    return url


def _shopify_result_meta(rj):
    """Extract optional Shopify Go API fields (Proxy, Time, cc)."""
    meta = {}
    proxy_status = rj.get("Proxy", rj.get("proxy"))
    if proxy_status is not None and str(proxy_status).strip():
        meta["Proxy"] = str(proxy_status).strip()
    time_taken = rj.get("Time", rj.get("time"))
    if time_taken is not None and str(time_taken).strip():
        meta["Time"] = str(time_taken).strip()
    card_echo = rj.get("cc", rj.get("CC"))
    if card_echo is not None and str(card_echo).strip():
        meta["cc"] = str(card_echo).strip()
    currency = rj.get("Currency", rj.get("currency"))
    if currency is not None and str(currency).strip():
        meta["Currency"] = str(currency).strip()
    return meta


def _coerce_api_bool(val) -> bool:
    if isinstance(val, bool):
        return val
    if val is None:
        return False
    return str(val).strip().lower() in ("true", "1", "yes")


def classify_response(rj):
    ar = str(rj.get('Response', rj.get('response', '')) or '')
    if ar.upper() == 'DS_REQUIRED':
        ar = '3DS_REQUIRED'
    st = _coerce_api_bool(rj.get('Status', rj.get('status', False)))
    price = rj.get('Price', rj.get('price', '-'))
    gw = extract_gateway_from_api(rj)
    if price is not None and price != '-':
        price = _format_price_with_currency(price)
    meta = _shopify_result_meta(rj)
    proxy_status = meta.get("Proxy", "")
    if proxy_status and proxy_status.lower() in ("dead", "error", "failed", "timeout"):
        return {"Response": ar or f"Proxy {proxy_status}", "Price": price, "Gateway": gw, "Status": "SiteError", **meta}
    rl = ar.lower()
    if is_site_error(ar) or is_proxy_error(ar):
        return {"Response": ar, "Price": price, "Gateway": gw, "Status": "SiteError", **meta}
    ch = ['order_paid', 'order_placed', 'order confirmed', 'order_confirmed', 'thank you', 'payment successful', 'order completed', 'charged', 'order_created']
    if any(k in rl for k in ch):
        return {"Response": ar, "Price": price, "Gateway": gw, "Status": "Charged", **meta}
    ap = ['otp_required', 'otp required', '3d_authentication', '3ds_required', '3d required', '3d_redirect', 'authentication_required', 'insufficient_funds', 'insufficient funds', 'cvc', 'ccn', 'ccn live cvv']
    if any(k in rl for k in ap):
        return {"Response": ar, "Price": price, "Gateway": gw, "Status": "Approved", **meta}
    dc = ['generic_decline', 'generic decline', 'do_not_honor', 'do not honor', 'stolen_card', 'lost_card', 'pickup_card', 'pick_up_card', 'restricted_card', 'restricted card', 'fraudulent', 'fraud suspected', 'fraud_suspected', 'expired_card', 'expired card', 'transaction_not_allowed', 'transaction not allowed', 'card_declined', 'card declined', 'processor_declined', 'processor declined', 'card_not_supported', 'card not supported', 'currency_not_supported', 'duplicate_transaction', 'revocation_of_authorization', 'no_action_taken', 'try_again_later', 'not_permitted', 'decline', 'your card was declined', 'payment_intent_authentication_failure', 'avs_check_failed', 'incorrect number', 'incorrect_number', 'invalid', 'invalid_number', 'decision_rule_block', 'generic_error']
    if any(k in rl for k in dc):
        return {"Response": ar, "Price": price, "Gateway": gw, "Status": "Declined", **meta}
    if st is True and not any(w in rl for w in ["decline", "denied", "failed", "error", "rejected", "refused", "fraud"]):
        return {"Response": ar, "Price": price, "Gateway": gw, "Status": "Approved", **meta}
    return {"Response": ar, "Price": price, "Gateway": gw, "Status": "Declined", **meta}


SHOPIFY_PROXY_BLOCKED_KEYWORDS = [
    "tokenization blocked",
    "403 forbidden",
    "proxy/ip blocked",
    "proxy blocked",
    "ip blocked",
]


def is_shopify_proxy_blocked_response(text: str) -> bool:
    if not text:
        return False
    lower = str(text).lower()
    return any(kw in lower for kw in SHOPIFY_PROXY_BLOCKED_KEYWORDS)


def is_shopify_proxy_valid_response(response: str, price=None, proxy_field: str = "") -> bool:
    """True when Shopify API returned a real card result (proxy is usable)."""
    if not response or is_shopify_proxy_blocked_response(response):
        return False
    if proxy_field and str(proxy_field).strip().lower() in ("dead", "error", "failed", "timeout"):
        return False
    if is_proxy_error(response) or is_site_error(response):
        return False
    if not is_truly_alive(response, price):
        return False
    result = classify_response({"Response": response, "Price": price, "Status": False})
    return result.get("Status") in ("Declined", "Approved", "Charged")


async def test_shopify_proxy(proxy_data, site=None, max_site_retries=3, key_api=False):
    """Test a proxy against the Shopify API (main or Go key-user API)."""
    test_card = "5154623245618097|03|2032|156"
    sites = []
    if site:
        sites = [site]
    else:
        try:
            sites = list(await get_shopify_sites())
        except Exception:
            sites = []
    if not sites:
        return False, "No Shopify sites for proxy test"

    tried_sites = set()
    last_detail = "Invalid Shopify response"
    for _ in range(max(1, min(max_site_retries, len(sites)))):
        available = [s for s in sites if s not in tried_sites] or list(sites)
        test_site = random.choice(available)
        tried_sites.add(test_site)
        try:
            api_site = test_site if str(test_site).startswith("http") else f"https://{test_site}"
            test_plan = "Custom" if key_api else None
            url = build_api_url(api_site, test_card, proxy_data, plan=test_plan)
            s = await get_sp_session()
            async with s.get(url) as resp:
                if resp.status != 200:
                    last_detail = f"HTTP_{resp.status}"
                    continue
                try:
                    raw = await resp.json(content_type=None)
                except Exception:
                    last_detail = "Invalid JSON"
                    continue

            response = str(raw.get("Response", raw.get("response", "")) or "")
            price = raw.get("Price", raw.get("price", "-"))
            proxy_field = str(raw.get("Proxy", raw.get("proxy", "")) or "")

            if is_shopify_proxy_blocked_response(response):
                return False, response
            if proxy_field.lower() in ("dead", "error", "failed", "timeout"):
                return False, f"Proxy {proxy_field}"

            if is_shopify_proxy_valid_response(response, price, proxy_field):
                return True, response
            last_detail = response or last_detail
        except asyncio.TimeoutError:
            last_detail = "Timeout"
        except Exception as e:
            last_detail = str(e)[:80]

    return False, last_detail



async def _test_proxy_for_gate(proxy_data, gate: str):
    if gate == "shopify_key":
        return await test_shopify_proxy(proxy_data, key_api=True)
    if gate == "shopify":
        return await test_shopify_proxy(proxy_data, key_api=False)
    return await test_proxy(proxy_data["proxy_url"])


async def run_parallel_proxy_tests(proxy_list, gate: str, on_each_result, worker_count=PROXY_TEST_WORKERS, cancel_check=None):
    """Test proxies with concurrent asyncio workers; each slot starts the next proxy when free."""
    sem = asyncio.Semaphore(worker_count)
    result_lock = asyncio.Lock()

    async def worker(proxy_data):
        if cancel_check and cancel_check():
            return
        async with sem:
            if cancel_check and cancel_check():
                return
            try:
                res = await _test_proxy_for_gate(proxy_data, gate)
            except Exception as e:
                res = e
            async with result_lock:
                await on_each_result(proxy_data, res)

    await asyncio.gather(*[worker(p) for p in proxy_list], return_exceptions=True)


async def check_card_api(card, site, proxy_data=None, user_id=None, session_getter=None, plan=None):
    uid = user_id or "?"
    try:
        api_site = site if site.startswith('http') else f'https://{site}'
        url = build_api_url(api_site, card, proxy_data, plan=plan)
        getter = session_getter or get_sp_session
        s = await getter()
        api_label = _shopify_api_label(url, plan)
        log_user(uid, "API_REQ", f"Card={card} | Site={site} | API={api_label}")
        async with s.get(url) as r:
            if r.status != 200:
                log_user(uid, "API_HTTP_ERR", f"Card={card} | Site={site} | Status={r.status}", "warning")
                return {"Response": f"HTTP_{r.status}", "Price": "-", "Gateway": "Shopify Payments", "Status": "SiteError", "card": card, "site": site}
            try:
                rj = await r.json(content_type=None)
            except Exception:
                return {"Response": "Invalid JSON", "Price": "-", "Gateway": "Shopify Payments", "Status": "SiteError", "card": card, "site": site}
        log_user(uid, "API_RAW", f"Card={card} | Gateway={rj.get('Gateway', 'MISSING')} | Response={rj.get('Response', '')}")
        result = classify_response(rj)
        result["card"] = card
        result["site"] = site
        log_user(uid, "API_RESP", f"Card={card} | Status={result['Status']} | Gateway={result['Gateway']} | Response={result['Response']} | Price={result.get('Price', '-')}")
        return result
    except asyncio.TimeoutError:
        return {"Response": "Timeout", "Price": "-", "Gateway": "Shopify Payments", "Status": "SiteError", "card": card, "site": site}
    except Exception as e:
        err = str(e)
        st2 = "SiteError" if is_site_error(err) or is_proxy_error(err) else "Declined"
        return {"Response": err[:100], "Price": "-", "Gateway": "Shopify Payments", "Status": st2, "card": card, "site": site}


async def check_card_with_retry(card, sites, user_id=None, proxies_data=None, max_retries=3, rotator=None, cancel_check=None, session_getter=None, plan=None):
    if not sites:
        return {"Response": "No sites", "Price": "-", "Gateway": "-", "Status": "Error", "card": card}, -1
    tried_sites, tried_proxies, last = set(), set(), None
    for attempt in range(max_retries):
        if cancel_check and cancel_check():
            return {"Response": "Stopped", "Price": "-", "Gateway": "-", "Status": "Error", "card": card}, -1
        site = rotator.pick_site(sites, exclude=tried_sites) if rotator else random.choice([s for s in sites if s not in tried_sites] or list(sites))
        tried_sites.add(site)
        proxy_data = None
        if proxies_data:
            proxy_data = rotator.pick_proxy(proxies_data, exclude=tried_proxies) if rotator else random.choice([p for p in proxies_data if p.get('proxy_url') not in tried_proxies] or list(proxies_data))
            if proxy_data:
                tried_proxies.add(proxy_data.get('proxy_url'))
        result = await check_card_api(card, site, proxy_data, user_id, session_getter=session_getter, plan=plan)
        if result.get("Status") != "SiteError":
            if rotator:
                rotator.report_site_ok(site)
                if proxy_data:
                    rotator.report_proxy_ok(proxy_data.get('proxy_url'))
            return result, sites.index(site) + 1
        if rotator:
            rotator.report_site_fail(site)
            # Rotate proxy on any SiteError (e.g. stableId extract fail), not only proxy-keyword errors
            if proxy_data:
                rotator.report_proxy_fail(proxy_data.get('proxy_url'))
        last = result
        if attempt < max_retries - 1:
            backoff = min(0.1 * (2 ** attempt) + random.uniform(0, 0.1), 2.0)
            await asyncio.sleep(backoff)
    if last:
        last["Status"] = "Error"
        return last, -1
    return {"Response": "Max retries", "Price": "-", "Gateway": "-", "Status": "Error", "card": card}, -1


async def test_site(site, proxy_data=None):
    test_card = "5154623245618097|03|2032|156"
    try:
        api_site = site if site.startswith('http') else f'https://{site}'
        url = build_api_url(api_site, test_card, proxy_data)
        s = await get_site_session()
        async with s.get(url) as resp:
            if resp.status != 200:
                return {'site': site, 'status': 'dead', 'price': '-', 'response': f'HTTP_{resp.status}'}
            try:
                raw = await resp.json(content_type=None)
            except Exception:
                return {'site': site, 'status': 'dead', 'price': '-', 'response': 'Invalid JSON'}
        rm = str(raw.get('Response', '') or '')
        gw = extract_gateway_from_api(raw)
        price = raw.get('Price', '-')
        if price and price != '-':
            price = _format_price_with_currency(price)
        if is_site_error(rm.lower()):
            return {'site': site, 'status': 'dead', 'price': price, 'response': rm, 'gateway': gw}
        if has_restricted_gateway(rm, gw):
            # Mark dead so /add skips and /site removes Authorize.Net / ONERWAY Direct
            return {
                'site': site,
                'status': 'dead',
                'price': price,
                'response': f"RESTRICTED | {gw} | {rm}" if gw else f"RESTRICTED | {rm}",
                'gateway': gw,
            }
        if not is_truly_alive(rm, price):
            return {'site': site, 'status': 'dead', 'price': price, 'response': rm, 'gateway': gw}
        return {'site': site, 'status': 'alive', 'price': price, 'response': rm, 'gateway': gw}
    except Exception as e:
        return {'site': site, 'status': 'dead', 'price': '-', 'response': str(e)[:50]}



# ====================== UNIVERSAL MASS GATE CHECK ======================
async def _mass_gate_check(event, gate_name, gate_cmd, api_func, mass_sem, is_auth_gate=False, is_shopify=False):
    if await check_maintenance(event):
        return
    if await check_gate_maintenance(event, "mass"):
        return
    if await check_gate_maintenance(event, gate_cmd):
        return
    if not await force_join_check(event):
        return
    uid = event.sender_id
    cd = check_global_cooldown(uid, f"mass_{gate_cmd}", 3)
    if cd > 0 and uid not in ADMIN_ID:
        return await styled_reply(event, slowdown_wait_text(cd))
    _, at, plan = await get_user_access(event)
    if at == "banned":
        t, e = banned_user_message()
        return await styled_reply(event, t, emoji_ids=e)
    if uid not in ADMIN_ID and not is_paid_plan(plan):
        return await send_premium_only_message(event)
    if uid not in ADMIN_ID and not is_paid_plan(plan):
        credits = await get_user_credits(uid)
        if credits <= 0:
            return await styled_reply(event, f"""{bs('No Credits Left')} {PE}
{PE} {bs('Balance')} {ARROW} {bval(0)}""", buttons=[[pbtn(bs("Buy Credits"), url="{DEV_LINK}")]], emoji_ids=[CE["stop"], CE["chart"]])
    cl = get_cc_limit(plan, uid)
    for key, proc in list(ACTIVE_MTXT_PROCESSES.items()):
        if (
            isinstance(proc, dict)
            and proc.get("user_id") == uid
            and proc.get("gate_cmd") == gate_cmd
            and not proc.get("stopped", False)
            and not proc.get("done", False)
        ):
            return await styled_reply(event, f"""{PE} {bs('Already running')} ({bs(gate_name)})
{PE} <code>/stop {proc.get('session_id', '?')}</code>""", emoji_ids=[5042112436648281096, 5042112436648281096])
    content = ""
    cmd_text = re.sub(rf'^[/.]{gate_cmd}\s*', '', event.raw_text, flags=re.IGNORECASE).strip()
    if cmd_text:
        content = cmd_text
    elif event.reply_to_msg_id:
        rm = await event.get_reply_message()
        if not rm:
            return await styled_reply(event, f"{PE} {bs('Message not found')}", emoji_ids=[CE["warn"]])
        if rm.document:
            fp = await rm.download_media()
            try:
                async with aiofiles.open(fp, 'r', encoding='utf-8', errors='ignore') as f:
                    content = await f.read()
                os.remove(fp)
            except Exception:
                try:
                    os.remove(fp)
                except Exception:
                    pass
                return
        elif rm.text:
            content = rm.text
        else:
            return await styled_reply(event, f"{PE} {bs('No content found')}", emoji_ids=[CE["warn"]])
    else:
        return await styled_reply(event, f"{PE} {bs('Reply to .txt or text with')} <code>/{gate_cmd}</code>", emoji_ids=[CE["info"]])
    cards = extract_cc(content)
    if not cards:
        return await styled_reply(event, f"{PE} {bs('No valid cards')}", emoji_ids=[CE["cross"]])
    raw_total = len(cards)
    cards, removed = filter_valid_cards(cards)
    await reply_mass_card_filter_notice(event, removed, len(cards))
    if not cards:
        return
    if len(cards) > cl:
        cards = cards[:cl]
    session_id = generate_session_id()
    log_user(uid, f"{gate_cmd.upper()}_MASS_INIT", f"Cards={raw_total} | Removed={removed} | Using={len(cards)} | Session={session_id}")
    ACTIVE_MTXT_PROCESSES[session_id] = {
        "stopped": False,
        "done": False,
        "tasks": [],
        "user_id": uid,
        "session_id": session_id,
        "gate_cmd": gate_cmd,
        "gate_name": gate_name,
        "results": [],
    }
    user_sem = _get_user_mass_sem(uid, gate_cmd, plan)
    
    send_approved = is_auth_gate
    asyncio.create_task(_run_mass_process(event, cards, gate_name, gate_cmd, api_func, user_sem, session_id, is_auth_gate, is_shopify, send_approved))


async def _run_mass_process(event, cards, gate_name, gate_cmd, api_func, mass_sem, session_id, is_auth_gate, is_shopify, send_approved):
    uid = event.sender_id
    plan = await get_user_plan(uid)
    name, username, tag, prof = await get_user_info(uid)
    user_link = user_link_html(uid, name, username)
    proc_key = session_id
    total = len(cards)
    checked = charged = approved = declined = errors = 0
    st = time.time()
    hits = []
    rotator = SmartRotator() if is_shopify else None
    sites = None
    proxies = None
    worker_limit = get_mass_workers(plan, gate_cmd, uid)

    proc = ACTIVE_MTXT_PROCESSES.get(proc_key)
    if isinstance(proc, dict):
        proc["gate_name"] = gate_name
        proc["gate_cmd"] = gate_cmd
        proc["name"] = name
        proc["username"] = username
        proc["total"] = total

    if is_shopify:
        owner_sites, owner_proxies = await get_owner_check_resources(plan=plan)
        sites = owner_sites
        proxies = owner_proxies
        if not sites:
            ACTIVE_MTXT_PROCESSES.pop(proc_key, None)
            return await reply_no_sites(event)
        if not proxies:
            ACTIVE_MTXT_PROCESSES.pop(proc_key, None)
            return await reply_no_proxy(event, gate=shopify_proxy_gate_for_plan(plan))
    log_user(uid, f"{gate_cmd.upper()}_MASS_START", f"Cards={total} | Session={session_id}")
    sm = await styled_reply(event, format_mass_progress(gate_name, "CHECKING", 0, total, 0, 0, 0, 0, "0s", session_id, user_link=user_link), buttons=make_mass_buttons(0, 0, 0, 0, session_id=session_id, is_done=False, errors=0), emoji_ids=get_mass_progress_emojis("CHECKING"))

    def is_stopped():
        p = ACTIVE_MTXT_PROCESSES.get(proc_key)
        if not p:
            return True
        return p.get("stopped", False) if isinstance(p, dict) else False

    _ui_lock = asyncio.Lock()
    _last_ui_update = 0

    async def _update_ui_batch(force=False):
        nonlocal checked, approved, charged, declined, errors, _last_ui_update
        if not force:
            if time.time() - _last_ui_update < 5.0:
                return
        async with _ui_lock:
            _last_ui_update = time.time()
            elapsed = format_elapsed(time.time() - st)
            try:
                await styled_edit(sm, format_mass_progress(gate_name, "CHECKING", checked, total, approved, charged, declined, errors, elapsed, session_id, user_link=user_link), buttons=make_mass_buttons(approved, charged, declined, checked, session_id=session_id, is_done=False, errors=errors), emoji_ids=get_mass_progress_emojis("CHECKING"))
            except Exception as e:
                log_system("STYLED_EDIT_ERR", f"Error={repr(e)}", "error")

    local_session = None
    if is_shopify:
        local_session = aiohttp.ClientSession(
            timeout=aiohttp.ClientTimeout(total=API_TIMEOUT, connect=10),
            connector=aiohttp.TCPConnector(
                limit=250,
                limit_per_host=250,
                ttl_dns_cache=300,
                use_dns_cache=True,
                enable_cleanup_closed=True,
                force_close=False
            )
        )

    async def get_local_session():
        return local_session

    async def worker(card):
        nonlocal checked, charged, approved, declined, errors
        if is_stopped():
            return
        async with mass_sem:
            if is_stopped():
                return
            try:
                if is_shopify:
                    result, _ = await check_card_with_retry(card, sites, uid, proxies, 3, rotator, cancel_check=is_stopped, session_getter=get_local_session, plan=plan)
                else:
                    result = await api_func(card, uid)
                if is_stopped():
                    return
                status = result.get("Status", "Declined")
                resp = result.get("Response", "")
                gw = result.get("Gateway", gate_name)
                price = result.get("Price", "-")
                checked += 1
                await _record_gate_result(gate_cmd, status not in ["SiteError", "Error"])
                if uid not in ADMIN_ID and not is_paid_plan(plan):
                    await deduct_credit(uid, 1)

                bi = result.get("bin_info") or await get_bin_info(card.split("|")[0])
                p = ACTIVE_MTXT_PROCESSES.get(proc_key)
                if isinstance(p, dict):
                    p.setdefault("results", []).append({
                        "card": card,
                        "status": status,
                        "response": resp,
                        "gateway": gw,
                        "bin_info": bi,
                    })

                log_user(uid, f"{gate_cmd.upper()}_MASS_CARD", f"Card={card} | Status={status} | Gateway={gw} | {checked}/{total}")
                if status in ["SiteError", "Error"]:
                    errors += 1
                elif status == "Charged":
                    charged += 1
                    hits.append(f"{card} - CHARGED - {resp} - {gw}")
                    fire_and_forget(track_user_stats(uid, "CHARGED"))
                    fire_and_forget(_send_mass_hit(card, result, status, uid, name, tag, prof, gate_name, is_auth_gate, gw, is_shopify))
                elif status == "Approved":
                    approved += 1
                    hits.append(f"{card} - APPROVED - {resp} - {gw}")
                    fire_and_forget(track_user_stats(uid, "APPROVED"))
                    if send_approved or is_auth_gate:
                        fire_and_forget(_send_mass_hit(card, result, status, uid, name, tag, prof, gate_name, is_auth_gate, gw, is_shopify))
                else:
                    declined += 1
                    fire_and_forget(track_user_stats(uid, "DECLINED"))
                limit = worker_limit
                if checked % limit == 0 or checked == total:
                    fire_and_forget(_update_ui_batch(force=(checked == total)))
            except asyncio.CancelledError:
                return
            except Exception as e:
                if not is_stopped():
                    errors += 1
                    checked += 1
                    log_user(uid, f"{gate_cmd.upper()}_MASS_ERR", f"Card={card} | Error={e}", "error")
                    limit = worker_limit
                    if checked % limit == 0 or checked == total:
                        fire_and_forget(_update_ui_batch(force=(checked == total)))

    try:
        tasks = [asyncio.create_task(worker(c)) for c in cards]
        p = ACTIVE_MTXT_PROCESSES.get(proc_key)
        if isinstance(p, dict):
            p["tasks"] = tasks
        try:
            await asyncio.gather(*tasks, return_exceptions=True)
        except Exception:
            pass
        await asyncio.sleep(0.3)
        elapsed = format_elapsed(time.time() - st)
        status_label = "STOPPED" if is_stopped() else "FINISHED"
        p = ACTIVE_MTXT_PROCESSES.get(proc_key)
        if isinstance(p, dict):
            p["done"] = True
            p["stopped"] = is_stopped()
        log_user(uid, f"{gate_cmd.upper()}_MASS_DONE", f"Charged={charged} | Approved={approved} | Declined={declined} | Errors={errors} | {checked}/{total} | {elapsed}")
        for _ in range(3):
            try:
                await styled_edit(sm, format_mass_progress(gate_name, status_label, checked, total, approved, charged, declined, errors, elapsed, session_id, user_link=user_link), buttons=make_mass_buttons(approved, charged, declined, checked, session_id=session_id, is_done=True, errors=errors), emoji_ids=get_mass_progress_emojis(status_label))
                break
            except Exception:
                await asyncio.sleep(0.5)
    finally:
        _cleanup_user_mass_sem(uid, gate_cmd, plan)
        if local_session:
            await local_session.close()


_USER_DM_LOCKS = {}
_CHANNEL_HIT_LOCK = asyncio.Lock()

def get_user_dm_lock(uid):
    if uid not in _USER_DM_LOCKS:
        _USER_DM_LOCKS[uid] = asyncio.Lock()
    return _USER_DM_LOCKS[uid]


async def _send_charged_to_channel(status, gw, resp, name, prof, tag):
    """Send Charged hit to HIT_CHANNEL only (no DM). Used by /sp, /sh."""
    if status != "Charged":
        return
    try:
        status_emoji = get_status_emoji_id(status)
        ch_msg, ch_emoji_ids = format_channel_hit(
            status, gw, (resp or "")[:150], name, prof, tag,
            price=None, status_emoji_id=status_emoji,
        )
        async with _CHANNEL_HIT_LOCK:
            try:
                await styled_send(
                    HIT_CHANNEL_ID,
                    ch_msg,
                    buttons=get_hit_button(status, is_channel=True),
                    emoji_ids=ch_emoji_ids,
                )
                await asyncio.sleep(2.5)
            except Exception:
                pass
    except Exception:
        pass


async def _send_mass_hit(card, result, status, uid, name, tag, prof, gate_name, is_auth_gate, gw, is_shopify=False):
    await asyncio.sleep(HIT_DELAY)
    try:
        resp = result.get('Response', '')[:150]
        if is_auth_gate and 'succeeded' not in resp.lower():
            return
        bi = await get_bin_info(card.split("|")[0])
        price = result.get('Price', '-')
        
        # Append price to Shopify Payments gateway if it exists
        if is_shopify and price and price != "-":
            gw = f"{gw} {price}"
            
        proxy_status = result.get("Proxy") if is_shopify else None
        emoji_ids = [get_status_emoji_id(status), 5447453226498552490, get_random_dev_emoji(), 6233303538676541503]
        if proxy_status:
            emoji_ids.append(4958610528588008305)
            
        dm_msg = format_mass_hit_dm(status, card, gw, resp, bi, name, prof, tag, proxy_status=proxy_status)
        
        # Send DM using user-specific lock
        async with get_user_dm_lock(uid):
            try:
                gif_url = await fetch_anime_gif()
                await styled_send(uid, dm_msg, buttons=get_hit_button(status), emoji_ids=emoji_ids, file=gif_url)
                await asyncio.sleep(2.5)  # Spacing out DMs to the user to avoid rate limits
            except Exception:
                pass
                
        send_to_channel = False
        if is_auth_gate and status == "Approved":
            send_to_channel = True
        elif not is_auth_gate and status == "Charged":
            send_to_channel = True
        if send_to_channel:
            status_emoji = get_status_emoji_id(status)
            ch_msg, ch_emoji_ids = format_channel_hit(status, gw, resp, name, prof, tag, price=None, status_emoji_id=status_emoji)
            # Send to channel using channel-specific lock
            async with _CHANNEL_HIT_LOCK:
                try:
                    await styled_send(HIT_CHANNEL_ID, ch_msg, buttons=get_hit_button(status, is_channel=True), emoji_ids=ch_emoji_ids)
                    await asyncio.sleep(2.5)  # Spacing out public channel hits to avoid rate limits
                except Exception:
                    pass
    except Exception:
        pass


# ====================== BIN COMMAND ======================
@client.on(events.NewMessage(pattern=r'(?i)^[/.]bin\b'))
async def bin_cmd(event):
    if await check_maintenance(event):
        return
    if not await force_join_check(event):
        return
    _, at = await can_use(event.sender_id, event.chat, event=event)
    if at == "banned":
        t, e = banned_user_message()
        return await styled_reply(event, t, emoji_ids=e)

    rt = re.sub(r'^[/.]bin\s*', '', event.raw_text, flags=re.IGNORECASE).strip()
    if not rt and event.is_reply:
        rm = await event.get_reply_message()
        if rm and rm.text:
            rt = rm.text
    if not rt:
        return await styled_reply(event, f"""{bs('BIN Lookup')} {PE}
{PE} <code>/bin 424242</code>
{PE} <code>/bin 4242424242424242</code>""", emoji_ids=[CE["search"], CE["info"]])

    bin_digits = re.sub(r'\D', '', rt)
    if len(bin_digits) < 6:
        cards = extract_cc(rt)
        if cards:
            bin_digits = re.sub(r'\D', '', cards[0].split('|')[0])

    lm = await styled_reply(event, f"{bs('Looking up BIN')}... ⏳")
    result = await lookup_bin(bin_digits)

    try:
        await lm.delete()
    except Exception:
        pass

    if result.get("error"):
        return await styled_reply(event, f"{PE} {bs(result['error'])}", emoji_ids=[CE["cross"]])

    country_emoji = result.get("country_emoji") or "🏳️"
    bin_text = build_panel_ui(
        f"{bs('BIN Lookup')} {PE}",
        [
            f"{PE} {bs('BIN')} {ARROW} {bval(result.get('bin', '-'))}",
            f"{PE} {bs('Scheme')} {ARROW} {bval(result.get('scheme', '-'))}",
            f"{PE} {bs('Type')} {ARROW} {bval(result.get('type', '-'))}",
            f"{PE} {bs('Brand')} {ARROW} {bval(result.get('brand', '-'))}",
            f"{PE} {bs('Bank')} {ARROW} {bval(result.get('bank', '-'))}",
            f"{PE} {bs('Country')} {ARROW} {country_emoji} {bval(result.get('country', '-'))}",
        ],
    )
    await styled_reply(event, bin_text, emoji_ids=[CE["search"], CE["info"], CE["globe"], CE["chart"], CE["gem"], CE["link"]])


# ====================== VBV COMMAND ======================
@client.on(events.NewMessage(pattern=r'(?i)^[/.]vbv\b'))
async def vbv_cmd(event):
    if await check_maintenance(event):
        return
    if await check_gate_maintenance(event, "vbv"):
        return
    if not await force_join_check(event):
        return
    uid = event.sender_id
    cd = check_global_cooldown(uid, "vbv", 2)
    if cd > 0 and uid not in ADMIN_ID:
        return await styled_reply(event, slowdown_wait_text(cd))
    _, at = await can_use(uid, event.chat)
    if at == "banned":
        t, e = banned_user_message()
        return await styled_reply(event, t, emoji_ids=e)
    plan = await get_user_plan(uid)
    is_group = event.chat.id != uid
    if uid not in ADMIN_ID and not is_paid_plan(plan):
        credits = await get_user_credits(uid)
        if credits <= 0:
            return await styled_reply(event, f"""{bs('No Credits Left')} {PE}
{PE} {bs('Balance')} {ARROW} {bval(0)}""", buttons=[[pbtn(bs("Buy Credits"), url="{DEV_LINK}")]], emoji_ids=[CE["stop"], CE["chart"]])
    if uid not in ADMIN_ID and not is_paid_plan(plan):
        if not is_group:
            return await send_group_only_message(event)
        if plan == FREE_PLAN and uid in _VBV_LAST_USE:
            elapsed = time.time() - _VBV_LAST_USE[uid]
            if elapsed < 10:
                remaining = 10 - int(elapsed)
                return await styled_reply(event, slowdown_wait_text(remaining))
        cd2 = get_free_gate_cooldown(uid, "vbv")
        if cd2 > 0:
            return await styled_reply(event, slowdown_wait_text(cd2))

    card = None
    if event.reply_to_msg_id:
        rm = await event.get_reply_message()
        if rm and rm.text:
            cc = extract_cc(rm.text)
            if cc:
                card = cc[0]
    if not card:
        cc = extract_cc(event.message.text)
        if cc:
            card = cc[0]
    if not card:
        return await styled_reply(event, f"{PE} <code>/vbv card|mm|yy|cvv</code>", emoji_ids=[CE["info"]])

    ok, reason = validate_card(card)
    if not ok:
        return await reply_invalid_card(event, reason)

    name, username, tag, prof = await get_user_info(uid)
    if uid not in ADMIN_ID and not is_paid_plan(plan):
        set_free_gate_last_use(uid, "vbv")
        if plan == FREE_PLAN:
            _VBV_LAST_USE[uid] = time.time()

    log_user(uid, "VBV_START", f"Card={card}")
    lm = await styled_reply(event, f"{bs('Processing')}… ⏳")
    try:
        async with _VBV_SEM:
            bin_task = asyncio.create_task(get_bin_info(card.split('|')[0]))
            result = await check_vbv_api(card)
            bi = await bin_task
        status = result.get('Status', 'Declined')
        gw = result.get('Gateway', '3DS Lookup')
        await _record_gate_result("vbv", status not in ["Error"])
        if uid not in ADMIN_ID and not is_paid_plan(plan) and status != "Error":
            await deduct_credit(uid, 1)
        msg = format_single_result(status, card, gw, result.get('Response', '')[:150], bi, name, prof, tag)
        await lm.delete()
        gif_url = await fetch_anime_gif()
        await styled_reply(event, msg, buttons=get_hit_button(status), emoji_ids=[get_status_emoji_id(status), 5447453226498552490, get_random_dev_emoji(), 6233303538676541503], file=gif_url)
    except Exception as e:
        await lm.delete()
        await styled_reply(event, f"{PE} {bs('Error')} {ARROW} <code>{e}</code>", emoji_ids=[CE["cross"]])


# ====================== FEEDBACK COMMAND ======================
_FB_ALBUM_WAIT_S = 1.5
_FB_ALBUM_ID_WINDOW = 15
_FB_MAX_MEDIA = 10


def _feedback_media_from_message(msg):
    if not msg or not msg.media:
        return None
    if msg.photo or msg.video or msg.gif or msg.sticker:
        return msg.media
    if msg.document:
        mime = (getattr(msg.document, "mime_type", "") or "").lower()
        if mime.startswith("image/") or mime.startswith("video/") or "gif" in mime:
            return msg.media
        for attr in getattr(msg.document, "attributes", None) or []:
            if isinstance(attr, (DocumentAttributeVideo, DocumentAttributeAnimated)):
                return msg.media
    if isinstance(msg.media, (MessageMediaPhoto, MessageMediaDocument)):
        return msg.media
    return None


def _feedback_album_bucket(media):
    """Telegram albums: photos together OR videos together (not mixed)."""
    if isinstance(media, MessageMediaPhoto):
        return "photo"
    if isinstance(media, MessageMediaDocument):
        doc = media.document
        if doc:
            mime = (doc.mime_type or "").lower()
            for attr in doc.attributes or []:
                if isinstance(attr, DocumentAttributeVideo):
                    return "video"
            if mime.startswith("video/"):
                return "video"
        return "photo"
    return "photo"


async def _collect_album_media(chat_id, grouped_id, center_id, wait_s=_FB_ALBUM_WAIT_S):
    await asyncio.sleep(wait_s)
    lo = max(1, center_id - _FB_ALBUM_ID_WINDOW)
    hi = center_id + _FB_ALBUM_ID_WINDOW
    try:
        messages = await client.get_messages(chat_id, ids=list(range(lo, hi + 1)))
    except Exception:
        messages = []
    items = []
    for msg in messages:
        if not msg or msg.grouped_id != grouped_id:
            continue
        med = _feedback_media_from_message(msg)
        if med:
            items.append((msg.id, med))
    items.sort(key=lambda x: x[0])
    return [m for _, m in items]


async def _gather_feedback_media(event):
    """Collect photo/video/gif media from /fb message, reply, or album."""
    media_items = []
    seen_ids = set()

    def _add_message(msg):
        if not msg or msg.id in seen_ids:
            return
        med = _feedback_media_from_message(msg)
        if med:
            seen_ids.add(msg.id)
            media_items.append(med)

    _add_message(event)

    if event.reply_to_msg_id:
        rm = await event.get_reply_message()
        if rm:
            if rm.grouped_id:
                for med in await _collect_album_media(event.chat_id, rm.grouped_id, rm.id):
                    media_items.append(med)
            else:
                _add_message(rm)

    if event.grouped_id:
        for med in await _collect_album_media(event.chat_id, event.grouped_id, event.id):
            media_items.append(med)

    unique = []
    seen_media = set()
    for med in media_items:
        key = id(med)
        if key in seen_media:
            continue
        seen_media.add(key)
        unique.append(med)
    return unique[:_FB_MAX_MEDIA]


async def _send_feedback_media(chat_id, media_items, caption, buttons=None):
    """Send multiple pics/videos/gifs; splits into Telegram-compatible albums (max 10 each)."""
    if not media_items:
        return await styled_send(chat_id, caption, buttons=buttons)

    if len(media_items) == 1:
        return await styled_send(chat_id, caption, buttons=buttons, file=media_items[0])

    photo_batch, video_batch = [], []
    for med in media_items[:_FB_MAX_MEDIA]:
        if _feedback_album_bucket(med) == "video":
            video_batch.append(med)
        else:
            photo_batch.append(med)

    last_msg = None
    caption_used = False

    async def _send_batch(batch):
        nonlocal last_msg, caption_used
        for i in range(0, len(batch), 10):
            chunk = batch[i:i + 10]
            cap = caption if not caption_used else None
            try:
                if len(chunk) == 1:
                    last_msg = await styled_send(chat_id, cap or " ", buttons=None, file=chunk[0])
                else:
                    text, entities = build_entities(cap, emoji_ids=None) if cap else ("", [])
                    last_msg = await client.send_file(
                        chat_id,
                        file=chunk,
                        caption=text if cap else None,
                        formatting_entities=entities if cap else None,
                    )
                if cap:
                    caption_used = True
            except Exception:
                for j, one in enumerate(chunk):
                    try:
                        use_cap = caption if not caption_used and j == 0 and i == 0 else None
                        last_msg = await styled_send(chat_id, use_cap or " ", buttons=None, file=one)
                        if use_cap:
                            caption_used = True
                    except Exception:
                        pass

    await _send_batch(photo_batch)
    await _send_batch(video_batch)

    if caption and not caption_used:
        last_msg = await styled_send(chat_id, caption, buttons=None)

    # Telegram albums often drop inline buttons — send them on a follow-up message.
    if buttons:
        btn_msg = await styled_send(chat_id, f"{PE} {bs(BOT_NAME)}", buttons=buttons)
        return btn_msg or last_msg
    return last_msg


@client.on(events.NewMessage(pattern=r'(?i)^[/.]fb\b'))
async def feedback_cmd(event):
    if await check_maintenance(event):
        return
    if not await force_join_check(event):
        return
    uid = event.sender_id
    cd = check_global_cooldown(uid, "fb", 5)
    if cd > 0 and uid not in ADMIN_ID:
        return await styled_reply(event, slowdown_wait_text(cd))

    comment = re.sub(r'^[/.]fb\s*', '', event.raw_text, flags=re.IGNORECASE).strip()
    media_items = await _gather_feedback_media(event)

    if not media_items:
        return await styled_reply(event, f"""{bs('Feedback')}
{UI_SEP}
{bs('Usage')} {ARROW} {bs('Send')} /fb {bs('with your feedback Or reply to a hit message with')} /fb""")

    media_type = f"{len(media_items)} media" if len(media_items) > 1 else "photo"

    name, username, tag, prof = await get_user_info(uid)
    feedback_text = f"""{bs('FEEDBACK')} 💎
{bs('USER')} {ARROW} {user_link_html(uid, name, username)}
{bs('USER ID')} {ARROW} <code>{uid}</code>"""
    if comment:
        feedback_text += f"\n{UI_SEP}\n{html.escape(comment)}"

    buy_kb = [[pbtn(bs("Buy Now"), url=f"{BOT_LINK.rstrip('/')}?start=buy", color="blue")]]
    submitted_ui = f"""{UI_SEP}
{bs('Feedback Submitted')} {PE}
{UI_SEP}"""
    submitted_emoji = [5436196151575459790]

    try:
        if uid in ADMIN_ID:
            await _send_feedback_media(HITS_CHANNEL_ID, media_items, feedback_text, buttons=buy_kb)
            fire_and_forget(save_feedback(uid, name, event.id, event.chat_id, media_type))
            log_user(uid, "FEEDBACK", f"Type={media_type} | Items={len(media_items)} | Owner direct to Hits")
            await styled_reply(event, submitted_ui, emoji_ids=submitted_emoji)
            return

        # Users: owner must Approve / Decline first
        fb_id = uuid.uuid4().hex[:10]
        approve_kb = [[
            pbtn(bs("Approve"), f"fb_ap:{fb_id}", color="green"),
            pbtn(bs("Decline"), f"fb_de:{fb_id}", color="red"),
        ]]
        owner_msgs = []
        for admin_id in ADMIN_ID:
            try:
                if len(media_items) == 1:
                    om = await styled_send(admin_id, feedback_text, buttons=approve_kb, file=media_items[0])
                else:
                    await _send_feedback_media(admin_id, media_items, feedback_text, buttons=None)
                    om = await styled_send(
                        admin_id,
                        f"💎 {bs('Action Required:')}",
                        buttons=approve_kb,
                        emoji_ids=[4958610528588008305],
                    )
                if om is not None:
                    if isinstance(om, list):
                        owner_msgs.extend(om)
                    else:
                        owner_msgs.append(om)
            except Exception as e:
                log_user(uid, "FEEDBACK_OWNER_DM_ERR", f"Admin={admin_id} Error={e}", "error")

        if not owner_msgs:
            return await styled_reply(event, f"{PE} {bs('Could not reach owner. Try again.')}", emoji_ids=[CE["cross"]])

        _PENDING_FEEDBACK[fb_id] = {
            "uid": uid,
            "name": name,
            "prof": prof,
            "caption": feedback_text,
            "media": media_items[0],
            "media_list": media_items,
            "media_type": media_type,
            "comment": comment,
            "src_chat_id": event.chat_id,
            "src_msg_id": event.id,
            "owner_msgs": owner_msgs,
            "status": "pending",
        }
        log_user(uid, "FEEDBACK_PENDING", f"Id={fb_id} | Type={media_type} | Items={len(media_items)} | Owners={len(owner_msgs)}")
        await styled_reply(event, submitted_ui, emoji_ids=submitted_emoji)
    except Exception as e:
        log_user(uid, "FEEDBACK_ERR", f"Error={e}", "error")
        await styled_reply(event, f"{PE} {bs('Error')} {ARROW} <code>{e}</code>", emoji_ids=[CE["cross"]])


async def _fb_delete_owner_dms(pending):
    """Remove approval messages from owner DMs only (Hits channel untouched)."""
    for msg in pending.get("owner_msgs") or []:
        try:
            await msg.delete()
        except Exception:
            try:
                await client_instance.delete_messages(msg.chat_id, [msg.id])
            except Exception:
                pass
    pending["owner_msgs"] = []


@client.on(events.CallbackQuery(pattern=rb"fb_ap:(.+)"))
async def fb_approve_cb(event):
    if event.sender_id not in ADMIN_ID:
        return await event.answer(f"{bs('Not allowed')}", alert=True)
    fb_id = event.pattern_match.group(1).decode()
    pending = _PENDING_FEEDBACK.get(fb_id)
    if not pending or pending.get("status") != "pending":
        return await event.answer(f"{bs('Already handled.')}", alert=True)
    pending["status"] = "approved"
    caption = pending.get("caption") or f"{bs('FEEDBACK')}"
    media = pending.get("media")
    media_list = pending.get("media_list") or ([media] if media else [])
    buy_kb = [[pbtn(bs("Buy Now"), url=f"{BOT_LINK.rstrip('/')}?start=buy", color="blue")]]
    try:
        if media_list:
            await _send_feedback_media(HITS_CHANNEL_ID, media_list, caption, buttons=buy_kb)
        else:
            await styled_send(HITS_CHANNEL_ID, caption, buttons=buy_kb)
        fire_and_forget(save_feedback(
            pending.get("uid"),
            pending.get("name") or "User",
            pending.get("src_msg_id") or 0,
            pending.get("src_chat_id") or 0,
            pending.get("media_type") or "unknown",
        ))
        log_user(pending.get("uid") or event.sender_id, "FEEDBACK_APPROVED", f"Id={fb_id} | By={event.sender_id}")
    except Exception as e:
        pending["status"] = "pending"
        log_system("FEEDBACK_APPROVE_ERR", f"Id={fb_id} Error={e}", "error")
        return await event.answer(f"{bs('Failed to post')}", alert=True)
    await _fb_delete_owner_dms(pending)
    _PENDING_FEEDBACK.pop(fb_id, None)
    await event.answer(f"{bs('Approved')} ✓")


@client.on(events.CallbackQuery(pattern=rb"fb_de:(.+)"))
async def fb_decline_cb(event):
    if event.sender_id not in ADMIN_ID:
        return await event.answer(f"{bs('Not allowed')}", alert=True)
    fb_id = event.pattern_match.group(1).decode()
    pending = _PENDING_FEEDBACK.get(fb_id)
    if not pending or pending.get("status") != "pending":
        return await event.answer(f"{bs('Already handled.')}", alert=True)
    pending["status"] = "declined"
    log_user(pending.get("uid") or event.sender_id, "FEEDBACK_DECLINED", f"Id={fb_id} | By={event.sender_id}")
    await _fb_delete_owner_dms(pending)
    _PENDING_FEEDBACK.pop(fb_id, None)
    await event.answer(f"{bs('Declined')}")


@client.on(events.CallbackQuery(pattern=rb"fb_done:(.+)"))
async def fb_done_cb(event):
    await event.answer(f"{bs('Already handled')}")


# ====================== SINGLE COMMANDS ======================
@client.on(events.NewMessage(pattern=r'(?i)^[/.]sp\b'))
async def sp_single(event):
    if await check_maintenance(event):
        return
    if await check_gate_maintenance(event, "sp"):
        return
    if not await force_join_check(event):
        return
    uid = event.sender_id
    cd = check_global_cooldown(uid, "sp", 2)
    if cd > 0 and uid not in ADMIN_ID:
        return await styled_reply(event, slowdown_wait_text(cd))
    _, at = await can_use(uid, event.chat)
    if at == "banned":
        t, e = banned_user_message()
        return await styled_reply(event, t, emoji_ids=e)
    plan = await get_user_plan(uid)
    is_group = event.chat.id != uid
    if uid not in ADMIN_ID and not is_paid_plan(plan):
        credits = await get_user_credits(uid)
        if credits <= 0:
            return await styled_reply(event, f"""{bs('No Credits Left')} {PE}
{PE} {bs('Balance')} {ARROW} {bval(0)}""", buttons=[[pbtn(bs("Buy Credits"), url="{DEV_LINK}")]], emoji_ids=[CE["stop"], CE["chart"]])
    if uid not in ADMIN_ID and not is_paid_plan(plan):
        if not is_group:
            return await send_group_only_message(event)
        cd2 = get_free_sp_cooldown_remaining(uid)
        if cd2 > 0:
            return await styled_reply(event, slowdown_wait_text(cd2))
    name, username, tag, prof = await get_user_info(uid)
    sites, proxies = await get_owner_check_resources(plan=plan)
    if not sites:
        return await styled_reply(event, f"""{PE} {bs('No shared sites available')}
{PE} {bs('Please try again later')}""", emoji_ids=[CE["warn"], CE["info"]])
    if not proxies:
        return await reply_no_proxy(event, gate=shopify_proxy_gate_for_plan(plan))
    card = None
    if event.reply_to_msg_id:
        rm = await event.get_reply_message()
        if rm and rm.text:
            cc = extract_cc(rm.text)
            if cc:
                card = cc[0]
    if not card:
        cc = extract_cc(event.message.text)
        if cc:
            card = cc[0]
    if not card:
        return await styled_reply(event, f"{PE} <code>/sp card|mm|yy|cvv</code>", emoji_ids=[CE["info"]])

    ok, reason = validate_card(card)
    if not ok:
        return await reply_invalid_card(event, reason)

    if uid not in ADMIN_ID and not is_paid_plan(plan):
        set_free_sp_last_use(uid)
    log_user(uid, "SP_START", f"Card={card} | Sites={len(sites)}")
    lm = await styled_reply(event, f"{bs('Processing')}… ⏳")
    try:
        async with _SP_SEM:
            bin_task = asyncio.create_task(get_bin_info(card.split('|')[0]))
            # Shared rotator → consecutive /sp checks rotate sites; SiteError also rotates within the check
            result, _ = await check_card_with_retry(card, sites, uid, proxies, 3, _SP_ROTATOR, session_getter=get_sp_session, plan=plan)
            bi = await bin_task
        status = result.get('Status', 'Declined')
        gw = result.get('Gateway', 'Shopify Payments')
        price = result.get('Price', '-')
        await _record_gate_result("sp", status not in ["Error", "SiteError"])
        if uid not in ADMIN_ID and not is_paid_plan(plan):
            await deduct_credit(uid, 1)
        
        # Append price to Shopify Payments gateway if it exists
        if price and price != "-":
            gw = f"{gw} {price}"
            
        if status in ["Charged", "Approved", "Declined"]:
            fire_and_forget(track_user_stats(uid, status.upper()))
            
        proxy_status = result.get("Proxy")
        emoji_ids = [get_status_emoji_id(status), 5447453226498552490, get_random_dev_emoji(), 6233303538676541503]
        if proxy_status:
            emoji_ids.append(4958610528588008305)
        msg = format_single_result(status, card, gw, result.get('Response', '')[:150], bi, name, prof, tag, proxy_status=proxy_status)
        await lm.delete()
        gif_url = await fetch_anime_gif()
        await styled_reply(event, msg, buttons=get_hit_button(status), emoji_ids=emoji_ids, file=gif_url)
        if status == "Charged":
            fire_and_forget(_send_charged_to_channel(status, gw, result.get('Response', ''), name, prof, tag))
    except Exception as e:
        await lm.delete()
        await styled_reply(event, f"{PE} {bs('Error')} {ARROW} <code>{e}</code>", emoji_ids=[CE["cross"]])


async def _run_sh_process(event, cards, session_id, sites, proxies, uid, plan, name, tag="TRIAL", prof="#"):
    proc_key = session_id
    session = ACTIVE_SH_SESSIONS.get(proc_key)
    if not session:
        return
    sm = session["msg"]
    rotator = SmartRotator()
    total = len(cards)

    try:
        for card in cards:
            if session.get("stopped"):
                break
            try:
                async with _SP_SEM:
                    bin_task = asyncio.create_task(get_bin_info(card.split("|")[0]))
                    result, _ = await check_card_with_retry(
                        card, sites, uid, proxies, 3, rotator, session_getter=get_sp_session
                    )
                    bi = await bin_task
                status = result.get("Status", "Declined")
                resp = result.get("Response", "")
                gw = result.get("Gateway", "Shopify Payments")
                price = result.get("Price", "-")
                await _record_gate_result("sp", status not in ["Error", "SiteError"])
                if uid not in ADMIN_ID and not is_paid_plan(plan):
                    await deduct_credit(uid, 1)
                if price and price != "-":
                    gw = f"{gw} {price}"
                if status in ["Charged", "Approved", "Declined"]:
                    fire_and_forget(track_user_stats(uid, status.upper()))
                if status == "Charged":
                    fire_and_forget(_send_charged_to_channel(status, gw, resp, name, prof, tag))
                log_user(uid, "SH_CARD", f"Card={card} | Status={status} | {len(session['results']) + 1}/{total}")
                session["results"].append({
                    "card": card,
                    "status": status,
                    "response": resp,
                    "gateway": gw,
                    "bin_info": bi,
                })
                await _edit_sh_message(sm, session, force_latest=True)
            except Exception as e:
                log_user(uid, "SH_CARD_ERR", f"Card={card} | Error={e}", "error")
                session["results"].append({
                    "card": card,
                    "status": "Error",
                    "response": str(e)[:120],
                    "gateway": "Shopify Payments",
                    "bin_info": await get_bin_info(card.split("|")[0]),
                })
                await _edit_sh_message(sm, session, force_latest=True)

        session["done"] = True
        await _edit_sh_message(sm, session, force_latest=True)
        log_user(uid, "SH_DONE", f"Cards={len(session['results'])}/{total} | Session={session_id}")
    except Exception as e:
        log_user(uid, "SH_FAIL", f"Error={e}", "error")
        session["done"] = True
        try:
            await styled_edit(sm, f"{PE} {bs('Error')} {ARROW} <code>{html.escape(str(e)[:120])}</code>", emoji_ids=[CE["cross"]])
        except Exception:
            pass


def _cleanup_sh_sessions(uid):
    for sid, proc in list(ACTIVE_SH_SESSIONS.items()):
        if proc.get("user_id") == uid:
            ACTIVE_SH_SESSIONS.pop(sid, None)


@client.on(events.NewMessage(pattern=r'(?i)^[/.]sh\b'))
async def sh_mass(event):
    if await check_maintenance(event):
        return
    if await check_gate_maintenance(event, "sp"):
        return
    if not await force_join_check(event):
        return
    uid = event.sender_id
    cd = check_global_cooldown(uid, "sh", 3)
    if cd > 0 and uid not in ADMIN_ID:
        return await styled_reply(event, slowdown_wait_text(cd))
    _, at = await can_use(uid, event.chat)
    if at == "banned":
        t, e = banned_user_message()
        return await styled_reply(event, t, emoji_ids=e)
    plan = await get_user_plan(uid)
    is_group = event.chat.id != uid
    if uid not in ADMIN_ID and not is_paid_plan(plan):
        credits = await get_user_credits(uid)
        if credits <= 0:
            return await styled_reply(event, f"""{bs('No Credits Left')} {PE}
{PE} {bs('Balance')} {ARROW} {bval(0)}""", buttons=[[pbtn(bs("Buy Credits"), url="{DEV_LINK}")]], emoji_ids=[CE["stop"], CE["chart"]])
    if uid not in ADMIN_ID and not is_paid_plan(plan):
        if not is_group:
            return await send_group_only_message(event)
        cd2 = get_free_sp_cooldown_remaining(uid)
        if cd2 > 0:
            return await styled_reply(event, slowdown_wait_text(cd2))
    for proc in ACTIVE_SH_SESSIONS.values():
        if proc.get("user_id") == uid and not proc.get("done"):
            return await styled_reply(event, f"{PE} {bs('Already running')} <code>/sh</code>", emoji_ids=[CE["warn"]])
    _cleanup_sh_sessions(uid)

    content = ""
    cmd_text = re.sub(r'^[/.]sh\s*', '', event.raw_text, flags=re.IGNORECASE).strip()
    if cmd_text:
        content = cmd_text
    elif event.reply_to_msg_id:
        rm = await event.get_reply_message()
        if not rm:
            return await styled_reply(event, f"{PE} {bs('Message not found')}", emoji_ids=[CE["warn"]])
        if rm.document:
            fp = await rm.download_media()
            try:
                async with aiofiles.open(fp, "r", encoding="utf-8", errors="ignore") as f:
                    content = await f.read()
            finally:
                try:
                    os.remove(fp)
                except Exception:
                    pass
        elif rm.text:
            content = rm.text
        else:
            return await styled_reply(event, f"{PE} {bs('No content found')}", emoji_ids=[CE["warn"]])
    else:
        return await styled_reply(event, f"{PE} {bs('Reply to .txt or text with')} <code>/sh</code>", emoji_ids=[CE["info"]])

    cards = extract_cc(content)
    if not cards:
        return await styled_reply(event, f"{PE} {bs('No valid cards')}", emoji_ids=[CE["cross"]])

    cards, removed = filter_valid_cards(cards)
    await reply_mass_card_filter_notice(event, removed, len(cards))
    if not cards:
        return

    if len(cards) > SH_MAX_CARDS:
        cards = cards[:SH_MAX_CARDS]

    sites, proxies = await get_owner_check_resources(plan=plan)
    if not sites:
        return await styled_reply(event, f"""{PE} {bs('No shared sites available')}
{PE} {bs('Please try again later')}""", emoji_ids=[CE["warn"], CE["info"]])
    if not proxies:
        return await reply_no_proxy(event, gate=shopify_proxy_gate_for_plan(plan))

    if uid not in ADMIN_ID and not is_paid_plan(plan):
        set_free_sp_last_use(uid)

    name, username, tag, prof = await get_user_info(uid)
    session_id = generate_session_id()
    start_session = {
        "session_id": session_id,
        "user_id": uid,
        "total": len(cards),
        "results": [],
        "start": time.time(),
        "name": name,
        "username": username,
        "view_page": 0,
        "done": False,
        "stopped": False,
    }
    init_text, init_emoji = format_sh_message(start_session, 0)
    sm = await styled_reply(event, init_text, emoji_ids=init_emoji or None)
    start_session["msg"] = sm
    ACTIVE_SH_SESSIONS[session_id] = start_session
    log_user(uid, "SH_START", f"Cards={len(cards)} | Session={session_id}")
    asyncio.create_task(_run_sh_process(event, cards, session_id, sites, proxies, uid, plan, name, tag, prof))


@client.on(events.CallbackQuery(pattern=rb"^sh_page:([^:]+):(\d+)$"))
async def sh_page_cb(event):
    await event.answer()
    try:
        session_id = event.pattern_match.group(1).decode()
        page_index = int(event.pattern_match.group(2).decode())
        session = ACTIVE_SH_SESSIONS.get(session_id)
        if not session:
            session = await get_sh_session(session_id)
            if session:
                ACTIVE_SH_SESSIONS[session_id] = session
        if not session:
            return
        await _edit_sh_message(await event.get_message(), session, page_index=page_index)
    except Exception as e:
        log_system("SH_PAGE_ERR", str(e), "error")


@client.on(events.CallbackQuery(pattern=rb"^sh_nop:.+$"))
async def sh_nop_cb(event):
    await event.answer()



# ====================== MASS COMMANDS ======================
@client.on(events.NewMessage(pattern=r'(?i)^[/.]msp\b'))
async def msp_mass(event):
    await _mass_gate_check(event, "Shopify", "msp", None, None, is_auth_gate=False, is_shopify=True)




# ====================== /stop ======================
@client.on(events.NewMessage(pattern=r'(?i)^[/.]stop\b'))
async def stop_cmd(event):
    uid = event.sender_id
    parts = event.raw_text.split()
    if len(parts) >= 2:
        session_id = parts[1].upper()
        proc = ACTIVE_MTXT_PROCESSES.get(session_id) or ACTIVE_SH_SESSIONS.get(session_id)
        if not proc:
            return await styled_reply(event, f"{PE} {bs('No session')} {ARROW} <code>{session_id}</code>", emoji_ids=[5042112436648281096])
        if isinstance(proc, dict) and proc.get("user_id") != uid and uid not in ADMIN_ID:
            return await styled_reply(event, f"{PE} {bs('Not your session!')}", emoji_ids=[5042112436648281096])
        if isinstance(proc, dict):
            proc["stopped"] = True
            proc["done"] = True
            for task in proc.get("tasks", []):
                if not task.done():
                    task.cancel()
        log_user(uid, "STOP_CMD", f"Session={session_id}")
        stop_msg = await styled_reply(event, f"{PE} {bs('Stopping')} <code>{session_id}</code>", emoji_ids=[5042112436648281096])
        await asyncio.sleep(2)
        try:
            await stop_msg.delete()
        except Exception:
            pass
        return
    user_sessions = []
    for key, proc in list(ACTIVE_MTXT_PROCESSES.items()) + list(ACTIVE_SH_SESSIONS.items()):
        if isinstance(proc, dict) and proc.get("user_id") == uid and not proc.get("stopped", False) and not proc.get("done", False):
            sid = proc.get("session_id", key)
            if sid not in user_sessions:
                user_sessions.append(sid)
    if not user_sessions:
        return await styled_reply(event, f"{PE} {bs('No active sessions')}", emoji_ids=[5042112436648281096])
    lines = "\n".join(f"{PE} <code>/stop {sid}</code>" for sid in user_sessions)
    await styled_reply(event, f"{PE} {bs('Your Active Sessions:')}\n{lines}", emoji_ids=[5042112436648281096] * (len(user_sessions) + 1))


@client.on(events.CallbackQuery(pattern=rb"^stop_mass:(.+)"))
async def stop_mass_cb(event):
    session_id = event.pattern_match.group(1).decode().upper()
    proc = ACTIVE_MTXT_PROCESSES.get(session_id) or ACTIVE_SH_SESSIONS.get(session_id)
    if not proc:
        return await event.answer("Session expired or not found", alert=True)
    if isinstance(proc, dict) and proc.get("user_id") != event.sender_id and event.sender_id not in ADMIN_ID:
        return await event.answer("Not your session!", alert=True)
    if isinstance(proc, dict):
        proc["stopped"] = True
        proc["done"] = True
        for task in proc.get("tasks", []):
            if not task.done():
                task.cancel()
    await event.answer("Stopped!", alert=True)


@client.on(events.CallbackQuery(pattern=rb"^mass_file:(approved|dead|all):(.+)"))
async def mass_file_cb(event):
    file_type = event.pattern_match.group(1).decode().lower()
    session_id = event.pattern_match.group(2).decode()

    proc = ACTIVE_MTXT_PROCESSES.get(session_id) or ACTIVE_SH_SESSIONS.get(session_id)

    if not proc:
        return await event.answer("Session expired or not found!", alert=True)

    is_finished = proc.get("done") or proc.get("stopped")
    if not is_finished and len(proc.get("results", [])) == 0:
        return await event.answer("Please wait for the checking to complete!", alert=True)

    gate_name = proc.get("gate_name") or "Shopify"
    results = proc.get("results") or []

    filtered_results = []
    if file_type == "approved":
        filtered_results = [r for r in results if r.get("status") == "Approved"]
    elif file_type == "dead":
        filtered_results = [r for r in results if r.get("status") not in ("Charged", "Approved")]
    else:
        filtered_results = list(results)

    total_count = len(filtered_results)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    file_type_upper = file_type.upper()
    filename = f"NOTHING_{file_type_upper}_{ts}.txt"

    header_text = f"Gate {PLAIN_ARROW} {gate_name} Mass\nResult {PLAIN_ARROW} {file_type.title()}\nTotal {PLAIN_ARROW} {total_count}\n" + UI_SEP + "\n"

    file_lines = [header_text]
    for r in filtered_results:
        card = r.get("card", "-")
        st = r.get("status", "DECLINED").upper()
        gw = r.get("gateway", f"{gate_name} Payments")
        resp = r.get("response", "ORDER_PLACED")
        bi = r.get("bin_info") or {"brand": "-", "bank": "-", "country": "-", "flag": "🇺🇸"}
        uname = proc.get("name") or "User"
        user_tag = "Premium"

        card_block = f"""Status {PLAIN_ARROW} {st}
Card {PLAIN_ARROW} {card}
Gate {PLAIN_ARROW} {gw}
Response {PLAIN_ARROW} {resp}
Brand {PLAIN_ARROW} {bi.get('brand', '-')}
Issuer {PLAIN_ARROW} {bi.get('bank', 'None')}
Country {PLAIN_ARROW} {bi.get('flag', '🇺🇸')} {bi.get('country', 'UNITED STATES')}
User {PLAIN_ARROW} {uname} ({user_tag})
Dev {PLAIN_ARROW} {DEV_NAME}
""" + UI_SEP + "\n"
        file_lines.append(card_block)

    file_content = "".join(file_lines)

    async with aiofiles.open(filename, "w", encoding="utf-8") as f:
        await f.write(file_content)

    if file_type == "dead":
        res_emoji = 4918014360267260850
    else:
        res_emoji = 5282843764451195532

    caption = f"""{bs('Gate')} {ARROW} {bs(gate_name)} {bs('Mass')}
{bs('Result')} {ARROW} {bs(file_type.title())} {PE}
{bs('Total')} {ARROW} {bval(total_count)}"""

    try:
        await styled_send(event.sender_id, caption, file=filename, emoji_ids=[res_emoji])
        await event.answer()
    except Exception as e:
        log_system("MASS_FILE_SEND_ERR", f"Error={e}", "error")
        await event.answer("Failed to send file.", alert=True)
    finally:
        try:
            os.remove(filename)
        except Exception:
            pass


# ====================== /cmds ======================

_CMDS_PAGES_PUBLIC = [
    ("Gates", [
        ("Shopify", "/sp", "Free"),
        ("Shopify Live", "/sh", "Free"),
        ("VBV Lookup", "/vbv", "Free"),
        ("Feedback", "/fb", "Free"),
    ]),
    ("Mass Gates", [
        ("Mass Shopify", "/msp", "Premium"),
        ("Stop Check", "/stop", "Premium"),
    ]),
    ("Tools", [
        ("BIN Lookup", "/bin", "Free"),
        ("User Info", "/info", "Free"),
        ("Redeem Key", "/redeem", "Free"),
        ("Hits", "/hits", "Free"),
        ("Feedback 24h", "/f", "Free"),
        ("Feedback All", "/feed", "Free"),
        ("Pricing", "/plan", "Free"),
        ("Commands", "/cmds", "Free"),
    ]),
]

_CMDS_PAGES_OWNER = [
    ("Gates", [
        ("Shopify", "/sp", "Free"),
        ("Shopify Live", "/sh", "Free"),
        ("VBV Lookup", "/vbv", "Free"),
        ("Feedback", "/fb", "Free"),
    ]),
    ("Mass Gates", [
        ("Mass Shopify", "/msp", "Premium"),
        ("Stop Check", "/stop", "Premium"),
    ]),
    ("Sites", [
        ("Add Site", "/add", "Owner"),
        ("Remove Site", "/rm", "Owner"),
        ("My Sites", "/sites", "Owner"),
        ("Check Site", "/site", "Owner"),
    ]),
    ("Proxy", [
        ("Add Proxy", "/addpxy", "Owner"),
        ("My Proxy", "/proxy", "Owner"),
        ("Remove Proxy", "/rmpxy", "Owner"),
        ("Check Proxy", "/chkpxy", "Owner"),
    ]),
    ("Keys", [
        ("Generate Keys", "/keys", "Owner"),
        ("Assign Key", "/key", "Owner"),
        ("Remaining Keys", "/rem", "Owner"),
        ("Revoke Key Plan", "/rkey [user_id] or /rkey all", "Owner"),
        ("Redeem Key", "/redeem", "Free"),
    ]),
    ("Tools", [
        ("BIN Lookup", "/bin", "Free"),
        ("User Info", "/info", "Free"),
        ("Hits", "/hits", "Free"),
        ("Feedback 24h", "/f", "Free"),
        ("Feedback All", "/feed", "Free"),
        ("Pricing", "/plan", "Free"),
        ("Commands", "/cmds", "Free"),
    ]),
]


def get_cmds_pages(uid=None):
    if uid is not None and is_owner(uid):
        return _CMDS_PAGES_OWNER
    return _CMDS_PAGES_PUBLIC


def build_cmds_page_text(page_index: int, uid=None) -> str:
    try:
        pages = get_cmds_pages(uid)
        category, commands = pages[page_index]
        total_pages = len(pages)
        title_line = f"{bs(category)} \u00b7 {bs(f'{page_index + 1} / {total_pages}')}"
        lines = [title_line, _ui_rule(title_line)]
        for name, cmd, ctype in commands:
            block_lines = [
                f"{bs('Gate')} {ARROW} {bs(name)}",
                f"{bs('Cmd')} {ARROW} <code>{html.escape(cmd)}</code>",
                f"{bs('Type')} {ARROW} {bs(ctype)}",
            ]
            lines.extend(block_lines)
            lines.append(_ui_rule(*block_lines))
        return "\n".join(lines)
    except Exception as e:
        log_system("CMDS_BUILD_ERR", str(e), "error")
        return f"{bs('Error')} {ARROW} {bs('Could not build commands page.')}"


def build_cmds_buttons(page_index: int, uid=None):
    total = len(get_cmds_pages(uid))
    nav = []
    if page_index > 0:
        nav.append(pbtn(f"« {bs('Prev')}", f"page_{page_index - 1}", color="blue"))
    nav.append(pbtn(bs(f"{page_index + 1} / {total}"), "cmds_nop"))
    if page_index < total - 1:
        nav.append(pbtn(f"{bs('Next')} »", f"page_{page_index + 1}", color="blue"))
    return [nav]


@client.on(events.NewMessage(pattern=r'(?i)^[/.](cmds?|commands?)$'))
async def cmds_cmd(event):
    try:
        await ensure_user(event.sender_id)
        log_user(event.sender_id, "CMDS", f"ChatID={event.chat_id}")
        if not await force_join_check(event):
            return
        _, at = await can_use(event.sender_id, event.chat)
        if at == "banned":
            t, e = banned_user_message()
            return await styled_reply(event, t, emoji_ids=e)
        text, entities = build_entities(build_cmds_page_text(0, event.sender_id))
        await event.reply(text, formatting_entities=entities, buttons=build_cmds_buttons(0, event.sender_id), link_preview=False)
    except Exception as e:
        log_user(event.sender_id, "CMDS_ERROR", f"Error={e}", "error")


@client.on(events.CallbackQuery(pattern=rb"^page_(\d+)$"))
async def cmds_page_cb(event):
    await event.answer()
    try:
        page_index = int(event.pattern_match.group(1).decode())
        pages = get_cmds_pages(event.sender_id)
        if page_index < 0 or page_index >= len(pages):
            return
        text, entities = build_entities(build_cmds_page_text(page_index, event.sender_id))
        await event.edit(text, formatting_entities=entities, buttons=build_cmds_buttons(page_index, event.sender_id), link_preview=False)
    except Exception as e:
        if "not modified" not in str(e).lower():
            log_system("CMDS_PAGE_ERR", str(e), "error")


@client.on(events.CallbackQuery(data=b"cmds_nop"))
async def cmds_nop_cb(event):
    await event.answer()


@client.on(events.CallbackQuery(data=b"cmds_close"))
async def cmds_close_cb(event):
    await event.answer()
    try:
        await event.delete()
    except Exception:
        pass


# ====================== /me ======================
@client.on(events.NewMessage(pattern=r'(?i)^[/.]me$'))
async def me_stats(event):
    uid = event.sender_id
    await ensure_user(uid)
    if not await force_join_check(event):
        return
    _, at = await can_use(uid, event.chat)
    if at == "banned":
        t, e = banned_user_message()
        return await styled_reply(event, t, emoji_ids=e)
    
    try:
        checked, charged, approved, declined = await get_user_stats(uid)
    except Exception:
        checked, charged, approved, declined = 0, 0, 0, 0
        
    text = f"""{bs('Your Stats')} {PE}
{UI_SEP}
{PE} {bs('Total Checked')} {ARROW} {bval(f'{checked:,}')}
{PE} {bs('Total Charged')} {ARROW} {bval(f'{charged:,}')}
{PE} {bs('Total Approved')} {ARROW} {bval(f'{approved:,}')}
{PE} {bs('Total Declined')} {ARROW} {bval(f'{declined:,}')}
{UI_SEP}
🛠️ {bs('Dev')} {ARROW} <a href='{DEV_LINK}'>{bs(DEV_NAME)}</a>"""
    try:
        charged_emoji = random.choice(CHARGED_EMOJIS)
        await styled_reply(event, text, emoji_ids=[5956561749070057536, 5257969839313526622, charged_emoji, 4958610528588008305, 4956612582816351459])
    except Exception as e:
        log_system("ME_CMD_ERR", f"User={uid} Error={e}", "error")


# ====================== /start ======================
@client.on(events.NewMessage(pattern=r'(?i)^[/.]start\b'))
async def start(event):
    try:
        if await check_maintenance(event):
            return
        name, username, tag, prof = await get_user_info(event.sender_id)
        start_payload = parse_start_payload(event.raw_text).lower()
        referrer_id = None
        if start_payload.startswith("ref_"):
            try:
                referrer_id = int(start_payload[4:])
            except ValueError:
                referrer_id = None
        existed = await user_exists(event.sender_id)
        await ensure_user(event.sender_id, name=name, username=username)
        if referrer_id and not existed:
            await register_pending_referral(event.sender_id, referrer_id)
        log_user(event.sender_id, "START", f"ChatID={event.chat_id}")
        if not await force_join_check(event):
            return
        _, at = await can_use(event.sender_id, event.chat)
        if at == "banned":
            t, e = banned_user_message()
            return await styled_reply(event, t, emoji_ids=e)
        plan = await get_user_plan(event.sender_id)
        credits = await get_user_credits(event.sender_id)
        credits_display = "Unlimited" if is_paid_plan(plan) or event.sender_id in ADMIN_ID else str(credits)
        joined_dt = await get_user_joined_date(event.sender_id)
        joined_str = joined_dt.strftime("%Y-%m-%d") if joined_dt else "Unknown"
        caption = build_start_caption(event.sender_id, name, username, plan, credits_display, joined_str)
        kb = build_start_kb(event.sender_id)

        if start_payload in ("buy", "plan", "plans", "show_plans"):
            text, emoji_ids, kb = format_plan_message()
            return await styled_reply(event, text, buttons=kb, emoji_ids=emoji_ids)

        if start_payload in ("ref", "referral"):
            ref_count = await get_verified_referral_count(event.sender_id)
            text = build_referral_caption(event.sender_id, ref_count)
            return await styled_reply(
                event, text, buttons=build_referral_kb(event.sender_id), emoji_ids=get_referral_emoji_ids(),
            )

        await styled_reply(event, caption, buttons=kb, noforwards=True, emoji_ids=get_start_emoji_ids())
        if start_payload == "msp" and is_paid_plan(plan):
            tip = f"{PE} {bs('Tip:')} <code>/{start_payload}</code> {bs('— reply to a .txt to start mass check')}"
            await styled_reply(event, tip, emoji_ids=[4902715076873553054])
    except Exception as e:
        log_user(event.sender_id, "START_ERROR", f"Error={e}", "error")


async def _show_referral_ui(event, edit=False):
    uid = event.sender_id
    ref_count = await get_verified_referral_count(uid)
    text = build_referral_caption(uid, ref_count)
    kb = build_referral_kb(uid)
    emoji_ids = get_referral_emoji_ids()
    if edit:
        await styled_edit(await event.get_message(), text, buttons=kb, emoji_ids=emoji_ids)
    else:
        await styled_reply(event, text, buttons=kb, emoji_ids=emoji_ids)


@client.on(events.NewMessage(pattern=r'(?i)^[/.]ref(?:erral)?$'))
async def ref_cmd(event):
    try:
        if await check_maintenance(event):
            return
        if not await force_join_check(event):
            return
        _, at = await can_use(event.sender_id, event.chat)
        if at == "banned":
            t, e = banned_user_message()
            return await styled_reply(event, t, emoji_ids=e)
        await ensure_user(event.sender_id)
        await _show_referral_ui(event)
    except Exception as e:
        log_user(event.sender_id, "REF_ERROR", f"Error={e}", "error")


@client.on(events.CallbackQuery(data=b"rx_referral"))
async def rx_referral_cb(event):
    await event.answer()
    try:
        await _show_referral_ui(event, edit=True)
    except Exception:
        await _show_referral_ui(event, edit=False)


_GATE_BACK_MAP = {
    "sp": "auth", "vbv": "auth",
    "msp": "mass", }


def _checker_menu_caption():
    return f"""{bs('Gates Status:')}
{bs('Gates')} {ARROW} {bval(2)} {PE}
{bs('Mass Gates')} {ARROW} {bval(1)} {PE}
{UI_SEP}
{bs('Select a Gate Category')}"""


def _checker_menu_kb():
    return [
        [pbtn(bs("Gates"), "rx_auth", color="blue"), pbtn(bs("Mass"), "rx_mass", color="blue")],
        [pbtn(f"« {bs('Back')}", "rx_back:main", color="red")],
    ]


CHECKER_MENU_EMOJI_IDS = [5220046725493828505, 5220046725493828505]


@client.on(events.CallbackQuery(data=b"rx_checker"))
async def rx_checker_cb(event):
    await event.answer()
    caption = _checker_menu_caption()
    kb = _checker_menu_kb()
    text, entities = build_entities(caption, emoji_ids=CHECKER_MENU_EMOJI_IDS)
    try:
        await event.edit(text, formatting_entities=entities, buttons=kb)
    except Exception:
        pass


@client.on(events.CallbackQuery(data=b"rx_auth"))
async def rx_auth_cb(event):
    await event.answer()
    caption = f"""{bs('Select Gate')}
\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501"""
    kb = [
        [pbtn(bs("Shopify"), "rx_gate:sp", color="blue")],
        [pbtn(bs("VBV Lookup"), "rx_gate:vbv", color="blue")],
        [pbtn(f"« {bs('Back')}", "rx_back:checker", color="red")]
    ]
    text, entities = build_entities(caption)
    try:
        await event.edit(text, formatting_entities=entities, buttons=kb)
    except Exception:
        pass


@client.on(events.CallbackQuery(data=b"rx_mass"))
async def rx_mass_cb(event):
    await event.answer()
    caption = f"""{bs('Select Mass Method')}
\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501"""
    kb = [
        [pbtn(bs("Shopify"), "rx_gate:msp", color="blue")],
        [pbtn(f"« {bs('Back')}", "rx_back:checker", color="red")]
    ]
    text, entities = build_entities(caption)
    try:
        await event.edit(text, formatting_entities=entities, buttons=kb)
    except Exception:
        pass


_GATE_INFO = {
    "sp": ("Shopify", "/sp card|mm|yy|cvv", "Charge", "\U0001F6D2"),
    "vbv": ("VBV Lookup", "/vbv card|mm|yy|cvv", "3DS", "🔐"),
    "msp": ("Shopify Mass", "/msp (reply to .txt)", "Mass", "\U0001F6D2"),
}


@client.on(events.CallbackQuery(pattern=rb"rx_gate:(.+)"))
async def rx_gate_cb(event):
    gate = event.pattern_match.group(1).decode()
    await event.answer()
    info = _GATE_INFO.get(gate)
    if not info:
        return
    name, cmd, gtype, emoji = info
    back_to = _GATE_BACK_MAP.get(gate, "checker")
    caption = f"""{bs('Gate')} {ARROW} {bs(name)}
{bs('Command')} {ARROW} <code>{cmd}</code>
{bs('Type')} {ARROW} {bs(gtype)}
{bs('Gate Health')} {ARROW} {bval(await _get_gate_health(gate))}
\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501"""
    kb = [[pbtn(f"« {bs('Back')}", f"rx_back:{back_to}", color="red")]]
    text, entities = build_entities(caption)
    try:
        await event.edit(text, formatting_entities=entities, buttons=kb)
    except Exception:
        pass


@client.on(events.CallbackQuery(pattern=rb"rx_back:(.+)"))
async def rx_back_cb(event):
    target = event.pattern_match.group(1).decode()
    await event.answer()
    if target == "main":
        uid = event.sender_id
        plan = await get_user_plan(uid)
        name, username, tag, prof = await get_user_info(uid)
        credits = await get_user_credits(uid)
        credits_display = "Unlimited" if is_paid_plan(plan) or uid in ADMIN_ID else str(credits)
        joined_dt = await get_user_joined_date(uid)
        joined_str = joined_dt.strftime("%Y-%m-%d") if joined_dt else "Unknown"
        caption = build_start_caption(uid, name, username, plan, credits_display, joined_str)
        kb = build_start_kb(uid)
        text, entities = build_entities(caption, emoji_ids=get_start_emoji_ids())
        try:
            await event.edit(text, formatting_entities=entities, buttons=kb)
        except Exception:
            pass
    elif target == "plan_menu":
        caption, emoji_ids, kb = format_plan_message()
        text, entities = build_entities(caption, emoji_ids=emoji_ids)
        try:
            await event.edit(text, formatting_entities=entities, buttons=kb)
        except Exception:
            pass
    elif target == "checker":
        caption = _checker_menu_caption()
        kb = _checker_menu_kb()
        text, entities = build_entities(caption, emoji_ids=CHECKER_MENU_EMOJI_IDS)
        try:
            await event.edit(text, formatting_entities=entities, buttons=kb)
        except Exception:
            pass
    elif target == "auth":
        caption = f"""{bs('Select Gate')}
\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501"""
        kb = [
            [pbtn(bs("Shopify"), "rx_gate:sp", color="blue")],
            [pbtn(bs("VBV Lookup"), "rx_gate:vbv", color="blue")],
            [pbtn(f"« {bs('Back')}", "rx_back:checker", color="red")]
        ]
        text, entities = build_entities(caption)
        try:
            await event.edit(text, formatting_entities=entities, buttons=kb)
        except Exception:
            pass
    elif target == "mass":
        caption = f"""{bs('Select Mass Method')}
\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501"""
        kb = [
            [pbtn(bs("Shopify"), "rx_gate:msp", color="blue")],
            [pbtn(f"« {bs('Back')}", "rx_back:checker", color="red")]
        ]
        text, entities = build_entities(caption)
        try:
            await event.edit(text, formatting_entities=entities, buttons=kb)
        except Exception:
            pass


# ====================== CRYPTO PAYMENT SYSTEM (/plan & /buy) ======================

# Paste your Binance API credentials here (Read permission only).
BINANCE_API_KEY = ""
BINANCE_API_SECRET = ""
# Railway/US IPs get Binance 451. Use EU/Asia HTTP proxy: http://user:pass@host:port
BINANCE_API_PROXY = ""

# net_key -> (coin, binance_network_code)
BINANCE_DEPOSIT_NETWORKS = {
    "bep20": ("USDT", "BSC"),
    "trc20": ("USDT", "TRX"),
    "ltc": ("LTC", "LTC"),
    "btc": ("BTC", "BTC"),
    "sol": ("SOL", "SOL"),
}

BUY_PAYMENT_WINDOW_SEC = 1800


async def _binance_signed_get(path: str, extra_params: dict = None):
    if not BINANCE_API_KEY or not BINANCE_API_SECRET:
        return None
    proxy = BINANCE_API_PROXY.strip() or None
    try:
        timeout = aiohttp.ClientTimeout(total=15)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            timestamp = await _binance_server_time_ms(session, proxy)
            params = {"timestamp": timestamp, "recvWindow": 60000}
            if extra_params:
                params.update(extra_params)
            query_string = urlencode(params)
            signature = hmac.new(
                BINANCE_API_SECRET.encode("utf-8"),
                query_string.encode("utf-8"),
                hashlib.sha256,
            ).hexdigest()
            params["signature"] = signature
            url = f"https://api.binance.com{path}?{urlencode(params)}"
            async with session.get(
                url,
                headers={"X-MBX-APIKEY": BINANCE_API_KEY},
                proxy=proxy,
            ) as resp:
                data = await resp.json(content_type=None)
                if resp.status == 200:
                    return data
                log_system("BINANCE_API_ERR", f"{path} | Status={resp.status} Body={data}", "warning")
    except Exception as e:
        log_system("BINANCE_API_ERR", f"{path} | {e}", "error")
    return None


async def _binance_server_time_ms(session, proxy=None):
    async with session.get("", proxy=proxy) as resp:
        data = await resp.json(content_type=None)
        return int(data["serverTime"])


async def fetch_binance_deposit_address(coin: str, network: str, label: str):
    """Fetch live deposit address from Binance."""
    if not BINANCE_API_KEY or not BINANCE_API_SECRET:
        log_system("BINANCE_ADDR_ERR", "Missing API key or secret", "warning")
        return None
    log_system("BINANCE_ADDR_FETCH", f"Requesting {label} | Coin={coin} | Network={network}")
    data = await _binance_signed_get(
        "",
        {"coin": coin, "network": network},
    )
    if isinstance(data, dict) and data.get("address"):
        addr = str(data["address"]).strip()
        tag = data.get("tag") or data.get("memo") or ""
        extra = f" | Tag={tag}" if tag else ""
        log_system("BINANCE_ADDR_OK", f"Fetched {label} | Address={addr}{extra} | Network={data.get('network', network)}")
        return addr
    log_system("BINANCE_ADDR_ERR", f"{label} | No address in response: {data}", "warning")
    return None


async def fetch_binance_deposit_history(coin: str, network: str, start_time_ms: int):
    data = await _binance_signed_get(
        "",
        {"coin": coin, "startTime": start_time_ms, "limit": 100},
    )
    if not isinstance(data, list):
        return []
    return [item for item in data if str(item.get("network", "")).upper() == network.upper()]


def _exact_payment_amount_match(received, expected) -> bool:
    return round(float(received), 8) == round(float(expected), 8)


async def check_binance_payment(net_key: str, target_amount, within_seconds: int = BUY_PAYMENT_WINDOW_SEC):
    dep = BINANCE_DEPOSIT_NETWORKS.get(net_key)
    if not dep:
        return False, None
    coin, network = dep
    start_ms = int((time.time() - within_seconds) * 1000)
    deposits = await fetch_binance_deposit_history(coin, network, start_ms)
    for item in deposits:
        if int(item.get("status", -1)) != 1:
            continue
        amount = item.get("amount")
        if amount is None:
            continue
        if not _exact_payment_amount_match(amount, target_amount):
            continue
        tx_id = item.get("txId") or item.get("id") or item.get("txid")
        return True, str(tx_id) if tx_id is not None else "binance_deposit"
    return False, None


def get_network_address(net_key: str) -> str:
    return f"{net_key.upper()}_ADDRESS_NOT_SET"


async def get_payment_address(net_key: str) -> str:
    dep = BINANCE_DEPOSIT_NETWORKS.get(net_key)
    if dep:
        coin, network = dep
        return await fetch_binance_deposit_address(coin, network, net_key.upper())
    return get_network_address(net_key)


BUY_PLANS = {
    "core": {"name": "Core", "price": 10, "duration_days": 7, "price_display": "$10", "credits": "∞ Unlimited"},
    "elite": {"name": "Elite", "price": 15, "duration_days": 15, "price_display": "$15", "credits": "∞ Unlimited"},
    "root": {"name": "Root", "price": 30, "duration_days": 30, "price_display": "$30", "credits": "∞ Unlimited"},
}

_NETWORK_NAMES = {
    "bep20": "Binance Smart Chain",
    "trc20": "TRON Network",
    "ltc": "Litecoin Network",
    "btc": "Bitcoin Network",
    "sol": "Solana Network",
}


def _payment_coin_label(net_key: str) -> str:
    dep = BINANCE_DEPOSIT_NETWORKS.get(net_key)
    return dep[0] if dep else "USDT"


def format_buy_payment_caption(plan_info, net_key, addr, pending=False, payment_found=False):
    price_val = plan_info["price"]
    net_name = _NETWORK_NAMES.get(net_key, "Binance Smart Chain")
    coin = _payment_coin_label(net_key)
    caption = f"""{bs('Plan')} {ARROW} {bs(plan_info['name'])}
{bs('Price')} {ARROW} {bs(f'${price_val}.00 USD')}
{bs('Pay')} {ARROW} {bs(f'{price_val} {coin}')}
{bs('Network')} {ARROW} {bs(net_name)}

{bs('Wallet Address')} {ARROW}
<code>{addr}</code>

{bs('Expires in')} {ARROW} {bs('30 min')}
{bs('Deposits take 3 mins to confirm after completion')}"""
    if payment_found:
        caption += f"""

{PE} {bs('Payment received!')}
{bs('The owner will activate your plan shortly.')}"""
    elif pending:
        caption += f"""

{PE} {bs('Your payment has not arrived yet.')}
{bs('Kindly pay the same amount and press Paid again.')}"""
    return caption


def format_plan_message():
    r = lambda: random.choice([
        5433818199982378380,
        5303453594517790819,
        5413634774268934356,
        5330319637156479518,
        5465478779038095942,
        5465645879035713500,
        5211021358527448098,
        5400228115458849450,
    ])

    text = f"""{updates_channel_bracket_link()} {bs('Buy Premium')} {PE}
{UI_SEP}
{bs('Access')} {ARROW} {bs('Core')} {PE}
{bs('Span')} {ARROW} [{bs('7 Days')}]
{bs('Credits')} {ARROW} {bval('∞')} {bs('Unlimited')}
{bs('Price')} {ARROW} {bs('10 USDT')}
{UI_SEP}
{bs('Access')} {ARROW} {bs('Elite')} {PE}
{bs('Span')} {ARROW} [{bs('15 Days')}]
{bs('Credits')} {ARROW} {bval('∞')} {bs('Unlimited')}
{bs('Price')} {ARROW} {bs('15 USDT')}
{UI_SEP}
{bs('Access')} {ARROW} {bs('Root')} {PE}
{bs('Span')} {ARROW} [{bs('30 Days')}]
{bs('Credits')} {ARROW} {bval('∞')} {bs('Unlimited')}
{bs('Price')} {ARROW} {bs('30 USDT')}
{UI_SEP}
{PE} {bs('Dev')} {ARROW} <a href='{DEV_LINK}'>{bs(DEV_NAME)}</a> {PE}"""

    emoji_ids = [
        4958610528588008305,
        5379869575338812919,
        5836898273666798437,
        4956420911310832630,
        r(),
        6233303538676541503,
    ]
    kb = [[pbtn(bs("Pay Via"), "buy_select_plan", color="blue")]]
    return text, emoji_ids, kb


def format_buy_plan_selection():
    caption = f"""{bs('Select Your Plan')}

{bs('Choose a plan to proceed with secure crypto payment')}"""
    kb = [
        [pbtn(bs("Core $10"), "buy_plan:core", color="blue")],
        [pbtn(bs("Elite $15"), "buy_plan:elite", color="blue")],
        [pbtn(bs("Root $30"), "buy_plan:root", color="blue")],
        [pbtn(f"« {bs('Back')}", "rx_back:main", color="red")]
    ]
    return caption, kb


@client.on(events.NewMessage(pattern=r'(?i)^[/.]buy\b'))
@client.on(events.NewMessage(pattern=r'(?i)^[/.](plan|plans)\b'))
async def plan_cmd(event):
    if await check_maintenance(event):
        return
    if not await force_join_check(event):
        return
    text, emoji_ids, kb = format_plan_message()
    await styled_reply(event, text, buttons=kb, emoji_ids=emoji_ids)


@client.on(events.CallbackQuery(data=b"show_plans"))
async def show_plans_cb(event):
    await event.answer()
    caption, emoji_ids, kb = format_plan_message()
    text, entities = build_entities(caption, emoji_ids=emoji_ids)
    try:
        await event.edit(text, formatting_entities=entities, buttons=kb)
    except Exception:
        pass


@client.on(events.CallbackQuery(data=b"buy_select_plan"))
async def buy_select_plan_cb(event):
    await event.answer()
    caption, kb = format_buy_plan_selection()
    text, entities = build_entities(caption)
    try:
        await event.edit(text, formatting_entities=entities, buttons=kb)
    except Exception:
        pass


@client.on(events.CallbackQuery(pattern=rb"^buy_plan:(core|elite|root)"))
async def buy_plan_cb(event):
    plan_key = event.pattern_match.group(1).decode()
    await event.answer()
    plan_info = BUY_PLANS.get(plan_key)
    if not plan_info:
        return

    caption = f"""{bs(plan_info['name'])} {bs('Plan')}
{bs('Price')} {ARROW} {bs(plan_info['price_display'])}
{bs('Duration')} {ARROW} {bs(f"{plan_info['duration_days']} Days")}
{bs('Credits')} {ARROW} {bval('∞')}
{bs('Select Payment Method')} {ARROW}"""

    kb = [
        [pbtn(bs("BEP20"), f"buy_net:{plan_key}:bep20", color="blue"), pbtn(bs("TRC20"), f"buy_net:{plan_key}:trc20", color="blue")],
        [pbtn(bs("LTC"), f"buy_net:{plan_key}:ltc", color="blue"), pbtn(bs("BTC"), f"buy_net:{plan_key}:btc", color="blue")],
        [pbtn(bs("SOL"), f"buy_net:{plan_key}:sol", color="blue")],
        [pbtn(f"« {bs('Back')}", "buy_select_plan", color="red")]
    ]
    text, entities = build_entities(caption)
    try:
        await event.edit(text, formatting_entities=entities, buttons=kb)
    except Exception:
        pass


@client.on(events.CallbackQuery(pattern=rb"^buy_net:(core|elite|root):(bep20|trc20|ltc|btc|sol)"))
async def buy_net_cb(event):
    plan_key = event.pattern_match.group(1).decode()
    net_key = event.pattern_match.group(2).decode()
    await event.answer()

    plan_info = BUY_PLANS.get(plan_key)
    if not plan_info:
        return

    addr = await get_payment_address(net_key)
    if net_key in BINANCE_DEPOSIT_NETWORKS and not addr:
        return await event.answer("Could not fetch wallet address. Try again.", alert=True)

    caption = format_buy_payment_caption(plan_info, net_key, addr)

    kb = [
        [pbtn(bs("Paid"), f"buy_check:{plan_key}:{net_key}", color="blue")],
        [pbtn(bs("Support"), url=DEV_LINK, color="blue")],
        [pbtn(f"« {bs('Back')}", f"buy_plan:{plan_key}", color="red")]
    ]
    text, entities = build_entities(caption)
    try:
        await event.edit(text, formatting_entities=entities, buttons=kb)
    except Exception:
        pass


@client.on(events.CallbackQuery(pattern=rb"^buy_check:(core|elite|root):(bep20|trc20|ltc|btc|sol)"))
async def buy_check_cb(event):
    plan_key = event.pattern_match.group(1).decode()
    net_key = event.pattern_match.group(2).decode()
    uid = event.sender_id

    plan_info = BUY_PLANS.get(plan_key)
    if not plan_info:
        return await event.answer("Invalid plan", alert=True)

    if net_key not in BINANCE_DEPOSIT_NETWORKS:
        return await event.answer("Unsupported payment network.", alert=True)

    addr = await get_payment_address(net_key)
    if not addr:
        return await event.answer("Could not fetch wallet address. Try again.", alert=True)

    price_val = plan_info["price"]
    coin = _payment_coin_label(net_key)
    tier_name = plan_info["name"]

    is_paid, tx_hash = await check_binance_payment(net_key, price_val)

    kb = [
        [pbtn(bs("Paid"), f"buy_check:{plan_key}:{net_key}", color="blue")],
        [pbtn(bs("Support"), url=DEV_LINK, color="blue")],
        [pbtn(f"« {bs('Back')}", f"buy_plan:{plan_key}", color="red")]
    ]

    if is_paid:
        is_new_notice = await claim_crypto_payment(tx_hash, uid, tier_name, net_key)
        name, username, _, _ = await get_user_info(uid)
        pay_amount_label = f"{price_val} {coin}"

        if is_new_notice:
            owner_msg = f"""{PE} {bs('Crypto Payment Received!')}

{PE} {bs('User:')} {user_link_html(uid, name, username)}
{PE} {bs('User ID:')} <code>{uid}</code>
{PE} {bs('Plan:')} {bs(tier_name)}
{PE} {bs('Amount:')} {bs(pay_amount_label)}
{PE} {bs('Network:')} {bs(net_key.upper())}
{PE} {bs('Tx:')} <code>{tx_hash}</code>

{PE} {bs('Activate the plan manually for this user.')}"""
            owner_emoji_ids = [5226656353744862682, 5278622189556354905, 5084974483685507801, 5172739056592749710]
            for admin_id in ADMIN_ID:
                try:
                    await styled_send(admin_id, owner_msg, emoji_ids=owner_emoji_ids)
                except Exception:
                    pass
            try:
                await styled_send(LOG_CHANNEL_ID, owner_msg, emoji_ids=owner_emoji_ids)
            except Exception:
                pass
            log_user(uid, "CRYPTO_PAYMENT_DETECTED", f"Plan={tier_name} | Amount={pay_amount_label} | Tx={tx_hash} | Net={net_key}")

        caption = format_buy_payment_caption(plan_info, net_key, addr, payment_found=True)
        text, entities = build_entities(caption, emoji_ids=[5226656353744862682, 5278622189556354905])
        try:
            await event.edit(text, formatting_entities=entities, buttons=kb)
        except Exception:
            pass
        return await event.answer("Payment received! Owner will activate your plan shortly.", alert=True)

    caption = format_buy_payment_caption(plan_info, net_key, addr, pending=True)
    text, entities = build_entities(caption, emoji_ids=[5042112436648281096])
    try:
        await event.edit(text, formatting_entities=entities, buttons=kb)
    except Exception:
        pass
    await event.answer("Your payment has not arrived yet. Kindly pay the same amount and press Paid again.", alert=True)


@client.on(events.CallbackQuery(data=b"check_joined"))
async def check_joined_cb(event):
    uid = event.sender_id
    if uid in ADMIN_ID:
        return await event.answer(f"✓ {bs('Admin')}!")
    _JOIN_CACHE.pop(uid, None)
    if await is_user_joined(uid):
        await mark_user_joined(uid)
        ref_result = await complete_referral_on_verify(uid)
        if ref_result and ref_result.get("rewarded"):
            try:
                await styled_send(
                    ref_result["referrer_id"],
                    f"{PE} {bs('Referral reward!')} {ARROW} {bs(f'{REFERRAL_REWARD_DAYS} day premium added')} ({bval(ref_result['count'])} {bs('verified')})",
                    emoji_ids=[REFERRAL_EMOJI],
                )
            except Exception:
                pass
        await event.answer(f"✓ {bs('Access granted! You can now use the bot.')}", alert=True)
        try:
            await styled_edit(
                await event.get_message(),
                f"""{bs('Welcome')} {PE}
{PE} {bs('You have successfully joined the group and channel.')}
{PE} <code>/start</code> {bs('for commands')}""",
                emoji_ids=[5319007286004299794, 5319248624511631572, 5258500422393415126]
            )
        except Exception:
            pass
    else:
        await event.answer(f"✗ {bs('You still need to join both!')}", alert=True)


# Old duplicate plan handlers removed — new Buy Premium system is handled by plan_cmd and show_plans_cb.


@client.on(events.NewMessage(pattern=r'(?i)^[/.]info$'))
async def info_cmd(event):
    if await check_maintenance(event):
        return
    if not await force_join_check(event):
        return
    if await is_banned_user(event.sender_id):
        t, e = banned_user_message()
        return await styled_reply(event, t, emoji_ids=e)
    name, username, tag, prof = await get_user_info(event.sender_id)
    await ensure_user(event.sender_id, name=name, username=username)
    plan = await get_user_plan(event.sender_id)
    user_doc = await get_user_doc(event.sender_id)
    credits = await get_user_credits(event.sender_id)
    credits_display = "Unlimited" if is_paid_plan(plan) or event.sender_id in ADMIN_ID else str(credits)
    joined_dt = await get_user_joined_date(event.sender_id)

    if plan.title() == "Custom":
        access_val = "Custom"
    elif is_paid_plan(plan):
        access_val = plan.capitalize()
    else:
        access_val = FREE_PLAN

    purchased_dt = user_doc.get("updated_at") if user_doc else None
    purchased_str = purchased_dt.strftime('%Y-%m-%d') if purchased_dt and is_paid_plan(plan) else "N/A"

    expiry = user_doc.get("expiry") if user_doc else None
    exp_str = expiry.strftime('%Y-%m-%d') if expiry and is_paid_plan(plan) else "N/A"

    joined_str = joined_dt.strftime('%Y-%m-%d') if joined_dt else "N/A"

    caption = f"""{bs('User')} {ARROW} {user_link_html(event.sender_id, name, username)}
{bs('User ID')} {ARROW} <code>{event.sender_id}</code>
{bs('Access')} {ARROW} {bval(access_val)}
{bs('Purchased oN')} {ARROW} {bval(purchased_str)}
{bs('EndinG oN')} {ARROW} {bval(exp_str)}
{bs('Credits')} {ARROW} {bval(credits_display)}
{bs('Joined')} {ARROW} {bval(joined_str)}"""

    await styled_reply(event, caption, buttons=get_hit_button())


# ====================== SITE MANAGEMENT ======================
@client.on(events.NewMessage(pattern=r'(?i)^[/.]add\b'))
async def add_site(event):
    if await check_maintenance(event):
        return
    if not await force_join_check(event):
        return
    if not is_owner(event.sender_id):
        return await send_owner_only_message(event)
    _, at = await can_use(event.sender_id, event.chat, event=event)
    if at == "banned":
        t, e = banned_user_message()
        return await styled_reply(event, t, emoji_ids=e)
    try:
        sta = []
        add_text = re.sub(r'^[/.]add\s*', '', event.raw_text or '', flags=re.IGNORECASE).strip()
        if event.reply_to_msg_id:
            rm = await event.get_reply_message()
            if rm:
                if rm.document:
                    fp = await rm.download_media()
                    try:
                        async with aiofiles.open(fp, "r", encoding="utf-8", errors="ignore") as f:
                            sta = extract_urls_from_text(await f.read())
                    finally:
                        try:
                            os.remove(fp)
                        except Exception:
                            pass
                elif rm.text:
                    sta = extract_urls_from_text(rm.text)
        elif event.document:
            fp = await event.download_media()
            try:
                async with aiofiles.open(fp, "r", encoding="utf-8", errors="ignore") as f:
                    sta = extract_urls_from_text(await f.read())
            finally:
                try:
                    os.remove(fp)
                except Exception:
                    pass
        if add_text:
            for s in extract_urls_from_text(add_text):
                if s not in sta:
                    sta.append(s)
        if not sta:
            return await styled_reply(event, SITE_USAGE_TEXT, emoji_ids=SITE_USAGE_EMOJIS)

        # Deduplicate input first; gate-specific existing filter happens after Shopify price filter
        new_sites = []
        seen = set()
        for site in sta:
            n = normalize_site_url(site)
            if n and n not in seen:
                seen.add(n)
                new_sites.append(n)

        if not new_sites:
            return await styled_reply(event, f"{PE} {bs('No valid sites found')}", emoji_ids=[CE["cross"]])

        log_user(event.sender_id, "ADD_SITE_START", f"Found {len(new_sites)} site(s)")

        uid = event.sender_id
        existing_norm = {normalize_site_url(s) for s in await get_shopify_sites()}
        current_site_count = len(existing_norm)
        if current_site_count >= MAX_SITES:
            return await styled_reply(event, f"⭐ {bs('Site limit reached')}", emoji_ids=[5042112436648281096])

        filtered_new, already_exists, seen_new = [], [], set()
        for site in new_sites:
            n = normalize_site_url(site)
            if not n:
                continue
            if n in existing_norm:
                already_exists.append(n)
            elif n not in seen_new:
                seen_new.add(n)
                filtered_new.append(n)

        remaining_slots = MAX_SITES - current_site_count
        if len(filtered_new) > remaining_slots:
            filtered_new = filtered_new[:remaining_slots]

        if not filtered_new:
            return await styled_reply(event, f"⭐ {bs('All sites already exist')}", emoji_ids=[5042112436648281096])

        PENDING_ADD_SITES[uid] = {
            "sites": filtered_new,
            "exists": already_exists,
            "event": event,
            "gate": "shopify",
        }
        kb = [
            [pbtn(f"{bs('0-5 USD')}", f"addprice:5:{uid}", color="blue"), pbtn(f"{bs('0-10 USD')}", f"addprice:10:{uid}", color="blue")],
            [pbtn(f"{bs('0-20 USD')}", f"addprice:20:{uid}", color="blue"), pbtn(f"{bs('0-40 USD')}", f"addprice:40:{uid}", color="blue")]
        ]
        caption = build_panel_ui(
            f"⭐  {bs('Select Price Range')}",
            [
                f"⭐ {bs('New Sites')} {ARROW} {bval(len(filtered_new))}",
                f"⭐ {bs('Already Exist')} {ARROW} {bval(len(already_exists))}",
            ],
            footer_lines=[f"⭐ {bs('Only working sites within price range will be added')}"],
        )
        await styled_reply(event, caption, buttons=kb, emoji_ids=[
            5855207143724027916,
            4902715076873553054,
            4902715076873553054,
            5980995951160987855,
        ])

    except Exception as e:
        log_user(event.sender_id, "ADD_SITE_ERROR", f"Error={e}", "error")
        await styled_reply(event, f"{PE} {bs('Error')} {ARROW} <code>{e}</code>", emoji_ids=[CE["cross"]])


@client.on(events.CallbackQuery(pattern=rb"addprice:(\d+):(\d+)"))
async def add_price_cb(event):
    max_price = int(event.pattern_match.group(1).decode())
    uid = int(event.pattern_match.group(2).decode())
    if event.sender_id != uid:
        return await safe_callback_answer(event, f"{bs('Not yours')}!", alert=True)
    data = PENDING_ADD_SITES.pop(uid, None)
    if not data:
        return await safe_callback_answer(event, f"{bs('Expired')}!", alert=True)
    if uid in ACTIVE_ADD_PROCESSES:
        return await safe_callback_answer(event, f"{bs('Already running')}!", alert=True)
    ACTIVE_ADD_PROCESSES[uid] = True
    await safe_callback_answer(event, f"{bs('Testing sites')}...")
    try:
        await event.delete()
    except Exception:
        pass
    asyncio.create_task(_process_add_sites(data["event"], data["sites"], data.get("exists") or [], max_price))


async def _process_add_sites(event, new_sites, already_exists, max_price):
    uid = event.sender_id
    total = len(new_sites)
    tested = 0
    working = 0
    dead = 0
    added_to_db = 0
    chat_id = event.chat_id

    proxies = await get_all_user_proxies(uid, gate="shopify")

    log_user(uid, "ADD_TEST_START", f"Testing {total} sites | MaxPrice=${max_price} | Proxies={len(proxies)}")

    current_sites = await get_shopify_sites()
    remaining_slots = MAX_SITES - len(current_sites)

    sm = await styled_reply(event, build_panel_ui(
        f"⭐ {bs('Testing Sites...')}",
        [f"⭐ {bs('Parsed')} {ARROW} {bval(total)} | {bs('Testing in batches of')} {bval(SITE_WORKERS)}..."],
        footer_lines=[f"⭐ {bs(f'Will stop at {remaining_slots} working sites.')}"],
    ), emoji_ids=[
        5325834523068342417,
        5215327832040811010,
        5084974483685507801,
    ])

    last_ui = [0]
    ui_lock = asyncio.Lock()
    working_sites_data = []

    def is_stopped():
        return uid not in ACTIVE_ADD_PROCESSES

    async def update_ui(force=False):
        now = time.time()
        if not force and now - last_ui[0] < _get_ui_interval():
            return
        async with ui_lock:
            last_ui[0] = now
            try:
                progress_text, progress_emojis = build_site_test_progress_ui(
                    working, added_to_db, dead, tested, total, title="Testing Sites"
                )
                await styled_edit(sm, progress_text, emoji_ids=progress_emojis)
            except:
                pass

    async def test_worker(site):
        nonlocal tested, working, dead, added_to_db
        async with _SITE_SEM:
            if is_stopped():
                return
            try:
                proxy_data = random.choice(proxies) if proxies else None
                res = await test_site(site, proxy_data)
                tested += 1
                if res['status'] == 'alive':
                    working += 1
                    price_str = res.get('price', '-')
                    price_val = _parse_price_value(price_str)
                    working_sites_data.append({'site': site, 'response': res.get('response', '-'), 'price': price_str, 'price_val': price_val})
                    if price_val <= max_price:
                        if await add_global_site(site):
                            added_to_db += 1
                            log_user(uid, "ADD_SITE_OK", f"Site={site} | Price=${price_val} | Added to shared Shopify pool")
                        else:
                            log_user(uid, "ADD_SITE_DUP", f"Site={site} | Already in shared Shopify pool")
                    else:
                        log_user(uid, "ADD_SITE_SKIP", f"Site={site} | Price=${price_val} > MaxPrice=${max_price}")
                else:
                    dead += 1
                    log_user(uid, "ADD_SITE_DEAD", f"Site={site} | Response={res.get('response', '')[:60]}")
                fire_and_forget(update_ui())
            except Exception as e:
                dead += 1
                tested += 1
                log_user(uid, "ADD_SITE_TEST_ERR", f"Site={site} | Error={e}", "error")

    await asyncio.gather(*[asyncio.create_task(test_worker(s)) for s in new_sites])

    log_user(uid, "ADD_TEST_DONE", f"Working={working} | Dead={dead} | AddedToDB={added_to_db} | MaxPrice=${max_price}")

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    fn = f"NOTHING_add_results_{ts}.txt"
    try:
        async with aiofiles.open(fn, 'w', encoding='utf-8') as f:
            await f.write(f"Total working Sites - {working}\n")
            await f.write("═" * 30 + "\n")
            for d in working_sites_data:
                resp = d['response']
                price = d['price']
                ru = resp.upper() if resp else ''
                if 'CARD_DECLINED' in ru:
                    tag = "{CARD_DECLINED}"
                elif 'ORDER_PAID' in ru:
                    tag = "{ORDER_PAID}"
                elif 'GENERIC_ERROR' in ru:
                    tag = "{GENERIC_ERROR}"
                elif '3DS_REQUIRED' in ru:
                    tag = "{3DS_REQUIRED}"
                elif 'INSUFFICIENT_FUNDS' in ru:
                    tag = "{INSUFFICIENT_FUNDS}"
                elif 'DO_NOT_HONOR' in ru:
                    tag = "{DO_NOT_HONOR}"
                elif 'FRAUD' in ru or 'SUSPECTED' in ru:
                    tag = "{FRAUD_SUSPECTED}"
                elif 'CVC' in ru or 'CVV' in ru:
                    tag = "{INCORRECT_CVC}"
                elif 'GENERIC_DECLINE' in ru:
                    tag = "{GENERIC_DECLINE}"
                else:
                    tag = "{" + resp[:30].replace('{', '').replace('}', '') + "}"
                if price and price != '-':
                    ps2 = f"({price})"
                else:
                    ps2 = "($0.00)"
                url = f"https://{d['site']}" if not d['site'].startswith('http') else d['site']
                await f.write(f"{url}  {tag}   {ps2}\n")
    except:
        pass

    try:
        await styled_edit(sm, build_panel_ui(
            f"⭐{bs('Sites Checking Complete!')}",
            [
                f"⭐ {bs('Working')} {ARROW} {bval(working)}",
                f"⭐ {bs('Dead')} {ARROW} {bval(dead)}",
                f"⭐ {bs('Added To DB (0-{max_price})')} {ARROW} {bval(added_to_db)}",
                f"⭐ {bs('Already Existed')} {ARROW} {bval(len(already_exists))}",
                f"⭐ {bs('Total Tested')} {ARROW} {bval(total)}",
            ],
            footer_lines=[f"⭐ {bs('Random')} site will be {bs('used for each CC check.')}"],
        ), emoji_ids=[
            5278622189556354905,
            5278622189556354905,
            5042112436648281096,
            5855207143724027916,
            5134452506935427991,
            5980995951160987855,
            5852670420074893746,
        ])
    except:
        pass

    if working_sites_data:
        try:
            await styled_send(chat_id, f"⭐ {bs('Working Sites')} ({bs(str(working))})", emoji_ids=[5278622189556354905], file=fn)
        except:
            pass
    try:
        os.remove(fn)
    except:
        pass

    ACTIVE_ADD_PROCESSES.pop(uid, None)


@client.on(events.NewMessage(pattern=r'(?i)^[/.]rm\b'))
async def remove_site(event):
    if await check_maintenance(event):
        return
    if not await force_join_check(event):
        return
    if not is_owner(event.sender_id):
        return await send_owner_only_message(event)
    _, at = await can_use(event.sender_id, event.chat, event=event)
    if at == "banned":
        t, e = banned_user_message()
        return await styled_reply(event, t, emoji_ids=e)

    rt = re.sub(r'^[/.]rm\s*', '', event.raw_text, flags=re.IGNORECASE).strip()
    uid = event.sender_id

    if not rt:
        return await styled_reply(event, f"""⭐ <code>/rm site.com</code>
⭐ <code>/rm all</code> {ARROW} {bs('remove all sites')}""", emoji_ids=[
            4902715076873553054, 5042112436648281096, 4902715076873553054
        ])

    if rt.lower() == 'all':
        removed_count = await _rm_clear_all(uid, "shopify")
        if removed_count == 0:
            return await styled_reply(event, f"⭐ {bs('No sites to remove')}", emoji_ids=[5042112436648281096])
        log_user(uid, "RM_ALL_SITES", f"Gate=Shopify | Removed={removed_count}")
        return await styled_reply(event, build_panel_ui(
            f"⭐{bs('All Sites Removed')}",
            [f"⭐ {bs('Removed')} {ARROW} {bval(removed_count)} {bs('sites')}"],
        ), emoji_ids=[5278622189556354905, 5042112436648281096])

    to_rm = extract_urls_from_text(rt)
    if not to_rm:
        return await styled_reply(event, f"⭐ {bs('No URLs found')}", emoji_ids=[5042112436648281096])

    new_sites, seen = [], set()
    for site in to_rm:
        n = normalize_site_url(site)
        if n and n not in seen:
            seen.add(n)
            new_sites.append(n)
    if not new_sites:
        return await styled_reply(event, f"⭐ {bs('No valid sites found')}", emoji_ids=[5042112436648281096])

    removed, nf = await _rm_match_and_delete(uid, "shopify", new_sites)
    log_user(uid, "RM_SITE", f"Gate=Shopify | Removed={len(removed)} | NotFound={len(nf)}")
    parts, eid = [], []
    if removed:
        parts.append("\n".join(f"⭐ {bs('Removed')} {ARROW} <code>{s}</code>" for s in removed))
        eid.extend([5278622189556354905] * len(removed))
    if nf:
        parts.append("\n".join(f"⭐ {bs('Not found')} {ARROW} <code>{s}</code>" for s in nf))
        eid.extend([5042112436648281096] * len(nf))
    return await styled_reply(
        event,
        "\n\n".join(parts) if parts else f"⭐ {bs('None removed')}",
        emoji_ids=eid or [5042112436648281096],
    )


async def _rm_match_and_delete(uid, gate, targets):
    """Remove normalized target sites from the chosen gate pool.
    Returns (removed_list, not_found_list)."""
    removed, nf = [], []
    existing = await get_shopify_sites()
    by_norm = {}
    for ex in existing:
        n = normalize_site_url(ex)
        if n and n not in by_norm:
            by_norm[n] = ex
    for n in targets:
        ex = by_norm.get(n)
        if ex and await remove_global_site(ex):
            removed.append(ex)
        else:
            nf.append(n)
    return removed, nf


async def _rm_clear_all(uid, gate):
    """Clear entire pool for gate. Returns removed count."""
    return await clear_global_sites()


@client.on(events.NewMessage(pattern=r'(?i)^[/.]sites$'))
async def list_sites(event):
    if await check_maintenance(event):
        return
    if not await force_join_check(event):
        return
    if not is_owner(event.sender_id):
        return await send_owner_only_message(event)
    if await is_banned_user(event.sender_id):
        t, e = banned_user_message()
        return await styled_reply(event, t, emoji_ids=e)
    await _send_sites_list(event)


async def _send_sites_list(event, edit_msg=None):
    uid = event.sender_id
    sites = await get_shopify_sites()
    title = f"Shopify Sites ({len(sites)}/{MAX_SITES})"
    empty_text = NO_SITES_UI_TEXT
    check_data = f"checkgate:shopify:{uid}"
    rotate_note = bs("Shared pool used for all users.")

    if not sites:
        if edit_msg:
            text, entities = build_entities(empty_text, emoji_ids=NO_SITES_UI_EMOJIS)
            try:
                await edit_msg.edit(text, formatting_entities=entities, buttons=None, link_preview=False)
            except Exception:
                pass
            return
        return await reply_no_sites(event)

    site_lines = [f"⭐ {bs(f'{i}. {s}')}" for i, s in enumerate(sites[:10], 1)]
    footer_lines = []
    if len(sites) > 10:
        footer_lines.append(f"⭐ {bs(f'... {len(sites) - 10} more')}")
    footer_lines.append(f"⭐ {rotate_note}")
    text = build_panel_ui(f"⭐ {bs(title)}", site_lines, footer_lines=footer_lines)
    eid = [5980995951160987855]
    eid.extend([5084974483685507801] * min(len(sites), 10))
    if len(sites) > 10:
        eid.append(4902715076873553054)
    eid.append(5852670420074893746)
    kb = [[pbtn(bs("Check Sites"), data=check_data, color="blue", icon=5435934308894258303)]]
    if edit_msg:
        text2, entities = build_entities(text, emoji_ids=eid)
        try:
            await edit_msg.edit(text2, formatting_entities=entities, buttons=kb, link_preview=False)
        except Exception:
            pass
        return
    await styled_reply(event, text, buttons=kb, emoji_ids=eid)


@client.on(events.CallbackQuery(pattern=rb"listgate:shopify:(\d+)"))
async def list_gate_cb(event):
    uid = int(event.pattern_match.group(1).decode())
    if event.sender_id != uid or not is_owner(uid):
        return await event.answer(f"{bs('Not yours')}!", alert=True)
    await event.answer()
    await _send_sites_list(event, edit_msg=await event.get_message())


async def run_check_sites_flow(event, edit_msg=None, gate=None):
    uid = event.sender_id
    if not is_owner(uid):
        if edit_msg:
            return await event.answer(f"{bs('Owner only command!')}", alert=True)
        return await send_owner_only_message(event)

    sites = await get_shopify_sites()
    if not sites:
        if edit_msg:
            return await event.answer(f"{bs('No sites')}!", alert=True)
        return await reply_no_sites(event)

    PENDING_SITE_CHECK[uid] = {"sites": sites, "event": event, "gate": "shopify"}

    kb = [
        [pbtn(f"{bs('0-5 USD')}", f"siteprice:5:{uid}", color="blue"), pbtn(f"{bs('0-10 USD')}", f"siteprice:10:{uid}", color="blue")],
        [pbtn(f"{bs('0-20 USD')}", f"siteprice:20:{uid}", color="blue"), pbtn(f"{bs('0-40 USD')}", f"siteprice:40:{uid}", color="blue")]
    ]

    text = build_panel_ui(
        f"⭐  {bs('Select Price Range')}",
        [f"⭐ {bs('Total Sites')} {ARROW} {bval(len(sites))}"],
        footer_lines=[
            f"⭐ {bs('Dead sites will be removed')}",
            f"⭐ {bs('Alive sites outside price range will also be removed')}",
        ],
    )

    emojis = [
        5855207143724027916,
        4902715076873553054,
        5042112436648281096,
        5980995951160987855,
    ]

    if edit_msg:
        await styled_edit(edit_msg, text, buttons=kb, emoji_ids=emojis)
    else:
        await styled_reply(event, text, buttons=kb, emoji_ids=emojis)


@client.on(events.NewMessage(pattern=r'(?i)^[/.]site$'))
async def check_sites_cmd(event):
    if await check_maintenance(event):
        return
    if not await force_join_check(event):
        return
    if not is_owner(event.sender_id):
        return await send_owner_only_message(event)
    if await is_banned_user(event.sender_id):
        t, e = banned_user_message()
        return await styled_reply(event, t, emoji_ids=e)
    await run_check_sites_flow(event)


@client.on(events.CallbackQuery(pattern=rb"check_sites_cb"))
async def check_sites_callback_cb(event):
    if not is_owner(event.sender_id):
        return await event.answer(f"{bs('Owner only command!')}", alert=True)
    await event.answer(f"{bs('Processing')}...")
    await run_check_sites_flow(event, edit_msg=event.message)




@client.on(events.CallbackQuery(pattern=rb"siteprice:(\d+):(\d+)"))
async def site_price_cb(event):
    max_price = int(event.pattern_match.group(1).decode())
    uid = int(event.pattern_match.group(2).decode())
    if event.sender_id != uid:
        return await event.answer(f"{bs('Not yours')}!", alert=True)
    data = PENDING_SITE_CHECK.pop(uid, None)
    if not data:
        return await event.answer(f"{bs('Expired')}!", alert=True)
    await event.answer(f"{bs('Checking sites')}...")
    msg = await event.get_message()
    asyncio.create_task(_process_site_check(data["event"], data["sites"], max_price, edit_msg=msg))


async def _process_site_check(event, sites, max_price, edit_msg=None):
    uid = event.sender_id
    total = len(sites)
    tested = 0
    alive_count = 0
    dead_count = 0
    kept_count = 0
    removed_price = 0
    chat_id = event.chat_id

    proxies = await get_all_user_proxies(uid, gate="shopify")

    log_user(uid, "SITE_CHK_START", f"Checking {total} sites | MaxPrice=${max_price} | Proxies={len(proxies)}")

    checking_text, checking_emojis = build_site_test_progress_ui(0, 0, 0, 0, total, title="Testing Sites")
    if edit_msg:
        sm = edit_msg
        await styled_edit(sm, checking_text, emoji_ids=checking_emojis)
    else:
        sm = await styled_reply(event, checking_text, emoji_ids=checking_emojis)

    last_ui = [0]
    ui_lock = asyncio.Lock()
    alive_sites_data = []
    dead_sites = set()
    price_removed_sites = set()

    async def update_ui(force=False):
        now = time.time()
        if not force and now - last_ui[0] < _get_ui_interval():
            return
        async with ui_lock:
            last_ui[0] = now
            try:
                progress_text, progress_emojis = build_site_test_progress_ui(
                    alive_count, kept_count, dead_count, tested, total, title="Testing Sites"
                )
                await styled_edit(sm, progress_text, emoji_ids=progress_emojis)
            except:
                pass

    async def check_worker(site):
        nonlocal tested, alive_count, dead_count, kept_count, removed_price
        async with _SITE_SEM:
            try:
                proxy_data = random.choice(proxies) if proxies else None
                res = await test_site(site, proxy_data)
                tested += 1

                if res['status'] == 'alive':
                    alive_count += 1
                    price_str = res.get('price', '-')
                    price_val = _parse_price_value(price_str)

                    if price_val <= max_price:
                        kept_count += 1
                        alive_sites_data.append({'site': site, 'response': res.get('response', '-'), 'price': price_str, 'price_val': price_val})
                        log_user(uid, "SITE_ALIVE_KEPT", f"Site={site} | Price=${price_val} | Kept")
                    else:
                        removed_price += 1
                        price_removed_sites.add(normalize_site_url(site))
                        log_user(uid, "SITE_ALIVE_PRICED", f"Site={site} | Price=${price_val} > ${max_price} | Removing")
                else:
                    dead_count += 1
                    dead_sites.add(normalize_site_url(site))
                    log_user(uid, "SITE_DEAD", f"Site={site} | Response={res.get('response', '')[:60]}")

                fire_and_forget(update_ui())
            except Exception as e:
                dead_count += 1
                tested += 1
                dead_sites.add(normalize_site_url(site))
                log_user(uid, "SITE_CHK_ERR", f"Site={site} | Error={e}", "error")

    await asyncio.gather(*[asyncio.create_task(check_worker(s)) for s in sites])

    for s in sites:
        n = normalize_site_url(s)
        if n in dead_sites or n in price_removed_sites:
            await remove_global_site(s)

    total_removed = len(dead_sites) + len(price_removed_sites)

    log_user(uid, "SITE_CHK_DONE", f"Alive={alive_count} | Kept={kept_count} | Dead={dead_count} | PriceRemoved={removed_price} | TotalRemoved={total_removed}")

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    fn = f"NOTHING_working_sites_{ts}.txt"
    try:
        async with aiofiles.open(fn, 'w', encoding='utf-8') as f:
            await f.write(f"Total working Sites - {kept_count}\n")
            await f.write("═" * 30 + "\n")
            for d in alive_sites_data:
                resp = d['response']
                price = d['price']
                ru = resp.upper() if resp else ''
                if 'CARD_DECLINED' in ru:
                    tag = "{CARD_DECLINED}"
                elif 'ORDER_PAID' in ru:
                    tag = "{ORDER_PAID}"
                elif 'GENERIC_ERROR' in ru:
                    tag = "{GENERIC_ERROR}"
                elif '3DS_REQUIRED' in ru:
                    tag = "{OTP_REQUIRED}"
                elif 'INSUFFICIENT_FUNDS' in ru:
                    tag = "{INSUFFICIENT_FUNDS}"
                elif 'DO_NOT_HONOR' in ru:
                    tag = "{DO_NOT_HONOR}"
                elif '3D' in ru or 'AUTHENTICATION' in ru:
                    tag = "{3D_AUTHENTICATION}"
                elif 'CVC' in ru or 'CVV' in ru:
                    tag = "{CVC_CHECK}"
                elif 'GENERIC_DECLINE' in ru:
                    tag = "{GENERIC_DECLINE}"
                else:
                    tag = "{" + resp[:30].replace('{', '').replace('}', '') + "}"
                if price and price != '-':
                    pc2 = str(price).replace('$', '')
                    try:
                        ps2 = f"(${round(float(pc2), 2)})"
                    except:
                        ps2 = f"(${pc2})"
                else:
                    ps2 = "($0.00)"
                url = f"https://{d['site']}" if not d['site'].startswith('http') else d['site']
                await f.write(f"{url}  {tag}   {ps2}\n")
    except:
        pass

    try:
        kb = [[pbtn(bs("Check Sites"), data=f"checkgate:shopify:{uid}", color="blue", icon=5435934308894258303)]]
        await styled_edit(sm, build_panel_ui(
            f"⭐{bs('Sites Checking Complete!')}",
            [
                f"⭐ {bs('Working')} {ARROW} {bval(alive_count)}",
                f"⭐ {bs('Dead')} {ARROW} {bval(dead_count)}",
                f"⭐ {bs('Added To DB (0-${max_price})')} {ARROW} {bval(kept_count)}",
                f"⭐ {bs('Over Price (removed)')} {ARROW} {bval(removed_price)}",
                f"⭐ {bs('Total Tested')} {ARROW} {bval(total)}",
            ],
            footer_lines=[f"⭐ {bs('Random site will be used for each CC check.')}"],
        ), buttons=kb, emoji_ids=[
            5278622189556354905,
            5278622189556354905,
            5042112436648281096,
            5855207143724027916,
            5134452506935427991,
            5980995951160987855,
            5852670420074893746,
        ])
    except:
        pass


    if alive_sites_data:
        try:
            await styled_send(chat_id, f"⭐ {bs('Working Sites')} ({bs(str(kept_count))})", emoji_ids=[5278622189556354905], file=fn)
        except:
            pass
    try:
        os.remove(fn)
    except:
        pass


# ====================== PROXY ======================
PROXY_USAGE_TEXT = f"""⭐ {bs('Usage')}:

⭐ <code>/addpxy host:port:user:pass</code>
⭐ {bs('Multi-line')}:
<code>/addpxy proxy1
proxy2
proxy3</code>

⭐ {bs('Or reply to a .txt file with proxies')}

⭐ {bs('Then choose')} {bs('Shopify')} {ARROW} {bs('Plan Users')} {bs('or')} {bs('Key Users')} ({bs('separate pools')})

⭐ {bs('Supported formats')}:
⭐ <code>host:port</code>
⭐ <code>host:port:user:pass</code>
⭐ <code>user:pass@host:port</code>
⭐ <code>socks5://user:pass@host:port</code>
⭐ <code>socks4 & http & https</code>

⭐ {bs(f'Max {MAX_PROXIES} proxies per pool (Shopify Plan / Shopify Key).')}"""

PROXY_USAGE_EMOJIS = [
    5855207143724027916,
    4902715076873553054,
    4902715076873553054,
    4902715076873553054,
    4902715076873553054,
    5084974483685507801,
    4902715076873553054,
    4902715076873553054,
    4902715076873553054,
    4902715076873553054,
    4902715076873553054,
    5980995951160987855
]

NO_PROXY_UI_TEXT = f"""⭐ <b>No Proxy Set!</b>

⭐ <b>You must add a proxy before checking CC.</b>
⭐ <b>Use: /addpxy host:port:user:pass {ARROW} Shopify</b>"""

NO_PROXY_UI_EMOJIS = [
    5042112436648281096,
    5855207143724027916,
    4902715076873553054,
]


def no_proxy_ui_text(gate: str = None) -> str:
    if gate == "shopify_key":
        return f"""⭐ <b>No Shopify Proxy Set! (Key Users)</b>

⭐ <b>Custom plan /sp and /msp use the Key Users proxy pool only.</b>
⭐ <b>Use: /addpxy {ARROW} Shopify {ARROW} Key Users</b>
⭐ <b>(Plan Users pool is separate and will not be used here.)</b>"""
    if gate == "shopify":
        return f"""⭐ <b>No Shopify Proxy Set! (Plan Users)</b>

⭐ <b>Paid plan /sp and /msp use the Plan Users proxy pool only.</b>
⭐ <b>Use: /addpxy {ARROW} Shopify {ARROW} Plan Users</b>
⭐ <b>(Key Users pool is separate and will not be used here.)</b>"""
    return NO_PROXY_UI_TEXT

SITE_USAGE_TEXT = f"""⭐ {bs('Usage')}:

⭐ <code>/add site</code>
⭐ {bs('Multi-line')}:
<code>/add site1
site2
site3</code>

⭐ {bs('Or reply to a .txt file with sites')}

⭐ {bs('Supported formats')}:
⭐ <code>http://</code> / <code>https://</code>

⭐ {bs(f'Max {MAX_SITES} Shopify sites.')}"""

SITE_USAGE_EMOJIS = [
    5855207143724027916,
    4902715076873553054,
    4902715076873553054,
    4902715076873553054,
    5084974483685507801,
    4902715076873553054,
    4902715076873553054,
    5980995951160987855
]

async def reply_no_proxy(event, gate: str = None):
    return await styled_reply(event, no_proxy_ui_text(gate), emoji_ids=NO_PROXY_UI_EMOJIS)


NO_SITES_UI_TEXT = f"""⭐ {bs('No Sites!')}

⭐ {bs('You must add some sites before checking.')}
⭐ {bs('Use: /add site1 or reply to a .txt file with sites.')}"""

NO_SITES_UI_EMOJIS = [
    5042112436648281096,
    5855207143724027916,
    4902715076873553054
]

async def reply_no_sites(event):
    return await styled_reply(event, NO_SITES_UI_TEXT, emoji_ids=NO_SITES_UI_EMOJIS)


def _proxy_gate_label(gate: str) -> str:
    g = (gate or "").strip().lower()
    if g == "shopify_key":
        return "Shopify (Key Users)"
    return "Shopify (Plan Users)"


def _shopify_pool_gate(pool: str) -> str:
    return "shopify_key" if (pool or "").strip().lower() == "key" else "shopify"


def _proxy_gate_select_text(extra_line=None):
    lines = [
        f"⭐ {bs('Shopify')} {ARROW} {bs('Plan Users')} {bs('or')} {bs('Key Users')}",
    ]
    if extra_line:
        return build_panel_ui(
            f"⭐  {bs('Select Gate')}",
            lines,
            secondary_lines=[extra_line],
        )
    return build_panel_ui(f"⭐  {bs('Select Gate')}", lines)


def _shopify_pool_select_text(action: str = None, extra_line=None):
    pool_lines = [
        f"⭐ {bs('Plan Users')} {ARROW} {bs('Core / Elite / Root / X')} ({bs('main API')})",
        f"⭐ {bs('Key Users')} {ARROW} {bs('Custom plan')} ({bs('3 Rotating APIs')})",
    ]
    footer = f"⭐ {bs('Pools are separate — no cross-use.')}"
    if action:
        text = build_panel_ui(
            f"⭐  {bs('Select Shopify Pool')}",
            [f"⭐ {bs('Action')} {ARROW} {bval(action)}"],
            secondary_lines=pool_lines,
            footer_lines=[footer],
        )
    else:
        text = build_panel_ui(
            f"⭐  {bs('Select Shopify Pool')}",
            pool_lines,
            footer_lines=[footer],
        )
    if extra_line:
        text += f"\n{extra_line}"
    return text


def _proxy_gate_select_emojis():
    return [5855207143724027916, 4902715076873553054, 4902715076873553054]


def _shopify_pool_kb(prefix: str, uid: int):
    return [
        [pbtn(bs("Plan Users"), f"{prefix}shop:plan:{uid}", color="blue"),
         pbtn(bs("Key Users"), f"{prefix}shop:key:{uid}", color="primary")],
    ]


def _proxy_gate_kb(prefix: str, uid: int):
    return [
        [pbtn(bs("Shopify"), f"{prefix}gate:shopify:{uid}", color="blue"),],
    ]


def _proxy_test_hint(gate: str) -> str:
    if gate == "shopify_key":
        return bs("Verified on Shopify 3 rotating APIs (Key Users).")
    if gate == "shopify":
        return bs("Verified on Shopify API (Plan Users).")
    return bs("Will stop at working proxies.")


async def _parse_proxy_lines_from_event(event):
    lines = []
    if event.is_reply:
        rm = await event.get_reply_message()
        if rm and rm.file:
            fp = await rm.download_media()
            try:
                async with aiofiles.open(fp, "r", encoding="utf-8") as f:
                    lines = [l.strip() for l in (await f.read()).splitlines() if l.strip()]
            finally:
                try:
                    os.remove(fp)
                except Exception:
                    pass
        elif rm and rm.text:
            lines = [l.strip() for l in rm.text.splitlines() if l.strip()]
    else:
        p = event.raw_text.split(maxsplit=1)
        if len(p) == 2:
            lines = [l.strip() for l in p[1].splitlines() if l.strip()]
    return lines


def build_proxy_test_progress_ui(gate_label, lines, title="Testing proxies in background..."):
    return build_panel_ui(f"⭐ {bs(title)} ({bs(gate_label)})", lines)


def build_proxy_test_complete_ui(gate_label, lines, footer_lines=None, title="Proxy Testing Complete!"):
    return build_panel_ui(f"⭐ {bs(title)} ({bs(gate_label)})", lines, footer_lines=footer_lines)


async def _process_add_proxies(event, parsed, gate: str):
    uid = event.sender_id
    gate_label = _proxy_gate_label(gate)
    cc = await get_proxy_count(uid, gate=gate)
    remaining_slots = MAX_PROXIES - cc
    if remaining_slots <= 0:
        return await styled_reply(event, f"⭐ {bs('Limit')} {bs(f'{MAX_PROXIES}/{MAX_PROXIES}')} ({bs(gate_label)})", emoji_ids=[5042112436648281096])
    parsed = parsed[:remaining_slots]
    log_user(uid, "ADD_PROXY_START", f"Gate={gate_label} | Testing {len(parsed)} proxies | Workers={PROXY_TEST_WORKERS} | Current={cc}/{MAX_PROXIES}")

    tm = await styled_reply(event, build_proxy_test_progress_ui(gate_label, [
        f"⭐ {bs('Parsed')} {ARROW} {bval(len(parsed))} | {bs('Workers')} {ARROW} {bval(PROXY_TEST_WORKERS)}",
    ], title="Testing proxies in background...") + f"\n⭐ {_proxy_test_hint(gate)}", emoji_ids=[
        5325834523068342417,
        5215327832040811010,
        5084974483685507801,
    ])

    added, failed = [], []
    tested_count = 0
    ui_lock = asyncio.Lock()
    last_ui = [0.0]

    async def refresh_ui(force=False):
        now = time.time()
        if not force and now - last_ui[0] < PROXY_TEST_UI_INTERVAL:
            return
        async with ui_lock:
            if not force and now - last_ui[0] < PROXY_TEST_UI_INTERVAL:
                return
            last_ui[0] = now
            await styled_edit(tm, build_proxy_test_progress_ui(gate_label, [
                f"⭐ {bs('Working')} {ARROW} {bval(f'{len(added)}/{remaining_slots}')}",
                f"⭐ {bs('Dead')} {ARROW} {bval(len(failed))}",
                f"⭐ {bs('Tested')} {ARROW} {bval(f'{tested_count}/{len(parsed)}')}",
                f"⭐ {bs('Workers')} {ARROW} {PROXY_TEST_WORKERS}",
            ]), emoji_ids=[
                5325834523068342417,
                5278622189556354905,
                5042112436648281096,
                5215327832040811010,
            ])

    async def on_result(pd2, res):
        nonlocal tested_count
        tested_count += 1
        d = f"{pd2['ip']}:{pd2['port']}"
        proxy_url = pd2.get('proxy_url', d)
        if isinstance(res, tuple) and res[0]:
            await add_proxy_db(uid, pd2, gate=gate)
            added.append(d)
            log_user(uid, "ADD_PROXY_OK", f"Gate={gate_label} | Proxy={proxy_url} | Response={res[1]} | [{tested_count}/{len(parsed)}]")
        else:
            failed.append(d)
            err_detail = res[1] if isinstance(res, tuple) else str(res)[:80]
            log_user(uid, "ADD_PROXY_DEAD", f"Gate={gate_label} | Proxy={proxy_url} | Error={err_detail} | [{tested_count}/{len(parsed)}]", "warning")
        await refresh_ui()

    try:
        await run_parallel_proxy_tests(parsed, gate, on_result, worker_count=PROXY_TEST_WORKERS)
        await refresh_ui(force=True)
        log_user(uid, "ADD_PROXY_DONE", f"Gate={gate_label} | Added={len(added)} | Failed={len(failed)} | Total={cc + len(added)}/{MAX_PROXIES}")

        if added:
            await styled_edit(tm, build_proxy_test_complete_ui(gate_label, [
                f"⭐ {bs('Working')} {ARROW} {bval(len(added))}",
                f"⭐ {bs('Dead')} {ARROW} {bval(len(failed))}",
                f"⭐ {bs('Total saved')} {ARROW} {bval(f'{len(added)}/{remaining_slots}')}",
            ], footer_lines=[f"⭐ {bs('Saved to')} {ARROW} {bs(gate_label)} {bs('proxy pool')}"]), emoji_ids=[
                5278622189556354905,
                5084974483685507801,
                5042112436648281096,
                5980995951160987855,
                5852670420074893746,
            ])
        else:
            await styled_edit(tm, f"""⭐ {bs('All proxies are dead!')} ({bs(gate_label)})

⭐ {bs('Tested')} {ARROW} {bval(len(parsed))} | {bs('None working.')}""", emoji_ids=[
                5042112436648281096,
                5855207143724027916,
            ])
    except Exception as e:
        log_user(uid, "ADD_PROXY_ERROR", f"Gate={gate_label} | Error={e}", "error")
        await styled_edit(tm, f"⭐ {bs('Error')} {ARROW} <code>{e}</code>", emoji_ids=[5042112436648281096])


async def _run_add_proxies_worker(event, parsed, gate: str, add_key: str):
    try:
        await _process_add_proxies(event, parsed, gate)
    finally:
        ACTIVE_ADD_PROXY.pop(add_key, None)


@client.on(events.NewMessage(pattern=r'(?i)^[/.]addpxy'))
async def add_proxy_cmd(event):
    if await check_maintenance(event):
        return
    if not await force_join_check(event):
        return
    if not is_owner(event.sender_id):
        return await send_owner_only_message(event)
    if event.is_group:
        return await styled_reply(event, f"⭐ {bs('Private only')}", emoji_ids=[5042112436648281096])
    if await is_banned_user(event.sender_id):
        t, e = banned_user_message()
        return await styled_reply(event, t, emoji_ids=e)

    try:
        lines = await _parse_proxy_lines_from_event(event)
        if not lines and len(event.raw_text.split(maxsplit=1)) < 2 and not event.is_reply:
            return await styled_reply(event, PROXY_USAGE_TEXT, emoji_ids=PROXY_USAGE_EMOJIS)
        if not lines:
            return await styled_reply(event, f"⭐ {bs('No proxies found')}", emoji_ids=[5042112436648281096])

        await ensure_user(event.sender_id)
        parsed, seen = [], set()
        for l in lines:
            pd = parse_proxy_format(l)
            if pd and pd['proxy_url'] not in seen:
                parsed.append(pd)
                seen.add(pd['proxy_url'])
        if not parsed:
            return await styled_reply(event, f"⭐ {bs('No valid proxies')}", emoji_ids=[5042112436648281096])

        uid = event.sender_id
        PENDING_ADD_PROXIES[uid] = {"proxies": parsed, "event": event}
        await styled_reply(event, _proxy_gate_select_text(
            f"⭐ {bs('Proxies parsed')} {ARROW} {bval(len(parsed))}"
        ), buttons=_proxy_gate_kb("addpxy", uid), emoji_ids=_proxy_gate_select_emojis())
    except Exception as e:
        log_user(event.sender_id, "ADD_PROXY_ERROR", f"Error={e}", "error")
        await styled_reply(event, f"⭐ {bs('Error')} {ARROW} <code>{e}</code>", emoji_ids=[5042112436648281096])


@client.on(events.CallbackQuery(pattern=rb"addpxygate:shopify:(\d+)"))
async def add_proxy_gate_cb(event):
    gate = event.pattern_match.group(1).decode()
    uid = int(event.pattern_match.group(2).decode())
    if event.sender_id != uid or not is_owner(uid):
        return await safe_callback_answer(event, f"{bs('Not yours')}!", alert=True)
    if not PENDING_ADD_PROXIES.get(uid):
        return await safe_callback_answer(event, f"{bs('Expired')}!", alert=True)
    if gate == "shopify":
        await safe_callback_answer(event, f"{bs('Select Shopify pool')}...")
        try:
            await styled_edit(
                await event.get_message(),
                _shopify_pool_select_text(
                    extra_line=f"⭐ {bs('Proxies parsed')} {ARROW} {bval(len(PENDING_ADD_PROXIES[uid].get('proxies') or []))}",
                ),
                buttons=_shopify_pool_kb("addpxy", uid),
                emoji_ids=_proxy_gate_select_emojis(),
            )
        except Exception:
            pass
        return

@client.on(events.CallbackQuery(pattern=rb"addpxyshop:(plan|key):(\d+)"))
async def add_proxy_shop_pool_cb(event):
    pool = event.pattern_match.group(1).decode()
    uid = int(event.pattern_match.group(2).decode())
    if event.sender_id != uid or not is_owner(uid):
        return await safe_callback_answer(event, f"{bs('Not yours')}!", alert=True)
    data = PENDING_ADD_PROXIES.pop(uid, None)
    if not data:
        return await safe_callback_answer(event, f"{bs('Expired')}!", alert=True)
    gate = _shopify_pool_gate(pool)
    await safe_callback_answer(event, f"{bs('Testing')} {_proxy_gate_label(gate)}...")
    try:
        await event.delete()
    except Exception:
        pass
    await _start_add_proxies(data, gate, uid, event)


async def _start_add_proxies(data, gate: str, uid: int, event):
    parsed = list(data.get("proxies") or [])
    existing = {p['proxy_url'] for p in await get_all_user_proxies(uid, gate=gate)}
    parsed = [p for p in parsed if p.get('proxy_url') not in existing]
    if not parsed:
        return await styled_reply(data.get("event") or event, f"⭐ {bs('All proxies already exist')} ({bs(_proxy_gate_label(gate))})", emoji_ids=[5042112436648281096])
    add_key = f"{uid}:{gate}"
    if add_key in ACTIVE_ADD_PROXY:
        return await safe_callback_answer(event, f"{bs('Already testing')} {_proxy_gate_label(gate)}!", alert=True)
    ACTIVE_ADD_PROXY[add_key] = True
    asyncio.create_task(_run_add_proxies_worker(data.get("event") or event, parsed, gate, add_key))


async def _send_proxy_list(event, gate: str, edit_msg=None):
    uid = event.sender_id
    gate_label = _proxy_gate_label(gate)
    proxies = await get_all_user_proxies(uid, gate=gate)
    if not proxies:
        msg = f"""⭐ {bs('No Proxy Set!')} ({bs(gate_label)})

⭐ {bs('Use')} <code>/addpxy</code> {ARROW} {bs(gate_label)}"""
        if edit_msg:
            try:
                await styled_edit(edit_msg, msg, emoji_ids=NO_PROXY_UI_EMOJIS)
            except Exception:
                pass
            return
        return await styled_reply(event, msg, emoji_ids=NO_PROXY_UI_EMOJIS)

    proxy_lines = []
    for i, p in enumerate(proxies[:10], 1):
        ip = str(p.get("ip") or "")
        port = str(p.get("port") or "")
        ptype = str(p.get("proxy_type") or "http").upper()
        proxy_lines.append(f"⭐ {bs(f'{i}. {ip}:{port} ({ptype})')}")
    footer_lines = []
    if len(proxies) > 10:
        footer_lines.append(f"⭐ {bs(f'... {len(proxies) - 10} more')}")
    text = build_panel_ui(f"⭐ {bs(f'{gate_label} Proxies [{len(proxies)}/{MAX_PROXIES}]')}", proxy_lines, footer_lines=footer_lines)
    eid = [5042101437237036298]
    eid.extend([5084974483685507801] * min(len(proxies), 10))
    if len(proxies) > 10:
        eid.append(4902715076873553054)
    eid.append(5852670420074893746)
    kb = [[pbtn(bs("Check Proxy"), data=f"checkpxygate:{gate}:{uid}", color="blue", icon=5435934308894258303)]]
    if edit_msg:
        await styled_edit(edit_msg, text, buttons=kb, emoji_ids=eid)
    else:
        await styled_reply(event, text, buttons=kb, emoji_ids=eid)


@client.on(events.NewMessage(pattern=r'(?i)^[/.]proxy$'))
async def view_proxies(event):
    if await check_maintenance(event):
        return
    if not await force_join_check(event):
        return
    if not is_owner(event.sender_id):
        return await send_owner_only_message(event)
    if event.is_group:
        return await styled_reply(event, f"⭐ {bs('Private only')}", emoji_ids=[5042112436648281096])
    if await is_banned_user(event.sender_id):
        t, e = banned_user_message()
        return await styled_reply(event, t, emoji_ids=e)

    uid = event.sender_id
    await styled_reply(event, _proxy_gate_select_text(), buttons=_proxy_gate_kb("listpxy", uid), emoji_ids=_proxy_gate_select_emojis())


@client.on(events.CallbackQuery(pattern=rb"listpxygate:shopify:(\d+)"))
async def list_proxy_gate_cb(event):
    gate = event.pattern_match.group(1).decode()
    uid = int(event.pattern_match.group(2).decode())
    if event.sender_id != uid or not is_owner(uid):
        return await safe_callback_answer(event, f"{bs('Not yours')}!", alert=True)
    if gate == "shopify":
        await safe_callback_answer(event, f"{bs('Select Shopify pool')}...")
        try:
            await styled_edit(
                await event.get_message(),
                _shopify_pool_select_text(),
                buttons=_shopify_pool_kb("listpxy", uid),
                emoji_ids=_proxy_gate_select_emojis(),
            )
        except Exception:
            pass
        return
    await safe_callback_answer(event)
    await _send_proxy_list(event, gate, edit_msg=await event.get_message())


@client.on(events.CallbackQuery(pattern=rb"listpxyshop:(plan|key):(\d+)"))
async def list_proxy_shop_pool_cb(event):
    pool = event.pattern_match.group(1).decode()
    uid = int(event.pattern_match.group(2).decode())
    if event.sender_id != uid or not is_owner(uid):
        return await safe_callback_answer(event, f"{bs('Not yours')}!", alert=True)
    gate = _shopify_pool_gate(pool)
    await safe_callback_answer(event)
    await _send_proxy_list(event, gate, edit_msg=await event.get_message())


@client.on(events.NewMessage(pattern=r'(?i)^[/.]rmpxy'))
async def remove_proxy_cmd(event):
    if await check_maintenance(event):
        return
    if not await force_join_check(event):
        return
    if not is_owner(event.sender_id):
        return await send_owner_only_message(event)
    if event.is_group:
        return await styled_reply(event, f"⭐ {bs('Private only')}", emoji_ids=[5042112436648281096])
    if await is_banned_user(event.sender_id):
        t, e = banned_user_message()
        return await styled_reply(event, t, emoji_ids=e)

    p = event.raw_text.split(maxsplit=1)
    if len(p) == 1:
        return await styled_reply(event, f"""⭐ <code>/rmpxy index</code>
⭐ <code>/rmpxy all</code>
⭐ {bs('Then choose')} {bs('Shopify')} {ARROW} {bs('Plan Users')} {bs('or')} {bs('Key Users')}""", emoji_ids=[4902715076873553054, 5042112436648281096, 4902715076873553054])

    arg = p[1].strip().lower()
    uid = event.sender_id
    if arg == 'all':
        PENDING_RM_PROXIES[uid] = {"mode": "all", "index": None, "event": event}
    else:
        try:
            idx = int(arg) - 1
            if idx < 0:
                raise ValueError("bad index")
        except Exception:
            return await styled_reply(event, f"⭐ {bs('Invalid index')}", emoji_ids=[5042112436648281096])
        PENDING_RM_PROXIES[uid] = {"mode": "index", "index": idx, "event": event}

    action = bs("Remove ALL proxies") if arg == "all" else f"{bs('Remove index')} #{int(arg)}"
    await styled_reply(
        event,
        _proxy_gate_select_text(f"⭐ {bs('Action')} {ARROW} {bval(action)}"),
        buttons=_proxy_gate_kb("rmpxy", uid),
        emoji_ids=_proxy_gate_select_emojis(),
    )


@client.on(events.CallbackQuery(pattern=rb"rmpxygate:shopify:(\d+)"))
async def rm_proxy_gate_cb(event):
    gate = event.pattern_match.group(1).decode()
    uid = int(event.pattern_match.group(2).decode())
    if event.sender_id != uid or not is_owner(uid):
        return await safe_callback_answer(event, f"{bs('Not yours')}!", alert=True)
    if not PENDING_RM_PROXIES.get(uid):
        return await safe_callback_answer(event, f"{bs('Expired')}!", alert=True)
    if gate == "shopify":
        action = PENDING_RM_PROXIES[uid].get("mode")
        action_txt = bs("Remove ALL proxies") if action == "all" else f"{bs('Remove index')} #{PENDING_RM_PROXIES[uid].get('index', 0) + 1}"
        await safe_callback_answer(event, f"{bs('Select Shopify pool')}...")
        try:
            await styled_edit(
                await event.get_message(),
                _shopify_pool_select_text(action_txt),
                buttons=_shopify_pool_kb("rmpxy", uid),
                emoji_ids=_proxy_gate_select_emojis(),
            )
        except Exception:
            pass
        return
    data = PENDING_RM_PROXIES.pop(uid, None)
    if not data:
        return await safe_callback_answer(event, f"{bs('Expired')}!", alert=True)
    await safe_callback_answer(event, f"{bs('Done')}")
    try:
        await event.delete()
    except Exception:
        pass
    await _execute_rm_proxy(data, gate, uid, event)


@client.on(events.CallbackQuery(pattern=rb"rmpxyshop:(plan|key):(\d+)"))
async def rm_proxy_shop_pool_cb(event):
    pool = event.pattern_match.group(1).decode()
    uid = int(event.pattern_match.group(2).decode())
    if event.sender_id != uid or not is_owner(uid):
        return await safe_callback_answer(event, f"{bs('Not yours')}!", alert=True)
    data = PENDING_RM_PROXIES.pop(uid, None)
    if not data:
        return await safe_callback_answer(event, f"{bs('Expired')}!", alert=True)
    gate = _shopify_pool_gate(pool)
    await safe_callback_answer(event, f"{bs('Done')}")
    try:
        await event.delete()
    except Exception:
        pass
    await _execute_rm_proxy(data, gate, uid, event)


async def _execute_rm_proxy(data, gate: str, uid: int, event):
    src = data.get("event") or event
    gate_label = _proxy_gate_label(gate)
    proxies = await get_all_user_proxies(uid, gate=gate)
    if not proxies:
        return await styled_reply(src, f"⭐ {bs('No Proxy Set!')} ({bs(gate_label)})", emoji_ids=NO_PROXY_UI_EMOJIS)

    if data.get("mode") == "all":
        c = await clear_all_proxies(uid, gate=gate)
        log_user(uid, "RM_PROXY_ALL", f"Gate={gate_label} | Cleared={c}")
        return await styled_reply(src, f"⭐ {bs('All')} {bs(str(c))} {bs(gate_label)} {bs('proxies removed')}", emoji_ids=[5278622189556354905])

    idx = data.get("index")
    if idx is None or not (0 <= idx < len(proxies)):
        return await styled_reply(src, f"⭐ {bs('Invalid')} ({bs('1')}-{bs(str(len(proxies)))}) ({bs(gate_label)})", emoji_ids=[5042112436648281096])
    rm = await remove_proxy_by_index(uid, idx, gate=gate)
    if not rm:
        return await styled_reply(src, f"⭐ {bs('Invalid index')} ({bs(gate_label)})", emoji_ids=[5042112436648281096])
    log_user(uid, "RM_PROXY", f"Gate={gate_label} | Removed={rm['ip']}:{rm['port']}")
    await styled_reply(src, f"⭐ {bs('Removed')} {ARROW} <code>{rm['ip']}:{rm['port']}</code> ({bs(gate_label)})", emoji_ids=[5278622189556354905])


async def run_check_proxies(event, tm=None, gate: str = "shopify"):
    uid = event.sender_id
    gate_label = _proxy_gate_label(gate)
    proxies = await get_all_user_proxies(uid, gate=gate)
    if not proxies:
        msg = f"""⭐ {bs('No Proxy Set!')} ({bs(gate_label)})

⭐ {bs('Use')} <code>/addpxy</code> {ARROW} {bs(gate_label)}"""
        if tm:
            return await styled_edit(tm, msg, emoji_ids=NO_PROXY_UI_EMOJIS)
        return await styled_reply(event, msg, emoji_ids=NO_PROXY_UI_EMOJIS)

    log_user(uid, "CHK_PROXY_START", f"Gate={gate_label} | Testing {len(proxies)} proxies | Workers={PROXY_TEST_WORKERS}")
    start_text = build_proxy_test_progress_ui(gate_label, [
        f"⭐ {bs('Total')} {ARROW} {bval(len(proxies))}",
        f"⭐ {bs('Workers')} {ARROW} {PROXY_TEST_WORKERS}",
    ], title="Checking Proxies in background...") + f"\n⭐ {_proxy_test_hint(gate)}"
    start_emojis = [5325834523068342417, 5215327832040811010, 5084974483685507801]
    if tm:
        await styled_edit(tm, start_text, emoji_ids=start_emojis)
    else:
        tm = await styled_reply(event, start_text, emoji_ids=start_emojis)

    w, d, tested = 0, 0, 0
    ui_lock = asyncio.Lock()
    last_ui = [0.0]

    async def refresh_ui(force=False):
        now = time.time()
        if not force and now - last_ui[0] < PROXY_TEST_UI_INTERVAL:
            return
        async with ui_lock:
            if not force and now - last_ui[0] < PROXY_TEST_UI_INTERVAL:
                return
            last_ui[0] = now
            await styled_edit(tm, build_proxy_test_progress_ui(gate_label, [
                f"⭐ {bs('Working')} {ARROW} {bval(f'{w}/{len(proxies)}')}",
                f"⭐ {bs('Dead')} {ARROW} {bval(d)}",
                f"⭐ {bs('Tested')} {ARROW} {bval(f'{tested}/{len(proxies)}')}",
                f"⭐ {bs('Workers')} {ARROW} {PROXY_TEST_WORKERS}",
            ]), emoji_ids=[
                5325834523068342417,
                5278622189556354905,
                5042112436648281096,
                5215327832040811010,
            ])

    async def on_result(proxy, res):
        nonlocal w, d, tested
        tested += 1
        proxy_url = proxy.get('proxy_url', '?')
        if isinstance(res, tuple) and res[0]:
            w += 1
            log_user(uid, "CHK_PROXY_OK", f"Gate={gate_label} | Proxy={proxy_url} | Response={res[1]} | [{tested}/{len(proxies)}]")
        else:
            d += 1
            err_detail = res[1] if isinstance(res, tuple) else str(res)[:80]
            log_user(uid, "CHK_PROXY_DEAD", f"Gate={gate_label} | Proxy={proxy_url} | Error={err_detail} | [{tested}/{len(proxies)}]", "warning")
            try:
                await remove_proxy_by_url(uid, proxy['proxy_url'], gate=gate)
            except Exception:
                pass
        await refresh_ui()

    await run_parallel_proxy_tests(proxies, gate, on_result, worker_count=PROXY_TEST_WORKERS)
    await refresh_ui(force=True)

    log_user(uid, "CHK_PROXY_DONE", f"Gate={gate_label} | Working={w} | Dead={d} | Total={len(proxies)}")

    if w > 0:
        remaining_proxies = await get_all_user_proxies(uid, gate=gate)
        proxy_lines = []
        for i, p in enumerate(remaining_proxies[:10], 1):
            ip = str(p.get("ip") or "")
            port = str(p.get("port") or "")
            ptype = str(p.get("proxy_type") or "http").upper()
            proxy_lines.append(f"⭐ {bs(f'{i}. {ip}:{port} ({ptype})')}")
        footer_lines = []
        if len(remaining_proxies) > 10:
            footer_lines.append(f"⭐ {bs(f'... {len(remaining_proxies) - 10} more')}")
        text = build_proxy_test_complete_ui(gate_label, [
            f"⭐ {bs('Working')} {ARROW} {bval(w)}",
            f"⭐ {bs('Dead')} {ARROW} {bval(d)}",
            f"⭐ {bs('Total saved')} {ARROW} {bval(f'{w}/{len(proxies)}')}",
            *proxy_lines,
        ], footer_lines=footer_lines, title="Proxy Check Complete!")
        eid = [5278622189556354905, 5084974483685507801, 5042112436648281096, 5980995951160987855]
        eid.extend([5084974483685507801] * min(len(remaining_proxies), 10))
        if len(remaining_proxies) > 10:
            eid.append(4902715076873553054)
        eid.append(5852670420074893746)
        kb = [[pbtn(bs("Check Proxy"), data=f"checkpxygate:{gate}:{uid}", color="blue", icon=5435934308894258303)]]
        await styled_edit(tm, text, buttons=kb, emoji_ids=eid)
    else:
        await styled_edit(tm, f"""⭐ {bs('All proxies are dead!')} ({bs(gate_label)})

⭐ {bs('Tested')} {ARROW} {bval(len(proxies))} | {bs('None working.')}""", emoji_ids=[
            5042112436648281096,
            5855207143724027916,
        ])


async def _run_check_proxies_worker(event, gate: str, chk_key: str):
    try:
        await run_check_proxies(event, tm=None, gate=gate)
    except Exception as e:
        log_user(event.sender_id, "CHK_PROXY_ERROR", f"Gate={gate} | Error={e}", "error")
    finally:
        ACTIVE_CHK_PROXY.pop(chk_key, None)


@client.on(events.NewMessage(pattern=r'(?i)^[/.]chkpxy$'))
async def check_proxies_cmd(event):
    if await check_maintenance(event):
        return
    if not await force_join_check(event):
        return
    if not is_owner(event.sender_id):
        return await send_owner_only_message(event)
    if event.is_group:
        return await styled_reply(event, f"⭐ {bs('Private only')}", emoji_ids=[5042112436648281096])
    if await is_banned_user(event.sender_id):
        t, e = banned_user_message()
        return await styled_reply(event, t, emoji_ids=e)

    uid = event.sender_id
    await styled_reply(event, _proxy_gate_select_text(), buttons=_proxy_gate_kb("checkpxy", uid), emoji_ids=_proxy_gate_select_emojis())


@client.on(events.CallbackQuery(pattern=rb"checkpxygate:(shopify|shopify_key):(\d+)"))
async def check_proxy_gate_cb(event):
    gate = event.pattern_match.group(1).decode()
    uid = int(event.pattern_match.group(2).decode())
    if event.sender_id != uid or not is_owner(uid):
        return await safe_callback_answer(event, f"{bs('Not yours')}!", alert=True)
    if await is_banned_user(uid):
        return await safe_callback_answer(event, "You are banned.", alert=True)
    if gate == "shopify":
        await safe_callback_answer(event, f"{bs('Select Shopify pool')}...")
        try:
            await styled_edit(
                await event.get_message(),
                _shopify_pool_select_text(),
                buttons=_shopify_pool_kb("checkpxy", uid),
                emoji_ids=_proxy_gate_select_emojis(),
            )
        except Exception:
            pass
        return
    chk_key = f"{uid}:{gate}"
    if chk_key in ACTIVE_CHK_PROXY:
        return await safe_callback_answer(event, f"{bs('Already checking')} {_proxy_gate_label(gate)}!", alert=True)
    ACTIVE_CHK_PROXY[chk_key] = True
    await safe_callback_answer(event, f"{bs('Checking')} {_proxy_gate_label(gate)}...")
    asyncio.create_task(_run_check_proxies_worker(event, gate, chk_key))


@client.on(events.CallbackQuery(pattern=rb"checkpxyshop:(plan|key):(\d+)"))
async def check_proxy_shop_pool_cb(event):
    pool = event.pattern_match.group(1).decode()
    uid = int(event.pattern_match.group(2).decode())
    if event.sender_id != uid or not is_owner(uid):
        return await safe_callback_answer(event, f"{bs('Not yours')}!", alert=True)
    if await is_banned_user(uid):
        return await safe_callback_answer(event, "You are banned.", alert=True)
    gate = _shopify_pool_gate(pool)
    chk_key = f"{uid}:{gate}"
    if chk_key in ACTIVE_CHK_PROXY:
        return await safe_callback_answer(event, f"{bs('Already checking')} {_proxy_gate_label(gate)}!", alert=True)
    ACTIVE_CHK_PROXY[chk_key] = True
    await safe_callback_answer(event, f"{bs('Checking')} {_proxy_gate_label(gate)}...")
    asyncio.create_task(_run_check_proxies_worker(event, gate, chk_key))


@client.on(events.CallbackQuery(data=b"check_proxies_cb"))
async def check_proxies_callback(event):
    # Legacy button → ask gate
    if not is_owner(event.sender_id):
        return await safe_callback_answer(event, f"{bs('Owner only command!')}", alert=True)
    await safe_callback_answer(event)
    uid = event.sender_id
    msg = await event.get_message()
    await styled_edit(msg, _proxy_gate_select_text(), buttons=_proxy_gate_kb("checkpxy", uid), emoji_ids=_proxy_gate_select_emojis())

# ====================== KEYS SYSTEM ======================
KEYS_USAGE_TEXT = f"""{PE} {bs('Usage:')}

{PE} <code>/keys [amount] [day or days]</code>


{PE} {bs('Or reply to a user by')} <code>/key [amount] [day or days]</code>

{PE} {bs('Supported formats:')}
{PE} <code>/key [amount] [day]</code>
{PE} <code>/keys [amount] [days]</code>


{PE} {bs('Max 1 key per user until plan expires.')}"""

KEYS_USAGE_EMOJIS = [
    5855207143724027916,
    4902715076873553054,
    4902715076873553054,
    5084974483685507801,
    4902715076873553054,
    4902715076873553054,
    5980995951160987855,
]


def _parse_key_args(raw_text: str):
    parts = (raw_text or "").split()
    if len(parts) < 3:
        return None, None
    try:
        amount = int(parts[1])
        days = int(parts[2])
    except (TypeError, ValueError):
        return None, None
    if amount < 1 or days < 1:
        return None, None
    return amount, days


def _format_keys_list_ui(title: str, keys: list, days: int | None = None):
    count = len(keys)
    plan_days = days
    if plan_days is None and keys:
        plan_days = 1
    plan_days = plan_days or 1
    day_label = "day" if plan_days == 1 else "days"
    lines = [
        f"{bs(title)} {PE}",
        UI_SEP,
        "",
        f"┣ {PE} {bs('Count')} ➜ {bs(str(count))}",
        f"┣ {PE} {bs('Plan')} ➜ {bs(f'{plan_days} {day_label} Plan')}",
        f"┣ {PE} {bs('Keys')}",
    ]
    emoji_ids = [
        5226656353744862682,
        5084974483685507801,
        5980995951160987855,
        5278622189556354905,
    ]
    for i, key in enumerate(keys):
        prefix = "┗" if i == len(keys) - 1 else "┣"
        lines.append(f"{prefix} <code>{html.escape(key)}</code>")
    lines.append("")
    lines.append(f"{PE} {bs('Users redeem with')} <code>/redeem [key]</code> {PE}")
    emoji_ids.extend([5172739056592749710, 5084974483685507801])
    return "\n".join(lines), emoji_ids


def format_key_claim_duration(expiry, days: int) -> str:
    if expiry:
        left = format_premium_time_left(expiry)
        if left.startswith("0d "):
            hours_part = left[3:].strip()
            if hours_part and hours_part != "0h":
                return hours_part
        if left.endswith(" 0h"):
            return left.replace(" 0h", "").strip()
        return left
    d = max(1, int(days or 1))
    if d == 1:
        return "24h"
    return f"{d}d"


def build_key_claimed_channel_text(uid, name, username, duration_label: str) -> str:
    return f"""{updates_channel_bracket_link()} {bs('Key Claimed')} {PE}
{UI_SEP}
{bs('User')} {ARROW} {user_link_html(uid, name, username)}
{bs('Duration')} {ARROW} {bval(duration_label)}
{UI_SEP}
{PE} {bs('Dev')} {ARROW} <a href='{DEV_LINK}'>{bs(DEV_NAME)}</a> {PE}"""


def get_key_claimed_channel_emoji_ids():
    return [KEY_CLAIMED_EMOJI, *get_dev_line_emojis()]


async def _generate_keys_flow(event, amount: int, days: int, assigned_to: int | None = None):
    if amount > MAX_KEYS_PER_GENERATE:
        amount = MAX_KEYS_PER_GENERATE
    keys = await create_keys(amount, days, created_by=event.sender_id, assigned_to=assigned_to)
    if not keys:
        return await styled_reply(event, f"{PE} {bs('Failed to generate keys')}", emoji_ids=[5042112436648281096])
    title = "Keys Generated"
    text, eids = _format_keys_list_ui(title, keys, days=days)
    log_user(
        event.sender_id,
        "KEYS_GENERATE",
        f"Count={len(keys)} | Days={days} | Assigned={assigned_to}",
    )
    await styled_reply(event, text, emoji_ids=eids)


@client.on(events.NewMessage(pattern=r'(?i)^[/.]keys\b'))
async def keys_cmd(event):
    if not is_owner(event.sender_id):
        return await send_owner_only_message(event)
    amount, days = _parse_key_args(event.raw_text)
    if amount is None:
        return await styled_reply(event, KEYS_USAGE_TEXT, emoji_ids=KEYS_USAGE_EMOJIS)
    await _generate_keys_flow(event, amount, days, assigned_to=None)


@client.on(events.NewMessage(pattern=r'(?i)^[/.]key\b'))
async def key_cmd(event):
    if not is_owner(event.sender_id):
        return await send_owner_only_message(event)
    amount, days = _parse_key_args(event.raw_text)
    if amount is None:
        return await styled_reply(event, KEYS_USAGE_TEXT, emoji_ids=KEYS_USAGE_EMOJIS)
    assigned_to = None
    if event.is_reply:
        try:
            rm = await event.get_reply_message()
            if rm and rm.sender_id:
                assigned_to = int(rm.sender_id)
        except Exception:
            assigned_to = None
    # /key is for assigning to a replied user; without reply behave like single/open key gen
    await _generate_keys_flow(event, amount, days, assigned_to=assigned_to)


@client.on(events.NewMessage(pattern=r'(?i)^[/.]rem$'))
async def rem_keys_cmd(event):
    if not is_owner(event.sender_id):
        return await send_owner_only_message(event)
    await expire_stale_unused_keys()
    remaining = await get_remaining_keys(limit=500)
    if not remaining:
        return await styled_reply(
            event,
            f"{PE} {bs('No remaining keys')}\n{PE} {bs('Generate with')} <code>/keys [amount] [days]</code>",
            emoji_ids=[5042112436648281096, 4902715076873553054],
        )
    # Group remaining keys by plan days and show each batch
    grouped = {}
    for k in remaining:
        d = int(k.get("days") or 1)
        grouped.setdefault(d, []).append(k.get("key"))
    for days_val in sorted(grouped.keys()):
        codes = [c for c in grouped[days_val] if c]
        if not codes:
            continue
        text, eids = _format_keys_list_ui("Remaining Keys", codes, days=days_val)
        await styled_reply(event, text, emoji_ids=eids)


async def _revoke_user_key_plan(target_uid: int, by_uid: int):
    """Downgrade one paid user to Trial and DM plan-expired notice. Returns result dict or None."""
    await ensure_user(target_uid)
    current_plan = await get_user_plan(target_uid)
    if not is_paid_plan(current_plan):
        return None
    await set_user_plan(target_uid, FREE_PLAN, 0)
    log_user(target_uid, "RKEY_REVOKE", f"Revoked={current_plan} | By={by_uid}")
    dm_sent = False
    try:
        await _send_plan_expired_notice(target_uid)
        dm_sent = True
    except Exception as e:
        log_user(target_uid, "RKEY_DM_ERR", f"Error={e}", "error")
    name, username, _, _ = await get_user_info(target_uid)
    return {
        "uid": target_uid,
        "user_link": user_link_html(target_uid, name, username),
        "previous": current_plan,
        "dm_sent": dm_sent,
    }


@client.on(events.NewMessage(pattern=r'(?i)^[/.]redeem\b'))
async def redeem_cmd(event):
    if await check_maintenance(event):
        return
    if not await force_join_check(event):
        return
    if await is_banned_user(event.sender_id):
        t, e = banned_user_message()
        return await styled_reply(event, t, emoji_ids=e)
    await ensure_user(event.sender_id)
    parts = event.raw_text.split(maxsplit=1)
    if len(parts) < 2 or not parts[1].strip():
        return await styled_reply(
            event,
            f"{PE} {bs('Usage:')}\n{PE} <code>/redeem [key]</code>",
            emoji_ids=[5855207143724027916, 4902715076873553054],
        )
    key_code = parts[1].strip().split()[0]
    result = await redeem_key(key_code, event.sender_id)
    err = result.get("error")
    if err == "already_redeemed":
        return await styled_reply(
            event,
            f"{PE} {bs('Redemption Failed!')}\n\n{PE} {bs('Key already redeemed')}",
            emoji_ids=[5042112436648281096, 5855207143724027916],
        )
    if err == "expired":
        return await styled_reply(
            event,
            f"{PE} {bs('Redemption Failed!')}\n\n{PE} {bs('Key expired. Contact')} {OWNER_CONTACT}.",
            emoji_ids=[5042112436648281096, 5855207143724027916],
        )
    if err == "not_yours":
        return await styled_reply(
            event,
            f"{PE} {bs('Not Your Key!')}\n\n"
            f"{PE} {bs('Contact the owner')} {OWNER_CONTACT} {bs('to get a key before checking.')}",
            emoji_ids=[5042112436648281096, 4902715076873553054],
        )
    if err == "already_premium":
        expiry = await get_user_expiry(event.sender_id)
        left = format_premium_time_left(expiry)
        return await styled_reply(
            event,
            f"{PE} {bs('You already have premium!')}\n\n"
            f"{PE} {bs('Plan:')} {bs(left)}\n"
            f"{PE} {bs('You cannot redeem another key while premium is active.')}",
            emoji_ids=[5042112436648281096, 5084974483685507801, 5855207143724027916],
        )
    if err or not result.get("ok"):
        return await styled_reply(
            event,
            f"{PE} {bs('Redemption Failed!')}\n\n{PE} {bs('Invalid key')}",
            emoji_ids=[5042112436648281096, 5855207143724027916],
        )

    days = int(result.get("days") or 1)
    log_user(event.sender_id, "KEY_REDEEM", f"Key={key_code} | Days={days}")
    name, username, tag, prof = await get_user_info(event.sender_id)
    expiry = await get_user_expiry(event.sender_id)
    duration_label = format_key_claim_duration(expiry, days)
    success_text = build_key_claimed_channel_text(event.sender_id, name, username, duration_label)
    success_emojis = get_key_claimed_channel_emoji_ids()
    await styled_reply(event, success_text, emoji_ids=success_emojis)
    if event.chat_id != event.sender_id:
        try:
            await styled_send(event.sender_id, success_text, emoji_ids=success_emojis)
        except Exception:
            pass
    try:
        await styled_send(LOG_CHANNEL_ID, success_text, emoji_ids=success_emojis)
    except Exception as e:
        log_system("KEY_REDEEM_CHANNEL_ERR", str(e), "error")


# ====================== ADMIN ======================
_BROADCAST_BLOCKED_ERRORS = (
    UserIsBlockedError,
    UserDeactivatedError,
    UserDeactivatedBanError,
    InputUserDeactivatedError,
)
_BROADCAST_BAD_ERRORS = (
    PeerIdInvalidError,
    ChatWriteForbiddenError,
    ChannelPrivateError,
)
_BROADCAST_EMOJI = {
    "megaphone": 5258500422393415126,
    "users": 5316992572680320646,
    "sent": 5316827280863934685,
    "blocked": 5316583502815181482,
    "chart": 5316832430529722441,
    "done": 5319248624511631572,
}
_BROADCAST_STATUS_IDS = [
    _BROADCAST_EMOJI["megaphone"],
    _BROADCAST_EMOJI["users"],
    _BROADCAST_EMOJI["sent"],
    _BROADCAST_EMOJI["blocked"],
]
_BROADCAST_PROGRESS_IDS = _BROADCAST_STATUS_IDS + [_BROADCAST_EMOJI["chart"]]
_BROADCAST_DONE_IDS = [
    _BROADCAST_EMOJI["done"],
    _BROADCAST_EMOJI["users"],
    _BROADCAST_EMOJI["sent"],
    _BROADCAST_EMOJI["blocked"],
]


def _broadcast_started_text(total_users):
    return (
        f"{PE} Broadcast started\n\n"
        f"{PE} Total users: {total_users}\n"
        f"{PE} Sent: 0\n"
        f"{PE} Blocked: 0\n"
        f"⚠️ Errors: 0"
    )


def _broadcast_progress_text(total, sent, blocked, errors, index):
    return (
        f"{PE} Broadcasting...\n\n"
        f"{PE} Total: {total}\n"
        f"{PE} Sent: {sent}\n"
        f"{PE} Blocked: {blocked}\n"
        f"⚠️ Errors: {errors}\n\n"
        f"{PE} Progress: {index}/{total}"
    )


def _broadcast_done_text(total, sent, blocked, errors):
    return (
        f"{PE} Broadcast completed\n\n"
        f"{PE} Total: {total}\n"
        f"{PE} Sent: {sent}\n"
        f"{PE} Blocked: {blocked}\n"
        f"⚠️ Errors: {errors}"
    )


async def _reply_broadcast_msg(event, text, emoji_ids=None):
    body, entities = build_entities(text, emoji_ids)
    return await event.reply(body, formatting_entities=entities)


async def _edit_broadcast_msg(msg, text, emoji_ids=None):
    try:
        body, entities = build_entities(text, emoji_ids)
        await msg.edit(body, formatting_entities=entities)
    except Exception:
        pass


async def _send_broadcast_payload(user_id, message):
    while True:
        try:
            async with _TG_RATE:
                if isinstance(message, str):
                    await client.send_message(user_id, message, link_preview=False)
                else:
                    await client.send_message(
                        user_id,
                        message.message or '',
                        file=message.media,
                        formatting_entities=message.entities,
                        buttons=message.buttons,
                        link_preview=False,
                    )
            return
        except FloodWaitError as e:
            await asyncio.sleep(e.seconds + 1)


async def _broadcast_worker(status_msg, user_ids, message):
    global broadcast_task
    sent = blocked = errors = 0
    total = len(user_ids)
    last_update = 0

    # Also send the same payload to group only (not Logs/Hits channels)
    for chat_id in _broadcast_user_chats():
        try:
            await _send_broadcast_payload(chat_id, message)
        except Exception as e:
            log_system("BROADCAST_CHAT_ERR", f"Chat={chat_id} Error={e}", "warning")
        await asyncio.sleep(BROADCAST_SLEEP_TIME)

    for index, user_id in enumerate(user_ids, start=1):
        try:
            await _send_broadcast_payload(user_id, message)
            sent += 1
        except _BROADCAST_BLOCKED_ERRORS:
            blocked += 1
        except _BROADCAST_BAD_ERRORS:
            errors += 1
        except Exception as e:
            log_system("BROADCAST_ERR", f"User={user_id} Error={e}", "warning")
            errors += 1

        await asyncio.sleep(BROADCAST_SLEEP_TIME)

        if index - last_update >= BROADCAST_PROGRESS_EVERY or index == total:
            last_update = index
            await _edit_broadcast_msg(
                status_msg,
                _broadcast_progress_text(total, sent, blocked, errors, index),
                _BROADCAST_PROGRESS_IDS,
            )

    await _edit_broadcast_msg(
        status_msg,
        _broadcast_done_text(total, sent, blocked, errors),
        _BROADCAST_DONE_IDS,
    )

    log_system("BROADCAST_DONE", f"Total={total} Sent={sent} Blocked={blocked} Errors={errors}")
    broadcast_task = None


@client.on(events.NewMessage(pattern=r'(?i)^[/.]broad\b'))
async def broad_cmd(event):
    global broadcast_task

    if event.sender_id not in ADMIN_ID:
        return

    if broadcast_task and not broadcast_task.done():
        return await event.reply("⚠️ A broadcast is already running.")

    message = None
    text = re.sub(r'^[/.]broad\s*', '', event.raw_text, flags=re.IGNORECASE).strip()
    if text:
        message = text
    elif event.is_reply:
        message = await event.get_reply_message()

    if not message:
        return await event.reply(
            "❌ Usage:\n"
            "/broad <message>\n"
            "OR reply to a message with /broad"
        )

    user_ids = await get_all_user_ids()
    if not user_ids:
        return await event.reply("⚠️ No users found.")

    status_msg = await _reply_broadcast_msg(
        event,
        _broadcast_started_text(len(user_ids)),
        _BROADCAST_STATUS_IDS,
    )

    log_user(event.sender_id, "BROADCAST_START", f"Users={len(user_ids)}")
    broadcast_task = asyncio.create_task(
        _broadcast_worker(status_msg, user_ids, message)
    )


@client.on(events.NewMessage(pattern=r'(?i)^[/.](maintenance|maintance)$'))
async def maint_cmd(event):
    if event.sender_id not in ADMIN_ID:
        return
    kb = [
        [pbtn(bs("Global Bot"), "mt:global", color="blue")],
        [pbtn(bs("Single Gates ➡️"), "mt_cat:single", color="blue"), pbtn(bs("Mass Gates ➡️"), "mt_cat:mass", color="blue")],
    ]
    global_status = "ON" if await get_maintenance_mode() else "OFF"
    text = f"""{bs('Bot Maintenance')}
{UI_SEP}
{bs('Global Bot')} ➔ <code>{global_status}</code>
{UI_SEP}
{bs('Select a category below to configure maintenance:')}"""
    await styled_reply(event, text, buttons=kb)


@client.on(events.CallbackQuery(pattern=rb"mt_cat:single"))
async def maint_single_cat_cb(event):
    if event.sender_id not in ADMIN_ID:
        return await event.answer("Not allowed", alert=True)
    await event.answer()
    kb = [
        [pbtn(bs("Shopify"), "mt:sp", color="blue")],
        [pbtn(bs("VBV Lookup"), "mt:vbv", color="blue")],
        [pbtn(f"« {bs('Back')}", "mt_back", color="red")],
    ]
    single_gates = {"sp": "Shopify", "vbv": "VBV Lookup"}
    lines = []
    for gk, gn in single_gates.items():
        st = "ON" if _GATE_MAINT.get(gk, False) else "OFF"
        lines.append(f"{bs(gn)} ➔ <code>{st}</code>")
    status_text = "\n".join(lines)
    text = f"""{bs('Single Gates Maintenance')}
{UI_SEP}
{status_text}
{UI_SEP}
{bs('Select a gate to configure:')}"""
    try:
        await event.edit(text, parse_mode='html', buttons=kb)
    except Exception:
        pass


@client.on(events.CallbackQuery(pattern=rb"mt_cat:mass"))
async def maint_mass_cat_cb(event):
    if event.sender_id not in ADMIN_ID:
        return await event.answer("Not allowed", alert=True)
    await event.answer()
    kb = [
        [pbtn(bs("Mass Shopify"), "mt:msp", color="blue")],
        [pbtn(bs("All Mass"), "mt:mass", color="blue")],
        [pbtn(f"« {bs('Back')}", "mt_back", color="red")],
    ]
    mass_gates = {
        "msp": "Mass Shopify",        "mass": "All Mass",
    }
    lines = []
    for gk, gn in mass_gates.items():
        st = "ON" if _GATE_MAINT.get(gk, False) else "OFF"
        lines.append(f"{bs(gn)} ➔ <code>{st}</code>")
    status_text = "\n".join(lines)
    text = f"""{bs('Mass Gates Maintenance')}
{UI_SEP}
{status_text}
{UI_SEP}
{bs('Select a mass gate to configure:')}"""
    try:
        await event.edit(text, parse_mode='html', buttons=kb)
    except Exception:
        pass


@client.on(events.CallbackQuery(pattern=rb"mt_back"))
async def maint_back_cb(event):
    if event.sender_id not in ADMIN_ID:
        return await event.answer("Not allowed", alert=True)
    await event.answer()
    kb = [
        [pbtn(bs("Global Bot"), "mt:global", color="blue")],
        [pbtn(bs("Single Gates ➡️"), "mt_cat:single", color="blue"), pbtn(bs("Mass Gates ➡️"), "mt_cat:mass", color="blue")],
    ]
    global_status = "ON" if await get_maintenance_mode() else "OFF"
    text = f"""{bs('Bot Maintenance')}
{UI_SEP}
{bs('Global Bot')} ➔ <code>{global_status}</code>
{UI_SEP}
{bs('Select a category below to configure maintenance:')}"""
    try:
        await event.edit(text, parse_mode='html', buttons=kb)
    except Exception:
        pass


@client.on(events.CallbackQuery(pattern=rb"mt:(.+)"))
async def maint_gate_cb(event):
    if event.sender_id not in ADMIN_ID:
        return await event.answer("Not allowed", alert=True)
    gate = event.pattern_match.group(1).decode()
    await event.answer()
    kb = [
        [pbtn(bs("ON"), f"mts:{gate}:on", color="blue"), pbtn(bs("OFF"), f"mts:{gate}:off", color="blue")],
        [pbtn(f"« {bs('Back')}", "mt_back", color="red")],
    ]
    if gate == "all":
        gname = "All Gates"
    elif gate == "global":
        gname = "Global Bot"
    else:
        gname = _MAINT_GATE_NAMES.get(gate, gate)

    if gate == "global":
        cur = "ON" if await get_maintenance_mode() else "OFF"
    else:
        cur = "ON" if _GATE_MAINT.get(gate, False) else "OFF"

    text, entities = build_entities(f"{bs(gname)}\n{bs('Current')} ➔ <code>{cur}</code>\n{UI_SEP}\n{bs('Set maintenance:')}")
    try:
        await event.edit(text, formatting_entities=entities, buttons=kb)
    except Exception:
        pass


@client.on(events.CallbackQuery(pattern=rb"mts:(.+):(on|off)"))
async def maint_set_cb(event):
    if event.sender_id not in ADMIN_ID:
        return await event.answer("Not allowed", alert=True)
    gate = event.pattern_match.group(1).decode()
    state = event.pattern_match.group(2).decode() == "on"
    await event.answer()
    if gate == "global":
        await set_maintenance_mode(state)
        gname = "Global Bot"
    elif gate == "all":
        for gk in _MAINT_GATE_NAMES:
            _GATE_MAINT[gk] = state
        gname = "All Gates"
        await save_maintenance_config()
    else:
        _GATE_MAINT[gate] = state
        gname = _MAINT_GATE_NAMES.get(gate, gate)
        await save_maintenance_config()
    st_text = "ON" if state else "OFF"
    log_system("GATE_MAINT", f"Gate={gname} | Set={st_text} | By={event.sender_id}")
    try:
        await _announce_maintenance_change(gate, state)
    except Exception as e:
        log_system("MAINT_ANNOUNCE_FAIL", f"Gate={gate} Error={e}", "error")

    # Back target depending on category
    back_target = "mt_back"
    if gate in ["sp", "vbv"]:
        back_target = "mt_cat:single"
    elif gate in ["msp", "mass"]:
        back_target = "mt_cat:mass"
        
    kb = [[pbtn(f"« {bs('Back')}", back_target, color="red")]]
    text, entities = build_entities(f"{bs(gname)} ➔ {bs('Maintenance')} <code>{st_text}</code>")
    try:
        await event.edit(text, formatting_entities=entities, buttons=kb)
    except Exception:
        pass


# ====================== PLAN ======================
async def _handle_plan_assign(event, plan_key):
    if event.sender_id not in ADMIN_ID:
        return
    parts = event.raw_text.split()
    if len(parts) < 2:
        return await styled_reply(event, f"{PE} <code>/{plan_key} user_id</code>", emoji_ids=[CE["warn"]])
    try:
        target_uid = int(parts[1])
    except ValueError:
        return await styled_reply(event, f"{PE} {bs('Invalid user ID')}", emoji_ids=[CE["cross"]])
    pi = PLANS[plan_key]
    target_name, target_username = "Unknown", None
    try:
        target_entity = await client_instance.get_entity(target_uid)
        target_username = getattr(target_entity, 'username', None)
        target_name = getattr(target_entity, 'first_name', None) or (f"@{target_username}" if target_username else "Unknown")
    except Exception:
        pass
    await ensure_user(target_uid, name=target_name, username=target_username)
    current_plan = await get_user_plan(target_uid)
    is_upgrade = is_paid_plan(current_plan)
    await set_user_plan(target_uid, pi["tier"], pi["duration_days"])
    expiry_date = (datetime.now() + timedelta(days=pi["duration_days"])).strftime('%Y-%m-%d %H:%M:%S')
    log_user(target_uid, "PLAN_SET", f"Plan={pi['tier']} | Duration={pi['duration_days']}d | By={event.sender_id} | Previous={current_plan} | Expiry={expiry_date}")
    await styled_reply(event, f"""✓ {bs('Plan Updated')}

<a href='{DEV_LINK}'>⊀</a> {bs('User')} ↬ {user_link_html(target_uid, target_name, target_username)}
<a href='{DEV_LINK}'>⊀</a> {bs('Plan')} ↬ {pi['emoji']} {pi['name']}
<a href='{DEV_LINK}'>⊀</a> {bs('Tier')} ↬ <code>{pi['tier']}</code>
<a href='{DEV_LINK}'>⊀</a> {bs('Duration')} ↬ <code>{pi['duration_days']} days</code>
<a href='{DEV_LINK}'>⊀</a> {bs('Expires')} ↬ <code>{expiry_date}</code>
<a href='{DEV_LINK}'>⌬</a> {bs('Dev')} ↬ <a href='{DEV_LINK}'>{bs(DEV_NAME)}</a>""")
    try:
        await styled_send(target_uid, f"""🎉 {bs('Congratulations!')} 🎉

<a href='{DEV_LINK}'>⊀</a> {bs('Your Plan Has Been Upgraded')}
<a href='{DEV_LINK}'>⊀</a> {bs('Plan')} ↬ {pi['emoji']} {pi['name']}
<a href='{DEV_LINK}'>⊀</a> {bs('Tier')} ↬ <code>{pi['tier']}</code>
<a href='{DEV_LINK}'>⊀</a> {bs('Duration')} ↬ <code>{pi['duration_days']} days</code>
<a href='{DEV_LINK}'>⊀</a> {bs('Expires')} ↬ <code>{expiry_date}</code>

<a href='{DEV_LINK}'>ℭ</a> {bs('Benefits')} {ARROW} {bs('Mass check unlocked')}
<a href='{DEV_LINK}'>ℭ</a> {bs('Limit')} {ARROW} {bs(str(get_cc_limit(pi['tier'])))} {bs('CCs')}

<a href='{DEV_LINK}'>⌬</a> {bs('Thank you for choosing our service!')}
<a href='{DEV_LINK}'>⌬</a> {bs('Dev')} ↬ <a href='{DEV_LINK}'>{bs(DEV_NAME)}</a>""")
    except:
        pass
    try:
        random_suffix = ''.join(random.choices(string.ascii_uppercase + string.digits, k=8))
        masked = f"{random_suffix[:2]}XXXX{random_suffix[-2:]}"
        receipt_id = f"NOTHING-{masked}"
        log_title = f"{bs('Plan RENEWED')} 🔄" if is_upgrade else f"{bs('New Plan Purchase')} 🛒"
        log_msg = f"""{log_title}
<a href='{DEV_LINK}'>⊀</a> {bs('User')} ↬ {user_link_html(target_uid, target_name, target_username)}
<a href='{DEV_LINK}'>⊀</a> {bs('Plan')} ↬ {pi['emoji']}{pi['name']}
<a href='{DEV_LINK}'>ℭ</a> {bs('Price')} ↬ <code>{pi['price']}</code>
<a href='{DEV_LINK}'>ℭ</a> {bs('Receipt')} ↬ <code>{receipt_id}</code>
<a href='{DEV_LINK}'>⌬</a> {bs('Dev')} ↬ <a href='{DEV_LINK}'>{bs(DEV_NAME)}</a>"""
        await styled_send(LOG_CHANNEL_ID, log_msg)
    except:
        pass


@client.on(events.NewMessage(pattern=r'(?i)^[/.]plan1\b'))
async def plan1_cmd(event):
    await _handle_plan_assign(event, "plan1")


@client.on(events.NewMessage(pattern=r'(?i)^[/.]plan2\b'))
async def plan2_cmd(event):
    await _handle_plan_assign(event, "plan2")


@client.on(events.NewMessage(pattern=r'(?i)^[/.]plan3\b'))
async def plan3_cmd(event):
    await _handle_plan_assign(event, "plan3")


@client.on(events.NewMessage(pattern=r'(?i)^[/.]plan4\b'))
async def plan4_cmd(event):
    await _handle_plan_assign(event, "plan4")


@client.on(events.NewMessage(pattern=r'(?i)^[/.]addcr\b'))
async def addcr_cmd(event):
    if event.sender_id not in ADMIN_ID:
        return
    parts = event.raw_text.split()
    if len(parts) < 3:
        return await styled_reply(event, f"{PE} <code>/addcr user_id amount</code>", emoji_ids=[CE["warn"]])
    try:
        target_uid = int(parts[1])
        amount = int(parts[2])
    except ValueError:
        return await styled_reply(event, f"{PE} {bs('Invalid user ID or amount')}", emoji_ids=[CE["cross"]])
    target_name, target_username = "Unknown", None
    try:
        target_entity = await client_instance.get_entity(target_uid)
        target_username = getattr(target_entity, 'username', None)
        target_name = getattr(target_entity, 'first_name', None) or (f"@{target_username}" if target_username else "Unknown")
    except Exception:
        pass
    await ensure_user(target_uid, name=target_name, username=target_username)
    await add_user_credits(target_uid, amount)
    log_user(target_uid, "CREDITS_ADD", f"Amount=+{amount} | NewBalance={new_balance} | By={event.sender_id}")
    cr_msg = f"""{bs('Credits Added!')} {PE}
 {bs('User')} \u21ac {user_link_html(target_uid, target_name, target_username)}
 {bs('Credits Added')} \u21ac +{amount}
 {bs('Total Credits')} \u21ac {new_balance}"""
    cr_kb = [[pbtn(bs("Support"), url="{DEV_LINK}", color="green")]]
    cr_ei = [CE["addtick"]]
    await styled_reply(event, cr_msg, buttons=cr_kb, emoji_ids=cr_ei)
    try:
        await styled_send(target_uid, cr_msg, buttons=cr_kb, emoji_ids=cr_ei)
    except Exception:
        pass



@client.on(events.NewMessage(pattern=r'(?i)^[/.]rkey\b'))
async def rkey_cmd(event):
    if await check_maintenance(event):
        return
    if not await force_join_check(event):
        return
    if not is_owner(event.sender_id):
        return await send_owner_only_message(event)
    if await is_banned_user(event.sender_id):
        t, e = banned_user_message()
        return await styled_reply(event, t, emoji_ids=e)

    parts = event.raw_text.split()
    if len(parts) < 2:
        return await styled_reply(
            event,
            f"{PE} {bs('Usage')}\n"
            f"<code>/rkey [user_id]</code> {bs('— revoke one user')}\n"
            f"<code>/rkey all</code> {bs('— revoke all active key plans')}",
            emoji_ids=[5855207143724027916],
        )

    arg = parts[1].strip().lower()
    if arg == "all":
        revoked_keys_count = await revoke_all_unused_keys()
        active_users = await get_active_key_plan_users()
        if not active_users:
            return await styled_reply(
                event,
                f"{PE} {bs('No active key-plan users found.')}\n{PE} {bs('Unused keys revoked:')} <code>{revoked_keys_count}</code>",
                emoji_ids=[5042112436648281096, 4902715076873553054],
            )

        status_msg = await styled_reply(
            event,
            f"⭐ {bs(f'Revoking {len(active_users)} Key Users...')}\n⭐ {bs('Please wait...')}",
            emoji_ids=[5325834523068342417, 5215327832040811010],
        )

        revoked_results = []
        for user_data in active_users:
            uid = int(user_data.get("user_id"))
            result = await _revoke_user_key_plan(uid, event.sender_id)
            if result:
                revoked_results.append(result)
            await asyncio.sleep(0.15)

        log_user(
            event.sender_id,
            "RKEY_ALL",
            f"Users={len(revoked_results)} | UnusedKeysRevoked={revoked_keys_count}",
        )

        if status_msg:
            try:
                await status_msg.delete()
            except Exception:
                pass

        header = (
            f"⭐ {bs('Revoke Complete!')} {PE}\n"
            f"{UI_SEP}\n"
            f"⭐ {bs('Revoked Key Users')} {ARROW} {bval(len(revoked_results))}\n"
            f"⭐ {bs('Unused Keys Revoked')} {ARROW} {bval(revoked_keys_count)}\n"
            f"{UI_SEP}\n"
        )
        lines = []
        for idx, r in enumerate(revoked_results, start=1):
            dm_flag = "✓ DM" if r["dm_sent"] else "❌ DM"
            lines.append(f"{idx}. {r['user_link']} {ARROW} {bs(r['previous'])} [{dm_flag}]")

        summary_text = header + "\n".join(lines)
        summary_emojis = [5278622189556354905, 5084974483685507801, 5172739056592749710, 4902715076873553054]

        if len(summary_text) <= 3900:
            await styled_reply(event, summary_text, emoji_ids=summary_emojis)
        else:
            chunk_lines = []
            curr_len = len(header)
            for line in lines:
                if curr_len + len(line) + 1 > 3800:
                    await styled_reply(event, header + "\n".join(chunk_lines), emoji_ids=summary_emojis)
                    chunk_lines = [line]
                    curr_len = len(header) + len(line)
                else:
                    chunk_lines.append(line)
                    curr_len += len(line) + 1
            if chunk_lines:
                await styled_reply(event, header + "\n".join(chunk_lines), emoji_ids=summary_emojis)
        return

    try:
        target_uid = int(parts[1])
    except ValueError:
        return await styled_reply(
            event,
            f"{PE} {bs('Usage')}\n"
            f"<code>/rkey [user_id]</code> {bs('— revoke one user')}\n"
            f"<code>/rkey all</code> {bs('— revoke all active key plans')}",
            emoji_ids=[5855207143724027916],
        )

    result = await _revoke_user_key_plan(target_uid, event.sender_id)
    if not result:
        return await styled_reply(
            event,
            f"{PE} {bs('User has no active plan')}",
            emoji_ids=[5042112436648281096],
        )

    await styled_reply(
        event,
        f"{PE} {bs('Plan Revoked')}\n"
        f"{PE} {bs('User')} {ARROW} <code>{target_uid}</code>\n"
        f"{PE} {bs('Previous')} {ARROW} {bs(result['previous'])}\n"
        f"{PE} {bs('DM')} {ARROW} {bs('Sent' if result['dm_sent'] else 'Failed')}",
        emoji_ids=[
            5278622189556354905,
            5084974483685507801,
            5980995951160987855,
            4902715076873553054,
        ],
    )


@client.on(events.NewMessage(pattern=r'(?i)^[/.]rplan\b'))
async def rplan_cmd(event):
    if event.sender_id not in ADMIN_ID:
        return
    parts = event.raw_text.split()
    if len(parts) < 2:
        return await styled_reply(event, f"{PE} <code>/rplan user_id</code>", emoji_ids=[CE["warn"]])
    try:
        target_uid = int(parts[1])
    except ValueError:
        return await styled_reply(event, f"{PE} {bs('Invalid user ID')}", emoji_ids=[CE["cross"]])
    target_name, target_username = "Unknown", None
    try:
        target_entity = await client_instance.get_entity(target_uid)
        target_username = getattr(target_entity, 'username', None)
        target_name = getattr(target_entity, 'first_name', None) or (f"@{target_username}" if target_username else "Unknown")
    except Exception:
        pass
    await ensure_user(target_uid, name=target_name, username=target_username)
    current_plan = await get_user_plan(target_uid)
    if not is_paid_plan(current_plan):
        return await styled_reply(event, f"{PE} {bs('User has no active plan')}", emoji_ids=[CE["cross"]])
    plan_name = current_plan.upper()
    plan_emoji = "❔"
    for pi in PLANS.values():
        if pi["tier"].lower() == current_plan.lower():
            plan_name = pi["name"]
            plan_emoji = pi["emoji"]
            break
    await set_user_plan(target_uid, FREE_PLAN, 0)
    log_user(target_uid, "PLAN_REVOKE", f"Revoked={current_plan} | By={event.sender_id}")
    await styled_reply(event, f"""✓ {bs('Plan Revoked')}

<a href='{DEV_LINK}'>⊀</a> {bs('User')} ↬ {user_link_html(target_uid, target_name, target_username)}
<a href='{DEV_LINK}'>⊀</a> {bs('Previous Plan')} ↬ {plan_emoji} {plan_name} ({bs(current_plan)})
<a href='{DEV_LINK}'>⊀</a> {bs('New Plan')} ↬ <code>{bs(FREE_PLAN)}</code>
<a href='{DEV_LINK}'>⌬</a> {bs('Dev')} ↬ <a href='{DEV_LINK}'>{bs(DEV_NAME)}</a>""")
    try:
        await styled_send(target_uid, f"""ℹ️ {bs('Plan Status Update')}

<a href='{DEV_LINK}'>⊀</a> {bs('Hello')} {bs(target_name)},
<a href='{DEV_LINK}'>⊀</a> {bs('Your')} {plan_name} ({bs(current_plan)}) {bs('has been ended.')}

<a href='{DEV_LINK}'>ℭ</a> {bs('Current Status')} {ARROW} {bs(f'Reverted to {FREE_PLAN}')}

<a href='{DEV_LINK}'>⌬</a> {bs('To renew, contact')} <a href='{DEV_LINK}'>@rapewthyou</a>
<a href='{DEV_LINK}'>⌬</a> {bs('Dev')} ↬ <a href='{DEV_LINK}'>{bs(DEV_NAME)}</a>""")
    except:
        pass


@client.on(events.NewMessage(pattern=r'(?i)^[/.]planall$'))
async def planall_cmd(event):
    if event.sender_id not in ADMIN_ID:
        return
    await expire_due_plans()
    all_users = await get_active_premium_users()
    if not all_users:
        return await styled_reply(event, f"{PE} {bs('No active plans')}", emoji_ids=[CE["warn"]])
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    fn = f"active_plans_{ts}.txt"
    content = f"ACTIVE PLANS LIST\nGenerated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\nTotal: {len(all_users)}\n{'=' * 40}\n\n"
    for u in all_users:
        uid2 = u.get("user_id", "?")
        tier = u.get("plan", "?")
        expiry = u.get("expiry")
        exp_str = expiry.strftime('%Y-%m-%d %H:%M:%S') if expiry else "Never"
        emoji = "❔"
        pname = tier
        for pi in PLANS.values():
            if pi["tier"] == tier:
                emoji = pi["emoji"]
                pname = pi["name"]
                break
        try:
            ent = await client_instance.get_entity(uid2)
            uname = getattr(ent, 'first_name', None) or "Unknown"
        except:
            uname = "Unknown"
        content += f"User: {uname}\nID: {uid2}\nPlan: {emoji} {pname}\nTier: {tier}\nExpires: {exp_str}\n{'-' * 40}\n"
    async with aiofiles.open(fn, 'w', encoding='utf-8') as f:
        await f.write(content)
    try:
        await styled_send(event.chat_id, f"{bs('Active Plans')} ({bs(str(len(all_users)))}) {PE}", emoji_ids=[CE["fire"]], file=fn)
    except:
        pass
    try:
        os.remove(fn)
    except:
        pass


# ====================== HITS LEADERBOARD ======================
async def _feedback_leaderboard_reply(event, top, total, title, total_label):
    if not top:
        return await styled_reply(event, f"{PE} {bs(f'No {title.lower()} yet')}", emoji_ids=[CE["warn"]])
    lines = []
    for i, u in enumerate(top, 1):
        uid = u.get("user_id", 0)
        count = u.get("feedbacks", 0)
        try:
            link, name, username = await get_user_link(uid)
            await ensure_user(uid, name=name, username=username)
        except Exception:
            name = u.get("name") or f"user_{uid}"
            username = u.get("username")
            link = user_link_html(uid, name, username)
        lines.append(f"{i}. {link} ➺ {count}")
    board = "\n".join(lines)
    FEEDBACK_EMOJI = 5436196151575459790
    await styled_reply(event, f""" {bs(title)}
{UI_SEP}
{board}
{UI_SEP}
{PE} {bs(total_label)} ➺ {total}
{UI_SEP}
{PE} {bs('Dev')} {ARROW} <a href='{DEV_LINK}'>{bs(DEV_NAME)}</a> {PE}""", emoji_ids=[FEEDBACK_EMOJI, *get_dev_line_emojis()])


@client.on(events.NewMessage(pattern=r'(?i)^[/.]f$'))
async def feedback_24h_cmd(event):
    if await check_maintenance(event):
        return
    if not await force_join_check(event):
        return
    since = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(hours=24)
    top = await get_top_feedbacks(10, since=since)
    total = await get_total_feedbacks(since=since)
    await _feedback_leaderboard_reply(event, top, total, "Feedback", "Total Feedback")


@client.on(events.NewMessage(pattern=r'(?i)^[/.]feed$'))
async def feedback_all_cmd(event):
    if await check_maintenance(event):
        return
    if not await force_join_check(event):
        return
    top = await get_top_feedbacks(10)
    total = await get_total_feedbacks()
    await _feedback_leaderboard_reply(event, top, total, "Feedback", "Total Feedback")


@client.on(events.NewMessage(pattern=r'(?i)^[/.]hits$'))
async def hits_cmd(event):
    if await check_maintenance(event):
        return
    if not await force_join_check(event):
        return
    top = await get_top_hits(10)
    total = await get_total_hits()
    if not top:
        return await styled_reply(event, f"{PE} {bs('No hits yet')}", emoji_ids=[CE["warn"]])
    lines = []
    for i, u in enumerate(top, 1):
        uid = u.get("user_id", 0)
        hits = u.get("hits", 0)
        try:
            link, name, username = await get_user_link(uid)
            await ensure_user(uid, name=name, username=username)
        except Exception:
            name = u.get("name") or f"user_{uid}"
            username = u.get("username")
            link = user_link_html(uid, name, username)
        lines.append(f"{i}. {link} ➺ {hits}")
    board = "\n".join(lines)
    HITS_EMOJI = 5359719332542718652
    await styled_reply(event, f""" {bs('Hits')}
{UI_SEP}
{board}
{UI_SEP}
{PE} {bs('Total Hits')} ➺ {total}
{UI_SEP}
{PE} {bs('Dev')} {ARROW} <a href='{DEV_LINK}'>{bs(DEV_NAME)}</a> {PE}""", emoji_ids=[HITS_EMOJI, *get_dev_line_emojis()])


@client.on(events.NewMessage(pattern=r'(?i)^[/.]stats$'))
async def stats_cmd(event):
    if await check_maintenance(event):
        return
    if not await force_join_check(event):
        return
    try:
        tc = await get_total_cards_count()
        ch = await get_charged_count()
        ap = await get_approved_count()
        dc = await get_declined_count()
        log_system("STATS", f"Checked={tc} | Charged={ch} | Approved={ap} | Declined={dc}")
        text = f"""{bs('Global Analytics')} {PE}
{UI_SEP}
{PE} {bs('Total Checked')} {ARROW} {bval(f'{tc:,}')}
{PE} {bs('Total Charged')} {ARROW} {bval(f'{ch:,}')}
{PE} {bs('Total Approved')} {ARROW} {bval(f'{ap:,}')}
{PE} {bs('Total Declined')} {ARROW} {bval(f'{dc:,}')}
{UI_SEP}
{PE} {bs('Dev')} {ARROW} <a href='{DEV_LINK}'>{bs(DEV_NAME)}</a> {PE}"""
        await styled_reply(event, text, emoji_ids=get_stats_emoji_ids())
    except Exception as e:
        await styled_reply(event, f"{PE} {bs('Error')} {ARROW} <code>{e}</code>", emoji_ids=[CE["cross"]])


# ====================== MAIN ======================
async def main():
    global client_instance
    client_instance = client
    log_system("BOOT", "Initializing database...")
    await init_db()
    try:
        seeded = 0
        for admin_id in ADMIN_ID:
            seeded = await seed_global_sites_from_user(admin_id)
            if seeded:
                break
        await count_global_sites()
    except Exception as e:
        log_system("BOOT", f"Shopify pool seed warning: {e}", "warning")
    await load_maintenance_config()
    await expire_due_plans()
    asyncio.create_task(_plan_expiry_worker())

    for _ in range(_BG_WORKERS_COUNT):
        asyncio.create_task(_bg_worker())

    while True:
        try:
            log_system("BOOT", "Starting bot client...")
            await client.start(bot_token=BOT_TOKEN)
            # Warm channel/group peers so styled_send does not miss access hashes
            for _cid in (LOGS_CHANNEL_ID, HITS_CHANNEL_ID, JOIN_GROUP_ID, HIT_CHANNEL_ID, LOG_CHANNEL_ID):
                try:
                    await _resolve_send_peer(_cid)
                except Exception:
                    pass
            log_system("BOOT", "✓ Bot Started!")
            await client.run_until_disconnected()
        except FloodWaitError as e:
            log_system("FLOOD", f"Sleeping={e.seconds + 5}s", "warning")
            await asyncio.sleep(e.seconds + 5)
        except Exception as e:
            log_system("CRASH", f"{e}", "error")
            await asyncio.sleep(10)


if __name__ == "__main__":
    try:
        import uvloop
        uvloop.install()
    except ImportError:
        pass
    asyncio.run(main())
