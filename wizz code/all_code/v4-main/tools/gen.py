from live_emoji import plan_badge, dev_badge
# gen.py - Advanced Credit Card Generator Module
# Supports wildcards (x/X), AMEX 4-digit CVV, regenerate button for inline display only

import re
import random
import time
import io
import asyncio
import logging
from typing import List, Dict, Tuple, Optional
from datetime import datetime
from html import escape

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# AIogram Imports
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
from aiogram import types, F
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, BufferedInputFile
from aiogram.utils.keyboard import InlineKeyboardBuilder

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# LOCAL IMPORTS
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
from database import get_user_credits, update_credits, PooledConn
from sub import get_premium_status
from bin import get_bin_info

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# CONFIGURATION
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

logger = logging.getLogger(__name__)

# Dictionary to track last command time for each user
user_last_command_time = {}

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# DATABASE HELPERS
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def ensure_gen_stats_columns():
    """Ensures gen stats columns exist in users table."""
    try:
        with PooledConn() as conn:
            cursor = conn.cursor()
            try:
                cursor.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS cards_generated INTEGER DEFAULT 0")
            except Exception:
                pass
            conn.commit()
        logger.info("[GEN] Stats columns checked.")
    except Exception as e:
        logger.error(f"[GEN] Error checking stats columns: {e}")

# Run on import
ensure_gen_stats_columns()


async def update_gen_stats(user_id: int, cards_count: int):
    """Increment cards_generated counter for user."""
    def _sync_update():
        try:
            with PooledConn() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    "UPDATE users SET cards_generated = cards_generated + %s WHERE user_id = %s",
                    (cards_count, user_id)
                )
                conn.commit()
        except Exception as e:
            logger.error(f"[GEN] Error updating gen stats: {e}")
    
    await asyncio.to_thread(_sync_update)


async def get_user_plan_name(user_id: int) -> str:
    """Fetches the specific plan name from receipts if premium, else Trial."""
    premium_result = await asyncio.to_thread(get_premium_status, user_id)
    is_premium = premium_result[0] if isinstance(premium_result, tuple) else False
    
    if is_premium:
        try:
            def _sync_fetch():
                with PooledConn() as conn:
                    cursor = conn.cursor()
                    cursor.execute(
                        "SELECT plan FROM receipts WHERE user_id = %s ORDER BY purchased_on DESC LIMIT 1",
                        (user_id,)
                    )
                    row = cursor.fetchone()
                    return row[0].upper() if row else "PREMIUM"
            
            return await asyncio.to_thread(_sync_fetch)
        except Exception as e:
            logger.error(f"[GEN] Error fetching plan name: {e}")
        return "PREMIUM"
    else:
        return "FREE"

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# ENHANCED LUHN ALGORITHM WITH WILDCARD SUPPORT
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def luhn_check(card_number: str) -> bool:
    """Validate a card number using the Luhn algorithm."""
    digits = [int(d) for d in card_number if d.isdigit()]
    
    for i in range(len(digits) - 2, -1, -2):
        digits[i] *= 2
        if digits[i] > 9:
            digits[i] = (digits[i] // 10) + (digits[i] % 10)
    
    total = sum(digits)
    return total % 10 == 0


def expand_wildcards(pattern: str) -> List[str]:
    """Expand wildcards (x/X) in a pattern to all possible combinations."""
    if 'x' not in pattern.lower():
        return [pattern]
    
    positions = [i for i, c in enumerate(pattern) if c.lower() == 'x']
    results = []
    
    for mask in range(10 ** len(positions)):
        new_pattern = list(pattern)
        temp = mask
        for pos in positions:
            new_pattern[pos] = str(temp % 10)
            temp //= 10
        results.append(''.join(new_pattern))
    
    return results


def generate_luhn_card_with_wildcard(prefix_pattern: str, length: int = 16) -> Tuple[str, str]:
    """
    Generate a valid credit card number supporting wildcards (x/X).
    Returns (generated_card, used_prefix)
    """
    if 'x' in prefix_pattern.lower():
        possible_prefixes = expand_wildcards(prefix_pattern)
        random.shuffle(possible_prefixes)
        for prefix in possible_prefixes:
            try:
                card = generate_luhn_card(prefix, length)
                if luhn_check(card):
                    return card, prefix
            except:
                continue
        prefix = prefix_pattern.replace('x', '0').replace('X', '0')
        return generate_luhn_card(prefix, length), prefix
    else:
        return generate_luhn_card(prefix_pattern, length), prefix_pattern


def generate_luhn_card(prefix: str, length: int = 16) -> str:
    """Generate a valid credit card number using the Luhn algorithm."""
    card = prefix
    
    while len(card) < length - 1:
        card += str(random.randint(0, 9))
    
    for i in range(10):
        test_card = card + str(i)
        if luhn_check(test_card):
            return test_card
    
    return card + "0"


def get_card_length(bin_prefix: str, bin_info: Dict = None) -> int:
    """Determine card length based on BIN info or prefix."""
    if bin_info:
        scheme = bin_info.get("scheme", "").lower()
        if scheme == "american express":
            return 15
    
    if bin_prefix.startswith(("34", "37")):
        return 15
    
    return 16


def get_cvv_length(bin_prefix: str, bin_info: Dict = None) -> int:
    """Determine CVV length based on card type."""
    if bin_info:
        scheme = bin_info.get("scheme", "").lower()
        if scheme == "american express":
            return 4
    
    if bin_prefix.startswith(("34", "37")):
        return 4
    
    return 3

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# ENHANCED INPUT PARSING WITH WILDCARD SUPPORT
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def parse_gen_input(input_text: str) -> Tuple[str, str, str, int, str]:
    """
    Parse the input for the gen command with wildcard support.
    Supports: 544422885678xxxx|06|27|xxx|100
    """
    bin_pattern = ""
    month = "rnd"
    year = "rnd"
    amount = 10
    cvv = "rnd"
    
    if "|" in input_text:
        parts = input_text.split("|")
        
        if len(parts) > 0:
            bin_pattern = parts[0].strip()
        
        if len(parts) > 1:
            month_val = parts[1].strip()
            if month_val.lower() in ["rnd", "xxx"]:
                month = "rnd"
            elif month_val.isdigit() and 1 <= int(month_val) <= 12:
                month = month_val.zfill(2)
            else:
                month = "rnd"
        
        if len(parts) > 2:
            year_val = parts[2].strip()
            if year_val.lower() in ["rnd", "xxx"]:
                year = "rnd"
            elif year_val.isdigit():
                if len(year_val) == 4:
                    year = year_val[2:]
                else:
                    year = year_val.zfill(2)
            else:
                year = "rnd"
        
        if len(parts) > 3:
            cvv_val = parts[3].strip()
            if cvv_val.lower() in ["rnd", "xxx"]:
                cvv = "rnd"
            elif cvv_val.isdigit() and len(cvv_val) in [3, 4]:
                cvv = cvv_val
            else:
                cvv = "rnd"
        
        if len(parts) > 4:
            try:
                amount_val = int(parts[4].strip())
                if 1 <= amount_val <= 100000:
                    amount = amount_val
            except ValueError:
                pass
    
    else:
        parts = input_text.split()
        
        if len(parts) > 0:
            bin_pattern = parts[0].strip()
        
        if len(parts) > 1:
            try:
                amount_val = int(parts[1].strip())
                if 1 <= amount_val <= 100000:
                    amount = amount_val
            except ValueError:
                month_val = parts[1].strip()
                if month_val.lower() not in ["rnd", "xxx"]:
                    month = month_val if month_val.isdigit() else "rnd"
        
        if len(parts) > 2 and month != "rnd":
            year_val = parts[2].strip()
            if year_val.lower() not in ["rnd", "xxx"]:
                year = year_val if year_val.isdigit() else "rnd"
        
        if len(parts) > 3 and month != "rnd" and year != "rnd":
            cvv_val = parts[3].strip()
            if cvv_val.lower() not in ["rnd", "xxx"]:
                cvv = cvv_val if cvv_val.isdigit() else "rnd"
        
        if len(parts) > 4:
            try:
                amount_val = int(parts[4].strip())
                if 1 <= amount_val <= 100000:
                    amount = amount_val
            except ValueError:
                pass
    
    if not bin_pattern:
        raise ValueError("BIN pattern is required")
    
    clean_pattern = re.sub(r'[^0-9xX]', '', bin_pattern)
    if len(clean_pattern) < 6:
        raise ValueError("BIN must be at least 6 digits (use x/X for wildcards)")
    
    return clean_pattern, month, year, amount, cvv

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# ENHANCED CARD GENERATION
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

async def generate_cards_enhanced(bin_pattern: str, month: str, year: str, amount: int, cvv: str) -> Tuple[List[str], Dict, str]:
    """
    Generate credit cards with wildcard support and proper CVV length.
    Returns (cards, bin_info, used_prefix)
    """
    base_bin = bin_pattern[:6].replace('x', '0').replace('X', '0')
    bin_info = await get_bin_info(base_bin)
    
    card_length = get_card_length(bin_pattern, bin_info)
    cvv_length = get_cvv_length(bin_pattern, bin_info)
    
    cards = []
    used_prefixes = set()
    
    for _ in range(amount):
        card_number, used_prefix = generate_luhn_card_with_wildcard(bin_pattern, card_length)
        used_prefixes.add(used_prefix)
        
        if month.lower() == "rnd":
            card_month = str(random.randint(1, 12)).zfill(2)
        else:
            card_month = month
        
        if year.lower() == "rnd":
            current_year = int(time.strftime("%y"))
            card_year = str(random.randint(current_year, current_year + 10)).zfill(2)
        else:
            card_year = year
        
        if cvv.lower() == "rnd":
            card_cvv = ''.join([str(random.randint(0, 9)) for _ in range(cvv_length)])
        else:
            card_cvv = cvv
            if len(card_cvv) > cvv_length:
                card_cvv = card_cvv[:cvv_length]
            elif len(card_cvv) < cvv_length:
                card_cvv = card_cvv + ''.join([str(random.randint(0, 9)) for _ in range(cvv_length - len(card_cvv))])
        
        card = f"{card_number}|{card_month}|{card_year}|{card_cvv}"
        cards.append(card)
    
    used_prefix = list(used_prefixes)[0] if used_prefixes else bin_pattern
    
    return cards, bin_info, used_prefix

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# REGENERATE BUTTON (ONLY FOR INLINE DISPLAY)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def get_regenerate_keyboard(bin_pattern: str, month: str, year: str, amount: int, cvv: str) -> InlineKeyboardMarkup:
    """Create inline keyboard with regenerate button only."""
    callback_data = f"gen_reg|{bin_pattern[:15]}|{month}|{year}|{amount}|{cvv}"
    
    builder = InlineKeyboardBuilder()
    builder.button(text="🔄 𝐑𝐞𝐠𝐞𝐧𝐞𝐫𝐚𝐭𝐞 𝐂𝐚𝐫𝐝𝐬", callback_data=callback_data, disable_web_page_preview=True)
    builder.adjust(1)
    
    return builder.as_markup()


async def regenerate_cards_callback(callback: types.CallbackQuery):
    """Handle regenerate button callback - only for inline display (1-20 cards)."""
    data = callback.data
    user_id = callback.from_user.id
    
    parts = data.split("|")
    if len(parts) < 6:
        await callback.answer("❌ Invalid regenerate request", show_alert=True, disable_web_page_preview=True)
        return
    
    _, bin_pattern, month, year, amount_str, cvv = parts
    amount = int(amount_str)
    
    # Only allow regeneration for 1-20 cards (inline display range)
    if amount > 20:
        await callback.answer("❌ Regeneration only available for 1-20 cards", show_alert=True)
        return
    
    current_credits = await asyncio.to_thread(get_user_credits, user_id)
    if current_credits is None or current_credits <= 0:
        await callback.answer("❌ Insufficient credits to regenerate!", show_alert=True, disable_web_page_preview=True)
        return
    
    new_balance = current_credits - 1
    await asyncio.to_thread(update_credits, user_id, new_balance)
    await update_gen_stats(user_id, amount)
    
    try:
        cards, bin_info, used_prefix = await generate_cards_enhanced(bin_pattern, month, year, amount, cvv)
        
        plan_name = await get_user_plan_name(user_id)
        user = callback.from_user
        
        user_link = f'<a href="tg://user?id={user.id}">{escape(user.first_name)}</a>'
        dev_link = dev_badge()
        user_display = f"{user_link} {plan_badge(plan_name)}"
        
        brand = (bin_info.get("scheme") or "N/A").title()
        bank = bin_info.get("bank") or "N/A"
        country = bin_info.get("country") or "Unknown"
        card_type = bin_info.get("type", "N/A")
        
        card_list = "\n".join([f"<code>{card}</code>" for card in cards])
        
        text = (
            f"<b>𝐂𝐚𝐫𝐝𝐬 𝐑𝐞𝐠𝐞𝐧𝐞𝐫𝐚𝐭𝐞𝐝 𝐒𝐮𝐜𝐜𝐞𝐬𝐬𝐟𝐮𝐥𝐥𝐲</b>\n"
            f"━━━━━━━━━━━━━━━━\n"
            f"<b>𝐁𝐈𝐍</b> ➺ <code>{used_prefix}</code>\n"
            f"<b>𝐆𝐞𝐧𝐞𝐫𝐚𝐭𝐞𝐝</b> ➺ <code>{len(cards)} cards</code>\n"
            f"━━━━━━━━━━━━━━━━\n"
            f"{card_list}\n"
            f"━━━━━━━━━━━━━━━━\n"
            f"┌─ <b>𝐁𝐫𝐚𝐧𝐝</b>: {brand}\n"
            f"├─ <b>𝐁𝐚𝐧𝐤</b>: {bank}\n"
            f"├─ <b>𝐂𝐨𝐮𝐧𝐭𝐫𝐲</b>: {country}\n"
            f"└─ <b>𝐓𝐲𝐩𝐞</b>: {card_type}\n"
            f"━━━━━━━━━━━━━━━━\n"
            f"<b>𝐔𝐬𝐞𝐫</b> ➺ {user_display}\n"
            f"<b>𝐃𝐞𝐯</b> ➺ {dev_link}"
            
        )
        
        await callback.message.edit_text(
            text=text,
            parse_mode="HTML",
            disable_web_page_preview=True,
            reply_markup=get_regenerate_keyboard(bin_pattern, month, year, amount, cvv)
        )
        
        await callback.answer("✅ Cards regenerated successfully!")
        
        if new_balance <= 10:
            await callback.message.answer(
                f"⚠️ <b>Low Credits Warning</b>\n"
                f"You have <code>{new_balance}</code> credits remaining.\n"
                f"Use /plan to recharge.",
                parse_mode="HTML"
            )
        
    except Exception as e:
        logger.error(f"[GEN] Regeneration error: {e}")
        await callback.answer("❌ Error regenerating cards", show_alert=True, disable_web_page_preview=True)

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# MAIN COMMAND HANDLER
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

async def gen_command(message: types.Message):
    """
    /gen <bin_pattern> - Generate credit cards with wildcard support
    """
    
    user = message.from_user
    user_id = user.id
    current_time = time.time()
    
    premium_result = await asyncio.to_thread(get_premium_status, user_id)
    is_premium = premium_result[0] if isinstance(premium_result, tuple) else False
    
    cooldown = 2 if is_premium else 5
    
    if user_id in user_last_command_time:
        elapsed = current_time - user_last_command_time[user_id]
        if elapsed < cooldown:
            remaining_time = round(cooldown - elapsed, 1)
            await message.reply(
                f"⚠️ <b>Slow Down!</b>\n"
                f"Please wait <code>{remaining_time}</code> seconds.\n\n"
                f"<i>Premium: {cooldown}s | FREE: 5s</i>",
                parse_mode="HTML"
            )
            return
    
    user_last_command_time[user_id] = current_time
    
    parts = message.text.split(maxsplit=1)
    if len(parts) < 2:
        await message.reply(
            "❌ <b>Invalid Format!</b>\n\n"
            "📌 <b>Basic Usage:</b>\n"
            "<code>/gen 486732</code>\n\n"
            "📌 <b>With Wildcards (x/X):</b>\n"
            "<code>/gen 544422885678xxxx</code>\n\n"
            "📌 <b>Full Format:</b>\n"
            "<code>/gen BIN|MM|YY|CVV|AMOUNT</code>\n\n"
            "📌 <b>Examples:</b>\n"
            "<code>/gen 544422885678xxxx|06|27|xxx|50</code>\n"
            "<code>/gen 486732|rnd|rnd|rnd|100</code>\n\n"
            "✨ <b>Features:</b>\n"
            "• Wildcard support (x/X = random digit)\n"
            "• AMEX auto-detection (4-digit CVV)\n"
            "• Regenerate button for 1-20 cards\n"
            "• Generate up to 100,000 cards\n"
            "• Auto TXT file for 20+ cards\n\n"
            "<b>Cost:</b> 1 credit per generation",
            parse_mode="HTML"
        )
        return
    
    input_text = parts[1].strip()
    
    try:
        bin_pattern, month, year, amount, cvv = parse_gen_input(input_text)
    except ValueError as e:
        await message.reply(
            f"⚠️ <b>Error: {str(e)}</b>",
            parse_mode="HTML"
        )
        return
    
    if amount < 1:
        amount = 1
    elif amount > 100000:
        await message.reply(
            "❌ <b>Maximum limit exceeded!</b>\n"
            "You can generate up to 100,000 cards per request.\n"
            f"Requested: {amount} cards",
            parse_mode="HTML"
        )
        return
    
    current_credits = await asyncio.to_thread(get_user_credits, user_id)
    if current_credits is None or current_credits <= 0:
        await message.reply(
            "❌ <b>Insufficient Credits!</b>\n\n"
            "You have 0 credits left.\n"
            "Use /plan to purchase more credits.",
            parse_mode="HTML"
        )
        return
    
    plan_name = await get_user_plan_name(user_id)
    
    if amount > 100:
        processing_text = f"<pre>🃏 Generating {amount:,} cards with pattern {bin_pattern[:6]}...⏳\nThis may take a few moments...</pre>"
    else:
        processing_text = f"<pre>🃏 Generating {amount} cards with pattern {bin_pattern[:6]}...⏳</pre>"
    
    proc_msg = await message.reply(processing_text, parse_mode="HTML")
    
    asyncio.create_task(
        process_gen_enhanced(
            message, proc_msg, user, user_id, bin_pattern, month, year, amount, cvv, plan_name
        )
    )


async def process_gen_enhanced(message, proc_msg, user, user_id, bin_pattern, month, year, amount, cvv, plan_name):
    """Process enhanced card generation with file support."""
    
    try:
        cards, bin_info, used_prefix = await generate_cards_enhanced(bin_pattern, month, year, amount, cvv)
        logger.info(f"[GEN] Generated {len(cards)} cards for user {user_id} with BIN {used_prefix}")
    except Exception as e:
        logger.error(f"[GEN] Generation error: {e}")
        await proc_msg.edit_text(
            text="❌ <b>Error generating cards. Please check your BIN pattern.</b>",
            parse_mode="HTML"
        )
        return
    
    current_balance = await asyncio.to_thread(get_user_credits, user_id)
    new_balance = max(0, current_balance - 1)
    await asyncio.to_thread(update_credits, user_id, new_balance)
    await update_gen_stats(user_id, len(cards))
    
    user_link = f'<a href="tg://user?id={user.id}">{escape(user.first_name)}</a>'
    dev_link = dev_badge()
    user_display = f"{user_link} {plan_badge(plan_name)}"
    
    brand = (bin_info.get("scheme") or "N/A").title()
    bank = bin_info.get("bank") or "N/A"
    country = bin_info.get("country") or "Unknown"
    card_type = bin_info.get("type", "N/A")
    
    # For 20+ cards - send as file (NO regenerate button)
    if amount > 20:
        file_content = "\n".join(cards)
        file_bytes = file_content.encode('utf-8')
        filename = f"WIZX_GEN_{used_prefix}_{int(time.time())}.txt"
        document = BufferedInputFile(file_bytes, filename=filename)
        
        caption = (
            f"<b>𝐂𝐚𝐫𝐝𝐬 𝐆𝐞𝐧𝐞𝐫𝐚𝐭𝐞𝐝 𝐒𝐮𝐜𝐜𝐞𝐬𝐬𝐟𝐮𝐥𝐥𝐲</b>\n"
            f"━━━━━━━━━━━━━━━━\n"
            f"<b>𝐁𝐈𝐍</b> ➺ <code>{used_prefix}</code>\n"
            f"<b>𝐆𝐞𝐧𝐞𝐫𝐚𝐭𝐞𝐝</b> ➺ <code>{len(cards):,} cards</code>\n"
            f"━━━━━━━━━━━━━━━━\n"
            f"┌─ <b>𝐁𝐫𝐚𝐧𝐝</b>: {brand}\n"
            f"├─ <b>𝐁𝐚𝐧𝐤</b>: {bank}\n"
            f"├─ <b>𝐂𝐨𝐮𝐧𝐭𝐫𝐲</b>: {country}\n"
            f"└─ <b>𝐓𝐲𝐩𝐞</b>: {card_type}\n"
            f"━━━━━━━━━━━━━━━━\n"
            f"<b>𝐔𝐬𝐞𝐫</b> ➺ {user_display}\n"
            f"<b>𝐃𝐞𝐯</b> ➺ {dev_link}\n"
            
        )
        
        try:
            await proc_msg.delete()
        except Exception:
            pass
        
        await message.reply_document(
            document=document,
            caption=caption,
            parse_mode="HTML",
            disable_web_page_preview=True
        )
        
        if new_balance <= 10:
            await message.reply(
                f"⚠️ <b>Low Credits Warning</b>\n"
                f"You have <code>{new_balance}</code> credits remaining.\n"
                f"Use /plan to recharge.",
                parse_mode="HTML",
                disable_web_page_preview=True
            )
    
    # For 1-20 cards - display inline (WITH regenerate button)
    else:
        card_list = "\n".join([f"<code>{card}</code>" for card in cards])
        
        final_caption = (
            f"<b>𝐂𝐚𝐫𝐝𝐬 𝐆𝐞𝐧𝐞𝐫𝐚𝐭𝐞𝐝 𝐒𝐮𝐜𝐜𝐞𝐬𝐬𝐟𝐮𝐥𝐥𝐲</b>\n"
            f"━━━━━━━━━━━━━━━━\n"
            f"<b>𝐁𝐈𝐍</b> ➺ <code>{used_prefix}</code>\n"
            f"<b>𝐆𝐞𝐧𝐞𝐫𝐚𝐭𝐞𝐝</b> ➺ <code>{len(cards)} cards</code>\n"
            f"━━━━━━━━━━━━━━━━\n"
            f"{card_list}\n"
            f"━━━━━━━━━━━━━━━━\n"
            f"┌─ <b>𝐁𝐫𝐚𝐧𝐝</b>: {brand}\n"
            f"├─ <b>𝐁𝐚𝐧𝐤</b>: {bank}\n"
            f"├─ <b>𝐂𝐨𝐮𝐧𝐭𝐫𝐲</b>: {country}\n"
            f"└─ <b>𝐓𝐲𝐩𝐞</b>: {card_type}\n"
            f"━━━━━━━━━━━━━━━━\n"
            f"<b>𝐔𝐬𝐞𝐫</b> ➺ {user_display}\n"
            f"<b>𝐃𝐞𝐯</b> ➺ {dev_link}"
            
        )
        
        try:
            await proc_msg.edit_text(
                text=final_caption,
                parse_mode="HTML",
                disable_web_page_preview=True,
                reply_markup=get_regenerate_keyboard(bin_pattern, month, year, amount, cvv)
            )
        except Exception as e:
            logger.error(f"[GEN] Error editing message: {e}")
            await message.reply(
                text=final_caption,
                parse_mode="HTML",
                disable_web_page_preview=True,
                reply_markup=get_regenerate_keyboard(bin_pattern, month, year, amount, cvv)
            )
        
        if new_balance <= 10:
            await message.reply(
                f"⚠️ <b>Low Credits Warning</b>\n"
                f"You have <code>{new_balance}</code> credits remaining.\n"
                f"Use /plan to recharge.",
                parse_mode="HTML"
            )


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# HELP COMMAND
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

async def genhelp_command(message: types.Message):
    """Show detailed help for Gen command."""
    help_text = (
        "🃏 <b>Advanced Credit Card Generator</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        
        "📌 <b>Basic Commands:</b>\n"
        "• <code>/gen 486732</code> - Generate 10 cards\n"
        "• <code>/gen 486732|12|26|123|50</code> - Full format\n\n"
        
        "✨ <b>Wildcard Support (x/X):</b>\n"
        "• <code>/gen 544422xxxxxx</code> - Random digits\n"
        "• <code>/gen 544422885678xxxx|06|27|xxx</code>\n\n"
        
        "📊 <b>Format Options:</b>\n"
        "• <b>BIN</b>: 6+ digits (use x/X for wildcards)\n"
        "• <b>MM</b>: 01-12 or 'rnd'/'xxx'\n"
        "• <b>YY</b>: 24-30 or 'rnd'/'xxx'\n"
        "• <b>CVV</b>: 3-4 digits or 'rnd'/'xxx'\n"
        "• <b>Amount</b>: 1-100,000 cards\n\n"
        
        "🎯 <b>Auto Features:</b>\n"
        "• AMEX detection → 4-digit CVV\n"
        "• Luhn validation → Valid cards only\n"
        "• Regenerate button → For 1-20 cards only\n"
        "• TXT file → For 20+ cards\n\n"
        
        "💰 <b>Pricing:</b>\n"
        "• 1 credit per generation (any amount)\n"
        "• Cooldown: 2s (Premium) / 5s (Free)\n\n"
        
        "📝 <b>Example:</b>\n"
        "<code>/gen 544422885678xxxx|06|27|xxx|100</code>\n"
        "→ Generates 100 valid cards with random CVV"
    )
    await message.reply(help_text, parse_mode="HTML", disable_web_page_preview=True)