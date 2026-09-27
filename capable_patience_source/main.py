import logging
import asyncio
import time
import psycopg2
from psycopg2.extras import RealDictCursor
from datetime import datetime
from typing import Dict, Any, Optional

from aiogram import Bot, Dispatcher, types, F, Router, BaseMiddleware
from aiogram.enums import ParseMode
from aiogram.client.default import DefaultBotProperties
from aiogram.filters import Command
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, FSInputFile

# [Your existing imports remain unchanged]
from database import get_user, create_user, get_user_credits, update_credits, DB_CONFIG, is_owner_user
from gate import on_command, off_command
from fb import setup_feedback_handler, feedback_cmd, router as fb_router
from stats import stats_command
from tools.binn import binn_command
from tools.url import gate_command, gatehelp_command, gmass_command
from tools.fake import fake_command, fakehelp_command, qfake_command
from tools.gen import gen_command, genhelp_command, regenerate_cards_callback
from cmds import cmds_command, router as cmds_router
from broad import broad_command, router as broad_router
from ban import ban_command, unban_command, BanMiddleware, router as ban_router
from status import status_command, router as status_router

from sub import (
    sub_command, rc_command, suball_command, g_code_command,
    claim_command, info_command, rsub_command, plan_command, 
    adcr_command
)

from gates.sh import sh_command, sh_callback_handler
from gates.sp import sp_command
from gates.hc import hc_command
from gates.pf import pf_command
from gates.vbv import vbv_command
from gates.ft import ft_command
from gates.bl import bl_command
from gates.at import at_command
from gates.pw import pw_command
from gates.rz import rz_command
from gates.pyu import pyu_command
from gates.py import py_command
from gates.nmi import nmi_command
from gates.nmi2 import nmi2_command
from gates.cl import cl_command
# ── HITTER COMMANDS (OFF — files moved; reintroduce later) ──────────
# from autohitters.stco import stco_command, stco_callback_handler
# from autohitters.hit_bot import router as hit_router, hit_command

from gates.auth_bot import router as auth_router, auth_command
from gates.stripe_bot import router as stripe_router, stripe_command

from mass_gates.msh import (
    router as msh_router, MshStopCallback, MshResultCallback,
    handle_stop_callback as msh_stop_handler,
    handle_result_callback as msh_result_handler,
    msh_command,
)
from mass_gates.mchk import (
    router as mchk_router, MchkStopCallback, MchkResultCallback,
    handle_stop_callback as mchk_stop_handler,
    handle_result_callback as mchk_result_handler,
)
from mass_gates.mst import (
    router as mst_router, MstStopCallback, MstResultCallback,
    handle_stop_callback as mst_stop_handler,
    handle_result_callback as mst_result_handler,
    mst_command
)

from mass_gates.mauth import router as mauth_router, mauth_command
from mass_gates.mstripe import router as mstripe_router, mstripe_command
from mass_gates._batch_common import sel_router
from mass_gates.stop import router as stop_router

import payments as pay_sys

# ========== BOT CONFIGURATION ==========
BOT_TOKEN = "8742835361:AAGJJJFuWSDaFRKlm-oows79yeT2WWaqkhQ"

WEBHOOK_URL = None

START_IMAGE_PATH = "photo_2026-09-22_15-54-30.jpg"
LOG_CHANNEL_ID = -1004453592223
BOT_LINK = "https://t.me/WIZZCHKv3_bot"

MAIN_SCREEN_TEXT = (
    "<tg-emoji emoji-id=\"5438436750114439411\">🏴‍☠️</tg-emoji> <b>𝑪𝑯𝑶𝑹 𝑷𝑨𝑳𝑻𝑨𝑵</b> <tg-emoji emoji-id=\"5438436750114439411\">🏴‍☠️</tg-emoji>\n"
    "━━━━━━━━━━━━━━━━━━━━━\n"
    "\n"
    "<tg-emoji emoji-id=\"5438098323871383999\">✨</tg-emoji> <b>जहाँ चोर पलटन का राज है वहीं आग है</b> <tg-emoji emoji-id=\"5195224408683204554\">🔥</tg-emoji>\n"
    "\n"
    "━━━━━━━━━━━━━━━━━━━━━\n"
    "\n"
    "<tg-emoji emoji-id=\"5085022089103016925\">⚡</tg-emoji> 𝐕𝐞𝐫𝐬𝐢𝐨𝐧 ➠ 𝐯𝟒\n"
    "<tg-emoji emoji-id=\"6136275172283391020\">⭐</tg-emoji> 𝐃𝐞𝐯 ➠ <a href='https://t.me/Enchanted_linux_0x'>Enchanted_linux_0x</a>\n"
    "\n"
    "━━━━━━━━━━━━━━━━━━━━━\n"
    "\n"
    "<tg-emoji emoji-id=\"5463071033256848094\">🔝</tg-emoji> <b>𝐂𝐡𝐨𝐨𝐬𝐞 𝐚𝐧 𝐨𝐩𝐭𝐢𝐨𝐧 𝐛𝐞𝐥𝐨𝐰</b>"
)

TOOLS_TEXT = (
    "━━━━━━━━━━━━━━━━━━━━━━\n"
    "◆ 𝐀𝐕𝐀𝐈𝐋𝐀𝐁𝐋𝐄 𝐓𝐎𝐎𝐋𝐒\n"
    "━━━━━━━━━━━━━━━━━━━━━━\n\n"
    "<tg-emoji emoji-id=\"5085022089103016925\">⚡</tg-emoji> <b>BIN TOOL</b>\n"
    "➤ Command: <code>/bin 123456</code>\n"
    "➤ Info: BIN lookup\n"
    "➤ Status: Online <tg-emoji emoji-id=\"6044254523009012231\">✅</tg-emoji>\n\n"
    "━━━━━━━━━━━━━━━━━━━━━━\n"
    "<tg-emoji emoji-id=\"5463071033256848094\">🔝</tg-emoji> <b>SITE ANALYZER</b>\n"
    "➤ Command: <code>/gate site.com</code>\n"
    "➤ Mass: <code>/gmass site1.com, site2.com</code>\n"
    "➤ Info: CMS, gateways, 3DS, captcha, WAF, DNS\n"
    "➤ Status: Online <tg-emoji emoji-id=\"6044254523009012231\">✅</tg-emoji>\n\n"
    "━━━━━━━━━━━━━━━━━━━━━━\n"
    "<tg-emoji emoji-id=\"5359719332542718652\">💎</tg-emoji> <b>CARD GENERATOR</b>\n"
    "➤ Command: <code>/gen 440066xxxxxxxxxx</code>\n"
    "➤ Info: Luhn-valid cards from BIN/wildcard\n"
    "➤ Status: Online <tg-emoji emoji-id=\"6044254523009012231\">✅</tg-emoji>\n\n"
    "━━━━━━━━━━━━━━━━━━━━━━\n"
    "<tg-emoji emoji-id=\"6136275172283391020\">⭐</tg-emoji> <b>FAKE IDENTITY</b>\n"
    "➤ Command: <code>/fake us</code>\n"
    "➤ Info: Name, address, SSN, credit info\n"
    "➤ Status: Online <tg-emoji emoji-id=\"6044254523009012231\">✅</tg-emoji>"
)

logging.basicConfig(format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO)

bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
dp = Dispatcher()

# Include routers
dp.include_router(msh_router)
dp.include_router(mchk_router)
dp.include_router(mst_router)
dp.include_router(auth_router)
dp.include_router(stripe_router)
dp.include_router(mauth_router)
dp.include_router(mstripe_router)
dp.include_router(sel_router)
dp.include_router(stop_router)
dp.include_router(cmds_router)
dp.include_router(fb_router)
dp.include_router(ban_router)
dp.include_router(broad_router)
dp.include_router(status_router)
# dp.include_router(hit_router)   # hitter OFF

router = Router()
dp.include_router(router)

# ========== CUSTOM EMOJI IDs ==========
EMOJI_LIGHTNING = "5085022089103016925"   # ⚡
EMOJI_BAT = "6136246765369694911"         # 🦇
EMOJI_STAR = "6136275172283391020"        # ⭐
EMOJI_TOP = "5463071033256848094"         # 🔝
EMOJI_DIAMOND = "5359719332542718652"     # 💎
EMOJI_APPROVED = "6044254523009012231"    # ✅
EMOJI_DECLINED = "5893081007153746175"    # ❌
EMOJI_SPARKLE = "5438098323871383999"     # ✨
EMOJI_FIRE = "5195224408683204554"        # 🔥
EMOJI_PIRATE = "5438436750114439411"      # 🏴‍☠️
EMOJI_WINK = "6136672117455853855"        # 😉
EMOJI_COOL = "6255570556104477305"        # 😎
EMOJI_WARNING = "6255910249362885846"     # ⚠️
EMOJI_WALLET = "5424976816530014958"      # 👛
EMOJI_STOP = "5247149163132493357"        # ⛔️

# ========== COLORFUL BUTTON HELPER (Bot API 9.4) ==========
def colored_button(
    text: str,
    callback_data: str = None,
    url: str = None,
    style: str = "primary",
    icon_custom_emoji_id: str = None
) -> InlineKeyboardButton:
    """
    Create a button with Telegram's new color system and optional custom emoji icon.
    
    ⚠️ IMPORTANT: Color styling (style parameter) works ONLY for callback buttons!
    URL buttons (with url parameter) will NOT show colors - this is a Telegram API limitation.
    
    Args:
        text: Button label text
        callback_data: Data sent when button is pressed (for colored buttons)
        url: URL to open (color styling is IGNORED by Telegram)
        style: "primary" (blue), "success" (green), "danger" (red)
        icon_custom_emoji_id: Custom emoji ID to show before text
    
    Returns:
        InlineKeyboardButton configured accordingly
    """
    if url:
        # URL buttons DO NOT support color styling in Telegram API
        # (colors only render on callback buttons). Emoji icons still work.
        kwargs = {"text": text, "url": url}
        if icon_custom_emoji_id:
            kwargs["icon_custom_emoji_id"] = icon_custom_emoji_id
        return InlineKeyboardButton(**kwargs)
    
    kwargs = {
        "text": text,
        "callback_data": callback_data,
        "style": style,
    }
    if icon_custom_emoji_id:
        kwargs["icon_custom_emoji_id"] = icon_custom_emoji_id

    return InlineKeyboardButton(**kwargs)


def colored_back_button(target: str, style: str = "primary") -> InlineKeyboardMarkup:
    """Create a colored back button."""
    return InlineKeyboardMarkup(inline_keyboard=[
        [colored_button(text="« Bᴀᴄᴋ", callback_data=target, style=style)]
    ])


def get_emoji_by_context(button_text: str) -> Optional[str]:
    """Return appropriate emoji ID based on button context."""
    button_lower = button_text.lower()
    
    if "gate" in button_lower or "hitter" in button_lower:
        return EMOJI_LIGHTNING
    elif "mass" in button_lower or "price" in button_lower or "pricing" in button_lower:
        return EMOJI_BAT
    elif "profile" in button_lower or "tools" in button_lower:
        return EMOJI_STAR
    elif "back" in button_lower or "main" in button_lower:
        return EMOJI_TOP
    elif "buy" in button_lower or "premium" in button_lower:
        return EMOJI_DIAMOND
    elif "auth" in button_lower or "charge" in button_lower:
        return EMOJI_LIGHTNING
    else:
        return EMOJI_STAR

ADMIN_IDS = {8462705169}


dp.message.middleware(BanMiddleware())


# ========== DB HELPERS ==========
def _db_conn():
    return psycopg2.connect(**DB_CONFIG, cursor_factory=RealDictCursor)


def _ensure_user_sync(user_id, username):
    try:
        if not get_user(user_id):
            create_user(user_id, username or "unknown")
        cr = get_user_credits(user_id)
        if not cr:
            update_credits(user_id, 150)
    except Exception as e:
        logging.error(f"ensure_user {user_id}: {e}")


async def ensure_user_and_credits(user_id, username="unknown"):
    await asyncio.to_thread(_ensure_user_sync, user_id, username)


def _status_sync(user_id):
    conn = _db_conn()
    cur = conn.cursor()
    plan, credits_str, joined_str = "Trial", "0", "N/A"
    is_owner = is_owner_user(user_id)
    if is_owner:
        plan = "OWNER"
    try:
        cur.execute("SELECT is_premium, premium_expiry, joined_at FROM users WHERE user_id = %s", (user_id,))
        row = cur.fetchone()
        if row:
            if row['joined_at']:
                joined_str = row['joined_at'].strftime('%Y-%m-%d')
            if row['is_premium'] == 1 and row['premium_expiry'] and datetime.now() < row['premium_expiry']:
                cur.execute("SELECT plan FROM receipts WHERE user_id = %s ORDER BY purchased_on DESC LIMIT 1", (user_id,))
                r = cur.fetchone()
                plan = r['plan'] if r else "Premium"
        if is_owner:
            credits_str = "∞"
        else:
            cr = get_user_credits(user_id)
            credits_str = str(cr if cr is not None else 0)
    except Exception as e:
        logging.error(f"status {user_id}: {e}")
        if is_owner:
            credits_str = "∞"
        else:
            cr = get_user_credits(user_id)
            credits_str = str(cr if cr is not None else 0)
    finally:
        conn.close()
    return credits_str, plan, joined_str


async def _get_profile_caption(user) -> str:
    credits_str, access_str, joined_str = await asyncio.to_thread(_status_sync, user.id)
    ul = f'<a href="tg://user?id={user.id}">{user.first_name}</a>'
    dl = '<a href="https://t.me/Enchanted_linux_0x">Enchanted_linux_0x</a>'
    return (
        f"<a href='https://t.me/Enchanted_linux_0x'>✧</a> 𝐔𝐬𝐞𝐫 𝐍𝐚𝐦𝐞 ➠ {ul}\n"
        f"<a href='https://t.me/Enchanted_linux_0x'>✧</a> 𝐔𝐬𝐞𝐫 𝐈𝐃 ➠ <code>{user.id}</code>\n"
        f"<a href='https://t.me/Enchanted_linux_0x'>✧</a> 𝐏𝐥𝐚𝐧 ➠ <b>{access_str}</b>\n"
        f"<a href='https://t.me/Enchanted_linux_0x'>✧</a> 𝐂𝐫𝐞𝐝𝐢𝐭𝐬 ➠ <b>{credits_str}</b>\n"
        f"<a href='https://t.me/Enchanted_linux_0x'>✧</a> 𝐉𝐨𝐢𝐧𝐞𝐝 ➠ <b>{joined_str}</b>\n"
        #f"━━━━━━━━━━━━━━━━\n"
        f"<a href='https://t.me/Enchanted_linux_0x'>✧</a> 𝐃𝐞𝐯 ➠ {dl}"
    )


def _loading_caption(user) -> str:
    ul = f'<a href="tg://user?id={user.id}">{user.first_name}</a>'
    dl = '<a href="https://t.me/Enchanted_linux_0x">Enchanted_linux_0x</a>'
    return (
        f"<a href='https://t.me/Enchanted_linux_0x'>✧</a> 𝐔𝐬𝐞𝐫 𝐍𝐚𝐦𝐞 ➠ {ul}\n"
        f"<a href='https://t.me/Enchanted_linux_0x'>✧</a> 𝐔𝐬𝐞𝐫 𝐈𝐃 ➠ <code>{user.id}</code>\n"
        f"<a href='https://t.me/Enchanted_linux_0x'>✧</a> 𝐏𝐥𝐚𝐧 ➠ <b></b>\n"
        f"<a href='https://t.me/Enchanted_linux_0x'>✧</a> 𝐂𝐫𝐞𝐝𝐢𝐭𝐬 ➠ <b></b>\n"
        f"<a href='https://t.me/Enchanted_linux_0x'>✧</a> 𝐉𝐨𝐢𝐧𝐞𝐝 ➠ <b></b>\n"
        #f"━━━━━━━━━━━━━━━━\n"
        f"<a href='https://t.me/Enchanted_linux_0x'>✧</a> 𝐃𝐞𝐯 ➠ {dl}"
    )


def mask_receipt_id(receipt_id):
    parts = receipt_id.split('-')
    if len(parts) == 3:
        m = parts[1]
        if len(m) >= 2:
            return f"{parts[0]}-{m[:2]}XX{m[4:]}-{parts[2]}"
    return receipt_id


# ========== ANIMATION WORDS ==========
ANIMATION_WORDS = [
    "<tg-emoji emoji-id=\"5085022089103016925\">⚡</tg-emoji> <b>𝑪𝑯𝑶𝑹 𝑷𝑨𝑳𝑻𝑨𝑵 𝑺𝒀𝑺𝑻𝑬𝑴 𝑩𝑶𝑶𝑻...</b>",
    "<tg-emoji emoji-id=\"5085022089103016925\">⚡</tg-emoji> <b>𝑰𝑵𝑰𝑻𝑰𝑨𝑳𝑰𝑺𝑰𝑵𝑮 𝑩𝑶𝑻 𝑭𝑼𝑵𝑪𝑻𝑰𝑶𝑵𝑺...</b>",
    "<tg-emoji emoji-id=\"5085022089103016925\">⚡</tg-emoji> <b>𝑬𝑺𝑻𝑨𝑩𝑳𝑰𝑺𝑯 𝑺𝑬𝑪𝑼𝑹𝑬 𝑪𝑶𝑵𝑵𝑬𝑪𝑻𝑰𝑶𝑵...</b>",
    "<tg-emoji emoji-id=\"5085022089103016925\">⚡</tg-emoji> <b>𝑫𝑬𝑷𝑳𝑶𝒀𝑰𝑵𝑮 𝑭𝑰𝑹𝑬𝑾𝑨𝑳𝑳 𝑷𝑹𝑶𝑻𝑶𝑪𝑶𝑳...</b>",
    "<tg-emoji emoji-id=\"5085022089103016925\">⚡</tg-emoji> <b>𝑺𝑬𝑪𝑼𝑹𝑬 𝑷𝑨𝒀𝑴𝑬𝑵𝑻 𝑮𝑨𝑻𝑬𝑾𝑨𝒀𝑺...</b>",
    "<tg-emoji emoji-id=\"5085022089103016925\">⚡</tg-emoji> <b>𝑨𝑼𝑻𝑯𝑬𝑵𝑻𝑰𝑪𝑨𝑻𝑬 𝑼𝑺𝑬𝑹𝑺 𝑺𝑬𝑺𝑺𝑰𝑶𝑵...</b>",
    "<tg-emoji emoji-id=\"5085022089103016925\">⚡</tg-emoji> <b>𝑪𝑯𝑶𝑹 𝑷𝑨𝑳𝑻𝑨𝑵 𝑶𝑵𝑳𝑰𝑵𝑬 !</b>"
]

# ========== PRE-BUILT KEYBOARDS ==========
# MAIN KEYBOARD
_MAIN_KB = InlineKeyboardMarkup(inline_keyboard=[
    [
        colored_button(text="Gᴀᴛᴇ", callback_data="menu_gates", style="primary", icon_custom_emoji_id=EMOJI_LIGHTNING),
        colored_button(text="Mᴀss", callback_data="menu_mass", style="primary", icon_custom_emoji_id=EMOJI_DIAMOND)
    ],
    [
        colored_button(text="Pʀᴏꜰɪʟᴇ", callback_data="menu_profile", style="primary", icon_custom_emoji_id=EMOJI_STAR),
        colored_button(text="Tᴏᴏʟs", callback_data="menu_tools", style="primary", icon_custom_emoji_id=EMOJI_TOP)
    ],
    [
        colored_button(text="OᴡɴᴇƦ", callback_data="open_owner", style="success", icon_custom_emoji_id=EMOJI_BAT),
        colored_button(text="Dᴇᴠ", callback_data="open_dev", style="primary", icon_custom_emoji_id=EMOJI_STAR)
    ]
])

# GATES SECTION
_KB_GATES = InlineKeyboardMarkup(inline_keyboard=[
    [
        colored_button(text="Aᴜᴛʜ", callback_data="info_auth", style="primary", icon_custom_emoji_id=EMOJI_LIGHTNING),
        colored_button(text="CʜᴀƦɢᴇ", callback_data="menu_charge_section", style="primary", icon_custom_emoji_id=EMOJI_DIAMOND),
        colored_button(text="3ᴅs Lᴏᴏᴋᴜᴘ", callback_data="menu_3ds_section", style="primary", icon_custom_emoji_id=EMOJI_TOP)
    ],
    # [colored_button(text="Hɪᴛᴛᴇʀ", callback_data="menu_hitter", style="primary", icon_custom_emoji_id=EMOJI_LIGHTNING)],  # hitter OFF
    [colored_button(text="« Bᴀᴄᴋ", callback_data="back_main", style="primary", icon_custom_emoji_id=EMOJI_BAT)]
])


# ── HITTER SECTION (OFF) ──────────────────────────────────────────────
# _KB_HITTER = InlineKeyboardMarkup(inline_keyboard=[
#     [
#         colored_button(text="Sᴛʀɪᴘᴇ", callback_data="info_hitter_stripe", style="primary", icon_custom_emoji_id=EMOJI_LIGHTNING),
#         colored_button(text="Wʜᴏᴘ", callback_data="info_hitter_whop", style="primary", icon_custom_emoji_id=EMOJI_DIAMOND)
#     ],
#     [colored_button(text="« Bᴀᴄᴋ", callback_data="menu_gates", style="primary", icon_custom_emoji_id=EMOJI_BAT)]
# ])


# CHARGE SECTION
_KB_CHARGE_SECTION = InlineKeyboardMarkup(inline_keyboard=[
    [
        colored_button(text="Sʜᴏᴘɪꜰʏ", callback_data="info_charge_shopify", style="primary", icon_custom_emoji_id=EMOJI_STAR),
        colored_button(text="Pᴀʏꜰᴀsᴛ", callback_data="info_charge_payfast", style="primary", icon_custom_emoji_id=EMOJI_DIAMOND)
    ],
    [
        colored_button(text="FᴀᴛᴢᴇʙƦᴀ", callback_data="info_charge_fatzebra", style="primary", icon_custom_emoji_id=EMOJI_TOP),
        colored_button(text="Nᴍɪ", callback_data="info_charge_nmi", style="primary", icon_custom_emoji_id=EMOJI_BAT)
    ],
    [
        colored_button(text="Bʟᴜᴇᴘᴀʏ", callback_data="info_charge_bluepay", style="primary", icon_custom_emoji_id=EMOJI_LIGHTNING),
        colored_button(text="Aᴜᴛʜɴᴇᴛ", callback_data="info_charge_authnet", style="primary", icon_custom_emoji_id=EMOJI_DIAMOND)
    ],
    [
        colored_button(text="Pᴀʏᴡᴀʏ", callback_data="info_charge_payway", style="primary", icon_custom_emoji_id=EMOJI_TOP),
        colored_button(text="RᴀᴢᴏƦᴘᴀʏ", callback_data="info_charge_razorpay", style="primary", icon_custom_emoji_id=EMOJI_STAR)
    ],
    [
        colored_button(text="PᴀʏU", callback_data="info_charge_payu", style="primary", icon_custom_emoji_id=EMOJI_BAT),
        colored_button(text="Nᴍɪ𝟮", callback_data="info_charge_nmi2", style="primary", icon_custom_emoji_id=EMOJI_LIGHTNING)
    ],
    [colored_button(text="Sᴛʀɪᴘᴇ", callback_data="info_charge_stripe", style="primary", icon_custom_emoji_id=EMOJI_LIGHTNING)],
    [colored_button(text="« Bᴀᴄᴋ", callback_data="menu_gates", style="primary", icon_custom_emoji_id=EMOJI_TOP)]
])

# 3DS SECTION
_KB_3DS_SECTION = InlineKeyboardMarkup(inline_keyboard=[
    [colored_button(text="3ᴅs Lᴏᴏᴋᴜᴘ", callback_data="info_3ds_vbv", style="primary", icon_custom_emoji_id=EMOJI_TOP)],
    [colored_button(text="« Bᴀᴄᴋ", callback_data="menu_gates", style="primary", icon_custom_emoji_id=EMOJI_BAT)]
])

# MASS SECTION
_KB_MASS = InlineKeyboardMarkup(inline_keyboard=[
    [
        colored_button(text="Sᴛʀɪᴘᴇ Aᴜᴛʜ", callback_data="info_mass_stripe", style="primary", icon_custom_emoji_id=EMOJI_LIGHTNING),
        colored_button(text="Pᴀʏᴘᴀʟ", callback_data="info_mass_paypal", style="primary", icon_custom_emoji_id=EMOJI_BAT)
    ],
    [
        colored_button(text="SK ʙᴀsᴇᴅ", callback_data="info_mass_skbased", style="primary", icon_custom_emoji_id=EMOJI_STAR),
        colored_button(text="Sʜᴏᴘɪꜰʏ", callback_data="info_mass_shopify", style="primary", icon_custom_emoji_id=EMOJI_DIAMOND)
    ],
    [
        colored_button(text="Aᴜᴛʜ", callback_data="info_mass_auth", style="primary", icon_custom_emoji_id=EMOJI_DIAMOND),
        colored_button(text="Sᴛʀɪᴘᴇ", callback_data="info_mass_stripe2", style="primary", icon_custom_emoji_id=EMOJI_LIGHTNING)
    ],
    [colored_button(text="« Bᴀᴄᴋ", callback_data="back_main", style="primary", icon_custom_emoji_id=EMOJI_BAT)]
])

_SEP = "━━━━━━━━━━━━━━━━"

# Back button helpers
def _back(target: str):
    return colored_back_button(target, style="primary")

_KB_BACK_MAIN = _back("back_main")
_KB_BACK_GATES = _back("menu_gates")
_KB_BACK_MASS = _back("menu_mass")
_KB_BACK_CHARGE = _back("menu_charge_section")
_KB_BACK_3DS = _back("menu_3ds_section")
_KB_BACK_TOOLS = _back("back_main")
_KB_BACK_MASS_LOCAL = _back("menu_mass")

# ========== STATIC MENU LOOKUP ==========
STATIC_MENU_MAP: dict = {
    "menu_gates": (
        "<b><tg-emoji emoji-id=\"5085022089103016925\">⚡</tg-emoji> 𝗚𝗔𝗧𝗘 𝗦𝗘𝗟𝗘𝗖𝗧𝗜𝗢𝗡</b>\n\n"
        "𝗔𝗨𝗧𝗛 ➠ Stripe authorization gates\n"
        "𝗖𝗛𝗔𝗥𝗚𝗘 ➠ Charge gates for payment processing\n"
        "𝟯𝗗𝗦 𝗟𝗢𝗢𝗞𝗨𝗣 ➠ 3D Secure verification lookup\n"
        "𝗛𝗜𝗧𝗧𝗘𝗥 ➠ Stripe / Whop auto hitters",
        _KB_GATES
    ),
    # "menu_hitter": ("...", _KB_HITTER),  # hitter OFF
    "menu_charge_section": ("<b><tg-emoji emoji-id=\"5424976816530014958\">👛</tg-emoji> 𝗖𝗛𝗔𝗥𝗚𝗘 𝗚𝗔𝗧𝗘𝗦</b>\n\nSelect a charge gate:", _KB_CHARGE_SECTION),
    "menu_3ds_section": ("<b><tg-emoji emoji-id=\"6136275172283391020\">⭐</tg-emoji> 𝟯𝗗𝗦 𝗟𝗢𝗢𝗞𝗨𝗣</b>\n\nSelect lookup method:", _KB_3DS_SECTION),
    "menu_mass": ("<b><tg-emoji emoji-id=\"5359719332542718652\">💎</tg-emoji> 𝗔𝘃𝗮𝗶𝗹𝗮𝗯𝗹𝗲 𝗠𝗮𝘀𝘀 𝗖𝗵𝗲𝗰𝗸𝗶𝗻𝗴 𝗢𝗽𝘁𝗶𝗼𝗻𝘀:</b>\n\n➤ 𝗦𝗧𝗥𝗜𝗣𝗘 𝗠𝗔𝗦𝗦 - Mass Stripe Auth Checking\n➤ 𝗣𝗔𝗬𝗣𝗔𝗟 𝗠𝗔𝗦𝗦 - Mass PayPal Checking\n➤ 𝗦𝗞𝗕𝗔𝗦𝗘𝗗 𝗠𝗔𝗦𝗦 - Mass SK Based Checking\n➤ 𝗦𝗛𝗢𝗣𝗜𝗙𝗬 𝗠𝗔𝗦𝗦 - Mass Shopify Charge Checking", _KB_MASS),
    "menu_profile": (None, None),
    "menu_tools": (TOOLS_TEXT, _KB_BACK_TOOLS),
}


# AUTH GATE INFO
STATIC_MENU_MAP["info_auth"] = (
    f"{_SEP}\n<b><i>Gate ➠ Stripe Auth (auth.py)</i></b>\n<b><i>Command ➠ /auth</i></b>\n"
    f"<b><i>Sites Loaded ➠ 3</i></b>\n<b><i>Gate Health ➠ 100%</i></b>\n{_SEP}",
    _back("menu_gates")
)

# ── HITTER INFO (OFF) ──────────────────────────────────────────────────
# STATIC_MENU_MAP["info_hitter_stripe"] = (...)
# STATIC_MENU_MAP["info_hitter_whop"] = (...)

# 3DS LOOKUP INFO
STATIC_MENU_MAP["info_3ds_vbv"] = (
    f"{_SEP}\n<b><i>Gate ➠ VBV Lookup</i></b>\n<b><i>Command ➠ /vbv</i></b>\n"
    f"<b><i>Sites Loaded ➠ 1</i></b>\n<b><i>Gate Health ➠ 100%</i></b>\n{_SEP}",
    _back("menu_3ds_section")
)

# CHARGE GATES INFO

STATIC_MENU_MAP["info_charge_shopify"] = (
    f"{_SEP}\n<b><i>Gate ➠ Shopify 5$</i></b>\n<b><i>Command ➠ /hc</i></b>\n"
    f"<b><i>Gate Health ➠ 100%</i></b>\n{_SEP}\n<b><i>Gate ➠ Shopify 1$</i></b>\n"
    f"<b><i>Command ➠ /sp</i></b>\n<b><i>Gate Health ➠ 100%</i></b>\n{_SEP}",
    _back("menu_charge_section")
)
STATIC_MENU_MAP["info_charge_payfast"] = (
    f"{_SEP}\n<b><i>Gate ➠ PayFast 0.30$</i></b>\n<b><i>Command ➠ /pf</i></b>\n"
    f"<b><i>Sites Loaded ➠ 1</i></b>\n<b><i>Gate Health ➠ 100%</i></b>\n{_SEP}",
    _back("menu_charge_section")
)
STATIC_MENU_MAP["info_charge_fatzebra"] = (
    f"{_SEP}\n<b><i>Gate ➠ FatZebra 4$</i></b>\n<b><i>Command ➠ /ft</i></b>\n"
    f"<b><i>Sites Loaded ➠ 1</i></b>\n<b><i>Gate Health ➠ 100%</i></b>\n{_SEP}",
    _back("menu_charge_section")
)
STATIC_MENU_MAP["info_charge_nmi"] = (
    f"{_SEP}\n<b><i>Gate ➠ NMI 1$</i></b>\n<b><i>Command ➠ /nmi</i></b>\n"
    f"<b><i>Gate Health ➠ 100%</i></b>\n{_SEP}",
    _back("menu_charge_section")
)
STATIC_MENU_MAP["info_charge_bluepay"] = (
    f"{_SEP}\n<b><i>Gate ➠ BluePay 20$</i></b>\n<b><i>Command ➠ /bl</i></b>\n"
    f"<b><i>Sites Loaded ➠ 1</i></b>\n<b><i>Gate Health ➠ 100%</i></b>\n{_SEP}",
    _back("menu_charge_section")
)
STATIC_MENU_MAP["info_charge_authnet"] = (
    f"{_SEP}\n<b><i>Gate ➠ Authorize.net 1$</i></b>\n<b><i>Command ➠ /at</i></b>\n"
    f"<b><i>Gate Health ➠ 100%</i></b>\n{_SEP}",
    _back("menu_charge_section")
)
STATIC_MENU_MAP["info_charge_payway"] = (
    f"{_SEP}\n<b><i>Gate ➠ PayWay 1$</i></b>\n<b><i>Command ➠ /pw</i></b>\n"
    f"<b><i>Gate Health ➠ 100%</i></b>\n{_SEP}",
    _back("menu_charge_section")
)
STATIC_MENU_MAP["info_charge_razorpay"] = (
    f"{_SEP}\n<b><i>Gate ➠ Razorpay 1₹</i></b>\n<b><i>Command ➠ /rz</i></b>\n"
    f"<b><i>Sites Loaded ➠ 5</i></b>\n<b><i>Gate Health ➠ 100%</i></b>\n{_SEP}",
    _back("menu_charge_section")
)
STATIC_MENU_MAP["info_charge_payu"] = (
    f"{_SEP}\n<b><i>Gate ➠ PayU 1$</i></b>\n<b><i>Command ➠ /pyu</i></b>\n"
    f"<b><i>Gate Health ➠ 100%</i></b>\n{_SEP}",
    _back("menu_charge_section")
)
STATIC_MENU_MAP["info_charge_nmi2"] = (
    f"{_SEP}\n<b><i>Gate ➠ NMI2 1$</i></b>\n<b><i>Command ➠ /nmi2</i></b>\n"
    f"<b><i>Gate Health ➠ 100%</i></b>\n{_SEP}",
    _back("menu_charge_section")
)

STATIC_MENU_MAP["info_charge_stripe"] = (
    f"{_SEP}\n<b><i>Gate ➠ Stripe 1$</i></b>\n<b><i>Command ➠ /stripe</i></b>\n"
    f"<b><i>Gate Health ➠ 100%</i></b>\n{_SEP}",
    _back("menu_charge_section")
)


# MASS GATES INFO
STATIC_MENU_MAP["info_mass_stripe"] = (
    f"{_SEP}\n[⊀] Command: /mchk cc|mm|yy|cvv\n[⊀] Info: Stripe mass checking\n[⊀] Status: Online <tg-emoji emoji-id=\"6044254523009012231\">✅</tg-emoji>\n[⊀] Type: Paid <tg-emoji emoji-id=\"5359719332542718652\">💎</tg-emoji>\n{_SEP}",
    _KB_BACK_MASS_LOCAL
)
STATIC_MENU_MAP["info_mass_paypal"] = (
    f"{_SEP}\n◆ 𝐏𝐀𝐘𝐏𝐀𝐋 𝐌𝐀𝐒𝐒 𝐂𝐇𝐄𝐂𝐊𝐈𝐍𝐆\n{_SEP}\n[⊀] Command: /mpp cc|mm|yy|cvv\n[⊀] Info: Mass paypal checking\n[⊀] Status: Online <tg-emoji emoji-id=\"6044254523009012231\">✅</tg-emoji>\n[⊀] Type: Paid <tg-emoji emoji-id=\"5359719332542718652\">💎</tg-emoji>\n{_SEP}",
    _KB_BACK_MASS_LOCAL
)
STATIC_MENU_MAP["info_mass_skbased"] = (
    f"{_SEP}\n◆ 𝐒𝐊𝐁𝐀𝐒𝐄𝐃 𝐌𝐀𝐒𝐒 𝐂𝐇𝐄𝐂𝐊𝐈𝐍𝐆\n{_SEP}\n[⊀] Command: /msk cc|mm|yy|cvv\n[⊀] Info: Mass SK based checking\n[⊀] Status: Online <tg-emoji emoji-id=\"6044254523009012231\">✅</tg-emoji>\n[⊀] Type: Paid <tg-emoji emoji-id=\"5359719332542718652\">💎</tg-emoji>\n{_SEP}",
    _KB_BACK_MASS_LOCAL
)
STATIC_MENU_MAP["info_mass_shopify"] = (
    f"{_SEP}\n◆ 𝐒𝐇𝐎𝐏𝐈𝐅𝐘 𝐌𝐀𝐒𝐒 𝐂𝐇𝐄𝐂𝐊𝐈𝐍𝐆\n{_SEP}\n[⊀] Command: /msh cc|mm|yy|cvv\n[⊀] Info: Mass shopify charge checking\n[⊀] Status: Online <tg-emoji emoji-id=\"6044254523009012231\">✅</tg-emoji>\n[⊀] Type: Paid <tg-emoji emoji-id=\"5359719332542718652\">💎</tg-emoji>\n{_SEP}",
    _KB_BACK_MASS_LOCAL
)

STATIC_MENU_MAP["info_mass_auth"] = (
    f"{_SEP}\n◆ 𝐀𝐔𝐓𝐇 𝐌𝐀𝐒𝐒 𝐂𝐇𝐄𝐂𝐊𝐈𝐍𝐆\n{_SEP}\n[⊀] Command: /mauth cc|mm|yy|cvv\n[⊀] Info: Mass auth checking\n[⊀] Status: Online <tg-emoji emoji-id=\"6044254523009012231\">✅</tg-emoji>\n[⊀] Type: Paid <tg-emoji emoji-id=\"5359719332542718652\">💎</tg-emoji>\n{_SEP}",
    _KB_BACK_MASS_LOCAL
)
STATIC_MENU_MAP["info_mass_stripe2"] = (
    f"{_SEP}\n◆ 𝐒𝐓𝐑𝐈𝐏𝐄 𝐌𝐀𝐒𝐒 𝐂𝐇𝐄𝐂𝐊𝐈𝐍𝐆\n{_SEP}\n[⊀] Command: /mstripe cc|mm|yy|cvv\n[⊀] Info: Mass stripe charge checking\n[⊀] Status: Online <tg-emoji emoji-id=\"6044254523009012231\">✅</tg-emoji>\n[⊀] Type: Paid <tg-emoji emoji-id=\"5359719332542718652\">💎</tg-emoji>\n{_SEP}",
    _KB_BACK_MASS_LOCAL
)

# PRICE MENU WITH BUY BUTTON
# ========== FAST INLINE EDIT HELPER ==========
async def _edit(msg: types.Message, text: str, kb: InlineKeyboardMarkup):
    try:
        if msg.caption is not None:
            await msg.edit_caption(caption=text, reply_markup=kb, parse_mode="HTML")
        else:
            await msg.edit_text(text=text, reply_markup=kb, parse_mode="HTML")
    except TypeError:
        pass
    except Exception as e:
        if "Message is not modified" not in str(e):
            logging.warning(f"_edit: {e}")


async def _safe_answer(cb: types.CallbackQuery, text: str = None, **kw):
    try:
        await cb.answer(text, **kw)
    except Exception:
        pass


# ========== /start WITH ANIMATION ==========
@router.message(Command("start"))
async def start(message: types.Message):
    user = message.from_user
    asyncio.create_task(ensure_user_and_credits(user.id, user.username))

    temp_msg = await message.answer(text=ANIMATION_WORDS[0], parse_mode="HTML")

    for i in range(1, len(ANIMATION_WORDS)):
        await asyncio.sleep(0.05)
        try:
            await temp_msg.edit_text(text=ANIMATION_WORDS[i], parse_mode="HTML")
        except Exception:
            pass

    await asyncio.sleep(0.05)
    try:
        await temp_msg.delete()
    except Exception:
        pass

    sent = await message.answer_photo(
        photo=FSInputFile(START_IMAGE_PATH),
        caption=MAIN_SCREEN_TEXT,
        reply_markup=_MAIN_KB,
        parse_mode="HTML"
    )


# ========== DOT COMMANDS ==========
DOT_COMMAND_MAP = {
    "sh": sh_command,
    "sp": sp_command, "hc": hc_command, "pf": pf_command,
    "vbv": vbv_command, "ft": ft_command, "bl": bl_command,
    "at": at_command, "pw": pw_command,
    "rz": rz_command, "pyu": pyu_command, "py": py_command,
    "nmi": nmi_command, "nmi2": nmi2_command,  # "stco": stco_command,  # hitter OFF
    "mst": mst_command, "msh": msh_command,  # "hit": hit_command, "co": hit_command,  # hitter OFF
    "auth": auth_command, "stripe": stripe_command, "mauth": mauth_command, "mstripe": mstripe_command, "bin": binn_command, "binn": binn_command,
    "sub": sub_command, "rc": rc_command, "suball": suball_command,
    "g_code": g_code_command, "claim": claim_command, "info": info_command,
    "rsub": rsub_command, "plan": plan_command, "adcr": adcr_command,
    "on": on_command, "off": off_command, "stats": stats_command,
    "cmds": cmds_command, "fb": feedback_cmd, "broad": broad_command,
    "ban": ban_command, "unban": unban_command, "status": status_command,
    "qfake": qfake_command, "fake": fake_command, "gen": gen_command, "gate": gate_command,
    "gmass": gmass_command, "gatehelp": gatehelp_command, "fakehelp": fakehelp_command, "genhelp": genhelp_command,
}


@router.message(F.text.regexp(r'^\.\w+'))
async def dot_command_handler(message: types.Message):
    cmd = message.text.strip().split()[0][1:].lower()
    h = DOT_COMMAND_MAP.get(cmd)
    if h:
        await h(message)


# ========== CALLBACK HANDLER ==========
_MASS_PREFIXES = ("mshs_", "mshr_", "msts_", "mstr_", "stco_", "fb_", "cmds_", "mchks_", "mchkr_", "mauth_res_", "mauth_stop_", "mstripe_res_", "mstripe_stop_")


@router.callback_query()
async def button_handler(callback: types.CallbackQuery):
    data = callback.data or ""

    if data.startswith(_MASS_PREFIXES):
        return

    # OWNER / DEV LINK BUTTONS (open via callback answer so they keep color + emoji icon)
    if data in ("open_owner", "open_dev"):
        await _safe_answer(callback, url="https://t.me/Enchanted_linux_0x")
        return

    msg = callback.message
    if not isinstance(msg, types.Message):
        await _safe_answer(callback, "❌ Message expired. Please use /start again.", show_alert=True)
        return

    # PROFILE MENU
    if data == "menu_profile":
        user = callback.from_user
        quick = _loading_caption(user)
        caption_task = asyncio.create_task(_get_profile_caption(user))
        asyncio.create_task(_safe_answer(callback))
        try:
            if msg.caption is not None:
                await msg.edit_caption(caption=quick, reply_markup=_KB_BACK_MAIN, parse_mode="HTML")
            else:
                await msg.edit_text(text=quick, reply_markup=_KB_BACK_MAIN, parse_mode="HTML")
        except Exception as e:
            if "Message is not modified" not in str(e):
                logging.warning(f"profile load: {e}")
        try:
            full = await caption_task
            if msg.caption is not None:
                await msg.edit_caption(caption=full, reply_markup=_KB_BACK_MAIN, parse_mode="HTML")
            else:
                await msg.edit_text(text=full, reply_markup=_KB_BACK_MAIN, parse_mode="HTML")
        except Exception:
            pass
        return

    # STATIC MENU
    static = STATIC_MENU_MAP.get(data)
    if static is not None:
        text, kb = static
        asyncio.create_task(_safe_answer(callback))
        asyncio.create_task(_edit(msg, text, kb))
        return

    # BACK TO MAIN
    if data == "back_main":
        asyncio.create_task(_safe_answer(callback))
        try:
            if msg.caption is not None:
                await msg.edit_caption(caption=MAIN_SCREEN_TEXT, reply_markup=_MAIN_KB, parse_mode="HTML")
            else:
                await msg.answer_photo(photo=FSInputFile(START_IMAGE_PATH), caption=MAIN_SCREEN_TEXT, reply_markup=_MAIN_KB, parse_mode="HTML")
        except Exception as e:
            if "Message is not modified" not in str(e):
                logging.warning(f"back_main: {e}")
        return


# ========== EXPLICIT CALLBACK REGISTRATIONS ==========
dp.callback_query.register(msh_stop_handler, MshStopCallback.filter())
dp.callback_query.register(msh_result_handler, MshResultCallback.filter())
dp.callback_query.register(mchk_stop_handler, MchkStopCallback.filter())
dp.callback_query.register(mchk_result_handler, MchkResultCallback.filter())
dp.callback_query.register(mst_stop_handler, MstStopCallback.filter())
dp.callback_query.register(mst_result_handler, MstResultCallback.filter())
dp.callback_query.register(sh_callback_handler, F.data.startswith("sh_"))
# dp.callback_query.register(stco_callback_handler, F.data.startswith("stco_"))  # hitter OFF
dp.callback_query.register(regenerate_cards_callback, F.data.startswith("gen_reg"))


# ========== COMMAND REGISTRATIONS ==========
for _cmd, _fn in [
    ("pw", pw_command), ("at", at_command), ("pf", pf_command),
    ("sh", sh_command),
    ("hc", hc_command), ("sp", sp_command),  # ("stco", stco_command),  # hitter OFF
    ("vbv", vbv_command),
    ("ft", ft_command), ("nmi", nmi_command), ("nmi2", nmi2_command), ("bl", bl_command),
    ("rz", rz_command), ("pyu", pyu_command), ("sub", sub_command), ("rc", rc_command),
    ("suball", suball_command), ("g_code", g_code_command), ("claim", claim_command),
    ("info", info_command), ("rsub", rsub_command), ("plan", plan_command),
    ("adcr", adcr_command), ("on", on_command), ("off", off_command),
    ("stats", stats_command), ("bin", binn_command), ("binn", binn_command),
    ("qfake", qfake_command), ("fake", fake_command), ("gen", gen_command), ("cl", cl_command), ("gate", gate_command), ("py", py_command),
    ("gmass", gmass_command), ("gatehelp", gatehelp_command), ("fakehelp", fakehelp_command), ("genhelp", genhelp_command),
]:
    dp.message.register(_fn, Command(_cmd))

setup_feedback_handler(dp)


# ========== MAIN ==========
def main():
    logging.info("Bot starting in Polling mode with COLORFUL BUTTONS (Primary Blue) and custom emoji icons.")
    logging.info("⚠️ NOTE: Color styling only works on callback buttons, NOT on URL buttons (Telegram API limitation).")
    dp.run_polling(bot, skip_updates=True)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        logging.info("Bot stopped.")
