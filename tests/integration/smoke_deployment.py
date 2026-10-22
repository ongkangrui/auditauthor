"""Read-only smoke check of the running Compose app after importing the samples.

Run explicitly: uv run python tests/integration/smoke_deployment.py
This does not submit paid analyses or alter saved reports.
"""

import hashlib

import httpx


def main():
    with httpx.Client(base_url="http://localhost:8000", timeout=30) as client:
        health = client.get("/health")
        health.raise_for_status()
        assert health.json()["status"] == "ok"
        reports_response = client.get("/reports")
        reports_response.raise_for_status()
        reports = reports_response.json()
        expected = {
            "ar_fy2021_22.pdf": 109,
            "ar_fy2022_23.pdf": 113,
            "ar_fy2023_24.pdf": 122,
            "ar_fy2024_25.pdf": 98,
        }
        for name, page_count in expected.items():
            report = next(r for r in reports if r["name"] == name)
            assert report["page_count"] == page_count
            original = client.get(f"/reports/{report['id']}/file")
            original.raise_for_status()
            assert hashlib.sha256(original.content).hexdigest() == report["sha256"]
        spec = client.get("/openapi.json")
        spec.raise_for_status()
        assert "/analyses/{job_id}/retry" in spec.json()["paths"]
        client.get("/analyses").raise_for_status()
    frontend = httpx.get("http://localhost:8501/_stcore/health", timeout=30)
    frontend.raise_for_status()
    assert frontend.text == "ok"
    print("PASS: frontend/backend health, four persisted reports, original PDF hashes, API schema.")
    print("Model configured:", health.json()["model_configured"])
    print("Credentials configured:", health.json()["credentials_configured"])


if __name__ == "__main__":
    main()
