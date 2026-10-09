import html
from pathlib import Path
import json
import pprint
import urllib.error
import urllib.request

import pytest

from ai_testing.config import settings


def _ollama_ready() -> str | None:
    """Return None if Ollama is up and has the model, else a skip reason."""
    root = settings.ollama_base_url.removesuffix("/v1")
    try:
        with urllib.request.urlopen(f"{root}/api/tags", timeout=3) as resp:
            tags = json.load(resp)
    except (urllib.error.URLError, OSError) as exc:
        return f"Ollama not reachable at {root} ({exc}). Run: ollama serve"
    names = {m["name"] for m in tags.get("models", [])}
    if settings.model_name not in names:
        return f"Model {settings.model_name!r} not pulled. Run: ollama pull {settings.model_name}"
    return None


def pytest_collection_modifyitems(config, items):
    reason = _ollama_ready()
    if reason is None:
        return
    for item in items:
        if "llm" in item.keywords:
            item.add_marker(pytest.mark.skip(reason=reason))


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
    if call.when == "call":
        report.record = getattr(item, "report_record", {})


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
    cells[:] = [
        cells[0],
        f'<td class="col-name">{_fmt_test(test)}</td>',
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
