from dataclasses import dataclass
from html import escape
from types import NoneType
from typing import get_args
from pydantic import BaseModel

from src.pubsub.models.channel import EventChannel
from src.utils.string import camel_to_snake


@dataclass
class OutgoingEvent[PayloadType: BaseModel | None, TargetChannelType: EventChannel | None]:
    payload: PayloadType

    @classmethod
    def name(cls) -> str:
        return camel_to_snake(cls.__name__)

    @classmethod
    def title(cls) -> str:
        return " ".join(map(str.capitalize, cls.name().split("_")))

    @classmethod
    def description(cls) -> str:
        return "Not yet documented"

    @classmethod
    def payload_example(cls) -> PayloadType | None:
        return None

    @classmethod
    def _type_variables(cls) -> tuple[type, ...]:
        origin = getattr(cls, "__orig_class__", None)
        if origin is None:
            raise ValueError('Origin is undefined')
        return get_args(origin)

    @classmethod
    def _base_type_variables(cls) -> tuple[type[PayloadType], type[TargetChannelType]]:
        iterated_class: type | None = cls
        while iterated_class and iterated_class is not OutgoingEvent:
            iterated_class = iterated_class.__base__
        assert isinstance(iterated_class, OutgoingEvent)
        return iterated_class._type_variables()

    @classmethod
    def payload_type(cls) -> type[PayloadType]:
        return cls._base_type_variables()[0]

    @classmethod
    def target_channel_type(cls) -> type[TargetChannelType]:
        return cls._base_type_variables()[1]

    @classmethod
    def payload_schema(cls) -> dict | None:
        payload_type: type[BaseModel] | None = cls.payload_type()  # type: ignore
        if payload_type:
            return payload_type.model_json_schema()
        return None

    @classmethod
    def payload_example_json(cls) -> dict | None:
        payload_example = cls.payload_example()
        if payload_example is None:
            return None
        return payload_example.model_dump()

    def to_dict(self, channel: TargetChannelType) -> dict:
        return dict(
            event=self.name(),
            channel=channel.model_dump() if not isinstance(channel, NoneType) else None,
            body=self.payload.model_dump() if not isinstance(self.payload, NoneType) else None
        )


class RefreshEvent[PayloadType: BaseModel, RefreshedChannelType: EventChannel](OutgoingEvent[PayloadType, None]):
    @classmethod
    def name(cls) -> str:
        refreshed_channel: type[RefreshedChannelType] = cls._type_variables()[1]
        return f"refresh.{refreshed_channel.channel_group}"

    @classmethod
    def title(cls) -> str:
        refreshed_channel: type[RefreshedChannelType] = cls._type_variables()[1]
        channel_group = refreshed_channel.channel_group
        return f"Channel Refresh: <code>{escape(channel_group)}</code>"

    @classmethod
    def description(cls) -> str:
        refreshed_channel: type[RefreshedChannelType] = cls._type_variables()[1]
        channel_group = refreshed_channel.channel_group
        return f"Delivers the actual state of a <code>{escape(channel_group)}</code> channel (for example, as a response to subscribing to it)"
