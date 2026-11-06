from datetime import datetime, UTC
from typing import Optional

from sqlalchemy import CHAR, LargeBinary
from sqlmodel import Field, Relationship, SQLModel, Column

from rules import PieceColor, PieceKind, PlyKind
from utils.datatypes import ChallengeAcceptorColor, ChallengeKind, OfferAction, OfferKind, OutcomeKind, StudyPublicity, TimeControlKind, UserRestrictionKind, UserRole

PLAYER_REF_COLUMN = Field(max_length=32)
SIP_COLUMN = Field(max_length=127)


# =============================== GAME =================================


class Game(SQLModel, table=True):
    id: int = Field(primary_key=True)
    started_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    white_player_ref: str = PLAYER_REF_COLUMN
    black_player_ref: str = PLAYER_REF_COLUMN
    time_control_kind: TimeControlKind
    rated: bool
    custom_starting_sip: str | None = SIP_COLUMN

    fischer_time_control: Optional["GameFischerTimeControl"] = Relationship(back_populates="game", cascade_delete=True)
    outcome: Optional["GameOutcome"] = Relationship(back_populates="game", cascade_delete=True)
    ply_events: list["GamePlyEvent"] = Relationship(back_populates="game", cascade_delete=True)
    chat_message_events: list["GameChatMessageEvent"] = Relationship(back_populates="game", cascade_delete=True)
    offer_events: list["GameOfferEvent"] = Relationship(back_populates="game", cascade_delete=True)
    time_added_events: list["GameTimeAddedEvent"] = Relationship(back_populates="game", cascade_delete=True)
    rollback_events: list["GameRollbackEvent"] = Relationship(back_populates="game", cascade_delete=True)


class GameFischerTimeControl(SQLModel, table=True):
    game_id: int = Field(primary_key=True, foreign_key="game.id")
    start_seconds: int
    increment_seconds: int = 0

    game: Game = Relationship(back_populates="fischer_time_control")


class GameOutcome(SQLModel, table=True):
    game_id: int = Field(primary_key=True, foreign_key="game.id")
    game_ended_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    kind: OutcomeKind
    winner: PieceColor

    game: Game = Relationship(back_populates="outcome")


class GamePlyEvent(SQLModel, table=True):  # Analytics-optimized
    id: int = Field(primary_key=True)
    occurred_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    game_id: int = Field(foreign_key="game.id")
    ply_index: int
    is_cancelled: bool = False
    moving_color: PieceColor
    from_i: int
    from_j: int
    to_i: int
    to_j: int
    kind: PlyKind
    morph_into: PieceKind | None
    moved_piece: PieceKind
    target_piece: PieceKind | None
    sip_after: str | None = SIP_COLUMN

    game: Game = Relationship(back_populates="ply_events")


class GameChatMessageEvent(SQLModel, table=True):
    id: int = Field(primary_key=True)
    occurred_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    game_id: int = Field(foreign_key="game.id")
    author_ref: str = PLAYER_REF_COLUMN
    text: str
    spectator: bool

    game: Game = Relationship(back_populates="chat_message_events")


class GameOfferEvent(SQLModel, table=True):
    id: int = Field(primary_key=True)
    occurred_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    game_id: int = Field(foreign_key="game.id")
    action: OfferAction
    offer_kind: OfferKind
    offer_author: PieceColor

    game: Game = Relationship(back_populates="offer_events")


class GameTimeAddedEvent(SQLModel, table=True):
    id: int = Field(primary_key=True)
    occurred_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    game_id: int = Field(foreign_key="game.id")
    amount_seconds: int
    receiver: PieceColor

    game: Game = Relationship(back_populates="time_added_events")


class GameRollbackEvent(SQLModel, table=True):
    id: int = Field(primary_key=True)
    occurred_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    game_id: int = Field(foreign_key="game.id")
    position_index_before: int
    position_index_after: int
    requested_by: PieceColor

    game: Game = Relationship(back_populates="rollback_events")


# =============================== CHALLENGE =================================


class Challenge(SQLModel, table=True):
    id: int = Field(primary_key=True)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    caller_ref: str = PLAYER_REF_COLUMN
    callee_ref: str = PLAYER_REF_COLUMN
    kind: ChallengeKind
    time_control_kind: TimeControlKind
    acceptor_color: ChallengeAcceptorColor = ChallengeAcceptorColor.RANDOM
    custom_starting_sip: str | None = SIP_COLUMN
    rated: bool
    active: bool
    resulting_game_id: int

    fischer_time_control: Optional["ChallengeFischerTimeControl"] = Relationship(back_populates="challenge", cascade_delete=True)


class ChallengeFischerTimeControl(SQLModel, table=True):
    challenge_id: int = Field(primary_key=True, foreign_key="challenge.id")
    start_seconds: int
    increment_seconds: int = 0

    challenge: Challenge = Relationship(back_populates="fischer_time_control")


# =============================== PLAYER =================================


class Player(SQLModel, table=True):
    login: str = Field(primary_key=True, max_length=32)
    joined_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    nickname: str
    avatar: bytes | None = Field(sa_column=Column(LargeBinary), default=None)
    preferred_role: UserRole | None = None  # Don't trust that this role exists! It could have been revoked since then!

    password: "PlayerPassword" = Relationship(back_populates="player", cascade_delete=True)
    roles: list["PlayerRole"] = Relationship(back_populates="player", cascade_delete=True)
    restrictions: list["PlayerRestriction"] = Relationship(back_populates="player", cascade_delete=True)
    followed_players: list["PlayerFollowedPlayer"] = Relationship(back_populates="follower", cascade_delete=True)
    studies: list["Study"] = Relationship(back_populates="author", cascade_delete=True)


# <private>
class PlayerPassword(SQLModel, table=True):
    login: str = Field(primary_key=True, foreign_key="player.login")
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    salt: str = Field(sa_column=Column(CHAR(6)))
    password_hash: str = Field(sa_column=Column(CHAR(32)))

    player: Player = Relationship(back_populates="password")


class PlayerRole(SQLModel, table=True):
    login: str = Field(primary_key=True, foreign_key="player.login")
    role: UserRole = Field(primary_key=True)
    granted_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    player: Player = Relationship(back_populates="roles")


class PlayerRestriction(SQLModel, table=True):
    id: int = Field(primary_key=True)
    login: str = Field(foreign_key="player.login")
    casted_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    expires: datetime | None
    kind: UserRestrictionKind

    player: Player = Relationship(back_populates="restrictions")


class PlayerFollowedPlayer(SQLModel, table=True):
    follower_login: str = Field(primary_key=True, foreign_key="player.login")
    followed_login: str = Field(primary_key=True, foreign_key="player.login")
    follows_since: datetime = Field(default_factory=lambda: datetime.now(UTC))

    follower: Player = Relationship(back_populates="followed_players", sa_relationship_kwargs=dict(foreign_keys="PlayerFollow.follower_login"))


class PlayerEloProgress(SQLModel, table=True):  # Used for: current elo retrieval, elo history plotting, antifraud checks
    id: int = Field(primary_key=True)
    login: str = Field(foreign_key="player.login")
    ts: datetime = Field(default_factory=lambda: datetime.now(UTC))
    time_control_kind: TimeControlKind
    elo: int
    delta: int
    causing_game_id: int = Field(foreign_key="game.id")
    ranked_games_played: int


# =============================== STUDY =================================


class Study(SQLModel, table=True):
    id: int = Field(primary_key=True)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    modified_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    author_login: str = Field(foreign_key="player.login")
    name: str = Field(max_length=64)
    description: str = Field(max_length=2000)
    publicity: StudyPublicity
    starting_sip: str = SIP_COLUMN
    key_sip: str = SIP_COLUMN
    deleted: bool = False

    author: Player = Relationship(back_populates="studies")
    tags: list["StudyTag"] = Relationship(back_populates="study", cascade_delete=True)
    nodes: list["StudyVariationNode"] = Relationship(back_populates="study", cascade_delete=True)


class StudyTag(SQLModel, table=True):
    study_id: int = Field(primary_key=True)
    tag: str = Field(primary_key=True, max_length=16)

    study: Study = Relationship(back_populates="tags")


class StudyVariationNode(SQLModel, table=True):
    study_id: int = Field(primary_key=True)
    joined_path: str = Field(primary_key=True, max_length=500)
    ply_from_i: int
    ply_from_j: int
    ply_to_i: int
    ply_to_j: int
    ply_morph_into: PieceKind | None

    study: Study = Relationship(back_populates="nodes")


# =============================== LOG =================================


class ServerLaunch(SQLModel, table=True):
    id: int = Field(primary_key=True)
    launched_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


# <private>
class RESTLog(SQLModel, table=True):
    id: int = Field(primary_key=True)
    ts: datetime = Field(default_factory=lambda: datetime.now(UTC))
    client_host: str
    authorized_as: str | None = PLAYER_REF_COLUMN
    endpoint: str
    method: str = Field(sa_column=Column(CHAR(4)))
    headers_json: str
    payload_json: str
    response_code: int
    response_json: str


# <private>
class WSLog(SQLModel, table=True):
    id: int = Field(primary_key=True)
    ts: datetime = Field(default_factory=lambda: datetime.now(UTC))
    connection_id: str = Field(sa_column=Column(CHAR(32)))
    authorized_as: str | None = PLAYER_REF_COLUMN
    payload_json: str
    incoming: bool


# <private>
class ServiceLog(SQLModel, table=True):
    id: int = Field(primary_key=True)
    ts: datetime = Field(default_factory=lambda: datetime.now(UTC))
    service: str
    message: str


# =============================== OTHER =================================


class SavedQuery(SQLModel, table=True):
    id: int = Field(primary_key=True)
    author_login: str
    is_private: bool
    name: str = Field(max_length=64)
    text: str = Field(max_length=2000)