# _tg_helpers.py — flood-safe Telegram send helpers shared across mass gates.
import asyncio
import logging
import time

from aiogram.exceptions import TelegramRetryAfter, TelegramForbiddenError, TelegramBadRequest

# Global token bucket: ~25 msgs/sec (headroom under Telegram's ~30/s global limit).
_G_RATE = 20.0
_G_CAP = 20.0
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
            if e.retry_after > 120:
                logging.warning(f"[TG] FloodWait {e.retry_after}s — dropping")
                return None
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
                if e.retry_after > 120:
                    logging.warning(f"[TG] FloodWait {e.retry_after}s — dropping")
                    return None
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


async def edit_message_safe(bot, chat_id, message_id, text, parse_mode="HTML", **kw):
    """Rate-limited (global + per-chat), FloodWait-aware edit_message_text. Never raises."""
    for _ in range(3):
        await _throttle(chat_id)
        try:
            return await bot.edit_message_text(chat_id=chat_id, message_id=message_id,
                                               text=text, parse_mode=parse_mode, **kw)
        except TelegramRetryAfter as e:
            if e.retry_after > 120:
                logging.warning(f"[TG] FloodWait {e.retry_after}s — dropping")
                return None
            logging.warning(f"[TG] FloodWait {e.retry_after}s — sleeping")
            await asyncio.sleep(e.retry_after + 1)
        except TelegramBadRequest:
            return None   # "message not modified" / "not found" — nothing to edit
        except Exception as e:
            logging.warning(f"[TG] edit failed for {chat_id}: {e}")
            return None
    return None


async def safe_reply(message, *args, **kwargs):
    """Reply to a message; FloodWait-aware + rate-limited; fall back to answer if deleted.

    Long FloodWaits (>2 min) are dropped instead of slept through, so the bot
    never hangs for an hour on a single flooded chat."""
    chat_id = message.chat.id
    for _ in range(3):
        await _throttle(chat_id)
        try:
            return await message.reply(*args, **kwargs)
        except TelegramRetryAfter as e:
            if e.retry_after > 120:
                logging.warning(f"[TG] FloodWait {e.retry_after}s on reply — dropping")
                return None
            logging.warning(f"[TG] FloodWait {e.retry_after}s on reply — sleeping")
            await asyncio.sleep(e.retry_after + 1)
        except TelegramBadRequest:
            break   # can't reply (deleted) -> fall through to plain answer
        except Exception as e:
            logging.warning(f"[TG] reply failed for {chat_id}: {e}")
            return None
    try:
        await _throttle(chat_id)
        return await message.answer(*args, **kwargs)
    except TelegramRetryAfter as e:
        logging.warning(f"[TG] FloodWait {e.retry_after}s on answer — dropping")
        return None
    except Exception:
        return None


# ── premium emoji IDs (shared hit-card UI) ──────────────────────────────
EMOJI_CARD     = '<tg-emoji emoji-id="4956719506027185156">💎</tg-emoji>'
EMOJI_GATEWAY  = '<tg-emoji emoji-id="5085022089103016925">⚡</tg-emoji>'
EMOJI_PRICE    = '<tg-emoji emoji-id="5424976816530014958">👛</tg-emoji>'
EMOJI_BRAND    = '<tg-emoji emoji-id="6136275172283391020">⭐</tg-emoji>'
EMOJI_ISSUER   = '<tg-emoji emoji-id="6136246765369694911">🦇</tg-emoji>'
EMOJI_COUNTRY  = '<tg-emoji emoji-id="5463071033256848094">🔝</tg-emoji>'
EMOJI_RESPONSE = '<tg-emoji emoji-id="6136275172283391020">⭐</tg-emoji>'
EMOJI_USER     = '<tg-emoji emoji-id="5359719332542718652">💎</tg-emoji>'
EMOJI_DEV      = '<tg-emoji emoji-id="6255712466118905093">⚡</tg-emoji>'
EMOJI_PX       = '<tg-emoji emoji-id="6253702009107516178">⭐</tg-emoji>'
EMOJI_TYPE     = '<tg-emoji emoji-id="4956719506027185156">💎</tg-emoji>'
EMOJI_LEVEL    = '<tg-emoji emoji-id="6136275172283391020">⭐</tg-emoji>'
CHARGED_EMOJI  = '<tg-emoji emoji-id="5359719332542718652">💎</tg-emoji>'
APPROVED_EMOJI = '<tg-emoji emoji-id="6044254523009012231">✅</tg-emoji>'
DECLINED_EMOJI = '<tg-emoji emoji-id="5893081007153746175">❌</tg-emoji>'
ERROR_EMOJI    = '<tg-emoji emoji-id="6255910249362885846">⚠️</tg-emoji>'


def build_hit_card(status, card, gateway, price, bin_info, response, user_display,
                   dev_link, proxy_status=None, extra_lines=None, currency="$"):
    """The premium single-check hit card (same look as the mass charged-hit UI)."""
    from html import escape
    status = (status or "").upper()
    bin_info = bin_info or {}
    bin_scheme = escape(str(bin_info.get("scheme", "N/A")))
    bin_level = escape(str(bin_info.get("brand", "N/A")))
    bin_bank = escape(str(bin_info.get("bank", "N/A")))
    bin_type = escape(str(bin_info.get("type", "N/A")))
    country_name = escape(str(bin_info.get("country", "N/A")))
    country_flag = bin_info.get("country_emoji", "")
    bin_country = f"{country_name} {country_flag}".strip() if country_flag else country_name
    safe_response = escape(str(response))
    safe_card = escape(str(card))
    safe_price = escape(str(price))

    if status == "CHARGED":
        header = f"<blockquote>{CHARGED_EMOJI} 𝐂𝐇𝐀𝐑𝐆𝐄𝐃 𝐇𝐈𝐓 {CHARGED_EMOJI}</blockquote>"
    elif status == "APPROVED":
        header = f"<blockquote>{APPROVED_EMOJI} 𝐀𝐏𝐏𝐑𝐎𝐕𝐄𝐃 {APPROVED_EMOJI}</blockquote>"
    elif status == "DECLINED":
        header = f"<blockquote>{DECLINED_EMOJI} 𝐃𝐄𝐂𝐋𝐈𝐍𝐄𝐃 {DECLINED_EMOJI}</blockquote>"
    else:
        header = f"<blockquote>{ERROR_EMOJI} 𝐄𝐑𝐑𝐎𝐑 {ERROR_EMOJI}</blockquote>"

    lines = [header, "━━━━━━━━━━━━━━━━━━━━━",
             f"{EMOJI_CARD} 𝐂𝐚𝐫𝐝 ➠ <tg-spoiler><code>{safe_card}</code></tg-spoiler>",
             f"{EMOJI_GATEWAY} 𝐆𝐚𝐭𝐞𝐰𝐚𝐲 ➠ <b>{escape(str(gateway))}</b>",
             f"{EMOJI_PRICE} 𝐏𝐫𝐢𝐜𝐞 ➠ <b>{safe_price} {currency}</b>",
             f"{EMOJI_BRAND} 𝐁𝐫𝐚𝐧𝐝 ➠ <b>{bin_scheme}</b>",
             f"{EMOJI_LEVEL} 𝐋𝐞𝐯𝐞𝐥 ➠ <b>{bin_level}</b>",
             f"{EMOJI_ISSUER} 𝐈𝐬𝐬𝐮𝐞𝐫 ➠ <b>{bin_bank}</b>",
             f"{EMOJI_COUNTRY} 𝐂𝐨𝐮𝐧𝐭𝐫𝐲 ➠ <b>{bin_country}</b>",
             f"{EMOJI_TYPE} 𝐓𝐲𝐩𝐞 ➠ <b>{bin_type}</b>",
             f"{EMOJI_RESPONSE} 𝐑𝐞𝐬𝐩𝐨𝐧𝐬𝐞 ➠ <b>{safe_response}</b>"]
    if extra_lines:
        lines.extend(extra_lines)
    lines.append("━━━━━━━━━━━━━━━━━━━━━")
    lines.append(f"{EMOJI_USER} 𝐔𝐬𝐞𝐫 ➠ {user_display}")
    px = f"   ✧   {EMOJI_PX} 𝐏𝐱 ➠ {proxy_status}" if proxy_status else ""
    lines.append(f"{EMOJI_DEV} 𝐃𝐞𝐯 ➠ {dev_link}{px}")
    return "\n".join(lines)
