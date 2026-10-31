from dataclasses import dataclass

from common.bots import LEGACY_ANACONDA_NAME, registered_bot_display_name


@dataclass(frozen=True)
class UserReference:
    reference: str

    @classmethod
    def logged(cls, login: str) -> UserReference:
        return UserReference(login)

    @classmethod
    def guest(cls, id: int) -> UserReference:
        return UserReference(f"_{id}")

    @classmethod
    def bot(cls, name: str) -> UserReference:
        return UserReference(f"+{name}")

    def is_guest(self) -> bool:
        return self.reference.startswith("_")

    def is_bot(self) -> bool:
        return self.reference.startswith("+")

    def is_player(self) -> bool:
        return self.reference[0] not in ("+", "_")

    @property
    def login(self) -> str:
        assert self.is_player()
        return self.reference

    @property
    def guest_id(self) -> int:
        assert self.is_guest()
        return int(self.reference[1:])

    @property
    def bot_name(self) -> str:
        assert self.is_bot()
        return self.reference[1:]

    def is_registered_bot(self) -> bool:
        return self.is_bot() and registered_bot_display_name(self.bot_name) is not None

    def __str__(self) -> str:
        return self.reference

    def pretty(self) -> str:
        if self.is_guest():
            return f"Guest {self.guest_id}"
        elif self.is_bot():
            if self.bot_name == LEGACY_ANACONDA_NAME:
                return f"{LEGACY_ANACONDA_NAME} (Bot)"
            return f"{registered_bot_display_name(self.bot_name) or self.bot_name.title()} (Bot)"
        else:
            return self.login
