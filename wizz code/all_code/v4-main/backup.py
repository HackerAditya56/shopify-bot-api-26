"""
Daily database + stats-file backup.

Every 24 h (at 00:00 server time, UTC) this module:
  1. dumps the PostgreSQL database with pg_dump  (gzip-compressed)
  2. zips the stats .txt files (mshh.txt, mst.txt, …)
  3. saves both to ./backups/ and DMs them to the owner
  4. prunes copies older than RETENTION_DAYS

It also performs a catch-up backup on boot if the newest one is older
than 20 h, so a restart around midnight never skips a day.
"""

import os
import gzip
import shutil
import zipfile
import asyncio
import logging
import subprocess
from datetime import datetime, timedelta
from pathlib import Path

from aiogram.types import FSInputFile

from database import DB_CONFIG

# ─────────────────────────────────────────────────────────────────────────────
# CONFIG
# ─────────────────────────────────────────────────────────────────────────────

BACKUP_DIR      = Path(__file__).resolve().parent / "backups"
RETENTION_DAYS  = 7          # keep this many days of backups
CATCHUP_AFTER_H = 20         # boot-time: back up if newest is older than this

# Stats / hit-log files written by the mass-checker commands.
STATS_FILES = [
    "mshh.txt",   # msh
    "mst.txt",    # mst
    "mchk.txt",   # mchk
    "mrz.txt",    # mrz
    "msk.txt",    # msk
    "mpp.txt",    # mpp
    "sites.txt",  # site list
]

PG_DUMP_BIN = shutil.which("pg_dump") or "/usr/bin/pg_dump"


# ─────────────────────────────────────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────────────────────────────────────

def _admin_id() -> int:
    try:
        from sub import ADMIN_ID
        return ADMIN_ID
    except Exception:
        return 8462705169


def _dump_db_sql(tmp_sql: Path) -> None:
    """Run pg_dump to a plain-SQL file. Raises on failure."""
    params = {
        "host":     DB_CONFIG["host"],
        "port":     str(DB_CONFIG.get("port", 5432)),
        "user":     DB_CONFIG["user"],
        "database": DB_CONFIG["database"],
        "password": DB_CONFIG["password"],
    }
    env = os.environ.copy()
    env["PGPASSWORD"] = params["password"]
    cmd = [
        PG_DUMP_BIN,
        "-h", params["host"],
        "-p", params["port"],
        "-U", params["user"],
        "-d", params["database"],
        "--no-owner",
        "--no-privileges",
        "--clean",
        "--if-exists",
        "-f", str(tmp_sql),
    ]
    proc = subprocess.run(cmd, env=env, capture_output=True, text=True, timeout=600)
    if proc.returncode != 0 or not tmp_sql.exists():
        raise RuntimeError(
            f"pg_dump failed (code {proc.returncode}): {proc.stderr.strip()[:400]}"
        )


def _gzip_file(src: Path, dest: Path) -> None:
    with open(src, "rb") as fin, gzip.open(dest, "wb", compresslevel=9) as fout:
        shutil.copyfileobj(fin, fout)


def _make_txt_zip(dest: Path) -> list:
    included = []
    with zipfile.ZipFile(dest, "w", zipfile.ZIP_DEFLATED) as zf:
        for name in STATS_FILES:
            p = Path(name)
            if p.exists() and p.is_file():
                zf.write(p, arcname=name)
                included.append(name)
    return included


def _prune(pattern_prefix: str) -> int:
    cutoff = datetime.now() - timedelta(days=RETENTION_DAYS)
    removed = 0
    for f in BACKUP_DIR.glob(f"{pattern_prefix}_*"):
        try:
            if datetime.fromtimestamp(f.stat().st_mtime) < cutoff:
                f.unlink()
                removed += 1
        except Exception:
            pass
    return removed


def _latest_age_hours() -> float:
    """Hours since the most recent backup file, or a huge number if none."""
    newest = 0.0
    for f in BACKUP_DIR.glob("broken_db_*.sql.gz"):
        try:
            newest = max(newest, f.stat().st_mtime)
        except Exception:
            pass
    if not newest:
        return 1e9
    return (datetime.now() - datetime.fromtimestamp(newest)).total_seconds() / 3600


# ─────────────────────────────────────────────────────────────────────────────
# BACKUP RUN
# ─────────────────────────────────────────────────────────────────────────────

async def run_backup(bot, reason: str = "scheduled"):
    """Create the DB + txt backups, DM them to the owner, prune old ones."""
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    stamp    = datetime.now().strftime("%Y-%m-%d")
    admin_id = _admin_id()

    db_gz    = BACKUP_DIR / f"broken_db_{stamp}.sql.gz"
    txt_zip  = BACKUP_DIR / f"stats_txt_{stamp}.zip"
    tmp_sql  = BACKUP_DIR / f".broken_db_{stamp}.tmp.sql"

    logging.info(f"[Backup] Starting ({reason}) …")

    # ── database dump ────────────────────────────────────────────────────────
    db_ok = False
    try:
        await asyncio.to_thread(_dump_db_sql, tmp_sql)
        await asyncio.to_thread(_gzip_file, tmp_sql, db_gz)
        db_ok = True
        size = db_gz.stat().st_size / 1024
        logging.info(f"[Backup] DB dump OK → {db_gz.name} ({size:.0f} KB)")
    except Exception as e:
        logging.error(f"[Backup] DB dump failed: {e}")
    finally:
        try:
            if tmp_sql.exists():
                tmp_sql.unlink()
        except Exception:
            pass

    # ── stats txt files ──────────────────────────────────────────────────────
    txt_ok, included = False, []
    try:
        included = await asyncio.to_thread(_make_txt_zip, txt_zip)
        txt_ok = True
        logging.info(f"[Backup] TXT zip OK → {txt_zip.name} ({len(included)} files)")
    except Exception as e:
        logging.error(f"[Backup] TXT zip failed: {e}")

    # ── deliver to owner ─────────────────────────────────────────────────────
    now_str = datetime.now().strftime("%d %b %Y, %H:%M UTC")
    if db_ok:
        try:
            await bot.send_document(
                chat_id=admin_id,
                document=FSInputFile(str(db_gz)),
                caption=(
                    "<b>🗄 Database Backup</b>\n"
                    "━━━━━━━━━━━\n"
                    f"📅 Date : <b>{now_str}</b>\n"
                    f"🗂 File : <code>{db_gz.name}</code>\n"
                    "🔐 Full PostgreSQL dump (restore: <code>gunzip | psql</code>)\n"
                    "━━━━━━━━━━━"
                ),
                parse_mode="HTML",
            )
        except Exception as e:
            logging.error(f"[Backup] Could not send DB backup: {e}")

    if txt_ok:
        try:
            file_list = "\n".join(f"• <code>{n}</code>" for n in included) or "• (none yet)"
            await bot.send_document(
                chat_id=admin_id,
                document=FSInputFile(str(txt_zip)),
                caption=(
                    "<b>📄 Stats Files Backup</b>\n"
                    "━━━━━━━━━━━\n"
                    f"📅 Date : <b>{now_str}</b>\n"
                    f"{file_list}\n"
                    "━━━━━━━━━━━"
                ),
                parse_mode="HTML",
            )
        except Exception as e:
            logging.error(f"[Backup] Could not send TXT backup: {e}")

    # if the DB dump broke, warn the owner explicitly
    if not db_ok:
        try:
            await bot.send_message(
                chat_id=admin_id,
                text="⚠️ <b>Backup failed!</b>\nThe daily database dump did not complete. Check the bot logs.",
                parse_mode="HTML",
            )
        except Exception:
            pass

    # ── prune old copies ─────────────────────────────────────────────────────
    removed  = await asyncio.to_thread(_prune, "broken_db")
    removed += await asyncio.to_thread(_prune, "stats_txt")
    if removed:
        logging.info(f"[Backup] Pruned {removed} old file(s)")
    logging.info("[Backup] Done ✅")


# ─────────────────────────────────────────────────────────────────────────────
# SCHEDULER
# ─────────────────────────────────────────────────────────────────────────────

def _seconds_until_midnight() -> float:
    now = datetime.now()
    tomorrow = (now + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
    return max(60.0, (tomorrow - now).total_seconds())


async def daily_backup_scheduler(bot):
    """Catch-up once on boot, then run every day at 00:00 server time."""
    try:
        age = await asyncio.to_thread(_latest_age_hours)
        if age > CATCHUP_AFTER_H:
            logging.info(f"[Backup] Last backup {age:.0f}h old — running catch-up now.")
            await run_backup(bot, reason="catch-up")
    except Exception as e:
        logging.error(f"[Backup] catch-up error: {e}")

    while True:
        wait = _seconds_until_midnight()
        logging.info(f"[Backup] Next run in {wait/3600:.2f}h (00:00 UTC)")
        await asyncio.sleep(wait)
        try:
            await run_backup(bot, reason="scheduled")
        except Exception as e:
            logging.error(f"[Backup] scheduled run error: {e}")
