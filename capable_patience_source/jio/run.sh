#!/usr/bin/env bash
# Host the Jio Recharge Checker API on port 9090 (separate from the bot).
cd "$(dirname "$0")"
exec python3 main.py
