"""Flask HTTP service mirroring c3.py, backed by the auto.py / auto_async.py core.

Endpoints (drop-in shape with c3.py):
    GET/POST /shopii
    GET/POST /shopii/persisted
    GET/POST /shopiig
    GET/POST /shopii/graphql
    GET      /shopii/health

Every successful response is rendered through auto.to_response_dict() and has
exactly the c3.py keys: CC, Currency, Gateway, Price, Proxy, Response, Status.
"""

from __future__ import annotations

import asyncio
import os
import re
import threading
import time

from flask import Flask, jsonify, request

import auto
import auto_async

app = Flask(__name__)

PORT = int(os.environ.get("PORT", "8082"))
HOST = os.environ.get("HOST", "0.0.0.0")

# ── per-shop pacing (c3.py parity) ────────────────────────────────────

_PACE_LOCK = threading.Lock()
_PACE_STATE: dict = {}
_PACE_INTERVAL = float(os.environ.get("PACE_INTERVAL", "1.0"))
_PACE_COOLDOWN = float(os.environ.get("PACE_COOLDOWN", "0.0"))


def _pace(shop_url: str) -> None:
    """Throttle per-shop starts so a single shop is not hammered."""
    if _PACE_INTERVAL <= 0:
        return
    while True:
        with _PACE_LOCK:
            now = time.time()
            last = _PACE_STATE.get(shop_url, 0.0)
            wait = _PACE_INTERVAL - (now - last)
            if wait <= 0:
                _PACE_STATE[shop_url] = now
                return
        time.sleep(min(wait, _PACE_INTERVAL))


# ── request helpers ───────────────────────────────────────────────────

def _norm_proxy(p):
    p = (p or "").strip()
    if not p:
        return ""
    try:
        return auto.normalize_proxy(p)
    except Exception:
        return ""


def _parse_card(card) -> str:
    """Accept a dict card or a "number|month|year|cvv" string; return the
    pipe form that auto.parse_card_entry() expects."""
    if isinstance(card, dict):
        return "{}|{}|{}|{}".format(
            card.get("number", ""), card.get("month", ""),
            card.get("year", ""), card.get("cvv", ""))
    return str(card or "").strip()


def _request_common():
    if request.method == "POST":
        data = request.get_json(silent=True) or {}
        cc = data.get("cc") or data.get("card") or ""
        site = data.get("site") or data.get("shop_url") or data.get("shop") or ""
        proxy = data.get("proxy") or ""
        proxy_urls = data.get("proxies") or data.get("proxy_urls") or ""
    else:
        data = request.args
        cc = data.get("cc") or data.get("card") or ""
        site = data.get("site") or data.get("shop_url") or data.get("shop") or ""
        proxy = data.get("proxy") or ""
        proxy_urls = data.get("proxies") or data.get("proxy_urls") or ""

    shop_url = (site or "").strip()
    if shop_url and not shop_url.startswith("http"):
        shop_url = "https://" + shop_url
    shop_url = shop_url.rstrip("/")

    card_entry = _parse_card(cc)

    proxy = auto.normalize_proxy(proxy) if (proxy or "").strip() else ""
    return data, shop_url, card_entry, proxy


def _error_response(response="ERROR", card="", proxy="", currency="USD"):
    return jsonify({
        "CC": card,
        "Currency": currency,
        "Gateway": "unknown",
        "Price": "0.00",
        "Proxy": "Live" if proxy else "None",
        "Response": response,
        "Status": "false",
    })


def _run_sync(shop_url, card_entry, proxy):
    result = auto.run_checkout_for_card(shop_url, card_entry, proxy)
    return auto.to_response_dict(result, proxy=proxy)


def _run_async(shop_url, card_entry, proxy):
    result = asyncio.run(auto_async.run_checkout_for_card_async(shop_url, card_entry, proxy))
    return auto_async.to_response_dict(result, proxy=proxy)


def _handle(runner):
    try:
        data, shop_url, card_entry, proxy = _request_common()
        if not shop_url or not card_entry:
            return _error_response(
                "MISSING_CARD" if not card_entry else "MISSING_SITE",
                card=card_entry, proxy=proxy), 400
        _pace(shop_url)
        return jsonify(runner(shop_url, card_entry, proxy))
    except auto.CardEntryError as e:
        return _error_response("MISSING_CARD", card="", proxy=""), 400
    except Exception:
        return _error_response("ERROR"), 200


# ── routes ────────────────────────────────────────────────────────────

@app.route("/shopii", methods=["GET", "POST"])
@app.route("/shopii/persisted", methods=["GET", "POST"])
def shopii_persisted():
    return _handle(_run_sync)


@app.route("/shopiig", methods=["GET", "POST"])
@app.route("/shopii/graphql", methods=["GET", "POST"])
def shopii_graphql():
    return _handle(_run_async)


@app.route("/shopii/health", methods=["GET"])
def health():
    return jsonify({"status": "ok", "service": "shopify-gate"})


@app.errorhandler(Exception)
def _handle_all(e):
    return _error_response("ERROR"), 200


if __name__ == "__main__":
    print("─" * 50)
    print("  Shopify Gate (auto) — Flask")
    print(f"  Host   : {HOST}")
    print(f"  Port   : {PORT}")
    print("  Routes : /shopii /shopii/persisted /shopiig /shopii/graphql /shopii/health")
    print("─" * 50)
    app.run(host=HOST, port=PORT, debug=False, threaded=True, use_reloader=False)
