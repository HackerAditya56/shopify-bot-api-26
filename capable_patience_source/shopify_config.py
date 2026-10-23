"""
Shared Shopify checker configuration for the bot.

Single and mass Shopify gates read their site list and proxy list from
the extracted files and call the local Shopify checker API.
"""

import os

_BOT_DIR = os.path.dirname(os.path.abspath(__file__))
_SHOPIFY_DIR = os.path.dirname(_BOT_DIR)  # parent dir holds site.txt / proxy.txt

# Local Shopify checker API (kali_api/main.py)
API_URL = os.environ.get("KALI_API_URL", "http://127.0.0.1:8092/shopii")
API_KEY = os.environ.get("KALI_API_KEY", "ladle")

# Site source: the v7 rotation list
SITES_FILE = os.environ.get("KALI_SITES_FILE", os.path.join(_SHOPIFY_DIR, "v7", "site.txt"))
PROXY_FILE = os.path.join(_SHOPIFY_DIR, "proxy.txt")


def load_lines(path):
    """Read non-empty lines, stripped, preserving order."""
    try:
        with open(path, "r", encoding="utf-8", errors="ignore") as f:
            return [line.strip() for line in f if line.strip()]
    except Exception:
        return []


def load_sites():
    return load_lines(SITES_FILE)


def load_proxies():
    return load_lines(PROXY_FILE)


# Convenience list for gates that import PROXY_LIST directly.
PROXY_LIST = load_proxies()
SITES = load_sites()
