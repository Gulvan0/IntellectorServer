from fastapi import APIRouter, HTTPException

from common.dependencies import (
    MainConfigDependency,
    MandatoryUserDependency,
    MutableStateDependency,
    OpeningMappingDepencency,
    SecretConfigDependency,
    SessionDependency,
)
from game.dependencies import CLIENT_IS_UPLOADER_DEPENDENCY, GAME_EXISTS_DEPENDENCY, GAME_IS_ONGOING_DEPENDENCY, GameDependency, SummarizedGameDependency
from game.methods.ply import append_ply
from game.exceptions import PlyInvalidException
from game.methods.create import create_external_game
from game.methods.end import end_game
from game.methods.rollback import RollbackPlyCountInput, perform_rollback, validate_rollback
from game.models.rest.external import (
    ExternalGameAppendPlyPayload,
    ExternalGameAppendPlyResponse,
    ExternalGameCreatePayload,
    ExternalGameEndPayload,
    ExternalGameRollbackPayload,
)
from game.models.main import GameSummaryPublic
from net.base_router import LoggingRoute


router = APIRouter(prefix="/game/external", route_class=LoggingRoute)


@router.post("/create", response_model=GameSummaryPublic)
async def create(
    *,
    payload: ExternalGameCreatePayload,
    client: MandatoryUserDependency,
    session: SessionDependency,
    state: MutableStateDependency
) -> GameSummaryPublic:
    return await create_external_game(
        uploader=client,
        white_player_ref=payload.white_player_ref,
        black_player_ref=payload.black_player_ref,
        time_control=payload.time_control,
        custom_starting_sip=payload.custom_starting_sip,
        session=session,
        state=state
    )


@router.post("/append_ply", response_model=ExternalGameAppendPlyResponse, dependencies=[
    CLIENT_IS_UPLOADER_DEPENDENCY,
    GAME_IS_ONGOING_DEPENDENCY,
])
async def append_ply_route(
    *,
    payload: ExternalGameAppendPlyPayload,
    db_game: SummarizedGameDependency,
    session: SessionDependency,
    state: MutableStateDependency,
    main_config: MainConfigDependency,
    secret_config: SecretConfigDependency,
    openings: OpeningMappingDepencency,
) -> ExternalGameAppendPlyResponse:
    try:
        outcome, _, _ = await append_ply(
            session,
            state,
            main_config,
            secret_config,
            openings,
            payload,
            db_game,
            payload.time_remainders
        )
    except PlyInvalidException as e:
        raise HTTPException(status_code=422, detail=f"Impossible ply. Current SIP is {e.current_sip}")
    else:
        return ExternalGameAppendPlyResponse(outcome=outcome)


@router.post("/end", dependencies=[
    GAME_EXISTS_DEPENDENCY,
    CLIENT_IS_UPLOADER_DEPENDENCY,
    GAME_IS_ONGOING_DEPENDENCY,
])
async def end(
    *,
    payload: ExternalGameEndPayload,
    session: SessionDependency,
    state: MutableStateDependency,
    main_config: MainConfigDependency,
    secret_config: SecretConfigDependency
) -> None:
    await end_game(session, state, main_config, secret_config, payload.game_id, payload.outcome_kind, payload.winner)


@router.post("/rollback", dependencies=[
    CLIENT_IS_UPLOADER_DEPENDENCY,
    GAME_IS_ONGOING_DEPENDENCY,
])
async def rollback(
    *,
    payload: ExternalGameRollbackPayload,
    db_game: GameDependency,
    session: SessionDependency,
    state: MutableStateDependency
) -> None:
    validation_results = await validate_rollback(session, payload.game_id, RollbackPlyCountInput(payload.new_ply_cnt))
    await perform_rollback(session, state, payload.game_id, db_game, validation_results)
