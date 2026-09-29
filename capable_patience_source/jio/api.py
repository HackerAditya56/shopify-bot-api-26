"""Jio Recharge Checker — HTTP API (FastAPI + uvicorn).  Bot-free build.

POST /check         {cc, number, proxy, amount}
GET  /check?cc=&number=&proxy=&amount=
POST /check/bulk    {number, cards:[{cc, proxy, amount}]}

cc format: number|MM|YYYY|CVV
proxy: host:port:user:pass  (or http://user:pass@host:port)
"""
from __future__ import annotations

import time
import os as _os
from concurrent.futures import ThreadPoolExecutor

from fastapi import FastAPI, Query
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from checker import RechargeChecker

app = FastAPI(
    title="Jio Recharge Checker",
    version="1.2",
    description="Checks a card against the Jio recharge flow. Proxy is mandatory.",
)

checker = RechargeChecker()
_executor = ThreadPoolExecutor(max_workers=30)

AMOUNTS = ["19", "29", "49", "69", "98", "129", "155", "199", "219", "239",
           "299", "349", "399", "449", "499", "599", "719", "839", "999", "1499"]


class CheckReq(BaseModel):
    cc: str
    number: str
    proxy: str  # mandatory
    amount: str = "19"
    extra_proxies: list[str] | None = None  # fallback pool for the Jio leg retry


class BulkCard(BaseModel):
    cc: str
    proxy: str  # mandatory
    amount: str = "19"


class BulkReq(BaseModel):
    number: str
    cards: list[BulkCard]


@app.get("/")
def root():
    return {
        "service": "jio-recharge-checker",
        "proxy": "MANDATORY",
        "amounts": [int(a) for a in AMOUNTS],
        "endpoints": {
            "GET /check": "?cc=number|MM|YYYY|CVV&number=7667702392&proxy=host:port:user:pass&amount=19",
            "POST /check": '{"cc":"number|MM|YYYY|CVV","number":"7667702392","proxy":"host:port:user:pass","amount":"19"}',
            "POST /check/bulk": '{"number":"7667702392","cards":[{"cc":"...","proxy":"...","amount":"19"}]}',
        },
        "categories": ["charged", "approved", "insufficient", "declined", "expired",
                       "cvv", "invalid", "blocked", "3d", "3d_timeout", "cancelled", "error"],
    }


@app.get("/check")
async def check_get(cc: str = Query(..., description="number|MM|YYYY|CVV"),
                    number: str = Query(...),
                    proxy: str = Query(..., description="host:port:user:pass (mandatory)"),
                    amount: str = Query("19"),
                    extra_proxies: str = Query(None, description="comma-separated fallback proxies")):
    extra = [x.strip() for x in extra_proxies.split(",") if x.strip()] if extra_proxies else None
    res = checker.check(cc, number, proxy, amount, extra)
    return JSONResponse(res)


@app.post("/check")
async def check_post(req: CheckReq):
    res = checker.check(req.cc, req.number, req.proxy, req.amount, req.extra_proxies)
    return JSONResponse(res)


@app.post("/check/bulk")
async def check_bulk(req: BulkReq):
    t0 = time.time()
    futs = [_executor.submit(checker.check, c.cc, req.number, c.proxy, c.amount) for c in req.cards]
    results = [f.result() for f in futs]
    cats = ["charged", "approved", "insufficient", "declined", "expired", "cvv",
            "invalid", "blocked", "3d", "3d_timeout", "cancelled", "error"]
    summary = {k: sum(1 for r in results if r["response"] == k) for k in cats}
    return {
        "number": req.number,
        "total": len(results),
        "summary": summary,
        "wall_time": round(time.time() - t0, 2),
        "results": results,
    }
