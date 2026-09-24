#!/usr/bin/env python3
"""
Continuously stream Railway logs (project astonishing-empathy, service HGG).
Whenever a log line contains site= and proxy= in the /shopii API format,
store the site and proxy in site.txt / proxy.txt — skip if already present.

Proxy saved WITHOUT scheme (user:pass@host:port) — the format /shopii accepts.
Site saved as full URL with trailing slash stripped.

Reconnects automatically if the log stream drops.

Run:   .venv/bin/python watch_logs.py
Stop:  Ctrl+C
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
import time
import urllib.parse
from pathlib import Path

BASE = Path(__file__).resolve().parent
SITE_FILE = BASE / "site.txt"
PROXY_FILE = BASE / "proxy.txt"

PROJECT = "969ac7c6-0a75-444b-a16f-369aa9f0b704"
ENV = "7cbfddf1-382b-44a8-8e0c-24490ea3a375"
SERVICE = "HGG"

SITE_RE = re.compile(r"site=([^&\s\"'<>]+)", re.IGNORECASE)
PROXY_RE = re.compile(r"proxy=([^&\s\"'<>]+)", re.IGNORECASE)

RECONNECT_DELAY = 3


def norm_site(value: str) -> str:
    return value.strip().rstrip("/")


def norm_proxy(value: str) -> str:
    value = value.strip()
    if "://" in value:
        value = value.split("://", 1)[1]
    return value


def load_set(path: Path) -> set[str]:
    if not path.is_file():
        return set()
    return {line.strip().lower() for line in path.read_text(encoding="utf-8", errors="replace").splitlines() if line.strip()}


def append_unique(path: Path, values: list[str], seen: set[str]) -> None:
    new = []
    for value in values:
        key = value.lower()
        if key and key not in seen:
            seen.add(key)
            new.append(value)
    if new:
        with path.open("a", encoding="utf-8") as fh:
            for value in new:
                fh.write(value + "\n")
        for value in new:
            print(f"[{path.name}] + {value}", flush=True)


def stream_once(seen_sites: set[str], seen_proxies: set[str]) -> None:
    cmd = [
        "railway", "logs",
        "--project", PROJECT,
        "--environment", ENV,
        "--service", SERVICE,
        "--json",
    ]
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True)
    try:
        assert proc.stdout is not None
        for line in proc.stdout:
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except Exception:
                continue
            msg = obj.get("message")
            if not isinstance(msg, str):
                continue

            sites = [norm_site(urllib.parse.unquote(m)) for m in SITE_RE.findall(msg)]
            proxies = [norm_proxy(urllib.parse.unquote(m)) for m in PROXY_RE.findall(msg)]

            if sites:
                append_unique(SITE_FILE, sites, seen_sites)
            if proxies:
                append_unique(PROXY_FILE, proxies, seen_proxies)
    finally:
        try:
            proc.kill()
        except Exception:
            pass


def main() -> None:
    seen_sites = load_set(SITE_FILE)
    seen_proxies = load_set(PROXY_FILE)

    print(f"streaming: railway logs --project {PROJECT} --environment {ENV} --service {SERVICE} --json", flush=True)
    print(f"preloaded: sites={len(seen_sites)} proxies={len(seen_proxies)}", flush=True)

    while True:
        try:
            stream_once(seen_sites, seen_proxies)
        except KeyboardInterrupt:
            print("stopped", flush=True)
            break
        except Exception as exc:
            print(f"stream error: {exc}", flush=True)
        print(f"stream ended, reconnecting in {RECONNECT_DELAY}s...", flush=True)
        time.sleep(RECONNECT_DELAY)


if __name__ == "__main__":
    main()
