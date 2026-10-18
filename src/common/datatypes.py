from enum import StrEnum, auto


class UserStatus(StrEnum):
    PLAYING = auto()  # online and playing a game that isn't correspondence
    ONLINE = auto()
    AWAY = auto()
    OFFLINE = auto()

    @classmethod
    def max(cls, *statuses: UserStatus) -> UserStatus:
        for possible_status in (UserStatus.PLAYING, UserStatus.ONLINE, UserStatus.AWAY):
            if possible_status in statuses:
                return possible_status
        return UserStatus.OFFLINE
