from dataclasses import dataclass
from html import escape
from types import NoneType
from typing import Any, get_args
from pydantic import BaseModel

from common.models import Id, IdList
from common.samples import id_lists, ids
from pubsub.models.channel import EventChannel
from utils.string import camel_to_snake


@dataclass
class OutgoingEvent[PayloadType: BaseModel | None, TargetChannelType: EventChannel]:
    payload: PayloadType
    target_channel: TargetChannelType

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
    def payload_examples(cls) -> list[PayloadType]:
        return []

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
    def payload_schema(cls) -> dict[str, Any] | None:
        payload_type: type[BaseModel] | None = cls.payload_type()  # type: ignore
        if payload_type:
            return payload_type.model_json_schema()
        return None

    @classmethod
    def payload_examples_json(cls) -> list[dict[str, Any] | None]:
        payload_type: type[BaseModel] | None = cls.payload_type()  # type: ignore
        if payload_type:
            if payload_type is Id:
                payload_examples: list[Any] = ids()
            elif payload_type is IdList:
                payload_examples = id_lists()
            else:
                payload_examples = cls.payload_examples()

            return [
                example.model_dump() if example is not None else None
                for example in payload_examples
            ]
        else:
            return [None]

    def to_dict(self) -> dict[str, Any]:
        return dict(
            event=self.name(),
            channel=self.target_channel.model_dump() if not isinstance(self.target_channel, NoneType) else None,
            body=self.payload.model_dump() if not isinstance(self.payload, NoneType) else None
        )


class RefreshEvent[PayloadType: BaseModel, RefreshedChannelType: EventChannel](OutgoingEvent[PayloadType, RefreshedChannelType]):
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
