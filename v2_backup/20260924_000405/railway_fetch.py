#!/usr/bin/env python3
"""
Fetch Shopify checker logs from Railway (project astonishing-empathy, service HGG),
extract site= and proxy= query params, dedupe, and save to site.txt / proxy.txt.

Modes:
  --mode once    paginate full available history (backwards) and save
  --mode watch   keep fetching new logs for --seconds and save continuously

Proxy entries are saved WITHOUT scheme (user:pass@host:port), matching the API.
Sites are saved as full URLs with trailing slashes stripped.
"""

from __future__ import annotations

import argparse
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

PAGE_SIZE = 5000
POLL_SECONDS = 10

SITE_RE = re.compile(r"site=([^&\s\"'<>]+)", re.IGNORECASE)
PROXY_RE = re.compile(r"proxy=([^&\s\"'<>]+)", re.IGNORECASE)


def run_logs(args: list[str]) -> str:
    cmd = [
        "railway", "logs",
        "--project", PROJECT,
        "--environment", ENV,
        "--service", SERVICE,
        "--json",
    ] + args
    proc = subprocess.run(cmd, capture_output=True, text=True)
    return proc.stdout


def parse_logs(text: str) -> list[dict]:
    objs = []
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            objs.append(json.loads(line))
        except Exception:
            continue
    return objs


def clean_site(value: str) -> str:
    return value.strip().rstrip("/")


def clean_proxy(value: str) -> str:
    value = value.strip()
    if "://" in value:
        value = value.split("://", 1)[1]
    return value


def extract(objs: list[dict]) -> tuple[list[str], list[str]]:
    sites: list[str] = []
    proxies: list[str] = []
    for obj in objs:
        msg = obj.get("message")
        if not isinstance(msg, str):
            continue
        for m in SITE_RE.finditer(msg):
            val = urllib.parse.unquote(m.group(1)).strip()
            if val:
                sites.append(clean_site(val))
        for m in PROXY_RE.finditer(msg):
            val = urllib.parse.unquote(m.group(1)).strip()
            if val:
                proxies.append(clean_proxy(val))
    return sites, proxies


def load_existing(path: Path) -> list[str]:
    if not path.is_file():
        return []
    return [l.strip() for l in path.read_text(encoding="utf-8", errors="replace").splitlines() if l.strip()]


def _union(existing: list[str], new: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for value in existing + new:
        key = value.lower()
        if key not in seen:
            seen.add(key)
            out.append(value)
    return out


def merge_save(sites: list[str], proxies: list[str]) -> tuple[int, int]:
    sites = _union(load_existing(SITE_FILE), sites)
    proxies = _union(load_existing(PROXY_FILE), proxies)
    SITE_FILE.write_text("\n".join(sites) + ("\n" if sites else ""), encoding="utf-8")
    PROXY_FILE.write_text("\n".join(proxies) + ("\n" if proxies else ""), encoding="utf-8")
    return len(sites), len(proxies)


def mode_once(max_pages: int = 600) -> None:
    all_sites: list[str] = []
    all_proxies: list[str] = []
    until: str | None = None

    for page in range(1, max_pages + 1):
        args = ["--lines", str(PAGE_SIZE)]
        if until:
            args += ["--until", until]
        text = run_logs(args)
        objs = parse_logs(text)
        if not objs:
            print(f"page {page}: no logs, stopping", flush=True)
            break

        sites, proxies = extract(objs)
        all_sites.extend(sites)
        all_proxies.extend(proxies)

        timestamps = [o.get("timestamp") for o in objs if o.get("timestamp")]
        if not timestamps:
            break
        oldest = min(timestamps)
        print(f"page {page}: {len(objs)} lines, oldest {oldest}, "
              f"unique_sites={len(set(s.lower() for s in all_sites))} "
              f"unique_proxies={len(set(p.lower() for p in all_proxies))}",
              flush=True)
        until = oldest
        if len(objs) < PAGE_SIZE:
            break

    total_sites, total_proxies = merge_save(all_sites, all_proxies)
    print(f"DONE once: site.txt={total_sites}  proxy.txt={total_proxies}", flush=True)


def mode_watch(seconds: int) -> None:
    end_at = time.time() + seconds
    last_ts: str | None = None

    print(f"WATCH start for {seconds}s", flush=True)
    while time.time() < end_at:
        args = ["--lines", str(PAGE_SIZE)]
        if last_ts:
            args += ["--since", last_ts]
        text = run_logs(args)
        objs = parse_logs(text)
        sites, proxies = extract(objs)

        if sites or proxies:
            total_sites, total_proxies = merge_save(sites, proxies)
            print(f"[{time.strftime('%H:%M:%S')}] new_sites={len(set(s.lower() for s in sites))} "
                  f"new_proxies={len(set(p.lower() for p in proxies))} "
                  f"totals sites={total_sites} proxies={total_proxies}", flush=True)

        timestamps = [o.get("timestamp") for o in objs if o.get("timestamp")]
        if timestamps:
            last_ts = max(timestamps)

        remaining = end_at - time.time()
        sleep_for = min(POLL_SECONDS, max(1.0, remaining))
        time.sleep(sleep_for)

    print("WATCH done", flush=True)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=["once", "watch"], default="once")
    parser.add_argument("--seconds", type=int, default=300)
    parser.add_argument("--max-pages", type=int, default=600)
    args = parser.parse_args()

    if args.mode == "once":
        mode_once(args.max_pages)
    else:
        mode_watch(args.seconds)


if __name__ == "__main__":
    main()
