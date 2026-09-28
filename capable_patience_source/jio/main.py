#!/usr/bin/env python3
"""Run the Jio Recharge Checker API on :9090 (separate from the Telegram bot).

Usage:  cd capable_patience_source/jio && python3 main.py

The API requires a proxy on every /check request and does NOT read any
proxies.txt. The bot supplies proxies from its own proxy.txt.
"""
import uvicorn

if __name__ == "__main__":
    uvicorn.run("api:app", host="0.0.0.0", port=9090, reload=False)
