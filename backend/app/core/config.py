from functools import lru_cache
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_env: str = "development"
    app_name: str = "Factygo API"
    app_version: str = "3.0.31"
    groq_api_key: str | None = None
    groq_model: str = "openai/gpt-oss-120b"
    groq_fallback_model: str | None = None
    groq_vision_model: str | None = None
    groq_vision_fallback_model: str | None = None
    groq_transcription_model: str = "whisper-large-v3-turbo"
    database_url: str = "sqlite:///./factygo.db"
    request_timeout: float = Field(default=20.0, gt=0, le=120)
    search_timeout: float = Field(default=10.0, gt=0, le=60)
    max_article_chars: int = Field(default=30000, gt=1000, le=100000)
    max_search_results: int = Field(default=12, gt=1, le=30)
    rate_limit_per_minute: int = Field(default=30, gt=1, le=120)
    cors_origins: str = "*"
    groq_max_instruction_chars: int = Field(default=28000, gt=4000, le=60000)
    groq_claim_input_chars: int = Field(default=9000, gt=1000, le=20000)
    groq_evidence_excerpt_chars: int = Field(default=1400, gt=300, le=5000)
    max_ai_wait_seconds: float = Field(default=25.0, gt=1, le=80)

    model_config = SettingsConfigDict(env_file=".env", case_sensitive=False, extra="ignore")


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
