"""
backend_router.py — Weighted multi-backend checkout with WAF-aware fallback.

Distribution:
  - curl_cffi: 50% (primary — mature, Android profiles, 19 Chrome targets)
  - wreq:      25% (126 profiles, BoringSSL native, proxy rotation)
  - httpcloak: 25% (Chrome 150, HTTP/3, TCP spoofing)
  - primp:     WAF-only fallback (different TLS stack, only on 403/406)

Each backend gets its own impersonation target rotation for JA4 diversity.

Usage:
    from backend_router import route_checkout
    result = await route_checkout(cc, site, proxy, amount_paise=100)
"""

import asyncio, random, time, datetime, sys, os
from typing import Optional

# ── Backend weights ───────────────────────────────────────────────────────
# curl_cffi must always be available. Others are optional.
BACKENDS = ['wreq', 'curl_cffi', 'httpcloak']
WEIGHTS = [0.50, 0.25, 0.25]  # wreq=50% (126 profiles, most diversity)

WAF_BACKEND = 'primp'  # Only used on WAF detection

# ── Impersonation targets per backend ─────────────────────────────────────
CURL_TARGETS = [
    "chrome99", "chrome100", "chrome101", "chrome104", "chrome107",
    "chrome110", "chrome116", "chrome119", "chrome120", "chrome123",
    "chrome124", "chrome131", "chrome133a", "chrome136", "chrome142",
    "chrome145", "chrome146", "chrome99_android", "chrome131_android",
]

HTTPCLOAK_PRESETS = [
    "chrome-146-windows", "chrome-148-windows", "chrome-150-windows",
    "chrome-146-android", "chrome-148-android", "chrome-150-android",
    "chrome-146-linux", "chrome-148-linux",
    "chrome-latest", "chrome-latest-android",
]

PRIMP_TARGETS = [
    "chrome_146", "chrome_148", "chrome_124", "chrome_131",
]


def _pick_backend(attempt: int = 0, force_waf: bool = False) -> str:
    """Pick a backend based on weighted distribution.

    Args:
        attempt: 0-based attempt number. Higher attempts try different backends.
        force_waf: If True, use the WAF fallback backend.
    """
    if force_waf and attempt > 0:
        return WAF_BACKEND

    if attempt == 0:
        # Weighted random selection
        r = random.random()
        cumulative = 0.0
        for backend, weight in zip(BACKENDS, WEIGHTS):
            cumulative += weight
            if r <= cumulative:
                return backend
        return BACKENDS[0]

    # On retry: cycle through remaining backends
    idx = attempt % len(BACKENDS)
    return BACKENDS[idx]


def _run_checkout_curl_cffi(site_url: str, proxy: str, target: str = None,
                             amount_paise: int = 100, timeout: int = 30) -> dict:
    """Run checkout via curl_cffi (full 3-step WAF check)."""
    from curl_cffi import requests as cr

    tgt = target or random.choice(CURL_TARGETS)
    t0 = time.time()
    codes = []

    try:
        s = cr.Session(impersonate=tgt, default_headers=True)
        s.proxies = {'http': proxy, 'https': proxy} if proxy else {}
        s.headers.update({
            'Accept-Language': 'en-IN,en;q=0.9,hi;q=0.8',
        })

        # Step 1: Payment page
        r = s.get(site_url, timeout=timeout, headers={
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            'Sec-Fetch-Dest': 'document', 'Sec-Fetch-Mode': 'navigate',
            'Sec-Fetch-Site': 'none',
        })
        codes.append(r.status_code)
        if r.status_code >= 400:
            return _waf_or_error(r.status_code, codes, time.time()-t0, target, 'curl_cffi')

        # Step 2: checkout.js
        r = s.get('https://checkout.razorpay.com/v1/checkout.js', timeout=timeout, headers={
            'Accept': '*/*', 'Referer': site_url,
            'Sec-Fetch-Dest': 'script', 'Sec-Fetch-Mode': 'no-cors',
            'Sec-Fetch-Site': 'cross-site',
        })
        codes.append(r.status_code)
        if r.status_code >= 400:
            return _waf_or_error(r.status_code, codes, time.time()-t0, target, 'curl_cffi')

        # Step 3: checkout/public
        r = s.get('https://api.razorpay.com/v1/checkout/public', timeout=timeout, headers={
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            'Referer': site_url, 'Sec-Fetch-Dest': 'iframe',
            'Sec-Fetch-Mode': 'navigate', 'Sec-Fetch-Site': 'cross-site',
        })
        codes.append(r.status_code)
        if r.status_code >= 400:
            return _waf_or_error(r.status_code, codes, time.time()-t0, target, 'curl_cffi')

        return {'status': 'ok', 'backend': 'curl_cffi', 'target': tgt,
                'codes': codes, 'time': time.time()-t0, 'waf': False}

    except Exception as e:
        return {'status': 'error', 'backend': 'curl_cffi', 'target': tgt,
                'codes': codes, 'time': time.time()-t0, 'waf': False,
                'error': str(e)[:150]}


def _run_checkout_wreq(site_url: str, proxy: str,
                        amount_paise: int = 100, timeout: int = 30) -> dict:
    """Run checkout via wreq (Chrome 146)."""
    import datetime as dt
    from wreq.blocking import Client as WClient
    from wreq.emulation import Emulation as WE

    t0 = time.time()
    codes = []
    td = dt.timedelta(seconds=timeout)

    try:
        kwargs = {'emulation': WE.Chrome146, 'timeout': td}
        if proxy:
            from wreq import Proxy as WP
            kwargs['proxies'] = [WP.all(proxy)]
        c = WClient(**kwargs)

        r = c.get(site_url)
        codes.append(r.status)
        if r.status != 200:
            return _waf_or_error(int(str(r.status).split()[0]), codes, time.time()-t0, 'chrome146', 'wreq')

        r = c.get('https://checkout.razorpay.com/v1/checkout.js')
        codes.append(r.status)
        if r.status != 200:
            return _waf_or_error(int(str(r.status).split()[0]), codes, time.time()-t0, 'chrome146', 'wreq')

        r = c.get('https://api.razorpay.com/v1/checkout/public')
        codes.append(r.status)
        if r.status != 200:
            return _waf_or_error(int(str(r.status).split()[0]), codes, time.time()-t0, 'chrome146', 'wreq')

        return {'status': 'ok', 'backend': 'wreq', 'target': 'chrome146',
                'codes': [int(str(x.status).split()[0]) for x in [r, r, r]],
                'time': time.time()-t0, 'waf': False}

    except Exception as e:
        return {'status': 'error', 'backend': 'wreq', 'target': 'chrome146',
                'codes': codes, 'time': time.time()-t0, 'waf': False,
                'error': str(e)[:150]}


def _run_checkout_httpcloak(site_url: str, proxy: str,
                             amount_paise: int = 100, timeout: int = 30) -> dict:
    """Run checkout via httpcloak."""
    import httpcloak

    preset = random.choice(HTTPCLOAK_PRESETS)
    t0 = time.time()
    codes = []
    s = None

    try:
        kwargs = {'preset': preset, 'timeout': timeout}
        if proxy:
            kwargs['proxy'] = proxy
        s = httpcloak.Session(**kwargs)

        r = s.get(site_url)
        codes.append(r.status_code)
        if r.status_code >= 400:
            return _waf_or_error(r.status_code, codes, time.time()-t0, preset, 'httpcloak')

        r = s.get('https://checkout.razorpay.com/v1/checkout.js')
        codes.append(r.status_code)
        if r.status_code >= 400:
            return _waf_or_error(r.status_code, codes, time.time()-t0, preset, 'httpcloak')

        r = s.get('https://api.razorpay.com/v1/checkout/public')
        codes.append(r.status_code)
        if r.status_code >= 400:
            return _waf_or_error(r.status_code, codes, time.time()-t0, preset, 'httpcloak')

        return {'status': 'ok', 'backend': 'httpcloak', 'target': preset,
                'codes': codes, 'time': time.time()-t0, 'waf': False}

    except Exception as e:
        return {'status': 'error', 'backend': 'httpcloak', 'target': preset,
                'codes': codes, 'time': time.time()-t0, 'waf': False,
                'error': str(e)[:150]}
    finally:
        if s:
            try:
                s.close()
            except Exception:
                pass


def _run_checkout_primp(site_url: str, proxy: str,
                         amount_paise: int = 100, timeout: int = 30) -> dict:
    """Run checkout via primp (WAF-only fallback)."""
    import primp

    tgt = random.choice(PRIMP_TARGETS)
    t0 = time.time()
    codes = []

    try:
        kwargs = {'impersonate': tgt, 'timeout': timeout, 'cookie_store': True}
        if proxy:
            kwargs['proxy'] = proxy
        c = primp.Client(**kwargs)

        r = c.get(site_url)
        codes.append(r.status_code)
        if r.status_code >= 400:
            return _waf_or_error(r.status_code, codes, time.time()-t0, tgt, 'primp')

        r = c.get('https://checkout.razorpay.com/v1/checkout.js')
        codes.append(r.status_code)
        if r.status_code >= 400:
            return _waf_or_error(r.status_code, codes, time.time()-t0, tgt, 'primp')

        r = c.get('https://api.razorpay.com/v1/checkout/public')
        codes.append(r.status_code)
        if r.status_code >= 400:
            return _waf_or_error(r.status_code, codes, time.time()-t0, tgt, 'primp')

        return {'status': 'ok', 'backend': 'primp', 'target': tgt,
                'codes': codes, 'time': time.time()-t0, 'waf': False}

    except Exception as e:
        return {'status': 'error', 'backend': 'primp', 'target': tgt,
                'codes': codes, 'time': time.time()-t0, 'waf': False,
                'error': str(e)[:150]}


def _waf_or_error(code, codes, elapsed, target, backend):
    """Determine if a non-200 response is WAF or other error."""
    is_waf = code in (403, 406)
    return {
        'status': 'waf' if is_waf else 'error',
        'backend': backend, 'target': target,
        'codes': codes, 'time': elapsed,
        'waf': is_waf,
        'error': f'HTTP {code}' if not is_waf else '',
    }


# ── Router ────────────────────────────────────────────────────────────────

async def route_checkout(site_url: str, proxy_url: str = None,
                          amount_paise: int = 100,
                          max_attempts: int = 4) -> dict:
    """Route a checkout through the multi-backend system.

    Attempt 0: Weighted random (curl_cffi 50%, wreq 25%, httpcloak 25%)
    Attempt 1: Different backend (round-robin)
    Attempt 2: Third backend
    Attempt 3: primp (WAF-only fallback)

    If any attempt returns a WAF signal (403/406), primp is tried on the
    next attempt regardless of the normal rotation.

    Returns: {'status': 'ok'|'waf'|'error', 'backend': ..., 'target': ...,
              'codes': [...], 'time': ..., 'waf': bool, 'attempts': int}
    """
    force_waf = False

    for attempt in range(max_attempts):
        backend = _pick_backend(attempt, force_waf)

        loop = asyncio.get_event_loop()

        if backend == 'curl_cffi':
            result = await loop.run_in_executor(
                None, _run_checkout_curl_cffi, site_url, proxy_url, None, amount_paise)
        elif backend == 'wreq':
            result = await loop.run_in_executor(
                None, _run_checkout_wreq, site_url, proxy_url, amount_paise)
        elif backend == 'httpcloak':
            result = await loop.run_in_executor(
                None, _run_checkout_httpcloak, site_url, proxy_url, amount_paise)
        elif backend == 'primp':
            result = await loop.run_in_executor(
                None, _run_checkout_primp, site_url, proxy_url, amount_paise)
        else:
            # Unknown backend — fall back to curl_cffi
            result = await loop.run_in_executor(
                None, _run_checkout_curl_cffi, site_url, proxy_url, None, amount_paise)

        result['attempt'] = attempt

        # If WAF detected, force primp on next attempt
        if result.get('waf'):
            force_waf = True
            continue

        # If successful or non-WAF error, return immediately
        if result['status'] == 'ok':
            return result

        # Non-WAF error — retry with different backend
        if attempt < max_attempts - 1:
            continue

    # All attempts exhausted
    return result


# ── Stats ─────────────────────────────────────────────────────────────────

_backend_stats: dict[str, dict] = {b: {'total': 0, 'pass': 0, 'waf': 0, 'error': 0}
                                    for b in BACKENDS + [WAF_BACKEND]}
_stats_lock = asyncio.Lock()


async def record_outcome(backend: str, status: str, is_waf: bool):
    """Record a checkout outcome for backend health monitoring."""
    async with _stats_lock:
        s = _backend_stats.get(backend, {'total': 0, 'pass': 0, 'waf': 0, 'error': 0})
        s['total'] += 1
        if status == 'ok':
            s['pass'] += 1
        elif is_waf:
            s['waf'] += 1
        else:
            s['error'] += 1


def get_backend_stats() -> dict:
    """Get backend performance stats for health check."""
    return dict(_backend_stats)
