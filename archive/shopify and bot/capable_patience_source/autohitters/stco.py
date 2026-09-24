import subprocess
import json
import logging
import asyncio
import time
import html
import re
from typing import List, Dict, Optional, Any

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# AIogram Imports
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
from aiogram import Router, F, types, Bot
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.exceptions import TelegramBadRequest

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# LOCAL IMPORTS (DATABASE)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
from database import get_user_credits, update_credits, create_user

# Initialize Router
router = Router()

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# CONFIGURATION
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

JS_SCRIPT_PATH = "autohitters/stco.js"
MAX_CARDS = 50             # Max cards allowed per command
PROXY_ENABLED = 'y'        # 'y' or 'n' passed to Node script
PARALLEL_LIMIT = 1         # Number of parallel node processes
UPDATE_EVERY = 1           # Update UI every X cards processed
RESULTS_PER_PAGE = 4       # Cards per page in UI
HIT_CHANNEL_ID = -1004453592223  # Channel ID for Hit Detect

# Global State for Pagination (In-Memory)
STCO_SESSIONS: Dict[int, Dict[str, Any]] = {}

# Logging setup
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# ASYNC HELPERS
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

async def run_subprocess(command: List[str]) -> Optional[Dict[str, Any]]:
    """Runs blocking subprocess in a thread to keep bot responsive."""
    loop = asyncio.get_running_loop()
    try:
        process = await loop.run_in_executor(
            None,
            lambda: subprocess.run(
                command,
                capture_output=True,
                text=True,
                timeout=120
            )
        )

        if process.returncode != 0:
            logger.error(f"Script Error: {process.stderr}")
            return None

        try:
            data = json.loads(process.stdout)
            if isinstance(data, list) and len(data) > 0:
                return data[0]
            return None
        except json.JSONDecodeError:
            logger.error("Failed to decode JSON from script.")
            return None

    except subprocess.TimeoutExpired:
        return None
    except Exception as e:
        logger.error(f"Subprocess exception: {e}")
        return None

async def send_hit_message(bot: Bot, resp_code: str, amount: str, user_name: str, user_id: int):
    """Sends the Hit Detect message to the channel."""
    try:
        user_link = f"<a href='tg://user?id={user_id}'>{html.escape(user_name)}</a>"
        dev_link = '<a href="https://t.me/Enchanted_linux_0x">Enchanted_linux_0x</a>'

        hit_msg = (
            f"<b>𝗛𝗶𝘁 𝗗𝗲𝘁𝗲𝗰𝘁𝗲𝗱 ➠</b> <b>𝗖𝗼𝗺𝗽𝗹𝗲𝘁𝗲𝗱 ✅</b>\n"
            f"<b>𝗚𝗮𝘁𝗲𝘄𝗮𝘆 ➠</b> <b>StripeAutoHitX</b>\n"
            f"<b>𝗥𝗲𝘀𝗽𝗼𝗻𝘀𝗲 ➠</b> <b>{html.escape(resp_code)}</b>\n"
            f"<b>𝗔𝗺𝗼𝘂𝗻𝘁 ➠</b> <b>{html.escape(amount)}</b>\n"
            f"<b>𝗨𝘀𝗲𝗿 ➠</b> <b>{user_link}</b>\n"
            f"<b>𝗗𝗲𝘃 ➠</b> {dev_link}"
        )

        #reply_markup = InlineKeyboardMarkup(inline_keyboard=[
            #[InlineKeyboardButton(text="𝘾𝙃𝙆 𝕏 [𝙒 𝙄 𝙕] ", url="https://t.me/CARDCHKX_BOT")]
        #])

        await bot.send_message(
            chat_id=HIT_CHANNEL_ID,
            text=hit_msg,
            parse_mode="HTML",
            #reply_markup=reply_markup,
            disable_web_page_preview=True
        )
    except Exception as e:
        logger.error(f"Failed to send hit message: {e}")

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# COMMAND HANDLER (UPDATED WITH CREDIT DEDUCTION)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

@router.message(F.text.startswith("/stco"))
async def stco_command(message: types.Message):
    user_id = message.from_user.id
    user_name = message.from_user.first_name or "User"
    username = message.from_user.username

    url = ""
    raw_cards = []

    # 1. Manual parsing to avoid 'get_args' attribute error
    text_content = message.text or ""
    parts = text_content.split()[1:] if " " in text_content else []

    if parts:
        potential_url = parts[0]
        if potential_url.startswith("http"):
            url = potential_url
            raw_cards.extend(parts[1:])

    # Safely check for reply_to_message
    if message.reply_to_message:
        replied_text = message.reply_to_message.text or message.reply_to_message.caption or ""
        raw_cards.extend(replied_text.split('\n'))

    # 2. Validate URL
    if not url:
        await message.reply(
            "❌ <b>Invalid Format!</b>\n\n"
            "Usage: <code>/stco &lt;checkout_link&gt; &lt;card1&gt; &lt;card2&gt; ...</code>\n"
            "Or reply to a list of cards.",
            parse_mode="HTML"
        )
        return

    # 3. Extract Cards with Regex
    card_pattern = re.compile(r'(\d{13,19})[\|/:\s]+(\d{1,2})[\|/:\s]+(\d{2,4})[\|/:\s]+(\d{3,4})')

    valid_cards = []
    seen = set()

    for item in raw_cards:
        match = card_pattern.search(item)
        if match:
            cc, mm, yy, cvv = match.groups()
            mm = mm.zfill(2)
            if len(yy) == 4: yy = yy[2:]
            formatted = f"{cc}|{mm}|{yy}|{cvv}"
            if formatted not in seen:
                seen.add(formatted)
                valid_cards.append(formatted)

    # 4. Limits Check
    if len(valid_cards) > MAX_CARDS:
        await message.reply(
            f"❌ <b>Limit Exceeded!</b>\n\nMax allowed: {MAX_CARDS}",
            parse_mode="HTML"
        )
        return

    if not valid_cards:
        await message.reply("⚠️ No valid cards found.", parse_mode="HTML")
        return

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # CREDIT DEDUCTION LOGIC
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

    try:
        # A. Ensure user exists in DB
        await asyncio.to_thread(create_user, user_id, username)

        # B. Check current credits
        current_credits = await asyncio.to_thread(get_user_credits, user_id)

        if current_credits is None or current_credits < 1:
            await message.reply(
                "❌ <b>Insufficient Credits!</b>\n\n"
                "You need at least 1 credit to use this command.\n"
                "Contact admin to top up.",
                parse_mode="HTML"
            )
            return

        # C. Deduct 1 credit
        new_balance = current_credits - 1
        await asyncio.to_thread(update_credits, user_id, new_balance)

        # Debug log
        logger.info(f"[STCO CREDIT] User {user_id} deducted 1 credit. Old: {current_credits} -> New: {new_balance}")

    except Exception as e:
        logger.error(f"Failed to process credits for user {user_id}: {e}")
        await message.reply("⚠️ <b>Database Error.</b>\nCould not verify credits. Please try again.", parse_mode="HTML")
        return

    # 5. Start Async Task (Non-blocking)
    asyncio.create_task(
        run_stco_check(message, url, valid_cards, user_name, user_id)
    )

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# ASYNC MASS CHECKER & UI LOGIC
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

async def run_stco_check(message: types.Message, url: str, cards: List[str], user_name: str, user_id: int):

    start_time = time.time()
    total_cards = len(cards)
    user_link = f"<a href='tg://user?id={user_id}'>{html.escape(user_name)}</a>"
    bot = message.bot

    # Initial Status Message — sent as a reply to the user's command
    status_msg = await message.reply(
        f"𝗧𝗼𝘁𝗮𝗹 𝗖𝗮𝗿𝗱𝘀 ➠ <code>{total_cards}</code>\n"
        f"𝗚𝗮𝘁𝗲𝘄𝗮𝘆 ➠ <code>StripeAutoHitX</code>\n"
        f"𝗧𝗶𝗺𝗲 ➠ <code>0.0s</code>\n"
        f"𝗨𝘀𝗲𝗿 ➠ {user_link}\n"
        f"━━━━━━━━━━━━━━━━\n"
        f"⏳ <b>𝗦𝘁𝗮𝗿𝘁𝗶𝗻𝗴 𝗠𝗮𝘀𝘀 𝗖𝗵𝗲𝗰𝗸...</b>",
        parse_mode="HTML", disable_web_page_preview=True
    )
    msg_id = status_msg.message_id

    # Initialize Session State
    STCO_SESSIONS[msg_id] = {
        "results": [],
        "page": 0,
        "total_cards": total_cards,
        "start_time": start_time,
        "user_name": user_name,
        "user_id": user_id,
        "msg_id": msg_id,
        "amount": "N/A",
        "final_status": "checking"  # checking, completed, expired
    }

    # Semaphore to limit parallel Node.js processes
    sem = asyncio.Semaphore(PARALLEL_LIMIT)

    async def worker(card: str):
        async with sem:
            # Command for Node script
            command = ['node', JS_SCRIPT_PATH, url, PROXY_ENABLED, card]
            res = await run_subprocess(command)

            if res:
                status = res.get('status', 'unknown')
                code = res.get('code', 'error')
                amount = res.get('amount', '')
                link = res.get('link', '')

                # Update amount if found
                if amount and STCO_SESSIONS[msg_id]["amount"] == "N/A":
                    STCO_SESSIONS[msg_id]["amount"] = amount

                # Determine Symbol
                symbol = "❌"
                if status == 'approved':
                    symbol = "✅"
                elif status == 'declined':
                    symbol = "❌"

                return {
                    "card": card,
                    "resp": code,
                    "status": status,
                    "symbol": symbol,
                    "link": link
                }
            else:
                return {
                    "card": card,
                    "resp": "script error",
                    "status": "error",
                    "symbol": "❌",
                    "link": ""
                }

    # Create tasks
    tasks = [asyncio.create_task(worker(cc)) for cc in cards]

    results = []
    pending = set(tasks)
    is_expired = False

    # Process tasks as they complete
    while pending:
        done, pending = await asyncio.wait(pending, return_when=asyncio.FIRST_COMPLETED)

        for task in done:
            try:
                res = task.result()
                results.append(res)

                # 1. CHECK FOR HIT
                if res.get('symbol') == '✅':
                    asyncio.create_task(
                        send_hit_message(
                            bot,
                            res.get('resp'),
                            STCO_SESSIONS[msg_id]['amount'],
                            user_name,
                            user_id
                        )
                    )

                # 2. CHECK FOR SESSION EXPIRED
                if res.get('resp') == 'checkout_not_active_session':
                    is_expired = True
                    STCO_SESSIONS[msg_id]["final_status"] = "expired"
                    # Cancel remaining tasks
                    for p in pending:
                        p.cancel()
                    pending.clear()
                    break
            except Exception as e:
                logger.error(f"Worker task error: {e}")

        if is_expired:
            break

        # Sort: Hits first, then others
        results.sort(key=lambda x: 0 if x['symbol'] == "✅" else 1)

        # Update UI periodically
        if len(results) % UPDATE_EVERY == 0 or not pending:
            elapsed = round(time.time() - start_time, 2)
            STCO_SESSIONS[msg_id]["results"] = results
            STCO_SESSIONS[msg_id]["elapsed_final"] = elapsed

            text = format_page_content(STCO_SESSIONS[msg_id], elapsed, is_working=True)

            # Only show "Checking..." if still running and not expired
            if not is_expired and len(results) < total_cards:
                text += f"\n\n⏳ <b>𝗰𝗵𝗲𝗰𝗸𝗶𝗻𝗴 {len(results)}/{total_cards}...</b>"

            try:
                await status_msg.edit_text(text, parse_mode="HTML", reply_markup=get_keyboard(msg_id))
            except TelegramBadRequest:
                pass
            except Exception as e:
                logger.error(f"UI Update error: {e}")

    # Finalize
    elapsed_final = round(time.time() - start_time, 2)
    STCO_SESSIONS[msg_id]["elapsed_final"] = elapsed_final

    if not is_expired:
        STCO_SESSIONS[msg_id]["final_status"] = "completed"

    footer_text = "\n\n✅ <b>𝗰𝗵𝗲𝗰𝗸 𝗰𝗼𝗺𝗽𝗹𝗲𝘁𝗲.</b>"
    if is_expired:
        footer_text = "\n\n⚠️ <b>𝗖𝗵𝗲𝗰𝗸𝗼𝘂𝘁 𝗘𝘅𝗽𝗶𝗿𝗲𝗱.</b>"

    final_text = format_page_content(STCO_SESSIONS[msg_id], elapsed_final, is_working=False)
    final_text += footer_text

    try:
        await status_msg.edit_text(final_text, parse_mode="HTML", reply_markup=get_keyboard(msg_id))
    except TelegramBadRequest:
        pass

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# FORMATTING & CALLBACKS
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def format_page_content(state: Dict[str, Any], elapsed: float, is_working: bool) -> str:
    results = state["results"]
    page = state["page"]
    start_idx = page * RESULTS_PER_PAGE
    page_results = results[start_idx : start_idx + RESULTS_PER_PAGE]

    user_link = f"<a href='tg://user?id={state['user_id']}'>{html.escape(state['user_name'])}</a>"
    amount = state.get('amount', 'N/A')

    text = (
        f"𝗧𝗼𝘁𝗮𝗹 𝗖𝗮𝗿𝗱𝘀 ➠ <code>{len(results)}/{state['total_cards']}</code>\n"
        f"𝗚𝗮𝘁𝗲𝘄𝗮𝘆 ➠ <code>StripeAutoHitX</code>\n"
        f"𝗔𝗺𝗼𝘂𝗻𝘁 ➠ <code>{html.escape(amount)}</code>\n"
        f"𝗧𝗶𝗺𝗲 ➠ <code>{elapsed}s</code>\n"
        f"𝗨𝘀𝗲𝗿 ➠ {user_link}\n"
        f"━━━━━━━━━━━━━━━━"
    )

    for res in page_results:
        resp_text = html.escape(res.get('resp', 'unknown')).lower()

        if res.get('symbol') == "✅" and res.get('link'):
            resp_text = f"succeeded | <a href='{res['link']}'>success_url</a>"

        text += (
            f"\n<code>{res['card']}</code> {res.get('symbol', '')}\n"
            f"<b>{resp_text}</b>\n"
            f"━━━━━━━━━━━━━━━━"
        )

    return text

def get_keyboard(msg_id: int) -> Optional[InlineKeyboardMarkup]:
    state = STCO_SESSIONS.get(msg_id)
    if not state: return None

    total = len(state["results"])
    if total == 0: return None

    pages = (total + RESULTS_PER_PAGE - 1) // RESULTS_PER_PAGE
    current = state["page"]

    buttons = []
    row = []

    if current > 0:
        row.append(InlineKeyboardButton(text="Back", callback_data=f"stco_prev_{msg_id}"))
    if current < pages - 1:
        row.append(InlineKeyboardButton(text="Next", callback_data=f"stco_next_{msg_id}"))

    if row:
        buttons.append(row)

    if not buttons:
        return None

    return InlineKeyboardMarkup(inline_keyboard=buttons)

@router.callback_query(F.data.startswith("stco_"))
async def stco_callback_handler(callback: types.CallbackQuery):
    data = callback.data
    parts = data.split("_")

    if len(parts) < 3:
        await callback.answer("Invalid callback")
        return

    try:
        msg_id = int(parts[2])
    except ValueError:
        await callback.answer("Invalid ID")
        return

    state = STCO_SESSIONS.get(msg_id)
    if not state:
        await callback.answer("Session expired or not found.", show_alert=True)
        return

    if callback.from_user.id != state['user_id']:
        await callback.answer("⛔ Not your session.", show_alert=True)
        return

    action = parts[1]
    total_results = len(state["results"])
    total_pages = (total_results + RESULTS_PER_PAGE - 1) // RESULTS_PER_PAGE

    if action == "next" and state['page'] < total_pages - 1:
        state['page'] += 1
    elif action == "prev" and state['page'] > 0:
        state['page'] -= 1

    await callback.answer()

    elapsed = state.get('elapsed_final', round(time.time() - state['start_time'], 2))
    text = format_page_content(state, elapsed, is_working=False)

    final_status = state.get('final_status', 'checking')
    if final_status == 'expired':
        text += "\n\n⚠️ <b>𝗖𝗵𝗲𝗰𝗸𝗼𝘂𝘁 𝗘𝘅𝗽𝗶𝗿𝗲𝗱.</b>"
    elif final_status == 'completed':
        text += "\n\n✅ <b>𝗰𝗵𝗲𝗰𝗸 𝗰𝗼𝗺𝗽𝗹𝗲𝘁𝗲.</b>"
    else:
        text += f"\n\n⏳ <b>𝗰𝗵𝗲𝗰𝗸𝗶𝗻𝗴 {len(state['results'])}/{state['total_cards']}...</b>"

    try:
        await callback.message.edit_text(text, parse_mode="HTML", reply_markup=get_keyboard(msg_id))
    except TelegramBadRequest:
        pass
