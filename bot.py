import os
import asyncio
from dataclasses import dataclass, field
from typing import cast

from dotenv import load_dotenv
from pyrogram.client import Client
from pyrogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, User
from pyrogram.filters import command, private, reply

from minrob_game import MinroobGame


@dataclass
class GameInfo:
    me: User
    game: MinroobGame = field(default_factory=MinroobGame)
    my_color: str | None = None
    turn_decided: bool = False
    my_turn: bool = False

    def decide_my_turn(self, first_name: str, turns_row: list[InlineKeyboardButton]):
        my_turn = False
        last_line_texts = [b.text for b in turns_row]
        for user_text in last_line_texts:
            if user_text.startswith("🎮"):
                if self.my_color is None:
                    if user_text.endswith(first_name):
                        my_turn = True
                        self.my_color = user_text[1]
                else:
                    my_turn = user_text.startswith("🎮" + self.my_color)
        self.my_turn = my_turn
        self.turn_decided = True

    def switch_turn(self):
        self.my_turn = not self.my_turn


games: dict[int, GameInfo] = {}
load_dotenv()

api_id = int(cast(str, os.getenv("API_ID")))
api_hash = cast(str, os.getenv("API_HASH"))

app = Client("my_bot", api_id=api_id, api_hash=api_hash)


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


@app.on_edited_message()  # type: ignore
async def minroob_started(client: Client, message: Message):
    await play_async(client, message)


@app.on_message(command("play") & reply & private)  # type: ignore
async def minroob_play_force(client: Client, message: Message):
    if not message.reply_to_message:
        return

    await play_async(client, message.reply_to_message)


app.run()
