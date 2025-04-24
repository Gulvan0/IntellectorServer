from datetime import datetime, UTC
from typing import Annotated

import bcrypt
from fastapi import APIRouter, HTTPException, Depends, UploadFile
from pydantic import StringConstraints
from sqlalchemy import update
from sqlalchemy.engine import TupleResult
from sqlalchemy.sql.functions import count
from sqlmodel import col, desc, or_, select, Session

from globalstate import GlobalState
from models import PlayerBase, PlayerFollowedPlayer, PlayerPublic, Player, PlayerRestriction, PlayerRestrictionBase, PlayerRestrictionPublic, PlayerRole, PlayerRoleBase, PlayerRolePublic, PlayerUpdate, Study
from utils.datatypes import StudyPublicity, UserRestrictionKind, UserRole
from .utils import get_session, OPTIONAL_USER_TOKEN_HEADER_SCHEME, USER_TOKEN_HEADER_SCHEME

router = APIRouter(prefix="/player")


@router.get("/{login}", response_model=PlayerPublic)
async def get_player(*, session: Session = Depends(get_session), login: Annotated[str, StringConstraints(to_lower=True)], token: str | None = Depends(OPTIONAL_USER_TOKEN_HEADER_SCHEME)):
    if token is not None:
        client_login = GlobalState.token_to_login.get(token)
        if not client_login:
            raise HTTPException(status_code=401, detail="Invalid token")
    else:
        client_login = None

    db_player = session.get(Player, login)

    if not db_player:
        raise HTTPException(status_code=404, detail="Player not found")

    is_friend = False
    if client_login and client_login != login:
        is_friend = session.get(PlayerFollowedPlayer, (client_login, login)) is not None

    studies_selection_query = select(  # noqa
        count(Study.id)
    ).where(
        Study.author_login == login
    )
    if client_login != login:
        studies_selection_query = studies_selection_query.where(
            col(Study.publicity).in_([StudyPublicity.PROFILE_AND_LINK_ONLY, StudyPublicity.PUBLIC])
        )
    studies_cnt = session.exec(studies_selection_query)  # noqa

    followed_players = list(session.exec(select(  # noqa
        PlayerFollowedPlayer.followed_login
    ).where(
        PlayerFollowedPlayer.follower_login == login
    )))

    db_roles: TupleResult[PlayerRole] = session.exec(select(  # noqa
        PlayerRole
    ).where(
        PlayerRole.login == login
    ).order_by(
        desc(PlayerRole.granted_at)
    ))
    roles = []
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

    db_restrictions = session.exec(select(  # noqa
        PlayerRestriction
    ).where(
        PlayerRestriction.login == login,
        or_(
            PlayerRestriction.expires == None,
            PlayerRestriction.expires > datetime.now(UTC)
        )
    ))
    restrictions = [
        PlayerRestrictionPublic(**PlayerRestrictionBase.model_validate(db_restriction).model_dump())
        for db_restriction in db_restrictions
    ]

    player = PlayerPublic(
        is_friend=is_friend,
        status=None,  # TODO (after the websocket processing is introduced)
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
async def update_player(*, session: Session = Depends(get_session), login: Annotated[str, StringConstraints(to_lower=True)], token: str = Depends(USER_TOKEN_HEADER_SCHEME), player: PlayerUpdate):
    client_login = GlobalState.token_to_login.get(token)
    if not client_login:
        raise HTTPException(status_code=401, detail="Invalid token")

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


@router.post("/follow")
async def follow(*, session: Session = Depends(get_session), login: Annotated[str, StringConstraints(to_lower=True)], token: str = Depends(USER_TOKEN_HEADER_SCHEME)):
    client_login = GlobalState.token_to_login.get(token)
    if not client_login:
        raise HTTPException(status_code=401, detail="Invalid token")

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


@router.post("/unfollow")
async def unfollow(*, session: Session = Depends(get_session), login: Annotated[str, StringConstraints(to_lower=True)], token: str = Depends(USER_TOKEN_HEADER_SCHEME)):
    client_login = GlobalState.token_to_login.get(token)
    if not client_login:
        raise HTTPException(status_code=401, detail="Invalid token")

    if client_login == login:
        raise HTTPException(status_code=400, detail="Cannot unfollow self")

    db_player_followed_player = session.get(PlayerFollowedPlayer, (client_login, login))
    if not db_player_followed_player:
        raise HTTPException(status_code=404, detail="Player is not followed or doesn't exist")

    session.delete(db_player_followed_player)
    session.commit()


@router.post("/role/add")
async def add_role(*, session: Session = Depends(get_session), login: Annotated[str, StringConstraints(to_lower=True)], role: UserRole, token: str = Depends(USER_TOKEN_HEADER_SCHEME)):
    client_login = GlobalState.token_to_login.get(token)
    if not client_login:
        raise HTTPException(status_code=401, detail="Invalid token")

    if not session.get(PlayerRole, (UserRole.ADMIN, client_login)):
        raise HTTPException(status_code=403, detail="Forbidden")

    if not session.get(Player, login):
        raise HTTPException(status_code=404, detail="Player not found")

    if session.get(PlayerRole, (role, login)):
        raise HTTPException(status_code=400, detail="Role is already present")

    db_role = PlayerRole(
        role=role,
        login=login
    )
    session.add(db_role)
    session.commit()


@router.delete("/role/remove")
async def remove_role(*, session: Session = Depends(get_session), login: Annotated[str, StringConstraints(to_lower=True)], role: UserRole, token: str = Depends(USER_TOKEN_HEADER_SCHEME)):
    client_login = GlobalState.token_to_login.get(token)
    if not client_login:
        raise HTTPException(status_code=401, detail="Invalid token")

    if not session.get(PlayerRole, (UserRole.ADMIN, client_login)):
        raise HTTPException(status_code=403, detail="Forbidden")

    db_player = session.get(Player, login)
    if not db_player:
        raise HTTPException(status_code=404, detail="Player not found")

    db_role = session.get(PlayerRole, (role, login))
    if not db_role:
        raise HTTPException(status_code=404, detail="Role is not assigned to this player")

    if db_player.preferred_role == role:
        db_player.preferred_role = None
        session.add(db_player)

    session.delete(db_role)
    session.commit()


@router.post("/restriction/add")
async def add_restriction(*, session: Session = Depends(get_session), login: Annotated[str, StringConstraints(to_lower=True)], restriction: UserRestrictionKind, expires: datetime | None = None, token: str = Depends(USER_TOKEN_HEADER_SCHEME)):
    client_login = GlobalState.token_to_login.get(token)
    if not client_login:
        raise HTTPException(status_code=401, detail="Invalid token")

    if not session.get(PlayerRole, (UserRole.ADMIN, client_login)):
        raise HTTPException(status_code=403, detail="Forbidden")

    if not session.get(Player, login):
        raise HTTPException(status_code=404, detail="Player not found")

    db_restriction = PlayerRestriction(
        expires=expires,
        kind=restriction,
        login=login
    )
    session.add(db_restriction)
    session.commit()


@router.delete("/restriction/remove")
async def remove_restriction(*, session: Session = Depends(get_session), restriction_id: int, token: str = Depends(USER_TOKEN_HEADER_SCHEME)):
    client_login = GlobalState.token_to_login.get(token)
    if not client_login:
        raise HTTPException(status_code=401, detail="Invalid token")

    if not session.get(PlayerRole, (UserRole.ADMIN, client_login)):
        raise HTTPException(status_code=403, detail="Forbidden")

    db_restriction = session.get(PlayerRestriction, restriction_id)
    if not db_restriction:
        raise HTTPException(status_code=404, detail="Not found")

    db_restriction.expires = datetime.now(UTC)
    session.add(db_restriction)
    session.commit()


@router.delete("/restriction/purge")
async def purge_restrictions(*, session: Session = Depends(get_session), login: Annotated[str, StringConstraints(to_lower=True)], restriction_kind: UserRestrictionKind | None = None, token: str = Depends(USER_TOKEN_HEADER_SCHEME)):
    client_login = GlobalState.token_to_login.get(token)
    if not client_login:
        raise HTTPException(status_code=401, detail="Invalid token")

    if not session.get(PlayerRole, (UserRole.ADMIN, client_login)):
        raise HTTPException(status_code=403, detail="Forbidden")

    update_query = update(PlayerRestriction).values(expires=datetime.now(UTC)).where(PlayerRestriction.login == login)
    if restriction_kind:
        update_query = update_query.where(PlayerRestriction.kind == restriction_kind)
    session.exec(update_query)

    session.commit()


@router.post("/avatar/update")
async def update_avatar(*, session: Session = Depends(get_session), login: Annotated[str, StringConstraints(to_lower=True)], image: UploadFile, token: str = Depends(USER_TOKEN_HEADER_SCHEME)):
    raise HTTPException(status_code=501, detail="Avatar upload is not yet available")
