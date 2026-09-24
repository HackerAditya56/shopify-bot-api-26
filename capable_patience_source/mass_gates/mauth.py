import asyncio
import re
import time
from datetime import datetime

from aiogram import types, F, Router

from database import is_gate_enabled, get_user_credits
from sub import get_premium_status
from mass_gates._batch_common import run_batch_check, handle_result_callback, handle_stop_callback
from gates.auth import check_cc

router = Router()

MAX_VALID_CARDS = 5000


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


def is_expired(mm, yy):
    try:
        now = datetime.now()
        cy = now.year % 100
        cm = now.month
        ey, em = int(yy), int(mm)
        if ey < cy:
            return True
        if ey == cy and em < cm:
            return True
        return False
    except ValueError:
        return True


def extract_cards(text):
    pattern = r'(\d{13,19})\s*[|/\\:\s]\s*(\d{1,2})\s*[|/\\:\s]\s*(\d{2,4})\s*[|/\\:\s]\s*(\d{3,4})'
    cards = []
    for m in re.findall(pattern, text):
        cc, mm, yy, cvv = m
        mm = mm.zfill(2)
        if len(yy) == 4:
            yy = yy[2:]
        cards.append(f"{cc}|{mm}|{yy}|{cvv}")
    return cards


@router.message(F.text.startswith("/mauth") | F.caption.startswith("/mauth"))
async def mauth_command(message: types.Message):
    if not await asyncio.to_thread(is_gate_enabled, "mauth"):
        await message.reply("🚧 <b>𝗔𝘂𝘁𝗵 𝗠𝗮𝘀𝘀 𝗚𝗮𝘁𝗲 𝘂𝗻𝗱𝗲𝗿 𝗠𝗮𝗶𝗻𝘁𝗲𝗻𝗮𝗻𝗰𝗲.</b>", parse_mode="HTML")
        return

    user = message.from_user
    user_id = user.id

    is_premium, _ = await asyncio.to_thread(get_premium_status, user_id)
    if not is_premium:
        await message.reply(
            "💎 𝗣𝗹𝗲𝗮𝘀𝗲 𝘂𝗽𝗴𝗿𝗮𝗱𝗲 𝘆𝗼𝘂𝗿 𝗽𝗹𝗮𝗻 𝘁𝗼 𝘂𝘀𝗲 𝘁𝗵𝗶𝘀 𝗳𝗲𝗮𝘁𝘂𝗿𝗲.\n\n👉 𝗨𝘀𝗲 /plan 𝘁𝗼 𝘂𝗽𝗴𝗿𝗮𝗱𝗲.",
            parse_mode="HTML"
        )
        return

    # collect cards from inline / reply / file
    raw_text = ""
    cmd_text = message.text or message.caption or ""
    parts = cmd_text.split(maxsplit=1)
    if len(parts) > 1:
        raw_text += parts[1] + " "
    if message.reply_to_message:
        rm = message.reply_to_message
        if rm.text:
            raw_text += rm.text + " "
        elif rm.caption:
            raw_text += rm.caption + " "

    document = message.document
    if not document and message.reply_to_message:
        document = message.reply_to_message.document
    if document:
        try:
            file_info = await message.bot.get_file(document.file_id)
            data = await message.bot.download_file(file_info.file_path)
            raw_text += data.read().decode('utf-8', errors='ignore')
        except Exception as e:
            await message.reply(f"❌ Error reading file: {e}")
            return

    if not raw_text.strip():
        await message.reply(
            "❌ <b>𝗡𝗼 𝗰𝗮𝗿𝗱𝘀 𝗳𝗼𝘂𝗻𝗱.</b>\n\n"
            "• <code>/mauth cc|mm|yy|cvv</code>\n"
            "• Reply to cards with <code>/mauth</code>\n"
            "• Send .txt file with <code>/mauth</code>",
            parse_mode="HTML"
        )
        return

    extracted = extract_cards(raw_text)
    valid = []
    for c in extracted:
        cc, mm, yy, cvv = c.split('|')
        if luhn_check(cc) and not is_expired(mm, yy):
            valid.append(c)
        if len(valid) >= MAX_VALID_CARDS:
            break

    if not valid:
        await message.reply("❌ No valid cards to check.", parse_mode="HTML")
        return

    total = len(valid)
    current_credits = await asyncio.to_thread(get_user_credits, user_id)
    if current_credits < total:
        await message.reply(
            f"❌ <b>𝗜𝗻𝘀𝘂𝗳𝗳𝗶𝗰𝗶𝗲𝗻𝘁 𝗖𝗿𝗲𝗱𝗶𝘁𝘀</b>\n\n"
            f"You need <b>{total}</b> credits to check <b>{total}</b> cards.\n"
            f"Your balance: <b>{current_credits}</b> credits.",
            parse_mode="HTML"
        )
        return

    plan_name = "PREMIUM" if is_premium else "FREE"

    asyncio.create_task(run_batch_check(message, valid, check_cc, "𝐒𝐭𝐫𝐢𝐩𝐞 𝐀𝐮𝐭𝐡", user_id, user, "mauth", plan_name))

@router.callback_query(F.data.startswith("mauth_res_"))
async def mauth_result_handler(callback: types.CallbackQuery):
    await handle_result_callback(callback)


@router.callback_query(F.data.startswith("mauth_stop_"))
async def mauth_stop_handler(callback: types.CallbackQuery):
    await handle_stop_callback(callback)
