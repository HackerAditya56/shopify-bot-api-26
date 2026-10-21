"""
BookMyShow (BMS) + PayU India checker API — FastAPI endpoint.

Usage:
    GET /payu2?cc=4001679034804536|01|2029|629&proxy=user:pass@host:port

Response (sanitized):
    {
      "cc": "4001679034804536|01|2029|629",
      "response_code": "CHARGED",
      "response": "CHARGED",
      "real_response": "Success",
      "amount": "260.00",
      "currency": "INR",
      "gateway": "BookMyShow"
    }
"""
from __future__ import annotations

import os

from fastapi import FastAPI, Query
from fastapi.responses import JSONResponse

from payu2 import run_bms_check, BmsResult

app = FastAPI(title="BookMyShow Checker API")

API_KEY = os.environ.get("PAYU_API_KEY", "ladle")


def _sanitize(res: BmsResult, cc: str) -> dict:
    return {
        "cc": cc,
        "response_code": res.response_code,
        "response": res.response_code,
        "real_response": res.real_response,
        "amount": res.amount,
        "currency": "INR",
        "gateway": "BookMyShow",
    }


@app.get("/payu2")
async def payu2(
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

    try:
        res = await run_bms_check(cc, proxy_url)
        return JSONResponse(_sanitize(res, cc))
    except Exception as e:
        import logging
        logging.getLogger("payu2").error("check failed for %s: %s", cc[:6], str(e)[:200])
        msg = str(e).lower()
        if any(k in msg for k in ("proxy", "curl", "timed out", "timeout", "connect", "resolve", "tunnel", "refused")):
            code = "PROXY_ERROR"
        elif "cloudflare" in msg or "clearance" in msg:
            code = "CLOUDFLARE_ERROR"
        elif "invalid card format" in msg:
            code = "INVALID_CARD"
        else:
            code = "ERROR"
        return JSONResponse({
            "cc": cc,
            "response_code": code,
            "response": "ERROR",
            "real_response": "ERROR",
            "amount": "0.00",
            "currency": "INR",
            "gateway": "BookMyShow",
        })


@app.get("/")
async def root():
    return {"ok": True, "api": "payu2"}


if __name__ == '__main__':
    import uvicorn
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument('--port', type=int, default=9400)
    ap.add_argument('--host', default='0.0.0.0')
    args = ap.parse_args()
    print(f"\n  FastAPI server: http://{args.host}:{args.port}\n")
    uvicorn.run(app, host=args.host, port=args.port, workers=1)
