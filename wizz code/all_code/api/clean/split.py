#!/usr/bin/env python3
"""
╔═══════════════════════════════════════════════════════════════════════════════╗
║           ULTIMATE CARD CLEANER & SPLITTER BOT  v5.0                         ║
║                        Production-Ready Release                               ║
║                             by Just-Lisa                                      ║
╚═══════════════════════════════════════════════════════════════════════════════╝

FEATURES:
    ✓ /clean     — Extract, validate, sort, deduplicate cards from any dump
    ✓ /split     — Interactive chunk splitting with 60s session timeout (no ZIPs)
    ✓ /shuffle   — True randomisation via Fisher-Yates algorithm
    ✓ /stats     — Audit statistics from persistent SQLite log
    ✓ /cancel    — Abort any active split session
    ✓ /broadcast — Owner-only: push a message to every registered user
    ✓ /scan      — Deep BIN analysis: country/network/type stats + export slices
    ✓ /fbin      — Filter a cleaned file by BIN prefix
    ✓ /bank      — Filter a cleaned file by bank name (partial, case-insensitive)
    ✓ Async processing  — multiple users served simultaneously
    ✓ Streaming I/O     — memory-efficient for very large files (300 MB+)
    ✓ In-memory sessions — instant timeout enforcement via asyncio.Task
    ✓ Structured logging — file + console with coloured output
    ✓ BIN caching       — each unique BIN looked up only once per scan
    ✓ Concurrent BIN API — aiohttp + semaphore for fast parallel lookups
    ✓ Export slices     — per country, network, type, bank, BIN
    ✓ Button pagination — navigate large result sets with inline keyboards
"""

# ============================================================
# STANDARD LIBRARY IMPORTS
# ============================================================
import os
import re
import sqlite3
import uuid
import tempfile
import random
import hashlib
import asyncio
import logging
import shutil
from contextlib import contextmanager
from collections import OrderedDict
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

# ============================================================
# THIRD-PARTY IMPORTS
# ============================================================
try:
    import aiohttp
except ImportError:
    os.system("pip install aiohttp")
    import aiohttp  # type: ignore

try:
    from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
    from telegram.ext import (
        Application,
        CallbackQueryHandler,
        CommandHandler,
        ConversationHandler,
        MessageHandler,
        ContextTypes,
        filters,
    )
    from telegram.constants import ParseMode, KeyboardButtonStyle
    from telegram.error import TelegramError
except ImportError:
    os.system("pip install python-telegram-bot>=21.0")
    from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup  # type: ignore
    from telegram.ext import (  # type: ignore
        Application,
        CallbackQueryHandler,
        CommandHandler,
        ConversationHandler,
        MessageHandler,
        ContextTypes,
        filters,
    )
    from telegram.constants import ParseMode, KeyboardButtonStyle  # type: ignore
    from telegram.error import TelegramError  # type: ignore

# ============================================================
# CONFIGURATION  (edit only this section)
# ============================================================
BOT_TOKEN: str = os.getenv("BOT_TOKEN", "8790453273:AAH2729HAfBJzMLcGUmSkzXfaojfPIAhbL8")
OWNER_ID: int = int(os.getenv("OWNER_ID", "8423281554"))
ADMIN_IDS: List[int] = [
    int(x) for x in os.getenv("ADMIN_IDS", "8423281554").split(",") if x.strip().isdigit()
]
SUPPORT_CHANNEL_LINK = "https://t.me/WIZXCHKv2_BOT"

MAX_FILE_SIZE: int = 300 * 1024 * 1024        # 300 MB — bot-side sanity cap
# Telegram's standard Bot API hard-limits getFile downloads to 20 MB.
# Files larger than this cause "File is too big" before any download starts.
TELEGRAM_DOWNLOAD_LIMIT: int = 20 * 1024 * 1024  # 20 MB
ALLOWED_EXTENSIONS = {".txt", ".dump", ".csv", ".cc", ".cards", ".data"}
SPLIT_TIMEOUT_SECONDS: int = 60
DATABASE_PATH: str = "card_bot_v4.db"
LOG_FILE: str = "card_bot.log"
MAX_CHUNK_SIZE: int = 500_000

# BIN service
BIN_API_URL = "https://bins.antipublic.cc/bins/{bin}"
BIN_CONCURRENCY = 200          # max parallel BIN lookups
BIN_RETRY_ATTEMPTS = 3        # retries on API failure
BIN_RETRY_DELAY = 1.0         # seconds between retries
BIN_MAX_PASSES = 2            # extra sweep rounds for BINs the API left unanswered
BIN_ROWS_IN_REPORT = 25       # BIN rows rendered in the report body

# Placeholders for BINs the lookup service has no metadata for
UNKNOWN_LABEL = "Unknown"
UNKNOWN_FLAG  = "🏳"

# Scan session
SCAN_SESSION_TTL_HOURS = 2    # auto-expire scan sessions
COUNTRIES_IN_TEXT = 16         # max countries shown in the stats message body(8)
ITEMS_PER_PAGE = 12            # export buttons per pagination page(6)

# ============================================================
# LOGGING
# ============================================================
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(name)s  %(message)s",
    handlers=[
        logging.FileHandler(LOG_FILE, encoding="utf-8"),
        logging.StreamHandler(),
    ],
)
logger = logging.getLogger("CardBot")


class _C:
    GRN = "\033[92m"
    RED = "\033[91m"
    CYN = "\033[96m"
    YLW = "\033[93m"
    RST = "\033[0m"


def _ok(msg: str) -> None:
    logger.info(msg)
    print(f"{_C.GRN}[✓] {msg}{_C.RST}")


def _err(msg: str) -> None:
    logger.error(msg)
    print(f"{_C.RED}[✗] {msg}{_C.RST}")


def _info(msg: str) -> None:
    logger.info(msg)
    print(f"{_C.CYN}[i] {msg}{_C.RST}")


def _warn(msg: str) -> None:
    logger.warning(msg)
    print(f"{_C.YLW}[!] {msg}{_C.RST}")


# ============================================================
# CONVERSATION STATES
# ============================================================
WAITING_FOR_SPLIT_SIZE = 1

# ============================================================
# CARD VALIDATOR
# ============================================================

class CardValidator:
    """
    Luhn check + BIN-range detection.
    Priority mirrors the /clean sort order required by spec.
    """

    _PATTERNS: "OrderedDict[str, re.Pattern]" = OrderedDict([
        ("BIN2",       re.compile(r"^2[0-9]{15}$")),
        ("AMEX",       re.compile(r"^3[47][0-9]{13}$")),
        ("VISA",       re.compile(r"^4[0-9]{12}(?:[0-9]{3})?$")),
        ("MASTERCARD", re.compile(
            r"^(5[1-5][0-9]{14}|2(2[2-9][0-9]{12}|[3-6][0-9]{13}|7[0-1][0-9]{12}|720[0-9]{12}))$"
        )),
        ("DISCOVER",   re.compile(
            r"^6(?:011|5[0-9]{2}|4[4-9][0-9]|22(?:12[6-9]|1[3-9][0-9]"
            r"|[2-8][0-9]{2}|9[01][0-9]|92[0-5])|64[4-9][0-9]|65[0-9]{2})[0-9]{10,12}$"
        )),
        ("JCB",        re.compile(r"^(352[8-9]|35[3-8][0-9])[0-9]{12}$")),
        ("DINERS",     re.compile(r"^3(?:0[0-5]|[68][0-9])[0-9]{11}$")),
        ("UNIONPAY",   re.compile(r"^62[0-9]{14,17}$")),
    ])

    _PRIORITY: Dict[str, int] = {
        "BIN2": 0, "AMEX": 1, "VISA": 2, "MASTERCARD": 3,
        "DISCOVER": 4, "JCB": 5, "DINERS": 6, "UNIONPAY": 7,
    }

    @staticmethod
    def luhn(number: str) -> bool:
        total, odd = 0, False
        for ch in reversed(number):
            d = int(ch)
            if odd:
                d *= 2
                if d > 9:
                    d -= 9
            total += d
            odd = not odd
        return total % 10 == 0

    @classmethod
    def card_type(cls, number: str) -> str:
        for name, pat in cls._PATTERNS.items():
            if pat.match(number):
                return name
        return "UNKNOWN"

    @classmethod
    def validate(
        cls,
        number: str,
        exp_month: str = "",
        exp_year: str = "",
    ) -> Tuple[bool, str, Optional[Dict]]:
        number = re.sub(r"\D", "", number)

        if not (13 <= len(number) <= 19):
            return False, "bad_length", None
        if not cls.luhn(number):
            return False, "luhn_fail", None

        ctype = cls.card_type(number)
        if ctype == "UNKNOWN":
            return False, "unknown_type", None

        if exp_month and exp_year:
            try:
                now = datetime.now()
                yr = int(exp_year)
                if yr < 100:
                    yr += 2000
                mo = int(exp_month)
                if yr < now.year or (yr == now.year and mo < now.month):
                    return False, "expired", None
            except (ValueError, TypeError):
                pass

        return True, "valid", {
            "card_number": number,
            "type": ctype,
            "bin": number[:6],
            "last4": number[-4:],
            "exp_month": exp_month.zfill(2) if exp_month else "",
            "exp_year": exp_year,
            "priority": cls._PRIORITY.get(ctype, 99),
        }


# ============================================================
# CARD EXTRACTOR
# ============================================================

class CardExtractor:
    """
    Extracts complete card records (number + month + year + CVV) from dump lines.

    Supported delimiters: | : / , and space (mixed is fine).
    Only returns records where all four fields are present.
    """

    _TRACK1 = re.compile(r"%B(\d{13,19})\^[^\^]+\^(\d{2})(\d{2})", re.I)
    _TRACK2 = re.compile(r";(\d{13,19})=(\d{2})(\d{2})\d{3}(\d{3,4})?", re.I)
    _FULL   = re.compile(
        r"(\d{13,19})"
        r"[\s|:/,]+"
        r"(\d{1,2})"
        r"[\s|:/,]+"
        r"(\d{2,4})"
        r"[\s|:/,]+"
        r"(\d{3,4})"
        r"(?=\s|[|:/,]|$)"
    )

    @classmethod
    def from_line(cls, line: str) -> List[Dict]:
        line = line.strip()
        if len(line) < 19:
            return []

        results: List[Dict] = []

        t1 = cls._TRACK1.search(line)
        t2 = cls._TRACK2.search(line)
        if t1:
            cvv = t2.group(4) if (t2 and t2.group(4)) else ""
            if cvv:
                results.append({
                    "card_number": t1.group(1),
                    "exp_month":   t1.group(3),
                    "exp_year":    t1.group(2),
                    "cvv":         cvv,
                })
            return results

        for m in cls._FULL.finditer(line):
            results.append({
                "card_number": m.group(1),
                "exp_month":   m.group(2).zfill(2),
                "exp_year":    m.group(3),
                "cvv":         m.group(4),
            })

        return results


# ============================================================
# YEAR NORMALISER
# ============================================================

def normalise_year(year: str) -> str:
    """Always returns a 4-digit year string. Empty stays empty."""
    if not year:
        return ""
    try:
        y = int(year)
        return str(2000 + y) if y < 100 else str(y)
    except ValueError:
        return year


# ============================================================
# DATABASE
# ============================================================

class Database:
    """Lightweight SQLite wrapper for audit logging."""

    def __init__(self, path: str) -> None:
        self.path = path
        self._init()

    @contextmanager
    def _conn(self):
        conn = sqlite3.connect(self.path, timeout=30)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def _init(self) -> None:
        with self._conn() as c:
            c.execute("""
                CREATE TABLE IF NOT EXISTS users (
                    id         INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id    INTEGER UNIQUE,
                    username   TEXT,
                    first_name TEXT,
                    first_seen TEXT,
                    last_seen  TEXT
                )
            """)
            c.execute("""
                CREATE TABLE IF NOT EXISTS clean_ops (
                    id           INTEGER PRIMARY KEY AUTOINCREMENT,
                    op_id        TEXT UNIQUE,
                    user_id      INTEGER,
                    input_name   TEXT,
                    total_lines  INTEGER,
                    valid        INTEGER,
                    invalid      INTEGER,
                    duplicates   INTEGER,
                    expired      INTEGER,
                    ts           TEXT
                )
            """)
            c.execute("""
                CREATE TABLE IF NOT EXISTS split_ops (
                    id           INTEGER PRIMARY KEY AUTOINCREMENT,
                    op_id        TEXT UNIQUE,
                    user_id      INTEGER,
                    source_name  TEXT,
                    total_cards  INTEGER,
                    chunk_size   INTEGER,
                    chunks       INTEGER,
                    ts           TEXT
                )
            """)
            c.execute("""
                CREATE TABLE IF NOT EXISTS shuffle_ops (
                    id           INTEGER PRIMARY KEY AUTOINCREMENT,
                    op_id        TEXT UNIQUE,
                    user_id      INTEGER,
                    source_name  TEXT,
                    card_count   INTEGER,
                    ts           TEXT
                )
            """)
        _info("Database initialised")

    def register_user(self, user_id: int, username: str, first_name: str) -> None:
        now = datetime.now().isoformat()
        with self._conn() as c:
            c.execute(
                """
                INSERT INTO users (user_id, username, first_name, first_seen, last_seen)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(user_id) DO UPDATE SET
                    username   = excluded.username,
                    first_name = excluded.first_name,
                    last_seen  = excluded.last_seen
                """,
                (user_id, username or "", first_name or "", now, now),
            )

    def get_all_user_ids(self) -> List[int]:
        with self._conn() as c:
            rows = c.execute("SELECT user_id FROM users ORDER BY id").fetchall()
        return [r[0] for r in rows]

    def get_user_count(self) -> int:
        with self._conn() as c:
            return c.execute("SELECT COUNT(*) FROM users").fetchone()[0]

    def log_clean(self, user_id: int, input_name: str, stats: Dict) -> None:
        op_id = str(uuid.uuid4())[:8]
        with self._conn() as c:
            c.execute(
                "INSERT INTO clean_ops VALUES (NULL,?,?,?,?,?,?,?,?,?)",
                (op_id, user_id, input_name,
                 stats["total"], stats["valid"], stats["invalid"],
                 stats["duplicates"], stats["expired"],
                 datetime.now().isoformat()),
            )

    def log_split(self, user_id: int, source: str, total: int,
                  chunk: int, chunks: int) -> None:
        op_id = str(uuid.uuid4())[:8]
        with self._conn() as c:
            c.execute(
                "INSERT INTO split_ops VALUES (NULL,?,?,?,?,?,?,?)",
                (op_id, user_id, source, total, chunk, chunks,
                 datetime.now().isoformat()),
            )

    def log_shuffle(self, user_id: int, source: str, count: int) -> None:
        op_id = str(uuid.uuid4())[:8]
        with self._conn() as c:
            c.execute(
                "INSERT INTO shuffle_ops VALUES (NULL,?,?,?,?,?)",
                (op_id, user_id, source, count,
                 datetime.now().isoformat()),
            )

    def get_stats(self) -> Dict:
        with self._conn() as c:
            users       = c.execute("SELECT COUNT(*) FROM users").fetchone()[0]
            clean_ops   = c.execute("SELECT COUNT(*) FROM clean_ops").fetchone()[0]
            split_ops   = c.execute("SELECT COUNT(*) FROM split_ops").fetchone()[0]
            shuffle_ops = c.execute("SELECT COUNT(*) FROM shuffle_ops").fetchone()[0]
            total_valid = c.execute(
                "SELECT COALESCE(SUM(valid),0) FROM clean_ops"
            ).fetchone()[0]
        return {
            "users":       users,
            "clean_ops":   clean_ops,
            "split_ops":   split_ops,
            "shuffle_ops": shuffle_ops,
            "total_valid": total_valid,
        }


# ============================================================
# IN-MEMORY SPLIT SESSION MANAGER
# ============================================================

class SplitSession:
    __slots__ = ("user_id", "file_path", "original_name", "total_cards",
                 "created_at", "timeout_task")

    def __init__(self, user_id: int, file_path: str, original_name: str,
                 total_cards: int) -> None:
        self.user_id       = user_id
        self.file_path     = file_path
        self.original_name = original_name
        self.total_cards   = total_cards
        self.created_at    = datetime.now()
        self.timeout_task: Optional[asyncio.Task] = None


class SplitSessionManager:
    """Thread-safe (asyncio) in-memory session store."""

    def __init__(self) -> None:
        self._sessions: Dict[int, SplitSession] = {}

    def create(self, user_id: int, file_path: str, original_name: str,
               total_cards: int) -> SplitSession:
        self._cleanup_session(user_id)
        s = SplitSession(user_id, file_path, original_name, total_cards)
        self._sessions[user_id] = s
        return s

    def get(self, user_id: int) -> Optional[SplitSession]:
        return self._sessions.get(user_id)

    def delete(self, user_id: int) -> None:
        self._cleanup_session(user_id)

    def _cleanup_session(self, user_id: int) -> None:
        s = self._sessions.pop(user_id, None)
        if s:
            if s.timeout_task and not s.timeout_task.done():
                s.timeout_task.cancel()
            _safe_delete(s.file_path)


# ============================================================
# SCAN SESSION MANAGER
# ============================================================

class ScanSessionData:
    """
    Holds all data produced by a /scan run.
    The source file is kept on disk for streaming exports.
    """
    __slots__ = (
        "session_id", "user_id", "file_path", "original_name",
        "created_at",
        # BIN cache: bin_str -> api response dict (or None on failure)
        "bin_cache",
        # Stats
        "total", "live", "expired_count", "duplicate_count", "unique_bins",
        # Sorted counts  (list of (name, count) descending)
        "country_list",   # (country_name, flag, count)
        "network_list",   # (network_name, count)
        "type_list",      # (card_type, count)
        "bank_list",      # (bank_name, count)
        "bin_list",       # (bin, count, flag, country, bank, network, level)
    )

    def __init__(self, session_id: str, user_id: int,
                 file_path: str, original_name: str) -> None:
        self.session_id    = session_id
        self.user_id       = user_id
        self.file_path     = file_path
        self.original_name = original_name
        self.created_at    = datetime.now()
        self.bin_cache: Dict[str, Optional[Dict]] = {}
        self.total          = 0
        self.live           = 0
        self.expired_count  = 0
        self.duplicate_count = 0
        self.unique_bins    = 0
        self.country_list:  List[Tuple] = []
        self.network_list:  List[Tuple] = []
        self.type_list:     List[Tuple] = []
        self.bank_list:     List[Tuple] = []
        self.bin_list:      List[Tuple] = []


class ScanSessionManager:
    """In-memory store for scan sessions (keyed by session_id string)."""

    def __init__(self) -> None:
        self._sessions: Dict[str, ScanSessionData] = {}
        # Also index by user_id for quick lookup
        self._by_user: Dict[int, str] = {}

    def create(self, user_id: int, file_path: str, original_name: str) -> ScanSessionData:
        # Remove any previous session for this user
        old_sid = self._by_user.get(user_id)
        if old_sid:
            self._evict(old_sid)

        sid = str(uuid.uuid4())[:8]
        s = ScanSessionData(sid, user_id, file_path, original_name)
        self._sessions[sid] = s
        self._by_user[user_id] = sid
        return s

    def get(self, session_id: str) -> Optional[ScanSessionData]:
        s = self._sessions.get(session_id)
        if s is None:
            return None
        # TTL check
        if datetime.now() - s.created_at > timedelta(hours=SCAN_SESSION_TTL_HOURS):
            self._evict(session_id)
            return None
        return s

    def delete_by_user(self, user_id: int) -> None:
        sid = self._by_user.get(user_id)
        if sid:
            self._evict(sid)

    def _evict(self, session_id: str) -> None:
        s = self._sessions.pop(session_id, None)
        if s:
            self._by_user.pop(s.user_id, None)
            _safe_delete(s.file_path)


# ============================================================
# FILE HELPERS
# ============================================================

def _safe_delete(path: str) -> None:
    try:
        if path and os.path.isfile(path):
            os.unlink(path)
    except OSError:
        pass


def _safe_rmtree(path: str) -> None:
    try:
        if path and os.path.isdir(path):
            shutil.rmtree(path, ignore_errors=True)
    except OSError:
        pass


def _count_lines(path: str) -> int:
    count = 0
    with open(path, "r", encoding="utf-8", errors="ignore") as f:
        for _ in f:
            count += 1
    return count


# ============================================================
# FILE PROCESSOR  (unchanged logic for /clean, /split, /shuffle)
# ============================================================

class FileProcessor:

    @staticmethod
    async def clean(input_path: str, output_path: str) -> Dict:
        stats = {
            "total":      0,
            "valid":      0,
            "invalid":    0,
            "duplicates": 0,
            "expired":    0,
            "incomplete": 0,
        }
        seen_hashes: set = set()
        valid_cards: List[Dict] = []

        def _validate_month(mon: str) -> bool:
            try:
                return 1 <= int(mon) <= 12
            except (ValueError, TypeError):
                return False

        def _validate_cvv(cvv: str, ctype: str) -> bool:
            if ctype == "AMEX":
                return len(cvv) == 4
            return len(cvv) == 3

        def _run() -> None:
            nonlocal stats
            with open(input_path, "r", encoding="utf-8", errors="ignore") as fin:
                for raw_line in fin:
                    stats["total"] += 1
                    extracted = CardExtractor.from_line(raw_line)

                    for card_data in extracted:
                        num = card_data["card_number"]
                        mon = card_data.get("exp_month", "")
                        yr  = card_data.get("exp_year",  "")
                        cvv = card_data.get("cvv",       "")

                        if not mon or not yr or not cvv:
                            stats["incomplete"] += 1
                            continue

                        if not _validate_month(mon):
                            stats["invalid"] += 1
                            continue

                        yr4 = normalise_year(yr)
                        h = hashlib.md5(f"{num}|{mon}|{yr4}".encode()).hexdigest()
                        if h in seen_hashes:
                            stats["duplicates"] += 1
                            continue
                        seen_hashes.add(h)

                        ok, reason, enriched = CardValidator.validate(num, mon, yr4)
                        if not ok:
                            if reason == "expired":
                                stats["expired"] += 1
                            else:
                                stats["invalid"] += 1
                            continue

                        ctype = enriched["type"]
                        if not _validate_cvv(cvv, ctype):
                            stats["invalid"] += 1
                            continue

                        enriched["cvv"]      = cvv
                        enriched["exp_year"] = yr4
                        valid_cards.append(enriched)
                        stats["valid"] += 1

                    if stats["total"] % 20_000 == 0:
                        _info(
                            f"  → {stats['total']} lines processed  "
                            f"valid={stats['valid']}  "
                            f"incomplete={stats['incomplete']}  "
                            f"dupes={stats['duplicates']}"
                        )

            valid_cards.sort(key=lambda c: c.get("priority", 99))
            with open(output_path, "w", encoding="utf-8") as fout:
                for c in valid_cards:
                    yr4 = normalise_year(c["exp_year"])
                    fout.write(
                        f"{c['card_number']}|{c['exp_month']}|{yr4}|{c['cvv']}\n"
                    )

            _ok(
                f"clean complete — valid={stats['valid']}  "
                f"incomplete={stats['incomplete']}  "
                f"dupes={stats['duplicates']}  "
                f"expired={stats['expired']}  "
                f"invalid={stats['invalid']}"
            )

        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, _run)
        return stats

    @staticmethod
    async def split(input_path: str, chunk_size: int,
                    output_dir: str) -> List[str]:
        output_files: List[str] = []

        def _run() -> None:
            chunk_num  = 1
            buf: List[str] = []
            with open(input_path, "r", encoding="utf-8", errors="ignore") as fin:
                for line in fin:
                    stripped = line.rstrip("\n\r")
                    if not stripped:
                        continue
                    buf.append(stripped + "\n")
                    if len(buf) >= chunk_size:
                        out = os.path.join(output_dir, f"split{chunk_num}.txt")
                        with open(out, "w", encoding="utf-8") as fout:
                            fout.writelines(buf)
                        _info(f"  → split{chunk_num}.txt  ({len(buf)} cards)")
                        output_files.append(out)
                        buf = []
                        chunk_num += 1
            if buf:
                out = os.path.join(output_dir, f"split{chunk_num}.txt")
                with open(out, "w", encoding="utf-8") as fout:
                    fout.writelines(buf)
                _info(f"  → split{chunk_num}.txt  ({len(buf)} cards)")
                output_files.append(out)

        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, _run)
        return output_files

    @staticmethod
    async def shuffle(input_path: str, output_path: str) -> int:
        def _run() -> int:
            with open(input_path, "r", encoding="utf-8", errors="ignore") as f:
                lines = [l for l in f if l.strip()]
            if not lines:
                return 0
            for i in range(len(lines) - 1, 0, -1):
                j = random.randint(0, i)
                lines[i], lines[j] = lines[j], lines[i]
            with open(output_path, "w", encoding="utf-8") as f:
                f.writelines(lines)
            return len(lines)

        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, _run)


# ============================================================
# BIN SERVICE
# ============================================================

class BINService:
    """
    Async BIN lookup with connection pooling, caching, and retry logic.
    A single shared aiohttp.ClientSession is reused for all requests.
    A semaphore caps concurrent lookups to BIN_CONCURRENCY.
    Each unique BIN is looked up at most once per scan.
    """

    def __init__(self) -> None:
        self._session: Optional[aiohttp.ClientSession] = None
        self._semaphore = asyncio.Semaphore(BIN_CONCURRENCY)

    async def start(self) -> None:
        connector = aiohttp.TCPConnector(limit=BIN_CONCURRENCY, ttl_dns_cache=300)
        timeout   = aiohttp.ClientTimeout(total=10)
        self._session = aiohttp.ClientSession(connector=connector, timeout=timeout)
        _info("BINService HTTP session started")

    async def stop(self) -> None:
        if self._session:
            await self._session.close()
            self._session = None
        _info("BINService HTTP session closed")

    @staticmethod
    def _parse(bin_str: str, data: Any) -> Optional[Dict]:
        """
        Normalise an API payload into the exact keys the rest of the bot uses.
        Returns None when the payload carries no usable BIN metadata.
        """
        if not isinstance(data, dict):
            return None
        if data.get("error"):
            return None

        def _txt(key: str) -> str:
            val = data.get(key)
            return val.strip() if isinstance(val, str) else ""

        brand  = _txt("brand")
        bank   = _txt("bank")
        ccode  = _txt("country").upper()
        cname  = _txt("country_name").upper()
        cflag  = _txt("country_flag")
        level  = _txt("level").upper()
        ctype  = _txt("type").upper()

        # A payload with no brand, bank and no country is not real metadata.
        if not brand and not bank and not ccode and not cname:
            return None

        return {
            "bin":          _txt("bin") or bin_str,
            "brand":        brand.upper(),
            "bank":         bank,
            "country":      ccode,
            "country_name": cname or ccode,
            "country_flag": cflag,
            "level":        level,
            "type":         ctype,
        }

    async def lookup(self, bin_str: str) -> Optional[Dict]:
        """
        Lookup a 6-digit BIN.  Returns a normalised dict or None when the API
        has no metadata for it. Never raises.
        """
        if not self._session:
            _warn("BINService.lookup called before start()")
            return None

        url = BIN_API_URL.format(bin=bin_str)
        for attempt in range(1, BIN_RETRY_ATTEMPTS + 1):
            try:
                async with self._semaphore:
                    async with self._session.get(url) as resp:
                        if resp.status == 200:
                            raw = await resp.json(content_type=None)
                            parsed = self._parse(bin_str, raw)
                            if parsed:
                                return parsed
                            _warn(f"BIN {bin_str}: 200 but no usable metadata")
                            return None
                        elif resp.status == 404:
                            return None          # BIN not found — not an error
                        elif resp.status == 429:
                            delay = float(resp.headers.get("Retry-After") or BIN_RETRY_DELAY * 3)
                            _warn(f"BIN {bin_str}: rate limited, backing off {delay:.1f}s")
                            await asyncio.sleep(delay)
                            continue
                        else:
                            _warn(f"BIN {bin_str}: HTTP {resp.status} (attempt {attempt})")
            except asyncio.TimeoutError:
                _warn(f"BIN {bin_str}: timeout (attempt {attempt})")
            except Exception as exc:
                _warn(f"BIN {bin_str}: {exc} (attempt {attempt})")

            if attempt < BIN_RETRY_ATTEMPTS:
                await asyncio.sleep(BIN_RETRY_DELAY * attempt)

        _err(f"BIN {bin_str}: all {BIN_RETRY_ATTEMPTS} attempts failed — unresolved")
        return None

    async def batch_lookup(
        self, bins: List[str], cache: Dict[str, Optional[Dict]]
    ) -> None:
        """
        Look up every BIN in `bins`, writing normalised results into `cache`.

        BINs the API did not answer are retried in a further sweep rather than
        being cached as a permanent failure, so a transient timeout or rate
        limit cannot silently strip BIN metadata from the report.
        """
        seen: Dict[str, None] = {}
        for b in bins:
            seen.setdefault(b, None)
        pending = [b for b in seen if not cache.get(b)]

        for sweep in range(1, BIN_MAX_PASSES + 1):
            if not pending:
                break
            _info(f"BINService: fetching {len(pending)} unique BINs (sweep {sweep})")
            await asyncio.gather(
                *(self._fetch_into_cache(b, cache) for b in pending),
                return_exceptions=True,
            )
            pending = [b for b in pending if not cache.get(b)]
            if pending and sweep < BIN_MAX_PASSES:
                _warn(f"BINService: {len(pending)} BINs unanswered — retrying once more")

        if pending:
            _warn(f"BINService: {len(pending)} BINs have no metadata after "
                  f"{BIN_MAX_PASSES} sweeps — they will be reported as Unknown")
        else:
            _info("BINService: every BIN resolved")

    async def _fetch_into_cache(
        self, bin_str: str, cache: Dict[str, Optional[Dict]]
    ) -> None:
        cache[bin_str] = await self.lookup(bin_str)


# ============================================================
# SCAN ENGINE
# ============================================================

class ScanEngine:
    """
    Streams a cleaned card file in two passes:
      Pass 1 — collect unique BINs + detect duplicates/expired
      (async gap) — batch BIN lookups
      Pass 2 — categorise every card line using cached BIN data
    All output goes into a ScanSessionData object.
    Never loads the whole file into RAM.
    """

    @staticmethod
    def _parse_line(line: str) -> Optional[Dict[str, str]]:
        """Parse a cleaned card line → {card, month, year, cvv, original}."""
        line = line.strip()
        if not line or len(line) < 10:
            return None
        parts = line.split("|")
        if len(parts) >= 4:
            card = re.sub(r"\D", "", parts[0])
            if len(card) >= 13:
                return {
                    "card":     card,
                    "month":    parts[1].strip(),
                    "year":     parts[2].strip(),
                    "cvv":      parts[3].strip(),
                    "original": line,
                }
        return None

    @classmethod
    async def scan(
        cls,
        session: ScanSessionData,
        bin_service: BINService,
    ) -> None:
        """Run the full scan pipeline and populate session with results."""
        loop = asyncio.get_event_loop()

        # ── Pass 1: collect BINs, duplicates, expiry ──────────
        bin_counts:     Dict[str, int]   = {}
        bin_sample:     Dict[str, str]   = {}   # bin6 → one card number
        seen_hashes:    set              = set()
        total           = 0
        expired_count   = 0
        dup_count       = 0

        def _pass1() -> None:
            nonlocal total, expired_count, dup_count
            with open(session.file_path, "r", encoding="utf-8", errors="ignore") as f:
                for raw in f:
                    parsed = cls._parse_line(raw)
                    if not parsed:
                        continue
                    total += 1

                    card  = parsed["card"]
                    month = parsed["month"]
                    year  = normalise_year(parsed["year"])

                    # Duplicate check
                    h = hashlib.md5(f"{card}|{month}|{year}".encode()).hexdigest()
                    if h in seen_hashes:
                        dup_count += 1
                        continue
                    seen_hashes.add(h)

                    # Expiry check
                    try:
                        now = datetime.now()
                        yr  = int(year) if year else 9999
                        mo  = int(month) if month else 1
                        if yr < now.year or (yr == now.year and mo < now.month):
                            expired_count += 1
                    except (ValueError, TypeError):
                        pass

                    # Count BIN
                    bin6 = card[:6]
                    bin_counts[bin6] = bin_counts.get(bin6, 0) + 1
                    bin_sample.setdefault(bin6, card)

                    if total % 20_000 == 0:
                        _info(f"  scan pass1: {total} lines, {len(bin_counts)} BINs")

        await loop.run_in_executor(None, _pass1)
        _info(f"Scan pass1 done — {total} total, {len(bin_counts)} unique BINs")

        # ── BIN lookup ─────────────────────────────────────────
        await bin_service.batch_lookup(list(bin_counts.keys()), session.bin_cache)

        # ── Pass 2: categorise ─────────────────────────────────
        country_counts: Dict[str, Dict]  = {}   # name → {flag, count}
        network_counts: Dict[str, int]   = {}
        type_counts:    Dict[str, int]   = {}
        bank_counts:    Dict[str, int]   = {}
        live            = 0
        seen_hashes2:   set              = set()

        def _pass2() -> None:
            nonlocal live
            with open(session.file_path, "r", encoding="utf-8", errors="ignore") as f:
                for raw in f:
                    parsed = cls._parse_line(raw)
                    if not parsed:
                        continue
                    card  = parsed["card"]
                    month = parsed["month"]
                    year  = normalise_year(parsed["year"])

                    # Skip duplicates (same logic as pass1)
                    h = hashlib.md5(f"{card}|{month}|{year}".encode()).hexdigest()
                    if h in seen_hashes2:
                        continue
                    seen_hashes2.add(h)

                    # Skip expired
                    try:
                        now = datetime.now()
                        yr  = int(year) if year else 9999
                        mo  = int(month) if month else 1
                        if yr < now.year or (yr == now.year and mo < now.month):
                            continue
                    except (ValueError, TypeError):
                        pass

                    live += 1
                    bin6     = card[:6]
                    bin_data = session.bin_cache.get(bin6)

                    # Network — API brand, else derived from the card number
                    if bin_data and bin_data.get("brand"):
                        network = bin_data["brand"].upper()
                    else:
                        network = CardValidator.card_type(card)
                    network_counts[network] = network_counts.get(network, 0) + 1

                    # Card type — API type, else UNKNOWN
                    ctype = (bin_data.get("type") if bin_data else None) or "UNKNOWN"
                    type_counts[ctype] = type_counts.get(ctype, 0) + 1

                    # Country — unresolved BINs land in an explicit Unknown
                    # bucket so no card is dropped and totals reconcile.
                    cname = (bin_data.get("country_name") if bin_data else None) or UNKNOWN_LABEL
                    cflag = (bin_data.get("country_flag") if bin_data else None) or UNKNOWN_FLAG
                    if cname not in country_counts:
                        country_counts[cname] = {"flag": cflag, "count": 0}
                    country_counts[cname]["count"] += 1

                    # Bank — same Unknown bucket treatment
                    bank = (bin_data.get("bank") if bin_data else None) or UNKNOWN_LABEL
                    bank_counts[bank] = bank_counts.get(bank, 0) + 1

        await loop.run_in_executor(None, _pass2)
        _info(f"Scan pass2 done — {live} live cards")

        # ── Populate session ───────────────────────────────────
        session.total           = total
        session.live            = live
        session.expired_count   = expired_count
        session.duplicate_count = dup_count
        session.unique_bins     = len(bin_counts)

        session.country_list = sorted(
            [(name, info["flag"], info["count"]) for name, info in country_counts.items()],
            key=lambda x: -x[2],
        )
        session.network_list = sorted(network_counts.items(), key=lambda x: -x[1])
        session.type_list    = sorted(type_counts.items(),    key=lambda x: -x[1])
        session.bank_list    = sorted(bank_counts.items(),    key=lambda x: -x[1])

        # bin_list: (bin, count, flag, country, bank, network, level)
        # Unresolved BINs still get their network derived locally so the row is
        # never a wall of "?".
        bl         = []
        unresolved = 0
        for bin6, cnt in sorted(bin_counts.items(), key=lambda x: -x[1]):
            bd = session.bin_cache.get(bin6)
            if bd:
                bl.append((
                    bin6, cnt,
                    bd.get("country_flag") or UNKNOWN_FLAG,
                    bd.get("country_name") or UNKNOWN_LABEL,
                    bd.get("bank") or UNKNOWN_LABEL,
                    bd.get("brand") or UNKNOWN_LABEL,
                    bd.get("level") or UNKNOWN_LABEL,
                ))
            else:
                unresolved += 1
                local_net  = CardValidator.card_type(bin_sample.get(bin6, ""))
                bl.append((
                    bin6, cnt, UNKNOWN_FLAG, UNKNOWN_LABEL, UNKNOWN_LABEL,
                    local_net, UNKNOWN_LABEL,
                ))
        session.bin_list = bl

        if unresolved:
            _warn(f"{unresolved}/{len(bin_counts)} BINs returned no metadata from the API")


# ============================================================
# EXPORT MANAGER
# ============================================================

class ExportManager:
    """
    Streams the source file and writes a filtered slice to a temp file.
    Never modifies or regenerates card lines — only filters.
    """

    @staticmethod
    def _parse_line(line: str) -> Optional[Dict[str, str]]:
        line = line.strip()
        if not line or len(line) < 10:
            return None
        parts = line.split("|")
        if len(parts) >= 4:
            card = re.sub(r"\D", "", parts[0])
            if len(card) >= 13:
                return {
                    "card":     card,
                    "month":    parts[1].strip(),
                    "year":     parts[2].strip(),
                    "original": line,
                }
        return None

    @classmethod
    async def export_slice(
        cls,
        session: ScanSessionData,
        category: str,   # 'C' country | 'N' network | 'T' type | 'B' bank | 'X' bin
        value: str,      # the filter value (country name, network name, etc.)
        output_path: str,
    ) -> int:
        """
        Write matching card lines to output_path.
        Returns count of lines written.
        """
        loop = asyncio.get_event_loop()
        count = [0]

        def _run() -> None:
            with open(session.file_path, "r", encoding="utf-8", errors="ignore") as fin, \
                 open(output_path, "w", encoding="utf-8", buffering=65536) as fout:
                for raw in fin:
                    parsed = cls._parse_line(raw)
                    if not parsed:
                        continue
                    card  = parsed["card"]
                    month = parsed["month"]
                    year  = normalise_year(parsed["year"])

                    # Skip expired
                    try:
                        now = datetime.now()
                        yr  = int(year) if year else 9999
                        mo  = int(month) if month else 1
                        if yr < now.year or (yr == now.year and mo < now.month):
                            continue
                    except (ValueError, TypeError):
                        pass

                    bin6     = card[:6]
                    bin_data = session.bin_cache.get(bin6)
                    match    = False

                    if category == "X":    # BIN
                        match = (bin6 == value)
                    elif category == "C":  # Country
                        cname = (bin_data.get("country_name") if bin_data else None) or UNKNOWN_LABEL
                        match = (cname == value)
                    elif category == "N":  # Network
                        if bin_data and bin_data.get("brand"):
                            net = bin_data["brand"].upper()
                        else:
                            net = CardValidator.card_type(card)
                        match = (net == value.upper())
                    elif category == "T":  # Type
                        ctype = (bin_data.get("type") if bin_data else None) or UNKNOWN_LABEL
                        match = (ctype.upper() == value.upper())
                    elif category == "B":  # Bank
                        bank = (bin_data.get("bank") if bin_data else None) or UNKNOWN_LABEL
                        match = (bank == value)

                    if match:
                        fout.write(parsed["original"] + "\n")
                        count[0] += 1

        await loop.run_in_executor(None, _run)
        return count[0]

    @classmethod
    async def export_by_bin_prefix(
        cls,
        file_path: str,
        bin_prefix: str,
        output_path: str,
    ) -> int:
        """Filter cards by BIN prefix (streaming, no BIN API needed)."""
        loop = asyncio.get_event_loop()
        count = [0]

        def _run() -> None:
            with open(file_path, "r", encoding="utf-8", errors="ignore") as fin, \
                 open(output_path, "w", encoding="utf-8", buffering=65536) as fout:
                for raw in fin:
                    stripped = raw.strip()
                    if not stripped:
                        continue
                    parts = stripped.split("|")
                    if parts:
                        card = re.sub(r"\D", "", parts[0])
                        if card.startswith(bin_prefix):
                            fout.write(stripped + "\n")
                            count[0] += 1

        await loop.run_in_executor(None, _run)
        return count[0]

    @classmethod
    async def export_by_bank(
        cls,
        file_path: str,
        bank_query: str,
        bin_cache: Dict[str, Optional[Dict]],
        output_path: str,
    ) -> int:
        """
        Filter cards by bank name (partial, case-insensitive).
        Uses the provided bin_cache; unknown BINs are skipped.
        """
        loop = asyncio.get_event_loop()
        count = [0]
        query_lower = bank_query.lower()

        def _run() -> None:
            with open(file_path, "r", encoding="utf-8", errors="ignore") as fin, \
                 open(output_path, "w", encoding="utf-8", buffering=65536) as fout:
                for raw in fin:
                    stripped = raw.strip()
                    if not stripped:
                        continue
                    parts = stripped.split("|")
                    if not parts:
                        continue
                    card = re.sub(r"\D", "", parts[0])
                    if len(card) < 13:
                        continue
                    bin6     = card[:6]
                    bin_data = bin_cache.get(bin6)
                    if not bin_data:
                        continue
                    bank = (bin_data.get("bank") or "").lower()
                    if query_lower in bank:
                        fout.write(stripped + "\n")
                        count[0] += 1

        await loop.run_in_executor(None, _run)
        return count[0]


# ============================================================
# PAGINATION HELPER
# ============================================================

class Paginator:
    """Build paginated InlineKeyboardMarkup for a list of (label, callback_data) pairs."""

    @staticmethod
    def build(
        items: List[Tuple[str, str]],
        page: int,
        per_page: int,
        nav_prefix: str,
        cols: int = 2,
        item_style: str | None = None,
    ) -> InlineKeyboardMarkup:
        """
        items      — list of (button_label, callback_data)
        page       — 0-based current page
        per_page   — items per page
        nav_prefix — prefix for navigation callback_data: f"{nav_prefix}:{page}"
        cols       — buttons per row
        item_style — KeyboardButtonStyle for item buttons (SUCCESS/PRIMARY/DANGER/None)
        """
        total_pages = max(1, (len(items) + per_page - 1) // per_page)
        page        = max(0, min(page, total_pages - 1))
        start       = page * per_page
        chunk       = items[start: start + per_page]

        keyboard: List[List[InlineKeyboardButton]] = []

        # Item buttons
        row: List[InlineKeyboardButton] = []
        for label, cb in chunk:
            row.append(InlineKeyboardButton(label, callback_data=cb, style=item_style))
            if len(row) >= cols:
                keyboard.append(row)
                row = []
        if row:
            keyboard.append(row)

        # Navigation row
        nav: List[InlineKeyboardButton] = []
        if page > 0:
            nav.append(InlineKeyboardButton(
                "⬅️ ᴘʀᴇᴠ",
                callback_data=f"{nav_prefix}:{page-1}",
                style=KeyboardButtonStyle.PRIMARY,
            ))
        nav.append(InlineKeyboardButton(f"📄 {page+1} / {total_pages}", callback_data="noop"))
        if page < total_pages - 1:
            nav.append(InlineKeyboardButton(
                "ɴᴇxᴛ ➡️",
                callback_data=f"{nav_prefix}:{page+1}",
                style=KeyboardButtonStyle.PRIMARY,
            ))
        keyboard.append(nav)

        # Back to main button
        keyboard.append([InlineKeyboardButton(
            "🔙 ʙᴀᴄᴋ ᴛᴏ ᴍᴇɴᴜ",
            callback_data=f"main:{nav_prefix.split(':')[1]}",
            style=KeyboardButtonStyle.DANGER,
        )])

        return InlineKeyboardMarkup(keyboard)

    @staticmethod
    def build_main(session: ScanSessionData) -> InlineKeyboardMarkup:
        """Main scan keyboard with section-navigation buttons."""
        sid = session.session_id
        rows: List[List[InlineKeyboardButton]] = []

        rows.append([
            InlineKeyboardButton(
                f"🌍 ᴄᴏᴜɴᴛʀɪᴇs  ·  {len(session.country_list)}",
                callback_data=f"list:{sid}:C:0",
                style=KeyboardButtonStyle.SUCCESS,
            )
        ])
        rows.append([
            InlineKeyboardButton(
                f"📶 ɴᴇᴛᴡᴏʀᴋs  ·  {len(session.network_list)}",
                callback_data=f"list:{sid}:N:0",
                style=KeyboardButtonStyle.PRIMARY,
            ),
            InlineKeyboardButton(
                f"💳 ᴛʏᴘᴇs  ·  {len(session.type_list)}",
                callback_data=f"list:{sid}:T:0",
                style=KeyboardButtonStyle.SUCCESS,
            ),
        ])
        rows.append([
            InlineKeyboardButton(
                f"🏦 ʙᴀɴᴋs  ·  {len(session.bank_list)}",
                callback_data=f"list:{sid}:B:0",
                style=KeyboardButtonStyle.DANGER,
            )
        ])
        rows.append([
            InlineKeyboardButton(
                f"💠 ʙɪɴs  ·  {len(session.bin_list)}",
                callback_data=f"list:{sid}:X:0",
                style=KeyboardButtonStyle.PRIMARY,
            )
        ])

        return InlineKeyboardMarkup(rows)


# ============================================================
# BOT GLOBALS
# ============================================================

db            = Database(DATABASE_PATH)
sessions      = SplitSessionManager()
scan_sessions = ScanSessionManager()
bin_service   = BINService()


def _authorised(user_id: int) -> bool:
    return True


def _deny_msg() -> str:
    return "❌ <b>unauthorised</b> — this bot is for private use only."


# ============================================================
# SCAN MESSAGE BUILDER
# ============================================================

def _build_scan_text(session: ScanSessionData) -> str:
    """Build the HTML stats message for a completed scan."""
    resolved = sum(1 for v in session.bin_cache.values() if v)
    total_bins = len(session.bin_cache)

    lines = [
        "⚡ <b>ғɪʟᴇ ᴀɴᴀʟʏsɪs</b>",
        "━━━━━━━━━━━━━━━━━━",
        f"⚡ <b>ғɪʟᴇ</b>      — <code>{session.original_name}</code>",
        f"⚡ <b>ʟɪᴠᴇ ᴄᴄs</b>  — <code>{session.live}</code>",
        f"⚡ <b>ᴇxᴘɪʀᴇᴅ</b>   — <code>{session.expired_count}</code>",
        f"⚡ <b>ᴅᴜᴘʟɪᴄᴀᴛᴇs</b> — <code>{session.duplicate_count}</code>",
        f"⚡ <b>ʙɪɴ ɪɴғᴏ</b>  — <code>{resolved}/{total_bins}</code>",
        "━━━━━━━━━━━━━━━━━━",
    ]

    # Countries
    if session.country_list:
        lines.append(f"⚡ <b>ᴄᴏᴜɴᴛʀɪᴇs</b> — {len(session.country_list)}")
        shown = session.country_list[:COUNTRIES_IN_TEXT]
        for name, flag, count in shown:
            lines.append(f"{flag} {name} — <code>{count}</code>")
        remaining = len(session.country_list) - len(shown)
        if remaining > 0:
            lines.append(f"<i>+{remaining} ᴍᴏʀᴇ…</i>")
        lines.append("━━━━━━━━━━━━━━━━━━")

    # Networks
    if session.network_list:
        lines.append("⚡ <b>ɴᴇᴛᴡᴏʀᴋs</b>")
        net_icons = {
            "VISA": "💳", "MASTERCARD": "💳", "AMEX": "💳",
            "DISCOVER": "💳", "JCB": "💳", "UNIONPAY": "💳",
            "DINERS": "💳", "BIN2": "💳",
        }
        for name, count in session.network_list:
            icon = net_icons.get(name.upper(), "•")
            lines.append(f"{icon} {name} — <code>{count}</code>")
        lines.append("━━━━━━━━━━━━━━━━━━")

    # Card types
    if session.type_list:
        lines.append("⚡ <b>ᴄᴀʀᴅ ᴛʏᴘᴇs</b>")
        type_icons = {"CREDIT": "🟢", "DEBIT": "🔵", "PREPAID": "🟡",
                      "CHARGE": "🟠", "UNKNOWN": "⚪"}
        for name, count in session.type_list:
            icon = type_icons.get(name.upper(), "•")
            lines.append(f"{icon} {name.capitalize()} — <code>{count}</code>")
        lines.append("━━━━━━━━━━━━━━━━━━")

    # BIN breakdown
    if session.bin_list:
        lines.append("⚡ <b>ʙɪɴs</b>")
        shown_rows = session.bin_list[:BIN_ROWS_IN_REPORT]
        for row in shown_rows:
            bin6, cnt, flag, country, bank, network, level = row
            bits = [f"{flag} {country}".strip(), network]
            if bank != UNKNOWN_LABEL:
                bits.append(bank)
            meta = " · ".join(b for b in bits if b and b != UNKNOWN_LABEL)
            lines.append(f"<code>{bin6}</code> — <code>{cnt}</code> — {meta}")
        remaining = len(session.bin_list) - len(shown_rows)
        if remaining > 0:
            lines.append(f"<i>+{remaining} ᴍᴏʀᴇ ʙɪɴs — ᴜᴀᴘ ᴛʜᴇ 💠 ʙɪɴs ʙᴜᴛᴛᴏɴ</i>")

    lines.append("\n<i>ᴜsᴇ ᴛʜᴇ ʙᴜᴛᴛᴏɴs ʙᴇʟᴏᴡ ᴛᴏ ᴇxᴘᴏʀᴛ sʟɪᴄᴇs</i>")
    return "\n".join(lines)


def _build_list_keyboard(session: ScanSessionData, category: str, page: int) -> InlineKeyboardMarkup:
    """Build a paginated export keyboard for one category."""
    sid = session.session_id

    if category == "C":
        items = [
            (f"{flag} {name}  ({cnt})", f"exp:{sid}:C:{i}")
            for i, (name, flag, cnt) in enumerate(session.country_list)
        ]
        nav_prefix  = f"list:{sid}:C"
        item_style  = KeyboardButtonStyle.SUCCESS
    elif category == "N":
        items = [
            (f"{name}  ({cnt})", f"exp:{sid}:N:{i}")
            for i, (name, cnt) in enumerate(session.network_list)
        ]
        nav_prefix  = f"list:{sid}:N"
        item_style  = KeyboardButtonStyle.PRIMARY
    elif category == "T":
        items = [
            (f"{name.capitalize()}  ({cnt})", f"exp:{sid}:T:{i}")
            for i, (name, cnt) in enumerate(session.type_list)
        ]
        nav_prefix  = f"list:{sid}:T"
        item_style  = KeyboardButtonStyle.SUCCESS
    elif category == "B":
        items = [
            (f"🏦 {name[:26]}  ({cnt})", f"exp:{sid}:B:{i}")
            for i, (name, cnt) in enumerate(session.bank_list)
        ]
        nav_prefix  = f"list:{sid}:B"
        item_style  = KeyboardButtonStyle.DANGER
    elif category == "X":
        items = [
            (f"{bin6}  ({cnt})  {flag}", f"exp:{sid}:X:{i}")
            for i, (bin6, cnt, flag, *_rest) in enumerate(session.bin_list)
        ]
        nav_prefix  = f"list:{sid}:X"
        item_style  = KeyboardButtonStyle.PRIMARY
    else:
        return Paginator.build_main(session)

    return Paginator.build(items, page, ITEMS_PER_PAGE, nav_prefix, cols=2, item_style=item_style)


# ============================================================
# HANDLER: /start
# ============================================================

async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    db.register_user(user.id, user.username or "", user.first_name or "")

    welcome_text = (
        f"<b><tg-emoji emoji-id=\"5989793276838812063\">💎</tg-emoji> 𝗖𝗮𝗿𝗱 𝗖𝗹𝗲𝗮𝗻𝗲𝗿</b>\n"
        f"━━━━━━━━━━━━━━━━━━━\n"
        f"<tg-emoji emoji-id=\"5289722755871162900\">👋</tg-emoji> <b>Wᴇʟᴄᴏᴍᴇ</b>, <b><a href=\"tg://user?id={user.id}\">{user.first_name}</a></b>\n\n"
        f"<tg-emoji emoji-id=\"5845947563601041174\">🧹</tg-emoji> <b>/clean</b>   ↬ <b>Exᴛʀᴀᴄᴛ & Vᴀʟɪᴅᴀᴛᴇ Cᴀʀᴅs</b>\n"
        f"<tg-emoji emoji-id=\"5208878706717636743\">✂️</tg-emoji> <b>/split</b>   ↬ <b>Sᴘʟɪᴛ Iɴᴛᴏ Cʜᴜɴᴋs</b>\n"
        f"<tg-emoji emoji-id=\"5926940334587122131\">🎲</tg-emoji> <b>/shuffle</b> ↬ <b>Ʀᴀɴᴅᴏᴍɪsᴇ Cᴀʀᴅs</b>\n"
        f"🔍 <b>/fbin</b>   ↬ <b>Fɪʟᴛᴇʀ ʙʏ BIN Pʀᴇғɪx</b>\n"
        f"🏦 <b>/bank</b>   ↬ <b>Fɪʟᴛᴇʀ ʙʏ Bᴀɴᴋ Nᴀᴍᴇ</b>\n"
        f"<tg-emoji emoji-id=\"6032808241891644148\">📊</tg-emoji> <b>/stats</b>  ↬ <b>Vɪᴇᴡ Aɴᴀʟʏᴛɪᴄs</b>\n"
        f"<tg-emoji emoji-id=\"4956337889593000947\">🚫</tg-emoji> <b>/cancel</b> ↬ <b>Aʙᴏʀᴛ Sᴇssɪᴏɴ</b>"
    )
    style_options = ["primary", "success", "danger"]
    random_style = random.choice(style_options)

    keyboard = InlineKeyboardMarkup([[
        InlineKeyboardButton("C ʟ ᴇ ᴀ ɴ - Ʀ", url=SUPPORT_CHANNEL_LINK,style= random_style,          
                icon_custom_emoji_id= "5463121572137022242",),
    ]])

    await update.message.reply_text(
        welcome_text,
        parse_mode=ParseMode.HTML,
        reply_markup=keyboard,
        disable_web_page_preview=True,
    )


# ============================================================
# HANDLER: /help
# ============================================================

async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    help_text = (
        "<b><tg-emoji emoji-id=\"5989793276838812063\">💎</tg-emoji> ʜᴇʟᴘ — ᴄᴀʀᴅ ʙᴏᴛ v5.0</b>\n\n"

        "<b><tg-emoji emoji-id=\"5845947563601041174\">🧹</tg-emoji> /clean</b>\n"
        "ʀᴇᴘʟʏ ᴛᴏ ᴀɴʏ ᴅᴜᴍᴘ ғɪʟᴇ ᴡɪᴛʜ <code>/clean</code>.\n"
        "• ᴇxᴛʀᴀᴄᴛs ᴄᴀʀᴅs ᴠɪᴀ ᴛʀᴀᴄᴋ1, ᴘɪᴘᴇ, ᴄᴏᴍᴍᴀ & ʀᴀᴡ ғᴏʀᴍᴀᴛs\n"
        "• ᴠᴀʟɪᴅᴀᴛᴇs ᴡɪᴛʜ <b>ʟᴜʜɴ + ʙɪɴ</b> ᴄʜᴇᴄᴋ\n"
        "• ʀᴇᴍᴏᴠᴇs ᴅᴜᴘʟɪᴄᴀᴛᴇs & ᴇxᴘɪʀᴇᴅ ᴇɴᴛʀɪᴇs\n"
        "• sᴏʀᴛs: ʙɪɴ2 → ᴀᴍᴇx → ᴠɪsᴀ → ᴍᴄ → ᴅɪsᴄᴏᴠᴇʀ/ᴊᴄʙ\n"
        "• ᴏᴜᴛᴘᴜᴛ ғᴏʀᴍᴀᴛ: <code>ᴄᴀʀᴅ|ᴍᴍ|ʏʏʏʏ|ᴄᴠᴠ</code>\n\n"

        "<b><tg-emoji emoji-id=\"5208878706717636743\">✂️</tg-emoji> /split</b>\n"
        "ʀᴇᴘʟʏ ᴛᴏ ᴀ ᴄʟᴇᴀɴᴇᴅ <code>.ᴛxᴛ</code> ᴡɪᴛʜ <code>/split</code>.\n"
        "• ʙᴏᴛ ᴀsᴋs ғᴏʀ ᴄʜᴜɴᴋ sɪᴢᴇ (60s ᴛɪᴍᴇᴏᴜᴛ)\n"
        "• ɴᴏ ᴢɪᴘ ᴀʀᴄʜɪᴠᴇs — ᴇᴠᴇʀ\n\n"

        "<b><tg-emoji emoji-id=\"5926940334587122131\">🎲</tg-emoji> /shuffle</b>\n"
        "ʀᴇᴘʟʏ ᴛᴏ ᴀ ᴄʟᴇᴀɴᴇᴅ <code>.ᴛxᴛ</code> ᴡɪᴛʜ <code>/shuffle</code>.\n\n"

        "<b>⚡ /scan</b>\n"
        "ʀᴇᴘʟʏ ᴛᴏ ᴀ ᴄʟᴇᴀɴᴇᴅ <code>.ᴛxᴛ</code> ᴡɪᴛʜ <code>/scan</code>.\n"
        "• ʟᴏᴏᴋs ᴜᴘ ᴇᴠᴇʀʏ ᴜɴɪǫᴜᴇ BIN ᴠɪᴀ API (ᴏɴᴄᴇ ᴇᴀᴄʜ)\n"
        "• sʜᴏᴡs ᴄᴏᴜɴᴛʀʏ, ɴᴇᴛᴡᴏʀᴋ, ᴛʏᴘᴇ, ʙᴀɴᴋ & BIN sᴛᴀᴛs\n"
        "• ᴇxᴘᴏʀᴛ ᴀɴʏ sʟɪᴄᴇ ᴀs ᴀ .ᴛxᴛ ᴠɪᴀ ɪɴʟɪɴᴇ ʙᴜᴛᴛᴏɴs\n\n"

        "<b>🔍 /fbin &lt;BIN&gt;</b>\n"
        "ʀᴇᴘʟʏ ᴛᴏ ᴀ ᴄʟᴇᴀɴᴇᴅ ғɪʟᴇ ᴡɪᴛʜ <code>/fbin 473702</code>.\n"
        "• ᴇxᴛʀᴀᴄᴛs ᴏɴʟʏ ᴄᴀʀᴅs ʙᴇɢɪɴɴɪɴɢ ᴡɪᴛʜ ᴛʜᴀᴛ BIN\n\n"

        "<b>🏦 /bank &lt;ɴᴀᴍᴇ&gt;</b>\n"
        "ʀᴇᴘʟʏ ᴛᴏ ᴀ ᴄʟᴇᴀɴᴇᴅ ғɪʟᴇ ᴡɪᴛʜ <code>/bank wells</code>.\n"
        "• ᴘᴀʀᴛɪᴀʟ, ᴄᴀsᴇ-ɪɴsᴇɴsɪᴛɪᴠᴇ ᴍᴀᴛᴄʜ\n\n"

        "<b><tg-emoji emoji-id=\"4956337889593000947\">🚫</tg-emoji> /cancel</b>\n"
        "ᴀʙᴏʀᴛ ᴀɴʏ ᴘᴇɴᴅɪɴɢ <code>/split</code> sᴇssɪᴏɴ."
    )
    await update.message.reply_text(help_text, parse_mode=ParseMode.HTML)


# ============================================================
# HANDLER: /stats
# ============================================================

async def cmd_stats(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    s = db.get_stats()
    stats_text = (
        "<tg-emoji emoji-id=\"6030687219537154393\">📊</tg-emoji> <b>Bᴏᴛ Sᴛᴀᴛɪsᴛɪᴄs</b>\n\n"
        f"• <b>Ʀᴇɢɪsᴛᴇʀᴇᴅ UsᴇƦs</b>  : <code>{s['users']}</code>\n"
        f"• <b>Cʟᴇᴀɴ OᴘᴇƦᴀᴛɪᴏɴs</b>  : <code>{s['clean_ops']}</code>\n"
        f"• <b>Sᴘʟɪᴛ OᴘᴇƦᴀᴛɪᴏɴs</b>  : <code>{s['split_ops']}</code>\n"
        f"• <b>Sʜᴜғғʟᴇ OᴘᴇƦᴀᴛɪᴏɴs</b>: <code>{s['shuffle_ops']}</code>\n"
        f"• <b>Tᴏᴛᴀʟ Vᴀʟɪᴅ CᴀƦᴅs</b> : <code>{s['total_valid']}</code>\n\n"
        f"• <b>Dᴀᴛᴀʙᴀsᴇ</b> : <tg-emoji emoji-id=\"6030687219537154393\">🟢</tg-emoji> Cᴏɴɴᴇᴄᴛᴇᴅ\n"
        f"• <b>Sᴛᴀᴛᴜs</b>   : <tg-emoji emoji-id=\"6030687219537154393\">🟢</tg-emoji> Oɴʟɪɴᴇ"
    )
    await update.message.reply_text(stats_text, parse_mode=ParseMode.HTML)


# ============================================================
# HANDLER: /clean
# ============================================================

async def cmd_clean(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user

    replied = update.message.reply_to_message
    if not replied or not replied.document:
        await update.message.reply_text(
            "<tg-emoji emoji-id=\"4956337889593000947\">❌</tg-emoji> <b>ᴜsᴀɢᴇ:</b> ʀᴇᴘʟʏ ᴛᴏ ᴀ ᴅᴜᴍᴘ ғɪʟᴇ ᴡɪᴛʜ <code>/clean</code>\n\n"
            "sᴇɴᴅ ʏᴏᴜʀ ᴅᴜᴍᴘ <code>.ᴛxᴛ</code>, ᴛʜᴇɴ ʀᴇᴘʟʏ ᴛᴏ ɪᴛ ᴡɪᴛʜ <code>/clean</code>.",
            parse_mode=ParseMode.HTML,
        )
        return

    doc = replied.document

    if doc.file_size and doc.file_size > TELEGRAM_DOWNLOAD_LIMIT:
        size_mb = doc.file_size / 1_048_576
        await update.message.reply_text(
            f"<tg-emoji emoji-id=\"4956337889593000947\">❌</tg-emoji> <b>ғɪʟᴇ ᴛᴏᴏ ʟᴀʀɢᴇ</b> — <code>{size_mb:.1f} MB</code>\n\n"
            "Tᴇʟᴇɢʀᴀᴍ's Bᴏᴛ API ᴄᴀɴ ᴏɴʟʏ ᴅᴏᴡɴʟᴏᴀᴅ ғɪʟᴇs ᴜᴘ ᴛᴏ <b>20 MB</b>.\n"
            "Pʟᴇᴀsᴇ sᴘʟɪᴛ ʏᴏᴜʀ ғɪʟᴇ ɪɴᴛᴏ ≤ 20 MB ᴄʜᴜɴᴋs ᴀɴᴅ ᴛʀʏ ᴀɢᴀɪɴ.",
            parse_mode=ParseMode.HTML,
        )
        return

    ext = Path(doc.file_name or "").suffix.lower()
    if ext not in ALLOWED_EXTENSIONS:
        await update.message.reply_text(
            f"<tg-emoji emoji-id=\"4956337889593000947\">❌</tg-emoji> ᴜɴsᴜᴘᴘᴏʀᴛᴇᴅ ғɪʟᴇ ᴛʏᴘᴇ <code>{ext}</code>.\n"
            f"ᴀʟʟᴏᴡᴇᴅ: <code>{', '.join(sorted(ALLOWED_EXTENSIONS))}</code>",
            parse_mode=ParseMode.HTML,
        )
        return

    progress = await update.message.reply_text(
        f"<tg-emoji emoji-id=\"5289722755871162900\">🔄</tg-emoji> <b>ᴄʟᴇᴀɴɪɴɢ…</b>\n\n"
        f"📄 <code>{doc.file_name}</code>\n"
        f"<tg-emoji emoji-id=\"5447421246172069841\">⏳</tg-emoji> ᴇxᴛʀᴀᴄᴛɪɴɢ ᴀɴᴅ ᴠᴀʟɪᴅᴀᴛɪɴɢ ᴄᴀʀᴅs — ᴘʟᴇᴀsᴇ ᴡᴀɪᴛ.",
        parse_mode=ParseMode.HTML,
    )

    tmp_in  = tempfile.mktemp(suffix=".txt")
    tmp_out = tempfile.mktemp(suffix="_cleaned.txt")

    try:
        tg_file = await context.bot.get_file(doc.file_id)
        await tg_file.download_to_drive(tmp_in)

        stats = await FileProcessor.clean(tmp_in, tmp_out)

        if stats["valid"] == 0:
            await progress.edit_text(
                "<tg-emoji emoji-id=\"5989793276838812063\">⚠️</tg-emoji> <b>ɴᴏ ᴠᴀʟɪᴅ ᴄᴀʀᴅs ғᴏᴜɴᴅ.</b>\n\n"
                "ᴄʜᴇᴄᴋ ᴛʜᴀᴛ ᴛʜᴇ ғɪʟᴇ ᴄᴏɴᴛᴀɪɴs ᴘᴀʏᴍᴇɴᴛ ᴄᴀʀᴅ ᴅᴀᴛᴀ ɪɴ ᴀ ʀᴇᴄᴏɢɴɪsᴇᴅ ғᴏʀᴍᴀᴛ.",
                parse_mode=ParseMode.HTML,
            )
            return

        db.log_clean(user.id, doc.file_name, stats)

        caption = (
            "<tg-emoji emoji-id=\"5463121572137022242\">✅</tg-emoji> <b>ᴄʟᴇᴀɴɪɴɢ ᴄᴏᴍᴘʟᴇᴛᴇ</b>\n\n"
            "<tg-emoji emoji-id=\"6032808241891644148\">📊</tg-emoji> <b>ʀᴇsᴜʟᴛs</b>\n"
            f"• ᴛᴏᴛᴀʟ ʟɪɴᴇs   : <code>{stats['total']}</code>\n"
            f"• <tg-emoji emoji-id=\"5463121572137022242\">✅</tg-emoji> ᴠᴀʟɪᴅ       : <code>{stats['valid']}</code>\n"
            f"• <tg-emoji emoji-id=\"4956337889593000947\">❌</tg-emoji> ɪɴᴠᴀʟɪᴅ     : <code>{stats['invalid']}</code>\n"
            f"• <tg-emoji emoji-id=\"5289722755871162900\">🔄</tg-emoji> ᴅᴜᴘʟɪᴄᴀᴛᴇs : <code>{stats['duplicates']}</code>\n"
            f"• <tg-emoji emoji-id=\"5447421246172069841\">⏰</tg-emoji> ᴇxᴘɪʀᴇᴅ    : <code>{stats['expired']}</code>\n"
            f"• <tg-emoji emoji-id=\"5989793276838812063\">⚠️</tg-emoji> ɪɴᴄᴏᴍᴘʟᴇᴛᴇ : <code>{stats['incomplete']}</code>\n\n"
            "💾 <code>ᴄʟᴇᴀɴᴇᴅ.ᴛxᴛ</code>\n\n"
            "<i>ʀᴇᴘʟʏ ᴡɪᴛʜ /split, /shuffle, /scan, /fbin, or /bank ᴛᴏ ᴄᴏɴᴛɪɴᴜᴇ</i>"
        )

        with open(tmp_out, "rb") as fout:
            await update.message.reply_document(
                document=fout,
                filename="cleaned.txt",
                caption=caption,
                parse_mode=ParseMode.HTML,
            )

        await progress.delete()

    except TelegramError as e:
        _err(f"Telegram error in /clean: {e}")
        await progress.edit_text(
            f"<tg-emoji emoji-id=\"4956337889593000947\">❌</tg-emoji> ᴛᴇʟᴇɢʀᴀᴍ ᴇʀʀᴏʀ: <code>{e}</code>",
            parse_mode=ParseMode.HTML,
        )
    except Exception as e:
        _err(f"/clean error: {e}")
        await progress.edit_text(
            f"<tg-emoji emoji-id=\"4956337889593000947\">❌</tg-emoji> ᴇʀʀᴏʀ: <code>{e}</code>",
            parse_mode=ParseMode.HTML,
        )
    finally:
        _safe_delete(tmp_in)
        _safe_delete(tmp_out)


# ============================================================
# HANDLER: /split  (ConversationHandler entry point)
# ============================================================

async def cmd_split(update: Update,
                    context: ContextTypes.DEFAULT_TYPE) -> int:
    user = update.effective_user

    replied = update.message.reply_to_message
    if not replied or not replied.document:
        await update.message.reply_text(
            "<tg-emoji emoji-id=\"4956337889593000947\">❌</tg-emoji> <b>ᴜsᴀɢᴇ:</b> ʀᴇᴘʟʏ ᴛᴏ ᴀ ᴄʟᴇᴀɴᴇᴅ <code>.ᴛxᴛ</code> ғɪʟᴇ ᴡɪᴛʜ <code>/split</code>",
            parse_mode=ParseMode.HTML,
        )
        return ConversationHandler.END

    doc = replied.document

    if not (doc.file_name or "").endswith(".txt"):
        await update.message.reply_text(
            "<tg-emoji emoji-id=\"4956337889593000947\">❌</tg-emoji> ᴘʟᴇᴀsᴇ ʀᴇᴘʟʏ ᴛᴏ ᴀ <code>.ᴛxᴛ</code> ғɪʟᴇ ᴄᴏɴᴛᴀɪɴɪɴɢ ᴄʟᴇᴀɴᴇᴅ ᴄᴀʀᴅs.",
            parse_mode=ParseMode.HTML,
        )
        return ConversationHandler.END

    if doc.file_size and doc.file_size > TELEGRAM_DOWNLOAD_LIMIT:
        size_mb = doc.file_size / 1_048_576
        await update.message.reply_text(
            f"<tg-emoji emoji-id=\"4956337889593000947\">❌</tg-emoji> <b>ғɪʟᴇ ᴛᴏᴏ ʟᴀʀɢᴇ</b> — <code>{size_mb:.1f} MB</code>\n\n"
            "Tᴇʟᴇɢʀᴀᴍ's Bᴏᴛ API ᴄᴀɴ ᴏɴʟʏ ᴅᴏᴡɴʟᴏᴀᴅ ғɪʟᴇs ᴜᴘ ᴛᴏ <b>20 MB</b>.\n"
            "Pʟᴇᴀsᴇ sᴘʟɪᴛ ʏᴏᴜʀ ғɪʟᴇ ɪɴᴛᴏ ≤ 20 MB ᴄʜᴜɴᴋs ᴀɴᴅ ᴛʀʏ ᴀɢᴀɪɴ.",
            parse_mode=ParseMode.HTML,
        )
        return ConversationHandler.END

    tmp_in = tempfile.mktemp(suffix=".txt")
    try:
        tg_file = await context.bot.get_file(doc.file_id)
        await tg_file.download_to_drive(tmp_in)
    except Exception as e:
        _err(f"Download failed in /split: {e}")
        _safe_delete(tmp_in)
        await update.message.reply_text(
            f"<tg-emoji emoji-id=\"4956337889593000947\">❌</tg-emoji> ᴄᴏᴜʟᴅ ɴᴏᴛ ᴅᴏᴡɴʟᴏᴀᴅ ғɪʟᴇ: <code>{e}</code>",
            parse_mode=ParseMode.HTML,
        )
        return ConversationHandler.END

    loop = asyncio.get_event_loop()
    total_cards = await loop.run_in_executor(
        None,
        lambda: sum(1 for l in open(tmp_in, encoding="utf-8", errors="ignore") if l.strip()),
    )

    session = sessions.create(user.id, tmp_in, doc.file_name, total_cards)

    prompt = await update.message.reply_text(
        f"<b><tg-emoji emoji-id=\"5208878706717636743\">✂️</tg-emoji> sᴘʟɪᴛ — ғɪʟᴇ ᴅᴇᴛᴇᴄᴛᴇᴅ</b>\n"
        f"▸ <b>ɴᴀᴍᴇ</b>  · <code>{doc.file_name}</code>\n"
        f"▸ <b>ᴄᴀʀᴅs</b> · <code>{total_cards}</code>\n\n"
        f"<b>ᴄʜᴜɴᴋ sɪᴢᴇ</b>\n"
        f"▸ <b>ʀᴇᴘʟʏ</b> · ᴡɪᴛʜ ᴀ ɴᴜᴍʙᴇʀ\n"
        f"▸ <b>ᴇx</b>    · <code>1000</code>\n\n"
        f"<i>ᴀᴜᴛᴏ-ᴄᴀɴᴄᴇʟ ɪɴ {SPLIT_TIMEOUT_SECONDS}s</i>",
        parse_mode=ParseMode.HTML,
    )

    async def _auto_cancel() -> None:
        await asyncio.sleep(SPLIT_TIMEOUT_SECONDS)
        if sessions.get(user.id):
            sessions.delete(user.id)
            try:
                await prompt.edit_text(
                    "<tg-emoji emoji-id=\"5447421246172069841\">⏱</tg-emoji> <b>sᴇssɪᴏɴ ᴇxᴘɪʀᴇᴅ.</b>\n\nᴘʟᴇᴀsᴇ ᴜsᴇ <code>/split</code> ᴀɢᴀɪɴ.",
                    parse_mode=ParseMode.HTML,
                )
            except TelegramError:
                pass
            _info(f"Split session auto-cancelled for user {user.id}")

    task = asyncio.create_task(_auto_cancel())
    session.timeout_task = task

    return WAITING_FOR_SPLIT_SIZE


# ============================================================
# HANDLER: split — receive chunk size
# ============================================================

async def split_receive_size(update: Update,
                             context: ContextTypes.DEFAULT_TYPE) -> int:
    user = update.effective_user

    raw = update.message.text.strip().replace(",", "").replace(".", "")
    try:
        chunk_size = int(raw)
    except ValueError:
        await update.message.reply_text(
            "<tg-emoji emoji-id=\"4956337889593000947\">❌</tg-emoji> ɪɴᴠᴀʟɪᴅ ɪɴᴘᴜᴛ — ᴘʟᴇᴀsᴇ sᴇɴᴅ ᴀ ᴡʜᴏʟᴇ ɴᴜᴍʙᴇʀ.\n"
            "ᴇxᴀᴍᴘʟᴇ: <code>1000</code>",
            parse_mode=ParseMode.HTML,
        )
        return WAITING_FOR_SPLIT_SIZE

    if chunk_size < 1:
        await update.message.reply_text(
            "<tg-emoji emoji-id=\"4956337889593000947\">❌</tg-emoji> ᴄʜᴜɴᴋ sɪᴢᴇ ᴍᴜsᴛ ʙᴇ ᴀᴛ ʟᴇᴀsᴛ <code>1</code>.",
            parse_mode=ParseMode.HTML,
        )
        return WAITING_FOR_SPLIT_SIZE

    if chunk_size > MAX_CHUNK_SIZE:
        await update.message.reply_text(
            f"<tg-emoji emoji-id=\"4956337889593000947\">❌</tg-emoji> ᴄʜᴜɴᴋ sɪᴢᴇ ᴛᴏᴏ ʟᴀʀɢᴇ — ᴍᴀxɪᴍᴜᴍ ɪs <code>{MAX_CHUNK_SIZE}</code>.",
            parse_mode=ParseMode.HTML,
        )
        return WAITING_FOR_SPLIT_SIZE

    session = sessions.get(user.id)
    if not session:
        await update.message.reply_text(
            "<tg-emoji emoji-id=\"4956337889593000947\">❌</tg-emoji> sᴇssɪᴏɴ ᴇxᴘɪʀᴇᴅ. ᴘʟᴇᴀsᴇ ᴜsᴇ <code>/split</code> ᴀɢᴀɪɴ.",
            parse_mode=ParseMode.HTML,
        )
        return ConversationHandler.END

    if session.timeout_task and not session.timeout_task.done():
        session.timeout_task.cancel()

    progress = await update.message.reply_text(
        f"<tg-emoji emoji-id=\"5289722755871162900\">🔄</tg-emoji> <b>sᴘʟɪᴛᴛɪɴɢ…</b>\n\n"
        f"📄 <code>{session.original_name}</code>\n"
        f"📦 ᴄʜᴜɴᴋ sɪᴢᴇ: <code>{chunk_size}</code>\n"
        f"<tg-emoji emoji-id=\"5447421246172069841\">⏳</tg-emoji> ᴘʀᴏᴄᴇssɪɴɢ — ᴘʟᴇᴀsᴇ ᴡᴀɪᴛ…",
        parse_mode=ParseMode.HTML,
    )

    output_dir = tempfile.mkdtemp()
    try:
        output_files = await FileProcessor.split(
            session.file_path, chunk_size, output_dir
        )

        num_chunks = len(output_files)
        db.log_split(user.id, session.original_name,
                     session.total_cards, chunk_size, num_chunks)

        for idx, path in enumerate(output_files, 1):
            card_count = await asyncio.get_event_loop().run_in_executor(
                None, _count_lines, path
            )
            with open(path, "rb") as fchunk:
                await update.message.reply_document(
                    document=fchunk,
                    filename=f"split{idx}.txt",
                    caption=(
                        f"📦 <b>sᴘʟɪᴛ {idx} / {num_chunks}</b>\n"
                        f"<tg-emoji emoji-id=\"5463121572137022242\">💳</tg-emoji> ᴄᴀʀᴅs: <code>{card_count}</code>"
                    ),
                    parse_mode=ParseMode.HTML,
                )

        await update.message.reply_text(
            f"<tg-emoji emoji-id=\"5463121572137022242\">✅</tg-emoji> <b>sᴘʟɪᴛ ᴄᴏᴍᴘʟᴇᴛᴇ</b>\n\n"
            f"• <b>sᴏᴜʀᴄᴇ</b>      : <code>{session.original_name}</code>\n"
            f"• <b>ᴛᴏᴛᴀʟ ᴄᴀʀᴅs</b> : <code>{session.total_cards}</code>\n"
            f"• <b>ᴄʜᴜɴᴋ sɪᴢᴇ</b>  : <code>{chunk_size}</code>\n"
            f"• <b>ғɪʟᴇs sᴇɴᴛ</b>  : <code>{num_chunks}</code>",
            parse_mode=ParseMode.HTML,
        )

        await progress.delete()

    except Exception as e:
        _err(f"Split processing error: {e}")
        await progress.edit_text(
            f"<tg-emoji emoji-id=\"4956337889593000947\">❌</tg-emoji> sᴘʟɪᴛ ғᴀɪʟᴇᴅ: <code>{e}</code>",
            parse_mode=ParseMode.HTML,
        )
    finally:
        sessions.delete(user.id)
        _safe_rmtree(output_dir)

    return ConversationHandler.END


# ============================================================
# HANDLER: /cancel
# ============================================================

async def cmd_cancel(update: Update,
                     context: ContextTypes.DEFAULT_TYPE) -> int:
    user_id = update.effective_user.id
    had_session = sessions.get(user_id) is not None
    sessions.delete(user_id)

    if had_session:
        await update.message.reply_text(
            "<tg-emoji emoji-id=\"5463121572137022242\">✅</tg-emoji> <b>sᴘʟɪᴛ sᴇssɪᴏɴ ᴄᴀɴᴄᴇʟʟᴇᴅ.</b>",
            parse_mode=ParseMode.HTML,
        )
    else:
        await update.message.reply_text(
            "<tg-emoji emoji-id=\"5989793276838812063\">ℹ️</tg-emoji> ɴᴏ ᴀᴄᴛɪᴠᴇ sᴇssɪᴏɴ ᴛᴏ ᴄᴀɴᴄᴇʟ.",
            parse_mode=ParseMode.HTML,
        )

    return ConversationHandler.END


# ============================================================
# HANDLER: /shuffle
# ============================================================

async def cmd_shuffle(update: Update,
                      context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user

    replied = update.message.reply_to_message
    if not replied or not replied.document:
        await update.message.reply_text(
            "<tg-emoji emoji-id=\"4956337889593000947\">❌</tg-emoji> <b>ᴜsᴀɢᴇ:</b> ʀᴇᴘʟʏ ᴛᴏ ᴀ ᴄʟᴇᴀɴᴇᴅ <code>.ᴛxᴛ</code> ғɪʟᴇ ᴡɪᴛʜ <code>/shuffle</code>",
            parse_mode=ParseMode.HTML,
        )
        return

    doc = replied.document

    if not (doc.file_name or "").endswith(".txt"):
        await update.message.reply_text(
            "<tg-emoji emoji-id=\"4956337889593000947\">❌</tg-emoji> ᴘʟᴇᴀsᴇ ʀᴇᴘʟʏ ᴛᴏ ᴀ <code>.ᴛxᴛ</code> ғɪʟᴇ ᴄᴏɴᴛᴀɪɴɪɴɢ ᴄʟᴇᴀɴᴇᴅ ᴄᴀʀᴅs.",
            parse_mode=ParseMode.HTML,
        )
        return

    if doc.file_size and doc.file_size > TELEGRAM_DOWNLOAD_LIMIT:
        size_mb = doc.file_size / 1_048_576
        await update.message.reply_text(
            f"<tg-emoji emoji-id=\"4956337889593000947\">❌</tg-emoji> <b>ғɪʟᴇ ᴛᴏᴏ ʟᴀʀɢᴇ</b> — <code>{size_mb:.1f} MB</code>\n\n"
            "Tᴇʟᴇɢʀᴀᴍ's Bᴏᴛ API ᴄᴀɴ ᴏɴʟʏ ᴅᴏᴡɴʟᴏᴀᴅ ғɪʟᴇs ᴜᴘ ᴛᴏ <b>20 MB</b>.\n"
            "Pʟᴇᴀsᴇ sᴘʟɪᴛ ʏᴏᴜʀ ғɪʟᴇ ɪɴᴛᴏ ≤ 20 MB ᴄʜᴜɴᴋs ᴀɴᴅ ᴛʀʏ ᴀɢᴀɪɴ.",
            parse_mode=ParseMode.HTML,
        )
        return

    progress = await update.message.reply_text(
        f"<tg-emoji emoji-id=\"5926940334587122131\">🎲</tg-emoji> <b>sʜᴜғғʟɪɴɢ…</b>\n\n"
        f"📄 <code>{doc.file_name}</code>\n"
        f"<tg-emoji emoji-id=\"5289722755871162900\">🔄</tg-emoji> ʀᴀɴᴅᴏᴍɪsɪɴɢ ᴄᴀʀᴅ ᴏʀᴅᴇʀ…",
        parse_mode=ParseMode.HTML,
    )

    tmp_in  = tempfile.mktemp(suffix=".txt")
    tmp_out = tempfile.mktemp(suffix="_shuffled.txt")

    try:
        tg_file = await context.bot.get_file(doc.file_id)
        await tg_file.download_to_drive(tmp_in)

        count = await FileProcessor.shuffle(tmp_in, tmp_out)

        if count == 0:
            await progress.edit_text(
                "<tg-emoji emoji-id=\"5989793276838812063\">⚠️</tg-emoji> ғɪʟᴇ ɪs ᴇᴍᴘᴛʏ — ɴᴏᴛʜɪɴɢ ᴛᴏ sʜᴜғғʟᴇ.",
                parse_mode=ParseMode.HTML,
            )
            return

        db.log_shuffle(user.id, doc.file_name, count)

        with open(tmp_out, "rb") as fout:
            await update.message.reply_document(
                document=fout,
                filename="shuffled.txt",
                caption=(
                    f"<tg-emoji emoji-id=\"5463121572137022242\">✅</tg-emoji> <b>sʜᴜғғʟᴇ ᴄᴏᴍᴘʟᴇᴛᴇ</b>\n\n"
                    f"• <b>ᴄᴀʀᴅs sʜᴜғғʟᴇᴅ</b>: <code>{count}</code>\n"
                    "• <b>ᴏʀᴅᴇʀ</b>: ғᴜʟʟʏ ʀᴀɴᴅᴏᴍɪsᴇᴅ"
                ),
                parse_mode=ParseMode.HTML,
            )

        await progress.delete()

    except TelegramError as e:
        _err(f"Telegram error in /shuffle: {e}")
        await progress.edit_text(
            f"<tg-emoji emoji-id=\"4956337889593000947\">❌</tg-emoji> ᴛᴇʟᴇɢʀᴀᴍ ᴇʀʀᴏʀ: <code>{e}</code>",
            parse_mode=ParseMode.HTML,
        )
    except Exception as e:
        _err(f"/shuffle error: {e}")
        await progress.edit_text(
            f"<tg-emoji emoji-id=\"4956337889593000947\">❌</tg-emoji> ᴇʀʀᴏʀ: <code>{e}</code>",
            parse_mode=ParseMode.HTML,
        )
    finally:
        _safe_delete(tmp_in)
        _safe_delete(tmp_out)


# ============================================================
# HANDLER: /broadcast  (owner only)
# ============================================================

async def cmd_broadcast(update: Update,
                        context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user

    if user.id != OWNER_ID:
        await update.message.reply_text(
            "<tg-emoji emoji-id=\"4956337889593000947\">❌</tg-emoji> <b>ᴏᴡɴᴇʀ ᴏɴʟʏ</b> — ᴛʜɪs ᴄᴏᴍᴍᴀɴᴅ ɪs ʀᴇsᴛʀɪᴄᴛᴇᴅ.",
            parse_mode=ParseMode.HTML,
        )
        return

    text = " ".join(context.args).strip() if context.args else ""
    if not text:
        await update.message.reply_text(
            "<tg-emoji emoji-id=\"4956337889593000947\">❌</tg-emoji> <b>ᴜsᴀɢᴇ:</b> <code>/broadcast ʏᴏᴜʀ ᴍᴇssᴀɢᴇ ʜᴇʀᴇ</code>",
            parse_mode=ParseMode.HTML,
        )
        return

    user_ids = db.get_all_user_ids()
    total    = len(user_ids)

    if total == 0:
        await update.message.reply_text(
            "<tg-emoji emoji-id=\"5989793276838812063\">⚠️</tg-emoji> ɴᴏ ʀᴇɢɪsᴛᴇʀᴇᴅ ᴜsᴇʀs ʏᴇᴛ.",
            parse_mode=ParseMode.HTML,
        )
        return

    progress = await update.message.reply_text(
        f"<tg-emoji emoji-id=\"5447421246172069841\">📢</tg-emoji> <b>ʙʀᴏᴀᴅᴄᴀsᴛɪɴɢ…</b>\n\n"
        f"sᴇɴᴅɪɴɢ ᴛᴏ <code>{total}</code> ᴜsᴇʀ(s) — ᴘʟᴇᴀsᴇ ᴡᴀɪᴛ.",
        parse_mode=ParseMode.HTML,
    )

    sent = failed = blocked = 0
    for uid in user_ids:
        try:
            await context.bot.send_message(chat_id=uid, text=text, parse_mode=ParseMode.HTML)
            sent += 1
        except TelegramError as e:
            err_str = str(e).lower()
            if "blocked" in err_str or "deactivated" in err_str or "chat not found" in err_str:
                blocked += 1
            else:
                failed += 1
        await asyncio.sleep(0.04)

    await progress.edit_text(
        f"<tg-emoji emoji-id=\"5463121572137022242\">✅</tg-emoji> <b>ʙʀᴏᴀᴅᴄᴀsᴛ ᴄᴏᴍᴘʟᴇᴛᴇ</b>\n\n"
        f"• <b>ᴛᴏᴛᴀʟ ᴜsᴇʀs</b>  : <code>{total}</code>\n"
        f"• <b>sᴇɴᴛ</b>         : <code>{sent}</code>\n"
        f"• <b>ʙʟᴏᴄᴋᴇᴅ/ʟᴇғᴛ</b> : <code>{blocked}</code>\n"
        f"• <b>ғᴀɪʟᴇᴅ</b>       : <code>{failed}</code>",
        parse_mode=ParseMode.HTML,
    )
    _ok(f"Broadcast done — sent={sent}  blocked={blocked}  failed={failed}")


# ============================================================
# SCAN CORE  (shared by /scan and the automatic upload handler)
# ============================================================

async def run_scan(update: Update, context: ContextTypes.DEFAULT_TYPE, doc: Any) -> None:
    """
    Download a card file, scan every BIN via the API and post the report
    with the export keyboard. Assumes the document is already validated.
    """
    user = update.effective_user

    progress = await update.message.reply_text(
        "⚡ <b>sᴄᴀɴɴɪɴɢ…</b>\n\n"
        f"📄 <code>{doc.file_name}</code>\n"
        "<tg-emoji emoji-id=\"5447421246172069841\">⏳</tg-emoji> ᴄᴏʟʟᴇᴄᴛɪɴɢ BINs — ᴘʟᴇᴀsᴇ ᴡᴀɪᴛ…",
        parse_mode=ParseMode.HTML,
    )

    tmp_in = tempfile.mktemp(suffix=".txt")
    try:
        tg_file = await context.bot.get_file(doc.file_id)
        await tg_file.download_to_drive(tmp_in)
    except Exception as e:
        _err(f"Download failed during scan: {e}")
        _safe_delete(tmp_in)
        await progress.edit_text(
            f"<tg-emoji emoji-id=\"4956337889593000947\">❌</tg-emoji> ᴄᴏᴜʟᴅ ɴᴏᴛ ᴅᴏᴡɴʟᴏᴀᴅ ғɪʟᴇ: <code>{e}</code>",
            parse_mode=ParseMode.HTML,
        )
        return

    # Create session — takes ownership of tmp_in
    session = scan_sessions.create(user.id, tmp_in, doc.file_name or "file.txt")

    try:
        await progress.edit_text(
            "⚡ <b>sᴄᴀɴɴɪɴɢ…</b>\n\n"
            f"📄 <code>{doc.file_name}</code>\n"
            "<tg-emoji emoji-id=\"5289722755871162900\">🔄</tg-emoji> ʟᴏᴏᴋɪɴɢ ᴜᴘ BINs ᴠɪᴀ API…",
            parse_mode=ParseMode.HTML,
        )

        await ScanEngine.scan(session, bin_service)

        if session.live == 0 and session.total == 0:
            scan_sessions.delete_by_user(user.id)
            await progress.edit_text(
                "<tg-emoji emoji-id=\"5989793276838812063\">⚠️</tg-emoji> ɴᴏ ᴄᴀʀᴅ ʟɪɴᴇs ᴅᴇᴛᴇᴄᴛᴇᴅ. Is ᴛʜɪs ᴀ ᴄʟᴇᴀɴᴇᴅ ᴄᴀʀᴅ ғɪʟᴇ?",
                parse_mode=ParseMode.HTML,
            )
            return

        text     = _build_scan_text(session)
        keyboard = Paginator.build_main(session)

        await progress.delete()
        await update.message.reply_text(
            text,
            parse_mode=ParseMode.HTML,
            reply_markup=keyboard,
        )
        _ok(f"Scan complete for user {user.id} — session {session.session_id}")

    except Exception as e:
        _err(f"Scan error: {e}")
        scan_sessions.delete_by_user(user.id)
        await progress.edit_text(
            f"<tg-emoji emoji-id=\"4956337889593000947\">❌</tg-emoji> ᴇʀʀᴏʀ ᴅᴜʀɪɴɢ sᴄᴀɴ: <code>{e}</code>",
            parse_mode=ParseMode.HTML,
        )


# ============================================================
# HANDLER: /scan
# ============================================================

async def cmd_scan(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    replied = update.message.reply_to_message
    if not replied or not replied.document:
        await update.message.reply_text(
            "⚡ <b>ɴᴏᴛᴋs ɴᴇᴄᴛ:</b> ᴊᴜsᴛ sᴇɴᴅ ᴛʜᴇ ᴄʟᴇᴀɴᴇᴅ <code>.ᴛxᴛ</code> ғɪʟᴇ — ɪᴛ sᴄᴀɴs ᴀᴜᴛᴏᴍᴀᴛɪᴄᴀʟʟʏ.",
            parse_mode=ParseMode.HTML,
        )
        return

    doc = replied.document

    if not (doc.file_name or "").endswith(".txt"):
        await update.message.reply_text(
            "<tg-emoji emoji-id=\"4956337889593000947\">❌</tg-emoji> ᴘʟᴇᴀsᴇ ʀᴇᴘʟʏ ᴛᴏ ᴀ <code>.ᴛxᴛ</code> ᴄʟᴇᴀɴᴇᴅ ᴄᴀʀᴅ ғɪʟᴇ.",
            parse_mode=ParseMode.HTML,
        )
        return

    if doc.file_size and doc.file_size > TELEGRAM_DOWNLOAD_LIMIT:
        size_mb = doc.file_size / 1_048_576
        await update.message.reply_text(
            f"<tg-emoji emoji-id=\"4956337889593000947\">❌</tg-emoji> <b>ғɪʟᴇ ᴛᴏᴏ ʟᴀʀɢᴇ</b> — <code>{size_mb:.1f} MB</code>\n\n"
            "Tᴇʟᴇɢʀᴀᴍ's Bᴏᴛ API ᴄᴀɴ ᴏɴʟʏ ᴅᴏᴡɴʟᴏᴀᴅ ғɪʟᴇs ᴜᴘ ᴛᴏ <b>20 MB</b>.\n"
            "Pʟᴇᴀsᴇ sᴘʟɪᴛ ʏᴏᴜʀ ғɪʟᴇ ɪɴᴛᴏ ≤ 20 MB ᴄʜᴜɴᴋs ᴀɴᴅ ᴛʀʏ ᴀɢᴀɪɴ.",
            parse_mode=ParseMode.HTML,
        )
        return

    await run_scan(update, context, doc)


# ============================================================
# HANDLER: automatic scan on file upload
# ============================================================

async def auto_scan(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Any card file the user sends is scanned immediately."""
    doc = update.message.document
    name = (doc.file_name or "").lower()

    if not name.endswith(".txt"):
        await update.message.reply_text(
            "<tg-emoji emoji-id=\"4956337889593000947\">❌</tg-emoji> "
            f"sᴄᴀɴ ᴏɴʟʏ ᴡᴏʀᴋs ᴡɪᴛʜ <code>.txt</code> ғɪʟᴇs, sᴇɴᴅ ᴏɴᴇ ᴡɪᴛʜ ᴛʜᴇ sᴀᴍᴇ ᴇxᴛᴇɴsɪᴏɴ.",
            parse_mode=ParseMode.HTML,
        )
        return

    if doc.file_size and doc.file_size > TELEGRAM_DOWNLOAD_LIMIT:
        size_mb = doc.file_size / 1_048_576
        await update.message.reply_text(
            f"<tg-emoji emoji-id=\"4956337889593000947\">❌</tg-emoji> <b>ғɪʟᴇ ᴛᴏᴏ ʟᴀʀɢᴇ</b> — <code>{size_mb:.1f} MB</code>\n\n"
            "Tᴇʟᴇɢʀᴀᴍ's Bᴏᴛ API ᴄᴀɴ ᴏɴʟʏ ᴅᴏᴡɴʟᴏᴀᴅ ғɪʟᴇs ᴜᴘ ᴛᴏ <b>20 MB</b>.\n"
            "Pʟᴇᴀsᴇ sᴘʟɪᴛ ʏᴏᴜʀ ғɪʟᴇ ɪɴᴛᴏ ≤ 20 MB ᴄʜᴜɴᴋs ᴀɴᴅ ᴛʀʏ ᴀɢᴀɪɴ.",
            parse_mode=ParseMode.HTML,
        )
        return

    await run_scan(update, context, doc)


# ============================================================
# HANDLER: /fbin  (NEW)
# ============================================================

async def cmd_fbin(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    replied = update.message.reply_to_message
    if not replied or not replied.document:
        await update.message.reply_text(
            "🔍 <b>ᴜsᴀɢᴇ:</b> ʀᴇᴘʟʏ ᴛᴏ ᴀ ᴄʟᴇᴀɴᴇᴅ <code>.ᴛxᴛ</code> ᴡɪᴛʜ <code>/fbin 473702</code>",
            parse_mode=ParseMode.HTML,
        )
        return

    if not context.args:
        await update.message.reply_text(
            "🔍 <b>ᴜsᴀɢᴇ:</b> <code>/fbin 473702</code>  (ʀᴇᴘʟʏ ᴛᴏ ᴀ ᴄʟᴇᴀɴᴇᴅ ᴛxᴛ)",
            parse_mode=ParseMode.HTML,
        )
        return

    bin_prefix = re.sub(r"\D", "", context.args[0])
    if len(bin_prefix) < 4:
        await update.message.reply_text(
            "<tg-emoji emoji-id=\"4956337889593000947\">❌</tg-emoji> ᴘʟᴇᴀsᴇ ᴘʀᴏᴠɪᴅᴇ ᴀᴛ ʟᴇᴀsᴛ 4 ᴅɪɢɪᴛs.",
            parse_mode=ParseMode.HTML,
        )
        return

    doc = replied.document
    if not (doc.file_name or "").endswith(".txt"):
        await update.message.reply_text(
            "<tg-emoji emoji-id=\"4956337889593000947\">❌</tg-emoji> ᴘʟᴇᴀsᴇ ʀᴇᴘʟʏ ᴛᴏ ᴀ <code>.ᴛxᴛ</code> ғɪʟᴇ.",
            parse_mode=ParseMode.HTML,
        )
        return

    if doc.file_size and doc.file_size > TELEGRAM_DOWNLOAD_LIMIT:
        size_mb = doc.file_size / 1_048_576
        await update.message.reply_text(
            f"<tg-emoji emoji-id=\"4956337889593000947\">❌</tg-emoji> <b>ғɪʟᴇ ᴛᴏᴏ ʟᴀʀɢᴇ</b> — <code>{size_mb:.1f} MB</code>\n\n"
            "Tᴇʟᴇɢʀᴀᴍ's Bᴏᴛ API ᴄᴀɴ ᴏɴʟʏ ᴅᴏᴡɴʟᴏᴀᴅ ғɪʟᴇs ᴜᴘ ᴛᴏ <b>20 MB</b>.\n"
            "Pʟᴇᴀsᴇ sᴘʟɪᴛ ʏᴏᴜʀ ғɪʟᴇ ɪɴᴛᴏ ≤ 20 MB ᴄʜᴜɴᴋs ᴀɴᴅ ᴛʀʏ ᴀɢᴀɪɴ.",
            parse_mode=ParseMode.HTML,
        )
        return

    progress = await update.message.reply_text(
        f"🔍 <b>ғɪʟᴛᴇʀɪɴɢ BIN <code>{bin_prefix}</code>…</b>",
        parse_mode=ParseMode.HTML,
    )

    tmp_in  = tempfile.mktemp(suffix=".txt")
    tmp_out = tempfile.mktemp(suffix=f"_{bin_prefix}.txt")

    try:
        tg_file = await context.bot.get_file(doc.file_id)
        await tg_file.download_to_drive(tmp_in)

        count = await ExportManager.export_by_bin_prefix(tmp_in, bin_prefix, tmp_out)

        if count == 0:
            await progress.edit_text(
                f"<tg-emoji emoji-id=\"5989793276838812063\">⚠️</tg-emoji> ɴᴏ ᴄᴀʀᴅs ғᴏᴜɴᴅ ғᴏʀ BIN <code>{bin_prefix}</code>.",
                parse_mode=ParseMode.HTML,
            )
            return

        out_name = f"{bin_prefix}.txt"
        with open(tmp_out, "rb") as fout:
            await update.message.reply_document(
                document=fout,
                filename=out_name,
                caption=(
                    f"🔍 <b>BIN ғɪʟᴛᴇʀ ᴄᴏᴍᴘʟᴇᴛᴇ</b>\n\n"
                    f"• <b>BIN</b>   : <code>{bin_prefix}</code>\n"
                    f"• <b>ᴄᴀʀᴅs</b> : <code>{count}</code>\n"
                    f"• <b>ғɪʟᴇ</b>  : <code>{out_name}</code>"
                ),
                parse_mode=ParseMode.HTML,
            )

        await progress.delete()

    except Exception as e:
        _err(f"/fbin error: {e}")
        await progress.edit_text(
            f"<tg-emoji emoji-id=\"4956337889593000947\">❌</tg-emoji> ᴇʀʀᴏʀ: <code>{e}</code>",
            parse_mode=ParseMode.HTML,
        )
    finally:
        _safe_delete(tmp_in)
        _safe_delete(tmp_out)


# ============================================================
# HANDLER: /bank  (NEW)
# ============================================================

async def cmd_bank(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    replied = update.message.reply_to_message
    if not replied or not replied.document:
        await update.message.reply_text(
            "🏦 <b>ᴜsᴀɢᴇ:</b> ʀᴇᴘʟʏ ᴛᴏ ᴀ ᴄʟᴇᴀɴᴇᴅ <code>.ᴛxᴛ</code> ᴡɪᴛʜ <code>/bank wells</code>",
            parse_mode=ParseMode.HTML,
        )
        return

    if not context.args:
        await update.message.reply_text(
            "🏦 <b>ᴜsᴀɢᴇ:</b> <code>/bank wells</code>  (ᴄᴀsᴇ-ɪɴsᴇɴsɪᴛɪᴠᴇ ᴘᴀʀᴛɪᴀʟ ᴍᴀᴛᴄʜ)",
            parse_mode=ParseMode.HTML,
        )
        return

    bank_query = " ".join(context.args).strip()
    if len(bank_query) < 2:
        await update.message.reply_text(
            "<tg-emoji emoji-id=\"4956337889593000947\">❌</tg-emoji> ᴘʟᴇᴀsᴇ ᴘʀᴏᴠɪᴅᴇ ᴀᴛ ʟᴇᴀsᴛ 2 ᴄʜᴀʀᴀᴄᴛᴇʀs.",
            parse_mode=ParseMode.HTML,
        )
        return

    doc = replied.document
    if not (doc.file_name or "").endswith(".txt"):
        await update.message.reply_text(
            "<tg-emoji emoji-id=\"4956337889593000947\">❌</tg-emoji> ᴘʟᴇᴀsᴇ ʀᴇᴘʟʏ ᴛᴏ ᴀ <code>.ᴛxᴛ</code> ғɪʟᴇ.",
            parse_mode=ParseMode.HTML,
        )
        return

    if doc.file_size and doc.file_size > TELEGRAM_DOWNLOAD_LIMIT:
        size_mb = doc.file_size / 1_048_576
        await update.message.reply_text(
            f"<tg-emoji emoji-id=\"4956337889593000947\">❌</tg-emoji> <b>ғɪʟᴇ ᴛᴏᴏ ʟᴀʀɢᴇ</b> — <code>{size_mb:.1f} MB</code>\n\n"
            "Tᴇʟᴇɢʀᴀᴍ's Bᴏᴛ API ᴄᴀɴ ᴏɴʟʏ ᴅᴏᴡɴʟᴏᴀᴅ ғɪʟᴇs ᴜᴘ ᴛᴏ <b>20 MB</b>.\n"
            "Pʟᴇᴀsᴇ sᴘʟɪᴛ ʏᴏᴜʀ ғɪʟᴇ ɪɴᴛᴏ ≤ 20 MB ᴄʜᴜɴᴋs ᴀɴᴅ ᴛʀʏ ᴀɢᴀɪɴ.",
            parse_mode=ParseMode.HTML,
        )
        return

    progress = await update.message.reply_text(
        f"🏦 <b>sᴇᴀʀᴄʜɪɴɢ ʙᴀɴᴋ:</b> <code>{bank_query}</code>\n"
        "<tg-emoji emoji-id=\"5289722755871162900\">🔄</tg-emoji> ʟᴏᴀᴅɪɴɢ BIN ᴅᴀᴛᴀ…",
        parse_mode=ParseMode.HTML,
    )

    tmp_in  = tempfile.mktemp(suffix=".txt")
    tmp_out = tempfile.mktemp(suffix="_bank.txt")

    try:
        tg_file = await context.bot.get_file(doc.file_id)
        await tg_file.download_to_drive(tmp_in)

        # Collect unique BINs first (streaming)
        loop = asyncio.get_event_loop()
        unique_bins: set = set()

        def _collect_bins() -> None:
            with open(tmp_in, "r", encoding="utf-8", errors="ignore") as f:
                for raw in f:
                    parts = raw.strip().split("|")
                    if parts:
                        card = re.sub(r"\D", "", parts[0])
                        if len(card) >= 13:
                            unique_bins.add(card[:6])

        await loop.run_in_executor(None, _collect_bins)

        # Build local cache for this operation
        local_cache: Dict[str, Optional[Dict]] = {}
        await bin_service.batch_lookup(list(unique_bins), local_cache)

        await progress.edit_text(
            f"🏦 <b>sᴇᴀʀᴄʜɪɴɢ ʙᴀɴᴋ:</b> <code>{bank_query}</code>\n"
            "<tg-emoji emoji-id=\"5289722755871162900\">🔄</tg-emoji> ғɪʟᴛᴇʀɪɴɢ ᴄᴀʀᴅs…",
            parse_mode=ParseMode.HTML,
        )

        count = await ExportManager.export_by_bank(
            tmp_in, bank_query, local_cache, tmp_out
        )

        if count == 0:
            await progress.edit_text(
                f"<tg-emoji emoji-id=\"5989793276838812063\">⚠️</tg-emoji> ɴᴏ ᴄᴀʀᴅs ғᴏᴜɴᴅ ғᴏʀ ʙᴀɴᴋ: <code>{bank_query}</code>",
                parse_mode=ParseMode.HTML,
            )
            return

        safe_name = re.sub(r'[^\w\s-]', '', bank_query)[:40].strip()
        out_name  = f"{safe_name}.txt" if safe_name else "bank.txt"

        with open(tmp_out, "rb") as fout:
            await update.message.reply_document(
                document=fout,
                filename=out_name,
                caption=(
                    f"🏦 <b>ʙᴀɴᴋ ғɪʟᴛᴇʀ ᴄᴏᴍᴘʟᴇᴛᴇ</b>\n\n"
                    f"• <b>ǫᴜᴇʀʏ</b> : <code>{bank_query}</code>\n"
                    f"• <b>ᴄᴀʀᴅs</b> : <code>{count}</code>\n"
                    f"• <b>ғɪʟᴇ</b>  : <code>{out_name}</code>"
                ),
                parse_mode=ParseMode.HTML,
            )

        await progress.delete()

    except Exception as e:
        _err(f"/bank error: {e}")
        await progress.edit_text(
            f"<tg-emoji emoji-id=\"4956337889593000947\">❌</tg-emoji> ᴇʀʀᴏʀ: <code>{e}</code>",
            parse_mode=ParseMode.HTML,
        )
    finally:
        _safe_delete(tmp_in)
        _safe_delete(tmp_out)


# ============================================================
# CALLBACK QUERY HANDLER  (NEW — scan export + pagination)
# ============================================================

async def callback_query_handler(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    query = update.callback_query
    await query.answer()

    data = query.data or ""

    # ── noop ───────────────────────────────────────────────────
    if data == "noop":
        return

    parts = data.split(":", 3)
    action = parts[0] if parts else ""

    # ── main:{sid} — restore main keyboard ────────────────────
    if action == "main" and len(parts) >= 2:
        sid     = parts[1]
        session = scan_sessions.get(sid)
        if not session:
            await query.answer("⚠️ sᴇssɪᴏɴ ᴇxᴘɪʀᴇᴅ — ᴘʟᴇᴀsᴇ ʀᴜɴ /scan ᴀɢᴀɪɴ.", show_alert=True)
            return
        keyboard = Paginator.build_main(session)
        try:
            await query.edit_message_reply_markup(reply_markup=keyboard)
        except TelegramError:
            pass
        return

    # ── list:{sid}:{cat}:{page} — show category list ──────────
    if action == "list" and len(parts) >= 4:
        sid      = parts[1]
        category = parts[2]
        try:
            page = int(parts[3])
        except ValueError:
            page = 0

        session = scan_sessions.get(sid)
        if not session:
            await query.answer("⚠️ sᴇssɪᴏɴ ᴇxᴘɪʀᴇᴅ — ᴘʟᴇᴀsᴇ ʀᴜɴ /scan ᴀɢᴀɪɴ.", show_alert=True)
            return

        keyboard = _build_list_keyboard(session, category, page)
        try:
            await query.edit_message_reply_markup(reply_markup=keyboard)
        except TelegramError:
            pass
        return

    # ── exp:{sid}:{cat}:{idx} — export a slice ────────────────
    if action == "exp" and len(parts) >= 4:
        sid      = parts[1]
        category = parts[2]
        try:
            idx = int(parts[3])
        except ValueError:
            await query.answer("❌ ɪɴᴠᴀʟɪᴅ ʀᴇǫᴜᴇsᴛ.", show_alert=True)
            return

        session = scan_sessions.get(sid)
        if not session:
            await query.answer("⚠️ sᴇssɪᴏɴ ᴇxᴘɪʀᴇᴅ — ᴘʟᴇᴀsᴇ ʀᴜɴ /scan ᴀɢᴀɪɴ.", show_alert=True)
            return

        # Resolve value and filename from index
        value    = ""
        out_name = "export.txt"

        try:
            if category == "C":
                name, flag, count = session.country_list[idx]
                value    = name
                safe     = re.sub(r'[^\w\s-]', '', name)[:40].strip()
                out_name = f"{safe}.txt" if safe else "country.txt"
            elif category == "N":
                name, count = session.network_list[idx]
                value    = name
                out_name = f"{name}.txt"
            elif category == "T":
                name, count = session.type_list[idx]
                value    = name
                out_name = f"{name.capitalize()}.txt"
            elif category == "B":
                name, count = session.bank_list[idx]
                value    = name
                safe     = re.sub(r'[^\w\s-]', '', name)[:40].strip()
                out_name = f"{safe}.txt" if safe else "bank.txt"
            elif category == "X":
                row      = session.bin_list[idx]
                value    = row[0]    # bin6
                out_name = f"{value}.txt"
        except IndexError:
            await query.answer("❌ ɪᴛᴇᴍ ɴᴏᴛ ғᴏᴜɴᴅ.", show_alert=True)
            return

        await query.answer(f"⚡ ᴇxᴘᴏʀᴛɪɴɢ {out_name}…")

        tmp_out = tempfile.mktemp(suffix=".txt")
        try:
            count = await ExportManager.export_slice(session, category, value, tmp_out)

            if count == 0:
                await query.message.reply_text(
                    f"<tg-emoji emoji-id=\"5989793276838812063\">⚠️</tg-emoji> ɴᴏ ᴄᴀʀᴅs ғᴏᴜɴᴅ ғᴏʀ <code>{value}</code>.",
                    parse_mode=ParseMode.HTML,
                )
                return

            with open(tmp_out, "rb") as fout:
                await query.message.reply_document(
                    document=fout,
                    filename=out_name,
                    caption=(
                        f"⚡ <b>ᴇxᴘᴏʀᴛ ᴄᴏᴍᴘʟᴇᴛᴇ</b>\n\n"
                        f"• <b>ᴄᴀᴛᴇɢᴏʀʏ</b> : <code>{value}</code>\n"
                        f"• <b>ᴄᴀʀᴅs</b>    : <code>{count}</code>\n"
                        f"• <b>ғɪʟᴇ</b>     : <code>{out_name}</code>"
                    ),
                    parse_mode=ParseMode.HTML,
                )

        except Exception as e:
            _err(f"Export error: {e}")
            await query.message.reply_text(
                f"<tg-emoji emoji-id=\"4956337889593000947\">❌</tg-emoji> ᴇxᴘᴏʀᴛ ғᴀɪʟᴇᴅ: <code>{e}</code>",
                parse_mode=ParseMode.HTML,
            )
        finally:
            _safe_delete(tmp_out)
        return


# ============================================================
# GLOBAL ERROR HANDLER
# ============================================================

async def error_handler(update: object,
                        context: ContextTypes.DEFAULT_TYPE) -> None:
    _err(f"Unhandled exception: {context.error}")
    if isinstance(update, Update) and update.effective_message:
        try:
            await update.effective_message.reply_text(
                "<tg-emoji emoji-id=\"4956337889593000947\">❌</tg-emoji> ᴀɴ ᴜɴᴇxᴘᴇᴄᴛᴇᴅ ᴇʀʀᴏʀ ᴏᴄᴄᴜʀʀᴇᴅ. ᴘʟᴇᴀsᴇ ᴛʀʏ ᴀɢᴀɪɴ.",
                parse_mode=ParseMode.HTML,
            )
        except TelegramError:
            pass


# ============================================================
# LIFECYCLE: aiohttp startup / shutdown
# ============================================================

async def _on_startup(application: Any) -> None:
    await bin_service.start()
    _ok("Bot started — BINService ready")


async def _on_shutdown(application: Any) -> None:
    await bin_service.stop()
    _ok("Bot stopped — BINService closed")


# ============================================================
# MAIN
# ============================================================

def main() -> None:
    print(_C.CYN)
    print("╔═══════════════════════════════════════════════════════╗")
    print("║      ULTIMATE CARD CLEANER & SPLITTER BOT  v5.0       ║")
    print("║                   by Just-Lisa                        ║")
    print("╚═══════════════════════════════════════════════════════╝")
    print(_C.RST)

    if not BOT_TOKEN or BOT_TOKEN == "YOUR_BOT_TOKEN_HERE":
        _err("Set BOT_TOKEN as an environment variable before starting.")
        return

    if OWNER_ID == 0:
        _err("Set OWNER_ID as an environment variable before starting.")
        return

    _info(f"Token   : {BOT_TOKEN[:10]}…")
    _info(f"Owner   : {OWNER_ID}")
    _info(f"Admins  : {ADMIN_IDS}")
    _info(f"Timeout : {SPLIT_TIMEOUT_SECONDS}s")

    app = (
        Application.builder()
        .token(BOT_TOKEN)
        .post_init(_on_startup)
        .post_shutdown(_on_shutdown)
        .build()
    )

    # Split uses ConversationHandler for the two-step interaction
    split_conv = ConversationHandler(
        entry_points=[CommandHandler("split", cmd_split)],
        states={
            WAITING_FOR_SPLIT_SIZE: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, split_receive_size),
            ],
        },
        fallbacks=[CommandHandler("cancel", cmd_cancel)],
    )

    app.add_handler(CommandHandler("start",     cmd_start))
    app.add_handler(CommandHandler("help",      cmd_help))
    app.add_handler(CommandHandler("stats",     cmd_stats))
    app.add_handler(CommandHandler("clean",     cmd_clean))
    app.add_handler(CommandHandler("shuffle",   cmd_shuffle))
    app.add_handler(CommandHandler("cancel",    cmd_cancel))
    app.add_handler(CommandHandler("broadcast", cmd_broadcast))
    app.add_handler(CommandHandler("scan",      cmd_scan))
    app.add_handler(CommandHandler("fbin",      cmd_fbin))
    app.add_handler(CommandHandler("bank",      cmd_bank))
    app.add_handler(split_conv)
    app.add_handler(CallbackQueryHandler(callback_query_handler))
    # Any uploaded card file is scanned automatically.
    # Registered in its own group (1) so it never blocks commands or the
    # split conversation, which live in group 0.
    app.add_handler(MessageHandler(filters.Document.ALL, auto_scan), group=1)
    app.add_error_handler(error_handler)

    _ok("Bot is running — press Ctrl+C to stop\n")

    try:
        app.run_polling(allowed_updates=Update.ALL_TYPES)
    except KeyboardInterrupt:
        _warn("Stopped by user")
    except Exception as e:
        _err(f"Fatal: {e}")


if __name__ == "__main__":
    main()
