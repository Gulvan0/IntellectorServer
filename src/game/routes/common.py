from datetime import UTC, datetime
from fastapi import APIRouter, HTTPException, Query

from board.piece import PieceColor
from common.dependencies import MainConfigDependency, MandatoryUserDependency, MutableStateDependency, SecretConfigDependency, SessionDependency
from game.dependencies import CLIENT_IS_UPLOADER_IF_EXTERNAL_DEPENDENCY, GAME_IS_ONGOING_DEPENDENCY, GameDependency, OptionalPlayerColorDependency
from game.methods.cast import to_public_game
from game.methods.event import append_event
from game.methods.get import get_current_games, get_latest_time_update, get_recent_games
from game.methods.timeout import check_timeout, plan_timeout_check
from game.models.chat import GameChatMessageEvent, GameSendChatMessagePayload
from game.models.main import Game, GamePublic
from game.models.rest.common import GameFilter
from game.models.time_added import GameAddTimePayload, GameTimeAddedEvent
from game.models.time_update import GameTimeUpdate, GameTimeUpdateReason
from net.base_router import LoggingRoute
from net.sub_storage import SubscriberTag
from pubsub.models.channel import GameEventChannel
from pubsub.outgoing_event.update import NewChatMessage


router = APIRouter(prefix="/game", route_class=LoggingRoute)


@router.get("/current", response_model=list[GamePublic])
async def get_current_games_route(
    *,
    session: SessionDependency,
    offset: int = 0,
    limit: int = Query(default=10, le=50),
    game_filter: GameFilter = GameFilter()
) -> list[GamePublic]:
    return [
        await to_public_game(session, game)
        for game in await get_current_games(session, game_filter, offset, limit)
    ]


@router.get("/recent", response_model=list[GamePublic])
async def get_recent_games_route(
    *,
    session: SessionDependency,
    offset: int = 0,
    limit: int = Query(default=10, le=50),
    game_filter: GameFilter = GameFilter()
) -> list[GamePublic]:
    return [
        await to_public_game(session, game)
        for game in await get_recent_games(session, game_filter, offset, limit)
    ]


@router.get("/{game_id}", response_model=GamePublic)
async def get_game(
    *,
    session: SessionDependency,
    game_id: int
) -> GamePublic:
    db_game = await session.get(Game, game_id)

    if not db_game:
        raise HTTPException(status_code=404, detail="Game not found")

    return await to_public_game(session, db_game)


@router.get("/{game_id}/check_timeout")
async def check_timeout_route(
    *,
    session: SessionDependency,
    state: MutableStateDependency,
    main_config: MainConfigDependency,
    secret_config: SecretConfigDependency,
    game_id: int
) -> None:
    await check_timeout(session, state, main_config, secret_config, game_id)


@router.post("/chat/send_message")
async def send_chat_message(
    *,
    session: SessionDependency,
    state: MutableStateDependency,
    db_game: GameDependency,
    client: MandatoryUserDependency,
    payload: GameSendChatMessagePayload
) -> None:
    is_spectator = db_game.outcome or client.reference not in (db_game.white_player_ref, db_game.black_player_ref)

    db_event = GameChatMessageEvent(
        author_ref=client.reference,
        text=payload.text[:255],
        game_id=payload.game_id,
        spectator=is_spectator
    )
    session.add(db_event)
    await session.commit()

    event = NewChatMessage(await db_event.to_broadcasted_data(session), GameEventChannel(game_id=payload.game_id))
    tag_blacklist = set()
    if not db_game.outcome and is_spectator:
        tag_blacklist = {SubscriberTag.WHITE_PLAYER, SubscriberTag.BLACK_PLAYER}
    await state.ws_subscribers.broadcast(event, tag_blacklist)


@router.post("/add_time", dependencies=[
    GAME_IS_ONGOING_DEPENDENCY,
    CLIENT_IS_UPLOADER_IF_EXTERNAL_DEPENDENCY,
])
async def add_time(
    *,
    payload: GameAddTimePayload,
    session: SessionDependency,
    state: MutableStateDependency,
    main_config: MainConfigDependency,
    db_game: GameDependency,
    player_color: OptionalPlayerColorDependency,
) -> None:
    receiver = payload.receiver
    if db_game.external_uploader_ref:
        if not payload.receiver:
            raise HTTPException(422, "Specifying receiver is mandatory for an external game")
    else:
        if not player_color:
            raise HTTPException(403, "To add time in an internal game, you must be a player in it")
        if payload.receiver == player_color:
            raise HTTPException(422, "In an internal game, it is only allowed to add time to your opponent, not to yourself")
        if not payload.receiver:
            receiver = player_color.opposite()
    assert receiver

    latest_time_update = await get_latest_time_update(session, payload.game_id)

    if not latest_time_update:
        raise HTTPException(422, f"Game {payload.game_id} is a correspondence game")

    addition_dt = datetime.now(UTC)

    secs_added = main_config.rules.secs_added_manually
    ms_added = secs_added * 1000

    appended_time_update = GameTimeUpdate(
        updated_at=addition_dt,
        white_ms=latest_time_update.white_ms,
        black_ms=latest_time_update.black_ms,
        ticking_side=latest_time_update.ticking_side,
        reason=GameTimeUpdateReason.TIME_ADDED
    )
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
    await append_event(session, state, event, payload.game_id)

    await plan_timeout_check(
        triggering_time_update=appended_time_update,
        game_id=payload.game_id,
        is_external=db_game.external_uploader_ref is not None
    )
