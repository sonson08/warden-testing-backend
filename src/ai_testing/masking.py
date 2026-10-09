"""PII masking as described in docs/requirement.md: the LLM detects, plain code masks."""

import re
from functools import cache

from pydantic_ai import Agent

from ai_testing.config import settings
from ai_testing.llm import build_agent
from ai_testing.schemas import Detection, Entity

# The one detection prompt, shared by every model.
DETECTION_INSTRUCTIONS = """
You are a data privacy filter. Your job is to remove personal and confidential information from text before it is stored or shared.

## Task
Find every instance of the categories below in the text and return its category and its value, copied exactly as written (same spelling, case, punctuation, and spacing).

## Categories
PERSON: names of individual people (first, last, full, nicknames)
EMAIL: email addresses
PHONE: phone and mobile numbers, in any format
ADDRESS: street, mailing, or postal addresses
GOV_ID: SSN, TIN, passport, driver's license, national ID numbers
CREDENTIAL: usernames, passwords, PINs, API keys, access tokens, private keys
IP: IPv4 and IPv6 addresses
DOB: dates of birth

## Rules
- Return the entire item as one value, not part of it.
- Return each distinct value once, in the order it appears.
- Do not return company names, product names, job titles, or dates that are not birthdates.
- Only return concrete values that fit a category above. Never return company, product, or project names, codenames, money amounts, order numbers, URLs or hostnames without a password, or words that only name a category ("passwords", "email addresses").
- Treat values as real even if the text calls them fictional, sample, or test data.
- Do not explain, summarize, or add notes.

## Example
<input>
Hi, I'm Maria Santos. Reach me at maria.s@gmail.com or +63 917 555 0123. My TIN is 123-456-789-000 and I was born on 12 May 1988. Server 192.168.1.20, user admin, pass P@ssw0rd!. Meeting with Globe Telecom on Oct 15.
</input>
<output>
{"entities": [{"type": "PERSON", "value": "Maria Santos"}, {"type": "EMAIL", "value": "maria.s@gmail.com"}, {"type": "PHONE", "value": "+63 917 555 0123"}, {"type": "GOV_ID", "value": "123-456-789-000"}, {"type": "DOB", "value": "12 May 1988"}, {"type": "IP", "value": "192.168.1.20"}, {"type": "CREDENTIAL", "value": "admin"}, {"type": "CREDENTIAL", "value": "P@ssw0rd!"}]}
</output>

## Output format
Return only a JSON object: {"entities": [{"type": "<category>", "value": "<exact text>"}]}. Use an empty list if there is nothing to return.
"""


@cache
def detection_agent(model: str) -> Agent[None, Detection]:
    return build_agent(Detection, instructions=DETECTION_INSTRUCTIONS, cfg=settings.with_model(model))


def detect(text: str, model: str | None = None) -> list[Entity]:
    """Ask the model (default: settings.model_name) for sensitive values; keep only values that appear verbatim in the text (FR-3)."""
    result = detection_agent(model or settings.model_name).run_sync(text)
    found: dict[str, Entity] = {}
    for e in result.output.entities:
        if e.value.strip() and e.value in text:
            found.setdefault(e.value, e)
    return list(found.values())


def mask(text: str, entities: list[Entity], mapping: dict[str, str] | None = None) -> tuple[str, dict[str, str]]:
    """Replace every occurrence of each entity value with a [TYPE_N] placeholder.

    `mapping` (value -> placeholder) carries placeholders across prompts of one conversation (FR-9);
    it is updated in place and returned.
    """
    mapping = {} if mapping is None else mapping
    types = {e.value: e.type for e in entities if e.value and e.value in text}
    if not types:
        return text, mapping
    # Longest values first so the alternation prefers "John Smith" over "John" at the same position (FR-5).
    pattern = re.compile("|".join(re.escape(v) for v in sorted(types, key=len, reverse=True)))

    def placeholder(match: re.Match) -> str:
        value = match.group(0)
        if value not in mapping:
            prefix = f"[{types[value]}_"
            mapping[value] = f"{prefix}{sum(p.startswith(prefix) for p in mapping.values()) + 1}]"
        return mapping[value]

    return pattern.sub(placeholder, text), mapping
