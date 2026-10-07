from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    bot_token: str = ""
    bot_username: str = "salon_bot"
    webhook_base_url: str = ""
    webhook_secret: str = ""
    database_url: str = "postgresql+asyncpg://app:app@localhost:5432/app"
    miniapp_url: str = "https://example.ru/app/"
    uploads_dir: str = "/data/uploads"
    uploads_base_url: str = "https://example.ru/uploads/"
    admin_username: str = ""
    admin_password: str = ""
    sentry_dsn: str = ""

    environment: str = "production"
    log_level: str = "INFO"
    # Путь к HTML политики обработки ПДн; пусто — встроенная заглушка.
    privacy_html_path: str = ""
    # Регистрировать webhook и menu button бота при старте api.
    telegram_setup_on_startup: bool = True

    init_data_max_age_seconds: int = 24 * 60 * 60
    invite_ttl_days: int = 7
    max_active_appointments_per_client: int = 3
    nearest_slot_horizon_days: int = 14

    @property
    def webhook_path(self) -> str:
        return f"/tg/webhook/{self.webhook_secret}"

    def salon_link(self, slug: str) -> str:
        return f"https://t.me/{self.bot_username}?startapp=s_{slug}"

    def invite_link(self, token: str) -> str:
        return f"https://t.me/{self.bot_username}?start=inv_{token}"

    def miniapp_link(self, start_param: str | None = None) -> str:
        if not start_param:
            return self.miniapp_url
        sep = "&" if "?" in self.miniapp_url else "?"
        return f"{self.miniapp_url}{sep}startapp={start_param}"


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
