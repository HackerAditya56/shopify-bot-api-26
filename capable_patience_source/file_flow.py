"""file_flow.py — auto-detect dropped files (proxy vs CC) and route them.

Proxy file  -> selection: Global (excl Razorpay) / Razorpay only.
CC file     -> cook (year format) -> mass gates -> gate runs its own
               charged-only / approved+charged selection window.
Manual /msh /mrz etc. commands keep working unchanged.
"""
import asyncio
import os
import re
import logging
from aiogram import types, F, Router
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

from mass_gates._tg_helpers import safe_reply
from proxy import parse_proxy_input, check_proxy_live
from mass_gates.msh import extract_cards_from_text, luhn_check

router = Router()

RZ_API = os.environ.get("RZ_API", "http://127.0.0.1:9000")
MAX_FILE = 8 * 1024 * 1024  # 8MB

ID_APPROVED = "6044254523009012231"
ID_DECLINED = "5893081007153746175"
ID_CHARGED = "5359719332542718652"
ID_WARNING = "6255910249362885846"
ID_STAR = "6136275172283391020"
ID_GATEWAY = "5085022089103016925"
ID_LOCK = "5258419835922030550"
ID_TOP = "5463071033256848094"
ID_STOP = "5247149163132493357"
ID_WALLET = "5424976816530014958"

def _tg(eid, fb):
    return f'<tg-emoji emoji-id="{eid}">{fb}</tg-emoji>'

def _btn(text, data, style="primary", emoji=None):
    kw = {"text": text, "callback_data": data, "style": style}
    if emoji:
        kw["icon_custom_emoji_id"] = emoji
    return InlineKeyboardButton(**kw)

_STATE = {}  # user_id -> dict

GATES = {
    "msh": ("𝗦𝗵𝗼𝗽𝗶𝗳𝘆 𝗠𝗮𝘀𝘀", "/msh"),
    "mrz": ("𝗥𝗮𝘇𝗼𝗿𝗽𝗮𝘆 𝗠𝗮𝘀𝘀", "/mrz"),
    "mst": ("𝗦𝘁𝗿𝗶𝗽𝗲 𝗠𝗮𝘀𝘀", "/mst"),
    "mauth": ("𝗔𝘂𝘁𝗵 𝗠𝗮𝘀𝘀", "/mauth"),
    "mchk": ("𝗖𝗵𝗸 𝗠𝗮𝘀𝘀", "/mchk"),
    "mstripe": ("𝗦𝘁𝗿𝗶𝗽𝗲 𝟮 𝗠𝗮𝘀𝘀", "/mstripe"),
}


def _detect_type(text: str) -> str:
    lines = [l.strip() for l in text.splitlines() if l.strip() and not l.strip().startswith("#")]
    if not lines:
        return "none"
    proxy = 0
    cc = 0
    cc_re = re.compile(r'^\d{13,19}\s*[|/:=\s]\s*\d{1,2}\s*[|/:]\s*\d{2,4}\s*[|/:]\s*\d{3,4}')
    for ln in lines[:500]:
        if parse_proxy_input(ln):
            proxy += 1
        if cc_re.match(ln):
            cc += 1
    if proxy > 0 and proxy >= cc:
        return "proxy"
    if cc > 0 and cc > proxy:
        return "cc"
    return "none"


@router.message(F.document)
async def on_file(message: types.Message):
    # skip command captions — /msh etc. handle their own files
    cap = (message.caption or "").strip()
    if cap.startswith("/"):
        return
    doc = message.document
    if not doc:
        return
    if doc.file_size and doc.file_size > MAX_FILE:
        await safe_reply(message, f'{_tg(ID_DECLINED, "❌")} 𝗙𝗶𝗹𝗲 𝘁𝗼𝗼 𝗹𝗮𝗿𝗴𝗲 (𝗺𝗮𝘅 𝟴𝗠𝗕).', parse_mode="HTML")
        return
    try:
        fi = await message.bot.get_file(doc.file_id)
        data = await message.bot.download_file(fi.file_path)
        content = data.read().decode("utf-8", errors="ignore") if hasattr(data, "read") else str(data)
    except Exception as e:
        logging.error(f"[file_flow] read: {e}")
        await safe_reply(message, f'{_tg(ID_DECLINED, "❌")} 𝗘𝗿𝗿𝗼𝗿 𝗿𝗲𝗮𝗱𝗶𝗻𝗴 𝗳𝗶𝗹𝗲.', parse_mode="HTML")
        return
    if not content.strip():
        await safe_reply(message, f'{_tg(ID_WARNING, "⚠️")} 𝗘𝗺𝗽𝘁𝘆 𝗳𝗶𝗹𝗲.', parse_mode="HTML")
        return

    typ = _detect_type(content)
    uid = message.from_user.id

    if typ == "proxy":
        _STATE[uid] = {"type": "proxy", "raw": content}
        text = (
            f'{_tg(ID_WALLET, "👛")} <b>𝗣𝗥𝗢𝗫𝗬 𝗙𝗜𝗟𝗘 𝗗𝗘𝗧𝗘𝗖𝗧𝗘𝗗</b>\n'
            f"━━━━━━━━━━━━━━━━\n"
            f'{_tg(ID_CHARGED, "💎")} 𝗪𝗵𝗲𝗿𝗲 𝘁𝗼 𝗮𝗱𝗱 𝘁𝗵𝗲𝗺?\n\n'
        )
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [
                _btn("𝗚𝗹𝗼𝗯𝗮𝗹 (𝗲𝘅𝗰𝗹 𝗥𝗭)", "ff_global", "success", ID_APPROVED),
                _btn("𝗥𝗮𝘇𝗼𝗿𝗽𝗮𝘆 𝗼𝗻𝗹𝘆", "ff_rz", "primary", ID_CHARGED),
            ],
            [_btn("𝗖𝗮𝗻𝗰𝗲𝗹", "ff_cancel", "danger", ID_STOP)],
        ])
        await message.answer(text, parse_mode="HTML", reply_markup=kb)
        return

    if typ == "cc":
        cards = extract_cards_from_text(content)
        if not cards:
            await safe_reply(message, f'{_tg(ID_WARNING, "⚠️")} 𝗡𝗼 𝗰𝗮𝗿𝗱𝘀 𝗳𝗼𝘂𝗻𝗱 𝗶𝗻 𝘁𝗵𝗲 𝗳𝗶𝗹𝗲.', parse_mode="HTML")
            return
        _STATE[uid] = {"type": "cc", "cards": cards}
        text = (
            f'{_tg(ID_CHARGED, "💎")} <b>𝗖𝗖 𝗙𝗜𝗟𝗘 𝗗𝗘𝗧𝗘𝗖𝗧𝗘𝗗</b>\n'
            f"━━━━━━━━━━━━━━━━\n"
            f'{_tg(ID_STAR, "⭐")} 𝗖𝗮𝗿𝗱𝘀 ➠ <code>{len(cards)}</code>\n\n'
            f'{_tg(ID_GATEWAY, "⚡")} 𝗖𝗵𝗼𝗼𝘀𝗲 𝘆𝗲𝗮𝗿 𝗳𝗼𝗿𝗺𝗮𝘁 (𝗰𝗼𝗼𝗸):\n'
        )
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [
                _btn("𝗬𝗬 (𝟮-𝗱𝗶𝗴𝗶𝘁)", "ff_cook_yy", "success", ID_APPROVED),
                _btn("𝗬𝗬𝗬𝗬 (𝟰-𝗱𝗶𝗴𝗶𝘁)", "ff_cook_yyyy", "primary", ID_CHARGED),
            ],
            [_btn("𝗖𝗮𝗻𝗰𝗲𝗹", "ff_cancel", "danger", ID_STOP)],
        ])
        await message.answer(text, parse_mode="HTML", reply_markup=kb)
        return

    await safe_reply(message, f'{_tg(ID_WARNING, "⚠️")} 𝗖𝗼𝘂𝗹𝗱 𝗻𝗼𝘁 𝗱𝗲𝘁𝗲𝗰𝘁 𝗽𝗿𝗼𝘅𝘆 𝗼𝗿 𝗖𝗖 𝗶𝗻 𝘁𝗵𝗶𝘀 𝗳𝗶𝗹𝗲.', parse_mode="HTML")


@router.callback_query(F.data.startswith("ff_"))
async def ff_cb(callback: types.CallbackQuery):
    uid = callback.from_user.id
    data = callback.data
    st = _STATE.get(uid)

    if data == "ff_cancel":
        _STATE.pop(uid, None)
        try:
            await callback.message.edit_text(f'{_tg(ID_DECLINED, "❌")} 𝗖𝗮𝗻𝗰𝗲𝗹𝗹𝗲𝗱.', parse_mode="HTML")
        except Exception:
            pass
        await callback.answer()
        return

    if not st:
        await callback.answer("𝗦𝗲𝘀𝘀𝗶𝗼𝗻 𝗲𝘅𝗽𝗶𝗿𝗲𝗱.", show_alert=True)
        return

    if data == "ff_global":
        await _add_global(callback, st)
    elif data == "ff_rz":
        await _add_rz(callback, st)
    elif data in ("ff_cook_yy", "ff_cook_yyyy"):
        st["cook"] = "yy" if data == "ff_cook_yy" else "yyyy"
        await _show_gates(callback, st)
    elif data.startswith("ff_gate_"):
        gate = data.split("_", 2)[2]
        await _run_gate(callback, st, gate)
    await callback.answer()


async def _add_global(callback, st):
    from proxy import process_proxies_background
    raw = st.get("raw", "")
    valid = []
    for ln in raw.splitlines():
        ln = ln.strip()
        if not ln or ln.startswith("#"):
            continue
        p = parse_proxy_input(ln)
        if p:
            valid.append(p)
    if not valid:
        await callback.message.edit_text(f'{_tg(ID_DECLINED, "❌")} 𝗡𝗼 𝘃𝗮𝗹𝗶𝗱 𝗽𝗿𝗼𝘅𝗶𝗲𝘀 𝗶𝗻 𝘁𝗵𝗲 𝗳𝗶𝗹𝗲.', parse_mode="HTML")
        _STATE.pop(callback.from_user.id, None)
        return
    await callback.message.edit_text(f'{_tg(ID_GATEWAY, "⚡")} 𝗖𝗵𝗲𝗰𝗸𝗶𝗻𝗴 {len(valid)} 𝗽𝗿𝗼𝘅𝗶𝗲𝘀 𝗮𝗻𝗱 𝗮𝗱𝗱𝗶𝗻𝗴 𝘁𝗼 𝗚𝗹𝗼𝗯𝗮𝗹 𝗽𝗼𝗼𝗹...', parse_mode="HTML")
    _STATE.pop(callback.from_user.id, None)
    asyncio.create_task(process_proxies_background(callback.bot, callback.message, valid, "𝗙𝗶𝗹𝗲 𝗱𝗿𝗼𝗽"))


async def _add_rz(callback, st):
    import aiohttp
    raw = st.get("raw", "")
    rz_proxies = []
    for ln in raw.splitlines():
        ln = ln.strip()
        if not ln or ln.startswith("#"):
            continue
        p = parse_proxy_input(ln)
        if p:
            rz_proxies.append(f"{p['ip']}:{p['port']}:{p['user']}:{p['password']}")
    if not rz_proxies:
        await callback.message.edit_text(f'{_tg(ID_DECLINED, "❌")} 𝗡𝗼 𝘃𝗮𝗹𝗶𝗱 𝗽𝗿𝗼𝘅𝗶𝗲𝘀 𝗶𝗻 𝘁𝗵𝗲 𝗳𝗶𝗹𝗲.', parse_mode="HTML")
        _STATE.pop(callback.from_user.id, None)
        return
    await callback.message.edit_text(f'{_tg(ID_GATEWAY, "⚡")} 𝗖𝗵𝗲𝗰𝗸𝗶𝗻𝗴 {len(rz_proxies)} 𝗮𝗴𝗮𝗶𝗻𝘀𝘁 𝗥𝗮𝘇𝗼𝗿𝗽𝗮𝘆 + 𝗮𝗱𝗱𝗶𝗻𝗴 𝘁𝗼 𝗥𝗭 𝗽𝗼𝗼𝗹...', parse_mode="HTML")
    _STATE.pop(callback.from_user.id, None)
    try:
        async with aiohttp.ClientSession() as s:
            async with s.post(f"{RZ_API}/check-proxy", json={"proxies": rz_proxies}, timeout=aiohttp.ClientTimeout(total=300)) as resp:
                j = await resp.json()
        live = j.get("live", 0)
        blocked = j.get("blocked", 0)
        dead = j.get("dead", 0)
        text = (
            f'{_tg(ID_APPROVED, "✅")} <b>𝗥𝗭 𝗣𝗼𝗼𝗹 𝗨𝗽𝗱𝗮𝘁𝗲𝗱</b>\n'
            f"━━━━━━━━━━━━━━━━\n"
            f'{_tg(ID_APPROVED, "✅")} 𝗟𝗶𝘃𝗲 ➠ <code>{live}</code>\n'
            f'{_tg(ID_STOP, "⛔")} 𝗕𝗹𝗼𝗰𝗸𝗲𝗱 ➠ <code>{blocked}</code>\n'
            f'{_tg(ID_DECLINED, "❌")} 𝗗𝗲𝗮𝗱 ➠ <code>{dead}</code>\n\n'
            f"𝗟𝗶𝘃𝗲 𝗼𝗻𝗲𝘀 𝗮𝗿𝗲 𝗻𝗼𝘄 𝗶𝗻 𝘁𝗵𝗲 𝗥𝗮𝘇𝗼𝗿𝗽𝗮𝘆 𝗽𝗼𝗼𝗹 (/rzp)."
        )
        await callback.message.edit_text(text, parse_mode="HTML")
    except Exception as e:
        logging.error(f"[file_flow] rz add: {e}")
        await callback.message.edit_text(f'{_tg(ID_DECLINED, "❌")} 𝗥𝗭 𝗔𝗣𝗜 𝗲𝗿𝗿𝗼𝗿: {str(e)[:80]}', parse_mode="HTML")


async def _show_gates(callback, st):
    cards = st.get("cards", [])
    cook = st.get("cook", "yy")
    rows = []
    for key, (label, cmd) in GATES.items():
        rows.append([_btn(label, f"ff_gate_{key}", "primary", ID_GATEWAY)])
    rows.append([_btn("𝗖𝗮𝗻𝗰𝗲𝗹", "ff_cancel", "danger", ID_STOP)])
    kb = InlineKeyboardMarkup(inline_keyboard=rows)
    text = (
        f'{_tg(ID_CHARGED, "💎")} <b>𝗖𝗛𝗢𝗢𝗦𝗘 𝗠𝗔𝗦𝗦 𝗚𝗔𝗧𝗘</b>\n'
        f"━━━━━━━━━━━━━━━━\n"
        f'{_tg(ID_STAR, "⭐")} 𝗖𝗮𝗿𝗱𝘀 ➠ <code>{len(cards)}</code>\n'
        f'{_tg(ID_GATEWAY, "⚡")} 𝗬𝗲𝗮𝗿 ➠ <b>{cook.upper()}</b>\n\n'
        f"𝗣𝗶𝗰𝗸 𝘁𝗵𝗲 𝗴𝗮𝘁𝗲 — 𝗶𝘁 𝘄𝗶𝗹𝗹 𝗮𝘀𝗸 𝗰𝗵𝗮𝗿𝗴𝗲𝗱-𝗼𝗻𝗹𝘆 𝗼𝗿 𝗮𝗽𝗽𝗿𝗼𝘃𝗲𝗱+𝗰𝗵𝗮𝗿𝗴𝗲𝗱."
    )
    await callback.message.edit_text(text, parse_mode="HTML", reply_markup=kb)


async def _run_gate(callback, st, gate):
    cards = st.get("cards", [])
    cook = st.get("cook", "yy")
    _STATE.pop(callback.from_user.id, None)
    from mass_gates.msh import msh_command
    from mass_gates.mrz import mrz_command
    from mass_gates.mst import mst_command
    from mass_gates.mauth import mauth_command
    from mass_gates.mchk import mchk_command
    from mass_gates.mstripe import mstripe_command
    handlers = {
        "msh": msh_command,
        "mrz": mrz_command,
        "mst": mst_command,
        "mauth": mauth_command,
        "mchk": mchk_command,
        "mstripe": mstripe_command,
    }
    h = handlers.get(gate)
    if not h:
        await callback.answer("𝗨𝗻𝗸𝗻𝗼𝘄𝗻 𝗴𝗮𝘁𝗲.", show_alert=True)
        return

    # normalize cards to the chosen year format
    out = []
    for c in cards:
        p = c.split("|")
        if len(p) != 4:
            continue
        cc, mm, yy, cvv = p
        if cook == "yyyy" and len(yy) == 2:
            yy = "20" + yy
        elif cook == "yy" and len(yy) == 4:
            yy = yy[2:]
        out.append(f"{cc}|{mm}|{yy}|{cvv}")
    cards_text = "\n".join(out)

    await callback.message.edit_text(f'{_tg(ID_GATEWAY, "⚡")} 𝗦𝘁𝗮𝗿𝘁𝗶𝗻𝗴 {GATES[gate][0]}...', parse_mode="HTML")

    fake = _FakeMsg(callback.bot, callback.from_user, callback.message.chat.id)
    fake.text = f"/{gate} {cards_text}"
    await h(fake)


class _FakeMsg:
    def __init__(self, bot, user, chat_id):
        self.bot = bot
        self.from_user = user
        self.chat = types.Chat(id=chat_id, type="private")
        self.chat_id = chat_id
        self.text = ""
        self.caption = None
        self.document = None
        self.reply_to_message = None
        self.message_id = 0

    async def reply(self, *a, **kw):
        kw.pop("reply_to_message_id", None)
        return await self.bot.send_message(chat_id=self.chat_id, *a, **kw)

    async def answer(self, *a, **kw):
        kw.pop("reply_to_message_id", None)
        return await self.bot.send_message(chat_id=self.chat_id, *a, **kw)

    async def reply_document(self, *a, **kw):
        kw.pop("reply_to_message_id", None)
        return await self.bot.send_document(chat_id=self.chat_id, *a, **kw)

    async def answer_photo(self, *a, **kw):
        return await self.bot.send_photo(chat_id=self.chat_id, *a, **kw)

    async def edit_text(self, *a, **kw):
        return None
