from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from random import choice, randint, random
from rstr import lowercase, normal, printable

from src.common.models import Id, IdList, UserRefWithNickname
from src.common.time_control import TimeControlKind


@dataclass
class SampleTimeControl:
    kind: TimeControlKind
    start_seconds: int = 0
    increment_seconds: int = 0


def uint(max_value: int = 999999) -> int:
    return randint(1, max_value)


def sample_id() -> Id:
    return Id(id=uint())


def ids() -> list[Id]:
    return [sample_id() for _ in range(3)]


def id_list() -> IdList:
    return IdList(ids=[uint() for _ in range(randint(1, 3))])


def id_lists() -> list[IdList]:
    return [id_list(), id_list(), IdList(ids=[])]


def boolean() -> bool:
    return random() < 0.5


def string(min_length: int = 5, max_length: int = 15) -> str:
    return printable(min_length, max_length, include=' ')


def underscore_str(min_length: int = 10, max_length: int = 15) -> str:
    return lowercase(min_length, max_length, include="_")


def nickname() -> str:
    return normal(10, 20)


def user_ref_with_nickname() -> UserRefWithNickname:
    return UserRefWithNickname(
        user_ref=underscore_str(),
        nickname=nickname()
    )


def guest_ref_with_nickname() -> UserRefWithNickname:
    guest_id = uint()
    return UserRefWithNickname(
        user_ref=f"_{guest_id}",
        nickname=f"Guest {guest_id}"
    )


def user_ref_with_nickname_list(count: int = 3) -> list[UserRefWithNickname]:
    return [user_ref_with_nickname(), guest_ref_with_nickname()][:count] + [
        user_ref_with_nickname() if boolean() else guest_ref_with_nickname()
        for _ in range(count - 2)
    ]


def bot_user_ref_with_nickname() -> UserRefWithNickname:
    return UserRefWithNickname(
        user_ref="+anaconda",
        nickname="Anaconda (bot)"
    )


def __offset_datetime(min_offset_days: int = 0, max_offset_days: int = 0, min_offset_secs: float = 0, max_offset_secs: float = 0) -> datetime:
    days_frame_length = max_offset_days - min_offset_days
    days = min_offset_days + random() * days_frame_length

    secs_frame_length = max_offset_secs - min_offset_secs
    secs = min_offset_secs + random() * secs_frame_length
    return datetime.now(UTC) + timedelta(days=days, seconds=secs)


def past_datetime(min_offset_days: int = 0, max_offset_days: int = 0, min_offset_secs: float = 0, max_offset_secs: float = 0) -> datetime:
    return __offset_datetime(-max_offset_days, -min_offset_days, -min_offset_secs, -max_offset_secs)


def future_datetime(min_offset_days: int = 0, max_offset_days: int = 0, min_offset_secs: float = 0, max_offset_secs: float = 0) -> datetime:
    return __offset_datetime(min_offset_days, max_offset_days, min_offset_secs, max_offset_secs)


def datetime_after(origin: datetime, max_delay_seconds: float = 134, min_delay_seconds: float = 0) -> datetime:
    frame_length = max_delay_seconds - min_delay_seconds
    return origin + timedelta(seconds=min_delay_seconds + random() * frame_length)


def time_control_kind(exclude_correspondence: bool = False) -> TimeControlKind:
    selection = TimeControlKind.non_correspondence_kinds() if exclude_correspondence else TimeControlKind.all_kinds()
    return choice(selection)


def time_control(kind: TimeControlKind | None = None, exclude_correspondence: bool = False) -> SampleTimeControl:
    if not kind:
        kind = time_control_kind(exclude_correspondence)

    match kind:
        case TimeControlKind.CORRESPONDENCE:
            return SampleTimeControl(kind)
        case TimeControlKind.HYPERBULLET:
            max_previous_tier_determinant = 0
            max_determinant = 59
        case TimeControlKind.BULLET:
            max_previous_tier_determinant = 59
            max_determinant = 179
        case TimeControlKind.BLITZ:
            max_previous_tier_determinant = 179
            max_determinant = 599
        case TimeControlKind.RAPID:
            max_previous_tier_determinant = 599
            max_determinant = 3599
        case TimeControlKind.CLASSIC:
            return SampleTimeControl(kind, randint(3600, 21600), randint(0, 600))

    start_seconds = randint(0, max_determinant)
    this_tier_increment_cap = (max_determinant - start_seconds) // 40
    prev_tier_increment_cap = (max_previous_tier_determinant - start_seconds) // 40
    increment_seconds = randint(max(0, 1 + prev_tier_increment_cap), this_tier_increment_cap)
    return SampleTimeControl(kind, start_seconds, increment_seconds)
