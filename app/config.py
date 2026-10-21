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

    gpk_source_url: str = Field(
        default="https://gpk.gov.by/situation-at-the-border/", alias="GPK_SOURCE_URL"
    )
    fetch_offset_minutes: int = Field(default=10, alias="FETCH_OFFSET_MINUTES")

    payment_provider_token: str = Field(default="", alias="PAYMENT_PROVIDER_TOKEN")
    payment_currency: str = Field(default="BYN", alias="PAYMENT_CURRENCY")
    price_car_minor: int = Field(default=500, alias="PRICE_CAR_MINOR")
    price_truck_minor: int = Field(default=900, alias="PRICE_TRUCK_MINOR")

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
