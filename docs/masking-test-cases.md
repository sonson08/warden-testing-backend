# Test cases: masking

Masking test cases for [requirement.md](requirement.md), run directly against Ollama (`qwen2.5:3b`). No backend is involved. Unmasking (restoring the original values) is out of scope here.

The automated cases are in [tests/test_masking.py](../tests/test_masking.py). Each test's docstring starts with its case ID.

## How it works

1. **Detect.** The model receives the prompt and returns `{type, value}` for each sensitive item, using JSON-schema output. The instructions live in [src/ai_testing/masking.py](../src/ai_testing/masking.py) as `DETECTION_INSTRUCTIONS`.
2. **Filter.** Any value that does not appear verbatim in the prompt is dropped (FR-3).
3. **Mask.** Plain code replaces every occurrence of each value with `[TYPE_N]`, longest values first (FR-4, FR-5, FR-8, FR-9).

The model only does step 1. Steps 2 and 3 are deterministic code.

Distil-PII models are fine-tuned on their own prompt and reply format, so they get the prompt from their model card (`DISTIL_SYSTEM_PROMPT`), and their tokens are mapped to the 5.2 types. Distil-PII has no tokens for credentials, IP addresses, dates of birth, organizations or confidential data, so it cannot pass those cases.

## Data-driven cases (tests/data/masking_cases.json)

- `OUT-nn` cases pass when every value the expected text replaces is gone, each expected placeholder type appears, no other type appears, and the rest of the text is kept (TC-LLM-02). Numbering and exact span boundaries are not compared.
- `KEEP-nn` cases must come back exactly as sent.
- `"exact": true` compares the whole string; `"xfail": "<reason>"` marks a known limit.

Policy decisions behind the expected values:

- A city, region or country on its own is not an address; street, block, lot or unit level is.
- Obvious sample values (`user@example.com`, `your-api-key-here`) are not masked.
- A connection string is one `CREDENTIAL`; an IP address is masked without its port; a phone extension is part of the phone number; a CVV is `FINANCIAL`.
- Case variants of a value (`JOHN.SMITH@ACME.COM` and `john.smith@acme.com`) get separate placeholders. This is a known limit.

## Running

```bash
.venv/bin/pytest tests/test_masking.py -v            # report: reports/test_masking.html
.venv/bin/pytest tests/test_masking.py -m "not llm"  # placeholder rules only, no Ollama
```

## Placeholder rules (no LLM)

These check step 3 on its own. When an LLM case fails, these rule out the masking code as the cause.

| ID        | Req         | Case                                                                       | Expected                                              |
| --------- | ----------- | -------------------------------------------------------------------------- | ----------------------------------------------------- |
| TC-MSK-01 | FR-8, FR-10 | Mask only `John Smith` in "Email John Smith at john.smith@acme.com"        | `Email [PERSON_1] at john.smith@acme.com`             |
| TC-MSK-02 | FR-4, FR-8  | The same name twice                                                         | Both occurrences become `[PERSON_1]`                   |
| TC-MSK-03 | FR-8, FR-9  | Two people and one email                                                   | `[PERSON_1]`, `[PERSON_2]`, `[EMAIL_1]`, numbered in order of appearance |
| TC-MSK-04 | FR-9        | Two prompts in one conversation                                            | John keeps `[PERSON_1]`; Jane gets `[PERSON_2]`        |
| TC-MSK-05 | FR-5        | Both `John` and `John Smith` are entities                                  | `John Smith` is one placeholder                       |
| TC-MSK-06 | FR-8        | Value with regex characters (`p@ss.w0rd*(x)+[1]`)                          | Matched literally                                     |
| TC-MSK-07 | FR-10       | No entities confirmed                                                      | Prompt unchanged                                      |

## Masking with the model

| ID        | Req          | Case                                                                                                   | Expected                                                                |
| --------- | ------------ | ------------------------------------------------------------------------------------------------------ | ----------------------------------------------------------------------- |
| TC-LLM-01 | FR-1, FR-8   | "Email John Smith at john.smith@acme.com"                                                              | `Email [PERSON_1] at [EMAIL_1]`                                         |
| TC-LLM-02 | §5.2, FR-8   | 16 prompts covering every type, including IPv4 and IPv6, SSN and passport, card and IBAN               | The value is gone, and a `[TYPE_n]` of the right type is in the text. ORGANIZATION and CONFIDENTIAL are allowed to fail (§8) |
| TC-LLM-03 | §7           | A prompt with no PII                                                                                   | Unchanged                                                               |
| TC-LLM-04 | FR-4         | A name repeated in the prompt                                                                          | Every occurrence is `[PERSON_1]`                                        |
| TC-LLM-05 | FR-5         | "John Smith joined... John said..."                                                                    | `John Smith` is one placeholder, and no stray `Smith` is left           |
| TC-LLM-06 | FR-3         | Prompts that tempt the model to reformat values ("john dot smith at acme dot com", `JOHN SMITH`, spelled-out numbers) | Only verbatim values are masked; the rest of the text is untouched |
| TC-LLM-07 | FR-2         | The same prompt masked twice                                                                           | Identical result                                                        |
| TC-LLM-08 | FR-9         | Two prompts in one conversation                                                                        | `[PERSON_1]` reused; the new person gets `[PERSON_2]`                   |
| TC-LLM-09 | §4, FR-10    | The §4 scenario with Project Falcon deselected                                                         | `Draft an email to [PERSON_1] ([EMAIL_1]) about the Project Falcon delay` |
| TC-LLM-10 | §12 #1       | A name, email, phone number and API key                                                                | None of the four values left in the masked text                         |
| TC-LLM-11 | §8 quality   | 10 labelled prompts with 10 each of PERSON, EMAIL, PHONE and CREDENTIAL                                | At least 90% of each type masked                                        |

TC-LLM-02 checks that the value is removed and that a placeholder of the expected type appears. It does not require the model to return the exact same span as the label. For example, masking the whole `postgres://admin:Hunter2!@...` string still counts as masking `Hunter2!`.

## Out of scope here

These belong in the backend's own tests:
- Unmasking (FR-12 to FR-15).
- Sessions and expiry (FR-16 to FR-18).
- The HTTP API, error codes, CORS, logging.
- Chunking long prompts (FR-6).
- Latency.
