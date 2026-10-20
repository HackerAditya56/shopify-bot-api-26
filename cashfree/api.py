
"""
Cashfree checker API — FastAPI endpoint (fixed ₹230, debit-only).

Usage:
    GET /cashfree?cc=4001679034804536|01|2029|629&proxy=user:pass@host:port

Response (sanitized):
    {"cc": ..., "response_code": ..., "response": ..., "real_response": ..., "amount": "230.00", "currency": "INR", "gateway": "Cashfree"}
"""
from __future__ import annotations
import os
from fastapi import FastAPI, Query
from fastapi.responses import JSONResponse
from cashfree import run_cashfree_check, CashfreeResult

app = FastAPI(title="Cashfree Checker API")
API_KEY = os.environ.get("CASHFREE_API_KEY", "ladle")


def _sanitize(res: CashfreeResult) -> dict:
    return {
        "cc": res.cc,
        "response_code": res.response_code,
        "response": res.response,
        "real_response": res.real_response,
        "amount": res.amount,
        "currency": res.currency,
        "gateway": res.gateway,
    }


@app.get("/cashfree")
async def cashfree(cc: str = Query(default=""), proxy: str = Query(default=""), key: str = Query(default="")):
    if key != API_KEY:
        return JSONResponse({"error": "invalid or missing API key"}, status_code=401)
    if not cc:
        return JSONResponse({"error": "missing cc"}, status_code=400)
    proxy_url = ""
    if proxy:
        p = proxy.strip()
        if "://" not in p:
            parts = p.split(":")
            if len(parts) == 4 and "@" not in p:
                p = f"http://{parts[0]}:{parts[1]}@{parts[2]}:{parts[3]}"
            else:
                p = "http://" + p
        proxy_url = p
    try:
        res = await run_cashfree_check(cc, proxy_url)
        return JSONResponse(_sanitize(res))
    except Exception as e:
        import logging
        msg = str(e) or ""
        low = msg.lower()
        logging.getLogger("cashfree").error("check failed for %s: %s", cc[:6], msg[:200])
        if any(k in low for k in ("proxy", "curl", "timed out", "timeout", "connect", "resolve", "tunnel", "refused")):
            code = "PROXY_ERROR"
        else:
            code = "ERROR"
        return JSONResponse({
            "cc": cc, "response_code": code, "response": "ERROR", "real_response": "ERROR",
            "amount": "230.00", "currency": "INR", "gateway": "Cashfree",
        })


@app.get("/")
async def root():
    return {"ok": True, "api": "cashfree"}


if __name__ == '__main__':
    import uvicorn
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument('--port', type=int, default=9300)
    ap.add_argument('--host', default='0.0.0.0')
    args = ap.parse_args()
    print(f"\n  FastAPI server: http://{args.host}:{args.port}\n")
    uvicorn.run(app, host=args.host, port=args.port, workers=1)
