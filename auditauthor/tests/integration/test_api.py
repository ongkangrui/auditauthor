from conftest import FakeModel, observation
from fastapi.testclient import TestClient

from auditauthor.api.app import create_app
from auditauthor.config import Settings
from auditauthor.domain.models import Extraction


def test_background_worker_executes_persisted_job(tmp_path, pdf_bytes):
    import time

    app = create_app(Settings(data_dir=tmp_path, model="openai/test"), FakeModel())
    with TestClient(app) as client:
        _, job = submit(client, pdf_bytes)
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            state = client.get(f"/analyses/{job['id']}").json()
            if state["status"] == "complete":
                break
            time.sleep(0.05)
        assert state["status"] == "complete"


def setup(tmp_path, model=None):
    app = create_app(
        Settings(data_dir=tmp_path, model="openai/test"),
        client=model or FakeModel(),
        start_worker=False,
    )
    return app, TestClient(app)


def submit(client, pdf_bytes):
    response = client.post(
        "/reports", files={"file": ("../../report.pdf", pdf_bytes, "application/pdf")}
    )
    assert response.status_code == 201
    report = response.json()
    response = client.post("/analyses", json={"report_ids": [report["id"]]})
    assert response.status_code == 202
    return report, response.json()


def test_full_flow_duplicate_export_and_restart(tmp_path, pdf_bytes):
    app, client = setup(tmp_path)
    report, job = submit(client, pdf_bytes)
    assert report["name"] == "report.pdf"
    again = client.post("/reports", files={"file": ("again.pdf", pdf_bytes)}).json()
    assert again["id"] == report["id"]
    app.state.runner.run(app.state.repository.get_job(job["id"]))
    result = client.get(f"/analyses/{job['id']}").json()
    assert result["status"] == "complete"
    assert result["resolved_models"] == ["fake-snapshot"]
    assert client.get(f"/reports/{report['id']}/file").content == pdf_bytes
    findings = client.get(f"/analyses/{job['id']}/findings").json()
    assert len(findings) == 1
    assert client.get(f"/analyses/{job['id']}/export?format=csv").text.startswith("id,report_id")
    assert client.get(f"/analyses/{job['id']}/export").json()["findings"] == findings
    assert client.post(f"/analyses/{job['id']}/retry").status_code == 409
    _, reopened = setup(tmp_path)
    assert reopened.get(f"/analyses/{job['id']}/findings").json() == findings


def test_partial_citation_failure_retry(tmp_path, pdf_bytes):
    class MixedModel(FakeModel):
        broken = True

        def generate(self, system, content, schema, model):
            if schema is Extraction and self.broken:
                self.extract_calls += 1
                invalid = observation(
                    evidence=[
                        {
                            "page": 1,
                            "excerpt": "Invented evidence that does not appear in the source.",
                        }
                    ]
                )
                return Extraction(observations=[observation(), invalid]), "fake"
            return super().generate(system, content, schema, model)

    fake = MixedModel()
    app, client = setup(tmp_path, fake)
    _, job = submit(client, pdf_bytes)
    app.state.runner.run(app.state.repository.get_job(job["id"]))
    assert client.get(f"/analyses/{job['id']}").json()["status"] == "partial"
    assert len(client.get(f"/analyses/{job['id']}/findings").json()) == 1
    fake.broken = False
    assert client.post(f"/analyses/{job['id']}/retry").status_code == 202
    app.state.runner.run(app.state.repository.get_job(job["id"]))
    assert client.get(f"/analyses/{job['id']}").json()["status"] == "complete"


def test_retry_does_not_repeat_completed_extraction(tmp_path, pdf_bytes):
    class FailsConsolidation(FakeModel):
        fail = True

        def generate(self, system, content, schema, model):
            if schema is not Extraction and self.fail:
                raise RuntimeError("Provider temporarily unavailable after bounded retries.")
            return super().generate(system, content, schema, model)

    fake = FailsConsolidation()
    app, client = setup(tmp_path, fake)
    _, job = submit(client, pdf_bytes)
    app.state.runner.run(app.state.repository.get_job(job["id"]))
    assert fake.extract_calls == 1
    fake.fail = False
    client.post(f"/analyses/{job['id']}/retry")
    app.state.runner.run(app.state.repository.get_job(job["id"]))
    assert fake.extract_calls == 1
    assert client.get(f"/analyses/{job['id']}").json()["status"] == "complete"


def test_interrupted_recovery_and_missing_ids(tmp_path, pdf_bytes):
    app, client = setup(tmp_path)
    _, job = submit(client, pdf_bytes)
    claimed = app.state.repository.next_job()
    assert claimed["status"] == "running"
    app.state.repository.recover()
    assert client.get(f"/analyses/{job['id']}").json()["status"] == "interrupted"
    assert client.post("/analyses", json={"report_ids": ["missing"]}).status_code == 404
    assert client.get("/reports/missing/file").status_code == 404
    assert client.post("/reports", files={"file": ("bad.pdf", b"bad")}).status_code == 422


def test_queue_bounded(tmp_path, pdf_bytes):
    app = create_app(
        Settings(data_dir=tmp_path, model="openai/test", max_pending_jobs=1), FakeModel(), False
    )
    client = TestClient(app)
    report, _ = submit(client, pdf_bytes)
    assert client.post("/analyses", json={"report_ids": [report["id"]]}).status_code == 429
