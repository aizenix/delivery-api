from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/delivery"
    redis_url: str = "redis://localhost:6379/0"
    celery_broker_url: str = "redis://localhost:6379/1"

    jwt_secret: str = "dev-jwt-secret-change-me-in-env-file"
    access_token_minutes: int = 30
    refresh_token_days: int = 30

    otp_ttl_seconds: int = 300
    otp_resend_seconds: int = 60
    otp_max_attempts: int = 5

    sms_backend: Literal["console", "http"] = "console"
    sms_gateway_url: str = ""
    sms_gateway_token: str = ""
    sms_sender: str = "Delivery"


settings = Settings()
