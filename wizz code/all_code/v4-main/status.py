import asyncio
import platform
import time
from datetime import datetime, timedelta
from typing import Tuple, Optional

from aiogram import Router, types
from aiogram.filters import Command

try:
    import psutil
    HAS_PSUTIL = True
except ImportError:
    HAS_PSUTIL = False

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# CONFIGURATION
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Owner only – /status exposes host/VPS internals, so it is
# restricted to the owner. Keep in sync with main.py ADMIN_IDS.

# Clickable bullet link (Telegram channel/username)
BULLET_LINK = '<a href="https://t.me/wizs_hub">⌬</a>'

OWNER_IDS: set = {8462705169}

router = Router()


def _is_owner(user_id: int) -> bool:
    return user_id in OWNER_IDS

# Global variable to store bot start time
BOT_START_TIME: Optional[float] = None


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# HELPERS
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
def _fmt_bytes(n: int) -> str:
    """Convert bytes to human readable format."""
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if n < 1024:
            return f"{n:.1f} {unit}"
        n /= 1024
    return f"{n:.1f} PB"


def _fmt_gb(n: int) -> float:
    """Convert bytes to GB."""
    return n / (1024 ** 3)


def _create_progress_bar(percent: float, length: int = 10) -> str:
    """Create a visual progress bar."""
    filled = int(length * percent / 100)
    empty = length - filled
    return f"█" * filled + f"░" * empty


def _get_os_version() -> str:
    """Get detailed OS version."""
    system = platform.system()
    release = platform.release()
    version = platform.version()
    
    if system == "Linux":
        try:
            with open("/etc/os-release", "r") as f:
                for line in f:
                    if line.startswith("PRETTY_NAME="):
                        return line.split("=")[1].strip().strip('"')
        except:
            pass
        return f"{system} {release}"
    elif system == "Windows":
        return f"{system} {release} (Build {version.split('.')[-1]})"
    elif system == "Darwin":
        return f"macOS {release}"
    else:
        return f"{system} {release}"


def _collect_status() -> Tuple[str, dict]:
    """
    Collect system status information.
    Returns a tuple of (formatted_message, raw_data_dict)
    """
    if not HAS_PSUTIL:
        return (
            f"{BULLET_LINK} ⚠️ <b>psutil not installed.</b>\n"
            f"{BULLET_LINK} Run: <code>pip install psutil</code>",
            {}
        )
    
    # ── SYSTEM INFORMATION ──────────────────────────────────────────
    os_name = _get_os_version()
    architecture = platform.machine()
    hostname = platform.node()
    
    # ── CPU ──────────────────────────────────────────────────────────
    cores_phys = psutil.cpu_count(logical=False) or 1
    cores_logic = psutil.cpu_count(logical=True) or 1
    cpu_usage = psutil.cpu_percent(interval=0.5)
    cpu_bar = _create_progress_bar(cpu_usage)
    
    # ── RAM ──────────────────────────────────────────────────────────
    ram = psutil.virtual_memory()
    total_memory = _fmt_gb(ram.total)
    used_memory = _fmt_gb(ram.used)
    available_memory = _fmt_gb(ram.available)
    ram_percent = ram.percent
    ram_bar = _create_progress_bar(ram_percent)
    
    # ── SWAP ─────────────────────────────────────────────────────────
    swap = psutil.swap_memory()
    total_swap = _fmt_gb(swap.total) if swap.total > 0 else 0
    used_swap = _fmt_gb(swap.used) if swap.total > 0 else 0
    swap_percent = swap.percent if swap.total > 0 else 0
    swap_bar = _create_progress_bar(swap_percent)
    
    # ── DISK ─────────────────────────────────────────────────────────
    disk = psutil.disk_usage("/")
    total_disk = _fmt_gb(disk.total)
    used_disk = _fmt_gb(disk.used)
    free_disk = _fmt_gb(disk.free)
    disk_percent = disk.percent
    disk_bar = _create_progress_bar(disk_percent)
    
    # ── NETWORK ──────────────────────────────────────────────────────
    net = psutil.net_io_counters()
    sent_bytes = net.bytes_sent
    recv_bytes = net.bytes_recv
    
    # Format network speeds with appropriate units
    def _fmt_speed(bytes_val: int) -> str:
        if bytes_val < 1024:
            return f"{bytes_val} B"
        elif bytes_val < 1024 ** 2:
            return f"{bytes_val / 1024:.1f} KB"
        elif bytes_val < 1024 ** 3:
            return f"{bytes_val / (1024 ** 2):.1f} MB"
        else:
            return f"{bytes_val / (1024 ** 3):.2f} GB"
    
    upload_str = _fmt_speed(sent_bytes)
    download_str = _fmt_speed(recv_bytes)
    
    # ── UPTIME ───────────────────────────────────────────────────────
    uptime_sec = int(time.time() - psutil.boot_time())
    uptime_str = str(timedelta(seconds=uptime_sec))
    
    # Format uptime to be more readable
    days = uptime_sec // 86400
    hours = (uptime_sec % 86400) // 3600
    minutes = (uptime_sec % 3600) // 60
    seconds = uptime_sec % 60
    
    if days > 0:
        uptime_str = f"{days}d {hours}h {minutes}m"
    elif hours > 0:
        uptime_str = f"{hours}h {minutes}m {seconds}s"
    elif minutes > 0:
        uptime_str = f"{minutes}m {seconds}s"
    else:
        uptime_str = f"{seconds}s"
    
    # ── BOT UPTIME ───────────────────────────────────────────────────
    bot_uptime_str = "N/A"
    if BOT_START_TIME:
        bot_uptime_sec = int(time.time() - BOT_START_TIME)
        days = bot_uptime_sec // 86400
        hours = (bot_uptime_sec % 86400) // 3600
        minutes = (bot_uptime_sec % 3600) // 60
        seconds = bot_uptime_sec % 60
        
        if days > 0:
            bot_uptime_str = f"{days}d {hours}h {minutes}m"
        elif hours > 0:
            bot_uptime_str = f"{hours}h {minutes}m {seconds}s"
        elif minutes > 0:
            bot_uptime_str = f"{minutes}m {seconds}s"
        else:
            bot_uptime_str = f"{seconds}s"
    
    # ── TOTAL USERS ──────────────────────────────────────────────────
    # This requires access to your database/user storage
    # For now, we'll return a placeholder that can be updated
    total_users = "N/A (requires DB)"
    
    # ── TIMESTAMP ────────────────────────────────────────────────────
    current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    last_updated = datetime.now().strftime("%H:%M:%S")
    
    # Build the formatted message
    message = (
        f"<pre>[ 𝐁𝐨𝐭 & 𝐕𝐏𝐒 𝐒𝐭𝐚𝐭𝐮𝐬 ]</pre>\n"
        f"{BULLET_LINK} 𝐒𝐭𝐚𝐭𝐮𝐬 ➠ <b>Active <tg-emoji emoji-id=\"5085022089103016925\">⚡</tg-emoji></b>\n"
        f"{BULLET_LINK} 𝐒𝐲𝐬𝐭𝐞𝐦 ➠ <b>{os_name}</b>\n"
        f"{BULLET_LINK} 𝐀𝐫𝐜𝐡𝐢𝐭𝐞𝐜𝐭𝐮𝐫𝐞 ➠ <b>{architecture}</b>\n"
        f"{BULLET_LINK} 𝐇𝐨𝐬𝐭𝐧𝐚𝐦𝐞 ➠ <b>{hostname}</b>\n"
        "――――――――――――――――――――――\n"
        f"{BULLET_LINK} 𝐂𝐏𝐔 ➠ <b>{cpu_usage:.1f}% ({cores_logic} cores)</b>\n"
        f"     {cpu_bar}\n"
        f"{BULLET_LINK} 𝐑𝐀𝐌 ➠ <b>{used_memory:.2f}GB / {total_memory:.2f}GB</b>\n"
        f"     {ram_bar}\n"
        f"    𝐑𝐀𝐌 𝐀𝐯𝐚𝐢𝐥𝐚𝐛𝐥𝐞 ➠ <b>{available_memory:.2f}GB</b>\n"
        f"{BULLET_LINK} 𝐒𝐰𝐚𝐩 ➠ <b>{used_swap:.2f}GB / {total_swap:.2f}GB</b>\n"
        f"     {swap_bar}\n"
        f"{BULLET_LINK} 𝐃𝐢𝐬𝐤 ➠ <b>{used_disk:.2f}GB / {total_disk:.2f}GB</b>\n"
        f"     {disk_bar}\n"
        f"    𝐃𝐢𝐬𝐤 𝐀𝐯𝐚𝐢𝐥𝐚𝐛𝐥𝐞 ➠ <b>{free_disk:.2f}GB</b>\n"
        "――――――――――――――――――――――\n"
        f"{BULLET_LINK} 𝐍𝐞𝐭𝐰𝐨𝐫𝐤 𝐒𝐩𝐞𝐞𝐝\n"
        f"     𝐔𝐩𝐥𝐨𝐚𝐝 ➠ <b>{upload_str}</b>\n"
        f"     𝐃𝐨𝐰𝐧𝐥𝐨𝐚𝐝 ➠ <b>{download_str}</b>\n"
        "――――――――――――――――――――――\n"
        #f"{BULLET_LINK} 𝐓𝐨𝐭𝐚𝐥 𝐔𝐬𝐞𝐫𝐬 ➠ <b>{total_users}</b>\n"
        f"{BULLET_LINK} 𝐕𝐏𝐒 𝐔𝐩𝐭𝐢𝐦𝐞 ➠ <b>{uptime_str}</b>\n"
        #f"{BULLET_LINK} 𝐁𝐨𝐭 𝐔𝐩𝐭𝐢𝐦𝐞 ➠ <b>{bot_uptime_str}</b>\n"
        f"{BULLET_LINK} 𝐂𝐮𝐫𝐫𝐞𝐧𝐭 𝐓𝐢𝐦𝐞 ➠ <b>{current_time}</b>\n"
        f"{BULLET_LINK} 𝐋𝐚𝐬𝐭 𝐔𝐩𝐝𝐚𝐭𝐞𝐝 ➠ <b>{last_updated}</b>\n"
        f"{BULLET_LINK} 𝐁𝐨𝐭 𝐁𝐲 ➠ <a href='tg://resolve?domain=broken_wiz'>𒉼 𝔦 乙</a>\n"
        "――――――――――――――――――――――"
    )
    
    raw_data = {
        "cpu_usage": cpu_usage,
        "ram_used": used_memory,
        "ram_total": total_memory,
        "disk_used": used_disk,
        "disk_total": total_disk,
        "uptime": uptime_sec,
        "bot_uptime": bot_uptime_sec if BOT_START_TIME else 0,
    }
    
    return message, raw_data


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# /status COMMAND (owner only)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
@router.message(Command("status"))
async def status_command(message: types.Message):
    """Handle /status command - displays VPS and bot status. Owner only."""
    if not _is_owner(message.from_user.id):
        await message.reply(
            f"{BULLET_LINK} ❌ <b>This command is for the owner only.</b>",
            parse_mode="HTML",
        )
        return

    # Send "typing" action while collecting data
    await message.bot.send_chat_action(message.chat.id, "typing")
    
    try:
        # Collect system status (runs in thread to avoid blocking)
        text, _ = await asyncio.to_thread(_collect_status)
        
        # Send the formatted message
        await message.reply(
            text,
            parse_mode="HTML",
            disable_web_page_preview=True
        )
    except Exception as e:
        error_msg = (
            f"{BULLET_LINK} ❌ <b>Failed to collect system status:</b>\n"
            f"{BULLET_LINK} <code>{str(e)}</code>"
        )
        await message.reply(error_msg, parse_mode="HTML")


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# INITIALIZATION FUNCTION
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
def init_status_module(bot_start_time: float):
    """
    Initialize the status module with bot start time.
    Call this when your bot starts up.
    """
    global BOT_START_TIME
    BOT_START_TIME = bot_start_time