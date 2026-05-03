from datetime import datetime
from typing import Literal

from sqlalchemy.orm import Load, joinedload, selectinload
from sqlmodel import Field, Relationship

from common.field_types import CurrentDatetime, OptionalSip, PlayerRef, OptionalPlayerRef, Sip
from common.models import UserRefWithNickname
from common.resolved_refs import ResolvedRefs
from common.time_control import TimeControlKind
from game.models.time_control import GameFischerTimeControl, GameFischerTimeControlPublic
from game.models.outcome import GameOutcome, GameOutcomePublic
from game.models.ply import GamePlyEvent, GamePlyEventPublic
from game.models.chat import GameChatMessageEvent, GameChatMessageEventPublic
from game.models.offer import GameOfferEvent, GameOfferEventPublic
from game.models.rollback import GameRollbackEvent, GameRollbackEventPublic
from game.models.time_added import GameTimeAddedEvent, GameTimeAddedEventPublic
from game.models.time_update import GameTimeUpdate, GameTimeUpdatePublic
from pubsub.models.state import GameStateRefresh
from utils.custom_model import CustomSQLModel


GenericEvent = GamePlyEventPublic | GameChatMessageEventPublic | GameOfferEventPublic | GameTimeAddedEventPublic | GameRollbackEventPublic
GenericEventList = list[GenericEvent]


class GameBase(CustomSQLModel):
    started_at: CurrentDatetime

    time_control_kind: TimeControlKind
    rated: bool
    custom_starting_sip: OptionalSip
    external_uploader_ref: OptionalPlayerRef


class Game(GameBase, table=True):
    id: int | None = Field(default=None, primary_key=True)
    white_player_ref: PlayerRef
    black_player_ref: PlayerRef
    latest_sip: Sip
    opening_sip: Sip

    fischer_time_control: GameFischerTimeControl | None = Relationship(back_populates="game", cascade_delete=True)
    outcome: GameOutcome | None = Relationship(back_populates="game", cascade_delete=True)
    ply_events: list[GamePlyEvent] = Relationship(back_populates="game", cascade_delete=True)
    chat_message_events: list[GameChatMessageEvent] = Relationship(back_populates="game", cascade_delete=True)
    offer_events: list[GameOfferEvent] = Relationship(back_populates="game", cascade_delete=True)
    time_added_events: list[GameTimeAddedEvent] = Relationship(back_populates="game", cascade_delete=True)
    rollback_events: list[GameRollbackEvent] = Relationship(back_populates="game", cascade_delete=True)

    @classmethod
    def load_options(cls, just_summary: bool, include_time_control: bool = True) -> list[Load]:
        options = [
            joinedload(Game.outcome)
                .options(*GameOutcome.load_options()),  # noqa: E131
        ]
        if include_time_control:
            options.append(
                joinedload(Game.fischer_time_control)
            )
        if not just_summary:
            options += [
                selectinload(Game.ply_events)
                    .options(*GamePlyEvent.load_options()),  # noqa: E131
                selectinload(Game.chat_message_events),
                selectinload(Game.offer_events),
                selectinload(Game.time_added_events)
                    .options(*GameTimeAddedEvent.load_options()),  # noqa: E131
                selectinload(Game.rollback_events)
                    .options(*GameRollbackEvent.load_options()),  # noqa: E131
            ]
        return options

    def collect_refs(self, include_nested: bool) -> set[str]:
        result = {
            self.white_player_ref,
            self.black_player_ref,
        }
        if include_nested:
            for chat_event in self.chat_message_events:
                result.add(chat_event.author_ref)
        return result

    def _collect_events(self, resolved_refs: ResolvedRefs, include_spectator_messages: bool = True) -> GenericEventList:
        events: GenericEventList = []

        for ply_event in self.ply_events:
            if not ply_event.is_cancelled:
                events.append(ply_event.to_public())
        for chat_event in self.chat_message_events:
            if include_spectator_messages or not chat_event.spectator:
                events.append(chat_event.to_public(resolved_refs))
        for offer_event in self.offer_events:
            events.append(GameOfferEventPublic.cast(offer_event))
        for time_added_event in self.time_added_events:
            events.append(time_added_event.to_public())
        for rollback_event in self.rollback_events:
            events.append(rollback_event.to_public())

        def get_soring_key(event: GenericEvent) -> datetime:
            key = event.occurred_at.timestamp()
            if isinstance(event, GameRollbackEventPublic):
                key += 0.0000001
            return key

        return sorted(events, key=get_soring_key)

    def to_state_refresh(
        self,
        resolved_refs: ResolvedRefs,
        latest_time_update: GameTimeUpdate | None,
        reason: Literal['SUB', 'INVALID_MOVE'],
        include_spectator_messages: bool = True
    ) -> GameStateRefresh:
        return GameStateRefresh(
            refresh_reason=reason,
            outcome=self.outcome.to_public() if self.outcome else None,
            events=self._collect_events(resolved_refs, include_spectator_messages),
            latest_time_update=GameTimeUpdatePublic.cast(latest_time_update)
        )

    def _to_summary_generic(
        self,
        resolved_refs: ResolvedRefs,
        fischer_time_control: GameFischerTimeControl | None,
        outcome: GameOutcome | None,
    ) -> GameSummaryPublic:
        return GameSummaryPublic(
            started_at=self.started_at,
            white_player=resolved_refs.get(self.white_player_ref),
            black_player=resolved_refs.get(self.black_player_ref),
            time_control_kind=self.time_control_kind,
            rated=self.rated,
            custom_starting_sip=self.custom_starting_sip,
            external_uploader_ref=self.external_uploader_ref,
            id=self.id,
            opening_sip=self.opening_sip,
            latest_sip=self.latest_sip,
            fischer_time_control=GameFischerTimeControlPublic.cast(fischer_time_control),
            outcome=outcome.to_public() if outcome else None,
        )

    def to_summary(self, resolved_refs: ResolvedRefs) -> GameSummaryPublic:
        return self._to_summary_generic(resolved_refs, self.fischer_time_control, self.outcome)

    def to_summary_as_new(self, resolved_refs: ResolvedRefs, fischer_time_control: GameFischerTimeControl | None) -> GameSummaryPublic:
        return self._to_summary_generic(resolved_refs, fischer_time_control, None)

    def to_public(self, resolved_refs: ResolvedRefs, latest_time_update: GameTimeUpdate | None) -> GamePublic:
        return GamePublic(
            **self.to_summary(resolved_refs).model_dump(),
            events=self._collect_events(resolved_refs),
            latest_time_update=GameTimeUpdatePublic.cast(latest_time_update)
        )


class GameSummaryPublic(GameBase):
    id: int
    white_player: UserRefWithNickname
    black_player: UserRefWithNickname
    latest_sip: Sip
    opening_sip: Sip

    fischer_time_control: GameFischerTimeControlPublic | None
    outcome: GameOutcomePublic | None


class GamePublic(GameSummaryPublic):
    events: GenericEventList
    latest_time_update: GameTimeUpdatePublic | None


class GameStartedBroadcastedData(GameBase):
    id: int
    white_player: UserRefWithNickname
    black_player: UserRefWithNickname

    fischer_time_control: GameFischerTimeControlPublic | None
