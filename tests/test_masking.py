"""Masking tests for the ChatGPT AI Firewall (docs/requirement.md), run directly against Ollama.

The test data lives in tests/data/masking_cases.json, grouped by category and keyed by case ID
(OUT-nn: sensitive values are masked; KEEP-nn: text without PII is left alone).
Placeholder types are the categories in the detection prompt (EntityType in src/ai_testing/schemas.py).
A case may set "xfail" (a known limit, with the reason) or "exact" (compare the whole string).
Every test runs once per model in settings.model_names (the `model` argument, see conftest.py).
"""

import json
import re
from collections import Counter
from pathlib import Path

import pytest

from ai_testing.masking import detect, mask
from ai_testing.schemas import Entity

CASES = json.loads((Path(__file__).parent / "data" / "masking_cases.json").read_text(encoding="utf-8"))
MASKING = CASES["masking_correctness"]
NON_PII = CASES["non_pii_untouched"]

PLACEHOLDER = re.compile(r"\[([A-Z_]+?)_\d+\]")
# Small words a model may fairly include in or leave out of a value ("on the 5th of June" vs "the 5th of June").
FILLER = {"a", "an", "the", "on", "in", "at", "of", "to", "and", "or", "near"}


def masked_text(text: str, model: str) -> tuple[str, list[Entity]]:
    ents = detect(text, model)
    return mask(text, ents)[0], ents


def found(ents: list[Entity]) -> list[str]:
    return [f"{e.type}: {e.value}" for e in ents]


def words(text: str) -> Counter:
    """Lowercase words of text, ignoring placeholders."""
    return Counter(re.findall(r"\w+", PLACEHOLDER.sub(" ", text).lower()))


def masking_problems(text: str, expected: str, actual: str) -> list[str]:
    """What is wrong with `actual`, judged as in docs/masking-test-cases.md TC-LLM-02.

    The sensitive values are the parts of `text` that `expected` replaces with placeholders. They must be gone,
    each expected placeholder type must appear, and no other words may be masked. Placeholder numbering and
    exact span boundaries are not compared, so "[ADDRESS_1], [ADDRESS_2]" for one address passes.
    """
    literals = PLACEHOLDER.split(expected)[::2]
    slots = PLACEHOLDER.findall(expected)
    match = re.fullmatch("(.+?)".join(map(re.escape, literals)), text, re.DOTALL)
    assert match, f"Test data error: expected {expected!r} does not line up with input {text!r}"

    kept, got = words("".join(literals)), words(actual)
    problems = [f"text changed or over-masked: {w!r} missing" for w in kept if got[w] < kept[w] and w not in FILLER]
    leaked = [w for w in words(" ".join(match.groups())) if got[w] > kept[w] and w not in FILLER]
    if leaked:
        problems.append(f"sensitive words still in the text: {leaked}")
    actual_types = set(PLACEHOLDER.findall(actual))
    problems += [f"no [{t}_n] placeholder" for t in sorted(set(slots) - actual_types)]
    problems += [f"unexpected [{t}_n] placeholder" for t in sorted(actual_types - set(slots))]
    return problems


def cases(group: dict) -> list:
    """One param per case ID; cases with an empty input are skipped until they are written, "xfail" cases are known limits."""
    params = []
    for case_id, c in group.items():
        marks = []
        if not c["input"]:
            marks.append(pytest.mark.skip(reason="no input yet"))
        if c.get("xfail"):
            marks.append(pytest.mark.xfail(reason=c["xfail"], strict=False))
        params.append(pytest.param(case_id, id=case_id, marks=marks))
    return params


@pytest.mark.llm
@pytest.mark.parametrize("case_id", cases(MASKING))
def test_sensitive_values_are_masked(record, model, case_id):
    """OUT-nn: each sensitive value becomes a placeholder of its type; the rest of the text is unchanged."""
    case = MASKING[case_id]
    actual, ents = masked_text(case["input"], model)
    problems = [] if case.get("exact") else masking_problems(case["input"], case["expected"], actual)
    record(case=case_id, input=case["input"], expected=case["expected"], actual=actual, model=model, detected=found(ents), problems=problems)

    if case.get("exact"):
        assert actual == case["expected"]
    else:
        assert not problems, "; ".join(problems)


@pytest.mark.llm
@pytest.mark.parametrize("case_id", cases(NON_PII))
def test_non_pii_is_untouched(record, model, case_id):
    """KEEP-nn: text without personal data comes back exactly as it was sent."""
    case = NON_PII[case_id]
    actual, ents = masked_text(case["input"], model)
    record(case=case_id, input=case["input"], expected=case["expected"], actual=actual, model=model, detected=found(ents))

    assert actual == case["expected"]
