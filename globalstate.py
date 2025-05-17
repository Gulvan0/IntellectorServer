from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from models.config import MainConfig, SecretConfig
from utils.config_loader import retrieve_config


@dataclass(frozen=True)
class UserReference:
    reference: str

    @classmethod
    def logged(cls, login: str) -> UserReference:
        return UserReference(login)

    @classmethod
    def guest(cls, id: int) -> UserReference:
        return UserReference(f"_{id}")

    def is_guest(self) -> bool:
        return self.reference.startswith("_")

    @property
    def login(self) -> str:
        assert not self.is_guest()
        return self.reference

    @property
    def guest_id(self) -> int:
        assert self.is_guest()
        return int(self.reference[1:])

    def __str__(self) -> str:
        return self.reference


class GlobalState:
    token_to_user: dict[str, UserReference] = dict()
    last_guest_id: int = 0
    ws_subscribers: dict[str, list[Any]] = dict()  # Channel as a key # TODO: Provide specific type
    main_config: MainConfig = retrieve_config('main', MainConfig)
    secret_config: SecretConfig = retrieve_config('secret', SecretConfig)

    @classmethod
    def add_guest(cls, token: str) -> int:
        cls.last_guest_id += 1
        cls.token_to_user[token] = UserReference.guest(cls.last_guest_id)
        return cls.last_guest_id

    @classmethod
    def add_logged(cls, token: str, login: str) -> None:
        cls.token_to_user[token] = UserReference.logged(login)
