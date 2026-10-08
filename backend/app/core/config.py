from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    database_url: str = ""
    llm_provider: str = "none"
    llm_base_url: str = "http://localhost:11434"
    llm_model: str = ""
    search_provider: str = "none"
    search_api_key: str = ""
    cors_origins: str = "http://localhost:3000"
    rate_limit_per_minute: int = 30

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


settings = Settings()
