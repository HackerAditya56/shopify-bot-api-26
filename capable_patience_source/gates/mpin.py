"""gates/mpin.py - Magicpin card-check gate (premium UI, button-controlled).

Flow:
  /mpin cc|mm|yy|cvv [amount=X]   -> brand-selection buttons
  pick a brand                    -> runs the check against the Magicpin API
                                    (:9100), one card at a time (account-bound)
"""
import asyncio
import logging
import os
import random
import re
import urllib.request
import urllib.parse
import json
from html import escape

from aiogram import types, F, Router
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

from database import is_gate_enabled, get_user_credits, update_credits, update_user_stats
from bin import get_bin_info
from sub import get_premium_status
from mass_gates._batch_common import (
    CUSTOM_CHARGED_EMOJI_ID,
    CUSTOM_APPROVED_EMOJI_ID,
    CUSTOM_DECLINED_EMOJI_ID,
    build_user_link,
)
from mass_gates._tg_helpers import safe_reply

router = Router()

MP_API = os.environ.get("MP_API", "http://127.0.0.1:9100")

EMOJI_GATEWAY = "5085022089103016925"
EMOJI_PRICE = "5424976816530014958"
EMOJI_BRAND = "6136275172283391020"
EMOJI_WARN = "6255910249362885846"
EMOJI_CARD = "4956719506027185156"

BRANDS = {
    "1": ("Amazon Pay", "\U0001F6D2"),
    "2": ("Google Play Recharge", "\U0001F3AE"),
    "3": ("Zomato", "\U0001F354"),
    "4": ("Blinkit", "\U0001F6CD"),
    "5": ("Uber", "\U0001F697"),
    "6": ("Myntra", "\U0001F457"),
    "7": ("Nykaa", "\U0001F484"),
    "8": ("BookMyShow", "\U0001F3AC"),
    "9": ("PVR Cinemas", "\U0001F3A5"),
    "10": ("MakeMyTrip", "\u2708"),
}

_PENDING = {}


def luhn_check(card_number: str) -> bool:
    card_number = str(card_number).strip()
    if not card_number.isdigit():
        return False
    total = 0
    rd = card_number[::-1]
    for i, ch in enumerate(rd):
        d = int(ch)
        if i % 2 == 1:
            d *= 2
            if d > 9:
                d -= 9
        total += d
    return total % 10 == 0


def _brand_keyboard(token: str) -> InlineKeyboardMarkup:
    rows = []
    keys = list(BRANDS.keys())
    for i in range(0, len(keys), 2):
        row = []
        for k in keys[i:i + 2]:
            name, em = BRANDS[k]
            row.append(InlineKeyboardButton(
                text=f"{em} {name}",
                callback_data=f"mpin_pick_{token}_{k}",
            ))
        rows.append(row)
    return InlineKeyboardMarkup(inline_keyboard=rows)


def _mp_api_check(cc: str, brand_key: str, amount: str | None) -> dict:
    q = urllib.parse.urlencode({"cc": cc, "brand": brand_key, "amount": amount or "", "qty": "1"})
    url = f"{MP_API}/mp/check?{q}"
    try:
        resp = urllib.request.urlopen(url, timeout=240)
        return json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        try:
            return json.loads(e.read().decode())
        except Exception:
            return {"ok": False, "error": f"HTTP {e.code}"}
    except Exception as e:
        return {"ok": False, "error": str(e)[:120]}


def _classify(response_text: str) -> str:
    r = str(response_text or "").lower()
    if any(x in r for x in ("success", "charged", "settled", "voucher", "paid", "approved", "completed")):
        return "charged"
    if any(x in r for x in ("3ds", "3-d", "3d ", "otp", "challenge")):
        return "three_d"
    if any(x in r for x in ("decline", "failure", "failed", "blocked", "insufficient",
                            "reject", "invalid", "expired", "limit", "frozen", "unavailable")):
        return "declined"
    return "error"


def _fmt_result(resp_text: str):
    key = _classify(resp_text)
    if key == "charged":
        return f'CHARGED <tg-emoji emoji-id="{CUSTOM_CHARGED_EMOJI_ID}">\U0001F48E</tg-emoji>', "charged"
    if key == "three_d":
        return f'3D <tg-emoji emoji-id="{CUSTOM_APPROVED_EMOJI_ID}">\U0001F510</tg-emoji>', "three_d"
    if key == "declined":
        return f'DECLINED <tg-emoji emoji-id="{CUSTOM_DECLINED_EMOJI_ID}">\u274C</tg-emoji>', "declined"
    return f'ERROR <tg-emoji emoji-id="{EMOJI_WARN}">\u26A0</tg-emoji>', "error"


@router.message(F.text.startswith("/mpin"))
async def mpin_command(message: types.Message):
    if not await asyncio.to_thread(is_gate_enabled, "mpin"):
        await safe_reply(message,
            f'<tg-emoji emoji-id="{EMOJI_WARN}">\U0001F6A7</tg-emoji> <b>Magicpin Gate under maintenance.</b>',
            parse_mode="HTML")
        return

    user = message.from_user
    user_id = user.id
    is_premium, _ = await asyncio.to_thread(get_premium_status, user_id)
    if not is_premium:
        await safe_reply(message,
            f'<tg-emoji emoji-id="{EMOJI_BRAND}">\U0001F48E</tg-emoji> Please upgrade your plan to use this feature.\n\nUse /plan to upgrade.',
            parse_mode="HTML")
        return

    raw_text = ""
    cmd_text = message.text or message.caption or ""
    parts = cmd_text.split(maxsplit=1)
    if len(parts) > 1:
        raw_text += parts[1].strip() + " "
    if message.reply_to_message:
        rm = message.reply_to_message
        raw_text += (rm.text or rm.caption or "") + " "

    if not raw_text.strip():
        await safe_reply(message,
            "Usage: /mpin cc|mm|yy|cvv [amount=X]  (or reply to a card with /mpin)",
            parse_mode="HTML")
        return

    amount = None
    amt_match = re.search(r'amount\s*=\s*(\d+)', raw_text, re.I)
    if amt_match:
        amount = amt_match.group(1)

    m = re.search(r'\b(\d{15,16})[|\s/?\\:]+(\d{1,2})[|\s/?\\:]+(\d{2,4})[|\s/?\\:]+(\d{3,4})\b', raw_text)
    if not m:
        await safe_reply(message, "Invalid Card Format. Provide 4242424242424242|05|27|123", parse_mode="HTML")
        return
    cc, mm, yy_raw, cvv = m.groups()
    if len(yy_raw) == 4:
        yy_raw = yy_raw[2:]
    formatted_cc = f"{cc}|{mm}|{yy_raw}|{cvv}"

    if not luhn_check(cc):
        await safe_reply(message, "Invalid Card (Luhn failed).", parse_mode="HTML")
        return

    current_credits = await asyncio.to_thread(get_user_credits, user_id)
    if current_credits is None or current_credits <= 0:
        await safe_reply(message, "Insufficient Credits!", parse_mode="HTML")
        return

    token = "".join(random.choices("ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789", k=8))
    _PENDING[token] = {"card": formatted_cc, "user_id": user_id, "user": user, "amount": amount}

    await safe_reply(message,
        f'<tg-emoji emoji-id="{EMOJI_BRAND}">\u2B50</tg-emoji> <b>Pick a brand</b>\n\n'
        f'<tg-emoji emoji-id="{EMOJI_CARD}">\U0001F4B3</tg-emoji> <b>Card</b> <code>{escape(formatted_cc)}</code>',
        parse_mode="HTML",
        reply_markup=_brand_keyboard(token))


@router.callback_query(F.data.startswith("mpin_"))
async def mpin_callback_handler(callback: types.CallbackQuery):
    data = callback.data or ""
    parts = data.split("_")
    if len(parts) < 3:
        await callback.answer("Expired.")
        return
    action, token = parts[1], parts[2]
    brand_key = parts[3] if len(parts) > 3 else None

    pend = _PENDING.get(token)
    if not pend:
        await callback.answer("Session expired. Run /mpin again.", show_alert=True)
        return

    await callback.answer()

    if action == "pick" and brand_key in BRANDS:
        brand_name, em = BRANDS[brand_key]
        await callback.message.edit_text(
            f'<tg-emoji emoji-id="{EMOJI_GATEWAY}">\u23F3</tg-emoji> <b>Checking...</b>\n\n'
            f'<tg-emoji emoji-id="{EMOJI_CARD}">\U0001F4B3</tg-emoji> <b>Card</b> <code>{escape(pend["card"])}</code>\n'
            f'<tg-emoji emoji-id="{EMOJI_BRAND}">\u2B50</tg-emoji> <b>Brand</b> {em} {brand_name}',
            parse_mode="HTML")
        asyncio.create_task(_run_check(callback, pend, brand_key, brand_name, em))
    elif action == "again":
        await callback.message.edit_text(
            f'<tg-emoji emoji-id="{EMOJI_BRAND}">\u2B50</tg-emoji> <b>Pick a brand</b>\n\n'
            f'<tg-emoji emoji-id="{EMOJI_CARD}">\U0001F4B3</tg-emoji> <b>Card</b> <code>{escape(pend["card"])}</code>',
            parse_mode="HTML",
            reply_markup=_brand_keyboard(token))


async def _run_check(callback, pend, brand_key, brand_name, em):
    user_id = pend["user_id"]
    user = pend["user"]
    card = pend["card"]
    amount = pend["amount"]

    result = await asyncio.to_thread(_mp_api_check, card, brand_key, amount)

    if not result.get("ok") and result.get("error") == "LOGIN_REQUIRED":
        await callback.message.edit_text(
            f'<tg-emoji emoji-id="{EMOJI_WARN}">\u26A0</tg-emoji> <b>Login required</b>\n\n'
            f'The Magicpin account is not logged in. Run login on the API then retry.',
            parse_mode="HTML")
        return

    if not result.get("ok"):
        await callback.message.edit_text(
            f'<tg-emoji emoji-id="{EMOJI_WARN}">\u26A0</tg-emoji> <b>Error</b>\n\n{escape(str(result.get("error") or "unknown"))}',
            parse_mode="HTML")
        return

    res = result.get("result") or {}
    resp_text = res.get("Response") or res.get("message") or "UNKNOWN"
    price = res.get("Price") or "0.00INR"
    final_status, status_key = _fmt_result(resp_text)

    deduct = {"charged": 2, "three_d": 1, "declined": 1, "error": 0}[status_key]
    if deduct:
        await asyncio.to_thread(lambda: update_credits(user_id, max(0, get_user_credits(user_id) - deduct)))
    await asyncio.to_thread(update_user_stats, user_id, status_key == "charged")

    bin_scheme = bin_bank = bin_country = "N/A"
    try:
        cc_num = card.split("|")[0]
        bin_info = await get_bin_info(cc_num[:6]) or {}
        bin_scheme = bin_info.get("scheme", "N/A")
        bin_bank = bin_info.get("bank", "N/A")
        cname = bin_info.get("country", "N/A")
        cflag = bin_info.get("country_emoji", "")
        bin_country = f"{cflag} {cname}" if cflag else cname
    except Exception:
        pass

    user_link = build_user_link(user)
    dev_link = '<a href="https://t.me/Enchanted_linux_0x">Enchanted_linux_0x</a>'

    voucher = ""
    if res.get("voucher_code"):
        voucher = f'\n<tg-emoji emoji-id="{EMOJI_BRAND}">\U0001F381</tg-emoji> <b>Voucher</b> <code>{escape(str(res.get("voucher_code")))}</code>'
        if res.get("voucher_pin"):
            voucher += f':{escape(str(res.get("voucher_pin")))}'

    caption = (
        f'Status {final_status}\n'
        f'<tg-emoji emoji-id="{EMOJI_CARD}">\U0001F4B3</tg-emoji> Card <code>{escape(card)}</code>\n'
        f'<tg-emoji emoji-id="{EMOJI_GATEWAY}">\u26A1</tg-emoji> Gateway Magicpin {em}\n'
        f'<tg-emoji emoji-id="{EMOJI_PRICE}">\U0001F45B</tg-emoji> Price <b>{escape(str(price))}</b>\n'
        f'<tg-emoji emoji-id="{EMOJI_BRAND}">\u2B50</tg-emoji> Brand <b>{escape(brand_name)}</b>\n'
        f'Response <b>{escape(str(resp_text)[:120])}</b>\n'
        f'Brand <b>{bin_scheme}</b>\n'
        f'Issuer <b>{bin_bank}</b>\n'
        f'Country <b>{bin_country}</b>'
        f'{voucher}\n'
        f'User {user_link}\n'
        f'Dev {dev_link}'
    )

    kb = InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="Check Again", callback_data=f"mpin_again_{token}", style="primary"),
        InlineKeyboardButton(text="Change Brand", callback_data=f"mpin_pick_{token}_1",
                             style="success", icon_custom_emoji_id=CUSTOM_APPROVED_EMOJI_ID),
    ]])

    try:
        await callback.message.edit_text(caption, parse_mode="HTML", reply_markup=kb, disable_web_page_preview=True)
    except Exception as e:
        logging.warning(f"mpin result edit failed: {e}")
