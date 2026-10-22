from aiogram import Router, F, types
from aiogram.filters import Command
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

router = Router()

# Premium Emoji IDs (provided by owner)
EMOJI_RED_TICK   = "6147565374289220368"
EMOJI_BLUE_TICK  = "5278628026416909103"
EMOJI_LIGHTNING  = "5350835008007324644"
EMOJI_STAR       = "5359686514697576863"
EMOJI_FIRE       = "6186076099764555777"
EMOJI_CROWN      = "6338940587193930733"
EMOJI_EPIC       = "5310296284874159738"
EMOJI_DRAGON     = "5226578782340553954"
EMOJI_GUN        = "5440406404936524730"
EMOJI_WHITE_STAR = "5247131412032670246"

# Per-page title emoji (key = title text -> emoji id)
TITLE_EMOJI = {
    "Shopify Gates": EMOJI_DRAGON,
    "Tools":         EMOJI_GUN,
    "Account":       EMOJI_WHITE_STAR,
}

PAGES = [
    {
        "title": "Shopify Gates",
        "entries": [
            {"gate": "Shopify 1$",         "cmd": "/sh",   "limit": "50",   "premium": False},
            {"gate": "Shopify Mass 0-20$", "cmd": "/msh",  "limit": "2000", "premium": True},
        ],
    },

    {
        "title": "Tools",
        "entries": [
            {"gate": "BIN Lookup",         "cmd": "/bin",        "limit": None, "premium": False},
        ],
    },
    {
        "title": "Account",
        "entries": [
            {"gate": "Statistics",         "cmd": "/leaderboard",  "limit": None, "premium": False},
            {"gate": "Account Info",       "cmd": "/info",   "limit": None, "premium": False},
            {"gate": "Claim Code",         "cmd": "/claim",  "limit": None, "premium": False},
            {"gate": "Give Feedback",      "cmd": "/fb",     "limit": None, "premium": False},
        ],
    },
]

TOTAL_PAGES = len(PAGES)
_SEP = "━━━━━━━━━━━━━━━━"


def _build_text(i: int) -> str:
    page = PAGES[i]
    title = page["title"]
    title_emoji_id = TITLE_EMOJI.get(title, EMOJI_STAR)
    lines = [
        f'<tg-emoji emoji-id="{title_emoji_id}">✨</tg-emoji> <b>{title}</b>  <code>{i + 1}/{TOTAL_PAGES}</code>',
        _SEP,
    ]
    for e in page["entries"]:
        if e["premium"]:
            tag = f'<tg-emoji emoji-id="{EMOJI_CROWN}">👑</tg-emoji>'
        else:
            tag = f'<tg-emoji emoji-id="{EMOJI_BLUE_TICK}">✅</tg-emoji>'
        limit_part = f"  ·  <i>{e['limit']}</i>" if e["limit"] is not None else ""
        lines.append(
            f'<tg-emoji emoji-id="{EMOJI_FIRE}">🔥</tg-emoji> '
            f'<b>{e["gate"]}</b>  ·  <code>{e["cmd"]}</code>{limit_part}  {tag}'
        )
    lines.append(_SEP)
    lines.append(
        f'<tg-emoji emoji-id="{EMOJI_CROWN}">👑</tg-emoji> '
        f'<b><a href="https://t.me/ShopifyxoBot">Rukia Shopify</a></b>'
    )
    return "\n".join(lines)

def _build_kb(i: int) -> InlineKeyboardMarkup:
    nav = []
    if i > 0:
        nav.append(InlineKeyboardButton(
            text="« Prev",
            callback_data=f"cmds_page_{i - 1}",
            style="danger",
            icon_custom_emoji_id=EMOJI_RED_TICK,
        ))
    nav.append(InlineKeyboardButton(
        text=f"{i + 1} / {TOTAL_PAGES}",
        callback_data="cmds_noop",
        style="primary",
        icon_custom_emoji_id=EMOJI_WHITE_STAR,
    ))
    if i < TOTAL_PAGES - 1:
        nav.append(InlineKeyboardButton(
            text="Next »",
            callback_data=f"cmds_page_{i + 1}",
            style="success",
            icon_custom_emoji_id=EMOJI_DRAGON,
        ))
    return InlineKeyboardMarkup(inline_keyboard=[nav])

# All texts and keyboards built once at import — zero runtime cost per button press
_CACHE: list[tuple[str, InlineKeyboardMarkup]] = [
    (_build_text(i), _build_kb(i)) for i in range(TOTAL_PAGES)
]

@router.message(Command("cmds"))
async def cmds_command(message: types.Message):
    text, kb = _CACHE[0]
    await message.reply(text=text, parse_mode="HTML", reply_markup=kb, disable_web_page_preview=True)

@router.callback_query(F.data.startswith("cmds_page_"))
async def cmds_page_callback(callback: types.CallbackQuery):
    await callback.answer()
    try:
        idx = int(callback.data[10:])
    except ValueError:
        return
    if not (0 <= idx < TOTAL_PAGES):
        return
    text, kb = _CACHE[idx]
    try:
        await callback.message.edit_text(text=text, parse_mode="HTML", reply_markup=kb, disable_web_page_preview=True)
    except Exception:
        pass

@router.callback_query(F.data == "cmds_noop")
async def cmds_noop(callback: types.CallbackQuery):
    await callback.answer()
