from typing import Iterable
from sqlalchemy import ScalarResult
from sqlmodel import Session, and_, col, desc, or_, select, func

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


def get_ply_history(session: Session, game_id: int, reverse_order: bool = False) -> ScalarResult[GamePlyEvent]:
    return session.exec(select(
        GamePlyEvent
    ).where(
        GamePlyEvent.game_id == game_id,
        not GamePlyEvent.is_cancelled
    ).order_by(
        desc(GamePlyEvent.ply_index) if reverse_order else col(GamePlyEvent.ply_index)
    ))


def get_ply_cnt(session: Session, game_id: int) -> int:
    last_ply_index = session.exec(select(
        func.max(GamePlyEvent.ply_index)
    ).where(
        GamePlyEvent.game_id == game_id,
        not GamePlyEvent.is_cancelled
    )).first()
    return last_ply_index + 1 if last_ply_index else 0


def get_active_offers(session: Session, game_id: int) -> ScalarResult[GameOfferEvent]:
    return session.exec(
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


def is_offer_active(session: Session, game_id: int, offer_kind: OfferKind, offer_author: PieceColor) -> bool:
    return session.exec(
        select(
            GameOfferEvent.action
        ).where(
            GameOfferEvent.game_id == game_id,
            GameOfferEvent.offer_kind == offer_kind,
            GameOfferEvent.offer_author == offer_author
        ).order_by(
            desc(GameOfferEvent.occurred_at)
        )
    ).first() == OfferAction.CREATE.value


def get_overall_player_game_counts(session: Session, player_login: str) -> OverallGameCounts:
    db_games_cnt = session.exec(select(
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


async def get_current_games(session: Session, game_filter: GameFilter, offset: int = 0, limit: int = 10) -> Iterable[Game]:
    return session.exec(select(
        Game
    ).where(
        Game.outcome == None,  # noqa
        *game_filter.construct_conditions()
    ).offset(offset).limit(limit)).all()


async def get_recent_games(session: Session, game_filter: GameFilter, offset: int = 0, limit: int = 10) -> Iterable[Game]:
    return session.exec(select(
        Game
    ).where(
        Game.outcome != None,  # noqa
        *game_filter.construct_conditions()
    ).order_by(desc(Game.started_at)).offset(offset).limit(limit)).all()


def get_ongoing_finite_game(session: Session) -> Game | None:
    return session.exec(
        select(Game)
        .join(GameOutcome)
        .where(
            Game.outcome != None,
            Game.time_control_kind != TimeControlKind.CORRESPONDENCE
        )
    ).first()


def get_last_ply_event(session: Session, game_id: int) -> GamePlyEvent | None:
    return session.exec(
        select(GamePlyEvent)
        .where(
            GamePlyEvent.game_id == game_id,
            not GamePlyEvent.is_cancelled
        )
        .order_by(
            desc(GamePlyEvent.ply_index)
        )
    ).first()


def get_initial_time(session: Session, game_id: int) -> GameTimeUpdate | None:
    return session.exec(
        select(GameTimeUpdate)
        .where(
            GameTimeUpdate.game_id == game_id
        )
        .order_by(
            col(GameTimeUpdate.id)
        )
    ).first()


def get_latest_time_update(session: Session, game_id: int) -> GameTimeUpdate | None:
    return session.exec(
        select(GameTimeUpdate)
        .where(
            GameTimeUpdate.game_id == game_id
        )
        .order_by(
            desc(GameTimeUpdate.id)
        )
    ).first()


def has_occured_thrice(session: Session, game_id: int, sip: str) -> bool:
    same_position_occurences_cnt = session.exec(select(
        func.count(col(GamePlyEvent.id))
    ).where(
        GamePlyEvent.game_id == game_id,
        not GamePlyEvent.is_cancelled,
        GamePlyEvent.sip_after == sip
    )).one()
    return same_position_occurences_cnt >= 3


def is_stale(session: Session, game_id: int, last_ply_index: int) -> bool:
    last_progressive_ply_index = session.exec(select(
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
    )).first()
    return last_ply_index - (last_progressive_ply_index or -1) >= 60
