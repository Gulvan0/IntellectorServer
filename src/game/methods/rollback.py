from dataclasses import dataclass
from datetime import UTC, datetime
from itertools import chain
from typing import Iterable

from fastapi import HTTPException

from game.methods.event import append_rollback_event
from game.methods.get import get_initial_time, get_ply_history
from game.methods.timeout import plan_timeout_check
from game.models.main import Game
from game.models.ply import GamePlyEvent
from game.models.rollback import GameRollbackEvent
from game.models.time_update import GameTimeUpdateReason
from net.core import MutableState
from board.constants.sip import DEFAULT_STARTING_SIP
from board.deserializers.sip import color_to_move_from_sip
from board.piece import PieceColor
from utils.async_orm_session import AsyncSession


@dataclass
class RollbackPlyCountInput:
    new_ply_cnt: int


@dataclass
class RollbackOfferAuthorInput:
    offer_author: PieceColor


@dataclass
class RollbackSuccessfulValidationResults:
    reversed_ply_events: Iterable[GamePlyEvent]
    old_ply_cnt: int
    new_ply_cnt: int
    requested_by: PieceColor


async def validate_rollback(
    session: AsyncSession,
    game_id: int,
    input: RollbackPlyCountInput | RollbackOfferAuthorInput
) -> RollbackSuccessfulValidationResults:
    ply_events = await get_ply_history(session, game_id, reverse_order=True)
    last_ply_event = next(ply_events, None)
    if not last_ply_event:
        raise HTTPException(422, "Too early for a rollback")

    old_color_to_move = color_to_move_from_sip(last_ply_event.sip_after)
    old_ply_cnt = last_ply_event.ply_index + 1

    match input:
        case RollbackOfferAuthorInput(offer_author):
            if offer_author != old_color_to_move:
                new_ply_cnt = old_ply_cnt - 1
            else:
                new_ply_cnt = old_ply_cnt - 2
                if new_ply_cnt < 0:
                    raise HTTPException(422, "Too early for a rollback")
            requested_by = offer_author
        case RollbackPlyCountInput(ply_cnt):
            new_ply_cnt = ply_cnt
            if new_ply_cnt >= old_ply_cnt:
                raise HTTPException(
                    422,
                    f"New ply count (got: {new_ply_cnt}) should be strictly less than current ply count ({old_ply_cnt})"
                )
            if new_ply_cnt - old_ply_cnt % 2 == 0:
                requested_by = old_color_to_move
            else:
                requested_by = old_color_to_move.opposite()

    return RollbackSuccessfulValidationResults(
        reversed_ply_events=chain([last_ply_event], ply_events),
        old_ply_cnt=old_ply_cnt,
        new_ply_cnt=new_ply_cnt,
        requested_by=requested_by
    )


async def perform_rollback(
    session: AsyncSession,
    mutable_state: MutableState,
    game_id: int,
    db_game: Game,
    validation_results: RollbackSuccessfulValidationResults
) -> None:
    rollback_dt = datetime.now(UTC)

    new_last_ply_event = None
    for ply_event in validation_results.reversed_ply_events:
        if ply_event.ply_index >= validation_results.new_ply_cnt:
            ply_event.is_cancelled = True
            session.add(ply_event)
        else:
            new_last_ply_event = ply_event
            break

    if new_last_ply_event:
        time_update = new_last_ply_event.time_update
        current_sip = new_last_ply_event.sip_after
    else:
        time_update = await get_initial_time(session, game_id)
        current_sip = db_game.custom_starting_sip or DEFAULT_STARTING_SIP

    if time_update:
        time_update = time_update.model_copy()
        time_update.updated_at = rollback_dt
        time_update.reason = GameTimeUpdateReason.ROLLBACK
        time_update.ticking_side = validation_results.requested_by if validation_results.new_ply_cnt >= 2 else None
        session.add(time_update)

    event = GameRollbackEvent(
        occurred_at=rollback_dt,
        ply_cnt_before=validation_results.old_ply_cnt,
        ply_cnt_after=validation_results.new_ply_cnt,
        requested_by=validation_results.requested_by,
        game_id=game_id,
        time_update=time_update
    )
    await append_rollback_event(session, mutable_state, event, game_id, current_sip)

    if time_update:
        await plan_timeout_check(
            triggering_time_update=time_update,
            game_id=game_id,
            is_external=db_game.external_uploader_ref is not None
        )
