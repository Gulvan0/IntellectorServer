from sqlmodel import desc, select, func
from src.common.models import UserRefWithNickname
from src.common.sql import exists, not_expired
from src.common.user_ref import UserReference
from src.player.models import Player, PlayerEloProgress, PlayerFollowedPlayer, PlayerRestriction, PlayerRestrictionPublic, PlayerRole, PlayerRolePublic
from src.player.datatypes import GameStats, OverallGameStats, UserRestrictionKind, UserRole
from src.utils.async_orm_session import AsyncSession

import src.game.datatypes as game_datatypes


async def prettify_player_reference(user_ref: UserReference, session: AsyncSession) -> str:
    if user_ref.is_guest():
        return f"Guest {user_ref.guest_id}"
    elif user_ref.is_bot():
        return f"{user_ref.bot_name} (bot)"
    else:
        player = await session.get(Player, user_ref.login)
        return player.nickname if player else user_ref.login


async def get_user_ref_with_nickname(session: AsyncSession, user_ref: UserReference | str) -> UserRefWithNickname:
    match user_ref:
        case UserReference():
            object_user_ref = user_ref
            str_user_ref = user_ref.reference
        case str():
            object_user_ref = UserReference(user_ref)
            str_user_ref = user_ref

    nickname = await prettify_player_reference(object_user_ref, session)
    return UserRefWithNickname(user_ref=str_user_ref, nickname=nickname)


async def get_optional_user_ref_with_nickname(session: AsyncSession, user_ref: UserReference | str | None) -> UserRefWithNickname | None:
    return await get_user_ref_with_nickname(session, user_ref) if user_ref else None


async def create_player(session: AsyncSession, login: str, nickname: str, commit: bool = True) -> None:
    player = Player(
        login=login,
        nickname=nickname,
    )
    session.add(player)
    if commit:
        await session.commit()


async def is_banned_in_ranked(session: AsyncSession, caller: UserReference) -> bool:
    return await exists(session, select(
        PlayerRestriction
    ).where(
        PlayerRestriction.kind == UserRestrictionKind.RATED_GAMES,
        PlayerRestriction.login == caller.login,
        not_expired(PlayerRestriction.expires)
    ))


async def is_player_following_player(session: AsyncSession, follower: str | None, followed: str | None) -> bool:
    if follower and followed and follower != followed:
        return await session.get(PlayerFollowedPlayer, (follower, followed)) is not None
    return False


async def get_followed_players(session: AsyncSession, follower: str) -> list[UserRefWithNickname]:
    player_follow_facts = await session.exec(select(
        PlayerFollowedPlayer
    ).where(
        PlayerFollowedPlayer.follower_login == follower
    ))

    result = []
    for i, player_follow_fact in enumerate(player_follow_facts):  # TODO: Optimize (DB-side join, remove relationship)
        if i >= 100:
            return result
        result.append(UserRefWithNickname(
            user_ref=player_follow_fact.followed_login,
            nickname=player_follow_fact.followed.nickname
        ))
    return result


async def get_roles(session: AsyncSession, role_owner_login: str, preferred_role: UserRole | None) -> list[PlayerRolePublic]:
    db_roles = await session.exec(select(
        PlayerRole
    ).where(
        PlayerRole.login == role_owner_login
    ).order_by(
        desc(PlayerRole.granted_at)
    ))
    roles: list[PlayerRolePublic] = []
    for db_role in db_roles:
        is_main = db_role.role == preferred_role
        role = PlayerRolePublic(
            is_main=is_main,
            role=db_role.role,
            granted_at=db_role.granted_at
        )
        if is_main:
            roles.insert(0, role)
        else:
            roles.append(role)
    return roles


async def get_restrictions(session: AsyncSession, restriction_owner_login: str) -> list[PlayerRestrictionPublic]:
    db_restrictions = await session.exec(select(
        PlayerRestriction
    ).where(
        PlayerRestriction.login == restriction_owner_login,
        not_expired(PlayerRestriction.expires)
    ))
    return [
        PlayerRestrictionPublic.cast(db_restriction)
        for db_restriction in db_restrictions
    ]


async def get_overall_game_stats(
    session: AsyncSession,
    player_login: str,
    overall_counts: game_datatypes.OverallGameCounts,
    required_calibration_games_cnt: int
) -> OverallGameStats:
    db_elo_entries = await session.exec(select(
        PlayerEloProgress
    ).where(
        PlayerEloProgress.login == player_login
    ).group_by(
        PlayerEloProgress.time_control_kind
    ).having(
        PlayerEloProgress.ts == func.max(PlayerEloProgress.ts)
    ))

    full_stats = OverallGameStats()
    for db_elo_entry in db_elo_entries:
        full_stats.extend_with(db_elo_entry.time_control_kind, GameStats(
            elo=db_elo_entry.elo,
            is_elo_provisional=db_elo_entry.ranked_games_played >= required_calibration_games_cnt,
            games_cnt=overall_counts.by_time_control[db_elo_entry.time_control_kind]
        ))
    return full_stats
