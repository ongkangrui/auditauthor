import json
import sqlite3
import threading
from contextlib import contextmanager
from pathlib import Path


class Repository:
    """Small JSON-backed aggregates; SQL owns identity and queue status."""

    def __init__(self, path: Path):
        path.parent.mkdir(parents=True, exist_ok=True)
        self.path = path
        self.lock = threading.RLock()
        with self.connect() as db:
            db.executescript("""
                PRAGMA journal_mode=WAL;
                CREATE TABLE IF NOT EXISTS reports (id TEXT PRIMARY KEY, payload TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS jobs (
                    id TEXT PRIMARY KEY, status TEXT NOT NULL, payload TEXT NOT NULL
                );
            """)

    @contextmanager
    def connect(self):
        connection = sqlite3.connect(self.path, timeout=30)
        try:
            with connection:
                yield connection
        finally:
            connection.close()

    def get_report(self, report_id):
        with self.connect() as db:
            row = db.execute("SELECT payload FROM reports WHERE id=?", (report_id,)).fetchone()
        return json.loads(row[0]) if row else None

    def list_reports(self):
        with self.connect() as db:
            return [
                json.loads(r[0])
                for r in db.execute("SELECT payload FROM reports ORDER BY rowid DESC")
            ]

    def add_report(self, report):
        with self.connect() as db:
            db.execute(
                "INSERT OR IGNORE INTO reports VALUES (?, ?)", (report["id"], json.dumps(report))
            )

    def get_job(self, job_id):
        with self.connect() as db:
            row = db.execute("SELECT payload FROM jobs WHERE id=?", (job_id,)).fetchone()
        return json.loads(row[0]) if row else None

    def update_report(self, report):
        with self.connect() as db:
            db.execute(
                "UPDATE reports SET payload=? WHERE id=?", (json.dumps(report), report["id"])
            )

    def list_jobs(self):
        with self.connect() as db:
            return [
                json.loads(r[0]) for r in db.execute("SELECT payload FROM jobs ORDER BY rowid DESC")
            ]

    def save_job(self, job):
        with self.connect() as db:
            db.execute(
                "INSERT INTO jobs VALUES (?, ?, ?) ON CONFLICT(id) DO UPDATE SET "
                "status=excluded.status, payload=excluded.payload",
                (job["id"], job["status"], json.dumps(job)),
            )

    def next_job(self):
        with self.lock, self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute(
                "SELECT payload FROM jobs WHERE status='queued' ORDER BY rowid LIMIT 1"
            ).fetchone()
            if not row:
                return None
            job = json.loads(row[0])
            job["status"] = "running"
            db.execute(
                "UPDATE jobs SET status=?, payload=? WHERE id=?",
                (job["status"], json.dumps(job), job["id"]),
            )
            return job

    def recover(self):
        for job in self.list_jobs():
            if job["status"] == "running":
                job["status"] = "interrupted"
                job["errors"].append(
                    {"stage": "worker", "message": "Processing interrupted; retry available."}
                )
                self.save_job(job)
