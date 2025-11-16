from pydantic import BaseModel
from sqlalchemy import ColumnElement
from sqlmodel import or_

from src.game.models.main import Game
from src.common.field_types import OptionalPlayerRef
from src.game.datatypes import TimeControlKind


class GameFilter(BaseModel):
    player_ref: OptionalPlayerRef = None
    time_control_kind: TimeControlKind | None = None

    def construct_conditions(self) -> list[bool | ColumnElement[bool]]:
        conditions: list[bool | ColumnElement[bool]] = []
        if self.player_ref:
            conditions.append(or_(
                Game.white_player_ref == self.player_ref,
                Game.black_player_ref == self.player_ref
            ))
        if self.time_control_kind:
            conditions.append(Game.time_control_kind == self.time_control_kind)
        return conditions
