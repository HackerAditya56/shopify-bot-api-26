import asyncio
import logging
from aiogram import types, Router
from database import (
    ALL_GATES,
    get_all_gate_status,
    is_known_gate,
    set_gate_status,
    set_gate_status_bulk,
)
import gifs

# 🔴 Replace with your Telegram user ID(s)
ADMINS = [8462705169]

router = Router()

_USAGE = (
    "❌ <b>Usage</b>\n"
    "<code>/on &lt;gate|all&gt;</code>  — enable a gate (or all)\n"
    "<code>/off &lt;gate|all&gt;</code> — disable a gate (or all)\n"
    "<code>/onall</code> / <code>/offall</code> — bulk mode\n"
    "<code>/gates</code> — list every gate with its status\n"
    "<code>/gif</code> / <code>/offgif</code> — show or hide result GIFs\n\n"
    "Example: <code>/off st</code>"
)

_BULK_WORDS = {"all", "allgates", "gates", "every", "everything"}


def _is_admin(user_id: int) -> bool:
    return user_id in ADMINS


def _usage_error(message: types.Message):
    return message.reply(_USAGE, parse_mode="HTML")


def _resolve_targets(arg: str):
    """Return (targets, error_text). error_text is None when valid."""
    arg = (arg or "").lower()
    if not arg:
        return None, "missing"
    if arg in _BULK_WORDS:
        return list(ALL_GATES), None
    if not is_known_gate(arg):
        return None, "unknown"
    return [arg], None


async def _apply_bulk(message: types.Message, enabled: bool):
    targets, _ = _resolve_targets("all")
    state = "ENABLED" if enabled else "UNDER MAINTENANCE"
    try:
        changed = await asyncio.to_thread(set_gate_status_bulk, enabled, targets)
    except Exception as e:
        logging.error(f"bulk gate {enabled}: {e}")
        await message.reply(
            f"❌ <b>Failed to update gates:</b> <code>{type(e).__name__}</code>\n"
            "Nothing was changed. Check the bot logs.",
            parse_mode="HTML",
        )
        return
    await message.reply(
        f"✅ <b>{len(changed)} gates are now {state}</b>\n\n"
        f"<code>{' '.join(changed)}</code>",
        parse_mode="HTML",
    )


async def _apply_single(message: types.Message, gate: str, enabled: bool):
    try:
        await asyncio.to_thread(set_gate_status, gate, enabled)
    except Exception as e:
        logging.error(f"set gate {gate}={enabled}: {e}")
        await message.reply(
            f"❌ <b>Failed to update gate:</b> <code>{type(e).__name__}</code>\n"
            "Nothing was changed. Check the bot logs.",
            parse_mode="HTML",
        )
        return
    await message.reply(
        f"✅ <b>{gate.upper()}</b> gate is now <b>ENABLED</b>" if enabled
        else f"🚧 <b>{gate.upper()}</b> gate is now <b>UNDER MAINTENANCE</b>",
        parse_mode="HTML",
    )


@router.message(lambda message: message.text and message.text.startswith("/onall"))
async def onall_command(message: types.Message):
    """Bulk mode: enable every gate at once."""
    if not _is_admin(message.from_user.id):
        return
    await _apply_bulk(message, True)


@router.message(lambda message: message.text and message.text.startswith("/offall"))
async def offall_command(message: types.Message):
    """Bulk mode: put every gate under maintenance at once."""
    if not _is_admin(message.from_user.id):
        return
    await _apply_bulk(message, False)


@router.message(lambda message: message.text and message.text.startswith("/offgif"))
async def offgif_command(message: types.Message):
    """Hide the reaction GIFs from single and mass gate result UIs."""
    if not _is_admin(message.from_user.id):
        return

    was_enabled = gifs.gifs_enabled()
    now_enabled = gifs.set_gifs_enabled(False)

    if now_enabled:
        # set_gifs_enabled could not apply the change (DB down).
        await message.reply(
            "❌ <b>Could not update the GIF setting.</b>\n"
            "The database is unreachable, so the toggle was not saved.",
            parse_mode="HTML",
        )
        return

    if was_enabled:
        await message.reply(
            "🎞 <b>GIFS are now HIDDEN.</b>\n\n"
            "Gate results will be sent as plain text with the same caption.",
            parse_mode="HTML",
        )
    else:
        await message.reply("🎞 <b>GIFS are already hidden.</b>", parse_mode="HTML")


@router.message(lambda message: message.text and message.text.startswith("/gif"))
async def gif_command(message: types.Message):
    """Show the reaction GIFs in single and mass gate result UIs."""
    if not _is_admin(message.from_user.id):
        return

    parts = (message.text or "").split()
    if len(parts) > 1 and parts[1].lower() in ("status", "info"):
        state = "ENABLED ✅" if gifs.gifs_enabled() else "DISABLED ❌"
        await message.reply(
            f"🎞 <b>GIF status ➺ {state}</b>\n\n"
            "<code>/gif</code> — show GIFs\n"
            "<code>/offgif</code> — hide GIFs",
            parse_mode="HTML",
        )
        return

    was_enabled = gifs.gifs_enabled()
    now_enabled = gifs.set_gifs_enabled(True)

    if not now_enabled:
        await message.reply(
            "❌ <b>Could not update the GIF setting.</b>\n"
            "The database is unreachable, so the toggle was not saved.",
            parse_mode="HTML",
        )
        return

    if was_enabled:
        await message.reply("🎞 <b>GIFS are already shown.</b>", parse_mode="HTML")
    else:
        await message.reply(
            "🎞 <b>GIFS are now SHOWN.</b>\n\n"
            "Gate results will be sent with the reaction GIF again.",
            parse_mode="HTML",
        )


@router.message(lambda message: message.text and message.text.startswith("/gates"))
async def gates_command(message: types.Message):
    """Show the live on/off status of every known gate."""
    if not _is_admin(message.from_user.id):
        return

    try:
        status = await asyncio.to_thread(get_all_gate_status)
    except Exception as e:
        logging.error(f"read gate status: {e}")
        await message.reply(
            f"❌ <b>Failed to read gate status:</b> <code>{type(e).__name__}</code>",
            parse_mode="HTML",
        )
        return

    on  = [g for g in ALL_GATES if status.get(g, True)]
    off = [g for g in ALL_GATES if not status.get(g, True)]

    lines = [
        "🎛 <b>𝐆𝐀𝐓𝐄 𝐒𝐓𝐀𝐓𝐔𝐒</b>",
        "━━━━━━━━━━━━━━━━━━━━━━",
        f"🟢 <b>ON ({len(on)})</b> ➠ <code>{' '.join(on) if on else '—'}</code>",
        "",
        f"🔴 <b>OFF ({len(off)})</b> ➠ <code>{' '.join(off) if off else '—'}</code>",
        "━━━━━━━━━━━━━━━━━━━━━━",
        f"<b>/offall</b> — disable all {len(ALL_GATES)} gates",
        f"<b>/onall</b>  — enable all {len(ALL_GATES)} gates",
        "━━━━━━━━━━━━━━━━━━━━━━",
        f"🎞 <b>GIFS ➺ {'ON ✅' if gifs.gifs_enabled() else 'OFF ❌'}</b>",
    ]
    await message.reply("\n".join(lines), parse_mode="HTML")


@router.message(lambda message: message.text and message.text.startswith("/on"))
async def on_command(message: types.Message):
    if not _is_admin(message.from_user.id):
        return

    parts = message.text.split()
    if len(parts) < 2:
        await _usage_error(message)
        return

    targets, err = _resolve_targets(parts[1])
    if err == "unknown":
        await message.reply(
            f"❌ <b>Unknown gate:</b> <code>{parts[1].lower()}</code>\n\n"
            f"Known gates: <code>{' '.join(ALL_GATES)}</code>\n"
            "Use <code>/gates</code> for live status.",
            parse_mode="HTML",
        )
        return

    if len(targets) > 1:
        await _apply_bulk(message, True)
        return

    gate = targets[0]
    await _apply_single(message, gate, True)


@router.message(lambda message: message.text and message.text.startswith("/off"))
async def off_command(message: types.Message):
    if not _is_admin(message.from_user.id):
        return

    parts = message.text.split()
    if len(parts) < 2:
        await _usage_error(message)
        return

    targets, err = _resolve_targets(parts[1])
    if err == "unknown":
        await message.reply(
            f"❌ <b>Unknown gate:</b> <code>{parts[1].lower()}</code>\n\n"
            f"Known gates: <code>{' '.join(ALL_GATES)}</code>\n"
            "Use <code>/gates</code> for live status.",
            parse_mode="HTML",
        )
        return

    if len(targets) > 1:
        await _apply_bulk(message, False)
        return

    gate = targets[0]
    await _apply_single(message, gate, False)
