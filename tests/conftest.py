import json

import pymupdf
import pytest

from auditauthor.domain.models import Consolidation, Extraction


@pytest.fixture
def pdf_bytes():
    with pymupdf.open() as doc:
        page = doc.new_page()
        page.insert_text(
            (72, 72), "Agency A system Alpha has no review of privileged account activities."
        )
        return doc.tobytes()


def observation(**overrides):
    return {
        "title": "Missing privileged activity review",
        "agency": "Agency A",
        "system": "Alpha",
        "theme": "logging/monitoring",
        "weakness": "Privileged activities were not reviewed.",
        "risk": None,
        "reported_remediation": None,
        "source_kind": "detail",
        "evidence": [
            {
                "page": 1,
                "excerpt": "Agency A system Alpha has no review of privileged account activities.",
            }
        ],
        **overrides,
    }


class FakeModel:
    def __init__(self):
        self.extract_calls = 0
        self.consolidate_calls = 0

    def generate(self, system, content, schema, model):
        if schema is Extraction:
            self.extract_calls += 1
            return Extraction(observations=[observation()]), "fake-snapshot"
        self.consolidate_calls += 1
        findings = json.loads(content)
        return Consolidation(
            insights=[
                {
                    "theme": findings[0]["theme"],
                    "weakness": "Missing activity review",
                    "audit_implication": "Review monitoring controls.",
                    "observation_ids": [f["id"] for f in findings],
                }
            ],
            duplicate_groups=[],
        ), "fake-snapshot"
