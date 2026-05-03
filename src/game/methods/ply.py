from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from fastapi import HTTPException

from common.time_control import TimeControlKind
from config.models import MainConfig, SecretConfig
from game.datatypes import OutcomeKind, SimpleOutcome, TimeRemainders
from game.exceptions import PlyInvalidException, TimeoutReachedException
from game.methods.event import append_event
from game.methods.get import get_current_sip_and_ply_cnt, get_last_ply_event, get_latest_time_update, has_occured_thrice, is_stale
from game.methods.offer import cancel_all_active_offers
from game.methods.timeout import plan_timeout_check
from game.methods.end import end_game
from game.models.main import Game
from game.models.ply import GamePlyEvent
from game.models.polymorphous import PlyPayload
from game.models.time_update import GameTimeUpdate, GameTimeUpdateReason
from net.core import MutableState
from board.constants.sip import DEFAULT_STARTING_SIP
from board.coords import HexCoordinates
from board.deserializers.sip import position_from_sip
from board.piece import PieceColor
from board.ply import Ply
from board.position import Position, PositionFinalityGroup
from board.serializers.sip import get_sip
from utils.async_orm_session import AsyncSession


@dataclass
class PlyTimeRemainders:
    white_ms_after_execution: int | None = None
    black_ms_after_execution: int | None = None


def _get_simple_outcome(session: AsyncSession, game_id: int, new_position: Position, new_sip: str, new_ply_index: int) -> SimpleOutcome | None:
    match new_position.get_finality_group():
        case PositionFinalityGroup.FATUM:
            return SimpleOutcome(kind=OutcomeKind.FATUM, winner=new_position.color_to_move.opposite())
        case PositionFinalityGroup.BREAKTHROUGH:
            return SimpleOutcome(kind=OutcomeKind.BREAKTHROUGH, winner=new_position.color_to_move.opposite())

    if has_occured_thrice(session, game_id, new_sip):
        return SimpleOutcome(kind=OutcomeKind.REPETITION)

    if is_stale(session, game_id, new_ply_index):
        return SimpleOutcome(kind=OutcomeKind.NO_PROGRESS)

    return None


async def _construct_new_ply_time_update(
    session: AsyncSession,
    game_id: int,
    ply_dt: datetime,
    new_ply_index: int,
    color_to_move: PieceColor,
    timeout_grace_ms: int,
    bonus_secs: int = 0,
) -> GameTimeUpdate | None:
    latest_time_update = await get_latest_time_update(session, game_id)
    if not latest_time_update:
        return None

    new_time_update = GameTimeUpdate(
        updated_at=ply_dt,
        white_ms=latest_time_update.white_ms,
        black_ms=latest_time_update.black_ms,
        ticking_side=color_to_move if new_ply_index >= 1 else None,
        reason=GameTimeUpdateReason.PLY
    )

    if latest_time_update.ticking_side:
        ms_passed = int((ply_dt - latest_time_update.updated_at).total_seconds() * 1000)
        if latest_time_update.ticking_side == PieceColor.WHITE:
            new_time_update.white_ms -= ms_passed
            remaining_time_at_check = new_time_update.white_ms
            new_time_update.white_ms += bonus_secs * 1000
        else:
            new_time_update.black_ms -= ms_passed
            remaining_time_at_check = new_time_update.black_ms
            new_time_update.black_ms += bonus_secs * 1000

        if remaining_time_at_check <= -timeout_grace_ms:
            timed_out_at = ply_dt + timedelta(milliseconds=remaining_time_at_check)
            raise TimeoutReachedException(winner=latest_time_update.ticking_side.opposite(), reached_at=timed_out_at)

    return new_time_update


async def append_ply(
    session: AsyncSession,
    mutable_state: MutableState,
    main_config: MainConfig,
    secret_config: SecretConfig,
    payload: PlyPayload,
    db_game: Game,
    time_remainders: TimeRemainders | None,
    assumed_moving_color: PieceColor | None = None
) -> tuple[SimpleOutcome | None, str, GameTimeUpdate | None]:
    prev_ply_event = await get_last_ply_event(session, payload.game_id)
    prev_sip, new_ply_index = get_current_sip_and_ply_cnt(db_game, prev_ply_event)
    prev_position = Position.default_starting() if prev_sip == DEFAULT_STARTING_SIP else position_from_sip(prev_sip)

    if assumed_moving_color and prev_position.color_to_move != assumed_moving_color:
        raise HTTPException(403, f"It's not your turn. Current SIP is {prev_sip}")

    if payload.original_sip and prev_sip != payload.original_sip:
        raise HTTPException(422, f"Wrong SIP. Current SIP is {prev_sip}")

    from_coords = HexCoordinates(payload.from_i, payload.from_j)
    to_coords = HexCoordinates(payload.to_i, payload.to_j)
    ply = Ply(from_coords, to_coords, payload.morph_into)

    if not prev_position.is_ply_possible(ply):
        raise PlyInvalidException(prev_sip)

    perform_ply_result = prev_position.perform_ply(ply)
    new_sip = get_sip(perform_ply_result.new_position)

    ply_dt = datetime.now(UTC)

    if not db_game.external_uploader_ref:
        await cancel_all_active_offers(session, mutable_state, payload.game_id, ply_dt)

    if time_remainders:
        if db_game.time_control_kind == TimeControlKind.CORRESPONDENCE:
            raise HTTPException(422, f"Game {payload.game_id} is a correspondence one")
        if not db_game.external_uploader_ref:
            raise HTTPException(422, f"Game {payload.game_id} is not external, therefore it's not possible to assign time remainders directly")
        new_time_update: GameTimeUpdate | None = GameTimeUpdate(
            updated_at=ply_dt,
            white_ms=time_remainders.white_ms,
            black_ms=time_remainders.black_ms,
            ticking_side=prev_position.color_to_move.opposite() if new_ply_index >= 1 else None,
            reason=GameTimeUpdateReason.PLY,
            game_id=payload.game_id
        )
    elif db_game.fischer_time_control:
        new_time_update = await _construct_new_ply_time_update(
            session,
            payload.game_id,
            ply_dt,
            new_ply_index,
            color_to_move=perform_ply_result.new_position.color_to_move,
            timeout_grace_ms=0,
            bonus_secs=db_game.fischer_time_control.increment_seconds
        )
    else:
        new_time_update = None

    event = GamePlyEvent(
        occurred_at=ply_dt,
        ply_index=new_ply_index,
        from_i=ply.departure.i,
        from_j=ply.departure.j,
        to_i=ply.destination.i,
        to_j=ply.destination.j,
        morph_into=ply.morph_into,
        game_id=payload.game_id,
        kind=perform_ply_result.properties.ply_kind,
        moving_color=prev_position.color_to_move,
        moved_piece=perform_ply_result.properties.moving_piece.kind,
        target_piece=perform_ply_result.properties.target_piece.kind if perform_ply_result.properties.target_piece else None,
        sip_after=new_sip,
        time_update=new_time_update
    )
    await append_event(session, mutable_state, event, payload.game_id, commit=False)

    db_game.latest_sip = new_sip
    session.add(db_game)
    await session.commit()
    await session.refresh(db_game)

    outcome = _get_simple_outcome(session, payload.game_id, perform_ply_result.new_position, new_sip, new_ply_index)
    if outcome:
        await end_game(
            session,
            mutable_state,
            main_config,
            secret_config,
            payload.game_id,
            outcome.kind,
            outcome.winner,
            ply_dt,
            pre_retrieved_db_game=db_game,
            pre_retrieved_latest_time_update=new_time_update
        )
    elif new_time_update:
        await plan_timeout_check(
            triggering_time_update=new_time_update,
            game_id=payload.game_id,
            is_external=db_game.external_uploader_ref is not None
        )
    return outcome, new_sip, new_time_update
