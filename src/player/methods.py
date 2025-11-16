from sqlmodel import Session, desc, select, func
from src.common.sql import exists, not_expired
from src.common.user_ref import UserReference
from src.player.models import Player, PlayerEloProgress, PlayerFollowedPlayer, PlayerRestriction, PlayerRestrictionPublic, PlayerRole, PlayerRolePublic
from src.player.datatypes import GameStats, OverallGameStats, UserRestrictionKind, UserRole
from src.utils.cast import model_cast

import src.game.datatypes as game_datatypes


def prettify_player_reference(player_ref: UserReference, session: Session) -> str:
    if player_ref.is_guest():
        return f"Guest {player_ref.guest_id}"
    elif player_ref.is_bot():
        return f"{player_ref.bot_name} (bot)"
    else:
        player = session.get(Player, player_ref.login)
        return player.nickname if player else player_ref.login


def create_player(session: Session, login: str, nickname: str, commit: bool = True):
    player = Player(
        login=login,
        nickname=nickname,
    )
    session.add(player)
    if commit:
        session.commit()


def is_banned_in_ranked(session: Session, caller: UserReference) -> bool:
    return exists(session, select(
        PlayerRestriction
    ).where(
        PlayerRestriction.kind == UserRestrictionKind.RATED_GAMES,
        PlayerRestriction.login == caller.login,
        not_expired(PlayerRestriction.expires)
    ))


def is_player_following_player(session: Session, follower: str | None, followed: str | None) -> bool:
    if follower and followed and follower != followed:
        return session.get(PlayerFollowedPlayer, (follower, followed)) is not None
    return False


def get_followed_player_logins(session: Session, follower: str) -> list[str]:
    return list(session.exec(select(
        PlayerFollowedPlayer.followed_login
    ).where(
        PlayerFollowedPlayer.follower_login == follower
    )))


def get_roles(session: Session, role_owner_login: str, preferred_role: UserRole | None) -> list[PlayerRolePublic]:
    db_roles = session.exec(select(
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


def get_restrictions(session: Session, restriction_owner_login: str) -> list[PlayerRestrictionPublic]:
    db_restrictions = session.exec(select(
        PlayerRestriction
    ).where(
        PlayerRestriction.login == restriction_owner_login,
        not_expired(PlayerRestriction.expires)
    ))
    return [
        model_cast(db_restriction, PlayerRestrictionPublic)
        for db_restriction in db_restrictions
    ]


def get_overall_game_stats(
    session: Session,
    player_login: str,
    overall_counts: game_datatypes.OverallGameCounts,
    required_calibration_games_cnt: int
) -> OverallGameStats:
    db_elo_entries = session.exec(select(
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
