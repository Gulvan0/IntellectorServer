import asyncio
from datetime import datetime, UTC
from fastapi import APIRouter, HTTPException, Query, UploadFile
from sqlalchemy import update
from sqlmodel import col, desc, select

from common.datatypes import UserStatus
from common.models import UserActivity, UserRefWithNickname
from common.time_control import TimeControlKind
from game.methods.get import get_overall_player_game_counts
from log.methods import last_seen_in_logs
from player.datatypes import RankedGameStats
from player.dependencies import PLAYER_EXISTS_DEPENDENCY, DBPlayerDependency
from net.base_router import LoggingRoute
from common.user_ref import UserReference
from player.methods import get_followed_players, get_followers, get_overall_ranked_game_stats, is_player_following_player
from common.dependencies import CLIENT_IS_ADMIN_DEPENDENCY, MainConfigDependency, MandatoryPlayerLoginDependency, MutableStateDependency, SessionDependency
from common.field_types import PlayerLogin
from player.models import (
    Player,
    PlayerFollowedPlayer,
    PlayerGameStats,
    PlayerGameStatsByTimeControl,
    PlayerPublic,
    PlayerRestriction,
    PlayerRestrictionPublic,
    PlayerRole,
    PlayerRolePublic,
    PlayerUpdate,
    RestrictionBatchRemovalPayload,
    RestrictionCastingPayload,
    RestrictionRemovalPayload,
    RoleOperationPayload,
)
from pubsub.models.channel import IncomingChallengesEventChannel


router = APIRouter(prefix="/player", route_class=LoggingRoute)


@router.get("/{login}/game_stats", response_model=PlayerGameStats)
async def game_stats(
    *,
    session: SessionDependency,
    login: PlayerLogin,
    main_config: MainConfigDependency,
) -> PlayerGameStats:
    counts, ranked_stats = await asyncio.gather(
        get_overall_player_game_counts(session, login),
        get_overall_ranked_game_stats(session, main_config, login)
    )

    by_time_control = {}
    for time_control_kind in TimeControlKind.all_kinds():
        specific_ranked_stats = ranked_stats.by_time_control.get(time_control_kind, RankedGameStats())
        by_time_control[time_control_kind] = PlayerGameStatsByTimeControl(
            elo=specific_ranked_stats.elo,
            is_elo_provisional=specific_ranked_stats.is_elo_provisional,
            ranked_games_cnt=specific_ranked_stats.ranked_games_cnt,
            all_games_cnt=counts.by_time_control.get(time_control_kind, 0)
        )

    return PlayerGameStats(
        by_time_control=by_time_control,
        best_ranked=ranked_stats.best,
        total_count=counts.total
    )


@router.get("/{login}/followers", response_model=list[UserRefWithNickname])
async def get_player_followers(
    *,
    session: SessionDependency,
    login: PlayerLogin,
    offset: int = 0,
    limit: int = Query(default=50, le=100)
) -> list[UserRefWithNickname]:
    return await get_followers(session, login, limit, offset)


@router.get("/{login}/followed", response_model=list[UserRefWithNickname])
async def get_player_followed_players(
    *,
    session: SessionDependency,
    login: PlayerLogin,
    offset: int = 0,
    limit: int = Query(default=50, le=100)
) -> list[UserRefWithNickname]:
    return await get_followed_players(session, login, limit, offset)


@router.get("/{login}/is_followed_by_me", response_model=bool)
async def is_followed_by_me(
    *,
    session: SessionDependency,
    login: PlayerLogin,
    client_login: MandatoryPlayerLoginDependency,
) -> bool:
    return await is_player_following_player(session, client_login, login)


@router.post("/{login}/follow", dependencies=[PLAYER_EXISTS_DEPENDENCY])
async def follow(*, session: SessionDependency, login: PlayerLogin, client_login: MandatoryPlayerLoginDependency) -> None:
    if client_login == login:
        raise HTTPException(status_code=422, detail="Cannot follow self")

    if await session.get(PlayerFollowedPlayer, (client_login, login)):
        raise HTTPException(status_code=422, detail="Already followed")

    db_player_followed_player = PlayerFollowedPlayer(
        follower_login=client_login,
        followed_login=login
    )
    session.add(db_player_followed_player)
    await session.commit()


@router.post("/{login}/unfollow")
async def unfollow(*, session: SessionDependency, login: PlayerLogin, client_login: MandatoryPlayerLoginDependency) -> None:
    if client_login == login:
        raise HTTPException(status_code=422, detail="Cannot unfollow self")

    db_player_followed_player = await session.get(PlayerFollowedPlayer, (client_login, login))
    if not db_player_followed_player:
        raise HTTPException(status_code=404, detail="Player is not followed or doesn't exist")

    await session.delete(db_player_followed_player)
    await session.commit()


@router.post("/{login}/role/list")
async def list_roles(
    *,
    session: SessionDependency,
    login: PlayerLogin
) -> list[PlayerRolePublic]:
    db_roles = await session.exec(select(
        PlayerRole
    ).where(
        PlayerRole.login == login
    ).order_by(
        desc(PlayerRole.granted_at)
    ))

    return [PlayerRolePublic.cast(db_role) for db_role in db_roles]


@router.post("/{login}/role/add", dependencies=[CLIENT_IS_ADMIN_DEPENDENCY, PLAYER_EXISTS_DEPENDENCY])
async def add_role(*, session: SessionDependency, login: PlayerLogin, payload: RoleOperationPayload) -> None:
    if await session.get(PlayerRole, (payload.role, login)):
        raise HTTPException(status_code=422, detail="Role is already present")

    db_role = PlayerRole(
        role=payload.role,
        login=login
    )
    session.add(db_role)
    await session.commit()


@router.delete("/{login}/role/remove", dependencies=[CLIENT_IS_ADMIN_DEPENDENCY])
async def remove_role(
    *,
    session: SessionDependency,
    login: PlayerLogin,
    payload: RoleOperationPayload,
    db_player: DBPlayerDependency
) -> None:
    db_role = await session.get(PlayerRole, (payload.role, login))
    if not db_role:
        raise HTTPException(status_code=404, detail="Role is not assigned to this player")

    if db_player.preferred_role == payload.role:
        db_player.preferred_role = None
        session.add(db_player)

    await session.delete(db_role)
    await session.commit()


@router.post("/{login}/restriction/list")
async def list_restrictions(
    *,
    session: SessionDependency,
    login: PlayerLogin
) -> list[PlayerRestrictionPublic]:
    db_restrictions = await session.exec(select(
        PlayerRestriction
    ).where(
        PlayerRestriction.login == login
    ).order_by(
        desc(PlayerRestriction.casted_at)
    ))

    return [PlayerRestrictionPublic.cast(db_restriction) for db_restriction in db_restrictions]


@router.post("/{login}/restriction/add", dependencies=[CLIENT_IS_ADMIN_DEPENDENCY, PLAYER_EXISTS_DEPENDENCY])
async def add_restriction(
    *,
    session: SessionDependency,
    login: PlayerLogin,
    payload: RestrictionCastingPayload
) -> None:
    db_restriction = PlayerRestriction(
        expires=payload.expires,
        kind=payload.restriction,
        login=login
    )
    session.add(db_restriction)
    await session.commit()


@router.delete("/{login}/restriction/remove", dependencies=[CLIENT_IS_ADMIN_DEPENDENCY])
async def remove_restriction(*, session: SessionDependency, payload: RestrictionRemovalPayload) -> None:
    db_restriction = await session.get(PlayerRestriction, payload.restriction_id)
    if not db_restriction:
        raise HTTPException(status_code=404, detail="Not found")

    db_restriction.expires = datetime.now(UTC)
    session.add(db_restriction)
    await session.commit()


@router.delete("/{login}/restriction/purge", dependencies=[CLIENT_IS_ADMIN_DEPENDENCY])
async def purge_restrictions(
    *,
    session: SessionDependency,
    login: PlayerLogin,
    payload: RestrictionBatchRemovalPayload
) -> None:
    update_query = update(PlayerRestriction).values(expires=datetime.now(UTC)).where(col(PlayerRestriction.login) == login)
    if payload.restriction:
        update_query = update_query.where(col(PlayerRestriction.kind) == payload.restriction)
    await session.exec(update_query)  # type: ignore

    await session.commit()


@router.post("/{login}/avatar/update")
async def update_avatar(
    *,
    session: SessionDependency,
    login: PlayerLogin,
    image: UploadFile,
    client_login: MandatoryPlayerLoginDependency
) -> None:
    raise HTTPException(status_code=501, detail="Avatar upload is not yet available")


@router.get("/{login}", response_model=PlayerPublic)
async def get_player(
    *,
    session: SessionDependency,
    login: PlayerLogin,
    state: MutableStateDependency,
) -> PlayerPublic:
    db_player = await session.get(Player, login, options=Player.load_options(roles=True))
    if not db_player:
        raise HTTPException(status_code=404, detail="Player not found")

    activity = state.get_user_activity_in_channel(
        user_ref=UserReference.logged(login),
        channel=IncomingChallengesEventChannel(user_ref=login)
    )

    if not activity:
        last_request_sent = await last_seen_in_logs(session, login)
        last_active = last_request_sent or db_player.joined_at
        last_active_unixsecs = max(db_player.last_recorded_activity_before_v3, int(last_active.timestamp()))
        activity = UserActivity(
            status=UserStatus.OFFLINE,
            last_active_unixsecs=last_active_unixsecs
        )

    return db_player.to_public(activity)


@router.patch("/{login}")
async def update_player(
    *,
    session: SessionDependency,
    login: PlayerLogin,
    db_player: DBPlayerDependency,
    client_login: MandatoryPlayerLoginDependency,
    player: PlayerUpdate
) -> None:
    if client_login != login:
        raise HTTPException(status_code=403, detail="Forbidden")

    if player.nickname:
        if player.nickname.strip() != player.nickname:
            raise HTTPException(status_code=422, detail="The nickname cannot start and/or end with a space")

        if "  " in player.nickname:
            raise HTTPException(status_code=422, detail="The nickname cannot have two or more subsequent spaces")

        if player.nickname.lower().replace(" ", "") != login:
            raise HTTPException(status_code=422, detail="The nickname should match the login with the only exceptions being different capitalizaion and extra spaces")
        db_player.nickname = player.nickname

    if player.preferred_role:
        if not await session.get(PlayerRole, (player.preferred_role, login)):
            raise HTTPException(status_code=422, detail="The player does not have the role selected to be set as preferred")
        db_player.preferred_role = player.preferred_role

    session.add(db_player)
    await session.commit()
