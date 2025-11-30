from datetime import UTC, datetime
from fastapi import APIRouter, HTTPException

from src.common.dependencies import (
    MainConfigDependency,
    MandatoryUserDependency,
    MutableStateDependency,
    SecretConfigDependency,
    SessionDependency,
)
from src.game.dependencies.rest import CLIENT_IS_UPLOADER_DEPENDENCY, GAME_EXISTS_DEPENDENCY, GAME_IS_ONGOING_DEPENDENCY, GameDependency
from src.game.endpoint_sinks import add_time_sink, append_ply_sink
from src.game.exceptions import PlyInvalidException, TimeoutReachedException
from src.game.methods.create import create_external_game
from src.game.methods.get import (
    get_initial_time,
    get_ply_history,
)
from src.game.methods.update import end_game
from src.game.models.external import (
    ExternalGameAddTimePayload,
    ExternalGameAppendPlyPayload,
    ExternalGameAppendPlyResponse,
    ExternalGameCreatePayload,
    ExternalGameEndPayload,
    ExternalGameRollbackPayload,
)
from src.game.models.main import GamePublic
from src.game.models.rollback import GameRollbackEvent
from src.game.models.time_update import GameTimeUpdateReason
from src.net.base_router import LoggingRoute
from src.net.outgoing import WebsocketOutgoingEventRegistry
from src.pubsub.models import GameEventChannel
from src.rules import DEFAULT_STARTING_SIP, Position


router = APIRouter(prefix="/game/external", route_class=LoggingRoute)


@router.get("/create", response_model=GamePublic)
async def create(
    *,
    payload: ExternalGameCreatePayload,
    client: MandatoryUserDependency,
    session: SessionDependency,
    state: MutableStateDependency
):
    return await create_external_game(
        uploader=client,
        white_player_ref=payload.white_player_ref,
        black_player_ref=payload.black_player_ref,
        time_control=payload.time_control,
        custom_starting_sip=payload.custom_starting_sip,
        session=session,
        state=state
    )


@router.get("/append_ply", response_model=ExternalGameAppendPlyResponse, dependencies=[
    CLIENT_IS_UPLOADER_DEPENDENCY,
    GAME_IS_ONGOING_DEPENDENCY,
])
async def append_ply(
    *,
    payload: ExternalGameAppendPlyPayload,
    db_game: GameDependency,
    session: SessionDependency,
    state: MutableStateDependency,
    secret_config: SecretConfigDependency
):
    try:
        outcome = await append_ply_sink(
            session,
            state,
            secret_config,
            payload,
            db_game,
            payload.time_remainders
        )
    except TimeoutReachedException as e:
        raise HTTPException(status_code=400, detail=(
            "Server-side timeouts for external games are not implemented yet. "
            "Please end the game explicitly via the respecitive HTTP route or provide time remainders"
        ))
    except PlyInvalidException as e:
        raise HTTPException(status_code=400, detail=f"Impossible ply. Current SIP is {e.current_sip}")
    else:
        return ExternalGameAppendPlyResponse(outcome=outcome)


@router.get("/end", dependencies=[
    GAME_EXISTS_DEPENDENCY,
    CLIENT_IS_UPLOADER_DEPENDENCY,
    GAME_IS_ONGOING_DEPENDENCY,
])
async def end(
    *,
    payload: ExternalGameEndPayload,
    session: SessionDependency,
    state: MutableStateDependency,
    secret_config: SecretConfigDependency
):
    await end_game(session, state, secret_config, payload.game_id, payload.outcome_kind, payload.winner)


@router.get("/rollback", dependencies=[
    CLIENT_IS_UPLOADER_DEPENDENCY,
    GAME_IS_ONGOING_DEPENDENCY,
])
async def rollback(
    *,
    payload: ExternalGameRollbackPayload,
    db_game: GameDependency,
    session: SessionDependency,
    state: MutableStateDependency
):
    ply_events = await get_ply_history(session, payload.game_id, reverse_order=True)
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
        time_update = await get_initial_time(session, payload.game_id)
        current_sip = db_game.custom_starting_sip or DEFAULT_STARTING_SIP

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
    await session.commit()

    await state.ws_subscribers.broadcast(
        WebsocketOutgoingEventRegistry.ROLLBACK,
        rollback_event.to_broadcasted_data(current_sip),
        GameEventChannel(game_id=payload.game_id)
    )


@router.get("/add_time", dependencies=[
    GAME_EXISTS_DEPENDENCY,
    CLIENT_IS_UPLOADER_DEPENDENCY,
    GAME_IS_ONGOING_DEPENDENCY,
])
async def add_time(
    *,
    payload: ExternalGameAddTimePayload,
    session: SessionDependency,
    state: MutableStateDependency,
    main_config: MainConfigDependency
):
    await add_time_sink(session, main_config, state, payload, payload.receiver)
