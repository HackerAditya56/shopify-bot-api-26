from __future__ import annotations

import asyncio
import datetime
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

import auto_async
from auto import CheckStatus
import config as cfg

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


_STATUS_TRUE = ("ORDER_PAID",)


def _build_response(res, cc: str, site: str, proxy: str, proxy_dead: bool = False) -> dict:
    response_str = (res.status_code or "").strip() or _err_text(res.error) or "UNKNOWN"
    if response_str.upper() == "ORDER_PLACED":
        response_str = "ORDER_PAID"
    # Never leak raw Shopify human-readable messages ("Payment flexibility terms
    # ID mismatch", "does not ship to ...", etc.) as the Response. Only stable
    # step labels and known codes pass through.
    if not response_str.startswith("Step "):
        low = response_str.lower()
        if any(w in low for w in (" mismatch", "cannot", "terms ", " checkout ",
                                   " delivery ", " payment ", " ship to",
                                   "strategy found", "serialized", "renegotiation")):
            response_str = "GENERIC_ERROR"

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

async def check_card_async(cc: str, site: str, proxy: str) -> dict:
    proxy_url = ""
    if proxy:
        try:
            proxy_url = auto_async.normalize_proxy(proxy)
        except Exception:
            pass

    proxy_dead = False
    try:
        res = await auto_async.run_checkout_for_card_async(site, cc, proxy_url)
    except Exception as e:
        err_msg = _err_text(e).replace("\n", " ")[:150]
        if proxy and any(s in err_msg.lower() for s in
                         ("proxy", "curl:", "tunnel", "refused", "timed out", "connection")):
            proxy_dead = True
        return _build_response(res=_result_error(cc, site, err_msg), cc=cc,
                               site=site, proxy=proxy, proxy_dead=proxy_dead)

    if res.status == CheckStatus.ERROR and proxy and res.error:
        err_msg = _err_text(res.error).lower()
        if any(s in err_msg for s in ("proxy", "curl:", "tunnel", "refused", "timed out")):
            proxy_dead = True

    response_str = (res.status_code or "").strip() or _err_text(res.error) or "UNKNOWN"
    _log.info("%s|%s|%s|%s", cc, response_str, _fmt_price(res.amount), res.currency or "?")
    return _build_response(res, cc=cc, site=site, proxy=proxy, proxy_dead=proxy_dead)


def _result_error(cc: str, site: str, msg: str):
    res = auto_async.CheckResult(card=cc, shop_url=site, site_name=site,
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

@asynccontextmanager
async def _lifespan(app: FastAPI):
    yield

app = FastAPI(title="Shopify Checker API", docs_url=None, redoc_url=None,
              lifespan=_lifespan)


@app.get("/")
@app.get("/health")
async def route_health():
    return JSONResponse({"ok": True, "api": "shopii"})


@app.get("/stats")
async def route_stats():
    with _stats_lock:
        return JSONResponse(dict(_stats))


@app.api_route("/shopii", methods=["GET", "POST"])
async def route_shopii(
    request: Request,
    cc:    Optional[str] = Query(None),
    site:  Optional[str] = Query(None),
    proxy: Optional[str] = Query(None),
):
    if _is_memory_exceeded():
        return JSONResponse(_build_response(_result_error(cc or "", site or "",
                                          "Server is busy"), cc or "", site or "", proxy or ""),
                            status_code=503)
    if request.method == "POST":
        try:
            body  = await request.json()
            cc    = body.get("cc",    cc)
            site  = body.get("site",  site)
            proxy = body.get("proxy", proxy)
        except Exception:
            pass

    if not cc or not site:
        return JSONResponse({
            "Gateway":  "Shopify Payments",
            "Currency": "USD",
            "Price":    "0.00",
            "Proxy":    "Dead",
            "Response": "MISSING_PARAMETERS",
            "Status":   "false",
            "CC":       cc or "",
            "site":     site or "",
        }, status_code=400)

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
               "errors" if resp["Response"] in ("UNKNOWN", "REJECTED", "TIMEOUT",
                                                 "GENERIC_ERROR", "PROCESSING") \
                 else "declined"
        _stats[kind] += 1

    resp["elapsed"] = round(time.monotonic() - t0, 2)
    return JSONResponse(resp)


# ══════════════════════════════════════════════════════════════
#  Entry point
# ══════════════════════════════════════════════════════════════

if __name__ == "__main__":
    print("━" * 50)
    print("  Shopify Checker API")
    print(f"  Host         : {cfg.HOST}")
    print(f"  Port         : {cfg.PORT}")
    print(f"  Workers      : {cfg.WORKERS}")
    print(f"  Endpoint     : /shopii")
    print(f"  Health       : /health")
    print(f"  Timeout      : {cfg.REQUEST_TIMEOUT}s")
    print("━" * 50)

    uvicorn.run(
        "main:app",
        host=cfg.HOST,
        port=cfg.PORT,
        workers=cfg.WORKERS,
        access_log=False,
        backlog=1024,
        timeout_keep_alive=cfg.UA_KEEP_ALIVE,
        limit_max_requests=None,
    )