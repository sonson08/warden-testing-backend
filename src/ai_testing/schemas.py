from typing import Literal

from pydantic import BaseModel, Field

EntityType = Literal[
    "PERSON", "EMAIL", "PHONE", "ADDRESS", "GOVERNMENT_ID", "FINANCIAL",
    "DATE_OF_BIRTH", "CREDENTIAL", "IP_ADDRESS", "ORGANIZATION", "CONFIDENTIAL",
]  # fmt: skip


class Entity(BaseModel):
    """One sensitive value found in a prompt (docs/requirement.md 5.2)."""

    type: EntityType = Field(description="The kind of sensitive data")
    value: str = Field(description="The value copied exactly as it appears in the message")


class Detection(BaseModel):
    """All sensitive values found in a prompt."""

    entities: list[Entity] = Field(description="Every sensitive value in the message; empty if there is none")


class CapitalAnswer(BaseModel):
    """Structured answer to "what is the capital of X?"."""

    country: str = Field(description="The country that was asked about")
    capital: str = Field(description="The capital city of that country")
