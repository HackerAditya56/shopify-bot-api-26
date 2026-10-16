"""
/rzg — Razorpay gate monitor.

Shows live pool state: proxies (total/cooldown/usable), sites (total/cooldown),
active mass checks, WAF 403 count, server-error count, total checkouts.
Refresh button re-renders in place.
"""
import os
import json
import time
import asyncio
import urllib.request
import urllib.parse

from aiogram import types, F, Router
from aiogram.types import InlineKeyboardMarkup

from database import OWNER_IDS
import rz_rotation
from mass_gates._batch_common import BATCH_SESSIONS
from mass_gates._tg_helpers import safe_reply
from proxy import (_tg, _btn, ID_APPROVED, ID_DECLINED, ID_CHARGED, ID_WARNING,
                  ID_STAR, ID_GATEWAY, ID_TOP, ID_LOCK, ID_FIRE, ID_WALLET)

router = Router()
RZ_API = os.environ.get("RZ_API", "http://127.0.0.1:9000")


def _api_get(path: str):
    try:
        with urllib.request.urlopen(f"{RZ_API}{path}", timeout=10) as resp:
            return json.loads(resp.read().decode())
    except Exception:
        return {}


def _build_text() -> str:
    st = rz_rotation.status()

    active_sessions = [s for s in BATCH_SESSIONS.values() if s.get("status") == "𝗖𝗵𝗲𝗰𝗸𝗶𝗻𝗴..."]
    n_active = len(active_sessions)
    in_flight = sum(s.get("checked", 0) for s in active_sessions)
    in_total = sum(s.get("total", 0) for s in active_sessions)

    api_stats = _api_get("/stats").get("stats", {})
    waf_403 = int(api_stats.get("waf_403", 0))
    rzp_5xx = int(api_stats.get("rzp_5xx", 0))
    total_ck = int(api_stats.get("total_checkouts", 0))

    proxy_cd = int(_api_get("/pool-status").get("cooldown", 0))
    site_cd = int(_api_get("/pool-status").get("site_cooldown", 0))

    active_line = (f"{_tg(ID_GATEWAY, '⚡')} 𝐀𝐜𝐭𝐢𝐯𝐞 𝐌𝐚𝐬𝐬 ➠ <b>{n_active}</b> "
                   f"({'/'.join([str(in_flight), str(in_total)]) if n_active else '0/0'} cards)")

    return (
        f"{_tg(ID_CHARGED, '💎')} <b>𝐑𝐀𝐙𝐎𝐑𝐏𝐀𝐘 𝐆𝐀𝐓𝐄</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━━\n"
        f"{active_line}\n"
        f"{_tg(ID_WALLET, '👛')} 𝐏𝐫𝐨𝐱𝐢𝐞𝐬 ➠ <b>{st['proxies_total']}</b> "
        f"({_tg(ID_APPROVED, '✅')} {st['proxies_usable']} · {_tg(ID_DECLINED, '❌')} {st['proxies_paused']})\n"
        f"{_tg(ID_TOP, '🔝')} 𝐀𝐏𝐈 𝐏𝐫𝐨𝐱𝐲 𝐂𝐨𝐨𝐥𝐝𝐨𝐰𝐧 ➠ <b>{proxy_cd}</b>\n"
        f"{_tg(ID_LOCK, '🔐')} 𝐒𝐢𝐭𝐞𝐬 ➠ <b>{st['sites_total']}</b> "
        f"({_tg(ID_APPROVED, '✅')} {st['sites_usable']} · {_tg(ID_DECLINED, '❌')} {st['sites_error_cooldown'] + st['sites_paused']})\n"
        f"{_tg(ID_TOP, '🔝')} 𝐀𝐏𝐈 𝐒𝐢𝐭𝐞 𝐂𝐨𝐨𝐥𝐝𝐨𝐰𝐧 ➠ <b>{site_cd}</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━━\n"
        f"{_tg(ID_FIRE, '🔥')} 𝐓𝐨𝐭𝐚𝐥 𝐂𝐡𝐞𝐜𝐤𝐨𝐮𝐭𝐬 ➠ <b>{total_ck}</b>\n"
        f"{_tg(ID_DECLINED, '⛔')} 𝐖𝐀𝐅 𝟒𝟎𝟑 ➠ <b>{waf_403}</b>\n"
        f"{_tg(ID_WARNING, '⚠️')} 𝐒𝐞𝐫𝐯𝐞𝐫 𝐄𝐫𝐫𝐨𝐫 ➠ <b>{st['server_error_count']}</b> "
        f"(𝟓𝐱𝐱: {rzp_5xx})\n"
        f"━━━━━━━━━━━━━━━━━━━━━\n"
        f"{_tg(ID_STAR, '⭐')} 𝐔𝐩𝐝𝐚𝐭𝐞𝐝 ➠ <code>{time.strftime('%H:%M:%S')}</code>"
    )


def _build_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [_btn("𝗥𝗲𝗳𝗿𝗲𝘀𝗵", "rzg_refresh", "success", ID_APPROVED)],
    ])


@router.message(F.text.startswith("/rzg"))
async def rzg_command(message: types.Message):
    if message.from_user.id not in OWNER_IDS:
        await safe_reply(message, f"{_tg(ID_DECLINED, '❌')} 𝗡𝗼𝘁 𝗮𝘂𝘁𝗵𝗼𝗿𝗶𝘇𝗲𝗱.", parse_mode="HTML")
        return
    text = await asyncio.to_thread(_build_text)
    await safe_reply(message, text, parse_mode="HTML", reply_markup=_build_kb())


@router.callback_query(F.data == "rzg_refresh")
async def rzg_refresh_cb(callback: types.CallbackQuery):
    if callback.from_user.id not in OWNER_IDS:
        await callback.answer("𝗡𝗼𝘁 𝗮𝘂𝘁𝗵𝗼𝗿𝗶𝘇𝗲𝗱.", show_alert=True)
        return
    text = await asyncio.to_thread(_build_text)
    try:
        await callback.message.edit_text(text, parse_mode="HTML", reply_markup=_build_kb())
    except Exception:
        await callback.message.answer(text, parse_mode="HTML", reply_markup=_build_kb())
    await callback.answer("𝗥𝗲𝗳𝗿𝗲𝘀𝗵𝗲𝗱")
