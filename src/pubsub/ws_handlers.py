from challenge.methods.cast import to_public_challenge
from challenge.methods.get import get_active_public_challenges, get_direct_challenges
from common.user_ref import UserReference
from game.methods.cast import compose_state_refresh, to_public_game
from game.methods.get import get_current_games
from game.models.main import Game
from game.models.rest import GameFilter
from net.core import WebSocketWrapper
from net.incoming import WebSocketHandlerCollection
from net.sub_storage import SubscriberTag
from net.utils.ws_error import WebSocketException
from player.methods import get_user_ref_with_nickname
from pubsub.models.channel import (
    GameEventChannel,
    GameListEventChannel,
    IncomingChallengesEventChannel,
    OutgoingChallengesEventChannel,
    PublicChallengeListEventChannel,
    StartedPlayerGamesEventChannel,
    SubscriberListEventChannel,
)
from pubsub.models.other import SubUnsubPayload
from pubsub.models.state import ChallengeListStateRefresh, GameListChannelsStateRefresh, SubscriberListChannelStateRefresh
from pubsub.outgoing_event.base import OutgoingEvent
from pubsub.outgoing_event.refresh import GameListRefresh, IncomingChallengesRefresh, OutgoingChallengesRefresh, PublicChallengeListRefresh, SubscriberListRefresh
from pubsub.outgoing_event.update import NewSubscriber, SubscriberLeft


collection = WebSocketHandlerCollection()


@collection.register(SubUnsubPayload)
async def sub(ws: WebSocketWrapper, client: UserReference | None, payload: SubUnsubPayload):
    sub_storage = ws.app.mutable_state.ws_subscribers
    tags = set()

    async with ws.app.get_db_session() as session:
        match payload.channel:
            case PublicChallengeListEventChannel():
                public_challenges = await get_active_public_challenges(session)
                refresh_event: OutgoingEvent = PublicChallengeListRefresh(ChallengeListStateRefresh(
                    challenges=public_challenges
                ))
            case GameListEventChannel():
                db_games = await get_current_games(session)
                games = [await to_public_game(session, db_game) for db_game in db_games]
                refresh_event = GameListRefresh(GameListChannelsStateRefresh(
                    games=games
                ))
            case IncomingChallengesEventChannel(user_ref=user_ref):
                if not client or client.reference != user_ref:
                    raise WebSocketException("Forbidden. Make sure you're authorized as a player whose incoming challenges you want to subscribe to")

                timer = ws.app.mutable_state.user_challenge_cancelling_timers.get(client)
                if timer:
                    timer.cancel()

                db_challenges = await get_direct_challenges(session, client, include_outgoing=False)
                incoming_challenges = [await to_public_challenge(session, db_challenge) for db_challenge in db_challenges]
                refresh_event = IncomingChallengesRefresh(ChallengeListStateRefresh(
                    challenges=incoming_challenges
                ))
            case OutgoingChallengesEventChannel(user_ref=user_ref):
                if not client or client.reference != user_ref:
                    raise WebSocketException("Forbidden. Make sure you're authorized as a player whose outgoing challenges you want to subscribe to")
                db_challenges = await get_direct_challenges(session, client, include_incoming=False)
                incoming_challenges = [await to_public_challenge(session, db_challenge) for db_challenge in db_challenges]
                refresh_event = OutgoingChallengesRefresh(ChallengeListStateRefresh(
                    challenges=incoming_challenges
                ))
            case GameEventChannel(game_id=game_id):
                db_game = await session.get(Game, game_id)
                if not db_game:
                    raise WebSocketException(f"Game {game_id} does not exist")

                is_spectator = not client or client.reference not in (db_game.white_player_ref, db_game.black_player_ref)

                if not is_spectator:
                    tags.add(SubscriberTag.PARTICIPATING_PLAYER)

                await compose_state_refresh(session, game_id, db_game, 'sub', include_spectator_messages=is_spectator)
            case StartedPlayerGamesEventChannel(watched_ref=watched_ref):
                db_games = await get_current_games(session, GameFilter(player_ref=watched_ref))
                games = [await to_public_game(session, db_game) for db_game in db_games]
                refresh_event = GameListRefresh(GameListChannelsStateRefresh(
                    games=games
                ))
            case SubscriberListEventChannel(channel=channel):
                subscribers = set()
                unauthenticated_subs_count = 0

                for subscriber in sub_storage.get_subscribers(channel):
                    subscriber_user_ref = subscriber.ws.get_user_ref()
                    if subscriber_user_ref:
                        subscribers.add(await get_user_ref_with_nickname(session, subscriber_user_ref))
                    else:
                        unauthenticated_subs_count += 1

                refresh_event = SubscriberListRefresh(SubscriberListChannelStateRefresh(
                    subscribers=list(subscribers),
                    unauthenticated_subs_count=unauthenticated_subs_count
                ))

        perform_actual_subscription = not sub_storage.has_ws_subscriber(ws, payload.channel)
        if perform_actual_subscription:
            sub_storage.subscribe(ws, payload.channel, tags)

        await ws.send_event(refresh_event)

        if perform_actual_subscription and not isinstance(payload.channel, SubscriberListEventChannel):
            subscriber_ref_with_nickname = None
            if client:
                subscriber_ref_with_nickname = await get_user_ref_with_nickname(session, client)

            await sub_storage.broadcast(
                NewSubscriber(subscriber_ref_with_nickname, SubscriberListEventChannel(channel=payload.channel))
            )


@collection.register(SubUnsubPayload)
async def unsub(ws: WebSocketWrapper, client: UserReference | None, payload: SubUnsubPayload):
    sub_storage = ws.app.mutable_state.ws_subscribers

    if not sub_storage.has_ws_subscriber(ws, payload.channel):
        raise WebSocketException(f"Failed to unsubscribe from channel {payload.channel.model_dump_json()}: you're not subscribed to it!")

    sub_storage.unsubscribe(ws, payload.channel)

    await ws.send_unsubscribed()

    if not isinstance(payload.channel, SubscriberListEventChannel):
        subscriber_ref_with_nickname = None
        if client:
            async with ws.app.get_db_session() as session:
                subscriber_ref_with_nickname = await get_user_ref_with_nickname(session, client)

        await sub_storage.broadcast(
            SubscriberLeft(subscriber_ref_with_nickname, SubscriberListEventChannel(channel=payload.channel))
        )
