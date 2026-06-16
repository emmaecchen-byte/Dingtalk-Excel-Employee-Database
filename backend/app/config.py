from typing import List

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_name: str = "钉钉考勤管理系统"
    database_url: str = "sqlite:///./attendance.db"
    cors_origins: List[str] = ["http://localhost:5173", "http://127.0.0.1:5173"]
    demo_mode: bool = True

    # PostgreSQL connection pool (used when database_url is postgresql://...)
    db_pool_size: int = 5
    db_max_overflow: int = 10
    db_pool_timeout: int = 30
    db_pool_recycle: int = 1800
    db_pool_pre_ping: bool = True

    # JWT authentication
    jwt_secret_key: str = "change-me-in-production-use-a-long-random-secret"
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 30
    refresh_token_expire_days: int = 7

    # DingTalk OAuth
    dingtalk_client_id: str = ""
    dingtalk_client_secret: str = ""
    dingtalk_corp_id: str = ""
    dingtalk_redirect_uri: str = "http://127.0.0.1:8000/api/auth/dingtalk/callback"
    frontend_url: str = "http://localhost:5173"

    @property
    def dingtalk_enabled(self) -> bool:
        return bool(self.dingtalk_client_id and self.dingtalk_client_secret and self.dingtalk_redirect_uri)

    # DingTalk employee sync
    dingtalk_root_department_id: int = 1
    dingtalk_user_page_size: int = 100
    dingtalk_api_delay_ms: int = 200
    dingtalk_rate_limit_backoff_seconds: float = 1.5

    # DingTalk webhook callbacks (HTTP push)
    dingtalk_webhook_token: str = ""
    dingtalk_webhook_aes_key: str = ""
    dingtalk_webhook_owner_key: str = ""

    @property
    def dingtalk_webhook_configured(self) -> bool:
        return bool(self.dingtalk_webhook_token and self.dingtalk_webhook_aes_key)

    @property
    def is_postgresql(self) -> bool:
        return self.database_url.startswith("postgresql")


settings = Settings()
