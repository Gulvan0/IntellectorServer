from pydantic import BaseModel


def model_cast_optional[TargetModelType: BaseModel](source: BaseModel | None, target: type[TargetModelType]) -> TargetModelType | None:
    return target.model_construct(**source.model_dump()) if source else None


def model_cast[TargetModelType: BaseModel](source: BaseModel, target: type[TargetModelType]) -> TargetModelType:
    return target.model_construct(**source.model_dump())
