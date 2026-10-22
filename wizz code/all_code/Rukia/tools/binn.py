import sys
import os
import re
import asyncio
import logging
import aiohttp

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Aiogram Imports
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
from aiogram import Router, F, types
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# PATH FIX (To import database from root folder)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# LOCAL IMPORTS
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
from database import get_user_credits, update_credits, get_collection
from sub import get_premium_status, ADMIN_IDS
from mass_gates.utils import _log_premium_plan

# Premium Emoji IDs (provided by owner)
EMOJI_RED_TICK   = "6147565374289220368"
EMOJI_BLUE_TICK  = "5278628026416909103"
EMOJI_LIGHTNING  = "5350835008007324644"
EMOJI_STAR       = "5359686514697576863"
EMOJI_FIRE       = "6186076099764555777"
EMOJI_CROWN      = "6338940587193930733"

# Initialize Router
router = Router()

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# HELPER: FETCH BIN FROM API DIRECTLY
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
async def fetch_bin_from_api(bin_number: str) -> dict:
    url = f"https://bins.antipublic.cc/bins/{bin_number}"
    async with aiohttp.ClientSession() as session:
        try:
            async with session.get(url, timeout=10) as resp:
                if resp.status == 200:
                    return await resp.json()
                elif resp.status == 404:
                    return {"error": "BIN not found."}
                elif resp.status == 429:
                    return {"error": "Rate limit exceeded."}
                else:
                    return {"error": f"API Error: HTTP {resp.status}"}
        except asyncio.TimeoutError:
            return {"error": "Request Timed Out."}
        except Exception as e:
            return {"error": f"Connection Error: {str(e)}"}

async def get_plan_name_from_db(user_id) -> str:
    """Fetches the plan name from receipts DB (only called when user is premium).
    Admin always shows ULTIMATE — even if their is_premium flag is 0
    (e.g. when an admin account has no /sub receipt in DB)."""
    if user_id in ADMIN_IDS:
        return "ULTIMATE"
    def _sync_fetch():
        col = get_collection("receipts")
        r = col.find_one({"user_id": user_id}, sort=[("purchased_on", -1)])
        if r and r.get("plan"):
            return str(r["plan"]).upper()
        return "NO PLAN"
    try:
        return await asyncio.to_thread(_sync_fetch)
    except Exception as e:
        logging.error(f"Error fetching plan name: {e}")
        return "NO PLAN"

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# COMMAND HANDLER (Aiogram 3.x)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

@router.message(F.text.startswith("/binn"))
async def binn_command(message: types.Message):
    """
    Fetches and displays BIN info using the direct API.
    Works with Args or Reply to a message.
    Deducts 1 credit on successful lookup.
    """

    user = message.from_user
    user_id = user.id

    # 1. EXTRACT TEXT (Check Arguments, then Reply)
    raw_text = ""

    parts = message.text.split()
    if len(parts) > 1:
        raw_text = " ".join(parts[1:])
    elif message.reply_to_message:
        replied_msg = message.reply_to_message
        if replied_msg.text:
            raw_text = replied_msg.text
        elif replied_msg.caption:
            raw_text = replied_msg.caption

    # 2. Validate that we have some text
    if not raw_text:
        await message.reply(
            "Error ➛ <b>Missing Argument<tg-emoji emoji-id='5397890704062038337'>❌</tg-emoji></b>\n"
            "Usage: <code>/bin 456789</code>\n",
            parse_mode="HTML"
        )
        return

    # 3. Extract and Clean Input (Get first 6 digits)
    digits_only = re.sub(r'\D', '', raw_text)

    if len(digits_only) < 6:
        await message.reply(
            "Error ➛ <b>Invalid Input<tg-emoji emoji-id='5397890704062038337'>❌</tg-emoji></b>\n"
            "Please provide at least 6 digits in the argument or replied message.",
            parse_mode="HTML"
        )
        return

    bin_6 = digits_only[:6]

    # 4. Run premium check AND BIN fetch simultaneously
    (is_premium, _), data = await asyncio.gather(
        asyncio.to_thread(get_premium_status, user_id),
        fetch_bin_from_api(bin_6)
    )
    # Admins always treated as premium (Elite + Unlimited)
    if user_id in ADMIN_IDS:
        is_premium = True

    # 5. Credit check (only for non-premium users)
    current_credits = 0
    if not is_premium:
        current_credits = await asyncio.to_thread(get_user_credits, user_id)
        if current_credits <= 0:
            await message.reply(
                "<tg-emoji emoji-id='5397890704062038337'>❌</tg-emoji> <b>Insufficient Credits!</b>\n\n"
                "You have 0 credits left.",
                parse_mode="HTML"
            )
            return

    # 6. Deduct credit IF fetch was successful
    if "error" not in data and not is_premium:
        await asyncio.to_thread(update_credits, user_id, current_credits - 1)

    # 7. Prepare UI Variables (get plan name in parallel with nothing — just fetch it)
    plan_name = await get_plan_name_from_db(user_id) if is_premium else "TRIAL"
    # Admin override: always show Elite
    if user_id in ADMIN_IDS:
        plan_name = "Elite"
    # Debug-log premium plan detection to premium_plans.txt (skips NO PLAN / TRIAL).
    try:
        _log_premium_plan(user.id, getattr(user, "username", None), plan_name)
    except Exception:
        pass
    user_link = f'<a href="tg://user?id={user.id}">{user.first_name}</a>'
    user_display = f"{user_link} <b>({plan_name})</b>"

    # 8. Format Response
    if "error" in data:
        final_text = (
            f"Status ➛ <b>Error</b>\n"
            f"Message ➛ <code>{data['error']}</code>\n"
            f"<tg-emoji emoji-id=\"{EMOJI_CROWN}\"><tg-emoji emoji-id='6338940587193930733'>👑</tg-emoji></tg-emoji> <b><a href=\"https://t.me/ShopifyxoBot\">Rukia Shopify</a></b>"
        )
    else:
        api_bin = data.get("bin", bin_6)
        brand = data.get("brand", "N/A")
        level = data.get("level", "N/A")
        bank = data.get("bank", "N/A")
        country = data.get("country_name", "N/A")
        flag = data.get("country_flag", "")
        card_type = data.get("type", "N/A")
        currencies = data.get("country_currencies", [])

        country_display = f"{flag} {country}" if flag else country
        currency_display = currencies[0] if currencies else "N/A"

        final_text = (
            f"Bin ➛ <code>{api_bin}</code>\n"
            f"Brand ➛ <b>{brand}</b>\n"
            f"Level ➛ <b>{level}</b>\n"
            f"Bank ➛ <b>{bank}</b>\n"
            f"Country ➛ <b>{country_display}</b>\n"
            f"Type ➛ <b>{card_type}</b>\n"
            f"Currency ➛ <b>{currency_display}</b>\n"
            f"User ➛ {user_display}\n"
            f"<tg-emoji emoji-id=\"{EMOJI_CROWN}\"><tg-emoji emoji-id='6338940587193930733'>👑</tg-emoji></tg-emoji> <b><a href=\"https://t.me/ShopifyxoBot\">Rukia Shopify</a></b>"
        )

    # 9. Send Direct Reply
    await message.reply(
        text=final_text,
        parse_mode="HTML",
        disable_web_page_preview=True
    )
