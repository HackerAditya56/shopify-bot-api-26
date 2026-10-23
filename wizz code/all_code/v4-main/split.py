from live_emoji import plan_badge, dev_badge
#!/usr/bin/env python3
"""
╔═══════════════════════════════════════════════════════════════════════════════╗
║          CARD CLEANER & SPLITTER MODULE  v4.0  —  aiogram edition            ║
║              /clean  /split  /shuffle  /cancel                               ║
╚═══════════════════════════════════════════════════════════════════════════════╝
"""

# ============================================================
# STANDARD LIBRARY
# ============================================================
import os
import re
import uuid
import sqlite3
import tempfile
import random
import hashlib
import asyncio
import logging
import shutil
from contextlib import contextmanager
from collections import OrderedDict
from datetime import datetime
from html import escape
from pathlib import Path
from typing import Dict, List, Optional, Tuple

# ============================================================
# AIOGRAM IMPORTS
# ============================================================
from aiogram import Router, F, types
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import FSInputFile

# ============================================================
# LOCAL IMPORTS  (mirror main.py pattern)
# ============================================================
from database import is_gate_enabled, get_user_credits, update_credits
from sub import get_premium_status

# ============================================================
# CONFIGURATION
# ============================================================
MAX_FILE_SIZE: int      = 100 * 1024 * 1024        # 100 MB
ALLOWED_EXTENSIONS      = {".txt", ".dump", ".csv", ".cc", ".cards", ".data"}
SPLIT_TIMEOUT_SECONDS   = 60
DATABASE_PATH           = "split_bot.db"
MAX_CHUNK_SIZE          = 500_000

# Admins — keep in sync with main.py ADMIN_IDS
ADMIN_IDS: set = {8462705169}

# ============================================================
# LOGGING
# ============================================================
logger = logging.getLogger(__name__)

# ============================================================
# FSM STATES
# ============================================================
class SplitStates(StatesGroup):
    waiting_for_size = State()

# ============================================================
# ROUTER
# ============================================================
router = Router()

# ============================================================
# UI HELPERS  — match main.py visual style
# ============================================================
DEV_LINK = dev_badge()
SEP       = "━━━━━━━━━━━━━━━━━━━━━━"


def _user_link(user: types.User) -> str:
    name = escape(user.first_name or "User")
    return f'<a href="tg://user?id={user.id}">{name}</a>'


def _is_admin(user_id: int) -> bool:
    return user_id in ADMIN_IDS


# ============================================================
# CARD VALIDATOR
# ============================================================
class CardValidator:
    _PATTERNS: "OrderedDict[str, re.Pattern]" = OrderedDict([
        ("BIN2",       re.compile(r"^2[0-9]{15}$")),
        ("AMEX",       re.compile(r"^3[47][0-9]{13}$")),
        ("VISA",       re.compile(r"^4[0-9]{12}(?:[0-9]{3})?$")),
        ("MASTERCARD", re.compile(
            r"^(5[1-5][0-9]{14}|2(2[2-9][0-9]{12}|[3-6][0-9]{13}"
            r"|7[0-1][0-9]{12}|720[0-9]{12}))$"
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
        cls, number: str, exp_month: str = "", exp_year: str = "",
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
                yr  = int(exp_year)
                if yr < 100:
                    yr += 2000
                mo = int(exp_month)
                if yr < now.year or (yr == now.year and mo < now.month):
                    return False, "expired", None
            except (ValueError, TypeError):
                pass
        return True, "valid", {
            "card_number": number,
            "type":        ctype,
            "bin":         number[:6],
            "last4":       number[-4:],
            "exp_month":   exp_month.zfill(2) if exp_month else "",
            "exp_year":    exp_year,
            "priority":    cls._PRIORITY.get(ctype, 99),
        }


# ============================================================
# CARD EXTRACTOR
# ============================================================
class CardExtractor:
    _TRACK1 = re.compile(r"%B(\d{13,19})\^[^\^]+\^(\d{2})(\d{2})", re.I)
    _TRACK2 = re.compile(r";(\d{13,19})=(\d{2})(\d{2})\d{3}(\d{3,4})?", re.I)
    _FULL   = re.compile(
        r"(\d{13,19})[\s|:/,]+(\d{1,2})[\s|:/,]+(\d{2,4})[\s|:/,]+(\d{3,4})"
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
def _normalise_year(year: str) -> str:
    if not year:
        return ""
    try:
        y = int(year)
        return str(2000 + y) if y < 100 else str(y)
    except ValueError:
        return year


# ============================================================
# DATABASE  (SQLite audit log — local only)
# ============================================================
class _Database:
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
                CREATE TABLE IF NOT EXISTS clean_ops (
                    id          INTEGER PRIMARY KEY AUTOINCREMENT,
                    op_id       TEXT UNIQUE,
                    user_id     INTEGER,
                    input_name  TEXT,
                    total_lines INTEGER,
                    valid       INTEGER,
                    invalid     INTEGER,
                    duplicates  INTEGER,
                    expired     INTEGER,
                    ts          TEXT
                )
            """)
            c.execute("""
                CREATE TABLE IF NOT EXISTS split_ops (
                    id          INTEGER PRIMARY KEY AUTOINCREMENT,
                    op_id       TEXT UNIQUE,
                    user_id     INTEGER,
                    source_name TEXT,
                    total_cards INTEGER,
                    chunk_size  INTEGER,
                    chunks      INTEGER,
                    ts          TEXT
                )
            """)
            c.execute("""
                CREATE TABLE IF NOT EXISTS shuffle_ops (
                    id          INTEGER PRIMARY KEY AUTOINCREMENT,
                    op_id       TEXT UNIQUE,
                    user_id     INTEGER,
                    source_name TEXT,
                    card_count  INTEGER,
                    ts          TEXT
                )
            """)

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

    def log_split(self, user_id: int, source: str,
                  total: int, chunk: int, chunks: int) -> None:
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
            clean_ops   = c.execute("SELECT COUNT(*) FROM clean_ops").fetchone()[0]
            split_ops   = c.execute("SELECT COUNT(*) FROM split_ops").fetchone()[0]
            shuffle_ops = c.execute("SELECT COUNT(*) FROM shuffle_ops").fetchone()[0]
            total_valid = c.execute(
                "SELECT COALESCE(SUM(valid),0) FROM clean_ops"
            ).fetchone()[0]
        return {
            "clean_ops":   clean_ops,
            "split_ops":   split_ops,
            "shuffle_ops": shuffle_ops,
            "total_valid": total_valid,
        }


db = _Database(DATABASE_PATH)


# ============================================================
# IN-MEMORY SPLIT SESSION MANAGER
# ============================================================
class _SplitSession:
    __slots__ = ("user_id", "file_path", "original_name",
                 "total_cards", "timeout_task")

    def __init__(self, user_id: int, file_path: str,
                 original_name: str, total_cards: int) -> None:
        self.user_id       = user_id
        self.file_path     = file_path
        self.original_name = original_name
        self.total_cards   = total_cards
        self.timeout_task: Optional[asyncio.Task] = None


class _SplitSessionManager:
    def __init__(self) -> None:
        self._sessions: Dict[int, _SplitSession] = {}

    def create(self, user_id: int, file_path: str,
               original_name: str, total_cards: int) -> _SplitSession:
        self._cleanup(user_id)
        s = _SplitSession(user_id, file_path, original_name, total_cards)
        self._sessions[user_id] = s
        return s

    def get(self, user_id: int) -> Optional[_SplitSession]:
        return self._sessions.get(user_id)

    def delete(self, user_id: int) -> None:
        self._cleanup(user_id)

    def _cleanup(self, user_id: int) -> None:
        s = self._sessions.pop(user_id, None)
        if s:
            if s.timeout_task and not s.timeout_task.done():
                s.timeout_task.cancel()
            _safe_delete(s.file_path)


sessions = _SplitSessionManager()


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
        for line in f:
            if line.strip():
                count += 1
    return count


# ============================================================
# FILE PROCESSOR
# ============================================================
class FileProcessor:

    @staticmethod
    async def clean(input_path: str, output_path: str) -> Dict:
        stats = {
            "total": 0, "valid": 0, "invalid": 0,
            "duplicates": 0, "expired": 0, "incomplete": 0,
        }
        seen_hashes: set    = set()
        valid_cards: List[Dict] = []

        def _validate_month(mon: str) -> bool:
            try:
                return 1 <= int(mon) <= 12
            except (ValueError, TypeError):
                return False

        def _validate_cvv(cvv: str, ctype: str) -> bool:
            return len(cvv) == 4 if ctype == "AMEX" else len(cvv) == 3

        def _run() -> None:
            with open(input_path, "r", encoding="utf-8", errors="ignore") as fin:
                for raw_line in fin:
                    stats["total"] += 1
                    for card_data in CardExtractor.from_line(raw_line):
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

                        yr4 = _normalise_year(yr)
                        h   = hashlib.md5(f"{num}|{mon}|{yr4}".encode()).hexdigest()
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

            valid_cards.sort(key=lambda c: c.get("priority", 99))
            with open(output_path, "w", encoding="utf-8") as fout:
                for c in valid_cards:
                    fout.write(
                        f"{c['card_number']}|"
                        f"{c['exp_month']}|"
                        f"{_normalise_year(c['exp_year'])}|"
                        f"{c['cvv']}\n"
                    )

        await asyncio.get_event_loop().run_in_executor(None, _run)
        return stats

    @staticmethod
    async def split(input_path: str, chunk_size: int,
                    output_dir: str) -> List[str]:
        output_files: List[str] = []

        def _run() -> None:
            chunk_num = 1
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
                        output_files.append(out)
                        buf = []
                        chunk_num += 1
            if buf:
                out = os.path.join(output_dir, f"split{chunk_num}.txt")
                with open(out, "w", encoding="utf-8") as fout:
                    fout.writelines(buf)
                output_files.append(out)

        await asyncio.get_event_loop().run_in_executor(None, _run)
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

        return await asyncio.get_event_loop().run_in_executor(None, _run)


# ============================================================
# GATE CHECK HELPER
# ============================================================
async def _gate_check(gate: str, message: types.Message) -> bool:
    enabled = await asyncio.to_thread(is_gate_enabled, gate)
    if not enabled:
        await message.reply(
            f"🚧 <b>𝗖𝗮𝗿𝗱 𝗧𝗼𝗼𝗹𝘀 ({gate}) 𝗮𝗿𝗲 𝘂𝗻𝗱𝗲𝗿 𝗺𝗮𝗶𝗻𝘁𝗲𝗻𝗮𝗻𝗰𝗲.</b>\n"
            "𝗜𝘁 𝘄𝗶𝗹𝗹 𝗯𝗲 𝗿𝗲𝘀𝘁𝗼𝗿𝗲𝗱 𝘀𝗼𝗼𝗻.",
            parse_mode="HTML",
        )
    return enabled


# ============================================================
# HANDLER: /clean
# ============================================================
@router.message(Command("clean"))
async def clean_command(message: types.Message) -> None:
    user    = message.from_user
    user_id = user.id

    if not await _gate_check("clean", message):
        return

    # Credits check (free users must have credits)
    is_premium, _ = await asyncio.to_thread(get_premium_status, user_id)
    credits       = await asyncio.to_thread(get_user_credits, user_id)
    if not is_premium and (credits is None or credits <= 0):
        await message.reply(
            "❌ <b>Insufficient Credits!</b>\n\n"
            "You have <b>0 credits</b> left.\n"
            "Please recharge to continue.",
            parse_mode="HTML",
        )
        return

    replied = message.reply_to_message
    if not replied or not replied.document:
        await message.reply(
            f"{SEP}\n"
            "❌ <b>𝗜𝗻𝘃𝗮𝗹𝗶𝗱 𝗨𝘀𝗮𝗴𝗲</b>\n\n"
            "𝗥𝗲𝗽𝗹𝘆 𝘁𝗼 𝗮 𝗱𝘂𝗺𝗽 𝗳𝗶𝗹𝗲 𝘄𝗶𝘁𝗵 <code>/clean</code>\n\n"
            "𝗘𝘅: Send your <code>.txt</code> dump → reply with <code>/clean</code>\n"
            f"{SEP}",
            parse_mode="HTML",
        )
        return

    doc = replied.document
    ext = Path(doc.file_name or "").suffix.lower()

    if doc.file_size > MAX_FILE_SIZE:
        await message.reply(
            f"❌ <b>File too large.</b>\n"
            f"Maximum allowed: <b>{MAX_FILE_SIZE // 1_048_576} MB</b>",
            parse_mode="HTML",
        )
        return

    if ext not in ALLOWED_EXTENSIONS:
        await message.reply(
            f"❌ <b>Unsupported file type</b> <code>{ext}</code>\n"
            f"Allowed: <code>{', '.join(sorted(ALLOWED_EXTENSIONS))}</code>",
            parse_mode="HTML",
        )
        return

    progress = await message.reply(
        f"<pre><code>⏳ 𝙇𝙤𝙖𝙙𝙞𝙣𝙜 𝘿𝙪𝙢𝙥 𝙁𝙞𝙡𝙚...</code></pre>\n"
        f"𝗙𝗶𝗹𝗲 ➠ <b>{doc.file_name}</b>\n"
        f"𝗦𝗶𝘇𝗲 ➠ <b>{doc.file_size:,} bytes</b>\n"
        f"𝗦𝘁𝗮𝘁𝘂𝘀 ➠ <b>Extracting & validating cards...</b>",
        parse_mode="HTML",
    )

    tmp_in  = tempfile.mktemp(suffix=".txt")
    tmp_out = tempfile.mktemp(suffix="_cleaned.txt")

    try:
        tg_file = await message.bot.get_file(doc.file_id)
        await message.bot.download_file(tg_file.file_path, destination=tmp_in)

        stats = await FileProcessor.clean(tmp_in, tmp_out)

        if stats["valid"] == 0:
            await progress.edit_text(
                f"{SEP}\n"
                "⚠️ <b>𝗡𝗼 𝗩𝗮𝗹𝗶𝗱 𝗖𝗮𝗿𝗱𝘀 𝗙𝗼𝘂𝗻𝗱</b>\n\n"
                "Check that the file contains payment card data\n"
                "in a recognised format.\n"
                f"{SEP}",
                parse_mode="HTML",
            )
            return

        db.log_clean(user_id, doc.file_name, stats)

        # Credit deduction for free users
        if not is_premium:
            new_bal = max(0, (credits or 0) - 1)
            await asyncio.to_thread(update_credits, user_id, new_bal)
        else:
            new_bal = credits or 0

        caption = (
            f"{SEP}\n"
            f"<a href='https://t.me/broken_wiz'>✧</a> <b>𝗖𝗹𝗲𝗮𝗻𝗶𝗻𝗴 𝗖𝗼𝗺𝗽𝗹𝗲𝘁𝗲</b>\n"
            f"{SEP}\n"
            f"<a href='https://t.me/broken_wiz'>✧</a> 𝗧𝗼𝘁𝗮𝗹 𝗟𝗶𝗻𝗲𝘀 ➠ <b>{stats['total']:,}</b>\n"
            f"<a href='https://t.me/broken_wiz'>✧</a> 𝗩𝗮𝗹𝗶𝗱 ➠ <b>{stats['valid']:,}</b>\n"
            #f"❌ 𝗜𝗻𝘃𝗮𝗹𝗶𝗱    ➠ <code>{stats['invalid']:,}</code>\n"
            #f"🔄 𝗗𝘂𝗽𝗹𝗶𝗰𝗮𝘁𝗲𝘀 ➠ <code>{stats['duplicates']:,}</code>\n"
            #f"⏰ 𝗘𝘅𝗽𝗶𝗿𝗲𝗱    ➠ <code>{stats['expired']:,}</code>\n"
            #f"⚠️ 𝗜𝗻𝗰𝗼𝗺𝗽𝗹𝗲𝘁𝗲 ➠ <code>{stats['incomplete']:,}</code>\n"
            #f"{SEP}\n"
            f"<a href='https://t.me/broken_wiz'>✧</a> 𝗖𝗿𝗲𝗱𝗶𝘁𝘀 𝗟𝗲𝗳𝘁 ➠ <code>{new_bal}</code>\n"
            f"<a href='https://t.me/broken_wiz'>✧</a> 𝗨𝘀𝗲𝗿 ➠ {_user_link(user)}\n"
            f"<a href='https://t.me/broken_wiz'>✧</a> 𝗗𝗲𝘃 ➠ {DEV_LINK}\n"
            f"{SEP}\n"
            
        )

        await message.reply_document(
            document=FSInputFile(tmp_out, filename="cleaned.txt"),
            caption=caption,
            parse_mode="HTML",
        )
        await progress.delete()

    except Exception as e:
        logger.error(f"[CLEAN] error: {e}")
        await progress.edit_text(
            f"❌ <b>Error:</b> <code>{e}</code>", parse_mode="HTML"
        )
    finally:
        _safe_delete(tmp_in)
        _safe_delete(tmp_out)


# ============================================================
# HANDLER: /split  (step 1 — entry point)
# ============================================================
@router.message(Command("split"))
async def split_command(message: types.Message, state: FSMContext) -> None:
    user    = message.from_user
    user_id = user.id

    if not await _gate_check("clean", message):
        return

    is_premium, _ = await asyncio.to_thread(get_premium_status, user_id)
    credits       = await asyncio.to_thread(get_user_credits, user_id)
    if not is_premium and (credits is None or credits <= 0):
        await message.reply(
            "❌ <b>Insufficient Credits!</b>\n\n"
            "You have <b>0 credits</b> left.\n"
            "Please recharge to continue.",
            parse_mode="HTML",
        )
        return

    replied = message.reply_to_message
    if not replied or not replied.document:
        await message.reply(
            f"{SEP}\n"
            "❌ <b>𝗜𝗻𝘃𝗮𝗹𝗶𝗱 𝗨𝘀𝗮𝗴𝗲</b>\n\n"
            "𝗥𝗲𝗽𝗹𝘆 𝘁𝗼 𝗮 𝗰𝗹𝗲𝗮𝗻𝗲𝗱 <code>.txt</code> 𝗳𝗶𝗹𝗲 𝘄𝗶𝘁𝗵 <code>/split</code>\n"
            f"{SEP}",
            parse_mode="HTML",
        )
        return

    doc = replied.document

    if not (doc.file_name or "").endswith(".txt"):
        await message.reply(
            "❌ <b>Please reply to a <code>.txt</code> file containing cards.</b>",
            parse_mode="HTML",
        )
        return

    if doc.file_size > MAX_FILE_SIZE:
        await message.reply(
            f"❌ <b>File too large.</b> Max: <b>{MAX_FILE_SIZE // 1_048_576} MB</b>",
            parse_mode="HTML",
        )
        return

    # Download file
    tmp_in = tempfile.mktemp(suffix=".txt")
    try:
        tg_file = await message.bot.get_file(doc.file_id)
        await message.bot.download_file(tg_file.file_path, destination=tmp_in)
    except Exception as e:
        _safe_delete(tmp_in)
        await message.reply(
            f"❌ <b>Could not download file:</b> <code>{e}</code>",
            parse_mode="HTML",
        )
        return

    # Count cards
    loop        = asyncio.get_event_loop()
    total_cards = await loop.run_in_executor(None, _count_lines, tmp_in)

    # Register session
    session = sessions.create(user_id, tmp_in, doc.file_name, total_cards)

    # Enter FSM state
    await state.set_state(SplitStates.waiting_for_size)
    await state.update_data(user_id=user_id)

    prompt = await message.reply(
        f"{SEP}\n"
        f"<a href='https://t.me/broken_wiz'>✧</a> <b>𝗦𝗣𝗟𝗜𝗧 — 𝗙𝗶𝗹𝗲 𝗗𝗲𝘁𝗲𝗰𝘁𝗲𝗱</b>\n"
        f"{SEP}\n"
        f"<a href='https://t.me/broken_wiz'>✧</a> 𝗦𝗼𝘂𝗿𝗰𝗲 ➠ <code>{doc.file_name}</code>\n"
        f"<a href='https://t.me/broken_wiz'>✧</a> 𝗖𝗮𝗿𝗱𝘀 ➠ <code>{total_cards:,}</code>\n"
        #f"{SEP}\n"
        f"<a href='https://t.me/broken_wiz'>✧</a> 𝗥𝗲𝗽𝗹𝘆 𝘄𝗶𝘁𝗵 𝗮 𝗻𝘂𝗺𝗯𝗲𝗿\n"
        f"<a href='https://t.me/broken_wiz'>✧</a> 𝗘𝘅. ➠ <code>5000</code>\n\n"
        f"<a href='https://t.me/broken_wiz'>✧</a> 𝗔𝘂𝘁𝗼-𝗰𝗮𝗻𝗰𝗲𝗹 𝗶𝗻 {SPLIT_TIMEOUT_SECONDS}𝘀 — 𝘂𝘀𝗲 /cancel 𝘁𝗼 𝗮𝗯𝗼𝗿𝘁\n"
        f"{SEP}",
        parse_mode="HTML",
        disable_web_page_preview=True,
    )

    # Schedule auto-cancel
    async def _auto_cancel() -> None:
        await asyncio.sleep(SPLIT_TIMEOUT_SECONDS)
        if sessions.get(user_id):
            sessions.delete(user_id)
            await state.clear()
            try:
                await prompt.edit_text(
                    f"{SEP}\n"
                    "⏱ <b>𝗦𝗲𝘀𝘀𝗶𝗼𝗻 𝗘𝘅𝗽𝗶𝗿𝗲𝗱</b>\n\n"
                    "Please use <code>/split</code> again.\n"
                    f"{SEP}",
                    parse_mode="HTML",
                )
            except Exception:
                pass

    task                 = asyncio.create_task(_auto_cancel())
    session.timeout_task = task


# ============================================================
# HANDLER: /split  (step 2 — receive chunk size)
# ============================================================
@router.message(SplitStates.waiting_for_size, F.text)
async def split_receive_size(message: types.Message, state: FSMContext) -> None:
    user    = message.from_user
    user_id = user.id

    raw = message.text.strip().replace(",", "").replace(".", "")
    try:
        chunk_size = int(raw)
    except ValueError:
        await message.reply(
            "❌ <b>Invalid input.</b>\n"
            "Please send a whole number. Example: <code>1000</code>",
            parse_mode="HTML",
        )
        return

    if chunk_size < 1:
        await message.reply(
            "❌ <b>Chunk size must be at least</b> <code>1</code>.",
            parse_mode="HTML",
        )
        return

    if chunk_size > MAX_CHUNK_SIZE:
        await message.reply(
            f"❌ <b>Chunk size too large.</b> Maximum: <code>{MAX_CHUNK_SIZE:,}</code>",
            parse_mode="HTML",
        )
        return

    session = sessions.get(user_id)
    if not session:
        await state.clear()
        await message.reply(
            "❌ <b>Session expired.</b> Please use <code>/split</code> again.",
            parse_mode="HTML",
        )
        return

    # Cancel the auto-cancel task
    if session.timeout_task and not session.timeout_task.done():
        session.timeout_task.cancel()

    # Clear FSM state immediately
    await state.clear()

    progress = await message.reply(
        f"<pre><code>⏳ 𝙎𝙥𝙡𝙞𝙩𝙩𝙞𝙣𝙜 𝙄𝙣 𝙋𝙧𝙤𝙜𝙧𝙚𝙨𝙨...</code></pre>\n"
        f"𝗙𝗶𝗹𝗲  ➠ <b>{session.original_name}</b>\n"
        f"𝗖𝗵𝘂𝗻𝗸 ➠ <b>{chunk_size:,}</b> cards per file\n"
        f"𝗦𝘁𝗮𝘁𝘂𝘀 ➠ <b>Processing, please wait...</b>",
        parse_mode="HTML",
    )

    output_dir = tempfile.mkdtemp()
    try:
        output_files = await FileProcessor.split(
            session.file_path, chunk_size, output_dir
        )
        num_chunks = len(output_files)
        db.log_split(user_id, session.original_name,
                     session.total_cards, chunk_size, num_chunks)

        # Send each chunk
        for idx, path in enumerate(output_files, 1):
            card_count = await asyncio.get_event_loop().run_in_executor(
                None, _count_lines, path
            )
            await message.reply_document(
                document=FSInputFile(path, filename=f"split{idx}.txt"),
                caption=(
                    #f"{SEP}\n"
                    f"<a href='https://t.me/broken_wiz'>✧</a> <b>𝗣𝗮𝗿𝘁 ➠ {idx} / {num_chunks}</b>\n"
                    f"<a href='https://t.me/broken_wiz'>✧</a> 𝗖𝗮𝗿𝗱𝘀 ➠ <b>{card_count:,}</b>\n"
                    #f"{SEP}"
                ),
                parse_mode="HTML",
            )

        await message.reply(
            f"{SEP}\n"
            f"<a href='https://t.me/broken_wiz'>✧</a> <b>𝗦𝗽𝗹𝗶𝘁 𝗖𝗼𝗺𝗽𝗹𝗲𝘁𝗲</b>\n"
            f"{SEP}\n"
            f"<a href='https://t.me/broken_wiz'>✧</a> 𝗦𝗼𝘂𝗿𝗰𝗲 ➠ <b>{session.original_name}</b>\n"
            f"<a href='https://t.me/broken_wiz'>✧</a> 𝗧𝗼𝘁𝗮𝗹 𝗖𝗮𝗿𝗱𝘀 ➠ <b>{session.total_cards:,}</b>\n"
            f"<a href='https://t.me/broken_wiz'>✧</a> 𝗖𝗵𝘂𝗻𝗸 𝗦𝗶𝘇𝗲 ➠ <b>{chunk_size:,}</b>\n"
            f"<a href='https://t.me/broken_wiz'>✧</a> 𝗙𝗶𝗹𝗲𝘀 𝗦𝗲𝗻𝘁 ➠ <b>{num_chunks}</b>\n"
            f"<a href='https://t.me/broken_wiz'>✧</a> 𝗨𝘀𝗲𝗿 ➠ {_user_link(user)}\n"
            f"<a href='https://t.me/broken_wiz'>✧</a> 𝗗𝗲𝘃 ➠ {DEV_LINK}\n"
            f"{SEP}",
            parse_mode="HTML",
            disable_web_page_preview=True,
        )
        await progress.delete()

    except Exception as e:
        logger.error(f"[SPLIT] error: {e}")
        await progress.edit_text(
            f"❌ <b>Split failed:</b> <code>{e}</code>", parse_mode="HTML"
        )
    finally:
        sessions.delete(user_id)
        _safe_rmtree(output_dir)


# ============================================================
# HANDLER: /cancel
# ============================================================
@router.message(Command("cancel"))
async def cancel_command(message: types.Message, state: FSMContext) -> None:
    user_id     = message.from_user.id
    had_session = sessions.get(user_id) is not None
    sessions.delete(user_id)
    await state.clear()

    if had_session:
        await message.reply(
            f"{SEP}\n"
            "✅ <b>𝗦𝗽𝗹𝗶𝘁 𝘀𝗲𝘀𝘀𝗶𝗼𝗻 𝗰𝗮𝗻𝗰𝗲𝗹𝗹𝗲𝗱.</b>\n"
            f"{SEP}",
            parse_mode="HTML",
        )
    else:
        await message.reply(
            f"{SEP}\n"
            "ℹ️ <b>𝗡𝗼 𝗮𝗰𝘁𝗶𝘃𝗲 𝘀𝗲𝘀𝘀𝗶𝗼𝗻 𝘁𝗼 𝗰𝗮𝗻𝗰𝗲𝗹.</b>\n"
            f"{SEP}",
            parse_mode="HTML",
        )


# ============================================================
# HANDLER: /shuffle
# ============================================================
@router.message(Command("shuffle"))
async def shuffle_command(message: types.Message) -> None:
    user    = message.from_user
    user_id = user.id

    if not await _gate_check("clean", message):
        return

    is_premium, _ = await asyncio.to_thread(get_premium_status, user_id)
    credits       = await asyncio.to_thread(get_user_credits, user_id)
    if not is_premium and (credits is None or credits <= 0):
        await message.reply(
            "❌ <b>Insufficient Credits!</b>\n\n"
            "You have <b>0 credits</b> left. Please recharge.",
            parse_mode="HTML",
        )
        return

    replied = message.reply_to_message
    if not replied or not replied.document:
        await message.reply(
            f"{SEP}\n"
            "❌ <b>𝗜𝗻𝘃𝗮𝗹𝗶𝗱 𝗨𝘀𝗮𝗴𝗲</b>\n\n"
            "𝗥𝗲𝗽𝗹𝘆 𝘁𝗼 𝗮 𝗰𝗹𝗲𝗮𝗻𝗲𝗱 <code>.txt</code> 𝗳𝗶𝗹𝗲 𝘄𝗶𝘁𝗵 <code>/shuffle</code>\n"
            f"{SEP}",
            parse_mode="HTML",
        )
        return

    doc = replied.document

    if not (doc.file_name or "").endswith(".txt"):
        await message.reply(
            "❌ <b>Please reply to a <code>.txt</code> file containing cards.</b>",
            parse_mode="HTML",
        )
        return

    if doc.file_size > MAX_FILE_SIZE:
        await message.reply(
            f"❌ <b>File too large.</b> Max: <b>{MAX_FILE_SIZE // 1_048_576} MB</b>",
            parse_mode="HTML",
        )
        return

    progress = await message.reply(
        f"<pre><code>🎲 𝙎𝙝𝙪𝙛𝙛𝙡𝙞𝙣𝙜 𝘾𝙖𝙧𝙙𝙨...</code></pre>\n"
        f"𝗙𝗶𝗹𝗲   ➠ <b>{doc.file_name}</b>\n"
        f"𝗦𝘁𝗮𝘁𝘂𝘀 ➠ <b>Randomising card order...</b>",
        parse_mode="HTML",
    )

    tmp_in  = tempfile.mktemp(suffix=".txt")
    tmp_out = tempfile.mktemp(suffix="_shuffled.txt")

    try:
        tg_file = await message.bot.get_file(doc.file_id)
        await message.bot.download_file(tg_file.file_path, destination=tmp_in)

        count = await FileProcessor.shuffle(tmp_in, tmp_out)

        if count == 0:
            await progress.edit_text(
                f"{SEP}\n"
                "⚠️ <b>File is empty — nothing to shuffle.</b>\n"
                f"{SEP}",
                parse_mode="HTML",
            )
            return

        db.log_shuffle(user_id, doc.file_name, count)

        # Credit deduction for free users
        if not is_premium:
            new_bal = max(0, (credits or 0) - 1)
            await asyncio.to_thread(update_credits, user_id, new_bal)
        else:
            new_bal = credits or 0

        await message.reply_document(
            document=FSInputFile(tmp_out, filename="shuffled.txt"),
            caption=(
                f"{SEP}\n"
                f"<a href='https://t.me/broken_wiz'>✧</a> <b>𝗦𝗵𝘂𝗳𝗳𝗹𝗲 𝗖𝗼𝗺𝗽𝗹𝗲𝘁𝗲</b>\n"
                f"{SEP}\n"
                f"<a href='https://t.me/broken_wiz'>✧</a> 𝗦𝗼𝘂𝗿𝗰𝗲 ➠ <b>{doc.file_name}</b>\n"
                f"<a href='https://t.me/broken_wiz'>✧</a> 𝗖𝗮𝗿𝗱𝘀 𝗦𝗵𝘂𝗳𝗳𝗹𝗲𝗱 ➠ <b>{count:,}</b>\n"
                f"<a href='https://t.me/broken_wiz'>✧</a> 𝗔𝗹𝗴𝗼𝗿𝗶𝘁𝗵𝗺 ➠ <b>Fisher-Yates</b>\n"
                f"<a href='https://t.me/broken_wiz'>✧</a> 𝗖𝗿𝗲𝗱𝗶𝘁𝘀 𝗟𝗲𝗳𝘁 ➠ <code>{new_bal}</code>\n"
                f"<a href='https://t.me/broken_wiz'>✧</a> 𝗨𝘀𝗲𝗿 ➠ {_user_link(user)}\n"
                f"<a href='https://t.me/broken_wiz'>✧</a> 𝗗𝗲𝘃 ➠ {DEV_LINK}\n"
                f"{SEP}"
            ),
            parse_mode="HTML",
            disable_web_page_preview=True,
        )
        await progress.delete()

    except Exception as e:
        logger.error(f"[SHUFFLE] error: {e}")
        await progress.edit_text(
            f"❌ <b>Error:</b> <code>{e}</code>", parse_mode="HTML"
        )
    finally:
        _safe_delete(tmp_in)
        _safe_delete(tmp_out)


# ============================================================
# EXPORTS
# ============================================================
__all__ = [
    "router",
    "clean_command",
    "split_command",
    "shuffle_command",
    "cancel_command",
    "db",
]
