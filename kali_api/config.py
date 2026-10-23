"""
kali_api — configuration (v7/main_v2.py-compatible names).

Edit here, restart the service. Every value is also read from the environment
(env wins), so systemd/docker can override without touching the tree.

    CHECKER_HOST, CHECKER_PORT / PORT     bind address
    CHECKER_WORKERS                       uvicorn processes   (v7: 31)
    CHECKER_TIMEOUT                       per-check seconds   (v7: 120)
    CHECKER_KEEP_ALIVE                    keep-alive seconds  (v7: 55)
    CHECKER_API_KEY                       single key
    KALI_API_KEYS                         comma separated keys (takes priority)

kali-only extras (all optional, sane defaults):
    KALI_MAX_CONCURRENCY                  0 = unlimited (load guard decides)
    KALI_LOAD_MAX_PERCENT                 refuse/park above this load
    KALI_QUEUE_WAIT                       0 = wait forever for a slot
    KALI_SITE_MODE                        "request" (site from caller) | "file"
"""
import os


def _int(name, default):
    try:
        return int(os.environ.get(name, default))
    except (TypeError, ValueError):
        return int(default)


# ── server (v7 names) ─────────────────────────────────────────────────────
HOST = os.environ.get("CHECKER_HOST", "0.0.0.0")
PORT = _int("CHECKER_PORT", os.environ.get("PORT", "8080"))

# uvicorn processes. each worker is a separate process with its own caches,
# its own stats and its own concurrency budget — 31 workers means 31x that.
WORKERS = _int("CHECKER_WORKERS", 31)

# per-check wall clock
REQUEST_TIMEOUT = _int("CHECKER_TIMEOUT", 120)

# keep-alive for idle client connections
UA_KEEP_ALIVE = _int("CHECKER_KEEP_ALIVE", 55)

# ── auth ──────────────────────────────────────────────────────────────────
CHECKER_API_KEY = os.environ.get("CHECKER_API_KEY", "ladle")


def _keys():
    raw = os.environ.get("KALI_API_KEYS") or CHECKER_API_KEY or ""
    return [k.strip() for k in raw.split(",") if k.strip()]


API_KEYS = _keys()

# ── sites (v7 names) ──────────────────────────────────────────────────────
_DEFAULT_SITES = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "v7", "site.txt")

SITE_FILE = os.environ.get("SITE_FILE", _DEFAULT_SITES)
SITE_LOW_FILE = os.environ.get("SITE_LOW_FILE", "site_low.txt")   # v7 compat
SITE_MID_FILE = os.environ.get("SITE_MID_FILE", "site_mid.txt")   # v7 compat

# kali aliases
SITES_FILE = os.environ.get("KALI_SITES_FILE", SITE_FILE)
SITE_MODE = os.environ.get("KALI_SITE_MODE", "request").lower()

# ── limits (kali extras) ──────────────────────────────────────────────────
# How many checks may RUN per worker process.
#   0 = unlimited: run while the box is under LOAD_MAX_PERCENT, queue above it
MAX_CONCURRENCY = _int("KALI_MAX_CONCURRENCY", 0)
LOAD_MAX_PERCENT = _int("KALI_LOAD_MAX_PERCENT", 95)
LOAD_TTL_SECONDS = _int("KALI_LOAD_TTL", 5)
QUEUE_WAIT = _int("KALI_QUEUE_WAIT", 0)
CAPACITY_POLL = _int("KALI_CAPACITY_POLL", 2)

# only used when MAX_CONCURRENCY == 0: the per-process ceiling
THREADS = _int("KALI_TASK_CAP", 1000)

LOG_LEVEL = os.environ.get("KALI_LOG_LEVEL", "INFO")
