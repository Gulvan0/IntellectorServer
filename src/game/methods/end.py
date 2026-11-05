from datetime import UTC, datetime
from typing import Any

from common.user_ref import UserReference
from config.models import MainConfig, SecretConfig
from game.models.main import Game
from game.methods.get import get_latest_time_update, get_ongoing_finite_game
from game.methods.ongoing import broadcast_ongoing_game_ended
from game.datatypes import OutcomeKind
from game.models.outcome import GameEndedEloUpdate, GameEndedEloUpdates, GameOutcome
from game.models.time_update import GameTimeUpdate, GameTimeUpdateReason
from net.state import MutableState
from notification.methods import delete_game_started_notifications
from player.methods import get_ranked_game_stats_for_time_control, lock_players_for_rating_update, resolve_player_refs
from player.models import PlayerEloProgress
from common.models import Id
from pubsub.models.channel import GameEventChannel, CurrentGameListEventChannel, RecentGameListEventChannel
from pubsub.outgoing_event.base import OutgoingEvent
from pubsub.outgoing_event.update import CurrentGameEnded, GameEnded, NewRecentGame
from board.piece import PieceColor
from utils.async_orm_session import AsyncSession


async def end_game(
    session: AsyncSession,
    state: MutableState,
    main_config: MainConfig,
    secret_config: SecretConfig,
    game_id: int,
    outcome: OutcomeKind,
    winner_color: PieceColor | None,
    ended_at: datetime | None = None,
    pre_retrieved_db_game: Game | None = None,
    pre_retrieved_latest_time_update: GameTimeUpdate | None = None,
    announced_first: OutgoingEvent[Any, Any] | None = None
) -> None:
    """Must run inside `state.game_action`. Commits whatever the session has pending along with the outcome and the ratings.
    `announced_first`: an event being stored along with the ending, to broadcast before it"""
    existing_outcome = await session.get(GameOutcome, game_id)
    if existing_outcome:
        return

    if not ended_at:
        ended_at = datetime.now(UTC)

    # Here we don't make use of any relationships, so no load options are needed
    db_game = pre_retrieved_db_game or await session.get(Game, game_id)
    if not db_game:
        return

    await session.flush()
    await session.refresh(db_game)  # an earlier commit may have expired it, and an async session can't reload it lazily

    final_time_update = None
    latest_time_update = pre_retrieved_latest_time_update or await get_latest_time_update(session, game_id)

    if latest_time_update:
        time_remainders = latest_time_update.get_actual_time_remainders(ended_at)

        final_time_update = GameTimeUpdate(
            updated_at=ended_at,
            white_ms=max(0, time_remainders[PieceColor.WHITE]),
            black_ms=max(0, time_remainders[PieceColor.BLACK]),
            ticking_side=None,
            reason=GameTimeUpdateReason.GAME_ENDED,
            game_id=game_id
        )

    db_outcome = GameOutcome(
        game_ended_at=ended_at,
        kind=outcome,
        winner=winner_color,
        game_id=game_id,
        time_update=final_time_update
    )
    elo_updates = None
    if db_game.rated and outcome != OutcomeKind.ABORT:
        players = {
            PieceColor.WHITE: UserReference(db_game.white_player_ref),
            PieceColor.BLACK: UserReference(db_game.black_player_ref)
        }

        if players[PieceColor.WHITE].is_player() and players[PieceColor.BLACK].is_player():
            await lock_players_for_rating_update(session, [player.login for player in players.values()])

            old_stats = {
                color: await get_ranked_game_stats_for_time_control(session, main_config, player_login.login, db_game.time_control_kind, for_rating_update=True)
                for color, player_login in players.items()
            }

            raw_elo_updates = {}

            for color in PieceColor:
                if not winner_color:
                    score = 0.5
                elif winner_color == color:
                    score = 1
                else:
                    score = 0

                old_player_elo = old_stats[color].elo or main_config.elo.default
                old_opponent_elo = old_stats[color.opposite()].elo or main_config.elo.default
                prior_games = old_stats[color].ranked_games_cnt

                calibration_games_left = max(main_config.elo.calibration_games - prior_games, 0)
                calibration_ratio = calibration_games_left / main_config.elo.calibration_games
                exp = main_config.elo.normal_log_slope + (main_config.elo.max_log_slope - main_config.elo.normal_log_slope) * calibration_ratio
                slope = 2 ** exp

                q_player = 10 ** (old_player_elo / 400)
                q_opponent = 10 ** (old_opponent_elo / 400)
                expected_score = q_player / (q_player + q_opponent)

                delta = round(slope * (score - expected_score))
                new_elo = old_player_elo + delta

                session.add(PlayerEloProgress(
                    login=players[color].login,
                    ts=ended_at,
                    time_control_kind=db_game.time_control_kind,
                    elo=new_elo,
                    delta=delta,
                    causing_game_id=game_id,
                    ranked_games_played=prior_games + 1
                ))

                raw_elo_updates[color] = GameEndedEloUpdate(new_value=new_elo, delta=delta)

            elo_updates = GameEndedEloUpdates(white=raw_elo_updates[PieceColor.WHITE], black=raw_elo_updates[PieceColor.BLACK])
            db_outcome.white_elo_delta = elo_updates.white.delta
            db_outcome.black_elo_delta = elo_updates.black.delta

    session.add(db_outcome)
    await session.commit()

    await session.refresh(db_outcome)
    await session.refresh(db_outcome, attribute_names=['time_update'])  # to_broadcasted_data reads it, and an async session can't load it lazily
    await session.refresh(db_game)
    await session.refresh(db_game, attribute_names=['fischer_time_control', 'outcome', 'bot_settings'])  # to_summary reads them, and an async session can't load them lazily

    if announced_first:
        state.concurrent_tasks.plan(state.ws_subscribers.broadcast(announced_first))
    state.concurrent_tasks.plan(state.ws_subscribers.broadcast(GameEnded(
        db_outcome.to_broadcasted_data(elo_updates),
        GameEventChannel(game_id=game_id)
    )))
    await broadcast_ongoing_game_ended(state, db_game)
    state.concurrent_tasks.plan(state.ws_subscribers.broadcast(CurrentGameEnded(Id(id=game_id), CurrentGameListEventChannel())))

    if outcome != OutcomeKind.ABORT:
        matching_channels = [
            channel
            for channel in state.ws_subscribers.get_subscribed_channels(RecentGameListEventChannel)
            if channel.matches(db_game.time_control_kind, db_game.rated)
        ]
        if matching_channels:
            resolved_refs = await resolve_player_refs(db_game.collect_refs(include_nested=False), session)
            summary = db_game.to_summary(resolved_refs)
            for channel in matching_channels:
                state.concurrent_tasks.plan(state.ws_subscribers.broadcast(NewRecentGame(summary, channel)))

    vk_token = secret_config.integrations.vk.token
    state.concurrent_tasks.plan_with_own_session(lambda notifications_session: delete_game_started_notifications(
        game_id=game_id,
        vk_token=vk_token,
        session=notifications_session
    ))

    if state.shutdown_activated and not await get_ongoing_finite_game(session):
        state.exit_event.set()
