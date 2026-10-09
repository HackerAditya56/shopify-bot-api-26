"""
run_logger.py — full A-to-Z per-card debug logger for the v2 flow.

Every checkout gets a unique run_id. Each request/response is recorded
step-by-step (method, url, headers, body, status, response headers/body,
cookies after, elapsed) into a single structured JSON file:

    logs/<run_id>.json

Useful for auditing exactly what the session sent/received and where a
checkout deviated.
"""

from __future__ import annotations

import json
import re
import time
import uuid
from datetime import datetime
from pathlib import Path

LOGS_DIR = Path(__file__).resolve().parent / "logs"
_BODY_MAX = 12000   # truncate large bodies; record full length

# Set to True to re-enable the per-card step-by-step debug logging.
# Disabled by default — was only needed to trace the CAPTCHA_REQUIRED flow.
ENABLED = False


def _phase_for_url(url: str) -> str:
    """Infer a human-readable phase name from the request URL."""
    u = url.lower()
    if "/cart/add" in u:
        return "cart_add"
    if "/cart.js" in u or u.endswith("/cart") or "/cart?" in u:
        return "cart"
    if "/checkouts/internal/graphql/persisted" in u:
        return "checkout_graphql"
    if "/checkouts/cn/" in u:
        return "checkout_page"
    if "/checkouts/internal/preloads" in u:
        return "checkout_preloads"
    if "checkout.pci.shopifyinc.com" in u and "/sessions" in u:
        return "pci_session"
    if "checkout.pci.shopifyinc.com" in u:
        return "pci_asset"
    if "/private_access_tokens" in u:
        return "private_access_token"
    if "/actions" in u and ".js" in u:
        return "actions_js"
    if "/products.json" in u or "/products/" in u:
        return "catalog"
    if "monorail" in u:
        return "telemetry_monorail"
    if "otlp" in u:
        return "telemetry_otlp"
    if "/api/collect" in u:
        return "telemetry_collect"
    if "/api/" in u:
        return "storefront_api"
    if u.endswith("/") or "/pages/" in u:
        return "landing"
    return "other"


class RunLogger:
    def __init__(self, card: str, site: str, proxy: str, client):
        card_num = card.split("|")[0] if "|" in (card or "") else (card or "")
        self.run_id = (
            datetime.now().strftime("%Y%m%d_%H%M%S")
            + "_" + (card_num[-4:] if card_num else "xxxx")
            + "_" + uuid.uuid4().hex[:6]
        )
        self.card = card
        self.site = site
        self.proxy = proxy
        self.started_at = datetime.now().isoformat()
        self.steps = []
        self.result = {}
        self.client = client
        # fingerprint context captured once
        self.context = {
            "impersonate": getattr(client, "impersonate", ""),
            "user_agent": getattr(client, "user_agent", ""),
        }

    def record(self, method: str, url: str, headers, body,
               resp, elapsed_ms: float, session_cookies=None) -> None:
        if not ENABLED:
            return
        cookies = {}
        if session_cookies is not None:
            cookies = session_cookies
        else:
            try:
                jar = None
                for attr in ("_session", "session"):
                    s = getattr(self.client, attr, None)
                    if s is not None:
                        jar = getattr(s, "cookies", None)
                        if jar is not None:
                            break
                if jar is not None:
                    cookies = {k: str(jar.get(k)) for k in jar}
            except Exception:
                pass

        resp_headers = {}
        resp_body = ""
        status = None
        final_url = ""
        try:
            status = resp.status_code
            final_url = str(resp.url)
            resp_headers = dict(resp.headers) if resp.headers else {}
            resp_body = resp.text or ""
        except Exception:
            pass

        phase = _phase_for_url(url)
        if phase == "checkout_graphql":
            m = re.search(r'"operationName"\s*:\s*"([^"]+)"', str(body or ""))
            if m:
                phase = f"checkout_graphql:{m.group(1)}"

        self.steps.append({
            "step": len(self.steps) + 1,
            "phase": phase,
            "method": method,
            "url": url,
            "request_headers": _clean(headers),
            "request_body": _trunc(str(body)),
            "request_body_len": len(str(body or "")),
            "response_status": status,
            "final_url": final_url,
            "response_headers": _clean(resp_headers),
            "response_body": _trunc(resp_body),
            "response_body_len": len(resp_body),
            "cookies_after": cookies,
            "elapsed_ms": round(elapsed_ms, 1),
        })

    def set_result(self, status, status_code, amount, currency, gateway, error):
        if not ENABLED:
            return
        self.result = {
            "status": str(status),
            "status_code": status_code,
            "amount": amount,
            "currency": currency,
            "gateway": gateway,
            "error": str(error) if error else None,
        }

    def save(self) -> str:
        if not ENABLED:
            return ""
        LOGS_DIR.mkdir(exist_ok=True)
        doc = {
            "run_id": self.run_id,
            "card": self.card,
            "site": self.site,
            "proxy": self.proxy,
            "fingerprint": self.context["impersonate"],
            "user_agent": self.context["user_agent"],
            "started_at": self.started_at,
            "finished_at": datetime.now().isoformat(),
            "total_steps": len(self.steps),
            "result": self.result,
            "steps": self.steps,
        }
        path = LOGS_DIR / f"{self.run_id}.json"
        path.write_text(json.dumps(doc, indent=2, ensure_ascii=False), encoding="utf-8")
        return str(path)


def _trunc(s: str) -> str:
    if s is None:
        return ""
    if len(s) > _BODY_MAX:
        return s[:_BODY_MAX] + f"...[truncated {len(s)} chars]"
    return s


def _clean(d) -> dict:
    if not d:
        return {}
    if isinstance(d, dict):
        return {str(k): str(v) for k, v in d.items()}
    try:
        return dict(d)
    except Exception:
        return {"_raw": str(d)}


class LoggedClient:
    """Wraps an AsyncTLSClient, logging every get/post automatically."""

    def __init__(self, client, logger: RunLogger):
        self._client = client
        self._logger = logger

    def __getattr__(self, name):
        return getattr(self._client, name)

    async def get(self, url, **kwargs):
        if not ENABLED:
            return await self._client.get(url, **kwargs)
        t0 = time.monotonic()
        resp = await self._client.get(url, **kwargs)
        self._logger.record("GET", url, kwargs.get("headers"), None, resp,
                            (time.monotonic() - t0) * 1000)
        return resp

    async def post(self, url, data=None, json=None, **kwargs):
        if not ENABLED:
            return await self._client.post(url, data=data, json=json, **kwargs)
        t0 = time.monotonic()
        resp = await self._client.post(url, data=data, json=json, **kwargs)
        self._logger.record("POST", url, kwargs.get("headers"),
                            data if data is not None else json, resp,
                            (time.monotonic() - t0) * 1000)
        return resp

    async def close(self):
        await self._client.close()
