from typing import Annotated, ClassVar, Literal, Union
from pydantic import Field

from src.utils.custom_model import CustomFrozenModel


class EveryoneEventChannel(CustomFrozenModel, frozen=True):
    group: ClassVar[str] = 'everyone'
    channel_group: Literal['everyone'] = 'everyone'


class PublicChallengeListEventChannel(CustomFrozenModel, frozen=True):
    group: ClassVar[str] = 'public_challenge_list'
    channel_group: Literal['public_challenge_list'] = 'public_challenge_list'


class GameListEventChannel(CustomFrozenModel, frozen=True):
    group: ClassVar[str] = 'game_list'
    channel_group: Literal['game_list'] = 'game_list'


class IncomingChallengesEventChannel(CustomFrozenModel, frozen=True):
    group: ClassVar[str] = 'incoming_challenges'
    channel_group: Literal['incoming_challenges'] = 'incoming_challenges'

    user_ref: str


class OutgoingChallengesEventChannel(CustomFrozenModel, frozen=True):
    group: ClassVar[str] = 'outgoing_challenges'
    channel_group: Literal['outgoing_challenges'] = 'outgoing_challenges'

    user_ref: str


class GameEventChannel(CustomFrozenModel, frozen=True):
    group: ClassVar[str] = 'game.main'
    channel_group: Literal['game.main'] = 'game.main'

    game_id: int


class StartedPlayerGamesEventChannel(CustomFrozenModel, frozen=True):
    group: ClassVar[str] = 'player.started_games'
    channel_group: Literal['player.started_games'] = 'player.started_games'

    watched_ref: str


class SubscriberListEventChannel(CustomFrozenModel, frozen=True):
    group: ClassVar[str] = 'subscriber_list'
    channel_group: Literal['subscriber_list'] = 'subscriber_list'

    channel: Union[
        EveryoneEventChannel,
        PublicChallengeListEventChannel,
        GameListEventChannel,
        IncomingChallengesEventChannel,
        OutgoingChallengesEventChannel,
        GameEventChannel,
        StartedPlayerGamesEventChannel,
    ]


type SubEligibleEventChannel = Union[
    PublicChallengeListEventChannel,
    GameListEventChannel,
    IncomingChallengesEventChannel,
    OutgoingChallengesEventChannel,
    GameEventChannel,
    StartedPlayerGamesEventChannel,
    SubscriberListEventChannel,
]


type EventChannel = Union[
    SubEligibleEventChannel,
    EveryoneEventChannel,
]


DISCRIMINATED_EVENT_CHANNEL_FIELD_ANNOTATION = Annotated[EventChannel, Field(discriminator="channel_group")]
