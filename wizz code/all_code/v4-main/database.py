import psycopg2
import psycopg2.pool
import psycopg2.extensions
from psycopg2.extras import RealDictCursor
from datetime import datetime
import threading
import time
import logging

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# DATABASE CONFIG  (edit only this block on your server)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

DB_CONFIG = {
    "host":     "localhost",
    "database": "broken",
    "user":     "chkx",
    "password": "SUBHAMOP90",     #🔴 replace with your real password
    "port":     5432,
    # Keep idle connections alive through NAT / firewalls
    "keepalives":          1,
    "keepalives_idle":     30,
    "keepalives_interval": 10,
    "keepalives_count":    5,
    # Hard cap how long a single query is allowed to run (seconds)
    "options":  "-c statement_timeout=30000",
}

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# POOL SETTINGS
#
# For 5 000 concurrent users with short-lived DB calls:
#   • minconn = 10  — always-ready workers
#   • maxconn = 80  — safely below PG's default 100-conn limit;
#                     raise to 150 if you bumped max_connections in pg
#
# Each "user command" typically holds a connection for < 50 ms,
# so 80 connections serve thousands of concurrent requests.
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

POOL_MIN = 10
POOL_MAX = 80

# How long (seconds) to keep retrying before giving up when pool is full
POOL_ACQUIRE_TIMEOUT = 15.0
# Base sleep between retries (doubles each attempt up to 1 s)
POOL_RETRY_BASE = 0.05

_pool: psycopg2.pool.ThreadedConnectionPool = None
_pool_lock = threading.Lock()


def _get_pool() -> psycopg2.pool.ThreadedConnectionPool:
    global _pool
    if _pool is not None and not _pool.closed:
        return _pool
    with _pool_lock:
        if _pool is None or _pool.closed:
            _pool = psycopg2.pool.ThreadedConnectionPool(POOL_MIN, POOL_MAX, **DB_CONFIG)
            logging.info(f"[DB] Connection pool created ({POOL_MIN}-{POOL_MAX} connections)")
    return _pool


def _acquire_raw() -> psycopg2.extensions.connection:
    """
    Borrow a raw connection from the pool.
    Retries with exponential back-off for up to POOL_ACQUIRE_TIMEOUT seconds
    so that brief spikes never produce "pool exhausted" errors.
    Also validates the connection and discards broken ones automatically.
    """
    deadline = time.monotonic() + POOL_ACQUIRE_TIMEOUT
    delay = POOL_RETRY_BASE

    while True:
        pool = _get_pool()
        try:
            conn = pool.getconn()
        except psycopg2.pool.PoolError:
            # Pool is full — wait and retry
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise RuntimeError(
                    "[DB] Connection pool exhausted: could not acquire a connection "
                    f"within {POOL_ACQUIRE_TIMEOUT}s. Consider raising POOL_MAX."
                )
            sleep_for = min(delay, remaining, 1.0)
            logging.warning(f"[DB] Pool exhausted — retrying in {sleep_for:.2f}s")
            time.sleep(sleep_for)
            delay = min(delay * 2, 1.0)
            continue

        # Validate the borrowed connection; replace if broken
        try:
            if conn.closed:
                raise psycopg2.OperationalError("connection closed")
            # Lightweight status check — no round-trip needed
            if conn.status != psycopg2.extensions.STATUS_READY:
                conn.reset()
        except Exception:
            # Discard the bad connection; the pool will open a fresh one next call
            try:
                pool.putconn(conn, close=True)
            except Exception:
                pass
            logging.warning("[DB] Discarded a broken connection, retrying …")
            continue

        return conn


def _release_raw(conn, close: bool = False) -> None:
    """Return a connection to the pool (or discard it if close=True)."""
    try:
        _get_pool().putconn(conn, close=close)
    except Exception as e:
        logging.warning(f"[DB] putconn error: {e}")


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# POOLED CONNECTION WRAPPER
#
# THE KEY FIX FOR sub.py:
# sub.py calls conn.close() on every connection it gets from
# get_db_connection().  On a raw psycopg2 connection that
# permanently destroys it, leaking it out of the pool forever.
# After ~50 commands the pool empties and all new requests block.
#
# This wrapper intercepts .close() and calls putconn() instead,
# so the connection is safely returned.  sub.py needs zero changes.
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class _PooledConnectionWrapper:
    """
    Thin proxy around a real psycopg2 connection.

    • All attribute access is forwarded to the underlying connection.
    • .close() returns the connection to the pool instead of destroying it.
    • Can also be used as a context manager (with _PooledConnectionWrapper()).
    • Thread-safe: the returned flag prevents double-return.
    """

    __slots__ = ("_conn", "_returned", "_lock")

    def __init__(self, conn: psycopg2.extensions.connection):
        object.__setattr__(self, "_conn",     conn)
        object.__setattr__(self, "_returned", False)
        object.__setattr__(self, "_lock",     threading.Lock())

    # ── proxy all normal attribute access to the real connection ──────────

    def __getattr__(self, name: str):
        return getattr(object.__getattribute__(self, "_conn"), name)

    def __setattr__(self, name: str, value):
        if name in self.__slots__:
            object.__setattr__(self, name, value)
        else:
            setattr(object.__getattribute__(self, "_conn"), name, value)

    # ── the critical override: intercept .close() ─────────────────────────

    def close(self) -> None:
        """Return the connection to the pool (never destroy it)."""
        lock = object.__getattribute__(self, "_lock")
        with lock:
            if object.__getattribute__(self, "_returned"):
                return          # already returned — nothing to do
            object.__setattr__(self, "_returned", True)

        conn = object.__getattribute__(self, "_conn")
        try:
            if conn.status == psycopg2.extensions.STATUS_IN_TRANSACTION:
                conn.rollback()
        except Exception:
            pass
        _release_raw(conn)

    # ── context-manager support ───────────────────────────────────────────

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        conn = object.__getattribute__(self, "_conn")
        if exc_type:
            try:
                conn.rollback()
            except Exception:
                pass
        self.close()
        return False

    def __del__(self):
        """Safety net: if the wrapper is GC-ed without close(), return it."""
        try:
            self.close()
        except Exception:
            pass


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# PUBLIC API — use these everywhere
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def get_db_connection() -> _PooledConnectionWrapper:
    """
    Borrow a connection from the pool wrapped so that .close() is safe.
    Compatible with all existing code that calls conn.close() directly.

    Preferred: use PooledConn() context manager for automatic return.
    """
    return _PooledConnectionWrapper(_acquire_raw())


class PooledConn:
    """
    Context manager: borrow a connection, then return it automatically.

    Usage:
        with PooledConn() as conn:
            cur = conn.cursor()
            ...
            conn.commit()
    """

    def __init__(self):
        self._wrapper: _PooledConnectionWrapper = None

    def __enter__(self) -> _PooledConnectionWrapper:
        self._wrapper = get_db_connection()
        return self._wrapper

    def __exit__(self, exc_type, *_):
        if self._wrapper is not None:
            if exc_type:
                try:
                    self._wrapper.rollback()
                except Exception:
                    pass
            self._wrapper.close()
        return False


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# IN-PROCESS TTL CACHES
# Cuts DB round-trips for hot read paths.
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

_gate_cache:    dict = {}
_gate_cache_ttl    = 30   # seconds — gate on/off rarely changes

_credits_cache: dict = {}
_credits_cache_ttl = 5    # short: credits change often

_premium_cache: dict = {}
_premium_cache_ttl = 60   # seconds — used by sub.py

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# SCHEMA INITIALIZATION
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def ensure_users_table():
    try:
        with PooledConn() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS users (
                    user_id    BIGINT PRIMARY KEY,
                    username   TEXT,
                    credits    INTEGER DEFAULT 0,
                    cc_checked INTEGER DEFAULT 0,
                    cc_charged INTEGER DEFAULT 0,
                    joined_at  TIMESTAMP
                )
            """)
            conn.commit()
        print("[DB] Users table checked.")
    except Exception as e:
        print(f"[DB] Error ensuring users table: {e}")


def ensure_stats_columns():
    try:
        with PooledConn() as conn:
            cursor = conn.cursor()
            cursor.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS cc_checked INTEGER DEFAULT 0")
            cursor.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS cc_charged INTEGER DEFAULT 0")
            conn.commit()
        print("[DB] Stats columns checked/created.")
    except Exception as e:
        print(f"[DB] Error checking stats columns: {e}")


def ensure_lifetime_stats_columns():
    """
    Idempotent migration: add the three lifetime counter columns if they don't
    exist.  Safe to call on every restart — existing data is never touched.
    """
    cols = [
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS cc_charged_lifetime  INTEGER DEFAULT 0",
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS cc_approved_lifetime INTEGER DEFAULT 0",
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS cc_declined_lifetime INTEGER DEFAULT 0",
    ]
    try:
        with PooledConn() as conn:
            cursor = conn.cursor()
            for col_sql in cols:
                try:
                    cursor.execute(col_sql)
                    conn.commit()
                except Exception:
                    conn.rollback()
        print("[DB] Lifetime stats columns checked/created.")
    except Exception as e:
        print(f"[DB] Error ensuring lifetime stats columns: {e}")


def ensure_proxy_table():
    try:
        with PooledConn() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS proxies (
                    id       SERIAL PRIMARY KEY,
                    user_id  BIGINT NOT NULL,
                    proxy    TEXT NOT NULL,
                    added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            conn.commit()
        print("[DB] Proxies table checked/created.")
    except Exception as e:
        print(f"[DB] Error creating proxies table: {e}")


def ensure_gate_table():
    try:
        with PooledConn() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS gate_status (
                    gate       TEXT PRIMARY KEY,
                    is_enabled BOOLEAN DEFAULT TRUE,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            conn.commit()
        print("[DB] Gate status table checked.")
    except Exception as e:
        print(f"[DB] Error creating gate table: {e}")


def ensure_keys_columns():
    """
    Extend the existing codes table with premium key fields.
    All new columns are nullable so existing codes (from /gen_code) are
    completely unaffected — they simply have NULL in these columns.

    A row is a premium key when plan_name IS NOT NULL.
    A row is a regular credit code when plan_name IS NULL.
    """
    try:
        with PooledConn() as conn:
            cursor = conn.cursor()
            for col_def in [
                "ALTER TABLE codes ADD COLUMN IF NOT EXISTS plan_name        TEXT",
                "ALTER TABLE codes ADD COLUMN IF NOT EXISTS duration_seconds BIGINT",
                "ALTER TABLE codes ADD COLUMN IF NOT EXISTS created_by       BIGINT",
                "ALTER TABLE codes ADD COLUMN IF NOT EXISTS expires_at       TIMESTAMP",
            ]:
                try:
                    cursor.execute(col_def)
                    conn.commit()
                except Exception:
                    conn.rollback()
        print("[DB] Keys columns checked/created.")
    except Exception as e:
        print(f"[DB] Error ensuring keys columns: {e}")


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# USER FUNCTIONS
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def get_user(user_id: int):
    with PooledConn() as conn:
        cur = conn.cursor(cursor_factory=RealDictCursor)
        cur.execute("SELECT * FROM users WHERE user_id = %s", (user_id,))
        return cur.fetchone()


def create_user(user_id: int, username: str, first_name: str = None):
    with PooledConn() as conn:
        cur = conn.cursor()
        cur.execute("""
            INSERT INTO users (user_id, username, first_name, credits, joined_at)
            VALUES (%s, %s, %s, %s, %s)
            ON CONFLICT (user_id) DO NOTHING
        """, (user_id, username, first_name, 150, datetime.now()))
        conn.commit()


def set_first_name(user_id: int, first_name: str):
    name = str(first_name or "").strip()[:64]
    if not name:
        return
    with PooledConn() as conn:
        cur = conn.cursor()
        cur.execute("UPDATE users SET first_name=%s WHERE user_id=%s", (name, user_id))
        conn.commit()


def get_user_credits(user_id: int) -> int:
    now = time.monotonic()
    cached = _credits_cache.get(user_id)
    if cached and now < cached[1]:
        return cached[0]
    with PooledConn() as conn:
        cur = conn.cursor()
        cur.execute("SELECT credits FROM users WHERE user_id = %s", (user_id,))
        result = cur.fetchone()
        credits = result[0] if result else 0
    _credits_cache[user_id] = (credits, now + _credits_cache_ttl)
    return credits


def update_credits(user_id: int, new_credits: int):
    with PooledConn() as conn:
        cur = conn.cursor()
        cur.execute("UPDATE users SET credits = %s WHERE user_id = %s", (new_credits, user_id))
        conn.commit()
    _credits_cache[user_id] = (new_credits, time.monotonic() + _credits_cache_ttl)


def deduct_credits_atomic(user_id: int, amount: int) -> int:
    """
    Atomically deducts `amount` credits in one SQL round-trip (floor 0).
    Replaces the racy get_user_credits() + update_credits() pattern.
    Returns new balance.
    """
    with PooledConn() as conn:
        cur = conn.cursor()
        cur.execute("""
            UPDATE users
               SET credits = GREATEST(credits - %s, 0)
             WHERE user_id = %s
         RETURNING credits
        """, (amount, user_id))
        row = cur.fetchone()
        conn.commit()
        new_credits = row[0] if row else 0
    _credits_cache[user_id] = (new_credits, time.monotonic() + _credits_cache_ttl)
    return new_credits


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# STATS FUNCTIONS
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def update_user_stats(user_id: int, is_charged: bool):
    """Single combined query instead of two separate ones."""
    with PooledConn() as conn:
        cur = conn.cursor()
        if is_charged:
            cur.execute("""
                UPDATE users
                   SET cc_checked = cc_checked + 1,
                       cc_charged = cc_charged + 1
                 WHERE user_id = %s
            """, (user_id,))
        else:
            cur.execute(
                "UPDATE users SET cc_checked = cc_checked + 1 WHERE user_id = %s",
                (user_id,)
            )
        conn.commit()


def increment_lifetime_stats(user_id: int, charged: int = 0, approved: int = 0, declined: int = 0):
    """
    Atomically increment the lifetime counter columns for a user in a single
    SQL round-trip.  Pass keyword arguments only for the counters that changed.

    CHARGED  — funds were actually deducted from the card.
    APPROVED — card is valid but no funds were deducted (auth-only / 3DS, etc.).
    DECLINED — card was rejected by the issuer.
    """
    if charged == 0 and approved == 0 and declined == 0:
        return  # nothing to do

    with PooledConn() as conn:
        cur = conn.cursor()
        cur.execute("""
            UPDATE users
               SET cc_charged_lifetime  = cc_charged_lifetime  + %s,
                   cc_approved_lifetime = cc_approved_lifetime + %s,
                   cc_declined_lifetime = cc_declined_lifetime + %s
             WHERE user_id = %s
        """, (charged, approved, declined, user_id))
        conn.commit()


def get_user_lifetime_stats(user_id: int) -> dict:
    """
    Return the lifetime checker statistics for a single user.
    Keys: cc_charged_lifetime, cc_approved_lifetime, cc_declined_lifetime.
    Returns zeros if the user row doesn't exist.
    """
    with PooledConn() as conn:
        cur = conn.cursor()
        cur.execute("""
            SELECT cc_charged_lifetime, cc_approved_lifetime, cc_declined_lifetime
              FROM users
             WHERE user_id = %s
        """, (user_id,))
        row = cur.fetchone()
    if row:
        return {
            "cc_charged_lifetime":  row[0] or 0,
            "cc_approved_lifetime": row[1] or 0,
            "cc_declined_lifetime": row[2] or 0,
        }
    return {"cc_charged_lifetime": 0, "cc_approved_lifetime": 0, "cc_declined_lifetime": 0}


def get_all_lifetime_stats_totals() -> dict:
    """
    Return the sum of all lifetime counters across every user, plus the total
    user count.  Used by the /all admin command.
    """
    with PooledConn() as conn:
        cur = conn.cursor()
        cur.execute("""
            SELECT
                COUNT(*)                          AS total_users,
                COALESCE(SUM(cc_charged_lifetime),  0) AS total_charged,
                COALESCE(SUM(cc_approved_lifetime), 0) AS total_approved,
                COALESCE(SUM(cc_declined_lifetime), 0) AS total_declined
              FROM users
        """)
        row = cur.fetchone()
    if row:
        return {
            "total_users":    row[0] or 0,
            "total_charged":  row[1] or 0,
            "total_approved": row[2] or 0,
            "total_declined": row[3] or 0,
        }
    return {"total_users": 0, "total_charged": 0, "total_approved": 0, "total_declined": 0}


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# GATE FUNCTIONS  — cached
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def is_gate_enabled(gate: str) -> bool:
    now = time.monotonic()
    cached = _gate_cache.get(gate)
    if cached and now < cached[1]:
        return cached[0]

    with PooledConn() as conn:
        cur = conn.cursor()
        cur.execute("""
            INSERT INTO gate_status (gate, is_enabled)
            VALUES (%s, TRUE)
            ON CONFLICT (gate) DO NOTHING
        """, (gate,))
        cur.execute("SELECT is_enabled FROM gate_status WHERE gate = %s", (gate,))
        row = cur.fetchone()
        conn.commit()
        status = bool(row[0]) if row else True

    _gate_cache[gate] = (status, now + _gate_cache_ttl)
    return status


def set_gate_status(gate: str, enabled: bool):
    with PooledConn() as conn:
        cur = conn.cursor()
        cur.execute("""
            INSERT INTO gate_status (gate, is_enabled)
            VALUES (%s, %s)
            ON CONFLICT (gate)
            DO UPDATE SET
                is_enabled = EXCLUDED.is_enabled,
                updated_at = CURRENT_TIMESTAMP
        """, (gate, enabled))
        conn.commit()
    _gate_cache[gate] = (enabled, time.monotonic() + _gate_cache_ttl)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# GATE REGISTRY + BULK OPERATIONS
# ALL_GATES is the canonical list of gate keys. Keep in sync with
# every is_gate_enabled("<key>") call site in gates/, mass_gates/,
# tools/ and split.py.
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

ALL_GATES: tuple = (
    # ── Single auth / charge gates ──
    "st",    # Stripe 1$
    "sh",    # Shopify
    "sp",    # Shopify 1$
    "pg",    # Payglocal 0.10$
    "hc",    # Shopify 5$
    "pf",    # PayFast
    "vbv",   # 3DS / VBV lookup
    "ft",    # FatZebra
    "bl",    # BluePay
    "pp",    # PayPal
    "at",    # Authorize.Net
    "pw",    # Payway
    "rz",    # Razorpay
    "pyu",   # PayU
    "b3",    # Braintree
    "py",    # Pyyup
    "nmi",   # NMI
    "nmi2",  # Payflow
    "sk",    # SK based
    "chk",   # Chk auth
    "ch",    # Chase auth
    "cl",    # Chargebee
    # ── Mass gates ──
    "msh",   # Mass Stripe / SK hit
    "mst",   # Mass Stripe
    "msk",   # Mass SK
    "mchk",  # Mass check
    "mrz",   # Mass Razorpay
    "mpp",   # Mass PayPal
    # ── Tools ──
    "scr",   # Telegram scraper
    "clean", # Card cleaner / splitter / shuffler
)


def is_known_gate(gate: str) -> bool:
    return gate in ALL_GATES


def get_all_gate_status() -> dict:
    """Return {gate: is_enabled} for every known gate."""
    status = {g: True for g in ALL_GATES}
    with PooledConn() as conn:
        cur = conn.cursor()
        cur.execute("SELECT gate, is_enabled FROM gate_status")
        rows = cur.fetchall()
    now = time.monotonic()
    for gate, enabled in rows:
        enabled = bool(enabled)
        status[gate] = enabled
        _gate_cache[gate] = (enabled, now + _gate_cache_ttl)
    return status


def set_gate_status_bulk(enabled: bool, gates=None) -> list:
    """
    Set every gate in `gates` (default: ALL_GATES) to `enabled`.
    Returns the list of gate names that were changed.
    """
    targets = list(ALL_GATES if gates is None else gates)
    if not targets:
        return []

    with PooledConn() as conn:
        cur = conn.cursor()
        cur.executemany("""
            INSERT INTO gate_status (gate, is_enabled)
            VALUES (%s, %s)
            ON CONFLICT (gate) DO UPDATE SET
                is_enabled = EXCLUDED.is_enabled,
                updated_at = CURRENT_TIMESTAMP
        """, [(g, enabled) for g in targets])
        conn.commit()

    now = time.monotonic()
    for g in targets:
        _gate_cache[g] = (enabled, now + _gate_cache_ttl)
    return targets


def clear_gate_cache(gate: str = None):
    """Drop cached gate status for one gate, or all gates if None."""
    if gate is None:
        _gate_cache.clear()
    else:
        _gate_cache.pop(gate, None)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# GLOBAL PROXY POOL  — owner-managed, shared across all users
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def create_global_proxy_table():
    try:
        with PooledConn() as conn:
            cur = conn.cursor()
            cur.execute("""
                CREATE TABLE IF NOT EXISTS global_proxies (
                    id             SERIAL PRIMARY KEY,
                    proxy          TEXT UNIQUE NOT NULL,
                    status         TEXT DEFAULT 'active',
                    fail_count     INTEGER DEFAULT 0,
                    success_count  INTEGER DEFAULT 0,
                    cooldown_until TIMESTAMP,
                    last_used      TIMESTAMP,
                    created_at     TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            conn.commit()
        print("[DB] Global proxies table checked/created.")
    except Exception as e:
        print(f"[DB] Error creating global_proxies table: {e}")


def add_global_proxy(proxy: str) -> str:
    """
    Insert a proxy into global_proxies (UNIQUE constraint prevents duplicates).
    Returns 'added' if new, 'exists' if already present.
    """
    try:
        with PooledConn() as conn:
            cur = conn.cursor()
            cur.execute("""
                INSERT INTO global_proxies (proxy)
                VALUES (%s)
                ON CONFLICT (proxy) DO NOTHING
            """, (proxy,))
            inserted = cur.rowcount
            conn.commit()
        return 'added' if inserted else 'exists'
    except Exception as e:
        logging.error(f"[DB] add_global_proxy error: {e}")
        return 'error'


def remove_global_proxy(proxy: str) -> bool:
    """Remove a specific proxy from the global pool. Returns True if deleted."""
    try:
        with PooledConn() as conn:
            cur = conn.cursor()
            cur.execute("DELETE FROM global_proxies WHERE proxy = %s", (proxy,))
            deleted = cur.rowcount
            conn.commit()
        return deleted > 0
    except Exception as e:
        logging.error(f"[DB] remove_global_proxy error: {e}")
        return False


def clear_global_proxies() -> int:
    """Delete all proxies from the global pool. Returns count deleted."""
    try:
        with PooledConn() as conn:
            cur = conn.cursor()
            cur.execute("SELECT COUNT(*) FROM global_proxies")
            count = cur.fetchone()[0]
            cur.execute("DELETE FROM global_proxies")
            conn.commit()
        return count
    except Exception as e:
        logging.error(f"[DB] clear_global_proxies error: {e}")
        return 0


def get_global_proxies() -> list:
    """Return all proxy strings from the global pool (status = active)."""
    try:
        with PooledConn() as conn:
            cur = conn.cursor()
            cur.execute("""
                SELECT proxy FROM global_proxies
                WHERE status = 'active'
                   OR cooldown_until IS NULL
                   OR cooldown_until <= NOW()
                ORDER BY id
            """)
            rows = cur.fetchall()
        return [row[0] for row in rows]
    except Exception as e:
        logging.error(f"[DB] get_global_proxies error: {e}")
        return []


def get_global_proxy_count() -> int:
    """Return total count of proxies in the global pool."""
    try:
        with PooledConn() as conn:
            cur = conn.cursor()
            cur.execute("SELECT COUNT(*) FROM global_proxies")
            return cur.fetchone()[0]
    except Exception as e:
        logging.error(f"[DB] get_global_proxy_count error: {e}")
        return 0


def mark_proxy_success(proxy: str):
    """Increment success_count and clear any cooldown for a proxy."""
    try:
        with PooledConn() as conn:
            cur = conn.cursor()
            cur.execute("""
                UPDATE global_proxies
                   SET success_count  = success_count + 1,
                       status         = 'active',
                       cooldown_until = NULL,
                       last_used      = NOW()
                 WHERE proxy = %s
            """, (proxy,))
            conn.commit()
    except Exception as e:
        logging.error(f"[DB] mark_proxy_success error: {e}")


def mark_proxy_failed(proxy: str, cooldown_seconds: int = 300):
    """Increment fail_count and set a cooldown_until timestamp."""
    try:
        with PooledConn() as conn:
            cur = conn.cursor()
            cur.execute("""
                UPDATE global_proxies
                   SET fail_count     = fail_count + 1,
                       status         = 'cooldown',
                       cooldown_until = NOW() + (%s || ' seconds')::INTERVAL,
                       last_used      = NOW()
                 WHERE proxy = %s
            """, (cooldown_seconds, proxy))
            conn.commit()
    except Exception as e:
        logging.error(f"[DB] mark_proxy_failed error: {e}")


def reset_failed_proxies():
    """Reset all proxies whose cooldown has expired back to active."""
    try:
        with PooledConn() as conn:
            cur = conn.cursor()
            cur.execute("""
                UPDATE global_proxies
                   SET status         = 'active',
                       cooldown_until = NULL
                 WHERE status = 'cooldown'
                   AND cooldown_until <= NOW()
            """)
            reset_count = cur.rowcount
            conn.commit()
        return reset_count
    except Exception as e:
        logging.error(f"[DB] reset_failed_proxies error: {e}")
        return 0


def proxy_statistics() -> dict:
    """Return aggregate statistics for the global proxy pool."""
    try:
        with PooledConn() as conn:
            cur = conn.cursor()
            cur.execute("""
                SELECT
                    COUNT(*)                                         AS total,
                    SUM(CASE WHEN status = 'active' THEN 1 ELSE 0 END) AS active,
                    SUM(CASE WHEN status = 'cooldown'
                              AND cooldown_until > NOW() THEN 1 ELSE 0 END) AS on_cooldown,
                    AVG(fail_count)                                  AS avg_fail_count
                FROM global_proxies
            """)
            row = cur.fetchone()
        if row:
            return {
                "total":         row[0] or 0,
                "active":        row[1] or 0,
                "on_cooldown":   row[2] or 0,
                "avg_fail_count": float(row[3] or 0),
            }
        return {}
    except Exception as e:
        logging.error(f"[DB] proxy_statistics error: {e}")
        return {}


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# RUN INITIALIZATION
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

ensure_users_table()
ensure_stats_columns()
ensure_lifetime_stats_columns()  # ← adds cc_charged/approved/declined_lifetime columns
ensure_proxy_table()
ensure_gate_table()
ensure_keys_columns()        # ← extends codes table for premium keys
create_global_proxy_table()  # ← global shared proxy pool
