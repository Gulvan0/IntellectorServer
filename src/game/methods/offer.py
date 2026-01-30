
from datetime import datetime

from fastapi import HTTPException
from board.deserializers.sip import color_to_move_from_sip
from config.models import MainConfig, SecretConfig
from game.methods.event import append_offer_event
from game.methods.rollback import RollbackOfferAuthorInput, perform_rollback, validate_rollback
from game.models.main import Game
from game.models.offer import GameOfferEvent, OfferActionBroadcastedData
from net.core import MutableState
from game.methods.end import end_game
from game.methods.get import (
    get_active_offers,
    get_ply_cnt,
    is_offer_active,
)
from board.piece import PieceColor
from game.datatypes import OfferAction, OfferKind, OutcomeKind
from pubsub.models.channel import GameEventChannel
from pubsub.outgoing_event.update import OfferActionPerformed
from utils.async_orm_session import AsyncSession


async def create_offer(
    session: AsyncSession,
    state: MutableState,
    main_config: MainConfig,
    secret_config: SecretConfig,
    game: Game,
    offer_kind: OfferKind,
    offer_author: PieceColor
) -> None:
    assert game.id

    ply_cnt = await get_ply_cnt(session, game.id)

    if offer_kind == OfferKind.DRAW:
        if ply_cnt < 2:
            raise HTTPException(403, "Draw cannot be offered during the first two moves of the game")
    else:
        starting_color = color_to_move_from_sip(game.custom_starting_sip) if game.custom_starting_sip else PieceColor.WHITE
        ply_cnt_threshold = 1 if offer_author == starting_color else 2
        if ply_cnt < ply_cnt_threshold:
            raise HTTPException(403, "Cannot ask for a takeback before your first move")

    if await is_offer_active(session, game.id, offer_kind, offer_author):
        raise HTTPException(409, "Offer is already active")

    if offer_kind == OfferKind.DRAW and is_offer_active(session, game.id, offer_kind, offer_author.opposite()):
        await accept_draw(session, state, main_config, secret_config, game.id, offer_author.opposite(), skip_activity_check=True)
        return

    await append_offer_event(session, state, OfferAction.CREATE, offer_kind, offer_author, game.id)


async def cancel_offer(
    session: AsyncSession,
    state: MutableState,
    game_id: int,
    offer_kind: OfferKind,
    offer_author: PieceColor,
    raise_on_missing: bool = True,
    commit: bool = True
) -> None:
    if not await is_offer_active(session, game_id, offer_kind, offer_author):
        if raise_on_missing:
            raise HTTPException(404, "Offer is not active")
        else:
            return

    await append_offer_event(session, state, OfferAction.CANCEL, offer_kind, offer_author, game_id, commit)


async def decline_offer(
    session: AsyncSession,
    state: MutableState,
    game_id: int,
    offer_kind: OfferKind,
    offer_author: PieceColor
) -> None:
    if not await is_offer_active(session, game_id, offer_kind, offer_author):
        raise HTTPException(404, "Offer is not active")

    await append_offer_event(session, state, OfferAction.DECLINE, offer_kind, offer_author, game_id)


async def accept_draw(
    session: AsyncSession,
    state: MutableState,
    main_config: MainConfig,
    secret_config: SecretConfig,
    game_id: int,
    offer_author: PieceColor,
    skip_activity_check: bool
) -> None:
    if not skip_activity_check and not await is_offer_active(session, game_id, OfferKind.DRAW, offer_author):
        raise HTTPException(404, "Offer is not active")

    await append_offer_event(session, state, OfferAction.ACCEPT, OfferKind.DRAW, offer_author, game_id)

    await end_game(session, state, main_config, secret_config, game_id, OutcomeKind.DRAW_AGREEMENT, None)


async def accept_takeback(
    session: AsyncSession,
    state: MutableState,
    offer_author: PieceColor,
    game: Game
) -> None:
    assert game.id

    if not await is_offer_active(session, game.id, OfferKind.TAKEBACK, offer_author):
        raise HTTPException(404, "Offer is not active")

    try:
        validation_results = await validate_rollback(
            session=session,
            game_id=game.id,
            input=RollbackOfferAuthorInput(offer_author)
        )
    except HTTPException:
        await append_offer_event(session, state, OfferAction.CANCEL, OfferKind.TAKEBACK, offer_author, game.id)
        raise
    else:
        await cancel_offer(session, state, game.id, OfferKind.TAKEBACK, offer_author.opposite(), raise_on_missing=False, commit=False)
        await cancel_offer(session, state, game.id, OfferKind.DRAW, offer_author, raise_on_missing=False, commit=False)
        await cancel_offer(session, state, game.id, OfferKind.DRAW, offer_author.opposite(), raise_on_missing=False, commit=False)

        await append_offer_event(session, state, OfferAction.ACCEPT, OfferKind.TAKEBACK, offer_author, game.id, commit=False)

        await perform_rollback(session, state, game.id, game, validation_results)


async def cancel_all_active_offers(session: AsyncSession, state: MutableState, game_id: int, ply_dt: datetime) -> None:
    for offer_event in await get_active_offers(session, game_id):
        cancel_event = GameOfferEvent(
            occurred_at=ply_dt,
            action=OfferAction.CANCEL,
            offer_kind=offer_event.offer_kind,
            offer_author=offer_event.offer_author,
            game_id=game_id
        )
        session.add(cancel_event)

        broadcasted_event = OfferActionPerformed(OfferActionBroadcastedData.cast(cancel_event), GameEventChannel(game_id=game_id))
        await state.ws_subscribers.broadcast(broadcasted_event)
    await session.commit()
