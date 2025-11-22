from typing import Iterable
from sqlalchemy import ScalarResult
from sqlmodel import and_, col, desc, or_, select, func
from sqlmodel.sql.expression import SelectOfScalar

from src.common.sql import count_if
from src.common.time_control import TimeControlKind
from src.game.datatypes import OfferAction, OfferKind, OverallGameCounts
from src.game.models.main import Game
from src.game.models.offer import GameOfferEvent
from src.game.models.outcome import GameOutcome
from src.game.models.ply import GamePlyEvent
from src.game.models.rest import GameFilter
from src.game.models.time_update import GameTimeUpdate
from src.rules import PieceColor, PieceKind, PlyKind
from src.utils.async_orm_session import AsyncSession


async def get_ply_history(session: AsyncSession, game_id: int, reverse_order: bool = False) -> ScalarResult[GamePlyEvent]:
    return await session.exec(select(
        GamePlyEvent
    ).where(
        GamePlyEvent.game_id == game_id,
        not GamePlyEvent.is_cancelled
    ).order_by(
        desc(GamePlyEvent.ply_index) if reverse_order else col(GamePlyEvent.ply_index)
    ))


async def get_ply_cnt(session: AsyncSession, game_id: int) -> int:
    query: SelectOfScalar[int] = select(
        func.max(GamePlyEvent.ply_index)
    ).where(
        GamePlyEvent.game_id == game_id,
        not GamePlyEvent.is_cancelled
    )
    result = await session.exec(query)
    last_ply_index = result.first()
    return last_ply_index + 1 if last_ply_index else 0


async def get_active_offers(session: AsyncSession, game_id: int) -> ScalarResult[GameOfferEvent]:
    return await session.exec(
        select(
            GameOfferEvent
        ).where(
            GameOfferEvent.game_id == game_id
        ).group_by(
            GameOfferEvent.offer_kind,
            GameOfferEvent.offer_author
        ).having(
            count_if(GameOfferEvent.action == OfferAction.CREATE) > count_if(GameOfferEvent.action != OfferAction.CREATE)
        )
    )


async def is_offer_active(session: AsyncSession, game_id: int, offer_kind: OfferKind, offer_author: PieceColor) -> bool:
    result = await session.exec(
        select(
            GameOfferEvent.action
        ).where(
            GameOfferEvent.game_id == game_id,
            GameOfferEvent.offer_kind == offer_kind,
            GameOfferEvent.offer_author == offer_author
        ).order_by(
            desc(GameOfferEvent.occurred_at)
        )
    )
    return result.first() == OfferAction.CREATE.value


async def get_overall_player_game_counts(session: AsyncSession, player_login: str) -> OverallGameCounts:
    db_games_cnt = await session.exec(select(
        Game.time_control_kind,
        func.count(col(Game.id))
    ).where(
        or_(
            Game.white_player_ref == player_login,
            Game.black_player_ref == player_login
        )
    ).group_by(
        Game.time_control_kind
    ))

    game_counts = OverallGameCounts()
    for db_games_cnt_item in db_games_cnt:
        game_counts.by_time_control[TimeControlKind(db_games_cnt_item[0])] = db_games_cnt_item[1]
        game_counts.total += db_games_cnt_item[1]
    return game_counts


async def get_current_games(session: AsyncSession, game_filter: GameFilter, offset: int = 0, limit: int = 10) -> Iterable[Game]:
    result = await session.exec(select(
        Game
    ).where(
        Game.outcome == None,  # noqa
        *game_filter.construct_conditions()
    ).offset(
        offset
    ).limit(
        limit
    ))
    return result.all()


async def get_recent_games(session: AsyncSession, game_filter: GameFilter, offset: int = 0, limit: int = 10) -> Iterable[Game]:
    result = await session.exec(select(
        Game
    ).where(
        Game.outcome != None,  # noqa
        *game_filter.construct_conditions()
    ).order_by(
        desc(Game.started_at)
    ).offset(
        offset
    ).limit(
        limit
    ))
    return result.all()


async def get_ongoing_finite_game(session: AsyncSession) -> Game | None:
    result = await session.exec(
        select(Game)
        .join(GameOutcome)
        .where(
            Game.outcome != None,
            Game.time_control_kind != TimeControlKind.CORRESPONDENCE
        )
    )
    return result.first()


async def get_last_ply_event(session: AsyncSession, game_id: int) -> GamePlyEvent | None:
    result = await session.exec(
        select(GamePlyEvent)
        .where(
            GamePlyEvent.game_id == game_id,
            not GamePlyEvent.is_cancelled
        )
        .order_by(
            desc(GamePlyEvent.ply_index)
        )
    )
    return result.first()


async def get_initial_time(session: AsyncSession, game_id: int) -> GameTimeUpdate | None:
    result = await session.exec(
        select(GameTimeUpdate)
        .where(
            GameTimeUpdate.game_id == game_id
        )
        .order_by(
            col(GameTimeUpdate.id)
        )
    )
    return result.first()


async def get_latest_time_update(session: AsyncSession, game_id: int) -> GameTimeUpdate | None:
    result = await session.exec(
        select(GameTimeUpdate)
        .where(
            GameTimeUpdate.game_id == game_id
        )
        .order_by(
            desc(GameTimeUpdate.id)
        )
    )
    return result.first()


async def has_occured_thrice(session: AsyncSession, game_id: int, sip: str) -> bool:
    result = await session.exec(select(
        func.count(col(GamePlyEvent.id))
    ).where(
        GamePlyEvent.game_id == game_id,
        not GamePlyEvent.is_cancelled,
        GamePlyEvent.sip_after == sip
    ))
    same_position_occurences_cnt = result.one()
    return same_position_occurences_cnt >= 3


async def is_stale(session: AsyncSession, game_id: int, last_ply_index: int) -> bool:
    result = await session.exec(select(
        GamePlyEvent.ply_index
    ).where(
        GamePlyEvent.game_id == game_id,
        not GamePlyEvent.is_cancelled,
        or_(
            and_(
                GamePlyEvent.target_piece != None,
                GamePlyEvent.kind != PlyKind.SWAP
            ),
            GamePlyEvent.moved_piece == PieceKind.PROGRESSOR
        )
    ))
    last_progressive_ply_index = result.first()
    return last_ply_index - (last_progressive_ply_index or -1) >= 60
