"""user_admin.py — /user admin panel (owner only).
Interactive button window: list users -> user detail with access (green/red),
plan, revoke, block/unblock. Premium emoji IDs + colored buttons everywhere.
"""
import asyncio
from datetime import datetime, timedelta
from aiogram import types, F, Router
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from database import get_db_connection, OWNER_IDS
from mass_gates._tg_helpers import safe_reply
from ban import _is_banned_sync, _ban_user_sync, _unban_user_sync

router = Router()

ID_APPROVED = "6044254523009012231"
ID_DECLINED = "5893081007153746175"
ID_CHARGED = "5359719332542718652"
ID_WARNING = "6255910249362885846"
ID_STAR = "6136275172283391020"
ID_GATEWAY = "5085022089103016925"
ID_LOCK = "5258419835922030550"
ID_TOP = "5463071033256848094"
ID_STOP = "5247149163132493357"
PAGE_SIZE = 8

def _tg(eid: str, fb: str) -> str:
    return f'<tg-emoji emoji-id="{eid}">{fb}</tg-emoji>'

def _btn(text, data, style="primary", emoji=None):
    kw = {"text": text, "callback_data": data, "style": style}
    if emoji:
        kw["icon_custom_emoji_id"] = emoji
    return InlineKeyboardButton(**kw)

def _is_owner(user_id: int) -> bool:
    return user_id in OWNER_IDS

def _all_users_sync():
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute(
        "SELECT user_id, first_name, username, is_premium, premium_expiry, "
        "credits, cc_checked, cc_charged, joined_at, is_owner "
        "FROM users ORDER BY user_id"
    )
    rows = cur.fetchall()
    conn.close()
    return rows

def _user_sync(user_id: int):
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute(
        "SELECT user_id, first_name, username, is_premium, premium_expiry, "
        "credits, cc_checked, cc_charged, joined_at, is_owner "
        "FROM users WHERE user_id = %s", (user_id,)
    )
    row = cur.fetchone()
    plan = None
    try:
        cur.execute(
            "SELECT plan FROM receipts WHERE user_id = %s ORDER BY purchased_on DESC LIMIT 1",
            (user_id,),
        )
        pr = cur.fetchone()
        plan = pr[0] if pr else None
    except Exception:
        plan = None
    conn.close()
    return row, plan

def _grant_sync(user_id: int, days: int):
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO users (user_id, username, first_name, credits, joined_at) "
        "VALUES (%s, %s, %s, %s, %s) ON CONFLICT (user_id) DO NOTHING",
        (user_id, "Unknown", "User", 0, datetime.now()),
    )
    cur.execute("SELECT premium_expiry FROM users WHERE user_id = %s", (user_id,))
    row = cur.fetchone()
    cur_exp = row[0] if row and row[0] else None
    base = cur_exp if (cur_exp and cur_exp > datetime.now()) else datetime.now()
    new_expiry = base + timedelta(days=days)
    cur.execute(
        "UPDATE users SET is_premium = 1, premium_expiry = %s WHERE user_id = %s",
        (new_expiry, user_id),
    )
    conn.commit()
    conn.close()
    return new_expiry

def _revoke_sync(user_id: int):
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute(
        "UPDATE users SET is_premium = 0, premium_expiry = NULL WHERE user_id = %s",
        (user_id,),
    )
    conn.commit()
    conn.close()

def _user_detail_text(row, plan) -> str:
    (uid, first_name, username, is_premium, expiry, credits,
     cc_checked, cc_charged, joined_at, is_owner) = row
    name = (first_name or username or str(uid))
    has_access = bool(is_premium) and bool(expiry) and expiry > datetime.now()
    banned = _is_banned_sync(uid)
    if is_owner:
        access_line = f'{_tg(ID_CHARGED, "💎")} 𝗔𝗰𝗰𝗲𝘀𝘀 ➠ <b>𝗢𝗪𝗡𝗘𝗥</b>'
        days_line = "∞"
    elif has_access:
        days_left = max(0, (expiry - datetime.now()).days)
        access_line = f'{_tg(ID_APPROVED, "✅")} 𝗔𝗰𝗰𝗲𝘀𝘀 ➠ <b>𝗚𝗥𝗔𝗡𝗧𝗘𝗗</b>'
        days_line = f'<code>{days_left}</code> 𝗱𝗮𝘆𝘀 𝗿𝗲𝗺𝗮𝗶𝗻𝗶𝗻𝗴'
    else:
        access_line = f'{_tg(ID_DECLINED, "❌")} 𝗔𝗰𝗰𝗲𝘀𝘀 ➠ <b>𝗡𝗢 𝗔𝗖𝗖𝗘𝗦𝗦</b>'
        days_line = "<b>𝟬</b> 𝗱𝗮𝘆𝘀"
    expiry_str = expiry.strftime("%Y-%m-%d") if expiry else "N/A"
    joined_str = joined_at.strftime("%Y-%m-%d") if joined_at else "N/A"
    uname = username or "N/A"
    banned_line = f'{_tg(ID_STOP, "⛔")} 𝗕𝗹𝗼𝗰𝗸𝗲𝗱 ➠ <b>𝗬𝗘𝗦</b>' if banned else f'{_tg(ID_APPROVED, "✅")} 𝗕𝗹𝗼𝗰𝗸𝗲𝗱 ➠ <b>𝗡𝗢</b>'
    plan_str = plan or ("𝗢𝗪𝗡𝗘𝗥" if is_owner else "𝗙𝗥𝗘𝗘")
    return (
        f'{_tg(ID_STAR, "⭐")} <b>𝗨𝗦𝗘𝗥 𝗗𝗘𝗧𝗔𝗜𝗟</b>\n'
        f"━━━━━━━━━━━━━━━━\n"
        f'{_tg(ID_GATEWAY, "⚡")} 𝗜𝗗 ➠ <code>{uid}</code>\n'
        f"𝗡𝗮𝗺𝗲 ➠ <b>{name}</b>\n"
        f"𝗨𝘀𝗲𝗿𝗻𝗮𝗺𝗲 ➠ @{uname}\n"
        f"━━━━━━━━━━━━━━━━\n"
        f"{access_line}\n"
        f'{_tg(ID_CHARGED, "💎")} 𝗣𝗹𝗮𝗻 ➠ <b>{plan_str}</b>\n'
        f'{_tg(ID_LOCK, "🔐")} 𝗥𝗲𝗺𝗮𝗶𝗻𝗶𝗻𝗴 ➠ {days_line}\n'
        f"𝗘𝘅𝗽𝗶𝗿𝘆 ➠ <code>{expiry_str}</code>\n"
        f"━━━━━━━━━━━━━━━━\n"
        f"{banned_line}\n"
        f"𝗖𝗿𝗲𝗱𝗶𝘁𝘀 ➠ <code>{credits}</code>\n"
        f"𝗖𝗵𝗲𝗰𝗸𝗲𝗱 ➠ <code>{cc_checked}</code>  |  𝗖𝗵𝗮𝗿𝗴𝗲𝗱 ➠ <code>{cc_charged}</code>\n"
        f"𝗝𝗼𝗶𝗻𝗲𝗱 ➠ <code>{joined_str}</code>"
    )

@router.message(F.text.startswith("/user"))
async def user_command(message: types.Message):
    if not _is_owner(message.from_user.id):
        await safe_reply(message, f'{_tg(ID_DECLINED, "❌")} 𝗡𝗼𝘁 𝗮𝘂𝘁𝗵𝗼𝗿𝗶𝘇𝗲𝗱.', parse_mode="HTML")
        return
    await _show_user_page(message, 0)

async def _show_user_page(message: types.Message, page: int):
    rows = await asyncio.to_thread(_all_users_sync)
    total = len(rows)
    pages = max(1, (total + PAGE_SIZE - 1) // PAGE_SIZE)
    page = max(0, min(page, pages - 1))
    chunk = rows[page * PAGE_SIZE:(page + 1) * PAGE_SIZE]
    if not chunk:
        await safe_reply(message, f'{_tg(ID_WARNING, "⚠️")} 𝗡𝗼 𝘂𝘀𝗲𝗿𝘀 𝗳𝗼𝘂𝗻𝗱.', parse_mode="HTML")
        return
    lines = [f'{_tg(ID_CHARGED, "💎")} <b>𝗨𝗦𝗘𝗥𝗦</b>  ({total})', "━━━━━━━━━━━━━━━━"]
    kb_rows = []
    for (uid, first_name, username, is_premium, expiry, credits,
         cc_checked, cc_charged, joined_at, is_owner) in chunk:
        has_access = bool(is_premium) and bool(expiry) and expiry > datetime.now()
        if is_owner:
            style, status_icon = "primary", ID_CHARGED
        elif has_access:
            style, status_icon = "success", ID_APPROVED
        else:
            style, status_icon = "danger", ID_DECLINED
        name = (first_name or username or str(uid))[:18]
        kb_rows.append([_btn(f"{name} · {uid}", f"ud_{uid}", style, status_icon)])
    nav = []
    if page > 0:
        nav.append(_btn("◀ 𝗕𝗮𝗰𝗸", f"up_{page - 1}", "primary", ID_TOP))
    if page < pages - 1:
        nav.append(_btn("𝗡𝗲𝘅𝘁 ▶", f"up_{page + 1}", "primary", ID_TOP))
    if nav:
        kb_rows.append(nav)
    kb = InlineKeyboardMarkup(inline_keyboard=kb_rows)
    text = "\n".join(lines) + f"\n━━━━━━━━━━━━━━━━\n𝗣𝗮𝗴𝗲 ➠ <code>{page + 1}/{pages}</code>"
    try:
        await message.answer(text, parse_mode="HTML", reply_markup=kb)
    except Exception:
        await safe_reply(message, text, parse_mode="HTML", reply_markup=kb)

@router.callback_query(F.data.startswith("up_"))
async def user_page_cb(callback: types.CallbackQuery):
    if not _is_owner(callback.from_user.id):
        await callback.answer("𝗡𝗼𝘁 𝗮𝘂𝘁𝗵𝗼𝗿𝗶𝘇𝗲𝗱.", show_alert=True)
        return
    page = int(callback.data.split("_", 1)[1])
    await _show_user_page(callback.message, page)
    await callback.answer()

def _detail_kb(uid, row):
    (u, fname, uname, is_premium, expiry, credits,
     cc_checked, cc_charged, joined_at, is_owner) = row
    has_access = bool(is_premium) and bool(expiry) and expiry > datetime.now()
    banned = _is_banned_sync(uid)
    rows = []
    if not is_owner:
        # access badge: green if has access, red if not
        if has_access:
            rows.append([_btn("𝗛𝗔𝗦 𝗔𝗖𝗖𝗘𝗦𝗦", "noop", "success", ID_APPROVED)])
        else:
            rows.append([_btn("𝗡𝗢 𝗔𝗖𝗖𝗘𝗦𝗦", "noop", "danger", ID_DECLINED)])
        rows.append([
            _btn("𝗚𝗿𝗮𝗻𝘁 𝟳𝗱", f"g_{uid}_7", "success", ID_APPROVED),
            _btn("𝗚𝗿𝗮𝗻𝘁 𝟯𝟬𝗱", f"g_{uid}_30", "success", ID_APPROVED),
            _btn("𝗚𝗿𝗮𝗻𝘁 𝟵𝟬𝗱", f"g_{uid}_90", "success", ID_APPROVED),
        ])
        rows.append([
            _btn("𝗥𝗲𝘃𝗼𝗸𝗲", f"rv_{uid}", "danger", ID_DECLINED),
        ])
        if banned:
            rows.append([_btn("𝗨𝗻𝗯𝗹𝗼𝗰𝗸", f"unblk_{uid}", "success", ID_APPROVED)])
        else:
            rows.append([_btn("𝗕𝗹𝗼𝗰𝗸", f"blk_{uid}", "danger", ID_STOP)])
    rows.append([_btn("◀ 𝗨𝘀𝗲𝗿𝘀", "up_0", "primary", ID_TOP)])
    return InlineKeyboardMarkup(inline_keyboard=rows)

@router.callback_query(F.data.startswith("ud_"))
async def user_detail_cb(callback: types.CallbackQuery):
    if not _is_owner(callback.from_user.id):
        await callback.answer("𝗡𝗼𝘁 𝗮𝘂𝘁𝗵𝗼𝗿𝗶𝘇𝗲𝗱.", show_alert=True)
        return
    uid = int(callback.data.split("_", 1)[1])
    row, plan = await asyncio.to_thread(_user_sync, uid)
    if not row:
        await callback.answer("𝗨𝘀𝗲𝗿 𝗻𝗼𝘁 𝗳𝗼𝘂𝗻𝗱.", show_alert=True)
        return
    text = _user_detail_text(row, plan)
    kb = _detail_kb(uid, row)
    try:
        await callback.message.edit_text(text, parse_mode="HTML", reply_markup=kb)
    except Exception:
        await callback.message.answer(text, parse_mode="HTML", reply_markup=kb)
    await callback.answer()

@router.callback_query(F.data.startswith("g_"))
async def grant_cb(callback: types.CallbackQuery):
    if not _is_owner(callback.from_user.id):
        await callback.answer("𝗢𝗻𝗹𝘆 𝘁𝗵𝗲 𝗼𝘄𝗻𝗲𝗿 𝗰𝗮𝗻 𝗴𝗿𝗮𝗻𝘁 𝗮𝗰𝗰𝗲𝘀𝘀.", show_alert=True)
        return
    _, uid, days = callback.data.split("_")
    uid = int(uid)
    new_expiry = await asyncio.to_thread(_grant_sync, uid, int(days))
    row, plan = await asyncio.to_thread(_user_sync, uid)
    text = _user_detail_text(row, plan)
    text += f"\n\n{_tg(ID_APPROVED, '✅')} 𝗚𝗿𝗮𝗻𝘁𝗲𝗱 (+{days} 𝗱𝗮𝘆𝘀). 𝗘𝘅𝗽𝗶𝗿𝘆 ➠ {new_expiry.strftime('%Y-%m-%d')}"
    kb = _detail_kb(uid, row)
    try:
        await callback.message.edit_text(text, parse_mode="HTML", reply_markup=kb)
    except Exception:
        pass
    await callback.answer(f"𝗔𝗰𝗰𝗲𝘀𝘀 𝗴𝗿𝗮𝗻𝘁𝗲𝗱 (+{days}𝗱)")

@router.callback_query(F.data.startswith("rv_"))
async def revoke_cb(callback: types.CallbackQuery):
    if not _is_owner(callback.from_user.id):
        await callback.answer("𝗢𝗻𝗹𝘆 𝘁𝗵𝗲 𝗼𝘄𝗻𝗲𝗿 𝗰𝗮𝗻 𝗿𝗲𝘃𝗼𝗸𝗲.", show_alert=True)
        return
    uid = int(callback.data.split("_", 1)[1])
    await asyncio.to_thread(_revoke_sync, uid)
    row, plan = await asyncio.to_thread(_user_sync, uid)
    text = _user_detail_text(row, plan)
    text += f"\n\n{_tg(ID_DECLINED, '❌')} 𝗔𝗰𝗰𝗲𝘀𝘀 𝗿𝗲𝘃𝗼𝗸𝗲𝗱."
    kb = _detail_kb(uid, row)
    try:
        await callback.message.edit_text(text, parse_mode="HTML", reply_markup=kb)
    except Exception:
        pass
    await callback.answer("𝗔𝗰𝗰𝗲𝘀𝘀 𝗿𝗲𝘃𝗼𝗸𝗲𝗱")

@router.callback_query(F.data.startswith("blk_"))
async def block_cb(callback: types.CallbackQuery):
    if not _is_owner(callback.from_user.id):
        await callback.answer("𝗡𝗼𝘁 𝗮𝘂𝘁𝗵𝗼𝗿𝗶𝘇𝗲𝗱.", show_alert=True)
        return
    uid = int(callback.data.split("_", 1)[1])
    if uid in OWNER_IDS:
        await callback.answer("𝗖𝗮𝗻𝗻𝗼𝘁 𝗯𝗹𝗼𝗰𝗸 𝘁𝗵𝗲 𝗼𝘄𝗻𝗲𝗿.", show_alert=True)
        return
    await asyncio.to_thread(_ban_user_sync, uid)
    row, plan = await asyncio.to_thread(_user_sync, uid)
    text = _user_detail_text(row, plan)
    text += f"\n\n{_tg(ID_STOP, '⛔')} 𝗨𝘀𝗲𝗿 𝗯𝗹𝗼𝗰𝗸𝗲𝗱."
    kb = _detail_kb(uid, row)
    try:
        await callback.message.edit_text(text, parse_mode="HTML", reply_markup=kb)
    except Exception:
        pass
    await callback.answer("𝗕𝗹𝗼𝗰𝗸𝗲𝗱")

@router.callback_query(F.data.startswith("unblk_"))
async def unblock_cb(callback: types.CallbackQuery):
    if not _is_owner(callback.from_user.id):
        await callback.answer("𝗡𝗼𝘁 𝗮𝘂𝘁𝗵𝗼𝗿𝗶𝘇𝗲𝗱.", show_alert=True)
        return
    uid = int(callback.data.split("_", 1)[1])
    await asyncio.to_thread(_unban_user_sync, uid)
    row, plan = await asyncio.to_thread(_user_sync, uid)
    text = _user_detail_text(row, plan)
    text += f"\n\n{_tg(ID_APPROVED, '✅')} 𝗨𝘀𝗲𝗿 𝘂𝗻𝗯𝗹𝗼𝗰𝗸𝗲𝗱."
    kb = _detail_kb(uid, row)
    try:
        await callback.message.edit_text(text, parse_mode="HTML", reply_markup=kb)
    except Exception:
        pass
    await callback.answer("𝗨𝗻𝗯𝗹𝗼𝗰𝗸𝗲𝗱")

@router.callback_query(F.data == "noop")
async def noop_cb(callback: types.CallbackQuery):
    await callback.answer()
