"""Application configuration — loaded from environment variables."""
from pathlib import Path
from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


PROJECT_ROOT = Path(__file__).resolve().parent.parent
AUTHORITATIVE_ENV_FILE = PROJECT_ROOT / ".env"


class Settings(BaseSettings):
    """Application settings loaded from environment variables / .env file."""

    model_config = SettingsConfigDict(
        env_file=str(AUTHORITATIVE_ENV_FILE),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Database
    DATABASE_URL: str = "postgresql+asyncpg://salesoorja:salesoorja@localhost:5432/salesoorja"
    DATABASE_URL_SYNC: str = "postgresql://salesoorja:salesoorja@localhost:5432/salesoorja"

    # Redis / Celery
    REDIS_URL: str = "redis://localhost:6379/0"
    CELERY_BROKER_URL: str = "redis://localhost:6379/0"
    CELERY_RESULT_BACKEND: str = "redis://localhost:6379/1"

    # Google / Gemini
    GOOGLE_API_KEY: str = ""
    GEMINI_API_KEY: str = ""
    GOOGLE_MAPS_API_KEY: str = ""
    # Zero-Cost LLM Cost Policy & Account Verification
    LLM_COST_POLICY: str = "ZERO_COST_ONLY"
    ALLOW_PAID_LLM: bool = False

    # Gemini Settings & Account Verification
    GEMINI_ACCOUNT_MODE: str = "FREE_NO_BILLING"  # Allowed: FREE_NO_BILLING, PAID, UNVERIFIED (Default: FREE_NO_BILLING)
    ORCHESTRATOR_GEMINI_MODEL: str = "gemini-3.1-flash-lite"

    # Hive Settings & Promotional-Credit Safety
    HIVE_API_KEY: str = ""
    HIVE_BASE_URL: str = "https://api-cdn.thehive.ai/api/v3"
    HIVE_MODEL: str = "deepseek-ai/DeepSeek-V4.1-Flash"
    HIVE_ACCOUNT_MODE: str = "UNVERIFIED"
    HIVE_ALLOW_PAID_OVERAGE: bool = False
    HIVE_TIMEOUT: int = 60
    HIVE_INPUT_USD_PER_MILLION_TOKENS: float = 0.15
    HIVE_OUTPUT_USD_PER_MILLION_TOKENS: float = 0.60

    # Orchestrator LLM Settings
    ORCHESTRATOR_MAX_ITERATIONS: int = 6
    ORCHESTRATOR_TOKEN_BUDGET: int = 20000


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

    # Search & Crawling
    SERPER_API_KEY: str = ""
    SERPER_DAILY_HARD_LIMIT: int = 1500
    SERPER_BUDGET_TIMEZONE: str = "Asia/Kolkata"
    SERPER_INITIAL_QUERIES_PER_COMPANY: int = 4
    SERPER_MAX_QUERIES_PER_COMPANY: int = 10
    # App settings
    SECRET_KEY: str = "change-me-in-production"
    DEBUG: bool = True
    CORS_ORIGINS: str = "http://localhost:5173,http://localhost:3000"

    @field_validator("DEBUG", mode="before")
    @classmethod
    def parse_debug_mode(cls, value):
        if isinstance(value, str):
            normalized = value.strip().lower()
            if normalized in {"release", "production", "prod"}:
                return False
            if normalized in {"development", "dev"}:
                return True
        return value

settings = Settings()
