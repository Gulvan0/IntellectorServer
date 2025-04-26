from pydantic import BaseModel


class KeepAliveParams(BaseModel):
    beat_interval_ms: int
    timeout_ms: int


class EloParams(BaseModel):
    default: int
    max_log_slope: float
    normal_log_slope: float
    calibration_games: int


class RuleParams(BaseModel):
    secs_added_manually: int


class MainConfig(BaseModel):
    min_client_build: int
    server_build: int
    keep_alive: KeepAliveParams
    elo: EloParams
    rules: RuleParams


class DBParams(BaseModel):
    host: str
    port: int
    user: str
    password: str
    database: str

    @property
    def url(self) -> str:
        return f"mysql://{self.user}:{self.password}@{self.host}:{self.port}/{self.database}"


class DiscordParams(BaseModel):
    webhook_url: str


class TelegramParams(BaseModel):
    token: str
    admin_chat_id: int


class VkParams(BaseModel):
    token: str
    community_chat_id: int


class IntegrationParams(BaseModel):
    discord: DiscordParams
    telegram: TelegramParams
    vk: VkParams


class SSLParams(BaseModel):
    cert_path: str
    key_path: str


class SecretConfig(BaseModel):
    db: DBParams
    integrations: IntegrationParams
    ssl: SSLParams | None = None
