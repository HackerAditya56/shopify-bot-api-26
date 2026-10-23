#!/usr/bin/env python3
"""
kali_api — async edition (v7/main_v2.py architecture).

Same routes as before, but the checker is the async engine (auto_async.py)
served by FastAPI/uvicorn instead of Flask threads:

    /sh              v7-compatible: key required, site optional (SITES_FILE)
    /shopii          legacy contract the bot uses (no key, ?site= required)
    /shopii/persisted, /shopiig, /shopii/graphql   aliases of /shopii
    /shopii/health   legacy health shape
    /health, /       {"ok": true, "api": "sh"}
    /stats           counters

Why it is calmer than the thread build: one request is one asyncio task,
so a check waiting on a socket does not pin a thread. Concurrency is bounded
by MAX_CONCURRENCY (or THREADS when MAX_CONCURRENCY=0) plus the load guard.

The old synchronous build is kept as main_legacy.py — run that if you need
to compare a verdict.
"""
from __future__ import annotations

import asyncio
import os
import random
import time

import uvicorn
from fastapi import FastAPI, Request, Query
from fastapi.responses import JSONResponse

import config as CFG
import auto_async
from auto import CheckStatus

# ── config shortcuts ─────────────────────────────────────────────────────
HOST = CFG.HOST
PORT = int(CFG.PORT)
API_KEYS = list(CFG.API_KEYS)
SITES_FILE = CFG.SITES_FILE
SITE_MODE = str(CFG.SITE_MODE).lower()
LOAD_MAX = float(CFG.LOAD_MAX_PERCENT)
LOAD_TTL = float(CFG.LOAD_TTL_SECONDS)
QUEUE_WAIT = int(CFG.QUEUE_WAIT)
CAPACITY_POLL = max(0.25, float(CFG.CAPACITY_POLL))
REQUEST_TIMEOUT = float(CFG.REQUEST_TIMEOUT)

_slots_n = int(CFG.MAX_CONCURRENCY) or max(1, int(CFG.THREADS))
_slots = asyncio.Semaphore(_slots_n)

_load_cache = {"ts": 0.0, "pct": 0.0}
_sites_cache = {"ts": 0.0, "sites": []}

_stats = {"active": 0, "total": 0, "charged": 0, "approved": 0,
          "pending": 0, "declined": 0, "errors": 0,
          "started": time.strftime("%Y-%m-%d %H:%M:%S")}


# ── helpers ──────────────────────────────────────────────────────────────
def _load_pct() -> float:
    now = time.time()
    if now - _load_cache["ts"] < LOAD_TTL:
        return _load_cache["pct"]
    pct = 0.0
    try:
        import psutil
        pct = max(psutil.cpu_percent(interval=0.0), psutil.virtual_memory().percent)
    except Exception:
        try:
            cores = os.cpu_count() or 1
            cpu = (os.getloadavg()[0] / cores) * 100.0
            mem = 0.0
            info = {}
            with open("/proc/meminfo") as f:
                for line in f:
                    k, _, rest = line.partition(":")
                    info[k.strip()] = rest.strip().split()[0]
            total = float(info.get("MemTotal", 1) or 1)
            avail = float(info.get("MemAvailable", 0) or 0)
            mem = (1.0 - avail / total) * 100.0
            pct = max(cpu, mem)
        except Exception:
            pct = 0.0
    _load_cache.update(ts=now, pct=pct)
    return pct


def _load_sites():
    try:
        st = os.stat(SITES_FILE)
    except OSError:
        return []
    if _sites_cache["ts"] == st.st_mtime and _sites_cache["sites"]:
        return _sites_cache["sites"]
    out = []
    try:
        with open(SITES_FILE, encoding="utf-8", errors="ignore") as f:
            for line in f:
                s = line.strip()
                if not s or s.startswith("#"):
                    continue
                if not s.startswith("http"):
                    s = "https://" + s
                out.append(s.rstrip("/"))
    except OSError:
        return []
    _sites_cache.update(ts=st.st_mtime, sites=out)
    return out


def _pick_site():
    sites = _load_sites()
    return random.choice(sites) if sites else ""


def _key_ok(candidate) -> bool:
    import hmac
    cand = str(candidate or "")
    return any(hmac.compare_digest(cand, str(k)) for k in API_KEYS)


async def _acquire():
    """Slot + load gate. Returns False only when QUEUE_WAIT expires."""
    deadline = None if QUEUE_WAIT <= 0 else time.time() + QUEUE_WAIT

    while _load_pct() >= LOAD_MAX:                 # box is hot -> park
        if deadline is not None and time.time() >= deadline:
            return False
        await asyncio.sleep(CAPACITY_POLL)

    try:
        if deadline is None:
            await _slots.acquire()
        else:
            await asyncio.wait_for(_slots.acquire(),
                                   timeout=max(0.1, deadline - time.time()))
    except asyncio.TimeoutError:
        return False
    return True


# ── response building (v7/main_v2.py contract) ───────────────────────────
_STATUS_TRUE = ("ORDER_PAID", "INSUFFICIENT_FUNDS", "ORDER_SUBMITTED")
_STATUS_PENDING = ("PROCESSING", "3DS_REQUIRED", "BOT_CHALLENGE")
_STATUS_PENDING_RAW = ("CAPTCHA_REQUIRED", "AUTHENTICATION_REQUIRED")
_STATUS_RETRYABLE = ("CHECKOUT_RETRYABLE", "RISK_BLOCKED")


def _fmt_price(s):
    if not s:
        return "0.00"
    try:
        return f"{float(s):.2f}"
    except (TypeError, ValueError):
        return str(s)


def _err_text(exc):
    if exc is None:
        return ""
    if getattr(exc, "args", None):
        return str(exc.args[0])
    return str(exc) or ""


def _outcome_for(res, response_str):
    name = (getattr(getattr(res, "status", None), "name", "") or "").upper()
    u = (response_str or "").strip().upper()
    if u == "ORDER_PAID" or name == "CHARGED":
        return "charged"
    if u in _STATUS_PENDING_RAW or u in _STATUS_PENDING:
        return "pending"
    if name == "APPROVED" or u in _STATUS_TRUE:
        return "approved"
    if name == "DECLINED":
        return "declined"
    if u in _STATUS_RETRYABLE or name == "ERROR":
        return "errors"
    if u in ("3DS_FAILED", "AUTHENTICATION_ERROR"):
        return "declined"
    if u in ("", "UNKNOWN", "TIMEOUT") or u.startswith("UNKNOWN_ERROR"):
        return "errors"
    return "declined"


def _build(res, cc, site, proxy, proxy_dead=False):
    response_str = (res.status_code or "").strip() or _err_text(res.error) or "UNKNOWN"
    if response_str.upper() == "ORDER_PLACED":
        response_str = "ORDER_PAID"
    if (res.status_code or "").strip().upper() in (_STATUS_PENDING + _STATUS_RETRYABLE):
        response_str = (res.status_code or "").strip().upper()
    return {
        "Gateway": (res.gateway or "Shopify Payments"),
        "Currency": (res.currency or "USD"),
        "Price": _fmt_price(res.amount),
        "Proxy": ("Dead" if proxy_dead else "Live") if proxy else "Dead",
        "Response": response_str,
        "Outcome": _outcome_for(res, response_str),
        "Status": "true" if response_str.upper() in _STATUS_TRUE else "false",
        "CC": cc,
        "site": site,
    }


def _result_error(cc, site, msg):
    res = auto_async.CheckResult(card=cc, shop_url=site, site_name=site,
                                 currency="USD", status=CheckStatus.ERROR)
    res.error = Exception(msg)
    return res


async def _check(cc: str, site: str, proxy: str):
    proxy_url = ""
    proxy_dead = False
    if proxy:
        try:
            proxy_url = auto_async.normalize_proxy(proxy)
        except Exception:
            return _build(_result_error(cc, site, "PROXY_FORMAT"), cc, site, proxy, proxy_dead=True)

    try:
        res = await asyncio.wait_for(
            auto_async.run_checkout_for_card_async(site, cc, proxy_url),
            timeout=REQUEST_TIMEOUT,
        )
    except asyncio.TimeoutError:
        return _build(_result_error(cc, site, "TIMEOUT"), cc, site, proxy)
    except Exception as e:
        msg = _err_text(e).replace("\n", " ")[:150]
        if proxy and any(s in msg.lower() for s in ("proxy", "curl:", "tunnel", "refused", "timed out", "connection")):
            proxy_dead = True
        return _build(_result_error(cc, site, msg), cc, site, proxy, proxy_dead=proxy_dead)

    if res.status == CheckStatus.ERROR and proxy and res.error:
        low = _err_text(res.error).lower()
        if any(s in low for s in ("proxy", "curl:", "tunnel", "refused", "timed out")):
            proxy_dead = True
    return _build(res, cc, site, proxy, proxy_dead=proxy_dead)


def _count(payload):
    resp = str(payload.get("Response", "")).upper()
    if resp == "ORDER_PAID":
        _stats["charged"] += 1
    elif resp in ("INSUFFICIENT_FUNDS", "APPROVED"):
        _stats["approved"] += 1
    elif resp in ("3DS_REQUIRED", "PROCESSING", "ORDER_SUBMITTED", "AUTHENTICATION_REQUIRED"):
        _stats["pending"] += 1
    elif resp in ("CARD_DECLINED", "DECLINED"):
        _stats["declined"] += 1
    else:
        _stats["errors"] += 1


# ── app ──────────────────────────────────────────────────────────────────
app = FastAPI(title="kali_api", docs_url=None, redoc_url=None)


@app.get("/health")
@app.get("/")
async def health():
    return {"ok": True, "api": "sh"}


@app.get("/shopii/health")
async def legacy_health():
    return {"status": "ok", "service": "shopify-gate"}


@app.get("/stats")
async def stats():
    return dict(_stats)


@app.api_route("/sh", methods=["GET", "POST"])
async def sh(request: Request,
             key: str | None = Query(None),
             cc: str | None = Query(None),
             proxy: str | None = Query(None),
             site: str | None = Query(None)):
    if request.method == "POST":
        try:
            body = await request.json()
            key = body.get("key", key)
            cc = body.get("cc", cc) or body.get("card", cc)
            proxy = body.get("proxy", proxy)
            site = body.get("site", site) or body.get("shop", site)
        except Exception:
            pass

    if not _key_ok(key):
        return JSONResponse({"error": "invalid or missing API key"}, status_code=401)

    if not cc:
        return JSONResponse(_v2_err("", site or "", "MISSING_PARAMETERS"), status_code=400)

    if SITE_MODE == "file" or not site:
        picked = _pick_site()
        if picked:
            site = picked
    if not site:
        return JSONResponse(_v2_err(cc, "", "NO_SITES_AVAILABLE"), status_code=503)

    if not site.startswith("http"):
        site = "https://" + site
    site = site.rstrip("/")

    if not await _acquire():
        return JSONResponse(_v2_err(cc, site, "SERVER_BUSY"), status_code=503)

    _stats["active"] += 1
    _stats["total"] += 1
    t0 = time.monotonic()
    try:
        payload = await _check(cc, site, proxy or "")
    finally:
        _stats["active"] -= 1
        _slots.release()

    payload["elapsed"] = round(time.monotonic() - t0, 2)
    _count(payload)
    return JSONResponse(payload)


@app.api_route("/shopii", methods=["GET", "POST"])
@app.api_route("/shopii/persisted", methods=["GET", "POST"])
@app.api_route("/shopiig", methods=["GET", "POST"])
@app.api_route("/shopii/graphql", methods=["GET", "POST"])
async def shopii(request: Request,
                 cc: str | None = Query(None),
                 proxy: str | None = Query(None),
                 site: str | None = Query(None),
                 proxy_urls: str | None = Query(None)):
    """Legacy contract the bot speaks: no key, site required."""
    if request.method == "POST":
        try:
            body = await request.json()
            cc = body.get("cc", cc) or body.get("card", cc)
            proxy = body.get("proxy", proxy)
            site = body.get("site", site) or body.get("shop", site)
        except Exception:
            pass

    if not cc or not site:
        return JSONResponse({
            "CC": cc or "", "Currency": "USD", "Gateway": "unknown",
            "Price": "0.00", "Proxy": "Dead",
            "Response": "MISSING_CARD" if not cc else "MISSING_SITE",
            "Status": "false",
        }, status_code=400)

    if SITE_MODE == "file":
        picked = _pick_site()
        if picked:
            site = picked
    if not site.startswith("http"):
        site = "https://" + site
    site = site.rstrip("/")

    if not await _acquire():
        return JSONResponse({"CC": cc, "Currency": "USD", "Gateway": "unknown",
                             "Price": "0.00", "Proxy": "Dead",
                             "Response": "SERVER_BUSY", "Status": "false"}, status_code=503)

    _stats["active"] += 1
    _stats["total"] += 1
    try:
        payload = await _check(cc, site, proxy or "")
    finally:
        _stats["active"] -= 1
        _slots.release()

    _count(payload)
    return JSONResponse(payload)


def _v2_err(cc, site, code):
    return {"Gateway": "Shopify Payments", "Currency": "USD", "Price": "0.00",
            "Proxy": "Dead", "Response": code, "Status": "false",
            "CC": cc or "", "site": site or ""}


if __name__ == "__main__":
    print(f"[kali_api] async | {len(API_KEYS)} key(s) | {SITES_FILE} "
          f"({len(_load_sites())} sites) | slots={_slots_n} | "
          f"load_guard={LOAD_MAX}% | timeout={REQUEST_TIMEOUT}s | site_mode={SITE_MODE}",
          flush=True)
    uvicorn.run("main:app", host=HOST, port=PORT,
                workers=max(1, int(CFG.WORKERS)), access_log=False,
                backlog=1024, timeout_keep_alive=60)
