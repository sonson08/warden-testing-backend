import html
from collections import Counter, defaultdict
from pathlib import Path
import json
import pprint
import urllib.error
import urllib.request

import pytest

from ai_testing.config import settings


def _ollama_models() -> tuple[set[str], str | None]:
    """Models pulled in Ollama, plus a skip reason if Ollama is unreachable."""
    root = settings.ollama_base_url.removesuffix("/v1")
    try:
        with urllib.request.urlopen(f"{root}/api/tags", timeout=3) as resp:
            tags = json.load(resp)
    except (urllib.error.URLError, OSError) as exc:
        return set(), f"Ollama not reachable at {root} ({exc}). Run: ollama serve"
    return {m["name"] for m in tags.get("models", [])}, None


def _model_of(item) -> str | None:
    """The `model` parameter of a test, if it has one."""
    callspec = getattr(item, "callspec", None)
    return callspec.params.get("model") if callspec else None


def pytest_generate_tests(metafunc):
    """Tests that take a `model` argument run once per model in settings.model_names."""
    if "model" in metafunc.fixturenames:
        metafunc.parametrize("model", settings.model_names)


def pytest_collection_modifyitems(config, items):
    pulled, down = _ollama_models()
    for item in items:
        if "llm" not in item.keywords:
            continue
        model = _model_of(item) or settings.model_name
        if down:
            item.add_marker(pytest.mark.skip(reason=down))
        # Ollama reads a name without a tag as ":latest" (`ollama pull llama3.2` is listed as llama3.2:latest).
        elif (model if ":" in model else f"{model}:latest") not in pulled:
            item.add_marker(pytest.mark.skip(reason=f"Model {model!r} not pulled. Run: ollama pull {model}"))


def pytest_collection_finish(session):
    """Load every model the selected LLM tests use before the first test, so no test's duration includes the load."""
    models = {
        _model_of(item) or settings.model_name
        for item in session.items
        if "llm" in item.keywords and not item.get_closest_marker("skip")
    }
    root = settings.ollama_base_url.removesuffix("/v1")
    reporter = session.config.pluginmanager.get_plugin("terminalreporter")
    for model in sorted(models):
        if reporter:
            reporter.write_line(f"Preloading {model} ...")
        # A generate request without a prompt only loads the model into memory.
        body = json.dumps({"model": model, "keep_alive": "30m"}).encode()
        req = urllib.request.Request(f"{root}/api/generate", data=body, headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=300):
                pass
        except (urllib.error.URLError, OSError) as exc:
            if reporter:
                reporter.write_line(f"Could not preload {model}: {exc}")


# --- HTML report: per-file rows with input / expected / actual / extras -------------------------


@pytest.fixture
def record(request):
    """Call record(input=..., expected=..., actual=..., **extra) so the values show in the HTML report."""
    data: dict = {}
    request.node.report_record = data
    return data.update


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_makereport(item, call):
    outcome = yield
    report = outcome.get_result()
    report.model = _model_of(item)
    if call.when == "call":
        report.record = getattr(item, "report_record", {})


# Per-model outcome counts for the model dropdown in the report summary.
_model_stats: dict[str, Counter] = defaultdict(Counter)


def pytest_runtest_logreport(report):
    model = getattr(report, "model", None)
    if not model:
        return
    if report.failed:
        _model_stats[model]["failed"] += 1
    elif report.skipped and not hasattr(report, "wasxfail"):
        _model_stats[model]["skipped"] += 1
    elif report.when == "call":
        _model_stats[model]["xfailed" if report.skipped else "passed"] += 1


def _fmt(value) -> str:
    if value is None:
        return ""
    if hasattr(value, "model_dump"):
        value = value.model_dump()
    # Narrow pretty-printing keeps lists/dicts one item per line instead of one very wide line.
    text = value if isinstance(value, str) else pprint.pformat(value, width=50, sort_dicts=False)
    return html.escape(text)


_ACRONYMS = {"api": "API", "pii": "PII", "llm": "LLM", "url": "URL", "ip": "IP"}


def _readable(name: str) -> str:
    """test_api_example_is_fully_masked -> API example is fully masked"""
    words = [_ACRONYMS.get(w, w) for w in name.removeprefix("test_").split("_")]
    return " ".join(words)[:1].upper() + " ".join(words)[1:]


def _fmt_test(test: str) -> str:
    """Readable test name, with long parametrize ids shortened onto their own line (full id on hover)."""
    name, bracket, params = test.partition("[")
    name = _readable(name)
    if not bracket:
        return html.escape(name)
    params = params.removesuffix("]")
    short = params if len(params) <= 40 else params[:39] + "…"
    return f'{html.escape(name)}<span class="params" title="{html.escape(params)}">[{html.escape(short)}]</span>'


def pytest_html_results_table_header(cells):
    # cells: Result, Test, Duration, Links -> replace Links with richer columns
    cells[:] = [
        cells[0],
        cells[1],
        "<th>Input</th>",
        "<th>Expected</th>",
        "<th>Actual</th>",
        "<th>Details</th>",
        cells[2],
    ]


def pytest_html_results_table_row(report, cells):
    rec = getattr(report, "record", {}) or {}
    test = report.nodeid.partition("::")[2]
    details = {k: v for k, v in rec.items() if k not in ("input", "expected", "actual")}
    details_html = "<br>".join(f"<b>{html.escape(k)}</b>: {_fmt(v)}" for k, v in details.items())
    # data-model lets the report's model dropdown hide rows of other models.
    model_attr = f' data-model="{html.escape(report.model)}"' if getattr(report, "model", None) else ""
    cells[:] = [
        cells[0],
        f'<td class="col-name"{model_attr}>{_fmt_test(test)}</td>',
        f"<td><pre>{_fmt(rec.get('input'))}</pre></td>",
        f"<td><pre>{_fmt(rec.get('expected'))}</pre></td>",
        f"<td><pre>{_fmt(rec.get('actual'))}</pre></td>",
        f"<td>{details_html}</td>",
        cells[2],
    ]


def pytest_html_results_summary(prefix, summary, postfix, session):
    files = sorted({item.nodeid.partition("::")[0] for item in session.items})
    label = "File" if len(files) == 1 else "Files"
    prefix.append(f'<p class="test-files"><b>{label}:</b> {", ".join(html.escape(f) for f in files)}</p>')
    models = [m for m in settings.model_names if m in _model_stats]
    if models:
        prefix.append(_model_filter(models))


# Rows of other models are hidden with a CSS rule rather than by touching the rows, because
# pytest-html re-renders the table (sorting, outcome filters). Rows without a model always show.
_MODEL_FILTER_SCRIPT = """
<style id="model-filter-style"></style>
<script>
document.getElementById("model-filter").addEventListener("change", (e) => {
  const model = e.target.value;
  document.getElementById("model-filter-style").textContent = model
    ? `#results-table tbody:has(td[data-model]):not(:has(td[data-model="${CSS.escape(model)}"])) { display: none; }`
    : "";
});
</script>
"""


def _model_filter(models: list[str]) -> str:
    """Dropdown that shows one model's rows; each option carries that model's outcome counts."""
    options = ['<option value="">All models</option>']
    for m in models:
        counts = ", ".join(f"{n} {k}" for k, n in _model_stats[m].items())
        options.append(f'<option value="{html.escape(m)}">{html.escape(m)} ({counts})</option>')
    select = f'<select id="model-filter">{"".join(options)}</select>'
    return f'<p class="model-filter"><label for="model-filter"><b>Model:</b></label> {select}</p>{_MODEL_FILTER_SCRIPT}'


@pytest.hookimpl(tryfirst=True)
def pytest_configure(config):
    """Report path: reports/<file>.html when one test file is run, else reports/report.html.
    An explicit --html=... always wins."""
    config.option.css.append(str(Path(__file__).with_name("report.css")))
    if config.option.htmlpath:
        return
    files = {Path(a.split("::")[0]).stem for a in config.args if a.split("::")[0].endswith(".py")}
    name = f"{files.pop()}" if len(files) == 1 and all(a.endswith(".py") or ".py::" in a for a in config.args) else "report"
    config.option.htmlpath = f"reports/{name}.html"
