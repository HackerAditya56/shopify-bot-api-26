"""
warmup_flow.py — human-like warmup + Shopify telemetry simulation.

Standalone (does NOT touch auto.py / auto_async.py). Reuses auto.TLSClient so the
curl_cffi cookie jar is the single source of truth across every hop, and the
profile/UA pairing from PROFILE_UA stays consistent.

Flow (mirrors hatch_session.har):
  1. Storefront landing        GET  /
  2. human reading delay       2.0 - 4.0 s
  3. browse a product          GET  /products/<handle>.js
  4. cart add (real form)      POST /cart/add.js        (multipart/form-data)
  5. cart state                GET  /cart.js
  6. human reading delay       3.0 - 5.0 s
  7. checkout init             POST /cart  -> 302 -> GET /checkouts/cn/<token>
  8. telemetry hits            POST monorail-edge.shopifysvc.com/v1/produce
                               POST <shop>/api/collect

Telemetry schema_ids are the modern descendants of the old /pages/internal/beacon.
"""

from __future__ import annotations

import json
import random
import re
import time
from typing import Dict, Optional, Tuple

from auto import TLSClient

# ──────────────────────── Telemetry constants ─────────────────────────

MONORAIL_PRODUCE = "https://monorail-edge.shopifysvc.com/v1/produce"

# Storefront-phase Monorail events use this zero-padded token (matches HAR);
# the real checkout session_token only exists once the checkout page loads.
ZERO_SESSION_TOKEN = "00000000-0000-0000-5000-000000000000"
MONORAIL_BATCH   = "https://monorail-edge.shopifysvc.com/unstable/produce_batch"

# Consent flags from a real /api/collect hit (hatch_session.har)
_COLLECT_SESSION_FLAGS = {
    "wd": False, "ua": False, "cf": True, "be": True, "nm": False,
    "nc": False, "ka": False, "sa": False, "ta": False, "pt": False,
    "mp": False, "sd": False,
}


def _now_ms() -> int:
    return int(time.time() * 1000)


# ──────────────────────── Telemetry emitters ──────────────────────────

def fire_monorail(client: TLSClient, schema_id: str, payload: Dict,
                  shop_url: str, metadata: Optional[Dict] = None) -> int:
    """Single-event Monorail beacon (the modern /pages/internal/beacon)."""
    now = _now_ms()
    body = json.dumps({
        "schema_id": schema_id,
        "payload": payload,
        "metadata": metadata if metadata is not None else {
            "event_created_at_ms": now,
            "event_sent_at_ms": now,
        },
    }, separators=(",", ":"))
    headers = {
        "Content-Type": "text/plain;charset=UTF-8",   # classic Monorail is text/plain JSON
        "Origin": shop_url,
        "Referer": shop_url + "/",
    }
    try:
        resp = client.post(MONORAIL_PRODUCE, data=body, headers=headers)
        return resp.status_code
    except Exception:
        return -1


def fire_site_abandonment(client: TLSClient, shop_url: str, shop_id: int,
                          page_type: str, navigation_start_ms: int,
                          duration_ms: int, session_token: str) -> int:
    """online_store_buyer_site_abandonment/1.1 — the key 'a human lingered here'
    signal. Fires with the wall-clock duration spent on the page."""
    return fire_monorail(
        client,
        "online_store_buyer_site_abandonment/1.1",
        {
            "shop_id": shop_id,
            "url": shop_url + "/",
            "navigation_start": navigation_start_ms,
            "duration": duration_ms,
            "session_token": session_token,
            "page_type": page_type,
        },
        shop_url,
    )


def fire_checkout_track(client: TLSClient, shop_url: str, shop_id: int,
                        event_name: str, checkout_token: str,
                        variant_id: str, product_id: str, price: str,
                        quantity: int = 1, currency: str = "USD") -> int:
    """checkout_track/3.8 — cart/checkout information telemetry."""
    return fire_monorail(
        client,
        "checkout_track/3.8",
        {
            "event_name": event_name,
            "cart_token": checkout_token,
            "tracking_unique": None,   # optional; omitted when unknown
            "shop_id": shop_id,
            "event_timestamp_epoch_ms": _now_ms(),
            "user_agent": client.user_agent,
            "content_language": "en-US",
            "action_name": "query",
            "line_item_product_ids": [int(product_id)] if product_id else [],
            "line_item_variant_ids": [int(variant_id)] if variant_id else [],
            "line_item_total_price": [price],
            "line_item_total_price_usd": [price],
            "line_item_quantity": [quantity],
            "currency": currency,
            "total_item_count": 1,
            "api_client_id": 580111,
            "current_api_client_id": 580111,
            "current_step": "onePage",
            "checkout_token": checkout_token,
            "source_processor": "web_checkout",
            "subtotal_price": price,
            "source_name": "checkout_one",
            "distinct_item_count": 1,
            "javascript_enabled": True,
            "checkout_platform": "checkout_one",
        },
        shop_url,
    )


def collect_analytics(client: TLSClient, shop_url: str, reason: str = "change") -> int:
    """POST /api/collect — Shopify storefront analytics consent/state ping."""
    body = json.dumps({"v": 1, "s": _COLLECT_SESSION_FLAGS, "r": reason}, separators=(",", ":"))
    headers = {"Content-Type": "application/json"}
    try:
        resp = client.post(f"{shop_url}/api/collect", data=body, headers=headers)
        return resp.status_code
    except Exception:
        return -1


# ──────────────────────── extraction helpers ──────────────────────────

def extract_shop_id(html: str) -> int:
    m = re.search(r'"(?:shop_id|shopId)"\s*:\s*(\d{4,})', html)
    return int(m.group(1)) if m else 0


def extract_session_token(html: str) -> str:
    import html as _html
    m = re.search(r'<meta\s+name="serialized-sessionToken"\s+content="([^"]*)"', _html.unescape(html))
    return _html.unescape(m.group(1)).strip('"') if m else ""


# ──────────────────────── the warmup flow ─────────────────────────────

def human_warmup(client: TLSClient, shop_url: str, variant_id: str,
                 product_id: str = "", product_handle: str = "",
                 shop_id: int = 0) -> Dict:
    """Run the human-like pre-checkout flow, storing every cookie in the single
    session jar and firing telemetry at the correct points.

    Returns the pieces the main checkout flow needs to continue:
      checkout_url, checkout_token, session_token, shop_id
    """
    shop_url = shop_url.rstrip("/")
    out: Dict = {"checkout_url": "", "checkout_token": "", "session_token": "", "shop_id": shop_id}

    # 1) Storefront landing — warm the session, let Shopify set its cookies
    landing_start = _now_ms()
    landing = client.get(shop_url + "/", timeout=20)
    if not out["shop_id"]:
        out["shop_id"] = extract_shop_id(landing.text)

    # 2) Human reading delay before interacting (2-4s)
    time.sleep(random.uniform(2.0, 4.0))

    # 3) Browse the product page (human looks at the item)
    if product_handle:
        try:
            client.get(f"{shop_url}/products/{product_handle}.js", timeout=15)
        except Exception:
            pass

    # 4) Cart add — the real storefront form, not the permalink shortcut
    form = (
        f"form_type=product&utf8=%E2%9C%93&id={variant_id}"
        + (f"&product-id={product_id}" if product_id else "")
        + "&quantity=1"
    )
    headers = {
        "Content-Type": "application/x-www-form-urlencoded",
        "X-Requested-With": "XMLHttpRequest",
        "Origin": shop_url,
        "Referer": shop_url + (f"/products/{product_handle}" if product_handle else "/"),
    }
    client.post(f"{shop_url}/cart/add.js", data=form, headers=headers, timeout=15)

    # 5) Cart state (confirms the line item, sets cart cookies)
    client.get(f"{shop_url}/cart.js", timeout=15)

    # 6) Human reading delay before hitting checkout (3-5s)
    time.sleep(random.uniform(3.0, 5.0))

    # 7) Checkout initiation — POST /cart (302) then land on /checkouts/cn/<token>
    checkout_resp = client.post(f"{shop_url}/cart", data={"checkout": ""},
                                allow_redirects=True, timeout=20)
    checkout_url = str(checkout_resp.url)
    out["checkout_url"] = checkout_url
    m = re.search(r"/checkouts/cn/([^/?]+)", checkout_url)
    out["checkout_token"] = m.group(1) if m else ""
    out["session_token"] = extract_session_token(checkout_resp.text)

    # 8) Telemetry hits, in the order a real browser fires them
    fire_site_abandonment(
        client, shop_url, out["shop_id"], "index",
        landing_start, _now_ms() - landing_start,
        out["session_token"] or ZERO_SESSION_TOKEN,
    )
    collect_analytics(client, shop_url, "change")
    if out["checkout_token"]:
        fire_checkout_track(
            client, shop_url, out["shop_id"], "cart_information",
            out["checkout_token"], variant_id, product_id, "1.00",
        )

    return out


if __name__ == "__main__":
    import sys
    shop = sys.argv[1] if len(sys.argv) > 1 else "https://www.hatchcollection.com"
    vid  = sys.argv[2] if len(sys.argv) > 2 else "45707137229"
    pid  = sys.argv[3] if len(sys.argv) > 3 else "10866027917"
    handle = sys.argv[4] if len(sys.argv) > 4 else "the-cotton-brief"

    c = TLSClient(timeout=20)
    try:
        res = human_warmup(c, shop, vid, pid, handle)
        print("warmup result:", json.dumps(res, indent=2))
        print("cookie count (jar):", len(c.session.cookies))
    finally:
        c.close()
