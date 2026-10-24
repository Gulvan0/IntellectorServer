from typing import Annotated, ClassVar, Literal, Union
from pydantic import Field, field_validator

from common.time_control import TimeControlKind
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


class RecentGameListEventChannel(CustomFrozenModel, frozen=True):
    """The latest finished games matching the filter. Equal filters are the same channel: the kinds are deduplicated and sorted"""
    group: ClassVar[str] = 'recent_game_list'
    channel_group: Literal['recent_game_list'] = 'recent_game_list'

    time_control_kinds: tuple[TimeControlKind, ...] = ()  # any of them; empty for any kind
    rated: bool | None = None

    @field_validator('time_control_kinds')
    @classmethod
    def normalize_time_control_kinds(cls, kinds: tuple[TimeControlKind, ...]) -> tuple[TimeControlKind, ...]:
        return tuple(sorted(set(kinds)))

    def matches(self, time_control_kind: TimeControlKind, rated: bool) -> bool:
        return (not self.time_control_kinds or time_control_kind in self.time_control_kinds) and (self.rated is None or self.rated == rated)


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


class PlayerOngoingGamesEventChannel(CustomFrozenModel, frozen=True):
    group: ClassVar[str] = 'player_ongoing_games'
    channel_group: Literal['player_ongoing_games'] = 'player_ongoing_games'

    watched_ref: str


class PlayerStatusEventChannel(CustomFrozenModel, frozen=True):
    group: ClassVar[str] = 'player_status'
    channel_group: Literal['player_status'] = 'player_status'

    watched_ref: str


SubscriberListedEventChannel = Union[
    EveryoneEventChannel,
    PublicChallengeListEventChannel,
    CurrentGameListEventChannel,
    IncomingChallengesEventChannel,
    OutgoingChallengesEventChannel,
    GameEventChannel,
    PlayerOngoingGamesEventChannel,
]


class SubscriberListEventChannel(CustomFrozenModel, frozen=True):
    group: ClassVar[str] = 'subscriber_list'
    channel_group: Literal['subscriber_list'] = 'subscriber_list'

    channel: SubscriberListedEventChannel


type SubEligibleEventChannel = Union[
    PublicChallengeListEventChannel,
    CurrentGameListEventChannel,
    RecentGameListEventChannel,
    IncomingChallengesEventChannel,
    OutgoingChallengesEventChannel,
    GameEventChannel,
    PlayerOngoingGamesEventChannel,
    PlayerStatusEventChannel,
    SubscriberListEventChannel,
]


type EventChannel = Union[
    SubEligibleEventChannel,
    EveryoneEventChannel,
]


DISCRIMINATED_EVENT_CHANNEL_FIELD_ANNOTATION = Annotated[EventChannel, Field(discriminator="channel_group")]
