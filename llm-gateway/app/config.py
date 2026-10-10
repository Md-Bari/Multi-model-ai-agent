from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # Reads llm-gateway/.env when run locally from app/, or env vars inside Docker.
    model_config = SettingsConfigDict(env_file=("../.env", ".env"), extra="ignore")

    # Docker sets DATABASE_URL; locally it is built from POSTGRES_PASSWORD.
    postgres_password: str = "gateway"
    database_url: str = ""
    redis_url: str = "redis://localhost:6379/0"

    # Real provider keys: these never leave the server.
    openai_api_key: str = ""
    anthropic_api_key: str = ""
    gemini_api_key: str = ""

    # LiteLLM model strings for each tier.
    cheap_model_gemini: str = "gemini/gemini-3.8-flash"
    cheap_model_openai: str = "openai/gpt-5-mini"
    strong_model_claude: str = "anthropic/claude-sonnet-5-5"
    strong_model_openai: str = "openai/gpt-5"

    llm_timeout: float = 60
    llm_num_retries: int = 1

    cache_ttl_seconds: int = 86400
    key_cache_ttl_seconds: int = 300
    session_ttl_seconds: int = 7 * 86400
    default_rpm_limit: int = 60
    cookie_secure: bool = False


settings = Settings()
if not settings.database_url:
    settings.database_url = f"postgresql+asyncpg://gateway:{settings.postgres_password}@localhost:5434/gateway"
