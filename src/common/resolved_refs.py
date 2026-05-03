from dataclasses import dataclass, field

from common.models import UserRefWithNickname
from common.user_ref import UserReference


@dataclass
class ResolvedRefs:
    mapping: dict[str, UserRefWithNickname] = field(default_factory=dict)

    def get(self, user_ref: str | UserReference) -> UserRefWithNickname:
        ref_object = UserReference(user_ref) if isinstance(user_ref, str) else user_ref
        ref_str = ref_object.reference
        return self.mapping.get(ref_str) or UserRefWithNickname(user_ref=ref_str, nickname=ref_object.pretty())

    def set(self, user_ref: str, user_ref_with_nickname: UserRefWithNickname) -> None:
        self.mapping[user_ref] = user_ref_with_nickname

    def all_values(self) -> list[UserRefWithNickname]:
        return list(self.mapping.values())
