from src.pubsub.models.channel import SubEligibleEventChannel
from src.utils.custom_model import CustomModel


class SubUnsubPayload(CustomModel):
    channel: SubEligibleEventChannel
