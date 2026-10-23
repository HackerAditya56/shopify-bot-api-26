#!/usr/bin/env python3
"""Generate a fresh Pyrogram session string for scr.py.

The string in scr.py was revoked by Telegram
(AUTH_KEY_UNREGISTERED), so /scr cannot start its user client.

Run this on the bot host:

    cd "$(dirname "$0")/.."
    venv/bin/python tools/pyro_login.py --write

It asks for the phone number in international format, the login code
Telegram sends, and the 2FA password if one is set.  The resulting
string is printed and, with --write, patched straight into scr.py.

Notes:
  * The account must be the one that should do the scraping; it joins
    the sites' channels, so use the account you already use for /scr.
  * Nothing is written to disk: the client runs in_memory=True.
"""
from __future__ import annotations

import argparse
import asyncio
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCR = ROOT / "scr.py"


def _read_api():
    """Pull API_ID / API_HASH out of scr.py so there is one source of truth."""
    src = SCR.read_text(encoding="utf-8")
    api_id = re.search(r"^API_ID\s*=\s*(\d+)", src, re.M)
    api_hash = re.search(r'^API_HASH\s*=\s*"([^"]+)"', src, re.M)
    if not (api_id and api_hash):
        sys.exit("could not find API_ID / API_HASH in scr.py")
    return int(api_id.group(1)), api_hash.group(1)


def _patch(session: str) -> None:
    src = SCR.read_text(encoding="utf-8")
    new_block = f'SESSION_STRING = (\n    "{session}"\n)'
    pattern = re.compile(r'^SESSION_STRING\s*=\s*\(.*?^\)', re.S | re.M)
    if not pattern.search(src):
        sys.exit("could not locate the SESSION_STRING block in scr.py")
    SCR.write_text(pattern.sub(new_block, src, count=1), encoding="utf-8")
    print(f"[+] scr.py SESSION_STRING replaced ({len(session)} chars)")


async def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--write", action="store_true", help="patch scr.py automatically")
    args = ap.parse_args()

    from pyrogram import Client

    api_id, api_hash = _read_api()
    print(f"[*] API_ID {api_id}  — signing in. Phone format: +91XXXXXXXXXX")
    async with Client("login_tmp", api_id=api_id, api_hash=api_hash, in_memory=True) as app:
        me = await app.get_me()
        session = await app.export_session_string()
    print("\n[+] signed in as", me.first_name, f"(@{me.username})" if me.username else "")
    print("\nSESSION_STRING:\n" + session + "\n")
    if args.write:
        _patch(session)
        print("[+] done — restart the bot to bring /scr online")


if __name__ == "__main__":
    asyncio.run(main())
