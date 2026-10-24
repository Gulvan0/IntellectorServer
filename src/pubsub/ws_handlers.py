import asyncio
from typing import Any, TypeIs
from challenge.methods.get import count_active_public_challenges, get_active_public_challenges, get_direct_challenges
from common.user_ref import UserReference
from config.models import MainConfig
from game.methods.get import get_all_current_games, get_latest_time_update, get_recent_games
from game.methods.ongoing import get_player_ongoing_games
from game.models.main import Game
from game.models.rest.common import GameFilter
from net.ws_wrapper import WebSocketWrapper
from net.incoming import WebSocketHandlerCollection
from net.sub_storage import SubscriberStorage, SubscriberTag
from net.utils.ws_error import ErrorKind, WebSocketException
from player.methods import resolve_player_refs, resolve_player_ref, resolve_optional_player_ref
from player.models import PlayerStatusState
from player.status import track_player_statuses
from pubsub.models.channel import (
    EventChannel,
    EveryoneEventChannel,
    GameEventChannel,
    CurrentGameListEventChannel,
    IncomingChallengesEventChannel,
    OutgoingChallengesEventChannel,
    PublicChallengeListEventChannel,
    PlayerOngoingGamesEventChannel,
    PlayerStatusEventChannel,
    RecentGameListEventChannel,
    SubEligibleEventChannel,
    SubscriberListEventChannel,
    SubscriberListedEventChannel,
)
from pubsub.models.other import SessionPayload, SubUnsubManyPayload, SubUnsubPayload
from pubsub.models.state import (
    ChallengeListStateRefresh,
    CurrentGameListStateRefresh,
    GameStateRefresh,
    PlayerOngoingGamesStateRefresh,
    PublicChallengeListStateRefresh,
    RecentGameListStateRefresh,
    SubscriberListChannelStateRefresh,
)
from pubsub.outgoing_event.base import RefreshEvent
from pubsub.outgoing_event.refresh import (
    CurrentGameListRefresh,
    GameRefresh,
    IncomingChallengesRefresh,
    OutgoingChallengesRefresh,
    PublicChallengeListRefresh,
    PlayerOngoingGamesRefresh,
    PlayerStatusRefresh,
    RecentGameListRefresh,
    SubscriberListRefresh,
)
from pubsub.outgoing_event.update import NewSubscriber, SubscriberLeft
from utils.async_orm_session import AsyncSession


RECENT_GAME_LIST_SIZE = 12


async def get_public_challenge_list_refresh(session: AsyncSession, main_config: MainConfig, channel: PublicChallengeListEventChannel) -> PublicChallengeListRefresh:
    public_challenges = await get_active_public_challenges(session, main_config)
    total = await count_active_public_challenges(session)
    return PublicChallengeListRefresh(
        payload=PublicChallengeListStateRefresh(challenges=public_challenges, total=total, has_more=total > len(public_challenges)),
        target_channel=channel
    )


async def get_current_game_list_refresh(session: AsyncSession, channel: CurrentGameListEventChannel) -> CurrentGameListRefresh:
    return CurrentGameListRefresh(
        payload=CurrentGameListStateRefresh(games=await get_all_current_games(session)),
        target_channel=channel
    )


async def get_recent_game_list_refresh(session: AsyncSession, channel: RecentGameListEventChannel) -> RecentGameListRefresh:
    game_filter = GameFilter(time_control_kinds=list(channel.time_control_kinds) or None, rated=channel.rated)
    return RecentGameListRefresh(
        payload=RecentGameListStateRefresh(games=await get_recent_games(session, game_filter, RECENT_GAME_LIST_SIZE)),
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
    main_config: MainConfig,
    channel: SubEligibleEventChannel,
    client: UserReference | None,
    sub_storage: SubscriberStorage,
    tags_storage: set[SubscriberTag],
    status_states: dict[str, PlayerStatusState]
) -> RefreshEvent[Any, Any]:
    match channel:
        case PublicChallengeListEventChannel():
            return await get_public_challenge_list_refresh(session, main_config, channel)
        case CurrentGameListEventChannel():
            return await get_current_game_list_refresh(session, channel)
        case RecentGameListEventChannel():
            return await get_recent_game_list_refresh(session, channel)
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
    return not isinstance(channel, (SubscriberListEventChannel, PlayerStatusEventChannel, RecentGameListEventChannel))


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

    # registered before the refreshes are computed: a change landing meanwhile is then in the refresh, and the client drops the events that precede it
    newly_subscribed: dict[SubEligibleEventChannel, bool] = {}
    for channel in channels:
        if sub_storage.has_ws_subscriber(ws, channel):
            continue
        # whoever is already there through another connection was announced then
        newly_subscribed[channel] = not (client is not None and sub_storage.has_user_subscriber(state.token_to_user, client, channel))
        sub_storage.subscribe(ws, channel)

    # everything that needs the session stays inside the block: a session used after it's closed checks out a new connection that's never returned
    async with ws.app.get_db_session() as session:
        status_logins = [channel.watched_ref for channel in channels if isinstance(channel, PlayerStatusEventChannel)]
        status_states = await track_player_statuses(session, state, status_logins)

        for channel in channels:
            tags: set[SubscriberTag] = set()
            try:
                refresh_events.append(await get_refresh(session, ws.app.main_config, channel, client, sub_storage, tags, status_states))
            except WebSocketException as e:
                if channel in newly_subscribed:
                    sub_storage.unsubscribe(ws, channel)
                await ws.send_error(e.kind, e.message, channel)
                continue

            if channel in newly_subscribed:
                sub_storage.set_tags(ws, channel, tags)
                if newly_subscribed[channel] and announces_subscribers(channel):
                    announced_channels.append(channel)

        state.concurrent_tasks.plan(ws.send_events(refresh_events))

        if announced_channels:
            subscriber_ref_with_nickname = await resolve_optional_player_ref(client, session)
            for announced_channel in announced_channels:
                state.concurrent_tasks.plan(sub_storage.broadcast(
                    NewSubscriber(subscriber_ref_with_nickname, SubscriberListEventChannel(channel=announced_channel))
                ))


async def unsubscribe(ws: WebSocketWrapper, client: UserReference | None, channels: list[SubEligibleEventChannel], *, confirm: bool = True) -> None:
    """Skips the channels `ws` isn't subscribed to"""
    state = ws.app.mutable_state

    left_channels = [channel for channel in channels if state.ws_subscribers.has_ws_subscriber(ws, channel)]
    for channel in left_channels:
        state.ws_subscribers.unsubscribe(ws, channel)

    if confirm:
        state.concurrent_tasks.plan(ws.send_unsubscribed())

    if any(isinstance(channel, OutgoingChallengesEventChannel) for channel in left_channels):
        state.concurrent_tasks.plan(ws.app.plan_challenge_cancellation_if_unwatched(client))

    for channel in left_channels:
        await broadcast_subscriber_left(ws, client, channel)


collection = WebSocketHandlerCollection()


@collection.register(SessionPayload)
async def session(ws: WebSocketWrapper, client: UserReference | None, payload: SessionPayload) -> None:
    """Sets who the socket acts as and makes its subscriptions exactly `payload.channels`. An invalid token leaves the socket anonymous and unsubscribed"""
    state = ws.app.mutable_state

    new_client = state.token_to_user.get(payload.token) if payload.token else None
    token_is_invalid = bool(payload.token) and new_client is None
    requested_channels = [] if token_is_invalid else payload.channels

    current_channels = [
        channel for channel in state.ws_subscribers.get_subscriptions(ws)
        if not isinstance(channel, EveryoneEventChannel)
    ]

    if new_client == client:
        channels_to_leave = [channel for channel in current_channels if channel not in requested_channels]
        channels_to_join = [channel for channel in requested_channels if channel not in current_channels]
    else:
        # the subscriber lists must see the old identity leave and the new one join
        channels_to_leave = current_channels
        channels_to_join = requested_channels

    if channels_to_leave:
        await unsubscribe(ws, client, channels_to_leave, confirm=False)

    ws.saved_token = payload.token if new_client else None

    if channels_to_join:
        await subscribe(ws, new_client, channels_to_join)

    if token_is_invalid:
        raise WebSocketException("Invalid token", ErrorKind.AUTH_ERROR)


@collection.register(SubUnsubPayload)
async def sub(ws: WebSocketWrapper, client: UserReference | None, payload: SubUnsubPayload) -> None:
    await subscribe(ws, client, [payload.channel])


@collection.register(SubUnsubManyPayload)
async def sub_many(ws: WebSocketWrapper, client: UserReference | None, payload: SubUnsubManyPayload) -> None:
    await subscribe(ws, client, payload.channels)


@collection.register(SubUnsubPayload)
async def unsub(ws: WebSocketWrapper, client: UserReference | None, payload: SubUnsubPayload) -> None:
    if not ws.app.mutable_state.ws_subscribers.has_ws_subscriber(ws, payload.channel):
        raise WebSocketException(f"Failed to unsubscribe from channel {payload.channel.model_dump_json()}: you're not subscribed to it!", channel=payload.channel)

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
