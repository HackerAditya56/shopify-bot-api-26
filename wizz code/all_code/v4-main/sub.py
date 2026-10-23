import asyncio
import re
import html
import psycopg2
from psycopg2.extras import RealDictCursor
from datetime import datetime, timedelta
import random
import string
import logging
import io
import time as _time

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# AIogram Imports
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
from aiogram import types, F, Router
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, BufferedInputFile

router = Router()

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# CONFIGURATION & IMPORTS
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
from database import PooledConn, _premium_cache, _premium_cache_ttl, get_user_lifetime_stats, get_all_lifetime_stats_totals, is_owner_user

ADMIN_ID       = 8462705169
LOG_CHANNEL_ID = -1003822850440
BOT_LINK       = "https://t.me/ladkichut03_bot"

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# DATABASE INIT
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def init_db():
    with PooledConn() as conn:
        cur = conn.cursor()

        # Ensure user_id is BIGINT
        try:
            cur.execute("ALTER TABLE users ALTER COLUMN user_id TYPE BIGINT")
            conn.commit()
        except Exception:
            conn.rollback()

        # Add any missing columns to users
        columns = [
            ("first_name",     "TEXT"),
            ("username",       "TEXT"),
            ("credits",        "INTEGER DEFAULT 0"),
            ("is_premium",     "INTEGER DEFAULT 0"),
            ("premium_expiry", "TIMESTAMP"),
            ("joined_at",      "TIMESTAMP DEFAULT NOW()"),
        ]
        for col_name, col_type in columns:
            try:
                cur.execute(
                    f"ALTER TABLE users ADD COLUMN IF NOT EXISTS {col_name} {col_type}"
                )
                conn.commit()
            except Exception as e:
                conn.rollback()
                logging.warning(f"Column check {col_name}: {e}")

        # receipts table
        try:
            cur.execute("""
                CREATE TABLE IF NOT EXISTS receipts (
                    id           SERIAL PRIMARY KEY,
                    receipt_id   TEXT UNIQUE,
                    user_id      BIGINT,
                    plan         TEXT,
                    amount_paid  REAL,
                    purchased_on TIMESTAMP,
                    expires_on   TIMESTAMP
                )
            """)
            conn.commit()
        except Exception:
            conn.rollback()

        for extra_col in [
            "ALTER TABLE receipts ADD COLUMN IF NOT EXISTS expires_on   TIMESTAMP",
            "ALTER TABLE receipts ADD COLUMN IF NOT EXISTS amount_paid  REAL",
        ]:
            try:
                cur.execute(extra_col)
                conn.commit()
            except Exception:
                conn.rollback()

        # Migrate old `amount` column → amount_paid if needed
        try:
            cur.execute("""
                UPDATE receipts
                   SET amount_paid = amount
                 WHERE amount_paid IS NULL
                   AND amount IS NOT NULL
            """)
            conn.commit()
        except Exception:
            conn.rollback()

        # codes table
        try:
            cur.execute("""
                CREATE TABLE IF NOT EXISTS codes (
                    code       TEXT PRIMARY KEY,
                    credits    INTEGER,
                    claimed_by BIGINT,
                    claimed_at TIMESTAMP
                )
            """)
            conn.commit()
        except Exception:
            conn.rollback()

        # ── Extend codes table for premium keys ──────────────────────────
        for col_def in [
            "ALTER TABLE codes ADD COLUMN IF NOT EXISTS plan_name        TEXT",
            "ALTER TABLE codes ADD COLUMN IF NOT EXISTS duration_seconds BIGINT",
            "ALTER TABLE codes ADD COLUMN IF NOT EXISTS created_by       BIGINT",
            "ALTER TABLE codes ADD COLUMN IF NOT EXISTS expires_at       TIMESTAMP",
        ]:
            try:
                cur.execute(col_def)
                conn.commit()
            except Exception:
                conn.rollback()

try:
    init_db()
except Exception as e:
    logging.error(f"DB Init Error: {e}")

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# HELPERS
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def generate_receipt_id():
    random_str = ''.join(random.choices(string.digits, k=6))
    return f"CHK-{random_str}-XWIZ"


def mask_receipt_id(receipt_id):
    parts = receipt_id.split('-')
    if len(parts) == 3:
        middle = parts[1]
        if len(middle) >= 2:
            masked_middle = middle[:2] + "XX" + middle[4:]
            return f"{parts[0]}-{masked_middle}-{parts[2]}"
    return receipt_id


def _esc(value) -> str:
    """
    HTML-escape any user-controlled text (first_name, username, etc.)
    before it is interpolated into an HTML parse_mode message.
    """
    return html.escape(str(value), quote=False)


def _lnk(symbol: str) -> str:
    """Wrap a decorative symbol so it opens the dev channel when tapped."""
    return f'<a href="https://t.me/broken_wiz">{symbol}</a>'


def _b(text: str) -> str:
    """Bold a whole caption line."""
    return f"<b>{text}</b>"


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# DURATION PARSER
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def _parse_duration(s: str):
    """Parse a duration string into total seconds. Returns None on failure."""
    s = s.strip().lower()
    match = re.fullmatch(r'(\d+)(m|h|d)', s)
    if not match:
        return None
    value, unit = int(match.group(1)), match.group(2)
    if value <= 0:
        return None
    if unit == 'm':
        return value * 60
    if unit == 'h':
        return value * 3600
    if unit == 'd':
        return value * 86400
    return None


def _seconds_to_display(seconds: int) -> str:
    """Convert seconds to a compact label such as ``29d 23h``."""
    seconds = max(0, int(seconds))
    days, remainder = divmod(seconds, 86400)
    hours, remainder = divmod(remainder, 3600)
    minutes = remainder // 60

    parts = []
    if days:
        parts.append(f"{days}d")
    if hours:
        parts.append(f"{hours}h")
    if minutes and not days:
        parts.append(f"{minutes}m")
    return " ".join(parts) or "0m"


_PLAN_DISPLAY_NAMES = {
    "swift": "ꕶᴡ𝖎ғ†",
    "turbo": "Ƭᴜʀʙᴏ",
    "nitro": "ɴɪⲧʀᴏ",
    "apex": "ꫝᴘᴇ✗",
    "owner": "ᴏꪝɴᴇʀ",
}


def _canonical_plan_name(plan_name: str) -> str:
    """Return the exact branded value used for known plans everywhere."""
    value = str(plan_name).strip()
    aliases = {
        "swift": _PLAN_DISPLAY_NAMES["swift"],
        "turbo": _PLAN_DISPLAY_NAMES["turbo"],
        "nitro": _PLAN_DISPLAY_NAMES["nitro"],
        "apex": _PLAN_DISPLAY_NAMES["apex"],
        "owner": _PLAN_DISPLAY_NAMES["owner"],
    }
    aliases.update({
        branded.casefold(): branded
        for branded in _PLAN_DISPLAY_NAMES.values()
    })
    return aliases.get(value.casefold(), value)


def _display_plan_name(plan_name: str) -> str:
    """Return the branded name used in every user-facing message."""
    return _canonical_plan_name(plan_name)


def _already_premium_notice(expires_on: str) -> str:
    """Shared 'you already have an active plan' caption used by /plan and /claim."""
    gem = '<tg-emoji emoji-id="5427168083074628963">💎</tg-emoji>'
    return (
        f'{_b(f"{_lnk("[⌭]")} Aʟʀᴇᴀᴅʏ Pʀᴇᴍɪᴜᴍ {gem}")}\n'
        f'────────────\n'
        f'{_b(f"{_lnk("⬢")} Yᴏᴜ ᴀʟʀᴇᴀᴅʏ ʜᴀᴠᴇ ᴀɴ ᴀᴄᴛɪᴠᴇ ᴘʀᴇᴍɪᴜᴍ ᴘʟᴀɴ.")}\n'
        f'{_b(f"{_lnk("⬡")} Exᴘɪʀᴇs Oɴ ➺ {_esc(expires_on)}")}\n'
        f'────────────\n'
        f'{_b(f"{_lnk("⎔")} Usᴇ /info ᴛᴏ sᴇᴇ ғᴜʟʟ ᴀᴄᴄᴏᴜɴᴛ ᴅᴇᴛᴀɪʟs.")}'
    )


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# NOTIFICATION HELPER (Only for Log Group)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

async def _send_log_notification(bot, chat_id, text: str) -> bool:
    """
    Send a notification to the log group with HTML attempt and plain-text fallback.
    Returns True if sent successfully, False otherwise.
    """
    if not chat_id:
        logging.error("[Claim] Log notification failed: chat_id is None or invalid")
        return False

    try:
        logging.info("[Claim] Attempting to send log notification to chat_id: %s", chat_id)

        kb = InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(
                text="🛒 Tᴀᴘ ᴛᴏ Bᴜʏ",
                url=f"{BOT_LINK}?start=plan",
                style="primary",
            )
        ]])

        # Try to send with HTML parsing first
        sent = await bot.send_message(
            chat_id=chat_id,
            text=text,
            parse_mode="HTML",
            disable_web_page_preview=True,
            reply_markup=kb,
        )
        try:
            await bot.pin_chat_message(chat_id, sent.message_id)
        except Exception as pin_err:
            logging.warning(f"[Claim] Could not pin log: {pin_err}")
        logging.info("[Claim] Log notification sent successfully to %s", chat_id)
        return True
        
    except Exception as html_error:
        logging.error(
            "[Claim] Log HTML notification failed for %s: %s",
            chat_id,
            html_error,
        )

    # Try plain-text fallback
    plain_text = html.unescape(re.sub(r"<[^>]*>", "", text))
    try:
        await bot.send_message(
            chat_id=chat_id,
            text=plain_text,
            disable_web_page_preview=True,
        )
        logging.info("[Claim] Log plain-text fallback sent to %s", chat_id)
        return True
    except Exception as fallback_error:
        logging.error(
            "[Claim] Log notification failed for %s after fallback: %s",
            chat_id,
            fallback_error,
        )
        return False


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# SYNC DB LOGIC
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def get_premium_status(user_id):
    """
    Returns (is_premium: bool, expiry: datetime | None).
    Results are cached for _premium_cache_ttl seconds.
    """
    # owners always carry premium — no plan, no expiry, nothing to buy
    if is_owner_user(user_id):
        return (True, None)

    now = _time.monotonic()
    cached = _premium_cache.get(user_id)
    if cached is not None and now < cached[1]:
        return cached[0]

    result = (False, None)
    with PooledConn() as conn:
        cur = conn.cursor(cursor_factory=RealDictCursor)
        cur.execute(
            "SELECT is_premium, premium_expiry FROM users WHERE user_id = %s",
            (user_id,)
        )
        row = cur.fetchone()
        if row:
            is_premium_flag = row['is_premium']
            expiry          = row['premium_expiry']

            if is_premium_flag == 1:
                if expiry:
                    if datetime.now() < expiry:
                        result = (True, expiry)
                    else:
                        cur.execute(
                            "UPDATE users SET is_premium = 0, premium_expiry = NULL, credits = 150 "
                            "WHERE user_id = %s",
                            (user_id,)
                        )
                        conn.commit()
                else:
                    cur.execute(
                        "UPDATE users SET is_premium = 0 WHERE user_id = %s",
                        (user_id,)
                    )
                    conn.commit()
            elif expiry and datetime.now() > expiry:
                cur.execute(
                    "UPDATE users SET premium_expiry = NULL, credits = 150 WHERE user_id = %s",
                    (user_id,)
                )
                conn.commit()

    _premium_cache[user_id] = (result, _time.monotonic() + _premium_cache_ttl)
    return result


def _resolve_user_id_sync(target_input):
    """Resolve a user_id from numeric ID, @username, or first_name."""
    with PooledConn() as conn:
        cur = conn.cursor(cursor_factory=RealDictCursor)

        if target_input.isdigit():
            cur.execute(
                "SELECT user_id FROM users WHERE user_id = %s",
                (int(target_input),)
            )
            row = cur.fetchone()
            if row:
                return row['user_id']

        username = target_input.lstrip('@').lower()
        cur.execute(
            "SELECT user_id FROM users WHERE LOWER(username) = %s",
            (username,)
        )
        row = cur.fetchone()
        if row:
            return row['user_id']

        cur.execute(
            "SELECT user_id FROM users WHERE LOWER(first_name) = %s",
            (username,)
        )
        row = cur.fetchone()
        if row:
            return row['user_id']

        return None


def _auth_db_sync(target_id, display_name, plan_name, days, credits, amount):
    """Grant a subscription plan. Returns receipt_id or raises on error."""
    expiry_date  = datetime.now() + timedelta(days=days)
    receipt_id   = generate_receipt_id()
    purchased_on = datetime.now()

    with PooledConn() as conn:
        cur = conn.cursor()
        cur.execute("""
            INSERT INTO users (user_id, username, first_name, credits, joined_at)
            VALUES (%s, %s, %s, %s, %s)
            ON CONFLICT (user_id) DO NOTHING
        """, (target_id, "Unknown", "User", 0, datetime.now()))
        cur.execute(
            "UPDATE users SET first_name = %s WHERE user_id = %s",
            (display_name, target_id)
        )
        cur.execute(
            "UPDATE users SET is_premium = 1, premium_expiry = %s WHERE user_id = %s",
            (expiry_date, target_id)
        )
        # Premium users always get 999999999 credits (displayed as ∞)
        cur.execute(
            "UPDATE users SET credits = 999999999 WHERE user_id = %s",
            (target_id,)
        )
        cur.execute(
            "INSERT INTO receipts (receipt_id, user_id, plan, amount_paid, purchased_on, expires_on) "
            "VALUES (%s, %s, %s, %s, %s, %s)",
            (receipt_id, target_id, plan_name, amount, purchased_on, expiry_date)
        )
        conn.commit()

    _premium_cache.pop(target_id, None)
    return receipt_id


def _adcr_db_sync(target_id, display_name, add_credits):
    """Add credits to a user. Returns new total."""
    with PooledConn() as conn:
        cur = conn.cursor(cursor_factory=RealDictCursor)
        cur.execute("""
            INSERT INTO users (user_id, username, first_name, credits, joined_at)
            VALUES (%s, %s, %s, %s, %s)
            ON CONFLICT (user_id) DO NOTHING
        """, (target_id, "Unknown", "User", 0, datetime.now()))
        cur.execute(
            "UPDATE users SET credits = credits + %s WHERE user_id = %s",
            (add_credits, target_id)
        )
        cur.execute(
            "SELECT credits FROM users WHERE user_id = %s",
            (target_id,)
        )
        updated   = cur.fetchone()
        new_total = updated['credits'] if updated else 0
        conn.commit()

    return new_total


def _rauth_db_sync(target_id):
    """Remove premium, reset credits to 150. Returns user row dict or None."""
    with PooledConn() as conn:
        cur = conn.cursor(cursor_factory=RealDictCursor)
        cur.execute(
            "UPDATE users SET is_premium = 0, premium_expiry = NULL, credits = 150 "
            "WHERE user_id = %s",
            (target_id,)
        )
        conn.commit()
        cur.execute(
            "SELECT first_name, username FROM users WHERE user_id = %s",
            (target_id,)
        )
        row = cur.fetchone()

    _premium_cache.pop(target_id, None)
    return row


def _rc_db_sync(receipt_id):
    """Fetch receipt + user details. Returns row dict or None."""
    with PooledConn() as conn:
        cur = conn.cursor(cursor_factory=RealDictCursor)
        cur.execute("""
            SELECT r.*, u.first_name, u.is_premium, u.credits
              FROM receipts r
              JOIN users u ON r.user_id = u.user_id
             WHERE r.receipt_id = %s
        """, (receipt_id,))
        return cur.fetchone()


def _info_db_sync(user_id, username, first_name):
    """Fetch full user info row, creating the user if missing."""
    get_premium_status(user_id)

    with PooledConn() as conn:
        cur = conn.cursor(cursor_factory=RealDictCursor)
        cur.execute("SELECT * FROM users WHERE user_id = %s", (user_id,))
        u_row = cur.fetchone()

        if not u_row:
            cur.execute(
                "INSERT INTO users (user_id, username, first_name, credits, joined_at) "
                "VALUES (%s, %s, %s, %s, %s)",
                (user_id, username, first_name, 0, datetime.now())
            )
            conn.commit()
            cur.execute("SELECT * FROM users WHERE user_id = %s", (user_id,))
            u_row = cur.fetchone()

        receipt_row = None
        if u_row['is_premium'] == 1:
            cur.execute(
                "SELECT plan, purchased_on FROM receipts "
                "WHERE user_id = %s ORDER BY purchased_on DESC LIMIT 1",
                (user_id,)
            )
            receipt_row = cur.fetchone()

    return dict(u_row), dict(receipt_row) if receipt_row else None


def _authall_db_sync():
    """Return all currently active premium users."""
    with PooledConn() as conn:
        cur = conn.cursor(cursor_factory=RealDictCursor)
        cur.execute("""
            SELECT DISTINCT ON (u.user_id)
                u.user_id, u.username, r.receipt_id, r.purchased_on,
                r.plan, u.premium_expiry, u.credits
              FROM users u
              LEFT JOIN receipts r ON u.user_id = r.user_id
             WHERE u.is_premium = 1 AND u.premium_expiry > NOW()
             ORDER BY u.user_id, r.purchased_on DESC
        """)
        return cur.fetchall()


def _gen_code_db_sync(amount):
    """Generate `amount` claim codes worth 200 credits each."""
    generated = []
    with PooledConn() as conn:
        cur = conn.cursor()
        for _ in range(amount):
            code = "WIZX-" + ''.join(
                random.choices(string.ascii_uppercase + string.digits, k=10)
            ) + "-CHK"
            cur.execute(
                "INSERT INTO codes (code, credits) VALUES (%s, %s)",
                (code, 200)
            )
            generated.append(code)
        conn.commit()
    return generated


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# PREMIUM KEY GENERATION
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def _key_db_sync(
    credits: int,
    plan_name: str,
    duration_seconds: int,
    created_by: int,
    count: int,
):
    """Generate and persist ``count`` premium keys in one transaction."""
    generated = []
    with PooledConn() as conn:
        cur = conn.cursor()
        while len(generated) < count:
            key = "WIZX-" + ''.join(
                random.choices(string.ascii_uppercase + string.digits, k=10)
            ) + "-CHK"
            cur.execute(
                "INSERT INTO codes "
                "(code, credits, plan_name, duration_seconds, created_by) "
                "VALUES (%s, %s, %s, %s, %s) "
                "ON CONFLICT (code) DO NOTHING",
                (key, credits, plan_name, duration_seconds, created_by)
            )
            if cur.rowcount == 1:
                generated.append(key)
        conn.commit()
    return generated


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# CLAIM LOGIC
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def _claim_db_sync(user_id, code):
    with PooledConn() as conn:
        cur = conn.cursor(cursor_factory=RealDictCursor)
        try:
            cur.execute("SELECT * FROM codes WHERE code = %s", (code,))
            row = cur.fetchone()
            if not row:
                return "invalid", None
            if row['claimed_by'] is not None:
                return "claimed", None

            is_prem, _ = get_premium_status(user_id)

            # ── Premium key path ──────────────────────────────────────────
            if row.get('plan_name') is not None:
                if is_prem:
                    return "premium", None

                duration_seconds = row['duration_seconds']
                expiry_date      = datetime.now() + timedelta(seconds=duration_seconds)
                receipt_id       = generate_receipt_id()
                purchased_on     = datetime.now()
                credits          = row['credits']
                plan_name        = row['plan_name']

                cur.execute("""
                    INSERT INTO users (user_id, username, first_name, credits, joined_at)
                    VALUES (%s, %s, %s, %s, %s)
                    ON CONFLICT (user_id) DO NOTHING
                """, (user_id, "Unknown", "User", 0, datetime.now()))

                cur.execute(
                    "UPDATE users SET is_premium = 1, premium_expiry = %s WHERE user_id = %s",
                    (expiry_date, user_id)
                )
                # Premium users always get 999999999 credits (displayed as ∞)
                cur.execute(
                    "UPDATE users SET credits = 999999999 WHERE user_id = %s",
                    (user_id,)
                )

                cur.execute(
                    "INSERT INTO receipts "
                    "(receipt_id, user_id, plan, amount_paid, purchased_on, expires_on) "
                    "VALUES (%s, %s, %s, %s, %s, %s)",
                    (receipt_id, user_id, plan_name, 0, purchased_on, expiry_date)
                )

                cur.execute(
                    "UPDATE codes SET claimed_by = %s, claimed_at = %s, expires_at = %s "
                    "WHERE code = %s",
                    (user_id, purchased_on, expiry_date, code)
                )
                conn.commit()

                _premium_cache.pop(user_id, None)

                return "premium_ok", {
                    "credits":          credits,
                    "plan_name":        plan_name,
                    "duration_seconds": duration_seconds,
                    "expiry_date":      expiry_date,
                    "receipt_id":       receipt_id,
                    "created_by":       row.get('created_by'),
                }

            # ── Regular code path ──────────────────────────────────────────
            if is_prem:
                return "premium", None

            cur.execute(
                "UPDATE codes SET claimed_by = %s, claimed_at = %s WHERE code = %s",
                (user_id, datetime.now(), code)
            )
            cur.execute(
                "UPDATE users SET credits = credits + %s WHERE user_id = %s",
                (row['credits'], user_id)
            )
            conn.commit()
            return "ok", row['credits']

        except Exception as e:
            conn.rollback()
            logging.error(f"Error claiming code: {e}")
            return "error", None


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# BACKGROUND EXPIRY WORKER
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def _expire_premiums_sync():
    """Find expired premium users, reset them, and return list for DM notifications."""
    expired = []
    with PooledConn() as conn:
        cur = conn.cursor(cursor_factory=RealDictCursor)
        cur.execute("""
            SELECT u.user_id,
                   COALESCE(r.plan, 'Premium') AS plan_name
              FROM users u
              LEFT JOIN LATERAL (
                  SELECT plan
                    FROM receipts
                   WHERE user_id = u.user_id
                   ORDER BY purchased_on DESC
                   LIMIT 1
              ) r ON TRUE
             WHERE u.is_premium = 1
               AND u.premium_expiry IS NOT NULL
               AND u.premium_expiry <= NOW()
        """)
        rows = cur.fetchall()

        if rows:
            user_ids = [r['user_id'] for r in rows]
            cur.execute("""
                UPDATE users
                   SET is_premium     = 0,
                       premium_expiry = NULL,
                       credits        = 150
                 WHERE user_id = ANY(%s)
            """, (user_ids,))
            conn.commit()
            for r in rows:
                _premium_cache.pop(r['user_id'], None)
                expired.append((r['user_id'], r['plan_name']))

    return expired


async def premium_expiry_worker(bot):
    """Long-running background task to handle expired subscriptions."""
    logging.info("[ExpiryWorker] Started.")
    while True:
        try:
            expired = await asyncio.to_thread(_expire_premiums_sync)
            for user_id, plan_name in expired:
                try:
                    await bot.send_message(
                        chat_id=user_id,
                        text=(
                            f'<tg-emoji emoji-id="5447381715293074599">⚠️</tg-emoji> <b>Yᴏᴜʀ <b>{_esc(_display_plan_name(plan_name))}</b> Sᴜʙsᴄʀɪᴘᴛɪᴏɴ Hᴀs Exᴘɪʀᴇᴅ.</b>\n\n'
                            f'<tg-emoji emoji-id="5445350109862720603">✅</tg-emoji> <b>Yᴏᴜʀ Aᴄᴄᴏᴜɴᴛ Hᴀs Aᴜᴛᴏᴍᴀᴛɪᴄᴀʟʟʏ Bᴇᴇɴ Rᴇᴠᴇʀᴛᴇᴅ Tᴏ Tʜᴇ Fʀᴇᴇ Pʟᴀɴ.</b>\n'
                            f'<tg-emoji emoji-id="5445350109862720603">✅</tg-emoji> <b>Yᴏᴜʀ Cʀᴇᴅɪᴛ Hᴀs Bᴇᴇɴ Rᴇsᴇᴛ Tᴏ 150.</b>'

                        ),
                        parse_mode="HTML"
                    )
                    logging.info(f"[ExpiryWorker] DM sent to {user_id}")
                except Exception as dm_err:
                    logging.warning(f"[ExpiryWorker] Could not DM {user_id}: {dm_err}")
        except Exception as e:
            logging.error(f"[ExpiryWorker] Cycle error: {e}")

        await asyncio.sleep(60)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# COMMAND: /plan
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

_PLAN_TEXT = (
    '<tg-emoji emoji-id="5424976816530014958">👛</tg-emoji> <b>ᴀᴄᴄᴇꜱꜱ ➺ ꕶω𝖎f†</b> <tg-emoji emoji-id="6253702009107516178">💎</tg-emoji>\n'
    '<tg-emoji emoji-id="6136246765369694911">🦇</tg-emoji> <b>ᴘƦɪᴄᴇ ➺</b> 𝟯$\n'
    '<tg-emoji emoji-id="6136246765369694911">🦇</tg-emoji> <b>ᴅᴜƦᴀᴛɪᴏɴ ➺</b> [𝟮 ᴅᴀʏꜱ]\n'
    '<tg-emoji emoji-id="6136246765369694911">🦇</tg-emoji> <b>ᴄƦᴇᴅɪᴛꜱ ➺</b> ∞\n'
    '━━━━━━━━━━━━━━━━\n'
    '<tg-emoji emoji-id="5424976816530014958">👛</tg-emoji> <b>ᴀᴄᴄᴇꜱꜱ ➺ Ƭυяʙσ</b> <tg-emoji emoji-id="6255712466118905093">⭐</tg-emoji>\n'
    '<tg-emoji emoji-id="6136246765369694911">🦇</tg-emoji> <b>ᴘƦɪᴄᴇ ➺</b> 𝟳$\n'
    '<tg-emoji emoji-id="6136246765369694911">🦇</tg-emoji> <b>ᴅᴜƦᴀᴛɪᴏɴ ➺</b> [𝟳 ᴅᴀʏꜱ]\n'
    '<tg-emoji emoji-id="6136246765369694911">🦇</tg-emoji> <b>ᴄƦᴇᴅɪᴛꜱ ➺</b> ∞\n'
    '━━━━━━━━━━━━━━━━\n'
    '<tg-emoji emoji-id="5424976816530014958">👛</tg-emoji> <b>ᴀᴄᴄᴇꜱꜱ ➺ Ⲛⲓⲧⲅⲟ</b> <tg-emoji emoji-id="6253702009107516178">⭐</tg-emoji>\n'
    '<tg-emoji emoji-id="6136246765369694911">🦇</tg-emoji> <b>ᴘƦɪᴄᴇ ➺</b> 𝟭𝟰$\n'
    '<tg-emoji emoji-id="6136246765369694911">🦇</tg-emoji> <b>ᴅᴜƦᴀᴛɪᴏɴ ➺</b> [𝟭𝟱 ᴅᴀʏꜱ]\n'
    '<tg-emoji emoji-id="6136246765369694911">🦇</tg-emoji> <b>ᴄƦᴇᴅɪᴛꜱ ➺</b> ∞\n'
    '━━━━━━━━━━━━━━━━\n'
    '<tg-emoji emoji-id="5424976816530014958">👛</tg-emoji> <b>ᴀᴄᴄᴇꜱꜱ ➺ ꫝᴘᴇ✗</b> <tg-emoji emoji-id="6255712466118905093">⚡</tg-emoji>\n'
    '<tg-emoji emoji-id="6136246765369694911">🦇</tg-emoji> <b>ᴘƦɪᴄᴇ ➺</b> 𝟮𝟱$\n'
    '<tg-emoji emoji-id="6136246765369694911">🦇</tg-emoji> <b>ᴅᴜƦᴀᴛɪᴏɴ ➺</b> [𝟯𝟬 ᴅᴀʏꜱ]\n'
    '<tg-emoji emoji-id="6136246765369694911">🦇</tg-emoji> <b>ᴄƦᴇᴅɪᴛꜱ ➺</b> ∞'
)

@router.message(F.text.startswith("/plan"))
async def plan_command(message: types.Message):
    is_prem, expiry = get_premium_status(message.from_user.id)

    if is_prem:
        if expiry:
            exp_str = expiry.strftime("%Y-%m-%d")
        else:
            exp_str = "N/A"
        await message.reply(_already_premium_notice(exp_str), parse_mode="HTML")
        return

    kb = InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="💎 Bᴜʏ Pʟᴀɴ", callback_data="menu_buy", style="primary"),
    ]])
    await message.reply(text=_PLAN_TEXT, parse_mode="HTML", reply_markup=kb)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# COMMAND: /auth
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

@router.message(F.text.startswith("/auth"))
async def auth_command(message: types.Message):
    if message.from_user.id != ADMIN_ID:
        await message.reply("❌ 𝗬𝗼𝘂 𝗮𝗿𝗲 𝗻𝗼𝘁 𝗮𝘂𝘁𝗵𝗼𝗿𝗶𝘇𝗲𝗱 𝘁𝗼 𝘂𝘀𝗲 𝘁𝗵𝗶𝘀.")
        return

    args = message.text.split()[1:]
    if len(args) < 2:
        await message.reply(
            "❌ 𝗨𝘀𝗮𝗴𝗲: /auth {user_id/username} {plan}\n"
            "Plans: ꕶω𝖎f†, Ƭυяʙσ, Ⲛⲓⲧⲅⲟ, ꫝᴘᴇ✗, ᴏꪝɴᴇʀ\n"
            "Example: /auth 123456 apex"
        )
        return

    target_input, plan = args[0], args[1].lower()

    plan_map = {
        "swift": (_PLAN_DISPLAY_NAMES["swift"],  2,  999999999,  3),
        "turbo": (_PLAN_DISPLAY_NAMES["turbo"],  7,  999999999,  7),
        "nitro": (_PLAN_DISPLAY_NAMES["nitro"],  15, 999999999, 14),
        "apex":  (_PLAN_DISPLAY_NAMES["apex"],   30, 999999999, 25),
        "owner": (_PLAN_DISPLAY_NAMES["owner"],  365, 999999, 0),
    }
    if plan not in plan_map:
        await message.reply(
            "❌ 𝗜𝗻𝘃𝗮𝗹𝗶𝗱 𝗽𝗹𝗮𝗻. 𝗣𝗹𝗮𝗻𝘀: "
            "<b>ꕶω𝖎f†</b>, <b>Ƭυяʙσ</b>, <b>Ⲛⲓⲧⲅⲟ</b>, "
            "<b>ꫝᴘᴇ✗</b>, <b>ᴏꪝɴᴇʀ</b>",
            parse_mode="HTML"
        )
        return

    target_id = await asyncio.to_thread(_resolve_user_id_sync, target_input)
    if not target_id:
        await message.reply("❌ 𝗖𝗼𝘂𝗹𝗱 𝗻𝗼𝘁 𝗳𝗶𝗻𝗱 𝘂𝘀𝗲𝗿 𝗶𝗻 𝗗𝗮𝘁𝗮𝗯𝗮𝘀𝗲.")
        return

    plan_name, days, credits, amount = plan_map[plan]
    display_plan_name = _display_plan_name(plan_name)

    display_name = "User"
    try:
        chat = await message.bot.get_chat(target_id)
        display_name = chat.first_name or chat.username or "User"
    except Exception:
        pass

    try:
        receipt_id = await asyncio.to_thread(
            _auth_db_sync, target_id, display_name, plan_name, days, credits, amount
        )
    except Exception as e:
        logging.error(f"Error updating subscription: {e}")
        await message.reply("❌ 𝗗𝗮𝘁𝗮𝗯𝗮𝘀𝗲 𝗘𝗿𝗿𝗼𝗿.")
        return

    safe_name  = _esc(display_name)
    user_link  = f'<a href="tg://user?id={target_id}">{safe_name}</a>'

    caption = (
        f"<b>Cᴏɴɢʀᴀᴛᴜʟᴀᴛɪᴏɴs! 🎉 Yᴏᴜʀ Aᴄᴄᴇss Hᴀs Bᴇᴇɴ Aᴄᴛɪᴠᴀᴛᴇᴅ</b>\n"
        f"<b>Usᴇʀ ➺ {user_link}</b>\n"
        f"<b>Aᴄᴄᴇss ➺ {display_plan_name}</b>\n"
        f"<b>Dᴜʀᴀᴛɪᴏɴ ➺ {days} Dᴀʏs</b>\n"
        f"<b>Cʀᴇᴅɪᴛs Aᴅᴅᴇᴅ ➺ +{credits:,}</b>\n"
        f"<b>Rᴇᴄɪᴇᴘᴛ ID ➺ <code>{receipt_id}</code></b>\n"
        f"<b>Pʟᴇᴀsᴇ Sᴀᴠᴇ Tʜɪs Rᴇᴄᴇɪᴘᴛ ID.</b>"
    )

    if plan == "owner":
        log_text = (
            f"<b>𝐎𝐖𝐍𝐄𝐑 𝐏𝐋𝐀𝐍 𝐀𝐂𝐓𝐈𝐕𝐀𝐓𝐄𝐃 👑</b>\n"
            f"<b>𝐔𝐬𝐞𝐫 ➺</b> {user_link}\n"
            f"<b>𝐏𝐥𝐚𝐧 ➺</b> <b>{display_plan_name}</b>\n"
            f"<b>𝐏𝐫𝐢𝐜𝐞 ➺</b> <b>{amount} USD</b>"
        )
    else:
        log_text = (
            f'<b>Nᴇᴡ Pʟᴀɴ Pᴜʀᴄʜᴀsᴇᴅ <tg-emoji emoji-id="5226656353744862682">🛒</tg-emoji></b>\n'
            f"<b>Usᴇʀ ➺</b> {user_link}\n"
            f"<b>Pʟᴀɴ ➺</b> <b>{display_plan_name}</b>\n"
            f"<b>Pʀɪᴄᴇ ➺</b> <b>{amount} USD</b>"
        )

    async def _dm_user():
        try:
            await message.bot.send_message(chat_id=target_id, text=caption, parse_mode="HTML")
            return True
        except Exception as e:
            logging.error(f"[Auth] Could not DM user {target_id}: {e}")
            return False

    async def _log_group():
        try:
            kb = InlineKeyboardMarkup(inline_keyboard=[[
                InlineKeyboardButton(
                    text="🛒 Tᴀᴘ ᴛᴏ Bᴜʏ",
                    url=f"{BOT_LINK}?start=plan",
                    style="primary",
                )
            ]])
            sent = await message.bot.send_message(
                chat_id=LOG_CHANNEL_ID, text=log_text,
                parse_mode="HTML", reply_markup=kb,
            )
            try:
                await message.bot.pin_chat_message(LOG_CHANNEL_ID, sent.message_id)
            except Exception as pin_err:
                logging.warning(f"[Auth] Could not pin log: {pin_err}")
            return True
        except Exception as e:
            logging.error(f"[Auth] Could not post to log channel {LOG_CHANNEL_ID}: {e}")
            return False

    dm_ok, log_ok = await asyncio.gather(_dm_user(), _log_group())

    admin_notice = (
        f"✅ <b>Subscription Activated</b>\n\n"
        f"User ➺ {user_link}\n"
        f"User ID ➺ <code>{target_id}</code>\n"
        f"Plan ➺ <b>{display_plan_name}</b>\n"
        f"Duration ➺ {days} Days\n"
        f"Credits Added ➺ +{credits:,}\n\n"
        f"DM to user ➺ {'✅ Delivered' if dm_ok else '⚠️ Failed — user may have blocked the bot or never opened a DM with it'}\n"
        f"Log group post ➺ {'✅ Delivered' if log_ok else '⚠️ Failed to post — check the bot is still an admin in the log group'}"
    )
    await message.reply(admin_notice, parse_mode="HTML")


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# COMMAND: /adcr
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

@router.message(F.text.startswith("/adcr"))
async def adcr_command(message: types.Message):
    if message.from_user.id != ADMIN_ID:
        await message.reply("❌ 𝐘𝐨𝐮 𝐚𝐫𝐞 𝐧𝐨𝐭 𝐚𝐮𝐭𝐡𝐨𝐫𝐢𝐬𝐞𝐝.")
        return

    args = message.text.split()[1:]
    if len(args) < 2:
        await message.reply("❌ 𝗨𝘀𝗮𝗴𝗲: /adcr {user_id} {amount}\nExample: /adcr 123456789 5000")
        return

    target_input, amount_input = args[0], args[1]
    try:
        add_credits = int(amount_input)
        if add_credits <= 0:
            await message.reply("❌ 𝗔𝗺𝗼𝘂𝗻𝘁 𝗺𝘂𝘀𝘁 𝗯𝗲 𝗮 𝗽𝗼𝘀𝗶𝘁𝗶𝘃𝗲 𝗻𝘂𝗺𝗯𝗲𝗿.")
            return
    except ValueError:
        await message.reply("❌ 𝗜𝗻𝘃𝗮𝗹𝗶𝗱 𝗮𝗺𝗼𝘂𝗻𝘁. 𝗣𝗹𝗲𝗮𝘀𝗲 𝗲𝗻𝘁𝗲𝗿 𝗮 𝗻𝘂𝗺𝗯𝗲𝗿.")
        return

    target_id = await asyncio.to_thread(_resolve_user_id_sync, target_input)
    if not target_id:
        await message.reply("❌ 𝗖𝗼𝘂𝗹𝗱 𝗻𝗼𝘁 𝗳𝗶𝗻𝗱 𝘂𝘀𝗲𝗿 𝗶𝗻 𝗗𝗮𝘁𝗮𝗯𝗮𝘀𝗲.")
        return

    display_name = "User"
    try:
        chat = await message.bot.get_chat(target_id)
        display_name = chat.first_name or chat.username or "User"
    except Exception:
        pass

    try:
        new_total = await asyncio.to_thread(_adcr_db_sync, target_id, display_name, add_credits)
    except Exception as e:
        logging.error(f"Error adding credits: {e}")
        await message.reply("❌ 𝗗𝗮𝘁𝗮𝗯𝗮𝘀𝗲 𝗘𝗿𝗿𝗼𝗿.")
        return

    user_link = f'<a href="tg://user?id={target_id}">{_esc(display_name)}</a>'
    user_text = (
        f'<b>Cʀᴇᴅɪᴛs Aᴅᴅᴇᴅ</b> <tg-emoji emoji-id="6100515480735321747">✅</tg-emoji>\n'
        f"<b>Usᴇʀ</b> ➺ {user_link}\n"
        f"<b>Cʀᴇᴅɪᴛs Aᴅᴅᴇᴅ</b> ➺ <b>{add_credits:,}</b>\n"
        f"<b>Tᴏᴛᴀʟ Cʀᴇᴅɪᴛs</b> ➺ <b>{new_total:,}</b>"
    )

    async def _dm_user():
        try:
            await message.bot.send_message(chat_id=target_id, text=user_text, parse_mode="HTML")
        except Exception as e:
            logging.error(f"[Adcr] Could not DM user {target_id}: {e}")

    async def _reply():
        try:
            await message.reply(
                f"✅ Added <b>{add_credits:,}</b> credits to {user_link}.\n"
                f"Nᴇᴡ Tᴏᴛᴀʟ ➺ <b>{new_total:,}</b>",
                parse_mode="HTML"
            )
        except Exception as e:
            logging.error(f"[Adcr] Could not reply: {e}")

    await asyncio.gather(
        _dm_user(),
        _reply(),
        return_exceptions=True,
    )


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# COMMAND: /rauth
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

@router.message(F.text.startswith("/rauth"))
async def rauth_command(message: types.Message):
    if message.from_user.id != ADMIN_ID:
        await message.reply("❌ 𝗬𝗼𝘂 𝗮𝗿𝗲 𝗻𝗼𝘁 𝗮𝘂𝘁𝗵𝗼𝗿𝗶𝘇𝗲𝗱 𝘁𝗼 𝘂𝘀𝗲 𝘁𝗵𝗶𝘀.")
        return

    args = message.text.split()[1:]
    if not args:
        await message.reply("❌ 𝗨𝘀𝗮𝗴𝗲: /rauth {user_id/username}")
        return

    target_id = await asyncio.to_thread(_resolve_user_id_sync, args[0])
    if not target_id:
        await message.reply("❌ 𝗖𝗼𝘂𝗹𝗱 𝗻𝗼𝘁 𝗳𝗶𝗻𝗱 𝘂𝘀𝗲𝗿 𝗶𝗻 𝗗𝗮𝘁𝗮𝗯𝗮𝘀𝗲.")
        return

    try:
        user_details = await asyncio.to_thread(_rauth_db_sync, target_id)
    except Exception as e:
        logging.error(f"Error removing subscription: {e}")
        await message.reply("❌ 𝗗𝗮𝘁𝗮𝗯𝗮𝘀𝗲 𝗘𝗿𝗿𝗼𝗿.")
        return

    if not user_details:
        await message.reply(f"✅ Premium removed from {target_id} and credits reset to 150.")
        return

    display_name = "User"
    temp_name = user_details.get('first_name') or user_details.get('username')
    if temp_name and temp_name not in ["Unknown", "User"]:
        display_name = temp_name
    else:
        try:
            chat = await message.bot.get_chat(target_id)
            display_name = chat.first_name or "User"
        except Exception:
            pass

    dm_text = (
        f"<b>Yᴏᴜʀ Aᴄᴄᴇss Hᴀs Bᴇᴇɴ Eɴᴅᴇᴅ. Rᴇɴᴇᴡᴀʟ Nᴏᴡ.</b>\n\n"
        f"<b>Uꜱᴇʀ ➺ {_esc(display_name)}</b>\n"
        f"<b>Uꜱᴇʀ Iᴅ ➺ <code>{target_id}</code></b>\n"
        f"<b>Sᴛᴀᴛᴜꜱ ➺ Fʀᴇᴇ</b>\n"
        f"<b>Cʀᴇᴅɪᴛꜱ ➺ 150</b>"
    )

    async def _dm_user():
        try:
            await message.bot.send_message(chat_id=target_id, text=dm_text, parse_mode="HTML")
        except Exception as e:
            logging.error(f"[Rauth] Could not DM user {target_id}: {e}")

    async def _reply():
        try:
            await message.reply(f"✅ Premium removed from {target_id} and credits reset to 150.")
        except Exception as e:
            logging.error(f"[Rauth] Could not reply: {e}")

    await asyncio.gather(
        _dm_user(),
        _reply(),
        return_exceptions=True,
    )


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# COMMAND: /rc
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

@router.message(F.text.startswith("/rc"))
async def rc_command(message: types.Message):
    if message.from_user.id != ADMIN_ID:
        await message.reply("❌ 𝗬𝗼𝘂 𝗮𝗿𝗲 𝗻𝗼𝘁 𝗮𝘂𝘁𝗵𝗼𝗿𝗶𝘇𝗲𝗱.")
        return

    args = message.text.split()[1:]
    if not args:
        await message.reply("❌ 𝗨𝘀𝗮𝗴𝗲: /rc {receipt_id}")
        return

    row = await asyncio.to_thread(_rc_db_sync, args[0])
    if not row:
        await message.reply("❌ 𝗥𝗲𝗰𝗲𝗶𝗽𝘁 𝗜𝗗 𝗻𝗼𝘁 𝗳𝗼𝘂𝗻𝗱.")
        return

    uid   = row['user_id']
    fname = row['first_name']
    if not fname or fname in ["User", "Unknown"]:
        try:
            chat  = await message.bot.get_chat(uid)
            fname = chat.first_name or "Unknown"
        except Exception:
            fname = "Unknown"

    user_link   = f'<a href="tg://user?id={uid}">{_esc(fname)}</a>'
    amount_val  = row.get('amount_paid') if row.get('amount_paid') is not None else row.get('amount', 0)
    date_str    = row['purchased_on'].strftime('%Y-%m-%d') if row['purchased_on'] else "N/A"
    expires_str = row['expires_on'].strftime('%Y-%m-%d') if row.get('expires_on') else "N/A"
    credits_str = f"{row['credits']:,}"

    text = (
        f"𝗨𝘀𝗲𝗿 ➺ {user_link}\n"
        f"𝗨𝘀𝗲𝗿 𝗜𝗗 ➺ <code>{uid}</code>\n"
        f"𝗔𝗰𝗰𝗲𝘀𝘀 ➺ <b>{_esc(_display_plan_name(row['plan']))}</b>\n"
        f"𝗣𝘂𝗿𝗰𝗵𝗮𝘀𝗲𝗱 𝗢𝗻 ➺ {date_str}\n"
        f"𝗘𝘅𝗽𝗶𝗿𝗲𝘀 𝗢𝗻 ➺ <b>{expires_str}</b>\n"
        f"𝗥𝗲𝗰𝗲𝗶𝗽𝘁 𝗜𝗗 ➺ <code>{row['receipt_id']}</code>\n"
        f"𝗔𝗺𝗼𝘂𝗻𝘁 ➺ {amount_val} $\n"
        f"𝗖𝘂𝗿𝗿𝗲𝗻𝘁 𝗖𝗿𝗲𝗱𝗶𝘁𝘀 ➺ {credits_str}"
    )
    await message.reply(text, parse_mode="HTML")


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# COMMAND: /info
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

@router.message(F.text.startswith("/info"))
async def info_command(message: types.Message):
    user    = message.from_user
    user_id = user.id

    u_row, r_row = await asyncio.to_thread(
        _info_db_sync, user_id, user.username, user.first_name
    )

    raw_name = "N/A"
    if user.first_name:
        raw_name = user.first_name
    elif u_row.get('first_name') and u_row['first_name'].lower() not in ['unknown', 'user', 'none']:
        raw_name = u_row['first_name']
    elif user.username:
        raw_name = f"@{user.username}"
    elif u_row.get('username') and u_row['username'].lower() not in ['unknown', 'user', 'none']:
        raw_name = f"@{u_row['username']}"

    username_link = f'<a href="tg://user?id={user_id}">{_esc(raw_name)}</a>' if raw_name != "N/A" else raw_name

    access_str    = "Free"
    purchased_str = "N/A"
    ending_str    = "N/A"

    if u_row['is_premium'] == 1 and r_row:
        access_str    = _display_plan_name(r_row['plan'])
        purchased_str = r_row['purchased_on'].strftime('%Y-%m-%d') if r_row['purchased_on'] else "N/A"
        if u_row.get('premium_expiry'):
            ending_str = u_row['premium_expiry'].strftime('%Y-%m-%d')
    elif u_row['is_premium'] == 1:
        access_str = "Premium"

    joined_disp  = u_row['joined_at'].strftime('%Y-%m-%d') if u_row.get('joined_at') else "N/A"
    credits_disp = f"{u_row['credits']:,}"

    text = (
        f'{_b(f"{_lnk("[⌭]")} Aᴄᴄᴏᴜɴᴛ Iɴғᴏʀᴍᴀᴛɪᴏɴ <tg-emoji emoji-id=\"6100515480735321747\">✅</tg-emoji>")}\n'
        f'━━━━━━━━━━━━━━\n'
        f'{_b(f"{_lnk("⬢")} Usᴇʀ ➺ {username_link}")}\n'
        f'{_b(f"{_lnk("⬡")} Usᴇʀ ID ➺ <code>{user_id}</code>")}\n'
        f'{_b(f"{_lnk("⬢")} Pʟᴀɴ ➺ {_esc(access_str)}")}\n'
        f'{_b(f"{_lnk("⬡")} Cʀᴇᴅɪᴛs ➺ {credits_disp}")}\n'
        f'{_b(f"{_lnk("⬢")} Pᴜʀᴄʜᴀsᴇᴅ ᴏɴ ➺ {_esc(purchased_str)}")}\n'
        f'{_b(f"{_lnk("⬡")} Eɴᴅɪɴɢ ᴏɴ ➺ {_esc(ending_str)}")}\n'
        f'{_b(f"{_lnk("⬢")} Jᴏɪɴᴇᴅ ➺ {_esc(joined_disp)}")}\n'
        f'━━━━━━━━━━━━━━\n'
        f'{_b(f"{_lnk("⎔")} Dᴇᴠ ➺ <a href=\"https://t.me/broken_wiz\">𒉼 𝔦 乙</a>")}'
    )
    await message.reply(text, parse_mode="HTML")


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# COMMAND: /authall
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

@router.message(F.text.startswith("/authall"))
async def authall_command(message: types.Message):
    if message.from_user.id != ADMIN_ID:
        return

    rows = await asyncio.to_thread(_authall_db_sync)
    if not rows:
        await message.reply("𝗡𝗼 𝗽𝗿𝗲𝗺𝗶𝘂𝗺 𝘂𝘀𝗲𝗿𝘀 𝗳𝗼𝘂𝗻𝗱.")
        return

    output = io.BytesIO()
    output.write("𝗽𝗿𝗲𝗺𝗶𝘂𝗺 𝘂𝘀𝗲𝗿𝘀 𝗟𝗶𝘀𝘁\n\n".encode('utf-8'))
    for row in rows:
        expiry_date = row['premium_expiry'].strftime('%Y-%m-%d') if row['premium_expiry'] else "N/A"
        line = (
            f"ID: {row['user_id']}\n"
            f"Username: {row['username'] or 'N/A'}\n"
            f"Plan: {_display_plan_name(row['plan']) if row['plan'] else 'N/A'}\n"
            f"Credits: {row['credits']}\n"
            f"Expiry: {expiry_date}\n"
            f"{'-'*30}\n"
        ).encode('utf-8')
        output.write(line)

    filename = f"premium_users_{datetime.now().strftime('%Y%m%d')}.txt"
    document = BufferedInputFile(output.getvalue(), filename=filename)
    await message.reply_document(document=document)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# COMMAND: /gen_code
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

@router.message(F.text.startswith("/gen_code"))
async def gen_code_command(message: types.Message):
    if message.from_user.id != ADMIN_ID:
        await message.reply("❌ 𝗬𝗼𝘂 𝗮𝗿𝗲 𝗻𝗼𝘁 𝗮𝘂𝘁𝗵𝗼𝗿𝗶𝘇𝗲𝗱.")
        return

    args = message.text.split()[1:]
    if not args:
        await message.reply("❌ 𝗨𝘀𝗮𝗴𝗲: /gen_code {amount}")
        return

    try:
        amount = int(args[0])
    except ValueError:
        await message.reply("❌ 𝗜𝗻𝘃𝗮𝗹𝗶𝗱 𝗮𝗺𝗼𝘂𝗻𝘁.")
        return

    generated_codes = await asyncio.to_thread(_gen_code_db_sync, amount)
    formatted_codes = "\n".join([f"<code>{c}</code>" for c in generated_codes])
    response = (
        f"𝗔𝗺𝗼𝘂𝗻𝘁 ➺ {amount}\n"
        f"𝗖𝗿𝗲𝗱𝗶𝘁𝘀 ➺ 200\n\n"
        f"{formatted_codes}\n\n"
        f"𝗨𝘀𝗲 /claim 𝘁𝗼 𝗴𝗲𝘁 𝘆𝗼𝘂𝗿 𝗰𝗿𝗲𝗱𝗶𝘁𝘀."
    )
    await message.reply(response, parse_mode="HTML")


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# COMMAND: /key (admin only)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

@router.message(F.text.startswith("/key"))
async def key_command(message: types.Message):
    if message.from_user.id != ADMIN_ID:
        await message.reply("❌ 𝗬𝗼𝘂 𝗮𝗿𝗲 𝗻𝗼𝘁 𝗮𝘂𝘁𝗵𝗼𝗿𝗶𝘇𝗲𝗱.")
        return

    args = message.text.split()[1:]
    if len(args) < 4:
        await message.reply(
            "❌ 𝗨𝘀𝗮𝗴𝗲: /key {credits} {plan_name} {duration} {counts}\n\n"
            "𝗘𝘅𝗮𝗺𝗽𝗹𝗲𝘀:\n"
            "/key 999999 Swift 2d 1\n"
            "/key 999999 Turbo 7d 5\n"
            "/key 150 Trial 1h 10\n\n"
            "𝗗𝘂𝗿𝗮𝘁𝗶𝗼𝗻 𝗳𝗼𝗿𝗺𝗮𝘁𝘀: 30m · 1h · 6h · 1d · 7d · 30d · 60d"
        )
        return

    credits_input   = args[0]
    plan_name_input = _canonical_plan_name(args[1])
    duration_input  = args[2]
    count_input     = args[3]

    try:
        credits = int(credits_input)
        if credits <= 0:
            await message.reply("❌ 𝗖𝗿𝗲𝗱𝗶𝘁𝘀 𝗺𝘂𝘀𝘁 𝗯𝗲 𝗮 𝗽𝗼𝘀𝗶𝘁𝗶𝘃𝗲 𝗻𝘂𝗺𝗯𝗲𝗿.")
            return
    except ValueError:
        await message.reply("❌ 𝗜𝗻𝘃𝗮𝗹𝗶𝗱 𝗰𝗿𝗲𝗱𝗶𝘁𝘀 𝘃𝗮𝗹𝘂𝗲. 𝗠𝘂𝘀𝘁 𝗯𝗲 𝗮 𝗻𝘂𝗺𝗯𝗲𝗿.")
        return

    try:
        count = int(count_input)
        if count <= 0 or count > 100:
            await message.reply("❌ 𝗖𝗼𝘂𝗻𝘁 𝗺𝘂𝘀𝘁 𝗯𝗲 𝗯𝗲𝘁𝘄𝗲𝗲𝗻 𝟭 𝗮𝗻𝗱 𝟭𝟬𝟬.")
            return
    except ValueError:
        await message.reply("❌ 𝗜𝗻𝘃𝗮𝗹𝗶𝗱 𝗰𝗼𝘂𝗻𝘁. 𝗠𝘂𝘀𝘁 𝗯𝗲 𝗮 𝗻𝘂𝗺𝗯𝗲𝗿.")
        return

    duration_seconds = _parse_duration(duration_input)
    if duration_seconds is None:
        await message.reply(
            "❌ 𝗜𝗻𝘃𝗮𝗹𝗶𝗱 𝗱𝘂𝗿𝗮𝘁𝗶𝗼𝗻.\n"
            "𝗨𝘀𝗲: 𝟯𝟬𝗺 · 𝟭𝗵 · 𝟲𝗵 · 𝟭𝟮𝗵 · 𝟭𝗱 · 𝟯𝗱 · 𝟳𝗱 · 𝟭𝟱𝗱 · 𝟯𝟬𝗱 · 𝟲𝟬𝗱"
        )
        return

    try:
        keys = await asyncio.to_thread(
            _key_db_sync,
            credits,
            plan_name_input,
            duration_seconds,
            message.from_user.id,
            count,
        )
    except Exception as e:
        logging.error(f"Error generating premium key: {e}")
        await message.reply("❌ 𝗗𝗮𝘁𝗮𝗯𝗮𝘀𝗲 𝗘𝗿𝗿𝗼𝗿.")
        return

    duration_display = _seconds_to_display(duration_seconds)
    formatted_keys = "\n".join(f"<code>{key}</code>" for key in keys)
    await message.reply(
        f'<b>Pʀᴇᴍɪᴜᴍ Kᴇʏs Gᴇɴᴇʀᴀᴛᴇᴅ <tg-emoji emoji-id="5444987348334965906">✅</tg-emoji></b>\n\n'
        f'<b>Cᴏᴜɴᴛs ➺ {count}</b>\n'
        f'<b>Kᴇʏs:\n{formatted_keys}</b>\n'
        f'<b>Pʟᴀɴ ➺ {_esc(_display_plan_name(plan_name_input))}</b>\n'
        f'<b>Cʀᴇᴅɪᴛs ➺ {credits:,}</b>\n'
        f'<b>Dᴜʀᴀᴛɪᴏɴ ➺ {duration_display}</b>\n\n'
        f'<b>Usᴀɢᴇ ➺ /claim &lt;key&gt;</b>',
        parse_mode="HTML"
    )


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# FIXED COMMAND: /claim (Single notification only - NO DM)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

@router.message(F.text.startswith("/claim"))
async def claim_command(message: types.Message):
    user    = message.from_user
    user_id = user.id
    args    = message.text.split()[1:]
    
    if not args:
        await message.reply("❌ Usᴀɢᴇ: /claim {code}")
        return

    code = args[0].upper()
    logging.info("[Claim] User %s attempting to claim code: %s", user_id, code)
    
    # Process the claim in a thread
    status, data = await asyncio.to_thread(_claim_db_sync, user_id, code)
    logging.info("[Claim] Result for user %s code %s: %s", user_id, code, status)

    if status == "invalid":
        await message.reply("❌ 𝗜𝗻𝘃𝗮𝗹𝗶𝗱 𝗖𝗼𝗱𝗲.")
        return

    elif status == "claimed":
        await message.reply("❌ 𝗧𝗵𝗶𝘀 𝗰𝗼𝗱𝗲 𝗵𝗮𝘀 𝗯𝗲𝗲𝗻 𝗮𝗹𝗿𝗲𝗮𝗱𝘆 𝗰𝗹𝗮𝗶𝗺𝗲𝗱.")
        return

    elif status == "premium":
        logging.warning("[Claim] User %s already has active premium", user_id)
        _, expiry_dt = await asyncio.to_thread(get_premium_status, user_id)
        expires_on = expiry_dt.strftime('%Y-%m-%d') if expiry_dt else "N/A"
        await message.reply(_already_premium_notice(expires_on), parse_mode="HTML")
        return

    elif status == "ok":
        credits_added = data
        await message.reply(f"✅ 𝗦𝘂𝗰𝗰𝗲𝘀𝘀𝗳𝘂𝗹𝗹𝘆 𝗖𝗹𝗮𝗶𝗺𝗲𝗱 {credits_added} 𝗰𝗿𝗲𝗱𝗶𝘁𝘀!")
        return

    elif status == "premium_ok":
        # ── Premium key successfully claimed ──────────────────────────────
        plan_name = data['plan_name']
        duration_s = data['duration_seconds']
        
        duration_display = _seconds_to_display(duration_s)
        
        # Build user mention
        user_name = user.first_name or user.username or str(user_id)
        user_link = f'<a href="tg://user?id={user_id}">{_esc(user_name)}</a>'
        
        # Build developer mention
        dev_id = data.get('created_by') or ADMIN_ID
        dev_name = "𒉼 𝔦 乙" if dev_id == ADMIN_ID else "𒉼 𝔦 乙"
        try:
            dev_chat = await message.bot.get_chat(dev_id)
            if dev_id != ADMIN_ID:
                dev_name = dev_chat.first_name or dev_chat.username or dev_name
        except Exception:
            pass
        dev_link = f'<a href="tg://user?id={dev_id}">{_esc(dev_name)}</a>'

        # ── Send ONLY ONE notification to the user (in the chat) ──────────
        user_notification = (
            f'<b>Pʀᴇᴍɪᴜᴍ Aᴄᴛɪᴠᴀᴛᴇᴅ! </b><tg-emoji emoji-id="6100515480735321747">✅</tg-emoji>\n'
            f'<b>────────────</b>\n'
            f'<b>Pʟᴀɴ ➺ {_esc(_display_plan_name(plan_name))}</b>\n'
            f'<b>Dᴜʀᴀᴛɪᴏɴ ➺ {duration_display}</b>\n'
            f'<b>────────────</b>\n'
            f'<b>Dᴇᴠ ➺ {dev_link}</b>'
        )
        
        try:
            await message.reply(user_notification, parse_mode="HTML")
            logging.info("[Claim] Success notification sent to user %s", user_id)
        except Exception as reply_error:
            logging.error("[Claim] Reply failed: %s", reply_error)

        # ── Send Log Group Notification ──────────────────────────────────
        log_text = (
            f'<b>Kᴇʏ Cʟᴀɪᴍᴇᴅ </b><tg-emoji emoji-id="5444987348334965906">✅</tg-emoji>\n'
            f'<b>────────────</b>\n'
            f'<b>Usᴇʀ ➺ {user_link}</b>\n'
            f'<b>Pʟᴀɴ ➺ {_esc(_display_plan_name(plan_name))}</b>\n'
            f'<b>Dᴜʀᴀᴛɪᴏɴ ➺ {duration_display}</b>\n'
            f'<b>────────────</b>\n'
            f'<b>Dᴇᴠ ➺ {dev_link}</b>'
        )
        
        log_sent = await _send_log_notification(message.bot, LOG_CHANNEL_ID, log_text)
        
        if log_sent:
            logging.info("[Claim] Log group notification sent to %s", LOG_CHANNEL_ID)
        else:
            logging.warning("[Claim] Log group notification FAILED for %s", LOG_CHANNEL_ID)

    else:
        logging.error("[Claim] Unexpected status '%s' for user %s code %s", status, user_id, code)
        await message.reply("❌ 𝗘𝗿𝗿𝗼𝗿 𝗖𝗹𝗮𝗶𝗺𝗶𝗻𝗴 𝗰𝗼𝗱𝗲. 𝗖𝗼𝗻𝘁𝗮𝗰𝘁 𝘀𝘂𝗽𝗽𝗼𝗿𝘁.")


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# COMMAND: /me  — personal lifetime statistics
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

@router.message(F.text.startswith("/me"))
async def me_command(message: types.Message):
    """Show the calling user's own lifetime checker statistics."""
    user    = message.from_user
    user_id = user.id

    stats    = await asyncio.to_thread(get_user_lifetime_stats, user_id)
    charged  = stats['cc_charged_lifetime']
    approved = stats['cc_approved_lifetime']
    declined = stats['cc_declined_lifetime']
    total    = charged + approved + declined

    raw_name  = user.first_name or user.username or str(user_id)
    user_link = f'<a href="tg://user?id={user_id}">{_esc(raw_name)}</a>'

    text = (
        f'<b>𝐋𝐢𝐟𝐞𝐭𝐢𝐦𝐞 𝐒𝐭𝐚𝐭𝐬</b> '
        f'<tg-emoji emoji-id="5893376775781617954">🏆</tg-emoji>\n'
        f"━━━━━━━━━━━━━━━━━━━━━\n"
        f"<b>𝐔𝐬𝐞𝐫 ➺</b> {user_link}\n"
        f"<b>𝐔𝐬𝐞𝐫 𝐈𝐃 ➺</b> <code>{user_id}</code>\n"
        f"━━━━━━━━━━━━━━━━━━━━━\n"
        f'<tg-emoji emoji-id="5359719332542718652">💎</tg-emoji> '
        f"<b>𝐂𝐡𝐚𝐫𝐠𝐞𝐝 ➺</b> <b>{charged:,}</b>\n"
        f'<tg-emoji emoji-id="6044254523009012231">✅</tg-emoji> '
        f"<b>𝐀𝐩𝐩𝐫𝐨𝐯𝐞𝐝 ➺</b> <b>{approved:,}</b>\n"
        f'<tg-emoji emoji-id="5893081007153746175">❌</tg-emoji> '
        f"<b>𝐃𝐞𝐜𝐥𝐢𝐧𝐞𝐝 ➺</b> <b>{declined:,}</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━━\n"
        f"<b>𝐓𝐨𝐭𝐚𝐥 𝐂𝐡𝐞𝐜𝐤𝐞𝐝 ➺</b> <b>{total:,}</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━━\n"
        f'<b>𝐃𝐞𝐯 ➺</b> <a href="https://t.me/broken_wiz">𒉼 𝔦 乙</a>'
    )
    await message.reply(text, parse_mode="HTML", disable_web_page_preview=True)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# COMMAND: /all  — global lifetime statistics (admin only)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

@router.message(F.text.startswith("/all"))
async def all_command(message: types.Message):
    """Show the SQL-summed lifetime totals across all users (admin only)."""
    if message.from_user.id != ADMIN_ID:
        await message.reply("❌ 𝗬𝗼𝘂 𝗮𝗿𝗲 𝗻𝗼𝘁 𝗮𝘂𝘁𝗵𝗼𝗿𝗶𝘇𝗲𝗱 𝘁𝗼 𝘂𝘀𝗲 𝘁𝗵𝗶𝘀.")
        return

    totals = await asyncio.to_thread(get_all_lifetime_stats_totals)
    total_users    = totals['total_users']
    total_charged  = totals['total_charged']
    total_approved = totals['total_approved']
    total_declined = totals['total_declined']
    total_checked  = total_charged + total_approved + total_declined

    text = (
        f'<b>𝐆𝐥𝐨𝐛𝐚𝐥 𝐋𝐢𝐟𝐞𝐭𝐢𝐦𝐞 𝐒𝐭𝐚𝐭𝐬</b> '
        f'<tg-emoji emoji-id="5893376775781617954">🏆</tg-emoji>\n'
        f"━━━━━━━━━━━━━━━━━━━━━\n"
        f"<b>𝐓𝐨𝐭𝐚𝐥 𝐔𝐬𝐞𝐫𝐬 ➺</b> <b>{total_users:,}</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━━\n"
        f'<tg-emoji emoji-id="5359719332542718652">💎</tg-emoji> '
        f"<b>𝐓𝐨𝐭𝐚𝐥 𝐂𝐡𝐚𝐫𝐠𝐞𝐝 ➺</b> <b>{total_charged:,}</b>\n"
        f'<tg-emoji emoji-id="6044254523009012231">✅</tg-emoji> '
        f"<b>𝐓𝐨𝐭𝐚𝐥 𝐀𝐩𝐩𝐫𝐨𝐯𝐞𝐝 ➺</b> <b>{total_approved:,}</b>\n"
        f'<tg-emoji emoji-id="5893081007153746175">❌</tg-emoji> '
        f"<b>𝐓𝐨𝐭𝐚𝐥 𝐃𝐞𝐜𝐥𝐢𝐧𝐞𝐝 ➺</b> <b>{total_declined:,}</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━━\n"
        f"<b>𝐓𝐨𝐭𝐚𝐥 𝐂𝐡𝐞𝐜𝐤𝐞𝐝 ➺</b> <b>{total_checked:,}</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━━\n"
        f'<b>𝐃𝐞𝐯 ➺</b> <a href="https://t.me/broken_wiz">𒉼 𝔦 乙</a>'
    )
    await message.reply(text, parse_mode="HTML", disable_web_page_preview=True)