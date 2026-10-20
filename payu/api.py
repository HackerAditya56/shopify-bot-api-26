
"""
PayU checker API — FastAPI endpoint.

Usage:
    GET /payu?amount=1&cc=4001679034804536|01|2029|629&proxy=user:pass@host:port

Response (sanitized — merchant site + internal identifiers never exposed):
    {
      "cc": "4001679034804536|01|2029|629",
      "response_code": "INSUFFICIENT_FUNDS",
      "response": "APPROVED",
      "real_response": "CARD_INSUFFICIENT_FUNDS",
      "amount": "1.00",
      "currency": "USD",
      "gateway": "PayU"
    }
"""
from __future__ import annotations

import os

from fastapi import FastAPI, Query
from fastapi.responses import JSONResponse

from payu import run_payu_check, PayuResult

app = FastAPI(title="PayU Checker API")

API_KEY = os.environ.get("PAYU_API_KEY", "ladle")


def _sanitize(res: PayuResult) -> dict:
    """Only the fields the caller needs. Never the merchant/site, JWT, order id."""
    return {
        "cc": res.cc,
        "response_code": res.response_code,
        "response": res.response,
        "real_response": res.real_response,
        "amount": res.amount,
        "currency": res.currency,
        "gateway": res.gateway,
    }


@app.get("/payu")
async def payu(
    amount: str = Query(default="1"),
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
            parts = p.split(":")
            if len(parts) == 4 and "@" not in p:
                p = f"http://{parts[0]}:{parts[1]}@{parts[2]}:{parts[3]}"
            else:
                p = "http://" + p
        proxy_url = p

    try:
        res = await run_payu_check(amount, cc, proxy_url)
        return JSONResponse(_sanitize(res))
    except Exception as e:
        # classify the failure, never leak internals
        msg = str(e) or ""
        low = msg.lower()
        import logging
        logging.getLogger("payu").error("check failed for %s: %s", cc[:6], msg[:200])
        if any(k in low for k in ("proxy", "curl", "timed out", "timeout", "connect", "resolve", "tunnel", "refused")):
            code = "PROXY_ERROR"
        elif any(k in low for k in ("create order", "order fetch", "tokenize", "payment submit", "status fetch", "threeds")):
            code = "GATEWAY_ERROR"
        elif "invalid card format" in low:
            code = "INVALID_CARD"
        else:
            code = "ERROR"
        return JSONResponse({
            "cc": cc,
            "response_code": code,
            "response": "ERROR",
            "real_response": "ERROR",
            "amount": "0.00",
            "currency": "USD",
            "gateway": "PayU",
        })


@app.get("/")
async def root():
    return {"ok": True, "api": "payu"}


if __name__ == '__main__':
    import uvicorn
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument('--port', type=int, default=9200)
    ap.add_argument('--host', default='0.0.0.0')
    args = ap.parse_args()
    print(f"\n  FastAPI server: http://{args.host}:{args.port}\n")
    uvicorn.run(app, host=args.host, port=args.port, workers=1)
