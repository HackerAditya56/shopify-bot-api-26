import aiohttp
import time
import random
import csv
import os
import logging
import threading

ANTIPUBLIC_URL = "https://bins.antipublic.cc/bins/{}"
CHARGEBLAST_URL = "https://api.chargeblast.com/bin/{}"

_BIN_CSV_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "bin_cache.csv")
_SHOPIFY_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_PROXY_FILE = os.path.join(_SHOPIFY_DIR, "proxy.txt")
_CSV_TTL = 3 * 86400   # re-fetch stale CSV entries after 3 days

# in-memory fast cache
_bin_cache = {}          # bin -> (result, timestamp)
_BIN_CACHE_TTL = 3600    # successful lookups cached 1h in memory
_BIN_ERROR_TTL = 60      # failed lookups retried after 60s

# persistent CSV cache: bin -> full result dict
_csv_data = {}
_csv_loaded = False
_csv_lock = threading.Lock()


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


async def _fetch_json(session, url: str, proxy=None):
    try:
        async with session.get(url, timeout=10, proxy=proxy) as resp:
            if resp.status == 200:
                try:
                    return await resp.json()
                except Exception:
                    return None
            return None
    except Exception:
        return None


def _now_str() -> str:
    return str(int(time.time()))  # unix seconds (for TTL comparison)


def _normalize_proxy(p: str):
    p = (p or "").strip()
    if not p:
        return None
    if "://" not in p:
        p = "http://" + p
    return p


def _load_proxies() -> list:
    try:
        with open(_PROXY_FILE, encoding="utf-8", errors="ignore") as f:
            return [x for x in (_normalize_proxy(ln) for ln in f if ln.strip() and not ln.strip().startswith("#")) if x]
    except Exception:
        return []


def _load_csv() -> dict:
    """Load bin_cache.csv into {bin: result}. Empty dict if missing."""
    data = {}
    if not os.path.exists(_BIN_CSV_PATH):
        return data
    try:
        with open(_BIN_CSV_PATH, "r", newline="", encoding="utf-8") as f:
            for row in csv.DictReader(f):
                b = (row.get("bin") or "").strip()
                if not b:
                    continue
                data[b] = {
                    "bin": b,
                    "scheme": row.get("scheme") or "N/A",
                    "type": row.get("type") or "N/A",
                    "brand": row.get("brand") or "N/A",
                    "bank": row.get("bank") or "N/A",
                    "country": row.get("country") or "N/A",
                    "country_emoji": row.get("country_emoji") or "",
                    "last_update": row.get("last_update") or "",
                }
    except Exception as e:
        logging.warning(f"[BIN] CSV load error: {e}")
    return data


def _write_csv(data: dict):
    fieldnames = ["bin", "scheme", "type", "brand", "bank", "country", "country_emoji", "last_update"]
    try:
        with open(_BIN_CSV_PATH, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            for b in sorted(data.keys()):
                r = data[b]
                writer.writerow({
                    "bin": b,
                    "scheme": r.get("scheme", "N/A"),
                    "type": r.get("type", "N/A"),
                    "brand": r.get("brand", "N/A"),
                    "bank": r.get("bank", "N/A"),
                    "country": r.get("country", "N/A"),
                    "country_emoji": r.get("country_emoji", ""),
                    "last_update": r.get("last_update", ""),
                })
    except Exception as e:
        logging.warning(f"[BIN] CSV write error: {e}")


async def get_bin_info(bin_number: str) -> dict:
    """Fetch BIN info. Persistent CSV cache (bin_cache.csv) is the source of
    truth: if a BIN is already in the CSV it is returned without any API call.
    New BINs are fetched from chargeblast.com (primary, unlimited) and enriched
    from antipublic.cc (level/brand/type); on rate-limit the last cached CSV row
    is served instead of null, then results are written to the CSV."""
    if not bin_number.isdigit() or len(bin_number) < 6:
        return {"error": "Invalid BIN. Must be at least 6 digits."}

    now = time.time()

    # 1) in-memory fast cache
    cached = _bin_cache.get(bin_number)
    if cached:
        result, ts = cached
        ttl = _BIN_ERROR_TTL if "error" in result else _BIN_CACHE_TTL
        if now - ts < ttl:
            return result

    # 2) persistent CSV cache (lazy load once)
    global _csv_data, _csv_loaded
    if not _csv_loaded:
        with _csv_lock:
            if not _csv_loaded:
                _csv_data = _load_csv()
                _csv_loaded = True

    row = _csv_data.get(bin_number)
    if row is not None:
        try:
            last = int(float(row.get("last_update") or "0"))
        except (TypeError, ValueError):
            last = 0
        # re-fetch stale rows (old blank/rate-limited data) and blank rows (all N/A)
        blank = row.get("scheme", "N/A") == "N/A" and row.get("bank", "N/A") == "N/A"
        if not blank and (now - last) < _CSV_TTL:
            _bin_cache[bin_number] = (row, now)
            return row

    # 3) fetch from APIs via proxies (datacenter IPs are blocked by both APIs).
    #    chargeblast is PRIMARY (unlimited, no rate limit).  antipublic is only
    #    used to enrich the "level"/"type" fields when chargeblast answers.
    proxies = _load_proxies()
    trial = random.sample(proxies, min(5, len(proxies))) if proxies else []
    trial.append(None)  # direct as a last resort

    result = None
    async with aiohttp.ClientSession() as session:
        cb_data = None
        for proxy in trial:
            cb_data = await _fetch_json(session, CHARGEBLAST_URL.format(bin_number), proxy)
            if cb_data is not None:
                break

        ap_data = None
        for proxy in trial:
            ap_data = await _fetch_json(session, ANTIPUBLIC_URL.format(bin_number), proxy)
            if ap_data is not None:
                break

        if cb_data is not None:
            result = _normalize_chargeblast(cb_data)
            # enrich with antipublic level/brand + type when available
            if ap_data is not None:
                ap_norm = _normalize_antipublic(ap_data)
                if ap_norm.get("brand") != "N/A":
                    result["brand"] = ap_norm["brand"]
                if ap_norm.get("type") != "N/A":
                    result["type"] = ap_norm["type"]
        elif ap_data is not None:
            result = _normalize_antipublic(ap_data)
        elif row is not None:
            # Rate-limited on both APIs -> serve the last known CSV row instead
            # of null/error, so a rate limit never blanks the BIN output.
            result = dict(row)
            result["stale"] = True
            logging.warning(f"[BIN] rate-limited for {bin_number}, serving stale cache")
        else:
            result = {"error": "BIN lookup failed (both APIs unavailable)."}
            logging.warning(f"[BIN] lookup failed for {bin_number} (both APIs down/rate-limited)")

    _bin_cache[bin_number] = (result, time.time())

    # persist successful results to CSV (with last_update); errors are retried
    if "error" not in result:
        result["last_update"] = _now_str()
        with _csv_lock:
            _csv_data[bin_number] = result
            _write_csv(_csv_data)

    return result
