from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime config, overridable via environment variables or a .env file."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    ollama_base_url: str = "http://localhost:11434/v1"
    model_name: str = "hf.co/mradermacher/Distil-PII-Llama-3.2-3B-Instruct-GGUF:Q4_K_M"
    # Tests that take a `model` argument run once per model here. Override with MODEL_NAMES='["hf.co/mradermacher/Distil-PII-Llama-3.2-3B-Instruct-GGUF:Q4_K_M"]'.
    model_names: list[str] = ["hf.co/mradermacher/Distil-PII-Llama-3.2-3B-Instruct-GGUF:Q4_K_M"]
    temperature: float = 0.0
    # temperature 0 alone is not fully repeatable on Ollama; a fixed seed reduces the variation.
    seed: int = 42

    def with_model(self, name: str) -> "Settings":
        """The same settings pointed at another model."""
        return self.model_copy(update={"model_name": name})


settings = Settings()
