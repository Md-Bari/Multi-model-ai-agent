from pydantic_settings import BaseSettings, SettingsConfigDict

# USD per 1M tokens: [input, output]. Verify against provider pricing pages and
# override with MODEL_PRICES='{"model": [in, out]}' in the environment.
DEFAULT_PRICES: dict[str, list[float]] = {
    "llama-3.1-8b-instant": [0.05, 0.08],
    "llama-3.3-70b-versatile": [0.59, 0.79],
    "openai/gpt-oss-20b": [0.075, 0.30],
    "openai/gpt-oss-120b": [0.15, 0.60],
    "gemini-3.8-flash": [0.50, 3.00],
}


class Settings(BaseSettings):
    # Local runs read the repo-root .env; in containers / Render everything comes from env vars.
    model_config = SettingsConfigDict(env_file=(".env", "../.env"), extra="ignore")

    environment: str = "development"  # development | production | test
    log_level: str = "INFO"

    # Docker / Render set DATABASE_URL. Locally it falls back to the compose Postgres.
    postgres_password: str = "gateway"
    database_url: str = ""
    redis_url: str = "redis://localhost:6379/0"

    # Real provider keys: these never leave the server.
    gemini_api_key: str = ""
    groq_api_key: str = ""

    # Deployments (LangChain model names).
    groq_fast_model: str = "llama-3.1-8b-instant"
    groq_large_model: str = "openai/gpt-oss-120b"
    gemini_model: str = "gemini-3.8-flash"

    # Order to try per tier: first is primary, the rest are fallbacks.
    tier_cheap: str = "groq-fast,gemini"
    tier_strong: str = "gemini,groq-large"

    llm_timeout_seconds: float = 45
    llm_max_retries: int = 1
    circuit_breaker_seconds: int = 30
    model_prices: dict[str, list[float]] = DEFAULT_PRICES

    cache_ttl_seconds: int = 86400
    key_cache_ttl_seconds: int = 300
    session_ttl_seconds: int = 7 * 86400
    default_rpm_limit: int = 60
    playground_rpm_limit: int = 20
    login_max_attempts: int = 10
    login_window_seconds: int = 900

    # Set true in production (HTTPS). Cookies then only travel over TLS.
    cookie_secure: bool = False
    # Comma-separated origins allowed to call the API from a browser (not needed
    # when the frontend proxies /api through its own domain).
    cors_origins: str = ""

    @property
    def is_production(self) -> bool:
        return self.environment == "production"


settings = Settings()
if not settings.database_url:
    settings.database_url = f"postgresql+asyncpg://gateway:{settings.postgres_password}@localhost:5434/gateway"
