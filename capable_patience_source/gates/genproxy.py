import asyncio
import json
import logging
import os
import random
import subprocess

from aiogram import types, F, Router

from mass_gates._tg_helpers import safe_reply

router = Router()

# ── paths ──────────────────────────────────────────────────────────────
_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))   # capable_patience_source
REPO = os.path.dirname(_ROOT)                                          # shopify root
KALI_PROXY = os.path.join(REPO, "v7", "kali_proxy.txt")
BMS_PROXY = os.path.join(REPO, "bms_proxy.txt")
GEN_SCRIPT = os.path.join(_ROOT, "webshare_gen.py")

# ── MinecraftEnchanted premium emoji IDs (unique) ─────────────────────
EMOJI_STAR    = "5321214486877609476"   # ⭐️
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
    """Self-sustaining: prefer a generated (bms) proxy; fall back to kali."""
    bms = _load(BMS_PROXY)
    if bms:
        return random.choice(bms), "bms"
    kali = _load(KALI_PROXY)
    if kali:
        return random.choice(kali), "kali"
    return None, None


def _run_generator(proxy):
    cmd = ["xvfb-run", "-a", "python3", GEN_SCRIPT, "--proxy", proxy, "--scheme", "socks5"]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=300, cwd=_ROOT)
        last = (proc.stdout or "").strip().splitlines()
        if not last:
            return None
        data = json.loads(last[-1])
        return data.get("rotating") or None
    except Exception as e:
        logging.error(f"[genproxy] generator error: {e}")
        return None


_GEN_LOCK = asyncio.Lock()


async def _bg_generate_loop(delay: int = 60):
    """Background self-sustaining proxy generation.

    Every `delay` seconds: pick a proxy (bms_proxy.txt first, kali fallback),
    mint a webshare account through it (SOCKS5), store the rotating endpoint
    in bms_proxy.txt. Serialised by _GEN_LOCK so it never overlaps a manual
    /genproxy run."""
    while True:
        try:
            proxy, source = _pick_proxy()
            if proxy:
                async with _GEN_LOCK:
                    rotating = await asyncio.to_thread(_run_generator, proxy)
                if rotating:
                    _append_bms(rotating)
                    logging.info(f"[genproxy-bg] generated {rotating} (source={source})")
                else:
                    logging.warning(f"[genproxy-bg] generation failed (source={source})")
            else:
                logging.warning("[genproxy-bg] no proxies in kali/bms files")
        except Exception as e:
            logging.error(f"[genproxy-bg] {e}")
        await asyncio.sleep(delay)


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
        f"<blockquote>{BOW} 𝗚𝗲𝗻𝗲𝗿𝗮𝘁𝗶𝗻𝗴 𝗪𝗲𝗯𝘀𝗵𝗮𝗿𝗲 𝗣𝗿𝗼𝘅𝘆 {DIAMOND}</blockquote>\n"
        f"{COMPASS} 𝗦𝗼𝘂𝗿𝗰𝗲 ➠ <b>{source.upper()}</b>",
        parse_mode="HTML")

    async with _GEN_LOCK:
        rotating = await asyncio.to_thread(_run_generator, proxy)

    if rotating:
        added = _append_bms(rotating)
        lines = [
            f"<blockquote>{STAR} 𝗣𝗿𝗼𝘅𝘆 𝗚𝗲𝗻𝗲𝗿𝗮𝘁𝗲𝗱 {STAR}</blockquote>",
            "━━━━━━━━━━━━━━━━━━━━━",
            f"{SHIELD} 𝗥𝗼𝘁𝗮𝘁𝗶𝗻𝗴 ➠ <code>{rotating}</code>",
            f"{DIAMOND} 𝗦𝘁𝗼𝗿𝗲𝗱 ➠ <b>bms_proxy.txt</b>",
            f"{COMPASS} 𝗦𝗼𝘂𝗿𝗰𝗲 ➠ <b>{source.upper()}</b>",
        ]
        await proc_msg.edit_text("\n".join(lines), parse_mode="HTML")
    else:
        await proc_msg.edit_text(
            f"{TARGET} <b>𝗚𝗲𝗻𝗲𝗿𝗮𝘁𝗶𝗼𝗻 𝗳𝗮𝗶𝗹𝗲𝗱</b>\n\n"
            f"{COMPASS} 𝘁𝗿𝗶𝗲𝗱 ➠ <code>{proxy[:60]}</code>",
            parse_mode="HTML")
