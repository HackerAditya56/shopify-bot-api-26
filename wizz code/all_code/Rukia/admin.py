import os
import sys
import asyncio
import subprocess
import time
import logging
from aiogram import Router, F, types
from aiogram.exceptions import TelegramRetryAfter, TelegramForbiddenError, TelegramBadRequest
from aiogram.filters import Command
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from database import is_unlimited_msh, set_unlimited_msh
from sub import _resolve_user_id_sync, _ensure_user_for_admin_sync
from mass_gates.msh import MshForceStopCallback

router = Router()

# Admin IDs (must match the rest of the bot)
ADMIN_IDS = {8423281554}

# Premium Emoji IDs (provided by owner)
EMOJI_RED_TICK   = "6147565374289220368"
EMOJI_BLUE_TICK  = "5278628026416909103"
EMOJI_LIGHTNING  = "5219745609631674840"
EMOJI_STAR       = "5359686514697576863"
EMOJI_FIRE       = "6186076099764555777"
EMOJI_CROWN      = "6338940587193930733"
EMOJI_EPIC       = "6052994304715002242"
EMOJI_DRAGON     = "5440636718262804952"
EMOJI_GUN        = "5440406404936524730"
EMOJI_WHITE_STAR = "5247131412032670246"

# Stop button emoji (matches the one used inside /msh progress UI)
BTN_STOP_EMOJI_ID = "6179444193518162239"

_SEP = "━━━━━━━━━━━━━━━━"

# Admin command groups: (category, emoji_id, [(cmd, description), ...])
ADMIN_GROUPS = [
    (
        "User Management",
        EMOJI_GUN,
        [
            ("/ban",      "&lt;user_id&gt;  ➛  Ban a user"),
            ("/unban",    "&lt;user_id&gt;  ➛  Unban a user"),
            ("/sub",      "&lt;user|@username&gt; &lt;plan&gt;  ➛  Manual subscribe (core/elite/root)"),
            ("/rsub",     "&lt;user|@username&gt;  ➛  Remove subscription"),
            ("/suball",   "➛  List every premium subscriber"),
            ("/unlimitedchk", "&lt;user|@username&gt; [on|off]  ➛  Toggle unlimited /msh for a user"),
        ],
    ),
    (
        "Credits &amp; Plans",
        EMOJI_FIRE,
        [
            ("/adcr",     "&lt;user_id&gt; &lt;amount&gt;  ➛  Add credits"),
            ("/rc",       "&lt;receipt_id&gt;  ➛  Remove credits via receipt"),
            ("/gencodes", "&lt;count&gt; &lt;days&gt;  ➛  Generate premium access code"),
            ("/sessions", "  ➛  View &amp; force-stop active MSH sessions"),
        ],
    ),
    (
        "Broadcast &amp; Status",
        EMOJI_EPIC,
        [
            ("/broad",    "➛  Reply to any msg → broadcast to all users"),
            ("/vps",      "➛  Server health (RAM, CPU, disk, uptime, proxy pool)"),
            ("/apihealth","➛  Ping every Shopify API endpoint → up/down + latency"),
            ("/fb",       "➛  Reply to a hit → submit feedback (approval in channel)"),
        ],
    ),
    (
        "Sites",
        EMOJI_DRAGON,
        [
            ("/addsites", "➛  Check new URLs via API+proxies → add live, skip duplicates"),
            ("/checksite","➛  Audit sites.txt → keep live, remove dead"),
            ("/removeall","➛  Wipe every site from sites.txt at once"),
        ],
    ),
    (
        "Proxy Pool",
        EMOJI_LIGHTNING,
        [
            ("/prx",      "➛  Check pool → remove dead, keep live"),
            ("/prx",      "&lt;ip:port:user:pass ...&gt;  ➛  Check + add live ones to pool"),
            ("/prx",      "(reply to .txt)  ➛  Check + add live ones to pool"),
        ],
    ),
    (
        "System",
        EMOJI_CROWN,
        [
            ("/restart",  "➛  Restart the bot (spawns fresh process & exits current one)"),
        ],
    ),
] 


def _build_admin_text() -> str:
    crown = f'<tg-emoji emoji-id="{EMOJI_CROWN}">👑</tg-emoji>'
    blue_tick = f'<tg-emoji emoji-id="{EMOJI_BLUE_TICK}">✅</tg-emoji>'
    gun = f'<tg-emoji emoji-id="{EMOJI_GUN}">🔫</tg-emoji>'
    epic = f'<tg-emoji emoji-id="{EMOJI_EPIC}">✨</tg-emoji>'
    fire = f'<tg-emoji emoji-id="{EMOJI_FIRE}">🔥</tg-emoji>'

    lines = [
        f"{crown} <b>𝗔𝗗𝗠𝗜𝗡 𝗖𝗢𝗠𝗠𝗔𝗡𝗗𝗦</b> {crown}",
        _SEP,
        f"{gun} <b>Restricted:</b> Admin IDs only",
        f"{blue_tick} <b>Access:</b> Granted",
        _SEP,
    ]

    for cat_name, cat_emoji_id, entries in ADMIN_GROUPS:
        cat_emoji = f'<tg-emoji emoji-id="{cat_emoji_id}">✨</tg-emoji>'
        lines.append(f"{cat_emoji} <b>{cat_name}</b>")
        for cmd, desc in entries:
            lines.append(f"  <b>{fire} {cmd}</b>")
            lines.append(f"     <i>{desc}</i>")
        lines.append(_SEP)

    lines.append(
        f'<tg-emoji emoji-id="{EMOJI_CROWN}">👑</tg-emoji> '
        f'<b><a href="https://t.me/blacklistedcarder1">Blacklisted Carder</a></b> '
        f'{epic}'
    )
    return "\n".join(lines)


def _build_admin_kb() -> InlineKeyboardMarkup:
    rows = []
    # Quick action shortcuts
    rows.append([
        InlineKeyboardButton(
            text="📊 𝗩𝗣𝗦",
            callback_data="admin_quick_vps",
            style="primary",
            icon_custom_emoji_id=EMOJI_LIGHTNING,
        ),
    ])
    rows.append([
        InlineKeyboardButton(
            text="💎 𝗚𝗲𝗻𝗲𝗿𝗮𝘁𝗲 𝗖𝗼𝗱𝗲",
            callback_data="admin_quick_gcode",
            style="success",
            icon_custom_emoji_id=EMOJI_FIRE,
        ),
    ])
    rows.append([
        InlineKeyboardButton(
            text="📣 𝗕𝗿𝗼𝗮𝗱𝗰𝗮𝘀𝘁",
            callback_data="admin_quick_broad",
            style="primary",
            icon_custom_emoji_id=EMOJI_EPIC,
        ),
        InlineKeyboardButton(
            text="⭐ 𝗦𝘂𝗯𝗮𝗹𝗹",
            callback_data="admin_quick_suball",
            style="primary",
            icon_custom_emoji_id=EMOJI_WHITE_STAR,
        ),
    ])
    rows.append([
        InlineKeyboardButton(
            text="🔍 𝗔𝘂𝗱𝗶𝘁 𝗦𝗶𝘁𝗲𝘀",
            callback_data="admin_quick_checksite",
            style="primary",
            icon_custom_emoji_id=EMOJI_DRAGON,
        ),
        InlineKeyboardButton(
            text="⚡ 𝗣𝗿𝘅 𝗣𝗼𝗼𝗹",
            callback_data="admin_quick_prx",
            style="primary",
            icon_custom_emoji_id=EMOJI_LIGHTNING,
        ),
    ])
    rows.append([
        InlineKeyboardButton(
            text="🔄 𝗥𝗲𝘀𝘁𝗮𝗿𝘁",
            callback_data="admin_quick_restart",
            style="danger",
            icon_custom_emoji_id=EMOJI_LIGHTNING,
        ),
    ])
    rows.append([
        InlineKeyboardButton(
            text="« 𝗕𝗮𝗰𝗸",
            callback_data="back_main",
            style="danger",
            icon_custom_emoji_id=EMOJI_RED_TICK,
        ),
    ])
    return InlineKeyboardMarkup(inline_keyboard=rows)


_ADMIN_TEXT = _build_admin_text()
_ADMIN_KB = _build_admin_kb()


@router.message(Command("admin"))
async def admin_command(message: types.Message):
    user_id = message.from_user.id
    if user_id not in ADMIN_IDS:
        red = f'<tg-emoji emoji-id="{EMOJI_RED_TICK}">❌</tg-emoji>'
        await message.reply(
            f"{red} <b>𝗔𝗰𝗰𝗲𝘀𝘀 𝗗𝗲𝗻𝗶𝗲𝗱.</b>\n\n"
            f"This command is restricted to admins only.",
            parse_mode="HTML",
        )
        return
    await message.reply(
        text=_ADMIN_TEXT,
        parse_mode="HTML",
        reply_markup=_ADMIN_KB,
        disable_web_page_preview=True,
    )


# Quick action buttons — all admin-only
@router.callback_query(F.data == "admin_quick_vps")
async def admin_vps_cb(callback: types.CallbackQuery):
    if callback.from_user.id not in ADMIN_IDS:
        await callback.answer("❌ Admin only", show_alert=True)
        return
    await callback.answer("💎 Tap /vps to view server status.", show_alert=True)


@router.callback_query(F.data == "admin_quick_gcode")
async def admin_gcode_cb(callback: types.CallbackQuery):
    if callback.from_user.id not in ADMIN_IDS:
        await callback.answer("❌ Admin only", show_alert=True)
        return
    await callback.answer(
        "💎 Use:\n<code>/gencodes 10 1</code>\n"
        "→ 10 premium codes, 1 day each",
        show_alert=True,
    )


@router.callback_query(F.data == "admin_quick_broad")
async def admin_broad_cb(callback: types.CallbackQuery):
    if callback.from_user.id not in ADMIN_IDS:
        await callback.answer("❌ Admin only", show_alert=True)
        return
    await callback.answer(
        "📣 Reply to any message with /broad to broadcast.",
        show_alert=True,
    )


@router.callback_query(F.data == "admin_quick_suball")
async def admin_suball_cb(callback: types.CallbackQuery):
    if callback.from_user.id not in ADMIN_IDS:
        await callback.answer("❌ Admin only", show_alert=True)
        return
    await callback.answer("⭐ Tap /suball to list subscribers.", show_alert=True)


@router.callback_query(F.data == "admin_quick_checksite")
async def admin_checksite_cb(callback: types.CallbackQuery):
    if callback.from_user.id not in ADMIN_IDS:
        await callback.answer("❌ Admin only", show_alert=True)
        return
    await callback.answer("🔍 Tap /checksite to audit sites.txt.", show_alert=True)


@router.callback_query(F.data == "admin_quick_prx")
async def admin_prx_cb(callback: types.CallbackQuery):
    if callback.from_user.id not in ADMIN_IDS:
        await callback.answer("❌ Admin only", show_alert=True)
        return
    await callback.answer(
        "⚡ Use:\n"
        "<code>/prx</code> — check pool\n"
        "<code>/prx ip:port:user:pass ...</code> — add\n"
        "or reply to a .txt file with /prx",
        show_alert=True,
    )


@router.callback_query(F.data == "admin_quick_restart")
async def admin_restart_cb(callback: types.CallbackQuery):
    if callback.from_user.id not in ADMIN_IDS:
        await callback.answer("❌ Admin only", show_alert=True)
        return
    await callback.answer(
        "🔄 Tap /restart to spawn a fresh bot process & exit the current one.",
        show_alert=True,
    )


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# /restart — Spawn a fresh bot process and exit current one
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
@router.message(Command("restart"))
async def restart_command(message: types.Message):
    if message.from_user.id not in ADMIN_IDS:
        red = f'<tg-emoji emoji-id="{EMOJI_RED_TICK}">❌</tg-emoji>'
        await message.reply(
            f"{red} <b>𝗔𝗰𝗰𝗲𝘀𝘀 𝗗𝗲𝗻𝗶𝗲𝗱.</b>\n\n"
            f"Admin only command.",
            parse_mode="HTML",
        )
        return

    crown = f'<tg-emoji emoji-id="{EMOJI_CROWN}">👑</tg-emoji>'
    lightning = f'<tg-emoji emoji-id="{EMOJI_LIGHTNING}">⚡</tg-emoji>'
    epic = f'<tg-emoji emoji-id="{EMOJI_EPIC}">✨</tg-emoji>'

    await message.reply(
        f"{crown} <b>𝗥𝗘𝗦𝗧𝗔𝗥𝗧𝗜𝗡𝗚 𝗕𝗢𝗧...</b>\n"
        f"{_SEP}\n"
        f"{lightning} <b>Stopping polling & spawning fresh process.</b>\n"
        f"{epic} <i>Bot will be back online in a moment.</i>\n"
        f"{_SEP}\n"
        f"{crown} <b><a href=\"https://t.me/blacklistedcarder1\">Blacklisted Carder</a></b>",
        parse_mode="HTML",
        disable_web_page_preview=True,
    )

    # Stop the current polling loop FIRST so Telegram releases the getUpdates
    # slot. Otherwise the new process and the old one collide → ConflictError.
    try:
        await router.parent_dispatcher.stop_polling()
    except Exception:
        try:
            from main import dp as _main_dp
            await _main_dp.stop_polling()
        except Exception:
            pass

    # Give Telegram a moment to release the slot before the new process polls
    await asyncio.sleep(2.0)

    args = [sys.executable] + sys.argv
    cwd = os.getcwd()

    try:
        if os.name == "nt":
            subprocess.Popen(
                args,
                cwd=cwd,
                stdin=None,
                stdout=None,
                stderr=None,
                creationflags=subprocess.CREATE_NEW_PROCESS_GROUP
                | subprocess.DETACHED_PROCESS,
                close_fds=True,
            )
        else:
            subprocess.Popen(
                args,
                cwd=cwd,
                stdin=None,
                stdout=None,
                stderr=None,
                start_new_session=True,
                close_fds=True,
            )
    except Exception as e:
        await message.reply(
            f'<tg-emoji emoji-id="{EMOJI_RED_TICK}">❌</tg-emoji> '
            f"<b>Restart failed:</b> <code>{e}</code>",
            parse_mode="HTML",
        )
        return

    os._exit(0)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# /unlimitedchk — Toggle unlimited /msh for a user
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Usage:
#   /unlimitedchk <user_id|@username>          → toggle on/off
#   /unlimitedchk <user_id|@username> on       → force ON
#   /unlimitedchk <user_id|@username> off      → force OFF
#
# When ON, that user can run /msh with any number of cards and
# no credits are deducted (admins already have this by default).
@router.message(Command("unlimitedchk"))
async def unlimitedchk_command(message: types.Message):
    red   = f'<tg-emoji emoji-id="{EMOJI_RED_TICK}">❌</tg-emoji>'
    green = f'<tg-emoji emoji-id="{EMOJI_BLUE_TICK}">✅</tg-emoji>'
    star  = f'<tg-emoji emoji-id="{EMOJI_WHITE_STAR}">⭐</tg-emoji>'

    if message.from_user.id not in ADMIN_IDS:
        await message.reply(
            f"{red} <b>𝗔𝗰𝗰𝗲𝘀𝘀 𝗗𝗲𝗻𝗶𝗲𝗱.</b>\n\nAdmin only command.",
            parse_mode="HTML",
        )
        return

    args = message.text.split()[1:]
    if not args:
        await message.reply(
            f"{red} <b>𝗨𝘀𝗮𝗴𝗲:</b>\n"
            f"<code>/unlimitedchk &lt;user_id|@username&gt;</code> — toggle\n"
            f"<code>/unlimitedchk &lt;user_id|@username&gt; on</code> — force ON\n"
            f"<code>/unlimitedchk &lt;user_id|@username&gt; off</code> — force OFF",
            parse_mode="HTML",
        )
        return

    target_input = args[0]
    explicit = args[1].lower() if len(args) > 1 else None
    if explicit not in (None, "on", "off"):
        await message.reply(
            f"{red} <b>Invalid flag:</b> <code>{html_escape(explicit)}</code>\n"
            f"Use <code>on</code> or <code>off</code>, or omit to toggle.",
            parse_mode="HTML",
        )
        return

    # Resolve target → user_id (numeric or @username)
    target_id = await asyncio.to_thread(_resolve_user_id_sync, target_input)
    if not target_id and target_input.startswith("@"):
        try:
            chat = await message.bot.get_chat(target_input)
            target_id = chat.id
            try:
                await asyncio.to_thread(
                    _ensure_user_for_admin_sync,
                    target_id,
                    chat.username or "",
                    chat.first_name or "User",
                )
            except Exception as db_e:
                logging.error(f"[unlimitedchk] pre-create user failed: {db_e}")
        except Exception as tg_e:
            logging.warning(f"[unlimitedchk] could not resolve @username: {tg_e}")
    if not target_id:
        await message.reply(
            f"{red} <b>𝗖𝗼𝘂𝗹𝗱 𝗻𝗼𝘁 𝗳𝗶𝗻𝗱 𝘂𝘀𝗲𝗿.</b>\n"
            f"User must have <code>/start</code>ed the bot, or be reachable via <code>@username</code>.",
            parse_mode="HTML",
        )
        return

    # Decide new value
    current = await asyncio.to_thread(is_unlimited_msh, target_id)
    if explicit == "on":
        new_val = True
    elif explicit == "off":
        new_val = False
    else:
        new_val = not current

    # Admins are already unlimited — clarify that to the admin
    if target_id in ADMIN_IDS and not new_val:
        await message.reply(
            f"{star} <b>Note:</b> <code>{target_id}</code> is an admin and already has unlimited /msh.\n"
            f"Toggle ignored (admins can't be downgraded by this command).",
            parse_mode="HTML",
        )
        return

    await asyncio.to_thread(set_unlimited_msh, target_id, new_val)

    # Friendly display name
    display_name = str(target_id)
    try:
        chat = await message.bot.get_chat(target_id)
        display_name = (
            f'<a href="tg://user?id={target_id}">{html_escape(chat.first_name or chat.username or "User")}</a>'
        )
    except Exception:
        display_name = f'<code>{target_id}</code>'

    state_txt = "𝗘𝗡𝗔𝗕𝗟𝗘𝗗 ✅" if new_val else "𝗗𝗜𝗦𝗔𝗕𝗟𝗘𝗗 ❌"
    icon = green if new_val else red

    # Notify the user via DM (best-effort)
    try:
        await message.bot.send_message(
            chat_id=target_id,
            text=(
                f"{icon} <b>𝗠𝗦𝗛 𝗨𝗻𝗹𝗶𝗺𝗶𝘁𝗲𝗱 ➛ {state_txt}</b>\n\n"
                + ("You can now run <code>/msh</code> with any number of cards — no credits will be deducted."
                   if new_val else
                   "Your <code>/msh</code> unlimited access has been revoked. Credits will now be deducted as usual.")
            ),
            parse_mode="HTML",
        )
    except Exception as e:
        logging.warning(f"[unlimitedchk] could not DM user {target_id}: {e}")

    crown = f'<tg-emoji emoji-id="{EMOJI_CROWN}">👑</tg-emoji>'
    await message.reply(
        f"{icon} <b>𝗠𝗦𝗛 𝗨𝗻𝗹𝗶𝗺𝗶𝘁𝗲𝗱 ➛ {state_txt}</b>\n"
        f"{_SEP}\n"
        f"𝗨𝘀𝗲𝗿 ➛ {display_name}\n"
        f"<code>{target_id}</code>\n"
        f"𝗣𝗿𝗲𝘃𝗶𝗼𝘂𝘀 ➛ {'✅ ON' if current else '❌ OFF'}\n"
        f"𝗡𝗲𝘄 ➛ {'✅ ON' if new_val else '❌ OFF'}\n"
        f"{_SEP}\n"
        f"{crown}",
        parse_mode="HTML",
        disable_web_page_preview=True,
    )


def html_escape(s: str) -> str:
    """Minimal HTML escape for safe insertion into parse_mode='HTML' text."""
    return (
        str(s)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# /sessions — List active /msh sessions + admin force-stop
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def _build_sessions_text_and_kb():
    """
    Build the /sessions list payload from MSH_SESSIONS.
    Returns (text, InlineKeyboardMarkup | None).
    """
    import time as _time
    from mass_gates.msh import MSH_SESSIONS, MshForceStopCallback

    crown = f'<tg-emoji emoji-id="{EMOJI_CROWN}">👑</tg-emoji>'
    fire  = f'<tg-emoji emoji-id="{EMOJI_FIRE}">🔥</tg-emoji>'
    red   = f'<tg-emoji emoji-id="{EMOJI_RED_TICK}">❌</tg-emoji>'

    checking = [(sid, s) for sid, s in MSH_SESSIONS.items() if s.get("status") == "CHECKING"]
    finished = [(sid, s) for sid, s in MSH_SESSIONS.items() if s.get("status") in ("STOPPED", "FINISHED")]
    checking.sort(key=lambda kv: kv[1].get("start_time", 0), reverse=True)
    finished.sort(key=lambda kv: kv[1].get("start_time", 0), reverse=True)
    finished = finished[:5]

    lines = [f"{crown} <b>𝗔𝗰𝘁𝗶𝘃𝗲 𝗦𝗲𝘀𝘀𝗶𝗼𝗻𝘀</b>", _SEP]

    if checking:
        lines.append(f"{fire} <b>𝗠𝗦𝗛 𝗥𝘂𝗻𝗻𝗶𝗻𝗴 ➛</b> <code>{len(checking)}</code>")
        for idx, (sid, sess) in enumerate(checking, 1):
            user_obj = sess.get("user_obj")
            uid = sess.get("user_id", "?")
            name = html_escape(getattr(user_obj, "first_name", "") or "User")
            uname = getattr(user_obj, "username", None)
            user_link = (
                f'<a href="https://t.me/{html_escape(uname)}">{name}</a>'
                if uname else f'<a href="tg://user?id={uid}">{name}</a>'
            )

            checked  = sess.get("checked", 0)
            total    = sess.get("total", 0)
            approved = sess.get("approved", 0)
            charged  = sess.get("charged", 0)
            errors   = sess.get("errors", 0)

            start_t = sess.get("start_time", 0)
            if start_t:
                elapsed = int(_time.time() - start_t)
                elapsed_str = f"{elapsed // 60}m {elapsed % 60}s" if elapsed >= 60 else f"{elapsed}s"
            else:
                elapsed_str = "—"

            lines.append(
                f"<b>{idx}.</b> {user_link} <code>{uid}</code>\n"
                f"    <b>Session ➛</b> <code>{sid}</code>\n"
                f"    <b>Progress ➛</b> <code>{checked}/{total}</code> · "
                f"✅<b>{approved}</b> 💎<b>{charged}</b> ❌<b>{errors}</b>\n"
                f"    <b>Running ➛</b> <i>{elapsed_str}</i>"
            )
    else:
        lines.append(f"{red} <b>No active MSH sessions.</b>")

    lines.append(_SEP)

    if finished:
        lines.append(f"<i>Recent finished / stopped (last {len(finished)}):</i>")
        for idx, (sid, sess) in enumerate(finished, 1):
            user_obj = sess.get("user_obj")
            uid = sess.get("user_id", "?")
            name = html_escape(getattr(user_obj, "first_name", "") or "User")
            uname = getattr(user_obj, "username", None)
            user_link = (
                f'<a href="https://t.me/{html_escape(uname)}">{name}</a>'
                if uname else f'<a href="tg://user?id={uid}">{name}</a>'
            )
            lines.append(
                f"<b>{idx}.</b> {user_link} <code>{uid}</code> · "
                f"<code>{sid}</code> · <i>{sess.get('status', '?')}</i>"
            )
        lines.append(_SEP)

    lines.append(f"{crown} <b><a href=\"https://t.me/blacklistedcarder1\">Blacklisted Carder</a></b>")

    rows = []
    for sid, _ in checking:
        rows.append([
            InlineKeyboardButton(
                text=f"🛑 Stop {sid}",
                callback_data=MshForceStopCallback(session_id=sid).pack(),
                style="danger",
                icon_custom_emoji_id=BTN_STOP_EMOJI_ID,
            ),
        ])
    rows.append([
        InlineKeyboardButton(
            text="🔄 Refresh",
            callback_data="admin_refresh_sessions",
            style="primary",
            icon_custom_emoji_id=EMOJI_LIGHTNING,
        ),
    ])

    return "\n".join(lines), InlineKeyboardMarkup(inline_keyboard=rows)


@router.message(Command("sessions"))
async def sessions_command(message: types.Message):
    if message.from_user.id not in ADMIN_IDS:
        await message.reply(
            f'<tg-emoji emoji-id="{EMOJI_RED_TICK}">❌</tg-emoji> '
            f"<b>𝗔𝗰𝗰𝗲𝘀𝘀 𝗗𝗲𝗻𝗶𝗲𝗱.</b>\n\nAdmin only command.",
            parse_mode="HTML",
        )
        return

    text, kb = _build_sessions_text_and_kb()
    try:
        await message.reply(
            text,
            parse_mode="HTML",
            reply_markup=kb,
            disable_web_page_preview=True,
        )
    except TelegramRetryAfter as e:
        retry_s = getattr(e, "retry_after", 5) or 5
        logging.info(
            f"[admin /sessions] Telegram flood control — "
            f"retrying in {retry_s}s"
        )
        await asyncio.sleep(retry_s + 0.5)
        try:
            await message.reply(
                text,
                parse_mode="HTML",
                reply_markup=kb,
                disable_web_page_preview=True,
            )
        except Exception as e2:
            logging.error(f"[admin /sessions] retry failed: {e2}")
    except (TelegramForbiddenError, TelegramBadRequest) as e:
        logging.warning(f"[admin /sessions] send failed: {e}")
    except Exception as e:
        logging.error(f"[admin /sessions] unexpected error: {e}")


@router.callback_query(F.data == "admin_refresh_sessions")
async def admin_refresh_sessions_cb(callback: types.CallbackQuery):
    if callback.from_user.id not in ADMIN_IDS:
        await callback.answer("❌ Admin only", show_alert=True)
        return
    try:
        text, kb = _build_sessions_text_and_kb()
        await callback.message.edit_text(
            text,
            parse_mode="HTML",
            reply_markup=kb,
            disable_web_page_preview=True,
        )
        # Count running sessions for the alert text
        running = text.count("MSH Running")  # cheap heuristic
        await callback.answer("🔄 Refreshed")
    except TelegramRetryAfter as e:
        retry_s = getattr(e, "retry_after", 5) or 5
        await asyncio.sleep(retry_s + 0.5)
        try:
            await callback.answer(f"⚠️ Flood control — retry in {retry_s}s", show_alert=True)
        except Exception:
            pass
    except Exception as e:
        try:
            await callback.answer(f"❌ {e}", show_alert=True)
        except Exception:
            pass


@router.callback_query(MshForceStopCallback.filter())
async def admin_force_stop_cb(callback: types.CallbackQuery, callback_data: MshForceStopCallback):
    if callback.from_user.id not in ADMIN_IDS:
        await callback.answer("❌ Admin only", show_alert=True)
        return

    from mass_gates.msh import MSH_SESSIONS, update_progress_message

    sid = callback_data.session_id
    sess = MSH_SESSIONS.get(sid)
    if not sess:
        try:
            await callback.answer(f"❌ Session {sid} not found", show_alert=True)
        except Exception:
            pass
        return

    if sess.get("status") in ("STOPPED", "FINISHED"):
        try:
            await callback.answer(f"⚠️ Session already {sess['status']}", show_alert=True)
        except Exception:
            pass
        # Still re-render so the button is gone if the session finished naturally
        try:
            text, kb = _build_sessions_text_and_kb()
            await callback.message.edit_text(text, parse_mode="HTML", reply_markup=kb, disable_web_page_preview=True)
        except Exception:
            pass
        return

    # ── Force-stop the session ──
    sess["status"] = "STOPPED"
    for task in sess.get("tasks", []):
        if not task.done():
            task.cancel()

    # Update the user's progress message so they see STOPPED
    try:
        await update_progress_message(callback.bot, sid)
    except Exception as e:
        logging.error(f"[admin-force-stop] update_progress_message failed: {e}")

    # Notify the admin
    try:
        user_obj = sess.get("user_obj")
        uid = sess.get("user_id", "?")
        name = getattr(user_obj, "first_name", "") or "User"
        await callback.answer(
            f"🛑 Stopped {sid}\n{name} ({uid})",
            show_alert=True,
        )
    except Exception:
        pass

    # Re-render the /sessions list with the stopped session removed
    try:
        text, kb = _build_sessions_text_and_kb()
        await callback.message.edit_text(
            text,
            parse_mode="HTML",
            reply_markup=kb,
            disable_web_page_preview=True,
        )
    except Exception as e:
        logging.error(f"[admin-force-stop] edit_text failed: {e}")


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# /apihealth — Ping every Shopify API endpoint (admin only)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Usage:
#   /apihealth        → probe every URL in SHOPIFY_API_URLS, report up/down + latency
#
# Probes the well-known `/health` endpoint first with a short timeout. If that
# fails (404 / timeout / non-2xx) we fall back to the actual `/check` endpoint
# with a minimal invalid card — that path is what real /msh traffic hits, so
# it's the truest signal of "is the API actually working for users right now".
async def _probe_one_api(api_url: str, timeout_s: float = 6.0) -> dict:
    """
    Probe a single Shopify API endpoint. Returns dict with:
        url, host, ok, status, latency_ms, detail
    `ok` is True only when the endpoint actually responds with 2xx (or returns
    a well-formed /health JSON like `{"status":"running"}`).
    """
    from urllib.parse import urlparse

    host = urlparse(api_url).netloc or api_url
    parsed = urlparse(api_url)
    base = f"{parsed.scheme}://{parsed.netloc}"

    # Lazy import so this module can be loaded even if aiohttp is in a weird state
    try:
        import aiohttp
    except Exception as e:
        return {
            "url": api_url, "host": host, "ok": False,
            "status": None, "latency_ms": 0.0,
            "detail": f"aiohttp missing: {e}",
        }

    session = None

    timeout = aiohttp.ClientTimeout(total=timeout_s)
    started = time.monotonic()


    # ── 1) Try /health ──
    try:
        async with aiohttp.ClientSession(timeout=timeout) as s:
            async with s.get(f"{base}/health") as r:
                body = await r.text()
                latency_ms = (time.monotonic() - started) * 1000.0
                if 200 <= r.status < 300:
                    # Treat well-formed JSON as healthy even if it doesn't say "ok"
                    ok = True
                    detail = f"HTTP {r.status}"
                    try:
                        import json as _json
                        data = _json.loads(body)
                        if isinstance(data, dict):
                            if "status" in data:
                                detail = f"HTTP {r.status} · status=<code>{html_escape(str(data['status']))}</code>"
                                ok = str(data.get("status", "")).lower() not in ("down", "error", "stopped")
                            elif "ok" in data:
                                detail = f"HTTP {r.status} · ok=<code>{data['ok']}</code>"
                                ok = bool(data.get("ok"))
                    except Exception:
                        pass
                    return {
                        "url": api_url, "host": host, "ok": ok,
                        "status": r.status, "latency_ms": latency_ms,
                        "detail": detail,
                    }
                # Non-2xx from /health → fall through to /check
                health_status = r.status
                health_latency = latency_ms
    except (asyncio.TimeoutError, aiohttp.ClientError, Exception) as e:
        health_status = None
        health_latency = (time.monotonic() - started) * 1000.0
        health_err = f"{type(e).__name__}: {e}"

    # ── 2) Fallback: hit the real /check path with a known-bad card ──
    # We only consider the endpoint "working" if it returns a JSON body (any
    # structured response means the backend is alive — even an "INVALID_CARD"
    # reply proves the API processed our request).
    try:
        from shopify_api import _build_params
        params = _build_params(
            "4000000000000002|12|99|999",  # known-decline test card
            "https://example.com",
            "http://127.0.0.1:1",          # dummy proxy — backend will likely ignore or fast-fail
            None,
        )
        started = time.monotonic()
        async with aiohttp.ClientSession(timeout=timeout) as s:
            async with s.get(api_url, params=params) as r:
                body = await r.text()
                latency_ms = (time.monotonic() - started) * 1000.0
                ok = False
                detail = f"HTTP {r.status}"
                try:
                    import json as _json
                    data = _json.loads(body)
                    if isinstance(data, dict):
                        ok = True
                        # Show the normalised Status if backend provided one
                        st = data.get("Status") or data.get("status") or data.get("Response")
                        if st:
                            detail = f"HTTP {r.status} · reply=<code>{html_escape(str(st)[:60])}</code>"
                        else:
                            detail = f"HTTP {r.status} · JSON OK"
                except Exception:
                    pass
                return {
                    "url": api_url, "host": host, "ok": ok,
                    "status": r.status, "latency_ms": latency_ms,
                    "detail": detail,
                }
    except asyncio.TimeoutError:
        return {
            "url": api_url, "host": host, "ok": False,
            "status": None, "latency_ms": (time.monotonic() - started) * 1000.0,
            "detail": f"timeout after {timeout_s:.0f}s",
        }
    except Exception as e:
        return {
            "url": api_url, "host": host, "ok": False,
            "status": None, "latency_ms": (time.monotonic() - started) * 1000.0,
            "detail": f"{type(e).__name__}: {html_escape(str(e))[:120]}",
        }


def _build_apihealth_text_and_kb(results: list, breaker: dict):
    """
    Render the /apihealth report. Returns (text, InlineKeyboardMarkup).
    results: list of dicts from _probe_one_api()
    breaker: dict from shopify_api._breaker_stats() + state
    """
    crown   = f'<tg-emoji emoji-id="{EMOJI_CROWN}">👑</tg-emoji>'
    fire    = f'<tg-emoji emoji-id="{EMOJI_FIRE}">🔥</tg-emoji>'
    green   = f'<tg-emoji emoji-id="{EMOJI_BLUE_TICK}">✅</tg-emoji>'
    red     = f'<tg-emoji emoji-id="{EMOJI_RED_TICK}">❌</tg-emoji>'
    lightning = f'<tg-emoji emoji-id="{EMOJI_LIGHTNING}">⚡</tg-emoji>'
    epic    = f'<tg-emoji emoji-id="{EMOJI_EPIC}">✨</tg-emoji>'

    up_count   = sum(1 for r in results if r["ok"])
    down_count = len(results) - up_count
    overall_ok = down_count == 0 and len(results) > 0
    overall_icon = green if overall_ok else red
    overall_txt  = "ALL 𝗨𝗣 ✅" if overall_ok else f"{down_count} DOWN ❌"

    import time as _t
    stamp = _t.strftime("%Y-%m-%d %H:%M:%S")

    lines = [
        f"{crown} <b>𝗔𝗣𝗜 𝗛𝗘𝗔𝗟𝗧𝗛</b> {crown}",
        _SEP,
        f"{overall_icon} <b>Overall ➛</b> {overall_txt}",
        f"{fire} <b>Endpoints ➛</b> <code>{up_count}</code> up · <code>{down_count}</code> down",
        f"{lightning} <b>Checked ➛</b> <i>{stamp}</i>",
        _SEP,
    ]

    for idx, r in enumerate(results, 1):
        icon = green if r["ok"] else red
        latency = r["latency_ms"]
        if latency >= 1000:
            lat_str = f"{latency / 1000:.2f}s"
        else:
            lat_str = f"{latency:.0f}ms"
        status = r["status"] if r["status"] is not None else "—"
        lines.append(
            f"{icon} <b>{idx}.</b> <code>{html_escape(r['host'])}</code>\n"
            f"    <b>HTTP ➛</b> <code>{status}</code>\n"
            f"    <b>Latency ➛</b> <code>{lat_str}</code>\n"
            f"    <i>{r['detail']}</i>"
        )

    lines.append(_SEP)

    # Breaker snapshot (best-effort — shopify_api may not be importable here)
    bstate = breaker.get("state", "—")
    bicon = green if bstate == "CLOSED" else (fire if bstate == "HALF_OPEN" else red)
    lines.append(
        f"{epic} <b>𝗖𝗶𝗿𝗰𝘂𝗶𝘁 𝗕𝗿𝗲𝗮𝗸𝗲𝗿 ➛</b> {bicon} <code>{html_escape(str(bstate))}</code>\n"
        f"    <b>Samples (30s) ➛</b> <code>{breaker.get('samples', 0)}</code>\n"
        f"    <b>Fail rate ➛</b> <code>{breaker.get('fail_rate', 0.0) * 100:.1f}%</code>\n"
        f"    <b>Avg latency ➛</b> <code>{breaker.get('avg_ms', 0.0) / 1000:.2f}s</code>"
    )
    lines.append(_SEP)
    lines.append(
        f'{crown} <b><a href="https://t.me/blacklistedcarder1">Blacklisted Carder</a></b>'
    )

    rows = [
        [InlineKeyboardButton(
            text="🔄 𝗥𝗲𝗳𝗿𝗲𝘀𝗵",
            callback_data="admin_refresh_apihealth",
            style="primary",
            icon_custom_emoji_id=EMOJI_LIGHTNING,
        )],
    ]
    return "\n".join(lines), InlineKeyboardMarkup(inline_keyboard=rows)


def _collect_breaker_snapshot() -> dict:
    """Best-effort pull of breaker state from shopify_api. Returns safe defaults.

    The breaker is now per-API (keyed by index); we aggregate the worst
    state across all APIs and sum samples so the /apihealth report still
    shows a single coherent snapshot.
    """
    snap = {"state": "UNKNOWN", "samples": 0, "fail_rate": 0.0, "avg_ms": 0.0}
    try:
        import shopify_api as _sa
        snap["state"] = _sa.get_global_breaker_state()
        # Aggregate samples across every API index that has data.
        total_n = 0
        total_fail = 0
        total_ms = 0.0
        for idx in range(len(_sa.SHOPIFY_API_URLS)):
            try:
                n, fr, avg = _sa._breaker_stats(idx)
                if n > 0:
                    fail = int(round(fr * n))
                    total_n += n
                    total_fail += fail
                    total_ms += avg * n
            except Exception:
                continue
        if total_n > 0:
            snap["samples"] = total_n
            snap["fail_rate"] = total_fail / total_n
            snap["avg_ms"] = total_ms / total_n
    except Exception as e:
        logging.debug(f"[apihealth] breaker snapshot unavailable: {e}")
    return snap


@router.message(Command("apihealth"))
async def apihealth_command(message: types.Message):
    red   = f'<tg-emoji emoji-id="{EMOJI_RED_TICK}">❌</tg-emoji>'
    crown = f'<tg-emoji emoji-id="{EMOJI_CROWN}">👑</tg-emoji>'

    if message.from_user.id not in ADMIN_IDS:
        await message.reply(
            f"{red} <b>𝗔𝗰𝗰𝗲𝘀𝘀 𝗗𝗲𝗻𝗶𝗲𝗱.</b>\n\nAdmin only command.",
            parse_mode="HTML",
        )
        return

    # Send "checking…" placeholder so the user sees something instantly
    sent = await message.reply(
        f"{crown} <b>𝗔𝗣𝗜 𝗛𝗘𝗔𝗟𝗧𝗛</b> {crown}\n{_SEP}\n"
        f"<i>Probing endpoints…</i>",
        parse_mode="HTML",
    )

    try:
        from shopify_api import SHOPIFY_API_URLS
    except Exception as e:
        try:
            await sent.edit_text(
                f"{red} <b>𝗖𝗼𝘂𝗹𝗱 𝗻𝗼𝘁 𝗹𝗼𝗮𝗱 <code>shopify_api</code>:</b>\n"
                f"<code>{html_escape(str(e))}</code>",
                parse_mode="HTML",
            )
        except Exception:
            pass
        return

    if not SHOPIFY_API_URLS:
        try:
            await sent.edit_text(
                f"{red} <b>No API endpoints configured</b> (SHOPIFY_API_URLS is empty).",
                parse_mode="HTML",
            )
        except Exception:
            pass
        return

    # Probe each endpoint in parallel
    probes = await asyncio.gather(
        *[_probe_one_api(url) for url, _ in SHOPIFY_API_URLS],
        return_exceptions=False,
    )
    breaker = _collect_breaker_snapshot()
    text, kb = _build_apihealth_text_and_kb(list(probes), breaker)

    try:
        await sent.edit_text(
            text,
            parse_mode="HTML",
            reply_markup=kb,
            disable_web_page_preview=True,
        )
    except TelegramRetryAfter as e:
        retry_s = getattr(e, "retry_after", 5) or 5
        logging.info(f"[admin /apihealth] Telegram flood — retrying in {retry_s}s")
        await asyncio.sleep(retry_s + 0.5)
        try:
            await sent.edit_text(
                text,
                parse_mode="HTML",
                reply_markup=kb,
                disable_web_page_preview=True,
            )
        except Exception as e2:
            logging.error(f"[admin /apihealth] retry failed: {e2}")
    except (TelegramForbiddenError, TelegramBadRequest) as e:
        logging.warning(f"[admin /apihealth] send failed: {e}")
    except Exception as e:
        logging.error(f"[admin /apihealth] unexpected error: {e}")


@router.callback_query(F.data == "admin_refresh_apihealth")
async def admin_refresh_apihealth_cb(callback: types.CallbackQuery):
    if callback.from_user.id not in ADMIN_IDS:
        await callback.answer("❌ Admin only", show_alert=True)
        return

    try:
        from shopify_api import SHOPIFY_API_URLS
        if not SHOPIFY_API_URLS:
            await callback.answer("❌ No endpoints configured", show_alert=True)
            return
        probes = await asyncio.gather(
            *[_probe_one_api(url) for url, _ in SHOPIFY_API_URLS],
        )
        breaker = _collect_breaker_snapshot()
        text, kb = _build_apihealth_text_and_kb(list(probes), breaker)
        await callback.message.edit_text(
            text,
            parse_mode="HTML",
            reply_markup=kb,
            disable_web_page_preview=True,
        )
        up = sum(1 for r in probes if r["ok"])
        await callback.answer(f"🔄 {up}/{len(probes)} up")
    except TelegramRetryAfter as e:
        retry_s = getattr(e, "retry_after", 5) or 5
        await asyncio.sleep(retry_s + 0.5)
        try:
            await callback.answer(f"⚠️ Flood control — retry in {retry_s}s", show_alert=True)
        except Exception:
            pass
    except Exception as e:
        try:
            await callback.answer(f"❌ {e}", show_alert=True)
        except Exception:
            pass
