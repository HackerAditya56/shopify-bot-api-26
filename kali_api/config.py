"""
kali_api — configuration.

Edit this file, then restart the service. Every value can also be overridden
with an environment variable (the env wins), so systemd/docker can set them
without touching the tree.
"""
import os


def _int(name, default):
    try:
        return int(os.environ.get(name, default))
    except (TypeError, ValueError):
        return int(default)


def _keys():
    raw = os.environ.get("KALI_API_KEYS") or os.environ.get("KALI_API_KEY") or "ladle"
    return [k.strip() for k in raw.split(",") if k.strip()]


# ── server ────────────────────────────────────────────────────────────────
HOST = os.environ.get("KALI_HOST", "0.0.0.0")
PORT = _int("PORT", 8090)

# "auto" -> waitress, then gunicorn, then flask dev server
SERVER  = os.environ.get("KALI_SERVER", "auto")
WORKERS = _int("KALI_WORKERS", 1)      # gunicorn processes (keep 1: shared caches)
# Server threads = how many requests can be INSIDE the process at once
# (running + queued). Keep it >= the burst you expect; waiting is nearly free.
THREADS = _int("KALI_THREADS", 3000)

# ── limits ────────────────────────────────────────────────────────────────
# How many checks may RUN at once.
#   0  -> unlimited: every request is accepted and runs while the box is under
#         LOAD_MAX_PERCENT; above it, requests WAIT (queue) instead of failing.
#   N  -> hard cap of N running checks; extras wait for a free slot.
MAX_CONCURRENCY = _int("KALI_MAX_CONCURRENCY", 0)

# Reject new checks once measured load >= this percent (CPU or RAM, whichever
# is worse). Only consulted while MAX_CONCURRENCY == 0; a positive cap always
# uses the semaphore instead.
LOAD_MAX_PERCENT = _int("KALI_LOAD_MAX_PERCENT", 95)
LOAD_TTL_SECONDS = _int("KALI_LOAD_TTL", 5)     # cache window for the load probe

# Seconds a request may wait for a slot / for the box to cool down.
# 0 = wait forever (the caller just stays connected). 30 = give up with 503.
QUEUE_WAIT = _int("KALI_QUEUE_WAIT", 0)

# How often a queued request re-checks the load while waiting.
CAPACITY_POLL = _int("KALI_CAPACITY_POLL", 2)

# Hard wall-clock budget per check. The running thread is not killed (python
# can't), it simply stops holding the slot; the caller gets TIMEOUT.
REQUEST_TIMEOUT = _int("KALI_REQUEST_TIMEOUT", 120)

# ── auth ──────────────────────────────────────────────────────────────────
# comma separated in KALI_API_KEYS, e.g. KALI_API_KEYS="ladle,abc123"
API_KEYS = _keys()

# ── sites ─────────────────────────────────────────────────────────────────
_DEFAULT_SITES = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "v7", "site.txt")
SITES_FILE = os.environ.get("KALI_SITES_FILE", _DEFAULT_SITES)

# "file"    -> always draw from SITES_FILE (ignores ?site=)
# "request" -> use ?site= when given, file only as fallback
SITE_MODE = os.environ.get("KALI_SITE_MODE", "request")

# ── misc ──────────────────────────────────────────────────────────────────
LOG_LEVEL = os.environ.get("KALI_LOG_LEVEL", "INFO")
