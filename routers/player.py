from dataclasses import dataclass, field
from datetime import datetime, UTC

import bcrypt  # type: ignore
from fastapi import APIRouter, HTTPException, UploadFile, Depends
from sqlalchemy import update
import sqlalchemy.sql.functions as func
from sqlmodel import Session, col, desc, or_, select

from models import (
    Game,
    GameStats,
    PlayerEloProgress,
    PlayerBase,
    PlayerFollowedPlayer,
    PlayerPublic,
    Player,
    PlayerRestriction,
    PlayerRestrictionBase,
    PlayerRestrictionPublic,
    PlayerRole,
    PlayerRoleBase,
    PlayerRolePublic,
    PlayerUpdate,
    RestrictionBatchRemovalPayload,
    RestrictionCastingPayload,
    RestrictionRemovalPayload,
    RoleOperationPayload,
    Study,
)
from models.channel import IncomingChallengesEventChannel
from utils.datatypes import StudyPublicity, TimeControlKind, UserReference, UserRole
from utils.query import not_expired
from .utils import MainConfigDependency, MutableStateDependency, OptionalPlayerLoginDependency, PlayerLogin, verify_admin, MandatoryPlayerLoginDependency, SessionDependency


router = APIRouter(prefix="/player")


@dataclass
class OverallGameCounts:
    by_time_control: dict[TimeControlKind, int] = field(default_factory=dict)
    total: int = 0


@dataclass
class OverallGameStats:
    by_time_control: dict[TimeControlKind, GameStats] = field(default_factory=dict)
    best: GameStats = field(default_factory=lambda: GameStats(elo=None, is_elo_provisional=True, games_cnt=0))

    def extend_with(self, time_control_kind: TimeControlKind, stats: GameStats) -> None:
        if time_control_kind in self.by_time_control:
            return
        self.by_time_control[time_control_kind] = stats
        if stats.is_better_than(self.best):
            self.best = stats


def is_player_following_player(session: Session, follower: str | None, followed: str | None) -> bool:
    if follower and followed and follower != followed:
        return session.get(PlayerFollowedPlayer, (follower, followed)) is not None
    return False


def get_studies_cnt(session: Session, author_login: str, include_private: bool) -> int:
    studies_selection_query = select(
        func.count(col(Study.id))
    ).where(
        Study.author_login == author_login
    )
    if not include_private:
        studies_selection_query = studies_selection_query.where(
            col(Study.publicity).in_([StudyPublicity.PROFILE_AND_LINK_ONLY, StudyPublicity.PUBLIC])
        )
    return session.exec(studies_selection_query).one()


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
            **PlayerRoleBase.model_validate(db_role).model_dump()
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
        PlayerRestrictionPublic(**PlayerRestrictionBase.model_validate(db_restriction).model_dump())
        for db_restriction in db_restrictions
    ]


def get_overall_game_counts(session: Session, player_login: str) -> OverallGameCounts:
    db_games_cnt = session.exec(select(
        Game.time_control_kind,
        func.count(col(Game.id))
    ).where(
        or_(
            Game.white_player_ref == player_login,
            Game.black_player_ref == player_login
        )
    ).group_by(
        Game.time_control_kind
    ))

    game_counts = OverallGameCounts()
    for db_games_cnt_item in db_games_cnt:
        game_counts.by_time_control[TimeControlKind(db_games_cnt_item[0])] = db_games_cnt_item[1]
        game_counts.total += db_games_cnt_item[1]
    return game_counts


def get_overall_game_stats(session: Session, player_login: str, overall_counts: OverallGameCounts, required_calibration_games_cnt: int) -> OverallGameStats:
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


@router.get("/{login}", response_model=PlayerPublic)
async def get_player(
    *,
    login: PlayerLogin,
    session: SessionDependency,
    state: MutableStateDependency,
    client_login: OptionalPlayerLoginDependency,
    main_config: MainConfigDependency
):
    db_player = session.get(Player, login)
    if not db_player:
        raise HTTPException(status_code=404, detail="Player not found")

    game_counts = get_overall_game_counts(session, login)
    game_stats = get_overall_game_stats(session, login, game_counts, main_config.elo.calibration_games)

    user_ref = UserReference.logged(login)
    player = PlayerPublic(
        is_friend=is_player_following_player(session, client_login, login),
        status=state.get_user_status_in_channel(user_ref, IncomingChallengesEventChannel(user_ref=login)),
        per_time_control_stats=game_stats.by_time_control,
        total_stats=GameStats(elo=game_stats.best.elo, is_elo_provisional=game_stats.best.is_elo_provisional, games_cnt=game_counts.total),
        studies_cnt=get_studies_cnt(session, login, client_login == login),
        followed_players=get_followed_player_logins(session, login),
        roles=get_roles(session, login, db_player.preferred_role),
        restrictions=get_restrictions(session, login),
        **PlayerBase.model_validate(db_player).model_dump()
    )

    return player


@router.patch("/{login}")
async def update_player(
    *,
    session: SessionDependency,
    login: PlayerLogin,
    client_login: MandatoryPlayerLoginDependency,
    player: PlayerUpdate
):
    if client_login != login and not session.get(PlayerRole, (UserRole.ADMIN, client_login)):
        raise HTTPException(status_code=403, detail="Forbidden")

    db_player = session.get(Player, login)
    if not db_player:
        raise HTTPException(status_code=404, detail="Player not found")

    if player.nickname:
        if player.nickname.lower() != login:
            raise HTTPException(status_code=400, detail="Only capitalization may be changed")
        db_player.nickname = player.nickname

    if player.password:
        salt = bcrypt.gensalt()
        db_player.password.salt = salt
        db_player.password.password_hash = bcrypt.hashpw(player.password, salt)

    if player.preferred_role:
        if not session.get(PlayerRole, (player.preferred_role, login)):
            raise HTTPException(status_code=400, detail="The player does not have the role selected to be set as preferred")
        db_player.preferred_role = player.preferred_role

    session.add(db_player)
    session.commit()


@router.post("/{login}/follow")
async def follow(*, session: SessionDependency, login: PlayerLogin, client_login: MandatoryPlayerLoginDependency):
    if client_login == login:
        raise HTTPException(status_code=400, detail="Cannot follow self")

    if not session.get(Player, login):
        raise HTTPException(status_code=404, detail="Player not found")

    if session.get(PlayerFollowedPlayer, (client_login, login)):
        raise HTTPException(status_code=400, detail="Already followed")

    db_player_followed_player = PlayerFollowedPlayer(
        follower_login=client_login,
        followed_login=login
    )
    session.add(db_player_followed_player)
    session.commit()


@router.post("/{login}/unfollow")
async def unfollow(*, session: SessionDependency, login: PlayerLogin, client_login: MandatoryPlayerLoginDependency):
    if client_login == login:
        raise HTTPException(status_code=400, detail="Cannot unfollow self")

    db_player_followed_player = session.get(PlayerFollowedPlayer, (client_login, login))
    if not db_player_followed_player:
        raise HTTPException(status_code=404, detail="Player is not followed or doesn't exist")

    session.delete(db_player_followed_player)
    session.commit()


@router.post("/{login}/role/add", dependencies=[Depends(verify_admin)])
async def add_role(*, session: SessionDependency, login: PlayerLogin, payload: RoleOperationPayload):
    if not session.get(Player, login):
        raise HTTPException(status_code=404, detail="Player not found")

    if session.get(PlayerRole, (payload.role, login)):
        raise HTTPException(status_code=400, detail="Role is already present")

    db_role = PlayerRole(
        role=payload.role,
        login=login
    )
    session.add(db_role)
    session.commit()


@router.delete("/{login}/role/remove", dependencies=[Depends(verify_admin)])
async def remove_role(
    *,
    session: SessionDependency,
    login: PlayerLogin,
    payload: RoleOperationPayload
):
    db_player = session.get(Player, login)
    if not db_player:
        raise HTTPException(status_code=404, detail="Player not found")

    db_role = session.get(PlayerRole, (payload.role, login))
    if not db_role:
        raise HTTPException(status_code=404, detail="Role is not assigned to this player")

    if db_player.preferred_role == payload.role:
        db_player.preferred_role = None
        session.add(db_player)

    session.delete(db_role)
    session.commit()


@router.post("/{login}/restriction/add", dependencies=[Depends(verify_admin)])
async def add_restriction(
    *,
    session: SessionDependency,
    login: PlayerLogin,
    payload: RestrictionCastingPayload
):
    if not session.get(Player, login):
        raise HTTPException(status_code=404, detail="Player not found")

    db_restriction = PlayerRestriction(
        expires=payload.expires,
        kind=payload.restriction,
        login=login
    )
    session.add(db_restriction)
    session.commit()


@router.delete("/{login}/restriction/remove", dependencies=[Depends(verify_admin)])
async def remove_restriction(*, session: SessionDependency, payload: RestrictionRemovalPayload):
    db_restriction = session.get(PlayerRestriction, payload.restriction_id)
    if not db_restriction:
        raise HTTPException(status_code=404, detail="Not found")

    db_restriction.expires = datetime.now(UTC)
    session.add(db_restriction)
    session.commit()


@router.delete("/{login}/restriction/purge", dependencies=[Depends(verify_admin)])
async def purge_restrictions(
    *,
    session: SessionDependency,
    login: PlayerLogin,
    payload: RestrictionBatchRemovalPayload
):
    update_query = update(PlayerRestriction).values(expires=datetime.now(UTC)).where(col(PlayerRestriction.login) == login)
    if payload.restriction:
        update_query = update_query.where(col(PlayerRestriction.kind) == payload.restriction)
    session.exec(update_query)  # type: ignore

    session.commit()


@router.post("/{login}/avatar/update")
async def update_avatar(
    *,
    session: SessionDependency,
    login: PlayerLogin,
    image: UploadFile,
    client_login: MandatoryPlayerLoginDependency
):
    raise HTTPException(status_code=501, detail="Avatar upload is not yet available")
