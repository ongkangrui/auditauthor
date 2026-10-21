import hashlib
from pathlib import Path

from auditauthor.adapters.pdf import extract_pdf
from auditauthor.domain.models import Report


class IngestionService:
    def __init__(self, repository, settings):
        self.repository = repository
        self.settings = settings
        self.directory = settings.data_dir / "reports"
        self.directory.mkdir(parents=True, exist_ok=True)

    def ingest(self, data: bytes, name: str, source_url: str | None = None) -> dict:
        if len(data) > self.settings.max_upload_mb * 1024 * 1024:
            raise ValueError("Report exceeds upload size limit.")
        report_id = hashlib.sha256(data).hexdigest()
        existing = self.repository.get_report(report_id)
        if existing:
            if source_url and not existing["source_url"]:
                existing["source_url"] = source_url
                self.repository.update_report(existing)
            return existing
        pages = extract_pdf(data, self.settings.max_pages)
        path = self.directory / f"{report_id}.pdf"
        path.write_bytes(data)
        report = {
            "id": report_id,
            "sha256": report_id,
            "name": Path(name.replace("\\", "/")).name[:200],
            "source_url": source_url,
            "page_count": len(pages),
            "pages": pages,
        }
        report = Report.model_validate(report).model_dump()
        self.repository.add_report(report)
        return report
