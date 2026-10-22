import asyncio
import logging
import os
import re
import subprocess

import requests
from aiogram import types, F, Router
from aiogram.exceptions import TelegramRetryAfter

from database import is_owner_user
from mass_gates._tg_helpers import safe_reply
from bms_proxy_pool import load_bms_proxies, BMS_PROXY

router = Router()

BMS_PAGE = "https://in.bookmyshow.com/explore/home/patna"
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"

# premium emoji IDs
EMOJI_STAR    = "6136275172283391020"   # ⭐️
EMOJI_AXE     = "5323436380834016178"   # 🪓
EMOJI_TARGET  = "5323410860138343577"   # 🎯
EMOJI_BOW     = "5323400479202387128"   # 🏹
STAR   = f'<tg-emoji emoji-id="{EMOJI_STAR}">⭐️</tg-emoji>'
AXE    = f'<tg-emoji emoji-id="{EMOJI_AXE}">🪓</tg-emoji>'
TARGET = f'<tg-emoji emoji-id="{EMOJI_TARGET}">🎯</tg-emoji>'
BOW    = f'<tg-emoji emoji-id="{EMOJI_BOW}">🏹</tg-emoji>'


def _proxy_url(proxy):
    """Normalize ANY proxy format -> http://user:pass@host:port (BMS API format).

    Accepts: ip:port, user:pass@ip:port, user:pass:ip:port, ip:port:user:pass,
    host:port:user:pass, http://..., socks5://... etc."""
    raw = proxy.get("url_format") if isinstance(proxy, dict) else str(proxy)
    s = raw.strip().lstrip("\ufeff")
    if not s:
        return None
    # strip any scheme
    s = re.sub(r"^(http|https|socks4|socks5)://", "", s, flags=re.IGNORECASE)
    # user:pass@host:port
    if "@" in s:
        return "http://" + s
    parts = s.split(":")
    if len(parts) == 4:
        # host:port:user:pass  vs  user:pass:host:port — port is always numeric
        if parts[1].isdigit():
            host, port, user, pwd = parts
            return f"http://{user}:{pwd}@{host}:{port}"
        user, pwd, host, port = parts
        return f"http://{user}:{pwd}@{host}:{port}"
    if len(parts) == 2:
        # ip:port
        return f"http://{s}"
    if len(parts) == 3:
        # user:pass:port (rare) -> treat last as port, no host
        return None
    return None


async def _extract_raw_lines(message):
    """Pull every raw proxy line from text / reply / file — no format filtering,
    so mixed-format .txt files are handled line-by-line."""
    raw_text = ""
    cmd = message.text or message.caption or ""
    parts = cmd.split(maxsplit=1)
    if len(parts) > 1:
        raw_text += parts[1].strip() + "\n"
    if message.reply_to_message:
        rm = message.reply_to_message
        if rm.text:
            raw_text += rm.text + "\n"
        elif rm.caption:
            raw_text += rm.caption + "\n"
    document = message.document
    if not document and message.reply_to_message:
        document = message.reply_to_message.document
    if document:
        try:
            fi = await message.bot.get_file(document.file_id)
            data = await message.bot.download_file(fi.file_path)
            raw_text += data.read().decode("utf-8", errors="ignore") + "\n"
        except Exception as e:
            logging.warning(f"[addbms] file read failed: {e}")
    lines = []
    for line in raw_text.splitlines():
        line = line.strip().lstrip("\ufeff")
        if line and not line.startswith("#"):
            lines.append(line)
    return lines


def _bms_page_ok(proxy: str) -> tuple:
    """Test a proxy against BMS via headful Chrome (the only real verdict).

    A plain curl gets 403 from BMS even on a clean IP, so the check launches
    undetected Chrome through the proxy + waits for Cloudflare's cf_clearance
    cookie. BLOCKED retries once (a rotating proxy gets a fresh IP)."""
    url = _proxy_url(proxy)
    if not url:
        return False, "bad format"
    script = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "bms_test_proxy.py")
    for attempt in range(2):
        try:
            r = subprocess.run(
                ["xvfb-run", "-a", "python3", script, "--proxy", url],
                capture_output=True, text=True, timeout=110,
            )
            verdict = (r.stdout or "").strip().splitlines()
            last = verdict[-1].strip() if verdict else ""
            if last.startswith("OK"):
                return True, "ok"
            if last.startswith("BLOCKED"):
                continue   # rotating proxy -> next attempt hits a fresh IP
            return False, f"dead {last[:40]}"
        except Exception as e:
            return False, f"err {str(e)[:40]}"
    return False, "blocked"


@router.message(F.text.startswith("/addbms"))
async def addbms_command(message: types.Message):
    user_id = message.from_user.id
    if not await asyncio.to_thread(is_owner_user, user_id):
        await safe_reply(message, f"{TARGET} <b>𝐃𝐞𝐯 𝐎𝐧𝐥𝐲</b>", parse_mode="HTML")
        return

    raw_lines = await _extract_raw_lines(message)
    if not raw_lines:
        await safe_reply(message, f"{TARGET} <b>𝐍𝐨 𝐩𝐫𝐨𝐱𝐢𝐞𝐬 𝐟𝐨𝐮𝐧𝐝.</b>\n\nSend a file/reply with <code>/addbms</code>.", parse_mode="HTML")
        return

    proc = await safe_reply(message,
        f"<blockquote>{BOW} 𝐓𝐞𝐬𝐭𝐢𝐧𝐠 {len(raw_lines)} 𝐩𝐫𝐨𝐱𝐢𝐞𝐬 𝐚𝐠𝐚𝐢𝐧𝐬𝐭 𝐁𝐌𝐒 {BOW}</blockquote>",
        parse_mode="HTML")

    existing = set(load_bms_proxies())
    sem = asyncio.Semaphore(3)    # 3 concurrent headful-Chrome checks (heavy)

    async def _check_one(line):
        url = _proxy_url(line)
        if not url:
            return None, line, "bad format"
        async with sem:
            ok, reason = await asyncio.to_thread(_bms_page_ok, url)
        return (url if ok else None), url, reason

    try:
        results = await asyncio.wait_for(asyncio.gather(*(_check_one(line) for line in raw_lines)), timeout=120)
    except Exception as e:
        logging.error(f"[addbms] gather failed: {e}")
        await safe_reply(message, f"{TARGET} <b>𝐏𝐫𝐨𝐱𝐲 𝐜𝐡𝐞𝐜𝐤 𝐭𝐢𝐦𝐞𝐝 𝐨𝐮𝐭.</b>", parse_mode="HTML")
        return

    added, skipped = [], []
    for good_url, disp, reason in results:
        if good_url and good_url not in existing:
            existing.add(good_url)
            added.append(good_url)
        else:
            skipped.append((disp[:50], reason))

    if added:
        try:
            with open(BMS_PROXY, "a", encoding="utf-8") as f:
                for u in added:
                    f.write(u + "\n")
        except Exception:
            pass

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
    result_text = "\n".join(lines)

    # 1) edit the Testing msg in place (no new send -> no new FloodWait)
    for _ in range(3):
        try:
            await proc.edit_text(result_text, parse_mode="HTML", disable_web_page_preview=True)
            return
        except TelegramRetryAfter as e:
            if e.retry_after > 120:
                break
            await asyncio.sleep(e.retry_after + 1)
        except Exception as e:
            logging.warning(f"[addbms] edit failed: {e}")
            break
    # 2) fresh send (answer, not reply)
    for _ in range(3):
        try:
            await message.answer(result_text, parse_mode="HTML", disable_web_page_preview=True)
            return
        except TelegramRetryAfter as e:
            if e.retry_after > 120:
                break
            await asyncio.sleep(e.retry_after + 1)
        except Exception as e:
            logging.warning(f"[addbms] answer failed: {e}")
            break
    # 3) last resort — plain text, no HTML parse to fail on
    try:
        await message.answer(result_text)
    except Exception:
        pass
