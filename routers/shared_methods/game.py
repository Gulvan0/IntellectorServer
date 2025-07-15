from datetime import UTC, datetime, timedelta
import time
from typing import Literal
from sqlmodel import Session, desc, select
from models.game import Game, GameOutcome, GamePlyEvent
from net.fastapi_wrapper import MutableState
from rules import PieceColor, Position
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


async def check_timeout(
    *,
    session: Session,
    state: MutableState,
    game_id: int,
    last_ply_event: GamePlyEvent | None | Literal['NOT_YET_RETRIEVED'] = 'NOT_YET_RETRIEVED',
    last_position: Position | Literal['NOT_YET_RETRIEVED'] = 'NOT_YET_RETRIEVED',
    outcome_abscence_checked: bool = False,
) -> bool:
    threshold = state.game_timeout_not_earlier_than.get(game_id)
    if not threshold or threshold > time.time():
        return False

    if not outcome_abscence_checked and session.get(GameOutcome, game_id) is not None:
        return False

    if last_ply_event == 'NOT_YET_RETRIEVED':
        last_ply_event = session.exec(select(
            GamePlyEvent
        ).where(
            GamePlyEvent.game_id == game_id,
            not GamePlyEvent.is_cancelled
        ).order_by(
            desc(GamePlyEvent.ply_index)
        )).first()

    if not last_ply_event or last_ply_event.ply_index < 1 or not last_ply_event.white_seconds_after_execution or not last_ply_event.black_seconds_after_execution:
        return False

    if last_position == 'NOT_YET_RETRIEVED':
        last_position = Position.from_sip(last_ply_event.sip_after)

    if last_position.color_to_move == PieceColor.BLACK:  # we don't use ply_index as the starting position might have been "black to move"
        time_remainder = last_ply_event.black_seconds_after_execution
        potential_winner = PieceColor.WHITE
    else:
        time_remainder = last_ply_event.white_seconds_after_execution
        potential_winner = PieceColor.BLACK

    timeout_dt = (last_ply_event.occurred_at + timedelta(seconds=time_remainder)).replace(tzinfo=UTC)
    if datetime.now(UTC) >= timeout_dt:
        await end_game(session, state, game_id, OutcomeKind.TIMEOUT, potential_winner, timeout_dt)
        return True

    return False
