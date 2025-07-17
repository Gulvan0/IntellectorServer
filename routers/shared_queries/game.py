from sqlmodel import Session, desc, select

from models.game import Game, GameOutcome, GamePlyEvent
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
