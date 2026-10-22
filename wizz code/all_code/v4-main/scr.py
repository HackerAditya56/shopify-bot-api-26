from live_emoji import plan_badge, dev_badge
import asyncio
import re
import os
import logging
import time
import random
import aiofiles
import aiohttp
import psycopg2.extras
from html import escape
from typing import Optional, List, Dict

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Aiogram Imports
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
from aiogram import types, F, Router
from aiogram.types import FSInputFile
from aiogram.exceptions import TelegramForbiddenError, TelegramBadRequest

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Local Imports  (mirrors chk.py pattern exactly)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
from database import is_gate_enabled, get_user_credits, update_credits, get_db_connection
from sub import get_premium_status

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Configuration
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

API_ID         = 34191449
API_HASH       = "acd4e7f41470d350bc1e2ac6ea0492ea"
SESSION_STRING = (
    "BAIXyCkAsDGK9peFnO6putknF7GQn_fAyFjwJ5kZvpDmvit-wjq7rptBfScfK9V-_YjeYy4_hZjHo80Cjz0zG-1S0rSKnz72O9AGSkrO6K68jdfDg3nPguyTKNe6Yk9CwEs7yER-tQBQU0c60JoSDw9OW1Yw2Jj6tfoHkX4wqnxgwR7KVRxwYR8K0VTZYUWswQ0lu1bDtN2oD5MiximX-OQCZg7GNa3BIvFoYEUL_A96BiIJMQtVy7wKIFlNFQHs5yUDfkBfbNzD5HmgoUrM8t9Q8HbhjTXm1iBjrU7MMW07SImAM6ibzTX7rHM13v8Mui2EpxTjnM_iP27BQNLQ6jhHlgi3AwAAAAH2EROSAA"
)

#API_ID         = 35113001
#API_HASH       = "bae3c4e34242aca7cdd1b8596fb1aad2"
#SESSION_STRING = (
    #"BAIXyCkAZcPH5esO3S1UAoU7fQhVz7_OEFmnVI6ZuQrISGJMOr-x1ugFuF25iJjFJrPQokjoIeu2riphRSiW3lgKAzEBeIRlv3be5PoYnWRb3nb_ZjhVC8E5FWWyPiG0d_3bjYbAW04F14JXOVegjeaby3CBfDQKRmnuRIr8fx3lPmXyROU1ldobXUeZ3RcJtLR3NSIzlu5EnyN3G4YoxsKXB1KR0vXBV-h3DcyrrErZFUINoilMfzGZZwJhJwbVCjyY3bTKV-Rb_k6kHgDsgGyaIUJ43nOo0GQGtdOAkO373JlMcg2fIeFjWeIkxaN-5ScdO2mOW7U0pYP9n0QIC9KrOGROYwAAAAH2EROSAA"
#) #broken_wiz

DEFAULT_LIMIT = 2000
PREMIUM_LIMIT = 7000
COOLDOWN_SECS = 10
CREDIT_COST   = 2

router = Router()
user_last_command_time: Dict[int, float] = {}

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# CLEAN LOGGER SETUP - No traceback spam
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# GIF Reactions  (identical to chk.py)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

REACTIONS = [
    "airkiss", "blush", "brofist", "celebrate", "cheers", "clap",
    "cool", "cuddle", "dance", "handhold", "happy", "hug",
    "kiss", "laugh", "lick", "love", "nervous", "nom",
    "nuzzle", "nyah", "pat", "peek", "shy", "sip",
    "sleep", "smile", "smug", "sorry", "thumbsup",
    "tickle", "tired", "wave", "wink", "yay", "yes"
]

async def get_anime_gif() -> str:
    reaction = random.choice(REACTIONS)
    api_url  = f"https://api.otakugifs.xyz/gif?reaction={reaction}"
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(api_url, timeout=10) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    return data.get("url", "")
    except Exception:
        pass  # Silent fail
    return "https://media.giphy.com/media/LdOyjZ7hx5S3yCjQ8I/giphy.gif"

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Database Helpers  (mirrors chk.py pattern)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

async def get_user_plan_name(user_id: int) -> str:
    is_premium, _ = get_premium_status(user_id)
    if is_premium:
        try:
            def _sync_fetch():
                conn   = get_db_connection()
                cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
                cursor.execute(
                    "SELECT plan FROM receipts WHERE user_id = %s ORDER BY purchased_on DESC LIMIT 1",
                    (user_id,)
                )
                row = cursor.fetchone()
                conn.close()
                return row['plan'].upper() if row else "PREMIUM"
            return await asyncio.to_thread(_sync_fetch)
        except Exception:
            return "PREMIUM"
    return "FREE"


async def update_user_stats(user_id: int, cards_found: int):
    def _sync_update():
        conn   = get_db_connection()
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE users SET cc_checked = cc_checked + 1 WHERE user_id = %s",
            (user_id,)
        )
        if cards_found > 0:
            cursor.execute(
                "UPDATE users SET cc_charged = cc_charged + 1 WHERE user_id = %s",
                (user_id,)
            )
        conn.commit()
        conn.close()
    await asyncio.to_thread(_sync_update)

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Scraper Helpers
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def remove_duplicates(cards: List[str]):
    unique = list(set(cards))
    return unique, len(cards) - len(unique)


def build_user_link(user_obj) -> str:
    name = user_obj.first_name or "User"
    if user_obj.username:
        return f'<a href="https://t.me/{user_obj.username}">{escape(name)}</a>'
    return f'<a href="tg://user?id={user_obj.id}">{escape(name)}</a>'

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Pyrogram Setup - FIXED: Lazy import to avoid event loop issue
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

PYROGRAM_AVAILABLE = False
user_client = None

# Define exception classes globally to avoid NameError
class _DummyException(Exception):
    pass

# These will be overridden when Pyrogram is imported
UserAlreadyParticipant = _DummyException
InviteHashExpired = _DummyException
InviteHashInvalid = _DummyException
InviteRequestSent = _DummyException
FloodWait = _DummyException
PeerIdInvalid = _DummyException
UsernameInvalid = _DummyException
UsernameNotOccupied = _DummyException
ChannelPrivate = _DummyException

def _init_pyrogram():
    """Lazy load Pyrogram to avoid Python 3.14 event loop issue"""
    global PYROGRAM_AVAILABLE, user_client
    global UserAlreadyParticipant, InviteHashExpired, InviteHashInvalid
    global InviteRequestSent, FloodWait, PeerIdInvalid, UsernameInvalid
    global UsernameNotOccupied, ChannelPrivate
    
    if PYROGRAM_AVAILABLE and user_client is not None:
        return True
    
    try:
        # Import Pyrogram here instead of at module level
        from pyrogram import Client as PyrogramClient
        from pyrogram.errors import (
            UserAlreadyParticipant as _UserAlreadyParticipant,
            InviteHashExpired as _InviteHashExpired,
            InviteHashInvalid as _InviteHashInvalid,
            InviteRequestSent as _InviteRequestSent,
            FloodWait as _FloodWait,
            PeerIdInvalid as _PeerIdInvalid,
            UsernameInvalid as _UsernameInvalid,
            UsernameNotOccupied as _UsernameNotOccupied,
            ChannelPrivate as _ChannelPrivate,
        )
        
        # Update global references
        UserAlreadyParticipant = _UserAlreadyParticipant
        InviteHashExpired = _InviteHashExpired
        InviteHashInvalid = _InviteHashInvalid
        InviteRequestSent = _InviteRequestSent
        FloodWait = _FloodWait
        PeerIdInvalid = _PeerIdInvalid
        UsernameInvalid = _UsernameInvalid
        UsernameNotOccupied = _UsernameNotOccupied
        ChannelPrivate = _ChannelPrivate
        
        user_client = PyrogramClient(
            "user_session",
            api_id=API_ID,
            api_hash=API_HASH,
            session_string=SESSION_STRING,
            workers=1000,
            no_updates=True,  # CRITICAL: Prevents automatic update handler errors
        )
        PYROGRAM_AVAILABLE = True
        logger.info("Pyrogram initialized successfully")
        return True
    except ImportError:
        logger.warning("Pyrogram not installed — run: pip install pyrogram tgcrypto")
        return False
    except Exception as e:
        logger.error(f"Pyrogram initialization failed: {e}")
        return False

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Pyrogram Lifecycle
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

async def initialize_pyrogram() -> bool:
    if not _init_pyrogram():
        return False
    if not user_client:
        return False
    try:
        await user_client.start()
        logger.info("Pyrogram client started successfully")
        return True
    except Exception as e:
        logger.error(f"Pyrogram start failed: {e}")
        return False


async def stop_pyrogram():
    global user_client
    if PYROGRAM_AVAILABLE and user_client:
        try:
            await user_client.stop()
            logger.info("Pyrogram client stopped")
        except Exception as e:
            logger.error(f"Pyrogram stop failed: {e}")

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# SAFE PEER RESOLUTION - FIXES THE MAIN ISSUE
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

async def safe_resolve_peer(client, channel_identifier: str) -> Optional[any]:
    """Safely resolve a peer without throwing traceback spam"""
    try:
        # Priority 1: Resolve with proper error handling
        peer = await client.resolve_peer(channel_identifier)
        return peer
    except (PeerIdInvalid, UsernameInvalid, UsernameNotOccupied, ChannelPrivate, KeyError, ValueError) as e:
        logger.info(f"[SCR] Peer invalid: {channel_identifier[:50]} - {type(e).__name__}")
        return None
    except Exception:
        return None


async def safe_join_private_chat(client, invite_link: str) -> bool:
    """Join private chat without error spam"""
    try:
        await client.join_chat(invite_link)
        logger.info(f"[SCR] Joined: {invite_link[:30]}...")
        return True
    except UserAlreadyParticipant:
        return True
    except InviteRequestSent:
        logger.info(f"[SCR] Join request sent")
        return False
    except (InviteHashExpired, InviteHashInvalid):
        logger.info(f"[SCR] Invalid invite link")
        return False
    except Exception:
        return False


async def validate_channel_access(client, channel_identifier: str) -> bool:
    """Validate channel is accessible before scraping"""
    try:
        chat = await client.get_chat(channel_identifier)
        return chat is not None
    except Exception:
        return False

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# SAFE TASK WRAPPER - PREVENTS ASYNCIO TRACEBACK SPAM
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def safe_task_wrapper(coro):
    """Wrapper that prevents unretrieved task exceptions"""
    async def wrapped():
        try:
            await coro
        except Exception as e:
            # Compact error logging - no traceback
            logger.info(f"[SCR] Task failed: {type(e).__name__}")
    return wrapped

def create_safe_task(coro):
    """Create a task that won't leak exceptions"""
    task = asyncio.create_task(coro)
    task.add_done_callback(lambda t: t.exception() if not t.cancelled() else None)
    return task

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Pyrogram Scraper Engine - SAFE VERSION
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

async def scrape_messages(
    client,
    channel_identifier: str,
    card_limit: int,
    start_number: Optional[str] = None,
    bank_name: Optional[str] = None,
) -> List[str]:
    """
    Scrape cards from a Telegram channel using Pyrogram's get_chat_history.
    Uses a single channel_identifier string (username or invite link).
    """
    collected: List[str] = []
    card_count = 0
    pattern    = r'\d{13,19}[\D]+\d{1,2}[\D]+\d{2,4}[\D]+\d{3,4}'

    logger.info(f"[SCR] Scraping: {channel_identifier[:50]} limit={card_limit}")

    # Step 1: Validate client is connected
    if not client or not client.is_connected:
        logger.info(f"[SCR] Client not connected")
        return []

    # Step 2: Validate channel is accessible
    if not await validate_channel_access(client, channel_identifier):
        logger.info(f"[SCR] Channel inaccessible: {channel_identifier[:50]}")
        return []

    # Step 3: Safe peer resolution (prevents KeyError/ValueError)
    peer = await safe_resolve_peer(client, channel_identifier)
    if not peer:
        logger.info(f"[SCR] Peer resolution failed")
        return []

    # Step 4: Scrape with comprehensive exception handling
    try:
        async for msg in client.get_chat_history(channel_identifier):
            if card_count >= card_limit:
                break

            text = msg.text or msg.caption
            if not text:
                continue

            if bank_name and bank_name.lower() not in text.lower():
                continue

            for match in re.findall(pattern, text):
                if card_count >= card_limit:
                    break
                digits = re.findall(r'\d+', match)
                if len(digits) < 4:
                    continue
                card_number, mo, year, cvv = digits[0], digits[1], digits[2], digits[3]
                year      = year[-2:]
                formatted = f"{card_number}|{mo}|{year}|{cvv}"

                if start_number:
                    if not card_number.startswith(start_number[:6]):
                        continue

                collected.append(formatted)
                card_count += 1

    except FloodWait as fw:
        logger.info(f"[SCR] FloodWait {fw.value}s")
    except (PeerIdInvalid, UsernameInvalid, UsernameNotOccupied, ChannelPrivate, KeyError, ValueError):
        logger.info(f"[SCR] Channel access denied")
    except Exception:
        logger.info(f"[SCR] Scrape interrupted")

    logger.info(f"[SCR] Complete: {len(collected)} cards")
    return collected[:card_limit]

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# /scr Command Handler (UNCHANGED)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

@router.message(F.text.startswith("/scr"))
async def scr_command(message: types.Message):
    """
    /scr <channel> <limit> [bin_or_bank]

    Examples:
        /scr @channelname 500
        /scr @channelname 500 515462
        /scr @channelname 500 Chase
        /scr https://t.me/+privateinvitelink 100
    """

    # ── 1. Gate check ────────────────────────────────────────────────────────
    if not await asyncio.to_thread(is_gate_enabled, "scr"):
        await message.reply(
            "🚧 <b>𝗦𝗰𝗿𝗮𝗽𝗲𝗿 𝗶𝘀 𝘂𝗻𝗱𝗲𝗿 𝗺𝗮𝗶𝗻𝘁𝗲𝗻𝗮𝗻𝗰𝗲.</b>\n"
            "𝗜𝘁 𝘄𝗶𝗹𝗹 𝗯𝗲 𝗿𝗲𝘀𝘁𝗼𝗿𝗲𝗱 𝘀𝗼𝗼𝗻.",
            parse_mode="HTML"
        )
        return

    user         = message.from_user
    user_id      = user.id
    current_time = time.time()

    # ── 2. Premium check ─────────────────────────────────────────────────────
    is_premium, _ = await asyncio.to_thread(get_premium_status, user_id)

    # ── 3. Cooldown  (free users only) ──────────────────────────────────────
    if not is_premium:
        last_time = user_last_command_time.get(user_id)
        if last_time is not None:
            elapsed = current_time - last_time
            if elapsed < COOLDOWN_SECS:
                remaining = round(COOLDOWN_SECS - elapsed, 1)
                await message.reply(
                    f"<tg-emoji emoji-id=\"6255910249362885846\">⚠️</tg-emoji> "
                    f"<b>𝗔𝗰𝘁𝗶𝘃𝗲 𝗰𝗼𝗼𝗹𝗱𝗼𝘄𝗻 !</b>\n\n"
                    f"𝗣𝗹𝗲𝗮𝘀𝗲 𝘄𝗮𝗶𝘁 <code>{remaining}</code> 𝘀𝗲𝗰𝗼𝗻𝗱𝘀 𝗯𝗲𝗳𝗼𝗿𝗲 𝗰𝗼𝗻𝘁𝗶𝗻𝘂𝗶𝗻𝗴.\n\n"
                    f"<tg-emoji emoji-id=\"6136275172283391020\">⭐</tg-emoji> "
                    f"𝗣𝘂𝗿𝗰𝗵𝗮𝘀𝗲 𝗮 𝗽𝗿𝗲𝗺𝗶𝘂𝗺 𝗽𝗹𝗮𝗻 𝘁𝗼 𝗿𝗲𝗺𝗼𝘃𝗲 𝘁𝗵𝗲 𝗰𝗼𝗼𝗹𝗱𝗼𝘄𝗻.",
                    parse_mode="HTML"
                )
                return
        user_last_command_time[user_id] = current_time

    # ── 4. Parse arguments ────────────────────────────────────────────────────
    parts = message.text.strip().split()
    args  = parts[1:]

    if len(args) < 2:
        await message.reply(
            "❌ <b>Usage:</b> <code>/scr [channel] [limit] [bin/bank]</code>\n\n"
            "<b>Examples:</b>\n"
            "• <code>/scr @channel 500</code>\n"
            "• <code>/scr @channel 500 515462</code>\n"
            "• <code>/scr @channel 500 Chase</code>\n"
            "• <code>/scr https://t.me/+link 200</code>",
            parse_mode="HTML"
        )
        return

    # ── 5. Credits check ─────────────────────────────────────────────────────
    current_credits = await asyncio.to_thread(get_user_credits, user_id)
    if current_credits is None or current_credits <= 0:
        await message.reply(
            "❌ <b>Insufficient Credits!</b>\n\n"
            "You have <b>0 credits</b> left.\n"
            "Please recharge to continue using this service.",
            parse_mode="HTML"
        )
        return

    # ── 6. Fetch plan name ────────────────────────────────────────────────────
    plan_name = await get_user_plan_name(user_id)

    # ── 7. Resolve channel ────────────────────────────────────────────────────
    channel_identifier = args[0]
    channel_id: Optional[int]       = None
    channel_name                    = "Unknown"
    channel_username: Optional[str] = None

    logger.info(f"Resolving channel: {channel_identifier}")

    if channel_identifier.lstrip("-").isdigit():
        # Numeric chat ID
        try:
            chat             = await message.bot.get_chat(int(channel_identifier))
            channel_name     = chat.title or str(channel_identifier)
            channel_id       = int(channel_identifier)
            channel_username = getattr(chat, "username", None)
        except Exception as e:
            logger.info(f"Failed to resolve chat ID: {e}")
            await message.reply(
                f"❌ <b>Invalid chat ID</b>\n<code>{escape(str(e))}</code>",
                parse_mode="HTML"
            )
            return

    elif channel_identifier.startswith("https://t.me/+"):
        # Private invite link — needs Pyrogram to join first
        if not _init_pyrogram() or not user_client or not user_client.is_connected:
            await message.reply(
                "⚠️ <b>Scraper offline</b> — Pyrogram client is not running.\n"
                "<i>Private invite links require the Pyrogram session to be active.</i>",
                parse_mode="HTML"
            )
            return
        try:
            await safe_join_private_chat(user_client, channel_identifier)
            chat             = await user_client.get_chat(channel_identifier)
            channel_name     = chat.title or channel_identifier
            channel_id       = chat.id
            channel_username = getattr(chat, "username", None)
        except Exception as e:
            logger.info(f"Failed to join private channel: {e}")
            await message.reply(
                f"❌ <b>Failed to join private channel</b>\n<code>{escape(str(e))}</code>",
                parse_mode="HTML"
            )
            return

    else:
        # Public @username or t.me/username link
        if channel_identifier.startswith("https://t.me/"):
            channel_username = channel_identifier[len("https://t.me/"):]
        elif channel_identifier.startswith("t.me/"):
            channel_username = channel_identifier[len("t.me/"):]
        else:
            channel_username = channel_identifier

        if not channel_username.startswith("@"):
            channel_username = "@" + channel_username

        try:
            chat             = await message.bot.get_chat(channel_username)
            channel_name     = chat.title or channel_username
            channel_id       = chat.id
            channel_username = getattr(chat, "username", None) or channel_username
        except Exception as e:
            logger.info(f"Failed to resolve username: {e}")
            await message.reply(
                f"❌ <b>Incorrect username or chat ID</b>\n<code>{escape(str(e))}</code>",
                parse_mode="HTML"
            )
            return

    # ── 8. Parse limit ────────────────────────────────────────────────────────
    try:
        limit = int(args[1])
    except ValueError:
        await message.reply(
            "❌ <b>Invalid limit</b>\n"
            "<i>Limit must be a number. Example: /scr @channel 500</i>",
            parse_mode="HTML"
        )
        return

    if limit <= 0:
        await message.reply("❌ <b>Limit must be greater than 0.</b>", parse_mode="HTML")
        return

    max_limit = PREMIUM_LIMIT if is_premium else DEFAULT_LIMIT
    if limit > max_limit:
        await message.reply(
            f"❌ <b>Limit too high</b>\n\n"
            f"Your <b>{plan_name}</b> plan allows a maximum of <b>{max_limit}</b> cards.\n"
            f"<i>Reduce your limit or upgrade your plan.</i>",
            parse_mode="HTML"
        )
        return

    # ── 9. Optional BIN / Bank filter ─────────────────────────────────────────
    bin_filter: Optional[str]  = None
    bank_filter: Optional[str] = None
    if len(args) > 2:
        if args[2].isdigit():
            bin_filter = args[2]
        else:
            bank_filter = " ".join(args[2:])

    # ── 10. Send processing message ───────────────────────────────────────────
    filter_display = bin_filter or bank_filter or "None"
    proc_msg = await message.reply(
        f"<pre><b>Sᴄʀᴀᴘᴘɪɴɢ Iɴ Pʀᴏɢʀᴇss⏳...</b></pre>\n"
        f"<b>Sᴏᴜʀᴄᴇ ➺</b> <code>{escape(channel_name)}</code>\n"
        f"<b>Lɪᴍɪᴛ ➺</b> <code>{limit}</code>\n"
        f"<b>Fɪʟᴛᴇʀ ➺</b> <code>{escape(str(filter_display))}</code>",
        parse_mode="HTML"
    )

    logger.info(f"SCR started: user={user_id} channel={channel_name} limit={limit}")

    # ── 11. Background scraping task - USING SAFE WRAPPER ──────────────────────
    create_safe_task(
        process_scr(
            message          = message,
            proc_msg         = proc_msg,
            user             = user,
            user_id          = user_id,
            plan_name        = plan_name,
            is_premium       = is_premium,
            channel_name     = channel_name,
            channel_id       = channel_id,
            channel_username = channel_username,
            limit            = limit,
            bin_filter       = bin_filter,
            bank_filter      = bank_filter,
        )
    )


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Background Processor - SAFE VERSION (NO TRACEBACK SPAM)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

async def process_scr(
    message, proc_msg, user, user_id, plan_name, is_premium,
    channel_name, channel_id, channel_username,
    limit, bin_filter, bank_filter
):
    # A. Verify Pyrogram is connected and auto-reconnect if needed
    if not _init_pyrogram() or not user_client:
        logger.info(f"[SCR] Pyrogram unavailable")
        try:
            await proc_msg.edit_text(
                f"⚠️ <b>Scraper Offline</b>\n<code>Pyrogram not available</code>",
                parse_mode="HTML"
            )
        except Exception:
            pass
        return

    # Auto-reconnect if disconnected
    if not user_client.is_connected:
        try:
            await user_client.start()
            logger.info(f"[SCR] Reconnected Pyrogram")
        except Exception:
            logger.info(f"[SCR] Failed to reconnect")
            try:
                await proc_msg.edit_text(
                    f"⚠️ <b>Scraper Offline</b>\n<code>Cannot connect to Telegram</code>",
                    parse_mode="HTML"
                )
            except Exception:
                pass
            return

    # B. Build the single identifier to pass to Pyrogram:
    if channel_username:
        pyrogram_target = channel_username if channel_username.startswith("@") else f"@{channel_username}"
    else:
        pyrogram_target = str(channel_id)

    # C. Run the scraper (safely)
    try:
        raw_cards = await scrape_messages(
            client             = user_client,
            channel_identifier = pyrogram_target,
            card_limit         = limit,
            start_number       = bin_filter,
            bank_name          = bank_filter,
        )
    except Exception:
        # Silent catch - no traceback
        logger.info(f"[SCR] Scrape failed for user {user_id}")
        raw_cards = []

    unique_cards, dupes_removed = remove_duplicates(raw_cards)
    cards_found = len(unique_cards)
    logger.info(f"[SCR] Result: {cards_found} unique, {dupes_removed} dupes")

    # D. Credit deduction
    if cards_found > 0:
        current_balance = await asyncio.to_thread(get_user_credits, user_id)
        new_balance     = max(0, current_balance - CREDIT_COST)
        await asyncio.to_thread(update_credits, user_id, new_balance)
        logger.info(f"[SCR] Credits: user={user_id} -{CREDIT_COST}")
    else:
        new_balance = await asyncio.to_thread(get_user_credits, user_id)

    # E. Update stats
    await update_user_stats(user_id, cards_found)

    # F. Build result caption
    user_link    = build_user_link(user)
    dev_link = dev_badge()
    user_display = f"{user_link} {plan_badge(plan_name)}"

    filter_line = ""
    if bin_filter:
        filter_line = f"BIN Fɪʟᴛᴇʀ ➺ <code>{escape(bin_filter)}</code>\n"
    elif bank_filter:
        filter_line = f"Bᴀɴᴋ Fɪʟᴛᴇʀ ➺ <code>{escape(bank_filter)}</code>\n"

    credits_warning = ""
    if new_balance <= 0:
        credits_warning = "\n⚠️ <b>Warning:</b> <i>You have 0 credits left. Please recharge.</i>"

    status_line = "Sᴛᴀᴛᴜs ➺ Cᴏᴍᴘʟᴇᴛᴇᴅ ✅" if cards_found > 0 else "Sᴛᴀᴛᴜs ➺ Nᴏ Cᴀʀᴅs Fᴏᴜɴᴅ ❌"

    final_caption = (
        f"{status_line}\n"
        f"Sᴏᴜʀᴄᴇ ➺ <code>{escape(channel_name)}</code>\n"
        f"Cᴀʀᴅs Fᴏᴜɴᴅ ➺ <code>{cards_found}</code>\n"
        f"Dᴜᴘʟɪᴄᴀᴛᴇ Rᴇᴍᴏᴠᴇᴅ ➺ <code>{dupes_removed}</code>\n"
        f"{filter_line}"
        f"Lɪᴍɪᴛ Usᴇᴅ ➺ <code>{limit}</code>\n"
        f"Cʀᴇᴅɪᴛs Lᴇғᴛ ➺ <code>{new_balance}</code>\n"
        f"Usᴇʀ ➺ {user_display}\n"
        f"Dᴇᴠ ➺ {dev_link}"
        f"{credits_warning}"
    )

    # G. Write cards to file if any found
    file_path: Optional[str] = None
    if cards_found > 0:
        try:
            safe_name = re.sub(r'[^\w\-]', '_', channel_name)
            file_path = f"x{cards_found}_{safe_name}.txt"
            async with aiofiles.open(file_path, mode='w') as f:
                await f.write("\n".join(unique_cards))
        except Exception:
            file_path = None

    # H. Fetch anime GIF
    gif_url = await get_anime_gif()

    # I. Delete processing message and send result
    try:
        try:
            await proc_msg.delete()
        except Exception:
            pass

        if cards_found > 0 and file_path and os.path.exists(file_path):
            try:
                await message.reply_animation(
                    animation  = gif_url,
                    caption    = final_caption,
                    parse_mode = "HTML",
                    disable_web_page_preview=True,
                )
                await message.reply_document(
                    document   = FSInputFile(file_path),
                    caption    = f"📁 <b>{cards_found} cards</b> from <code>{escape(channel_name)}</code>",
                    parse_mode = "HTML",
                )
            except (TelegramForbiddenError, TelegramBadRequest):
                await message.reply(
                    text       = final_caption,
                    parse_mode = "HTML",
                    disable_web_page_preview=True,
                )
                try:
                    await message.reply_document(
                        document   = FSInputFile(file_path),
                        caption    = f"📁 <b>{cards_found} cards</b> from <code>{escape(channel_name)}</code>",
                        parse_mode = "HTML",
                    )
                except Exception:
                    pass
        else:
            try:
                await message.reply_animation(
                    animation  = gif_url,
                    caption    = final_caption,
                    parse_mode = "HTML",
                    disable_web_page_preview=True,
                )
            except (TelegramForbiddenError, TelegramBadRequest):
                await message.reply(
                    text       = final_caption,
                    parse_mode = "HTML",
                    disable_web_page_preview=True,
                )

    except Exception:
        try:
            await proc_msg.edit_text(
                text       = final_caption,
                parse_mode = "HTML",
                disable_web_page_preview=True,
            )
        except Exception:
            await message.reply(
                text       = final_caption,
                parse_mode = "HTML",
                disable_web_page_preview=True,
            )
    finally:
        if file_path and os.path.exists(file_path):
            try:
                os.remove(file_path)
            except OSError:
                pass


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Exports
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

__all__ = [
    "router",
    "scr_command",
    "initialize_pyrogram",
    "stop_pyrogram",
]