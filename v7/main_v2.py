from __future__ import annotations

import asyncio
import ctypes
import datetime
import gc
import hmac
import logging
import os
import sys
import threading
import time
import warnings
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Optional

warnings.filterwarnings("ignore")

_here = Path(__file__).resolve().parent
if str(_here) not in sys.path:
    sys.path.insert(0, str(_here))

import uvicorn
from fastapi import FastAPI, Request, Query
from fastapi.responses import JSONResponse

import auto_async_v2
from auto import CheckStatus
import config as cfg

# ══════════════════════════════════════════════════════════════
#  v2 test files — leave the path blank; paste your full path + filename.
#  e.g. SITES_FILE = "/home/user/sites.txt"   (one shop URL per line)
#       PROXY_FILE = "/home/user/proxies.txt" (one proxy per line)
# ══════════════════════════════════════════════════════════════
SITES_FILE = os.environ.get("V2_SITES_FILE", "site.txt")    # one shop URL per line
PROXY_FILE = os.environ.get("V2_PROXY_FILE", "proxy.txt")    # user:pass@host:port
TEST_CC    = os.environ.get("V2_TEST_CC", "4000000000000002")  # test card

try:
    import psutil
    _MEMORY_CHECK = True
except ImportError:
    psutil = None
    _MEMORY_CHECK = False

logging.basicConfig(level=logging.INFO, format="%(message)s",
                    handlers=[logging.StreamHandler()])
_log = logging.getLogger("api")

# ══════════════════════════════════════════════════════════════
#  Result helpers
# ══════════════════════════════════════════════════════════════

def _fmt_price(s: object) -> str:
    """Format any amount string as exactly 2 decimals; passthrough if unparseable."""
    if not s:
        return "0.00"
    try:
        return f"{float(s):.2f}"
    except (ValueError, TypeError):
        return str(s)


def _err_text(exc: BaseException | None) -> str:
    if exc is None:
        return ""
    if exc.args and exc.args[0]:
        return str(exc.args[0])
    return str(exc) or ""


_STATUS_TRUE = ("ORDER_PAID", "INSUFFICIENT_FUNDS")


def _build_response(res, cc: str, site: str, proxy: str, proxy_dead: bool = False) -> dict:
    response_str = (res.status_code or "").strip() or _err_text(res.error) or "UNKNOWN"
    if response_str.upper() == "ORDER_PLACED":
        response_str = "ORDER_PAID"

    status_bool = "true" if response_str.upper() in _STATUS_TRUE else "false"

    return {
        "Gateway":  (res.gateway or "Shopify Payments"),
        "Currency": (res.currency or "USD"),
        "Price":    _fmt_price(res.amount),
        "Proxy":    ("Dead" if proxy_dead else "Live") if proxy else "Dead",
        "Response": response_str,
        "Status":   status_bool,
        "CC":       cc,
        "site":     site,
    }


# ══════════════════════════════════════════════════════════════
#  Async card check
# ══════════════════════════════════════════════════════════════

# ──────────────────────────────────────────────────────────────
#  Retry / error handling — on failure, swap proxy / site / session
# ──────────────────────────────────────────────────────────────
SITE_FILE = os.environ.get("SITE_FILE", str(_here / "site.txt"))
PROXY_FILE = os.environ.get("PROXY_FILE", str(_here / "proxy.txt"))
CHECK_MAX_RETRIES = int(os.environ.get("CHECK_MAX_RETRIES", "4"))
# Total time budget for the retry loop (seconds). Keeps a card from
# retrying forever and blowing past the upstream request timeout.
CHECK_TOTAL_BUDGET = float(os.environ.get("CHECK_TOTAL_BUDGET", "110"))

_site_blacklist = {}     # site -> blacklisted_until_ts
_failed_proxies = {}     # proxy -> fail_count

_REAL_RESULTS = (
    "CARD_DECLINED", "ORDER_PAID", "INSUFFICIENT_FUNDS", "3DS_REQUIRED",
    "INVALID_PAYMENT_METHOD", "INVALID_CVC", "INCORRECT_CVC", "EXPIRED",
    "INVALID_PURCHASE_TYPE", "TEST_MODE_LIVE_CARD", "DECISION_RULE_BLOCK",
    "AMOUNT_TOO_SMALL", "TRANSACTION_NOT_ALLOWED", "RESTRICTED_CARD",
    "DO_NOT_HONOR", "GENERIC_DECLINE", "PROCESSING_ERROR", "PICK_UP_CARD",
)


# price/country retry ladder (ported from main(6).py) — recover the two most
# common "shop is fine but this attempt needs a different product/country" errors.
PRICE_LADDER = (0.50, 2.0, 5.0, 10.0)
COUNTRY_LADDER = ("US", "CA", "GB", "AU")


def _load_pool(path: str) -> list:
    try:
        with open(path, encoding="utf-8", errors="ignore") as f:
            return [ln.strip() for ln in f if ln.strip() and not ln.strip().startswith("#")]
    except Exception:
        return []


def _is_proxy_err(text: str) -> bool:
    m = (text or "").lower()
    return any(k in m for k in (
        "could not resolve proxy", "curl:", "proxy", "tunnel", "refused",
        "timed out", "timeout", "connection", "dns", "name resolution"))


def _is_site_err(text: str) -> bool:
    m = (text or "").lower()
    return any(k in m for k in (
        "no available products", "catalog blocked", "no valid products",
        "not shopify", "second address line", "shop configuration",
        "404", "401", "subtotal", "minimum", "order subtotal"))


def _next_proxy(preferred: str, exclude: set) -> str:
    pool = _load_pool(PROXY_FILE)
    # drop proxies that have failed repeatedly (module-level counter)
    bad = {p for p, n in _failed_proxies.items() if n >= 3}
    exclude = exclude | bad
    if preferred and preferred not in exclude:
        return preferred
    for p in pool:
        if p not in exclude:
            return p
    return preferred or ""


def _next_site(preferred: str, exclude: set) -> str:
    now = time.time()
    pool = _load_pool(SITE_FILE)
    # honor the module-level blacklist (auto-removed bad sites, 10 min TTL)
    exclude = exclude | {s for s, ts in _site_blacklist.items() if ts > now}
    if preferred and preferred not in exclude:
        return preferred
    for s in pool:
        if s not in exclude:
            return s
    return preferred or ""


_site_idx = 0
_site_idx_lock = threading.Lock()


def _pick_site() -> str:
    """Round-robin a non-blacklisted site from site.txt (the API's own pool).

    The caller-passed `site` is ignored entirely — the API always serves from
    this pool so a single bad site can't be pinned or hammered by a caller.
    """
    global _site_idx
    pool = _load_pool(SITE_FILE)
    if not pool:
        return ""
    now = time.time()
    with _site_idx_lock:
        for _ in range(len(pool)):
            s = pool[_site_idx % len(pool)]
            _site_idx = (_site_idx + 1) % len(pool)
            if _site_blacklist.get(s, 0) <= now:
                return s
        return pool[0]


async def check_card_async(cc: str, site: str, proxy: str) -> dict:
    cur_site = site or ""
    cur_proxy = proxy or ""
    failed_proxies = set()
    bad_sites = set()
    last_res = None
    last_err = "retries exhausted"
    proxy_dead = False

    start_time = time.monotonic()
    price_idx = 0
    country_idx = 0
    for attempt in range(CHECK_MAX_RETRIES + 1):
        if time.monotonic() - start_time > CHECK_TOTAL_BUDGET:
            break
        proxy_url = ""
        if cur_proxy:
            try:
                proxy_url = auto_async_v2.normalize_proxy(cur_proxy)
            except Exception:
                pass

        try:
            res = await auto_async_v2.run_checkout_for_card_async(
                cur_site, cc, proxy_url,
                min_price=PRICE_LADDER[price_idx],
                country_override=COUNTRY_LADDER[country_idx])
        except Exception as e:
            err_msg = _err_text(e).replace("\n", " ")[:150]
            last_err = err_msg
            _log.info("%s|EXCEPTION|%s", cc, err_msg)
            return _build_response(_result_error(cc, cur_site, err_msg), cc=cc,
                                   site=cur_site, proxy=cur_proxy, proxy_dead=True)

        status_code = (res.status_code or "").strip().upper()
        err_text = _err_text(res.error) or ""

        # proxy/transport error -> surface DIRECTLY (proxy is caller-supplied,
        # so a dead proxy is the caller's problem, not silently retried)
        if _is_proxy_err(err_text):
            _failed_proxies[cur_proxy] = _failed_proxies.get(cur_proxy, 0) + 1
            _log.info("%s|PROXY_ERROR|%s|%s", cc, _err_text(res.error)[:80], _fmt_price(res.amount))
            return _build_response(res, cc=cc, site=cur_site, proxy=cur_proxy, proxy_dead=True)

        # site error (in status_code OR error text) -> blacklist + fresh site
        if _is_site_err(status_code) or _is_site_err(err_text):
            _site_blacklist[cur_site] = time.time() + 600
            bad_sites.add(cur_site)
            cur_site = _next_site(cur_site, bad_sites)
            last_res = res
            continue

        # real result (declined / charged / approved) -> return
        if res.status != CheckStatus.ERROR or status_code in _REAL_RESULTS:
            response_str = status_code or _err_text(res.error) or "UNKNOWN"
            _log.info("%s|%s|%s|%s", cc, response_str, _fmt_price(res.amount), res.currency or "?")
            return _build_response(res, cc=cc, site=cur_site, proxy=cur_proxy, proxy_dead=proxy_dead)

        # price/country ladder — retry same site with a pricier product / different country
        if "PAYMENTS_UNACCEPTABLE_PAYMENT_AMOUNT" in (status_code + " " + err_text).upper():
            if price_idx + 1 < len(PRICE_LADDER):
                price_idx += 1
                last_res = res
                continue
        if "DELIVERY_NO_DELIVERY_STRATEGY" in (status_code + " " + err_text).upper():
            if country_idx + 1 < len(COUNTRY_LADDER):
                country_idx += 1
                last_res = res
                continue

        # any other step failure -> legacy REST fallback, then direct, then fresh site
        # (1) legacy_checkout (captcha-free REST path)
        try:
            leg = await auto_async_v2.legacy_checkout_entry(cur_site, cc, proxy_url)
        except Exception:
            leg = None
        if leg and leg.get("status") in ("charged", "approved", "declined"):
            _leg = {"charged": auto_async_v2.CheckStatus.CHARGED,
                    "approved": auto_async_v2.CheckStatus.APPROVED,
                    "declined": auto_async_v2.CheckStatus.DECLINED}[leg["status"]]
            _leg_res = auto_async_v2.CheckResult(
                card=cc, status=_leg, status_code=(leg.get("code") or "CARD_DECLINED").upper(),
                amount="0.00", currency="USD", gateway=leg.get("gate", "") or "shopify_payments",
                site_name=cur_site.replace("https://", "").replace("http://", ""),
                shop_url=cur_site, receipt_url="", error=None, retryable=False)
            _log.info("%s|%s|%s|%s", cc, (leg.get("code") or "CARD_DECLINED").upper(), "0.00", "USD")
            return _build_response(_leg_res, cc=cc, site=cur_site, proxy=cur_proxy, proxy_dead=False)

        # (2) fresh site
        bad_sites.add(cur_site)
        cur_site = _next_site(cur_site, bad_sites)
        last_res = res

    if last_res is not None:
        response_str = (last_res.status_code or "").strip() or _err_text(last_res.error) or "UNKNOWN"
        _log.info("%s|%s|%s|%s", cc, response_str, _fmt_price(last_res.amount), last_res.currency or "?")
        return _build_response(last_res, cc=cc, site=cur_site, proxy=cur_proxy, proxy_dead=proxy_dead)

    _log.info("%s|%s|%s|%s", cc, last_err, "0.00", "")
    return _build_response(res=_result_error(cc, cur_site, last_err), cc=cc,
                           site=cur_site, proxy=cur_proxy, proxy_dead=proxy_dead)


def _result_error(cc: str, site: str, msg: str):
    res = auto_async_v2.CheckResult(card=cc, shop_url=site, site_name=site,
                                 currency="USD", status=CheckStatus.ERROR)
    res.error = Exception(msg)
    return res


# ══════════════════════════════════════════════════════════════
#  Stats & memory guard
# ══════════════════════════════════════════════════════════════

_stats = {
    "active":     0,
    "total":      0,
    "charged":    0,
    "approved":   0,
    "declined":   0,
    "errors":     0,
    "started":    time.strftime("%Y-%m-%d %H:%M:%S"),
}
_stats_lock = threading.Lock()
_mem_cache: dict = {"val": False, "ts": 0.0}


def _key_valid(key: str | None) -> bool:
    """Constant-time master-key check. `ladle` -> unlimited; anything else rejected."""
    if not key:
        return False
    return hmac.compare_digest(str(key), cfg.CHECKER_API_KEY)


def _is_memory_exceeded() -> bool:
    if not _MEMORY_CHECK or psutil is None:
        return False
    now = time.time()
    if now - _mem_cache["ts"] < 5.0:
        return _mem_cache["val"]
    try:
        val = psutil.virtual_memory().percent >= 95
    except Exception:
        val = False
    _mem_cache["val"] = val
    _mem_cache["ts"]  = now
    return val


# ══════════════════════════════════════════════════════════════
#  FastAPI app
# ══════════════════════════════════════════════════════════════

def _mem_trim_loop(interval: float = 45.0):
    """Periodically gc.collect() + malloc_trim to return freed heap to the OS.

    Runs in a daemon thread per worker process. Pure memory management —
    never touches checkout logic, so card results are identical. The trim only
    helps AFTER a burst: it lets RSS drop when concurrency falls, so the next
    burst doesn't start near the RAM ceiling."""
    try:
        libc = ctypes.CDLL("libc.so.6")
        _trim = libc.malloc_trim
        _trim.argtypes = [ctypes.c_size_t]
        _trim.restype = ctypes.c_int
    except Exception:
        _trim = None
    while True:
        time.sleep(interval)
        try:
            gc.collect()
            if _trim is not None:
                _trim(0)
        except Exception:
            pass


def _start_mem_trim():
    """Start the trim thread if MEM_TRIM=1 (default on)."""
    if os.environ.get("MEM_TRIM", "1") != "1":
        return
    t = threading.Thread(target=_mem_trim_loop, name="mem-trim", daemon=True)
    t.start()


@asynccontextmanager
async def _lifespan(app: FastAPI):
    _start_mem_trim()
    yield

app = FastAPI(title="Shopify Checker API v2", docs_url=None, redoc_url=None,
              lifespan=_lifespan)


IP_LOG_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "ip.txt")
_ip_log_lock = threading.Lock()


def _load_seen_ips() -> set:
    try:
        with open(IP_LOG_FILE, encoding="utf-8") as f:
            return {line.strip() for line in f if line.strip()}
    except Exception:
        return set()


_seen_ips = _load_seen_ips()


def _log_new_ip(ip: str):
    """Append an IP to ip.txt only if it hasn't been seen before."""
    if not ip or ip == "unknown":
        return
    global _seen_ips
    with _ip_log_lock:
        if ip in _seen_ips:
            return
        _seen_ips.add(ip)
        try:
            with open(IP_LOG_FILE, "a", encoding="utf-8") as f:
                f.write(ip + "\n")
        except Exception:
            pass


@app.middleware("http")
async def _log_client_ip(request: Request, call_next):
    """Record the requester IP to ip.txt (new IPs only, /sh endpoint only)."""
    if request.url.path.rstrip("/") == "/sh":
        ip = request.client.host if request.client else "unknown"
        xff = request.headers.get("x-forwarded-for")
        if xff:
            ip = xff.split(",")[0].strip()
        _log_new_ip(ip)
    return await call_next(request)


@app.get("/")
@app.get("/health")
async def route_health():
    return JSONResponse({"ok": True, "api": "sh"})


@app.get("/stats")
async def route_stats():
    with _stats_lock:
        return JSONResponse(dict(_stats))


@app.api_route("/sh", methods=["GET", "POST"])
async def route_sh(
    request: Request,
    cc:    Optional[str] = Query(None),
    proxy: Optional[str] = Query(None),
    key:   Optional[str] = Query(None),
):
    # `site` is intentionally NOT accepted: the API always draws from its own
    # site pool (site.txt), so a caller-supplied site is dropped.
    if request.method == "POST":
        try:
            body  = await request.json()
            key   = body.get("key", key)
            cc    = body.get("cc", cc)
            proxy = body.get("proxy", proxy)
        except Exception:
            pass

    if not _key_valid(key):
        return JSONResponse({"error": "invalid or missing API key"}, status_code=401)

    if _is_memory_exceeded():
        return JSONResponse(_build_response(_result_error(cc or "", "",
                                          "Server is busy"), cc or "", "", proxy or ""),
                            status_code=503)

    if not cc:
        return JSONResponse({
            "Gateway":  "Shopify Payments",
            "Currency": "USD",
            "Price":    "0.00",
            "Proxy":    "Dead",
            "Response": "MISSING_PARAMETERS",
            "Status":   "false",
            "CC":       cc or "",
            "site":     "",
        }, status_code=400)

    site = _pick_site()
    if not site:
        return JSONResponse({
            "Gateway":  "Shopify Payments",
            "Currency": "USD",
            "Price":    "0.00",
            "Proxy":    "Dead",
            "Response": "NO_SITES_AVAILABLE",
            "Status":   "false",
            "CC":       cc,
            "site":     "",
        }, status_code=503)

    if not site.startswith("http"):
        site = "https://" + site
    site = site.rstrip("/")

    with _stats_lock:
        _stats["active"] += 1
        _stats["total"]  += 1

    t0   = time.monotonic()
    resp = None
    try:
        resp = await asyncio.wait_for(
            check_card_async(cc, site, proxy or ""),
            timeout=cfg.REQUEST_TIMEOUT,
        )
    except asyncio.TimeoutError:
        with _stats_lock:
            _stats["errors"] += 1
            _stats["active"] -= 1
        return JSONResponse({
            "Gateway":  "Shopify Payments",
            "Currency": "USD",
            "Price":    "0.00",
            "Proxy":    "Dead",
            "Response": "TIMEOUT",
            "Status":   "false",
            "CC":       cc,
            "site":     site,
        })
    except Exception as e:
        with _stats_lock:
            _stats["errors"] += 1
            _stats["active"] -= 1
        return JSONResponse(_build_response(
            _result_error(cc, site, str(e)[:150]), cc, site, proxy or ""))

    with _stats_lock:
        _stats["active"] -= 1
        kind = "charged" if resp["Response"] == "ORDER_PAID" else \
               "approved" if resp["Status"] == "true" else \
               "declined" if resp["Response"] != "UNKNOWN" else "errors"
        _stats[kind] += 1

    resp["elapsed"] = round(time.monotonic() - t0, 2)
    return JSONResponse(resp)


# ══════════════════════════════════════════════════════════════
#  Entry point
# ══════════════════════════════════════════════════════════════

# ══════════════════════════════════════════════════════════════
#  v2 theory-test runner: warmup + tracking + score, against sites/proxies
# ══════════════════════════════════════════════════════════════

def _load_lines(path: str) -> list:
    if not path:
        return []
    try:
        with open(path, encoding="utf-8", errors="replace") as f:
            return [ln.strip() for ln in f if ln.strip() and not ln.strip().startswith("#")]
    except FileNotFoundError:
        _log.warning("file not found: %s", path)
        return []


async def test_v2():
    sites   = _load_lines(SITES_FILE)
    proxies = _load_lines(PROXY_FILE)
    if not sites:
        _log.error("V2_SITES_FILE is blank or empty — paste a path to a .txt of shop URLs.")
        return
    if not proxies:
        _log.warning("V2_PROXY_FILE blank — running direct (no proxy).")
        proxies = [""]

    for i, site in enumerate(sites):
        if not site.startswith("http"):
            site = "https://" + site
        site = site.rstrip("/")
        proxy = proxies[i % len(proxies)] if proxies else ""
        _log.info("── [%d/%d] %s (proxy %s)", i + 1, len(sites), site, proxy or "direct")
        try:
            resp = await asyncio.wait_for(
                check_card_async(TEST_CC, site, proxy),
                timeout=cfg.REQUEST_TIMEOUT,
            )
        except asyncio.TimeoutError:
            resp = {"Response": "TIMEOUT", "Status": "false", "CC": TEST_CC, "site": site}
        except Exception as e:
            resp = {"Response": str(e)[:100], "Status": "false", "CC": TEST_CC, "site": site}
        _log.info("     -> %s | %s | %s", resp.get("Response"), resp.get("Gateway"), resp.get("Price"))


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "test":
        _log.info("v2 theory test: sites=%s proxy=%s cc=%s", SITES_FILE or "(blank)", PROXY_FILE or "(blank)", TEST_CC)
        asyncio.run(test_v2())
        sys.exit(0)

    print("━" * 50)
    print("  Shopify Checker API v2")
    print(f"  Host         : {cfg.HOST}")
    print(f"  Port         : {cfg.PORT}")
    print(f"  Workers      : {cfg.WORKERS}")
    print(f"  Endpoint     : /sh")
    print(f"  Health       : /health")
    print(f"  Timeout      : {cfg.REQUEST_TIMEOUT}s")
    print("━" * 50)

    uvicorn.run(
        "main_v2:app",
        host=cfg.HOST,
        port=cfg.PORT,
        workers=cfg.WORKERS,
        access_log=False,
        backlog=1024,
        timeout_keep_alive=cfg.UA_KEEP_ALIVE,
        limit_max_requests=None,
    )