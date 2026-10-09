from typing import TypeVar

from pydantic_ai import Agent, NativeOutput, TextOutput
from pydantic_ai.models.openai import OpenAIChatModel
from pydantic_ai.providers.ollama import OllamaProvider
from pydantic_ai.settings import ModelSettings

from ai_testing.config import Settings, settings as default_settings

T = TypeVar("T")


def build_model(cfg: Settings = default_settings) -> OpenAIChatModel:
    """Chat model pointed at the local Ollama server."""
    return OpenAIChatModel(cfg.model_name, provider=OllamaProvider(base_url=cfg.ollama_base_url))


def build_agent(
    output_type: type[T] | TextOutput[T],
    instructions: str,
    cfg: Settings = default_settings,
) -> Agent[None, T]:
    """Agent whose replies are validated against output_type (a Pydantic model).

    A TextOutput is passed through unchanged, for models fine-tuned on their own reply format.
    """
    return Agent(
        build_model(cfg),
        # Tool-call output is unreliable on small Ollama models (empty replies); use JSON-schema mode.
        output_type=NativeOutput(output_type) if isinstance(output_type, type) else output_type,
        instructions=instructions,
        model_settings=ModelSettings(temperature=cfg.temperature, seed=cfg.seed),
        retries=2,
    )
