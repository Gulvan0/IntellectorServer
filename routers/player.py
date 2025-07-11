from datetime import datetime, UTC
from typing import Annotated

import bcrypt  # type: ignore
from fastapi import APIRouter, HTTPException, UploadFile, Depends
from pydantic import StringConstraints
from sqlalchemy import update
from sqlalchemy.sql.functions import count
from sqlmodel import col, desc, select

from models import (
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
from utils.datatypes import StudyPublicity, UserReference, UserRole
from utils.query import not_expired
from .utils import MutableStateDependency, OptionalPlayerLoginDependency, PlayerLogin, verify_admin, MandatoryPlayerLoginDependency, SessionDependency


router = APIRouter(prefix="/player")


@router.get("/{login}", response_model=PlayerPublic)
async def get_player(*, login: PlayerLogin, session: SessionDependency, state: MutableStateDependency, client_login: OptionalPlayerLoginDependency):
    db_player = session.get(Player, login)

    if not db_player:
        raise HTTPException(status_code=404, detail="Player not found")

    is_friend = False
    if client_login and client_login != login:
        is_friend = session.get(PlayerFollowedPlayer, (client_login, login)) is not None

    studies_selection_query = select(
        count(col(Study.id))
    ).where(
        Study.author_login == login
    )
    if client_login != login:
        studies_selection_query = studies_selection_query.where(
            col(Study.publicity).in_([StudyPublicity.PROFILE_AND_LINK_ONLY, StudyPublicity.PUBLIC])
        )
    studies_cnt = session.exec(studies_selection_query)

    followed_players = list(session.exec(select(
        PlayerFollowedPlayer.followed_login
    ).where(
        PlayerFollowedPlayer.follower_login == login
    )))

    db_roles = session.exec(select(
        PlayerRole
    ).where(
        PlayerRole.login == login
    ).order_by(
        desc(PlayerRole.granted_at)
    ))
    roles: list[PlayerRolePublic] = []
    for db_role in db_roles:
        is_main = db_role.role == db_player.preferred_role
        role = PlayerRolePublic(
            is_main=is_main,
            **PlayerRoleBase.model_validate(db_role).model_dump()
        )
        if is_main:
            roles.insert(0, role)
        else:
            roles.append(role)

    db_restrictions = session.exec(select(
        PlayerRestriction
    ).where(
        PlayerRestriction.login == login,
        not_expired(PlayerRestriction.expires)
    ))
    restrictions = [
        PlayerRestrictionPublic(**PlayerRestrictionBase.model_validate(db_restriction).model_dump())
        for db_restriction in db_restrictions
    ]

    user_ref = UserReference.logged(login)
    player = PlayerPublic(
        is_friend=is_friend,
        status=state.get_user_status_in_channel(user_ref, IncomingChallengesEventChannel(user_ref=login)),
        per_time_control_stats=None,  # TODO (after the game models are ready)
        total_stats=None,  # TODO (after the game models are ready)
        studies_cnt=studies_cnt,
        followed_players=followed_players,
        roles=roles,
        restrictions=restrictions,
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
