from dataclasses import dataclass
from typing import Literal, Union

from pydantic import BaseModel, Field


class EveryoneEventChannel(BaseModel, frozen=True):
    channel_group: Literal['everyone'] = 'everyone'


class OpenChallengesEventChannel(BaseModel, frozen=True):
    channel_group: Literal['open_challenges'] = 'open_challenges'


class ActiveGamesEventChannel(BaseModel, frozen=True):
    channel_group: Literal['active_games'] = 'active_games'


class DirectChallengesEventChannel(BaseModel, frozen=True):
    channel_group: Literal['direct_challenges'] = 'direct_challenges'
    user_ref: str


class GamePublicEventChannel(BaseModel, frozen=True):
    channel_group: Literal['game/public'] = 'game/public'
    game_id: int


class GameSpectatorOnlyEventChannel(BaseModel, frozen=True):
    channel_group: Literal['game/spectator_only'] = 'game/spectator_only'
    game_id: int


class StartedPlayerGamesEventChannel(BaseModel, frozen=True):
    channel_group: Literal['player/started_games'] = 'player/started_games'
    watched_ref: str


class EventChannel(BaseModel, frozen=True):
    channel: Union[
        EveryoneEventChannel,
        OpenChallengesEventChannel,
        ActiveGamesEventChannel,
        DirectChallengesEventChannel,
        GamePublicEventChannel,
        GameSpectatorOnlyEventChannel,
        StartedPlayerGamesEventChannel,
    ] = Field(discriminator="channel_group")


EVERYONE = EventChannel(channel=EveryoneEventChannel())
