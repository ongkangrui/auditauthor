import argparse
from pathlib import Path
from urllib.parse import urlparse

from auditauthor.adapters.ago import download_report
from auditauthor.adapters.repository import Repository
from auditauthor.config import Settings
from auditauthor.services.ingestion import IngestionService


def main():
    parser = argparse.ArgumentParser(description="Import public AGO annual report PDFs")
    commands = parser.add_subparsers(dest="command", required=True)
    local = commands.add_parser("import", help="Import explicitly selected local PDFs")
    local.add_argument("paths", nargs="+", type=Path)
    download = commands.add_parser(
        "download", help="Download explicitly selected official AGO PDF URLs"
    )
    download.add_argument("urls", nargs="+")
    args = parser.parse_args()
    settings = Settings()
    service = IngestionService(Repository(settings.data_dir / "audit.sqlite3"), settings)
    try:
        if args.command == "import":
            for path in args.paths:
                if path.stat().st_size > settings.max_upload_mb * 1024 * 1024:
                    raise ValueError(f"{path.name} exceeds upload size limit.")
                report = service.ingest(path.read_bytes(), path.name)
                print(f"Imported {report['name']}: {report['id']}")
        else:
            for url in args.urls:
                data, final_url = download_report(url, settings.max_upload_mb * 1024 * 1024)
                report = service.ingest(data, Path(urlparse(final_url).path).name, source_url=url)
                print(f"Downloaded {report['name']}: {report['id']}")
    except (ValueError, OSError) as exc:
        parser.exit(1, f"{exc}\n")


if __name__ == "__main__":
    main()
