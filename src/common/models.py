from src.utils.custom_model import CustomModel


class EmptyModel(CustomModel):
    pass


class Id(CustomModel):
    id: int
