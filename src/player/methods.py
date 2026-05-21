from collections.abc import Iterable

from sqlmodel import and_, col, desc, select, func
from common.models import UserRefWithNickname
from common.resolved_refs import ResolvedRefs
from common.sql import exists, not_expired
from common.time_control import TimeControlKind
from common.user_ref import UserReference
from config.models import MainConfig
from player.models import Player, PlayerEloProgress, PlayerFollowedPlayer, PlayerRestriction
from player.datatypes import RankedGameStats, OverallRankedGameStats, UserRestrictionKind
from utils.async_orm_session import AsyncSession


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


async def is_player_following_player(session: AsyncSession, follower_login: str, followed_login: str) -> bool:
    if follower_login != followed_login:
        return await session.get(PlayerFollowedPlayer, (follower_login, followed_login)) is not None
    return False


async def get_followers(session: AsyncSession, followed_login: str, limit: int, offset: int) -> list[UserRefWithNickname]:
    followers = await session.exec(select(
        PlayerFollowedPlayer.follower_login,
        Player.nickname
    ).join(
        Player,
        PlayerFollowedPlayer.follower_login == Player.login,  # type: ignore
        isouter=True
    ).where(
        PlayerFollowedPlayer.followed_login == followed_login
    ).limit(limit).offset(offset))

    return [
        UserRefWithNickname(
            user_ref=login,
            nickname=nickname
        )
        for login, nickname in followers
    ]


async def get_followed_players(session: AsyncSession, follower_login: str, limit: int, offset: int) -> list[UserRefWithNickname]:
    followed_players = await session.exec(select(
        PlayerFollowedPlayer.followed_login,
        Player.nickname
    ).join(
        Player,
        PlayerFollowedPlayer.followed_login == Player.login,  # type: ignore
        isouter=True
    ).where(
        PlayerFollowedPlayer.follower_login == follower_login
    ).limit(limit).offset(offset))

    return [
        UserRefWithNickname(
            user_ref=login,
            nickname=nickname
        )
        for login, nickname in followed_players
    ]


async def get_overall_ranked_game_stats(
    session: AsyncSession,
    main_config: MainConfig,
    player_login: str,
) -> OverallRankedGameStats:
    subquery = select(
        PlayerEloProgress.login,
        PlayerEloProgress.time_control_kind,
        func.max(PlayerEloProgress.ts).label("max_ts")
    ).where(
        PlayerEloProgress.login == player_login
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

    full_stats = OverallRankedGameStats()
    for db_elo_entry in db_elo_entries:
        full_stats.extend_with(
            db_elo_entry.time_control_kind,
            db_elo_entry.to_stats(main_config.elo.calibration_games)
        )
    return full_stats


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
