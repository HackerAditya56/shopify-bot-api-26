"""
bms_proxy_pool.py — the BMS gate's proxy source: generated webshare rotating
proxies (bms_proxy.txt) + the user's own DB pool.

Also provides prune: a webshare rotating proxy that reports "Bandwidth limit
reached" (free 1GB burned) is removed from bms_proxy.txt automatically.
"""
import logging
import os

_ROOT = os.path.dirname(os.path.abspath(__file__))        # capable_patience_source
REPO = os.path.dirname(_ROOT)                              # shopify root
BMS_PROXY = os.path.join(REPO, "bms_proxy.txt")


def load_bms_proxies() -> list:
    """Return the generated webshare rotating proxy lines (p.webshare.io:80:...)."""
    out = []
    try:
        with open(BMS_PROXY, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#"):
                    out.append(line)
    except Exception:
        pass
    return out


OWNER_ID = 8462705169

_DEV_NOTIFY_TEXT = (
    "🚨 <b>𝐁𝐌𝐒 𝐏𝐫𝐨𝐱𝐲 𝐅𝐥𝐚𝐠𝐠𝐞𝐝 + 𝐑𝐞𝐦𝐨𝐯𝐞𝐝</b> 🚨\n"
    "━━━━━━━━━━━━━━━━━━━━━\n"
    "🧭 <b>𝐏𝐫𝐨𝐱𝐲</b> ➠ <code>{proxy}</code>\n"
    "⚙️ <i>dropped from bms_proxy.txt mid-check</i>"
)


async def prune_and_notify(proxy: str, bot) -> bool:
    """Remove a flagged proxy from bms_proxy.txt + DM the dev."""
    removed = prune_bms_proxy(proxy)
    if removed and bot:
        try:
            await bot.send_message(OWNER_ID, _DEV_NOTIFY_TEXT.format(proxy=proxy), parse_mode="HTML")
        except Exception as e:
            logging.warning(f"[bms_proxy] dev notify failed: {e}")
    return removed


def is_rotating(proxy: str) -> bool:
    """True for webshare rotating endpoints (p.webshare.io + -rotate user) —
    these rotate to a fresh IP per request, so a single 403 is NOT fatal."""
    p = str(proxy or "")
    return "p.webshare.io" in p and "-rotate" in p


def prune_bms_proxy(line: str) -> bool:
    """Remove a burned proxy from bms_proxy.txt. Returns True if removed."""
    try:
        with open(BMS_PROXY, encoding="utf-8") as f:
            lines = [l.strip() for l in f if l.strip()]
        kept = [l for l in lines if l != line.strip()]
        if len(kept) == len(lines):
            return False
        with open(BMS_PROXY, "w", encoding="utf-8") as f:
            f.write("\n".join(kept) + ("\n" if kept else ""))
        logging.warning(f"[bms_proxy] pruned burned proxy: {line}")
        return True
    except Exception as e:
        logging.error(f"[bms_proxy] prune {line}: {e}")
        return False
