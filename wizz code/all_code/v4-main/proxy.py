import re
import logging
import aiohttp
import asyncio
from urllib.parse import quote
from io import BytesIO

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# AIogram Imports
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
from aiogram import types, F, Router
from aiogram.types import BufferedInputFile

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# LOCAL IMPORTS
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
from database import (
    get_db_connection,
    add_global_proxy,
    clear_global_proxies,
    get_global_proxies,
    get_global_proxy_count,
    proxy_statistics,
)

# Router for this module
router = Router()

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# CONFIGURATION
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

OWNER_IDS           = {8462705169}
MAX_CONCURRENT_CHECKS = 5      # Parallel proxy-check limit
PROXY_TIMEOUT       = 8        # Timeout per proxy check (seconds)
IPIFY_API_URL       = "https://api.ipify.org?format=json"
MAX_FILE_SIZE       = 5 * 1024 * 1024  # 5 MB max file size


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# PARSING HELPERS  (unchanged — still needed for validation)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def parse_proxy_input(proxy_input):
    """
    Parses proxy input from ANY common format.
    Returns a dict with keys: user, password, ip, port,
    original_format, url_format, db_format, http_format.
    Returns None if the line cannot be parsed.
    """
    if not proxy_input or not proxy_input.strip():
        return None

    s = proxy_input.strip()
    protocol = 'http'

    # Remove BOM characters if present
    if s.startswith('\ufeff'):
        s = s[1:]

    protocol_match = re.match(r'^(?P<p>http|https|socks4|socks5)://', s, re.IGNORECASE)
    if protocol_match:
        protocol = protocol_match.group('p').lower()
        s = s[len(protocol_match.group('p')) + 3:]

    def is_valid(ip, port):
        if not ip or not port:
            return False
        ip_pattern = re.compile(r'^([a-zA-Z0-9\-\.]+)$')
        if not ip_pattern.match(ip):
            return False
        return port and port.isdigit() and 1 <= int(port) <= 65535

    # Pattern A: user:pass@ip:port
    match = re.match(r'^([^:@]+):([^:@]+)@([^:@]+):(\d+)$', s)
    if match:
        user, password, ip, port = match.groups()
        if is_valid(ip, port):
            return build_dict(user, password, ip, port, protocol, proxy_input)

    # Pattern B: user:pass ip:port
    match = re.match(r'^([^:@]+):([^:@]+)\s+([^:@]+):(\d+)$', s)
    if match:
        user, password, ip, port = match.groups()
        if is_valid(ip, port):
            return build_dict(user, password, ip, port, protocol, proxy_input)

    # Pattern C: ip:port user pass
    match = re.match(r'^([^:@]+):(\d+)\s+([^:@]+)\s+([^:@]+)$', s)
    if match:
        ip, port, user, password = match.groups()
        if is_valid(ip, port):
            return build_dict(user, password, ip, port, protocol, proxy_input)

    # Pattern D: user pass ip:port
    match = re.match(r'^([^:@]+)\s+([^:@]+)\s+([^:@]+):(\d+)$', s)
    if match:
        user, password, ip, port = match.groups()
        if is_valid(ip, port):
            return build_dict(user, password, ip, port, protocol, proxy_input)

    # Pattern E: user pass ip port
    match = re.match(r'^([^:@]+)\s+([^:@]+)\s+([^:@]+)\s+(\d+)$', s)
    if match:
        user, password, ip, port = match.groups()
        if is_valid(ip, port):
            return build_dict(user, password, ip, port, protocol, proxy_input)

    # Pattern F: user:pass:ip:port
    match = re.match(r'^([^:@]+):([^:@]+):([^:@]+):(\d+)$', s)
    if match:
        user, password, ip, port = match.groups()
        if is_valid(ip, port):
            return build_dict(user, password, ip, port, protocol, proxy_input)

    # Pattern G: ip:port:user:pass
    match = re.match(r'^([^:@]+):(\d+):([^:@]+):([^:@]+)$', s)
    if match:
        ip, port, user, password = match.groups()
        if is_valid(ip, port):
            return build_dict(user, password, ip, port, protocol, proxy_input)

    # Pattern H: ip:port (no auth)
    match = re.match(r'^([^:@]+):(\d+)$', s)
    if match:
        ip, port = match.groups()
        if is_valid(ip, port):
            return build_dict("", "", ip, port, protocol, proxy_input)

    return None


def build_dict(user, password, ip, port, protocol, original_input):
    encoded_user = quote(user, safe='') if user else ''
    encoded_pass = quote(password, safe='') if password else ''

    if user and password:
        url_format  = f"{protocol}://{encoded_user}:{encoded_pass}@{ip}:{port}"
        http_format = f"http://{user}:{password}@{ip}:{port}"
        db_format   = f"{user} {password} {ip} {port}"
    else:
        url_format  = f"{protocol}://{ip}:{port}"
        http_format = f"http://{ip}:{port}"
        db_format   = f"{ip} {port}"

    return {
        "user":            user,
        "password":        password,
        "ip":              ip,
        "port":            port,
        "original_format": original_input,
        "url_format":      url_format,
        "db_format":       db_format,
        "http_format":     http_format,
    }


async def check_proxy_live(proxy_url, session=None, timeout=PROXY_TIMEOUT):
    """
    Checks if a proxy is live by connecting to IPIFY.
    Returns: (is_alive: bool, info: dict)
    """
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
        'Accept':     'application/json',
    }
    client_timeout = aiohttp.ClientTimeout(total=timeout, connect=timeout / 2)

    close_session = False
    if session is None:
        session       = aiohttp.ClientSession(timeout=client_timeout, headers=headers)
        close_session = True

    try:
        async with session.get(IPIFY_API_URL, proxy=proxy_url, ssl=False) as resp:
            if resp.status == 200:
                try:
                    data = await resp.json()
                    ip   = data.get('ip')
                    if ip:
                        return True, {"ip": ip}
                    return False, {"error": "No IP in response"}
                except Exception:
                    text_data = await resp.text()
                    if text_data and text_data.strip():
                        return True, {"ip": text_data.strip()}
                    return False, {"error": "Empty response"}
            elif resp.status == 429:
                return False, {"error": "Rate limited"}
            else:
                return False, {"error": f"HTTP {resp.status}"}

    except asyncio.TimeoutError:
        return False, {"error": "Timeout"}
    except aiohttp.ClientProxyConnectionError:
        return False, {"error": "Connection failed"}
    except aiohttp.ClientConnectorError:
        return False, {"error": "DNS/Connection error"}
    except aiohttp.ClientError as e:
        return False, {"error": f"Client error: {str(e)[:50]}"}
    except Exception as e:
        return False, {"error": str(e)[:80]}
    finally:
        if close_session:
            await session.close()


async def check_proxies_parallel(proxies_list, max_concurrent=MAX_CONCURRENT_CHECKS):
    """Check multiple proxies in parallel with a semaphore cap."""
    if not proxies_list:
        return []

    semaphore = asyncio.Semaphore(max_concurrent)

    async def check_with_semaphore(proxy_data):
        async with semaphore:
            is_live, info = await check_proxy_live(proxy_data['url_format'])
            return (proxy_data, is_live, info)

    tasks   = [check_with_semaphore(p) for p in proxies_list]
    results = await asyncio.gather(*tasks, return_exceptions=True)

    processed = []
    for i, result in enumerate(results):
        if isinstance(result, Exception):
            processed.append((proxies_list[i], False, {"error": str(result)}))
        else:
            processed.append(result)

    return processed


async def run_db_operation(func, *args):
    """Run a synchronous DB function in a thread-pool executor."""
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, func, *args)


async def extract_proxies_from_input(message: types.Message):
    """
    Extract proxies from message text, reply, or attached file.
    Returns: (valid_proxies_list, total_lines_processed, error_message)
    """
    raw_text = ""

    # Command inline text
    if message.text:
        parts = message.text.split(maxsplit=1)
        if len(parts) > 1:
            raw_text += parts[1].strip() + "\n"

    # Replied message
    if message.reply_to_message:
        if message.reply_to_message.text:
            raw_text += message.reply_to_message.text + "\n"
        if message.reply_to_message.caption:
            raw_text += message.reply_to_message.caption + "\n"

    # Document / file
    document = message.document
    if not document and message.reply_to_message:
        document = message.reply_to_message.document

    if document:
        if document.file_size > MAX_FILE_SIZE:
            return None, 0, f"<b>❌ File too large. Max {MAX_FILE_SIZE // (1024 * 1024)} MB.</b>"

        file_ext = (document.file_name or "").rsplit('.', 1)[-1].lower()
        if file_ext not in ['txt', 'text', 'csv', 'proxy', 'list']:
            return None, 0, f"<b>⚠️ Unsupported file type: {file_ext}. Use .txt files only.</b>"

        try:
            file       = await message.bot.get_file(document.file_id)
            file_bytes = await message.bot.download_file(file.file_path)
            raw_text  += file_bytes.decode('utf-8', errors='ignore')
        except Exception as e:
            logging.error(f"File read error: {e}")
            return None, 0, f"<b>❌ Error reading file: {str(e)[:100]}</b>"

    if not raw_text.strip():
        return None, 0, "<b>⚠️ No proxy data found!</b>"

    lines         = raw_text.strip().split('\n')
    valid_proxies = []

    for line_num, line in enumerate(lines, 1):
        line = line.strip()
        if not line or line.startswith('#'):
            continue
        proxy_data = parse_proxy_input(line)
        if proxy_data:
            valid_proxies.append(proxy_data)
        else:
            logging.debug(f"Invalid proxy format at line {line_num}: {line[:50]}")

    return valid_proxies, len(lines), None


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# GLOBAL PROXY MANAGER  — singleton, in-memory cache
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class GlobalProxyManager:
    """
    Singleton that caches the global proxy pool in memory.
    Mass gates call get_all_proxies() to seed their per-session ProxyManager.
    Owner commands (gproxyadd / gproxyclear / gproxyreload) mutate the DB
    and call reload() to refresh the cache.
    """

    def __init__(self):
        self._proxies: list = []   # list of raw proxy strings (db_format)
        self._lock = asyncio.Lock()
        self._loaded: bool  = False

    async def reload(self):
        """Re-read all global proxies from the DB into the in-memory cache."""
        async with self._lock:
            try:
                proxies       = await asyncio.to_thread(get_global_proxies)
                self._proxies = proxies
                self._loaded  = True
                logging.info(f"[GlobalProxyManager] Reloaded {len(self._proxies)} proxies.")
            except Exception as e:
                logging.error(f"[GlobalProxyManager] Reload error: {e}")

    def get_all_proxies(self) -> list:
        """Return a snapshot copy of all cached proxy strings."""
        return list(self._proxies)

    def get_count(self) -> int:
        return len(self._proxies)

    def is_loaded(self) -> bool:
        return self._loaded

    def statistics(self) -> dict:
        return {
            "total":  len(self._proxies),
            "loaded": self._loaded,
        }


# Module-level singleton — import this from mass gates
global_proxy_manager = GlobalProxyManager()


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# OWNER-ONLY HELPER
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def _is_owner(user_id: int) -> bool:
    return user_id in OWNER_IDS


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# COMMAND: /gproxyadd  — add proxies to the global pool
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

@router.message(F.text.startswith("/proxy") & ~F.text.startswith("/proxyinfo") & ~F.text.startswith("/gproxyinfo"))
async def gproxyadd_command(message: types.Message):
    if not _is_owner(message.from_user.id):
        await message.reply("❌ Owner-only command.")
        return

    valid_proxies, total_lines, error_msg = await extract_proxies_from_input(message)

    if error_msg:
        await message.reply(error_msg, parse_mode="HTML")
        return

    if not valid_proxies:
        await message.reply(
            "<b>❌ No valid proxies found!</b>\n\n"
            "<i>Supported formats:\n"
            "• ip:port\n"
            "• user:pass@ip:port\n"
            "• user:pass ip:port\n"
            "• user:pass:ip:port</i>",
            parse_mode="HTML"
        )
        return

    # Progress message
    status_msg = await message.reply(
        f"⏳ <b>Checking {len(valid_proxies)} proxies...</b>\n"
        f"<i>Testing {min(MAX_CONCURRENT_CHECKS, len(valid_proxies))} at a time...</i>",
        parse_mode="HTML"
    )

    # Parallel liveness check
    results_list = await check_proxies_parallel(valid_proxies)

    live_proxies = [proxy_data for proxy_data, is_live, _ in results_list if is_live]
    dead_count   = len(valid_proxies) - len(live_proxies)

    # Save live proxies to DB
    added_count  = 0
    clone_count  = 0

    def _save_to_db():
        nonlocal added_count, clone_count
        _added = 0
        _clones = 0
        for pd in live_proxies:
            result = add_global_proxy(pd['db_format'])
            if result == 'added':
                _added += 1
            else:
                _clones += 1
        return _added, _clones

    try:
        added_count, clone_count = await asyncio.to_thread(_save_to_db)
    except Exception as e:
        logging.error(f"[gproxyadd] DB error: {e}")

    # Refresh in-memory cache
    await global_proxy_manager.reload()

    caption = (
        f"<b>✅ Done!</b>\n\n"
        f"<b>Total parsed ➠</b> <code>{len(valid_proxies)}</code>\n"
        f"<b>Live ➠</b> <b>{len(live_proxies)}</b> ✅\n"
        f"<b>Added ➠</b> <b>{added_count}</b> 💾\n"
        f"<b>Clones ➠</b> <b>{clone_count}</b> 🔁\n"
        f"<b>Dead ➠</b> <b>{dead_count}</b> ❌\n\n"
        f"<b>Global pool size ➠</b> <code>{global_proxy_manager.get_count()}</code>"
    )

    try:
        await status_msg.edit_text(caption, parse_mode="HTML")
    except Exception:
        await message.reply(caption, parse_mode="HTML")


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# COMMAND: /gproxyclear  — wipe the entire global pool
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

@router.message(F.text.startswith("/gproxyclear"))
async def gproxyclear_command(message: types.Message):
    if not _is_owner(message.from_user.id):
        await message.reply("❌ Owner-only command.")
        return

    try:
        deleted = await asyncio.to_thread(clear_global_proxies)
        await global_proxy_manager.reload()
        await message.reply(
            f"<b>✅ Global proxy pool cleared.</b>\n"
            f"<b>Deleted ➠</b> <code>{deleted}</code> proxies.",
            parse_mode="HTML"
        )
    except Exception as e:
        logging.error(f"[gproxyclear] Error: {e}")
        await message.reply("<b>❌ Error clearing global proxies.</b>", parse_mode="HTML")


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# COMMAND: /gproxyreload  — refresh in-memory cache from DB
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

@router.message(F.text.startswith("/gproxyreload"))
async def gproxyreload_command(message: types.Message):
    if not _is_owner(message.from_user.id):
        await message.reply("❌ Owner-only command.")
        return

    await global_proxy_manager.reload()
    await message.reply(
        f"<b>✅ Global proxy cache refreshed.</b>\n"
        f"<b>Pool size ➠</b> <code>{global_proxy_manager.get_count()}</code> proxies.",
        parse_mode="HTML"
    )


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# COMMAND: /gproxyinfo  — show global pool stats
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

@router.message(F.text.startswith("/gproxyinfo"))
async def gproxyinfo_command(message: types.Message):
    if not _is_owner(message.from_user.id):
        await message.reply("❌ Owner-only command.")
        return

    try:
        count = await asyncio.to_thread(get_global_proxy_count)
        stats = await asyncio.to_thread(proxy_statistics)
        cached = global_proxy_manager.get_count()

        msg = (
            f"<b>📊 Global Proxy Pool Info</b>\n\n"
            f"<b>DB count ➠</b> <code>{count}</code>\n"
            f"<b>Cached (in-memory) ➠</b> <code>{cached}</code>\n"
        )
        if stats:
            msg += (
                f"\n<b>DB Statistics:</b>\n"
                f"  Total: <code>{stats.get('total', 0)}</code>\n"
                f"  Active: <code>{stats.get('active', 0)}</code>\n"
                f"  On cooldown: <code>{stats.get('on_cooldown', 0)}</code>\n"
                f"  Avg fail count: <code>{stats.get('avg_fail_count', 0):.1f}</code>\n"
            )
        msg += f"\n<i>Use /gproxyreload to refresh the in-memory cache.</i>"

        await message.reply(msg, parse_mode="HTML")
    except Exception as e:
        logging.error(f"[gproxyinfo] Error: {e}")
        await message.reply("<b>❌ Error fetching proxy info.</b>", parse_mode="HTML")


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# COMMAND: /gproxyexport  — export global pool as .txt
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

@router.message(F.text.startswith("/checkproxy"))
async def gproxyexport_command(message: types.Message):
    if not _is_owner(message.from_user.id):
        await message.reply("❌ Owner-only command.")
        return

    proxies = global_proxy_manager.get_all_proxies()
    if not proxies:
        await message.reply("<b>📭 Global proxy pool is empty.</b>", parse_mode="HTML")
        return

    # Convert db_format strings back to http_format for live recheck
    proxy_data_list = []
    for p_str in proxies:
        parsed = parse_proxy_input(p_str)
        if parsed:
            proxy_data_list.append(parsed)
        else:
            proxy_data_list.append({
                "db_format": p_str,
                "http_format": p_str,
                "url_format": f"http://{p_str}",
                "original_format": "url_format",
            })

    # Recheck every proxy in the full global pool in parallel
    status_edit = await message.reply(
        f"⏳ <b>Rechecking {len(proxy_data_list)} global proxies...</b>",
        parse_mode="HTML"
    )
    results = await check_proxies_parallel(proxy_data_list)

    live_data = [proxy_data for proxy_data, is_live, _ in results if is_live]
    if not live_data:
        await status_edit.edit_text(
            "<b>❌ No live proxies found in the global pool.</b>",
            parse_mode="HTML"
        )
        return

    # Export valid proxies as a .txt file
    lines = [proxy_data['http_format'] for proxy_data in live_data]
    file_content = "\n".join(lines) + "\n"
    txt_file = BufferedInputFile(
        file=file_content.encode('utf-8'),
        filename=f"valid_proxies_{len(live_data)}.txt"
    )

    await message.reply_document(
        document=txt_file,
        caption=(
            f"<b>✅ Valid Global Proxies</b>\n"
            f"<b>Checked ➠</b> <code>{len(proxy_data_list)}</code>\n"
            f"<b>Live ➠</b> <code>{len(live_data)}</code> proxies"
        ),
        parse_mode="HTML"
    )


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# DEPRECATED USER PROXY COMMANDS  (owner-only notice)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

@router.message(F.text.startswith("/proxy") & ~F.text.startswith("/proxyinfo"))
async def proxy_command(message: types.Message):
    await message.reply(
        "ℹ️ <b>Per-user proxies are no longer supported.</b>\n\n"
        "The bot now uses a shared global proxy pool managed by the owner.\n"
        "You do not need to upload proxies to use mass gates.",
        parse_mode="HTML"
    )


@router.message(F.text.startswith("/checkproxy"))
async def checkproxy_command(message: types.Message):
    await message.reply(
        "ℹ️ <b>Per-user proxies are no longer supported.</b>\n\n"
        "The bot now uses a shared global proxy pool.",
        parse_mode="HTML"
    )


@router.message(F.text.startswith("/clearproxy"))
async def clearproxy_command(message: types.Message):
    await message.reply(
        "ℹ️ <b>Per-user proxies are no longer supported.</b>\n\n"
        "The bot now uses a shared global proxy pool.",
        parse_mode="HTML"
    )


@router.message(F.text.startswith("/myproxy"))
async def myproxy_command(message: types.Message):
    await message.reply(
        "ℹ️ <b>Per-user proxies are no longer supported.</b>\n\n"
        "The bot now uses a shared global proxy pool managed by the owner.",
        parse_mode="HTML"
    )
