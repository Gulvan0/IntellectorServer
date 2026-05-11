import asyncio
from typing import Any
from challenge.methods.get import get_active_public_challenges, get_direct_challenges
from common.user_ref import UserReference
from game.methods.get import get_current_games, get_latest_time_update
from game.models.main import Game
from game.models.rest.common import GameFilter
from net.ws_wrapper import WebSocketWrapper
from net.incoming import WebSocketHandlerCollection
from net.sub_storage import SubscriberStorage, SubscriberTag
from net.utils.ws_error import WebSocketException
from player.methods import resolve_player_refs, resolve_player_ref, resolve_optional_player_ref
from pubsub.models.channel import (
    GameEventChannel,
    CurrentGameListEventChannel,
    IncomingChallengesEventChannel,
    OutgoingChallengesEventChannel,
    PublicChallengeListEventChannel,
    StartedPlayerGamesEventChannel,
    SubEligibleEventChannel,
    SubscriberListEventChannel,
)
from pubsub.models.other import SubUnsubPayload
from pubsub.models.state import ChallengeListStateRefresh, CurrentGameListStateRefresh, GameStateRefresh, StartedPlayerGamesStateRefresh, SubscriberListChannelStateRefresh
from pubsub.outgoing_event.base import RefreshEvent
from pubsub.outgoing_event.refresh import (
    CurrentGameListRefresh,
    GameRefresh,
    IncomingChallengesRefresh,
    OutgoingChallengesRefresh,
    PublicChallengeListRefresh,
    StartedPlayerGamesRefresh,
    SubscriberListRefresh,
)
from pubsub.outgoing_event.update import NewSubscriber, SubscriberLeft
from utils.async_orm_session import AsyncSession


async def get_public_challenge_list_refresh(session: AsyncSession, channel: PublicChallengeListEventChannel) -> PublicChallengeListRefresh:
    public_challenges = await get_active_public_challenges(session)
    return PublicChallengeListRefresh(
        payload=ChallengeListStateRefresh(challenges=public_challenges),
        target_channel=channel
    )


async def get_game_list_refresh(session: AsyncSession, channel: CurrentGameListEventChannel) -> CurrentGameListRefresh:
    games = await get_current_games(session)
    return CurrentGameListRefresh(
        payload=CurrentGameListStateRefresh(games=games),
        target_channel=channel
    )


async def get_incoming_challenges_refresh(session: AsyncSession, channel: IncomingChallengesEventChannel, client: UserReference | None) -> IncomingChallengesRefresh:
    if not client or client.reference != channel.user_ref:
        raise WebSocketException("Forbidden. Make sure you're authorized as a player whose incoming challenges you want to subscribe to")

    incoming_challenges = await get_direct_challenges(session, client, include_outgoing=False)
    return IncomingChallengesRefresh(
        payload=ChallengeListStateRefresh(challenges=incoming_challenges),
        target_channel=channel
    )


async def get_outgoing_challenges_refresh(session: AsyncSession, channel: OutgoingChallengesEventChannel, client: UserReference | None) -> OutgoingChallengesRefresh:
    if not client or client.reference != channel.user_ref:
        raise WebSocketException("Forbidden. Make sure you're authorized as a player whose outgoing challenges you want to subscribe to")

    outgoing_challenges = await get_direct_challenges(session, client, include_incoming=False)
    return OutgoingChallengesRefresh(
        payload=ChallengeListStateRefresh(challenges=outgoing_challenges),
        target_channel=channel
    )


async def get_game_refresh(session: AsyncSession, channel: GameEventChannel, client: UserReference | None, tags_storage: set[SubscriberTag]) -> GameRefresh:
    db_game = await session.get(Game, channel.game_id, options=Game.load_options(just_summary=False, include_time_control=False))
    if not db_game:
        raise WebSocketException(f"Game {channel.game_id} does not exist")

    is_spectator = False
    if client:
        if client.reference == db_game.white_player_ref:
            is_spectator = True
            tags_storage.add(SubscriberTag.WHITE_PLAYER)
        elif client.reference == db_game.black_player_ref:
            is_spectator = True
            tags_storage.add(SubscriberTag.BLACK_PLAYER)

    collected_refs = db_game.collect_refs(include_nested=True)
    resolved_refs = await resolve_player_refs(collected_refs, session)
    latest_time_update = await get_latest_time_update(session, channel.game_id)
    game_state = GameStateRefresh.construct_from_game(
        game=db_game,
        resolved_refs=resolved_refs,
        latest_time_update=latest_time_update,
        reason='SUB',
        include_spectator_messages=is_spectator
    )
    return GameRefresh(
        payload=game_state,
        target_channel=channel
    )


async def get_started_player_games_refresh(session: AsyncSession, channel: StartedPlayerGamesEventChannel) -> StartedPlayerGamesRefresh:
    games = await get_current_games(session, GameFilter(player_ref=channel.watched_ref))
    return StartedPlayerGamesRefresh(
        payload=StartedPlayerGamesStateRefresh(current_games=games),
        target_channel=channel
    )


async def get_subscriber_list_refresh(session: AsyncSession, channel: SubscriberListEventChannel, sub_storage: SubscriberStorage) -> SubscriberListRefresh:
    subscriber_refs = set()
    unauthenticated_subs_count = 0

    for subscriber in sub_storage.get_subscribers(channel.channel):
        subscriber_user_ref = subscriber.ws.get_user_ref()
        if subscriber_user_ref:
            subscriber_refs.add(subscriber_user_ref)
        else:
            unauthenticated_subs_count += 1

    resolved_refs = await resolve_player_refs(list(subscriber_refs)[:1000], session)

    return SubscriberListRefresh(
        payload=SubscriberListChannelStateRefresh(
            subscribers=resolved_refs.all_values(),
            unauthenticated_subs_count=unauthenticated_subs_count
        ),
        target_channel=channel
    )


async def get_refresh(
    session: AsyncSession,
    channel: SubEligibleEventChannel,
    client: UserReference | None,
    sub_storage: SubscriberStorage,
    tags_storage: set[SubscriberTag]
) -> RefreshEvent[Any, Any]:
    match channel:
        case PublicChallengeListEventChannel():
            return await get_public_challenge_list_refresh(session, channel)
        case CurrentGameListEventChannel():
            return await get_game_list_refresh(session, channel)
        case IncomingChallengesEventChannel():
            return await get_incoming_challenges_refresh(session, channel, client)
        case OutgoingChallengesEventChannel():
            return await get_outgoing_challenges_refresh(session, channel, client)
        case GameEventChannel():
            return await get_game_refresh(session, channel, client, tags_storage)
        case StartedPlayerGamesEventChannel():
            return await get_started_player_games_refresh(session, channel)
        case SubscriberListEventChannel():
            return await get_subscriber_list_refresh(session, channel, sub_storage)


collection = WebSocketHandlerCollection()


@collection.register(SubUnsubPayload)
async def sub(ws: WebSocketWrapper, client: UserReference | None, payload: SubUnsubPayload) -> None:
    sub_storage = ws.app.mutable_state.ws_subscribers

    if client and isinstance(payload.channel, IncomingChallengesEventChannel):
        timer = ws.app.mutable_state.user_challenge_cancelling_timers.get(client)
        if timer:
            timer.cancel()

    tags: set[SubscriberTag] = set()
    async with ws.app.get_db_session() as session:
        refresh_event = await get_refresh(session, payload.channel, client, sub_storage, tags)

    perform_actual_subscription = not sub_storage.has_ws_subscriber(ws, payload.channel)
    if perform_actual_subscription:
        sub_storage.subscribe(ws, payload.channel, tags)

    asyncio.create_task(ws.send_event(refresh_event))

    if perform_actual_subscription and not isinstance(payload.channel, SubscriberListEventChannel):
        subscriber_ref_with_nickname = await resolve_optional_player_ref(client, session)

        asyncio.create_task(sub_storage.broadcast(
            NewSubscriber(subscriber_ref_with_nickname, SubscriberListEventChannel(channel=payload.channel))
        ))


@collection.register(SubUnsubPayload)
async def unsub(ws: WebSocketWrapper, client: UserReference | None, payload: SubUnsubPayload) -> None:
    sub_storage = ws.app.mutable_state.ws_subscribers

    if not sub_storage.has_ws_subscriber(ws, payload.channel):
        raise WebSocketException(f"Failed to unsubscribe from channel {payload.channel.model_dump_json()}: you're not subscribed to it!")

    sub_storage.unsubscribe(ws, payload.channel)

    asyncio.create_task(ws.send_unsubscribed())

    if isinstance(payload.channel, OutgoingChallengesEventChannel):
        asyncio.create_task(ws.app.plan_challenge_cancellation_if_unwatched(client))

    if not isinstance(payload.channel, SubscriberListEventChannel):
        subscriber_ref_with_nickname = None
        if client:
            async with ws.app.get_db_session() as session:
                subscriber_ref_with_nickname = await resolve_player_ref(client, session)

        asyncio.create_task(sub_storage.broadcast(
            SubscriberLeft(subscriber_ref_with_nickname, SubscriberListEventChannel(channel=payload.channel))
        ))
