from datetime import UTC, datetime
from typing import Sequence
from fastapi import APIRouter, HTTPException, Query
from sqlmodel import Session, desc, select
from models.channel import GameEventChannel
from models.game import (
    ExternalGameAddTimePayload,
    ExternalGameAppendPlyPayload,
    ExternalGameAppendPlyResponse,
    ExternalGameCreatePayload,
    ExternalGameEndPayload,
    ExternalGameRollbackPayload,
    Game,
    GameFilter,
    GamePlyEvent,
    GamePublic,
    GameRollbackEvent,
    PlyBroadcastedData,
    RollbackBroadcastedData,
    SimpleOutcome,
)
from models.game.time_added import GameTimeAddedEvent, TimeAddedBroadcastedData
from models.game.time_update import GameTimeUpdate, GameTimeUpdatePublic, GameTimeUpdateReason
from net.outgoing import WebsocketOutgoingEventRegistry
from routers.shared_methods.game.create import create_external_game
from routers.shared_methods.game.update import check_timeout, end_game
from routers.shared_methods.game.get import TimeoutReachedException, construct_new_ply_time_update, get_ply_history
from routers.shared_methods.game.cast import compose_public_game
from routers.shared_queries.game import get_initial_time, get_last_ply_event, get_latest_time_update, has_occured_thrice, is_stale
from routers.utils import MainConfigDependency, MandatoryUserDependency, MutableStateDependency, SecretConfigDependency, SessionDependency
from routers.websocket.game import get_current_sip_and_ply_cnt
from rules import DEFAULT_STARTING_SIP, HexCoordinates, PieceColor, Ply, Position, PositionFinalityGroup
from utils.datatypes import OutcomeKind, UserReference
from utils.query import model_cast_optional


router = APIRouter(prefix="/game")


@router.get("/{game_id}", response_model=GamePublic)
async def get_game(*, session: SessionDependency, game_id: int):
    db_game = session.get(Game, game_id)

    if not db_game:
        raise HTTPException(status_code=404, detail="Game not found")

    return compose_public_game(session, db_game)


async def get_current_games(session: Session, game_filter: GameFilter, offset: int = 0, limit: int = 10) -> Sequence[Game]:
    return session.exec(select(
        Game
    ).where(
        Game.outcome == None,  # noqa
        *game_filter.construct_conditions()
    ).offset(offset).limit(limit)).all()


@router.get("/current", response_model=list[GamePublic])
async def get_current_games_route(*, session: SessionDependency, offset: int = 0, limit: int = Query(default=10, le=50), game_filter: GameFilter = GameFilter()):
    return [
        compose_public_game(session, game)
        for game in await get_current_games(session, game_filter, offset, limit)
    ]


async def get_recent_games(session: Session, game_filter: GameFilter, offset: int = 0, limit: int = 10) -> Sequence[Game]:
    return session.exec(select(
        Game
    ).where(
        Game.outcome != None,  # noqa
        *game_filter.construct_conditions()
    ).order_by(desc(Game.started_at)).offset(offset).limit(limit)).all()


@router.get("/recent", response_model=list[GamePublic])
async def get_recent_games_route(*, session: SessionDependency, offset: int = 0, limit: int = Query(default=10, le=50), game_filter: GameFilter = GameFilter()):
    return [
        compose_public_game(session, game)
        for game in await get_recent_games(session, game_filter, offset, limit)
    ]


@router.get("/{game_id}/check_timeout")
async def check_timeout_route(*, session: SessionDependency, state: MutableStateDependency, secret_config: SecretConfigDependency, game_id: int):
    await check_timeout(session=session, state=state, secret_config=secret_config, game_id=game_id)


@router.get("/external/create", response_model=GamePublic)
async def create_external_game_route(*, payload: ExternalGameCreatePayload, client: MandatoryUserDependency, session: SessionDependency, state: MutableStateDependency):
    return await create_external_game(
        uploader=client,
        white_player_ref=payload.white_player_ref,
        black_player_ref=payload.black_player_ref,
        time_control=payload.time_control,
        custom_starting_sip=payload.custom_starting_sip,
        session=session,
        state=state
    )


@router.get("/external/append_ply", response_model=ExternalGameAppendPlyResponse)
async def append_ply_to_external_game_route(
    *,
    payload: ExternalGameAppendPlyPayload,
    client: MandatoryUserDependency,
    session: SessionDependency,
    state: MutableStateDependency,
    secret_config: SecretConfigDependency
):
    db_game = session.get(Game, payload.game_id)
    if not db_game:
        raise HTTPException(status_code=404, detail="Game not found")

    if db_game.external_uploader_ref != client.reference:
        if db_game.external_uploader_ref:
            pretty_uploader_ref = UserReference(db_game.external_uploader_ref).pretty()
            message = f"Only {pretty_uploader_ref} can modify this game"
        else:
            message = "Cannot modify internal game"
        raise HTTPException(status_code=403, detail=message)

    if db_game.outcome:
        raise HTTPException(status_code=400, detail="Game has already ended")

    prev_ply_event = get_last_ply_event(session, payload.game_id)
    prev_sip, new_ply_index = get_current_sip_and_ply_cnt(db_game, prev_ply_event)
    prev_position = Position.default_starting() if prev_sip == DEFAULT_STARTING_SIP else Position.from_sip(prev_sip)

    from_coords = HexCoordinates(payload.from_i, payload.from_j)
    to_coords = HexCoordinates(payload.to_i, payload.to_j)
    ply = Ply(from_coords, to_coords, payload.morph_into)

    if not prev_position.is_ply_possible(ply):
        raise HTTPException(status_code=400, detail=f"Impossible ply. Current SIP is {prev_sip}")

    perform_ply_result = prev_position.perform_ply_without_validation(ply)
    new_sip = perform_ply_result.new_position.to_sip()

    ply_dt = datetime.now(UTC)

    if db_game.fischer_time_control:
        if not payload.white_ms_after_execution or not payload.black_ms_after_execution:
            raise HTTPException(status_code=400, detail="Time remainders should be provided")

        new_time_update = GameTimeUpdate(
            updated_at=ply_dt,
            white_ms=payload.white_ms_after_execution,
            black_ms=payload.black_ms_after_execution,
            ticking_side=prev_position.color_to_move.opposite() if new_ply_index >= 1 else None,
            reason=GameTimeUpdateReason.PLY,
            game_id=payload.game_id
        )
        session.add(new_time_update)
    else:
        new_time_update = None

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
    session.commit()

    await state.ws_subscribers.broadcast(
        WebsocketOutgoingEventRegistry.NEW_PLY,
        PlyBroadcastedData(
            occurred_at=ply_dt,
            from_i=ply.departure.i,
            from_j=ply.departure.j,
            to_i=ply.destination.i,
            to_j=ply.destination.j,
            morph_into=ply.morph_into,
            game_id=payload.game_id,
            sip_after=new_sip,
            time_update=model_cast_optional(new_time_update, GameTimeUpdatePublic)
        ),
        GameEventChannel(game_id=payload.game_id)
    )

    match perform_ply_result.new_position.get_finality_group():
        case PositionFinalityGroup.FATUM:
            await end_game(session, state, secret_config, payload.game_id, OutcomeKind.FATUM, prev_position.color_to_move, ply_dt)
            return ExternalGameAppendPlyResponse(outcome=SimpleOutcome(kind=OutcomeKind.FATUM, winner=prev_position.color_to_move))
        case PositionFinalityGroup.BREAKTHROUGH:
            await end_game(session, state, secret_config, payload.game_id, OutcomeKind.BREAKTHROUGH, prev_position.color_to_move, ply_dt)
            return ExternalGameAppendPlyResponse(outcome=SimpleOutcome(kind=OutcomeKind.BREAKTHROUGH, winner=prev_position.color_to_move))

    if has_occured_thrice(session, payload.game_id, new_sip):
        await end_game(session, state, secret_config, payload.game_id, OutcomeKind.REPETITION, None, ply_dt)
        return ExternalGameAppendPlyResponse(outcome=SimpleOutcome(kind=OutcomeKind.REPETITION, winner=None))

    if is_stale(session, payload.game_id, new_ply_index):
        await end_game(session, state, secret_config, payload.game_id, OutcomeKind.NO_PROGRESS, None, ply_dt)
        return ExternalGameAppendPlyResponse(outcome=SimpleOutcome(kind=OutcomeKind.NO_PROGRESS, winner=None))

    return ExternalGameAppendPlyResponse(outcome=None)


@router.get("/external/end")
async def end_external_game_route(
    *,
    payload: ExternalGameEndPayload,
    client: MandatoryUserDependency,
    session: SessionDependency,
    state: MutableStateDependency,
    secret_config: SecretConfigDependency
):
    if payload.outcome_kind == OutcomeKind.DRAW_AGREEMENT and payload.winner:
        raise HTTPException(status_code=400, detail="This outcome kind cannot have a winner")
    if payload.outcome_kind != OutcomeKind.DRAW_AGREEMENT and not payload.winner:
        raise HTTPException(status_code=400, detail="This outcome kind should have a winner")

    db_game = session.get(Game, payload.game_id)
    if not db_game:
        raise HTTPException(status_code=404, detail="Game not found")

    if db_game.external_uploader_ref != client.reference:
        if db_game.external_uploader_ref:
            pretty_uploader_ref = UserReference(db_game.external_uploader_ref).pretty()
            message = f"Only {pretty_uploader_ref} can modify this game"
        else:
            message = "Cannot modify internal game"
        raise HTTPException(status_code=403, detail=message)

    await end_game(session, state, secret_config, payload.game_id, payload.outcome_kind, payload.winner)  # TODO: Ensure all of the necessary checks are present


@router.get("/external/rollback")
async def rollback_external_game_route(
    *,
    payload: ExternalGameRollbackPayload,
    client: MandatoryUserDependency,
    session: SessionDependency,
    state: MutableStateDependency
):
    game = session.get(Game, payload.game_id)
    if not game:
        raise HTTPException(status_code=404, detail="Game not found")

    if game.external_uploader_ref != client.reference:
        if game.external_uploader_ref:
            pretty_uploader_ref = UserReference(game.external_uploader_ref).pretty()
            message = f"Only {pretty_uploader_ref} can modify this game"
        else:
            message = "Cannot modify internal game"
        raise HTTPException(status_code=403, detail=message)

    if game.outcome:
        raise HTTPException(status_code=400, detail="Game has already ended")

    ply_events = get_ply_history(session, payload.game_id, reverse_order=True)
    last_ply_event = next(ply_events, None)
    if not last_ply_event:
        raise HTTPException(status_code=400, detail="Too early for a rollback")

    old_ply_cnt = last_ply_event.ply_index + 1
    if old_ply_cnt <= payload.new_ply_cnt:
        raise HTTPException(
            status_code=400,
            detail=f"new_ply_cnt (got: {payload.new_ply_cnt} should be strictly less than current ply count ({old_ply_cnt})"
        )

    last_ply_event.is_cancelled = True  # At least one ply will be cancelled, we've already ensured that above
    session.add(last_ply_event)

    # Continuing the iteration
    # We'll start from the element before the last one, because we've already extracted the last one using next() function above
    new_last_ply_event = None
    for ply_event in ply_events:
        if ply_event.ply_index < payload.new_ply_cnt:
            new_last_ply_event = ply_event
            break
        ply_event.is_cancelled = True
        session.add(ply_event)

    rollback_dt = datetime.now(UTC)

    new_last_ply_event = next(ply_events, None)
    if new_last_ply_event:
        time_update = new_last_ply_event.time_update
        current_sip = new_last_ply_event.sip_after
    else:
        time_update = get_initial_time(session, payload.game_id)
        current_sip = game.custom_starting_sip or DEFAULT_STARTING_SIP

    requested_by = Position.color_to_move_from_sip(current_sip)

    if time_update:
        time_update = time_update.model_copy()
        time_update.updated_at = rollback_dt
        time_update.reason = GameTimeUpdateReason.ROLLBACK
        time_update.ticking_side = Position.color_to_move_from_sip(current_sip) if payload.new_ply_cnt >= 2 else None
        session.add(time_update)

    rollback_event = GameRollbackEvent(
        occurred_at=rollback_dt,
        ply_cnt_before=old_ply_cnt,
        ply_cnt_after=payload.new_ply_cnt,
        requested_by=requested_by,
        game_id=payload.game_id,
        time_update=time_update
    )
    session.add(rollback_event)
    session.commit()

    await state.ws_subscribers.broadcast(
        WebsocketOutgoingEventRegistry.ROLLBACK,
        rollback_event.to_broadcasted_data(current_sip),
        GameEventChannel(game_id=payload.game_id)
    )


@router.get("/external/add_time")
async def add_time_external_game_route(
    *,
    payload: ExternalGameAddTimePayload,
    client: MandatoryUserDependency,
    session: SessionDependency,
    state: MutableStateDependency,
    main_config: MainConfigDependency
):
    game = session.get(Game, payload.game_id)
    if not game:
        raise HTTPException(status_code=404, detail="Game not found")

    if game.external_uploader_ref != client.reference:
        if game.external_uploader_ref:
            pretty_uploader_ref = UserReference(game.external_uploader_ref).pretty()
            message = f"Only {pretty_uploader_ref} can modify this game"
        else:
            message = "Cannot modify internal game"
        raise HTTPException(status_code=403, detail=message)

    if game.outcome:
        raise HTTPException(status_code=400, detail="Game has already ended")

    latest_time_update = get_latest_time_update(session, payload.game_id)

    if not latest_time_update:
        raise HTTPException(status_code=400, detail=f"Game {payload.game_id} is a correspondence game")

    addition_dt = datetime.now(UTC)

    secs_added = main_config.rules.secs_added_manually
    ms_added = secs_added * 1000

    appended_time_update = latest_time_update.model_copy()
    appended_time_update.updated_at = addition_dt
    appended_time_update.reason = GameTimeUpdateReason.TIME_ADDED
    if payload.receiver == PieceColor.WHITE:
        appended_time_update.white_ms += ms_added
    else:
        appended_time_update.black_ms += ms_added

    time_added_event = GameTimeAddedEvent(
        occurred_at=addition_dt,
        amount_seconds=secs_added,
        receiver=payload.receiver,
        game_id=payload.game_id,
        time_update=appended_time_update
    )

    session.add(time_added_event)
    session.add(appended_time_update)
    session.commit()

    await state.ws_subscribers.broadcast(
        WebsocketOutgoingEventRegistry.TIME_ADDED,
        time_added_event.to_broadcasted_data(),
        GameEventChannel(game_id=payload.game_id)
    )
