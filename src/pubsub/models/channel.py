from typing import Annotated, ClassVar, Literal, Union
from pydantic import Field

from utils.custom_model import CustomFrozenModel


class EveryoneEventChannel(CustomFrozenModel, frozen=True):
    group: ClassVar[str] = 'everyone'
    channel_group: Literal['everyone'] = 'everyone'


class PublicChallengeListEventChannel(CustomFrozenModel, frozen=True):
    group: ClassVar[str] = 'public_challenge_list'
    channel_group: Literal['public_challenge_list'] = 'public_challenge_list'


class CurrentGameListEventChannel(CustomFrozenModel, frozen=True):
    group: ClassVar[str] = 'current_game_list'
    channel_group: Literal['current_game_list'] = 'current_game_list'


class IncomingChallengesEventChannel(CustomFrozenModel, frozen=True):
    group: ClassVar[str] = 'incoming_challenges'
    channel_group: Literal['incoming_challenges'] = 'incoming_challenges'

    user_ref: str


class OutgoingChallengesEventChannel(CustomFrozenModel, frozen=True):
    group: ClassVar[str] = 'outgoing_challenges'
    channel_group: Literal['outgoing_challenges'] = 'outgoing_challenges'

    user_ref: str


class GameEventChannel(CustomFrozenModel, frozen=True):
    group: ClassVar[str] = 'game'
    channel_group: Literal['game'] = 'game'

    game_id: int


class StartedPlayerGamesEventChannel(CustomFrozenModel, frozen=True):
    group: ClassVar[str] = 'started_player_games'
    channel_group: Literal['started_player_games'] = 'started_player_games'

    watched_ref: str


class SubscriberListEventChannel(CustomFrozenModel, frozen=True):
    group: ClassVar[str] = 'subscriber_list'
    channel_group: Literal['subscriber_list'] = 'subscriber_list'

    channel: Union[
        EveryoneEventChannel,
        PublicChallengeListEventChannel,
        CurrentGameListEventChannel,
        IncomingChallengesEventChannel,
        OutgoingChallengesEventChannel,
        GameEventChannel,
        StartedPlayerGamesEventChannel,
    ]


type SubEligibleEventChannel = Union[
    PublicChallengeListEventChannel,
    CurrentGameListEventChannel,
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
