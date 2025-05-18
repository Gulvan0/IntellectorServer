from models.game import GamePlyEvent  # TODO: To be changed later
from utils.fastapi_wrappers import WebSocketHandlerCollection, WebSocketWrapper


collection = WebSocketHandlerCollection()


@collection.register(GamePlyEvent)
async def move(ws: WebSocketWrapper, payload: GamePlyEvent):
    ...  # TODO: To be filled later
