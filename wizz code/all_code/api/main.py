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


_STATUS_TRUE = ("ORDER_PAID", "INSUFFICIENT_FUNDS", "ORDER_SUBMITTED")

# The store accepted the submission but no terminal receipt has confirmed it.
# Treated as a terminal non-pending verdict per request.
_STATUS_PENDING = ("PROCESSING", "3DS_REQUIRED", "BOT_CHALLENGE")

# auto.py's normalize_card_result() rewrites these raw Shopify codes into the
# result vocabulary above (CAPTCHA_REQUIRED -> BOT_CHALLENGE,
# AUTHENTICATION_REQUIRED -> 3DS_REQUIRED). main.py receives the raw code, so
# the originals must be listed here too or the rewrite is invisible at the
# bucketing layer. Without this, a captcha challenge was reported as
# "approved" because CheckStatus.APPROVED is checked before the pending set.
_STATUS_PENDING_RAW = ("CAPTCHA_REQUIRED", "AUTHENTICATION_REQUIRED")

# Shop/transport faults that are worth another attempt rather than a verdict.
_STATUS_RETRYABLE = ("CHECKOUT_RETRYABLE", "RISK_BLOCKED")


def _outcome_for(res, response_str: str) -> str:
    """Stable outcome class for stats and for the caller.

    The CheckStatus attached by auto.py is authoritative: it comes from
    result_status_for(), which consults Shopify's own error taxonomy. Treating
    "anything that is not UNKNOWN" as a decline recorded every transient and
    processing fault -- TRANSIENT_ERROR, PUBLIC_PAYMENT_ERROR,
    DECISION_RULE_BLOCK, bot challenges -- as a card decline. That inflated
    the decline counter and hid the real cause behind a clean-looking number.
    """
    name = (getattr(getattr(res, "status", None), "name", "") or "").upper()
    u = (response_str or "").strip().upper()
    if u == "ORDER_PAID" or name == "CHARGED":
        return "charged"
    # Raw Shopify codes that auto.py normalises into _STATUS_PENDING. This must
    # be checked before the APPROVED branch below, because a captcha challenge
    # or a 3DS step both arrive with CheckStatus.APPROVED and were otherwise
    # counted as a clean approval -- the exact misreading the Outcome field
    # was added to eliminate.
    if u in _STATUS_PENDING_RAW:
        return "pending"
    if u in _STATUS_PENDING:
        return "pending"
    if name == "APPROVED" or u in _STATUS_TRUE:
        return "approved"
    if name == "DECLINED":
        return "declined"
    if u in _STATUS_RETRYABLE or name == "ERROR":
        return "errors"
    # A failed 3DS attempt is a completed negative answer from the issuer, not
    # an operational fault, so it must not be pooled with transient errors.
    if u == "3DS_FAILED" or u == "AUTHENTICATION_ERROR":
        return "declined"
    if u in ("", "UNKNOWN", "TIMEOUT") or u.startswith("UNKNOWN_ERROR"):
        return "errors"
    return "declined"


def _build_response(res, cc: str, site: str, proxy: str, proxy_dead: bool = False) -> dict:
    response_str = (res.status_code or "").strip() or _err_text(res.error) or "UNKNOWN"
    if response_str.upper() == "ORDER_PLACED":
        response_str = "ORDER_PAID"

    # Preserve a machine-readable pending/retryable code even when the result
    # carries a human message alongside it, so callers can still tell the
    # outcome class apart.
    if (res.status_code or "").strip().upper() in (_STATUS_PENDING + _STATUS_RETRYABLE):
        response_str = (res.status_code or "").strip().upper()

    status_bool = "true" if response_str.upper() in _STATUS_TRUE else "false"

    return {
        "Gateway":  (res.gateway or "Shopify Payments"),
        "Currency": (res.currency or "USD"),
        "Price":    _fmt_price(res.amount),
        "Proxy":    ("Dead" if proxy_dead else "Live") if proxy else "Dead",
        "Response": response_str,
        "Outcome":  _outcome_for(res, response_str),
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
    "pending":    0,
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
        # Routed through _build_response so every reply carries the same shape.
        # This hand-rolled dict was the one response missing "Outcome" and
        # "elapsed", so a caller could not tell a bad request from a card result
        # without special-casing on field presence.
        return JSONResponse(
            _build_response(_result_error(cc or "", site or "", "MISSING_PARAMETERS"),
                            cc or "", site or "", proxy or ""),
            status_code=400)

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
        # Ordering matters: charged wins over the Status bool, and pending is
        # checked before declined so an unconfirmed order is never recorded as
        # a decline. _build_response already resolved the class from the
        # authoritative CheckStatus, so fall back to "errors" rather than
        # guessing "declined".
        kind = resp.get("Outcome") or "errors"
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