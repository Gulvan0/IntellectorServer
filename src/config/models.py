from src.utils.custom_model import CustomModel


class KeepAliveParams(CustomModel):
    beat_interval_ms: int
    timeout_ms: int


class EloParams(CustomModel):
    default: int
    max_log_slope: float
    normal_log_slope: float
    calibration_games: int


class RuleParams(CustomModel):
    secs_added_manually: int


class LimitParams(CustomModel):
    max_total_active_challenges: int
    max_same_callee_active_challenges: int


class MainConfig(CustomModel):
    min_client_build: int
    server_build: int
    keep_alive: KeepAliveParams
    elo: EloParams
    rules: RuleParams
    limits: LimitParams


class DBParams(CustomModel):
    host: str
    port: int
    user: str
    password: str
    database: str

    @property
    def url(self) -> str:
        return f"mysql+aiomysql://{self.user}:{self.password}@{self.host}:{self.port}/{self.database}"


class DiscordParams(CustomModel):
    webhook_url: str


class TelegramParams(CustomModel):
    token: str
    admin_chat_id: int


class VkParams(CustomModel):
    token: str
    community_chat_id: int


class IntegrationParams(CustomModel):
    discord: DiscordParams
    telegram: TelegramParams
    vk: VkParams


class SSLParams(CustomModel):
    cert_path: str
    key_path: str


class SecretConfig(CustomModel):
    db: DBParams
    integrations: IntegrationParams
    ssl: SSLParams | None = None
