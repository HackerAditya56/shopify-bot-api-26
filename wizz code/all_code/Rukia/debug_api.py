"""
Debug script: Hit the new Shopify API directly and dump the raw JSON.
Run this and share the output so we can map the response keys correctly.

Usage:
    python debug_api.py
"""
import asyncio
import json
import aiohttp
from shopify_api import SHOPIFY_API_URLS, _build_params


TEST_CARD = "4807092200568438|07|28|357"
TEST_SITE = "https://powerbuild.store"
TEST_PROXY = "http://purevpn0s12153504:1LTpwxbCJbEdXo@px041202.pointtoserver.com:10780"

TIMEOUT = 90  # bumped up — new API is slow


async def test_one(api_url: str, renames, label: str):
    print(f"\n{'=' * 70}")
    print(f"Testing {label}: {api_url}")
    print(f"Timeout: {TIMEOUT}s")
    print(f"{'=' * 70}")

    params = _build_params(TEST_CARD, TEST_SITE, TEST_PROXY, renames)
    print(f"Query params: { {k: (v[:30] + '...' if len(v) > 30 else v) for k, v in params.items()} }")

    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(
                api_url,
                params=params,
                timeout=aiohttp.ClientTimeout(total=TIMEOUT),
            ) as resp:
                text = await resp.text()
                print(f"HTTP Status: {resp.status}")
                print(f"--- Raw response (first 2000 chars) ---")
                print(text[:2000])
                print(f"--- End raw ---")
                try:
                    data = json.loads(text)
                    print(f"\n--- Parsed JSON (formatted) ---")
                    print(json.dumps(data, indent=2))
                    print(f"\n--- Top-level keys ---")
                    for k in data.keys():
                        v = data[k]
                        if isinstance(v, str) and len(v) > 80:
                            v = v[:80] + "..."
                        print(f"  {k!r}: {v!r}")
                except Exception as e:
                    print(f"(Could not parse as JSON: {e})")
    except Exception as e:
        print(f"Request FAILED: {type(e).__name__}: {e}")


async def main():
    for idx, (api_url, renames) in enumerate(SHOPIFY_API_URLS):
        label = "PRIMARY" if idx == 0 else f"BACKUP #{idx}"
        await test_one(api_url, renames, label)


if __name__ == "__main__":
    asyncio.run(main())
