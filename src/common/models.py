from common.datatypes import UserStatus
from utils.custom_model import CustomModel


class Id(CustomModel):
    id: int


class IdList(CustomModel):
    ids: list[int]


class UserRefWithNickname(CustomModel):
    user_ref: str
    nickname: str


class UserActivity(CustomModel):
    status: UserStatus
    last_active_unixsecs: int

    def compose_with(self, other: UserActivity) -> UserActivity:
        return UserActivity(
            status=UserStatus.max(self.status, other.status),
            last_active_unixsecs=max(self.last_active_unixsecs, other.last_active_unixsecs)
        )
