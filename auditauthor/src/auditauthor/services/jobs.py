import json
import threading
from datetime import UTC, datetime
from uuid import uuid4

from auditauthor.adapters.pdf import make_chunks
from auditauthor.domain.models import PROMPT_VERSION, SCHEMA_VERSION, Extraction
from auditauthor.domain.ports import AnalysisStore, ModelClient
from auditauthor.prompts import EXTRACT
from auditauthor.services.consolidation import consolidate_theme
from auditauthor.services.evidence import deduplicate, validate_observation


def now():
    return datetime.now(UTC).isoformat()


def new_job(report_ids: list[str], settings) -> dict:
    return {
        "id": uuid4().hex,
        "report_ids": list(dict.fromkeys(report_ids)),
        "status": "queued",
        "created_at": now(),
        "updated_at": now(),
        "model": settings.model,
        "resolved_models": [],
        "prompt_version": PROMPT_VERSION,
        "schema_version": SCHEMA_VERSION,
        "chunk_chars": settings.chunk_chars,
        "overlap_chars": settings.overlap_chars,
        "chunks": [],
        "findings": [],
        "insights": [],
        "errors": [],
        "history": [],
        "coverage": {},
        "consolidations": {},
    }


class AnalysisRunner:
    def __init__(self, repository: AnalysisStore, client: ModelClient, settings):
        self.repository = repository
        self.client = client
        self.settings = settings

    def save(self, job):
        chunks = job["chunks"]
        reports = [self.repository.get_report(i) for i in job["report_ids"]]
        warnings = [
            {"report_id": r["id"], "page": p["number"], "message": p["warning"]}
            for r in reports
            for p in r["pages"]
            if p["warning"]
        ]
        job["coverage"] = {
            "total_chunks": len(chunks),
            "completed_chunks": sum(c["status"] == "complete" for c in chunks),
            "failed_chunks": sum(c["status"] in ("partial", "failed") for c in chunks),
            "total_pages": sum(r["page_count"] for r in reports),
            "page_warnings": warnings,
        }
        job["updated_at"] = now()
        self.repository.save_job(job)

    def run(self, job, stop: threading.Event | None = None):
        job["status"] = "running"
        job["errors"] = []
        reports = {i: self.repository.get_report(i) for i in job["report_ids"]}
        if not job["chunks"]:
            for report_id, report in reports.items():
                for chunk in make_chunks(report["pages"], job["chunk_chars"], job["overlap_chars"]):
                    job["chunks"].append(
                        {
                            "report_id": report_id,
                            "index": chunk["index"],
                            "status": "pending",
                            "findings": [],
                            "errors": [],
                        }
                    )
        self.save(job)
        chunk_lookup = {
            rid: make_chunks(r["pages"], job["chunk_chars"], job["overlap_chars"])
            for rid, r in reports.items()
        }
        changed = False
        for state in job["chunks"]:
            if stop and stop.is_set():
                job["status"] = "interrupted"
                self.save(job)
                return
            if state["status"] == "complete":
                continue
            changed = True
            # Persist invalidation with the chunk checkpoint, including across abrupt restarts.
            job["consolidations"] = {}
            report = reports[state["report_id"]]
            chunk = chunk_lookup[state["report_id"]][state["index"]]
            state["errors"] = []
            try:
                extracted, resolved = self.client.generate(
                    EXTRACT, json.dumps(chunk, ensure_ascii=False), Extraction, job["model"]
                )
                extracted = Extraction.model_validate(extracted)
                if resolved not in job["resolved_models"]:
                    job["resolved_models"].append(resolved)
                valid = []
                for observation in extracted.observations:
                    try:
                        valid.append(
                            validate_observation(observation, report, chunk).model_dump(mode="json")
                        )
                    except ValueError as exc:
                        state["errors"].append(
                            {"stage": "evidence", "message": str(exc), "title": observation.title}
                        )
                state["findings"] = valid
                state["status"] = "partial" if state["errors"] else "complete"
            except Exception as exc:  # noqa: BLE001 -- isolate chunk failures and retain successful work
                state["status"] = "failed"
                state["errors"] = [{"stage": "extraction", "message": safe_error(exc)}]
            self.save(job)
        job["findings"] = deduplicate([f for c in job["chunks"] for f in c["findings"]])
        # Successful extraction changes invalidate downstream cached consolidation.
        if changed:
            job["consolidations"] = {}
        accepted, insights = [], []
        themes = sorted({f["theme"] for f in job["findings"]})
        for theme in themes:
            if stop and stop.is_set():
                job["status"] = "interrupted"
                self.save(job)
                return
            findings = [f for f in job["findings"] if f["theme"] == theme]
            cached = job["consolidations"].get(theme)
            if not cached:
                try:
                    kept, grouped, resolved = consolidate_theme(self.client, findings, job["model"])
                    cached = {"findings": kept, "insights": grouped}
                    job["consolidations"][theme] = cached
                    if resolved not in job["resolved_models"]:
                        job["resolved_models"].append(resolved)
                except Exception as exc:  # noqa: BLE001 -- isolate theme failures
                    job["errors"].append(
                        {"stage": "consolidation", "theme": theme, "message": safe_error(exc)}
                    )
            accepted.extend(cached["findings"] if cached else findings)
            insights.extend(cached["insights"] if cached else [])
            self.save(job)
        job["findings"], job["insights"] = accepted, insights
        job["errors"].extend(
            {**e, "report_id": c["report_id"], "chunk": c["index"]}
            for c in job["chunks"]
            for e in c["errors"]
        )
        self.save(job)
        incomplete = bool(job["errors"] or job["coverage"]["page_warnings"])
        job["status"] = (
            (
                "partial"
                if any(c["status"] in ("complete", "partial") for c in job["chunks"])
                else "failed"
            )
            if incomplete
            else "complete"
        )
        self.save(job)


def safe_error(exc):
    # Only internally generated ValueError / RuntimeError messages are safe to expose.
    if type(exc) in (ValueError, RuntimeError):
        return str(exc)
    return f"Processing failed ({type(exc).__name__}); retry or inspect configuration."


class Worker:
    def __init__(self, repository, runner):
        self.repository, self.runner = repository, runner
        self.stop = threading.Event()
        self.thread = threading.Thread(target=self.loop, name="analysis-worker", daemon=True)

    def loop(self):
        while not self.stop.is_set():
            job = self.repository.next_job()
            if not job:
                self.stop.wait(0.5)
                continue
            try:
                self.runner.run(job, self.stop)
            except Exception as exc:  # noqa: BLE001 -- keep the persistent worker alive
                job["status"] = "failed"
                job["errors"].append({"stage": "worker", "message": safe_error(exc)})
                self.repository.save_job(job)

    def start(self):
        self.repository.recover()
        self.thread.start()

    def close(self):
        self.stop.set()
        self.thread.join(timeout=5)
