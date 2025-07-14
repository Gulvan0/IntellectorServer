from models.game import GamePlyEvent  # TODO: To be changed later
from net.fastapi_wrapper import WebSocketWrapper
from net.incoming import WebSocketHandlerCollection
from utils.datatypes import UserReference


collection = WebSocketHandlerCollection()


@collection.register(GamePlyEvent)
async def move(ws: WebSocketWrapper, client: UserReference | None, payload: GamePlyEvent):
    ...  # TODO: To be filled later


# TODO: Bot game handlers
