from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any
from pydantic import BaseModel
from models import (
    GamePublic,
    ChallengePublic,
    Id,
    GameStartedBroadcastedData,
    GameEndedBroadcastedData,
    StartedPlayerGamesEventChannel,
    PublicChallengeListEventChannel,
    GameListEventChannel,
    IncomingChallengesEventChannel,
    OutgoingChallengesEventChannel,
    EventChannel,
)
from models.channel import EveryoneEventChannel, GamePublicEventChannel, GameSpectatorOnlyEventChannel
from models.game import ChatMessageBroadcastedData, InvalidPlyResponseData, PlyBroadcastedData
from models.other import EmptyModel


@dataclass(frozen=True)
class WebsocketOutgoingEvent[T: BaseModel, C: EventChannel]:
    event_name: str
    payload_type: type[T]
    target_channel_class: type[C] | None
    title: str | None = None
    summary: str | None = None
    description: str | None = None


class WebsocketOutgoingEventRegistry(WebsocketOutgoingEvent, Enum):
    GAME_STARTED = (
        "game_started",
        GamePublic,
        StartedPlayerGamesEventChannel,
        "Game Started (for player's followers)",
        "Broadcasted to `player.started_games` channel group whenever a new game involving a respective player starts"
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

    SERVER_SHUTDOWN = (
        "server_shutdown",
        EmptyModel,
        EveryoneEventChannel,
        "Server Shutdown",
        "Broadcasted to `everyone` channel group whenever the server starts preparing for the shutdown"
    )

    NEW_MOVE = (
        "new_move",
        PlyBroadcastedData,
        GamePublicEventChannel,
        "TODO",
        "TODO"
    )

    INVALID_MOVE = (
        "invalid_move",
        InvalidPlyResponseData,
        GamePublicEventChannel,
        "TODO",
        "TODO"
    )

    NEW_PLAYER_CHAT_MESSAGE = (
        "new_player_chat_message",
        ChatMessageBroadcastedData,
        GamePublicEventChannel,
        "TODO",
        "TODO"
    )

    NEW_SPECTATOR_CHAT_MESSAGE = (
        "new_player_chat_message",
        ChatMessageBroadcastedData,
        GameSpectatorOnlyEventChannel,
        "TODO",
        "TODO"
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
