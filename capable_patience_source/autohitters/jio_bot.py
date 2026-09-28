''' autohitters/jio_bot.py — /jio command: Jio Recharge Checker via local API (port 9090)
# The API itself (jio/api.py) runs as a SEPARATE service on :9090 — not started by the bot.
'''

import asyncio
import os
import random
import re
from html import escape as html_escape

from aiogram import types, F, Router
import aiohttp

from database import get_user_credits, update_credits, is_owner_user
from sub import get_premium_status

router = Router()

JIO_API = "http://127.0.0.1:9090/check"
JIO_BULK_API = "http://127.0.0.1:9090/check/bulk"
_SHOPIFY_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
PROXY_FILE = os.path.join(_SHOPIFY_DIR, "proxy.txt")

# Premium emoji IDs — ONLY these exist in the bot's emoji pack (no hardcoded emoji).
E_DIAMOND   = "5359719332542718652"   # 💎 charged
E_APPROVED  = "6044254523009012231"   # ✅ approved / live
E_DECLINED  = "5893081007153746175"   # ❌ declined
E_LIGHTNING = "5085022089103016925"   # ⚡ 3ds
E_BAT       = "6136246765369694911"   # 🦇 blocked
E_CLOCK     = "5258419835922030550"   # 🕔 expired / timeout
E_PURSE     = "5424976816530014958"   # 👛 price
E_CARD      = "4956719506027185156"   # 💎 card
E_STAR      = "6136275172283391020"   # ⭐ gateway / resp


def _tg(eid, text):
    return f'<tg-emoji emoji-id="{eid}">{text}</tg-emoji>'


# API category -> (status_key, emoji_id, fallback_emoji, label)
RESPONSE_MAP = {
    "charged":      ("CHARGED",       E_DIAMOND,   "💎", "𝐂𝐇𝐀𝐑𝐆𝐄𝐃"),
    "approved":     ("APPROVED",      E_APPROVED,  "✅", "𝐀𝐏𝐏𝐑𝐎𝐕𝐄𝐃"),
    "insufficient": ("INSUFFICIENT",  E_APPROVED,  "✅", "𝐈𝐍𝐒𝐔𝐅𝐅𝐈𝐂𝐈𝐄𝐍𝐓"),
    "declined":     ("DECLINED",      E_DECLINED,  "❌", "𝐃𝐄𝐂𝐋𝐈𝐍𝐄𝐃"),
    "expired":      ("EXPIRED",       E_CLOCK,     "🕔", "𝐄𝐗𝐏𝐈𝐑𝐄𝐃"),
    "cvv":          ("CVV",           E_DECLINED,  "❌", "𝐂𝐕𝐕"),
    "invalid":      ("INVALID",       E_DECLINED,  "❌", "𝐈𝐍𝐕𝐀𝐋𝐈𝐃"),
    "blocked":      ("BLOCKED",       E_BAT,       "🦇", "𝐁𝐋𝐎𝐂𝐊𝐄𝐃"),
    "3d":           ("3DS",           E_LIGHTNING, "⚡", "𝟑𝐃𝐒"),
    "3d_timeout":   ("3DS_TIMEOUT",   E_CLOCK,     "🕔", "𝟑𝐃𝐒 𝐓𝐈𝐌𝐄𝐎𝐔𝐓"),
    "cancelled":    ("CANCELLED",     E_DECLINED,  "❌", "𝐂𝐀𝐍𝐂𝐄𝐋𝐋𝐄𝐃"),
    "error":        ("ERROR",         E_DECLINED,  "❌", "𝐄𝐑𝐑𝐎𝐑"),
}

# results worth DM-ing individually (live-ish)
HIT_CATEGORIES = {"charged", "approved", "insufficient", "3d"}


def _load_proxies():
    try:
        with open(PROXY_FILE, encoding="utf-8", errors="ignore") as f:
            return [ln.strip() for ln in f if ln.strip() and not ln.strip().startswith("#")]
    except Exception:
        return []


async def _check_card(session, cc, number, proxy, amount):
    try:
        async with session.post(
            JIO_API,
            json={"cc": cc, "number": number, "proxy": proxy, "amount": amount},
            timeout=aiohttp.ClientTimeout(total=60),
        ) as resp:
            data = await resp.json()
        return data
    except Exception as e:
        return {
            "cc": cc, "response": "error", "real-response": f"{type(e).__name__}: {e}",
            "gateway": "none", "price": "-", "time": 0, "number": number,
        }


async def _check_bulk(session, number, cards, proxies, amount):
    """POST all cards to /check/bulk (parallel on the API side) and return (results, summary)."""
    payload = {
        "number": number,
        "cards": [{"cc": c, "proxy": proxies[i % len(proxies)], "amount": amount}
                  for i, c in enumerate(cards)],
    }
    try:
        async with session.post(JIO_BULK_API, json=payload,
                                timeout=aiohttp.ClientTimeout(total=3600)) as resp:
            data = await resp.json()
        return data.get("results", []), data.get("summary", {})
    except Exception as e:
        errs = [{"cc": c, "response": "error", "real-response": f"{type(e).__name__}: {e}",
                 "gateway": "none", "price": "-", "time": 0, "number": number} for c in cards]
        return errs, {}


def _format_result(res):
    cat = str(res.get("response", "error")).lower()
    _, eid, emoji, label = RESPONSE_MAP.get(cat, RESPONSE_MAP["error"])
    cc = res.get("cc", "")
    real = str(res.get("real-response", ""))[:80]
    gateway = res.get("gateway", "-")
    price = res.get("price", "-")
    parts = [
        f"{_tg(eid, emoji)} <b>{label}</b>",
        "━━━━━━━━━━━━━━━━━━━━━",
        f"{_tg(E_CARD, '💎')} <b>𝐂𝐚𝐫𝐝 ➠</b> <code>{html_escape(cc)}</code>",
        f"{_tg(E_PURSE, '👛')} <b>𝐏𝐫𝐢𝐜𝐞 ➠</b> {html_escape(price)}",
        f"{_tg(E_STAR, '⭐')} <b>𝐆𝐚𝐭𝐞𝐰𝐚𝐲 ➠</b> {html_escape(gateway)}",
        f"{_tg(E_STAR, '⭐')} <b>𝐑𝐞𝐬𝐩 ➠</b> {html_escape(real)}",
    ]
    return "\n".join(parts)


@router.message(F.text.startswith("/jio"))
async def jio_command(message: types.Message):
    user = message.from_user
    user_id = user.id

    is_premium, _ = await asyncio.to_thread(get_premium_status, user_id)
    if not is_premium and not is_owner_user(user_id):
        await message.reply(f"{_tg(E_DIAMOND, '💎')} <b>Premium only.</b> Use /plan to upgrade.", parse_mode="HTML")
        return

    args = message.text.split()[1:] if " " in message.text else []
    number = args[0].strip() if args else ""
    amount = args[1].strip() if len(args) > 1 else "19"

    raw_cards = []
    if message.reply_to_message:
        t = message.reply_to_message.text or message.reply_to_message.caption or ""
        raw_cards.extend(t.splitlines())
    # .txt file support (reply with a file, like /msh)
    document = message.document
    if not document and message.reply_to_message:
        document = message.reply_to_message.document
    if document:
        try:
            fi = await message.bot.get_file(document.file_id)
            data = await message.bot.download_file(fi.file_path)
            raw_cards.extend(data.read().decode("utf-8", errors="ignore").splitlines())
        except Exception as e:
            await message.reply(f"{_tg(E_DECLINED, '❌')} <b>Error reading file:</b> {html_escape(str(e))}", parse_mode="HTML")
            return
    if len(args) > 2:
        raw_cards.extend(args[2:])

    pat = re.compile(r'(\d{13,19})[\|/:\s]+(\d{1,2})[\|/:\s]+(\d{2,4})[\|/:\s]+(\d{3,4})')
    cards, seen = [], set()
    for item in raw_cards:
        for m in pat.finditer(item):
            cc, mm, yy, cvv = m.groups()
            if len(yy) == 2:
                yy = "20" + yy
            c = f"{cc}|{mm.zfill(2)}|{yy}|{cvv}"
            if c not in seen:
                seen.add(c)
                cards.append(c)

    if not re.fullmatch(r"\d{10}", number):
        await message.reply(
            f"{_tg(E_DECLINED, '❌')} <b>Usage:</b> <code>/jio &lt;number&gt; [amount]</code> + reply to cards or a .txt file.",
            parse_mode="HTML")
        return
    if not cards:
        await message.reply(f"{_tg(E_DECLINED, '❌')} <b>No cards found.</b>", parse_mode="HTML")
        return

    proxies = _load_proxies()
    if not proxies:
        await message.reply(f"{_tg(E_DECLINED, '❌')} <b>No proxies.</b>", parse_mode="HTML")
        return

    proc = await message.reply(
        f"{_tg(E_LIGHTNING, '⚡')} <b>Jio Recharge checking…</b> {len(cards)} card(s) → <code>{number}</code> ₹{amount}",
        parse_mode="HTML")

    async with aiohttp.ClientSession() as session:
        results, _summary = await _check_bulk(session, number, cards, proxies, amount)

        # DM live hits individually
        for r in results:
            cat = str(r.get("response", "error")).lower()
            if cat in HIT_CATEGORIES:
                try:
                    await message.reply(_format_result(r), parse_mode="HTML")
                except Exception:
                    pass

    counts = {}
    for r in results:
        k = str(r.get("response", "error")).lower()
        counts[k] = counts.get(k, 0) + 1
    summary = [f"{_tg(E_LIGHTNING, '⚡')} <b>Jio Recharge — Complete</b>", "━━━━━━━━━━━━━━━━━━━━━"]
    for k in RESPONSE_MAP:
        if k in counts:
            _, eid, emoji, label = RESPONSE_MAP[k]
            summary.append(f"{_tg(eid, emoji)} {label} ➠ {counts[k]}")
    summary.append("━━━━━━━━━━━━━━━━━━━━━")
    summary.append(f"{_tg(E_CARD, '💎')} <b>Total ➠</b> {len(results)}")
    try:
        await proc.edit_text("\n".join(summary), parse_mode="HTML")
    except Exception:
        pass
