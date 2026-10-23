import asyncio
import logging
import uuid
from html import escape
from typing import Any, Dict, List, Optional

from aiogram import types, Router, F, BaseMiddleware
from aiogram.filters import Command
from aiogram.types import (
    InlineKeyboardMarkup, InlineKeyboardButton,
    InputMediaPhoto, InputMediaVideo, InputMediaAnimation, InputMediaDocument,
)

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# CONFIGURATION
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
ADMIN_ID         = 8462705169  # Owner's Telegram ID
FEEDBACK_CHANNEL = -1003912886127   # Channel where approved feedback is posted

router = Router()

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# MEDIA GROUP COLLECTOR MIDDLEWARE
# Runs on every message — stores album messages before handlers fire
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# {media_group_id: [Message, ...]}
_MEDIA_GROUPS: Dict[str, List[types.Message]] = {}

class MediaGroupCollectorMiddleware(BaseMiddleware):
    async def __call__(self, handler, event: types.Message, data: Dict[str, Any]):
        gid = getattr(event, "media_group_id", None)
        if gid:
            bucket = _MEDIA_GROUPS.setdefault(gid, [])
            # Deduplicate by message_id
            existing_ids = {m.message_id for m in bucket}
            if event.message_id not in existing_ids:
                bucket.append(event)
            
            # Set a timer to clean up this group after 3 seconds
            async def cleanup_group():
                await asyncio.sleep(3)
                _MEDIA_GROUPS.pop(gid, None)
            
            asyncio.create_task(cleanup_group())
        
        # Always let the handler chain continue
        return await handler(event, data)

router.message.middleware(MediaGroupCollectorMiddleware())

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# IN-MEMORY PENDING STORE
# key  : short UUID hex
# value: {
#   "messages":     [Message, ...]   — the replied-to messages (1 or full album)
#   "media_type":   "photo"|"video"|"animation"|"document"|"text"|"photo_album"
#   "hit_text":     str
#   "user":         User
#   "timestamp":    float
# }
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
_PENDING: dict = {}

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# MEDIA DETECTION
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
def _detect_media(msg: types.Message) -> str:
    """Returns media type string for a single message."""
    if msg.photo:       return "photo"
    if msg.video:       return "video"
    if msg.animation:   return "animation"
    if msg.document:    return "document"
    return "text"

def _get_file_id(msg: types.Message) -> Optional[str]:
    """Returns the primary file_id from a message, or None."""
    if msg.photo:       return msg.photo[-1].file_id
    if msg.video:       return msg.video.file_id
    if msg.animation:   return msg.animation.file_id
    if msg.document:    return msg.document.file_id
    return None

def _get_caption_or_text(msg: types.Message) -> str:
    """Get caption or text from message."""
    return (msg.caption or msg.text or "").strip()

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# HELPERS
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
def _admin_info_text(user: types.User, media_type: str, count: int) -> str:
    """Create admin notification text with user info."""
    username_part = f"@{user.username}" if user.username else "N/A"
    user_link     = f'<a href="tg://user?id={user.id}">{escape(user.first_name)}</a>'
    
    # Format media label
    if media_type == "photo_album":
        media_label = f"📸 Album ({count} photos)"
    elif count > 1:
        media_label = f"{count}× {media_type}"
    else:
        media_emoji = {
            "photo": "📷 Photo",
            "video": "🎥 Video",
            "animation": "🎬 GIF",
            "document": "📄 Document",
            "text": "📝 Text"
        }.get(media_type, media_type)
        media_label = media_emoji
    
    return (
        "━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"<b><tg-emoji emoji-id=\"5465465194056525619\">👍</tg-emoji> NEW FEEDBACK</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"<b>👤 User ➠</b> {user_link}\n"
        f"<b>🆔 User ID ➠</b> <code>{user.id}</code>\n"
        f"<b>📛 Username ➠</b> {username_part}\n"
        f"<b>🎯 Media:</b> {media_label}\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━"
    )

def _admin_keyboard(pid: str) -> InlineKeyboardMarkup:
    """Create inline keyboard for admin approval."""
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="✅ Approve", callback_data=f"fb_approve_{pid}"),
            InlineKeyboardButton(text="❌ Reject", callback_data=f"fb_reject_{pid}"),
        ]
    ])

def _channel_caption(user: types.User, hit_text: str) -> str:
    """Create caption for channel post."""
    # Get user's display name (first_name or last_name or username)
    user_display = user.first_name or user.last_name or user.username or "User"
    user_link = f'<a href="tg://user?id={user.id}">{escape(user_display)}</a>'
    note_part = hit_text if hit_text else "—"
    
    return (
        f'<b><tg-emoji emoji-id=\"5956561749070057536\">👍</tg-emoji> Nᴇᴡ Fᴇᴇᴅʙᴀᴄᴋ</b>\n'
        f'<b>━━━━━━━━━━━━</b>\n'
        f'<b><tg-emoji emoji-id=\"5445174334031166029\">😵</tg-emoji> Usᴇʀ ➺</b> {user_link}\n'
        f'<b><tg-emoji emoji-id=\"5445358884480916784\">😎</tg-emoji> ID ➺</b> {user.id}\n'
        f'<b><tg-emoji emoji-id=\"5445344161333015312\">⭐️</tg-emoji> Mᴇssᴀɢᴇ ➺ {note_part}</b>\n'
    )

def _build_input_media(msg: types.Message, caption: str = "", parse_mode: str = "HTML") -> Optional[Any]:
    """Build an InputMedia* object for send_media_group."""
    fid = _get_file_id(msg)
    if not fid:
        return None
    
    mtype = _detect_media(msg)
    if mtype == "photo":
        return InputMediaPhoto(media=fid, caption=caption or None, parse_mode=parse_mode if caption else None)
    elif mtype == "video":
        return InputMediaVideo(media=fid, caption=caption or None, parse_mode=parse_mode if caption else None)
    elif mtype == "animation":
        # send_media_group doesn't support animation; fall back to document
        return InputMediaDocument(media=fid, caption=caption or None, parse_mode=parse_mode if caption else None)
    elif mtype == "document":
        return InputMediaDocument(media=fid, caption=caption or None, parse_mode=parse_mode if caption else None)
    return None

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# CLEANUP TASKS (to be started after bot is running)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
async def cleanup_old_pending():
    """Clean up old pending feedbacks (older than 1 hour)."""
    while True:
        await asyncio.sleep(3600)  # Run every hour
        current_time = asyncio.get_event_loop().time()
        expired = []
        for pid, data in _PENDING.items():
            if current_time - data.get("timestamp", 0) > 3600:  # 1 hour expiry
                expired.append(pid)
        for pid in expired:
            _PENDING.pop(pid, None)
            logging.info(f"[fb] Cleaned up expired pending feedback: {pid}")

async def start_cleanup_tasks():
    """Start all cleanup tasks (call this after bot is running)."""
    asyncio.create_task(cleanup_old_pending())
    logging.info("[fb] Cleanup tasks started")

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# /fb COMMAND HANDLER
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
@router.message(Command("fb"))
async def feedback_cmd(message: types.Message):
    """
    Reply to any hit message with /fb to submit it as feedback.
    Supports: single photo, video, GIF/animation, document, text, or photo albums (up to 10).
    """
    # Check if replying to a message
    if not message.reply_to_message:
        await message.reply(
            "<b>❌ Usage:</b> <i>Reply to your hit message with /fb</i>",
            parse_mode="HTML"
        )
        return

    replied = message.reply_to_message
    user = message.from_user

    # ── Send INSTANT confirmation to user ──────────────────────────────────
    confirm_msg = await message.reply(
        "━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        "<b>✅ Fᴇᴇᴅʙᴀᴄᴋ Sᴜʙᴍɪᴛᴛᴇᴅ!</b>\n"
        "<i>Tʜᴀɴᴋ Yᴏᴜ Fᴏʀ Yᴏᴜʀ Fᴇᴇᴅʙᴀᴄᴋ! </i>\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━",
        parse_mode="HTML"
    )

    # Auto-delete confirmation after 3 seconds
    async def auto_delete():
        await asyncio.sleep(3)
        try:
            await confirm_msg.delete()
            await message.delete()
        except:
            pass
    
    asyncio.create_task(auto_delete())

    # ── Collect media group if applicable ───────────────────────────────────
    gid = getattr(replied, "media_group_id", None)
    if gid:
        # Wait briefly so all album messages can be collected by the middleware
        await asyncio.sleep(0.5)
        group_msgs = list(_MEDIA_GROUPS.get(gid, [replied]))
        # Sort by message_id to preserve original order
        group_msgs.sort(key=lambda m: m.message_id)
        # Cap at 10 (Telegram media group limit)
        group_msgs = group_msgs[:10]
        
        # Check if it's a photo album (all photos) or mixed
        is_photo_album = all(msg.photo for msg in group_msgs)
        media_type = "photo_album" if is_photo_album and len(group_msgs) > 1 else "mixed_album"
        hit_text = _get_caption_or_text(replied)
    else:
        group_msgs = [replied]
        media_type = _detect_media(replied)
        hit_text = _get_caption_or_text(replied)

    # ── Store pending feedback ──────────────────────────────────────────────
    pid = uuid.uuid4().hex[:10]
    _PENDING[pid] = {
        "messages": group_msgs,
        "media_type": media_type,
        "hit_text": hit_text,
        "user": user,
        "timestamp": asyncio.get_event_loop().time(),
    }

    admin_text = _admin_info_text(user, media_type, len(group_msgs))

    # ── Forward all hit messages to admin + send info block ─────────────────
    async def forward_messages_to_admin():
        """Forward all messages to admin with error handling."""
        for msg in group_msgs:
            try:
                await message.bot.forward_message(
                    chat_id=ADMIN_ID,
                    from_chat_id=msg.chat.id,
                    message_id=msg.message_id
                )
                # Small delay to avoid flooding
                await asyncio.sleep(0.1)
            except Exception as e:
                logging.warning(f"[fb] Could not forward message {msg.message_id}: {e}")

    async def send_admin_info():
        """Send admin notification with approval buttons."""
        try:
            await message.bot.send_message(
                chat_id=ADMIN_ID,
                text=admin_text,
                parse_mode="HTML",
                reply_markup=_admin_keyboard(pid),
                disable_web_page_preview=True
            )
            logging.info(f"[fb] Pending {pid} stored for user {user.id} ({media_type}, {len(group_msgs)} item(s))")
        except Exception as e:
            logging.error(f"[fb] Admin notify error: {e}")
            # Try to notify admin about the error
            try:
                await message.bot.send_message(
                    chat_id=ADMIN_ID,
                    text=f"⚠️ Error processing feedback: {e}\nPID: {pid}",
                    parse_mode="HTML"
                )
            except:
                pass

    # Run both tasks concurrently
    await asyncio.gather(
        forward_messages_to_admin(),
        send_admin_info()
    )

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# APPROVE CALLBACK
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
@router.callback_query(F.data.startswith("fb_approve_"))
async def fb_approve(callback: types.CallbackQuery):
    """Handle admin approval of feedback."""
    # Answer callback immediately
    await callback.answer("✅ Approving feedback...")
    
    # Update admin message instantly
    try:
        await callback.message.edit_text(
            "<b>✅ Approved — Posting to channel...</b>",
            parse_mode="HTML"
        )
    except:
        pass

    pid = callback.data.replace("fb_approve_", "")
    entry = _PENDING.pop(pid, None)

    if not entry:
        await callback.message.edit_text(
            "<b>⚠️ Expired — Feedback already handled or bot restarted.</b>",
            parse_mode="HTML"
        )
        return

    user = entry["user"]
    msgs = entry["messages"]
    media_type = entry["media_type"]
    hit_text = entry["hit_text"]
    caption = _channel_caption(user, hit_text)

    try:
        # Handle different media types
        if media_type == "photo_album" and len(msgs) > 1:
            # Send as media group
            media_items = []
            for i, msg in enumerate(msgs):
                inp = _build_input_media(msg, caption=caption if i == 0 else "")
                if inp:
                    media_items.append(inp)
            
            if media_items:
                await callback.bot.send_media_group(
                    chat_id=FEEDBACK_CHANNEL,
                    media=media_items
                )
            else:
                # Fallback: send first message
                await callback.bot.forward_message(
                    chat_id=FEEDBACK_CHANNEL,
                    from_chat_id=msgs[0].chat.id,
                    message_id=msgs[0].message_id
                )

        elif media_type == "photo":
            file_id = _get_file_id(msgs[0])
            if file_id:
                await callback.bot.send_photo(
                    chat_id=FEEDBACK_CHANNEL,
                    photo=file_id,
                    caption=caption,
                    parse_mode="HTML"
                )
            else:
                await callback.bot.send_message(
                    chat_id=FEEDBACK_CHANNEL,
                    text=caption,
                    parse_mode="HTML"
                )

        elif media_type == "video":
            file_id = _get_file_id(msgs[0])
            if file_id:
                await callback.bot.send_video(
                    chat_id=FEEDBACK_CHANNEL,
                    video=file_id,
                    caption=caption,
                    parse_mode="HTML"
                )
            else:
                await callback.bot.send_message(
                    chat_id=FEEDBACK_CHANNEL,
                    text=caption,
                    parse_mode="HTML"
                )

        elif media_type == "animation":
            file_id = _get_file_id(msgs[0])
            if file_id:
                await callback.bot.send_animation(
                    chat_id=FEEDBACK_CHANNEL,
                    animation=file_id,
                    caption=caption,
                    parse_mode="HTML"
                )
            else:
                await callback.bot.send_message(
                    chat_id=FEEDBACK_CHANNEL,
                    text=caption,
                    parse_mode="HTML"
                )

        elif media_type == "document":
            file_id = _get_file_id(msgs[0])
            if file_id:
                await callback.bot.send_document(
                    chat_id=FEEDBACK_CHANNEL,
                    document=file_id,
                    caption=caption,
                    parse_mode="HTML"
                )
            else:
                await callback.bot.send_message(
                    chat_id=FEEDBACK_CHANNEL,
                    text=caption,
                    parse_mode="HTML"
                )

        elif media_type == "mixed_album":
            # Handle mixed albums by sending each item separately
            for i, msg in enumerate(msgs):
                file_id = _get_file_id(msg)
                if file_id:
                    msg_type = _detect_media(msg)
                    item_caption = caption if i == 0 else ""
                    
                    if msg_type == "photo":
                        await callback.bot.send_photo(
                            chat_id=FEEDBACK_CHANNEL,
                            photo=file_id,
                            caption=item_caption,
                            parse_mode="HTML" if item_caption else None
                        )
                    elif msg_type == "video":
                        await callback.bot.send_video(
                            chat_id=FEEDBACK_CHANNEL,
                            video=file_id,
                            caption=item_caption,
                            parse_mode="HTML" if item_caption else None
                        )
                    elif msg_type == "animation":
                        await callback.bot.send_animation(
                            chat_id=FEEDBACK_CHANNEL,
                            animation=file_id,
                            caption=item_caption,
                            parse_mode="HTML" if item_caption else None
                        )
                    elif msg_type == "document":
                        await callback.bot.send_document(
                            chat_id=FEEDBACK_CHANNEL,
                            document=file_id,
                            caption=item_caption,
                            parse_mode="HTML" if item_caption else None
                        )
                    await asyncio.sleep(0.2)  # Small delay between messages

        else:  # Text only
            await callback.bot.send_message(
                chat_id=FEEDBACK_CHANNEL,
                text=caption,
                parse_mode="HTML",
                disable_web_page_preview=True
            )

        # Update admin message to show success
        await callback.message.edit_text(
            "<b>✅ Approved — Posted to channel successfully!</b>",
            parse_mode="HTML"
        )
        
        logging.info(f"[fb] Approved and posted for user {user.id} ({media_type}, {len(msgs)} item(s))")

    except Exception as e:
        logging.error(f"[fb] Approve post error: {e}")
        try:
            await callback.message.edit_text(
                f"<b>❌ Approval failed:</b>\n<code>{str(e)[:200]}</code>",
                parse_mode="HTML"
            )
        except Exception:
            pass

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# REJECT CALLBACK
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
@router.callback_query(F.data.startswith("fb_reject_"))
async def fb_reject(callback: types.CallbackQuery):
    """Handle admin rejection of feedback."""
    await callback.answer("❌ Feedback rejected")
    
    pid = callback.data.replace("fb_reject_", "")
    entry = _PENDING.pop(pid, None)
    
    if entry:
        user = entry["user"]
        logging.info(f"[fb] Rejected feedback {pid} from user {user.id}")
    
    await callback.message.edit_text(
        "<b>❌ Rejected — Feedback declined</b>",
        parse_mode="HTML"
    )

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# REGISTRATION FUNCTION
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
def setup_feedback_handler(dispatcher):
    """Setup function for compatibility with existing code."""
    logging.info("[fb] Feedback handler router is ready")
    # Return router for inclusion
    return router

# Export the start_cleanup_tasks function to be called from main.py
__all__ = ['setup_feedback_handler', 'router', 'start_cleanup_tasks']