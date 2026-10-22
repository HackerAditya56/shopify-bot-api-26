# ═══════════════════════════════════════════════════════════════════════════════
# live_emoji.py — Animated plan badges for card result UI  |  CHK X WIZ
# ═══════════════════════════════════════════════════════════════════════════════
#
# Each plan maps to a fixed animated (premium) Telegram emoji. Because the badge
# is derived from the plan key, a user keeps the SAME emoji for their whole
# session (their plan never changes mid-session).

PLAN_EMOJI_IDS = {
    "SWIFT": "5384277294116284331",
    "TURBO": "5303400229549135579",
    "NITRO": "6136464120779638846",
    "APEX":  "6154611916678369390",
    "OWNER": "5379869575338812919",
}

DEFAULT_EMOJI_ID = "5956561749070057536"

DEV_EMOJI_ID = "5260681660189408650"

# Every known spelling of a plan (keys + branded display names) maps to its key.
_ALIASES = {
    "swift":    "SWIFT",
    "ꕶᴡ𝖎ғ†":   "SWIFT",
    "ꕶω𝖎f†":    "SWIFT",
    "turbo":    "TURBO",
    "Ƭᴜʀʙᴏ":   "TURBO",
    "Ƭυяʙσ":    "TURBO",
    "nitro":    "NITRO",
    "ɴɪⲧʀᴏ":   "NITRO",
    "Ⲛⲓⲧⲅⲟ":   "NITRO",
    "apex":     "APEX",
    "ꫝᴘᴇ✗":    "APEX",
    "owner":    "OWNER",
    "ᴏꪝɴᴇʀ":   "OWNER",
}

_LOOKUP = {}
for _alias, _plan in _ALIASES.items():
    _LOOKUP[_alias] = _plan
    _LOOKUP[_alias.casefold()] = _plan


def plan_badge(plan_name) -> str:
    """Return an animated <tg-emoji> badge for the user's plan."""
    raw = str(plan_name or "").strip()
    plan = _LOOKUP.get(raw) or _LOOKUP.get(raw.casefold())
    eid = PLAN_EMOJI_IDS.get(plan, DEFAULT_EMOJI_ID)
    return f'<tg-emoji emoji-id="{eid}">💎</tg-emoji>'


def dev_badge() -> str:
    """Return the dev link with the animated trophy beside it."""
    return (
        '<a href="https://t.me/broken_wiz">𒉼 𝔦 乙</a> '
        f'<tg-emoji emoji-id="{DEV_EMOJI_ID}">🏆</tg-emoji>'
    )