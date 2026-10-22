import asyncio
import logging
from typing import Callable, Dict, Any, Awaitable
from aiogram import Router, types, BaseMiddleware
from aiogram.filters import Command
from database import get_collection

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# CONFIGURATION
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
ADMIN_IDS = {8423281554}

router = Router()

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# SYNC DB HELPERS (run via asyncio.to_thread)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
def _is_banned_sync(user_id: int) -> bool:
    col = get_collection("banned_users")
    return col.find_one({"user_id": user_id}) is not None

def _ban_user_sync(user_id: int):
    col = get_collection("banned_users")
    col.update_one(
        {"user_id": user_id},
        {"$setOnInsert": {"user_id": user_id, "banned_at": __import__("datetime").datetime.now()}},
        upsert=True
    )

def _unban_user_sync(user_id: int) -> bool:
    col = get_collection("banned_users")
    result = col.delete_one({"user_id": user_id})
    return result.deleted_count > 0

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# /ban COMMAND   —  /ban 123456789
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
@router.message(Command("ban"))
async def ban_command(message: types.Message):
    if message.from_user.id not in ADMIN_IDS:
        await message.reply("⛔ Admin only.")
        return

    parts = message.text.split()
    if len(parts) < 2 or not parts[1].lstrip("-").isdigit():
        await message.reply("Usage: /ban [user_id]")
        return

    target_id = int(parts[1])
    if target_id in ADMIN_IDS:
        await message.reply("<tg-emoji emoji-id='5397890704062038337'>❌</tg-emoji> Cannot ban an admin.")
        return

    await asyncio.to_thread(_ban_user_sync, target_id)
    await message.reply(
        f"<tg-emoji emoji-id='5397890704062038337'>🚫</tg-emoji> User <code>{target_id}</code> has been <b>banned</b>.",
        parse_mode="HTML"
    )

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# /unban COMMAND  —  /unban 123456789
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
@router.message(Command("unban"))
async def unban_command(message: types.Message):
    if message.from_user.id not in ADMIN_IDS:
        await message.reply("⛔ Admin only.")
        return

    parts = message.text.split()
    if len(parts) < 2 or not parts[1].lstrip("-").isdigit():
        await message.reply("Usage: /unban [user_id]")
        return

    target_id = int(parts[1])
    removed = await asyncio.to_thread(_unban_user_sync, target_id)

    if removed:
        await message.reply(
            f"<tg-emoji emoji-id='5310296284874159738'>✅</tg-emoji> User <code>{target_id}</code> has been <b>unbanned</b>.",
            parse_mode="HTML"
        )
    else:
        await message.reply(
            f"<tg-emoji emoji-id='5350572310627632617'>⚠️</tg-emoji> User <code>{target_id}</code> is <b>not</b> in the ban list.",
            parse_mode="HTML"
        )

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# BAN MIDDLEWARE
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
BAN_WARNING = (
    "<tg-emoji emoji-id='5397890704062038337'>🚫</tg-emoji> <b>You have been banned from using this bot.</b>\n\n"
    "If you believe this is a mistake, contact support."
)

class BanMiddleware(BaseMiddleware):
    async def __call__(
        self,
        handler: Callable[[types.Message, Dict[str, Any]], Awaitable[Any]],
        event: types.Message,
        data: Dict[str, Any]
    ) -> Any:
        user = event.from_user
        if not user or user.id in ADMIN_IDS:
            return await handler(event, data)

        banned = await asyncio.to_thread(_is_banned_sync, user.id)
        if banned:
            try:
                await event.reply(BAN_WARNING, parse_mode="HTML")
            except Exception:
                pass
            return  # stop processing

        return await handler(event, data)
