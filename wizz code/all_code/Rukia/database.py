import sqlite3
import threading
import time
import logging
import os
import hashlib
import json
from datetime import datetime
from typing import Optional

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# DATABASE CONFIG
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "bot.db")

DB_CONFIG = {"path": DB_PATH}
MONGO_URI = f"sqlite://{DB_PATH}"
DB_NAME = "telegram_bot"


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# DATETIME HELPERS  ★ FIXED
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def _to_dt(value):
    """Parse a stored datetime value into a real datetime object.
    Handles: None, datetime (passthrough), ISO with T, ISO with space,
    'YYYY-MM-DD HH:MM:SS', 'YYYY-MM-DD'."""
    if value is None:
        return None
    if isinstance(value, datetime):
        return value
    if not isinstance(value, str):
        return value
    s = value.strip()
    if not s:
        return None
    # Try ISO first (T separator)
    try:
        return datetime.fromisoformat(s)
    except Exception:
        pass
    # Try space separator
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M:%S.%f",
                "%Y-%m-%d", "%Y-%m-%dT%H:%M:%S.%fZ",
                "%Y-%m-%dT%H:%M:%SZ"):
        try:
            return datetime.strptime(s, fmt)
        except Exception:
            continue
    return None


def _from_dt(value):
    """Serialize a datetime (or passthrough a string) for storage."""
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.isoformat()
    return str(value)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# CONNECTION
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

_local = threading.local()
_init_lock = threading.Lock()
_initialized = False


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH, timeout=30, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    return conn


def _get_conn() -> sqlite3.Connection:
    conn = getattr(_local, "conn", None)
    if conn is None:
        conn = _connect()
        _local.conn = conn
    return conn


def get_db_connection():
    return _get_conn()


class PooledConn:
    def __enter__(self):  return _get_conn()
    def __exit__(self, *args): pass


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# CACHES
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

_gate_cache = {};       _gate_cache_ttl = 30
_credits_cache = {};    _credits_cache_ttl = 5
_premium_cache = {};    _premium_cache_ttl = 5


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# NATIVE SCHEMA
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

_SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    user_id         INTEGER PRIMARY KEY,
    username        TEXT,
    first_name      TEXT DEFAULT '',
    credits         INTEGER DEFAULT 150,
    cc_checked      INTEGER DEFAULT 0,
    cc_charged      INTEGER DEFAULT 0,
    is_premium      INTEGER DEFAULT 0,
    premium_expiry  TEXT,
    unlimited_msh   INTEGER DEFAULT 0,
    joined_at       TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS gate_status (
    gate        TEXT PRIMARY KEY,
    is_enabled  INTEGER DEFAULT 1,
    updated_at  TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS banned_users (
    user_id     INTEGER PRIMARY KEY,
    reason      TEXT,
    banned_at   TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS receipts (
    receipt_id  TEXT PRIMARY KEY,
    user_id     INTEGER,
    plan        TEXT,
    plan_name   TEXT,
    days        INTEGER,
    created_at  TEXT DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_receipts_user ON receipts(user_id);

CREATE TABLE IF NOT EXISTS codes (
    code        TEXT PRIMARY KEY,
    credits     INTEGER DEFAULT 0,
    days        INTEGER DEFAULT 0,
    max_uses    INTEGER DEFAULT 1,
    uses        INTEGER DEFAULT 0,
    created_at  TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS proxies (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id     INTEGER,
    proxy       TEXT,
    added_at    TEXT DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_proxies_user ON proxies(user_id);

CREATE TABLE IF NOT EXISTS charged_hits (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id     INTEGER,
    username    TEXT,
    first_name  TEXT,
    ts          TEXT DEFAULT CURRENT_TIMESTAMP,
    line_hash   TEXT
);
CREATE INDEX IF NOT EXISTS idx_hits_user ON charged_hits(user_id);
CREATE INDEX IF NOT EXISTS idx_hits_ts   ON charged_hits(ts);
CREATE INDEX IF NOT EXISTS idx_hits_hash ON charged_hits(line_hash);
"""


def _init_schema():
    global _initialized
    with _init_lock:
        if _initialized:
            return
        conn = _get_conn()
        conn.executescript(_SCHEMA)
        conn.commit()
        _initialized = True
        logging.info(f"[DB] SQLite ready at {DB_PATH}")


def ensure_users_table():               _init_schema()
def ensure_stats_columns():             _init_schema()
def ensure_proxy_table():               _init_schema()
def ensure_gate_table():                _init_schema()
def ensure_banned_table():              _init_schema()
def ensure_receipts_table():            _init_schema()
def ensure_codes_table():               _init_schema()
def ensure_charged_hits_collection():   _init_schema()


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# USER FUNCTIONS  ★ FIXED — datetime conversions everywhere
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def get_user(user_id: int):
    conn = _get_conn()
    row = conn.execute("SELECT * FROM users WHERE user_id = ?", (user_id,)).fetchone()
    if not row:
        return None
    d = dict(row)
    # ★ Always convert these to real datetime objects
    d["joined_at"]      = _to_dt(d.get("joined_at"))
    d["premium_expiry"] = _to_dt(d.get("premium_expiry"))
    return d


def create_user(user_id: int, username: str):
    conn = _get_conn()
    conn.execute(
        """INSERT OR IGNORE INTO users
           (user_id, username, first_name, credits, cc_checked, cc_charged,
            is_premium, premium_expiry, unlimited_msh, joined_at)
           VALUES (?, ?, '', 150, 0, 0, 0, NULL, 0, ?)""",
        (user_id, username, datetime.now().isoformat()),
    )
    conn.commit()


def is_unlimited_msh(user_id: int) -> bool:
    row = _get_conn().execute(
        "SELECT unlimited_msh FROM users WHERE user_id = ?", (user_id,)
    ).fetchone()
    return bool(row["unlimited_msh"]) if row else False


def set_unlimited_msh(user_id: int, value: bool) -> bool:
    conn = _get_conn()
    conn.execute(
        """INSERT INTO users (user_id, unlimited_msh) VALUES (?, ?)
           ON CONFLICT(user_id) DO UPDATE SET unlimited_msh = excluded.unlimited_msh""",
        (user_id, 1 if value else 0),
    )
    conn.commit()
    return value


def get_user_credits(user_id: int) -> int:
    now = time.monotonic()
    c = _credits_cache.get(user_id)
    if c and now < c[1]:
        return c[0]
    row = _get_conn().execute(
        "SELECT credits FROM users WHERE user_id = ?", (user_id,)
    ).fetchone()
    credits = row["credits"] if row else 0
    _credits_cache[user_id] = (credits, now + _credits_cache_ttl)
    return credits


def update_credits(user_id: int, new_credits: int):
    conn = _get_conn()
    conn.execute("UPDATE users SET credits = ? WHERE user_id = ?", (new_credits, user_id))
    conn.commit()
    _credits_cache[user_id] = (new_credits, time.monotonic() + _credits_cache_ttl)


def deduct_credits_atomic(user_id: int, amount: int) -> int:
    conn = _get_conn()
    row = conn.execute("SELECT credits FROM users WHERE user_id = ?", (user_id,)).fetchone()
    current = row["credits"] if row else 0
    new_val = max(current - amount, 0)
    conn.execute("UPDATE users SET credits = ? WHERE user_id = ?", (new_val, user_id))
    conn.commit()
    _credits_cache[user_id] = (new_val, time.monotonic() + _credits_cache_ttl)
    return new_val


def update_user_stats(user_id: int, is_charged: bool):
    conn = _get_conn()
    if is_charged:
        conn.execute(
            "UPDATE users SET cc_checked = cc_checked + 1, cc_charged = cc_charged + 1 WHERE user_id = ?",
            (user_id,),
        )
    else:
        conn.execute("UPDATE users SET cc_checked = cc_checked + 1 WHERE user_id = ?", (user_id,))
    conn.commit()


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# GATE FUNCTIONS
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def is_gate_enabled(gate: str) -> bool:
    now = time.monotonic()
    c = _gate_cache.get(gate)
    if c and now < c[1]:
        return c[0]
    conn = _get_conn()
    conn.execute("INSERT OR IGNORE INTO gate_status (gate, is_enabled) VALUES (?, 1)", (gate,))
    conn.commit()
    row = conn.execute("SELECT is_enabled FROM gate_status WHERE gate = ?", (gate,)).fetchone()
    status = bool(row["is_enabled"]) if row else True
    _gate_cache[gate] = (status, now + _gate_cache_ttl)
    return status


def set_gate_status(gate: str, enabled: bool):
    conn = _get_conn()
    conn.execute(
        """INSERT INTO gate_status (gate, is_enabled, updated_at) VALUES (?, ?, ?)
           ON CONFLICT(gate) DO UPDATE SET
             is_enabled = excluded.is_enabled, updated_at = excluded.updated_at""",
        (gate, 1 if enabled else 0, datetime.now().isoformat()),
    )
    conn.commit()
    _gate_cache[gate] = (enabled, time.monotonic() + _gate_cache_ttl)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# CHARGED HITS
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

_MSHH_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "mshh.txt")
_MSHH_LOCK = threading.Lock()
_MIGRATION_DONE = False
_MIGRATION_LOCK = threading.Lock()


def _append_mshh_line(user_id: int, username: str, first_name: str) -> None:
    try:
        line = f"{int(user_id)}|{(username or 'None')}|{(first_name or 'Unknown')}\n"
        with _MSHH_LOCK:
            with open(_MSHH_PATH, "a", encoding="utf-8") as f:
                f.write(line)
    except Exception as e:
        logging.warning(f"_append_mshh_line backup write failed: {e}")


def add_charged_hit(user_id: int, username: str, first_name: str):
    safe_user = int(user_id)
    safe_uname = username if username else "None"
    safe_fname = first_name if first_name else "Unknown"
    try:
        conn = _get_conn()
        conn.execute(
            "INSERT INTO charged_hits (user_id, username, first_name, ts) VALUES (?, ?, ?, ?)",
            (safe_user, safe_uname, safe_fname, datetime.now().isoformat()),
        )
        conn.commit()
    except Exception as e:
        logging.error(f"add_charged_hit {safe_user}: {e}")
    _append_mshh_line(safe_user, safe_uname, safe_fname)


def _read_mshh_lines():
    out = []
    try:
        if not os.path.isfile(_MSHH_PATH):
            return out
        with _MSHH_LOCK:
            with open(_MSHH_PATH, "r", encoding="utf-8", errors="ignore") as f:
                for raw in f:
                    line = raw.strip()
                    if not line:
                        continue
                    parts = line.split("|", 2)
                    if len(parts) < 3:
                        continue
                    try:
                        uid = int(parts[0])
                    except ValueError:
                        continue
                    out.append((uid, parts[1], parts[2]))
    except Exception as e:
        logging.error(f"_read_mshh_lines: {e}")
    return out


def _aggregate_from_mshh(limit: int = 10):
    from collections import Counter
    lines = _read_mshh_lines()
    if not lines:
        return [], {}
    counts = Counter()
    details = {}
    for uid, uname, fname in reversed(lines):
        counts[uid] += 1
        if uid not in details:
            details[uid] = {
                "username": uname if uname and uname != "None" else None,
                "first_name": fname if fname and fname != "Unknown" else "Unknown",
            }
    ranked = counts.most_common(limit)
    top_users = [(str(uid), cnt) for uid, cnt in ranked]
    user_details = {str(uid): details[uid] for uid, _ in ranked}
    return top_users, user_details


def migrate_mshh_to_atlas():
    global _MIGRATION_DONE
    with _MIGRATION_LOCK:
        if _MIGRATION_DONE:
            return (0, 0, 0)
        _MIGRATION_DONE = True

    if not os.path.isfile(_MSHH_PATH):
        return (0, 0, 0)
    lines = _read_mshh_lines()
    if not lines:
        return (0, 0, 0)

    inserted = skipped = errors = 0
    try:
        conn = _get_conn()
        for idx, (uid, uname, fname) in enumerate(lines):
            payload = f"{idx}|{uid}|{uname}|{fname}".encode("utf-8")
            line_hash = hashlib.sha1(payload).hexdigest()[:16]
            if conn.execute("SELECT 1 FROM charged_hits WHERE line_hash = ?", (line_hash,)).fetchone():
                skipped += 1
                continue
            conn.execute(
                "INSERT INTO charged_hits (user_id, username, first_name, ts, line_hash) VALUES (?, ?, ?, ?, ?)",
                (int(uid), uname, fname, datetime.now().isoformat(), line_hash),
            )
            inserted += 1
        conn.commit()
        if inserted or skipped:
            print(f"[DB] mshh.txt -> SQLite migration: inserted={inserted}, skipped={skipped}")
    except Exception as e:
        logging.error(f"migrate_mshh_to_atlas: {e}")
        errors += 1
    return (inserted, skipped, errors)


def get_charged_leaderboard(limit: int = 10):
    try:
        conn = _get_conn()
        rows = conn.execute(
            """
            SELECT user_id, COUNT(*) AS cnt,
                   (SELECT username   FROM charged_hits c2 WHERE c2.user_id = c1.user_id ORDER BY ts DESC LIMIT 1) AS username,
                   (SELECT first_name FROM charged_hits c2 WHERE c2.user_id = c1.user_id ORDER BY ts DESC LIMIT 1) AS first_name
            FROM charged_hits c1
            GROUP BY user_id
            ORDER BY cnt DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
        top_users, user_details = [], {}
        for r in rows:
            uid = str(r["user_id"])
            top_users.append((uid, r["cnt"]))
            uname = r["username"]
            fname = r["first_name"] or "Unknown"
            user_details[uid] = {
                "username": uname if uname and uname != "None" else None,
                "first_name": fname if fname and fname != "Unknown" else "Unknown",
            }
        if top_users:
            return top_users, user_details
        return _aggregate_from_mshh(limit=limit)
    except Exception as e:
        logging.error(f"get_charged_leaderboard: {e}")
        try:
            return _aggregate_from_mshh(limit=limit)
        except Exception:
            return [], {}


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# GLOBAL PROXY POOL
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

GLOBAL_PROXIES_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "proxies.txt")


def load_global_proxies() -> list:
    try:
        if not os.path.exists(GLOBAL_PROXIES_FILE):
            return []
        with open(GLOBAL_PROXIES_FILE, "r", encoding="utf-8", errors="ignore") as f:
            return [line.strip() for line in f if line.strip()]
    except Exception as e:
        logging.error(f"Error loading global proxies: {e}")
        return []


def to_http_proxy_url(raw: str) -> Optional[str]:
    parts = raw.split(":")
    if len(parts) != 4:
        return None
    host, port, user, password = parts
    if not host or not port.isdigit() or not (1 <= int(port) <= 65535):
        return None
    return f"http://{user}:{password}@{host}:{port}"


def load_global_proxies_http() -> list:
    return [u for u in (to_http_proxy_url(p) for p in load_global_proxies()) if u]


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# MONGO-COMPAT SHIM  ★ FIXED — datetimes returned to callers
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


class _FakeCursorResult:
    def __init__(self, docs): self._docs = list(docs)
    def __iter__(self):        return iter(self._docs)
    def sort(self, *a, **kw):  return self
    def limit(self, n):        self._docs = self._docs[:n]; return self
    def skip(self, n):         self._docs = self._docs[n:]; return self


def _match(doc: dict, query: dict) -> bool:
    for k, v in query.items():
        if k.startswith("$"):
            continue
        val = doc.get(k)
        if isinstance(v, dict):
            for op, ov in v.items():
                if op == "$in"  and val not in ov:                       return False
                if op == "$nin" and val in ov:                           return False
                if op == "$ne"  and val == ov:                           return False
                if op == "$gt"  and not (val is not None and val > ov):  return False
                if op == "$lt"  and not (val is not None and val < ov):  return False
                if op == "$gte" and not (val is not None and val >= ov): return False
                if op == "$lte" and not (val is not None and val <= ov): return False
                if op == "$exists":
                    if (ov and val is None) or (not ov and val is not None):
                        return False
        else:
            if val != v:
                return False
    return True


def _project(doc: dict, projection):
    if not projection:
        return doc
    keep = {k for k, v in projection.items() if v}
    drop = {k for k, v in projection.items() if not v}
    if keep:
        return {k: doc.get(k) for k in keep if k in doc}
    return {k: v for k, v in doc.items() if k not in drop}


def _apply_ops(doc: dict, ops: dict):
    for op, fields in ops.items():
        if op == "$set":
            doc.update(fields)
        elif op == "$inc":
            for f, n in fields.items():
                doc[f] = (doc.get(f) or 0) + n
        elif op == "$setOnInsert":
            for f, v in fields.items():
                doc.setdefault(f, v)
        elif op == "$unset":
            for f in fields:
                doc.pop(f, None)


# ★ Fields in "users" table that should be converted back to datetime on read
_DT_FIELDS = {"joined_at", "premium_expiry", "created_at", "banned_at",
              "updated_at", "ts", "added_at", "expires_at", "expiry"}


def _hydrate_datetimes(doc: dict) -> dict:
    """Convert known datetime fields in a shim-returned doc from str → datetime."""
    for k in list(doc.keys()):
        if k in _DT_FIELDS and isinstance(doc[k], str):
            dt = _to_dt(doc[k])
            if dt is not None:
                doc[k] = dt
    return doc


def _dehydrate_datetimes(doc: dict) -> dict:
    """Convert datetime values to strings before serializing to JSON."""
    for k in list(doc.keys()):
        if isinstance(doc[k], datetime):
            doc[k] = doc[k].isoformat()
    return doc


class _SQLiteCollectionShim:
    def __init__(self, name: str):
        self.name = name
        self.table = f"_mongo_{name}"
        self._ensure_table()

    def _ensure_table(self):
        conn = _get_conn()
        conn.execute(
            f"CREATE TABLE IF NOT EXISTS {self.table} ("
            f"  _id TEXT PRIMARY KEY, _doc TEXT NOT NULL)"
        )
        conn.commit()

    def _all_docs(self):
        rows = _get_conn().execute(f"SELECT _doc FROM {self.table}").fetchall()
        out = []
        for (raw,) in rows:
            try:    out.append(json.loads(raw))
            except Exception: pass
        return out

    def find_one(self, query=None, projection=None, **kw):
        for d in self._all_docs():
            if _match(d, query or {}):
                return _hydrate_datetimes(_project(d, projection))
        return None

    def find(self, query=None, projection=None, **kw):
        return _FakeCursorResult(
            _hydrate_datetimes(_project(d, projection))
            for d in self._all_docs() if _match(d, query or {})
        )

    def count_documents(self, query=None, **kw):
        return sum(1 for d in self._all_docs() if _match(d, query or {}))

    def insert_one(self, doc):
        conn = _get_conn()
        d = _dehydrate_datetimes(dict(doc))  # ★ convert datetimes → str
        _id = d.get("_id") or hashlib.sha1(
            json.dumps(d, default=str, sort_keys=True).encode()
            + str(time.time_ns()).encode()
        ).hexdigest()
        d["_id"] = _id
        conn.execute(
            f"INSERT INTO {self.table} (_id, _doc) VALUES (?, ?)",
            (_id, json.dumps(d, default=str)),
        )
        conn.commit()
        return type("R", (), {"inserted_id": _id})()

    def insert_many(self, docs, ordered=False):
        return type("R", (), {"inserted_ids": [self.insert_one(d).inserted_id for d in docs]})()

    def update_one(self, query, update, upsert=False):
        conn = _get_conn()
        for _id, raw in conn.execute(f"SELECT _id, _doc FROM {self.table}").fetchall():
            d = json.loads(raw)
            if _match(d, query or {}):
                # ★ convert any datetime values in $set before applying
                upd = dict(update or {})
                if "$set" in upd:
                    upd["$set"] = {
                        k: (v.isoformat() if isinstance(v, datetime) else v)
                        for k, v in upd["$set"].items()
                    }
                _apply_ops(d, upd)
                conn.execute(
                    f"UPDATE {self.table} SET _doc = ? WHERE _id = ?",
                    (json.dumps(d, default=str), _id),
                )
                conn.commit()
                return type("R", (), {"modified_count": 1})()
        if upsert:
            d = _dehydrate_datetimes(dict(query or {}))
            upd = dict(update or {})
            if "$set" in upd:
                upd["$set"] = {
                    k: (v.isoformat() if isinstance(v, datetime) else v)
                    for k, v in upd["$set"].items()
                }
            _apply_ops(d, upd)
            res = self.insert_one(d)
            return type("R", (), {"modified_count": 0, "upserted_id": res.inserted_id})()
        return type("R", (), {"modified_count": 0})()

    def update_many(self, query, update):
        conn = _get_conn()
        n = 0
        for _id, raw in conn.execute(f"SELECT _id, _doc FROM {self.table}").fetchall():
            d = json.loads(raw)
            if _match(d, query or {}):
                upd = dict(update or {})
                if "$set" in upd:
                    upd["$set"] = {
                        k: (v.isoformat() if isinstance(v, datetime) else v)
                        for k, v in upd["$set"].items()
                    }
                _apply_ops(d, upd)
                conn.execute(
                    f"UPDATE {self.table} SET _doc = ? WHERE _id = ?",
                    (json.dumps(d, default=str), _id),
                )
                n += 1
        conn.commit()
        return type("R", (), {"modified_count": n})()

    def delete_one(self, query):
        conn = _get_conn()
        for _id, raw in conn.execute(f"SELECT _id, _doc FROM {self.table}").fetchall():
            d = json.loads(raw)
            if _match(d, query or {}):
                conn.execute(f"DELETE FROM {self.table} WHERE _id = ?", (_id,))
                conn.commit()
                return type("R", (), {"deleted_count": 1})()
        return type("R", (), {"deleted_count": 0})()

    def delete_many(self, query):
        conn = _get_conn()
        ids = [ _id for _id, raw in conn.execute(
                    f"SELECT _id, _doc FROM {self.table}").fetchall()
                if _match(json.loads(raw), query or {}) ]
        for _id in ids:
            conn.execute(f"DELETE FROM {self.table} WHERE _id = ?", (_id,))
        conn.commit()
        return type("R", (), {"deleted_count": len(ids)})()

    def create_index(self, *a, **kw):  return None
    def drop(self):                    return None

    def aggregate(self, pipeline, **kw):
        docs = self._all_docs()
        for stage in pipeline:
            if "$match" in stage:
                docs = [d for d in docs if _match(d, stage["$match"])]
            elif "$sort" in stage:
                for k, direction in reversed(list(stage["$sort"].items())):
                    docs.sort(key=lambda x: (x.get(k) is None, x.get(k)), reverse=direction < 0)
            elif "$limit" in stage:
                docs = docs[: stage["$limit"]]
            elif "$skip" in stage:
                docs = docs[stage["$skip"]:]
            elif "$group" in stage:
                grp = stage["$group"]
                key_expr = grp.get("_id", "")
                key_field = key_expr.lstrip("$") if isinstance(key_expr, str) else None
                buckets = {}
                for d in docs:
                    k = d.get(key_field) if key_field else None
                    b = buckets.setdefault(k, {"_id": k})
                    for out_field, expr in grp.items():
                        if out_field == "_id":
                            continue
                        if isinstance(expr, dict) and "$sum" in expr:
                            b[out_field] = b.get(out_field, 0) + expr["$sum"]
                        elif isinstance(expr, dict) and "$first" in expr:
                            b.setdefault(out_field, d.get(expr["$first"].lstrip("$")))
                        elif isinstance(expr, dict) and "$last" in expr:
                            b[out_field] = d.get(expr["$last"].lstrip("$"))
                docs = list(buckets.values())
            elif "$project" in stage:
                docs = [_project(d, stage["$project"]) for d in docs]
        return _FakeCursorResult(_hydrate_datetimes(d) for d in docs)


_collection_cache = {}


def get_collection(name: str):
    if name not in _collection_cache:
        _collection_cache[name] = _SQLiteCollectionShim(name)
    return _collection_cache[name]


class _FakeMongoClient:
    def __init__(self, *a, **kw): pass
    def __getitem__(self, name):  return _get_conn()
    def __getattr__(self, name):  return _get_conn()


MongoClient = _FakeMongoClient


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# FAKE psycopg2 shims
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

try:
    import psycopg2  # noqa
except ImportError:
    import sys, types as _types
    _fake_pg = _types.ModuleType("psycopg2")
    _fake_extras = _types.ModuleType("psycopg2.extras")
    class _RealDictCursor: pass
    _fake_extras.RealDictCursor = _RealDictCursor
    _fake_pg.extras = _fake_extras
    _fake_pg.connect = lambda *a, **kw: _get_conn()
    sys.modules.setdefault("psycopg2", _fake_pg)
    sys.modules.setdefault("psycopg2.extras", _fake_extras)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# INIT
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

_init_schema()
try:
    migrate_mshh_to_atlas()
except Exception as _mig_err:
    logging.error(f"startup migration failed: {_mig_err}")


if __name__ == "__main__":
    print(f"SQLite database: {DB_PATH}")
    for row in _get_conn().execute(
        "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
    ):
        print(f"  - {row['name']}")