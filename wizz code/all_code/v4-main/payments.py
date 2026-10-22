# ═══════════════════════════════════════════════════════════════════════════════
# payments.py — Plisio Crypto Payment Gateway  |  CHK X WIZ  v12
# ═══════════════════════════════════════════════════════════════════════════════
#
# Plisio gives a hosted checkout page for every invoice. The bot shares the link
# with the user and automatically verifies the operation status until it's paid.
#
# Flow: Plan → open Plisio checkout page (BTC/ETH/USDT/TRX/…) → auto-detect → activate
# ═══════════════════════════════════════════════════════════════════════════════

import urllib.request
import urllib.parse
import urllib.error
import json
import asyncio
import time
import html
import logging
import random
import string
from typing import Optional, Dict, Any
from datetime import datetime, timedelta

# ═══════════════════════════════════════════════════════════════════════════════
# CONFIG
# ═══════════════════════════════════════════════════════════════════════════════

PLISIO_API_KEY = "Y_gjUuqwH31qBUbIdevuGNGl4nKizHVZLwznDaY-24JsI3Ko--agJYyfzcWRXscO"
PLISIO_API_BASE = "https://api.plisio.net/api/v1"

PLISIO_EXPIRE_MIN = 60          # invoice lifetime in minutes
PLISIO_POLL_SECONDS = 6         # how often we check the operation status

LOG_CHANNEL_ID = -1003822850440 # purchase log channel (also pinned)
BOT_LINK       = "https://t.me/ladkichut03_bot"   # deep-link base for /plan

# ═══════════════════════════════════════════════════════════════════════════════
# PLANS
# ═══════════════════════════════════════════════════════════════════════════════

PLANS: Dict[str, Dict[str, Any]] = {
    "swift": {"price": 3,  "days": 2,  "credits": 999999999, "display": "ꕶᴡ𝖎ғ†"},
    "turbo": {"price": 7,  "days": 7,  "credits": 999999999, "display": "Ƭᴜʀʙᴏ"},
    "nitro": {"price": 14, "days": 15, "credits": 999999999, "display": "ɴɪⲧʀᴏ"},
    "apex":  {"price": 25, "days": 30, "credits": 999999999, "display": "ꫝᴘᴇ✗"},
}

# ═══════════════════════════════════════════════════════════════════════════════
# DB
# ═══════════════════════════════════════════════════════════════════════════════

def init_payments_db():
    try:
        from database import PooledConn
        with PooledConn() as conn:
            cur = conn.cursor()
            cur.execute("""
                CREATE TABLE IF NOT EXISTS payment_tracks (
                    track_id    TEXT PRIMARY KEY,
                    user_id     BIGINT,
                    plan        TEXT,
                    price_usd   REAL,
                    pay_amount  TEXT,
                    currency    TEXT,
                    network     TEXT,
                    address     TEXT,
                    invoice_url TEXT,
                    order_id    TEXT,
                    status      TEXT DEFAULT 'Pending',
                    created_at  TIMESTAMP DEFAULT NOW(),
                    paid_at     TIMESTAMP
                )
            """)
            cur.execute("ALTER TABLE payment_tracks ADD COLUMN IF NOT EXISTS address TEXT")
            cur.execute("ALTER TABLE payment_tracks ADD COLUMN IF NOT EXISTS invoice_url TEXT")
            cur.execute("ALTER TABLE payment_tracks ADD COLUMN IF NOT EXISTS order_id TEXT")
            cur.execute("ALTER TABLE payment_tracks ADD COLUMN IF NOT EXISTS currency TEXT")
            cur.execute("ALTER TABLE payment_tracks ADD COLUMN IF NOT EXISTS network TEXT")
            cur.execute("ALTER TABLE payment_tracks ADD COLUMN IF NOT EXISTS paid_at TIMESTAMP")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_payment_tracks_user  ON payment_tracks(user_id)")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_payment_tracks_status ON payment_tracks(status)")
            conn.commit()
    except Exception as e:
        logging.error(f"[PayDB] init error: {e}")

try:
    init_payments_db()
except Exception:
    pass


def _save_payment_db(track_id, user_id, plan, price_usd, pay_amount,
                     currency, network, invoice_url, order_id, address=None):
    try:
        from database import PooledConn
        addr = address or invoice_url
        with PooledConn() as conn:
            cur = conn.cursor()
            cur.execute("""
                INSERT INTO payment_tracks
                    (track_id, user_id, plan, price_usd, pay_amount,
                     currency, network, address, invoice_url, order_id)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                ON CONFLICT (track_id) DO NOTHING
            """, (track_id, user_id, plan, price_usd, str(pay_amount),
                  currency, network, addr, invoice_url, order_id))
            conn.commit()
    except Exception as e:
        logging.error(f"[PayDB] save error: {e}")


def _update_payment_meta_db(track_id: str, currency: str, network: str, address: str):
    try:
        from database import PooledConn
        with PooledConn() as conn:
            cur = conn.cursor()
            cur.execute(
                "UPDATE payment_tracks SET currency=%s, network=%s, address=%s "
                "WHERE track_id=%s",
                (currency, network, address, track_id)
            )
            conn.commit()
    except Exception as e:
        logging.error(f"[PayDB] update meta error: {e}")


def _update_payment_status_db(track_id: str, status: str):
    try:
        from database import PooledConn
        with PooledConn() as conn:
            cur = conn.cursor()
            if status == "Paid":
                cur.execute(
                    "UPDATE payment_tracks SET status=%s, paid_at=NOW() WHERE track_id=%s",
                    (status, track_id)
                )
            else:
                cur.execute(
                    "UPDATE payment_tracks SET status=%s WHERE track_id=%s",
                    (status, track_id)
                )
            conn.commit()
    except Exception as e:
        logging.error(f"[PayDB] update status error: {e}")


def get_payment_by_track_id(track_id: str) -> Optional[Dict]:
    try:
        from database import PooledConn
        from psycopg2.extras import RealDictCursor
        with PooledConn() as conn:
            cur = conn.cursor(cursor_factory=RealDictCursor)
            cur.execute("SELECT * FROM payment_tracks WHERE track_id=%s", (track_id,))
            row = cur.fetchone()
            return dict(row) if row else None
    except Exception as e:
        logging.error(f"[PayDB] get error: {e}")
        return None


def get_payment_by_address(address: str) -> Optional[Dict]:
    try:
        from database import PooledConn
        from psycopg2.extras import RealDictCursor
        with PooledConn() as conn:
            cur = conn.cursor(cursor_factory=RealDictCursor)
            cur.execute(
                "SELECT * FROM payment_tracks WHERE track_id=%s OR address=%s OR invoice_url=%s "
                "ORDER BY created_at DESC LIMIT 1",
                (address, address, address)
            )
            row = cur.fetchone()
            return dict(row) if row else None
    except Exception as e:
        logging.error(f"[PayDB] get by address error: {e}")
        return None

# ═══════════════════════════════════════════════════════════════════════════════
# IN-MEMORY SESSIONS
# ═══════════════════════════════════════════════════════════════════════════════

active_payments: Dict[str, Dict[str, Any]] = {}
user_sessions:   Dict[int, Dict[str, str]] = {}

_bot = None

def set_bot(bot):
    global _bot
    _bot = bot

def get_bot():
    return _bot

# ═══════════════════════════════════════════════════════════════════════════════
# PLISIO HTTP HELPERS
# ═══════════════════════════════════════════════════════════════════════════════

def _plisio_get(path: str, params: Optional[dict] = None) -> Optional[dict]:
    query_params = dict(params or {})
    query_params["api_key"] = PLISIO_API_KEY
    url = f"{PLISIO_API_BASE}/{path}"
    if query_params:
        url += "?" + urllib.parse.urlencode(query_params)
    try:
        req = urllib.request.Request(
            url,
            headers={"User-Agent": "CHKxWIZ-Bot/12.0", "Accept": "application/json"},
        )
        resp = urllib.request.urlopen(req, timeout=20)
        return json.loads(resp.read())
    except urllib.error.HTTPError as e:
        try:
            err = json.loads(e.read())
        except Exception:
            err = {}
        logging.error(f"[Plisio] GET /{path} HTTP {e.code}: {err}")
        return err or None
    except Exception as e:
        logging.error(f"[Plisio] GET /{path} failed: {e}")
        return None

# ═══════════════════════════════════════════════════════════════════════════════
# PAYMENT CREATION  (hosted checkout page)
# ═══════════════════════════════════════════════════════════════════════════════

def _fetch_operation_meta(track_id: str) -> Dict[str, str]:
    """Return the crypto {currency, network, address} Plisio assigns to an
    invoice. Plisio only mints the deposit address once the buyer opens the
    checkout page, so this can be empty right after creation."""
    res = _plisio_get(f"operations/{track_id}")
    if not res or res.get("status") != "success":
        return {}
    d        = res.get("data") or {}
    currency = str(d.get("currency") or d.get("psys_cid") or "").strip()
    address  = str(d.get("address") or d.get("to_address") or "").strip()
    network  = PLISIO_CURRENCY_NETWORKS.get(currency, currency or "")
    return {"currency": currency, "network": network, "address": address}

def create_payment(user_id: int, plan: str, retries: int = 3) -> Optional[Dict]:
    if plan not in PLANS:
        return None

    plan_info = PLANS[plan]
    order_id  = f"CHKXWIZ_{user_id}_{plan}_{int(datetime.now().timestamp())}"

    params = {
        "source_currency": "USD",
        "source_amount":  str(plan_info["price"]),
        "order_name":     plan_info["display"],
        "order_number":   order_id,          # must be unique per order
        "expire_min":     str(PLISIO_EXPIRE_MIN),
        "language":       "en_US",
        # no `currency` → Plisio auto-selects a coin and the buyer can switch on the page
    }

    last_err = None
    for attempt in range(max(1, retries)):
        res = _plisio_get("invoices/new", params)
        if res and res.get("status") == "success" and res.get("data"):
            break
        last_err = (res or {}).get("data") or res or {}
        if attempt < retries - 1:
            logging.warning(f"[Plisio] Invoice creation attempt {attempt+1} failed: {last_err}")
            time.sleep(1 + attempt)

    if not res or res.get("status") != "success" or not res.get("data"):
        logging.error(f"[Plisio] Payment error: {last_err}")
        return None

    data        = res["data"] or {}
    txn_id      = data.get("txn_id")
    invoice_url = data.get("invoice_url")
    if not txn_id or not invoice_url:
        logging.error(f"[Plisio] Missing txn_id/invoice_url: {data}")
        return None

    # Plisio assigns the deposit address once the checkout page is opened.
    meta = _fetch_operation_meta(txn_id)
    if not meta.get("address"):
        time.sleep(2)
        meta = _fetch_operation_meta(txn_id)

    currency = meta.get("currency", "")
    network  = meta.get("network", "")
    address  = meta.get("address", "")

    payment_data = {
        "track_id":    txn_id,
        "invoice_url": invoice_url,
        "price":       plan_info["price"],
        "order_id":    order_id,
        "status":      "Pending",
        "currency":    currency,
        "network":     network,
        "address":     address,
        "expire_min":  PLISIO_EXPIRE_MIN,
    }

    _save_payment_db(
        txn_id, user_id, plan,
        plan_info["price"], str(plan_info["price"]),
        currency, network, invoice_url, order_id, address or None,
    )
    logging.info(f"[Plisio] Invoice created: {txn_id} | ${plan_info['price']} | {invoice_url}")
    return payment_data


# ═══════════════════════════════════════════════════════════════════════════════
# STATUS CHECK
# ═══════════════════════════════════════════════════════════════════════════════

# Plisio statuses that mean "money is in" (mismatch = overpaid, still good).
PAID_STATUSES   = ("completed", "paid", "overpaid", "mismatch")
# Statuses that mean the money is arriving / waiting for confirmations.
PENDING_STATUSES = ("new", "pending", "pending internal", "email_sent",
                    "underpaid")
# Partial top-ups still arrive: accept if they cover the invoice, else keep
# polling until the invoice window closes.
PARTIAL_STATUSES = ("partial_paid",)
# Dead statuses: no payment, replaced invoice, or gateway gave up — check the
# amount + any sibling invoice before declaring Expired.
DEAD_STATUSES = ("expired", "cancelled", "cancelled duplicate", "canceled",
                 "error", "failed", "system_fail")

def min_acceptable_usd(price_usd: float) -> float:
    """Accept small underpayments (network/fee rounding) and any overpayment.
    $3 plan → $2.95. Larger plans → 1% slack with a $0.05 floor."""
    try:
        price = float(price_usd or 0)
    except Exception:
        return 0.0
    if price <= 0:
        return 0.0
    return price - max(0.05, price * 0.01)


def _fetch_invoice_detail(track_id: str) -> Dict[str, Any]:
    """Rich invoice payload: amount, received_amount, params.source_amount…"""
    res = _plisio_get(f"invoices/{track_id}")
    if not res or res.get("status") != "success":
        return {}
    d = res.get("data") or {}
    return d.get("invoice") or d or {}


def _received_usd(inv: Dict[str, Any]) -> Optional[float]:
    """How much actually arrived, in USD."""
    try:
        received = float(inv.get("received_amount") or 0)
        rate     = float(inv.get("source_rate") or 0)
        if received > 0 and rate > 0:
            return received * rate
    except Exception:
        pass
    return None


def _paid_within_tolerance(track_id: str) -> bool:
    """True when the money that arrived covers the invoice (within slack)."""
    inv = _fetch_invoice_detail(track_id)
    if not inv:
        return False

    price = 0.0
    try:
        price = float(((inv.get("params") or {}).get("source_amount")) or 0)
    except Exception:
        price = 0.0
    if price <= 0:
        row = get_payment_by_track_id(track_id)
        price = float(row.get("price_usd") or 0) if row else 0.0
    if price <= 0:
        return False

    minimum = min_acceptable_usd(price)
    got     = _received_usd(inv)

    if got is None:
        # Same-units fallback (crypto → crypto): received/invoice × price.
        try:
            received = float(inv.get("received_amount") or 0)
            full     = float(inv.get("amount") or 0)
            if received > 0 and full > 0:
                got = (received / full) * price
        except Exception:
            got = None

    if got is None:
        return False
    return got >= minimum - 1e-9


def _sibling_paid(track_id: str, data: Dict[str, Any], depth: int) -> bool:
    """True only if a REAL sibling (same order_number) settled this invoice.

    The buyer may switch currency on the checkout page — Plisio then cancels the
    parent invoice and the payment lands on a child invoice. Plisio's operations
    list endpoint IGNORES the order_number filter (it returns unrelated shop
    operations), so trusting that list caused ANY previously-settled payment on
    the shop to flip an unpaid, expired invoice to 'Paid'. Every candidate is now
    verified through its own invoice detail and MUST carry the same order_number.
    """
    if depth > 3:
        return False

    order_id = None
    row = get_payment_by_track_id(track_id)
    if row:
        order_id = row.get("order_id")
    if not order_id:
        params = (_fetch_invoice_detail(track_id).get("params") or {})
        order_id = params.get("order_number")
    if not order_id:
        return False

    res = _plisio_get("operations", {"order_number": str(order_id), "per-page": 50})
    if not res or res.get("status") != "success":
        return False

    seen = 0
    for op in (res.get("data") or {}).get("operations") or []:
        other = str(op.get("txn_id") or "")
        if not other or other == track_id:
            continue
        if seen >= 15:
            break
        seen += 1

        inv = _fetch_invoice_detail(other)
        if not inv:
            continue
        inv_order = str(((inv.get("params") or {}).get("order_number")) or "").strip()
        if inv_order != str(order_id):
            # Different order — returned despite the filter; not our sibling.
            continue

        raw = str(inv.get("status") or op.get("status") or "").strip().lower()
        if raw in PAID_STATUSES:
            if _paid_within_tolerance(other):
                return True
            continue
        if raw in PENDING_STATUSES:
            if _paid_within_tolerance(other):
                return True
            continue
        if check_payment_status(other, depth + 1) == "Paid":
            return True
    return False


def check_payment_status(track_id: str, _depth: int = 0) -> str:
    if _depth > 3:
        return "Pending"
    res = _plisio_get(f"operations/{track_id}")
    if not res or res.get("status") != "success":
        return "Pending"

    data = res.get("data") or {}
    raw  = str(data.get("status", "")).strip().lower()

    if raw in PAID_STATUSES:
        if raw in ("overpaid", "mismatch") and not _paid_within_tolerance(track_id):
            # Plisio flags these without a settled full amount — require proof.
            status = "Pending"
        else:
            status = "Paid"
    elif raw in PENDING_STATUSES:
        status = "Pending"
    elif raw in PARTIAL_STATUSES:
        status = "Paid" if _paid_within_tolerance(track_id) else "Pending"
    else:
        # Dead / replaced: the invoice may still have been funded elsewhere.
        status = "Expired"
        if _sibling_paid(track_id, data, _depth) or _paid_within_tolerance(track_id):
            status = "Paid"

    if track_id in active_payments:
        active_payments[track_id]["status"] = status
    return status


def _claim_paid(track_id: str) -> bool:
    """Atomically flip a track to Paid. Returns True only for the first caller,
    so plan activation never runs twice (monitor vs /track)."""
    try:
        from database import PooledConn
        with PooledConn() as conn:
            cur = conn.cursor()
            cur.execute(
                "UPDATE payment_tracks SET status='Paid', paid_at=NOW() "
                "WHERE track_id=%s AND (status IS NULL OR status <> 'Paid')",
                (track_id,),
            )
            claimed = cur.rowcount > 0
            conn.commit()
            return bool(claimed)
    except Exception as e:
        logging.error(f"[PayDB] claim paid {track_id}: {e}")
        return False


# ═══════════════════════════════════════════════════════════════════════════════
# PLAN ACTIVATION
# ═══════════════════════════════════════════════════════════════════════════════

def generate_receipt_id():
    return f"CHK-{''.join(random.choices(string.digits, k=6))}-XWIZ"


def activate_plan(user_id: int, plan: str) -> bool:
    if plan not in PLANS:
        return False
    plan_info = PLANS[plan]
    try:
        from database import PooledConn
        from psycopg2.extras import RealDictCursor

        expiry = datetime.now() + timedelta(days=plan_info["days"])

        with PooledConn() as conn:
            cur = conn.cursor(cursor_factory=RealDictCursor)

            cur.execute("""
                INSERT INTO users (user_id, username, first_name, credits, joined_at)
                VALUES (%s,%s,%s,%s,%s) ON CONFLICT (user_id) DO NOTHING
            """, (user_id, "Unknown", "User", 0, datetime.now()))

            cur.execute("SELECT premium_expiry FROM users WHERE user_id=%s", (user_id,))
            row = cur.fetchone()
            if row and row.get("premium_expiry"):
                current = row["premium_expiry"]
                if current and datetime.now() < current:
                    expiry = current + timedelta(days=plan_info["days"])

            cur.execute(
                "UPDATE users SET is_premium=1, premium_expiry=%s WHERE user_id=%s",
                (expiry, user_id)
            )
            cur.execute(
                "UPDATE users SET credits=999999999 WHERE user_id=%s",
                (user_id,)
            )

            receipt_id   = generate_receipt_id()
            purchased_on = datetime.now()
            cur.execute(
                "INSERT INTO receipts "
                "(receipt_id,user_id,plan,amount_paid,purchased_on,expires_on) "
                "VALUES (%s,%s,%s,%s,%s,%s)",
                (receipt_id, user_id, plan, plan_info["price"], purchased_on, expiry)
            )
            affected = cur.rowcount
            conn.commit()

        if affected > 0:
            logging.info(f"✅ Activated {plan} for user {user_id}")
            return True
        return False

    except Exception as e:
        logging.error(f"Plan activation error for {user_id}: {e}")
        return False


def get_receipt_for_user(user_id: int, plan: str) -> Optional[Dict[str, Any]]:
    try:
        from database import PooledConn
        from psycopg2.extras import RealDictCursor
        with PooledConn() as conn:
            cur = conn.cursor(cursor_factory=RealDictCursor)
            cur.execute("SELECT first_name FROM users WHERE user_id=%s", (user_id,))
            user_row   = cur.fetchone()
            first_name = (user_row["first_name"] or "User") if user_row else "User"
            if first_name in ("Unknown", "User"):
                first_name = "User"
            user_link = f'<a href="tg://user?id={user_id}">{html.escape(str(first_name))}</a>'

            cur.execute(
                "SELECT receipt_id FROM receipts WHERE user_id=%s AND plan=%s "
                "ORDER BY purchased_on DESC LIMIT 1",
                (user_id, plan)
            )
            receipt_row = cur.fetchone()

        if receipt_row:
            p = PLANS.get(plan, {})
            return {
                "user_link":  user_link,
                "plan_name":  p.get("display", plan),
                "days":       p.get("days", 0),
                "credits":    p.get("credits", 0),
                "receipt_id": receipt_row["receipt_id"],
            }
        return None
    except Exception as e:
        logging.error(f"Receipt fetch error for {user_id}: {e}")
        return None

# ═══════════════════════════════════════════════════════════════════════════════
# PAYMENT CAPTION + KEYBOARD
# ═══════════════════════════════════════════════════════════════════════════════

def format_payment_caption(payment_data: Dict, plan: str, extra: Optional[Dict] = None) -> str:
    p       = PLANS.get(plan, {})
    e       = extra or payment_data or {}
    network = e.get("network") or "Auto-detect on payment page"
    address = e.get("address") or ""
    expire  = int(payment_data.get("expire_min") or PLISIO_EXPIRE_MIN)
    track   = str(payment_data.get("track_id", "N/A"))
    track_ref = address or track

    if address:
        addr_line = f"<b>Aᴅᴅʀᴇss ➵</b> <code>{html.escape(address)}</code>"
    else:
        addr_line = "<b>Aᴅᴅʀᴇss ➵</b> <b>Show In Web Page</b>"

    return (
        f"━━━━━━━━━━━━━━━━\n"
        f"<b>💎 Payment Invoice</b>\n"
        f"━━━━━━━━━━━━━━━━\n"
        f"<b>Plan ➵</b> {p.get('display', plan)}\n"
        f"<b>Price ➵</b> ${p.get('price', 0):.2f}\n"
        f"<b>Network ➵</b> <b>{html.escape(str(network))}</b>\n"
        f"{addr_line}\n"
        f"<b>Expire ➵</b> ⏳ {expire} min\n"
        f"<b>Track ID ➵</b> <code>{html.escape(track)}</code>\n"
        f"━━━━━━━━━━━━━━━━\n"
        #f"<i>💳 Pay the exact amount to the address on the secure page.</i>\n"
        #f"<i>📲 Track this payment anytime with:</i>\n"
        #f"<code>/track {html.escape(track_ref)}</code>\n"
        #f"<i>✅ Auto-verifies — your plan activates instantly.</i>"
    )


# ═══════════════════════════════════════════════════════════════════════════════
# MONITORING
# ═══════════════════════════════════════════════════════════════════════════════

async def start_payment_monitor(track_id: str, chat_id: int, message_id: int,
                                is_photo: bool, original_text: str,
                                payment_data: Optional[Dict] = None,
                                plan: str = None, user_id: int = None):
    if track_id not in active_payments:
        active_payments[track_id] = {}
    ex = active_payments[track_id].get("task")
    if ex and not ex.done():
        ex.cancel()
    existing = active_payments[track_id].get("plan") or plan
    active_payments[track_id].update({
        "chat_id":       chat_id,
        "message_id":    message_id,
        "is_photo":      is_photo,
        "original_text": original_text,
        "payment_data":  payment_data or active_payments[track_id].get("payment_data"),
        "plan":          existing,
        "user_id":       user_id or active_payments[track_id].get("user_id"),
        "meta_sig":      "",
    })
    task = asyncio.create_task(_monitor_payment_loop(track_id))
    active_payments[track_id]["task"] = task


async def _refresh_invoice_caption(track_id: str, meta: Dict[str, str]):
    """Live-update the invoice message once Plisio assigns network + address."""
    data = active_payments.get(track_id)
    if not data or not meta.get("address"):
        return
    from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Oᴘᴇɴ Pᴀʏᴍᴇɴᴛ Pᴀɢᴇ",
                              url=(data.get("payment_data") or {}).get("invoice_url", ""),
                              style="primary")],
        [InlineKeyboardButton(text="Sᴜᴘᴘᴏʀᴛ",
                              url="https://t.me/broken_wiz", style="primary")],
        [InlineKeyboardButton(text="« Bᴀᴄᴋ ᴛᴏ Pʟᴀɴs",
                              callback_data=f"pay_back_plans_{data.get('user_id', 0)}",
                              style="danger")],
    ])
    base = dict(data.get("payment_data") or {})
    base.update({"network": meta.get("network"), "address": meta["address"],
                 "currency": meta.get("currency")})
    caption = format_payment_caption(base, data.get("plan") or "swift")
    await _edit_invoice_msg(get_bot(), data.get("chat_id"), data.get("message_id"),
                            data.get("is_photo", True), caption, kb)


async def _monitor_payment_loop(track_id: str):
    max_checks  = int((PLISIO_EXPIRE_MIN * 60) / PLISIO_POLL_SECONDS) + 10
    check_count = 0
    while check_count < max_checks:
        try:
            status = await asyncio.to_thread(check_payment_status, track_id)
            if status == "Paid":
                logging.info(f"💰 Payment confirmed: {track_id}")
                await _handle_payment_success(track_id)
                return
            elif status == "Expired":
                logging.info(f"⏰ Payment expired: {track_id}")
                await _handle_payment_expired(track_id)
                return

            # Enrich the invoice caption with the live deposit address / network.
            if status == "Pending":
                meta = await asyncio.to_thread(_fetch_operation_meta, track_id)
                if meta.get("address"):
                    current = active_payments.get(track_id, {})
                    sig = f"{meta.get('currency')}|{meta.get('address')}"
                    if current.get("meta_sig") != sig:
                        await asyncio.to_thread(
                            _update_payment_meta_db,
                            track_id, meta.get("currency", ""),
                            meta.get("network", ""), meta["address"],
                        )
                        active_payments[track_id]["meta_sig"] = sig
                        await _refresh_invoice_caption(track_id, meta)

            await asyncio.sleep(PLISIO_POLL_SECONDS)
            check_count += 1
        except asyncio.CancelledError:
            return
        except Exception as e:
            logging.error(f"Monitor error for {track_id}: {e}")
            await asyncio.sleep(PLISIO_POLL_SECONDS)
    await _handle_payment_expired(track_id)


async def _edit_invoice_msg(bot, chat_id, message_id, is_photo, text, kb=None):
    """Edit photo caption or plain text depending on message type."""
    try:
        if is_photo:
            await bot.edit_message_caption(
                chat_id=chat_id, message_id=message_id,
                caption=text, parse_mode="HTML", reply_markup=kb
            )
        else:
            await bot.edit_message_text(
                chat_id=chat_id, message_id=message_id,
                text=text, parse_mode="HTML", reply_markup=kb
            )
    except Exception as e:
        logging.warning(f"[Monitor] Edit failed: {e}")
        try:
            await bot.send_message(chat_id=chat_id, text=text,
                                   parse_mode="HTML", reply_markup=kb)
        except Exception:
            pass


async def _handle_payment_success(track_id: str):
    bot = get_bot()
    if not bot:
        return

    payment    = active_payments.get(track_id, {})
    user_id    = payment.get("user_id")
    plan       = payment.get("plan")
    chat_id    = payment.get("chat_id")
    message_id = payment.get("message_id")
    is_photo   = payment.get("is_photo", True)

    if not user_id or not plan:
        db_payment = await asyncio.to_thread(get_payment_by_track_id, track_id)
        if db_payment:
            user_id = user_id or db_payment.get("user_id")
            plan    = plan    or db_payment.get("plan")

    if not all([user_id, plan]):
        logging.error(f"[Pay] Missing user/plan for track {track_id}")
        return

    db_row = await asyncio.to_thread(get_payment_by_track_id, track_id)
    already_paid = bool(db_row and str(db_row.get("status") or "") == "Paid")
    if already_paid:
        # Another path (restart recovery / /track) already activated this plan.
        _cleanup_payment(track_id, user_id)
        return

    if db_row and not db_row.get("user_id"):
        user_id = user_id or db_row.get("user_id")

    await asyncio.to_thread(_claim_paid, track_id)
    await asyncio.to_thread(activate_plan, user_id, plan)

    # Pull the real Telegram first name so receipts/logs never show "User".
    try:
        chat = await bot.get_chat(user_id)
        real_name = chat.first_name or chat.username
        if real_name:
            await asyncio.to_thread(_save_user_first_name, user_id, real_name)
    except Exception as e:
        logging.warning(f"[Pay] get_chat {user_id}: {e}")

    p            = PLANS.get(plan, {})
    receipt_info = await asyncio.to_thread(get_receipt_for_user, user_id, plan)

    success_text = (
        f"✅ <b>Tʀᴀɴsᴀᴄᴛɪᴏɴ Sᴜᴄᴄᴇᴇᴅᴇᴅ!</b>\n\n"
        f"<b>Pʟᴀɴ ➵</b> {p.get('display', plan)}\n"
        f"<b>Dᴜʀᴀᴛɪᴏɴ ➵</b> {p.get('days', 0)} Dᴀʏs\n"
        f"<b>Cʀᴇᴅɪᴛs ➵</b> ∞\n\n"
        f"<b>Yᴏᴜʀ ᴘʟᴀɴ ʜᴀs ʙᴇᴇɴ ᴀᴄᴛɪᴠᴀᴛᴇᴅ! 🎉</b>"
    )
    if chat_id and message_id:
        await _edit_invoice_msg(bot, chat_id, message_id, is_photo, success_text)

    dm_text = (
        f"🎉 <b>Cᴏɴɢʀᴀᴛᴜʟᴀᴛɪᴏɴs! Aᴄᴄᴇss Aᴄᴛɪᴠᴀᴛᴇᴅ.</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n"
        f"<b>Aᴄᴄᴇss ➵</b> {receipt_info['plan_name'] if receipt_info else p.get('display', plan)}\n"
        f"<b>Dᴜʀᴀᴛɪᴏɴ ➵</b> {p.get('days', 0)} Dᴀʏs\n"
        f"<b>Cʀᴇᴅɪᴛs ➵</b> ∞\n"
    )
    if receipt_info:
        dm_text += (
            f"<b>Rᴇᴄᴇɪᴘᴛ ID ➵</b> <code>{receipt_info['receipt_id']}</code>\n"
            f"━━━━━━━━━━━━━━━━━━━━━━\n"
            f"<i>Please save your Receipt ID.</i>"
        )
    try:
        from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
        kb = InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(text="💬 Sᴜᴘᴘᴏʀᴛ", url="https://t.me/broken_wiz")
        ]])
        await bot.send_message(chat_id=user_id, text=dm_text,
                               parse_mode="HTML", reply_markup=kb)
    except Exception as e:
        logging.error(f"Could not DM user {user_id}: {e}")

    await _send_purchase_log(bot, user_id, plan, receipt_info)

    _cleanup_payment(track_id, user_id)


async def _send_purchase_log(bot, user_id, plan, receipt_info):
    """Post a new-purchase message to the log channel and pin it."""
    try:
        from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
        from live_emoji import plan_badge

        p = PLANS.get(plan, {})
        display = html.escape(str(p.get("display", plan)))
        price   = p.get("price", 0)

        if receipt_info:
            user_line = f"{receipt_info['user_link']} {plan_badge(plan)}"
        else:
            user_line = f'<a href="tg://user?id={user_id}">User</a> {plan_badge(plan)}'

        log_text = (
            f"🎉 <b>Nᴇᴡ Sᴜʙsᴄʀɪᴘᴛɪᴏɴ Pᴜʀᴄʜᴀsᴇᴅ</b>\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"<b>Usᴇʀ ➵</b> {user_line}\n"
            f"<b>Pʟᴀɴ ➵</b> {display}\n"
            f"<b>Pʀɪᴄᴇ ➵</b> ${price}\n"
            f"━━━━━━━━━━━━━━━━━━━━"
        )

        kb = InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(
                text="🛒 Tᴀᴘ ᴛᴏ Bᴜʏ",
                url=f"{BOT_LINK}?start=plan",
                style="primary",
            )
        ]])

        sent = await bot.send_message(
            chat_id=LOG_CHANNEL_ID, text=log_text,
            parse_mode="HTML", reply_markup=kb,
        )
        try:
            await bot.pin_chat_message(LOG_CHANNEL_ID, sent.message_id)
        except Exception as pin_err:
            logging.warning(f"[Pay] Could not pin purchase log: {pin_err}")
        logging.info(f"[Pay] Purchase log posted for user {user_id} ({plan})")
    except Exception as e:
        logging.error(f"[Pay] Purchase log failed for user {user_id}: {e}")


async def _handle_payment_expired(track_id: str):
    bot = get_bot()
    if not bot:
        return
    payment    = active_payments.get(track_id, {})
    chat_id    = payment.get("chat_id")
    message_id = payment.get("message_id")
    is_photo   = payment.get("is_photo", True)
    user_id    = payment.get("user_id")

    await asyncio.to_thread(_update_payment_status_db, track_id, "Expired")
    if chat_id and message_id:
        await _edit_invoice_msg(bot, chat_id, message_id, is_photo,
            "⏰ <b>Pᴀʏᴍᴇɴᴛ Exᴘɪʀᴇᴅ</b>\n\n"
            "The payment window has closed.\n"
            "Please start a new payment."
        )
    _cleanup_payment(track_id, user_id)


async def manual_check_payment(track_id: str) -> str:
    status = await asyncio.to_thread(check_payment_status, track_id)
    if status == "Paid":
        await _handle_payment_success(track_id)
    elif status == "Expired":
        await _handle_payment_expired(track_id)
    return status if status else "Pending"

# ═══════════════════════════════════════════════════════════════════════════════
# SESSION & CLEANUP
# ═══════════════════════════════════════════════════════════════════════════════

def set_user_session(user_id: int, plan: str, currency: str = None):
    user_sessions[user_id] = {"plan": plan, "currency": currency}

def get_user_session(user_id: int) -> Optional[Dict]:
    return user_sessions.get(user_id)

def clear_user_session(user_id: int):
    user_sessions.pop(user_id, None)

def _cleanup_payment(track_id: str, user_id: int = None):
    if track_id in active_payments:
        task = active_payments[track_id].get("task")
        if task and not task.done():
            task.cancel()
        del active_payments[track_id]
    if user_id:
        user_sessions.pop(user_id, None)

def cancel_user_active_payment(user_id: int):
    for track_id, payment in list(active_payments.items()):
        if payment.get("user_id") == user_id:
            task = payment.get("task")
            if task and not task.done():
                task.cancel()
            del active_payments[track_id]
    clear_user_session(user_id)

def register_payment(track_id: str, user_id: int, plan: str):
    active_payments[track_id] = {
        "user_id":    user_id,
        "plan":       plan,
        "created_at": datetime.now(),
        "status":     "Pending",
    }

# ═══════════════════════════════════════════════════════════════════════════════
# KEYBOARD BUILDERS
# ═══════════════════════════════════════════════════════════════════════════════

def get_plan_selection_keyboard():
    from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
    rows  = []
    for key, p in PLANS.items():
        rows.append([InlineKeyboardButton(
            text=f"{p['display']} ~ ${p['price']}",
            callback_data=f"pay_plan_{key}",
            style="primary",
        )])
    rows.append([InlineKeyboardButton(text="« Bᴀᴄᴋ", callback_data="back_main", style="danger")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def get_paid_button_keyboard(track_id: str, user_id: int, invoice_url: str):
    from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Oᴘᴇɴ Pᴀʏᴍᴇɴᴛ Pᴀɢᴇ", url=invoice_url, style="primary")],
        [InlineKeyboardButton(text="Sᴜᴘᴘᴏʀᴛ", url="https://t.me/broken_wiz", style="primary")],
        [InlineKeyboardButton(text="« Bᴀᴄᴋ ᴛᴏ Pʟᴀɴs", callback_data=f"pay_back_plans_{user_id}", style="danger")],
    ])


# ═══════════════════════════════════════════════════════════════════════════════
# TRACK A PAYMENT  (/track <track_id | invoice_url>)
# ═══════════════════════════════════════════════════════════════════════════════

PLISIO_CURRENCY_NETWORKS = {
    "BTC": "Bitcoin",
    "BCH": "Bitcoin Cash",
    "ETH": "Ethereum",
    "ETC": "Ethereum Classic",
    "LTC": "Litecoin",
    "DOGE": "Dogecoin",
    "DASH": "Dash",
    "ZEC": "Zcash",
    "TRX": "TRON (TRC20)",
    "USDT": "Tether (USDT)",
    "USDT_BSC": "Binance Smart Chain (BEP20)",
    "USDT_BTC": "Omni (Bitcoin)",
    "USDT_ERC20": "Ethereum (ERC20)",
    "USDT_BEP20": "Binance Smart Chain (BEP20)",
    "USDT_TRC20": "TRON (TRC20)",
    "USDT_AVAX": "Avalanche (C-Chain)",
    "USDT_POLYGON": "Polygon",
    "DAI_ERC20": "Ethereum (ERC20)",
}


def _get_user_name(user_id) -> str:
    try:
        from database import PooledConn
        from psycopg2.extras import RealDictCursor
        with PooledConn() as conn:
            cur = conn.cursor(cursor_factory=RealDictCursor)
            cur.execute("SELECT first_name, username FROM users WHERE user_id=%s", (user_id,))
            row = cur.fetchone()
            if row:
                name = str(row.get("first_name") or "").strip()
                if name and name.lower() not in ("unknown", "user"):
                    return name
                name = str(row.get("username") or "").strip().lstrip("@")
                if name and name.lower() != "unknown":
                    return name
    except Exception as e:
        logging.error(f"[PayDB] get_user_name {user_id}: {e}")
    return "User"


def _save_user_first_name(user_id, name):
    """Persist the real Telegram first name (users table often has NULL)."""
    try:
        from database import PooledConn
        name = str(name or "").strip()[:64]
        if not name:
            return
        with PooledConn() as conn:
            cur = conn.cursor()
            cur.execute("UPDATE users SET first_name=%s WHERE user_id=%s",
                        (name, user_id))
            conn.commit()
    except Exception as e:
        logging.error(f"[PayDB] save first_name {user_id}: {e}")


def _track_dt(dt, default="—"):
    if not dt:
        return default
    try:
        h = int(dt.strftime("%I"))
        return f"{dt.strftime('%d/%m/%y')} ( {h}{dt.strftime(':%M %p')} )"
    except Exception:
        return str(dt)


def track_payment_info(ref: str) -> Optional[Dict]:
    """Look up a payment (+ Plisio live check) and return display data.
    If Plisio confirms the money arrived, the plan is activated right here —
    this is the recovery path for invoices that were marked Expired early."""
    ref = (ref or "").strip()
    if not ref:
        return None

    row = get_payment_by_track_id(ref) or get_payment_by_address(ref)
    if not row:
        return None

    status        = row.get("status") or "Pending"
    prev_status   = status
    paid_raw      = None
    paid_received = None
    currency_slug = ""
    address       = row.get("address") or row.get("invoice_url") or row["track_id"]

    try:
        status = check_payment_status(row["track_id"])
    except Exception as e:
        logging.error(f"[Plisio] track live check {row['track_id']}: {e}")
        status = prev_status

    try:
        live = _plisio_get(f"operations/{row['track_id']}")
    except Exception:
        live = None
    if live and live.get("status") == "success":
        d = live.get("data") or {}
        if d.get("address"):
            address = d["address"]
        if status == "Paid":
            paid_raw      = d.get("paid_sum") or d.get("sum") or d.get("amount")
            currency_slug = d.get("currency") or d.get("psys_cid") or ""
        elif d.get("psys_cid") or d.get("currency"):
            currency_slug = d.get("currency") or d.get("psys_cid") or ""

    if status == "Paid" and prev_status != "Paid":
        inv = _fetch_invoice_detail(row["track_id"])
        paid_received = inv.get("received_amount")
        if inv.get("currency") and not currency_slug:
            currency_slug = inv.get("currency")
        if _claim_paid(row["track_id"]):
            user_id = row.get("user_id")
            plan    = row.get("plan")
            if user_id and plan:
                activate_plan(int(user_id), str(plan))
                row["paid_at"] = datetime.now()
            status = "Paid"

    return {
        "track_id":  row["track_id"],
        "user_id":   row.get("user_id"),
        "status":    status,
        "price_usd": float(row.get("price_usd") or 0),
        "paid_raw":  paid_received or paid_raw,
        "currency":  currency_slug,
        "network":   PLISIO_CURRENCY_NETWORKS.get(currency_slug, currency_slug or "Plisio"),
        "order_for": _get_user_name(row.get("user_id")),
        "address":   address,
        "created_at": row.get("created_at"),
        "paid_at":    row.get("paid_at"),
    }


def format_track_caption(info: Dict) -> str:
    status   = info["status"]
    icon     = {"Paid": "💎", "Expired": "⏰"}.get(status, "⏳")
    paid_usd = info.get("price_usd") or 0

    if status == "Paid" and info.get("paid_raw"):
        paid_line = f"{info['paid_raw']} {info.get('currency') or ''}".strip()
    elif status == "Paid":
        paid_line = f"${paid_usd:.2f} USD"
    else:
        paid_line = "—"

    name = html.escape(str(info.get("order_for") or "User"))
    if info.get("user_id"):
        order_line = f'<a href="tg://user?id={int(info["user_id"])}">{name}</a>'
    else:
        order_line = name

    return (
        "💎 <b>Pᴀʏᴍᴇɴᴛ Tʀᴀᴄᴋ</b>\n"
        "────────────\n"
        f"<b>Sᴛᴀᴛᴜs ➵</b> {icon} <b>{status}</b>\n"
        f"<b>Tʀᴀᴄᴋ ID ➵</b> <code>{info['track_id']}</code>\n"
        f"<b>Oʀᴅᴇʀ Fᴏʀ ➵</b> {order_line}\n"
        "────────────\n"
        f"<b>Aᴍᴏᴜɴᴛ ➵</b> ${paid_usd:.2f} USD\n"
        f"<b>Pᴀɪᴅ ➵</b> {paid_line}\n"
        f"<b>Nᴇᴛᴡᴏʀᴋ ➵</b> {info.get('network') or '—'}\n"
        f"<b>Aᴅᴅʀᴇss ➵</b> <code>{info.get('address') or '—'}</code>\n"
        "────────────\n"
        f"<b>Cʀᴇᴀᴛᴇᴅ ➵</b> {_track_dt(info.get('created_at'))}\n"
        f"<b>Pᴀɪᴅ ᴏɴ ➵</b> {_track_dt(info.get('paid_at'), '—') if status == 'Paid' else '—'}"
    )


def scan_recoverable_payments(limit: int = 50):
    """Startup scan (thread-safe, blocking): recent Pending/Expired invoices.
    Returns [(track_id, live_status, user_id, plan), …] so the async caller can
    re-arm monitors or push settled payments through the success flow."""
    try:
        from database import PooledConn
        from psycopg2.extras import RealDictCursor
        with PooledConn() as conn:
            cur = conn.cursor(cursor_factory=RealDictCursor)
            cur.execute(
                "SELECT track_id, user_id, plan, status FROM payment_tracks "
                "WHERE status IN ('Pending','Expired') "
                "AND created_at > NOW() - INTERVAL '24 hours' "
                "ORDER BY created_at DESC LIMIT %s",
                (limit,),
            )
            rows = [dict(r) for r in cur.fetchall()]
    except Exception as e:
        logging.error(f"[Pay] resume query failed: {e}")
        return []

    results = []
    for row in rows:
        track_id = row.get("track_id")
        if not track_id or track_id in active_payments:
            continue
        try:
            live_status = check_payment_status(track_id)
        except Exception as e:
            logging.error(f"[Pay] resume check {track_id}: {e}")
            continue
        if live_status in ("Paid", "Pending"):
            results.append((track_id, live_status, row.get("user_id"), row.get("plan")))
    return results


async def resume_payments():
    """Re-arm monitors and recover any invoice Plisio already settled."""
    results = await asyncio.to_thread(scan_recoverable_payments)
    for track_id, live_status, user_id, plan in results:
        try:
            if live_status == "Paid":
                asyncio.create_task(_handle_payment_success(track_id))
                logging.info(f"[Pay] Recovering payment {track_id}")
            else:
                active_payments[track_id] = {
                    "user_id": user_id,
                    "plan":    plan,
                    "status":  "Pending",
                }
                asyncio.create_task(_monitor_payment_loop(track_id))
                logging.info(f"[Pay] Resumed monitor for {track_id}")
        except Exception as e:
            logging.error(f"[Pay] resume {track_id}: {e}")


# ═════════════════════════════════════════════════════════════════════════════
# MAINTENANCE DOWNTIME COMPENSATION — auto-extend paid plans + DM notice
# ═════════════════════════════════════════════════════════════════════════════
#
# A heartbeat row (bot_state.last_seen) is refreshed every 60 s while the bot
# runs. On boot, downtime = now − last heartbeat. When the bot was offline for
# a full day or more, every still-active paid plan is pushed forward by that
# many whole days and the owner receives the "Plan Extended" DM.
# Short restarts (< 1 day) are ignored entirely — no extension, no message.
# ═════════════════════════════════════════════════════════════════════════════

HEARTBEAT_KEY         = "last_seen"
HEARTBEAT_INTERVAL    = 60      # seconds between heartbeats
COMPENSATE_MIN_DAYS   = 1       # only act when downtime >= 1 whole day
COMPENSATE_MAX_DAYS   = 30      # safety cap (stale-clock protection)


def _init_state_db():
    try:
        from database import PooledConn
        with PooledConn() as conn:
            cur = conn.cursor()
            cur.execute("""
                CREATE TABLE IF NOT EXISTS bot_state (
                    key        TEXT PRIMARY KEY,
                    value      TEXT NOT NULL,
                    updated_at TIMESTAMP DEFAULT NOW()
                )
            """)
            conn.commit()
    except Exception as e:
        logging.error(f"[Maint] state db init error: {e}")

try:
    _init_state_db()
except Exception:
    pass


def _parse_ts(value) -> Optional[datetime]:
    if not value:
        return None
    for fmt in ("%Y-%m-%dT%H:%M:%S.%f", "%Y-%m-%dT%H:%M:%S"):
        try:
            return datetime.strptime(str(value), fmt)
        except Exception:
            continue
    return None


def _claim_downtime() -> Optional[timedelta]:
    """Read the previous heartbeat and stamp 'now' in the same breath.
    Returns the downtime (last run → this run), or None on first boot."""
    now = datetime.now()
    try:
        from database import PooledConn
        with PooledConn() as conn:
            cur = conn.cursor()
            cur.execute("SELECT value FROM bot_state WHERE key=%s", (HEARTBEAT_KEY,))
            row = cur.fetchone()
            if row:
                cur.execute(
                    "UPDATE bot_state SET value=%s, updated_at=NOW() WHERE key=%s",
                    (now.isoformat(), HEARTBEAT_KEY),
                )
                conn.commit()
                prev = _parse_ts(row[0])
                if prev is None:
                    return None
                delta = now - prev
                return delta if delta.total_seconds() > 0 else None
            # First boot with this feature: start the clock, compensate nothing.
            cur.execute(
                "INSERT INTO bot_state (key, value, updated_at) VALUES (%s,%s,NOW())",
                (HEARTBEAT_KEY, now.isoformat()),
            )
            conn.commit()
            return None
    except Exception as e:
        logging.error(f"[Maint] claim downtime error: {e}")
        return None


def _write_last_seen(ts: Optional[datetime] = None):
    ts = ts or datetime.now()
    try:
        from database import PooledConn
        with PooledConn() as conn:
            cur = conn.cursor()
            cur.execute(
                "INSERT INTO bot_state (key, value, updated_at) VALUES (%s,%s,NOW()) "
                "ON CONFLICT (key) DO UPDATE SET value=EXCLUDED.value, updated_at=NOW()",
                (HEARTBEAT_KEY, ts.isoformat()),
            )
            conn.commit()
    except Exception as e:
        logging.error(f"[Maint] heartbeat write error: {e}")


def _extend_active_premium(days: int):
    """Push every still-active premium_expiry forward by `days`.
    Returns [(user_id, new_expiry), …] for users actually extended."""
    delta      = timedelta(days=days)
    extended   = []
    try:
        from database import PooledConn
        from psycopg2.extras import RealDictCursor
        with PooledConn() as conn:
            cur = conn.cursor(cursor_factory=RealDictCursor)
            cur.execute(
                "SELECT user_id, premium_expiry FROM users "
                "WHERE is_premium=1 AND premium_expiry > NOW()"
            )
            rows = cur.fetchall()
            for row in rows:
                new_expiry = row["premium_expiry"] + delta
                cur.execute(
                    "UPDATE users SET premium_expiry=%s "
                    "WHERE user_id=%s AND premium_expiry=%s",
                    (new_expiry, row["user_id"], row["premium_expiry"]),
                )
                if cur.rowcount:
                    extended.append((int(row["user_id"]), new_expiry))
            conn.commit()
    except Exception as e:
        logging.error(f"[Maint] extend premium error: {e}")
        return []
    try:
        from sub import _premium_cache
        for user_id, _ in extended:
            _premium_cache.pop(user_id, None)
    except Exception:
        pass
    return extended


async def apply_maintenance_compensation(bot):
    """Auto-compensation: offline >= 1 whole day → extend every still-active
    paid plan by that many days and DM the user the 'Plan Extended' notice."""
    downtime = await asyncio.to_thread(_claim_downtime)
    if downtime is None:
        return

    hours = downtime.total_seconds() / 3600
    days  = int(downtime.total_seconds() // 86400)

    if days < COMPENSATE_MIN_DAYS:
        logging.info(f"[Maint] Downtime {hours:.1f}h < {COMPENSATE_MIN_DAYS}d — no compensation.")
        return

    days     = min(days, COMPENSATE_MAX_DAYS)
    extended = await asyncio.to_thread(_extend_active_premium, days)
    logging.info(f"[Maint] Downtime {hours:.1f}h → extended {len(extended)} plan(s) by {days} day(s).")

    if not extended:
        return

    try:
        from live_emoji import dev_badge
        dev_link = dev_badge()
    except Exception:
        dev_link = '<a href="https://t.me/broken_wiz">𒉼 𝔦 乙</a>'

    day_word = "Day" if days == 1 else "Days"
    for user_id, new_expiry in extended:
        text = (
            f"<b>[⌭] Plan Extended 🎁</b>\n"
            f"━━━━━━━━━━━\n"
            f"Your plan has been extended for <b>{days} {day_word}</b> due to maintenance downtime.\n"
            f"⏱ New Expiry : <b>{new_expiry.strftime('%d %b %Y, %H:%M')} UTC</b>\n"
            f"✨ We hope you love our bot!\n"
            f"━━━━━━━━━━━\n"
            f"Dev ➵ {dev_link}"
        )
        try:
            await bot.send_message(chat_id=user_id, text=text, parse_mode="HTML")
        except Exception as e:
            logging.warning(f"[Maint] Could not DM compensation notice to {user_id}: {e}")
        await asyncio.sleep(0.05)   # gentle on Telegram rate limits


async def _maintenance_heartbeat():
    """Keep the last_seen clock fresh so downtime is measured accurately."""
    while True:
        try:
            await asyncio.to_thread(_write_last_seen, datetime.now())
        except Exception as e:
            logging.error(f"[Maint] heartbeat loop error: {e}")
        await asyncio.sleep(HEARTBEAT_INTERVAL)
