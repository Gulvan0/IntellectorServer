from sqlalchemy.engine import URL

from utils.custom_model import CustomModel


class KeepAliveParams(CustomModel):
    silence_check_interval_secs: int  # how often a silent connection is checked on
    max_client_silence_secs: int  # a connection silent for this long is closed
    away_after_secs: int  # a user without activity for this long is shown as away
    send_timeout_secs: int  # a connection that can't take a message in this time is dropped


class EloParams(CustomModel):
    default: int
    max_log_slope: float
    normal_log_slope: float
    calibration_games: int


class RuleParams(CustomModel):
    secs_added_manually: int
    first_move_deadline_secs: int  # for each of the two plies made before the clocks start
    external_first_move_deadline_secs: int
    heartbeat_stale_secs: int  # an external game's uploader that stayed silent this long is considered gone
    min_suspension_ttl_secs: int  # a suspended timed game is abandoned after at least this long without its uploader
    correspondence_suspension_ttl_secs: int


class LimitParams(CustomModel):
    max_total_active_challenges: int
    max_same_callee_active_challenges: int
    max_http_body_bytes: int
    max_ws_message_bytes: int
    max_guest_tokens: int
    db_pool_size: int
    db_pool_max_overflow: int


class RateLimitRule(CustomModel):
    max_requests: int  # also the largest burst
    window_secs: int  # the time it takes an emptied budget to refill


class RateLimitParams(CustomModel):
    http_by_ip: RateLimitRule  # every HTTP request from an IP
    general: RateLimitRule  # by user, or IP without a valid token: the routes not in any group below
    signin: RateLimitRule  # by IP
    signin_failures: RateLimitRule  # by login
    registration: RateLimitRule  # by IP
    guest: RateLimitRule  # by IP
    game_creation: RateLimitRule  # by user
    game_action: RateLimitRule  # by user: separate from the rest, so that nothing else can use up a player's moves
    chat: RateLimitRule  # by user
    write: RateLimitRule  # by user
    search: RateLimitRule  # by user
    ws_connect: RateLimitRule  # by IP
    ws_message: RateLimitRule  # by connection, pings included
    client_error: RateLimitRule  # by user, or IP without a valid token
    max_ws_connections_per_ip: int


class AntispamWindowDefinition(CustomModel):
    window_size_seconds: int
    max_messages: int


class MainConfig(CustomModel):
    keep_alive: KeepAliveParams
    elo: EloParams
    rules: RuleParams
    limits: LimitParams
    rate_limits: RateLimitParams
    vk_antispam_windows: list[AntispamWindowDefinition]


class DBParams(CustomModel):
    host: str
    port: int
    user: str
    password: str
    database: str

    @property
    def url(self) -> str:
        return f"mysql+aiomysql://{self.user}:{self.password}@{self.host}:{self.port}/{self.database}"

    def sync_url(self, database: str | None = None) -> URL:
        """For Alembic, which does not run on an asyncio driver. Built from parts, so that special characters of the password need no escaping"""
        return URL.create("mysql+pymysql", self.user, self.password, self.host, self.port, database or self.database)


class DiscordParams(CustomModel):
    webhook_url: str


class TelegramParams(CustomModel):
    token: str
    admin_chat_id: int


class ProxyParams(CustomModel):
    """The Cloudflare Worker relaying Discord and Telegram calls, disguised as VK API calls"""
    url: str
    key: str


class VkParams(CustomModel):
    token: str
    community_chat_id: int


class IntegrationParams(CustomModel):
    discord: DiscordParams
    telegram: TelegramParams
    proxy: ProxyParams
    vk: VkParams


class SSLParams(CustomModel):
    cert_path: str
    key_path: str


class SecretConfig(CustomModel):
    db: DBParams
    integrations: IntegrationParams
    ssl: SSLParams | None = None  # set for the test stage only: in prod, Caddy terminates TLS
