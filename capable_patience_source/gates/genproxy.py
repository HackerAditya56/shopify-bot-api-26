import asyncio
import json
import logging
import os
import random
import subprocess

from aiogram import types, F, Router

from mass_gates._tg_helpers import safe_reply
from proxy_pool import add_proxy_sync

router = Router()

# ── paths ──────────────────────────────────────────────────────────────
_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))   # capable_patience_source
REPO = os.path.dirname(_ROOT)                                          # shopify root
KALI_PROXY = os.path.join(REPO, "v7", "kali_proxy.txt")
BMS_PROXY = os.path.join(REPO, "bms_proxy.txt")
GEN_SCRIPT = os.path.join(_ROOT, "webshare_gen.py")

# ── MinecraftEnchanted premium emoji IDs (unique) ─────────────────────
EMOJI_STAR    = "6136275172283391020"   # ⭐️
EMOJI_SHIELD  = "5323325115411245266"   # 🛡
EMOJI_BOW     = "5323400479202387128"   # 🏹
EMOJI_TARGET  = "5323410860138343577"   # 🎯
EMOJI_COMPASS = "5323308163175327669"   # 🧭
EMOJI_DIAMOND = "5323344825016166715"   # 💎

STAR = f'<tg-emoji emoji-id="{EMOJI_STAR}">⭐️</tg-emoji>'
SHIELD = f'<tg-emoji emoji-id="{EMOJI_SHIELD}">🛡</tg-emoji>'
BOW = f'<tg-emoji emoji-id="{EMOJI_BOW}">🏹</tg-emoji>'
TARGET = f'<tg-emoji emoji-id="{EMOJI_TARGET}">🎯</tg-emoji>'
COMPASS = f'<tg-emoji emoji-id="{EMOJI_COMPASS}">🧭</tg-emoji>'
DIAMOND = f'<tg-emoji emoji-id="{EMOJI_DIAMOND}">💎</tg-emoji>'


def _load(path):
    out = []
    try:
        with open(path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#"):
                    out.append(line)
    except Exception:
        pass
    return out


def _append_bms(line):
    try:
        existing = set(_load(BMS_PROXY))
        if line not in existing:
            with open(BMS_PROXY, "a", encoding="utf-8") as f:
                f.write(line + "\n")
            return True
    except Exception as e:
        logging.error(f"[genproxy] append {line}: {e}")
    return False


def _pick_proxy():
    """Kali (residential) proxies first — datacenter webshare IPs trip reCAPTCHA.
    Only fall back to bms proxies if the kali pool is empty."""
    kali = _load(KALI_PROXY)
    if kali:
        return random.choice(kali), "kali"
    bms = _load(BMS_PROXY)
    if bms:
        return random.choice(bms), "bms"
    return None, None


def _run_generator(proxy):
    cmd = ["xvfb-run", "-a", "python3", GEN_SCRIPT, "--proxy", proxy, "--scheme", "socks5"]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=300, cwd=_ROOT)
        out = (proc.stdout or "").strip()
        # the generator prints one JSON line (last); parse it robustly
        for line in reversed(out.splitlines()):
            line = line.strip()
            if line.startswith("{"):
                try:
                    data = json.loads(line)
                    if data.get("error"):
                        logging.error(f"[genproxy] generator error: {data['error'][:300]}")
                    return data.get("rotating") or None
                except Exception:
                    pass
        if proc.stderr:
            logging.error(f"[genproxy] generator stderr: {proc.stderr.strip()[:400]}")
        else:
            logging.error(f"[genproxy] generator produced no JSON: stdout={out[:200]!r}")
        return None
    except Exception as e:
        logging.error(f"[genproxy] generator error: {e}")
        return None


_GEN_LOCK = asyncio.Lock()


async def _bg_generate_loop(delay: int = 60, fail_delay: int = 300):
    """Background self-sustaining proxy generation.

    On success: wait `delay` (60s). On failure: wait `fail_delay` (5 min) and
    retry — the loop never breaks. Serialised by _GEN_LOCK."""
    while True:
        ok = False
        try:
            proxy, source = _pick_proxy()
            if proxy:
                async with _GEN_LOCK:
                    rotating = await asyncio.to_thread(_run_generator, proxy)
                if rotating:
                    _append_bms(rotating)
                    logging.info(f"[genproxy-bg] generated {rotating} (source={source})")
                    ok = True
                else:
                    logging.warning(f"[genproxy-bg] generation failed (source={source}) — retry in {fail_delay}s")
            else:
                logging.warning(f"[genproxy-bg] no proxies in kali/bms files — retry in {fail_delay}s")
        except Exception as e:
            logging.error(f"[genproxy-bg] {e} — retry in {fail_delay}s")
        await asyncio.sleep(delay if ok else fail_delay)


def start_bg_loop(delay: int = 60):
    """Start the background proxy-generation loop. Returns the task."""
    delay = int(os.environ.get("GENPROXY_BG_DELAY", str(delay)))
    enabled = os.environ.get("GENPROXY_BG", "1") == "1"
    if not enabled:
        logging.info("[genproxy-bg] disabled via GENPROXY_BG=0")
        return None
    return asyncio.create_task(_bg_generate_loop(delay))


@router.message(F.text.startswith("/genproxy"))
async def genproxy_command(message: types.Message):
    user_id = message.from_user.id

    proxy, source = _pick_proxy()
    if not proxy:
        await safe_reply(message, f"{TARGET} <b>𝗡𝗼 𝗽𝗿𝗼𝘅𝗶𝗲𝘀</b> — kali_proxy.txt + bms_proxy.txt are empty.", parse_mode="HTML")
        return

    proc_msg = await safe_reply(message,
        f"<blockquote>{BOW} 𝗚𝗲𝗻𝗲𝗿𝗮𝘁𝗶𝗻𝗴 𝗣𝗿𝗼𝘅𝘆 𝗣𝗹𝗲𝗮𝘀𝗲 𝗪𝗮𝗶𝘁 {BOW}</blockquote>",
        parse_mode="HTML")

    async with _GEN_LOCK:
        rotating = await asyncio.to_thread(_run_generator, proxy)

    if rotating:
        _append_bms(rotating)
        # also hand the proxy to this user's /proxy pool
        given = await asyncio.to_thread(add_proxy_sync, user_id, rotating)
        lines = [
            f"<blockquote>{STAR} 𝗣𝗿𝗼𝘅𝘆 𝗚𝗲𝗻𝗲𝗿𝗮𝘁𝗲𝗱 {STAR}</blockquote>",
            "━━━━━━━━━━━━━━━━━━━━━",
            f"{SHIELD} 𝗥𝗼𝘁𝗮𝘁𝗶𝗻𝗴 ➠ <code>{rotating}</code>",
            f"{DIAMOND} 𝗦𝘁𝗼𝗿𝗲𝗱 ➠ <b>bms_proxy.txt</b> {'+ 𝘆𝗼𝘂𝗿 𝗽𝗼𝗼𝗹' if given else ''}",
            f"{COMPASS} 𝗦𝗼𝘂𝗿𝗰𝗲 ➠ <b>{source.upper()}</b>",
        ]
        await proc_msg.edit_text("\n".join(lines), parse_mode="HTML")
    else:
        await proc_msg.edit_text(
            f"{TARGET} <b>𝗚𝗲𝗻𝗲𝗿𝗮𝘁𝗶𝗼𝗻 𝗳𝗮𝗶𝗹𝗲𝗱</b>\n\n"
            f"{COMPASS} 𝘁𝗿𝘆 𝗮𝗴𝗮𝗶𝗻 𝗮𝗳𝘁𝗲𝗿 𝘀𝗼𝗺𝗲 𝘁𝗶𝗺𝗲",
            parse_mode="HTML")
