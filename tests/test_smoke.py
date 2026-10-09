import pytest

from ai_testing.config import settings
from ai_testing.llm import build_agent
from ai_testing.schemas import CapitalAnswer


@pytest.mark.llm
def test_model_returns_valid_structured_answer(record):
    prompt = "What is the capital of France?"
    expected = CapitalAnswer(country="France", capital="Paris")
    agent = build_agent(CapitalAnswer, instructions="You are a concise geography assistant.")

    result = agent.run_sync(prompt)

    usage = result.usage
    record(
        input=prompt,
        expected=expected,
        actual=result.output,
        model=settings.model_name,
        temperature=settings.temperature,
        tokens=f"{usage.input_tokens} in / {usage.output_tokens} out",
        requests=usage.requests,
    )

    # Pydantic already guaranteed the shape; now check the content.
    assert isinstance(result.output, CapitalAnswer)
    assert result.output.country.lower() == expected.country.lower()
    assert result.output.capital.lower() == expected.capital.lower()
