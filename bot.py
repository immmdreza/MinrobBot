import asyncio
import os
from typing import cast

from dotenv import load_dotenv
from pyrogram.client import Client
from pyrogram.filters import command, private, reply
from pyrogram.types import InlineKeyboardMarkup, Message

from minrob_game import GameInfo


games: dict[int, GameInfo] = {}
load_dotenv()

api_id = int(cast(str, os.getenv("API_ID")))
api_hash = cast(str, os.getenv("API_HASH"))
session_string = cast(str, os.getenv("SESSION_STRING"))

app = Client(
    ":memory:", api_id=api_id, api_hash=api_hash, session_string=session_string
)


async def play_async(_: Client, message: Message):
    if not message.via_bot:
        return

    if not (message.via_bot.username and message.via_bot.username == "minroobot"):
        return

    if not isinstance(message.reply_markup, InlineKeyboardMarkup):
        return

    buttons = message.reply_markup.inline_keyboard[:-2]
    if len(buttons) < 8:
        await message.reply_text("Buttons row invalid.")

    if message.id in games:
        game = games[message.id]
    else:
        game = GameInfo(await _.get_me())
        games[message.id] = game

    if any(any(button.text == "💣" for button in row) for row in buttons):
        await message.reply_text("Game is ended!")
        return

    game.decide_my_turn(
        cast(str, game.me.first_name), message.reply_markup.inline_keyboard[-2]
    )

    game.game.reorder_blocks_from_buttons(buttons)
    game.game.calculate_all_success_ratios()

    if game.my_turn:

        await asyncio.sleep(1)
        selected = game.game.play()
        print(
            "Clicking on block at",
            selected.position,
            "with success ratios",
            ", ".join(str(x) for x in selected._success_ratios),
        )
        await message.click(selected.position.y, selected.position.x)


@app.on_message(group=-1)  # type: ignore
async def join_minroob(_: Client, message: Message):
    if not message.via_bot:
        return

    if not (message.via_bot.username and message.via_bot.username == "minroobot"):
        return

    try:
        await message.click()
        await message.reply_text("I'm here!")
    except TimeoutError:
        await message.reply_text("I may be here or not.")


@app.on_edited_message()  # type: ignore
async def minroob_started(client: Client, message: Message):
    await play_async(client, message)


@app.on_message(command("play") & reply & private)  # type: ignore
async def minroob_play_force(client: Client, message: Message):
    if not message.reply_to_message:
        return

    await play_async(client, message.reply_to_message)


@app.on_message(command("ss") & private)  # type: ignore
async def minroob_ss(client: Client, message: Message):
    ss = await client.export_session_string()
    await message.reply_text(ss)


app.run()
