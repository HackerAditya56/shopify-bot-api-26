from aiogram import types, Router
from database import set_gate_status

# 🔴 Replace with your Telegram user ID(s)
ADMINS = [8462705169]

router = Router()

@router.message(lambda message: message.text and message.text.startswith("/on"))
async def on_command(message: types.Message):
    if message.from_user.id not in ADMINS:
        return

    parts = message.text.split()
    if len(parts) < 2:
        await message.reply(
            "<tg-emoji emoji-id=\"5893081007153746175\">❌</tg-emoji> Usage: /on <gate>\nExample: /on au"
        )
        return

    gate = parts[1].lower()
    set_gate_status(gate, True)

    await message.reply(
        f"<tg-emoji emoji-id=\"6044254523009012231\">✅</tg-emoji> <b>{gate.upper()}</b> gate is now <b>ENABLED</b>",
        parse_mode="HTML"
    )


@router.message(lambda message: message.text and message.text.startswith("/off"))
async def off_command(message: types.Message):
    if message.from_user.id not in ADMINS:
        return

    parts = message.text.split()
    if len(parts) < 2:
        await message.reply(
            "<tg-emoji emoji-id=\"5893081007153746175\">❌</tg-emoji> Usage: /off <gate>\nExample: /off au"
        )
        return

    gate = parts[1].lower()
    set_gate_status(gate, False)

    await message.reply(
        f"<tg-emoji emoji-id=\"6255910249362885846\">⚠️</tg-emoji> <b>{gate.upper()}</b> gate is now <b>UNDER MAINTENANCE</b>",
        parse_mode="HTML"
    )
