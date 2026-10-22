# ═══════════════════════════════════════════════════════════════════════════════
# payments.py - OxaPay Crypto Payment Gateway (Fully Automated Premium Edition)
# ═══════════════════════════════════════════════════════════════════════════════

import requests
import json
import asyncio
import logging
import random
import string
from typing import Optional, Dict, Any
from datetime import datetime, timedelta

# ═══════════════════════════════════════════════════════════════════════════════
# OXAPAY CONFIGURATION
# ═══════════════════════════════════════════════════════════════════════════════

API_KEY = "NLQIPG-8SOFHX-VPRQZ5-MQA7H9"
CALLBACK_URL = "https://cxchk.site/payment_callback"
API_BASE = "https://api.oxapay.com/v1"

# ═══════════════════════════════════════════════════════════════════════════════
# DIRECT NETWORK MAPPING (The only 7 allowed options)
# ═══════════════════════════════════════════════════════════════════════════════

DIRECT_NETWORKS: Dict[str, Dict[str, str]] = {
    "BEP20": {"currency": "USDT", "network": "BSC"},
    "TRC20": {"currency": "USDT", "network": "TRC20"},
    "LTC": {"currency": "LTC", "network": "Litecoin"},
    "BTC": {"currency": "BTC", "network": "Bitcoin"},
    "SOL": {"currency": "SOL", "network": "Solana"},
    "POL": {"currency": "POL", "network": "Polygon"},
    "TON": {"currency": "TON", "network": "TON"}
}

# ═══════════════════════════════════════════════════════════════════════════════
# PLAN CONFIGURATION
# ═══════════════════════════════════════════════════════════════════════════════

PLANS: Dict[str, Dict[str, Any]] = {
    "ULTRA":     {"price": 10, "days": 7,  "credits": 13000, "display": "ULTRA"},
    "SUPER":     {"price": 15, "days": 15, "credits": 23000, "display": "SUPER"},
    "ULTIMATE":  {"price": 30, "days": 30, "credits": 53000, "display": "ULTIMATE"}
}

# ═══════════════════════════════════════════════════════════════════════════════
# UNICODE BOLD MATH SANS MAPPER (Fixed Lengths)
# ═══════════════════════════════════════════════════════════════════════════════

def to_premium_bold(text: str) -> str:
    """Converts standard text to Unicode Bold Math Sans-Serif"""
    normal = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789$"
    bold   = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789$"
    return text.translate(str.maketrans(normal, bold))

# ═══════════════════════════════════════════════════════════════════════════════
# PAYMENT TRACKING (In-Memory)
# ═══════════════════════════════════════════════════════════════════════════════

active_payments: Dict[str, Dict[str, Any]] = {}
user_sessions: Dict[int, Dict[str, str]] = {}

_bot = None

def set_bot(bot):
    global _bot
    _bot = bot

def get_bot():
    return _bot

# ═══════════════════════════════════════════════════════════════════════════════
# PAYMENT CREATION & STATUS
# ═══════════════════════════════════════════════════════════════════════════════

def create_payment(user_id: int, plan: str, currency: str, network: str) -> Optional[Dict]:
    if plan not in PLANS: return None
    
    plan_info = PLANS[plan]
    url = f"{API_BASE}/payment/white-label"
    headers = {
        "merchant_api_key": API_KEY,
        "Content-Type": "application/json",
        "User-Agent": "Mozilla/5.0"
    }
    order_id = f"{user_id}_{plan}_{int(datetime.now().timestamp())}"
    payload = {
        "amount": plan_info["price"], "currency": "USD", "pay_currency": currency,
        "network": network, "lifetime": 30, "fee_paid_by_payer": 0,
        "under_paid_coverage": 2, "to_currency": "USDT", "order_id": order_id,
        "description": f"{plan} Plan Activation - User {user_id}", "callback_url": CALLBACK_URL
    }
    
    try:
        r = requests.post(url, data=json.dumps(payload), headers=headers, timeout=30)
        res = r.json()
        if res.get("status") == 200:
            payment_data = res["data"]
            return {
                "track_id": payment_data["track_id"], "address": payment_data["address"],
                "amount": payment_data["pay_amount"], "currency": payment_data["pay_currency"],
                "network": payment_data["network"], "qr": payment_data["qr_code"],
                "expires": payment_data["expired_at"], "order_id": order_id
            }
        else:
            logging.error(f"OxaPay API Error: {res}")
            return None
    except Exception as e:
        logging.error(f"Payment creation error: {e}")
        return None

def check_payment_status(track_id: str) -> Optional[str]:
    url = f"{API_BASE}/payment/{track_id}"
    headers = {"merchant_api_key": API_KEY, "Content-Type": "application/json", "User-Agent": "Mozilla/5.0"}
    try:
        r = requests.get(url, headers=headers, timeout=15)
        res = r.json()
        status = res.get("data", {}).get("status")
        if track_id in active_payments:
            active_payments[track_id]["status"] = status
        return status
    except Exception as e:
        logging.error(f"Status check error for {track_id}: {e}")
        return None

# ═══════════════════════════════════════════════════════════════════════════════
# PLAN ACTIVATION
# ═══════════════════════════════════════════════════════════════════════════════
def generate_receipt_id():
    """Generates a Receipt ID like BLC-054879-PLR"""
    random_str = ''.join(random.choices(string.digits, k=6))
    return f"BLC-{random_str}-PLR"

def activate_plan(user_id: int, plan: str) -> bool:
    if plan not in PLANS: return False
    plan_info = PLANS[plan]
    try:
        from database import get_collection
        users = get_collection("users")
        receipts = get_collection("receipts")
        expiry = datetime.now() + timedelta(days=plan_info["days"])

        # 1. ENSURE USER EXISTS
        users.update_one(
            {"user_id": user_id},
            {"$setOnInsert": {"user_id": user_id, "username": "Unknown", "first_name": "User", "credits": 0, "joined_at": datetime.now()}},
            upsert=True
        )

        # 2. Calculate correct expiry date (stacking if already premium)
        doc = users.find_one({"user_id": user_id}, {"premium_expiry": 1})
        if doc and doc.get("premium_expiry"):
            current_expiry = doc["premium_expiry"]
            if current_expiry and datetime.now() < current_expiry:
                expiry = current_expiry + timedelta(days=plan_info["days"])

        # 3. Update Premium
        users.update_one(
            {"user_id": user_id},
            {"$set": {"is_premium": 1, "premium_expiry": expiry}}
        )
        # Drop cached premium status so the user is recognised as premium
        # immediately on their next command — without this the 60s cache
        # keeps returning the stale (False, None) value.
        try:
            from database import _premium_cache
            _premium_cache.pop(user_id, None)
        except Exception:
            pass

        # 4. Add Plan Credits
        users.update_one({"user_id": user_id}, {"$inc": {"credits": plan_info["credits"]}})

        # 5. Generate and Store Receipt
        receipt_id = generate_receipt_id()
        purchased_on = datetime.now()
        receipts.insert_one({
            "receipt_id": receipt_id,
            "user_id": user_id,
            "plan": plan,
            "amount_paid": plan_info["price"],
            "purchased_on": purchased_on,
            "expires_on": expiry
        })

        logging.info(f"✅ Activated {plan} for user {user_id} (+{plan_info['credits']} credits)")
        return True
    except Exception as e:
        logging.error(f"Plan activation error for {user_id}: {e}")
        return False

# ═══════════════════════════════════════════════════════════════════════════════
# GET RECEIPT INFO FOR CONGRATULATIONS MESSAGE
# ═══════════════════════════════════════════════════════════════════════════════

def get_receipt_for_user(user_id: int, plan: str) -> Optional[Dict[str, Any]]:
    """Fetches receipt details for the congratulations message."""
    try:
        from database import get_collection
        users = get_collection("users")
        receipts = get_collection("receipts")

        # Get user info
        u = users.find_one({"user_id": user_id}, {"first_name": 1})
        first_name = (u.get("first_name") or "User") if u else "User"
        if first_name in ["Unknown", "User", ""]:
            first_name = "User"

        user_link = f'<a href="tg://user?id={user_id}">{first_name}</a>'

        # Get latest receipt for this plan
        r = receipts.find_one(
            {"user_id": user_id, "plan": plan},
            sort=[("purchased_on", -1)]
        )

        if r:
            plan_info = PLANS.get(plan, {})
            plan_display = plan_info.get('display', plan)
            return {
                "user_link": user_link,
                "plan_name": plan_display,
                "days": plan_info.get('days', 0),
                "credits": plan_info.get('credits', 0),
                "receipt_id": r["receipt_id"]
            }
        return None
    except Exception as e:
        logging.error(f"Error getting receipt for user {user_id}: {e}")
        return None

# ═══════════════════════════════════════════════════════════════════════════════
# PREMIUM TEXT FORMATTERS (Exact UI Match)
# ═══════════════════════════════════════════════════════════════════════════════

def format_payment_caption(payment_data: Dict, plan: str) -> str:
    plan_info = PLANS.get(plan, {})
    
    try:
        expires_dt = datetime.fromisoformat(payment_data["expires"].replace("Z", "+00:00"))
        diff = expires_dt - datetime.now(expires_dt.tzinfo)
        minutes = int(diff.total_seconds() / 60)
    except:
        minutes = 30

    plan_txt = to_premium_bold(f"Plan ➛ {plan_info.get('display', plan)}")
    price_txt = to_premium_bold(f"Price ➛ ${plan_info.get('price', 0):.2f} USD")
    pay_txt = to_premium_bold(f"Pay ➛ {payment_data['amount']} {payment_data['currency']}")
    net_txt = to_premium_bold(f"Network ➛ {payment_data['network']}")
    dep_txt = to_premium_bold("Deposit Address ➛")
    exp_txt = to_premium_bold(f"Expires in ➛ {minutes} minutes")
    confirm_txt = to_premium_bold("Deposits take 3 mins to confirm after completed")
    
    return (
        f"{plan_txt}\n"
        f"{price_txt}\n"
        f"{pay_txt}\n"
        f"{net_txt}\n\n"
        f"{dep_txt}\n"
        f"<code>{payment_data['address']}</code>\n\n"
        f"{exp_txt}\n"
        f"{confirm_txt}"
    )

# ═══════════════════════════════════════════════════════════════════════════════
# AUTOMATIC MONITORING LOGIC (Runs silently)
# ═══════════════════════════════════════════════════════════════════════════════

async def start_payment_monitor(track_id: str, chat_id: int, message_id: int, is_photo: bool, original_text: str):
    if track_id in active_payments:
        existing = active_payments[track_id].get("task")
        if existing and not existing.done(): existing.cancel()
    
    active_payments[track_id].update({"chat_id": chat_id, "message_id": message_id, "is_photo": is_photo, "original_text": original_text})
    task = asyncio.create_task(_monitor_payment_loop(track_id))
    active_payments[track_id]["task"] = task

async def _monitor_payment_loop(track_id: str):
    max_checks = 360
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
            await asyncio.sleep(5)
            check_count += 10
        except asyncio.CancelledError:
            return
        except Exception as e:
            logging.error(f"Monitor error for {track_id}: {e}")
            await asyncio.sleep(5)

async def _handle_payment_success(track_id: str):
    bot = get_bot()
    if not bot: return
    
    payment = active_payments.get(track_id, {})
    user_id = payment.get("user_id")
    plan = payment.get("plan")
    chat_id = payment.get("chat_id")
    message_id = payment.get("message_id")
    
    if not all([user_id, plan, chat_id, message_id]): return
    
    success = await asyncio.to_thread(activate_plan, user_id, plan)
    plan_info = PLANS.get(plan, {})
    
    # Get receipt info for congratulations message
    receipt_info = get_receipt_for_user(user_id, plan)
    
    if receipt_info:
        dm_text = (
            f"Congratulations!<tg-emoji emoji-id='5310296284874159738'>🎉</tg-emoji> your access has been activated.\n"
            f"User ➛ {receipt_info['user_link']}\n"
            f"Access ➛ <b>{receipt_info['plan_name']}</b>\n"
            f"Duration ➛ {receipt_info['days']} Days\n"
            f"Credits Added ➛ +{receipt_info['credits']:,}\n"
            f"Receipt ID ➛ <code>{receipt_info['receipt_id']}</code>\n"
            f"please save this receipt ID."
        )
    else:
        dm_text = (
            f"Congratulations!<tg-emoji emoji-id='5310296284874159738'>🎉</tg-emoji> your access has been activated.\n"
            f"Access ➛ <b>{plan_info.get('display', plan)}</b>\n"
            f"Duration ➛ {plan_info.get('days', 0)} Days\n"
            f"Credits Added ➛ +{plan_info.get('credits', 0):,}\n"
            f"Your plan has been activated!"
        )
    
    # SUCCESS EDIT TEXT (for the payment chat)
    success_text = (
        f"<tg-emoji emoji-id='5310296284874159738'>✅</tg-emoji> <b>Transaction Succeeded!</b>\n\n"
        f" <b>Plan ➛</b> {plan_info.get('display', plan)}\n"
        f" <b>Duration ➛</b> {plan_info.get('days', 0)} Days\n"
        f" <b>Credits Added ➛</b> +{plan_info.get('credits', 0):,}\n\n"
        f" <b>Your plan has been activated!</b>"
    )
    
    try:
        await bot.edit_message_text(chat_id=chat_id, message_id=message_id, text=success_text)
    except Exception as e:
        logging.error(f"Error editing success message: {e}")
        try:
            await bot.send_message(chat_id=chat_id, text=success_text)
        except: pass
    
    # SEND DM TO USER (congratulations message)
    try:
        from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="Support", url="https://t.me/ShopifyxoBot")]
        ])
        await bot.send_message(
            chat_id=user_id,
            text=dm_text,
            parse_mode="HTML",
            reply_markup=keyboard
        )
        logging.info(f"📧 Sent congratulations DM to user {user_id}")
    except Exception as e:
        logging.error(f"Could not send DM to user {user_id}: {e}")
    
    _cleanup_payment(track_id, user_id)

async def _handle_payment_expired(track_id: str):
    bot = get_bot()
    if not bot: return
    payment = active_payments.get(track_id, {})
    chat_id = payment.get("chat_id")
    message_id = payment.get("message_id")
    user_id = payment.get("user_id")
    
    expired_text = "<b>Payment Expired</b>\n\nThe payment window has closed.\nPlease start a new payment."
    try:
        await bot.edit_message_text(chat_id=chat_id, message_id=message_id, text=expired_text)
    except: pass
    
    _cleanup_payment(track_id, user_id)

async def manual_check_payment(track_id: str) -> str:
    """Returns status string silently without touching the chat message."""
    status = await asyncio.to_thread(check_payment_status, track_id)
    if status == "Paid":
        await _handle_payment_success(track_id)
    elif status == "Expired":
        await _handle_payment_expired(track_id)
    return status if status else "Pending"

# ═══════════════════════════════════════════════════════════════════════════════
# SESSION & CLEANUP MANAGEMENT
# ═══════════════════════════════════════════════════════════════════════════════

def set_user_session(user_id: int, plan: str, currency: str = None):
    user_sessions[user_id] = {"plan": plan, "currency": currency}

def get_user_session(user_id: int) -> Optional[Dict]:
    return user_sessions.get(user_id)

def clear_user_session(user_id: int):
    if user_id in user_sessions: del user_sessions[user_id]

def _cleanup_payment(track_id: str, user_id: int = None):
    if track_id in active_payments:
        task = active_payments[track_id].get("task")
        if task and not task.done(): task.cancel()
        del active_payments[track_id]
    if user_id and user_id in user_sessions: del user_sessions[user_id]

def cancel_user_active_payment(user_id: int):
    for track_id, payment in list(active_payments.items()):
        if payment.get("user_id") == user_id:
            task = payment.get("task")
            if task and not task.done(): task.cancel()
            del active_payments[track_id]
    clear_user_session(user_id)

def register_payment(track_id: str, user_id: int, plan: str):
    active_payments[track_id] = {"user_id": user_id, "plan": plan, "created_at": datetime.now(), "status": "Pending"}

# ═══════════════════════════════════════════════════════════════════════════════
# KEYBOARD BUILDERS (No emojis, no bold tags inside buttons)
# ═══════════════════════════════════════════════════════════════════════════════

def get_plan_selection_keyboard():
    from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text='ULTRA — $10', callback_data="pay_plan_ULTRA")],
        [InlineKeyboardButton(text='SUPER — $15', callback_data="pay_plan_SUPER")],
        [InlineKeyboardButton(text='ULTIMATE — $30', callback_data="pay_plan_ULTIMATE")],
        [InlineKeyboardButton(text="« Back", callback_data="menu_pricing")]
    ])

def get_network_selection_keyboard(user_id: int):
    from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="USDT (BEP20)", callback_data="pay_direct_BEP20"), InlineKeyboardButton(text="USDT (TRC20)", callback_data="pay_direct_TRC20")],
        [InlineKeyboardButton(text="LITECOIN", callback_data="pay_direct_LTC"), InlineKeyboardButton(text="BITCOIN", callback_data="pay_direct_BTC")],
        [InlineKeyboardButton(text="SOLANA", callback_data="pay_direct_SOL"), InlineKeyboardButton(text="POLYGON", callback_data="pay_direct_POL")],
        [InlineKeyboardButton(text="TON", callback_data="pay_direct_TON")],
        [InlineKeyboardButton(text="« Back", callback_data=f"pay_back_plans_{user_id}")]
    ])

def get_paid_button_keyboard(track_id: str, user_id: int):
    from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text='Paid ✅', callback_data=f"pay_check_{track_id}")],
        [InlineKeyboardButton(text="« Back", callback_data=f"pay_back_plans_{user_id}")]
    ])
