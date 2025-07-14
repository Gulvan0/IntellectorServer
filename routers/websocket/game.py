from sqlmodel import Session, desc, select
from models.game import Game, GamePlyEvent, PlyIntentData
from net.fastapi_wrapper import WebSocketWrapper
from net.incoming import WebSocketHandlerCollection
from net.util import WebSocketException
from rules import HexCoordinates, PieceColor, Ply, Position
from utils.datatypes import UserReference


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

        last_ply_event = session.exec(select(
            GamePlyEvent
        ).where(
            GamePlyEvent.game_id == payload.game_id
        ).order_by(
            desc(GamePlyEvent.ply_index)
        )).first()

        if last_ply_event:
            last_position = Position.from_sip(last_ply_event.sip_after)
            future_ply_index = last_ply_event.ply_index + 1
        else:
            last_position = Position.from_sip(game.custom_starting_sip) if game.custom_starting_sip else Position.default_starting()
            future_ply_index = 0

        if last_position.color_to_move != client_color:
            raise WebSocketException("It's not your turn!")

        # TODO: Check timeout (has to be the separate function taking optional precalculated args)

        ply = Ply(
            HexCoordinates(payload.from_i, payload.from_j),
            HexCoordinates(payload.to_i, payload.to_j),
            payload.morph_into.to_piece_kind() if payload.morph_into else None
        )
        if not last_position.is_ply_possible(ply):
            ...  # TODO: Send invalid move notification

        # TODO: Perform ply, compare with the sip from the payload, raise on mismatch (or better, send current game state)

        ...  # TODO: To be filled later (compare with the original Haxe implementation to make sure it aligns)
        # + remember to notify about cancelled challenges (and other then-implicit-now-explicit things)
        # + when saving the time data don't forget to update the state.game_timeout_not_earlier_than entry (but not before the second move)


# TODO: Bot game handlers
