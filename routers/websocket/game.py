from datetime import UTC, datetime
from sqlmodel import Session, and_, col, or_, select, func
from models.channel import GamePublicEventChannel
from models.common import PieceKindField, PlyKindField
from models.game import Game, GamePlyEvent, GamePlyEventPublic, InvalidPlyResponseData, PlyIntentData
from net.fastapi_wrapper import WebSocketWrapper
from net.incoming import WebSocketHandlerCollection
from net.outgoing import WebsocketOutgoingEventRegistry
from net.util import WebSocketException
from routers.shared_methods.game import check_timeout, end_game
from routers.shared_queries.game import get_last_ply_event
from rules import DEFAULT_STARTING_SIP, HexCoordinates, PieceColor, PieceKind, Ply, Position, PositionFinalityGroup
from utils.datatypes import OutcomeKind, UserReference


collection = WebSocketHandlerCollection()


@collection.register(PlyIntentData)
async def move(ws: WebSocketWrapper, client: UserReference | None, payload: PlyIntentData):
    if not client:
        raise WebSocketException("Authorization required. Please provide an auth token")

    with Session(ws.app.db_engine) as session:
        game = session.get(Game, payload.game_id)
        if not game:
            raise WebSocketException(f"Game {payload.game_id} does not exist")

        if game.outcome:
            raise WebSocketException(f"Game {payload.game_id} has already ended")

        if client.reference == game.white_player_ref:
            client_color = PieceColor.WHITE
        elif client.reference == game.black_player_ref:
            client_color = PieceColor.BLACK
        else:
            raise WebSocketException(f"You are not the player in game {payload.game_id}")

        last_ply_event = get_last_ply_event(session, payload.game_id)

        if last_ply_event:
            last_sip = last_ply_event.sip_after
            last_position = Position.from_sip(last_sip)
            future_ply_index = last_ply_event.ply_index + 1
        else:
            if game.custom_starting_sip:
                last_sip = game.custom_starting_sip
                last_position = Position.from_sip(last_sip)
            else:
                last_sip = DEFAULT_STARTING_SIP
                last_position = Position.default_starting()
            future_ply_index = 0

        if last_position.color_to_move != client_color:
            raise WebSocketException("It's not your turn!")

        game_ended_by_timeout = await check_timeout(
            session=session,
            state=ws.app.mutable_state,
            game_id=payload.game_id,
            last_ply_event=last_ply_event,
            last_position=last_position,
            outcome_abscence_checked=True
        )
        if game_ended_by_timeout:
            return

        from_coords = HexCoordinates(payload.from_i, payload.from_j)
        to_coords = HexCoordinates(payload.to_i, payload.to_j)
        ply = Ply(
            from_coords,
            to_coords,
            payload.morph_into.to_piece_kind() if payload.morph_into else None
        )
        is_valid = True
        if last_position.is_ply_possible(ply):
            new_position = last_position.perform_ply_without_validation(ply)
            new_sip = new_position.to_sip()
            if new_sip == payload.sip_after:
                moving_piece = last_position.piece_arrangement.get(from_coords)
                target_piece = last_position.piece_arrangement.get(to_coords)
            else:
                is_valid = False
        else:
            is_valid = False

        if not is_valid:
            ply_history = session.exec(select(
                GamePlyEvent
            ).where(
                GamePlyEvent.game_id == payload.game_id,
                not GamePlyEvent.is_cancelled
            ).order_by(
                col(GamePlyEvent.ply_index)
            )).fetchall()

            await ws.send_event(
                WebsocketOutgoingEventRegistry.INVALID_MOVE,
                InvalidPlyResponseData(
                    game_id=payload.game_id,
                    ply_history=[GamePlyEventPublic(**ply.model_dump()) for ply in ply_history],
                    current_sip=last_sip
                ),
                GamePublicEventChannel(game_id=payload.game_id)
            )
            return

        # Doing that before adding a new move to ensure correct count
        same_position_occurences_cnt = session.exec(select(
            func.count(col(GamePlyEvent.id))
        ).where(
            GamePlyEvent.game_id == payload.game_id,
            not GamePlyEvent.is_cancelled,
            GamePlyEvent.sip_after == new_sip
        )).one()
        is_threefold = same_position_occurences_cnt >= 2

        ply_dt = datetime.now(UTC)

        # TODO: Calculate time remainders (except for corresp.; only after second move; don't forget to add increment)
        # TODO: Add to ply history (use calculations above)
        # TODO: Cancel all offers (in db) + notify followers

        match new_position.get_finality_group():
            case PositionFinalityGroup.FATUM:
                await end_game(session, ws.app.mutable_state, payload.game_id, OutcomeKind.FATUM, client_color, ply_dt)
                return
            case PositionFinalityGroup.BREAKTHROUGH:
                await end_game(session, ws.app.mutable_state, payload.game_id, OutcomeKind.BREAKTHROUGH, client_color, ply_dt)
                return

        if is_threefold:
            await end_game(session, ws.app.mutable_state, payload.game_id, OutcomeKind.REPETITION, None, ply_dt)
            return

        last_progressive_ply_index = session.exec(select(
            GamePlyEvent.ply_index
        ).where(
            GamePlyEvent.game_id == payload.game_id,
            not GamePlyEvent.is_cancelled,
            or_(
                and_(
                    GamePlyEvent.target_piece != None,
                    GamePlyEvent.kind != PlyKindField.SWAP
                ),
                GamePlyEvent.moved_piece == PieceKindField.PROGRESSOR
            )
        )).first()
        is_no_progress = future_ply_index - (last_progressive_ply_index or -1) >= 60

        if is_no_progress:
            await end_game(session, ws.app.mutable_state, payload.game_id, OutcomeKind.NO_PROGRESS, None, ply_dt)
            return

        # TODO: Send move event


# TODO: Bot game handlers
# TODO: Check rounded timestamp usage everywhere, might need more precision
