"""Application configuration loaded from environment variables (.env in local dev)."""

from __future__ import annotations

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    bot_token: str = Field(default="", alias="BOT_TOKEN")
    admin_telegram_ids_raw: str = Field(default="", alias="ADMIN_TELEGRAM_IDS")

    database_url: str = Field(
        default="postgresql+asyncpg://postgres:postgres@localhost:5432/queue_monitor",
        alias="DATABASE_URL",
    )

    timezone: str = Field(default="Europe/Minsk", alias="TIMEZONE")

    border_api_url: str = Field(
        default="https://belarusborder.by/info/checkpoint?token=bts47d5f-6420-4f74-8f78-42e8e4370cc4",
        alias="BORDER_API_URL",
    )
    fetch_interval_minutes: int = Field(default=5, alias="FETCH_INTERVAL_MINUTES")

    payment_provider_token: str = Field(default="", alias="PAYMENT_PROVIDER_TOKEN")
    payment_currency: str = Field(default="BYN", alias="PAYMENT_CURRENCY")
    price_car_minor: int = Field(default=500, alias="PRICE_CAR_MINOR")
    price_truck_minor: int = Field(default=900, alias="PRICE_TRUCK_MINOR")

    @property
    def normalized_database_url(self) -> str:
        """Railway's Postgres plugin exposes DATABASE_URL as postgres:// or
        postgresql://; SQLAlchemy's async engine needs the asyncpg driver scheme.
        Rewriting here keeps the Railway variable a plain reference
        (${{Postgres.DATABASE_URL}}) instead of requiring manual edits.
        """
        url = self.database_url
        if url.startswith("postgres://"):
            return "postgresql+asyncpg://" + url[len("postgres://") :]
        if url.startswith("postgresql://"):
            return "postgresql+asyncpg://" + url[len("postgresql://") :]
        return url

    @property
    def admin_telegram_ids(self) -> set[int]:
        ids: set[int] = set()
        for part in self.admin_telegram_ids_raw.split(","):
            part = part.strip()
            if part.isdigit():
                ids.add(int(part))
        return ids

    @property
    def payments_enabled(self) -> bool:
        return bool(self.payment_provider_token)


settings = Settings()
