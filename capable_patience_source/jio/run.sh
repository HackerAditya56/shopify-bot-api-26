#!/usr/bin/env bash
# Host the Jio Recharge Checker API on port 9090 (separate from the bot).
# Run this BEFORE starting the bot:  bash jio/run.sh
cd "$(dirname "$0")"
exec uvicorn api:app --host 0.0.0.0 --port 9090
