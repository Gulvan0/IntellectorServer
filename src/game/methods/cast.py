from datetime import datetime, timedelta
from typing import Literal

from src.game.exceptions import TimeoutReachedException
from src.game.models.offer import GameOfferEventPublic
from src.game.models.main import Game, GamePublic, GameStateRefresh, GenericEventList
from src.game.models.time_control import GameFischerTimeControlPublic
from src.game.models.time_update import GameTimeUpdate, GameTimeUpdatePublic, GameTimeUpdateReason
from src.game.methods.get import get_ply_history, get_latest_time_update
from src.rules.piece import PieceColor
from src.utils.async_orm_session import AsyncSession

import src.player.methods as player_methods


async def collect_game_events(
    session: AsyncSession,
    game_id: int,
    game: Game,
    include_spectator_messages: bool
) -> GenericEventList:
    events: GenericEventList = []

    for ply_event in await get_ply_history(session, game_id):
        events.append(ply_event.to_public())
    for chat_event in game.chat_message_events:
        if include_spectator_messages or not chat_event.spectator:
            events.append(await chat_event.to_public(session))
    for offer_event in game.offer_events:
        events.append(GameOfferEventPublic.cast(offer_event))
    for time_added_event in game.time_added_events:
        events.append(time_added_event.to_public())
    for rollback_event in game.rollback_events:
        events.append(rollback_event.to_public())

    return sorted(events, key=lambda x: x.occurred_at)


async def to_public_game(
    session: AsyncSession,
    game: Game
) -> GamePublic:
    assert game.id
    return GamePublic(
        started_at=game.started_at,
        white_player=player_methods.get_user_ref_with_nickname(session, game.white_player_ref),
        black_player=player_methods.get_user_ref_with_nickname(session, game.black_player_ref),
        time_control_kind=game.time_control_kind,
        rated=game.rated,
        custom_starting_sip=game.custom_starting_sip,
        external_uploader_ref=game.external_uploader_ref,
        id=game.id,
        fischer_time_control=GameFischerTimeControlPublic.cast(game.fischer_time_control),
        outcome=game.outcome.to_public() if game.outcome else None,
        events=collect_game_events(session, game.id, game, include_spectator_messages=True),
        latest_time_update=GameTimeUpdatePublic.cast(await get_latest_time_update(session, game.id))
    )


async def compose_state_refresh(
    session: AsyncSession,
    game_id: int,
    game: Game,
    reason: Literal['sub', 'invalid_move'],
    include_spectator_messages: bool
) -> GameStateRefresh:
    return GameStateRefresh(
        game_id=game_id,
        refresh_reason=reason,
        outcome=game.outcome.to_public() if game.outcome else None,
        events=await collect_game_events(session, game_id, game, include_spectator_messages),
        latest_time_update=GameTimeUpdatePublic.cast(await get_latest_time_update(session, game_id))
    )


async def construct_new_ply_time_update(
    session: AsyncSession,
    game_id: int,
    ply_dt: datetime,
    new_ply_index: int,
    color_to_move: PieceColor,
    timeout_grace_ms: int
) -> GameTimeUpdate | None:
    latest_time_update = await get_latest_time_update(session, game_id)
    if not latest_time_update:
        return None

    new_time_update = latest_time_update.model_copy()
    new_time_update.reason = GameTimeUpdateReason.PLY
    new_time_update.updated_at = ply_dt

    if latest_time_update.ticking_side:
        ms_passed = int((ply_dt - latest_time_update.updated_at).total_seconds() * 1000)
        if latest_time_update.ticking_side == PieceColor.WHITE:
            new_time_update.white_ms -= ms_passed
            remaining_time = new_time_update.white_ms
        else:
            new_time_update.black_ms -= ms_passed
            remaining_time = new_time_update.black_ms

        if remaining_time <= -timeout_grace_ms:
            timed_out_at = ply_dt + timedelta(milliseconds=remaining_time)
            raise TimeoutReachedException(winner=latest_time_update.ticking_side.opposite(), reached_at=timed_out_at)

    new_time_update.ticking_side = color_to_move if new_ply_index >= 1 else None

    return new_time_update
