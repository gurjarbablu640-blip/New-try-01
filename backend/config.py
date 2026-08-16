"""Application configuration — loaded from environment variables."""
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Application settings loaded from environment variables / .env file."""

    # Database
    DATABASE_URL: str = "postgresql+asyncpg://salesoorja:salesoorja@localhost:5432/salesoorja"
    DATABASE_URL_SYNC: str = "postgresql://salesoorja:salesoorja@localhost:5432/salesoorja"

    # Redis / Celery
    REDIS_URL: str = "redis://localhost:6379/0"
    CELERY_BROKER_URL: str = "redis://localhost:6379/0"
    CELERY_RESULT_BACKEND: str = "redis://localhost:6379/1"

    # Claude / Anthropic
    ANTHROPIC_API_KEY: str = ""

    # Google / Gemini
    GOOGLE_API_KEY: str = ""
    GOOGLE_MAPS_API_KEY: str = ""

    # Apollo API
    APOLLO_API_KEY: str = ""
    APOLLO_API_BASE_URL: str = "https://api.apollo.io/v1"
    DISPOSABLE_DOMAINS_FILE: str = "data/disposable_email_domains.json"

    # Outbound SMTP / Email Settings
    SMTP_HOST: str = ""
    SMTP_PORT: int = 587
    SMTP_USER: str = ""
    SMTP_PASSWORD: str = ""
    SMTP_FROM_EMAIL: str = "sales@oorja.local"
    SMTP_FROM_NAME: str = "Oorja Technical Services"
    SMTP_USE_TLS: bool = True
    OUTBOUND_TEST_MODE: bool = True
    OUTBOUND_TEST_MAILBOX: str = "test@oorja.local"

    # Inbound IMAP Settings
    IMAP_HOST: str = ""
    IMAP_PORT: int = 993
    IMAP_USER: str = ""
    IMAP_PASSWORD: str = ""
    IMAP_USE_SSL: bool = True

    # App settings
    SECRET_KEY: str = "change-me-in-production"
    DEBUG: bool = True
    CORS_ORIGINS: str = "http://localhost:5173,http://localhost:3000"

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        extra = "ignore"


settings = Settings()
