# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# GIF TOGGLE  ( /gif  ·  /offgif )
# Global switch for the anime reaction GIFs attached to single-gate
# and mass-gate result UIs.
#
# Enabled  (default) — results are sent as Telegram animations (GIFs)
#                      exactly as they are today.
# Disabled           — results are sent as plain text messages carrying
#                      the identical caption. No GIF is fetched or sent.
#
# Implementation note: every gate calls either message.reply_animation()
# or bot.send_animation(). Both funnel through Bot.__call__ -> session,
# so the swap is done in one place (GifToggleSession) instead of editing
# the 27+ gate modules individually.
#
# Storage: the bot_settings key/value table, same as privacy.py.
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

import logging

from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.methods import SendAnimation, SendMessage

SETTING_KEY = "gifs"
DEFAULT_ENABLED = True

_state = {"enabled": DEFAULT_ENABLED}


def _db():
    from database import PooledConn
    return PooledConn()


def init_gifs():
    """Create the setting row if missing and load the persisted value."""
    try:
        with _db() as conn:
            cur = conn.cursor()
            cur.execute("""
                CREATE TABLE IF NOT EXISTS bot_settings (
                    key   TEXT PRIMARY KEY,
                    value TEXT
                )
            """)
            cur.execute(
                "INSERT INTO bot_settings(key, value) VALUES (%s, %s) "
                "ON CONFLICT (key) DO NOTHING",
                (SETTING_KEY, "on" if DEFAULT_ENABLED else "off"),
            )
            conn.commit()
        _state["enabled"] = _load_from_db()
        logging.info(f"[Gifs] init ok (enabled={_state['enabled']})")
    except Exception as e:
        logging.error(f"[Gifs] init error: {e}")


def _load_from_db() -> bool:
    try:
        with _db() as conn:
            cur = conn.cursor()
            cur.execute("SELECT value FROM bot_settings WHERE key = %s", (SETTING_KEY,))
            row = cur.fetchone()
        if row is None:
            return DEFAULT_ENABLED
        return str(row[0]).lower() == "on"
    except Exception as e:
        logging.error(f"[Gifs] load error: {e}")
        return DEFAULT_ENABLED


def gifs_enabled() -> bool:
    """True when GIFs should be attached to gate result UIs."""
    return _state["enabled"]


def set_gifs_enabled(enabled: bool) -> bool:
    """Persist + apply the toggle. Returns the value that is now active."""
    _state["enabled"] = bool(enabled)
    try:
        with _db() as conn:
            cur = conn.cursor()
            cur.execute(
                "UPDATE bot_settings SET value = %s WHERE key = %s",
                ("on" if _state["enabled"] else "off", SETTING_KEY),
            )
            if cur.rowcount == 0:
                # Row vanished (e.g. table was dropped) — recreate it.
                cur.execute(
                    "INSERT INTO bot_settings(key, value) VALUES (%s, %s) "
                    "ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value",
                    (SETTING_KEY, "on" if _state["enabled"] else "off"),
                )
            conn.commit()
    except Exception as e:
        logging.error(f"[Gifs] save error: {e}")
    return _state["enabled"]


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# SESSION INTERCEPTION
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def animation_to_message(method: SendAnimation) -> SendMessage:
    """
    Build an equivalent text-only SendMessage from a SendAnimation.

    The caption becomes the message text and caption_entities become
    entities so HTML/emoji formatting survives the conversion. Animation
    only fields (animation, thumbnail, duration, has_spoiler, ...) are
    simply not carried over.
    """
    text = method.caption or ""
    if not text:
        text = "✅ Result"

    return SendMessage(
        chat_id=method.chat_id,
        text=text,
        parse_mode=method.parse_mode,
        entities=method.caption_entities,
        business_connection_id=method.business_connection_id,
        message_thread_id=method.message_thread_id,
        direct_messages_topic_id=method.direct_messages_topic_id,
        disable_notification=method.disable_notification,
        protect_content=method.protect_content,
        message_effect_id=method.message_effect_id,
        reply_to_message_id=method.reply_to_message_id,
        reply_parameters=method.reply_parameters,
        reply_markup=method.reply_markup,
        allow_sending_without_reply=method.allow_sending_without_reply,
        allow_paid_broadcast=method.allow_paid_broadcast,
        suggested_post_parameters=method.suggested_post_parameters,
        ephemeral_message_parameters=method.ephemeral_message_parameters,
    )


class GifToggleSession(AiohttpSession):
    """
    Drop-in AiohttpSession that strips GIFs when the toggle is off.

    Passing this to Bot(session=...) means no call site anywhere in the
    project needs to change: send_animation() becomes send_message() on
    the wire, transparently.
    """

    async def __call__(self, bot, method, timeout: int = None):
        if not _state["enabled"] and isinstance(method, SendAnimation):
            method = animation_to_message(method)
        return await super().__call__(bot, method, timeout=timeout)


def build_session() -> GifToggleSession:
    """
    Build the session instance for the bot.

    A plain Bot() gets a stock AiohttpSession with default settings, so
    constructing GifToggleSession with no arguments is equivalent apart
    from the GIF interception. Proxy / timeout settings from
    DefaultBotProperties can be layered on here if they are added later.
    """
    return GifToggleSession()


init_gifs()
