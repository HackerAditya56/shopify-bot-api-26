
"""
BMS (BookMyShow + PayU/Juspay) checker API — FastAPI endpoint for payu3.

Run on a no-display VPS under xvfb (headful Chrome is mandatory for Cloudflare):
    xvfb-run -a python3 payu3_api.py --port 9400

Usage:
    GET /bms?cc=5178058277710722|11|26|087&proxy=user:pass@host:port&key=ladle

Failure codes: PROXY_BANDWIDTH (webshare 402, free 1GB burned), PROXY_AUTH,
PROXY_ERROR, CLOUDFLARE_BLOCKED (403 after retries), INVALID_CARD.

Response (sanitized):
    {
      "cc": "5178058277710722|11|26|087",
      "response_code": "INSUFFICIENT_FUNDS",
      "response": "DECLINED",
      "real_response": "Insufficient funds",
      "amount": "180.00",
      "currency": "INR",
      "gateway": "BMS"
    }
"""
from __future__ import annotations

import asyncio
import os

from fastapi import FastAPI, Query
from fastapi.responses import JSONResponse

from payu3 import (run_bms_check, BmsResult, ProxyError, CloudflareBlocked,
                   preflight)

app = FastAPI(title="BMS Checker API (payu3)")

API_KEY = os.environ.get("BMS_API_KEY", "ladle")

# one headful browser at a time is heavy; cap concurrency per process
_BMS_SEM = asyncio.Semaphore(int(os.environ.get("BMS_MAX_CONCURRENCY", "2")))

# response_code -> bucket (CHARGED / APPROVED / DECLINED / ERROR)
_DECLINE_CODES = {
    "INSUFFICIENT_FUNDS", "DECLINED", "INCORRECT_CVV", "EXPIRED_CARD",
    "STOLEN_CARD", "INVALID_CARD", "NOT_ACCEPTED", "REFUSED_BY_ISSUER",
}
_APPROVE_CODES = {"3DS_REQUIRED", "CHALLENGE_REQUIRED", "APPROVED"}


def _err(cc: str, code: str, detail: str = "") -> dict:
    return {
        "cc": cc,
        "response_code": code,
        "response": "ERROR",
        "real_response": detail or "ERROR",
        "amount": "0.00",
        "currency": "INR",
        "gateway": "BMS",
    }


def _sanitize(res: BmsResult) -> dict:
    code = res.response_code or "ERROR"
    if code == "CHARGED":
        bucket = "CHARGED"
    elif code in _APPROVE_CODES:
        bucket = "APPROVED"
    elif code in _DECLINE_CODES:
        bucket = "DECLINED"
    else:
        bucket = "ERROR"
    return {
        "cc": getattr(res, "cc", ""),
        "response_code": code,
        "response": bucket,
        "real_response": res.real_response or "N/A",
        "amount": res.amount or "0.00",
        "currency": "INR",
        "gateway": "BMS",
    }


@app.get("/bms")
async def bms(
    cc: str = Query(default=""),
    proxy: str = Query(default=""),
    key: str = Query(default=""),
):
    if key != API_KEY:
        return JSONResponse({"error": "invalid or missing API key"}, status_code=401)
    if not cc:
        return JSONResponse({"error": "missing cc"}, status_code=400)

    proxy_url = ""
    if proxy:
        p = proxy.strip()
        if "://" not in p:
            p = "http://" + p
        proxy_url = p

    if not proxy_url and os.environ.get("BMS_REQUIRE_PROXY", "0") in ("1", "true", "yes"):
        return JSONResponse(_err(cc, "PROXY_ERROR", "no proxy supplied"), status_code=200)

    async with _BMS_SEM:
        try:
            res = await run_bms_check(cc, proxy_url)
            out = _sanitize(res)
            out["cc"] = cc
            return JSONResponse(out)
        except ProxyError as e:
            import logging
            logging.getLogger("bms").warning("proxy %s for %s: %s", e.reason, cc[:6], e.detail[:120])
            code = {"bandwidth": "PROXY_BANDWIDTH", "auth": "PROXY_AUTH"}.get(e.reason, "PROXY_ERROR")
            return JSONResponse(_err(cc, code, f"proxy {e.reason}"))
        except CloudflareBlocked as e:
            import logging
            logging.getLogger("bms").error("cf block for %s: %s", cc[:6], str(e)[:120])
            return JSONResponse(_err(cc, "CLOUDFLARE_BLOCKED", str(e)[:120]))
        except Exception as e:
            msg = str(e) or ""
            low = msg.lower()
            import logging
            logging.getLogger("bms").error("check failed for %s: %s", cc[:6], msg[:200])
            if "403" in low or "cloudflare" in low or "blocked" in low:
                code = "CLOUDFLARE_BLOCKED"
            elif "bandwidth" in low:
                code = "PROXY_BANDWIDTH"
            elif any(k in low for k in ("proxy", "curl", "timed out", "timeout",
                                        "connect", "resolve", "tunnel", "refused")):
                code = "PROXY_ERROR"
            elif "invalid card format" in low:
                code = "INVALID_CARD"
            else:
                code = "ERROR"
            return JSONResponse(_err(cc, code, msg[:160]))


@app.get("/proxycheck")
async def proxycheck(proxy: str = Query(default=""), key: str = Query(default="")):
    if key != API_KEY:
        return JSONResponse({"error": "invalid or missing API key"}, status_code=401)
    reason = preflight(proxy)
    return {"proxy": proxy[:40], "ok": reason in ("", "direct"), "reason": reason}


@app.get("/")
async def root():
    return {"ok": True, "api": "bms"}


if __name__ == "__main__":
    import argparse
    import uvicorn
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=int(os.environ.get("BMS_PORT", "9400")))
    ap.add_argument("--host", default="0.0.0.0")
    args = ap.parse_args()
    print(f"\n  BMS (payu3) FastAPI server: http://{args.host}:{args.port}\n")
    uvicorn.run(app, host=args.host, port=args.port, workers=1)
