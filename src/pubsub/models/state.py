from src.common.models import UserRefWithNickname
from src.utils.custom_model import CustomModel


# TODO: Move all state refresh models there


class SubscriberListEventChannelState(CustomModel):
    subscribers: list[UserRefWithNickname]
