from board.constants.sip import DEFAULT_STARTING_SIP
from common.models import Id
from game.methods.get import get_current_games, get_last_ply_event, get_latest_time_update
from game.models.main import Game, OngoingGamePublic, OngoingGameUpdate
from game.models.rest.common import GameFilter
from game.models.time_update import GameTimeUpdatePublic
from net.state import MutableState
from pubsub.models.channel import PlayerOngoingGamesEventChannel
from pubsub.outgoing_event.update import OngoingGameEnded, OngoingGameUpdated
from utils.async_orm_session import AsyncSession


async def get_ongoing_game_update(session: AsyncSession, game_id: int, custom_starting_sip: str | None) -> OngoingGameUpdate:
    last_ply_event = await get_last_ply_event(session, game_id)
    latest_time_update = await get_latest_time_update(session, game_id)

    return OngoingGameUpdate(
        game_id=game_id,
        ply_cnt=last_ply_event.ply_index + 1 if last_ply_event else 0,
        latest_sip=last_ply_event.sip_after if last_ply_event else custom_starting_sip or DEFAULT_STARTING_SIP,
        last_ply_at=last_ply_event.occurred_at if last_ply_event else None,
        latest_time_update=GameTimeUpdatePublic.cast(latest_time_update)
    )


async def get_player_ongoing_games(session: AsyncSession, player_ref: str) -> list[OngoingGamePublic]:
    summaries = await get_current_games(session, GameFilter(player_ref=player_ref), limit=None)

    ongoing_games = []
    for summary in summaries:
        update = await get_ongoing_game_update(session, summary.id, summary.custom_starting_sip)
        ongoing_games.append(OngoingGamePublic(
            **summary.model_dump(exclude={'latest_sip'}),
            latest_sip=update.latest_sip,
            ply_cnt=update.ply_cnt,
            last_ply_at=update.last_ply_at,
            latest_time_update=update.latest_time_update
        ))
    return ongoing_games


def _player_channels(game: Game) -> list[PlayerOngoingGamesEventChannel]:
    return [
        PlayerOngoingGamesEventChannel(watched_ref=player_ref)
        for player_ref in (game.white_player_ref, game.black_player_ref)
    ]


async def broadcast_ongoing_game_update(session: AsyncSession, state: MutableState, game_id: int) -> None:
    db_game = await session.get(Game, game_id, populate_existing=True)  # the cached one may be expired by a commit
    if not db_game:
        return

    update = await get_ongoing_game_update(session, game_id, db_game.custom_starting_sip)
    for channel in _player_channels(db_game):
        await state.ws_subscribers.broadcast(OngoingGameUpdated(update, channel))


async def broadcast_ongoing_game_ended(state: MutableState, game: Game) -> None:
    assert game.id is not None
    for channel in _player_channels(game):
        await state.ws_subscribers.broadcast(OngoingGameEnded(Id(id=game.id), channel))
