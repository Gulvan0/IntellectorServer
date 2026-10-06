from dataclasses import dataclass
from html import escape
from types import NoneType
from typing import Any, get_args, get_origin
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
        for ancestor_class in cls.__mro__:
            for base in vars(ancestor_class).get("__orig_bases__", ()):
                origin = get_origin(base)
                if isinstance(origin, type) and issubclass(origin, OutgoingEvent):
                    return get_args(base)
        raise ValueError(f'{cls.__name__} does not parametrize OutgoingEvent')

    @classmethod
    def _base_type_variables(cls) -> tuple[type[PayloadType], type[TargetChannelType]]:
        return cls._type_variables()  # type: ignore

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
            channel=self.target_channel.model_dump(mode="json") if not isinstance(self.target_channel, NoneType) else None,
            body=self.payload.model_dump(mode="json") if not isinstance(self.payload, NoneType) else None
        )


class RefreshEvent[PayloadType: BaseModel, RefreshedChannelType: EventChannel](OutgoingEvent[PayloadType, RefreshedChannelType]):
    @classmethod
    def title(cls) -> str:
        refreshed_channel: type[RefreshedChannelType] = cls._type_variables()[1]
        channel_group = refreshed_channel.group
        return f"Channel Refresh: <code>{escape(channel_group)}</code>"

    @classmethod
    def description(cls) -> str:
        refreshed_channel: type[RefreshedChannelType] = cls._type_variables()[1]
        channel_group = refreshed_channel.group
        return f"Delivers the actual state of a <code>{escape(channel_group)}</code> channel (for example, as a response to subscribing to it)"
