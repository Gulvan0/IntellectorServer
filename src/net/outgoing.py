from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any
from pydantic import BaseModel

from src.challenge.models import ChallengeListStateRefresh, ChallengePublic, SpecificUserChallengeListStateRefresh
from src.common.models import EmptyModel, Id
from src.game.models.chat import ChatMessageBroadcastedData
from src.game.models.main import GamePublic, GameStartedBroadcastedData, GameStateRefresh
from src.game.models.offer import OfferActionBroadcastedData
from src.game.models.other import GameListChannelsStateRefresh
from src.game.models.outcome import GameEndedBroadcastedData
from src.game.models.ply import PlyBroadcastedData
from src.game.models.rollback import RollbackBroadcastedData
from src.game.models.time_added import TimeAddedBroadcastedData
from src.player.models import StartedPlayerGamesStateRefresh
from src.pubsub.models import (
    EventChannel,
    EveryoneEventChannel,
    GameEventChannel,
    GameListEventChannel,
    IncomingChallengesEventChannel,
    OutgoingChallengesEventChannel,
    PublicChallengeListEventChannel,
    StartedPlayerGamesEventChannel,
)


@dataclass(frozen=True)
class WebsocketOutgoingEvent[T: BaseModel, C: EventChannel]:
    event_name: str
    payload_type: type[T]
    target_channel_class: type[C] | None
    title: str | None = None
    summary: str | None = None
    description: str | None = None


# TODO: New subscriber / subscriber left
class WebsocketOutgoingEventRegistry(WebsocketOutgoingEvent, Enum):
    SERVER_SHUTDOWN = (
        "server_shutdown",
        EmptyModel,
        EveryoneEventChannel,
        "Server Shutdown",
        "Broadcasted to `everyone` channel group whenever the server starts preparing for the shutdown"
    )

    REFRESH_STARTED_PLAYER_GAMES = (
        "refresh.player.started_games",
        StartedPlayerGamesStateRefresh,
        None,
        "Channel state refresh: `player.started_games`"
    )

    GAME_STARTED = (
        "game_started",
        GamePublic,
        StartedPlayerGamesEventChannel,
        "Game Started (for player's followers)",
        "Broadcasted to `player.started_games` channel group whenever a new game involving a respective player starts"
    )

    REFRESH_PUBLIC_CHALLENGE_LIST = (
        "refresh.public_challenge_list",
        ChallengeListStateRefresh,
        None,
        "Channel state refresh: `public_challenge_list`"
    )

    NEW_PUBLIC_CHALLENGE = (
        "new_public_challenge",
        ChallengePublic,
        PublicChallengeListEventChannel,
        "New Public Challenge",
        "Broadcasted to `public_challenge_list` channel group whenever a new public challenge is created"
    )

    PUBLIC_CHALLENGE_CANCELLED = (
        "public_challenge_cancelled",
        Id,
        PublicChallengeListEventChannel,
        "Public Challenge Cancelled",
        "Broadcasted to `public_challenge_list` channel group whenever a public challenge is cancelled"
    )

    PUBLIC_CHALLENGE_FULFILLED = (
        "public_challenge_fulfilled",
        Id,
        PublicChallengeListEventChannel,
        "Public Challenge Fulfilled",
        "Broadcasted to `public_challenge_list` channel group whenever a public challenge is fulfilled (i.e. accepted by someone)"
    )

    REFRESH_GAME_LIST = (
        "refresh.game_list",
        GameListChannelsStateRefresh,
        None,
        "Channel state refresh: `game_list`"
    )

    NEW_ACTIVE_GAME = (
        "new_active_game",
        GameStartedBroadcastedData,
        GameListEventChannel,
        "Game Started (for game lists watchers)",
        "Broadcasted to `game_list` channel group whenever a new game starts"
    )

    NEW_RECENT_GAME = (
        "new_recent_game",
        GameEndedBroadcastedData,
        GameListEventChannel,
        "Game Ended (for game lists watchers)",
        "Broadcasted to `game_list` channel group whenever a game ends"
    )

    REFRESH_INCOMING_CHALLENGES = (
        "refresh.incoming_challenges",
        SpecificUserChallengeListStateRefresh,
        None,
        "Channel state refresh: `incoming_challenges`"
    )

    INCOMING_CHALLENGE_RECEIVED = (
        "incoming_challenge_received",
        ChallengePublic,
        IncomingChallengesEventChannel,
        "Incoming Challenge Received",
        "Broadcasted to `incoming_challenges` channel group whenever a direct challenge arrives"
    )

    INCOMING_CHALLENGE_CANCELLED = (
        "incoming_challenge_cancelled",
        Id,
        IncomingChallengesEventChannel,
        "Incoming Challenge Cancelled",
        "Broadcasted to `incoming_challenges` channel group whenever an incoming direct challenge is cancelled"
    )

    REFRESH_OUTGOING_CHALLENGES = (
        "refresh.outgoing_challenges",
        SpecificUserChallengeListStateRefresh,
        None,
        "Channel state refresh: `outgoing_challenges`"
    )

    OUTGOING_CHALLENGE_ACCEPTED = (
        "outgoing_challenge_accepted",
        Id,
        OutgoingChallengesEventChannel,
        "Outgoing Challenge Accepted",
        "Broadcasted to `outgoing_challenges` channel group whenever an outgoing (direct or open) challenge is accepted"
    )

    OUTGOING_CHALLENGE_REJECTED = (
        "outgoing_challenge_rejected",
        Id,
        OutgoingChallengesEventChannel,
        "Outgoing Challenge Rejected",
        "Broadcasted to `outgoing_challenges` channel group whenever an outgoing direct challenge is rejected"
    )

    OUTGOING_CHALLENGE_CANCELLED_BY_SERVER = (
        "outgoing_challenge_cancelled_by_server",
        Id,
        OutgoingChallengesEventChannel,
        "Outgoing Challenge Cancelled by Server",
        "Broadcasted to `outgoing_challenges` channel group whenever the server cancels an outgoing challenge due to shutdown"
    )

    REFRESH_GAME = (
        "refresh.game",
        GameStateRefresh,
        None,
        "Channel state refresh: `game`"
    )

    NEW_PLY = (
        "new_ply",
        PlyBroadcastedData,
        GameEventChannel,
        "New Ply",
        "Broadcasted to `game` channel group whenever a new move happens on the board"
    )

    NEW_CHAT_MESSAGE = (
        "new_chat_message",
        ChatMessageBroadcastedData,
        GameEventChannel,
        "New Chat Message",
        "Broadcasted to `game` channel group whenever a new chat message arrives"
    )

    OFFER_ACTION_PERFORMED = (
        "offer_action_performed",
        OfferActionBroadcastedData,
        GameEventChannel,
        "Offer Action Performed",
        "Broadcasted to `game` channel group whenever a draw or takeback offer is created, cancelled, accepted or rejected"
    )

    TIME_ADDED = (
        "time_added",
        TimeAddedBroadcastedData,
        GameEventChannel,
        "Time Added",
        "Broadcasted to `game` channel group whenever a player decides to add time to the opponent's reserves"
    )

    ROLLBACK = (
        "rollback",
        RollbackBroadcastedData,
        GameEventChannel,
        "Rollback",
        "Broadcasted to `game` channel group whenever some of the last moves get cancelled"
    )

    GAME_ENDED = (
        "game_ended",
        GameEndedBroadcastedData,
        GameEventChannel,
        "Game Ended (for specific game watchers)",
        "Broadcasted to `game` channel group when the game ends"
    )

    @classmethod
    def generate_asyncapi_specification(cls) -> dict[str, Any]:
        result: dict[str, dict] = dict(
            channels={},
            operations={},
            components=dict(
                messages={}
            )
        )
        for outgoing_event in cls:
            if outgoing_event.target_channel_class:
                channel_class: type[EventChannel] = outgoing_event.target_channel_class
                channel_group = channel_class.group
            else:
                channel_group = "NO_CHANNEL"

            msg_ref = {"$ref": f"#/components/messages/{outgoing_event.event_name}"}
            if channel_group not in result["channels"]:
                result["channels"][channel_group] = dict(address=channel_group, messages={})
                result["operations"][channel_group] = dict(action="send", messages=[], channel={
                    "$ref": f"#/channels/{channel_group}"
                })
            result["channels"][channel_group]["messages"][outgoing_event.event_name] = msg_ref
            result["operations"][channel_group]["messages"].append({
                "$ref": f"#/channels/{channel_group}/messages/{outgoing_event.event_name}"
            })

            payload_type: type[BaseModel] = outgoing_event.payload_type
            msg_definition = dict(
                name=outgoing_event.event_name,
                payload=payload_type.model_json_schema(ref_template=f'#/components/messages/{outgoing_event.event_name}/payload/$defs/{{model}}')
            )
            if outgoing_event.title:
                msg_definition["title"] = outgoing_event.title
            if outgoing_event.summary:
                msg_definition["summary"] = outgoing_event.summary
            if outgoing_event.description:
                msg_definition["description"] = outgoing_event.description
            result["components"]["messages"][outgoing_event.event_name] = msg_definition
        return result
