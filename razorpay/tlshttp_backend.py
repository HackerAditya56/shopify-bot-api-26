"""
tlshttp_backend.py — tlshttp HTTP backend compatible with RazorpaySession.

Provides Session/AsyncSession classes that match curl_cffi's API
so RazorpaySession can use tlshttp as a drop-in replacement.

tlshttp uses uTLS (Go-based) instead of curl-impersonate (C-based),
giving different TLS fingerprints that bypass Razorpay's WAF.
"""

from __future__ import annotations

import asyncio
import time
from typing import Optional
from urllib.parse import urlparse, unquote


class TlsHttpCookieJar:
    """Minimal cookie jar matching curl_cffi's cookie API."""
    def __init__(self):
        self._cookies: dict[str, str] = {}

    def set(self, name: str, value: str, domain: str = '', path: str = '/'):
        self._cookies[name] = value

    def get_dict(self) -> dict[str, str]:
        return dict(self._cookies)

    def __iter__(self):
        return iter(self._cookies)

    def items(self):
        return self._cookies.items()

    def get(self, name: str, default=None):
        return self._cookies.get(name, default)

    def __contains__(self, name):
        return name in self._cookies

    def __len__(self):
        return len(self._cookies)


class TlsHttpResponse:
    """Thin wrapper to make tlshttp response look like curl_cffi response."""

    def __init__(self, tls_response, session: 'TlsHttpAsyncSession' = None):
        self._r = tls_response
        self._session = session
        self.status_code = getattr(tls_response, 'status_code', 0) or 0
        self.text = getattr(tls_response, 'text', '') or ''
        self.content = (self.text.encode() if self.text else b'')
        self.headers = dict(getattr(tls_response, 'headers', {}) or {})

    @property
    def cookies(self):
        return self._session._cookies if self._session else {}


class TlsHttpAsyncSession:
    """Mimics curl_cffi.requests.AsyncSession using tlshttp.AsyncClient."""

    def __init__(self, proxy_url: str = None, proxy_auth: tuple = None,
                 timeout: float = 15.0, headers: dict = None,
                 profile=None, random_tls: bool = True, http2: bool = True):
        self._proxy_url = proxy_url
        self._proxy_auth = proxy_auth
        self._timeout = timeout
        self._default_headers = dict(headers) if headers else {}
        self._profile = profile
        self._random_tls = random_tls
        self._http2 = http2
        self._client = None
        self.cookies = TlsHttpCookieJar()
        self._closed = False
        self.headers = {}  # mimic curl_cffi headers dict

    async def _ensure_client(self):
        if self._client is None or self._closed:
            from tlshttp import AsyncClient, Chrome
            profile = self._profile or Chrome.V133_PSK
            proxy = self._proxy_url
            # tlshttp expects http://user:pass@host:port
            # If we have proxy_auth, construct full URL
            if proxy and self._proxy_auth:
                user, pwd = self._proxy_auth
                p = urlparse(proxy)
                proxy = f'{p.scheme}://{user}:{pwd}@{p.hostname}:{p.port}'

            self._client = AsyncClient(
                profile=profile,
                proxy=proxy,
                timeout=self._timeout,
                random_tls_extension_order=self._random_tls,
                http2=self._http2,
                headers=self._default_headers,
            )
        return self._client

    async def close(self):
        if self._client is not None and not self._closed:
            try:
                await self._client.aclose()
            except Exception:
                pass
            self._closed = True
            self._client = None

    def _merge_headers(self, extra: dict = None) -> dict:
        h = dict(self._default_headers)
        if extra:
            h.update(extra)
        return h

    async def _do_request(self, method: str, url: str, data=None, json=None,
                          headers: dict = None):
        """Route request to tlshttp, handling pre-encoded string data."""
        c = await self._ensure_client()
        h = self._merge_headers(headers)

        # tlshttp's 'data' parameter URL-encodes a dict. If we have a
        # pre-encoded string (like curl_cffi form bodies), use 'content'.
        if data is not None:
            if isinstance(data, str):
                if 'Content-Type' not in h:
                    h['Content-Type'] = 'application/x-www-form-urlencoded'
                r = await c.request(method, url, content=data, headers=h)
            else:
                r = await c.request(method, url, data=data, headers=h)
        elif json is not None:
            r = await c.request(method, url, json=json, headers=h)
        else:
            r = await c.request(method, url, headers=h)
        return TlsHttpResponse(r, self)

    async def get(self, url: str, headers: dict = None, timeout: float = None):
        c = await self._ensure_client()
        r = await c.get(url, headers=self._merge_headers(headers))
        return TlsHttpResponse(r, self)

    async def post(self, url: str, data=None, json=None, headers: dict = None,
                   timeout: float = None):
        return await self._do_request('POST', url, data=data, json=json, headers=headers)

    async def request(self, method: str, url: str, data=None, json=None,
                      headers: dict = None, timeout: float = None):
        return await self._do_request(method, url, data=data, json=json, headers=headers)

    def update_cookies(self, cookies):
        """Merge cookies from a response or dict."""
        if isinstance(cookies, dict):
            self._cookies.update(cookies)


class TlsHttpSession:
    """Mimics curl_cffi.requests.Session using tlshttp.Client (sync)."""

    def __init__(self, proxy_url: str = None, proxy_auth: tuple = None,
                 timeout: float = 15.0, headers: dict = None,
                 profile=None, random_tls: bool = True, http2: bool = True):
        from tlshttp import Client, Chrome
        self._profile = profile or Chrome.V133_PSK
        self._timeout = timeout
        self._default_headers = dict(headers) if headers else {}
        self._cookies: dict[str, str] = {}
        self.cookies = TlsHttpCookieJar()
        self.headers = {}
        self.proxies = {}

        # Build proxy URL
        proxy = proxy_url
        if proxy and proxy_auth:
            user, pwd = proxy_auth
            p = urlparse(proxy)
            proxy = f'{p.scheme}://{user}:{pwd}@{p.hostname}:{p.port}'

        self._client = Client(
            profile=self._profile,
            proxy=proxy,
            timeout=timeout,
            random_tls_extension_order=random_tls,
            http2=http2,
            headers=self._default_headers,
        )

    def close(self):
        try:
            self._client.close()
        except Exception:
            pass

    def _merge_headers(self, extra: dict = None) -> dict:
        h = dict(self._default_headers)
        if extra:
            h.update(extra)
        return h

    def _do_request(self, method: str, url: str, data=None, json=None,
                    headers: dict = None):
        """Route request to tlshttp, handling pre-encoded string data."""
        h = self._merge_headers(headers)
        if data is not None:
            if isinstance(data, str):
                if 'Content-Type' not in h:
                    h['Content-Type'] = 'application/x-www-form-urlencoded'
                r = self._client.request(method, url, content=data, headers=h)
            else:
                r = self._client.request(method, url, data=data, headers=h)
        elif json is not None:
            r = self._client.request(method, url, json=json, headers=h)
        else:
            r = self._client.request(method, url, headers=h)
        return TlsHttpResponse(r, self)

    def get(self, url: str, headers: dict = None):
        r = self._client.get(url, headers=self._merge_headers(headers))
        return TlsHttpResponse(r, self)

    def post(self, url: str, data=None, json=None, headers: dict = None):
        return self._do_request('POST', url, data=data, json=json, headers=headers)

    def request(self, method: str, url: str, data=None, json=None,
                headers: dict = None, timeout: float = None):
        return self._do_request(method, url, data=data, json=json, headers=headers)

    def update_cookies(self, cookies):
        if isinstance(cookies, dict):
            self._cookies.update(cookies)


# ── WAF test (3-step check via tlshttp) ──────────────────────────────────

async def tlshttp_waf_check(site_url: str, proxy_url: str, timeout: float = 15.0) -> dict:
    """Quick 3-step check using tlshttp. Returns waf=True if blocked."""
    import time as _time
    from tlshttp import AsyncClient, Chrome

    t0 = _time.time()
    codes = []
    try:
        async with AsyncClient(
            profile=Chrome.V133_PSK,
            proxy=proxy_url,
            timeout=timeout,
            random_tls_extension_order=True,
            http2=True,
        ) as c:
            r1 = await c.get(site_url, headers={
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
                'Accept-Language': 'en-IN,en;q=0.9,hi;q=0.8',
            })
            codes.append(r1.status_code)
            if r1.status_code >= 400:
                return {'status': 'waf' if r1.status_code in (403, 406) else 'error',
                        'backend': 'tlshttp', 'target': 'chrome_v133_psk',
                        'codes': codes, 'time': _time.time() - t0,
                        'waf': r1.status_code in (403, 406),
                        'http_code': r1.status_code, 'step': 'page'}

            r2 = await c.get('https://checkout.razorpay.com/v1/checkout.js', headers={
                'Accept': '*/*', 'Referer': site_url,
            })
            codes.append(r2.status_code)
            if r2.status_code >= 400:
                return {'status': 'waf' if r2.status_code in (403, 406) else 'error',
                        'backend': 'tlshttp', 'target': 'chrome_v133_psk',
                        'codes': codes, 'time': _time.time() - t0,
                        'waf': r2.status_code in (403, 406),
                        'http_code': r2.status_code, 'step': 'checkout.js'}

            r3 = await c.get(
                'https://api.razorpay.com/v1/checkout/public?traffic_env=production',
                headers={
                    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
                    'Referer': site_url,
                })
            codes.append(r3.status_code)
            return {'status': 'ok', 'backend': 'tlshttp', 'target': 'chrome_v133_psk',
                    'codes': codes, 'time': _time.time() - t0,
                    'waf': r3.status_code in (403, 406),
                    'http_code': r3.status_code}
    except Exception as e:
        return {'status': 'error', 'backend': 'tlshttp', 'target': 'chrome_v133_psk',
                'codes': codes, 'time': _time.time() - t0, 'waf': False,
                'error': str(e)[:150]}
