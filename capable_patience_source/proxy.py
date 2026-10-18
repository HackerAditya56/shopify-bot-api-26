import re
import logging
import aiohttp
import asyncio
from urllib.parse import quote
from concurrent.futures import ThreadPoolExecutor
import io

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# AIogram Imports
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
from aiogram import types, F, Router
from aiogram.types import BufferedInputFile, InlineKeyboardMarkup

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# LOCAL IMPORTS
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
from database import get_db_connection
from mass_gates._tg_helpers import safe_reply

# Router for this module
router = Router()

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# CONFIGURATION
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
MAX_CONCURRENT_CHECKS = 200  # Parallel requests limit (/proxy checks 200 at a time)
PROXY_TIMEOUT = 8  # Timeout per proxy check (seconds)
IPIFY_API_URL = "https://api.ipify.org?format=json"  # Ipify API endpoint
MAX_FILE_SIZE = 5 * 1024 * 1024  # 5MB max file size

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Premium custom emoji IDs (no hardcoded unicode emojis)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
ID_APPROVED = "6044254523009012231"   # ✅
ID_DECLINED = "5893081007153746175"   # ❌
ID_CHARGED = "5359719332542718652"    # 💎
ID_WARNING = "6255910249362885846"    # ⚠️
ID_STAR = "6136275172283391020"       # ⭐
ID_GATEWAY = "5085022089103016925"    # ⚡
ID_FIRE = "5195224408683204554"       # 🔥
ID_SPARKLE = "5438098323871383999"    # ✨
ID_LOCK = "5258419835922030550"       # 🔐
ID_BAT = "6136246765369694911"        # 🦇
ID_TOP = "5463071033256848094"        # 🔝
ID_WALLET = "5424976816530014958"     # 👛


def _tg(emoji_id: str, fallback: str) -> str:
    return f'<tg-emoji emoji-id="{emoji_id}">{fallback}</tg-emoji>'


def _btn(text, data, style="primary", emoji=None):
    from aiogram.types import InlineKeyboardButton
    kw = {"text": text, "callback_data": data, "style": style}
    if emoji:
        kw["icon_custom_emoji_id"] = emoji
    return InlineKeyboardButton(**kw)

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# PARSING HELPERS
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def parse_proxy_input(proxy_input):
    """
    Parses proxy input from ANY common format.
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
        s = s[len(protocol_match.group('p'))+3:]

    def is_valid(ip, port):
        if not ip or not port:
            return False
        # Basic IP/hostname validation
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
    # URL encode special characters in username/password
    encoded_user = quote(user, safe='') if user else ''
    encoded_pass = quote(password, safe='') if password else ''
    
    # Build URL with auth if credentials exist
    if user and password:
        url_format = f"{protocol}://{encoded_user}:{encoded_pass}@{ip}:{port}"
        http_format = f"http://{user}:{password}@{ip}:{port}"
        db_format = f"{user} {password} {ip} {port}"
    else:
        url_format = f"{protocol}://{ip}:{port}"
        http_format = f"http://{ip}:{port}"
        db_format = f"{ip} {port}"
    
    return {
        "user": user,
        "password": password,
        "ip": ip,
        "port": port,
        "original_format": original_input,
        "url_format": url_format,
        "db_format": db_format,
        "http_format": http_format
    }


async def check_proxy_live(proxy_url, session=None, timeout=PROXY_TIMEOUT):
    """
    Checks if proxy is live using IPIFY API.
    Returns: (is_alive: bool, info: dict)
    """
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
        'Accept': 'application/json'
    }
    
    client_timeout = aiohttp.ClientTimeout(total=timeout, connect=timeout/2)
    
    # Use caller-provided session if given, else open (and fully close) our own.
    if session is not None:
        return await _check_with_session(session, proxy_url)

    try:
        async with aiohttp.ClientSession(timeout=client_timeout, headers=headers) as own_session:
            return await _check_with_session(own_session, proxy_url)
    except Exception:
        return False, {"error": "session error"}


async def _check_with_session(session, proxy_url):
    try:
        async with session.get(IPIFY_API_URL, proxy=proxy_url, ssl=False) as resp:
            if resp.status == 200:
                try:
                    data = await resp.json()
                    ip = data.get('ip')
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
    except aiohttp.ClientConnectorError as e:
        return False, {"error": "DNS/Connection error"}
    except aiohttp.ClientError as e:
        return False, {"error": f"Client error: {str(e)[:50]}"}
    except Exception as e:
        return False, {"error": str(e)[:80]}


async def check_proxies_parallel(proxies_list, max_concurrent=MAX_CONCURRENT_CHECKS):
    """
    Check multiple proxies in parallel with semaphore limiting.
    One shared aiohttp session for the whole batch — avoids creating/closing
    hundreds of per-check sessions (the source of 'Unclosed connection' warnings).
    """
    if not proxies_list:
        return []
        
    semaphore = asyncio.Semaphore(max_concurrent)
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
        'Accept': 'application/json'
    }
    timeout = aiohttp.ClientTimeout(total=PROXY_TIMEOUT, connect=PROXY_TIMEOUT/2)
    
    async def check_with_semaphore(proxy_data):
        async with semaphore:
            is_live, info = await check_proxy_live(proxy_data['url_format'], session=session)
            return (proxy_data, is_live, info)
    
    # Shared session: opened and closed exactly once via async with.
    async with aiohttp.ClientSession(timeout=timeout, headers=headers) as session:
        tasks = [check_with_semaphore(p) for p in proxies_list]
        results = await asyncio.gather(*tasks, return_exceptions=True)
    
    # Process results - handle any exceptions
    processed_results = []
    for i, result in enumerate(results):
        if isinstance(result, Exception):
            processed_results.append((proxies_list[i], False, {"error": str(result)}))
        else:
            processed_results.append(result)
    
    return processed_results


async def run_db_operation(func, *args):
    """Helper to run DB operations in thread pool"""
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, func, *args)


async def extract_proxies_from_input(message: types.Message):
    """
    Extract proxies from message text, reply, or attached file.
    Returns: (valid_proxies_list, total_lines_processed, error_message)
    """
    raw_text = ""
    
    # Extract from command text
    parts = message.text.split(maxsplit=1)
    if len(parts) > 1:
        raw_text += parts[1].strip() + "\n"
    
    # Extract from replied message text
    if message.reply_to_message:
        if message.reply_to_message.text:
            raw_text += message.reply_to_message.text + "\n"
        if message.reply_to_message.caption:
            raw_text += message.reply_to_message.caption + "\n"
    
    # Extract from document/file
    document = message.document
    if not document and message.reply_to_message:
        document = message.reply_to_message.document
    
    if document:
        # Check file size
        if document.file_size > MAX_FILE_SIZE:
            return None, 0, f'{_tg(ID_DECLINED, "❌")} <b>𝐅𝐢𝐥𝐞 𝐭𝐨𝐨 𝐥𝐚𝐫𝐠𝐞. 𝐌𝐚𝐱 {MAX_FILE_SIZE // (1024*1024)}𝐌𝐁.</b>'
        
        # Check file extension
        file_ext = document.file_name.split('.')[-1].lower() if document.file_name else ''
        if file_ext not in ['txt', 'text', 'csv', 'proxy', 'list']:
            return None, 0, f'{_tg(ID_WARNING, "⚠️")} <b>𝐔𝐧𝐬𝐮𝐩𝐩𝐨𝐫𝐭𝐞𝐝 𝐟𝐢𝐥𝐞 𝐭𝐲𝐩𝐞: {file_ext}\n𝐏𝐥𝐞𝐚𝐬𝐞 𝐮𝐬𝐞 .𝐭𝐱𝐭 𝐟𝐢𝐥𝐞𝐬 𝐨𝐧𝐥𝐲.</b>'
        
        try:
            file = await message.bot.get_file(document.file_id)
            data = await message.bot.download_file(file.file_path)
            # download_file returns BytesIO in aiogram 3 — read() then decode.
            content = data.read() if hasattr(data, 'read') else data
            raw_text += content.decode('utf-8', errors='ignore')
        except Exception as e:
            logging.error(f"File read error: {e}")
            return None, 0, f'{_tg(ID_DECLINED, "❌")} <b>𝐄𝐫𝐫𝐨𝐫 𝐫𝐞𝐚𝐝𝐢𝐧𝐠 𝐟𝐢𝐥𝐞: {str(e)[:100]}</b>'
    
    if not raw_text.strip():
        return None, 0, f'{_tg(ID_WARNING, "⚠️")} <b>𝐍𝐨 𝐩𝐫𝐨𝐱𝐲 𝐝𝐚𝐭𝐚 𝐟𝐨𝐮𝐧𝐝!</b>'
    
    # Parse all lines
    lines = raw_text.strip().split('\n')
    valid_proxies = []
    invalid_count = 0
    
    for line_num, line in enumerate(lines, 1):
        line = line.strip()
        if not line or line.startswith('#'):  # Skip empty lines and comments
            continue
        
        proxy_data = parse_proxy_input(line)
        if proxy_data:
            valid_proxies.append(proxy_data)
        else:
            invalid_count += 1
            logging.debug(f"Invalid proxy format at line {line_num}: {line[:50]}")
    
    return valid_proxies, len(lines), None


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# BACKGROUND TASKS (PARALLEL PROCESSING)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

async def process_proxies_background(bot, message: types.Message, valid_proxies: list, source_type="input"):
    """Process proxies in background - PARALLEL checking (5 at a time)"""
    user_id = message.from_user.id
    chat_id = message.chat.id
    total_count = len(valid_proxies)
    
    # Send initial status message
    status_msg = await safe_reply(message, 
        f'{_tg(ID_GATEWAY, "⚡")} <b>𝐏𝐫𝐨𝐜𝐞𝐬𝐬𝐢𝐧𝐠...</b>\n\n'
        f"<code>{total_count}</code> 𝐩𝐫𝐨𝐱𝐢𝐞𝐬 𝐭𝐨 𝐜𝐡𝐞𝐜𝐤\n"
        f"<b>𝐂𝐡𝐞𝐜𝐤𝐢𝐧𝐠</b> {min(MAX_CONCURRENT_CHECKS, total_count)} 𝐚𝐭 𝐚 𝐭𝐢𝐦𝐞...",
        parse_mode="HTML"
    )
    
    # ✅ PARALLEL CHECKING - Fast!
    results_list = await check_proxies_parallel(valid_proxies)
    
    # Count results
    live_count = sum(1 for _, is_live, _ in results_list if is_live)
    dead_count = total_count - live_count
    
    # Prepare proxies to save
    to_save = [proxy_data['db_format'] for proxy_data, is_live, _ in results_list if is_live]
    
    # Save to DB (skip clones)
    added_count = 0
    clone_count = 0
    if to_save:
        try:
            def save_to_db():
                conn = get_db_connection()
                cursor = conn.cursor()
                
                # Fetch existing proxies for this user to check clones
                cursor.execute("SELECT proxy FROM proxies WHERE user_id = %s", (user_id,))
                existing_proxies = {row[0] for row in cursor.fetchall()}
                
                added = 0
                clones = 0
                for p_str in to_save:
                    if p_str not in existing_proxies:
                        cursor.execute("INSERT INTO proxies (user_id, proxy) VALUES (%s, %s)", (user_id, p_str))
                        existing_proxies.add(p_str)
                        added += 1
                    else:
                        clones += 1
                
                conn.commit()
                conn.close()
                return added, clones
            
            added_count, clone_count = await run_db_operation(save_to_db)
        except Exception as e:
            logging.error(f"DB Error: {e}")

    # Build final response
    is_bulk = total_count > 1
    
    if is_bulk:
        caption = (
            f'{_tg(ID_APPROVED, "✅")} <b>𝐂𝐨𝐦𝐩𝐥𝐞𝐭𝐞!</b>\n\n'
            f'<b>𝐒𝐨𝐮𝐫𝐜𝐞:</b> {source_type}\n'
            f'<b>𝐓𝐨𝐭𝐚𝐥 ➠</b> <code>{total_count}</code>\n'
            f'{_tg(ID_APPROVED, "✅")} <b>𝐋𝐢𝐯𝐞 ➠</b> <b>{live_count}</b>\n'
            f'{_tg(ID_CHARGED, "💎")} <b>𝐀𝐝𝐝𝐞𝐝 ➠</b> <b>{added_count}</b>\n'
            f'{_tg(ID_STAR, "⭐")} <b>𝐂𝐥𝐨𝐧𝐞𝐬 ➠</b> <b>{clone_count}</b>\n'
            f'{_tg(ID_DECLINED, "❌")} <b>𝐃𝐞𝐚𝐝 ➠</b> <b>{dead_count}</b>'
        )
    else:
        # Single proxy result
        if results_list:
            proxy_data, is_live, info = results_list[0]
        else:
            proxy_data, is_live, info = valid_proxies[0], False, {}
        
        if is_live:
            ip = info.get("ip") or proxy_data['ip']
            if added_count > 0:
                caption = (
                    f'{_tg(ID_APPROVED, "✅")} <b>𝐒𝐮𝐜𝐜𝐞𝐬𝐬!</b>\n\n'
                    f'{_tg(ID_APPROVED, "✅")} <b>𝐒𝐭𝐚𝐭𝐮𝐬 ➠ 𝐋𝐢𝐯𝐞</b>\n'
                    f'<b>𝐈𝐏 ➠</b> <code>{ip}</code>\n\n'
                    f'{_tg(ID_CHARGED, "💎")} <b>𝐒𝐚𝐯𝐞𝐝 𝐭𝐨 𝐝𝐚𝐭𝐚𝐛𝐚𝐬𝐞</b>'
                )
            else:
                caption = (
                    f'{_tg(ID_WARNING, "⚠️")} <b>𝐖𝐚𝐫𝐧𝐢𝐧𝐠!</b>\n\n'
                    f'{_tg(ID_APPROVED, "✅")} <b>𝐒𝐭𝐚𝐭𝐮𝐬 ➠ 𝐋𝐢𝐯𝐞</b>\n'
                    f'<b>𝐈𝐏 ➠</b> <code>{ip}</code>\n\n'
                    f'{_tg(ID_STAR, "⭐")} <b>𝐀𝐥𝐫𝐞𝐚𝐝𝐲 𝐞𝐱𝐢𝐬𝐭𝐬 𝐢𝐧 𝐃𝐁</b>'
                )
        else:
            error_msg = info.get("error", "𝐔𝐧𝐤𝐧𝐨𝐰𝐧")
            caption = (
                f'{_tg(ID_DECLINED, "❌")} <b>𝐅𝐚𝐢𝐥𝐞𝐝!</b>\n\n'
                f'{_tg(ID_DECLINED, "❌")} <b>𝐒𝐭𝐚𝐭𝐮𝐬 ➠ 𝐃𝐞𝐚𝐝</b>\n'
                f'<b>𝐑𝐞𝐚𝐬𝐨𝐧 ➠</b> <code>{error_msg}</code>\n\n'
                f'{_tg(ID_DECLINED, "❌")} <b>𝐍𝐨𝐭 𝐚𝐝𝐝𝐞𝐝.</b>'
            )
    
    # Edit status message with final result
    try:
        await bot.edit_message_text(
            chat_id=status_msg.chat.id,
            message_id=status_msg.message_id,
            text=caption,
            parse_mode="HTML"
        )
    except Exception:
        # If edit fails, send new message
        await safe_reply(message, caption, parse_mode="HTML")


async def check_db_proxies_background(bot, message: types.Message):
    """Check saved proxies in background - PARALLEL, single reply to command"""
    user_id = message.from_user.id
    
    # Fetch proxies from DB
    def fetch_proxies():
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT id, proxy FROM proxies WHERE user_id = %s", (user_id,))
        rows = cursor.fetchall()
        conn.close()
        return rows
    
    try:
        rows = await run_db_operation(fetch_proxies)
    except Exception as e:
        logging.error(f"DB Error: {e}")
        await safe_reply(message, f'{_tg(ID_DECLINED, "❌")} <b>𝐃𝐁 𝐄𝐫𝐫𝐨𝐫.</b>', parse_mode="HTML")
        return

    if not rows:
        await safe_reply(message, f'{_tg(ID_WARNING, "⚠️")} <b>𝐍𝐨 𝐩𝐫𝐨𝐱𝐢𝐞𝐬 𝐬𝐚𝐯𝐞𝐝.</b>', parse_mode="HTML")
        return

    total_count = len(rows)
    
    # Send initial status message
    status_msg = await safe_reply(message, 
        f'{_tg(ID_GATEWAY, "⚡")} <b>𝐂𝐡𝐞𝐜𝐤𝐢𝐧𝐠 𝐲𝐨𝐮𝐫 /𝐩𝐫𝐨𝐱𝐲 𝐩𝐨𝐨𝐥...</b>\n\n'
        f'<code>{total_count}</code> 𝐬𝐚𝐯𝐞𝐝 𝐩𝐫𝐨𝐱𝐢𝐞𝐬\n'
        f'<i>𝐓𝐞𝐬𝐭𝐢𝐧𝐠 {min(MAX_CONCURRENT_CHECKS, total_count)} 𝐚𝐭 𝐚 𝐭𝐢𝐦𝐞...</i>',
        parse_mode="HTML"
    )
    
    # Prepare proxy list for parallel checking
    proxies_to_check = []
    proxy_id_map = {}
    
    for idx, (proxy_id, proxy_str) in enumerate(rows):
        parsed = parse_proxy_input(proxy_str)
        if parsed:
            proxies_to_check.append(parsed)
            proxy_id_map[idx] = proxy_id
        else:
            # Invalid format, mark for deletion
            proxy_id_map[idx] = proxy_id
    
    # ✅ PARALLEL CHECKING - Much faster!
    results_list = await check_proxies_parallel(proxies_to_check)
    
    dead_ids = []
    live_proxies = []
    
    # Process results
    for idx, (proxy_data, is_live, info) in enumerate(results_list):
        db_id = proxy_id_map.get(idx)
        if is_live:
            live_proxies.append(proxy_data['db_format'])
        else:
            if db_id:
                dead_ids.append(db_id)
    
    # Also delete any invalid format proxies
    for idx in range(len(rows)):
        if idx not in proxy_id_map and idx < len(rows):
            dead_ids.append(rows[idx][0])
    
    # Delete dead proxies from DB
    if dead_ids:
        def delete_dead():
            conn = get_db_connection()
            cursor = conn.cursor()
            # Use parameterized query for list
            placeholders = ','.join(['%s'] * len(dead_ids))
            cursor.execute(f"DELETE FROM proxies WHERE id IN ({placeholders})", dead_ids)
            conn.commit()
            conn.close()
        
        try:
            await run_db_operation(delete_dead)
        except Exception as e:
            logging.error(f"DB Delete Error: {e}")

    # Build caption
    caption = (
        f'{_tg(ID_APPROVED, "✅")} <b>𝐂𝐡𝐞𝐜𝐤 𝐂𝐨𝐦𝐩𝐥𝐞𝐭𝐞!</b>\n\n'
        f'<b>𝐓𝐨𝐭𝐚𝐥 ➠</b> <code>{total_count}</code>\n'
        f'{_tg(ID_APPROVED, "✅")} <b>𝐋𝐢𝐯𝐞 ➠</b> <b>{len(live_proxies)}</b>\n'
        f'{_tg(ID_DECLINED, "❌")} <b>𝐑𝐞𝐦𝐨𝐯𝐞𝐝 ➠</b> <b>{len(dead_ids)}</b>'
    )

    kb = InlineKeyboardMarkup(inline_keyboard=[[
        _btn("𝗥𝗲-𝗰𝗵𝗲𝗰𝗸", "chkpxy_again", "primary", ID_GATEWAY),
        _btn("𝗔𝗱𝗱 𝗣𝗿𝗼𝘅𝗶𝗲𝘀", "chkpxy_add", "success", ID_APPROVED),
    ]])

    if not live_proxies:
        caption += f'\n\n{_tg(ID_WARNING, "⚠️")} <b>𝐍𝐨 𝐥𝐢𝐯𝐞 𝐩𝐫𝐨𝐱𝐢𝐞𝐬 𝐫𝐞𝐦𝐚𝐢𝐧𝐢𝐧𝐠.</b>\n\n𝐔𝐬𝐞 /proxy 𝐭𝐨 𝐚𝐝𝐝 𝐦𝐨𝐫𝐞.' 
        
        # Update status message
        try:
            await bot.edit_message_text(
                chat_id=status_msg.chat.id,
                message_id=status_msg.message_id,
                text=caption,
                parse_mode="HTML",
                reply_markup=kb,
            )
        except Exception:
            await safe_reply(message, caption, parse_mode="HTML", reply_markup=kb)
        return

    # Build .txt file content with http format
    file_content = ""
    for p_str in live_proxies:
        parsed = parse_proxy_input(p_str)
        if parsed:
            file_content += parsed['http_format'] + "\n"
        else:
            file_content += p_str + "\n"

    # Write only the LIVE proxies back to the Shopify proxy.txt (remove dead)
    try:
        import shopify_config
        with open(shopify_config.PROXY_FILE, "w", encoding="utf-8") as _pf:
            _pf.write(file_content)
        caption += f'\n\n{_tg(ID_GATEWAY, "⚡")} <b>𝐩𝐫𝐨𝐱𝐲.𝐭𝐱𝐭 𝐮𝐩𝐝𝐚𝐭𝐞𝐝 ➠ {len(live_proxies)} 𝐥𝐢𝐯𝐞</b>'
    except Exception as _e:
        logging.error(f"proxy.txt write error: {_e}")

    # Create file
    txt_file = BufferedInputFile(
        file=file_content.encode('utf-8'),
        filename=f"live_proxies_{len(live_proxies)}.txt"
    )

    # Delete status message and send file
    try:
        await bot.delete_message(
            chat_id=status_msg.chat.id, 
            message_id=status_msg.message_id
        )
    except Exception:
        pass

    # Send document replying directly to original command
    try:
        await message.reply_document(
            document=txt_file,
            caption=caption,
            parse_mode="HTML",
            reply_to_message_id=message.message_id,
            reply_markup=kb,
        )
    except Exception as e:
        logging.error(f"File send error: {e}")
        await safe_reply(message, caption, parse_mode="HTML")


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# COMMAND 1: /proxy (Add Single, Bulk, or File)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

@router.message(F.text.startswith("/proxy"))
async def proxy_command(message: types.Message):
    # Extract proxies from all sources (text, reply, file)
    valid_proxies, total_lines, error_msg = await extract_proxies_from_input(message)
    
    if error_msg:
        await safe_reply(message, error_msg, parse_mode="HTML")
        return
    
    if not valid_proxies:
        if total_lines > 0:
            await safe_reply(message, 
                f'{_tg(ID_DECLINED, "❌")} <b>𝐍𝐨 𝐯𝐚𝐥𝐢𝐝 𝐩𝐫𝐨𝐱𝐢𝐞𝐬 𝐟𝐨𝐮𝐧𝐝!</b>\n\n'
                f"𝐏𝐫𝐨𝐜𝐞𝐬𝐬𝐞𝐝 {total_lines} 𝐥𝐢𝐧𝐞𝐬, 𝐛𝐮𝐭 𝐧𝐨 𝐯𝐚𝐥𝐢𝐝 𝐩𝐫𝐨𝐱𝐢𝐞𝐬 𝐝𝐞𝐭𝐞𝐜𝐭𝐞𝐝.\n\n"
                f"<i>𝐒𝐮𝐩𝐩𝐨𝐫𝐭𝐞𝐝 𝐟𝐨𝐫𝐦𝐚𝐭𝐬:\n"
                f"• ip:port\n"
                f"• user:pass@ip:port\n"
                f"• user:pass ip:port\n"
                f"• ip:port user pass\n"
                f"• user pass ip:port\n"
                f"• user:pass:ip:port</i>",
                parse_mode="HTML"
            )
        else:
            await safe_reply(message, 
                f'{_tg(ID_WARNING, "⚠️")} <b>𝐈𝐧𝐯𝐚𝐥𝐢𝐝 𝐔𝐬𝐚𝐠𝐞!</b>\n\n'
                "𝐔𝐬𝐞: <code>/proxy &lt;proxy_data&gt;</code>\n"
                "𝐎𝐫 𝐬𝐞𝐧𝐝 𝐚 .𝐭𝐱𝐭 𝐟𝐢𝐥𝐞 𝐰𝐢𝐭𝐡 𝐩𝐫𝐨𝐱𝐢𝐞𝐬\n"
                "𝐎𝐫 𝐫𝐞𝐩𝐥𝐲 𝐭𝐨 𝐚 𝐦𝐞𝐬𝐬𝐚𝐠𝐞 𝐜𝐨𝐧𝐭𝐚𝐢𝐧𝐢𝐧𝐠 𝐩𝐫𝐨𝐱𝐢𝐞𝐬",
                parse_mode="HTML"
            )
        return
    
    # Determine source type for display
    source_type = "𝐓𝐞𝐱𝐭 𝐢𝐧𝐩𝐮𝐭"
    if message.document or (message.reply_to_message and message.reply_to_message.document):
        source_type = "𝐓𝐞𝐱𝐭 𝐟𝐢𝐥𝐞 📄"
    elif message.reply_to_message and message.reply_to_message.text:
        source_type = "𝐑𝐞𝐩𝐥𝐢𝐞𝐝 𝐦𝐞𝐬𝐬𝐚𝐠𝐞 💬"
    
    # Start background task
    asyncio.create_task(process_proxies_background(message.bot, message, valid_proxies, source_type))


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# COMMAND 2: /checkproxy
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

@router.message(F.text.startswith(("/checkproxy", "/chkpxy")))
async def checkproxy_command(message: types.Message):
    # Start background task - will reply when done with .txt file
    asyncio.create_task(check_db_proxies_background(message.bot, message))


class _FakeMsg:
    """Minimal message-like object for callback-triggered re-checks."""
    def __init__(self, callback: types.CallbackQuery):
        m = callback.message
        self.from_user = callback.from_user
        self.chat = m.chat
        self.message_id = m.message_id
        self.document = None
        self.reply_to_message = None
        self.text = "/chkpxy"
        self.caption = None
        self.reply = m.answer
        self.answer = m.answer
        self.reply_document = m.answer_document
        self.bot = callback.bot


@router.callback_query(F.data == "chkpxy_again")
async def chkpxy_again_cb(callback: types.CallbackQuery):
    await callback.answer("𝐑𝐞-𝐜𝐡𝐞𝐜𝐤𝐢𝐧𝐠...")
    asyncio.create_task(check_db_proxies_background(callback.bot, _FakeMsg(callback)))


@router.callback_query(F.data == "chkpxy_add")
async def chkpxy_add_cb(callback: types.CallbackQuery):
    await callback.answer("𝐀𝐝𝐝 𝐩𝐫𝐨𝐱𝐢𝐞𝐬")
    await callback.message.answer(
        f'{_tg(ID_APPROVED, "✅")} <b>𝐀𝐝𝐝 𝐩𝐫𝐨𝐱𝐢𝐞𝐬</b>\n\n'
        f'<code>/proxy ip:port</code>\n'
        f'<code>/proxy user:pass@ip:port</code>\n'
        f'𝐨𝐫 𝐬𝐞𝐧𝐝 𝐚 .𝐭𝐱𝐭 𝐟𝐢𝐥𝐞.',
        parse_mode="HTML",
    )


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# COMMAND 3: /clearproxy
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

@router.message(F.text.startswith("/clearproxy"))
async def clearproxy_command(message: types.Message):
    user_id = message.from_user.id
    
    def clear_proxies():
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM proxies WHERE user_id = %s", (user_id,))
        count = cursor.fetchone()[0]
        
        if count > 0:
            cursor.execute("DELETE FROM proxies WHERE user_id = %s", (user_id,))
            conn.commit()
            conn.close()
            return count
        else:
            conn.close()
            return 0
    
    try:
        count = await run_db_operation(clear_proxies)
        if count > 0:
            msg = f'{_tg(ID_APPROVED, "✅")} <b>𝐒𝐮𝐜𝐜𝐞𝐬𝐬!</b>\n\n<b>𝐃𝐞𝐥𝐞𝐭𝐞𝐝 {count} 𝐩𝐫𝐨𝐱𝐢𝐞𝐬.</b>'
        else:
            msg = f'{_tg(ID_WARNING, "⚠️")} <b>𝐃𝐚𝐭𝐚𝐛𝐚𝐬𝐞 𝐢𝐬 𝐚𝐥𝐫𝐞𝐚𝐝𝐲 𝐞𝐦𝐩𝐭𝐲.</b>'
        await safe_reply(message, msg, parse_mode="HTML")
    except Exception as e:
        logging.error(f"DB Error: {e}")
        await safe_reply(message, f'{_tg(ID_DECLINED, "❌")} <b>𝐄𝐫𝐫𝐨𝐫.</b>', parse_mode="HTML")


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# COMMAND 4: /myproxy
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

@router.message(F.text.startswith("/myproxy"))
async def myproxy_command(message: types.Message):
    """Quick check how many proxies are saved"""
    user_id = message.from_user.id
    
    def count_proxies():
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM proxies WHERE user_id = %s", (user_id,))
        count = cursor.fetchone()[0]
        conn.close()
        return count
    
    try:
        count = await run_db_operation(count_proxies)
        if count > 0:
            msg = (
                f'{_tg(ID_STAR, "⭐")} <b>𝐘𝐨𝐮𝐫 𝐏𝐫𝐨𝐱𝐢𝐞𝐬</b>\n\n'
                f"<b>𝐓𝐨𝐭𝐚𝐥 𝐒𝐚𝐯𝐞𝐝:</b> <b>{count}</b> 𝐩𝐫𝐨𝐱𝐢𝐞𝐬\n\n"
                f"𝐔𝐬𝐞 <code>/checkproxy</code> 𝐭𝐨 𝐭𝐞𝐬𝐭 𝐭𝐡𝐞𝐦\n"
                f"𝐔𝐬𝐞 <code>/clearproxy</code> 𝐭𝐨 𝐫𝐞𝐦𝐨𝐯𝐞 𝐚𝐥𝐥"
            )
        else:
            msg = (
                f'{_tg(ID_WARNING, "⚠️")} <b>𝐍𝐨 𝐏𝐫𝐨𝐱𝐢𝐞𝐬</b>\n\n'
                f"𝐘𝐨𝐮 𝐡𝐚𝐯𝐞𝐧'𝐭 𝐬𝐚𝐯𝐞𝐝 𝐚𝐧𝐲 𝐩𝐫𝐨𝐱𝐢𝐞𝐬 𝐲𝐞𝐭.\n\n"
                f"𝐔𝐬𝐞 <code>/proxy</code> 𝐭𝐨 𝐚𝐝𝐝 𝐬𝐨𝐦𝐞!"
            )
        await safe_reply(message, msg, parse_mode="HTML")
    except Exception as e:
        logging.error(f"DB Error: {e}")
        await safe_reply(message, f'{_tg(ID_DECLINED, "❌")} <b>𝐄𝐫𝐫𝐨𝐫.</b>', parse_mode="HTML")