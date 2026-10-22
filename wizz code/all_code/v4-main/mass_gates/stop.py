import logging
import asyncio

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# AIOGRAM IMPORTS
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
from aiogram import types, F, Router

router = Router()

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# IMPORTS (SHARED STATE FROM ALL GATE MODULES)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

# ── MRZ (Mass Razorpay) ──────────────────────────────────────────────────────
try:
    from mass_gates.mrz import MRZ_SESSIONS, update_progress_message as update_mrz_message
except ImportError:
    logging.warning("[STOP] Error importing from mrz.py.")
    MRZ_SESSIONS     = {}
    update_mrz_message = None

# ── MSH (Mass Shopify / SK-based) ────────────────────────────────────────────
try:
    from mass_gates.msh import MSH_SESSIONS, update_progress_message as update_msh_message
except ImportError:
    logging.warning("[STOP] Error importing from msh.py.")
    MSH_SESSIONS      = {}
    update_msh_message = None

# ── MCHK (Mass Stripe Auth) ──────────────────────────────────────────────────
try:
    from mass_gates.mchk import MCHK_SESSIONS, update_progress_message as update_mchk_message
except ImportError:
    logging.warning("[STOP] Error importing from mchk.py.")
    MCHK_SESSIONS      = {}
    update_mchk_message = None

# ── MST (Mass Stripe) ────────────────────────────────────────────────────────
try:
    from mass_gates.mst import MST_SESSIONS, update_progress_message as update_mst_message
except ImportError:
    logging.warning("[STOP] Error importing from mst.py.")
    MST_SESSIONS      = {}
    update_mst_message = None

# ── MNMI (Mass NMI) ──────────────────────────────────────────────────────────
try:
    from mass_gates.mnmi import MNMI_SESSIONS, update_progress_message as update_mnmi_message
except ImportError:
    logging.warning("[STOP] Error importing from mnmi.py.")
    MNMI_SESSIONS      = {}
    update_mnmi_message = None

# ── MBL (Mass BluePay) ───────────────────────────────────────────────────────
try:
    from mass_gates.mbl import MBL_SESSIONS, update_progress_message as update_mbl_message
except ImportError:
    logging.warning("[STOP] Error importing from mbl.py.")
    MBL_SESSIONS      = {}
    update_mbl_message = None

# ── MSK (Mass SK Based) ──────────────────────────────────────────────────────
try:
    from mass_gates.msk import MSK_SESSIONS, update_progress_message as update_msk_message
except ImportError:
    logging.warning("[STOP] Error importing from msk.py.")
    MSK_SESSIONS      = {}
    update_msk_message = None

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Sessions that use (bot, session_id) signature for update_progress_message
# All others use (message, session_id)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
_BOT_SIG_TYPES = {"MST", "MNMI", "MBL", "MCHK", "MSK"}

# Status strings that mean "already finished / stopped"
_STOPPED_STATUSES  = {"<b>Sᴛᴏᴘᴘᴇᴅ</b>", "STOPPED"}
_FINISHED_STATUSES = {"<b>Sᴜᴍᴍᴀʀʏ</b>", "FINISHED"}

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# /stop COMMAND
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

@router.message(F.text.startswith("/stop"))
async def stop_command(message: types.Message):
    user_id = message.from_user.id

    # 1. Parse arguments
    parts = message.text.split(maxsplit=1)
    if len(parts) < 2:
        await message.answer(
            "⚠️ <b>Usage ➠</b> /stop <code>{session_id}</code>\n"
            "<b>Find the Session ID in your progress message.</b>",
            parse_mode="HTML"
        )
        return

    session_id = parts[1].strip()

    # 2. Locate session across all gate dictionaries
    _lookup_order = [
        (MRZ_SESSIONS,  "MRZ",  update_mrz_message),
        (MSH_SESSIONS,  "MSH",  update_msh_message),
        (MCHK_SESSIONS, "MCHK", update_mchk_message),
        (MST_SESSIONS,  "MST",  update_mst_message),
        (MNMI_SESSIONS, "MNMI", update_mnmi_message),
        (MBL_SESSIONS,  "MBL",  update_mbl_message),
        (MSK_SESSIONS,  "MSK",  update_msk_message),
    ]

    session      = None
    session_type = None
    update_func  = None

    for store, stype, ufunc in _lookup_order:
        found = store.get(session_id)
        if found:
            session      = found
            session_type = stype
            update_func  = ufunc
            break

    # 3. Not found
    if not session:
        await message.answer(
            f"❌ <b>Session Not Found</b>\n\n"
            f"<b>ID ➠</b> <code>{session_id}</code>\n"
            f"<b>Reason ➠</b> Expired or Invalid",
            parse_mode="HTML"
        )
        return

    # 4. Ownership check
    if session.get("user_id") != user_id:
        await message.answer(
            "🚫 <b>Access Denied</b>\n\n"
            "You cannot stop a session started by another user.",
            parse_mode="HTML"
        )
        return

    # 5. Already stopped / finished check
    current_status = session.get("status", "")
    if current_status in _STOPPED_STATUSES:
        await message.answer(
            f"⚠️ <b>Session Already Stopped</b>\n\n"
            f"<b>ID ➠</b> <code>{session_id}</code> 🛑",
            parse_mode="HTML"
        )
        return
    if current_status in _FINISHED_STATUSES:
        await message.answer(
            f"⚠️ <b>Session Already Finished</b>\n\n"
            f"<b>ID ➠</b> <code>{session_id}</code> ✅",
            parse_mode="HTML"
        )
        return

    # 6. Set stopped status
    session["status"] = "<b>Sᴛᴏᴘᴘᴇᴅ</b>"

    # 7. Cancel running tasks
    cancelled = 0
    for task in session.get("tasks", []):
        if not task.done():
            task.cancel()
            cancelled += 1

    # 8. Update progress message
    if update_func:
        try:
            if session_type in _BOT_SIG_TYPES:
                await update_func(message.bot, session_id)
            else:
                await update_func(message, session_id)
        except Exception as e:
            logging.error(f"[STOP] progress update error for {session_type}: {e}")

    # 9. Confirmation
    await message.answer(
        f"<b>Status ➠ Terminated 🛑</b>\n\n"
        f"<b>Session ID ➠</b> <code>{session_id}</code>\n"
        f"<b>Type ➠</b> {session_type}\n"
        f"<b>Tasks ➠</b> {cancelled} Cancelled Successfully",
        parse_mode="HTML"
    )
