import os
import json
import asyncio
import secrets
import string as _string
import datetime
from contextlib import asynccontextmanager

import aiosqlite

PAID_PLANS = ["Core", "Elite", "Root", "X", "Custom"]

DB_PATH = os.getenv("DB_PATH", "razor_x_bot.db")

REFERRAL_GOAL = 5
REFERRAL_REWARD_DAYS = 1

KEY_PREFIX = "NARUTO-"
KEY_UNUSED_TTL_HOURS = 24
MAX_KEYS_PER_GENERATE = 50

PROXY_GATES = ("shopify", "shopify_key")

READ_POOL_SIZE = 8

# ============ 𝗗𝗔𝗧𝗘𝗧𝗜𝗠𝗘 𝗛𝗘𝗟𝗣𝗘𝗥𝗦 ============
_DT_FMT = "%Y-%m-%d %H:%M:%S.%f"
_DT_PARSE_FORMATS = (
    _DT_FMT,
    "%Y-%m-%d %H:%M:%S",
    "%Y-%m-%dT%H:%M:%S.%f",
    "%Y-%m-%dT%H:%M:%S",
    "%Y-%m-%d",
)


def _now() -> datetime.datetime:
    return datetime.datetime.now(datetime.timezone.utc).replace(tzinfo=None)


def _fmt_dt(value):
    """Serialize a datetime to a fixed-width naive-UTC string.

    Fixed width matters: ISO strings of differing widths do not sort correctly
    as text, and every date comparison in this module is a lexicographic one.
    """
    if value is None:
        return None
    if isinstance(value, str):
        return value
    if isinstance(value, datetime.datetime):
        if value.tzinfo is not None:
            value = value.astimezone(datetime.timezone.utc).replace(tzinfo=None)
        return value.strftime(_DT_FMT)
    return str(value)


def _parse_dt(value):
    if value is None or value == "":
        return None
    if isinstance(value, datetime.datetime):
        return value.replace(tzinfo=None) if value.tzinfo else value
    text = str(value).strip().replace("Z", "")
    text = text.replace("T", " ", 1) if "T" in text else text
    for fmt in _DT_PARSE_FORMATS:
        try:
            parsed = datetime.datetime.strptime(text, fmt)
            return parsed.replace(tzinfo=None) if parsed.tzinfo else parsed
        except ValueError:
            continue
    try:
        parsed = datetime.datetime.fromisoformat(text)
        return parsed.replace(tzinfo=None) if parsed.tzinfo else parsed
    except ValueError:
        return None


_DT_COLS = {
    "users": ("created_at", "updated_at", "expiry"),
    "keys": ("created_at", "key_expires_at", "redeemed_at", "expired_at"),
    "proxies": ("added_at",),
    "sites": ("added_at",),
    "global_sites": ("added_at",),
    "joined_users": ("joined_at",),
    "feedbacks": ("created_at",),
    "referrals": ("created_at", "verified_at"),
    "crypto_payments": ("claimed_at",),
    "maintenance": ("updated_at",),
    "sh_sessions": ("updated_at",),
}

_BOOL_COLS = {
    "users": ("banned", "pending_expiry_notify", "plan_expiry_notified"),
    "referrals": ("verified",),
    "maintenance": ("global_maintenance",),
    "sh_sessions": ("done", "stopped"),
}

_IDENTITY_TABLES = ("proxies", "sites", "cards")


def _row_to_dict(row, table=None):
    """Convert an aiosqlite Row into a Mongo-shaped dict."""
    if row is None:
        return None
    data = dict(row)
    if table in _IDENTITY_TABLES and "id" in data:
        data["_id"] = data["id"]
    if table:
        for col in _DT_COLS.get(table, ()):
            if col in data:
                data[col] = _parse_dt(data[col])
        for col in _BOOL_COLS.get(table, ()):
            if col in data:
                data[col] = bool(data[col])
    return data


def _paid_in_clause():
    return ",".join("?" for _ in PAID_PLANS)


# ============ 𝗦𝗖𝗛𝗘𝗠𝗔 ============

_SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    user_id INTEGER PRIMARY KEY,
    name TEXT,
    username TEXT,
    plan TEXT NOT NULL DEFAULT 'Trial',
    expiry TEXT,
    premium_days INTEGER,
    banned INTEGER NOT NULL DEFAULT 0,
    banned_by INTEGER,
    credits INTEGER NOT NULL DEFAULT 0,
    created_at TEXT,
    updated_at TEXT,
    pending_expiry_notify INTEGER,
    plan_expiry_notified INTEGER,
    total_checked INTEGER NOT NULL DEFAULT 0,
    total_charged INTEGER NOT NULL DEFAULT 0,
    total_approved INTEGER NOT NULL DEFAULT 0,
    total_declined INTEGER NOT NULL DEFAULT 0,
    hits INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_users_plan ON users(plan);
CREATE INDEX IF NOT EXISTS idx_users_plan_expiry ON users(plan, expiry);
CREATE INDEX IF NOT EXISTS idx_users_banned ON users(banned);
CREATE INDEX IF NOT EXISTS idx_users_pending_expiry ON users(pending_expiry_notify);

CREATE TABLE IF NOT EXISTS keys (
    key TEXT PRIMARY KEY,
    days INTEGER NOT NULL DEFAULT 1,
    status TEXT NOT NULL DEFAULT 'unused',
    assigned_to INTEGER,
    created_by INTEGER,
    created_at TEXT,
    key_expires_at TEXT,
    redeemed_by INTEGER,
    redeemed_at TEXT,
    expired_at TEXT
);
CREATE INDEX IF NOT EXISTS idx_keys_status ON keys(status);
CREATE INDEX IF NOT EXISTS idx_keys_expires ON keys(key_expires_at);
CREATE INDEX IF NOT EXISTS idx_keys_assigned ON keys(assigned_to);

CREATE TABLE IF NOT EXISTS proxies (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    gate TEXT NOT NULL DEFAULT 'shopify',
    ip TEXT,
    port TEXT,
    username TEXT,
    password TEXT,
    proxy_url TEXT,
    proxy_type TEXT DEFAULT 'http',
    added_at TEXT
);
CREATE INDEX IF NOT EXISTS idx_proxies_user_gate_url ON proxies(user_id, gate, proxy_url);
CREATE INDEX IF NOT EXISTS idx_proxies_user_gate ON proxies(user_id, gate);
CREATE INDEX IF NOT EXISTS idx_proxies_user ON proxies(user_id);

CREATE TABLE IF NOT EXISTS sites (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    site TEXT,
    added_at TEXT
);
CREATE INDEX IF NOT EXISTS idx_sites_user_site ON sites(user_id, site);
CREATE INDEX IF NOT EXISTS idx_sites_user ON sites(user_id);

CREATE TABLE IF NOT EXISTS global_sites (
    site TEXT PRIMARY KEY,
    added_at TEXT
);

CREATE TABLE IF NOT EXISTS cards (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER,
    created_at TEXT,
    status TEXT
);
CREATE INDEX IF NOT EXISTS idx_cards_created ON cards(created_at);
CREATE INDEX IF NOT EXISTS idx_cards_status ON cards(status);

CREATE TABLE IF NOT EXISTS joined_users (
    user_id INTEGER PRIMARY KEY,
    joined_at TEXT
);

CREATE TABLE IF NOT EXISTS feedbacks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER,
    user_name TEXT,
    message_id INTEGER,
    chat_id INTEGER,
    media_type TEXT,
    created_at TEXT
);
CREATE INDEX IF NOT EXISTS idx_feedbacks_user ON feedbacks(user_id);
CREATE INDEX IF NOT EXISTS idx_feedbacks_created ON feedbacks(created_at);

CREATE TABLE IF NOT EXISTS referrals (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    referred_user_id INTEGER NOT NULL UNIQUE,
    referrer_id INTEGER NOT NULL,
    verified INTEGER NOT NULL DEFAULT 0,
    created_at TEXT,
    verified_at TEXT
);
CREATE INDEX IF NOT EXISTS idx_referrals_referrer ON referrals(referrer_id);

CREATE TABLE IF NOT EXISTS crypto_payments (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    tx_id TEXT NOT NULL UNIQUE,
    user_id INTEGER,
    plan TEXT,
    net_key TEXT,
    claimed_at TEXT
);

CREATE TABLE IF NOT EXISTS maintenance (
    _id TEXT PRIMARY KEY,
    global_maintenance INTEGER NOT NULL DEFAULT 0,
    gates TEXT NOT NULL DEFAULT '{}',
    updated_at TEXT
);

CREATE TABLE IF NOT EXISTS sh_sessions (
    session_id TEXT PRIMARY KEY,
    user_id INTEGER,
    total INTEGER,
    results TEXT,
    start REAL,
    name TEXT,
    username TEXT,
    view_page INTEGER NOT NULL DEFAULT 0,
    done INTEGER NOT NULL DEFAULT 0,
    stopped INTEGER NOT NULL DEFAULT 0,
    updated_at TEXT
);

CREATE TABLE IF NOT EXISTS gate_health (
    gate_key TEXT PRIMARY KEY,
    records TEXT NOT NULL DEFAULT '[]'
);
"""

_read_pool: asyncio.Queue | None = None
_write_conn = None
_init_lock = asyncio.Lock()
_write_lock = asyncio.Lock()


async def _connect():
    conn = await aiosqlite.connect(DB_PATH, timeout=30.0, isolation_level=None)
    conn.row_factory = aiosqlite.Row
    for pragma in (
        "PRAGMA journal_mode=WAL",
        "PRAGMA synchronous=NORMAL",
        "PRAGMA busy_timeout=30000",
        "PRAGMA temp_store=MEMORY",
        "PRAGMA cache_size=-16000",
    ):
        await conn.execute(pragma)
    return conn


async def _ensure_pool():
    global _read_pool, _write_conn
    if _read_pool is not None:
        return
    async with _init_lock:
        if _read_pool is not None:
            return
        directory = os.path.dirname(os.path.abspath(DB_PATH))
        if directory:
            os.makedirs(directory, exist_ok=True)
        _write_conn = await _connect()
        pool = asyncio.Queue()
        for _ in range(READ_POOL_SIZE):
            await pool.put(await _connect())
        _read_pool = pool


@asynccontextmanager
async def _read():
    await _ensure_pool()
    conn = await _read_pool.get()
    try:
        yield conn
    finally:
        await _read_pool.put(conn)


@asynccontextmanager
async def _tx():
    """Serialized write transaction. All writers go through this single lock."""
    await _ensure_pool()
    async with _write_lock:
        conn = _write_conn
        await conn.execute("BEGIN IMMEDIATE")
        try:
            yield conn
        except BaseException:
            try:
                await conn.execute("ROLLBACK")
            except Exception:
                pass
            raise
        await conn.execute("COMMIT")


async def _write1(sql, params=()):
    """Run a single autocommit write statement, serialized against other writers.

    A lone statement is already atomic in SQLite, so this skips the explicit
    BEGIN/COMMIT round-trips that _tx() needs for multi-statement work.
    Returns the affected row count.
    """
    await _ensure_pool()
    async with _write_lock:
        cur = await _write_conn.execute(sql, params)
        return cur.rowcount


async def _fetch_one(sql, params=(), table=None):
    async with _read() as conn:
        async with conn.execute(sql, params) as cur:
            row = await cur.fetchone()
    return _row_to_dict(row, table)


async def _fetch_all(sql, params=(), table=None):
    async with _read() as conn:
        async with conn.execute(sql, params) as cur:
            rows = await cur.fetchall()
    return [_row_to_dict(r, table) for r in rows]


async def _fetch_val(sql, params=(), default=0):
    async with _read() as conn:
        async with conn.execute(sql, params) as cur:
            row = await cur.fetchone()
    if row is None or row[0] is None:
        return default
    return row[0]


async def close_db():
    """Close every pooled connection. Safe to call more than once."""
    global _read_pool, _write_conn
    async with _init_lock:
        if _read_pool is not None:
            while not _read_pool.empty():
                conn = await _read_pool.get()
                try:
                    await conn.close()
                except Exception:
                    pass
            _read_pool = None
        if _write_conn is not None:
            try:
                await _write_conn.close()
            except Exception:
                pass
            _write_conn = None


async def init_db():
    """𝗜𝗻𝗶𝘁𝗶𝗮𝗹𝗶𝘇𝗲 𝗱𝗮𝘁𝗮𝗯𝗮𝘀𝗲 𝘄𝗶𝘁𝗵 𝗶𝗻𝗶𝘅𝗲𝘅𝗲𝘀"""
    try:
        await _ensure_pool()
        async with _write_lock:
            await _write_conn.executescript(_SCHEMA)
        try:
            copied = await migrate_proxy_gates()
            if copied:
                print(f"⚠︎ 𝗣𝗿𝗼𝘅𝘆 𝗴𝗮𝘁𝗲 𝗺𝗶𝗴𝗿𝗮𝘁𝗶𝗼𝗻: {copied} 𝗽𝗿𝗼𝘅𝘆 𝗱𝗼𝗰𝘀 𝗺𝗶𝗴𝗿𝗮𝘁𝗲𝗱")
        except Exception as mig_e:
            print(f"⚠︎ 𝗣𝗿𝗼𝘅𝘆 𝗴𝗮𝘁𝗲 𝗺𝗶𝗴𝗿𝗮𝘁𝗶𝗼𝗻: {mig_e}")
        print("✓ 𝗥𝗔𝗭𝗢𝗥 𝗫 𝗗𝗮𝘁𝗮𝗯𝗮𝘀𝗲 𝗶𝗻𝗶𝘁𝗶𝗮𝗹𝗶𝘇𝗲𝗱 𝘀𝘂𝗰𝗰𝗲𝘀𝘀𝗳𝘂𝗹𝗹𝘆!")
    except Exception as e:
        print(f"⚠︎ 𝗗𝗕 𝗶𝗻𝗶𝘁 𝘄𝗮𝗿𝗻𝗶𝗻𝗴: {e}")


# ============ 𝗨𝗦𝗘𝗥 𝗠𝗔𝗡𝗔𝗚𝗘𝗠𝗘𝗡𝗧 ============

async def get_user_doc(user_id: int) -> dict | None:
    """Return the full user document as a dict."""
    return await _fetch_one("SELECT * FROM users WHERE user_id = ?", (user_id,), "users")


async def ensure_user(user_id: int, name: str = None, username: str = None):
    """𝗘𝗻𝘀𝘂𝗿𝗲 𝘂𝘀𝗲𝗿 𝗲𝘅𝗶𝘀𝘁𝘀 𝗶𝗻 𝗗𝗕"""
    try:
        now = _fmt_dt(_now())
        set_cols = []
        set_vals = []
        if name:
            set_cols.append("name")
            set_vals.append(name)
        if username:
            set_cols.append("username")
            set_vals.append(username)
        assigns = [f"{col} = excluded.{col}" for col in set_cols]

        insert_cols = ["user_id", "plan", "expiry", "banned", "banned_by", "credits", "created_at"]
        insert_vals = [user_id, "Trial", None, 0, None, 250, now]
        all_cols = insert_cols + set_cols
        placeholders = ",".join("?" for _ in all_cols)

        if assigns:
            sql = (
                f"INSERT INTO users ({', '.join(all_cols)}) VALUES ({placeholders}) "
                f"ON CONFLICT(user_id) DO UPDATE SET {', '.join(assigns)}"
            )
        else:
            sql = (
                f"INSERT INTO users ({', '.join(insert_cols)}) VALUES ({placeholders}) "
                "ON CONFLICT(user_id) DO NOTHING"
            )

        await _write1(sql, insert_vals + set_vals)
    except Exception:
        pass


async def _downgrade_expired_plan(user_id: int) -> str | None:
    """Atomically downgrade an expired paid plan. Returns the previous tier, or None.

    Only called once a read has confirmed the plan is actually expired, so the
    global write lock is never taken on the hot read path.
    """
    now_s = _fmt_dt(_now())
    async with _tx() as conn:
        async with conn.execute(
            f"SELECT plan FROM users WHERE user_id = ? AND plan IN ({_paid_in_clause()}) "
            "AND expiry IS NOT NULL AND expiry < ?",
            (user_id, *PAID_PLANS, now_s),
        ) as cur:
            row = await cur.fetchone()
        if row is None:
            return None
        old_plan = row[0]
        await conn.execute(
            "UPDATE users SET plan = 'Trial', expiry = NULL, "
            "pending_expiry_notify = 1, updated_at = ? WHERE user_id = ?",
            (now_s, user_id),
        )
    return "Trial" if old_plan == "Bronze" else old_plan


async def check_and_expire_plan(user_id: int) -> str | None:
    """Downgrade an expired paid plan to Trial. Returns the previous plan tier, or None."""
    row = await _fetch_one(
        "SELECT plan, expiry FROM users WHERE user_id = ?", (user_id,), "users"
    )
    if not row:
        return None
    if row.get("plan") not in PAID_PLANS:
        return None
    expiry = row.get("expiry")
    if not expiry or expiry >= _now():
        return None
    return await _downgrade_expired_plan(user_id)


async def get_user_plan(user_id: int) -> str:
    """𝗚𝗲𝘁 𝘂𝘀𝗲𝗿'𝘀 𝗰𝘂𝗿𝗿𝗲𝗻𝘁 𝗽𝗹𝗮𝗻"""
    row = await _fetch_one(
        "SELECT plan, expiry FROM users WHERE user_id = ?", (user_id,), "users"
    )
    if not row:
        return "Trial"

    value = row.get("plan") or "Trial"
    expiry = row.get("expiry")
    if value in PAID_PLANS and expiry and expiry < _now():
        await _downgrade_expired_plan(user_id)
        return "Trial"
    if value == "Bronze":
        return "Trial"
    return value


async def set_user_plan(user_id: int, plan: str, days: int = 0):
    """𝗦𝗲𝘁 𝘂𝘀𝗲𝗿 𝗽𝗹𝗮𝗻 𝘄𝗶𝘁𝗵 𝗲𝘅𝗽𝗶𝗿𝘆"""
    expiry = None
    if days > 0:
        expiry = _fmt_dt(_now() + datetime.timedelta(days=days))

    await _write1(
        "INSERT INTO users (user_id, plan, expiry, premium_days, updated_at) "
        "VALUES (?, ?, ?, ?, ?) "
        "ON CONFLICT(user_id) DO UPDATE SET "
        "plan = excluded.plan, expiry = excluded.expiry, "
        "premium_days = excluded.premium_days, updated_at = excluded.updated_at, "
        "pending_expiry_notify = NULL, plan_expiry_notified = NULL",
        (user_id, plan, expiry, days, _fmt_dt(_now())),
    )
async def is_premium_user(user_id: int) -> bool:
    """𝗖𝗵𝗲𝗰𝗸 𝗶𝗳 𝘂𝘀𝗲𝗿 𝗵𝗮𝘀 𝗽𝗿𝗲𝗺𝗶𝘂𝗺 𝗽𝗹𝗮𝗻"""
    plan = await get_user_plan(user_id)
    return plan in PAID_PLANS


async def get_user_expiry(user_id: int):
    """Return active plan expiry datetime, or None."""
    row = await _fetch_one(
        "SELECT expiry, plan FROM users WHERE user_id = ?", (user_id,), "users"
    )
    if not row:
        return None
    plan = row.get("plan")
    expiry = row.get("expiry")
    if plan in PAID_PLANS and expiry and expiry < _now():
        await _downgrade_expired_plan(user_id)
        return None
    if plan not in PAID_PLANS:
        return None
    return expiry


async def is_banned_user(user_id: int) -> bool:
    """𝗖𝗵𝗲𝗰𝗸 𝗶𝗳 𝘂𝘀𝗲𝗿 𝗵𝗮𝘀 𝗯𝗮𝗻𝗻𝗲𝗱"""
    row = await _fetch_one("SELECT banned FROM users WHERE user_id = ?", (user_id,), "users")
    return bool(row.get("banned")) if row else False


async def set_user_banned(user_id: int, banned: bool, banned_by: int | None = None):
    """𝗦𝗲𝘁 𝗯𝗮𝗻 𝘀𝘁𝗮𝘁𝘂𝘀 𝗽𝗼𝗿 𝘂𝘀𝗲𝗿"""
    await _write1(
        "INSERT INTO users (user_id, banned, banned_by, updated_at) VALUES (?, ?, ?, ?) "
        "ON CONFLICT(user_id) DO UPDATE SET banned = excluded.banned, "
        "banned_by = excluded.banned_by, updated_at = excluded.updated_at",
        (user_id, 1 if banned else 0, banned_by, _fmt_dt(_now())),
    )
# ============ CREDITS ============

async def get_user_credits(user_id: int):
    row = await _fetch_one("SELECT credits FROM users WHERE user_id = ?", (user_id,))
    if not row:
        return 0
    return row.get("credits") or 0


async def set_user_credits(user_id: int, amount: int):
    await _write1(
        "INSERT INTO users (user_id, credits) VALUES (?, ?) "
        "ON CONFLICT(user_id) DO UPDATE SET credits = excluded.credits",
        (user_id, amount),
    )
async def add_user_credits(user_id: int, amount: int):
    await _write1(
        "INSERT INTO users (user_id, credits) VALUES (?, ?) "
        "ON CONFLICT(user_id) DO UPDATE SET credits = COALESCE(users.credits, 0) + excluded.credits",
        (user_id, amount),
    )
async def deduct_credit(user_id: int, amount: int = 1) -> bool:
    try:
        admin_ids = json.loads(os.getenv("ADMIN_ID", "[]"))
        if user_id in admin_ids:
            return True
    except Exception:
        pass
    if await get_user_plan(user_id) in PAID_PLANS:
        return True
    return await _write1(
        "UPDATE users SET credits = credits - ? WHERE user_id = ? AND credits >= ?",
        (amount, user_id, amount),
    ) > 0
async def get_user_joined_date(user_id: int):
    row = await _fetch_one("SELECT created_at FROM users WHERE user_id = ?", (user_id,), "users")
    if not row:
        return None
    return row.get("created_at")


# ============ 𝗝𝗢𝗜𝗡 𝗩𝗘𝗥𝗜𝗙𝗜𝗖𝗔𝗧𝗜𝗢𝗡 𝗖𝗔𝗥𝗡𝗘 ============

async def mark_user_joined(user_id: int):
    """𝗠𝗮𝗿𝗸 𝗮 𝘂𝘀𝗲𝗿 𝗮𝘀 𝗵𝗮𝘃𝗶𝗺𝗴 𝗷𝗼𝗶𝗻𝗲𝗱 𝗿𝗲𝗾𝘂𝗶𝗿𝗲𝗱 𝗰𝗵𝗮𝘁𝘀"""
    await _write1(
        "INSERT INTO joined_users (user_id, joined_at) VALUES (?, ?) "
        "ON CONFLICT(user_id) DO UPDATE SET joined_at = excluded.joined_at",
        (user_id, _fmt_dt(_now())),
    )
async def is_user_marked_joined(user_id: int) -> bool:
    """𝗖𝗵𝗲𝗰𝗸 𝗶𝗳 𝘂𝘀𝗲𝗿 𝗵𝗮𝘀 𝗺𝗮𝗿𝗸𝗲𝗱 𝗮𝘀 𝗷𝗼𝗶𝗻𝗲𝗱"""
    row = await _fetch_one("SELECT user_id FROM joined_users WHERE user_id = ?", (user_id,))
    return row is not None


async def remove_joined_mark(user_id: int):
    """𝗥𝗲𝗺𝗼𝘃𝗲 𝗵𝗵𝗲 𝗷𝗼𝗶𝗻𝗲𝗱 𝗺𝗮𝗿𝗸"""
    await _write1("DELETE FROM joined_users WHERE user_id = ?", (user_id,))
# ============ REFERRALS ============

async def user_exists(user_id: int) -> bool:
    row = await _fetch_one("SELECT user_id FROM users WHERE user_id = ?", (user_id,))
    return row is not None


async def register_pending_referral(referred_user_id: int, referrer_id: int) -> bool:
    if referred_user_id == referrer_id or referrer_id <= 0:
        return False
    if not await user_exists(referred_user_id):
        return False
    if await is_user_marked_joined(referred_user_id):
        return False
    try:
        await _write1(
            "INSERT INTO referrals (referred_user_id, referrer_id, verified, created_at) "
            "VALUES (?, ?, 0, ?)",
            (referred_user_id, referrer_id, _fmt_dt(_now())),
        )
        return True
    except aiosqlite.IntegrityError:
        return False
    except Exception:
        return False


async def get_verified_referral_count(referrer_id: int) -> int:
    return await _fetch_val(
        "SELECT COUNT(*) FROM referrals WHERE referrer_id = ? AND verified = 1",
        (referrer_id,),
    )


async def extend_user_plan_days(user_id: int, days: int):
    now = _now()
    now_s = _fmt_dt(now)
    row = await _fetch_one("SELECT plan, expiry FROM users WHERE user_id = ?", (user_id,), "users")
    plan = (row or {}).get("plan") or "Trial"
    if plan not in PAID_PLANS:
        plan = "Core"
    expiry = (row or {}).get("expiry")
    if expiry and expiry > now:
        new_expiry = _fmt_dt(expiry + datetime.timedelta(days=days))
    else:
        new_expiry = _fmt_dt(now + datetime.timedelta(days=days))
    await _write1(
        "INSERT INTO users (user_id, plan, expiry, updated_at) VALUES (?, ?, ?, ?) "
        "ON CONFLICT(user_id) DO UPDATE SET plan = excluded.plan, "
        "expiry = excluded.expiry, updated_at = excluded.updated_at",
        (user_id, plan, new_expiry, now_s),
    )
async def complete_referral_on_verify(referred_user_id: int):
    now_s = _fmt_dt(_now())
    async with _tx() as conn:
        async with conn.execute(
            "SELECT id, referrer_id FROM referrals WHERE referred_user_id = ? AND verified = 0",
            (referred_user_id,),
        ) as cur:
            row = await cur.fetchone()
        if row is None:
            return None
        ref_id = row["id"]
        referrer_id = row["referrer_id"]
        await conn.execute(
            "UPDATE referrals SET verified = 1, verified_at = ? WHERE id = ?",
            (now_s, ref_id),
        )
        async with conn.execute(
            "SELECT COUNT(*) FROM referrals WHERE referrer_id = ? AND verified = 1",
            (referrer_id,),
        ) as cur:
            count = (await cur.fetchone())[0]

    rewarded = False
    if count % REFERRAL_GOAL == 0:
        await extend_user_plan_days(referrer_id, REFERRAL_REWARD_DAYS)
        rewarded = True
    return {"referrer_id": referrer_id, "count": count, "rewarded": rewarded}


# ============ 𝗞𝗘𝗬 𝗠𝗔𝗡𝗔𝗚𝗘𝗠𝗘𝗡𝗧 ============


def _generate_key_code(length: int = 20) -> str:
    alphabet = _string.ascii_letters + _string.digits
    return KEY_PREFIX + "".join(secrets.choice(alphabet) for _ in range(length))


async def create_keys(amount: int, days: int, created_by: int, assigned_to: int | None = None):
    """Create unused redeem keys. Returns list of key strings."""
    amount = max(1, min(int(amount), MAX_KEYS_PER_GENERATE))
    days = max(1, int(days))
    now = _now()
    now_s = _fmt_dt(now)
    key_expires_at = _fmt_dt(now + datetime.timedelta(hours=KEY_UNUSED_TTL_HOURS))
    created = []
    for _ in range(amount):
        for _attempt in range(8):
            code = _generate_key_code()
            try:
                await _write1(
                    "INSERT INTO keys (key, days, status, assigned_to, created_by, "
                    "created_at, key_expires_at, redeemed_by, redeemed_at) "
                    "VALUES (?, ?, 'unused', ?, ?, ?, ?, NULL, NULL)",
                    (code, days, assigned_to, created_by, now_s, key_expires_at),
                )
                created.append(code)
                break
            except aiosqlite.IntegrityError:
                continue
            except Exception:
                break
    return created


async def get_key_doc(key: str):
    if not key:
        return None
    return await _fetch_one("SELECT * FROM keys WHERE key = ?", (key.strip(),), "keys")


async def expire_stale_unused_keys() -> int:
    """Mark unused keys past 24h as expired."""
    now_s = _fmt_dt(_now())
    return await _write1(
        "UPDATE keys SET status = 'expired', expired_at = ? "
        "WHERE status = 'unused' AND key_expires_at IS NOT NULL AND key_expires_at < ?",
        (now_s, now_s),
    )
async def revoke_all_unused_keys() -> int:
    """Mark all unused keys as revoked/expired immediately."""
    return await _write1(
        "UPDATE keys SET status = 'expired', expired_at = ? WHERE status = 'unused'",
        (_fmt_dt(_now()),),
    )
async def get_remaining_keys(limit: int = 500):
    """Return unused keys that have not auto-expired yet."""
    await expire_stale_unused_keys()
    return await _fetch_all(
        "SELECT key, days, assigned_to, created_at, key_expires_at FROM keys "
        "WHERE status = 'unused' AND key_expires_at > ? "
        "ORDER BY created_at DESC LIMIT ?",
        (_fmt_dt(_now()), int(limit)),
        "keys",
    )


async def redeem_key(key: str, user_id: int) -> dict:
    """
    Attempt to redeem a key for user_id.
    Returns {"ok": bool, "error": str|None, "days": int|None, "key_doc": dict|None}
    error values: not_found | already_redeemed | expired | not_yours | already_premium
    """
    await expire_stale_unused_keys()
    code = (key or "").strip()
    if not code:
        return {"ok": False, "error": "not_found", "days": None, "key_doc": None}

    doc = await _fetch_one("SELECT * FROM keys WHERE key = ?", (code,), "keys")
    if not doc:
        return {"ok": False, "error": "not_found", "days": None, "key_doc": None}

    status = doc.get("status", "unused")
    if status == "redeemed":
        return {"ok": False, "error": "already_redeemed", "days": None, "key_doc": doc}
    if status == "expired":
        return {"ok": False, "error": "expired", "days": None, "key_doc": doc}

    now = _now()
    now_s = _fmt_dt(now)
    expires_at = doc.get("key_expires_at")
    if expires_at and expires_at < now:
        await _write1(
            "UPDATE keys SET status = 'expired', expired_at = ? WHERE key = ?",
            (now_s, code),
        )
        return {"ok": False, "error": "expired", "days": None, "key_doc": doc}

    assigned_to = doc.get("assigned_to")
    if assigned_to is not None and int(assigned_to) != int(user_id):
        return {"ok": False, "error": "not_yours", "days": None, "key_doc": doc}

    if await is_premium_user(user_id):
        return {"ok": False, "error": "already_premium", "days": None, "key_doc": doc}

    days = int(doc.get("days") or 1)
    async with _tx() as conn:
        cur = await conn.execute(
            "UPDATE keys SET status = 'redeemed', redeemed_by = ?, redeemed_at = ? "
            "WHERE key = ? AND status = 'unused'",
            (user_id, now_s, code),
        )
        claimed_ok = cur.rowcount > 0
        claimed = None
        if claimed_ok:
            async with conn.execute("SELECT * FROM keys WHERE key = ?", (code,)) as sel:
                claimed = await sel.fetchone()
    if not claimed_ok:
        fresh = await _fetch_one("SELECT * FROM keys WHERE key = ?", (code,), "keys")
        if fresh and fresh.get("status") == "redeemed":
            return {"ok": False, "error": "already_redeemed", "days": None, "key_doc": fresh}
        if fresh and fresh.get("status") == "expired":
            return {"ok": False, "error": "expired", "days": None, "key_doc": fresh}
        return {"ok": False, "error": "already_redeemed", "days": None, "key_doc": fresh}

    await set_user_plan(user_id, "Custom", days)
    return {"ok": True, "error": None, "days": days, "key_doc": _row_to_dict(claimed, "keys")}


# ============ 𝗣𝗥𝗢𝗫𝗬 𝗠𝗔𝗡𝗔𝗚𝗘𝗠𝗘𝗡𝗧 ============


def _norm_proxy_gate(gate: str) -> str:
    g = (gate or "shopify").strip().lower()
    if g in ("shopify_key", "shopify-key", "key", "key_users", "keyusers"):
        return "shopify_key"
    return g if g in PROXY_GATES else "shopify"


async def _ensure_proxy_gate_copy(doc, target_gate: str) -> bool:
    """Insert a gate copy of a proxy doc if that gate twin is missing. Returns True if inserted."""
    exists = await _fetch_one(
        "SELECT id FROM proxies WHERE user_id IS ? AND proxy_url IS ? AND gate = ?",
        (doc.get("user_id"), doc.get("proxy_url"), target_gate),
    )
    if exists:
        return False
    await _write1(
        "INSERT INTO proxies (user_id, gate, ip, port, username, password, proxy_url, "
        "proxy_type, added_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            doc.get("user_id"),
            target_gate,
            doc.get("ip"),
            doc.get("port"),
            doc.get("username"),
            doc.get("password"),
            doc.get("proxy_url"),
            doc.get("proxy_type"),
            doc.get("added_at"),
        ),
    )
    return True


async def migrate_proxy_gates():
    """Backfill gate field on legacy proxy docs."""
    return await _write1(
        "UPDATE proxies SET gate = 'shopify' WHERE gate IS NULL OR gate = ''"
    )
async def add_proxy_db(user_id: int, proxy_data: dict, gate: str = "shopify"):
    """Add proxy for user into a gate pool (shopify | shopify_key)."""
    gate = _norm_proxy_gate(gate)
    await _write1(
        "INSERT INTO proxies (user_id, gate, ip, port, username, password, proxy_url, "
        "proxy_type, added_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            user_id,
            gate,
            proxy_data.get("ip"),
            proxy_data.get("port"),
            proxy_data.get("username"),
            proxy_data.get("password"),
            proxy_data.get("proxy_url"),
            proxy_data.get("type", "http"),
            _fmt_dt(_now()),
        ),
    )
async def get_all_user_proxies(user_id: int, gate: str = "shopify"):
    """Get all proxies for user in one gate pool, oldest first."""
    return await _fetch_all(
        "SELECT * FROM proxies WHERE user_id = ? AND gate = ? ORDER BY added_at ASC, id ASC",
        (user_id, _norm_proxy_gate(gate)),
        "proxies",
    )


async def get_proxy_count(user_id: int, gate: str = "shopify") -> int:
    """Get user's proxy count for one gate pool."""
    return await _fetch_val(
        "SELECT COUNT(*) FROM proxies WHERE user_id = ? AND gate = ?",
        (user_id, _norm_proxy_gate(gate)),
    )


async def remove_proxy_by_index(user_id: int, index: int, gate: str = "shopify"):
    """Remove proxy by index within a gate pool."""
    proxies = await get_all_user_proxies(user_id, gate=gate)
    if 0 <= index < len(proxies):
        proxy = proxies[index]
        await _write1("DELETE FROM proxies WHERE id = ?", (proxy["id"],))
        return proxy
    return None


async def remove_proxy_by_url(user_id: int, proxy_url: str, gate: str = "shopify"):
    """Remove proxy by URL within a gate pool."""
    return await _write1(
        "DELETE FROM proxies WHERE user_id = ? AND gate = ? AND proxy_url = ?",
        (user_id, _norm_proxy_gate(gate), proxy_url),
    ) > 0
async def clear_all_proxies(user_id: int, gate: str = "shopify") -> int:
    """Clear all proxies for user in one gate pool."""
    return await _write1(
        "DELETE FROM proxies WHERE user_id = ? AND gate = ?",
        (user_id, _norm_proxy_gate(gate)),
    )
# ============ 𝗚𝗜𝗧𝗘 𝗠𝗔𝗡𝗔𝗚𝗘𝗠𝗘𝗡𝗧 ============

async def add_site_db(user_id: int, site: str) -> bool:
    """Add a site to a user's personal site list."""
    try:
        await _write1(
            "INSERT INTO sites (user_id, site, added_at) VALUES (?, ?, ?)",
            (user_id, site, _fmt_dt(_now())),
        )
        return True
    except Exception:
        return False


async def get_user_sites(user_id: int):
    return await _fetch_all(
        "SELECT * FROM sites WHERE user_id = ? ORDER BY id ASC", (user_id,), "sites"
    )


async def remove_site_db(user_id: int, site: str) -> bool:
    return await _write1(
        "DELETE FROM sites WHERE user_id = ? AND site = ?", (user_id, site)
    ) > 0
async def add_global_site(site: str) -> bool:
    """𝗔𝗱𝗱 𝗴𝗹𝗼𝗯𝗮𝗹 𝘀𝗶𝘁𝗲"""
    if not site:
        return False
    try:
        await _write1(
            "INSERT INTO global_sites (site, added_at) VALUES (?, ?) "
            "ON CONFLICT(site) DO NOTHING",
            (site, _fmt_dt(_now())),
        )
        return True
    except Exception:
        return False


async def get_global_sites():
    """𝗚𝗲𝘁 𝗮𝗹𝗹 𝗴𝗹𝗼𝗯𝗮𝗹 𝘀𝗶𝘁𝗲𝘀"""
    rows = await _fetch_all("SELECT site FROM global_sites", table="global_sites")
    return [row["site"] for row in rows if row.get("site")]


async def remove_global_site(site: str) -> bool:
    """𝗥𝗲𝗺𝗼𝘃𝗲 𝗴𝗹𝗼𝗯𝗮𝗹 𝘀𝗶𝘁𝗲"""
    return await _write1("DELETE FROM global_sites WHERE site = ?", (site,)) > 0
async def count_global_sites() -> int:
    """𝗖𝗼𝘂𝗻𝘁 𝗴𝗹𝗼𝗯𝗮𝗹 (𝘀𝗵𝗮𝗿𝗲𝗱) 𝘀𝗶𝘁𝗲𝘀"""
    return await _fetch_val("SELECT COUNT(*) FROM global_sites")


async def add_global_sites_bulk(sites) -> int:
    """𝗔𝗱𝗱 𝗺𝗮𝗻𝘆 𝗴𝗹𝗼𝗯𝗮𝗹 𝘀𝗶𝘁𝗲𝘀, 𝗶𝗴𝗻𝗼𝗿𝗶𝗻𝗴 𝗱𝘂𝗽𝗹𝗶𝗰𝗮𝘁𝗲𝘀. Returns number added."""
    added = 0
    now_s = _fmt_dt(_now())
    for site in sites or ():
        if not site:
            continue
        try:
            if await _write1(
                "INSERT INTO global_sites (site, added_at) VALUES (?, ?) "
                "ON CONFLICT(site) DO NOTHING",
                (site, now_s),
            ) > 0:
                    added += 1
        except Exception:
            pass
    return added


async def clear_global_sites() -> int:
    """𝗖𝗹𝗲𝗮𝗿 𝗵𝗵𝗲 𝗲𝗻𝘁𝗶𝗿𝗲 𝗴𝗹𝗼𝗯𝗮𝗹 (𝘀𝗵𝗮𝗿𝗲𝗱) 𝘀𝗶𝘁𝗲 𝗽𝗼𝗼𝗹"""
    return await _write1("DELETE FROM global_sites")
async def seed_global_sites_from_user(user_id: int) -> int:
    """Seed the shared pool from a user's personal sites if the pool is empty.

    This is a one-time, non-destructive migration so that existing deployments
    (where free users used to read the admin's personal site list) keep working
    after the shared pool is decoupled from any single user's personal list.
    Returns the number of sites seeded (0 if the pool already had sites).
    """
    if await count_global_sites() > 0:
        return 0
    rows = await _fetch_all("SELECT site FROM sites WHERE user_id = ?", (user_id,))
    sites = [row["site"] for row in rows if row.get("site")]
    if not sites:
        return 0
    return await add_global_sites_bulk(sites)


# ============ 𝗖𝗔𝗥𝗗 𝗦𝗧𝗔𝗧𝗦 ============

async def track_user_stats(user_id: int, status: str):
    """𝗧𝗿𝗮𝗰𝗸 𝘂𝘀𝗲𝗿 𝗴𝗮𝘁𝗲 𝘀𝘁𝗮𝘁𝘀 (𝗻𝗼 𝗰𝗮𝗿𝗱 𝘀𝘁𝗼𝗿𝗮𝗴𝗲)"""
    if user_id is None:
        return
    status_upper = (status or "").upper()
    charged = 1 if status_upper == "CHARGED" else 0
    approved = 1 if status_upper == "APPROVED" else 0
    declined = 1 if status_upper == "DECLINED" else 0
    hits = 1 if status_upper == "CHARGED" else 0
    now_s = _fmt_dt(_now())
    try:
        await _write1(
            "INSERT INTO users (user_id, plan, expiry, banned, banned_by, credits, "
            "created_at, total_checked, total_charged, total_approved, total_declined, hits) "
            "VALUES (?, 'Trial', NULL, 0, NULL, 250, ?, 1, ?, ?, ?, ?) "
            "ON CONFLICT(user_id) DO UPDATE SET "
            "total_checked = COALESCE(users.total_checked, 0) + 1, "
            "total_charged = COALESCE(users.total_charged, 0) + excluded.total_charged, "
            "total_approved = COALESCE(users.total_approved, 0) + excluded.total_approved, "
            "total_declined = COALESCE(users.total_declined, 0) + excluded.total_declined, "
            "hits = COALESCE(users.hits, 0) + excluded.hits",
            (user_id, now_s, charged, approved, declined, hits),
        )
    except Exception:
        pass


async def _sum_column(column: str) -> int:
    return await _fetch_val(f"SELECT COALESCE(SUM({column}), 0) FROM users")


async def get_total_cards_count() -> int:
    return await _sum_column("total_checked")


async def get_charged_count() -> int:
    return await _sum_column("total_charged")


async def get_approved_count() -> int:
    return await _sum_column("total_approved")


async def get_declined_count() -> int:
    return await _sum_column("total_declined")


# ============ 𝗙𝗘𝗘𝗗𝗕𝗔𝗖𝗞 ============

async def save_feedback(user_id: int, user_name: str, message_id: int, chat_id: int, media_type: str):
    """𝗦𝗮𝘃𝗲 𝗳𝗲𝗲𝗱𝗯𝗮𝗰𝗸 𝘁𝗼 𝗗𝗕"""
    try:
        await _write1(
            "INSERT INTO feedbacks (user_id, user_name, message_id, chat_id, media_type, "
            "created_at) VALUES (?, ?, ?, ?, ?, ?)",
            (user_id, user_name, message_id, chat_id, media_type, _fmt_dt(_now())),
        )
    except Exception:
        pass


async def get_feedback_count() -> int:
    """𝗚𝗲𝘁 𝗵𝗼𝘁𝗮𝗹 𝗳𝗲𝗲𝗱𝗯𝗮𝗰𝗸 𝗰𝗼𝘂𝗻𝘁"""
    return await _fetch_val("SELECT COUNT(*) FROM feedbacks")


async def get_top_feedbacks(limit: int = 10, since=None):
    """Top users by approved feedback count (only saved on owner approve)."""
    try:
        params = []
        where = ""
        if since is not None:
            where = "WHERE created_at >= ?"
            params.append(_fmt_dt(since))
        params.append(int(limit))
        rows = await _fetch_all(
            "WITH ranked AS ("
            "  SELECT user_id, user_name,"
            "         ROW_NUMBER() OVER (PARTITION BY user_id ORDER BY created_at DESC, id DESC) AS rn"
            f"  FROM feedbacks {where}"
            ") "
            "SELECT user_id, COUNT(*) AS feedbacks, "
            "       MAX(CASE WHEN rn = 1 THEN user_name END) AS name "
            "FROM ranked GROUP BY user_id ORDER BY feedbacks DESC LIMIT ?",
            tuple(params),
        )
        return [
            {"user_id": r["user_id"], "feedbacks": r.get("feedbacks", 0), "name": r.get("name")}
            for r in rows
        ]
    except Exception as e:
        print(f"Error getting top feedbacks: {e}")
        return []


async def get_total_feedbacks(since=None) -> int:
    try:
        if since is not None:
            return await _fetch_val(
                "SELECT COUNT(*) FROM feedbacks WHERE created_at >= ?", (_fmt_dt(since),)
            )
        return await _fetch_val("SELECT COUNT(*) FROM feedbacks")
    except Exception as e:
        print(f"Error getting total feedbacks: {e}")
        return 0


# ============ 𝗦𝗧𝗔𝗧𝗜𝗦𝗧𝗜𝗖𝗦 ============

async def get_total_users() -> int:
    return await _fetch_val("SELECT COUNT(*) FROM users")


async def get_all_user_ids():
    """Get all registered user IDs for broadcasts."""
    rows = await _fetch_all("SELECT user_id FROM users", table="users")
    return [row["user_id"] for row in rows if row.get("user_id")]


async def get_premium_count() -> int:
    return await _fetch_val(
        f"SELECT COUNT(*) FROM users WHERE plan IN ({_paid_in_clause()}) AND expiry > ?",
        (*PAID_PLANS, _fmt_dt(_now())),
    )


async def get_all_premium_users():
    return await _fetch_all(
        "SELECT user_id, plan, expiry FROM users "
        f"WHERE plan IN ({_paid_in_clause()}) LIMIT 1000",
        tuple(PAID_PLANS),
        "users",
    )


async def get_active_premium_users():
    """Return paid users whose plan expiry is still in the future."""
    return await _fetch_all(
        "SELECT user_id, plan, expiry FROM users "
        f"WHERE plan IN ({_paid_in_clause()}) AND expiry > ? LIMIT 1000",
        (*PAID_PLANS, _fmt_dt(_now())),
        "users",
    )


async def get_active_key_plan_users():
    """Return users on an active key-redeemed plan only (Custom tier from /redeem)."""
    return await _fetch_all(
        "SELECT user_id, plan, expiry FROM users "
        "WHERE plan = 'Custom' AND expiry > ? LIMIT 1000",
        (_fmt_dt(_now()),),
        "users",
    )


async def expire_due_plans() -> int:
    """Downgrade all expired paid plans and queue expiry notifications."""
    now_s = _fmt_dt(_now())
    return await _write1(
        f"UPDATE users SET plan = 'Trial', expiry = NULL, pending_expiry_notify = 1, "
        f"updated_at = ? WHERE plan IN ({_paid_in_clause()}) "
        "AND expiry IS NOT NULL AND expiry < ?",
        (now_s, *PAID_PLANS, now_s),
    )
async def get_pending_expiry_notifications(limit: int = 200):
    return await _fetch_all(
        "SELECT user_id FROM users WHERE pending_expiry_notify = 1 LIMIT ?",
        (int(limit),),
        "users",
    )


async def clear_pending_expiry_notification(user_id: int):
    await _write1(
        "UPDATE users SET pending_expiry_notify = NULL, plan_expiry_notified = 1 "
        "WHERE user_id = ?",
        (user_id,),
    )
# ============ MAINTENANCE PERSISTENCE ============
async def save_maintenance_db(global_maint: bool, gates: dict):
    """Save maintenance status to database"""
    try:
        await _write1(
            "INSERT INTO maintenance (_id, global_maintenance, gates, updated_at) "
            "VALUES ('config', ?, ?, ?) "
            "ON CONFLICT(_id) DO UPDATE SET global_maintenance = excluded.global_maintenance, "
            "gates = excluded.gates, updated_at = excluded.updated_at",
            (1 if global_maint else 0, json.dumps(gates or {}), _fmt_dt(_now())),
        )
    except Exception as e:
        print(f"Error saving maintenance: {e}")


async def load_maintenance_db():
    """Load maintenance status from database"""
    try:
        row = await _fetch_one(
            "SELECT * FROM maintenance WHERE _id = 'config'", table="maintenance"
        )
        if row:
            gates = row.get("gates")
            if isinstance(gates, str):
                try:
                    gates = json.loads(gates)
                except Exception:
                    gates = {}
            return (bool(row.get("global_maintenance")), gates or {}, True)
    except Exception as e:
        print(f"Error loading maintenance: {e}")
    return False, {}, False


# ============ HITS TRACKING ============
async def get_top_hits(limit: int = 10):
    """Get top users by hits from database"""
    try:
        return await _fetch_all(
            "SELECT user_id, hits, name, username FROM users "
            "WHERE hits > 0 ORDER BY hits DESC LIMIT ?",
            (int(limit),),
            "users",
        )
    except Exception as e:
        print(f"Error getting top hits: {e}")
        return []


async def get_total_hits() -> int:
    """Get total hits across all users"""
    try:
        return await _sum_column("hits")
    except Exception as e:
        print(f"Error getting total hits: {e}")
        return 0


# ============ SHOPIFY SESSION PERSISTENCE ============
async def save_sh_session(session: dict):
    """Save shopify check session to database (exclude non-serializable objects like msg)"""
    try:
        doc = (
            session.get("session_id"),
            session.get("user_id"),
            session.get("total"),
            json.dumps(session.get("results") or [], default=str),
            session.get("start"),
            session.get("name"),
            session.get("username"),
            int(session.get("view_page", 0) or 0),
            1 if session.get("done", False) else 0,
            1 if session.get("stopped", False) else 0,
            _fmt_dt(_now()),
        )
        await _write1(
            "INSERT INTO sh_sessions (session_id, user_id, total, results, start, name, "
            "username, view_page, done, stopped, updated_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?) "
            "ON CONFLICT(session_id) DO UPDATE SET "
            "user_id = excluded.user_id, total = excluded.total, results = excluded.results, "
            "start = excluded.start, name = excluded.name, username = excluded.username, "
            "view_page = excluded.view_page, done = excluded.done, "
            "stopped = excluded.stopped, updated_at = excluded.updated_at",
            doc,
        )
    except Exception as e:
        print(f"Error saving sh session: {e}")


async def get_sh_session(session_id: str):
    """Load shopify check session from database"""
    try:
        row = await _fetch_one(
            "SELECT * FROM sh_sessions WHERE session_id = ?", (session_id,), "sh_sessions"
        )
        if not row:
            return None
        results = row.get("results")
        if isinstance(results, str):
            try:
                results = json.loads(results)
            except Exception:
                results = []
        row["results"] = results or []
        return row
    except Exception as e:
        print(f"Error loading sh session: {e}")
        return None


# ============ USER STATS ============
async def get_user_stats(user_id: int):
    """Get stats (checked, charged, approved, declined) for a user"""
    try:
        row = await _fetch_one(
            "SELECT total_checked, total_charged, total_approved, total_declined "
            "FROM users WHERE user_id = ?",
            (user_id,),
        )
        if row:
            return (
                row.get("total_checked") or 0,
                row.get("total_charged") or 0,
                row.get("total_approved") or 0,
                row.get("total_declined") or 0,
            )
    except Exception:
        pass
    return 0, 0, 0, 0


# ============ CRYPTO PAYMENTS ============
async def claim_crypto_payment(tx_id: str, user_id: int, plan: str, net_key: str) -> bool:
    """Return True if owner has not been notified for this tx yet."""
    if not tx_id:
        return False
    try:
        await _write1(
            "INSERT INTO crypto_payments (tx_id, user_id, plan, net_key, claimed_at) "
            "VALUES (?, ?, ?, ?, ?)",
            (tx_id, user_id, plan, net_key, _fmt_dt(_now())),
        )
        return True
    except aiosqlite.IntegrityError:
        return False
    except Exception:
        return False


# ============ 𝗚𝗔𝗧𝗘 𝗚𝗘𝗔𝗟𝗧𝗛 ============
async def record_gate_result(gate_key: str, success) -> bool:
    """Append a success/failure sample, keeping only the most recent 100.

    The read-modify-write runs inside a single serialized transaction. Doing the
    SELECT on a separate read connection would let concurrent writers all read
    the same snapshot and clobber each other's samples.
    """
    try:
        async with _tx() as conn:
            cur = await conn.execute(
                "SELECT records FROM gate_health WHERE gate_key = ?", (gate_key,)
            )
            row = await cur.fetchone()
            records = []
            if row and isinstance(row[0], str):
                try:
                    records = json.loads(row[0])
                except Exception:
                    records = []
            if not isinstance(records, list):
                records = []
            records.append(bool(success))
            if len(records) > 100:
                records = records[-100:]
            await conn.execute(
                "INSERT INTO gate_health (gate_key, records) VALUES (?, ?) "
                "ON CONFLICT(gate_key) DO UPDATE SET records = excluded.records",
                (gate_key, json.dumps([1 if r else 0 for r in records])),
            )
        return True
    except Exception:
        return False


async def get_gate_health_records(gate_key: str):
    """Return the stored list of recent gate results (0/1 ints), or None."""
    try:
        row = await _fetch_one("SELECT records FROM gate_health WHERE gate_key = ?", (gate_key,))
        if not row or not row.get("records"):
            return None
        records = row["records"]
        if isinstance(records, str):
            try:
                records = json.loads(records)
            except Exception:
                return None
        return records if isinstance(records, list) else None
    except Exception:
        return None
