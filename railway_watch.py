#!/usr/bin/env python3
"""
Railway log watcher — continuously extracts site= and proxy= from the logs of
TWO Railway projects, dedupes, and appends to site.txt / proxy.txt.

Runs until Ctrl+C. Each poll prints how many new entries were added and how
many were skipped (already present).

Standalone tool: it only reads logs via the `railway` CLI and writes two local
text files. It does not touch anything else.

Usage:
    python3 railway_watch.py
    python3 railway_watch.py --interval 15 --backfill 6h --site-file site.txt --proxy-file proxy.txt
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

POLL_INTERVAL = 15      # seconds between polls
BACKFILL = "1h"         # initial historical window on startup ("" = skip backfill)

# Railway projects to watch: project id + environment id + service id.
# service id can also be replaced by the service name.
PROJECTS = [
    {
        "name": "thriving-amazement",
        "project": "c24b7209-1efb-46c8-9d01-5900896e51ff",
        "environment": "90c8e87c-4535-4db2-bdb5-9b2b264ee69c",
        "service": "736a08e4-cb9d-426e-b1f7-d44f01ac455a",
    },
    {
        "name": "astonishing-empathy",
        "project": "969ac7c6-0a75-444b-a16f-369aa9f0b704",
        "environment": "7cbfddf1-382b-44a8-8e0c-24490ea3a375",
        "service": "eaa0c103-62ac-4359-9bf0-5ace7298c4ff",
    },
]

SITE_RE = re.compile(r"site=([^&\s\"'<>]+)", re.IGNORECASE)
PROXY_RE = re.compile(r"proxy=([^&\s\"'<>]+)", re.IGNORECASE)

# A credential may be alphanumeric / safe chars, or a valid %-escape (curl decodes later).
_CRED = r"(?:[A-Za-z0-9._~-]|%[0-9A-Fa-f]{2})+"
VALID_SITE_RE = re.compile(r"^https?://[A-Za-z0-9.-]+(?:\.[A-Za-z0-9.-]+)+/?$")
VALID_PROXY_RE = re.compile(rf"^{_CRED}:{_CRED}@[A-Za-z0-9.-]+:\d{{2,5}}$")


def run_logs(project: str, environment: str, service: str, since: str) -> str:
    """Fetch logs as JSON via the railway CLI. Returns raw stdout (empty on failure)."""
    cmd = [
        "railway", "logs",
        "--project", project,
        "--environment", environment,
        "--service", service,
        "--json",
        "--since", since,
    ]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
    except Exception as e:
        print(f"    ! railway logs failed ({type(e).__name__})", flush=True)
        return ""
    if proc.returncode != 0:
        print(f"    ! railway logs rc={proc.returncode}: {proc.stderr.strip()[:200]}", flush=True)
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
    value = value.strip().rstrip("/")
    if not VALID_SITE_RE.match(value):
        return ""
    return value


def clean_proxy(value: str) -> str:
    value = value.strip()
    if "://" in value:
        value = value.split("://", 1)[1]
    if not VALID_PROXY_RE.match(value):
        return ""
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
            # Do NOT unquote the proxy: credentials arrive URL-encoded and
            # curl needs them encoded (unquoting corrupts % / & / { } passwords).
            val = m.group(1).strip()
            val = clean_proxy(val)
            if val:
                proxies.append(val)
    return sites, proxies


def load_lines(path: Path) -> list[str]:
    if not path.is_file():
        return []
    return [l.strip() for l in path.read_text(encoding="utf-8", errors="replace").splitlines() if l.strip()]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--site-file", default=str(SITE_FILE))
    ap.add_argument("--proxy-file", default=str(PROXY_FILE))
    ap.add_argument("--interval", type=int, default=POLL_INTERVAL)
    ap.add_argument("--backfill", default=BACKFILL, help="initial window, e.g. 6h / 1d (empty to skip)")
    args = ap.parse_args()

    site_file = Path(args.site_file)
    proxy_file = Path(args.proxy_file)
    interval = max(1, args.interval)
    window = f"{interval * 3}s"   # overlapping window so no log slips between polls

    # in-memory dedupe sets, seeded from the existing files (case-insensitive)
    seen_sites = {v.lower() for v in load_lines(site_file)}
    seen_proxies = {v.lower() for v in load_lines(proxy_file)}
    new_sites, new_proxies = [], []
    skipped_sites = skipped_proxies = 0

    print(f"Railway log watcher started.", flush=True)
    print(f"  site file : {site_file}", flush=True)
    print(f"  proxy file: {proxy_file}", flush=True)
    print(f"  interval  : {interval}s (window {window})", flush=True)
    print(f"  projects  : {', '.join(p['name'] for p in PROJECTS)}", flush=True)
    print(f"  existing  : {len(seen_sites)} sites, {len(seen_proxies)} proxies", flush=True)
    print("Press Ctrl+C to stop.", flush=True)
    print("-" * 70, flush=True)

    def sweep(since: str, label: str) -> None:
        nonlocal skipped_sites, skipped_proxies
        batch_sites, batch_proxies = [], []
        for p in PROJECTS:
            text = run_logs(p["project"], p["environment"], p["service"], since)
            objs = parse_logs(text)
            sites, proxies = extract(objs)
            batch_sites.extend(sites)
            batch_proxies.extend(proxies)

        n_add_s = n_add_p = n_skip_s = n_skip_p = 0
        for s in batch_sites:
            k = s.lower()
            if k not in seen_sites:
                seen_sites.add(k)
                new_sites.append(s)
                n_add_s += 1
            else:
                n_skip_s += 1
        for p_ in batch_proxies:
            k = p_.lower()
            if k not in seen_proxies:
                seen_proxies.add(k)
                new_proxies.append(p_)
                n_add_p += 1
            else:
                n_skip_p += 1

        skipped_sites += n_skip_s
        skipped_proxies += n_skip_p

        if new_sites or new_proxies:
            if new_sites:
                with open(site_file, "a", encoding="utf-8") as f:
                    f.write("\n".join(new_sites) + "\n")
            if new_proxies:
                with open(proxy_file, "a", encoding="utf-8") as f:
                    f.write("\n".join(new_proxies) + "\n")
            new_sites.clear()
            new_proxies.clear()

        print(
            f"[{time.strftime('%H:%M:%S')}] {label}: "
            f"+{n_add_s} sites, +{n_add_p} proxies | "
            f"dup {n_skip_s} sites, {n_skip_p} proxies | "
            f"totals {len(seen_sites)} sites, {len(seen_proxies)} proxies",
            flush=True,
        )

    try:
        if args.backfill:
            sweep(args.backfill, f"backfill {args.backfill}")
        while True:
            time.sleep(interval)
            sweep(window, "poll")
    except KeyboardInterrupt:
        print("\nStopped.", flush=True)
        print(f"Final totals: {len(seen_sites)} sites, {len(seen_proxies)} proxies", flush=True)
        print(f"  (this run: {skipped_sites} duplicate sites, {skipped_proxies} duplicate proxies)", flush=True)


if __name__ == "__main__":
    main()
