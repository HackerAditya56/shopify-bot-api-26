import aiohttp
import time

_bin_cache = {}          # bin -> (result, timestamp)
_BIN_CACHE_TTL = 3600    # successful lookups cached 1h
_BIN_ERROR_TTL = 60      # failed lookups retried after 60s

ANTIPUBLIC_URL = "https://bins.antipublic.cc/bins/{}"
CHARGEBLAST_URL = "https://api.chargeblast.com/bin/{}"


def _flag_from_country_code(code: str) -> str:
    """Regional-indicator flag from a 2-letter ISO code (US -> 🇺🇸)."""
    if not code or len(code) != 2:
        return ""
    try:
        return "".join(chr(0x1F1E6 + (ord(c.upper()) - ord("A"))) for c in code)
    except Exception:
        return ""


def _normalize_antipublic(data: dict) -> dict:
    return {
        "bin": str(data.get("bin", "")),
        "length": "N/A",
        "luhn": "N/A",
        "scheme": data.get("brand", "N/A"),      # brand -> scheme (VISA / MASTERCARD)
        "type": data.get("type", "N/A"),          # DEBIT / CREDIT
        "brand": data.get("level", "N/A"),        # level -> brand (CLASSIC / WORLD)
        "bank": data.get("bank", "N/A"),
        "bank_phone": "N/A",
        "bank_url": "N/A",
        "country": data.get("country_name", "N/A"),
        "country_emoji": data.get("country_flag", ""),
    }


def _normalize_chargeblast(data: dict) -> dict:
    return {
        "bin": str(data.get("bin", "")),
        "length": "N/A",
        "luhn": "N/A",
        "scheme": data.get("brand", "N/A"),      # brand -> scheme
        "type": data.get("type", "N/A"),          # DEBIT / CREDIT
        "brand": "N/A",                           # chargeblast has no level field
        "bank": data.get("issuer", data.get("bank", "N/A")),
        "bank_phone": "N/A",
        "bank_url": "N/A",
        "country": data.get("country", "N/A"),
        "country_emoji": _flag_from_country_code(data.get("a2", "")),
    }


async def _fetch_json(session, url: str):
    async with session.get(url, timeout=10) as resp:
        if resp.status == 200:
            try:
                return await resp.json()
            except Exception:
                return None
        return None


async def get_bin_info(bin_number: str) -> dict:
    """Fetch BIN info. Primary: antipublic.cc. Falls back to chargeblast.com
    on rate-limit / failure so a 429 never blanks the result card.
    Results are cached (1h success / 60s failure) so mass checks with
    repeated BINs don't hammer the free BIN APIs into rate-limiting."""
    if not bin_number.isdigit() or len(bin_number) < 6:
        return {"error": "Invalid BIN. Must be at least 6 digits."}

    now = time.time()
    cached = _bin_cache.get(bin_number)
    if cached:
        result, ts = cached
        ttl = _BIN_ERROR_TTL if "error" in result else _BIN_CACHE_TTL
        if now - ts < ttl:
            return result

    async with aiohttp.ClientSession() as session:
        # 1) antipublic (primary)
        try:
            data = await _fetch_json(session, ANTIPUBLIC_URL.format(bin_number))
        except Exception:
            data = None
        if data is not None:
            result = _normalize_antipublic(data)
            _bin_cache[bin_number] = (result, time.time())
            return result

        # 2) chargeblast (fallback)
        try:
            data = await _fetch_json(session, CHARGEBLAST_URL.format(bin_number))
        except Exception:
            data = None
        if data is not None:
            result = _normalize_chargeblast(data)
            _bin_cache[bin_number] = (result, time.time())
            return result

        result = {"error": "BIN lookup failed (both APIs unavailable)."}
        _bin_cache[bin_number] = (result, time.time())
        return result
