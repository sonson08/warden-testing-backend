# ai-testing

Boilerplate for testing a local LLM (Ollama, Distil-PII Llama 3.2 3B) with Pydantic AI + pytest.

## Setup (WSL / Linux)

```bash
ollama serve &                 # if not already running
ollama pull hf.co/mradermacher/Distil-PII-Llama-3.2-3B-Instruct-GGUF:Q4_K_M
ollama pull qwen2.5:7b
python3 -m venv .venv
.venv/bin/pip install -e ".[dev]"
cp .env.example .env           # optional: change model / URL
```

## Run

```bash
.venv/bin/pytest -v              # all tests
.venv/bin/pytest -m "not llm"    # skip tests that hit the model
.venv/bin/pytest tests/test_smoke.py                 # a single test file
.venv/bin/pytest tests/test_smoke.py::test_model_returns_valid_structured_answer   # a single test
```

Tests marked `@pytest.mark.llm` are skipped automatically if Ollama is down or the model isn't pulled.

### Comparing models

A test that takes a `model` argument runs once per model in `MODEL_NAMES` (default `["hf.co/mradermacher/Distil-PII-Llama-3.2-3B-Instruct-GGUF:Q4_K_M", "qwen2.5:7b"]`), so one run checks every model. Models that aren't pulled are skipped.

```bash
MODEL_NAMES='["hf.co/mradermacher/Distil-PII-Llama-3.2-3B-Instruct-GGUF:Q4_K_M"]' .venv/bin/pytest tests/test_masking.py   # just one model
.venv/bin/pytest tests/test_masking.py -k "Distil-PII"   # same, using the test ids
```

The report has a **Model** dropdown in the summary that shows one model's rows, with its passed/failed counts.

## HTML report

Every `pytest` run writes a self-contained HTML report, git-ignored and overwritten on each run. One row per test: Result, File, Test, Input, Expected, Actual, Details (model, tokens, ...), Duration.

- Whole suite -> `reports/report.html`
- A single test file -> `reports/<file>.html` (e.g. `tests/test_smoke.py` -> `reports/test_smoke.html`), containing only that file's tests

Tests fill the Input/Expected/Actual/Details columns with the `record` fixture: `record(input=..., expected=..., actual=..., model=...)`.

Open it (use `reports/<file>.html` for a per-file report):

- **From WSL:** opens in the Windows default browser.
  ```bash
  explorer.exe reports/report.html
  ```
- **From Windows:** paste the path into a browser or Explorer address bar:
  `\\wsl.localhost\Ubuntu\home\lyzer\hackathon-testing\reports\report.html`
- **From VS Code:** right-click the file in the Explorer panel, choose "Reveal in File Explorer", then double-click it. (VS Code can't render it without an HTML preview extension.)

The report is a single self-contained file, so it can be copied or emailed without the project.

To write it elsewhere: `.venv/bin/pytest --html=path/to/report.html`.

## Layout

- `src/ai_testing/config.py` – settings (env vars / `.env`)
- `src/ai_testing/llm.py` – `build_agent(OutputModel, instructions)` → typed Pydantic AI agent (uses `NativeOutput`, i.e. Ollama JSON-schema mode, because tool-call output is unreliable on small models)
- `src/ai_testing/schemas.py` – Pydantic output models
- `tests/` – pytest suite

## Adding a test

1. Define the expected output shape as a Pydantic model in `schemas.py`.
2. `agent = build_agent(MyModel, instructions="...")`
3. `result = agent.run_sync("prompt")` and assert on `result.output`.
