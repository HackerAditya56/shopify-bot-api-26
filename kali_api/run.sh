#!/usr/bin/env bash
# kali_api launcher — Shopify gate checker (flask + curl_cffi)
set -euo pipefail
cd "$(dirname "$0")"
export PORT="${PORT:-8090}"
export KALI_API_URL="${KALI_API_URL:-http://127.0.0.1:${PORT}/shopii}"
exec "${PYTHON:-/usr/bin/python3}" main.py
