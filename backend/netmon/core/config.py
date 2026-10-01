"""Application settings, loaded from environment variables (prefix ``NETMON_``) or ``.env``."""

from __future__ import annotations

from functools import lru_cache
from typing import Annotated, Literal

from pydantic import Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

_INSECURE_SECRET = "change-me-in-production"  # noqa: S105 - sentinel, rejected in production


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="NETMON_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # ------------------------------------------------------------------ application
    app_name: str = "NetMon"
    environment: Literal["development", "production", "test"] = "development"
    api_prefix: str = "/api/v1"
    log_level: str = "INFO"
    log_format: Literal["console", "json"] = "console"
    cors_origins: Annotated[list[str], NoDecode] = Field(
        default_factory=lambda: ["http://localhost:5173", "http://127.0.0.1:5173"]
    )
    prometheus_enabled: bool = True

    # ------------------------------------------------------------------ database
    database_url: str = "sqlite+aiosqlite:///./netmon.db"
    db_echo: bool = False
    db_pool_size: int = 10
    db_auto_create: bool = False  # create tables on start-up (tests / throw-away dev DBs)

    # ------------------------------------------------------------------ security
    secret_key: SecretStr = SecretStr(_INSECURE_SECRET)
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 12 * 60
    login_max_attempts: int = 5
    login_lockout_seconds: int = 300
    first_admin_email: str = "admin@netmon.local"
    first_admin_password: SecretStr = SecretStr("ChangeMe123!")

    # ------------------------------------------------------------------ monitoring engine
    monitoring_enabled: bool = True
    monitor_mode: Literal["live", "simulation"] = "live"
    poll_interval_seconds: int = Field(default=30, ge=5, le=3600)
    max_concurrent_polls: int = Field(default=64, ge=1, le=1024)
    icmp_count: int = Field(default=3, ge=1, le=20)
    icmp_interval: float = Field(default=0.2, ge=0.01)
    icmp_timeout: float = Field(default=1.0, gt=0)
    icmp_privileged: bool | None = None  # None = auto-detect (root -> raw sockets)
    tcp_timeout: float = Field(default=2.0, gt=0)
    snmp_timeout: float = Field(default=2.0, gt=0)
    snmp_retries: int = Field(default=1, ge=0, le=5)
    down_after_failures: int = Field(default=2, ge=1, le=20)
    degraded_latency_ms: float = 150.0
    degraded_packet_loss: float = 10.0
    metrics_retention_days: int = Field(default=90, ge=1)
    simulation_seed: int | None = None

    # ------------------------------------------------------------------ discovery
    discovery_max_hosts: int = Field(default=1024, ge=1, le=65536)
    discovery_concurrency: int = Field(default=128, ge=1, le=1024)
    discovery_timeout: float = Field(default=1.0, gt=0)

    # ------------------------------------------------------------------ notifications
    alert_webhook_url: str | None = None
    alert_min_severity: Literal["info", "warning", "critical"] = "warning"
    smtp_host: str | None = None
    smtp_port: int = 587
    smtp_username: str | None = None
    smtp_password: SecretStr | None = None
    smtp_from: str = "netmon@localhost"
    smtp_to: Annotated[list[str], NoDecode] = Field(default_factory=list)
    smtp_starttls: bool = True

    @field_validator("cors_origins", "smtp_to", mode="before")
    @classmethod
    def _split_csv(cls, value: object) -> object:
        if isinstance(value, str):
            return [item.strip() for item in value.split(",") if item.strip()]
        return value

    @model_validator(mode="after")
    def _check_production_safety(self) -> Settings:
        if self.environment == "production":
            if self.secret_key.get_secret_value() == _INSECURE_SECRET:
                raise ValueError("NETMON_SECRET_KEY must be set to a strong value in production")
            if len(self.secret_key.get_secret_value()) < 32:
                raise ValueError("NETMON_SECRET_KEY must be at least 32 characters in production")
        return self

    @property
    def is_sqlite(self) -> bool:
        return self.database_url.startswith("sqlite")

    @property
    def uses_default_secret(self) -> bool:
        return self.secret_key.get_secret_value() == _INSECURE_SECRET


@lru_cache
def get_settings() -> Settings:
    return Settings()
