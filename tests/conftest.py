import html
from pathlib import Path
import json
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
    if hasattr(value, "model_dump"):
        value = value.model_dump()
    return html.escape(str(value)) if value is not None else ""


def pytest_html_results_table_header(cells):
    # cells: Result, Test, Duration, Links -> replace Test/Links with richer columns
    cells[:] = [
        cells[0],
        '<th class="sortable" data-column-type="file">File</th>',
        cells[1].replace("Test", "Test", 1),
        "<th>Input</th>",
        "<th>Expected</th>",
        "<th>Actual</th>",
        "<th>Details</th>",
        cells[2],
    ]


def pytest_html_results_table_row(report, cells):
    rec = getattr(report, "record", {}) or {}
    file, _, test = report.nodeid.partition("::")
    details = {k: v for k, v in rec.items() if k not in ("input", "expected", "actual")}
    details_html = "<br>".join(f"<b>{html.escape(k)}</b>: {_fmt(v)}" for k, v in details.items())
    cells[:] = [
        cells[0],
        f'<td class="col-file">{html.escape(file)}</td>',
        f'<td class="col-name">{html.escape(test)}</td>',
        f"<td><pre>{_fmt(rec.get('input'))}</pre></td>",
        f"<td><pre>{_fmt(rec.get('expected'))}</pre></td>",
        f"<td><pre>{_fmt(rec.get('actual'))}</pre></td>",
        f"<td>{details_html}</td>",
        cells[2],
    ]


@pytest.hookimpl(tryfirst=True)
def pytest_configure(config):
    """Report path: reports/<file>.html when one test file is run, else reports/report.html.
    An explicit --html=... always wins."""
    if config.option.htmlpath:
        return
    files = {Path(a.split("::")[0]).stem for a in config.args if a.split("::")[0].endswith(".py")}
    name = f"{files.pop()}" if len(files) == 1 and all(a.endswith(".py") or ".py::" in a for a in config.args) else "report"
    config.option.htmlpath = f"reports/{name}.html"
