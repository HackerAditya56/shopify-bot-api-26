import logging
import asyncio
import time
import html
import psycopg2
from psycopg2.extras import RealDictCursor
from datetime import datetime
from typing import Dict, Any, Optional

from aiogram import Bot, Dispatcher, types, F, Router, BaseMiddleware
from aiogram.enums import ParseMode
from aiogram.client.default import DefaultBotProperties
from aiogram.filters import Command
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.storage.memory import MemoryStorage
from database import get_user, create_user, get_user_credits, update_credits, set_first_name, DB_CONFIG
from live_emoji import _ALIASES as _PLAN_ALIASES, _LOOKUP as _PLAN_LOOKUP
import privacy
import gifs
from gate import (
    on_command, off_command, onall_command, offall_command,
    gates_command, gif_command, offgif_command,
)
from fb import router as fb_router, start_cleanup_tasks, setup_feedback_handler, feedback_cmd
from stats import stats_command
from tools.binn import binn_command
from tools.gen import gen_command, genhelp_command, regenerate_cards_callback
from cmds import router as cmds_router, cmds_command
from broad import broad_command, router as broad_router
from ban import ban_command, unban_command, BanMiddleware, router as ban_router
from status import status_command, router as status_router
from sub import (
    auth_command, rc_command, authall_command, gen_code_command,
    claim_command, info_command, rauth_command, plan_command,
    adcr_command, get_premium_status, key_command,
    premium_expiry_worker,
    me_command, all_command,                        # ← lifetime stats
)
from proxy import (
    proxy_command, checkproxy_command, clearproxy_command, myproxy_command,
    gproxyadd_command, gproxyclear_command, gproxyreload_command,
    gproxyinfo_command, gproxyexport_command,
    global_proxy_manager,
)

from gates.st import st_command
from gates.sh import sh_command, sh_callback_handler
from gates.sp import sp_command
from gates.pg import pg_command
from gates.hc import hc_command
from gates.pf import pf_command
from gates.vbv import vbv_command
from gates.ft import ft_command
from gates.bl import bl_command
from gates.pp import pp_command
from gates.at import at_command
from gates.pw import pw_command
from gates.rz import rz_command
from gates.pyu import pyu_command
from gates.py import py_command
from gates.chk import chk_command
from gates.ch import ch_command
from gates.sk import sk_command
from gates.b3 import b3_command
from gates.nmi import nmi_command
from gates.nmi2 import nmi2_command
from gates.cl import cl_command
from autohitters.stco import stco_command, stco_callback_handler
from autohitters.whop import router as whop_router, whop_command, whop_callback_handler
from autohitters.jio import router as jio_router, jio_command, jio_callback_handler
from autohitters.mpin import router as mpin_router

from mass_gates.msh import (
    router as msh_router, MshStopCallback, MshResultCallback,
    handle_stop_callback as msh_stop_handler,
    handle_result_callback as msh_result_handler,
)
from mass_gates.mpp import (
    router as mpp_router, MppStopCallback, MppResultCallback,
    handle_stop_callback as mpp_stop_handler,
    handle_result_callback as mpp_result_handler,
)
from mass_gates.mrz import (
    router as mrz_router, MrzStopCallback, MrzResultCallback,
    handle_stop_callback as mrz_stop_handler,
    handle_result_callback as mrz_result_handler,
    mrz_command
)
from mass_gates.mchk import (
    router as mchk_router, MchkStopCallback, MchkResultCallback,
    handle_stop_callback as mchk_stop_handler,
    handle_result_callback as mchk_result_handler,
)
from mass_gates.msk import (
    router as msk_router, MskStopCallback, MskResultCallback,
    handle_stop_callback as msk_stop_handler,
    handle_result_callback as msk_result_handler,
    msk_command,
)
from mass_gates.mst import (
    router as mst_router, MstStopCallback, MstResultCallback,
    handle_stop_callback as mst_stop_handler,
    handle_result_callback as mst_result_handler,
    mst_command
)
from mass_gates.sitechk import (
    checksite_command, seturl_command, siteall_command,
    removeall_command, dedupe_command, proxyinfo_command, resetproxy_command
)

import payments as pay_sys

from backup import daily_backup_scheduler

# ── Scraper ──────────────────────────────────────────────────────────────────
from scr import router as scr_router, scr_command, initialize_pyrogram, stop_pyrogram


# ── Card Cleaner / Splitter / Shuffler ────────────────────────────────────────
from split import (
    router as split_router,
    clean_command,
    split_command,
    shuffle_command,
    cancel_command,
)

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# BOT CONFIGURATION
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

BOT_TOKEN = "8817680595:AAFeJ7ts_5LXOmiHXLGsfFSHo9HmZlPP168"

START_IMAGE_URL     = "https://i.ibb.co/27F3HxbX/IMG-20260521-222337.jpg"
#BCcode full link
LOG_CHANNEL_ID      = -1003912886127
BOT_LINK            = "https://t.me/CHKXWZ_BOT"
REQUIRED_CHANNEL_ID = -1004453592223
REQUIRED_GROUP_ID   = -1004453592223
REQUIRED_GROUP2_ID  = -1004453592223
CHANNEL_LINK        = "https://t.me/+I3047b0vANk3NjRl"
GROUP_LINK          = "https://t.me/+I3047b0vANk3NjRl"
GROUP2_LINK         = "https://t.me/+I3047b0vANk3NjRl"
OWNER_LINK = "https://t.me/Enchanted_linux_0x"
JOIN_TEXT = (
    "<tg-emoji emoji-id=\"6174632717750115359\">❓</tg-emoji> <b>Aᴄᴄᴇss Rᴇsᴛʀɪᴄᴛᴇᴅ</b> "
    "<tg-emoji emoji-id=\"5116151848855667552\">🚫</tg-emoji>\n\n"
    "<tg-emoji emoji-id=\"6124902618574625426\">👑</tg-emoji> <b>Tᴏ Usᴇ Tʜɪs Bᴏᴛ Yᴏᴜ Mᴜsᴛ Bᴇ Nᴇᴇᴅ ᴛᴏ Jᴏɪɴ Oᴜʀ </b>"
    "<b>Cʜᴀɴɴᴇʟ & Gʀᴏᴜᴘ Cʜᴀᴛ.</b>\n\n"
    "<tg-emoji emoji-id=\"4904845878868575100\">😇</tg-emoji> <b>Cʟɪᴄᴋ Vᴇʀɪғʏ Aғᴛᴇʀ Jᴏɪɴɪɴɢ.</b>"
)

PRICING_TEXT = (
    '<tg-emoji emoji-id="5424976816530014958">👛</tg-emoji> <b>ᴀᴄᴄᴇꜱꜱ ➵ Sᴡɪꜰᴛ</b> '
    '<tg-emoji emoji-id="6253702009107516178">💎</tg-emoji>\n'
    '<tg-emoji emoji-id="6136246765369694911">🦇</tg-emoji> <b>ᴘƦɪᴄᴇ ➵</b> 𝟯$\n'
    '<tg-emoji emoji-id="6136246765369694911">🦇</tg-emoji> <b>ᴅᴜƦᴀᴛɪᴏɴ ➵</b> [𝟮 ᴅᴀʏꜱ]\n'
    '<tg-emoji emoji-id="6136246765369694911">🦇</tg-emoji> <b>ᴄƦᴇᴅɪᴛꜱ ➵</b> ∞\n'
    '━━━━━━━━━━━━━━━━\n'
    '<tg-emoji emoji-id="5424976816530014958">👛</tg-emoji> <b>ᴀᴄᴄᴇꜱꜱ ➵ TᴜƦʙᴏ</b> '
    '<tg-emoji emoji-id="6255712466118905093">⭐</tg-emoji>\n'
    '<tg-emoji emoji-id="6136246765369694911">🦇</tg-emoji> <b>ᴘƦɪᴄᴇ ➵</b> 𝟳$\n'
    '<tg-emoji emoji-id="6136246765369694911">🦇</tg-emoji> <b>ᴅᴜƦᴀᴛɪᴏɴ ➵</b> [𝟳 ᴅᴀʏꜱ]\n'
    '<tg-emoji emoji-id="6136246765369694911">🦇</tg-emoji> <b>ᴄƦᴇᴅɪᴛꜱ ➵</b> ∞\n'
    '━━━━━━━━━━━━━━━━\n'
    '<tg-emoji emoji-id="5424976816530014958">👛</tg-emoji> <b>ᴀᴄᴄᴇꜱꜱ ➵ NɪᴛʀƦᴏ</b> '
    '<tg-emoji emoji-id="6253702009107516178">⭐</tg-emoji>\n'
    '<tg-emoji emoji-id="6136246765369694911">🦇</tg-emoji> <b>ᴘƦɪᴄᴇ ➵</b> 𝟭𝟰$\n'
    '<tg-emoji emoji-id="6136246765369694911">🦇</tg-emoji> <b>ᴅᴜƦᴀᴛɪᴏɴ ➵</b> [𝟭𝟱 ᴅᴀʏꜱ]\n'
    '<tg-emoji emoji-id="6136246765369694911">🦇</tg-emoji> <b>ᴄƦᴇᴅɪᴛꜱ ➵</b> ∞\n'
    '━━━━━━━━━━━━━━━━\n'
    '<tg-emoji emoji-id="5424976816530014958">👛</tg-emoji> <b>ᴀᴄᴄᴇꜱꜱ ➵ Aᴘᴇx</b> '
    '<tg-emoji emoji-id="6255712466118905093">⚡</tg-emoji>\n'
    '<tg-emoji emoji-id="6136246765369694911">🦇</tg-emoji> <b>ᴘƦɪᴄᴇ ➵</b> 𝟮𝟱$\n'
    '<tg-emoji emoji-id="6136246765369694911">🦇</tg-emoji> <b>ᴅᴜƦᴀᴛɪᴏɴ ➵</b> [𝟯𝟬 ᴅᴀʏꜱ]\n'
    '<tg-emoji emoji-id="6136246765369694911">🦇</tg-emoji> <b>ᴄƦᴇᴅɪᴛꜱ ➵</b> ∞'
)

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)

# FSM storage must be passed to Dispatcher for split states to work
# GifToggleSession lets /offgif strip animation GIFs from every gate
# result UI at the transport layer, with no changes to the gate modules.
bot = Bot(
    token=BOT_TOKEN,
    session=gifs.build_session(),
    default=DefaultBotProperties(parse_mode=ParseMode.HTML),
)
dp  = Dispatcher(storage=MemoryStorage())


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Include Routers
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

dp.include_router(msh_router)
dp.include_router(mpp_router)
dp.include_router(mchk_router)
dp.include_router(msk_router)
dp.include_router(mst_router)
dp.include_router(mrz_router)
dp.include_router(cmds_router)
dp.include_router(fb_router)
dp.include_router(ban_router)
dp.include_router(broad_router)
dp.include_router(status_router)
dp.include_router(scr_router)      # ← Scraper router
dp.include_router(split_router)     # ← Card Cleaner / Splitter / Shuffler
dp.include_router(whop_router) # whop
dp.include_router(jio_router) # jio
dp.include_router(mpin_router) # magicpin hitter

router = Router()
dp.include_router(router)

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Custom Emoji IDs
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

EMOJI_LIGHTNING = "5085022089103016925"
EMOJI_BAT       = "6136246765369694911"
EMOJI_STAR      = "6136275172283391020"
EMOJI_TOP       = "5463071033256848094"
EMOJI_DIAMOND   = "5359719332542718652"
EMOJI_APPROVED  = "6100515480735321747"
EMOJI_DECLINED  = "6100541628496219252"

ADMIN_IDS = {8462705169}

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Button Helper
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def colored_button(
    text: str,
    callback_data: str = None,
    url: str = None,
    style: str = "primary",
    icon_custom_emoji_id: str = None,
) -> InlineKeyboardButton:
    kwargs: dict = {"text": text, "style": style}
    if url:
        kwargs["url"] = url
    else:
        kwargs["callback_data"] = callback_data
    return InlineKeyboardButton(**kwargs)


def colored_back_button(target: str, style: str = "danger") -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [colored_button(text="« Bᴀᴄᴋ", callback_data=target, style=style)]
    ])

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Membership Cache  (unchanged from original)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

_MEMBERSHIP_CACHE: Dict[int, tuple]       = {}
_MEMBERSHIP_CACHE_TTL                     = 60
_MEMBERSHIP_LOCK: Dict[int, asyncio.Lock] = {}
_VALID_STATUSES                           = {"member", "administrator", "creator"}
_MEMBERSHIP_LOCK_MAP_LOCK: Optional[asyncio.Lock] = None


def _get_lock_map_lock() -> asyncio.Lock:
    global _MEMBERSHIP_LOCK_MAP_LOCK
    if _MEMBERSHIP_LOCK_MAP_LOCK is None:
        _MEMBERSHIP_LOCK_MAP_LOCK = asyncio.Lock()
    return _MEMBERSHIP_LOCK_MAP_LOCK


async def _get_user_lock(user_id: int) -> asyncio.Lock:
    async with _get_lock_map_lock():
        if user_id not in _MEMBERSHIP_LOCK:
            _MEMBERSHIP_LOCK[user_id] = asyncio.Lock()
        return _MEMBERSHIP_LOCK[user_id]


async def check_membership(user_id: int, bot_instance: Bot) -> bool:
    now    = time.monotonic()
    cached = _MEMBERSHIP_CACHE.get(user_id)
    if cached is not None:
        is_member, expires_at = cached
        if now < expires_at:
            return is_member

    lock = await _get_user_lock(user_id)
    async with lock:
        now    = time.monotonic()
        cached = _MEMBERSHIP_CACHE.get(user_id)
        if cached is not None:
            is_member, expires_at = cached
            if now < expires_at:
                return is_member
        try:
            ch, gr, gr2 = await asyncio.gather(
                bot_instance.get_chat_member(REQUIRED_CHANNEL_ID, user_id),
                bot_instance.get_chat_member(REQUIRED_GROUP_ID,   user_id),
                bot_instance.get_chat_member(REQUIRED_GROUP2_ID,  user_id),
            )
            is_member = (ch.status in _VALID_STATUSES
                         and gr.status in _VALID_STATUSES
                         and gr2.status in _VALID_STATUSES)
        except Exception as e:
            logging.warning(f"Membership check failed for {user_id}: {e}")
            is_member = False
        ttl = _MEMBERSHIP_CACHE_TTL if is_member else 15
        _MEMBERSHIP_CACHE[user_id] = (is_member, now + ttl)
        return is_member


def invalidate_membership_cache(user_id: int):
    _MEMBERSHIP_CACHE.pop(user_id, None)


_JOIN_KB = InlineKeyboardMarkup(inline_keyboard=[
    [
        colored_button(
            text="Jᴏɪɴ Cʜᴀɴɴᴇʟ", 
            url=CHANNEL_LINK, 
            style="primary",
            icon_custom_emoji_id=EMOJI_STAR  # Add your channel emoji ID
        ),
        colored_button(
            text="Jᴏɪɴ Gʀᴏᴜᴘ",   
            url=GROUP_LINK, 
            style="primary",
            icon_custom_emoji_id=EMOJI_STAR  # Add your group emoji ID
        ),
    ],
    [
        colored_button(
            text="Jᴏɪɴ Lᴏɢs",
            url=GROUP2_LINK,
            style="primary",
            icon_custom_emoji_id=EMOJI_STAR,
        ),
    ],
    [
        colored_button(
            text="✅ Jᴏɪɴᴇᴅ !",
            callback_data="verify_membership",
            style="success",
            icon_custom_emoji_id=EMOJI_STAR,
        )
    ],
])


class MembershipMiddleware(BaseMiddleware):
    async def __call__(self, handler, event: types.Message, data: Dict[str, Any]):
        user = event.from_user
        if not user:
            return await handler(event, data)
        if user.id in ADMIN_IDS:
            return await handler(event, data)
        if not await check_membership(user.id, data["bot"]):
            await event.answer(
                text=JOIN_TEXT,
                parse_mode="HTML",
                reply_markup=_JOIN_KB,
                disable_web_page_preview=True,
            )
            return
        return await handler(event, data)


dp.message.middleware(MembershipMiddleware())
dp.message.middleware(BanMiddleware())


@router.callback_query(F.data == "verify_membership")
async def verify_membership_callback(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    invalidate_membership_cache(user_id)
    joined  = await check_membership(user_id, callback.bot)
    if joined:
        try:
            await callback.answer(
                "✅ 𝐕𝐞𝐫𝐢𝐟𝐢𝐞𝐝! 𝐘𝐨𝐮 𝐧𝐨𝐰 𝐡𝐚𝐯𝐞 𝐟𝐮𝐥𝐥 𝐚𝐜𝐜𝐞𝐬𝐬.",
                show_alert=True,
            )
        except Exception:
            pass
        try:
            await callback.message.delete()
        except Exception:
            pass
        user = callback.from_user
        asyncio.create_task(ensure_user_and_credits(user.id, user.username, user.first_name))
        asyncio.create_task(_show_start(callback.message.chat.id, callback.bot, user))
    else:
        try:
            await callback.answer(
                "❌ 𝐘𝐨𝐮 𝐡𝐚𝐯𝐞𝐧'𝐭 𝐣𝐨𝐢𝐧𝐞𝐝 𝐲𝐞𝐭!\n\n"
                "𝐏𝐥𝐞𝐚𝐬𝐞 𝐣𝐨𝐢𝐧 𝐛𝐨𝐭𝐡 𝐭𝐡𝐞 𝐠𝐫𝐨𝐮𝐩 𝐚𝐧𝐝 𝐜𝐡𝐚𝐧𝐧𝐞𝐥, 𝐭𝐡𝐞𝐧 𝐜𝐥𝐢𝐜𝐤 𝐉𝐨𝐢𝐧𝐞𝐝 𝐚𝐠𝐚𝐢𝐧.",
                show_alert=True,
            )
        except Exception:
            pass

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# DB Helpers
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def _db_conn():
    return psycopg2.connect(**DB_CONFIG, cursor_factory=RealDictCursor)


def _ensure_user_sync(user_id, username, first_name=None):
    try:
        if not get_user(user_id):
            create_user(user_id, username or "unknown", first_name)
        if first_name:
            set_first_name(user_id, first_name)
        cr = get_user_credits(user_id)
        if not cr:
            update_credits(user_id, 150)
    except Exception as e:
        logging.error(f"ensure_user {user_id}: {e}")


async def ensure_user_and_credits(user_id, username="unknown", first_name=None):
    await asyncio.to_thread(_ensure_user_sync, user_id, username, first_name)


def _status_sync(user_id):
    conn = _db_conn()
    cur  = conn.cursor()
    plan, credits_str, joined_str = "FREE", "0", "N/A"
    try:
        cur.execute(
            "SELECT is_premium, premium_expiry, joined_at FROM users WHERE user_id = %s",
            (user_id,)
        )
        row = cur.fetchone()
        if row:
            if row['joined_at']:
                joined_str = row['joined_at'].strftime('%Y-%m-%d')
            if (
                row['is_premium'] == 1
                and row['premium_expiry']
                and datetime.now() < row['premium_expiry']
            ):
                cur.execute(
                    "SELECT plan FROM receipts WHERE user_id = %s ORDER BY purchased_on DESC LIMIT 1",
                    (user_id,)
                )
                r    = cur.fetchone()
                plan = r['plan'] if r else "Premium"
        cr          = get_user_credits(user_id)
        credits_str = str(cr if cr is not None else 0)
    except Exception as e:
        logging.error(f"status {user_id}: {e}")
        cr          = get_user_credits(user_id)
        credits_str = str(cr if cr is not None else 0)
    finally:
        conn.close()
    return credits_str, plan, joined_str


BOT_VERSION = "3.1"

EMOJI_PHONE = "5246734896356936944"
EMOJI_PLATE = "6152176648746702128"

# MATHEMATICAL SANS-SERIF BOLD ITALIC capital, contiguous from A.
_MATH_ITALIC_BASE = 0x1D63C

# Branded small-caps plan names, reused from live_emoji so the glyph sets and
# the plan badges never drift apart. Prefer the fancy alias over the plain key.
PLAN_DISPLAY = {}
for _alias, _key in _PLAN_ALIASES.items():
    _cur = PLAN_DISPLAY.get(_key)
    if _cur is None or (_cur.isascii() and not _alias.isascii()):
        PLAN_DISPLAY[_key] = _alias


def _lnk(symbol: str) -> str:
    """Wrap a decorative symbol so it opens the dev channel when tapped."""
    return f'<a href="https://t.me/broken_wiz">{symbol}</a>'


def _b(text: str) -> str:
    """Bold a whole caption line."""
    return f"<b>{text}</b>"


def _math_italic(text: str) -> str:
    """Render ASCII letters as MATHEMATICAL SANS-SERIF BOLD ITALIC capitals."""
    out = []
    for ch in text.upper():
        if "A" <= ch <= "Z":
            out.append(chr(_MATH_ITALIC_BASE + (ord(ch) - ord("A"))))
        else:
            out.append(ch)
    return "".join(out)


def _plan_display(plan) -> str:
    """Show the branded small-caps plan name when we have one."""
    raw = html.escape(str(plan or "").strip())
    key = _PLAN_LOOKUP.get(raw) or _PLAN_LOOKUP.get(raw.casefold())
    return PLAN_DISPLAY.get(key or raw.upper(), raw)


async def _get_profile_caption(user) -> str:
    credits_str, access_str, joined_str = await asyncio.to_thread(_status_sync, user.id)
    name = html.escape(str(user.first_name or "User"))
    if user.username:
        ul = f'<a href="https://t.me/{html.escape(user.username)}">{name}</a>'
    else:
        ul = f'<a href="tg://user?id={user.id}">{name}</a>'
    dl = '<a href="https://t.me/broken_wiz">𒉼 𝔦 乙</a>'
    phone = f'<tg-emoji emoji-id="{EMOJI_PHONE}">📱</tg-emoji>'
    plate = f'<tg-emoji emoji-id="{EMOJI_PLATE}">🍽</tg-emoji>'
    return (
        f'{_b(f"{_lnk("[⌭]")} 𝗪𝗲𝗹𝗰𝗼𝗺𝗲 𝘁𝗼 𝘾𝙃𝙆 𝕏 [𝙒 𝙄 𝙕] {plate}")}\n'
        f"\n"
        f'{_b(f"{_lnk("⬢")} Usᴇʀ ➵ {ul}")}\n'
        f'{_b(f"{_lnk("⬡")} Usᴇʀ ID ➵ <code>{user.id}</code>")}\n'
        f'{_b(f"{_lnk("⬢")} Pʟᴀɴ ➵ {_plan_display(access_str)}")}\n'
        f'{_b(f"{_lnk("⬡")} Cʀᴇᴅɪᴛs ➵ {html.escape(credits_str)}")}\n'
        f'{_b(f"{_lnk("⬢")} Jᴏɪɴᴇᴅ ➵ {html.escape(joined_str)}")}\n'
        f'{_b("━━━━━━━━━━━━━━━")}\n'
        f'{_b(f"{_lnk("⎔")} Vᴇʀsɪᴏɴ ➵ ᴠ{BOT_VERSION}")}\n'
        f'{_b(f"{_lnk("⎔")} Dᴇᴠ ➵ {dl} {phone}")}\n'
        f'{_b("━━━━━━━━━━━━━━━")}\n'
        f'{_b("Choose an option below.")}'
    )


def mask_receipt_id(receipt_id):
    parts = receipt_id.split('-')
    if len(parts) == 3:
        m = parts[1]
        if len(m) >= 2:
            return f"{parts[0]}-{m[:2]}XX{m[4:]}-{parts[2]}"
    return receipt_id

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Pre-built Keyboards
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

_MAIN_KB = InlineKeyboardMarkup(inline_keyboard=[
    [
        colored_button("Gᴀᴛᴇ",    callback_data="menu_gates",   icon_custom_emoji_id=EMOJI_LIGHTNING),
        colored_button("Pʀɪᴄɪɴɢ", callback_data="menu_price",   icon_custom_emoji_id=EMOJI_DIAMOND),
    ],
    [
        colored_button("Sᴜᴘᴘᴏʀᴛ", url=OWNER_LINK,               icon_custom_emoji_id=EMOJI_BAT),
        colored_button("Gʀᴏᴜᴘ",   url=GROUP_LINK,               icon_custom_emoji_id=EMOJI_STAR),
    ],
])

_KB_GATES = InlineKeyboardMarkup(inline_keyboard=[
    [
        colored_button("Aᴜᴛʜ",      callback_data="menu_auth_section",   icon_custom_emoji_id=EMOJI_LIGHTNING),
        colored_button("CʜᴀƦɢᴇ",    callback_data="menu_charge_section", icon_custom_emoji_id=EMOJI_DIAMOND),
    ],
    [
        colored_button("Mᴀss",      callback_data="menu_mass",    icon_custom_emoji_id=EMOJI_BAT),
        colored_button("HɪᴛᴛᴇƦ",    callback_data="menu_hitter",  icon_custom_emoji_id=EMOJI_LIGHTNING),
    ],
    [colored_button("« Bᴀᴄᴋ",      callback_data="back_main",        icon_custom_emoji_id=EMOJI_BAT, style="danger")],
])

_KB_AUTH_SECTION = InlineKeyboardMarkup(inline_keyboard=[
    [
        colored_button("SᴛƦɪᴘᴇ",    callback_data="menu_auth_stripe",    icon_custom_emoji_id=EMOJI_LIGHTNING),
        colored_button("Bʀᴀɪɴᴛʀᴇᴇ", callback_data="menu_auth_braintree", icon_custom_emoji_id=EMOJI_BAT),
    ],
    [
        colored_button("Cʜᴀsᴇ",    callback_data="menu_auth_chase",     icon_custom_emoji_id=EMOJI_LIGHTNING),
        colored_button("3ᴅs Lᴏᴏᴋᴜᴘ", callback_data="info_3ds_vbv",        icon_custom_emoji_id=EMOJI_TOP),
    ],
    [colored_button("« Bᴀᴄᴋ", callback_data="menu_gates", icon_custom_emoji_id=EMOJI_TOP, style="danger")],
])

_KB_CHARGE_SECTION = InlineKeyboardMarkup(inline_keyboard=[
    [
        colored_button("Sᴛʀɪᴘᴇ",   callback_data="info_charge_stripe",   icon_custom_emoji_id=EMOJI_LIGHTNING),
        colored_button("Pᴀʏᴘᴀʟ",   callback_data="info_charge_paypal",   icon_custom_emoji_id=EMOJI_BAT),
    ],
    [
        colored_button("Sʜᴏᴘɪꜰʏ",  callback_data="info_charge_shopify",  icon_custom_emoji_id=EMOJI_STAR),
        colored_button("RᴀᴢᴏƦᴘᴀʏ", callback_data="info_charge_razorpay", icon_custom_emoji_id=EMOJI_STAR),
    ],
    [
        colored_button("PᴀʏU",      callback_data="info_charge_payu",      icon_custom_emoji_id=EMOJI_BAT),
        colored_button("Nᴍɪ",       callback_data="info_charge_nmi",       icon_custom_emoji_id=EMOJI_BAT),
        # The following charge gates remain disabled:
        # colored_button("Pᴀʏꜰᴀsᴛ", callback_data="info_charge_payfast", icon_custom_emoji_id=EMOJI_DIAMOND),
        # colored_button("FᴀᴛᴢᴇʙƦᴀ", callback_data="info_charge_fatzebra", icon_custom_emoji_id=EMOJI_TOP),
    ],
    [
        colored_button("SK Bᴀsᴇᴅ", callback_data="info_charge_sk", icon_custom_emoji_id=EMOJI_LIGHTNING),
        colored_button("Pᴀʏɢʟᴏᴄᴀʟ", callback_data="info_charge_payglocal", icon_custom_emoji_id=EMOJI_LIGHTNING),
    ],
    # colored_button("Bʟᴜᴇᴘᴀʏ", callback_data="info_charge_bluepay", icon_custom_emoji_id=EMOJI_LIGHTNING),
    # colored_button("Aᴜᴛʜɴᴇᴛ", callback_data="info_charge_authnet", icon_custom_emoji_id=EMOJI_DIAMOND),
    # colored_button("Pᴀʏᴡᴀʏ", callback_data="info_charge_payway", icon_custom_emoji_id=EMOJI_TOP),
    # colored_button("Pᴀʏғʟᴏᴡ", callback_data="info_charge_nmi2", icon_custom_emoji_id=EMOJI_LIGHTNING),
    [colored_button("« Bᴀᴄᴋ", callback_data="menu_gates",       icon_custom_emoji_id=EMOJI_TOP, style="danger")],
])

_KB_3DS_SECTION = InlineKeyboardMarkup(inline_keyboard=[
    # colored_button("3ᴅs Lᴏᴏᴋᴜᴘ", callback_data="info_3ds_vbv", icon_custom_emoji_id=EMOJI_TOP),
    [colored_button("« Bᴀᴄᴋ",      callback_data="menu_auth_section", icon_custom_emoji_id=EMOJI_BAT, style="danger")],
])

_KB_MASS = InlineKeyboardMarkup(inline_keyboard=[
    [
        colored_button("Sᴛʀɪᴘᴇ",    callback_data="info_mass_stripe",    icon_custom_emoji_id=EMOJI_LIGHTNING),
        colored_button("Sʜᴏᴘɪꜰʏ",   callback_data="info_mass_shopify",   icon_custom_emoji_id=EMOJI_STAR),
    ],
    [
        colored_button("Rᴀᴢᴏʀᴘᴀʏ",  callback_data="info_mass_razorpay",  icon_custom_emoji_id=EMOJI_DIAMOND),
        colored_button("SK Bᴀsᴇᴅ",  callback_data="info_mass_sk",        icon_custom_emoji_id=EMOJI_LIGHTNING),
    ],
    # colored_button("Mᴀꜱꜱ Sᴛʀɪᴘᴇ", callback_data="info_mass_autoshopify_msh", icon_custom_emoji_id=EMOJI_TOP),
    [colored_button("« Bᴀᴄᴋ",        callback_data="menu_gates",             icon_custom_emoji_id=EMOJI_BAT, style="danger")],
])

# Shopify mass subsection is disabled for now, including its old proxy/site UI.
# _KB_MASS_AUTOSHOPIFY = InlineKeyboardMarkup(inline_keyboard=[
#     # colored_button("Pʀᴏxʏ", callback_data="...", icon_custom_emoji_id=EMOJI_BAT),
#     # colored_button("Sɪᴛᴇ", callback_data="...", icon_custom_emoji_id=EMOJI_TOP),
#     [colored_button("« Bᴀᴄᴋ", callback_data="info_mass_autoshopify", icon_custom_emoji_id=EMOJI_TOP, style="danger")],
# ])

_KB_HITTER = InlineKeyboardMarkup(inline_keyboard=[
    [
        colored_button("Sᴛʀɪᴘᴇ HɪᴛᴛᴇƦ", callback_data="info_hitter_stripe", icon_custom_emoji_id=EMOJI_LIGHTNING),
        colored_button("Wʜᴏᴘ HɪᴛᴛᴇƦ",   callback_data="info_hitter_whop",   icon_custom_emoji_id=EMOJI_STAR),
    ],
    [
        colored_button("Jɪᴏ Hɪᴛᴛᴇʀ",   callback_data="info_hitter_jio",    icon_custom_emoji_id=EMOJI_DIAMOND),
        colored_button("Mᴀɢɪᴄᴘɪɴ Hɪᴛᴛᴇʀ", callback_data="info_hitter_mpin", icon_custom_emoji_id=EMOJI_STAR),
    ],
    [
        InlineKeyboardButton(
            text="Stop",
            callback_data="hitters_stop_all",
            style="danger",
            icon_custom_emoji_id=EMOJI_DECLINED,
        ),
    ],
    [colored_button("« Bᴀᴄᴋ", callback_data="menu_gates", icon_custom_emoji_id=EMOJI_BAT, style="danger")],
])
_KB_PRICE_WITH_BUY = InlineKeyboardMarkup(inline_keyboard=[
    [colored_button("Bᴜʏ",    callback_data="menu_buy",  style="success", icon_custom_emoji_id=EMOJI_DIAMOND)],
    [colored_button("« Bᴀᴄᴋ", callback_data="back_main",                  icon_custom_emoji_id=EMOJI_BAT, style="danger")],
])

_SEP = "━━━━━━━━━━━━━━━━"

def _back(t): 
    return InlineKeyboardMarkup(inline_keyboard=[
        [colored_button(text="« Bᴀᴄᴋ", callback_data=t, style="danger")]
    ])

_KB_BACK_MASS_LOCAL = InlineKeyboardMarkup(inline_keyboard=[
    [colored_button(text="« Bᴀᴄᴋ", callback_data="menu_mass", style="danger", icon_custom_emoji_id=EMOJI_BAT)]
])

_KB_BACK_AUTOSHOPIFY = InlineKeyboardMarkup(inline_keyboard=[
    [colored_button(text="« Bᴀᴄᴋ", callback_data="info_mass_autoshopify", style="danger", icon_custom_emoji_id=EMOJI_BAT)]
])

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Static Menu Map
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

STATIC_MENU_MAP: dict = {
    "menu_gates"          : ("<b>𝗦ᴇ𝗹ᴇᴄᴛ ʏᴏᴜʀ Gᴀᴛᴇᴡᴀʏ.</b>\n\n", _KB_GATES),
    "menu_auth_section"   : ("<b>𝗦ᴇʟᴇᴄᴛ Aɴ Aᴜᴛʜ Gᴀᴛᴇ</b>",      _KB_AUTH_SECTION),
    "menu_charge_section" : ("<b>𝗦ᴇʟᴇᴄᴛ ᴀ Cʜᴀʀɢᴇ Gᴀᴛᴇ</b>",      _KB_CHARGE_SECTION),
    "menu_3ds_section"    : ("<b>𝗦ᴇʟᴇᴄᴛ LᴏᴏᴋUP Gᴀᴛᴇ</b>",         _KB_3DS_SECTION),
    "menu_mass"           : ("<b>𝗦ᴇʟᴇᴄᴛ ᴀ Mᴀss Gᴀᴛᴇᴡᴀʏ.</b>",     _KB_MASS),
    "menu_hitter"         : (
        # "<b>𝗦ᴛʀɪᴘᴇ Aᴜᴛᴏ Hɪᴛᴛᴇʀ</b>"
        "𝐓𝐡𝐢𝐬 𝐟𝐞𝐚𝐭𝐮𝐫𝐞 𝐢𝐬 𝐮𝐧𝐝𝐞𝐫 𝐝𝐞𝐯𝐞𝐥𝐨𝐩𝐦𝐞𝐧𝐭.",
        _KB_HITTER
    ),
    "menu_buy"     : (
        '<tg-emoji emoji-id="5427168083074628963">💎</tg-emoji> <b>Select Your Plan</b>\n\n'
        "<b>Pick a Plan Below, Pay Through a Secure Hosted Crypto Checkout Page.</b>",
        #"your access activates automatically once the payment is confirmed.",
        pay_sys.get_plan_selection_keyboard(),
    ),
    "menu_auth_stripe"    : (f"{_SEP}\n<b><i>Gate ➵ Stripe Auth</i></b>\n<b><i>Command ➵ /chk</i></b>\n<b><i>Sites ➵ 1</i></b>\n<b><i>Health ➵ 100%</i></b>\n{_SEP}", _back("menu_auth_section")),
    "menu_auth_braintree" : (f"{_SEP}\n<b><i>Gate ➵ Braintree Premium Auth</i></b>\n<b><i>Command ➵ /b3</i></b>\n<b><i>Sites ➵ 1</i></b>\n<b><i>Health ➵ 100%</i></b>\n{_SEP}", _back("menu_auth_section")),
    "menu_auth_chase"     : (f"{_SEP}\n<b><i>Gate ➵ Chase Auth</i></b>\n<b><i>Command ➵ /ch</i></b>\n<b><i>Sites ➵ 1</i></b>\n<b><i>Health ➵ 100%</i></b>\n{_SEP}", _back("menu_auth_section")),
    "info_3ds_vbv"        : (f"{_SEP}\n<b><i>Gate ➵ VBV Lookup</i></b>\n<b><i>Command ➵ /vbv</i></b>\n<b><i>Sites ➵ 1</i></b>\n<b><i>Health ➵ 100%</i></b>\n{_SEP}", _back("menu_auth_section")),
    "info_charge_stripe"   : (f"{_SEP}\n<b><i>Gate ➵ Stripe 1$</i></b>\n<b><i>Command ➵ /st</i></b>\n<b><i>Sites ➵ 1</i></b>\n<b><i>Health ➵ 100%</i></b>\n{_SEP}", _back("menu_charge_section")),
    "info_charge_paypal"   : (f"{_SEP}\n<b><i>Gate ➵ PayPal 0.01$</i></b>\n<b><i>Command ➵ /pp</i></b>\n<b><i>Sites ➵ 1</i></b>\n<b><i>Health ➵ 100%</i></b>\n{_SEP}", _back("menu_charge_section")),
    "info_charge_shopify"  : (f"{_SEP}\n<b><i>Gate ➵ Shopify 5$</i></b>\n<b><i>Command ➵ /hc</i></b>\n<b><i>Health ➵ 100%</i></b>\n{_SEP}\n<b><i>Gate ➵ Shopify 1$</i></b>\n<b><i>Command ➵ /sp</i></b>\n<b><i>Health ➵ 100%</i></b>\n{_SEP}", _back("menu_charge_section")),
    "info_charge_payfast"  : (f"{_SEP}\n<b><i>Gate ➵ PayFast 0.30$</i></b>\n<b><i>Command ➵ /pf</i></b>\n<b><i>Sites ➵ 1</i></b>\n<b><i>Health ➵ 100%</i></b>\n{_SEP}", _back("menu_charge_section")),
    "info_charge_fatzebra" : (f"{_SEP}\n<b><i>Gate ➵ FatZebra 4$</i></b>\n<b><i>Command ➵ /ft</i></b>\n<b><i>Sites ➵ 1</i></b>\n<b><i>Health ➵ 100%</i></b>\n{_SEP}", _back("menu_charge_section")),
    "info_charge_nmi"      : (f"{_SEP}\n<b><i>Gate ➵ NMI 1$</i></b>\n<b><i>Command ➵ /nmi</i></b>\n<b><i>Health ➵ 100%</i></b>\n{_SEP}", _back("menu_charge_section")),
    "info_charge_bluepay"  : (f"{_SEP}\n<b><i>Gate ➵ BluePay 20$</i></b>\n<b><i>Command ➵ /bl</i></b>\n<b><i>Sites ➵ 1</i></b>\n<b><i>Health ➵ 100%</i></b>\n{_SEP}", _back("menu_charge_section")),
    "info_charge_authnet"  : (f"{_SEP}\n<b><i>Gate ➵ Authorize.Net 1$</i></b>\n<b><i>Command ➵ /at</i></b>\n<b><i>Sites ➵ 1</i></b>\n<b><i>Health ➵ 100%</i></b>\n{_SEP}", _back("menu_charge_section")),
    "info_charge_payway"   : (f"{_SEP}\n<b><i>Gate ➵ Payway 1$</i></b>\n<b><i>Command ➵ /pw</i></b>\n<b><i>Sites ➵ 1</i></b>\n<b><i>Health ➵ 100%</i></b>\n{_SEP}", _back("menu_charge_section")),
    "info_charge_razorpay" : (f"{_SEP}\n<b><i>Gate ➵ Razorpay</i></b>\n<b><i>Command ➵ /rz</i></b>\n<b><i>Sites ➵ 1</i></b>\n<b><i>Health ➵ 100%</i></b>\n{_SEP}", _back("menu_charge_section")),
    "info_charge_payu"     : (f"{_SEP}\n<b><i>Gate ➵ PayU</i></b>\n<b><i>Command ➵ /pyu</i></b>\n<b><i>Sites ➵ 1</i></b>\n<b><i>Health ➵ 100%</i></b>\n{_SEP}", _back("menu_charge_section")),
    "info_charge_nmi2"     : (f"{_SEP}\n<b><i>Gate ➵ Payflow</i></b>\n<b><i>Command ➵ /nmi2</i></b>\n<b><i>Sites ➵ 1</i></b>\n<b><i>Health ➵ 100%</i></b>\n{_SEP}", _back("menu_charge_section")),
    "info_charge_sk"       : (f"{_SEP}\n<b><i>Gate ➵ SK Based 0.50$</i></b>\n<b><i>Command ➵ /sk</i></b>\n<b><i>Sites ➵ 1</i></b>\n<b><i>Health ➵ 100%</i></b>\n{_SEP}", _back("menu_charge_section")),
    "info_charge_payglocal": (f"{_SEP}\n<b><i>Gate ➵ Payglocal 0.10$</i></b>\n<b><i>Command ➵ /pg</i></b>\n<b><i>Health ➵ 100%</i></b>\n{_SEP}", _back("menu_charge_section")),
    "info_mass_stripe"     : (f"{_SEP}\n<b><i>Gate ➵ Mass Stripe</i></b>\n<b><i>Command ➵ /mst</i></b>\n<b><i>Health ➵ 100%</i></b>\n{_SEP}", _back("menu_mass")),
    "info_mass_paypal"     : (f"{_SEP}\n<b><i>Gate ➵ Mass PayPal</i></b>\n<b><i>Coming Soon</i></b>\n{_SEP}", _back("menu_mass")),
    "info_mass_skbased"    : (f"{_SEP}\n<b><i>Gate ➵ Mass SK Based</i></b>\n<b><i>Command ➵ /msh</i></b>\n<b><i>Health ➵ 100%</i></b>\n{_SEP}", _back("menu_mass")),
    "info_mass_razorpay"   : (f"{_SEP}\n<b><i>Gate ➵ Mass Razorpay</i></b>\n<b><i>Command ➵ /mrz</i></b>\n<b><i>Health ➵ 100%</i></b>\n{_SEP}", _back("menu_mass")),
    "info_mass_sk"         : (f"{_SEP}\n<b><i>Gate ➵ Mass SK Based 0.50$</i></b>\n<b><i>Command ➵ /msk</i></b>\n<b><i>Health ➵ 100%</i></b>\n{_SEP}", _back("menu_mass")),
    "info_hitter_stripe"   : (f"{_SEP}\n<b><i>Gate ➵ Stripe Auto Hitter</i></b>\n<b><i>Command ➵ /stco</i></b>\n<b><i>Mode ➵ Automated Stripe Checking</i></b>\n<b><i>Status ➵ Available</i></b>\n{_SEP}", _back("menu_hitter")),
    "info_hitter_whop"     : (f"{_SEP}\n<b><i>Gate ➵ Whop Auto Hitter</i></b>\n<b><i>Command ➵ /hit</i></b>\n<b><i>Mode ➵ Automated Whop Checking</i></b>\n<b><i>Status ➵ Available</i></b>\n{_SEP}", _back("menu_hitter")),
    "info_hitter_jio"      : (
        f"{_SEP}\n"
        "<b><i>Gate ➵ Jio Auto Hitter</i></b>\n"
        "<b><i>Command ➵ /jio &lt;phone&gt; &lt;amount&gt; &lt;card&gt;</i></b>\n"
        "<b><i>Mode ➵ Automated Jio Checking</i></b>\n"
        #"<b><i>Access ➵ Only Paid Users</i></b>\n"
        "<b><i>Status ➵ Available</i></b>\n"
        f"{_SEP}\n",
        
        _back("menu_hitter"),
    ),
    "info_hitter_mpin"     : (
        f"{_SEP}\n"
        "<b><i>Gate ➵ Magicpin Auto Hitter</i></b>\n"
        "<b><i>Login ➵ /mpsession &lt;phone&gt; ➵ /motp &lt;otp&gt;</i></b>\n"
        "<b><i>Commands ➵ /mpl (Play 50₹) • /mzm (Zomato 500₹)</i></b>\n"
        "<b><i>Blinkit ➵ /mbl (500₹) • /mbl1 (1000₹)</i></b>\n"
        "<b><i>Mode ➵ Automated Magicpin Checking</i></b>\n"
        "<b><i>Status ➵ Available</i></b>\n"
        f"{_SEP}\n",
        _back("menu_hitter"),
    ),
    "info_mass_shopify"    : (f"{_SEP}\n<b><i>Gate ➵ Mass Shopify</i></b>\n"
                               f"<b><i>Mode ➵ Shopify Mass Checker</i></b>\n"
                               f"<b><i>Command ➵ /msh</i></b>\n"
                               f"<b><i>Status ➵ Available</i></b>\n{_SEP}",
                               _back("menu_mass")),
    # "info_mass_autoshopify": ("<b>𝗔𝘂𝘛ᴏ Sʜᴏᴘɪꜰʏ</b>", _KB_MASS_AUTOSHOPIFY),
    "info_mass_autoshopify_msh": (f"{_SEP}\n<b><i>Gate ➵ Mass Stripe</i></b>\n<b><i>Command ➵ /msh</i></b>\n<b><i>Health ➵ 100%</i></b>\n{_SEP}", _back("menu_mass")),
    "menu_price": (PRICING_TEXT, _KB_PRICE_WITH_BUY),
}

# Keep the hitter entry available with its current details.
STATIC_MENU_MAP["menu_hitter"] = (
    f"{_SEP}\n"
    "<b>𝗦ᴇʟᴇᴄᴛ ʏᴏᴜʀ Hɪᴛᴛᴇʀ</b>\n"
    f"{_SEP}",
    _KB_HITTER,
)

for _i in range(12, 17):
    STATIC_MENU_MAP[f"info_charge_gate{_i}"] = (
        f"{_SEP}\n<b><i>Gate ➵ Coming Soon</i></b>\n"
        f"<b><i>Status ➵ 🚧 Under Development</i></b>\n{_SEP}",
        _back("menu_charge_section")
    )

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Edit Helper
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

async def _edit(msg: types.Message, text: str, kb: InlineKeyboardMarkup):
    try:
        if msg.caption is not None:
            await msg.edit_caption(caption=text, reply_markup=kb, parse_mode="HTML")
        else:
            await msg.edit_text(text=text, reply_markup=kb, parse_mode="HTML")
    except TypeError:
        pass
    except Exception as e:
        if "message is not modified" not in str(e).lower():
            logging.warning(f"_edit: {e}")


async def _safe_answer(cb: types.CallbackQuery, text: str = "", **kw):
    try:
        await cb.answer(text, **kw)
    except Exception:
        pass

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# /start
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

async def _start_caption(user) -> str:
    return await _get_profile_caption(user)


async def _show_start(chat_id: int, bot_instance: Bot, user=None):
    if user is None:
        return
    caption = await _start_caption(user)
    # await bot_instance.send_photo(
    #     chat_id    = chat_id,
    #     photo      = START_IMAGE_URL,
    #     caption    = caption,
    #     reply_markup = _MAIN_KB,
    #     parse_mode = "HTML",
    # )
    await bot_instance.send_message(
        chat_id      = chat_id,
        text         = caption,
        reply_markup = _MAIN_KB,
        parse_mode   = "HTML",
    )


@router.message(Command("start"))
async def start(message: types.Message):
    user = message.from_user
    asyncio.create_task(ensure_user_and_credits(user.id, user.username, user.first_name))
    parts = (message.text or "").split(maxsplit=1)
    args = parts[1] if len(parts) > 1 else ""
    if args and "plan" in args.lower():
        from sub import _PLAN_TEXT
        kb = InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(text="💎 Bᴜʏ Pʟᴀɴ", callback_data="menu_buy", style="primary"),
        ]])
        await message.answer(text=_PLAN_TEXT, parse_mode="HTML", reply_markup=kb)
        return
    await _show_start(message.chat.id, message.bot, user)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# /track  — Live payment status check
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

_TRACK_USAGE = (
    "ℹ️ <b>Uꜱᴀɢᴇ</b>\n"
    "<code>/track &lt;track_id&gt;</code>\n\n"
    "Your <b>Track ID</b> is shown on your payment invoice.\n"
    "Example: <code>/track 6aab8a7cb4b72aa7f2042ff8</code>"
)


@router.message(Command("track"))
async def track_command(message: types.Message):
    user_id = message.from_user.id
    if user_id not in ADMIN_IDS:
        await message.answer(
            "❌ <b>This command is for the owner only.</b>",
            parse_mode="HTML",
        )
        return
    parts = (message.text or "").strip().split(maxsplit=1)
    if len(parts) < 2:
        await message.answer(_TRACK_USAGE, parse_mode="HTML")
        return
    info = await asyncio.to_thread(pay_sys.track_payment_info, parts[1].strip())
    if not info:
        await message.answer(
            "❌ <b>Pᴀʏᴍᴇɴᴛ ʀᴇᴄᴏʀᴅ ɴᴏᴛ ғᴏᴜɴᴅ.</b>\n\n"
            "Check the Track ID and try again.",
            parse_mode="HTML",
        )
        return
    # Show the real Telegram first name (DB may still hold NULL / "User").
    if info.get("user_id"):
        try:
            chat = await message.bot.get_chat(info["user_id"])
            real_name = chat.first_name or chat.username
            if real_name:
                info["order_for"] = real_name
                set_first_name(info["user_id"], real_name)
        except Exception:
            pass
    await message.answer(
        pay_sys.format_track_caption(info),
        parse_mode="HTML",
        disable_web_page_preview=True,
    )

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Dot Commands (.cmd shorthand)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

DOT_COMMAND_MAP = {
    "chk": chk_command, "ch": ch_command, "sk": sk_command, "msk": msk_command, "st": st_command, "sh": sh_command, "sp": sp_command, "pg": pg_command,
    "hc": hc_command, "pf": pf_command, "vbv": vbv_command, "ft": ft_command,
    "bl": bl_command, "pp": pp_command, "at": at_command, "pw": pw_command,
    "rz": rz_command, "pyu": pyu_command, "b3": b3_command, "py": py_command,
    "nmi": nmi_command, "nmi2": nmi2_command, "stco": stco_command,
    "mst": mst_command, "bin": binn_command, "binn": binn_command,
    "auth": auth_command, "rc": rc_command, "authall": authall_command,
    "gen_code": gen_code_command, "claim": claim_command, "info": info_command,
    "rauth": rauth_command, "plan": plan_command, "adcr": adcr_command,
    "key": key_command,                                          # ← new
    "me": me_command, "all": all_command,                        # ← lifetime stats
    "on": on_command, "off": off_command,
    "onall": onall_command, "offall": offall_command, "gates": gates_command,
    "gif": gif_command, "offgif": offgif_command,
    "stats": stats_command,
    "proxy": proxy_command, "checkproxy": checkproxy_command,
    "clearproxy": clearproxy_command, "myproxy": myproxy_command,
    "gproxyadd": gproxyadd_command, "gproxyclear": gproxyclear_command,
    "gproxyreload": gproxyreload_command, "gproxyinfo": gproxyinfo_command,
    "gproxyexport": gproxyexport_command,
    "checksite": checksite_command, "seturl": seturl_command,
    "siteall": siteall_command, "removeall": removeall_command,
    "dedupe": dedupe_command, "proxyinfo": proxyinfo_command,
    "resetproxy": resetproxy_command, "cmds": cmds_command,
    "fb": feedback_cmd, "broad": broad_command,
    "ban": ban_command, "unban": unban_command, "status": status_command,
    "gen": gen_command,
    # "gate": gate_command, "fakehelp": fakehelp_command, # ← url.py / fake.py removed
    "mrz": mrz_command, "whop": whop_command, "hit": whop_command, "jio": jio_command,
    "track": track_command,
    # ── Scraper ──────────────────────────────────────────────────────────────
    "scr": scr_command,
}


@router.message(F.text.regexp(r'^\.\w+'))
async def dot_command_handler(message: types.Message):
    cmd = message.text.strip().split()[0][1:].lower()
    h   = DOT_COMMAND_MAP.get(cmd)
    if h:
        await h(message)

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# /setting  — hide/unhide user names in hit-log group messages
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def _setting_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(
                text="Hide",
                callback_data="setting_hide",
                style="success",
                icon_custom_emoji_id=EMOJI_APPROVED,
            ),
            InlineKeyboardButton(
                text="Unhide",
                callback_data="setting_show",
                style="danger",
                icon_custom_emoji_id=EMOJI_DECLINED,
            ),
        ],
        [
            InlineKeyboardButton(
                text="Close",
                callback_data="setting_close",
                style="danger",
                icon_custom_emoji_id=EMOJI_DECLINED,
            ),
        ],
    ])


def _setting_text() -> str:
    if privacy.names_hidden():
        status = f'<tg-emoji emoji-id="{EMOJI_APPROVED}">✅</tg-emoji> Hidden'
    else:
        status = f'<tg-emoji emoji-id="{EMOJI_DECLINED}">❌</tg-emoji> Visible'
    return (
        '<b><a href="https://t.me/broken_wiz">[⌭]</a> Hide Setting</b>\n'
        '━━━━━━━━━━━\n'
        f'<b>Name is ➵ {status}</b>'
    )


@router.message(Command("setting"))
async def setting_command(message: types.Message):
    is_paid, _ = get_premium_status(message.from_user.id)
    if not is_paid and message.from_user.id not in ADMIN_IDS:
        await message.reply("❌ <b>Only paid plan users can access this.</b>\n\nBuy a plan to unlock this feature.")
        return
    await message.reply(
        text=_setting_text(),
        parse_mode="HTML",
        reply_markup=_setting_kb(),
    )


@router.callback_query(F.data.in_({"setting_hide", "setting_show"}))
async def setting_callback(callback: types.CallbackQuery):
    is_paid, _ = get_premium_status(callback.from_user.id)
    if not is_paid and callback.from_user.id not in ADMIN_IDS:
        await _safe_answer(callback, "❌ Only paid plan users can access this.", show_alert=True)
        return
    hide = callback.data == "setting_hide"
    privacy.set_names_hidden(hide)
    await _safe_answer(
        callback,
        "🔒 Names are now HIDDEN in log groups." if hide else "👁 Names are now VISIBLE in log groups.",
        show_alert=True,
    )
    await _edit(callback.message, _setting_text(), _setting_kb())


@router.callback_query(F.data == "setting_close")
async def setting_close_callback(callback: types.CallbackQuery):
    try:
        await callback.message.delete()
    except Exception:
        pass
    await _safe_answer(callback)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Global Stop — cancel every running hitter / mass-check
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

_HIT_CODE_DIRS = ("autohitters", "mass_gates", "gates")


def _stop_all_hittings() -> int:
    """Cancel every in-flight hitter/check task across all gates. Returns count."""
    current = asyncio.current_task()
    cancelled = 0
    for task in asyncio.all_tasks():
        if task is current or task.done():
            continue
        coro = task.get_coro()
        code = getattr(coro, "cr_code", None)
        if code is None:
            code = getattr(getattr(coro, "__func__", None), "__code__", None)
        filename = getattr(code, "co_filename", "") if code else ""
        if not filename:
            continue
        parts = filename.replace("\\", "/").split("/")
        if len(parts) >= 2 and parts[-2] in _HIT_CODE_DIRS:
            task.cancel()
            cancelled += 1
    return cancelled


@router.callback_query(F.data == "hitters_stop_all")
async def hitters_stop_all_callback(callback: types.CallbackQuery):
    n = _stop_all_hittings()
    logging.info(f"🛑 [STOP-ALL] cancelled {n} tasks")
    await _safe_answer(
        callback,
        f"🛑 Stopped {n} running check(s)." if n else "ℹ️ Nothing is running.",
        show_alert=True,
    )


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Callback Handler
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

_MASS_PREFIXES = ("mshs_", "mshr_", "msts_", "mstr_", "stco_", "fb_", "cmds_", "mchks_", "mchkr_", "msks_", "mskr_", "mppr_", "mpps_")


@router.callback_query(lambda cb: not (cb.data or "").startswith(("pay_plan_", "pay_check_", "pay_back_plans_")))
async def button_handler(callback: types.CallbackQuery):
    data = callback.data or ""

    if data.startswith(_MASS_PREFIXES):
        return

    msg = callback.message
    if not isinstance(msg, types.Message):
        await _safe_answer(callback, "❌ Message expired. Please use /start again.", show_alert=True)
        return

    # Static menus
    static = STATIC_MENU_MAP.get(data)
    if static is not None:
        text, kb = static
        asyncio.create_task(_safe_answer(callback))
        asyncio.create_task(_edit(msg, text, kb))
        return

    # Back to main
    if data == "back_main":
        asyncio.create_task(_safe_answer(callback))
        try:
            caption = await _start_caption(callback.from_user)
            if msg.text is not None:
                await msg.edit_text(text=caption, reply_markup=_MAIN_KB, parse_mode="HTML")
            else:
                try:
                    await msg.delete()
                except Exception:
                    pass
                # await callback.bot.send_photo(
                #     chat_id=msg.chat.id,
                #     photo=START_IMAGE_URL, caption=caption,
                #     reply_markup=_MAIN_KB, parse_mode="HTML",
                # )
                await callback.bot.send_message(
                    chat_id=msg.chat.id,
                    text=caption,
                    reply_markup=_MAIN_KB, parse_mode="HTML",
                )
        except Exception as e:
            if "message is not modified" not in str(e).lower():
                logging.warning(f"back_main: {e}")
        return

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Automated Payments (Plisio)  — Plan → Hosted Checkout Page → Auto-detect → Activate
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

@router.callback_query(F.data.startswith("pay_plan_"))
async def pay_plan_callback(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    plan    = callback.data[len("pay_plan_"):]
    if plan not in pay_sys.PLANS:
        await _safe_answer(callback, "Invalid plan selected.", show_alert=True)
        return

    pay_sys.cancel_user_active_payment(user_id)
    await _safe_answer(callback, "⏳ Creating your payment page… please wait.", show_alert=True)

    payment = await asyncio.to_thread(pay_sys.create_payment, user_id, plan)
    if not payment:
        await _edit(
            callback.message,
            "❌ <b>Fᴀɪʟᴇᴅ ᴛᴏ ᴄʀᴇᴀᴛᴇ ᴘᴀʏᴍᴇɴᴛ.</b>\n"
            "Please try again or contact support.",
            pay_sys.get_plan_selection_keyboard(),
        )
        return

    pay_sys.register_payment(payment["track_id"], user_id, plan)
    pay_sys.set_user_session(user_id, plan)

    kb      = pay_sys.get_paid_button_keyboard(payment["track_id"], user_id, payment["invoice_url"])
    caption = pay_sys.format_payment_caption(payment, plan)

    await _edit(callback.message, caption, kb)

    pay_sys.start_payment_monitor(
        payment["track_id"], callback.message.chat.id,
        callback.message.message_id, False, caption,
        payment_data=payment, plan=plan, user_id=user_id,
    )


@router.callback_query(F.data.startswith("pay_check_"))
async def pay_check_callback(callback: types.CallbackQuery):
    track_id = callback.data[len("pay_check_"):]
    status = await pay_sys.manual_check_payment(track_id)
    if status in ("Paid", "Expired"):
        await _safe_answer(callback)
    else:
        await _safe_answer(
            callback,
            "⏳ Payment not detected yet.\n\n"
            "Please send the exact crypto amount to the payment page address first, "
            "then tap 'I Have Paid' again.",
            show_alert=True,
        )


@router.callback_query(F.data.startswith("pay_back_plans_"))
async def pay_back_plans_callback(callback: types.CallbackQuery):
    pay_sys.clear_user_session(callback.from_user.id)
    await _safe_answer(callback)
    await _edit(
        callback.message,
        "💎 <b>Sᴇʟᴇᴄᴛ Yᴏᴜʀ Pʟᴀɴ</b>",
        pay_sys.get_plan_selection_keyboard(),
    )


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Explicit Callback Registrations
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

dp.callback_query.register(msh_stop_handler,         MshStopCallback.filter())
dp.callback_query.register(msh_result_handler,        MshResultCallback.filter())
dp.callback_query.register(mpp_stop_handler,         MppStopCallback.filter())
dp.callback_query.register(mpp_result_handler,        MppResultCallback.filter())
dp.callback_query.register(mchk_stop_handler,         MchkStopCallback.filter())
dp.callback_query.register(mchk_result_handler,       MchkResultCallback.filter())
dp.callback_query.register(msk_stop_handler,          MskStopCallback.filter())
dp.callback_query.register(msk_result_handler,        MskResultCallback.filter())
dp.callback_query.register(mst_stop_handler,          MstStopCallback.filter())
dp.callback_query.register(mst_result_handler,        MstResultCallback.filter())
dp.callback_query.register(mrz_stop_handler,          MrzStopCallback.filter())
dp.callback_query.register(mrz_result_handler,        MrzResultCallback.filter())
dp.callback_query.register(sh_callback_handler,       F.data.startswith("sh_"))
dp.callback_query.register(stco_callback_handler,     F.data.startswith("stco_"))
dp.callback_query.register(whop_callback_handler,     F.data.startswith("whop_"))
dp.callback_query.register(jio_callback_handler,      F.data.startswith("jio_"))
dp.callback_query.register(regenerate_cards_callback, F.data.startswith("gen_reg"))

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Command Registrations
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

for _cmd, _fn in [
    ("pp", pp_command), ("pw", pw_command), ("at", at_command), ("pf", pf_command),
    ("b3", b3_command), ("chk", chk_command), ("ch", ch_command), ("sk", sk_command), ("sh", sh_command), ("st", st_command),
    ("hc", hc_command), ("sp", sp_command), ("pg", pg_command), ("stco", stco_command), ("vbv", vbv_command),
    ("ft", ft_command), ("nmi", nmi_command), ("nmi2", nmi2_command), ("bl", bl_command),
    ("rz", rz_command), ("pyu", pyu_command), ("auth", auth_command), ("rc", rc_command),
    ("authall", authall_command), ("gen_code", gen_code_command), ("claim", claim_command),
    ("info", info_command), ("rauth", rauth_command), ("plan", plan_command),
    ("adcr", adcr_command), ("key", key_command),                   # ← new
    ("me", me_command), ("all", all_command),                       # ← lifetime stats
    ("on", on_command), ("off", off_command),
    ("onall", onall_command), ("offall", offall_command), ("gates", gates_command),
    ("gif", gif_command), ("offgif", offgif_command),
    ("mst", mst_command), ("msk", msk_command), ("hit", whop_command), ("jio", jio_command), ("checksite", checksite_command), ("seturl", seturl_command),
    ("siteall", siteall_command), ("removeall", removeall_command), ("dedupe", dedupe_command),
    ("proxyinfo", proxyinfo_command), ("myproxy", myproxy_command),
    ("resetproxy", resetproxy_command), ("stats", stats_command),
    ("proxy", proxy_command), ("checkproxy", checkproxy_command),
    ("clearproxy", clearproxy_command), ("myproxy", myproxy_command),
    ("gproxyadd", gproxyadd_command), ("gproxyclear", gproxyclear_command),
    ("gproxyreload", gproxyreload_command), ("gproxyinfo", gproxyinfo_command),
    ("gproxyexport", gproxyexport_command),
    ("bin", binn_command), ("binn", binn_command),
    ("gen", gen_command),
    ("cl", cl_command), ("py", py_command), ("mrz", mrz_command), ("whop", whop_command),
    ("track", track_command),
    # ── Scraper ──────────────────────────────────────────────────────────────
    ("scr", scr_command),
]:
    dp.message.register(_fn, Command(_cmd))

setup_feedback_handler(dp)

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Main
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

async def main():
    logging.info("Bot starting...")

    # Give the payment module access to the bot so invoice edits / DMs work
    pay_sys.set_bot(bot)
    logging.info("Payment gateway: READY ✅")

    # Maintenance compensation: if we were offline >= 1 day, extend every
    # still-active paid plan by that many days and DM the affected users.
    asyncio.create_task(pay_sys.apply_maintenance_compensation(bot))
    asyncio.create_task(pay_sys._maintenance_heartbeat())
    logging.info("Maintenance compensation: ARMED ✅")

    # Re-arm monitors + recover invoices Plisio settled while we were offline
    asyncio.create_task(pay_sys.resume_payments())
    logging.info("Payment recovery: STARTED ✅")

    # Daily database + stats-file backup, delivered to the owner's DM at 00:00
    asyncio.create_task(daily_backup_scheduler(bot))
    logging.info("Daily backup scheduler: STARTED ✅")

    # Start Pyrogram scraper client before polling begins
    pyrogram_ok = await initialize_pyrogram()
    if pyrogram_ok:
        logging.info("Pyrogram scraper: ONLINE ✅")
    else:
        logging.warning("Pyrogram scraper: OFFLINE ⚠️  — /scr will not work")

    # Start the premium expiry background worker.
    # It polls the DB every 60 s, resets expired subscriptions, and
    # sends a private DM to each affected user.  No group notifications.
    asyncio.create_task(premium_expiry_worker(bot))
    logging.info("Premium expiry worker: STARTED ✅")

    await global_proxy_manager.reload()
    logging.info(f"Global proxy pool: LOADED ✅ ({global_proxy_manager.get_count()} proxies)")

    try:
        await dp.start_polling(bot, skip_updates=True)
    finally:
        await stop_pyrogram()
        logging.info("Bot stopped.")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
