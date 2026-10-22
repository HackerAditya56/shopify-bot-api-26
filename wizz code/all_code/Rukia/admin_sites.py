import os
import asyncio
import time
import logging
import io
import re
from aiogram import Router, F, types, Bot
from aiogram.filters import Command
from aiogram.types import BufferedInputFile

from mass_gates.sitechk import (
    SITES_FILE,
    check_site_status,
    normalize_url,
    read_sites,
    write_sites,
)

# Regex to extract URLs from a line of text. Catches both bare URLs
# (one per line) AND result-log lines like:
#   "4688390703420295|07|29|674  [Shopify Payments]  CARD_DECLINED  $16.5 USD  | https://theconsciouscloset.myshopify.com"
# Stops at whitespace, pipe `|`, or end-of-line so trailing noise like
# "retry:1" or comments is excluded.
_URL_REGEX = re.compile(r'https?://[A-Za-z0-9._\-]+(?:/[^\s|]*)?', re.IGNORECASE)

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

MAX_FILE_SIZE = 5 * 1024 * 1024  # 5 MB cap for uploaded .txt files
MAX_CONCURRENT_SITE_CHECKS = 20  # higher = faster site audits
PROGRESS_BAR_LEN = 16
MIN_EDIT_INTERVAL = 0.3  # seconds (Telegram edit rate-limit guard)

_SEP = "━━━━━━━━━━━━━━━━"


def _is_admin(user_id: int) -> bool:
    return user_id in ADMIN_IDS


async def _gather_input_urls(message: types.Message) -> list:
    """Extract URLs from /addsites command text, reply, or .txt document.

    Accepts BOTH formats:
      1. Bare URLs (one per line):
            https://site1.myshopify.com
            https://site2.myshopify.com
      2. Result-log lines (e.g. from /msh exports), where the URL sits
         alongside card data:
            4688390703420295|07|29|674  [Shopify Payments]  CARD_DECLINED  $16.5 USD  | https://theconsciouscloset.myshopify.com

    For each line we run a regex that pulls out every http(s) URL it can
    find. Lines without a URL are silently ignored (they were probably
    blank lines, comments, or pure card data).
    """
    raw_text = ""
    parts = message.text.split(maxsplit=1)
    if len(parts) > 1:
        raw_text += parts[1].strip() + "\n"
    if message.reply_to_message:
        if message.reply_to_message.text:
            raw_text += message.reply_to_message.text + "\n"
        if message.reply_to_message.caption:
            raw_text += message.reply_to_message.caption + "\n"

    # Accept document from EITHER the command message itself OR the
    # message it is replying to (Telegram stores these in different
    # places depending on whether user attached the file or replied to it).
    document = message.document
    if not document and message.reply_to_message:
        document = message.reply_to_message.document
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
            buf = io.BytesIO()
            await message.bot.download_file(file.file_path, destination=buf)
            buf.seek(0)
            raw_text += buf.read().decode("utf-8", errors="ignore")
        except Exception as e:
            await message.reply(
                f'<tg-emoji emoji-id="{EMOJI_RED_TICK}">❌</tg-emoji> '
                f"<b>Error reading file:</b> <code>{e}</code>",
                parse_mode="HTML",
            )
            return []


    if not raw_text.strip():
        return []

    # Walk every line, regex out URLs. One log line may legitimately
    # contain a single URL, but be lenient — if a line has multiple,
    # take all of them (deduped later in addsites_command).
    urls = []
    seen = set()
    for ln in raw_text.splitlines():
        for match in _URL_REGEX.findall(ln):
            u = match.strip().rstrip('.,);]')
            if u and u not in seen:
                seen.add(u)
                urls.append(u)
    return urls


async def _check_with_progress(
    urls: list,
    status_msg: types.Message,
    header: str,
) -> list:
    """Run check_site_status in parallel, update status_msg with a live progress bar.

    Returns the results list in the SAME order as `urls`.
    Each element is the tuple (url, status, data, resp) from sitechk.check_site_status.
    """
    total = len(urls)
    sem = asyncio.Semaphore(MAX_CONCURRENT_SITE_CHECKS)

    async def run_one(idx: int, url: str):
        async with sem:
            try:
                return (idx, url, await check_site_status(url))
            except Exception:
                return (idx, url, (url, "ERROR", None, None))

    tasks = [asyncio.create_task(run_one(i, u)) for i, u in enumerate(urls)]

    indexed_results: list = [None] * total
    done = 0
    live = 0
    dead = 0
    errors = 0
    last_edit = 0.0

    async def render(force: bool = False):
        nonlocal last_edit
        now = time.monotonic()
        if not force and (now - last_edit) < MIN_EDIT_INTERVAL:
            return
        pct = int(100 * done / total) if total else 0
        filled = int(PROGRESS_BAR_LEN * done / total) if total else 0
        bar = "█" * filled + "░" * (PROGRESS_BAR_LEN - filled)
        blue = f'<tg-emoji emoji-id="{EMOJI_BLUE_TICK}">✅</tg-emoji>'
        red = f'<tg-emoji emoji-id="{EMOJI_RED_TICK}">❌</tg-emoji>'
        lightning = f'<tg-emoji emoji-id="{EMOJI_LIGHTNING}">⚡</tg-emoji>'
        text = (
            f"{lightning} <b>{header}</b>\n"
            f"{_SEP}\n"
            f"<b>Progress:</b> <code>[{bar}]</code> "
            f"<b>{done}/{total}</b> <i>({pct}%)</i>\n"
            f"{blue} <b>Live ➛</b> <b>{live}</b>   "
            f"{red} <b>Dead ➛</b> <b>{dead}</b>   "
            f"<b>Errors ➛</b> <b>{errors}</b>\n"
            f"{_SEP}\n"
            f"<i>Live updates...</i>"
        )
        try:
            await status_msg.edit_text(text, parse_mode="HTML")
            last_edit = now
        except Exception:
            pass

    await render(force=True)

    for fut in asyncio.as_completed(tasks):
        idx, url, res = await fut
        if isinstance(res, tuple) and len(res) >= 2:
            status = res[1]
        else:
            status = "ERROR"
        indexed_results[idx] = (url, status, res[2] if len(res) > 2 else None,
                                res[3] if len(res) > 3 else None)
        if status == "KEEP":
            live += 1
        elif status == "REMOVE":
            dead += 1
        else:
            errors += 1
        done += 1
        await render(force=(done == total))

    return indexed_results


async def _send_dead_sites_txt(
    message: types.Message,
    dead_lines: list,
    error_lines: list,
    dead_count: int,
    error_count: int,
) -> None:
    """Build and send a .txt file listing all dead/error sites together
    with the response from the test-card check.
    """
    buf = io.BytesIO()
    # Header explaining the columns
    buf.write(b"# Dead & Error Sites | Response (test card check)\n")
    buf.write(b"# Format: PREFIX: url | response_from_api\n")
    buf.write(b"#   DEAD:  -> failed validation / price / dead keyword\n")
    buf.write(b"#   ERROR: -> could not be checked (network/parse failure)\n\n")
    for line in dead_lines:
        buf.write((line + "\n").encode("utf-8"))
    for line in error_lines:
        buf.write((line + "\n").encode("utf-8"))
    buf.seek(0)
    total = dead_count + error_count
    dead_file = BufferedInputFile(
        file=buf.read(),
        filename=f"dead_sites_{total}.txt",
    )
    red = f'<tg-emoji emoji-id="{EMOJI_RED_TICK}">❌</tg-emoji>'
    try:
        await message.reply_document(
            document=dead_file,
            caption=(
                f"{red} <b>Dead & Error Sites</b>\n\n"
                f"<b>Dead:</b> <code>{dead_count}</code>   "
                f"<b>Errors:</b> <code>{error_count}</code>   "
                f"<b>Total:</b> <code>{total}</code>"
            ),
            parse_mode="HTML",
            reply_to_message_id=message.message_id,
        )
    except Exception as e:
        logging.exception(f"Failed to send dead_sites txt: {e}")


def _build_caption_report(
    total: int,
    working: int,
    dead: int,
    duplicates: int,
    errors: int,
    pool_after: int,
    mode_label: str,
) -> str:
    crown = f'<tg-emoji emoji-id="{EMOJI_CROWN}">👑</tg-emoji>'
    fire  = f'<tg-emoji emoji-id="{EMOJI_FIRE}">🔥</tg-emoji>'
    red   = f'<tg-emoji emoji-id="{EMOJI_RED_TICK}">❌</tg-emoji>'
    blue  = f'<tg-emoji emoji-id="{EMOJI_BLUE_TICK}">✅</tg-emoji>'
    epic  = f'<tg-emoji emoji-id="{EMOJI_EPIC}">✨</tg-emoji>'
    gun   = f'<tg-emoji emoji-id="{EMOJI_GUN}">🔫</tg-emoji>'

    return (
        f"{crown} <b>SITE {mode_label} DONE</b>\n"
        f"{_SEP}\n"
        f"{fire} <b>Tested ➛</b> <code>{total}</code>\n"
        f"{blue} <b>Working ➛</b> <b>{working}</b>\n"
        f"{red} <b>Dead ➛</b> <b>{dead}</b>\n"
        f"{gun} <b>Duplicates skipped ➛</b> <b>{duplicates}</b>\n"
        f"<b>Errors ➛</b> <b>{errors}</b>\n"
        f"{epic} <b>Pool now ➛</b> <b>{pool_after}</b> sites\n"
        f"{_SEP}\n"
        f"{crown} <b><a href=\"https://t.me/ShopifyxoBot\">Rukia Shopify</a></b>"
    )


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# /addsites — Add new sites (check via API+proxies, skip duplicates)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
@router.message(Command("addsites"))
async def addsites_command(message: types.Message):
    if not _is_admin(message.from_user.id):
        await message.reply(
            f'<tg-emoji emoji-id="{EMOJI_RED_TICK}">❌</tg-emoji> '
            f"<b>Access Denied.</b>\n\nAdmin only command.",
            parse_mode="HTML",
        )
        return

    urls = await _gather_input_urls(message)
    if not urls:
        await message.reply(
            f'<tg-emoji emoji-id="{EMOJI_RED_TICK}">❌</tg-emoji> '
            f"<b>No URLs found in input.</b>\n\n"
            f"Send <code>/addsites https://site1.myshopify.com https://site2.myshopify.com</code>\n"
            f"or reply to a .txt file with <code>/addsites</code>.",
            parse_mode="HTML",
        )
        return

    # Dedup against existing pool (normalized)
    existing_sites = await asyncio.to_thread(read_sites)
    existing_norm = {normalize_url(s) for s in existing_sites}

    # Dedup the input itself
    seen = set()
    unique_urls = []
    for u in urls:
        n = normalize_url(u)
        if n in seen:
            continue
        seen.add(n)
        unique_urls.append(u)

    duplicate_count = sum(1 for u in unique_urls if normalize_url(u) in existing_norm)
    new_urls = [u for u in unique_urls if normalize_url(u) not in existing_norm]

    if not new_urls:
        await message.reply(
            f'<tg-emoji emoji-id="{EMOJI_BLUE_TICK}">✅</tg-emoji> '
            f"<b>All {duplicate_count} URLs are already in sites.txt.</b>\n"
            f"Nothing to add.",
            parse_mode="HTML",
        )
        return

    lightning = f'<tg-emoji emoji-id="{EMOJI_LIGHTNING}">⚡</tg-emoji>'
    dragon = f'<tg-emoji emoji-id="{EMOJI_DRAGON}">🐉</tg-emoji>'
    status_msg = await message.reply(
        f"{lightning} <b>Checking new sites...</b>\n"
        f"{_SEP}\n"
        f"{dragon} <b>To test ➛</b> <code>{len(new_urls)}</code>\n"
        f"<b>Duplicates (skipped) ➛</b> <code>{duplicate_count}</code>\n"
        f"{_SEP}\n"
        f"<i>Initializing checker...</i>",
        parse_mode="HTML",
    )

    results = await _check_with_progress(
        new_urls,
        status_msg,
        header="CHECKING NEW SITES",
    )

    working_urls = []
    working_lines = []  # formatted lines: "url | price | response"
    dead_urls = []
    error_urls = []
    dead_lines = []      # formatted lines: "DEAD: url | response"
    error_lines = []     # formatted lines: "ERROR: url | response"
    for url, status, _data, resp in results:
        if status == "KEEP":
            working_urls.append(url)
            # resp already contains the price (e.g. "$16.50 | CARD_DECLINED")
            working_lines.append(f"{url} | {resp}")
        elif status == "REMOVE":
            dead_urls.append(url)
            dead_lines.append(f"DEAD: {url} | {resp}")
        else:
            error_urls.append(url)
            error_lines.append(f"ERROR: {url} | {resp}")

    # Append working sites to existing pool (preserve existing order)
    final_pool = list(existing_sites)
    for u in working_urls:
        nu = normalize_url(u)
        if nu not in {normalize_url(x) for x in final_pool}:
            final_pool.append(u)

    pool_after = await asyncio.to_thread(write_sites, final_pool)

    caption = _build_caption_report(
        total=len(new_urls),
        working=len(working_urls),
        dead=len(dead_urls),
        duplicates=duplicate_count,
        errors=len(error_urls),
        pool_after=pool_after,
        mode_label="ADD",
    )

    # Send .txt of working sites — formatted with price + response
    if working_urls:
        buf = io.BytesIO()
        # Header line for human readability
        buf.write(b"# Working Sites | Price | Response (test card check)\n")
        for line in working_lines:
            buf.write((line + "\n").encode("utf-8"))
        buf.seek(0)
        live_file = BufferedInputFile(
            file=buf.read(),
            filename=f"working_sites_{len(working_urls)}.txt",
        )
        try:
            await status_msg.delete()
        except Exception:
            pass
        await message.reply_document(
            document=live_file,
            caption=caption,
            parse_mode="HTML",
            reply_to_message_id=message.message_id,
        )
    else:
        try:
            await status_msg.edit_text(caption, parse_mode="HTML", disable_web_page_preview=True)
        except Exception:
            await message.reply(caption, parse_mode="HTML", disable_web_page_preview=True)

    # Send .txt of dead/error sites (admin requested — to review rejections)
    if dead_lines or error_lines:
        await _send_dead_sites_txt(
            message, dead_lines, error_lines,
            dead_count=len(dead_lines), error_count=len(error_lines),
        )


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# /checksite — Audit existing sites (keep working, remove dead)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
@router.message(Command("checksite"))
async def checksite_command(message: types.Message):
    if not _is_admin(message.from_user.id):
        await message.reply(
            f'<tg-emoji emoji-id="{EMOJI_RED_TICK}">❌</tg-emoji> '
            f"<b>Access Denied.</b>\n\nAdmin only command.",
            parse_mode="HTML",
        )
        return

    sites = await asyncio.to_thread(read_sites)
    if not sites:
        await message.reply(
            f'<tg-emoji emoji-id="{EMOJI_RED_TICK}">❌</tg-emoji> '
            f"<b>sites.txt is empty.</b>\n\n"
            f"Use <code>/addsites</code> to add new sites first.",
            parse_mode="HTML",
        )
        return

    lightning = f'<tg-emoji emoji-id="{EMOJI_LIGHTNING}">⚡</tg-emoji>'
    dragon = f'<tg-emoji emoji-id="{EMOJI_DRAGON}">🐉</tg-emoji>'
    status_msg = await message.reply(
        f"{lightning} <b>Auditing sites.txt...</b>\n"
        f"{_SEP}\n"
        f"{dragon} <b>Total ➛</b> <code>{len(sites)}</code>\n"
        f"{_SEP}\n"
        f"<i>Initializing checker...</i>",
        parse_mode="HTML",
    )

    results = await _check_with_progress(
        sites,
        status_msg,
        header="AUDITING SITES",
    )

    working_urls = []
    working_lines = []  # formatted lines: "url | price | response"
    dead_count = 0
    error_count = 0
    dead_lines = []      # formatted lines: "DEAD: url | response"
    error_lines = []     # formatted lines: "ERROR: url | response"
    for url, status, _data, resp in results:
        if status == "KEEP":
            working_urls.append(url)
            # resp already contains the price (e.g. "$16.50 | CARD_DECLINED")
            working_lines.append(f"{url} | {resp}")
        elif status == "REMOVE":
            dead_count += 1
            dead_lines.append(f"DEAD: {url} | {resp}")
        else:
            error_count += 1
            error_lines.append(f"ERROR: {url} | {resp}")

    pool_after = await asyncio.to_thread(write_sites, working_urls)

    caption = _build_caption_report(
        total=len(sites),
        working=len(working_urls),
        dead=dead_count,
        duplicates=0,
        errors=error_count,
        pool_after=pool_after,
        mode_label="AUDIT",
    )

    # Send .txt of working sites — formatted with price + response
    if working_urls:
        buf = io.BytesIO()
        # Header line for human readability
        buf.write(b"# Working Sites | Price | Response (test card check)\n")
        for line in working_lines:
            buf.write((line + "\n").encode("utf-8"))
        buf.seek(0)
        live_file = BufferedInputFile(
            file=buf.read(),
            filename=f"working_sites_{len(working_urls)}.txt",
        )
        try:
            await status_msg.delete()
        except Exception:
            pass
        await message.reply_document(
            document=live_file,
            caption=caption,
            parse_mode="HTML",
            reply_to_message_id=message.message_id,
        )
    else:
        try:
            await status_msg.edit_text(caption, parse_mode="HTML", disable_web_page_preview=True)
        except Exception:
            await message.reply(caption, parse_mode="HTML", disable_web_page_preview=True)

    # Send .txt of dead/error sites (admin requested — to review rejections)
    if dead_lines or error_lines:
        await _send_dead_sites_txt(
            message, dead_lines, error_lines,
            dead_count=dead_count, error_count=error_count,
        )
