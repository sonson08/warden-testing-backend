from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime config, overridable via environment variables or a .env file."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    ollama_base_url: str = "http://localhost:11434/v1"
    model_name: str = "qwen2.5:3b"
    temperature: float = 0.0
    # temperature 0 alone is not fully repeatable on Ollama; a fixed seed reduces the variation.
    seed: int = 42


settings = Settings()
