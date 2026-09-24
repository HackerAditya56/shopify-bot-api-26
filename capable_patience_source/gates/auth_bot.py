import asyncio
import re
import logging
import time
import random
import aiohttp
from html import escape

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# AIogram Imports
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
from aiogram import types, F, Router
from aiogram.exceptions import TelegramForbiddenError, TelegramBadRequest

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# LOCAL IMPORTS
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
from database import is_gate_enabled, get_user_credits, update_credits
from bin import get_bin_info
from sub import get_premium_status
from gates.auth import check_cc

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# PREMIUM EMOJI IDs
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
CUSTOM_CHARGED_EMOJI_ID = "4956719506027185156"
CUSTOM_APPROVED_EMOJI_ID = "4958610528588008305"
CUSTOM_DECLINED_EMOJI_ID = "4956612582816351459"

router = Router()
user_last_command_time = {}

REACTIONS = [
    "airkiss", "blush", "brofist", "celebrate", "cheers", "clap",
    "cool", "cuddle", "dance", "handhold", "happy", "hug",
    "kiss", "laugh", "lick", "love", "nervous", "nom",
    "nuzzle", "nyah", "pat", "peek", "shy", "sip",
    "sleep", "smile", "smug", "sorry", "thumbsup",
    "tickle", "tired", "wave", "wink", "yay", "yes"
]

async def get_anime_gif():
    reaction = random.choice(REACTIONS)
    api_url = f"https://api.otakugifs.xyz/gif?reaction={reaction}"
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(api_url, timeout=10) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    return data.get("url")
    except Exception as e:
        logging.error(f"Error fetching anime gif: {e}")
    return "https://media.giphy.com/media/v1.Y2lkPTc5MGI3NjExM3Z6eXF6eXF6eXF6eXF6eXF6eXF6eXF6SZlcD12MV9pbnRlcm5hbF9naWZfYnlfaWQmY3Q9Zw/LdOyjZ7h5xS3yCjQ8I/giphy.gif"

def luhn_check(card_number):
    card_number = str(card_number).strip()
    if not card_number.isdigit():
        return False
    total = 0
    reverse_digits = card_number[::-1]
    for i, char in enumerate(reverse_digits):
        digit = int(char)
        if i % 2 == 1:
            digit *= 2
            if digit > 9:
                digit -= 9
        total += digit
    return total % 10 == 0

def build_user_link(user_obj):
    name = user_obj.first_name or "User"
    if user_obj.username:
        return f'<a href="https://t.me/{user_obj.username}">{name}</a>'
    return f'<a href="tg://user?id={user_obj.id}">{name}</a>'

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# COMMAND HANDLER
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

@router.message(F.text.startswith("/auth"))
async def auth_command(message: types.Message):
    # 1. GATE CHECK
    if not await asyncio.to_thread(is_gate_enabled, "auth"):
        await message.reply(
            "🚧 <b>𝗔𝘂𝘁𝗵 𝗚𝗮𝘁𝗲 𝗶𝘀 𝘂𝗻𝗱𝗲𝗿 𝗺𝗮𝗶𝗻𝘁𝗲𝗻𝗮𝗻𝗰𝗲.</b>\n"
            "𝗜𝘁 𝘄𝗶𝗹𝗹 𝗯𝗲 𝗯𝗮𝗰𝗸 𝘀𝗵𝗼𝗿𝘁𝗹𝘆.",
            parse_mode="HTML"
        )
        return

    user = message.from_user
    user_id = user.id
    current_time = time.time()

    # 2. PREMIUM STATUS
    is_premium, _ = await asyncio.to_thread(get_premium_status, user_id)

    # 3. RATE LIMIT (free users)
    if not is_premium:
        if user_id in user_last_command_time:
            elapsed = current_time - user_last_command_time[user_id]
            if elapsed < 10:
                remaining_time = round(10 - elapsed, 1)
                await message.reply(
                    f"<tg-emoji emoji-id=\"6255910249362885846\">⚠️</tg-emoji> <b>𝗔𝗰𝘁𝗶𝘃𝗲 𝗰𝗼𝗼𝗹𝗱𝗼𝘄𝗻 !</b>\n\n"
                    f"𝗣𝗹𝗲𝗮𝘀𝗲 𝘄𝗮𝗶𝘁 <code>{remaining_time}</code> 𝘀𝗲𝗰𝗼𝗻𝗱𝘀.",
                    parse_mode="HTML"
                )
                return
        user_last_command_time[user_id] = current_time

    # 4. EXTRACT CARD
    parts = message.text.split(maxsplit=1)
    raw_text = ""
    if len(parts) > 1:
        raw_text = parts[1].strip()
    elif message.reply_to_message:
        raw_text = message.reply_to_message.text or message.reply_to_message.caption

    if not raw_text:
        await message.reply(
            "❌ <b>Usage:</b> /auth <code>cc|mm|yy|cvv</code>\n"
            "Or reply to a message containing card details.",
            parse_mode="HTML"
        )
        return

    pattern = r'\b(\d{15,16})[|\s/?\\:]+(\d{2,4})[|\s/?\\:]+(\d{2,4})[|\s/?\\:]+(\d{3,4})\b'
    match = re.search(pattern, raw_text)
    if not match:
        await message.reply(
            "❌ <b>Invalid Card Format.</b>\n"
            "Please provide CC as <code>4242424242424242|05|27|123</code>",
            parse_mode="HTML"
        )
        return

    cc, mm, yy_raw, cvv = match.groups()
    yy = yy_raw[2:] if len(yy_raw) == 4 else yy_raw
    formatted_cc = f"{cc}|{mm}|{yy}|{cvv}"

    # 5. LUHN CHECK
    if not luhn_check(cc):
        await message.reply("❌ <b>Invalid Card</b>\nYour card number is incorrect.", parse_mode="HTML")
        return

    # 6. CREDITS
    current_credits = await asyncio.to_thread(get_user_credits, user_id)
    if current_credits is None or current_credits <= 0:
        await message.reply("❌ <b>Insufficient Credits!</b>\n\nYou have 0 credits left.", parse_mode="HTML")
        return

    # 7. PLAN NAME
    is_premium2, _ = await asyncio.to_thread(get_premium_status, user_id)
    plan_name = "PREMIUM" if is_premium2 else "FREE"

    # 8. PROCESSING MESSAGE
    proc_msg = await message.reply(
        f"<tg-emoji emoji-id=\"6253754970349243649\">✨</tg-emoji> <b>𝗣𝗿𝗼𝗰𝗲𝘀𝘀𝗶𝗻𝗴...</b>\n"
        f"<code>{escape(formatted_cc)}</code>\n"
        f"<b>𝗚𝗮𝘁𝗲𝘄𝗮𝘆 ➠ 𝗔𝘂𝘁𝗵</b>",
        parse_mode="HTML"
    )

    # 9. BACKGROUND
    asyncio.create_task(process_auth_check(message, proc_msg, user, user_id, formatted_cc, cc, plan_name))

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# BACKGROUND PROCESSOR
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

async def process_auth_check(message, proc_msg, user, user_id, formatted_cc, cc, plan_name):
    try:
        status, res_msg, brand = await asyncio.to_thread(check_cc, formatted_cc)
    except Exception as e:
        logging.error(f"𝗔𝘂𝘁𝗵 check error: {e}")
        status, res_msg, brand = "ERROR", str(e), "UNKNOWN"

    if not status:
        status, res_msg, brand = "ERROR", "Internal Processing Error", "UNKNOWN"

    # BIN LOOKUP
    try:
        bin_info = await get_bin_info(cc[:6])
    except Exception:
        bin_info = {}
    bin_scheme = bin_info.get("scheme", "N/A")
    bin_bank = bin_info.get("bank", "N/A")
    country_name = bin_info.get("country", "N/A")
    country_flag = bin_info.get("country_emoji", "")
    bin_country = f"{country_name} {country_flag}" if country_flag else country_name

    status_upper = str(status).upper()
    is_charged = False
    credits_to_deduct = 0

    if status_upper in ("APPROVED", "LIVE", "3DS", "CHARGED"):
        final_status = f'𝗔𝗣𝗣𝗥𝗢𝗩𝗘𝗗 <tg-emoji emoji-id="{CUSTOM_APPROVED_EMOJI_ID}">✅</tg-emoji>'
        is_charged = True
        credits_to_deduct = 1
    elif status_upper == "DECLINED":
        final_status = f'𝗗𝗘𝗖𝗟𝗜𝗡𝗘𝗗 <tg-emoji emoji-id="{CUSTOM_DECLINED_EMOJI_ID}">❌</tg-emoji>'
        credits_to_deduct = 1
    else:
        final_status = "𝗘𝗥𝗥𝗢𝗥 ⚠️"
        credits_to_deduct = 0

    # CREDIT DEDUCTION
    if credits_to_deduct > 0:
        current_balance = await asyncio.to_thread(get_user_credits, user_id)
        new_balance = max(0, current_balance - credits_to_deduct)
        await asyncio.to_thread(update_credits, user_id, new_balance)

    # STATS
    def _sync_stats():
        from database import get_db_connection
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("UPDATE users SET cc_checked = cc_checked + 1 WHERE user_id = %s", (user_id,))
        if is_charged:
            cur.execute("UPDATE users SET cc_charged = cc_charged + 1 WHERE user_id = %s", (user_id,))
        conn.commit()
        conn.close()
    await asyncio.to_thread(_sync_stats)

    # FINAL CAPTION
    user_link = build_user_link(user)
    dev_link = '<a href="https://t.me/Enchanted_linux_0x">Enchanted_linux_0x</a>'
    user_display = f"{user_link} <b>[{plan_name}]</b>"

    final_caption = (
        f"𝗦𝘁𝗮𝘁𝘂𝘀 ➠ {final_status}\n"
        f"𝗖𝗮𝗿𝗱 ➠ <code>{formatted_cc}</code>\n"
        f"𝗚𝗮𝘁𝗲𝘄𝗮𝘆 ➠ 𝗔𝘂𝘁𝗵\n"
        f"𝗥𝗲𝘀𝗽𝗼𝗻𝘀𝗲 ➠ <b>{escape(str(res_msg))}</b>\n"
        f"𝗕𝗿𝗮𝗻𝗱 ➠ <b>{escape(str(brand))}</b>\n"
        f"𝗜𝘀𝘀𝘂𝗲𝗿 ➠ <b>{bin_bank}</b>\n"
        f"𝗖𝗼𝘂𝗻𝘁𝗿𝘆 ➠ <b>{bin_country}</b>\n"
        f"𝗨𝘀𝗲𝗿 ➠ {user_display}\n"
        f"𝗗𝗲𝘃 ➠ {dev_link}"
    )

    gif_url = await get_anime_gif()

    try:
        try:
            await proc_msg.delete()
        except Exception:
            pass
        await message.reply_animation(
            animation=gif_url, caption=final_caption, parse_mode="HTML", disable_web_page_preview=True
        )
    except (TelegramForbiddenError, TelegramBadRequest) as e:
        logging.warning(f"[auth] Could not send GIF, falling back to text: {e}")
        try:
            await proc_msg.edit_text(text=final_caption, parse_mode="HTML", disable_web_page_preview=True)
        except Exception as edit_err:
            logging.error(f"Error editing message: {edit_err}")
            try:
                await message.reply(text=final_caption, parse_mode="HTML", disable_web_page_preview=True)
            except Exception as reply_err:
                logging.error(f"Error replying: {reply_err}")
    except Exception as e:
        logging.error(f"Error sending result: {e}")
        try:
            await proc_msg.edit_text(text=final_caption, parse_mode="HTML", disable_web_page_preview=True)
        except Exception:
            try:
                await message.reply(text=final_caption, parse_mode="HTML", disable_web_page_preview=True)
            except Exception as reply_err:
                logging.error(f"Error replying: {reply_err}")
