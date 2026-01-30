from fastapi import APIRouter, HTTPException
from common.dependencies import MainConfigDependency, MutableStateDependency, SecretConfigDependency, SessionDependency
from game.datatypes import OfferAction, OfferKind, OutcomeKind
from game.dependencies import GAME_IS_INTERNAL_DEPENDENCY, GAME_IS_ONGOING_DEPENDENCY, GameDependency, PlayerColorDependency
from game.methods.ply import append_ply
from game.exceptions import PlyInvalidException, TimeoutReachedException
from game.methods.cast import compose_state_refresh
from game.methods.end import end_game
from game.methods.offer import accept_draw, accept_takeback, cancel_offer, create_offer, decline_offer
from game.models.rest.internal import InternalGameAppendPlyPayload, InternalGameAppendPlyResponse, InternalGamePerformOfferActionPayload
from game.models.time_update import GameTimeUpdatePublic
from net.base_router import LoggingRoute


router = APIRouter(prefix="/game/internal", route_class=LoggingRoute)


@router.post("/append_ply", response_model=InternalGameAppendPlyResponse, dependencies=[
    GAME_IS_INTERNAL_DEPENDENCY,
    GAME_IS_ONGOING_DEPENDENCY,
])
async def append_ply_route(
    *,
    payload: InternalGameAppendPlyPayload,
    db_game: GameDependency,
    client_color: PlayerColorDependency,
    session: SessionDependency,
    state: MutableStateDependency,
    main_config: MainConfigDependency,
    secret_config: SecretConfigDependency
) -> InternalGameAppendPlyResponse:
    try:
        outcome, sip_after, time_update = await append_ply(
            session,
            state,
            main_config,
            secret_config,
            payload,
            db_game,
            None,
            client_color
        )
    except TimeoutReachedException as e:
        await end_game(
            session,
            state,
            main_config,
            secret_config,
            payload.game_id,
            OutcomeKind.TIMEOUT,
            e.winner,
            e.reached_at,
            pre_retrieved_db_game=db_game,
        )
    except PlyInvalidException as e:
        game_state = await compose_state_refresh(
            session=session,
            game_id=payload.game_id,
            game=db_game,
            reason='invalid_move',
            include_spectator_messages=False
        )
        raise HTTPException(status_code=422, detail=dict(
            reason="Impossible ply",
            game_state=game_state
        ))
    return InternalGameAppendPlyResponse(outcome=outcome, sip_after=sip_after, time_update=GameTimeUpdatePublic.cast(time_update))


@router.post("/perform_offer_action", dependencies=[
    GAME_IS_INTERNAL_DEPENDENCY,
    GAME_IS_ONGOING_DEPENDENCY,
])
async def perform_offer_action(
    *,
    payload: InternalGamePerformOfferActionPayload,
    db_game: GameDependency,
    client_color: PlayerColorDependency,
    session: SessionDependency,
    state: MutableStateDependency,
    main_config: MainConfigDependency,
    secret_config: SecretConfigDependency
) -> None:
    match payload.action_kind:
        case OfferAction.CREATE:
            await create_offer(session, state, main_config, secret_config, db_game, payload.offer_kind, client_color)
        case OfferAction.CANCEL:
            await cancel_offer(session, state, payload.game_id, payload.offer_kind, client_color)
        case OfferAction.DECLINE:
            await decline_offer(session, state, payload.game_id, payload.offer_kind, client_color.opposite())
        case OfferAction.ACCEPT:
            if payload.offer_kind == OfferKind.DRAW:
                await accept_draw(session, state, main_config, secret_config, payload.game_id, client_color.opposite(), skip_activity_check=False)
            else:
                await accept_takeback(session, state, client_color.opposite(), db_game)
