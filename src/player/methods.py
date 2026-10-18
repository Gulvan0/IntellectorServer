from collections.abc import Collection, Iterable
from datetime import datetime
from typing import TYPE_CHECKING

from sqlmodel import and_, col, desc, or_, select, func
from common.datatypes import UserStatus
from common.models import UserActivity, UserRefWithNickname
from common.resolved_refs import ResolvedRefs
from common.sql import exists, not_expired
from common.time_control import TimeControlKind
from common.user_ref import UserReference
from config.models import MainConfig
from game.models.main import Game
from player.models import (
    EloHistoryEntry,
    Player,
    PlayerCard,
    PlayerConnections,
    PlayerEloProgress,
    PlayerFollowedPlayer,
    PlayerMainRating,
    PlayerRestriction,
)
from player.datatypes import RankedGameStats, OverallRankedGameStats, UserRestrictionKind
from pubsub.models.channel import IncomingChallengesEventChannel
from utils.async_orm_session import AsyncSession


if TYPE_CHECKING:
    from net.state import MutableState


async def resolve_player_refs(refs: Iterable[str | UserReference], session: AsyncSession) -> ResolvedRefs:
    result = ResolvedRefs()
    logins = set()

    for ref in refs:
        ref_object = UserReference(ref) if isinstance(ref, str) else ref
        ref_str = ref_object.reference
        if ref_object.is_player():
            logins.add(ref_str)

    if logins:
        players = await session.exec(
            select(Player).where(col(Player.login).in_(logins))
        )
        for player in players:
            result.set(player.login, UserRefWithNickname(user_ref=player.login, nickname=player.nickname))

    return result


async def resolve_player_ref(ref: str | UserReference, session: AsyncSession) -> UserRefWithNickname:
    mapping = await resolve_player_refs([ref], session)
    return mapping.get(ref)


async def resolve_optional_player_ref(ref: str | UserReference | None, session: AsyncSession) -> UserRefWithNickname | None:
    return await resolve_player_ref(ref, session) if ref is not None else None


async def create_player(session: AsyncSession, login: str, nickname: str, commit: bool = True) -> None:
    player = Player(
        login=login,
        nickname=nickname,
    )
    session.add(player)
    if commit:
        await session.commit()
    else:
        await session.flush()


async def is_banned_in_ranked(session: AsyncSession, caller: UserReference) -> bool:
    return await exists(session, select(
        PlayerRestriction
    ).where(
        PlayerRestriction.kind == UserRestrictionKind.RATED_GAMES,
        PlayerRestriction.login == caller.login,
        not_expired(PlayerRestriction.expires)
    ))


async def get_follows_since(session: AsyncSession, follower_login: str, followed_login: str) -> datetime | None:
    if follower_login == followed_login:
        return None
    db_follow = await session.get(PlayerFollowedPlayer, (follower_login, followed_login))
    return db_follow.follows_since if db_follow else None


async def get_overall_ranked_game_stats_batch(
    session: AsyncSession,
    main_config: MainConfig,
    player_logins: Collection[str],
) -> dict[str, OverallRankedGameStats]:
    result: dict[str, OverallRankedGameStats] = {login: OverallRankedGameStats() for login in player_logins}
    if not player_logins:
        return result

    subquery = select(
        PlayerEloProgress.login,
        PlayerEloProgress.time_control_kind,
        func.max(PlayerEloProgress.ts).label("max_ts")
    ).where(
        col(PlayerEloProgress.login).in_(player_logins)
    ).group_by(
        PlayerEloProgress.login,
        PlayerEloProgress.time_control_kind
    ).subquery()

    db_elo_entries = await session.exec(select(
        PlayerEloProgress
    ).join(
        subquery,
        and_(
            PlayerEloProgress.login == subquery.c.login,
            PlayerEloProgress.time_control_kind == subquery.c.time_control_kind,
            PlayerEloProgress.ts == subquery.c.max_ts,
        )
    ))

    for db_elo_entry in db_elo_entries:
        result[db_elo_entry.login].extend_with(
            db_elo_entry.time_control_kind,
            db_elo_entry.to_stats(main_config.elo.calibration_games)
        )
    return result


async def get_overall_ranked_game_stats(
    session: AsyncSession,
    main_config: MainConfig,
    player_login: str,
) -> OverallRankedGameStats:
    batch = await get_overall_ranked_game_stats_batch(session, main_config, [player_login])
    return batch[player_login]


def main_rating_of(stats: OverallRankedGameStats) -> PlayerMainRating | None:
    if not stats.best:
        return None
    best_stats = stats.by_time_control[stats.best]
    if best_stats.elo is None:
        return None
    return PlayerMainRating(
        time_control_kind=stats.best,
        elo=best_stats.elo,
        provisional=best_stats.is_elo_provisional
    )


async def get_players_in_live_games(session: AsyncSession, player_logins: Collection[str]) -> set[str]:
    if not player_logins:
        return set()

    db_games = await session.exec(select(
        Game.white_player_ref,
        Game.black_player_ref
    ).where(
        Game.outcome == None,  # noqa
        Game.time_control_kind != TimeControlKind.CORRESPONDENCE,
        or_(
            col(Game.white_player_ref).in_(player_logins),
            col(Game.black_player_ref).in_(player_logins)
        )
    ))

    return {ref for refs in db_games for ref in refs if ref in player_logins}


def get_ws_activity(state: MutableState, player_login: str) -> UserActivity | None:
    return state.get_user_activity_in_channel(
        user_ref=UserReference.logged(player_login),
        channel=IncomingChallengesEventChannel(user_ref=player_login)
    )


async def promote_to_playing(session: AsyncSession, activities: dict[str, UserActivity]) -> None:
    online_logins = {login for login, activity in activities.items() if activity.status == UserStatus.ONLINE}
    for login in await get_players_in_live_games(session, online_logins):
        activities[login] = UserActivity(status=UserStatus.PLAYING, last_active_unixsecs=activities[login].last_active_unixsecs)


async def get_player_statuses(session: AsyncSession, state: MutableState, player_logins: Collection[str]) -> dict[str, UserStatus]:
    activities: dict[str, UserActivity] = {}
    for login in player_logins:
        activity = get_ws_activity(state, login)
        if activity:
            activities[login] = activity

    await promote_to_playing(session, activities)
    return {
        login: activities[login].status if login in activities else UserStatus.OFFLINE
        for login in player_logins
    }


async def get_connections(session: AsyncSession, state: MutableState, main_config: MainConfig, player_login: str) -> PlayerConnections:
    db_follows = await session.exec(select(
        PlayerFollowedPlayer.follower_login,
        PlayerFollowedPlayer.followed_login
    ).where(
        or_(
            PlayerFollowedPlayer.follower_login == player_login,
            PlayerFollowedPlayer.followed_login == player_login
        )
    ))

    followed: set[str] = set()
    followers: set[str] = set()
    for follower_login, followed_login in db_follows:
        if follower_login == player_login:
            followed.add(followed_login)
        else:
            followers.add(follower_login)

    all_logins = followed | followers
    resolved_refs = await resolve_player_refs(all_logins, session)
    statuses = await get_player_statuses(session, state, all_logins)
    ranked_stats = await get_overall_ranked_game_stats_batch(session, main_config, all_logins)

    def cards(logins: set[str]) -> list[PlayerCard]:
        return [
            PlayerCard(
                player=resolved_refs.get(login),
                status=statuses[login],
                main_rating=main_rating_of(ranked_stats[login])
            )
            for login in sorted(logins)
        ]

    return PlayerConnections(
        friends=cards(followed & followers),
        following=cards(followed - followers),
        followers=cards(followers - followed)
    )


async def get_ranked_game_stats_for_time_control(
    session: AsyncSession,
    main_config: MainConfig,
    player_login: str,
    time_control_kind: TimeControlKind,
) -> RankedGameStats:
    entries = await session.exec(select(
        PlayerEloProgress
    ).where(
        PlayerEloProgress.login == player_login,
        PlayerEloProgress.time_control_kind == time_control_kind
    ).order_by(
        desc(PlayerEloProgress.ts)
    ))
    last_entry = entries.first()

    if not last_entry:
        return RankedGameStats()

    return last_entry.to_stats(main_config.elo.calibration_games)


async def get_elo_history(session: AsyncSession, player_login: str, time_control_kind: TimeControlKind) -> list[EloHistoryEntry]:
    entries = await session.exec(select(
        PlayerEloProgress.ts,
        PlayerEloProgress.elo
    ).where(
        PlayerEloProgress.login == player_login,
        PlayerEloProgress.time_control_kind == time_control_kind
    ).order_by(
        col(PlayerEloProgress.ts),
        col(PlayerEloProgress.id)
    ))

    return [EloHistoryEntry(ts=ts, elo=elo) for ts, elo in entries]
