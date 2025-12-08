from contextlib import contextmanager
from typing import Generator
from fastapi import APIRouter, HTTPException

from src.common.dependencies import (
    MainConfigDependency,
    MandatoryUserDependency,
    MutableStateDependency,
    SecretConfigDependency,
    SessionDependency,
)
from src.game.dependencies.rest import CLIENT_IS_UPLOADER_DEPENDENCY, GAME_EXISTS_DEPENDENCY, GAME_IS_ONGOING_DEPENDENCY, GameDependency
from src.game.endpoint_sinks import RollbackPlyCountInput, add_time_sink, append_ply_sink, perform_rollback, validate_rollback
from src.game.exceptions import PlyInvalidException, SinkException, TimeoutReachedException
from src.game.methods.create import create_external_game
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
from src.net.base_router import LoggingRoute


router = APIRouter(prefix="/game/external", route_class=LoggingRoute)


@contextmanager
def sink_exception_wrapper() -> Generator[None, None, None]:
    try:
        yield
    except SinkException as e:
        raise HTTPException(e.status_code or 400, e.message)


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
        with sink_exception_wrapper():
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
    with sink_exception_wrapper():
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
    with sink_exception_wrapper():
        validation_results = await validate_rollback(session, payload.game_id, RollbackPlyCountInput(payload.new_ply_cnt))
        await perform_rollback(session, state, payload.game_id, db_game, validation_results)


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
    with sink_exception_wrapper():
        await add_time_sink(session, main_config, state, payload, payload.receiver)
