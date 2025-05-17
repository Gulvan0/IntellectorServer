from datetime import datetime, UTC

from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import and_, col, or_, select, Session

from globalstate import GlobalState
from models import Challenge, ChallengeCreateDirect, ChallengeCreateOpen, ChallengePublic, Player, PlayerRestriction
from routers.utils import get_session, OPTIONAL_USER_TOKEN_HEADER_SCHEME
from rules import DEFAULT_STARTING_SIP, Position
from utils.datatypes import ChallengeAcceptorColor, ChallengeKind, UserRestrictionKind
from utils.query import exists, not_expired

router = APIRouter(prefix="/challenge")


# TODO: Challenge merging
# TODO: Cancel all outgoing when a game starts
# TODO: Don't create new challenges when a server is shutting down

# In some other places...
# TODO: Cancel all challenges when a server is shutting down
# TODO: Broadcast shutdown announcement to everyone


@router.post("/create/open", status_code=201, response_model=ChallengePublic)
async def create_open_challenge(*, session: Session = Depends(get_session), token: str = Depends(OPTIONAL_USER_TOKEN_HEADER_SCHEME), challenge: ChallengeCreateOpen):
    client = GlobalState.token_to_user.get(token)
    if not client:
        raise HTTPException(status_code=401, detail="Invalid token")

    if challenge.rated:
        if client.is_guest():
            challenge.rated = False
        else:
            is_banned = exists(session, select(
                PlayerRestriction
            ).where(
                PlayerRestriction.kind == UserRestrictionKind.RATED_GAMES,
                PlayerRestriction.login == client.login,
                not_expired(PlayerRestriction.expires)
            ))
            if is_banned:
                challenge.rated = False
            else:
                challenge.custom_starting_sip = None
                challenge.acceptor_color = ChallengeAcceptorColor.RANDOM

    if challenge.custom_starting_sip:
        if challenge.custom_starting_sip == DEFAULT_STARTING_SIP:
            challenge.custom_starting_sip = None
        elif not Position.from_sip(challenge.custom_starting_sip).is_valid_starting():
            raise HTTPException(status_code=400, detail="Invalid starting situation")

    if challenge.fischer_time_control is None:
        time_control_equality_conditions = [Challenge.fischer_time_control == None]
    else:
        time_control_equality_conditions = [
            Challenge.fischer_time_control != None,
            Challenge.fischer_time_control.start_seconds == challenge.fischer_time_control.start_seconds,  # type: ignore
            Challenge.fischer_time_control.increment_seconds == challenge.fischer_time_control.increment_seconds,  # type: ignore
        ]

    identical_challenge = session.exec(select(
        Challenge
    ).where(
        Challenge.active,
        Challenge.acceptor_color == challenge.acceptor_color,
        Challenge.caller_ref == client.reference,
        Challenge.rated == challenge.rated,
        Challenge.custom_starting_sip == challenge.custom_starting_sip,
        Challenge.kind == (ChallengeKind.LINK_ONLY if challenge.link_only else ChallengeKind.PUBLIC),
        *time_control_equality_conditions
    )).first()
    if identical_challenge:
        raise HTTPException(status_code=400, detail=f"Challenge already exists ({identical_challenge.id})")

    mergeable_kind_conditions = []
    if not challenge.link_only:
        mergeable_kind_conditions = [
            or_(
                Challenge.kind == ChallengeKind.PUBLIC,
                and_(
                    Challenge.kind == ChallengeKind.DIRECT,
                    Challenge.callee_ref == client.reference
                )
            )
        ]

    mergeable_challenge = session.exec(select(
        Challenge
    ).where(
        Challenge.active,
        Challenge.acceptor_color.mergeable_with(challenge.acceptor_color),
        Challenge.caller_ref != client.reference,
        Challenge.rated == challenge.rated,
        Challenge.custom_starting_sip == challenge.custom_starting_sip,
        *mergeable_kind_conditions,
        *time_control_equality_conditions
    ).order_by(
        col(Challenge.created_at)
    )).first()

    if mergeable_challenge:
        ...  # TODO: Merge
    else:
        ...  # TODO: create and challenge


@router.post("/create/direct", status_code=201, response_model=ChallengePublic)
async def create_direct_challenge(*, session: Session = Depends(get_session), token: str = Depends(OPTIONAL_USER_TOKEN_HEADER_SCHEME), challenge: ChallengeCreateDirect):
    client = GlobalState.token_to_user.get(token)
    if not client:
        raise HTTPException(status_code=401, detail="Invalid token")

    ...
    # TODO: validate sip (valid starting)
    # TODO: check ranked ban
    # TODO: check player exists (may also be guest!!)
    # TODO: check has no challenge towards this player
    # TODO: check not to himself
    # TODO: check player online and incorporate this info into the response
    # TODO: create

# TODO: Get challenge

# TODO: Delete challenge

# TODO: Get open challenges with pagination

# TODO: Get direct (both incoming and outgoing) challenges + expose for websocket

# TODO: Accept challenge - game starts

# TODO: Decline challenge - notification is sent
