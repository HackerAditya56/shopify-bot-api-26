# ─────────────────────────────────────────────────────────
#  Shopify Checker API — config
#  All values can be overridden via environment variables
#  (Railway supplies PORT automatically)
# ─────────────────────────────────────────────────────────

import os

# Host/port — Railway sets PORT for you; fallbacks for local dev
HOST = os.environ.get("CHECKER_HOST", "0.0.0.0")
PORT = int(os.environ.get("CHECKER_PORT", os.environ.get("PORT", "8080")))

# Per-request budget for a full checkout run
REQUEST_TIMEOUT = int(os.environ.get("CHECKER_TIMEOUT", "120"))

# Uvicorn workers. Keep 1 by default (cheap Railway plans, in-memory caches).
WORKERS = int(os.environ.get("CHECKER_WORKERS", "15"))

# Keep-alive for long-lived connections (499s usually come from the client /
# load balancer giving up, so we tune this to be forgiving)
UA_KEEP_ALIVE = int(os.environ.get("CHECKER_KEEP_ALIVE", "55"))

# API key for auth — leave empty to disable auth
CHECKER_API_KEY = os.environ.get("CHECKER_API_KEY", "")

# Site list files (used only for the optional random-site helper)
SITE_FILE     = os.environ.get("SITE_FILE",     "site.txt")
SITE_LOW_FILE = os.environ.get("SITE_LOW_FILE", "site_low.txt")
SITE_MID_FILE = os.environ.get("SITE_MID_FILE", "site_mid.txt")
