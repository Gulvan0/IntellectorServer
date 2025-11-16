import os
from pathlib import Path

import yaml  # type: ignore
from pydantic import BaseModel


def _merge(common: dict, stage: dict) -> None:
    for key, stage_value in stage.items():
        common_value = common.get(key)
        if common_value and isinstance(common_value, dict):
            assert isinstance(stage_value, dict), f"Type conflict: {key} is not dict in stage config"
            _merge(common_value, stage_value)
            continue
        common[key] = stage_value


def load[ConfigType: BaseModel](name: str, config_type: type[ConfigType]) -> ConfigType:
    raw_config_content: dict = yaml.safe_load(Path(f'resources/config/{name}.yaml').read_text())
    cooked_config = raw_config_content.get("common", {})
    _merge(cooked_config, raw_config_content.get(os.getenv("STAGE"), {}))
    return config_type.model_validate(cooked_config)
