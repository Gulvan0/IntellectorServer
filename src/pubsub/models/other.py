from pubsub.models.channel import SubEligibleEventChannel
from utils.custom_model import CustomModel


class SubUnsubPayload(CustomModel):
    channel: SubEligibleEventChannel


class SubUnsubManyPayload(CustomModel):
    channels: list[SubEligibleEventChannel]


class SessionPayload(CustomModel):
    token: str | None = None
    channels: list[SubEligibleEventChannel] = []
