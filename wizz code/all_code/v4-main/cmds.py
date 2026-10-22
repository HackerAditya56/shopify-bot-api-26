from aiogram import Router, types
from aiogram.types import InlineKeyboardMarkup
import html
import logging

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)

router = Router()

# ============ CUSTOM EMOJI IDs ============
EMOJI_OK_ID = "4958610528588008305"   # ✅
BTN_CLOSE_EMOJI_ID = "5454350746407419714"  # animated close emoji

DEV_LINK = "https://t.me/broken_wiz"


def _lnk(symbol: str) -> str:
    """Wrap a decorative symbol so it opens the dev channel when tapped."""
    return f'<a href="{DEV_LINK}">{symbol}</a>'


def _b(text: str) -> str:
    """Bold a whole caption line."""
    return f"<b>{text}</b>"


# ============ CONFIGURATION ============
# Every section renders in one message: title, separator, then one line per command.
COMMAND_SECTIONS = [
    ("Single check", [
            ("/chk", "Stripe auth"),
            ("/b3", "Braintree auth"),
            ("/ch", "Chase auth"),
            ("/vbv", "Braintree VBV"),
            ("/st", "Stripe Charge 1$"),
            ("/sp", "Shopify 0.75$"),
            ("/hc", "Shopify 5.00$"),
            ("/pp", "Paypal key 1$"),
            ("/rz", "Razorpay"),
            ("/sk", "SK based"),
            ("/pg", "Payglocal 0.10$"),
            ("/nmi", "NMI charge 1$"),
    ]),
    ("Mass check", [
        ("/sh", "Shopify mass 0-5 USD (50 max)"),
        ("/msh", "Shopify mass 0-5 USD"),
        ("/mpp", "Paypal key 1$ mass"),
        ("/msk", "SK based mass"),
        ("/mrz", "Razorpay mass"),
    ]),
    ("Hitters", [
            ("/hit", "Whop hitter"),
            ("/stco", "Stripe checkout hitter"),
            ("/jio", "Jio hitter"),
    ]),
    ("Tools", [
        ("/bin", "Bin lookup"),
        ("/gen", "Generate cards"),
        ("/info", "Show user info"),
        ("/fb", "give feedback of your hits"),
        ("/plan", "Buy plan"),
        ("/scr", "Scrapper"),
    ]),
]

SEPARATOR = "━━━━━━━━━━━━━━"


def escape_html(text: str) -> str:
    """Escape HTML special characters"""
    if text is None:
        return ""
    return html.escape(str(text), quote=False)


def build_text() -> str:
    """Build the full single-page command caption."""
    try:
        ok = f'<tg-emoji emoji-id="{EMOJI_OK_ID}">✅</tg-emoji>'
        blocks = []
        for title, entries in COMMAND_SECTIONS:
            lines = [
                _b(f"{_lnk('[⌭]')} {escape_html(title)} {ok}"),
                SEPARATOR,
            ]
            for cmd, caption in entries:
                lines.append(_b(f"{escape_html(cmd)} ➺ {escape_html(caption)}"))
            blocks.append("\n".join(lines))
        return "\n\n".join(blocks)
    except Exception as e:
        logger.error(f"Error building cmds text: {e}")
        return "Error: Could not build command list."


def build_keyboard() -> InlineKeyboardMarkup:
    """Close button only, since everything fits on one page."""
    return InlineKeyboardMarkup(inline_keyboard=[[
        {
            "text": "Cʟᴏsᴇ",
            "callback_data": "cmds_close",
            "style": "danger",
            "icon_custom_emoji_id": BTN_CLOSE_EMOJI_ID,
        }
    ]])


# ============ HANDLERS ============
@router.message(lambda m: m.text and m.text.startswith("/cmds"))
async def cmds_command(message: types.Message):
    """Handle /cmds - shows the full command list on a single page."""
    await message.reply(
        text=build_text(),
        parse_mode="HTML",
        disable_web_page_preview=True,
        reply_markup=build_keyboard(),
    )


@router.callback_query(lambda c: c.data == "cmds_close")
async def handle_close(callback: types.CallbackQuery):
    """Handle close button - delete the message"""
    await callback.answer()
    try:
        await callback.message.delete()
    except Exception as e:
        logger.error(f"Error deleting message: {e}")