from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_env: str = Field(default="local", alias="APP_ENV")
    auto_migrate: bool = Field(default=True, alias="AUTO_MIGRATE")
    tz: str = Field(default="Asia/Seoul", alias="TZ")
    database_url: str | None = Field(default=None, alias="DATABASE_URL")
    slack_bot_token: str | None = Field(default=None, alias="SLACK_BOT_TOKEN")
    max_threads_poll_per_run: int = Field(default=300, alias="MAX_THREADS_POLL_PER_RUN")
    openai_api_key: str | None = Field(default=None, alias="OPENAI_API_KEY")
    openai_model: str = Field(default="gpt-4o-mini", alias="OPENAI_MODEL")
    max_messages_per_thread_for_summary: int = Field(
        default=80, alias="MAX_MESSAGES_PER_THREAD_FOR_SUMMARY"
    )
    max_messages_per_thread_for_report: int = Field(
        default=200, alias="MAX_MESSAGES_PER_THREAD_FOR_REPORT"
    )
    summary_language: str = Field(default="ko", alias="SUMMARY_LANGUAGE")
    max_threads_per_daily_report: int = Field(
        default=60, alias="MAX_THREADS_PER_DAILY_REPORT"
    )

    model_config = SettingsConfigDict(
        env_file=".env",
        extra="ignore",
        case_sensitive=False,
    )


settings = Settings()
