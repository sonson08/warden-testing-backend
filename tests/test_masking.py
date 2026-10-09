"""Masking tests for the ChatGPT AI Firewall (docs/requirement.md), run directly against Ollama.

Each test's docstring starts with its case ID from docs/masking-test-cases.md.
Tests marked `llm` call qwen2.5:3b via Ollama; the others check the placeholder rules only.
"""

import re

import pytest

from ai_testing.config import settings
from ai_testing.masking import detect, mask
from ai_testing.schemas import Entity

SCENARIO_TEXT = "Draft an email to John Smith (john.smith@acme.com) about the Project Falcon delay"
API_EXAMPLE_TEXT = "Email John Smith at john.smith@acme.com"


def entity(type_: str, value: str) -> Entity:
    return Entity(type=type_, value=value)


def masked_text(text: str, mapping: dict[str, str] | None = None) -> tuple[str, list[Entity]]:
    entities = detect(text)
    return mask(text, entities, mapping)[0], entities


def found(entities: list[Entity]) -> list[str]:
    return [f"{e.type}: {e.value}" for e in entities]


# --- Placeholder rules (no LLM) -----------------------------------------------------------------


def test_mask_api_example_masks_only_confirmed_entity(record):
    """TC-MSK-01 (FR-8, FR-10): only the confirmed entity is replaced."""
    actual, _ = mask(API_EXAMPLE_TEXT, [entity("PERSON", "John Smith")])
    expected = "Email [PERSON_1] at john.smith@acme.com"
    record(input=API_EXAMPLE_TEXT, expected=expected, actual=actual)

    assert actual == expected


def test_mask_replaces_every_occurrence(record):
    """TC-MSK-02 (FR-4, FR-8): a repeated value is masked everywhere with the same placeholder."""
    text = "John Smith called. Later, John Smith emailed again."
    actual, _ = mask(text, [entity("PERSON", "John Smith")])
    expected = "[PERSON_1] called. Later, [PERSON_1] emailed again."
    record(input=text, expected=expected, actual=actual)

    assert actual == expected


def test_mask_numbers_each_type_independently(record):
    """TC-MSK-03 (FR-8, FR-9): numbering is per type, in order of appearance."""
    text = "John Smith and Jane Doe share jane.doe@acme.com"
    ents = [entity("EMAIL", "jane.doe@acme.com"), entity("PERSON", "Jane Doe"), entity("PERSON", "John Smith")]
    actual, _ = mask(text, ents)
    expected = "[PERSON_1] and [PERSON_2] share [EMAIL_1]"
    record(input=text, expected=expected, actual=actual)

    assert actual == expected


def test_mask_keeps_placeholders_across_prompts(record):
    """TC-MSK-04 (FR-9): within a conversation a known value keeps its placeholder; a new one gets the next number."""
    first, mapping = mask("Call John Smith today", [entity("PERSON", "John Smith")])
    second, _ = mask("Ask Jane Doe to cc John Smith", [entity("PERSON", "Jane Doe"), entity("PERSON", "John Smith")], mapping)
    record(
        input=["Call John Smith today", "Ask Jane Doe to cc John Smith"],
        expected=["Call [PERSON_1] today", "Ask [PERSON_2] to cc [PERSON_1]"],
        actual=[first, second],
    )

    assert first == "Call [PERSON_1] today"
    assert second == "Ask [PERSON_2] to cc [PERSON_1]"


def test_mask_overlapping_values_longest_wins(record):
    """TC-MSK-05 (FR-5): 'John Smith' is masked as one span even when 'John' is also an entity."""
    text = "John Smith met John"
    actual, _ = mask(text, [entity("PERSON", "John"), entity("PERSON", "John Smith")])
    expected = "[PERSON_1] met [PERSON_2]"
    record(input=text, expected=expected, actual=actual)

    assert actual == expected


def test_mask_matches_values_literally(record):
    """TC-MSK-06 (FR-8): regex metacharacters in a value are matched literally."""
    text = "The password is p@ss.w0rd*(x)+[1] and pXss_w0rd is not it."
    actual, _ = mask(text, [entity("CREDENTIAL", "p@ss.w0rd*(x)+[1]")])
    expected = "The password is [CREDENTIAL_1] and pXss_w0rd is not it."
    record(input=text, expected=expected, actual=actual)

    assert actual == expected


def test_mask_with_no_entities_leaves_text_unchanged(record):
    """TC-MSK-07 (FR-10): deselecting everything leaves the prompt unchanged."""
    actual, _ = mask(API_EXAMPLE_TEXT, [])
    record(input=API_EXAMPLE_TEXT, expected=API_EXAMPLE_TEXT, actual=actual)

    assert actual == API_EXAMPLE_TEXT


# --- Masking with the model ---------------------------------------------------------------------


@pytest.mark.llm
def test_api_example_is_fully_masked(record):
    """TC-LLM-01 (FR-1, FR-8): the requirement's example prompt is masked as documented."""
    actual, ents = masked_text(API_EXAMPLE_TEXT)
    expected = "Email [PERSON_1] at [EMAIL_1]"
    record(input=API_EXAMPLE_TEXT, expected=expected, actual=actual, model=settings.model_name, detected=found(ents))

    assert actual == expected


MASKING_CASES = [
    ("PERSON", "Please write a thank-you note to Maria Gonzalez for her help.", "Maria Gonzalez"),
    ("EMAIL", "Forward the invoice to billing.team@northwind-traders.com today.", "billing.team@northwind-traders.com"),
    ("PHONE", "Call the customer back on +1 415-555-0132 after lunch.", "+1 415-555-0132"),
    ("ADDRESS", "Ship the replacement to 742 Evergreen Terrace, Springfield, IL 62704.", "742 Evergreen Terrace"),
    ("GOVERNMENT_ID", "My SSN is 123-45-6789, can you check this tax form?", "123-45-6789"),
    ("GOVERNMENT_ID", "Renew passport number X12345678 for Tom before June.", "X12345678"),
    ("FINANCIAL", "Charge the card 4111 1111 1111 1111 for the renewal.", "4111 1111 1111 1111"),
    ("FINANCIAL", "Wire the deposit to IBAN DE89 3704 0044 0532 0130 00 by Monday.", "DE89 3704 0044 0532 0130 00"),
    ("DATE_OF_BIRTH", "Anna Lee was born on 14 March 1985; update her insurance form.", "14 March 1985"),
    ("CREDENTIAL", "Why does this fail? OPENAI_API_KEY=sk-proj-4f9aT2xQ8LmZ7cV1bN3k", "sk-proj-4f9aT2xQ8LmZ7cV1bN3k"),
    ("CREDENTIAL", "Debug this: postgres://admin:Hunter2!@db01:5432/prod", "Hunter2!"),
    ("IP_ADDRESS", "The server at 10.24.6.181 keeps dropping SSH connections.", "10.24.6.181"),
    ("IP_ADDRESS", "Why can't I ping 2001:db8:85a3::8a2e:370:7334 from the VPN?", "2001:db8:85a3::8a2e:370:7334"),
    pytest.param(
        "ORGANIZATION", "Our client Globex Corporation wants the report by Friday.", "Globex Corporation",
        marks=pytest.mark.xfail(strict=False, reason="NFR: lower recall acceptable for ORGANIZATION"),
    ),
    pytest.param(
        "CONFIDENTIAL", "Summarize the risks of Project Nightingale, our unreleased product.", "Project Nightingale",
        marks=pytest.mark.xfail(strict=False, reason="NFR: lower recall acceptable for CONFIDENTIAL"),
    ),
    pytest.param(
        "CONFIDENTIAL", "Check the logs on build-07.corp.internal before the release.", "build-07.corp.internal",
        marks=pytest.mark.xfail(strict=False, reason="NFR: lower recall acceptable for CONFIDENTIAL"),
    ),
]  # fmt: skip


@pytest.mark.llm
@pytest.mark.parametrize(("type_", "text", "value"), MASKING_CASES)
def test_each_entity_type_is_masked(record, type_, text, value):
    """TC-LLM-02 (5.2, FR-8): the sensitive value is gone and a placeholder of its type is in its place."""
    actual, ents = masked_text(text)
    record(input=text, expected=f"{value!r} replaced by [{type_}_n]", actual=actual, detected=found(ents))

    assert value not in actual, f"{value!r} was not masked"
    assert re.search(rf"\[{type_}_\d+\]", actual), f"no [{type_}_n] placeholder"


@pytest.mark.llm
def test_prompt_without_pii_is_unchanged(record):
    """TC-LLM-03 (section 7 'No PII found'): a harmless prompt is not changed."""
    text = "What is the average time complexity of quicksort, and why?"
    actual, ents = masked_text(text)
    record(input=text, expected=text, actual=actual, detected=found(ents))

    assert actual == text


@pytest.mark.llm
def test_repeated_value_is_masked_everywhere(record):
    """TC-LLM-04 (FR-4): every occurrence of a detected value is masked with the same placeholder."""
    text = "John Smith called. Later, John Smith emailed again."
    actual, ents = masked_text(text)
    expected = "[PERSON_1] called. Later, [PERSON_1] emailed again."
    record(input=text, expected=expected, actual=actual, detected=found(ents))

    assert actual == expected


@pytest.mark.llm
def test_full_name_is_masked_as_one_placeholder(record):
    """TC-LLM-05 (FR-5): 'John Smith' becomes one placeholder, not '[PERSON_1] Smith'."""
    text = "John Smith joined the call. John said the numbers look fine."
    actual, ents = masked_text(text)
    record(input=text, expected="starts with [PERSON_1] joined the call; no 'Smith' left", actual=actual, detected=found(ents))

    assert actual.startswith("[PERSON_1] joined the call.")
    assert "Smith" not in actual


@pytest.mark.llm
@pytest.mark.parametrize(
    "text",
    [
        "my email is john dot smith at acme dot com, please remember it",
        "Contact JOHN SMITH (john.smith@acme.com). Mr. Smith prefers mornings.",
        "call jane on five five five, one two three four, ext 9",
    ],
)
def test_only_verbatim_values_are_masked(record, text):
    """TC-LLM-06 (FR-3): values the model reformatted are discarded; masking never garbles the rest of the text."""
    actual, ents = masked_text(text)
    record(input=text, expected="each detected value appears verbatim; text outside placeholders untouched", actual=actual, detected=found(ents))

    for e in ents:
        assert e.value in text
    # The masked text must be the original with only some spans swapped for placeholders.
    pieces = re.split(r"\[[A-Z_]+_\d+\]", actual)
    assert re.fullmatch(".+?".join(map(re.escape, pieces)), text, re.S)


@pytest.mark.llm
def test_masking_is_repeatable(record):
    """TC-LLM-07 (FR-2): temperature 0 gives the same masked prompt twice."""
    first, _ = masked_text(SCENARIO_TEXT)
    second, _ = masked_text(SCENARIO_TEXT)
    record(input=SCENARIO_TEXT, expected=first, actual=second)

    assert first == second


@pytest.mark.llm
def test_conversation_keeps_placeholders_across_prompts(record):
    """TC-LLM-08 (FR-9): the same person keeps [PERSON_1] in a later prompt; a new person gets [PERSON_2]."""
    mapping: dict[str, str] = {}
    first, _ = masked_text("Call John Smith about the invoice.", mapping)
    second, ents = masked_text("Ask Jane Doe to set up a call with John Smith.", mapping)
    record(
        input=["Call John Smith about the invoice.", "Ask Jane Doe to set up a call with John Smith."],
        expected=["Call [PERSON_1] about the invoice.", "Ask [PERSON_2] to set up a call with [PERSON_1]."],
        actual=[first, second],
        detected=found(ents),
    )

    assert first == "Call [PERSON_1] about the invoice."
    assert second == "Ask [PERSON_2] to set up a call with [PERSON_1]."


@pytest.mark.llm
def test_scenario_deselected_entity_stays_unmasked(record):
    """TC-LLM-09 (section 4, FR-10, demo criterion 3): the user deselects Project Falcon; only name and email are masked."""
    ents = detect(SCENARIO_TEXT)
    confirmed = [e for e in ents if "Falcon" not in e.value]
    actual, _ = mask(SCENARIO_TEXT, confirmed)
    expected = "Draft an email to [PERSON_1] ([EMAIL_1]) about the Project Falcon delay"
    record(input=SCENARIO_TEXT, expected=expected, actual=actual, detected=found(ents))

    assert actual == expected


@pytest.mark.llm
def test_demo_prompt_leaks_nothing(record):
    """TC-LLM-10 (demo criterion 1): a name, email, phone number and API key are all masked."""
    text = (
        "Write a follow-up to Priya Patel (priya.patel@contoso.com, +1 206-555-0173) and mention that "
        "the integration key sk-proj-Z8yX7wV6uT5sR4qP3oN2 was revoked."
    )
    secrets = ["Priya Patel", "priya.patel@contoso.com", "+1 206-555-0173", "sk-proj-Z8yX7wV6uT5sR4qP3oN2"]
    actual, ents = masked_text(text)
    record(input=text, expected="none of the 4 values in the masked text", actual=actual, detected=found(ents))

    leaked = [s for s in secrets if s in actual]
    assert not leaked, f"leaked to ChatGPT: {leaked}"


RECALL_SET = [
    (
        "Hi, I'm Daniel Okafor. Reach me at daniel.okafor@brightwave.io or +44 20 7946 0958. "
        "Our staging key is sk_test_51HxQ2eKz8VbN0aPq.",
        [("PERSON", "Daniel Okafor"), ("EMAIL", "daniel.okafor@brightwave.io"),
         ("PHONE", "+44 20 7946 0958"), ("CREDENTIAL", "sk_test_51HxQ2eKz8VbN0aPq")],
    ),
    (
        "Can you rewrite this complaint from Sofia Rossi (sofia.rossi@gmail.com, 555-867-5309)? "
        "She pasted her password Tr0ub4dor&3 in the ticket.",
        [("PERSON", "Sofia Rossi"), ("EMAIL", "sofia.rossi@gmail.com"),
         ("PHONE", "555-867-5309"), ("CREDENTIAL", "Tr0ub4dor&3")],
    ),
    (
        "Add Kenji Watanabe to the call list: kenji.w@sakura-tech.jp, +81 3-1234-5678. "
        "Use token ghp_A1b2C3d4E5f6G7h8I9j0KlMnOpQrStUv for the repo.",
        [("PERSON", "Kenji Watanabe"), ("EMAIL", "kenji.w@sakura-tech.jp"),
         ("PHONE", "+81 3-1234-5678"), ("CREDENTIAL", "ghp_A1b2C3d4E5f6G7h8I9j0KlMnOpQrStUv")],
    ),
    (
        "Draft a reply to Emily Carter at emily.carter@outlook.com; her mobile is 07700 900123. "
        "The AWS secret is wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY.",
        [("PERSON", "Emily Carter"), ("EMAIL", "emily.carter@outlook.com"),
         ("PHONE", "07700 900123"), ("CREDENTIAL", "wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY")],
    ),
    (
        "Ahmed Hassan (ahmed.hassan@globalfreight.com, +971 50 123 4567) asked why the connection string "
        "Server=sql01;User Id=sa;Password=P@ssw0rd123; fails.",
        [("PERSON", "Ahmed Hassan"), ("EMAIL", "ahmed.hassan@globalfreight.com"),
         ("PHONE", "+971 50 123 4567"), ("CREDENTIAL", "P@ssw0rd123")],
    ),
    (
        "Schedule a meeting with Laura Schmidt, laura.schmidt@bauwerk.de, phone +49 30 901820. "
        "The shared login password is Winter2026!",
        [("PERSON", "Laura Schmidt"), ("EMAIL", "laura.schmidt@bauwerk.de"),
         ("PHONE", "+49 30 901820"), ("CREDENTIAL", "Winter2026!")],
    ),
    (
        "Our contractor Carlos Mendez can be reached at c.mendez@solaris.mx or +52 55 1234 5678. "
        "His API key is AIzaSyD-9tSrke72PouQMnMX-a7eZSW0jkFMBWY.",
        [("PERSON", "Carlos Mendez"), ("EMAIL", "c.mendez@solaris.mx"),
         ("PHONE", "+52 55 1234 5678"), ("CREDENTIAL", "AIzaSyD-9tSrke72PouQMnMX-a7eZSW0jkFMBWY")],
    ),
    (
        "Thank Grace Kim for the review: grace.kim@northpeak.ca, 604-555-0147. "
        "Then rotate the Slack token xoxb-2048-4096-AbCdEfGhIjKlMnOp.",
        [("PERSON", "Grace Kim"), ("EMAIL", "grace.kim@northpeak.ca"),
         ("PHONE", "604-555-0147"), ("CREDENTIAL", "xoxb-2048-4096-AbCdEfGhIjKlMnOp")],
    ),
    (
        "Send the contract to Mohammed Al-Farsi at m.alfarsi@desertrose.ae, tel. +966 11 234 5678, "
        "and include the SFTP password Qz7!mR2#vL9p.",
        [("PERSON", "Mohammed Al-Farsi"), ("EMAIL", "m.alfarsi@desertrose.ae"),
         ("PHONE", "+966 11 234 5678"), ("CREDENTIAL", "Qz7!mR2#vL9p")],
    ),
    (
        "Remind Olivia Brown (olivia.brown@lumen.co.uk, +44 7911 123456) that the bearer token "
        "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxMjMifQ.abc123 expires today.",
        [("PERSON", "Olivia Brown"), ("EMAIL", "olivia.brown@lumen.co.uk"),
         ("PHONE", "+44 7911 123456"), ("CREDENTIAL", "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxMjMifQ.abc123")],
    ),
]  # fmt: skip


@pytest.mark.llm
def test_masking_recall_at_least_90_percent(record):
    """TC-LLM-11 (NFR detection quality): >= 90% of PERSON, EMAIL, PHONE and CREDENTIAL values are masked."""
    masked_count: dict[str, int] = {}
    total: dict[str, int] = {}
    leaked = []
    for text, labels in RECALL_SET:
        actual, _ = masked_text(text)
        for type_, value in labels:
            total[type_] = total.get(type_, 0) + 1
            if value in actual:
                leaked.append(f"{type_}: {value}")
            else:
                masked_count[type_] = masked_count.get(type_, 0) + 1
    recall = {t: masked_count.get(t, 0) / n for t, n in total.items()}
    record(
        input=f"{len(RECALL_SET)} prompts, {sum(total.values())} labelled values",
        expected="masked >= 90% per type",
        actual={t: f"{r:.0%}" for t, r in recall.items()},
        leaked=leaked,
    )

    for type_, r in recall.items():
        assert r >= 0.9, f"{type_} recall {r:.0%}; leaked {[v for v in leaked if v.startswith(type_)]}"
