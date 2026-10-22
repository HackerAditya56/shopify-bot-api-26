"""Check what different endpoints return for Shopify sites."""
import asyncio
import aiohttp

URLS = [
    "https://scrap-addicts.myshopify.com",
    "https://garners-natural-life.myshopify.com",
]


async def fetch(s, u, ep):
    url = u.rstrip("/") + ep
    try:
        async with s.get(url, allow_redirects=False, timeout=aiohttp.ClientTimeout(total=10)) as r:
            text = await r.text()
            return r.status, len(text), text[:80].replace("\n", " ")
    except Exception as e:
        return None, 0, f"{type(e).__name__}: {e}"


async def main():
    async with aiohttp.ClientSession() as s:
        for u in URLS:
            print(f"\n=== {u} ===")
            for ep in ["", "/products.json?limit=1", "/collections/all.json?limit=1"]:
                status, length, snippet = await fetch(s, u, ep)
                print(f"  {ep:35}  {status}  len={length}  body[:80]={snippet!r}")


asyncio.run(main())
