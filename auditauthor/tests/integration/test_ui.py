from pathlib import Path

import httpx
from conftest import observation
from streamlit.testing.v1 import AppTest

APP = Path(__file__).resolve().parents[2] / "src/auditauthor/ui/app.py"


def test_review_ui_renders_evidence_and_filters(monkeypatch, pdf_bytes):
    finding = {**observation(), "id": "finding-1", "report_id": "report-1"}
    job = {
        "id": "job-1",
        "status": "complete",
        "created_at": "2026-10-21T12:00:00+00:00",
        "model": "openai/test",
        "prompt_version": "1.0",
        "schema_version": "1.0",
        "report_ids": ["report-1"],
        "errors": [],
        "coverage": {"total_chunks": 1, "completed_chunks": 1, "page_warnings": []},
    }
    data = {
        "/reports": [{"id": "report-1", "name": "sample.pdf"}],
        "/analyses": [job],
        "/analyses/job-1": job,
        "/analyses/job-1/findings": [finding],
        "/analyses/job-1/insights": [],
    }

    def request(method, url, **kwargs):
        path = httpx.URL(url).path
        if path.endswith("/file"):
            return httpx.Response(200, content=pdf_bytes, request=httpx.Request(method, url))
        return httpx.Response(200, json=data.get(path, {}), request=httpx.Request(method, url))

    monkeypatch.setattr(httpx, "request", request)
    app = AppTest.from_file(str(APP)).run(timeout=30)
    assert not app.exception
    assert app.title[0].value == "AuditAuthor"
    assert len(app.dataframe) == 1
    assert any("Physical PDF page 1" in item.value for item in app.markdown)
    next(widget for widget in app.selectbox if widget.label == "Theme").select(
        "logging/monitoring"
    ).run()
    assert not app.exception


def test_empty_ui_and_backend_error(monkeypatch):
    monkeypatch.setattr(
        httpx,
        "request",
        lambda method, url, **kwargs: httpx.Response(
            200, json=[], request=httpx.Request(method, url)
        ),
    )
    app = AppTest.from_file(str(APP)).run(timeout=20)
    assert not app.exception
    assert any("start an analysis" in item.value for item in app.info)
