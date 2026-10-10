# _tg_helpers.py — flood-safe Telegram send helpers shared across mass gates.
import asyncio
import logging
import time

from aiogram.exceptions import TelegramRetryAfter, TelegramForbiddenError, TelegramBadRequest

# Global token bucket: ~25 msgs/sec (headroom under Telegram's ~30/s global limit).
_G_RATE = 25.0
_G_CAP = 25.0
_g_state = {"tokens": _G_CAP, "ts": time.monotonic(), "lock": None}

# Per-chat token bucket: ~1 msg/sec per chat (Telegram per-chat limit),
# with a small burst allowance (short bursts are tolerated).
_C_RATE = 1.0
_C_CAP = 3.0
_chats = {}   # chat_id -> {"tokens": float, "ts": float}


def _g_lock():
    if _g_state["lock"] is None:
        _g_state["lock"] = asyncio.Lock()
    return _g_state["lock"]


async def _acquire_global():
    while True:
        async with _g_lock():
            now = time.monotonic()
            _g_state["tokens"] = min(_G_CAP, _g_state["tokens"] + (now - _g_state["ts"]) * _G_RATE)
            _g_state["ts"] = now
            if _g_state["tokens"] >= 1:
                _g_state["tokens"] -= 1
                return
        await asyncio.sleep(0.04)


async def _acquire_chat(chat_id):
    while True:
        entry = _chats.setdefault(chat_id, {"tokens": _C_CAP, "ts": time.monotonic()})
        now = time.monotonic()
        entry["tokens"] = min(_C_CAP, entry["tokens"] + (now - entry["ts"]) * _C_RATE)
        entry["ts"] = now
        if entry["tokens"] >= 1:
            entry["tokens"] -= 1
            return
        await asyncio.sleep(0.1)


async def _throttle(chat_id):
    await _acquire_global()
    await _acquire_chat(chat_id)


async def send_message_safe(bot, chat_id, text, parse_mode="HTML", **kw):
    """Rate-limited (global + per-chat), FloodWait-aware send_message. Never raises."""
    for _ in range(3):
        await _throttle(chat_id)
        try:
            return await bot.send_message(chat_id=chat_id, text=text, parse_mode=parse_mode, **kw)
        except TelegramRetryAfter as e:
            logging.warning(f"[TG] FloodWait {e.retry_after}s — sleeping")
            await asyncio.sleep(e.retry_after + 1)
        except Exception as e:
            logging.warning(f"[TG] send_message failed for {chat_id}: {e}")
            return None
    return None


async def send_hit(bot, chat_id, caption, gif_url=None, parse_mode="HTML"):
    """Deliver a hit reliably: GIF animation first, plain-text fallback. Never raises."""
    if gif_url:
        for _ in range(3):
            await _throttle(chat_id)
            try:
                return await bot.send_animation(chat_id=chat_id, animation=gif_url,
                                                caption=caption, parse_mode=parse_mode)
            except TelegramRetryAfter as e:
                logging.warning(f"[TG] FloodWait {e.retry_after}s — sleeping")
                await asyncio.sleep(e.retry_after + 1)
            except TelegramForbiddenError as e:
                logging.warning(f"[TG] Forbidden for {chat_id}: {e}")
                return None
            except Exception as e:
                logging.warning(f"[TG] animation failed ({e}); falling back to text")
                break
    return await send_message_safe(bot, chat_id, caption, parse_mode=parse_mode,
                                   disable_web_page_preview=True)


async def safe_reply(message, *args, **kwargs):
    """Reply to a message; fall back to a plain answer if it was deleted."""
    try:
        return await message.reply(*args, **kwargs)
    except TelegramBadRequest:
        try:
            return await message.answer(*args, **kwargs)
        except Exception:
            return None
