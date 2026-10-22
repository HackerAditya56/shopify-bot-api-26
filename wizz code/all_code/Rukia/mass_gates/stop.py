import logging
import asyncio

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# AIogram Imports
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
from aiogram import types, F, Router

# Router for this module
router = Router()

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# IMPORTS (SHARED STATE FROM GATE MODULES)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

# Import MAU (Mass Auth) Sessions and UI Updater
try:
    from mass_gates.mau import MAU_SESSIONS, update_progress_message as update_mau_message
except ImportError:
    logging.warning("[STOP.PY] Error importing from mau.py.")
    MAU_SESSIONS = {}
    update_mau_message = None

# Import MSH (Mass Shopify) Sessions and UI Updater
try:
    from mass_gates.msh import MSH_SESSIONS, update_progress_message as update_msh_message
except ImportError:
    logging.warning("[STOP.PY] Error importing from msh.py.")
    MSH_SESSIONS = {}
    update_msh_message = None

# Import MST (Mass Stripe) Sessions and UI Updater
try:
    from mass_gates.mst import MST_SESSIONS, update_progress_message as update_mst_message
except ImportError:
    logging.warning("[STOP.PY] Error importing from mst.py.")
    MST_SESSIONS = {}
    update_mst_message = None

# Import MNMI (Mass NMI) Sessions and UI Updater
try:
    from mass_gates.mnmi import MNMI_SESSIONS, update_progress_message as update_mnmi_message
except ImportError:
    logging.warning("[STOP.PY] Error importing from mnmi.py.")
    MNMI_SESSIONS = {}
    update_mnmi_message = None

# Import MBL (Mass BluePay) Sessions and UI Updater
try:
    from mass_gates.mbl import MBL_SESSIONS, update_progress_message as update_mbl_message
except ImportError:
    logging.warning("[STOP.PY] Error importing from mbl.py.")
    MBL_SESSIONS = {}
    update_mbl_message = None

@router.message(F.text.startswith("/stop"))
async def stop_command(message: types.Message):
    user_id = message.from_user.id
    
    # 1. Parse Arguments
    parts = message.text.split(maxsplit=1)
    
    if not parts or len(parts) < 2:
        await message.answer(
            "<tg-emoji emoji-id='5350572310627632617'>⚠️</tg-emoji> Usage ➛ /stop <code>{session_id}</code>\n"
            "Find the Session ID in your progress message.",
            parse_mode="HTML"
        )
        return

    session_id = parts[1].strip()

    # 2. Locate Session in all dictionaries
    session = MAU_SESSIONS.get(session_id)
    session_type = "MAU" 
    update_func = update_mau_message
    
    if not session:
        session = MSH_SESSIONS.get(session_id)
        session_type = "MSH"
        update_func = update_msh_message
    
    if not session:
        session = MST_SESSIONS.get(session_id)
        session_type = "MST"
        update_func = update_mst_message

    if not session:
        session = MNMI_SESSIONS.get(session_id)
        session_type = "MNMI"
        update_func = update_mnmi_message

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # CHECK MBL (Mass BluePay)
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    if not session:
        session = MBL_SESSIONS.get(session_id)
        session_type = "MBL"
        update_func = update_mbl_message
    
    # 3. Check if session exists
    if not session:
        await message.answer(
            f"<tg-emoji emoji-id='5397890704062038337'>❌</tg-emoji> Session Not Found\n\n"
            f"ID ➛ <code>{session_id}</code>\n"
            f"Reason ➛ Expired or Invalid",
            parse_mode="HTML"
        )
        return

    # 4. Authorization Check
    if session['user_id'] != user_id:
        await message.answer(
            "<tg-emoji emoji-id='5397890704062038337'>🚫</tg-emoji> Access Denied\n\n"
            "You cannot stop a session started by another user.",
            parse_mode="HTML"
        )
        return

    # 5. Check if already stopped or finished
    if session['status'] in ["STOPPED", "FINISHED"]:
        status_icon = "🛑" if session['status'] == "STOPPED" else "<tg-emoji emoji-id='5310296284874159738'>✅</tg-emoji>"
        await message.answer(
            f"<tg-emoji emoji-id='5350572310627632617'>⚠️</tg-emoji> Session Already {session['status']}\n\n"
            f"ID ➛ <code>{session_id}</code>\n"
            f"Status ➛ {session['status']} {status_icon}",
            parse_mode="HTML"
        )
        return

    # 6. SET STOPPED STATUS
    session['status'] = "STOPPED"

    # 7. INSTANTLY CANCEL ONGOING REQUESTS
    active_tasks = session.get('tasks', [])
    for task in active_tasks:
        if not task.done():
            task.cancel()

    # 8. Update the Progress Message immediately
    if update_func:
        try:
            # MST, MNMI, and MBL use (bot, session_id) signature
            # MAU and MSH traditionally use (message, session_id)
            if session_type in ["MST", "MNMI", "MBL"]:
                await update_func(message.bot, session_id)
            else:
                await update_func(message, session_id)
        except Exception as e:
            logging.error(f"Error updating progress on stop: {e}")

    # 9. Confirmation Message
    await message.answer(
        f"Status ➛ Terminated 🛑\n\n"
        f"Session ID ➛ <code>{session_id}</code>\n"
        f"Type ➛ {session_type}\n"
        f"Tasks ➛ Cancelled Successfully",
        parse_mode="HTML"
    )
