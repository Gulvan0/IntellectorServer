from typing import Literal, Union

from pydantic import BaseModel, Field


class EveryoneEventChannel(BaseModel, frozen=True):
    channel_group: Literal['everyone'] = 'everyone'


class PublicChallengeListEventChannel(BaseModel, frozen=True):
    channel_group: Literal['public_challenge_list'] = 'public_challenge_list'


class GameListEventChannel(BaseModel, frozen=True):
    channel_group: Literal['game_list'] = 'game_list'


class IncomingChallengesEventChannel(BaseModel, frozen=True):
    channel_group: Literal['incoming_challenges'] = 'incoming_challenges'
    user_ref: str


class OutgoingChallengesEventChannel(BaseModel, frozen=True):
    channel_group: Literal['outgoing_challenges'] = 'outgoing_challenges'
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
        PublicChallengeListEventChannel,
        GameListEventChannel,
        IncomingChallengesEventChannel,
        OutgoingChallengesEventChannel,
        GamePublicEventChannel,
        GameSpectatorOnlyEventChannel,
        StartedPlayerGamesEventChannel,
    ] = Field(discriminator="channel_group")


EVERYONE = EventChannel(channel=EveryoneEventChannel())
