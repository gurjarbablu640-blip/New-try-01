"""Application configuration — loaded from environment variables."""
import os
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

    # Google / Gemini
    GOOGLE_API_KEY: str = ""
    GOOGLE_MAPS_API_KEY: str = ""
    GOOGLE_SEARCH_CX: str = ""  # Google Custom Search Engine ID

    # Serper.dev Search API
    SERPER_API_KEY: str = ""

    # Zero-Cost LLM Cost Policy & Account Verification
    LLM_COST_POLICY: str = "ZERO_COST_ONLY"
    ALLOW_PAID_LLM: bool = False

    # Gemini Settings & Account Verification
    GEMINI_ACCOUNT_MODE: str = "FREE_NO_BILLING"  # Allowed: FREE_NO_BILLING, PAID, UNVERIFIED (Default: FREE_NO_BILLING)
    ORCHESTRATOR_GEMINI_MODEL: str = "gemini-3.1-flash-lite"

    # Groq Settings & Account Verification
    GROQ_API_KEY: str = ""
    GROQ_ACCOUNT_MODE: str = "UNVERIFIED"  # Allowed: FREE, PAID, UNVERIFIED (Default: UNVERIFIED)
    GROQ_MODEL: str = "openai/gpt-oss-20b"

    # OpenRouter Settings & Account Verification
    OPENROUTER_API_KEY: str = ""
    OPENROUTER_ACCOUNT_MODE: str = "UNVERIFIED"  # Allowed: FREE, PAID, UNVERIFIED (Default: UNVERIFIED)
    OPENROUTER_MODEL: str = "meta-llama/llama-3.3-70b-instruct:free"

    # Cloudflare Settings & Account Verification
    CLOUDFLARE_ACCOUNT_ID: str = ""
    CLOUDFLARE_API_TOKEN: str = ""
    CLOUDFLARE_ACCOUNT_MODE: str = "UNVERIFIED"  # Allowed: FREE, PAID, UNVERIFIED (Default: UNVERIFIED)
    CLOUDFLARE_MODEL: str = "@cf/meta/llama-3.1-8b-instruct"

    # UnoRouter Settings & Zero-Cost Route
    UNOROUTER_API_KEY: str = ""
    UNOROUTER_ENABLED: bool = True
    UNOROUTER_BASE_URL: str = "https://api.unorouter.com/v1"
    UNOROUTER_MODEL: str = "glm-5.3-search:free"
    UNOROUTER_ACCOUNT_MODE: str = "FREE"  # Allowed: FREE, PAID, UNVERIFIED (Default: FREE for approved zero-cost routes)
    UNOROUTER_TIMEOUT: int = 90

    # LLM Reasoning Cache
    LLM_CACHE_ENABLED: bool = True
    LLM_CACHE_DIR: str = "data/llm_cache"
    LLM_CACHE_TTL_DAYS: int = 30

    # OpenAI / ChatGPT (Retained for manual/explicit use only; blocked when ALLOW_PAID_LLM=False)
    OPENAI_API_KEY: str = ""
    OPENAI_MODEL: str = "gpt-4o"

    # Orchestrator LLM Settings (Zero-Cost Safe)
    ORCHESTRATOR_PRIMARY_PROVIDER: str = "gemini"
    ORCHESTRATOR_FALLBACK_PROVIDER: str = "groq"
    ORCHESTRATOR_OPENAI_MODEL: str = "gpt-4o"
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
    SEARXNG_BASE_URL: str = "http://localhost:8080"

    # DeerFlow Service Adapter (Isolated HTTP boundary)
    DEERFLOW_BASE_URL: str = os.getenv("DEERFLOW_BASE_URL", "http://deerflow:8001" if os.path.exists("/.dockerenv") else "http://localhost:8001")
    DEERFLOW_ENABLED: bool = True
    DEERFLOW_TIMEOUT_SECONDS: int = 60

    # App settings
    SECRET_KEY: str = "change-me-in-production"
    DEBUG: bool = True
    CORS_ORIGINS: str = "http://localhost:5173,http://localhost:3000"

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        extra = "ignore"


settings = Settings()
