from datetime import UTC, datetime
from typing import Sequence
from fastapi import APIRouter, HTTPException, Query
from sqlmodel import Session, desc, select
from models.channel import GameEventChannel
from models.game import (
    ExternalGameAppendPlyPayload,
    ExternalGameAppendPlyResponse,
    ExternalGameCreatePayload,
    ExternalGameEndPayload,
    Game,
    GameFilter,
    GamePlyEvent,
    GamePublic,
    PlyBroadcastedData,
    SimpleOutcome,
)
from net.outgoing import WebsocketOutgoingEventRegistry
from routers.shared_methods.game import check_timeout, create_external_game, end_game
from routers.shared_queries.game import get_last_ply_event, has_occured_thrice, is_stale
from routers.utils import MandatoryUserDependency, MutableStateDependency, SecretConfigDependency, SessionDependency
from routers.websocket.game import get_current_sip_and_ply_cnt
from rules import DEFAULT_STARTING_SIP, HexCoordinates, Ply, Position, PositionFinalityGroup
from utils.datatypes import OutcomeKind, UserReference


router = APIRouter(prefix="/game")


@router.get("/{game_id}", response_model=GamePublic)
async def get_game(*, session: SessionDependency, state: MutableStateDependency, secret_config: SecretConfigDependency, game_id: int):
    await check_timeout(session=session, state=state, secret_config=secret_config, game_id=game_id)

    db_game = session.get(Game, game_id)

    if not db_game:
        raise HTTPException(status_code=404, detail="Game not found")

    return db_game


async def get_current_games(session: Session, game_filter: GameFilter, offset: int = 0, limit: int = 10) -> Sequence[Game]:
    return session.exec(select(
        Game
    ).where(
        Game.outcome == None,  # noqa
        *game_filter.construct_conditions()
    ).offset(offset).limit(limit)).all()


@router.get("/current", response_model=list[GamePublic])
async def get_current_games_route(*, session: SessionDependency, offset: int = 0, limit: int = Query(default=10, le=50), game_filter: GameFilter = GameFilter()):
    return get_current_games(session, game_filter, offset, limit)


async def get_recent_games(session: Session, game_filter: GameFilter, offset: int = 0, limit: int = 10) -> Sequence[Game]:
    return session.exec(select(
        Game
    ).where(
        Game.outcome != None,  # noqa
        *game_filter.construct_conditions()
    ).order_by(desc(Game.started_at)).offset(offset).limit(limit)).all()


@router.get("/recent", response_model=list[GamePublic])
async def get_recent_games_route(*, session: SessionDependency, offset: int = 0, limit: int = Query(default=10, le=50), game_filter: GameFilter = GameFilter()):
    return get_recent_games(session, game_filter, offset, limit)


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

    ply_event = GamePlyEvent(
        occurred_at=ply_dt,
        ply_index=new_ply_index,
        white_ms_after_execution=payload.white_ms_after_execution,
        black_ms_after_execution=payload.black_ms_after_execution,
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
    )
    session.add(ply_event)
    session.commit()

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

    await state.ws_subscribers.broadcast(
        WebsocketOutgoingEventRegistry.NEW_PLY,
        PlyBroadcastedData(
            occurred_at=ply_dt,
            white_ms_after_execution=payload.white_ms_after_execution,
            black_ms_after_execution=payload.black_ms_after_execution,
            from_i=ply.departure.i,
            from_j=ply.departure.j,
            to_i=ply.destination.i,
            to_j=ply.destination.j,
            morph_into=ply.morph_into,
            game_id=payload.game_id,
            sip_after=new_sip
        ),
        GameEventChannel(game_id=payload.game_id)
    )

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


# TODO: Bot game handlers (rollback, time added)
