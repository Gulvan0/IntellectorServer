from typing import ClassVar, Literal, Union

from pydantic import BaseModel, Field, create_model


class EventChannelBase(BaseModel, frozen=True):
    group: ClassVar[str] = ""


def _create_event_channel_model(name: str, group: str, fields: dict = {}) -> type[EventChannelBase]:
    return create_model(
        name,
        channel_group=(Literal[group], group),
        group=(ClassVar[str], group),
        __base__=EventChannelBase,
        **fields
    )


EveryoneEventChannel = _create_event_channel_model(
    'EveryoneEventChannel',
    group='everyone'
)


PublicChallengeListEventChannel = _create_event_channel_model(
    'PublicChallengeListEventChannel',
    group='public_challenge_list'
)


GameListEventChannel = _create_event_channel_model(
    'GameListEventChannel',
    group='game_list'
)


IncomingChallengesEventChannel = _create_event_channel_model(
    'IncomingChallengesEventChannel',
    group='incoming_challenges',
    fields=dict(
        user_ref=str
    )
)


OutgoingChallengesEventChannel = _create_event_channel_model(
    'OutgoingChallengesEventChannel',
    group='outgoing_challenges',
    fields=dict(
        user_ref=str
    )
)


GamePublicEventChannel = _create_event_channel_model(
    'GamePublicEventChannel',
    group='game.public',
    fields=dict(
        game_id=int
    )
)


GameSpectatorOnlyEventChannel = _create_event_channel_model(
    'GameSpectatorOnlyEventChannel',
    group='game.spectator_only',
    fields=dict(
        game_id=int
    )
)


StartedPlayerGamesEventChannel = _create_event_channel_model(
    'StartedPlayerGamesEventChannel',
    group='player.started_games',
    fields=dict(
        watched_ref=str
    )
)


channel_type = Union[
    EveryoneEventChannel,
    PublicChallengeListEventChannel,
    GameListEventChannel,
    IncomingChallengesEventChannel,
    OutgoingChallengesEventChannel,
    GamePublicEventChannel,
    GameSpectatorOnlyEventChannel,
    StartedPlayerGamesEventChannel,
]


class EventChannel(BaseModel, frozen=True):
    channel: channel_type = Field(discriminator="channel_group")  # noqa


EVERYONE = EventChannel(channel=EveryoneEventChannel())
