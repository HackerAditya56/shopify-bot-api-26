"""
telemetry_v2.py — Shopify telemetry tracker for the v2 human-like flow.

Fires the real tracking endpoints decoded from hatch_session.har, with session
data captured as the checkout progresses. Every emitter is fire-and-forget:
errors are swallowed so a telemetry failure never breaks the checkout.

Endpoints:
  - monorail-edge.shopifysvc.com/v1/produce        (single beacon)
  - monorail-edge.shopifysvc.com/unstable/produce_batch
  - otlp-http-production.shopifysvc.com/v1/metrics (web-pixels-manager)
  - otlp-http-production.shopifysvc.com/v1/logs    (shop-js)
  - <shop>/api/collect                             (storefront analytics)
"""

from __future__ import annotations

import json
import time
from typing import Optional

MONORAIL_PRODUCE = "https://monorail-edge.shopifysvc.com/v1/produce"
MONORAIL_BATCH   = "https://monorail-edge.shopifysvc.com/unstable/produce_batch"
OTLP_METRICS     = "https://otlp-http-production.shopifysvc.com/v1/metrics"
OTLP_LOGS        = "https://otlp-http-production.shopifysvc.com/v1/logs"

ZERO_SESSION_TOKEN = "00000000-0000-0000-5000-000000000000"

_COLLECT_FLAGS = {
    "wd": False, "ua": False, "cf": True, "be": True, "nm": False,
    "nc": False, "ka": False, "sa": False, "ta": False, "pt": False,
    "mp": False, "sd": False,
}


def _now_ms() -> int:
    return int(time.time() * 1000)


def _now_ns() -> int:
    return int(time.time() * 1_000_000_000)


class Tracker:
    """Holds the evolving session context and fires matching telemetry.

    Update the context as the flow progresses (shop_id, checkout_token,
    session_token, variant/product/price), then call the phase emitters.
    """

    def __init__(self, client, shop_url: str):
        self.client = client
        self.shop_url = shop_url.rstrip("/")
        self.shop_id = 0
        self.checkout_token = ""
        self.session_token = ZERO_SESSION_TOKEN
        self.variant_id = ""
        self.product_id = ""
        self.price = "1.00"
        self.currency = "USD"

    # ---- context setters ----
    def set_shop(self, shop_id: int) -> None:
        self.shop_id = shop_id or self.shop_id

    def set_checkout(self, checkout_token: str, session_token: str = "") -> None:
        if checkout_token:
            self.checkout_token = checkout_token
        if session_token:
            self.session_token = session_token

    def set_item(self, variant_id: str, product_id: str, price: str) -> None:
        self.variant_id = str(variant_id) if variant_id else self.variant_id
        self.product_id = str(product_id) if product_id else self.product_id
        if price:
            self.price = str(price)

    # ---- low-level senders ----
    async def _post(self, url: str, body: str, headers: dict) -> int:
        try:
            r = await self.client.post(url, data=body, headers=headers, timeout=10)
            return r.status_code
        except Exception:
            return -1

    async def monorail(self, schema_id: str, payload: dict) -> int:
        now = _now_ms()
        body = json.dumps({
            "schema_id": schema_id,
            "payload": payload,
            "metadata": {"event_created_at_ms": now, "event_sent_at_ms": now},
        }, separators=(",", ":"))
        return await self._post(MONORAIL_PRODUCE, body, {
            "Content-Type": "text/plain;charset=UTF-8",
            "Origin": self.shop_url,
            "Referer": self.shop_url + "/",
        })

    async def collect(self, reason: str = "change") -> int:
        body = json.dumps({"v": 1, "s": _COLLECT_FLAGS, "r": reason}, separators=(",", ":"))
        return await self._post(self.shop_url + "/api/collect", body, {
            "Content-Type": "application/json",
        })

    async def otlp_metric(self, event_name: str, service: str = "web-pixels-manager",
                          surface: str = "storefront-renderer") -> int:
        ns = _now_ns()
        data_point = {
            "startTimeUnixNano": ns, "timeUnixNano": ns, "asDouble": 1,
            "attributes": [
                {"key": "surface", "value": {"stringValue": surface}},
                {"key": "feature", "value": {"stringValue": "event_emission"}},
                {"key": "event_name", "value": {"stringValue": event_name}},
                {"key": "user_can_be_tracked", "value": {"stringValue": "false"}},
            ],
        }
        metric = {
            "name": "web_pixels_manager_feature_usage", "unit": "1",
            "sum": {"aggregationTemporality": 1, "isMonotonic": True, "dataPoints": [data_point]},
        }
        scope_metric = {
            "scope": {"name": "open-telemetry-mini-client", "version": "1.1.0", "attributes": []},
            "metrics": [metric],
        }
        resource_metric = {
            "resource": {"attributes": [{"key": "service.name", "value": {"stringValue": service}}]},
            "scopeMetrics": [scope_metric],
        }
        body = json.dumps({"resourceMetrics": [resource_metric]}, separators=(",", ":"))
        return await self._post(OTLP_METRICS, body, {
            "Content-Type": "application/json",
            "Origin": self.shop_url,
            "Referer": self.shop_url + "/",
        })

    async def otlp_log(self, message: str, feature: str = "ShopCartSync") -> int:
        ns = _now_ns()
        record = {
            "timeUnixNano": ns, "observedTimeUnixNano": ns,
            "attributes": [
                {"key": "beta", "value": {"boolValue": True}},
                {"key": "feature", "value": {"stringValue": feature}},
            ],
            "body": {"stringValue": message},
        }
        scope_log = {
            "scope": {"name": "open-telemetry-mini-client", "version": "1.1.0", "attributes": []},
            "logRecords": [record],
        }
        resource_log = {
            "resource": {"attributes": [{"key": "service.name", "value": {"stringValue": "shop-js"}}]},
            "scopeLogs": [scope_log],
        }
        body = json.dumps({"resourceLogs": [resource_log]}, separators=(",", ":"))
        return await self._post(OTLP_LOGS, body, {
            "Content-Type": "application/json",
            "Origin": self.shop_url,
            "Referer": self.shop_url + "/",
        })

    # ---- phase emitters (order mirrors the HAR) ----
    async def storefront_landing(self) -> None:
        """Landing phase: web-pixels 'Page Viewed' metric + collect ping."""
        await self.otlp_metric("Page Viewed")
        await self.collect("change")

    async def site_abandonment(self, page_type: str, nav_start_ms: int,
                               duration_ms: int) -> None:
        """Fired when leaving a storefront page — the 'human lingered' signal."""
        await self.monorail("online_store_buyer_site_abandonment/1.1", {
            "shop_id": self.shop_id,
            "url": self.shop_url + "/",
            "navigation_start": nav_start_ms,
            "duration": duration_ms,
            "session_token": self.session_token,
            "page_type": page_type,
        })

    async def cart_added(self) -> None:
        """Cart phase: ShopCartSync log + cart_information track."""
        await self.otlp_log("ShopCartSync recognition TTL applied", "ShopCartSync")
        if self.checkout_token:
            await self.monorail("checkout_track/3.8", self._cart_track_payload("cart_information"))

    async def checkout_loaded(self) -> None:
        """Checkout init: lifecycle + interaction events."""
        if not self.checkout_token:
            return
        await self.monorail("checkout_lifecycle_events/7.7", {
            "shop_id": self.shop_id,
            "checkout_token": self.checkout_token,
            "event_name": "checkout_started",
            "checkout_platform": "checkout_one",
            "event_time": _now_ms(),
        })
        await self.monorail("checkout_c1_interaction_and_impression_events/2.25", {
            "shop_id": self.shop_id,
            "session_token": self.session_token,
            "checkout_token": self.checkout_token,
            "event_name": "page_viewed",
            "event_type": "impression",
            "step": "onePage",
        })

    async def address_completed(self) -> None:
        if not self.checkout_token:
            return
        await self.monorail("checkout_address_completion/1.0", {
            "shop_id": self.shop_id,
            "checkout_token": self.checkout_token,
            "country": self.currency,
            "section": "shipping_address",
            "completed_fields": 8,
            "is_billing_default_to_shipping_address": True,
        })

    async def card_entered(self) -> None:
        if not self.checkout_token:
            return
        await self.monorail("checkout_credit_card_number_interaction/1.1", {
            "checkout_token": self.checkout_token,
            "payment_method_identifier": "card",
            "display_name": "Card",
            "event_name": "card_number_entered",
        })

    async def checkout_submitted(self) -> None:
        if not self.checkout_token:
            return
        await self.monorail("checkout_track/3.8", self._cart_track_payload("checkout_completed"))
        await self.monorail("checkout_lifecycle_events/7.7", {
            "shop_id": self.shop_id,
            "checkout_token": self.checkout_token,
            "event_name": "checkout_completed",
            "checkout_platform": "checkout_one",
            "event_time": _now_ms(),
        })

    def _cart_track_payload(self, event_name: str) -> dict:
        return {
            "event_name": event_name,
            "cart_token": self.checkout_token,
            "shop_id": self.shop_id,
            "event_timestamp_epoch_ms": _now_ms(),
            "user_agent": getattr(self.client, "user_agent", ""),
            "content_language": "en-US",
            "action_name": "query",
            "line_item_product_ids": [int(self.product_id)] if self.product_id else [],
            "line_item_variant_ids": [int(self.variant_id)] if self.variant_id else [],
            "line_item_total_price": [self.price],
            "line_item_total_price_usd": [self.price],
            "line_item_quantity": [1],
            "currency": self.currency,
            "total_item_count": 1,
            "api_client_id": 580111,
            "current_api_client_id": 580111,
            "current_step": "onePage",
            "checkout_token": self.checkout_token,
            "source_processor": "web_checkout",
            "subtotal_price": self.price,
            "source_name": "checkout_one",
            "distinct_item_count": 1,
            "javascript_enabled": True,
            "checkout_platform": "checkout_one",
        }
