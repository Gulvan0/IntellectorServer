from typing import Annotated, ClassVar, Literal, Union

from pydantic import BaseModel, Field


class EveryoneEventChannel(BaseModel, frozen=True):
    group: ClassVar[str] = 'everyone'
    channel_group: Literal['everyone'] = 'everyone'


class PublicChallengeListEventChannel(BaseModel, frozen=True):
    group: ClassVar[str] = 'public_challenge_list'
    channel_group: Literal['public_challenge_list'] = 'public_challenge_list'


class GameListEventChannel(BaseModel, frozen=True):
    group: ClassVar[str] = 'game_list'
    channel_group: Literal['game_list'] = 'game_list'


class IncomingChallengesEventChannel(BaseModel, frozen=True):
    group: ClassVar[str] = 'incoming_challenges'
    channel_group: Literal['incoming_challenges'] = 'incoming_challenges'

    user_ref: str


class OutgoingChallengesEventChannel(BaseModel, frozen=True):
    group: ClassVar[str] = 'outgoing_challenges'
    channel_group: Literal['outgoing_challenges'] = 'outgoing_challenges'

    user_ref: str


class GamePublicEventChannel(BaseModel, frozen=True):
    group: ClassVar[str] = 'game.public'
    channel_group: Literal['game.public'] = 'game.public'

    game_id: int


class GameSpectatorOnlyEventChannel(BaseModel, frozen=True):
    group: ClassVar[str] = 'game.spectator_only'
    channel_group: Literal['game.spectator_only'] = 'game.spectator_only'

    game_id: int


class StartedPlayerGamesEventChannel(BaseModel, frozen=True):
    group: ClassVar[str] = 'player.started_games'
    channel_group: Literal['player.started_games'] = 'player.started_games'

    watched_ref: str


EventChannel = Union[
    EveryoneEventChannel,
    PublicChallengeListEventChannel,
    GameListEventChannel,
    IncomingChallengesEventChannel,
    OutgoingChallengesEventChannel,
    GamePublicEventChannel,
    GameSpectatorOnlyEventChannel,
    StartedPlayerGamesEventChannel,
]


DISCRIMINATED_EVENT_CHANNEL_FIELD_ANNOTATION = Annotated[EventChannel, Field(discriminator="channel_group")]
