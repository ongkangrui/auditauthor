import csv
import io
import json
import os
from contextlib import asynccontextmanager

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, UploadFile
from fastapi.responses import FileResponse, Response
from starlette.concurrency import run_in_threadpool

from auditauthor.adapters.llm import LiteLLMClient
from auditauthor.adapters.repository import Repository
from auditauthor.config import Settings
from auditauthor.domain.models import (
    PROMPT_VERSION,
    SCHEMA_VERSION,
    AnalysisRequest,
    AnalysisSummary,
    Finding,
    Insight,
    ReportSummary,
)
from auditauthor.services.ingestion import IngestionService
from auditauthor.services.jobs import AnalysisRunner, Worker, new_job


def report_summary(report):
    return {k: v for k, v in report.items() if k != "pages"}


def job_summary(job):
    return {
        k: v
        for k, v in job.items()
        if k not in ("chunks", "findings", "insights", "consolidations")
    }


def create_app(settings=None, client=None, start_worker=True):
    load_dotenv(override=False)
    settings = settings or Settings()
    repo = Repository(settings.data_dir / "audit.sqlite3")
    ingestion = IngestionService(repo, settings)
    runner = AnalysisRunner(repo, client or LiteLLMClient(settings), settings)
    worker = Worker(repo, runner)

    @asynccontextmanager
    async def lifespan(app):
        if start_worker:
            worker.start()
        yield
        if start_worker:
            worker.close()

    app = FastAPI(title="AuditAuthor", version="0.1.0", lifespan=lifespan)
    app.state.repository, app.state.runner = repo, runner

    def require_job(job_id):
        job = repo.get_job(job_id)
        if job is None:
            raise HTTPException(404, "Analysis not found.")
        return job

    def require_capacity():
        if (
            sum(j["status"] in ("queued", "running") for j in repo.list_jobs())
            >= settings.max_pending_jobs
        ):
            raise HTTPException(
                429, "Analysis queue is full. Wait for an active analysis to finish."
            )

    @app.get("/health")
    def health():
        return {
            "status": "ok",
            "model_configured": bool(settings.model),
            "credentials_configured": bool(os.getenv("OPENAI_API_KEY")),
        }

    @app.get("/reports", response_model=list[ReportSummary])
    def reports():
        return [report_summary(r) for r in repo.list_reports()]

    @app.post("/reports", status_code=201, response_model=ReportSummary)
    async def upload(file: UploadFile):
        data = bytearray()
        try:
            while block := await file.read(1024 * 1024):
                data.extend(block)
                if len(data) > settings.max_upload_mb * 1024 * 1024:
                    raise HTTPException(413, "Report exceeds upload size limit.")
            report = await run_in_threadpool(
                ingestion.ingest, bytes(data), file.filename or "report.pdf"
            )
            return report_summary(report)
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from exc
        finally:
            await file.close()

    @app.get("/reports/{report_id}/file")
    def report_file(report_id: str):
        report = repo.get_report(report_id)
        if not report:
            raise HTTPException(404, "Report not found.")
        return FileResponse(
            ingestion.directory / f"{report['id']}.pdf",
            media_type="application/pdf",
            filename=report["name"],
            content_disposition_type="inline",
        )

    @app.get("/analyses", response_model=list[AnalysisSummary])
    def analyses():
        return [job_summary(j) for j in repo.list_jobs()]

    @app.post("/analyses", status_code=202, response_model=AnalysisSummary)
    def analyse(request: AnalysisRequest):
        if not settings.model:
            raise HTTPException(503, "Set AUDIT_MODEL to an OpenAI structured-output model.")
        if client is None and not os.getenv("OPENAI_API_KEY"):
            raise HTTPException(503, "Set OPENAI_API_KEY in the backend environment.")
        if any(repo.get_report(i) is None for i in request.report_ids):
            raise HTTPException(404, "One or more reports were not found.")
        with repo.lock:
            require_capacity()
            job = new_job(request.report_ids, settings)
            repo.save_job(job)
        return job_summary(job)

    @app.get("/analyses/{job_id}", response_model=AnalysisSummary)
    def analysis(job_id: str):
        return job_summary(require_job(job_id))

    @app.get("/analyses/{job_id}/findings", response_model=list[Finding])
    def findings(job_id: str):
        return require_job(job_id)["findings"]

    @app.get("/analyses/{job_id}/insights", response_model=list[Insight])
    def insights(job_id: str):
        return require_job(job_id)["insights"]

    @app.post("/analyses/{job_id}/retry", status_code=202, response_model=AnalysisSummary)
    def retry(job_id: str):
        with repo.lock:
            job = require_job(job_id)
            if job["status"] not in ("partial", "failed", "interrupted"):
                raise HTTPException(
                    409, "Only partial, failed or interrupted analyses can be retried."
                )
            if job["prompt_version"] != PROMPT_VERSION or job["schema_version"] != SCHEMA_VERSION:
                raise HTTPException(409, "Analysis version changed. Create a new analysis.")
            require_capacity()
            job["history"].append(
                {"updated_at": job["updated_at"], "errors": job["errors"], "status": job["status"]}
            )
            job["status"] = "queued"
            repo.save_job(job)
            return job_summary(job)

    @app.get("/analyses/{job_id}/export")
    def export(job_id: str, format: str = "json"):
        job = require_job(job_id)
        if format == "json":
            payload = {
                **job_summary(job),
                "findings": job["findings"],
                "insights": job["insights"],
                "reports": [report_summary(repo.get_report(i)) for i in job["report_ids"]],
            }
            return Response(
                json.dumps(payload, indent=2, ensure_ascii=False),
                media_type="application/json",
                headers={"Content-Disposition": f'attachment; filename="{job_id}.json"'},
            )
        if format != "csv":
            raise HTTPException(422, "Export format must be csv or json.")
        buffer = io.StringIO(newline="")
        columns = [
            "id",
            "report_id",
            "title",
            "agency",
            "system",
            "theme",
            "weakness",
            "risk",
            "reported_remediation",
            "evidence",
            "analysis_status",
        ]
        writer = csv.DictWriter(buffer, fieldnames=columns)
        writer.writeheader()
        for finding in job["findings"]:
            row = {k: finding.get(k) for k in columns}
            row["evidence"] = json.dumps(finding["evidence"], ensure_ascii=False)
            row["analysis_status"] = job["status"]
            # Prevent spreadsheet formula execution when opening CSV exports.
            writer.writerow(
                {
                    k: (
                        "'" + v
                        if isinstance(v, str) and v.lstrip().startswith(("=", "+", "-", "@"))
                        else v
                    )
                    for k, v in row.items()
                }
            )
        return Response(
            buffer.getvalue(),
            media_type="text/csv",
            headers={"Content-Disposition": f'attachment; filename="{job_id}.csv"'},
        )

    return app
