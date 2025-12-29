from datetime import datetime, UTC
from fastapi import APIRouter, HTTPException, UploadFile, Depends
from sqlalchemy import update
from sqlmodel import col

from src.player.dependencies import DBPlayerDependency
from src.net.base_router import LoggingRoute
from src.common.user_ref import UserReference
from src.player.methods import get_followed_players, get_overall_game_stats, get_restrictions, get_roles, is_player_following_player
from src.player.datatypes import GameStats
from src.common.dependencies import MainConfigDependency, MandatoryPlayerLoginDependency, MutableStateDependency, OptionalPlayerLoginDependency, SessionDependency, verify_admin
from src.common.field_types import PlayerLogin
from src.player.models import (
    PlayerFollowedPlayer,
    PlayerPublic,
    PlayerRestriction,
    PlayerRole,
    PlayerUpdate,
    RestrictionBatchRemovalPayload,
    RestrictionCastingPayload,
    RestrictionRemovalPayload,
    RoleOperationPayload,
)

import src.game.methods.get as game_get_methods
import src.study.methods as study_methods
import src.pubsub.models.channel as pubsub_models


router = APIRouter(prefix="/player", route_class=LoggingRoute)


@router.get("/{login}", response_model=PlayerPublic)
async def get_player(
    *,
    session: SessionDependency,
    login: PlayerLogin,
    db_player: DBPlayerDependency,
    state: MutableStateDependency,
    client_login: OptionalPlayerLoginDependency,
    main_config: MainConfigDependency
):
    game_counts = await game_get_methods.get_overall_player_game_counts(session, login)
    game_stats = await get_overall_game_stats(session, login, game_counts, main_config.elo.calibration_games)

    user_ref = UserReference.logged(login)
    player = PlayerPublic(
        login=db_player.login,
        joined_at=db_player.joined_at,
        nickname=db_player.nickname,
        is_friend=await is_player_following_player(session, client_login, login),
        status=state.get_user_status_in_channel(user_ref, pubsub_models.IncomingChallengesEventChannel(user_ref=login)),
        per_time_control_stats=game_stats.by_time_control,
        total_stats=GameStats(elo=game_stats.best.elo, is_elo_provisional=game_stats.best.is_elo_provisional, games_cnt=game_counts.total),
        studies_cnt=await study_methods.get_player_studies_cnt(session, login, client_login == login),
        followed_players=await get_followed_players(session, login),  # TODO: Move to separate models/routes, support pagination
        roles=await get_roles(session, login, db_player.preferred_role),
        restrictions=await get_restrictions(session, login)
    )

    return player


@router.patch("/{login}")
async def update_player(
    *,
    session: SessionDependency,
    login: PlayerLogin,
    db_player: DBPlayerDependency,
    client_login: MandatoryPlayerLoginDependency,
    player: PlayerUpdate
):
    if client_login != login:
        raise HTTPException(status_code=403, detail="Forbidden")

    if player.nickname:
        if player.nickname.strip() != player.nickname:
            raise HTTPException(status_code=400, detail="The nickname cannot start and/or end with a space")

        if "  " in player.nickname:
            raise HTTPException(status_code=400, detail="The nickname cannot have two or more subsequent spaces")

        if player.nickname.lower().replace(" ", "") != login:
            raise HTTPException(status_code=400, detail="The nickname should match the login with the only exceptions being different capitalizaion and extra spaces")
        db_player.nickname = player.nickname

    if player.preferred_role:
        if not await session.get(PlayerRole, (player.preferred_role, login)):
            raise HTTPException(status_code=400, detail="The player does not have the role selected to be set as preferred")
        db_player.preferred_role = player.preferred_role

    session.add(db_player)
    await session.commit()


@router.post("/{login}/follow")
async def follow(*, session: SessionDependency, login: PlayerLogin, client_login: MandatoryPlayerLoginDependency, _: DBPlayerDependency):
    if client_login == login:
        raise HTTPException(status_code=400, detail="Cannot follow self")

    if await session.get(PlayerFollowedPlayer, (client_login, login)):
        raise HTTPException(status_code=400, detail="Already followed")

    db_player_followed_player = PlayerFollowedPlayer(
        follower_login=client_login,
        followed_login=login
    )
    session.add(db_player_followed_player)
    await session.commit()


@router.post("/{login}/unfollow")
async def unfollow(*, session: SessionDependency, login: PlayerLogin, client_login: MandatoryPlayerLoginDependency):
    if client_login == login:
        raise HTTPException(status_code=400, detail="Cannot unfollow self")

    db_player_followed_player = await session.get(PlayerFollowedPlayer, (client_login, login))
    if not db_player_followed_player:
        raise HTTPException(status_code=404, detail="Player is not followed or doesn't exist")

    await session.delete(db_player_followed_player)
    await session.commit()


@router.post("/{login}/role/add", dependencies=[Depends(verify_admin)])
async def add_role(*, session: SessionDependency, login: PlayerLogin, payload: RoleOperationPayload, _: DBPlayerDependency):
    if await session.get(PlayerRole, (payload.role, login)):
        raise HTTPException(status_code=400, detail="Role is already present")

    db_role = PlayerRole(
        role=payload.role,
        login=login
    )
    session.add(db_role)
    await session.commit()


@router.delete("/{login}/role/remove", dependencies=[Depends(verify_admin)])
async def remove_role(
    *,
    session: SessionDependency,
    login: PlayerLogin,
    payload: RoleOperationPayload,
    db_player: DBPlayerDependency
):
    db_role = await session.get(PlayerRole, (payload.role, login))
    if not db_role:
        raise HTTPException(status_code=404, detail="Role is not assigned to this player")

    if db_player.preferred_role == payload.role:
        db_player.preferred_role = None
        session.add(db_player)

    await session.delete(db_role)
    await session.commit()


@router.post("/{login}/restriction/add", dependencies=[Depends(verify_admin)])
async def add_restriction(
    *,
    session: SessionDependency,
    login: PlayerLogin,
    payload: RestrictionCastingPayload,
    _: DBPlayerDependency
):
    db_restriction = PlayerRestriction(
        expires=payload.expires,
        kind=payload.restriction,
        login=login
    )
    session.add(db_restriction)
    await session.commit()


@router.delete("/{login}/restriction/remove", dependencies=[Depends(verify_admin)])
async def remove_restriction(*, session: SessionDependency, payload: RestrictionRemovalPayload):
    db_restriction = await session.get(PlayerRestriction, payload.restriction_id)
    if not db_restriction:
        raise HTTPException(status_code=404, detail="Not found")

    db_restriction.expires = datetime.now(UTC)
    session.add(db_restriction)
    await session.commit()


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
    await session.exec(update_query)  # type: ignore

    await session.commit()


@router.post("/{login}/avatar/update")
async def update_avatar(
    *,
    session: SessionDependency,
    login: PlayerLogin,
    image: UploadFile,
    client_login: MandatoryPlayerLoginDependency
):
    raise HTTPException(status_code=501, detail="Avatar upload is not yet available")
