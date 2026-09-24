import asyncio
import psycopg2
from psycopg2.extras import RealDictCursor
from datetime import datetime, timedelta
import random
import string
import logging
import io

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# AIogram Imports
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
from aiogram import types, F, Router
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, BufferedInputFile

router = Router()

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# CONFIGURATION & IMPORTS
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
try:
    from database import DB_CONFIG, PooledConn, _premium_cache, _premium_cache_ttl
    _USE_POOL = True
except ImportError:
    DB_CONFIG = {"dbname": "your_db", "user": "your_user", "password": "your_pass", "host": "localhost"}
    _USE_POOL = False

ADMIN_ID = 8462705169
LOG_CHANNEL_ID = -1004453592223

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# DATABASE HELPERS (POSTGRESQL)
# All DB functions are synchronous — always call via asyncio.to_thread()
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def get_db_connection():
    if _USE_POOL:
        from database import get_db_connection as _pc
        conn = _pc()
        conn.cursor_factory = RealDictCursor
        return conn
    return psycopg2.connect(**DB_CONFIG, cursor_factory=RealDictCursor)

def init_db():
    conn = get_db_connection()
    cursor = conn.cursor()

    try:
        cursor.execute("ALTER TABLE users ALTER COLUMN user_id TYPE BIGINT")
        conn.commit()
    except Exception:
        conn.rollback()

    columns = [
        ("first_name",      "TEXT"),
        ("username",        "TEXT"),
        ("credits",         "INTEGER DEFAULT 0"),
        ("is_premium",      "INTEGER DEFAULT 0"),
        ("premium_expiry",  "TIMESTAMP"),
        ("joined_at",       "TIMESTAMP DEFAULT NOW()"),
    ]
    for col_name, col_type in columns:
        try:
            cursor.execute(f"ALTER TABLE users ADD COLUMN IF NOT EXISTS {col_name} {col_type}")
            conn.commit()
        except Exception as e:
            conn.rollback()
            logging.warning(f"Column check {col_name}: {e}")

    try:
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS receipts (
                id SERIAL PRIMARY KEY,
                receipt_id TEXT UNIQUE,
                user_id BIGINT,
                plan TEXT,
                amount_paid REAL,
                purchased_on TIMESTAMP,
                expires_on TIMESTAMP
            )
        ''')
        conn.commit()
    except Exception:
        conn.rollback()

    try:
        cursor.execute("ALTER TABLE receipts ADD COLUMN IF NOT EXISTS expires_on TIMESTAMP")
        conn.commit()
    except Exception:
        conn.rollback()

    try:
        cursor.execute("SELECT amount_paid FROM receipts LIMIT 1")
        conn.rollback()
    except Exception:
        conn.rollback()
        try:
            cursor.execute("ALTER TABLE receipts ADD COLUMN IF NOT EXISTS amount_paid REAL")
            conn.commit()
            try:
                cursor.execute("UPDATE receipts SET amount_paid = amount WHERE amount_paid IS NULL AND amount IS NOT NULL")
                conn.commit()
            except Exception:
                conn.rollback()
        except Exception as e:
            conn.rollback()
            logging.warning(f"Migration amount_paid check: {e}")

    try:
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS codes (
                code TEXT PRIMARY KEY,
                credits INTEGER,
                claimed_by BIGINT,
                claimed_at TIMESTAMP
            )
        ''')
        conn.commit()
    except Exception:
        conn.rollback()

    conn.close()

try:
    init_db()
except Exception as e:
    logging.error(f"DB Init Error: {e}")

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# SYNC LOGIC HELPERS
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

def get_premium_status(user_id):
    import time as _t
    if _USE_POOL:
        now = _t.monotonic()
        cached = _premium_cache.get(user_id)
        if cached is not None and now < cached[1]:
            return cached[0]
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT is_premium, premium_expiry FROM users WHERE user_id = %s", (user_id,))
    row = cursor.fetchone()
    if not row:
        conn.close()
        return False, None
    is_premium_flag = row['is_premium']
    expiry = row['premium_expiry']
    result = (False, None)
    if is_premium_flag == 1:
        if expiry:
            if datetime.now() < expiry:
                result = (True, expiry)
            else:
                cursor.execute(
                    "UPDATE users SET is_premium = 0, premium_expiry = NULL, credits = 150 WHERE user_id = %s",
                    (user_id,)
                )
                conn.commit()
                result = (False, None)
        else:
            cursor.execute("UPDATE users SET is_premium = 0 WHERE user_id = %s", (user_id,))
            conn.commit()
            result = (False, None)
    elif expiry:
        if datetime.now() > expiry:
            cursor.execute(
                "UPDATE users SET premium_expiry = NULL, credits = 150 WHERE user_id = %s",
                (user_id,)
            )
            conn.commit()
            result = (False, None)
    conn.close()
    if _USE_POOL:
        _premium_cache[user_id] = (result, _t.monotonic() + _premium_cache_ttl)
    return result

def _resolve_user_id_sync(target_input):
    """Resolve user ID from either numeric ID or username."""
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        
        # Check if input is numeric (user_id)
        if target_input.isdigit():
            cursor.execute("SELECT user_id FROM users WHERE user_id = %s", (int(target_input),))
            row = cursor.fetchone()
            if row:
                return row['user_id']
        
        # Check if input is username (with or without @)
        username = target_input.lstrip('@').lower()
        cursor.execute("SELECT user_id FROM users WHERE LOWER(username) = %s", (username,))
        row = cursor.fetchone()
        if row:
            return row['user_id']
        
        # Try to search by first_name (exact match)
        cursor.execute("SELECT user_id FROM users WHERE LOWER(first_name) = %s", (username,))
        row = cursor.fetchone()
        if row:
            return row['user_id']
        
        return None
    except Exception as e:
        logging.error(f"Error resolving user ID: {e}")
        return None
    finally:
        conn.close()

def _sub_db_sync(target_id, display_name, plan_name, days, credits, amount):
    """Full /sub DB update. Returns receipt_id or raises on error."""
    expiry_date = datetime.now() + timedelta(days=days)
    receipt_id = generate_receipt_id()
    purchased_on = datetime.now()
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO users (user_id, username, first_name, credits, joined_at)
            VALUES (%s, %s, %s, %s, %s)
            ON CONFLICT (user_id) DO NOTHING
        """, (target_id, "Unknown", "User", 0, datetime.now()))
        cursor.execute("UPDATE users SET first_name = %s WHERE user_id = %s", (display_name, target_id))
        cursor.execute(
            "UPDATE users SET is_premium = 1, premium_expiry = %s WHERE user_id = %s",
            (expiry_date, target_id)
        )
        cursor.execute(
            "UPDATE users SET credits = credits + %s WHERE user_id = %s",
            (credits, target_id)
        )
        cursor.execute(
            "INSERT INTO receipts (receipt_id, user_id, plan, amount_paid, purchased_on, expires_on) "
            "VALUES (%s, %s, %s, %s, %s, %s)",
            (receipt_id, target_id, plan_name, amount, purchased_on, expiry_date)
        )
        conn.commit()
        return receipt_id
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

def _adcr_db_sync(target_id, display_name, add_credits):
    """Add credits to user. Returns new total."""
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO users (user_id, username, first_name, credits, joined_at)
            VALUES (%s, %s, %s, %s, %s)
            ON CONFLICT (user_id) DO NOTHING
        """, (target_id, "Unknown", "User", 0, datetime.now()))
        cursor.execute(
            "UPDATE users SET credits = credits + %s WHERE user_id = %s",
            (add_credits, target_id)
        )
        cursor.execute("SELECT credits FROM users WHERE user_id = %s", (target_id,))
        updated = cursor.fetchone()
        new_total = updated['credits'] if updated else 0
        conn.commit()
        return new_total
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

def _rsub_db_sync(target_id):
    """Remove premium from user, reset credits to 150. Returns user details dict or None."""
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE users SET is_premium = 0, premium_expiry = NULL, credits = 150 WHERE user_id = %s",
            (target_id,)
        )
        conn.commit()
        cursor.execute("SELECT first_name, username FROM users WHERE user_id = %s", (target_id,))
        return cursor.fetchone()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

def _rc_db_sync(receipt_id):
    """Fetch receipt + user details. Returns row dict or None."""
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute('''
            SELECT r.*, u.first_name, u.is_premium, u.credits
            FROM receipts r
            JOIN users u ON r.user_id = u.user_id
            WHERE r.receipt_id = %s
        ''', (receipt_id,))
        return cursor.fetchone()
    finally:
        conn.close()

def _info_db_sync(user_id, username, first_name):
    """Fetch info row, creating user if missing. Returns dict."""
    get_premium_status(user_id)  # resets expired plans
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM users WHERE user_id = %s", (user_id,))
    u_row = cursor.fetchone()
    if not u_row:
        cursor.execute(
            "INSERT INTO users (user_id, username, first_name, credits, joined_at) VALUES (%s, %s, %s, %s, %s)",
            (user_id, username, first_name, 0, datetime.now())
        )
        conn.commit()
        cursor.execute("SELECT * FROM users WHERE user_id = %s", (user_id,))
        u_row = cursor.fetchone()
    receipt_row = None
    if u_row['is_premium'] == 1:
        cursor.execute(
            "SELECT plan, purchased_on FROM receipts WHERE user_id = %s ORDER BY purchased_on DESC LIMIT 1",
            (user_id,)
        )
        receipt_row = cursor.fetchone()
    conn.close()
    return dict(u_row), dict(receipt_row) if receipt_row else None

def _suball_db_sync():
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('''
        SELECT DISTINCT ON (u.user_id)
            u.user_id, u.username, r.receipt_id, r.purchased_on, r.plan, u.premium_expiry, u.credits
        FROM users u
        LEFT JOIN receipts r ON u.user_id = r.user_id
        WHERE u.is_premium = 1 AND u.premium_expiry > NOW()
        ORDER BY u.user_id, r.purchased_on DESC
    ''')
    rows = cursor.fetchall()
    conn.close()
    return rows

def _g_code_db_sync(amount):
    generated = []
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        for _ in range(amount):
            code = "WIZX-" + ''.join(random.choices(string.ascii_uppercase + string.digits, k=10)) + "-CHK"
            cursor.execute("INSERT INTO codes (code, credits) VALUES (%s, %s)", (code, 200))
            generated.append(code)
        conn.commit()
    except Exception as e:
        conn.rollback()
        logging.error(f"Error generating codes: {e}")
    finally:
        conn.close()
    return generated

def _claim_db_sync(user_id, code):
    """
    Returns one of:
      ("invalid",  None)
      ("claimed",  None)
      ("premium",  None)
      ("ok",       credits_added)
      ("error",    None)
    """
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM codes WHERE code = %s", (code,))
        row = cursor.fetchone()
        if not row:
            return "invalid", None
        if row['claimed_by'] is not None:
            return "claimed", None
        is_prem, _ = get_premium_status(user_id)
        if is_prem:
            return "premium", None
        cursor.execute(
            "UPDATE codes SET claimed_by = %s, claimed_at = %s WHERE code = %s",
            (user_id, datetime.now(), code)
        )
        cursor.execute(
            "UPDATE users SET credits = credits + %s WHERE user_id = %s",
            (row['credits'], user_id)
        )
        conn.commit()
        return "ok", row['credits']
    except Exception as e:
        conn.rollback()
        logging.error(f"Error claiming code: {e}")
        return "error", None
    finally:
        conn.close()

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# COMMAND: /buy — replies directly to the user's message
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

_PLAN_TEXT = (
    f'<tg-emoji emoji-id="5424976816530014958">👛</tg-emoji> <b>ᴀᴄᴄᴇꜱꜱ ➠ Sᴡɪꜰᴛ</b> <tg-emoji emoji-id="6253702009107516178">💎</tg-emoji>\n'
    f'<tg-emoji emoji-id="6136246765369694911">🦇</tg-emoji> <b>ᴘƦɪᴄᴇ ➠</b> 𝟳$\n'
    f'<tg-emoji emoji-id="6136246765369694911">🦇</tg-emoji> <b>ᴅᴜƦᴀᴛɪᴏɴ ➠</b> [𝟳 ᴅᴀʏꜱ]\n'
    f'<tg-emoji emoji-id="6136246765369694911">🦇</tg-emoji> <b>ᴄƦᴇᴅɪᴛꜱ ➠</b> 𝟭𝟱,𝟬𝟬𝟬\n'
    f'━━━━━━━━━━━━━━━━\n'
    f'<tg-emoji emoji-id="5424976816530014958">👛</tg-emoji> <b>ᴀᴄᴄᴇꜱꜱ ➠ TᴜƦʙᴏ</b> <tg-emoji emoji-id="6255712466118905093">⭐</tg-emoji>\n'
    f'<tg-emoji emoji-id="6136246765369694911">🦇</tg-emoji> <b>ᴘƦɪᴄᴇ ➠</b> 𝟭𝟰$\n'
    f'<tg-emoji emoji-id="6136246765369694911">🦇</tg-emoji> <b>ᴅᴜƦᴀᴛɪᴏɴ ➠</b> [𝟭𝟱 ᴅᴀʏꜱ]\n'
    f'<tg-emoji emoji-id="6136246765369694911">🦇</tg-emoji> <b>ᴄƦᴇᴅɪᴛꜱ ➠</b> 𝟮𝟱,𝟬𝟬𝟬\n'
    f'━━━━━━━━━━━━━━━━\n'
    f'<tg-emoji emoji-id="5424976816530014958">👛</tg-emoji> <b>ᴀᴄᴄᴇꜱꜱ ➠ NɪᴛʀƦᴏ</b> <tg-emoji emoji-id="6253702009107516178">⭐</tg-emoji>\n'
    f'<tg-emoji emoji-id="6136246765369694911">🦇</tg-emoji> <b>ᴘƦɪᴄᴇ ➠</b> 𝟮𝟱$\n'
    f'<tg-emoji emoji-id="6136246765369694911">🦇</tg-emoji> <b>ᴅᴜƦᴀᴛɪᴏɴ ➠</b> [𝟯𝟬 ᴅᴀʏꜱ]\n'
    f'<tg-emoji emoji-id="6136246765369694911">🦇</tg-emoji> <b>ᴄƦᴇᴅɪᴛꜱ ➠</b> 𝟲𝟬,𝟬𝟬𝟬\n'
    f'━━━━━━━━━━━━━━━━\n'
    f'<tg-emoji emoji-id="5424976816530014958">👛</tg-emoji> <b>ᴀᴄᴄᴇꜱꜱ ➠ Aᴘᴇx</b> <tg-emoji emoji-id="6255712466118905093">⚡</tg-emoji>\n'
    f'<tg-emoji emoji-id="6136246765369694911">🦇</tg-emoji> <b>ᴘƦɪᴄᴇ ➠</b> 𝟰𝟬$\n'
    f'<tg-emoji emoji-id="6136246765369694911">🦇</tg-emoji> <b>ᴅᴜƦᴀᴛɪᴏɴ ➠</b> [𝟲𝟬 ᴅᴀʏꜱ]\n'
    f'<tg-emoji emoji-id="6136246765369694911">🦇</tg-emoji> <b>ᴄƦᴇᴅɪᴛꜱ ➠</b> 𝟭,𝟬𝟬,𝟬𝟬𝟬'
)
#_PLAN_KB = InlineKeyboardMarkup(inline_keyboard=[
    #[InlineKeyboardButton(text='💎 𝗣𝗮𝘆 𝗩𝗶𝗮', callback_data="menu_payment_methods")]
#])

@router.message(F.text.startswith("/plan"))
async def plan_command(message: types.Message):
    """Replies directly to the user's /plan command with the pricing chart."""
    await message.reply(text=_PLAN_TEXT, parse_mode="HTML", #reply_markup=_PLAN_KB
    )

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# COMMAND: /sub
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

@router.message(F.text.startswith("/sub"))
async def sub_command(message: types.Message):
    user = message.from_user
    if user.id != ADMIN_ID:
        await message.reply("❌ 𝗬𝗼𝘂 𝗮𝗿𝗲 𝗻𝗼𝘁 𝗮𝘂𝘁𝗵𝗼𝗿𝗶𝘇𝗲𝗱 𝘁𝗼 𝘂𝘀𝗲 𝘁𝗵𝗶𝘀.")
        return

    args = message.text.split()[1:]
    if len(args) < 2:
        await message.reply("❌ 𝗨𝘀𝗮𝗴𝗲: /sub {user_id/username} {plan}\nPlans: swift, turbo, nitro, apex, owner\nExample: /sub 123456 apex")
        return

    target_input, plan = args[0], args[1].lower()

    plan_map = {
        "swift":  ("Swift 🚀",   7,   15000, 7),
        "turbo":  ("Turbo ⚡",   15,  25000, 14),
        "nitro":  ("Nitro 🔥",   30,  50000, 25),
        "apex":   ("Apex 👑",    60,  100000, 40),
        "owner":  ("Owner 👑",   365, 999999, 0),  # Owner plan with 0 price (free for admin use)
    }
    if plan not in plan_map:
        await message.reply("❌ 𝗜𝗻𝘃𝗮𝗹𝗶𝗱 𝗽𝗹𝗮𝗻. 𝗣𝗹𝗮𝗻𝘀: <b>Swift</b>, <b>Turbo</b>, <b>Nitro</b>, <b>Apex</b>, <b>Owner</b>", parse_mode="HTML")
        return

    # Resolve target ID in thread
    target_id = await asyncio.to_thread(_resolve_user_id_sync, target_input)
    if not target_id:
        await message.reply("❌ 𝗖𝗼𝘂𝗹𝗱 𝗻𝗼𝘁 𝗳𝗶𝗻𝗱 𝘂𝘀𝗲𝗿 𝗶𝗻 𝗗𝗮𝘁𝗮𝗯𝗮𝘀𝗲.")
        return

    plan_name, days, credits, amount = plan_map[plan]

    # Fetch display name from Telegram API (non-blocking)
    display_name = "User"
    try:
        chat = await message.bot.get_chat(target_id)
        display_name = chat.first_name or chat.username or "User"
    except Exception:
        pass

    user_link = f'<a href="tg://user?id={target_id}">{display_name}</a>'

    # DB update in thread
    try:
        receipt_id = await asyncio.to_thread(_sub_db_sync, target_id, display_name, plan_name, days, credits, amount)
    except Exception as e:
        logging.error(f"Error updating subscription: {e}")
        await message.reply("❌ 𝗗𝗮𝘁𝗮𝗯𝗮𝘀𝗲 𝗘𝗿𝗿𝗼𝗿.")
        return

    masked_id = mask_receipt_id(receipt_id)

    caption = (
        f"𝐂𝐨𝐧𝐠𝐫𝐚𝐭𝐮𝐥𝐚𝐭𝐢𝐨𝐧𝐬!🎉 𝐲𝐨𝐮𝐫 𝐚𝐜𝐜𝐞𝐬𝐬 𝐡𝐚𝐬 𝐛𝐞𝐞𝐧 𝐚𝐜𝐭𝐢𝐯𝐚𝐭𝐞𝐝.\n"
        f"𝗨𝘀𝗲𝗿 ➠ {user_link}\n"
        f"𝗔𝗰𝗰𝗲𝘀𝘀 ➠ <b>{plan_name}</b>\n"
        f"𝗗𝘂𝗿𝗮𝘁𝗶𝗼𝗻 ➠ {days} Days\n"
        f"𝗖𝗿𝗲𝗱𝗶𝘁𝘀 𝗔𝗱𝗱𝗲𝗱 ➠ +{credits:,}\n"
        f"𝗥𝗲𝗰𝗲𝗶𝗽𝘁 𝗜𝗗 ➠ <code>{receipt_id}</code>\n"
        f"𝗽𝗹𝗲𝗮𝘀𝗲 𝘀𝗮𝘃𝗲 𝘁𝗵𝗶𝘀 𝗿𝗲𝗰𝗲𝗶𝗽𝘁 𝗜𝗗."
    )
    #support_kb = InlineKeyboardMarkup(inline_keyboard=[
        #[InlineKeyboardButton(text="𝗦𝘂𝗽𝗽𝗼𝗿𝘁", url="https://t.me/FailureFr_07")]
    #])
    
    # For owner plan, use different log text (no amount shown)
    if plan == "owner":
        log_text = (
            f"<b>𝐎𝐖𝐍𝐄𝐑 𝐏𝐋𝐀𝐍 𝐀𝐂𝐓𝐈𝐕𝐀𝐓𝐄𝐃 👑</b>\n"
            f"<b>𝐔𝐬𝐞𝐫 ➠</b> {user_link}\n"
            f"<b>𝐀𝐜𝐜𝐞𝐬𝐬 ➠</b> <b>{plan_name}</b>\n"
            f"<b>𝐃𝐮𝐫𝐚𝐭𝐢𝐨𝐧 ➠</b> 365 Days\n"
            f"<b>𝐑𝐞𝐜𝐞𝐢𝐩𝐭 𝐈𝐃 ➠</b> <code>{masked_id}</code>"
        )
    else:
        log_text = (
            f"<b>𝐍𝐄𝐖 𝐏𝐋𝐀𝐍 𝐏𝐔𝐑𝐂𝐇𝐀𝐒𝐄𝐃 🛒</b>\n"
            f"<b>𝐔𝐬𝐞𝐫 ➠</b> {user_link}\n"
            f"<b>𝐀𝐜𝐜𝐞𝐬𝐬 ➠</b> <b>{plan_name}</b>\n"
            f"<b>𝐀𝐦𝐨𝐮𝐧𝐭 ➠</b> <b>{amount} $</b>\n"
            f"<b>𝐑𝐞𝐜𝐞𝐢𝐩𝐭 𝐈𝐃 ➠</b> <code>{masked_id}</code>"
        )
    
    #log_kb = InlineKeyboardMarkup(inline_keyboard=[
        #[InlineKeyboardButton(text="𝗕𝘂𝘆 𝗡𝗼𝘄", callback_data="show_buy_plans")]
    #])

    # Send DM to user + log to channel + admin confirm — all concurrently
    async def _dm_user():
        try:
            await message.bot.send_message(chat_id=target_id, text=caption, parse_mode="HTML", #reply_markup=support_kb
            )
        except Exception as e:
            logging.error(f"Could not DM user {target_id}: {e}")

    async def _reply():
        await message.reply(f"✅ Premium granted to {target_id} for {days} days with {credits:,} credits.")

    await asyncio.gather(
        _dm_user(),
        message.bot.send_message(chat_id=LOG_CHANNEL_ID, text=log_text, parse_mode="HTML"),
        _reply(),
    )

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# COMMAND: /adcr
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

@router.message(F.text.startswith("/adcr"))
async def adcr_command(message: types.Message):
    user = message.from_user
    if user.id != ADMIN_ID:
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

    user_link = f'<a href="tg://user?id={target_id}">{display_name}</a>'
    user_text = (
        f"𝐂𝐫𝐞𝐝𝐢𝐭𝐬 𝐀𝐝𝐝𝐞𝐝 ✅\n"
        f"𝐔𝐬𝐞𝐫 ➠ {user_link}\n"
        f"𝐂𝐫𝐞𝐝𝐢𝐭𝐬 𝐀𝐝𝐝𝐞𝐝 ➠ <b>{add_credits:,}</b>\n"
        f"𝐓𝐨𝐭𝐚𝐥 𝐂𝐫𝐞𝐝𝐢𝐭𝐬 ➠ <b>{new_total:,}</b>"
    )
    #support_kb = InlineKeyboardMarkup(inline_keyboard=[
        #[InlineKeyboardButton(text="𝗦𝘂𝗽𝗽𝗼𝗿𝘁", url="https://t.me/FailureFr_07")]
    #])

    async def _dm_user():
        try:
            await message.bot.send_message(chat_id=target_id, text=user_text, parse_mode="HTML", #reply_markup=support_kb
            )
        except Exception as e:
            logging.error(f"Could not DM user {target_id}: {e}")

    async def _reply():
        await message.reply(
            f"✅ Added <b>{add_credits:,}</b> credits to {user_link}.\n"
            f"𝐍𝐞𝐰 𝐓𝐨𝐭𝐚𝐥 ➠ <b>{new_total:,}</b>",
            parse_mode="HTML"
        )

    await asyncio.gather(
        _dm_user(),
        _reply(),
    )

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# COMMAND: /rsub
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

@router.message(F.text.startswith("/rsub"))
async def rsub_command(message: types.Message):
    user = message.from_user
    if user.id != ADMIN_ID:
        await message.reply("❌ 𝗬𝗼𝘂 𝗮𝗿𝗲 𝗻𝗼𝘁 𝗮𝘂𝘁𝗵𝗼𝗿𝗶𝘇𝗲𝗱 𝘁𝗼 𝘂𝘀𝗲 𝘁𝗵𝗶𝘀.")
        return

    args = message.text.split()[1:]
    if not args:
        await message.reply("❌ 𝗨𝘀𝗮𝗴𝗲: /rsub {user_id/username}")
        return

    target_id = await asyncio.to_thread(_resolve_user_id_sync, args[0])
    if not target_id:
        await message.reply("❌ 𝗖𝗼𝘂𝗹𝗱 𝗻𝗼𝘁 𝗳𝗶𝗻𝗱 𝘂𝘀𝗲𝗿 𝗶𝗻 𝗗𝗮𝘁𝗮𝗯𝗮𝘀𝗲.")
        return

    try:
        user_details = await asyncio.to_thread(_rsub_db_sync, target_id)
    except Exception as e:
        logging.error(f"Error removing subscription: {e}")
        await message.reply("❌ 𝗗𝗮𝘁𝗮𝗯𝗮𝘀𝗲 𝗘𝗿𝗿𝗼𝗿.")
        return

    if not user_details:
        await message.reply(f"✅ Premium removed from {target_id} and credits reset to 150.")
        return

    display_name = "User"
    temp_name = user_details['first_name'] if user_details['first_name'] else user_details['username']
    if temp_name and temp_name not in ["Unknown", "User"]:
        display_name = temp_name
    else:
        try:
            chat = await message.bot.get_chat(target_id)
            display_name = chat.first_name or "User"
        except Exception:
            pass

    dm_text = (
        f"𝐘𝐨𝐮𝐫 𝐚𝐜𝐜𝐞𝐬𝐬 𝐡𝐚𝐬 𝐛𝐞𝐞𝐧 𝐞𝐧𝐝𝐞𝐝. 𝐑𝐞𝐧𝐞𝐰𝐚𝐥 𝐧𝐨𝐰.\n\n"
        f"𝐔𝐬𝐞𝐫 ➠ {display_name}\n"
        f"𝐔𝐬𝐞𝐫 𝐈𝐃 ➠ <code>{target_id}</code>\n"
        f"𝐒𝐭𝐚𝐭𝐮𝐬 ➠ <b>Trial</b>\n"
        f"𝐂𝐫𝐞𝐝𝐢𝐭𝐬 ➠ <b>150</b>"
    )
    #buy_kb = InlineKeyboardMarkup(inline_keyboard=[
        #[InlineKeyboardButton(text="𝗕𝘂𝘆 𝗡𝗼𝘄", callback_data="show_buy_plans")]
    #])

    async def _dm_user():
        try:
            await message.bot.send_message(chat_id=target_id, text=dm_text, parse_mode="HTML", #reply_markup=buy_kb
            )
        except Exception as e:
            logging.error(f"Could not DM user {target_id}: {e}")

    async def _reply():
        await message.reply(f"✅ Premium removed from {target_id} and credits reset to 150.")

    await asyncio.gather(
        _dm_user(),
        _reply(),
    )

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# COMMAND: /rc
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

@router.message(F.text.startswith("/rc"))
async def rc_command(message: types.Message):
    user = message.from_user
    if user.id != ADMIN_ID:
        await message.reply("❌ 𝗬𝗼𝘂 𝗮𝗿𝗲 𝗻𝗼𝘁 𝗮𝘂𝘁𝗵𝗼𝗿𝗶𝘇𝗲𝗱.")
        return

    args = message.text.split()[1:]
    if not args:
        await message.reply("❌ 𝗨𝘀𝗮𝗴𝗲: /rc {receipt_id}")
        return

    receipt_id = args[0]
    row = await asyncio.to_thread(_rc_db_sync, receipt_id)

    if not row:
        await message.reply("❌ 𝗥𝗲𝗰𝗲𝗶𝗽𝘁 𝗜𝗗 𝗻𝗼𝘁 𝗳𝗼𝘂𝗻𝗱.")
        return

    uid = row['user_id']
    fname = row['first_name']
    if not fname or fname in ["User", "Unknown"]:
        try:
            chat = await message.bot.get_chat(uid)
            fname = chat.first_name or "Unknown"
        except Exception:
            fname = "Unknown"

    user_link = f'<a href="tg://user?id={uid}">{fname}</a>'
    amount_val = row.get('amount_paid') if row.get('amount_paid') is not None else row.get('amount', 0)
    date_str    = row['purchased_on'].strftime('%Y-%m-%d') if row['purchased_on'] else "N/A"
    expires_str = row['expires_on'].strftime('%Y-%m-%d') if row.get('expires_on') else "N/A"
    credits_str = f"{row['credits']:,}"

    text = (
        f"𝗨𝘀𝗲𝗿 ➠ {user_link}\n"
        f"𝗨𝘀𝗲𝗿 𝗜𝗗 ➠ <code>{uid}</code>\n"
        f"𝗔𝗰𝗰𝗲𝘀𝘀 ➠ <b>{row['plan']}</b>\n"
        f"𝗣𝘂𝗿𝗰𝗵𝗮𝘀𝗲𝗱 𝗢𝗻 ➠ {date_str}\n"
        f"𝗘𝘅𝗽𝗶𝗿𝗲𝘀 𝗢𝗻 ➠ <b>{expires_str}</b>\n"
        f"𝗥𝗲𝗰𝗲𝗶𝗽𝘁 𝗜𝗗 ➠ <code>{row['receipt_id']}</code>\n"
        f"𝗔𝗺𝗼𝘂𝗻𝘁 ➠ {amount_val} $\n"
        f"𝗖𝘂𝗿𝗿𝗲𝗻𝘁 𝗖𝗿𝗲𝗱𝗶𝘁𝘀 ➠ {credits_str}"
        
    )
    #keyboard = InlineKeyboardMarkup(inline_keyboard=[
        #[InlineKeyboardButton(text="𝑪𝑨𝑹𝑫 ✘ 𝑪𝑯𝑲", url="https://t.me/CARDXV4_BOT")]
    #])
    await message.reply(text, parse_mode="HTML", #reply_markup=keyboard
    )

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# COMMAND: /info
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

@router.message(F.text.startswith("/info"))
async def info_command(message: types.Message):
    user = message.from_user
    user_id = user.id

    u_row, r_row = await asyncio.to_thread(_info_db_sync, user_id, user.username, user.first_name)

    raw_name = "N/A"
    if user.username:
        raw_name = f"@{user.username}"
    elif user.first_name:
        raw_name = user.first_name
    elif u_row.get('username') and u_row['username'].lower() not in ['unknown', 'user', 'none']:
        raw_name = u_row['username']
    elif u_row.get('first_name') and u_row['first_name'].lower() not in ['unknown', 'user', 'none']:
        raw_name = u_row['first_name']

    username_link = f'<a href="tg://user?id={user_id}">{raw_name}</a>' if raw_name != "N/A" else raw_name

    access_str    = "Trial"
    purchased_str = "N/A"
    ending_str    = "N/A"

    if u_row['is_premium'] == 1 and r_row:
        access_str    = r_row['plan']
        purchased_str = r_row['purchased_on'].strftime('%Y-%m-%d') if r_row['purchased_on'] else "N/A"
        if u_row.get('premium_expiry'):
            ending_str = u_row['premium_expiry'].strftime('%Y-%m-%d')
    elif u_row['is_premium'] == 1:
        access_str = "Premium"

    joined_disp  = u_row['joined_at'].strftime('%Y-%m-%d') if u_row.get('joined_at') else "N/A"
    credits_disp = f"{u_row['credits']:,}"

    text = (
        f"𝗨𝘀𝗲𝗿 ➠ {username_link}\n"
        f"𝗨𝘀𝗲𝗿 𝗜𝗗 ➠ <code>{user_id}</code>\n"
        f"𝗔𝗰𝗰𝗲𝘀𝘀 ➠ <b>{access_str}</b>\n"
        f"𝗣𝘂𝗿𝗰𝗵𝗮𝘀𝗲𝗱 𝗼𝗻 ➠ <b>{purchased_str}</b>\n"
        f"𝗘𝗻𝗱𝗶𝗻𝗴 𝗼𝗻 ➠ <b>{ending_str}</b>\n"
        f"𝗖𝗿𝗲𝗱𝗶𝘁𝘀 ➠ <b>{credits_disp}</b>\n"
        f"𝗝𝗼𝗶𝗻𝗲𝗱 ➠ <b>{joined_disp}</b>"
    )
    #keyboard = InlineKeyboardMarkup(inline_keyboard=[
        #[InlineKeyboardButton(text="𝑪𝑨𝑹𝑫 ✘ 𝑪𝑯𝑲", url="https://t.me/CARDXV4_BOT")]
    #])
    await message.reply(text, parse_mode="HTML", #reply_markup=keyboard
    )

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# COMMAND: /suball
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

@router.message(F.text.startswith("/suball"))
async def suball_command(message: types.Message):
    user = message.from_user
    if user.id != ADMIN_ID:
        return

    rows = await asyncio.to_thread(_suball_db_sync)

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
            f"Plan: {row['plan'] or 'N/A'}\n"
            f"Credits: {row['credits']}\n"
            f"Expiry: {expiry_date}\n"
            f"{'-'*30}\n"
        ).encode('utf-8')
        output.write(line)

    filename = f"premium_users_{datetime.now().strftime('%Y%m%d')}.txt"
    document = BufferedInputFile(output.getvalue(), filename=filename)
    await message.reply_document(document=document)

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# COMMAND: /g_code
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

@router.message(F.text.startswith("/g_code"))
async def g_code_command(message: types.Message):
    user = message.from_user
    if user.id != ADMIN_ID:
        await message.reply("❌ 𝗬𝗼𝘂 𝗮𝗿𝗲 𝗻𝗼𝘁 𝗮𝘂𝘁𝗵𝗼𝗿𝗶𝘇𝗲𝗱.")
        return

    args = message.text.split()[1:]
    if not args:
        await message.reply("❌ 𝗨𝘀𝗮𝗴𝗲: /g_code {amount}")
        return

    try:
        amount = int(args[0])
    except ValueError:
        await message.reply("❌ 𝗜𝗻𝘃𝗮𝗹𝗶𝗱 𝗮𝗺𝗼𝘂𝗻𝘁.")
        return

    generated_codes = await asyncio.to_thread(_g_code_db_sync, amount)
    formatted_codes = "\n".join([f"<code>{c}</code>" for c in generated_codes])
    response = (
        f"𝗔𝗺𝗼𝘂𝗻𝘁 ➠ {amount}\n"
        f"𝗖𝗿𝗲𝗱𝗶𝘁𝘀 ➠ 200\n\n"
        f"{formatted_codes}\n\n"
        f"𝗨𝘀𝗲 /claim 𝘁𝗼 𝗴𝗲𝘁 𝘆𝗼𝘂𝗿 𝗰𝗿𝗲𝗱𝗶𝘁𝘀."
    )
    await message.reply(response, parse_mode="HTML")

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# COMMAND: /claim
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

@router.message(F.text.startswith("/claim"))
async def claim_command(message: types.Message):
    user = message.from_user
    user_id = user.id

    args = message.text.split()[1:]
    if not args:
        await message.reply("❌ 𝗨𝘀𝗮𝗴𝗲: /claim {code}")
        return

    code = args[0].upper()
    status, credits_added = await asyncio.to_thread(_claim_db_sync, user_id, code)

    if status == "invalid":
        await message.reply("❌ 𝗜𝗻𝘃𝗮𝗹𝗶𝗱 𝗖𝗼𝗱𝗲.")
    elif status == "claimed":
        await message.reply("❌ 𝗧𝗵𝗶𝘀 𝗰𝗼𝗱𝗲 𝗵𝗮𝘀 𝗯𝗲𝗲𝗻 𝗮𝗹𝗿𝗲𝗮𝗱𝘆 𝗰𝗹𝗮𝗶𝗺𝗲𝗱.")
    elif status == "premium":
        await message.reply("❌ 𝗨𝘀𝗲𝗿𝘀 𝘄𝗶𝘁𝗵 𝗮𝗻 𝗮𝗰𝘁𝗶𝘃𝗲 𝗽𝗹𝗮𝗻 𝗰𝗮𝗻𝗻𝗼𝘁 𝗿𝗲𝗱𝗲𝗲𝗺 𝗰𝗼𝗱𝗲𝘀.")
    elif status == "ok":
        await message.reply(f"✅ 𝗦𝘂𝗰𝗰𝗲𝘀𝘀𝗳𝘂𝗹𝗹𝘆 𝗖𝗹𝗮𝗶𝗺𝗲𝗱 {credits_added} 𝗰𝗿𝗲𝗱𝗶𝘁𝘀!")
    else:
        await message.reply("❌ 𝗘𝗿𝗿𝗼𝗿 𝗖𝗹𝗮𝗶𝗺𝗶𝗻𝗴 𝗰𝗼𝗱𝗲. 𝗖𝗼𝗻𝘁𝗮𝗰𝘁 𝘀𝘂𝗽𝗽𝗼𝗿𝘁.")