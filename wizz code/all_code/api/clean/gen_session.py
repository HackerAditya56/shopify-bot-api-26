import asyncio
import os

from telethon import TelegramClient
from telethon.sessions import StringSession

try:
    from clean import API_ID, API_HASH
except Exception:
    API_ID = 0
    API_HASH = ""

env_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")


def _load_env():
    if not os.path.exists(env_path):
        return
    with open(env_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, _, v = line.partition("=")
            os.environ.setdefault(k.strip(), v.strip())


async def main():
    global API_ID, API_HASH
    _load_env()
    API_ID = API_ID or int(os.environ.get("API_ID", "0") or 0)
    API_HASH = API_HASH or os.environ.get("API_HASH", "")

    if not API_ID or not API_HASH:
        print("Set API_ID and API_HASH in clean.py (or in a .env file) before running.")
        return

    async with TelegramClient(StringSession(), API_ID, API_HASH) as client:
        session_str = client.session.save()
        print("\n=== TELETHON_SESSION (paste into clean.py) ===\n")
        print(session_str)
        print("\n=============================================\n")

        out_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "session.txt")
        with open(out_path, "w", encoding="utf-8") as f:
            f.write(session_str)
        print(f"Also saved to {out_path}")


if __name__ == "__main__":
    asyncio.run(main())
