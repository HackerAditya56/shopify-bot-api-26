import asyncio
import logging
import os

import requests
from aiogram import types, F, Router

from database import is_owner_user
from mass_gates._tg_helpers import safe_reply
from proxy import extract_proxies_from_input, parse_proxy_input
from bms_proxy_pool import load_bms_proxies, BMS_PROXY

router = Router()

BMS_PAGE = "https://in.bookmyshow.com/explore/home/patna"
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"

# premium emoji IDs
EMOJI_STAR    = "5321214486877609476"   # ⭐️
EMOJI_AXE     = "5323436380834016178"   # 🪓
EMOJI_TARGET  = "5323410860138343577"   # 🎯
EMOJI_BOW     = "5323400479202387128"   # 🏹
STAR   = f'<tg-emoji emoji-id="{EMOJI_STAR}">⭐️</tg-emoji>'
AXE    = f'<tg-emoji emoji-id="{EMOJI_AXE}">🪓</tg-emoji>'
TARGET = f'<tg-emoji emoji-id="{EMOJI_TARGET}">🎯</tg-emoji>'
BOW    = f'<tg-emoji emoji-id="{EMOJI_BOW}">🏹</tg-emoji>'


def _proxy_url(proxy: str):
    try:
        parsed = parse_proxy_input(proxy)
        if parsed and parsed.get("url_format"):
            return parsed["url_format"]
    except Exception:
        pass
    p = proxy.strip()
    return p if "://" in p else "http://" + p


def _bms_page_ok(proxy: str) -> tuple:
    """Test a proxy against the BMS page. Returns (ok, reason)."""
    url = _proxy_url(proxy)
    try:
        r = requests.get(BMS_PAGE, proxies={"http": url, "https": url},
                         headers={"User-Agent": UA, "Accept-Language": "en-US,en;q=0.9"},
                         timeout=20, allow_redirects=True)
        if r.status_code == 403:
            return False, "403 blocked"
        if r.status_code == 200:
            return True, "ok"
        return False, f"HTTP {r.status_code}"
    except Exception as e:
        return False, f"err {str(e)[:40]}"


@router.message(F.text.startswith("/addbms"))
async def addbms_command(message: types.Message):
    user_id = message.from_user.id
    if not await asyncio.to_thread(is_owner_user, user_id):
        await safe_reply(message, f"{TARGET} <b>𝐃𝐞𝐯 𝐎𝐧𝐥𝐲</b>", parse_mode="HTML")
        return

    valid, total, err = await extract_proxies_from_input(message)
    if err:
        await safe_reply(message, err, parse_mode="HTML")
        return
    if not valid:
        await safe_reply(message, f"{TARGET} <b>𝐍𝐨 𝐯𝐚𝐥𝐢𝐝 𝐩𝐫𝐨𝐱𝐢𝐞𝐬.</b>\n\nSend a file/reply with <code>/addbms</code>.", parse_mode="HTML")
        return

    proc = await safe_reply(message,
        f"<blockquote>{BOW} 𝐓𝐞𝐬𝐭𝐢𝐧𝐠 {len(valid)} 𝐩𝐫𝐨𝐱𝐢𝐞𝐬 𝐚𝐠𝐚𝐢𝐧𝐬𝐭 𝐁𝐌𝐒 {BOW}</blockquote>",
        parse_mode="HTML")

    existing = set(load_bms_proxies())
    added, skipped = [], []
    for p in valid:
        ok, reason = await asyncio.to_thread(_bms_page_ok, p)
        if ok and p not in existing:
            try:
                with open(BMS_PROXY, "a", encoding="utf-8") as f:
                    f.write(p + "\n")
                existing.add(p)
                added.append(p)
            except Exception:
                pass
        else:
            skipped.append((p, reason))

    lines = [
        f"<blockquote>{STAR} 𝐁𝐌𝐒 𝐏𝐫𝐨𝐱𝐲 𝐂𝐡𝐞𝐜𝐤 {STAR}</blockquote>",
        "━━━━━━━━━━━━━━━━━━━━━",
        f"{STAR} 𝐀𝐝𝐝𝐞𝐝 ➠ <b>{len(added)}</b>",
        f"{AXE} 𝐒𝐤𝐢𝐩𝐩𝐞𝐝 ➠ <b>{len(skipped)}</b>",
    ]
    for p in added[:5]:
        lines.append(f"  {STAR} <code>{p[:50]}</code>")
    if len(added) > 5:
        lines.append(f"  <i>…+{len(added)-5} more</i>")
    await proc.edit_text("\n".join(lines), parse_mode="HTML")
