from sqlalchemy import ColumnElement
from sqlmodel import col, or_

from common.time_control import TimeControlKind
from game.datatypes import OutcomeKind
from game.models.main import Game, GameSummaryPublic
from game.models.outcome import GameOutcome
from common.field_types import OptionalPlayerRef
from utils.custom_model import CustomModel


class GameFilter(CustomModel):
    player_ref: OptionalPlayerRef = None
    time_control_kinds: list[TimeControlKind] | None = None  # any of them; null for any kind
    rated: bool | None = None
    finished: bool | None = None
    exclude_aborted: bool = False

    def construct_conditions(self, ignore_kinds: bool = False, ignore_rated: bool = False) -> list[bool | ColumnElement[bool]]:
        conditions: list[bool | ColumnElement[bool]] = []
        if self.player_ref:
            conditions.append(or_(
                Game.white_player_ref == self.player_ref,
                Game.black_player_ref == self.player_ref
            ))
        if self.time_control_kinds is not None and not ignore_kinds:
            conditions.append(col(Game.time_control_kind).in_(self.time_control_kinds))
        if self.rated is not None and not ignore_rated:
            conditions.append(Game.rated == self.rated)
        if self.finished is not None:
            conditions.append(Game.outcome != None if self.finished else Game.outcome == None)  # noqa
        if self.exclude_aborted:
            conditions.append(~col(Game.outcome).has(col(GameOutcome.kind) == OutcomeKind.ABORT))
        return conditions


class GameSearchPayload(GameFilter):
    with_counts: bool = False


class GameSearchRatedCounts(CustomModel):
    rated: int
    casual: int


class GameSearchCounts(CustomModel):
    """Each facet's counts apply every other facet of the filter, but not its own"""
    time_control_kinds: dict[TimeControlKind, int]
    rated: GameSearchRatedCounts


class GameSearchResult(CustomModel):
    games: list[GameSummaryPublic]
    total: int
    counts: GameSearchCounts | None = None
