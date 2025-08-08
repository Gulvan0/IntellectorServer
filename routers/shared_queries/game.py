from sqlalchemy import func
from sqlmodel import Session, and_, col, desc, or_, select

from models.game import Game, GameOutcome, GamePlyEvent
from rules import PieceKind, PlyKind
from utils.datatypes import TimeControlKind


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
