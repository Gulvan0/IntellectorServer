from dataclasses import dataclass
from datetime import UTC, datetime
from itertools import chain
from typing import Iterable

from src.config.models import MainConfig, SecretConfig
from src.game.datatypes import OutcomeKind, SimpleOutcome, TimeRemainders
from src.game.exceptions import PlyInvalidException, SinkException
from src.game.methods.cast import construct_new_ply_time_update
from src.game.methods.event import append_event, append_rollback_event
from src.game.methods.get import get_current_sip_and_ply_cnt, get_initial_time, get_last_ply_event, get_latest_time_update, get_ply_history, has_occured_thrice, is_stale
from src.game.methods.update import cancel_all_active_offers, end_game
from src.game.models.main import Game
from src.game.models.ply import GamePlyEvent
from src.game.models.polymorphous import PayloadWithGameId, PlyPayload
from src.game.models.rollback import GameRollbackEvent
from src.game.models.time_added import GameTimeAddedEvent
from src.game.models.time_update import GameTimeUpdate, GameTimeUpdateReason
from src.net.core import MutableState
from src.rules.constants.sip import DEFAULT_STARTING_SIP
from src.rules.coords import HexCoordinates
from src.rules.deserializers.sip import color_to_move_from_sip, position_from_sip
from src.rules.piece import PieceColor
from src.rules.ply import Ply
from src.rules.position import Position, PositionFinalityGroup
from src.rules.serializers.sip import get_sip
from src.utils.async_orm_session import AsyncSession


@dataclass
class PlyTimeRemainders:
    white_ms_after_execution: int | None = None
    black_ms_after_execution: int | None = None


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


async def append_ply_sink(
    session: AsyncSession,
    mutable_state: MutableState,
    secret_config: SecretConfig,
    payload: PlyPayload,
    db_game: Game,
    time_remainders: TimeRemainders | None,
    assumed_moving_color: PieceColor | None = None
) -> SimpleOutcome | None:
    prev_ply_event = await get_last_ply_event(session, payload.game_id)
    prev_sip, new_ply_index = get_current_sip_and_ply_cnt(db_game, prev_ply_event)
    prev_position = Position.default_starting() if prev_sip == DEFAULT_STARTING_SIP else position_from_sip(prev_sip)

    if assumed_moving_color and prev_position.color_to_move != assumed_moving_color:
        raise SinkException(f"It's not your turn. Current SIP is {prev_sip}")

    if payload.original_sip and prev_sip != payload.original_sip:
        raise SinkException(f"Wrong SIP. Current SIP is {prev_sip}")

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
        if not db_game.fischer_time_control:
            raise SinkException(f"Game {payload.game_id} is a correspondence one")
        if not db_game.external_uploader_ref:
            raise SinkException(f"Game {payload.game_id} is not external, therefore it's not possible to assign time remainders directly")
        new_time_update: GameTimeUpdate | None = GameTimeUpdate(
            updated_at=ply_dt,
            white_ms=time_remainders.white_ms,
            black_ms=time_remainders.black_ms,
            ticking_side=prev_position.color_to_move.opposite() if new_ply_index >= 1 else None,
            reason=GameTimeUpdateReason.PLY,
            game_id=payload.game_id
        )
    else:
        new_time_update = await construct_new_ply_time_update(
            session,
            payload.game_id,
            ply_dt,
            new_ply_index,
            color_to_move=perform_ply_result.new_position.color_to_move,
            timeout_grace_ms=0
        )

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
    await append_event(session, mutable_state, event, payload.game_id)

    outcome = _get_simple_outcome(session, payload.game_id, perform_ply_result.new_position, new_sip, new_ply_index)
    if outcome:
        await end_game(
            session,
            mutable_state,
            secret_config,
            payload.game_id,
            outcome.kind,
            outcome.winner,
            ply_dt
        )
    return outcome


async def validate_rollback(
    session: AsyncSession,
    game_id: int,
    input: RollbackPlyCountInput | RollbackOfferAuthorInput
) -> RollbackSuccessfulValidationResults:
    ply_events = await get_ply_history(session, game_id, reverse_order=True)
    last_ply_event = next(ply_events, None)
    if not last_ply_event:
        raise SinkException("Too early for a rollback")

    old_color_to_move = color_to_move_from_sip(last_ply_event.sip_after)
    old_ply_cnt = last_ply_event.ply_index + 1

    match input:
        case RollbackOfferAuthorInput(offer_author):
            if offer_author != old_color_to_move:
                new_ply_cnt = old_ply_cnt - 1
            else:
                new_ply_cnt = old_ply_cnt - 2
                if new_ply_cnt < 0:
                    raise SinkException("Too early for a rollback")
            requested_by = offer_author
        case RollbackPlyCountInput(ply_cnt):
            new_ply_cnt = ply_cnt
            if new_ply_cnt >= old_ply_cnt:
                raise SinkException(
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


async def add_time_sink(
    session: AsyncSession,
    main_config: MainConfig,
    mutable_state: MutableState,
    payload: PayloadWithGameId,
    receiver: PieceColor
) -> None:
    latest_time_update = await get_latest_time_update(session, payload.game_id)

    if not latest_time_update:
        raise SinkException(f"Game {payload.game_id} is a correspondence game")

    addition_dt = datetime.now(UTC)

    secs_added = main_config.rules.secs_added_manually
    ms_added = secs_added * 1000

    appended_time_update = latest_time_update.model_copy()
    appended_time_update.updated_at = addition_dt
    appended_time_update.reason = GameTimeUpdateReason.TIME_ADDED
    if receiver == PieceColor.WHITE:
        appended_time_update.white_ms += ms_added
    else:
        appended_time_update.black_ms += ms_added

    event = GameTimeAddedEvent(
        occurred_at=addition_dt,
        amount_seconds=secs_added,
        receiver=receiver,
        game_id=payload.game_id,
        time_update=appended_time_update
    )
    await append_event(session, mutable_state, event, payload.game_id)
