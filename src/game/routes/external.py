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
from src.game.endpoint_sinks import add_time_sink, append_ply_sink, rollback_sink
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
    await rollback_sink(session, state, payload, db_game, payload.new_ply_cnt)


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
