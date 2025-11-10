from typing import Literal
from sqlmodel import Session
from models.game import (
    Game,
    GameChatMessageEventPublic,
    GameOfferEventPublic,
    GameOutcomePublic,
    GamePlyEventPublic,
    GamePublic,
    GameRollbackEventPublic,
    GameStateRefresh,
    GameTimeAddedEventPublic,
)
from models.game.main import GenericEventList
from models.game.time_control import GameFischerTimeControlPublic
from models.game.time_update import GameTimeUpdatePublic
from routers.shared_methods.game.get import get_ply_history
from routers.shared_queries.game import get_latest_time_update
from utils.query import model_cast, model_cast_optional


def collect_game_events(
    session: Session,
    game_id: int,
    game: Game,
    include_spectator_messages: bool
) -> GenericEventList:
    events: GenericEventList = []

    for ply_event in get_ply_history(session, game_id):
        events.append(ply_event.to_public())
    for chat_event in game.chat_message_events:
        if include_spectator_messages or not chat_event.spectator:
            events.append(model_cast(chat_event, GameChatMessageEventPublic))
    for offer_event in game.offer_events:
        events.append(model_cast(offer_event, GameOfferEventPublic))
    for time_added_event in game.time_added_events:
        events.append(time_added_event.to_public())
    for rollback_event in game.rollback_events:
        events.append(rollback_event.to_public())

    return sorted(events, key=lambda x: x.occurred_at)


def compose_public_game(
    session: Session,
    game: Game
) -> GamePublic:
    assert game.id
    return GamePublic(
        started_at=game.started_at,
        white_player_ref=game.white_player_ref,
        black_player_ref=game.black_player_ref,
        time_control_kind=game.time_control_kind,
        rated=game.rated,
        custom_starting_sip=game.custom_starting_sip,
        external_uploader_ref=game.external_uploader_ref,
        id=game.id,
        fischer_time_control=model_cast_optional(game.fischer_time_control, GameFischerTimeControlPublic),
        outcome=game.outcome.to_public() if game.outcome else None,
        events=collect_game_events(session, game.id, game, include_spectator_messages=True),
        latest_time_update=model_cast_optional(get_latest_time_update(session, game.id), GameTimeUpdatePublic)
    )


def compose_state_refresh(
    session: Session,
    game_id: int,
    game: Game,
    reason: Literal['sub', 'invalid_move'],
    include_spectator_messages: bool
) -> GameStateRefresh:
    return GameStateRefresh(
        game_id=game_id,
        refresh_reason=reason,
        outcome=game.outcome.to_public() if game.outcome else None,
        events=collect_game_events(session, game_id, game, include_spectator_messages),
        latest_time_update=model_cast_optional(get_latest_time_update(session, game_id), GameTimeUpdatePublic)
    )
