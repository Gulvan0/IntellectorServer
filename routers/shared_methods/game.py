from datetime import datetime
from sqlmodel import Session, select
from models.game import Game, GameOutcome
from net.fastapi_wrapper import MutableState
from rules import PieceColor
from utils.datatypes import OutcomeKind


async def end_game(
    session: Session,
    state: MutableState,
    game_id: int,
    outcome: OutcomeKind,
    winner_color: PieceColor | None,
    ended_at: datetime | None = None
) -> None:
    ...  # TODO: Fill

    if state.shutdown_activated and not session.exec(select(Game).join(GameOutcome).where(Game.outcome != None)).first():
        raise KeyboardInterrupt

    state.game_timeout_not_earlier_than.pop(game_id, None)
