
from src.game.endpoint_sinks import RollbackOfferAuthorInput, perform_rollback, validate_rollback
from src.game.exceptions import SinkException
from src.game.methods.event import append_offer_event
from src.game.models.main import Game
from src.net.core import WebSocketWrapper
from src.net.utils.ws_error import WebSocketException
from src.game.methods.update import end_game
from src.game.methods.get import (
    is_offer_active,
)
from src.rules import PieceColor
from src.game.datatypes import OfferAction, OfferKind, OutcomeKind
from src.utils.async_orm_session import AsyncSession


async def create_offer(
    session: AsyncSession,
    ws: WebSocketWrapper,
    game_id: int,
    color_to_move: PieceColor,
    ply_cnt: int,
    offer_kind: OfferKind,
    offer_author: PieceColor
) -> None:
    if offer_kind == OfferKind.DRAW:
        if ply_cnt < 2:
            raise WebSocketException("Draw cannot be offered during the first two moves of the game")
    else:
        ply_cnt_threshold = 1 if color_to_move == PieceColor.WHITE else 2
        if ply_cnt < ply_cnt_threshold:
            raise WebSocketException("Cannot ask for a takeback before your first move")

    if await is_offer_active(session, game_id, offer_kind, offer_author):
        raise WebSocketException("Offer is already active")

    if offer_kind == OfferKind.DRAW and is_offer_active(session, game_id, offer_kind, offer_author.opposite()):
        await accept_draw(session, ws, game_id, offer_author.opposite(), skip_activity_check=True)
        return

    await append_offer_event(session, ws.app.mutable_state, OfferAction.CREATE, offer_kind, offer_author, game_id)


async def cancel_offer(
    session: AsyncSession,
    ws: WebSocketWrapper,
    game_id: int,
    offer_kind: OfferKind,
    offer_author: PieceColor,
    raise_on_missing: bool = True,
    commit: bool = True
) -> None:
    if not await is_offer_active(session, game_id, offer_kind, offer_author):
        if raise_on_missing:
            raise WebSocketException("Offer is not active")
        else:
            return

    await append_offer_event(session, ws.app.mutable_state, OfferAction.CANCEL, offer_kind, offer_author, game_id, commit)


async def decline_offer(
    session: AsyncSession,
    ws: WebSocketWrapper,
    game_id: int,
    offer_kind: OfferKind,
    offer_author: PieceColor
) -> None:
    if not await is_offer_active(session, game_id, offer_kind, offer_author):
        raise WebSocketException("Offer is not active")

    await append_offer_event(session, ws.app.mutable_state, OfferAction.DECLINE, offer_kind, offer_author, game_id)


async def accept_draw(session: AsyncSession, ws: WebSocketWrapper, game_id: int, offer_author: PieceColor, skip_activity_check: bool) -> None:
    if not skip_activity_check and not await is_offer_active(session, game_id, OfferKind.DRAW, offer_author):
        raise WebSocketException("Offer is not active")

    await append_offer_event(session, ws.app.mutable_state, OfferAction.ACCEPT, OfferKind.DRAW, offer_author, game_id)

    await end_game(session, ws.app.mutable_state, ws.app.secret_config, game_id, OutcomeKind.DRAW_AGREEMENT, None)


async def accept_takeback(session: AsyncSession, ws: WebSocketWrapper, game_id: int, offer_author: PieceColor, game: Game) -> None:
    if not await is_offer_active(session, game_id, OfferKind.TAKEBACK, offer_author):
        raise WebSocketException("Offer is not active")

    try:
        validation_results = await validate_rollback(
            session=session,
            game_id=game_id,
            input=RollbackOfferAuthorInput(offer_author)
        )
    except SinkException as e:
        await append_offer_event(session, ws.app.mutable_state, OfferAction.CANCEL, OfferKind.TAKEBACK, offer_author, game_id)
        raise WebSocketException(e.message)
    else:
        await cancel_offer(session, ws, game_id, OfferKind.TAKEBACK, offer_author.opposite(), raise_on_missing=False, commit=False)
        await cancel_offer(session, ws, game_id, OfferKind.DRAW, offer_author, raise_on_missing=False, commit=False)
        await cancel_offer(session, ws, game_id, OfferKind.DRAW, offer_author.opposite(), raise_on_missing=False, commit=False)

        await append_offer_event(session, ws.app.mutable_state, OfferAction.ACCEPT, OfferKind.TAKEBACK, offer_author, game_id, commit=False)

        await perform_rollback(session, ws.app.mutable_state, game_id, game, validation_results)
