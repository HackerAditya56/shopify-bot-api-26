import asyncio
import time
import aiohttp

# Updated URL
BINLIST_URL = "https://bins.antipublic.cc/bins/{}"

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# BIN CACHE — TTL cache for BIN lookups.
#
# Every card does a BIN lookup (first 6 digits). With 15 users
# running /msh simultaneously and many cards sharing the same BIN
# (e.g. all "424009xxxxxxxxxx" cards), the previous implementation
# fired the same external API request thousands of times.
#
# Cache benefits:
#   - Same BIN across the same /msh session → 1 lookup, 1999 cache hits
#   - Same BIN across different users → still cached (1h TTL)
#   - Uses the SHARED aiohttp session from shopify_api (no per-call
#     TCP+TLS+connection-pool tear-down).
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

_BIN_CACHE: dict = {}
_BIN_CACHE_TTL_S = 3600.0  # 1 hour
_BIN_LOCKS: dict = {}      # per-bin lock to coalesce concurrent fetches
_BIN_LOCKS_GUARD = asyncio.Lock()


def _bin_cache_get(bin6: str):
    """Return cached dict if fresh, else None."""
    entry = _BIN_CACHE.get(bin6)
    if not entry:
        return None
    if time.monotonic() - entry[1] > _BIN_CACHE_TTL_S:
        _BIN_CACHE.pop(bin6, None)
        return None
    return entry[0]


async def _get_bin_lock(bin6: str) -> asyncio.Lock:
    async with _BIN_LOCKS_GUARD:
        lock = _BIN_LOCKS.get(bin6)
        if lock is None:
            lock = asyncio.Lock()
            _BIN_LOCKS[bin6] = lock
        return lock


async def _fetch_bin_fresh(bin6: str) -> dict:
    """One HTTP fetch for a BIN; uses shared session if available."""
    url = BINLIST_URL.format(bin6)
    # Try shared session first (keeps connection pool warm, no setup cost).
    try:
        from shopify_api import _get_shared_session
        sess = await _get_shared_session()
    except Exception:
        sess = None

    try:
        if sess is not None:
            async with sess.get(url, timeout=aiohttp.ClientTimeout(total=8)) as resp:
                return await _parse_bin_response(resp)
        # Fallback: own short-lived session (only if shared isn't initialised)
        async with aiohttp.ClientSession() as session:
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=8)) as resp:
                return await _parse_bin_response(resp)
    except Exception as e:
        return {"error": f"Exception: {str(e)}"}


async def _parse_bin_response(resp) -> dict:
    """Map the API response into our normalised BIN dict."""
    if resp.status == 429:
        return {"error": "Rate limit exceeded. Try again later."}
    if resp.status == 404:
        return {"error": "BIN not found."}
    if resp.status != 200:
        return {"error": f"API request failed (status {resp.status})"}

    try:
        data = await resp.json()
    except Exception as e:
        return {"error": f"Invalid JSON: {e}"}

    return {
        "bin": data.get("bin"),
        "length": "N/A",
        "luhn": "N/A",
        "scheme": data.get("brand"),
        "type": data.get("type"),
        "brand": data.get("level"),
        "bank": data.get("bank"),
        "bank_phone": "N/A",
        "bank_url": "N/A",
        "country": data.get("country_name"),
        "country_emoji": data.get("country_flag"),
    }


async def get_bin_info(bin_number: str) -> dict:
    """
    Fetch BIN information from the antipublic.cc API.
    Results are cached per BIN for 1 hour (most /msh sessions reuse
    many of the same BIN prefixes).
    """
    if not bin_number or not bin_number.isdigit() or len(bin_number) < 6:
        return {"error": "Invalid BIN. Must be at least 6 digits."}

    bin6 = bin_number[:6]

    # Fast path: cached
    cached = _bin_cache_get(bin6)
    if cached is not None:
        return cached

    # Slow path: coalesce concurrent fetches for the same BIN via per-bin lock
    lock = await _get_bin_lock(bin6)
    async with lock:
        # Double-check after acquiring lock (another coroutine may have filled it)
        cached = _bin_cache_get(bin6)
        if cached is not None:
            return cached
        result = await _fetch_bin_fresh(bin6)
        _BIN_CACHE[bin6] = (result, time.monotonic())
        return result
