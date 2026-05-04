from __future__ import annotations

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_env: str = Field(default="development", alias="APP_ENV")
    log_level: str = Field(default="INFO", alias="LOG_LEVEL")
    database_url: str = Field(default="sqlite:///./shipments.db", alias="DATABASE_URL")
    check_interval_minutes: int = Field(default=30, alias="CHECK_INTERVAL_MINUTES")
    tracker_batch_size: int = Field(default=100, alias="TRACKER_BATCH_SIZE")
    daily_summary_hour: int = Field(default=8, alias="DAILY_SUMMARY_HOUR")
    daily_summary_minute: int = Field(default=0, alias="DAILY_SUMMARY_MINUTE")
    scheduler_timezone: str = Field(default="Europe/Lisbon", alias="SCHEDULER_TIMEZONE")

    google_sheets_enabled: bool = Field(default=False, alias="GOOGLE_SHEETS_ENABLED")
    google_sheets_spreadsheet_id: str = Field(default="", alias="GOOGLE_SHEETS_SPREADSHEET_ID")
    google_sheets_worksheet_name: str = Field(default="Shipments", alias="GOOGLE_SHEETS_WORKSHEET_NAME")
    google_sheets_credentials_file: str = Field(
        default="./google-service-account.json",
        alias="GOOGLE_SHEETS_CREDENTIALS_FILE",
    )

    telegram_bot_token: str = Field(default="", alias="TELEGRAM_BOT_TOKEN")
    telegram_chat_id: str = Field(default="", alias="TELEGRAM_CHAT_ID")
    telegram_api_base: str = Field(default="https://api.telegram.org", alias="TELEGRAM_API_BASE")

    aggregator_provider: str = Field(default="17track", alias="AGGREGATOR_PROVIDER")
    aggregator_api_key: str = Field(default="", alias="AGGREGATOR_API_KEY")
    aggregator_base_url: str = Field(default="https://api.17track.net/track/v2.2", alias="AGGREGATOR_BASE_URL")
    aggregator_timeout_seconds: int = Field(default=20, alias="AGGREGATOR_TIMEOUT_SECONDS")

    playwright_headless: bool = Field(default=True, alias="PLAYWRIGHT_HEADLESS")
    playwright_timeout_ms: int = Field(default=45_000, alias="PLAYWRIGHT_TIMEOUT_MS")
    playwright_max_retries: int = Field(default=3, alias="PLAYWRIGHT_MAX_RETRIES")
    playwright_user_agent: str = Field(
        default=(
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/135.0.0.0 Safari/537.36"
        ),
        alias="PLAYWRIGHT_USER_AGENT",
    )
    playwright_locale: str = Field(default="en-US", alias="PLAYWRIGHT_LOCALE")

    cyprus_post_tracking_url: str = Field(
        default="https://www.cypruspost.post/en/track-n-trace-results",
        alias="CYPRUS_POST_TRACKING_URL",
    )
    acs_tracking_url: str = Field(
        default="https://www.acscourier.net/en/track-and-trace/",
        alias="ACS_TRACKING_URL",
    )
    acs_search_api_url: str = Field(
        default="https://api.acscourier.net/api/parcels/search",
        alias="ACS_SEARCH_API_URL",
    )


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
