from datetime import datetime
from enum import Enum, auto

from board.samples import non_default_starting_sip
from challenge.datatypes import ChallengeAcceptorColor, ChallengeKind
from challenge.models import ChallengeFischerTimeControlPublic, ChallengePublic

from common.models import UserRefWithNickname
from common.samples import boolean, datetime_after, past_datetime, time_control, uint, user_ref_with_nickname
from common.time_control import TimeControlKind
from game.samples import game


class ChallengeState(Enum):
    ACTIVE = auto()
    FULFILLED = auto()
    CANCELLED = auto()


def challenge(
    kind: ChallengeKind = ChallengeKind.DIRECT,
    state: ChallengeState = ChallengeState.FULFILLED,
    rated: bool | None = None,
    correspondence: bool | None = None,
    caller: UserRefWithNickname | None = None,
    callee: UserRefWithNickname | None = None,
    created_at: datetime | None = None
) -> ChallengePublic:
    if rated is None:
        rated = boolean()

    if not caller:
        caller = user_ref_with_nickname()
    if not callee:
        callee = user_ref_with_nickname() if kind == ChallengeKind.DIRECT else None
    acceptor = callee or user_ref_with_nickname()

    if rated:
        acceptor_color = ChallengeAcceptorColor.RANDOM
        players = (caller, acceptor) if boolean() else (acceptor, caller)
    else:
        if boolean():
            acceptor_color = ChallengeAcceptorColor.WHITE
            players = (acceptor, caller)
        else:
            acceptor_color = ChallengeAcceptorColor.BLACK
            players = (caller, acceptor)

    if correspondence:
        sample_time_control = time_control(TimeControlKind.CORRESPONDENCE)
    else:
        sample_time_control = time_control(exclude_correspondence=correspondence is not None)

    custom_starting_sip = None
    if not rated:
        custom_starting_sip = non_default_starting_sip()

    if not created_at:
        created_at = past_datetime(min_offset_days=3, max_offset_days=200)

    return ChallengePublic(
        acceptor_color=acceptor_color,
        custom_starting_sip=custom_starting_sip,
        rated=rated,
        id=uint(),
        created_at=created_at,
        caller=caller,
        callee=callee,
        kind=kind,
        time_control_kind=sample_time_control.kind,
        active=state == ChallengeState.ACTIVE,
        fischer_time_control=ChallengeFischerTimeControlPublic(
            start_seconds=sample_time_control.start_seconds,
            increment_seconds=sample_time_control.increment_seconds
        ) if sample_time_control.kind != TimeControlKind.CORRESPONDENCE else None,
        resulting_game=game(
            players=players,
            time_control=sample_time_control,
            rated=rated,
            custom_starting_sip=custom_starting_sip,
            external_uploader_login=None,
            finished=True,
            started_at=datetime_after(created_at, min_delay_seconds=30, max_delay_seconds=8 * 60)
        ) if state == ChallengeState.FULFILLED else None
    )


def minimal_representative_challenges() -> list[ChallengePublic]:
    return [
        challenge(ChallengeKind.DIRECT, ChallengeState.FULFILLED, rated=True, correspondence=False),
        challenge(ChallengeKind.LINK_ONLY, ChallengeState.ACTIVE, rated=False, correspondence=False),
        challenge(ChallengeKind.PUBLIC, ChallengeState.CANCELLED, rated=False, correspondence=True),
    ]


def incoming_challenges(count: int = 2) -> list[ChallengePublic]:
    callee = user_ref_with_nickname()
    return [
        challenge(ChallengeKind.DIRECT, ChallengeState.ACTIVE, rated=boolean(), correspondence=boolean(), callee=callee)
        for _ in range(count)
    ]


def outgoing_challenges(count: int = 3) -> list[ChallengePublic]:
    caller = user_ref_with_nickname()
    return [
        challenge(ChallengeKind.DIRECT, ChallengeState.ACTIVE, rated=True, correspondence=False, caller=caller),
        challenge(ChallengeKind.LINK_ONLY, ChallengeState.ACTIVE, rated=False, correspondence=False, caller=caller),
        challenge(ChallengeKind.PUBLIC, ChallengeState.ACTIVE, rated=False, correspondence=True, caller=caller),
    ][:count] + [challenge(caller=caller) for _ in range(count - 3)]


def active_public_challenges(count: int = 3) -> list[ChallengePublic]:
    return [
        challenge(ChallengeKind.PUBLIC, ChallengeState.ACTIVE, rated=boolean(), correspondence=boolean())
        for _ in range(count)
    ]
