"""gates/mpin.py - Magicpin card-check gate (button-controlled, premium-only emojis).

Flow:
  /mpin                 -> main menu (Login / Status / Buy / Brands)
  Login                 -> send phone -> send OTP (session persisted on API)
  Buy Card              -> pick brand -> pick amount -> pick qty -> send up to 10 cards
  -> sequential check (account-bound) -> per-card results

All emojis use PREMIUM custom-emoji IDs (icon_custom_emoji_id on buttons and
<tg-emoji emoji-id="..."> tags in text) - no hardcoded unicode emojis.
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
from mass_gates._batch_common import build_user_link
from mass_gates._tg_helpers import safe_reply

router = Router()

MP_API = os.environ.get("MP_API", "http://127.0.0.1:9100")

# ── PREMIUM EMOJI IDs (custom Telegram emojis - no hardcoded unicode) ──
ID_CHARGED = "5359719332542718652"    # 💎
ID_APPROVED = "6044254523009012231"   # ✅
ID_DECLINED = "5893081007153746175"   # ❌
ID_GATEWAY = "5085022089103016925"    # ⚡
ID_WALLET = "5424976816530014958"     # 👛
ID_STAR = "6136275172283391020"       # ⭐
ID_WARNING = "6255910249362885846"    # ⚠️
ID_BAT = "6136246765369694911"        # 🦇
ID_TOP = "5463071033256848094"        # 🔝
ID_FIRE = "5195224408683204554"       # 🔥
ID_SPARKLE = "5438098323871383999"    # ✨
ID_LOCK = "5258419835922030550"       # 🔐


def _tg(emoji_id: str, fallback: str) -> str:
    return f'<tg-emoji emoji-id="{emoji_id}">{fallback}</tg-emoji>'


BRANDS = {
    "1": "Amazon Pay",
    "2": "Google Play Recharge",
    "3": "Zomato",
    "4": "Blinkit",
    "5": "Uber",
    "6": "Myntra",
    "7": "Nykaa",
    "8": "BookMyShow",
    "9": "PVR Cinemas",
    "10": "MakeMyTrip",
}

def _amt_label(a):
    return f"₹{int(a)}" if float(a) == int(float(a)) else f"₹{float(a):g}"

_STATE = {}


def _in_wait(message: types.Message) -> bool:
    st = _STATE.get(message.from_user.id)
    return bool(st and str(st.get("step", "")).startswith("wait_"))


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


def _btn(text, data, style="primary", emoji=None):
    kw = {"text": text, "callback_data": data, "style": style}
    if emoji:
        kw["icon_custom_emoji_id"] = emoji
    return InlineKeyboardButton(**kw)


def _menu_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [_btn("𝗟𝗼𝗴𝗶𝗻", "mpin_login", "primary", ID_LOCK),
         _btn("𝗦𝘁𝗮𝘁𝘂𝘀", "mpin_status", "primary", ID_GATEWAY)],
        [_btn("𝗕𝘂𝘆 𝗖𝗮𝗿𝗱", "mpin_buy", "success", ID_CHARGED),
         _btn("𝗕𝗿𝗮𝗻𝗱𝘀", "mpin_brands", "primary", ID_STAR)],
        [_btn("« 𝗠𝗮𝗶𝗻 𝗠𝗲𝗻𝘂", "back_main", "primary")],
    ])


def _brand_keyboard() -> InlineKeyboardMarkup:
    rows = []
    keys = list(BRANDS.keys())
    for i in range(0, len(keys), 2):
        row = []
        for k in keys[i:i + 2]:
            row.append(_btn(BRANDS[k], f"mpin_brand_{k}", "primary"))
        rows.append(row)
    rows.append([_btn("« 𝗕𝗮𝗰𝗸", "mpin_menu", "primary")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def _amount_qty_keyboard(st) -> InlineKeyboardMarkup:
    # live in-stock amounts from the selected brand
    variants = st.get("variants") or []
    seen = set()
    amts = []
    for v in variants:
        if not v.get("in_stock", True):
            continue
        a = float(v.get("amount", 0) or 0)
        key = f"{a:.2f}"
        if key in seen or a <= 0:
            continue
        seen.add(key)
        amts.append(a)
    amts = sorted(amts)[:6]

    rows = []
    amt_row = [_btn("Auto", "mpin_amt_auto", "success" if st.get("amount") == "auto" else "primary")]
    for a in amts:
        key = f"{a:.2f}"
        style = "success" if st.get("amount") == key else "primary"
        amt_row.append(_btn(_amt_label(a), f"mpin_amt_{key}", style))
    rows.append(amt_row)
    qty_row = [_btn(str(n), f"mpin_qty_{n}", "success" if st.get("qty") == n else "primary") for n in range(1, 6)]
    rows.append(qty_row)
    rows.append([
        _btn("𝗦𝘁𝗮𝗿𝘁", "mpin_start", "success", ID_APPROVED),
        _btn("« 𝗕𝗮𝗰𝗸", "mpin_buy", "primary"),
    ])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def _mp_api(method, path, params=None, body=None):
    url = f"{MP_API}{path}"
    if params:
        url += "?" + urllib.parse.urlencode(params)
    try:
        if body is not None:
            req = urllib.request.Request(url, data=json.dumps(body).encode(),
                                         headers={"Content-Type": "application/json"}, method="POST")
        else:
            req = urllib.request.Request(url, method=method)
        resp = urllib.request.urlopen(req, timeout=240)
        return json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        try:
            return json.loads(e.read().decode())
        except Exception:
            return {"ok": False, "error": f"HTTP {e.code}"}
    except Exception as e:
        return {"ok": False, "error": str(e)[:120]}


def _mp_check(cc, brand_key, amount, qty):
    return _mp_api("GET", "/mp/check", {"cc": cc, "brand": brand_key, "amount": amount or "", "qty": str(qty or 1)})


def _mp_variants(brand_key):
    return _mp_api("GET", "/mp/variants", {"brand": brand_key})


def _mp_status():
    return _mp_api("GET", "/mp/status")


def _mp_login_send(phone):
    return _mp_api("POST", "/mp/login/send", body={"phone": phone})


def _mp_login_verify(phone, otp):
    return _mp_api("POST", "/mp/login/verify", body={"phone": phone, "otp": otp})


def _classify(resp_text):
    r = str(resp_text or "").lower()
    if any(x in r for x in ("success", "charged", "settled", "voucher", "paid", "approved", "completed")):
        return "charged"
    if any(x in r for x in ("3ds", "3-d", "3d ", "otp", "challenge")):
        return "three_d"
    if any(x in r for x in ("decline", "failure", "failed", "blocked", "insufficient",
                            "reject", "invalid", "expired", "limit", "frozen", "unavailable")):
        return "declined"
    return "error"


def _fmt_status(resp_text):
    key = _classify(resp_text)
    if key == "charged":
        return f'𝗖𝗛𝗔𝗥𝗚𝗘𝗗 {_tg(ID_CHARGED, "💎")}', "charged"
    if key == "three_d":
        return f'𝟯𝗗 {_tg(ID_LOCK, "🔐")}', "three_d"
    if key == "declined":
        return f'𝗗𝗘𝗖𝗟𝗜𝗡𝗘𝗗 {_tg(ID_DECLINED, "❌")}', "declined"
    return f'𝗘𝗥𝗥𝗢𝗥 {_tg(ID_WARNING, "⚠️")}', "error"


@router.message(F.text.startswith("/mpin") | F.caption.startswith("/mpin"))
async def mpin_command(message: types.Message):
    if not await asyncio.to_thread(is_gate_enabled, "mpin"):
        await safe_reply(message, f'{_tg(ID_WARNING, "🚧")} <b>𝗠𝗮𝗴𝗶𝗰𝗽𝗶𝗻 𝗚𝗮𝘁𝗲 𝘂𝗻𝗱𝗲𝗿 𝗺𝗮𝗶𝗻𝘁𝗲𝗻𝗮𝗻𝗰𝗲.</b>', parse_mode="HTML")
        return

    user = message.from_user
    user_id = user.id
    is_premium, _ = await asyncio.to_thread(get_premium_status, user_id)
    if not is_premium:
        await safe_reply(message, f'{_tg(ID_STAR, "💎")} 𝗣𝗹𝗲𝗮𝘀𝗲 𝘂𝗽𝗴𝗿𝗮𝗱𝗲 𝘆𝗼𝘂𝗿 𝗽𝗹𝗮𝗻 𝘁𝗼 𝘂𝘀𝗲 𝘁𝗵𝗶𝘀 𝗳𝗲𝗮𝘁𝘂𝗿𝗲.\n\n𝗨𝘀𝗲 /plan 𝘁𝗼 𝘂𝗽𝗴𝗿𝗮𝗱𝗲.', parse_mode="HTML")
        return

    _STATE[user_id] = {"step": "menu", "qty": 1, "amount": "auto", "cards": [], "results": []}

    st = await asyncio.to_thread(_mp_status)
    authed = bool(st.get("authed")) if isinstance(st, dict) else False
    phone = st.get("phone", "—") if isinstance(st, dict) else "—"
    auth_line = f'{_tg(ID_APPROVED, "✅")} 𝗟𝗼𝗴𝗴𝗲𝗱 𝗶𝗻' if authed else f'{_tg(ID_DECLINED, "❌")} 𝗡𝗼𝘁 𝗹𝗼𝗴𝗴𝗲𝗱 𝗶𝗻'

    await safe_reply(message,
        f'{_tg(ID_STAR, "⭐")} <b>𝗠𝗔𝗚𝗜𝗖𝗣𝗜𝗡 𝗚𝗔𝗧𝗘</b>\n'
        f'━━━━━━━━━━━━━━━━\n'
        f'{auth_line}\n'
        f'{_tg(ID_CHARGED, "💎")} 𝗣𝗵𝗼𝗻𝗲 ➠ <code>{escape(str(phone))}</code>\n'
        f'━━━━━━━━━━━━━━━━\n'
        f'𝗕𝘂𝘆 𝗮 𝗿𝗲𝗮𝗹 𝘃𝗼𝘂𝗰𝗵𝗲𝗿 𝘁𝗼 𝗰𝗵𝗲𝗰𝗸 𝗮 𝗰𝗮𝗿𝗱 (𝗿𝗲𝗮𝗹 𝗰𝗵𝗮𝗿𝗴𝗲).',
        parse_mode="HTML", reply_markup=_menu_keyboard())


@router.callback_query(F.data.startswith("mpin_"))
async def mpin_callback_handler(callback: types.CallbackQuery):
    data = callback.data or ""
    user_id = callback.from_user.id
    st = _STATE.setdefault(user_id, {"step": "menu", "qty": 1, "amount": "auto", "cards": [], "results": []})

    await callback.answer()

    if data == "mpin_menu":
        st["step"] = "menu"
        s = await asyncio.to_thread(_mp_status)
        authed = bool(s.get("authed")) if isinstance(s, dict) else False
        auth_line = f'{_tg(ID_APPROVED, "✅")} 𝗟𝗼𝗴𝗴𝗲𝗱 𝗶𝗻' if authed else f'{_tg(ID_DECLINED, "❌")} 𝗡𝗼𝘁 𝗹𝗼𝗴𝗴𝗲𝗱 𝗶𝗻'
        await callback.message.edit_text(
            f'{_tg(ID_STAR, "⭐")} <b>𝗠𝗔𝗚𝗜𝗖𝗣𝗜𝗡 𝗚𝗔𝗧𝗘</b>\n━━━━━━━━━━━━━━━━\n{auth_line}',
            parse_mode="HTML", reply_markup=_menu_keyboard())
        return

    if data == "mpin_login":
        st["step"] = "wait_phone"
        await callback.message.edit_text(
            f'{_tg(ID_LOCK, "🔐")} <b>𝗟𝗼𝗴𝗶𝗻</b>\n\n'
            f'𝗦𝗲𝗻𝗱 𝘆𝗼𝘂𝗿 𝟭𝟬-𝗱𝗶𝗴𝗶𝘁 𝗽𝗵𝗼𝗻𝗲 𝗻𝘂𝗺𝗯𝗲𝗿:',
            parse_mode="HTML")
        return

    if data == "mpin_status":
        s = await asyncio.to_thread(_mp_status)
        authed = bool(s.get("authed")) if isinstance(s, dict) else False
        phone = s.get("phone", "—") if isinstance(s, dict) else "—"
        uid = s.get("user_id", "—") if isinstance(s, dict) else "—"
        auth = f'{_tg(ID_APPROVED, "✅")} 𝗟𝗼𝗴𝗴𝗲𝗱 𝗶𝗻' if authed else f'{_tg(ID_DECLINED, "❌")} 𝗡𝗼𝘁 𝗹𝗼𝗴𝗴𝗲𝗱 𝗶𝗻'
        await callback.message.edit_text(
            f'{_tg(ID_GATEWAY, "📊")} <b>𝗦𝗲𝘀𝘀𝗶𝗼𝗻 𝗦𝘁𝗮𝘁𝘂𝘀</b>\n━━━━━━━━━━━━━━━━\n'
            f'{auth}\n'
            f'𝗣𝗵𝗼𝗻𝗲 ➠ <code>{escape(str(phone))}</code>\n'
            f'𝗨𝘀𝗲𝗿 𝗜𝗗 ➠ <code>{escape(str(uid))}</code>',
            parse_mode="HTML", reply_markup=InlineKeyboardMarkup(inline_keyboard=[[_btn("« 𝗕𝗮𝗰𝗸", "mpin_menu", "primary")]]))
        return

    if data == "mpin_brands":
        lines = "\n".join(BRANDS.values())
        await callback.message.edit_text(
            f'{_tg(ID_STAR, "🛒")} <b>𝗔𝘃𝗮𝗶𝗹𝗮𝗯𝗹𝗲 𝗕𝗿𝗮𝗻𝗱𝘀</b>\n━━━━━━━━━━━━━━━━\n{lines}',
            parse_mode="HTML", reply_markup=InlineKeyboardMarkup(inline_keyboard=[[_btn("« 𝗕𝗮𝗰𝗸", "mpin_menu", "primary")]]))
        return

    if data == "mpin_buy":
        st["step"] = "buy"
        await callback.message.edit_text(
            f'{_tg(ID_STAR, "⭐")} <b>𝗣𝗶𝗰𝗸 𝗮 𝗯𝗿𝗮𝗻𝗱</b>',
            parse_mode="HTML", reply_markup=_brand_keyboard())
        return

    if data.startswith("mpin_brand_"):
        key = data[len("mpin_brand_"):]
        if key in BRANDS:
            st["brand_key"] = key
            st["brand_name"] = BRANDS[key]
            st["amount"] = "auto"
        # fetch the LIVE voucher variants so amount buttons are real
        await callback.message.edit_text(
            f'{_tg(ID_GATEWAY, "⏳")} <b>𝗟𝗼𝗮𝗱𝗶𝗻𝗴 𝘃𝗮𝗿𝗶𝗮𝗻𝘁𝘀...</b>',
            parse_mode="HTML")
        v = await asyncio.to_thread(_mp_variants, key)
        st["variants"] = v.get("variants", []) if isinstance(v, dict) else []
        await callback.message.edit_text(
            f'{_tg(ID_WALLET, "👛")} <b>𝗦𝗲𝗹𝗲𝗰𝘁 𝗮𝗺𝗼𝘂𝗻𝘁 & 𝗾𝘁𝘆</b>\n\n'
            f'{_tg(ID_STAR, "⭐")} 𝗕𝗿𝗮𝗻𝗱 ➠ <b>{escape(st.get("brand_name", "?"))}</b>\n'
            f'{_tg(ID_WALLET, "👛")} 𝗔𝗺𝗼𝘂𝗻𝘁 ➠ <b>{st.get("amount", "auto")}</b>\n'
            f'{_tg(ID_LOCK, "🔢")} 𝗤𝘁𝘆 ➠ <b>{st.get("qty", 1)}</b>',
            parse_mode="HTML", reply_markup=_amount_qty_keyboard(st))
        return

    if data.startswith("mpin_amt_"):
        st["amount"] = data[len("mpin_amt_"):]
        await callback.message.edit_text(
            f'{_tg(ID_WALLET, "👛")} <b>𝗦𝗲𝗹𝗲𝗰𝘁 𝗮𝗺𝗼𝘂𝗻𝘁 & 𝗾𝘁𝘆</b>\n\n'
            f'𝗕𝗿𝗮𝗻𝗱 ➠ <b>{escape(st.get("brand_name", "?"))}</b>\n'
            f'𝗔𝗺𝗼𝘂𝗻𝘁 ➠ <b>{st.get("amount", "auto")}</b>\n'
            f'𝗤𝘁𝘆 ➠ <b>{st.get("qty", 1)}</b>',
            parse_mode="HTML", reply_markup=_amount_qty_keyboard(st))
        return

    if data.startswith("mpin_qty_"):
        st["qty"] = int(data[len("mpin_qty_"):])
        await callback.message.edit_text(
            f'{_tg(ID_WALLET, "👛")} <b>𝗦𝗲𝗹𝗲𝗰𝘁 𝗮𝗺𝗼𝘂𝗻𝘁 & 𝗾𝘁𝘆</b>\n\n'
            f'𝗕𝗿𝗮𝗻𝗱 ➠ <b>{escape(st.get("brand_name", "?"))}</b>\n'
            f'𝗔𝗺𝗼𝘂𝗻𝘁 ➠ <b>{st.get("amount", "auto")}</b>\n'
            f'𝗤𝘁𝘆 ➠ <b>{st.get("qty", 1)}</b>',
            parse_mode="HTML", reply_markup=_amount_qty_keyboard(st))
        return

    if data == "mpin_start":
        st["step"] = "wait_cards"
        st["cards"] = []
        await callback.message.edit_text(
            f'{_tg(ID_CHARGED, "💎")} <b>𝗦𝗲𝗻𝗱 𝗰𝗮𝗿𝗱𝘀 (𝗺𝗮𝘅 𝟭𝟬)</b>\n\n'
            f'𝗣𝗮𝘀𝘁𝗲 𝗰𝗮𝗿𝗱𝘀 𝗶𝗻 𝗳𝗼𝗿𝗺𝗮𝘁 <code>number|mm|yy|cvv</code>\n'
            f'𝗼𝗻𝗲 𝗽𝗲𝗿 𝗹𝗶𝗻𝗲, 𝘁𝗵𝗲𝗻 𝗱𝗼𝗻𝗲.',
            parse_mode="HTML")
        return


@router.message(F.text & ~F.text.startswith("/") & F.func(_in_wait))
async def mpin_input_handler(message: types.Message):
    user_id = message.from_user.id
    st = _STATE.get(user_id)
    if not st:
        return
    step = st.get("step")

    if step == "wait_phone":
        phone = message.text.strip().replace("+", "").replace(" ", "")
        if not phone.isdigit() or len(phone) not in (10, 12):
            await safe_reply(message, f'{_tg(ID_WARNING, "❌")} 𝗜𝗻𝘃𝗮𝗹𝗶𝗱 𝗽𝗵𝗼𝗻𝗲. 𝗦𝗲𝗻𝗱 𝗮 𝟭𝟬-𝗱𝗶𝗴𝗶𝘁 𝗻𝘂𝗺𝗯𝗲𝗿.', parse_mode="HTML")
            return
        await safe_reply(message, f'{_tg(ID_LOCK, "⏳")} 𝗦𝗲𝗻𝗱𝗶𝗻𝗴 𝗢𝗧𝗣...', parse_mode="HTML")
        await asyncio.to_thread(_mp_login_send, phone)
        st["phone"] = phone
        st["step"] = "wait_otp"
        await safe_reply(message,
            f'{_tg(ID_LOCK, "🔐")} <b>𝗢𝗧𝗣 𝗦𝗲𝗻𝘁</b>\n\n'
            f'𝗦𝗲𝗻𝗱 𝘁𝗵𝗲 𝗢𝗧𝗣 𝗰𝗼𝗱𝗲 𝗿𝗲𝗰𝗲𝗶𝘃𝗲𝗱 𝗼𝗻 {escape(phone)}.',
            parse_mode="HTML")
        return

    if step == "wait_otp":
        otp = message.text.strip()
        if not otp.isdigit() or len(otp) < 4:
            await safe_reply(message, f'{_tg(ID_WARNING, "❌")} 𝗜𝗻𝘃𝗮𝗹𝗶𝗱 𝗢𝗧𝗣.', parse_mode="HTML")
            return
        await safe_reply(message, f'{_tg(ID_LOCK, "⏳")} 𝗩𝗲𝗿𝗶𝗳𝘆𝗶𝗻𝗴...', parse_mode="HTML")
        r = await asyncio.to_thread(_mp_login_verify, st.get("phone", ""), otp)
        ok = bool(r.get("ok")) or bool(r.get("authed"))
        st["step"] = "menu"
        if ok:
            await safe_reply(message,
                f'{_tg(ID_APPROVED, "✅")} <b>𝗟𝗼𝗴𝗴𝗲𝗱 𝗶𝗻!</b>\n'
                f'𝗦𝗲𝘀𝘀𝗶𝗼𝗻 𝘀𝗮𝘃𝗲𝗱. 𝗬𝗼𝘂 𝗰𝗮𝗻 𝗻𝗼𝘄 /mpin 𝘁𝗼 𝗰𝗵𝗲𝗰𝗸 𝗰𝗮𝗿𝗱𝘀.',
                parse_mode="HTML")
        else:
            await safe_reply(message,
                f'{_tg(ID_DECLINED, "❌")} <b>𝗟𝗼𝗴𝗶𝗻 𝗳𝗮𝗶𝗹𝗲𝗱.</b>\n{escape(str(r.get("response") or r.get("error") or "unknown"))[:200]}',
                parse_mode="HTML")
        return

    if step == "wait_cards":
        raw = message.text or ""
        cards = re.findall(r'\b(\d{15,16})[|\s/?\\:]+(\d{1,2})[|\s/?\\:]+(\d{2,4})[|\s/?\\:]+(\d{3,4})\b', raw)
        if not cards:
            await safe_reply(message, f'{_tg(ID_WARNING, "❌")} 𝗡𝗼 𝘃𝗮𝗹𝗶𝗱 𝗰𝗮𝗿𝗱𝘀 𝗳𝗼𝘂𝗻𝗱.', parse_mode="HTML")
            return
        for cc, mm, yy, cvv in cards:
            yy2 = yy[2:] if len(yy) == 4 else yy
            st["cards"].append(f"{cc}|{mm}|{yy2}|{cvv}")
        st["cards"] = st["cards"][:10]
        if not luhn_check(st["cards"][0].split("|")[0]):
            await safe_reply(message, f'{_tg(ID_WARNING, "❌")} 𝗙𝗶𝗿𝘀𝘁 𝗰𝗮𝗿𝗱 𝗳𝗮𝗶𝗹𝗲𝗱 𝗟𝘂𝗵𝗻.', parse_mode="HTML")
            st["step"] = "menu"
            return
        await asyncio.create_task(_run_batch(message, st, user_id))
        return


async def _run_batch(message, st, user_id):
    brand_key = st.get("brand_key", "1")
    brand_name = st.get("brand_name", "Auto")
    amount = st.get("amount", "auto")
    qty = st.get("qty", 1)
    cards = st.get("cards", [])
    st["step"] = "menu"

    proc = await safe_reply(message,
        f'{_tg(ID_GATEWAY, "⏳")} <b>𝗖𝗵𝗲𝗰𝗸𝗶𝗻𝗴 {len(cards)} 𝗰𝗮𝗿𝗱(𝘀)...</b>\n'
        f'{_tg(ID_STAR, "⭐")} 𝗕𝗿𝗮𝗻𝗱 ➠ {escape(brand_name)} | 𝗤𝘁𝘆 ➠ {qty} | 𝗔𝗺𝗼𝘂𝗻𝘁 ➠ {escape(amount)}',
        parse_mode="HTML")

    # results: (card, status_key, status_disp, voucher, pin, resp, price)
    results = []
    charged_found = False
    for i, card in enumerate(cards, 1):
        try:
            await proc.edit_text(
                f'{_tg(ID_GATEWAY, "⏳")} <b>𝗖𝗵𝗲𝗰𝗸𝗶𝗻𝗴 {i}/{len(cards)}...</b>\n'
                f'{_tg(ID_CHARGED, "💎")} <code>{escape(card)}</code>',
                parse_mode="HTML")
        except Exception:
            pass
        r = await asyncio.to_thread(_mp_check, card, brand_key, amount, qty)
        if not isinstance(r, dict):
            results.append((card, "error", "𝗘𝗥𝗥𝗢𝗥", "", "", "no response", "—"))
            continue
        if r.get("error") == "LOGIN_REQUIRED":
            await proc.edit_text(f'{_tg(ID_WARNING, "⚠️")} <b>𝗟𝗼𝗴𝗶𝗻 𝗿𝗲𝗾𝘂𝗶𝗿𝗲𝗱.</b> 𝗟𝗼𝗴𝗶𝗻 𝗳𝗶𝗿𝘀𝘁 𝘃𝗶𝗮 /mpin → 𝗟𝗼𝗴𝗶𝗻.', parse_mode="HTML")
            return
        res = r.get("result") or {}
        resp = res.get("Response") or res.get("message") or r.get("error") or "UNKNOWN"
        status_disp, status_key = _fmt_status(resp)
        voucher = res.get("voucher_code", "")
        pin = res.get("voucher_pin", "")
        price = res.get("Price", "—")
        results.append((card, status_key, status_disp, voucher, pin, resp, price))
        if status_key == "charged":
            await asyncio.to_thread(update_user_stats, user_id, True)
            charged_found = True
            break  # STOP on charge — do not burn the remaining cards

    from collections import Counter
    counts = Counter(r[1] for r in results)

    # credits deduction (per card): charged 2, three_d 1, declined 1, error 0
    deduct = sum({"charged": 2, "three_d": 1, "declined": 1, "error": 0}.get(r[1], 0) for r in results)
    if deduct:
        await asyncio.to_thread(lambda: update_credits(user_id, max(0, get_user_credits(user_id) - deduct)))

    # ── Design 1: full per-card detail blocks ──
    blocks = []
    for r in results:
        card, key, disp, voucher, pin, resp, price = r
        bin_scheme = bin_bank = bin_country = "N/A"
        try:
            cc_num = card.split("|")[0]
            bi = await get_bin_info(cc_num[:6]) or {}
            bin_scheme = bi.get("scheme", "N/A")
            btype = bi.get("type", "")
            if btype:
                bin_scheme = f"{bin_scheme} · {btype}"
            bin_bank = bi.get("bank", "N/A")
            cname = bi.get("country", "N/A")
            cflag = bi.get("country_emoji", "")
            bin_country = f"{cflag} {cname}" if cflag else cname
        except Exception:
            pass
        vline = ""
        if voucher:
            vpin = f":{escape(str(pin))}" if pin else ""
            vline = f'\n{_tg(ID_SPARKLE, "🎁")} 𝗩𝗼𝘂𝗰𝗵𝗲𝗿 ➠ <code>{escape(str(voucher))}{vpin}</code>'
        block = (
            f'━━━━━━━━━━━━━━━━\n'
            f'{_tg(ID_CHARGED, "💎")} <code>{escape(card)}</code>\n'
            f'━━━━━━━━━━━━━━━━\n'
            f'𝗦𝘁𝗮𝘁𝘂𝘀 ➠ {disp}\n'
            f'{_tg(ID_GATEWAY, "⚡")} 𝗚𝗮𝘁𝗲𝘄𝗮𝘆 ➠ <b>𝗠𝗮𝗴𝗶𝗰𝗽𝗶𝗻</b>\n'
            f'{_tg(ID_STAR, "⭐")} 𝗕𝗿𝗮𝗻𝗱 ➠ <b>{escape(brand_name)}</b>\n'
            f'{_tg(ID_WALLET, "👛")} 𝗣𝗿𝗶𝗰𝗲 ➠ <b>{escape(str(price))}</b>\n'
            f'𝗥𝗲𝘀𝗽𝗼𝗻𝘀𝗲 ➠ <b>{escape(str(resp)[:120])}</b>\n'
            f'𝗕𝗜𝗡 ➠ <b>{bin_scheme}</b>\n'
            f'{_tg(ID_BAT, "🦇")} 𝗜𝘀𝘀𝘂𝗲𝗿 ➠ <b>{bin_bank}</b>\n'
            f'{_tg(ID_TOP, "🔝")} 𝗖𝗼𝘂𝗻𝘁𝗿𝘆 ➠ <b>{bin_country}</b>'
            f'{vline}'
        )
        blocks.append(block)

    body = "\n".join(blocks) if blocks else "𝗡𝗼 𝗿𝗲𝘀𝘂𝗹𝘁𝘀"
    stop_note = f'\n{_tg(ID_CHARGED, "💎")} <b>𝗖𝗵𝗮𝗿𝗴𝗲𝗱 — 𝘀𝘁𝗼𝗽𝗽𝗲𝗱, 𝗿𝗲𝗺𝗮𝗶𝗻𝗶𝗻𝗴 𝗰𝗮𝗿𝗱𝘀 𝘀𝗸𝗶𝗽𝗽𝗲𝗱</b>' if charged_found else ""

    await proc.edit_text(
        f'{_tg(ID_GATEWAY, "⚡")} <b>𝗠𝗮𝗴𝗶𝗰𝗽𝗶𝗻 𝗥𝗲𝘀𝘂𝗹𝘁</b>\n'
        f'{_tg(ID_CHARGED, "💎")} 𝗖𝗵𝗮𝗿𝗴𝗲𝗱 ➠ {counts.get("charged", 0)}   {_tg(ID_LOCK, "🔐")} 𝟯𝗗 ➠ {counts.get("three_d", 0)}\n'
        f'{_tg(ID_DECLINED, "❌")} 𝗗𝗲𝗰𝗹𝗶𝗻𝗲𝗱 ➠ {counts.get("declined", 0)}   {_tg(ID_WARNING, "⚠️")} 𝗘𝗿𝗿𝗼𝗿 ➠ {counts.get("error", 0)}\n'
        f'{body}'
        f'{stop_note}',
        parse_mode="HTML", disable_web_page_preview=True)
