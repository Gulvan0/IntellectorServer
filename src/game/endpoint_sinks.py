from dataclasses import dataclass
from datetime import UTC, datetime
from src.config.models import MainConfig, SecretConfig
from src.game.datatypes import OutcomeKind, SimpleOutcome, TimeRemainders
from src.game.exceptions import PlyInvalidException, SinkException
from src.game.methods.cast import construct_new_ply_time_update
from src.game.methods.get import get_current_sip_and_ply_cnt, get_last_ply_event, get_latest_time_update, has_occured_thrice, is_stale
from src.game.methods.update import cancel_all_active_offers, end_game
from src.game.models.main import Game
from src.game.models.ply import GamePlyEvent
from src.game.models.polymorphous import PayloadWithGameId, PlyPayload
from src.game.models.time_added import GameTimeAddedEvent
from src.game.models.time_update import GameTimeUpdate, GameTimeUpdateReason
from src.net.core import MutableState
from src.net.outgoing import WebsocketOutgoingEventRegistry
from src.pubsub.models import GameEventChannel
from src.rules import DEFAULT_STARTING_SIP, HexCoordinates, PieceColor, Ply, Position, PositionFinalityGroup
from src.utils.async_orm_session import AsyncSession


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
    prev_position = Position.default_starting() if prev_sip == DEFAULT_STARTING_SIP else Position.from_sip(prev_sip)

    if assumed_moving_color and prev_position.color_to_move != assumed_moving_color:
        raise SinkException(f"It's not your turn. Current SIP is {prev_sip}")

    if payload.original_sip and prev_sip != payload.original_sip:
        raise SinkException(f"Wrong SIP. Current SIP is {prev_sip}")

    from_coords = HexCoordinates(payload.from_i, payload.from_j)
    to_coords = HexCoordinates(payload.to_i, payload.to_j)
    ply = Ply(from_coords, to_coords, payload.morph_into)

    if not prev_position.is_ply_possible(ply):
        raise PlyInvalidException(prev_sip)

    perform_ply_result = prev_position.perform_ply_without_validation(ply)
    new_sip = perform_ply_result.new_position.to_sip()

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

    ply_event = GamePlyEvent(
        occurred_at=ply_dt,
        ply_index=new_ply_index,
        from_i=ply.departure.i,
        from_j=ply.departure.j,
        to_i=ply.destination.i,
        to_j=ply.destination.j,
        morph_into=ply.morph_into,
        game_id=payload.game_id,
        kind=perform_ply_result.ply_kind,
        moving_color=prev_position.color_to_move,
        moved_piece=perform_ply_result.moving_piece.kind,
        target_piece=perform_ply_result.target_piece.kind if perform_ply_result.target_piece else None,
        sip_after=new_sip,
        time_update=new_time_update
    )
    session.add(ply_event)
    await session.commit()

    await mutable_state.ws_subscribers.broadcast(
        WebsocketOutgoingEventRegistry.NEW_PLY,
        ply_event.to_broadcasted_data(),
        GameEventChannel(game_id=payload.game_id)
    )

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


async def rollback_sink(
    session: AsyncSession,
    mutable_state: MutableState,
    payload: PayloadWithGameId,
    new_last_ply_index: int
) -> None:
    ...


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

    time_added_event = GameTimeAddedEvent(
        occurred_at=addition_dt,
        amount_seconds=secs_added,
        receiver=receiver,
        game_id=payload.game_id,
        time_update=appended_time_update
    )

    session.add(time_added_event)
    session.add(appended_time_update)
    await session.commit()

    await mutable_state.ws_subscribers.broadcast(
        WebsocketOutgoingEventRegistry.TIME_ADDED,
        time_added_event.to_broadcasted_data(),
        GameEventChannel(game_id=payload.game_id)
    )
