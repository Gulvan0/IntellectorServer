from src.utils.custom_model import CustomModel


class Id(CustomModel):
    id: int


class IdList(CustomModel):
    ids: list[int]


class UserRefWithNickname(CustomModel):
    user_ref: str
    nickname: str
