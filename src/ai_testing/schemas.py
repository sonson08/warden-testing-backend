from pydantic import BaseModel, Field


class CapitalAnswer(BaseModel):
    """Structured answer to "what is the capital of X?"."""

    country: str = Field(description="The country that was asked about")
    capital: str = Field(description="The capital city of that country")
