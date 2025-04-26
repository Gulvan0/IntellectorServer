from models.config import MainConfig, SecretConfig
from utils.config_loader import retrieve_config


class GlobalState:
    token_to_login: dict[str, str] = dict()
    ws_subscribers: dict[str, ...] = dict()
    main_config: MainConfig = retrieve_config('main', MainConfig)
    secret_config: SecretConfig = retrieve_config('secret', SecretConfig)
