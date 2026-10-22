import hashlib
import json
from pathlib import Path

import pytest

from auditauthor.adapters.pdf import extract_pdf, make_chunks
from auditauthor.services.evidence import normalize

ROOT = Path(__file__).resolve().parents[2]
REPORTS = sorted((ROOT / "input").glob("*.pdf"))


@pytest.mark.parametrize("path", REPORTS, ids=lambda p: p.name)
def test_supplied_report_extraction(path):
    pages = extract_pdf(path.read_bytes(), 500)
    assert len(pages) > 90
    assert sum(len(p["text"]) for p in pages) > 100000
    chunks = make_chunks(pages, 14000, 2000)
    covered = {part["page"] for c in chunks for part in c["parts"]}
    assert all(p["number"] in covered for p in pages if p["text"])


def test_benchmark_quotes_match_sources():
    data = json.loads((ROOT / "docs/EVALUATION_SET.json").read_text(encoding="utf-8"))
    assert sum(len(c["expected"]) for c in data["cases"]) >= 20
    assert sum(not c["expected"] for c in data["cases"]) >= 4
    cache = {}
    for case in data["cases"]:
        path = ROOT / "input" / case["report"]
        if case["report"] not in cache:
            content = path.read_bytes()
            cache[case["report"]] = (hashlib.sha256(content).hexdigest(), extract_pdf(content, 500))
        digest, pages = cache[case["report"]]
        assert digest == case["report_sha256"]
        for excerpt in case["pages"]:
            assert normalize(excerpt["text"]) in normalize(pages[excerpt["number"] - 1]["text"])
