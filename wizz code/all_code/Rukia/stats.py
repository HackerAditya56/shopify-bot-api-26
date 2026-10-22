import asyncio
import logging

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# AIogram Imports
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
from aiogram import types, F, Router

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# DB import — leaderboard now lives in MongoDB Atlas so it
# survives VPS redeploys (mshh.txt / mst.txt were wiped every update).
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
from database import get_charged_leaderboard

# Router for this module
router = Router()

# Premium Emoji IDs (provided by owner)
EMOJI_RED_TICK   = "6147565374289220368"
EMOJI_BLUE_TICK  = "5278628026416909103"
EMOJI_LIGHTNING  = "5350835008007324644"
EMOJI_STAR       = "5359686514697576863"
EMOJI_FIRE       = "6186076099764555777"
EMOJI_CROWN      = "6338940587193930733"
EMOJI_EPIC       = "5310296284874159738"
EMOJI_DRAGON     = "5226578782340553954"
EMOJI_GUN        = "5440406404936524730"
EMOJI_WHITE_STAR = "5247131412032670246"

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# HELPERS
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def get_leaderboard_data():
    """
    Fetches the top 10 users ranked by total charged card hits.
    Data is aggregated from the `charged_hits` collection in
    MongoDB Atlas — persistent across VPS redeploys.
    """
    return get_charged_leaderboard(limit=10)

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# COMMAND: /leaderboard
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

@router.message(F.text.regexp(r"^/(leaderboard|stats)(\s|$)"))
async def leaderboard_command(message: types.Message):
    """
    Displays the top 10 users ranked by total Charged cards.
    Pulls data from the charged_hits collection (MongoDB Atlas).
    Alias: /stats
    """
    
    # Create a status message while fetching
    status_msg = await message.answer(
        f"<tg-emoji emoji-id='4904882772637648609'>⏳</tg-emoji> <b>Loading…</b>",
        parse_mode="HTML"
    )

    try:
        # Run file reading in thread to prevent blocking
        top_users, user_details = await asyncio.to_thread(get_leaderboard_data)

        # 1. Format the Message
        if not top_users:
            text = (
                f"<tg-emoji emoji-id=\"6183613910977876404\">💎</tg-emoji> <b>Top Charged Users</b>\n"
                "━━━━━━━━━━━━━━━━\n"
                "<i>No charged cards yet.</i>"
            )
        else:
            lines = [
                f"┏━━━━━━━━━━━━━━━━━━━━┓\n"
                f"  <tg-emoji emoji-id=\"6183613910977876404\">💎</tg-emoji> "
                f"<b>Top Charged Users</b> "
                f"<tg-emoji emoji-id=\"6183613910977876404\">💎</tg-emoji>\n"
                f"┗━━━━━━━━━━━━━━━━━━━━┛",
            ]
            podium = []
            rest = []
            for index, (user_id, count) in enumerate(top_users, 1):
                details = user_details.get(user_id, {})
                fname = details.get('first_name', 'Unknown')
                uname = details.get('username')
                if uname:
                    user_link = f'<a href="https://t.me/{uname}">{fname}</a>'
                else:
                    user_link = f'<a href="tg://user?id={user_id}">{fname}</a>'
                charge_word = "charge" if count == 1 else "charges"
                if index == 1:
                    medal = "🥇"
                    podium.append(f"{medal} <b>{user_link}</b>\n     ⚡ <b>{count}</b> {charge_word}")
                elif index == 2:
                    medal = "🥈"
                    podium.append(f"{medal} <b>{user_link}</b>\n     ⚡ <b>{count}</b> {charge_word}")
                elif index == 3:
                    medal = "🥉"
                    podium.append(f"{medal} <b>{user_link}</b>\n     ⚡ <b>{count}</b> {charge_word}")
                else:
                    rest.append(f"<b>{index}.</b> {user_link} ➛ <b>{count}</b>")
            if podium:
                lines.append("\n".join(podium))
            if rest:
                lines.append("━━━━━━━━━━━━━━━━")
                lines.append("\n".join(rest))
            lines.append("━━━━━━━━━━━━━━━━")
            lines.append(f"<tg-emoji emoji-id=\"5397981293512243749\">✨</tg-emoji> <i>Top 10 by charged cards</i>")
            text = "\n".join(lines)

        # 2. Edit the original message with the result
        await status_msg.edit_text(text, parse_mode="HTML", disable_web_page_preview=True)

    except Exception as e:
        logging.error(f"Error in /leaderboard command: {e}")
        await status_msg.edit_text("❌ <b>Error fetching stats.</b>", parse_mode="HTML")
