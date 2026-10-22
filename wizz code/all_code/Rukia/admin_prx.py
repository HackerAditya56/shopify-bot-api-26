import os
import asyncio
import logging
import io
from aiogram import Router, F, types
from aiogram.filters import Command
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, BufferedInputFile

from proxy import parse_proxy_input, check_proxies_parallel, MAX_CONCURRENT_CHECKS

router = Router()

# Admin IDs (must match the rest of the bot)
ADMIN_IDS = {8423281554}

# Premium Emoji IDs (provided by owner)
EMOJI_RED_TICK   = "6147565374289220368"
EMOJI_BLUE_TICK  = "5278628026416909103"
EMOJI_LIGHTNING  = "5350835008007324644"
EMOJI_STAR       = "5359686514697576863"
EMOJI_FIRE       = "6186076099764555777"
EMOJI_CROWN      = "6338940587193930733"
EMOJI_EPIC       = "5310296284874159738"
EMOJI_DRAGON     = "5226578782340553954"
EMOJI_GUN        = "5440406404936524730"
EMOJI_WHITE_STAR = "5247131412032670246"

# Global proxy pool file (host:port:user:pass format, one per line)
PROXIES_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "proxies.txt")
MAX_FILE_SIZE = 5 * 1024 * 1024  # 5 MB cap for uploaded .txt files

_SEP = "━━━━━━━━━━━━━━━━"


def _read_pool() -> list:
    """Read all proxy lines from proxies.txt (deduped, stripped, non-empty)."""
    try:
        if not os.path.exists(PROXIES_FILE):
            return []
        with open(PROXIES_FILE, "r", encoding="utf-8", errors="ignore") as f:
            seen = set()
            out = []
            for line in f:
                p = line.strip()
                if p and p not in seen:
                    seen.add(p)
                    out.append(p)
            return out
    except Exception as e:
        logging.error(f"[prx] read_pool: {e}")
        return []


def _write_pool(proxies: list) -> int:
    """Overwrite proxies.txt with the given list. Returns count written."""
    try:
        with open(PROXIES_FILE, "w", encoding="utf-8") as f:
            for p in proxies:
                f.write(p.strip() + "\n")
        return len(proxies)
    except Exception as e:
        logging.error(f"[prx] write_pool: {e}")
        return 0


def _to_pool_format(proxy_data: dict) -> str:
    """Convert parsed proxy dict back to host:port:user:pass line format."""
    return f"{proxy_data['ip']}:{proxy_data['port']}:{proxy_data['user']}:{proxy_data['password']}"


async def _gather_input_proxies(message: types.Message) -> list:
    """Extract proxy strings from /prx command text, reply, or .txt document."""
    raw_text = ""
    parts = message.text.split(maxsplit=1)
    if len(parts) > 1:
        raw_text += parts[1].strip() + "\n"
    if message.reply_to_message:
        if message.reply_to_message.text:
            raw_text += message.reply_to_message.text + "\n"
        if message.reply_to_message.caption:
            raw_text += message.reply_to_message.caption + "\n"

    document = message.document
    if document:
        if document.file_size > MAX_FILE_SIZE:
            await message.reply(
                f'<tg-emoji emoji-id="{EMOJI_RED_TICK}">❌</tg-emoji> '
                f"<b>File too large.</b> Max 5 MB.",
                parse_mode="HTML",
            )
            return []
        try:
            file = await message.bot.get_file(document.file_id)
            byte_content = await file.download_as_bytearray()
            raw_text += byte_content.decode("utf-8", errors="ignore")
        except Exception as e:
            await message.reply(
                f'<tg-emoji emoji-id="{EMOJI_RED_TICK}">❌</tg-emoji> '
                f"<b>Error reading file:</b> <code>{e}</code>",
                parse_mode="HTML",
            )
            return []

    if not raw_text.strip():
        return []

    lines = [ln.strip() for ln in raw_text.strip().splitlines() if ln.strip()]
    return lines


@router.message(Command("prx"))
async def prx_command(message: types.Message):
    """Admin-only proxy pool manager.

    Usage:
      /prx                     → check the existing pool, remove dead, keep live
      /prx <proxy list>        → check inline list, append live ones to pool
      /prx (reply to .txt)     → check proxies from replied text/document
    """
    user_id = message.from_user.id
    if user_id not in ADMIN_IDS:
        await message.reply(
            f'<tg-emoji emoji-id="{EMOJI_RED_TICK}">❌</tg-emoji> '
            f"<b>Access Denied.</b>\n\n"
            f"Admin only command.",
            parse_mode="HTML",
        )
        return

    crown = f'<tg-emoji emoji-id="{EMOJI_CROWN}">👑</tg-emoji>'
    lightning = f'<tg-emoji emoji-id="{EMOJI_LIGHTNING}">⚡</tg-emoji>'
    fire = f'<tg-emoji emoji-id="{EMOJI_FIRE}">🔥</tg-emoji>'
    red = f'<tg-emoji emoji-id="{EMOJI_RED_TICK}">❌</tg-emoji>'
    blue = f'<tg-emoji emoji-id="{EMOJI_BLUE_TICK}">✅</tg-emoji>'
    epic = f'<tg-emoji emoji-id="{EMOJI_EPIC}">✨</tg-emoji>'

    # ── Decide mode: pool check vs new proxies ──
    has_input = (
        (message.text and len(message.text.split(maxsplit=1)) > 1)
        or (message.reply_to_message and (
            message.reply_to_message.text
            or message.reply_to_message.caption
            or message.reply_to_message.document
        ))
        or message.document
    )

    if not has_input:
        # ── MODE 1: check current pool, remove dead ──
        pool = await asyncio.to_thread(_read_pool)
        if not pool:
            await message.reply(
                f"{crown} <b>PROXY POOL</b>\n{_SEP}\n"
                f"{red} <b>Pool is empty.</b>\n"
                f"Send <code>/prx ip:port:user:pass ...</code> or reply to a .txt file to add proxies.",
                parse_mode="HTML",
            )
            return

        # Parse every line; skip invalid ones
        parsed_list = []
        invalid_count = 0
        for raw in pool:
            data = parse_proxy_input(raw)
            if data:
                parsed_list.append(data)
            else:
                invalid_count += 1

        status_msg = await message.reply(
            f"{lightning} <b>Checking pool...</b>\n"
            f"{_SEP}\n"
            f"<b>Pool size ➛</b> <code>{len(pool)}</code>\n"
            f"<b>Testing {MAX_CONCURRENT_CHECKS} at a time...</b>",
            parse_mode="HTML",
        )

        async def _on_progress(done: int, total_count: int):
            try:
                if done == total_count or done % 10 == 0:
                    await status_msg.edit_text(
                        f"{lightning} <b>Checking pool...</b>\n"
                        f"{_SEP}\n"
                        f"<b>Progress ➛</b> <code>{done}/{total_count}</code>\n"
                        f"<b>Testing {MAX_CONCURRENT_CHECKS} at a time...</b>",
                        parse_mode="HTML",
                    )
            except Exception:
                pass

        results = await check_proxies_parallel(parsed_list, on_progress=_on_progress)
        live_data = [p for p, ok, _ in results if ok]
        dead_pairs = [(p, info) for p, ok, info in results if not ok]
        dead_data = [p for p, _ in dead_pairs]
        live_pool_lines = [_to_pool_format(p) for p in live_data]
        written = await asyncio.to_thread(_write_pool, live_pool_lines)

        # Build sample text (first few live + first few dead with reason)
        live_sample = "\n".join(f"  • <code>{_to_pool_format(p)}</code>" for p in live_data[:5])
        dead_sample_lines = []
        for p, info in dead_pairs[:5]:
            host = p.get("ip", "?")
            reason = (info or {}).get("error", "Dead")
            dead_sample_lines.append(f"  • <code>{host}</code> — {reason}")
        dead_sample = "\n".join(dead_sample_lines)

        text = (
            f"{crown} <b>POOL CHECK DONE</b>\n"
            f"{_SEP}\n"
            f"{fire} <b>Checked ➛</b> <code>{len(pool)}</code>\n"
            f"{blue} <b>Live kept ➛</b> <b>{len(live_data)}</b>\n"
            f"{red} <b>Dead removed ➛</b> <b>{len(dead_data)}</b>\n"
            f"<b>Invalid format ➛</b> <b>{invalid_count}</b>\n"
            f"{epic} <b>Pool now ➛</b> <b>{written}</b> proxies\n"
        )
        if live_sample and len(live_data) > 0:
            text += (
                f"{_SEP}\n"
                f"{blue} <b>Live sample:</b>\n{live_sample}\n"
            )
        if dead_sample and len(dead_pairs) > 0:
            more = f"\n  <i>... +{len(dead_pairs) - 5} more</i>" if len(dead_pairs) > 5 else ""
            text += (
                f"{red} <b>Dead sample:</b>\n{dead_sample}{more}\n"
            )
        text += (
            f"{_SEP}\n"
            f"{crown} <b><a href=\"https://t.me/ShopifyxoBot\">Rukia Shopify</a></b>"
        )
        try:
            await status_msg.edit_text(text, parse_mode="HTML", disable_web_page_preview=True)
        except Exception:
            await message.reply(text, parse_mode="HTML", disable_web_page_preview=True)
        return

    # ── MODE 2: check new proxies from input, add live ones to pool ──
    new_lines = await _gather_input_proxies(message)
    if not new_lines:
        await message.reply(
            f"{red} <b>No proxies found in input.</b>\n\n"
            f"Usage:\n"
            f"<code>/prx host:port:user:pass ...</code>\n"
            f"or reply to a .txt file with <code>/prx</code>.",
            parse_mode="HTML",
        )
        return

    parsed_list = []
    invalid_count = 0
    for raw in new_lines:
        data = parse_proxy_input(raw)
        if data:
            parsed_list.append(data)
        else:
            invalid_count += 1

    if not parsed_list:
        await message.reply(
            f"{red} <b>No valid proxy formats found.</b>\n"
            f"Invalid: <code>{invalid_count}</code>",
            parse_mode="HTML",
        )
        return

    status_msg = await message.reply(
        f"{lightning} <b>Checking new proxies...</b>\n"
        f"{_SEP}\n"
        f"<b>To test ➛</b> <code>{len(parsed_list)}</code>\n"
        f"<b>Invalid ➛</b> <code>{invalid_count}</code>\n"
        f"<b>Testing {MAX_CONCURRENT_CHECKS} at a time...</b>",
        parse_mode="HTML",
    )

    async def _on_progress_new(done: int, total_count: int):
        try:
            if done == total_count or done % 10 == 0:
                await status_msg.edit_text(
                    f"{lightning} <b>Checking new proxies...</b>\n"
                    f"{_SEP}\n"
                    f"<b>Progress ➛</b> <code>{done}/{total_count}</code>\n"
                    f"<b>Invalid ➛</b> <code>{invalid_count}</code>\n"
                    f"<b>Testing {MAX_CONCURRENT_CHECKS} at a time...</b>",
                    parse_mode="HTML",
                )
        except Exception:
            pass

    results = await check_proxies_parallel(parsed_list, on_progress=_on_progress_new)
    live_data = [p for p, ok, _ in results if ok]
    dead_pairs = [(p, info) for p, ok, info in results if not ok]
    dead_data = [p for p, _ in dead_pairs]

    # Merge with existing pool, dedup
    existing = await asyncio.to_thread(_read_pool)
    existing_set = set(existing)
    added_count = 0
    duplicate_count = 0
    merged = list(existing)
    for p in live_data:
        line = _to_pool_format(p)
        if line not in existing_set:
            merged.append(line)
            existing_set.add(line)
            added_count += 1
        else:
            duplicate_count += 1

    written = await asyncio.to_thread(_write_pool, merged)

    # Build a live-only .txt for the admin to download
    if live_data:
        buf = io.BytesIO()
        for p in live_data:
            buf.write((_to_pool_format(p) + "\n").encode("utf-8"))
        buf.seek(0)
        live_file = BufferedInputFile(
            file=buf.read(),
            filename=f"live_proxies_{len(live_data)}.txt",
        )
    else:
        live_file = None

    # Sample lines for the caption
    dead_sample_lines = []
    for p, info in dead_pairs[:3]:
        host = p.get("ip", "?")
        reason = (info or {}).get("error", "Dead")
        dead_sample_lines.append(f"  • <code>{host}</code> — {reason}")
    dead_sample = "\n".join(dead_sample_lines)

    text = (
        f"{crown} <b>PROXY ADD DONE</b>\n"
        f"{_SEP}\n"
        f"{fire} <b>Tested ➛</b> <code>{len(parsed_list)}</code>\n"
        f"{blue} <b>Live ➛</b> <b>{len(live_data)}</b>\n"
        f"{red} <b>Dead ➛</b> <b>{len(dead_data)}</b>\n"
        f"<b>Invalid format ➛</b> <b>{invalid_count}</b>\n"
        f"<b>Added ➛</b> <b>{added_count}</b> {epic}\n"
        f"<b>Duplicates ➛</b> <b>{duplicate_count}</b>\n"
        f"<b>Pool now ➛</b> <b>{written}</b> proxies\n"
    )
    if dead_sample and len(dead_pairs) > 0:
        more = f"\n  <i>... +{len(dead_pairs) - 3} more</i>" if len(dead_pairs) > 3 else ""
        text += f"{red} <b>Dead sample:</b>\n{dead_sample}{more}\n"
    text += (
        f"{_SEP}\n"
        f"{crown} <b><a href=\"https://t.me/ShopifyxoBot\">Rukia Shopify</a></b>"
    )

    try:
        await status_msg.delete()
    except Exception:
        pass

    if live_file:
        await message.reply_document(
            document=live_file,
            caption=text,
            parse_mode="HTML",
            reply_to_message_id=message.message_id,
        )
    else:
        await message.reply(text, parse_mode="HTML", disable_web_page_preview=True)
