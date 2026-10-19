import asyncio
from typing import Any, TypeIs
from challenge.methods.get import get_active_public_challenges, get_direct_challenges
from common.user_ref import UserReference
from game.methods.get import get_current_games, get_latest_time_update
from game.methods.ongoing import get_player_ongoing_games
from game.models.main import Game
from net.ws_wrapper import WebSocketWrapper
from net.incoming import WebSocketHandlerCollection
from net.sub_storage import SubscriberStorage, SubscriberTag
from net.utils.ws_error import WebSocketException
from player.methods import resolve_player_refs, resolve_player_ref, resolve_optional_player_ref
from player.models import PlayerStatusState
from player.status import track_player_statuses
from pubsub.models.channel import (
    EventChannel,
    GameEventChannel,
    CurrentGameListEventChannel,
    IncomingChallengesEventChannel,
    OutgoingChallengesEventChannel,
    PublicChallengeListEventChannel,
    PlayerOngoingGamesEventChannel,
    PlayerStatusEventChannel,
    SubEligibleEventChannel,
    SubscriberListEventChannel,
    SubscriberListedEventChannel,
)
from pubsub.models.other import SubUnsubManyPayload, SubUnsubPayload
from pubsub.models.state import ChallengeListStateRefresh, CurrentGameListStateRefresh, GameStateRefresh, PlayerOngoingGamesStateRefresh, SubscriberListChannelStateRefresh
from pubsub.outgoing_event.base import RefreshEvent
from pubsub.outgoing_event.refresh import (
    CurrentGameListRefresh,
    GameRefresh,
    IncomingChallengesRefresh,
    OutgoingChallengesRefresh,
    PublicChallengeListRefresh,
    PlayerOngoingGamesRefresh,
    PlayerStatusRefresh,
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

    is_player = False
    if client:
        if client.reference == db_game.white_player_ref:
            is_player = True
            tags_storage.add(SubscriberTag.WHITE_PLAYER)
        elif client.reference == db_game.black_player_ref:
            is_player = True
            tags_storage.add(SubscriberTag.BLACK_PLAYER)

    collected_refs = db_game.collect_refs(include_nested=True)
    resolved_refs = await resolve_player_refs(collected_refs, session)
    latest_time_update = await get_latest_time_update(session, channel.game_id)
    game_state = GameStateRefresh.construct_from_game(
        game=db_game,
        resolved_refs=resolved_refs,
        latest_time_update=latest_time_update,
        reason='SUB',
        include_spectator_messages=not is_player or db_game.outcome is not None  # players see them once the game is over
    )
    return GameRefresh(
        payload=game_state,
        target_channel=channel
    )


async def get_player_ongoing_games_refresh(session: AsyncSession, channel: PlayerOngoingGamesEventChannel) -> PlayerOngoingGamesRefresh:
    games = await get_player_ongoing_games(session, channel.watched_ref)
    return PlayerOngoingGamesRefresh(
        payload=PlayerOngoingGamesStateRefresh(current_games=games),
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
    tags_storage: set[SubscriberTag],
    status_states: dict[str, PlayerStatusState]
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
        case PlayerOngoingGamesEventChannel():
            return await get_player_ongoing_games_refresh(session, channel)
        case PlayerStatusEventChannel():
            return PlayerStatusRefresh(payload=status_states[channel.watched_ref], target_channel=channel)
        case SubscriberListEventChannel():
            return await get_subscriber_list_refresh(session, channel, sub_storage)


def announces_subscribers(channel: EventChannel) -> TypeIs[SubscriberListedEventChannel]:
    """Whether the channel's subscriber list hears of users joining and leaving it"""
    return not isinstance(channel, (SubscriberListEventChannel, PlayerStatusEventChannel))


async def subscribe(ws: WebSocketWrapper, client: UserReference | None, channels: list[SubEligibleEventChannel]) -> None:
    """A channel that can't be subscribed to gets an error, the rest are subscribed to regardless"""
    state = ws.app.mutable_state
    sub_storage = state.ws_subscribers

    if client and any(isinstance(channel, IncomingChallengesEventChannel) for channel in channels):
        timer = state.user_challenge_cancelling_timers.get(client)
        if timer:
            timer.cancel()

    refresh_events: list[RefreshEvent[Any, Any]] = []
    announced_channels: list[SubscriberListedEventChannel] = []
    # everything that needs the session stays inside the block: a session used after it's closed checks out a new connection that's never returned
    async with ws.app.get_db_session() as session:
        status_logins = [channel.watched_ref for channel in channels if isinstance(channel, PlayerStatusEventChannel)]
        status_states = await track_player_statuses(session, state, status_logins)

        for channel in channels:
            tags: set[SubscriberTag] = set()
            try:
                refresh_events.append(await get_refresh(session, channel, client, sub_storage, tags, status_states))
            except WebSocketException as e:
                await ws.send_error(e.kind, e.message)
                continue

            # whoever is already there through another connection was announced then
            already_present = client is not None and sub_storage.has_user_subscriber(state.token_to_user, client, channel)

            perform_actual_subscription = not sub_storage.has_ws_subscriber(ws, channel)
            if perform_actual_subscription:
                sub_storage.subscribe(ws, channel, tags)

            if perform_actual_subscription and not already_present and announces_subscribers(channel):
                announced_channels.append(channel)

        state.concurrent_tasks.plan(ws.send_events(refresh_events))

        if announced_channels:
            subscriber_ref_with_nickname = await resolve_optional_player_ref(client, session)
            for announced_channel in announced_channels:
                state.concurrent_tasks.plan(sub_storage.broadcast(
                    NewSubscriber(subscriber_ref_with_nickname, SubscriberListEventChannel(channel=announced_channel))
                ))


async def unsubscribe(ws: WebSocketWrapper, client: UserReference | None, channels: list[SubEligibleEventChannel]) -> None:
    """Skips the channels `ws` isn't subscribed to"""
    state = ws.app.mutable_state

    left_channels = [channel for channel in channels if state.ws_subscribers.has_ws_subscriber(ws, channel)]
    for channel in left_channels:
        state.ws_subscribers.unsubscribe(ws, channel)

    state.concurrent_tasks.plan(ws.send_unsubscribed())

    if any(isinstance(channel, OutgoingChallengesEventChannel) for channel in left_channels):
        state.concurrent_tasks.plan(ws.app.plan_challenge_cancellation_if_unwatched(client))

    for channel in left_channels:
        await broadcast_subscriber_left(ws, client, channel)


collection = WebSocketHandlerCollection()


@collection.register(SubUnsubPayload)
async def sub(ws: WebSocketWrapper, client: UserReference | None, payload: SubUnsubPayload) -> None:
    await subscribe(ws, client, [payload.channel])


@collection.register(SubUnsubManyPayload)
async def sub_many(ws: WebSocketWrapper, client: UserReference | None, payload: SubUnsubManyPayload) -> None:
    await subscribe(ws, client, payload.channels)


@collection.register(SubUnsubPayload)
async def unsub(ws: WebSocketWrapper, client: UserReference | None, payload: SubUnsubPayload) -> None:
    if not ws.app.mutable_state.ws_subscribers.has_ws_subscriber(ws, payload.channel):
        raise WebSocketException(f"Failed to unsubscribe from channel {payload.channel.model_dump_json()}: you're not subscribed to it!")

    await unsubscribe(ws, client, [payload.channel])


@collection.register(SubUnsubManyPayload)
async def unsub_many(ws: WebSocketWrapper, client: UserReference | None, payload: SubUnsubManyPayload) -> None:
    await unsubscribe(ws, client, payload.channels)


async def broadcast_subscriber_left(ws: WebSocketWrapper, client: UserReference | None, channel: EventChannel) -> None:
    """Tells the channel's subscriber list that `client` has left it, unless they're still there through another connection"""
    if not announces_subscribers(channel):
        return

    state = ws.app.mutable_state
    if client and state.ws_subscribers.has_user_subscriber(state.token_to_user, client, channel):
        return

    subscriber_ref_with_nickname = None
    if client:
        async with ws.app.get_db_session() as session:
            subscriber_ref_with_nickname = await resolve_player_ref(client, session)

    state.concurrent_tasks.plan(state.ws_subscribers.broadcast(
        SubscriberLeft(subscriber_ref_with_nickname, SubscriberListEventChannel(channel=channel))
    ))
