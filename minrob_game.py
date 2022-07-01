from abc import abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Generator, Generic, TypeVar

from pyrogram.types import InlineKeyboardButton, User


class Player(Enum):
    Blue = 1
    Red = 2


@dataclass
class RevalInfo:
    revealed: bool
    was_mine: bool
    revealed_by: Player | None
    was_empty: bool


@dataclass(repr=True, eq=True)
class Position:
    x: int
    y: int


INITIAL_SUCCESS_RATIO = 0.005
CUSTOM_SUCCESS_RATIO: dict[tuple[int, int], float] = {
    (1, 1): 0.02,
    (1, 5): 0.02,
    (6, 1): 0.02,
    (6, 5): 0.02,
    (2, 2): 0.01,
    (2, 4): 0.01,
    (5, 2): 0.01,
    (5, 4): 0.01,
}


class Block:
    def __init__(self, position: Position, reval_info: RevalInfo) -> None:
        self.position = position
        self.reval_info = reval_info
        self._success_ratios: set[float] = {
            CUSTOM_SUCCESS_RATIO.get((position.x, position.y), INITIAL_SUCCESS_RATIO)
        }

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}({self.position})"

    def add_success_ratio(self, ratio: float):
        if ratio < 0.0 or ratio > 1.0:
            raise ValueError("ratio must be between 0.0 and 1.0")

        self._success_ratios.add(ratio)

    @property
    def success_ratio(self) -> float:
        return max(self._success_ratios)

    @property
    def is_impossible(self):
        return 0.0 in self._success_ratios

    @property
    def is_sure(self):
        return 1.0 in self._success_ratios


class UnRevealedBlock(Block):
    def __init__(self, position: Position) -> None:
        super().__init__(
            position,
            RevalInfo(
                revealed=False, was_mine=False, revealed_by=None, was_empty=False
            ),
        )


class RevealedBlock(Block):
    def __init__(self, position: Position, revealed_by: Player | None = None) -> None:
        super().__init__(
            position,
            RevalInfo(
                revealed=True, was_mine=False, revealed_by=revealed_by, was_empty=False
            ),
        )


class MineBlock(RevealedBlock):
    def __init__(self, position: Position, revealed_by: Player | None = None) -> None:
        self.reval_info = RevalInfo(
            revealed=True, was_mine=True, revealed_by=revealed_by, was_empty=False
        )
        super().__init__(position, revealed_by)


class NumericBlock(RevealedBlock):
    def __init__(self, position: Position, number: int) -> None:
        self.reval_info = RevalInfo(
            revealed=True, was_mine=False, revealed_by=None, was_empty=False
        )
        self.number = number
        super().__init__(position, None)


class EmptyBlock(RevealedBlock):
    def __init__(self, position: Position) -> None:
        self.reval_info = RevalInfo(
            revealed=True, was_mine=False, revealed_by=None, was_empty=True
        )
        self.revealed_by = None
        super().__init__(position, None)

    def __repr__(self) -> str:
        return f"EmptyBlock({self.position})"


_TBlock = TypeVar("_TBlock", bound=Block)


class AbstractRatioCalculator(Generic[_TBlock]):
    def __init__(self, block_type: type[_TBlock]) -> None:
        self._block_type = block_type

    def calculate(self, current_block: Block, surrounding_blocks: list[Block]):
        if not isinstance(current_block, self._block_type):
            return
        self.__calculate__(current_block, surrounding_blocks)

    @abstractmethod
    def __calculate__(self, current_block: Block, surrounding_blocks: list[Block]):
        ...


class MinroobGame:
    def __init__(self) -> None:
        self._reminded_mins = 15
        self._blocks: list[list[Block]] = []
        for x in range(8):
            self._blocks.append([])
            for y in range(7):
                self._blocks[-1].append(UnRevealedBlock(Position(x, y)))

    def reorder_blocks_from_buttons(self, buttons: list[list[InlineKeyboardButton]]):
        self._blocks = [
            [
                MinroobGame.button_text_to_block(button.text, Position(x, y))
                for y, button in enumerate(row)
            ]
            for x, row in enumerate(buttons)
        ]

    @staticmethod
    def button_text_to_block(button_text: str, position: Position) -> Block:
        match button_text:
            case "🔵️":
                return MineBlock(position=position, revealed_by=Player.Blue)
            case "🔴":
                return MineBlock(position=position, revealed_by=Player.Red)
            case " ":
                return EmptyBlock(position=position)
            case "⬜️":
                return UnRevealedBlock(position=position)
            case _:
                if button_text[0].isdigit():
                    return NumericBlock(position=position, number=int(button_text[0]))
                raise ValueError(f"Unknown button text: {button_text}")

    def _iter_surrounding_blocks(self, block: Block) -> Generator[Block, None, None]:
        for x in range(block.position.x - 1, block.position.x + 2):
            for y in range(block.position.y - 1, block.position.y + 2):
                if x < 0 or x >= 8 or y < 0 or y >= 7:
                    continue
                yield self._blocks[x][y]

    @staticmethod
    def _calculate_success_ratio(
        current_block: Block, surrounding_blocks: list[Block]
    ) -> None:
        if not isinstance(current_block, NumericBlock):
            return None

        unrevealed_around = 0
        mines_block = 0
        for block in surrounding_blocks:
            if isinstance(block, MineBlock):
                mines_block += 1
            if not block.reval_info.revealed:
                unrevealed_around += 1

        try:
            ratio = (current_block.number - mines_block) / unrevealed_around
        except ZeroDivisionError:
            ratio = 0.0
        for block in surrounding_blocks:
            if not block.reval_info.revealed:
                block.add_success_ratio(ratio)

    def calculate_all_success_ratios(self):
        for row in self._blocks:
            for block in row:
                if isinstance(block, NumericBlock):
                    self._calculate_success_ratio(
                        block, list(self._iter_surrounding_blocks(block))
                    )

    def play(self):
        return next(
            block
            for block in sorted(
                [
                    block
                    for row in self._blocks
                    for block in row
                    if not block.reval_info.revealed and not block.is_impossible
                ],
                key=lambda block: block.success_ratio,
                reverse=True,
            )
        )


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
