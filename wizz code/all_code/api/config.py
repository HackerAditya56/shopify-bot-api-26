# ─────────────────────────────────────────────────────────
#  Shopify Checker API — config (VPS edition)
#  All values can be overridden via environment variables
# ─────────────────────────────────────────────────────────

import os

# Host/port — bind to all interfaces so the VPS public IP works
HOST = os.environ.get("CHECKER_HOST", "0.0.0.0")
PORT = int(os.environ.get("CHECKER_PORT", os.environ.get("PORT", "8002")))

# Per-request budget for a full checkout run
REQUEST_TIMEOUT = int(os.environ.get("CHECKER_TIMEOUT", "120"))

# Keep workers = 1 on a small VPS. In-memory caches + a single event loop
# is plenty; more workers just duplicate memory.
WORKERS = int(os.environ.get("CHECKER_WORKERS", "1"))

# Keep-alive for long-lived connections
UA_KEEP_ALIVE = int(os.environ.get("CHECKER_KEEP_ALIVE", "55"))

# API key for auth — leave empty to disable auth
CHECKER_API_KEY = os.environ.get("CHECKER_API_KEY", "")

# Site list used when the caller does not pass ?site=
# Where the site comes from: "file" = SITES_FILE always wins, "request" = honour ?site=
SITE_MODE = os.environ.get("SITE_MODE", "file")

SITES_FILE = os.environ.get(
    "SITES_FILE",
    str(__import__("pathlib").Path(__file__).resolve().parent.parent / "v4-main" / "sites.txt"),
)

# Site list files (used only for the optional random-site helper)
SITE_FILE     = os.environ.get("SITE_FILE",     "site.txt")
SITE_LOW_FILE = os.environ.get("SITE_LOW_FILE", "site_low.txt")
SITE_MID_FILE = os.environ.get("SITE_MID_FILE", "site_mid.txt")

# Prefer IPv4 by default — broken IPv6 is a very common cause of
# "connection timed out" on cheap VPS providers.
os.environ.setdefault("AIOHTTP_RESOLVER_IPV4", "1")