from pubsub.models.channel import SubEligibleEventChannel
from utils.custom_model import CustomModel


class SubUnsubPayload(CustomModel):
    channel: SubEligibleEventChannel
