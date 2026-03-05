"""Application settings loaded from environment variables."""

from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime configuration for the RevenueCat agent platform."""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    database_url: str = Field(default="postgresql://user:pass@localhost:5432/revenuecat_agent", alias="DATABASE_URL")
    redis_url: str = Field(default="redis://localhost:6379/0", alias="REDIS_URL")
    log_level: str = Field(default="INFO", alias="LOG_LEVEL")

    openai_api_key: str | None = Field(default=None, alias="OPENAI_API_KEY")
    openai_model: str = Field(default="gpt-4.1-mini", alias="OPENAI_MODEL")
    openai_moderation_model: str = Field(default="omni-moderation-latest", alias="OPENAI_MODERATION_MODEL")

    gemini_api_key: str | None = Field(default=None, alias="GEMINI_API_KEY")
    gemini_model: str = Field(default="gemini-2.5-pro", alias="GEMINI_MODEL")

    vertex_project_id: str | None = Field(default=None, alias="VERTEX_PROJECT_ID")
    vertex_location: str = Field(default="us-central1", alias="VERTEX_LOCATION")
    vertex_model: str = Field(default="gemini-2.5-flash", alias="VERTEX_MODEL")
    vertex_heavy_model: str = Field(default="gemini-2.5-pro", alias="VERTEX_HEAVY_MODEL")
    vertex_flash_models: str = Field(
        default="gemini-2.5-flash,gemini-2.5-flash-lite",
        alias="VERTEX_FLASH_MODELS",
    )
    vertex_access_token: str | None = Field(default=None, alias="VERTEX_ACCESS_TOKEN")

    ollama_base_url: str = Field(default="http://localhost:11434", alias="OLLAMA_BASE_URL")
    ollama_model: str = Field(default="llama3.1:8b", alias="OLLAMA_MODEL")

    llm_primary_provider: str = Field(default="vertex", alias="LLM_PRIMARY_PROVIDER")
    llm_secondary_provider: str = Field(default="openai", alias="LLM_SECONDARY_PROVIDER")
    llm_tertiary_provider: str = Field(default="gemini", alias="LLM_TERTIARY_PROVIDER")
    llm_timeout_ms: int = Field(default=12000, alias="LLM_TIMEOUT_MS")

    moderation_provider: str = Field(default="openai", alias="MODERATION_PROVIDER")
    moderation_timeout_ms: int = Field(default=4000, alias="MODERATION_TIMEOUT_MS")

    revenuecat_api_key: str | None = Field(default=None, alias="REVENUECAT_API_KEY")
    revenuecat_app_id: str | None = Field(default=None, alias="REVENUECAT_APP_ID")

    twitter_api_key: str | None = Field(default=None, alias="TWITTER_API_KEY")
    twitter_api_secret: str | None = Field(default=None, alias="TWITTER_API_SECRET")
    twitter_access_token: str | None = Field(default=None, alias="TWITTER_ACCESS_TOKEN")
    twitter_access_token_secret: str | None = Field(default=None, alias="TWITTER_ACCESS_TOKEN_SECRET")
    twitter_bearer_token: str | None = Field(default=None, alias="TWITTER_BEARER_TOKEN")

    github_token: str | None = Field(default=None, alias="GITHUB_TOKEN")
    github_username: str | None = Field(default=None, alias="GITHUB_USERNAME")
    github_repo: str | None = Field(default=None, alias="GITHUB_REPO")

    hashnode_api_key: str | None = Field(default=None, alias="HASHNODE_API_KEY")
    hashnode_publication_id: str | None = Field(default=None, alias="HASHNODE_PUBLICATION_ID")

    enable_discord: bool = Field(default=False, alias="ENABLE_DISCORD")
    discord_bot_token: str | None = Field(default=None, alias="DISCORD_BOT_TOKEN")
    discord_channel_id: str | None = Field(default=None, alias="DISCORD_CHANNEL_ID")

    slack_webhook_url: str | None = Field(default=None, alias="SLACK_WEBHOOK_URL")

    agent_name: str = Field(default="RevenueCatAgent", alias="AGENT_NAME")
    agent_start_date: str = Field(default="2026-03-05", alias="AGENT_START_DATE")

    force_auto_mode: Literal["DRY_RUN", "AUTO_LOW_RISK", "AUTO_ALL", ""] | None = Field(
        default=None, alias="FORCE_AUTO_MODE"
    )

    quality_min_score: float = Field(default=75.0, alias="QUALITY_MIN_SCORE")
    quality_similarity_threshold: float = Field(default=0.92, alias="QUALITY_SIMILARITY_THRESHOLD")
    experiment_success_threshold: float = Field(default=0.10, alias="EXPERIMENT_SUCCESS_THRESHOLD")

    admin_api_token: str | None = Field(default=None, alias="ADMIN_API_TOKEN")

    backup_remote_url: str | None = Field(default=None, alias="BACKUP_REMOTE_URL")
    backup_s3_endpoint: str | None = Field(default=None, alias="BACKUP_S3_ENDPOINT")
    backup_s3_access_key: str | None = Field(default=None, alias="BACKUP_S3_ACCESS_KEY")
    backup_s3_secret_key: str | None = Field(default=None, alias="BACKUP_S3_SECRET_KEY")
    backup_retention_daily: int = Field(default=30, alias="BACKUP_RETENTION_DAILY")
    backup_retention_weekly: int = Field(default=12, alias="BACKUP_RETENTION_WEEKLY")


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return a cached Settings instance."""

    return Settings()
