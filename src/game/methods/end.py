import asyncio
from datetime import UTC, datetime

from common.user_ref import UserReference
from config.models import MainConfig, SecretConfig
from game.models.main import Game
from game.methods.get import get_latest_time_update, get_ongoing_finite_game
from game.datatypes import OutcomeKind
from game.models.outcome import GameEndedEloUpdate, GameEndedEloUpdates, GameOutcome
from game.models.time_update import GameTimeUpdate, GameTimeUpdateReason
from net.core import MutableState
from notification.methods import delete_game_started_notifications
from player.methods import get_ranked_game_stats_for_time_control, resolve_player_refs
from player.models import PlayerEloProgress
from pubsub.models.channel import GameEventChannel, CurrentGameListEventChannel
from pubsub.outgoing_event.update import GameEnded, NewRecentGame
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
    pre_retrieved_latest_time_update: GameTimeUpdate | None = None
) -> None:
    async with state.get_game_end_lock(game_id):
        existing_outcome = await session.get(GameOutcome, game_id)
        if existing_outcome:
            return

        if not ended_at:
            ended_at = datetime.now(UTC)

        # Here we don't make use of any relationships, so no load options are needed
        db_game = pre_retrieved_db_game or await session.get(Game, game_id)
        if not db_game:
            return

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
        session.add(db_outcome)
        await session.commit()

        elo_updates = None
        if db_game.rated and outcome != OutcomeKind.ABORT:
            players = {
                PieceColor.WHITE: UserReference(db_game.white_player_ref),
                PieceColor.BLACK: UserReference(db_game.black_player_ref)
            }

            raw_elo_updates = {}

            if players[PieceColor.WHITE].is_player() and players[PieceColor.BLACK].is_player():
                old_stats = {
                    color: await get_ranked_game_stats_for_time_control(session, main_config, player_login.login, db_game.time_control_kind)
                    for color, player_login in players.items()
                }

                for color in PieceColor:
                    if not winner_color:
                        score = 0.5
                    elif winner_color == color:
                        score = 1
                    else:
                        score = 0

                    old_player_elo = old_stats[color].elo or 1200
                    old_opponent_elo = old_stats[color.opposite()].elo or 1200
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

            await session.commit()

            elo_updates = GameEndedEloUpdates(white=raw_elo_updates[PieceColor.WHITE], black=raw_elo_updates[PieceColor.BLACK])

        await session.refresh(db_outcome)
        await session.refresh(db_game)

        async def broadcast_new_recent_game() -> None:
            collected_refs = db_game.collect_refs(include_nested=False)
            resolved_refs = await resolve_player_refs(collected_refs, session)
            await state.ws_subscribers.broadcast(NewRecentGame(
                db_game.to_summary(resolved_refs),
                CurrentGameListEventChannel()
            ))

        await asyncio.gather(
            broadcast_new_recent_game(),
            state.ws_subscribers.broadcast(GameEnded(
                db_outcome.to_broadcasted_data(elo_updates),
                GameEventChannel(game_id=game_id)
            )),
            delete_game_started_notifications(
                game_id=game_id,
                vk_token=secret_config.integrations.vk.token,
                session=session
            )
        )

        if state.shutdown_activated and not await get_ongoing_finite_game(session):
            raise KeyboardInterrupt
        else:
            state.release_game_end_lock(game_id)
